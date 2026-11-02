"""验证真实边界查询在预算、构造交付和关闭取消处的资源所有权。

输入经memory/CSV、完整历史和已登记表达式，不替换候选时间或原因计算。
账本故障只在明确操作前/后取消，旧输出仍须可用，最终工厂清理成功/RAM归零。
复用现有工厂而不继承其TestCase，文件位于work；不测试生产驱动或旧CAN。
"""

# 模块别名不会使unittest重复发现被复用工厂；原关闭错误必须显式断言。
import unittest
from unittest.mock import patch
import test_stream_boundaries as factories
from chronaxis.execution.boundaries import BoundaryQueries


class BoundaryOwnershipTests(unittest.TestCase):
    """每个故障使用真实独立边界层，先前查询由原owner持有。"""

    def fixture(self, backend):
        """建立可查询边界的真实最新状态并登记关闭。

        参数: backend参考或NumPy。返回: 原工厂fixture。
        异常: 来源/绑定错误传播，内部关闭错误或漏账断言失败。
        """
        factory = factories.StreamBoundaryTests('runTest')
        factory.setUp()
        fixture = factory.prepare(backend=backend)
        self.addCleanup(self.cleanup_fixture, factory, fixture.budget)
        fixture.state.apply(fixture.groups[0])
        return fixture

    def cleanup_fixture(self, factory, budget):
        """断言层级清理和账本归零。参数: 原工厂/账本。返回: None。异常: AssertionError。"""
        self.assertTrue(factory.doCleanups(), '真实边界工厂关闭失败')
        self.assertEqual(budget.ram_bytes, 0)

    def fault(self, original, after):
        """只取消第一次真实账本调用。

        参数: original原方法；after是否先执行。返回: 故障回调。
        异常: 唯一KeyboardInterrupt，之后原方法正常工作。
        """
        called = False

        def invoke(amount):
            """调用原方法或取消。参数: amount bytes。返回: 原返回。异常: KeyboardInterrupt。"""
            nonlocal called
            if not called:
                called = True
                if after:
                    original(amount)
                raise KeyboardInterrupt('boundary-owner-budget')
            return original(amount)

        return invoke

    def test_result_and_owner_release_cancel_before_and_after(self):
        """结果/固定owner释放前后取消均只抵销一次，且保留上游。

        参数: 无。返回: None。异常: 关闭状态/金额/清理错误断言失败。
        """
        for backend in ('reference', 'numpy'):
            for after in (False, True):
                fixture = self.fixture(backend)
                result = fixture.boundaries.query_next(fixture.compiled[0], after_ns=0)
                before, cost = fixture.budget.ram_bytes, result._cost
                with patch.object(fixture.budget, 'release_ram', side_effect=self.fault(fixture.budget.release_ram, after)):
                    with self.assertRaises(KeyboardInterrupt):
                        result.close()
                self.assertEqual(result.closed, after)
                self.assertEqual(fixture.budget.ram_bytes, before - cost if after else before)
                result.close()
                before, cost = fixture.budget.ram_bytes, fixture.boundaries._fixed_cost
                with patch.object(fixture.budget, 'release_ram', side_effect=self.fault(fixture.budget.release_ram, after)):
                    with self.assertRaises(KeyboardInterrupt):
                        fixture.boundaries.close()
                self.assertEqual(fixture.boundaries.closed, after)
                self.assertEqual(fixture.budget.ram_bytes, before - cost if after else before)
                fixture.boundaries.close()
                self.assertFalse(fixture.expressions.closed)

    def test_query_and_constructor_reserve_cancel_keeps_old_results(self):
        """查询/构造申请前后取消不漏账，不破坏此前边界。

        参数: 无。返回: None。异常: 取消后的金额/登记或旧输出错误断言失败。
        """
        for backend in ('reference', 'numpy'):
            fixture = self.fixture(backend)
            old = fixture.boundaries.query_next(fixture.compiled[0], after_ns=0)
            baseline = fixture.budget.ram_bytes
            for constructor in (False, True):
                for after in (False, True):
                    with patch.object(fixture.budget, 'reserve_ram', side_effect=self.fault(fixture.budget.reserve_ram, after)):
                        with self.assertRaises(KeyboardInterrupt):
                            if constructor:
                                BoundaryQueries(fixture.expressions)
                            else:
                                fixture.boundaries.query_next(fixture.compiled[0], after_ns=0)
                    self.assertEqual(fixture.budget.ram_bytes, baseline)
                    self.assertEqual(set(fixture.boundaries._results), {old})
                    self.assertEqual(old.time_ns, 3)
            old.close()

    def test_partial_registration_and_delivery_cancel_remove_only_new_result(self):
        """结果构造交付/部分登记后取消只撤销新查询。

        参数: 无。返回: None。异常: 孤儿登记或旧输出被关闭断言失败。
        """
        for backend in ('reference', 'numpy'):
            fixture = self.fixture(backend)
            old = fixture.boundaries.query_next(fixture.compiled[0], after_ns=0)
            baseline = fixture.budget.ram_bytes
            original = fixture.boundaries._register

            def cancel_delivery(*args):
                """原构造后取消。参数: 原参数。返回: 无。异常: KeyboardInterrupt。"""
                original(*args)
                raise KeyboardInterrupt('boundary-owner-delivery')

            class CancelInstall(set):
                """保留旧登记，只在新项已经安装后取消。"""

                def add(self, result):
                    """先安装再取消。参数: 新结果。返回: 无。异常: KeyboardInterrupt。"""
                    super().add(result)
                    raise KeyboardInterrupt('boundary-owner-install')

            for registration in (False, True):
                context = patch.object(fixture.boundaries, '_results', CancelInstall({old})) if registration else patch.object(
                    fixture.boundaries, '_register', side_effect=cancel_delivery)
                with context:
                    with self.assertRaises(KeyboardInterrupt):
                        fixture.boundaries.query_next(fixture.compiled[0], after_ns=0)
                    self.assertEqual(set(fixture.boundaries._results), {old})
                self.assertEqual(fixture.budget.ram_bytes, baseline)
                self.assertEqual(old.time_ns, 3)
            old.close()

    def test_terminal_none_and_detach_cancel_leave_retryable_owner(self):
        """域末None抵销临时申请，脱离登记取消不重复释放。

        参数: 无。返回: None。异常: None漏账、关闭孤儿或重试重复扣账断言失败。
        """
        for backend in ('reference', 'numpy'):
            fixture = self.fixture(backend)
            baseline = fixture.budget.ram_bytes
            self.assertIsNone(fixture.boundaries.query_next(fixture.compiled[0], after_ns=8))
            self.assertEqual(fixture.budget.ram_bytes, baseline)
            result = fixture.boundaries.query_next(fixture.compiled[0], after_ns=0)
            # 脱离失败发生在账本已抵销之后，结果先关闭，owner重试只清理登记。
            class CancelDiscard(set):
                """首次脱离操作前取消，owner随后可重试同一登记。"""

                cancelled = False  # 只注入一次取消，不替owner完成关闭。

                def discard(self, item):
                    """脱离原集合或首次取消。参数: 结果。返回: None。异常: KeyboardInterrupt。"""
                    if not self.cancelled:
                        self.cancelled = True
                        raise KeyboardInterrupt('boundary-detach')
                    super().discard(item)

            fixture.boundaries._results = CancelDiscard({result})
            with self.assertRaises(KeyboardInterrupt):
                result.close()
            self.assertTrue(result.closed)
            fixture.boundaries.close()
            self.assertTrue(fixture.boundaries.closed)
