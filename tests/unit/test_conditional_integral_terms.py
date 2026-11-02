"""用手算真值检查两独立有限条件面积核及最终分类，不访问真实历史。

共用typed输入测试TRUE/FALSE/UNKNOWN、两个覆盖分区、真实值更新、精度与面积故障。
原序归约复用各自IntegralSum.push_values，最终单位只转换一次；不伪造IntegralTerms。
合法零、全FALSE零证明、未知None和计算失败分开，并与原完整核交叉核对政策。
测试只使用小型内存模型，无文件/来源扫描副作用；运行日志由命令保存在work。
"""

# 冻结模型用replace制造不合法输入，不复制或调用另一后端数值作预期。
from dataclasses import replace
import unittest
import numpy as np
from chronaxis.core.conditional_integral_terms import ReferenceConditionalIntegralTerms
from chronaxis.core.conditional_integral_terms_reference import compute_conditional_integral_terms_reference
from chronaxis.core.conditional_integral_terms_numpy import NumpyConditionalIntegralTerms, compute_conditional_integral_terms_numpy
from chronaxis.core.conditional_integral_result import make_conditional_integral_result
from chronaxis.core.integral_sum import IntegralSumResult
from chronaxis.core.integral_sum_reference import ReferenceIntegralSum
from chronaxis.core.integral_sum_numpy import NumpyIntegralSum
from chronaxis.core.calculations import CalculationSeries, CalculationDefinition, calculation_unit
from chronaxis.core.calculations_reference import compute_reference
from chronaxis.core.calculations_numpy import compute_numpy
from chronaxis.core.models import Interval, SourceRef
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.types import QualityFlag as Q, SignalDType as D
from chronaxis.sources.csv_spec import CSVSourceRef
from chronaxis.timebase.conversion import INT64_MIN, INT64_MAX


