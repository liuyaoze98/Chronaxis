"""从已封存的新解码历史逐段计算一个窗口的表达式视图。

输入为实际运行绑定、原保持上下文、已编译表达式及域内Interval，坐标为整数纳秒。
先校验原历史身份，再打开独立状态与完整组游标；窗口前组只建立种子。
每步按真实更新、依赖TTL、来源终点或窗口末端拆分，返回须close的点/连续视图帧。
参考与NumPy分别调用既有独立表达式核，不物化完整样本、时间轴或帧列表。
资源属于本回读对象；原历史、调用方lease和原state借用，不重读旧报文/DBC。
提前停止不提供本次全文件EOF证明；运行绑定已有完整校验证据与部分回读分开。
新层保守预算包含前瞻、种子、查询和输出，不能代表外部留存量或进程RSS。
"""

# 只组合已有封存历史、保持、表达式和精确边界，不实现新的数值或指标算法。
import numpy as np
from ..core.decoded_binding import DecodedBindings
from ..core.expression import CompiledExpression
from ..core.models import Interval
from ..results.errors import ResultClosedError
from .bindings import _fingerprint
from .boundaries import BoundaryQueries
from .expressions import ExpressionQueries
from .history import DecodedHistoryStore, _metadata_bytes
from .hold import HoldContext, HoldQueries
from .state import LatestSignalState
from .temporal_buffer import _BatchRegistry


