"""声明尚未归约的ZOH积分项及其覆盖、质量和来源事实。

输入来自有限CalculationSeries块，输出按原区间顺序保留面积和有效掩码。
面积单位为原输入单位乘秒，尚未应用输出单位因子；未知存储0必须结合掩码。
本模块只校验冻结协议，不执行数值积分、文件读取或资源分配策略。
纯核输出在调用方CalculationBlock的workspace内消费，独立留存须另计预算。
参考模型用原生tuple；数组模型在对应NumPy模块定义，通用模型不导入NumPy。
"""

# 只共享typed事实与门槛，两数值核各自计算面积、有效性及覆盖。
from dataclasses import dataclass
from math import isfinite
from .calculations import CalculationSeries, CalculationDefinition, calculation_unit
from .calculations_reference import require_calculation
from .models import Interval, SourceRef
from .types import QualityFlag as Q
from .validation import require_text


@dataclass(frozen=True)
class IntegralFacts:
    """保留当前块的原请求、实际范围、可核实覆盖与来源，不负责最终归约。

    只有value_valid_duration_ns表示有效面积时长；源诊断与计算质量完整OR。
    此处没有条件FALSE证据，不能由空项推断条件空选择为零。
    """

    spec: CalculationDefinition  # 原请求窗口及最终部分结果政策，不按块覆盖重写。
    actual_window: Interval | None  # 当前块与请求交集，无交集保持None。
    value_valid_duration_ns: int  # 可核实面积时长，整数ns。
    valid_sample_count: int  # 半开当前块内实际更新且可核实的样本数。
    value_unknown_ranges: tuple[Interval, ...]  # 请求明细时的连续未知范围；未请求为空，不据此推断覆盖完整。
    quality: Q  # 来源及精度/非有限/下溢等计算诊断。
    input_unit: str  # 输入工程单位，面积尚未换为J/Ah等输出单位。
    binding_identity: str  # 当前真实表达式身份。
    source_refs: tuple[SourceRef, ...]  # 当前块完整真实定位，保留子类。

    def __post_init__(self):
        """校验事实结构和覆盖边界，不更正错误事实。

        参数: 无。返回: None。异常: TypeError/ValueError为类型或不可能覆盖。
        """
        # 原请求和实际交集需真实类型；覆盖计数的上界由实际纳秒跨度决定。
        if not isinstance(self.spec, CalculationDefinition) or self.spec.operation != 'integral':
            raise TypeError('积分项事实需要integral CalculationDefinition')
        if self.actual_window is not None and not isinstance(self.actual_window, Interval):
            raise TypeError('积分项实际范围需要Interval或None')
        duration = 0 if self.actual_window is None else self.actual_window.end_ns - self.actual_window.start_ns
        # 原生非负整数与真实时长上界，不把bool或浮点秒当ns。
        if (type(self.value_valid_duration_ns) is not int or not 0 <= self.value_valid_duration_ns <= duration
                or type(self.valid_sample_count) is not int or self.valid_sample_count < 0):
            raise ValueError('积分项覆盖或样本数不合法')
        # 未知范围是正区间，不能越过当前实际窗口或凭空建立观测。
        if (type(self.value_unknown_ranges) is not tuple
                or any(not isinstance(item, Interval) or item.start_ns >= item.end_ns
                       or self.actual_window is None or item.start_ns < self.actual_window.start_ns
                       or item.end_ns > self.actual_window.end_ns for item in self.value_unknown_ranges)):
            raise ValueError('积分项未知范围必须位于实际窗口')
        # 保留typed质量和完整来源子类，不把任意文字当来源事实。
        if not isinstance(self.quality, Q) or type(self.source_refs) is not tuple or any(not isinstance(item, SourceRef) for item in self.source_refs):
            raise TypeError('积分项需要typed质量与完整来源tuple')
        # 来源文字不作为绑定证明，保留上层已验证身份和单位。
        require_text(self.input_unit, 'integral.input_unit')
        require_text(self.binding_identity, 'integral.binding_identity')


@dataclass(frozen=True)
class ReferenceIntegralTerms:
    """保存标量参考的原序面积和显式有效掩码，不累计全窗口项。"""

    areas: tuple[float, ...]  # 每个原区间的面积，未观察/无效位置为0存储占位。
    valid: tuple[bool, ...]  # 只有True位置可参与后续数值归约。
    facts: IntegralFacts  # 当前块覆盖/原请求/诊断，不是最终CalculationResult。

    def __post_init__(self):
        """校验同长冻结列及有限面积，拒绝用无效非零占位。

        参数: 无。返回: None。异常: TypeError/ValueError为列/掩码/面积错误。
        """
        # 面积/掩码必须同长冻结；有效与未知都不允许非有限存储。
        if type(self.areas) is not tuple or type(self.valid) is not tuple or len(self.areas) != len(self.valid) or not isinstance(self.facts, IntegralFacts):
            raise TypeError('参考积分项需要同长tuple及IntegralFacts')
        if any(type(value) is not float or not isfinite(value) or type(keep) is not bool
               or not keep and value != 0 for value, keep in zip(self.areas, self.valid)):
            raise ValueError('参考积分面积需有限float，未知使用掩码及0存储')


def require_valid_until(times, valid_until_ns):
    """校验有限块的必要有效截止列。参数: 时间tuple/可选截止tuple。返回: None。异常: 类型/长度/范围错误。"""
    if valid_until_ns is not None:
        if type(valid_until_ns) is not tuple or len(valid_until_ns) != len(times):
            raise TypeError('有效截止需要与驱动点同长的tuple')
        for deadline in valid_until_ns:
            if deadline is not None and (type(deadline) is not int or not -(1 << 63) <= deadline < (1 << 63)):
                raise ValueError('有效截止需要int64实际时间或None')


def require_integral_terms(series, spec, *, step_ns=None, valid_until_ns=None):
    """共享输入/单位/可表示时长门槛，不共享数值内核。

    参数: series为CalculationSeries，spec为原integral请求；step_ns为可选固定/DBC周期。
        valid_until_ns为可选同长实际截止tuple，None项表示无额外有效截止。
        指定周期时每点必须为所选驱动的真实更新，不能把TTL/窗口边界当报文。
        调用方负责选驱动；本接口不接受尚未分配权重的混合时间轴。返回: None。
    异常: 类型/dtype/算子/条件/单位配置错误；OverflowError为int64不可表示跨度。
    """
    # 沿用原输入类型门槛，条件与其他算子需待各自独立归约契约实现。
    require_calculation(series, spec, step_ns=step_ns)
    # 截止仅用于当前块的必要有效性计算；None沿用原无额外截止路径。
    require_valid_until(series.times_ns, valid_until_ns)
    if spec.operation != 'integral' or series.conditions is not None:
        raise ValueError('当前积分项只支持无选择条件的integral')
    # 预先验证最终单位配置，但本层不把返回因子应用到每块。
    calculation_unit(spec, series.unit)
    # 只防守正交集跨度，不以绝对坐标转浮点，也不延长原观测。
    left = max(spec.window.start_ns, series.observation.start_ns)
    right = min(spec.window.end_ns, series.observation.end_ns)
    if right - left > 2 ** 63 - 1:
        raise OverflowError('积分区间时长不能超过正int64')
