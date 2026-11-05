"""在编译期解析版本4的有限单位目录，并推导转换及复合单位。

输入为单位文本或不可变Unit，输出单位元数据及转换系数，不处理样本值。
物理量纲和量种分别检查；有理数与π倍率保持符号形式，避免提前舍入。
解析器仅接受登记原子及有限乘除幂语法，不使用eval、不读写文件。
本模块是当前配置唯一的单位目录；未知标签不会隐式使用其他单位表。
"""

# 所有对象仅依赖标准库，登记表建成后不允许调用侧修改。
from dataclasses import dataclass
from fractions import Fraction
from math import isfinite, isqrt, pi
import re
from types import MappingProxyType


REGISTRY_VERSION = "chronaxis-units-v4.1"
KIND_BASES = ("V", "A", "s", "N", "m", "K", "delta_K", "rad")
# 各量种在质量、长度、时间、电流、温度五个物理维度上的指数。
_PHYSICAL_BASES = (
    (1, 2, -3, -1, 0), (0, 0, 0, 1, 0), (0, 0, 1, 0, 0),
    (1, 1, -2, 0, 0), (0, 1, 0, 0, 0), (0, 0, 0, 0, 1),
    (0, 0, 0, 0, 1), (0, 0, 0, 0, 0),
)
_MAX_EXPONENT = 32
_MAX_FACTOR_BITS = 4096


def _indices(value: tuple[int, ...], size: int, field: str, *, bounded: bool = True) -> None:
    """检查不可变指数向量，拒绝布尔值和超限幂。

    参数: value为指数tuple，size为维数，field用于错误定位；bounded决定是否限制±32。
    返回: None。
    异常: TypeError为结构或类型错误，ValueError为指数超限。
    """
    # bool是int子类，必须按精确类型检查，防止非法元数据混入。
    if type(value) is not tuple or len(value) != size or any(type(item) is not int for item in value):
        raise TypeError(f"{field}必须为{size}个整数构成的tuple")
    if bounded and any(abs(item) > _MAX_EXPONENT for item in value):
        raise ValueError(f"{field}组合指数必须在-32到32之间")


def _dimensions(kind: tuple[int, ...]) -> tuple[int, ...]:
    """从量种基计算物理量纲，不据量纲反猜量种。

    参数: kind为八维量种指数。
    返回: 质量、长度、时间、电流、温度的五维指数。
    异常: 调用方负责输入结构检查。
    """
    # 同物理量纲仍可能是能量/力矩等不同量种。
    return tuple(sum(power * basis[index] for power, basis in zip(kind, _PHYSICAL_BASES)) for index in range(5))


