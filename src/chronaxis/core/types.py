"""定义信号类型、时间坐标、三值条件和质量原因，供模型及计算层共用。

模型接收明确的枚举成员；质量原因以固定的整数位保存，允许组合已知位，
拒绝未知位。Truth区分条件成立、不成立和无法确定三种结果，禁止直接转为
Python布尔值。SignalDType声明值类型，TimeType区分相对坐标与UTC绝对坐标。
本模块只依赖标准库，不读取数据或文件，不持有会话状态；SourceType当前
只描述内存输入。
"""

# 严格位边界防止未知质量位被误认为已校验策略。
from enum import Enum, FlagBoundary, IntFlag


class Truth(Enum):
    """保存条件成立、不成立或无法确定的三种结果。

    TRUE和FALSE表示已有充分证据；UNKNOWN表示缺失、过期或无法有效求值。
    成员不可变，任何成员都禁止隐式转为Python布尔值，调用者须明确处理三种结果。
    """

    TRUE = "true"  # 已知且条件成立。
    FALSE = "false"  # 已知且条件不成立。
    UNKNOWN = "unknown"  # 缺失、过期或无法有效求值。

    def __bool__(self) -> bool:
        """阻止三个枚举成员被Python统一当作True。

        参数: 无额外参数；当前三值结果。
        返回: 无正常返回；须显式比较Truth成员。
        异常: TypeError；三值逻辑尚未由普通Python bool表达。
        """
        # 对TRUE/FALSE也统一拒绝，避免逻辑分支误用枚举默认真值。
        raise TypeError("Truth不能隐式转bool，请显式处理TRUE/FALSE/UNKNOWN")


class QualityFlag(IntFlag, boundary=FlagBoundary.STRICT):
    """用固定整数位保存样本无效或质量受限的原因。

    多个原因可以组合；基础策略拒绝所有非零位。NONE表示没有记录原因，
    仍需结合valid判断有效性。最高位为256，数组至少需要16位保存全部标志；
    构造时拒绝负值和未知位。
    """

    NONE = 0  # 没有已记录原因，不证明来源能力完整。
    MISSING = 1  # 缺少所需观测。
    STALE = 2  # 观测超过有效期。
    DECODE_ERROR = 4  # 来源解析或解码失败。
    NONFINITE = 8  # 数值NaN或无穷。
    OUT_OF_RANGE = 16  # 超过明确业务范围。
    ESTIMATED = 32  # 显式估计值，首版基础策略也禁止。
    OVERFLOW = 64  # 定宽运算上溢或下溢，回绕结果不能作为有效值。
    PRECISION_LOSS = 128  # 不能精确表示的数值转换。
    DOMAIN_ERROR = 256  # 除零等值域错误。

    @classmethod
    def _missing_(cls, value):
        """检查候选质量位值，再由标准库构造合法的位组合。

        参数:
            value: 没有对应单一成员的候选位值；合法组合必须是非负整数。
        返回:
            QualityFlag或None: 合法组合由IntFlag构造；其他输入遵循标准库协议。
        异常:
            ValueError: 候选值为负数、包含未知位或不能构造为合法质量值。
        """
        # STRICT仍会归一化负值；须在该标准库过程之前显式拒绝。
        if isinstance(value, int) and value < 0:
            # -512不能被隐藏为NONE，非法原因不进入有效模型。
            raise ValueError("quality mask必须非负")
        # 非负已知组合沿用标准位构造，未知正位由STRICT拒绝。
        return super()._missing_(value)


class SignalDType(Enum):
    """声明信号值的逻辑类型，供模型和数值运算检查使用。

    整数明确分为int64和uint64，浮点使用float64。bool独立于整数，enum使用
    显式标签域；类型不会根据Python继承关系或NumPy自动类型提升推断。
    """

    INT64 = "int64"  # 有符号64位整数。
    UINT64 = "uint64"  # 无符号64位整数。
    FLOAT64 = "float64"  # 有限双精度浮点，不隐式转大整数。
    BOOL = "bool"  # 明确布尔值，不按任意数值的Python真值判断。
    ENUM = "enum"  # 显式枚举标签，不参与一般数值运算。


class TimeType(Enum):
    """区分相对来源坐标和UTC绝对坐标，保留显式起点依据。

    不读取机器时区，不自动把相对0当作UTC epoch。
    """

    RELATIVE = "relative"  # 需要来源声明origin。
    ABSOLUTE = "absolute"  # 已规范化UTC epoch纳秒。


class SourceType(Enum):
    """标明当前内存模型接受的数据来源种类。

    MEMORY表示调用者直接提供已转换为纳秒的内存行。本枚举没有可变注册表，
    不会因为声明一个外部来源名称就自动读取或解码该来源。
    """

    MEMORY = "memory"  # 已声明纳秒的内存行，不执行旧读写或解码。
