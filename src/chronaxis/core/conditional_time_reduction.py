"""声明有限条件时间统计事实及结构门槛，不执行数值或时间归约。

支持条件min_time/max_time/time_weighted_mean和主BOOL duration。值覆盖与外BOOL条件覆盖
独立完整划分实际窗口；外FALSE不选择，外UNKNOWN不算FALSE。duration另保存外TRUE
但主FALSE的有效零证据，选中时长只含主TRUE。mean的值覆盖包含转float精度门槛，
权重数值故障不改输入覆盖。纯模型不读来源、不管理预算，不留存全窗输入；
有限事实及返回元数据需要外层owner预先计费，最终分类也由外层负责。
"""

# 两数值核仅共享typed模型和静态配置/几何门槛，不共享数值计算。
from dataclasses import dataclass
from .calculations import CalculationDefinition, CalculationSeries
from .models import Interval, SourceRef
from .time_reduction import require_time_config
from .types import QualityFlag as Q, SignalDType as D
from .validation import require_text


def _unknown_duration(ranges, actual):
    """核对一种未知范围的顺序与几何，返回精确整数时长。

    参数: ranges为冻结正Interval tuple，actual为原请求内实际交集或None。
    返回: 原生int未知纳秒。异常: TypeError/ValueError为类型、重叠、反序或越界。
    """
    # 各未知分区独立检查，不靠总长度掩盖重复位置或跨越实际边界。
    if type(ranges) is not tuple:
        raise TypeError('条件时间未知范围需要tuple')
    cursor, total = (actual.start_ns if actual is not None else 0), 0
    for item in ranges:
        if (not isinstance(item, Interval) or actual is None or item.start_ns < cursor
                or item.start_ns >= item.end_ns or item.end_ns > actual.end_ns):
            raise ValueError('条件时间未知范围必须有序、不重叠且在实际窗口内')
        cursor, total = item.end_ns, total + item.end_ns - item.start_ns
    return total


