"""独立检查CAN静态声明、规范原定位和冻结来源引用，不读取任何报文或DBC。

输入是明确Path/TimebaseSpec、B1六字段定位及手写原timestamp；输出为unittest
断言。通过禁止open/stat/resolve/动态加载证明模型只校验声明；类型、int64偏移、
严格JSON及附加定位冲突在读取前拒绝。原消息/信号名称、通道、浮点诊断和0起
yield位置保持，evaluation_index不被误认成legacy_sum求值流。无文件或进程副作用，
不依赖可选CAN库，不使用其他TestCase夹具，也不声称来源或真实日志已经验证。
"""

from configuration_fixtures import current_fixture

# 测试只用标准库和纯声明模型，不导入adapter、worker或可选CAN库。
from dataclasses import FrozenInstanceError, replace
import json
from math import copysign
from pathlib import Path, PurePath
import unittest
from unittest.mock import patch
from chronaxis.core.models import SourceRef, TimebaseSpec
from chronaxis.core.types import TimeType
from chronaxis.legacy.records import LegacyCANField, MAX_WIRE_BYTES, PROFILE_ID, field_to_dict
from chronaxis.sources.can_spec import CANSourceRef, LegacyCANSpec, can_field_from_key


class ForeignInteger(int):
    """模拟外部整数子类，验证原生int合同不会被isinstance偷偷放宽。"""


class ForeignText(str):
    """模拟文本子类，规范定位仍必须接原生str而非可重载比较的对象。"""


