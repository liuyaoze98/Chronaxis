"""回归完整内存NumPy指标在大数消去后保留的小贡献。

输入为明确的W/kW合成完整时间轴及真实内存来源，输出为unittest断言。
先核手算积分1J、样本均值1/3W和时间均值1/3W，再独立执行标量参考与
数组内核；不以被复用的NumPy误差核作为正确性真值。覆盖原序中间溢出、
规范化时间权重、半偶舍入、零/未知、选择掩码、部分政策和最终单位转换。
超过4096个输入项不能被新增固定容量门槛拒绝；原输入和完整结果事实保持不变。
只使用新核心合成数据，不读外部文件、不计时、不改select或旧CAN路径。
"""

# 标准库求和只作独立测试真值，不参与产品NumPy实现。
from math import copysign, fsum, ldexp
import random
import unittest

# 真实内存原行、时钟、会话和绑定用于公开完整内存入口回归。
from chronaxis.core import (
    MemoryRow, SessionSpec, SignalBindings, SignalDefinition,
    SignalDType as D, SourceSpec, TimebaseSpec, TimeType, compile_expression,
)
from chronaxis.core.calculations import CalculationSeries, CalculationDefinition
from chronaxis.core.calculations_reference import compute_reference
from chronaxis.core.calculations_numpy import compute_numpy
from chronaxis.core.calculations_memory_reference import compute_memory_reference
from chronaxis.core.calculations_memory_numpy import compute_memory_numpy
from chronaxis.core.models import Interval, SourceRef
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.types import QualityFlag as Q


SECOND = 1_000_000_000
OPS = ('integral', 'sample_mean', 'time_weighted_mean')


def series_for(values, *, times=None, conditions=None, actual=None, unit='W'):
    """构造明确原值与边界的冻结完整时间轴，不补有效零。

    参数: values含末端边界值，None表示MISSING；times为可选纳秒tuple；
        conditions为可选bool/None，actual标记哪些位置是真实数值更新，unit为原单位。
    返回: CalculationSeries，默认每秒一个真实更新，来源引用为明确合成字段。
    异常: 底层模型传播类型、范围、时间回退和列长度错误。
    """
    # None同时具有无效标志与原因，不能成为归约的正常零面积。
    numeric = tuple(ScalarValue(value, D.FLOAT64, value is not None,
                               Q.NONE if value is not None else Q.MISSING)
                    for value in values)
    # TRUE/FALSE和UNKNOWN独立保存；末点只给观测边界，不增加额外时长。
    selected = None if conditions is None else tuple(
        ScalarValue(value, D.BOOL, value is not None,
                    Q.NONE if value is not None else Q.MISSING)
        for value in conditions)
    axis = tuple(index * SECOND for index in range(len(values))) if times is None else times
    updates = (True,) * len(values) if actual is None else actual
    # 非空真实字段引用让完整事实对照同时覆盖绑定与来源，而不伪造外部读取证明。
    return CalculationSeries(Interval(axis[0], axis[-1]), axis, numeric, updates, unit,
                        selected, binding_identity='cancellation-synthetic-v1',
                        source_refs=(SourceRef('session', 'sensor', 'raw'),))


