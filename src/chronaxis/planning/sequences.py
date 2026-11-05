"""检查请求/响应点事件配对的公开声明，不读取信号或执行配对。

输入是JSON节点或冻结SequencePlan；输出为已验证的计划和联合依赖。
只引用同计划的点规则，拒绝活动、跨时钟、重名和非法延迟。观测条件直接
采用响应规则的条件，用户不需要重复配置另一份观测表达式。
"""

from dataclasses import dataclass
from .diagnostic_collection import usable_node, collect_node_error
from .checks import PlanValidationError
from .checks import array_at, duration_at, model_at, number_at, object_at, text_at
from .nodes import register_id
from ..core.validation import require_identifier
from ..core.types import TimeType
from ..timebase.conversion import require_int64_ns


@dataclass(frozen=True)
class SequencePlan:
    """保存一个FIFO配对声明；延迟包含两端，max_pending限制同时等待的请求数。"""

    sequence_id: str
    start_rule: str
    response_rule: str
    min_delay_ns: int
    max_delay_ns: int
    max_pending: int = 65536

    def __post_init__(self):
        """检查独立字段，不读取其他规则。

        参数: 无。返回: None。异常: TypeError/ValueError为名称或整数边界错误。
        """
        for name in (self.sequence_id, self.start_rule, self.response_rule):
            require_identifier(name, 'sequence节点名称')
        if any(type(value) is not int for value in (self.min_delay_ns, self.max_delay_ns, self.max_pending)):
            raise TypeError('sequence延迟和容量须为原生整数')
        if not 0 <= self.min_delay_ns <= self.max_delay_ns or self.max_pending < 1:
            raise ValueError('sequence需要0<=min_delay<=max_delay及正max_pending')
        require_int64_ns(self.min_delay_ns, 'min_delay_ns')
        require_int64_ns(self.max_delay_ns, 'max_delay_ns')


def sequence_dependencies(item, rules, bindings):
    """检查两端引用和时钟，返回两规则实际原信号依赖。

    参数: item为SequencePlan，rules为RulePlan元组，bindings为声明或运行绑定。
    返回: 去重且稳定排序的别名tuple。异常: TypeError/ValueError为不支持的引用或时钟。
    """
    if type(item) is not SequencePlan:
        raise TypeError('sequences需要SequencePlan')
    catalog = {rule.rule_id: rule for rule in rules}
    dependencies = set()
    for name in (item.start_rule, item.response_rule):
        rule = catalog.get(name)
        if rule is None or rule.rule_type not in ('rising_edge', 'falling_edge', 'start_only'):
            raise ValueError('sequence只引用本计划rising/falling/start_only点规则：' + name)
        dependencies.update(rule.condition.dependencies)
    result = tuple(sorted(dependencies))
    bindings.require_synchronized(result)
    # 常量条件没有信号依赖，但使用dataset观测轴；其隐含时钟也必须与另一端相同。
    if any(not catalog[name].condition.dependencies for name in (item.start_rule, item.response_rule)):
        declared = getattr(bindings, 'declarations', bindings)
        evidenced = {proof.source for proof in declared.synchronization}
        sources = {source.name: source for source in declared.sources}
        for name in result:
            source = sources[bindings.resolve(name).source]
            mapped = (source.timebase == declared.timebase or source.name in evidenced
                or source.timebase.time_type is TimeType.ABSOLUTE and declared.timebase.time_type is TimeType.ABSOLUTE)
            if not mapped:
                raise ValueError('常量规则与响应/请求信号没有共同dataset时钟：' + source.name)
    return result


def parse_sequences(value, rules, bindings, ids):
    """解析独立sequences数组，节点ID与规则/窗口/指标共用名称空间。

    参数: value为JSON数组，rules/bindings为已验证声明，ids为本计划名称集合。
    返回: SequencePlan tuple。异常: PlanValidationError保留非法字段或引用的位置。
    """
    result = []
    for index, raw in enumerate(array_at(value, '$.sequences')):
        path = f'$.sequences[{index}]'
        if not usable_node(path, raw):
            continue
        try:
            path = f'$.sequences[{index}]'
            raw = object_at(raw, path, ('name', 'start', 'response', 'max_delay'), ('min_delay', 'max_pending'))
            item = model_at(SequencePlan, path, register_id(raw['name'], path + '.name', ids),
                text_at(raw['start'], path + '.start', identifier=True),
                text_at(raw['response'], path + '.response', identifier=True),
                duration_at(raw.get('min_delay', '0s'), path + '.min_delay'),
                duration_at(raw['max_delay'], path + '.max_delay'),
                number_at(raw.get('max_pending', 65536), path + '.max_pending', integer=True, minimum=1))
            model_at(sequence_dependencies, path, item, rules, bindings)
            result.append(item)
        except PlanValidationError as error:
            collect_node_error(error, path, raw)
    return tuple(result)
