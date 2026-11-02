"""独立标量计算有限块中的原序ZOH面积项，保留未知与覆盖事实。

输入为无选择条件的CalculationSeries/CalculationDefinition，输出ReferenceIntegralTerms。
逐正区间先裁剪整数ns，再乘当前有效值；不跨UNKNOWN，不先求和或换单位。
严格检查整数到float精度、乘积非有限和非零下溢，并更新该区间样本可用性。
只依赖标准库及typed核心，不调用NumPy、不读文件、不修改输入。
所有有限列表/冻结输出在调用方块workspace内使用，单独调用不提供内存上限。
"""

# 标量有限性及精度判据独立于数组核，只有模型与门槛共享。
from math import isfinite
from .integral_terms import IntegralFacts, ReferenceIntegralTerms, require_integral_terms
from .calculations import merge_ranges
from .models import Interval
from .numeric import ScalarValue, to_float_reference
from .types import QualityFlag as Q
from .record_intervals import clipped_record_seconds


def compute_integral_terms_reference(series, spec, *, step_ns=None, retain_unknown_ranges=True, valid_until_ns=None):
    """逐区间计算原序未转换面积与明确有效掩码。

    参数: series为有限CalculationSeries；spec为无条件integral CalculationDefinition；step_ns省略
        保持实际积分，指定时输入仅含所选驱动真实更新，按实际交集比例计周期。
        retain_unknown_ranges=False不构造未知区间明细，保留计算所需的有效时长/质量。
        valid_until_ns为同长实际有效截止，None项表示本块无额外截止；到达截止即失效。
    返回: ReferenceIntegralTerms，areas/valid长度N-1；面积单位为input_unit乘秒。
    异常: 输入/单位/时间/分配错误传播；数值精度/溢出/下溢写入质量并使面积无效。
    """
    # 先验证请求；裁剪仍在精确整数ns域，无交集不产生实际范围。
    require_integral_terms(series, spec, step_ns=step_ns, valid_until_ns=valid_until_ns)
    if type(retain_unknown_ranges) is not bool:
        raise TypeError('未知区间保留选项需要bool')
    start = max(series.observation.start_ns, spec.window.start_ns)
    end = min(series.observation.end_ns, spec.window.end_ns)
    actual = Interval(start, end) if start <= end else None
    # 每值转换独立检查精度，不改变原ScalarValue。
    values = [to_float_reference(value) for value in series.values]
    # 已经失效的驱动快照不能继续计算；过期时间不由固定周期延长。
    if valid_until_ns is not None:
        for index, deadline in enumerate(valid_until_ns):
            if deadline is not None and series.times_ns[index] >= deadline:
                value = values[index]
                values[index] = ScalarValue(value.value, value.dtype, False, value.quality | Q.STALE, value.labels)
    # 列长度受调用方有限输入约束；逐区间保留原顺序，不累计面积总值。
    areas, valid, unknown = [], [], []
    duration, sample_count, quality = 0, 0, Q.NONE
    for index in range(len(series.times_ns) - 1):
        left, right = max(start, series.times_ns[index]), min(end, series.times_ns[index + 1])
        area, keep = 0.0, False
        if left < right:
            deadline = None if valid_until_ns is None else valid_until_ns[index]
            effective_right = right if deadline is None else max(left, min(right, deadline))
            # 非零实际区间才纳入来源诊断，末点不增加面积。
            value = values[index]
            quality |= series.diagnostics[index] | value.quality
            if effective_right < right:
                quality |= Q.STALE
            if value.valid and left < effective_right:
                seconds = ((effective_right - left) / 1_000_000_000 if step_ns is None else
                           clipped_record_seconds(series.times_ns[index], series.times_ns[index + 1],
                                                  spec.window if effective_right == right else Interval(left, effective_right),
                                                  step_ns=step_ns))
                term = value.value * seconds
                failure = Q.NONFINITE if not isfinite(term) else Q.PRECISION_LOSS if term == 0 and value.value != 0 else Q.NONE
                if failure == Q.NONE:
                    area, keep = term, True
                    duration += effective_right - left
                else:
                    # 失败项和该位置真实样本均不可核实，不把下溢当正常零。
                    quality |= failure
                    values[index] = ScalarValue(value.value, value.dtype, False, value.quality | failure, value.labels)
            # 无效正区间保留位置和原因，未观察区间不伪造未知覆盖。
            if not keep and retain_unknown_ranges:
                unknown.append(Interval(left, right))
            elif retain_unknown_ranges and effective_right < right:
                unknown.append(Interval(effective_right, right))
        # 保留每个原区间的槽位及顺序，未知0存储只能结合False掩码使用。
        areas.append(area)
        valid.append(keep)
    # 样本只来自半开窗口内真实更新；面积故障已在局部转换列标无效。
    for index, time in enumerate(series.times_ns):
        if start <= time < end and series.actual_value_updates[index]:
            value = values[index]
            quality |= series.diagnostics[index] | value.quality
            if value.valid:
                sample_count += 1
    # 仅紧凑诊断与冻结事实，原绑定/来源引用保持，不生成最终指标状态。
    facts = IntegralFacts(spec, actual, duration, sample_count, merge_ranges(unknown), quality,
                          series.unit, series.binding_identity, series.source_refs)
    return ReferenceIntegralTerms(tuple(areas), tuple(valid), facts)
