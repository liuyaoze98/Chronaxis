"""以独立手算验证真实驱动记录对的周期积分，不开放尚未接线的公共AnalysisRunner。"""

from dataclasses import replace
import unittest

from chronaxis.core.integral_terms_reference import compute_integral_terms_reference
from chronaxis.core.integral_terms_numpy import compute_integral_terms_numpy
from chronaxis.core.integral_sum_reference import ReferenceIntegralSum
from chronaxis.core.integral_sum_numpy import NumpyIntegralSum
from chronaxis.core.calculations import CalculationSeries, CalculationDefinition
from chronaxis.core.models import Interval
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.types import SignalDType as D, QualityFlag as Q
from chronaxis.timebase.conversion import INT64_MAX, TimeOverflowError


class RecordIntegralTermsTests(unittest.TestCase):
    """复用原面积及有界累计核，验证裁剪、无效覆盖、分块和数值异常。"""

    backends = ((compute_integral_terms_reference, ReferenceIntegralSum),
                (compute_integral_terms_numpy, NumpyIntegralSum))

    def series(self, times, values):
        """构造只有真实驱动点的功率列。参数: 时间和值。返回: CalculationSeries。异常: 模型错误。"""
        typed = tuple(ScalarValue(value, D.FLOAT64) if value is not None else
                      ScalarValue(None, D.FLOAT64, False, Q.MISSING) for value in values)
        return CalculationSeries(Interval(times[0], times[-1]), times, typed,
                            (True,) * len(times), 'W')

    def test_user_half_period_and_unit_conversion_once(self):
        """4000W半周期为200J，整周期400J；最终一次换Wh。参数: 无。返回: None。异常: 断言失败。"""
        series = self.series((10_000_000_000, 10_120_000_000), (4000.0, 4000.0))
        for compute, reducer in self.backends:
            for window, period, expected in (
                (Interval(10_060_000_000, 10_120_000_000), 100_000_000, 200.0),
                (series.observation, 100_000_000, 400.0),
                (Interval(10_060_000_000, 10_120_000_000), None, 240.0)):
                terms = compute(series, CalculationDefinition('energy', 'integral', window), step_ns=period)
                total = reducer()
                total.push(terms)
                self.assertAlmostEqual(total.finish('J').value, expected)
                self.assertAlmostEqual(total.finish('Wh', 1 / 3600).value, expected / 3600)
                # 实际窗口仍使用原时间；不把周期改写成时间坐标。
                self.assertEqual(terms.facts.actual_window, window)
                self.assertEqual(series.times_ns[-1], 10_120_000_000)

    def test_fractional_ns_and_large_timestamp_preserve_energy(self):
        """1ns周期的三分之一仍有面积，接近int64上界也不丢1ns。参数: 无。返回: None。异常: 断言失败。"""
        for origin in (0, INT64_MAX - 3):
            series = self.series((origin, origin + 3), (3e9, 3e9))
            spec = CalculationDefinition('energy', 'integral', Interval(origin + 1, origin + 2))
            for compute, reducer in self.backends:
                terms = compute(series, spec, step_ns=1)
                total = reducer()
                total.push(terms)
                self.assertAlmostEqual(total.finish('J').value, 1.0, places=14)

    def test_invalid_replaces_value_and_chunk_size_does_not_change_sum(self):
        """无效前值不桥接；每块保留最后边界，周期不因分块重复。参数: 无。返回: None。异常: 断言失败。"""
        times = (0, 120_000_000, 300_000_000, 500_000_000, 600_000_000)
        values = (4000.0, None, -2000.0, 0.0, 9000.0)
        spec = CalculationDefinition('energy', 'integral', Interval(60_000_000, 550_000_000))
        for compute, reducer in self.backends:
            for size in (1, 2, 4):
                total = reducer()
                for index in range(0, len(times) - 1, size):
                    end = min(index + size + 1, len(times))
                    terms = compute(self.series(times[index:end], values[index:end]), spec, step_ns=100_000_000)
                    total.push(terms)
                # +200，未知，-200，0；末点不加一次900J。
                result = total.finish('J')
                self.assertAlmostEqual(result.value, 0.0)
                self.assertEqual(result.valid_term_count, 3)
                self.assertFalse(result.calculation_failed)

    def test_no_tail_no_overlap_and_unknown_are_not_valid_zero(self):
        """单点、无交集、全无效都没有有效面积；有效零仍有一项。参数: 无。返回: None。异常: 断言失败。"""
        for compute, reducer in self.backends:
            for series, window in (
                (self.series((0,), (4000.0,)), Interval(0, 10)),
                (self.series((0, 10), (4000.0, 4000.0)), Interval(10, 20)),
                (self.series((0, 10), (None, 4000.0)), Interval(0, 10))):
                terms = compute(series, CalculationDefinition('energy', 'integral', window), step_ns=100)
                total = reducer()
                total.push(terms)
                self.assertIsNone(total.finish('J').value)
                self.assertEqual(total.valid_term_count, 0)
            terms = compute(self.series((0, 10), (0.0, None)),
                            CalculationDefinition('energy', 'integral', Interval(0, 10)), step_ns=100)
            self.assertEqual(tuple(terms.valid), (True,))

    def test_actual_expiry_clips_period_without_rewriting_denominator(self):
        """0.18秒记录对在0.15秒失效：固定0.1秒只取5/6，实际模式取0.15秒。"""
        series = self.series((0, 180_000_000), (4000., 4000.))
        for compute, reducer in self.backends:
            for period, expected in ((100_000_000, 400. * 5 / 6), (None, 600.)):
                terms = compute(series, CalculationDefinition('energy', 'integral', series.observation),
                                step_ns=period, valid_until_ns=(150_000_000, 150_000_000))
                total = reducer()
                total.push(terms)
                self.assertAlmostEqual(total.finish('J').value, expected)
                self.assertEqual(terms.facts.value_valid_duration_ns, 150_000_000)
                self.assertEqual(terms.facts.value_unknown_ranges, (Interval(150_000_000, 180_000_000),))
                self.assertTrue(terms.facts.quality & Q.STALE)
                self.assertEqual(terms.facts.valid_sample_count, 1)

    def test_expiry_and_requested_window_intersections(self):
        """请求窗可位于过期前、跨过期点或全在过期后；未知范围不能越过请求。"""
        series = self.series((0, 180_000_000), (4000., 4000.))
        for compute, reducer in self.backends:
            for start, end, expected, valid_duration, unknown in (
                (0, 90_000_000, 200., 90_000_000, ()),
                (120_000_000, 180_000_000, 400. / 6, 30_000_000, (Interval(150_000_000, 180_000_000),)),
                (150_000_000, 180_000_000, None, 0, (Interval(150_000_000, 180_000_000),))):
                terms = compute(series, CalculationDefinition('energy', 'integral', Interval(start, end)),
                    step_ns=100_000_000, valid_until_ns=(150_000_000, None))
                total = reducer()
                total.push(terms)
                if expected is None:
                    self.assertIsNone(total.finish('J').value)
                else:
                    self.assertAlmostEqual(total.finish('J').value, expected)
                self.assertEqual(terms.facts.value_valid_duration_ns, valid_duration)
                self.assertEqual(terms.facts.value_unknown_ranges, unknown)

    def test_expiry_at_sample_and_optional_detail(self):
        """到截止即无效；后续新值有新截止；关闭明细仍保同值/质量/有效时长。"""
        series = self.series((0, 100, 200, 300), (4000., 4000., 2000., 2000.))
        for compute, reducer in self.backends:
            outputs = []
            for retain in (True, False):
                terms = compute(series, CalculationDefinition('energy', 'integral', series.observation),
                    step_ns=100_000_000, valid_until_ns=(100, 100, 300, 300), retain_unknown_ranges=retain)
                total = reducer()
                total.push(terms)
                self.assertEqual(total.finish('J').value, 600.)
                self.assertEqual(terms.facts.valid_sample_count, 2)
                self.assertEqual(terms.facts.value_unknown_ranges, (Interval(100, 200),) if retain else ())
                outputs.append((terms.facts.value_valid_duration_ns, terms.facts.quality))
            self.assertEqual(outputs[0], outputs[1])

    def test_bad_expiry_rejected(self):
        """拒绝错误截止长度、bool及溢出，未提供截止保留原路径。"""
        series = self.series((0, 100), (4000., 4000.))
        spec = CalculationDefinition('energy', 'integral', series.observation)
        for compute, _ in self.backends:
            for deadlines in ((0,), [None, None], (True, None), (INT64_MAX + 1, None)):
                with self.assertRaises((TypeError, ValueError)):
                    compute(series, spec, step_ns=100, valid_until_ns=deadlines)
            original = compute(series, spec, step_ns=100)
            optional = compute(series, spec, step_ns=100, valid_until_ns=(None, None))
            self.assertEqual(tuple(original.areas), tuple(optional.areas))
            self.assertEqual(original.facts, optional.facts)

    def test_numeric_overflow_and_underflow_remain_invalid(self):
        """周期乘积溢出/下溢沿既有质量规则，不作为正常零。参数: 无。返回: None。异常: 断言失败。"""
        for value, period, flag in ((1e308, 10_000_000_000, Q.NONFINITE),
                                    (5e-324, 1, Q.PRECISION_LOSS)):
            for compute, _ in self.backends:
                series = self.series((0, 1_000_000_000), (value, value))
                terms = compute(series, CalculationDefinition('energy', 'integral', series.observation), step_ns=period)
                self.assertEqual(tuple(terms.valid), (False,))
                self.assertTrue(terms.facts.quality & flag)

    def test_period_and_synthetic_boundary_rejected_before_computation(self):
        """静态周期非法或将TTL/EOF点冒充驱动记录时失败；actual原路径保持。参数: 无。返回: None。异常: 断言失败。"""
        series = self.series((0, 10), (4000.0, 4000.0))
        spec = CalculationDefinition('energy', 'integral', series.observation)
        for compute, _ in self.backends:
            for period, error in ((True, TypeError), (1.5, TypeError), (0, ValueError),
                                   (-1, ValueError), (INT64_MAX + 1, TimeOverflowError)):
                with self.assertRaises(error):
                    compute(series, spec, step_ns=period)
            for flags in ((False, True), (True, False)):
                synthetic = replace(series, actual_value_updates=flags)
                with self.assertRaisesRegex(ValueError, '合成边界'):
                    compute(synthetic, spec, step_ns=100)
                self.assertTrue(tuple(compute(synthetic, spec).valid)[0])


if __name__ == '__main__':
    unittest.main()
