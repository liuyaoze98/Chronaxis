"""在一次完整组提交的两侧构造有预算的真实条件证据。

调用方先对所有条件prepare，捕获同一整数ns的更新前点，再统一提交一次完整组，
逐个complete查询连续后态和真实点，调用独立参考或NumPy三视图内核。
只读state revision证明两段之间只有目标提交，定时器允许没有提交；不执行state.apply。
输出须close，保存ConditionTick与当前点依赖的完整SourceRef，不代表事件全部原始行。
固定槽、workspace及refs深元数据先申请；三份表达式查询分别拥有已验预算。
最终输出不保留编译树或HistorySample。无文件/旧链操作、全量时间轴或检测器推进。
账本沿用单线程约束；外部另存tick/refs自行负责生命周期，不代表整进程RSS。
构造清理失败保留原异常，持续失败由condition_evidence_queries_cleanup_owner恢复
本次自有固定槽；借用ExpressionQueries/state不由该恢复对象关闭。
"""

# 共享校验/所有权协议，不共享两个独立证据及表达式数值核。
import numpy as np
from ..core.condition_evidence import condition_ticks_reference, condition_ticks_numpy
from ..core.expression import CompiledExpression
from ..core.models import Interval
from ..core.types import SignalDType
from ..results.errors import AnalysisError, ResultClosedError
from ..results.spool import _cleanup_owner
from ..timebase.conversion import require_int64_ns
from .expressions import ExpressionQueries
from .history import _metadata_bytes
# 复用已验常量空间双向登记，避免完成结果高峰留下哈希容量。
from .temporal_buffer import _BatchRegistry


