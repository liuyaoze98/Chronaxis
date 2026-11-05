"""把一个有限窗口的历史回读装成有预算的指标输入块。

输入为封存的新解码历史、原保持上下文、实际绑定、表达式及CalculationDefinition。
支持无选择条件的时间与样本口径输入；每块最多batch_intervals个正区间。
每块的CalculationSeries可交给既有独立参考或NumPy指标核；本模块不归约整个窗口。
相邻块共享边界点，但半开区间不重叠；终点点值不增加面积或样本。
NumPy表达式仍执行原数组核，装箱循环只恢复冻结数值、质量和完整来源定位。
构造和本块空间先申请，至多保留一个回读前瞻帧；不保存完整轴或块列表。
输出块各自拥有预算，close可重试；借用历史、原state和lease不由本对象关闭。
失败后禁止推进，旧块仍独立可读。文件读取只由新历史回读执行，不读取旧报文。
可显式给出原context.domain内已核实的observation，仅裁剪计算实际域，不修改原
context、绑定或请求。默认None兼容原domain及原预算，本身不证明实际观测范围。
"""

# 只组合已有协议及回读，不复制原指标算法或改变数值后端。
from ..core.moments import MOMENTS
from ..core.quantiles import SAMPLE_QUANTILES
from ..core.decoded_binding import DecodedBindings
from ..core.expression import CompiledExpression
from ..core.calculations import CalculationSeries, CalculationDefinition
from ..core.calculations_memory_reference import require_calculation_plan
from ..core.models import Interval
from ..core.numeric import ScalarValue
from ..core.types import QualityFlag as Q, SignalDType as D
from ..results.errors import ResultClosedError
from .history import DecodedHistoryStore, _metadata_bytes
from .hold import HoldContext
from .temporal_buffer import _BatchRegistry
from .window_replay import HistoricalWindowReplay


def _calculation_observation(context, observation):
    """解析计算观测范围，只返回已有Interval引用，不改保持上下文或输入身份。

    参数: context为原HoldContext；observation为其域内Interval或兼容默认None。
    返回: 显式Interval，None时返回原context.domain；实际观测证明由调用方提供。
    异常: TypeError为非typed上下文/范围；ValueError为显式范围越出原domain。
    """
    # 门槛在任何自有资源构造前执行；不缩窄context来绕过表达式与绑定domain核对。
    if not isinstance(context, HoldContext):
        raise TypeError('指标观测范围需原HoldContext')
    if observation is None:
        return context.domain
    if not isinstance(observation, Interval):
        raise TypeError('显式指标observation需Interval')
    if not context.domain.start_ns <= observation.start_ns <= observation.end_ns <= context.domain.end_ns:
        raise ValueError('指标observation必须位于原context.domain内')
    return observation


