"""在预算内按原求值顺序累计调用方已经算好的旧口径贡献。

输入为LegacySumContribution的有限精确tuple，每项保留LegacyDecodedUpdate
身份并显式选择有限float贡献或跳过原因。输出为未舍入的冻结快照；本层不求
表达式、不再乘period/factor/dt，不把原quality推断成TTL、缓存或跳过政策。
legacy_policy必须由提供者明确填写，不证明完整复现ChrgInfo的旧行为。

累计器只保存一个来源的最后顺序、总数、计数及四种原因计数。每批先付新状态
和临时列费用，再独立核顺序及数值，本批另付的临时费用实际释放后才一次提交候选状态。
内部历史AnalysisRunner可明确预付一条的工作空间；本owner保持这笔费用直到close，
单条计算复用它，多条仅另付不足部分，不能借共享账本中其他owner的余额抵账。
参考路径逐项使用Python浮点加法；NumPy路径按需加载独立数组核，不共享参考
数值计算。输入及返回快照归调用方，本层估算不包含其已有内存或整个进程RSS。
本模块不读写文件、不调用旧reader/解码器；close只释放本owner的实际RAM槽。
"""

# 冻结模型及候选复制只依赖标准库，数组依赖仅在明确选择且有贡献时加载。
from collections.abc import Mapping
from copy import copy
from dataclasses import dataclass
from enum import Enum
from math import isfinite
from types import MappingProxyType

from ..core.validation import require_identifier, require_text
from ..results.budget import ResourceBudget, _cleanup_owner, _release_owned_ram, _reserve_owned_ram
from ..results.errors import ResultClosedError
from .updates import LegacyDecodedUpdate, LegacyUpdateOrder


class LegacySkipReason(Enum):
    """提供者明确选择的一次跳过原因，不由累计器根据原值或质量推断。

    四个固定成员覆盖输入缺项、条件不成立、求值错误和非有限输入。
    枚举无可变状态；原因仅解释该提供者为何未给出有限贡献，不补造旧缓存事实。
    """

    MISSING_INPUT = "missing_input"
    CONDITION_FALSE = "condition_false"
    EVALUATION_ERROR = "evaluation_error"
    NONFINITE_INPUT = "nonfinite_input"


# 原因域固定，内部计数tuple和公开冻结映射都保持此声明顺序及全部零项。
_SKIP_REASONS = tuple(LegacySkipReason)


def _require_contribution(value: float | None, skip_reason: LegacySkipReason | None) -> None:
    """检查有限原生贡献与显式跳过原因互斥，不转换或修补数值。

    参数: value为原生有限float或None；skip_reason为固定枚举或None。
    返回: None；合法数值和显式跳过均保持原样。
    异常: TypeError为类型不符；ValueError为非有限数值或贡献/原因关系矛盾。
    """
    # 先限制明确的原因域；None贡献只能表示提供者已选择跳过，不能省略原因。
    if skip_reason is not None and not isinstance(skip_reason, LegacySkipReason):
        raise TypeError("skip_reason必须为LegacySkipReason或None")
    if value is None:
        if skip_reason is None:
            raise ValueError("无贡献时必须显式提供skip_reason")
        return
    # int和bool即使可转float也不能隐藏提供者采用的数值政策。
    if type(value) is not float:
        raise TypeError("贡献必须为原生float或None")
    if not isfinite(value):
        raise ValueError("贡献必须为有限float；非有限输入应由提供者显式跳过")
    if skip_reason is not None:
        raise ValueError("有限贡献不能同时携带skip_reason")