@dataclass(frozen=True)
class Scale:
    """保存正有理系数乘π整数次幂，只有执行前才转float64。

    factor与pi_power不可变；负方向属于信号转换，不属于单位倍率。
    分子和分母分别最多4096位，避免无量纲嵌套幂绕过量种指数限制。
    """

    factor: Fraction  # 正有理倍率，保持十进制换算精确。
    pi_power: int = 0  # π指数，用于角度与角速度转换。

    def __post_init__(self) -> None:
        """检查倍率结构及范围。

        参数: 无。
        返回: None。
        异常: TypeError为类型错误，ValueError为非正倍率、指数或有理数位数超限。
        """
        # 不把传入浮点近似自动伪装成精确的单位常数。
        if type(self.factor) is not Fraction or type(self.pi_power) is not int:
            raise TypeError("Scale需要Fraction倍率和整数π指数")
        if self.factor <= 0 or abs(self.pi_power) > _MAX_EXPONENT:
            raise ValueError("单位倍率必须为正，π指数必须在-32到32之间")
        # 无量纲幂不增加kind指数，必须单独限制精确有理数的存储规模。
        if self.factor.numerator.bit_length() > _MAX_FACTOR_BITS or self.factor.denominator.bit_length() > _MAX_FACTOR_BITS:
            raise ValueError("单位倍率的分子或分母超过4096位限制")

    def to_float(self) -> float:
        """在数值执行边界取得有限float倍率。

        参数: 无。
        返回: 正有限float；π取math.pi的float64表示，整体倍率最后统一舍入。
        异常: ValueError为上溢、下溢到零或非有限结果。
        """
        # 先在有界有理数内组合π近似，避免factor单独溢出而最终倍率本来可表示。
        try:
            value = float(self.factor * Fraction.from_float(pi) ** self.pi_power)
        except OverflowError as error:
            raise ValueError("单位倍率不能表示为有限float64") from error
        if not isfinite(value) or value <= 0:
            raise ValueError("单位倍率不能表示为正有限float64")
        return value

    def multiply(self, other: "Scale") -> "Scale":
        """相乘两个符号倍率。

        参数: other为Scale。
        返回: 新Scale，不舍入。
        异常: TypeError为输入类型错误，ValueError为指数超限。
        """
        # 先核实对象，避免通过任意属性调用构造未知倍率。
        if not isinstance(other, Scale):
            raise TypeError("倍率乘法需要Scale")
        return Scale(self.factor * other.factor, self.pi_power + other.pi_power)

    def divide(self, other: "Scale") -> "Scale":
        """相除两个正符号倍率。

        参数: other为Scale。
        返回: 新Scale，不舍入。
        异常: TypeError为输入类型错误，ValueError为指数超限。
        """
        # 单位倍率已保证非零，因此此处不会产生正常除零分支。
        if not isinstance(other, Scale):
            raise TypeError("倍率除法需要Scale")
        return Scale(self.factor / other.factor, self.pi_power - other.pi_power)

    def power(self, exponent: int) -> "Scale":
        """对符号倍率求有界整数幂。

        参数: exponent为-32到32的原生整数。
        返回: 新Scale。
        异常: TypeError为非整数，ValueError为幂或结果指数超限。
        """
        # 文本幂和内部平方共用同一明确边界。
        if type(exponent) is not int:
            raise TypeError("单位幂必须为整数")
        if abs(exponent) > _MAX_EXPONENT:
            raise ValueError("单位幂必须在-32到32之间")
        return Scale(self.factor ** exponent, self.pi_power * exponent)

    def square_root(self) -> "Scale":
        """对可精确开方的符号倍率取正平方根。

        参数: 无。
        返回: 新Scale。
        异常: ValueError为有理系数非完全平方或π指数为奇数。
        """
        # 不引入未定义的根号常数，也不以浮点近似替代精确身份。
        numerator = isqrt(self.factor.numerator)
        denominator = isqrt(self.factor.denominator)
        if numerator * numerator != self.factor.numerator or denominator * denominator != self.factor.denominator or self.pi_power % 2:
            raise ValueError("单位倍率不能在有理数和整数π幂范围内精确开方")
        return Scale(Fraction(numerator, denominator), self.pi_power // 2)


@dataclass(frozen=True)
class Unit:
    """保存单位拼写、物理量纲、量种、倍率及可选温度偏移。

    数值换到基准的公式为value*scale+offset；偏移仅用于绝对温度。
    量种指数独立区分能量、力矩、角度、比例及绝对温度/温差。
    symbol可以是中间代数描述；只有canonical_unit返回的symbol保证可重读。
    """

    symbol: str  # 当前表示的单位文本，复合表示可不同于基准名称。
    dimensions: tuple[int, ...]  # 质量、长度、时间、电流、温度。
    kind: tuple[int, ...]  # KIND_BASES顺序的八维量种指数。
    scale: Scale  # 相对量种基准的符号倍率。
    offset: Fraction = Fraction(0)  # 基准单位中的偏移，如273.15K。
    temperature_role: str | None = None  # absolute、delta或非单一温度。

    def __post_init__(self) -> None:
        """验证模型不变量，防止手工构造伪造量纲或温度角色。

        参数: 无。
        返回: None。
        异常: TypeError为结构错误，ValueError为量纲/量种/角色不一致。
        """
        # 模型不承接任意对象转换；语法限制由文本入口负责。
        if type(self.symbol) is not str or not self.symbol.strip() or not isinstance(self.scale, Scale) or type(self.offset) is not Fraction:
            raise TypeError("Unit需要非空文本、Scale及Fraction偏移")
        _indices(self.kind, 8, "kind")
        # 物理指数由有界kind唯一推导，不再单设同样上限误拒V^32等合法单位。
        _indices(self.dimensions, 5, "dimensions", bounded=False)
        if self.dimensions != _dimensions(self.kind):
            raise ValueError("物理量纲与量种指数不一致")
        if self.temperature_role != _temperature_role(self.kind):
            raise ValueError("温度角色与量种指数不一致")
        if self.offset and (self.temperature_role != "absolute" or self.scale.pi_power):
            raise ValueError("偏移仅用于无π倍率的绝对温度")


def _temperature_role(kind: tuple[int, ...]) -> str | None:
    """仅为单一绝对温度或温差赋角色，复合温度仍由量种指数区分。

    参数: kind为八维指数。
    返回: absolute、delta或None。
    异常: 无，结构由调用方检查。
    """
    # K²与delta_K²的区别留在量种基中，不伪装成单一温度。
    if kind == (0, 0, 0, 0, 0, 1, 0, 0):
        return "absolute"
    if kind == (0, 0, 0, 0, 0, 0, 1, 0):
        return "delta"
    return None


def _make(symbol: str, kind: tuple[int, ...], scale: Scale | None = None,
          offset: Fraction = Fraction(0)) -> Unit:
    """从量种统一构造含一致物理量纲和温度角色的单位。

    参数: symbol为拼写，kind为八维指数，scale缺省1，offset缺省0。
    返回: 已校验Unit。
    异常: Unit验证错误直接传播。
    """
    # 所有代数运算使用同一构造步骤，避免遗漏派生温度角色。
    return Unit(symbol, _dimensions(kind), kind, scale or Scale(Fraction(1)), offset, _temperature_role(kind))


def _require_unit(value: Unit) -> None:
    """检查单位代数入口的typed对象。

    参数: value为待检查对象。
    返回: None。
    异常: TypeError为非Unit对象。
    """
    # 未知单位必须由上层保留unverified，不能当成无量纲计算。
    if not isinstance(value, Unit):
        raise TypeError("单位运算需要已解析的Unit")


def _require_multiplicative(value: Unit) -> None:
    """拒绝带偏移温度参与乘除和幂运算。

    参数: value为Unit。
    返回: None。
    异常: TypeError为非Unit；ValueError为带偏移单位。
    """
    # 在自动规范化之前检查，不能把摄氏度偷偷转换成K绕过限制。
    _require_unit(value)
    if value.offset:
        raise ValueError("带偏移的温度不能直接乘除或求幂，请先显式转换到K")


def multiply(left: Unit, right: Unit) -> Unit:
    """组合单位乘法，保留数值仍需应用的原尺度。

    参数: left、right为已解析Unit。
    返回: 量种指数相加、倍率相乘的新Unit。
    异常: TypeError为类型错误；ValueError为偏移单位或指数超限。
    """
    # 仅组合元数据，不改数值表达式的计算结合顺序。
    _require_multiplicative(left)
    _require_multiplicative(right)
    kind = tuple(a + b for a, b in zip(left.kind, right.kind))
    return _make(f"({left.symbol})*({right.symbol})", kind, left.scale.multiply(right.scale))


def divide(left: Unit, right: Unit) -> Unit:
    """组合单位除法，量种相同的比值成为普通比例。

    参数: left、right为已解析Unit。
    返回: 指数相减、倍率相除的新Unit。
    异常: TypeError为类型错误；ValueError为偏移单位或指数超限。
    """
    # 单位的除法不判断样本分母值，实际除零由数值核处理。
    _require_multiplicative(left)
    _require_multiplicative(right)
    kind = tuple(a - b for a, b in zip(left.kind, right.kind))
    return _make(f"({left.symbol})/({right.symbol})", kind, left.scale.divide(right.scale))


def _power(unit: Unit, exponent: int) -> Unit:
    """处理解析器和平方共用的有界单位整数幂。

    参数: unit为Unit，exponent为-32到32整数。
    返回: 新Unit。
    异常: TypeError为类型错误；ValueError为偏移温度、幂或组合超限。
    """
    # 即使幂为0或1，也不能让偏移温度走乘法语义。
    _require_multiplicative(unit)
    scale = unit.scale.power(exponent)
    return _make(f"({unit.symbol})^{exponent}", tuple(value * exponent for value in unit.kind), scale)


def square(unit: Unit) -> Unit:
    """求单位平方，同时平方其倍率。

    参数: unit为Unit。
    返回: 新Unit。
    异常: TypeError或ValueError沿单位幂检查传播。
    """
    # 实际样本平方的溢出检查属于两个数值后端。
    return _power(unit, 2)


def square_root(unit: Unit) -> Unit:
    """对偶数量种指数和可精确开方倍率求平方根。

    参数: unit为Unit。
    返回: 新Unit；K²返回K量种，温差平方返回温差量种。非原子尺度的symbol
        只供内部描述；公开显示或重新解析应先取canonical_unit。
    异常: TypeError为类型错误；ValueError为偏移、奇数指数或非精确倍率。
    边界: 数值编译器先把输入转为规范基准再开方，不能据中间倍率非完全平方
        拒绝本来合法的sqrt(mA*A)；本函数自身不转换样本数值。
    """
    # 只检查物理维度会把rad误认为普通比例，必须逐个检查量种基。
    _require_multiplicative(unit)
    if any(value % 2 for value in unit.kind):
        raise ValueError("开方要求所有量种指数为偶数")
    kind = tuple(value // 2 for value in unit.kind)
    scale = unit.scale.square_root()
    # 返回规范基名或与其尺度等价的原子名，避免构造不允许的sqrt文本。
    base = canonical_unit(_make("root", kind))
    for candidate in ATOMIC_UNITS.values():
        if candidate.kind == kind and candidate.scale == scale and not candidate.offset:
            return candidate
    if scale == Scale(Fraction(1)):
        return base
    return _make(f"sqrt({unit.symbol})", kind, scale)


def conversion(source: Unit, target: Unit) -> tuple[Scale, Fraction]:
    """计算source数值到target的乘法系数和加法偏移。

    参数: source、target为已解析Unit。
    返回: (scale,offset)，数值公式为value*scale+offset。
    异常: TypeError为非Unit；ValueError为量种、温度角色或偏移不兼容。
    """
    # 不能以物理指数相同为由把力矩、角度或温差变成另一种量。
    _require_unit(source)
    _require_unit(target)
    if source.kind != target.kind or source.temperature_role != target.temperature_role:
        raise ValueError(f"单位量种不兼容：{source.symbol}→{target.symbol}")
    difference = source.offset - target.offset
    if difference and target.scale.pi_power:
        raise ValueError("带π的目标倍率不能承接温度偏移")
    return source.scale.divide(target.scale), difference / target.scale.factor


def _kind_symbol(kind: tuple[int, ...]) -> str:
    """为未命名量种构造固定基顺序的可解析乘除文本。

    参数: kind为八维整数指数。
    返回: 只含规范原子和乘除幂的文本。
    异常: 无，模型已限制指数。
    """
    # 分母多项必须加括号，避免a/b*c与a/(b*c)混淆。
    numerator = []
    denominator = []
    for base, exponent in zip(KIND_BASES, kind):
        if not exponent:
            continue
        destination = numerator if exponent > 0 else denominator
        power = abs(exponent)
        destination.append(base if power == 1 else f"{base}^{power}")
    top = "*".join(numerator) or "1"
    if not denominator:
        return top
    bottom = "*".join(denominator)
    return f"{top}/{bottom}" if len(denominator) == 1 else f"{top}/({bottom})"


def canonical_unit(unit: Unit) -> Unit:
    """取得该量种倍率1、偏移0的稳定计算/显示基准。

    参数: unit为Unit。
    返回: 首选规范单位或由固定量种基构造的单位。
    异常: TypeError为非Unit，ValueError为模型不一致。
    """
    # 此函数只返回目标，调用者必须应用conversion而不是只替换标签。
    _require_unit(unit)
    if unit.kind in PREFERRED_UNITS:
        return PREFERRED_UNITS[unit.kind]
    return _make(_kind_symbol(unit.kind), unit.kind)


def output_label(unit: Unit, spelling: str) -> str:
    """为所选尺度返回可重新解析的输出单位名称。

    参数: unit是已解析目标；spelling是生成它的单位文本。
    返回: 原子单位用登记名称，基准组合用规范名称，其他倍率保留原拼写。
    异常: 调用者须先解析单位；非法模型沿用注册表检查。
    """
    # 不能把非基准复合单位直接换成基准标签，否则标签和数值倍率不符。
    if unit.symbol in ATOMIC_UNITS:
        return unit.symbol
    base = canonical_unit(unit)
    return base.symbol if (unit.scale, unit.offset) == (base.scale, base.offset) else spelling.strip()


def _build_atoms() -> dict[str, Unit]:
    """建立有限原子表，不自动扩张SI前缀或读取外部定义。

    参数: 无。
    返回: 供模块初始化冻结的字典。
    异常: 注册项不一致时传播Unit验证错误。
    """
    # 每项明确给出量种、尺度和偏移；这里只生成编译期少量对象。
    zero = (0,) * 8
    definitions = {"1": _make("1", zero), "%": _make("%", zero, Scale(Fraction(1, 100)))}
    for index, name in enumerate(KIND_BASES):
        kind = tuple(int(position == index) for position in range(8))
        definitions[name] = _make(name, kind)
    composites = {
        "W": (1, 1, 0, 0, 0, 0, 0, 0), "J": (1, 1, 1, 0, 0, 0, 0, 0),
        "Ah": (0, 1, 1, 0, 0, 0, 0, 0), "Ohm": (1, -1, 0, 0, 0, 0, 0, 0),
        "Hz": (0, 0, -1, 0, 0, 0, 0, 0), "rpm": (0, 0, -1, 0, 0, 0, 0, 1),
        "Pa": (0, 0, 0, 1, -2, 0, 0, 0),
    }
    for name, kind in composites.items():
        scale = Scale(Fraction(3600)) if name == "Ah" else Scale(Fraction(1, 30), 1) if name == "rpm" else Scale(Fraction(1))
        definitions[name] = _make(name, kind, scale)
    for name, base, factor in (
        ("mV", "V", Fraction(1, 1000)), ("mA", "A", Fraction(1, 1000)),
        ("kW", "W", Fraction(1000)), ("Wh", "J", Fraction(3600)),
        ("kWh", "J", Fraction(3600000)), ("ms", "s", Fraction(1, 1000)),
        ("us", "s", Fraction(1, 1000000)), ("ns", "s", Fraction(1, 1000000000)),
        ("mOhm", "Ohm", Fraction(1, 1000)), ("kOhm", "Ohm", Fraction(1000)),
        ("MOhm", "Ohm", Fraction(1000000)), ("kPa", "Pa", Fraction(1000)),
        ("bar", "Pa", Fraction(100000)),
    ):
        definitions[name] = _make(name, definitions[base].kind, Scale(factor))
    definitions["degC"] = _make("degC", definitions["K"].kind, offset=Fraction(27315, 100))
    definitions["delta_degC"] = _make("delta_degC", definitions["delta_K"].kind)
    definitions["deg"] = _make("deg", definitions["rad"].kind, Scale(Fraction(1, 180), 1))
    return definitions


# 别名严格大小写敏感；C不解释为摄氏度，任意未登记前缀仍未知。
ATOMIC_UNITS = MappingProxyType(_build_atoms())
UNIT_ALIASES = MappingProxyType({
    "µs": "us", "μs": "us", "°C": "degC", "℃": "degC", "ΔK": "delta_K",
    "Δ°C": "delta_degC", "Δ℃": "delta_degC", "Ω": "Ohm", "Ω": "Ohm",
    "mΩ": "mOhm", "kΩ": "kOhm", "MΩ": "MOhm", "°": "deg",
})


def _build_preferred() -> dict[tuple[int, ...], Unit]:
    """登记倍率1的默认名称，不取用户参数顺序决定显示单位。

    参数: 无。
    返回: 按量种索引的首选单位字典，初始化后冻结。
    异常: 模型错误直接传播。
    """
    # 电荷、速度等复合基准无需作为单个解析原子再次登记。
    result = {ATOMIC_UNITS[name].kind: ATOMIC_UNITS[name] for name in ("1", "V", "A", "W", "J", "s", "K", "delta_K", "Ohm", "m", "Hz", "rad", "N", "Pa")}
    for symbol, kind in (
        ("A*s", (0, 1, 1, 0, 0, 0, 0, 0)), ("m/s", (0, 0, -1, 0, 1, 0, 0, 0)),
        ("m/s^2", (0, 0, -2, 0, 1, 0, 0, 0)), ("rad/s", (0, 0, -1, 0, 0, 0, 0, 1)),
        ("N*m", (0, 0, 0, 1, 1, 0, 0, 0)),
    ):
        result[kind] = _make(symbol, kind)
    return result


PREFERRED_UNITS = MappingProxyType(_build_preferred())


class _Parser:
    """用有限词元递归下降解析单位；未知原子保留None但仍检查完整语法。

    状态仅为本次词元tuple与读取位置，不跨计划缓存，不执行输入文本。
    """

    def __init__(self, text: str) -> None:
        """构建有限词元流。

        参数: text为长度已检查的非空单位文本。
        返回: None。
        异常: ValueError为词元数量超限。
        """
        # 仅归一化明确批准的乘号和上标，不做任意Unicode折叠。
        normalized = text.replace("·", "*").replace("²", "^2").replace("³", "^3")
        self.tokens = tuple(re.findall(r"[*/^()]|[^\s*/^()]+", normalized))
        if len(self.tokens) > 64:
            raise ValueError("单位文本不能超过64个词元")
        self.position = 0

    def peek(self) -> str | None:
        """查看当前词元，不推进位置。

        参数: 无。
        返回: 当前文本或流尾None。
        异常: 无。
        """
        # 显式流尾使缺右括号与缺运算数得到语法错误。
        return self.tokens[self.position] if self.position < len(self.tokens) else None

    def factor(self) -> Unit | None:
        """解析原子或括号表达式及可选整数幂。

        参数: 无。
        返回: 已知Unit或未知原子的None。
        异常: ValueError为语法、幂或已知单位运算错误。
        """
        token = self.peek()
        # 括号不接受隐式乘法，也不能用空括号代替无量纲1。
        if token == "(":
            self.position += 1
            result = self.expression()
            if self.peek() != ")":
                raise ValueError("单位表达式缺少右括号")
            self.position += 1
        elif token is None or token in ("*", "/", "^", ")"):
            raise ValueError("单位表达式缺少原子或括号内表达式")
        else:
            self.position += 1
            # 不把表达式运算或Python对象访问文本吞为一个未知原子。
            if any(character in token for character in "+-.[]{}=,:;!&|\\'\"<>"):
                raise ValueError(f"单位原子含不允许的语法：{token}")
            result = ATOMIC_UNITS.get(UNIT_ALIASES.get(token, token))
        # 单项最多一个幂；连续幂必须写成明确括号结构。
        if self.peek() == "^":
            self.position += 1
            exponent_text = self.peek()
            if exponent_text is None or re.fullmatch(r"[+-]?[0-9]+", exponent_text) is None:
                raise ValueError("单位幂必须为整数文本")
            exponent = int(exponent_text)
            if abs(exponent) > _MAX_EXPONENT:
                raise ValueError("单位幂必须在-32到32之间")
            self.position += 1
            if result is not None:
                result = _power(result, exponent)
        return result

    def expression(self) -> Unit | None:
        """按同级左结合解析乘除，完整检查未知项旁的已知非法温度。

        参数: 无。
        返回: 已知Unit，含未知原子时为None。
        异常: ValueError为语法或单位组合错误。
        """
        result = self.factor()
        while self.peek() in ("*", "/"):
            operator = self.peek()
            self.position += 1
            right = self.factor()
            # 未知标签不掩盖已知摄氏度的非法乘除。
            if result is not None:
                _require_multiplicative(result)
            if right is not None:
                _require_multiplicative(right)
            if result is None or right is None:
                result = None
            else:
                result = multiply(result, right) if operator == "*" else divide(result, right)
        return result


def resolve_unit(text: str) -> Unit | None:
    """解析登记单位和受限复合文本，未知原子返回None。

    参数: text为最多256字符的非空文本，允许首尾空白。
    返回: Unit或None；语法正确的未知单位不伪装为verified。
    异常: TypeError为非文本；ValueError为空、语法、资源或非法单位组合。
    """
    # 原始长度先限额，不能靠大量空白绕过入口限制。
    if type(text) is not str:
        raise TypeError("单位必须为文本")
    if len(text) > 256 or not text.strip():
        raise ValueError("单位必须为非空且不超过256字符的文本")
    # 无运算标记的自定义多词标签沿旧unknown政策保留；已知原子并列仍是坏语法。
    stripped = text.strip()
    if not any(character in stripped for character in "*/^()·²³"):
        words = stripped.split()
        if len(words) > 1 and not any(character in stripped for character in "+-.[]{}=,:;!&|\\'\"<>") and all(UNIT_ALIASES.get(word, word) not in ATOMIC_UNITS for word in words):
            return None
    parser = _Parser(stripped)
    result = parser.expression()
    if parser.peek() is not None:
        raise ValueError(f"单位表达式存在多余词元：{parser.peek()}")
    return result
