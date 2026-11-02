"""定义请求/响应配对输入与结果，不读取日志或改变原事件。

调用者先生成A、B事件，并提供响应条件的完整时间证据；SequenceTick收齐同刻
事实，SequenceRule规定闭区间延迟。SequenceResult保存原事件、延迟和观测质量，
与现有point/activity事件表分开，公共AnalysisRunner通过SequenceRow保存其原事实。
一个规则实例只属于一个dataset/session/group；group由上游分组后显式指定，
不从车辆名或报文ID猜测。这里只用标准库，不执行配对或保持全局状态。
"""

# 冻结输入防止跨批处理时调用者改写已确认事实。
from dataclasses import dataclass
from .temporal import ConditionTick, Event
from .types import QualityFlag as Q, Truth
from .validation import require_identifier, require_text
from ..timebase.conversion import checked_add_ns, require_int64_ns


@dataclass(frozen=True)
class SequenceRule:
    """保存同一组内FIFO配对所需的身份和延迟范围。

延迟两端包含，最小值可为0；A/B由既有规则ID指定，以事件confirmed_ns参与配对。
group_id是调用者已经划分的实体/分析组，实例之间不共享候选或响应。
    """

    rule_id: str
    dataset_id: str
    session_id: str
    start_rule_id: str
    response_rule_id: str
    min_delay_ns: int
    max_delay_ns: int
    group_id: str = 'default'
    record_clock: bool = False  # True时delay按所选记录间隔累计，事件坐标仍是实际时间。

    def __post_init__(self):
        """验证规则身份与整数延迟，不猜测缺省等待时间。

        参数: 无额外参数，读取冻结字段。
        返回: None；纳秒规范为Python整数。
        异常: TypeError/ValueError/OverflowError表示非法身份、范围或类型。
        """
        if type(self.record_clock) is not bool:
            raise TypeError('record_clock需要bool')
        # 规则名称沿用简单标识符，数据集/会话/分组保留完整文本身份。
        for field in ('rule_id', 'start_rule_id', 'response_rule_id'):
            require_identifier(getattr(self, field), field)
        for field in ('dataset_id', 'session_id', 'group_id'):
            require_text(getattr(self, field), field)
        # Python精确整数比较，拒绝负延迟、倒置范围及bool时间。
        minimum = require_int64_ns(self.min_delay_ns, 'min_delay_ns')
        maximum = require_int64_ns(self.max_delay_ns, 'max_delay_ns')
        if not 0 <= minimum <= maximum:
            raise ValueError('需要0 <= min_delay_ns <= max_delay_ns')
        object.__setattr__(self, 'min_delay_ns', minimum)
        object.__setattr__(self, 'max_delay_ns', maximum)

    def check_event(self, event: Event, *, response: bool):
        """检查事件来自指定规则和当前会话，不按同名信号跨会话配对。

        参数: event为既有Event；response明确表示A或B角色。
        返回: None，保留原事件及其来源引用。
        异常: TypeError为类型不符，ValueError为数据集/会话/规则不匹配。
        """
        # Event自身已验证边界与来源归属，这里验证配对规则的范围。
        if not isinstance(event, Event) or type(response) is not bool:
            raise TypeError('需要Event及bool角色')
        expected = self.response_rule_id if response else self.start_rule_id
        if (event.rule.dataset_id, event.rule.session_id, event.rule.rule_id) != (self.dataset_id, self.session_id, expected):
            raise ValueError('顺序事件的数据集、会话或规则不匹配')