@dataclass(frozen=True)
class LegacySumContribution:
    """关联一次更新身份与提供者已求出的贡献，不保存新的信号缓存。

    update保留原模型对象；value是有限原生float，或与明确skip_reason配对的
    None。即使update.quality非零，有限贡献也不由本层自动否决。该对象由调用方
    提供，不证明旧表达式、触发门控、缺失处理或真实日志逐次出口已经接通。
    """

    update: LegacyDecodedUpdate  # 此次求值的原身份，引用保持不变。
    value: float | None  # 已计算一次的贡献，不再施加时间或单位倍率。
    skip_reason: LegacySkipReason | None = None  # 仅None贡献需要明确原因。

    def __post_init__(self) -> None:
        """验证真实更新模型及互斥的贡献/跳过结构。

        参数: 无，读取update、value和skip_reason。
        返回: None；不复制update或修改其原值、质量。
        异常: TypeError为非模型或数值/原因类型不符；ValueError为结构或有限性错误。
        """
        # 保留已验证的原更新引用，再独立核对贡献结构，不重造或改写求值身份。
        if not isinstance(self.update, LegacyDecodedUpdate):
            raise TypeError("update必须为LegacyDecodedUpdate")
        _require_contribution(self.value, self.skip_reason)


@dataclass(frozen=True)
class LegacySumSnapshot:
    """保存固定大小的未舍入累计事实，明确区分没有贡献与有效零和。

    evaluation_count包括跳过，contribution_count只数实际加法项；四键
    skip_counts复制冻结且始终含零项。没有求值和全部跳过分别以reason说明，
    只有曾接收有效贡献才给float总数。快照归调用方，可在累计器关闭后保留；
    不保存逐次列表，也不声称普通时间积分的覆盖率或旧整文件行为全等。
    """

    session_id: str  # 原会话身份。
    source: str  # 单一来源身份。
    legacy_policy: str  # 提供者显式声明的贡献及跳过政策文本。
    value: float | None  # 未舍入总数；没有有效贡献时为None。
    evaluation_count: int  # 所有已接受求值，包括跳过。
    contribution_count: int  # 实际有限贡献数量，包括值为0的项。
    skipped_count: int  # 显式跳过的求值数量。
    skip_counts: Mapping[LegacySkipReason, int]  # 固定四键的独立冻结映射。
    reason: str | None  # no_evaluations/all_skipped；有贡献时为None。

    def __post_init__(self) -> None:
        """核对有限计数关系与空结果原因，并冻结固定四键映射。

        参数: 无，读取所有快照字段。
        返回: None；skip_counts转换成新的MappingProxyType，其他事实不改写。
        异常: TypeError为字段类型不符；ValueError为计数、原因域或结果关系矛盾；
            MemoryError为固定小映射分配失败，不返回部分快照。
        """
        # 身份和政策仍须明确，合法的数值不能掩盖缺失的来源或政策声明。
        require_identifier(self.session_id, "session_id")
        require_identifier(self.source, "source")
        require_text(self.legacy_policy, "legacy_policy")
        # 三种计数分别非负，且求值数必须由贡献和跳过完整闭合，不能遗漏已接受项。
        for count in (self.evaluation_count, self.contribution_count, self.skipped_count):
            if type(count) is not int:
                raise TypeError("快照计数必须为原生非布尔int")
            if count < 0:
                raise ValueError("快照计数必须非负")
        if self.evaluation_count != self.contribution_count + self.skipped_count:
            raise ValueError("求值数必须等于贡献数加跳过数")
        # 固定键域不能由可变Mapping实现注入额外原因，仍独立复制调用方dict。
        if type(self.skip_counts) not in (dict, MappingProxyType):
            raise TypeError("skip_counts需要dict或MappingProxyType")
        if set(self.skip_counts) != set(_SKIP_REASONS):
            raise ValueError("skip_counts必须恰好包含四个LegacySkipReason")
        copied = {}
        for reason in _SKIP_REASONS:
            count = self.skip_counts[reason]
            if type(count) is not int:
                raise TypeError("跳过原因计数必须为原生非布尔int")
            if count < 0:
                raise ValueError("跳过原因计数必须非负")
            copied[reason] = count
        if sum(copied.values()) != self.skipped_count:
            raise ValueError("四种原因计数之和必须等于skipped_count")
        # 用实际贡献数区分未求值、全跳过与有贡献，不用总数的真假判断是否为空。
        expected_reason = None if self.contribution_count else (
            "no_evaluations" if self.evaluation_count == 0 else "all_skipped"
        )
        if self.reason != expected_reason:
            raise ValueError("快照reason与实际贡献数量不一致")
        # 有贡献时零和也是有限结果；没有贡献时必须保留None，不能补成正常0。
        if self.contribution_count:
            if type(self.value) is not float:
                raise TypeError("有贡献的快照需要原生float总数")
            if not isfinite(self.value):
                raise ValueError("快照总数必须有限")
        elif self.value is not None:
            raise ValueError("没有有效贡献时value必须为None")
        object.__setattr__(self, "skip_counts", MappingProxyType(copied))


