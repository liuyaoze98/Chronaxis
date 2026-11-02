"""组合完整条件积分事实与已换单位数值，复用既有结果政策。

只有正请求完整观测且条件全程已知FALSE才能证明空选择为0。
UNKNOWN、无实际观测和零窗口保持无法判断，部分值按report/strict政策交付。
本模块只核对模型、单位和项数，不重复面积、求和或单位转换。
输入须来自同一实际归约owner，纯结构不能证明该配对；分类需要复制有限
未知诊断容器，外层必须提前预约元数据内存。本模块不读文件或改变输入。
"""

# 共用的非数值分类不影响参考/NumPy面积及原序归约的独立性。
from .conditional_integral_terms import ConditionalIntegralFacts
from .integral_sum import IntegralSumResult
from .calculations import CalculationResult, calculation_unit, make_calculation_result


def make_conditional_integral_result(facts: ConditionalIntegralFacts, number: IntegralSumResult) -> CalculationResult:
    """把完整覆盖与数值快照分类，保留TRUE/FALSE/UNKNOWN和原来源。

    参数: facts为整窗真实事实，number为同一owner最终换单位后的数值快照。
    返回: CalculationResult；原数值质量与输入原因完整合并，FALSE零由既有政策产生。
    异常: TypeError/ValueError为类型、单位或样本/面积项数矛盾；分配错误传播。
    """
    if not isinstance(facts, ConditionalIntegralFacts) or not isinstance(number, IntegralSumResult):
        raise TypeError('条件积分分类需要ConditionalIntegralFacts和IntegralSumResult')
    if not facts.ranges_retained:
        raise ValueError('完整结果不能将未保留范围当成没有未知区间')
    unit, _ = calculation_unit(facts.spec, facts.input_unit)
    if number.unit != unit:
        raise ValueError('条件积分数值单位与原请求不一致')
    # 每项只对应正整数纳秒区间；样本不是TTL/条件单独更新，不能超过正常面积项数。
    if (not facts.valid_sample_count <= number.valid_term_count <= facts.selected_duration_ns
            or (number.valid_term_count == 0) != (facts.selected_duration_ns == 0)):
        raise ValueError('条件积分样本、正常面积项数与选择时长不一致')
    actual = facts.actual_window
    span = 0 if actual is None else actual.end_ns - actual.start_ns
    all_false = actual is not None and span > 0 and actual == facts.spec.window and facts.false_duration_ns == span
    # facts本身带身份/来源；无需伪造完整CalculationSeries或把无条件事实改成条件事实。
    return make_calculation_result(facts.spec, facts, number.value, number.unit, actual,
                              facts.value_valid_duration_ns, facts.condition_known_duration_ns,
                              facts.selected_duration_ns, facts.selected_value_unknown_duration_ns,
                              facts.valid_sample_count, facts.value_unknown_ranges, facts.condition_unknown_ranges,
                              facts.quality | number.quality, all_false=all_false,
                              calculation_failed=number.calculation_failed)
