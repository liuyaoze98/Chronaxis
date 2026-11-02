"""逐时间组检测持续条件和真实边沿，输出已经确认的活动或点事件。

输入为完整ConditionTick批次、会话范围和TemporalRule。持续候选跨批保留：
先结算此前TRUE区间的时长，再处理当前点更新和连续状态，最后处理观测结束。
确认时间记录为精确阈值到期时刻，不等待下一报文。空批次不重置状态，finish
只能在真正会话终点之后调用。默认保存全部事件；主动drain_events只转交并清空
已产生输出，不重置业务状态，此后finish返回尚未取走的事件。
这是独立的标准库参考状态机，只共享模型、身份和协议检查，不调用NumPy
检测算法。不读取来源、不持有全局状态，每个检测器对应一个规则和会话。
"""

# 模型/来源校验可共享，参考状态不导入NumPy。
from .temporal import ConditionTick, ConditionTimeline, TemporalRule, make_event
# 来源必须属于当前真实session。
from .models import Interval, SourceRef
# 三值严格比较枚举，不隐式bool化UNKNOWN。
from .types import QualityFlag as Q, Truth


def require_batch(ticks, start_ns, end_ns, previous_time_ns, ended):
    """验证完整时刻组的批次顺序/边界，不检测状态。

    参数: ticks tuple、完整domain ns、前一时刻previous_time_ns或None、ended标志。
    返回: None，空批次允许但不产生EOF。
    异常: TypeError/ValueError为错类型/回退/中途terminal/边界不符。
    """
    # 已归并条件组必须typed，不接半组原信号更新。
    if not isinstance(ticks, tuple) or any(not isinstance(item, ConditionTick) for item in ticks):
        # AtomicUpdateBuffer在上游处理跨batch同时间样本。
        raise TypeError('检测batch需tuple ConditionTick')
    # terminal之后不能继续添加非空证据。
    if ticks and ended:
        # session结束与普通batch尾严格分开。
        raise ValueError('真实terminal之后不能push')
    # 首组要覆盖明示domain起点，不猜遗漏区间。
    if ticks and previous_time_ns is None and ticks[0].time_ns != start_ns:
        # 可以显式UNKNOWN起点，不能省略范围。
        raise ValueError('首组必须为domain start')
    # 静态协议逐组检查，没有truth检测逻辑。
    for index, tick in enumerate(ticks):
        # 前一个完整时间组只用于严格单调检查。
        prior = previous_time_ns if index == 0 else ticks[index-1].time_ns
        # 不排序或合并重复条件组来掩盖调用侧错误。
        if prior is not None and tick.time_ns <= prior or not start_ns <= tick.time_ns <= end_ns:
            # 同时间完整组只能提交一次。
            raise ValueError('条件组重复/回退/超domain')
        # 会话终点必须terminal，terminal必须最后且在真实end_ns。
        if tick.terminal != (tick.time_ns == end_ns) or tick.terminal and index != len(ticks)-1:
            # 单文件/batch EOF不允许当session EOF。
            raise ValueError('terminal与真实domain end不符')


def require_detector(rule, start_ns, end_ns, refs):
    """校验规则/域/来源范围，不初始化算法状态。

    参数: rule真实TemporalRule、start_ns/end_ns ns、refs SourceRef tuple。
    返回: None，span/int64/会话一致则通过。
    异常: TypeError/ValueError/OverflowError为配置或来源冲突。
    """
    # 每次运行的独立规则不可无类型占位。
    if not isinstance(rule, TemporalRule) or not isinstance(refs, tuple):
        # 后端不能默认某个全局规则。
        raise TypeError('检测需要TemporalRule及tuple refs')
    # 先证明域跨度，数组差值后续才可安全减。
    Interval(start_ns, end_ns)
    # 真来源定位必须同当前会话。
    for ref in refs:
        # 跨会话同名来源不是同一输入。
        if not isinstance(ref, SourceRef) or ref.session_id != rule.session_id:
            # 不静默换session或清空来源。
            raise ValueError('检测来源session不一致')


