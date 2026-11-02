"""用独立Python遍历计算完整窗口变化量，作为数组实现的数值参考。

输入是有界ZOH片段和一个查询时刻，输出数值、三值条件和覆盖率。
首尾使用点值，窗内使用实际观测及连续片段；缺口不插值、不延长有效期。
本模块不依赖NumPy，不读文件，不保存跨调用状态或触发锁存。
"""

from math import isfinite
from .types import QualityFlag as Q, SignalDType as D, Truth
from .window_delta import WindowDeltaResult, validate_delta_input


def window_delta_reference(spec, spans, time_ns, dtype):
    """逐段求完整窗口首尾差和方向单调性。

    参数: spec配置、spans有序DeltaSpan tuple、time_ns纳秒、dtype数值类型。
    返回: WindowDeltaResult；阈值比较包含等于，UNKNOWN不伪装False。
    异常: 输入结构错误；定宽数值溢出以质量结果返回。
    """
    time_ns = validate_delta_input(spec, spans, time_ns, dtype)
    left = time_ns - spec.window_ns
    duration, quality, first, last, observations = 0, Q.NONE, None, None, []
    first_found = last_found = False
    for item in spans:
        # 左端在边界上优先用该边界真实点；内部位置沿有限ZOH。
        if item.start_ns == left or item.start_ns < left < item.end_ns:
            first_found = True
            first = item.value
            quality |= item.point_quality if item.start_ns == left else item.quality
        if item.start_ns == time_ns or item.start_ns < time_ns < item.end_ns:
            last_found = True
            last = item.value
            quality |= item.point_quality if item.start_ns == time_ns else item.quality
        lo, hi = max(left, item.start_ns), min(time_ns, item.end_ns)
        if lo < hi:
            if item.quality == Q.NONE:
                duration += hi - lo
            else:
                quality |= item.quality
        # 边界值与窗内真实观测都参与单调性，不能只比较两个端点。
        if left < item.start_ns < time_ns:
            quality |= item.point_quality
            observations.append(item.value)
    if not first_found or not last_found or duration != spec.window_ns:
        quality |= Q.MISSING
    if quality != Q.NONE:
        return WindowDeltaResult(time_ns, left, None, Truth.UNKNOWN, quality,
                                 duration, duration / spec.window_ns, None)
    values = [first, *observations, last]
    nondecreasing = all(a <= b for a, b in zip(values, values[1:]))
    nonincreasing = all(a >= b for a, b in zip(values, values[1:]))
    monotonic = (nondecreasing if spec.direction == 'rise' else nonincreasing
                 if spec.direction == 'fall' else nondecreasing or nonincreasing)
    # Python整数先算真实差值再检查定宽范围，避免溢出后拿回绕值判断阈值。
    value = first - last if spec.direction == 'fall' else last - first
    if spec.direction == 'any':
        value = abs(value)
    if dtype is D.FLOAT64 and not isfinite(value):
        quality = Q.NONFINITE
    elif dtype is D.INT64 and not -(2**63) <= value < 2**63:
        quality = Q.OVERFLOW
    elif dtype is D.UINT64 and not 0 <= value < 2**64:
        quality = Q.OVERFLOW
    if quality != Q.NONE:
        return WindowDeltaResult(time_ns, left, None, Truth.UNKNOWN, quality,
                                 duration, 1.0, monotonic)
    satisfied = value >= spec.threshold and (not spec.monotonic or monotonic)
    return WindowDeltaResult(time_ns, left, value, Truth.TRUE if satisfied else Truth.FALSE,
                             Q.NONE, duration, 1.0, monotonic)
