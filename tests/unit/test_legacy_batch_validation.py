"""用原记录模型及真实JSON字节验证未保留报文的轻量校验边界。

合成输入覆盖全部原帧字段、Unicode/转义通道和信号名、非有限诊断、巨整数及64KiB。
长度期望直接来自原ITEM编码器和标准库JSON，不能用被测公式构造期望值。
测试只在内存建立消息替身，不导入CAN库、启动进程、读取旧快照或写入工作目录。
"""

from configuration_fixtures import current_fixture

from collections.abc import Mapping
import itertools
import json
import math
import random
import struct
import sys
from types import SimpleNamespace
import unittest

from chronaxis.legacy import records
from chronaxis.legacy.batch_validation import _item_base_size, validate_discarded
from chronaxis.legacy.worker import _frame


_BOOL_FIELDS = ('is_extended_id', 'is_remote_frame', 'is_error_frame', 'is_fd', 'is_rx',
                'bitrate_switch', 'error_state_indicator')


def message(**changes):
    """建立不含CAN库行为的原字段替身。参数: changes为覆盖字段。返回: 消息。异常: 分配错误。"""
    fields = dict(timestamp=1700000000.125, arbitration_id=428, is_extended_id=False,
                  is_remote_frame=False, is_error_frame=False, channel=0, dlc=8,
                  data=bytearray(range(8)), is_fd=False, is_rx=True,
                  bitrate_switch=False, error_state_indicator=False)
    fields.update(changes)
    return SimpleNamespace(**fields)


def original_record(msg, values, sequence):
    """执行原消息模型检查，作为独立行为基准。

    参数: msg/values/sequence与被测函数相同。返回: 原记录模型。异常: 原边界错误。
    """
    return records.LegacyDecodedFrame(sequence, _frame(msg), values)


def item_packet(msg, values, sequence):
    """按原公开模型生成真实ITEM包，长度参考不依赖被测公式。

    参数: msg/values/sequence为合法原消息。返回: 原JSON包dict。异常: 原模型错误。
    """
    record = original_record(msg, values, sequence)
    return {'op': 'item', 'request_id': sequence, 'record': records.decoded_to_dict(record)}


class CountedMapping(Mapping):
    """保存有限原值并记录items遍历次数，用于确认未保存数据只检查一遍。"""

    def __init__(self, values):
        """保存原值和计数。参数: values为有限dict。返回: 新对象。异常: 无。"""
        self.values, self.visits = values, 0

    def __getitem__(self, key):
        """保持Mapping取值。参数: key为信号名。返回: 原数值。异常: 原KeyError。"""
        return self.values[key]

    def __iter__(self):
        """保持原键顺序。参数: 无。返回: 原键迭代器。异常: 无。"""
        return iter(self.values)

    def __len__(self):
        """提供有限键数。参数: 无。返回: 原字典长度。异常: 无。"""
        return len(self.values)

    def items(self):
        """统计完整遍历次数。参数: 无。返回: 原items视图。异常: 无。"""
        self.visits += 1
        return self.values.items()


class TextSubclass(str):
    """无新增状态的字符串子类，验证名称必须保持原生str边界。"""


