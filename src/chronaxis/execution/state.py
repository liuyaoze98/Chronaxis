"""把已经收齐的同刻更新原子提交为各别名的最新规范观测。

输入为当前SignalDefinition/session及DecodedTimeGroup，输出选定更新和冲突数量。
先检查整个组的绑定、dtype/单位和递增时间，再应用既有同刻error/last_by_sequence政策。
组内任一失败不会更新任何别名；无效更新同样覆盖旧值，不重做归一化或回退有效观测。
共享ResourceBudget覆盖声明、最新记录和提交临时容器，不保存全历史。
这是两后端可共享的控制协议；TTL/来源范围/表达式查询和独立对齐内核留后续。
无文件操作或旧链调用，close释放自有引用；调用方保存返回对象的空间另负责。
"""

# 控制协议只处理已经归一化的标量事实，不调用参考或NumPy数值内核。
from dataclasses import dataclass
from math import isnan
from types import MappingProxyType
from ..core.binding import SignalDefinition
from ..core.types import SignalDType
from ..core.validation import require_identifier
from ..results.budget import ResourceBudget
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


def _same_fact(left: HistorySample, right: HistorySample) -> bool:
    """按现有核心比较逻辑值/类型/valid/quality，NaN诊断可以同因一致。

    参数: left/right已检查的同别名同刻样本。返回: bool事实一致。
    异常: 内部已校验类型错误传播；不把不同CSV位置本身算数值冲突。
    """
    a, b = left.value, right.value
    # dtype/单位另在绑定检查，原位置不同不会改变数值冲突政策。
    return (a.valid == b.valid and a.quality == b.quality and type(a.value) is type(b.value)
            and (a.value == b.value or type(a.value) is float and isnan(a.value) and isnan(b.value)))


@dataclass(frozen=True)
class _StateSnapshot:
    """持有一次完整提交的只读映射、时间、冲突计数与预算量；安装后字段不可改。"""

    latest: MappingProxyType
    last_time_ns: int | None
    conflict_count: int
    retained_cost: int
    revision: int  # 成功完整组提交次数，仅用于内部两段查询证明提交顺序。


class LatestSignalState:
    """持有固定声明与每别名一个最新记录；成功完整组严格递增，不按批次重置。"""

    def __init__(self, budget: ResourceBudget, definitions: tuple[SignalDefinition, ...], session_id: str):
        """先申请声明/容器预算，再检查唯一别名并创建空状态。

        参数: budget共享账本；definitions当前冻结声明，常量计划可为空tuple；session_id当前会话。
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
        cost = 32768 + len(definitions) * 8192 + _metadata_bytes((definitions, session_id)) * 16
        # 自有状态只经私有指针更新，公开属性不能绕过绑定检查或改写预算所有权。
        self._budget, self._closed, self._session_id = budget, False, session_id
        self._fixed_cost, self._definitions, self._labels, self._snapshot = 0, None, None, None
        before = budget.ram_bytes
        try:
            # 申请也在保护区；单线程账本可辨别操作成功但返回被取消的交接。
            budget.reserve_ram(cost)
            self._fixed_cost = cost
            # 同一别名不能隐式选首声明；模型本身已校验别名/策略/单位。
            if len({item.name for item in definitions}) != len(definitions):
                raise ValueError('状态定义别名重复')
            self._definitions = MappingProxyType({item.name: item for item in definitions})
            # ENUM物理下标按声明标签的首次出现顺序，连无效观测也必须携带同一域。
            self._labels = MappingProxyType({item.name: tuple(dict.fromkeys(label for _, label in item.choices))
                                            for item in definitions if item.dtype is SignalDType.ENUM})
            self._snapshot = _StateSnapshot(MappingProxyType({item.name: None for item in definitions}), None, 0, 0, 0)
        except BaseException as exc:
            if self._fixed_cost == 0 and budget.ram_bytes == before + cost:
                self._fixed_cost = cost
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

    def apply(self, group: DecodedTimeGroup) -> CommittedUpdates:
        """整个组检查/选择成功后一次替换最新状态，任何失败保持旧状态。

        参数: group已收齐的同刻更新，time_ns严格晚于上次提交。
        返回: CommittedUpdates，选定更新按别名排序、每别名一次，冲突数遵循核心政策。
        异常: 类型/时间/绑定/同刻冲突错误或预算超限；不部分更新或重做转换。
        """
        self._ensure_open()
        if not isinstance(group, DecodedTimeGroup):
            raise TypeError('状态只能提交完整DecodedTimeGroup')
        if self.last_time_ns is not None and group.time_ns <= self.last_time_ns:
            raise ValueError('状态完整组必须严格递增，不能重复提交或回退')
        # 先计输入选定记录/分组引用及固定别名副本，再建立任何临时容器。
        work = 4096 + len(self.definitions) * 512 + sum(512 + estimate_record_bytes(item) for item in group.samples)
        self.budget.reserve_ram(work)
        workspace_owned = True
        try:
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
            result = CommittedUpdates(group.time_ns, tuple(selected), conflicts)
            latest = dict(self.latest)
            latest.update((sample.name, sample) for sample in selected)
            retained = sum(estimate_record_bytes(item) for item in latest.values() if item is not None)
            # 工作申请包含所有新增记录；原未变记录由原持有申请覆盖。
            change = retained - self.retained_cost
            if change > work:
                raise ValueError('状态内部预估不足，拒绝提交')
            # 构造映射、累计整数和整帧均可能分配；必须在安装前完成才能保持失败原子性。
            snapshot = _StateSnapshot(MappingProxyType(latest), group.time_ns, self.conflict_count + conflicts,
                                      retained, self.revision + 1)
            release_amount = work - change
            # 账本转账也先完成；之后仅赋值一个已有指针，没有计数算术或容器构造。
            self.budget.release_ram(release_amount)
            workspace_owned = False
            self._snapshot = snapshot
            return result
        finally:
            # 成功已转账新增持有量；失败只抵销本次临时申请，旧状态及预算保持。
            if workspace_owned:
                self.budget.release_ram(work)

    def close(self) -> None:
        """丢弃自有声明与最新记录，抵销账本，不删除历史或修改返回对象。

        参数: 无。返回: None，幂等。异常: 预算/取消传播；抵销前可重试，已抵销仍最小关闭。
        """
        if self.closed:
            return
        # 外部只读旧视图不改；以账本实际变化区分操作前后取消，避免二次扣账。
        cost, before, released = self.fixed_cost + self.retained_cost, self.budget.ram_bytes, False
        try:
            self.budget.release_ram(cost)
            released = True
        finally:
            if released or self.budget.ram_bytes == before - cost:
                self._closed = True
                self._snapshot = self._definitions = self._labels = None
                self._fixed_cost = 0


def _sequence(sample: HistorySample) -> int:
    """选定稳定原序号。参数: sample规范观测。返回: int sequence。异常: 无。"""
    return sample.sequence