class CANSpecTests(unittest.TestCase):
    """每例独立构造静态声明，不建立工作目录或访问实际CAN输入。"""

    def spec(self, **changes):
        """建立可读的合法来源声明，覆盖项仅用于本例负例。

        参数: changes为显式字段差异。返回: LegacyCANSpec。
        异常: 被测静态校验原错误，不生成文件或默认工程标定值。
        """
        values = {'name': 'source_can', 'path': Path('unread/input.BLF'), 'dbc_path': Path('unread/input.dbc'),
            'channel': 0, 'timebase': TimebaseSpec('declared_clock', TimeType.RELATIVE, 'explicit origin')}
        values.update(changes)
        return LegacyCANSpec(**values)

    def locator(self):
        """给出含点号及中文原名的完整定位，不把它拼成DSL变量。

        参数: 无。返回: LegacyCANField。异常: 原B1定位模型错误。
        """
        return LegacyCANField(0, '电池.原始电压', 0x321, False, False)

    def reference(self, **changes):
        """为同一原定位建立完整引用，覆盖项可制造可追溯性冲突。

        参数: changes为本例字段差异。返回: CANSourceRef。异常: 被测引用校验原错误。
        """
        field = self.locator()
        values = {'session_id': 'session', 'source_name': 'source_can', 'field': field.key,
            'path': '原始输入/input.BLF', 'profile': PROFILE_ID, 'channel': field.channel,
             'signal': field.signal, 'frame_id': field.frame_id,
            'is_extended': field.is_extended, 'is_fd': field.is_fd, 'yield_sequence': 0,
            'timestamp': 1.234567890123, 'time_quantized': True}
        values.update(changes)
        return CANSourceRef(**values)

    def test_spec_and_reference_construction_have_no_io_or_dynamic_loading(self):
        """构造只保声明对象，禁止触碰文件、解析DBC或动态加载库。

        参数: 无。返回: None。异常: 任一I/O/动态加载或声明对象被替换时断言失败。
        """
        path, dbc = Path('never_created/drive.BLF'), Path('never_created/drive.dbc')
        clock = TimebaseSpec('manual_clock', TimeType.ABSOLUTE)
        # 最后才禁动态导入，避免mock自身的目标解析被误当产品加载。
        with patch('builtins.open', side_effect=AssertionError('构造打开了文件')) as builtin_open, \
                patch.object(Path, 'open', side_effect=AssertionError('构造Path.open')) as path_open, \
                patch.object(Path, 'stat', side_effect=AssertionError('构造查询文件')) as stat, \
                patch.object(Path, 'resolve', side_effect=AssertionError('构造解析真实路径')) as resolve, \
                patch('importlib.import_module', side_effect=AssertionError('构造动态加载库')) as dynamic:
            spec = self.spec(path=path, dbc_path=dbc, timebase=clock)
            ref = self.reference()
            field = can_field_from_key(ref.field)
        self.assertIs(spec.path, path)
        self.assertIs(spec.dbc_path, dbc)
        self.assertIs(spec.timebase, clock)
        self.assertEqual((spec.unit, spec.offset_ns, spec.legacy_profile), ('s', 0, PROFILE_ID))
        self.assertEqual(field, self.locator())
        for method in (builtin_open, path_open, stat, resolve, dynamic):
            method.assert_not_called()

    def test_spec_rejects_unsupported_scope_and_non_native_channel(self):
        """多文件替代、错误格式/时基/profile/单位和非原生通道都在读取前拒绝。

        参数: 无。返回: None。异常: 非法声明被静默改名、换profile或转换类型时断言失败。
        """
        changes = ({'name': 'battery.current'}, {'name': 'for'}, {'name': 'abs'}, {'name': ''},
            {'path': 'input.blf'}, {'path': PurePath('input.blf')}, {'path': (Path('a.blf'),)},
            {'path': Path('input.asc')}, {'path': Path('input.csv')}, {'path': Path('folder')},
            {'dbc_path': 'input.dbc'}, {'dbc_path': None}, {'timebase': 'clock'}, {'timebase': None},
            {'channel': True}, {'channel': 0.0}, {'channel': '0'}, {'channel': ForeignInteger(0)}, {'channel': -1},
            {'unit': 'ms'}, {'unit': 'ISO8601'}, {'unit': 's '}, {'unit': None},
            {'legacy_profile': 'filter-main-blf-v1'}, {'legacy_profile': ''}, {'legacy_profile': None})
        for change in changes:
            with self.subTest(change=change), self.assertRaises((TypeError, ValueError)):
                self.spec(**change)
        # 后缀只限定BLF，大小写不改变原Path；静态构造不认证它实际存在。
        self.assertEqual(str(self.spec(path=Path('input.blf')).path), str(Path('input.blf')))

    def test_offset_is_native_int64_and_source_is_frozen(self):
        """偏移精确保留有符号边界，bool/外部整数/溢出不靠隐式归一化修复。

        参数: 无。返回: None。异常: 偏移丢位、接受非法类型或冻结被破坏时断言失败。
        """
        for offset in (-(1 << 63), 0, (1 << 63) - 1):
            spec = self.spec(offset_ns=offset)
            self.assertEqual(spec.offset_ns, offset)
            self.assertIs(type(spec.offset_ns), int)
        for offset in (True, 0.0, '0', ForeignInteger(0)):
            with self.subTest(offset=offset), self.assertRaises(TypeError):
                self.spec(offset_ns=offset)
        for offset in (-(1 << 63) - 1, 1 << 63):
            with self.subTest(offset=offset), self.assertRaises(OverflowError):
                self.spec(offset_ns=offset)
        spec = self.spec()
        with self.assertRaises(FrozenInstanceError):
            spec.channel = 1

    def test_canonical_key_preserves_original_locator_names(self):
        """定位JSON只是原字段键，保全部名称和native类型，不成为表达式或语义目录。

        参数: 无。返回: None。异常: 原名被替换/裁剪、定位信息缺失或非规范文本被接受断言失败。
        """
        expected = self.locator()
        field = can_field_from_key(expected.key)
        self.assertEqual(field, expected)
        self.assertEqual(field.signal, '电池.原始电压')
        self.assertNotIn('message', field_to_dict(field))
        self.assertEqual(field.key, json.dumps(current_fixture(field_to_dict(expected)), ensure_ascii=False,
            sort_keys=True, separators=(',', ':')))
        alternatives = (' ' + expected.key, expected.key + '\n',
            json.dumps(current_fixture(field_to_dict(expected)), ensure_ascii=False),
            json.dumps(current_fixture(field_to_dict(expected)), ensure_ascii=True, sort_keys=True, separators=(',', ':')))
        for text in alternatives:
            with self.subTest(text=text), self.assertRaises(ValueError):
                can_field_from_key(text)

    def test_key_requires_exact_six_fields_and_strict_json_native_types(self):
        """重复/多余/缺失字段、bool冒充整数、非JSON或超限键不能成为有效定位。

        参数: 无。返回: None。异常: 任何非法key被接受时断言失败；不执行对象标签或eval。
        """
        base, key = field_to_dict(self.locator()), self.locator().key
        variants = []
        for name, value in (('channel', False), ('channel', 0.0), ('frame_id', True), ('frame_id', -1),
                ('is_extended', 0), ('is_fd', 1), ('message', None), ('signal', '')):
            variants.append({**base, name: value})
        variants.extend(({**base, 'unit': 'V'}, {name: value for name, value in base.items() if name != 'channel'}))
        for value in variants:
            text = json.dumps(current_fixture(value), ensure_ascii=False, sort_keys=True, separators=(',', ':'))
            with self.subTest(value=value), self.assertRaises((TypeError, ValueError)):
                can_field_from_key(text)
        for text in ('[]', 'null', '{}', '{broken', 'battery.current', 'NaN',
                key.replace('"channel":0', '"channel":0,"channel":0'),
                key.replace('"frame_id":801', '"frame_id":NaN'), 'x' * (MAX_WIRE_BYTES + 1)):
            with self.subTest(text=text[:100]), self.assertRaises((TypeError, ValueError)):
                can_field_from_key(text)
        for text in (key.encode('utf-8'), None, 0, False):
            with self.subTest(kind=type(text)), self.assertRaises(TypeError):
                can_field_from_key(text)

    def test_reference_preserves_full_identity_timestamp_and_is_frozen(self):
        """继承通用身份并保路径/原定位/原浮点/量化，求值别名只对应原yield位置。

        参数: 无。返回: None。异常: 身份原值丢失、改时间或允许引用变动时断言失败。
        """
        ref, field = self.reference(), self.locator()
        self.assertIsInstance(ref, SourceRef)
        self.assertEqual((ref.session_id, ref.source_name, ref.field), ('session', 'source_can', field.key))
        self.assertEqual((ref.path, ref.profile, ref.channel, ref.signal, ref.frame_id,
            ref.is_extended, ref.is_fd), ('原始输入/input.BLF', PROFILE_ID, 0, field.signal, 0x321, False, False))
        self.assertEqual((ref.timestamp, ref.time_quantized, ref.yield_sequence, ref.evaluation_index),
            (1.234567890123, True, 0, 0))
        same_time_next = replace(ref, yield_sequence=1)
        self.assertEqual(same_time_next.timestamp, ref.timestamp)
        self.assertEqual(same_time_next.evaluation_index, 1)
        self.assertNotEqual(same_time_next, ref)
        for name, value in (('yield_sequence', 9), ('timestamp', 0.0), ('evaluation_index', 9)):
            with self.subTest(name=name), self.assertRaises(FrozenInstanceError):
                setattr(ref, name, value)

    def test_reference_rejects_locator_and_common_identity_conflicts(self):
        """六字段与规范key任一不一致都拒绝，不能用合法外壳掩盖错来源引用。

        参数: 无。返回: None。异常: 定位冲突、坏基础身份、路径或profile通过断言失败。
        """
        changes = ({'channel': 1}, {'message': 'Other_Message'}, {'signal': 'other.signal'}, {'frame_id': 0x322},
            {'is_extended': True}, {'is_fd': True}, {'session_id': 'bad.session'}, {'source_name': 'bad.source'},
            {'field': ''}, {'field': 'battery.current'}, {'path': ''}, {'path': '  '}, {'path': Path('input.blf')},
            {'profile': 'other'}, {'profile': None}, {'channel': True}, {'frame_id': True},
            {'is_extended': 0}, {'is_fd': 1})
        for change in changes:
            with self.subTest(change=change), self.assertRaises((TypeError, ValueError)):
                self.reference(**change)

    def test_reference_rejects_noncanonical_keys_without_reparsing_same_locator(self):
        """公共引用仍逐字核规范JSON，不为每条相同原定位再解析一次。

        参数: 无。返回: None。异常: 接受空白/转义/重复键/子类或重新解析时断言失败。
        """
        field, text = self.locator(), self.locator().key
        bad = (' ' + text, text + '\n',
               json.dumps(current_fixture(field_to_dict(field)), ensure_ascii=True, sort_keys=True, separators=(',', ':')),
               text.replace('"channel":0', '"channel":0,"channel":0'),
               text.replace('"channel":0', '"channel":false'), ForeignText(text))
        # 这里只禁重解析，原LegacyCANField及其有界规范编码器照常执行完整检查。
        with patch('chronaxis.sources.can_spec.can_field_from_key', side_effect=AssertionError('重复定位解析')):
            self.assertEqual(self.reference().field, text)
            for key in bad:
                with self.subTest(key=key), self.assertRaises((TypeError, ValueError)):
                    self.reference(field=key)

    def test_reference_requires_native_sequence_finite_float_and_bool_quantization(self):
        """原时间允许负秒/-0.0而保留精度诊断；非有限、bool序号和猜测量化值拒绝。

        参数: 无。返回: None。异常: 非法追溯字段通过或原负零/位置被改写断言失败。
        """
        negative_zero = self.reference(timestamp=-0.0, yield_sequence=(1 << 64) + 1, time_quantized=False)
        self.assertEqual(copysign(1.0, negative_zero.timestamp), -1.0)
        self.assertEqual(negative_zero.evaluation_index, (1 << 64) + 1)
        self.assertEqual(self.reference(timestamp=-1.5).timestamp, -1.5)
        for change in ({'yield_sequence': -1}, {'yield_sequence': True}, {'yield_sequence': 0.0},
                {'yield_sequence': ForeignInteger(0)}, {'timestamp': 0}, {'timestamp': True}, {'timestamp': '0'},
                {'timestamp': float('nan')}, {'timestamp': float('inf')}, {'timestamp': float('-inf')},
                {'time_quantized': 0}, {'time_quantized': 'false'}):
            with self.subTest(change=change), self.assertRaises((TypeError, ValueError)):
                self.reference(**change)
