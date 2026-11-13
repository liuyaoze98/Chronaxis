"""把明确单位的时间数值或完整日期转换为整数纳秒，并保存转换诊断。

数值入口接收声明为s、ms、us或ns的整数、十进制文本、Decimal或已有float；
日期入口接收完整ISO日期。输出为int64纳秒及输入表示、舍入和时区信息。
换算通过十进制系数和指数完成，只在最终纳秒处舍入；恰好半值时取最近偶数，
不受Decimal全局精度影响，也不经过浮点UTC秒数。
日期中的明确时区偏移优先；无偏移时须传入tzinfo，重复或不存在的本地时刻
会被拒绝。已有浮点的上游精度无法恢复。单值最多4096位有效数字，极大指数
先判断溢出或舍零，不分配无界的10次幂。
参考加减先用Python整数计算再检查范围，独立于NumPy实现。本模块仅依赖
标准库，不读取文件、不使用机器默认时区，也不持有会话或日志状态。
"""

# 标准库负责精确输入表示、冻结诊断、时区与序列类型；不导入数值后端。
import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone, tzinfo
from decimal import Decimal, InvalidOperation
from numbers import Integral
from typing import Sequence

# int64纳秒协议允许负坐标，但不允许任何算术wrap。
INT64_MIN = -(1 << 63)
# 正端点与负端点不对称，所有精确计算完成后按此上界拒绝溢出。
INT64_MAX = (1 << 63) - 1
# 单位按10的幂转换，避免先乘float导致绝对时间失真。
UNIT_EXPONENTS = {"ns": 0, "us": 3, "ms": 6, "s": 9}
# 时间参数只接受完整数值和明确后缀；单位大小写敏感。
DURATION_PATTERN = re.compile(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)(ns|us|ms|s)")
# 日期支持完整秒及任意十进制分数，不由datetime截断亚微秒。
DATETIME_PATTERN = re.compile(
    r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})?"
)
# UTC原点只表达坐标，不将相对来源自动绑定到这个原点。
UTC_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class TimeOverflowError(OverflowError):
    """时间坐标、偏移后坐标或非负跨度超出int64时拒绝运算。

    异常不携带可被误用的回绕结果；失败由调用者记录为任务校验错误。
    本类型没有可变状态，不打开资源或把失败当正常零时长。
    """


@dataclass(frozen=True)
class TimeConversion:
    """保存规范时间及来源精度，避免跨任务修改转换诊断。

    time_ns经入口校验为int64；quantized表示实际纳秒舍入发生，浮点限制
    与量化分别记录。input_text保留转换所见表示，不证明上游原始精度。
    source_timezone仅记录日期采用的时区，不替代多源同步依据。
    """

    time_ns: int  # 核心坐标或时长，单位纳秒，有符号64位范围。
    input_representation: str  # integer/decimal_text/decimal/binary_float/ISO8601等实际来源。
    input_unit: str  # 明确声明的s/ms/us/ns，日期入口使用ISO8601。
    input_text: str  # 当前入口所见文本；不记录用户日志或假设更高源精度。
    quantized: bool  # 原精确表示不能整纳秒表示时为True，包括舍为0。
    precision_limited: bool = False  # 浮点输入只能规范化其已有精度。
    rounding: str = "round_half_even"  # 最终纳秒固定采用最近偶数舍入。
    source_timezone: str | None = None  # 日期实际采用的tzinfo说明，纯数值不猜。