class NumpyCancellationTests(unittest.TestCase):
    """以独立手算和参考核验证三种浮点归约，保留完整模型事实。"""

    def check_pair(self, series, spec, expected):
        """独立执行两后端并核对预期值、全部非数值字段及原输入。

        参数: series/spec为真实冻结模型，expected为本例独立真值或None。
        返回: NumPy CalculationResult，供具体场景检查覆盖、状态和质量。
        异常: 真值、完整事实或输入变化由unittest断言报告。
        """
        # 保留原对象和值快照，不能由数组只读设置反向修改借用的模型。
        before = (series.times_ns, series.values, series.conditions,
                  series.actual_value_updates, series.diagnostics, series.source_refs)
        reference = compute_reference(series, spec)
        actual = compute_numpy(series, spec)
        self.assertEqual(reference.value, expected)
        self.assertEqual(actual.value, expected)
        # 本组固定IEEE64真值可精确比较，不通过扩大容差掩盖低位消失。
        self.assertEqual(reference, actual)
        self.assertEqual(before, (series.times_ns, series.values, series.conditions,
                                 series.actual_value_updates, series.diagnostics,
                                 series.source_refs))
        return actual

    def test_three_operations_keep_hand_calculated_cancellation(self):
        """三个1秒区间贡献1J，两种均值均为1/3W，不是旧0或0.5。

        参数: 无。返回: None。异常: 手算或完整事实差异由断言报告。
        """
        # 末端0W仅结束观测，半开窗口排除末端样本。
        series = series_for((1e16, 1.0, -1e16, 0.0))
        for operation, expected in (('integral', 1.0), ('sample_mean', 1 / 3),
                             ('time_weighted_mean', 1 / 3)):
            with self.subTest(operation=operation):
                result = self.check_pair(series, CalculationDefinition('cancel', operation, series.observation), expected)
                self.assertEqual((result.status, result.reason, result.quality),
                                 ('complete', 'ok', Q.NONE))
                self.assertEqual((result.valid_sample_count, result.selected_duration_ns),
                                 (3, 3 * SECOND))
                self.assertEqual((result.requested_coverage, result.value_coverage,
                                  result.condition_coverage), (1.0, 1.0, 1.0))

    def test_real_memory_bindings_reach_both_independent_full_bridges(self):
        """原MemoryRow经真实编译和两条完整桥接仍得到手算三结果。

        参数: 无。返回: None。异常: 绑定、桥接、来源或输入改变由断言报告。
        """
        # 新会话与显式时间原点保证本例不继承其他测试的值或绑定。
        clock = TimebaseSpec('clock', TimeType.RELATIVE, 'cancellation-memory-v1')
        rows = tuple(MemoryRow(index * SECOND, {'raw': value}, index)
                     for index, value in enumerate((1e16, 1.0, -1e16, 0.0)))
        source = SourceSpec('sensor', clock, rows, observation_start_ns=0,
                            observation_end_ns=3 * SECOND)
        definition = SignalDefinition('power', 'sensor', 'raw', D.FLOAT64,
                                      'W', 10 * SECOND)
        bindings = SignalBindings(SessionSpec('session', clock, 0, 3 * SECOND,
                                              (source,)), (definition,))
        compiled = compile_expression('power', bindings)
        # 同一声明分别进入独立原行转换、保持、表达式和指标实现。
        for operation, expected in (('integral', 1.0), ('sample_mean', 1 / 3),
                             ('time_weighted_mean', 1 / 3)):
            with self.subTest(operation=operation):
                spec = CalculationDefinition('memory_cancel', operation, Interval(0, 3 * SECOND))
                reference = compute_memory_reference(compiled, spec)
                actual = compute_memory_numpy(compiled, spec)
                self.assertEqual((reference.value, actual.value), (expected, expected))
                self.assertEqual(reference, actual)
                self.assertEqual(actual.binding_identity, compiled.identity)
                self.assertTrue(actual.source_refs)
        self.assertIs(bindings.session.sources[0], source)
        self.assertEqual(tuple(row.values['raw'] for row in rows),
                         (1e16, 1.0, -1e16, 0.0))

    def test_half_even_smallest_term_and_valid_zero_remain_numeric(self):
        """舍入中点上方的小项和最小次正规值保留，有效消去零保持+0。

        参数: 无。返回: None。异常: 精确IEEE64或质量差异由断言报告。
        """
        # 1e16+1正好到半偶中点，再加1e-16应选择上方相邻float。
        series = series_for((1e16, 1.0, 1e-16, 0.0))
        self.check_pair(series, CalculationDefinition('half_even', 'integral', series.observation),
                        10000000000000002.0)
        # 1秒乘最小次正规值不会下溢；均值只有一个真实样本也不能补零。
        smallest = ldexp(1.0, -1074)
        for values, expected in (((smallest, 0.0), smallest),
                                 ((1e16, -1e16, 0.0), 0.0),
                                 ((-0.0, 0.0, 0.0), 0.0)):
            for operation in OPS:
                with self.subTest(values=values, operation=operation):
                    series = series_for(values)
                    result = self.check_pair(series, CalculationDefinition('tiny_zero', operation, series.observation), expected)
                    self.assertEqual(result.quality, Q.NONE)
                    if expected == 0:
                        self.assertEqual(copysign(1.0, result.value), 1.0)

    def test_false_mask_and_actual_updates_keep_their_original_meaning(self):
        """FALSE排除危险乘积，真实更新掩码只影响样本均值而不改保持积分。

        参数: 无。返回: None。异常: 掩码、计数或数值差异由断言报告。
        """
        # 最后1e308保持两秒但明确FALSE，不应计算成Inf再使正常选中集失败。
        series = series_for((1e16, 1.0, -1e16, 1e308, 0.0),
                            times=(0, SECOND, 2 * SECOND, 3 * SECOND, 5 * SECOND),
                            conditions=(True, True, True, False, False))
        for operation, expected in (('integral', 1.0), ('sample_mean', 1 / 3),
                             ('time_weighted_mean', 1 / 3)):
            with self.subTest(operation=operation):
                result = self.check_pair(series, CalculationDefinition('masked', operation, series.observation), expected)
                self.assertEqual((result.selected_duration_ns, result.quality), (3 * SECOND, Q.NONE))
        # 中间1W为合成边界而非真实更新：样本只余正负大数，保持值仍贡献面积。
        series = series_for((1e16, 1.0, -1e16, 0.0), actual=(True, False, True, True))
        for operation, expected in (('integral', 1.0), ('sample_mean', 0.0),
                             ('time_weighted_mean', 1 / 3)):
            with self.subTest(actual_mask_op=operation):
                result = self.check_pair(series, CalculationDefinition('updates', operation, series.observation), expected)
                self.assertEqual(result.valid_sample_count, 2)

    def test_partial_unknown_false_empty_and_unobserved_policies_are_preserved(self):
        """部分/严格、UNKNOWN、全FALSE、零窗与无观测不被空归约统一成零。

        参数: 无。返回: None。异常: 状态、覆盖、原因或数值差异由断言报告。
        """
        # 最后一秒缺值；前三秒仍独立形成可核实的消去结果。
        partial = series_for((1e16, 1.0, -1e16, None, 0.0))
        for operation in OPS:
            for policy in ('report', 'strict'):
                with self.subTest(operation=operation, policy=policy):
                    expected = None if policy == 'strict' else 1.0 if operation == 'integral' else 1 / 3
                    spec = CalculationDefinition('partial', operation, partial.observation, policy)
                    result = self.check_pair(partial, spec, expected)
                    self.assertEqual((result.value_coverage, result.requested_coverage), (0.75, 1.0))
                    self.assertEqual(result.value_unknown_ranges, (Interval(3 * SECOND, 4 * SECOND),))
                    self.assertTrue(result.quality & Q.MISSING)
                    self.assertEqual(result.reason, 'insufficient_coverage' if policy == 'strict' else 'partial_coverage')
        # 全未知与有明确FALSE证明不同；数值无效的诊断仍保留。
        unknown = series_for((None, None, None))
        false = series_for((None, None, None), conditions=(False, False, False))
        for operation in OPS:
            with self.subTest(empty_op=operation):
                result = self.check_pair(unknown, CalculationDefinition('unknown', operation, unknown.observation), None)
                self.assertEqual(result.reason, 'no_valid_selected_data')
                result = self.check_pair(false, CalculationDefinition('false', operation, false.observation),
                                         0.0 if operation == 'integral' else None)
                self.assertEqual(result.reason, 'empty_selection')
                for window, reason in ((Interval(0, 0), 'zero_length_window'),
                                       (Interval(8 * SECOND, 9 * SECOND), 'no_observation')):
                    result = self.check_pair(false, CalculationDefinition('empty', operation, window), None)
                    self.assertEqual(result.reason, reason)

    def test_original_order_overflow_and_normalized_time_mean_stay_distinct(self):
        """原总和中途溢出不能后续抵消恢复，时间均值仍先规范化权重。

        参数: 无。返回: None。异常: 原序、失败质量或均值差异由断言报告。
        """
        # 原始前两项之和溢出，积分和样本均值须保留既有参考失败政策。
        series = series_for((1e308, 1e308, -1e308, 0.0))
        for operation in ('integral', 'sample_mean'):
            with self.subTest(operation=operation):
                result = self.check_pair(series, CalculationDefinition('overflow', operation, series.observation), None)
                self.assertEqual((result.reason, result.quality), ('calculation_failed', Q.NONFINITE))
                self.assertEqual(result.value_coverage, 1.0)
        # 时间权重每项为1/3，有限加权项的原序和没有发生上述原总和溢出。
        result = self.check_pair(series, CalculationDefinition('weighted', 'time_weighted_mean', series.observation),
                                 1e308 * (1 / 3))
        self.assertEqual(result.quality, Q.NONE)
        # 相反顺序先精确消去大数，然后加入小项，不能因输入跨度大而误拒。
        series = series_for((1e308, -1e308, 1.0, 0.0))
        for operation, expected in (('integral', 1.0), ('sample_mean', 1 / 3),
                             ('time_weighted_mean', 1 / 3)):
            self.check_pair(series, CalculationDefinition('finite_order', operation, series.observation), expected)

    def test_clipping_and_final_unit_conversion_do_not_move_inside_sum(self):
        """先裁剪区间、后归约、最后一次换单位，不提前放大可抵消项。

        参数: 无。返回: None。异常: 裁剪、单位、精度或结果差异由断言报告。
        """
        # 提前把每个kW值乘1000会溢出；当前契约只转换已经消去的大数总和。
        series = series_for((1e308, -1e308, 1.0, 0.0), unit='kW')
        for operation in OPS:
            output_unit = 'J' if operation == 'integral' else 'W'
            expected = 1000.0 if operation == 'integral' else (1 / 3) * 1000
            result = self.check_pair(series, CalculationDefinition('units', operation, series.observation,
                                                      output_unit=output_unit), expected)
            self.assertEqual((result.unit, result.quality), (output_unit, Q.NONE))
        # 大数两侧各裁0.5秒，仍只余中间1J；时间均值分母为2秒。
        series = series_for((1e16, 1.0, -1e16, 0.0))
        clipped = Interval(SECOND // 2, 5 * SECOND // 2)
        self.check_pair(series, CalculationDefinition('clip', 'integral', clipped), 1.0)
        self.check_pair(series, CalculationDefinition('clip_mean', 'time_weighted_mean', clipped), 0.5)
        # Wh倍率只在正常原量纲1J之后执行一次，不在各项分别转换。
        self.check_pair(series, CalculationDefinition('wh', 'integral', series.observation,
                                          output_unit='Wh'), 1 / 3600)

    def test_more_than_4096_terms_add_no_new_fixed_capacity_rejection(self):
        """完整输入超过旧流式默认容量仍正常，不因项数产生新阈值异常。

        参数: 无。返回: None。异常: 新增容量错误或手算差异由断言报告。
        """
        # 4097个零也是有效原项，随后三项的低位必须保留；末0只给边界。
        values = (0.0,) * 4097 + (1e16, 1.0, -1e16)
        series = series_for(values + (0.0,))
        for operation in OPS:
            with self.subTest(operation=operation):
                expected = 1.0 if operation == 'integral' else 1 / len(values)
                result = self.check_pair(series, CalculationDefinition('long', operation, series.observation), expected)
                self.assertEqual((result.valid_sample_count, result.quality), (len(values), Q.NONE))

    def test_fixed_exponent_streams_match_independent_fsum_and_reference(self):
        """固定指数跨度流以标准库fsum独立核真值，不拿NumPy流式核自证。

        参数: 无。返回: None。异常: 数值、完整事实或输入变化由断言报告。
        """
        rng = random.Random(70180)
        # 有界小组保留极大/极小、正负和舍入变化，不作规模或性能结论。
        for case in range(12):
            values = tuple(ldexp(rng.uniform(-1.0, 1.0), rng.randint(-900, 900))
                           for _ in range(15))
            series = series_for(values + (0.0,))
            expected = {'integral': fsum(values),
                        'sample_mean': fsum(values) / len(values),
                        'time_weighted_mean': fsum(value * (1 / len(values)) for value in values)}
            for operation in OPS:
                with self.subTest(case=case, operation=operation):
                    self.check_pair(series, CalculationDefinition('exponents', operation, series.observation), expected[operation])


if __name__ == '__main__':
    # 直接执行仅启动本专项，模块导入不触发测试或外部I/O。
    unittest.main()
