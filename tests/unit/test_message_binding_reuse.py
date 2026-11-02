"""验证同一新消息仓只核验一次，各指标仍有独立声明、费用及错误恢复。

输入复用真实封口消息仓和合成CAN公共AnalysisRunner夹具；输出留在work。
检查复制核验结果时不再打开reader，跨仓/未完成/变化输入不能借证，取消只保留
新lease自己的责任；实际计算reader仍核全流SHA。数值真值为两条4000W各乘0.1/0.2s。
"""

from configuration_fixtures import current_fixture
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from chronaxis import AnalysisPlan
from chronaxis.core.message_binding import ExpressionParameter, MessageDeclarations
from chronaxis.execution import message_bindings as module
from chronaxis.execution.message_bindings import MessageBindingLease, bind_message_store
from chronaxis.execution.can_reader import CANObservationRead
from chronaxis.execution.current_message_calculation import CurrentMessageCalculation
from chronaxis.legacy.message_store import DecodedMessageStore
from chronaxis.results.errors import AnalysisError, ResultClosedError, ResultFormatError
import test_legacy_message_bindings as binding_fixture
import test_run_message_calculations as runner_fixture


class MessageBindingReuseTests(unittest.TestCase):
    """每例有真实仓及借用预算标记，复用不借用其他lease的费用或关闭责任。"""

    def fixture(self):
        """建立原消息绑定夹具并登记其严格资源清理。

        参数: 无。返回: 已初始化helper。异常: 原目录/模型错误直接传播。
        """
        helper = binding_fixture.LegacyMessageBindingTests('runTest')
        helper.setUp()
        self.addCleanup(helper.tearDown)
        return helper

    def copy(self, helper, store, first, declarations=None):
        """创建独立复用lease并登记清理，不能让测试丢失其费用。

        参数: helper/store/first为本例实际资源；declarations可替换消息声明。
        返回: 新lease。异常: 原工厂错误传播。
        """
        copied = bind_message_store(helper.declarations if declarations is None else declarations,
            store, verified_by=first)
        helper.owners.append(copied)
        return copied

    def test_different_declarations_share_scan_but_keep_independent_bindings_and_cost(self):
        """不同period声明不重复读文件，但拥有不同绑定、独立费用和不受影响的并行reader。

        参数: 无。返回: None。异常: 复制时读文件、混用声明或抵销旧费用令断言失败。
        """
        helper = self.fixture()
        store = helper.store()
        first = helper.lease(store)
        reader = store.iter_records()
        helper.owners.append(reader)
        before = store.budget.ram_bytes
        declarations = MessageDeclarations(helper.base, 'bus', (ExpressionParameter('period', .2, 's'),))
        with patch.object(store, 'iter_records', side_effect=AssertionError('不可重复扫描')), \
                patch.object(Path, 'open', side_effect=AssertionError('复制绑定不可重开文件')):
            copied = self.copy(helper, store, first, declarations)
        self.assertIsNot(copied, first)
        self.assertIs(copied.bindings.declarations, declarations)
        self.assertNotEqual(copied.bindings.identity, first.bindings.identity)
        self.assertEqual(copied.bindings.evidence, first.bindings.evidence)
        self.assertIsNot(copied.bindings.evidence, first.bindings.evidence)
        self.assertEqual(store.budget.ram_bytes, before + copied._fixed_cost)
        copied.close()
        self.assertEqual(store.budget.ram_bytes, before)
        self.assertFalse(first.closed or reader.closed or store.closed)

    def test_empty_store_and_copy_chain_remain_valid_after_first_lease_closes(self):
        """空仓首末仍None，已复制lease独立持证，原lease关闭不使它丢失费用或绑定。

        参数: 无。返回: None。异常: 空仓伪造端点、关闭原lease使副本失效或重复抵费令断言失败。
        """
        helper = self.fixture()
        store = helper.store(rows=())
        first = helper.lease(store)
        copied = self.copy(helper, store, first)
        first.close()
        self.assertEqual(copied.bindings.evidence.record_count, 0)
        self.assertIsNone(copied.bindings.evidence.first_time_ns)
        self.assertIsNone(copied.bindings.evidence.last_time_ns)
        third = self.copy(helper, store, copied)
        third.close()
        self.assertFalse(copied.closed or store.closed)

    def test_structural_unfinished_and_closed_proofs_are_rejected_without_reader(self):
        """只有真实完成且未关闭的lease可借证，普通结构和半成品均不能跳过核验。

        参数: 无。返回: None。异常: 伪证据被接受、错误开reader或清掉原绑定令断言失败。
        """
        helper = self.fixture()
        store = helper.store()
        first = helper.lease(store)
        half = MessageBindingLease(store.budget)
        helper.owners.append(half)
        with patch.object(store, 'iter_records', side_effect=AssertionError('无效证据不可开reader')):
            for proof in (first.bindings, first.bindings.evidence, object()):
                with self.assertRaises(TypeError):
                    bind_message_store(helper.declarations, store, verified_by=proof)
            for proof in (half, first):
                if proof is first:
                    first.close()
                with self.assertRaises(ResultClosedError) as caught:
                    bind_message_store(helper.declarations, store, verified_by=proof)
                self.assertTrue(caught.exception.message_binding_lease_cleanup_owner.closed)

    def test_another_store_cannot_borrow_proof_even_with_identical_public_facts(self):
        """另一实际仓即使伪装同路径/读取标签/内容摘要，也不能借原对象的核验结果。

        参数: 无。返回: None。异常: 仅比较字符串而忽略实际store身份令断言失败。
        """
        helper = self.fixture()
        store = helper.store()
        first = helper.lease(store)
        other = helper.store(budget=store.budget)
        path, identity = other.file_path, other.read_identity
        try:
            other.file_path, other.read_identity = store.file_path, store.read_identity
            with patch.object(other, 'iter_records', side_effect=AssertionError('跨仓不可读证')):
                with self.assertRaises(ResultFormatError):
                    self.copy(helper, other, first)
        finally:
            other.file_path, other.read_identity = path, identity
        self.assertFalse(first.closed or store.closed or other.closed)

    def test_changed_seal_or_file_snapshot_cannot_reuse_previous_verification(self):
        """封口元数据或实际文件状态变化时拒绝复用，不打开文件补做隐式扫描。

        参数: 无。返回: None。异常: 接受变化输入或访问已替换路径令断言失败。
        """
        for changed in ('read_identity', 'file_path', 'file_time'):
            with self.subTest(changed=changed):
                helper = self.fixture()
                store = helper.store()
                first = helper.lease(store)
                original = getattr(store, changed) if changed != 'file_time' else None
                try:
                    if changed == 'file_time':
                        state = store.file_path.stat()
                        os.utime(store.file_path, ns=(state.st_atime_ns, state.st_mtime_ns + 1_000_000_000))
                    elif changed == 'file_path':
                        store.file_path = helper.root / 'unopened-missing-path'
                    else:
                        store.read_identity = 'changed-after-verification'
                    with patch.object(store, 'iter_records', side_effect=AssertionError('变化输入不可复用')):
                        with self.assertRaises(ResultFormatError):
                            self.copy(helper, store, first)
                finally:
                    if changed != 'file_time':
                        setattr(store, changed, original)
                self.assertFalse(first.closed or store.closed)

    def test_cancelled_copy_keeps_only_new_fee_until_recovery(self):
        """新副本预约后或模型构造时取消，持续抵费失败只保新责任，不动原lease或仓。

        参数: 无。返回: None。异常: 原取消被盖、旧费用被抵销或新费用丢失令断言失败。
        """
        for boundary in ('reserve_after', 'model'):
            with self.subTest(boundary=boundary):
                helper = self.fixture()
                store = helper.store()
                first = helper.lease(store)
                before = store.budget.ram_bytes
                primary, cleanup = KeyboardInterrupt('shared-bind-cancel'), RuntimeError('copy-release-held')
                original_reserve = store.budget.reserve_ram

                def reserve(amount):
                    """真实入账后抛原取消。参数: amount为字节。返回: 无。异常: primary。"""
                    original_reserve(amount)
                    raise primary

                injection = (patch.object(store.budget, 'reserve_ram', side_effect=reserve)
                    if boundary == 'reserve_after' else patch.object(module, 'MessageBindings', side_effect=primary))
                with injection, patch.object(store.budget, 'release_ram', side_effect=cleanup), \
                        patch.object(store, 'iter_records', side_effect=AssertionError('副本不可开reader')):
                    with self.assertRaises(KeyboardInterrupt) as caught:
                        bind_message_store(helper.declarations, store, verified_by=first)
                    self.assertIs(caught.exception, primary)
                    owner = caught.exception.message_binding_lease_cleanup_owner
                    helper.owners.append(owner)
                    self.assertFalse(owner.closed)
                    self.assertGreater(owner._fixed_cost, 0)
                    self.assertEqual(store.budget.ram_bytes, before + owner._fixed_cost)
                    self.assertFalse(first.closed or store.closed)
                owner.close()
                self.assertEqual(store.budget.ram_bytes, before)

    def test_actual_reader_still_rejects_content_changed_after_shared_binding(self):
        """共享后实际计算所用reader仍检查全流SHA，不能拿先前证据掩盖后来的内容改动。

        参数: 无。返回: None。异常: 实际EOF接受篡改内容或伪报verified_eof令断言失败。
        """
        helper = self.fixture()
        store = helper.store()
        first = helper.lease(store)
        self.copy(helper, store, first)
        before = store.file_path.read_bytes()
        after = before.replace(b'4000.0', b'5000.0')
        self.assertNotEqual(before, after)
        self.assertEqual(len(before), len(after))
        store.file_path.write_bytes(after)
        reader = store.iter_records()
        helper.owners.append(reader)
        with self.assertRaises(AnalysisError):
            tuple(reader)
        self.assertFalse(reader.verified_eof)

    def test_public_runner_two_parameter_sets_share_one_actual_read(self):
        """两个period独立得800/1600J；同次读入四帧、交付三帧，不回读旧消息仓。

        参数: 无。返回: None。异常: 重复扫描、共用错误参数、漏求值或资源不归零令断言失败。
        """
        helper = runner_fixture.RunMessageCalculationTests('runTest')
        self.addCleanup(helper.doCleanups)
        work, config, _ = helper.fixture(calculation_count=2)
        config['message_calculations'][1]['parameters']['period']['value'] = .2
        plan = AnalysisPlan.from_dict(current_fixture(config), base_dir=work)
        original, calls = CANObservationRead._deliver_message, []
        snapshot, snapshots = CurrentMessageCalculation.snapshot, {}
        close, observations = CANObservationRead.close, []

        def delivered(reader, record, time_ns):
            """透明观察同次原帧交付。参数: 原reader/记录/时间。返回: 原结果。异常: 原错误。"""
            calls.append(id(reader))
            return original(reader, record, time_ns)

        def observed(owner):
            """保存真实累计快照用于独立计数校验。参数: owner。返回: 原快照。异常: 原错误。"""
            value = snapshot(owner)
            snapshots[owner._calculation.calculation_id] = value
            return value

        def closed(reader):
            """关闭前保存真实EOF，不以交付条数冒充原帧数。参数: reader。返回: 原结果。异常: 原错误。"""
            if reader._finished and not reader._closed and not reader._closing and not reader._failed:
                observations.append(reader.observation)
            return close(reader)

        with patch.object(CANObservationRead, '_deliver_message', delivered), \
                patch.object(CurrentMessageCalculation, 'snapshot', observed), \
                patch.object(CANObservationRead, 'close', closed), \
                patch.object(DecodedMessageStore, 'iter_records', side_effect=AssertionError('当前执行不回读旧消息仓')):
            result = helper.run_plan(work, plan)
        rows = helper.rows(result, 'summary')
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(set(calls)), 1)
        self.assertEqual([(fact.row_count, fact.source_eof) for fact in observations], [(4, True)])
        self.assertEqual({row.calculation_id: row.value for row in rows}, {'energy0': 800., 'energy1': 1600.})
        self.assertEqual(set(snapshots), {'energy0', 'energy1'})
        self.assertTrue(all(row.evaluation_count == 3 and row.skipped_count == 1 for row in snapshots.values()))
        self.assertEqual(len(helper.rows(result, 'contributions')), 6)
        result.close()
        self.assertEqual(result.spool.budget.ram_bytes, 0)


if __name__ == '__main__':
    unittest.main()
