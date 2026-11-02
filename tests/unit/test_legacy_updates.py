"""独立验证兼容逐次更新的冻结原值及顺序，不构造旧链未暴露的求值点。

输入全部是本测试显式声明的LegacyDecodedUpdate，输出为模型和LegacyUpdateOrder
断言。同刻不同帧、同帧不同section保独立evaluation_index；只按合同检查顺序与
同帧身份，不去重、不套TTL、不推断dtype、不累加表达式，也不把合成流称为旧日志。
原字段全文、0/False/None/NaN/Inf保留，映射只接受精确dict或MappingProxyType并复制
冻结。拒绝后可继续接收合法记录，防止失败污染最后帧身份或公开计数。
测试只依赖标准库和纯模型，不建立工作目录、不导入可选CAN依赖、不访问Ref。
"""

from collections import UserDict
from dataclasses import FrozenInstanceError, dataclass, fields, replace
from math import copysign, isinf, isnan
from pathlib import Path
from types import MappingProxyType
import unittest
from unittest.mock import patch

from chronaxis.core.models import SourceRef
from chronaxis.core.types import QualityFlag as Q
from chronaxis.legacy.updates import LegacyDecodedUpdate, LegacyUpdateOrder


class ForeignInteger(int):
    """模拟非原生整数，检查身份和原值不会靠isinstance被隐式放行。"""


class ForeignText(str):
    """模拟非原生字段文本，检查原值映射键的精确native合同。"""


class ForeignDictionary(dict):
    """模拟dict子类，证明输入映射不接受任意自定义迭代或复制行为。"""


@dataclass(frozen=True)
class DetailedReference(SourceRef):
    """在真实冻结SourceRef上增加定位说明，验证合同明确允许引用派生类型。"""

    detail: str = 'explicit synthetic evaluation reference'


