"""以预先申请的预算批量推进独立时序检测器，并增量转交最终事件。

输入为ResourceBudget、冻结规则/会话域/固定来源引用和完整ConditionTick tuple；
可选StabilitySpec启用双向状态转换，迟滞可另传同刻退出条件，固定/批费用额外覆盖。
输出为须close的TemporalEventBatch。固定规则及完整refs元数据先计账再建立core。
每批按输入长度N申请ticks持有、NumPy数组/run掩码、最多N个Event及稳定ID构造
临时串的保守上界，随后调用一个独立core的真实批量push和正式drain_events。
返回批只保存事件tuple，不保存全量输入轴或core状态；整个本批预留转交结果，
直到close抵销，未用空间也保守保留，不声称精确RSS。旧批与后续推进相互独立。
活动批以各批对象内的双向指针登记，容器不建立哈希表，也不保留已关闭批的峰值槽位；
固定申请覆盖登记首指针，每批申请覆盖自己的链指针，稀疏关闭不留下未计账容量。
core开始前预算不足不改变检测状态，可重试；开始后任何异常或取消使owner失败，
丢弃内部core并禁止再次推进，保留此前已交付批，不声称状态事务回滚。
本组件不生成三视图/actual_unknown、不读来源、不调度deadline或发布公共AnalysisRunner；
source_refs是调用方给定的固定引用，不宣称覆盖输入每个CSV行的位置。
构造持续清理失败在原异常附temporal_detector_cleanup_owner，保留实际固定费用
和真实部分实例；不通过关闭调用方budget或上游查询弥补本次恢复责任。
"""

# 输入及输出模型共享协议，两个检测器仍使用各自独立的状态/数组算法。
from ..core.models import SourceRef
from ..core.temporal import ConditionTick, TemporalRule
from ..core.temporal_reference import ReferenceTemporalDetector
from ..core.temporal_numpy import NumpyTemporalDetector
from ..core.stability import StabilitySpec, StabilityDetector
from ..core.start_end import StartEndSpec, StartEndDetector
from ..results.budget import ResourceBudget
from ..results.errors import AnalysisError, ResultClosedError
from ..results.spool import _cleanup_owner
# 泛型冻结元数据估算保留CSVSourceRef全部字段，不使用封闭结果codec缩掉定位。
from .history import _metadata_bytes


class _BatchRegistry:
    """用已有批对象的双向指针登记活动结果，新增/移除不分配容器容量。

    只保存首指针；每个成员的前后指针由其已申请的批对象持有。长度按需遍历，
    owner推进和关闭不计算长度。移除支持新增首节点尚未完全安装时的失败清理。
    """

    def __init__(self):
        """建立固定大小登记器。参数: 无。返回: 新登记器。异常: MemoryError。"""
        # 空登记器只有首指针，不申请随历史批数增长的数组或哈希槽。
        self._first = None

    def __bool__(self):
        """检查是否有活动批。参数: 无。返回: bool。异常: 无。"""
        # 生命周期循环只需首指针，避免关闭时遍历计数或复制集合。
        return self._first is not None

    def __len__(self):
        """读取活动批数量。参数: 无。返回: int。异常: 内部链损坏。

        该诊断接口按需遍历，不建立随批数增长的辅助计数容器。
        """
        # 在已有链上使用常量空间计数；正常推进不调用此诊断接口。
        count, result = 0, self._first
        while result is not None:
            count += 1
            result = result._next
        # 计数不缓存，批关闭后没有高峰数量对应的遗留容量。
        return count

    def __iter__(self):
        """遍历当前活动批。参数: 无。返回: 常量空间迭代器。异常: 内部链损坏。"""
        # 先保存下一节点，允许调用方在当前节点交付后关闭当前批。
        result = self._first
        while result is not None:
            following = result._next
            yield result
            result = following

    def add(self, result):
        """把新批安装到首端，不分配额外节点。

        参数: result尚未登记、具有_registry/_previous/_next指针的预算结果。
            用于时序事件批或内部预备条件结果，各自owner负责释放金额。
        返回: None。
        异常: ValueError为重复/跨登记器安装；取消由owner撤销部分安装。
        """
        # 每批只有一个登记归属，不把重复安装解释为创建第二份预算所有权。
        if result._registry is not None:
            raise ValueError('时序事件批已登记')
        # 先保留旧首端与归属，外层异常处理能识别并撤销任一部分安装步骤。
        result._previous, result._next, result._registry = None, self._first, self
        if self._first is not None:
            self._first._previous = result
        self._first = result

    def discard(self, result):
        """移除一个完整或部分安装的批，保留其他活动批。

        参数: result待移除批。返回: None；不属于本登记器时无副作用。
        异常: 内部链损坏；不抵销批预算，由其生命周期边界负责释放。
        """
        # 成员标记只用于本容器，避免失败清理影响先前已交付批的归属。
        if result._registry is not self:
            return
        # 每个邻接关系先确认实际指向本批，兼容新增首节点中途取消后的撤销。
        previous, following = result._previous, result._next
        if previous is not None and previous._next is result:
            previous._next = following
        if following is not None and following._previous is result:
            following._previous = previous
        if self._first is result:
            self._first = following
        # 脱链后不持有旧批或其邻接对象，关闭不会留下高峰容器容量。
        result._previous = result._next = result._registry = None


