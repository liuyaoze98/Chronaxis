"""对同长度数值列执行算术和比较，并逐位置记录有效性与质量。

输入NumericArray保存一维values、bool类型的valid和uint16类型的quality。
算术先合并质量原因，再用布尔掩码选择能计算的位置，输出独立的只读列。
整数先检查符号、幅度和目标定宽范围，再执行NumPy逐元素函数；
需要float64时先检查整数的精确表示，失败位置不执行正常运算。

所有列的形状都是(N,)，N为行数；枚举存为int64编码并携带固定labels。
无效位置的零或False仅是存储占位，不能脱离valid当作业务值使用。
本模块依赖NumPy及核心类型规则，不读写文件或加载旧解码路径。
仅共享静态类型与模型检查，不调用标量参考数值函数，也不以object数组
或逐样本Python回调代替列运算；输出复制存储，不修改调用者数组。
"""

# 冻结模型及静态白名单；数组内核使用实际ufunc和掩码。
from dataclasses import dataclass
# 只读静态映射或显式质量/type枚举用于结构协议。
from types import MappingProxyType
# NumPy显式加载，承担真实typed列/ufunc与掩码计算。
import numpy as np

# 仅共享类型契约，不导入参考运算。
from .numeric import COMPARISONS, result_dtype
# 只读静态映射或显式质量/type枚举用于结构协议。
from .types import QualityFlag, SignalDType
# 共享原生/文本结构校验，不共享数值参考。
from .validation import require_text

# 每个输出声明有固定物理布局；enum是固定域的int64编码。
DTYPES = MappingProxyType({SignalDType.INT64: np.dtype('int64'), SignalDType.UINT64: np.dtype('uint64'),
                          SignalDType.FLOAT64: np.dtype('float64'), SignalDType.BOOL: np.dtype('bool'),
                          SignalDType.ENUM: np.dtype('int64')})
# ufunc只来自静态注册，用户不能传自由函数。
COMPARE_UFUNCS = MappingProxyType({'eq': np.equal, 'ne': np.not_equal, 'lt': np.less,
                                  'le': np.less_equal, 'gt': np.greater, 'ge': np.greater_equal})


def _readonly(array: np.ndarray) -> np.ndarray:
    """复制列并设置普通只读所有权约定。

    参数: array为已校验ndarray。
    返回: 拥有独立存储的只读列。
    异常: 内存分配错误传播；不声称防恶意篡改。
    """
    # 不借用调用侧可变缓冲。
    result = array.copy()
    # 输出不能普通原位修改。
    result.flags.writeable = False
    # 独立所有权允许调用侧继续使用其原数组。
    return result


