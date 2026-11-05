"""按时间组将请求与响应FIFO配对，区分未响应和无法确定。

输入为同一组完整有序的SequenceTick，输出为每次push新确定的SequenceResult。
检测器保存尚未决定的请求；返回的结果不再在内部累积。候选数有明确上限，
任何失败均封闭实例，调用者不能把部分结果宣告为完整任务成功。
响应可判断性来自既有ConditionTick的连续/点视图，TTL等边界必须由上游提供。
状态循环只依赖标准库，不冒称NumPy数组优化，不读取来源或写盘。
"""

# FIFO候选入队出队为常数时间；身份使用稳定内容，避免批次影响结果ID。
from collections import deque
from hashlib import sha256
from .binding import _identity
from .models import Interval
from .sequence import SequenceResult, SequenceRule, SequenceTick
from .temporal import ConditionTimeline, Event
from .temporal_reference import require_batch
from .types import QualityFlag as Q, Truth
from ..timebase.conversion import checked_add_ns

# 固定质量位前缀计数避免每次输入都遍历全部待响应请求。
_QUALITY_BITS = tuple(Q)


class SequenceDetector:
    """维护一个dataset/session/group/rule的等待队列与观测状态。

候选按A时间和同刻稳定ID排序。B只消费最早的合格A；截止点先匹配再超时。
输入跨批连续、批尾不当EOF；每次push立即转交已决定结果。max_pending限制
同时存在的请求数量，不是整进程RAM保证，公共AnalysisRunner的SequenceRows另行计费。
    """

    def __init__(self, rule: SequenceRule, start_ns: int, end_ns: int, *, max_pending: int = 65536):
        """建立独立状态，不从别的组或会话复制候选。

        参数: rule；start_ns/end_ns为明确会话范围；max_pending为正原生整数。
        返回: 新检测器，尚未消费任何时间组。
        异常: TypeError/ValueError/OverflowError为规则、范围或容量错误。
        """
        # 会话范围和容量在任何状态分配前校验。
        if not isinstance(rule, SequenceRule) or type(max_pending) is not int or max_pending <= 0:
            raise TypeError('需要SequenceRule及正int max_pending')
        domain = Interval(start_ns, end_ns)
        self.rule, self.start_ns, self.end_ns = rule, domain.start_ns, domain.end_ns
        self.max_pending = max_pending
        self._pending = deque()
        self._counts = [0] * len(_QUALITY_BITS)
        self._quality = Q.NONE
        self._cursor = self.start_ns
        self._last_time = None
        self._record_elapsed = 0
        self._ended = self._finished = self._failed = False

    @property
    def pending_count(self):
        """返回尚未决定的请求数量，不暴露可修改队列。

        参数: 无。
        返回: 非负整数；已结束或失败时为0。
        异常: 无主动异常。
        """
        # 不为查看数量复制全部事件。
        return len(self._pending)

    def _note(self, quality):
        """累计本段未知原因，供各请求按自己的起点查询。

        参数: quality为已校验的质量位。
        返回: None，更新固定长度计数器。
        异常: 无主动异常；只由内部协议调用。
        """
        # 每段最多检查固定9位，不按候选数做重复状态更新。
        for index, bit in enumerate(_QUALITY_BITS):
            if quality & bit:
                self._counts[index] += 1

    def _advance(self, time_ns):
        """结算上个时间组至指定时刻的连续观测，不推断额外响应。

        参数: time_ns为不早于内部游标的时间。
        返回: None；正长度未知区间计入质量，零长度不增加区间证据。
        异常: 无主动异常，外层已验证时间顺序。
        """
        # 同刻处理不伪造时长；此段状态由上个完整输入组确定。
        if time_ns > self._cursor and self._quality != Q.NONE:
            self._note(self._quality)
        self._cursor = time_ns

    def _result(self, pending, time_ns, response=None, *, early_end=False):
        """把一个请求的最终事实转换为稳定结果，保留原事件引用。

        参数: pending含请求/质量快照/deadline；time_ns为决定时刻；response可空；early_end表示提前EOF。
        返回: SequenceResult，匹配或有质量依据的未匹配结果。
        异常: 模型校验或内存异常传播，不输出伪成功。
        """
        # 只累积请求之后出现的未知位，之前的缺失不能污染新请求。
        request, snapshot, _deadline = pending
        quality = request.dependency_quality & Q.ESTIMATED
        if response is not None:
            quality |= response.dependency_quality & Q.ESTIMATED
        for bit, before, after in zip(_QUALITY_BITS, snapshot, self._counts):
            if after > before:
                quality |= bit
        if early_end:
            quality |= Q.MISSING
        status = 'matched' if response is not None else 'indeterminate' if quality != Q.NONE else 'no_response'
        delay = None if response is None else (self._record_elapsed - _deadline + self.rule.max_delay_ns
            if self.rule.record_clock else time_ns-int(request.confirmed_ns))
        # 身份包括组、规则参数及原事件；批大小/候选容量不影响业务身份。
        identity = (self.rule.dataset_id, self.rule.session_id, self.rule.group_id, self.rule.rule_id,
                    self.rule.start_rule_id, self.rule.response_rule_id, self.rule.min_delay_ns,
                    self.rule.max_delay_ns, request.event_id, int(request.confirmed_ns),
                    None if response is None else response.event_id, time_ns, status)
        if self.rule.record_clock:
            identity += ('record_clock', delay)
        result_id = sha256(_identity(identity).encode('utf-8')).hexdigest()
        return SequenceResult(result_id, self.rule, request, response, status, time_ns, delay, quality)

    def _consume(self, tick, output, advance=None):
        """按先前截止点、同刻配对、同刻超时、EOF的顺序处理一组。

        参数: tick为已检查的SequenceTick，output是本批局部输出列表。
        返回: None；更新候选和游标，不存储已经转交的结果。
        异常: MemoryError为候选上限；结果构造失败传播。
        """
        # 上游允许NumPy整数；这里规范容器，避免后续运算/身份编码继承数组标量。
        time = int(tick.condition.time_ns)
        if self.rule.record_clock:
            self._record_elapsed += advance
            self._advance(time)
        clock = self._record_elapsed if self.rule.record_clock else time
        # 无新消息也在精确deadline结算；严格小于当前时间的候选已无匹配机会。
        while self._pending and self._pending[0][2] < clock:
            deadline = self._pending[0][2]
            if not self.rule.record_clock:
                self._advance(deadline)
            output.append(self._result(self._pending.popleft(), time if self.rule.record_clock else deadline))
        self._advance(time)
        # 同刻A必须先收齐，B的输入顺序不能影响零延迟匹配。
        if len(self._pending) + len(tick.starts) > self.max_pending:
            raise MemoryError('sequence待响应请求超过max_pending')
        for event in sorted(tick.starts, key=lambda item: item.event_id):
            self._pending.append((event, tuple(self._counts), clock + self.rule.max_delay_ns
                if self.rule.record_clock else checked_add_ns(time, self.rule.max_delay_ns)))
        # 独立点UNKNOWN也不能被当作完整观察；terminal人工连续UNKNOWN不计入。
        if tick.condition.point_state is Truth.UNKNOWN:
            self._note(tick.condition.point_quality)
        for response in sorted(tick.responses, key=lambda item: item.event_id):
            # 所有请求使用同一min_delay；最老的还太新时，其余也不能匹配。
            if self._pending and (clock - self._pending[0][2] + self.rule.max_delay_ns
                    if self.rule.record_clock else time-int(self._pending[0][0].confirmed_ns)) >= self.rule.min_delay_ns:
                output.append(self._result(self._pending.popleft(), time, response))
        # 只有同刻合格B都使用过后，才决定截止点仍剩余的请求。
        while self._pending and self._pending[0][2] == clock:
            output.append(self._result(self._pending.popleft(), time))
        if tick.condition.terminal:
            # 观察先结束不能证明设备未响应；不把deadline裁短成正常超时。
            while self._pending:
                output.append(self._result(self._pending.popleft(), time, early_end=True))
            self._ended = True
        self._quality = tick.condition.quality | (tick.condition.diagnostic_quality & Q.ESTIMATED)
        self._last_time = time

    def push(self, ticks: tuple[SequenceTick, ...], *, advances=None) -> tuple[SequenceResult, ...]:
        """消费一批完整时间组并仅返回本批确定的结果。

        参数: ticks为有序tuple，可为空，首末与声明会话范围一致；advances仅规则
            record_clock模式使用，保存一个必要累计计数而不存逐点时间对照。
        返回: 新SequenceResult tuple；调用者负责消费，不在实例中重复保留。
        异常: TypeError/ValueError/OverflowError为协议错误；MemoryError为容量不足。
        副作用: 失败后释放候选并封闭实例，已转交的早先批次不能视为完整成功。
        """
        # 失败或finish后的实例不允许继续使用，避免部分状态拼成另一个任务。
        if self._failed or self._finished:
            raise ValueError('sequence实例已失败或finish')
        try:
            if not isinstance(ticks, tuple) or any(not isinstance(tick, SequenceTick) for tick in ticks):
                raise TypeError('push需要SequenceTick tuple')
            require_batch(tuple(tick.condition for tick in ticks), self.start_ns, self.end_ns, self._last_time, self._ended)
            from .temporal_clock import require_clock_advances
            require_clock_advances(tuple(t.condition for t in ticks), advances, self.rule.record_clock, self._last_time)
            # 整批先检查归属及deadline溢出，再推进；错误事件不能污染另一组。
            for tick in ticks:
                for event in tick.starts:
                    self.rule.check_event(event, response=False)
                    if not self.rule.record_clock:
                        checked_add_ns(event.confirmed_ns, self.rule.max_delay_ns)
                for event in tick.responses:
                    self.rule.check_event(event, response=True)
            output = []
            for index, tick in enumerate(ticks):
                self._consume(tick, output, None if advances is None else advances[index])
            return tuple(output)
        except Exception:
            # 超限/坏输入均使任务失败，不能跳过该批继续生产正常结果。
            self._failed = True
            self._pending.clear()
            raise

    def finish(self):
        """确认已经收到真正EOF，不制造额外响应或超时。

        参数: 无。
        返回: None；结果已经由各次push转交。
        异常: ValueError为缺EOF、失败或重复finish。
        """
        # 与批尾区分，只有terminal之后可以声明消费完成。
        if self._failed or self._finished or not self._ended:
            raise ValueError('finish需要完整terminal且实例未关闭')
        self._finished = True


