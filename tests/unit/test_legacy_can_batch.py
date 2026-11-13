"""验证新批次CAN协议的条数/字节边界、完整原记录、真实EOF及资源恢复。

纯字节用例主动造坏头、截断、乱序和非法JSON，真实spawn用例现场生成BLF/DBC，
只写新work目录；独立受控worker注入EOF退出、发送/关闭取消，不冒称旧行为基准。
保留原逐条接口的全部测试，新增批次必须核完整原时间、同刻数据、稀疏序号和借款。
"""

from chronaxis.can_dependencies import runtime_dependency_versions
from functools import partial
import os
import platform
import struct
import unittest
from unittest.mock import patch

from chronaxis.legacy.batch_read import LegacyCANBatchRead
from chronaxis.legacy.batch_wire import (HEADER, LENGTH, MAX_BATCH_BYTES, MIN_BATCH_BYTES,
    MAX_BATCH_ROWS, BATCH_MAGIC, decode_batch, encode_batch)
from chronaxis.legacy.records import (LegacyCANRequest, LegacyDecodedFrame, LegacyRawFrame,
    MAX_WIRE_BYTES, PROFILE_ID, decode_packet, decoded_to_dict, encode_packet)
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import BudgetExceededError
from chronaxis.sources.protocol import SourceReadError
from test_legacy_can_process import (ProcessFixture, ConnectionFault, ProcessFault,
    SYNTHETIC_DBC, BASE_TIMESTAMP, HAS_CAN, observed_real_worker)


class BatchConnectionFault(ConnectionFault):
    """在既有实际连接故障代理上增加send入口，不伪造操作成功或关闭状态。"""

    def send_bytes(self, *args, **kwargs):
        """在真实发送前后注入原错误。参数: 原参数。返回: 原返回。异常: 设定对象/原IO错误。"""
        return self._invoke('send_bytes', *args, **kwargs)


def observed_batch_worker(connection):
    """复用真实vendor调用追踪，只在测试子进程替换控制循环为新批次实现。

    参数: connection为真实Pipe。返回: 正常返回None。异常: 原生产worker或追踪错误。
    """
    from chronaxis.legacy import worker
    from chronaxis.legacy.batch_worker import batch_worker_main
    with patch.object(worker, 'worker_main', batch_worker_main):
        observed_real_worker(connection)


def sample(index=0, frame_id=256):
    """生成明确的协议测试原记录。参数: 序号/ID。返回: 冻结记录。异常: 原模型错误。"""
    frame = LegacyRawFrame(float(index), frame_id, False, False, False, 0, 1,
        b'\x01', False, True, False, False)
    return LegacyDecodedFrame(index, frame, {'value': 0, 'false': False, 'negative': -1.25})


def payload(rows, *, count=None, eof=False):
    """编码给定原序记录。参数: rows/count/eof。返回: bytes。异常: 原编码错误。"""
    start = rows[0].sequence if rows else 0
    count = len(rows) if count is None else count
    return encode_batch(start, [float(start+i) for i in range(count)],
        [encode_packet(decoded_to_dict(row)) for row in rows], eof, MAX_BATCH_BYTES)


def controlled_batch_worker(connection, *, mode='data'):
    """用真实独立子进程返回受控批次，测试协议及退出而非原CAN数值。

    参数: connection为真实Pipe；mode为明确故障。返回: None。异常: 指定失败时SystemExit。
    """
    initial = decode_packet(connection.recv_bytes(MAX_WIRE_BYTES))
    ready = {'op': 'ready', 'version': 1, 'profile': PROFILE_ID,
        'worker_pid': os.getpid(), 'fields': [{'locator': x, 'unit': 'V'} for x in initial['fields']],
        'dependency_versions': runtime_dependency_versions()}
    connection.send_bytes(encode_packet(ready))
    try:
        packet = decode_packet(connection.recv_bytes(MAX_WIRE_BYTES))
        if packet['op'] != 'pull_batch':
            raise AssertionError('测试需要一个明确批次许可')
        if mode == 'disconnect':
            return
        if mode == 'bad_start':
            data = payload((sample(1),), eof=True)
        elif mode == 'truncated':
            data = b'CXB1'
        elif mode == 'overlong':
            data = b'X'*(packet['bytes']+1)
        elif mode == 'empty_non_eof':
            data = HEADER.pack(BATCH_MAGIC, 0, 0, 0, 0)
        else:
            data = payload((sample(),), eof=True)
        connection.send_bytes(data)
        if mode == 'bad_exit':
            raise SystemExit(7)
    finally:
        connection.close()


