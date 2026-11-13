"""[home] 核真实CAN输入字节指纹、按需混合读取与失败恢复，不执行性能测量。

复用独占work中的六帧BLF和手写DBC，实际spawn保持旧读取/解码路径。
测试独立重编码已交付记录，核时间字节与记录字节SHA、跨传输分批稳定性、真EOF
才开放以及无普通样本需求时才启用。取消和退款失败须保真实read owner；不伪造
扫描证明或把仅有输入字节摘要写成完整信号样本摘要。
"""

import hashlib
import importlib.util
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from chronaxis.core.binding import SignalDefinition
from chronaxis.core.models import TimebaseSpec
from chronaxis.core.types import SignalDType, TimeType
from chronaxis.execution import can_reader
from chronaxis.legacy import batch_read
from chronaxis.legacy.batch_wire import LENGTH
from chronaxis.legacy.records import LegacyCANField, decoded_to_dict, encode_packet
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import ResultClosedError
from chronaxis.sources.can_spec import LegacyCANSpec
from chronaxis.sources.models import ReadRequest
from chronaxis.sources.protocol import SourceReadError
import test_can_batch_history as fixture


class MessageObserver:
    """只在测试中保存有限交付记录的规范字节，用独立算法核输入摘要。"""

    def __init__(self):
        """建立小列表。参数: 无。返回: None。异常: 原分配错误。"""
        self.records = []

    def observe(self, record):
        """独立编码同次交付的原记录。参数: 实际record。返回: None。异常: 原编码错误。"""
        self.records.append(encode_packet(decoded_to_dict(record)))


class CANDefaultBatchSelectionTests(unittest.TestCase):
    """只构造来源，核默认协议选择不打开输入、不启动读取或改变all静态费用。"""

    def test_automatic_selection_and_explicit_rejection_do_not_read_inputs(self):
        """None随解码策略选协议，显式False拒绝requested，坏spec仍是TypeError。

        参数: 无。返回: None。异常: 输入IO、启动读取、协议选择、静态费用或退款错误时断言失败。
        """
        root = Path(__file__).resolve().parents[2] / 'work/optional-contribution-tests/auto-batch' / uuid4().hex
        budget = ResourceBudget()
        budget.reserve_ram(333)
        costs = {'all': [], 'requested': []}
        with patch.object(Path, 'open', side_effect=AssertionError('构造不能打开输入')), \
                patch.object(can_reader, 'LegacyCANProcessRead', side_effect=AssertionError('构造不能启动逐条读取')), \
                patch.object(batch_read, 'LegacyCANBatchRead', side_effect=AssertionError('构造不能启动批读取')):
            cases = (('requested', {}, True), ('requested', {'batch_read': None}, True),
                     ('all', {}, False), ('all', {'batch_read': None}, False),
                     ('all', {'batch_read': False}, False), ('all', {'batch_read': True}, True))
            for index, (scope, options, expected) in enumerate(cases):
                with self.subTest(scope=scope, options=options):
                    spec = LegacyCANSpec('bus', root / 'absent.blf', root / 'absent.dbc', 0,
                        TimebaseSpec('clock', TimeType.RELATIVE, 'synthetic'), decode_scope=scope)
                    owner = can_reader.BudgetedLegacyCANSourceAdapter(budget, spec, 'session', (),
                        work_dir=root / ('case-' + str(index)), message_frame_ids=(256,), **options)
                    try:
                        self.assertIs(owner.batch_read, expected)
                        self.assertEqual(owner._requests, set())
                        self.assertIsNone(owner._uninstalled_request)
                        costs[scope].append(owner._fixed_cost)
                    finally:
                        owner.close()
                    self.assertEqual(budget.ram_bytes, 333)
            # 各新目录名等长；省略、None及显式选择不应更改all原静态收费。
            self.assertEqual(len(set(costs['all'])), 1)
            self.assertEqual(len(set(costs['requested'])), 1)
            requested = LegacyCANSpec('bus', root / 'absent.blf', root / 'absent.dbc', 0,
                TimebaseSpec('clock', TimeType.RELATIVE, 'synthetic'))
            with self.assertRaisesRegex(ValueError, 'batch_read不能为False'):
                can_reader.BudgetedLegacyCANSourceAdapter(budget, requested, 'session', (),
                    work_dir=root / 'rejected', batch_read=False)
            self.assertEqual(budget.ram_bytes, 333)
            with self.assertRaises(TypeError):
                can_reader.BudgetedLegacyCANSourceAdapter(budget, object(), 'session', (),
                    work_dir=root / 'invalid-spec')
            self.assertEqual(budget.ram_bytes, 333)
        self.assertFalse((root / 'absent.blf').exists())
        self.assertFalse((root / 'absent.dbc').exists())
        self.assertFalse((root / 'rejected').exists())
        self.assertFalse((root / 'invalid-spec').exists())
        budget.release_ram(333)
        self.assertEqual(budget.ram_bytes, 0)


