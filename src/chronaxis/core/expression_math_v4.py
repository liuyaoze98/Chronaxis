"""编译版本4的逐点极值、限幅、平方和开方表达式。

输入是白名单调用AST及本次编译器，输出是显式标记单位、dtype与依赖的
冻结节点。先检查完整输入，再按所有参数的原始声明尺度解释裸常量，
最后确定公共数值表示。仅对不依赖样本的clip边界执行静态判序。
"""

from dataclasses import replace
from . import unit_registry as units
from .expression import ExprNode, _node, contains_host_call
from .numeric import INTEGER_BOUNDS
from .types import SignalDType as D


MATH_KERNELS = frozenset(('minimum', 'maximum', 'clip', 'sqrt'))
MATH_FUNCTIONS = MATH_KERNELS | {'square'}  # square展开成已有的定宽乘法。


def _common_unit(compiler, args, call):
    """将同量种的多个数值放到共同尺度，在换算前确定裸数字单位。

    参数: compiler为v4编译器，args为数值节点，call用于错误定位。
    返回: 同单位节点tuple，已知单位取规范基准，未知同名保留原标签。
    异常: ValueError为量种不兼容、未知单位异名或裸数字有多种尺度解释。
    """
    # 不把尚无单位的裸常量本身当成单位依据；quantity及消息参数自带声明。
    anchors = [arg for arg in args if not arg.constant]
    if not anchors:
        return args
    first = anchors[0]
    origin = units.resolve_unit(first.unit)
    target = units.canonical_unit(origin).symbol if origin is not None else first.unit
    has_bare = len(anchors) != len(args)
    for arg in anchors[1:]:
        # 检查所有有单位输入，交换参数不能改变兼容与否或裸数字的物理含义。
        other = units.resolve_unit(arg.unit)
        if origin is None or other is None:
            if arg.unit != first.unit:
                compiler._error(call, '不同的未知单位不能自动比较')
            continue
        try:
            units.conversion(origin, other)
        except ValueError as error:
            compiler._error(call, str(error))
        if has_bare and (other.scale, other.offset) != (origin.scale, origin.offset):
            compiler._error(call, '裸数值存在多个声明尺度，请使用quantity指定单位')
    # 所有锚点的尺度已相同，或没有裸常量；已知量种选择的目标与参数顺序无关。
    annotated = (replace(arg, unit=first.unit, unit_status=first.unit_status) if arg.constant else arg
                 for arg in args)
    return tuple(compiler._convert(arg, target, call) for arg in annotated)


def _common_dtype(compiler, args, call):
    """对称选定可用于极值和限幅的公共dtype，明确记录必要的精确提升。

    参数: compiler为v4编译器，args已统一单位，call用于错误定位。
    返回: 逐一适配后的节点tuple；所有节点dtype相同。
    异常: ValueError为原信号类型冲突、定宽字面量越界或不允许的提升。
    """
    # 原信号之间若已经不兼容，不能借第三个浮点字面量隐式重写其dtype。
    fixed_types = {arg.dtype for arg in args if not (arg.constant or arg.typed_constant
                   or (arg.conversion_promoted and arg.dtype is D.FLOAT64)
                   or (compiler.message_domain and not arg.aliases and arg.dtype is D.FLOAT64))}
    if len(fixed_types) > 1:
        compiler._error(call, '数值函数输入的信号dtype不兼容')
    if any(arg.dtype is D.FLOAT64 for arg in args):
        dtype = D.FLOAT64
    elif fixed_types:
        dtype = next(iter(fixed_types))
    else:
        dtype = D.UINT64 if any(arg.dtype is D.UINT64 for arg in args) else D.INT64
    # 先按字面量规则适配；只有浮点输出才需要对真实整数输入做精度检查。
    anchor = ExprNode('const', dtype, '1', 'verified', value=0, constant=True)
    result = []
    for arg in args:
        child = compiler._context(arg, anchor, call, arithmetic=True)
        if child.dtype is not dtype:
            if dtype is not D.FLOAT64:
                compiler._error(call, '数值函数输入无法使用共同的整数dtype')
            child = compiler._known_node(_node('to_float', D.FLOAT64, child.unit, (child,)))
        result.append(child)
    return tuple(result)


def check_integer_leaves(compiler, args, call):
    """检查实际需要定宽存储的叶节点，包括未选分支内的配置字面量。

    参数: compiler为v4编译器，args为要检查的表达式树，call用于定位。
    返回: None。异常: ValueError为叶节点定宽越界。
    """
    # 共享派生子树只访问一次。允许无界的纯整数比较阈值已编入专用节点字段。
    pending, seen = list(args), set()
    while pending:
        child = pending.pop()
        if id(child) in seen:
            continue
        seen.add(id(child))
        if (child.operator == 'const' and child.dtype in INTEGER_BOUNDS
                and not INTEGER_BOUNDS[child.dtype][0] <= child.value <= INTEGER_BOUNDS[child.dtype][1]):
            compiler._error(call, '数值函数输入的整数常量超出64位范围')
        pending.extend(child.args)


def compile_math(compiler, call):
    """为一个已注册的数学函数检查签名、单位、类型和静态边界。

    参数: compiler为版本4编译器，call为裸函数名调用AST。
    返回: ExprNode；平方直接复用经过定宽溢出检查的乘法节点。
    异常: ValueError为非法参数、越界常量、不可推导的单位或静态倒置边界。
    """
    name = call.func.id
    count = len(call.args)
    if name not in MATH_FUNCTIONS or call.keywords:
        compiler._error(call, '数学函数仅支持已登记名称与显式位置参数')
    if ((name in ('minimum', 'maximum') and count < 2) or (name == 'clip' and count != 3)
            or (name in ('sqrt', 'square') and count != 1)):
        compiler._error(call, f'{name}位置参数数量不正确')
    args = tuple(compiler.visit(arg) for arg in call.args)
    if any(arg.dtype not in (*INTEGER_BOUNDS, D.FLOAT64) for arg in args):
        compiler._error(call, f'{name}的全部参数必须为数值')
    check_integer_leaves(compiler, args, call)

    if name in ('square', 'sqrt'):
        # 必须先识别偏移温度，否则转成K后会绕过显式转换契约。
        child = args[0]
        unit = units.resolve_unit(child.unit)
        if unit is None or unit.offset:
            compiler._error(call, f'{name}需要已登记的无偏移单位，摄氏度须先显式转换为K')
        if name == 'square':
            return compiler._binary('mul', child, child, call)
        # mA*A先换成A²再开方，根号内倍率不必恰为有理数的平方。
        child = compiler._canonical(child, call)
        try:
            output = units.canonical_unit(units.square_root(units.canonical_unit(unit))).symbol
        except ValueError as error:
            compiler._error(call, str(error))
        return compiler._known_node(_node('sqrt', D.FLOAT64, output, (child,)))

    args = _common_dtype(compiler, _common_unit(compiler, args, call), call)
    if name == 'clip' and all(not a.aliases and not contains_host_call(a) for a in args[1:]):
        # 参数及字面量表达式在编译时已有值。只判定两个有效边界间可证明的倒置；
        # 数值错误（如除零）仍由原节点给出具体质量，不伪造成边界顺序错误。
        from .expression_reference import _evaluate
        cache = {}
        lower, upper = (_evaluate(bound, {}, cache).value for bound in args[1:])
        if lower.valid and upper.valid and lower.value > upper.value:
            compiler._error(call, 'clip的静态下界大于上界')
    return compiler._known_node(_node(name, args[0].dtype, args[0].unit, args))
