"""从真实独立解码仓核验消息绑定事实、完整EOF及失败时的实际责任。

输入是有限原始解码帧、显式消息声明和真实ResourceBudget；每例写独占work仓。
正确性取手写时间/条数及hashlib，不用手造MessageSourceEvidence冒充回读；结构模型
测试另外明确标注不证明IO。缺key和空仓合法，首末取全仓原序，不按TTL/投影裁剪。

真实FileIO代理仅在read/close前后注入，最高lease与原store责任分别核对。store的
reader失败原本会poison父仓，此行为不被误报为binder显式关闭借仓；未返回reader
仍由原store保留，不能要求lease擅自接管借用父。共享预算保调用方777及另一仓的
活reader，费用均核真实交易和恢复基线，不以共享余额补账，也不生成假半初始化owner。
本文件不读CAN/DBC，不造history/DecodedBindings，不扩大到B5同次捕获或AnalysisRunner。
"""

from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from chronaxis.core.binding import SignalDefinition
from chronaxis.core.declarations import DeclarationBindings, DeclaredSource
from chronaxis.core.message_binding import (ExpressionParameter, MessageBindings,
    MessageDeclarations, MessageSourceEvidence)
from chronaxis.core.models import Interval, TimebaseSpec
from chronaxis.core.types import SignalDType as D, TimeType
from chronaxis.execution import message_bindings as module
from chronaxis.execution.message_bindings import MessageBindingLease, bind_message_store
from chronaxis.legacy.message_store import DecodedMessageStore
from chronaxis.legacy.records import LegacyDecodedFrame, LegacyRawFrame
from chronaxis.results import BudgetExceededError, ResourceBudget, ResultClosedError, ResultFormatError


def decoded_record(sequence, values):
    """建立完整原帧和本次原字典，标签不作为CAN已认证证明。

    参数: sequence为连续原序；values保缺key。返回: LegacyDecodedFrame。
    异常: 原records校验错误传播；不加TTL、别名或求值索引。
    """
    frame = LegacyRawFrame(float(sequence), 0x100, False, False, False, 'raw channel',
        2, b'\xa0\x0f', False, True, False, False)
    return LegacyDecodedFrame(sequence, frame, values)


class ActualReadFile:
    """透传实际FD，read及close故障不虚构closed或EOF事实。"""

    def __init__(self, actual):
        """保存真实FD及禁用的注入配置。参数: actual为FileIO。返回: 代理。异常: 无。
        """
        self.actual = actual
        self.read_error = self.close_error = None
        self.fail_read_at = 1
        self.read_calls = self.close_calls = 0
        self.close_after = False

    def __getattr__(self, name):
        """转发真实属性。参数: name。返回: 原属性。异常: 原属性错误传播。"""
        return getattr(self.actual, name)

    def readline(self, size):
        """真实限长读取，指定调用前可抛原对象。参数: size。返回: bytes。异常: 原IO/注入错。"""
        self.read_calls += 1
        if self.read_error is not None and self.read_calls >= self.fail_read_at:
            raise self.read_error
        return self.actual.readline(size)

    def close(self):
        """在实际close前或后抛同一故障。参数: 无。返回: 原返回。异常: 原close_error/IO错。"""
        self.close_calls += 1
        if self.close_error is not None and not self.close_after:
            raise self.close_error
        result = self.actual.close()
        if self.close_error is not None:
            raise self.close_error
        return result


class StopBeforePhysicalEOF:
    """交付全部真实行后提前close，不读取底层最终空readline，证明行数不能代替EOF。"""

    def __init__(self, actual, count):
        """保存实际reader和有限条数。参数: actual/count。返回: 代理。异常: 无。"""
        self.actual, self.count, self.delivered = actual, count, 0

    def __getattr__(self, name):
        """转发实际证明/费用/句柄。参数: name。返回: 原属性。异常: 原属性错误。"""
        return getattr(self.actual, name)

    def __iter__(self):
        """返回同一位置。参数: 无。返回: self。异常: 无。"""
        return self

    def __next__(self):
        """只在最后真实行之后截断协议。参数: 无。返回: 原记录。异常: 提前StopIteration。"""
        if self.delivered == self.count:
            self.actual.close()
            raise StopIteration
        record = next(self.actual)
        self.delivered += 1
        return record

    def close(self):
        """仅关闭原子reader。参数: 无。返回: 原close值。异常: 原关闭错。"""
        return self.actual.close()


