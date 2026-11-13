"""[home] 直接验证ID优先的按需读取、无时间包与精确完整检查回退。

内存替身明确标成worker识别的精确原生类，通过禁止属性访问证明无关字段没有被碰。
实际worker、严格JSON和新包编解码都使用产品实现；替身不证明真实BLF性能。
另用既有现场BLF夹具执行真实spawn、EOF、预取与资源清理；产物只写work专用目录。
"""

from pathlib import Path
from types import SimpleNamespace
import math
import unittest
from unittest.mock import patch

from chronaxis.legacy import batch_worker, worker
from chronaxis.legacy.batch_wire import (DEMAND_MAGIC, DEMAND_HEADER, MAX_BATCH_BYTES,
    MAX_BATCH_ROWS, decode_batch, encode_batch, record_payload_offset)
from chronaxis.legacy.records import (LegacyCANField, LegacyCANRequest, decode_packet,
                                     encode_packet, field_to_dict)
from chronaxis.legacy.required_records import (RequiredCANFrame, RequiredDecodedFrame,
                                             required_to_dict, required_from_packet)
from test_legacy_can_batch_worker_limits import ControlledOriginalChain, ScriptedBytesConnection, pull
from test_legacy_batch_validation import message
from test_legacy_can_process import ProcessFixture, HAS_CAN, SYNTHETIC_DBC, BASE_TIMESTAMP
from chronaxis.legacy.batch_read import LegacyCANBatchRead
from chronaxis.legacy.batch_wire import MIN_BATCH_BYTES
from chronaxis.sources.protocol import SourceReadError


class GuardedMessage:
    """可声明禁止访问的报文替身，属性错误意味着优化实际仍做了无关工作。"""

    def __init__(self, sequence, *, scope, unrelated):
        """准备固定身份。参数: sequence/scope/unrelated。返回: None。异常: 原构造错误。"""
        self.__dict__.update(vars(message(timestamp=float(sequence), arbitration_id=257 if unrelated else 256)))
        self.synthetic_sequence = sequence
        # 不在初始化后改写禁止表，测试可观察到的访问均由生产worker执行。
        prohibited = {'dlc', 'data', 'is_rx', 'bitrate_switch', 'error_state_indicator'}
        if scope == 'source' and not unrelated:
            prohibited.clear()  # source目标仍提供完整原帧给既有时序/导出消费者。
        if scope == 'none' or unrelated and scope == 'selected':
            prohibited.add('timestamp')
        if unrelated:
            prohibited.update(('channel', 'is_extended_id', 'is_fd', 'is_remote_frame', 'is_error_frame'))
        self.prohibited = prohibited

    def __getattribute__(self, name):
        """拒绝不需要的字段访问。参数: name。返回: 原属性。异常: AssertionError为越界处理。"""
        if name not in ('__dict__', 'prohibited') and name in object.__getattribute__(self, 'prohibited'):
            raise AssertionError('不应读取的报文属性: ' + name)
        return object.__getattribute__(self, name)


class DemandChain(ControlledOriginalChain):
    """四帧交替目标ID的有限链，可独立选择原生识别和目标故障。"""

    def __init__(self, scope, *, native=True, fault=None, values=None):
        """保存消息策略。参数: scope/native/fault/values。返回: None。异常: 无。"""
        super().__init__(4, {'x': 7.0} if values is None else values)
        self.scope, self.native, self.fault = scope, native, fault
        self.can = SimpleNamespace(Message=GuardedMessage) if native else SimpleNamespace()

    def __next__(self):
        """按原序生成输入。参数: 无。返回: 消息。异常: 真EOF或目标字段故障由worker发现。"""
        sequence = self.next_calls
        self.next_calls += 1
        if sequence >= self.count:
            raise StopIteration
        if self.native:
            msg = GuardedMessage(sequence, scope=self.scope, unrelated=sequence % 2 == 0)
        else:
            msg = message(timestamp=float(sequence), arbitration_id=257 if sequence % 2 == 0 else 256)
            msg.synthetic_sequence = sequence
        if self.fault == 'target_time' and sequence == 1:
            msg.timestamp = float('nan')
        if self.fault == 'unrelated_dlc' and sequence == 0:
            msg.dlc = 65
        if self.fault in ('unrelated_channel_bytes', 'unrelated_channel_surrogate') and sequence == 0:
            msg.channel = '汉'*30000 if self.fault.endswith('bytes') else '\ud800'
        return msg


