"""声明有限时间统计的事实和数值结果，不执行时间或数值归约。

TimeCalculationFacts保留一个块的有效时长、TRUE时长、真实更新计数和完整来源。
TimeReductionResult只保存一次最终换单位后的候选数值及计算故障。
无条件时间极值、时间均值和BOOL时长使用各自独立参考/NumPy核；本模块
仅共享类型、单位和输入结构门槛，不读文件、不保留全轴、不管理预算。
纯核及返回的有限事实由外层owner提前预约内存，留存结果也须由外层计费。
"""

# 冻结协议与有限输出检查只依赖通用核心，不依赖NumPy。
from dataclasses import dataclass
from math import isfinite
from .calculations import CalculationDefinition, CalculationSeries, calculation_unit
from .models import Interval, SourceRef
from .types import SignalDType as D, QualityFlag as Q
from .validation import require_text
from .integral_sum import require_partial_limit
from .record_intervals import require_record_step
from .integral_terms import require_valid_until


@dataclass(frozen=True)
class TimeCalculationFacts:
    """保存有限块的真实覆盖事实；FALSE仍是有效BOOL，不能算成未知。

    selected_duration_ns在数值算子等于有效时长，在duration只计有效TRUE。
    sample_count只计半开块内真实更新，duration另要求TRUE，不计共享右端。
    time_weighted_mean的值有效性已包含整数到float的精度检查；权重计算故障不改覆盖。
    """

    spec: CalculationDefinition  # 原请求、政策和scope，不按当前块重写。
    actual_window: Interval | None  # 当前块与原请求的真实交集。
    value_valid_duration_ns: int  # 所有有效值的整数纳秒时长。
    selected_duration_ns: int  # 数值有效时长，或BOOL TRUE时长。
    valid_sample_count: int  # 已选真实更新计数，不是保持区间数。
    value_unknown_ranges: tuple[Interval, ...]  # 完整未知范围，按时序保存。
    quality: Q  # 输入、精度及依赖原因，不表示必须全数值失败。
    input_unit: str  # 原分析单位，尚未做最终输出转换。
    dtype: D  # 原声明类型，极值保留精确整数。
    binding_identity: str  # 实际表达式绑定身份。
    source_refs: tuple[SourceRef, ...]  # 完整定位，保留真实子类和字段。
    ranges_retained: bool = True  # 精简执行可不构造未知位置，不能用于完整覆盖证据。

    def __post_init__(self):
        """核对覆盖划分及真实字段类型，不修复错误事实。

        参数: 无。返回: None。异常: TypeError/ValueError为结构或矛盾时长。
        """
        # 原请求和dtype必须符合时间统计的支持范围。
        require_time_config(self.spec, self.input_unit, self.dtype, None, 4096)
        if self.actual_window is not None and not isinstance(self.actual_window, Interval):
            raise TypeError('时间事实实际范围需要Interval或None')
        span = 0 if self.actual_window is None else self.actual_window.end_ns - self.actual_window.start_ns
        if self.actual_window is not None and (self.actual_window.start_ns < self.spec.window.start_ns
                                               or self.actual_window.end_ns > self.spec.window.end_ns):
            raise ValueError('时间事实范围超出原请求')
        # 纳秒与计数保持原生整数，布尔不能作为时长进入账本。
        if (any(type(value) is not int for value in (self.value_valid_duration_ns,
                self.selected_duration_ns, self.valid_sample_count))
                or not 0 <= self.selected_duration_ns <= self.value_valid_duration_ns <= span
                or not 0 <= self.valid_sample_count <= self.selected_duration_ns):
            raise ValueError('时间事实有效时长、选择或样本计数矛盾')
        if self.spec.operation != 'duration' and self.selected_duration_ns != self.value_valid_duration_ns:
            raise ValueError('无条件数值的选择时长必须等于有效时长')
        # 有效与未知必须完整划分正区间，不接受重复、越界或无序诊断。
        if type(self.value_unknown_ranges) is not tuple:
            raise TypeError('时间事实未知范围需要tuple')
        cursor = self.actual_window.start_ns if self.actual_window is not None else 0
        unknown = 0
        for item in self.value_unknown_ranges:
            if (not isinstance(item, Interval) or item.start_ns < cursor or item.start_ns >= item.end_ns
                    or self.actual_window is None or item.end_ns > self.actual_window.end_ns):
                raise ValueError('时间事实未知范围无序、重叠或越界')
            cursor, unknown = item.end_ns, unknown + item.end_ns - item.start_ns
        if type(self.ranges_retained) is not bool or not self.ranges_retained and self.value_unknown_ranges:
            raise ValueError('精简时间事实不能携带未知范围')
        if self.ranges_retained and unknown + self.value_valid_duration_ns != span:
            raise ValueError('时间事实未完整划分有效和未知时长')
        # 原因、来源与身份不能由自由文字或路径占位替代。
        if not isinstance(self.quality, Q) or type(self.source_refs) is not tuple or any(not isinstance(ref, SourceRef) for ref in self.source_refs):
            raise TypeError('时间事实需要typed质量和完整来源tuple')
        require_text(self.binding_identity, 'time.binding_identity')


