"""验证条件积分事实的连续前缀、两类未知计费和失败后的关闭。

输入为手算的纳秒块与明确的TRUE/FALSE/UNKNOWN证据；数值归约使用已验收的
两条独立误差内核。测试不以另一个后端当真值，不读取历史快照或写生产数据。
候选预算、构造分配和申请/释放取消在新owner处注入，borrowed金额始终保留。
真实历史与独立面积核分别由对应专项覆盖，这里只验证新整窗协议和所有权。
"""

# 标准库提供故障注入；NumPy仅在数组模型测试中创建真实只读输入。
from dataclasses import replace
import unittest
from unittest.mock import patch
import numpy as np
from chronaxis.core.conditional_integral_terms import ConditionalIntegralFacts, ReferenceConditionalIntegralTerms
from chronaxis.core.conditional_integral_terms_numpy import NumpyConditionalIntegralTerms
from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.models import Interval, SourceRef
from chronaxis.core.types import QualityFlag as Q
from chronaxis.execution import conditional_integral_facts as module
from chronaxis.execution.conditional_integral_reduction import ConditionalIntegralReduction
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import BudgetExceededError, ResultClosedError


class ConditionalIntegralFactsTests(unittest.TestCase):
    """持有测试owner并在所有故障恢复后核对共享账本基线。"""

    def facts(self, spec, left, right, mode='true', refs=()):
        """按单一输入情形构造完整块事实。

        参数: spec为原请求，left/right为ns，mode区分TRUE、FALSE、UNKNOWN、TRUE但值缺失，refs完整定位。
        返回: 冻结事实。异常: 模型矛盾直接传播，不在夹具中纠正。
        """
        # TRUE无效值与条件UNKNOWN分别保留，FALSE时值也可缺失。
        duration = right - left
        valid_value = duration if mode in ('true', 'unknown') else 0
        known = 0 if mode == 'unknown' else duration
        selected = duration if mode == 'true' else 0
        selected_unknown = duration if mode == 'bad' else 0
        false = duration if mode == 'false' else 0
        value_unknown = () if valid_value or duration == 0 else (Interval(left, right),)
        condition_unknown = (Interval(left, right),) if mode == 'unknown' and duration else ()
        return ConditionalIntegralFacts(spec, Interval(left, right), valid_value, known,
            selected, selected_unknown, false, int(selected > 0), value_unknown,
            condition_unknown, Q.MISSING if value_unknown or condition_unknown else Q.NONE,
            'W', 'actual-binding', refs)

    def owner(self, spec=None, observation=None, budget=None):
        """建立并登记新事实owner。参数: 可覆盖原请求/观测/账本。返回: owner。异常: 构造失败。"""
        # 默认四纳秒请求便于逐整数时间点手算；清理登记在构造成功后才建立。
        spec = CalculationDefinition('energy', 'integral', Interval(0, 4)) if spec is None else spec
        budget = ResourceBudget() if budget is None else budget
        owner = module.ConditionalIntegralFactsAccumulator(budget, spec,
            spec.window if observation is None else observation, 'W', 'actual-binding')
        self.addCleanup(owner.close)
        return owner

    def cancel_once(self, original, after=False):
        """生成一次前后取消。参数: 原方法/after。返回: 可调用故障。异常: KeyboardInterrupt一次。"""
        # 闭包只取消第一笔动作，后续恢复必须继续使用实际账本。
        calls = 0
        def invoke(amount):
            """在指定扣账位置取消。参数: amount。返回: 原方法结果。异常: 首次KeyboardInterrupt。"""
            # 申请/释放前取消尚未改变账目；成功后取消已经改变，owner需以实际增量收尾。
            nonlocal calls
            calls += 1
            if calls == 1 and not after:
                raise KeyboardInterrupt('before')
            result = original(amount)
            if calls == 1:
                raise KeyboardInterrupt('after')
            return result
        return invoke

    def test_mixed_truth_preserves_independent_partitions_and_complete_refs(self):
        """四个1ns块分别TRUE/FALSE/UNKNOWN/TRUE无值，完整分区按手算累计。

        参数: 无。返回: None。异常: 覆盖、真假、样本或来源合并与手算不一致。
        """
        # 四个完整状态的独立分区不能由面积或另一被测后端反推。
        owner = self.owner()
        refs = tuple(SourceRef('session', 'table', 'raw.' + str(index)) for index in range(4))
        for index, mode in enumerate(('true', 'false', 'unknown', 'bad')):
            owner.push(self.facts(owner._spec, index, index + 1, mode, (refs[index], refs[index])))
        # finish前不能借出前缀；完成后按手算分别核对覆盖和完整来源的去重次序。
        with self.assertRaises(RuntimeError):
            _ = owner.facts
        owner.finish()
        facts = owner.facts
        self.assertEqual((facts.value_valid_duration_ns, facts.condition_known_duration_ns,
            facts.selected_duration_ns, facts.selected_value_unknown_duration_ns,
            facts.false_duration_ns, facts.valid_sample_count), (2, 3, 1, 1, 1, 1))
        self.assertEqual(facts.value_unknown_ranges, (Interval(1, 2), Interval(3, 4)))
        self.assertEqual(facts.condition_unknown_ranges, (Interval(2, 3),))
        self.assertEqual(facts.source_refs, refs)
        # 关闭归还自有金额并收回借用访问；不能把清空引用当成尚可读取的结果。
        owner.close()
        self.assertEqual(owner._budget.ram_bytes, 0)
        with self.assertRaises(ResultClosedError):
            _ = owner.facts

    def test_adjacent_condition_unknown_merges_and_known_stream_ram_is_constant(self):
        """跨块条件UNKNOWN相邻合并，长UNKNOWN流不保留轴和面积。

        参数: 无。返回: None。异常: 范围跨有效洞合并或固定状态随流长度增长。
        """
        # 每块值有效而条件未知，只应增长一个连续未知段而不增长时间轴。
        spec = CalculationDefinition('energy', 'integral', Interval(0, 80))
        owner = self.owner(spec)
        costs = []
        for left in range(80):
            owner.push(self.facts(spec, left, left + 1, 'unknown'))
            costs.append(owner._budget.ram_bytes)
        owner.finish()
        # 连续UNKNOWN紧凑为一段，计费稳定；不因没有选中面积变为FALSE。
        self.assertEqual(owner.facts.condition_unknown_ranges, (Interval(0, 80),))
        self.assertEqual(owner.facts.selected_duration_ns, 0)
        self.assertEqual(len(set(costs)), 1)
        self.assertFalse(hasattr(owner, '_areas'))
        self.assertFalse(hasattr(owner, '_times'))

    def test_incomplete_gap_identity_and_point_protocol_fail_closed(self):
        """完整目标不能由前缀猜测，点必须真实到达且身份/连续性不可混用。

        参数: 无。返回: None。异常: 不完整、错身份或缺口被接受。
        """
        # 完整目标已固定，仅有第一块不能猜测EOF；失败后只允许显式关闭。
        owner = self.owner()
        owner.push(self.facts(owner._spec, 0, 1))
        with self.assertRaises(ValueError):
            owner.finish()
        self.assertTrue(owner.failed)
        # 缺口和另一绑定分别违反连续性及身份门槛，不应被错误归约合并。
        for first in (1, 0):
            owner = self.owner()
            facts = self.facts(owner._spec, first, 2)
            if first == 0:
                facts = replace(facts, binding_identity='another')
            with self.assertRaises(ValueError):
                owner.push(facts)
            self.assertTrue(owner.failed)
        # 与请求相接仍是实际点，必须收到点事实；完全域外则可直接无观测结束。
        point = self.owner(observation=Interval(4, 4))
        with self.assertRaises(ValueError):
            point.finish()
        point = self.owner(observation=Interval(4, 4))
        point.push(self.facts(point._spec, 4, 4))
        point.finish()
        self.assertEqual(point.facts.actual_window, Interval(4, 4))
        absent = self.owner(observation=Interval(5, 5))
        absent.finish()
        self.assertIsNone(absent.facts.actual_window)

    def test_budget_precedes_candidate_and_disjoint_condition_ranges_are_not_dropped(self):
        """条件未知诊断单独计费；候选拒绝在预算前分配或静默截断。

        参数: 无。返回: None。异常: 预算检查顺序错误或丢诊断后假完成。
        """
        # 收紧到当前持有金额，候选分配函数应在任何调用前被预算门槛挡住。
        budget = ResourceBudget()
        owner = self.owner(budget=budget)
        block = self.facts(owner._spec, 0, 1, 'unknown')
        budget.memory_budget_bytes = budget.ram_bytes
        with patch.object(module, '_join_unknown', side_effect=AssertionError('allocated')) as allocate:
            with self.assertRaises(BudgetExceededError):
                owner.push(block)
            allocate.assert_not_called()
        owner.close()
        self.assertEqual(budget.ram_bytes, 0)
        # 第二个独立owner已经持有一段条件未知，超限后原前缀及诊断必须保留供关闭。
        spec = CalculationDefinition('energy', 'integral', Interval(0, 40))
        budget = ResourceBudget()
        owner = self.owner(spec, budget=budget)
        owner.push(self.facts(spec, 0, 1, 'unknown'))
        # 保留旧未知与候选峰值需要更多费用，随后收紧到当前费用只允许显式失败。
        budget.memory_budget_bytes = budget.ram_bytes
        with self.assertRaises(BudgetExceededError):
            owner.push(self.facts(spec, 1, 2, 'true'))
        self.assertEqual(owner._state.condition_unknown_ranges, (Interval(0, 1),))
        owner.close()
        self.assertEqual(budget.ram_bytes, 0)

    def test_constructor_persistent_cleanup_keeps_original_exception_and_recovery_owner(self):
        """构造分配失败且释放持续取消时，原MemoryError仍携带可恢复owner。

        参数: 无。返回: None。异常: 清理覆盖原错、金额丢失或恢复后重复扣账。
        """
        # 321字节属于调用方；新冻结状态分配和清理都失败时，只能由恢复owner归还新增部分。
        budget = ResourceBudget()
        budget.reserve_ram(321)
        error = MemoryError('facts-allocation')
        with patch.object(module, '_unique_refs', side_effect=error):
            with patch.object(budget, 'release_ram', side_effect=KeyboardInterrupt('cleanup')):
                with self.assertRaises(MemoryError) as raised:
                    self.owner(budget=budget)
        self.assertIs(raised.exception, error)
        # 原异常必须保留恢复句柄，清理错误不能替代它；幂等关闭不能侵占借用金额。
        recovered = error.conditional_integral_facts_cleanup_owner
        recovered.close()
        recovered.close()
        self.assertEqual(budget.ram_bytes, 321)
        self.assertTrue(recovered.closed)
        budget.release_ram(321)

    def test_push_and_close_cancel_before_after_preserve_borrowed_amount(self):
        """候选申请/释放和最终关闭的前后取消均只归还本owner金额。

        参数: 无。返回: None。异常: 取消后不能重试、错误公开前缀或重复扣账。
        """
        # 每次建立新owner，隔离四种申请/释放前后取消；取消的前缀不开放为完整事实。
        for name in ('reserve_ram', 'release_ram'):
            for after in (False, True):
                budget = ResourceBudget()
                budget.reserve_ram(123)
                owner = self.owner(budget=budget)
                with patch.object(budget, name, side_effect=self.cancel_once(getattr(budget, name), after)):
                    with self.assertRaises(KeyboardInterrupt):
                        owner.push(self.facts(owner._spec, 0, 1))
                self.assertTrue(owner.failed)
                owner.close()
                self.assertEqual(budget.ram_bytes, 123)
                budget.release_ram(123)
        # 最终关闭另行核对：释放后取消已还款，重试不得再次扣同一笔。
        for after in (False, True):
            budget = ResourceBudget()
            budget.reserve_ram(456)
            owner = self.owner(budget=budget)
            with patch.object(budget, 'release_ram', side_effect=self.cancel_once(budget.release_ram, after)):
                with self.assertRaises(KeyboardInterrupt):
                    owner.close()
            owner.close()
            owner.close()
            self.assertEqual(budget.ram_bytes, 456)
            budget.release_ram(456)

    def test_reduction_both_backends_preserve_valid_zero_and_false_evidence(self):
        """有效零面积是真实证据，FALSE值缺失只影响值覆盖，不影响完整已知条件。

        参数: 无。返回: None。异常: 数字空和代替选择、后端/事实连接不一致。
        """
        # 两后端分别消费真实tuple或只读数组，真值直接来自一个有效零项和一段FALSE。
        spec = CalculationDefinition('energy', 'integral', Interval(0, 2))
        for backend in ('reference', 'numpy'):
            budget = ResourceBudget()
            owner = ConditionalIntegralReduction(budget, spec, spec.window, 'W', 'actual-binding', backend=backend)
            self.addCleanup(owner.close)
            # FALSE值未知保持False面积掩码，TRUE的合法零有一个正常积分项。
            for index, mode in enumerate(('true', 'false')):
                facts = self.facts(spec, index, index + 1, mode)
                if backend == 'reference':
                    terms = ReferenceConditionalIntegralTerms((0.0,), (mode == 'true',), facts)
                else:
                    values = np.array([0.0], dtype=np.float64)
                    valid = np.array([mode == 'true'], dtype=bool)
                    values.setflags(write=False)
                    valid.setflags(write=False)
                    terms = NumpyConditionalIntegralTerms(values, valid, facts)
                owner.push(terms)
            # 只有覆盖完整后借出数值；有效零与无有效项的None不能混淆。
            owner.finish()
            self.assertEqual((owner.result.value, owner.result.valid_term_count), (0.0, 1))
            self.assertEqual((owner.facts.false_duration_ns, owner.facts.condition_known_duration_ns), (1, 2))
            owner.close()
            self.assertEqual(budget.ram_bytes, 0)

    def test_reduction_wrong_backend_and_premature_finish_hide_all_prefixes(self):
        """错误面积模型和前缀EOF均不能借出最终数值或事实。

        参数: 无。返回: None。异常: 错误后端、未覆盖目标被假报完整。
        """
        # 错后端和未收到完整观测分别独立失败，不能读取另一情形留下的前缀。
        spec = CalculationDefinition('energy', 'integral', Interval(0, 2))
        for wrong_backend in (True, False):
            budget = ResourceBudget()
            owner = ConditionalIntegralReduction(budget, spec, spec.window, 'W', 'actual-binding')
            self.addCleanup(owner.close)
            if wrong_backend:
                terms = ReferenceConditionalIntegralTerms((1.0,), (True,), self.facts(spec, 0, 1))
                with self.assertRaises(TypeError):
                    owner.push(terms)
            else:
                with self.assertRaises(ValueError):
                    owner.finish()
            self.assertTrue(owner.failed)
            # 所有失败都只能关闭，账本清理不能受错误输入影响。
            with self.assertRaises(RuntimeError):
                _ = owner.result
            owner.close()
            self.assertEqual(budget.ram_bytes, 0)