class TemporalEventBatch:
    """持有本批最终事件及独立申请，owner失败后仍可读至本批或owner关闭。

    events为冻结tuple，事件模型不随后续core推进改变。外部另存已取得的事件
    超过close时刻须自行负责引用，不把释放申请解释为强制销毁外部对象。
    """

    def __init__(self, owner, cost, events):
        """在完整预留中转交事件，不复制来源元数据或保留输入ticks。

        参数: owner自有检测owner；cost本批已有申请；events已排空的Event tuple。
        返回: 新批结果，随后由owner登记。
        异常: MemoryError为构造失败，由owner清理本次申请并进入failed。
        """
        # 原事件及固定引用保持只读模型，预算归结果直到close。
        self._owner, self._cost, self._events, self._closed = owner, cost, events, False
        # 登记节点复用本批对象；字段随本批预留持有，不另外分配哈希表槽位。
        self._previous = self._next = self._registry = None

    @property
    def closed(self):
        """读取批关闭状态。参数: 无。返回: bool。异常: 无。"""
        # 关闭标志即使事件引用已清理也可读取，支持幂等收尾。
        return self._closed

    @property
    def events(self):
        """读取只读最终事件。参数: 无。返回: Event tuple。异常: ResultClosedError。"""
        # 关闭后的事件已不由本批预算持有，拒绝继续借用其私有引用。
        if self._closed:
            raise ResultClosedError('时序事件批已关闭')
        # 返回冻结tuple，后续core推进或其它批关闭不会改写本批事件。
        return self._events

    def close(self):
        """抵销一次完整本批申请，不修改其它批或检测业务状态。

        参数: 无。返回: None，重复关闭安全。
        异常: 内部账本不一致或取消；若已抵销则完成最小脱链/关闭后传播，
            尚未抵销时保持开放，可再次关闭。共享账本遵守其单线程契约。
        """
        # 第二次关闭不能再次抵销同一批申请。
        if self._closed:
            return
        # 单线程账本快照区分release调用入口取消和完成抵销后的返回取消。
        owner, cost = self._owner, self._cost
        budget, before = owner._budget, owner._budget.ram_bytes
        try:
            # 抵销和本地归零处于同一受保护块，后续脱链取消不会重复释放。
            budget.release_ram(cost)
            self._cost = 0
            owner._results.discard(self)
            self._closed = True
            self._events = self._owner = None
            self._previous = self._next = self._registry = None
        except BaseException:
            # 已抵销时完成最小收尾；未抵销时不删除仍有申请的登记批。
            if self._cost == 0 or budget.ram_bytes == before - cost:
                self._cost = 0
                owner._results.discard(self)
                self._closed = True
                self._events = self._owner = None
                self._previous = self._next = self._registry = None
            # 取消仍交还调用方，资源状态不会由吞异常伪装为正常调用。
            raise


