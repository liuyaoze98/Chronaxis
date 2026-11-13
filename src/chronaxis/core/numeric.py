"""把已解码的单个值转换成声明类型，并提供独立的标量运算参考实现。

normalize_reference接收SignalDefinition、原生标量和上游质量原因，
只应用额外声明的scale、offset、枚举映射与有效范围，输出ScalarValue。
算术和比较接收ScalarValue，先检查类型与质量，再计算并检查结果范围。
value保存数值或原诊断；dtype说明类型；valid表示能否使用；quality记录原因。

整数先在Python精确整数域中运算，再检查int64或uint64的定宽边界。
需要float64时，先检查整数是否能被精确表示；无效输入不参与正常计算。
memory_series_reference从已有内存行生成信号历史，保留来源和纳秒时间。
本模块只依赖标准库与核心模型，不读取文件、加载DBC或调用NumPy数值内核。
数组实现可共享静态类型规则和模型检查，数值计算仍由各自实现承担。
"""

# 有限性/配置端点辅助只使用标准库，不替代数组数值内核。
from math import isfinite
# 静态内建比较仅用于参考白名单，不接自由函数。
from operator import eq, ne, lt, le, gt, ge
# 只读静态映射或显式质量/type枚举用于结构协议。
from types import MappingProxyType

# 使用真实已校验定义与来源模型，memory适配只处理已暴露原行。
from .binding import SignalBindings, SignalDefinition
# 保留原样本来源与身份，不能重写原行。
from .models import SignalSample
# 接入已校验保持模型，不改变原来源顺序。
from .state import SignalSeries
# 只读静态映射或显式质量/type枚举用于结构协议。
from .types import QualityFlag, SignalDType
# 共享原生结构校验，不共享数值参考。
from .validation import require_scalar
# 时间offset使用已有精确整数加法协议。
from ..timebase.conversion import checked_add_ns

# 重导出共用标量类，保持公开导入和进程序列化路径不变。
from .scalar import INTEGER_BOUNDS, ScalarValue

# 首版算术和比较白名单，DSL语法检查由EXPR承担。
ARITHMETIC = frozenset({"add", "sub", "mul", "div"})
# 精确比较白名单与算术分开，不放行任意函数。
COMPARISONS = frozenset({"eq", "ne", "lt", "le", "gt", "ge"})
# 静态内建比较映射不接受用户函数，也无需创建无说明内部函数。
COMPARE_FUNCTIONS = MappingProxyType({"eq": eq, "ne": ne, "lt": lt, "le": le, "gt": gt, "ge": ge})


def result_dtype(operator: str, left: SignalDType, right: SignalDType, allow_float_literal: bool = False) -> SignalDType:
    """根据运算和两侧声明类型，确定允许的结果类型。

    参数:
        operator: 已注册的算术或比较名称。
        left、right: 两侧SignalDType声明。
        allow_float_literal: 编译器已证明混合类型中的浮点侧是字面量时才为True。
    返回:
        SignalDType。比较返回BOOL；除法或允许的浮点算术返回FLOAT64。
    异常:
        TypeError: 类型声明或字面量证明标志的类型不合法。
        ValueError: 运算未注册、逻辑类型不支持该运算，或混合类型未显式归一化。
    边界:
        本函数只检查静态类型，不计算信号值。INT64与UINT64可精确比较；
        两种不同整数类型的信号不能直接混合算术。
    """
    # 编译语义只接受完整枚举和明确布尔字面量证明。
    if not isinstance(left, SignalDType) or not isinstance(right, SignalDType) or type(allow_float_literal) is not bool:
        # 不以字符串类型名绕过静态门槛。
        raise TypeError("运算dtype必须显式声明")
    # 未注册函数/运算不能进入数值执行。
    if operator not in ARITHMETIC | COMPARISONS:
        # 幂等未支持项由上层直接拒绝。
        raise ValueError(f"未支持数值运算：{operator}")
    # bool和enum仅支持同类型等值比较。
    if left in (SignalDType.BOOL, SignalDType.ENUM) or right in (SignalDType.BOOL, SignalDType.ENUM):
        # 不将逻辑值转0/1参加一般数值运算。
        if left is not right or operator not in ("eq", "ne"):
            # 枚举排序/算术不是首版契约。
            raise ValueError("bool/enum仅支持同类型eq/ne")
        # 逻辑等值比较仍返回显式bool掩码。
        return SignalDType.BOOL
    # 两种定宽整数比较在整数域精确，不能隐藏转float。
    if operator in COMPARISONS:
        # 仅整数/float信号混合比较需先显式归一化。
        if left is not right and SignalDType.FLOAT64 in (left, right) and not allow_float_literal:
            # 常量路径须由编译器证明，信号路径配置拒绝。
            raise ValueError("整数/float信号比较需显式归一化")
        # 同型或signed/unsigned比较输出bool。
        return SignalDType.BOOL
    # 不同整数dtype信号也不能隐式promotion算术。
    if left is not right and not (allow_float_literal and SignalDType.FLOAT64 in (left, right)):
        # 配置错误不伪装成样本缺失。
        raise ValueError("不同dtype信号算术需显式归一化")
    # 除法或明确浮点字面量算术使用float64，先检查整数精度。
    return SignalDType.FLOAT64 if operator == "div" or SignalDType.FLOAT64 in (left, right) else left


