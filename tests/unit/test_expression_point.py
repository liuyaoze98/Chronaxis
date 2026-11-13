"""核对流式生产逐点核与手算结果、独立参考核和真正批量NumPy核。

用有限的边界样例验证定宽、有效分支、单位、查表及宿主协议。生产入口禁用
参考/数组解释器仍须工作；数组后端自身仍按整列计算，不借用生产逐点实现。
测试仅构造内存输入，不读取真实日志，也不提供性能收益结论。
"""

from dataclasses import replace
from math import copysign
import unittest
from unittest.mock import patch

import numpy as np

from chronaxis.core import expression_numpy, expression_reference
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.declarations import DeclarationBindings, DeclaredSource
from chronaxis.core.expression import ExprNode, validate_expression
from chronaxis.core.expression_point import PointProgram
from chronaxis.core.lookup import LookupTablePlan
from chronaxis.core.models import Interval, TimebaseSpec
from chronaxis.core.numeric_numpy import NumericArray, DTYPES, _output
from chronaxis.core.scalar import ScalarValue
from chronaxis.core.types import QualityFlag as Q, SignalDType as D, TimeType
from chronaxis.core.where_updates import reference_updates, numpy_updates
from chronaxis.execution.driver_expression import DriverExpression
from chronaxis.execution.groups import DecodedTimeGroup
from chronaxis.execution.state import LatestSignalState
from chronaxis.extensions import FunctionSpec, ValueSpec, using_extension_budget
from chronaxis.results.budget import ResourceBudget
from test_stream_state import make_sample


def node(op, dtype, *args, **options):
    """建立静态测试树。参数: 操作、类型、子树及节点属性。返回: ExprNode。异常: 构造错误。"""
    aliases = tuple(dict.fromkeys(alias for arg in args for alias in arg.aliases))
    return ExprNode(op, dtype, '1', 'verified', args=tuple(args), aliases=aliases, **options)


def name(alias, dtype, *, labels=()):
    """声明一个测试输入。参数: 名称、类型和枚举域。返回: 名称节点。异常: 构造错误。"""
    return ExprNode('name', dtype, '1', 'verified', name=alias, aliases=(alias,), labels=labels)


def column(value):
    """独立装箱给数组对照核，不调用被测适配器。

    参数: 一条规范标量。返回: 保留原码的单行NumericArray。异常: 模型错误。
    """
    raw = value.labels.index(value.value) if value.valid and value.labels else value.value if value.valid else 0
    return NumericArray(value.dtype, np.array([raw], dtype=DTYPES[value.dtype]),
                        np.array([value.valid]), np.array([int(value.quality)], dtype=np.uint16),
                        value.labels, None if value.code is None else column(value.code))


