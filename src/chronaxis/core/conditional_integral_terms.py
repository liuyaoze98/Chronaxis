"""声明有限条件积分项及值、条件各自的覆盖事实，不执行数值计算。

条件为BOOL三值：TRUE且值可核实才产生面积，FALSE属于已知未选择，UNKNOWN
不是FALSE。两种未知区间分别划分实际窗口，真实样本只计有效值更新且条件TRUE。
ReferenceConditionalIntegralTerms保留原序面积与显式有效掩码，面积单位仍为
原输入单位乘秒；不在块内归约或转换最终单位，空归约不代表正常零。
本模块只校验冻结模型和公共输入门槛，不读文件、不改输入，也不申请预算；
有限临时列和事实须由调用方owner事先预约，独立留存须另行计费。
"""

# 冻结协议与范围检查只依赖标准库；两面积核仅共享非数值输入门槛。
from dataclasses import dataclass
from math import isfinite
from .calculations import CalculationDefinition, CalculationSeries, calculation_unit
from .models import Interval, SourceRef
from .types import QualityFlag as Q, SignalDType as D
from .validation import require_text


def _unknown_duration(ranges, actual):
    """校验一种未知范围完整有序、不重叠且不越过实际窗口。

    参数: ranges为冻结Interval tuple，actual为实际交集或None。
    返回: 原生int纳秒未知总时长。异常: TypeError/ValueError为结构或不可能范围。
    """
    if type(ranges) is not tuple:
        raise TypeError('条件积分未知范围需要tuple')
    cursor, total = (actual.start_ns if actual is not None else 0), 0
    # 只验证诊断几何，不能按总长度掩盖重复区间或已知缺口。
    for item in ranges:
        if (not isinstance(item, Interval) or actual is None or item.start_ns < cursor
                or item.start_ns >= item.end_ns or item.end_ns > actual.end_ns):
            raise ValueError('条件积分未知范围必须有序、不重叠且在实际窗口内')
        cursor, total = item.end_ns, total + item.end_ns - item.start_ns
    return total


@dataclass(frozen=True)
class ConditionalIntegralFacts:
    """保存当前块原请求与完整覆盖，值缺失和条件未知分别说明。

    known包含TRUE和FALSE；selected只计TRUE且面积可核实的时长。
    selected_value_unknown只计TRUE而值/面积不可核实的时长，不混入条件UNKNOWN。
    FALSE不乘面积，原值的类型和精度检查仍保留在值覆盖及质量中。
    """

    spec: CalculationDefinition  # 原integral请求、scope和部分结果政策。
    actual_window: Interval | None  # 当前实际交集，不外推EOF。
    value_valid_duration_ns: int  # 原值经积分可用性检查后的有效时长。
    condition_known_duration_ns: int  # 可判断TRUE或FALSE的时长。
    selected_duration_ns: int  # TRUE且值/面积可核实的时长。
    selected_value_unknown_duration_ns: int  # TRUE但值/面积不可核实的时长。
    false_duration_ns: int  # 已知FALSE时长，只有完整窗才证明空选择零。
    valid_sample_count: int  # 半开当前块内原值真实更新且有效/TRUE的数量。
    value_unknown_ranges: tuple[Interval, ...]  # 值及面积计算不可核实的正区间。
    condition_unknown_ranges: tuple[Interval, ...]  # BOOL UNKNOWN正区间，与值未知独立。
    quality: Q  # 输入、依赖和精度/面积故障原因完整OR。
    input_unit: str  # 原输入工程单位，面积尚未转换输出单位。
    binding_identity: str  # 实际联合输入中原值表达式身份。
    source_refs: tuple[SourceRef, ...]  # 完整来源子类与原定位，不只保存字段名。
    ranges_retained: bool = True  # 仅明确请求时保留未知范围；False不能用于完整明细归约。

    def __post_init__(self):
        """验证两完整分区、选中与FALSE恒等式，不修复矛盾事实。

        参数: 无。返回: None。异常: TypeError/ValueError为类型、覆盖或未知几何错误。
        """
        if not isinstance(self.spec, CalculationDefinition) or self.spec.operation != 'integral':
            raise TypeError('条件积分事实需要integral CalculationDefinition')
        if self.actual_window is not None and not isinstance(self.actual_window, Interval):
            raise TypeError('条件积分实际范围需要Interval或None')
        actual, request = self.actual_window, self.spec.window
        span = 0 if actual is None else actual.end_ns - actual.start_ns
        if actual is not None and not request.start_ns <= actual.start_ns <= actual.end_ns <= request.end_ns:
            raise ValueError('条件积分实际范围越过原请求')
        durations = (self.value_valid_duration_ns, self.condition_known_duration_ns, self.selected_duration_ns,
                     self.selected_value_unknown_duration_ns, self.false_duration_ns)
        # 所有时长与样本计数为原生整数，不能把bool或浮点秒作纳秒。
        if any(type(value) is not int or not 0 <= value <= span for value in durations):
            raise ValueError('条件积分覆盖时长需要实际跨度内的非负原生int')
        if (type(self.valid_sample_count) is not int or not 0 <= self.valid_sample_count <= self.selected_duration_ns
                or self.selected_duration_ns > self.value_valid_duration_ns
                or self.selected_value_unknown_duration_ns > span - self.value_valid_duration_ns
                or self.false_duration_ns > self.condition_known_duration_ns
                or self.selected_duration_ns + self.selected_value_unknown_duration_ns !=
                   self.condition_known_duration_ns - self.false_duration_ns):
            raise ValueError('条件积分样本、选择、FALSE与已知时长矛盾')
        # 分别核对值与条件的完整实际域，不将UNKNOWN当FALSE合并。
        if type(self.ranges_retained) is not bool:
            raise TypeError('范围保留标志需要bool')
        if not self.ranges_retained and (self.value_unknown_ranges != () or self.condition_unknown_ranges != ()):
            raise ValueError('未请求范围时不能附带范围明细')
        if self.ranges_retained and _unknown_duration(self.value_unknown_ranges, actual) + self.value_valid_duration_ns != span:
            raise ValueError('条件积分值有效与未知未完整划分实际窗口')
        if self.ranges_retained and _unknown_duration(self.condition_unknown_ranges, actual) + self.condition_known_duration_ns != span:
            raise ValueError('条件积分已知与条件未知未完整划分实际窗口')
        if not isinstance(self.quality, Q) or type(self.source_refs) is not tuple or any(not isinstance(ref, SourceRef) for ref in self.source_refs):
            raise TypeError('条件积分事实需要typed质量和完整来源tuple')
        require_text(self.input_unit, 'conditional_integral.input_unit')
        require_text(self.binding_identity, 'conditional_integral.binding_identity')


