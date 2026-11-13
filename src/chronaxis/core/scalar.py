"""保存数值及枚举的声明类型、有效性和质量原因。

ScalarValue 是模型和数值计算共同使用的不可变数据对象。它只依赖基础类型和
原生标量校验，不导入信号模型、绑定或计算模块，供这些模块安全地共同引用。
公开入口仍由 chronaxis.core.numeric 和 chronaxis.core 重导出同一个类。
"""

from dataclasses import dataclass, field
from math import isfinite
from types import MappingProxyType

from .types import QualityFlag, SignalDType
from .validation import require_scalar, require_text


# 定宽端点由协议明确给出，不依赖 NumPy 提升类型或整数回绕。
INTEGER_BOUNDS = MappingProxyType({SignalDType.INT64: (-(2 ** 63), 2 ** 63 - 1), SignalDType.UINT64: (0, 2 ** 64 - 1)})


@dataclass(frozen=True)
class ScalarValue:
    """保存一个值的声明类型、有效性和质量原因。

    valid只能是bool，且当且仅当quality为NONE时为True。有质量问题的value
    可保留原始诊断，例如None或NaN，但不能作为正常数值参加后续计算。
    有效整数必须落在dtype对应的定宽范围内，有效float64必须有限。
    枚举使用labels中的文本值；labels是不可变的固定标签域，比较时必须同域。
    实例不可重新赋值，不持有跨时间或跨分析任务的状态。
    """

    value: int | float | bool | str | None  # 正常值或无效原诊断。
    dtype: SignalDType  # 输出声明类型，不靠值推断。
    valid: bool = True  # 无效不代表正常0。
    quality: QualityFlag = QualityFlag.NONE  # 输入原因和计算失败原因。
    labels: tuple[str, ...] = ()  # 仅enum有固定公开逻辑域。
    code: 'ScalarValue | None' = None  # 仅 enum_code 需要的原整数，可与标签有不同有效性。
    partial: bool = field(default=False,kw_only=True,repr=False)  # 有限变换窗口仅有部分输入时仍可估算的数值。

    def __post_init__(self) -> None:
        """检查值与声明类型是否一致，并核对有效性和质量原因。

        参数:
            无显式参数；读取value、dtype、valid、quality和labels。
        返回:
            None。保留输入声明，不自动转换类型、补零或清除质量原因。
        异常:
            TypeError: 字段类型或枚举标签域结构不合法。
            ValueError: 有效性与质量矛盾，浮点值非有限或枚举值不在声明域内。
            OverflowError: 有效整数超出声明类型的定宽范围。
        """
        # 原诊断也需不可变原生标量。
        require_scalar(self.value)
        if type(self.partial) is not bool or self.partial and not self.valid:
            raise ValueError('部分结果标志仅用于实际可用的数值')
        # dtype和质量都必须是真实已定义枚举。
        if not isinstance(self.dtype, SignalDType) or not isinstance(self.quality, QualityFlag) or type(self.valid) is not bool:
            # 不接受字符串类型名，也不把任意数值按Python真假规则当作valid。
            raise TypeError("ScalarValue需要typed dtype/quality及bool valid")
        # 逻辑域只能由明确冻结标签构成。
        if self.code is not None and (self.dtype is not SignalDType.ENUM or not isinstance(self.code, ScalarValue)
                                      or self.code.dtype not in INTEGER_BOUNDS):
            raise TypeError('只有枚举可附带整数原码')
        if not isinstance(self.labels, tuple) or (self.dtype is not SignalDType.ENUM and self.labels):
            # 数值不携带隐式业务枚举含义。
            raise TypeError("labels仅支持enum tuple域")
        # enum即使invalid也需有合法声明域。
        if self.dtype is SignalDType.ENUM:
            # 空域或重复标签不能证明逻辑值身份。
            if not self.labels or len(set(self.labels)) != len(self.labels):
                # 不自动猜枚举域。
                raise ValueError("enum需要非空唯一labels")
            # 标签保留完整大小写业务文本。
            for label in self.labels:
                # 不将标签当作表达式名称。
                require_text(label, "enum.label")
        # 有效性不能与禁止质量矛盾。
        if self.valid != (self.quality == QualityFlag.NONE):
            # 无效结果必须携带原因，不能悄悄恢复正常。
            raise ValueError("valid与基础质量策略矛盾")
        # invalid诊断无需满足正常输出类型，不参加正常计算。
        if not self.valid:
            # 保留原NaN/None/错误编码及原因。
            return
        # 严格原生类型，bool不视作整数。
        expected = {SignalDType.INT64: int, SignalDType.UINT64: int, SignalDType.FLOAT64: float,
                    SignalDType.BOOL: bool, SignalDType.ENUM: str}[self.dtype]
        # 不隐式promotion或解析字符串数值。
        if type(self.value) is not expected:
            # 类型冲突是结构错误，归一化层须明确转换。
            raise TypeError("ScalarValue有效值与dtype不一致")
        # 有效定宽整数不能沿用Python无界结果。
        if self.dtype in INTEGER_BOUNDS:
            # signed/unsigned端点分别校验。
            lower, upper = INTEGER_BOUNDS[self.dtype]
            # 边界值本身合法，只有超界拒绝。
            if not lower <= self.value <= upper:
                # 运算内核应先转OVERFLOW无效，不能直接构造正常越界值。
                raise OverflowError("ScalarValue有效整数超界")
        # 浮点正常值单独检查有限，不能借整数范围掩盖Inf。
        elif self.dtype is SignalDType.FLOAT64 and not isfinite(self.value):
            # float正常路径不接受NaN/Inf。
            raise ValueError("ScalarValue有效float必须有限")
        # 枚举正常标签必须确属当前声明域。
        elif self.dtype is SignalDType.ENUM and self.value not in self.labels:
            # 未声明字符串不是正常枚举。
            raise ValueError("ScalarValue枚举标签不在域内")


def _scalar_from_validated_fields(value, dtype, valid=True, quality=QualityFlag.NONE,
                                  labels=(), code=None, *, partial=False):
    """从同次运行已核的数值列或已有标量构造共享值，不重复检查声明。

    参数: 与ScalarValue相同；调用方必须已经证明全部字段不变量，不能传入
        外部未检查数据或刚计算而未检查范围/有限性的结果。
    返回: 字段完全相同的冻结ScalarValue，不保存检查标志或额外副本。
    异常: 分配错误原样传播。仅限内部调用，公开构造仍完整验证。
    """
    result = object.__new__(ScalarValue)
    # 数值和标签都已不可变；只安装现有字段，不建立其他可变状态。
    object.__setattr__(result, 'value', value)
    object.__setattr__(result, 'dtype', dtype)
    object.__setattr__(result, 'valid', valid)
    object.__setattr__(result, 'quality', quality)
    object.__setattr__(result, 'labels', labels)
    object.__setattr__(result, 'code', code)
    object.__setattr__(result, 'partial', partial)
    return result


# 进程间传输与既有pickle使用这一公开路径；生成数据类后设置，避免循环导入。
ScalarValue.__module__ = "chronaxis.core.numeric"
