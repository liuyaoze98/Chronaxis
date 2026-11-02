"""验证样本统计在共享预算内分块，保持半开边界、未知和原序均值。

只用已归一化合成点，不读文件；大预算原整块是相同数值核的分块对照，
另用全有效整数输入手算极值和均值。每次关闭核对资源归属，不更改全局预算。
"""
import unittest
from unittest.mock import patch

from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.models import Interval
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.types import SignalDType as D, QualityFlag as Q
from chronaxis.execution.record_time_calculation import RecordTimeCalculation
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import BudgetExceededError


class SampleBudgetBatchingTests(unittest.TestCase):
    """批内TTL和真假切换不会因预算切分产生额外真实样本。"""

    def run_calculation(self, operation, backend, budget_size, *, conditioned=False, missing=False):
        """计算1000个半开样本及一个右端点。

        参数: 算子、后端、共享限额及缺失/条件选择。
        返回: 结果与峰值。异常: 产品错误或资源未清零时失败。
        """
        budget = ResourceBudget(budget_size)
        # 模拟读取器仍持有1MiB，不允许统计器花用这部分预算。
        budget.reserve_ram(1048576)
        spec = CalculationDefinition('statistic', operation, Interval(0, 10000))
        owner = RecordTimeCalculation(budget, spec, 'A', D.INT64, None,
            backend=backend, batch_intervals=4096, conditioned=conditioned)
        try:
            for time in range(1001):
                absent = missing and time % 7 == 0
                value = ScalarValue(None, D.INT64, False, Q.MISSING) if absent else ScalarValue(time % 10, D.INT64)
                condition = ScalarValue(time % 3 == 0, D.BOOL)
                options = dict(conditions=(condition,), condition_valid_until_ns=(time * 10 + 8,)) if conditioned else {}
                owner.consume(((time * 10, value, time * 10 + 7 if missing else None),),
                    actual_value_updates=(True if not missing else time % 5 != 0,), **options)
            result = owner.finish()
            peak = budget.peak_ram_bytes
        finally:
            owner.close()
            self.assertEqual(budget.ram_bytes, 1048576)
            budget.release_ram(1048576)
        self.assertLessEqual(peak, budget_size)
        return result, peak

    def test_budget_split_matches_whole_block_and_hand_values(self):
        """两后端三算子保持准确值和完整质量。参数: 无。返回: None。异常: 断言失败。"""
        for backend in ('reference', 'numpy'):
            for operation, hand in (('sample_minimum', 0), ('sample_maximum', 9), ('sample_mean', 4.5)):
                for complex_case in (False, True):
                    with self.subTest(backend=backend, operation=operation, complex_case=complex_case):
                        expected, _ = self.run_calculation(operation, backend, 256 * 1024**2,
                            conditioned=complex_case, missing=complex_case)
                        actual, _ = self.run_calculation(operation, backend, 12 * 1024**2,
                            conditioned=complex_case, missing=complex_case)
                        self.assertEqual(actual, expected)
                        if not complex_case:
                            self.assertEqual(actual.value, hand)

    def test_minimum_block_failure_names_calculation_and_cleans_up(self):
        """最小工作区不足仍拒绝，不偷改预算。参数: 无。返回: None。异常: 断言失败。"""
        budget = ResourceBudget()
        spec = CalculationDefinition('peak_current', 'sample_maximum', Interval(0, 2))
        owner = RecordTimeCalculation(budget, spec, 'A', D.INT64, None)
        external = budget.memory_budget_bytes - budget.ram_bytes - 100000
        budget.reserve_ram(external)
        try:
            owner.consume(((0, ScalarValue(2, D.INT64)), (2, ScalarValue(3, D.INT64))),
                          actual_value_updates=(True, True))
            with self.assertRaisesRegex(BudgetExceededError, 'peak_current.*样本统计工作区不足'):
                owner.finish()
        finally:
            owner.close()
            self.assertEqual(budget.ram_bytes, external)
            budget.release_ram(external)

    def test_cancel_between_chunks_preserves_cleanup(self):
        """已计算第一块后取消不会交付前缀。参数: 无。返回: None。异常: 断言失败。"""
        budget = ResourceBudget(12 * 1024**2)
        owner = RecordTimeCalculation(budget,
            CalculationDefinition('maximum', 'sample_maximum', Interval(0, 1000)),
            'A', D.INT64, None, batch_intervals=4096)
        owner.consume(tuple((i, ScalarValue(i, D.INT64)) for i in range(1001)),
                      actual_value_updates=(True,) * 1001)
        original = owner._flush_block
        calls = 0
        def cancel_second():
            """第一块真实计算，第二块取消。参数: 无。返回: None。异常: KeyboardInterrupt。"""
            nonlocal calls
            calls += 1
            if calls == 2:
                raise KeyboardInterrupt('synthetic cancellation')
            return original()
        try:
            with patch.object(owner, '_flush_block', side_effect=cancel_second):
                with self.assertRaises(KeyboardInterrupt):
                    owner.finish()
            self.assertTrue(owner._failed)
            self.assertFalse(owner._finished)
        finally:
            owner.close()
        self.assertEqual(budget.ram_bytes, 0)