class PointExpressionTests(unittest.TestCase):
    """以明确数值/质量答案覆盖生产逐点入口，不把另一实现当作唯一真值。"""

    def check(self, root, context, expected, *, quality=Q.NONE, diagnostic=None):
        """对照三个独立核及给定答案。参数: 树、输入、答案和质量。返回: 逐点结果。异常: 断言。"""
        program = PointProgram(root)
        actual = program.evaluate(context, {})
        reference = expression_reference._evaluate(root, context, {})
        array = expression_numpy._evaluate(root, {key: column(value) for key, value in context.items()}, 1, {})
        for result in (actual, reference):
            self.assertEqual((result.value.dtype, result.value.valid, result.value.quality),
                             (root.dtype, quality == Q.NONE, quality))
            self.assertEqual(result.value.value, expected)
        self.assertEqual((array.value.dtype, bool(array.value.valid[0]), Q(int(array.value.quality[0]))),
                         (root.dtype, quality == Q.NONE, quality))
        if quality == Q.NONE:
            array_value = (array.value.labels[int(array.value.values[0])] if array.value.labels
                           else array.value.values[0].item())
            self.assertEqual(array_value, expected)
        wanted_diagnostic = quality if diagnostic is None else diagnostic
        self.assertEqual((actual.dependency_quality, reference.dependency_quality,
                          Q(int(array.dependency_quality[0]))), (wanted_diagnostic,) * 3)
        return actual.value

    def test_integer_arithmetic_and_mixed_comparison_boundaries(self):
        """整数溢出不回绕，混合符号比较不转浮点。参数: 无。返回: 无。异常: 断言。"""
        for op, dtype, a, b, expected, quality in (
                ('add', D.INT64, (1 << 63) - 1, 1, None, Q.OVERFLOW),
                ('sub', D.UINT64, 0, 1, None, Q.OVERFLOW),
                ('mul', D.INT64, -(1 << 62), 3, None, Q.OVERFLOW),
                ('mul', D.UINT64, 1 << 32, (1 << 32) - 1, (1 << 64) - (1 << 32), Q.NONE)):
            with self.subTest(op=op, dtype=dtype):
                self.check(node(op, dtype, name('a', dtype), name('b', dtype)),
                           {'a': ScalarValue(a, dtype), 'b': ScalarValue(b, dtype)}, expected, quality=quality)
        self.check(node('lt', D.BOOL, name('a', D.INT64), name('b', D.UINT64)),
                   {'a': ScalarValue(-1, D.INT64), 'b': ScalarValue((1 << 64) - 1, D.UINT64)}, True)
        self.check(node('int_literal_lt', D.BOOL, name('a', D.UINT64), value=1 << 100),
                   {'a': ScalarValue((1 << 64) - 1, D.UINT64)}, True)

    def test_float_precision_nonfinite_and_invalid_priority(self):
        """精确大整数可转，丢有效位拒绝，无效输入不补造第二个精度错误。参数: 无。返回: 无。异常: 断言。"""
        for number, expected, quality in ((1 << 63, float(1 << 63), Q.NONE),
                                          ((1 << 53) + 1, None, Q.PRECISION_LOSS)):
            self.check(node('to_float', D.FLOAT64, name('x', D.UINT64)),
                       {'x': ScalarValue(number, D.UINT64)}, expected, quality=quality)
        self.check(node('mul', D.FLOAT64, name('a', D.FLOAT64), name('b', D.FLOAT64)),
                   {'a': ScalarValue(1e308, D.FLOAT64), 'b': ScalarValue(2., D.FLOAT64)}, None, quality=Q.NONFINITE)
        self.check(node('div', D.FLOAT64, name('a', D.FLOAT64), name('b', D.FLOAT64)),
                   {'a': ScalarValue(1., D.FLOAT64), 'b': ScalarValue(0., D.FLOAT64)}, None, quality=Q.DOMAIN_ERROR)
        self.check(node('add', D.FLOAT64, name('a', D.UINT64), name('b', D.FLOAT64), allow_float_literal=True),
                   {'a': ScalarValue((1 << 53) + 1, D.UINT64),
                    'b': ScalarValue(None, D.FLOAT64, False, Q.MISSING)}, None, quality=Q.MISSING)

    def test_affine_units_and_zero_rules(self):
        """完整仿射允许偏移抵消，纯倍率下溢拒绝。参数: 无。返回: 无。异常: 断言。"""
        for raw, scale, offset, expected, quality in (
                (1500., .001, 0., 1.5, Q.NONE), (-273.15, 1., 273.15, 0., Q.NONE),
                (5e-324, .5, 0., None, Q.PRECISION_LOSS)):
            self.check(node('unit_convert', D.FLOAT64, name('x', D.FLOAT64), value=(scale, offset)),
                       {'x': ScalarValue(raw, D.FLOAT64)}, expected, quality=quality)
        self.check(node('unit_convert', D.INT64, name('x', D.INT64), value=(2, -1)),
                   {'x': ScalarValue(1 << 62, D.INT64)}, (1 << 63) - 1)

    def test_compiler_float_literals_and_exact_large_comparison(self):
        """使用真实编译器的混合字面量许可，不把许可误当成舍入大整数的同意。参数: 无。返回: 无。异常: 断言。"""
        clock = TimebaseSpec('analysis', TimeType.RELATIVE, 'test_origin')
        signals = (SignalDefinition('unsigned', 'bus', 'u', D.UINT64, '1', 10**9),)
        declarations = DeclarationBindings('session', clock, Interval(0, 10**9),
                                          (DeclaredSource('bus', clock, 'synthetic'),), signals)
        for expression, raw, expected, quality in (
                ('unsigned + 0.5', 2, 2.5, Q.NONE),
                ('unsigned + 0.0', 1 << 63, float(1 << 63), Q.NONE),
                ('unsigned + 0.0', (1 << 53) + 1, None, Q.PRECISION_LOSS),
                ('unsigned == 9007199254740993', (1 << 53) + 1, True, Q.NONE),
                ('unsigned < 18446744073709551616', (1 << 64) - 1, True, Q.NONE)):
            with self.subTest(expression=expression, raw=raw):
                compiled = validate_expression(expression, declarations)
                self.check(compiled.root, {'unsigned': ScalarValue(raw, D.UINT64)}, expected, quality=quality)
        compiled = validate_expression('-0.0', declarations)
        value = self.check(compiled.root, {}, -0.)
        self.assertEqual(copysign(1., value.value), -1.)

    def test_math_signed_zero_and_bad_clip_boundaries(self):
        """极值保留首个等值负零，坏限幅保留输入与域两项原因。参数: 无。返回: 无。异常: 断言。"""
        for op in ('minimum', 'maximum'):
            value = self.check(node(op, D.FLOAT64, name('a', D.FLOAT64), name('b', D.FLOAT64)),
                               {'a': ScalarValue(-0., D.FLOAT64), 'b': ScalarValue(0., D.FLOAT64)}, -0.)
            self.assertEqual(copysign(1., value.value), -1.)
        self.check(node('clip', D.INT64, name('x', D.INT64), name('lo', D.INT64), name('hi', D.INT64)),
                   {'x': ScalarValue(None, D.INT64, False, Q.MISSING),
                    'lo': ScalarValue(5, D.INT64), 'hi': ScalarValue(2, D.INT64)},
                   None, quality=Q.MISSING | Q.DOMAIN_ERROR)
        self.check(node('sqrt', D.FLOAT64, name('x', D.INT64)),
                   {'x': ScalarValue(-((1 << 53) + 1), D.INT64)}, None, quality=Q.DOMAIN_ERROR)
        self.check(node('sqrt', D.FLOAT64, name('x', D.INT64)), {'x': ScalarValue(9, D.INT64)}, 3.)

    def test_boolean_known_result_keeps_dependency_reason(self):
        """已知真假可决定三值结果，但依赖诊断不消失。参数: 无。返回: 无。异常: 断言。"""
        missing = ScalarValue(None, D.BOOL, False, Q.MISSING)
        for op, decisive in (('and', False), ('or', True)):
            self.check(node(op, D.BOOL, name('x', D.BOOL), name('y', D.BOOL)),
                       {'x': missing, 'y': ScalarValue(decisive, D.BOOL)}, decisive, diagnostic=Q.MISSING)
        self.check(node('not', D.BOOL, name('x', D.BOOL)), {'x': missing}, None, quality=Q.MISSING)

    def test_isclose_retains_intermediate_failures(self):
        """显式容差按既有非对称公式计算，溢出不被当成无限容差。参数: 无。返回: 无。异常: 断言。"""
        root = node('isclose', D.BOOL, *(name(alias, D.FLOAT64) for alias in ('a', 'b', 'atol', 'rtol')))
        self.check(root, {key: ScalarValue(value, D.FLOAT64) for key, value in
                         dict(a=10.5, b=10., atol=.1, rtol=.05).items()}, True)
        self.check(root, {key: ScalarValue(value, D.FLOAT64) for key, value in
                         dict(a=1e308, b=-1e308, atol=.1, rtol=.05).items()}, None, quality=Q.NONFINITE)

    def test_where_only_visits_selected_names_and_no_value_cache_leaks(self):
        """未选分支不求值；复用程序时数值缓存不能跨点继承。参数: 无。返回: 无。异常: 断言。"""
        root = node('where', D.FLOAT64, name('flag', D.BOOL), name('yes', D.FLOAT64), name('no', D.FLOAT64))
        program = PointProgram(root)
        cache = {}
        result = program.evaluate({'flag': ScalarValue(True, D.BOOL), 'yes': ScalarValue(4., D.FLOAT64)}, cache)
        self.assertEqual(result.value.value, 4.)
        self.assertEqual(set(program.used_names(cache)), {'flag', 'yes'})
        result = program.evaluate({'flag': ScalarValue(False, D.BOOL), 'no': ScalarValue(7., D.FLOAT64)}, {})
        self.assertEqual(result.value.value, 7.)
        result = program.evaluate({'flag': ScalarValue(None, D.BOOL, False, Q.MISSING)}, {})
        self.assertEqual(result.value.quality, Q.MISSING)

    def test_where_update_evidence_matches_atomic_group_rules(self):
        """条件同值刷新不采样、分支更新仍采样、未知恢复和切换采样。参数: 无。返回: 无。异常: 断言。"""
        root = node('where', D.FLOAT64, name('flag', D.BOOL), name('yes', D.FLOAT64), name('no', D.FLOAT64))
        program = PointProgram(root)
        previous = {'flag': ScalarValue(True, D.BOOL), 'yes': ScalarValue(4., D.FLOAT64), 'no': ScalarValue(7., D.FLOAT64)}
        cases = ((previous, dict(flag=True, yes=False, no=False), False),
                 (previous, dict(flag=False, yes=True, no=False), True),
                 (previous, dict(flag=False, yes=False, no=True), False),
                 ({**previous, 'flag': ScalarValue(False, D.BOOL)}, dict(flag=True, yes=False, no=False), True),
                 ({**previous, 'flag': ScalarValue(None, D.BOOL, False, Q.MISSING)}, dict(flag=True, yes=False, no=False), True))
        for current, updates, expected in cases:
            self.assertEqual(program.updates(root, current, previous, updates), expected)
            self.assertEqual(reference_updates(root, current, previous, updates), expected)
            array = numpy_updates(root, {k: column(v) for k, v in current.items()},
                                  {k: column(v) for k, v in previous.items()},
                                  {k: np.array([v]) for k, v in updates.items()}, 1)
            self.assertEqual(bool(array[0]), expected)
        unknown = {**previous, 'flag': ScalarValue(None, D.BOOL, False, Q.MISSING)}
        self.assertTrue(program.updates(root, previous, unknown, dict(flag=True, yes=False, no=False)))

    def test_enum_code_survives_unknown_label(self):
        """标签未知不屏蔽合法原码；缺观测保持缺失。参数: 无。返回: 无。异常: 断言。"""
        operand = name('state', D.ENUM, labels=('off', 'on'))
        root = node('enum_code', D.INT64, operand)
        self.check(root, {'state': ScalarValue(None, D.ENUM, False, Q.OUT_OF_RANGE,
                                             operand.labels, ScalarValue(9, D.INT64))}, 9)
        self.check(root, {'state': ScalarValue(None, D.ENUM, False, Q.MISSING, operand.labels)},
                   None, quality=Q.MISSING)

    def test_integer_functions_keep_width_and_fractional_quality(self):
        """定宽余数、符号位和转型边界与手算一致。参数: 无。返回: 无。异常: 断言。"""
        self.check(node('mod', D.INT64, name('a', D.INT64), name('b', D.INT64)),
                   {'a': ScalarValue(-(1 << 63), D.INT64), 'b': ScalarValue(-1, D.INT64)}, 0)
        self.check(node('bit_extract', D.UINT64, name('x', D.INT64), value=(0, 64)),
                   {'x': ScalarValue(-1, D.INT64)}, (1 << 64) - 1)
        self.check(node('bit_test', D.BOOL, name('x', D.INT64), value=(63, 1)),
                   {'x': ScalarValue(-1, D.INT64)}, True)
        for raw, quality in ((1.5, Q.PRECISION_LOSS), (float(1 << 63), Q.OVERFLOW)):
            self.check(node('to_int64', D.INT64, name('x', D.FLOAT64)),
                       {'x': ScalarValue(raw, D.FLOAT64)}, None, quality=quality)

    def test_lookup_modes_bounds_and_reused_readonly_views(self):
        """准备期建立只读视图，逐点查询不重建表。参数: 无。返回: 无。异常: 断言。"""
        table = LookupTablePlan('curve', ((1, 10), (2, 40), (4, 60)), 'V', 'W')
        for mode, expected in (('linear', 25.), ('previous', 10), ('next', 40)):
            prepared = table.prepare(mode, 'invalid')
            root = node('lookup', prepared.dtype, name('x', D.FLOAT64), value=prepared)
            self.check(root, {'x': ScalarValue(1.5, D.FLOAT64)}, expected)
            self.check(root, {'x': ScalarValue(0., D.FLOAT64)}, None, quality=Q.OUT_OF_RANGE)
            program = PointProgram(root)
            with patch('numpy.frombuffer', side_effect=AssertionError('逐点不可重建表视图')):
                self.assertEqual(program.evaluate({'x': ScalarValue(2., D.FLOAT64)}, {}).value.value, 40)
            _, axis, values = program._tables[id(root)]
            self.assertFalse(axis.flags.writeable or values.flags.writeable)
        limit = float.fromhex('0x1.fffffffffffffp+1023')
        prepared = LookupTablePlan('wide', ((-limit, -1.), (limit, 1.)), 'V', 'W').prepare('linear', 'invalid')
        self.check(node('lookup', D.FLOAT64, name('x', D.FLOAT64), value=prepared),
                   {'x': ScalarValue(0., D.FLOAT64)}, None, quality=Q.NONFINITE)
        for points, query in ((((0., 0.), (limit, 1.)), 5e-324),
                              (((-limit, 0.), (0., 1.)), -5e-324)):
            prepared = LookupTablePlan('rounded', points, 'V', 'W').prepare('linear', 'invalid')
            self.check(node('lookup', D.FLOAT64, name('x', D.FLOAT64), value=prepared),
                       {'x': ScalarValue(query, D.FLOAT64)}, None, quality=Q.PRECISION_LOSS)
        # 平坦区间无需除以跨度；即使跨度本身会溢出，返回共同节点值仍是原合同。
        prepared = LookupTablePlan('flat', ((-limit, 2.), (limit, 2.)), 'V', 'W').prepare('linear', 'invalid')
        self.check(node('lookup', D.FLOAT64, name('x', D.FLOAT64), value=prepared),
                   {'x': ScalarValue(0., D.FLOAT64)}, 2.)

    def test_plugin_keeps_numpy_callback_and_releases_resources(self):
        """只有宿主边界装列，无效或未选分支不运行回调，失败归还资源。参数: 无。返回: 无。异常: 断言。"""
        calls = []
        def reference(args, resources):
            """参数: 宿主输入。返回: 不应返回。异常: 错误后端立即失败。"""
            raise AssertionError('生产NumPy选择不可调用参考回调')
        def numpy_callback(args, resources):
            """参数: 有效列和预算。返回: 双倍列。异常: 预算错误。"""
            resources.reserve(32)
            calls.append(len(args[0].values))
            return _output(D.FLOAT64, args[0].values * 2., np.zeros(1, dtype=np.uint16))
        spec = FunctionSpec('calibrate', 'v1', (ValueSpec(D.FLOAT64, '1'),),
                            ValueSpec(D.FLOAT64, '1'), reference, numpy_callback)
        hosted = node('host_function', D.FLOAT64, name('x', D.FLOAT64), host_function=spec)
        root = node('where', D.FLOAT64, name('flag', D.BOOL), hosted, name('fallback', D.FLOAT64))
        program = PointProgram(root)
        budget = ResourceBudget()
        with using_extension_budget(budget):
            self.assertEqual(program.evaluate({'flag': ScalarValue(True, D.BOOL), 'x': ScalarValue(3., D.FLOAT64)}, {}).value.value, 6.)
            self.assertEqual(calls, [1])
            self.assertEqual(budget.ram_bytes, 0)

            self.assertEqual(program.evaluate({'flag': ScalarValue(False, D.BOOL), 'fallback': ScalarValue(4., D.FLOAT64)}, {}).value.value, 4.)
            self.assertFalse(program.evaluate({'flag': ScalarValue(True, D.BOOL), 'x': ScalarValue(None, D.FLOAT64, False, Q.MISSING)}, {}).value.valid)
            self.assertEqual(calls, [1])
            def broken(args, resources):
                """参数: 有效列和预算。返回: 无。异常: 预约后取消。"""
                resources.reserve(32)
                raise KeyboardInterrupt('取消测试')
            bad = replace(spec, numpy=broken)
            with self.assertRaises(KeyboardInterrupt):
                PointProgram(node('host_function', D.FLOAT64, name('x', D.FLOAT64), host_function=bad)).evaluate(
                    {'x': ScalarValue(1., D.FLOAT64)}, {})
            self.assertEqual(budget.ram_bytes, 0)

    def test_real_array_evaluation_remains_independent(self):
        """三行数组仍由整列核执行，不能回到Python逐点解释器。参数: 无。返回: 无。异常: 断言。"""
        root = node('mul', D.INT64, name('a', D.INT64), name('b', D.INT64))
        context = {key: NumericArray(D.INT64, np.array(values, dtype=np.int64), np.ones(3, dtype=bool),
                                    np.zeros(3, dtype=np.uint16))
                   for key, values in dict(a=[2, 3, 4], b=[5, 6, 7]).items()}
        with patch.object(PointProgram, 'evaluate', side_effect=AssertionError('整列核不能逐点解释')):
            result = expression_numpy._evaluate(root, context, 3, {})
        self.assertEqual(result.value.values.tolist(), [10, 18, 28])

    def test_driver_builtin_path_avoids_arrays_and_reference_evaluation(self):
        """真实状态、TTL和活动分支都走逐点入口；关闭退款且不关闭借入状态。参数: 无。返回: 无。异常: 断言。"""
        clock = TimebaseSpec('analysis', TimeType.RELATIVE, 'test_origin')
        signals = (SignalDefinition('flag', 'bus', 'flag', D.BOOL, '1', 10**9),
                   SignalDefinition('voltage', 'bus', 'v', D.FLOAT64, 'mV', 150_000_000),
                   SignalDefinition('fallback', 'bus', 'other', D.FLOAT64, 'mV', 10**9))
        declarations = DeclarationBindings('session', clock, Interval(0, 10**9),
                                          (DeclaredSource('bus', clock, 'synthetic'),), signals)
        static = validate_expression('where(flag, voltage, fallback)', declarations, unit='V')
        budget = ResourceBudget()
        state = LatestSignalState(budget, signals, 'session')
        self.addCleanup(state.close)
        driver = DriverExpression(static, state, None, backend='numpy')
        self.addCleanup(driver.close)
        samples = tuple(make_sample(definition, 0, index, raw) for index, (definition, raw)
                        in enumerate(zip(signals, (True, 1500., None))))
        state.apply(DecodedTimeGroup(0, samples))
        with patch.object(expression_reference, '_evaluate', side_effect=AssertionError('参考核被调用')), \
             patch.object(expression_numpy, '_evaluate', side_effect=AssertionError('单元素数组解释器被调用')), \
             patch.object(NumericArray, '__post_init__', side_effect=AssertionError('内建逐点不可装列')):
            value, deadline = driver.evaluate_at(0)
            self.assertEqual((value.value, deadline), (1.5, 150_000_000))
            self.assertTrue(driver.actual_update_at(0))
            expired, _ = driver.evaluate_at(150_000_000)
            self.assertEqual(expired.quality, Q.STALE)
            # 部分有效性只来自选中的分支，未选数据不污染正常读数。
            context = dict(flag=ScalarValue(True, D.BOOL), voltage=ScalarValue(1500., D.FLOAT64),
                           fallback=ScalarValue(7000., D.FLOAT64, partial=True))
            self.assertFalse(driver._evaluate_values(context).partial)
            context['flag'] = ScalarValue(False, D.BOOL)
            self.assertTrue(driver._evaluate_values(context).partial)
        driver.close()
        self.assertFalse(state.closed)
        state.close()
        self.assertEqual(budget.ram_bytes, 0)
