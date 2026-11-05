"""用三个独立来源手算 where 的选取、样本均值、时间均值和边沿证据。

输入是合成的开关和两路功率；两个后端分别经过完整内存与公开 Runner。
未选信号刷新、缺值，以及仅刷新开关，均不能改变样本的权重。
"""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from chronaxis import AnalysisPlan, AnalysisRunner
from chronaxis.core import MemoryRow, SessionSpec, SignalBindings, SignalDefinition, SignalDType as D, SourceSpec, TimebaseSpec, TimeType
from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.calculations_memory_numpy import build_calculation_series_numpy
from chronaxis.core.calculations_memory_reference import build_calculation_series_reference
from chronaxis.core.expression import compile_expression
from chronaxis.core.models import Interval
from chronaxis.core.temporal import TemporalRule
from chronaxis.core.temporal_memory_numpy import build_timeline_numpy
from chronaxis.core.temporal_memory_reference import build_timeline_reference


SIGNALS = (
    ('gate', D.BOOL, '1', ((0, True), (1, True), (3, False), (4, False), (5, True), (6, True))),
    ('left', D.FLOAT64, 'W', ((0, 10.), (2, 20.), (4, 99.), (6, 100.))),
    ('right', D.FLOAT64, 'W', ((0, None), (1, 40.), (2, 45.), (4, 30.), (6, 25.))),
)
EXPR = 'where(gate, left, right)'


class WhereAcceptanceTests(unittest.TestCase):
    """验证同一已选功率在直接计算与由配置启动时保持相同的采样规则。"""

    def test_memory_actual_flags_and_rule_evidence(self):
        """即使未选列缺失或刷新，仍只在选中列更新或条件换边时采样。

        参数: 无。返回: None。异常: 两种后端的值、质量或更新证据与手算不同时断言失败。
        """
        clock = TimebaseSpec('clock', TimeType.RELATIVE, 'same')
        sources, signals = [], []
        for name, dtype, unit, records in SIGNALS:
            sources.append(SourceSpec(name, clock, tuple(MemoryRow(t, {'raw':v}, i) for i,(t,v) in enumerate(records)),
                                      observation_start_ns=0, observation_end_ns=6))
            signals.append(SignalDefinition(name, name, 'raw', dtype, unit, 20, config_version=4))
        bindings = SignalBindings(SessionSpec('session', clock, 0, 6, tuple(sources)), tuple(signals))
        compiled = compile_expression(EXPR, bindings)
        condition = compile_expression(EXPR + ' > 0', bindings)
        spec = CalculationDefinition('mean', 'sample_mean', Interval(0,6), config_version=4)
        rule = TemporalRule('rule', 'dataset', 'session', 'rising_edge')
        for builder, timeline in ((build_calculation_series_reference,build_timeline_reference),
                                  (build_calculation_series_numpy,build_timeline_numpy)):
            with self.subTest(backend=builder.__name__):
                series = builder(compiled,spec)
                active = [(t, value.value) for t, value, flag in zip(series.times_ns, series.values, series.actual_value_updates)
                          if t < 6 and flag and value.valid]
                self.assertEqual(active, [(0,10.),(2,20.),(3,45.),(4,30.),(5,99.)])
                ticks = timeline(condition, rule).ticks
                self.assertEqual([t.time_ns for t in ticks if t.actual_update and t.time_ns < 6],[0,2,3,4,5])
                self.assertFalse(any(t.diagnostic_quality for t in ticks if t.time_ns < 6))

    def test_refresh_at_expiry_is_not_a_new_numeric_sample(self):
        """条件在刚到期的一刻续上不计样本，条件中间确实过期后恢复才计样本。

        参数: 无。返回: None。异常: 1ns的准时刷新或3ns的恢复采样不符合预期时断言失败。
        """
        clock = TimebaseSpec('clock', TimeType.RELATIVE, 'same')
        source = SourceSpec('switches', clock, tuple(MemoryRow(t, {'raw':True}, i) for i,t in enumerate((0,1,3))),
                            observation_start_ns=0, observation_end_ns=5)
        signals = (SignalDefinition('gate','switches','raw',D.BOOL,'1',1,config_version=4),)
        bound = SignalBindings(SessionSpec('session',clock,0,5,(source,)), signals)
        compiled = compile_expression('where(gate,10,20)',bound)
        spec = CalculationDefinition('mean','sample_mean',Interval(0,5),config_version=4)
        for build in (build_calculation_series_reference,build_calculation_series_numpy):
            series = build(compiled,spec)
            self.assertEqual([t for t, value, flag in zip(series.times_ns,series.values,series.actual_value_updates)
                              if flag and value.valid],[0,3])

    def test_public_sample_select_and_integral(self):
        """真实分支更新的均值是40.8W，按保持时长积分是214J。

        参数: 无。返回: None。异常: 计划、执行、明细时间或计算结果不符使测试失败。
        """
        for backend in ('reference','numpy'):
            sources, signals = [], []
            for name, dtype, unit, records in SIGNALS:
                sources.append(dict(name=name,source_type='memory',time=dict(clock='same'),
                                    rows=[dict(time=f'{t}s',values={'raw':v}) for t,v in records]))
                signals.append(dict(name=name,source=name,field='raw',dtype=dtype.value,unit=unit,valid_for='20s'))
            raw = dict(config_version=4,dataset=dict(name='selection',domain=dict(start='0s',end='6s')),
                       sources=sources,signals=signals,
                       calculations=[dict(name=name,operation=op,expr=EXPR) for name,op in
                                     (('mean','sample_mean'),('energy','integral'),('selected','select'))])
            with self.subTest(backend=backend), TemporaryDirectory(dir='work') as directory:
                with AnalysisRunner(backend).run(AnalysisPlan.from_dict(raw), Path(directory)/'run') as result:
                    stats = {row.calculation_id:row for row in result.iter_calculations()}
                    self.assertAlmostEqual(stats['mean'].value, 40.8)
                    self.assertAlmostEqual(stats['energy'].value, 214.)
                    self.assertTrue(all(row.status == 'complete' for row in stats.values()))
                    rows = list(result.iter_selections())
                    self.assertEqual([(r.time_ns // 10**9,r.value) for r in rows],[(0,10.),(2,20.),(3,45.),(4,30.),(5,99.)])
