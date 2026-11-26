"""把连续文件的内部面积生成交给工作进程，保留主会话的原序积分结果。

本模块只服务于已确认的同帧、ZOH 会话积分，全部积分项共用实际间隔、同一个
固定间隔或DBC周期；DBC周期取同次DBC核实的驱动报文周期。读取配置沿用普通
CAN 并行路径；未满足静态条件时不创建资源。工作进程不发布结果，主进程
负责跨文件状态和最终累计，所有自有进程及预算由本次会话关闭。
"""

from __future__ import annotations

from dataclasses import replace
from time import process_time, perf_counter
from typing import TYPE_CHECKING

from ..core.calculations import CalculationDefinition
from ..core.models import Interval
from ..results.budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..results.errors import AnalysisError, ResultClosedError
from ..sources.can_spec import can_field_from_key
from .history import _metadata_bytes
from .same_frame_integrals import direct_integral_inputs

if TYPE_CHECKING:
    from ..core.binding import SignalDefinition
    from ..planning.plan import AnalysisPlan
    from ..planning.models import SourcePlan
    from ..planning.input_requirements import InputRequirements, SourceInputRequirements
    from ..results.budget import ResourceBudget
    from ..sources.text_can_spec import CANTextSpec
    from .record_integral import RecordIntegralResult


def parallel_integral_inputs(plan: AnalysisPlan) -> tuple[SignalDefinition, ...] | None:
    """判断已经选择后端的计划能否使用连续多文件面积生成。

    参数: plan 为公共入口已验证并解析后端的计划；调用方另核原请求为 auto。
    返回: 实际依赖信号定义 tuple；不适用返回 None，不读取 DBC 或原文件。
    异常: 非法内部计划结构的属性错误，运行错误不作为切换路径的依据。
    """
    definitions = direct_integral_inputs(plan)
    if definitions is None or len(plan.sources) != 1 or plan.execution.process_count <= 1:
        return None
    # 暂不传递查表声明；复杂表达式仍沿普通路径，不为无关表增加跨进程副本。
    if getattr(plan.bindings, 'lookups', None):
        return None
    # 有界传输的内部容量不是用户配置限制；过宽声明继续使用现有执行路径。
    collections = (definitions, plan.calculations, plan.derived, plan.bindings.signals,
                   plan.bindings.sources, plan.bindings.derived_names,
                   plan.bindings.synchronization)
    if any(len(items) > 4096 for items in collections):
        return None
    from .integral_blocks import boundary_supported
    if not boundary_supported(definitions):
        return None
    source = plan.sources[0]
    if source.source_type not in ('can_blf', 'can_asc', 'asc_or_blf'):
        return None
    if getattr(source.config, 'decode_scope', 'requested') != 'requested':
        return None
    files = source.config.input_paths if source.source_type == 'can_blf' else source.config.inputs
    if len(files) < 2 or source.config.file_merge != 'concatenate':
        return None
    return definitions


def parallel_integral_source(source: SourcePlan, definitions: tuple[SignalDefinition, ...],
                             requirement: SourceInputRequirements,
                             intervals: tuple = ()) -> tuple[CANTextSpec, dict]:
    """取得普通并行 CAN 读取使用的来源与选中字段政策。

    参数: source 为唯一来源，definitions 为实际依赖，requirement 为共用需求分析结果；
        intervals 为计划已解析的 (消费者, IntervalChoice) tuple，默认空，用于请求DBC驱动周期。
    返回: (CANTextSpec, options)，直接供现有 CANTextDecodeRead 使用。
    异常: 内部来源或字段结构错误；不加载 DBC，不读取文件。
    此函数限无导出、无追溯的直接积分子集；选中时间检查与全来源观测仍分开。
    周期请求与普通记录游标相同：先按间隔声明顺序列DBC驱动字段，再列未填有效期的字段，
    使缺少DBC周期时由同一检查报告同一字段。
    """
    fields = tuple(can_field_from_key(item.field) for item in definitions)
    selected = {item.name: field for item, field in zip(definitions, fields)}
    drivers = tuple(selected[choice.driver] for _, choice in intervals
                    if choice.mode == 'dbc' and choice.driver in selected)
    cycles = tuple(dict.fromkeys((*drivers, *(field for item, field in zip(definitions, fields)
                                             if item.valid_for_ns is None))))
    options = dict(classify_unselected=False, cycle_fields=cycles, integrity=False,
                   trace=False, retain_source_time=False,
                   emit_frame_ids=requirement.decode_frame_ids)
    config = source.config
    if source.source_type == 'can_blf':
        from ..sources.blf import BLFSpec
        from ..sources.text_can_spec import CANTextSpec
        # 与 RecordSourceCursor 的纯 BLF 并行转接相同，不套用串行专用解码政策。
        config = CANTextSpec(config.name, tuple(BLFSpec(path, config.offset_ns)
                             for path in config.input_paths), config.dbc_path,
                             config.channel, config.timebase, config.decode_policy,
                             'full' if config.decode_scope == 'all' else config.input_check,
                             config.file_merge)
        options['blf_time_scope'] = requirement.time_scope
        options['legacy_blf_decode'] = source.config.decode_policy == 'legacy'
        if requirement.time_scope != 'source':
            options['time_frame_ids'] = requirement.decode_frame_ids
    else:
        # ASC/混合来源 auto 只核目标 ID 的顺序，但 reader 同次保留实际观测首末。
        if requirement.input_check == 'auto':
            options['time_frame_ids'] = requirement.decode_frame_ids
            if requirement.time_scope != 'source':
                options['selected_ids'] = requirement.decode_frame_ids
    return config, options