def pair_sequence(rule: SequenceRule, starts: tuple[Event, ...], responses: tuple[Event, ...],
                  timeline: ConditionTimeline, *, batch_rows: int = 65536, max_pending: int = 65536):
    """将既有事件与完整响应条件轴接到顺序核心，适合可控内存分析。

    参数: rule；starts/responses为已确认事件tuple；timeline含全部条件变化、TTL及EOF；
        batch_rows为每批完整时间组数，max_pending限制等待队列。
    返回: SequenceResult tuple；只为此内存便利入口收集全部输出。
    异常: TypeError/ValueError为类型/归属/缺失事件时刻；容量与时间溢出传播。
    边界: 不补采样、解析文件或推断同步；大数据上层直接分批使用SequenceDetector。
    """
    # 完整轴定义了可判断区间，来源范围不允许继承其他会话。
    if not isinstance(timeline, ConditionTimeline) or type(batch_rows) is not int or batch_rows <= 0:
        raise TypeError('需要ConditionTimeline及正int batch_rows')
    detector = SequenceDetector(rule, timeline.start_ns, timeline.end_ns, max_pending=max_pending)
    if any(ref.session_id != rule.session_id for ref in timeline.source_refs):
        raise ValueError('响应观测来源不属于当前会话')
    groups = ({}, {})
    for events, group, response in ((starts, groups[0], False), (responses, groups[1], True)):
        if not isinstance(events, tuple):
            raise TypeError('完整事件输入需要tuple')
        seen = set()
        for event in events:
            rule.check_event(event, response=response)
            if event.event_id in seen:
                raise ValueError('同一角色内事件ID重复')
            seen.add(event.event_id)
            group.setdefault(event.confirmed_ns, []).append(event)
    # 事件时刻必须有明确条件点证据，不由本入口伪造TTL、点状态或EOF。
    times = {tick.time_ns for tick in timeline.ticks}
    if any(time not in times for group in groups for time in group):
        raise ValueError('事件确认时刻不在响应条件时间轴中')
    results = []
    for offset in range(0, len(timeline.ticks), batch_rows):
        ticks = tuple(SequenceTick(tick, tuple(groups[0].get(tick.time_ns, ())), tuple(groups[1].get(tick.time_ns, ())))
                      for tick in timeline.ticks[offset:offset+batch_rows])
        results.extend(detector.push(ticks))
    detector.finish()
    return tuple(results)
