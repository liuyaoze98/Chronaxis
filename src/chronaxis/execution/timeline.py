"""逐个准确边界驱动一个真实条件规则，不建立全量分析轴。

调用方保留真实下一完整组直到consumed_group=True，域前完整组由调用方先提交作种子。
本游标直接处理domain.start，随后选择TTL、当前duration deadline、更新和来源/会话末。
每步prepare旧点→可选一次完整组提交→complete三视图→独立预算Detector，终点正式finish。
输出TimelineStep拥有条件结果和事件批，须close；固定与步workspace先申请，输出不复制
事件/位置，不保留完整组。旧已交付步在后续失败后仍可读，失败游标禁止继续。
只驱动单规则；多规则共用提交、窗口/指标和公共AnalysisRunner另接，不改旧I/O或业务算法。
使用同一单线程账本，保证新层保守计账，不代表整进程RSS或外部另存引用被强制回收。
"""

# 只复用已验时间/查询/检测/生命周期协议，两个数值后端仍各自执行。
from ..core.expression import CompiledExpression
from ..core.models import SourceRef
from ..core.temporal import TemporalRule
from ..core.types import SignalDType
from ..results.errors import AnalysisError, ResultClosedError
from .boundaries import BoundaryQueries, RuleDeadline, _require_native_ns
from .condition_evidence import ConditionEvidenceQueries
from .groups import DecodedTimeGroup
from .temporal_buffer import BudgetedTemporalDetector, _BatchRegistry


def _require_timeline_input(evidence, boundaries, compiled, rule, source_refs):
    """共用单/多规则的已有起点与实际会话校验，不推进或分配分析数组。

    参数: 两查询、登记BOOL、冻结规则及固定SourceRef tuple。
    返回: 原表达式整数登记槽；不持有编译树。
    异常: 类型/上游/会话/已处理起点错误，保留全部caller状态。
    """
    if not isinstance(evidence, ConditionEvidenceQueries) or not isinstance(boundaries, BoundaryQueries):
        raise TypeError('时间游标需要真实条件与边界查询')
    evidence._ensure_open()
    boundaries._ensure_open()
    if boundaries._expressions is not evidence._queries:
        raise ValueError('时间游标两查询必须借用同一真实表达式owner')
    # 同一个表达式owner仍可能有不同实际范围；在Detector申请前拒绝错配的终点或起点。
    if (boundaries._domain.start_ns != evidence._start
            or boundaries._domain.end_ns != evidence._end):
        raise ValueError('时间游标两查询必须使用同一实际观测范围')
    if not isinstance(compiled, CompiledExpression) or compiled.root.dtype is not SignalDType.BOOL:
        raise TypeError('时间游标需要已登记BOOL条件')
    slot = evidence._slots.get(id(compiled))
    if slot is None or evidence._queries._expressions[slot] is not compiled:
        raise ValueError('时间游标条件未登记')
    if not isinstance(rule, TemporalRule) or type(source_refs) is not tuple or any(
            not isinstance(ref, SourceRef) for ref in source_refs):
        raise TypeError('时间游标需要冻结规则和SourceRef tuple')
    # 实际执行以HoldContext会话为准，不能套用内存绑定的bindings.session字段。
    if rule.session_id != evidence._queries._holds._context.session_id or any(ref.session_id != rule.session_id for ref in source_refs):
        raise ValueError('时间游标规则/来源会话与实际绑定不一致')
    state = evidence._queries._holds._state
    if (state.last_time_ns is not None and state.last_time_ns >= evidence._start
            or evidence._pending[slot] is not None or evidence._completed_times[slot] is not None):
        raise ValueError('时间游标必须从未处理的起点开始，种子只允许域前完整组')
    return slot