class DemandWorkerTests(unittest.TestCase):
    """从真实worker入口验证原序、按需属性和新版本声明，全部资源在同次调用关闭。"""

    def execute(self, scope='none', *, native=True, fault=None, values=None, error=False, rows=4096):
        """运行实际worker。参数: 策略与故障；rows为单批许可。返回: 链/连接。异常: 断言或非预期退出。"""
        chain = DemandChain(scope, native=native, fault=fault, values=values)
        commands = [(dict(pull(0, ids=[256]), rows=rows), 0, 0)]
        if rows == 2:
            commands.extend(((dict(pull(2, ids=[256]), rows=2), 2, 1),
                             (dict(pull(4, ids=[256]), rows=2), 4, 2)))
        connection = ScriptedBytesConnection(chain, commands)
        field = LegacyCANField(0, 'x', 256, False, False)
        chain.db.messages = (SimpleNamespace(frame_id=256, length=8,
            is_extended_frame=False, is_fd=False, signals=(SimpleNamespace(name='x'),)),)
        request = LegacyCANRequest(Path('synthetic.blf'), Path('synthetic.dbc'), (field,))
        processor = SimpleNamespace(parse_frame=chain.parse_frame,
            cantools=SimpleNamespace(database=SimpleNamespace()))
        with patch.object(worker, '_request', return_value=request), \
                patch.object(batch_worker, 'load_dbc_file', side_effect=lambda path,module: chain.load_file(path)), \
                patch.object(worker, '_load_can_runtime', return_value=(getattr(chain,'can',None),processor.cantools)), \
                patch.object(worker, '_iter_blf', side_effect=chain.iter_frames), \
                patch.object(batch_worker, '_parse_selected', side_effect=lambda db,frame,message,duplicates: processor.parse_frame(frame,db)), \
                patch.object(worker, '_field_metadata', return_value=[{'locator': field_to_dict(field), 'unit': None}]), \
                patch.object(batch_worker.metadata, 'version', return_value='controlled'):
            if error:
                with self.assertRaises(SystemExit):
                    batch_worker.batch_worker_main(connection, decode_frame_ids=(256,),
                        input_check='auto', time_scope=scope)
            else:
                batch_worker.batch_worker_main(connection, decode_frame_ids=(256,),
                    input_check='auto', time_scope=scope)
        self.assertTrue(connection.closed)
        self.assertEqual(chain.close_calls, 1)
        return chain, connection

    def unpack(self, connection, scope):
        """按独立原帧计数推进解包。参数: connection/scope。返回: 批次列表。异常: 包不符。"""
        result, start = [], 0
        for payload, _, _ in connection.sent:
            if payload.startswith(DEMAND_MAGIC):
                batch, eof = decode_batch(payload, expected_start=start, row_limit=MAX_BATCH_ROWS,
                    byte_limit=MAX_BATCH_BYTES, frame_ids=(256,), input_check='auto', time_scope=scope)
                start += batch.frame_count
                result.append((batch, eof))
        return result

    def test_none_skips_every_unrelated_property_and_target_time(self):
        """无时间任务仅读无关ID，目标也不碰时间/载荷。参数: 无。返回: None。异常: 越界访问或断言。"""
        chain, connection = self.execute()
        batch, eof = self.unpack(connection, 'none')[0]
        self.assertEqual((chain.next_calls, chain.parse_calls), (5, 2))
        self.assertEqual((batch.frame_count, batch.timestamps, batch.full_check_count), (4, (), 0))
        self.assertEqual([r.sequence for r in batch.records], [1, 3])
        self.assertTrue(all(r.frame.timestamp is None for r in batch.records))
        self.assertTrue(eof)
        ready = decode_packet(connection.sent[0][0])
        self.assertEqual((ready['version'], ready['input_check'], ready['time_scope']), (4, 'auto', 'none'))
        self.assertEqual(record_payload_offset(batch), DEMAND_HEADER.size)

    def test_selected_reads_target_times_only_and_preserves_raw_gap(self):
        """目标时间仅两项，原跨度仍四条。参数: 无。返回: None。异常: 无关属性访问或断言。"""
        _, connection = self.execute('selected')
        batch, eof = self.unpack(connection, 'selected')[0]
        self.assertEqual((batch.frame_count, batch.timestamps), (4, (1.0, 3.0)))
        self.assertTrue(eof)
        self.assertEqual([r.sequence for r in batch.records], [1, 3])

    def test_source_auto_checks_only_unrelated_time(self):
        """source自动范围允许看无关时间，目标完整原帧仍需载荷；使用非原生明确回退核计数。

        参数: 无。返回: None。异常: 原序/时间/回退数断言失败。
        """
        for native in (False, True):
            with self.subTest(native=native):
                _, connection = self.execute('source', native=native)
                batch, eof = self.unpack(connection, 'source')[0]
                self.assertEqual((batch.frame_count, batch.timestamps, batch.full_check_count),
                                 (4, (0.0, 1.0, 2.0, 3.0), 0 if native else 4))
                self.assertTrue(eof)
                self.assertEqual(record_payload_offset(batch), DEMAND_HEADER.size+32)

    def test_non_native_falls_back_and_rejects_unrelated_bad_frame(self):
        """非原生即使无关也保完整旧检查。参数: 无。返回: None。异常: 未拒绝坏DLC时断言失败。"""
        chain, connection = self.execute(native=False, fault='unrelated_dlc', error=True)
        self.assertEqual((chain.next_calls, chain.parse_calls), (1, 0))
        self.assertEqual(decode_packet(connection.sent[-1][0])['op'], 'error')

    def test_target_bad_values_and_selected_time_still_fail(self):
        """目标值类型和需要的时间仍严格检查。参数: 无。返回: None。异常: 未拒绝错误。"""
        self.execute(values={'x': 'bad'}, error=True)
        self.execute('selected', fault='target_time', error=True)

    def test_non_native_unrelated_channel_keeps_utf8_and_original_item_limit(self):
        """非原生无关帧不绕过旧UTF-8或64KiB检查，不增加解码调用。

        参数: 无。返回: None。异常: 未拒绝坏通道或处理多余消息时断言失败。
        """
        for fault in ('unrelated_channel_bytes', 'unrelated_channel_surrogate'):
            for scope in ('none', 'selected', 'source'):
                with self.subTest(fault=fault, scope=scope):
                    chain, connection = self.execute(scope, native=False, fault=fault, error=True)
                    self.assertEqual((chain.next_calls, chain.parse_calls), (1, 0))
                    packet = decode_packet(connection.sent[-1][0])
                    self.assertEqual(packet['op'], 'error')
                    self.assertFalse(any(p[0].startswith(DEMAND_MAGIC) for p in connection.sent))

    def test_non_native_target_values_are_bounded_by_original_full_frame_shell(self):
        """按需较小外壳能容纳的记录，非原生回退仍按旧完整外壳拒绝。

        参数: 无。返回: None。异常: 原旧限额未保留或多解码时断言失败。
        """
        from chronaxis.legacy.batch_validation import _item_base_size
        from chronaxis.legacy.records import MAX_WIRE_BYTES
        target = message(timestamp=1.0, arbitration_id=256, channel=0)
        # 单条值字典只有x键，数值字节长度选在“旧ITEM超一字节，新Required仍合法”处。
        base = _item_base_size(worker._frame(target), 1)
        available = MAX_WIRE_BYTES-base+2
        name = 'x'*(available-5)
        frame = RequiredCANFrame(None, 256, 0, False, False, False, False)
        RequiredDecodedFrame(1, frame, {name: 0})
        # INIT只请求x字段，使用临时投影保持超长键可实际进入所需值，不更改原解码器。
        with patch.object(batch_worker, '_project_values', return_value={name: 0}):
            chain, connection = self.execute(native=False, error=True)
        self.assertEqual((chain.next_calls, chain.parse_calls), (2, 1))
        self.assertEqual(decode_packet(connection.sent[-1][0])['op'], 'error')

    def test_missing_target_field_stays_missing(self):
        """解码缺键不补零。参数: 无。返回: None。异常: 断言。"""
        _, connection = self.execute(values={})
        self.assertEqual([dict(r.values) for r in self.unpack(connection, 'none')[0][0].records], [{}, {}])

    def test_raw_counter_continues_across_target_sparse_batches_and_true_eof(self):
        """两条一批按原序连续，EOF需额外真实探测。参数: 无。返回: None。异常: 许可或计数断言。"""
        chain, connection = self.execute(rows=2)
        batches = self.unpack(connection, 'none')
        self.assertEqual([b.frame_count for b, _ in batches], [2, 2, 0])
        self.assertEqual([eof for _, eof in batches], [False, False, True])
        self.assertEqual([r.sequence for b, _ in batches for r in b.records], [1, 3])
        self.assertEqual((chain.next_calls, chain.parse_calls), (5, 2))


