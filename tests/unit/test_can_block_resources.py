"""核固定 CAN 块的有限键复用和失败后所有权，不依赖真实报文或性能阈值。"""
from dataclasses import replace
import gc
import struct
import unittest
from unittest.mock import patch
import weakref

from chronaxis.execution import can_block_codec as codec
from chronaxis.legacy.records import LegacyCANField
from chronaxis.sources import can_spec, text_can_decode
from chronaxis.sources.text_can_decode import DecodedCANRecord
from test_can_block_codec import record, facts


class CANBlockKeyReuseTests(unittest.TestCase):
    """同块复用已核键；新块及公开构造继续完整检查。"""

    def test_keys_checked_once_per_block_and_public_constructor_unchanged(self):
        """核每块两键只解析两次，且公共构造没有继承内部信任。"""
        first = record()
        second_key = LegacyCANField(0, 'Voltage', 0x123, False, False).key
        first = replace(first, values=first.values + ((second_key, 400.0),))
        originals = [replace(first, sequence=i, raw=replace(first.raw, sequence=i)) for i in range(8)]
        packet = codec.encode_block(0, originals, True, facts())
        calls = []
        original_parse = can_spec.can_field_from_key
        def observed(key):
            """记录真实完整解析，不替换其检查结果。"""
            calls.append(key)
            return original_parse(key)
        with patch.object(can_spec, 'can_field_from_key', observed), patch.object(text_can_decode, 'can_field_from_key', observed):
            self.assertEqual(codec.decode_block(packet)[1], originals)
            self.assertEqual(len(calls), 2)
            self.assertEqual(codec.decode_block(packet)[1], originals)
            self.assertEqual(len(calls), 4)
            self.assertEqual(replace(first), first)
            self.assertEqual(len(calls), 6)
        self.assertNotIn('value', calls)  # 原物理字段名称不作为规范CAN键解析。

    def test_new_block_rejects_noncanonical_key(self):
        """上一块合法不使下一块非规范JSON字段获准。"""
        original = record()
        codec.decode_block(codec.encode_block(0, [original], False, facts()))
        invalid = replace(original)
        key, value = invalid.values[0]
        object.__setattr__(invalid, 'values', ((' ' + key, value),))
        with self.assertRaisesRegex(ValueError, '规范'):
            codec.decode_block(codec.encode_block(1, [invalid], True, facts()))


