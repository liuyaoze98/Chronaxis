"""常量统计只依赖真实观测，不解析不需要的值；独立手算覆盖空/多源/裁剪。"""

from configuration_fixtures import current_fixture
from itertools import product
from uuid import uuid4
import unittest
from unittest.mock import patch
from chronaxis import AnalysisPlan,AnalysisRunner,validate_analysis_plan
import test_record_sources as source_cases
import test_record_runner as raw_cases


class RecordConstantTests(unittest.TestCase):
    """验证公开输入而非给常量补造信号。"""
    setUp=source_cases.RecordSourcesTests.setUp
    config=source_cases.RecordSourcesTests.config

    def constant(self,kind='memory'):
        """构造只有常量的三种消费者。参数: 来源形式。返回: 配置。异常: IO错。"""
        raw=self.config(kind,mode='actual')
        raw['calculations']=[dict(name='elapsed',scope='session',operation='duration',condition='True'),
                        dict(name='never',scope='session',operation='duration',condition='False')]
        raw['rules']=[dict(name='alarm',rule_type='condition_duration', duration_comparison='>=',condition='True',minimum_duration='0.2s')]
        return raw

    def test_parsed_constant_and_mixed_actual_scope(self):
        """常量0.3s/有效零；裁剪0.06起得0.24s。混合信号同次读取、不影响常量。"""
        for kind,backend,mixed,clip in product(('memory','signal_csv'),('reference','numpy'),(False,True),(False,True)):
            raw=self.constant(kind)
            if mixed:
                raw['calculations'].append(dict(name='energy',scope='session',operation='integral',expr='power',unit='J'))
            if clip:
                raw['dataset']['domain']['start']='0.06s'
            with self.subTest(kind=kind,backend=backend,mixed=mixed,clip=clip):
                plan=AnalysisPlan.from_dict(current_fixture(raw))
                self.assertTrue(validate_analysis_plan(plan).execution_ready)
                with AnalysisRunner(backend).run(plan,self.root/uuid4().hex) as result:
                    calculations={row.calculation_id:row for row in result.iter_calculations()}
                    self.assertAlmostEqual(calculations['elapsed'].value,.24 if clip else .3)
                    self.assertEqual(calculations['never'].value,0.)
                    alarm,=tuple(result.iter_events())
                    self.assertEqual((alarm.start_ns,alarm.confirmed_ns,alarm.end_ns),
                        (60000000,260000000,300000000) if clip else (0,200000000,300000000))

    def test_empty_and_single_do_not_invent_span(self):
        """空输入无事件无统计；单条没有相邻区间，不延长到domain末尾。"""
        for count,backend in product((0,1),('reference','numpy')):
            raw=self.constant()
            for source in raw['sources']:
                source['rows']=source['rows'][:count]
            with AnalysisRunner(backend).run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex) as result:
                self.assertEqual(tuple(result.iter_events()),())
                self.assertTrue(all(row.value is None for row in result.iter_calculations()))

    def test_constant_values_are_not_parsed(self):
        """所有信号均无关：坏数值不会解析，也不装箱或建历史。"""
        for kind in ('memory','signal_csv'):
            raw=self.constant(kind)
            if kind=='memory':
                for source in raw['sources']:
                    for row in source['rows']:
                        row['values']['raw']='unneeded'
            else:
                from pathlib import Path
                for source in raw['sources']:
                    Path(source['path']).write_text('time,raw\n0,unneeded\n300000000,bad\n',encoding='utf-8')
            with patch('chronaxis.sources.packing._pack_numeric_columns',side_effect=AssertionError('unneeded values')):
                with AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex) as result:
                    self.assertAlmostEqual(next(result.iter_calculations()).value,.3)


    def test_constant_sequence_uses_input_scope(self):
        """常量不伪造实际更新边沿；常量False响应仍提供已知未响应区间。"""
        for backend,constant_request in product(('reference','numpy'),(True,False)):
            raw=self.constant()
            raw['rules']=[dict(name='ask',rule_type='rising_edge',condition='True' if constant_request else 'current > 0',emit_initial=True),
                          dict(name='reply',rule_type='rising_edge',condition='current > 11' if constant_request else 'False')]
            raw['sequences']=[dict(name='pair',start='ask',response='reply',min_delay='0s',max_delay='0.2s')]
            with AnalysisRunner(backend).run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex) as result:
                pairs=tuple(result.iter_sequences())
                if constant_request:
                    self.assertEqual(pairs,())
                else:
                    pair,=pairs
                    self.assertEqual((pair.decided_ns,pair.status),(200000000,'no_response'))

    def test_failure_and_cancellation_no_prefix_or_budget_left(self):
        """首末可用不代表文件通过：坏尾行或结果写入取消必须全清理。"""
        from pathlib import Path
        from chronaxis.results import AnalysisError
        from chronaxis.results.spool import ResultSpool
        raw=self.constant('signal_csv')
        Path(raw['sources'][0]['path']).write_text('time,raw\n0,x\nbad,y\n',encoding='utf-8')
        root=self.root/uuid4().hex
        with self.assertRaises(AnalysisError):
            AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(raw)),root)
        self.assertFalse(root.exists())
        budgets=[]
        original=ResultSpool.append
        def cancel(owner,row):
            """真实写入后取消。参数: 仓/行。返回: 无。异常: KeyboardInterrupt。"""
            original(owner,row)
            budgets.append(owner.budget)
            raise KeyboardInterrupt('constant cancellation')
        raw=self.constant()
        root=self.root/uuid4().hex
        with patch.object(ResultSpool,'append',cancel),self.assertRaises(KeyboardInterrupt):
            AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(raw)),root)
        self.assertTrue(budgets)
        self.assertEqual(budgets[0].ram_bytes,0)
        self.assertFalse(root.exists())


class RawConstantTests(unittest.TestCase):
    """原始三格式只观察实际时间，无目标值解码。"""
    setUp=raw_cases.RecordRunnerTests.setUp
    asc=raw_cases.RecordRunnerTests.asc
    csv=raw_cases.RecordRunnerTests.csv
    blf=raw_cases.RecordRunnerTests.blf
    plan=raw_cases.RecordRunnerTests.plan
    fixtures=raw_cases.RecordRunnerTests.fixtures

    def test_three_formats_no_signal_values(self):
        """原始0到0.3秒支持常量，不因零投影丢掉真实观测。"""
        for (kind,path),backend in product(self.fixtures().items(),('reference','numpy')):
            def edit(raw):
                """只需要观测。参数: 配置。返回: None。异常: 无。"""
                raw['calculations']=[dict(name='elapsed',scope='session',operation='duration',condition='True')]
                raw['rules']=[dict(name='alarm',rule_type='condition_duration', duration_comparison='>=',condition='True',minimum_duration='0.2s')]
            with self.subTest(kind=kind,backend=backend),patch(
                    'chronaxis.execution.raw_signal_groups.pack_message_values',side_effect=AssertionError('unneeded values')):
                with AnalysisRunner(backend).run(self.plan(kind,path,'actual',edit),self.root/uuid4().hex) as result:
                    calculation,=tuple(result.iter_calculations())
                    self.assertAlmostEqual(calculation.value,.3,places=5)
                    alarm,=tuple(result.iter_events())
                    self.assertAlmostEqual(alarm.confirmed_ns/1e9,.2,places=5)
