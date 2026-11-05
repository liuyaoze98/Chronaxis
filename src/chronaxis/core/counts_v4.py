"""定义v4计数结果及对象发现的完整性，不保存事件或原始样本。

样本计数沿用既有真实更新与选择政策，对象计数只计指定规则或窗口在本会话
最终产生的对象。计数保留整数；有证据的空集、发现不完整及没有观测分别报告。
"""

from .types import QualityFlag as Q


OBJECT_COUNTS = ('point_event_count', 'activity_count', 'segment_count')
COUNT_OPERATIONS = ('sample_count', *OBJECT_COUNTS)


def classify_count(count, policy, *, observed, determinate, complete):
    """由已知计数及范围证据决定整数结果、状态、原因与额外质量。

    参数: count为已发现对象数；policy为report或strict；后三项分别说明是否
        有观测、是否至少有部分可判定范围、是否能判定完整请求。
    返回: (value,status,reason,quality)，完全未知为None。
    异常: ValueError为计数或部分结果政策不合法。
    """
    if type(count) is not int or count < 0 or policy not in ('report', 'strict'):
        raise ValueError('计数需要非负原生整数及report/strict政策')
    if not observed:
        return None, 'indeterminate', 'no_observation', Q.MISSING
    if count > (1 << 64) - 1:
        return None, 'indeterminate', 'calculation_failed', Q.OVERFLOW
    if not determinate and not count:
        return None, 'indeterminate', 'insufficient_data', Q.MISSING
    if not complete:
        if policy == 'strict':
            return None, 'indeterminate', 'insufficient_coverage', Q.MISSING
        return count, 'partial', 'partial_coverage', Q.MISSING
    return count, 'complete', 'ok' if count else 'empty_selection', Q.NONE
