"""从公开AnalysisRunner验证三格式规则与间隔选择，事件预期来自手算。"""

from configuration_fixtures import current_fixture

from itertools import product
from uuid import uuid4
import unittest
from unittest.mock import patch
from chronaxis import AnalysisRunner, AnalysisPlan, validate_analysis_plan
from chronaxis.results import SummaryEventRow
import test_record_runner as calculation_cases
from test_stability_runner import stable_config
import test_raw_can_continuous as files


class RecordRuleRunnerTests(unittest.TestCase):
    """规则输出只有事件表，混合统计时共用输入并保全局结果序号。"""

    setUp=files.RawCANContinuousTests.setUp
    asc=files.RawCANContinuousTests.asc
    csv=files.RawCANContinuousTests.csv
    blf=files.RawCANContinuousTests.blf
    fixtures=calculation_cases.RecordRunnerTests.fixtures
    plan=calculation_cases.RecordRunnerTests.plan

    def test_three_formats_modes_and_backends(self):
        """实际0.2秒确认；固定/DBC第三条0.3秒确认，EOF都在实际0.3秒截断。"""
        for (kind,path),mode,backend in product(self.fixtures().items(),('actual','fixed','dbc'),('reference','numpy')):
            def edit(raw):
                """仅请求一条电压持续规则。参数: raw。返回: None。异常: 无。"""
                raw['calculations']=[]
                raw['rules']=[dict(name='alarm',rule_type='condition_duration',condition='voltage > 350',minimum_duration='0.2s')]
            plan=self.plan(kind,path,mode,edit)
            self.assertTrue(validate_analysis_plan(plan).execution_ready)
            result=AnalysisRunner(backend).run(plan,self.root/uuid4().hex)
            self.addCleanup(result.close)
            row,=tuple(result.iter_events())
            self.assertIs(type(row),SummaryEventRow)
            self.assertEqual(row.status,'truncated')
            self.assertAlmostEqual(row.start_ns/1e9,0.)
            self.assertAlmostEqual(row.confirmed_ns/1e9,.2 if mode=='actual' else .3,places=5)
            self.assertAlmostEqual(row.end_ns/1e9,.3,places=5)
            self.assertEqual(result.spool.tables,('events',))
            budget=result.spool.budget
            result.close()
            self.assertEqual(budget.ram_bytes,0)

    def test_hysteresis_parsed_source_and_mixed_calculations(self):
        """内存温度85→77→77→75，实际0到9报警；统计和事件共用一次读取。"""
        raw=stable_config()
        raw.update(config_version=3)
        raw['intervals']=dict(default=dict(mode='fixed',value='2ns',driver='temperature'))
        raw['calculations']=[dict(name='hot',scope='session',operation='duration',condition='temperature > 80')]
        for backend in ('reference','numpy'):
            with AnalysisRunner(backend).run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex) as result:
                event,=tuple(result.iter_events())
                self.assertEqual((event.start_ns,event.end_ns,event.status),(0,9,'closed'))
                calculation,=tuple(result.iter_calculations())
                self.assertEqual(calculation.value,2e-9)

    def test_empty_and_single_input_do_not_invent_duration(self):
        """空来源不产事件；单条观测也不能拼出持续活动。"""
        self.fixtures()
        for path in (self.asc('').path,self.asc('0.0 1 100 Rx d 2 C8 0A\n').path):
            def edit(raw):
                """请求正持续门槛。参数: raw。返回: None。异常: 无。"""
                raw['calculations']=[]
                raw['rules']=[dict(name='alarm',rule_type='condition_duration',condition='voltage > 350',minimum_duration='0.1s')]
            with AnalysisRunner().run(self.plan('can_asc',path,'fixed',edit),self.root/uuid4().hex) as result:
                self.assertFalse(tuple(result.iter_events()))

    def test_cancel_after_real_event_releases_all_owners(self):
        """已产生真实事件后取消，不返回事件前缀；规则和读取由最高会话统一清理。"""
        from chronaxis.execution.record_session_calculations import RecordSessionCalculations
        original=RecordSessionCalculations._emit_event
        budgets=[]
        def cancel(owner,event):
            """实际写入后中断。参数: owner/event。返回: 无。异常: KeyboardInterrupt。"""
            original(owner,event)
            budgets.append(owner._budget)
            raise KeyboardInterrupt('cancel after event')
        raw=stable_config()
        raw.update(config_version=3)
        path=self.root/uuid4().hex
        with patch.object(RecordSessionCalculations,'_emit_event',cancel):
            with self.assertRaises(KeyboardInterrupt):
                AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(raw)),path)
        self.assertTrue(budgets)
        self.assertEqual(budgets[0].ram_bytes,0)
        self.assertFalse(path.exists())

    def test_sequence_three_raw_formats_and_clocks(self):
        """请求0秒、响应0.12秒；actual延迟0.12秒，固定/DBC延迟0.1秒。"""
        for (kind,path),mode,backend in product(self.fixtures().items(),('actual','fixed','dbc'),('reference','numpy')):
            def edit(raw):
                """使用同帧两信号形成请求响应。参数: 配置。返回: None。异常: 无。"""
                raw['calculations']=[]
                raw['rules']=[dict(name='ask',rule_type='rising_edge',condition='voltage > 350',emit_initial=True),
                              dict(name='reply',rule_type='rising_edge',condition='current >= 12')]
                raw['sequences']=[dict(name='pair',start='ask',response='reply',min_delay='0s',max_delay='0.2s')]
            with self.subTest(kind=kind,mode=mode,backend=backend):
                plan=self.plan(kind,path,mode,edit)
                with AnalysisRunner(backend).run(plan,self.root/uuid4().hex) as result:
                    row,=tuple(result.iter_sequences())
                    self.assertEqual(row.status,'matched')
                    self.assertAlmostEqual(row.decided_ns/1e9,.12,places=5)
                    self.assertAlmostEqual(row.delay_ns/1e9,.12 if mode=='actual' else .1,places=5)

    def test_threshold_three_raw_formats_and_clocks(self):
        """高电压全程报警：actual累计0.3秒，固定/DBC两个周期累计0.2秒。"""
        for (kind,path),mode in product(self.fixtures().items(),('actual','fixed','dbc')):
            def edit(raw):
                """只请求阈值预设，自带每事件时长和总累计。参数: raw。返回: None。异常: 无。"""
                raw['calculations']=[]
                raw['presets']=[dict(name='high',preset_type='threshold_excursion',version='1',
                    role_bindings=dict(signal='voltage'),parameters=dict(unit='V',enter_threshold=350,exit_threshold=300))]
            with self.subTest(kind=kind,mode=mode):
                with AnalysisRunner().run(self.plan(kind,path,mode,edit),self.root/uuid4().hex) as result:
                    summary,=result.metadata.threshold_durations
                    self.assertEqual(summary.status,'complete')
                    self.assertAlmostEqual(summary.value,.3 if mode=='actual' else .2,places=5)
                    calculation,=tuple(result.iter_calculations())
                    self.assertAlmostEqual(calculation.value,summary.value,places=5)
