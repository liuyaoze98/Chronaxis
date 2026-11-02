"""从封存的新历史取得有限的数值列和BOOL选择列，交付共同指标输入。

父对象拥有两路HistoricalCalculationBlocks和每路至多一个当前输入块。每次输出
最多batch_intervals个正区间，保留两路剩余范围而不收集整个窗口。
只回读已经解码并封存的新历史，不再次调用来源adapter或旧reader/decoder。
共同轴沿原零阶保持、TTL和末点语义；条件单独更新不能成为数值样本。
observation可指定原domain内已核实计算域，两路原样传递并按其与原请求取交集；
不派生context。None兼容原domain和原预算，本身不是实际观测证明。

构造先校验实际绑定与联合同步，固定状态和每个完整输出在创建前预约。
输出CalculationBlock独立持有金额和登记指针，旧输出不随下次推进变化。
父close关闭自有输出、两当前输入、两回读者及固定账目，不关闭借用历史。
取消前后核对实际预约/释放；构造清理持续失败保留原异常的恢复owner。
失败后不继续推进或返回前缀结果，已交付块仍独立可读至close。
本模块交付时间、样本或select口径输入，不做整窗归约或公共AnalysisRunner接线，也不承诺控制全进程RSS。
"""

# 只组合原有限回读和公共时间输入协议，数值核及旧I/O保持独立。
from dataclasses import replace
from ..core.decoded_binding import DecodedBindings
from ..core.expression import CompiledExpression
from ..core.calculations import CalculationDefinition
from ..core.calculations_memory_reference import require_calculation_plan
from ..core.calculation_series_join import join_calculation_series, _joint_times
from ..core.models import Interval
from ..results.errors import ResultClosedError
from .history import DecodedHistoryStore, _metadata_bytes
from .hold import HoldContext
from .calculation_blocks import HistoricalCalculationBlocks, CalculationBlock, _calculation_observation
from .temporal_buffer import _BatchRegistry


