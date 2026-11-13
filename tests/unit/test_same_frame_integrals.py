"""独立手算同帧实际积分，检查同刻选择、TTL、数值质量和预算责任。"""

import unittest
from unittest.mock import patch

from chronaxis.core.binding import SignalDefinition
from chronaxis.core.declarations import DeclarationBindings, DeclaredSource
from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.expression import validate_expression
from chronaxis.core.models import Interval, TimebaseSpec, SourceRef
from chronaxis.core.types import SignalDType as D, TimeType, QualityFlag as Q
from chronaxis.execution.record_integral import RecordIntegral
from chronaxis.execution.same_frame_integrals import SameFrameIntegrals, same_frame_binding
from chronaxis.legacy.records import LegacyCANField, field_to_dict
from chronaxis.legacy.updates import LegacyDecodedUpdate
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import ResultClosedError


class SameFrameIntegralTests(unittest.TestCase):
    """无文件或共用数值真值；预期面积由给定帧时刻与TTL直接计算。"""

    def owners(self, *, age=10**9, policy='error', window=None, size=2, unit='J'):
        """创建独立共享账本和借用积分器。参数: TTL/冲突/范围/批/单位。返回: 两owner及账本。"""
        clock = TimebaseSpec('analysis', TimeType.RELATIVE, 'origin')
        fields = tuple(LegacyCANField(channel=0, frame_id=256, signal=signal)
                       for signal in ('Voltage', 'Current'))
        definitions = tuple(SignalDefinition(name, 'bus', field.key, D.FLOAT64, symbol,
                            age if name == 'v' else 10**9, same_time_policy=policy)
                            for name, field, symbol in zip(('v', 'i'), fields, ('V', 'A')))
        declarations = DeclarationBindings('session', clock, Interval(0, 10**9),
            (DeclaredSource('bus', clock, 'synthetic'),), definitions)
        expression = validate_expression('v * i', declarations)
        facts = tuple(dict(locator=field_to_dict(field), dbc_frames=((False, False),)) for field in fields)
        binding = same_frame_binding(definitions, facts)
        self.assertIsNotNone(binding)
        budget = ResourceBudget()
        integral = RecordIntegral(budget, CalculationDefinition('energy', 'integral',
            window or Interval(0, 300_000_000), output_unit=unit), 'W', D.FLOAT64, None,
            backend='reference', batch_intervals=size)
        self.addCleanup(integral.close)
        owner = SameFrameIntegrals(budget, definitions, (expression,), (integral,),
                                   binding, 'session', lambda: None)
        self.addCleanup(owner.close)
        return owner, integral, budget

    def test_explicit_frame_metadata_and_existing_fd_notice(self):
        """显式帧型的既有元数据没有dbc_frames，兼容提示仍足以证明同帧。"""
        fields = tuple(LegacyCANField(0, signal, 256, False, False) for signal in ('Voltage','Current'))
        definitions = tuple(SignalDefinition(alias, 'bus', field.key, D.FLOAT64, unit, 10**9)
                            for alias, field, unit in zip(('v','i'), fields, ('V','A')))
        facts = tuple(dict(locator=field_to_dict(field), unit=unit) for field, unit in zip(fields,('V','A')))
        self.assertFalse(same_frame_binding(definitions, facts).dbc_fd)
        notice = dict(code='dbc_fd_classic_selector', dbc_is_fd=True, requested_is_fd=False)
        compatible = tuple(dict(fact, frame_format_compatibility=notice) for fact in facts)
        self.assertTrue(same_frame_binding(definitions, compatible).dbc_fd)
        self.assertIsNone(same_frame_binding(definitions, facts[:1]))
        self.assertIsNone(same_frame_binding(definitions, (facts[0], compatible[1])))

    def update(self, time, sequence, v=400., i=10.):
        """生成一条同步电压/电流更新。参数: ns/原序号/原值。返回: 已校验更新。"""
        return LegacyDecodedUpdate(time, 'bus', 0, 256, False, False, False, False,
            SourceRef('session', 'bus', 'message'), sequence, sequence, dict(Voltage=v, Current=i))

    def close_zero(self, owner, integral, budget):
        """只关闭自己的资源，最后账本必须归零。参数: owner三件。返回: None。异常: 断言。"""
        owner.close()
        self.assertGreater(budget.ram_bytes, 0)  # 借用积分器尚由调用方持有。
        integral.close()
        self.assertEqual(budget.ram_bytes, 0)

    def test_actual_clipping_eof_and_units_across_buffer_sizes(self):
        """4000W×(0.24-0.06)s=720J=0.2Wh，EOF尾段及批容量不改变结果。"""
        for size in (1, 2, 64):
            owner, integral, budget = self.owners(size=size, unit='Wh',
                window=Interval(60_000_000, 240_000_000))
            owner.consume(self.update(0, 0))
            owner.consume(self.update(120_000_000, 1))
            owner.finish(300_000_000)
            result = integral.finish()
            self.assertAlmostEqual(result.value, .2)
            self.assertEqual((result.status, result.quality), ('complete', Q.NONE))
            self.close_zero(owner, integral, budget)

    def test_ttl_invalid_overwrite_and_no_fabricated_observation(self):
        """两段50ms有效期共400J；中间缺值只保留480J；空输入和单点没有面积。"""
        owner, integral, budget = self.owners(age=50_000_000)
        owner.consume(self.update(0, 0)); owner.consume(self.update(120_000_000, 1))
        owner.finish(300_000_000)
        result = integral.finish()
        self.assertEqual(result.value, 400.)
        self.assertEqual(result.status, 'partial')
        self.assertTrue(result.quality & Q.STALE)
        self.close_zero(owner, integral, budget)
        owner, integral, budget = self.owners()
        owner.consume(self.update(0, 0)); owner.consume(self.update(120_000_000, 1, v=None))
        owner.finish(300_000_000)
        result = integral.finish()
        self.assertEqual(result.value, 480.)
        self.assertTrue(result.quality & Q.MISSING)
        self.close_zero(owner, integral, budget)
        for observed_end in (None, 0):
            owner, integral, budget = self.owners()
            if observed_end is not None:
                owner.consume(self.update(0, 0))
            owner.finish(observed_end)
            self.assertIsNone(integral.finish().value)
            self.close_zero(owner, integral, budget)

    def test_same_time_selection_conflict_and_duplicate_sequence(self):
        """同刻采用最大原序号；error政策和重复序号均失败且不能继续。"""
        owner, integral, budget = self.owners(policy='last_by_sequence')
        owner.consume(self.update(0, 1))
        owner.consume(self.update(0, 0, v=300., i=20.))
        owner.consume(self.update(120_000_000, 2, v=500.))
        owner.finish(300_000_000)
        self.assertEqual(integral.finish().value, 1380.)
        self.close_zero(owner, integral, budget)
        for sequence, value, text in ((1, 401., '同信号同时间冲突'), (0, 400., '原sequence重复')):
            owner, integral, budget = self.owners()
            owner.consume(self.update(0, 0))
            with self.assertRaisesRegex(ValueError, text):
                owner.consume(self.update(0, sequence, v=value))
            with self.assertRaises(ResultClosedError):
                owner.finish(300_000_000)
            self.close_zero(owner, integral, budget)

    def test_numerical_validation_and_budget_cancellation(self):
        """精度、非有限及类型错误保留原因；费用已入账后取消仍能回收。"""
        for value, reason in ((2**53+1, Q.PRECISION_LOSS), (float('inf'), Q.NONFINITE), (True, Q.DECODE_ERROR)):
            owner, integral, budget = self.owners()
            owner.consume(self.update(0, 0, v=value))
            owner.finish(300_000_000)
            result = integral.finish()
            self.assertIsNone(result.value)
            self.assertTrue(result.quality & reason)
            self.close_zero(owner, integral, budget)
        owner, integral, budget = self.owners()
        original = budget.reserve_ram
        def cancelled(amount):
            """账本成功后模拟取消，检验owner登记。参数: bytes。返回: 无。异常: KeyboardInterrupt。"""
            original(amount)
            raise KeyboardInterrupt('cancel after reservation')
        with patch.object(budget, 'reserve_ram', side_effect=cancelled):
            with self.assertRaises(KeyboardInterrupt):
                owner.consume(self.update(0, 0))
        self.close_zero(owner, integral, budget)

    def test_binding_proof_rejects_ambiguity_without_reading(self):
        """同ID不同物理候选不能进入直接路径；字段名不同但同帧可以。"""
        owner, integral, budget = self.owners()
        definitions = tuple(owner._definitions.values())
        fields = tuple(LegacyCANField(channel=0, frame_id=256, signal=name) for name in ('Voltage', 'Current'))
        facts = tuple(dict(locator=field_to_dict(field), dbc_frames=((False, False),)) for field in fields)
        self.assertIsNotNone(same_frame_binding(definitions, facts))
        ambiguous = (dict(facts[0], dbc_frames=((False, False), (True, False))), facts[1])
        self.assertIsNone(same_frame_binding(definitions, ambiguous))
        self.assertIsNone(same_frame_binding(definitions, ()))
        self.close_zero(owner, integral, budget)