class CalculationBlock:
    """持有独立的冻结输入列及本块预算，不依赖后续回读状态。

    series只有有限行；外部提前保存series引用后的存活量由外部负责。
    双向登记指针随本块申请计账，关闭过程中拒绝读取半关闭输出。
    """

    def __init__(self, owner, cost, series):
        """接收已申请空间内的冻结列，登记由创建者完成。

        参数: owner为本次分块者；cost为bytes；series为CalculationSeries。
        返回: 新块。异常: 分配失败由外层收回本次申请。
        """
        # 冻结列和登记指针已包含在本次成本，不再复制样本。
        self._owner, self._cost, self._series = owner, cost, series
        self._closed = self._closing = False
        self._registry = self._previous = self._next = None

    @property
    def closed(self):
        """读取关闭事实。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    @property
    def series(self):
        """读取有限指标列。参数: 无。返回: CalculationSeries。异常: ResultClosedError。"""
        # 释放前取消保留重试入口，不能同时暴露正在关闭的列。
        if self._closed or self._closing:
            raise ResultClosedError('指标输入块已关闭或正在关闭')
        return self._series

    def _discard(self):
        """脱链并丢引用，不重复扣账。

        参数: 无。返回: None。异常: 脱链失败传播，finally仍保存真实关闭事实。
        """
        try:
            self._owner._results.discard(self)
        finally:
            self._closed, self._cost = True, 0
            self._series = self._owner = None

    def close(self):
        """区分真实扣账前后取消，释放一次且支持重试。

        参数: 无。返回: None。异常: 账本/取消原样传播。
        """
        if self._closed:
            return
        self._closing = True
        budget, cost = self._owner._budget, self._cost
        before, released = budget.ram_bytes, False
        try:
            budget.release_ram(cost)
            released = True
        finally:
            # 返回途中取消也可能已扣账；此时完成最小关闭避免再次释放。
            if released or budget.ram_bytes == before - cost:
                self._discard()


class HistoricalCalculationBlocks:
    """只保留一个共享边界帧，逐块交付当前窗口的指标输入。

    _pending归自有回读者持有，其成本由原回读帧申请覆盖；不重复提交时间组。
    每块重新复制有限冻结列，旧块不会随下一块变化，主动留存须close归还预算。
    无观测交集输出空迭代；零长度交集只输出一个点块，不能推断正常积分零。
    """

    def __init__(self, history, context, bindings, compiled, spec, *, backend='numpy', batch_intervals=64,
                 observation=None):
        """校验分块计算能力、预留固定空间，再创建自有回读者。

        参数: history/context/bindings/compiled为真实原输入；spec为CalculationDefinition；
            backend为reference/numpy；batch_intervals为每块最多正区间数，需正原生int。
            observation为原domain内已核实Interval；None兼容原domain，不提供观测证明。
        返回: 尚未读取历史的新分块者。异常: 类型/能力/身份/预算或取消错误。
            原异常的calculation_blocks_cleanup_owner保留持续清理失败时的自有恢复句柄。
        """
        if (not isinstance(history, DecodedHistoryStore) or not isinstance(context, HoldContext)
                or not isinstance(bindings, DecodedBindings) or not isinstance(compiled, CompiledExpression)
                or not isinstance(spec, CalculationDefinition)):
            raise TypeError('历史指标分块需要真实封存历史、上下文、绑定、表达式和CalculationDefinition')
        history._check('sealed')
        if backend not in ('reference', 'numpy') or type(batch_intervals) is not int or batch_intervals < 1:
            raise ValueError('指标分块需合法后端及正整数batch_intervals')
        # samples/select复用相同保持列，只有actual_value_updates标记的半开真实更新才计样本/行。
        if spec.operation not in ('integral', 'min_time', 'max_time', 'time_weighted_mean', 'duration',
                           'sample_count', 'sample_minimum', 'sample_maximum', 'sample_mean', 'select', *MOMENTS, *SAMPLE_QUANTILES):
            raise ValueError('当前历史指标分块只支持已接线的时间、样本与select输入')
        if compiled.bindings.identity != bindings.identity:
            raise ValueError('指标表达式与当前实际绑定不同')
        # 共享类型、选择输出单位和同步门槛，块仍保留表达式原值供后续核使用。
        require_calculation_plan(compiled, spec, None)
        # 计算域与原请求取交集；保持context及其完整来源身份不变。
        observed = _calculation_observation(context, observation)
        left = max(observed.start_ns, spec.window.start_ns)
        right = min(observed.end_ns, spec.window.end_ns)
        actual = Interval(left, right) if left <= right else None
        metadata = _metadata_bytes((context, bindings.sources, compiled.dependencies))
        # 显式范围引用计入原固定预约；None不改变既有固定/每步金额。
        cost = 65536 + 16 * metadata + (0 if observation is None else 16 * _metadata_bytes(observation))
        self._budget, self._fixed_cost = history.budget, 0
        self._closed = self._closing = self._failed = self._done = False
        self._results = self._replay = self._pending = None
        self._inflight_cost, self._unpublished_block = 0, None
        self._backend, self._compiled, self._spec, self._actual = backend, compiled, spec, actual
        self._observation = observation
        self._batch_intervals = batch_intervals
        # 覆盖有限列表/冻结副本、原完整定位和装箱量；回读/查询的申请另在原owner持有。
        self._step_cost = 65536 + (batch_intervals + 1) * (8192 + 32 * metadata)
        before = self._budget.ram_bytes
        try:
            self._budget.reserve_ram(cost)
            self._fixed_cost = cost
            self._results = _BatchRegistry()
            # 即使没有交集也核对真实输入契约，用域内零点避免读文件或制造观测。
            replay_range = actual if actual is not None else Interval(observed.start_ns, observed.start_ns)
            self._replay = HistoricalWindowReplay(history, context, bindings, compiled, replay_range, backend=backend)
        except BaseException as exc:
            # 子构造尚未赋值时通过原异常接管其恢复句柄，不能只关闭外层固定金额。
            child = getattr(exc, 'window_replay_cleanup_owner', None)
            if child is not None:
                self._replay = child
            if self._fixed_cost == 0 and self._budget.ram_bytes == before + cost:
                self._fixed_cost = cost
            try:
                self.close()
            except BaseException as cleanup:
                exc.add_note(f'指标分块初始化清理附加失败: {type(cleanup).__name__}')
                # 最小重试处理瞬时取消；持续失败交出父owner，保留子资源和预算的归属。
                if not self._closed:
                    try:
                        self.close()
                    except BaseException as retry:
                        exc.add_note(f'指标分块初始化清理重试失败: {type(retry).__name__}')
                        if not self._closed:
                            exc.calculation_blocks_cleanup_owner = self
                            exc.add_note('释放恢复后调用calculation_blocks_cleanup_owner.close()')
            raise

    @property
    def closed(self):
        """读取完整关闭事实。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    @property
    def failed(self):
        """读取推进失败标志。参数: 无。返回: bool。异常: 无。"""
        return self._failed

    def __iter__(self):
        """返回本分块者。参数: 无。返回: self。异常: 无。"""
        return self

    def _capture(self, frame):
        """在已预留块空间中恢复一行，不承担数值计算。

        参数: frame为真实回读帧。返回: (ScalarValue, bool actual, Q诊断, SourceRef tuple)。
        异常: 关闭/真实结构/装箱分配错误；数组输入形状(1,)，单位为原表达式单位。
        边界: valid ENUM物理整数码沿原labels映射回标签字符串；其他dtype及invalid不改口径。
        """
        # 正区间用连续视图，只有末点使用点视图，不把EOF末样本延长成面积。
        result = frame.continuous_result if frame.continuous_result is not None else frame.point_result
        if self._backend == 'reference':
            row = result.rows[0]
            value, diagnostic = row.value, row.dependency_quality
        else:
            # 只恢复已由独立数组核算出的一个typed结果，invalid存储占位仍为None。
            row = result.arrays
            column = row.value
            valid = bool(column.valid[0])
            # 新select允许ENUM；只在valid ENUM位置恢复原标签，不能把内部编码当公开ScalarValue。
            stored = column.values[0].item() if valid else None
            if valid and column.dtype is D.ENUM:
                stored = column.labels[int(stored)]
            value = ScalarValue(stored, column.dtype, valid, Q(int(column.quality[0])), column.labels)
            diagnostic = Q(int(row.dependency_quality[0]))
        # 保留真实SourceRef子类及全部字段，不只用字段名字重造来源。
        refs = tuple(sample.source_ref for sample in result.samples)
        return value, bool(result.actual_update[0]), diagnostic, refs

    def __next__(self):
        """先申请块空间，再消费有限区间与一个共享右边界。

        参数: 无。返回: CalculationBlock，series最多batch_intervals+1行。
        异常: StopIteration为完成/无交集；推进错误标failed并保留旧块可读。
        """
        if self._closed or self._closing or self._failed:
            raise ResultClosedError('历史指标分块已关闭、正在关闭或推进失败')
        if self._done or self._actual is None:
            self._done = True
            raise StopIteration
        cost, before = self._step_cost, self._budget.ram_bytes
        try:
            self._budget.reserve_ram(cost)
            self._inflight_cost = cost
            # 所有临时列和最终tuple的并存已预留；最多一个前瞻帧另由回读者计账。
            times, values, updates, diagnostics, refs = [], [], [], [], []
            while True:
                if self._pending is None:
                    self._pending = next(self._replay)
                frame = self._pending
                value, update, diagnostic, sources = self._capture(frame)
                times.append(frame.time_ns)
                values.append(value)
                updates.append(update)
                diagnostics.append(diagnostic)
                refs.extend(sources)
                terminal = frame.time_ns == self._actual.end_ns
                if terminal:
                    self._done = True
                # 最后点留给下块作左端；当前半开指标核不会计算该点的面积或样本。
                if terminal or len(times) == self._batch_intervals + 1:
                    if terminal:
                        frame.close()
                        self._pending = None
                    break
                frame.close()
                self._pending = None
            series = CalculationSeries(Interval(times[0], times[-1]), tuple(times), tuple(values), tuple(updates),
                                  self._compiled.root.unit, diagnostics=tuple(diagnostics),
                                  binding_identity=self._compiled.identity, source_refs=tuple(refs))
            # owner先保有尚未交付输出，清理取消时仍有后续close入口。
            self._unpublished_block = CalculationBlock(self, cost, series)
            block = self._unpublished_block
            self._inflight_cost = 0
            self._results.add(block)
            self._unpublished_block = None
            return block
        except BaseException:
            # 消费已经推进，不假装能重放同一步；只撤销本次未交付申请。
            self._failed = True
            if self._unpublished_block is None and self._inflight_cost == 0 and self._budget.ram_bytes == before + cost:
                # 申请已成功但在返回途中取消，本次成本还没有保存到字段。
                self._inflight_cost = cost
            self._release_unpublished()
            raise

    def _release_unpublished(self):
        """关闭未交付输出或抵销尚无输出持有的申请，真实释放后清字段。

        参数: 无。返回: None，可重试。异常: 子关闭/扣账/取消错误传播。
        """
        if self._unpublished_block is not None:
            # 输出已经取得本次申请；即使字段赋值间取消，也只由该输出抵销一次。
            self._inflight_cost = 0
            self._unpublished_block.close()
            self._unpublished_block = None
        if self._inflight_cost:
            cost, before, released = self._inflight_cost, self._budget.ram_bytes, False
            try:
                self._budget.release_ram(cost)
                released = True
            finally:
                # 扣账前取消保留重试金额，扣账后取消清零以免close重复抵销。
                if released or self._budget.ram_bytes == before - cost:
                    self._inflight_cost = 0

    def close(self):
        """关闭自有块及回读者，真实释放后才记录closed。

        参数: 无。返回: None，可重试。异常: 子close/账本/取消错误传播。
        """
        if self._closed:
            return
        self._closing = True
        self._release_unpublished()
        # 固定首指针遍历，不为关闭复制活动块列表。
        while self._results:
            block = self._results._first
            block.close()
            if block.closed and block._registry is self._results:
                self._results.discard(block)
        if self._replay is not None:
            self._replay.close()
            self._replay = self._pending = None
        before, released = self._budget.ram_bytes, False
        try:
            if self._fixed_cost:
                self._budget.release_ram(self._fixed_cost)
            released = True
        finally:
            if released or self._budget.ram_bytes == before - self._fixed_cost:
                self._closed, self._fixed_cost = True, 0
                self._results = self._compiled = self._spec = self._actual = None
                self._observation = None
