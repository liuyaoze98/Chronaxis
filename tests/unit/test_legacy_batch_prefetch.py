"""验证有界CAN预取的正常读取、双批费用、同步回退及真实接线。

现场生成小BLF/DBC，只写home工作目录。成功读取与同步入口逐字段比较，
原函数trace独立核次数和顺序；原子取消/关闭失败由专门故障模块覆盖。
不使用耗时快慢推断预取成功，使用许可、真实管道回应与费用槽作为证据。
"""

import unittest
from unittest.mock import patch

from chronaxis.legacy import batch_read as module
from chronaxis.legacy.batch_wire import MIN_BATCH_BYTES
from chronaxis.legacy.records import LegacyCANRequest, decoded_to_dict, encode_packet
from chronaxis.results.errors import ResultClosedError
from chronaxis.sources.protocol import SourceReadError
from test_legacy_can_batch import observed_batch_worker
from test_legacy_can_process import (ProcessFixture, HAS_CAN, SYNTHETIC_DBC,
                                     BASE_TIMESTAMP)


@unittest.skipUnless(HAS_CAN, '真实CAN可选依赖不可用')
class LegacyBatchPrefetchTests(ProcessFixture):
    """每例拥有独立真实输入和借款，关闭后不可抵销其他owner的余额。"""

    def write_frames(self, count):
        """写同刻及交错报文的有限真输入。

        参数: count为原帧数。返回: None。异常: 原writer或文件错误。
        """
        import can
        self.dbc_path.write_text(SYNTHETIC_DBC, encoding='utf-8')
        with can.BLFWriter(str(self.input_path)) as writer:
            for index in range(count):
                writer.on_message_received(can.Message(
                    timestamp=BASE_TIMESTAMP + (index // 2) * .125,
                    arbitration_id=256 if index % 2 == 0 else 257,
                    is_extended_id=False, channel=0, data=bytes([index])))

    def batch_read(self, *, prefetch=True, ids=(256,), rows=2, headroom=0, observed=False):
        """建立已登记的真实read，不立即启动。

        参数: 预取/投影/批大小/余量/是否观察原函数。返回: read。异常: 原构造错误。
        """
        request = LegacyCANRequest(self.input_path, self.dbc_path, (self.field,))
        read = module.LegacyCANBatchRead(request, self.budget, frame_ids=ids,
            batch_rows=rows, consumer_headroom_bytes=headroom, prefetch=prefetch,
            _worker_target=observed_batch_worker if observed else None)
        self.reads.append(read)
        return read

    def test_full_sparse_and_empty_projection_match_sync_bytes(self):
        """完整/稀疏/空投影保全部时间与原记录字节，不改变数值。

        参数: 无。返回: None。异常: 原读取或逐字段断言失败。
        """
        self.write_frames(5)
        for ids in (None, (256,), ()):
            with self.subTest(ids=ids):
                baseline = self.batch_read(prefetch=False, ids=ids)
                expected = list(baseline)
                read = self.batch_read(ids=ids)
                actual = list(read)
                self.assertEqual(actual, expected)
                self.assertEqual([encode_packet(decoded_to_dict(row))
                    for batch in actual for row in batch.records],
                    [encode_packet(decoded_to_dict(row))
                    for batch in expected for row in batch.records])
                self.assertEqual(read.counters, baseline.counters)
                self.assertTrue(read.finished and read.closed)
                self.assertEqual(read._exit_code, 0)
                self.assertEqual(self.budget.ram_bytes, self.borrowed)

    def test_two_full_paid_slots_and_successful_original_call_order(self):
        """两槽已付款且余量可实际借用，原next/parse顺序和次数不变。

        参数: 无。返回: None。异常: 原来源错误或费用/trace断言失败。
        """
        self.write_frames(5)
        headroom = 2 * 1024 ** 2
        read = self.batch_read(headroom=headroom, observed=True)
        first = next(read)
        self.assertEqual(first.start_sequence, 0)
        self.assertEqual(read._prefetch_packet['request_id'], 2)
        self.assertEqual(read._prefetch_cost, 128 * read._prefetch_packet['bytes'])
        self.assertEqual(read._current_cost, 128 * read._batch_limit)
        self.assertTrue(read._waiting)
        self.assertEqual(read.counters['pulls_issued'], 2)
        self.assertEqual(read.counters['items_accepted'], 2)
        self.budget.reserve_ram(headroom)
        self.budget.release_ram(headroom)
        with self.assertRaises(SourceReadError):
            read._try_prefetch()
        self.assertEqual(read.counters['pulls_issued'], 2)
        batches = [first] + list(read)
        self.assertEqual([len(batch.timestamps) for batch in batches], [2, 2, 1])
        trace = self.read_trace()
        events = [item['rule'] for item in trace]
        self.assertEqual(events.count('load_file'), 1)
        self.assertEqual(events.count('next'), 6)
        self.assertEqual(events.count('parse'), 5)
        self.assertEqual([item['data_hex'] for item in trace if item['rule'] == 'parse'],
                         ['00', '01', '02', '03', '04'])
        self.assertTrue(read.finished and read.closed)
        self.assertEqual(self.budget.ram_bytes, self.borrowed)

    def test_low_budget_uses_only_sync_and_preserves_headroom(self):
        """余额只够一批时不预取，仍能完整读取与给消费者付款。

        参数: 无。返回: None。异常: 原预算/来源错误或断言失败。
        """
        self.write_frames(5)
        headroom = 1024 ** 2
        read = self.batch_read(headroom=headroom).start()
        loan = (self.budget.memory_budget_bytes - self.budget.ram_bytes
                - headroom - 128 * MIN_BATCH_BYTES)
        self.budget.reserve_ram(loan)
        try:
            first = next(read)
            self.assertFalse(read._waiting)
            self.assertIsNone(read._prefetch_packet)
            self.assertEqual(read._prefetch_cost, 0)
            self.assertEqual(read.counters['pulls_issued'], 1)
            self.budget.reserve_ram(headroom)
            self.budget.release_ram(headroom)
            batches = [first] + list(read)
            self.assertEqual(sum(len(batch.timestamps) for batch in batches), 5)
            # 最小字节包每读前须留下完整64KiB单条空间，故本例每包一帧，另有真实空EOF。
            self.assertEqual([len(batch.timestamps) for batch in batches], [1, 1, 1, 1, 1, 0])
            self.assertEqual(read.counters['pulls_issued'], 6)
            self.assertTrue(read.finished)
            self.assertEqual(self.budget.ram_bytes, self.borrowed + loan)
        finally:
            read.close()
            self.budget.release_ram(loan)

    def test_early_close_can_consume_one_additional_batch_only(self):
        """已交付两帧后至多再读已授权两帧，提前close不能声明完整EOF。

        参数: 无。返回: None。异常: 原关闭或真实消费前缀断言失败。
        """
        self.write_frames(5)
        read = self.batch_read(observed=True)
        next(read)
        # 等真实回应证明预取已完成，不接收它，也不再授予第三次许可。
        self.assertTrue(read._connection.poll(5))
        read.close()
        trace = self.read_trace()
        self.assertEqual([x['rule'] for x in trace].count('next'), 4)
        self.assertEqual([x['rule'] for x in trace].count('parse'), 4)
        self.assertEqual(read.counters['items_accepted'], 2)
        self.assertEqual(read.counters['pulls_issued'], 2)
        self.assertFalse(read.finished)
        self.assertTrue(read.closed)
        self.assertEqual((read._current_cost, read._prefetch_cost), (0, 0))

    def test_empty_and_exact_batch_eof_require_actual_close(self):
        """空文件/整批结束仍核真实空EOF，并保最后批费用至实际关闭。

        参数: 无。返回: None。异常: 原IO/协议错误或断言失败。
        """
        for count, expected in ((0, [0]), (4, [2, 2, 0])):
            with self.subTest(count=count):
                self.write_frames(count)
                read = self.batch_read()
                sizes = []
                while not read._batch_eof:
                    sizes.append(len(next(read).timestamps))
                self.assertEqual(sizes, expected)
                self.assertFalse(read.finished)
                self.assertIsNone(read._prefetch_packet)
                self.assertEqual(read._prefetch_cost, 0)
                self.assertGreater(read._current_cost, 0)
                with self.assertRaises(StopIteration):
                    next(read)
                self.assertTrue(read.finished and read.closed)
                self.assertEqual(self.budget.ram_bytes, self.borrowed)

    def test_default_off_and_invalid_flags_preserve_original_entry(self):
        """默认仍只读当前批，非bool开关构造失败且不泄漏。

        参数: 无。返回: None。异常: 原错误或前缀/预算断言失败。
        """
        self.write_frames(5)
        request = LegacyCANRequest(self.input_path, self.dbc_path, (self.field,))
        read = module.LegacyCANBatchRead(request, self.budget, batch_rows=2,
                                       _worker_target=observed_batch_worker)
        self.reads.append(read)
        self.assertFalse(read._prefetch)
        next(read)
        status = read._exchange({'op': 'status'})
        self.assertEqual(status['parse_calls'], 2)
        self.assertEqual(read._prefetch_cost, 0)
        read.close()
        for flag in (None, 0, 1, 'true'):
            with self.subTest(flag=flag), self.assertRaises(SourceReadError):
                module.LegacyCANBatchRead(request, self.budget, prefetch=flag)
            self.assertEqual(self.budget.ram_bytes, self.borrowed)

    def test_dynamic_headroom_is_strict_and_never_blocks_sync(self):
        """额外余量只阻止预取，不能误拒仍有预算的同步读取。

        参数: 无。返回: None。异常: 原来源错误或类型/费用断言失败。
        """
        self.write_frames(5)
        read = self.batch_read()
        for value, error in ((True, TypeError), (1.0, TypeError), (None, TypeError), (-1, ValueError)):
            with self.subTest(value=value), self.assertRaises(error):
                read._set_prefetch_headroom(value)
        read._set_prefetch_headroom(self.budget.memory_budget_bytes)
        first = next(read)
        self.assertFalse(read._waiting)
        self.assertEqual(read._prefetch_cost, 0)
        self.assertEqual(sum(len(batch.timestamps) for batch in [first] + list(read)), 5)
        self.assertTrue(read.finished and read.closed)
        with self.assertRaises(ResultClosedError):
            read._set_prefetch_headroom(0)


@unittest.skipUnless(HAS_CAN, '真实CAN可选依赖不可用')
class CANPrefetchWiringTests(unittest.TestCase):
    """只复用独立来源夹具设置，不继承并重复执行其已有全部测试。"""

    def test_real_adapter_enables_prefetch_with_existing_headroom(self):
        """公共CAN分析接线显式开启预取，保原消费余量和全源完成事实。

        参数: 无。返回: None。异常: 原来源错误或接线/关闭断言失败。
        """
        from test_can_batch_history import NeededCANHistoryTests
        fixture = NeededCANHistoryTests('test_sparse_history_full_observation_and_same_time')
        fixture.setUp()
        try:
            with patch.object(module, 'LegacyCANBatchRead', wraps=module.LegacyCANBatchRead) as factory:
                read = fixture.read()
                list(read)
                self.assertTrue(factory.call_args.kwargs['prefetch'])
                self.assertGreater(factory.call_args.kwargs['consumer_headroom_bytes'], 0)
                self.assertTrue(read.finished)
                self.assertEqual(read.observation.row_count, 6)
        finally:
            fixture.tearDown()


if __name__ == '__main__':
    unittest.main()
