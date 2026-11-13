"""独立手算及真实有限历史块验证原序未转换积分项。

小型typed输入给出面积、未知、质量与覆盖真值；参考核不以NumPy结果作预期。
真实memory/CSV块按1/2/7区间切分，检查源终点、原序项与原单位转换分离。
测试只为合成小数据保存摘要，纯核输出在原块close前消费；原工厂核对RAM0。
覆盖定宽精度、FLOAT乘积溢出/下溢、零/无交集及非法能力/只读协议。
"""

# 原真实分块测试只作为夹具模块使用，不重复收集类。
from dataclasses import replace
from math import fsum
import unittest
import numpy as np
from chronaxis.core.integral_terms import ReferenceIntegralTerms
from chronaxis.core.integral_terms_reference import compute_integral_terms_reference
from chronaxis.core.integral_terms_numpy import NumpyIntegralTerms, compute_integral_terms_numpy
from chronaxis.core.calculations import CalculationSeries, CalculationDefinition, calculation_unit, merge_ranges
from chronaxis.core.calculations_reference import compute_reference
from chronaxis.core.calculations_numpy import compute_numpy
from chronaxis.core.models import Interval, MemoryRow, SourceRef
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.types import SignalDType as D, QualityFlag as Q
from chronaxis.timebase.conversion import INT64_MIN, INT64_MAX, TimeOverflowError


