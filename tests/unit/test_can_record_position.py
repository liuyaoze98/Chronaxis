"""核已解码记录重编号不重复解析字段，同时保留位置、结构和入站检查。"""
from dataclasses import FrozenInstanceError, replace
import unittest
from unittest.mock import patch

from chronaxis.execution import can_block_codec as codec
from chronaxis.execution.parallel_can_decode import _with_position
from chronaxis.sources import text_can_decode
import test_can_block_codec as fixtures


class CANRecordPositionTests(unittest.TestCase):
    """只把实际固定块解码成功的记录传给内部重编号入口。"""

    def decoded(self):
        """通过真实固定解码器得到已核记录，不伪造信任标志。"""
        item = fixtures.record()
        return codec.decode_block(codec.encode_block(0, [item], True, fixtures.facts()))[1][0]

    def test_reindex_preserves_fields_without_reparsing_keys(self):
        """只改两个编号，字段、原帧和重建事实共享原对象且数值完整。"""
        item = self.decoded()
        expected = replace(item, input_index=4, sequence=100)
        with patch.object(text_can_decode, 'can_field_from_key', side_effect=AssertionError('不得重新解析已核键')):
            result = _with_position(item, 4, 100)
        self.assertEqual(result, expected)
        for name in ('raw', 'values', 'frame_values', 'frame_layout'):
            self.assertIs(getattr(result, name), getattr(item, name))
        self.assertEqual((item.input_index, item.sequence), (0, 3))
        self.assertEqual((result.input_index, result.sequence), (4, 100))

    def test_new_positions_still_reject_wrong_type_and_negative_values(self):
        """负数、bool、float都不能成为新编号。"""
        item = self.decoded()
        for value in (-1, True, 1.0, None):
            for positions in ((value, 1), (0, value)):
                with self.subTest(positions=positions), self.assertRaises(ValueError):
                    _with_position(item, *positions)

    def test_values_are_immutable_and_public_constructor_still_checks_keys(self):
        """公共模型不能改写值，外部构造仍拒绝非规范字段键。"""
        item = self.decoded()
        with self.assertRaises(FrozenInstanceError):
            item.values = ()
        with self.assertRaises(TypeError):
            item.values[0] = ('changed', 1)
        with self.assertRaisesRegex(ValueError, '规范'):
            replace(item, values=((' '+item.values[0][0], 1),))

    def test_structural_corruption_is_not_accepted_by_reindex(self):
        """故障注入绕过冻结机制时，其余类型、状态、重复项检查仍有效。"""
        changes = dict(source='not a valid name', status='other', raw=None,
                       values='not_pairs', frame_layout=(('mux', True),))
        for name, value in changes.items():
            item = self.decoded()
            object.__setattr__(item, name, value)
            with self.subTest(name=name), self.assertRaises((TypeError, ValueError)):
                _with_position(item, 0, 1)
        item = self.decoded()
        object.__setattr__(item, 'values', item.values+item.values)
        with self.assertRaisesRegex(ValueError, '重复'):
            _with_position(item, 0, 1)

    def test_disk_packet_key_tamper_rejected_before_heap_delivery(self):
        """有无磁盘摘要都先完整核新块，不能用重编号绕过被篡改字段。"""
        item = self.decoded()
        object.__setattr__(item, 'values', ((' '+item.values[0][0], 1),))
        packet = codec.encode_block(0, [item], True, fixtures.facts())
        for integrity in (False, True):
            cursor = fixtures.CANDiskProtocolTests().cursor([packet], integrity=integrity)
            try:
                with self.subTest(integrity=integrity), self.assertRaisesRegex(ValueError, '规范'):
                    cursor._push(0)
                self.assertFalse(cursor._heap)
            finally:
                for handle in cursor._handles:
                    handle.close()


if __name__ == '__main__':
    unittest.main()
