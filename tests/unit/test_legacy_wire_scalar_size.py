"""用标准库JSON真实字节校核wire尺寸快捷路径和原拒绝边界。

输入覆盖ASCII全部字符、Unicode/转义、原生标量、非有限数值及64KiB包边界；
输出只在内存生成，不启动CAN读取、不访问DBC或历史快照。期望值独立来自
标准库json.dumps后严格UTF-8编码，不调用被测尺寸函数作为参考。
"""

from configuration_fixtures import current_fixture
import json
import math
import random
import struct
import sys
import unittest
from unittest.mock import patch

from chronaxis.legacy import records


class _WireTextSubclass(str):
    """无新增状态的str子类，用于证明协议只接原生键，不隐式转换子类。"""


class WireScalarSizeTests(unittest.TestCase):
    """验证快捷计数的精确字节与拒绝条件，不能用更松的大小限制换取速度。"""

    def assert_scalar_bytes(self, value):
        """以标准库实际JSON字节校核相等及少一字节边界。

        参数: value为合法原生标量。返回: None。
        异常: 被测尺寸不符、超限未拒或合法边界被拒令断言失败。
        """
        expected = len(json.dumps(current_fixture(value), ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8'))
        self.assertEqual(records._scalar_size(value, expected), expected)
        self.assertEqual(records._scalar_size(value, expected + 1), expected)
        with self.assertRaises(ValueError):
            records._scalar_size(value, expected - 1)

    def test_every_ascii_character_and_printable_combinations_match_json(self):
        """控制字符、DEL、引号/反斜杠与普通文本都保持精确字节数。

        参数: 无。返回: None。异常: 某ASCII字符漏算转义或错误走快捷计数令断言失败。
        """
        for value in ('', 'PULL', 'BMS_BatPackActVol', ' C:/data/report.json ',
                      ''.join(chr(index) for index in range(128))):
            with self.subTest(value=repr(value)):
                self.assert_scalar_bytes(value)
        for code in range(128):
            with self.subTest(ascii=code):
                self.assert_scalar_bytes(chr(code))
                self.assert_scalar_bytes(chr(code) * 3)

    def test_unicode_and_escape_mixtures_preserve_strict_utf8_and_json_quoting(self):
        """多字节、补充平面、组合字符及转义混合使用原JSON/UTF-8规则。

        参数: 无。返回: None。异常: 多字节漏计、控制字符少转义或孤代理被接受令断言失败。
        """
        values = ('中文信号', 'é', '\u007f\u0080\u07ff\u0800\ud7ff\ue000\uffff',
                  '\U00010000\U0010ffff', 'e\u0301', '电压\n"\\\x00\t😀')
        for value in values:
            with self.subTest(value=repr(value)):
                self.assert_scalar_bytes(value)
        for value in ('\ud800', '\udfff', 'a\ud800b', '\ud800\udc00'):
            with self.subTest(surrogate=repr(value)):
                with self.assertRaises(UnicodeEncodeError):
                    json.dumps(current_fixture(value), ensure_ascii=False).encode('utf-8')
                with self.assertRaises(UnicodeEncodeError):
                    records._scalar_size(value, records.MAX_WIRE_BYTES)

    def test_null_booleans_and_signed_large_integers_match_json(self):
        """None/bool按null/true/false计数，整数保负号与完整十进制表示。

        参数: 无。返回: None。异常: bool当作1/0、截短整数或超大整数边界改变令断言失败。
        """
        for value in (None, True, False, 0, 1, -1, 2**63-1, -(2**63), 2**64-1,
                      10**100, -(10**100), 2**2048):
            with self.subTest(value=repr(value)):
                self.assert_scalar_bytes(value)
        with self.assertRaisesRegex(ValueError, 'wire整数超过单包能力'):
            records._scalar_size(1 << (records.MAX_WIRE_BYTES * 4), records.MAX_WIRE_BYTES)

    def test_finite_float_values_keep_original_json_format(self):
        """负零、指数、极值与固定种子位模式继续服从JSON编码器的数值表示。

        参数: 无。返回: None。异常: 浮点长度改变、溢出值或边界少算令断言失败。
        """
        values = [-0.0, 0.0, 1.0, -1.25, 1e-7, 1e20, sys.float_info.min,
                  sys.float_info.max, math.nextafter(0.0, 1.0)]
        generator = random.Random(191)
        for _ in range(256):
            value = struct.unpack('>d', generator.getrandbits(64).to_bytes(8, 'big'))[0]
            if math.isfinite(value):
                values.append(value)
        for value in values:
            with self.subTest(value=value):
                self.assert_scalar_bytes(value)

    def test_nonfinite_and_unsupported_types_are_still_rejected(self):
        """快捷路径不能接非有限原值或把bytes/容器/任意对象当作原生标量。

        参数: 无。返回: None。异常: 非法类型被隐式转换或非有限值当普通JSON令断言失败。
        """
        for value in (float('nan'), float('inf'), -float('inf')):
            with self.subTest(nonfinite=repr(value)):
                with self.assertRaisesRegex(ValueError, '非有限数值'):
                    records._scalar_size(value, records.MAX_WIRE_BYTES)
        for value in (b'x', [], {}, object(), 1+2j):
            with self.subTest(unsupported=type(value).__name__):
                with self.assertRaises(TypeError):
                    records._scalar_size(value, records.MAX_WIRE_BYTES)

    def test_ascii_unicode_and_escape_packets_keep_exact_64kib_boundary(self):
        """ASCII、多字节和需转义文本都以实际UTF-8包长判断，深度限制也不放宽。

        参数: 无。返回: None。异常: 64KiB边界误判、数据改变或深度越界被接受令断言失败。
        """
        # 外壳{"x":""}占8字节；不同字符编码成本分别为1、2、2、6字节。
        for character, width in (('a', 1), ('é', 2), ('\\', 2), ('\x00', 6)):
            count = (records.MAX_WIRE_BYTES - 8) // width
            body = {'x': character * count}
            expected = json.dumps(current_fixture(body), ensure_ascii=False, allow_nan=False, sort_keys=True,
                                  separators=(',', ':')).encode('utf-8')
            self.assertEqual(records.encode_packet(body), expected)
            self.assertEqual(records.decode_packet(expected), body)
            self.assertEqual(records._wire_tree(body), len(expected))
            with self.assertRaises(ValueError):
                records.encode_packet({'x': character * (count + 1)})
        nested = 0
        for _ in range(18):
            nested = [nested]
        with self.assertRaises(ValueError):
            records.encode_packet({'x': nested})

    def test_common_protocol_packet_needs_no_per_scalar_json_encoder(self):
        """普通控制包的尺寸预检不逐标量编码，最终包字节仍是原规范格式。

        参数: 无。返回: None。异常: 尺寸预检再次建立标量编码器或输出字节改变令断言失败。
        """
        packet = {'sequence': 0, 'type': 'PULL', 'eof': False, 'optional': None}
        # 只约束尺寸预检；整包编码仍正常使用标准库JSON。
        with patch.object(records.json, 'dumps', side_effect=AssertionError('普通标量不应重复JSON编码')):
            size = records._wire_tree(packet)
        actual = records.encode_packet(packet)
        self.assertEqual(size, len(actual))
        self.assertEqual(actual, b'{"eof":false,"optional":null,"sequence":0,"type":"PULL"}')

    def test_whole_packets_match_original_piecewise_encoder_bytes(self):
        """有限浮点与混合文本整包逐字节等于旧的标准库分片编码结果。

        参数: 无。返回: None。异常: 键排序、负零、指数或转义字节变化令断言失败。
        参考保留原JSONEncoder.iterencode路径，固定种子生成1024种IEEE位模式，
        同时覆盖最大/最小正规数及次正规数；不调用被测长度函数生成期望字节。
        """
        values = [-0.0, 0.0, 1.0, -1e-7, 1e20, sys.float_info.min,
                  sys.float_info.max, math.nextafter(0.0, 1.0)]
        generator = random.Random(603)
        for _ in range(1024):
            value = struct.unpack('>d', generator.getrandbits(64).to_bytes(8, 'big'))[0]
            if math.isfinite(value):
                values.append(value)
        encoder = json.JSONEncoder(ensure_ascii=False, allow_nan=False, sort_keys=True,
                                   separators=(',', ':'))
        for index, value in enumerate(values):
            packet = {'z': [value, None, True, False, -18446744073709551616],
                      '中文': {'转义': '\n"\\\x00😀', 'value': value}, 'a': index}
            expected = b''.join(piece.encode('utf-8') for piece in encoder.iterencode(packet))
            with self.subTest(float_hex=value.hex()):
                self.assertEqual(records.encode_packet(packet), expected)
                decoded = records.decode_packet(expected)
                self.assertEqual(decoded['z'][0].hex(), value.hex())

    def test_single_encoding_keeps_strict_tree_rejections(self):
        """整包改用一次编码后仍先执行原类型、非有限值与UTF-8校验。

        参数: 无。返回: None。异常: 标准库会接受的非协议结构绕过预检令断言失败。
        非字符串键、元组和非有限数值不能因标准库支持转换而被悄悄接受。
        """
        for packet in ([], None, {'x': (1, 2)}, {1: 'x'}, {'x': b'abc'}):
            with self.subTest(packet=repr(packet)):
                with self.assertRaises(TypeError):
                    records.encode_packet(packet)
        for value in (float('nan'), float('inf'), -float('inf')):
            with self.subTest(nonfinite=repr(value)):
                with self.assertRaisesRegex(ValueError, 'wire非有限数值必须显式标签'):
                    records.encode_packet({'x': value})
        with self.assertRaises(UnicodeEncodeError):
            records.encode_packet({'x': '\ud800'})

    def test_dictionary_keys_keep_depth_and_validation_order(self):
        """原生键仍计入递归深度，类型及深度拒绝继续早于文本UTF-8编码。

        参数: 无。返回: None。异常: 第17层键被接受或错误检查次序改变令断言失败。
        空容器在16层可用；非空字典的键和值要再进入一层，不能省掉这一层的限制。
        """
        self.assertEqual(records._wire_tree({}, depth=16, remaining=2), 2)
        self.assertEqual(records._wire_tree({'x': 0}, depth=15), 7)
        for value, depth in (({}, 17), ({'x': 0}, 16), ({'\ud800': 0}, 16)):
            with self.subTest(value=repr(value), depth=depth):
                with self.assertRaisesRegex(ValueError, '^wire嵌套或累计大小超过上限$'):
                    records._wire_tree(value, depth=depth)
        # 非原生键先被类型检查拒绝；不能因它同时处于深度边界而改抛ValueError。
        for name in (1, ('x',), b'x', _WireTextSubclass('x')):
            with self.subTest(key_type=type(name).__name__):
                with self.assertRaisesRegex(TypeError, '^wire字典键需要str$'):
                    records._wire_tree({name: 0}, depth=16)
        with self.assertRaises(UnicodeEncodeError):
            records._wire_tree({'\ud800': 0}, depth=15)

    def test_dictionary_keys_keep_remaining_byte_error_priority(self):
        """区别根预算、键空间、冒号后的负余额以及第二个键的分隔符越界。

        参数: 无。返回: None。异常: 预算拒绝类别/消息变化或容许少一字节令断言失败。
        {'x':0}恰好7字节；5字节时冒号已使值的剩余额度为负，6字节时值本身超限。
        """
        cases = (({'x': 0}, -1, 'wire嵌套或累计大小超过上限'),
                 ({'x': 0}, 0, 'wire容器超过单包上限'),
                 ({'x': 0}, 2, 'wire文本超过单包上限'),
                 ({'x': 0}, 5, 'wire嵌套或累计大小超过上限'),
                 ({'x': 0}, 6, 'wire包超过65536字节'),
                 ({'x': 0, 'y': 0}, 7, 'wire嵌套或累计大小超过上限'))
        for value, remaining, message in cases:
            with self.subTest(value=value, remaining=remaining):
                with self.assertRaisesRegex(ValueError, '^' + message + '$'):
                    records._wire_tree(value, remaining=remaining)
        self.assertEqual(records._wire_tree({'x': 0}, remaining=7), 7)
        # 第二键类型非法时，仍先报类型错误，而不是逗号使剩余预算变负的错误。
        with self.assertRaisesRegex(TypeError, '^wire字典键需要str$'):
            records._wire_tree({'x': 0, 1: None}, remaining=7)

    def test_unicode_and_escaped_keys_keep_exact_packet_limit(self):
        """把64KiB边界放在键上，验证新路径保留引号、转义和UTF-8的真实字节数。

        参数: 无。返回: None。异常: 键字节少算、边界误拒或多一字节未拒令断言失败。
        单键null对象除键内容外占9字节，用ASCII补齐余数使每种输入都精确达到65536字节。
        """
        for character, width in (('a', 1), ('é', 2), ('\\', 2), ('\x00', 6)):
            count, padding = divmod(records.MAX_WIRE_BYTES - 9, width)
            key = character * count + 'a' * padding
            packet = {key: None}
            expected = json.dumps(current_fixture(packet), ensure_ascii=False, allow_nan=False,
                                  sort_keys=True, separators=(',', ':')).encode('utf-8')
            with self.subTest(character=repr(character)):
                self.assertEqual(len(expected), records.MAX_WIRE_BYTES)
                self.assertEqual(records._wire_tree(packet), len(expected))
                self.assertEqual(records.encode_packet(packet), expected)
                with self.assertRaises(ValueError):
                    records.encode_packet({key + 'a': None})


if __name__ == '__main__':
    unittest.main()
