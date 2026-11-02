"""说明一次执行为何有或没有业务结果，不保存逐条输入或重复时间记录。

执行层在原有规则推进、指标写出时累计少量状态；本模块只冻结并校验这些事实，
供清单和CLI共用。事件存在与指标是否完整分别表示，不能以completed代替业务有效性。
"""
from dataclasses import dataclass, asdict

from ..core.validation import require_identifier


@dataclass(frozen=True)
class RuleOutcome:
    """一条规则的结果概况；未知可与已生成事件并存。"""

    rule_id: str
    status: str
    event_count: int
    has_unknown: bool
    unobserved_signals: tuple[str, ...] = ()

    def __post_init__(self):
        """参数: 无。返回: None。异常: TypeError/ValueError，状态或计数不合法。"""
        require_identifier(self.rule_id, 'rule_id')
        if self.status not in ('no_observation', 'insufficient_data', 'events_found',
                              'duration_not_met', 'condition_not_met', 'no_event'):
            raise ValueError('规则结果状态无效')
        if type(self.event_count) is not int or self.event_count < 0 or type(self.has_unknown) is not bool:
            raise TypeError('规则结果需要非负事件计数和布尔未知标记')
        if type(self.unobserved_signals) is not tuple or len(set(self.unobserved_signals)) != len(self.unobserved_signals):
            raise TypeError('未观测信号需要无重复tuple')
        for name in self.unobserved_signals:
            require_identifier(name, 'unobserved_signal')
        if (self.status == 'events_found') != (self.event_count > 0):
            raise ValueError('规则结果状态与事件计数不一致')

    def to_dict(self):
        """参数: 无。返回: 小型JSON对象。异常: 无；不读取结果或输入。"""
        return asdict(self)


@dataclass(frozen=True)
class AnalysisOutcome:
    """规则状态与指标行计数；不根据事件数推断能量正确或数据完整。"""

    rules: tuple[RuleOutcome, ...] = ()
    complete: int = 0
    partial: int = 0
    indeterminate: int = 0
    no_observation: int = 0

    def __post_init__(self):
        """参数: 无。返回: None。异常: TypeError/ValueError，重复规则或错误计数。"""
        if type(self.rules) is not tuple or any(type(item) is not RuleOutcome for item in self.rules):
            raise TypeError('分析概况需要RuleOutcome tuple')
        if len({item.rule_id for item in self.rules}) != len(self.rules):
            raise ValueError('分析概况规则重复')
        for value in (self.complete, self.partial, self.indeterminate, self.no_observation):
            if type(value) is not int or value < 0:
                raise ValueError('指标概况计数需要非负整数')
        if self.no_observation > self.complete + self.partial + self.indeterminate:
            raise ValueError('无观测指标数不能超过指标总数')

    def to_dict(self):
        """参数: 无。返回: 清单/CLI同用的JSON对象。异常: 无。"""
        return dict(rules=[item.to_dict() for item in self.rules], calculations=dict(
            complete=self.complete, partial=self.partial, indeterminate=self.indeterminate,
            no_observation=self.no_observation))
