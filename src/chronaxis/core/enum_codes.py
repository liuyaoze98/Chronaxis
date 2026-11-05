"""在 v4 表达式中读取按需保留的枚举原始整数列，标签索引没有原码含义。"""

from .numeric import INTEGER_BOUNDS, ScalarValue
from .types import QualityFlag as Q, SignalDType as D
from math import isfinite


def validate_code_dtype(dtype, choices):
    """检查声明的整数存储类型及其可表示的 choices 键。

    参数: dtype 为 INT64 或 UINT64，choices 为原代码到逻辑标签的映射对。
    返回: None。异常: ValueError 为非整数类型、非整数键或定宽范围不符。
    同一标签可由多个不同代码表示，此处不反向查找标签。
    """
    if dtype not in (D.INT64, D.UINT64):
        raise ValueError('枚举 code_dtype 必须是 int64 或 uint64')
    lower, upper = INTEGER_BOUNDS[dtype]
    if any(type(code) is not int or not lower <= code <= upper for code, _ in choices):
        raise ValueError('枚举 choices 原码必须是 code_dtype 可表示的整数')


def compile_enum_code(compiler, call):
    """从已编译的枚举来源取得原码 dtype 并登记本节点的真实依赖。

    参数: compiler 为 v4 编译器，call 为 enum_code 的 AST 调用。
    返回: 输出单位 1 的整数节点。异常: 参数数量、来源或原码类型不明时报编译错误。
    """
    from .expression import _node
    if len(call.args) != 1 or call.keywords:
        compiler._error(call, 'enum_code 需要一个枚举信号参数')
    operand = compiler.visit(call.args[0])
    if operand.operator != 'name' or operand.dtype is not D.ENUM:
        compiler._error(call, 'enum_code 需要来自声明信号的枚举值')
    dtype = compiler.signals[operand.name].code_dtype
    if dtype is None:
        compiler._error(call, 'enum_code 需要已核实的整数原码类型，请声明 code_dtype: int64 或 uint64')
    return _node('enum_code', dtype, '1', (operand,))


def code_dependencies(root):
    """收集参与本次计算或其派生子树的枚举原码，忽略单纯使用标签的名称。

    参数: root 为已编译表达式根。返回: 需要同时读取原码的别名集合。
    异常: 输入不是表达式节点时传播属性错误。
    """
    found, seen, pending = set(), set(), [root]
    while pending:
        node = pending.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        if node.operator == 'enum_code':
            found.add(node.args[0].name)
        pending.extend(node.args)
    return frozenset(found)


def original_code(definition, original, quality=Q.NONE):
    """把已解码原整数装入声明的定宽类型，不经标签或浮点中转。

    参数: definition 为有 code_dtype 的枚举，original 为映射前原值，quality 为来源质量。
    返回: 整数 ScalarValue。异常: 缺少有效类型声明时报错。未知映射不使整数本身无效。
    """
    dtype = definition.code_dtype
    lower, upper = INTEGER_BOUNDS[dtype]
    if quality == Q.NONE:
        if original is None:
            quality = Q.MISSING
        elif type(original) is float and not isfinite(original):
            quality = Q.NONFINITE
        elif type(original) is not int:
            quality = Q.DECODE_ERROR
        elif not lower <= original <= upper:
            quality = Q.OVERFLOW
        elif any(type(value) is int and value == original for value in definition.invalid_values):
            quality = Q.OUT_OF_RANGE
    return ScalarValue(original if not quality else None, dtype, not quality, quality)


def code_column(definition, originals):
    """按原生输入类型装箱有限原码批；未请求不分配列。

    参数: definition 为运行投影，originals 为映射前异构 Python 输入。
    返回: None 或只读的定宽整数 NumericArray。异常: 声明或输入违反模型时传播。
    """
    if not definition.capture_code:
        return None
    import numpy as np
    from .numeric_numpy import NumericArray, DTYPES
    values = np.zeros(len(originals), dtype=DTYPES[definition.code_dtype])
    quality = np.zeros(len(originals), dtype=np.uint16)
    for index, original in enumerate(originals):
        code = original_code(definition, original)
        if code.valid:
            values[index] = code.value
        quality[index] = int(code.quality)
    return NumericArray(definition.code_dtype, values, quality == 0, quality)


def memory_histories(compiled, names, factory, condition=None):
    """只为实际消费码视图的表达式建立附原码的历史。

    参数: compiled/condition 为值和可选条件，names 为实际联合依赖，factory 为独立后端。
    返回: 名称到 SignalSeries 的映射。异常: 原输入转换或绑定错误直接传播。
    """
    required = code_dependencies(compiled.root)
    if condition is not None:
        required |= code_dependencies(condition.root)
    return {name: factory(compiled.bindings, name, capture_code=name in required) for name in names}


