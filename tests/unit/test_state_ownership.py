"""最小复现新state构造/关闭预算操作前后取消，不改变完整组提交算法。

纯内存小账本和已声明样本分别验证字段/预算交接；失败账本不由替身偷偷抵销。
成功抵销后最小关闭，之前未发生动作时保留同一状态以便重试。
"""

# 共享已验合成规范记录函数，导入模块别名不重复发现原TestCase。
import unittest
from unittest.mock import patch
import test_stream_state as state_facts
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.types import SignalDType
from chronaxis.execution.groups import DecodedTimeGroup
from chronaxis.execution.state import LatestSignalState
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import ResultClosedError


class StateOwnershipTests(unittest.TestCase):
    """每子场景独立纯内存账本，断言前不通过清字段掩盖原取消缺陷。"""

    def cancel_once(self, original, after):
        """首次操作前或成功后取消，后续调用真实方法。

        参数: original预算函数，after是否先真实操作。返回: 故障函数。
        异常: 首次KeyboardInterrupt，其他原错误传播。
        """
        used = False

        def invoke(amount):
            """执行目标取消。参数: bytes。返回: 原返回。异常: 首次KeyboardInterrupt。"""
            nonlocal used
            if not used:
                used = True
                if after:
                    original(amount)
                raise KeyboardInterrupt('state-budget-lifecycle')
            return original(amount)

        return invoke

    def definition(self):
        """创建固定声明。参数: 无。返回: SignalDefinition。异常: 模型错误传播。"""
        return SignalDefinition('a', 'table', 'raw.a', SignalDType.FLOAT64, '1', 3)

    def check_close(self, active):
        """核对关闭前后取消的完整真实状态与账本。

        参数: active是否提交一个真实规范样本。返回: None。
        异常: 重复扣账/字段未关闭/样本变更断言失败，不清私有字段绕过。
        """
        for after in (False, True):
            with self.subTest(active=active, after=after):
                budget, definition = ResourceBudget(), self.definition()
                state = LatestSignalState(budget, (definition,), 'session')
                sample = state_facts.make_sample(definition, 0, 0, 1.0) if active else None
                if active:
                    state.apply(DecodedTimeGroup(0, (sample,)))
                    self.assertGreater(state.retained_cost, 0)
                before = budget.ram_bytes
                with patch.object(budget, 'release_ram', side_effect=self.cancel_once(budget.release_ram, after)):
                    with self.assertRaises(KeyboardInterrupt):
                        state.close()
                self.assertEqual(state.closed, after)
                self.assertEqual(budget.ram_bytes, 0 if after else before)
                if not after:
                    self.assertIs(state.get('a'), sample)
                    self.assertEqual(state.revision, int(active))
                state.close()
                state.close()
                self.assertEqual(budget.ram_bytes, 0)
                self.assertEqual((state.fixed_cost, state.retained_cost, state.last_time_ns), (0, 0, None))
                with self.assertRaises(ResultClosedError):
                    state.get('a')

    def test_constructor_reserve_before_after_cancel_releases_successful_cost(self):
        """构造申请前后取消均不交付owner，成功申请必须由构造保护区抵销。

        参数: 无。返回: None。异常: 申请返回取消漏固定成本断言失败。
        """
        for after in (False, True):
            with self.subTest(after=after):
                budget = ResourceBudget()
                with patch.object(budget, 'reserve_ram', side_effect=self.cancel_once(budget.reserve_ram, after)):
                    with self.assertRaises(KeyboardInterrupt):
                        LatestSignalState(budget, (self.definition(),), 'session')
                self.assertEqual(budget.ram_bytes, 0)

    def test_empty_state_close_release_before_after_cancel_is_retryable(self):
        """空state固定成本关闭取消可重试且不重复抵销。参数: 无。返回: None。异常: 断言失败。"""
        self.check_close(False)

    def test_retained_sample_close_release_before_after_cancel_is_retryable(self):
        """真实最新样本与固定成本一次关闭，取消不遗留字段。参数: 无。返回: None。异常: 断言失败。"""
        self.check_close(True)
