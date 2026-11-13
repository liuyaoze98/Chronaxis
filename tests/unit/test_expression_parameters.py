"""用手算和显式合成消息绑定检验单位参数及独立两后端表达式。

本测试只验证编译、有限参数、类型、质量和表达式身份；合成MessageSourceEvidence
是模型夹具，不是来源读取证明。真实单次读取/同刻消息的公共行为另由Runner测试核对。
"""

from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import unittest
from unittest.mock import patch
from hashlib import sha256
from types import SimpleNamespace

import numpy as np

from chronaxis.core.binding import SignalBindings, SignalDefinition
from chronaxis.core.declarations import DeclarationBindings, DeclaredSource
from chronaxis.core.expression import (DerivedDefinition, StaticExpression, compile_expression,
    validate_expression)
from chronaxis.core.expression_numpy import evaluate_numpy
from chronaxis.core.expression_reference import evaluate_reference
from chronaxis.core.message_binding import (ExpressionParameter, MessageBindings,
    MessageDeclarations, MessageSourceEvidence)
from chronaxis.core.models import (Interval, MemoryRow, SessionSpec, SourceRef, SourceSpec,
    TimebaseSpec)
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.numeric_numpy import DTYPES, NumericArray
from chronaxis.core.types import QualityFlag as Q, SignalDType as D, TimeType
from chronaxis.legacy.records import LegacyDecodedFrame, LegacyRawFrame
from chronaxis.legacy.sum import LegacySumAccumulator, LegacySumContribution
from chronaxis.legacy.updates import LegacyDecodedUpdate
from chronaxis.results.budget import ResourceBudget


def raw_record(sequence, values):
    """建立已返回的完整原帧模型，不伪造CAN读取或旧求值证明。

    参数: sequence连续原序，values为本次原字段字典。返回: LegacyDecodedFrame。
    异常: 真实records校验错误传播；不改原数据或补缺失key。
    """
    frame = LegacyRawFrame(0.0, 0x100, False, False, False, 0, 2, b'\xa0\x0f',
        False, True, False, False)
    return LegacyDecodedFrame(sequence, frame, values)


def numeric_column(values, dtype):
    """只把独立typed标量装箱，不在参考真值路径调用数组数值核。

    参数: values为ScalarValue有限tuple，dtype为显式类型。返回: NumericArray。
    异常: 原布局/类型模型错误传播，不转型或广播错误输入。
    """
    return NumericArray(dtype,
        np.array([item.value if item.valid else 0 for item in values], dtype=DTYPES[dtype]),
        np.array([item.valid for item in values], dtype=np.bool_),
        np.array([int(item.quality) for item in values], dtype=np.uint16))


