"""按手算核对条件积分的所选周期、实际有效期与按需未知范围；保旧详细事实契约。"""

from dataclasses import replace
import unittest
from chronaxis.core.calculations import CalculationSeries, CalculationDefinition
from chronaxis.core.models import Interval
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.types import SignalDType as D, QualityFlag as Q
from chronaxis.core.conditional_integral_terms_reference import compute_conditional_integral_terms_reference
from chronaxis.core.conditional_integral_terms_numpy import compute_conditional_integral_terms_numpy
from chronaxis.core.conditional_integral_result import make_conditional_integral_result
from chronaxis.core.integral_sum_reference import ReferenceIntegralSum
from chronaxis.core.integral_sum_numpy import NumpyIntegralSum


class RecordConditionalIntegralTermsTests(unittest.TestCase):
    """两条驱动记录形成一个完整分母，值和条件覆盖分别保留。"""

    backends = ((compute_conditional_integral_terms_reference, ReferenceIntegralSum),
                (compute_conditional_integral_terms_numpy, NumpyIntegralSum))

    def series(self, condition=True):
        """构造0—0.18秒4000W及可选三值条件。参数: condition。返回: CalculationSeries。异常: 模型错误。"""
        flag = ScalarValue(condition, D.BOOL) if condition is not None else ScalarValue(None, D.BOOL, False, Q.MISSING)
        return CalculationSeries(Interval(0, 180_000_000), (0, 180_000_000),
            (ScalarValue(4000., D.FLOAT64),) * 2, (True, True), 'W', conditions=(flag, flag))

    def test_separate_expiry_and_hand_coverage(self):
        """值/条件谁先到期都不改变原记录跨度，TRUE未知部分不能当FALSE。"""
        for compute, reducer in self.backends:
            for condition, v_end, c_end, energy, v_ms, known_ms, selected_ms, unknown_ms, false_ms in (
                (True,150,120,400.*2/3,150,120,120,0,0),
                (True,120,150,400.*2/3,120,150,120,30,0),
                (False,150,120,None,150,120,0,0,120),
                (True,0,None,None,0,180,0,180,0),
                (True,None,0,None,180,0,0,0,0),
                (None,None,None,None,180,0,0,0,0)):
                series = self.series(condition)
                facts_seen = []
                for retain in (True, False):
                    terms = compute(series, CalculationDefinition('energy', 'integral', series.observation),
                        step_ns=100_000_000, valid_until_ns=(None if v_end is None else v_end*10**6, None),
                        condition_valid_until_ns=(None if c_end is None else c_end*10**6, None), retain_unknown_ranges=retain)
                    total = reducer()
                    total.push_values(terms.areas, terms.valid)
                    if energy is None:
                        self.assertIsNone(total.finish('J').value)
                    else:
                        self.assertAlmostEqual(total.finish('J').value, energy)
                    facts = terms.facts
                    counts = (facts.value_valid_duration_ns, facts.condition_known_duration_ns,
                        facts.selected_duration_ns, facts.selected_value_unknown_duration_ns, facts.false_duration_ns)
                    self.assertEqual(counts, tuple(item*10**6 for item in (v_ms, known_ms, selected_ms, unknown_ms, false_ms)))
                    facts_seen.append(counts)
                    self.assertEqual(facts.ranges_retained, retain)
                    if not retain:
                        self.assertEqual((facts.value_unknown_ranges, facts.condition_unknown_ranges), ((), ()))
                        with self.assertRaisesRegex(ValueError, '未保留范围'):
                            make_conditional_integral_result(facts, total.finish('J'))
                self.assertEqual(facts_seen[0], facts_seen[1])

    def test_window_overlap_uses_original_pair(self):
        """窗口0.06—0.12占原记录对1/3，所以为133.333J，不能当完整400J。"""
        series = self.series()
        spec = CalculationDefinition('energy', 'integral', Interval(60_000_000, 120_000_000))
        for compute, reducer in self.backends:
            terms = compute(series, spec, step_ns=100_000_000, valid_until_ns=(150_000_000, None))
            total = reducer()
            total.push_values(terms.areas, terms.valid)
            self.assertAlmostEqual(total.finish('J').value, 400./3)
            actual = compute(series, spec)
            total = reducer()
            total.push_values(actual.areas, actual.valid)
            self.assertEqual(total.finish('J').value, 240.)

    def test_unchanged_default_and_invalid_new_options(self):
        """无新选项时完整原结果保持；周期不能接受合成驱动点或错误截止。"""
        series = self.series()
        spec = CalculationDefinition('energy', 'integral', series.observation)
        for compute, _ in self.backends:
            old = compute(series, spec)
            new = compute(series, spec, valid_until_ns=(None,None), condition_valid_until_ns=(None,None))
            self.assertEqual(tuple(old.areas), tuple(new.areas))
            self.assertEqual(old.facts, new.facts)
            with self.assertRaisesRegex(ValueError, '合成边界'):
                compute(replace(series, actual_value_updates=(False,True)), spec, step_ns=100)
            with self.assertRaises(TypeError):
                compute(series, spec, valid_until_ns=(None,))
            with self.assertRaises(TypeError):
                compute(series, spec, retain_unknown_ranges=0)
