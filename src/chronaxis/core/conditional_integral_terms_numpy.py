"""用真实NumPy列运算生成有限条件积分面积与各自的覆盖事实。

输入有限数值CalculationSeries、显式BOOL条件与原integral请求，输出只读一维float64
面积、bool掩码及ConditionalIntegralFacts。先按整数ns裁剪，再按TRUE/有效掩码乘秒。
数值转换、面积、故障和覆盖归约独立于标量参考；元数据循环只恢复诊断Interval。
FALSE、UNKNOWN不做乘法，不把未知存储零视为正常结果，不提前归约或换单位。
不修改输入、不读来源；N/N-1临时列及输出由调用方有限workspace预约并消费。
"""

# 只共享非数值模型门槛；计算采用独立NumPy转换与真实ufunc/掩码。
from dataclasses import dataclass
import numpy as np
from .conditional_integral_terms import ConditionalIntegralFacts, require_conditional_integral_terms
from .calculations import merge_ranges
from .models import Interval
from .numeric_numpy import DTYPES, NumericArray, to_float_numpy
from .types import QualityFlag as Q


@dataclass(frozen=True)
class NumpyConditionalIntegralTerms:
    """保存原序只读面积与明确掩码，不借用可写输入或隐式掩码数组。"""

    areas: np.ndarray  # float64形状(N-1,)，未转换的输入单位乘秒。
    valid: np.ndarray  # bool形状(N-1,)，仅TRUE且正常面积可归约。
    facts: ConditionalIntegralFacts  # 当前块双覆盖、样本与来源，不是全窗结果。

    def __post_init__(self):
        """检查普通一维同长只读列、有限面积及冻结事实。

        参数: 无。返回: None。异常: TypeError/ValueError为类型、形状、可写或占位错误。
        """
        # 拒绝自定义/隐藏掩码子类；纯输出不能依赖调用侧数组行为。
        if (type(self.areas) is not np.ndarray or type(self.valid) is not np.ndarray
                or self.areas.dtype != np.float64 or self.valid.dtype != bool
                or self.areas.ndim != 1 or self.areas.shape != self.valid.shape
                or not isinstance(self.facts, ConditionalIntegralFacts)):
            raise TypeError('数组条件积分项需要同长一维float64/bool及ConditionalIntegralFacts')
        if (self.areas.flags.writeable or self.valid.flags.writeable
                or not np.all(np.isfinite(self.areas)) or np.any(~self.valid & (self.areas != 0))):
            raise ValueError('数组条件积分项必须只读且有限，无效位置只能0存储')


