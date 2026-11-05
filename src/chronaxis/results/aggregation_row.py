"""保存组级值、明确总体和互斥的纳入/排除计数，版本15不改变旧结果行。"""

from dataclasses import dataclass
from math import isfinite
from ..core.types import QualityFlag as Q
from ..core.validation import require_identifier, require_text


@dataclass(frozen=True)
class SummaryAggregationRow:
    """一个实际分组的结果；配对小计是观测请求分类，参与率不是时间覆盖率。"""

    sequence: int
    dataset_id: str
    entity_id: str
    session_id: str
    aggregation_id: str
    source_kind: str
    source_id: str
    operation: str
    group_keys: tuple[str, ...]
    group_values: tuple[str, ...]
    value: int | float | None
    unit: str
    status: str
    reason: str
    candidate_count: int
    included_count: int
    definition_excluded_count: int
    quality_excluded_count: int
    included_partial_count: int
    matched_count: int
    timeout_count: int
    insufficient_observation_count: int
    pending_count: int
    discovery_complete: bool
    quality: Q

    def __post_init__(self):
        """检查组身份、有限值、数值政策和计数守恒。参数: 无。返回: None。异常: 无效协议直接拒绝。"""
        for name in ('dataset_id','entity_id','session_id','aggregation_id','source_id'):
            require_identifier(getattr(self,name),name)
        if self.source_kind not in ('calculation','sequence','rule','window'):
            raise ValueError('聚合来源类型错误')
        if self.operation not in ('count','sum','mean','variance','quantile','median'):
            raise ValueError('聚合操作错误')
        if type(self.group_keys) is not tuple or type(self.group_values) is not tuple or len(self.group_keys)!=len(self.group_values):
            raise ValueError('聚合分组键值需要等长tuple')
        if len(set(self.group_keys))!=len(self.group_keys):
            raise ValueError('聚合分组键不能重复')
        for key,value in zip(self.group_keys,self.group_values):
            require_identifier(key,'group_key')
            require_text(value,'group_value')
        counts=(self.sequence,self.candidate_count,self.included_count,self.definition_excluded_count,
                self.quality_excluded_count,self.included_partial_count,self.matched_count,self.timeout_count,
                self.insufficient_observation_count,self.pending_count)
        if any(type(x) is not int or not 0<=x<1<<64 for x in counts):
            raise ValueError('聚合计数需要 uint64 范围原生整数')
        if self.candidate_count != self.included_count+self.definition_excluded_count+self.quality_excluded_count or self.included_partial_count>self.included_count:
            raise ValueError('聚合纳入/排除数量与总体不符')
        if sum(counts[-4:]) != (self.candidate_count if self.source_kind=='sequence' else 0):
            raise ValueError('请求分类数量与总体不符')
        if type(self.discovery_complete) is not bool or not isinstance(self.quality,Q):
            raise TypeError('聚合总体完整性或质量错误')
        if self.status not in ('complete','partial','indeterminate','empty'):
            raise ValueError('聚合状态错误')
        require_text(self.unit,'unit')
        require_text(self.reason,'reason')
        if self.value is not None and (type(self.value) not in (int,float) or type(self.value) is float and not isfinite(self.value)):
            raise ValueError('聚合数值需要有限数或null')
        if self.status in ('empty','indeterminate') and self.value is not None or self.status=='complete' and self.value is None:
            raise ValueError('聚合状态与数值矛盾')
        if self.operation=='count' and (self.unit!='1' or self.value is not None and
                (type(self.value) is not int or self.value!=self.included_count)):
            raise ValueError('对象计数须为实际纳入数，单位1')


AGGREGATION_FIELDS = tuple(SummaryAggregationRow.__dataclass_fields__)