@dataclass(frozen=True)
class ConditionalTimeCalculationFacts:
    """保存有限块双覆盖和选择交集，主FALSE只为duration保留有效零证据。

    数值算子selected包含外TRUE有效值；duration的selected只含外TRUE主TRUE。
    selected_false只含duration外TRUE主FALSE，其他算子为0；真实样本遵循相同选择。
    两未知元组分别完整划分值与外条件，不用UNKNOWN填零或代替FALSE。
    """

    spec: CalculationDefinition  # 原时间统计请求与政策，不按块重写。
    actual_window: Interval | None  # 当前块真实交集，不外推EOF。
    value_valid_duration_ns: int  # 原值通过本算子门槛后的有效纳秒。
    condition_known_duration_ns: int  # 外条件TRUE/FALSE已知纳秒。
    selected_duration_ns: int  # 外TRUE有效数值，duration另须主TRUE。
    selected_value_unknown_duration_ns: int  # 外TRUE但值未知，不混入外条件UNKNOWN。
    false_duration_ns: int  # 外条件已知FALSE纳秒，只有完整窗才证明空选择。
    selected_false_duration_ns: int  # duration外TRUE主FALSE有效零证据，其他算子0。
    valid_sample_count: int  # 已选真实值更新，不是条件更新/保持区间数。
    value_unknown_ranges: tuple[Interval, ...]  # 值未知位置，包含mean精度失败。
    condition_unknown_ranges: tuple[Interval, ...]  # 外条件UNKNOWN位置。
    quality: Q  # 输入、精度与依赖原因，不包含数值weight失败。
    input_unit: str  # 原分析工程单位，尚未转换最终输出。
    dtype: D  # 极值保留原定宽整数；duration为BOOL。
    binding_identity: str  # 原值表达式联合输入身份。
    source_refs: tuple[SourceRef, ...]  # 原定位和真实子类完整保留。
    ranges_retained: bool = True  # False只留分类所需计数，不构造未知范围。

    def __post_init__(self):
        """验证正分区、选择交集和完整身份，不修补矛盾事实。

        参数: 无。返回: None。异常: TypeError/ValueError为配置、几何或交集矛盾。
        """
        # 配置门槛只验证typed算子、单位、dtype，不计算浮点数值。
        require_time_config(self.spec, self.input_unit, self.dtype, None, 4096)
        if self.actual_window is not None and not isinstance(self.actual_window, Interval):
            raise TypeError('条件时间实际范围需要Interval或None')
        actual, request = self.actual_window, self.spec.window
        span = 0 if actual is None else actual.end_ns - actual.start_ns
        if actual is not None and not request.start_ns <= actual.start_ns <= actual.end_ns <= request.end_ns:
            raise ValueError('条件时间实际范围越过原请求')
        durations = (self.value_valid_duration_ns, self.condition_known_duration_ns, self.selected_duration_ns,
                     self.selected_value_unknown_duration_ns, self.false_duration_ns, self.selected_false_duration_ns)
        # 计数与纳秒必须原生int；bool不能通过整数继承关系冒充时长。
        if any(type(value) is not int or not 0 <= value <= span for value in durations):
            raise ValueError('条件时间覆盖需要实际跨度内原生非负int')
        if (type(self.valid_sample_count) is not int or not 0 <= self.valid_sample_count <= self.selected_duration_ns
                or self.selected_duration_ns + self.selected_false_duration_ns > self.value_valid_duration_ns
                or self.selected_value_unknown_duration_ns > span - self.value_valid_duration_ns
                or self.false_duration_ns > self.condition_known_duration_ns
                or self.selected_duration_ns + self.selected_false_duration_ns + self.selected_value_unknown_duration_ns
                   != self.condition_known_duration_ns - self.false_duration_ns
                or self.spec.operation != 'duration' and self.selected_false_duration_ns != 0):
            raise ValueError('条件时间样本、选择、有效FALSE及已知交集矛盾')
        # 值和外条件分别完整划分实际域；不能用另一种未知补缺口。
        if type(self.ranges_retained) is not bool or not self.ranges_retained and (self.value_unknown_ranges or self.condition_unknown_ranges):
            raise ValueError('精简条件时间事实不能携带未知范围')
        value_unknown = _unknown_duration(self.value_unknown_ranges, actual)
        condition_unknown = _unknown_duration(self.condition_unknown_ranges, actual)
        if self.ranges_retained and value_unknown + self.value_valid_duration_ns != span:
            raise ValueError('条件时间值有效与未知未完整划分实际窗口')
        if self.ranges_retained and condition_unknown + self.condition_known_duration_ns != span:
            raise ValueError('条件时间已知与外条件未知未完整划分实际窗口')
        if not isinstance(self.quality, Q) or type(self.source_refs) is not tuple or any(not isinstance(ref, SourceRef) for ref in self.source_refs):
            raise TypeError('条件时间需要typed质量和完整来源tuple')
        require_text(self.binding_identity, 'conditional_time.binding_identity')


def require_conditional_time_series(series, spec, input_unit, dtype):
    """核对有限联合输入的条件、单位、类型与正交集几何。

    参数: series为有限CalculationSeries，其余为归约的原配置。
    返回: 当前实际交集Interval或None。异常: TypeError/ValueError/OverflowError。
    """
    # BOOL条件已由CalculationSeries验证；缺条件不能被默认为全TRUE或全FALSE。
    if not isinstance(series, CalculationSeries):
        raise TypeError('条件时间归约需要CalculationSeries')
    if series.conditions is None or series.unit != input_unit or series.values[0].dtype is not dtype:
        raise ValueError('条件时间归约需要同单位同dtype及显式BOOL条件')
    left, right = max(spec.window.start_ns, series.observation.start_ns), min(spec.window.end_ns, series.observation.end_ns)
    if right - left > 2**63 - 1:
        raise OverflowError('条件时间正交集跨度超过int64')
    return Interval(left, right) if left <= right else None
