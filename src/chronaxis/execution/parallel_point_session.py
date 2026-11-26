"""time_order直接积分的组点并行会话：文件工作进程送同刻组点，主进程按串行顺序归并并积分。

PERF-P5-ORDER-01（A1、A2合同）。适用计划与连续多文件并行积分相同，只是来源`file_merge`为
`time_order`、进程上限1及以上都可以（parallel_point_inputs）。

输入：已验证计划、共享预算、共用需求分析结果和本次会话工作目录。
输出：与计划计算项同序的RecordIntegralResult，以及供结果清单使用的帧型兼容提示；
与现有串行time_order直接积分逐位相同。

流程：
1. prepare：首帧前核对时间范围、静态和动态条件及预算，任一不满足就返回False沿用现有路径；
2. execute读取段：ParallelPointPool收齐全部文件的组点包写入PointSpool，读取段错误一律在此报出；
3. execute归并段：关闭工作进程后，按（时间、文件位置）k路归并各文件组点，同一时刻的各文件部分按
   文件位置依次合并；先核跨文件帧型、再合并、遇延迟错误按原类型抛出，最后用SameFrameIntegrals
   的同一求值与积分规则推进RecordIntegral；
4. 交付结果前删除暂存。失败只清理本次登记的进程、暂存与费用，不重读、不换路径。
"""

from __future__ import annotations

from dataclasses import replace
import heapq
from time import process_time, perf_counter
from typing import TYPE_CHECKING

from ..core.calculations import CalculationDefinition
from ..core.models import Interval
from ..results.budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..results.errors import AnalysisError, ResultClosedError
from ..sources.protocol import SourceReadError
from .history import _metadata_bytes
from .same_frame_integrals import direct_integral_inputs

if TYPE_CHECKING:
    from ..core.binding import SignalDefinition
    from ..planning.plan import AnalysisPlan
    from ..planning.input_requirements import InputRequirements
    from ..results.budget import ResourceBudget
    from .record_integral import RecordIntegralResult


def parallel_point_inputs(plan: AnalysisPlan) -> tuple[SignalDefinition, ...] | None:
    """判断已经选择后端的计划能否使用time_order组点并行（A1-1静态部分）。

    参数: plan为公共入口已验证并解析后端的计划；调用方另核原请求为auto。
    返回: 实际依赖信号定义tuple；不适用返回None，不读取DBC或原文件。
    异常: 非法内部计划结构的属性错误；运行错误不作为切换路径的依据。
    与parallel_integral_inputs只有两点不同：要求time_order；进程上限为1也适用。
    time_scope为source的动态条件需要需求分析结果，在ParallelPointSession.prepare中核对。
    """
    definitions = direct_integral_inputs(plan)
    if definitions is None or len(plan.sources) != 1 or plan.execution.process_count < 1:
        return None
    # 查表声明不随任务传输；过宽声明超出有界传输的内部容量，二者都沿用现有路径。
    if getattr(plan.bindings, 'lookups', None):
        return None
    collections = (definitions, plan.calculations, plan.derived, plan.bindings.signals,
                   plan.bindings.sources, plan.bindings.derived_names, plan.bindings.synchronization)
    if any(len(items) > 4096 for items in collections):
        return None
    from .integral_blocks import boundary_supported
    # 单个多帧组点与同刻组摘要的编码上界相同，能放进面积包边界的声明也能放进组点包（A2-3）。
    if not boundary_supported(definitions):
        return None
    source = plan.sources[0]
    if source.source_type not in ('can_blf', 'can_asc', 'asc_or_blf'):
        return None
    if getattr(source.config, 'decode_scope', 'requested') != 'requested':
        return None
    files = source.config.input_paths if source.source_type == 'can_blf' else source.config.inputs
    if len(files) < 2 or source.config.file_merge != 'time_order':
        return None
    return definitions


