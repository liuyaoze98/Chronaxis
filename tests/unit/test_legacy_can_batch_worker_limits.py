"""直接驱动生产批次worker，验证字节/条数封口之前不会多调用旧链。

连接和旧vendor都是明确的内存测试替身：连接按脚本交付真实协议bytes，旧链记录
next/parse次数及原序。测试实际执行batch_worker_main、原记录校验和真实批次编码，
不声称这些替身证明真实BLF/DBC兼容性；真实spawn覆盖由既有专项负责。
不读取DBC或日志，不创建文件或进程，不修改旧模块。临时patch只在单例内生效。
新增[home]新鲜记录编码回归复用同一worker替身，检查完整字节与模型先拒绝的顺序。
"""

from collections import deque
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from chronaxis.legacy import batch_worker, worker
from chronaxis.legacy.batch_wire import (BATCH_MAGIC, HEADER, LENGTH, MAX_BATCH_BYTES,
    MAX_BATCH_ROWS, MIN_BATCH_BYTES, decode_batch, encode_batch)
from chronaxis.legacy.records import (LegacyCANRequest, MAX_WIRE_BYTES, decoded_to_dict,
    decode_packet, encode_packet)
from test_legacy_batch_validation import message, original_record
from test_legacy_checked_decode import ChangingMapping


class ControlledOriginalChain:
    """明确替代原vendor的有限消息链，累计调用事实，绝不打开真实来源。"""

    def __init__(self, count, values):
        """保存合成输入和计数。参数: count/values为条数与原值。返回: 替身。异常: 无。"""
        self.count, self.values = count, values
        self.next_calls = self.parse_calls = self.close_calls = 0
        self.load_calls = self.iter_calls = 0
        self.parsed_sequences = []
        self.db = SimpleNamespace(messages=())

    def load_file(self, path):
        """模拟一次原DBC加载。参数: path为合成路径。返回: 同一db。异常: 路径断言失败。"""
        assert path == 'synthetic.dbc', path
        self.load_calls += 1
        return self.db

    def iter_frames(self, path):
        """模拟一次原迭代入口。参数: path为合成路径。返回: 自身。异常: 路径断言失败。"""
        assert path == 'synthetic.blf', path
        self.iter_calls += 1
        return self

    def __iter__(self):
        """提供原顺序迭代器。参数: 无。返回: 自身。异常: 无。"""
        return self

    def __next__(self):
        """计入真实EOF探测，按原序生成消息。参数: 无。返回: 消息。异常: 真StopIteration。"""
        sequence = self.next_calls
        self.next_calls += 1
        if sequence >= self.count:
            raise StopIteration
        # 时间固定，确保接近64KiB用例的动态长度只取决于原序号位数。
        msg = message(timestamp=0.0, arbitration_id=256)
        msg.synthetic_sequence = sequence
        return msg

    def parse_frame(self, msg, db):
        """记录每条原消息的唯一解码调用。参数: msg/db。返回: 原values。异常: 身份断言失败。"""
        assert db is self.db
        self.parse_calls += 1
        self.parsed_sequences.append(msg.synthetic_sequence)
        return self.values

    def close(self):
        """记录生成器关闭，不推进输入。参数: 无。返回: None。异常: 无。"""
        self.close_calls += 1


class ScriptedBytesConnection:
    """按明确脚本提供许可，记录发送时的原调用数；没有线程、睡眠或隐式预读。"""

    def __init__(self, chain, commands):
        """准备INIT与控制脚本。参数: chain及(command,next,parse)序列。返回: 连接。异常: 无。"""
        init = {'op': 'init', 'version': 1, 'path': 'synthetic.blf',
                'dbc_path': 'synthetic.dbc', 'fields': []}
        self.chain = chain
        self.commands = deque([(init, 0, 0), *commands])
        self.sent, self.closed = [], False

    def recv_bytes(self, limit):
        """交付下一许可前验证上一批未多读。参数: limit为控制包上限。返回: bytes。异常: 断言。"""
        assert self.commands, 'worker在脚本末尾仍试图取得未授权控制消息'
        packet, expected_next, expected_parse = self.commands.popleft()
        actual = self.chain.next_calls, self.chain.parse_calls
        assert actual == (expected_next, expected_parse), (packet, actual)
        payload = encode_packet(packet)
        assert len(payload) <= limit
        return payload

    def send_bytes(self, payload):
        """保留真实生产字节及发送时计数。参数: payload。返回: None。异常: 分配错误。"""
        self.sent.append((payload, self.chain.next_calls, self.chain.parse_calls))

    def close(self):
        """记录连接关闭。参数: 无。返回: None。异常: 无。"""
        self.closed = True