class LegacyBatchWireTests(unittest.TestCase):
    """以独立坏字节和全量/稀疏模型检查接收边界，不只做正常编码器往返。"""

    def unpack(self, data, *, selected=None, start=0, rows=MAX_BATCH_ROWS):
        """调用被测解包器。参数: bytes及许可。返回: 批次/EOF。异常: 原解包错误。"""
        return decode_batch(data, expected_start=start, row_limit=rows,
            byte_limit=MAX_BATCH_BYTES, frame_ids=selected)

    def test_all_and_sparse_preserve_raw_sequence_and_values(self):
        """全量和稀疏保持同一原字段。参数: 无。返回: None。异常: 断言失败。"""
        records = tuple(sample(i) for i in range(4))
        batch, eof = self.unpack(payload(records, eof=True))
        self.assertTrue(eof)
        self.assertEqual(batch.records, records)
        sparse = encode_batch(0, [float(i) for i in range(4)],
            [encode_packet(decoded_to_dict(records[i])) for i in (1, 3)], True, MAX_BATCH_BYTES)
        batch, _ = self.unpack(sparse, selected=(256,))
        self.assertEqual([r.sequence for r in batch.records], [1, 3])
        self.assertEqual(batch.timestamps, (0.0, 1.0, 2.0, 3.0))
        with self.assertRaises(ValueError):
            self.unpack(sparse)

    def test_empty_projection_and_empty_file_are_distinct(self):
        """不保留记录仍要全时间，空文件只准EOF。参数: 无。返回: None。异常: 断言失败。"""
        data = encode_batch(0, [0.0, 1.0], [], False, MAX_BATCH_BYTES)
        batch, eof = self.unpack(data, selected=())
        self.assertEqual(batch.timestamps, (0.0, 1.0))
        self.assertFalse(eof)
        self.assertEqual(batch.records, ())
        empty, eof = self.unpack(encode_batch(0, [], [], True, MAX_BATCH_BYTES))
        self.assertEqual(empty.timestamps, ())
        self.assertTrue(eof)
        with self.assertRaises(ValueError):
            encode_batch(0, [], [], False, MAX_BATCH_BYTES)

    def test_hostile_headers_lengths_json_and_sequences_fail(self):
        """逐种坏包明确拒绝，不能部分接受。参数: 无。返回: None。异常: 断言失败。"""
        good = payload((sample(),), eof=True)
        head = HEADER.size
        candidates = [good[:head-1], b'CXB2'+good[4:], good+b'x',
            HEADER.pack(BATCH_MAGIC, 0, 4097, 1, 0),
            HEADER.pack(BATCH_MAGIC, 0, 1, 2, 1)+good[head:],
            HEADER.pack(BATCH_MAGIC, 0, 1, 1, 2)+good[head:],
            HEADER.pack(BATCH_MAGIC, 0, 0, 0, 0),
            good[:head+8]+LENGTH.pack(MAX_WIRE_BYTES+1)+good[head+12:],
            good[:-1], payload((sample(1),), eof=True),
            HEADER.pack(BATCH_MAGIC, 0, 1, 1, 0)+struct.pack('>d', float('nan'))]
        for data in candidates:
            with self.subTest(size=len(data), prefix=data[:20]):
                with self.assertRaises((ValueError, TypeError)):
                    self.unpack(data)
        for raw in (b'{"sequence":0,"sequence":0}', b'{"values":NaN}',
                    b'{"frame":{"unknown":[]}}', b'{"x":'+b'['*40+b'0'+b']'*40+b'}'):
            data = HEADER.pack(BATCH_MAGIC, 0, 1, 1, 1)+struct.pack('>d',0.0)+LENGTH.pack(len(raw))+raw
            with self.assertRaises((ValueError, TypeError)):
                self.unpack(data)
        duplicate = encode_batch(0, [0.0, 1.0],
            [encode_packet(decoded_to_dict(sample()))]*2, True, MAX_BATCH_BYTES)
        with self.assertRaises(ValueError):
            self.unpack(duplicate)
        mismatch = good[:head]+struct.pack('>d', -0.0)+good[head+8:]
        with self.assertRaises(ValueError):
            self.unpack(mismatch)

    def test_row_limit_and_byte_limit_are_both_enforced(self):
        """最大原时间数组受行数限制，单记录受字节限制。参数: 无。返回: None。异常: 断言失败。"""
        data = encode_batch(0, [0.0]*4096, [], False, MAX_BATCH_BYTES)
        self.assertEqual(len(self.unpack(data, selected=())[0].timestamps), 4096)
        with self.assertRaises(ValueError):
            self.unpack(data, selected=(), rows=4095)
        with self.assertRaises(ValueError):
            encode_batch(0, [0.0]*4097, [], False, MAX_BATCH_BYTES)
        with self.assertRaises(ValueError):
            encode_batch(0, [0.0], [b'x'*(MAX_WIRE_BYTES+1)], True, MAX_BATCH_BYTES)