class ParallelPointSession:
    """拥有一次time_order组点任务：工作池、暂存、同帧积分owner和积分器。

    准备阶段只取得DBC事实；读取许可在数值任务安装后才发出。失败后只清理，不重扫输入。
    关闭保留统计和帧型提示，供父会话写清单。
    """

    @staticmethod
    def fixed_cost(plan: AnalysisPlan) -> int:
        """查询会话声明费，供构造及首帧前准入共用。

        参数: plan为已选中的AnalysisPlan。返回: int，保守预约的字节数。
        异常: 不适用计划时ValueError；静态模型原错误继续传播。
        """
        definitions = parallel_point_inputs(plan)
        if definitions is None:
            raise ValueError('计划不适用于time_order组点并行')
        return 131072 + 4096 * len(plan.calculations) + 32 * _metadata_bytes(definitions)

    def __init__(self, plan: AnalysisPlan, budget: ResourceBudget, requirements: InputRequirements, work_dir) -> None:
        """登记自有资源槽并预付有限声明空间，不读输入。

        参数: plan为适用计划；budget为父会话账本；requirements为共用需求；work_dir为本次会话自有工作目录，
            暂存目录建在其下。
        返回: None。
        异常: 不适用计划时ValueError；预算不足时BudgetExceededError，清理失败附parallel_point_session_cleanup_owner。
        """
        self._plan, self._budget, self._requirements, self._work_dir = plan, budget, requirements, work_dir
        self._held_cost = self._fixed_cost = 0
        self._pool = self._spool = self._owner = self._pending = None
        self._calculations = []
        self._definitions = parallel_point_inputs(plan)
        if self._definitions is None:
            raise ValueError('计划不适用于time_order组点并行')
        self.source_name = plan.sources[0].name
        self.metadata = None
        self.frame_format_notices = ()
        self.observed_start = self.observed_end = None
        self._raw = True
        self._integrity = False
        self._closed = self._finished = self._prepared = self._started = False
        self.timings = dict(parent_cpu_seconds=0.0, merge_integrate_seconds=0.0, groups=0)
        try:
            _reserve_owned_ram(self, self.fixed_cost(plan), '_fixed_cost')
        except BaseException as error:
            _cleanup_owner(self, error, 'parallel_point_session_cleanup_owner', '组点并行会话构造')
            raise

    def _new(self, factory, recovery, *args, **kwargs):
        """接管构造未返回的资源。

        参数: factory为资源类；recovery为构造异常上携带待清理owner的属性名；args、kwargs为构造参数。
        返回: 新owner。异常: 原构造错误，已部分创建的资源记入_pending。
        """
        try:
            return factory(*args, **kwargs)
        except BaseException as error:
            self._pending = getattr(error, recovery, None)
            raise

    def prepare(self) -> bool:
        """读取同次DBC元数据并建立积分状态，在首帧前决定是否适用（A1-1、A2-7）。

        参数: 无。返回: bool；True表示已安装数值任务并许可读取，False表示条件或预算不适用、输入未被消费。
        异常: 重复调用或已关闭时ResultClosedError；DBC、类型、预算及进程错误原样传播，False不用于吞掉运行错误。
        """
        if self._closed or self._prepared:
            raise ResultClosedError('组点并行准备只能执行一次')
        from .parallel_integral_session import parallel_integral_source
        from .parallel_point_pool import ParallelPointPool
        from .same_frame_integrals import (same_frame_binding, direct_integral_interval, dbc_driver_cycle,
                                           SameFrameIntegrals, same_frame_integrals_cost)
        from .signal_validity import resolve_signal_validity
        from .record_integral import RecordIntegral, record_integral_cost
        from .integral_blocks import BLOCK_RAM
        plan = self._plan
        source = plan.sources[0]
        requirement = self._requirements.for_source(source.name)
        # 只有全来源观测时目标记录都带时间；其他time_scope沿用现有路径（A1-1兜底）。
        if requirement.time_scope != 'source':
            return False
        # 直接积分计划的time_scope为source时，现有time_order游标与连续并行积分的读取选项相同（A1-2）。
        config, options = parallel_integral_source(source, self._definitions, requirement, plan.intervals.resolved)
        self._integrity = options.get('integrity', False)
        specs = tuple(CalculationDefinition(request.calculation_id, request.operation,
                      plan.dataset.domain or Interval(0, 0), request.partial_policy,
                      request.unit, minimum_coverage=request.minimum_coverage,
                      config_version=plan.config_version, ddof=request.ddof, q=request.q)
                      for request in plan.calculations)
        expressions = tuple(request.signal for request in plan.calculations)
        derived = tuple(item.definition for item in plan.derived)
        batch = min(plan.execution.batch_rows, 4096)
        mode, step = direct_integral_interval(plan)
        integral_cost = sum(record_integral_cost(spec, expression.root.unit, batch_intervals=batch)
                            for spec, expression in zip(specs, expressions))
        direct_cost = same_frame_integrals_cost(self._definitions, expressions, derived)
        headroom = 3 * BLOCK_RAM + 8192
        files = len(config.inputs)
        # 读取段与归并段不重叠：工作进程退出并退款后才预约每文件一个块的归并缓冲。
        whole = integral_cost + direct_cost + headroom
        startup = ParallelPointPool.startup_cost(config, self._definitions,
            process_count=plan.execution.process_count, **options)
        minimum = ParallelPointPool.points_minimum_cost(len(self._definitions),
            process_count=plan.execution.process_count, file_count=files)
        read_phase = startup + max(2 * BLOCK_RAM, minimum)
        merge_phase = files * BLOCK_RAM
        if self._budget.ram_bytes + whole + max(read_phase, merge_phase) > self._budget.memory_budget_bytes:
            return False
        self._pool = self._new(ParallelPointPool, 'parallel_integral_pool_cleanup_owner',
                               config, self._budget, self._definitions,
                               process_count=plan.execution.process_count, **options)
        self.metadata = self._pool.prepare_metadata()
        self._definitions = resolve_signal_validity(self._definitions, {source.name: self})
        binding = same_frame_binding(self._definitions, self.metadata['fields'])
        if binding is None:
            return False
        if mode == 'dbc':
            # 取不到唯一驱动周期时沿用现有路径，由其按原规则计算或报错，不在这里猜周期。
            step = dbc_driver_cycle(plan, self.metadata['fields'])
            if step is None:
                return False
        quote = self._pool.configuration_cost(self._definitions, expressions, specs, binding,
            plan.dataset.session_id, derived=derived, domain=plan.dataset.domain, batch_intervals=batch, step_ns=step)
        additional = quote + integral_cost + same_frame_integrals_cost(self._definitions, expressions, derived)
        additional += headroom + 32 * _metadata_bytes(self._definitions)
        if self._budget.ram_bytes + additional > self._budget.memory_budget_bytes:
            return False
        # 归并段：工作池全部费用退还后，常驻部分加归并缓冲仍须在预算内。
        if (self._budget.ram_bytes - self._pool._held_cost + integral_cost + direct_cost + merge_phase + headroom
                > self._budget.memory_budget_bytes):
            return False
        for spec, expression in zip(specs, expressions):
            self._calculations.append(self._new(RecordIntegral, 'record_integral_cleanup_owner',
                self._budget, spec, expression.root.unit, expression.root.dtype, step,
                backend='reference', batch_intervals=batch))
        self._owner = self._new(SameFrameIntegrals, 'same_frame_cleanup_owner', self._budget, self._definitions,
            expressions, tuple(self._calculations), binding, plan.dataset.session_id, self._update_bounds, derived=derived)
        self._pool.configure(self._definitions, expressions, specs, binding, plan.dataset.session_id,
                             derived=derived, domain=plan.dataset.domain, batch_intervals=batch, step_ns=step)
        self._prepared = True
        return True

    def _update_bounds(self) -> None:
        """同步全部文件的实际观测范围。参数: 无。返回: None。异常: 非法内部时间。

        读取段结束时范围已是最终值（A1-8）；省略domain时把积分器窗口改为该范围，与现有路径相同。
        """
        if self._pool is not None:
            self.observed_start, self.observed_end = self._pool.first_ns, self._pool.last_ns
        if self._plan.dataset.domain is None and self.observed_start is not None:
            domain = Interval(self.observed_start, self.observed_end)
            for calculation in self._calculations:
                calculation._spec = replace(calculation._spec, window=domain)

    def _retain_notices(self) -> None:
        """保留本次实际帧型兼容提示，规则与连续并行积分会话相同。参数: 无。返回: None。异常: 元数据或预算错误。"""
        from .parallel_integral_session import ParallelIntegralSession
        ParallelIntegralSession._retain_notices(self)

    def _merge(self, identities) -> None:
        """归并段：k路归并各文件组点，合并同刻组并交给同帧积分owner（A2-6）。

        参数: identities为按文件序号排列的实际帧型tuple，元素为（扩展帧, FD）或None。
        返回: None。
        异常: 跨文件帧型不一致、同刻冲突或延迟错误时按串行相同的类型和信息抛出；暂存读回、
            时间次序或积分器错误原样传播。
        """
        from .file_group_points import DeferredPointError
        from .file_integral_terms import _conflict, _merge_group, _offset_group
        definitions = self._definitions
        spool = self._spool
        count = len(identities)
        streams = [((), 0) for _ in range(count)]
        last = [None] * count
        pending, heap = {}, []

        def advance(index):
            """取文件的下一个事件压入堆。参数: index为文件序号。返回: None。异常: 读回错误或文件内时间倒退。"""
            events, position = streams[index]
            while position == len(events):
                packet = spool.next_packet(index)
                if packet is None:
                    streams[index] = ((), 0)
                    return
                events, position = packet.events, 0
            event = events[position]
            streams[index] = (events, position + 1)
            # 文件内组点时间严格递增；延迟错误可与其前缀组点同一时刻。
            if last[index] is not None and (event.time_ns < last[index]
                    or event.time_ns == last[index] and type(event) is not DeferredPointError):
                raise SourceReadError('组点暂存文件内时间次序非法')
            last[index] = event.time_ns
            pending[index] = event
            heapq.heappush(heap, (event.time_ns, index))

        for index in range(count):
            advance(index)
        seen, started = None, set()
        while heap:
            time = heap[0][0]
            merged = None
            # 同一时刻按文件位置依次处理；每个文件同一时间只在堆里有一项。
            while heap and heap[0][0] == time:
                _, index = heapq.heappop(heap)
                event = pending.pop(index)
                if index not in started:
                    started.add(index)
                    # 串行在该文件首帧先投影、后比较：先报此前已合并部分的冲突，再核帧型。
                    if merged is not None:
                        _conflict(merged, definitions)
                    identity = identities[index]
                    if identity is not None:
                        if seen is None:
                            seen = identity
                        elif identity != seen:
                            missing = 'is_extended' if seen[0] != identity[0] else 'is_fd'
                            raise ValueError('同一报文绑定匹配多种实际帧，请补充 ' + missing)
                if type(event) is DeferredPointError:
                    if merged is not None:
                        _conflict(merged, definitions)
                    raise event.kind(event.message)
                # 组内位置加文件偏移后按（文件位置、组内位置）比较先后，复用既有合并与冲突规则。
                group = _offset_group(event, index << 64)
                merged = group if merged is None else _merge_group(merged, group, definitions)
                advance(index)
            _conflict(merged, definitions)
            self._owner.consume_group(time, merged.last_values)
            self.timings['groups'] += 1

    def execute(self) -> tuple[RecordIntegralResult, ...]:
        """执行读取段与归并段，全部完成后交付最终结果。

        参数: 无。返回: 与计划计算项同序的RecordIntegralResult tuple。
        异常: 读取段错误（SourceReadError）、归并段的串行同类错误、暂存或累计错误；不交付失败前缀。
        """
        if self._closed or not self._prepared or self._started:
            raise ResultClosedError('组点并行需要准备完成且只能执行一次')
        self._started = True
        cpu = process_time()
        from .parallel_point_pool import PointSpool
        try:
            count = len(self._pool.spec.inputs)
            self._spool = self._new(PointSpool, 'point_spool_cleanup_owner', self._budget, self._work_dir, count,
                                    integrity=self._integrity)
            self._pool.spool_all(self._spool)
            self._update_bounds()
            self._retain_notices()
            identities = tuple(self._pool.file_facts[index]['frame_identity'] for index in range(count))
            self.timings.update(self._pool.timings)
            # 归并前关闭工作进程并退还其预约，再为归并缓冲预约（A2-6）。
            self.metadata = None
            self._pool.close()
            self._spool.open_readers()
            started = perf_counter()
            self._merge(identities)
            self._owner.finish(self.observed_end)
            results = tuple(calculation.finish() for calculation in self._calculations)
            if self._plan.dataset.domain is None and self.observed_start is None:
                results = tuple(replace(result, value=None, status='indeterminate', reason='no_observation')
                                for result in results)
            self.timings['merge_integrate_seconds'] += perf_counter() - started
            # 暂存没有其他消费者，交付结果前删除（A2-8）。
            self._spool.close()
            self._spool = None
            self._finished = True
            return results
        finally:
            self.timings['parent_cpu_seconds'] += process_time() - cpu

    @property
    def worker_process_count(self) -> int:
        """返回本次组点并行实际启动的工作进程数，关闭后仍可查看。参数: 无。返回: 非负int。异常: 无。"""
        return len(self.timings.get('worker_pids', ()))

    def close(self) -> None:
        """关闭真实资源后逐项退款，失败保留所有权供重试。

        参数: 无。返回: None；成功后幂等。异常: 子资源关闭或账本原错。
        """
        if self._closed:
            return
        self.metadata = None
        # 同帧owner借用积分器，先关闭它；工作池与暂存各自只清理本次登记的资源。
        for slot in ('_pending', '_owner', '_pool', '_spool'):
            owner = getattr(self, slot)
            if owner is not None:
                owner.close()
                if not getattr(owner, '_closed', False) or getattr(owner, '_held_cost', 0):
                    raise AnalysisError('组点并行子资源没有完整关闭')
                setattr(self, slot, None)
        for index, owner in enumerate(self._calculations):
            if owner is not None:
                owner.close()
                if not owner._closed or owner._held_cost:
                    raise AnalysisError('组点并行累计器没有完整关闭')
                self._calculations[index] = None
        self._calculations.clear()
        self._plan = self._requirements = self._definitions = None
        self.frame_format_notices = ()
        _release_owned_ram(self, self._fixed_cost, '_fixed_cost')
        self._closed = True