@dataclass(frozen=True)
class NumericArray:
    """保存没有时间轴的一组数值，以及每个位置的有效性和质量原因。

    values、valid和quality均为形状(N,)的普通ndarray，长度必须一致。
    values的物理类型由dtype指定，valid为bool，quality为uint16；
    valid严格等于quality == 0，无效位置只能作为存储占位使用。
    枚举以int64编码表示，labels给出固定标签顺序，只检查有效位置的编码。
    构造时复制三个数组并设置只读标志，保留独立存储；这是一项普通使用
    约定，不声称能抵御主动解除写保护。实例不保存时间、单位或跨批次状态。
    """

    dtype: SignalDType  # 逻辑类型不靠NumPy推断。
    values: np.ndarray  # int64/uint64/float64/bool列；enum为int64 code。
    valid: np.ndarray  # bool有效位置，禁止maskless运算。
    quality: np.ndarray  # uint16足够容纳九种质量位。
    labels: tuple[str, ...] = ()  # enum顺序域，其他dtype为空。
    code: 'NumericArray | None' = None  # 仅请求 enum_code 时附带独立整数列。

    def take(self, indices):
        """按活动行切出标签及所需原码，保持同一坐标系。

        参数: indices 为行号或布尔掩码。返回: 对应行的独立 NumericArray。
        异常: 索引或布局不合法时传播数组错误。
        """
        return NumericArray(self.dtype, self.values[indices], self.valid[indices],
                            self.quality[indices], self.labels,
                            None if self.code is None else self.code.take(indices))

    def __post_init__(self) -> None:
        """验证布局、基础质量、有限性及enum域后冻结独立副本。

        参数: 无；读取数据类字段。
        返回: None；不隐式cast或清除质量。
        异常: TypeError为布局；ValueError为shape/质量/非法正常值。
        """
        # dtype必须是当前协议声明。
        if not isinstance(self.dtype, SignalDType) or not isinstance(self.labels, tuple):
            # 无类型字段不进入数组执行。
            raise TypeError('NumericArray需要typed dtype与tuple labels')
        # 严格ndarray不接隐藏掩码或自定义子类行为。
        for array, dtype in ((self.values, DTYPES[self.dtype]), (self.valid, np.dtype('bool')), (self.quality, np.dtype('uint16'))):
            # shape和物理类型不能靠自动astype补救。
            if type(array) is not np.ndarray or array.ndim != 1 or array.dtype != dtype:
                # 输出接口与内存布局必须明确。
                raise TypeError('NumericArray需要1维精确dtype ndarray')
        # 禁止广播掩盖行错位。
        if not (len(self.values) == len(self.valid) == len(self.quality)):
            # 不截断或重复最后一行。
            raise ValueError('数值/valid/quality长度不同')
        if self.code is not None and (self.dtype is not SignalDType.ENUM or not isinstance(self.code, NumericArray)
                or self.code.dtype not in (SignalDType.INT64, SignalDType.UINT64) or len(self.code.values) != len(self.values)):
            raise ValueError('只有枚举可附带等长整数原码列')
        # 仅非负已知原因位；valid严格等于基础无质量。
        if np.any(self.quality > 511) or not np.array_equal(self.valid, self.quality == 0):
            # invalid不能无原因，ESTIMATED也不能默认当正常。
            raise ValueError('质量与valid矛盾或未知质量位')
        # 正常float不能携带NaN/Inf。
        if self.dtype is SignalDType.FLOAT64 and np.any(~np.isfinite(self.values[self.valid])):
            # invalid诊断只存储，不通过finite单一检查判断整数质量。
            raise ValueError('正常float必须有限')
        # enum域由显式labels提供，不能隐式猜顺序。
        if self.dtype is SignalDType.ENUM:
            # 非空且唯一；映射归一化已处理多码同标签。
            if not self.labels or len(set(self.labels)) != len(self.labels):
                # 空域不能解释任何枚举编码。
                raise ValueError('enum需要非空唯一域')
            # 大小写敏感的业务文本原样保留。
            for label in self.labels:
                # labels不是表达式名称。
                require_text(label, 'enum.label')
            # 只校验正常编码，invalid占位不参与业务比较。
            if np.any((self.values[self.valid] < 0) | (self.values[self.valid] >= len(self.labels))):
                # 不采用Python负索引解释未知枚举。
                raise ValueError('正常enum code超出域')
        # 非枚举字段不能隐藏带入业务标签域。
        elif self.labels:
            # 普通数值不附带隐藏枚举语义。
            raise ValueError('非enum不能携带labels')
        # 数据类只读与数组只读是两层约定，均有独立所有权。
        for field in ('values', 'valid', 'quality'):
            # 三个输入列各自复制，不改调用侧写保护。
            object.__setattr__(self, field, _readonly(getattr(self, field)))


def _output(dtype, values, quality, labels=()) -> NumericArray:
    """用已有质量列建立统一有效性结果。

    参数: dtype/values/quality为局部结果；labels为enum域。
    返回: 独立只读NumericArray。
    异常: 模型校验/分配错误传播，不改变数值政策。
    """
    # 只有质量NONE的位置可以正常使用。
    return NumericArray(dtype, values, quality == 0, quality, labels)


