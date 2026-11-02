"""用独立标量计算求值表达式，并保留未知结果的原因。

evaluate_reference接收当前CompiledExpression、真实普通或消息绑定和context。
context按依赖别名提供ScalarValue，输出Evaluation，分别保存计算结果和
全部被求值依赖的质量原因。evaluate_memory_reference还可从已有内存行
提取信号，经参考转换和按时间保持后，在给定纳秒坐标逐点求值。

布尔表达式使用TRUE、FALSE、UNKNOWN（未知）三种状态。例如FALSE and
UNKNOWN可确定为FALSE，TRUE or UNKNOWN可确定为TRUE；被遮蔽的异常
仍保留在dependency_quality中。isclose按abs(a-b) <= atol + rtol*abs(b)
计算，两种容差均由表达式显式提供，非有限中间值不能变成正常判断。

只依赖标准库和参考数值、对齐模块，不执行任意Python代码，也不读取
旧日志或额外解码。当前求值缓存不跨时间点保留，不调用NumPy数值内核。
"""

# 冻结结果保证逻辑质量与诊断质量清楚分离。
from dataclasses import dataclass
# context只接受真实映射，不反射对象属性。
from collections.abc import Mapping
# 用静态编译模型和当前真实绑定校验身份。
from .expression import CompiledExpression
# 已校验输入绑定不能用用户字符串冒充。
from .binding import SignalBindings
# 解码绑定由实际历史核对工厂生成；本入口不创建伪造内存来源。
from .decoded_binding import DecodedBindings
# 消息仓使用独立绑定；只接受其显式context，不引入时间保持或原历史。
from .message_binding import MessageBindings
# 独立参考数值内核，内部比较映射只有标准运算。
from .numeric import (COMPARE_FUNCTIONS, ScalarValue, binary_reference, memory_series_reference,
                      to_float_reference, unary_reference)
# 独立参考保持为memory查询生成输入。
from .state import align_reference
# 三值使用BOOL的valid，不将UNKNOWN默认转False。
from .types import QualityFlag as Q, SignalDType as D


@dataclass(frozen=True)
class Evaluation:
    """分别保存可用的计算结果，以及本次求值的全部质量诊断。

    value是ScalarValue，其quality表示结果本身不可用的原因。
    dependency_quality另存依赖和计算的原因并集；即使已知FALSE或TRUE使
    布尔结果可以确定，原来的异常也仍可追溯，不能强塞回正常结果的quality。
    实例不可重新赋值，不保存下一个时间点的信号状态。
    """

    value: ScalarValue  # 实际逻辑输出。
    dependency_quality: Q  # 原依赖/本次计算的全部诊断并集。


def require_context(compiled, context, bindings):
    """核对表达式的输入身份和调用者提供的依赖名称。

    参数:
        compiled: 可执行CompiledExpression；context为真实映射对象。
        bindings: 当前SignalBindings、DecodedBindings或MessageBindings，须与编译身份一致。
    返回:
        None。context的键必须恰好等于dependencies，纯常量表达式需空映射。
    异常:
        TypeError: 计划、映射或绑定模型类型不合法。
        ValueError: 绑定身份不同，或依赖键缺失、多余。
    边界:
        只校验结构，不读来源、不求值；各个值的类型由后续执行入口检查。
    """
    # 执行不能仅凭表达式文本或语义名复用旧绑定。
    if (not isinstance(compiled, CompiledExpression) or not isinstance(bindings, (SignalBindings, DecodedBindings, MessageBindings))
            or not isinstance(compiled.bindings, (SignalBindings, DecodedBindings, MessageBindings)) or not isinstance(context, Mapping)):
        # 不把接口配置错吞为UNKNOWN。
        raise TypeError('执行需要CompiledExpression/context及真实普通或消息绑定')
    # 相同结构名称不证明输入数据/转换/TTL相同。
    if compiled.bindings.identity != bindings.identity:
        # 必须重新编译真实当前绑定。
        raise ValueError('可执行表达式与当前输入绑定身份不同')
    # 普通解码核实际投影，消息绑定核单来源依赖；两者均拒绝静态声明冒充运行域。
    if isinstance(bindings, (DecodedBindings, MessageBindings)):
        bindings.require_synchronized(compiled.dependencies)
    # 禁止缺列/错误列映射/隐式全局取值。
    if set(context) != set(compiled.dependencies):
        # 常量表达式context为空，不猜未提供信号。
        raise ValueError('context必须精确提供表达式dependencies')