def compute_conditional_integral_terms_numpy(series, spec, *, step_ns=None, valid_until_ns=None,
                                           condition_valid_until_ns=None, retain_unknown_ranges=True):
    """按真实数组掩码生成面积，独立归约值、条件和选择覆盖。

    参数: series为有限数值CalculationSeries及显式BOOL条件，spec为原integral请求。
        step_ns选择固定/DBC周期；两个until列给实际有效截止；范围明细可显式关闭。
    返回: NumpyConditionalIntegralTerms；只读面积/掩码形状N-1，临时列形状N或N-1。
    异常: 输入、单位、时间和分配错误传播；浮点故障写质量并使对应值/面积失效。
    """
    # 时间不先转float，实际交集为整数域；所有有限输入先过公共结构门槛。
    require_conditional_integral_terms(series, spec, step_ns=step_ns, valid_until_ns=valid_until_ns,
                                      condition_valid_until_ns=condition_valid_until_ns)
    if type(retain_unknown_ranges) is not bool:
        raise TypeError('未知范围保留选项需要bool')
    start = max(series.observation.start_ns, spec.window.start_ns)
    end = min(series.observation.end_ns, spec.window.end_ns)
    actual = Interval(start, end) if start <= end else None
    # N个真实typed值经独立数组精度核；无效0仅是受valid约束的存储。
    column = NumericArray(series.values[0].dtype,
        np.array([value.value if value.valid else 0 for value in series.values], dtype=DTYPES[series.values[0].dtype]),
        np.array([value.valid for value in series.values], dtype=bool),
        np.array([int(value.quality) for value in series.values], dtype=np.uint16))
    values = to_float_numpy(column)
    # BOOL列按已知和真值两个(N,)掩码处理，UNKNOWN占位False不进入FALSE覆盖。
    known = np.array([condition.valid for condition in series.conditions], dtype=bool)
    truth = np.array([condition.value if condition.valid else False for condition in series.conditions], dtype=bool)
    condition_quality = np.array([int(condition.quality) for condition in series.conditions], dtype=np.uint16)
    times = np.array(series.times_ns, dtype=np.int64)
    left, right = np.maximum(times[:-1], np.int64(start)), np.minimum(times[1:], np.int64(end))
    observed = right > left
    durations = np.zeros(len(left), dtype=np.int64)
    np.subtract(right, left, out=durations, where=observed)
    # 当前块副本可标记面积故障；只对TRUE有效正区间执行input_unit乘秒的ufunc。
    valid_values, quality_values = values.valid.copy(), values.quality.copy()
    value_right, condition_right = right, right
    value_durations, condition_durations = durations, durations
    # 两种有效性各有实际截止，不能用一个联合截止丢掉已知FALSE或值覆盖。
    for deadlines, is_value in ((valid_until_ns, True), (condition_valid_until_ns, False)):
        if deadlines is None:
            continue
        expiry = np.array([item if item is not None else (1 << 63) - 1 for item in deadlines], dtype=np.int64)
        has_expiry = np.array([item is not None for item in deadlines], dtype=bool)
        expired = has_expiry & (times >= expiry)
        clipped = np.maximum(left, np.minimum(right, expiry[:-1]))
        clipped_durations = np.zeros(len(left), dtype=np.int64)
        np.subtract(clipped, left, out=clipped_durations, where=observed)
        if is_value:
            valid_values[expired] = False
            quality_values[expired] |= int(Q.STALE)
            quality_values[:-1][observed & (clipped < right)] |= int(Q.STALE)
            value_right, value_durations = clipped, clipped_durations
        else:
            known[expired] = False
            condition_quality[expired] |= int(Q.STALE)
            condition_quality[:-1][observed & (clipped < right)] |= int(Q.STALE)
            condition_right, condition_durations = clipped, clipped_durations
    selected_durations = (durations if valid_until_ns is None and condition_valid_until_ns is None
                          else np.minimum(value_durations, condition_durations))
    keep = observed & (selected_durations > 0) & valid_values[:-1] & known[:-1] & truth[:-1]
    areas = np.zeros(len(left), dtype=np.float64)
    seconds = selected_durations.astype(np.float64)
    if step_ns is None:
        seconds /= 1_000_000_000
    else:
        # 分母保留完整实际记录对，不能改用条件/有效期裁剪后的长度。
        seconds /= np.diff(times)
        seconds *= step_ns / 1_000_000_000
    with np.errstate(over='ignore', under='ignore', invalid='ignore'):
        np.multiply(values.values[:-1], seconds, out=areas, where=keep)
    # 非有限及非零下溢只标实际执行的TRUE项，并使该位置真实样本失效。
    nonfinite = keep & ~np.isfinite(areas)
    underflow = keep & (areas == 0) & (values.values[:-1] != 0)
    quality_values[:-1][nonfinite] |= int(Q.NONFINITE)
    quality_values[:-1][underflow] |= int(Q.PRECISION_LOSS)
    valid_values[:-1][nonfinite | underflow] = False
    keep = observed & (selected_durations > 0) & valid_values[:-1] & known[:-1] & truth[:-1]
    areas[~keep] = 0.0
    # 五种覆盖分别按(N-1,)掩码归约正整数ns，总和不超过已验证int64实际跨度。
    value_duration = int(np.sum(value_durations, where=observed & valid_values[:-1], dtype=np.int64))
    known_duration = int(np.sum(condition_durations, where=observed & known[:-1], dtype=np.int64))
    selected_duration = int(np.sum(selected_durations, where=keep, dtype=np.int64))
    selected_unknown_duration = int(np.sum(condition_durations, where=observed & known[:-1] & truth[:-1], dtype=np.int64)) - selected_duration
    false_duration = int(np.sum(condition_durations, where=observed & known[:-1] & ~truth[:-1], dtype=np.int64))
    # 样本只计真实原值更新；条件变化与右终点不成为数值样本。
    actual_updates = np.array(series.actual_value_updates, dtype=bool)
    actual_samples = actual_updates & (times >= start) & (times < end)
    sample_count = int(np.count_nonzero(actual_samples & valid_values & known & truth))
    # 诊断来自实际正区间或真实样本，不将窗口外末点质量传播入结果。
    diagnostic = np.array([int(flag) for flag in series.diagnostics], dtype=np.uint16) | quality_values | condition_quality
    relevant = actual_samples.copy()
    relevant[:-1] |= observed
    quality = Q(int(np.bitwise_or.reduce(diagnostic, where=relevant, initial=0)))
    # Python循环仅将有限未知掩码恢复精确Interval；数值和覆盖未调用参考核。
    value_unknown = (tuple(Interval(int(value_right[index] if valid_values[index] else left[index]), int(right[index]))
        for index in np.flatnonzero(observed & (~valid_values[:-1] | (value_right < right)))) if retain_unknown_ranges else ())
    condition_unknown = (tuple(Interval(int(condition_right[index] if known[index] else left[index]), int(right[index]))
        for index in np.flatnonzero(observed & (~known[:-1] | (condition_right < right)))) if retain_unknown_ranges else ())
    facts = ConditionalIntegralFacts(spec, actual, value_duration, known_duration, selected_duration,
        selected_unknown_duration, false_duration, sample_count, merge_ranges(value_unknown),
        merge_ranges(condition_unknown), quality, series.unit, series.binding_identity, series.source_refs,
        ranges_retained=retain_unknown_ranges)
    # 返回只读列供独立原序float归约；输出未申请独立owner，不能脱离已预约workspace留存。
    areas.setflags(write=False)
    keep.setflags(write=False)
    return NumpyConditionalIntegralTerms(areas, keep, facts)