def _magnitude(values: np.ndarray) -> np.ndarray:
    """在uint64中取得整数列的精确绝对幅度。

    参数:
        values: 形状(N,)的int64或uint64数组，由调用者保证布局。
    返回:
        新的uint64数组，形状保持(N,)；int64最小值得到2**63。
    异常:
        内存分配或底层数组操作异常直接传播。
    流程:
        先复制位表示，再对有符号负数按补码取反加一，不调用会溢出的abs(min)。
    """
    # unsigned输入本身就是幅度，复制防止原位别名。
    result = values.view(np.uint64).copy()
    # signed补码只用于定义良好的位解释，不先算有符号abs(min)。
    if values.dtype == np.dtype('int64'):
        # 负数的按位取反加1最大是2**63，全部在uint64范围内。
        negative = values < 0
        # 显式补码幅度算法；~位结果不超过uint64 max-1。
        result[negative] = np.bitwise_not(result[negative]) + np.uint64(1)
    # 后续乘法/精度检查均在此精确整数幅度域。
    return result


def _from_magnitude(magnitude: np.ndarray, negative: np.ndarray) -> np.ndarray:
    """把已证明范围合法的整数幅度和符号恢复成int64列。

    参数:
        magnitude: 形状(N,)的uint64幅度。正数不超过2**63-1，负数不超过2**63。
        negative: 同形状bool掩码，True表示该位置应为负数。
    返回:
        独立存储的int64数组；零和最小负数均通过位表示恢复。
    异常:
        调用者负责证明范围与布局；内存分配或数组操作异常直接传播。
    边界:
        先复制幅度再构建负数补码，最后改变位视图，不先执行危险的有符号负号。
    """
    # 正数位模式与signed相同，负数逐位置构建补码。
    bits = magnitude.copy()
    # 零幅度无需形成uint64 max+1；非零负数补码不溢出。
    selected = negative & (magnitude != 0)
    # ~幅度最大uint64 max-1，加1安全。
    bits[selected] = np.bitwise_not(magnitude[selected]) + np.uint64(1)
    # 已证明符号范围后进行位视图，不隐式算术wrap。
    return bits.view(np.int64)


def to_float_numpy(value: NumericArray) -> NumericArray:
    """用固定11个尾位掩码独立检查整数到float64是否精确。

    参数: value为数值NumericArray；invalid输入不转换。
    返回: float64列及保留/新增PRECISION_LOSS质量；shape保持。
    异常: TypeError为结构/逻辑类型；分配错误传播。
    """
    # bool/enum不进入数值提升。
    if not isinstance(value, NumericArray) or value.dtype in (SignalDType.BOOL, SignalDType.ENUM):
        # 不隐式把False当0或编码当数值。
        raise TypeError('float转换需要数值列')
    # 复制原因和独立输出占位，无效0不可使用。
    quality = value.quality.copy()
    # 输出固定float64且一维N。
    result = np.zeros(len(value.values), dtype=np.float64)
    # float已通过模型有限检查，不需要整数精度判据。
    if value.dtype is SignalDType.FLOAT64:
        # 仅拷贝正常位置，invalid占位不参与转换。
        result[value.valid] = value.values[value.valid]
    else:
        # 幅度精确包括signed min与unsigned max。
        magnitude = _magnitude(value.values)
        # 丢精度掩码按指数要求尾位为0，不做危险float→int64回转。
        loss = np.zeros(len(result), dtype=bool)
        # 64位幅度只需检查11种尾位间距；每轮检查整列，循环次数不随样本数增长。
        for bits in range(1, 12):
            # 指数区间最低有效位间距为2**bits；更大指数继续检查更多尾位。
            loss |= (magnitude >= np.uint64(2 ** (52 + bits))) & ((magnitude & np.uint64(2 ** bits - 1)) != 0)
        # 仅正常输入因精度变无效，已有原因不被计算占位污染。
        failed = value.valid & loss
        # 质量掩码至少uint16，不截断256等高位。
        quality[failed] |= np.uint16(QualityFlag.PRECISION_LOSS)
        # 真正转换只发生在已经证明精确且有效的位置。
        selected = value.valid & ~loss
        # 64位整数范围内不会超float64有限范围。
        result[selected] = value.values[selected].astype(np.float64)
    # 模型共享只校验输出，不共享参考数值。
    return _output(SignalDType.FLOAT64, result, quality)


