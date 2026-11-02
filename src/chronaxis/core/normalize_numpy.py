"""按信号声明转换一列原字段值，并保留有效性、质量和原来源身份。

直接入口输入SignalDefinition、同质的已解码原列及uint16上游质量，输出
NumericArray。执行额外线性转换、编码映射、无效值及业务范围检查，不重复
DBC已完成的缩放。整数仿射先用精确配置常量求合法输入区间，再用无符号
距离按列计算，避免定宽中间回绕，不使用object数组进行数值运算。
memory_series_numpy按原生类型分组装箱，批量转换后按原行顺序恢复样本。
Python逐行操作负责类型分组和身份还原，不执行逐样本数值参考计算。
本模块依赖NumPy和核心模型，不读取文件或旧来源，不修改调用方原列；
完整内存历史会分配与行数成比例的存储，不保证生产执行预算。
"""

# 配置常量的精确区间算法与列数值计算分开。
from math import ceil, floor, isfinite
# NumPy显式加载，承担真实typed列/ufunc与掩码计算。
import numpy as np

# 共享校验模型/布局；不导入参考normalize函数。
from .binding import SignalBindings, SignalDefinition
# 保留原样本来源与身份，不能重写原行。
from .models import SignalSample
# 仅共享dtype/定宽静态协议；数组路径不调用标量数值。
from .numeric import INTEGER_BOUNDS
# 实际独立数组入口/布局供列执行及测试对照。
from .numeric_numpy import DTYPES, NumericArray, _from_magnitude, _magnitude, _output, to_float_numpy
# 接入已校验保持模型，不改变原来源顺序。
from .state import SignalSeries
# 只读静态映射或显式质量/type枚举用于结构协议。
from .types import QualityFlag, SignalDType
# 时间offset使用已有精确整数加法协议。
from ..timebase.conversion import checked_add_ns


