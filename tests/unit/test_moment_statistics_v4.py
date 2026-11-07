"""C2 的样本/时间方差、标准差和均方根手算验收。

小型固定输入经完整序列和公开 Runner 分别执行。另以极端浮点、整数精度、
跨块与不同实际权重检验数值和覆盖，临时文件只在项目 work 创建。
"""

from dataclasses import replace
from math import sqrt
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import json
import numpy as np
from chronaxis import AnalysisPlan, AnalysisRunner
from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.calculations_reference import compute_reference
from chronaxis.core.calculations_numpy import compute_numpy
from chronaxis.core.moments_reference import ReferenceMoments
from chronaxis.core.moments_numpy import NumpyMoments
from chronaxis.core.types import SignalDType as D, QualityFlag as Q
import test_sample_reduction as fixtures


class MomentStatisticsTests(unittest.TestCase):
    """两个后端分别对照手工真值；观察时长、真实样本数与数值结果独立检查。"""

    def test_unequal_weights_ddof_split_and_fixed(self):
        """参数: 无。返回: 无。异常: 样本分母、裁剪、固定周期或时间拆分权重不符。"""
        make = fixtures.SampleReductionTests().series
        for compute in (compute_reference, compute_numpy):
            for times, values, actual in (((0,1,4),(0.,10.,99.),(True,True,True)),
                                          ((0,1000,4000),(0.,10.,99.),(True,True,True)),
                                          ((0,1,2,4),(0.,10.,10.,99.),(True,True,False,True))):
                s = make(times, values, actual=actual)
                for op, ddof, expected in (('sample_variance',0,25.),('sample_variance',1,50.),
                        ('sample_stddev',1,sqrt(50)),('time_variance',0,18.75),('time_stddev',0,sqrt(18.75)),
                        ('sample_rms',None,sqrt(50)),('time_rms',None,sqrt(75))):
                    spec = CalculationDefinition('m', op, s.observation, config_version=4, ddof=ddof)
                    result = compute(s, spec)
                    self.assertAlmostEqual(result.value, expected)
                    self.assertEqual(result.valid_sample_count, 2)
            # 两条实际记录分别跨1和3ns，但每条明确代表同样的周期。
            s = make((0,1,4), (0.,10.,99.), (True,True,False))
            spec = CalculationDefinition('m','time_variance',s.observation,config_version=4)
            self.assertAlmostEqual(compute(s,spec,step_ns=1).value, 25.)

    def test_wide_ranges_centered_variance_and_stable_rms(self):
        """参数: 无。返回: 无。异常: 跨块大基数偏差被抵消、正常根溢出或实际超界无标记。"""
        maximum = float.fromhex('0x1.fffffffffffffp+1023')
        for factory in (ReferenceMoments, NumpyMoments):
            for splits in ((4,), (1,2,1)):
                data = [1e16+v for v in (0,2,4,6)]
                moments = factory('sample_variance')
                offset = 0
                for size in splits:
                    moments.push(np.array(data[offset:offset+size]))
                    offset += size
                value, quality = moments.finish(0,1)
                self.assertEqual(quality, Q.NONE)
                self.assertAlmostEqual(value,5.)
            for op in ('sample_variance','sample_stddev','sample_rms'):
                moments = factory(op)
                moments.push(np.array([-maximum, maximum]))
                value, quality = moments.finish(0,1)
                if op == 'sample_variance':
                    self.assertEqual((value,quality), (None,Q.NONFINITE))
                else:
                    self.assertEqual((value,quality), (maximum,Q.NONE))
            # 闭合到另一尺度后方差仍可表示，不能因原平方溢出提前失败。
            moments = factory('sample_variance')
            moments.push(np.array([-1e155,1e155]))
            value, quality = moments.finish(0,1e-6)
            self.assertEqual(quality, Q.NONE)
            self.assertAlmostEqual(value / 1e304,1.)

    def test_undefined_variance_precision_and_units(self):
        """参数: 无。返回: 无。异常: 单样本df、未知数据或温差量纲处理错误。"""
        make = fixtures.SampleReductionTests().series
        for compute in (compute_reference, compute_numpy):
            s = make((0,2),(7.,99.))
            spec = CalculationDefinition('m','sample_variance',s.observation,config_version=4,ddof=1)
            result = compute(s,spec)
            self.assertEqual((result.value,result.status,result.reason,result.valid_sample_count),
                             (None,'indeterminate','insufficient_samples',1))
            unknown = make((0,2),(None,99.))
            self.assertEqual(compute(unknown,spec).reason,'no_valid_selected_data')
            bad_int = make((0,2),((1<<53)+1,0),dtype=D.INT64)
            self.assertTrue(compute(bad_int,spec).quality & Q.PRECISION_LOSS)
            temp = make((0,1,2),(10.,30.,99.), unit='degC')
            for op, unit, expected in (('sample_stddev','delta_degC',10.),('time_variance','delta_K^2',100.)):
                s = CalculationDefinition('m',op,temp.observation,output_unit=unit,config_version=4)
                self.assertAlmostEqual(compute(temp,s).value,expected)
            with self.assertRaises(ValueError):
                compute(temp,replace(spec,operation='sample_rms',ddof=None))

    def config(self, backend):
        """给定后端建立同会话、活动与片段的统计请求。参数: 后端。返回: 字典。异常: 无。"""
        operations = ('sample_variance','sample_stddev','sample_rms','time_variance','time_stddev','time_rms')
        items = [dict(name=op,operation=op,expr='v') for op in operations]
        items += [dict(name='event_sample',operation='sample_variance',ddof=1,expr='v',scope={'rule':'active'}),
                  dict(name='constant_sample',operation='sample_rms',expr='1'),
                  dict(name='window_time',operation='time_variance',expr='v',scope={'window':'around'},condition='v>=0')]
        return dict(config_version=4,dataset=dict(name='demo',domain=dict(start='0s',end='4s')),
            sources=[dict(name='table',source_type='memory',rows=[dict(time=f'{t}s',values=dict(raw=x)) for
                    t,x in ((0,0.),(1,10.),(4,-1.))])],
            signals=[dict(name='v',field='raw',dtype='float64',unit='V',valid_for='10s')],
            rules=[dict(name='active',rule_type='condition_duration', duration_comparison='>=',condition='v>=0',minimum_duration='0s')],
            windows=[dict(name='around',rule='active',anchor='activity',pre='0s',post='0s',merge='none')],
            calculations=items,execution=dict(backend=backend,batch_rows=1))

    def test_public_session_event_segment_and_rejections(self):
        """参数: 无。返回: 无。异常: 公共范围、单位、版本或参数约束失效。"""
        for backend in ('reference','numpy'):
            raw = self.config(backend)
            plan = AnalysisPlan.from_dict(raw)
            with TemporaryDirectory(dir='work', prefix='moment-v4-') as folder:
                with AnalysisRunner().run(plan,work_dir=Path(folder)/'run') as result:
                    rows = {r.calculation_id:r for r in result.iter_calculations()}
                    for name, expected in (('sample_variance',25.),('sample_stddev',5.),('sample_rms',sqrt(50)),
                            ('time_variance',18.75),('time_stddev',sqrt(18.75)),('time_rms',sqrt(75)),
                            ('event_sample',50.),('window_time',18.75)):
                        self.assertAlmostEqual(rows[name].value,expected,msg=name)
                    self.assertEqual(rows['event_sample'].scope,'event')
                    self.assertEqual((rows['constant_sample'].value,rows['constant_sample'].reason),(None,'no_samples'))
                    self.assertEqual(rows['window_time'].scope,'segment')
            for op, ddof in (('sample_rms',0),('time_variance',1),('sample_variance',2),('sample_stddev',True)):
                raw['calculations'] = [dict(name='m',operation=op,expr='v',ddof=ddof)]
                with self.assertRaises(ValueError):
                    AnalysisPlan.from_dict(raw)
            raw['config_version'] = 3
            raw['calculations'] = [dict(name='m',operation='time_rms',expr='v')]
            with self.assertRaises(ValueError):
                AnalysisPlan.from_dict(raw)

    def test_resolved_defaults_roundtrip_preserves_ddof_and_output_scale(self):
        """参数: 无。返回: 无。异常: 显式化默认值后引入无关ddof或输出尺度错误。"""
        from chronaxis.configuration.resolution import resolved_configuration
        raw = self.config('reference')
        raw['calculations'] = [dict(name='v1',operation='sample_stddev',expr='v',unit='mV'),
                               dict(name='v2',operation='sample_variance',expr='v',unit='mV^2',ddof=1),
                               dict(name='r',operation='time_rms',expr='v')]
        with TemporaryDirectory(dir='work',prefix='moment-resolve-') as folder:
            path = Path(folder)/'plan.json'
            path.write_text(json.dumps(raw),encoding='utf-8')
            resolved = resolved_configuration(path,defaults=True)
            first, second, rms = resolved['calculations']
            self.assertEqual((first['ddof'],second['ddof']), (0,1))
            self.assertNotIn('ddof',rms)
            plan = AnalysisPlan.from_dict(resolved)
            with AnalysisRunner().run(plan,work_dir=Path(folder)/'run') as result:
                rows={row.calculation_id:row for row in result.iter_calculations()}
                self.assertEqual(rows['v1'].value,5000.)
                self.assertEqual(rows['v2'].value,50e6)

    def test_historical_blocks_agree_with_hand_weight_and_sample_count(self):
        """参数: 无。返回: 无。异常: 历史值/条件块接线导致分母或共享端点重复。"""
        from chronaxis.core.models import MemoryRow
        from chronaxis.core.binding import SignalDefinition
        from chronaxis.execution.historical_conditional_time_calculation import HistoricalConditionalTimeCalculation
        from chronaxis.execution.historical_sample_calculation import HistoricalSampleCalculation
        from test_window_replay import WindowReplayTests

        for backend in ('reference','numpy'):
            factory = WindowReplayTests()
            self.addCleanup(lambda f=factory:self.assertTrue(f.doCleanups()))
            f = factory.fixture(domain=(0,4),backend=backend,
                definitions=(SignalDefinition('a','table','raw.a',D.FLOAT64,'V',10,config_version=4),),
                rows_by_source={'table':tuple(MemoryRow(t,{'raw.a':v},i)
                                  for i,(t,v) in enumerate(((0,0.),(1,10.),(4,-1.))))},
                texts=('a','a>=0'))
            for typ, op, ddof, expected in ((HistoricalConditionalTimeCalculation,'time_variance',0,18.75),
                                            (HistoricalSampleCalculation,'sample_variance',1,50.)):
                spec = CalculationDefinition('m',op,f.domain,config_version=4,ddof=ddof)
                owner = typ(f.history,f.holds._context,f.lease.bindings,f.compiled[0],spec,f.compiled[1],
                            backend=backend,batch_intervals=1)
                self.addCleanup(owner.close)
                while owner.step():
                    pass
                self.assertAlmostEqual(owner.result.value,expected)
                self.assertEqual(owner.result.valid_sample_count,2)
                owner.close()

    def test_budget_and_cancellation_release_run_without_partial_result(self):
        """参数: 无。返回: 无。异常: 预算或取消错误未原样传播、留下暂存结果或RAM。"""
        from chronaxis.core.models import Interval
        from chronaxis.core.numeric import ScalarValue
        from chronaxis.execution.record_time_calculation import RecordTimeCalculation
        from chronaxis.results.budget import ResourceBudget
        from chronaxis.results.errors import BudgetExceededError
        spec = CalculationDefinition('m','sample_variance',Interval(0,4),config_version=4)
        budget = ResourceBudget(16*1024**2)
        owner = RecordTimeCalculation(budget,spec,'V',D.FLOAT64,None,backend='numpy',batch_intervals=1)
        self.addCleanup(owner.close)
        budget.memory_budget_bytes = budget.ram_bytes + 1024
        rows = ((0,ScalarValue(0.,D.FLOAT64),None),(4,ScalarValue(10.,D.FLOAT64),None))
        with self.assertRaises(BudgetExceededError):
            owner.consume(rows,actual_value_updates=(True,True))
        owner.close()
        self.assertEqual(budget.ram_bytes,0)
        with TemporaryDirectory(dir='work',prefix='moment-cancel-') as folder:
            destination=Path(folder)/'run'
            with patch.object(NumpyMoments,'push',side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
                AnalysisRunner().run(AnalysisPlan.from_dict(self.config('numpy')),work_dir=destination)
            self.assertFalse(destination.exists())

    def test_public_dbc_and_fixed_use_clipped_original_driver_pairs(self):
        """参数: 无。返回: 无。异常: 忽略TTL或以实际时长代替裁剪后的DBC/固定周期权重。"""
        from test_record_runner import RecordRunnerTests
        from configuration_fixtures import current_fixture
        from uuid import uuid4
        factory = RecordRunnerTests()
        factory.setUp()
        self.addCleanup(factory.doCleanups)
        path = factory.fixtures()['can_asc']

        def edit(raw):
            """限定请求窗和电流TTL。参数: 既有构造器中的配置。返回: 无。异常: 转换错误。"""
            raw['dataset']['domain']['start']='0.06s'
            raw['signals'][1]['valid_for']='0.15s'
            raw['calculations']=[dict(name='scatter',operation='time_variance',expr='power')]
            public=current_fixture(raw)
            raw.clear()
            raw.update(public,config_version=4)

        # 两个保持值4000W、4800W。实际覆盖0.06/0.15s；周期0.1s时
        # 两项分别权重0.1×0.06/0.12、0.1×0.15/0.18，对应比例3:5。
        for backend in ('reference','numpy'):
            for mode,expected in (('actual',640000*10/49),('fixed',150000.),('dbc',150000.)):
                plan = factory.plan('can_asc',path,mode,edit)
                with AnalysisRunner(backend).run(plan,work_dir=factory.root/uuid4().hex) as result:
                    row, = result.iter_calculations()
                    self.assertAlmostEqual(row.value,expected)
                    self.assertEqual(row.status,'partial')
