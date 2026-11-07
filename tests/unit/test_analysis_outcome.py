"""用具体条件游程核对轻量结果概况，不以执行完成代替有效结果。

合成内存输入经过公共Runner；只读最终元数据，断言未新增输入扫描或逐条轨迹。
原始CAN空匹配与纯消息累计另用既有合成ASC夹具验证。
"""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
import unittest

from chronaxis import AnalysisPlan, AnalysisRunner
from chronaxis.results.analysis_outcome import AnalysisOutcome, RuleOutcome


class AnalysisOutcomeTests(unittest.TestCase):
    """两数值后端共享可读原因；结果有缺口时仍保留已生成事件。"""

    def setUp(self):
        """参数: 无。返回: None。异常: 临时目录I/O失败。"""
        self.temp=TemporaryDirectory(prefix='chronaxis-outcome-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def config(self,values, *, rule_type='condition_duration', constant=False):
        """参数: (秒,值)序列、规则类别、是否无信号常量。返回: 最小公共配置。异常: 无。"""
        rule=dict(name='active',rule_type=rule_type,condition='True' if constant else 'power > 0')
        if rule_type=='condition_duration':
            rule.update(minimum_duration='2s',duration_comparison='>=')
        return dict(config_version=4,dataset=dict(name='sample',domain=dict(start='0s',end='4s')),
            sources=[dict(name='table',source_type='memory',rows=[dict(time=f'{time}s',
                values={} if constant else dict(raw=value)) for time,value in values])],
            signals=[] if constant else [dict(name='power',field='raw',dtype='float64',unit='W',valid_for='5s')],
            rules=[rule],calculations=[] if constant else [dict(name='energy',scope=dict(rule='active'),
                operation='integral',expr='power',unit='J')])

    def outcome(self,raw,backend='numpy'):
        """参数: 配置/后端。返回: 概况及指标tuple。异常: 运行错误；结果始终关闭。"""
        with AnalysisRunner(backend).run(AnalysisPlan.from_dict(raw),work_dir=self.root/uuid4().hex) as result:
            outcome=result.metadata.analysis_outcome
            self.assertEqual(outcome.to_dict(),result.run_manifest['run']['analysis_outcome'])
            rows=tuple(result.iter_calculations())
        return outcome,rows

    def test_where_unobserved_branch_affects_only_rules_that_select_it(self):
        """缺失分支在未选时不能把全程已知的FALSE报告为无观测。

        参数: 无。返回: None。异常: 未选空来源改变结果，或选择该来源后漏报未知。
        """
        clock = dict(time_type='relative', unit='s', clock='common')
        for backend in ('reference', 'numpy'):
            for last in (1., -1.):
                raw = self.config([(0, 1.), (2, last), (4, last)])
                raw.update(config_version=4, calculations=[])
                raw['sources'][0]['time'] = clock
                raw['sources'].append(dict(name='other', source_type='memory', rows=[], time=clock))
                raw['signals'][0]['source'] = 'table'
                raw['signals'].append(dict(name='unused', source='other', field='absent', unit='W',
                                           dtype='float64', valid_for='5s'))
                raw['rules'][0]['condition'] = 'where(power > 0, power, unused) < 0'
                outcome, _ = self.outcome(raw, backend)
                rule, = outcome.rules
                self.assertEqual(rule.event_count, 0)
                if last == 1.:
                    self.assertEqual((rule.status, rule.has_unknown), ('condition_not_met', False))
                else:
                    self.assertTrue(rule.has_unknown)
                    self.assertIn('unused', rule.unobserved_signals)

    def test_rule_reasons_and_calculation_counts(self):
        """参数: 无。返回: None。异常: 断言失败；未满足与未知分别说明。"""
        cases=[([], 'no_observation',0), ([(0,0),(4,0)],'condition_not_met',0),
               ([(0,10),(1,0),(4,0)],'duration_not_met',0),
               ([(0,None),(4,0)],'insufficient_data',0),
               ([(0,10),(4,0)],'events_found',1),
               ([(0,None),(1,10),(4,0)],'events_found',1)]
        for backend in ('reference','numpy'):
            for values,status,count in cases:
                with self.subTest(backend=backend,status=status,values=values):
                    outcome,rows=self.outcome(self.config(values),backend)
                    self.assertEqual((outcome.rules[0].status,outcome.rules[0].event_count),(status,count))
                    self.assertEqual(outcome.complete+outcome.partial+outcome.indeterminate,len(rows))
                    if values and values[0][1] is None:
                        self.assertTrue(outcome.rules[0].has_unknown)
                    if status=='events_found':self.assertGreater(rows[0].value,0)

    def test_edge_constant_and_disabled_optional_outputs(self):
        """参数: 无。返回: None。异常: 断言失败；常量空输入和边沿没有时长误报。"""
        raw=self.config([(0,1),(4,1)],rule_type='rising_edge')
        raw['calculations']=[]
        outcome,_=self.outcome(raw)
        self.assertEqual(outcome.rules[0].status,'no_event')
        outcome,_=self.outcome(self.config([],constant=True))
        self.assertEqual(outcome.rules[0].status,'no_observation')
        outcome,_=self.outcome(self.config([(0,1),(4,1)],constant=True))
        self.assertEqual(outcome.rules[0].event_count,1)
        raw=self.config([(0,10),(4,0)])
        raw['outputs']=dict(contributions='none')
        raw['diagnostics']=dict(trace=False,integrity=False)
        outcome,rows=self.outcome(raw)
        self.assertEqual((outcome.complete,len(rows)),(1,1))

    def test_empty_session_calculation_has_no_observation(self):
        """参数: 无。返回: None。异常: 断言失败；没有事件也没有有效零能量。"""
        raw=self.config([])
        raw['dataset'].pop('domain')
        raw['rules']=[]
        raw['calculations'][0]['scope']='session'
        outcome,rows=self.outcome(raw)
        self.assertEqual((outcome.indeterminate,outcome.no_observation),(1,1))
        self.assertIsNone(rows[0].value)

    def test_model_rejects_false_success(self):
        """参数: 无。返回: None。异常: 断言失败；不允许事件计数与成功状态矛盾。"""
        with self.assertRaises(ValueError):RuleOutcome('rule','events_found',0,False)
        with self.assertRaises(ValueError):AnalysisOutcome(no_observation=1)


class RawAnalysisOutcomeTests(unittest.TestCase):
    """真实ASC匹配/空匹配与纯消息累计不依赖额外状态或二次扫描。"""
    from test_record_legacy_runner import RecordLegacyRunnerTests as _Fixture
    setUp=_Fixture.setUp
    asc=_Fixture.asc
    csv=_Fixture.csv
    blf=_Fixture.blf
    fixtures=_Fixture.fixtures
    plan=_Fixture.plan

    def test_unobserved_channel_and_pure_message_counts(self):
        """参数: 无。返回: None。异常: I/O或断言失败；通道错误不称作条件未成立。"""
        from configuration_fixtures import current_fixture
        path=self.fixtures()['can_asc']
        raw=self.plan('can_asc',path,False)
        with AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex) as result:
            outcome=result.metadata.analysis_outcome
            self.assertEqual((outcome.rules,outcome.complete,outcome.indeterminate),((),2,0))
        unmatched=deepcopy(raw)
        unmatched['sources'][0]['dbc_by_channel']={'2':str(self.dbc)}
        unmatched['signals'][0]['field']['channel']=2
        for item in unmatched['message_calculations']:
            item['update_message']['channel']=2
        with AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(unmatched)),self.root/uuid4().hex) as result:
            outcome=result.metadata.analysis_outcome
            self.assertEqual((outcome.indeterminate,outcome.no_observation),(2,2))
        raw.pop('message_calculations')
        raw['sources'][0]['dbc_by_channel']={'2':str(self.dbc)}
        raw['signals'][0]['field']['channel']=2
        raw['rules']=[dict(name='active',rule_type='condition_duration', duration_comparison='>=',condition='power > 0',minimum_duration='0.1s')]
        raw['calculations']=[dict(name='area',scope=dict(rule='active'),operation='integral',expr='power',unit='J')]
        with AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex) as result:
            outcome=result.metadata.analysis_outcome
            self.assertEqual(outcome.rules[0].status,'no_observation')
            self.assertEqual(outcome.rules[0].unobserved_signals,('power',))
            self.assertEqual(tuple(result.iter_events()),())