def require_int64_ns(value: int, field: str = "time_ns") -> int:
    """校验整数纳秒协议，明确拒绝布尔、浮点和越界。

    参数:
        value (Integral): 时间整数，允许NumPy整数标量，不允许bool。
        field (str): 错误定位字段，默认time_ns。
    返回:
        int: 独立Python整数，保留原精确值。
    异常:
        TypeError: 非整数或bool，不能靠隐式截断转换。
        TimeOverflowError: 超出有符号64位纳秒范围。
    """
    # 记录流已规范为原生整数，直接核范围避免每次查询Integral注册关系。
    # 精确类型判断不会把bool或自定义整数子类当成这一分支。
    if type(value) is int:
        if not INT64_MIN <= value <= INT64_MAX:
            raise TimeOverflowError(f"{field}超出int64纳秒范围")
        return value
    # bool虽是Python整数子类，时间协议不得把True当1ns。
    if isinstance(value, bool) or not isinstance(value, Integral):
        # 输入类型错误在运算之前定位，不生成正常结果。
        raise TypeError(f"{field}必须为整数纳秒，不能为布尔或浮点")
    # 归一为Python整数只改变容器类型，不损失NumPy整数的位值。
    result = int(value)
    # 两侧边界包含；后续数组运算只能使用此范围内的时间。
    if not INT64_MIN <= result <= INT64_MAX:
        # 不返回wrap或饱和值，超界就是失败。
        raise TimeOverflowError(f"{field}超出int64纳秒范围")
    # 返回已校验值供时间协议与数组形状校验共享。
    return result


def _decimal_input(value: int | float | str | Decimal) -> tuple[Decimal, str, str]:
    """取得精确的输入表示，不受全局Decimal计算精度影响。

    参数:
        value: 整数、十进制文本、Decimal或当前已有的float。
    返回:
        tuple: 精确Decimal、表示类型、原入口文本。
    异常:
        TypeError: 布尔或未支持的类型。
        ValueError: 空文本或非法文本、非有限值或超过4096位有效数字。
    """
    # 布尔不是时间，提前阻止其走整数路径。
    if isinstance(value, bool):
        # 类型拒绝明确，不采用Python隐式真值判断。
        raise TypeError("布尔值不能表示时间")
    # 文本保留十进制精度，不先解析为浮点。
    if isinstance(value, str):
        # 两端空白不代表精度或单位，数字主体按Decimal解析。
        text = value.strip()
        # 表示类型写入转换记录用于追溯。
        representation = "decimal_text"
        # 只拦截语法错误，不吞掉溢出或其他实现异常。
        try:
            # Decimal构造从文本取得完整系数，不执行上下文舍入。
            number = Decimal(text)
        except InvalidOperation as error:
            # 带明确类型的错误交给计划/来源边界处理。
            raise ValueError("非法十进制时间文本") from error
    elif isinstance(value, Integral):
        # 源整数可以比int64大，最终量纲变换后再判范围。
        number, representation, text = Decimal(int(value)), "integer", str(value)
    elif isinstance(value, float):
        # 按当前二进制值精确展开，不将repr十进制当作未损失源数据。
        number, representation, text = Decimal.from_float(value), "binary_float", repr(value)
    elif isinstance(value, Decimal):
        # Decimal对象原样读取，没有重新量化为固定全局精度。
        number, representation, text = value, "decimal", str(value)
    else:
        # 不接受任意对象隐式转str或float，防止时间含义被猜测。
        raise TypeError("时间仅接受整数、十进制文本、Decimal或float")
    # 非有限值没有有效时间坐标，不映射为0或极值。
    if not number.is_finite():
        # 同时拒绝NaN、Infinity及已有非有限浮点。
        raise ValueError("时间必须为有限数值")
    # 限制数字主体规模，指数另用符号和位数判断，避免构造巨大整数。
    if len(number.as_tuple().digits) > 4096:
        # 明示此入口资源界限，不声称接受任意长度数值文本。
        raise ValueError("时间超过4096位有效数字限制")
    # 返回解析事实，实际纳秒运算由下一层进行。
    return number, representation, text