def _affine_integer(raw, selected, dtype, scale, offset):
    """用逆映射范围与幅度分段实现精确整数线性转换。

    参数: raw为int64/uint64列；selected为有效mask；dtype目标整数；
        scale/offset为任意精确Python整数配置常量。
    返回: 目标定宽列及OVERFLOW mask；允许中间数学值越界但最终值合法。
    异常: 调用侧校验类型，分配错误传播；不逐样本用Python算数。
    """
    # 目标上下界在精确Python配置域，不转float。
    lower, upper = INTEGER_BOUNDS[dtype]
    # 原输入只支持两种64位整数，边界来自真实物理类型。
    input_lower, input_upper = (-(2 ** 63), 2 ** 63 - 1) if raw.dtype == np.dtype('int64') else (0, 2 ** 64 - 1)
    # 输出同长目标列，invalid占位不正常使用。
    result = np.zeros(len(raw), dtype=DTYPES[dtype])
    # 零scale也是声明关系，但非法/非有限原输入早已被拒绝。
    if scale == 0:
        # 只有常数结果在目标范围内才正常。
        overflow = selected.copy() if not lower <= offset <= upper else np.zeros(len(raw), dtype=bool)
        # 合法结果为同一常量，不执行乘法。
        if lower <= offset <= upper:
            # target常量已证明可表示。
            result[selected] = offset
        # 上游原因不由占位污染。
        return result, overflow
    # 正scale和负scale分别求精确逆区间，向上取整使用ceil(n/d)=-floor(-n/d)。
    if scale > 0:
        # 求最小合法整数输入。
        lo = max(input_lower, -((-(lower - offset)) // scale))
        # 求最大合法整数输入。
        hi = min(input_upper, (upper - offset) // scale)
    else:
        # 负scale反转不等号，仍用精确配置整数。
        lo = max(input_lower, -((-(upper - offset)) // scale))
        # 最大合法输入对应目标下界。
        hi = min(input_upper, (lower - offset) // scale)
    # 不存在合法原整数时不能进行任何数值运算。
    if lo > hi:
        # 全部选中位置明确目标OVERFLOW。
        return result, selected.copy()
    # 逆区间已经与原dtype求交，比较常量可安全cast。
    accepted = selected & (raw >= raw.dtype.type(lo)) & (raw <= raw.dtype.type(hi))
    # 先标记不合法输入，不能先机器乘加再尝试检查。
    overflow = selected & ~accepted
    # 精确选取最小合法输入作为局部计算原点。
    base = lo * scale + offset
    # 子集所有距离非负且不超过原64位跨度。
    values = raw[accepted]
    # 到负pivot的距离用幅度相减或相加，不算signed x-lo。
    if lo < 0:
        # 此分支原输入一定signed。
        magnitude = _magnitude(values)
        # 负输入离pivot更近，幅度≤abs(pivot)。
        negative = values < 0
        # 距离为uint64，一维有效子集M。
        distance = np.empty(len(values), dtype=np.uint64)
        # abs(pivot)-abs(x)安全非负。
        distance[negative] = np.uint64(-lo) - magnitude[negative]
        # abs(pivot)+x≤uint64 max，已由原输入跨度证明。
        distance[~negative] = np.uint64(-lo) + magnitude[~negative]
    else:
        # 非负pivot意味着选中输入非负，可安全cast。
        distance = values.astype(np.uint64) - np.uint64(lo)
    # 如果系数超过uint64 max，逆区间最多一个输入，所有距离为0。
    if abs(scale) > 2 ** 64 - 1:
        # 无需cast巨大系数；静态范围已证明合法结果都是base。
        result[accepted] = base
        # 正常结果完全精确。
        return result, overflow
    # distance*abs(scale)≤目标跨度≤uint64 max，由逆区间证明安全。
    change = distance * np.uint64(abs(scale))
    # unsigned目标只做已证明不溢出/下溢的相应方向运算。
    if dtype is SignalDType.UINT64:
        # 最终合法范围已在运算前证明。
        result[accepted] = np.uint64(base) + change if scale > 0 else np.uint64(base) - change
    else:
        # signed结果跨过零时使用幅度与符号分段，避免signed中间超界。
        magnitude = np.empty(len(change), dtype=np.uint64)
        # 正scale增加，负base可越过零。
        if scale > 0:
            # base>=0全部非负且base+change≤max。
            if base >= 0:
                # unsigned内部结果也在signed max内。
                magnitude[:] = np.uint64(base) + change
                # 没有负结果。
                negative = np.zeros(len(change), dtype=bool)
            else:
                # change小于abs(base)的位置仍为负。
                negative = change < np.uint64(-base)
                # 不同方向分别执行安全unsigned减法。
                magnitude[negative] = np.uint64(-base) - change[negative]
                # 含零结果，幅度不超signed max。
                magnitude[~negative] = change[~negative] - np.uint64(-base)
        else:
            # base<=0再减少，负幅度加法≤2**63。
            if base <= 0:
                # 已证明目标范围，幅度加法无wrap。
                magnitude[:] = np.uint64(-base) + change
                # 零的符号在位解释函数中特别处理。
                negative = np.ones(len(change), dtype=bool)
            else:
                # 跨零分段，equal对应正常0。
                negative = change > np.uint64(base)
                # 负结果幅度≤2**63。
                magnitude[negative] = change[negative] - np.uint64(base)
                # 正数/零幅度≤signed max。
                magnitude[~negative] = np.uint64(base) - change[~negative]
        # 每个符号段已证明范围，位解释包含min，不做signed负号溢出。
        result[accepted] = _from_magnitude(magnitude, negative)
    # 数值与错误mask保持原行。
    return result, overflow


def _float_limit(value, *, lower):
    """将精确配置边界向区间内收至可表示float64端点。

    参数: value为原生int/有限float；lower表示下界或上界。
    返回: float端点，大到不可表示的整数按方向得到Inf/最大有限值。
    异常: 配置类型已校验；数值转换溢出仅表示不可达端点。
    """
    # 配置整数不能先舍入后改变有效范围。
    try:
        # 这里只转换一次配置常量，不是逐样本数值。
        result = float(value)
    except OverflowError:
        # 超float范围的整数边界仍有确定区间含义。
        result = float('inf') if value > 0 else float('-inf')
    # 向合法方向收缩；Python的float/int比较保留精确整数边界。
    if (lower and result < value) or (not lower and result > value):
        # nextafter处理边界舍入及Inf收缩，避免误收工程值。
        result = float(np.nextafter(result, float('inf') if lower else float('-inf')))
    # 返回可直接批量比较的端点。
    return result


def normalize_numpy(definition: SignalDefinition, raw: np.ndarray, quality: np.ndarray | None = None) -> NumericArray:
    """按声明批量转换原列，检查编码映射、无效原值和转换后的业务范围。

    参数:
        definition (SignalDefinition): 当前信号类型、转换、编码和范围声明。
        raw (ndarray, shape=(N,)): 同质原列，dtype为int64、uint64、float64、
            bool或Unicode文本；不接受object数组和隐式广播。
        quality (ndarray[uint16], shape=(N,) | None): 已知上游质量原因；默认
            None表示全部NONE。已有原因保留，无效位置不进入正常计算。
    返回:
        NumericArray: 目标声明类型的值、有效掩码和完整质量原因。无效值是
        存储占位；内存适配另外从原行保留诊断值。
    异常:
        TypeError或ValueError: 输入布局、质量位或声明结构不合法。
        MemoryError: 数组分配失败。
        数值溢出、非有限值或精度损失记录为质量原因，不输出正常值。
    副作用:
        输出和原因使用局部数组，不修改原列或调用者质量列。
    """
    # 不接受object列或隐藏dtype转换，原数值宽度明确。
    if not isinstance(definition, SignalDefinition) or type(raw) is not np.ndarray or raw.ndim != 1 or not (raw.dtype in (np.dtype('int64'), np.dtype('uint64'), np.dtype('float64'), np.dtype('bool')) or raw.dtype.kind == 'U'):
        # I/O适配应先按原类型装箱。
        raise TypeError('normalize需要声明及1维明确原列类型')
    # 默认上游质量NONE，真实缺失由适配写MISSING。
    reasons = np.zeros(len(raw), dtype=np.uint16) if quality is None else quality
    # 布局不自动广播，不接受未知质量位。
    if type(reasons) is not np.ndarray or reasons.ndim != 1 or reasons.dtype != np.dtype('uint16') or len(reasons) != len(raw) or np.any(reasons > 511):
        # 配置/结构问题不能伪装数据缺失。
        raise ValueError('上游质量需要同长uint16已知位')
    # 后续只改局部原因副本，不修改调用侧。
    reasons = reasons.copy()
    # 每一层只对还正常的位置新增诊断。
    selected = reasons == 0
    # 非有限先拒绝，scale0不能把Inf恢复正常。
    if raw.dtype == np.dtype('float64'):
        # 正常输入NaN/Inf明确NONFINITE。
        reasons[selected & ~np.isfinite(raw)] |= np.uint16(QualityFlag.NONFINITE)
    # 同类型invalid原值规则批量运行，bool/int不会互相匹配。
    native_type = {'i': int, 'u': int, 'f': float, 'b': bool, 'U': str}[raw.dtype.kind]
    # 配置规则循环次数与样本数无关，每次真实列比较。
    for value in definition.invalid_values:
        # 超原dtype整数范围不会存在，不让NumPy隐式promotion到float。
        if type(value) is native_type and (native_type is not int or np.iinfo(raw.dtype).min <= value <= np.iinfo(raw.dtype).max):
            # 仅正常尚未失败的位置拒绝原无效码。
            reasons[(reasons == 0) & (raw == value)] |= np.uint16(QualityFlag.OUT_OF_RANGE)
    # 目标列物理dtype明确，无效为仅存储占位。
    values = np.zeros(len(raw), dtype=DTYPES[definition.dtype])
    # enum域按显式映射第一次标签顺序固定。
    labels = tuple(dict.fromkeys(label for _, label in definition.choices)) if definition.dtype is SignalDType.ENUM else ()
    # bool/enum映射与数值转换完全分开。
    if definition.dtype in (SignalDType.BOOL, SignalDType.ENUM):
        # 原生bool且没有额外choices可以保留真实False。
        if definition.dtype is SignalDType.BOOL and not definition.choices and raw.dtype == np.dtype('bool'):
            # 不使用truthiness推断其他原类型。
            values[reasons == 0] = raw[reasons == 0]
            # 正常False与invalid分开。
            return _output(definition.dtype, values, reasons)
        # 命中域掩码一维N。
        matched = np.zeros(len(raw), dtype=bool)
        # 逐配置编码向整列批量映射，不逐样本回调。
        for code, label in definition.choices:
            # 原生类型必须精确相同，整数编码另检查可表示。
            if type(code) is native_type and (native_type is not int or np.iinfo(raw.dtype).min <= code <= np.iinfo(raw.dtype).max):
                # 只有合法输入能命中声明码。
                mask = (reasons == 0) & (raw == code)
                # enum显式标签编码，bool保留类型。
                values[mask] = labels.index(label) if labels else label
                # 后续未匹配原码将明确无效。
                matched |= mask
        # 不自动取第一项，不转任意整数为bool。
        reasons[(reasons == 0) & ~matched] |= np.uint16(QualityFlag.OUT_OF_RANGE)
        # 返回固定逻辑域及完整质量。
        return _output(definition.dtype, values, reasons, labels)
    # 数值输入拒绝bool/字符串，而非解析/恢复正常。
    if raw.dtype.kind in ('b', 'U'):
        # upstream已有原因保持，不通过错误原码增加算术诊断。
        reasons[reasons == 0] |= np.uint16(QualityFlag.DECODE_ERROR)
        # 所有结果均有明确原因。
        return _output(definition.dtype, values, reasons)
    # 整数目标和整数配置在精确仿射路径处理。
    if definition.dtype in INTEGER_BOUNDS and raw.dtype.kind in ('i', 'u') and type(definition.scale) is int and type(definition.offset) is int:
        # 原整数不先经float，不因中间数学值超界误判最终合法结果。
        values, overflow = _affine_integer(raw, reasons == 0, definition.dtype, definition.scale, definition.offset)
        # 失败输入在计算之前识别。
        reasons[overflow] |= np.uint16(QualityFlag.OVERFLOW)
    else:
        # 原数值列封装只作模型校验，浮点精度核独立。
        raw_dtype = {'i': SignalDType.INT64, 'u': SignalDType.UINT64, 'f': SignalDType.FLOAT64}[raw.dtype.kind]
        # 已标记非有限的位置不是正常float，因此可保留原诊断。
        original_valid = reasons == 0
        # 原值和常量转换失败需要独立合并，不能掩盖同时发生的质量。
        converted = to_float_numpy(_output(raw_dtype, raw, reasons))
        # 合并真实精度失败位置。
        reasons = converted.quality.copy()
        # 配置常量只转换一次，但精度仍严格检查。
        constants = []
        # 系数/offset不应因为转换无穷而吞配置语义。
        for constant in (definition.scale, definition.offset):
            # Python配置常量转float有限检查，与reference核独立。
            try:
                # 常量次数固定，不是行循环。
                number = float(constant)
            except OverflowError:
                # 表示float数值失败，不能生成正常Inf。
                number = float('inf')
            # float64可精确表示常量才可参与列乘加。
            flag = QualityFlag.NONFINITE if not isfinite(number) else QualityFlag.PRECISION_LOSS if type(constant) is int and int(number) != constant else QualityFlag.NONE
            # 数值转换失败只影响原本有效输入。
            reasons[original_valid] |= np.uint16(flag)
            # 局部常量仅在全部检查后用于算术。
            constants.append(number)
        # 只有原值与常量都正常才执行线性转换。
        selected = reasons == 0
        # 局部float输出一维N，invalid占位不参与计算。
        transformed = np.zeros(len(raw), dtype=np.float64)
        # 单独乘再加，与参考float流程一致，不使用融合乘加改变两步计算的舍入。
        with np.errstate(over='ignore', invalid='ignore'):
            # where保证无效输入/非法常量未执行乘加。
            np.multiply(converted.values, constants[0], out=transformed, where=selected)
            # 第二步同样只对原先正常执行位置。
            np.add(transformed, constants[1], out=transformed, where=selected)
        # 算术非有限明确失败，不通过targetcast隐藏。
        reasons[selected & ~np.isfinite(transformed)] |= np.uint16(QualityFlag.NONFINITE)
        # 整数目标还需要拒绝小数和端点外float。
        if definition.dtype in INTEGER_BOUNDS:
            # 保留前序失败后再检测小数。
            selected = reasons == 0
            # 不截断合法小数冒充整型。
            reasons[selected & (transformed != np.trunc(transformed))] |= np.uint16(QualityFlag.PRECISION_LOSS)
            # 上界采用exclusive 2**63/2**64，避免max转float向上舍入。
            lo, hi = INTEGER_BOUNDS[definition.dtype]
            # 下界和exclusive上界均能精确表示。
            outside = (transformed < float(lo)) | (transformed >= float(hi + 1))
            # 小数精度失败优先级与参考一致，不添加额外OVERFLOW。
            reasons[(reasons == 0) & outside] |= np.uint16(QualityFlag.OVERFLOW)
            # 证明可表示后才能实际astype。
            selected = reasons == 0
            # 不对NaN/Inf/超界值执行cast。
            values[selected] = transformed[selected].astype(DTYPES[definition.dtype])
        else:
            # float结果直接保持真实计算值和质量。
            values = transformed
    # 业务范围针对最终有效转换值，严禁先舍入配置整数边界。
    if definition.valid_range is not None:
        # 固定两个配置端点，不是逐样本检查。
        lo, hi = definition.valid_range
        # float边界向合法区间内收后批量比较。
        if definition.dtype is SignalDType.FLOAT64:
            # 端点转换是精确边界而非隐藏工程值修正。
            outside = (values < _float_limit(lo, lower=True)) | (values > _float_limit(hi, lower=False))
        else:
            # 整型工程边界先取ceil/floor再求目标域交集。
            lower, upper = INTEGER_BOUNDS[definition.dtype]
            # 配置Python整数保持完整；float有限边界取整精确。
            lo, hi = max(lower, ceil(lo)), min(upper, floor(hi))
            # 空域全部工程失败，否则安全cast边界。
            outside = np.ones(len(raw), dtype=bool) if lo > hi else ((values < DTYPES[definition.dtype].type(lo)) | (values > DTYPES[definition.dtype].type(hi)))
        # 先前数值失败不被业务范围0占位污染。
        reasons[(reasons == 0) & outside] |= np.uint16(QualityFlag.OUT_OF_RANGE)
    # 最终结果独立只读，valid只由完整质量决定。
    return _output(definition.dtype, values, reasons)


def memory_series_numpy(bindings: SignalBindings, name: str) -> SignalSeries:
    """按原字段类型分组装箱，批量转换后恢复原行顺序和来源身份。

    参数:
        bindings (SignalBindings): 当前会话的已校验绑定。
        name (str): 已绑定的原信号别名。
    返回:
        SignalSeries: 正常值使用转换结果，无效值保留原字段诊断；时间只应用
        声明的固定偏移，原序号和来源引用保持不变。
    异常:
        TypeError、ValueError或OverflowError: 定义、布局、同时间冲突、原行归属
        或时间映射检查失败。
        MemoryError: 装箱、结果或数组分配失败。
    副作用:
        分配本次完整历史，不读取旧来源或修改原行。
    """
    # 当前定义与真实来源唯一，不继承上次输入。
    definition = bindings.resolve(name)
    # 来源名称已在绑定层校验。
    source = next(item for item in bindings.session.sources if item.name == definition.source)
    # 原行顺序，只选已有目标字段，不增加观测或解码。
    rows = tuple(row for row in source.rows if definition.field in row.values)
    # 按原生物理类型分组装箱，不使用object算术。
    groups = {}
    # 空间为原输入行数；当前memory核心不声称生产资源门槛。
    results = [None] * len(rows)
    # Python逐行仅作原生类型/宽度检查与装箱身份。
    for index, row in enumerate(rows):
        # 原值来自已解码memory字段。
        value = row.values[definition.field]
        # 缺失无法在正常typed列表示，先包装质量而不是补成正常0。
        if value is None:
            # 模拟typed原列占位但携带MISSING，转换核不会使用。
            key, packed, flag = 'i', 0, QualityFlag.MISSING
        # 原生整数先确定原64位存储域，不能从目标dtype倒推源宽度。
        elif type(value) is int:
            # 原数值协议仅支持int64/uint64；宽度超出明确OVERFLOW。
            flag = QualityFlag.NONE if -(2 ** 63) <= value <= 2 ** 64 - 1 else QualityFlag.OVERFLOW
            # 超界原整数占位不参与运算，原诊断最后恢复。
            key, packed = ('i' if value <= 2 ** 63 - 1 else 'u'), value if flag == QualityFlag.NONE else 0
        else:
            # bool和str保持各自独立物理域，float不提前过滤非有限。
            key, packed, flag = {float: 'f', bool: 'b', str: 'U'}[type(value)], value, QualityFlag.NONE
        # 每组保存输出位置/原数据/质量，只进行存储布局操作。
        groups.setdefault(key, []).append((index, packed, int(flag)))
    # 不同原类型分别走同质真实数组内核，循环次数至多5。
    for key, items in groups.items():
        # 类型由装箱规则明确，不采用跨类型隐式promotion。
        dtype = {'i': np.int64, 'u': np.uint64, 'f': np.float64, 'b': bool, 'U': str}[key]
        # 每组批量形成原值/质量typed数组。
        raw = np.array([value for _, value, _ in items], dtype=dtype)
        # None/超界输入携带质量，因此占位不能恢复正常。
        quality = np.array([flag for _, _, flag in items], dtype=np.uint16)
        # 核心计算真实批量执行，不调用reference归一化。
        normalized = normalize_numpy(definition, raw, quality)
        # Python遍历仅还原公开原生结果与身份，不进行数值计算。
        for position, (index, _, _) in enumerate(items):
            # 正常enum编码按冻结域恢复标签。
            value = normalized.labels[int(normalized.values[position])] if normalized.labels and normalized.valid[position] else normalized.values[position].item()
            # 保存值/有效性/完整质量，原诊断稍后按行恢复。
            results[index] = (value, bool(normalized.valid[position]), QualityFlag(int(normalized.quality[position])))
    # 输出按原行顺序恢复，原时间offset明确且安全。
    samples = tuple(SignalSample(name, checked_add_ns(row.time_ns, source.offset_ns), value if valid else row.values[definition.field], valid, quality, bindings.source_ref(name), row.sequence)
                    for row, (value, valid, quality) in zip(rows, results))
    # 同时间及来源约束由SignalSeries检查，不改变原来源消息数量。
    return SignalSeries(bindings, name, samples)