class ParallelIntegralSession:
    """拥有一次面积并行任务和父累计状态，最终结果沿原会话发布。

    准备阶段仅取得 DBC 事实；实际读取必须等待绑定证明、有效期和数值任务
    安装。失败后只清理，不重扫输入。关闭保留统计和必要帧型提示，供父会话
    写清单；原记录、面积块和完整元数据不作为默认输出保存。
    """

    @staticmethod
    def fixed_cost(plan: AnalysisPlan) -> int:
        """查询会话声明费，供构造及首帧前准入共用。

        参数: plan为已选中的AnalysisPlan。返回: int，保守预约的字节数。
        异常: 不适用计划时ValueError；静态模型原错误继续传播。
        """
        definitions = parallel_integral_inputs(plan)
        if definitions is None:
            raise ValueError('计划不适用于连续多文件并行积分')
        return 131072 + 4096 * len(plan.calculations) + 32 * _metadata_bytes(definitions)

    def __init__(self, plan: AnalysisPlan, budget: ResourceBudget,
                 requirements: InputRequirements) -> None:
        """登记自有资源槽并预付有限声明空间。

        参数: plan 为适用计划；budget 为父会话账本；requirements 为共用需求。
        返回: None，构造新的会话owner，尚未读取原帧。
        异常: 不适用计划时ValueError；预算不足时BudgetExceededError，
            清理失败附parallel_integral_session_cleanup_owner。
        """
        self._plan, self._budget, self._requirements = plan, budget, requirements
        self._held_cost = self._fixed_cost = 0
        self._pool = self._parent = self._pending = None
        self._calculations = []
        self._definitions = parallel_integral_inputs(plan)
        if self._definitions is None:
            raise ValueError('计划不适用于连续多文件并行积分')
        self.source_name = plan.sources[0].name
        self.metadata = None
        self.frame_format_notices = ()
        self.observed_start = self.observed_end = None
        self._raw = True
        self._closed = self._finished = self._prepared = self._started = False
        self.timings = dict(parent_cpu_seconds=0.0, parent_boundary_reduce_seconds=0.0,
                            parent_finish_seconds=0.0)
        try:
            _reserve_owned_ram(self, self.fixed_cost(plan), '_fixed_cost')
        except BaseException as error:
            _cleanup_owner(self, error, 'parallel_integral_session_cleanup_owner', '并行积分会话构造')
            raise

    def _new(self, factory, recovery, *args, **kwargs):
        """接管构造未返回的资源。参数: 工厂及恢复属性、参数。返回: owner。异常: 原错。"""
        try:
            return factory(*args, **kwargs)
        except BaseException as error:
            self._pending = getattr(error, recovery, None)
            raise

    def prepare(self) -> bool:
        """读取同次 DBC 元数据并建立父累计器，在首帧前决定是否适用。

        参数: 无。返回: bool；True表示已安装数值任务，False表示绑定不能证明同帧或预算不适合。
        异常: 重复调用或已关闭时ResultClosedError；DBC、类型、预算及进程错误原样传播，
            False不用于吞掉运行错误。
        """
        if self._closed or self._prepared:
            raise ResultClosedError('并行积分准备只能执行一次')
        from .parallel_integral_pool import ParallelIntegralPool
        from .same_frame_integrals import same_frame_binding, direct_integral_interval, dbc_driver_cycle
        from .signal_validity import resolve_signal_validity
        from .file_integral_terms import ParentIntegralTerms, parent_terms_cost, parent_terms_minimum_cost
        from .record_integral import RecordIntegral, record_integral_cost
        from .integral_blocks import BLOCK_RAM
        plan = self._plan
        source = plan.sources[0]
        config, options = parallel_integral_source(source, self._definitions,
                                                   self._requirements.for_source(source.name),
                                                   plan.intervals.resolved)
        specs = tuple(CalculationDefinition(request.calculation_id, request.operation,
                      plan.dataset.domain or Interval(0, 0), request.partial_policy,
                      request.unit, minimum_coverage=request.minimum_coverage,
                      config_version=plan.config_version, ddof=request.ddof, q=request.q)
                      for request in plan.calculations)
        expressions = tuple(request.signal for request in plan.calculations)
        derived = tuple(item.definition for item in plan.derived)
        batch = min(plan.execution.batch_rows, 4096)
        # 选择条件已保证全部积分项共用一种间隔；DBC周期的纳秒要等同次DBC事实到达后再取。
        mode, step = direct_integral_interval(plan)
        integral_cost = sum(record_integral_cost(spec, expression.root.unit, batch_intervals=batch)
                            for spec, expression in zip(specs, expressions))
        headroom = 3 * BLOCK_RAM + 8192
        # 固定数值缓冲不依赖DBC，已超预算时不能先启动整池、再关闭并重建普通读取池。
        # 这里只排除必然不足的情况；DBC/有效期/声明图仍在READY后精确检查。
        minimum = ParallelIntegralPool.configuration_minimum_cost(len(expressions),
            process_count=plan.execution.process_count, file_count=len(config.inputs), batch_intervals=batch)
        minimum += parent_terms_minimum_cost(len(expressions), batch_intervals=batch)
        minimum += integral_cost + headroom
        # READY 的展开图也需空间；首次读取许可尚未发送，费用不合适可沿原路径。
        startup = ParallelIntegralPool.startup_cost(config, self._definitions,
            process_count=plan.execution.process_count, **options)
        if self._budget.ram_bytes + startup + max(2 * BLOCK_RAM, minimum) > self._budget.memory_budget_bytes:
            return False
        self._pool = self._new(ParallelIntegralPool, 'parallel_integral_pool_cleanup_owner',
                              config, self._budget, self._definitions,
                              process_count=plan.execution.process_count, **options)
        self.metadata = self._pool.prepare_metadata()
        self._definitions = resolve_signal_validity(self._definitions, {source.name: self})
        binding = same_frame_binding(self._definitions, self.metadata['fields'])
        if binding is None:
            # 尚未授予读取额度；此处只表示静态候选不适用，输入从未被消费。
            return False
        if mode == 'dbc':
            # 与普通路径相同取驱动报文的同次DBC周期；取不到唯一值时首帧前沿用普通路径，
            # 由普通路径按原规则计算或报告错误，不在这里猜周期。
            step = dbc_driver_cycle(plan, self.metadata['fields'])
            if step is None:
                return False
        additional = self._pool.configuration_cost(self._definitions, expressions, specs,
            binding, plan.dataset.session_id, derived=derived, domain=plan.dataset.domain,
            batch_intervals=batch, step_ns=step)
        additional += parent_terms_cost(self._definitions, expressions, derived, batch_intervals=batch)
        additional += integral_cost
        # 保留已知的块展开及最终提示空间；运行中超限仍按原错退出，绝不重扫。
        additional += headroom + 32 * _metadata_bytes(self._definitions)
        if self._budget.ram_bytes + additional > self._budget.memory_budget_bytes:
            return False
        for spec, expression in zip(specs, expressions):
            self._calculations.append(self._new(RecordIntegral, 'record_integral_cleanup_owner',
                self._budget, spec, expression.root.unit, expression.root.dtype, step,
                backend='reference', batch_intervals=min(plan.execution.batch_rows, 4096)))
        self._parent = self._new(ParentIntegralTerms, 'parent_integral_terms_cleanup_owner',
            self._budget, self._definitions, expressions, tuple(self._calculations), binding,
            plan.dataset.session_id, derived=derived, domain=plan.dataset.domain)
        self._pool.configure(self._definitions, expressions, specs, binding,
                             plan.dataset.session_id, derived=derived, domain=plan.dataset.domain,
                             batch_intervals=min(plan.execution.batch_rows, 4096), step_ns=step)
        self._prepared = True
        return True

    def _update_bounds(self) -> None:
        """同步已消费输入的实际范围。参数: 无。返回: None。异常: 非法内部时间。

        没有显式 domain 时，只修改最终分类所需窗口；不构造第二条时间轴。
        """
        self.observed_start, self.observed_end = self._pool.first_ns, self._pool.last_ns
        if self._plan.dataset.domain is None and self.observed_start is not None:
            domain = Interval(self.observed_start, self.observed_end)
            for calculation in self._calculations:
                calculation._spec = replace(calculation._spec, window=domain)

    def execute(self) -> tuple[RecordIntegralResult, ...]:
        """按文件顺序消费面积及边界，全部 EOF 后交付最终结果。

        参数: 无。返回: 与计划计算项同序的 RecordIntegralResult tuple。
        异常: 原始读取、边界、累计或关闭错误；不交付失败前缀。
        """
        if self._closed or not self._prepared or self._started:
            raise ResultClosedError('并行积分需要准备完成且只能执行一次')
        self._started = True
        cpu = process_time()
        sequence_offset = 0
        from .file_integral_terms import FileIntegralHead
        seen = None
        try:
            for index in range(len(self._pool.spec.inputs)):
                self._parent.begin_file(sequence_offset)
                for event in self._pool.iter_file(index):
                    self._update_bounds()
                    if type(event) is FileIntegralHead:
                        # BUG-P5-005：原路径由一个投影跨全部文件记住已见帧型，在后一文件首帧发现不同即报错；
                        # 这里在消费每个文件首组之前按文件顺序核对，先于该组的同刻合并，错误文字相同。
                        identity = self._pool.file_facts[index]['frame_identity']
                        if identity is not None and seen is not None and identity != seen:
                            missing = 'is_extended' if seen[0] != identity[0] else 'is_fd'
                            raise ValueError('同一报文绑定匹配多种实际帧，请补充 ' + missing)
                        seen = seen or identity
                    started = perf_counter()
                    self._parent.consume(event)
                    self.timings['parent_boundary_reduce_seconds'] += perf_counter() - started
                sequence_offset += self._pool.file_facts[index]['count']
            # iter_file 的最后终态证明读取器已关闭；进程资源也在交付结果前关闭。
            self._update_bounds()
            started = perf_counter()
            self._parent.finish(self.observed_end)
            results = tuple(calculation.finish() for calculation in self._calculations)
            if self._plan.dataset.domain is None and self.observed_start is None:
                results = tuple(replace(result, value=None, status='indeterminate',
                                        reason='no_observation') for result in results)
            self.timings['parent_finish_seconds'] += perf_counter() - started
            self._retain_notices()
            self.metadata = None
            self._pool.close()
            self._finished = True
            return results
        finally:
            self.timings['parent_cpu_seconds'] += process_time() - cpu
            self.timings.update(self._pool.timings)

    def _retain_notices(self) -> None:
        """保留本次实际帧型兼容提示。参数: 无。返回: None。异常: 元数据或预算错误。"""
        from ..results.can_metadata import CANFrameFormatNotice
        # 显式绑定的提示来自已核 DBC；自动匹配的经典帧提示由工作进程投影提供。
        automatic = getattr(self._pool, 'compatibility_fields', {})
        if automatic or any('frame_format_compatibility' in fact for fact in self.metadata['fields']):
            _reserve_owned_ram(self, 8192 + 32 * _metadata_bytes(self._definitions), '_fixed_cost')
        result = []
        for definition in self._definitions:
            field = can_field_from_key(definition.field)
            recorded = False
            for fact in self.metadata['fields']:
                if field != type(field)(**fact['locator']) or 'frame_format_compatibility' not in fact:
                    continue
                notice = fact['frame_format_compatibility']
                extended = field.is_extended if field.is_extended is not None else automatic.get(field)
                if extended is not None:
                    result.append(CANFrameFormatNotice(definition.name, field.channel, field.signal,
                        field.frame_id, extended, notice['dbc_is_fd'], notice['requested_is_fd'], notice['code']))
                    recorded = True
            if field in automatic and not recorded:
                result.append(CANFrameFormatNotice(definition.name, field.channel, field.signal,
                    field.frame_id, automatic[field], True, False, 'dbc_fd_classic_selector'))
        self.frame_format_notices = tuple(result)

    @property
    def worker_process_count(self) -> int:
        """返回本次面积并行实际启动的工作进程数，关闭后仍可查看。参数: 无。返回: 非负int。异常: 无。"""
        return len(self.timings.get('worker_pids', ()))

    def close(self) -> None:
        """关闭真实资源后逐项退款，失败保留所有权供重试。

        参数: 无。返回: None；成功后幂等。异常: 子资源关闭或账本原错。
        """
        if self._closed:
            return
        # READY 图由 pool 付费；先结束借用，再允许 pool 退还该图费用。
        self.metadata = None
        for slot in ('_pending', '_pool', '_parent'):
            owner = getattr(self, slot)
            if owner is not None:
                owner.close()
                if not getattr(owner, '_closed', False) or getattr(owner, '_held_cost', 0):
                    raise AnalysisError('并行积分子资源没有完整关闭')
                setattr(self, slot, None)
        for index, owner in enumerate(self._calculations):
            if owner is not None:
                owner.close()
                if not owner._closed or owner._held_cost:
                    raise AnalysisError('并行积分累计器没有完整关闭')
                self._calculations[index] = None
        self._calculations.clear()
        self._plan = self._requirements = self._definitions = self.metadata = None
        self.frame_format_notices = ()
        _release_owned_ram(self, self._fixed_cost, '_fixed_cost')
        self._closed = True