@unittest.skipUnless(all(importlib.util.find_spec(name) for name in ('can', 'cantools', 'natsort')),
                     '缺少可选CAN依赖')
class CANInputFingerprintTests(unittest.TestCase):
    """每例拥有真实文件与预算；指纹只借至read关闭，所有子资源都须真实归还。"""

    def setUp(self):
        """创建原六帧真实夹具。参数: 无。返回: None。异常: 原文件/依赖错误。"""
        fixture.NeededCANHistoryTests.setUp(self)

    def tearDown(self):
        """按真实owner逆序关闭并核账本归零。参数: 无。返回: None。异常: 原关闭或断言。"""
        fixture.NeededCANHistoryTests.tearDown(self)

    def adapter(self, *, scope='requested', raw=False, history=False, aliases=True):
        """创建可用于普通或直接消费的实际来源。

        参数: scope/raw/history控制读取行为；aliases决定是否存在所需Sample定义。
        返回: 新adapter。异常: 原声明、目录或预算错误；所有资源登记到本例清理表。
        """
        field = LegacyCANField(0, 'Sample', 256, False, False)
        definitions = (SignalDefinition('value', 'bus', field.key, SignalDType.FLOAT64,
            'V', 1000000000, input_unit='V'),) if aliases else ()
        spec = LegacyCANSpec('bus', self.blf, self.dbc, 0,
            TimebaseSpec('clock', TimeType.RELATIVE, 'synthetic'),
            offset_ns=-1700000000000000000, decode_scope=scope)
        source = can_reader.BudgetedLegacyCANSourceAdapter(self.budget, spec, 'session', definitions,
            backend='reference', work_dir=self.root / ('adapter-' + uuid4().hex),
            batch_read=True, retain_raw_frames=raw, capture_message_updates=history,
            message_frame_ids=(256,), message_consumer=lambda update: None)
        self.owners.append(source)
        return source

    def read(self, source, *, ordinary=False, consumer=True):
        """创建原请求及可选测试消费者，不在创建时读取文件。

        参数: source为实际adapter；ordinary选择普通Sample列；consumer开启直接观察。
        返回: (read,观察者或None)。异常: 原请求/预算错误；read登记到清理表。
        """
        observer = MessageObserver() if consumer else None
        source._update_consumer = (lambda update: None) if consumer else None
        request = ReadRequest('session', ('value',) if ordinary else (), 0, 5000000000, 2)
        read = source.iter_batches(request)
        original = read._deliver_message
        def observed(record, mapped):
            """观察原记录后照常交付。参数: 原记录/时间。返回: 原返回。异常: 原交付错误。"""
            if observer is not None:
                observer.observe(record)
            return original(record, mapped)
        read._deliver_message = observed
        self.owners.append(read)
        return read, observer

    def advance_to_eof(self, read):
        """接收空进度批直到唯一 EOF，期间输入指纹始终不可提前读取。

        参数: read 为真实纯消息读取器。返回: EOF 批；不代替最终耗尽和清理。
        异常: 原读取错误或协议/提前开放指纹断言失败。
        """
        while True:
            batch = next(read)
            self.assertEqual(batch.sample_count, 0)
            with self.assertRaises(ResultClosedError):
                _ = read.input_fingerprints
            if batch.source_eof:
                return batch

    def test_fingerprints_match_actual_bytes_and_ignore_transport_batch_boundaries(self):
        """两种真实传输分批获得相同输入指纹，原帧首末/缺值/同刻均保留。

        参数: 无。返回: None。异常: 实际字节、行数、EOF或分批稳定性断言失败。
        """
        results = []
        original_init = batch_read.LegacyCANBatchRead.__init__
        for transport_rows in (2, 5):
            with self.subTest(transport_rows=transport_rows):
                source = self.adapter()
                read, observer = self.read(source)

                def initialize(process, *args, **kwargs):
                    """仅改变本例传输条数。参数: 原构造参数。返回: None。异常: 原构造错误。"""
                    kwargs['batch_rows'] = transport_rows
                    original_init(process, *args, **kwargs)

                with self.assertRaises(ResultClosedError):
                    _ = read.input_fingerprints
                with patch.object(batch_read.LegacyCANBatchRead, '__init__', initialize):
                    self.advance_to_eof(read)
                    with self.assertRaises(ResultClosedError):
                        _ = read.input_fingerprints
                    with self.assertRaises(StopIteration):
                        next(read)
                actual = read.input_fingerprints
                expected_times = struct.pack('>6d', *(1700000000.0 + value for value in (0, 1, 1, 2, 3, 4)))
                expected_records = b''.join(LENGTH.pack(len(row)) + row for row in observer.records)
                self.assertEqual(actual, (hashlib.sha256(expected_times).hexdigest(),
                    hashlib.sha256(expected_records).hexdigest(), 6, 3))
                self.assertEqual((read.observation.row_count, read.observation.first_ns,
                                  read.observation.last_ns), (6, 0, 4000000000))
                self.assertTrue(read.finished)
                self.assertIsNone(read._process)
                results.append(actual)
                read.close()
                with self.assertRaises(ResultClosedError):
                    _ = read.input_fingerprints
                source.close()
        self.assertEqual(results[0], results[1])

    def test_empty_source_has_real_empty_byte_fingerprints(self):
        """真实空BLF只在完成后返回两个空流摘要，不虚构任何消息。

        参数: 无。返回: None。异常: 真EOF、计数或摘要断言失败。
        """
        import can
        with can.BLFWriter(self.blf):
            pass
        read, observer = self.read(self.adapter(aliases=False))
        list(read)
        empty = hashlib.sha256(b'').hexdigest()
        self.assertEqual(read.input_fingerprints, (empty, empty, 0, 0))
        self.assertEqual(observer.records, [])
        self.assertIsNone(read.observation.first_ns)

    def test_only_direct_empty_projection_pays_and_builds_hash_state(self):
        """普通信号/没有直接消费者不建hash，启用路径只增加8192固定费用。

        参数: 无。返回: None。异常: 多余SHA调用或费用差异断言失败。
        """
        source = self.adapter(scope='requested')
        factory = Mock(side_effect=hashlib.sha256)
        with patch.object(can_reader, 'hashlib', SimpleNamespace(sha256=factory)):
            inactive, _ = self.read(source, consumer=False)
            base_cost = inactive._fixed_cost
            self.assertFalse(inactive._input_fingerprints_enabled)
            self.assertEqual(factory.call_count, 0)
            inactive.close()
            active, _ = self.read(source)
            self.assertEqual(active._fixed_cost - base_cost, 8192)
            self.assertEqual(factory.call_count, 2)
            active.close()
            ordinary, _ = self.read(source, ordinary=True)
            self.assertFalse(ordinary._input_fingerprints_enabled)
            self.assertEqual(factory.call_count, 2)
            list(ordinary)
            with self.assertRaises(ResultClosedError):
                _ = ordinary.input_fingerprints
        self.assertEqual(factory.call_count, 2)

    def test_all_empty_direct_request_keeps_original_fee_without_fingerprints(self):
        """显式all即使有消费者和空请求也不创建或提交未使用的指纹。

        参数: 无。返回: None。异常: 额外费用、hash/回调工作或错误开放指纹时断言失败。
        真实读取到EOF后仍只提供原观测；不存在普通信号声明不改变all的证据策略。
        """
        source = self.adapter(scope='all', aliases=False)
        factory = Mock(side_effect=hashlib.sha256)
        with patch.object(can_reader, 'hashlib', SimpleNamespace(sha256=factory)), \
                patch.object(can_reader.CANObservationRead, '_observe_validated_packet',
                    side_effect=AssertionError('all不得执行输入指纹回调')) as callback:
            inactive, _ = self.read(source, consumer=False)
            base_cost = inactive._fixed_cost
            inactive.close()
            active, observer = self.read(source, consumer=True)
            self.assertFalse(active._input_fingerprints_enabled)
            self.assertEqual(active._fixed_cost, base_cost)
            self.assertIsNone(active._input_timestamp_sha)
            self.assertIsNone(active._input_records_sha)
            self.advance_to_eof(active)
            self.assertIsNone(active._process._validated_packet_consumer)
            with self.assertRaises(StopIteration):
                next(active)
            self.assertTrue(active.finished)
            self.assertEqual(active.observation.row_count, 6)
            self.assertEqual(len(observer.records), 3)
            self.assertEqual(factory.call_count, 0)
            callback.assert_not_called()
            with self.assertRaises(ResultClosedError):
                _ = active.input_fingerprints
            active.close()

    def test_requested_supports_sample_history_and_raw_frames_together(self):
        """同一requested来源可生成普通列、消息历史和全原帧副本，不扩大解码ID。

        参数: 无。返回: None。异常: 所需值、全观测或策略事实断言失败。
        """
        source = self.adapter(raw=True, history=True)
        read, _ = self.read(source, ordinary=True, consumer=False)
        batches = list(read)
        self.assertEqual(source.decode_frame_ids, (256,))
        self.assertEqual(read.runtime_metadata['version'], 3)
        self.assertEqual(read.runtime_metadata['decoded_values_policy'], 'requested_fields-v1')
        columns = [batch.series['value'] for batch in batches if 'value' in batch.series]
        self.assertEqual([int(seq) for column in columns for seq in column.sequence], [1, 2, 4])
        self.assertEqual([bool(value) for column in columns for value in column.valid], [True, True, False])
        self.assertEqual((read._raw_store.count, read._message_store.count), (6, 3))
        self.assertEqual([dict(row.decoded.values) for row in read._message_store.iter_records()],
                         [{'Sample': 3}, {'Sample': 5}, {}])
        self.assertFalse(read._input_fingerprints_enabled)

    def test_hash_update_cancel_and_refund_failure_keep_highest_real_owner(self):
        """第二段hash取消后不重投当前批，持续退款失败仍能用同read恢复。

        参数: 无。返回: None。异常: 主错被替换、错误完成或未归还费用时断言失败。
        """
        source = self.adapter()
        read, _ = self.read(source)
        original_release = self.budget.release_ram
        primary, secondary = KeyboardInterrupt('input digest update'), OSError('read refund blocked')
        count = []

        class FailingDigest:
            """只在接收到真实已验证包后抛一次指定取消，不伪造完成hash。"""

            def update(self, payload):
                """记录一次真实更新尝试。参数: 借入memoryview。返回: 无。异常: 同primary。"""
                try:
                    count.append(len(payload))
                    raise primary
                finally:
                    payload = None

        def release(amount):
            """仅阻止本read固定费用退款。参数: 金额。返回: 原返回。异常: 同secondary。"""
            if amount == read._fixed_cost:
                raise secondary
            return original_release(amount)

        read._input_records_sha = FailingDigest()
        with patch.object(self.budget, 'release_ram', release):
            with self.assertRaises(KeyboardInterrupt) as caught:
                next(read)
            self.assertIs(caught.exception, primary)
            self.assertIs(primary.can_observation_read_cleanup_owner, read)
            self.assertEqual(len(count), 1)
            self.assertTrue(read.failed)
            self.assertFalse(read.finished or read.closed)
            self.assertIsNone(read._process)
            self.assertIsNone(read._input_timestamp_sha)
            self.assertIsNone(read._input_records_sha)
            with self.assertRaises(ResultClosedError):
                _ = read.input_fingerprints
            with self.assertRaises(OSError):
                read.close()
        read.close()
        self.assertTrue(read.closed)

    def test_finish_rejects_mismatched_hashed_frame_count(self):
        """真实EOF仍须核摘要计数与原观测一致，不能发布部分输入指纹。

        参数: 无。返回: None。异常: 计数错配被误当成功或关闭责任残留时断言失败。
        """
        read, _ = self.read(self.adapter())
        self.advance_to_eof(read)
        read._input_frame_count -= 1
        with self.assertRaises(SourceReadError):
            next(read)
        self.assertTrue(read.failed and read.closed)
        self.assertFalse(read.finished)
        with self.assertRaises(ResultClosedError):
            _ = read.input_fingerprints


if __name__ == '__main__':
    unittest.main()