def _integer_compare(operator, left, right, selected) -> np.ndarray:
    """在整数域精确比较signed/unsigned两列。

    参数: operator静态比较名，left/right整数列，selected有效bool掩码。
    返回: bool结果列，invalid占位False。
    异常: 调用者保证等长/类型，分配错误传播。
    """
    # 默认为不可使用的False，占位必须随质量掩码传递。
    result = np.zeros(len(left), dtype=bool)
    # 同dtype直接精确ufunc，不经过float。
    if left.dtype == right.dtype:
        # where不触碰invalid数值。
        COMPARE_UFUNCS[operator](left, right, out=result, where=selected)
        # 同型比较已经完成。
        return result
    # 哪一侧signed明示，不依赖NumPy混合promotion。
    signed_left = left.dtype == np.dtype('int64')
    # 负signed与任何unsigned之间的序固定。
    signed = left if signed_left else right
    # signed非负位置才能安全转uint64。
    negative = selected & (signed < 0)
    # 负signed永小于unsigned；换侧序相反。
    negative_result = operator in ('ne', 'lt', 'le') if signed_left else operator in ('ne', 'gt', 'ge')
    # 一次填满确定比较的负数子集。
    result[negative] = negative_result
    # 其余正常位置在无符号域精确比较。
    remaining = selected & ~negative
    # 子集cast证明非负，不从uint64 max转signed。
    result[remaining] = COMPARE_UFUNCS[operator](left[remaining].astype(np.uint64), right[remaining].astype(np.uint64))
    # 完整结果保持原行布局。
    return result


def _integer_arithmetic(operator, left, right, selected):
    """先检查整数结果是否超界，再计算安全位置的加减乘。

    参数:
        operator: add、sub或mul；left、right为同形状(N,)且同类型的整数数组。
        selected: 同形状bool掩码，标出两侧输入均有效的位置。
    返回:
        同类型结果数组和bool溢出掩码，均为形状(N,)。
        未选中或溢出位置保持零占位，调用者必须同时传递有效性与质量。
    异常:
        调用者保证输入布局和注册运算；内存分配或数组操作异常直接传播。
    流程:
        加减按符号检查安全门槛；乘法在uint64幅度域检查limit // b。
        检查后才调用逐元素函数，避免先发生整数回绕再判断溢出。
    """
    # 局部结果占位与失败掩码均为一维N。
    result = np.zeros_like(left)
    # 只考虑有效位置，invalid任意位模式不触发附加错误。
    overflow = np.zeros(len(left), dtype=bool)
    # 同型signed/unsigned路径分开，避免隐式promotion。
    signed = left.dtype == np.dtype('int64')
    # 先用减/加安全门槛检查add/sub。
    if operator in ('add', 'sub'):
        # unsigned add max-b安全；sub直接比较a<b。
        if not signed:
            # 全列门槛只是合法定宽值，无危险算术。
            overflow = selected & ((left > np.uint64(2 ** 64 - 1) - right) if operator == 'add' else (left < right))
        else:
            # 分符号取子集，min/max与相应b之差保证在范围内。
            positive = selected & (right > 0)
            # 0右值永不产生add/sub溢出。
            negative = selected & (right < 0)
            # add的正b只检查上界，负b只检查下界。
            if operator == 'add':
                # max-正数与min-负数均安全。
                overflow[positive] = left[positive] > np.int64(2 ** 63 - 1) - right[positive]
                # 包含b=min，min-min=0合法。
                overflow[negative] = left[negative] < np.int64(-(2 ** 63)) - right[negative]
            else:
                # sub正b检查min+b，负b检查max+b，门槛安全。
                overflow[positive] = left[positive] < np.int64(-(2 ** 63)) + right[positive]
                # 包含a=max,b=min，明确失败不执行subtract。
                overflow[negative] = left[negative] > np.int64(2 ** 63 - 1) + right[negative]
        # 只对已证明结果范围的元素调用ufunc。
        ufunc = np.add if operator == 'add' else np.subtract
        # where阻止无效/失败位置参与计算。
        ufunc(left, right, out=result, where=selected & ~overflow)
    else:
        # 精确幅度计算避免abs(min)，乘法不先wrap再检查。
        a, b = _magnitude(left), _magnitude(right)
        # signed负结果允许幅度2**63，正结果只允许max。
        negative = (left < 0) ^ (right < 0) if signed else np.zeros(len(left), dtype=bool)
        # 所有幅度限值都使用uint64，避免浮点近似改变溢出边界。
        limit = np.where(negative, np.uint64(2 ** 63), np.uint64(2 ** 63 - 1)) if signed else np.full(len(left), 2 ** 64 - 1, dtype=np.uint64)
        # b=0不做正常除法，乘积确定0合法。
        nonzero = selected & (b != 0)
        # 除法门槛在精确unsigned整数域。
        overflow[nonzero] = a[nonzero] > limit[nonzero] // b[nonzero]
        # 正常乘法完全不接触越界位置。
        np.multiply(left, right, out=result, where=selected & ~overflow)
    # 数值内核返回质量原因，由外层统一组合。
    return result, overflow


