"""用独立手算检查有限数值/条件轴合并，不以另一后端制造预期。

输入显式指定整数纳秒、typed值与三值条件，检查条件边界不成为数值样本。
已有参考/NumPy面积核分别消费合并输入，仍保持数值实现独立。
本专项不读文件、不修改原输入；不代表实际封存历史owner或公共AnalysisRunner接线。
"""

# 手算样例只使用有限冻结模型，两面积核独立执行同一已合并协议。
import unittest
from dataclasses import replace
from unittest.mock import patch
from chronaxis.core.calculation_series_join import join_calculation_series
from chronaxis.core.calculations import CalculationSeries, CalculationDefinition
from chronaxis.core.calculations_reference import compute_reference
from chronaxis.core.calculations_numpy import compute_numpy
from chronaxis.core.models import Interval, SourceRef
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.types import SignalDType as D, QualityFlag as Q
from chronaxis.sources.csv_spec import CSVSourceRef


class CalculationSeriesJoinTests(unittest.TestCase):
    """逐一验收边界、样本、质量、容量及原始值身份，不使用共享结果真值。"""

    def series(self, times, values, *, dtype=D.FLOAT64, unit='W', updates=None, refs=()):
        """建立明确的有限列，None携带MISSING而不是FALSE。

        参数: times/values及声明dtype/unit/真实更新/来源。返回: CalculationSeries。
        异常: 输入模型门槛传播；默认各原轴点均声明真实更新。
        """
        rows = tuple(ScalarValue(None, dtype, False, Q.MISSING) if value is None else
                     ScalarValue(float(value) if dtype is D.FLOAT64 else value, dtype)
                     for value in values)
        return CalculationSeries(Interval(times[0], times[-1]), tuple(times), rows,
                            tuple(updates) if updates is not None else (True,) * len(times),
                            unit, binding_identity='joined-test', source_refs=tuple(refs))

    def condition(self, times, values, **kwargs):
        """声明BOOL列。参数: 时间/三值/额外字段。返回: CalculationSeries。异常: 原门槛。
        """
        return self.series(times, values, dtype=D.BOOL, unit='1', **kwargs)

    def test_condition_only_boundaries_do_not_add_samples(self):
        """常数4W，条件T/F/U/T各1秒，真值8J、条件覆盖3/4，仅0秒真实值样本。

        参数: 无。返回: None。异常: 边界、三值、样本或手算结果改变。
        """
        end = 4_000_000_000
        value = self.series((0, end), (4, 999))
        condition = self.condition(tuple(i * 1_000_000_000 for i in range(5)),
                                   (True, False, None, True, False))
        joined = join_calculation_series(value, condition, max_intervals=4)
        self.assertEqual(joined.times_ns, condition.times_ns)
        self.assertEqual(joined.actual_value_updates, (True, False, False, False, True))
        self.assertEqual(tuple(v.value for v in joined.conditions), (True, False, None, True, False))
        self.assertEqual(joined.conditions[2].quality, Q.MISSING)
        self.assertEqual(joined.values[-1].value, 999)
        for compute in (compute_reference, compute_numpy):
            result = compute(joined, CalculationDefinition('area', 'integral', Interval(0, end)))
            self.assertEqual((result.value, result.status, result.condition_coverage), (8., 'partial', .75))
            self.assertEqual((result.value_valid_duration_ns, result.selected_duration_ns), (end, 2_000_000_000))
            self.assertEqual(result.valid_sample_count, 1)
            strict = compute(joined, CalculationDefinition('area', 'integral', Interval(0, end), 'strict'))
            self.assertIsNone(strict.value)

    def test_false_unknown_and_selected_value_missing_remain_distinct(self):
        """全FALSE可证明0、全UNKNOWN为None，值未知与条件未知分别记录。

        参数: 无。返回: None。异常: 用空求和把未知当正常0。
        """
        value = self.series((0, 2_000_000_000), (None, 4))
        for state, expected in ((False, 0), (None, None), (True, None)):
            joined = join_calculation_series(value, self.condition(value.times_ns, (state, state)))
            for compute in (compute_reference, compute_numpy):
                result = compute(joined, CalculationDefinition('area', 'integral', value.observation))
                self.assertEqual(result.value, expected)
                self.assertEqual(result.value_valid_duration_ns, 0)
                self.assertEqual(result.condition_known_duration_ns,
                                 0 if state is None else value.observation.end_ns)

    def test_clipping_uses_left_hold_and_keeps_real_update_flags(self):
        """[2,7)裁剪左端为保持值而非样本，双方5同刻只保留一次边界。

        参数: 无。返回: None。异常: 读取未来值或重复同刻更新。
        """
        value = self.series((0, 5, 8), (1, 2, 3))
        condition = self.condition((0, 3, 5, 8), (True, False, True, False))
        joined = join_calculation_series(value, condition, window=Interval(2, 7))
        self.assertEqual(joined.times_ns, (2, 3, 5, 7))
        self.assertEqual(tuple(v.value for v in joined.values), (1, 1, 2, 2))
        self.assertEqual(joined.actual_value_updates, (False, False, True, False))
        self.assertEqual(tuple(v.value for v in joined.conditions), (True, False, True, True))

    def test_point_and_real_terminal_never_add_interval(self):
        """实际末点更新保留为点值，点窗口只一个位置，不产生面积。

        参数: 无。返回: None。异常: EOF被延长或末点贡献积分。
        """
        value = self.series((0, 3), (2, 100))
        condition = self.condition((0, 3), (True, False))
        point = join_calculation_series(value, condition, window=Interval(3, 3), max_intervals=1)
        self.assertEqual((point.times_ns, point.values[0].value, point.conditions[0].value), ((3,), 100, False))
        for compute in (compute_reference, compute_numpy):
            self.assertIsNone(compute(point, CalculationDefinition('area', 'integral', point.observation)).value)
            result = compute(join_calculation_series(value, condition), CalculationDefinition('area', 'integral', value.observation))
            self.assertAlmostEqual(result.value, 6e-9)

    def test_capacity_rejects_before_constructing_output(self):
        """联合四区间容量3须失败，不能删边界或先分配输出再检查。

        参数: 无。返回: None。异常: 容量错误未抛出或已经构造输出。
        """
        value = self.series((0, 2, 4), (1, 2, 3))
        condition = self.condition((0, 1, 3, 4), (True, False, True, False))
        # 两个输入已经校验；容量不足时不能再调用输出模型的构造校验。
        with patch.object(CalculationSeries, '__post_init__', side_effect=AssertionError('过早构造输出')) as output:
            with self.assertRaisesRegex(ValueError, 'max_intervals'):
                join_calculation_series(value, condition, max_intervals=3)
            output.assert_not_called()
        self.assertEqual(join_calculation_series(value, condition, max_intervals=4).times_ns, (0, 1, 2, 3, 4))

    def test_full_sources_diagnostics_and_exact_integers_are_preserved(self):
        """完整来源、原依赖质量和uint64最大整数不经float转换。

        参数: 无。返回: None。异常: 来源丢失/诊断覆盖/整数精度损失。
        """
        a = SourceRef('session', 'value_source', 'raw.value')
        b = SourceRef('session', 'condition_source', 'raw.flag')
        # 纯元数据样例不读取此路径，同一原字段的CSV具体位置不能被基类吞掉。
        csv = CSVSourceRef('session', 'value_source', 'raw.value',
                           'work/synthetic.csv', 2, '0', str(2**64-1), False)
        value = self.series((0, 4), (2**64-1, 1), dtype=D.UINT64, unit='1', refs=(a,))
        condition = replace(self.condition((0, 2, 4), (False, None, True), refs=(a, b, csv)),
                            diagnostics=(Q.STALE, Q.MISSING, Q.NONE))
        joined = join_calculation_series(value, condition)
        self.assertEqual(joined.source_refs, (a, b, csv))
        self.assertIs(joined.source_refs[-1], csv)
        self.assertIs(joined.values[1], value.values[0])
        self.assertEqual(joined.values[1].value, 2**64-1)
        self.assertEqual(joined.diagnostics, (Q.STALE, Q.MISSING, Q.NONE))
        self.assertIs(joined.conditions[1], condition.values[1])

    def test_different_domains_require_explicit_covered_window(self):
        """观测不同不猜结束范围，显式[2,5]双方覆盖可合并，外推拒绝。

        参数: 无。返回: None。异常: 缺观测被静默补齐。
        """
        value = self.series((0, 5), (1, 2))
        condition = self.condition((2, 8), (True, False))
        with self.assertRaises(ValueError):
            join_calculation_series(value, condition)
        self.assertEqual(join_calculation_series(value, condition, window=Interval(2, 5)).times_ns, (2, 5))
        with self.assertRaises(ValueError):
            join_calculation_series(value, condition, window=Interval(1, 6))

    def test_reject_invalid_config_and_preserve_inputs(self):
        """嵌套条件、非BOOL、错误窗口和容量拒绝，原冻结输入完全不变。

        参数: 无。返回: None。异常: 非法配置被隐式修复。
        """
        value = self.series((0, 5), (1, 2))
        condition = self.condition((0, 5), (True, False))
        before = (value, condition)
        for wrong in (True, 0, -1, 1.5):
            with self.assertRaises((TypeError, ValueError)):
                join_calculation_series(value, condition, max_intervals=wrong)
        for wrong in (value, replace(condition, unit='V'), replace(condition, conditions=condition.values)):
            with self.assertRaises(ValueError):
                join_calculation_series(value, wrong)
        with self.assertRaises(TypeError):
            join_calculation_series(value, condition, window=(0, 5))
        with self.assertRaises(TypeError):
            join_calculation_series(None, condition)
        join_calculation_series(value, condition)
        self.assertEqual((value, condition), before)
