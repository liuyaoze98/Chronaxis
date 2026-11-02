"""验证固定周期消息输入无需时间轴，且保留原数值和顺序契约。

输入全部为有限合成原值、显式定义和原帧身份。输出断言覆盖独立手算数值、
两后端归一化、原pack_decoded兼容、无时间模型冻结及累计器原子拒绝。
不读取日志或RefProjects，不生成工作文件；实际NumPy内核与参考内核独立。
未采集时间只能用None表达，同一顺序器或累计器不能混入带时间更新。
"""

# 测试只构造内存夹具，copy检查累计器所使用的顺序状态复制仍保合同。
from copy import copy
from dataclasses import FrozenInstanceError, replace
from types import MappingProxyType
import unittest
from unittest.mock import patch

# NumPy用于验证真实数组类型、所有权和按位数值，不替代独立标量真值。
import numpy as np

from chronaxis.core.binding import SignalDefinition
from chronaxis.core.models import SourceRef
from chronaxis.core.numeric_numpy import NumericArray
from chronaxis.core.types import QualityFlag as Q, SignalDType as D
from chronaxis.legacy.sum import LegacySumAccumulator, LegacySumContribution
from chronaxis.legacy.updates import LegacyDecodedUpdate, LegacyUntimedUpdate, LegacyUpdateOrder
from chronaxis.results import ResourceBudget
from chronaxis.sources.packing import pack_decoded, pack_message_values


