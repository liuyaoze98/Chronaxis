"""用独立手算和python-can写出对照验证新ASC解析，不把旧ASC回退当真值。

合成数据仅写新项目work目录；原始快照只读。覆盖纳秒/进制/帧身份/严格坏行，
以及EOF、提前关闭、取消、预算和关闭失败的责任。公共AnalysisRunner接线属于后续C节点。
"""

from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import BudgetExceededError
from chronaxis.sources.asc import ASCSpec, ASCRead, MAX_ASC_LINE_CHARS
from chronaxis.sources.raw_can import CANTextError


class ASCSourceTests(unittest.TestCase):
    """每次测试使用独立目录，严格比较真实字段而非仅比较帧数量。"""

    def setUp(self):
        """创建隔离输出。参数: 无。返回: None。异常: 新项目目录I/O错误。
        """
        # 不清理/改写RefProjects；保留合成工件供失败后复核。
        self.root = Path('work/m3-input-home-20261023/tests') / uuid4().hex
        self.root.mkdir(parents=True)
        self.budget = ResourceBudget()

    def fixture(self, body, *, header='base hex timestamps absolute\n', **options):
        """写合成ASC。参数: body数据、header头、options静态选项。返回: ASCSpec。异常: I/O或配置错。
        """
        # 写到显式新文件，输入格式由测试直接声明，不用被测writer生成预期。
        path = self.root / (uuid4().hex + '.asc')
        path.write_text(header + body, encoding='utf-8')
        return ASCSpec(path, **options)

    def read(self, body, **options):
        """完整消费合成来源。参数: body和fixture选项。返回: 记录list。异常: 被测原错。
        """
        # 这里数据规模固定且很小；长期保存记录的费用不属于reader测试。
        with ASCRead(self.fixture(body, **options), self.budget) as reader:
            return list(reader)

    def test_classic_identity_and_exact_nanoseconds(self):
        """核同刻不同帧及扩展ID。参数: 无。返回: None。异常: 断言失败。
        """
        records = self.read('0.000000001 1 123 Rx d 2 01 ff\n'
                            '0.000000001 2 123x Tx d 1 80\n0.25 1 0 Rx d 0\n')
        # 1ns不经float往返；物理行和yield序号分别保留，同刻两条不去重。
        self.assertEqual([(r.time_ns, r.line_number, r.sequence) for r in records],
                         [(1, 2, 0), (1, 3, 1), (250000000, 4, 2)])
        self.assertEqual(records[0].frame.data, b'\x01\xff')
        self.assertEqual((records[1].frame.channel, records[1].frame.is_extended_id,
                          records[1].frame.is_rx), (1, True, False))
        self.assertEqual(self.budget.ram_bytes, 0)

    def test_decimal_base_and_relative_event_clock(self):
        """计时元数据也参与relative累加。参数: 无。返回: None。异常: 断言失败。
        """
        records = self.read('0.1 Start of measurement\n0.2 1 291 Rx d 1 255\n'
                            '0.3 1 291 Tx d 1 128\n', header='base dec timestamps relative\n')
        # 0.1+0.2=0.3秒，后一条为0.6秒；291十进制是0x123。
        self.assertEqual([r.time_ns for r in records], [300000000, 600000000])
        self.assertEqual(records[0].frame.arbitration_id, 0x123)
        self.assertEqual(records[0].frame.data, b'\xff')

    def test_standard_fd_layout_flags_and_dlc(self):
        """DLC编码9与12字节区分。参数: 无。返回: None。异常: 断言失败。
        """
        payload = ' '.join(f'{i:02x}' for i in range(12))
        records = self.read(f'0 CANFD 2 Tx 123x Voltage 1 1 9 12 {payload} 0 0 7000 0 0 0 0 0\n'
                            '1 CANFD 1 Rx 123 0 0 0 0\n')
        # 标准布局与命名布局都只读取各自载荷，不能把BRS/长度字段当数据字节。
        frame = records[0].frame
        self.assertEqual((frame.is_fd, frame.bitrate_switch, frame.error_state_indicator), (True, True, True))
        self.assertEqual((records[0].dlc_code, frame.dlc, frame.data), (9, 12, bytes(range(12))))
        self.assertEqual((records[1].frame.is_fd, records[1].frame.is_remote_frame), (True, False))

    def test_remote_and_error_records(self):
        """远程DLC不等于实际载荷长度。参数: 无。返回: None。异常: 断言失败。
        """
        remote, error = self.read('0 1 123 Rx r 8\n1 2 ErrorFrame\n')
        self.assertEqual((remote.frame.dlc, remote.frame.data, remote.frame.is_remote_frame), (8, b'', True))
        self.assertTrue(error.frame.is_error_frame)
        self.assertIsNone(error.dlc_code)

    def test_fd_error_keeps_transmit_direction(self):
        """错误帧仍保留明确Tx方向。参数: 无。返回: None。异常: 断言失败。
        """
        record = self.read('0 CANFD 2 Tx ErrorFrame\n')[0]
        self.assertEqual((record.frame.is_fd, record.frame.channel, record.frame.is_rx), (True, 1, False))

    def test_header_date_explicit_timezone_and_offset(self):
        """日历参考采用声明UTC+8。参数: 无。返回: None。异常: 断言失败。
        """
        records = self.read('0.000000001 1 123 Rx d 0\n',
                            header='date Thu Jan 01 08:00:00 AM 1970\nbase hex timestamps absolute\n',
                            time_reference='epoch', timezone_offset_minutes=480, offset_ns=2)
        self.assertEqual(records[0].time_ns, 3)
        with self.assertRaisesRegex(ValueError, '时区'):
            ASCSpec(self.root / 'none.asc', time_reference='epoch')

    def test_trigger_blocks_keep_continuity(self):
        """第二触发块时间不重置到零。参数: 无。返回: None。异常: 断言失败。
        """
        records = self.read('Begin Triggerblock Thu Jan 01 08:00:00.000 1970\n'
                            '0 1 123 Rx d 0\nEnd TriggerBlock\n'
                            'Begin Triggerblock Thu Jan 01 08:00:01.000 1970\n0.1 1 123 Rx d 0\n')
        self.assertEqual([r.time_ns for r in records], [0, 1100000000])

    def test_fractional_nanosecond_rounding_is_recorded(self):
        """保留舍入事实及原文。参数: 无。返回: None。异常: 断言失败。
        """
        record = self.read('0.0000000015 1 123 Rx d 0\n')[0]
        self.assertEqual((record.time_ns, record.time_quantized, record.raw_time), (2, True, '0.0000000015'))

    def test_relative_subnanosecond_deltas_accumulate_before_rounding(self):
        """两次0.5ns累加为1ns，避免逐条舍入累积偏差。参数: 无。返回: None。异常: 断言失败。
        """
        records = self.read('0.0000000005 1 123 Rx d 0\n0.0000000005 1 123 Rx d 0\n',
                            header='base hex timestamps relative\n')
        self.assertEqual([(r.time_ns, r.time_quantized) for r in records], [(0, True), (1, False)])
        # 小于1ns的回退也应拒绝，不能因为舍入成同一坐标就掩盖乱序。
        with self.assertRaisesRegex(CANTextError, '回退'):
            self.read('0.0000000012 1 123 Rx d 0\n0.0000000011 1 123 Rx d 0\n')

    def test_invalid_rows_fail_at_physical_line_without_prefix_replay(self):
        """各种坏行只能抛错，不能吞掉或重放前缀。参数: 无。返回: None。异常: 断言失败。
        """
        bad_rows = ('1 1 123 Rx d 2 ff', '1 1 800 Rx d 0', '1 0 123 Rx d 0',
                    '1 1 123 Rx d 1 100', '1 1 123 Rx d 0 ff',
                    '1 CANFD 1 Rx 123 1 0 9 8 00 00 00 00 00 00 00 00',
                    '1 CANFD 1 Rx 123 2 0 8 8 00 00 00 00 00 00 00 00',
                    '0 1 123 Rx d 0', 'bogus text', '1 1 123 ??? d 0')
        for bad in bad_rows:
            with self.subTest(row=bad):
                spec = self.fixture('0.5 1 123 Rx d 1 01\n' + bad + '\n')
                reader = ASCRead(spec, self.budget)
                self.assertEqual(next(reader).sequence, 0)
                with self.assertRaises(CANTextError) as caught:
                    next(reader)
                self.assertEqual(caught.exception.line_number, 3)
                self.assertEqual(reader.count, 1)
                self.assertEqual(list(reader), [])
                self.assertTrue(reader.closed)
                self.assertEqual(self.budget.ram_bytes, 0)

    def test_boundaries_header_long_line_and_bad_encoding(self):
        """不无限读行或猜测编码。参数: 无。返回: None。异常: 断言失败。
        """
        for spec in (self.fixture('0 1 123 Rx d 0\n', header=''),
                     self.fixture('x' * (MAX_ASC_LINE_CHARS + 1))):
            with self.assertRaises(CANTextError):
                list(ASCRead(spec, self.budget))
            self.assertEqual(self.budget.ram_bytes, 0)
        spec = self.fixture('')
        spec.path.write_bytes(b'base hex timestamps absolute\n\xff\n')
        with self.assertRaisesRegex(CANTextError, '编码') as caught:
            list(ASCRead(spec, self.budget))
        self.assertEqual(caught.exception.line_number, 2)
        self.assertEqual(self.budget.ram_bytes, 0)

    def test_early_close_cancel_and_budget_failure(self):
        """中止不继续读取，取消原错保留。参数: 无。返回: None。异常: 断言失败。
        """
        spec = self.fixture('0 1 123 Rx d 0\n1 1 123 Rx d 0\n')
        reader = ASCRead(spec, self.budget)
        next(reader)
        reader.close()
        reader.close()
        self.assertEqual(list(reader), [])
        self.assertEqual(self.budget.ram_bytes, 0)
        with self.assertRaises(BudgetExceededError):
            ASCRead(spec, ResourceBudget(1024))
        original = RuntimeError('cancel requested')
        with patch.object(self, 'read', side_effect=original):
            reader = ASCRead(spec, self.budget, check_cancel=self.read)
            with self.assertRaises(RuntimeError) as caught:
                next(reader)
        self.assertIs(caught.exception, original)
        self.assertTrue(reader.closed)
        self.assertEqual(self.budget.ram_bytes, 0)

    def test_failed_open_and_cleanup_failure_preserve_recovery_owner(self):
        """清理错误不能取代坏行原错。参数: 无。返回: None。异常: 断言失败。
        """
        with self.assertRaises(FileNotFoundError):
            ASCRead(ASCSpec(self.root / 'none.asc'), self.budget)
        self.assertEqual(self.budget.ram_bytes, 0)
        reader = ASCRead(self.fixture('bad\n'), self.budget)
        with patch.object(reader, 'close', side_effect=OSError('close fault')):
            with self.assertRaises(CANTextError) as caught:
                next(reader)
        self.assertIs(caught.exception.asc_read_cleanup_owner, reader)
        self.assertGreater(self.budget.ram_bytes, 0)
        reader.close()
        self.assertEqual(self.budget.ram_bytes, 0)

    def test_python_can_standard_writer_interoperability(self):
        """与本地python-can标准writer独立对照。参数: 无。返回: None。异常: 断言失败。
        """
        try:
            import can
        except ImportError:
            self.skipTest('独立标准writer对照需要python-can可选依赖')
        path = self.root / 'standard.asc'
        messages = [can.Message(timestamp=1700000000 + i, arbitration_id=0x123,
                                is_extended_id=bool(i), channel=i, data=bytes(range(12 if i else 8)),
                                is_fd=bool(i), bitrate_switch=bool(i)) for i in range(2)]
        with can.ASCWriter(str(path)) as writer:
            for message in messages:
                writer(message)
        # 输出以首触发块为零；比较全部可表示帧字段和相差一秒，不比较无时区头日期。
        records = list(ASCRead(ASCSpec(path), self.budget))
        self.assertEqual([r.time_ns for r in records], [0, 10**9])
        for source, record in zip(messages, records):
            self.assertEqual((record.frame.data, record.frame.channel, record.frame.is_fd,
                              record.frame.is_extended_id, record.frame.bitrate_switch),
                             (bytes(source.data), source.channel, source.is_fd,
                              source.is_extended_id, source.bitrate_switch))
