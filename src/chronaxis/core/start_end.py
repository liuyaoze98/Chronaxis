"""从开始条件到结束条件记录活动，并区分超时与缺观测。

输入是同一会话中按时间严格递增的两组ConditionTick。开始采用已知上升沿，
可选择首次已知TRUE也启动；活动期间只等待结束条件或时限，不排队重复开始。
输出沿用正长度Event，status=timeout表示在可判断的结束条件下等到时限。
UNKNOWN/真实失效与EOF继续区分interrupted/truncated，不能凭缺数据判超时。
这是有界有序状态转换，不读取来源、不保留全量历史，也不属于数值数组核。
"""

from dataclasses import dataclass
from .temporal import make_event
from .temporal_reference import require_batch, require_detector
from .types import QualityFlag as Q, Truth as T
from ..timebase.conversion import require_int64_ns


@dataclass(frozen=True)
class StartEndSpec:
    """保存最长等待时长与首次启动策略；None明确表示不限时。"""

    timeout_ns: int | None = None  # 从开始时刻算起；正纳秒或显式不限时。
    emit_initial: bool = True  # 首次已知开始条件为TRUE时允许启动。

    def __post_init__(self):
        """拒绝零/负时限及假布尔。参数: 无。返回: None。异常: 类型/范围错误。"""
        if self.timeout_ns is not None:
            value = require_int64_ns(self.timeout_ns, 'timeout_ns')
            if value <= 0:
                raise ValueError('start_end时限必须为正或None')
            object.__setattr__(self, 'timeout_ns', value)
        if type(self.emit_initial) is not bool:
            raise TypeError('emit_initial必须为bool')