def pull(start, *, size=MAX_BATCH_BYTES, ids=None):
    """生成明确单批许可。参数: start/size/ids为原序、上限和投影。返回: dict。异常: 无。"""
    return {'op': 'pull_batch', 'request_id': start, 'rows': MAX_BATCH_ROWS,
            'bytes': size, 'frame_ids': ids}


class LegacyBatchWorkerLimitTests(unittest.TestCase):
    """围绕实际worker循环验证封口、EOF及未选值检查，补足纯编解码测试。"""

    def run_worker(self, count, values, commands, *, error=False):
        """以明确替身执行实际生产worker，并核初始化/收尾次数。

        参数: count/values为原输入，commands为许可脚本，error表示预期失败退出。
        返回: (chain,connection)。异常: 非预期worker错误或调用/关闭断言失败。
        """
        chain = ControlledOriginalChain(count, values)
        connection = ScriptedBytesConnection(chain, commands)
        request = LegacyCANRequest(Path('synthetic.blf'), Path('synthetic.dbc'), ())
        processor = SimpleNamespace(parse_frame=chain.parse_frame,
            cantools=SimpleNamespace(database=SimpleNamespace(load_file=chain.load_file)))
        versions = {'python-can': 'controlled-test', 'cantools': 'controlled-test',
                    'natsort': 'controlled-test'}
        # 只替换需要磁盘/旧库的入口；消息循环、字段/值校验及编码均执行生产实现。
        with patch.object(worker, '_request', return_value=request), \
                patch.object(worker, '_load_vendor', return_value=(chain, processor, {})), \
                patch.object(batch_worker.metadata, 'version', side_effect=versions.__getitem__):
            if error:
                with self.assertRaises(SystemExit) as caught:
                    batch_worker.batch_worker_main(connection)
                self.assertEqual(caught.exception.code, 1)
            else:
                batch_worker.batch_worker_main(connection)
        self.assertEqual((chain.load_calls, chain.iter_calls, chain.close_calls), (1, 1, 1))
        self.assertTrue(connection.closed)
        self.assertFalse(connection.commands, '许可脚本应被完整执行，不用提前失败伪造封口')
        self.assertEqual(connection.sent[0][1:], (0, 0), 'READY之前不得next或parse')
        self.assertEqual(decode_packet(connection.sent[0][0])['op'], 'ready')
        return chain, connection

    def unpack_batches(self, connection, *, size=MAX_BATCH_BYTES, ids=None):
        """按已发送原序逐批解包。参数: connection及许可。返回: 批次/EOF列表。异常: 原解包错误。"""
        result, start = [], 0
        for payload, _, _ in connection.sent:
            if payload.startswith(BATCH_MAGIC):
                batch, eof = decode_batch(payload, expected_start=start, row_limit=MAX_BATCH_ROWS,
                    byte_limit=size, frame_ids=None if ids is None else tuple(ids))
                start += len(batch.timestamps)
                result.append((batch, eof))
        return result

    def test_near_64kib_records_stop_at_bytes_before_reading_next(self):
        """原ITEM恰好64KiB时按实际字节提前封口，STOP前不会偷读下一帧。

        参数: 无。返回: None。异常: 多next/parse、超包、丢失或重复记录令断言失败。
        """
        msg = message(timestamp=0.0, arbitration_id=256)
        base = {'op': 'item', 'request_id': 0,
                'record': decoded_to_dict(original_record(msg, {'x': 0}, 0))}
        values = {'x' + 'a' * (MAX_WIRE_BYTES - len(encode_packet(base))): 0}
        full = {'op': 'item', 'request_id': 0,
                'record': decoded_to_dict(original_record(msg, values, 0))}
        self.assertEqual(len(encode_packet(full)), MAX_WIRE_BYTES)
        record_bytes = len(encode_packet(full['record']))
        for size, expected_count in ((MAX_BATCH_BYTES, 4), (MIN_BATCH_BYTES, 1)):
            with self.subTest(size=size):
                # 独立检查预期条数确实填满本次许可，不能把实现返回数当作期望。
                occupied = HEADER.size + expected_count * (8 + LENGTH.size + record_bytes)
                self.assertLessEqual(occupied, size)
                self.assertGreater(occupied + 8 + LENGTH.size + MAX_WIRE_BYTES, size)
                commands = [(pull(0, size=size), 0, 0),
                            ({'op': 'status'}, expected_count, expected_count),
                            ({'op': 'stop'}, expected_count, expected_count)]
                chain, connection = self.run_worker(expected_count + 1, values, commands)
                batches = self.unpack_batches(connection, size=size)
                self.assertEqual(len(batches), 1)
                batch, eof = batches[0]
                self.assertFalse(eof)
                self.assertEqual([row.sequence for row in batch.records], list(range(expected_count)))
                self.assertEqual(chain.parsed_sequences, list(range(expected_count)))
                status = decode_packet(connection.sent[-1][0])
                self.assertEqual((status['frames_returned'], status['parse_calls']),
                                 (expected_count, expected_count))

    def test_byte_split_continuation_preserves_last_record_and_real_eof(self):
        """最小单条包跨三个许可保全部原序，第四许可才实际探测到EOF。

        参数: 无。返回: None。异常: 包满后藏起多读帧、跳号或提前EOF令断言失败。
        """
        commands = [(pull(index, size=MIN_BATCH_BYTES), index, index) for index in range(4)]
        chain, connection = self.run_worker(3, {}, commands)
        batches = self.unpack_batches(connection, size=MIN_BATCH_BYTES)
        self.assertEqual([len(batch.timestamps) for batch, _ in batches], [1, 1, 1, 0])
        self.assertEqual([eof for _, eof in batches], [False, False, False, True])
        self.assertEqual([row.sequence for batch, _ in batches for row in batch.records], [0, 1, 2])
        self.assertEqual((chain.next_calls, chain.parse_calls), (4, 3))

    def test_4095_4096_4097_rows_and_eof_keep_every_original_time(self):
        """空投影仍逐条读/解码；4096条整批不能提前探测下一条或伪造EOF。

        参数: 无。返回: None。异常: 原调用数、批次跨度或EOF标志不符。
        """
        for count, expected_lengths, expected_eof in ((4095, [4095], [True]),
                (4096, [4096, 0], [False, True]), (4097, [4096, 1], [False, True])):
            commands = [(pull(0, ids=[]), 0, 0)]
            if count >= MAX_BATCH_ROWS:
                commands.append((pull(MAX_BATCH_ROWS, ids=[]), MAX_BATCH_ROWS, MAX_BATCH_ROWS))
            with self.subTest(count=count):
                chain, connection = self.run_worker(count, {}, commands)
                batches = self.unpack_batches(connection, ids=[])
                self.assertEqual([len(batch.timestamps) for batch, _ in batches], expected_lengths)
                self.assertEqual([eof for _, eof in batches], expected_eof)
                self.assertTrue(all(not batch.records for batch, _ in batches))
                self.assertTrue(all(timestamp == 0.0 for batch, _ in batches for timestamp in batch.timestamps))
                self.assertEqual(chain.parsed_sequences, list(range(count)))
                self.assertEqual((chain.next_calls, chain.parse_calls), (count + 1, count))

    def test_unselected_invalid_and_overlong_values_still_fail_before_batch_send(self):
        """投影为空也拒绝坏值/超64KiB记录，不部分交付或继续读取下一帧。

        参数: 无。返回: None。异常: 未选坏值被接受、未正确报告远端错误或多读。
        """
        for values, error_type in (({'x': 'not-numeric'}, 'TypeError'),
                                   ({'x' * MAX_WIRE_BYTES: 0}, 'ValueError')):
            with self.subTest(error_type=error_type):
                chain, connection = self.run_worker(2, values, [(pull(0, ids=[]), 0, 0)], error=True)
                self.assertEqual((chain.next_calls, chain.parse_calls), (1, 1))
                self.assertFalse(any(packet.startswith(BATCH_MAGIC) for packet, _, _ in connection.sent))
                error = decode_packet(connection.sent[-1][0])
                self.assertEqual((error['op'], error['phase'], error['request_id']), ('error', 'batch', 0))
                self.assertEqual(error['error']['type'], error_type)

    def test_fresh_record_keeps_complete_public_bytes(self):
        """实际worker完整批字节与公共编码一致，保诊断标签、Unicode、负零和大整数。

        参数: 无。返回: None。异常: 字节、原调用数或真实EOF不符时断言失败。
        """
        values = {'zero': 0, 'false': False, 'true': True, 'negative_zero': -0.0,
            'nan': float('nan'), 'inf': float('inf'), '-inf': -float('inf'),
            '电压\n"\\\x00😀': 2**2048, 'e\u0301': -2**2048}
        record = original_record(message(timestamp=0.0, arbitration_id=256), values, 0)
        expected = encode_batch(0, [0.0], [encode_packet(decoded_to_dict(record))],
            True, MAX_BATCH_BYTES)
        chain, connection = self.run_worker(1, values, [(pull(0), 0, 0)])
        # 比实际发送的完整包，不能用新编码器自身往返充当期望。
        self.assertEqual(connection.sent[1][0], expected)
        self.assertEqual((chain.next_calls, chain.parse_calls), (2, 1))

    def test_selected_model_rejects_bad_values_before_fresh_encoding(self):
        """保留帧仍先完成两遍Mapping及Unicode/64KiB检查，不把坏值交给私有编码器。

        参数: 无。返回: None。异常: 错误顺序、原调用数或提前发送批数据不符。
        """
        changing = ChangingMapping()
        for values, kind in ((changing, 'TypeError'), ({'\ud800': 0}, 'UnicodeEncodeError'),
                ({'x' * MAX_WIRE_BYTES: 0}, 'ValueError')):
            with self.subTest(kind=kind), patch.object(batch_worker, '_encode_fresh_packet') as encode:
                chain, connection = self.run_worker(2, values, [(pull(0), 0, 0)], error=True)
                encode.assert_not_called()
                self.assertEqual((chain.next_calls, chain.parse_calls), (1, 1))
                self.assertFalse(any(data.startswith(BATCH_MAGIC) for data, _, _ in connection.sent))
                error = decode_packet(connection.sent[-1][0])
                self.assertEqual((error['phase'], error['error']['type']), ('batch', kind))
        self.assertEqual(changing.visits, 2, '第二遍原值变化仍须在完整模型内拒绝')

    def test_fresh_encoding_checks_actual_byte_limit(self):
        """即使模型已检查，实际编码结束仍核传输上限；原ITEM的64KiB边界由既有用例覆盖。

        参数: 无。返回: None。异常: 等长被拒或超长被放行时断言失败。
        """
        record = original_record(message(), {'电压😀': 1}, 0)
        packet = decoded_to_dict(record)
        expected = encode_packet(packet)
        # 只缩小私有编码器的上限，保持输入来自真实完整模型，以触发最后一道长度防线。
        with patch.object(batch_worker, 'MAX_WIRE_BYTES', len(expected)):
            self.assertEqual(batch_worker._encode_fresh_packet(packet), expected)
        with patch.object(batch_worker, 'MAX_WIRE_BYTES', len(expected) - 1):
            with self.assertRaisesRegex(ValueError, '^wire包超过65536字节$'):
                batch_worker._encode_fresh_packet(packet)

    def test_fresh_encoding_cancellation_clears_own_traceback_references(self):
        """编码取消保留原异常对象，本层失败栈不继续持有记录树和输出缓冲。

        参数: 无。返回: None。异常: 取消被替换、吞掉或本层仍留大引用时断言失败。
        """
        packet = decoded_to_dict(original_record(message(), {'value': 1}, 0))
        for failure in (KeyboardInterrupt('cancel'), MemoryError('allocation')):
            with self.subTest(kind=type(failure).__name__):
                try:
                    with patch.object(batch_worker.json, 'dumps', side_effect=failure):
                        batch_worker._encode_fresh_packet(packet)
                except BaseException as caught:
                    self.assertIs(caught, failure)
                    trace, found = caught.__traceback__, False
                    while trace is not None:
                        if trace.tb_frame.f_code is batch_worker._encode_fresh_packet.__code__:
                            found = True
                            self.assertIsNone(trace.tb_frame.f_locals['packet'])
                            self.assertIsNone(trace.tb_frame.f_locals['payload'])
                        trace = trace.tb_next
                    self.assertTrue(found)
                else:
                    self.fail('必须传播原编码取消')


if __name__ == '__main__':
    unittest.main()