def binary_numpy(operator: str, left: NumericArray, right: NumericArray, *, allow_float_literal: bool = False) -> NumericArray:
    """对两列执行注册算术或比较，只计算质量允许的位置。

    参数:
        operator: 已注册的二元运算名称；left、right为同长度NumericArray。
        allow_float_literal: 编译器证明浮点字面量可用于混合类型时才为True。
    返回:
        独立只读NumericArray，形状保持(N,)。质量按位合并，计算失败追加原因。
        比较返回BOOL，算术遵守静态结果类型；无效占位不表示正常零或False。
    异常:
        TypeError、ValueError: 模型、类型、长度、注册运算或枚举域不合法。
        内存分配异常直接传播；除零、溢出或丢精度作为质量原因返回。
    流程:
        先检查类型与等长布局，再合并有效掩码；整数路径保留精确比较和定宽
        检查，浮点路径先做精度转换。各路径独立于标量参考实现，不修改输入。
    """
    # 完整typed输入必须存在，空列也做静态配置检查。
    if not isinstance(left, NumericArray) or not isinstance(right, NumericArray):
        # 不接受自由字典或裸数组。
        raise TypeError('binary需要两数值列')
    # 静态dtype协议允许共享，不调用参考运算。
    dtype = result_dtype(operator, left.dtype, right.dtype, allow_float_literal)
    # 同长行布局，无隐式broadcast。
    if len(left.values) != len(right.values):
        # 调用側必须显式对齐。
        raise ValueError('binary两列长度不同')
    # enum编码等值仅在同一标签域内成立。
    if left.dtype is SignalDType.ENUM and left.labels != right.labels:
        # 不能以整数code相同当不同逻辑标签相同。
        raise ValueError('enum比较需要相同标签域')
    # 基础质量合并不受存储占位影响。
    quality = left.quality | right.quality
    # 正常运算只允许双侧有效。
    selected = left.valid & right.valid
    # float算术/比较需要独立精度转换先验。
    float_path = dtype is SignalDType.FLOAT64 or (operator in COMPARISONS and SignalDType.FLOAT64 in (left.dtype, right.dtype))
    # 同型整数和逻辑比较保持精确原布局。
    if operator in COMPARISONS and not float_path:
        # 两种整数使用专门符号门槛，不隐式浮点promotion。
        if left.dtype in (SignalDType.INT64, SignalDType.UINT64):
            # 此函数单次批量精确执行。
            values = _integer_compare(operator, left.values, right.values, selected)
        else:
            # bool与同域enum等值ufunc。
            values = np.zeros(len(quality), dtype=bool)
            # 无效编码不参与比较。
            COMPARE_UFUNCS[operator](left.values, right.values, out=values, where=selected)
        # 质量并集正确保留invalid占位。
        return _output(dtype, values, quality)
    # float路径先检查两操作数，各自独立转换。
    if float_path:
        # 仅共同有效输入触发新质量，避免无效另一侧诱发多余精度错误。
        a = to_float_numpy(_output(left.dtype, left.values, quality, left.labels))
        # 同样quality使失败位置不在第二侧执行正常转换。
        b = to_float_numpy(_output(right.dtype, right.values, quality, right.labels))
        # 共同有效位置可能因整数精度丢失变无效。
        quality = a.quality | b.quality
        # 数值执行仅在全部转换成功处。
        selected = quality == 0
        # 比较结果逻辑型，float算术结果数值型。
        values = np.zeros(len(quality), dtype=DTYPES[dtype])
        # 除零先剔除，不能先产生Inf后当正常。
        if operator == 'div':
            # 包含正负0分母，0/0亦同。
            zero = selected & (b.values == 0)
            # 该位置明示域错误，不触发正常除法。
            quality[zero] |= np.uint16(QualityFlag.DOMAIN_ERROR)
            # 更新执行掩码后调用真实ufunc。
            selected &= ~zero
        # 浮点overflow/invalid转质量，不向外伪报正常数值。
        with np.errstate(over='ignore', invalid='ignore', divide='raise'):
            # 静态分派既包括比较又包括算术。
            ufunc = COMPARE_UFUNCS[operator] if operator in COMPARISONS else {'add': np.add, 'sub': np.subtract, 'mul': np.multiply, 'div': np.divide}[operator]
            # where保证invalid及除零位置未执行。
            ufunc(a.values, b.values, out=values, where=selected)
        # 正常float结果非有限需要新增诊断，bool结果不会非有限。
        if dtype is SignalDType.FLOAT64:
            # 只标记实际执行位置，不污染invalid占位。
            quality[selected & ~np.isfinite(values)] |= np.uint16(QualityFlag.NONFINITE)
        # 构造输出前模型保证所有valid浮点有限。
        return _output(dtype, values, quality)
    # 剩余路径都是同dtype整数+/-/*。
    values, overflow = _integer_arithmetic(operator, left.values, right.values, selected)
    # 精确门槛失败原因与上游质量共存。
    quality[overflow] |= np.uint16(QualityFlag.OVERFLOW)
    # 溢出0只是无效存储占位，不能当成功值。
    return _output(dtype, values, quality)


