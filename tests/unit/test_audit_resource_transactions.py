"""核对最新信号状态在实际预约或转账后取消时的事务与预算归属。

使用真实共享账本和小型原记录，不启动文件工作进程。旧快照与其他所有者费用
必须保持不变，失败后的状态仍能按明确协议继续或关闭。
"""
import unittest
from unittest.mock import patch
import test_stream_state as state_facts
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.types import SignalDType
from chronaxis.execution.groups import DecodedTimeGroup
from chronaxis.execution.state import LatestSignalState
from chronaxis.results.budget import ResourceBudget


class AfterEffectOnce:
    """只在首次真实操作已经成功后抛错，后续调用继续使用原方法。"""

    def __init__(self, original, error):
        """保存实际调用和异常对象。参数: 原方法/异常。返回: 新注入器。异常: 无。"""
        self.original, self.error, self.fired = original, error, False

    def __call__(self, *args, **kwargs):
        """先产生真实效果再取消。参数: 原参数。返回: 原返回。异常: 首次指定异常。"""
        result = self.original(*args, **kwargs)
        if not self.fired:
            self.fired = True
            raise self.error
        return result


class StateResourceTransactionsTests(unittest.TestCase):
    """补齐 apply 的事务边界，既有测试已经覆盖构造和 close 的同类取消。"""

    def state(self):
        """建立独立小账本与声明。参数: 无。返回: 状态/声明。异常: 原构造错误。"""
        definition = SignalDefinition('a', 'table', 'raw.a', SignalDType.FLOAT64, 'A', 3)
        state = LatestSignalState(ResourceBudget(), (definition,), 'session')
        return state, definition

    def test_apply_reserve_after_cancel_preserves_old_state_and_balance(self):
        """申请已实际成功后取消，旧状态和旧账本保持，关闭不遗留临时费用。"""
        state, definition = self.state()
        baseline = state.budget.ram_bytes
        error = KeyboardInterrupt('apply reserve already recorded')
        fault = AfterEffectOnce(state.budget.reserve_ram, error)
        group = DecodedTimeGroup(0, (state_facts.make_sample(definition, 0, 0, 1.0),))
        with patch.object(state.budget, 'reserve_ram', new=fault):
            with self.assertRaises(KeyboardInterrupt) as caught:
                state.apply(group)
        self.assertTrue(fault.fired)
        self.assertIs(caught.exception, error)
        self.assertIsNone(state.get('a'))
        self.assertEqual(state.revision, 0)
        self.assertEqual(state.budget.ram_bytes, baseline)
        state.close()
        state.close()
        self.assertEqual(state.budget.ram_bytes, 0)

    def test_apply_transfer_after_cancel_preserves_snapshot_and_other_owner(self):
        """临时费用转账后取消，不能二次抵销，也不能用其他所有者的费用补差额。"""
        state, definition = self.state()
        original = state_facts.make_sample(definition, 0, 0, 1.0)
        state.apply(DecodedTimeGroup(0, (original,)))
        # 同一账本另有独立使用者；本状态 close 只能退自己的固定费和保留记录费。
        other_owner = 10_000_000
        state.budget.reserve_ram(other_owner)
        baseline = state.budget.ram_bytes
        error = KeyboardInterrupt('apply transfer already recorded')
        fault = AfterEffectOnce(state.budget.release_ram, error)
        group = DecodedTimeGroup(1, (state_facts.make_sample(definition, 1, 1, 2.0),))
        with patch.object(state.budget, 'release_ram', new=fault):
            with self.assertRaises(KeyboardInterrupt) as caught:
                state.apply(group)
        self.assertTrue(fault.fired)
        self.assertIs(caught.exception, error)
        self.assertIs(state.get('a'), original)
        self.assertEqual((state.revision, state.last_time_ns), (1, 0))
        self.assertEqual(state.budget.ram_bytes, baseline)
        state.close()
        self.assertEqual(state.budget.ram_bytes, other_owner)
        state.budget.release_ram(other_owner)
        self.assertEqual(state.budget.ram_bytes, 0)