class ExpressionParameterTests(unittest.TestCase):
    """隔离每个真实仓、lease及累计器，普通和消息域的名称/单位规则分别验证。"""

    def setUp(self):
        """建立明确声明及真实共享预算。参数: 无。返回: None。异常: 原模型或目录错误。
        """
        self.budget = ResourceBudget(128 * 1024**2)
        self.budget.reserve_ram(111)
        self.owners = []
        self.clock = TimebaseSpec('clock', TimeType.RELATIVE, 'message-parameter-synthetic')
        self.definitions = (
            SignalDefinition('power', 'bus', 'Raw.Power', D.FLOAT64, 'W', 1),
            SignalDefinition('counter', 'bus', 'Raw.Counter', D.INT64, '1', 1),
            SignalDefinition('ratio', 'bus', 'Raw.Ratio', D.FLOAT64, '1', 1),
            SignalDefinition('unsigned', 'bus', 'Raw.Unsigned', D.UINT64, '1', 1),
            SignalDefinition('other_voltage', 'aux', 'Voltage', D.FLOAT64, 'V', 1))
        self.base = DeclarationBindings('session', self.clock, Interval(0, 10_000_000_000),
            (DeclaredSource('bus', self.clock, 'explicit-decoded-source'),
             DeclaredSource('aux', self.clock, 'another-declared-source')),
            self.definitions, derived_names=('global_derived',))

    def tearDown(self):
        """只经实际owner释放，借款必须最后仍完整。参数: 无。返回: None。异常: 漏账即失败。
        """
        for owner in reversed(self.owners):
            owner.close()
        self.assertEqual(self.budget.ram_bytes, 111)
        self.budget.release_ram(111)
        self.assertEqual(self.budget.ram_bytes, 0)

    def message(self, *, parameters=None, derived_names=(), rows=None):
        """为纯表达式测试创建确定的合成绑定；不声称已经读取或核验文件。

        参数: parameters/derived_names为消息局部声明；rows为(time_ns,原字典)有限tuple。
        返回: (MessageDeclarations,MessageBindings,合成记录tuple)。异常: 模型校验错误。
        """
        if parameters is None:
            parameters = (ExpressionParameter('period', 0.1, 's'),)
        declarations = MessageDeclarations(self.base, 'bus', parameters, derived_names)
        if rows is None:
            rows = ((0, {'Raw.Power': 4000.0}), (0, {'Raw.Power': 4000.0}))
        records = tuple(SimpleNamespace(time_ns=time, decoded=raw_record(index, values))
                        for index, (time, values) in enumerate(rows))
        digest = sha256(repr(rows).encode('utf8')).hexdigest()
        evidence = MessageSourceEvidence('bus', 'session', 'synthetic-expression-test',
            digest, digest, len(records), rows[0][0] if rows else None, rows[-1][0] if rows else None)
        return declarations, MessageBindings(declarations, evidence), records

    def compare(self, compiled, bindings, contexts):
        """同一原值分别交标量及数组核，独立核完整valid/quality/dtype和值。

        参数: compiled/bindings为实际执行身份；contexts为有限当前消息tuple。
        返回: reference结果tuple和ArrayEvaluation。异常: 身份、数值或断言错误传播。
        """
        reference = tuple(evaluate_reference(compiled, context, bindings) for context in contexts)
        columns = {name: numeric_column(tuple(context[name] for context in contexts),
            bindings.resolve(name).dtype) for name in compiled.dependencies}
        array = evaluate_numpy(compiled, columns, bindings, size=len(contexts))
        self.assertIs(array.value.dtype, compiled.root.dtype)
        self.assertEqual(array.value.valid.tolist(), [item.value.valid for item in reference])
        self.assertEqual(array.value.quality.tolist(), [int(item.value.quality) for item in reference])
        self.assertEqual(array.dependency_quality.tolist(), [int(item.dependency_quality) for item in reference])
        for index, item in enumerate(reference):
            self.assertIs(item.value.dtype, compiled.root.dtype)
            if item.value.valid:
                self.assertEqual(array.value.values[index].item(), item.value.value)
        return reference, array

    def test_hand_energy_and_two_same_time_contributions_across_backends_and_cuts(self):
        """4000W乘0.1s逐条400J，同刻两次交既有原序累计为800，切批不丢一次。

        参数: 无。返回: None。异常: 数值/次数/单位/预算断言失败。
        新evaluation_index只标识本例显式贡献，不冒称来自旧ChrgInfo调用现场。
        """
        _, bindings, records = self.message()
        compiled = compile_expression('power * period', bindings)
        self.assertEqual((compiled.root.unit, compiled.dependencies), ('J', ('power',)))
        self.assertEqual(compiled.root.unit_status, 'verified')
        self.assertEqual(tuple(item.time_ns for item in records), (0, 0))
        for backend in ('reference', 'numpy'):
            for size in (1, 2, 7):
                with self.subTest(backend=backend, size=size):
                    accumulator = LegacySumAccumulator(self.budget, 'session', 'bus',
                        legacy_policy=bindings.declarations.message_policy, backend=backend, max_batch_rows=size)
                    self.owners.append(accumulator)
                    observed = []
                    for offset in range(0, len(records), size):
                        selected = records[offset:offset + size]
                        contexts = tuple({'power': ScalarValue(item.decoded.values['Raw.Power'], D.FLOAT64)}
                            for item in selected)
                        if backend == 'reference':
                            values = tuple(evaluate_reference(compiled, context, bindings).value.value
                                for context in contexts)
                        else:
                            values = tuple(evaluate_numpy(compiled, {'power': numeric_column(
                                tuple(context['power'] for context in contexts), D.FLOAT64)}, bindings).value.values.tolist())
                        observed.extend(values)
                        contributions = []
                        for item, value in zip(selected, values):
                            frame = item.decoded.frame
                            update = LegacyDecodedUpdate(item.time_ns, 'bus', frame.channel,
                                frame.arbitration_id, frame.is_extended_id, frame.is_fd,
                                frame.is_remote_frame, frame.is_error_frame,
                                SourceRef('session', 'bus', 'Raw.Power'), item.decoded.sequence,
                                item.decoded.sequence, item.decoded.values)
                            contributions.append(LegacySumContribution(update, value))
                        accumulator.consume(tuple(contributions))
                    self.assertEqual(observed, [400.0, 400.0])
                    snapshot = accumulator.snapshot()
                    self.assertEqual((snapshot.value, snapshot.evaluation_count,
                        snapshot.contribution_count, snapshot.skipped_count), (800.0, 2, 2, 0))
                    accumulator.close()

    def test_parameter_units_survive_unary_abs_composition_and_local_derived(self):
        """参数在一元/abs/组合/派生中都保秒，不被加减或比较对方重赋瓦特。

        参数: 无。返回: None。异常: 单位洗掉、裸literal旧语义改变或求值不符时失败。
        """
        _, bindings, _ = self.message(parameters=(ExpressionParameter('period', 0.1, 's'),
            ExpressionParameter('factor', 0.1, '1')), derived_names=('energy', 'half_period'))
        derived = (DerivedDefinition('energy', 'power * abs(-period)', 'J'),
            DerivedDefinition('half_period', 'period / 2', 's'))
        for text, unit, expected in (('power * abs(-period)', 'J', 400.0),
                ('power * (period + period)', 'J', 800.0), ('energy', 'J', 400.0),
                ('power * (period / 2)', 'J', 200.0), ('power * half_period', 'J', 200.0),
                ('power + 1', 'W', 4001.0), ('power > 0', '1', True)):
            with self.subTest(text=text):
                compiled = compile_expression(text, bindings, derived=derived)
                reference, _ = self.compare(compiled, bindings,
                    ({'power': ScalarValue(4000.0, D.FLOAT64)},))
                self.assertEqual((compiled.root.unit, reference[0].value.value), (unit, expected))
        for text in ('power + period', 'power > period', 'power + abs(-period)',
                'power + (period + period)', 'power + (period / 2)', 'power + half_period',
                'power + energy'):
            with self.subTest(invalid=text), self.assertRaises(ValueError):
                compile_expression(text, bindings, derived=derived)
        # 两个容差仍只准裸数字，operation=const的typed参数也不能借此改成W或无量纲。
        for text in ('isclose(power, power, atol=period, rtol=0)',
                'isclose(power, power, atol=0, rtol=period)',
                'isclose(power, power, atol=factor, rtol=0)',
                'isclose(power, power, atol=0, rtol=factor)'):
            with self.subTest(tolerance=text), self.assertRaises(ValueError):
                compile_expression(text, bindings, derived=derived)
        compiled = compile_expression('isclose(power, power, atol=1, rtol=0)', bindings,
            derived=derived)
        self.assertTrue(self.compare(compiled, bindings,
            ({'power': ScalarValue(4000.0, D.FLOAT64)},))[0][0].value.value)

    def test_pure_parameter_columns_have_explicit_size_and_no_signal_dependencies(self):
        """无信号参数组合仍是typed FLOAT64，数组N由显式size决定而非猜一行。

        参数: 无。返回: None。异常: dtype/shape/单位/常量资格或无size门槛错误时失败。
        """
        _, bindings, _ = self.message(parameters=(ExpressionParameter('period', 0.1, 's'),
            ExpressionParameter('factor', 2, '1')))
        compiled = compile_expression('abs(-period) * factor', bindings)
        self.assertEqual((compiled.dependencies, compiled.root.unit), ((), 's'))
        self.assertFalse(compiled.root.constant)
        self.assertIs(compiled.root.dtype, D.FLOAT64)
        for size in (0, 1, 7):
            with self.subTest(size=size):
                reference, array = self.compare(compiled, bindings, tuple({} for _ in range(size)))
                self.assertEqual(array.value.values.shape, (size,))
                self.assertEqual(array.value.values.tolist(), [0.2] * size)
                self.assertTrue(all(item.value.value == 0.2 for item in reference))
                self.assertFalse(array.value.values.flags.writeable)
        with self.assertRaises(ValueError):
            evaluate_numpy(compiled, {}, bindings)
        for size in (True, -1, np.int64(1)):
            with self.subTest(invalid_size=repr(size)), self.assertRaises(TypeError):
                evaluate_numpy(compiled, {}, bindings, size=size)

    def test_parameters_require_finite_native_exact_float_and_are_frozen(self):
        """参数统一FLOAT64但不吞有损整数、bool、非原生数或非有限配置。

        参数: 无。返回: None。异常: 精度、单位状态或冻结保护不符时失败。
        """
        for value in (0, -2, 2**53, 2**53 + 2, 0.1):
            with self.subTest(value=value):
                parameter = ExpressionParameter('factor', value, '1')
                self.assertIs(type(parameter.value), float)
                self.assertEqual(parameter.value, value)
                self.assertIs(parameter.dtype, D.FLOAT64)
                self.assertEqual(parameter.unit_status, 'verified')
                with self.assertRaises(FrozenInstanceError):
                    parameter.value = 99.0
        self.assertEqual(ExpressionParameter('factor', 1, 'unregistered_unit').unit_status, 'unverified')
        for value in (True, None, '0.1', np.float64(0.1), np.int64(1)):
            with self.subTest(type_error=repr(value)), self.assertRaises(TypeError):
                ExpressionParameter('factor', value, '1')
        for value in (float('nan'), float('inf'), -float('inf'), 2**53 + 1, 10**400):
            with self.subTest(value_error=str(value)[:40]), self.assertRaises((ValueError, OverflowError)):
                ExpressionParameter('factor', value, '1')
        for name in ('abs', 'period.with.dot', '', 'for'):
            with self.subTest(name=name), self.assertRaises((TypeError, ValueError)):
                ExpressionParameter(name, 1, '1')

    def test_message_namespace_selects_original_definitions_and_rejects_all_base_collisions(self):
        """消息域只取原source定义；参数/局部derived不可遮蔽其他来源或原派生名称。

        参数: 无。返回: None。异常: 名称覆盖、重写定义或非法policy被接受时失败。
        """
        declarations = MessageDeclarations(self.base, 'bus', (ExpressionParameter('period', 0.1, 's'),),
            ('local_energy',))
        self.assertEqual(tuple(item.name for item in declarations.signals), ('power', 'counter', 'ratio', 'unsigned'))
        for actual, original in zip(declarations.signals, self.definitions):
            self.assertIs(actual, original)
        self.assertEqual(declarations.derived_names, ('local_energy',))
        self.assertIs(declarations.resolve('power'), self.definitions[0])
        for conflict in ('power', 'other_voltage', 'global_derived'):
            with self.subTest(parameter=conflict), self.assertRaises(ValueError):
                MessageDeclarations(self.base, 'bus', (ExpressionParameter(conflict, 1, '1'),))
            with self.subTest(derived=conflict), self.assertRaises(ValueError):
                MessageDeclarations(self.base, 'bus', derived_names=(conflict,))
        parameter = ExpressionParameter('period', 0.1, 's')
        for parameters, names in (((parameter, parameter), ()), ((parameter,), ('period',)),
                ((), ('local', 'local'))):
            with self.subTest(parameters=parameters, names=names), self.assertRaises(ValueError):
                MessageDeclarations(self.base, 'bus', parameters, names)
        with self.assertRaises(TypeError):
            MessageDeclarations(self.base, 'bus', [parameter])
        with self.assertRaises(ValueError):
            MessageDeclarations(self.base, 'missing')
        with self.assertRaises(ValueError):
            MessageDeclarations(self.base, 'bus', message_policy='ttl-cache')
        with self.assertRaises(ValueError):
            validate_expression('other_voltage + 1', declarations,
                derived=(DerivedDefinition('local_energy', 'power * period', 'J'),))

    def test_static_validation_has_no_io_and_does_not_create_execution_proof(self):
        """声明可静态检查400J量纲，但不能交编译运行或两个数值入口执行。

        参数: 无。返回: None。异常: 静态触碰输入、混淆模型或越过门槛时失败。
        """
        declarations = MessageDeclarations(self.base, 'bus', (ExpressionParameter('period', 0.1, 's'),))
        with patch.object(Path, 'open', side_effect=AssertionError('static must not open')):
            static = validate_expression('power * period', declarations)
        self.assertIs(type(static), StaticExpression)
        self.assertEqual((static.root.unit, static.dependencies), ('J', ('power',)))
        with self.assertRaises(TypeError):
            compile_expression('power * period', declarations)
        with self.assertRaises(TypeError):
            evaluate_reference(static, {'power': ScalarValue(4000.0, D.FLOAT64)}, declarations)
        with self.assertRaises(TypeError):
            evaluate_numpy(static, {}, declarations, size=1)

    def test_parameter_and_synthetic_input_identity_isolate_compiled_context(self):
        """参数值/单位及合成消息输入改变身份，旧compiled不得借同名新消息执行。

        参数: 无。返回: None。异常: 仅名称或声明SHA被当作执行身份时失败。
        """
        declarations, bindings, _ = self.message()
        changed = replace(declarations, parameters=(ExpressionParameter('period', 0.2, 's'),))
        changed_unit = replace(declarations, parameters=(ExpressionParameter('period', 0.1, 'ms'),))
        self.assertNotEqual(declarations.identity, changed.identity)
        self.assertNotEqual(declarations.identity, changed_unit.identity)
        # 参数类型固定FLOAT64，精确int1与float1.0同一规范值，负零hex仍保不同身份。
        integer = replace(declarations, parameters=(ExpressionParameter('period', 1, 's'),))
        floating = replace(declarations, parameters=(ExpressionParameter('period', 1.0, 's'),))
        positive_zero = replace(declarations, parameters=(ExpressionParameter('period', 0.0, 's'),))
        negative_zero = replace(declarations, parameters=(ExpressionParameter('period', -0.0, 's'),))
        self.assertEqual(integer.identity, floating.identity)
        self.assertNotEqual(positive_zero.identity, negative_zero.identity)
        _, other, _ = self.message(rows=((0, {'Raw.Power': 4001.0}),))
        self.assertIs(type(bindings), MessageBindings)
        self.assertNotEqual(bindings.identity, other.identity)
        compiled = compile_expression('power * period', bindings)
        self.assertNotEqual(compiled.identity, compile_expression('power * period', other).identity)
        with self.assertRaises(ValueError):
            evaluate_reference(compiled, {'power': ScalarValue(4000.0, D.FLOAT64)}, other)
        with self.assertRaises(ValueError):
            evaluate_numpy(compiled, {'power': numeric_column((ScalarValue(4000.0, D.FLOAT64),), D.FLOAT64)}, other)
        for context in ({}, {'power': ScalarValue(4000.0, D.FLOAT64), 'period': ScalarValue(0.1, D.FLOAT64)}):
            with self.subTest(context=context), self.assertRaises(ValueError):
                evaluate_reference(compiled, context, bindings)

    def test_message_integer_mixing_checks_precision_and_does_not_enable_two_real_dtypes(self):
        """消息参数混整数允许受检转换，有损2**53+1为质量失败，两个真实混型仍拒。

        参数: 无。返回: None。异常: 隐式舍入、丢质量或普通规则被扩张时失败。
        """
        _, bindings, _ = self.message(parameters=(ExpressionParameter('factor', 1, '1'),))
        for name, dtype in (('counter', D.INT64), ('unsigned', D.UINT64)):
            with self.subTest(name=name):
                compiled = compile_expression(name + ' * factor', bindings)
                reference, array = self.compare(compiled, bindings,
                    ({name: ScalarValue(2**53, dtype)}, {name: ScalarValue(2**53 + 1, dtype)}))
                self.assertEqual(reference[0].value.value, float(2**53))
                self.assertFalse(reference[1].value.valid)
                self.assertTrue(reference[1].value.quality & Q.PRECISION_LOSS)
                self.assertEqual(array.value.valid.tolist(), [True, False])
        with self.assertRaises(ValueError):
            compile_expression('counter + ratio', bindings)
        # 原普通memory绑定从真实SourceSpec行构造，不使用消息参数扩张普通编译入口。
        source = SourceSpec('bus', self.clock, (MemoryRow(0, {'Raw.Power': 4000.0}, 0),),
            observation_start_ns=0, observation_end_ns=1)
        ordinary = SignalBindings(SessionSpec('session', self.clock, 0, 1, (source,)),
            (self.definitions[0],))
        self.assertEqual(evaluate_reference(compile_expression('power + 1', ordinary),
            {'power': ScalarValue(4000.0, D.FLOAT64)}, ordinary).value.value, 4001.0)
        with self.assertRaises(ValueError):
            compile_expression('power * factor', ordinary)

    def test_current_message_missing_value_has_no_ttl_or_previous_message_fill(self):
        """当前原字典缺key明确MISSING，既不沿用4000也不因间隔套通用TTL。

        参数: 无。返回: None。异常: 缺值补零/前值或按时间改变当前显式值时失败。
        """
        _, bindings, records = self.message(rows=((0, {'Raw.Power': 4000.0}),
            (2_000_000_000, {}), (3_000_000_000, {'Raw.Power': 4000.0})))
        compiled = compile_expression('power * period', bindings)
        contexts = tuple({'power': ScalarValue(item.decoded.values['Raw.Power'], D.FLOAT64)
            if 'Raw.Power' in item.decoded.values else ScalarValue(None, D.FLOAT64, False, Q.MISSING)}
            for item in records)
        reference, _ = self.compare(compiled, bindings, contexts)
        self.assertEqual([item.value.value if item.value.valid else None for item in reference],
            [400.0, None, 400.0])
        self.assertEqual([item.value.quality for item in reference], [Q.NONE, Q.MISSING, Q.NONE])
        self.assertTrue(reference[1].dependency_quality & Q.MISSING)


if __name__ == '__main__':
    # 只有明确脚本运行才发现测试；正式验证由根任务统一执行并保留原日志。
    unittest.main()