class IntegralTermsTests(unittest.TestCase):
    """两个独立核共用typed输入，原计算值由手算和原完整核双重校核。"""

    def series(self, times=(0, 3, 5, 8), values=None, dtype=D.FLOAT64, unit='1', actual=None):
        """建立明确合成typed输入。

        参数: times完整ns轴；values可为ScalarValue tuple；dtype/unit为原类型/单位；
            actual为真实更新标志，省略表示每点真实更新。
        返回: CalculationSeries。异常: 原模型错误传播。
        """
        if values is None:
            values = (ScalarValue(1.0, dtype), ScalarValue(None, dtype, False, Q.STALE),
                      ScalarValue(2.0, dtype), ScalarValue(9.0, dtype))
        actual = tuple(True for _ in times) if actual is None else actual
        return CalculationSeries(Interval(times[0], times[-1]), times, values, actual, unit,
                            binding_identity='explicit-terms-synthetic', source_refs=(SourceRef('session', 'table', 'raw.a'),))

    def terms(self, series, spec, backend):
        """调用当前独立核。

        参数: series/spec为真实typed输入；backend为reference/numpy。
        返回: 相应冻结积分项。异常: 原输入/计算错误传播。
        """
        compute = compute_integral_terms_reference if backend == 'reference' else compute_integral_terms_numpy
        return compute(series, spec)

    def summary(self, terms):
        """只恢复测试摘要，不构造参考预期。

        参数: terms为真实参考/数组输出。返回: (areas tuple, valid tuple, facts)。
        异常: 实际输出结构错误传播。
        """
        return tuple(float(value) for value in terms.areas), tuple(bool(value) for value in terms.valid), terms.facts

    def test_hand_clipped_zoh_order_masks_unknown_and_true_updates(self):
        """2—7ns裁剪得到1e-9/未知/4e-9，覆盖3ns、样本1且不跨缺口。

        参数: 无。返回: None。异常: 顺序、掩码、覆盖或质量不符手算断言失败。
        """
        series = self.series(actual=(True, False, True, True))
        spec = CalculationDefinition('area', 'integral', Interval(2, 7), scope='event', minimum_coverage=0.8)
        for backend in ('reference', 'numpy'):
            areas, keep, facts = self.summary(self.terms(series, spec, backend))
            self.assertEqual(areas, (1e-9, 0.0, 4e-9))
            self.assertEqual(keep, (True, False, True))
            self.assertEqual(facts.actual_window, Interval(2, 7))
            self.assertEqual(facts.value_valid_duration_ns, 3)
            self.assertEqual(facts.valid_sample_count, 1)
            self.assertEqual(facts.value_unknown_ranges, (Interval(3, 5),))
            self.assertEqual(facts.quality, Q.STALE)
            self.assertIs(facts.spec, spec)
            self.assertIs(facts.source_refs, series.source_refs)

    def test_raw_unit_terms_do_not_apply_kilowatt_or_output_factor_per_block(self):
        """kW原序面积2/6在最终换Wh前保持原量级，不提前乘1000或除3600。

        参数: 无。返回: None。异常: 重复或提前单位转换断言失败。
        """
        series = self.series((0, 1_000_000_000, 3_000_000_000),
            (ScalarValue(2.0, D.FLOAT64), ScalarValue(3.0, D.FLOAT64), ScalarValue(100.0, D.FLOAT64)), unit='kW')
        spec = CalculationDefinition('energy', 'integral', series.observation, output_unit='Wh')
        _, factor = calculation_unit(spec, series.unit)
        for backend, whole in (('reference', compute_reference), ('numpy', compute_numpy)):
            areas, keep, facts = self.summary(self.terms(series, spec, backend))
            self.assertEqual(areas, (2.0, 6.0))
            self.assertEqual(keep, (True, True))
            self.assertEqual(facts.input_unit, 'kW')
            self.assertAlmostEqual(fsum(areas) * factor, whole(series, spec).value, places=14)
            self.assertEqual(facts.valid_sample_count, 2)

    def test_precision_nonfinite_and_underflow_make_terms_unknown_not_zero(self):
        """大整数丢精度、乘积溢出和非零下溢均保留诊断，正常零仍有效。

        参数: 无。返回: None。异常: 无效当0、合法大整数误失效或样本漏改断言失败。
        """
        cases = ((D.UINT64, 2 ** 53 + 1, 1, Q.PRECISION_LOSS, False),
                 (D.UINT64, 2 ** 63, 1, Q.NONE, True),
                 (D.INT64, -2 ** 63, 1, Q.NONE, True),
                 (D.FLOAT64, 1e308, 2_000_000_000, Q.NONFINITE, False),
                 (D.FLOAT64, 5e-324, 1, Q.PRECISION_LOSS, False),
                 (D.FLOAT64, 0.0, 1, Q.NONE, True))
        for dtype, number, end, quality, valid in cases:
            for backend in ('reference', 'numpy'):
                with self.subTest(dtype=dtype, number=number, backend=backend):
                    series = self.series((0, end), (ScalarValue(number, dtype), ScalarValue(number, dtype)), dtype=dtype)
                    spec = CalculationDefinition('numeric', 'integral', series.observation)
                    areas, keep, facts = self.summary(self.terms(series, spec, backend))
                    self.assertEqual(keep, (valid,))
                    self.assertEqual(facts.quality, quality)
                    self.assertEqual(facts.value_valid_duration_ns, end if valid else 0)
                    self.assertEqual(facts.valid_sample_count, 1 if valid else 0)
                    if not valid:
                        self.assertEqual(areas, (0.0,))
                        self.assertEqual(facts.value_unknown_ranges, (series.observation,))

    def test_zero_no_intersection_all_unknown_and_adjacent_unknown_ranges(self):
        """零/无交集无有效项，全未知不是正常空和，连续未知只紧凑合并诊断。

        参数: 无。返回: None。异常: 假面积/观测/未知范围错误断言失败。
        """
        series = self.series()
        for backend in ('reference', 'numpy'):
            for window, actual in ((Interval(5, 5), Interval(5, 5)), (Interval(9, 10), None)):
                areas, keep, facts = self.summary(self.terms(series, CalculationDefinition('empty', 'integral', window), backend))
                self.assertFalse(any(keep))
                self.assertEqual(facts.actual_window, actual)
                self.assertEqual(facts.value_valid_duration_ns, 0)
                self.assertEqual(facts.valid_sample_count, 0)
                self.assertEqual(facts.value_unknown_ranges, ())
            unknown = self.series(values=tuple(ScalarValue(None, D.FLOAT64, False, Q.MISSING) for _ in range(4)))
            _, keep, facts = self.summary(self.terms(unknown, CalculationDefinition('unknown', 'integral', Interval(2, 7)), backend))
            self.assertFalse(any(keep))
            self.assertEqual(facts.value_unknown_ranges, (Interval(2, 7),))
            point = self.series((5,), (ScalarValue(2.0, D.FLOAT64),))
            result = self.terms(point, CalculationDefinition('point', 'integral', Interval(5, 5)), backend)
            self.assertEqual(len(result.areas), 0)

    def test_large_absolute_coordinates_preserve_nanosecond_terms_and_clipped_masks(self):
        """int64两端附近仍先求整数小差，窗口外槽位保留而不进入归约。

        参数: 无。返回: None。异常: float绝对时间舍入或裁剪次序错误断言失败。
        """
        for base in (INT64_MIN, INT64_MAX - 8):
            times = tuple(base + value for value in (0, 3, 5, 8))
            series = self.series(times)
            for backend in ('reference', 'numpy'):
                spec = CalculationDefinition('exact', 'integral', Interval(base + 5, base + 7))
                areas, keep, facts = self.summary(self.terms(series, spec, backend))
                self.assertEqual(areas, (0.0, 0.0, 4e-9))
                self.assertEqual(keep, (False, False, True))
                self.assertEqual(facts.value_valid_duration_ns, 2)
                self.assertEqual(facts.quality, Q.NONE)



    def test_inputs_wrong_operator_condition_unit_or_span_rejected(self):
        """未支持条件/算子、单位冲突及不能表示的dt在数值计算前拒绝。

        参数: 无。返回: None。异常: 静态错误被吞为未知或放宽能力断言失败。
        """
        series = self.series()
        for backend in ('reference', 'numpy'):
            for bad in (CalculationDefinition('bad', 'time_weighted_mean', series.observation),
                        CalculationDefinition('bad', 'integral', series.observation, output_unit='W')):
                with self.assertRaises(ValueError):
                    self.terms(series, bad, backend)
            with self.assertRaises(ValueError):
                self.terms(replace(series, conditions=tuple(ScalarValue(False, D.BOOL) for _ in series.times_ns)),
                           CalculationDefinition('condition', 'integral', series.observation), backend)
        # 原Interval模型已拒绝超int64跨度，不能声称这种输入到达面积内核。
        with self.assertRaises(TimeOverflowError):
            Interval(INT64_MIN, INT64_MAX)

    def test_frozen_output_models_reject_bad_masks_nonfinite_and_impossible_facts(self):
        """返回模型严格有限/只读，错误掩码和不可能覆盖不被修补。

        参数: 无。返回: None。异常: 结构不变量或数组输入被修改断言失败。
        """
        series = self.series()
        spec = CalculationDefinition('area', 'integral', Interval(2, 7))
        terms = self.terms(series, spec, 'numpy')
        self.assertEqual(terms.areas.dtype, np.float64)
        self.assertEqual(terms.valid.dtype, bool)
        self.assertFalse(terms.areas.flags.writeable)
        with self.assertRaises(ValueError):
            terms.areas[0] = 9
        with self.assertRaises(ValueError):
            ReferenceIntegralTerms((1.0,), (False,), terms.facts)
        # 返回模型不能接纳非有限有效面积，即使未经过计算入口。
        with self.assertRaises(ValueError):
            ReferenceIntegralTerms((float('inf'),), (True,), terms.facts)
        with self.assertRaises(ValueError):
            areas = np.array([float('nan')], dtype=np.float64)
            valid = np.array([True], dtype=bool)
            areas.setflags(write=False)
            valid.setflags(write=False)
            NumpyIntegralTerms(areas, valid, terms.facts)
        with self.assertRaises(ValueError):
            replace(terms.facts, value_valid_duration_ns=100)
        with self.assertRaises(ValueError):
            NumpyIntegralTerms(np.zeros(3), np.ones(3, dtype=bool), terms.facts)
        self.assertEqual(series.values[0].value, 1.0)
