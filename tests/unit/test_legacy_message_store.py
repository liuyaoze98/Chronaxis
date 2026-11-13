"""用完整手写解码帧及真实文件验证独立逐次仓的原序、严格格式和恢复责任。

输入是有限LegacyDecodedFrame及调用方已映射时间，不读取CAN或DBC，不生成旧求值点。
真值直接来自手写12字段、原字典和hashlib；同刻原序、缺key、非有限诊断均不修补。
原records仅支持数值/bool值，None/str保持构造拒绝，channel的None/str/int则合法。
磁盘外壳独立允许64KiB+1024，原IPC仍保持64KiB，不借临时放宽常量解析大包。

真实FD代理只在实际读写/flush/close前后注入；共享预算保调用方4096及另一活仓。
错误/取消保原对象、实际最高decoded_message_store_cleanup_owner和可重试资源槽，
完整EOF须核数量/SHA并成功关闭FD与费用。所有工件仅写work独占UUID目录并保留，
不删除Ref、不依赖其他TestCase，也不宣称B3已接CAN/表达式或整个进程RSS有界。
"""

from configuration_fixtures import current_fixture

from dataclasses import FrozenInstanceError
import gc
from hashlib import sha256
import json
from math import copysign, isnan
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4
import weakref

from chronaxis.legacy import message_store as module
from chronaxis.legacy import records as records_module
from chronaxis.legacy.message_store import (DecodedMessageStore, StoredDecodedMessage,
    MAX_DECODED_MESSAGE_ROW_BYTES)
from chronaxis.legacy.records import (LegacyDecodedFrame, LegacyRawFrame, MAX_WIRE_BYTES,
    decoded_to_dict, encode_packet)
from chronaxis.results import BudgetExceededError, ResourceBudget, ResultClosedError, ResultFormatError


def original_frame(index=0):
    """手写完整公开帧，覆盖64字节、FD标志及None/文本/非目标整数通道。

    参数: index为0/1/2。返回: LegacyRawFrame。异常: 原模型校验错误传播。
    """
    return LegacyRawFrame((-0.0, 1.25, 1.25)[index], 0x1fffffff - index, index != 1,
        index == 1, index == 2, ('原.channel\nA', None, -3)[index], 64, bytes(range(64)),
        index != 1, index == 1, index == 0, index == 2)


def original_decoded(index=0, *, sequence=None, values=None):
    """建立原数值/bool字典，不用被测仓的编码器生成独立真值。

    参数: index选择原帧；sequence可改原序负例；values可显式覆盖原字段字典。
    返回: LegacyDecodedFrame。异常: 原records类型/wire上限错误传播。
    """
    if values is None:
        values = {} if index == 1 else {'  原.Power  ': 0, 'flag': False, 'nan': float('nan'),
            'positive_inf': float('inf'), 'negative_inf': float('-inf'), 'negative_zero': -0.0,
            'large': (1 << 80) + 5}
    return LegacyDecodedFrame(index if sequence is None else sequence, original_frame(index), values)


class ActualFile:
    """透明代理本例真实FileIO；closed来自实际FD，不提供假成功或假文件内容。"""

    def __init__(self, actual):
        """保真实句柄和可恢复故障配置。参数: actual为FileIO。返回: 代理。异常: 无。"""
        self.actual = actual
        self.write_error = self.flush_error = self.close_error = self.read_error = None
        self.partial_bytes, self.close_calls, self.flush_calls, self.write_calls = 0, 0, 0, 0
        self.close_after = self.flush_after = False
        self.last_payload = None

    def __getattr__(self, name):
        """透传其余实际属性。参数: name为属性名。返回: 原属性。异常: 原属性错误。"""
        return getattr(self.actual, name)

    def write(self, payload):
        """可真实写前缀后抛原错误，或返回真实短写量。

        参数: payload为原bytes-like。返回: 原实际写入量。异常: write_error或原文件错误。
        """
        self.write_calls += 1
        if self.write_error is not None:
            self.last_payload = payload
            if self.partial_bytes:
                self.actual.write(payload[:self.partial_bytes])
            raise self.write_error
        return self.actual.write(payload[:self.partial_bytes] if self.partial_bytes else payload)

    def flush(self):
        """在实际flush前后持续故障。参数: 无。返回: 原返回。异常: flush_error或原IO错。"""
        self.flush_calls += 1
        if self.flush_error is not None and not self.flush_after:
            raise self.flush_error
        value = self.actual.flush()
        if self.flush_error is not None:
            raise self.flush_error
        return value

    def close(self):
        """在实际close前后持续故障。参数: 无。返回: 原返回。异常: close_error或原IO错。"""
        self.close_calls += 1
        if self.close_error is not None and not self.close_after:
            raise self.close_error
        value = self.actual.close()
        if self.close_error is not None:
            raise self.close_error
        return value

    def readline(self, size):
        """透传限长真实读取或抛同一原主错。参数: size。返回: 原bytes。异常: read_error/IO错。"""
        if self.read_error is not None:
            raise self.read_error
        return self.actual.readline(size)


class RegistrationFailure(set):
    """在真实reader登记前或后抛错，保实际reader用于核未返回FD责任。"""

    def __init__(self, error, after):
        """保存原错误及位置。参数: error/after。返回: 空登记集。异常: 原分配错误。"""
        super().__init__()
        self.error, self.after, self.reader = error, after, None

    def add(self, reader):
        """观察实际登记并失败。参数: 真reader。返回: 无。异常: 同一error。"""
        self.reader = reader
        if self.after:
            super().add(reader)
        raise self.error


class CodecTemporary:
    """仅用于真实records编码错误的弱引用资源，不能成为合法wire值。"""


