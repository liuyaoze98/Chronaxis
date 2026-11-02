"""验证BUG-M2-197单条累计预付空间的实际预算、原子累计和恢复；device_label: home。

用真实ResourceBudget和LegacySumAccumulator填满共享余额，确认已付款单条计算不再
临时借款；多条先付差额且预算失败不计算、不重试、不推进顺序。默认False保留原费用。
预约和关闭前后取消只注入实际预算回调，真实owner保持恢复责任，不能抵销调用方或
另一活累计器的费用。最后用公共AnalysisRunner及新work合成BLF验证两个指标的实际接线、
同刻两条400J贡献和缺值skip；不修改RefProjects，也不把合成证据当真实十文件验收。
"""

# 大部分边界只需内存模型；真实CAN依赖仅由最后一项现有小夹具按需导入。
import unittest
from unittest.mock import patch

from chronaxis.core.models import SourceRef
from chronaxis.legacy.sum import LegacySumAccumulator, LegacySumContribution
from chronaxis.legacy.updates import LegacyDecodedUpdate
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import BudgetExceededError, ResultClosedError


class LegacySumWorkspaceTests(unittest.TestCase):
    """检查单owner实付槽，不用更改限额或人为减账使错误消失。"""

    def contribution(self, index, value=400.0):
        """构造手算已知贡献。参数: 原序号/float。返回: 真实贡献模型。异常: 原模型错误。"""
        update = LegacyDecodedUpdate(time_ns=index, source='bus', channel=0, frame_id=256,
            is_extended=False, is_fd=False, is_remote=False, is_error=False,
            source_ref=SourceRef('session', 'bus', 'Power'), sequence=index,
            evaluation_index=index, values={'Power': 4000.0})
        return LegacySumContribution(update, value)

    def owner(self, backend='reference', *, budget=None, prepay=True):
        """真实构造并登记最终清理。参数: 后端/可选共享账本/预付选项。返回: (budget,owner)。异常: 构造错误。"""
        if budget is None:
            budget = ResourceBudget(1024 * 1024)
        owner = LegacySumAccumulator(budget, 'session', 'bus', legacy_policy='explicit-v1',
            backend=backend, max_batch_rows=4, prepay_single=prepay)
        self.addCleanup(owner.close)
        return budget, owner

    def test_full_shared_budget_single_rows_need_no_extra_reservation_and_keep_order(self):
        """共享余额为零仍按1e16、-1e16、1精确顺序得1，重复原序不二次累加。

        参数: 无。返回: None。异常: 临时借款、重排、重复累计或抵销借款使测试失败。
        """
        for backend in ('reference', 'numpy'):
            with self.subTest(backend=backend):
                budget, owner = self.owner(backend)
                self.assertEqual(owner._workspace_cost, 4352)
                borrowed = budget.memory_budget_bytes - budget.ram_bytes
                budget.reserve_ram(borrowed)
                try:
                    with patch.object(budget, 'reserve_ram', wraps=budget.reserve_ram) as reserve, \
                            patch.object(budget, 'release_ram', wraps=budget.release_ram) as release:
                        owner.consume(())
                        for index, value in enumerate((1e16, -1e16, 1.0)):
                            owner.consume((self.contribution(index, value),))
                        before = owner.snapshot()
                        with self.assertRaises(ValueError):
                            owner.consume((self.contribution(2, 1.0),))
                        self.assertEqual(owner.snapshot(), before)
                    reserve.assert_not_called()
                    release.assert_not_called()
                    self.assertEqual((before.value, before.evaluation_count, before.contribution_count), (1.0, 3, 3))
                    self.assertEqual(budget.ram_bytes, budget.memory_budget_bytes)
                    owner.close()
                    self.assertEqual(budget.ram_bytes, borrowed)
                finally:
                    budget.release_ram(borrowed)
                    owner.close()
                self.assertEqual(budget.ram_bytes, 0)

    def test_multiple_rows_reserve_only_shortfall_and_never_retry_after_budget_failure(self):
        """两条需要多付256字节，满账先拒绝且不计算；补足余额后仅调用一次得800J。

        参数: 无。返回: None。异常: 超限仍计算、自动重试或多/少付差额使测试失败。
        """
        for backend in ('reference', 'numpy'):
            with self.subTest(backend=backend):
                budget, owner = self.owner(backend)
                borrowed = budget.memory_budget_bytes - budget.ram_bytes
                budget.reserve_ram(borrowed)
                pair, before = (self.contribution(0), self.contribution(1)), owner.snapshot()
                try:
                    with patch.object(owner, '_candidate', wraps=owner._candidate) as candidate:
                        with self.assertRaises(BudgetExceededError):
                            owner.consume(pair)
                        candidate.assert_not_called()
                        self.assertEqual(owner.snapshot(), before)
                        budget.release_ram(256)
                        borrowed -= 256
                        with patch.object(budget, 'reserve_ram', wraps=budget.reserve_ram) as reserve, \
                                patch.object(budget, 'release_ram', wraps=budget.release_ram) as release:
                            owner.consume(pair)
                        reserve.assert_called_once_with(256)
                        release.assert_called_once_with(256)
                        self.assertEqual(candidate.call_count, 1)
                    self.assertEqual((owner.snapshot().value, owner.snapshot().evaluation_count), (800.0, 2))
                finally:
                    budget.release_ram(borrowed)
                    owner.close()
                self.assertEqual(budget.ram_bytes, 0)

    def test_default_cost_is_unchanged_and_option_rejects_non_boolean_before_payment(self):
        """默认入口仍单次完整申请4352，预付只额外增加自有4352；0/1不冒充bool。

        参数: 无。返回: None。异常: 默认费用变化、非法选项先付款或共享费用不闭合失败。
        """
        budget = ResourceBudget(1024 * 1024)
        owner = LegacySumAccumulator(budget, 'session', 'bus', legacy_policy='explicit-v1', backend='reference')
        self.addCleanup(owner.close)
        fixed = budget.ram_bytes
        self.assertEqual(owner._workspace_cost, 0)
        with patch.object(budget, 'reserve_ram', wraps=budget.reserve_ram) as reserve, \
                patch.object(budget, 'release_ram', wraps=budget.release_ram) as release:
            owner.consume((self.contribution(0),))
        reserve.assert_called_once_with(4352)
        release.assert_called_once_with(4352)
        owner.close()
        _, prepaid = self.owner(budget=budget)
        self.assertEqual(budget.ram_bytes, fixed + 4352)
        prepaid.close()
        for value in (0, 1, None, 'yes'):
            with self.subTest(option=value), patch.object(budget, 'reserve_ram', wraps=budget.reserve_ram) as reserve:
                with self.assertRaises(TypeError):
                    self.owner(budget=budget, prepay=value)
                reserve.assert_not_called()
                self.assertEqual(budget.ram_bytes, 0)
        # 比真实固定费加单条费少一字节时，应在构造阶段拒绝并完整归还已付固定费。
        limited = ResourceBudget(777 + fixed + 4351)
        limited.reserve_ram(777)
        with self.assertRaises(BudgetExceededError):
            self.owner(budget=limited)
        self.assertEqual(limited.ram_bytes, 777)
        limited.release_ram(777)

    def test_constructor_workspace_reserve_cancel_before_and_after_returns_only_own_cost(self):
        """单条槽预约前后取消保原对象，已经支付的固定/工作槽均恢复至外部777基线。

        参数: 无。返回: None。异常: 漏费、重复归还或替换原KeyboardInterrupt失败。
        """
        for after in (False, True):
            with self.subTest(after=after):
                budget = ResourceBudget(1024 * 1024)
                budget.reserve_ram(777)
                original = budget.reserve_ram
                marker = KeyboardInterrupt('single workspace constructor')
                hits = []

                def reserve(amount):
                    """仅命中单条槽真实预约。参数: 金额。返回: 原结果。异常: 同一marker。"""
                    if amount == 4352:
                        hits.append(amount)
                        if after:
                            original(amount)
                        raise marker
                    return original(amount)

                with patch.object(budget, 'reserve_ram', side_effect=reserve):
                    with self.assertRaises(KeyboardInterrupt) as caught:
                        self.owner(budget=budget)
                self.assertIs(caught.exception, marker)
                self.assertEqual(hits, [4352])
                self.assertEqual(budget.ram_bytes, 777)
                recovery = getattr(marker, 'legacy_sum_cleanup_owner', None)
                if recovery is not None:
                    self.assertTrue(recovery.closed)
                    recovery.close()
                budget.release_ram(777)

    def test_unreturned_prepaid_owner_survives_persistent_constructor_cleanup_failure(self):
        """预付成功后取消且持续释放失败，异常携带真实owner，恢复不触碰兄弟累计器。

        参数: 无。返回: None。异常: 丢owner、误退其他费用或提前宣称关闭失败。
        """
        budget, sibling = self.owner()
        sibling.consume((self.contribution(0, 17.0),))
        baseline, sibling_snapshot = budget.ram_bytes, sibling.snapshot()
        primary, secondary = KeyboardInterrupt('workspace after reserve'), RuntimeError('persistent release')
        original, calls = budget.reserve_ram, []

        def reserve(amount):
            """真实付款后只在工作槽取消。参数: 金额。返回: None。异常: 原primary。"""
            original(amount)
            if amount == 4352:
                raise primary

        def release(amount):
            """持续阻止实际归还。参数: 金额。返回: 不返回。异常: 原secondary。"""
            calls.append(amount)
            raise secondary

        with patch.object(budget, 'reserve_ram', side_effect=reserve), \
                patch.object(budget, 'release_ram', side_effect=release):
            with self.assertRaises(KeyboardInterrupt) as caught:
                self.owner(budget=budget)
            self.assertIs(caught.exception, primary)
            owner = primary.legacy_sum_cleanup_owner
            self.assertIs(type(owner), LegacySumAccumulator)
            self.addCleanup(owner.close)
            self.assertEqual(owner._workspace_cost, 4352)
            self.assertEqual(budget.ram_bytes, baseline + owner._held_cost)
            for _ in range(3):
                with self.assertRaises(RuntimeError) as cleanup:
                    owner.close()
                self.assertIs(cleanup.exception, secondary)
                self.assertIs(secondary.legacy_sum_cleanup_owner, owner)
            self.assertGreaterEqual(len(calls), 5)
            self.assertTrue(all(amount == 4352 for amount in calls))
            self.assertFalse(owner.closed)
        owner.close()
        owner.close()
        self.assertEqual(budget.ram_bytes, baseline)
        self.assertEqual(sibling.snapshot(), sibling_snapshot)
        sibling.close()
        self.assertEqual(budget.ram_bytes, 0)

    def test_single_candidate_cancel_preserves_prepaid_space_and_original_state(self):
        """已付款单条候选取消不回收永久槽，也不提交或重试，合法后续调用只加一次。

        参数: 无。返回: None。异常: 原异常变化、状态提前提交或同槽费用丢失失败。
        """
        for backend in ('reference', 'numpy'):
            with self.subTest(backend=backend):
                budget, owner = self.owner(backend)
                baseline, before = budget.ram_bytes, owner.snapshot()
                marker = KeyboardInterrupt('single candidate cancelled')
                with patch.object(owner, '_candidate', side_effect=marker) as candidate:
                    with self.assertRaises(KeyboardInterrupt) as caught:
                        owner.consume((self.contribution(0),))
                self.assertIs(caught.exception, marker)
                self.assertIs(marker.legacy_sum_cleanup_owner, owner)
                self.assertEqual(candidate.call_count, 1)
                self.assertEqual(owner.snapshot(), before)
                self.assertEqual(budget.ram_bytes, baseline)
                owner.consume((self.contribution(0),))
                self.assertEqual((owner.snapshot().value, owner.snapshot().evaluation_count), (400.0, 1))
                owner.close()
                self.assertEqual(budget.ram_bytes, 0)

    def test_extra_workspace_reserve_and_release_cancellation_is_atomic(self):
        """多条差额预约/释放前后取消均保原状态，未释放的256仅由同owner恢复。

        参数: 无。返回: None。异常: 重算、提前提交、永久槽被误退或恢复金额错误失败。
        """
        for operation in ('reserve_ram', 'release_ram'):
            for after in (False, True):
                with self.subTest(operation=operation, after=after):
                    budget, owner = self.owner()
                    baseline, state = budget.ram_bytes, owner._state
                    marker, original = KeyboardInterrupt('extra workspace cancellation'), getattr(budget, operation)
                    calls = []

                    def fail(amount):
                        """在真实差额回调前后取消。参数: 金额。返回: 原结果。异常: 同一marker。"""
                        if amount == 256:
                            calls.append(amount)
                            if after:
                                original(amount)
                            raise marker
                        return original(amount)

                    with patch.object(budget, operation, side_effect=fail):
                        with self.assertRaises(KeyboardInterrupt) as caught:
                            owner.consume((self.contribution(0), self.contribution(1)))
                    self.assertIs(caught.exception, marker)
                    self.assertIs(marker.legacy_sum_cleanup_owner, owner)
                    self.assertIs(owner._state, state)
                    self.assertEqual(owner._workspace_cost, 4352)
                    if operation == 'release_ram' and not after:
                        self.assertGreaterEqual(len(calls), 3)
                        self.assertEqual(budget.ram_bytes, baseline + 256)
                        with self.assertRaises(ResultClosedError):
                            owner.consume((self.contribution(0),))
                    else:
                        self.assertEqual(budget.ram_bytes, baseline)
                        owner.consume((self.contribution(0), self.contribution(1)))
                        self.assertEqual((owner.snapshot().value, owner.snapshot().evaluation_count), (800.0, 2))
                    owner.close()
                    self.assertEqual(budget.ram_bytes, 0)

    def test_prepaid_close_cancel_before_after_preserves_actual_remaining_slot(self):
        """永久工作槽释放前持续失败或释放后取消，重试只还尚欠费用且不抵销外部777。

        参数: 无。返回: None。异常: 假关闭、重复归还或恢复owner变化失败。
        """
        for after in (False, True):
            with self.subTest(after=after):
                budget, owner = self.owner()
                budget.reserve_ram(777)
                original, marker, calls = budget.release_ram, KeyboardInterrupt('close prepaid'), []

                def release(amount):
                    """仅在实际永久槽归还前后取消。参数: 金额。返回: 原结果。异常: 原marker。"""
                    if amount == 4352:
                        calls.append(amount)
                        if after:
                            original(amount)
                        raise marker
                    return original(amount)

                with patch.object(budget, 'release_ram', side_effect=release):
                    for _ in range(1 if after else 3):
                        with self.assertRaises(KeyboardInterrupt) as caught:
                            owner.close()
                        self.assertIs(caught.exception, marker)
                        self.assertIs(marker.legacy_sum_cleanup_owner, owner)
                        self.assertEqual(owner._workspace_cost, 0 if after else 4352)
                        self.assertEqual(budget.ram_bytes, owner._held_cost + 777)
                    self.assertFalse(owner.closed)
                    with self.assertRaises(ResultClosedError):
                        owner.consume(())
                owner.close()
                owner.close()
                self.assertEqual(budget.ram_bytes, 777)
                self.assertEqual(len(calls), 1 if after else 3)
                budget.release_ram(777)

    def test_public_runner_prepays_each_calculation_before_full_balance_single_consumption(self):
        """真实AnalysisRunner两个指标在每次单条累计前填满余额，仍各得800J且只求值三次。

        参数: 无。返回: None。异常: 接线未预付、重复累计、缺值skip丢失或最终账不为0失败。
        """
        from chronaxis import AnalysisRunner
        import test_run_message_calculations as fixtures
        original = LegacySumAccumulator.consume
        for backend in ('reference', 'numpy'):
            with self.subTest(backend=backend):
                work, _, plan = fixtures.RunMessageCalculationTests.fixture(self, backend=backend, calculation_count=2)
                observed, snapshots = [], []

                def consume(owner, contributions):
                    """填满共享余额后透传一次真实累计。参数: 原owner/tuple。返回: 原结果。异常: 原错误。"""
                    self.assertEqual(owner._workspace_cost, 4352)
                    self.assertEqual(len(contributions), 1)
                    budget = owner._budget
                    borrowed = budget.memory_budget_bytes - budget.ram_bytes
                    budget.reserve_ram(borrowed)
                    before = owner.snapshot().evaluation_count
                    try:
                        original(owner, contributions)
                    finally:
                        budget.release_ram(borrowed)
                    self.assertEqual(owner.snapshot().evaluation_count, before + 1)
                    observed.append(owner)
                    snapshots.append(owner.snapshot())

                with patch.object(LegacySumAccumulator, 'consume', new=consume):
                    result = AnalysisRunner().run(plan, work_dir=work / 'prepaid-run')
                self.addCleanup(result.close)
                try:
                    summaries = fixtures.RunMessageCalculationTests.rows(self, result, 'summary')
                    rows = fixtures.RunMessageCalculationTests.rows(self, result, 'contributions')
                    self.assertEqual(tuple(row.value for row in summaries), (800.0, 800.0))
                    self.assertEqual(tuple(row.evaluation_count for row in snapshots[-2:]), (3, 3))
                    self.assertEqual(tuple(row.skipped_count for row in snapshots[-2:]), (1, 1))
                    self.assertEqual(len(rows), 6)
                    self.assertEqual(len(observed), 6)
                    self.assertEqual(len({id(owner) for owner in observed}), 2)
                    self.assertTrue(all(owner.closed and owner._workspace_cost == 0 for owner in observed))
                finally:
                    result.close()
                self.assertEqual(result.spool.budget.ram_bytes, 0)


if __name__ == '__main__':
    # spawn导入模块只声明测试，入口自身才运行suite。
    unittest.main()
