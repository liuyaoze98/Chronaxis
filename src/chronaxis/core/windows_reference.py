"""独立用Python精确整数扩展、合并并裁剪事件窗口，输出完整片段事实。

输入已排序真实Event、WindowSpec和观测Interval，输出Segment tuple。
先按onset/点锚点扩展请求，再按明确政策分组，最后裁剪并计算覆盖。
single按真实活动间隔判断，pre重叠不扩大分组；相等deadline重入合并。
本实现不调用NumPy数值，只共享协议与元数据包装，不读写旧日志或重写事件。
输入和输出均完整保存在内存中，调用方负责资源预算。
"""

# 精确时间算术在Python整数域检查，不wrap或先转float。
from ..timebase.conversion import checked_add_ns
from .models import Interval
# 共享协议与ID/质量包装，不共享扩展、合并或覆盖算法。
from .windows import require_windows, make_segment, require_resolved_windows


def build_segments_reference(events, spec, observation, *, bounds=None, compact=False):
    """根据真实事件构造请求窗口及其实际观测交集。

    参数: events为已排序Event tuple；spec为WindowSpec；observation为真实半开范围。
    返回: Segment或compact的CompactSegment tuple；bounds为按所选周期解析的真实边界。空事件返回空tuple。
    异常: 模型、排序、归属错误传播；请求端点或跨度溢出明确拒绝。
    流程: 逐事件精确扩展，按none/重叠/相邻/真实退出间隔分组，逐组裁剪。
        不改变原Event，不增加旧writer调用，不凭EOF外的请求补观测。
    """
    # 类型和原事件事实在数值执行前验证。
    require_windows(events, spec, observation)
    require_resolved_windows(events,bounds,compact)
    groups = []
    # 当前组的请求范围与末个真实活动分开保存，pre不参与退出间隔。
    for index,event in enumerate(events):
        start = checked_add_ns(event.start_ns, -spec.pre_ns) if bounds is None else bounds[index][0]
        end_anchor = event.start_ns if event.end_ns is None else event.end_ns
        extension = spec.exit_delay_ns if spec.merge == 'exit_delay' else spec.post_ns
        end = checked_add_ns(end_anchor, extension) if bounds is None else bounds[index][1]
        left_clip,right_clip=(False,False) if bounds is None else bounds[index][2:]
        requested = Interval(start, end)
        # 每组先有独立请求，再决定是否与已有组连接。
        merge = False
        if groups:
            previous = groups[-1]
            if spec.merge == 'exit_delay':
                merge = event.start_ns <= (checked_add_ns(previous[2][-1].end_ns, spec.exit_delay_ns) if bounds is None else previous[1]) or previous[4]
            elif spec.merge == 'overlap':
                merge = start < previous[1] or start==previous[1] and (previous[4] or left_clip)
            elif spec.merge == 'overlap_and_adjacent':
                merge = start <= previous[1]
        # 合并仅扩展片段，不写回原活动边界或真实状态。
        if merge:
            groups[-1] = (min(groups[-1][0], start), max(groups[-1][1], end), groups[-1][2] + (event,),groups[-1][3] or left_clip,groups[-1][4] or right_clip)
        else:
            groups.append((requested.start_ns, requested.end_ns, (event,),left_clip,right_clip))
    results = []
    # 逐组裁剪和覆盖为独立参考算术，不调用数组内核。
    for start, end, parents,left_clip,right_clip in groups:
        requested = Interval(start, end)
        left, right = max(start, observation.start_ns), min(end, observation.end_ns)
        actual = Interval(left, right) if left <= right else None
        coverage = None if compact else (0 if actual is None else actual.duration_ns()) / requested.duration_ns()
        results.append(make_segment(spec, requested, actual, coverage, parents,compact=compact,clipped=left_clip or right_clip))
    return tuple(results)
