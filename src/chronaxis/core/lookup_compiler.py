"""将 v4 lookup 的固定签名和表名引用编译为单输入节点。

输入只接受表达式 AST 和当前有身份的绑定。先校验关键字、单位与类型，
随后准备引用表的只读列；不访问其他配置或数据来源。
"""

import ast
from dataclasses import replace
from .expression import _node
from .types import SignalDType as D
from .unit_registry import output_label, resolve_unit


def compile_lookup(compiler, node):
    """编译查表调用。参数: v4 编译器和调用 AST。返回: 有单位的节点。异常: 签名、表名、类型或单位错。"""
    if len(node.args) != 2:
        compiler._error(node, 'lookup需要两个位置参数：数值和表名字面量')
    name = node.args[1]
    if not isinstance(name, ast.Constant) or type(name.value) is not str:
        compiler._error(name, 'lookup表名须为字符串字面量')
    table = next((item for item in compiler.bindings.lookups if item.name == name.value), None)
    if table is None:
        compiler._error(name, f'未声明的lookup表：{name.value}')
    options = {}
    for keyword in node.keywords:
        if keyword.arg not in ('mode', 'bounds') or keyword.arg in options:
            compiler._error(keyword.value, 'lookup仅接受不重复的mode/bounds关键字')
        if not isinstance(keyword.value, ast.Constant) or type(keyword.value.value) is not str:
            compiler._error(keyword.value, 'lookup选项须为字符串字面量')
        options[keyword.arg] = keyword.value.value
    child = compiler.visit(node.args[0])
    if child.dtype not in (D.INT64, D.UINT64, D.FLOAT64):
        compiler._error(node.args[0], 'lookup仅接受数值输入')
    # 唯一尺度锚点为表轴。裸数按该声明单位解释，quantity 常量保留其原单位再换算。
    if child.constant and child.unit == '1' and not child.unit_explicit and not child.typed_constant:
        child = replace(child, unit=table.input_unit)
    child = compiler._convert(child, table.input_unit, node)
    from .expression_math_v4 import check_integer_leaves
    check_integer_leaves(compiler, (child,), node)
    try:
        prepared = table.prepare(options.get('mode', 'linear'), options.get('bounds', 'invalid'))
    except ValueError as error:
        compiler._error(node, str(error))
    label = output_label(resolve_unit(table.unit), table.unit)
    # 即便输入为裸常量，结果也有表声明的独立单位，不得在外围算术中重新解释。
    result = compiler._known_node(_node('lookup', prepared.dtype, label, (child,), value=prepared))
    return replace(result, constant=False, typed_constant=child.constant or child.typed_constant, unit_explicit=True)