def _exact_float(value: int | float) -> tuple[float | None, QualityFlag]:
    """参考路径用整数往返校验显式浮点转换。

    参数: value为原生整数或float；输入类型由调用者明确校验。
    返回: float值及NONE，或None及PRECISION_LOSS/NONFINITE。
    异常: 无主动异常；数值溢出转换为质量，不吞配置类型错误。
    """
    # 超大Python整数转换可能抛OverflowError，表示非有限浮点输出。
    try:
        # 显式转换，不能先丢精度后比较浮点近似。
        result = float(value)
    except OverflowError:
        # 只将明确转换溢出变为NONFINITE。
        return None, QualityFlag.NONFINITE
    # 已有float的非有限同样禁止。
    if not isfinite(result):
        # 不能保留Inf为正常数值。
        return None, QualityFlag.NONFINITE
    # 整数与转回整数精确比较，不先把原整数也变float。
    if type(value) is int and int(result) != value:
        # 2**53+1不能默默舍入为2**53。
        return None, QualityFlag.PRECISION_LOSS
    # 合法显式float转换完成，不恢复来源已有float精度。
    return result, QualityFlag.NONE


def to_float_reference(value: ScalarValue) -> ScalarValue:
    """显式将数值结果转换float64，保留invalid和精度失败。

    参数: value为int64/uint64/float64 ScalarValue。
    返回: ScalarValue float64，无法精确表示时invalid/PRECISION_LOSS。
    异常: TypeError/ValueError为结构或逻辑dtype。
    """
    # 逻辑bool/enum不能进入数值转换。
    if not isinstance(value, ScalarValue) or value.dtype in (SignalDType.BOOL, SignalDType.ENUM):
        # 不用truthiness或字符串解析实现转换。
        raise TypeError("float转换需要数值ScalarValue")
    # 无效输入不执行正常转换，原因传递。
    if not value.valid:
        # 输出占位不参与正常算术。
        return ScalarValue(None, SignalDType.FLOAT64, False, value.quality)
    # 参考使用独立整数往返，不调用数组精度掩码。
    number, quality = _exact_float(value.value)
    # 转换失败是样本质量，不是正常舍入结果。
    return ScalarValue(number, SignalDType.FLOAT64, quality == QualityFlag.NONE, quality)


