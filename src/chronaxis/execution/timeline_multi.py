"""在同一完整组两侧推进一个数据集会话的多条件/多规则。

调用方先保留域前种子与真实下一完整组，最早边界由各条件TTL/来源EOF和对应规则deadline选择。
不同表达式对象槽全部prepare后至多一次state.apply，再全部complete并推进各自独立Detector。
迟滞的进出条件都参加该过程；防抖截止与条件TTL/EOF共同决定下一时刻。
同一编译对象被多个规则引用时只保存一份三视图；不共享数值核或改变原读写/解码调用。
固定配置与步workspace先计规则数预算，子条件/事件批各自保有预算，输出须close。
步骤失败不回滚已提交组或规则，禁止重试但保留原输出，单线程生命周期不承诺RSS。
没有全量轴/历史缓存、窗口指标或公共AnalysisRunner，固定事件绑定refs不等于全部原始行。
构造中的未安装Detector由父_uninstalled_detector持续持有；深子构造尚未返回
也按原异常上的temporal_detector_cleanup_owner接管，持续清理失败再交出真实父
multi_rule_timeline_cleanup_owner。恢复仅关闭自有步/Detector/固定配置，不关闭查询。
"""

# 冻结配置及控制协议复用，不改变参考/NumPy条件或规则数值实现。
from dataclasses import dataclass
from ..core.expression import CompiledExpression
from ..core.models import SourceRef
from ..core.temporal import TemporalRule
from ..core.stability import StabilitySpec
from ..core.start_end import StartEndSpec
from ..core.types import SignalDType
from ..results.errors import AnalysisError, ResultClosedError
from ..results.spool import _cleanup_owner
from .boundaries import RuleDeadline, _require_native_ns
from .groups import DecodedTimeGroup
from .history import _metadata_bytes
from .temporal_buffer import BudgetedTemporalDetector, _BatchRegistry
from .timeline import _require_timeline_input


@dataclass(frozen=True)
class TimelineRule:
    """声明一个已编译条件与冻结规则的关联，固定来源位置由caller提供。

    不持有运行状态，实际owner/会话/起点由多规则游标校验；多个规则可引用相同compiled对象。
    """

    rule: TemporalRule  # 当前数据集/会话中的唯一规则ID。
    compiled: CompiledExpression  # 同一实际表达式owner登记的BOOL对象。
    source_refs: tuple[SourceRef, ...] = ()  # 固定绑定定位，当前点物理行另在步骤返回。
    stability: StabilitySpec | None = None  # 可选双向防抖；不改变普通条件时间线。
    exit_compiled: CompiledExpression | None = None  # 迟滞退出或start_end结束BOOL；防抖可省略。
    start_end: StartEndSpec | None = None  # 开始/结束专用时限；与迟滞互斥。

    def __post_init__(self):
        """校验冻结输入结构，不创建Detector。

        参数: 无，读取规则、进出条件、来源与可选防抖声明。返回: None，保留原对象。
        异常: TypeError为非规则/BOOL/SourceRef tuple或非法迟滞声明。
        """
        if (not isinstance(self.rule, TemporalRule) or not isinstance(self.compiled, CompiledExpression)
                or self.compiled.root.dtype is not SignalDType.BOOL or type(self.source_refs) is not tuple
                or any(not isinstance(ref, SourceRef) for ref in self.source_refs)):
            raise TypeError('多规则声明需要冻结规则、BOOL编译对象及SourceRef tuple')
        if self.stability is not None and not isinstance(self.stability, StabilitySpec):
            raise TypeError('多规则防抖需要StabilitySpec')
        if self.start_end is not None and (not isinstance(self.start_end, StartEndSpec)
                or self.stability is not None or self.exit_compiled is None):
            raise TypeError('start_end需要独立结束条件且不能混用迟滞')
        if self.exit_compiled is not None and (self.stability is None and self.start_end is None
                or not isinstance(self.exit_compiled, CompiledExpression)
                or self.exit_compiled.root.dtype is not SignalDType.BOOL):
            raise TypeError('独立结束/退出条件需要已编译BOOL和对应状态声明')

    @property
    def expressions(self):
        """收集进出条件供共享查询。参数: 无。返回: 编译对象tuple。异常: 无。"""
        return (self.compiled,) if self.exit_compiled is None else (self.compiled, self.exit_compiled)

    @property
    def dependencies(self):
        """收集两个条件的实际依赖。参数: 无。返回: 名称tuple。异常: 无。"""
        return tuple(dict.fromkeys(name for expression in self.expressions for name in expression.dependencies))


