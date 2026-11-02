"""将已计算的时间、状态和质量格式化为可读文字，不改变计算结果。

输入为精简结果的标量，输出为CSV单元格或清单说明。整数纳秒用整数运算
转换为十进制秒，不经过浮点，不补造日期。此模块无文件和输入读取副作用。
"""

# 系统词汇集中维护；业务名称、表达式和普通结果数值不翻译或舍入。
STATES = {
    'complete': '完整', 'partial': '部分有效', 'indeterminate': '无法确定',
    'closed': '正常结束', 'interrupted': '数据中断',
    'truncated': '观测结束，活动尚未确认结束', 'timeout': '超时结束',
    'point': '瞬时事件', 'empty': '空窗口', 'matched': '已响应',
    'no_response': '时限内未响应', 'true': '满足条件', 'unknown': '条件未知',
}
REASONS = {
    'ok': '', 'partial_coverage': '仅统计有效部分', 'partial_input': '输入仅部分有效',
    'insufficient_coverage': '有效数据不足', 'no_observation': '没有所需观测数据',
    'zero_length_window': '统计范围长度为零', 'calculation_failed': '计算失败',
    'empty_selection': '条件已知，未选中数据', 'unknown_selection': '无法确定选中哪些数据',
    'no_samples': '没有可用样本', 'no_valid_selected_data': '选中范围内没有有效数据',
    'no_evaluations': '没有参与计算的报文', 'contributed': '已计入',
    'missing_input': '缺少计算输入', 'condition_false': '不满足条件，已跳过',
    'evaluation_error': '计算失败，已跳过', 'nonfinite_input': '输入不是有限数，已跳过',
    'observed': '实际观测', 'estimated': '估计值', 'missing': '数据缺失',
    'missing_right': '缺少右侧样本', 'sufficient': '满足覆盖率要求',
}
QUALITY = ((1, '数据缺失'), (2, '数据过期'), (4, '解码失败'), (8, '非有限值'),
           (16, '数值超出允许范围'), (32, '估计值'), (64, '数值溢出'),
           (128, '精度损失'), (256, '计算定义域错误'))
OUTCOMES = {
    'no_observation': '没有所需观测数据', 'insufficient_data': '数据不足，无法确定是否发生事件',
    'events_found': '已找到满足要求的事件', 'duration_not_met': '条件曾成立，但持续时间不满足要求',
    'condition_not_met': '观测范围内条件未成立', 'no_event': '没有产生事件',
}


def seconds(value):
    """精确转换纳秒，不产生第二套时间值。

    参数: value为整数纳秒或None。返回: 最多9位小数的秒文本；None为空字符串。
    异常: TypeError为非整数输入；不接受bool或浮点纳秒。
    """
    if value is None:
        return ''
    if type(value) is not int:
        raise TypeError('可读时间需要整数纳秒')
    # 负时间使用绝对值拆分，避免Python负整数除法改变小数部分。
    whole, fraction = divmod(abs(value), 1_000_000_000)
    text = str(whole) + (('.' + f'{fraction:09d}'.rstrip('0')) if fraction else '')
    return ('-' if value < 0 else '') + text


def quality_text(value):
    """翻译已设置质量位，0不声称数据绝对正确。

    参数: value为质量整数。返回: 中文原因，以分号分隔；0为空。
    异常: 类型错误传播；未知位明确保留提示，不能静默丢失。
    """
    parts = [text for mask, text in QUALITY if int(value) & mask]
    remainder = int(value) & ~sum(mask for mask, _ in QUALITY)
    if remainder:
        parts.append(f'未识别质量标记{remainder}')
    return '；'.join(parts)


def explanation(row):
    """合并一项结果的必要原因和质量，不把普通ok当作诊断。

    参数: row为已校验平坦字段。返回: 中文说明。异常: 缺失字段错误传播。
    """
    reason = row.get('reason', '')
    parts = [REASONS.get(reason, reason), quality_text(row['quality'])]
    if row.get('coverage_status') == 'indeterminate':
        parts.append('未达到要求的覆盖率')
    return '；'.join(dict.fromkeys(part for part in parts if part))


def outcome_messages(outcome):
    """解释同次分析的轻量概况，不额外寻找未知区间。

    参数: outcome为AnalysisOutcome或None。返回: 每规则一条说明的列表。
    异常: 无；有未知与已有完整事件可以同时出现。
    """
    if outcome is None:
        return []
    messages = []
    for item in outcome.rules:
        text = f'{item.rule_id}：{OUTCOMES[item.status]}（{item.event_count}个）'
        if item.has_unknown:
            text += '；其他观测中存在条件未知，不据此否定已输出区间的计算状态'
        if item.unobserved_signals:
            text += '；未观测到：' + '、'.join(item.unobserved_signals)
        messages.append(text)
    return messages