def binary_reference(operator: str, left: ScalarValue, right: ScalarValue, *, allow_float_literal: bool = False) -> ScalarValue:
    """对两个已检查的标量执行算术或比较，并保留质量原因。

    参数:
        operator: 已注册的二元运算名称；left、right为ScalarValue。
        allow_float_literal: 由编译器证明浮点字面量可以参与混合类型运算。
    返回:
        ScalarValue。输入无效时传播两侧原因；整数超界、除零、非有限结果
        或浮点转换丢精度时返回无效结果，不以零或舍入值替代。
    异常:
        TypeError、ValueError: 输入模型、运算类型或枚举比较域不符合要求。
    流程:
        先检查静态类型，即使输入无效也不跳过配置错误。正常整数在Python
        精确整数域中计算，再检查目标定宽范围；浮点路径先检查转换精度。
    """
    # 运行输入须已经通过逻辑结果构造门槛。
    if not isinstance(left, ScalarValue) or not isinstance(right, ScalarValue):
        # 不把无类型对象直接算作正常数据。
        raise TypeError("二元运算需要ScalarValue")
    # 即使数据invalid也先检查静态配置错误。
    dtype = result_dtype(operator, left.dtype, right.dtype, allow_float_literal)
    # enum等值比较须同一公开逻辑域。
    if left.dtype is SignalDType.ENUM and left.labels != right.labels:
        # 不同域的相同标签不证明相同业务含义。
        raise ValueError("enum比较域不一致")
    # 原原因全部保留，invalid不进入正常值计算。
    quality = left.quality | right.quality
    # 基础质量禁全部非零位。
    if not left.valid or not right.valid:
        # 结果无正常值，不能用0假装成功。
        return ScalarValue(None, dtype, False, quality)
    # 原生值用于独立参考，整数不会先经float。
    a, b = left.value, right.value
    # float数值路径先核查全部整数可精确表示。
    if dtype is SignalDType.FLOAT64 or (operator in COMPARISONS and SignalDType.FLOAT64 in (left.dtype, right.dtype)):
        # 参考两个操作数分别转换/检查。
        a, qa = _exact_float(a)
        # 保留两侧同时发生的精度/非有限诊断。
        b, qb = _exact_float(b)
        # 转换失败不继续算术或比较。
        quality |= qa | qb
        # 返回明确invalid，不能比较已舍入整数。
        if quality != QualityFlag.NONE:
            # 同样错误政策由NumPy独立精度掩码实现。
            return ScalarValue(None, dtype, False, quality)
    # 比较在精确原生域中按白名单执行。
    if operator in COMPARISONS:
        # 此处允许signed/unsigned Python整数精确比较。
        result = COMPARE_FUNCTIONS[operator](a, b)
        # 正常比较结果是bool，不转Truth或吞UNKNOWN。
        return ScalarValue(result, SignalDType.BOOL)
    # 0分母在真正除法之前拒绝。
    if operator == "div" and b == 0:
        # 包含0/0，不能生成正常Inf/NaN或0。
        return ScalarValue(None, dtype, False, QualityFlag.DOMAIN_ERROR)
    # Python整数中间值无界，之后仍检查定宽规范。
    result = a + b if operator == "add" else a - b if operator == "sub" else a * b if operator == "mul" else a / b
    # 定宽输出不能以Python大整数成功为由放行。
    if dtype in INTEGER_BOUNDS:
        # signed/unsigned各自端点明确。
        lower, upper = INTEGER_BOUNDS[dtype]
        # 下溢同样属于OVERFLOW，不返回wrap后的值。
        if not lower <= result <= upper:
            # 质量失败不会参与后续事件/统计。
            return ScalarValue(None, dtype, False, QualityFlag.OVERFLOW)
    # 浮点溢出产生非有限结果，不能沿用整数OVERFLOW原因。
    elif not isfinite(result):
        # float输出非有限是NONFINITE，不正常归约。
        return ScalarValue(None, dtype, False, QualityFlag.NONFINITE)
    # 正常结果保持输出dtype和NONE质量。
    return ScalarValue(result, dtype)


def unary_reference(operator: str, value: ScalarValue) -> ScalarValue:
    """独立参考abs/negate，在整数域拒绝min翻转及unsigned下溢。

    参数: operator为abs或neg；value为数值ScalarValue。
    返回: 同dtype ScalarValue，超界为OVERFLOW，invalid原因保留。
    异常: TypeError/ValueError为输入或未支持逻辑/运算。
    """
    # 不接受逻辑值或自由运算名。
    if not isinstance(value, ScalarValue) or value.dtype in (SignalDType.BOOL, SignalDType.ENUM) or operator not in ("abs", "neg"):
        # unary DSL白名单由EXPR静态映射。
        raise ValueError("unary仅支持数值abs/neg")
    # 无效输入不能通过abs恢复正常。
    if not value.valid:
        # 原原因作为结果质量传播。
        return ScalarValue(None, value.dtype, False, value.quality)
    # Python精确整数参考，不发生int64 min的先wrap。
    result = abs(value.value) if operator == "abs" else -value.value
    # 正常结果仍服从同一定宽。
    if value.dtype in INTEGER_BOUNDS:
        # unsigned neg非零下溢与signed min翻转均在范围外。
        lower, upper = INTEGER_BOUNDS[value.dtype]
        # 先验证再构造，禁止饱和值假装正常。
        if not lower <= result <= upper:
            # 明示原因，无正常值可计算。
            return ScalarValue(None, value.dtype, False, QualityFlag.OVERFLOW)
    # 有限float取abs/neg仍有限，逻辑构造再次校验。
    return ScalarValue(result, value.dtype)


