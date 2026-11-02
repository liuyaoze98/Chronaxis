"""手算固定/DBC权重跨批累计，复用原时间归约；不保存或回读实际数据文件。"""

from dataclasses import replace
import unittest

from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.models import Interval
from chronaxis.core.types import SignalDType as D
from chronaxis.core.time_reduction_reference import ReferenceTimeReduction
from chronaxis.core.time_reduction_numpy import NumpyTimeReduction
import test_time_reduction as fixtures


class RecordTimeReductionTests(unittest.TestCase):
    """两遍均值与单遍时长分别检查，不以另一个后端结果作为真值。"""

    series = fixtures.TimeReductionTests.series
    chunks = fixtures.TimeReductionTests.chunks
    kernels = (ReferenceTimeReduction, NumpyTimeReduction)

    def test_mean_two_passes_and_different_chunk_sizes(self):
        """半周期4000和整周期1000给2000，前后两遍分块不同也一致。参数: 无。返回: None。异常: 断言失败。"""
        series = self.series((4000, 1000, 9000), (0, 120_000_000, 300_000_000))
        spec = CalculationDefinition('average', 'time_weighted_mean', Interval(60_000_000, 300_000_000))
        for kernel in self.kernels:
            first = kernel(spec, 'W', D.FLOAT64, step_ns=100_000_000)
            for chunk in self.chunks(series, 1):
                first.push(chunk)
            self.assertAlmostEqual(first.selected_weight_seconds, 0.15)
            with self.assertRaises(RuntimeError):
                first.finish()
            second = kernel(spec, 'W', D.FLOAT64, step_ns=100_000_000,
                            selected_weight_seconds=first.selected_weight_seconds)
            for chunk in self.chunks(series, 2):
                second.push(chunk)
            self.assertAlmostEqual(second.finish().value, 2000.0)

    def test_duration_fractional_ns_unknown_and_valid_zero(self):
        """三分之一ns不截断，未知不桥接，FALSE为零但有有效项。参数: 无。返回: None。异常: 断言失败。"""
        for kernel in self.kernels:
            for values, expected, terms in (((True, None, True, False), 1 / 3e9, 2),
                                            ((False, False, False, True), 0.0, 3),
                                            ((None, None, None, True), None, 0)):
                series = self.series(values, (0, 3, 9, 12), dtype=D.BOOL, unit='1')
                spec = CalculationDefinition('duration', 'duration', Interval(2, 10))
                for size in (1, 2, 3):
                    state = kernel(spec, '1', D.BOOL, step_ns=1)
                    for chunk in self.chunks(series, size):
                        state.push(chunk)
                    result = state.finish()
                    if expected is None:
                        self.assertIsNone(result.value)
                    else:
                        # 2—3ns与9—10ns各占一个周期的1/3，两段TRUE。
                        target = expected * 2 if values[0] is True else expected
                        self.assertAlmostEqual(result.value, target, delta=1e-24)
                    self.assertEqual(result.valid_term_count, terms)

    def test_unknown_mean_exclusion_large_values_and_exact_extrema(self):
        """缺值不入分母，大均值保持有限；极值不构造权重状态。参数: 无。返回: None。异常: 断言失败。"""
        for kernel in self.kernels:
            series = self.series((1e308, None, 1e308, 999), (0, 2, 5, 8))
            spec = CalculationDefinition('average', 'time_weighted_mean', series.observation)
            first = kernel(spec, 'W', D.FLOAT64, step_ns=10_000_000_000)
            for chunk in self.chunks(series, 1):
                first.push(chunk)
            self.assertEqual(first.selected_weight_seconds, 20.0)
            second = kernel(spec, 'W', D.FLOAT64, step_ns=10_000_000_000,
                            selected_weight_seconds=first.selected_weight_seconds)
            for chunk in self.chunks(series, 2):
                second.push(chunk)
            self.assertEqual(second.finish().value, 1e308)
            integers = self.series((2**63, 2**63 + 1, 0), dtype=D.UINT64)
            extreme = kernel(CalculationDefinition('highest', 'max_time', integers.observation), 'W', D.UINT64, step_ns=100)
            extreme.push(integers)
            self.assertEqual(extreme.finish().value, 2**63 + 1)
            self.assertIsNone(extreme.selected_weight_seconds)

    def test_wrong_denominator_and_synthetic_points_fail(self):
        """两遍权重不一致和把合成点当驱动必须失败。参数: 无。返回: None。异常: 断言失败。"""
        series = self.series((1, 2, 3), (0, 2, 5))
        spec = CalculationDefinition('average', 'time_weighted_mean', series.observation)
        for kernel in self.kernels:
            for kwargs in ({'step_ns': 1, 'selected_duration_ns': 5},
                           {'selected_weight_seconds': 1.0},
                           {'step_ns': 1, 'selected_weight_seconds': 0.0},
                           {'step_ns': 1, 'selected_weight_seconds': float('nan')},
                           {'step_ns': 1, 'selected_weight_seconds': True}):
                with self.assertRaises(ValueError):
                    kernel(spec, 'W', D.FLOAT64, **kwargs)
            wrong = kernel(spec, 'W', D.FLOAT64, step_ns=1, selected_weight_seconds=3e-9)
            wrong.push(series)
            with self.assertRaisesRegex(ValueError, '分母不同'):
                wrong.finish()
            state = kernel(spec, 'W', D.FLOAT64, step_ns=1)
            with self.assertRaisesRegex(ValueError, '合成边界'):
                state.push(replace(series, actual_value_updates=(True, False, True)))
            self.assertEqual(state.selected_weight_seconds, 0.0)


if __name__ == '__main__':
    unittest.main()
