"""把已经收齐的同刻更新原子提交为各别名的最新规范观测。

输入为当前SignalDefinition/session及DecodedTimeGroup，输出选定更新和冲突数量。
先检查整个组的绑定、dtype/单位和递增时间，再应用既有同刻error/last_by_sequence政策。
组内任一失败不会更新任何别名；无效更新同样覆盖旧值，不重做归一化或回退有效观测。
共享ResourceBudget覆盖声明、最新记录和提交临时容器，不保存全历史。
这是两后端可共享的控制协议；TTL/来源范围/表达式查询和独立对齐内核留后续。
无文件操作或旧链调用，close释放自有引用；调用方保存返回对象的空间另负责。
"""

# 控制协议只处理已经归一化的标量事实，不调用参考或NumPy数值内核。
from dataclasses import dataclass, replace
from math import isnan
from types import MappingProxyType
from ..core.binding import SignalDefinition
from ..core.numeric import ScalarValue
from ..core.scalar import _scalar_from_validated_fields
from ..core.types import SignalDType
from ..core.validation import require_identifier
from ..results.budget import ResourceBudget, _reserve_owned_ram
from ..results.errors import ResultClosedError
from .groups import DecodedTimeGroup
from .history import _metadata_bytes
from .history_records import HistorySample, estimate_record_bytes


@dataclass(frozen=True)
class CommittedUpdates:
    """保存一次原子提交结果，别名唯一，原seq/ref/质量及显式冲突数量保留。"""

    time_ns: int
    updates: tuple[HistorySample, ...]
    conflict_count: int

    def __post_init__(self):
        """复用完整组检查时间/身份，再限制每别名仅有一个选定观测。

        参数: 无，读取字段。返回: None。异常: TypeError/ValueError为非法结果。
        """
        DecodedTimeGroup(self.time_ns, self.updates)
        if len({item.name for item in self.updates}) != len(self.updates) or type(self.conflict_count) is not int or self.conflict_count < 0:
            raise ValueError('提交结果需唯一别名与非负原生冲突数')


def _committed_from_validated_fields(time_ns, updates, conflict_count):
    """包装本次已完成绑定/冲突选择的结果，不再遍历一次时间组。

    参数: 原完整组时刻、每别名唯一的选定tuple、非负冲突数。
    返回: CommittedUpdates。异常: 分配错误传播，不安装部分状态。
    只由LatestSignalState.apply在全部检查后使用；公开构造仍完整验证。
    """
    result = object.__new__(CommittedUpdates)
    object.__setattr__(result, 'time_ns', time_ns)
    object.__setattr__(result, 'updates', updates)
    object.__setattr__(result, 'conflict_count', conflict_count)
    return result


def _same_fact(left: HistorySample, right: HistorySample) -> bool:
    """按现有核心比较逻辑值/类型/valid/quality，NaN诊断可以同因一致。

    参数: left/right已检查的同别名同刻样本。返回: bool事实一致。
    异常: 内部已校验类型错误传播；不把不同CSV位置本身算数值冲突。
    """
    a, b = left.value, right.value
    # dtype/单位另在绑定检查，原位置不同不会改变数值冲突政策。
    return (a.valid == b.valid and a.quality == b.quality and a.code == b.code and type(a.value) is type(b.value)
            and (a.value == b.value or type(a.value) is float and isnan(a.value) and isnan(b.value)))


@dataclass(frozen=True)
class _StateSnapshot:
    """持有一次完整提交的只读映射、时间、冲突计数与预算量；安装后字段不可改。"""

    latest: MappingProxyType
    last_time_ns: int | None
    conflict_count: int
    retained_cost: int
    revision: int  # 成功完整组提交次数，仅用于内部两段查询证明提交顺序。
    costs: MappingProxyType  # 每别名最新记录的已核费用；与latest在同一快照内替换。
    prior: dict | None = None  # 仅v4最近一组被替换的(时间,规范标量)，无原记录定位。