class MultiTimelineStep:
    """拥有全部已计账子结果与少量输出视图，顺序与固定槽/规则顺序对应。

    ticks按不同条件槽，events_by_rule按规则顺序，缓存仅小typed值/事件引用。
    refs通过仍打开的自有条件读取，不把大位置元数据复制到未计账缓存。
    """

    def __init__(self, owner, cost, time_ns, consumed, conditions, batches):
        """在已申请workspace中创建输出视图，不安装链。

        参数: owner游标、cost bytes、time_ns ns、consumed是否消费组、conditions/batches局部句柄list。
        返回: None；初始化实例状态；子句柄移交到此对象。异常: 构造错误由外层关闭局部句柄。
        """
        self._owner, self._cost, self._closed = owner, cost, False
        self._time, self._consumed, self._conditions, self._batches = time_ns, consumed, conditions, batches
        self._slots, self._keys = owner._unique_slots, owner._keys
        # 元数据由上游/自有Detector计账，workspace覆盖每规则至多一个Event及小tuple视图。
        self._ticks = tuple(condition.ticks[0] for condition in conditions)
        self._events = tuple(batch.events for batch in batches)
        self._registry = self._previous = self._next = None

    def _ensure_open(self):
        """拒绝释放后读取。参数: 无。返回: None。异常: ResultClosedError。"""
        if self._closed:
            raise ResultClosedError('多规则时间步已关闭')

    @property
    def closed(self):
        """读取关闭状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    @property
    def time_ns(self):
        """读取准确时刻。参数: 无。返回: int ns。异常: ResultClosedError。"""
        self._ensure_open()
        return self._time

    @property
    def consumed_group(self):
        """读取是否消费前瞻。参数: 无。返回: bool。异常: ResultClosedError。"""
        self._ensure_open()
        return self._consumed

    @property
    def condition_slots(self):
        """读取ticks对应表达式登记槽。参数: 无。返回: int tuple。异常: ResultClosedError。"""
        self._ensure_open()
        return self._slots

    @property
    def ticks(self):
        """读取各不同条件证据。参数: 无。返回: ConditionTick tuple。异常: ResultClosedError。"""
        self._ensure_open()
        return self._ticks

    @property
    def source_refs(self):
        """读取每条件当前点完整位置。参数: 无。返回: 嵌套SourceRef tuple。异常: 关闭。"""
        self._ensure_open()
        return tuple(condition.source_refs for condition in self._conditions)

    @property
    def rule_keys(self):
        """读取事件批对应dataset/session/rule身份。参数: 无。返回: 三元tuple的tuple。异常: 关闭。"""
        self._ensure_open()
        return self._keys

    @property
    def events_by_rule(self):
        """读取各规则本次增量事件。参数: 无。返回: Event tuple的tuple。异常: 关闭。"""
        self._ensure_open()
        return self._events

    def _discard(self):
        """无扣账地脱离并清空自有视图。

        参数: 无。返回: None。异常: 脱链取消传播，finally仍关闭；owner随后只清理残留链。
        """
        try:
            self._owner._results.discard(self)
        finally:
            self._closed, self._cost = True, 0
            self._owner = self._conditions = self._batches = self._time = self._consumed = None
            self._slots = self._keys = self._ticks = self._events = None

    def close(self):
        """释放全部子结果再释放workspace，支持中途关闭取消后重试。

        参数: 无。返回: None，幂等。异常: 子结果/预算/取消传播，已扣workspace最小关闭。
        """
        if self._closed:
            return
        # list槽只在对应子结果成功关闭后清空，失败句柄仍可重试。
        for results in (self._batches, self._conditions):
            for index, result in enumerate(results):
                if result is not None:
                    result.close()
                    results[index] = None
        budget, cost = self._owner._budget, self._cost
        before, released = budget.ram_bytes, False
        try:
            budget.release_ram(cost)
            released = True
        finally:
            if released or budget.ram_bytes == before - cost:
                self._discard()


class MultiRuleTimeline:
    """单数据集会话的多规则同步游标，每真实组只提交一次。

    只保存固定槽/规则顺序、当前游标和独立检测器；不同条件在同一组前全部捕获旧点。
    不保存编译树或原组，既有表达式owner拥有树；关闭自有资源不关闭借用查询。
    _uninstalled_detector负责尚未装入_detectors的真实子实例，安装成功才清空；
    构造清理持续失败的父实例从原异常multi_rule_timeline_cleanup_owner恢复close。
    """

    def __init__(self, evidence, boundaries, rules: tuple[TimelineRule, ...]):
        """校验规则关联后先预算再建立固定槽和各独立Detector。

        参数: 两真实共享查询、同一dataset/session且rule_id唯一的非空冻结rules。
        返回: 新游标，尚未处理起点。异常: 配置/已有起点/预算/取消原错误传播；
            部分构造接管未返回Detector，持续清理失败从multi_rule_timeline_cleanup_owner恢复。
        """
        if type(rules) is not tuple or not rules or any(type(item) is not TimelineRule for item in rules):
            raise TypeError('多规则游标需要非空TimelineRule tuple')
        # 不建立容器/检测器之前逐条复用单规则既有输入契约。
        for item in rules:
            _require_timeline_input(evidence, boundaries, item.compiled, item.rule, item.source_refs)
            if item.exit_compiled is not None:
                _require_timeline_input(evidence, boundaries, item.exit_compiled, item.rule, item.source_refs)
        fixed = 65536 + 8192 * len(rules) + 16 * sum(_metadata_bytes(item.rule) for item in rules)
        self._budget, self._fixed_cost, self._closed, self._failed = evidence._budget, 0, False, False
        self._evidence = self._boundaries = self._results = self._detectors = None
        self._uninstalled_detector = None
        self._slots = self._unique_slots = self._slot_positions = self._keys = None
        self._exit_slots = None
        self._start, self._end, self._cursor = evidence._start, evidence._end, None
        self._revision = evidence._queries._holds._state.revision
        before = self._budget.ram_bytes
        try:
            self._budget.reserve_ram(fixed)
            self._fixed_cost = fixed
            self._evidence, self._boundaries, self._results = evidence, boundaries, _BatchRegistry()
            self._detectors = [None] * len(rules)
            # 本次单一dataset/session，规则ID保持原文，不造虚假deadline别名。
            if any(item.rule.dataset_id != rules[0].rule.dataset_id for item in rules):
                raise ValueError('多规则游标只能处理同一dataset')
            if len({item.rule.rule_id for item in rules}) != len(rules):
                raise ValueError('多规则游标rule_id必须唯一')
            self._slots = tuple(evidence._slots[id(item.compiled)] for item in rules)
            self._exit_slots = tuple(None if item.exit_compiled is None else evidence._slots[id(item.exit_compiled)] for item in rules)
            self._unique_slots = tuple(dict.fromkeys(self._slots + tuple(slot for slot in self._exit_slots if slot is not None)))
            self._slot_positions = {slot: index for index, slot in enumerate(self._unique_slots)}
            self._keys = tuple((item.rule.dataset_id, item.rule.session_id, item.rule.rule_id) for item in rules)
            for index, item in enumerate(rules):
                # 先存到父恢复字段再安装；失败离开构造frame也不能丢失这笔子所有权。
                self._uninstalled_detector = BudgetedTemporalDetector(self._budget, item.rule, self._start, self._end,
                    source_refs=item.source_refs, backend=evidence._backend, stability=item.stability, start_end=item.start_end)
                self._detectors[index] = self._uninstalled_detector
                self._uninstalled_detector = None
        except BaseException as exc:
            # 深子构造未返回时只有原异常上的实际恢复owner可达，不根据总余额重建子费用。
            child = getattr(exc, 'temporal_detector_cleanup_owner', None)
            if child is not None:
                self._uninstalled_detector = child
            if self._fixed_cost == 0 and self._budget.ram_bytes == before + fixed:
                self._fixed_cost = fixed
            # 父统一负责未安装与已安装子，清理取消只记notes且保留真实父恢复句柄。
            _cleanup_owner(self, exc, 'multi_rule_timeline_cleanup_owner', '多规则时间游标构造')
            raise

    @property
    def closed(self):
        """读取关闭状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    @property
    def failed(self):
        """读取禁止重试状态。参数: 无。返回: bool。异常: 无。"""
        return self._failed

    @property
    def cursor_ns(self):
        """读取已处理游标。参数: 无。返回: int ns或None。异常: ResultClosedError。"""
        if self._closed:
            raise ResultClosedError('多规则游标已关闭')
        return self._cursor

    def _ensure_active(self):
        """核对自身/上游。参数: 无。返回: None。异常: 关闭/AnalysisError。"""
        if self._closed:
            raise ResultClosedError('多规则游标已关闭')
        if self._failed:
            raise AnalysisError('多规则游标已失败，禁止重试')
        self._evidence._ensure_open()
        self._boundaries._ensure_open()

    def _construct(self, cost, time_ns, consumed, conditions, batches):
        """仅构造局部输出。参数: 已计账事实/子句柄。返回: MultiTimelineStep。异常: 分配/取消。"""
        return MultiTimelineStep(self, cost, time_ns, consumed, conditions, batches)

    def step(self, next_group: DecodedTimeGroup | None = None) -> MultiTimelineStep | None:
        """选择全局一个时刻，全部旧点捕获后只提交一次完整更新。

        参数: caller保留的下一完整组或无后续组None；种子已在构造前提交。
        返回: 须close的步，真正terminal处理后None。
        异常: 入口/版本错误前置拒绝，首workspace申请失败可重试；开始后失败禁止重试，
            不回滚已提交state或已推进规则，原输出继续可读，本次子句柄仍有清理归属。
        """
        self._ensure_active()
        state = self._evidence._queries._holds._state
        if state.revision != self._revision:
            raise ValueError('多规则游标开始后不得外部提交state')
        if next_group is not None:
            if type(next_group) is not DecodedTimeGroup:
                raise TypeError('多规则游标需要真实DecodedTimeGroup或None')
            _require_native_ns(next_group.time_ns, 'multi.next_group_ns')
            if next_group.time_ns < self._start or self._cursor is not None and next_group.time_ns <= self._cursor:
                raise ValueError('多规则前瞻须不早于域起点且晚于已处理游标')
        if self._cursor == self._end:
            return None
        cost, before = 65536 + 32768 * len(self._detectors), self._budget.ram_bytes
        reserved, started, conditions, batches, final, result = False, False, None, None, None, None
        try:
            self._budget.reserve_ram(cost)
            reserved, started = True, True
            # 先预建固定槽，子查询/事件返回后无需增长list再交接所有权。
            conditions, batches = [None] * len(self._unique_slots), [None] * len(self._detectors)
            time_ns = self._start
            if self._cursor is not None:
                time_ns = self._end
                for slot in self._unique_slots:
                    # 只向对应条件传当前各规则deadline，每次重算，不保留过期timer。
                    deadlines = tuple(RuleDeadline(detector.rule.rule_id, detector.next_deadline_ns)
                        for rule_slot, detector in zip(self._slots, self._detectors)
                        if rule_slot == slot and detector.next_deadline_ns is not None)
                    compiled = self._evidence._queries._expressions[slot]
                    boundary = self._boundaries.query_next(compiled, after_ns=self._cursor,
                        next_group_ns=None if next_group is None else next_group.time_ns, duration_deadlines=deadlines)
                    try:
                        time_ns = min(time_ns, boundary.time_ns)
                    finally:
                        boundary.close()
            # 所有不同条件取得旧点后才提交，共享条件不会重复占用预备槽。
            for index, slot in enumerate(self._unique_slots):
                compiled = self._evidence._queries._expressions[slot]
                conditions[index] = self._evidence.prepare(compiled, time_ns)
            consumed = next_group is not None and next_group.time_ns == time_ns
            if consumed:
                state.apply(next_group)
            for condition in conditions:
                condition.complete()
            for index, (slot, detector) in enumerate(zip(self._slots, self._detectors)):
                condition = conditions[self._slot_positions[slot]]
                exit_slot = self._exit_slots[index]
                if exit_slot is None:
                    batches[index] = detector.push(condition.ticks)
                else:
                    exit_condition = conditions[self._slot_positions[exit_slot]]
                    batches[index] = detector.push(condition.ticks, exit_condition.ticks)
                if time_ns == self._end:
                    final = detector.finish()
                    final.close()
                    final = None
            result = self._construct(cost, time_ns, consumed, conditions, batches)
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
                    if final is not None:
                        final.close()
                    # 原owner保有尚未成功关闭句柄，借用层由caller按层级收尾。
                    for children in (batches, conditions):
                        if children is not None:
                            for child in children:
                                if child is not None:
                                    child.close()
                finally:
                    if reserved or self._budget.ram_bytes == before + cost:
                        self._budget.release_ram(cost)
            raise

    @property
    def duration_summaries(self):
        """在关闭前提取已完成规则的小型累计快照。

        参数: 无。返回: (rule_id,start_ns,end_ns,active_ns,known_ns)的tuple。
        异常: 关闭/失败/未完成的原检测器错误；不保存全部事件或输入点。
        """
        if self._closed or self._failed:
            raise ResultClosedError('失败或关闭的时间线不能读取累计')
        result = []
        for detector in self._detectors:
            counts = detector.duration_counts
            if counts is not None:
                result.append((detector.rule.rule_id, detector.start_ns, detector.end_ns, *counts))
        return tuple(result)

    def close(self):
        """关闭自有步、未安装/已安装Detector及固定配置，保留caller查询/状态/历史。

        参数: 无。返回: None，幂等。
        异常: 子结果/预算/取消传播；子句柄成功close才清字段，未释放可重试。
            固定已释放时最小关闭，不对借用查询或上游state调用close。
        """
        if self._closed:
            return
        while self._results:
            result = next(iter(self._results))
            result.close()
            self._results.discard(result)
        # 尚未安装的深子也属于本父；成功关闭才丢字段，持续取消保留明确恢复路径。
        if self._uninstalled_detector is not None:
            self._uninstalled_detector.close()
            self._uninstalled_detector = None
        if self._detectors is not None:
            # 已安装槽逐项清空，避免一个后续子失败时重新承担已完成的子关闭责任。
            for index, detector in enumerate(self._detectors):
                if detector is not None:
                    detector.close()
                    self._detectors[index] = None
            self._detectors = None
        cost, before, released = self._fixed_cost, self._budget.ram_bytes, False
        try:
            self._budget.release_ram(cost)
            released = True
        finally:
            if released or self._budget.ram_bytes == before - cost:
                self._closed, self._fixed_cost = True, 0
                self._evidence = self._boundaries = self._results = None
                self._slots = self._unique_slots = self._slot_positions = self._keys = self._exit_slots = None
