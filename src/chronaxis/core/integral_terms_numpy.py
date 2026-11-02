"""用真实数组计算有限块的原序ZOH面积项，不在块内先求和或换单位。

输入为无条件CalculationSeries/CalculationDefinition，输出只读(N-1,)面积/有效掩码与IntegralFacts。
先裁剪int64端点，批量计算整数差、秒、乘积及非有限/下溢掩码，UNKNOWN不补正常零。
整数到float的判据用独立NumPy转换核；覆盖归约独立，不调用标量面积或覆盖实现。
元数据循环仅恢复未知Interval，不承担数值计算；不修改输入或读写文件。
输出及临时数组需在调用方有限块workspace内消费；本纯核不提供独立内存上限。
"""

# 数值全部用真实ufunc/掩码/归约；只共享冻结事实和配置门槛。
from dataclasses import dataclass
import numpy as np
from .integral_terms import IntegralFacts, require_integral_terms
from .calculations import merge_ranges
from .models import Interval
from .numeric_numpy import DTYPES, NumericArray, to_float_numpy
from .types import QualityFlag as Q


@dataclass(frozen=True)
class NumpyIntegralTerms:
    """持有只读面积及显式有效掩码，数组保持原区间顺序。"""

    areas: np.ndarray  # float64形状(N-1,)，无效位置0只是存储。
    valid: np.ndarray  # bool形状(N-1,)，True位置可归约。
    facts: IntegralFacts  # 当前块原请求/覆盖/诊断和完整真实来源。

    def __post_init__(self):
        """检查真实一维同长只读数组，不接受object或非有限占位。

        参数: 无。返回: None。异常: TypeError/ValueError为数组或事实错误。
        """
        # 只接受同形真实数值列，返回后禁止原地改写冻结面积事实。
        if (not isinstance(self.areas, np.ndarray) or not isinstance(self.valid, np.ndarray)
                or self.areas.dtype != np.float64 or self.valid.dtype != bool
                or self.areas.ndim != 1 or self.areas.shape != self.valid.shape
                or not isinstance(self.facts, IntegralFacts)):
            raise TypeError('数组积分项需要同长一维float64/bool及IntegralFacts')
        if (self.areas.flags.writeable or self.valid.flags.writeable
                or not np.all(np.isfinite(self.areas)) or np.any(~self.valid & (self.areas != 0))):
            raise ValueError('数组积分项必须只读且有限，无效位置仅0存储')


