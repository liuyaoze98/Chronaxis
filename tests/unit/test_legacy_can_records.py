"""独立核对旧CAN原帧记录的无损模型、严格JSON和复制前64KiB边界。

输入完全为显式合成的公开帧字段、数值映射及路径声明，不依赖CAN extra，不读
BLF/DBC、不启动进程。原始64字节payload及全部布尔标志必须无损；解码bool、0、
大整数和有限浮点保原类型，非有限浮点仅通过固定diagnostic_float标签传输。
严格负例拒绝额外字段、重复JSON键、裸NaN、类型混淆和超长/过深输入。
CountingMapping只声明大规模而不实际建立大字典，核容量检查发生在items/复制之前；
长度谎报及两遍间变化也必须在有限前缀内停止。测试不修改旧源码、已冻结进程专项
或任何输入文件，device_label: home。异常均由原模型/helper报告，不宽化生产契约。
"""

from configuration_fixtures import current_fixture

from collections.abc import Mapping
from dataclasses import FrozenInstanceError, replace
import json
import math
from pathlib import Path
import unittest
from unittest.mock import patch

from chronaxis.legacy import records as module


class CountingMapping(Mapping):
    """以惰性items计数早拒及动态前缀，不先分配其声称的巨大数据。"""

    def __init__(self, reported_length, pass_counts, key_width=1024):
        """保存有限计数参数。参数: 声称长度/各遍惰性条数/键宽。返回: 新Mapping。异常: 无。"""
        self.reported_length, self.pass_counts, self.key_width = reported_length, pass_counts, key_width
        self.length_calls = self.items_calls = self.iter_calls = self.getitem_calls = 0
        self.visited = []

    def __len__(self):
        """只返回声明长度。参数: 无。返回: int。异常: 无，不生成任何条目。"""
        self.length_calls += 1
        return self.reported_length

    def __iter__(self):
        """拒绝隐藏的通用复制路径。参数: 无。返回: 无。异常: AssertionError证明先遍历。"""
        self.iter_calls += 1
        raise AssertionError('不应通过通用Mapping迭代复制巨大输入')

    def __getitem__(self, key):
        """拒绝隐藏逐键复制。参数: key。返回: 无。异常: AssertionError证明过早复制。"""
        self.getitem_calls += 1
        raise AssertionError('不应逐键复制巨大输入')

    def items(self):
        """惰性提供当前一遍并计实际访问前缀。参数: 无。返回: 键值迭代器。异常: 无。"""
        index = min(self.items_calls, len(self.pass_counts) - 1)
        count = self.pass_counts[index]
        self.items_calls += 1
        self.visited.append(0)
        for sequence in range(count):
            self.visited[-1] += 1
            yield 'x' * self.key_width + str(sequence), 0


