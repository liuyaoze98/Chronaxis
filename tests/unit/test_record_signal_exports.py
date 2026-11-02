"""信号导出在同次读取在线写出，只有最后一组临时保留。"""

from configuration_fixtures import current_fixture
import csv,json
from pathlib import Path
from uuid import uuid4
import unittest
from unittest.mock import patch
from chronaxis import AnalysisRunner,AnalysisPlan,validate_analysis_plan
import test_record_runner as raw_cases
from test_window_delta_runner import delta_config

class RecordSignalExportTests(unittest.TestCase):
    """三格式、两后端及解析信号输出保原值/质量，末端不补假采样。"""
    setUp=raw_cases.RecordRunnerTests.setUp
    asc=raw_cases.RecordRunnerTests.asc
    csv=raw_cases.RecordRunnerTests.csv
    blf=raw_cases.RecordRunnerTests.blf
    fixtures=raw_cases.RecordRunnerTests.fixtures
    plan=raw_cases.RecordRunnerTests.plan

    def rows(self,result):
        """发布一次并读有限信号表。参数: 完成结果。返回: 文件行字典。异常: 原I/O错。"""
        path=self.root/uuid4().hex;result.write(path)
        records=[json.loads(line) for line in (path/'exports.jsonl').read_text(encoding='utf-8').splitlines()]
        output=next(r for r in records if r['export_type']=='signal_csv')
        root=path/'exports'/output['directory']
        data={}
        for name in ('original.csv','resampled.csv'):
            if (root/name).exists():
                with (root/name).open(encoding='utf-8',newline='') as f:data[name]=list(csv.DictReader(f))
        return data,records

    def test_three_formats_mixed_frames_and_calculations(self):
        """一遍输入同时算能量、写原帧和信号；信号只含所选电流。"""
        for kind,path in self.fixtures().items():
            def edit(raw):
                raw['outputs']['signal_csv']={'signals':['current']}
                raw['outputs']['can_frames']={'source':raw['sources'][0]['name'],'format':'asc'}
            plan=self.plan(kind,path,'fixed',edit)
            self.assertTrue(validate_analysis_plan(plan).execution_ready)
            with AnalysisRunner().run(plan,self.root/uuid4().hex) as result:
                data,records=self.rows(result)
                self.assertEqual([r['export_type'] for r in records],['signal_csv','can_frames'])
                self.assertEqual([r['value'] for r in data['original.csv']],['10.0','12.0'])
                self.assertTrue(all(r['signal']=='current' for r in data['original.csv']))
                self.assertEqual(len(list(result.iter_calculations())),2)

    def test_export_only_linear_online_and_ttl(self):
        """所选信号不进入计算最新值仓；既有离线插值使用端点/间隔政策，保缺失标记。"""
        from chronaxis.execution.record_signal_export import RecordSignalExport
        original=RecordSignalExport.observe;max_pending=[]
        def inspect(owner,group):
            result=original(owner,group);max_pending.append(len(owner._pending));return result
        for backend in ('reference','numpy'):
            raw=delta_config();raw.update(config_version=3)
            raw['rules']=[];raw['outputs']['signal_csv']={'signals':['voltage'],'resampling':{'continuous':['voltage'],'period':'1ns','max_gap':'3ns'}}
            with patch.object(RecordSignalExport,'observe',inspect),patch('chronaxis.execution.record_session_calculations.LatestSignalState',side_effect=AssertionError('纯导出不需要最新值仓')):
                with AnalysisRunner(backend).run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex) as result:
                    data,records=self.rows(result)
                    self.assertNotIn('original.csv',data)
                    values={int(row['time_ns']):row for row in data['resampled.csv']}
                    self.assertEqual(values[3]['value'],'2.5')
                    self.assertEqual(values[3]['status'],'estimated')
                    self.assertEqual(values[13]['reason'],'missing_right')
                    self.assertNotIn(14,values)
            self.assertLessEqual(max(max_pending),1)

    def test_empty_single_and_cancel(self):
        """空/单点不补范围；实际写出后取消必须回收费用。"""
        from chronaxis.results.signal_exports import SignalCSVWriter
        for rows in ([],[{'time':'0ns','values':{'voltage':3}}]):
            raw=delta_config();raw.update(config_version=3);raw['rules']=[]
            raw['sources'][0]['rows']=rows;raw['outputs']['signal_csv']={'signals':['voltage']}
            with AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex) as result:
                data,_=self.rows(result);self.assertEqual(data['original.csv'],[])
        raw=delta_config();raw.update(config_version=3);raw['outputs']['signal_csv']={'signals':['voltage']}
        original=SignalCSVWriter.push;budgets=[]
        def cancel(owner,sample):
            budgets.append(owner._budget);original(owner,sample);raise KeyboardInterrupt('synthetic signal write cancel')
        with patch.object(SignalCSVWriter,'push',cancel):
            with self.assertRaises(KeyboardInterrupt):AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex)
        self.assertTrue(budgets);self.assertTrue(all(b.ram_bytes==0 for b in budgets))

    def test_segment_export_only_requested_samples(self):
        """按周期窗口回读电流两行；必要样本仓不保存未请求电压或另一个时间轴。"""
        from chronaxis.execution.record_export_samples import RecordExportSamples
        original=RecordExportSamples.append;names=[]
        def observe(owner,sample):
            names.append(sample.name);return original(owner,sample)
        for kind,path in self.fixtures().items():
            def edit(raw):
                raw['rules']=[dict(name='edge',rule_type='rising_edge',condition='current>=12')]
                raw['windows']=[dict(name='around',rule='edge',anchor='point',pre='0.1s',post='0.1s')]
                raw['outputs']['signal_csv']={'signals':['current'],'scope':'segments','window':'around'}
            with patch.object(RecordExportSamples,'append',observe):
                with AnalysisRunner().run(self.plan(kind,path,'fixed',edit),self.root/uuid4().hex) as result:
                    data,records=self.rows(result)
                    self.assertEqual([r['value'] for r in data['original.csv']],['10.0','12.0'])
                    segment,=result.iter_segments();self.assertEqual(records[0]['segment_id'],segment.segment_id)
        self.assertEqual(set(names),{'current'})

    def test_sample_history_enum_uint64_and_truncation(self):
        """枚举仅存编码、uint64不经float；短读明确失败，不输出前缀成功。"""
        from chronaxis.execution.record_export_samples import RecordExportSamples
        from chronaxis.core.binding import SignalDefinition
        from chronaxis.core.models import SourceRef,Interval
        from chronaxis.core.numeric import ScalarValue
        from chronaxis.core.types import SignalDType as D,QualityFlag as Q
        from chronaxis.execution.history_records import HistorySample
        from chronaxis.results.budget import ResourceBudget
        definitions=(SignalDefinition('state','bus','state',D.ENUM,'1',10,choices=((0,'off'),(1,'scope'))),
                     SignalDefinition('counter','bus','counter',D.UINT64,'1',10))
        budget=ResourceBudget();owner=RecordExportSamples(budget,self.root,definitions,'session')
        self.addCleanup(owner.close)
        for t,index,physical,value in ((0,0,1,ScalarValue('scope',D.ENUM,labels=('off','scope'))),
              (1,1,2**64-1,ScalarValue(2**64-1,D.UINT64)),(2,0,0,ScalarValue(None,D.ENUM,False,Q.MISSING,('off','scope')))):
            d=definitions[index]
            owner.append(HistorySample(0,d.name,t,t,physical,value,d.unit,SourceRef('session','bus',d.field),False,None))
        actual=list(owner.rows(Interval(0,3)))
        self.assertEqual([s.value.value for s in actual],['scope',2**64-1,None])
        self.assertFalse(actual[-1].value.valid)
        owner._file.truncate(1)
        with self.assertRaisesRegex(ValueError,'短读'):list(owner.rows(Interval(0,3)))
        owner.close();self.assertEqual(budget.ram_bytes,0)

    def test_dbc_period_same_three_formats_and_schema(self):
        """DBC100ms在三格式生成同一0/0.1/0.2网格，静态声明不读文件。"""
        from jsonschema import Draft202012Validator
        docs=Path(__file__).resolve().parents[2]/'Docs/Schema'
        doc=json.loads((docs/'analysis.schema.json').read_text(encoding='utf-8'))
        for kind,path in self.fixtures().items():
            raw_seen=[]
            def edit(raw):
                raw['outputs']['signal_csv']={'signals':['current'],'resampling':{'continuous':['current'],'period':{'mode':'dbc'},'max_gap':'1s'}}
                raw_seen.append(raw)
            plan=self.plan(kind,path,'fixed',edit)
            Draft202012Validator(doc).validate(raw_seen[0])
            self.assertEqual(plan.outputs.signal_csv.period_driver,'current')
            self.assertIsNone(plan.outputs.signal_csv.spec.resampling.period_ns)
            for backend in ('reference','numpy'):
                with AnalysisRunner(backend).run(plan,self.root/uuid4().hex) as result:
                    data,_=self.rows(result)
                    rows=data['resampled.csv']
                    self.assertEqual([int(r['time_ns']) for r in rows],[0,100000000,200000000])
                    self.assertAlmostEqual(float(rows[1]['value']),10+2*.1/.12,places=4)
                    self.assertEqual(rows[-1]['reason'],'missing_right')

    def test_parsed_dbc_and_explicit_null_driver_rejected(self):
        """已解析数据不借其他DBC装成原帧；显式null不是自动选择。"""
        from chronaxis import PlanValidationError
        raw=delta_config();raw.update(config_version=3)
        raw['outputs']['signal_csv']={'signals':['voltage'],'resampling':{'continuous':['voltage'],'period':{'mode':'dbc'},'max_gap':'10ns'}}
        with self.assertRaises(PlanValidationError):AnalysisPlan.from_dict(current_fixture(raw))
        path=self.fixtures()['can_asc']
        def edit(raw):
            raw['outputs']['signal_csv']={'signals':['current'],'resampling':{'continuous':['current'],'period':{'mode':'dbc','driver':None},'max_gap':'1s'}}
        with self.assertRaises(PlanValidationError):self.plan('can_asc',path,'fixed',edit)

    def test_dbc_multi_message_requires_driver_and_bad_cycle_fails_before_read(self):
        """两个不同报文不能自动取某个周期；缺/零周期在首条记录前报错。"""
        from chronaxis import PlanValidationError,AnalysisError
        from chronaxis.execution.record_source_cursor import RecordSourceCursor
        fixtures=self.fixtures()
        def ambiguous(raw):
            raw['signals'][0]['field'].update(frame_id=257)
            raw['outputs']['signal_csv']={'signals':['current','voltage'],'resampling':{'continuous':['current','voltage'],'period':{'mode':'dbc'},'max_gap':'1s'}}
        with self.assertRaisesRegex(PlanValidationError,'多个报文'):self.plan('can_asc',fixtures['can_asc'],'fixed',ambiguous)
        def explicit(raw):
            ambiguous(raw);raw['outputs']['signal_csv']['resampling']['period']['driver']='current'
        self.assertEqual(self.plan('can_asc',fixtures['can_asc'],'fixed',explicit).outputs.signal_csv.period_driver,'current')
        original=self.dbc.read_text(encoding='utf-8')
        for invalid in ('','BA_ "GenMsgCycleTime" BO_ 256 0;'):
            self.dbc.write_text(original.replace('BA_ "GenMsgCycleTime" BO_ 256 100;',invalid),encoding='utf-8')
            def edit(raw):
                raw['outputs']['signal_csv']={'signals':['current'],'resampling':{'continuous':['current'],'period':{'mode':'dbc'},'max_gap':'1s'}}
            with patch.object(RecordSourceCursor,'peek',side_effect=AssertionError('不应读取首帧')):
                with self.assertRaises(AnalysisError):AnalysisRunner().run(self.plan('can_asc',fixtures['can_asc'],'actual',edit),self.root/uuid4().hex)
