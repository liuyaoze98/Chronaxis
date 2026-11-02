"""核对简化CAN绑定的配置合同，不读取日志或DBC。

输入为手写ID、可选帧类型和YAML文本；预期整数由字面值独立给出。
同时检查旧message拒绝及实际来源引用与可选选择器的关系；无持久文件副作用。
"""

import unittest
from chronaxis.legacy.records import LegacyCANField, field_from_dict, field_to_dict, normalize_frame_id, PROFILE_ID
from chronaxis.configuration.yaml_parser import parse_yaml
from chronaxis.configuration.models import ConfigurationError
from chronaxis.sources.can_spec import CANSourceRef
from chronaxis.planning.models import LegacyMessageSelector


class CANBindingContractTests(unittest.TestCase):
    """覆盖ID规范、可选类型和删除字段，避免用同一转换函数生成测试真值。"""

    def test_integer_formats(self):
        """不同文本写法统一成整数。参数: 无。返回: None。异常: 不一致时断言失败。"""
        for raw, expected in ((256, 256), ('256', 256), ('0x100', 256), ('0X100', 256),
                              ('0b100000000', 256), ('0B100000000', 256), ('010', 10), ('0', 0)):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_frame_id(raw), expected)
                self.assertEqual(LegacyCANField(0, 'Voltage', raw).frame_id, expected)
                self.assertEqual(LegacyMessageSelector(0, raw).frame_id, expected)

    def test_invalid_id_formats(self):
        """拒绝猜测、空值及越界。参数: 无。返回: None。异常: 非法输入被接受时断言失败。"""
        for raw in (True, False, 1.0, -1, 0x20000000, '', ' 256', '+256', '0o10', '1_000', '0x', '0b2'):
            with self.subTest(raw=raw), self.assertRaises((TypeError, ValueError)):
                normalize_frame_id(raw)

    def test_optional_flags_and_removed_message(self):
        """省略、false和null有不同含义。参数: 无。返回: None。异常: 合同不符时断言失败。"""
        raw = dict(channel=0, frame_id='0x100', signal='Voltage')
        field = field_from_dict(raw)
        self.assertIsNone(field.is_extended)
        self.assertIsNone(field.is_fd)
        self.assertEqual(field_to_dict(field), dict(channel=0, frame_id=256, signal='Voltage'))
        self.assertIs(field_from_dict(dict(raw, is_fd=False)).is_fd, False)
        for flag in ('is_extended', 'is_fd'):
            for value in (None, 0, 'false'):
                with self.subTest(flag=flag, value=value), self.assertRaises(TypeError):
                    field_from_dict(dict(raw, **{flag: value}))
        with self.assertRaisesRegex(ValueError, 'message参数已删除'):
            field_from_dict(dict(raw, message='Pack'))

    def test_yaml_id_lexical_contract(self):
        """YAML原生数字不能绕过三种进制约定。参数: 无。返回: None。异常: 解释错误时断言失败。"""
        for token, expected in (('0x100', 256), ('0b100000000', 256), ('010', 10)):
            parsed, _ = parse_yaml('field:\n  frame_id: ' + token, 'inline.yaml')
            self.assertEqual(parsed['field']['frame_id'], expected)
        for token in ('0o10', '1_000', '+256'):
            with self.subTest(token=token), self.assertRaises(ConfigurationError):
                parse_yaml('field:\n  frame_id: ' + token, 'inline.yaml')

    def test_source_ref_records_actual_flags(self):
        """省略类型的选择器仍可记录实际扩展帧。参数: 无。返回: None。异常: 约束被忽略时断言失败。"""
        field = LegacyCANField(0, 'Voltage', 256)
        ref = CANSourceRef('session', 'bus', field.key, 'synthetic.blf', PROFILE_ID,
                           0, 'Voltage', 256, True, False, 0, 0.0, False)
        self.assertIs(ref.is_extended, True)
        restricted = LegacyCANField(0, 'Voltage', 256, False)
        with self.assertRaisesRegex(ValueError, '实际帧与绑定'):
            CANSourceRef('session', 'bus', restricted.key, 'synthetic.blf', PROFILE_ID,
                         0, 'Voltage', 256, True, False, 0, 0.0, False)