class LegacyCANRecordsTests(unittest.TestCase):
    """四个独立纯记录验收，覆盖无损、拒绝、复制上界与无IO声明。"""

    def raw_frame(self):
        """提供全部标志为真的64字节公开快照。参数: 无。返回: LegacyRawFrame。异常: 原构造错误。"""
        return module.LegacyRawFrame(1700000000.125, 0x1ABCDE, True, True, True,
            'CAN0', 64, bytes(range(64)), True, True, True, True)

    def test_complete_raw_and_decoded_roundtrip_preserves_types_and_freezing(self):
        """完整raw、空payload及typed诊断值往返，不把False/0/非有限值变成替代值。

        参数: 无。返回: None。异常: 原helper或无损/不可变断言失败。
        """
        raw = self.raw_frame()
        empty = replace(raw, timestamp=0.0, arbitration_id=0, is_extended_id=False,
            is_remote_frame=False, is_error_frame=False, channel=None, dlc=0, data=b'',
            is_fd=False, is_rx=False, bitrate_switch=False, error_state_indicator=False)
        for frame in (raw, empty):
            with self.subTest(payload_length=len(frame.data)):
                encoded = module.frame_to_dict(frame)
                decoded = module.frame_from_dict(module.decode_packet(module.encode_packet(encoded)))
                self.assertEqual(decoded, frame, '所有公开raw字段必须完整相等')
                self.assertEqual(encoded['data_hex'], frame.data.hex())
                self.assertIs(type(decoded.data), bytes)
        self.assertEqual(len(raw.data), 64)
        with self.assertRaises(FrozenInstanceError):
            raw.dlc = 0
        values = {'false': False, 'zero': 0, 'precise': 2 ** 53 + 1, 'uint': 2 ** 64 - 1,
            'finite': 1.25, 'negative_zero': -0.0, 'nan': float('nan'),
            'positive_inf': float('inf'), 'negative_inf': float('-inf')}
        record = module.LegacyDecodedFrame(7, raw, values)
        values['finite'] = 9.0
        self.assertEqual(record.values['finite'], 1.25, '冻结模型必须复制原有限映射')
        wire = module.decoded_to_dict(record)
        self.assertEqual(wire['values']['nan'], {'diagnostic_float': 'nan'})
        self.assertEqual(wire['values']['positive_inf'], {'diagnostic_float': 'inf'})
        self.assertEqual(wire['values']['negative_inf'], {'diagnostic_float': '-inf'})
        payload = module.encode_packet({'op': 'item', 'request_id': 7, 'record': wire})
        self.assertNotIn(b'NaN', payload)
        self.assertNotIn(b'Infinity', payload)
        rebuilt = module.decoded_from_dict(module.decode_packet(payload)['record'])
        self.assertEqual((rebuilt.sequence, rebuilt.frame), (7, raw))
        for name, expected, kind in (('false', False, bool), ('zero', 0, int),
                ('precise', 2 ** 53 + 1, int), ('uint', 2 ** 64 - 1, int), ('finite', 1.25, float)):
            with self.subTest(name=name):
                self.assertIs(type(rebuilt.values[name]), kind)
                self.assertEqual(rebuilt.values[name], expected)
        self.assertTrue(math.isnan(rebuilt.values['nan']))
        self.assertEqual(rebuilt.values['positive_inf'], float('inf'))
        self.assertEqual(rebuilt.values['negative_inf'], float('-inf'))
        self.assertEqual(math.copysign(1, rebuilt.values['negative_zero']), -1)
        with self.assertRaises(TypeError):
            rebuilt.values['zero'] = 1
        with self.assertRaises(FrozenInstanceError):
            rebuilt.sequence = 8

    def test_strict_json_model_shapes_types_and_exact_wire_boundary(self):
        """拒重复键/裸NaN/额外字段/bool定位/深包，恰64KiB通过而再多一字节拒绝。

        参数: 无。返回: None。异常: 原模型错误或严格边界断言失败。
        """
        for payload in (b'{"x":0,"x":1}', b'{"x":{"a":0,"a":1}}',
                b'{"x":NaN}', b'{"x":Infinity}', b'{"x":-Infinity}'):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    module.decode_packet(payload)
        field = module.LegacyCANField(0, 'Sample', 0x100, False, False)
        for changed in ({'channel': False}, {'is_extended': 0}, {'is_fd': 1}, {'frame_id': True}):
            with self.subTest(changed=changed):
                locator = module.field_to_dict(field)
                locator.update(changed)
                with self.assertRaises(TypeError):
                    module.field_from_dict(locator)
        with self.assertRaises(ValueError):
            module.frame_from_dict({**module.frame_to_dict(self.raw_frame()), 'extra': 0})
        body = module.decoded_to_dict(module.LegacyDecodedFrame(0, self.raw_frame(), {'x': 0}))
        with self.assertRaises(ValueError):
            module.decoded_from_dict({**body, 'extra': 0})
        body['values']['x'] = {'diagnostic_float': 'nan', 'extra': 0}
        with self.assertRaises(ValueError):
            module.decoded_from_dict(body)
        with self.assertRaises(TypeError):
            module.LegacyDecodedFrame(True, self.raw_frame(), {})
        with self.assertRaises(ValueError):
            replace(self.raw_frame(), data=bytes(65))
        with self.assertRaises(ValueError):
            replace(self.raw_frame(), timestamp=float('nan'))
        maximum = module.encode_packet({'x': 'a' * (module.MAX_WIRE_BYTES - 8)})
        self.assertEqual(len(maximum), module.MAX_WIRE_BYTES)
        self.assertEqual(len(module.decode_packet(maximum)['x']), module.MAX_WIRE_BYTES - 8)
        with self.assertRaises(ValueError):
            module.encode_packet({'x': 'a' * (module.MAX_WIRE_BYTES - 7)})
        with self.assertRaises(ValueError):
            module.decode_packet(b' ' * (module.MAX_WIRE_BYTES + 1))
        nested = 0
        for _ in range(18):
            nested = [nested]
        with self.assertRaises(ValueError):
            module.encode_packet({'x': nested})
        with self.assertRaises(ValueError):
            module.decode_packet(json.dumps(current_fixture({'x': nested})).encode('utf-8'))
        with self.assertRaises(TypeError):
            module.encode_packet({'x': object()})

    def test_size_preflight_rejects_before_copy_and_bounds_changing_mapping(self):
        """大声明零遍历即拒，谎报长度或二遍扩大也只访问有界前缀。

        参数: 无。返回: None。异常: 原容量错误之外的遍历/复制或上界断言失败。
        """
        enormous = CountingMapping(module.MAX_WIRE_BYTES, (1_000_000,))
        with self.assertRaises(ValueError):
            module.LegacyDecodedFrame(0, self.raw_frame(), enormous)
        self.assertGreater(enormous.length_calls, 0)
        self.assertEqual((enormous.items_calls, enormous.iter_calls, enormous.getitem_calls), (0, 0, 0),
            '必须在进入items或复制以前因声明规模拒绝')
        for passes, expected_passes in (((1_000_000,), 1), ((1, 1_000_000), 2)):
            with self.subTest(passes=passes):
                changing = CountingMapping(1, passes)
                with self.assertRaises(ValueError):
                    module.LegacyDecodedFrame(0, self.raw_frame(), changing)
                self.assertEqual(changing.items_calls, expected_passes)
                self.assertLessEqual(changing.visited[-1], module.MAX_WIRE_BYTES // 1024 + 1,
                    '每个键至少1024字节，不能遍历完整巨大映射后才拒绝')
                self.assertEqual((changing.iter_calls, changing.getitem_calls), (0, 0))
        oversized = {'sequence': 0, 'frame': module.frame_to_dict(self.raw_frame()),
            'values': {'x' * module.MAX_WIRE_BYTES: 0}}
        with patch.object(module, '_value_from_wire', side_effect=AssertionError('不应先转换复制values')):
            with self.assertRaises(ValueError):
                module.decoded_from_dict(oversized)

    def test_request_and_locator_are_static_and_keep_original_names(self):
        """构造仅保原路径/定位，原DBC名称不是DSL变量，不探测文件或改写名称。

        参数: 无。返回: None。异常: 原声明错误或静态/冻结/原名称断言失败。
        """
        input_path, dbc_path = Path('unopened/input.blf'), Path('unopened/source.dbc')
        field = module.LegacyCANField(0, 'Signal.with space/原值', 0x100, False, False)
        fields = (field,)
        with patch('builtins.open', side_effect=AssertionError('请求构造不准IO')), \
                patch.object(Path, 'open', side_effect=AssertionError('请求构造不准Path.open')), \
                patch.object(Path, 'stat', side_effect=AssertionError('请求构造不准stat')), \
                patch.object(Path, 'resolve', side_effect=AssertionError('请求构造不准resolve')):
            request = module.LegacyCANRequest(input_path, dbc_path, fields)
            self.assertIs(request.input_path, input_path)
            self.assertIs(request.dbc_path, dbc_path)
            self.assertIs(request.fields, fields)
            self.assertEqual(request.profile, module.PROFILE_ID)
            locator = module.field_to_dict(field)
            self.assertEqual(module.field_from_dict(locator), field)
            self.assertEqual(json.loads(field.key), locator)
            self.assertEqual(field.signal, 'Signal.with space/原值')
            with self.assertRaises(ValueError):
                module.LegacyCANRequest(input_path, dbc_path, (field, field))
            with self.assertRaises(TypeError):
                module.LegacyCANRequest(input_path, dbc_path, [field])
        with self.assertRaises(FrozenInstanceError):
            request.input_path = Path('other.blf')