class WindowReplayFrame:
    """拥有一个时刻的点视图、可选连续视图及本步workspace。

    连续值适用于[time_ns,end_ns)，末点帧的两端相等且continuous_result为None。
    点视图可能是保持值，只有ExpressionResult.actual_update才表示真实依赖更新。
    两个子结果和链指针的预算在本帧close后释放，关闭过程中拒绝读取半关闭结果。
    """

    def __init__(self, owner, cost, time_ns, end_ns, point, continuous):
        """接收已计账的表达式结果，暂不安装登记。

        参数: owner为回读者；cost为本步bytes；time_ns/end_ns为整数ns；
            point为点ExpressionResult，continuous为连续结果或None。
        返回: 新帧。异常: 构造失败由调用方回收子结果和workspace。
        """
        # 本帧不复制数组或原样本；链指针及坐标包含在本步固定workspace内。
        self._owner, self._cost, self._closed, self._closing = owner, cost, False, False
        self._time, self._end, self._point, self._continuous = time_ns, end_ns, point, continuous
        self._registry = self._previous = self._next = None

    def _ensure_open(self):
        """拒绝释放或部分关闭后的读取。

        参数: 无。返回: None。异常: ResultClosedError。
        """
        if self._closed or self._closing:
            raise ResultClosedError('窗口回读帧已关闭或正在关闭')

    @property
    def closed(self):
        """读取资源完成状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    @property
    def time_ns(self):
        """读取当前点坐标。参数: 无。返回: int纳秒。异常: 关闭时拒绝。"""
        self._ensure_open()
        return self._time

    @property
    def end_ns(self):
        """读取连续区间排除的右端。参数: 无。返回: int纳秒。异常: 关闭时拒绝。"""
        self._ensure_open()
        return self._end

    @property
    def point_result(self):
        """读取当前点表达式结果，保留actual_update和原样本。

        参数: 无。返回: ExpressionResult。异常: 关闭时拒绝。
        """
        self._ensure_open()
        return self._point

    @property
    def continuous_result(self):
        """读取左闭右开区间的值，末点没有连续面积。

        参数: 无。返回: ExpressionResult或None。异常: 关闭时拒绝。
        """
        self._ensure_open()
        return self._continuous

    def _discard(self):
        """解除完整或部分链登记，不再次扣账。

        参数: 无。返回: None。异常: 登记取消仍在finally关闭字段。
        """
        try:
            if self._registry is not None:
                self._registry.discard(self)
        finally:
            # 预算已抵销时不能保留可再次释放的金额或大输出引用。
            self._closed, self._cost = True, 0
            self._owner = self._point = self._continuous = self._time = self._end = None

    def close(self):
        """关闭子结果后释放本步申请，取消前可重试、实际扣账后最小关闭。

        参数: 无。返回: None，幂等。异常: 子关闭/预算/取消传播。
        """
        if self._closed:
            return
        self._closing = True
        # 每个子结果完成才清字段，保留尚未成功关闭的句柄供下一次close。
        for name in ('_continuous', '_point'):
            child = getattr(self, name)
            if child is not None:
                child.close()
                setattr(self, name, None)
        budget, cost = self._owner._budget, self._cost
        before, released = budget.ram_bytes, False
        try:
            budget.release_ram(cost)
            released = True
        finally:
            if released or budget.ram_bytes == before - cost:
                self._discard()


class HistoricalWindowReplay:
    """以独立种子状态回读一个有限窗口，原调用方状态不变。

    _front由完整组游标持有且计账，消费以后才请求下一组；不另存历史列表。
    输出帧登记在固定头指针链中，先前帧在后续失败后仍可读取。
    单线程推进失败不可重试；close可重试并关闭自有查询、状态和游标。
    迭代完成仍须close，以便调用方保留最后帧；完成窗口不等于全文件重放到EOF。
    """

    def __init__(self, history: DecodedHistoryStore, context: HoldContext, bindings: DecodedBindings,
                 compiled: CompiledExpression, interval: Interval, *, backend='numpy'):
        """先预留元数据，再核对当前历史与绑定并创建独立回读资源。

        参数: history为sealed新历史；context为原域与来源EOF事实；bindings为实际绑定；
            compiled为该绑定的表达式；interval为域内含点端的窗口；backend为reference/numpy。
        返回: 尚未读入种子的新回读者。
        异常: 类型/域/来源身份/预算/构造取消；保留原异常，不关闭借用历史。
            持续清理失败时，从异常的window_replay_cleanup_owner取得自有恢复句柄。
        """
        if (not isinstance(history, DecodedHistoryStore) or not isinstance(context, HoldContext)
                or not isinstance(bindings, DecodedBindings) or not isinstance(compiled, CompiledExpression)
                or not isinstance(interval, Interval)):
            raise TypeError('窗口回读需要封存历史、保持上下文、实际绑定、编译表达式和Interval')
        history._check('sealed')
        if backend not in ('reference', 'numpy'):
            raise ValueError('窗口回读backend需要reference或numpy')
        if not context.domain.start_ns <= interval.start_ns <= interval.end_ns <= context.domain.end_ns:
            raise ValueError('窗口回读范围必须位于原绑定domain内')
        # 元数据估算只遍历已有冻结树；临时指纹容器和子owner另在申请之后创建。
        cost = 65536 + len(bindings.sources) * 8192 + 16 * _metadata_bytes((context, interval, bindings.sources))
        self._budget, self._fixed_cost = history.budget, 0
        self._closed = self._closing = self._failed = self._done = self._seeded = False
        self._history = self._compiled = self._interval = self._results = None
        self._state = self._holds = self._expressions = self._boundaries = self._groups = None
        self._front = None
        self._cursor, self._backend = interval.start_ns, backend
        before = self._budget.ram_bytes
        try:
            self._budget.reserve_ram(cost)
            self._fixed_cost = cost
            self._history, self._compiled, self._interval = history, compiled, interval
            self._results = _BatchRegistry()
            # 匹配实际历史而非同名来源；指纹临时树已由本固定申请覆盖。
            if {proof.source for proof in bindings.sources} != set(history.validators):
                raise ValueError('窗口运行绑定与当前历史来源不同')
            for proof in bindings.sources:
                validator = history.validators[proof.source]
                completion = history.source_completions[proof.source]
                given_completion = next((item for item in context.completions if item.source == proof.source), None)
                # 封存SHA只证明历史字节；外来观测/EOF及最终批进度仍须对照实际typed事实。
                # 完成事实缺源时以None拒绝；不创建全源缓存，也不把最后批计数当全源总量。
                if (proof.history_sha256 != history.hashes[proof.source].hexdigest()
                        or [proof.progress_count, proof.sample_count] != history.counts[proof.source]
                        or proof.description_sha256 != _fingerprint(validator.description)
                        or proof.request_sha256 != _fingerprint(validator.request)
                        or proof.session_id != completion.session_id
                        or proof.projected_aliases != validator.request.signal_names
                        or proof.observation_start_ns != validator.description.observation_start_ns
                        or proof.observation_end_ns != completion.observed_end_ns
                        or proof.source_eof != completion.source_eof
                        or given_completion != completion):
                    raise ValueError('窗口运行绑定与当前封存历史身份不同')
            # 当前固定费已覆盖真实投影元数据；回读只持实际样本别名，不补未读取声明的空状态。
            from dataclasses import replace
            from ..core.enum_codes import code_dependencies
            codes = code_dependencies(compiled.root)
            definitions = tuple(replace(item, capture_code=True) if item.name in codes else item
                                for item in bindings.projected_signals)
            self._state = LatestSignalState(self._budget, definitions, context.session_id)
            self._holds = HoldQueries(self._state, context)
            self._expressions = ExpressionQueries(self._holds, bindings, (compiled,))
            self._boundaries = BoundaryQueries(self._expressions)
            # 首步成功预留workspace后才打开组游标及真实FD，构造不读取任何历史记录。
        except BaseException as exc:
            # 尚未赋值的失败子构造通过原异常交出句柄，父owner继续持有它的关闭责任。
            for name, recovery_name in (('_state', 'state_cleanup_owner'),
                                        ('_holds', 'hold_queries_cleanup_owner'),
                                        ('_expressions', 'expression_queries_cleanup_owner'),
                                        ('_boundaries', 'boundary_queries_cleanup_owner')):
                child = getattr(exc, recovery_name, None)
                if child is not None:
                    setattr(self, name, child)
            if self._fixed_cost == 0 and self._budget.ram_bytes == before + cost:
                self._fixed_cost = cost
            try:
                self.close()
            except BaseException as cleanup:
                exc.add_note(f'窗口回读初始化清理附加失败: {type(cleanup).__name__}')
                # 瞬时取消只重试一次；持续失败仍保留所有未关闭子对象，不能丢失自有费用。
                if not self._closed:
                    try:
                        self.close()
                    except BaseException as retry:
                        exc.add_note(f'窗口回读初始化清理重试失败: {type(retry).__name__}')
                        if not self._closed:
                            exc.window_replay_cleanup_owner = self
                            exc.add_note('释放恢复后调用window_replay_cleanup_owner.close()')
            raise

    @property
    def closed(self):
        """读取owner是否完全关闭。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    @property
    def failed(self):
        """读取推进失败状态。参数: 无。返回: bool。异常: 无。"""
        return self._failed

    def _ensure_open(self):
        """检查owner及借用历史仍可用，不允许故障后继续推进。

        参数: 无。返回: None。异常: ResultClosedError。
        """
        if self._closed or self._closing or self._failed:
            raise ResultClosedError('窗口回读已关闭、正在关闭或推进失败')
        self._history._check('sealed')

    def __iter__(self):
        """返回当前独立回读者。参数: 无。返回: self。异常: 无。"""
        return self

    def _seed(self):
        """逐个消费窗口前完整组，保留第一个未消费前瞻。

        参数: 无。返回: None。异常: 真实历史/原子state错误传播，外层标失败。
        """
        self._groups = self._history.iter_groups()
        self._front = next(self._groups, None)
        while self._front is not None and self._front.time_ns < self._interval.start_ns:
            self._state.apply(self._front)
            # 上组已经提交state后才推进，原组预算不会早于消费释放。
            self._front = next(self._groups, None)
        self._seeded = True

    def _query(self, *, point):
        """在已预留本步空间内调用原独立后端查询。

        参数: point为是否点视图。返回: 须close的ExpressionResult。
        异常: 原保持/表达式/预算错误传播；数组shape=(1,), int64纳秒。
        """
        if self._backend == 'reference':
            return self._expressions.query_reference(self._compiled, (self._cursor,), point=point)
        return self._expressions.query_numpy(self._compiled, np.array([self._cursor], dtype=np.int64), point=point)

    def __next__(self):
        """先预算再读种子或消费更新，返回一个准确区间及当前点。

        参数: 无。返回: WindowReplayFrame；末点连续视图为None。
        异常: StopIteration表示窗口完成；任何推进故障标failed，先前输出保持。
        """
        self._ensure_open()
        if self._done:
            raise StopIteration
        cost = 65536 + 32768 * len(self._state.definitions)
        before, owned, frame = self._budget.ram_bytes, False, None
        point = continuous = None
        try:
            self._budget.reserve_ram(cost)
            owned = True
            if not self._seeded:
                self._seed()
            if self._front is not None and self._front.time_ns == self._cursor:
                self._state.apply(self._front)
                self._front = next(self._groups, None)
            right = self._interval.end_ns
            if self._cursor < right:
                boundary = self._boundaries.query_next(self._compiled, after_ns=self._cursor,
                    next_group_ns=None if self._front is None else self._front.time_ns)
                try:
                    right = min(right, boundary.time_ns)
                finally:
                    boundary.close()
            # 种子保持值也返回点视图，真实样本计数必须使用actual_update而非帧数。
            point = self._query(point=True)
            if self._cursor < right:
                continuous = self._query(point=False)
            frame = WindowReplayFrame(self, cost, self._cursor, right, point, continuous)
            owned = False
            self._results.add(frame)
            if self._cursor == self._interval.end_ns:
                self._done = True
            else:
                self._cursor = right
            return frame
        except BaseException:
            self._failed = True
            # 清理只作用于本次未交付结果，先前帧及调用方资源不会被撤销。
            if frame is not None:
                frame.close()
            else:
                try:
                    if continuous is not None:
                        continuous.close()
                finally:
                    if point is not None:
                        point.close()
            raise
        finally:
            # 已成功reserve后的返回取消也计入本步清理，未成功不会抵销其他owner。
            if owned or frame is None and self._budget.ram_bytes == before + cost:
                self._budget.release_ram(cost)

    def close(self):
        """按资源依赖关闭自有帧/查询/状态/游标，保留借用历史与原state。

        参数: 无。返回: None，幂等。异常: 子关闭/预算取消，保留尚未完成句柄供重试。
        """
        if self._closed:
            return
        self._closing = True
        while self._results:
            frame = next(iter(self._results))
            frame.close()
            self._results.discard(frame)
        # 先关闭输出和查询，再释放种子状态与前瞻；每个完成以后才清本owner字段。
        for name in ('_boundaries', '_expressions', '_holds', '_state', '_groups'):
            child = getattr(self, name)
            if child is not None:
                child.close()
                setattr(self, name, None)
        cost, before, released = self._fixed_cost, self._budget.ram_bytes, False
        try:
            self._budget.release_ram(cost)
            released = True
        finally:
            if released or self._budget.ram_bytes == before - cost:
                self._closed, self._fixed_cost = True, 0
                self._front = self._results = self._history = self._compiled = self._interval = None
