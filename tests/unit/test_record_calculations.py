"""手算周期积分、加权均值和条件时长，核对两后端及原实际间隔语义。"""

from dataclasses import replace
import unittest

from chronaxis.core.calculations import CalculationSeries, CalculationDefinition
from chronaxis.core.calculations_reference import compute_reference
from chronaxis.core.calculations_numpy import compute_numpy
from chronaxis.core.models import Interval
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.types import SignalDType as D, QualityFlag as Q


class RecordCalculationTests(unittest.TestCase):
    """只测试有限真实驱动列；公共执行/TTL混合时间轴另行接线。"""

    backends = (staticmethod(compute_reference), staticmethod(compute_numpy))

    def series(self, values=(4000.0, 1000.0, 9000.0), *, conditions=None, dtype=D.FLOAT64, unit='W'):
        """构造不等实际间隔的驱动点。参数: 值/条件/类型/单位。返回: CalculationSeries。异常: 模型错误。"""
        times = (0, 120_000_000, 300_000_000)
        typed = tuple(ScalarValue(v, dtype) if v is not None else ScalarValue(None, dtype, False, Q.MISSING) for v in values)
        condition_values = None if conditions is None else tuple(
            ScalarValue(v, D.BOOL) if v is not None else ScalarValue(None, D.BOOL, False, Q.MISSING) for v in conditions)
        return CalculationSeries(Interval(0, times[-1]), times, typed, (True,) * 3, unit, condition_values)

    def test_weighted_mean_and_energy_use_same_clipped_periods(self):
        """权重50/100ms得到300J和2000W；actual为420J和1750W。参数: 无。返回: None。异常: 断言失败。"""
        series = self.series()
        for compute in self.backends:
            for operation, fixed, actual in (('integral', 300.0, 420.0), ('time_weighted_mean', 2000.0, 1750.0),
                                       ('min_time', 1000.0, 1000.0), ('max_time', 4000.0, 4000.0)):
                spec = CalculationDefinition('statistic', operation, Interval(60_000_000, 300_000_000))
                result = compute(series, spec, step_ns=100_000_000)
                self.assertAlmostEqual(result.value, fixed)
                self.assertAlmostEqual(compute(series, spec).value, actual)
                self.assertEqual(result.actual_window, spec.window)
                self.assertEqual(result.status, 'complete')

    def test_duration_counts_true_only_and_can_exceed_actual_span(self):
        """BOOL FALSE已知不累计，所选周期不受实际跨度大小限制。参数: 无。返回: None。异常: 断言失败。"""
        spec = CalculationDefinition('duration', 'duration', Interval(60_000_000, 300_000_000))
        for compute in self.backends:
            for values, expected in (((True, True, False), 0.15), ((True, False, True), 0.05),
                                      ((False, False, True), 0.0), ((None, None, True), None)):
                series = self.series(values, dtype=D.BOOL, unit='1')
                result = compute(series, spec, step_ns=100_000_000)
                if expected is None:
                    self.assertIsNone(result.value)
                else:
                    self.assertAlmostEqual(result.value, expected)
            series = self.series((True, True, True), dtype=D.BOOL, unit='1')
            self.assertEqual(compute(series, spec, step_ns=1_000_000_000).value, 1.5)

    def test_conditions_unknown_and_strict_preserve_existing_policy(self):
        """条件FALSE排除、UNKNOWN保持部分结果，strict不给未知部分补零。参数: 无。返回: None。异常: 断言失败。"""
        spec = CalculationDefinition('energy', 'integral', Interval(60_000_000, 300_000_000))
        for compute in self.backends:
            for second in (False, None):
                series = self.series(conditions=(True, second, True))
                result = compute(series, spec, step_ns=100_000_000)
                self.assertAlmostEqual(result.value, 200.0)
                strict = compute(series, replace(spec, partial_policy='strict'), step_ns=100_000_000)
                if second is None:
                    self.assertEqual(result.status, 'partial')
                    self.assertIsNone(strict.value)
                else:
                    self.assertEqual(result.status, 'complete')
                    self.assertAlmostEqual(strict.value, 200.0)
            self.assertEqual(compute(self.series(conditions=(False, False, True)), spec,
                                     step_ns=100_000_000).value, 0)

    def test_mean_normalizes_before_multiplication(self):
        """大有限均值不先乘周期产生溢出，缺值不进入分母。参数: 无。返回: None。异常: 断言失败。"""
        spec = CalculationDefinition('average', 'time_weighted_mean', Interval(0, 300_000_000))
        for compute in self.backends:
            result = compute(self.series((1e308, 1e308, 1e308)), spec, step_ns=10_000_000_000)
            self.assertEqual(result.value, 1e308)
            result = compute(self.series((4000.0, None, 9000.0)), spec, step_ns=100_000_000)
            self.assertEqual(result.value, 4000.0)
            self.assertEqual(result.status, 'partial')

    def test_no_tail_and_no_period_for_sample_statistics(self):
        """末点不补周期，样本均值不接受时间周期，合成边界必须先正确处理。参数: 无。返回: None。异常: 断言失败。"""
        series = self.series()
        for compute in self.backends:
            result = compute(series, CalculationDefinition('energy', 'integral', Interval(300_000_000, 400_000_000)), step_ns=100_000_000)
            self.assertIsNone(result.value)
            with self.assertRaisesRegex(ValueError, '样本统计'):
                compute(series, CalculationDefinition('average', 'sample_mean', series.observation), step_ns=100_000_000)
            with self.assertRaisesRegex(ValueError, '合成边界'):
                compute(replace(series, actual_value_updates=(True, False, True)),
                        CalculationDefinition('energy', 'integral', series.observation), step_ns=100_000_000)


if __name__ == '__main__':
    unittest.main()
