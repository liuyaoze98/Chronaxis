"""将完整积分事实与已换单位的数值组合成既有 CalculationResult。

输入必须是同一 IntegralReduction 交付的两项冻结结果；不创建虚假 CalculationSeries。
先校验单位、覆盖划分和计数，再复用既有 report/strict 与最低覆盖门槛分类。
本层没有积分数值核，不重复换单位，也不把输入质量中的非有限直接当整窗计算失败。
无文件副作用；分类会复制未知区间容器，调用方须事先预约元数据工作空间。
纯模型不含共同运行凭据，结构校验不能证明来源配对，实际 owner 负责保证。
"""

# 共享非数值分类规则，两个积分后端仍独立；真实 facts 自带完整身份和定位。
from .integral_terms import IntegralFacts
from .integral_sum import IntegralSumResult
from .calculations import CalculationResult, calculation_unit, make_calculation_result


def make_integral_result(facts: IntegralFacts, number: IntegralSumResult) -> CalculationResult:
    """把同一归约的数值及完整覆盖按现有政策归类。

    参数: facts 为完整真实交集事实；number 为已经换成最终单位的数值快照。
    返回: CalculationResult，保留原请求、样本、未知范围、质量及完整来源子类。
    异常: TypeError/ValueError 为模型、单位、范围或计数矛盾；分配错误传播。
    边界: 无条件积分，已知条件时长等于实际跨度；没有全 FALSE 的选择证据。
    """
    # 不以任意对象提供的同名属性冒充真实冻结结果，单位只校验而不再乘因子。
    if not isinstance(facts, IntegralFacts) or not isinstance(number, IntegralSumResult):
        raise TypeError('积分分类需要IntegralFacts和IntegralSumResult')
    unit, _ = calculation_unit(facts.spec, facts.input_unit)
    if number.unit != unit:
        raise ValueError('积分数值输出单位与原请求不一致')
    actual, request = facts.actual_window, facts.spec.window
    duration = 0 if actual is None else actual.end_ns - actual.start_ns
    if actual is not None and not request.start_ns <= actual.start_ns <= actual.end_ns <= request.end_ns:
        raise ValueError('积分实际观测越过原请求')
    # 每个有效面积对应正整数纳秒区间；真实有效更新不能多于有效面积项。
    if (not 0 <= facts.valid_sample_count <= number.valid_term_count <= facts.value_valid_duration_ns
            or (number.valid_term_count == 0) != (facts.value_valid_duration_ns == 0)):
        raise ValueError('积分面积项数、有效时长与真实样本不一致')
    # 严格检查完整划分，不能用重复未知范围或缺失区间伪造覆盖。
    cursor = 0 if actual is None else actual.start_ns
    unknown_duration = 0
    for interval in facts.value_unknown_ranges:
        if interval.start_ns < cursor:
            raise ValueError('积分未知范围需有序且不重叠')
        cursor = interval.end_ns
        unknown_duration += interval.end_ns - interval.start_ns
    if unknown_duration + facts.value_valid_duration_ns != duration:
        raise ValueError('积分有效与未知时长未完整划分实际窗口')
    # 现有分类只从第二参数取identity/refs，直接提供真实facts，不伪造全窗信号列。
    return make_calculation_result(facts.spec, facts, number.value, number.unit, actual,
                              facts.value_valid_duration_ns, duration, facts.value_valid_duration_ns,
                              unknown_duration, facts.valid_sample_count, facts.value_unknown_ranges, (),
                              facts.quality | number.quality, all_false=False,
                              calculation_failed=number.calculation_failed)