def normalize_reference(definition: SignalDefinition, value, quality: QualityFlag = QualityFlag.NONE) -> ScalarValue:
    """按显式信号声明转换一个已解码值，并检查业务有效范围。

    参数:
        definition: SignalDefinition，提供目标类型、scale、offset、choices及范围。
        value: 已解码的原生标量；不解析数值字符串。
        quality: 上游已有质量原因，默认NONE。
    返回:
        ScalarValue。正常值使用目标类型；无效时保留原值及缺失、非有限、
        超范围、解码失败、精度损失或溢出的原因。枚举同时保留固定标签域。
    异常:
        TypeError: 声明、质量或原生标量结构不合法。
        数值转换失败记入quality，配置错误仍由底层检查直接抛出。
    流程:
        先处理已有质量、缺失值和显式无效值；逻辑类型按choices映射，
        数值类型应用额外的value * scale + offset，再检查定宽与valid_range。
        输入已完成上游解码，本函数不加载DBC，也不重复上游的工程单位转换。
    """
    # 不接无类型转换字典或自由质量值。
    if not isinstance(definition, SignalDefinition) or not isinstance(quality, QualityFlag):
        # 配置校验先于数值操作。
        raise TypeError("normalize需要SignalDefinition及QualityFlag")
    # 输入原生类型检查无副作用，不解析数值字符串。
    require_scalar(value)
    # enum结果域来自已经冻结的编码映射。
    labels = tuple(dict.fromkeys(label for _, label in definition.choices)) if definition.dtype is SignalDType.ENUM else ()
    # 已有质量不足以正常使用，不再执行转换。
    if quality != QualityFlag.NONE:
        # 保留上游原值及原因。
        return ScalarValue(value, definition.dtype, False, quality, labels)
    # 原缺失先明确标记，不补0。
    if value is None:
        # 缺失没有正常业务类型。
        return ScalarValue(value, definition.dtype, False, QualityFlag.MISSING, labels)
    # 输入NaN/Inf先拒绝，不能借scale0把非有限输入恢复正常。
    if type(value) is float and not isfinite(value):
        # 来源已有浮点精度不做伪修复。
        return ScalarValue(value, definition.dtype, False, QualityFlag.NONFINITE, labels)
    # 所有原整数（包含映射编码）须属于原64位数值协议。
    if type(value) is int and not -(2 ** 63) <= value <= 2 ** 64 - 1:
        # 原值仍保存，超宽Python整数不是新输入dtype。
        return ScalarValue(value, definition.dtype, False, QualityFlag.OVERFLOW, labels)
    # 无效值规则使用原类型与值，bool不隐式等于int编码。
    if any(type(item) is type(value) and item == value for item in definition.invalid_values):
        # 明示业务无效值没有正常计算意义。
        return ScalarValue(value, definition.dtype, False, QualityFlag.OUT_OF_RANGE, labels)
    # 逻辑映射与数值转换分开，不能通过truthiness猜标签。
    if definition.dtype in (SignalDType.BOOL, SignalDType.ENUM):
        # 原生bool在没有额外映射时可以直接使用。
        if definition.dtype is SignalDType.BOOL and not definition.choices and type(value) is bool:
            # 真正False是合法值，不代表UNKNOWN。
            return ScalarValue(value, definition.dtype)
        # 明示编码精确匹配，未声明码不能自动取第一个。
        matches = [label for code, label in definition.choices if type(code) is type(value) and code == value]
        # 编码域之外或没有bool声明映射均失败。
        if not matches:
            # 保留错误原码诊断，不能转换任意数值为bool。
            return ScalarValue(value, definition.dtype, False, QualityFlag.OUT_OF_RANGE, labels)
        # 定义已保证编码唯一，不猜目标标签。
        return ScalarValue(matches[0], definition.dtype, labels=labels)
    # 普通数值原值只允许int/float，bool与str不能隐藏转换。
    if type(value) not in (int, float):
        # I/O层解析失败需明确原因，不自行float字符串。
        return ScalarValue(value, definition.dtype, False, QualityFlag.DECODE_ERROR)
    # 整数输入与整数系数可在独立Python整数域精确变换。
    integer_path = definition.dtype in INTEGER_BOUNDS and all(type(item) is int for item in (value, definition.scale, definition.offset))
    # 完整线性结果在精确域计算，避免中间机器wrap。
    if integer_path:
        # 转换是额外已声明线性关系，不重复上游缩放。
        result = value * definition.scale + definition.offset
    else:
        # 非整数系数或float输出须先检查输入和整数系数可精确表示。
        number, qvalue = _exact_float(value)
        # 大整数系数同样不能悄悄舍入。
        scale, qscale = _exact_float(definition.scale)
        # 偏移涉及整数时亦遵守精度契约。
        offset, qoffset = _exact_float(definition.offset)
        # 任一精度/非有限问题先停止正常变换。
        failure = qvalue | qscale | qoffset
        # 保留原诊断，不执行失败位置乘加。
        if failure != QualityFlag.NONE:
            # 两后端以独立掩码验证同样政策。
            return ScalarValue(value, definition.dtype, False, failure)
        # 已核实输入后再计算额外变换。
        result = number * scale + offset
        # 浮点非有限输出明确无效。
        if not isfinite(result):
            # 不能用范围检查忽略NaN/Inf。
            return ScalarValue(value, definition.dtype, False, QualityFlag.NONFINITE)
    # 整型目标要求整数精确结果，不能截断float小数。
    if definition.dtype in INTEGER_BOUNDS:
        # 整型结果若为float必须恰为整数。
        if type(result) is float and not result.is_integer():
            # 目标dtype丢失小数是明确精度失败。
            return ScalarValue(value, definition.dtype, False, QualityFlag.PRECISION_LOSS)
        # Python精确比较定宽上下限，不把max先转float。
        lower, upper = INTEGER_BOUNDS[definition.dtype]
        # 目标范围在真正cast前校验。
        if not lower <= result <= upper:
            # signed/unsigned下溢/溢出均无效。
            return ScalarValue(value, definition.dtype, False, QualityFlag.OVERFLOW)
        # 已证明精确整型结果才转换原生int。
        result = int(result)
    # 业务范围针对转换后的值，与DBC min/max分开。
    if definition.valid_range is not None and not definition.valid_range[0] <= result <= definition.valid_range[1]:
        # 不裁剪错误工程值冒充正常。
        return ScalarValue(value, definition.dtype, False, QualityFlag.OUT_OF_RANGE)
    # 正常输出保持显式目标dtype。
    return ScalarValue(result, definition.dtype)