def compute_integral_terms_numpy(series, spec, *, step_ns=None, retain_unknown_ranges=True, valid_until_ns=None):
    """批量生成未转换面积与有效掩码，独立计算覆盖和样本数。

    参数: series为有限CalculationSeries，spec为无条件integral请求；step_ns省略保持
        实际积分，指定时只接收所选驱动真实更新，按实际交集比例计周期。
        retain_unknown_ranges=False跳过未知范围对象构造，仍计算有效时长和质量。
        valid_until_ns为同长实际有效截止；到达截止即失效，不改变记录对分母。
    返回: NumpyIntegralTerms；实际临时/输出列为N或N-1，面积单位input_unit乘秒。
    异常: 输入/单位/时间/分配错误传播；浮点故障追加质量并使对应项无效。
    """
    # typed请求先校验，实际交集仍为整数ns；输入不被裁剪改写。
    require_integral_terms(series, spec, step_ns=step_ns, valid_until_ns=valid_until_ns)
    if type(retain_unknown_ranges) is not bool:
        raise TypeError('未知区间保留选项需要bool')
    start = max(series.observation.start_ns, spec.window.start_ns)
    end = min(series.observation.end_ns, spec.window.end_ns)
    actual = Interval(start, end) if start <= end else None
    # N个值/有效性/uint16质量列；未知0仅存储，独立转换核检查定宽精度。
    column = NumericArray(series.values[0].dtype,
        np.array([value.value if value.valid else 0 for value in series.values], dtype=DTYPES[series.values[0].dtype]),
        np.array([value.valid for value in series.values], dtype=bool),
        np.array([int(value.quality) for value in series.values], dtype=np.uint16))
    values = to_float_numpy(column)
    # 绝对时间不先转float；只对正裁剪区间求安全int64差。
    times = np.array(series.times_ns, dtype=np.int64)
    left, right = np.maximum(times[:-1], np.int64(start)), np.minimum(times[1:], np.int64(end))
    observed = right > left
    # 仅当前块的必要截止掩码；原始右端点继续作为周期比例的分母。
    effective_right = right
    expired_samples = None
    if valid_until_ns is not None:
        deadlines = np.array([item if item is not None else (1 << 63) - 1 for item in valid_until_ns], dtype=np.int64)
        has_deadline = np.array([item is not None for item in valid_until_ns], dtype=bool)
        expired_samples = has_deadline & (times >= deadlines)
        effective_right = np.maximum(left, np.minimum(right, deadlines[:-1]))
    effective = observed if valid_until_ns is None else observed & (effective_right > left)
    durations = np.zeros(len(left), dtype=np.int64)
    np.subtract(effective_right, left, out=durations, where=effective)
    # N与N-1临时列均为当前块副本；mask限制乘法，面积为input_unit乘秒。
    valid_values, quality_values = values.valid.copy(), values.quality.copy()
    if expired_samples is not None:
        valid_values[expired_samples] = False
        quality_values[expired_samples] |= int(Q.STALE)
        quality_values[:-1][observed & (effective_right < right)] |= int(Q.STALE)
    keep = effective & valid_values[:-1]
    areas = np.zeros(len(left), dtype=np.float64)
    seconds = durations.astype(np.float64)
    if step_ns is None:
        seconds /= 1_000_000_000
    else:
        # 完整记录对作为分母；只算当前有限块，不创建第二时间轴或取整权重。
        # CalculationSeries严格递增且观测跨度受int64限制，diff不会溢出或为零。
        seconds /= np.diff(times)
        seconds *= step_ns / 1_000_000_000
    with np.errstate(over='ignore', under='ignore', invalid='ignore'):
        np.multiply(values.values[:-1], seconds, out=areas, where=keep)
    # 计算失败既影响当前面积也影响同位置样本可用性，原输入列保持不变。
    nonfinite = keep & ~np.isfinite(areas)
    underflow = keep & (areas == 0) & (values.values[:-1] != 0)
    quality_values[:-1][nonfinite] |= int(Q.NONFINITE)
    quality_values[:-1][underflow] |= int(Q.PRECISION_LOSS)
    valid_values[:-1][nonfinite | underflow] = False
    keep = effective & valid_values[:-1]
    areas[~keep] = 0.0
    # 真实样本半开计数；非负有效dt总和受原实际跨度int64上界约束。
    actual_updates = np.array(series.actual_value_updates, dtype=bool)
    actual_samples = actual_updates & (times >= start) & (times < end)
    sample_count = int(np.count_nonzero(actual_samples & valid_values))
    duration = int(np.sum(durations, where=keep, dtype=np.int64))
    # 只OR实际样本和已观察正区间的诊断，窗口外末点不污染结果。
    diagnostic = np.array([int(value) for value in series.diagnostics], dtype=np.uint16) | quality_values
    relevant = actual_samples.copy()
    relevant[:-1] |= observed
    quality = Q(int(np.bitwise_or.reduce(diagnostic, where=relevant, initial=0)))
    # 只对有限块的诊断恢复Interval，原时间不经float，合并仅限相邻未知。
    unknown = (tuple(Interval(int(effective_right[index] if keep[index] else left[index]), int(right[index]))
                     for index in np.flatnonzero(observed & (~keep | (effective_right < right))))
               if retain_unknown_ranges else ())
    facts = IntegralFacts(spec, actual, duration, sample_count, merge_ranges(unknown), quality,
                          series.unit, series.binding_identity, series.source_refs)
    # 输出仍归调用方块workspace存活范围；纯核没有独立资源owner。
    areas.setflags(write=False)
    keep.setflags(write=False)
    return NumpyIntegralTerms(areas, keep, facts)