class ReferenceTemporalDetector:
    """保存一个规则在一个会话内的候选活动、确认时间和边沿前态。

    candidate_start与confirmed分别保存起点和确认时刻；last_truth与last_time
    保存上一完整组，seen_known控制首次已知条件。全部状态属于当前实例，普通
    批次边界不清理；finish只在真实终点之后关闭实例。未确认候选不作为Event输出。
    events默认累计；drain_events可增量取走输出，候选、边沿前态和抑制状态不变。
    start_only额外保存blocked_until_ns；只接受真实rising_edge或明确首次初始化，
    固定窗口内触发丢弃，到期不排队或自动重触发，右端真实边沿允许再次接受。
    """

    def __init__(self, rule, start_ns, end_ns, source_refs=(), *, record_clock=False):
        """检查规则、会话范围和来源后，创建空的检测状态。

        参数:
            rule (TemporalRule): 当前规则，不继承其他实例配置。
            start_ns、end_ns (int): 完整会话起止坐标，单位为纳秒。
            source_refs (tuple[SourceRef, ...]): 当前来源引用，默认空tuple。
        返回:
            None: 候选、确认时间、边沿前态和事件集合均从初始状态开始。
        异常:
            TypeError、ValueError或OverflowError: 规则、时间范围或来源归属不合法。
        副作用:
            初始化本实例状态，没有全局缓存或文件操作。
        """
        # 校验与状态算法分开，后端只共享该协议。
        # record_clock仅接受调用方显式周期增量；实际坐标仍用于事件。
        require_detector(rule, start_ns, end_ns, source_refs)
        if type(record_clock) is not bool:
            raise TypeError('record_clock需要bool')
        self.record_clock = record_clock
        self.candidate_elapsed = self.blocked_remaining = 0
        # 当前规则/范围/来源不从全局缓存继承。
        self.rule, self.start_ns, self.end_ns, self.refs = rule, start_ns, end_ns, source_refs
        # 尚未消费任何完整时间组。
        self.last_time, self.last_truth = None, Truth.UNKNOWN
        # 新session不继承初始化/候选状态。
        self.seen_known, self.candidate_start, self.confirmed = False, None, None
        # 当前活动期间的所有依赖诊断。
        self.diagnostic = Q.NONE
        # 未主动排空时累计最终事件；输出容器与真正EOF/finish生命周期分开。
        self.events, self.ended, self.finished = [], False, False
        # 固定抑制跨普通batch保留，仅真实接受触发才更新，不排队被抑制边沿。
        self.blocked_until_ns = None

    @property
    def next_deadline_ns(self):
        """给出待确认候选的精确下一deadline，不等待新报文时间。

        参数: 无；读取候选/规则/完整domain。
        返回: int ns或None；超domain门槛永不误cast/wrap。
        异常: 无主动异常；状态局部。
        """
        # 没有候选/已确认/edge规则没有持续deadline。
        if self.record_clock or self.candidate_start is None or self.confirmed is not None:
            # 不能创建虚假计时器。
            return None
        # Python整数域先算再比较；不发生int64 wrap。
        deadline = self.candidate_start + self.rule.qualifying_duration_ns
        # 域外候选不能在EOF之后确认。
        return deadline if deadline <= self.end_ns else None

    def _consume(self, tick, advance=None):
        """结算旧TRUE区间，再处理当前更新及连续状态，最后处理会话终点。

        参数:
            tick (ConditionTick): 已经过批次协议检查的完整时间组。
        返回:
            None: 更新本实例候选、确认时间、诊断、边沿前态和最终事件。
        异常:
            TypeError、ValueError或OverflowError: 构造事件时模型检查失败，错误原样传播。
        边界:
            阈值恰好等于当前结束时间仍可确认；真实FALSE优先闭合，真实无效更新
            优先中断。单纯观测结束截断活动；会话终点不创建新持续候选。
        """
        # 记录模式只减少必要的剩余等待，不改写任何实际端点。
        if self.record_clock:
            self.blocked_remaining = max(0, self.blocked_remaining - advance)
        # 旧TRUE状态到tick之前仍属于已观测半开区间。
        if self.rule.rule_type == 'condition_duration' and self.candidate_start is not None:
            # 精确门槛在旧状态中确认，False/invalid在同刻不能抹除。
            if self.record_clock:
                self.candidate_elapsed = min(self.rule.qualifying_duration_ns, self.candidate_elapsed + advance)
                deadline = tick.time_ns if self.candidate_elapsed >= self.rule.qualifying_duration_ns else None
            else:
                deadline = self.candidate_start + self.rule.qualifying_duration_ns
            # 即使t跳到5ns仍保存3ns确认，轴构造器会插入deadline独立tick。
            if self.confirmed is None and deadline is not None and deadline <= tick.time_ns:
                # 不把确认当onset或延长区间。
                self.confirmed = deadline
            # 包含当前结束证据的诊断，但不修改真实truth。
            self.diagnostic |= tick.diagnostic_quality | tick.quality | tick.point_quality
        # 边沿仅由真实更新与已知旧状态决定。
        if self.rule.rule_type in ('rising_edge', 'falling_edge', 'start_only') and tick.actual_update:
            # 默认从UNKNOWN变为TRUE或FALSE不构成已知边沿。
            edge = self.rule.rule_type in ('rising_edge', 'start_only') and self.last_truth is Truth.FALSE and tick.point_state is Truth.TRUE or self.rule.rule_type == 'falling_edge' and self.last_truth is Truth.TRUE and tick.point_state is Truth.FALSE
            # 显式首次known TRUE允许初始化点，后续unknown恢复不重复initial。
            initial = self.rule.rule_type in ('rising_edge', 'start_only') and self.rule.emit_initial and not self.seen_known and tick.point_state is Truth.TRUE
            # 半开抑制区间右端真实边沿可触发；到期本身不制造候选或自动重触发。
            allowed = (self.rule.rule_type != 'start_only' or
                (self.blocked_remaining == 0 if self.record_clock else
                 self.blocked_until_ns is None or tick.time_ns >= self.blocked_until_ns))
            # 没有真实变化/初始化证据不输出point。
            if (edge or initial) and allowed:
                # 点start=confirmed，end=None，不增加任何持续面积。
                self.events.append(make_event(self.rule, tick.time_ns, tick.time_ns, None, 'point', Q.NONE,
                                              tick.diagnostic_quality, self.refs, trigger='initial' if initial else self.rule.rule_type))
                # 宽整数deadline可超观测域，只用于比较，不能wrap为早期时间。
                if self.rule.rule_type == 'start_only':
                    if self.record_clock:
                        self.blocked_remaining = self.rule.window_duration_ns
                    else:
                        self.blocked_until_ns = tick.time_ns + self.rule.window_duration_ns
        # condition_duration看到真实结束/连续非TRUE或真正terminal，立即结束候选。
        if self.rule.rule_type == 'condition_duration' and self.candidate_start is not None and (tick.terminal or tick.state is not Truth.TRUE):
            # 实际更新明确为FALSE时优先闭合，观测结束或有效期到期仍保留诊断。
            if tick.actual_update and tick.point_state is Truth.FALSE:
                # 真实结束证据不能降级truncated。
                status, quality = 'closed', Q.NONE
            # 实际更新导致未知优先interrupted，包括同EOF真实invalid。
            elif tick.actual_unknown:
                # 不能仅凭任一列更新误判同刻TTL因果。
                status, quality = 'interrupted', tick.point_quality
            # 纯EOF缺观测保留truncated，同刻TTL原因仍在diagnostic。
            elif tick.terminal or tick.observation_end:
                # 没有实际结束不伪造False。
                status, quality = 'truncated', tick.quality | tick.point_quality
            # 明确连续已知False同样结束，显式span可给出该证据。
            elif tick.state is Truth.FALSE:
                # known条件结束是closed。
                status, quality = 'closed', Q.NONE
            else:
                # TTL早于EOF或UNKNOWN缺口中断真实连续性。
                status, quality = 'interrupted', tick.quality
            # 不够门槛的pending不输出已确认事实。
            if self.confirmed is not None:
                # 已确认activity区间不会因post/pre片段填平缺口。
                self.events.append(make_event(self.rule, self.candidate_start, self.confirmed, tick.time_ns,
                                              status, quality, self.diagnostic, self.refs))
            # 候选彻底结束，后续TRUE从新onset开始。
            self.candidate_start, self.confirmed, self.diagnostic = None, None, Q.NONE
        # 非终点TRUE才建立持续候选，condition_duration=0也不建末点活动。
        if self.rule.rule_type == 'condition_duration' and not tick.terminal and tick.state is Truth.TRUE and self.candidate_start is None:
            # onset保留真实活动开始，不等待确认才设起点。
            self.candidate_start = tick.time_ns
            self.candidate_elapsed = 0
            # 零门槛立即确认；正门槛由精确deadline处理。
            self.confirmed = tick.time_ns if self.rule.qualifying_duration_ns == 0 else None
            # 起点与后续组按同一规则累计；连续为真时，点证据仍可能含未知原因。
            self.diagnostic = tick.diagnostic_quality | tick.quality | tick.point_quality
        # 每组point/continuous可不同，后续边沿旧状态采用连续区间truth。
        self.last_truth, self.last_time = tick.state, tick.time_ns
        # 初始化策略只允许首次known，恢复TRUE不能反复initial。
        self.seen_known |= tick.point_state is not Truth.UNKNOWN
        # 只有真实会话terminal才能结束流，不处理batch/file尾EOF。
        self.ended |= tick.terminal

    def push(self, ticks: tuple[ConditionTick, ...], *, advances=None):
        """消费完整组批次，保留候选/边沿并返回本次新最终事件。

        参数: ticks已归并tuple，允许空batch不重置。
        返回: 本批新增Event tuple，未结束pending/active不写伪事件。
        异常: ValueError为finish后/回退/边界错，typed协议异常传播。
        """
        # advances仅在记录计时模式提供；各项是本组推进量，不是另一套时间坐标。
        # finish生命周期不能隐式resume。
        if self.finished:
            # 新会话要新实例，不复用旧状态。
            raise ValueError('检测器已finish')
        # 完整组顺序校验与检测状态分开。
        require_batch(ticks, self.start_ns, self.end_ns, self.last_time, self.ended)
        from .temporal_clock import require_clock_advances
        require_clock_advances(ticks, advances, self.record_clock, self.last_time)
        # 记录已产生数量，只返回新增事实。
        previous = len(self.events)
        # 独立参考逐组状态循环，不称为NumPy数组化。
        for index, tick in enumerate(ticks):
            # 内部按先结算时长、再处理实际更新、最后处理观测结束的顺序推进。
            self._consume(tick, None if advances is None else advances[index])
        # 空batch自然返回空且不修改状态。
        return tuple(self.events[previous:])

    def drain_events(self):
        """转交当前未取走的最终事件，并清空输出容器，不推进或重置业务状态。

        参数: 无，读取本实例已经产生的events。
        返回: Event tuple；未产生输出或已经排空时为空tuple。
        异常: MemoryError为tuple构造失败，此时原输出保持未排空。
        副作用: 成功后只清空events，候选/确认/前态/初始化/抑制及生命周期均保持。
        """
        # 先成功构造冻结转交结果，再清空原列表，分配失败不会丢失已产生事件。
        events = tuple(self.events)
        self.events.clear()
        return events

    def finish(self):
        """在已处理真正terminal后关闭并返回当前尚未取走的稳定事件。

        参数: 无，不制造EOF或读取额外输入。
        返回: 尚未drain的Event tuple；未调用drain时仍返回全部事件，保持原API。
        异常: ValueError为缺terminal或重复finish。
        """
        # 未到domain end不能把batch尾当EOF收尾。
        if not self.ended or self.finished:
            # 调用者须先收齐真正末组。
            raise ValueError('finish需已消费真正terminal且不能重复')
        # 标记封闭实例，防跨任务继承状态。
        self.finished = True
        # 所有pending已在terminal处理；只返回尚未主动drain取走的稳定输出。
        return tuple(self.events)


def detect_reference(rule: TemporalRule, timeline: ConditionTimeline, *, batch_rows: int = 65536):
    """按任意合法批大小消费完整条件轴，不重置状态。

    参数: rule/timeline；batch_rows正原生int，只切组，不切原子同刻事实。
    返回: 独立参考Event tuple，ID与分割无关。
    异常: TypeError/ValueError为模型/批大小，检测协议错误传播。
    """
    # 不接受自由轴或bool批大小。
    if not isinstance(timeline, ConditionTimeline) or type(batch_rows) is not int or batch_rows <= 0:
        # 不能通过广播凑批次或丢最后行。
        raise TypeError('detect需ConditionTimeline及正int batch_rows')
    # 每次独立实例，完整源关联与域。
    detector = ReferenceTemporalDetector(rule, timeline.start_ns, timeline.end_ns, timeline.source_refs)
    # batch边界不会触发finish/reset。
    for start in range(0, len(timeline.ticks), batch_rows):
        # 只有已完整收齐的ConditionTick进入状态机。
        detector.push(timeline.ticks[start:start+batch_rows])
    # timeline模型保证唯一真正末组已消费。
    return detector.finish()