def _sum_reference(carry: float, values: tuple[float, ...]) -> float:
    """以独立Python浮点逐项左折叠，发现任一中间溢出立即拒绝本批。

    参数: carry是此前有限总数；values是按原求值顺序选出的有限float tuple。
    返回: float；无舍入、补偿求和或块和重排的候选总数。
    异常: OverflowError为任一中间累计非有限；取消及内存异常原样传播。
    """
    candidate = carry
    try:
        # 每次加法承接前一项的真实浮点尾数；逐中间值检查，禁止靠后续抵消修复溢出。
        for value in values:
            candidate = candidate + value
            if not isfinite(candidate):
                raise OverflowError("legacy_sum中间累计非有限，整批拒绝")
        return candidate
    finally:
        # 异常traceback可能由调用方长期保留；不得经纯核参数保活本层选值tuple。
        values = None
        candidate = None


class LegacySumAccumulator:
    """拥有单来源有限累计状态和实际预算槽，不拥有调用方更新或共享账本。

    _state一次保存顺序器、总数、贡献数及四原因计数。候选顺序器用copy.copy
    复制，共享的旧状态tuple不可变；包括skip的全部记录仍检查会话和原序。
    _fixed_cost覆盖本层有限元数据及候选重叠；_workspace_cost可预付单条工作区，
    _batch_cost只覆盖本批超过预付容量的临时费用。三者之和为_held_cost。
    费用清理未完成时拒绝新消费，close可按同owner重试。
    """

    def __init__(self, budget: ResourceBudget, session_id: str, source: str, *,
                 legacy_policy: str, backend: str = "numpy", max_batch_rows: int = 64,
                 prepay_single: bool = False):
        """先安装责任槽、校验配置并预付费用，再建立空顺序及累计状态。

        参数: budget为借用共享账本；session_id/source为固定身份；legacy_policy
            是必填非空政策；backend为reference或numpy；max_batch_rows为正原生int；
            prepay_single为原生bool，True时本owner构造预付4352字节单条工作区，
            供内部历史AnalysisRunner在共享余额用尽时继续已有单条计算，不缓存贡献；
            默认False保原批行为，多条调用仍须先预约实际所需空间的不足部分。
        返回: 新累计器；初始无求值、无贡献，不把初始加法carry当正常结果。
        异常: TypeError/ValueError为配置不符；预算及取消原错传播。构造清理持续
            失败时，原异常的legacy_sum_cleanup_owner保留真实未返回owner。
        """
        if not isinstance(budget, ResourceBudget):
            raise TypeError("budget必须为ResourceBudget")
        # 首次外部预算回调前安装全部实际费用和关闭槽，避免未返回对象失去责任。
        self._budget = budget
        self._held_cost = self._fixed_cost = self._workspace_cost = self._batch_cost = 0
        self._closed = self._closing = False
        self._state = None
        self._session_id = self._source = self._legacy_policy = None
        self._backend = None
        self._max_batch_rows = 0
        try:
            # 先检查调用配置，避免无效来源、政策或块上限进入已付费的累计状态。
            require_identifier(session_id, "session_id")
            require_identifier(source, "source")
            require_text(legacy_policy, "legacy_policy")
            if type(backend) is not str or backend not in ("reference", "numpy"):
                raise ValueError("backend仅支持reference或numpy")
            if type(max_batch_rows) is not int:
                raise TypeError("max_batch_rows必须为正原生int")
            if max_batch_rows <= 0:
                raise ValueError("max_batch_rows必须为正原生int")
            if type(prepay_single) is not bool:
                raise TypeError("prepay_single必须为原生bool")
            # 文本计费按最多UTF-32字符及候选/快照引用余量，固定开销覆盖有限状态。
            cost = 16384 + 8 * (len(session_id) + len(source) + len(legacy_policy))
            _reserve_owned_ram(self, cost, "_fixed_cost")
            # 预约前已安装独立责任槽，预约成功后取消也由本未返回owner清理。
            # 4352沿用单条原公式4096+256，不减原估算，也不替其他owner付款。
            if prepay_single:
                _reserve_owned_ram(self, 4352, "_workspace_cost")
            self._session_id, self._source, self._legacy_policy = session_id, source, legacy_policy
            self._backend, self._max_batch_rows = backend, max_batch_rows
            self._state = (LegacyUpdateOrder(session_id, source), 0.0, 0, (0, 0, 0, 0))
        except BaseException as exc:
            _cleanup_owner(self, exc, "legacy_sum_cleanup_owner", "legacy累计构造")
            raise

    @property
    def closed(self) -> bool:
        """读取完全关闭事实；参数: 无；返回: bool；异常: 无。"""
        return self._closed

    def _ensure_open(self) -> None:
        """拒绝关闭或有待恢复费用的owner，防止新批覆盖旧责任槽。

        参数: 无。返回: None。异常: ResultClosedError为已关闭或正在清理。
        """
        if self._closed or self._closing:
            raise ResultClosedError("legacy累计器已关闭或正在清理")

    def _candidate(self, contributions: tuple[LegacySumContribution, ...]) -> tuple:
        """在已预付空间内生成独立候选，返回时不保留逐次值临时列。

        参数: contributions为本批借用tuple，长度已经检查。
        返回: tuple；新顺序器、候选总数、贡献数和四原因计数。
        异常: TypeError/ValueError为贡献或顺序错误；OverflowError为中间累计溢出；
            数组导入、分配或取消原样传播，原_state始终不被修改。
        """
        candidate_order = skips = selected = values = None
        try:
            # 只复制有限顺序状态，后续accept只改候选，保留整批失败时的原顺序事实。
            order, carry, contribution_count, previous_skips = self._state
            candidate_order = copy(order)
            skips = list(previous_skips)
            selected = []
            # 每项先核模型再推进候选，后续坏项不能让此前部分求值提前提交。
            for contribution in contributions:
                if not isinstance(contribution, LegacySumContribution):
                    raise TypeError("consume仅接受LegacySumContribution")
                # 即使整批全部跳过，原更新身份和求值顺序也必须完整推进及核对。
                candidate_order.accept(contribution.update)
                if contribution.value is None:
                    skips[_SKIP_REASONS.index(contribution.skip_reason)] += 1
                else:
                    selected.append(contribution.value)
            # 不添加跳过占位0；全skip保持原carry，尚无贡献时快照仍由计数判为None。
            if selected:
                values = tuple(selected)
                if self._backend == "reference":
                    carry = _sum_reference(carry, values)
                else:
                    from .sum_numpy import sum_numpy
                    carry = sum_numpy(carry, values)
            return candidate_order, carry, contribution_count + len(selected), tuple(skips)
        finally:
            # 先断开本层新建的候选、选值和原因容器；保留原输入和异常本身。
            # 否则失败traceback会在批费用释放后继续保活这些临时副本。
            candidate_order = skips = selected = values = None

    def _release_failed_batch(self, primary: BaseException) -> None:
        """有限重试本批实际费用，清理副错只附注原异常，不关闭正常累计状态。

        参数: primary为原校验、计算、预算或取消异常。
        返回: None；持续未释费用设置_closing，禁止覆盖该责任槽。
        异常: 清理错误只记notes；真正剩余费用由原异常携带的owner.close恢复。
        """
        # 至多重试两次已登记费用，不无限阻塞原错；剩余责任留给显式close恢复。
        for attempt in range(2):
            if not self._batch_cost:
                break
            try:
                _release_owned_ram(self, self._batch_cost, "_batch_cost")
            except BaseException as cleanup:
                primary.add_note(f"legacy批费用清理第{attempt + 1}次失败: {type(cleanup).__name__}")
        if self._batch_cost:
            self._closing = True

    def consume(self, contributions: tuple[LegacySumContribution, ...]) -> None:
        """整批核验并累计，临时差额实际释放成功后才一次安装全部候选事实。

        参数: contributions为精确tuple，长度不超过max_batch_rows；空tuple合法。
            已预付单条空间时仅预约超过该自有容量的差额；默认仍预约完整本批费用。
        返回: None；成功提交全部项，任何失败不推进原数值、计数或顺序。
        异常: TypeError/ValueError为类型、批上限、来源或顺序；OverflowError为累计
            非有限；ResultClosedError为关闭中。预算、导入、分配或取消原样传播并
            附legacy_sum_cleanup_owner。清理成功后普通失败可用合法后续批恢复。
        """
        self._ensure_open()
        candidate = None
        try:
            # 先限定真实有限容器和批上限；空批不建立候选，也不申请无用工作区。
            if type(contributions) is not tuple:
                raise TypeError("consume需要精确tuple")
            if len(contributions) > self._max_batch_rows:
                raise ValueError("本批超过max_batch_rows")
            if not contributions:
                return
            # 每项256覆盖选值list/tuple、seed/累计/有限性数组及验证临时量；固定
            # 4096覆盖顺序器和四计数候选。输入update.values不复制也不深遍历计费。
            extra = max(0, 4096 + len(contributions) * 256 - self._workspace_cost)
            if extra:
                _reserve_owned_ram(self, extra, "_batch_cost")
            candidate = self._candidate(contributions)
            # _candidate已退出，所有逐次临时列已丢弃；这里只保固定候选与旧状态重叠。
            _release_owned_ram(self, self._batch_cost, "_batch_cost")
        except BaseException as exc:
            # 释放预算前丢弃尚未提交的固定候选，异常frame不能继续替它保留引用。
            candidate = None
            self._release_failed_batch(exc)
            exc.legacy_sum_cleanup_owner = self
            raise
        # 提交前不再调用预算或数值代码；候选分配与临时费用收尾均已完成。
        self._state = candidate

    def snapshot(self) -> LegacySumSnapshot:
        """返回调用方拥有的独立冻结快照，不舍入、不封口或证明来源EOF。

        参数: 无。返回: LegacySumSnapshot；四原因键始终存在，计数为0也不省略。
        异常: ResultClosedError为关闭中；分配或取消原样传播并附真实恢复owner。
        """
        self._ensure_open()
        try:
            order, total, contribution_count, skips = self._state
            # 固定原因域每次都含全部零项，返回的小映射独立于内部计数tuple。
            counts = dict(zip(_SKIP_REASONS, skips))
            # 空结果按求值及贡献数分类，已有累计不会被后来全跳过的批次清空。
            reason = None if contribution_count else (
                "no_evaluations" if order.count == 0 else "all_skipped"
            )
            return LegacySumSnapshot(
                self._session_id, self._source, self._legacy_policy,
                total if contribution_count else None, order.count, contribution_count,
                order.count - contribution_count, counts, reason,
            )
        except BaseException as exc:
            exc.legacy_sum_cleanup_owner = self
            raise

    def close(self) -> None:
        """释放本累计器实际费用，可在释放前后取消或持续失败后重试同一owner。

        参数: 无。返回: None；只有所有自有槽实际归零才closed=True，重复close无操作。
        异常: 原预算或取消异常保持，附legacy_sum_cleanup_owner；半关闭时拒绝继续
            consume/snapshot，不释放调用方借款，不使已返回快照失效。
        """
        # 只有完全关闭才幂等返回，避免重复close再次触发预算回调或抵销借款。
        if self._closed:
            return
        self._closing = True
        # 本层无FD或子owner；先丢自有状态引用，释放后取消也不留下未计费的新状态。
        self._state = None
        try:
            _release_owned_ram(self, self._batch_cost, "_batch_cost")
            _release_owned_ram(self, self._workspace_cost, "_workspace_cost")
            _release_owned_ram(self, self._fixed_cost, "_fixed_cost")
        except BaseException as exc:
            exc.legacy_sum_cleanup_owner = self
            raise
        self._session_id = self._source = self._legacy_policy = None
        self._closed = True
