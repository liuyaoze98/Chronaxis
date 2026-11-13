"""核对无DLC远程帧从ASC读取、暂存到导出时不会被误写为长度零。

使用临时合成ASC及真实导出器；不读取历史输入。ASC保留未知长度，BLF因不能
表达未知长度明确拒绝，失败后归还预算且不发布完成结果。
"""

import json
from pathlib import Path
import unittest

from workspace_fixtures import TemporaryDirectory
from published_paths import published_file
from chronaxis.core.models import Interval
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.frame_exports import FrameExportSpec, as_export_frame, export_can_frames
from chronaxis.results.frame_rebuild import _frame_packet, _restore_frame
from chronaxis.sources.asc import ASCRead, ASCSpec
from chronaxis.sources.blf import BLFRead, BLFSpec


class UnknownRemoteDLCExportTests(unittest.TestCase):
    """对未知长度和明确零长度分别检查，避免把二者混为一类。"""

    def setUp(self):
        """创建自有合成输入。参数: 无。返回: None。异常: 文件系统错误。"""
        directory = TemporaryDirectory(prefix='unknown-dlc-', dir='work')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.budget = ResourceBudget()
        self.source = self.root / 'input.asc'
        self.source.write_text('base hex timestamps absolute\n0.0 1 100 Rx r\n0.1 1 100 Rx r 0\n', encoding='ascii')
        with ASCRead(ASCSpec(self.source), self.budget) as reader:
            self.records = tuple(reader)

    def test_asc_round_trip_and_optional_details_preserve_unknown(self):
        """两种明细模式均保留省略DLC，明确零仍为零。参数: 无。返回: None。异常: 断言。"""
        for compact in (True, False):
            with self.subTest(compact=compact):
                manifest = export_can_frames(self.records, FrameExportSpec(), Interval(0, 200000000),
                    self.root / str(compact), self.budget, source='bus', device_label='试验台', compact=compact)
                with ASCRead(ASCSpec(published_file(manifest, 'frames.asc')), self.budget) as reader:
                    actual = tuple(reader)
                self.assertEqual([item.dlc_code for item in actual], [None, 0])
                if not compact:
                    rows = [json.loads(line) for line in published_file(manifest, 'frames.jsonl').read_text(encoding='utf-8').splitlines()]
                    self.assertEqual([item['frame']['dlc'] for item in rows], [None, 0])
                self.assertEqual(self.budget.ram_bytes, 0)

    def test_export_spool_keeps_the_unknown_length(self):
        """经过输出排序暂存仍能区分未知与零。参数: 无。返回: None。异常: 断言。"""
        for record in self.records:
            value = as_export_frame(record, compact=True)
            restored = _restore_frame(_frame_packet(value))
            self.assertEqual(restored, value)
        self.assertFalse(as_export_frame(self.records[0]).remote_dlc_known)
        self.assertTrue(as_export_frame(self.records[1]).remote_dlc_known)

    def test_blf_refuses_unknown_length_and_releases_resources(self):
        """BLF不能表达未知长度时拒绝发布，不编造DLC。参数: 无。返回: None。异常: 断言。"""
        destination = self.root / 'blf'
        spec = FrameExportSpec('blf', 0, 'relative', '2026-11-11', 480)
        with self.assertRaisesRegex(ValueError, '未提供DLC'):
            export_can_frames(self.records, spec, Interval(0, 200000000), destination,
                self.budget, source='bus', device_label='lab-pc')
        self.assertFalse(destination.exists())
        self.assertEqual(self.budget.ram_bytes, 0)

    def test_real_blf_remote_lengths_survive_asc_and_blf_exports(self):
        """真实BLF的远程长度8和0往返均明确保留。参数: 无。返回: None。异常: 断言或I/O。

        同时放入普通数据帧，确保补充远程帧长度不会改变其他帧的可选DLC记录。
        """
        import can

        source = self.root / 'known-lengths.blf'
        writer = can.BLFWriter(source)
        try:
            for index, length in enumerate((8, 0)):
                writer.on_message_received(can.Message(timestamp=1700000000.0 + index * 0.125,
                    arbitration_id=0x100, is_extended_id=False, is_remote_frame=True,
                    dlc=length, channel=0, is_rx=True))
            writer.on_message_received(can.Message(timestamp=1700000000.25,
                arbitration_id=0x101, is_extended_id=False, data=b'\x42', channel=0, is_rx=True))
        finally:
            writer.stop()

        reader = BLFRead(BLFSpec(source), self.budget)
        try:
            records = tuple(reader)
        finally:
            reader.close()
        self.assertEqual([record.dlc_code for record in records], [8, 0, None])
        self.assertEqual(self.budget.ram_bytes, 0)
        for record in records:
            exported = as_export_frame(record, compact=True)
            self.assertTrue(exported.remote_dlc_known)
            self.assertEqual(_restore_frame(_frame_packet(exported)), exported)

        interval = Interval(records[0].time_ns, records[-1].time_ns + 1)
        for format_name in ('asc', 'blf'):
            with self.subTest(format=format_name):
                spec = FrameExportSpec(format_name, source_time_reference='epoch')
                manifest = export_can_frames(records, spec, interval, self.root / format_name,
                    self.budget, source='bus', device_label='lab-pc', compact=True)
                path = published_file(manifest, 'frames.' + format_name)
                result_reader = (ASCRead(ASCSpec(path), self.budget) if format_name == 'asc'
                    else BLFRead(BLFSpec(path), self.budget))
                try:
                    actual = tuple(result_reader)
                finally:
                    result_reader.close()
                self.assertEqual([record.frame.dlc for record in actual], [8, 0, 1])
                self.assertEqual([record.dlc_code for record in actual[:2]], [8, 0])
                self.assertEqual([record.frame.is_remote_frame for record in actual], [True, True, False])
                self.assertEqual(actual[-1].frame.data, b'\x42')
                self.assertEqual(self.budget.ram_bytes, 0)