def aligned_scalar(definition, state):
    """恢复对齐点的标签和独立原码，过期和域外状态同时作用于两者。

    参数: definition 为信号声明，state 为参考保持结果。
    返回: ScalarValue。异常: 质量或输入布局非法时传播。
    """
    labels = tuple(dict.fromkeys(label for _, label in definition.choices)) if definition.dtype is D.ENUM else ()
    code = state.sample.code if state.sample is not None else None
    boundary = state.quality & (Q.MISSING | Q.STALE)
    if code is not None and boundary:
        code = ScalarValue(None, code.dtype, False, code.quality | boundary)
    return ScalarValue(state.value, definition.dtype, state.valid, state.quality, labels, code)


def expire_value(value, reason):
    """把同一观测边界分别施加到值及附带原码，各自保留独立质量。

    参数: value 为保存的最新值，reason 为本次缺观测或过期原因。
    返回: 当前时刻无效的 ScalarValue。异常: 错误 dtype 或质量组合由模型拒绝。
    """
    code = value.code
    if code is not None:
        code = ScalarValue(None, code.dtype, False, code.quality | reason)
    return ScalarValue(None, value.dtype, False, value.quality | reason, value.labels, code)


def aligned_column(state):
    """使用数组保持的相同样本索引同步原码及其自身质量。

    参数: state 为 AlignedArray。返回: NumericArray；标签单独使用时不分配码列。
    异常: 不一致的历史布局或整数存储错误。
    """
    import numpy as np
    from .numeric_numpy import DTYPES, NumericArray
    history = state.history
    samples = history.series.samples
    definition = history.series.bindings.resolve(history.series.name)
    code = None
    if samples and samples[0].code is not None:
        dtype = definition.code_dtype
        source = np.asarray([s.code.value if s.code.valid else 0 for s in samples], dtype=DTYPES[dtype])
        reasons = np.asarray([int(s.code.quality) for s in samples], dtype=np.uint16)
        present = state.sample_indices >= 0
        values = np.zeros(state.values.shape, dtype=DTYPES[dtype])
        quality = state.quality & int(Q.MISSING | Q.STALE)
        indices = state.sample_indices[present]
        values[present] = source[indices]
        quality[present] |= reasons[indices]
        code = NumericArray(dtype, values, quality == 0, quality)
    return NumericArray(definition.dtype, state.values, state.valid, state.quality, history.labels, code)


def history_code(definition, sample):
    """读取历史中单独保存的原码，从原数据重查标签映射无关的质量。

    参数: definition 为枚举声明，sample 为原历史观测，None 表示从未观测。
    返回: 原码 ScalarValue。异常: 缺少必要历史投影时明确失败。
    """
    if sample is None:
        return ScalarValue(None, definition.code_dtype, False, Q.MISSING)
    if sample.value.code is not None:
        return sample.value.code
    if not sample.original_present:
        raise ValueError('enum_code 需要回读时保留枚举原始整数')
    quality = sample.value.quality
    if sample.original_value is not None:
        quality &= ~Q.OUT_OF_RANGE
    return original_code(definition, sample.original_value, quality)


def historical_column(definition, arrays):
    """沿历史保持的有样本掩码及时间质量构建请求的原码列。

    参数: definition 为枚举声明，arrays 为同一历史快照的有限保持批。
    返回: 与该批同长的整数 NumericArray。异常: 缺少原码投影或布局错误。
    """
    import numpy as np
    from .numeric_numpy import NumericArray, DTYPES
    code = history_code(definition, arrays.sample)
    quality = arrays.quality & int(Q.MISSING | Q.STALE)
    quality[arrays.has_sample] |= int(code.quality)
    values = np.full(arrays.values.shape, code.value if code.valid else 0, dtype=DTYPES[code.dtype])
    return NumericArray(code.dtype, values, quality == 0, quality)


def enum_code_reference(node, operand):
    """读取一条原码及其独立质量，保持有效的未映射代码。

    参数: node 为已检查的 enum_code 节点，operand 为对应 ENUM 的 ScalarValue。
    返回: 整数 ScalarValue。异常: 已有观测却缺原码投影或类型不一致时报错。
    """
    if operand.code is not None and operand.code.dtype is node.dtype:
        return operand.code
    if operand.code is None and operand.quality & (Q.MISSING | Q.STALE):
        return ScalarValue(None, node.dtype, False, operand.quality)
    raise ValueError('枚举缺少与声明一致的原码投影，无法从标签还原代码')


def enum_code_numpy(node, operand):
    """读取当前批的原码列及独立有效性，原码与枚举有效性分别判断。

    参数: node 为已检查的 enum_code 节点，operand 为形状 (N,) 的 ENUM 列。
    返回: 同形状整数 NumericArray。异常: 有观测而原码投影缺失或类型错误时报错。
    """
    import numpy as np
    from .numeric_numpy import NumericArray, DTYPES
    if operand.code is not None and operand.code.dtype is node.dtype:
        return operand.code
    if operand.code is None and np.all((operand.quality & int(Q.MISSING | Q.STALE)) != 0):
        return NumericArray(node.dtype, np.zeros(len(operand.values), dtype=DTYPES[node.dtype]),
                            operand.valid, operand.quality)
    raise ValueError('枚举缺少与声明一致的原码投影，无法从标签还原代码')