@dataclass(frozen=True)
class ReferenceConditionalIntegralTerms:
    """保存有限原序面积，未知占位0只能与False掩码一起解释。"""

    areas: tuple[float, ...]  # 形状N-1的原序有限float面积，未换最终单位。
    valid: tuple[bool, ...]  # 只有TRUE选择且正常面积为True。
    facts: ConditionalIntegralFacts  # 当前块覆盖与完整定位，不是整窗最终状态。

    def __post_init__(self):
        """核对冻结同长面积与真实事实，不允许非有限或无效非零占位。

        参数: 无。返回: None。异常: TypeError/ValueError为列结构、面积或事实类型。
        """
        if (type(self.areas) is not tuple or type(self.valid) is not tuple or len(self.areas) != len(self.valid)
                or not isinstance(self.facts, ConditionalIntegralFacts)):
            raise TypeError('参考条件积分项需要同长tuple及ConditionalIntegralFacts')
        if any(type(area) is not float or not isfinite(area) or type(keep) is not bool
               or not keep and area != 0 for area, keep in zip(self.areas, self.valid)):
            raise ValueError('条件积分面积需有限float/bool，无效位置只能存0')


def require_conditional_integral_terms(series, spec, *, step_ns=None, valid_until_ns=None, condition_valid_until_ns=None):
    """校验typed数值、BOOL条件、明确积分单位及可表示正跨度。

    参数: series为有限CalculationSeries，spec为原integral请求。
        step_ns为所选周期，两个until列为值/条件的实际有效截止，均可省略保原行为。
    返回: None。异常: TypeError/ValueError/OverflowError为模型、能力、单位或时间错误。
    """
    # 仅共享结构门槛；两后端独立计算转换、面积、掩码、时长与样本。
    if not isinstance(series, CalculationSeries) or not isinstance(spec, CalculationDefinition):
        raise TypeError('条件积分需要CalculationSeries和CalculationDefinition')
    from .record_intervals import require_record_step
    from .integral_terms import require_valid_until
    require_record_step(step_ns, series.actual_value_updates)
    require_valid_until(series.times_ns, valid_until_ns)
    require_valid_until(series.times_ns, condition_valid_until_ns)
    if (spec.operation != 'integral' or series.conditions is None
            or series.values[0].dtype not in (D.INT64, D.UINT64, D.FLOAT64)
            or any(value.dtype is not D.BOOL for value in series.conditions)):
        raise ValueError('条件积分只支持数值integral及显式BOOL选择条件')
    calculation_unit(spec, series.unit)
    left, right = max(spec.window.start_ns, series.observation.start_ns), min(spec.window.end_ns, series.observation.end_ns)
    if right - left > 2 ** 63 - 1:
        raise OverflowError('条件积分正交集跨度超过int64')
