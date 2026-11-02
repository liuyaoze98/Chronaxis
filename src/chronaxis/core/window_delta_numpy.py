"""用数组掩码计算窗口覆盖、首尾位置和整窗单调性。

输入和输出与独立参考一致；实际使用searchsorted、区间裁剪、质量掩码和
相邻数组比较，不调用参考核。时间在整数域裁剪后才建立数组，避免下限回绕。
数值保留int64/uint64/float64，不将大整数转换成浮点。无文件和状态副作用。
"""

import numpy as np
from .types import QualityFlag as Q, SignalDType as D, Truth
from .window_delta import WindowDeltaResult, validate_delta_input


def window_delta_numpy(spec, spans, time_ns, dtype):
    """通过真实数组运算计算一个窗口，不复用参考算法的数值函数。

    参数: spec配置、spans有序DeltaSpan tuple、time_ns纳秒、dtype类型。
    返回: WindowDeltaResult。异常: 输入错误；数值失败记录质量。
    """
    time_ns = validate_delta_input(spec, spans, time_ns, dtype)
    left = time_ns - spec.window_ns
    starts = np.asarray([item.start_ns for item in spans], dtype=np.int64)
    ends = np.asarray([item.end_ns for item in spans], dtype=np.int64)
    flags = np.asarray([int(item.quality) for item in spans], dtype=np.uint16)
    points = np.asarray([int(item.point_quality) for item in spans], dtype=np.uint16)
    # 每个交叠长度不超过window_ns，求和不超过同一窗口，定宽时间运算安全。
    lower = np.maximum(starts, max(left, -(2**63)))
    upper = np.minimum(ends, time_ns)
    overlap = lower < upper
    lengths = np.zeros(len(spans), dtype=np.int64)
    np.subtract(upper, lower, out=lengths, where=overlap)
    duration = int(np.sum(lengths, where=flags == 0, initial=0, dtype=np.int64))
    quality = Q(int(np.bitwise_or.reduce(flags[overlap], initial=0)))
    indices = []
    for boundary in (left, time_ns):
        # left可能低于int64下限，先处理后再交给searchsorted，防隐式浮点比较。
        index = -1 if boundary < -(2**63) else int(np.searchsorted(starts, boundary, side='right')) - 1
        if index < 0 or not (starts[index] == boundary or boundary < ends[index]):
            quality |= Q.MISSING
            indices.append(None)
        else:
            indices.append(index)
            quality |= Q(int(points[index] if starts[index] == boundary else flags[index]))
    middle = (starts > max(left, -(2**63))) & (starts < time_ns)
    # 当left低于最小时间时，最小时间处仍属于窗口内观测。
    if left < -(2**63):
        middle = starts < time_ns
    quality |= Q(int(np.bitwise_or.reduce(points[middle], initial=0)))
    if duration != spec.window_ns:
        quality |= Q.MISSING
    if quality != Q.NONE:
        return WindowDeltaResult(time_ns, left, None, Truth.UNKNOWN, quality,
                                 duration, duration / spec.window_ns, None)
    first, last = (spans[index].value for index in indices)
    values = np.asarray([first, *(item.value for item, include in zip(spans, middle) if include), last],
                        dtype=dtype.value)
    nondecreasing = bool(np.all(values[1:] >= values[:-1]))
    nonincreasing = bool(np.all(values[1:] <= values[:-1]))
    monotonic = (nondecreasing if spec.direction == 'rise' else nonincreasing
                 if spec.direction == 'fall' else nondecreasing or nonincreasing)
    a, b = (values[0], values[-1]) if spec.direction == 'fall' else (values[-1], values[0])
    if spec.direction == 'any' and a < b:
        a, b = b, a
    # 减法前用范围不等式证明安全，防止numpy先回绕；无隐藏float提升。
    if dtype is D.INT64:
        aa, bb = int(a), int(b)
        if (bb > 0 and aa < -(2**63) + bb) or (bb < 0 and aa > 2**63 - 1 + bb):
            quality = Q.OVERFLOW
    elif dtype is D.UINT64 and a < b:
        quality = Q.OVERFLOW
    if quality != Q.NONE:
        return WindowDeltaResult(time_ns, left, None, Truth.UNKNOWN, quality, duration, 1.0, monotonic)
    with np.errstate(over='ignore', invalid='ignore'):
        value = np.subtract(a, b).item()
    if dtype is D.FLOAT64 and not np.isfinite(value):
        return WindowDeltaResult(time_ns, left, None, Truth.UNKNOWN, Q.NONFINITE, duration, 1.0, monotonic)
    satisfied = value >= spec.threshold and (not spec.monotonic or monotonic)
    return WindowDeltaResult(time_ns, left, value, Truth.TRUE if satisfied else Truth.FALSE,
                             Q.NONE, duration, 1.0, monotonic)
