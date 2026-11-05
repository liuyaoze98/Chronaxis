"""声明有限样本统计事实、数值快照与结构门槛，不执行样本归约。

支持样本极值、均值、计数、方差、标准差、RMS及精确分位数。BOOL条件可省略为全TRUE。值有效与条件
已知分别完整划分实际窗口；FALSE不选择，UNKNOWN不当FALSE。真实样本仅计半开
窗口内原值实际更新且有效/TRUE，TTL、条件更新和裁剪保持边界不能成为样本。
mean的值覆盖包含整数转float精度门槛，求和、除法和单位故障单独记数值失败。
纯协议不读来源、不管理预算、不保存全轴；有限元数据及结果由外层owner计费。
"""

# 两数值后端仅共享冻结协议、单位和几何校验，数值与覆盖计算各自独立。
from .moments import SAMPLE_MOMENTS
from .quantiles import SAMPLE_QUANTILES
from dataclasses import dataclass
from math import isfinite
from .integral_sum import require_partial_limit
from .calculations import CalculationSeries, CalculationDefinition, calculation_conversion
from .models import Interval, SourceRef
from .types import QualityFlag as Q, SignalDType as D
from .validation import require_text


def _unknown_duration(ranges, actual):
    """校验一种未知范围并精确累计纳秒，不用总长度掩盖重复位置。

    参数: ranges为冻结正Interval tuple；actual为原请求内交集或None。
    返回: 原生int未知总时长。异常: TypeError/ValueError为类型、反序、重叠或越界。
    """
    # 值和条件各自执行本结构检查，不能互相补充另一种覆盖缺口。
    if type(ranges) is not tuple:
        raise TypeError('样本事实未知范围需要tuple')
    cursor, total = (actual.start_ns if actual is not None else 0), 0
    for item in ranges:
        if (not isinstance(item, Interval) or actual is None or item.start_ns < cursor
                or item.start_ns >= item.end_ns or item.end_ns > actual.end_ns):
            raise ValueError('样本未知范围必须有序、不重叠且在实际窗口内')
        cursor, total = item.end_ns, total + item.end_ns - item.start_ns
    return total


@dataclass(frozen=True)
class SampleCalculationFacts:
    """保存有限块双覆盖与真实选中样本，样本数不代替区间数或时长。

    selected只计条件TRUE且数值可用的正时长，selected_value_unknown只计TRUE值未知。
    无条件known等于实际跨度、false为0；mean精度失败属于值未知，数值累计失败不改事实。
    """

    spec: CalculationDefinition  # 原samples请求、scope与覆盖政策。
    actual_window: Interval | None  # 当前块真实交集，不外推EOF。
    value_valid_duration_ns: int  # 通过本算子值门槛的有效纳秒。
    condition_known_duration_ns: int  # 条件可判断TRUE/FALSE的纳秒。
    selected_duration_ns: int  # 条件TRUE且值有效的保持纳秒，不是样本分母。
    selected_value_unknown_duration_ns: int  # TRUE但值未知的纳秒。
    false_duration_ns: int  # 明确FALSE纳秒，不包含条件UNKNOWN。
    valid_sample_count: int  # 半开窗口中有效/TRUE的原值真实更新。
    value_unknown_ranges: tuple[Interval, ...]  # 原值和mean精度未知位置。
    condition_unknown_ranges: tuple[Interval, ...]  # 独立BOOL UNKNOWN位置。
    quality: Q  # 输入、精度与依赖原因，不含归约数值故障。
    input_unit: str  # 原分析工程单位，未最终转换。
    dtype: D  # 原数值声明，极值保持int64/uint64精确整数。
    binding_identity: str  # 原值联合输入实际身份。
    source_refs: tuple[SourceRef, ...]  # 完整来源定位，保留真实子类。

    def __post_init__(self):
        """核对完整双分区、选择交集及typed字段，不修补事实。

        参数: 无。返回: None。异常: TypeError/ValueError为配置、覆盖、类型或几何矛盾。
        """
        # 结构配置不执行数值转换，只检查样本统计能力与单位。
        require_sample_config(self.spec, self.input_unit, self.dtype, 4096)
        if self.actual_window is not None and not isinstance(self.actual_window, Interval):
            raise TypeError('样本实际范围需要Interval或None')
        actual, request = self.actual_window, self.spec.window
        span = 0 if actual is None else actual.end_ns - actual.start_ns
        if actual is not None and not request.start_ns <= actual.start_ns <= actual.end_ns <= request.end_ns:
            raise ValueError('样本事实实际范围超出原请求')
        durations = (self.value_valid_duration_ns, self.condition_known_duration_ns, self.selected_duration_ns,
                     self.selected_value_unknown_duration_ns, self.false_duration_ns)
        # 原生整数纳秒与计数不能接受bool/浮点；TRUE值未知不能超过全部值未知。
        if (any(type(value) is not int or not 0 <= value <= span for value in durations)
                or type(self.valid_sample_count) is not int or not 0 <= self.valid_sample_count <= self.selected_duration_ns
                or self.selected_duration_ns > self.value_valid_duration_ns
                or self.selected_value_unknown_duration_ns > span - self.value_valid_duration_ns
                or self.false_duration_ns > self.condition_known_duration_ns
                or self.selected_duration_ns + self.selected_value_unknown_duration_ns
                   != self.condition_known_duration_ns - self.false_duration_ns):
            raise ValueError('样本事实计数、选择与双覆盖交集矛盾')
        if _unknown_duration(self.value_unknown_ranges, actual) + self.value_valid_duration_ns != span:
            raise ValueError('样本值有效与未知未完整划分实际窗口')
        if _unknown_duration(self.condition_unknown_ranges, actual) + self.condition_known_duration_ns != span:
            raise ValueError('样本条件已知与未知未完整划分实际窗口')
        # 完整来源和质量保持真实类型，不将文件名或自由文字当作来源证据。
        if not isinstance(self.quality, Q) or type(self.source_refs) is not tuple or any(not isinstance(ref, SourceRef) for ref in self.source_refs):
            raise TypeError('样本事实需要typed质量和完整来源tuple')
        require_text(self.binding_identity, 'sample.binding_identity')