class LegacyUpdatesTests(unittest.TestCase):
    """每例显式提供有限记录与身份；模型本身不证明profile、质量或缓存已核实。"""

    def update(self, **changes):
        """构造一条完整合法的合成求值记录，差异只作用于本次独立输入。

        参数: changes为显式字段覆盖。返回: LegacyDecodedUpdate。
        异常: 被测构造校验原样传播；不补缺失帧标志或生成隐藏求值序号。
        """
        fields = dict(time_ns=100, source='bus', channel=0, frame_id=0x100,
            is_extended=False, is_fd=False, is_remote=False, is_error=False,
            source_ref=SourceRef('session', 'bus', 'Raw.Power'), sequence=0,
            evaluation_index=0, values={'Raw.Power': 4000.0})
        fields.update(changes)
        return LegacyDecodedUpdate(**fields)

    def state(self, order):
        """读取公开顺序状态作原子拒绝快照，不访问实现的临时或私有槽。

        参数: order为本例真实LegacyUpdateOrder。返回: 会话/来源及最后状态tuple。
        异常: 公开属性不存在或读取失败即测试失败，不补默认值掩盖缺失实现。
        """
        return (order.session_id, order.source, order.last_time_ns, order.last_sequence,
            order.last_evaluation_index, order.count)

    def test_original_values_are_frozen_copied_and_preserve_diagnostics(self):
        """两个允许映射都独立冻结；0/False/None、字段全文和非有限原诊断逐项保留。

        参数: 无。返回: None。异常: 引用外部可变映射、改名/补零或记录可改时断言失败。
        """
        for proxy in (False, True):
            with self.subTest(mapping_proxy=proxy):
                backing = {'  报文.Raw.Power  ': 0, '   ': 'space-only original field', 'flag': False, 'missing': None,
                    'label': '原枚举.Text', 'nan': float('nan'), 'positive_inf': float('inf'),
                    'negative_inf': float('-inf'), 'negative_zero': -0.0, 'large': (1 << 80) + 3}
                original = MappingProxyType(backing) if proxy else backing
                update = self.update(values=original)
                self.assertIs(type(update.values), MappingProxyType)
                self.assertIsNot(update.values, original)
                self.assertEqual(tuple(update.values), tuple(backing))
                self.assertIs(type(update.values['  报文.Raw.Power  ']), int)
                self.assertEqual(update.values['  报文.Raw.Power  '], 0)
                self.assertIs(update.values['flag'], False)
                self.assertIsNone(update.values['missing'])
                self.assertEqual(update.values['label'], '原枚举.Text')
                self.assertEqual(update.values['   '], 'space-only original field')
                self.assertTrue(isnan(update.values['nan']))
                self.assertTrue(isinf(update.values['positive_inf']) and update.values['positive_inf'] > 0)
                self.assertTrue(isinf(update.values['negative_inf']) and update.values['negative_inf'] < 0)
                self.assertEqual(copysign(1.0, update.values['negative_zero']), -1.0)
                self.assertEqual(update.values['large'], (1 << 80) + 3)
                # 未记录原因不证明原值正常；模型不得根据NaN或None自行猜质量。
                self.assertIs(update.quality, Q.NONE)
                backing['flag'], backing['new'] = True, 9
                del backing['missing']
                self.assertIs(update.values['flag'], False)
                self.assertIn('missing', update.values)
                self.assertNotIn('new', update.values)
                with self.assertRaises(TypeError):
                    update.values['flag'] = True
                with self.assertRaises(FrozenInstanceError):
                    update.time_ns = 101
                with self.assertRaises(FrozenInstanceError):
                    update.values = MappingProxyType({})
        self.assertEqual(dict(self.update(values={}).values), {})
        quality = Q.MISSING | Q.ESTIMATED
        self.assertIs(self.update(quality=quality).quality, quality)

    def test_mapping_native_fields_values_and_typed_quality_are_enforced(self):
        """拒绝自定义映射、空/非原生字段、可变值及非typed质量，不擅自归一化。

        参数: 无。返回: None。异常: 任一非法输入被复制、强转或吞掉时断言失败。
        """
        mappings = (UserDict({'P': 1}), ForeignDictionary(P=1), [('P', 1)], None)
        for value in mappings:
            with self.subTest(mapping_type=type(value).__name__):
                with self.assertRaises(TypeError):
                    self.update(values=value)
        for values, error in (({'': 1}, ValueError),
                ({1: 1}, TypeError), ({ForeignText('P'): 1}, TypeError),
                ({'P': []}, TypeError), ({'P': {}}, TypeError), ({'P': (1,)}, TypeError),
                ({'P': bytearray(b'x')}, TypeError), ({'P': ForeignInteger(1)}, TypeError),
                ({'P': ForeignText('text')}, TypeError)):
            with self.subTest(values_type=repr(values)):
                with self.assertRaises(error):
                    self.update(values=values)
        for quality in (0, 1, False, 'MISSING', None):
            with self.subTest(quality=quality):
                with self.assertRaises(TypeError):
                    self.update(quality=quality)

    def test_identity_integer_flags_and_time_boundaries_are_exact(self):
        """帧ID按标准/扩展位分界，身份整数拒bool，时间只采用共享int64规范。

        参数: 无。返回: None。异常: 超范围、隐式强转或缺少必填帧标志被接受时失败。
        """
        for time in (-(1 << 63), (1 << 63) - 1):
            with self.subTest(time_ns=time):
                self.assertEqual(self.update(time_ns=time).time_ns, time)
        for time in (-(1 << 63) - 1, 1 << 63):
            with self.subTest(outside_time=time):
                with self.assertRaises(OverflowError):
                    self.update(time_ns=time)
        for time in (False, 1.0, '1', None):
            with self.subTest(time_type=type(time).__name__):
                with self.assertRaises(TypeError):
                    self.update(time_ns=time)
        for extended, maximum in ((False, 0x7ff), (True, 0x1fffffff)):
            self.assertEqual(self.update(is_extended=extended, frame_id=maximum).frame_id, maximum)
            with self.assertRaises(ValueError):
                self.update(is_extended=extended, frame_id=maximum + 1)
        for name in ('channel', 'frame_id', 'sequence', 'evaluation_index'):
            for value in (True, 0.0, '0', ForeignInteger(0)):
                with self.subTest(integer_field=name, value_type=type(value).__name__):
                    with self.assertRaises(TypeError):
                        self.update(**{name: value})
            with self.subTest(negative_field=name):
                with self.assertRaises(ValueError):
                    self.update(**{name: -1})
        large = (1 << 80) + 7
        self.assertEqual((self.update(channel=large).channel,
            self.update(sequence=large).sequence, self.update(evaluation_index=large).evaluation_index), (large,) * 3)
        for name in ('is_extended', 'is_fd', 'is_remote', 'is_error'):
            for value in (0, 1, None, 'false'):
                with self.subTest(flag=name, value=value):
                    with self.assertRaises(TypeError):
                        self.update(**{name: value})
            base = self.update()
            arguments = {field.name: getattr(base, field.name) for field in fields(base) if field.name != name}
            with self.subTest(missing_flag=name):
                with self.assertRaises(TypeError):
                    LegacyDecodedUpdate(**arguments)

    def test_source_reference_and_order_owner_are_explicit(self):
        """引用需真实SourceRef及匹配source；顺序器再核会话，拒绝后仍保持空状态。

        参数: 无。返回: None。异常: 跨来源/会话被接受或错误输入污染计数时失败。
        """
        ref = DetailedReference('session', 'bus', '原字段.全文')
        self.assertIs(self.update(source_ref=ref).source_ref, ref)
        for ref in (None, {'session_id': 'session', 'source_name': 'bus', 'field': 'P'}):
            with self.subTest(reference_type=type(ref).__name__):
                with self.assertRaises(TypeError):
                    self.update(source_ref=ref)
        with self.assertRaises(ValueError):
            self.update(source_ref=SourceRef('session', 'other', 'P'))
        order = LegacyUpdateOrder('session', 'bus')
        empty = ('session', 'bus', None, None, None, 0)
        self.assertEqual(self.state(order), empty)
        for name in ('session_id', 'source', 'last_time_ns', 'last_sequence', 'last_evaluation_index', 'count'):
            with self.subTest(readonly_state=name):
                with self.assertRaises(AttributeError):
                    setattr(order, name, 9)
                self.assertEqual(self.state(order), empty)
        for update in (self.update(source='other', source_ref=SourceRef('session', 'other', 'P')),
                self.update(source_ref=SourceRef('another_session', 'bus', 'P'))):
            with self.subTest(source=update.source, session=update.source_ref.session_id):
                with self.assertRaises(ValueError):
                    order.accept(update)
                self.assertEqual(self.state(order), empty)
        for value in (None, {}, object()):
            with self.subTest(update_type=type(value).__name__):
                with self.assertRaises(TypeError):
                    order.accept(value)
                self.assertEqual(self.state(order), empty)
        self.assertIsNone(order.accept(self.update()))
        self.assertEqual(self.state(order), ('session', 'bus', 100, 0, 0, 1))

    def test_order_retains_same_time_frames_and_same_frame_sections(self):
        """手写两条同刻帧加同帧第二section，三个求值均接收且允许evaluation间隙。

        参数: 无。返回: None。异常: 按time/sequence去重、补TTL或要求序号相邻时失败。
        """
        order = LegacyUpdateOrder('session', 'bus')
        first = self.update(time_ns=0, sequence=7, evaluation_index=11, values={'P': 4000})
        second = self.update(time_ns=0, sequence=8, evaluation_index=15, values={'P': 4000})
        section = replace(second, evaluation_index=16, values={'other_section': False}, quality=Q.ESTIMATED,
            source_ref=SourceRef('session', 'bus', 'Other.section'))
        later = self.update(time_ns=10_000_000_000, sequence=10, evaluation_index=21, values={'P': None})
        for count, update in enumerate((first, second, section, later), 1):
            self.assertIsNone(order.accept(update))
            self.assertEqual(self.state(order), ('session', 'bus', update.time_ns,
                update.sequence, update.evaluation_index, count))
        # 顺序器不累计4000、不乘dt、不替换None；记录仍为调用者提供的独立原事实。
        self.assertEqual((first.values['P'], second.values['P']), (4000, 4000))
        self.assertIs(section.values['other_section'], False)
        self.assertIsNone(later.values['P'])

    def test_order_rejects_atomically_then_recovers_original_frame_identity(self):
        """每种回退/重复或同帧身份冲突都不提交，紧随其后的合法section仍可接收。

        参数: 无。返回: None。异常: 坏输入改变公开状态或隐藏最后帧身份时失败。
        """
        first = self.update(time_ns=100, sequence=7, evaluation_index=11)
        changes = ({'evaluation_index': 11}, {'evaluation_index': 10}, {'time_ns': 99},
            {'sequence': 6}, {'time_ns': 101}, {'channel': 1}, {'frame_id': 0x101},
            {'is_extended': True}, {'is_fd': True}, {'is_remote': True}, {'is_error': True})
        for change in changes:
            with self.subTest(change=change):
                order = LegacyUpdateOrder('session', 'bus')
                order.accept(first)
                before = self.state(order)
                bad = replace(first, evaluation_index=12, **change) if 'evaluation_index' not in change \
                    else replace(first, **change)
                with self.assertRaises(ValueError):
                    order.accept(bad)
                self.assertEqual(self.state(order), before)
                # 此处仍用原帧的全部身份；若失败先写了隐藏帧键，本次恢复会误拒绝。
                self.assertIsNone(order.accept(replace(first, evaluation_index=20, values={'next_section': 0})))
                self.assertEqual(self.state(order), ('session', 'bus', 100, 7, 20, 2))
                self.assertIsNone(order.accept(replace(first, time_ns=101, sequence=8, evaluation_index=21)))
                self.assertEqual(self.state(order), ('session', 'bus', 101, 8, 21, 3))

    def test_construction_and_accept_do_not_open_inputs_or_load_optional_libraries(self):
        """共同模型只校显式事实，禁止文件访问和动态加载证明无隐式旧链执行。

        参数: 无。返回: None。异常: 任一文件/加载调用或更新事实被修补时失败。
        """
        with patch('builtins.open', side_effect=AssertionError('更新模型打开文件')) as builtin_open, \
                patch.object(Path, 'open', side_effect=AssertionError('更新模型Path.open')) as path_open, \
                patch('importlib.import_module', side_effect=AssertionError('更新模型动态加载')) as dynamic:
            order = LegacyUpdateOrder('session', 'bus')
            update = self.update(time_ns=10_000_000_000, values={'cached.P': None, 'flag': False})
            order.accept(update)
        self.assertEqual(self.state(order), ('session', 'bus', 10_000_000_000, 0, 0, 1))
        self.assertEqual(dict(update.values), {'cached.P': None, 'flag': False})
        for method in (builtin_open, path_open, dynamic):
            method.assert_not_called()


if __name__ == '__main__':
    # 模块导入不执行测试；根任务统一正式运行并保存证据。
    unittest.main()