class LatestSignalState:
    """持有固定声明与每别名一个最新记录；成功完整组严格递增，不按批次重置。"""

    def __init__(self, budget: ResourceBudget, definitions: tuple[SignalDefinition, ...], session_id: str,
                 *, declaration_owner=None):
        """先申请声明/容器预算，再检查唯一别名并创建空状态。

        参数: budget共享账本；definitions当前冻结声明，常量计划可为空tuple；session_id当前会话。
            declaration_owner仅供运行树传入仍持有同一声明的RunSession；独立调用省略。
        返回: 新状态。异常: 配置/预算/取消；保留原异常并清理成功申请，包括申请返回取消。
            持续清理失败时，原异常的state_cleanup_owner提供本次状态的恢复close入口。
        """
        # 没有信号仍需固定付费的时间游标；真实原行/范围由上层证明，不伪造占位信号。
        if not isinstance(budget, ResourceBudget) or type(definitions) is not tuple or any(not isinstance(item, SignalDefinition) for item in definitions):
            raise TypeError('状态需要账本与SignalDefinition tuple')
        # 周期须在来源初始化后核实；最新值状态不接受尚待DBC的声明。
        if any(item.valid_for_ns is None for item in definitions):
            raise ValueError('状态需要已确定的有效期；请先读取DBC周期或提供period/valid_for')
        require_identifier(session_id, 'state.session_id')
        # 新增费用映射只借用声明中的名称，自己拥有字典槽、只读代理和整数费用。
        # 固定申请覆盖一份持有映射；apply另外申请新副本，不能把新旧同时存在算成一份。
        cache_cost = 512 + len(definitions) * 128
        from .static_metadata import static_metadata_bytes
        borrowed = ()
        if declaration_owner is not None:
            from .run_session import RunSession
            if (not isinstance(declaration_owner, RunSession) or declaration_owner.closed or declaration_owner._closing
                    or declaration_owner._budget is not budget):
                raise ValueError('共享声明必须由同一账本中仍开放的运行会话持有')
            borrowed = declaration_owner._plan.bindings.signals
        # 运行树保证先关子state再释放父声明；不接受数字/布尔标志作为共享证明。
        # 只有与父会话完全相同的声明对象才借用；DBC补全或类型变换产生的新对象照付。
        # 独立使用时没有父owner，完整声明在本状态中计一次，驱动只借此状态。
        cost = (32768 + len(definitions) * 8192 + cache_cost
                + static_metadata_bytes((definitions, session_id), borrowed=borrowed)
                + sum(512 + 64 * len(item.choices) for item in definitions))
        # 自有状态只经私有指针更新，公开属性不能绕过绑定检查或改写预算所有权。
        self._budget, self._closed, self._session_id = budget, False, session_id
        self._fixed_cost, self._definitions, self._labels, self._snapshot = 0, None, None, None
        # _held_cost记录本对象实际已付总额；与当前快照费用的差额是未提交事务。
        # 这项差额从当前快照推导，成功时只需安装一个快照指针，不再同步第二个标志。
        self._held_cost = 0
        try:
            # 申请也在保护区；单线程账本可辨别操作成功但返回被取消的交接。
            _reserve_owned_ram(self, cost, '_fixed_cost')
            # 同一别名不能隐式选首声明；模型本身已校验别名/策略/单位。
            if len({item.name for item in definitions}) != len(definitions):
                raise ValueError('状态定义别名重复')
            self._definitions = MappingProxyType({item.name: item for item in definitions})
            # ENUM物理下标按声明标签的首次出现顺序，连无效观测也必须携带同一域。
            self._labels = MappingProxyType({item.name: tuple(dict.fromkeys(label for _, label in item.choices))
                                            for item in definitions if item.dtype is SignalDType.ENUM})
            self._snapshot = _StateSnapshot(MappingProxyType({item.name: None for item in definitions}), None, 0, 0, 0,
                                            MappingProxyType({item.name: 0 for item in definitions}))
        except BaseException as exc:
            # 构造异常不能被释放取消替换；只重试一次，未抵销费用仍归本状态owner。
            try:
                self.close()
            except BaseException as cleanup:
                exc.add_note(f'状态初始化清理附加失败: {type(cleanup).__name__}')
                if not self._closed:
                    try:
                        self.close()
                    except BaseException as retry:
                        exc.add_note(f'状态初始化清理重试失败: {type(retry).__name__}')
                        if not self._closed:
                            exc.state_cleanup_owner = self
                            exc.add_note('释放恢复后调用state_cleanup_owner.close()')
            raise

    @property
    def budget(self) -> ResourceBudget:
        """返回共享账本引用。参数: 无。返回: ResourceBudget。异常: 无；不转移所有权。"""
        return self._budget

    @property
    def session_id(self) -> str:
        """返回固定会话标识。参数: 无。返回: str。异常: 无。"""
        return self._session_id

    @property
    def closed(self) -> bool:
        """返回关闭状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    @property
    def definitions(self) -> MappingProxyType:
        """返回固定声明只读视图。参数: 无。返回: 映射。异常: ResultClosedError为关闭。"""
        self._ensure_open()
        return self._definitions

    @property
    def latest(self) -> MappingProxyType:
        """返回当前快照只读视图。参数: 无。返回: 映射。异常: ResultClosedError为关闭。

        调用方跨提交保存旧视图会延长旧观测寿命，该外部保留量不由状态预算负责。
        """
        self._ensure_open()
        return self._snapshot.latest

    @property
    def fixed_cost(self) -> int:
        """返回声明预算量。参数: 无。返回: int bytes，关闭后0。异常: 无。"""
        return self._fixed_cost

    @property
    def retained_cost(self) -> int:
        """返回最新记录预算量。参数: 无。返回: int bytes，关闭后0。异常: 无。"""
        return 0 if self._snapshot is None else self._snapshot.retained_cost

    @property
    def _transaction_delta(self) -> int:
        """取得实际已付量与当前快照的差额。参数: 无。返回: 带符号bytes。异常: 无。"""
        return self._held_cost - self._fixed_cost - self.retained_cost

    @property
    def last_time_ns(self) -> int | None:
        """返回最后完整组时间。参数: 无。返回: int ns或None。异常: 无。"""
        return None if self._snapshot is None else self._snapshot.last_time_ns

    @property
    def conflict_count(self) -> int:
        """返回累计显式冲突数。参数: 无。返回: int，关闭后0。异常: 无。"""
        return 0 if self._snapshot is None else self._snapshot.conflict_count

    @property
    def revision(self) -> int:
        """读取成功完整组的提交版本，失败提交不推进该版本。

        参数: 无。返回: 原生非负int，初始0，每成功提交增加1。
        异常: ResultClosedError为状态关闭；不能通过此属性修改快照。
        """
        # 版本与latest/time在同一冻结快照中安装，不建立独立可变计数器。
        self._ensure_open()
        return self._snapshot.revision

    def _ensure_open(self) -> None:
        """拒绝关闭后访问。参数: 无。返回: None。异常: ResultClosedError。"""
        if self.closed:
            raise ResultClosedError('最新信号状态已关闭')

    def get(self, name: str) -> HistorySample | None:
        """返回当前原样规范观测；无更新是None，无效更新不会回退旧值。

        参数: name当前简单别名。返回: HistorySample或None。
        异常: KeyError为未知别名；ResultClosedError为关闭。不检查TTL或观测范围。
        """
        self._ensure_open()
        return self.latest[name]

    def _before_group(self, name):
        """查组前标量。参数: v4别名。返回: (时间,标量)或None。异常: 未声明别名。"""
        snapshot = self._snapshot
        if snapshot.prior is not None and name in snapshot.prior:
            return snapshot.prior[name]
        sample = snapshot.latest[name]
        return None if sample is None else (sample.time_ns, sample.value)

    def apply(self, group: DecodedTimeGroup) -> CommittedUpdates:
        """整个组检查/选择成功后一次替换最新状态，任何失败保持旧状态。

        参数: group已收齐的同刻更新，time_ns严格晚于上次提交。
        返回: CommittedUpdates，选定更新按别名排序、每别名一次，冲突数遵循核心政策。
        异常: 类型/时间/绑定/同刻冲突错误或预算超限；不部分更新或重做转换。
        """
        self._ensure_open()
        if self._transaction_delta:
            raise ResultClosedError('最新信号状态尚有未恢复的事务费用，请先关闭state_cleanup_owner')
        if not isinstance(group, DecodedTimeGroup):
            raise TypeError('状态只能提交完整DecodedTimeGroup')
        if self.last_time_ns is not None and group.time_ns <= self.last_time_ns:
            raise ValueError('状态完整组必须严格递增，不能重复提交或回退')
        # 先付分组引用、费用索引及固定别名副本，再建立临时容器。
        # 额外每条256覆盖本组id→费用索引；不持有跨组/跨运行的记录缓存。
        work = (4096 + len(self.definitions) * 512 + 512 + len(self.definitions) * 128
                + 768 * len(group.samples))
        # 旧历史只有原始整数时，当前组要额外构造并保留一个定宽整数 ScalarValue。
        # 每字段包装及安全倍数与 estimate_record_bytes 一致，uint64 最大值覆盖两种原码。
        enrich = sum(1 for item in group.samples if item.name in self.definitions and
                     self.definitions[item.name].capture_code and item.value.code is None)
        costs = snapshot = record_costs = None
        try:
            self._change_budget(work)
            # 当前输入对象不可变，临时费用与最终保留费用可共用本次估算。
            record_costs = {id(item): estimate_record_bytes(item) for item in group.samples}
            payload_cost = sum(record_costs.values())
            if enrich:
                from ..results.codec import _estimate
                payload_cost += enrich * 16 * (256 + _estimate(ScalarValue((1 << 64) - 1, SignalDType.UINT64)))
            self._change_budget(payload_cost)
            work += payload_cost
            candidates, identities = {}, set()
            for sample in group.samples:
                definition = self.definitions.get(sample.name)
                if definition is None:
                    raise ValueError('完整组包含未声明别名')
                # 完整来源/会话/字段保留，CSV额外定位不能用来冒充其他信号。
                ref = sample.source_ref
                if (ref.session_id != self.session_id or ref.source_name != definition.source or ref.field != definition.field
                        or sample.value.dtype is not definition.dtype or sample.unit != definition.unit):
                    raise ValueError('完整组当前绑定/dtype/单位不匹配')
                if definition.dtype is SignalDType.ENUM and sample.value.labels != self._labels[sample.name]:
                    raise ValueError('完整组ENUM标签域与当前声明不匹配')
                if definition.capture_code and sample.value.code is None:
                    from ..core.enum_codes import history_code
                    sample = replace(sample, value=replace(sample.value, code=history_code(definition, sample)))
                # 一个别名绑定单一来源；不同CSV定位不能为重复原seq提供合法平手。
                identity = (sample.name, sample.sequence)
                if identity in identities:
                    raise ValueError('完整组同别名原sequence重复')
                identities.add(identity)
                candidates.setdefault(sample.name, []).append(sample)
            selected, conflicts = [], 0
            for name in sorted(candidates):
                records = candidates[name]
                same = all(_same_fact(records[0], item) for item in records)
                if not same and self.definitions[name].same_time_policy == 'error':
                    raise ValueError(f'同信号同时间冲突：{name}@{group.time_ns}ns')
                # 按原来源sequence选择，与组内遍历顺序无关；相同事实不记冲突。
                selected.append(max(records, key=_sequence))
                conflicts += 0 if same else len(records) - 1
            result = _committed_from_validated_fields(group.time_ns, tuple(selected), conflicts)
            latest = dict(self.latest)
            costs = dict(self._snapshot.costs)
            retained = self.retained_cost
            # v4 where 查询可以在任意次状态提交后才开始，不能靠上次查询缓存区分
            # “条件刷新”和“切换”。每别名最多一项及已计费的规范标签域，包含在
            # 按声明数量/宽度预付的固定状态内；不保留原始定位及无效输入大原文。
            prior = None
            for item in selected:
                if prior is None:
                    prior = {}
                old = latest[item.name]
                prior[item.name] = None
                if old is not None:
                    value = old.value
                    prior[item.name] = (old.time_ns, _scalar_from_validated_fields(value.value if value.valid else None,
                        value.dtype, value.valid, value.quality, self._labels.get(item.name, ()), value.code,
                        partial=value.partial))
                # 只估算本组真正选中的替换记录；未更新别名沿用不可变快照中的已核费用。
                # 原码补齐发生在选择前，因此这里收费的是最终保留对象，不是原始输入副本。
                cost = record_costs.get(id(item))
                # 补齐原码会产生新对象；只有该情况重新核算最终保留内容。
                if cost is None:
                    cost = estimate_record_bytes(item)
                retained += cost - costs[item.name]
                costs[item.name] = cost
                latest[item.name] = item
            # 工作申请包含所有新增记录；原未变记录由原持有申请覆盖。
            change = retained - self.retained_cost
            if change > work:
                raise ValueError('状态内部预估不足，拒绝提交')
            # 构造映射、累计整数和整帧均可能分配；必须在安装前完成才能保持失败原子性。
            snapshot = _StateSnapshot(MappingProxyType(latest), group.time_ns, self.conflict_count + conflicts,
                                      retained, self.revision + 1, MappingProxyType(costs), prior)
            release_amount = work - change
            record_costs = None
            # 账本转账也先完成；之后仅赋值一个已有指针，没有计数算术或容器构造。
            self._change_budget(-release_amount)
            self._snapshot = snapshot
            return result
        except BaseException as error:
            # 新缓存没有交付时不由异常栈延长其寿命；外部输入和旧只读快照仍归原所有者。
            costs = snapshot = record_costs = None
            self._restore_transaction(error)
            raise

    def _change_budget(self, delta):
        """为一次直接预算操作登记实际增减，操作完成后取消也不会遗失归属。

        参数: delta为带符号费用，正数申请、负数退款。返回: None。
        异常: 原预算或取消传播；只观察本次直接调用，不按共享余额计算其他费用。
        """
        if delta == 0:
            return
        before = self._budget.ram_bytes
        try:
            if delta > 0:
                self._budget.reserve_ram(delta)
            else:
                self._budget.release_ram(-delta)
        finally:
            if self._budget.ram_bytes == before + delta:
                self._held_cost += delta

    def _restore_transaction(self, primary):
        """恢复未提交事务的实际费用差额，清理失败不替换最先发生的错误。

        参数: primary为提交中的原异常。返回: None。异常: 不主动替换主异常；
        两次恢复仍失败时附state_cleanup_owner，禁止再次apply，由同一对象close处理。
        """
        for attempt in range(2):
            delta = self._transaction_delta
            if delta == 0:
                return
            try:
                # 正差额退回未交付工作区；负差额则补回刚退掉的旧记录费用。
                # 后者不增加实际数据，所需余量正是本事务先前释放的量。
                self._change_budget(-delta)
            except BaseException as cleanup:
                primary.add_note(f'状态事务恢复第{attempt + 1}次附加失败: {type(cleanup).__name__}')
        if self._transaction_delta:
            primary.state_cleanup_owner = self
            primary.add_note('费用恢复后调用state_cleanup_owner.close()')

    def close(self) -> None:
        """丢弃自有声明与最新记录，抵销账本，不删除历史或修改返回对象。

        参数: 无。返回: None，幂等。异常: 预算/取消传播；抵销前可重试，已抵销仍最小关闭。
        """
        if self.closed:
            return
        # 外部只读旧视图不改；以账本实际变化区分操作前后取消，避免二次扣账。
        # 失败事务可能尚有正/负差额；只退本对象真实已付金额，不拿旧快照的逻辑费用
        # 代替账本，也不从共享总余额反推本对象需要退多少。
        cost, before, released = self._held_cost, self.budget.ram_bytes, False
        try:
            self.budget.release_ram(cost)
            released = True
        finally:
            if released or self.budget.ram_bytes == before - cost:
                self._closed = True
                self._snapshot = self._definitions = self._labels = None
                self._fixed_cost = self._held_cost = 0


def _sequence(sample: HistorySample) -> int:
    """选定稳定原序号。参数: sample规范观测。返回: int sequence。异常: 无。"""
    return sample.sequence
