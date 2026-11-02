"""用手算验证有限条件时间统计两独立纯核，不读取真实历史或来源。

覆盖极值原定宽精度、mean两遍全TRUE有效分母、主BOOL FALSE正常零、双未知分区、
真实值更新与半开边界。数值weight/最终换算故障独立于输入覆盖，单位只finish转换。
每个后端共用typed输入但预期来自手算；非法配置、身份与事实不被修补成业务UNKNOWN。
仅使用小型有限内存模型，测试无文件副作用，执行日志由命令保存在work专用目录。
"""

# 冻结输入用于构造明确边界；NumPy/参考被测核各自独立，不用另一后端值作真值。
from dataclasses import replace
import unittest
from chronaxis.core.conditional_time_reduction_reference import ReferenceConditionalTimeReduction
from chronaxis.core.conditional_time_reduction_numpy import NumpyConditionalTimeReduction
from chronaxis.core.calculations import CalculationSeries, CalculationDefinition
from chronaxis.core.models import Interval, SourceRef
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.types import QualityFlag as Q, SignalDType as D
from chronaxis.sources.csv_spec import CSVSourceRef
from chronaxis.timebase.conversion import INT64_MIN, INT64_MAX


class ConditionalTimeReductionTests(unittest.TestCase):
    """两个后端在同一小型typed输入下分别核对手算候选与覆盖事实。"""

    def series(self, times=(0, 1), values=(4.0, 99.0), conditions=(True, False),
               *, dtype=D.FLOAT64, unit='1', actual=None, refs=None, diagnostics=()):
        """建立明确三值和真实更新输入，None为MISSING而不是正常零。

        参数: times完整ns轴；values/conditions同长原值；dtype/unit为原声明；
            actual为真实值更新，refs完整来源，diagnostics额外依赖原因。
        返回: 冻结CalculationSeries。异常: 原typed模型错误传播。
        """
        # 数值和外BOOL各自有有效性及质量；None不在helper中被猜成False或0。
        values = tuple(ScalarValue(value, dtype) if value is not None else ScalarValue(None, dtype, False, Q.MISSING) for value in values)
        conditions = None if conditions is None else tuple(ScalarValue(value, D.BOOL) if value is not None else ScalarValue(None, D.BOOL, False, Q.MISSING) for value in conditions)
        actual = tuple(True for _ in times) if actual is None else actual
        refs = (SourceRef('session', 'table', 'raw.value'),) if refs is None else refs
        return CalculationSeries(Interval(times[0], times[-1]), times, values, actual, unit, conditions,
                            diagnostics, 'explicit-conditional-time-synthetic', refs)

    def reducer(self, series, operation, backend, *, denominator=None, spec=None):
        """建立一个后端归约实例，默认保持原观察请求。

        参数: series提供原unit/dtype，operation为时间算子；backend声明独立核；
            denominator为mean次遍全TRUE有效ns，spec可显式裁剪/换单位。
        返回: 新纯归约实例。异常: 原配置错误传播。
        """
        # 每个测试后端有独立状态，不让首遍/次遍或两个后端共享可变候选。
        cls = ReferenceConditionalTimeReduction if backend == 'reference' else NumpyConditionalTimeReduction
        spec = CalculationDefinition('time_metric', operation, series.observation) if spec is None else spec
        return cls(spec, series.unit, series.values[0].dtype, selected_duration_ns=denominator)

    def test_hand_true_false_unknown_true_extrema_and_two_pass_mean(self):
        """T/F/U/T的2、8选中值手算极值2/8、均值5，条件覆盖3/4且真实样本1。

        参数: 无。返回: None。异常: 选择分母、真实更新或双覆盖不符真值断言失败。
        """
        # 外FALSE的99和UNKNOWN的-100都不参与数值；末点缺值不污染半开窗口质量。
        series = self.series((0, 1, 2, 3, 4), (2.0, 99.0, -100.0, 8.0, None),
                             (True, False, None, True, None), actual=(True, False, False, False, True))
        for backend in ('reference', 'numpy'):
            for operation, expected in (('min_time', 2.0), ('max_time', 8.0), ('time_weighted_mean', 5.0)):
                # mean首遍只确认TRUE有效时长2ns，次遍复读同一有限模型并使用这个全窗分母。
                reducer = self.reducer(series, operation, backend)
                facts = reducer.push(series)
                if operation == 'time_weighted_mean':
                    with self.assertRaises(RuntimeError):
                        reducer.finish()
                    reducer = self.reducer(series, operation, backend, denominator=reducer.selected_duration_ns)
                    self.assertEqual(reducer.push(series), facts)
                # 三算子共用同一选择事实，条件独自更新不成为数值样本。
                number = reducer.finish()
                self.assertEqual((number.value, number.valid_term_count, number.calculation_failed), (expected, 2, False))
                self.assertEqual((facts.value_valid_duration_ns, facts.condition_known_duration_ns,
                    facts.selected_duration_ns, facts.selected_value_unknown_duration_ns, facts.false_duration_ns,
                    facts.selected_false_duration_ns, facts.valid_sample_count), (4, 3, 2, 0, 1, 0, 1))
                self.assertEqual(facts.value_unknown_ranges, ())
                self.assertEqual(facts.condition_unknown_ranges, (Interval(2, 3),))
                self.assertEqual(facts.quality, Q.MISSING)

    def test_missing_value_condition_partitions_and_mean_first_pass(self):
        """TRUE缺值、FALSE有效零、外UNKNOWN缺值、TRUE有效2分别形成完整双分区。

        参数: 无。返回: None。异常: 分区、交集或合成边界样本误计断言失败。
        """
        # 最后一段TRUE有效2并非真实值更新，贡献均值/极值但样本数0。
        series = self.series((0, 1, 2, 3, 4), (None, 0.0, None, 2.0, 99.0),
                             (True, False, None, True, True), actual=(True, True, False, False, True))
        for backend in ('reference', 'numpy'):
            for operation in ('min_time', 'max_time', 'time_weighted_mean'):
                facts = self.reducer(series, operation, backend).push(series)
                # TRUE值未知仅0—1；2—3是外条件未知，不能扩大为TRUE值未知。
                self.assertEqual((facts.value_valid_duration_ns, facts.condition_known_duration_ns,
                    facts.selected_duration_ns, facts.selected_value_unknown_duration_ns, facts.false_duration_ns,
                    facts.valid_sample_count), (2, 3, 1, 1, 1, 0))
                self.assertEqual(facts.value_unknown_ranges, (Interval(0, 1), Interval(2, 3)))
                self.assertEqual(facts.condition_unknown_ranges, (Interval(2, 3),))

    def test_extrema_preserve_full_uint64_and_signed_integer_precision(self):
        """uint64最大两整数以及INT64两端极值保持原int，不先转float舍入。

        参数: 无。返回: None。异常: 原dtype精度、选择或不必要精度失效断言失败。
        """
        # 每例两个正区间都为外TRUE以比较原整数；末点外FALSE仅提供边界，不参与极值。
        cases = ((D.UINT64, (2**64-1, 2**64-2, 0), 2**64-2, 2**64-1),
                 (D.INT64, (-2**63, 2**63-1, 0), -2**63, 2**63-1))
        for dtype, values, minimum, maximum in cases:
            for backend in ('reference', 'numpy'):
                series = self.series((0, 1, 2), values, (True, True, False), dtype=dtype)
                for operation, expected in (('min_time', minimum), ('max_time', maximum)):
                    reducer = self.reducer(series, operation, backend)
                    facts, number = reducer.push(series), reducer.finish()
                    self.assertIs(type(number.value), int)
                    self.assertEqual(number.value, expected)
                    self.assertEqual((facts.value_valid_duration_ns, facts.selected_duration_ns, facts.quality), (2, 2, Q.NONE))

    def test_mean_precision_applies_even_false_but_only_true_forms_denominator(self):
        """mean检查所有值精度，但FALSE/UNKNOWN不成为规范化分母或权重。

        参数: 无。返回: None。异常: 未选大整数舍入污染覆盖或分母误算断言失败。
        """
        # 不精确整数在TRUE和FALSE各一段，第三段TRUE精确2；可用分母只剩1ns。
        series = self.series((0, 1, 2, 3), (2**53+1, 2**53+1, 2, 0), (True, False, True, None), dtype=D.UINT64)
        for backend in ('reference', 'numpy'):
            first = self.reducer(series, 'time_weighted_mean', backend)
            facts = first.push(series)
            self.assertEqual((first.value_valid_duration_ns, first.selected_duration_ns), (1, 1))
            self.assertEqual((facts.selected_value_unknown_duration_ns, facts.false_duration_ns, facts.quality), (1, 1, Q.PRECISION_LOSS))
            self.assertEqual(facts.value_unknown_ranges, (Interval(0, 2),))
            # 第二遍只用精确选中2，原输入大整数不会被替换成正常零进入均值。
            second = self.reducer(series, 'time_weighted_mean', backend, denominator=1)
            self.assertEqual(second.push(series), facts)
            self.assertEqual(second.finish().value, 2.0)

    def test_mean_normalizes_before_multiplication_and_weights_true_selection(self):
        """1e308保持2秒均值仍有限；选中权重按2/5、3/5而不是整个观察窗7秒。

        参数: 无。返回: None。异常: 先面积溢出、先求块均值或分母含FALSE断言失败。
        """
        # 第一例直接面积会1e308*2溢出，均值先用dt/D=1应保留1e308。
        cases = ((self.series((0, 2*10**9), (1e308, 0.0), (True, False)), 1e308),
                 (self.series((0, 2*10**9, 4*10**9, 7*10**9), (2.0, 100.0, 8.0, 0.0), (True, False, True, False)), 5.6))
        for series, expected in cases:
            for backend in ('reference', 'numpy'):
                first = self.reducer(series, 'time_weighted_mean', backend)
                facts = first.push(series)
                second = self.reducer(series, 'time_weighted_mean', backend, denominator=first.selected_duration_ns)
                self.assertEqual(second.push(series), facts)
                # 手算2*(2/5)+8*(3/5)=5.6，不能用被拒绝的100补分母或先求面积。
                number = second.finish()
                self.assertEqual(number.value, expected)
                self.assertFalse(number.calculation_failed)

    def test_weight_underflow_is_numeric_failure_without_changing_full_coverage(self):
        """最小非零float权重1/2下溢使整次均值失败，输入2ns与两个样本仍完整。

        参数: 无。返回: None。异常: weight失败被当正常零或把覆盖改成部分断言失败。
        """
        # 两段输入均有效TRUE，第二段正常1不可以掩盖第一段非零weight下溢。
        series = self.series((0, 1, 2), (5e-324, 1.0, 0.0), (True, True, False))
        for backend in ('reference', 'numpy'):
            first = self.reducer(series, 'time_weighted_mean', backend)
            facts = first.push(series)
            second = self.reducer(series, 'time_weighted_mean', backend, denominator=2)
            self.assertEqual(second.push(series), facts)
            number = second.finish()
            self.assertEqual((facts.value_valid_duration_ns, facts.selected_duration_ns, facts.valid_sample_count, facts.quality), (2, 2, 2, Q.NONE))
            self.assertEqual((number.value, number.calculation_failed, number.quality, number.valid_term_count), (None, True, Q.PRECISION_LOSS, 2))

    def test_duration_main_false_zero_outer_false_and_unknown_evidence(self):
        """主FALSE外TRUE提供正常0，外FALSE或UNKNOWN无数值项，不能由纯核凭空补0。

        参数: 无。返回: None。异常: 主FALSE混UNKNOWN、外FALSE直接零或样本口径错误断言失败。
        """
        # 第一例主BOOL有效FALSE、外TRUE；第二外FALSE；第三外UNKNOWN；第四主未知外TRUE。
        cases = ((False, True, 0.0, 1, 1, 0, 1), (True, False, None, 0, 0, 1, 1),
                 (True, None, None, 0, 0, 0, 1), (None, True, None, 0, 0, 0, 0))
        for value, condition, expected, term_count, selected_false, false_ns, value_ns in cases:
            for backend in ('reference', 'numpy'):
                series = self.series(values=(value, False), conditions=(condition, False), dtype=D.BOOL)
                reducer = self.reducer(series, 'duration', backend)
                facts, number = reducer.push(series), reducer.finish()
                # selected只主TRUE，这四例都0；主FALSE1ns证据单独留在selected_false。
                self.assertEqual((number.value, number.valid_term_count), (expected, term_count))
                self.assertEqual((facts.selected_duration_ns, facts.selected_false_duration_ns,
                    facts.false_duration_ns, facts.value_valid_duration_ns, facts.valid_sample_count), (0, selected_false, false_ns, value_ns, 0))

    def test_duration_true_counts_only_real_values_under_outer_true(self):
        """外TRUE主TRUE累计2ns，但条件独自更新和终点不计样本；主FALSE1ns有效零保留。

        参数: 无。返回: None。异常: BOOL时长、真假交集或边界真实样本误计断言失败。
        """
        # 三段主TRUE/FALSE/TRUE且外TRUE；只有0ns是已选原值真实更新，2ns是条件/边界更新。
        series = self.series((0, 1, 2, 3), (True, False, True, None), (True, True, True, None),
                             dtype=D.BOOL, actual=(True, True, False, True))
        for backend in ('reference', 'numpy'):
            reducer = self.reducer(series, 'duration', backend)
            facts, number = reducer.push(series), reducer.finish()
            self.assertEqual((number.value, number.unit, number.valid_term_count), (2e-9, 's', 3))
            self.assertEqual((facts.value_valid_duration_ns, facts.condition_known_duration_ns, facts.selected_duration_ns,
                facts.selected_false_duration_ns, facts.valid_sample_count, facts.quality), (3, 3, 2, 1, 1, Q.NONE))

    def test_int64_boundary_clipping_point_and_no_intersection(self):
        """极大绝对时间仍保留1ns差；零点/无交集不会因点值产生数值证据。

        参数: 无。返回: None。异常: 裁剪时间舍入、终点或空和误给数值断言失败。
        """
        # 两端附近同样裁剪2—7ns，只选择1*1ns和2*2ns，均值手算5/3。
        for base in (INT64_MIN, INT64_MAX-8):
            times = tuple(base+offset for offset in (0, 3, 5, 8))
            series = self.series(times, (1.0, 99.0, 2.0, None), (True, False, True, None), actual=(True, False, True, True))
            for backend in ('reference', 'numpy'):
                spec = CalculationDefinition('edge', 'time_weighted_mean', Interval(base+2, base+7))
                reducer = self.reducer(series, 'time_weighted_mean', backend, denominator=3, spec=spec)
                facts = reducer.push(series)
                self.assertAlmostEqual(reducer.finish().value, 5/3)
                self.assertEqual((facts.value_valid_duration_ns, facts.selected_duration_ns, facts.valid_sample_count, facts.quality), (5, 3, 1, Q.NONE))
        # min/max/duration只凭正区间有证据；零请求和不相交观察域均保留None/0项。
        for backend in ('reference', 'numpy'):
            for window, actual in ((Interval(0, 0), Interval(0, 0)), (Interval(2, 3), None)):
                series = self.series()
                reducer = self.reducer(series, 'min_time', backend, spec=CalculationDefinition('empty', 'min_time', window))
                facts, number = reducer.push(series), reducer.finish()
                self.assertEqual((facts.actual_window, number.value, number.valid_term_count), (actual, None, 0))
            point = self.series((5,), (4.0,), (True,))
            reducer = self.reducer(point, 'max_time', backend)
            self.assertEqual(reducer.push(point).valid_sample_count, 0)
            self.assertIsNone(reducer.finish().value)

    def test_multiblock_mean_original_order_and_final_conversion(self):
        """多块3e16/3/-3e16按全窗D=3保留均值1，最终kW转W仅一次且状态不存全轴。

        参数: 无。返回: None。异常: 块均值拼接、小项抵消或重复转换断言失败。
        """
        # 三个独立1ns块总选择3ns；每块规范权重1/3给1e16、1、-1e16原序项。
        blocks = tuple(self.series((i, i+1), (value, 0.0), (True, False), unit='kW') for i, value in enumerate((3e16, 3.0, -3e16)))
        spec = CalculationDefinition('split', 'time_weighted_mean', Interval(0, 3), output_unit='W')
        for backend in ('reference', 'numpy'):
            first = self.reducer(blocks[0], 'time_weighted_mean', backend, spec=spec)
            first_facts = tuple(first.push(block) for block in blocks)
            self.assertEqual(first.selected_duration_ns, 3)
            second = self.reducer(blocks[0], 'time_weighted_mean', backend, denominator=3, spec=spec)
            self.assertEqual(tuple(second.push(block) for block in blocks), first_facts)
            number = second.finish()
            self.assertEqual((number.value, number.unit, number.valid_term_count), (1000.0, 'W', 3))
            self.assertEqual((second.value_valid_duration_ns, second.selected_duration_ns), (3, 3))

    def test_units_sources_dependency_and_conversion_failure_keep_facts(self):
        """完整CSV定位与依赖原因保留，极值最终换单位精度/溢出故障不改输入覆盖。

        参数: 无。返回: None。异常: 来源降格、诊断丢失或转换故障改覆盖断言失败。
        """
        # 诊断STALE是逻辑依赖原因，原有效值仍可选；CSV原单元格与来源子类须原样保存。
        ref = CSVSourceRef('session', 'table', 'raw.value', 'synthetic.csv', 2, '0', '2', False)
        series = self.series(unit='kW', refs=(ref,), diagnostics=(Q.STALE, Q.MISSING))
        for backend in ('reference', 'numpy'):
            spec = CalculationDefinition('unit', 'max_time', series.observation, output_unit='W')
            reducer = self.reducer(series, 'max_time', backend, spec=spec)
            facts, number = reducer.push(series), reducer.finish()
            self.assertEqual((number.value, number.unit, facts.quality), (4000.0, 'W', Q.STALE))
            self.assertIs(facts.source_refs, series.source_refs)
            self.assertIs(facts.source_refs[0], ref)
            # 不精确大整数要求换单位、或1e308最终乘1000，数值失败但原dtype极值覆盖完整。
            for dtype, value, quality in ((D.UINT64, 2**53+1, Q.PRECISION_LOSS), (D.FLOAT64, 1e308, Q.NONFINITE)):
                bad = self.series(values=(value, value), dtype=dtype, unit='kW')
                reducer = self.reducer(bad, 'max_time', backend, spec=replace(spec, window=bad.observation))
                facts, number = reducer.push(bad), reducer.finish()
                self.assertEqual((facts.value_valid_duration_ns, facts.selected_duration_ns, facts.quality), (1, 1, Q.NONE))
                self.assertEqual((number.value, number.calculation_failed, number.quality), (None, True, quality))

    def test_configuration_identity_denominator_and_fact_partitions_reject_errors(self):
        """显式BOOL、单位/dtype、身份与分母门槛严格，冻结事实拒绝交集和未知矛盾。

        参数: 无。返回: None。异常: 非法结构被隐式修复或矛盾事实未拒绝断言失败。
        """
        # 从正常TRUE数值基线制造配置/输入错误；模型错误不是业务UNKNOWN。
        series = self.series()
        for backend in ('reference', 'numpy'):
            for bad in (replace(series, conditions=None), replace(series, unit='W'), self.series(dtype=D.INT64, values=(4, 99))):
                with self.assertRaises((TypeError, ValueError)):
                    self.reducer(series, 'min_time', backend).push(bad)
            reducer = self.reducer(series, 'min_time', backend)
            facts = reducer.push(series)
            with self.assertRaises(ValueError):
                reducer.push(replace(series, binding_identity='different'))
            # mean分母必须正原生int64，且finish校验实际次遍选择时长相同。
            for denominator in (0, True, 1.0, -1):
                with self.assertRaises(ValueError):
                    self.reducer(series, 'time_weighted_mean', backend, denominator=denominator)
            mismatch = self.reducer(series, 'time_weighted_mean', backend, denominator=2)
            mismatch.push(series)
            with self.assertRaises(ValueError):
                mismatch.finish()
            # TRUE值未知不能超过总值未知；数值ops不能伪造selected_false或越界/重叠未知。
            bad_facts = ({'selected_duration_ns': 0, 'selected_value_unknown_duration_ns': 1},
                         {'selected_duration_ns': 0, 'selected_false_duration_ns': 1},
                         {'value_valid_duration_ns': True}, {'condition_known_duration_ns': 0},
                         {'value_valid_duration_ns': 0, 'value_unknown_ranges': (Interval(0, 1), Interval(0, 1))},
                         {'actual_window': Interval(0, 2)}, {'source_refs': ['raw.value']})
            for changes in bad_facts:
                with self.subTest(changes=changes), self.assertRaises((TypeError, ValueError)):
                    replace(facts, **changes)


# 专项可独立启动，完整回归和真实历史生命周期由主任务统一验证。
if __name__ == '__main__':
    unittest.main()