@dataclass(frozen=True)
class TimeReductionResult:
    """保存整窗时间统计的数值快照，覆盖与report/strict由外层分类。

    极值可为精确int；均值与时长为float。有效零和无有效证据的None分别保存。
    valid_term_count统计有效正区间，不等于真实更新样本数或TRUE区间数。
    """

    value: int | float | None  # 最终单位下的有限候选值。
    unit: str  # 已核对的输出单位，不再逐块换算。
    calculation_failed: bool  # 权重、原序求和或最终转换故障。
    quality: Q  # 仅本次数值归约故障，输入原因在facts。
    valid_term_count: int  # 原值经算子门槛后有效的正区间数。

    def __post_init__(self):
        """拒绝未知、正常零和故障之间的矛盾，不补候选值。

        参数: 无。返回: None。异常: TypeError/ValueError为字段或状态矛盾。
        """
        require_text(self.unit, 'time.output_unit')
        # 精确整数无需float检查；bool与非有限浮点均不是有效统计输出。
        if self.value is not None and (type(self.value) not in (int, float)
                or type(self.value) is float and not isfinite(self.value)):
            raise ValueError('时间归约值需要有限int/float或None')
        if (type(self.calculation_failed) is not bool or not isinstance(self.quality, Q)
                or type(self.valid_term_count) is not int or self.valid_term_count < 0):
            raise TypeError('时间归约状态、质量和项数类型错误')
        # 数值故障须有明确证据，成功项不可无值，也不能混入数值故障原因。
        if self.calculation_failed:
            if self.value is not None or self.quality == Q.NONE or self.valid_term_count == 0:
                raise ValueError('时间计算故障需要有效项、None和质量原因')
        elif self.quality != Q.NONE or ((self.valid_term_count == 0) != (self.value is None)):
            raise ValueError('时间成功数值、项数或质量矛盾')


@dataclass(frozen=True)
class MeanTimeBlock:
    """借出一批均值所需数值和权重；不含原帧、双时间或逐条来源。

    values/weights为参考tuple或NumPy有限列，调用者为其内存付费。
    仅均值首遍显式请求时生成；facts仍用于必要的结果分类。
    """

    facts: object  # 无条件或条件时间事实。
    values: object  # 已通过均值精度门槛的有限数值列。
    weights: object  # 与values同长的正权重，周期模式为折算秒数。


def require_time_config(spec, input_unit, dtype, selected_duration_ns, partial_limit, *,
                        step_ns=None, selected_weight_seconds=None):
    """检查无条件时间归约配置，不执行数值转换或计算。

    参数: 原spec/单位/dtype；selected_duration_ns为actual均值第二遍整窗时长；
        step_ns为固定/DBC周期，该模式均值改用selected_weight_seconds有效权重秒数。
    返回: (output_unit, factor)。异常: TypeError/ValueError为不支持能力或非法配置。
    """
    # 样本统计及条件选择有独立接口，不由时间统计配置承载。
    if not isinstance(spec, CalculationDefinition) or spec.operation not in ('min_time', 'max_time', 'time_weighted_mean', 'duration'):
        raise TypeError('有限时间归约仅支持明确无条件时间算子')
    allowed = (D.BOOL,) if spec.operation == 'duration' else (D.INT64, D.UINT64, D.FLOAT64)
    if not isinstance(dtype, D) or dtype not in allowed:
        raise ValueError('时间算子与dtype不匹配')
    require_text(input_unit, 'time.input_unit')
    require_partial_limit(partial_limit)
    require_record_step(step_ns, ())
    if step_ns is not None and selected_duration_ns is not None:
        raise ValueError('周期均值不能使用实际纳秒时长作分母')
    if selected_weight_seconds is not None and (
            step_ns is None or spec.operation != 'time_weighted_mean'
            or type(selected_weight_seconds) is not float
            or not isfinite(selected_weight_seconds) or selected_weight_seconds <= 0):
        raise ValueError('仅周期均值第二遍接受有限正float权重秒数')
    # None明确表示均值第一遍；第二遍分母须正且可由安全int64时长表示。
    if selected_duration_ns is not None and (spec.operation != 'time_weighted_mean' or type(selected_duration_ns) is not int
            or not 0 < selected_duration_ns <= 2 ** 63 - 1):
        raise ValueError('仅时间均值第二遍接受正原生int64整窗有效时长')
    return calculation_unit(spec, input_unit)


def require_time_series(series, spec, input_unit, dtype):
    """校验有限输入身份类型与正交集时长，不共享数值运算。

    参数: series为有限CalculationSeries，其余为归约构造配置。
    返回: 当前实际交集Interval或None。异常: TypeError/ValueError/OverflowError。
    """
    # 只接受真实模型及无条件列，不自动转dtype、换单位或处理缺失结构。
    if not isinstance(series, CalculationSeries):
        raise TypeError('时间归约需要CalculationSeries')
    if series.conditions is not None or series.unit != input_unit or series.values[0].dtype is not dtype:
        raise ValueError('时间归约只接受同单位同dtype的无条件输入')
    left, right = max(spec.window.start_ns, series.observation.start_ns), min(spec.window.end_ns, series.observation.end_ns)
    if right - left > 2 ** 63 - 1:
        raise OverflowError('时间统计正交集时长超过int64')
    return Interval(left, right) if left <= right else None


def require_time_options(series, step_ns, valid_until_ns, retain_unknown_ranges):
    """检查记录周期、实际截止和范围输出开关，不执行数值计算。

    参数: 有限series、可选周期、同长截止tuple和bool开关。返回: None。
    异常: 类型、长度或将合成边界当周期记录时拒绝。
    """
    require_record_step(step_ns, series.actual_value_updates)
    require_valid_until(series.times_ns, valid_until_ns)
    if type(retain_unknown_ranges) is not bool:
        raise TypeError('未知范围保留开关需要bool')
