"""BUG-AUDIT-020：合法长表达式不受普通元数据32层限制误伤。

费用对照使用修复前冻结的浅树计费公式，确保没有顺带降低预算；长加法从
实际编译器进入驱动器，结果与手算和同意义的平衡树一致。环和未知结构仍拒绝。
"""

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from sys import getsizeof
import unittest
from unittest.mock import patch

from chronaxis.core.binding import SignalDefinition
from chronaxis.core.declarations import DeclarationBindings, DeclaredSource
from chronaxis.core.expression import ExprNode, validate_expression
from chronaxis.core.models import Interval, TimebaseSpec
from chronaxis.core.types import SignalDType as D, TimeType
from chronaxis.execution import history
from chronaxis.execution.driver_expression import DriverExpression
from chronaxis.execution.groups import DecodedTimeGroup
from chronaxis.execution.state import LatestSignalState
from chronaxis.extensions import ExtensionRegistry, FunctionSpec, ReductionSpec, TransformSpec
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import ResultFormatError
from test_stream_state import make_sample


def old_shallow_cost(value, depth=0):
    """冻结修复前的计费合同，只用于浅树独立对照。

    参数: 原已支持元数据和起始深度。返回: 原公式基础字节数。
    异常: 原32层或不支持结构的ResultFormatError；不调用新估算实现。
    """
    if depth > 32:
        raise ResultFormatError('历史元数据超过32层')
    if type(value) in (ExtensionRegistry, FunctionSpec, ReductionSpec, TransformSpec):
        return 256
    if type(value) is SignalDefinition:
        defaults = {'input_dtype', 'code_dtype', 'capture_code', 'config_version'}
        return getsizeof(value) + sum(16 if field.name in defaults and getattr(value, field.name) is field.default
            else 256 + old_shallow_cost(getattr(value, field.name), depth + 1) for field in fields(value))
    if is_dataclass(value) and not isinstance(value, type):
        return getsizeof(value) + sum(256 + old_shallow_cost(getattr(value, field.name), depth + 1)
                                     for field in fields(value))
    if isinstance(value, Mapping):
        return getsizeof(value) + sum(128 + old_shallow_cost(key, depth + 1)
                                     + old_shallow_cost(item, depth + 1) for key, item in value.items())
    if type(value) is tuple:
        return getsizeof(value) + sum(32 + old_shallow_cost(item, depth + 1) for item in value)
    if isinstance(value, Enum):
        return 512
    if value is None or type(value) in (str, int, bool, float, bytes):
        return getsizeof(value) + 64
    raise ResultFormatError('历史元数据类型无法估算')


def balanced(names):
    """按原顺序给加法加平衡括号。参数: 非空别名tuple。返回: 文本。异常: 无。"""
    if len(names) == 1:
        return names[0]
    middle = len(names) // 2
    return '(' + balanced(names[:middle]) + '+' + balanced(names[middle:]) + ')'