class DemandWireTests(unittest.TestCase):
    """验证新包类型、时间声明与记录边界，不借真实旧库作为预期值。"""

    def packet(self, *, sequence=2, timestamp=None, scope='none', values=None):
        """生成一条目标的五原帧包。参数: 序号/时间/scope/values。返回: bytes。异常: 产品边界错误。"""
        frame = RequiredCANFrame(timestamp, 256, 0, False, False, False, False)
        record = RequiredDecodedFrame(sequence, frame, {'x': -0.0} if values is None else values)
        return encode_batch(0, [] if scope == 'none' else [timestamp],
            [encode_packet(required_to_dict(record))], True, MAX_BATCH_BYTES,
            raw_count=5, time_scope=scope, input_check='auto')

    def decode(self, payload, scope='none'):
        """严格解包本测试许可。参数: payload/scope。返回: (batch,eof)。异常: 坏包拒绝。"""
        return decode_batch(payload, expected_start=0, row_limit=5, byte_limit=MAX_BATCH_BYTES,
                            frame_ids=(256,), input_check='auto', time_scope=scope)

    def test_scope_magic_and_time_mismatch_rejected(self):
        """错误scope、旧magic及none中假时间均拒绝。参数: 无。返回: None。异常: 断言。"""
        payload = self.packet()
        with self.assertRaises(ValueError):
            self.decode(payload, 'selected')
        with self.assertRaises(ValueError):
            self.decode(b'CXB1'+payload[4:])
        with self.assertRaises(ValueError):
            self.decode(self.packet(timestamp=0.0))
        with self.assertRaises(ValueError):
            decode_batch(payload, expected_start=0, row_limit=5, byte_limit=MAX_BATCH_BYTES,
                         frame_ids=(256,), input_check='full', time_scope='none')

    def test_raw_count_sequence_fallback_count_and_trailing_bytes_rejected(self):
        """稀疏记录仍受原序跨度与回退计数约束。参数: 无。返回: None。异常: 断言。"""
        payload = self.packet()
        parts = list(DEMAND_HEADER.unpack_from(payload))
        for index, value in ((2, 2), (4, 6), (6, 6)):
            bad = parts.copy()
            bad[index] = value
            with self.assertRaises(ValueError):
                self.decode(DEMAND_HEADER.pack(*bad)+payload[DEMAND_HEADER.size:])
        with self.assertRaises(ValueError):
            self.decode(payload+b'x')

    def test_nonfinite_labels_and_negative_zero_preserved(self):
        """所需值的诊断浮点和负零仍无损。参数: 无。返回: None。异常: 断言或编码错误。"""
        batch, _ = self.decode(self.packet(values={'x': -0.0, 'nan': float('nan')}))
        self.assertEqual(batch.records[0].values['x'].hex(), '-0x0.0p+0')
        self.assertTrue(math.isnan(batch.records[0].values['nan']))

    def test_required_duplicate_keys_types_and_limits_rejected(self):
        """独立记录入口不跳过重复键/未知字段/布尔序号/64KiB。参数: 无。返回: None。异常: 断言。"""
        for payload in (b'{"sequence":0,"sequence":1}', b'{"x":0}', b' '+b'x'*65536):
            with self.assertRaises((TypeError, ValueError)):
                required_from_packet(payload)
        frame = RequiredCANFrame(None, 256, 0, False, False, False, False)
        with self.assertRaises(TypeError):
            RequiredDecodedFrame(True, frame, {})
        with self.assertRaises(ValueError):
            RequiredDecodedFrame(0, frame, {'x'*65536: 1})