class ConditionalIntegralTermsTests(unittest.TestCase):
    """两个后端共用有限typed输入，期待值来自手算而非另一个内核。"""

    def series(self, times=(0, 1_000_000_000), values=(4.0, 99.0), conditions=(True, False),
               *, dtype=D.FLOAT64, unit='W', actual=None, refs=None, diagnostics=()):
        """建立明确合成值与三值条件，None代表MISSING而非正常零。

        参数: times为完整ns轴，values/conditions为同长原生值；dtype/unit声明值类型和单位；
            actual为真实值更新标志，refs为完整来源，diagnostics为额外依赖原因。
        返回: 冻结CalculationSeries。异常: 不合法typed输入由原模型检查传播。
        """
        # None具有显式质量；BOOL条件与数值dtype分别声明，禁止隐式真假转换。
        numeric = tuple(ScalarValue(value, dtype) if value is not None else ScalarValue(None, dtype, False, Q.MISSING) for value in values)
        condition = None if conditions is None else tuple(ScalarValue(value, D.BOOL) if value is not None else ScalarValue(None, D.BOOL, False, Q.MISSING) for value in conditions)
        updates = tuple(True for _ in times) if actual is None else actual
        refs = (SourceRef('session', 'table', 'raw.value'),) if refs is None else refs
        return CalculationSeries(Interval(times[0], times[-1]), times, numeric, updates, unit, condition,
                            diagnostics, 'explicit-conditional-synthetic', refs)

    def terms(self, series, spec, backend):
        """调用一个独立面积核，不由测试预先计算覆盖。

        参数: series/spec为typed输入，backend为reference/numpy。
        返回: 对应原序冻结面积项。异常: 实际核心错误原样传播。
        """
        compute = compute_conditional_integral_terms_reference if backend == 'reference' else compute_conditional_integral_terms_numpy
        return compute(series, spec)

    def result(self, terms, backend):
        """通过相同后端原序数值推进及一次最终转换得到分类结果。

        参数: terms为真实有限输出，backend声明独立归约后端。
        返回: CalculationResult。异常: 原模型、数值容量、单位或分类错误传播。
        """
        # 面积在原单位下原序推进；数值计数不能伪造成真实值更新样本。
        reducer = ReferenceIntegralSum() if backend == 'reference' else NumpyIntegralSum()
        reducer.push_values(terms.areas, terms.valid)
        unit, factor = calculation_unit(terms.facts.spec, terms.facts.input_unit)
        return make_conditional_integral_result(terms.facts, reducer.finish(unit, factor))

    def test_hand_true_false_unknown_true_and_original_policies(self):
        """4W的T/F/U/T四秒面积8J、条件覆盖.75、样本1，strict保留诊断但无部分值。

        参数: 无。返回: None。异常: 面积、分区、政策或原完整核不符手算断言失败。
        """
        # 四个一秒区间只选第1、4段；中间条件更新不是原值更新，末点999也不贡献面积。
        series = self.series((0, 10**9, 2*10**9, 3*10**9, 4*10**9), (4.0,)*4+(999.0,),
                             (True, False, None, True, False), actual=(True, False, False, False, True))
        # 两独立面积/归约后端分别验证report与strict，同一输入的事实不因政策而变化。
        for backend, whole in (('reference', compute_reference), ('numpy', compute_numpy)):
            for policy in ('report', 'strict'):
                with self.subTest(backend=backend, policy=policy):
                    spec = CalculationDefinition('energy', 'integral', series.observation, partial_policy=policy, minimum_coverage=.8)
                    terms = self.terms(series, spec, backend)
                    # 手算4+4=8J；FALSE和UNKNOWN槽位都未乘面积，但有效性不能混同。
                    self.assertEqual(tuple(terms.areas), (4.0, 0.0, 0.0, 4.0))
                    self.assertEqual(tuple(terms.valid), (True, False, False, True))
                    facts, result = terms.facts, self.result(terms, backend)
                    self.assertEqual((facts.value_valid_duration_ns, facts.condition_known_duration_ns,
                        facts.selected_duration_ns, facts.false_duration_ns, facts.selected_value_unknown_duration_ns,
                        facts.valid_sample_count), (4*10**9, 3*10**9, 2*10**9, 10**9, 0, 1))
                    self.assertEqual(facts.condition_unknown_ranges, (Interval(2*10**9, 3*10**9),))
                    self.assertEqual(facts.value_unknown_ranges, ())
                    # 条件已知3/4低于.8门槛；report留8J、strict留None，完整核只作政策交叉核对。
                    self.assertEqual(result.value, 8.0 if policy == 'report' else None)
                    self.assertEqual(result.condition_coverage, .75)
                    self.assertEqual(result.coverage_status, 'indeterminate')
                    self.assertEqual(result, whole(series, spec))

    def test_false_zero_proof_unknown_and_true_without_values_are_distinct(self):
        """完整FALSE即使值全缺失仍证明0；条件未知或TRUE值未知不能凭空返回0。

        参数: 无。返回: None。异常: 空和、条件真假和双覆盖混淆断言失败。
        """
        # 三种都没有有效面积项，但只有正窗口全FALSE有零证明；其余保留各自未知原因。
        cases = (((None, None), (False, False), 0.0, 'empty_selection', 0, 10**9, 0),
                 ((4.0, 4.0), (None, None), None, 'unknown_selection', 10**9, 0, 0),
                 ((None, None), (True, True), None, 'no_valid_selected_data', 0, 10**9, 10**9))
        # 两后端分别核对数值/原因及值、条件覆盖，避免仅检查掩码相同就认作等价。
        for values, conditions, expected, reason, value_ns, known_ns, selected_unknown in cases:
            for backend in ('reference', 'numpy'):
                with self.subTest(conditions=conditions, backend=backend):
                    series = self.series(values=values, conditions=conditions)
                    terms = self.terms(series, CalculationDefinition('proof', 'integral', series.observation), backend)
                    facts, result = terms.facts, self.result(terms, backend)
                    self.assertFalse(any(terms.valid))
                    self.assertEqual((result.value, result.reason), (expected, reason))
                    self.assertEqual((facts.value_valid_duration_ns, facts.condition_known_duration_ns,
                        facts.selected_value_unknown_duration_ns), (value_ns, known_ns, selected_unknown))
                    self.assertEqual(facts.valid_sample_count, 0)

    def test_independent_missing_partitions_and_real_value_updates(self):
        """TRUE缺值和条件UNKNOWN各记自己的区间，FALSE有效值只贡献值覆盖。

        参数: 无。返回: None。异常: 分区交集、FALSE时长或条件更新计样本断言失败。
        """
        # 四个1ns区间分别为TRUE缺值、FALSE有效零、条件未知且缺值、TRUE有效2。
        # 最后一段只由条件或边界变化形成，actual=False，因此2e-9面积不带真实样本。
        series = self.series((0, 1, 2, 3, 4), (None, 0.0, None, 2.0, 99.0),
                             (True, False, None, True, True), actual=(True, True, False, False, True))
        # 逐后端核对完整双分区与交集：值有效2ns、条件已知3ns、选中1ns、TRUE值未知1ns。
        for backend in ('reference', 'numpy'):
            terms = self.terms(series, CalculationDefinition('partition', 'integral', series.observation), backend)
            facts = terms.facts
            self.assertEqual(tuple(terms.areas), (0.0, 0.0, 0.0, 2e-9))
            self.assertEqual((facts.value_valid_duration_ns, facts.condition_known_duration_ns,
                facts.selected_duration_ns, facts.selected_value_unknown_duration_ns, facts.false_duration_ns,
                facts.valid_sample_count), (2, 3, 1, 1, 1, 0))
            self.assertEqual(facts.value_unknown_ranges, (Interval(0, 1), Interval(2, 3)))
            self.assertEqual(facts.condition_unknown_ranges, (Interval(2, 3),))

    def test_only_true_multiplies_and_area_failure_changes_value_and_samples(self):
        """1e308乘2秒在TRUE溢出，FALSE/UNKNOWN不做乘法；后续有效TRUE仍报告部分2J。

        参数: 无。返回: None。异常: 未选择项误失效或面积故障漏改样本断言失败。
        """
        # 同一大值区间在TRUE时实际乘2秒才溢出；FALSE/UNKNOWN不乘，后段固定产生2J。
        for condition in (True, False, None):
            for backend in ('reference', 'numpy'):
                series = self.series((0, 2*10**9, 3*10**9), (1e308, 2.0, 0.0), (condition, True, False))
                terms = self.terms(series, CalculationDefinition('overflow', 'integral', series.observation), backend)
                facts, result = terms.facts, self.result(terms, backend)
                # 正常后段提供唯一有效样本；前段仅在TRUE失去值覆盖，UNKNOWN另影响条件覆盖。
                self.assertEqual(tuple(terms.areas), (0.0, 2.0))
                self.assertEqual(facts.value_valid_duration_ns, 10**9 if condition is True else 3*10**9)
                self.assertEqual(facts.valid_sample_count, 1)
                self.assertEqual(facts.quality, Q.NONFINITE if condition is True else Q.MISSING if condition is None else Q.NONE)
                self.assertEqual(result.value, 2.0)
                self.assertEqual(result.status, 'complete' if condition is False else 'partial')
                # 面积故障必须保留原2秒值未知位置，不能只在数值掩码中丢掉它。
                if condition is True:
                    self.assertEqual(facts.selected_value_unknown_duration_ns, 2*10**9)
                    self.assertEqual(facts.value_unknown_ranges, (Interval(0, 2*10**9),))

    def test_underflow_is_unknown_only_when_selected_and_valid_zero_is_evidence(self):
        """最小非零float乘1ns下溢不可当0；FALSE未乘保留有效值，真实零TRUE是合法0。

        参数: 无。返回: None。异常: 下溢与正常零、未选择面积判据混淆断言失败。
        """
        # 每例只观察1ns：最小非零值TRUE乘法下溢、FALSE不乘、正常零TRUE有效是三种不同证据。
        cases = ((5e-324, True, Q.PRECISION_LOSS, False, None),
                 (5e-324, False, Q.NONE, False, 0.0), (0.0, True, Q.NONE, True, 0.0))
        # 核对面积掩码、值覆盖和真实样本一起失效/保留，再检查最终零或None分类。
        for value, condition, quality, keep, expected in cases:
            for backend in ('reference', 'numpy'):
                series = self.series((0, 1), (value, 99.0), (condition, False))
                terms = self.terms(series, CalculationDefinition('small', 'integral', series.observation), backend)
                self.assertEqual(tuple(terms.valid), (keep,))
                self.assertEqual(terms.facts.quality, quality)
                self.assertEqual(terms.facts.value_valid_duration_ns, 0 if quality else 1)
                self.assertEqual(terms.facts.valid_sample_count, 1 if keep else 0)
                self.assertEqual(self.result(terms, backend).value, expected)

    def test_fixed_integer_precision_checks_false_values_without_rounded_evidence(self):
        """不可精确的大整数即使FALSE仍失去值覆盖，2**63与INT64_MIN可精确浮点表示。

        参数: 无。返回: None。异常: 类型转换舍入冒充正常值或大精确数误拒绝断言失败。
        """
        # 2**53+1及其负数不可精确转float；2**63和INT64_MIN虽大但浮点可精确表示。
        cases = ((D.UINT64, 2**53+1, False), (D.INT64, -(2**53+1), False),
                 (D.UINT64, 2**63, True), (D.INT64, -2**63, True))
        # TRUE/FALSE都必须先过值精度门槛；选择仅决定面积及真实样本是否参与。
        for dtype, value, exact in cases:
            for condition in (True, False):
                for backend in ('reference', 'numpy'):
                    with self.subTest(dtype=dtype, condition=condition, backend=backend):
                        series = self.series((0, 1), (value, value), (condition, False), dtype=dtype)
                        terms = self.terms(series, CalculationDefinition('precision', 'integral', series.observation), backend)
                        self.assertEqual(terms.facts.value_valid_duration_ns, int(exact))
                        self.assertEqual(terms.facts.quality, Q.NONE if exact else Q.PRECISION_LOSS)
                        self.assertEqual(tuple(terms.valid), (exact and condition,))
                        self.assertEqual(terms.facts.valid_sample_count, int(exact and condition))

    def test_clipping_and_int64_extremes_preserve_ns_and_exclude_terminal(self):
        """裁剪2—7ns先求整数差，即使绝对坐标极大也得到1e-9/0/4e-9，终点质量排除。

        参数: 无。返回: None。异常: 绝对时间float舍入、终点或合成边界计数断言失败。
        """
        # 在0、int64下界及上界附近重复同一小跨度；末点故意缺值且条件未知以检查半开边界。
        for base in (0, INT64_MIN, INT64_MAX-8):
            times = tuple(base+offset for offset in (0, 3, 5, 8))
            series = self.series(times, (1.0, 99.0, 2.0, None), (True, False, True, None), actual=(True, False, True, True))
            # 请求2—7ns只包含首段1ns与末有效段2ns，只有5ns原值更新计为一个样本。
            for backend in ('reference', 'numpy'):
                terms = self.terms(series, CalculationDefinition('clip', 'integral', Interval(base+2, base+7)), backend)
                self.assertEqual(tuple(terms.areas), (1e-9, 0.0, 4e-9))
                self.assertEqual(tuple(terms.valid), (True, False, True))
                self.assertEqual((terms.facts.value_valid_duration_ns, terms.facts.condition_known_duration_ns,
                    terms.facts.selected_duration_ns, terms.facts.valid_sample_count), (5, 5, 3, 1))
                self.assertEqual(terms.facts.quality, Q.NONE)

    def test_zero_point_disjoint_and_short_false_observation_do_not_prove_full_zero(self):
        """零请求、点观测和无交集没有面积，局部FALSE观测不能证明完整请求为0。

        参数: 无。返回: None。异常: 空和或截断FALSE误给零证据断言失败。
        """
        # 四种缺少完整正观察的原因分别为零请求、单点、无交集、EOF只覆盖请求前半窗。
        # 最后一例虽实际观测全FALSE，仍没有证据说明未观察的后半窗也FALSE。
        cases = ((self.series(), Interval(1, 1), Interval(1, 1), 'zero_length_window'),
                 (self.series((5,), (2.0,), (False,)), Interval(0, 10), Interval(5, 5), 'no_observation'),
                 (self.series(), Interval(2*10**9, 3*10**9), None, 'no_observation'),
                 (self.series(conditions=(False, False)), Interval(0, 2*10**9), Interval(0, 10**9), 'no_valid_selected_data'))
        # 空有效掩码必须配合实际范围和明确None原因判断，不能把空归约自动当正常零。
        for series, window, actual, reason in cases:
            for backend in ('reference', 'numpy'):
                terms = self.terms(series, CalculationDefinition('empty', 'integral', window), backend)
                result = self.result(terms, backend)
                self.assertFalse(any(terms.valid))
                self.assertEqual(terms.facts.actual_window, actual)
                self.assertEqual((result.value, result.reason), (None, reason))

    def test_original_units_one_final_conversion_sources_and_dependency_quality(self):
        """kW面积2/6原量级保留，最终只换一次Wh；CSV完整定位和已知逻辑依赖质量保留。

        参数: 无。返回: None。异常: 双转换、来源降格或诊断丢失断言失败。
        """
        # 原单位kW的两段分别2*1和3*2；CSV子类保留原单元格，额外STALE来自依赖诊断。
        ref = CSVSourceRef('session', 'table', 'raw.value', 'synthetic.csv', 3, '1.000', '2', False)
        refs = (ref, SourceRef('session', 'condition', 'raw.flag'))
        series = self.series((0, 10**9, 3*10**9), (2.0, 3.0, 99.0), (True, True, False),
                             unit='kW', refs=refs, diagnostics=(Q.STALE, Q.NONE, Q.MISSING))
        # 先核对原量级面积及完整来源对象；末点MISSING不在半开观察中，不能污染质量。
        for backend in ('reference', 'numpy'):
            spec = CalculationDefinition('units', 'integral', series.observation, output_unit='Wh')
            terms = self.terms(series, spec, backend)
            self.assertEqual(tuple(terms.areas), (2.0, 6.0))
            self.assertEqual(terms.facts.input_unit, 'kW')
            self.assertIs(terms.facts.source_refs, refs)
            self.assertIs(terms.facts.source_refs[0], ref)
            self.assertEqual(terms.facts.quality, Q.STALE)
            # 最终只换一次：8kW*s乘1000再除3600为Wh，输入诊断不改变完整选择状态。
            result = self.result(terms, backend)
            self.assertAlmostEqual(result.value, 8*1000/3600, places=14)
            self.assertEqual((result.unit, result.status, result.valid_sample_count), ('Wh', 'complete', 2))
            self.assertIs(result.source_refs[0], ref)

    def test_original_order_cancellation_and_numerical_failure_keep_full_coverage(self):
        """1e16/1/-1e16原序归约保留1；中间或最终转换溢出只使数值失败，不改完整覆盖。

        参数: 无。返回: None。异常: 块预求和消掉小项、故障覆盖重写或后续抵消恢复断言失败。
        """
        # 一秒面积原序分别验证低位抵消、中途1e308+1e308溢出、kW最终乘1000溢出。
        cases = (((1e16, 1.0, -1e16, 0.0), 'W', 1.0, False),
                 ((1e308, 1e308, -1e308, 0.0), 'W', None, True),
                 ((1e308, 0.0, 0.0, 0.0), 'kW', None, True))
        # 每项面积本身均有限有效；归约或最终转换失败只改变数值状态，完整覆盖和3个样本保留。
        for values, unit, expected, failed in cases:
            for backend in ('reference', 'numpy'):
                series = self.series((0, 10**9, 2*10**9, 3*10**9), values, (True,)*4, unit=unit)
                terms = self.terms(series, CalculationDefinition('sum', 'integral', series.observation), backend)
                result = self.result(terms, backend)
                self.assertTrue(all(terms.valid))
                self.assertEqual((result.value, result.value_coverage, result.condition_coverage,
                    result.selected_duration_ns, result.valid_sample_count), (expected, 1.0, 1.0, 3*10**9, 3))
                self.assertEqual(result.reason, 'calculation_failed' if failed else 'ok')
                self.assertEqual(result.quality, Q.NONFINITE if failed else Q.NONE)

    def test_models_are_frozen_masked_and_reject_impossible_partitions(self):
        """冻结模型拒绝无效非零、可写数组、乱序未知和交集矛盾，不改原输入。

        参数: 无。返回: None。异常: 模型放过矛盾或输出可写断言失败。
        """
        # 正常同一输入先核对未被改写，并检查数组输出只读一维float64/bool实际布局。
        series = self.series()
        spec = CalculationDefinition('model', 'integral', series.observation)
        reference, array = self.terms(series, spec, 'reference'), self.terms(series, spec, 'numpy')
        self.assertEqual(series.values[0], ScalarValue(4.0, D.FLOAT64))
        self.assertFalse(array.areas.flags.writeable)
        self.assertFalse(array.valid.flags.writeable)
        self.assertEqual((array.areas.dtype, array.valid.dtype, array.areas.ndim), (np.dtype('float64'), np.dtype('bool'), 1))
        # 完整值有效却声称TRUE值未知，以及错几何/类型等不能靠总量掩盖。
        bad = ({'selected_duration_ns': 5*10**8, 'selected_value_unknown_duration_ns': 5*10**8},
               {'value_valid_duration_ns': True}, {'valid_sample_count': 10**9+1},
               {'value_valid_duration_ns': 0, 'value_unknown_ranges': (Interval(0, 7*10**8), Interval(5*10**8, 10**9))},
               {'condition_known_duration_ns': 0, 'condition_unknown_ranges': ()},
               {'actual_window': Interval(0, 2*10**9)}, {'source_refs': ['raw.value']})
        for changes in bad:
            with self.subTest(changes=changes), self.assertRaises((TypeError, ValueError)):
                replace(reference.facts, **changes)
        # 面积存储与显式掩码不符必须拒绝；冻结事实不能让无效非零冒充正常面积。
        with self.assertRaises(ValueError):
            ReferenceConditionalIntegralTerms((4.0,), (False,), reference.facts)
        # copy恢复可写、reshape变二维：两种数组协议错误分别检查，不靠自动冻结或压平修复。
        with self.assertRaises(ValueError):
            NumpyConditionalIntegralTerms(array.areas.copy(), array.valid.copy(), array.facts)
        with self.assertRaises(TypeError):
            NumpyConditionalIntegralTerms(array.areas.reshape((1, 1)), array.valid.reshape((1, 1)), array.facts)

    def test_typed_input_and_final_unit_term_sample_contracts(self):
        """条件/数值能力和分类单位、项数门槛严格检查，不能用typed外壳掩盖矛盾。

        参数: 无。返回: None。异常: 错能力或错误结果配对被接受断言失败。
        """
        # 从合法数值积分基线构造缺条件、BOOL主值、非integral算子和明确不可转换单位四种拒绝输入。
        series = self.series()
        spec = CalculationDefinition('typed', 'integral', series.observation)
        for backend in ('reference', 'numpy'):
            for bad_series, bad_spec in ((replace(series, conditions=None), spec),
                    (self.series(values=(True, False), dtype=D.BOOL, unit='1'), spec),
                    (series, replace(spec, operation='time_weighted_mean')),
                    (replace(series, unit='unknown-unit'), replace(spec, output_unit='J'))):
                with self.subTest(backend=backend, operation=bad_spec.operation, unit=bad_series.unit), self.assertRaises((TypeError, ValueError)):
                    self.terms(bad_series, bad_spec, backend)
            facts = self.terms(series, spec, backend).facts
            # typed数值自身合法，但与事实的样本/有效项或单位不能配对。
            for number in (IntegralSumResult(4.0, 'Wh', False, Q.NONE, 1),
                           IntegralSumResult(None, 'J', False, Q.NONE, 0),
                           IntegralSumResult(4.0, 'J', False, Q.NONE, 10**9+1)):
                with self.assertRaises(ValueError):
                    make_conditional_integral_result(facts, number)
            # 非typed结果在配对前即拒绝，不把对象缺字段异常当业务UNKNOWN。
            with self.assertRaises(TypeError):
                make_conditional_integral_result(facts, object())


# 允许单独命令运行专项，完整回归由主任务统一负责。
if __name__ == '__main__':
    unittest.main()
