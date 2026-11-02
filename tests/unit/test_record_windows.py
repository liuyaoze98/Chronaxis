"""从公开AnalysisRunner核周期选窗、跨批合并和片段指标；预期均由原记录手算。"""

from configuration_fixtures import current_fixture
from itertools import product
from uuid import uuid4
import unittest
from chronaxis import AnalysisRunner,AnalysisPlan
from chronaxis.results import SummarySegmentRow
import test_record_runner as raw_cases
import test_record_sources as source_cases


class RawRecordWindowTests(unittest.TestCase):
    """同一三格式数据的窗口实际边界与所选记录计时一致。"""
    setUp=raw_cases.RecordRunnerTests.setUp
    asc=raw_cases.RecordRunnerTests.asc
    csv=raw_cases.RecordRunnerTests.csv
    blf=raw_cases.RecordRunnerTests.blf
    fixtures=raw_cases.RecordRunnerTests.fixtures
    plan=raw_cases.RecordRunnerTests.plan

    @staticmethod
    def edit(raw):
        """事件在0.12秒，取前后各0.1。参数: 配置。返回: None。异常: 无。"""
        raw['rules']=[dict(name='edge',rule_type='rising_edge',condition='current >= 12')]
        raw['windows']=[dict(name='around',rule='edge',anchor='point',pre='0.1s',post='0.1s',merge='none')]
        raw['calculations']=[dict(name='energy',scope='segment:around',operation='integral',expr='power',unit='J')]

    def test_three_formats_actual_fixed_dbc(self):
        """actual取0.02—0.22，fixed/DBC取0—0.3；保实际端点及父ID。"""
        for (kind,path),backend,mode in product(self.fixtures().items(),('reference','numpy'),('actual','fixed','dbc')):
            with self.subTest(kind=kind,backend=backend,mode=mode):
                result=AnalysisRunner(backend).run(self.plan(kind,path,mode,self.edit),self.root/uuid4().hex)
                self.addCleanup(result.close)
                segment,=tuple(result.iter_segments())
                event,=tuple(result.iter_events())
                calculation,=tuple(result.iter_calculations())
                self.assertIs(type(segment),SummarySegmentRow)
                self.assertAlmostEqual(segment.start_ns/1e9,.02 if mode=='actual' else 0,places=5)
                self.assertAlmostEqual(segment.end_ns/1e9,.22 if mode=='actual' else .3,places=5)
                self.assertEqual(segment.parent_event_ids,(event.event_id,))
                self.assertEqual(segment.status,'complete')
                self.assertAlmostEqual(calculation.value,880,places=3)
                self.assertEqual(calculation.parent_id,segment.segment_id)
                self.assertFalse(hasattr(segment,'requested'))
                budget=result.spool.budget
                result.close()
                self.assertEqual(budget.ram_bytes,0)

    def test_fractional_period_and_eof_clipping(self):
        """半周期按原对比例：0.06—0.21；超过尾端只裁到0.3并标部分。"""
        path=self.fixtures()['can_asc']
        for backend,post,strict in product(('reference','numpy'),('0.05s','0.3s'),(False,True)):
            def edit(raw):
                """不复制请求与实际时间轴。参数: 配置。返回: None。异常: 无。"""
                self.edit(raw)
                raw['windows'][0].update(pre='0.05s',post=post)
                raw['calculations'][0]['partial_policy']='strict' if strict else 'report'
            with AnalysisRunner(backend).run(self.plan('can_asc',path,'fixed',edit),self.root/uuid4().hex) as result:
                segment,=tuple(result.iter_segments())
                calculation,=tuple(result.iter_calculations())
                self.assertEqual(segment.start_ns,60000000)
                self.assertEqual(segment.end_ns,210000000 if post=='0.05s' else 300000000)
                self.assertEqual(segment.status,'complete' if post=='0.05s' else 'partial')
                if strict and post!='0.05s':
                    self.assertIsNone(calculation.value)
                else:
                    self.assertAlmostEqual(calculation.value,440 if post=='0.05s' else 680)

    def test_requested_coverage_and_compact_publication(self):
        """0.35秒周期请求只取得0.15秒，覆盖3/7；默认片段仅一套实际端点。"""
        import csv,json
        path=self.fixtures()['can_asc']
        for threshold in (.4,.5):
            def edit(raw):
                """明确要求覆盖门槛。参数: 配置。返回: None。异常: 无。"""
                self.edit(raw)
                raw['windows'][0].update(pre='0.05s',post='0.3s')
                raw['calculations'][0]['minimum_coverage']=threshold
            with AnalysisRunner().run(self.plan('can_asc',path,'fixed',edit),self.root/uuid4().hex) as result:
                calculation,=tuple(result.iter_calculations())
                self.assertEqual(calculation.coverage_status,'sufficient' if threshold==.4 else 'indeterminate')
                self.assertAlmostEqual(calculation.value,680.)
                output=self.root/uuid4().hex
                result.table_format = 'csv'  # 本项继续验收原交换字段及schema。
                result.write(output)
                manifest=json.loads((output/'run_manifest.json').read_text(encoding='utf-8'))
                self.assertEqual(manifest['row_schema_versions']['segments'],11)
                with (output/'segments.csv').open(encoding='utf-8-sig',newline='') as stream:
                    row,=tuple(csv.DictReader(stream))
                self.assertNotIn('row_json',row)
                self.assertNotIn('requested_start_ns',row)
                self.assertEqual(len(json.loads(row['parent_event_ids'])),1)
                self.assertFalse((output/'quality.jsonl').exists())

    def test_cancel_after_segment_cleans_input_indexes_and_finished_events(self):
        """最终事件表已就绪但片段发布取消时，整个任务仍失败清理。"""
        from unittest.mock import patch
        from chronaxis.execution.record_session_calculations import RecordSessionCalculations
        original=RecordSessionCalculations._emit_segment
        budgets=[]
        def cancel(owner,segment):
            """真实追加后取消。参数: owner/片段。返回: 无。异常: KeyboardInterrupt。"""
            original(owner,segment)
            budgets.append(owner._budget)
            raise KeyboardInterrupt('segment cancellation')
        path=self.fixtures()['can_asc']
        root=self.root/uuid4().hex
        with patch.object(RecordSessionCalculations,'_emit_segment',cancel),self.assertRaises(KeyboardInterrupt):
            AnalysisRunner().run(self.plan('can_asc',path,'fixed',self.edit),root)
        self.assertTrue(budgets)
        self.assertEqual(budgets[0].ram_bytes,0)
        self.assertFalse(root.exists())