class BudgetedTemporalDetector:
    """维护一个私有core、固定申请及活动事件批，预算外不累计旧events。

    规则和domain只读，候选/run/前态跨普通批保存。每次push后正式drain输出，
    已交付事件由批独立计账；调用方不直接操作core。failed与closed分别表示
    推进失败和资源关闭，失败丢弃core但不隐式关闭先前批。
    """

    def __init__(self, budget: ResourceBudget, rule: TemporalRule, start_ns: int, end_ns: int,
                 source_refs: tuple[SourceRef, ...] = (), backend: str = 'numpy', *, stability=None, start_end=None, record_clock=False):
        """先申请完整规则/来源固定空间，再创建新的独立后端检测器。

        参数: budget共享账本；rule冻结规则；start_ns/end_ns整数ns域；source_refs固定引用；
            backend为reference或numpy；stability或start_end分别选择防抖/迟滞或开始结束，互斥；
            record_clock=True时等待只由push的advances推进，默认仍按实际时间。
        返回: 新owner，未消费任何tick。
        异常: 类型/后端/规则/域/来源/预算/构造原错误；本次固定申请清理持续失败时，
            原异常附temporal_detector_cleanup_owner供恢复close，不改变调用方预算所有权。
        """
        # 固定申请之前只接受既有冻结协议，拒绝用任意对象驱动元数据遍历。
        if (not isinstance(budget, ResourceBudget) or not isinstance(rule, TemporalRule)
                or type(source_refs) is not tuple or any(not isinstance(ref, SourceRef) for ref in source_refs)):
            raise TypeError('预算时序检测需要ResourceBudget/TemporalRule及SourceRef tuple')
        # 后端选择显式且稳定；无静默回退或模型外数值实现。
        if type(backend) is not str or backend not in ('reference', 'numpy'):
            raise ValueError('时序后端必须为reference或numpy')
        if stability is not None and not isinstance(stability, StabilitySpec):
            raise TypeError('防抖参数需要StabilitySpec')
        if start_end is not None and (not isinstance(start_end, StartEndSpec) or stability is not None):
            raise TypeError('开始结束参数需要独立StartEndSpec，不能混用迟滞')
        # 估算只遍历调用方已提供的冻结模型，不建立事件集合、数组或core状态。
        metadata = _metadata_bytes((rule, source_refs))
        fixed = 32768 + 16 * _metadata_bytes((rule, start_ns, end_ns, source_refs, backend))
        if stability is not None:
            fixed += 32768 + 16 * _metadata_bytes(stability)
        if start_end is not None:
            fixed += 32768 + 16 * _metadata_bytes(start_end)
        # 先建立可幂等清理的空owner壳，尚不创建core或登记器。
        self._budget, self._fixed_cost, self._closed, self._failed = budget, 0, False, False
        self._rule = self._start = self._end = self._refs = self._detector = self._results = None
        self._event_metadata_cost = 0
        self._failed_workspace_cost = 0
        # 申请前快照覆盖reserve返回取消，避免已扣账但owner尚未记录申请的窗口。
        before = budget.ram_bytes
        try:
            # 固定申请成功后才允许建立登记器和两个独立后端中的一个。
            budget.reserve_ram(fixed)
            self._fixed_cost = fixed
            self._rule, self._start, self._end, self._refs = rule, start_ns, end_ns, source_refs
            self._event_metadata_cost = metadata
            self._results = _BatchRegistry()
            # 实际构造器继续检查域跨度/会话归属；参考不调用数组核，数组不回退参考。
            detector_type = ReferenceTemporalDetector if backend == 'reference' else NumpyTemporalDetector
            if start_end is not None:
                self._detector = StartEndDetector(rule, start_ns, end_ns, start_end, source_refs, backend=backend, record_clock=record_clock)
            elif stability is not None:
                self._detector = StabilityDetector(rule, start_ns, end_ns, stability, source_refs, backend=backend, record_clock=record_clock)
            else:
                self._detector = detector_type(rule, start_ns, end_ns, source_refs, record_clock=record_clock)
        except BaseException as exc:
            # reserve已经完成但返回时取消，仍将该申请纳入最小关闭收尾。
            if self._fixed_cost == 0 and budget.ram_bytes == before + fixed:
                self._fixed_cost = fixed
            # 部分构造通过同一关闭边界抵销；清理失败不能替换原错或丢失未交付owner。
            _cleanup_owner(self, exc, 'temporal_detector_cleanup_owner', '预算时序检测器构造')
            raise

    def _ensure_open(self):
        """拒绝关闭后访问。参数: 无。返回: None。异常: ResultClosedError。"""
        # 资源已归还后不能继续使用私有规则或检测状态。
        if self._closed:
            raise ResultClosedError('预算时序检测器已关闭')

    def _ensure_active(self):
        """拒绝关闭或失败后继续推进/读取deadline，不尝试恢复部分core状态。

        参数: 无。返回: None。异常: ResultClosedError或AnalysisError为不可继续。
        """
        # 先处理资源生命周期，再区分不可重试的部分推进失败。
        self._ensure_open()
        if self._failed:
            raise AnalysisError('预算时序检测器已失败，禁止重试当前状态')
        if self._failed_workspace_cost:
            raise AnalysisError('上次工作区尚未释放，请先关闭预算时序检测器')

    @property
    def rule(self):
        """读取冻结规则。参数: 无。返回: TemporalRule。异常: ResultClosedError。"""
        # 规则只借用固定申请内的冻结对象，不提供重新配置入口。
        self._ensure_open()
        return self._rule

    @property
    def start_ns(self):
        """读取domain起点。参数: 无。返回: int ns。异常: ResultClosedError。"""
        # 域起点由构造器验证，读取时不重新计算或改变检测状态。
        self._ensure_open()
        return self._start

    @property
    def end_ns(self):
        """读取domain终点。参数: 无。返回: int ns。异常: ResultClosedError。"""
        # 域终点由构造器验证，不能用读取请求补造terminal输入。
        self._ensure_open()
        return self._end

    @property
    def next_deadline_ns(self):
        """读取core准确待确认截止。参数: 无。返回: int或None。异常: 关闭或失败。"""
        # 只从仍可推进的私有core读取准确deadline，不重建已失败状态。
        self._ensure_active()
        return self._detector.next_deadline_ns

    @property
    def closed(self):
        """读取资源关闭状态。参数: 无。返回: bool。异常: 无。"""
        # 生命周期状态不依赖已释放的core或批引用。
        return self._closed

    @property
    def failed(self):
        """读取推进失败状态。参数: 无。返回: bool。异常: 无；close不掩盖失败。"""
        # 保留失败事实供收尾诊断，资源关闭不能把它改写为成功。
        return self._failed

    @property
    def duration_counts(self):
        """借出已结束迟滞核的固定累计值，其他检测器无额外结果。

        参数: 无。返回: 整数纳秒对或None。异常: 关闭、失败或尚未结束错误。
        """
        self._ensure_active()
        return self._detector.duration_counts if isinstance(self._detector, StabilityDetector) else None

    def extend_observed_end(self, end_ns):
        """将在线上界推进到新读到的真实末端，不交付terminal或分配输入历史。

        参数: 已观测int64末端。返回: None。异常: 已封闭或末端回退。
        """
        from ..timebase.conversion import require_int64_ns
        self._ensure_active()
        end = require_int64_ns(end_ns, 'observed_end')
        if self._detector.ended or self._detector.finished or end < self._end:
            raise ValueError('在线观测上界只能在封闭前递增')
        self._detector.end_ns = self._end = end
        if isinstance(self._detector, StabilityDetector):
            self._detector._core.end_ns = end

    def set_observed_end(self, end_ns):
        """将请求上界收窄为实际观测终点，必须在交付该终点组之前调用。

        参数: end_ns实际int64终点。返回: None。不生成terminal或结果，不回撤已处理组。
        异常: 类型/范围或已完成错误；非法调用不改变core与owner边界。
        """
        from ..timebase.conversion import require_int64_ns
        self._ensure_active()
        end = require_int64_ns(end_ns,'observed_end')
        detector = self._detector
        if (detector.ended or detector.finished or not self._start <= end <= self._end
                or detector.last_time is not None and end <= detector.last_time):
            raise ValueError('观测终点必须在尚未交付的请求范围内')
        detector.end_ns = end
        if isinstance(detector,StabilityDetector):
            detector._core.end_ns = end
        self._end = end

    def _workspace_cost(self, ticks, maximum_events):
        """估算输入持有、批量数组、最多N事件及其稳定ID临时串的同时存活上界。

        参数: ticks已提供typed tuple；maximum_events本批最大输出数。
        返回: 非负int bytes，空批也覆盖固定工作容器。
        异常: 元数据估算错误；尚未调用core，不改变业务状态。
        """
        # 每tick最多一个最终事件；16KiB覆盖数组、前缀/run索引、掩码和Python装箱。
        # 规则/refs可能含任意长文本，32倍深成本同时覆盖Event模型/稳定ID编码及引用。
        # 输入tick深成本单独计入，已有调用方tuple不因此被当作免费内存。
        return 32768 + 4 * _metadata_bytes(ticks) + maximum_events * (16384 + 32 * self._event_metadata_cost)

    def _register(self, cost, events):
        """只构造结果；外层取得本地引用后才登记并负责异常清理。

        参数: cost本批完整申请；events已正式排空tuple。
        返回: 尚未登记的TemporalEventBatch。异常: 构造/返回取消由推进边界抵销并failed。
        """
        # helper返回取消时结果尚未安装；只有外层可见的local才能进入登记器。
        return TemporalEventBatch(self, cost, events)

    def _discard_unreturned(self, result):
        """撤销本次未交付结果，预算仍由外层一次抵销，不关闭先前批。

        参数: result为已构造的新批或None。返回: None。
        异常: 内部登记不一致；不调用result.close以免重复释放本批申请。
        """
        # 构造或helper返回失败时外层未取得对象，且对象还没有进入登记器。
        if result is None:
            return
        # add可能已经安装后报错，只撤销当前local；先前结果保持独立所有权。
        self._results.discard(result)
        result._closed, result._cost = True, 0
        result._events = result._owner = None
        result._previous = result._next = result._registry = None

    def _fail(self):
        """丢弃部分推进的core并永久禁止重试，保留此前结果和固定元数据诊断。

        参数: 无。返回: None。异常: 无主动异常；不声称旧业务状态已回滚。
        """
        # 业务状态不可事务回滚，失败后丢弃core而保留自有已交付批。
        self._failed = True
        self._detector = None

    def _release_failed_workspace(self):
        """退还未交付批的实际申请，释放完成后取消也立即清槽。

        参数: 无。返回: None。异常: 原退款错误；尚未释放的金额留给下一次close。
        本槽与固定申请、此前已交付批分开；只围绕一次直接账本调用判断副作用。
        """
        cost = self._failed_workspace_cost
        if not cost:
            return
        before = self._budget.ram_bytes
        try:
            self._budget.release_ram(cost)
            self._failed_workspace_cost = 0
        except BaseException:
            if self._budget.ram_bytes == before - cost:
                self._failed_workspace_cost = 0
            raise

    def _refund_failed_workspace(self, cost, original):
        """接管本次未交付批的费用并尝试归还，保留原推进错误和最高owner。

        参数: cost为本次已实际申请字节，original为业务或取消异常。
        返回: None。退款失败只追加说明；调用方继续抛原异常，close负责重试。
        """
        self._failed_workspace_cost = cost
        try:
            self._release_failed_workspace()
        except BaseException as cleanup:
            original.add_note('时序检测工作区释放失败: ' + type(cleanup).__name__)
            original.temporal_detector_cleanup_owner = self

    def push(self, ticks: tuple[ConditionTick, ...], exit_ticks=None, *, advances=None) -> TemporalEventBatch:
        """在预算内整批推进独立core，随后正式排空当前最终事件。

        参数: ticks完整组tuple，允许空批；迟滞可另给同刻exit_ticks，start_end必须提供结束组，普通防抖省略。
            批次不重置候选/边沿状态；advances仅记录模式提供，每组一个必要周期增量。
        返回: 须close的TemporalEventBatch，最多len(ticks)个最终事件。
        异常: 预算拒绝或申请取消发生在core前，可恢复；core调用或后续任何异常/取消使owner failed，
            抵销本批申请，先前批保持可读和计账。
        """
        # 输入协议检查在core前完成，错误输入不消耗任何检测状态。
        self._ensure_active()
        if type(ticks) is not tuple or any(not isinstance(tick, ConditionTick) for tick in ticks):
            raise TypeError('预算时序push需要完整ConditionTick tuple')
        if isinstance(self._detector, StartEndDetector) and exit_ticks is None:
            raise TypeError('start_end必须提供结束条件')
        if exit_ticks is not None and (not isinstance(self._detector, (StabilityDetector, StartEndDetector))
                or type(exit_ticks) is not tuple or any(not isinstance(tick, ConditionTick) for tick in exit_ticks)):
            raise TypeError('独立结束/退出仅供start_end或迟滞，且需完整ConditionTick tuple')
        cost = self._workspace_cost(ticks, len(ticks))
        from ..core.temporal_clock import require_clock_advances
        require_clock_advances(ticks, advances, self._detector.record_clock, self._detector.last_time)
        if advances is not None:
            cost += 4096 + len(advances) * 1024
        if exit_ticks is not None:
            cost += 4 * _metadata_bytes(exit_ticks)
        # 申请/开始标志与快照区分未推进的preflight取消和不能重试的core故障。
        before, reserved, started = self._budget.ram_bytes, False, False
        result = None
        try:
            # 申请失败不会触及core；已扣账的reserve返回取消也在外层一次抵销。
            self._budget.reserve_ram(cost)
            reserved = True
            # 从调用core开始即不承诺事务回滚；数组后端收到完整批而非逐点外部循环。
            started = True
            if exit_ticks is None:
                self._detector.push(ticks, advances=advances)
            else:
                self._detector.push(ticks, exit_ticks, advances=advances)
            events = self._detector.drain_events()
            # 单规则每tick最多闭合一个活动或生成一个点事件，超过即拒绝未计账输出。
            if len(events) > len(ticks):
                raise AnalysisError('时序检测输出超过预先申请的每tick一个事件上界')
            # 取得local后再安装，add中途失败也能精准撤销当前批的链接。
            result = self._register(cost, events)
            self._results.add(result)
            # 交付只读批，完整本批申请转交结果直到其close。
            return result
        except BaseException as error:
            # 排空/构造/登记属于推进后失败，preflight拒绝或取消则保留原core状态。
            if started:
                self._discard_unreturned(result)
                self._fail()
            # 正常申请记录与单线程快照共同覆盖reserve成功返回前的取消窗口。
            if reserved or self._budget.ram_bytes == before + cost:
                self._refund_failed_workspace(cost, error)
            raise

    def finish(self) -> TemporalEventBatch:
        """在core已消费真正terminal后封闭检测器，返回剩余增量批且不重发旧事件。

        参数: 无，不能补造终点或消费新的输入。
        返回: 须close的批；本owner每次push均排空，因此正常finish.events为空。
        异常: 预算拒绝/申请取消在core前可重试；缺terminal/重复finish或后续失败使owner failed。
        """
        # finish的固定工作容器也先申请，超限不消费terminal封闭状态。
        self._ensure_active()
        cost = self._workspace_cost((), 0)
        # 申请/开始标志覆盖reserve返回取消，外层local覆盖登记部分安装。
        before, reserved, started = self._budget.ram_bytes, False, False
        result = None
        try:
            # 预算申请失败或取消时不消费真正terminal的封闭状态。
            self._budget.reserve_ram(cost)
            reserved = True
            # 正式finish仍执行既有terminal协议；已交付事件不再留在core.events中。
            started = True
            self._detector.finish()
            events = self._detector.drain_events()
            # 每次push已经交付全部当前输出，finish不得重发事件或另造终点活动。
            if events:
                raise AnalysisError('预算检测器finish出现未在push中增量交付的事件')
            # 在外层可清理引用内完成安装后，才交付终点剩余批。
            result = self._register(cost, events)
            self._results.add(result)
            return result
        except BaseException as error:
            # terminal部分封闭不可重试，尚未开始的preflight仍保持原检测器可用。
            if started:
                self._discard_unreturned(result)
                self._fail()
            # 不对未成功的申请做释放，也不漏掉已扣账但返回取消的申请。
            if reserved or self._budget.ram_bytes == before + cost:
                self._refund_failed_workspace(cost, error)
            raise

    def close(self):
        """关闭全部自有批和固定申请，不关闭调用方budget或删除任何数据。

        参数: 无。返回: None，幂等且支持部分构造失败。
        异常: 内部账本不一致或取消；已释放固定申请时完成最小收尾后传播。
            failed标志保留用于说明此前失败；尚未释放时可重试关闭。
        """
        # 关闭可重复调用，不重复释放固定或批申请。
        if self._closed:
            return
        # 未交付批的失败退款不属于任何已交付结果，先处理它且保留重试金额。
        self._release_failed_workspace()
        # 逐项关闭避免收尾时再复制活动批集合；没有其它owner的结果进入此集合。
        while self._results:
            next(iter(self._results)).close()
        # 所有链节点都已脱离，仅剩固定申请；快照识别release完成后的返回取消。
        cost, before = self._fixed_cost, self._budget.ram_bytes
        try:
            self._budget.release_ram(cost)
            self._fixed_cost = 0
            self._closed = True
            self._rule = self._refs = self._detector = self._results = None
        except BaseException:
            # 固定抵销已发生则完成关闭，避免调用方重试时再释放同一申请。
            if self._fixed_cost == 0 or self._budget.ram_bytes == before - cost:
                self._fixed_cost = 0
                self._closed = True
                self._rule = self._refs = self._detector = self._results = None
            # 仍传播原异常，不把收尾完成当作此次close未发生取消。
            raise