def unary_numpy(operator: str, value: NumericArray) -> NumericArray:
    """独立数组abs/neg，signed min和unsigned负号先拒绝。

    参数: operator为abs/neg；value为数值列。
    返回: 同dtype列及保留/新增质量，shape保持。
    异常: TypeError/ValueError为结构/未知运算，分配错误传播。
    """
    # 不接受逻辑数值化或任意函数。
    if not isinstance(value, NumericArray) or value.dtype in (SignalDType.BOOL, SignalDType.ENUM) or operator not in ('abs', 'neg'):
        # 与参考输入拒绝语义一致。
        raise ValueError('unary仅支持数值abs/neg')
    # 输入原因先复制，输出独立存储。
    quality = value.quality.copy()
    # invalid占位从不作为正常结果使用。
    result = np.zeros_like(value.values)
    # 只有正常输入需检查目标定宽。
    overflow = np.zeros(len(result), dtype=bool)
    # signed min abs/neg均超上界。
    if value.dtype is SignalDType.INT64:
        # 不先执行危险abs(min)或neg(min)。
        overflow = value.valid & (value.values == np.int64(-(2 ** 63)))
    # 无符号abs恒合法，只有neg需要下溢检查。
    elif value.dtype is SignalDType.UINT64 and operator == 'neg':
        # 非零unsigned负号必然下溢；0合法。
        overflow = value.valid & (value.values != 0)
    # 静态ufunc仅对已证明安全的位置执行。
    ufunc = np.absolute if operator == 'abs' else np.negative
    # unsigned neg允许位置仅0，不wrap。
    ufunc(value.values, out=result, where=value.valid & ~overflow)
    # 失败原因独立可追溯。
    quality[overflow] |= np.uint16(QualityFlag.OVERFLOW)
    # 不改变输入布局或质量。
    return _output(value.dtype, result, quality)
