"""手算实际截止与周期折算，验证时间统计不把过期区间算入权重。"""

from dataclasses import replace
from math import fsum
import random
import unittest
from unittest.mock import patch

from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.models import Interval
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.types import SignalDType as D, QualityFlag as Q
from chronaxis.core.time_reduction_reference import ReferenceTimeReduction
from chronaxis.core.time_reduction_numpy import NumpyTimeReduction
from chronaxis.core.conditional_time_reduction_reference import ReferenceConditionalTimeReduction
from chronaxis.core.conditional_time_reduction_numpy import NumpyConditionalTimeReduction
import test_time_reduction as fixtures


class RecordTimeDeadlineTests(unittest.TestCase):
    """同一手算真值分别检查两个后端、原始间隔和周期模式。"""

    series = fixtures.TimeReductionTests.series
    plain = (ReferenceTimeReduction, NumpyTimeReduction)
    conditional = (ReferenceConditionalTimeReduction, NumpyConditionalTimeReduction)

    def test_partial_interval_and_two_pass_mean(self):
        """窗口及有效期只缩短分子，不更改原记录对。参数: 无。返回: None。异常: 断言失败。"""
        series = self.series((4000, 1000, 9000), (0, 120_000_000, 300_000_000))
        spec = CalculationDefinition('mean', 'time_weighted_mean', Interval(60_000_000, 300_000_000))
        deadlines = (90_000_000, 210_000_000, None)
        for kernel in self.plain:
            for step in (None, 100_000_000):
                first = kernel(spec, 'W', D.FLOAT64, step_ns=step)
                facts = first.push(series, valid_until_ns=deadlines)
                self.assertEqual(facts.value_valid_duration_ns, 120_000_000)
                self.assertEqual(facts.value_unknown_ranges, (Interval(90_000_000, 120_000_000), Interval(210_000_000, 300_000_000)))
                self.assertTrue(facts.quality & Q.STALE)
                denominator = ({'selected_duration_ns': first.selected_duration_ns} if step is None
                               else {'selected_weight_seconds': first.selected_weight_seconds})
                second = kernel(spec, 'W', D.FLOAT64, step_ns=step, **denominator)
                compact = second.push(series, valid_until_ns=deadlines, retain_unknown_ranges=False)
                self.assertFalse(compact.ranges_retained)
                self.assertEqual(compact.value_unknown_ranges, ())
                self.assertAlmostEqual(second.finish().value, 1750.0 if step is None else 2000.0)

    def test_conditional_period_duration_and_independent_deadlines(self):
        """条件和值先后过期各自分类，主FALSE仍为有效零。参数: 无。返回: None。异常: 断言失败。"""
        series = self.series((True, False, True), (0, 120, 300), dtype=D.BOOL, unit='1')
        series = replace(series, conditions=(ScalarValue(True, D.BOOL),)*3)
        for kernel in self.conditional:
            state = kernel(CalculationDefinition('d', 'duration', Interval(60, 300)), '1', D.BOOL, step_ns=100)
            facts = state.push(series, valid_until_ns=(90, 250, None), condition_valid_until_ns=(100, 210, None))
            self.assertAlmostEqual(state.finish().value, 25e-9)
            self.assertEqual((facts.value_valid_duration_ns, facts.condition_known_duration_ns,
                              facts.selected_duration_ns, facts.selected_false_duration_ns,
                              facts.selected_value_unknown_duration_ns), (160, 130, 30, 90, 10))
            self.assertEqual(facts.condition_unknown_ranges, (Interval(100, 120), Interval(210, 300)))
            false = replace(series, conditions=(ScalarValue(False, D.BOOL),)*3)
            empty = kernel(CalculationDefinition('d', 'duration', series.observation), '1', D.BOOL, step_ns=100)
            f = empty.push(false, condition_valid_until_ns=(60, 200, None), retain_unknown_ranges=False)
            self.assertEqual(f.false_duration_ns, 140)
            self.assertEqual(f.selected_duration_ns, 0)
            self.assertIsNone(empty.finish().value)  # 外层根据已知覆盖分类，不在核中冒充完整零。

    def test_randomized_condition_mean_and_chunking(self):
        """标准库直接累加手工权重；两遍不同切块不改变结果。参数: 无。返回: None。异常: 断言失败。"""
        rng = random.Random(20261024)
        for _ in range(12):
            times = [0]
            for i in range(15):
                times.append(times[-1] + rng.randrange(1, 80))
            values = tuple(rng.choice((None, -400, 0, 50, 900)) for t in times)
            truth = tuple(rng.choice((True, False, None)) for t in times)
            deadlines = tuple(t + rng.randrange(0, 80) for t in times)
            cdeadlines = tuple(t + rng.randrange(0, 80) for t in times)
            series = replace(self.series(values, times), conditions=tuple(
                ScalarValue(None, D.BOOL, False, Q.MISSING) if v is None else ScalarValue(v, D.BOOL) for v in truth))
            spec = CalculationDefinition('mean', 'time_weighted_mean', Interval(5, times[-1]-2))
            for step in (None, 100):
                weights = []
                for i in range(len(times)-1):
                    dt = max(0, min(times[i+1], spec.window.end_ns, deadlines[i], cdeadlines[i])-max(times[i], 5))
                    if values[i] is not None and truth[i] is True and dt:
                        weights.append((values[i], dt if step is None else dt/(times[i+1]-times[i])*step/1e9))
                if not weights:
                    continue
                denominator = fsum(w for v, w in weights)
                expected = fsum(v*(w/denominator) for v, w in weights)
                for kernel in self.conditional:
                    first = kernel(spec, 'W', D.FLOAT64, step_ns=step)
                    first.push(series, valid_until_ns=deadlines, condition_valid_until_ns=cdeadlines)
                    options = ({'selected_duration_ns': first.selected_duration_ns} if step is None
                               else {'selected_weight_seconds': first.selected_weight_seconds})
                    second = kernel(spec, 'W', D.FLOAT64, step_ns=step, **options)
                    for i in range(len(times)-1):
                        section = slice(i, i+2)
                        block = replace(series, observation=Interval(times[i], times[i+1]), times_ns=series.times_ns[section],
                            values=series.values[section], conditions=series.conditions[section],
                            actual_value_updates=series.actual_value_updates[section], diagnostics=series.diagnostics[section])
                        second.push(block, valid_until_ns=deadlines[section], condition_valid_until_ns=cdeadlines[section], retain_unknown_ranges=False)
                    self.assertAlmostEqual(second.finish().value, expected, delta=1e-10)

    def test_expired_points_extrema_and_no_unused_ranges(self):
        """失效恰在更新时不计样本或极值；精简模式不构造未知Interval。参数: 无。返回: None。异常: 断言失败。"""
        series = self.series((2**63+1, 2**63+2, 0), (0, 100, 200), dtype=D.UINT64)
        for kernel in self.plain:
            state = kernel(CalculationDefinition('max', 'max_time', series.observation), 'W', D.UINT64, step_ns=100)
            with patch(kernel.__module__ + '.Interval', side_effect=AssertionError('不应构造未知区间')):
                facts = state.push(series, valid_until_ns=(0, 150, None), retain_unknown_ranges=False)
            self.assertEqual(state.finish().value, 2**63+2)
            self.assertEqual(facts.valid_sample_count, 1)
            self.assertEqual(facts.value_valid_duration_ns, 50)
            for bad in ((1,), [1, 2, 3], (True, None, None)):
                with self.assertRaises((TypeError, ValueError)):
                    state.push(series, valid_until_ns=bad)


if __name__ == '__main__':
    unittest.main()