class LegacyBatchProcessTests(ProcessFixture):
    """真实进程验证批EOF/异常关闭；每例保留实际共享借款，不以余额猜关闭事实。"""

    def batch_read(self, *, mode='data', ids=None, rows=4096, real=False, headroom=0):
        """建立并登记真实批owner。参数: 场景/投影/条数/真实旧库。返回: read。异常: 原构造错误。"""
        request = LegacyCANRequest(self.input_path, self.dbc_path, (self.field,))
        read = LegacyCANBatchRead(request, self.budget, frame_ids=ids, batch_rows=rows,
            consumer_headroom_bytes=headroom,
            _worker_target=None if real else partial(controlled_batch_worker, mode=mode))
        self.reads.append(read)
        return read

    def test_final_data_is_delivered_before_actual_complete(self):
        """最后数据批与完整关闭分开，EOF后重复next幂等。参数: 无。返回: None。异常: 断言失败。"""
        read = self.batch_read()
        self.assertFalse(read.finished)
        row = next(read)
        self.assertEqual(row.records, (sample(),))
        self.assertFalse(read.finished)
        with self.assertRaises(StopIteration):
            next(read)
        self.assertTrue(read.finished)
        self.assertTrue(read.closed)
        self.assertEqual(read.counters['items_accepted'], 1)
        self.assertEqual(read.counters['frames_authorized'], 4096)
        self.assertEqual(self.budget.ram_bytes, self.borrowed)
        with self.assertRaises(StopIteration):
            next(read)

    def test_invalid_protocol_and_exit_never_complete(self):
        """坏包、断管、EOF后异常退出不能冒充成功。参数: 无。返回: None。异常: 断言失败。"""
        for mode in ('bad_start', 'truncated', 'overlong', 'empty_non_eof', 'disconnect', 'bad_exit'):
            read = self.batch_read(mode=mode)
            with self.subTest(mode=mode):
                with self.assertRaises(SourceReadError):
                    list(read)
                self.assertFalse(read.finished)
                read.close()
                self.assertEqual(self.budget.ram_bytes, self.borrowed)

    def test_budget_failure_precedes_batch_permission(self):
        """不足一条最坏空间时不发PULL，保原借款。参数: 无。返回: None。异常: 断言失败。"""
        read = self.batch_read()
        read.start()
        loan = self.budget.memory_budget_bytes - self.budget.ram_bytes - 128*MIN_BATCH_BYTES + 1
        self.budget.reserve_ram(loan)
        try:
            with self.assertRaises(BudgetExceededError):
                next(read)
            self.assertEqual(read.counters['pulls_issued'], 0)
            self.assertEqual(self.budget.ram_bytes, self.borrowed+loan)
        finally:
            self.budget.release_ram(loan)

    def test_send_cancel_preserves_identity_and_reclaims_current_fee(self):
        """实际发送后取消保原对象，并清真实批次费用。参数: 无。返回: None。异常: 断言失败。"""
        read = self.batch_read()
        read.start()
        error = KeyboardInterrupt('batch-send')
        read._connection = BatchConnectionFault(read._connection, operation='send_bytes', error=error, after=True)
        with self.assertRaises(KeyboardInterrupt) as caught:
            next(read)
        self.assertIs(caught.exception, error)
        self.assertFalse(read.finished)
        self.assertTrue(read.closed)
        self.assertIsNone(read._current)
        self.assertEqual(self.budget.ram_bytes, self.borrowed)

    def test_receive_cancel_and_persistent_close_keep_actual_owner(self):
        """接收后取消或关闭持续失败保原对象/费用，恢复不影响借款。参数: 无。返回: None。异常: 断言失败。"""
        read = self.batch_read()
        read.start()
        error = KeyboardInterrupt('batch-receive')
        read._connection = BatchConnectionFault(read._connection, operation='recv_bytes', error=error, after=True)
        with self.assertRaises(KeyboardInterrupt) as caught:
            next(read)
        self.assertIs(caught.exception, error)
        self.assertTrue(read.closed)
        self.assertIsNone(read._pending_reply)
        self.assertEqual(self.budget.ram_bytes, self.borrowed)
        for operation in ('join', 'close'):
            read = self.batch_read()
            next(read)
            failure = OSError('persistent '+operation)
            proxy = ProcessFault(read._process, operation, failure, False)
            read._process = proxy
            with self.assertRaises(OSError) as caught:
                read.close()
            self.assertIs(caught.exception, failure)
            self.assertIs(failure.can_process_read_cleanup_owner, read)
            self.assertFalse(read.closed)
            self.assertGreater(self.budget.ram_bytes, self.borrowed)
            proxy.error = None
            read.close()
            self.assertFalse(read.finished)
            self.assertIsNone(read._current)
            self.assertEqual(self.budget.ram_bytes, self.borrowed)

    def test_small_available_budget_shrinks_wire_without_empty_loop(self):
        """只有最小合法批次预算时仍进展并正确退费。参数: 无。返回: None。异常: 断言失败。"""
        read = self.batch_read()
        read.start()
        loan = self.budget.memory_budget_bytes-self.budget.ram_bytes-128*(MIN_BATCH_BYTES+16)
        self.budget.reserve_ram(loan)
        try:
            batch = next(read)
            self.assertEqual(len(batch.timestamps), 1)
            self.assertEqual(read._batch_limit, MIN_BATCH_BYTES+16)
            with self.assertRaises(StopIteration):
                next(read)
            self.assertTrue(read.finished)
            self.assertEqual(self.budget.ram_bytes, self.borrowed+loan)
        finally:
            self.budget.release_ram(loan)

    def test_consumer_headroom_remains_available_until_consumed(self):
        """缩包后给消费端留出实付空间，不重复付款或侵占借款。参数: 无。返回: None。异常: 断言失败。"""
        headroom = 2*1024*1024
        read = self.batch_read(headroom=headroom)
        read.start()
        loan = self.budget.memory_budget_bytes-self.budget.ram_bytes-128*MIN_BATCH_BYTES-headroom
        self.budget.reserve_ram(loan)
        try:
            next(read)
            self.assertEqual(read._batch_limit, MIN_BATCH_BYTES)
            self.budget.reserve_ram(headroom)
            self.budget.release_ram(headroom)
            with self.assertRaises(StopIteration):
                next(read)
            self.assertEqual(self.budget.ram_bytes, self.borrowed+loan)
        finally:
            self.budget.release_ram(loan)

    def test_invalid_consumer_headroom_is_rejected_without_leak(self):
        """余量不能使用布尔、负数或浮点，构造失败退回固定费。参数: 无。返回: None。异常: 断言失败。"""
        for value in (True, -1, 1.5):
            with self.subTest(value=value), self.assertRaises(SourceReadError):
                self.batch_read(headroom=value)
            self.assertEqual(self.budget.ram_bytes, self.borrowed)

    @unittest.skipUnless(HAS_CAN, '真实CAN可选依赖不可用')
    def test_original_call_trace_same_prefix_and_complete_counts(self):
        """实际旧函数逐帧调用不因选择少做或重排，提前close不读下一批。参数: 无。返回: None。异常: 原IO/断言。"""
        import can
        self.dbc_path.write_text(SYNTHETIC_DBC, encoding='utf-8')
        with can.BLFWriter(str(self.input_path)) as writer:
            for index in range(5):
                writer.on_message_received(can.Message(timestamp=BASE_TIMESTAMP+index*.125,
                    arbitration_id=256 if index%2 == 0 else 257, is_extended_id=False,
                    channel=0, data=bytes([index])))
        request = LegacyCANRequest(self.input_path, self.dbc_path, (self.field,))
        read = LegacyCANBatchRead(request, self.budget, frame_ids=(256,), batch_rows=3,
            _worker_target=observed_batch_worker)
        self.reads.append(read)
        batch = next(read)
        self.assertEqual([x.sequence for x in batch.records], [0,2])
        self.assertEqual(read._exchange({'op':'status'})['parse_calls'], 3)
        read.close()
        trace = self.read_trace()
        self.assertEqual(sum(x['rule']=='load_file' for x in trace), 1)
        self.assertEqual(sum(x['rule']=='next' for x in trace), 3)
        parsed = [x for x in trace if x['rule']=='parse']
        self.assertEqual([x['arbitration_id'] for x in parsed], [256,257,256])
        self.assertEqual([x['data_hex'] for x in parsed], ['00','01','02'])
        self.assertFalse(read.finished)

    @unittest.skipUnless(HAS_CAN, '真实CAN可选依赖不可用')
    def test_real_reader_full_sparse_empty_and_exact_batch_eof(self):
        """真实BLF完整/稀疏/空投影保同刻原序，末批与空EOF明确。参数: 无。返回: None。异常: 原IO或断言。"""
        import can
        self.dbc_path.write_text(SYNTHETIC_DBC, encoding='utf-8')
        with can.BLFWriter(str(self.input_path)) as writer:
            for index, ident in enumerate((256, 257, 256, 257)):
                writer.on_message_received(can.Message(timestamp=BASE_TIMESTAMP+(index//2)*.125,
                    arbitration_id=ident, is_extended_id=False, channel=0, data=bytes([index])))
        for ids in (None, (256,), ()):
            read = self.batch_read(ids=ids, rows=2, real=True)
            read.start()
            self.assertEqual(read._exchange({'op':'status'})['parse_calls'], 0)
            first = next(read)
            # 没有下一批许可时STATUS是控制屏障，证明最多读本批，不用sleep猜测。
            status = read._exchange({'op':'status'})
            self.assertEqual((status['frames_returned'], status['parse_calls']), (2,2))
            batches = [first]+list(read)
            self.assertEqual([len(x.timestamps) for x in batches], [2,2,0])
            records = [r for batch in batches for r in batch.records]
            self.assertEqual([r.sequence for r in records], [0,1,2,3] if ids is None else [0,2] if ids else [])
            if ids:
                self.assertEqual([r.values['Sample'] for r in records], [-1,3])
            self.assertEqual([t for batch in batches for t in batch.timestamps],
                [BASE_TIMESTAMP,BASE_TIMESTAMP,BASE_TIMESTAMP+.125,BASE_TIMESTAMP+.125])
            self.assertTrue(read.finished)
            self.assertEqual(read.counters['items_accepted'], 4)
            self.assertEqual(read.counters['pulls_issued'], 3)
            self.assertEqual(self.budget.ram_bytes, self.borrowed)


if __name__ == '__main__':
    # Windows spawn导入测试模块时不会执行测试或访问真实输入。
    unittest.main()
