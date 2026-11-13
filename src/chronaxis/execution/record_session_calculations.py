"""在原AnalysisRunner会话内合并所需来源并执行会话时间指标。

共享同刻最新状态；每项指标只保自己的驱动点和归约状态。输入只读一次，
不创建普通历史、消息历史或完整贡献。均值仅保其算法必需的值与权重暂存。
每来源只保有界前瞻，同刻跨来源更新收齐后求值。所有输入真正EOF并关闭
后才交付最终结果，失败不发布已累计的前缀。
"""

from ..core.moments import SAMPLE_MOMENTS
from ..core.quantiles import SAMPLE_QUANTILES
from dataclasses import replace
from ..core.models import Interval
from functools import partial
from ..core.calculations import CalculationDefinition
from ..legacy.records import field_to_dict
from ..results.errors import ResultClosedError, AnalysisError
from ..results.spool import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..results.summary import SummaryCalculationRow
from ..results.summary import SummaryCoverageCalculationRow, SummaryHostedCalculationRow
from ..results.summary import SummaryEventRow
from ..core.types import QualityFlag as Q
from ..results.summary import SummarySequenceRow
from ..sources.can_spec import can_field_from_key
from .history import _metadata_bytes
from .state import LatestSignalState
from .driver_expression import DriverExpression
from .record_integral import RecordIntegral
from .record_time_calculation import RecordTimeCalculation
from .record_source_cursor import RecordSourceCursor
from .groups import DecodedTimeGroup
from .current_message_calculation import CurrentMessageCalculation
from ..legacy.sum import LegacySkipReason
from .record_rule_timeline import RecordRuleTimeline
from .record_sequences import RecordSequences
from ..planning.intervals import IntervalChoice
from .record_event_durations import RecordEventDurations,is_event_duration
from ..core.counts_v4 import OBJECT_COUNTS
from .record_object_counts import object_count_results
from .record_scope_calculations import RecordScopeCalculations
from .record_time_indexes import RecordTimeIndexes
from .record_windows import RecordWindows
from .record_exports import RecordExports
from ..results.summary import SummarySegmentRow
from ..results.summary import SummaryContributionRow
from ..results.summary import SummaryInputRow
from .record_diagnostics import RecordDiagnostics
from .record_selection import RecordSelection
from ..results.summary import SummarySelectionRow


