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
import test_calculation_blocks as real_history
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
from chronaxis.execution import integral_reduction as module
from chronaxis.execution.integral_reduction import IntegralReduction
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

    def owner(self, backend='numpy', spec=None, budget=None, limit=4096, unit='W', observation=None):
        """创建资源 owner 并登记关闭。

        参数: 配置可覆盖默认 0—3ns/W；budget 可含调用方已有金额。返回: 新 owner。
        异常: 真实构造错误传播。
        """
        # 清理只释放新 owner，借用账本由各测试核对基线。
        spec = CalculationDefinition('area', 'integral', Interval(0, 3)) if spec is None else spec
        budget = ResourceBudget() if budget is None else budget
        result = IntegralReduction(budget, spec, spec.window if observation is None else observation,
                                   unit, 'sum-test', backend=backend, partial_limit=limit)
        self.addCleanup(result.close)
        return result

    def cancel_at(self, original, after=False, call=1):
        """在第 call 次动作前或成功后取消，之后恢复真实账本操作。

        参数: original 为原方法；after 为取消时机。返回: 故障函数。异常: 指定次取消。
        """
        # 调用计数在抛错前推进，使清理重试不会重复触发同一个故障。
        calls = 0

        def invoke(amount):
            """执行一次故障动作。参数: amount 为 bytes。返回: 原结果。异常: 一次取消。"""
            nonlocal calls
            calls += 1
            if calls == call:
                if after:
                    original(amount)
                raise KeyboardInterrupt('integral-sum-test')
            return original(amount)

        return invoke

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

    def test_owner_full_facts_sample_count_and_once_registered_unit_conversion(self):
        """三面积项的真实样本仅1，kW乘秒到J的1000因子只在最终应用。

        参数: 无。返回: None。异常: 覆盖、计数、单位或完整门槛不符。
        """
        for backend in ('reference', 'numpy'):
            spec = CalculationDefinition('area', 'integral', Interval(0, 3), output_unit='J')
            owner = self.owner(backend, spec, unit='kW')
            for index, value in enumerate((1e16, 1.0, -1e16)):
                terms = self.terms(backend, (value,), spec=spec, start=index, count=int(index == 0))
                # 单位来自真实配置；只替换冻结事实，不在核内猜单位倍率。
                terms = replace(terms, facts=replace(terms.facts, input_unit='kW'))
                owner.push(terms)
            with self.assertRaises(RuntimeError):
                _ = owner.result
            owner.finish()
            self.assertEqual(owner.result.value, 1000.0)
            self.assertEqual(owner.result.unit, 'J')
            self.assertEqual(owner.result.valid_term_count, 3)
            self.assertEqual(owner.facts.valid_sample_count, 1)
            self.assertEqual(owner.facts.value_valid_duration_ns, 3)
            owner.finish()
            with self.assertRaises(RuntimeError):
                owner.push(self.terms(backend, (1.0,), spec=spec, start=3))
            owner.close()
            with self.assertRaises(ResultClosedError):
                _ = owner.result

    def test_numeric_failure_still_finishes_full_coverage(self):
        """数值中途溢出仍消费后续完整覆盖事实，操作状态不伪装成异常失败。

        参数: 无。返回: None。异常: 覆盖遗漏或故障类型混同断言失败。
        """
        for backend in ('reference', 'numpy'):
            owner = self.owner(backend)
            spec = CalculationDefinition('area', 'integral', Interval(0, 3))
            for index, area in enumerate((1e308, 1e308, -1e308)):
                owner.push(self.terms(backend, (area,), spec=spec, start=index))
            owner.finish()
            self.assertFalse(owner.failed)
            self.assertTrue(owner.result.calculation_failed)
            self.assertEqual(owner.facts.value_valid_duration_ns, 3)
            self.assertEqual(owner.result.valid_term_count, 3)

    def test_invalid_area_product_is_unknown_while_other_area_remains_reportable(self):
        """第一段面积乘积溢出仅使该段未知，后续正常段仍可报告并保留诊断。

        参数: 无。返回: None。异常: 无效面积被当零证据或正常段被累计故障覆盖。
        """
        # 1e308保持2秒会在面积生成时溢出；正常2W保持1秒的独立手算为2J。
        times = (0, 2_000_000_000, 3_000_000_000)
        values = tuple(ScalarValue(value, D.FLOAT64) for value in (1e308, 2.0, 0.0))
        series = CalculationSeries(Interval(0, times[-1]), times, values, (True,) * 3, 'W',
                              binding_identity='sum-test')
        spec = CalculationDefinition('area', 'integral', series.observation)
        for backend in ('reference', 'numpy'):
            owner = self.owner(backend, spec)
            compute = compute_integral_terms_reference if backend == 'reference' else compute_integral_terms_numpy
            owner.push(compute(series, spec))
            owner.finish()
            # 数值归约只消费有效面积，输入计算质量及未知范围由事实独立保存。
            self.assertEqual(owner.result.value, 2.0)
            self.assertFalse(owner.result.calculation_failed)
            self.assertEqual(owner.result.valid_term_count, 1)
            self.assertEqual(owner.facts.value_valid_duration_ns, 1_000_000_000)
            self.assertEqual(owner.facts.value_unknown_ranges, (Interval(0, 2_000_000_000),))
            self.assertTrue(owner.facts.quality & Q.NONFINITE)

    def test_all_unknown_point_and_no_intersection_are_distinct(self):
        """全未知、真实点及无交集都没有面积证据，但保留不同实际范围。

        参数: 无。返回: None。异常: 覆盖范围或零证据混同断言失败。
        """
        for backend in ('reference', 'numpy'):
            owner = self.owner(backend)
            spec = CalculationDefinition('area', 'integral', Interval(0, 3))
            owner.push(self.terms(backend, (0.0,) * 3, (False,) * 3, spec))
            owner.finish()
            self.assertIsNone(owner.result.value)
            self.assertEqual(owner.facts.value_unknown_ranges, (Interval(0, 3),))
            point_spec = CalculationDefinition('area', 'integral', Interval(2, 2))
            point = self.owner(backend, point_spec)
            point.push(self.terms(backend, (), spec=point_spec, start=2))
            point.finish()
            self.assertEqual(point.facts.actual_window, Interval(2, 2))
            absent = self.owner(backend, spec, observation=Interval(4, 6))
            absent.finish()
            self.assertIsNone(absent.facts.actual_window)
            self.assertIsNone(absent.result.value)

    def test_incomplete_protocol_and_backend_errors_allow_only_close(self):
        """欠缺范围、错误后端和容量异常后的 owner 不允许交付前缀或继续。

        参数: 无。返回: None。异常: 不完整范围被接受或失败状态不封闭。
        """
        for backend in ('reference', 'numpy'):
            incomplete = self.owner(backend)
            with self.assertRaises(ValueError):
                incomplete.finish()
            wrong = self.owner(backend)
            with self.assertRaises(TypeError):
                wrong.push(self.terms('numpy' if backend == 'reference' else 'reference', (1.0,) * 3))
            limited = self.owner(backend, limit=1)
            with self.assertRaises(IntegralStateLimitError):
                limited.push(self.terms(backend, (1e16, 1.0, -1e16)))
            for owner in (incomplete, wrong, limited):
                self.assertTrue(owner.failed)
                with self.assertRaises(RuntimeError):
                    _ = owner.result
                with self.assertRaises(RuntimeError):
                    _ = owner.facts
                with self.assertRaises(RuntimeError):
                    owner.push(self.terms(backend, (1.0,) * 3))
                owner.close()
                self.assertEqual(owner._budget.ram_bytes, 0)

    def test_real_memory_csv_two_backends_all_splits_match_hand_truth(self):
        """真实更新0/5/8ns在2—7ns积分5e-9、有效3ns、样本1且未知3—5ns。

        参数: 无。返回: None。异常: 分块或后端改变手算、完整来源或预算基线。
        """
        rows = {'table': (MemoryRow(0, {'raw.a': 1}, 0), MemoryRow(5, {'raw.a': 2}, 1), MemoryRow(8, {'raw.a': 2}, 2))}
        for kind in ('memory', 'csv'):
            for backend in ('reference', 'numpy'):
                for size in (1, 2, 7):
                    with self.subTest(kind=kind, backend=backend, size=size):
                        helper = real_history.CalculationBlocksTests('runTest')
                        try:
                            fixture = helper.fixture(kind=kind, backend=backend, rows_by_source=rows, size=size)
                            baseline = fixture.budget.ram_bytes
                            spec = CalculationDefinition('area', 'integral', Interval(2, 7))
                            blocks = helper.owner(fixture, spec, backend=backend, batch_intervals=size)
                            owner = IntegralReduction(fixture.budget, spec, fixture.holds._context.domain,
                                                      '1', fixture.compiled[0].identity, backend=backend)
                            try:
                                # 每块即时生成未求和面积，使用后关闭，不保留整轴或全面积。
                                compute = compute_integral_terms_reference if backend == 'reference' else compute_integral_terms_numpy
                                for block in blocks:
                                    try:
                                        owner.push(compute(block.series, spec))
                                    finally:
                                        block.close()
                                owner.finish()
                                self.assertEqual(owner.result.value, 5e-9)
                                self.assertEqual(owner.result.unit, 's')
                                self.assertEqual((owner.facts.value_valid_duration_ns, owner.facts.valid_sample_count), (3, 1))
                                self.assertEqual(owner.facts.value_unknown_ranges, (Interval(3, 5),))
                                self.assertEqual(owner.facts.binding_identity, fixture.compiled[0].identity)
                                if kind == 'csv':
                                    self.assertTrue(any(isinstance(ref, CSVSourceRef) for ref in owner.facts.source_refs))
                                self.assertEqual(fixture.state.revision, 0)
                            finally:
                                # EOF不是close，归约和历史回读owner分别归还自有资源。
                                owner.close()
                                blocks.close()
                            self.assertEqual(fixture.budget.ram_bytes, baseline)
                        finally:
                            self.assertTrue(helper.doCleanups())

    def test_long_stream_keeps_fixed_numeric_budget_and_borrowed_baseline(self):
        """1200块精确抵消流不保存全窗面积，数字状态和借用账本保持有限。

        参数: 无。返回: None。异常: RAM随面积项数增长或关闭扣借用金额。
        """
        for backend in ('reference', 'numpy'):
            budget = ResourceBudget()
            budget.reserve_ram(1234)
            spec = CalculationDefinition('area', 'integral', Interval(0, 1200))
            owner = self.owner(backend, spec, budget)
            retained = budget.ram_bytes
            for start in range(1200):
                owner.push(self.terms(backend, (1.0 if start % 2 == 0 else -1.0,), spec=spec, start=start))
                self.assertEqual(budget.ram_bytes, retained)
                self.assertLessEqual(owner._kernel.partial_count, 1)
            owner.finish()
            self.assertEqual(owner.result.value, 0.0)
            self.assertEqual(owner.result.valid_term_count, 1200)
            owner.close()
            owner.close()
            self.assertEqual(budget.ram_bytes, 1234)

    def test_budget_rejects_before_numeric_construction_or_push(self):
        """固定和候选预算超限都发生在对应数值分配/推进之前。

        参数: 无。返回: None。异常: 越过预算执行核或账本漏收。
        """
        for backend, symbol in (('reference', 'ReferenceIntegralSum'), ('numpy', 'NumpyIntegralSum')):
            budget = ResourceBudget(1000)
            with patch.object(module, symbol) as constructor:
                with self.assertRaises(BudgetExceededError):
                    self.owner(backend, budget=budget)
                constructor.assert_not_called()
            self.assertEqual(budget.ram_bytes, 0)
            budget = ResourceBudget()
            owner = self.owner(backend, budget=budget)
            budget.memory_budget_bytes = budget.ram_bytes
            with patch.object(owner._kernel, 'push') as compute:
                with self.assertRaises(BudgetExceededError):
                    owner.push(self.terms(backend, (1.0,) * 3))
                compute.assert_not_called()
            owner.close()
            self.assertEqual(budget.ram_bytes, 0)

    def test_constructor_reserve_cancel_before_after_and_child_creation(self):
        """父与子初始申请取消前后均保留原异常，归还成功申请的自有预算。

        参数: 无。返回: None。异常: 取消被吞或借用账本泄漏。
        """
        for backend in ('reference', 'numpy'):
            for call in (1, 2):
                for after in (False, True):
                    budget = ResourceBudget()
                    budget.reserve_ram(1234)
                    with patch.object(budget, 'reserve_ram', self.cancel_at(budget.reserve_ram, after, call)):
                        with self.assertRaises(KeyboardInterrupt):
                            self.owner(backend, budget=budget)
                    self.assertEqual(budget.ram_bytes, 1234)

    def test_constructor_actual_allocation_failure_and_cleanup_cancel(self):
        """申请后构造分配失败遇到清理取消时保留原异常，并进行一次可达重试。

        参数: 无。返回: None。异常: 原错误被替换或资源留存。
        """
        for backend, symbol in (('reference', 'ReferenceIntegralSum'), ('numpy', 'NumpyIntegralSum')):
            for after in (False, True):
                budget = ResourceBudget()
                budget.reserve_ram(1234)
                original = MemoryError('kernel-allocation')
                with patch.object(module, symbol, side_effect=original), patch.object(
                        budget, 'release_ram', self.cancel_at(budget.release_ram, after)):
                    with self.assertRaises(MemoryError) as caught:
                        self.owner(backend, budget=budget)
                self.assertIs(caught.exception, original)
                self.assertEqual(budget.ram_bytes, 1234)

    def test_nested_persistent_cleanup_exposes_parent_owner_for_recovery(self):
        """子构造和两层清理持续取消时父句柄可达，恢复后一次性归还所有自有金额。

        参数: 无。返回: None。异常: 句柄丢失、原异常改变或重复扣账。
        """
        budget = ResourceBudget()
        budget.reserve_ram(1234)
        original = KeyboardInterrupt('child-reserve')
        reserve = self.cancel_at(budget.reserve_ram, True, 2)
        # 子和父的最小重试均不能成功；故障撤去后显式恢复owner。
        with patch.object(budget, 'reserve_ram', reserve), patch.object(budget, 'release_ram', side_effect=original):
            with self.assertRaises(KeyboardInterrupt) as caught:
                self.owner(budget=budget)
        owner = caught.exception.integral_reduction_cleanup_owner
        self.assertIsNotNone(owner._facts_owner)
        self.assertGreater(budget.ram_bytes, 1234)
        owner.close()
        owner.close()
        self.assertEqual(budget.ram_bytes, 1234)

    def test_push_reserve_cancel_and_release_cancel_leave_close_reachable(self):
        """父候选、子候选申请及子/父释放前后取消均封闭失败结果并可清理。

        参数: 无。返回: None。异常: 预算漏收、失败结果可读或取消被吞。
        """
        for backend in ('reference', 'numpy'):
            for method in ('reserve_ram', 'release_ram'):
                for call in (1, 2):
                    for after in (False, True):
                        budget = ResourceBudget()
                        budget.reserve_ram(1234)
                        owner = self.owner(backend, budget=budget)
                        with patch.object(budget, method, self.cancel_at(getattr(budget, method), after, call)):
                            with self.assertRaises(KeyboardInterrupt):
                                owner.push(self.terms(backend, (1.0,) * 3))
                        self.assertTrue(owner.failed)
                        with self.assertRaises(RuntimeError):
                            _ = owner.result
                        owner.close()
                        self.assertEqual(budget.ram_bytes, 1234)

    def test_close_before_after_each_owner_release_is_retryable_and_idempotent(self):
        """子/父释放前后取消按实际账本处理，重复关闭不扣调用方已有金额。

        参数: 无。返回: None。异常: 关闭结果或账本基线不符。
        """
        for call in (1, 2):
            for after in (False, True):
                budget = ResourceBudget()
                budget.reserve_ram(1234)
                owner = self.owner(budget=budget)
                with patch.object(budget, 'release_ram', self.cancel_at(budget.release_ram, after, call)):
                    with self.assertRaises(KeyboardInterrupt):
                        owner.close()
                with self.assertRaises(ResultClosedError):
                    owner.finish()
                owner.close()
                owner.close()
                self.assertTrue(owner.closed)
                self.assertEqual(budget.ram_bytes, 1234)

    def test_finish_cancellation_disallows_borrowing_complete_facts(self):
        """覆盖完成后的数值结束取消也不能借出只有事实的半成品。

        参数: 无。返回: None。异常: 未封闭失败结果或资源漏收。
        """
        owner = self.owner()
        owner.push(self.terms('numpy', (1.0,) * 3))
        with patch.object(owner._kernel, 'finish', side_effect=KeyboardInterrupt('finish')):
            with self.assertRaises(KeyboardInterrupt):
                owner.finish()
        with self.assertRaises(RuntimeError):
            _ = owner.facts
        owner.close()
        self.assertEqual(owner._budget.ram_bytes, 0)


if __name__ == '__main__':
    # 手动执行仍沿用 unittest 生命周期及登记的清理，不额外创建输出文件。
    unittest.main()
