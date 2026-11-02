"""用手算和原完整核核对有限时间归约及同后端浮点入口。

覆盖裁剪保持值、精确大整数、规范化权重、任意切块、未知和有效零。
数值真值独立于被测NumPy核；异常门槛不能改覆盖或伪装正常结果。
本专项只使用有限内存样例，不写历史目录、不测试生产预算或真实日志。
"""

# 固定手算与独立标准库真值，数组仅建立明确有限测试列。
from dataclasses import replace
from math import fsum
import random
import unittest
from unittest.mock import patch
import numpy as np
from chronaxis.core.calculations import CalculationDefinition, CalculationSeries
from chronaxis.core.calculations_reference import compute_reference
from chronaxis.core.calculations_numpy import compute_numpy
from chronaxis.core.models import Interval, SourceRef
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.types import SignalDType as D, QualityFlag as Q
from chronaxis.core.time_reduction import TimeCalculationFacts, TimeReductionResult
from chronaxis.core.time_reduction_reference import ReferenceTimeReduction
from chronaxis.core.time_reduction_numpy import NumpyTimeReduction
from chronaxis.core.integral_sum_reference import ReferenceIntegralSum
from chronaxis.core.integral_sum_numpy import NumpyIntegralSum
from chronaxis.core.integral_terms import IntegralFacts, ReferenceIntegralTerms
from chronaxis.core.integral_terms_numpy import NumpyIntegralTerms