@unittest.skipUnless(HAS_CAN, '真实CAN可选依赖未全部安装')
class DemandRealReadTests(ProcessFixture):
    """现场生成真实输入，验证新包在spawn、预取、预算及关闭中的实际接线。"""

    def setUp(self):
        """创建六帧交替ID。参数: 无。返回: None。异常: 原写文件或旧writer错误。"""
        super().setUp()
        import can
        self.dbc_path.write_text(SYNTHETIC_DBC, encoding='utf-8')
        with can.BLFWriter(str(self.input_path)) as writer:
            for index in range(6):
                writer.on_message_received(can.Message(timestamp=BASE_TIMESTAMP+index*.125,
                    arbitration_id=256 if index % 2 else 257, is_extended_id=False, channel=0,
                    data=bytes([index])))

    def make_demand_read(self, *, scope='none', prefetch=False, ids=(256,), headroom=0):
        """构造并登记来源责任。参数: scope/prefetch/ids/headroom。返回: read。异常: 原配置或预算错误。"""
        request = LegacyCANRequest(self.input_path, self.dbc_path, () if not ids else (self.field,))
        read = LegacyCANBatchRead(request, self.budget, frame_ids=ids, batch_rows=2,
            prefetch=prefetch, decode_scope='requested', decode_frame_ids=ids,
            input_check='auto', time_scope=scope, consumer_headroom_bytes=headroom)
        self.reads.append(read)
        return read

    def test_real_scopes_prefetch_and_exact_eof_keep_values_and_raw_count(self):
        """三种时间范围和同步/预取均保原序和值。参数: 无。返回: None。异常: 来源、计数或退款断言。"""
        for scope in ('none', 'selected', 'source'):
            for prefetch in (False, True):
                with self.subTest(scope=scope, prefetch=prefetch):
                    read = self.make_demand_read(scope=scope, prefetch=prefetch)
                    batches = list(read)
                    self.assertEqual(sum(b.frame_count for b in batches), 6)
                    self.assertEqual([r.sequence for b in batches for r in b.records], [1, 3, 5])
                    self.assertEqual([r.values['Sample'] for b in batches for r in b.records], [1, 5, 9])
                    self.assertEqual(sum(len(b.timestamps) for b in batches),
                                     {'none': 0, 'selected': 3, 'source': 6}[scope])
                    self.assertEqual(read.counters['items_returned'], 6)
                    self.assertEqual(read.full_check_count, 0)
                    self.assertTrue(read.finished and read.closed)
                    self.assertEqual(self.budget.ram_bytes, self.borrowed)

    def test_no_targets_still_progresses_and_confirms_true_eof(self):
        """完全无目标仍按原条数推进，不能把空目标当空来源。参数: 无。返回: None。异常: 原序或完成断言。"""
        read = self.make_demand_read(ids=(), prefetch=True)
        batches = list(read)
        self.assertEqual([b.frame_count for b in batches], [2, 2, 2, 0])
        self.assertTrue(all(not b.records and not b.timestamps for b in batches))
        self.assertTrue(read.finished)
        self.assertEqual(read.counters['items_returned'], 6)

    def test_cancel_closes_both_paid_slots_without_faking_completion(self):
        """交付首批后提前关，预取费用全部归还且不宣称EOF。参数: 无。返回: None。异常: 原关闭或余额断言。"""
        read = self.make_demand_read(prefetch=True)
        first = next(read)
        self.assertEqual(first.frame_count, 2)
        self.assertGreater(read._prefetch_cost, 0)
        read.close()
        self.assertFalse(read.finished)
        self.assertEqual(self.budget.ram_bytes, self.borrowed)

    def test_one_batch_budget_falls_back_to_sync(self):
        """只够一批时不预取，独立借款不会被清理归还。参数: 无。返回: None。异常: 预算或读失败。"""
        read = self.make_demand_read(prefetch=True).start()
        loan = self.budget.memory_budget_bytes-self.budget.ram_bytes-128*MIN_BATCH_BYTES
        self.budget.reserve_ram(loan)
        try:
            first = next(read)
            self.assertEqual(first.frame_count, 2)
            self.assertIsNone(read._prefetch_packet)
            read.close()
            self.assertEqual(self.budget.ram_bytes, self.borrowed+loan)
        finally:
            read.close()
            self.budget.release_ram(loan)

    def test_scope_conflicts_and_ready_strategy_mismatch_rejected(self):
        """非法组合在启动前拒绝，v4不能被v3或另一时间范围冒充。参数: 无。返回: None。异常: 断言。"""
        request = LegacyCANRequest(self.input_path, self.dbc_path, (self.field,))
        for kwargs in ({'input_check': 'auto'}, {'time_scope': 'none'},
                       {'input_check': 'auto', 'time_scope': 'bad'}):
            with self.assertRaises(SourceReadError):
                LegacyCANBatchRead(request, self.budget, **kwargs)
            self.assertEqual(self.budget.ram_bytes, self.borrowed)
        read = self.make_demand_read().start()
        metadata = dict(read.metadata)
        for key, value in (('version', 3), ('time_scope', 'source'), ('input_check', 'full')):
            bad = dict(metadata, **{key: value})
            with self.assertRaises(SourceReadError):
                read._check_ready(bad)
        read.close()