class LegacyMessageStoreTests(unittest.TestCase):
    """每例真实仓/FD/账本独立；故障恢复前核资源事实，最终清理不代替及时关闭断言。"""

    def setUp(self):
        """建立本例唯一work根并登记实际资源。参数: 无。返回: None。异常: 原目录错误。"""
        self.root = Path(__file__).resolve().parents[2] / 'work/m2-legacy-tests/message-store' / uuid4().hex
        self.root.mkdir(parents=True)
        self.owners, self.budgets, self.handles = [], [], []

    def tearDown(self):
        """停用测试故障后仅由真实owner关闭资源，核借款保留，工件不删除。

        参数: 无。返回: None。异常: 实际关闭、漏账或多抵销借款直接使测试失败。
        """
        for handle in self.handles:
            handle.write_error = handle.flush_error = handle.close_error = handle.read_error = None
        for owner in reversed(self.owners):
            owner.close()
        for budget in self.budgets:
            self.assertEqual(budget.ram_bytes, 4096)
            budget.release_ram(4096)
            self.assertEqual(budget.ram_bytes, 0)

    def budget(self, *, quota=None, memory=64 * 1024**2):
        """建立实际共享账本并保调用方4096标记。参数: quota/memory。返回: budget。异常: 原预算错。"""
        budget = ResourceBudget(memory, quota)
        budget.reserve_ram(4096)
        self.budgets.append(budget)
        return budget

    def store(self, name=None, *, budget=None, max_row_bytes=MAX_DECODED_MESSAGE_ROW_BYTES):
        """真实构造并登记成功owner，绝不通过__new__生成半初始化仓。

        参数: name为本例新子目录；budget可共享；max_row_bytes为明确行上限。
        返回: DecodedMessageStore。异常: 原构造/预算/IO错误。
        """
        if name is None:
            name = 'store-' + str(len(self.owners))
        owner = DecodedMessageStore(self.budget() if budget is None else budget, self.root / name,
            'bus', 'session', decoder_profile='explicit-decoded-v1', read_identity='actual-read-1',
            max_row_bytes=max_row_bytes)
        self.owners.append(owner)
        return owner

    def populated(self, name=None, *, budget=None):
        """写三条原序0/1/2、时间5/5/9并真实seal。参数: name/budget。返回: 仓。异常: 原错误。"""
        owner = self.store(name, budget=budget)
        for index, time_ns in enumerate((5, 5, 9)):
            owner.append(original_decoded(index), time_ns, time_quantized=index == 1)
        owner.seal()
        return owner

    def shared(self):
        """保另一封口仓及未读活reader，证明本仓失败不会关闭借用层的真实FD。

        参数: 无。返回: 含budget/sibling/reader/基线的有限夹具。异常: 原文件/预算错误。
        """
        budget = self.budget()
        sibling = self.populated('sibling-' + str(len(self.owners)), budget=budget)
        reader = sibling.iter_records()
        return SimpleNamespace(budget=budget, sibling=sibling, reader=reader, baseline=budget.ram_bytes)

    def assert_shared(self, data):
        """核借用仓与实际FD仍活，RAM只回原借用基线。参数: data。返回: None。异常: 误关/漏账失败。"""
        self.assertFalse(data.sibling.closed)
        self.assertFalse(data.reader.closed or data.reader.handle.closed)
        self.assertEqual(data.sibling.count, 3)
        self.assertEqual(data.budget.ram_bytes, data.baseline)

    def recovered(self, error, expected=None):
        """核异常最高实际父仓并登记最终清理。参数: 原error/可选expected。返回: 真仓。异常: 缺失/身份错失败。"""
        owner = getattr(error, 'decoded_message_store_cleanup_owner', None)
        self.assertIs(type(owner), DecodedMessageStore)
        if expected is not None:
            self.assertIs(owner, expected)
        if not any(item is owner for item in self.owners):
            self.owners.append(owner)
        return owner

    def wrap_writer(self, owner):
        """仅代理owner真实已打开writer，不替换文件或重建假句柄。

        参数: owner为building仓。返回: ActualFile。异常: 无实际writer时直接失败。
        """
        wrapped = ActualFile(owner._writer)
        owner._writer = wrapped
        self.handles.append(wrapped)
        return wrapped

    def assert_values(self, actual, expected):
        """逐项核原值类型、NaN及负零，避免普通dict相等掩盖False/0或NaN问题。

        参数: actual/expected为有限原字段映射。返回: None。异常: 类型/原值/字段改变即失败。
        """
        # 原records编码按键排序，不承诺字典插入顺序；字段集合完整与帧原序分别验证。
        self.assertEqual(set(actual), set(expected))
        for key, value in expected.items():
            self.assertIs(type(actual[key]), type(value))
            if type(value) is float and isnan(value):
                self.assertTrue(isnan(actual[key]))
            else:
                self.assertEqual(actual[key], value)
                if type(value) is float and value == 0:
                    self.assertEqual(copysign(1.0, actual[key]), copysign(1.0, value))

    def test_frozen_record_model_and_existing_decoded_value_contract(self):
        """存储模型不换算时间或原帧；量化必须bool，原records仍拒None/str解码值。

        参数: 无。返回: None。异常: 隐式强转、扩张IPC原值域或冻结被破坏时失败。
        """
        decoded = original_decoded()
        for time_ns in (-(1 << 63), (1 << 63) - 1):
            stored = StoredDecodedMessage(time_ns, True, decoded)
            self.assertIs(stored.decoded, decoded)
            self.assertEqual(stored.time_ns, time_ns)
            self.assertIs(stored.time_quantized, True)
            with self.assertRaises(FrozenInstanceError):
                stored.time_ns = 0
        for changes, error in (({'time_ns': 1 << 63}, OverflowError),
                ({'time_ns': -(1 << 63) - 1}, OverflowError), ({'time_ns': True}, TypeError),
                ({'time_ns': 0.0}, TypeError), ({'time_quantized': 1}, TypeError),
                ({'time_quantized': None}, TypeError), ({'decoded': object()}, TypeError)):
            with self.subTest(changes=changes):
                values = dict(time_ns=0, time_quantized=False, decoded=decoded)
                values.update(changes)
                with self.assertRaises(error):
                    StoredDecodedMessage(**values)
        for value in (None, 'unsupported enum label'):
            with self.subTest(decoded_value=value):
                with self.assertRaises(TypeError):
                    original_decoded(values={'P': value})

    def test_full_fields_same_time_and_original_values_roundtrip_with_actual_sha(self):
        """三帧所有字段/同刻/原值无损，独立读文件核固定外层、数量、SHA和真实reader收尾。

        参数: 无。返回: None。异常: 字段修补、去重、虚假完整性或费用错误时失败。
        """
        owner = self.populated()
        payload = owner.file_path.read_bytes()
        self.assertEqual(owner.file_path.name, 'decoded_messages.jsonl')
        self.assertEqual((owner.source_name, owner.session_id, owner.decoder_profile, owner.read_identity),
            ('bus', 'session', 'explicit-decoded-v1', 'actual-read-1'))
        self.assertEqual((owner.count, owner.sha256, owner.spool_bytes), (3, sha256(payload).hexdigest(), len(payload)))
        self.assertIsNone(owner._writer)
        packets = [json.loads(line) for line in payload.splitlines()]
        self.assertTrue(all(set(packet) == {'store_version', 'time_ns', 'time_quantized', 'decoded'} for packet in packets))
        self.assertEqual([packet['decoded']['sequence'] for packet in packets], [0, 1, 2])
        self.assertEqual([packet['time_ns'] for packet in packets], [5, 5, 9])
        self.assertEqual([packet['time_quantized'] for packet in packets], [False, True, False])
        self.assertEqual(packets[0]['decoded']['values']['nan'], {'diagnostic_float': 'nan'})
        reader = owner.iter_records()
        handle = reader.handle
        rows = tuple(reader)
        self.assertEqual(len(rows), 3)
        self.assertTrue(reader.verified_eof and reader.closed and handle.closed)
        for index, stored in enumerate(rows):
            expected = original_decoded(index)
            self.assertIs(type(stored), StoredDecodedMessage)
            self.assertEqual((stored.time_ns, stored.time_quantized), ((5, 5, 9)[index], index == 1))
            self.assertEqual(stored.decoded.frame, expected.frame)
            self.assertEqual(stored.decoded.frame.timestamp.hex(), expected.frame.timestamp.hex())
            self.assertEqual(stored.decoded.sequence, index)
            self.assert_values(stored.decoded.values, expected.values)
        self.assertEqual(dict(rows[1].decoded.values), {})
        owner.close()
        self.assertEqual(owner.budget.ram_bytes, 4096)
        self.assertTrue(owner.file_path.is_file())

    def test_empty_source_and_independent_readers_require_real_final_eof(self):
        """空源可真EOF；两reader各自位置，末行交付及提前close都不产生完整证明。

        参数: 无。返回: None。异常: 状态、独立FD、verified_eof或预算结算错误时失败。
        """
        empty = self.store('empty')
        with self.assertRaises(RuntimeError):
            empty.iter_records()
        empty.seal()
        self.assertEqual((empty.count, empty.sha256), (0, sha256(b'').hexdigest()))
        reader = empty.iter_records()
        self.assertEqual(tuple(reader), ())
        self.assertTrue(reader.verified_eof and reader.closed and reader.handle.closed)
        owner = self.populated('populated')
        baseline = owner.budget.ram_bytes
        first, second = owner.iter_records(), owner.iter_records()
        self.assertIsNot(first.handle, second.handle)
        self.assertEqual(next(first).decoded.sequence, 0)
        self.assertEqual(next(second).decoded.sequence, 0)
        self.assertEqual([next(first).decoded.sequence for _ in range(2)], [1, 2])
        self.assertFalse(first.verified_eof)
        second.close()
        self.assertFalse(second.verified_eof)
        with self.assertRaises(StopIteration):
            next(first)
        self.assertTrue(first.verified_eof and first.closed and first.handle.closed)
        self.assertEqual(owner.budget.ram_bytes, baseline)
        owner.close()
        with self.assertRaises(ResultClosedError):
            owner.iter_records()

    def test_sequence_time_quantization_and_int64_rules_poison_invalid_append(self):
        """连续原序和非递减时间严格核，单端int64合法不因跨度大被Interval额外拒绝。

        参数: 无。返回: None。异常: 重排、同序重复、错误量化或越界被接受时失败。
        """
        cases = ((1, 5, False, False), (0, 5, False, True), (1, 4, False, True),
            (0, 1 << 63, False, False), (0, 5, 1, False))
        for index, (sequence, time_ns, quantized, seed) in enumerate(cases):
            with self.subTest(index=index):
                owner = self.store('invalid-' + str(index))
                if seed:
                    owner.append(original_decoded(), 5, time_quantized=False)
                with self.assertRaises((TypeError, ValueError, OverflowError)):
                    owner.append(original_decoded(sequence=sequence), time_ns, time_quantized=quantized)
                self.assertIn(owner.state, ('failed', 'cancelled'))
                self.assertIsNone(owner.sha256)
                with self.assertRaises(ResultClosedError):
                    owner.seal()
                owner.close()
                self.assertEqual(owner.budget.ram_bytes, 4096)
        owner = self.store('wide-endpoints')
        owner.append(original_decoded(0), -(1 << 63), time_quantized=False)
        owner.append(original_decoded(1), (1 << 63) - 1, time_quantized=True)
        owner.seal()
        reader = owner.iter_records()
        self.assertEqual([row.time_ns for row in reader], [-(1 << 63), (1 << 63) - 1])
        self.assertTrue(reader.verified_eof)

    def test_disk_envelope_can_exceed_ipc_without_relaxing_original_wire_limit(self):
        """合法原ITEM满64KiB时磁盘外壳仍可读，整磁盘包交旧IPC则依然明确拒绝。

        参数: 无。返回: None。异常: 偷改wire上限、截断原字段或外壳超限定被接受时失败。
        """
        empty = original_decoded(values={})
        base = len(encode_packet(dict(operation='item', request_id=0, record=decoded_to_dict(empty))))
        # 新增ASCII键值项相对空{}恰多len(key)+4字节；ITEM恰达到原有公开wire限制。
        key = 'x' * (MAX_WIRE_BYTES - base - 4)
        record = original_decoded(values={key: 0})
        original_item = encode_packet(dict(operation='item', request_id=0, record=decoded_to_dict(record)))
        self.assertEqual(len(original_item), MAX_WIRE_BYTES)
        owner = self.store()
        owner.append(record, (1 << 63) - 1, time_quantized=True)
        owner.seal()
        payload = owner.file_path.read_bytes()
        self.assertEqual(MAX_DECODED_MESSAGE_ROW_BYTES, MAX_WIRE_BYTES + 1024)
        self.assertGreater(len(payload), MAX_WIRE_BYTES)
        self.assertLessEqual(len(payload), MAX_DECODED_MESSAGE_ROW_BYTES)
        self.assertEqual(MAX_WIRE_BYTES, 65536)
        with self.assertRaises(ValueError):
            encode_packet(json.loads(payload))
        reader = owner.iter_records()
        rows = tuple(reader)
        self.assertEqual(len(rows), 1)
        self.assertEqual(dict(rows[0].decoded.values), {key: 0})
        self.assertTrue(reader.verified_eof and reader.handle.closed)

    def test_strict_outer_decoded_types_duplicate_keys_and_line_limit_are_rejected(self):
        """从实际合法行窄改外层/decoded结构与原生类型，严格拒未知/重复/越界行。

        参数: 无。返回: None。异常: 任一非法磁盘行产生完成证明或资源不可恢复时失败。
        """
        cases = ('version_bool', 'version_unknown', 'outer_extra', 'outer_missing', 'quantized_int',
            'time_bool', 'decoded_extra', 'sequence_bool', 'frame_flag_int', 'diagnostic_unknown',
            'duplicate_outer', 'duplicate_value', 'bare_nan', 'malformed_decoded_json',
            'invalid_utf8', 'row_too_long')
        for index, case in enumerate(cases):
            with self.subTest(case=case):
                owner = self.populated('format-' + str(index))
                lines = owner.file_path.read_bytes().splitlines(keepends=True)
                packet = json.loads(lines[0])
                if case == 'version_bool':
                    packet['store_version'] = True
                elif case == 'version_unknown':
                    packet['store_version'] = 2
                elif case == 'outer_extra':
                    packet['unknown'] = 1
                elif case == 'outer_missing':
                    del packet['time_quantized']
                elif case == 'quantized_int':
                    packet['time_quantized'] = 0
                elif case == 'time_bool':
                    packet['time_ns'] = False
                elif case == 'decoded_extra':
                    packet['decoded']['unknown'] = 1
                elif case == 'sequence_bool':
                    packet['decoded']['sequence'] = False
                elif case == 'frame_flag_int':
                    packet['decoded']['frame']['is_fd'] = 1
                elif case == 'diagnostic_unknown':
                    packet['decoded']['values']['nan'] = {'diagnostic_float': 'unknown'}
                if case == 'duplicate_outer':
                    changed = lines[0].replace(b'"store_version":1', b'"store_version":1,"store_version":1', 1)
                    self.assertNotEqual(changed, lines[0])
                elif case == 'duplicate_value':
                    changed = lines[0].replace(b'"flag":false', b'"flag":false,"flag":true', 1)
                    self.assertNotEqual(changed, lines[0])
                elif case == 'bare_nan':
                    changed = lines[0].replace(b'{"diagnostic_float":"nan"}', b'NaN', 1)
                    self.assertNotEqual(changed, lines[0])
                elif case == 'malformed_decoded_json':
                    changed = lines[0].replace(b'"sequence":0', b'"sequence":', 1)
                    self.assertNotEqual(changed, lines[0])
                elif case == 'invalid_utf8':
                    changed = lines[0].replace(b'"flag":false', b'"\xff":false', 1)
                    self.assertNotEqual(changed, lines[0])
                elif case == 'row_too_long':
                    changed = b' ' * MAX_DECODED_MESSAGE_ROW_BYTES + b'\n'
                else:
                    changed = (json.dumps(current_fixture(packet), ensure_ascii=False, allow_nan=False,
                        separators=(',', ':')) + '\n').encode('utf-8')
                owner.file_path.write_bytes(changed + b''.join(lines[1:]))
                reader = owner.iter_records()
                handle = reader.handle
                with self.assertRaises(ResultFormatError) as caught:
                    tuple(reader)
                if case == 'malformed_decoded_json':
                    # 清codec临时frame不能删除原JSON错误供调用方保留的有界诊断。
                    self.assertIsInstance(caught.exception.__cause__, json.JSONDecodeError)
                    self.assertIn('"sequence":,', caught.exception.__cause__.doc)
                    self.assertGreater(caught.exception.__cause__.pos, 0)
                elif case == 'invalid_utf8':
                    self.assertIsInstance(caught.exception.__cause__, UnicodeDecodeError)
                    self.assertIn(b'\xff', caught.exception.__cause__.object)
                self.recovered(caught.exception, owner)
                self.assertFalse(reader.verified_eof)
                owner.close()
                self.assertTrue(handle.closed and reader.closed)
                self.assertEqual(owner.budget.ram_bytes, 4096)

    def test_legal_tail_tamper_truncation_and_appended_record_fail_integrity(self):
        """合法值尾改保条数/顺序，整行截断及追加也必须在完整回读时拒绝。

        参数: 无。返回: None。异常: SHA/条数不核或提前交付末行就verified时失败。
        """
        for case in ('legal_tail', 'removed_last_line', 'truncated_last_line', 'appended_record'):
            with self.subTest(case=case):
                owner = self.populated(case)
                lines = owner.file_path.read_bytes().splitlines(keepends=True)
                if case == 'legal_tail':
                    packet = json.loads(lines[-1])
                    packet['decoded']['values']['large'] += 1
                    lines[-1] = (json.dumps(current_fixture(packet), ensure_ascii=False, allow_nan=False,
                        separators=(',', ':')) + '\n').encode('utf-8')
                elif case == 'removed_last_line':
                    lines = lines[:-1]
                elif case == 'truncated_last_line':
                    lines[-1] = lines[-1][:-17]
                else:
                    packet = json.loads(lines[-1])
                    packet['decoded']['sequence'] = 3
                    lines.append((json.dumps(current_fixture(packet), ensure_ascii=False, allow_nan=False,
                        separators=(',', ':')) + '\n').encode('utf-8'))
                owner.file_path.write_bytes(b''.join(lines))
                reader = owner.iter_records()
                handle = reader.handle
                with self.assertRaises(ResultFormatError) as caught:
                    tuple(reader)
                if case == 'legal_tail':
                    self.assertRegex(str(caught.exception), '摘要|SHA')
                self.assertFalse(reader.verified_eof)
                self.recovered(caught.exception, owner)
                owner.close()
                self.assertTrue(reader.closed and handle.closed)
                self.assertEqual(owner.budget.ram_bytes, 4096)

    def test_row_ram_and_spool_capacity_are_reserved_before_actual_write(self):
        """行上限、真实RAM容量与磁盘配额都在write前拒绝，不能写部分行后冒充预算检查。

        参数: 无。返回: None。异常: 预付顺序、count/SHA或实际文件内容不符时失败。
        """
        for case in ('row_limit', 'ram_limit', 'spool_limit'):
            with self.subTest(case=case):
                if case == 'ram_limit':
                    probe = self.store('cost-probe')
                    fixed = probe.budget.ram_bytes - 4096
                    probe.close()
                    budget = self.budget(memory=4096 + fixed + 1)
                else:
                    budget = self.budget(quota=1 if case == 'spool_limit' else None)
                owner = self.store(case, budget=budget, max_row_bytes=1 if case == 'row_limit'
                    else MAX_DECODED_MESSAGE_ROW_BYTES)
                wrapped = self.wrap_writer(owner)
                with self.assertRaises(ValueError if case == 'row_limit' else BudgetExceededError):
                    owner.append(original_decoded(), 5, time_quantized=False)
                self.assertEqual(wrapped.write_calls, 0)
                self.assertEqual(owner.count, 0)
                self.assertIsNone(owner.sha256)
                owner.close()
                self.assertTrue(wrapped.actual.closed)
                self.assertEqual(owner.file_path.read_bytes(), b'')
                self.assertEqual(budget.ram_bytes, 4096)
                self.assertEqual(budget.spool_bytes, 0)

    def test_append_ram_and_spool_cancel_before_after_keep_original_and_real_accounting(self):
        """两笔真实申请前后KI均保原对象；RAM回借用基线，已预留spool不虚构归还。

        参数: 无。返回: None。异常: 注入未命中、最高父丢失、错误替换或借款被抵销时失败。
        """
        for method_name in ('reserve_ram', 'reserve_spool'):
            for after in (False, True):
                with self.subTest(method=method_name, after=after):
                    data = self.shared()
                    owner = self.store(budget=data.budget)
                    handle = owner._writer
                    original = getattr(data.budget, method_name)
                    marker, calls = KeyboardInterrupt(method_name + ' before/after'), []
                    spool_before = data.budget.spool_bytes

                    def fail_reserve(amount):
                        """围绕单笔实际预约取消。参数: amount。返回: 无。异常: 同一marker。"""
                        calls.append(amount)
                        if after:
                            original(amount)
                        raise marker

                    with patch.object(data.budget, method_name, side_effect=fail_reserve):
                        with self.assertRaises(KeyboardInterrupt) as caught:
                            owner.append(original_decoded(), 5, time_quantized=False)
                    self.assertIs(caught.exception, marker)
                    self.assertEqual(len(calls), 1)
                    self.assertGreater(calls[0], 0)
                    self.recovered(marker, owner).close()
                    self.assertTrue(handle.closed)
                    self.assertEqual(owner.count, 0)
                    self.assertEqual(owner.file_path.read_bytes(), b'')
                    expected = calls[0] if method_name == 'reserve_spool' and after else 0
                    self.assertEqual(owner.spool_bytes, expected)
                    self.assertEqual(data.budget.spool_bytes, spool_before + expected)
                    self.assert_shared(data)

    def test_constructor_budget_cancel_and_real_directory_protection(self):
        """构造首笔预约前后取消交真实owner；拒绝已有目标，客户同名目录可用。

        参数: 无。返回: None。异常: 假owner、预算漏账或已有/受保护目录被改写时失败。
        """
        for after in (False, True):
            with self.subTest(after=after):
                data = self.shared()
                original = data.budget.reserve_ram
                marker, calls = KeyboardInterrupt('construct reserve boundary'), []

                def fail_reserve(amount):
                    """实际构造预付前后取消。参数: amount。返回: 无。异常: marker原对象。"""
                    calls.append(amount)
                    if after:
                        original(amount)
                    raise marker

                with patch.object(data.budget, 'reserve_ram', side_effect=fail_reserve):
                    with self.assertRaises(KeyboardInterrupt) as caught:
                        DecodedMessageStore(data.budget, self.root / ('construct-' + str(after)), 'bus', 'session',
                            decoder_profile='explicit-decoded-v1', read_identity='actual-read-1')
                self.assertIs(caught.exception, marker)
                self.assertEqual(len(calls), 1)
                self.recovered(marker).close()
                self.assert_shared(data)
        existing = self.root / 'existing'
        existing.mkdir()
        sentinel = existing / 'keep.bin'
        sentinel.write_bytes(b'original')
        budget = self.budget()
        with self.assertRaises(FileExistsError):
            DecodedMessageStore(budget, existing, 'bus', 'session', decoder_profile='profile', read_identity='read')
        self.assertEqual(sentinel.read_bytes(), b'original')
        self.assertEqual(tuple(existing.iterdir()), (sentinel,))
        allowed = self.root / 'RefProjects' / 'new'
        allowed.parent.mkdir()
        marker=allowed.parent/'user.txt'
        marker.write_bytes(b'keep')
        owner=DecodedMessageStore(budget, allowed, 'bus', 'session', decoder_profile='profile', read_identity='read')
        self.assertTrue(owner.file_path.is_file())
        owner.close()
        self.assertEqual(marker.read_bytes(),b'keep')
        self.assertEqual(budget.ram_bytes, 4096)
        # writer尚未返回时，构造原错加持续RAM收尾副错也必须保同一真实未返回父。
        data = self.shared()
        primary, secondary = OSError('writer open injection'), RuntimeError('constructor cleanup release')
        releases = []

        def fail_release(amount):
            """阻止构造已付费的真实释放。参数: amount。返回: 无。异常: secondary原对象。"""
            releases.append(amount)
            raise secondary

        with patch.object(Path, 'open', side_effect=primary), \
                patch.object(data.budget, 'release_ram', side_effect=fail_release):
            with self.assertRaises(OSError) as caught:
                DecodedMessageStore(data.budget, self.root / 'constructor-open', 'bus', 'session',
                    decoder_profile='profile', read_identity='read')
            self.assertIs(caught.exception, primary)
            owner = self.recovered(primary)
            self.assertIsNone(owner._writer)
            self.assertFalse(owner.closed)
            for _ in range(3):
                with self.assertRaises(RuntimeError) as cleanup:
                    owner.close()
                self.assertIs(cleanup.exception, secondary)
                self.recovered(secondary, owner)
            self.assertGreaterEqual(len(releases), 3)
            self.assertTrue(getattr(primary, '__notes__', ()))
        owner.close()
        self.assertTrue(owner.closed)
        self.assert_shared(data)

    def test_large_native_constructor_metadata_is_budgeted_before_validation_or_path_copy(self):
        """小真实预算先拒大原文本，不能先strip/校标识或构造本层Path副本再报超限。

        参数: 无。返回: None。异常: 预付晚于复制验证、原预算错误替换或创建目录时失败。
        Path对象由调用方建立的表示不在本例范围，本例只给native str且不读私有路径缓存。
        """
        large = ' ' * 32768 + 'explicit-large-native-text'
        for changed in ('decoder_profile', 'read_identity', 'work_dir'):
            with self.subTest(changed=changed):
                budget = self.budget(memory=4097)
                arguments = dict(work_dir=str(self.root / ('not-created-' + changed)),
                    decoder_profile='explicit-profile', read_identity='explicit-read')
                arguments[changed] = arguments[changed] + large if changed == 'work_dir' else large
                before = tuple(self.root.iterdir())
                reserve, path_new = budget.reserve_ram, module.Path.__new__
                path_calls, budget_errors = [], []

                def observe_path(cls, *args, **kwargs):
                    """观察真实Path构造，类型检查仍用原Path类。参数: 原构造参数。返回: 原Path。异常: 原错。"""
                    path_calls.append(args)
                    return path_new(cls, *args, **kwargs)

                def observe_reserve(amount):
                    """调用真实小账本并保它实际生成的异常。参数: amount。返回: 原返回。异常: 原BudgetExceededError。"""
                    try:
                        return reserve(amount)
                    except BudgetExceededError as error:
                        budget_errors.append(error)
                        raise

                with patch.object(module, 'require_identifier', wraps=module.require_identifier) as identifier, \
                        patch.object(module, 'require_text', wraps=module.require_text) as text, \
                        patch.object(module.Path, '__new__', new=observe_path), \
                        patch.object(budget, 'reserve_ram', new=observe_reserve):
                    with self.assertRaises(BudgetExceededError) as caught:
                        DecodedMessageStore(budget, arguments['work_dir'], 'bus', 'session',
                            decoder_profile=arguments['decoder_profile'], read_identity=arguments['read_identity'])
                self.assertEqual(len(budget_errors), 1)
                self.assertIs(caught.exception, budget_errors[0])
                identifier.assert_not_called()
                text.assert_not_called()
                self.assertEqual(path_calls, [])
                owner = self.recovered(caught.exception)
                self.assertIsNone(owner.path)
                self.assertIsNone(owner.file_path)
                owner.close()
                self.assertEqual(budget.ram_bytes, 4096)
                self.assertEqual(tuple(self.root.iterdir()), before)

    def test_real_short_write_and_partial_failure_preserve_primary_and_fd_recovery(self):
        """真实短写可完整推进；写五字节后主错配持续close副错不丢FD或覆盖原主错。

        参数: 无。返回: None。异常: 原计数/SHA/错误身份或最高owner恢复断言失败。
        """
        owner = self.store('short-success')
        wrapped = self.wrap_writer(owner)
        wrapped.partial_bytes = 5
        owner.append(original_decoded(), 5, time_quantized=False)
        owner.seal()
        self.assertGreater(wrapped.write_calls, 1)
        self.assertEqual(owner.count, 1)
        self.assertEqual(owner.sha256, sha256(owner.file_path.read_bytes()).hexdigest())
        self.assertTrue(wrapped.actual.closed)
        for primary in (RuntimeError('partial write primary'), KeyboardInterrupt('partial write primary')):
            with self.subTest(primary=type(primary).__name__):
                data = self.shared()
                owner = self.store(budget=data.budget)
                wrapped = self.wrap_writer(owner)
                wrapped.partial_bytes, wrapped.write_error = 5, primary
                secondary = RuntimeError('persistent close secondary')
                wrapped.close_error = secondary
                with self.assertRaises(type(primary)) as caught:
                    owner.append(original_decoded(), 5, time_quantized=False)
                self.assertIs(caught.exception, primary)
                self.recovered(primary, owner)
                self.assertEqual(owner.count, 0)
                self.assertIsNone(owner.sha256)
                self.assertFalse(wrapped.actual.closed or owner.closed)
                self.assertEqual(owner.file_path.stat().st_size, 5)
                # 即使外部代理强保传入view，产品也须release它，不能继续保活待写bytes。
                self.assertIs(type(wrapped.last_payload), memoryview)
                with self.assertRaises(ValueError):
                    len(wrapped.last_payload)
                for _ in range(3):
                    with self.assertRaises(RuntimeError) as cleanup:
                        owner.close()
                    self.assertIs(cleanup.exception, secondary)
                    self.recovered(secondary, owner)
                self.assertGreaterEqual(wrapped.close_calls, 3)
                self.assertTrue(getattr(primary, '__notes__', ()))
                wrapped.close_error = None
                owner.close()
                owner.close()
                self.assertTrue(owner.closed and wrapped.actual.closed)
                self.assertIsNone(owner._pending_payload)
                self.assert_shared(data)

    def test_seal_flush_and_close_before_after_failures_never_publish_sealed_sha(self):
        """真实flush/close边界任一取消都不封口，count可保留但SHA/可读完成事实不能开放。

        参数: 无。返回: None。异常: 原取消替换、假sealed或真实FD不可恢复时失败。
        """
        for operation in ('flush', 'close'):
            for after in (False, True):
                with self.subTest(operation=operation, after=after):
                    data = self.shared()
                    owner = self.store(budget=data.budget)
                    wrapped = self.wrap_writer(owner)
                    owner.append(original_decoded(), 5, time_quantized=False)
                    marker = KeyboardInterrupt('seal ' + operation)
                    setattr(wrapped, operation + '_error', marker)
                    setattr(wrapped, operation + '_after', after)
                    with self.assertRaises(KeyboardInterrupt) as caught:
                        owner.seal()
                    self.assertIs(caught.exception, marker)
                    self.recovered(marker, owner)
                    self.assertNotEqual(owner.state, 'sealed')
                    self.assertEqual(owner.count, 1)
                    self.assertIsNone(owner.sha256)
                    with self.assertRaises(ResultClosedError):
                        owner.iter_records()
                    wrapped.flush_error = wrapped.close_error = None
                    owner.close()
                    self.assertTrue(wrapped.actual.closed and owner.closed)
                    self.assert_shared(data)

    def test_eof_verification_waits_for_successful_actual_reader_close(self):
        """完整行数和SHA已到EOF但FD持续关失败时，verified_eof仍为False并保最高父。

        参数: 无。返回: None。异常: 提前完成证明、原取消覆盖或借用FD误关时失败。
        """
        data = self.shared()
        owner = self.populated('eof-close', budget=data.budget)
        reader = owner.iter_records()
        wrapped = ActualFile(reader.handle)
        self.handles.append(wrapped)
        reader.handle = wrapped
        self.assertEqual([next(reader).decoded.sequence for _ in range(3)], [0, 1, 2])
        marker = KeyboardInterrupt('EOF reader close persistent')
        wrapped.close_error = marker
        with self.assertRaises(KeyboardInterrupt) as caught:
            next(reader)
        self.assertIs(caught.exception, marker)
        self.recovered(marker, owner)
        self.assertFalse(reader.verified_eof or wrapped.actual.closed)
        for _ in range(3):
            with self.assertRaises(KeyboardInterrupt) as cleanup:
                owner.close()
            self.assertIs(cleanup.exception, marker)
        self.assertFalse(reader.verified_eof)
        self.assertGreaterEqual(wrapped.close_calls, 3)
        wrapped.close_error = None
        owner.close()
        self.assertTrue(reader.closed and wrapped.actual.closed)
        self.assertFalse(reader.verified_eof)
        self.assert_shared(data)

    def test_reader_close_before_after_cancel_preserves_other_same_store_reader(self):
        """直接关一个reader前后取消可重试，同仓另一FD和位置保持可独立完成。

        参数: 无。返回: None。异常: 误关其他reader、假关闭或重复抵销费用时失败。
        """
        for after in (False, True):
            with self.subTest(after=after):
                owner = self.populated()
                baseline = owner.budget.ram_bytes
                first, second = owner.iter_records(), owner.iter_records()
                wrapped = ActualFile(first.handle)
                self.handles.append(wrapped)
                first.handle = wrapped
                marker = KeyboardInterrupt('reader close boundary')
                wrapped.close_error, wrapped.close_after = marker, after
                for _ in range(1 if after else 3):
                    with self.assertRaises(KeyboardInterrupt) as caught:
                        first.close()
                    self.assertIs(caught.exception, marker)
                    self.recovered(marker, owner)
                    self.assertFalse(second.closed or second.handle.closed)
                self.assertEqual(wrapped.actual.closed, after)
                wrapped.close_error = None
                first.close()
                first.close()
                self.assertFalse(first.verified_eof)
                self.assertEqual([record.decoded.sequence for record in second], [0, 1, 2])
                self.assertTrue(second.verified_eof and second.handle.closed)
                self.assertEqual(owner.budget.ram_bytes, baseline)

    def test_eof_reader_fee_cancel_before_after_never_fakes_verified_completion(self):
        """真实EOF关FD后读费抵销失败仍不给verified；释放前持续恢复与后取消不重复还费。

        参数: 无。返回: None。异常: 提前完成证明、注入没命中或借款/费用错误时失败。
        """
        for after in (False, True):
            with self.subTest(after=after):
                data = self.shared()
                owner = self.populated(budget=data.budget)
                reader = owner.iter_records()
                handle, fee = reader.handle, reader._fixed_cost
                self.assertGreater(fee, 0)
                self.assertEqual([next(reader).decoded.sequence for _ in range(3)], [0, 1, 2])
                release = data.budget.release_ram
                marker, calls = KeyboardInterrupt('EOF reader fee cancel'), []

                def release_reader(amount):
                    """只拦本reader实际费交易。参数: amount。返回: 原返回。异常: 同一marker。"""
                    if amount != fee:
                        return release(amount)
                    calls.append(amount)
                    if after:
                        release(amount)
                    raise marker

                with patch.object(data.budget, 'release_ram', side_effect=release_reader):
                    with self.assertRaises(KeyboardInterrupt) as caught:
                        next(reader)
                    self.assertIs(caught.exception, marker)
                    self.recovered(marker, owner)
                    self.assertTrue(handle.closed)
                    self.assertFalse(reader.verified_eof)
                    if after:
                        self.assertEqual(len(calls), 1)
                    else:
                        for _ in range(3):
                            with self.assertRaises(KeyboardInterrupt) as cleanup:
                                owner.close()
                            self.assertIs(cleanup.exception, marker)
                        self.assertGreaterEqual(len(calls), 3)
                owner.close()
                owner.close()
                self.assertTrue(reader.closed and owner.closed)
                self.assertFalse(reader.verified_eof)
                self.assert_shared(data)

    def test_unreturned_reader_reserve_and_registration_failures_keep_actual_parent(self):
        """未返回reader预算前后取消或登记前后错误，最高父保实际费用与真实FD。

        参数: 无。返回: None。异常: 原错误替换、pending丢失或借用仓误关时失败。
        """
        for after in (False, True):
            with self.subTest(stage='reserve', after=after):
                data = self.shared()
                owner = self.populated(budget=data.budget)
                original = data.budget.reserve_ram
                marker, calls = KeyboardInterrupt('reader reserve boundary'), []

                def fail_reserve(amount):
                    """在真实子费用前后取消。参数: amount。返回: 无。异常: 同一marker。"""
                    calls.append(amount)
                    if after:
                        original(amount)
                    raise marker

                with patch.object(data.budget, 'reserve_ram', side_effect=fail_reserve), \
                        patch.object(Path, 'open', wraps=Path.open) as opened:
                    with self.assertRaises(KeyboardInterrupt) as caught:
                        owner.iter_records()
                self.assertIs(caught.exception, marker)
                self.assertEqual(len(calls), 1)
                opened.assert_not_called()
                self.recovered(marker, owner).close()
                self.assertIsNone(owner._pending_reader)
                self.assert_shared(data)
            with self.subTest(stage='registration', after=after):
                data = self.shared()
                owner = self.populated(budget=data.budget)
                marker = MemoryError('reader registration primary')
                secondary = RuntimeError('unreturned actual reader close')
                registry = RegistrationFailure(marker, after)
                owner._readers = registry
                actual_open = Path.open
                handles = []

                def opened_reader(path, *args, **kwargs):
                    """仅包装实际新reader FD。参数: 原Path.open参数。返回: 原FD代理。异常: 原IO。"""
                    actual = actual_open(path, *args, **kwargs)
                    if path == owner.file_path and args and args[0] == 'rb':
                        wrapped = ActualFile(actual)
                        wrapped.close_error = secondary
                        handles.append(wrapped)
                        self.handles.append(wrapped)
                        return wrapped
                    return actual

                with patch.object(Path, 'open', new=opened_reader):
                    with self.assertRaises(MemoryError) as caught:
                        owner.iter_records()
                self.assertIs(caught.exception, marker)
                self.recovered(marker, owner)
                self.assertEqual(len(handles), 1)
                self.assertIs(owner._pending_reader, registry.reader)
                self.assertFalse(handles[0].actual.closed or owner.closed)
                for _ in range(3):
                    with self.assertRaises(RuntimeError) as cleanup:
                        owner.close()
                    self.assertIs(cleanup.exception, secondary)
                handles[0].close_error = None
                owner.close()
                self.assertTrue(handles[0].actual.closed and registry.reader.closed)
                self.assertIsNone(owner._pending_reader)
                self.assert_shared(data)

    def test_parent_release_before_persistent_and_after_cancel_preserve_borrowed_credit(self):
        """实际FD先关，费用前持续三次失败保槽；费用后KI不能再次归还借款或其他仓费用。

        参数: 无。返回: None。异常: 原取消/最高owner丢失、假closed或多抵账时失败。
        """
        for after in (False, True):
            with self.subTest(after=after):
                data = self.shared()
                owner = self.store(budget=data.budget)
                handle, release = owner._writer, data.budget.release_ram
                marker, calls = KeyboardInterrupt('parent fee release'), []

                def fail_release(amount):
                    """围绕实际固定费抵销取消。参数: amount。返回: 无。异常: 同一marker。"""
                    calls.append(amount)
                    if after:
                        release(amount)
                    raise marker

                with patch.object(data.budget, 'release_ram', side_effect=fail_release):
                    for _ in range(1 if after else 3):
                        with self.assertRaises(KeyboardInterrupt) as caught:
                            owner.close()
                        self.assertIs(caught.exception, marker)
                        self.recovered(marker, owner)
                        self.assertTrue(handle.closed)
                    if after:
                        owner.close()
                        self.assertEqual(len(calls), 1)
                    else:
                        self.assertGreaterEqual(len(calls), 3)
                        self.assertFalse(owner.closed)
                owner.close()
                owner.close()
                self.assertTrue(owner.closed)
                self.assert_shared(data)

    def test_checked_record_rebuild_uses_proof_or_one_complete_inner_tree_check(self):
        """真实回读中两个复杂包各完整检查一次，有限空值包用正证明，真实EOF仍保持。

        参数: 无。返回: None。异常: 原子树重复检查、值类型变化或EOF/预算不符令断言失败。
        仅计根为sequence/frame/values的检查，模型自身ITEM外壳及值诊断仍正常检查。
        """
        owner = self.populated('checked-tree-once')
        original = records_module._wire_tree
        counts = {'decoded_roots': 0}

        def observed(value, depth=0, remaining=MAX_WIRE_BYTES):
            """透明核同一原树。参数: 原值/深度/字节。返回: 原长度。异常: 原检查错误。"""
            if depth == 0 and type(value) is dict and set(value) == {'sequence', 'frame', 'values'}:
                counts['decoded_roots'] += 1
            return original(value, depth, remaining)

        reader = owner.iter_records()
        with patch.object(records_module, '_wire_tree', new=observed):
            rows = tuple(reader)
        self.assertEqual(counts['decoded_roots'], 2)
        self.assertEqual(tuple(row.decoded.sequence for row in rows), (0, 1, 2))
        for index, row in enumerate(rows):
            self.assertEqual(row.decoded.frame, original_frame(index))
            self.assert_values(row.decoded.values, original_decoded(index).values)
        self.assertTrue(reader.closed and reader.verified_eof)
        owner.close()
        self.assertEqual(owner.budget.ram_bytes, 4096)

    def test_inner_byte_and_depth_limits_still_precede_checked_conversion(self):
        """65536/65537字节及16/17层边界仍由首次严格解包检查，不用私有入口绕过。

        参数: 无。返回: None。异常: 越界先进入转换或合法JSON边界未到模型校验令断言失败。
        probe是额外模型字段，边界内仍须以形状错误拒绝；不是新增可接受记录格式。
        """
        base = decoded_to_dict(original_decoded(values={}))
        header = encode_packet(dict(store_version=1, time_ns=0, time_quantized=False))[:-1]
        empty = json.dumps(current_fixture({**base, 'probe': ''}), ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        padding = MAX_WIRE_BYTES - len(empty)
        exact = json.dumps(current_fixture({**base, 'probe': 'x' * padding}),
            ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        extra = json.dumps(current_fixture({**base, 'probe': 'x' * (padding + 1)}),
            ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        self.assertEqual((len(exact), len(extra)), (65536, 65537))
        cases = [(exact, True), (extra, False), (b'{"record":0,"record":1}', False),
            (b'{"record":NaN}', False), (b'{"\xff":0}', False)]
        for depth in (16, 17):
            nested = 0
            for _ in range(depth - 1):
                nested = [nested]
            cases.append((json.dumps(current_fixture({**base, 'probe': nested}),
                ensure_ascii=False, separators=(',', ':')).encode('utf-8'), depth == 16))
        convert = records_module._decoded_from_checked_dict
        for index, (inner, reaches_model) in enumerate(cases):
            with self.subTest(case=index):
                payload = header + module._DECODED_BOUNDARY + inner + b'}\n'
                with patch.object(records_module, '_decoded_from_checked_dict', wraps=convert) as checked:
                    with self.assertRaises(ResultFormatError) as caught:
                        module._decode_row(payload)
                self.assertEqual(checked.call_count, int(reaches_model))
                self.assertIsNotNone(caught.exception.__cause__)
                if reaches_model:
                    self.assertIn('decoded frame', str(caught.exception.__cause__))

    def test_checked_conversion_failure_and_cancel_clear_temporary_frame_and_keep_shared_budget(self):
        """新转换失败或取消时保原异常和用户帧，释放已重建临时frame及本仓费用。

        参数: 无。返回: None。异常: 包装取消、换掉cause、临时对象保活或误关借用仓令断言失败。
        首次JSON解包真实执行；仅在原值恢复处注入，保留异常TB以检验清理真实效果。
        """
        for error_type in (ValueError, KeyboardInterrupt):
            with self.subTest(error_type=error_type):
                data = self.shared()
                owner = self.populated('checked-failure-' + error_type.__name__, budget=data.budget)
                reader = owner.iter_records()
                marker = error_type('checked conversion injection')
                original = records_module.frame_from_dict
                references = []
                guard = {'user marker': object()}

                def observed_frame(value):
                    """借原函数重建并只存弱引用。参数: 原frame树。返回: 原frame。异常: 原错误。"""
                    frame = original(value)
                    references.append(weakref.ref(frame))
                    return frame

                def interrupted_value(value):
                    """在转换原值时注入同一异常。参数: 原标量。返回: 无。异常: marker。"""
                    user_guard = guard
                    raise marker

                retained = None
                with patch.object(records_module, 'frame_from_dict', new=observed_frame), \
                        patch.object(records_module, '_value_from_wire', new=interrupted_value):
                    try:
                        next(reader)
                    except BaseException as error:
                        # 明确保留TB；不能靠assertRaises自动清TB使弱引用假通过。
                        retained = error
                self.assertIsNotNone(retained)
                self.assertIs(retained if error_type is KeyboardInterrupt else retained.__cause__, marker)
                self.recovered(retained, owner).close()
                self.assert_shared(data)
                self.assertTrue(reader.closed and reader.handle.closed)
                self.assertFalse(reader.verified_eof)
                gc.collect()
                # 复杂值先尝试固定小包证明，释放第一份frame后才进入原完整转换。
                self.assertEqual(len(references), 2)
                self.assertTrue(all(reference() is None for reference in references))
                current = marker.__traceback__
                conversion_frames, user_frames = [], []
                while current is not None:
                    if current.tb_frame.f_code.co_name == '_decoded_from_checked_dict':
                        conversion_frames.append(current.tb_frame)
                    if current.tb_frame.f_code.co_name == 'interrupted_value':
                        user_frames.append(current.tb_frame)
                    current = current.tb_next
                self.assertEqual(len(conversion_frames), 1)
                self.assertEqual(conversion_frames[0].f_locals, {})
                self.assertEqual(len(user_frames), 1)
                self.assertIs(user_frames[0].f_locals['user_guard'], guard)

    def test_codec_failure_retains_original_traceback_input_and_user_frame_without_temporary(self):
        """真实records类型错误保异常/TB节点和用户guard，仅已结束codec临时对象可释放。

        参数: 无。返回: None。异常: 清用户帧/原输入、替换原错或临时副本保活时失败。
        注入只让本次新仓调用真实原encoder处理一个不支持对象；不修改records或旧链。
        """
        data = self.shared()
        owner = self.store(budget=data.budget)
        record = original_decoded()
        encode = module.encode_packet
        references, errors, original_nodes = [], [], []
        guard = {'original user marker': object()}

        def inject_codec_failure(packet):
            """调用真encoder制造TypeError并清测试自有临时引用。

            参数: packet是仓本次编码树。返回: 小header原编码；decoded阶段无正常返回。
            异常: 真实records TypeError原样抛出；本测试用户guard必须留在原TB帧中。
            """
            if 'sequence' not in packet:
                return encode(packet)
            user_guard = guard
            temporary = CodecTemporary()
            references.append(weakref.ref(temporary))
            try:
                return encode({'unsupported': temporary})
            except TypeError as error:
                errors.append(error)
                current = error.__traceback__
                while current is not None:
                    if current.tb_frame.f_globals.get('__name__') == 'chronaxis.legacy.records':
                        original_nodes.append(current)
                    current = current.tb_next
                raise
            finally:
                # 用户回调负责自身引用；产品不得clear这个用户帧或修改guard。
                packet = temporary = None

        retained = None
        with patch.object(module, 'encode_packet', new=inject_codec_failure):
            try:
                owner.append(record, 5, time_quantized=False)
            except TypeError as error:
                # 不用assertRaises清掉TB，真实风险条件一直保留到所有资源断言之后。
                retained = error
        self.assertEqual(len(errors), 1)
        self.assertIs(retained, errors[0])
        self.assertIsNotNone(retained.__traceback__)
        self.recovered(retained, owner).close()
        self.assert_shared(data)
        gc.collect()
        self.assertEqual(len(references), 1)
        self.assertIsNone(references[0]())
        current, surviving_nodes, user_frames = retained.__traceback__, [], []
        while current is not None:
            if current.tb_frame.f_globals.get('__name__') == 'chronaxis.legacy.records':
                surviving_nodes.append(current)
            if current.tb_frame.f_code.co_name == 'inject_codec_failure':
                user_frames.append(current.tb_frame)
            current = current.tb_next
        self.assertTrue(original_nodes)
        self.assertEqual([id(node) for node in surviving_nodes], [id(node) for node in original_nodes])
        self.assertEqual(len(user_frames), 1)
        self.assertIs(user_frames[0].f_locals['user_guard'], guard)
        self.assertEqual(tuple(guard), ('original user marker',))
        self.assertEqual(record.frame, original_frame())
        self.assert_values(record.values, original_decoded().values)


if __name__ == '__main__':
    # 模块导入不运行测试；根任务统一执行专项并保正式日志。
    unittest.main()
