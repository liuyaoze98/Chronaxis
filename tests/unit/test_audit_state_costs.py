"""验证最新信号费用按别名复用，同时保留快照、峰值预算和失败恢复。

使用现役 RecordSample 和必要的历史枚举输入，只有内存中的合成记录。
这些用例计数实际估算调用，并用独立重算的保留记录总量核对差额，未做耗时断言。
"""

from dataclasses import replace
import unittest
from unittest.mock import patch

import test_stream_state as state_facts
from test_audit_resource_transactions import AfterEffectOnce
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.models import SourceRef
from chronaxis.core.numeric import normalize_reference
from chronaxis.core.types import SignalDType
from chronaxis.execution.groups import DecodedTimeGroup
from chronaxis.execution.history_records import estimate_record_bytes
from chronaxis.execution.record_sample import RecordSample
from chronaxis.execution.state import LatestSignalState
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import ResultClosedError
from chronaxis.sources.csv_spec import CSVSourceRef


class StateCostCacheTests(unittest.TestCase):
    """费用缓存只保存每个声明的一个费用，不保存全历史或全局对象缓存。"""

    def definition(self, name, **options):
        """建立当前数值声明。参数: 名称/模型选项。返回: SignalDefinition。异常: 模型错误。"""
        return SignalDefinition(name, 'table', 'raw.' + name, SignalDType.FLOAT64, 'A', 3, **options)

    def sample(self, definition, time, sequence, value, text=None):
        """生成现役规范记录。参数: 声明/时刻/序号/值/可选原文。返回: RecordSample。异常: 模型错误。"""
        reference = SourceRef('session', 'table', definition.field)
        if text is not None:
            reference = CSVSourceRef('session', 'table', definition.field, 'synthetic.csv', sequence + 2,
                                     str(time), text, False)
        return RecordSample(definition.name, time, sequence, normalize_reference(definition, value),
                            definition.unit, reference)

    def state(self, definitions):
        """登记真实状态关闭。参数: 声明tuple。返回: 状态。异常: 初始化或最终清理错误。"""
        state = LatestSignalState(ResourceBudget(), definitions, 'session')
        self.addCleanup(state.close)
        return state

    def assert_owned_cost(self, state, other=0):
        """从实际保留记录独立核算总额。参数: 状态/其他所有者费用。返回: None。异常: 断言失败。"""
        expected = sum(estimate_record_bytes(record) for record in state.latest.values() if record is not None)
        self.assertEqual(state.retained_cost, expected)
        self.assertEqual(state.budget.ram_bytes, other + state.fixed_cost + expected)
        self.assertEqual(state._held_cost, state.fixed_cost + expected)
        self.assertEqual(state._transaction_delta, 0)

    def test_sparse_current_update_never_revisits_unchanged_payload(self):
        """只更新 a 时，b/c 的长来源引用不再递归估算，旧只读快照仍能独立读取。"""
        definitions = tuple(self.definition(name) for name in ('a', 'b', 'c'))
        state = self.state(definitions)
        initial = tuple(self.sample(item, 0, 0, 1.0, '旧' * 2000) for item in definitions)
        state.apply(DecodedTimeGroup(0, initial))
        old = state._snapshot
        visited = []

        def observe(record):
            """记录真正估算的对象。参数: 规范记录。返回: 原费用。异常: 原估算错误。"""
            visited.append(record)
            return estimate_record_bytes(record)

        updated = self.sample(definitions[0], 1, 1, 2.0)
        with patch('chronaxis.execution.state.estimate_record_bytes', new=observe):
            state.apply(DecodedTimeGroup(1, (updated,)))
        self.assertTrue(visited)
        self.assertEqual({record.name for record in visited}, {'a'})
        self.assertIs(old.latest['a'], initial[0])
        self.assertIs(state.get('a'), updated)
        self.assertIs(state.get('b'), initial[1])
        self.assertEqual(old.costs['b'], state._snapshot.costs['b'])
        self.assertEqual(len(state._snapshot.costs), len(definitions))
        with self.assertRaises(TypeError):
            old.costs['a'] = 0
        self.assert_owned_cost(state)

    def test_fee_follows_selected_sequence_not_input_order(self):
        """同刻冲突选序号最大的记录；费用不得沿用未选中的长记录或输入列表末项。"""
        definition = self.definition('a', same_time_policy='last_by_sequence')
        for reverse in (False, True):
            with self.subTest(reverse=reverse):
                state = self.state((definition,))
                long = self.sample(definition, 0, 1, 1.0, 'x' * 3000)
                selected = self.sample(definition, 0, 2, 2.0)
                records = (selected, long) if reverse else (long, selected)
                result = state.apply(DecodedTimeGroup(0, records))
                self.assertEqual(result.conflict_count, 1)
                self.assertEqual(result.updates, (selected,))
                self.assertIs(state.get('a'), selected)
                self.assertEqual(state.retained_cost, estimate_record_bytes(selected))
                self.assert_owned_cost(state)

    def test_cost_increase_decrease_and_peak_include_live_replacement(self):
        """来源文本变长再变短时按实际差额收费，提交峰值仍覆盖旧状态和新输入。"""
        definition = self.definition('a')
        state = self.state((definition,))
        previous = 0
        for number, text in enumerate((None, '长' * 4000, None)):
            record = self.sample(definition, number, number, number + 1.0, text)
            before = state.budget.ram_bytes
            state.apply(DecodedTimeGroup(number, (record,)))
            self.assertGreaterEqual(state.budget.peak_ram_bytes, before + estimate_record_bytes(record))
            if number == 1:
                self.assertGreater(state.retained_cost, previous)
            elif number == 2:
                self.assertLess(state.retained_cost, previous)
            previous = state.retained_cost
            self.assert_owned_cost(state)

    def test_enriched_enum_keeps_final_code_payload_cost(self):
        """历史枚举补入必要原码后，缓存费用对应最终记录，输入对象仍没有被改写。"""
        definition = SignalDefinition('mode', 'table', 'raw.mode', SignalDType.ENUM, '1', 3,
            choices=((7, 'on'), (9, 'off')), code_dtype=SignalDType.INT64, capture_code=True)
        state = self.state((definition,))
        sample = state_facts.make_sample(definition, 0, 0, 7)
        # 构造旧历史布局，强制走已经支持的原码补齐入口。
        sample = replace(sample, value=replace(sample.value, code=None))
        state.apply(DecodedTimeGroup(0, (sample,)))
        selected = state.get('mode')
        self.assertIsNone(sample.value.code)
        self.assertEqual(selected.value.code.value, 7)
        self.assertEqual(selected.value.code.dtype, SignalDType.INT64)
        self.assertGreater(estimate_record_bytes(selected), estimate_record_bytes(sample))
        self.assert_owned_cost(state)

    def test_persistent_refund_failure_retains_owner_without_spending_other_fee(self):
        """申请后取消且恢复退款持续失败时保留最高状态；之后 close 只退实际自有金额。"""
        definition = self.definition('a')
        state = self.state((definition,))
        other = 123456
        state.budget.reserve_ram(other)
        primary = KeyboardInterrupt('apply reserve completed')
        fault = AfterEffectOnce(state.budget.reserve_ram, primary)
        group = DecodedTimeGroup(0, (self.sample(definition, 0, 0, 1.0),))
        with patch.object(state.budget, 'reserve_ram', new=fault), patch.object(
                state.budget, 'release_ram', side_effect=OSError('refund unavailable')):
            with self.assertRaises(KeyboardInterrupt) as caught:
                state.apply(group)
        self.assertIs(caught.exception, primary)
        self.assertIs(primary.state_cleanup_owner, state)
        self.assertIsNone(state.get('a'))
        with self.assertRaises(ResultClosedError):
            state.apply(group)
        state.close()
        state.close()
        self.assertEqual(state.budget.ram_bytes, other)
        state.budget.release_ram(other)

    def test_negative_delta_restore_failure_closes_only_remaining_owned_fee(self):
        """长记录变短后退款已完成但取消，补回旧费用失败时不得多退另一所有者的钱。"""
        definition = self.definition('a')
        state = self.state((definition,))
        original = self.sample(definition, 0, 0, 1.0, 'x' * 5000)
        state.apply(DecodedTimeGroup(0, (original,)))
        other = 123456
        state.budget.reserve_ram(other)
        primary = KeyboardInterrupt('negative transfer completed')
        reserve = state.budget.reserve_ram
        transferred = AfterEffectOnce(state.budget.release_ram, primary)

        def reject_restore(amount):
            """正常支付工作区，转账取消后的补费才失败。参数: bytes。返回: None。异常: 恢复故障。"""
            if transferred.fired:
                raise OSError('restore unavailable')
            return reserve(amount)

        group = DecodedTimeGroup(1, (self.sample(definition, 1, 1, 2.0),))
        with patch.object(state.budget, 'release_ram', new=transferred), patch.object(
                state.budget, 'reserve_ram', new=reject_restore):
            with self.assertRaises(KeyboardInterrupt) as caught:
                state.apply(group)
        self.assertIs(caught.exception, primary)
        self.assertIs(primary.state_cleanup_owner, state)
        self.assertIs(state.get('a'), original)
        self.assertLess(state._transaction_delta, 0)
        with self.assertRaises(ResultClosedError):
            state.apply(group)
        state.close()
        self.assertEqual(state.budget.ram_bytes, other)
        state.budget.release_ram(other)

    def test_negative_delta_restore_after_cancel_keeps_original_and_can_retry(self):
        """补回旧费用已经成功又取消时，主错误保持，旧快照和预算恢复后可重试原组。"""
        definition = self.definition('a')
        state = self.state((definition,))
        original = self.sample(definition, 0, 0, 1.0, 'x' * 5000)
        state.apply(DecodedTimeGroup(0, (original,)))
        baseline = state.budget.ram_bytes
        primary = KeyboardInterrupt('transfer completed')
        secondary = SystemExit('restore completed')
        reserve = state.budget.reserve_ram
        transferred = AfterEffectOnce(state.budget.release_ram, primary)
        restored = []

        def cancel_after_restore(amount):
            """仅补费成功后再取消。参数: bytes。返回: None。异常: 一次恢复取消。"""
            reserve(amount)
            if transferred.fired and not restored:
                restored.append(True)
                raise secondary

        group = DecodedTimeGroup(1, (self.sample(definition, 1, 1, 2.0),))
        with patch.object(state.budget, 'release_ram', new=transferred), patch.object(
                state.budget, 'reserve_ram', new=cancel_after_restore):
            with self.assertRaises(KeyboardInterrupt) as caught:
                state.apply(group)
        self.assertIs(caught.exception, primary)
        self.assertTrue(restored)
        self.assertIs(state.get('a'), original)
        self.assertEqual(state.budget.ram_bytes, baseline)
        self.assert_owned_cost(state)
        state.apply(group)
        self.assertEqual(state.get('a').value.value, 2.0)
        self.assert_owned_cost(state)


if __name__ == '__main__':
    unittest.main()