class StartEndDetector:
    """为单个规则保存至多一段活动和开始条件前态；批次边界不重置。

    活动中忽略重复开始；首次真实结束优先同刻时限。结束条件未知会终止已知
    活动，恢复后需要新的开始边沿；当前开始和结束同时成立不制造零长度活动。
    source_refs在构造时固定，输出可drain移交，未移交事件才留在实例中。
    """

    def __init__(self, rule, start_ns, end_ns, spec, source_refs=(), *, backend='reference', record_clock=False):
        """建立独立的活动状态，规则沿用condition_duration=0输出模型。

        参数: rule为TemporalRule；start_ns/end_ns为会话域；spec为StartEndSpec；
        source_refs为真实依赖引用；backend验证reference/numpy入口。
        返回: None；初始化实例状态。异常: 规则/范围/参数错误。状态算法没有数值后端分叉。
        """
        require_detector(rule, start_ns, end_ns, source_refs)
        if not isinstance(spec, StartEndSpec) or rule.rule_type != 'condition_duration' or rule.minimum_duration_ns != 0:
            raise ValueError('start_end需要StartEndSpec和duration=0输出规则')
        if backend not in ('reference', 'numpy'):
            raise ValueError('start_end后端需reference或numpy')
        if type(record_clock) is not bool:
            raise TypeError('record_clock需要bool')
        self.record_clock, self.remaining = record_clock, None
        self.rule, self.spec, self.source_refs = rule, spec, source_refs
        self.start_ns, self.end_ns = int(start_ns), int(end_ns)
        self.active_start, self.deadline = None, None
        self.previous_start, self.seen_start = T.UNKNOWN, False
        self.diagnostic = Q.NONE
        self.last_time, self.ended, self.finished = None, False, False
        self.events = []

    @property
    def next_deadline_ns(self):
        """提供域内时限供时间线推进。参数: 无。返回: int或None。异常: 无。"""
        return self.deadline if not self.record_clock and self.deadline is not None and self.deadline <= self.end_ns else None

    def _close(self, time_ns, status, quality=Q.NONE):
        """保存有正长度的活动后清理计时，绝不延长零长度点。

        参数: time_ns结束纳秒；status/quality表示实际结束原因。返回: None。
        异常: Event结构或分配错误；失败后调用方丢弃实例。
        """
        if self.active_start is not None and time_ns > self.active_start:
            self.events.append(make_event(self.rule, self.active_start, self.active_start,
                time_ns, status, quality, self.diagnostic, self.source_refs))
        self.active_start, self.deadline = None, None
        self.remaining = None
        self.diagnostic = Q.NONE

    @staticmethod
    def _unknown_status(end_condition):
        """按真实失效与观测结束区分原因。参数: end_condition证据。返回: str。异常: 无。"""
        return ('truncated' if (end_condition.terminal or end_condition.observation_end) and not end_condition.actual_unknown
                else 'interrupted')

    def _advance(self, start_condition, end_condition, advance=None):
        """推进一个完整时间组，先补精确时限，再处理实际结束和新开始。

        参数: 同刻start_condition/end_condition条件证据。返回: None。异常: 输出构造错误。
        边界: 跨过时限前未出现其它组，表示此前连续结束条件已知不成立；
        同刻未知则不能证明截止点没有end_condition，保留未知/EOF原因。
        """
        time_ns = int(start_condition.time_ns)
        if self.record_clock and self.remaining is not None:
            self.remaining = max(0, self.remaining - advance)
        if self.deadline is not None and self.deadline < time_ns:
            self._close(self.deadline, 'timeout')
        diagnostic = (start_condition.diagnostic_quality | end_condition.diagnostic_quality | start_condition.quality
                      | end_condition.quality | start_condition.point_quality | end_condition.point_quality)
        was_active = self.active_start is not None
        if was_active:
            self.diagnostic |= diagnostic
            # 只有结束条件决定已启动活动；开始信号后来失效不抹去已确认的开始。
            if end_condition.point_state is T.TRUE:
                self._close(time_ns, 'closed')
            elif end_condition.point_state is T.UNKNOWN:
                self._close(time_ns, self._unknown_status(end_condition), end_condition.point_quality)
            elif end_condition.state is T.TRUE and not end_condition.terminal:
                # 右侧连续条件已经成立时，结束边界就在当前时刻，不等下条采样。
                self._close(time_ns, 'closed')
            elif (self.remaining == 0 if self.record_clock else self.deadline is not None and self.deadline == time_ns):
                self._close(time_ns, 'timeout')
            elif end_condition.terminal or end_condition.observation_end:
                self._close(time_ns, 'truncated', end_condition.quality | Q.MISSING)
            elif end_condition.state is T.UNKNOWN:
                self._close(time_ns, 'interrupted', end_condition.quality)
        # 不在结束同刻抢占新的开始，也不把持续TRUE或UNKNOWN恢复当新上升沿。
        # 首次策略也适用于常量TRUE：有实际观测域即可，不要求常量收到信号更新。
        initial = not self.seen_start and self.spec.emit_initial
        edge = self.previous_start is T.FALSE and start_condition.actual_update
        begins = start_condition.point_state is T.TRUE and (initial or edge)
        if (not was_active and self.active_start is None and begins and not start_condition.terminal
                and end_condition.point_state is T.FALSE and end_condition.state is T.FALSE and not end_condition.observation_end):
            self.active_start = time_ns
            # Python整数避免跨int64上界回绕；域外时限不会交给时间推进器。
            self.deadline = None if self.record_clock or self.spec.timeout_ns is None else time_ns + self.spec.timeout_ns
            self.remaining = self.spec.timeout_ns
            self.diagnostic = diagnostic
        if start_condition.point_state is not T.UNKNOWN:
            self.seen_start = True
        self.previous_start = start_condition.state

    def push(self, ticks, end_ticks, *, advances=None):
        """消费同域、同刻、完整的开始/结束条件批。

        参数: ticks/end_ticks为ConditionTick tuple，可为空；advances仅record_clock模式
            提供本组周期增量，不改变开始/结束的实际时间。返回: 本批新增Event tuple；
        同时保留到drain。异常: 协议/排序/结束后推进错误；输入失败不排序或补齐。
        """
        if self.finished:
            raise ValueError('start_end检测器已finish')
        require_batch(ticks, self.start_ns, self.end_ns, self.last_time, self.ended)
        from .temporal_clock import require_clock_advances
        require_clock_advances(ticks, advances, self.record_clock, self.last_time)
        require_batch(end_ticks, self.start_ns, self.end_ns, self.last_time, self.ended)
        if len(ticks) != len(end_ticks) or any(a.time_ns != b.time_ns for a, b in zip(ticks, end_ticks)):
            raise ValueError('start_end两个条件必须在相同完整时间组求值')
        first = len(self.events)
        for index, (start, end) in enumerate(zip(ticks, end_ticks)):
            self._advance(start, end, None if advances is None else advances[index])
            self.last_time, self.ended = int(start.time_ns), start.terminal
        return tuple(self.events[first:])

    def drain_events(self):
        """转交当前输出，不清活动状态。参数: 无。返回: Event tuple。异常: 分配错误。"""
        result = tuple(self.events)
        self.events.clear()
        return result

    def finish(self):
        """仅在已收到真实末组后封闭。参数: 无。返回: 未移交Event tuple。异常: 协议错误。"""
        if self.finished or not self.ended:
            raise ValueError('start_end需要唯一finish且已有真实terminal')
        self.finished = True
        return tuple(self.events)
