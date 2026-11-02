"""保存一次阈值报警预设在实际观测范围内的时长汇总。

输入是同次迟滞状态机累计的整数纳秒，不再次读取信号或推算缺口内状态。
有未知时间时只报告已知报警累计，完整总时长为空；无观测不返回正常零。
快照只随有限预设数增长，由结果清单预算承担，重复发布不会重新计算。
"""

from dataclasses import dataclass
from math import isfinite
from ..core.models import Interval
from ..core.validation import require_identifier


@dataclass(frozen=True)
class ThresholdDurationMetadata:
    """冻结报警、已知与未知时长，完整总数只在整个观测范围已知时给出。"""

    preset_id: str  # 本次计划的预设ID。
    rule_id: str  # 实际生成的迟滞规则ID，可关联事件表。
    observed_start_ns: int | None  # 实际时钟组起点，无观测为None。
    observed_end_ns: int | None  # 实际时钟组末点，不向请求末端外推。
    known_active_duration_ns: int  # 已知报警区间的准确整数纳秒和。
    known_duration_ns: int  # 已知报警或未报警的总纳秒。

    def __post_init__(self):
        """检查固定计数和观测范围的一致性。

        参数: 无。返回: None。异常: TypeError/ValueError为身份、范围或计数矛盾。
        """
        require_identifier(self.preset_id, 'threshold.preset_id')
        require_identifier(self.rule_id, 'threshold.rule_id')
        if (self.observed_start_ns is None) != (self.observed_end_ns is None):
            raise ValueError('阈值汇总观测端点必须同时存在或同时为空')
        if self.observed_start_ns is not None:
            if type(self.observed_start_ns) is not int or type(self.observed_end_ns) is not int:
                raise TypeError('阈值汇总端点须原生整数纳秒')
            Interval(self.observed_start_ns, self.observed_end_ns)
        if any(type(value) is not int for value in (self.known_active_duration_ns, self.known_duration_ns)):
            raise TypeError('阈值汇总时长须原生整数纳秒')
        if not 0 <= self.known_active_duration_ns <= self.known_duration_ns <= self.observed_duration_ns:
            raise ValueError('报警/已知时长不得超过实际观测范围')

    @property
    def observed_duration_ns(self):
        """取得实际半开范围长度。参数: 无。返回: int纳秒。异常: 无。"""
        return 0 if self.observed_start_ns is None else self.observed_end_ns - self.observed_start_ns

    @property
    def unknown_duration_ns(self):
        """取得未确定报警状态的时长。参数: 无。返回: int纳秒。异常: 无。"""
        return self.observed_duration_ns - self.known_duration_ns

    @property
    def total_duration_ns(self):
        """完整总时长不能由未知区间推测。参数: 无。返回: int或None。异常: 无。"""
        return self.known_active_duration_ns if self.observed_duration_ns > 0 and self.unknown_duration_ns == 0 else None

    @property
    def status(self):
        """区分完整、部分、全未知和无观测。参数: 无。返回: 状态文本。异常: 无。"""
        if self.observed_duration_ns == 0:
            return 'no_observation'
        if self.known_duration_ns == 0:
            return 'indeterminate'
        return 'partial' if self.unknown_duration_ns else 'complete'

    def to_dict(self):
        """将纳秒事实及便于阅读的秒数写入清单。

        参数: 无。返回: 独立dict。异常: 无；调用方在复制前预付元数据费用。
        """
        return dict(preset_id=self.preset_id, rule_id=self.rule_id,
            observed_start_ns=self.observed_start_ns, observed_end_ns=self.observed_end_ns,
            observed_duration_ns=self.observed_duration_ns, known_duration_ns=self.known_duration_ns,
            known_active_duration_ns=self.known_active_duration_ns, unknown_duration_ns=self.unknown_duration_ns,
            total_duration_ns=self.total_duration_ns,
            total_duration_s=None if self.total_duration_ns is None else self.total_duration_ns / 10**9,
            known_active_duration_s=self.known_active_duration_ns / 10**9, status=self.status)


@dataclass(frozen=True)
class SummaryThresholdDuration:
    """新合同只保存一个累计值和单位；partial说明它只是已知部分。"""

    preset_id: str
    rule_id: str
    value: float | None
    status: str
    unit: str = 's'

    def __post_init__(self):
        """检查唯一单位和未知总量。参数: 无。返回: None。异常: 非法身份/数值/状态。"""
        require_identifier(self.preset_id,'preset_id')
        require_identifier(self.rule_id,'rule_id')
        if self.value is not None and (type(self.value) not in (int,float) or not isfinite(self.value) or self.value<0):
            raise ValueError('报警时长必须为非负有限值或未知')
        if self.unit!='s' or self.status not in ('no_observation','indeterminate','partial','complete'):
            raise ValueError('报警汇总单位或状态无效')
        if (self.status in ('no_observation','indeterminate')) != (self.value is None):
            raise ValueError('无观测/全未知为空，完整或部分累计必须有可核实值')

    def to_dict(self):
        """发布一种数值单位，不附重复ns/s或时间范围。参数: 无。返回: dict。异常: 无。"""
        return dict(preset_id=self.preset_id,rule_id=self.rule_id,unit=self.unit,
            value=self.value,status=self.status)