class MergedRecordWindowTests(unittest.TestCase):
    """跨批合并保全部父关联，不重算或覆盖原事件。"""
    setUp=source_cases.RecordSourcesTests.setUp

    def test_adjacent_and_exit_delay_merge(self):
        """每活动退出后再取一个记录周期，三段相接并裁EOF，最终只一段。"""
        for backend,merge in product(('reference','numpy'),('overlap_and_adjacent','exit_delay')):
            window=dict(name='merged',rule='alarm',anchor='activity',pre='0s',post='0.1s',merge=merge)
            if merge=='exit_delay':
                window.update(post='0s',exit_delay='0.1s')
            raw=dict(config_version=3,
                dataset=dict(name='data',entity='device',session='session',domain=dict(start='0s',end='1s')),
                sources=[dict(name='input',source_type='memory',time=dict(time_type='relative',unit='s',origin='clock'),
                    rows=[dict(time=t,values=dict(v=v)) for t,v in zip(('0s','0.12s','0.3s','0.45s','0.7s','0.9s'),(1,0,1,0,1,0))])],
                signals=[dict(name='value',source='input',field='v',dtype='float64',unit='1',valid_for='1s')],
                rules=[dict(name='alarm',rule_type='condition_duration',condition='value > 0',minimum_duration='0s')],
                windows=[window],calculations=[],intervals=dict(default=dict(mode='fixed',value='0.1s',driver='value')),
                execution=dict(batch_rows=1,result_buffer_rows=1))
            with self.subTest(backend=backend,merge=merge):
                with AnalysisRunner(backend).run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex) as result:
                    segment,=tuple(result.iter_segments())
                    events=tuple(result.iter_events())
                    self.assertEqual(len(events),3)
                    self.assertEqual(segment.parent_event_ids,tuple(event.event_id for event in events))
                    self.assertEqual((segment.start_ns,segment.end_ns,segment.status),(0,900000000,'partial'))
