"""将版本4整数编码、位选取和显式数值类型转换编译为冻结节点。

mod及位操作在单位为1的64位整数域工作，位号在编译时校验并固化。
显式cast先确定输入的物理尺度，再选择结果dtype。编译只访问声明与纯常量，
逐点的溢出、域错误和精度失败交给各自的参考/数组内核处理。
"""

from dataclasses import replace
from . import unit_registry as units
from .expression import _node, ExprNode, contains_host_call
from .expression_math_v4 import check_integer_leaves
from .numeric import INTEGER_BOUNDS
from .types import SignalDType as D


CAST_TYPES = {'to_int64': D.INT64, 'to_uint64': D.UINT64, 'to_float64': D.FLOAT64}
INTEGER_KERNELS = frozenset(('mod', 'bit_test', 'bit_extract', 'to_int64', 'to_uint64'))
INTEGER_FUNCTIONS = INTEGER_KERNELS | {'to_float64'}  # 浮点目标复用现有精确to_float核。


def _require_word(compiler, child, call):
    """核对64位整数及数值尺度1，可接受等价的无量纲单位表达式。

    参数: compiler为本次编译器，child为数值节点，call定位错误。
    返回: None。异常: ValueError为非整数、未知单位、带物理单位或非1倍率。
    """
    unit = units.resolve_unit(child.unit)
    one = units.resolve_unit('1')
    if (child.dtype not in INTEGER_BOUNDS or unit is None or unit.kind != one.kind
            or unit.scale != one.scale or unit.offset != one.offset):
        compiler._error(call, 'mod与位操作只接受单位1的int64或uint64；请显式转换数值和类型')


def _bit_parameter(compiler, child, call):
    """读取可在编译期确定的无量纲整数，位置与宽度边界由调用处统一判定。

    参数: compiler为本次编译器，child为位号或宽度节点，call定位错误。
    返回: 原生int。异常: ValueError为依赖运行数据或静态数值本身无效。
    """
    _require_word(compiler, child, call)
    if child.aliases or contains_host_call(child):
        compiler._error(call, '位号、起点与宽度必须是编译期整数')
    # 配置字面量及无依赖表达式按同一数值协议检查，不执行任意Python。
    from .expression_reference import _evaluate
    value = _evaluate(child, {}, {}).value
    if not value.valid:
        compiler._error(call, '位参数没有有效的编译期整数值')
    return value.value


def compile_integer(compiler, call):
    """编译mod、位操作或精确cast，冻结整数策略与编译期位参数。

    参数: compiler为v4编译器，call为已登记名称的裸调用AST。
    返回: ExprNode；cast结果按所选尺度保持目标dtype，位索引不构造运行列。
    异常: ValueError为签名、输入类型/单位、位参数、常量越界或隐式混合定宽。
    """
    name = call.func.id
    arity = 1 if name in CAST_TYPES else 3 if name == 'bit_extract' else 2
    if name not in INTEGER_FUNCTIONS or len(call.args) != arity or call.keywords:
        compiler._error(call, f'{name}需要{arity}个位置参数')
    args = tuple(compiler.visit(arg) for arg in call.args)
    check_integer_leaves(compiler, args, call)
    child = args[0]
    if name in CAST_TYPES:
        if child.dtype not in (*INTEGER_BOUNDS, D.FLOAT64):
            compiler._error(call, '显式数值类型转换只接受数值，枚举需先用enum_code')
        # 1500mV的信号默认对应1.5V，转int不能截断；先显式to_unit(x,"mV")
        # 时输入尺度是mV，转int得到1500mV。外层不能再把它当作裸字面量重写。
        if not child.unit_explicit:
            child = compiler._canonical(child, call)
        op = 'to_float' if name == 'to_float64' else name
        result = _node(op, CAST_TYPES[name], child.unit, (child,), unit_explicit=child.unit_explicit)
        return compiler._known_node(replace(result, constant=False, typed_constant=False, conversion_promoted=False))
    _require_word(compiler, child, call)
    if name == 'mod':
        right = args[1]
        _require_word(compiler, right, call)
        # 两个纯整数字面量无信号锚点，按能容纳正大数的共同定宽适配；
        # 两个不同定宽的信号不能自动升为float，用户须先明确目标类型。
        if all(arg.constant or arg.typed_constant for arg in args):
            dtype = D.UINT64 if any(arg.dtype is D.UINT64 for arg in args) else D.INT64
            anchor = ExprNode('const', dtype, '1', 'verified', value=0, constant=True)
            child, right = (compiler._context(arg, anchor, call, arithmetic=True) for arg in args)
        else:
            child = compiler._context(child, right, call, arithmetic=True)
            right = compiler._context(right, child, call, arithmetic=True)
        if child.dtype is not right.dtype:
            compiler._error(call, 'mod的int64/uint64输入须先显式转换到同一整数类型')
        return compiler._known_node(_node('mod', child.dtype, '1', (child, right)))
    # 位0是最低位。start=0,width=64允许取得完整补码；任何移位的起点最多63。
    start = _bit_parameter(compiler, args[1], call)
    width = 1 if name == 'bit_test' else _bit_parameter(compiler, args[2], call)
    if not (0 <= start < 64 and 1 <= width <= 64 - start):
        compiler._error(call, '位号须在0到63之间，宽度须为正且起点加宽度不超过64')
    result = _node(name, D.BOOL if name == 'bit_test' else D.UINT64, '1', (child,), value=(start, width))
    return compiler._known_node(replace(result, constant=False, typed_constant=False, conversion_promoted=False))