class PreparedConditionEvidence:
    """保存一个条件的旧点和输出，生命周期为预备→完成/失败→关闭。

    每表达式至多一个预备槽；完成后释放槽，输出仍保有独立预算。
    complete失败不回滚state且禁止再次完成；close始终负责自有资源。
    私有链指针由登记器维护，公开状态/输出只读。
    """

    def __init__(self, owner, cost, slot, time_ns, revision, before, axis):
        """接收已申请workspace和旧点，不复制数组或编译树。

        参数: owner管理者；cost字节；slot登记序号；time_ns原生ns；revision旧版本；
            before为ExpressionResult，axis为一点tuple/int64列。
        返回: None；初始化实例状态。异常: 分配失败由prepare清理。
        """
        # 三查询字段先置完整空壳，局部构造失败不建立登记归属。
        self._owner, self._cost, self._slot = owner, cost, slot
        self._time, self._revision, self._axis = time_ns, revision, axis
        self._before, self._continuous, self._point = before, None, None
        self._ticks, self._refs = None, None
        self._binding_identity, self._compiled_identity = before.binding_identity, before.compiled_identity
        self._closed, self._completed, self._failed = False, False, False
        self._registry = self._previous = self._next = None

    def _ensure_open(self):
        """拒绝释放后使用。参数: 无。返回: None。异常: ResultClosedError。"""
        if self._closed:
            raise ResultClosedError('预备条件证据已关闭')

    @property
    def closed(self):
        """读取关闭状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    @property
    def failed(self):
        """读取完成失败状态。参数: 无。返回: bool。异常: 无。"""
        return self._failed

    @property
    def completed(self):
        """读取完成状态。参数: 无。返回: bool。异常: 无。"""
        return self._completed

    @property
    def time_ns(self):
        """读取目标时间。参数: 无。返回: 原生int ns。异常: ResultClosedError。"""
        self._ensure_open()
        return self._time

    @property
    def ticks(self):
        """读取一点证据。参数: 无。返回: ConditionTick tuple。异常: 关闭/未完成。"""
        self._ensure_open()
        # 未完成必须与合法空批区分，不能用空tuple掩盖失败。
        if not self._completed:
            raise AnalysisError('条件证据尚未完成')
        return self._ticks

    @property
    def source_refs(self):
        """读取当前点位置。参数: 无。返回: SourceRef tuple。异常: 关闭/未完成。"""
        self._ensure_open()
        if not self._completed:
            raise AnalysisError('条件证据尚未完成')
        return self._refs

    @property
    def binding_identity(self):
        """读取实际绑定身份。参数: 无。返回: SHA文本。异常: ResultClosedError。"""
        self._ensure_open()
        return self._binding_identity

    @property
    def compiled_identity(self):
        """读取编译身份。参数: 无。返回: SHA文本。异常: ResultClosedError。"""
        self._ensure_open()
        return self._compiled_identity

    def _close_views(self):
        """关闭三快照，失败句柄留在字段供close重试。

        参数: 无。返回: None，成功字段清空。异常: 查询关闭错误原样传播。
        """
        # 只遍历固定生命周期字段，当前两视图先释放，旧点最后释放。
        for name in ('_continuous', '_point', '_before'):
            result = getattr(self, name)
            if result is not None:
                result.close()
                setattr(self, name, None)

    def _charge_refs(self, amount):
        """保存完整来源位置前增加独立持有量。

        参数: amount非负bytes。返回: None，成功金额计入_cost。
        异常: 预算拒绝/取消传播；已记账的返回取消仍保有申请直到close。
        """
        # 无refs不增加账本调用；单线程快照覆盖reserve返回取消。
        if not amount:
            return
        budget = self._owner._budget
        before = budget.ram_bytes
        try:
            budget.reserve_ram(amount)
        finally:
            if budget.ram_bytes == before + amount:
                self._cost += amount

    def complete(self):
        """核对唯一目标提交后求值并形成真实三视图证据。

        参数: 无；调用方可已提交一次同刻完整组，定时器可不提交。
        返回: None，之后通过ticks/source_refs读取快照。
        异常: 版本/预算/求值/取消错误传播，转failed并禁止再完成；不回滚state，仍须close。
        """
        self._ensure_open()
        if self._failed or self._completed:
            raise AnalysisError('条件证据不能重复完成或从失败恢复')
        try:
            owner = self._owner
            owner._ensure_open()
            state = owner._queries._holds._state
            # 零次是定时器，一次必须正好是目标；末时间相同不能掩盖中间提交。
            if state.revision != self._revision:
                if state.revision != self._revision + 1 or state.last_time_ns != self._time:
                    raise ValueError('预备条件两段之间只能提交一次目标完整组')
            compiled = owner._queries._expressions[self._slot]
            query = owner._queries.query_reference if owner._backend == 'reference' else owner._queries.query_numpy
            # 每次返回立即归入字段，部分失败不丢查询句柄。
            self._continuous = query(compiled, self._axis, point=False)
            self._point = query(compiled, self._axis, point=True)
            actual = bool(self._point.actual_update[0])
            # 样本本身invalid才是实际无效；TTL失效不能冒充真实新更新。
            invalid = any(sample.time_ns == self._time and not sample.value.valid for sample in self._point.samples)
            holds = owner._queries._holds
            source_end = any(holds._bounds[holds._definitions[name].source][1] == self._time
                             for name in compiled.dependencies)
            terminal = self._time == owner._end
            # 深成本包含CSV子类完整文件/物理行位置，先计账再建立refs tuple。
            ref_cost = sum(1024 + 16 * _metadata_bytes(sample.source_ref) for sample in self._point.samples)
            self._charge_refs(ref_cost)
            refs = tuple(sample.source_ref for sample in self._point.samples)
            if owner._backend == 'reference':
                ticks = condition_ticks_reference(self._axis, self._before.rows, self._continuous.rows,
                                                  self._point.rows, (actual,), (invalid,), (source_end,), (terminal,))
            else:
                # 四标志均为形状(1,)bool，证据计算使用独立NumPy列核，不回退标量。
                flags = tuple(np.array((value,), dtype='bool') for value in (actual, invalid, source_end, terminal))
                ticks = condition_ticks_numpy(self._axis, self._before.arrays, self._continuous.arrays,
                                              self._point.arrays, *flags)
            # 借用查询全部关闭后才交付，最终只保留独立计账的tick/refs。
            self._close_views()
            self._ticks, self._refs, self._completed = ticks, refs, True
            owner._pending[self._slot] = None
            owner._completed_times[self._slot] = self._time
        except BaseException:
            # state可能前移，失败不声称可重做；该已交付预备对象继续拥有句柄。
            self._failed = True
            raise

    def _discard(self):
        """移除链成员与预备槽，丢弃已释放的自有引用。

        参数: 无。返回: None，结果关闭。
        异常: 脱链错误传播，finally仍关闭；owner重试可清理残留链。
        """
        owner = self._owner
        try:
            owner._results.discard(self)
        finally:
            # 只移除仍属于自己的槽，不覆盖后来创建的同条件结果。
            if owner._pending[self._slot] is self:
                owner._pending[self._slot] = None
            self._closed, self._cost = True, 0
            self._before = self._continuous = self._point = self._axis = self._ticks = self._refs = None
            self._owner = self._binding_identity = self._compiled_identity = None

    def close(self):
        """释放三查询与workspace/refs，保留上游。

        参数: 无。返回: None，幂等。
        异常: 查询/预算关闭错误传播，未扣账可重试，已扣账取消最小收尾。
        """
        if self._closed:
            return
        self._close_views()
        budget, cost = self._owner._budget, self._cost
        before, released = budget.ram_bytes, False
        try:
            budget.release_ram(cost)
            released = True
        finally:
            if released or budget.ram_bytes == before - cost:
                self._discard()


class ConditionEvidenceQueries:
    """借用真实表达式查询，固定槽和链式结果拥有独立预算。

    每表达式至多一个未完成结果，已完成输出按自身成本可保留到close。
    编译树由上游拥有，本层只保存整数登记序号，不延长已释放编译元数据寿命。
    """

    def __init__(self, expressions: ExpressionQueries, *, backend='numpy', observation=None):
        """先申请固定槽/游标空间，再取得上游登记序号。

        参数: expressions打开的真实ExpressionQueries；backend为reference/numpy；
            observation为原请求范围内的实际Interval，None沿用原HoldContext.domain。
        返回: 新owner，不关闭上游或提交state。
        异常: 类型/关闭/预算/取消原错误传播；部分构造关闭自有申请，持续清理失败
            从原异常的condition_evidence_queries_cleanup_owner恢复close，不关闭上游。
        """
        if not isinstance(expressions, ExpressionQueries):
            raise TypeError('条件证据需要真实ExpressionQueries')
        expressions._ensure_open()
        if type(backend) is not str or backend not in ('reference', 'numpy'):
            raise ValueError('条件证据后端必须为reference或numpy')
        # 实际范围只约束本查询的推进，不复制HoldContext或改变真实绑定身份。
        domain = expressions._holds._context.domain
        if observation is not None:
            if not isinstance(observation, Interval):
                raise TypeError('条件证据实际观测范围需要Interval或None')
            if observation.start_ns < domain.start_ns or observation.end_ns > domain.end_ns:
                raise ValueError('条件证据实际观测范围必须完全位于原domain内')
            domain = observation
        # 上述类型和范围拒绝先于本owner的任何预算申请，零长度真实范围合法。
        fixed = 65536 + 512 * len(expressions._expressions)
        self._budget, self._fixed_cost, self._closed = expressions._budget, 0, False
        self._queries = self._slots = self._pending = self._completed_times = self._results = None
        self._backend, self._start, self._end = backend, None, None
        before = self._budget.ram_bytes
        try:
            self._budget.reserve_ram(fixed)
            self._fixed_cost = fixed
            # 固定整数槽不保留编译对象，重复登记对象沿用一个槽。
            self._queries = expressions
            self._slots = {id(item): index for index, item in enumerate(expressions._expressions)}
            self._pending = dict.fromkeys(self._slots.values())
            self._completed_times = dict.fromkeys(self._slots.values())
            self._results = _BatchRegistry()
            self._start, self._end = domain.start_ns, domain.end_ns
        except BaseException as exc:
            # 本次只有一笔直接固定预约；实际已入账而返回取消时先保有这笔自有费用。
            if self._fixed_cost == 0 and self._budget.ram_bytes == before + fixed:
                self._fixed_cost = fixed
            # 原构造错误优先，清理取消记notes；持续失败交出真实未返回owner供上层接管。
            _cleanup_owner(self, exc, 'condition_evidence_queries_cleanup_owner', '条件证据查询构造')
            raise

    @property
    def closed(self):
        """读取关闭状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    def _ensure_open(self):
        """检查自身及上游。参数: 无。返回: None。异常: ResultClosedError。"""
        if self._closed:
            raise ResultClosedError('条件证据查询已关闭')
        self._queries._ensure_open()

    def _construct(self, cost, slot, time_ns, revision, before, axis):
        """仅构造局部结果，不安装槽或结果链。

        参数: cost已申请bytes，其余为prepare捕获的事实/旧点。
        返回: PreparedConditionEvidence。异常: 构造/返回取消由prepare清理。
        """
        return PreparedConditionEvidence(self, cost, slot, time_ns, revision, before, axis)

    def prepare(self, compiled, time_ns: int) -> PreparedConditionEvidence:
        """在目标组提交前捕获同刻旧点并返回有预算预备结果。

        参数: compiled为登记BOOL对象；time_ns原生int ns，域内且晚于已提交组。
        返回: 须complete/close对象；可先为所有条件prepare再统一state.apply。
        异常: 未登记/非BOOL/时间回退/槽占用/预算/取消传播，失败不改变state或旧结果。
        """
        self._ensure_open()
        if not isinstance(compiled, CompiledExpression) or compiled.root.dtype is not SignalDType.BOOL:
            raise TypeError('条件证据只接受已编译BOOL条件')
        slot = self._slots.get(id(compiled))
        if slot is None or self._queries._expressions[slot] is not compiled:
            raise ValueError('条件不属于当前登记对象')
        if type(time_ns) is not int:
            raise TypeError('条件证据时间需要原生int纳秒')
        require_int64_ns(time_ns)
        state = self._queries._holds._state
        last = self._completed_times[slot]
        # 旧点在真实提交前捕获，不以t-1或已提交当前点冒充before。
        if (not self._start <= time_ns <= self._end or state.last_time_ns is not None and time_ns <= state.last_time_ns
                or last is not None and time_ns <= last):
            raise ValueError('证据时间须域内且晚于已提交组和已完成点')
        if self._pending[slot] is not None:
            raise ValueError('当前条件已有未完成预备结果')
        cost = 65536 + 1024 * len(compiled.dependencies)
        initial, reserved, old, result = self._budget.ram_bytes, False, None, None
        try:
            # workspace先于一点轴/旧点/结果；表达式查询另有独立申请。
            self._budget.reserve_ram(cost)
            reserved = True
            axis = (time_ns,) if self._backend == 'reference' else np.array((time_ns,), dtype='int64')
            if self._backend == 'numpy':
                axis.flags.writeable = False
            query = self._queries.query_reference if self._backend == 'reference' else self._queries.query_numpy
            old = query(compiled, axis, point=True)
            result = self._construct(cost, slot, time_ns, state.revision, old, axis)
            self._pending[slot] = result
            self._results.add(result)
            return result
        except BaseException:
            # 仅撤销当前对象，旧点独立关闭，workspace由本边界唯一抵销。
            try:
                if result is not None:
                    result._discard()
            finally:
                try:
                    if old is not None:
                        old.close()
                finally:
                    if reserved or self._budget.ram_bytes == initial + cost:
                        self._budget.release_ram(cost)
            raise

    def close(self):
        """关闭自有预备/完成结果与固定槽，保留调用方上游。

        参数: 无。返回: None，幂等。
        异常: 子结果/预算关闭错误传播，已释放固定空间的取消最小收尾。
        """
        if self._closed:
            return
        while self._results:
            result = next(iter(self._results))
            result.close()
            self._results.discard(result)
        cost, initial, released = self._fixed_cost, self._budget.ram_bytes, False
        try:
            self._budget.release_ram(cost)
            released = True
        finally:
            if released or self._budget.ram_bytes == initial - cost:
                # 仅丢借用引用，不关闭表达式/state/历史或保留已释放固定槽。
                self._closed, self._fixed_cost = True, 0
                self._queries = self._slots = self._pending = self._completed_times = self._results = None