class UntimedMessageInputTests(unittest.TestCase):
    """逐例使用独立定义和模型，不共享累计状态，不把合成结果作为真实日志证据。"""

    def definition(self, dtype=D.FLOAT64, **changes):
        """建立显式原值转换，不根据待测输入推断类型。

        参数: dtype为SignalDType；changes覆盖单位、范围或枚举映射等声明。
        返回: SignalDefinition，有限有效期只为声明完整，不产生时间消费者。
        异常: 声明校验错误直接传播；夹具不补默认业务周期。
        """
        # 有效期声明不表示无时间累计会保持上次信号值。
        fields = dict(name='value', source='bus', field='Raw.Value', dtype=dtype,
            unit='1', valid_for_ns=1)
        fields.update(changes)
        return SignalDefinition(**fields)

    def update(self, **changes):
        """构造一条无时间的合法求值，允许覆盖共有身份以测试拒绝边界。

        参数: changes为显式字段差异，time_ns缺省None，不生成假时间。
        返回: LegacyUntimedUpdate，原字段值独立冻结。
        异常: 被测模型校验错误原样传播。
        """
        # 原帧序号与求值序号均由夹具明确给定，不从None时间推算。
        fields = dict(time_ns=None, source='bus', channel=0, frame_id=0x100,
            is_extended=False, is_fd=False, is_remote=False, is_error=False,
            source_ref=SourceRef('session', 'bus', 'Raw.Value'), sequence=7,
            evaluation_index=11, values={'Raw.Value': 4000.0})
        fields.update(changes)
        return LegacyUntimedUpdate(**fields)

    def test_hand_values_quality_and_independent_backends(self):
        """转换后1000mA为1A，缺失/非有限/业务超界逐项保明确质量。

        参数: 无。返回: None。异常: 数值、质量、只读所有权或后端独立性错误则失败。
        """
        definition = self.definition(unit='A', input_unit='mA', scale=0.001,
            valid_range=(-2.0, 2.0))
        originals = (1000, None, float('inf'), -0.0, 3000)
        expected_quality = [0, int(Q.MISSING), int(Q.NONFINITE), 0, int(Q.OUT_OF_RANGE)]
        # 每个后端都核独立手算值；patch另一实现禁止隐式互相调用。
        for backend, forbidden in (('reference', 'normalize_numpy'), ('numpy', 'normalize_reference')):
            with self.subTest(backend=backend), patch('chronaxis.sources.packing.' + forbidden,
                    side_effect=AssertionError('调用了另一数值后端')):
                result = pack_message_values(definition, originals, backend)
            self.assertIs(type(result), NumericArray)
            self.assertEqual(result.values[result.valid].tolist(), [1.0, -0.0])
            # 缩放加偏移的既有契约可能把-0归一化为+0，不额外改变该语义。
            self.assertEqual(result.quality.tolist(), expected_quality)
            self.assertEqual(result.valid.tolist(), [True, False, False, True, False])
            for array in (result.values, result.valid, result.quality):
                self.assertFalse(array.flags.writeable)
                self.assertTrue(array.flags.owndata)

    def test_all_native_groups_match_existing_timed_output(self):
        """原生类型、整数边界、枚举、bool及空批兼容原pack_decoded完整数值结果。

        参数: 无。返回: None。异常: 输出列、dtype、标签或空批语义变化时失败。
        """
        fixtures = ((self.definition(D.INT64), (0, -1, 2**63-1, 2**63, 2**80, None, 1.0, True, '1')),
            (self.definition(D.UINT64), (0, 2**64-1, -1, 2**64, None, False)),
            (self.definition(D.FLOAT64), (2**53+1, 2.5, float('nan'), False, 'x', None)),
            (self.definition(D.BOOL), (True, False, 1, 0, None)),
            (self.definition(D.ENUM, choices=((1, 'scope'), (0, 'off'), ('ON', 'scope'))),
                (1, 0, 'ON', 2, None)))
        for definition, originals in fixtures:
            for backend in ('reference', 'numpy'):
                for batch in (originals, ()):
                    with self.subTest(dtype=definition.dtype, backend=backend, empty=not batch):
                        timed = pack_decoded(definition, tuple((10 + i, i, value)
                            for i, value in enumerate(batch)), SourceRef('session', 'bus', 'Raw.Value'), backend)
                        untimed = pack_message_values(definition, batch, backend)
                        for field in ('values', 'valid', 'quality'):
                            np.testing.assert_array_equal(getattr(untimed, field), getattr(timed, field))
                        self.assertEqual((untimed.dtype, untimed.labels), (timed.dtype, timed.labels))

    def test_message_pack_never_constructs_signal_series_or_time_columns(self):
        """禁止SignalSeries构造，证明无时间入口没有借0时间绕过原模型。

        参数: 无。返回: None。异常: 触及SignalSeries、添加时间身份字段或隐式接受坏原值时失败。
        """
        # 该入口直接返回NumericArray，不需要SourceRef、sequence或时间模型。
        with patch('chronaxis.sources.packing.SignalSeries', side_effect=AssertionError('构造了时间列')):
            result = pack_message_values(self.definition(), (4.0, 5.0), 'numpy')
        self.assertEqual(result.values.tolist(), [4.0, 5.0])
        for name in ('times_ns', 'time_ns', 'sequences', 'source_refs'):
            self.assertFalse(hasattr(result, name))
        for definition, originals, backend in ((None, (), 'numpy'),
                (self.definition(), [], 'numpy'), (self.definition(), (), 'automatic'),
                (self.definition(), ([],), 'numpy')):
            with self.subTest(backend=backend, originals_type=type(originals).__name__):
                with self.assertRaises(TypeError):
                    pack_message_values(definition, originals, backend)

    def test_untimed_model_preserves_parent_identity_and_frozen_values(self):
        """None时间必须显式，原身份/质量校验不弱化，原值仍独立冻结。

        参数: 无。返回: None。异常: 接受占位时间、放宽共有字段或共享可变值即失败。
        """
        original = {'Raw.Value': None, 'flag': False}
        update = self.update(values=original, quality=Q.MISSING)
        self.assertIsInstance(update, LegacyDecodedUpdate)
        self.assertIsNone(update.time_ns)
        self.assertIs(type(update.values), MappingProxyType)
        original['Raw.Value'] = 9
        self.assertIsNone(update.values['Raw.Value'])
        with self.assertRaises(FrozenInstanceError):
            update.time_ns = 0
        for value in (0, 1, False, float('nan'), 'none'):
            with self.subTest(time_ns=value), self.assertRaises(TypeError):
                self.update(time_ns=value)
        # 原有模型继续拒绝None，不把子类能力静默扩大到通用时间输入。
        with self.assertRaises(TypeError):
            LegacyDecodedUpdate(**{name: getattr(update, name) for name in update.__dataclass_fields__})
        for change, error in (({'sequence': True}, TypeError), ({'sequence': -1}, ValueError),
                ({'is_fd': 0}, TypeError), ({'frame_id': 0x800}, ValueError),
                ({'values': {'': 1}}, ValueError), ({'values': {'x': []}}, TypeError),
                ({'quality': 0}, TypeError),
                ({'source_ref': SourceRef('session', 'other', 'x')}, ValueError)):
            with self.subTest(change=change), self.assertRaises(error):
                self.update(**change)

    def test_untimed_order_uses_real_sequence_and_rejects_mixed_modes_atomically(self):
        """无时间顺序保间隙、同帧身份和求值递增，双向混用拒绝后状态不变。

        参数: 无。返回: None。异常: 假时间、同帧冲突、混用提交或copy丢模式时失败。
        """
        first = self.update()
        order = LegacyUpdateOrder('session', 'bus')
        order.accept(first)
        for changes in ({'sequence': 6}, {'evaluation_index': 11},
                {'channel': 1}, {'frame_id': 0x101}, {'is_fd': True}):
            before = order._state
            fields = dict(evaluation_index=12)
            fields.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                order.accept(replace(first, **fields))
            self.assertIs(order._state, before)
        order.accept(replace(first, evaluation_index=13, values={'other': 1}))
        order.accept(replace(first, sequence=100, evaluation_index=20))
        self.assertEqual((order.last_time_ns, order.last_sequence, order.last_evaluation_index,
            order.count), (None, 100, 20, 3))
        fields = {name: getattr(first, name) for name in first.__dataclass_fields__}
        fields.update(time_ns=9, sequence=101, evaluation_index=21)
        timed = LegacyDecodedUpdate(**fields)
        # copy.copy用于累计器候选状态；拒绝不能修改原tuple或错误切换模式。
        copied = copy(order)
        before = copied._state
        with self.assertRaises(ValueError):
            copied.accept(timed)
        self.assertIs(copied._state, before)
        timed_order = LegacyUpdateOrder('session', 'bus')
        timed_order.accept(timed)
        before = timed_order._state
        with self.assertRaises(ValueError):
            timed_order.accept(replace(first, sequence=102, evaluation_index=22))
        self.assertIs(timed_order._state, before)

    def test_existing_sum_accepts_untimed_and_preserves_order_and_atomicity(self):
        """原累计器复用None时间子类，1e16/-1e16/1仍按原顺序得到1。

        参数: 无。返回: None。异常: 两后端结果不符、混用污染数值或预算未恢复时失败。
        """
        for backend in ('reference', 'numpy'):
            budget = ResourceBudget(1024**2)
            owner = LegacySumAccumulator(budget, 'session', 'bus',
                legacy_policy='explicit-contributions-v1', backend=backend, max_batch_rows=8)
            try:
                # 跨批次复用同一数值核，独立手算真值能捕获改用无序sum。
                owner.consume(tuple(LegacySumContribution(self.update(sequence=index,
                    evaluation_index=index), value) for index, value in enumerate((1e16, -1e16))))
                owner.consume((LegacySumContribution(self.update(sequence=2, evaluation_index=2), 1.0),))
                before = owner.snapshot()
                self.assertEqual((before.value, before.evaluation_count, before.contribution_count), (1.0, 3, 3))
                seed = self.update()
                fields = {name: getattr(seed, name) for name in seed.__dataclass_fields__}
                fields.update(time_ns=1, sequence=3, evaluation_index=3)
                with self.assertRaises(ValueError):
                    owner.consume((LegacySumContribution(LegacyDecodedUpdate(**fields), 10.0),))
                self.assertEqual(owner.snapshot(), before)
                owner.consume((LegacySumContribution(self.update(sequence=4, evaluation_index=4), 2.0),))
                self.assertEqual(owner.snapshot().value, 3.0)
            finally:
                owner.close()
            # 真实预算归零，不能为了接受新模型留住失败批次或关闭费用。
            self.assertEqual(budget.snapshot()['ram_estimated_bytes'], 0)


if __name__ == '__main__':
    # 仅直接执行时启动测试，导入不产生工作文件或其他副作用。
    unittest.main()
