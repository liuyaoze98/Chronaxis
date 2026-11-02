"""验证真实历史回读构造失败后仍能取得未清理完的资源。

合成历史通过原工厂写入work；故障只注入新分析层构造和账本释放。
预期原异常保持身份，持续清理失败时公开恢复owner，恢复后关闭归还自有费用。
测试额外记录close收到的对象只为回收修复前的泄漏，不能代替生产恢复句柄。
借用的历史、原状态和调用方预算必须保持，全部工厂关闭后RAM为0。
"""

# 复用真实工厂但不导入测试类名称，避免完整发现重复计数。
import unittest
from unittest.mock import patch
import test_window_replay as real_history
from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.models import Interval
from chronaxis.execution import calculation_blocks as blocks_module
from chronaxis.execution import window_replay as replay_module


class ReplayConstructorRecoveryTests(unittest.TestCase):
    """分别检查回读者、外层分块者及嵌套失败时的恢复归属。"""

    def prepare(self, backend='numpy'):
        """创建真实封存历史并注册原工厂清理。

        参数: backend为两个实际后端之一。返回: (工厂, fixture)。异常: 原工厂错误。
        """
        helper = real_history.WindowReplayTests('runTest')
        fixture = helper.fixture(backend=backend, kind='csv')
        # 清理需要在本测试收回新owner之后执行，不能在注册时提前调用。
        self.addCleanup(self.cleanup_factory, helper)
        return helper, fixture

    def cleanup_factory(self, helper):
        """关闭原工厂并核对其原有RAM零断言。

        参数: helper为原测试工厂。返回: None。异常: 清理断言失败。
        """
        self.assertTrue(helper.doCleanups())

    def invoke(self, fixture, kind, backend='numpy'):
        """调用真实构造接口，不读取或改变历史。

        参数: fixture为真实输入，kind为replay或blocks，backend为实际执行后端。
        返回: 新owner。异常: 注入故障。
        """
        args = (fixture.history, fixture.holds._context, fixture.lease.bindings, fixture.compiled[0])
        if kind == 'replay':
            return replay_module.HistoricalWindowReplay(*args, Interval(2, 7), backend=backend)
        return blocks_module.HistoricalCalculationBlocks(*args, CalculationDefinition('area', 'integral', Interval(2, 7)), backend=backend)

    def capture_close(self, original, captured):
        """记录真实close收到的owner，生产仍调用原关闭实现。

        参数: original为原方法，captured为测试回收列表。返回: 包装方法。异常: 原故障传播。
        """
        def close(owner):
            """执行原关闭并保存测试回收入口。

            参数: owner为正在清理的实际对象。返回: None。异常: 原close错误。
            """
            if all(item is not owner for item in captured):
                captured.append(owner)
            return original(owner)
        return close

    def persistent_failure(self, kind, nested=False, backend='numpy'):
        """构造失败且释放持续取消，核对原异常与可恢复owner。

        参数: kind为外层种类，nested为分块者内回读是否失败，backend为工厂后端。
        返回: None。异常: 丢失恢复句柄或自有预算的断言失败。
        """
        _, fixture = self.prepare(backend)
        baseline, captured = fixture.budget.ram_bytes, []
        original = MemoryError('real-constructor-failure')
        replay_close = replay_module.HistoricalWindowReplay.close
        blocks_close = blocks_module.HistoricalCalculationBlocks.close
        target = (patch.object(replay_module, 'BoundaryQueries', side_effect=original)
                  if kind == 'replay' or nested else
                  patch.object(blocks_module, 'HistoricalWindowReplay', side_effect=original))
        try:
            with target, patch.object(fixture.budget, 'release_ram', side_effect=KeyboardInterrupt('persistent-release')):
                with patch.object(replay_module.HistoricalWindowReplay, 'close', self.capture_close(replay_close, captured)):
                    with patch.object(blocks_module.HistoricalCalculationBlocks, 'close', self.capture_close(blocks_close, captured)):
                        with self.assertRaises(MemoryError) as raised:
                            self.invoke(fixture, kind, backend)
            self.assertIs(raised.exception, original)
            name = 'window_replay_cleanup_owner' if kind == 'replay' else 'calculation_blocks_cleanup_owner'
            recovery = getattr(original, name, None)
            self.assertIsNotNone(recovery, '构造失败必须保留未关闭owner供调用方恢复')
            self.assertFalse(recovery.closed)
            if nested:
                self.assertIs(recovery._replay, original.window_replay_cleanup_owner)
            self.assertGreater(fixture.budget.ram_bytes, baseline)
            recovery.close()
            recovery.close()
            self.assertTrue(recovery.closed)
            self.assertEqual(fixture.budget.ram_bytes, baseline)
            self.assertEqual(fixture.state.revision, 0)
        finally:
            # 原代码没有生产句柄时仍必须收回测试资源，不让失败污染下一例。
            for owner in reversed(captured):
                owner.close()
            self.assertEqual(fixture.budget.ram_bytes, baseline)

    def test_replay_persistent_release_exposes_original_owner(self):
        """两实际后端的回读构造失败都保留原异常及资源恢复句柄。

        参数: 无。返回: None。异常: 恢复与借用资源断言失败。
        """
        for backend in ('reference', 'numpy'):
            with self.subTest(backend=backend):
                self.persistent_failure('replay', backend=backend)

    def test_blocks_persistent_release_exposes_original_owner(self):
        """外层固定空间已申请而子构造失败时，持续释放错误不能丢失它。

        参数: 无。返回: None。异常: 恢复句柄或最终RAM断言失败。
        """
        self.persistent_failure('blocks')

    def test_nested_replay_recovery_is_adopted_by_blocks(self):
        """赋值尚未完成的失败子回读者通过异常句柄交给外层继续清理。

        参数: 无。返回: None。异常: 丢子owner或借用预算断言失败。
        """
        self.persistent_failure('blocks', nested=True)

    def test_transient_cleanup_cancel_is_retried_without_changing_error(self):
        """释放前只取消一次时构造清理应重试，原MemoryError仍传播。

        参数: 无。返回: None。异常: 未重试或异常被替换断言失败。
        """
        for kind in ('replay', 'blocks'):
            with self.subTest(kind=kind):
                helper, fixture = self.prepare()
                baseline = fixture.budget.ram_bytes
                original = MemoryError('transient-constructor-failure')
                target = (patch.object(replay_module, 'BoundaryQueries', side_effect=original)
                          if kind == 'replay' else patch.object(blocks_module, 'HistoricalWindowReplay', side_effect=original))
                captured = []
                cls = replay_module.HistoricalWindowReplay if kind == 'replay' else blocks_module.HistoricalCalculationBlocks
                actual_close = cls.close
                try:
                    with target, patch.object(cls, 'close', self.capture_close(actual_close, captured)):
                        with patch.object(fixture.budget, 'release_ram', helper.cancel_once(fixture.budget.release_ram, False)):
                            with self.assertRaises(MemoryError) as raised:
                                self.invoke(fixture, kind)
                    self.assertIs(raised.exception, original)
                    self.assertEqual(fixture.budget.ram_bytes, baseline)
                    self.assertTrue(all(owner.closed for owner in captured))
                finally:
                    for owner in captured:
                        owner.close()


# unittest发现和直接运行均执行上述真实故障断言。
if __name__ == '__main__':
    unittest.main()
