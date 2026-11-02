"""独立标量生成有限条件积分面积，分别保存值覆盖与BOOL条件覆盖。

输入为有限CalculationSeries和原integral请求，输出原序(N-1,)面积/掩码及冻结事实。
每个值先通过标量浮点精度检查；只有TRUE且有效值才乘裁剪后的整数纳秒时长。
面积溢出或非零下溢使该位置值和真实样本失效；FALSE、UNKNOWN不做面积乘法。
不把UNKNOWN补零，不归约面积或转换最终单位，不读取来源、不修改输入。
只依赖标准库及typed模型，不调用NumPy；有限临时列须由调用方owner预约。
"""

# 标量数值与覆盖判据独立于数组核，仅复用已校验模型和结构门槛。
from math import isfinite
from .conditional_integral_terms import ConditionalIntegralFacts, ReferenceConditionalIntegralTerms, require_conditional_integral_terms
from .calculations import merge_ranges
from .models import Interval
from .numeric import ScalarValue, to_float_reference
from .types import QualityFlag as Q
from .record_intervals import clipped_record_seconds


def compute_conditional_integral_terms_reference(series, spec, *, step_ns=None, valid_until_ns=None,
                                                condition_valid_until_ns=None, retain_unknown_ranges=True):
    """逐正区间生成未转换原序面积与独立值、条件覆盖事实。

    参数: series为有限数值CalculationSeries及显式BOOL条件，spec为原integral请求。
        step_ns为可选所选周期；两个until列是实际有效截止；范围明细可显式关闭。
    返回: ReferenceConditionalIntegralTerms；面积为输入单位乘秒，无效槽位0配False。
    异常: 输入、单位、时间与分配错误传播；精度、面积溢出/下溢写入质量及未知。
    """
    # 结构先校验，裁剪保留精确整数ns；没有交集不凭空创建观察域。
    require_conditional_integral_terms(series, spec, step_ns=step_ns, valid_until_ns=valid_until_ns,
                                      condition_valid_until_ns=condition_valid_until_ns)
    if type(retain_unknown_ranges) is not bool:
        raise TypeError('未知范围保留选项需要bool')
    start = max(series.observation.start_ns, spec.window.start_ns)
    end = min(series.observation.end_ns, spec.window.end_ns)
    actual = Interval(start, end) if start <= end else None
    # 所有值都接受原完整积分的精度门槛，包括FALSE与UNKNOWN未选择的值。
    values = [to_float_reference(value) for value in series.values]
    conditions = series.conditions if condition_valid_until_ns is None else list(series.conditions)
    # 到期点本身已失效；未到期的部分区间在下方独立裁剪。
    for rows, deadlines in ((values, valid_until_ns), (conditions, condition_valid_until_ns)):
        if deadlines is not None:
            for index, deadline in enumerate(deadlines):
                if deadline is not None and series.times_ns[index] >= deadline:
                    old = rows[index]
                    rows[index] = ScalarValue(None, old.dtype, False, old.quality | Q.STALE, old.labels)
    areas, valid, value_unknown, condition_unknown = [], [], [], []
    value_duration, known_duration, selected_duration = 0, 0, 0
    selected_unknown_duration, false_duration, sample_count, quality = 0, 0, 0, Q.NONE
    # 原N-1槽位顺序不变；数值未跨块归约，条件单独变化只改变选择覆盖。
    for index in range(len(series.times_ns) - 1):
        left, right = max(start, series.times_ns[index]), min(end, series.times_ns[index + 1])
        area, keep = 0.0, False
        if left < right:
            value, condition = values[index], conditions[index]
            quality |= series.diagnostics[index] | value.quality | condition.quality
            value_end = right if valid_until_ns is None or valid_until_ns[index] is None else max(left, min(right, valid_until_ns[index]))
            condition_end = right if condition_valid_until_ns is None or condition_valid_until_ns[index] is None else max(left, min(right, condition_valid_until_ns[index]))
            selected_end = min(value_end, condition_end)
            if value_end < right or condition_end < right:
                quality |= Q.STALE
            # 只有明确TRUE才计算面积；FALSE不因未执行的溢出丢掉值覆盖。
            if value.valid and condition.valid and condition.value and selected_end > left:
                seconds = ((selected_end - left) / 1_000_000_000 if step_ns is None else
                    clipped_record_seconds(series.times_ns[index], series.times_ns[index + 1],
                        spec.window if selected_end == right else Interval(left, selected_end), step_ns=step_ns))
                term = value.value * seconds
                failure = Q.NONFINITE if not isfinite(term) else Q.PRECISION_LOSS if term == 0 and value.value != 0 else Q.NONE
                if failure == Q.NONE:
                    area, keep = term, True
                else:
                    # 局部转换列同时更新样本有效性；原ScalarValue不被改写。
                    value = ScalarValue(value.value, value.dtype, False, value.quality | failure, value.labels)
                    values[index] = value
                    quality |= failure
            # 值和条件各自完整分区；TRUE值未知与条件UNKNOWN分别登记。
            if value.valid:
                value_duration += value_end - left
                if retain_unknown_ranges and value_end < right:
                    value_unknown.append(Interval(value_end, right))
            elif retain_unknown_ranges:
                value_unknown.append(Interval(left, right))
            if condition.valid:
                known_duration += condition_end - left
                if not condition.value:
                    false_duration += condition_end - left
                elif value.valid:
                    selected_duration += selected_end - left
                    selected_unknown_duration += condition_end - selected_end
                else:
                    selected_unknown_duration += condition_end - left
                if retain_unknown_ranges and condition_end < right:
                    condition_unknown.append(Interval(condition_end, right))
            elif retain_unknown_ranges:
                condition_unknown.append(Interval(left, right))
        # 未观察槽位也保留原位置，但不形成UNKNOWN或正常积分项。
        areas.append(area)
        valid.append(keep)
    # 只计半开范围内原值真实更新且有效/TRUE；条件更新与末点不能计样本。
    for index, time in enumerate(series.times_ns):
        if start <= time < end and series.actual_value_updates[index]:
            value, condition = values[index], conditions[index]
            quality |= series.diagnostics[index] | value.quality | condition.quality
            if value.valid and condition.valid and condition.value:
                sample_count += 1
    # 两未知元组仅合并相邻范围；完整来源子类和联合绑定身份原样保留。
    facts = ConditionalIntegralFacts(spec, actual, value_duration, known_duration, selected_duration,
        selected_unknown_duration, false_duration, sample_count, merge_ranges(value_unknown),
        merge_ranges(condition_unknown), quality, series.unit, series.binding_identity, series.source_refs,
        ranges_retained=retain_unknown_ranges)
    return ReferenceConditionalIntegralTerms(tuple(areas), tuple(valid), facts)
