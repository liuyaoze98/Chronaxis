"""从已经封口的规则与窗口输出构建会话级对象计数，不回读结果仓。

规则检测器本就按事件身份输出一次，完整窗口核也只发布最终片段一次。
活动使用规则事件数，片段使用窗口发布次数，因此同一活动被多个窗口引用
不会重复计数。每个被请求的窗口仅保留一个整数。
"""

from ..core.counts_v4 import OBJECT_COUNTS, classify_count
from .record_time_calculation import RecordTimeResult


def object_count_results(plan, rules, segment_counts):
    """逐项交付具有状态及质量的会话计数。

    参数: plan为最终会话计划，rules为已结束的规则owner，segment_counts为按需窗口计数。
    返回: (CalculationPlan,RecordTimeResult)迭代器，输出单位固定为1。
    异常: 尚未完成的规则或不合法引用直接失败，不能在事件流前缀上报告完成。
    """
    for request in plan.calculations:
        if request.operation not in OBJECT_COUNTS:
            continue
        # 窗口发现完整性来自产生父事件的规则；片段几何裁剪不改变已有对象身份。
        rule_id = request.count_target
        if request.operation == 'segment_count':
            rule_id = next(w.event for w in plan.windows if w.window_id == request.count_target)
        owner = next(r for r in rules if r._request.rule_id == rule_id)
        observed, known, complete, diagnostic = owner.count_evidence(plan.dataset.domain)
        number = segment_counts[request.count_target] if request.operation == 'segment_count' else owner.outcome().event_count
        value, status, reason, quality = classify_count(number, request.partial_policy, observed=observed,
                                                       determinate=known, complete=complete)
        # 有具体原因时保留原始位（例如STALE），不把每种无效都再标成MISSING。
        if reason == 'calculation_failed':
            diagnostic |= quality
        yield request, RecordTimeResult(value, '1', status, reason, diagnostic or quality)
