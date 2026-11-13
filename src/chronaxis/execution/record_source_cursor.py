"""按需读取一个来源并提供完整同刻组，供多来源按时间合并。

原始报文沿共同解码更新，解析数据沿既有SignalBatch。每次只保一个读取批
及尚未消费的同刻组，所有缓存逐笔付费；不建立磁盘历史或重复扫描输入。
"""

from collections import deque
from ..results.errors import AnalysisError, ResultClosedError
from ..results.spool import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..sources.can_spec import can_field_from_key
from ..sources.models import ReadRequest
from .history import _metadata_bytes
from .raw_signal_groups import RawSignalGroups
from .batch_signal_groups import BatchSignalGroups
from .text_can_reader import BudgetedTextCANSourceAdapter
from .memory_reader import BudgetedMemorySourceAdapter
from .csv_reader import BudgetedSignalCSVSourceAdapter
from .frame_capture import FrameDBCContext


def _queued_group_cost(sample_count):
    """返回现有待消费时间组费用，同时供 CSV 判断可交接的批容量。

    参数: sample_count 为组内样本数。返回: 字节估算。异常: 输入由内部计数保证。
    """
    return 4096 + sample_count * 8192


class RecordSourceCursor:
    """拥有来源、实际游标、同刻归组与已付费前瞻队列。"""

    def __init__(self, plan, source, definitions, values, clocks, budget, work_dir, *,
                 group_names=None, message_consumer=None, message_keys=(), observe_bounds=False, retain_frames=False, requirements=None):
        """建立所需来源，原始报文只初始化一次DBC，不读首帧。

        参数: 原计划/来源、该来源定义、数值和驱动别名集合、预算、专用新路径。
            retain_frames仅原帧导出请求时移交同次原帧仓；
            observe_bounds为无信号常量计算收集实际范围；group_names只含时序计算依赖；message_consumer/keys为实际逐消息消费者及定位。
        返回: 游标owner。异常: 原构造错误，恢复入口record_source_cleanup_owner。
        """
        self._budget = budget
        self.source_name = source.name
        self.frame_format_notices = ()
        self._definitions = definitions
        self._held_cost = self._fixed_cost = self._queue_cost = 0
        self._adapter = self._read = self._groups = self._pending = None
        self._queue = self._current = self.metadata = None
        self._current_cost = 0
        self._closed = self._closing = self._failed = self._finished = self._saw_eof = False
        self._reading_started = False
        self._raw = source.source_type in ('can_blf', 'can_asc', 'asc_or_blf', 'raw_can_csv')
        self._message_consumer = message_consumer
        self._observe_bounds=observe_bounds
        self._retain_frames=retain_frames
        self._raw_store=self._message_store=self._dbc_context=None
        self._read_identity=None
        self.source_kind=source.source_type
        self._capture_messages=False
        self._memory_first=(source.config.rows[0].time_ns+source.config.offset_ns
                            if observe_bounds and source.source_type=="memory" and source.config.rows else None)
        self.observed_start = self.observed_end = None
        try:
            _reserve_owned_ram(self, 131072 + 32*_metadata_bytes(definitions), '_fixed_cost')
            self._queue = deque()
            grouped = definitions if group_names is None else tuple(item for item in definitions if item.name in group_names)
            if grouped:
                self._groups = self._new(RawSignalGroups if self._raw else BatchSignalGroups,
                    'raw_groups_cleanup_owner' if self._raw else 'batch_groups_cleanup_owner',
                    budget, grouped, plan.dataset.session_id, self._enqueue,
                    **({'backend': plan.execution.backend,
                        'clock_only':tuple(item.name for item in grouped if item.name in clocks-values)} if self._raw else {}))
            options = dict(backend=plan.execution.backend)
            if self._raw:
                output=plan.outputs.can_frames
                if retain_frames and output is not None and output.resampling is not None:
                    self._dbc_context=self._new(FrameDBCContext,'frame_dbc_cleanup_owner',
                        source.config.dbc_path,output.rules,budget,cycle_periods=output.resampling.period_ns is None,integrity=plan.diagnostics.integrity)
                selected = {item.name: item for item in definitions}
                cycles = tuple(dict.fromkeys(can_field_from_key(selected[choice.driver].field)
                    for _, choice in plan.intervals.resolved
                    if choice.mode == 'dbc' and choice.driver in selected))
                cycles = tuple(dict.fromkeys((*cycles, *(can_field_from_key(item.field)
                    for item in definitions if item.valid_for_ns is None))))
                output=plan.outputs.signal_csv
                if output is not None and output.period_driver in selected:
                    cycles=tuple(dict.fromkeys((*cycles,can_field_from_key(selected[output.period_driver].field))))
                fields = tuple(dict.fromkeys(can_field_from_key(item.field) for item in definitions if item.name in clocks))
                keys = tuple(dict.fromkeys((*message_keys,
                    *((f.channel, f.frame_id, f.is_extended, f.is_fd) for f in fields))))
                options.update(work_dir=work_dir, retain_raw_frames=retain_frames, cycle_fields=cycles, metadata_fields=fields,
                    message_keys=keys, message_consumer=self._consume_message)
                files = source.config.input_paths if source.source_type=='can_blf' else source.config.inputs
                # 进程数是上限；单文件或上限1的接续在宿主内读取，解码政策单独传递。
                parallel = min(plan.execution.process_count,len(files)) > 1 or getattr(source.config,'file_merge','concatenate') == 'time_order'
                factory, recovery = BudgetedTextCANSourceAdapter, 'text_can_source_cleanup_owner'
                options['integrity']=plan.diagnostics.integrity
                options['trace']=False
                if self._dbc_context is not None:
                    options['database_context']=self._dbc_context
                if source.source_type == 'can_blf':
                    full = (source.config.input_check == 'full' or source.config.decode_scope == 'all') if requirements is None else requirements.input_check=='full'
                    scope = requirements.time_scope if requirements is not None else ('source' if full or grouped or observe_bounds or retain_frames else 'selected' if plan.dataset.domain is not None else 'none')
                    if source.config.file_merge=='time_order':
                        scope='source' if scope=='source' else 'selected'
                    # 低层调用可不传requirements，沿既有值、时钟和导出声明推导目标ID。
                    decode_ids = (requirements.decode_frame_ids if requirements is not None else tuple(sorted(
                        {can_field_from_key(item.field).frame_id for item in definitions if item.name in values}
                        | {key[1] for key in keys}
                        | {field.frame_id for field in (() if self._dbc_context is None else self._dbc_context.extra_fields)})))
                    options['blf_time_scope']=scope
                    options['legacy_blf_decode']=source.config.decode_policy=='legacy'
                    if not parallel:
                        options['serial_blf_policy']=source.config.decode_scope
                    if scope!='source':
                        options['time_frame_ids']=decode_ids
                    if not retain_frames:
                        if source.config.decode_scope=='all':
                            if not parallel:
                                # 串行all完成全部解码/值检查后，才按旧ID范围交付；并行保持原政策。
                                options['post_decode_frame_ids']=decode_ids
                        else:
                            options['emit_frame_ids']=decode_ids
                else:
                    if (requirements is not None and requirements.input_check == 'auto'
                            and source.source_type in ('can_asc','asc_or_blf') and not retain_frames):
                        options['time_frame_ids'] = requirements.decode_frame_ids
                    if (requirements is not None and requirements.input_check == 'auto'
                            and requirements.time_scope != 'source' and not retain_frames):
                        options['selected_ids'] = requirements.decode_frame_ids
                    if parallel and not retain_frames and requirements is not None:
                        options['emit_frame_ids']=requirements.decode_frame_ids
                if parallel:
                    options['process_count']=plan.execution.process_count
                adapter_definitions = tuple(item for item in definitions if item.name in values)
                names = ()
            else:
                factory, recovery = ((BudgetedMemorySourceAdapter, 'memory_source_cleanup_owner')
                    if source.source_type == 'memory' else (BudgetedSignalCSVSourceAdapter, 'csv_source_cleanup_owner'))
                adapter_definitions = definitions
                names = tuple(item.name for item in definitions)
                options.update(clock_only=tuple(item.name for item in definitions if item.name in clocks-values),
                               retain_original=False)
                if source.source_type == 'signal_csv':
                    # 单批可出现每样本一个时间组；给接收队列留出空间，实际费用仍由队列自己预约。
                    options['consumer_sample_bytes'] = _queued_group_cost(1)
            config=source.config
            # 公共原帧来源统一使用同次文本原帧仓；旧低层仓仍由其独立API管理。
            self.legacy_frame_storage = False
            if self._raw and source.source_type=='can_blf':
                from ..sources.text_can_spec import CANTextSpec
                from ..sources.blf import BLFSpec
                config=CANTextSpec(config.name,tuple(BLFSpec(p,config.offset_ns) for p in config.input_paths),
                    config.dbc_path,config.channel,config.timebase,config.decode_policy,
                    'full' if config.decode_scope=='all' else config.input_check,config.file_merge)
            self._adapter = self._new(factory, recovery, budget, config,
                                      plan.dataset.session_id, adapter_definitions, **options)
            self._read = self._adapter.iter_batches(ReadRequest(plan.dataset.session_id, names,
                None if plan.dataset.domain is None else plan.dataset.domain.start_ns,
                None if plan.dataset.domain is None else plan.dataset.domain.end_ns, plan.execution.batch_rows),
                **({"observe_bounds":True} if source.source_type=="signal_csv" and observe_bounds else {}))
            if self._raw:
                self.metadata = self._read.prepare_metadata()
                if self._groups is not None:
                    self._groups.configure_metadata(self.metadata['fields'])
                self._read_identity=self._read.identity
        except BaseException as error:
            _cleanup_owner(self, error, 'record_source_cleanup_owner', '记录流来源构造')
            raise
        finally:
            definitions = adapter_definitions = selected = fields = options = values = clocks = None

    def _consume_message(self, update):
        """同次解码先交逐消息消费者，再按需归组。参数: update。返回: None。异常: 原消费错误。"""
        try:
            if self._message_consumer is not None:
                self._message_consumer(update)
            if self._groups is not None:
                self._groups.consume(update)
        finally:
            update = None

    def _attach_raw_groups(self, definitions: tuple, session_id: str, backend: str) -> None:
        """候选绑定不适用时，在同一游标首帧前建立普通归组。

        参数: 本次实际所需定义、会话和明确后端。返回: None。异常: 已开始读取或构造错误。
        只用于无纯时钟/导出的直接积分候选；复用已加载DBC，不重开适配器。
        """
        if not self._raw or self._reading_started or self._groups is not None or self._closed or self._failed:
            raise ResultClosedError('只能在原始来源首次读取前附加普通归组')
        self._groups = self._new(RawSignalGroups, 'raw_groups_cleanup_owner',
            self._budget, definitions, session_id, self._enqueue, backend=backend)
        self._groups.configure_metadata(self.metadata['fields'])

    def _refresh_observed_bounds(self) -> None:
        """同步消息回调中取得同次读取已见范围。参数: 无。返回: None。异常: 原读取状态错误。

        不主动读下一条；EOF关闭后保留原游标已经记录的最终范围。
        """
        if self._raw and self._read is not None:
            self.observed_start, self.observed_end = self._read.observed_bounds

    def _new(self, factory, recovery, *args, **kwargs):
        """接实际未返回的子owner。参数: 工厂/属性/参数。返回: owner。异常: 原错。"""
        try:
            return factory(*args, **kwargs)
        except BaseException as error:
            self._pending = getattr(error, recovery, None)
            raise

    def _enqueue(self, group):
        """在上游释放组费用前接管必要组。参数: 完整组。返回: None。异常: 预算/取消。"""
        try:
            cost = _queued_group_cost(len(group.samples))
            _reserve_owned_ram(self, cost, '_queue_cost')
            self._queue.append((group, cost))
        finally:
            group = None

    def peek(self):
        """读取到下一个完整组或真实EOF，返回借用组。

        参数: 无。返回: DecodedTimeGroup或EOF的None。异常: 原输入/预算错误；失败后只清理。
        """
        if self._closed or self._closing or self._failed:
            raise ResultClosedError('记录流来源已关闭或失败')
        self._reading_started = True
        batch = None
        try:
            while self._current is None and not self._queue and not self._finished:
                try:
                    batch = next(self._read)
                except StopIteration:
                    if (self._raw and not self._read.exhausted) or not self._raw and not self._saw_eof:
                        raise AnalysisError('来源未交付真实完整EOF')
                    if self._raw:
                        observed = self._read.observation
                        self.observed_start, self.observed_end = observed.first_ns, observed.last_ns
                        self._retain_frame_notices()
                    if self._retain_frames:
                        self._read.take_raw_store(self,'_raw_store')
                    if self._capture_messages:
                        self._read.take_message_store(self,'_message_store')
                    self.metadata = None
                    self._close_slot('_read')
                    self._close_slot('_adapter')
                    if self._groups is not None:
                        self._groups.finish()
                    self._finished = True
                    break
                self._saw_eof = batch.source_eof
                if self._raw:
                    self.observed_start,self.observed_end = self._read.observed_bounds
                if not self._raw:
                    for column in batch.series.values():
                        if len(column.time_ns):
                            first,last = int(column.time_ns[0]),int(column.time_ns[-1])
                            self.observed_start = first if self.observed_start is None else min(first,self.observed_start)
                            self.observed_end = last if self.observed_end is None else max(last,self.observed_end)
                    if batch.observed_end_ns is not None:
                        self.observed_end = int(batch.observed_end_ns)
                    if self._observe_bounds:
                        self.observed_start=(self._memory_first if self._memory_first is not None else
                            getattr(self._read,'observed_start',self.observed_start))
                    if self._groups is not None:
                        self._groups.consume(batch)
                elif batch.series:
                    raise AnalysisError('原始记录流不应额外构造普通信号列')
                batch = None
            if self._current is None and self._queue:
                self._current, self._current_cost = self._queue.popleft()
            return self._current
        except BaseException as error:
            self._failed = True
            error.record_source_cleanup_owner = self
            raise
        finally:
            batch = column = observed = None

    def advance(self):
        """消费当前组并释放其费用，不主动读取下一组。参数: 无。返回: None。异常: 预算/取消。"""
        self._current = None
        cost, self._current_cost = self._current_cost, 0
        _release_owned_ram(self, cost, '_queue_cost')

    def _retain_frame_notices(self):
        """在同次真实EOF后保留已核DBC帧型提示，不借清单声明代替读取。

        参数: 无。返回: None。异常: 已核元数据不一致或预算失败；最高游标负责清理。
        只复制实际差异及原绑定，不保留完整READY、样本或历史仓。
        """
        from ..results.can_metadata import CANFrameFormatNotice
        facts = self._read.runtime_metadata['fields']
        notices = tuple(fact for fact in facts if 'frame_format_compatibility' in fact)
        projection = getattr(self._read, '_binding_projection', None)
        automatic = {} if projection is None else projection.compatibility_fields
        if not notices and not automatic:
            return
        _reserve_owned_ram(self, 8192 + 32 * _metadata_bytes((notices, self._definitions)), '_fixed_cost')
        result = []
        for definition in self._definitions:
            field = can_field_from_key(definition.field)
            recorded = False
            for fact in notices:
                if field != type(field)(**fact['locator']):
                    continue
                notice = fact['frame_format_compatibility']
                extended = field.is_extended if field.is_extended is not None else automatic.get(field)
                if extended is None:
                    continue
                result.append(CANFrameFormatNotice(definition.name, field.channel,
                    field.signal, field.frame_id, extended, notice['dbc_is_fd'],
                    notice['requested_is_fd'], notice['code']))
                recorded = True
            if field in automatic and not recorded:
                result.append(CANFrameFormatNotice(definition.name, field.channel, field.signal,
                    field.frame_id, automatic[field], True, False, 'dbc_fd_classic_selector'))
        self.frame_format_notices = tuple(result)

    @staticmethod
    def _require_closed(owner):
        """关闭未完成时保留槽。参数: 子owner。返回: None。异常: AnalysisError。"""
        if not (getattr(owner, 'closed', False) or getattr(owner, '_closed', False)) or getattr(owner, '_held_cost', 0):
            raise AnalysisError('来源子资源仍未关闭或持有费用')

    def _close_slot(self, slot):
        """成功关闭后才撤槽。参数: 槽名。返回: None。异常: 原关闭错。"""
        owner = getattr(self, slot)
        if owner is not None:
            owner.close()
            self._require_closed(owner)
            setattr(self, slot, None)

    def close(self):
        """按责任释放当前批/队列和输入；提前关闭不交付末组。

        参数: 无。返回: None。异常: 原关闭/预算错，可从同一owner重试。
        """
        if self._closed:
            return
        self._closing = True
        self._close_slot('_pending')
        self._close_slot('_read')
        self._close_slot('_adapter')
        self._close_slot('_groups')
        self._close_slot('_raw_store')
        self._close_slot('_message_store')
        self._close_slot('_dbc_context')
        self.metadata = self._current = self._queue = self._message_consumer = None
        self._definitions = self.frame_format_notices = ()
        _release_owned_ram(self, self._queue_cost, '_queue_cost')
        _release_owned_ram(self, self._fixed_cost, '_fixed_cost')
        self._closed = True