class LegacyBatchValidationTests(unittest.TestCase):
    """对照原模型的接受/拒绝和实际字节长度，不改变或代替公共模型。"""

    def assert_rejected_like_original(self, msg, values, sequence=0):
        """要求非法单项由原路径和辅助函数以同类异常拒绝。

        参数: msg/values/sequence为待拒绝输入。返回: None。异常: 断言或非预期错误。
        """
        with self.assertRaises((TypeError, ValueError, UnicodeError, OverflowError)) as expected:
            original_record(msg, values, sequence)
        with self.assertRaises(type(expected.exception)):
            validate_discarded(msg, values, sequence)

    def assert_exact_base(self, msg, sequence):
        """将空ITEM计长公式与两个实际编码路径逐项对照。

        参数: msg为合法原字段；sequence为原序号。返回: None。异常: 大小/输出断言失败。
        """
        packet = item_packet(msg, {}, sequence)
        expected = json.dumps(current_fixture(packet), ensure_ascii=False, allow_nan=False, sort_keys=True,
                              separators=(',', ':')).encode('utf-8')
        self.assertEqual(records.encode_packet(packet), expected)
        self.assertEqual(_item_base_size(_frame(msg), sequence), len(expected))
        self.assertIsNone(validate_discarded(msg, {}, sequence))

    def test_exact_empty_item_bytes_cover_all_boolean_combinations(self):
        """七个原bool的128种组合全部按true/false真实长度计算。

        参数: 无。返回: None。异常: 某个bool字段漏算或按0/1编码令断言失败。
        """
        for flags in itertools.product((False, True), repeat=7):
            with self.subTest(flags=flags):
                self.assert_exact_base(message(**dict(zip(_BOOL_FIELDS, flags))), 1024)

    def test_exact_empty_item_bytes_cover_raw_fields_and_float_formats(self):
        """原时间浮点位模式、序号、ID/DLC/载荷与通道均与真实ITEM字节一致。

        参数: 无。返回: None。异常: 指数、负零、多字节、控制字符或固定字段漏计。
        """
        channels = (None, 0, -123, 2**2048, '', '通道😀', '电\n"\\\x00', '\x7f')
        times = [-0.0, 0.0, 1.0, -1e-7, 1e20, sys.float_info.max,
                 sys.float_info.min, math.nextafter(0.0, 1.0)]
        generator = random.Random(611)
        for _ in range(128):
            value = struct.unpack('>d', generator.getrandbits(64).to_bytes(8, 'big'))[0]
            if math.isfinite(value):
                times.append(value)
        for index, timestamp in enumerate(times):
            msg = message(timestamp=timestamp, channel=channels[index % len(channels)],
                          arbitration_id=(0, 0x1fffffff)[index % 2], dlc=index % 65,
                          data=bytes(range(index % 65)))
            with self.subTest(time=timestamp.hex(), case=index):
                self.assert_exact_base(msg, (0, 1, 10**100, 2**2048)[index % 4])

    def test_complete_values_keep_zero_false_diagnostics_and_unicode(self):
        """完整原值包含0、False和非有限诊断时仍逐项接受，不按truthiness省略。

        参数: 无。返回: None。异常: 合法值被拒、输入被改或字节边界失真。
        """
        values = {'zero': 0, 'false': False, 'true': True, 'negative_zero': -0.0,
                  'nan': float('nan'), 'inf': float('inf'), '-inf': -float('inf'),
                  '电压\n"\\\x00😀': 2**2048, 'e\u0301': -2**2048}
        msg = message(channel='通道\n"\\😀')
        before = dict(values)
        encoded = records.encode_packet(item_packet(msg, values, 99))
        self.assertLess(len(encoded), records.MAX_WIRE_BYTES)
        self.assertIsNone(validate_discarded(msg, values, 99))
        self.assertEqual(tuple(values), tuple(before))
        self.assertIs(values['false'], False)
        self.assertTrue(math.isnan(values['nan']))

    def test_64kib_boundary_uses_actual_encoder_for_signal_and_channel_text(self):
        """真实编码长为65535/65536/65537时，与原模型的接受边界完全一致。

        参数: 无。返回: None。异常: ASCII、Unicode、转义文本少算或多算一个字节。
        """
        for channel in (False, True):
            for prefix in ('', '通道😀', '\n"\\\x00'):
                # 先编码短合法包，再添加ASCII补齐精确字节；期望不调用被测公式。
                msg = message(channel=prefix if channel else 0)
                values = {'x' if channel else prefix + 'x': 0}
                base = len(records.encode_packet(item_packet(msg, values, 7)))
                for delta in (-1, 0, 1):
                    padding = 'a' * (records.MAX_WIRE_BYTES - base + delta)
                    candidate = message(channel=prefix + padding) if channel else msg
                    actual_values = values if channel else {prefix + 'x' + padding: 0}
                    with self.subTest(channel=channel, prefix=repr(prefix), delta=delta):
                        if delta <= 0:
                            packet = item_packet(candidate, actual_values, 7)
                            self.assertEqual(len(records.encode_packet(packet)), records.MAX_WIRE_BYTES + delta)
                            self.assertIsNone(validate_discarded(candidate, actual_values, 7))
                        else:
                            self.assert_rejected_like_original(candidate, actual_values, 7)

    def test_invalid_mapping_names_values_and_depth_are_not_skipped(self):
        """未保留记录也拒绝非Mapping、非法名称、嵌套容器和非原生数值。

        参数: 无。返回: None。异常: 原模型应拒绝的值被辅助函数接受。
        """
        nested = 0
        for _ in range(18):
            nested = [nested]
        invalid = (None, [], (), {'': 1}, {1: 2}, {TextSubclass('x'): 0},
                   {'\ud800': 0}, {'x': None}, {'x': '1'}, {'x': b'1'},
                   {'x': object()}, {'x': nested}, {'x': {'diagnostic_float': 'nan'}},
                   {'x': 1 + 2j}, {'x': 1 << (records.MAX_WIRE_BYTES * 4)})
        for index, values in enumerate(invalid):
            with self.subTest(case=index):
                self.assert_rejected_like_original(message(), values)
        for sequence in (-1, False, 0.0, '0', 1 << (records.MAX_WIRE_BYTES * 4)):
            with self.subTest(sequence_type=type(sequence).__name__):
                self.assert_rejected_like_original(message(), {}, sequence)

    def test_invalid_raw_fields_match_original_frame_checks(self):
        """即使ID未被选择，时间、ID、DLC、载荷、通道和全部标志仍执行原检查。

        参数: 无。返回: None。异常: 非法原字段被静默跳过或改变异常类型。
        """
        changes = ({'timestamp': 1}, {'timestamp': float('nan')}, {'timestamp': float('inf')},
                   {'arbitration_id': False}, {'arbitration_id': -1}, {'arbitration_id': 0x20000000},
                   {'dlc': True}, {'dlc': -1}, {'dlc': 65}, {'data': bytes(65)},
                   {'channel': False}, {'channel': []}, {'channel': '\ud800'},
                   {'channel': 'a' * (records.MAX_WIRE_BYTES + 1)},
                   {'channel': 1 << (records.MAX_WIRE_BYTES * 4)})
        for change in (*changes, *({name: 0} for name in _BOOL_FIELDS)):
            with self.subTest(field=tuple(change)):
                self.assert_rejected_like_original(message(**change), {})

    def test_discarded_mapping_checked_once_without_copy_or_retained_state(self):
        """没有待保存副本时只遍历一次原Mapping，公共模型仍维持原两遍保证。

        参数: 无。返回: None。异常: 辅助函数再次遍历、改写或保存完整解码模型。
        """
        values = CountedMapping({'x': 0, '电压': float('nan')})
        self.assertIsNone(validate_discarded(message(), values, 0))
        self.assertEqual(values.visits, 1)
        original_record(message(), values, 0)
        self.assertEqual(values.visits, 3)


if __name__ == '__main__':
    unittest.main()