def convert_time(value: int | float | str | Decimal, unit: str) -> TimeConversion:
    """按明确单位换算纳秒，并在最终结果处取最近偶数舍入。

    参数:
        value: 有限整数、十进制文本、Decimal或已有float，允许负时间坐标。
        unit (str): 大小写敏感的s、ms、us或ns；没有默认单位。
    返回:
        TimeConversion: 整数纳秒、输入表示与单位，以及是否发生纳秒舍入和
        是否受已有浮点精度限制的诊断。
    异常:
        TypeError或ValueError: 输入类型、文本语法、有效数字长度或单位不合法。
        TimeOverflowError: 舍入后的结果超出int64范围。
    处理流程:
        分离符号、系数和指数，在整数域缩放或求商余数，再舍入到整纳秒。
        极大正指数提前拒绝；极大负指数直接判定舍为0，避免无界分配。
    副作用:
        无，不修改输入、Decimal上下文或时间基准。
    """
    # 单位必须显式属于当前协议，不猜测秒或自动改大小写。
    if not isinstance(unit, str) or unit not in UNIT_EXPONENTS:
        # 错误是配置问题，不是正常未知样本。
        raise ValueError("时间单位必须为s/ms/us/ns")
    # 得到与输入类型对应的精确表示和来源诊断。
    number, representation, text = _decimal_input(value)
    # tuple不做十进制算术，因此不受调用者的精度/舍入模式影响。
    sign, digits, exponent = number.as_tuple()
    # 有效数字最多4096，Python整数可精确保留这一受限系数。
    coefficient = int("".join(str(digit) for digit in digits))
    # 同一整数尺度下相加指数，不先乘float或Decimal上下文数值。
    shift = exponent + UNIT_EXPONENTS[unit]
    # 精确0在任意指数下仍为0，不触发巨大幂或量化。
    if coefficient == 0:
        # 正负零不影响时间轴，记录无实际量化。
        magnitude, quantized = 0, False
    elif shift >= 0:
        # int64绝对值至多19位，超过则在分配10次幂前失败。
        if len(digits) + shift > 19:
            # 溢出不通过舍入、截断或wrap绕过。
            raise TimeOverflowError("单位换算后超出int64纳秒范围")
        # 仅对可表示数量级进行精确整数乘法。
        magnitude, quantized = coefficient * (10 ** shift), False
    elif -shift > len(digits):
        # 数量级严格小于0.1ns，必定舍至0，不需生成巨大分母。
        magnitude, quantized = 0, True
    else:
        # 剩余负指数至多4096，受输入位数限制，不产生无界分配。
        divisor = 10 ** (-shift)
        # 在非负系数上求商余，负号最后应用可对称处理负半值。
        magnitude, remainder = divmod(coefficient, divisor)
        # 严格超过半值进位，恰好半值仅在商为奇数时进位。
        if 2 * remainder > divisor or (2 * remainder == divisor and magnitude % 2 == 1):
            # 进位后的int64合法性仍必须在下一步校验。
            magnitude += 1
        # 仅实际非零余数表示量化，保留完整整纳秒输入的False。
        quantized = remainder != 0
    # 保留负号并检查正负边界，不把MIN绝对值转换为int64中间值。
    time_ns = require_int64_ns(-magnitude if sign else magnitude)
    # 冻结诊断区分实际纳秒量化与上游浮点已有限精度。
    return TimeConversion(time_ns, representation, unit, text, quantized, representation == "binary_float")


def parse_duration(text: str) -> TimeConversion:
    """解析带单位的非负持续参数，允许显式零长度。

    参数:
        text (str): 完整数值后缀，如500ms、3s、0ns。
    返回:
        TimeConversion: 纳秒持续时间，原带单位文本保留。
    异常:
        TypeError: 非文本。
        ValueError: 缺单位、非法语法或原数值为负，即使负小值会舍为0。
        TimeOverflowError: 换算/舍入超int64。
    """
    # 配置参数须为明确单位字符串，不默认将数字解释为秒。
    if not isinstance(text, str):
        # 错误定位为参数类型，不调用任意对象字符串方法。
        raise TypeError("持续参数必须为带单位文本")
    # fullmatch禁止余留不明字符或叠加单位。
    match = DURATION_PATTERN.fullmatch(text.strip())
    # 无匹配即缺失或非法数值/单位，不能只解析前缀。
    if match is None:
        # 给出当前真实支持范围，不声明其他配置解析已实现。
        raise ValueError("持续参数格式应为数值+s/ms/us/ns")
    # 原始负参数在量化前拒绝，防止-0.1ns舍为0后绕过约束。
    if Decimal(match[1]) < 0:
        # 固定持续不能反向，负时间坐标应使用convert_time入口。
        raise ValueError("持续参数不能为负")
    # 仅换算一次，实际元数据仍由精确入口生成。
    result = convert_time(match[1], match[2])
    # 原带单位文本保留，记录它是配置持续而非单独数值字符串。
    return replace(result, input_text=text, input_representation="duration_text")