def _logic(operator, values):
    """独立标量三值and/or/not，不以UNKNOWN当False。

    参数: operator固定逻辑名，values为BOOL ScalarValue tuple。
    返回: ScalarValue；正常决断quality NONE，未知保留原因并集。
    异常: 调用侧静态类型保证，不接数值truthiness。
    """
    # not对未知仍保持原原因。
    if operator == 'not':
        # known TRUE/FALSE取反，不使用Truth.__bool__。
        return ScalarValue(not values[0].value, D.BOOL) if values[0].valid else ScalarValue(None, D.BOOL, False, values[0].quality)
    # 所有原因仍在外层Evaluation诊断保存。
    quality = Q.NONE
    # 标量参考逐逻辑值判断，允许独立状态循环。
    for value in values:
        # 同一操作原始原因不丢失。
        quality |= value.quality
    # 对称规则：任一已知False决定and，已知True决定or。
    deciding = False if operator == 'and' else True
    # invalid数值占位不参与判断，不能False-like导致决断。
    if any(value.valid and value.value is deciding for value in values):
        # 结果已知，原异常仍由外层依赖诊断保存。
        return ScalarValue(deciding, D.BOOL)
    # 没有决断值且有unknown，结果仍未知。
    if quality != Q.NONE:
        # 保留真实未知原因而非一律MISSING。
        return ScalarValue(None, D.BOOL, False, quality)
    # 所有已知：and全部TRUE，or全部FALSE。
    return ScalarValue(not deciding, D.BOOL)


def _evaluate(node, context, cache):
    """用独立参考数值解释单个冻结节点及局部公共子树。

    参数: node静态树；context当前typed值；cache仅本次point局部缓存。
    返回: Evaluation，完整诊断与逻辑有效性分开。
    异常: 静态模型/类型错误直接传播，不eval或吞配置异常。
    """
    # 公共表达式复用只限同一点/当前真实输入。
    if node in cache:
        # 不跨point继承旧信号值。
        return cache[node]
    # 常量字面量已由编译器完成上下文dtype/域检查。
    if node.operator == 'const':
        # dtype/labels构造不能任意隐式转值。
        value = ScalarValue(node.value, node.dtype, labels=node.labels)
        # literal没有原信号异常。
        result = Evaluation(value, Q.NONE)
    # 只使用当前显式context的简单名称。
    elif node.operator == 'name':
        # 输入包装身份与dtype由外层入口校验。
        value = context[node.name]
        # 上游全部质量同时作为诊断保留。
        result = Evaluation(value, value.quality)
    else:
        # 子树全部求值以保留原依赖异常，即使逻辑已可决断。
        children = tuple(_evaluate(arg, context, cache) for arg in node.args)
        # 当前节点可用逻辑结果，不是原诊断值。
        values = tuple(child.value for child in children)
        # 诊断汇总包括已被已知逻辑结果遮蔽的异常。
        diagnostic = Q.NONE
        # 此为独立标量参考循环，不共享数组归约内核。
        for child in children:
            # 原因并集不会被normal BOOL清除。
            diagnostic |= child.dependency_quality
        # 三值逻辑独立于数值质量门槛。
        if node.operator in ('and', 'or', 'not'):
            # FALSE and UNKNOWN与TRUE or UNKNOWN都可确定结果，diagnostic仍保存原原因。
            value = _logic(node.operator, values)
        # 数值单目用已验收的独立参考函数。
        elif node.operator in ('abs', 'neg'):
            # int64 min依然严格OVERFLOW。
            value = unary_reference(node.operator, values[0])
        # float信号上下文中的整数literal显式精度检查。
        elif node.operator == 'to_float':
            # 不能通过编译隐藏舍入整数。
            value = to_float_reference(values[0])
        # 精确整数比较literal可以超过64位边界。
        elif node.operator.startswith('int_literal_'):
            # Python整数参考绝不先转float。
            value = ScalarValue(COMPARE_FUNCTIONS[node.operator[12:]](values[0].value, node.value), D.BOOL) if values[0].valid else ScalarValue(None, D.BOOL, False, values[0].quality)
        # isclose严格按明确非对称判据，拒绝默认容差。
        elif node.operator == 'isclose':
            # 四个数值都经各自严格float精度检查。
            a, b, atol, rtol = (to_float_reference(item) for item in values)
            # 判据abs(a-b)，非有限中间值仍显式UNKNOWN。
            distance = unary_reference('abs', binary_reference('sub', a, b))
            # 右边rtol*abs(b)的参考IEEE路径。
            relative = binary_reference('mul', rtol, unary_reference('abs', b))
            # atol与relative依旧用明确数值质量规则。
            tolerance = binary_reference('add', atol, relative)
            # 不把非有限容差当无穷阈值正常通过。
            value = binary_reference('le', distance, tolerance)
            # 当前中间数值原因也纳入原依赖诊断。
            diagnostic |= a.quality | b.quality | atol.quality | rtol.quality | distance.quality | tolerance.quality
        else:
            # 编译树只包含注册二元数值/比较，不执行自由函数。
            value = binary_reference(node.operator, values[0], values[1], allow_float_literal=node.allow_float_literal)
        # 结果原因是诊断子集，known决断不丢所有依赖质量。
        result = Evaluation(value, diagnostic | value.quality)
    # 仅当前point的公共子树值可以复用。
    cache[node] = result
    # 冻结结果不持有跨调用可变状态。
    return result


