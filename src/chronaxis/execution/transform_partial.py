"""区分滚动输入窗口的部分性和下游查询轴的覆盖率，只标记确实参与的原值。"""

from dataclasses import replace
from ..core.types import QualityFlag as Q


def partial_in_block(rows, window, *, samples):
    """核实当前有限块是否实际使用部分值或部分选择条件。

    参数: rows 为点/值/有效截止/条件/条件截止及可选真实更新，window 为实际计算请求。
    返回: 有属于半开窗口的真实选中样本，或有选中且有效的正长度保持区间时返回 True。
    异常: 内部行损坏时传播结构错误；不把末端共享点计入两块。
    """
    for index in range(len(rows)-1):
        time,value,deadline,condition,condition_deadline=rows[index][:5]
        if not (value.partial or condition is not None and condition.partial):
            continue
        if not value.valid or condition is not None and (not condition.valid or not condition.value):
            continue
        if samples:
            if (len(rows[index])>5 and rows[index][5] and window.start_ns<=time<window.end_ns
                    and (deadline is None or time<deadline) and (condition_deadline is None or time<condition_deadline)):
                return True
        else:
            left=max(time,window.start_ns)
            right=min(rows[index+1][0],window.end_ns)
            if deadline is not None:
                right=min(right,deadline)
            if condition_deadline is not None:
                right=min(right,condition_deadline)
            if left<right:
                return True
    return False


def partial_result(result, policy):
    """保留原失败，或将有限估算按当前指标政策输出。参数: 冻结归约结果和report/strict。返回: 新结果。异常: 非结果对象。"""
    quality=result.quality|Q.ESTIMATED
    if result.value is None:
        return replace(result,quality=quality)
    strict=policy=='strict'
    return replace(result,value=None if strict else result.value,status='indeterminate' if strict else 'partial',
                   reason='partial_input',quality=quality)