def parse_datetime_ns(text: str, source_timezone: tzinfo | None = None) -> TimeConversion:
    """将ISO完整日期转换为UTC整数纳秒，保留亚微秒分数。

    参数:
        text (str): YYYY-MM-DDTHH:MM:SS[.fraction][Z/±HH:MM]，也允许空格分隔。
        source_timezone (tzinfo|None): 无offset时必须提供；显式offset优先。
    返回:
        TimeConversion: UTC epoch纳秒、量化与实际采用时区，非机器默认。
    异常:
        TypeError/ValueError: 文本/时区非法、naive缺时区、本地时刻模糊或不存在。
        TimeOverflowError: int64时间超界。
        OverflowError: 转到UTC时超出datetime历法边界。
    副作用:
        无；不调用系统本地时区，不加载IANA名称或访问文件。
    """
    # 日期输入必须为完整文本，不从文件名、机器地区或对象repr猜测。
    if not isinstance(text, str):
        # 错误类型在任何时区操作前拒绝。
        raise TypeError("日期必须为ISO文本")
    # 固定语法将任意长度秒分数独立保留，datetime仅处理整秒。
    match = DATETIME_PATTERN.fullmatch(text.strip())
    # 完整日期/offset格式不满足时，不能只解析一部分。
    if match is None:
        # 不声明日期-only、闰秒或任意厂商时间语法可用。
        raise ValueError("日期须为完整ISO年月日时分秒及可选offset")
    # 整秒基础与offset由datetime校验历法，分数不被微秒截断。
    base, fraction, offset = match.groups()
    # 标准库会归一化+00:60等偏移；文本分量须先严格拒绝非法范围。
    if offset is not None and offset != "Z":
        # 显式±HH:MM两个分量分别校验，不能用合计秒数掩盖非法分钟。
        if int(offset[1:3]) > 23 or int(offset[4:6]) > 59:
            # 时区偏移不是允许自动进位的时长，来源错误必须可见。
            raise ValueError("ISO offset小时须为00—23、分钟须为00—59")
    # UTC Z显式变换为等价offset文本，不改变物理时刻。
    whole = datetime.fromisoformat(base + ("+00:00" if offset == "Z" else offset or ""))
    # 只有没有时区偏移的日期输入需要调用者的来源时区。
    if whole.tzinfo is None:
        # 不用宿主机器时区作为隐式来源事实。
        if not isinstance(source_timezone, tzinfo):
            # 缺项在执行前明确定位。
            raise ValueError("无offset日期必须声明source_timezone")
        # 同一墙钟时刻采用fold0/1只检查歧义，不静默选择某个重复时刻。
        whole = whole.replace(tzinfo=source_timezone)
        # 不同fold偏移意味着模糊或跳空，来源应改为明确offset。
        if whole.utcoffset() is None or whole.utcoffset() != whole.replace(fold=1).utcoffset():
            # 拒绝无法唯一定位的本地时刻，不制造顺序可靠的假时间。
            raise ValueError("来源时区下时刻不唯一或不存在，请使用明确offset")
        # 往返校验捕获同offset也无法返回原墙钟值的时区映射。
        roundtrip = whole.astimezone(timezone.utc).astimezone(source_timezone)
        # 不存在的墙钟时间不能被时区库规范化后静默接受。
        if roundtrip.replace(tzinfo=None) != whole.replace(tzinfo=None):
            # 保留明确的失败原因，不当作正常数值0。
            raise ValueError("来源时区下本地时刻不存在")
    # 在UTC整数timedelta域保留天/秒/微秒，不用timestamp浮点方法。
    delta = whole.astimezone(timezone.utc) - UTC_EPOCH
    # 来源tzinfo可含微秒offset；UTC基准保留亚秒，最终范围在加原分数后检查。
    base_ns = (delta.days * 86400 + delta.seconds) * 1_000_000_000 + delta.microseconds * 1000
    # 小数由相同精确量化协议处理，允许舍入进位到下一秒。
    partial = convert_time("0." + (fraction or "0"), "s")
    # 时区基准是1000ns的整数倍，不影响原分数最近偶数舍入的奇偶判定，最终检查坐标。
    result_ns = require_int64_ns(base_ns + partial.time_ns)
    # 日期原文本和实际tzinfo写入诊断，当前解析没有浮点精度限制。
    return TimeConversion(result_ns, "ISO8601", "ISO8601", text, partial.quantized, source_timezone=str(whole.tzinfo))


