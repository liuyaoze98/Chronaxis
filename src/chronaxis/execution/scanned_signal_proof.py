"""为纯CAN逐消息计划保存实际完成证明，不保存无人使用的普通样本文件。

输入为原计划、实际需求字段的预算CAN读取和同一请求。显式all诊断仍构造原
HistorySample并编码为规范字节，只增量计算stream_sha256，不落盘。
默认直接累计不生成普通信号样本，只在唯一EOF处核协议，并按真实时间范围保存原时间与
所需记录的独立内容指纹。显式all诊断保原规范样本摘要；有贡献明细时仍核消息仓。
真实读取耗尽、进程结束、消息仓移交及read关闭后才开放有限证明。该证明明确是
扫描流证据，不是DecodedSourceEvidence，也不提供磁盘history_sha256或文件EOF。
旧公开历史绑定、普通分析和原始导出不使用本模块。消息计算直接消费原批或读取实际消息仓。
所有新状态、当前批、单行编码和未关闭资源先计预算，失败保同一最高owner供重试。
"""

from dataclasses import dataclass
from collections.abc import Mapping
from hashlib import sha256
import heapq

from ..core.numeric import ScalarValue
from ..core.types import QualityFlag, SignalDType
from ..planning.plan import AnalysisPlan
from ..planning.models import SourcePlan
from ..planning.input_requirements import collect_input_requirements
from ..results.errors import AnalysisError, ResultClosedError, ResultFormatError
from ..results.spool import _cleanup_owner, _reserve_owned_ram, _release_owned_ram
from ..sources.models import ReadRequest, SignalBatch
from ..sources.protocol import BatchValidator
from .bindings import _fingerprint, require_decoded_source_contract
from .can_reader import BudgetedLegacyCANSourceAdapter
from .can_batch_reader import CANBatchObservationRead
from .history import _metadata_bytes, _pending_bytes, _batch_bytes
from .history_records import HistorySample, HistoryProgress, estimate_record_bytes, encode_record
from .observed_ingestion import SourceScanObservation


def can_message_only(plan):
    """选择没有普通样本消费者的全CAN计划。参数: 原AnalysisPlan。返回: bool。异常: 错误模型属性错误。"""
    return bool(plan.message_calculations and all(source.source_type == 'can_blf' for source in plan.sources)
        and not plan.rules and not plan.windows and not plan.calculations
        and plan.outputs.signal_csv is None and plan.outputs.can_frames is None)


def _source_contract(source):
    """提取有限原CAN配置事实供替换检查。参数: 原SourcePlan。返回: 冻结tuple。异常: 非CAN属性错误。"""
    config = source.config
    original = (source.name, source.source_type, source.input_identity, source.time_unit, source.timezone_text,
            config.name, str(config.path), str(config.dbc_path), config.channel, config.legacy_profile,
            config.timebase, config.unit, config.offset_ns)
    # 旧all指纹严格保持原有限tuple；新方式显式进入完成证据，不借用旧全解码身份。
    contract = original if config.decode_scope == 'all' else original + (('decode-scope-v1', config.decode_scope),)
    return contract if config.input_check == 'full' or config.decode_scope == 'all' else contract + (('input-check-v1', config.input_check),)


@dataclass(frozen=True)
class ScannedSignalFacts:
    """保存已完成首遍验证的有限事实；stream摘要不声称有对应磁盘文件。"""

    source: str
    session_id: str
    source_contract_sha256: str
    description_sha256: str
    request_sha256: str
    stream_sha256: str
    progress_count: int
    sample_count: int
    projected_aliases: tuple[str, ...]
    completion: HistoryProgress
    observation: SourceScanObservation