class FailingRegistration(set):
    """在原仓登记真实reader前后失败，保存实际未返回实例供父恢复核验。"""

    def __init__(self, error, after):
        """保存故障位置。参数: error/after。返回: 空实际集合。异常: 无。"""
        super().__init__()
        self.error, self.after, self.reader = error, after, None

    def add(self, reader):
        """可先实际登记再抛原错。参数: reader为真实对象。返回: 无。异常: 同一error。"""
        self.reader = reader
        if self.after:
            super().add(reader)
        raise self.error


class LegacyMessageBindingTests(unittest.TestCase):
    """每例实际封口仓/独立reader/lease，故障恢复必须保原错和借用边界。"""

    def setUp(self):
        """建立独占目录及静态声明，未读任何来源。参数: 无。返回: None。异常: 原错误。"""
        self.root = Path(__file__).resolve().parents[2] / 'work/m2-legacy-tests/message-bindings' / uuid4().hex
        self.root.mkdir(parents=True)
        self.owners, self.budgets, self.handles = [], [], []
        clock = TimebaseSpec('clock', TimeType.RELATIVE, 'message-bindings-synthetic')
        self.definition = SignalDefinition('power', 'bus', 'Raw.Power', D.FLOAT64, 'W', 1)
        self.base = DeclarationBindings('session', clock, Interval(0, 10),
            (DeclaredSource('bus', clock, 'explicit-store-config'),
             DeclaredSource('aux', clock, 'other-config')), (self.definition,))
        self.declarations = MessageDeclarations(self.base, 'bus', (ExpressionParameter('period', 0.1, 's'),))

    def tearDown(self):
        """解除本例代理故障后按实际owner关闭，借款只能最后释放。

        参数: 无。返回: None。异常: 真实关闭错误或预算不守恒直接失败。
        """
        for handle in self.handles:
            handle.read_error = handle.close_error = None
        for owner in reversed(self.owners):
            owner.close()
        for budget in self.budgets:
            self.assertEqual(budget.ram_bytes, 777)
            budget.release_ram(777)
            self.assertEqual(budget.ram_bytes, 0)

    def budget(self):
        """建立真实账本和调用方标记。参数: 无。返回: ResourceBudget。异常: 原预算错。"""
        budget = ResourceBudget(64 * 1024**2)
        budget.reserve_ram(777)
        self.budgets.append(budget)
        return budget

    def store(self, *, budget=None, rows=None, seal=True):
        """真实构造并写仓；空rows与默认三行明确区分。

        参数: budget可共享；rows为(time,原字典)；seal控制真封口。
        返回: 实际DecodedMessageStore。异常: 原模型、写入或预算错误传播。
        """
        owner = DecodedMessageStore(self.budget() if budget is None else budget,
            self.root / ('store-' + str(len(self.owners))), 'bus', 'session',
            decoder_profile='explicit-decoded-v1', read_identity=uuid4().hex)
        self.owners.append(owner)
        if rows is None:
            rows = ((0, {'Raw.Power': 4000.0}), (0, {}), (9, {'unbound.field': False}))
        for index, (time_ns, values) in enumerate(rows):
            owner.append(decoded_record(index, values), time_ns, time_quantized=False)
        if seal:
            owner.seal()
        return owner

    def lease(self, store, declarations=None):
        """经真实工厂获取lease并登记关闭。参数: 原store/可选声明。返回: lease。异常: 原工厂错。"""
        lease = bind_message_store(self.declarations if declarations is None else declarations, store)
        self.owners.append(lease)
        return lease

    def recovery(self, error, expected=None):
        """核最高lease是真实构造对象并登记，不用__new__补责任。

        参数: 原error/可选expected。返回: 同一MessageBindingLease。异常: 身份或属性缺失失败。
        """
        owner = getattr(error, 'message_binding_lease_cleanup_owner', None)
        self.assertIs(type(owner), MessageBindingLease)
        if expected is not None:
            self.assertIs(owner, expected)
        if not any(item is owner for item in self.owners):
            self.owners.append(owner)
        with self.assertRaises(ResultClosedError):
            _ = owner.bindings
        return owner

    def shared(self):
        """保另一真实仓的活FD，目标失败不得影响这个不同owner。

        参数: 无。返回: budget/sibling/reader/基线。异常: 原文件或预算错误。
        """
        budget = self.budget()
        sibling = self.store(budget=budget)
        reader = sibling.iter_records()
        return SimpleNamespace(budget=budget, sibling=sibling, reader=reader, baseline=budget.ram_bytes)

    def assert_shared(self, data):
        """核真实兄弟FD、借款及费用基线。参数: data。返回: None。异常: 误关/漏账失败。"""
        self.assertFalse(data.sibling.closed or data.reader.closed or data.reader.handle.closed)
        self.assertEqual(data.budget.ram_bytes, data.baseline)

    def opening(self, handles, *, read_error=None, close_error=None, close_after=False):
        """返回只包装实际rb文件的Path.open透传函数，不虚构open成功。

        参数: handles保存真实代理；其余指定本次FD故障。返回: 函数。
        异常: 实际文件打开错误不包装，沿原对象传播。
        """
        original_open = Path.open

        def open_file(path, mode='r', *args, **kwargs):
            """真实打开后安装观察代理。参数: Path.open原参数。返回: 原FD或代理。异常: 原IO错。"""
            actual = original_open(path, mode, *args, **kwargs)
            if mode != 'rb':
                return actual
            wrapped = ActualReadFile(actual)
            wrapped.read_error, wrapped.close_error = read_error, close_error
            wrapped.fail_read_at, wrapped.close_after = 2, close_after
            handles.append(wrapped)
            self.handles.append(wrapped)
            return wrapped

        return open_file

    def test_factory_reads_whole_store_and_closes_only_own_reader_before_return(self):
        """真EOF后才返回完整SHA/count/首末，两个lease独立且不误关借仓/其他reader。

        参数: 无。返回: None。异常: 提前证据、身份重建、FD或预算事实不符时失败。
        """
        store = self.store()
        external = store.iter_records()
        before = store.budget.ram_bytes
        original, readers = store.iter_records, []

        def observe_reader():
            """只记录真实返回子。参数: 无。返回: 原reader。异常: 原工厂错误。"""
            reader = original()
            readers.append(reader)
            return reader

        with patch.object(store, 'iter_records', new=observe_reader), \
                patch.object(store, 'close', wraps=store.close) as close_store:
            first, second = self.lease(store), self.lease(store)
            close_store.assert_not_called()
            self.assertEqual(len(readers), 2)
            self.assertTrue(all(reader.verified_eof and reader.closed and reader.handle.closed for reader in readers))
            bindings, evidence = first.bindings, first.bindings.evidence
            self.assertIs(type(bindings), MessageBindings)
            self.assertIs(bindings.declarations, self.declarations)
            self.assertIs(bindings.resolve('power'), self.definition)
            self.assertEqual(bindings.identity, second.bindings.identity)
            self.assertEqual((evidence.source, evidence.session_id, evidence.decoder_profile,
                evidence.read_identity), ('bus', 'session', store.decoder_profile, store.read_identity))
            self.assertEqual((evidence.record_count, evidence.first_time_ns, evidence.last_time_ns), (3, 0, 9))
            self.assertEqual(evidence.store_sha256, sha256(store.file_path.read_bytes()).hexdigest())
            self.assertEqual(evidence.store_sha256, store.sha256)
            with self.assertRaises(FrozenInstanceError):
                evidence.record_count = 0
            with self.assertRaises(FrozenInstanceError):
                bindings.evidence = evidence
            first.close()
            first.close()
            self.assertFalse(second.closed)
            self.assertIs(second.bindings.resolve('power'), self.definition)
            second.close()
            close_store.assert_not_called()
        self.assertFalse(store.closed or external.closed or external.handle.closed)
        self.assertEqual(store.budget.ram_bytes, before)
        with self.assertRaises(ResultClosedError):
            _ = first.bindings
        external.close()

    def test_empty_point_extreme_and_missing_field_ranges_come_from_all_actual_rows(self):
        """空仓None、单点相同端点、int64全跨度及无已绑定字段都按原行事实返回。

        参数: 无。返回: None。异常: 域裁剪、假零点、跨度溢出或要求字段出现时失败。
        """
        cases = (((), (0, None, None)), (((7, {}),), (1, 7, 7)),
            (((-(2**63), {}), (2**63 - 1, {})), (2, -(2**63), 2**63 - 1)))
        for rows, expected in cases:
            with self.subTest(expected=expected):
                store = self.store(rows=rows)
                lease = self.lease(store)
                evidence = lease.bindings.evidence
                self.assertEqual((evidence.record_count, evidence.first_time_ns, evidence.last_time_ns), expected)
                self.assertEqual(evidence.store_sha256, sha256(store.file_path.read_bytes()).hexdigest())
                lease.close()
                self.assertFalse(store.closed)

    def test_structural_evidence_is_not_factory_io_proof_and_wrong_inputs_are_rejected(self):
        """模型只校结构，工厂仍需真实活sealed仓及对应来源/会话，不能拿evidence替代。

        参数: 无。返回: None。异常: 类型/归属/状态门槛错误时失败。
        """
        with patch.object(Path, 'open', side_effect=AssertionError('model must not read')):
            evidence = MessageSourceEvidence('bus', 'session', 'explicit-profile', 'explicit-read',
                '0' * 64, 1, 0, 0)
            structured = MessageBindings(self.declarations, evidence)
        self.assertIs(structured.evidence, evidence)
        for changes in ({'store_sha256': 'g' * 64}, {'record_count': True},
                {'record_count': 0}, {'first_time_ns': None}, {'last_time_ns': -1}):
            with self.subTest(changes=changes), self.assertRaises((TypeError, ValueError)):
                replace(evidence, **changes)
        store = self.store()
        before = store.budget.ram_bytes
        for wrong in (evidence, structured, self.base):
            with self.subTest(wrong=type(wrong)), self.assertRaises(TypeError):
                bind_message_store(wrong, store)
        with self.assertRaises(TypeError):
            bind_message_store(self.declarations, structured)
        variants = (MessageDeclarations(self.base, 'aux'),
            MessageDeclarations(replace(self.base, session_id='another_session'), 'bus'))
        for declarations in variants:
            with self.subTest(source=declarations.source), self.assertRaises(ValueError) as caught:
                bind_message_store(declarations, store)
            self.recovery(caught.exception).close()
            self.assertFalse(store.closed)
            self.assertEqual(store.budget.ram_bytes, before)
        building = self.store(seal=False)
        with self.assertRaises(RuntimeError):
            bind_message_store(self.declarations, building)
        building.close()
        with self.assertRaises(ResultClosedError):
            bind_message_store(self.declarations, building)

    def test_tamper_truncation_and_extra_suffix_fail_real_sha_count_and_close_fd(self):
        """实际行改值、缺尾行和追加记录均无法生成绑定，保原store失败策略及最高恢复。

        参数: 无。返回: None。异常: 损坏被接受、资源或原错误身份不符时失败。
        """
        for damage in ('value', 'truncate', 'append'):
            with self.subTest(damage=damage):
                data = self.shared()
                store = self.store(budget=data.budget)
                payload = store.file_path.read_bytes()
                if damage == 'value':
                    damaged = payload.replace(b'4000.0', b'4001.0', 1)
                    self.assertNotEqual(damaged, payload)
                elif damage == 'truncate':
                    damaged = b''.join(payload.splitlines(keepends=True)[:-1])
                else:
                    damaged = payload + payload.splitlines(keepends=True)[-1]
                store.file_path.write_bytes(damaged)
                handles = []
                with patch.object(Path, 'open', new=self.opening(handles)):
                    with self.assertRaises(ResultFormatError) as caught:
                        bind_message_store(self.declarations, store)
                owner = self.recovery(caught.exception)
                self.assertIs(getattr(caught.exception, 'decoded_message_store_cleanup_owner', None), store)
                owner.close()
                store.close()
                self.assertTrue(handles and all(handle.closed for handle in handles))
                self.assert_shared(data)

    def test_all_records_delivered_then_early_close_still_cannot_prove_physical_eof(self):
        """最后原记录已交付且count相同仍不足，提前close不得伪造verified_eof。

        参数: 无。返回: None。异常: EOF资格、真实FD或借用仓生命周期不符时失败。
        """
        store = self.store()
        before = store.budget.ram_bytes
        original, wrappers = store.iter_records, []

        def early_reader():
            """包装真实游标而不改其证明。参数: 无。返回: 提前结束代理。异常: 原工厂错。"""
            wrapped = StopBeforePhysicalEOF(original(), store.count)
            wrappers.append(wrapped)
            return wrapped

        with patch.object(store, 'iter_records', new=early_reader):
            with self.assertRaises(ResultFormatError) as caught:
                bind_message_store(self.declarations, store)
        self.recovery(caught.exception).close()
        self.assertEqual(len(wrappers), 1)
        self.assertEqual(wrappers[0].delivered, 3)
        self.assertFalse(wrappers[0].verified_eof)
        self.assertTrue(wrappers[0].closed and wrappers[0].handle.closed)
        self.assertFalse(store.closed)
        self.assertEqual(store.budget.ram_bytes, before)

    def test_real_capacity_rejection_precedes_reader_and_identity_construction(self):
        """真实账本只剩1字节时先报预算，不打开reader或创建运行绑定模型。

        参数: 无。返回: None。异常: 预算晚于副作用、错误替换或借款被抵销时失败。
        """
        store = self.store()
        budget, before = store.budget, store.budget.ram_bytes
        filler = budget.memory_budget_bytes - before - 1
        budget.reserve_ram(filler)
        try:
            with patch.object(store, 'iter_records', wraps=store.iter_records) as reader, \
                    patch.object(module, 'MessageSourceEvidence', wraps=MessageSourceEvidence) as evidence:
                with self.assertRaises(BudgetExceededError) as caught:
                    bind_message_store(self.declarations, store)
                reader.assert_not_called()
                evidence.assert_not_called()
            self.recovery(caught.exception).close()
            self.assertFalse(store.closed)
            self.assertEqual(budget.ram_bytes, before + filler)
        finally:
            budget.release_ram(filler)

    def test_factory_fixed_reserve_before_after_cancel_retains_same_real_lease(self):
        """固定费预约前后取消均保原KI和真实未返回lease，且尚未读仓。

        参数: 无。返回: None。异常: 原错/责任槽/费用或借用层断言失败。
        """
        for after in (False, True):
            with self.subTest(after=after):
                data = self.shared()
                store = self.store(budget=data.budget)
                before = data.budget.ram_bytes
                reserve, calls = data.budget.reserve_ram, []
                marker = KeyboardInterrupt('fixed reserve cancellation')

                def cancel(amount):
                    """命中工厂首笔真实预约。参数: amount。返回: 无。异常: 同一marker。"""
                    calls.append(amount)
                    if after:
                        reserve(amount)
                    raise marker

                with patch.object(data.budget, 'reserve_ram', new=cancel), \
                        patch.object(store, 'iter_records', wraps=store.iter_records) as reader:
                    with self.assertRaises(KeyboardInterrupt) as caught:
                        bind_message_store(self.declarations, store)
                    reader.assert_not_called()
                self.assertIs(caught.exception, marker)
                self.assertEqual(len(calls), 1)
                owner = self.recovery(marker)
                owner.close()
                self.assertTrue(owner.closed)
                self.assertEqual(data.budget.ram_bytes, before)
                self.assertFalse(store.closed)
                store.close()
                self.assert_shared(data)

    def test_returned_lease_release_before_after_cancel_is_retryable_without_parent_close(self):
        """已返回lease抵费前持续三次/后一次取消不重扣，且不关闭同仓外部reader。

        参数: 无。返回: None。异常: 原KI、最高owner、FD隔离或金额不符时失败。
        """
        for after in (False, True):
            with self.subTest(after=after):
                store = self.store()
                external = store.iter_records()
                baseline = store.budget.ram_bytes
                owner = self.lease(store)
                fee = owner._held_cost
                self.assertGreater(fee, 0)
                release, calls = store.budget.release_ram, []
                marker = KeyboardInterrupt('returned lease release cancellation')

                def cancel(amount):
                    """只命中该真实lease金额。参数: amount。返回: 原返回或无。异常: 同一marker。"""
                    if amount != fee:
                        return release(amount)
                    calls.append(amount)
                    if after:
                        release(amount)
                    raise marker

                with patch.object(store.budget, 'release_ram', new=cancel), \
                        patch.object(store, 'close', wraps=store.close) as close_store:
                    for _ in range(1 if after else 3):
                        with self.assertRaises(KeyboardInterrupt) as caught:
                            owner.close()
                        self.assertIs(caught.exception, marker)
                        self.recovery(marker, owner)
                    if after:
                        owner.close()
                        self.assertEqual(len(calls), 1)
                    else:
                        self.assertGreaterEqual(len(calls), 3)
                        self.assertFalse(owner.closed)
                    close_store.assert_not_called()
                owner.close()
                owner.close()
                self.assertTrue(owner.closed)
                self.assertEqual(store.budget.ram_bytes, baseline)
                self.assertFalse(store.closed or external.closed or external.handle.closed)
                external.close()

    def test_real_read_primary_and_persistent_fd_close_preserve_both_owners(self):
        """真实第二次read原错配持续close副错保FD，lease只重试其reader而非借store。

        参数: 无。返回: None。异常: 原主错被覆盖、实际FD丢失或借款/兄弟仓受损时失败。
        """
        for error_type in (OSError, KeyboardInterrupt):
            with self.subTest(error_type=error_type.__name__):
                data = self.shared()
                store = self.store(budget=data.budget)
                primary, secondary = error_type('actual second read primary'), RuntimeError('persistent fd close')
                handles = []
                with patch.object(Path, 'open', new=self.opening(handles, read_error=primary,
                        close_error=secondary)):
                    with self.assertRaises(error_type) as caught:
                        bind_message_store(self.declarations, store)
                self.assertIs(caught.exception, primary)
                owner = self.recovery(primary)
                self.assertIs(getattr(primary, 'decoded_message_store_cleanup_owner', None), store)
                self.assertEqual(len(handles), 1)
                self.assertEqual(handles[0].read_calls, 2)
                self.assertFalse(handles[0].closed)
                self.assertIsNotNone(owner._reader)
                self.assertIsNone(owner._current)
                for _ in range(3):
                    with self.assertRaises(RuntimeError) as cleanup:
                        owner.close()
                    self.assertIs(cleanup.exception, secondary)
                    self.recovery(secondary, owner)
                self.assertGreaterEqual(handles[0].close_calls, 3)
                self.assertTrue(any('RuntimeError' in note for note in primary.__notes__))
                handles[0].close_error = handles[0].read_error = None
                with patch.object(store, 'close', wraps=store.close) as close_store:
                    owner.close()
                    close_store.assert_not_called()
                self.assertTrue(handles[0].closed)
                store.close()
                self.assert_shared(data)
        # close已经实际成功后再抛错，只能保原主错并按真实closed收尾，不能重复关FD。
        data = self.shared()
        store = self.store(budget=data.budget)
        primary, secondary = KeyboardInterrupt('read before post-close cancellation'), RuntimeError('after actual close')
        handles = []
        with patch.object(Path, 'open', new=self.opening(handles, read_error=primary,
                close_error=secondary, close_after=True)):
            with self.assertRaises(KeyboardInterrupt) as caught:
                bind_message_store(self.declarations, store)
        self.assertIs(caught.exception, primary)
        self.recovery(primary).close()
        self.assertIs(primary.decoded_message_store_cleanup_owner, store)
        self.assertEqual(len(handles), 1)
        self.assertTrue(handles[0].closed)
        self.assertEqual(handles[0].close_calls, 1)
        store.close()
        self.assert_shared(data)

    def test_real_eof_reader_fee_before_after_cancel_never_opens_completed_bindings(self):
        """真正EOF抵reader费前持续故障或抵费后取消，都不能开放半完成证据。

        参数: 无。返回: None。异常: 提前完成、费用重扣、原KI或资源事实不符时失败。
        """
        for after in (False, True):
            with self.subTest(after=after):
                data = self.shared()
                store = self.store(budget=data.budget)
                original, readers, fees = store.iter_records, [], []
                release, calls = data.budget.release_ram, []
                marker = KeyboardInterrupt('reader eof release cancellation')

                def observe_reader():
                    """记录同一实际reader金额。参数: 无。返回: 原reader。异常: 原构造错。"""
                    reader = original()
                    readers.append(reader)
                    fees.append(reader._held_cost)
                    return reader

                def cancel(amount):
                    """只命中实际子reader金额。参数: amount。返回: 原返回。异常: 同一marker。"""
                    if not fees or amount != fees[0]:
                        return release(amount)
                    calls.append(amount)
                    if after:
                        release(amount)
                    raise marker

                with patch.object(store, 'iter_records', new=observe_reader), \
                        patch.object(data.budget, 'release_ram', new=cancel):
                    with self.assertRaises(KeyboardInterrupt) as caught:
                        bind_message_store(self.declarations, store)
                    self.assertIs(caught.exception, marker)
                    owner = self.recovery(marker)
                    self.assertIs(getattr(marker, 'decoded_message_store_cleanup_owner', None), store)
                    self.assertEqual(len(readers), 1)
                    self.assertTrue(readers[0].handle.closed)
                    self.assertFalse(readers[0].verified_eof)
                    if after:
                        self.assertEqual(len(calls), 1)
                    else:
                        for _ in range(3):
                            with self.assertRaises(KeyboardInterrupt) as cleanup:
                                owner.close()
                            self.assertIs(cleanup.exception, marker)
                        self.assertGreaterEqual(len(calls), 3)
                owner.close()
                store.close()
                self.assert_shared(data)

    def test_unreturned_reader_remains_original_store_responsibility_not_borrowed_parent_adoption(self):
        """真实登记前后失败且FD持续关不掉时，未返回子由原store保留，lease不代关父。

        参数: 无。返回: None。异常: 未返回FD无owner、原主错覆盖或越权关闭借仓时失败。
        """
        # 首笔是lease固定费，第二笔才是原store真实reader；此处命中后者而非随机reserve。
        for after in (False, True):
            with self.subTest(reader_reserve_after=after):
                data = self.shared()
                store = self.store(budget=data.budget)
                reserve, amounts = data.budget.reserve_ram, []
                marker = KeyboardInterrupt('unreturned actual reader reserve')

                def cancel_reader(amount):
                    """首笔透传，第二笔原reader预约前后取消。参数: amount。返回: 原返回。异常: 同一marker。"""
                    amounts.append(amount)
                    if len(amounts) == 2:
                        if after:
                            reserve(amount)
                        raise marker
                    return reserve(amount)

                with patch.object(data.budget, 'reserve_ram', new=cancel_reader), \
                        patch.object(Path, 'open', side_effect=AssertionError('reserve must precede reader FD')) as open_file:
                    with self.assertRaises(KeyboardInterrupt) as caught:
                        bind_message_store(self.declarations, store)
                    open_file.assert_not_called()
                self.assertIs(caught.exception, marker)
                self.assertEqual(len(amounts), 2)
                self.assertGreater(amounts[1], amounts[0])
                owner = self.recovery(marker)
                self.assertIs(marker.decoded_message_store_cleanup_owner, store)
                self.assertTrue(owner.closed)
                self.assertIsNone(store._pending_reader)
                owner.close()
                store.close()
                self.assert_shared(data)
        for after in (False, True):
            with self.subTest(after=after):
                data = self.shared()
                store = self.store(budget=data.budget)
                primary, secondary = MemoryError('actual registration primary'), RuntimeError('pending fd close')
                registry = FailingRegistration(primary, after)
                store._readers = registry
                handles = []
                with patch.object(Path, 'open', new=self.opening(handles, close_error=secondary)):
                    with self.assertRaises(MemoryError) as caught:
                        bind_message_store(self.declarations, store)
                self.assertIs(caught.exception, primary)
                owner = self.recovery(primary)
                self.assertTrue(owner.closed)
                self.assertIsNone(owner._reader)
                self.assertIs(getattr(primary, 'decoded_message_store_cleanup_owner', None), store)
                self.assertIs(store._pending_reader, registry.reader)
                self.assertIsNotNone(registry.reader)
                self.assertEqual(len(handles), 1)
                self.assertFalse(handles[0].closed)
                with patch.object(store, 'close', wraps=store.close) as close_store:
                    owner.close()
                    close_store.assert_not_called()
                for _ in range(3):
                    with self.assertRaises(RuntimeError) as cleanup:
                        store.close()
                    self.assertIs(cleanup.exception, secondary)
                    self.assertIs(secondary.decoded_message_store_cleanup_owner, store)
                handles[0].close_error = None
                store.close()
                self.assertTrue(handles[0].closed)
                self.assertIsNone(store._pending_reader)
                self.assert_shared(data)


if __name__ == '__main__':
    # 根任务统一正式运行；模块导入仅定义测试和透明资源代理。
    unittest.main()