def memory_series_reference(bindings: SignalBindings, name: str, *, capture_code=False) -> SignalSeries:
    """从当前内存来源提取一个字段，转换后生成信号历史。

    参数:
        bindings: 当前真实SignalBindings；name为其中已定义的简单别名。
        原行时间使用整数纳秒，来源offset_ns只作为显式时间偏移应用一次。
    返回:
        SignalSeries。保存正常转换值或无效原值，以及质量、时间、序号和来源。
    异常:
        绑定、归属、时间溢出、顺序或冲突检查失败时传播底层异常。
    边界:
        只处理原行中实际出现的字段；其他字段更新不生成该信号的新观测。
        创建新的样本集合，不修改原行、不排序，也不读取日志或加载DBC。
    """
    # 当前定义与来源必须明确，不能继承其他计划。
    definition = bindings.resolve(name)
    # 已绑定来源在会话内唯一。
    source = next(item for item in bindings.session.sources if item.name == definition.source)
    # 新结果局部保存，不改变原memory行。
    samples = []
    # 原行顺序、参数和身份不被调整。
    for row in source.rows:
        # 其他字段更新不伪造当前列的新观测。
        if definition.field not in row.values:
            # 缺列不是该列明确invalid更新。
            continue
        # 原值已是解码/表格输出，参考只应用额外声明变换。
        original = row.values[definition.field]
        # 独立参考归一化，不调用被测NumPy核。
        value = normalize_reference(definition, original)
        from .enum_codes import original_code
        # 输出样本保留原诊断、稳定身份与显式时间offset。
        samples.append(SignalSample(name, checked_add_ns(row.time_ns, source.offset_ns),
                                    value.value if value.valid else original, value.valid, value.quality,
                                    bindings.source_ref(name), row.sequence,
                                    original_code(definition, original) if capture_code else None))
    # 交给SignalSeries检查同时间更新、原行身份和声明类型，不调整输入顺序。
    return SignalSeries(bindings, name, tuple(samples))
