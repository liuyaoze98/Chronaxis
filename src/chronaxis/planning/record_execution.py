"""声明新记录流当前可执行范围；静态报告与实际会话共用同一检查。

这里只检查有限配置，不读取来源，不把尚未接线的能力报为已支持。
"""


from ..core.moments import MOMENTS, SAMPLE_MOMENTS
from ..core.quantiles import SAMPLE_QUANTILES
from ..core.counts_v4 import COUNT_OPERATIONS, OBJECT_COUNTS


def is_event_duration(request):
    """识别事件总时长的静态声明，不导入执行层。参数: 指标请求。返回: bool。异常: 无。"""
    return (request.scope.startswith('event:') and request.operation=='duration' and request.signal is None
            and request.condition is not None and request.condition.root.operator=='const'
            and request.condition.root.value is True)


def record_execution_errors(plan):
    """检查会话时间指标的已接线路径。

    参数: 已编译计划。返回: 错误tuple，空值表示当前组合可执行。
    异常: 非法typed对象属性错误传播；不访问文件或修改计划。
    """
    errors = []
    # typed计划也不能让无DBC来源携带未确定的有效期；不靠读取数据猜周期。
    sources = {source.name: source for source in plan.sources}
    for signal in plan.signals:
        definition = signal.definition
        source = sources.get(definition.source)
        if definition.valid_for_ns is None and (source is None or
                source.source_type not in ('can_blf', 'can_asc', 'asc_or_blf', 'raw_can_csv')):
            errors.append(definition.name + '没有DBC周期依据；请填写本信号period或valid_for')
    if not (plan.calculations or plan.message_calculations or plan.rules or plan.outputs.can_frames or plan.outputs.signal_csv) or any((item.scope != 'session' and not item.scope.startswith(('event:','segment:'))) or item.operation not in
            ('integral', 'duration', 'min_time', 'max_time', 'time_weighted_mean','sample_minimum','sample_maximum','sample_mean','select', *COUNT_OPERATIONS, *MOMENTS, *SAMPLE_QUANTILES) and
            (plan.extensions is None or item.operation not in plan.extensions.reductions) for item in plan.calculations):
        errors.append('当前配置当前接入会话积分及时间统计')
    choices = dict(plan.intervals.resolved)
    if any(item.calculation_id not in choices for item in plan.calculations if item.operation not in ('sample_minimum','sample_maximum','sample_mean','select', *COUNT_OPERATIONS, *SAMPLE_MOMENTS, *SAMPLE_QUANTILES) and
           (plan.extensions is None or item.operation not in plan.extensions.reductions)):
        errors.append('当前配置指标缺少已解析间隔选择')
    names, value_names = set(), set()
    for request in plan.rules:
        names.update(request.dependencies)
        value_names.update(request.dependencies)
        choice=choices.get(request.rule_id)
        if choice is None and request.rule_type not in ('rising_edge','falling_edge'):
            errors.append('当前配置规则缺少已解析间隔选择')
        elif choice is not None and choice.driver is not None:
            names.add(choice.driver)
    for calculation in plan.calculations:
        for expression in (calculation.signal, calculation.condition):
            if expression is not None:
                names.update(expression.dependencies)
                value_names.update(expression.dependencies)
        choice = choices.get(calculation.calculation_id)
        if choice is not None and choice.driver is not None:
            names.add(choice.driver)
    for request in plan.sequences:
        choice=choices.get(request.sequence_id)
        if choice is None:
            errors.append('当前配置配对缺少已解析间隔选择')
        elif choice.driver is not None:
            names.add(choice.driver)
    for window in plan.windows:
        choice=choices.get(window.window_id)
        if choice is not None and choice.driver is not None:
            names.add(choice.driver)
    if plan.outputs.signal_csv is not None:
        names.update(plan.outputs.signal_csv.spec.signals)
    from .transforms import active_transforms, physical_dependencies
    transforms=active_transforms(plan,names)
    names.update(physical_dependencies(plan,names))
    names.update(choices[t.name].driver for t in transforms if choices[t.name].driver)
    needed = {item.definition.source for item in plan.signals if item.definition.name in names}
    if any(not t.physical for t in transforms):
        needed.update(sources)
    needed.update(item.source for item in plan.message_calculations)
    if plan.outputs.can_frames is not None:
        needed.add(plan.outputs.can_frames.source)
    if any(not rule.dependencies and (choices.get(rule.rule_id) is None or
           choices[rule.rule_id].driver is None) for rule in plan.rules) or any(
            calculation.scope=='session' and calculation.operation not in OBJECT_COUNTS and (choices.get(calculation.calculation_id) is None or choices[calculation.calculation_id].driver is None)
            and not any(e.dependencies for e in (calculation.signal,calculation.condition) if e is not None) for calculation in plan.calculations):
        needed.update(source.name for source in plan.sources)
    if not needed or any(item.source_type not in ('can_blf', 'can_asc', 'asc_or_blf', 'raw_can_csv', 'memory', 'signal_csv')
                              for item in plan.sources if item.name in needed):
        errors.append('当前配置需要已声明且支持的观测来源')
    return tuple(errors)