class RecordSessionCalculations:
    """拥有实时计算和读取子资源；计划与最终结果仓只借用。"""

    def __init__(self, plan, budget, work_dir, *, requirements=None, declaration_owner=None, direct_integrals: bool=False):
        """预约有限声明空间，不启动读取。

        参数: plan已校验计划、budget共享预算、work_dir已有私有运行目录；
            declaration_owner为持有共享声明的父RunSession，独立使用时省略；
            direct_integrals仅由公共入口的auto选择启用，仍需首帧前证明适用。
        返回: 新owner。异常: 构造原错附record_session_cleanup_owner供父会话接管。
        """
        if type(direct_integrals) is not bool:
            raise TypeError('直接积分内部选择需要bool')
        from ..planning.backend_selection import execution_plan
        plan = execution_plan(plan)
        self._plan, self._budget, self._path = plan, budget, work_dir
        self._declaration_owner = declaration_owner
        self._full_domain = plan.dataset.domain is None
        self._observed_domain = None
        if requirements is None:
            from ..planning.input_requirements import collect_input_requirements
            requirements=collect_input_requirements(plan)
        self._requirements=requirements
        self._held_cost = self._fixed_cost = self._group_cost = 0
        self._state = self._groups = self._adapter = self._read = self._pending = None
        self._calculations = self._expressions = self._cursors = None
        self._messages = None
        # 汇总请求共享一份有界目标消息批；完整贡献保原逐消息输出次序。
        self._message_buffer = []
        self._message_cost = 0
        self._message_batch_rows = (1 if plan.outputs.contributions == 'full'
                                    else min(plan.execution.batch_rows, 4096))
        self._source_ends = None
        self._rules = None
        self._sequences = None
        self._event_durations=None
        self._scope_calculations=None
        self._segment_counts = {}
        self._transform_stages = []
        self._transform_aliases = frozenset()
        self._time_indexes=self._windows=self._exports=None
        self._diagnostics=None
        self._direct_requested = direct_integrals
        self._direct_binding = self._direct_owner = None
        self._rules_begun = False
        self._constant_calculations=frozenset()
        self._spool = None
        self._aggregations = self._append_result = None
        self._next_sequence = 0
        # 指标状态随原写出计数；不为了概况回读结果仓。
        self._outcome_counts = dict(complete=0, partial=0, indeterminate=0, no_observation=0)
        self._closed = self._closing = self._failed = self._started = False
        try:
            # 本层只创建子资源槽、来源索引和计数；表达式/信号声明仍借用原计划。
            count = (len(plan.calculations) + len(plan.message_calculations) + len(plan.rules)
                     + len(plan.windows) + len(plan.sources) + len(plan.signals))
            _reserve_owned_ram(self, 131584 + 4096 * count, '_fixed_cost')
            self._calculations, self._expressions, self._cursors, self._messages = [], [], [], []
            self._source_ends = {}
            self._rules = []
        except BaseException as error:
            _cleanup_owner(self, error, 'record_session_cleanup_owner', '记录流会话构造')
            raise

    def _new(self, factory, recovery, *args, **kwargs):
        """保留尚未交付的真实子owner。参数: 工厂/恢复属性/参数。返回: owner。异常: 原错。"""
        try:
            return factory(*args, **kwargs)
        except BaseException as error:
            self._pending = getattr(error, recovery, None)
            raise

    def _consume_group(self, group):
        """先原子提交同刻组，再分别按所选报文推进各指标。

        参数: 完整DecodedTimeGroup。返回: None。异常: 表达式/预算/累计原错。
        非驱动无效更新仅截断待算值，不新增周期；条件截止独立处理。
        """
        try:
            if self._diagnostics is not None:
                raw_sources={c.source_name for c in self._cursors if c._raw}
                for sample in group.samples:
                    if sample.name in self._transform_aliases:
                        continue  # 网格样本不是实际来源的报文或原字段诊断。
                    if sample.source_ref.source_name not in raw_sources:
                        values_needed=set(self._requirements.ordinary_sample_aliases)|set(self._requirements.message_aliases)
                        clock_only=sample.name not in values_needed
                        self._diagnostics.consume(sample.source_ref.source_name,sample.sequence,sample.time_ns,
                            'signal_clock' if clock_only else 'signal_sample',sample.source_ref.field,
                            {} if clock_only else {sample.name:sample.value.value},sample.value.quality)
            if self._time_indexes is not None:
                self._time_indexes.observe_group(group)
            if self._event_durations is not None:
                self._event_durations.observe_group(group)
            for owner in self._rules:
                ends=[self._source_ends[source] for source in owner.sources if source in self._source_ends]
                if len(ends)==len(owner.sources) and ends and max(ends)<group.time_ns:
                    owner.finish(max(ends))
                owner.before_group(group.time_ns)
                owner.clock_group(group)
            if self._sequences is not None:
                self._sequences.flush_before(group.time_ns)
            if self._exports is not None and self._exports._signal is not None:
                self._exports._signal.observe(group)
            if self._state is not None:
                selected=tuple(s for s in group.samples if s.name in self._state.definitions)
                if selected:
                    self._state.apply(group if len(selected)==len(group.samples) else DecodedTimeGroup(group.time_ns,selected))
            if self._scope_calculations is not None:
                self._scope_calculations.observe_group()
            if self._sequences is not None:
                self._sequences.drivers(group)
            for index,(calculation, expressions) in enumerate(zip(self._calculations, self._expressions)):
                if index in self._constant_calculations:
                    continue
                value, condition = expressions
                row = value.evaluate()
                selected = condition.evaluate() if condition is not None else None
                if value.invalidated_at is not None:
                    calculation.expire_at(value.invalidated_at)
                if condition is not None and condition.invalidated_at is not None:
                    calculation.expire_at(condition.invalidated_at, condition=True)
                if row is not None:
                    updates=({'actual_value_updates':(value.actual_update_at(row[0]),)}
                        if getattr(calculation,'_samples',False) else {})
                    if condition is None:
                        calculation.consume((row,),**updates)
                    else:
                        if selected is None or selected[0] != row[0]:
                            raise AnalysisError('值和条件未按同一驱动组求值')
                        calculation.consume((row,), conditions=(selected[1],),
                                       condition_valid_until_ns=(selected[2],),**updates)
            for owner in self._rules:
                owner.after_group(group.time_ns)
                ends=[self._source_ends[source] for source in owner.sources if source in self._source_ends]
                if len(ends)==len(owner.sources) and ends and max(ends)==group.time_ns:
                    owner.finish(max(ends))
        finally:
            group = calculation = expressions = value = condition = row = selected = None

    def _emit_selection(self,request,parent,row):
        """按请求保存一份选择值及状态。参数: 请求/父ID/旧核借入行。返回: None。异常: 暂存错误。"""
        dataset=self._plan.dataset
        self._spool.append(SummarySelectionRow(self._next_sequence,dataset.dataset_id,dataset.entity,
            dataset.session_id,request.calculation_id,request.scope.split(':',1)[0],parent,row.time_ns,
            row.value.value if row.value.valid else None,row.value.dtype.value,row.unit,row.value.valid,
            row.selection.value,row.quality))
        self._next_sequence+=1

    def _emit_input_trace(self,source,sequence,time_ns,record_type,locator,values,quality):
        """仅按trace请求写最终追溯表。参数: 本次必要输入定位。返回: None。异常: 暂存错误。"""
        dataset=self._plan.dataset
        self._spool.append(SummaryInputRow(self._next_sequence,dataset.dataset_id,dataset.entity,
            dataset.session_id,source,sequence,time_ns,record_type,locator,values,quality))
        self._next_sequence+=1

    def _emit_contribution(self, request, contribution, quality):
        """仅按请求写计算定位和值/跳过。参数: 请求、借入贡献及本次质量。返回: None。异常: 暂存原错。"""
        update=contribution.update
        dataset=self._plan.dataset
        self._spool.append(SummaryContributionRow(self._next_sequence,dataset.dataset_id,dataset.entity,
            dataset.session_id,request.calculation_id,update.source,update.sequence,update.evaluation_index,
            contribution.value,contribution.skip_reason.value if contribution.skip_reason is not None else 'contributed',
            quality))
        self._next_sequence+=1

    def execute_into(self, spool):
        """准备输入与算子，推进一次输入，并把已完成结果写入原结果仓。

        参数: spool为本次ResultSpool。返回: None，不在这里发布文件。
        异常: 原始准备、读取或计算错误；保留可重试的record_session_cleanup_owner。
        """
        if self._closed or self._closing or self._failed or self._started:
            raise ResultClosedError('记录流会话只能执行一次')
        self._started = True
        self._spool = spool
        session_values = choices = definitions = source_cursors = state = None
        try:
            session_values, choices = self._prepare_requests(spool)
            definitions, source_cursors, state = self._prepare_input_state(choices)
            self._prepare_operators(session_values, choices, definitions, source_cursors, state)
            self._merge_sources()
            if self._direct_owner is not None:
                self._direct_owner.finish(self._source_ends.get(self._direct_binding.source))
            self._complete_results(session_values, spool)
        except BaseException as error:
            self._failed = True
            error.record_session_cleanup_owner = self
            raise
        finally:
            # 只解除编排帧对已交付声明和资源的借用，不关闭调用方结果仓。
            session_values = choices = definitions = source_cursors = state = spool = None
            self._spool = self._append_result = None

    def _prepare_requests(self, spool):
        """从已验证计划取得请求和间隔选择；只为实际输出建立汇总状态。

        参数: 结果仓。返回: 会话数值请求与间隔选择。异常: 汇总状态构造错误。"""
        try:
            plan = self._plan
            self._append_result = spool.append
            if plan.aggregations:
                from .result_aggregations import ResultAggregations
                self._aggregations=self._new(ResultAggregations,'aggregation_cleanup_owner',plan,self._budget)
                self._append_result=self._append_aggregate_input
            choices = dict(plan.intervals.resolved)
            hosted_reductions=plan.extensions.reductions if plan.extensions is not None else {}
            # 仅有数值输入的会话指标建立表达式和归约资源；对象计数在规则、窗口封口后产生。
            session_values = tuple(m for m in plan.calculations if m.scope == 'session'
                                   and m.operation not in OBJECT_COUNTS)
            self._segment_counts = {m.count_target: 0 for m in plan.calculations if m.operation == 'segment_count'}
            for request in plan.calculations:
                if request.operation in ('sample_count','sample_minimum','sample_maximum','sample_mean','select', *SAMPLE_MOMENTS, *SAMPLE_QUANTILES, *hosted_reductions):
                    choices[request.calculation_id]=IntervalChoice('actual')
            self._constant_calculations=frozenset(index for index,calculation in
                enumerate(session_values)
                if choices[calculation.calculation_id].driver is None and not any(
                    expression.dependencies for expression in (calculation.signal,calculation.condition) if expression is not None))
            return session_values, choices
        finally:
            # 仅放开本栈帧的临时引用；返回值已交付，子资源仍由会话所有者关闭。
            spool = plan = choices = hosted_reductions = session_values = request = None

    def _prepare_input_state(self, choices):
        """按共用需求打开来源并建立最新信号状态，不提前读完文件。

        参数: 已解析间隔选择。返回: 实际定义、来源游标映射和状态。
        异常: 来源、DBC周期或资源构造错误；子资源立即登记到本会话。"""
        try:
            plan = self._plan
            needed=self._requirements
            active_transforms=tuple(t for t in plan.transforms if t.name in needed.transform_names)
            self._transform_aliases=frozenset(t.name for t in active_transforms)
            if plan.diagnostics.trace or plan.diagnostics.integrity:
                self._diagnostics=self._new(RecordDiagnostics,'record_diagnostics_cleanup_owner',
                    plan,needed,self._budget,self._emit_input_trace)
            observe_bounds=needed.constant_observation
            values=set(needed.ordinary_sample_aliases)|set(needed.message_aliases)
            clocks={name for source in needed.sources for name in source.clock_aliases}
            group_names=set(needed.ordinary_sample_aliases)|clocks
            state_names=set(needed.analysis_sample_aliases)|clocks|self._transform_aliases
            export_names=set() if plan.outputs.signal_csv is None else set(plan.outputs.signal_csv.spec.signals)
            export_sources={item.definition.source for item in plan.signals if item.definition.name in export_names}
            for request in plan.message_calculations:
                values.update(request.expr.dependencies)
                if request.disjunction is not None:
                    values.add(request.disjunction.signal)
                owner = self._new(CurrentMessageCalculation, 'current_message_calculation_cleanup_owner',
                    request, plan.sources, plan.bindings, plan.dataset.session_id, self._budget,
                    backend=plan.execution.backend, batch_rows=self._message_batch_rows, domain=plan.dataset.domain,
                    contribution_consumer=(partial(self._emit_contribution,request)
                        if plan.outputs.contributions=='full' else None))
                self._messages.append((request, owner))
            from ..core.enum_codes import code_dependencies
            expressions = [expr for rule in plan.rules for expr in rule.expressions]
            expressions.extend(expr for calc in plan.calculations for expr in (calc.signal, calc.condition)
                               if expr is not None)
            expressions.extend(t.expression for t in active_transforms)
            requested_codes = {name for expr in expressions for name in code_dependencies(expr.root)}
            definitions = tuple(replace(item.definition, capture_code=True) if item.definition.name in requested_codes
                                else item.definition for item in plan.signals
                                if item.definition.name in values | clocks)
            from .same_frame_integrals import direct_integral_inputs, same_frame_binding
            direct = self._direct_requested and direct_integral_inputs(plan) is not None
            state = None
            source_cursors = {}
            for source in plan.sources:
                source_definitions = tuple(item for item in definitions if item.source == source.name)
                selectors = tuple(item.update_message for item in plan.message_calculations if item.source == source.name)
                keys = tuple(dict.fromkeys((item.channel, item.frame_id, item.is_extended, item.is_fd) for item in selectors))
                retain_frames=plan.outputs.can_frames is not None and plan.outputs.can_frames.source==source.name
                source_requirement=needed.for_source(source.name)
                if source_requirement.active:
                    cursor = self._new(RecordSourceCursor, 'record_source_cleanup_owner',
                        plan, source, source_definitions, values, clocks, self._budget,
                        self._path / ('input-' + source.name), group_names=() if direct else group_names,
                        message_consumer=self._consume_direct_update if direct else self._consume_message if keys or self._diagnostics is not None else None, message_keys=keys,observe_bounds=observe_bounds or source.name in export_sources,retain_frames=retain_frames,requirements=source_requirement)
                    self._cursors.append(cursor)
                    source_cursors[source.name] = cursor
            # 复用本次来源初始化得到的DBC周期，首帧前补齐默认有效期。
            # 不提前构造带假有效期的计算状态；无关信号不进入definitions。
            from .signal_validity import resolve_signal_validity
            definitions = resolve_signal_validity(definitions, source_cursors)
            if direct:
                cursor = source_cursors[definitions[0].source]
                self._direct_binding = same_frame_binding(definitions, cursor.metadata['fields'])
                if self._direct_binding is None:
                    # 首帧前决定普通路径；原DBC和游标保留，不再次加载或读取。
                    cursor._message_consumer = None
                    cursor._attach_raw_groups(definitions, plan.dataset.session_id, plan.execution.backend)
            definitions += tuple(t.output for t in active_transforms)
            # 由最后一层向前接回调。每层只打开自己所需状态，原Reader仍只消费一次。
            if active_transforms:
                from .transform_stream import TransformStage
                emit=self._consume_group
                for t in reversed(active_transforms):
                    choice=choices[t.name]
                    period=choice.step_ns
                    if choice.mode=='dbc':
                        definition=next(d for d in definitions if d.name==choice.driver)
                        locator=field_to_dict(can_field_from_key(definition.field))
                        period=next(f['cycle_ns'] for f in source_cursors[definition.source].metadata['fields']
                                    if f['locator']==locator)
                    stage=self._new(TransformStage,'transform_cleanup_owner',plan,t,definitions,choice,period,
                                    self._source_ends,source_cursors,self._budget,emit)
                    self._transform_stages.insert(0,stage)
                    emit=stage.push
            if self._full_domain:
                # 零长度只供尚未收到输入的数值owner构造，不作为观测或读取过滤条件。
                # 游标已用原始None请求创建；每轮前瞻后改成真实已读范围。
                plan = replace(plan, dataset=replace(plan.dataset, domain=Interval(0, 0)))
                self._plan = plan
            if self._direct_binding is None and (state_names or observe_bounds):
                state = self._state = self._new(LatestSignalState, 'state_cleanup_owner',
                    self._budget, tuple(item for item in definitions if item.name in state_names), plan.dataset.session_id,
                    declaration_owner=self._declaration_owner)
            if plan.outputs.can_frames is not None or plan.outputs.signal_csv is not None:
                self._exports=self._new(RecordExports,'record_exports_cleanup_owner',
                    plan,self._budget,self._path/'exports',self._cursors)
            return definitions, source_cursors, state
        finally:
            # 仅放开本栈帧的临时引用；返回值已交付，子资源仍由会话所有者关闭。
            choices = plan = needed = active_transforms = values = clocks = group_names = state_names = export_names = export_sources = None
            request = owner = expressions = requested_codes = definitions = state = source_cursors = source = source_definitions = selectors = keys = source_requirement = cursor = None
            emit = t = choice = definition = locator = stage = None

    def _prepare_operators(self, session_values, choices, definitions, source_cursors, state):
        """依次建立实际请求的计算、事件、窗口和序列算子。

        参数: 会话请求、间隔选择、实际信号定义及本次来源与状态。
        返回: None。异常: 单位、周期或资源构造错误，已构造对象仍由本会话持有。"""
        try:
            plan = self._plan
            hosted_reductions = plan.extensions.reductions if plan.extensions is not None else {}
            derived = tuple(item.definition for item in plan.derived)
            for request in session_values:
                choice = choices[request.calculation_id]
                step = choice.step_ns
                if choice.mode == 'dbc':
                    locator = field_to_dict(can_field_from_key(state.definitions[choice.driver].field))
                    metadata = source_cursors[state.definitions[choice.driver].source].metadata
                    step = next(item['cycle_ns'] for item in metadata['fields'] if item['locator'] == locator)
                expression = request.signal if request.signal is not None else request.condition
                condition = request.condition if request.signal is not None else None
                # 先登记可达槽，再构造下一个子资源，避免后续构造失败遗失前者。
                if self._direct_binding is None:
                    self._expressions.append([None, None])
                    for index, static in enumerate((expression, condition)):
                        if static is not None:
                            self._expressions[-1][index] = self._new(DriverExpression,
                                'driver_expression_cleanup_owner', static, state, choice.driver,
                                backend=plan.execution.backend, derived=derived, observation_ends=self._source_ends)
                descriptor=hosted_reductions.get(request.operation)
                spec = CalculationDefinition(request.calculation_id, 'sample_minimum' if descriptor else request.operation, plan.dataset.domain,
                                  request.partial_policy, request.unit, minimum_coverage=request.minimum_coverage,
                                  config_version=plan.config_version, ddof=request.ddof, q=request.q)
                factory = RecordIntegral if request.operation == 'integral' else RecordTimeCalculation
                recovery = 'record_integral_cleanup_owner' if request.operation == 'integral' else 'record_time_cleanup_owner'
                extra = {'work_dir': self._path} if request.operation == 'time_weighted_mean' else {}
                if descriptor:
                    extra={'hosted':descriptor}
                if request.operation=='select':
                    factory,recovery=RecordSelection,'record_selection_cleanup_owner'
                    extra={'consumer':partial(self._emit_selection,request,None)}
                self._calculations.append(self._new(factory, recovery, self._budget, spec,
                    expression.root.unit, expression.root.dtype, step, backend=plan.execution.backend,
                    batch_intervals=min(plan.execution.batch_rows, 4096), conditioned=condition is not None, **extra))
            if self._direct_binding is not None:
                from .same_frame_integrals import SameFrameIntegrals
                self._direct_owner = self._new(SameFrameIntegrals, 'same_frame_cleanup_owner',
                    self._budget, definitions, tuple(item.signal for item in session_values),
                    tuple(self._calculations), self._direct_binding, plan.dataset.session_id,
                    self._before_direct_group, derived=derived)
            metadata = None
            event_requests=tuple(item for item in plan.calculations if is_event_duration(item))
            index_ids={item.calculation_id for item in event_requests}|{item.window_id for item in plan.windows}
            drivers=tuple(dict.fromkeys(choices[name].driver for name in index_ids if choices[name].mode!='actual'))
            if drivers:
                self._time_indexes=self._new(RecordTimeIndexes,'record_time_indexes_cleanup_owner',
                    self._budget,self._path,drivers)
            if plan.windows:
                steps={}
                for request in plan.windows:
                    choice=choices[request.window_id]
                    step=choice.step_ns
                    if choice.mode=='dbc':
                        definition=state.definitions[choice.driver]
                        locator=field_to_dict(can_field_from_key(definition.field))
                        step=next(item['cycle_ns'] for item in source_cursors[definition.source].metadata['fields']
                                  if item['locator']==locator)
                    steps[request.window_id]=step
                self._windows=self._new(RecordWindows,'record_windows_cleanup_owner',
                    plan,self._budget,self._time_indexes,steps,self._emit_segment)
            if event_requests:
                steps={}
                for request in event_requests:
                    choice=choices[request.calculation_id]
                    step=choice.step_ns
                    if choice.mode=='dbc':
                        definition=state.definitions[choice.driver]
                        locator=field_to_dict(can_field_from_key(definition.field))
                        step=next(item['cycle_ns'] for item in source_cursors[definition.source].metadata['fields']
                                  if item['locator']==locator)
                    steps[request.calculation_id]=step
                self._event_durations=self._new(RecordEventDurations,'record_event_duration_cleanup_owner',
                    plan,self._budget,self._path,steps,self._emit_event_duration,indexes=self._time_indexes)
            scope_requests=tuple(item for item in plan.calculations if item.scope!='session' and not is_event_duration(item))
            if scope_requests:
                steps={}
                for request in scope_requests:
                    choice=choices[request.calculation_id]
                    step=choice.step_ns
                    if choice.mode=='dbc':
                        definition=state.definitions[choice.driver]
                        locator=field_to_dict(can_field_from_key(definition.field))
                        step=next(item['cycle_ns'] for item in source_cursors[definition.source].metadata['fields']
                                  if item['locator']==locator)
                    steps[request.calculation_id]=step
                self._scope_calculations=self._new(RecordScopeCalculations,'record_scope_calculations_cleanup_owner',
                    plan,state,self._budget,self._path,steps,scope_requests,self._source_ends,self._emit_event_duration,
                    selection_consumer=self._emit_selection)
            if plan.sequences:
                steps={}
                for request in plan.sequences:
                    choice=choices[request.sequence_id]
                    step=choice.step_ns
                    if choice.mode=='dbc':
                        definition=state.definitions[choice.driver]
                        locator=field_to_dict(can_field_from_key(definition.field))
                        step=next(item['cycle_ns'] for item in source_cursors[definition.source].metadata['fields']
                                  if item['locator']==locator)
                    steps[request.sequence_id]=step
                self._sequences=self._new(RecordSequences,'record_sequences_cleanup_owner',
                    plan,state,self._budget,steps,self._emit_sequence)
            for request in plan.rules:
                if any(p.preset_type=='threshold_excursion' and request.rule_id==p.id+'_activity' for p in plan.presets):
                    request=replace(request,stability=replace(request.stability,track_duration=True))
                choice=choices.get(request.rule_id,IntervalChoice('actual'))
                step=choice.step_ns
                if choice.mode=='dbc':
                    definition=state.definitions[choice.driver]
                    locator=field_to_dict(can_field_from_key(definition.field))
                    step=next(item['cycle_ns'] for item in source_cursors[definition.source].metadata['fields']
                              if item['locator']==locator)
                self._rules.append(self._new(RecordRuleTimeline,'record_rule_cleanup_owner',
                    plan,request,state,self._budget,step,choice.driver,self._source_ends,self._emit_event,
                    step_consumer=None if self._sequences is None else self._sequences.observe))
        finally:
            # 仅放开本栈帧的临时引用；返回值已交付，子资源仍由会话所有者关闭。
            session_values = choices = definitions = source_cursors = state = plan = hosted_reductions = derived = request = choice = metadata = expression = condition = static = None
            descriptor = spec = factory = extra = event_requests = index_ids = drivers = steps = definition = locator = scope_requests = None

    def _complete_results(self, session_values, spool):
        """输入真正EOF后完成尾部、统计和结果汇总，不发布未完成前缀。

        参数: 会话请求和原结果仓。返回: None。异常: 尾部计算、封存或写入错误。"""
        try:
            plan = self._plan
            # 真正EOF并关闭来源后，提交不足一批的尾部；失败不发布前缀。
            self._flush_messages()
            if self._exports is not None:
                self._exports.session()
            self._consume_constants()
            self._finish_actual_tails()
            if self._scope_calculations is not None:
                self._scope_calculations.finish(self._cursors)
            if self._event_durations is not None:
                self._event_durations.finish()
            if self._windows is not None:
                self._windows.finish(self._cursors,spool)
            if self._exports is not None:
                self._exports.seal()
            for request, calculation in zip(session_values, self._calculations):
                result = calculation.finish()
                if request.operation=='select':continue
                if self._full_domain and self._observed_domain is None:
                    result = replace(result, value=None, status='indeterminate', reason='no_observation')
                self._emit_event_duration(request,None,result)
            # 所有片段已完成合并，此时只读取事件计数及按需记录的最终片段身份数。
            for request, result in object_count_results(self._plan, self._rules, self._segment_counts):
                self._emit_event_duration(request, None, result)
            for sequence, (request, owner) in enumerate(self._messages, len(plan.calculations)):
                result = owner.snapshot()
                incomplete = any(count for reason, count in result.skip_counts.items()
                                 if reason is not LegacySkipReason.CONDITION_FALSE)
                status = 'indeterminate' if result.value is None else 'partial' if incomplete else 'complete'
                self._append_result(SummaryCalculationRow(self._next_sequence, plan.dataset.dataset_id, plan.dataset.entity,
                    plan.dataset.session_id, request.calculation_id, 'legacy_sum', 'session', None,
                    None if result.value is None else round(result.value, 6), request.unit, status,
                    result.reason or ('partial_input' if incomplete else 'ok'), owner.quality))
                self._count_outcome(status,result.reason)
                self._next_sequence+=1
            if self._aggregations is not None:
                for row in self._aggregations.rows(self._rules,self._next_sequence):
                    spool.append(row)
                    self._next_sequence+=1
        finally:
            # 仅放开本栈帧的临时引用；返回值已交付，子资源仍由会话所有者关闭。
            session_values = spool = plan = request = calculation = result = owner = row = None

    def _append_aggregate_input(self,row):
        """从同一源行同时得到公开记录和聚合输入，不复制或重扫源表。

        参数: row 为当前行。返回: None。异常: 原写出/归约错误终止整个会话。
        """
        self._spool.append(row)
        self._aggregations.accept(row)

    def _finish_actual_tails(self):
        """以实际来源EOF结算连续计算和样本统计，固定周期不凭空加报文。

        参数: 无，读取已耗尽游标、最新状态及尚待结算的末点。
        返回: None。异常: 表达式、预算或累计错误原样传播。
        不新增样本、贡献或追溯；观察结束和TTL都来自真实输入，domain仅负责裁剪。
        """
        for index, (calculation, expressions) in enumerate(zip(self._calculations, self._expressions)):
            samples = getattr(calculation, '_samples', False)
            if (index in self._constant_calculations
                    or not samples and calculation._step_ns is not None or not calculation._rows):
                continue
            value, condition = expressions
            sources = {definition.source for expression in expressions if expression is not None
                       for _, definition in expression._definitions}
            ends = [self._source_ends[source] for source in sources if source in self._source_ends]
            if not ends or max(ends) <= calculation._last_time:
                continue
            start, end = calculation._last_time, max(ends)
            # 最后组当时可能尚未知另一来源EOF；现在按右侧保持重算，不能沿用已结束来源的点值。
            current, deadline = value.evaluate_at(start)
            selected, condition_deadline = (None, None) if condition is None else condition.evaluate_at(start)
            if samples:
                # 保留真实末点及其更新标志；EOF查询只补齐有效截止，不把保持值写成新样本。
                # 某依赖来源已在末点结束时，其右侧保持无效，仍沿用既有半开EOF政策。
                previous = calculation._rows[-1]
                value_ends = tuple(t for t in (previous[2], deadline,
                    start if not current.valid else None) if t is not None)
                condition_ends = tuple(t for t in (previous[4], condition_deadline,
                    start if selected is not None and not selected.valid else None) if t is not None)
                calculation._rows[-1] = (start, previous[1], min(value_ends) if value_ends else None,
                    previous[3], min(condition_ends) if condition_ends else None) + previous[5:]
            else:
                calculation._rows[-1] = (start, current, deadline, selected, condition_deadline)
            calculation.consume(((end, current, deadline),),
                **({'actual_value_updates': (False,)} if samples else {}),
                **({} if condition is None else
                   {'conditions': (selected,), 'condition_valid_until_ns': (condition_deadline,)}))

    def _consume_constants(self):
        """常量只需真实首末范围，EOF后复用相同统计核，不创建假信号或逐行值。

        参数: 无。返回: None。异常: 求值/预算/计算原错；无观测不喂任何点。
        """
        if not self._constant_calculations:
            return
        starts=[c.observed_start for c in self._cursors if c.observed_start is not None]
        ends=[c.observed_end for c in self._cursors if c.observed_start is not None and c.observed_end is not None]
        if not starts or not ends:
            return
        first,last=min(starts),max(ends)
        for index in self._constant_calculations:
            calculation=self._calculations[index]
            value,condition=self._expressions[index]
            result,_=value.evaluate_at(last)
            selected=None if condition is None else condition.evaluate_at(last)[0]
            for time in dict.fromkeys((first,last)):
                # 常量的两个观测边界只说明保持范围，没有真实值更新可供计数。
                updates = {'actual_value_updates': (False,)} if calculation._spec.operation in ('sample_count', *SAMPLE_MOMENTS, *SAMPLE_QUANTILES) else {}
                calculation.consume(((time,result,None),),**updates,**({} if condition is None else
                    {'conditions':(selected,),'condition_valid_until_ns':(None,)}))

    def _emit_event(self,event):
        """将必要事件字段直接写一次最终结果仓。参数: 原核心事件。返回: None。异常: 原写入错。"""
        try:
            plan=self._plan
            self._append_result(SummaryEventRow(self._next_sequence,plan.dataset.dataset_id,plan.dataset.entity,
                plan.dataset.session_id,event.rule.rule_id,event.event_id,event.start_ns,event.confirmed_ns,
                event.end_ns,event.status,event.trigger_kind,event.quality | (event.dependency_quality & Q.ESTIMATED)))
            self._next_sequence+=1
            if self._event_durations is not None:
                self._event_durations.observe_event(event)
            if self._scope_calculations is not None:
                self._scope_calculations.observe_event(event)
        finally:
            event=None

    def _emit_event_duration(self,request,event_id,result):
        """把每段事件指标直接写最终指标表。参数: 请求/父ID/结果。返回: None。异常: 原发布错。"""
        plan=self._plan
        model=SummaryCalculationRow if result.coverage_status is None else SummaryCoverageCalculationRow
        extra={} if result.coverage_status is None else {'coverage_status':result.coverage_status}
        if plan.extensions is not None and request.operation in plan.extensions.reductions:
            model=SummaryHostedCalculationRow
            extra['extension_version']=plan.extensions.reductions[request.operation].version
        self._append_result(model(self._next_sequence,plan.dataset.dataset_id,plan.dataset.entity,
            plan.dataset.session_id,request.calculation_id,request.operation,request.scope.split(':',1)[0],event_id,
            result.value,result.unit,result.status,result.reason,result.quality,**extra))
        self._count_outcome(result.status,result.reason)
        self._next_sequence+=1

    def _emit_segment(self,segment):
        """只写实际片段与父关联，后续指标借用同一片段。参数: 核心片段。返回: None。异常: 原发布/计算错。"""
        if self._exports is not None:
            self._exports.segment(segment)
        plan=self._plan
        actual=segment.actual
        self._append_result(SummarySegmentRow(self._next_sequence,plan.dataset.dataset_id,plan.dataset.entity,
            plan.dataset.session_id,segment.window_id,segment.segment_id,
            None if actual is None else actual.start_ns,None if actual is None else actual.end_ns,
            segment.status,segment.parent_event_ids,segment.quality))
        self._next_sequence+=1
        if segment.window_id in self._segment_counts:
            self._segment_counts[segment.window_id] += 1
        if self._scope_calculations is not None:
            self._scope_calculations.observe_segment(segment)

    def _count_outcome(self,status,reason):
        """随已写出的指标计数。参数: 行状态/原因。返回: None。异常: 未支持的内部状态。"""
        self._outcome_counts[status] += 1
        if reason in ('no_observation','no_evaluations'):
            self._outcome_counts['no_observation'] += 1

    def analysis_outcome(self):
        """取得同次规则和指标概况。参数: 无。返回: AnalysisOutcome。异常: 规则未完成。"""
        from ..results.analysis_outcome import AnalysisOutcome
        return AnalysisOutcome(tuple(owner.outcome() for owner in self._rules),**self._outcome_counts)

    def threshold_summaries(self):
        """生成明确预设请求的有限汇总，不复制状态轨迹。参数: 无。返回: tuple。异常: 未完成统计错误。"""
        from ..results.threshold_metadata import SummaryThresholdDuration
        presets={preset.id:preset for preset in self._plan.presets if preset.preset_type=='threshold_excursion'}
        result=[]
        for owner in self._rules:
            name=owner._request.rule_id
            preset_id=name.removesuffix('_activity')
            if preset_id in presets:
                value,status=owner.duration_result
                result.append(SummaryThresholdDuration(preset_id,name,value,status))
        return tuple(result)

    def _emit_sequence(self,result):
        """只写最终配对结论，不复制事件全文。参数: 核心结果。返回: None。异常: 原写入错。"""
        try:
            plan=self._plan
            self._append_result(SummarySequenceRow(self._next_sequence,plan.dataset.dataset_id,plan.dataset.entity,
                plan.dataset.session_id,result.rule.rule_id,result.result_id,result.request.event_id,
                None if result.response is None else result.response.event_id,result.decided_ns,
                result.delay_ns,result.status,result.observation_quality))
            self._next_sequence+=1
        finally:
            result=None

    def _consume_message(self, update):
        """按原序收集有限目标批，供同来源各累计器共用。

        参数: update是只借用到本回调结束的原消息；延长寿命前先付费。
        返回: None。异常: 预算、计算或取消原错；完整明细仍逐消息交付。
        """
        try:
            if self._diagnostics is not None:
                self._diagnostics.consume(update.source,update.sequence,update.time_ns,
                    'decoded_message',f'can:{update.channel}:{update.frame_id}:{int(update.is_extended)}:{int(update.is_fd)}',
                    update.values,update.quality)
            if not any(request.source == update.source for request, _ in self._messages):
                return
            if self._message_batch_rows == 1:
                for request, owner in self._messages:
                    if request.source == update.source:
                        owner.consume((update,))
                return
            # 来源切换时先提交上一批，绝不将不同来源输入混入同一求和序列。
            if self._message_buffer and self._message_buffer[0].source != update.source:
                self._flush_messages()
            cost = 16384 + 16 * _metadata_bytes(update)
            # 为下一次实际计算留出空间，不能只按缓存本身是否放得下填满预算。
            row_cost = max(owner._row_cost for request, owner in self._messages
                           if request.source == update.source)
            compute_cost = 16384 + (len(self._message_buffer) + 1) * row_cost
            # 读取器还可能构造本批返回列，不能把它尚未申请的费用当成空闲缓存。
            # 消息延长持有最多占总预算的1/16，其余仍供读取、计算和结果共用。
            buffer_limit = self._budget.memory_budget_bytes // 16
            if (self._message_buffer and (self._message_cost + cost > buffer_limit
                    or self._budget.ram_bytes + cost + compute_cost
                    > self._budget.memory_budget_bytes)):
                self._flush_messages()
            _reserve_owned_ram(self, cost, '_message_cost')
            self._message_buffer.append(update)
            if (len(self._message_buffer) >= self._message_batch_rows
                    or self._message_cost >= buffer_limit):
                self._flush_messages()
        finally:
            update = None

    def _flush_messages(self):
        """共享当前目标批完成各汇总计算，不创建历史或逐次输出。

        参数: 无，使用已付费的有限消息缓冲。返回: None。
        异常: 原计算/取消错误优先；清理失败保留费用，供close重试。
        """
        if not self._message_buffer:
            return
        updates = tuple(self._message_buffer)
        primary = None
        try:
            for request, owner in self._messages:
                if request.source == updates[0].source:
                    owner.consume(updates)
        except BaseException as error:
            primary = error
            raise
        finally:
            # 即使计算失败也不重放可能已经累计过的批；只允许资源清理。
            updates = None
            self._message_buffer.clear()
            try:
                _release_owned_ram(self, self._message_cost, '_message_cost')
            except BaseException as cleanup:
                if primary is None:
                    raise
                primary.add_note('目标消息批费用清理失败：' + type(cleanup).__name__)

    def _consume_direct_update(self, update: 'LegacyDecodedUpdate') -> None:
        """向已完成首帧前检查的同帧owner交付更新。参数: 更新。返回: None。异常: 原消费错误。"""
        self._direct_owner.consume(update)

    def _before_direct_group(self) -> None:
        """结算前更新省略domain的实际范围；显式裁剪不额外查询。参数: 无。返回: None。异常: 原读取状态错误。"""
        if not self._full_domain:
            return
        for cursor in self._cursors:
            cursor._refresh_observed_bounds()
        self._advance_observed_domain()

    def _advance_observed_domain(self):
        """用已付费游标的真实首末更新在线范围，不读取更多输入或保存时间序列。

        参数: 无。返回: None。显式范围保持原裁剪规则；省略范围只保一个当前并集。
        异常: 非法时间或已封闭检测器的推进错误沿原清理路径传播。
        """
        if not self._full_domain:
            return
        starts = [c.observed_start for c in self._cursors if c.observed_start is not None]
        ends = [c.observed_end for c in self._cursors if c.observed_end is not None]
        if not starts or not ends:
            return
        domain = Interval(min(starts), max(ends))
        if domain == self._observed_domain:
            return
        self._observed_domain = domain
        self._plan = replace(self._plan, dataset=replace(self._plan.dataset, domain=domain))
        for calculation in self._calculations:
            calculation._spec = replace(calculation._spec, window=domain)
            reduction = getattr(calculation, '_reduction', None)
            if reduction is not None:
                reduction._spec = calculation._spec
        for owner in self._rules:
            owner._plan = self._plan
            owner.extend_observation(domain.end_ns)
        for owner in (self._sequences, self._windows, self._scope_calculations,
                      self._event_durations, self._exports):
            if owner is not None:
                owner._plan = self._plan
        if self._exports is not None and self._exports._signal is not None:
            self._exports._signal.update_observation(self._plan)

    def _merge_sources(self):
        """每来源只取已付费前瞻，收齐同刻更新再求值。

        参数: 无。返回: None，所有实际来源EOF才返回。异常: 原读取/计算/预算错误。
        不按文件顺序拼接不同来源，不为跨源合并建磁盘历史。
        """
        heads = group = samples = None
        primary = None
        try:
            while True:
                heads = tuple(cursor.peek() for cursor in self._cursors)
                self._advance_observed_domain()
                for cursor in self._cursors:
                    if cursor._finished and cursor.observed_end is not None:
                        self._source_ends[cursor.source_name] = cursor.observed_end
                if self._sequences is not None:
                    self._sequences.bounds(self._cursors,self._source_ends)
                if not self._rules_begun:
                    for owner in self._rules:
                        starts=[cursor.observed_start for cursor in self._cursors
                                if cursor.source_name in owner.sources and cursor.observed_start is not None]
                        if starts:
                            owner.begin(min(starts))
                    self._rules_begun=True
                live = tuple(head for head in heads if head is not None)
                if not live:
                    for stage in self._transform_stages:
                        stage.finish()
                    for owner in self._rules:
                        ends=[self._source_ends[source] for source in owner.sources if source in self._source_ends]
                        if ends:
                            owner.finish(max(ends))
                    if self._sequences is not None:
                        self._sequences.flush_before()
                    return
                time = min(head.time_ns for head in live)
                count = sum(len(head.samples) for head in live if head.time_ns == time)
                _reserve_owned_ram(self, 16384 + count*1024, '_group_cost')
                samples = tuple(sample for head in live if head.time_ns == time for sample in head.samples)
                group = DecodedTimeGroup(time, samples)
                if self._transform_stages:
                    self._transform_stages[0].push(group)
                else:
                    self._consume_group(group)
                group = samples = live = None
                for cursor, head in zip(self._cursors, heads):
                    if head is not None and head.time_ns == time:
                        cursor.advance()
                heads = head = None
                _release_owned_ram(self, self._group_cost, '_group_cost')
        except BaseException as error:
            primary = error
            raise
        finally:
            heads = group = samples = live = head = None
            try:
                _release_owned_ram(self, self._group_cost, '_group_cost')
            except BaseException as cleanup:
                if primary is None:
                    raise
                primary.add_note('跨来源同刻组清理失败：'+type(cleanup).__name__)

    def _close_slot(self, slot):
        """关闭成功才解除责任。参数: 槽名。返回: None。异常: 原关闭错，槽保留以便重试。"""
        owner = getattr(self, slot)
        if owner is not None:
            owner.close()
            self._require_closed(owner)
            setattr(self, slot, None)

    @staticmethod
    def _require_closed(owner):
        """核实子资源真实关闭再撤槽。参数: owner。返回: None。异常: AnalysisError保留原责任。"""
        if not (getattr(owner, 'closed', False) or getattr(owner, '_closed', False)) or getattr(owner, '_held_cost', 0):
            raise AnalysisError('记录流子资源仍未关闭或持有费用')

    def close(self):
        """反向释放自有资源，保留失败槽供父会话重试。

        参数: 无。返回: None。异常: 原关闭/预算错误；不会抵销其他owner的费用。
        """
        if self._closed:
            return
        self._closing = True
        self._message_buffer.clear()
        self._segment_counts.clear()
        _release_owned_ram(self, self._message_cost, '_message_cost')
        self._close_slot('_pending')
        for stage in self._transform_stages:
            stage.close()
        self._transform_stages.clear()
        self._close_slot('_aggregations')
        self._close_slot('_diagnostics')
        self._close_slot('_direct_owner')
        self._close_slot('_exports')
        for index, owner in enumerate(self._cursors or ()):
            if owner is not None:
                owner.close()
                self._require_closed(owner)
                self._cursors[index] = None
        self._close_slot('_read')
        self._close_slot('_adapter')
        self._close_slot('_groups')
        self._close_slot('_sequences')
        self._close_slot('_event_durations')
        self._close_slot('_scope_calculations')
        self._close_slot('_windows')
        self._close_slot('_time_indexes')
        for index,owner in enumerate(self._rules or ()):
            if owner is not None:
                owner.close()
                self._require_closed(owner)
                self._rules[index]=None
        for index, pair in enumerate(self._messages or ()):
            if pair is not None:
                pair[1].close()
                self._require_closed(pair[1])
                self._messages[index] = None
        for index, owner in enumerate(self._calculations or ()):
            if owner is not None:
                owner.close()
                self._require_closed(owner)
                self._calculations[index] = None
        for pair in self._expressions or ():
            for index, owner in enumerate(pair):
                if owner is not None:
                    owner.close()
                    self._require_closed(owner)
                    pair[index] = None
        self._close_slot('_state')
        self._calculations = self._expressions = self._cursors = self._messages = self._plan = self._source_ends = None
        self._declaration_owner = None
        self._direct_binding = None
        self._rules=self._spool=self._requirements=None
        _release_owned_ram(self, self._group_cost, '_group_cost')
        _release_owned_ram(self, self._fixed_cost, '_fixed_cost')
        self._closed = True
