"""独立用NumPy扩展、分组和裁剪事件窗口，再恢复片段模型。

输入已排序Event tuple、WindowSpec和实际观测Interval，输出Segment tuple。
时间端点为(N,) int64纳秒列，先检查扩展溢出，再执行UFUNC；按真实活动间隔
或请求窗口重叠建立组边界，reduceat归约每组范围，数组裁剪并计算覆盖。
输出循环只打包模型/元数据，不逐事件执行参考数值；不调用参考窗口算法。
输入和数组完整物化，不读旧链、不写文件、不承诺整个AnalysisRunner的预算。
"""

# 真正数组端点、掩码与分组归约，禁止object/vectorize替代。
import numpy as np
from ..timebase.conversion import INT64_MIN, INT64_MAX, TimeOverflowError
from .models import Interval
# 只共享已校验协议与ID/诊断包装。
from .windows import require_windows, make_segment, require_resolved_windows


def build_segments_numpy(events, spec, observation, *, bounds=None, compact=False):
    """以数组计算请求与实际范围，输出保留原事件关联的片段。

    参数: events已排序真实事件；spec为WindowSpec；observation为真实Interval。
    返回: Segment或compact的CompactSegment tuple；bounds为已解析的实际边界。旧覆盖保持独立float64比值。
    异常: 配置/模型错误传播；端点或跨度溢出明确拒绝；分配失败不吞。
    流程: 扩展前校验int64上下界，批量建立连接掩码/组索引、归约、裁剪及覆盖。
        恢复Interval时校验请求跨度，再做安全整数差；不改变原事件。
    """
    # 共享的门槛没有窗口数值或归约。
    require_windows(events, spec, observation)
    require_resolved_windows(events,bounds,compact)
    if not events:
        return ()
    # 每个时间列为(N,)纳秒，point的结束锚点等于真实触发时刻。
    onsets = np.array([event.start_ns for event in events], dtype=np.int64)
    endings = np.array([event.start_ns if event.end_ns is None else event.end_ns for event in events], dtype=np.int64)
    extension = spec.exit_delay_ns if spec.merge == 'exit_delay' else spec.post_ns
    if bounds is None:
        if np.any(onsets < np.int64(INT64_MIN + spec.pre_ns)) or np.any(endings > np.int64(INT64_MAX - extension)):
            raise TimeOverflowError('窗口请求扩展超出int64纳秒')
        starts = np.subtract(onsets, np.int64(spec.pre_ns))
        ends = np.add(endings, np.int64(extension))
        left_clip=right_clip=np.zeros(len(events),dtype=bool)
    else:
        starts=np.array([item[0] for item in bounds],dtype=np.int64)
        ends=np.array([item[1] for item in bounds],dtype=np.int64)
        left_clip=np.array([item[2] for item in bounds],dtype=bool)
        right_clip=np.array([item[3] for item in bounds],dtype=bool)
    # 连接掩码(N-1,)；single比较真实onset与前活动退出deadline，不使用pre。
    if spec.merge == 'exit_delay':
        connected = (onsets[1:] <= ends[:-1]) | right_clip[:-1]
    elif spec.merge == 'overlap':
        prior=np.maximum.accumulate(ends)[:-1]
        connected = (starts[1:] < prior) | ((starts[1:] == prior) & (np.maximum.accumulate(right_clip)[:-1] | left_clip[1:]))
    elif spec.merge == 'overlap_and_adjacent':
        connected = starts[1:] <= np.maximum.accumulate(ends)[:-1]
    else:
        connected = np.zeros(len(events)-1, dtype=bool)
    # 组首索引和结束索引只依赖本次真实事件，未重新排序旧输入。
    first = np.concatenate((np.array([0], dtype=np.int64), np.flatnonzero(~connected)+1))
    stop = np.concatenate((first[1:], np.array([len(events)], dtype=np.int64)))
    group_starts = np.minimum.reduceat(starts, first)
    group_ends = np.maximum.reduceat(ends, first)
    # 模型恢复先验证合并请求跨度，之后整数求差才保证不wrap。
    requests = tuple(Interval(int(start), int(end)) for start, end in zip(group_starts, group_ends))
    left = np.maximum(group_starts, np.int64(observation.start_ns))
    right = np.minimum(group_ends, np.int64(observation.end_ns))
    observed = right >= left
    actuals = tuple(Interval(int(start), int(end)) if flag else None for start, end, flag in zip(left, right, observed))
    if compact:
        coverages=[None]*len(first)
    else:
        requested_duration = np.subtract(group_ends, group_starts)
        actual_duration = np.zeros(len(first), dtype=np.int64)
        np.subtract(right, left, out=actual_duration, where=observed)
        coverages = np.divide(actual_duration.astype(np.float64), requested_duration.astype(np.float64))
    clipped=np.logical_or.reduceat(left_clip|right_clip,first)
    # 输出循环只关联父事件和包装typed模型，全部边界/分组/覆盖已在数组完成。
    return tuple(make_segment(spec, requests[index], actuals[index], None if compact else float(coverages[index]), events[int(start):int(end)],compact=compact,clipped=bool(clipped[index]))
                 for index, (start, end) in enumerate(zip(first, stop)))