@dataclass(frozen=True)
class SampleReductionResult:
    """保存最终单位数值与真实样本数，不复用时间统计的区间项数语义。

    极值可保留精确int，均值为float；有效零、无样本None和数值失败分别表示。
    输入覆盖与最终report/strict/空选择分类由外层负责，数值快照不补正常零。
    """

    value: int | float | None  # 最终单位有限候选，无法核实为None。
    unit: str  # 最终输出标签，已换单位一次。
    calculation_failed: bool  # 原序和、除法或最终转换失败。
    quality: Q  # 仅数值故障，输入原因另存facts。
    valid_sample_count: int  # 实际参与候选的有效真实样本数。
    insufficient_samples: bool = False  # 单个样本无法定义ddof=1的离散度。

    def __post_init__(self):
        """拒绝样本数、正常数值和失败状态之间的矛盾。

        参数: 无。返回: None。异常: TypeError/ValueError为字段类型或不可能数值状态。
        """
        # 非有限/bool不能成为正常候选，原整数不被float检查造成舍入。
        require_text(self.unit, 'sample.output_unit')
        if self.value is not None and (type(self.value) not in (int, float)
                or type(self.value) is float and not isfinite(self.value)):
            raise ValueError('样本结果需要有限int/float或None')
        if (type(self.calculation_failed) is not bool or not isinstance(self.quality, Q)
                or type(self.valid_sample_count) is not int or self.valid_sample_count < 0):
            raise TypeError('样本结果需要真实失败状态、质量和非负原生int计数')
        # 空样本只能无值；有效失败须有样本及原因，成功不带数值故障位。
        if type(self.insufficient_samples) is not bool:
            raise TypeError('不足样本标志需要bool')
        if self.insufficient_samples:
            if self.valid_sample_count != 1 or self.value is not None or self.calculation_failed or self.quality != Q.NONE:
                raise ValueError('自由度不足必须保留一个有效样本及无数值状态')
        elif self.calculation_failed:
            if self.value is not None or self.quality == Q.NONE or self.valid_sample_count == 0:
                raise ValueError('样本数值失败需要有效样本、None与明确原因')
        elif self.quality != Q.NONE or (self.valid_sample_count == 0) != (self.value is None):
            raise ValueError('样本成功结果数值、计数或质量矛盾')


def require_sample_config(spec, input_unit, dtype, partial_limit):
    """校验三samples能力、数值dtype与明确单位，不计算样本。

    参数: 原spec/input_unit/dtype及正原生int误差容量partial_limit。
    返回: CalculationConversion。异常: TypeError/ValueError为类型、能力、单位或容量。
    """
    # BOOL/ENUM与时间算子各有独立口径，不在本核中暗自提升或扩展。
    if not isinstance(spec, CalculationDefinition) or spec.operation not in ('sample_count', 'sample_minimum', 'sample_maximum', 'sample_mean', *SAMPLE_MOMENTS, *SAMPLE_QUANTILES):
        raise TypeError('样本归约需要已支持的样本统计操作')
    if not isinstance(dtype, D) or dtype not in (D.INT64, D.UINT64, D.FLOAT64):
        raise ValueError('样本统计只接受数值dtype')
    require_text(input_unit, 'sample.input_unit')
    require_partial_limit(partial_limit)
    return calculation_conversion(spec, input_unit)


def require_sample_series(series, spec, input_unit, dtype):
    """核对有限输入unit/dtype及精确交集，保留可选BOOL条件。

    参数: series为有限CalculationSeries，其余为归约原配置。
    返回: 实际交集Interval或None。异常: TypeError/ValueError/OverflowError。
    """
    # CalculationSeries已校验可选条件列为BOOL；不自动换单位、转dtype或补原值更新。
    if not isinstance(series, CalculationSeries):
        raise TypeError('样本归约需要CalculationSeries')
    if series.unit != input_unit or series.values[0].dtype is not dtype:
        raise ValueError('样本归约只接受同unit及同dtype输入')
    left, right = max(spec.window.start_ns, series.observation.start_ns), min(spec.window.end_ns, series.observation.end_ns)
    if right-left > 2**63-1:
        raise OverflowError('样本正交集跨度超过int64')
    return Interval(left, right) if left <= right else None