class CANBlockResourceTests(unittest.TestCase):
    """原异常保留时，只允许其失败模型诊断存活，不保留整块或内部包视图。"""

    def damaged_packet(self, mode):
        """建立八条包含大整数的记录，修改一处真实私有协议事实。"""
        large = (1 << (16_384 * 8 - 1)) + 17
        first = record(large)
        records = [replace(first, sequence=i, raw=replace(first.raw, sequence=i)) for i in range(8)]
        if mode == 'model':
            object.__setattr__(records[-1], 'status', 'unselected')
        packet = codec.encode_block(0, records, True, facts())
        if mode == 'trailing':
            packet = packet[:4] + struct.pack('!I', len(packet)-7) + packet[8:] + b'\x01'
        elif mode == 'integer':
            reader = codec._Reader(packet)
            offset = reader.position
            reader.close()
            self.assertEqual(packet[offset:offset+6], b'\x03\x00\x00\x00\x01\x00')
            packet = packet[:offset] + b'\x03\x00\x00\x00\x02\x00\x00' + packet[offset+6:]
            packet = packet[:4] + struct.pack('!I', len(packet)-8) + packet[8:]
        elif mode == 'decimal':
            packet = packet[:-1] + b'\x0a'
        return packet

    def check_failure_cleanup(self, mode, message):
        """保留实际异常并核成功建成的临时模型已释放，读取器已关闭。"""
        packet = self.damaged_packet(mode)
        readers, references = [], []
        original_reader = codec._Reader
        original_factory = DecodedCANRecord._from_bound_values
        class ObservedReader(original_reader):
            """只记录拥有者，不修改数据或限额。"""
            def __init__(self, *args, **kwargs):
                """执行原读取器构造并登记其实际对象。"""
                super().__init__(*args, **kwargs)
                readers.append(self)
        def observed_record(cls, *args, **kwargs):
            """仍调用实际工厂，用弱引用观察未交付的成功记录。"""
            result = original_factory(*args, **kwargs)
            references.append(weakref.ref(result))
            return result
        error = None
        with patch.object(codec, '_Reader', ObservedReader), patch.object(DecodedCANRecord, '_from_bound_values', classmethod(observed_record)):
            try:
                codec.decode_block(packet)
            except ValueError as caught:
                error = caught
        self.assertIsNotNone(error)
        self.assertIn(message, str(error))
        gc.collect()
        self.assertTrue(all(reference() is None for reference in references))
        self.assertEqual(len(readers), 1)
        self.assertIsNone(readers[0].data)
        self.assertEqual(readers[0].strings, [])
        stack = error.__traceback__
        model_ids = set()
        while stack is not None:
            values = stack.tb_frame.f_locals
            model = values.get('self')
            if isinstance(model, DecodedCANRecord):
                model_ids.add(id(model))
            if stack.tb_frame.f_code.co_filename == codec.__file__:
                for name in ('raw', 'digits'):
                    if isinstance(values.get(name), memoryview):
                        with self.assertRaises(ValueError):
                            values[name].nbytes
            stack = stack.tb_next
        self.assertEqual(len(model_ids), 1 if mode == 'model' else 0)
        self.assertEqual(len(references), 7 if mode == 'model' else 0 if mode == 'integer' else 8)

    def test_tail_error_releases_all_completed_records(self):
        """尾部损坏后不让异常保留前八条已完成记录。"""
        self.check_failure_cleanup('trailing', '未消费')

    def test_model_error_keeps_only_failing_record_diagnostic(self):
        """模型错误的self保留原诊断，之前七条记录已释放。"""
        self.check_failure_cleanup('model', '未解码')

    def test_invalid_integer_releases_subview(self):
        """整数编码失败时，内层切片不再持有整个包。"""
        self.check_failure_cleanup('integer', '非最短')

    def test_invalid_decimal_releases_subview_and_records(self):
        """Decimal数字损坏时关闭内层视图并释放已完成模型。"""
        self.check_failure_cleanup('decimal', 'Decimal数字')


class CANFixedReadTests(unittest.TestCase):
    """固定宽度读取保留精确长度边界和失败游标，不改变字节序。"""

    def test_byte_reads_last_byte_then_reports_unchanged_end(self):
        """最后一字节正常读取，再读报原截断错且不越界推进。"""
        packet = codec.encode_block(0, [], True, facts())
        reader = codec._Reader(packet)
        try:
            reader.position = len(packet)-1
            self.assertEqual(reader.byte(), packet[-1])
            self.assertEqual(reader.position, len(packet))
            with self.assertRaisesRegex(codec.CANBlockError, '^CAN数据块截断$'):
                reader.byte()
            self.assertEqual(reader.position, len(packet))
        finally:
            reader.close()

    def test_uint_exact_four_bytes_and_each_short_boundary(self):
        """核四字节大端值，并逐一拒绝0至3字节余量且游标不变。"""
        packet = codec.encode_block(0, [], True, facts())
        for remaining in range(5):
            with self.subTest(remaining=remaining):
                reader = codec._Reader(packet)
                try:
                    position = len(packet)-remaining
                    reader.position = position
                    if remaining == 4:
                        self.assertEqual(reader.uint(), int.from_bytes(packet[-4:], 'big'))
                        self.assertEqual(reader.position, len(packet))
                    else:
                        with self.assertRaisesRegex(codec.CANBlockError, '^CAN数据块截断$'):
                            reader.uint()
                        self.assertEqual(reader.position, position)
                finally:
                    reader.close()


if __name__ == '__main__':
    unittest.main()