def checked_add_ns(time_ns: int, offset_ns: int) -> int:
    """为一个纳秒坐标添加固定偏移，并检查结果是否仍在int64范围内。

    参数:
        time_ns (Integral): 已满足int64范围的原时间坐标，单位为纳秒。
        offset_ns (Integral): 已满足int64范围的固定偏移，单位为纳秒。
    返回:
        int: 精确的新坐标；成功相加不表示不同来源已经同步。
    异常:
        TypeError: 任一输入不是非布尔整数。
        TimeOverflowError: 任一输入或相加结果超出int64范围。
    """
    # 两个参数各自满足协议，禁止使用超界offset抵消超界输入。
    source, offset = require_int64_ns(time_ns), require_int64_ns(offset_ns, "offset_ns")
    # Python中间值不wrap，最终显式检查结果。
    return require_int64_ns(source + offset, "shifted_time_ns")


def shift_times_reference(times: Sequence[int], offset_ns: int) -> tuple[int, ...]:
    """逐项独立计算固定偏移，作为数组内核的整数真值参考。

    参数:
        times (Sequence[Integral]): 已声明纳秒坐标，不要求排序。
        offset_ns (Integral): 合法int64固定偏移。
    返回:
        tuple[int,...]: 新整数序列，空输入返回空tuple。
    异常:
        TypeError/TimeOverflowError: 参数类型或任一坐标/结果超界。
    副作用:
        无；不导入或调用NumPy实现，不修改输入。
    """
    # 空序列也先检查offset，非法配置不能因没有样本而通过。
    offset = require_int64_ns(offset_ns, "offset_ns")
    # 标量检查/相加提供独立参考路径，不进行数组运算或隐式浮点转换。
    return tuple(checked_add_ns(value, offset) for value in times)


def time_deltas_reference(times: Sequence[int]) -> tuple[int, ...]:
    """计算非递减整数时间的相邻跨度，允许同时间不同样本。

    参数:
        times (Sequence[Integral]): 来源顺序的int64纳秒，允许重复坐标。
    返回:
        tuple[int,...]: 长度max(N-1,0)的非负int64跨度。
    异常:
        TypeError/ValueError: 非整数或来源内时间回退。
        TimeOverflowError: 输入或跨度超界，即使两端各自合法。
    副作用:
        无；Python整数参考不调用NumPy内核，也不排序或去重。
    """
    # 先验证所有坐标，单点/空输入也不掩盖非法坐标。
    checked = tuple(require_int64_ns(value) for value in times)
    # 输出单独保存，不能修改调用者序列。
    result = []
    # 相邻跨度在Python整数域计算，避免绝对时间先转float失去1ns。
    for left, right in zip(checked, checked[1:]):
        # 负跨度表示来源乱序，首版明确拒绝而非排序旧输出。
        if right < left:
            # 同时间合法；这里只拒绝严格回退。
            raise ValueError("时间序列必须非递减")
        # 大跨符号差值可能超过MAX，先以精确整数取得再校验。
        result.append(require_int64_ns(right - left, "delta_ns"))
    # 返回只读参考结果，空/单点自然无相邻跨度。
    return tuple(result)