class TimeReductionTests(unittest.TestCase):
    """逐后端独立检查候选数值、真实事实和非法输入，不借测试数量证明接线。"""

    def series(self, values, times=None, dtype=D.FLOAT64, unit='W', updates=None):
        """建立明确有限typed样例，None代表带MISSING原因的未知。

        参数: 原值/times/dtype/单位/真实更新列。返回: CalculationSeries。
        异常: 真实模型门槛传播；默认每相邻时间差1ns，末点不贡献区间。
        """
        times = tuple(range(len(values))) if times is None else tuple(times)
        rows = tuple(ScalarValue(None, dtype, False, Q.MISSING) if value is None else
                     ScalarValue(float(value) if dtype is D.FLOAT64 else value, dtype) for value in values)
        return CalculationSeries(Interval(times[0], times[-1]), times, rows,
                            (True,) * len(times) if updates is None else tuple(updates), unit,
                            binding_identity='time-test', source_refs=(SourceRef('session', 'memory', 'raw.value'),))

    def kernel(self, backend, spec, series, denominator=None, limit=4096):
        """创建指定独立核。参数: 后端/原配置/分母/容量。返回: 新核。异常: 配置错误。
        """
        return (ReferenceTimeReduction if backend == 'reference' else NumpyTimeReduction)(
            spec, series.unit, series.values[0].dtype, selected_duration_ns=denominator, partial_limit=limit)

    def chunks(self, series, size):
        """按正区间数切有限块，共享右端但不复制真实样本计数。

        参数: 完整测试样例和正size。返回: 有限CalculationSeries生成器。异常: 模型错误。
        """
        # 测试允许保存完整轴；生产接线由root以封存历史有限回读单独验证。
        for start in range(0, len(series.times_ns) - 1, size):
            end = min(start + size, len(series.times_ns) - 1)
            yield replace(series, observation=Interval(series.times_ns[start], series.times_ns[end]),
                          times_ns=series.times_ns[start:end + 1], values=series.values[start:end + 1],
                          actual_value_updates=series.actual_value_updates[start:end + 1], diagnostics=series.diagnostics[start:end + 1])

    def run_number(self, backend, spec, series, size=64):
        """按确认的两遍均值或单遍其他时间指标计算纯数值。

        参数: 后端、原spec、样例与块大小。返回: (数值结果,第一遍事实列表)。
        异常: 真实纯核门槛传播；全未知均值只返回无候选，不伪造正分母。
        """
        first = self.kernel(backend, spec, series)
        facts = [first.push(block) for block in self.chunks(series, size)]
        if spec.operation != 'time_weighted_mean':
            return first.finish(), facts
        denominator = first.selected_duration_ns
        if denominator == 0:
            return TimeReductionResult(None, spec.output_unit or series.unit, False, Q.NONE, 0), facts
        second = self.kernel(backend, spec, series, denominator)
        for block in self.chunks(series, size):
            second.push(block)
        return second.finish(), facts

    def test_time_extrema_clip_and_terminal(self):
        """极值包含裁剪左边界保持值，但右端真实点不增加贡献。参数: 无。返回: None。异常: 断言失败。"""
        series = self.series((5, 9, -2, 999), (0, 2, 5, 8))
        for backend in ('reference', 'numpy'):
            for operation, expected in (('min_time', -2.), ('max_time', 9.)):
                for size in (1, 2, 7):
                    result, facts = self.run_number(backend, CalculationDefinition('value', operation, Interval(1, 7)), series, size)
                    self.assertEqual(result.value, expected)
                    self.assertEqual(sum(item.value_valid_duration_ns for item in facts), 6)
                    self.assertEqual(sum(item.valid_sample_count for item in facts), 2)

    def test_extrema_preserve_large_integers(self):
        """原单位整数极值精确保留UINT64和INT64端点。参数: 无。返回: None。异常: 断言失败。"""
        for dtype, values, expected in ((D.UINT64, (2 ** 64 - 1, 2 ** 53 + 1, 0), 2 ** 64 - 1),
                                       (D.INT64, (-2 ** 63, 2 ** 63 - 1, 0), 2 ** 63 - 1)):
            series = self.series(values, dtype=dtype, unit='1')
            for backend in ('reference', 'numpy'):
                result, _ = self.run_number(backend, CalculationDefinition('value', 'max_time', Interval(0, 2)), series, 1)
                self.assertEqual(result.value, expected)
                self.assertIs(type(result.value), int)

    def test_mean_uses_global_duration(self):
        """不同块时长的均值使用全窗分母，10*1/4+30*3/4=25。参数: 无。返回: None。异常: 断言失败。"""
        series = self.series((10, 30, 999), (0, 1, 4))
        for backend in ('reference', 'numpy'):
            for size in (1, 2, 7):
                result, facts = self.run_number(backend, CalculationDefinition('mean', 'time_weighted_mean', Interval(0, 4)), series, size)
                self.assertEqual(result.value, 25.)
                self.assertEqual(sum(item.selected_duration_ns for item in facts), 4)

    def test_mean_normalization_avoids_area_overflow(self):
        """有效权重先规范化，1e308保持4秒均值仍为1e308。参数: 无。返回: None。异常: 断言失败。"""
        series = self.series((1e308, 1e308, 0), (0, 3_000_000_000, 4_000_000_000))
        for backend in ('reference', 'numpy'):
            result, facts = self.run_number(backend, CalculationDefinition('mean', 'time_weighted_mean', series.observation), series, 1)
            self.assertEqual(result.value, 1e308)
            self.assertFalse(result.calculation_failed)
            self.assertEqual(sum(item.value_valid_duration_ns for item in facts), 4_000_000_000)

    def test_mean_cancellation_preserves_small_term(self):
        """原序有界误差状态保留大数抵消后的1/3。参数: 无。返回: None。异常: 断言失败。"""
        series = self.series((1e16, 1, -1e16, 0))
        expected = fsum((1e16 / 3, 1 / 3, -1e16 / 3))
        for backend in ('reference', 'numpy'):
            for size in (1, 2, 7):
                result, _ = self.run_number(backend, CalculationDefinition('mean', 'time_weighted_mean', series.observation), series, size)
                self.assertEqual(result.value, expected)

    def test_mean_underflow_keeps_original_coverage(self):
        """非零加权项下溢使均值计算失败，2ns原有效覆盖保持。参数: 无。返回: None。异常: 断言失败。"""
        series = self.series((5e-324, 0, 0))
        for backend in ('reference', 'numpy'):
            result, facts = self.run_number(backend, CalculationDefinition('mean', 'time_weighted_mean', series.observation), series, 1)
            self.assertEqual((result.value, result.calculation_failed, result.quality), (None, True, Q.PRECISION_LOSS))
            self.assertEqual(sum(item.value_valid_duration_ns for item in facts), 2)
            self.assertTrue(all(item.quality == Q.NONE for item in facts))

    def test_mean_precision_gate_excludes_inexact_integer(self):
        """均值整数精度失败成为未知区间，极值仍保持原整数。参数: 无。返回: None。异常: 断言失败。"""
        series = self.series((2 ** 53 + 1, 2, 0), dtype=D.UINT64, unit='1')
        for backend in ('reference', 'numpy'):
            result, facts = self.run_number(backend, CalculationDefinition('mean', 'time_weighted_mean', series.observation), series, 1)
            self.assertEqual(result.value, 2.)
            self.assertEqual(sum(item.value_valid_duration_ns for item in facts), 1)
            self.assertTrue(facts[0].quality & Q.PRECISION_LOSS)
            self.assertEqual(facts[0].value_unknown_ranges, (Interval(0, 1),))

    def test_mean_first_pass_and_wrong_denominator_rejected(self):
        """第一遍禁输出，第二遍分母错误或权重超范围不能交付。参数: 无。返回: None。异常: 断言失败。"""
        series = self.series((1e308, 0), (0, 2))
        for backend in ('reference', 'numpy'):
            spec = CalculationDefinition('mean', 'time_weighted_mean', series.observation)
            first = self.kernel(backend, spec, series)
            first.push(series)
            with self.assertRaises(RuntimeError):
                first.finish()
            second = self.kernel(backend, spec, series, 1)
            second.push(series)
            with self.assertRaises(ValueError):
                second.finish()

    def test_duration_false_zero_true_and_unknown(self):
        """BOOL FALSE提供有效零，TRUE贡献时长，未知独立保留。参数: 无。返回: None。异常: 断言失败。"""
        for backend in ('reference', 'numpy'):
            for values, expected, valid, selected, samples in (((False, False, True), 0., 2, 0, 0),
                    ((True, False, True), 1e-9, 2, 1, 1), ((False, None, True), 0., 1, 0, 0),
                    ((None, None, True), None, 0, 0, 0)):
                series = self.series(values, dtype=D.BOOL, unit='1')
                result, facts = self.run_number(backend, CalculationDefinition('time', 'duration', series.observation), series, 1)
                self.assertEqual(result.value, expected)
                self.assertEqual(sum(item.value_valid_duration_ns for item in facts), valid)
                self.assertEqual(sum(item.selected_duration_ns for item in facts), selected)
                self.assertEqual(sum(item.valid_sample_count for item in facts), samples)

    def test_zero_values_and_all_unknown(self):
        """各数值算子有效0与全未知None区分。参数: 无。返回: None。异常: 断言失败。"""
        for backend in ('reference', 'numpy'):
            for operation in ('min_time', 'max_time', 'time_weighted_mean'):
                for values, expected in (((0, 0, 99), 0.), ((None, None, 99), None)):
                    series = self.series(values)
                    result, _ = self.run_number(backend, CalculationDefinition('value', operation, series.observation), series, 1)
                    self.assertEqual(result.value, expected)

    def test_output_unit_only_once_and_integer_precision(self):
        """原kW数值最终一次转W，整数转换精度错误不能报正常结果。参数: 无。返回: None。异常: 断言失败。"""
        for backend in ('reference', 'numpy'):
            for operation in ('min_time', 'max_time', 'time_weighted_mean'):
                series = self.series((2, 2, 0), unit='kW')
                result, _ = self.run_number(backend, CalculationDefinition('value', operation, series.observation, output_unit='W'), series, 1)
                self.assertEqual(result.value, 2000.)
            series = self.series((2 ** 64 - 1, 0), dtype=D.UINT64, unit='W')
            result, _ = self.run_number(backend, CalculationDefinition('value', 'min_time', series.observation, output_unit='kW'), series)
            self.assertEqual((result.value, result.quality), (None, Q.PRECISION_LOSS))

    def test_final_conversion_range_failures(self):
        """最终单位非有限与非零下溢均是计算失败。参数: 无。返回: None。异常: 断言失败。"""
        for backend in ('reference', 'numpy'):
            for value, source, target, expected in ((1e308, 'kW', 'W', Q.NONFINITE), (5e-324, 'W', 'kW', Q.PRECISION_LOSS)):
                series = self.series((value, 0), unit=source)
                for operation in ('min_time', 'time_weighted_mean'):
                    result, _ = self.run_number(backend, CalculationDefinition('value', operation, series.observation, output_unit=target), series)
                    self.assertEqual((result.value, result.calculation_failed, result.quality), (None, True, expected))

    def test_large_absolute_time_and_no_observation(self):
        """绝对大时间仍保留1ns，域外交集不发生反序wrap。参数: 无。返回: None。异常: 断言失败。"""
        start = 2 ** 63 - 3
        series = self.series((7, 0), (start, start + 1))
        for backend in ('reference', 'numpy'):
            spec = CalculationDefinition('value', 'min_time', series.observation)
            kernel = self.kernel(backend, spec, series)
            facts = kernel.push(series)
            self.assertEqual((kernel.finish().value, facts.value_valid_duration_ns), (7., 1))
            kernel = self.kernel(backend, replace(spec, window=Interval(-2 ** 63, -2 ** 63 + 1)), series)
            self.assertIsNone(kernel.push(series).actual_window)
            self.assertIsNone(kernel.finish().value)

    def test_point_and_synthetic_updates(self):
        """点窗口没有时长，保持左端不伪装真实更新。参数: 无。返回: None。异常: 断言失败。"""
        series = self.series((4, 9, 99), updates=(False, True, True))
        for backend in ('reference', 'numpy'):
            spec = CalculationDefinition('value', 'min_time', Interval(0, 1))
            kernel = self.kernel(backend, spec, series)
            facts = kernel.push(series)
            self.assertEqual((kernel.finish().value, facts.valid_sample_count), (4., 0))
            kernel = self.kernel(backend, replace(spec, window=Interval(1, 1)), series)
            facts = kernel.push(series)
            self.assertEqual((facts.value_valid_duration_ns, facts.valid_sample_count), (0, 0))
            self.assertIsNone(kernel.finish().value)

    def test_quality_sources_and_whole_kernel_agreement(self):
        """小数据完整核对照独立手算，诊断和来源事实不丢。参数: 无。返回: None。异常: 断言失败。"""
        series = self.series((3, None, 7, 99), (0, 2, 5, 8))
        for backend, complete in (('reference', compute_reference), ('numpy', compute_numpy)):
            for operation in ('min_time', 'max_time', 'time_weighted_mean'):
                spec = CalculationDefinition('value', operation, Interval(1, 7))
                result, facts = self.run_number(backend, spec, series, 1)
                self.assertEqual(result.value, complete(series, spec).value)
                self.assertEqual(sum(item.value_valid_duration_ns for item in facts), 3)
                self.assertTrue(any(item.quality & Q.MISSING for item in facts))
                self.assertTrue(all(item.source_refs is series.source_refs for item in facts))

    def test_fixed_random_weighted_truth(self):
        """固定短轴按手算全窗权重对照切块，不能用另一后端作唯一真值。参数: 无。返回: None。异常: 断言失败。"""
        rng = random.Random(117)
        for _ in range(20):
            times = [0]
            for _ in range(7):
                times.append(times[-1] + rng.randrange(1, 10))
            raw = [float(rng.randrange(-50, 51)) if rng.randrange(4) else None for _ in times]
            series = self.series(raw, times)
            denominator = sum(times[index + 1] - time for index, time in enumerate(times[:-1]) if raw[index] is not None)
            expected = fsum(raw[index] * ((times[index + 1] - time) / denominator)
                            for index, time in enumerate(times[:-1]) if raw[index] is not None)
            for backend in ('reference', 'numpy'):
                for size in (1, 2, 7):
                    result, _ = self.run_number(backend, CalculationDefinition('mean', 'time_weighted_mean', series.observation), series, size)
                    self.assertAlmostEqual(result.value, expected, delta=1e-12)

    def test_config_and_input_rejections(self):
        """拒绝未知算子、条件、单位、dtype、身份和伪造分母。参数: 无。返回: None。异常: 断言失败。"""
        series = self.series((1, 2, 0))
        spec = CalculationDefinition('value', 'min_time', series.observation)
        for backend in ('reference', 'numpy'):
            cls = ReferenceTimeReduction if backend == 'reference' else NumpyTimeReduction
            for operation in ('integral', 'sample_mean'):
                with self.assertRaises(TypeError):
                    cls(replace(spec, operation=operation), 'W', D.FLOAT64)
            for denominator in (0, -1, True, 1., 2 ** 63):
                with self.assertRaises(ValueError):
                    cls(replace(spec, operation='time_weighted_mean'), 'W', D.FLOAT64, selected_duration_ns=denominator)
            with self.assertRaises(ValueError):
                cls(spec, 'W', D.BOOL)
            with self.assertRaises(ValueError):
                cls(replace(spec, output_unit='A'), 'W', D.FLOAT64)
            kernel = self.kernel(backend, spec, series)
            with self.assertRaises(TypeError):
                kernel.push({})
            with self.assertRaises(ValueError):
                kernel.push(replace(series, conditions=(ScalarValue(True, D.BOOL),) * 3))
            with self.assertRaises(ValueError):
                kernel.push(replace(series, unit='kW'))
            kernel.push(series)
            with self.assertRaises(ValueError):
                kernel.push(replace(series, binding_identity='other'))

    def test_frozen_models_reject_impossible_facts(self):
        """typed输出模型不接受缺失划分、虚假样本或失败正常值。参数: 无。返回: None。异常: 断言失败。"""
        series = self.series((1, 0))
        spec = CalculationDefinition('value', 'min_time', series.observation)
        facts = self.kernel('reference', spec, series).push(series)
        for changes in ({'value_valid_duration_ns': 0}, {'valid_sample_count': 2}, {'selected_duration_ns': 0},
                        {'actual_window': Interval(0, 2)}, {'quality': 'missing'}, {'source_refs': ('fake',)}):
            with self.assertRaises((TypeError, ValueError)):
                replace(facts, **changes)
        with self.assertRaises(ValueError):
            TimeReductionResult(0., 'W', True, Q.NONFINITE, 1)

    def test_generic_values_and_original_integral_delegation(self):
        """两个原积分入口委托同后端通用项入口，抵消结果和typed门槛保持。参数: 无。返回: None。异常: 断言失败。"""
        spec = CalculationDefinition('area', 'integral', Interval(0, 3))
        facts = IntegralFacts(spec, spec.window, 3, 0, (), Q.NONE, 'W', 'time-test', ())
        values = (1e16, 1., -1e16)
        for backend in ('reference', 'numpy'):
            kernel = ReferenceIntegralSum() if backend == 'reference' else NumpyIntegralSum()
            if backend == 'reference':
                terms = ReferenceIntegralTerms(values, (True,) * 3, facts)
            else:
                array, mask = np.array(values), np.ones(3, dtype=bool)
                array.setflags(write=False)
                mask.setflags(write=False)
                terms = NumpyIntegralTerms(array, mask, facts)
            with patch.object(kernel, 'push_values', wraps=kernel.push_values) as delegated:
                kernel.push(terms)
                delegated.assert_called_once()
            self.assertEqual(kernel.finish('J').value, 1.)
            with self.assertRaises(TypeError):
                kernel.push(object())

    def test_generic_values_validate_before_mutation(self):
        """通用入口拒绝非有限、可写、错列和无效非零项，原状态不动。参数: 无。返回: None。异常: 断言失败。"""
        reference = ReferenceIntegralSum()
        for values, mask in (([1.], (True,)), ((1.,), ()), ((float('inf'),), (True,)), ((1.,), (False,))):
            with self.assertRaises((TypeError, ValueError)):
                reference.push_values(values, mask)
        self.assertEqual(reference.valid_term_count, 0)
        arrays = NumpyIntegralSum()
        for raw, flags, readonly in (((1.,), (True,), False), ((float('inf'),), (True,), True), ((1.,), (False,), True)):
            values, valid = np.array(raw), np.array(flags)
            values.setflags(write=not readonly)
            valid.setflags(write=not readonly)
            with self.assertRaises((TypeError, ValueError)):
                arrays.push_values(values, valid)
        self.assertEqual(arrays.valid_term_count, 0)


if __name__ == '__main__':
    # 允许直接运行本有限专项；全项目回归由根统一执行。
    unittest.main()