@dataclass(frozen=True)
class SequenceTick:
    """保存同一时刻全部A/B及响应是否可判断的证据。

condition.state描述此刻之后的连续区间，point_state描述此刻本身；terminal的
人工连续UNKNOWN不污染真实末点。B出现时点证据必须已知。角色内重复ID拒绝，
事件顺序不参与业务配对，检测器会按稳定ID处理同刻并列事件。
    """

    condition: ConditionTick
    starts: tuple[Event, ...] = ()
    responses: tuple[Event, ...] = ()

    def __post_init__(self):
        """验证原子时间组，避免把一半同刻事实先送入检测器。

        参数: 无额外参数；condition及两个事件tuple。
        返回: None，不排序或修改调用者对象。
        异常: TypeError/ValueError为结构、时间、重复ID或观测矛盾。
        """
        # 输入必须使用已校验的时间证据；每个事件按确认时刻参与顺序判断。
        if not isinstance(self.condition, ConditionTick):
            raise TypeError('condition需要ConditionTick')
        for events in (self.starts, self.responses):
            if not isinstance(events, tuple) or any(not isinstance(event, Event) for event in events):
                raise TypeError('同刻事件需要Event tuple')
            if any(event.confirmed_ns != self.condition.time_ns for event in events):
                raise ValueError('事件确认时间与同刻组不同')
            if len({event.event_id for event in events}) != len(events):
                raise ValueError('同一角色内事件ID重复')
        # 真实B不能同时被描述为响应条件无法判断，FALSE边沿则仍是已知证据。
        if self.responses and self.condition.point_state is Truth.UNKNOWN:
            raise ValueError('响应事件缺少已知的点观测证据')


@dataclass(frozen=True)
class SequenceResult:
    """保存一个请求的最终处理结果，原请求和响应均可追溯。

matched表示观察到合格响应；no_response表示完整等待后可确定无响应；
indeterminate表示等待中缺观测或提前结束。observation_quality保留等待期间的未知原因，
即使最后匹配成功也不隐藏先前缺失。decided_ns为响应、deadline或提前EOF时刻。
    """

    result_id: str
    rule: SequenceRule
    request: Event
    response: Event | None
    status: str
    decided_ns: int
    delay_ns: int | None
    observation_quality: Q

    def __post_init__(self):
        """拒绝不可能的结果组合，防止把未知观测组装成正常超时。

        参数: 无额外参数，读取结果字段。
        返回: None；不生成事件或写结果文件。
        异常: TypeError/ValueError/OverflowError为身份、时间或状态矛盾。
        """
        # 结果保留强类型规则/原事件，范围检查与输入相同。
        require_text(self.result_id, 'result_id')
        if not isinstance(self.rule, SequenceRule) or not isinstance(self.observation_quality, Q):
            raise TypeError('结果需要SequenceRule及QualityFlag')
        self.rule.check_event(self.request, response=False)
        decided = require_int64_ns(self.decided_ns, 'decided_ns')
        object.__setattr__(self, 'decided_ns', decided)
        deadline = None if self.rule.record_clock else checked_add_ns(self.request.confirmed_ns, self.rule.max_delay_ns)
        if decided < self.request.confirmed_ns or deadline is not None and decided > deadline:
            raise ValueError('决定时刻超出请求等待范围')
        # 匹配必须在闭区间内；非匹配没有可用延迟值，不能用0冒充。
        if self.status == 'matched':
            self.rule.check_event(self.response, response=True)
            delay = require_int64_ns(self.delay_ns, 'delay_ns')
            object.__setattr__(self, 'delay_ns', delay)
            if (decided != self.response.confirmed_ns
                    or not self.rule.record_clock and delay != decided-int(self.request.confirmed_ns)
                    or not self.rule.min_delay_ns <= delay <= self.rule.max_delay_ns):
                raise ValueError('匹配时间或延迟与规则不符')
        elif self.status in ('no_response', 'indeterminate'):
            if self.response is not None or self.delay_ns is not None:
                raise ValueError('未匹配结果不能包含响应或延迟')
            if self.status == 'no_response' and (deadline is not None and decided != deadline or self.observation_quality != Q.NONE):
                raise ValueError('no_response需要完整、已知的等待区间')
            if self.status == 'indeterminate' and self.observation_quality == Q.NONE:
                raise ValueError('indeterminate必须说明缺失观测原因')
        else:
            raise ValueError('未知顺序结果状态')