class ExpressionMetadataBudgetTests(unittest.TestCase):
    """将表达式结构深度与外部数据协议深度分开，验证费用和失败边界。"""

    def declarations(self, count=16):
        """创建同源数值声明。参数: 信号数。返回: 声明绑定。异常: 模型校验原错。"""
        clock = TimebaseSpec('analysis', TimeType.RELATIVE, 'metadata_test')
        signals = tuple(SignalDefinition('value' + str(index), 'source', 'v' + str(index), D.FLOAT64, '1', 10**9)
                        for index in range(count))
        return DeclarationBindings('session', clock, Interval(0, 10**9),
                                   (DeclaredSource('source', clock, 'synthetic'),), signals)

    def test_valid_left_associated_expression_and_balanced_result(self):
        """16路左结合加法可准备，所有1至16的输入得到136。参数: 无。返回: 无。异常: 断言。"""
        declarations = self.declarations()
        names = tuple(signal.name for signal in declarations.signals)
        left = validate_expression(' + '.join(names), declarations)
        with self.assertRaises(ResultFormatError):
            old_shallow_cost(left)
        for expression in (left, validate_expression(balanced(names), declarations)):
            self.assertGreater(history._metadata_bytes(expression), 0)
            for backend in ('reference', 'numpy'):
                with self.subTest(backend=backend, expression=expression.text):
                    budget = ResourceBudget()
                    state = LatestSignalState(budget, declarations.signals, 'session')
                    self.addCleanup(state.close)
                    driver = DriverExpression(expression, state, None, backend=backend)
                    self.addCleanup(driver.close)
                    state.apply(DecodedTimeGroup(0, tuple(make_sample(signal, 0, index, float(index + 1))
                                for index, signal in enumerate(declarations.signals))))
                    self.assertEqual(driver.evaluate()[1].value, 136.)
                    driver.close()
                    state.close()
                    self.assertEqual(budget.ram_bytes, 0)

    def test_shallow_expression_and_declaration_costs_unchanged(self):
        """浅树、字段默认引用和外层容器仍使用原费用。参数: 无。返回: 无。异常: 字节差异。"""
        declarations = self.declarations(2)
        expression = validate_expression('value0 + value1 * 2', declarations)
        for value in (expression.root, expression, declarations.signals,
                      {'config': (expression, declarations.signals)}, (expression.root, expression.root)):
            self.assertEqual(history._metadata_bytes(value), old_shallow_cost(value))

    def test_shared_subtree_keeps_each_reference_charge(self):
        """共享子树只遍历一次，重复槽仍全额计费。参数: 无。返回: 无。异常: 费用或重遍断言。"""
        leaf = ExprNode('name', D.FLOAT64, '1', 'verified', name='value0', aliases=('value0',))
        root = ExprNode('add', D.FLOAT64, '1', 'verified', args=(leaf, leaf), aliases=('value0',))
        counts = {}
        def sized(value):
            """记录表达式对象估算次数。参数: 元数据。返回: 原getsizeof。异常: 原结构错误。"""
            if type(value) is ExprNode:
                counts[id(value)] = counts.get(id(value), 0) + 1
            return getsizeof(value)
        with patch.object(history, 'getsizeof', sized):
            actual = history._metadata_bytes(root)
        self.assertEqual(actual, old_shallow_cost(root))
        self.assertEqual(counts, {id(root): 1, id(leaf): 1})

    def test_unknown_metadata_depth_and_types_stay_rejected(self):
        """普通32层边界不随表达式放宽，未知对象仍拒绝。参数: 无。返回: 无。异常: 断言。"""
        value = 'leaf'
        for _ in range(32):
            value = (value,)
        self.assertEqual(history._metadata_bytes(value), old_shallow_cost(value))
        with self.assertRaises(ResultFormatError):
            history._metadata_bytes((value,))
        with self.assertRaises(ResultFormatError):
            history._metadata_bytes(object())
        bad = ExprNode('name', D.FLOAT64, '1', 'verified', args=(object(),))
        with self.assertRaises(ResultFormatError):
            history._metadata_bytes(bad)
        bad = ExprNode('const', D.FLOAT64, '1', 'verified', value=value)
        with self.assertRaises(ResultFormatError):
            history._metadata_bytes(bad)

    def test_cycles_in_metadata_and_expression_are_rejected(self):
        """普通容器、表达式子图及跨字段回环均终止为格式错误。参数: 无。返回: 无。异常: 断言。"""
        mapping = {}
        mapping['self'] = mapping
        with self.assertRaisesRegex(ResultFormatError, '循环引用'):
            history._metadata_bytes(mapping)
        root = ExprNode('add', D.FLOAT64, '1', 'verified')
        object.__setattr__(root, 'args', (root,))
        with self.assertRaisesRegex(ResultFormatError, '循环引用'):
            history._metadata_bytes(root)
        root = ExprNode('const', D.FLOAT64, '1', 'verified')
        object.__setattr__(root, 'value', {'root': root})
        with self.assertRaisesRegex(ResultFormatError, '循环引用'):
            history._metadata_bytes(root)
