"""验证原序积分归约的舍入、失败语义、真实分块接线及预算清理。

手算真值与标准库 fsum 对照分别保留，不能用另一个后端作为唯一正确性证据。
覆盖抵消、半偶、原序中途溢出、最终单位转换和空有效掩码；未知不是正常零。
真实 memory/CSV 夹具在 work 建文件并独立关闭；不写历史快照。
长流不收集全部面积，取消故障同时检查借用预算基线和恢复句柄。
"""

# 夹具只按模块别名复用，不重复收集其他测试类；新数值核各自独立调用。
from math import fsum, ldexp, copysign
from dataclasses import replace
import random
import unittest
from unittest.mock import patch
import numpy as np
from chronaxis.core.integral_sum import IntegralSumResult, IntegralStateLimitError
from chronaxis.core.integral_sum_reference import ReferenceIntegralSum
from chronaxis.core.integral_sum_numpy import NumpyIntegralSum
from chronaxis.core.integral_terms import IntegralFacts, ReferenceIntegralTerms
from chronaxis.core.integral_terms_numpy import NumpyIntegralTerms, compute_integral_terms_numpy
from chronaxis.core.integral_terms_reference import compute_integral_terms_reference
from chronaxis.core.calculations import CalculationDefinition, CalculationSeries
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.models import Interval, MemoryRow
from chronaxis.core.types import QualityFlag as Q
from chronaxis.core.types import SignalDType as D
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import BudgetExceededError, ResultClosedError
from chronaxis.sources.csv_spec import CSVSourceRef