class HistoricalConditionalBlocks:
    """持有两路有限输入与独立输出登记，按共同窗口单向推进。

    _cursor是尚未交付的半开区间左端；每路_current覆盖该点，过右端才换块。
    点窗口只交付一次。已登记输出费用归各CalculationBlock，固定/未交付金额归父。
    _failed或_closing后仅允许关闭，历史/原状态和绑定均由调用方管理。
    """

    def __init__(self, history, context, bindings, compiled, spec, condition, *,
                 backend='numpy', batch_intervals=64, observation=None):
        """核对联合依赖，预约固定金额，再创建两路自有分块者。

        参数: history为封存历史，context/bindings为原保持和实际绑定，compiled
            为值表达式，spec为时间、样本或select指标，condition为BOOL表达式；backend为
            reference/numpy，batch_intervals为输出正区间上限。
            observation为原domain内已核实Interval；None兼容原domain，不证明实际观测。
        返回: 新有限联合owner。异常: 类型/能力/同步/预算/取消错误原样传播；
            持续清理失败时原异常的conditional_blocks_cleanup_owner可再次close。
        """
        # 先检查真实模型和支持范围，不用名称字符串冒充执行身份。
        if (not isinstance(history, DecodedHistoryStore) or not isinstance(context, HoldContext)
                or not isinstance(bindings, DecodedBindings) or not isinstance(compiled, CompiledExpression)
                or not isinstance(spec, CalculationDefinition) or not isinstance(condition, CompiledExpression)):
            raise TypeError('条件历史分块需要封存历史、上下文、实际绑定及两个编译表达式')
        history._check('sealed')
        if backend not in ('reference', 'numpy') or type(batch_intervals) is not int or batch_intervals < 1:
            raise ValueError('条件历史分块需要合法后端和正整数batch_intervals')
        # 三种samples与select保留原值更新标记，条件或TTL边界不会生成真实样本/选择行。
        if spec.operation not in ('integral', 'min_time', 'max_time', 'time_weighted_mean', 'duration',
                           'sample_minimum', 'sample_maximum', 'sample_mean', 'select'):
            raise ValueError('条件历史输入只支持已接线的时间、样本与select口径')
        # 行流保留数值/BOOL/ENUM原值单位，不借联合条件静默转换输出。
        if spec.operation == 'select' and spec.output_unit not in (None, compiled.root.unit):
            raise ValueError('条件select历史输入必须保留原表达式单位')
        if compiled.bindings.identity != bindings.identity:
            raise ValueError('值表达式与当前实际绑定不同')
        require_calculation_plan(compiled, spec, condition)
        # 两路必须在同一显式观测域内计算，不能缩短原context或以短源EOF裁整个会话。
        observed = _calculation_observation(context, observation)
        left = max(observed.start_ns, spec.window.start_ns)
        right = min(observed.end_ns, spec.window.end_ns)
        actual = Interval(left, right) if left <= right else None
        metadata = _metadata_bytes((context, bindings.sources, compiled.identity, condition.identity, spec))
        # 先建立能在预约/子构造失败时安全关闭的固定字段，不持有任何借用资源的所有权。
        self._budget, self._fixed_cost, self._inflight_cost = history.budget, 0, 0
        self._closed = self._closing = self._failed = self._done = False
        self._results = self._unpublished_block = None
        self._blocks, self._current = (None, None), (None, None)
        self._actual, self._cursor, self._batch_intervals = actual, left, batch_intervals
        self._observation = observation
        self._step_cost = 0
        # 显式引用加原固定费；默认None不改变任何原金额，也不强制子层走显式分支。
        fixed = 131072 + 16 * metadata + (0 if observation is None else 16 * _metadata_bytes(observation))
        building = 0
        try:
            self._reserve(fixed, fixed=True)
            self._results = _BatchRegistry()
            self._blocks, self._current = [None, None], [None, None]
            self._blocks[0] = HistoricalCalculationBlocks(history, context, bindings, compiled, spec,
                                                    backend=backend, batch_intervals=batch_intervals,
                                                    observation=self._observation)
            # BOOL分块仅提供原条件列；内部duration配置不执行时长统计或改原请求。
            building = 1
            condition_spec = replace(spec, operation='duration', output_unit=None)
            self._blocks[1] = HistoricalCalculationBlocks(history, context, bindings, condition, condition_spec,
                                                    backend=backend, batch_intervals=batch_intervals,
                                                    observation=self._observation)
        except BaseException as exc:
            # 尚未赋值的失败子构造可能已持有资源，必须从原异常接管其恢复句柄。
            child = getattr(exc, 'calculation_blocks_cleanup_owner', None)
            if child is not None:
                self._blocks[building] = child
            for attempt in range(2):
                try:
                    self.close()
                    break
                except BaseException as cleanup:
                    exc.add_note(f'条件历史初始化清理第{attempt + 1}次附加失败: {type(cleanup).__name__}')
            if not self._closed:
                exc.conditional_blocks_cleanup_owner = self
                exc.add_note('释放恢复后调用conditional_blocks_cleanup_owner.close()')
            raise

    @property
    def closed(self):
        """读取全部自有资源关闭事实。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    @property
    def failed(self):
        """读取不可继续推进的失败标志。参数: 无。返回: bool。异常: 无。"""
        return self._failed

    def __iter__(self):
        """返回本owner。参数: 无。返回: self。异常: 无。"""
        return self

    def _reserve(self, cost, *, fixed=False):
        """即使预约返回途中取消，也及时记录真正取得的自有金额。

        参数: cost为保守bytes；fixed区分构造和当前未交付输出。
        返回: None。异常: 超预算/取消原样传播，不靠发布后的总余额推断所有权。
        """
        before = self._budget.ram_bytes
        try:
            self._budget.reserve_ram(cost)
        finally:
            # 本次原子预约没有其他子操作；真实增加cost才记录，失败前未取得则为0。
            if self._budget.ram_bytes == before + cost:
                if fixed:
                    self._fixed_cost = cost
                else:
                    self._inflight_cost = cost

    def _load(self, side):
        """只在本路当前块到达游标时关闭并取得下一块。

        参数: side为0值/1条件。返回: 覆盖游标的有限CalculationSeries。
        异常: 回读/关闭失败，或输入提前结束/范围错位；不能将意外EOF当正常完成。
        """
        current = self._current[side]
        if current is not None and current.series.observation.end_ns == self._cursor:
            current.close()
            self._current[side] = None
        if self._current[side] is None:
            try:
                self._current[side] = next(self._blocks[side])
            except StopIteration as exc:
                raise ValueError('条件历史输入在完整窗口交付前意外结束') from exc
        series = self._current[side].series
        # 初始点和最终点可以是零区间；非终点旧块必须覆盖一个正区间。
        if (series.observation.start_ns > self._cursor or series.observation.end_ns < self._cursor
                or (self._cursor < self._actual.end_ns and series.observation.end_ns == self._cursor)
                or series.observation.end_ns > self._actual.end_ns):
            raise ValueError('条件历史两路当前块没有覆盖同一实际游标')
        return series

    def __next__(self):
        """产生一个有独立预算的联合块，保留尚未交付的两路剩余区间。

        参数: 无。返回: CalculationBlock，最多batch_intervals+1行。
        异常: StopIteration仅表示正常完整结束/无交集；其余失败后只允许close。
        """
        if self._closed or self._closing or self._failed:
            raise ResultClosedError('条件历史分块已关闭、正在关闭或推进失败')
        if self._done or self._actual is None:
            self._done = True
            raise StopIteration
        try:
            value, condition = self._load(0), self._load(1)
            right = min(value.observation.end_ns, condition.observation.end_ns)
            candidate = Interval(self._cursor, right)
            # 不保存合并轴，只找到第N个正区间右端；剩余输入块由下次继续使用。
            for index, time in enumerate(_joint_times(value, condition, candidate)):
                if index == self._batch_intervals:
                    right = time
                    break
            window = Interval(self._cursor, right)
            # 两份输入、临时列与冻结输出的并存，完整来源/诊断均按当前元数据计费。
            self._step_cost = 65536 + (self._batch_intervals + 1) * 8192 + 16 * _metadata_bytes((value, condition))
            self._reserve(self._step_cost)
            series = join_calculation_series(value, condition, window=window, max_intervals=self._batch_intervals)
            self._unpublished_block = CalculationBlock(self, self._step_cost, series)
            block = self._unpublished_block
            # 输出对象一旦取得金额，未交付关闭以它为准，不重复抵销父inflight。
            self._inflight_cost = 0
            self._results.add(block)
            self._unpublished_block = None
            self._cursor, self._done = right, right == self._actual.end_ns
            return block
        except BaseException as exc:
            self._failed = True
            try:
                self._release_unpublished()
            except BaseException as cleanup:
                # 保留原推进错误与恢复字段，不能让清理失败掩盖真正失败原因。
                exc.add_note(f'条件历史未交付块清理附加失败: {type(cleanup).__name__}')
            raise

    def _release_unpublished(self):
        """关闭未交付块或抵销尚未转交的输出金额，释放前后取消均可重试。

        参数: 无。返回: None。异常: 块关闭/扣账/取消错误原样传播。
        """
        if self._unpublished_block is not None:
            self._inflight_cost = 0
            self._unpublished_block.close()
            self._unpublished_block = None
        if self._inflight_cost:
            cost, before, released = self._inflight_cost, self._budget.ram_bytes, False
            try:
                self._budget.release_ram(cost)
                released = True
            finally:
                if released or self._budget.ram_bytes == before - cost:
                    self._inflight_cost = 0

    def close(self):
        """依次关闭自有输出、当前块、两回读者和固定金额，保留借用资源。

        参数: 无。返回: None，重复关闭安全。异常: 关闭/释放取消可重试。
        """
        if self._closed:
            return
        self._closing = True
        self._release_unpublished()
        while self._results:
            # 输出可能已释放但脱链途中取消；重试关闭需完成残留登记的最小收尾。
            block = self._results._first
            block.close()
            if block.closed and block._registry is self._results:
                self._results.discard(block)
        for side in range(2):
            if self._current[side] is not None:
                self._current[side].close()
                self._current[side] = None
        for side in range(2):
            if self._blocks[side] is not None:
                self._blocks[side].close()
                self._blocks[side] = None
        cost, before, released = self._fixed_cost, self._budget.ram_bytes, False
        try:
            if cost:
                self._budget.release_ram(cost)
            released = True
        finally:
            # 构造预约前失败也可关闭；真实固定金额释放后才宣布整体完成。
            if released or self._budget.ram_bytes == before - cost:
                self._fixed_cost = 0
                self._closed = True
                self._results = self._actual = None
                self._observation = None