@dataclass(frozen=True)
class ScannedInputFacts:
    """记录纯消息读取的实际输入摘要，不声称生成或验证过普通信号样本。"""

    source: str  # 本次真实来源。
    session_id: str  # 原会话。
    source_contract_sha256: str  # 静态来源与解码策略。
    description_sha256: str  # 实际需求字段描述。
    request_sha256: str  # 无普通样本的真实读取请求。
    original_timestamps_sha256: str | None  # source为全时间SHA，其他范围明确未采集。
    retained_records_sha256: str  # 实际保留记录的长度前缀与JSON原字节。
    required_aliases: tuple[str, ...]  # 实际需要的消息字段别名。
    retained_record_count: int  # 保留的原消息数，不是样本数。
    completion: HistoryProgress  # 仅内部EOF协议标记；不编码成样本流摘要。
    observation: SourceScanObservation  # 原读取数量及明确时间范围。
    time_scope: str = 'source'  # 未采集时间不能借用旧全时间证明。
    input_check: str = 'full'  # 实际固定的原帧检查策略。


class ScannedCANSignals:
    """拥有一个实际CAN read、有限验证状态和未移交消息仓，不拥有普通历史文件。"""

    def __init__(self, declarations, source_plan, adapter, request, *, input_only=False):
        """核实际投影和原来源后预付状态。

        参数: 四项原对象；input_only仅纯消息空样本请求，改存实际输入指纹。
        返回: 读取与证明owner。异常: 原合同/预算错误，不打开第二次来源。
        """
        if (not isinstance(source_plan, SourcePlan) or source_plan.source_type != 'can_blf'
                or type(adapter) is not BudgetedLegacyCANSourceAdapter or type(request) is not ReadRequest
                or not adapter.batch_read or adapter.retain_raw_frames):
            raise TypeError('扫描证明只接真实有界CAN来源、原请求且无原始导出')
        if type(input_only) is not bool or input_only and (request.signal_names or adapter.capture_message_updates
                or adapter._update_consumer is None):
            raise ValueError('输入证明仅接真实直接累计的空普通样本请求')
        self._declarations, self._source_plan, self._adapter, self._request = declarations, source_plan, adapter, request
        self._input_only = input_only
        self._projected_aliases = request.signal_names
        self._required_aliases = None
        self._input_fingerprints = None
        self._budget, self._config = adapter.budget, source_plan.config
        self._fixed_cost = self._pending_cost = self._append_cost = self._record_cost = self._runtime_cost = self._held_cost = 0
        self._read = self._batch = self._message_store = None
        self._description = self._validator = self._definitions = self._contract = None
        self._hash = self._expected_sha = self._completion = self._facts = self._facts_sha = None
        self._counts = self._expected_counts = (0, 0)
        self._runtime_metadata = self._read_identity = None
        self._started = self._finished = self._closed = self._closing = self._failed = False
        self._capture_message_updates = adapter.capture_message_updates
        self._decode_scope, self._decode_frame_ids = adapter.decode_scope, None
        self.retain_raw_frames = False
        description = source = contract_request = None
        try:
            # 输入定义借用原对象；所有新索引、验证器、规范记录及摘要空间分别预付。
            description = adapter.describe()
            cost = 65536 + 32 * _metadata_bytes((description, request, declarations))
            _reserve_owned_ram(self, cost, '_fixed_cost')
            self._required_aliases = tuple(item.name for item in adapter.signals)
            # 借用固定tuple的存活由本扫描已付描述/声明空间覆盖，adapter关闭后仍可核证据。
            self._decode_frame_ids = adapter.decode_frame_ids
            self._description, self._contract = description, _source_contract(source_plan)
            self._validator = BatchValidator(description, request)
            self._hash = sha256()
            self._expected_sha = self._hash.hexdigest()
            self._max_line_bytes = max(1, self._budget.memory_budget_bytes // 256)
            self._require_contract()
            source = next(item for item in declarations.sources if item.name == source_plan.name)
            # 这里只核纯合同；空字段来源仍须由consume取得真实全帧观测和EOF。
            # DBC/消息字段有实际用途，普通样本投影可以为空；分别核需要的字段描述与读请求。
            contract_request = ReadRequest(request.session_id, self._required_aliases,
                request.domain_start_ns, request.domain_end_ns, request.batch_rows)
            self._definitions = require_decoded_source_contract(declarations, source, description, contract_request)
        except BaseException as exc:
            self._failed = True
            _cleanup_owner(self, exc, 'scanned_can_signals_cleanup_owner', 'CAN扫描证明构造')
            raise
        finally:
            # 构造失败可能已退款；异常栈不再保留本次新建请求和别名元组。
            description = source = contract_request = None

    def _require_contract(self, *, completed=False):
        """核原对象与实际本流状态，完成后不再访问已关闭adapter。参数: completed。返回: None。异常: 替换/失效错误。"""
        if self._closed or self._closing or self._failed:
            raise ResultClosedError('CAN扫描证明已关闭、清理或失败')
        source, adapter = self._source_plan, self._adapter
        declared = next((item for item in self._declarations.sources if item.name == source.name), None)
        if (source.config is not self._config or _source_contract(source) != self._contract
                or declared is None or declared.input_identity != source.input_identity
                or declared.timebase != self._config.timebase or declared.offset_ns != self._config.offset_ns
                or self._request.session_id != self._declarations.session_id
                or self._request.signal_names != self._projected_aliases
                or self._config.decode_scope == 'all' and self._projected_aliases != tuple(
                    item.name for item in self._declarations.signals if item.source == source.name)
                or self._validator.description is not self._description or self._validator.request is not self._request
                or self._counts != self._expected_counts or self._hash.hexdigest() != self._expected_sha):
            raise ValueError('CAN扫描证明的原来源、完整投影、请求、验证器或计数摘要已改变')
        if not completed:
            adapter._ensure_open()
            if (adapter.spec is not self._config or adapter.budget is not self._budget
                    or adapter.session_id != self._request.session_id or adapter.describe() != self._description
                    or adapter.capture_message_updates is not self._capture_message_updates
                    or adapter.decode_scope != self._decode_scope
                    or adapter.decode_frame_ids != self._decode_frame_ids
                    or adapter.retain_raw_frames or not adapter.batch_read):
                raise ValueError('CAN扫描证明的实际adapter与原合同不符')

    def _digest_record(self, record):
        """编码一条原规范记录并更新流摘要。参数: HistorySample/Progress。返回: None。异常: 原模型/编码/预算错误。"""
        payload = primary = None
        try:
            _reserve_owned_ram(self, estimate_record_bytes(record), '_record_cost')
            payload = encode_record(record, self._max_line_bytes)
            self._hash.update(payload)
        except BaseException as exc:
            primary = exc
            raise
        finally:
            record = payload = None
            self._release_temporary('_record_cost', primary)

    def _release_temporary(self, slot, primary):
        """归还实际临时费，清理错误不覆盖主错。参数: 费用槽及原异常。返回: None。异常: 无主错时释放错误。"""
        try:
            _release_owned_ram(self, getattr(self, slot), slot)
        except BaseException as cleanup:
            if primary is None:
                raise
            primary.add_note('扫描临时费用清理附加失败: ' + type(cleanup).__name__)

    def _accept(self, batch):
        """按原历史顺序验证并编码一批，不写磁盘。参数: 原SignalBatch。返回: None。异常: 原协议/样本/预算错。"""
        columns = heap = column = record = value = original = progress = None
        definition = labels = logical = physical = primary = None
        try:
            if type(batch) is not SignalBatch or batch.source != self._source_plan.name:
                raise ValueError('扫描样本批不属于原来源')
            if self._input_only:
                # 直接累计在read内部消费所有消息；这里只接受空的唯一EOF，不造ScalarValue/样本或摘要。
                if batch.series or not batch.source_eof or self._completion is not None:
                    raise ValueError('纯消息输入证明不能混入普通样本或非最终批')
                self._validator.accept(batch)
                self._completion = HistoryProgress(0, batch.source, batch.session_id,
                    0, batch.watermark_ns, True, batch.observed_end_ns)
                self._counts = self._expected_counts = (1, 0)
                return
            batch_index, total = self._counts
            if batch_index >= 2 ** 63 - 1 or total + batch.sample_count >= 2 ** 63:
                raise OverflowError('扫描批次/样本计数超过int64')
            growth = batch.sample_count * 256 + len(batch.series) * 512
            _reserve_owned_ram(self, _batch_bytes(batch) + _pending_bytes(self._validator)
                + growth + 4096 + len(batch.series) * 512, '_append_cost')
            self._validator.accept(batch)
            pending = _pending_bytes(self._validator)
            if pending < self._pending_cost:
                _release_owned_ram(self, self._pending_cost - pending, '_pending_cost')
            else:
                retained = pending - self._pending_cost
                self._append_cost -= retained
                self._pending_cost += retained
            columns = tuple(batch.series.values())
            heap = [(int(item.time_ns[0]), int(item.sequence[0]), order, 0)
                    for order, item in enumerate(columns) if len(item.time_ns)]
            heapq.heapify(heap)
            while heap:
                time, sequence, order, index = heapq.heappop(heap)
                column = columns[order]
                physical, valid = column.values[index].item(), bool(column.valid[index])
                original_present = column.original_values is not None
                original = column.original_values[index] if original_present else None
                logical = column.labels[physical] if valid and column.dtype is SignalDType.ENUM else physical
                if not valid and original_present:
                    logical = original
                value = ScalarValue(logical, column.dtype, valid, QualityFlag(int(column.quality[index])), column.labels)
                record = HistorySample(batch_index, column.name, time, sequence, physical, value,
                    column.unit, column.source_ref[index], original_present, original)
                definition = self._definitions[record.name]
                labels = tuple(dict.fromkeys(label for _, label in definition.choices)) if definition.dtype is SignalDType.ENUM else ()
                if (record.source_ref.field != definition.field or record.value.dtype is not definition.dtype
                        or record.unit != definition.unit or record.value.labels != labels):
                    raise ResultFormatError('实际扫描样本与当前绑定契约不符')
                self._digest_record(record)
                if index + 1 < len(column.time_ns):
                    heapq.heappush(heap, (int(column.time_ns[index + 1]), int(column.sequence[index + 1]), order, index + 1))
            progress = HistoryProgress(batch_index, batch.source, batch.session_id,
                batch.sample_count, batch.watermark_ns, batch.source_eof, batch.observed_end_ns)
            self._digest_record(progress)
            self._counts = self._expected_counts = (batch_index + 1, total + batch.sample_count)
            self._expected_sha = self._hash.hexdigest()
            if batch.source_eof:
                self._completion = progress
        except BaseException as exc:
            primary = exc
            raise
        finally:
            batch = columns = heap = column = record = value = original = progress = None
            definition = labels = logical = physical = None
            self._release_temporary('_append_cost', primary)

    def _adopt(self, exc):
        """接实际未返回的read，避免丢失构造失败资源。参数: 原异常。返回: None。异常: 无正常新增异常。"""
        if self._read is None:
            self._read = getattr(exc, 'can_observation_read_cleanup_owner', None)
        if self._read is None and self._message_store is None:
            self._message_store = getattr(exc, 'decoded_message_store_cleanup_owner', None)

    def _close_read(self):
        """关闭本次真实read，失败保留责任。参数: 无。返回: None。异常: 原关闭错误。"""
        self._batch = None
        if self._read is not None:
            self._read.close()
            if not self._read.closed:
                raise AnalysisError('扫描read关闭未完成')
            self._read = None

    def consume(self):
        """完整扫描一次并在真实EOF和关闭后发布证明。参数: 无。返回: None。异常: 原错误及最高恢复owner。"""
        self._require_contract(completed=self._finished)
        if self._finished:
            return
        if self._started:
            raise ResultClosedError('CAN扫描证明不能重复开始读取')
        fact = metadata = store = observation = facts = None
        try:
            self._started = True
            self._read = self._adapter.iter_batches_with_observation(self._request)
            if type(self._read) is not CANBatchObservationRead:
                raise TypeError('扫描证明必须消费本次实际CANBatchObservationRead')
            while True:
                self._require_contract()
                try:
                    self._batch = next(self._read)
                except StopIteration:
                    break
                self._require_contract()
                self._accept(self._batch)
                self._batch = None
            self._require_contract()
            completion = self._completion
            if completion is None or not completion.source_eof or not self._validator.ended:
                raise ValueError('扫描证明缺少原流完整EOF')
            fact = self._read.observation
            if (not self._read.exhausted or self._read.failed or fact.request is not self._request
                    or fact.read_identity != self._read.identity or fact.source != self._source_plan.name
                    or fact.session_id != self._request.session_id or not fact.source_eof
                    or fact.last_ns != completion.observed_end_ns):
                raise ValueError('CAN扫描完成事实不属于同一次真实读取')
            metadata = self._read.runtime_metadata
            _reserve_owned_ram(self, 65536 + 32 * _metadata_bytes(metadata), '_runtime_cost')
            self._runtime_metadata, self._read_identity = metadata, fact.read_identity
            if self._read.capture_message_updates is not self._capture_message_updates:
                raise ValueError('扫描read的原消息捕获开关已改变')
            if self._capture_message_updates:
                self._read.take_message_store(self, '_message_store')
                store = self._message_store
                if (store.closed or store.state != 'sealed' or not store.sparse_sequences
                        or store.count > fact.row_count or store._last_sequence >= fact.row_count
                        or store.source_name != fact.source or store.session_id != fact.session_id
                        or store.read_identity != fact.read_identity or store.decoder_profile != metadata['profile']):
                    raise ValueError('扫描消息仓不属于本次完整输入')
            start = self._description.observation_start_ns
            observation = SourceScanObservation(fact.source, fact.session_id, fact.first_ns, fact.last_ns,
                fact.row_count, (fact.first_ns if start is None else start) if fact.time_scope == 'source' else None,
                completion.observed_end_ns if fact.time_scope == 'source' else None, True,
                fact.time_scope, fact.retained_record_count, fact.full_check_count)
            if self._input_only:
                self._input_fingerprints = self._read.input_fingerprints
                timestamp_sha, records_sha, frame_count, retained_count = self._input_fingerprints
                if frame_count != fact.row_count:
                    raise ValueError('实际输入指纹原帧数与观测不一致')
                facts = ScannedInputFacts(fact.source, fact.session_id, _fingerprint(self._contract),
                    _fingerprint(self._description), _fingerprint(self._request), timestamp_sha,
                    records_sha, self._required_aliases, retained_count, completion, observation,
                    self._adapter.time_scope, self._adapter.input_check)
            else:
                facts = ScannedSignalFacts(fact.source, fact.session_id, _fingerprint(self._contract),
                    _fingerprint(self._description), _fingerprint(self._request), self._expected_sha,
                    self._counts[0], self._counts[1], self._request.signal_names, completion, observation)
            self._close_read()
            self._facts = facts
            self._facts_sha = _fingerprint(facts)
            self._finished = True
        except BaseException as exc:
            self._failed = True
            self._adopt(exc)
            exc.scanned_can_signals_cleanup_owner = self
            raise
        finally:
            fact = metadata = store = observation = facts = None

    def assert_current(self, source, description, request, declarations):
        """核活的完整扫描与调用者原合同。参数: 四项原对象。返回: None。异常: 替换或未完成证明。"""
        self._require_contract(completed=True)
        if (not self._finished or self._facts is None or self._source_plan is not source
                or self._description is not description or self._request is not request
                or self._declarations is not declarations or self._facts.completion != self._completion
                or self._facts.description_sha256 != _fingerprint(description)
                or self._facts.request_sha256 != _fingerprint(request)):
            raise ValueError('扫描证明未完成或不是当前原计划及完整样本流')
        if self._input_only:
            if (type(self._facts) is not ScannedInputFacts or self._input_fingerprints is None
                    or (self._facts.original_timestamps_sha256, self._facts.retained_records_sha256)
                        != self._input_fingerprints[:2]
                    or self._facts.required_aliases != self._required_aliases
                    or self._facts.retained_record_count != self._input_fingerprints[3]):
                raise ValueError('输入证明与实际已验证字节流不符')
        elif (self._facts.stream_sha256 != self._expected_sha
                or (self._facts.progress_count, self._facts.sample_count) != self._counts):
            raise ValueError('样本扫描证明与实际计数摘要不符')
        if _fingerprint(self._facts) != self._facts_sha:
            raise ValueError('扫描证明的完成事实已被替换')

    @property
    def facts(self):
        """借读真实完成的扫描事实。参数: 无。返回: ScannedSignalFacts。异常: 原生命周期/合同错误。"""
        self.assert_current(self._source_plan, self._description, self._request, self._declarations)
        return self._facts

    @property
    def observation(self):
        """读取全部原帧观测。参数: 无。返回: SourceScanObservation。异常: 未完成/失效证明。"""
        return self.facts.observation

    @property
    def runtime_metadata(self):
        """借读同次READY。参数: 无。返回: 冻结元数据。异常: 未完成/失效证明。"""
        self.facts
        return self._runtime_metadata

    @property
    def read_identity(self):
        """读取同次真实read标识。参数: 无。返回: str。异常: 未完成/失效证明。"""
        self.facts
        return self._read_identity

    @property
    def capture_message_updates(self):
        """读取原捕获开关。参数: 无。返回: bool。异常: 无。"""
        return self._capture_message_updates

    @property
    def closed(self):
        """读取实际关闭状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    @property
    def finished(self):
        """读取成功扫描事实，不代替当前活性检查。参数: 无。返回: bool。异常: 无。"""
        return self._finished

    def take_message_store(self, receiver, slot='_message_store'):
        """先安装父实际槽再解除本消息仓责任。参数: 同预算父及空槽。返回: 原仓。异常: 原移交错误。"""
        self.facts
        store = self._message_store
        if (not self._capture_message_updates or store is None or getattr(receiver, '_budget', None) is not self._budget
                or type(slot) is not str or not slot.startswith('_') or not hasattr(receiver, slot)
                or getattr(receiver, slot) is not None):
            raise ValueError('扫描消息仓移交需同预算空父槽且只能一次')
        try:
            setattr(receiver, slot, store)
        except BaseException as exc:
            exc.scanned_can_signals_cleanup_owner = self
            raise
        finally:
            if getattr(receiver, slot, None) is store:
                self._message_store = None
        return store

    def close(self):
        """关闭真实read/未移交仓后归还本owner费用。参数: 无。返回: None。异常: 持续失败保本最高owner。"""
        if self._closed:
            return
        self._closing = True
        try:
            self._close_read()
            if self._message_store is not None:
                self._message_store.close()
                if not self._message_store.closed:
                    raise AnalysisError('扫描消息仓未完成关闭')
                self._message_store = None
            self._facts = self._facts_sha = self._runtime_metadata = self._read_identity = None
            self._definitions = self._validator = self._description = self._contract = self._hash = None
            self._decode_frame_ids = None
            self._input_fingerprints = self._required_aliases = self._projected_aliases = None
            self._completion = self._counts = self._expected_counts = self._expected_sha = None
            self._declarations = self._source_plan = self._adapter = self._request = self._config = None
            for slot in ('_record_cost', '_append_cost', '_pending_cost', '_runtime_cost', '_fixed_cost'):
                _release_owned_ram(self, getattr(self, slot), slot)
            self._closed = self._held_cost == 0
        except BaseException as exc:
            exc.scanned_can_signals_cleanup_owner = self
            raise


@dataclass(frozen=True)
class _ScannedBindings:
    """仅用于纯消息运行清单的已扫描定义，不能交给普通历史表达式执行入口。"""

    declarations: object
    sources: tuple[ScannedSignalFacts | ScannedInputFacts, ...]
    identity: str

    @property
    def signals(self):
        """借用全部原信号定义。参数: 无。返回: 冻结tuple。异常: 无。"""
        return self.declarations.signals

    def resolve(self, name):
        """解析原定义供清单角色核对。参数: 别名。返回: SignalDefinition。异常: 原声明解析错误。"""
        return self.declarations.resolve(name)


class ScannedBindingLease:
    """拥有已完成扫描的有限运行清单证明；借用scan但不关闭它们。"""

    def __init__(self, plan, scans, descriptions, requests, budget):
        """核真实扫描后建立版本化绑定摘要。参数: 同次原计划及来源对象。返回: lease。异常: 合同/预算错误。"""
        if (type(plan) is not AnalysisPlan or not can_message_only(plan) or type(scans) is not tuple
                or len(scans) != len(plan.sources) or any(type(scan) is not ScannedCANSignals for scan in scans)
                or type(descriptions) is not tuple or len(descriptions) != len(plan.sources)
                or not isinstance(requests, Mapping) or set(requests) != {source.name for source in plan.sources}):
            raise TypeError('扫描绑定仅接全CAN纯消息计划及完整实际扫描')
        self._budget, self._plan, self._scans = budget, plan, scans
        self._descriptions, self._requests = descriptions, requests
        self._fixed_cost = self._held_cost = 0
        self._bindings = None
        self._closed = self._closing = False
        facts = identity = source = scan = description = declared = None
        requirements = needed = aliases = expected_fields = expected_samples = prefix = None
        try:
            _reserve_owned_ram(self, 65536 + 32768 * len(scans)
                + 32 * _metadata_bytes((plan.bindings, plan.message_calculations,
                    descriptions, tuple(requests.values()))), '_fixed_cost')
            facts = []
            requirements = collect_input_requirements(plan)
            for source, scan, description in zip(plan.sources, scans, descriptions):
                if scan._budget is not budget:
                    raise ValueError('扫描绑定必须使用同一实际budget')
                scan.assert_current(source, description, requests[source.name], plan.bindings)
                needed = requirements.for_source(source.name)
                aliases = tuple(item.name for item in plan.bindings.signals if item.source == source.name)
                expected_fields = aliases if source.config.decode_scope == 'all' else needed.required_aliases
                expected_samples = aliases if source.config.decode_scope == 'all' else needed.ordinary_sample_aliases
                if (requests[source.name].signal_names != expected_samples
                        or tuple(item.name for item in description.fields) != expected_fields):
                    raise ValueError('扫描投影未恰好覆盖本计划实际需求')
                declared = next(item for item in plan.bindings.sources if item.name == source.name)
                require_decoded_source_contract(plan.bindings, declared, description, requests[source.name])
                facts.append(scan.facts)
            facts = tuple(facts)
            prefix = 'scanned-input-binding-v2:' if any(scan._input_only for scan in scans) else 'scanned-signal-binding-v1:'
            identity = prefix + _fingerprint((plan.bindings.identity, facts))
            self._bindings = _ScannedBindings(plan.bindings, facts, identity)
        except BaseException as exc:
            _cleanup_owner(self, exc, 'scanned_binding_lease_cleanup_owner', '扫描绑定构造')
            raise
        finally:
            facts = identity = source = scan = description = declared = None
            requirements = needed = aliases = expected_fields = expected_samples = prefix = None

    @property
    def bindings(self):
        """借读当前完整扫描绑定，拒绝失效scan。参数: 无。返回: 私有绑定。异常: 状态/原合同错误。"""
        if self._closed or self._closing or self._bindings is None:
            raise ResultClosedError('扫描绑定未完成或已关闭')
        for source, scan, description in zip(self._plan.sources, self._scans, self._descriptions):
            scan.assert_current(source, description, self._requests[source.name], self._plan.bindings)
        return self._bindings

    @property
    def closed(self):
        """读取真实关闭状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    def close(self):
        """释放自有证明，不关闭借用scan。参数: 无。返回: None。异常: 预算释放错误可重试。"""
        if self._closed:
            return
        self._closing = True
        self._bindings = self._plan = self._scans = self._descriptions = self._requests = None
        _release_owned_ram(self, self._fixed_cost, '_fixed_cost')
        self._closed = self._held_cost == 0