def evaluate_reference(compiled: CompiledExpression, context: Mapping, bindings: SignalBindings | DecodedBindings | MessageBindings) -> Evaluation:
    """检查当前标量输入后，对表达式进行一次独立参考求值。

    参数:
        compiled: 当前CompiledExpression；bindings为对应的普通或MessageBindings运行绑定。
        context: 以精确依赖别名为键的ScalarValue映射，声明类型与枚举域须匹配。
    返回:
        Evaluation，区分正常或未知的计算结果，并保留所有依赖的质量诊断。
    异常:
        TypeError、ValueError: 依赖键、模型、类型、枚举域或绑定身份不合法。
        数值计算失败写入质量原因，不把配置错误当作缺失数据。
    边界:
        每次调用使用新缓存，只复用本次求值中的公共子树，不继承上一次的值。
    """
    # 静态执行身份和列映射须执行前成立。
    require_context(compiled, context, bindings)
    # 校验真实当前dtype和枚举域，不能只靠上下文名字。
    for name, value in context.items():
        # 冻结定义来自当前真实绑定。
        definition = bindings.resolve(name)
        # 只有typed标量可执行，不把裸float当信号。
        if not isinstance(value, ScalarValue) or value.dtype is not definition.dtype:
            # 输入类型冲突不是样本缺失。
            raise TypeError('context值与当前signal dtype不一致')
        # enum域需与真实映射一致。
        labels = tuple(dict.fromkeys(item for _, item in definition.choices)) if definition.dtype is D.ENUM else ()
        # 不让不同任务同名code域串入。
        if value.labels != labels:
            # 命名一致不证明语义域一致。
            raise ValueError('context enum域与绑定不同')
    # 每个时间点都创建新缓存，避免沿用上个时间点的信号值。
    return _evaluate(compiled.root, context, {})


def evaluate_memory_reference(compiled: CompiledExpression, times: tuple[int, ...], *, point: bool = False) -> tuple[Evaluation, ...]:
    """从已有内存行取得信号，在指定纳秒坐标逐点计算表达式。

    参数:
        compiled: 关联真实内存输入的CompiledExpression。
        times: 非递减的整数纳秒元组；point控制真实末点查询视图。
    返回:
        与times等长的Evaluation元组，保存正常值、未知状态和依赖诊断。
    异常:
        TypeError: 非memory绑定，包括DecodedBindings；其他时间/来源/配置异常原样传播。
    边界:
        只提取实际依赖，先归一化再按有效期保持；纯常量也检查时间轴。
        为完整内存历史建立新对象，不读取文件、额外解码或修改原行。
    """
    # 纯常量也须明确拒绝解码绑定，不能借空依赖意外进入memory快捷路径。
    if not isinstance(compiled, CompiledExpression) or not isinstance(compiled.bindings, SignalBindings):
        raise TypeError('memory快捷求值需要真实SignalBindings的CompiledExpression')
    # 仅材料化当前实际依赖，不改变旧链筛选或扫描次数。
    histories = {name: memory_series_reference(compiled.bindings, name) for name in compiled.dependencies}
    # 参考保持与数组查询实现独立。
    aligned = {name: align_reference(series, times, point=point) for name, series in histories.items()}
    # 当前memory空依赖也需严格校验时间/视图接口。
    if not histories:
        # 常量没有来源，时间轴依旧遵守typed ns协议。
        from ..timebase.conversion import require_int64_ns
        # 不能将自由序列或int truthiness解释成合法时间轴。
        if not isinstance(times, tuple) or type(point) is not bool:
            # 同参考保持输入结构要求。
            raise TypeError('times需tuple且point需bool')
        # 每个坐标仍必须合法定宽且不回退。
        for index, time in enumerate(times):
            # 精确整数时间不经float转换。
            require_int64_ns(time, 'time_ns')
            # 不排序用户输入掩盖异常。
            if index and time < times[index-1]:
                # 空依赖也不是时间回退豁免。
                raise ValueError('时间轴回退')
    # 当前点只使用已对齐的真实结果，invalid原值保留。
    results = []
    # 标量参考允许逐时间解释，不冒充数组化。
    for index in range(len(times)):
        # 当前局部context不跨时间保存数值。
        context = {name: ScalarValue(states[index].value, compiled.bindings.resolve(name).dtype, states[index].valid, states[index].quality,
                                     tuple(dict.fromkeys(label for _, label in compiled.bindings.resolve(name).choices)) if compiled.bindings.resolve(name).dtype is D.ENUM else ())
                   for name, states in aligned.items()}
        # 完整绑定身份再次门槛校验后运行真实参考。
        results.append(evaluate_reference(compiled, context, compiled.bindings))
    # 返回不可变结果，不持有全局任务状态。
    return tuple(results)
