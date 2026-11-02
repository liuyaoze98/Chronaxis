"""为当前平坦结果确定所属表和稳定排序键，不构造额外结果包装。

输入为已计算的冻结行；输出为固定表名和纯标量tuple，不读取来源或复制数值历史。
每个表按会话、业务对象和真实顺序排序，父ID明确关联事件或片段。
"""

from .summary import SummaryCalculationRow, SummaryCoverageCalculationRow, SummaryEventRow, SummarySequenceRow, SummarySegmentRow, SummaryContributionRow, SummaryInputRow, SummarySelectionRow, SUMMARY_MODELS

ResultRow = SummaryCalculationRow | SummaryEventRow | SummarySequenceRow | SummarySegmentRow | SummaryCoverageCalculationRow | SummaryContributionRow | SummaryInputRow | SummarySelectionRow


def row_table(row: ResultRow) -> str:
    """返回行所属表名，不依赖外部对象属性反射。

    参数: row为已登记的结果行之一。返回: 当前固定表名。
    异常: TypeError为未注册类型。
    """
    # 精确类型防止子类增加未经编解码登记的字段。
    try:
        if type(row) in SUMMARY_MODELS:
            return SUMMARY_MODELS[type(row)][0]
        raise TypeError('未注册结果行类型')
    finally:
        # 返回名已先求值；原错误/TB只保位置，不替抵费后的借入行继续持有完整refs。
        row = None


def row_sort_key(row: ResultRow) -> tuple:
    """给出session、规则、起点、序号为主的确定排序键。

    参数: row为typed结果行。返回: 不含浮点值或可变对象的tuple。
    异常: TypeError为非法行；不在这里排序或重复原数据读取。
    """
    # 各表分别排序；序号为相同业务键提供稳定顺序。
    try:
        row_table(row)
        if type(row) in SUMMARY_MODELS and SUMMARY_MODELS[type(row)][0]=='selections':
            return (row.session_id,row.calculation_id,row.scope,row.parent_id or '',row.time_ns,
                    row.sequence,row.dataset_id,row.entity_id)
        if type(row) in SUMMARY_MODELS and SUMMARY_MODELS[type(row)][0]=='input_trace':
            return (row.session_id,row.source,row.original_sequence,row.sequence,row.dataset_id,row.entity_id)
        if type(row) in SUMMARY_MODELS and SUMMARY_MODELS[type(row)][0]=='contributions':
            return (row.session_id,row.calculation_id,row.evaluation_index,row.original_sequence,
                    row.sequence,row.dataset_id,row.entity_id)
        if type(row) in SUMMARY_MODELS and SUMMARY_MODELS[type(row)][0]=='calculations':
            return (row.session_id, row.calculation_id, row.scope, row.parent_id or '',
                    0, row.sequence, row.dataset_id, row.entity_id)
        if type(row) is SummarySegmentRow:
            return (row.session_id,row.window_id,row.start_ns if row.start_ns is not None else -(1<<63),
                    row.sequence,row.dataset_id,row.entity_id)
        if type(row) in (SummaryEventRow, SummarySequenceRow):
            time = row.start_ns if type(row) is SummaryEventRow else row.decided_ns
            return (row.session_id,row.rule_id,time,row.sequence,row.dataset_id,row.entity_id)
        raise TypeError('未注册结果排序类型')
    finally:
        # 正常key元组不变；取消保原TB，但本层不再借持行、事件或片段的完整实体树。
        row = time = None
