"""声明整窗积分数值归约结果和容量门槛，不执行数值求和。

两个独立数值核接收原序面积项，输出尚未分类覆盖状态的冻结数值结果。
面积先在输入单位乘秒下累计，最终只转换一次；覆盖和来源另由事实 owner 保存。
本模块不导入 NumPy、不读写文件，也不提供独立内存预算。
"""

# 共享协议与输入门槛，不共享求和或浮点误差计算。
from dataclasses import dataclass
from math import isfinite
from .types import QualityFlag as Q
from .validation import require_text


class IntegralStateLimitError(ValueError):
    """表示误差项超过显式容量，调用方须停止当前归约并清理资源。

    不截断误差项，也不把容量不足伪装为正常数值或 NONFINITE。
    """


def require_partial_limit(limit: int) -> int:
    """校验误差项数量的硬上限。

    参数: limit 为正原生整数。返回: 原值。异常: ValueError 为 bool、非整数或非正数。
    """
    # 容量是精确计数，拒绝布尔、浮点或无限制配置。
    if type(limit) is not int or limit <= 0:
        raise ValueError('积分误差项容量需要正原生int')
    return limit


def require_sum_finish(unit: str, factor: float) -> tuple[str, float]:
    """校验纯核的输出标签及一次性转换因子。

    参数: unit 为非空标签；factor 为正有限原生 float。返回: (unit, factor)。
    异常: TypeError/ValueError 为文字或因子错误；单位维度由外层 calculation_unit 校验。
    """
    # 纯核不能凭单位文本推导因子，外层须先核对已注册的维度转换。
    require_text(unit, 'integral.output_unit')
    if type(factor) is not float or not isfinite(factor) or factor <= 0:
        raise ValueError('积分转换因子需要正有限原生float')
    return unit, factor


@dataclass(frozen=True)
class IntegralSumResult:
    """保存已换单位的数值快照，不代替覆盖和最终 CalculationResult 分类。

    valid_term_count 统计参与累计的有效面积项，与实际信号更新样本数不同。
    无有效项时 value 为 None；有有效零面积时 value 为 0.0。
    """

    value: float | None  # 最终单位下的有限面积，未知或计算失败为 None。
    unit: str  # 已由调用方声明的最终输出单位。
    calculation_failed: bool  # 数值求和或最终转换失败，不表示输入全部未知。
    quality: Q  # 本次数值归约诊断，输入覆盖质量另保留在 IntegralFacts。
    valid_term_count: int  # 原序有效面积项数，不冒充真实样本计数。

    def __post_init__(self):
        """拒绝矛盾的冻结结果，不自动补零或修正故障。

        参数: 无。返回: None。异常: TypeError/ValueError 为结构或状态不一致。
        """
        # 标签、计数和诊断保持真实类型，拒绝 bool 当作整数计数。
        require_text(self.unit, 'integral.output_unit')
        if (type(self.calculation_failed) is not bool or not isinstance(self.quality, Q)
                or type(self.valid_term_count) is not int or self.valid_term_count < 0):
            raise TypeError('积分数值结果需要真实状态、质量和非负整数计数')
        if self.value is not None and (type(self.value) is not float or not isfinite(self.value)):
            raise ValueError('积分数值结果只接受有限float或None')
        # 未知与失败都不得借零值冒充成功，成功的有效项必须有明确数值。
        if self.calculation_failed:
            if self.value is not None or self.quality == Q.NONE or self.valid_term_count == 0:
                raise ValueError('积分计算失败需要有效项、None值及明确质量原因')
        elif ((self.valid_term_count == 0) != (self.value is None)) or self.quality != Q.NONE:
            raise ValueError('积分成功结果的数值、计数或质量不一致')