class TimelineStep:
    """拥有一个时刻的条件证据和本次增量事件，三个申请各自唯一释放。

    条件和事件不复制，workspace覆盖本对象/链字段；关闭子结果后释放workspace。
    私有链仅登记本owner，后续失败不撤销先前已交付对象。
    """

    def __init__(self, owner, cost, time_ns, consumed, condition, events):
        """接收已计账子结果，不安装登记。

        参数: owner游标；cost workspace bytes；time_ns整数ns；consumed是否消费组；
            condition完成条件证据；events预算事件批。
        返回: 尚未登记的步。异常: 构造失败由step外层清理。
        """
        self._owner, self._cost, self._closed = owner, cost, False
        self._time, self._consumed, self._condition, self._events = time_ns, consumed, condition, events
        self._registry = self._previous = self._next = None

    def _ensure_open(self):
        """拒绝释放后读取。参数: 无。返回: None。异常: ResultClosedError。"""
        if self._closed:
            raise ResultClosedError('时间游标步已关闭')

    @property
    def closed(self):
        """读取资源状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    @property
    def time_ns(self):
        """读取准确时刻。参数: 无。返回: 原生int ns。异常: ResultClosedError。"""
        self._ensure_open()
        return self._time

    @property
    def consumed_group(self):
        """读取是否消费前瞻。参数: 无。返回: bool。异常: ResultClosedError。"""
        self._ensure_open()
        return self._consumed

    @property
    def tick(self):
        """借读自有一点证据。参数: 无。返回: ConditionTick。异常: ResultClosedError。"""
        self._ensure_open()
        return self._condition.ticks[0]

    @property
    def source_refs(self):
        """借读当前点完整位置。参数: 无。返回: SourceRef tuple。异常: ResultClosedError。"""
        self._ensure_open()
        return self._condition.source_refs

    @property
    def events(self):
        """借读本次增量输出。参数: 无。返回: Event tuple。异常: ResultClosedError。"""
        self._ensure_open()
        return self._events.events

    def _discard(self):
        """无扣账地解除登记与关闭引用。

        参数: 无。返回: None。异常: 脱链取消传播，finally仍关闭，owner可重试移除。
        """
        try:
            self._owner._results.discard(self)
        finally:
            self._closed, self._cost = True, 0
            self._owner = self._condition = self._events = self._time = self._consumed = None

    def close(self):
        """依次关闭两子结果与workspace，未扣账可重试。

        参数: 无。返回: None，幂等。
        异常: 子结果/预算/取消传播，已扣workspace则最小收尾且不会再次扣账。
        """
        if self._closed:
            return
        # 每个子句柄成功关闭才清空字段，关闭取消留给下次重试。
        for name in ('_events', '_condition'):
            result = getattr(self, name)
            if result is not None:
                result.close()
                setattr(self, name, None)
        budget, cost = self._owner._budget, self._cost
        before, released = budget.ram_bytes, False
        try:
            budget.release_ram(cost)
            released = True
        finally:
            if released or budget.ram_bytes == before - cost:
                self._discard()


class TemporalTimeline:
    """借用单条件查询/边界并拥有一个新检测器的严格递增游标。

    起点前可有已提交种子；开始后只能由此游标提交state，revision检测外部错位。
    不缓存输入组、全轴或事件全集；每个已交付步独立持有预算到close。
    """

    def __init__(self, evidence: ConditionEvidenceQueries, boundaries: BoundaryQueries,
                 compiled: CompiledExpression, rule: TemporalRule, *, source_refs: tuple[SourceRef, ...] = ()):
        """校验共享真实上游与单规则后创建预算检测器。

        参数: evidence/boundaries借用同一表达式owner；compiled已登记BOOL；rule冻结配置；
            source_refs调用方提供的固定规则绑定位置，不等于全部事件原始行。
        返回: 新游标，尚未处理start。异常: 类型/登记/会话/已有推进/预算/取消传播并清理自有申请。
        """
        slot = _require_timeline_input(evidence, boundaries, compiled, rule, source_refs)
        state = evidence._queries._holds._state
        # 固定元数据由已计账上游/检测器各自拥有，此申请覆盖游标与登记字段。
        self._budget, self._fixed_cost, self._closed, self._failed = evidence._budget, 0, False, False
        self._evidence = self._boundaries = self._detector = self._results = None
        self._slot, self._cursor, self._revision = slot, None, state.revision
        self._start, self._end = evidence._start, evidence._end
        before = self._budget.ram_bytes
        try:
            self._budget.reserve_ram(65536)
            self._fixed_cost = 65536
            self._evidence, self._boundaries, self._results = evidence, boundaries, _BatchRegistry()
            self._detector = BudgetedTemporalDetector(self._budget, rule, self._start, self._end,
                                                      source_refs=source_refs, backend=evidence._backend)
        except BaseException:
            if self._fixed_cost == 0 and self._budget.ram_bytes == before + 65536:
                self._fixed_cost = 65536
            self.close()
            raise

    @property
    def closed(self):
        """读取关闭状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    @property
    def failed(self):
        """读取不可重试状态。参数: 无。返回: bool。异常: 无。"""
        return self._failed

    @property
    def cursor_ns(self):
        """读取已处理游标。参数: 无。返回: int ns或起步前None。异常: ResultClosedError。"""
        if self._closed:
            raise ResultClosedError('时间游标已关闭')
        return self._cursor

    def _ensure_active(self):
        """核对自身/上游可用。参数: 无。返回: None。异常: 关闭或AnalysisError。"""
        if self._closed:
            raise ResultClosedError('时间游标已关闭')
        if self._failed:
            raise AnalysisError('时间游标已失败，禁止重试')
        self._evidence._ensure_open()
        self._boundaries._ensure_open()

    def _construct(self, cost, time_ns, consumed, condition, events):
        """仅构造局部步。参数: 已计账事实与句柄。返回: TimelineStep。异常: 分配/取消。"""
        return TimelineStep(self, cost, time_ns, consumed, condition, events)

    def step(self, next_group: DecodedTimeGroup | None = None) -> TimelineStep | None:
        """推进一个准确时刻，只有consumed_group为True时调用方才取下一完整组。

        参数: next_group真实前瞻或明确无后续组的None，域前种子已由调用方提交。
        返回: 须close的TimelineStep；已处理terminal后为None。
        异常: 入口/外部revision错位前置拒绝；workspace不足未推进可重试；开始后的错误标failed，
            不回滚state/Detector，保留以前输出且清理本次未交付申请。
        """
        self._ensure_active()
        state = self._evidence._queries._holds._state
        if state.revision != self._revision:
            raise ValueError('时间游标开始后不得外部提交state')
        if next_group is not None:
            if type(next_group) is not DecodedTimeGroup:
                raise TypeError('时间游标需要真实DecodedTimeGroup或None')
            _require_native_ns(next_group.time_ns, 'timeline.next_group_ns')
            if next_group.time_ns < self._start or self._cursor is not None and next_group.time_ns <= self._cursor:
                raise ValueError('前瞻必须位于域起点及之后且严格晚于已处理游标')
        if self._cursor == self._end:
            return None
        # 固定一点控制workspace先申请；条件、边界与事件各自另有已验预算。
        cost, before = 65536, self._budget.ram_bytes
        reserved, started, condition, events, final, result = False, False, None, None, None, None
        try:
            self._budget.reserve_ram(cost)
            reserved, started = True, True
            compiled = self._evidence._queries._expressions[self._slot]
            time_ns = self._start
            if self._cursor is not None:
                deadline = self._detector.next_deadline_ns
                deadlines = () if deadline is None else (RuleDeadline(self._detector.rule.rule_id, deadline),)
                boundary = self._boundaries.query_next(compiled, after_ns=self._cursor,
                    next_group_ns=None if next_group is None else next_group.time_ns, duration_deadlines=deadlines)
                try:
                    time_ns = boundary.time_ns
                finally:
                    boundary.close()
            # 同一完整组在旧点捕获之后只提交一次，定时器绝不制造实际更新。
            consumed = next_group is not None and next_group.time_ns == time_ns
            condition = self._evidence.prepare(compiled, time_ns)
            if consumed:
                state.apply(next_group)
            condition.complete()
            events = self._detector.push(condition.ticks)
            if time_ns == self._end:
                final = self._detector.finish()
                final.close()
                final = None
            # 外层先拿到对象再安装，取消只清理当前步，不关闭先前输出。
            result = self._construct(cost, time_ns, consumed, condition, events)
            self._results.add(result)
            self._cursor, self._revision = time_ns, state.revision
            return result
        except BaseException:
            if started:
                self._failed = True
            try:
                if result is not None:
                    result._discard()
            finally:
                try:
                    # 未交付子结果仍有原owner登记；成功关闭移除，失败保留到owner.close。
                    for child in (final, events, condition):
                        if child is not None:
                            child.close()
                finally:
                    if reserved or self._budget.ram_bytes == before + cost:
                        self._budget.release_ram(cost)
            raise

    def close(self):
        """关闭所有自有步、检测器与固定空间，保留借用查询/状态/历史。

        参数: 无。返回: None，幂等。
        异常: 子关闭/预算/取消传播，未完成可重试，固定已释放则最小关闭。
        """
        if self._closed:
            return
        while self._results:
            result = next(iter(self._results))
            result.close()
            self._results.discard(result)
        if self._detector is not None:
            self._detector.close()
            self._detector = None
        cost, before, released = self._fixed_cost, self._budget.ram_bytes, False
        try:
            self._budget.release_ram(cost)
            released = True
        finally:
            if released or self._budget.ram_bytes == before - cost:
                self._closed, self._fixed_cost = True, 0
                self._evidence = self._boundaries = self._results = None