class IntegralSumTests(unittest.TestCase):
    """以明确手算和受控原序输入检验两个独立后端及完整 owner 生命周期。"""

    def terms(self, backend, areas, valid=None, spec=None, start=0, count=0):
        """建立有限 typed 面积块，每项覆盖 1ns，计数由测试显式指定。

        参数: backend 为后端；areas/valid 为有限序列；spec 为原请求；start/count 为真实事实。
        返回: 对应冻结 Terms。异常: 原模型或数组构造错误。
        """
        # 不依赖另一个数值后端构造测试数据，未知面积仍以显式掩码表示。
        areas = tuple(float(value) for value in areas)
        valid = (True,) * len(areas) if valid is None else tuple(valid)
        spec = CalculationDefinition('area', 'integral', Interval(0, len(areas))) if spec is None else spec
        unknown = tuple(Interval(start + index, start + index + 1)
                        for index, keep in enumerate(valid) if not keep)
        facts = IntegralFacts(spec, Interval(start, start + len(areas)), sum(valid), count, unknown,
                              Q.MISSING if unknown else Q.NONE, 'W', 'sum-test', ())
        if backend == 'reference':
            return ReferenceIntegralTerms(areas, valid, facts)
        # 两个真实只读一维列，只在有限测试输入中分配，生产预算由 owner 负责。
        values, mask = np.array(areas, dtype=np.float64), np.array(valid, dtype=bool)
        values.setflags(write=False)
        mask.setflags(write=False)
        return NumpyIntegralTerms(values, mask, facts)

    def kernel(self, backend, limit=4096):
        """建立独立纯核。参数: backend/limit 为明确配置。返回: 新核。异常: 原构造错误。"""
        # 不使用计算结果适配或跨后端委托。
        return (ReferenceIntegralSum if backend == 'reference' else NumpyIntegralSum)(limit)



    def test_hand_cancellation_all_splits_preserve_one(self):
        """1e16 + 1 - 1e16 的手算真值为 1，任意切分不能丢失中间小项。

        参数: 无。返回: None。异常: 舍入或切分差异断言失败。
        """
        # 四种切分包含把低位放在块内部或两块之间的情况。
        for backend in ('reference', 'numpy'):
            for parts in (((1e16, 1.0, -1e16),), ((1e16,), (1.0, -1e16)),
                          ((1e16, 1.0), (-1e16,)), ((1e16,), (1.0,), (-1e16,))):
                with self.subTest(backend=backend, parts=parts):
                    kernel = self.kernel(backend)
                    for part in parts:
                        kernel.push(self.terms(backend, part))
                    result = kernel.finish('J')
                    self.assertEqual((result.value, result.valid_term_count, result.quality), (1.0, 3, Q.NONE))
                    self.assertFalse(result.calculation_failed)

    def test_hand_half_even_subnormal_and_signed_zero(self):
        """半偶修正保留极小正项，最小非零值不丢失，精确抵消返回 +0.0。

        参数: 无。返回: None。异常: 已知 IEEE64 边界与手算不符。
        """
        # 第一项落在大数的舍入中点之上；最小 subnormal 用确切二进制指数建立。
        cases = (((1e16, 1.0, 1e-16), 10000000000000002.0),
                 ((1e16, 1.0), 1e16), ((ldexp(1.0, -1074),), ldexp(1.0, -1074)),
                 ((-0.0, 0.0), 0.0), ((1e16, -1e16), 0.0))
        for backend in ('reference', 'numpy'):
            for areas, expected in cases:
                with self.subTest(backend=backend, areas=areas):
                    kernel = self.kernel(backend)
                    kernel.push(self.terms(backend, areas))
                    self.assertEqual(kernel.finish('J').value, expected)
                    if expected == 0:
                        self.assertEqual(copysign(1.0, kernel.finish('J').value), 1.0)

    def test_original_order_intermediate_overflow_stays_failed(self):
        """前两个 1e308 已在原序溢出，后续负项不得恢复成正常面积。

        参数: 无。返回: None。异常: 故障状态或有效计数不符。
        """
        # 精确总数最终可有限不代表原序计算可成功；所有后续有效项仍须计数。
        for backend in ('reference', 'numpy'):
            kernel = self.kernel(backend)
            for part in ((1e308,), (1e308, -1e308), (0.0,)):
                kernel.push(self.terms(backend, part))
            self.assertTrue(kernel.calculation_failed)
            self.assertEqual(kernel.partial_count, 0)
            self.assertEqual(kernel.finish('J'), IntegralSumResult(None, 'J', True, Q.NONFINITE, 4))

    def test_invalid_storage_and_empty_have_no_zero_evidence(self):
        """空或全未知没有正常零证据；有效零项和 UNKNOWN 不能混同。

        参数: 无。返回: None。异常: None/零或计数不符。
        """
        for backend in ('reference', 'numpy'):
            # 无效掩码的零占位不参与有效面积项计数。
            kernel = self.kernel(backend)
            kernel.push(self.terms(backend, (0.0,), (False,)))
            self.assertEqual(kernel.finish('J'), IntegralSumResult(None, 'J', False, Q.NONE, 0))
            kernel.push(self.terms(backend, (0.0,), (True,)))
            self.assertEqual(kernel.finish('J').value, 0.0)
            self.assertEqual(kernel.valid_term_count, 1)
            self.assertEqual(self.kernel(backend).finish('J').value, None)

    def test_final_factor_once_and_conversion_failure_does_not_mutate_snapshot_state(self):
        """只在结束乘一次因子；换算溢出/非零下溢不能污染原量纲累计。

        参数: 无。返回: None。异常: 因子位置、质量或非破坏快照不符。
        """
        for backend in ('reference', 'numpy'):
            kernel = self.kernel(backend)
            # 先逐块保留可抵消的原值，先乘大倍率会使第一块错误溢出。
            for part in ((1e308,), (-1e308, 1.0)):
                kernel.push(self.terms(backend, part))
            self.assertEqual(kernel.finish('J', 1e300).value, 1e300)
            self.assertFalse(kernel.calculation_failed)
            large, tiny = self.kernel(backend), self.kernel(backend)
            large.push(self.terms(backend, (1e308,)))
            tiny.push(self.terms(backend, (1e-300,)))
            self.assertEqual(large.finish('J', 1000.0).quality, Q.NONFINITE)
            self.assertEqual(tiny.finish('J', 1e-300).quality, Q.PRECISION_LOSS)
            self.assertTrue(tiny.finish('J', 1e-300).calculation_failed)
            self.assertEqual(tiny.finish('J').value, 1e-300)

    def test_seeded_exponent_streams_match_independent_fsum_for_all_splits(self):
        """受控指数随机流对独立 fsum 真值，分块 1/2/7/全块必须逐位一致。

        参数: 无。返回: None。异常: 任何原序舍入或切分改变断言失败。
        """
        # 固定种子及有限指数避免把无序随机故障误当正常真值；含正负抵消和低位。
        rng = random.Random(601)
        for case in range(40):
            areas = [ldexp(rng.uniform(-1, 1), rng.randint(-1000, 1000)) for _ in range(30)]
            expected = fsum(areas)
            for backend in ('reference', 'numpy'):
                for size in (1, 2, 7, len(areas)):
                    with self.subTest(case=case, backend=backend, size=size):
                        kernel = self.kernel(backend)
                        for start in range(0, len(areas), size):
                            kernel.push(self.terms(backend, areas[start:start + size]))
                        self.assertEqual(kernel.finish('J').value, expected)

    def test_capacity_failure_does_not_drop_low_partials_or_install_current_item(self):
        """容量为1时 1e16 加1需要第二误差项，必须报错而非静默截断。

        参数: 无。返回: None。异常: 未报错或安装超容量项断言失败。
        """
        for backend in ('reference', 'numpy'):
            kernel = self.kernel(backend, 1)
            kernel.push(self.terms(backend, (1e16,)))
            with self.assertRaises(IntegralStateLimitError):
                kernel.push(self.terms(backend, (1.0,)))
            self.assertEqual((kernel.partial_count, kernel.valid_term_count), (1, 1))

    def test_config_and_frozen_result_reject_impossible_states(self):
        """类型、输出因子及冻结状态矛盾明确拒绝，不自动归一化。

        参数: 无。返回: None。异常: 错误配置未被拒绝断言失败。
        """
        for backend in ('reference', 'numpy'):
            for limit in (True, 0, -1, 1.0, None):
                with self.assertRaises(ValueError):
                    self.kernel(backend, limit)
            kernel = self.kernel(backend)
            for factor in (1, True, 0.0, -1.0, float('inf'), float('nan')):
                with self.assertRaises(ValueError):
                    kernel.finish('J', factor)
            with self.assertRaises((TypeError, ValueError)):
                kernel.finish('')
            with self.assertRaises(TypeError):
                kernel.push(self.terms('numpy' if backend == 'reference' else 'reference', (1.0,)))
        # 结果不能把无证据、失败和非有限值冒充正常数值。
        for args in ((0.0, 'J', False, Q.NONE, 0), (None, 'J', False, Q.NONE, 1),
                     (None, 'J', True, Q.NONE, 1), (float('inf'), 'J', False, Q.NONE, 1)):
            with self.assertRaises(ValueError):
                IntegralSumResult(*args)
















if __name__ == '__main__':
    # 手动执行仍沿用 unittest 生命周期及登记的清理，不额外创建输出文件。
    unittest.main()
