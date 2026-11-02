"""把本次真实来源读取与同一历史写入关联，保留有限的原行观测证明。

ObservedSourceScan借用building DecodedHistoryStore、原SourcePlan、预算来源
适配器和原ReadRequest。构造只校验与预约有限描述；consume才创建本scan独占的
read，并把每批原样直接history.append，不向调用方yield、不保留批次列表或重扫
输入。每次追加前后核对本来源预期计数和摘要，其他来源可独立推进，不能把另一次
恰好使用相同请求的read或手造CSVObservation当作本历史首端证据。

CSV使用自有的真实CSVObservationRead，真正StopIteration后复制其首末原时间行
和行数；CAN使用同次CANObservationRead，保全部原帧的范围、READY与封口暂存；
若原adapter显式capture_message_updates开启，同次decoded仓也在read.close前
先安装本scan责任槽，再由take_message_store移交；不开启时不创建消息仓或新费用。
memory沿实际原SourceSpec.rows以O(1)取得首末时间和len，offset只施加
一次。空投影仍计原行，全空与单点明确区分。observed_start优先保留原描述的明确
开始端，否则为实际first；observed_end使用本历史实际EOF进度，memory已声明的
延长终点不会被last覆盖或再次偏移。非空未知终点拒绝，不猜测周期。

finished要求原read真正耗尽、完整EOF已成功写入此历史、来源合同保持、全部本次
读取资源关闭成功，随后才开放SourceScanObservation、history_sha256和counts。
这些是本scan写入时的有限快照，后继还须核对当前实际历史及绑定，快照不代替
磁盘SHA重新校验。构造和清理失败保最高observed_source_scan_cleanup_owner。

本owner只计有限身份、请求、描述及快照，原SourceSpec.rows和raw_config不深遍历
或复制，原输入由来源预算承担。close关闭自有read及未移交原帧/消息仓，释放自身费用，不关闭
借用history、adapter或其他read，不删除文件。不改历史格式、默认来源清理路径、
数值核、同步规则或旧CAN链，也不声称覆盖整个进程RSS。
"""

# 事实只用冻结小模型，来源仍走实际预算入口，不重新解释或归一化原行。
from dataclasses import dataclass
from ..core.models import SourceSpec
from ..core.validation import require_identifier
from ..timebase.conversion import checked_add_ns, require_int64_ns
from ..planning.models import SourcePlan
from ..sources.csv_spec import SignalCSVSpec
from ..sources.can_spec import LegacyCANSpec
from ..sources.text_can_spec import CANTextSpec
from .text_can_reader import BudgetedTextCANSourceAdapter,TextCANObservationRead
from ..sources.models import ReadRequest
from ..results.errors import AnalysisError, ResultClosedError
from ..results.spool import _cleanup_owner, _reserve_owned_ram, _release_owned_ram
from .csv_observation import CSVObservationRead
from .csv_reader import BudgetedSignalCSVSourceAdapter
from .can_reader import BudgetedLegacyCANSourceAdapter, CANObservationRead
from .memory_reader import BudgetedMemorySourceAdapter
from .history import DecodedHistoryStore, _metadata_bytes


@dataclass(frozen=True)
class SourceScanObservation:
    """保留本scan实际原行事实及来源声明允许的观测范围，不证明来源之间同步。

    first_ns、last_ns及row_count描述原行；observed_start_ns、observed_end_ns
    保留描述与实际完成进度。空来源仍可有声明边界，但row_count必须为0且原行
    首末均为None，后继不能把声明边界解释成真实原行或常量规则的观测证据。
    """

    source: str  # 实际来源名称。
    session_id: str  # 原请求与完成进度的同一会话。
    first_ns: int | None  # 实际首条原时间行，转换及offset后的整数ns。
    last_ns: int | None  # 实际末条原时间行，全空为None。
    row_count: int  # 原时间行总数，包含空投影行而不按信号样本数计算。
    observed_start_ns: int | None  # 明确描述start优先，否则实际first。
    observed_end_ns: int | None  # 实际EOF进度的observed_end，已完成一次时钟映射。
    source_eof: bool  # 完整来源耗尽并已写入本history，必须为True。
    time_scope: str = 'source'  # none/selected不声称全来源时间观测。
    retained_record_count: int = 0  # 所需记录数，用于解释稀疏时间范围。
    full_check_count: int = 0  # 非原生输入完整检查回退数。

    def __post_init__(self):
        """检查事实内部一致性，不读文件、扩展范围或补假设周期。

        参数: 无，读取冻结字段。返回: None。异常: 类型、行数、端点或EOF矛盾。
        """
        # 安全来源及会话名称不替代实际读取和历史关联。
        require_identifier(self.source, 'source_scan.source')
        require_identifier(self.session_id, 'source_scan.session_id')
        if type(self.row_count) is not int or self.row_count < 0 or self.source_eof is not True:
            raise ValueError('来源扫描事实需非负原生行数及完整EOF')
        for name in ('first_ns', 'last_ns', 'observed_start_ns', 'observed_end_ns'):
            value = getattr(self, name)
            if value is not None:
                require_int64_ns(value, 'source_scan.' + name)
        # 全空不伪造时间0；非空允许同刻单点，但必须保留实际可核实终点。
        if (type(self.retained_record_count) is not int or not 0 <= self.retained_record_count <= self.row_count
                or type(self.full_check_count) is not int or not 0 <= self.full_check_count <= self.row_count):
            raise ValueError('来源保留记录/完整回退计数非法')
        if self.time_scope not in ('none', 'selected', 'source'):
            raise ValueError('来源时间范围非法')
        if self.time_scope != 'source':
            if self.observed_start_ns is not None or self.observed_end_ns is not None:
                raise ValueError('部分或未采集时间不能声明全来源范围')
            if self.time_scope == 'none' and (self.first_ns is not None or self.last_ns is not None):
                raise ValueError('无时间来源不能声明首末')
            if self.time_scope == 'selected':
                # 原帧数非零不代表存在目标时间；仅真实保留记录决定目标首末是否存在。
                if not self.retained_record_count and (self.first_ns is not None or self.last_ns is not None):
                    raise ValueError('没有目标记录不能声明目标首末时间')
                if self.retained_record_count and (self.first_ns is None or self.last_ns is None):
                    raise ValueError('存在目标记录时必须保留目标首末时间')
            if (self.first_ns is None) != (self.last_ns is None) or self.first_ns is not None and self.first_ns > self.last_ns:
                raise ValueError('目标记录首末时间不一致')
            return
        if self.row_count == 0:
            if self.first_ns is not None or self.last_ns is not None:
                raise ValueError('全空扫描的原行首末须为None')
        elif (self.first_ns is None or self.last_ns is None or self.first_ns > self.last_ns
                or self.observed_start_ns is None or self.observed_end_ns is None
                or self.observed_start_ns > self.first_ns or self.observed_end_ns < self.last_ns):
            raise ValueError('非空扫描需有序原行首末及包含它们的实际观测边界')
        if (self.observed_start_ns is not None and self.observed_end_ns is not None
                and self.observed_start_ns > self.observed_end_ns):
            raise ValueError('来源扫描观测范围不能回退')


class ObservedSourceScan:
    """拥有单个真实read及有限扫描快照，借用历史、来源和计划但不关闭它们。

    _expected_counts和_expected_sha只跟踪本source的成功写入，consume不向外
    交付批次。_finished须在真实耗尽与read关闭后设置；失败或半关闭只允许close。
    固定费用覆盖描述、请求及所有有限快照，直到显式close才释放。
    """

    def __init__(self, history, source_plan, adapter, request):
        """核对空的building来源及原对象关系，先预约有限合同，不开始读取。

        参数: history为实际DecodedHistoryStore；source_plan为原SourcePlan；adapter
            为同budget实际预算memory、CSV、旧CAN或新文本CAN来源；request须是history使用的原对象。
        返回: 尚未扫描的owner。异常: 合同、类型、预算或取消原错；持续构造清理失败
            附observed_source_scan_cleanup_owner，恢复后调用其close。
        """
        # 不接受独立事实模型或自由迭代器代替实际来源入口。
        if (not isinstance(history, DecodedHistoryStore) or not isinstance(source_plan, SourcePlan)
                or not isinstance(request, ReadRequest)
                or not isinstance(adapter, (BudgetedMemorySourceAdapter, BudgetedSignalCSVSourceAdapter,
                    BudgetedLegacyCANSourceAdapter,BudgetedTextCANSourceAdapter))):
            raise TypeError('来源扫描需实际历史、SourcePlan、预算来源及原ReadRequest')
        history._check('building')
        adapter._ensure_open()
        name = source_plan.name
        if name not in history.validators or adapter.budget is not history.budget:
            raise ValueError('来源扫描需属于同一历史及共享budget')
        validator = history.validators[name]
        if (validator.request is not request or history.counts[name] != [0, 0]
                or validator.ended or name in history._completions):
            raise ValueError('来源扫描需原request及尚无append或EOF的历史来源')
        # 首次预算回调前安装全部槽；原rows仅借引用，不做深遍历或副本。
        self._history, self._source_plan, self._adapter, self._request = history, source_plan, adapter, request
        self._budget, self._source = history.budget, name
        self._fixed_cost = self._held_cost = 0
        self._read = self._batch = self._observation = self._history_sha256 = self._counts = None
        # CAN原帧仓在本次read完成后先移入本父；有限READY另计，不能随read.close失去出处。
        self._raw_store = self._runtime_metadata = self._read_identity = None
        self._message_store = None
        self.retain_raw_frames = (adapter.retain_raw_frames
            if isinstance(adapter, (BudgetedLegacyCANSourceAdapter,BudgetedTextCANSourceAdapter)) else False)
        self._capture_message_updates = (adapter.capture_message_updates
            if isinstance(adapter, BudgetedLegacyCANSourceAdapter) else False)
        self._runtime_cost = 0
        self._description, self._validator = validator.description, validator
        self._expected_counts, self._expected_sha = (0, 0), history.hashes[name].hexdigest()
        self._started = self._finished = self._closed = self._closing = self._failed = False
        try:
            # 有限描述和请求已知；source_plan.config/metadata/raw_config与完整rows均不纳入递归估算。
            cost = 65536 + 16 * _metadata_bytes((self._description, request, source_plan.name,
                source_plan.source_type, source_plan.time_unit, source_plan.timezone_text))
            _reserve_owned_ram(self, cost, '_fixed_cost')
            self._require_contract()
        except BaseException as exc:
            # 尚未创建read也要保留实际固定费；原错不被清理取消覆盖。
            self._failed = True
            self._adopt_cleanup(exc)
            _cleanup_owner(self, exc, 'observed_source_scan_cleanup_owner', '来源扫描构造')
            raise

    def _require_contract(self):
        """在每次读取和追加边界核对原来源对象、描述、请求与本source预期写入。

        参数: 无。返回: None。异常: 原生命周期错误，或ValueError为替换、外部追加或合同变化。
        """
        # 允许其他source推进，但本source只能由此scan写入，不能接半读历史继续猜首端。
        self._history._check('building')
        self._adapter._ensure_open()
        if self._adapter.budget is not self._budget or self._history.budget is not self._budget:
            raise ValueError('扫描来源或历史的实际共享budget已被替换')
        name = self._source
        validator = self._history.validators.get(name)
        if (validator is not self._validator or validator.request is not self._request
                or tuple(self._history.counts[name]) != self._expected_counts
                or self._history.hashes[name].hexdigest() != self._expected_sha):
            raise ValueError('扫描历史的原validator、request、计数或摘要已被其他写入替换')
        plan, adapter = self._source_plan, self._adapter
        if isinstance(adapter, BudgetedMemorySourceAdapter):
            config = adapter._adapter.source
            matched = plan.source_type == 'memory' and isinstance(plan.config, SourceSpec)
        elif isinstance(adapter, BudgetedSignalCSVSourceAdapter):
            config = adapter.spec
            matched = plan.source_type == 'signal_csv' and isinstance(plan.config, SignalCSVSpec)
        elif isinstance(adapter,BudgetedTextCANSourceAdapter):
            config=adapter.spec
            matched=plan.source_type in ('can_asc','asc_or_blf','raw_can_csv') and type(plan.config) is CANTextSpec and plan.source_type==config.source_type
        else:
            config = adapter.spec
            matched = plan.source_type == 'can_blf' and type(plan.config) is LegacyCANSpec
        if (not matched or plan.config is not config or config.name != name
                or self._request.session_id != (adapter._adapter.session_id
                    if isinstance(adapter, BudgetedMemorySourceAdapter) else adapter.session_id)
                or adapter.describe() != self._description):
            raise ValueError('扫描来源原config、会话或实际描述与历史合同不一致')
        if (isinstance(adapter, BudgetedLegacyCANSourceAdapter)
                and (adapter.capture_message_updates is not self._capture_message_updates
                    or adapter.retain_raw_frames is not self.retain_raw_frames)):
            raise ValueError('扫描CAN来源的原消息捕获开关已改变')
        if isinstance(adapter,BudgetedTextCANSourceAdapter) and adapter.retain_raw_frames is not self.retain_raw_frames:
            raise ValueError('文本CAN原帧保存选择已改变')

    def _adopt_cleanup(self, exc):
        """接管实际未返回的最高来源读取owner，不接借用来源或历史。

        参数: exc为原异常。返回: None。异常: 无预期异常。
        """
        # 先接对应来源工厂交出的实际read，再由本scan作为最高父恢复；借用来源不接管。
        for attribute in ('can_observation_read_cleanup_owner', 'csv_observation_read_cleanup_owner','text_can_observation_cleanup_owner',
                'memory_read_cleanup_owner'):
            read = getattr(exc, attribute, None)
            if read is not None and self._read is None:
                self._read = read
                break
        # 没有更高实际read父时才接未返回消息仓，不能把同一子在两个父重复收责。
        if self._capture_message_updates and self._read is None and self._message_store is None:
            self._message_store = getattr(exc, 'decoded_message_store_cleanup_owner', None)

    def _close_read(self):
        """结束本scan实际read，成功后才清字段，不影响adapter的其他read。

        参数: 无。返回: None。异常: 原read关闭错误；旧memory未完成费用明确拒绝。
        """
        # 当前批先结束借引用，read负责它自己的原generator、FD及批次费用。
        self._batch = None
        if self._read is not None:
            self._read.close()
            if (isinstance(self._adapter, BudgetedMemorySourceAdapter)
                    and (not self._read.closed or self._read.cost != 0)):
                raise AnalysisError('原memory读取仍有未完成清理费用，来源扫描不能声明完成')
            self._read = None

    def consume(self):
        """单次扫描真实来源并把每个原batch直接写入同一history，成功后开放快照。

        参数: 无。返回: None，重复调用已完成scan不重读。
        异常: 原读取、历史追加、预算、来源变化或关闭错误；failed后只可close，原错附最高恢复owner。
        """
        self._ensure_active()
        if self._finished:
            return
        if self._started:
            raise ResultClosedError('来源扫描consume已开始，不能重入同一读取')
        try:
            self._require_contract()
            self._started = True
            # 本owner亲自创建read，不能传入另一次独立读取或手造观测替代本历史数据流。
            if isinstance(self._adapter, BudgetedSignalCSVSourceAdapter):
                self._read = self._adapter.iter_batches_with_observation(self._request)
                if type(self._read) is not CSVObservationRead:
                    raise TypeError('CSV扫描必须使用实际CSVObservationRead')
            elif isinstance(self._adapter,BudgetedTextCANSourceAdapter):
                self._read=self._adapter.iter_batches_with_observation(self._request)
                if type(self._read) is not TextCANObservationRead:
                    raise TypeError('文本CAN扫描必须使用真实TextCANObservationRead')
            elif isinstance(self._adapter, BudgetedLegacyCANSourceAdapter):
                self._read = self._adapter.iter_batches_with_observation(self._request)
                from .can_batch_reader import CANBatchObservationRead
                expected_type = CANBatchObservationRead if self._adapter.batch_read else CANObservationRead
                if type(self._read) is not expected_type:
                    raise TypeError('CAN扫描必须使用本adapter对应的实际read')
            else:
                self._read = self._adapter.iter_batches(self._request)
            while True:
                self._require_contract()
                try:
                    self._batch = next(self._read)
                except StopIteration:
                    break
                # 下一笔读取返回后仍核合同，防止读取回调期间替换来源或向本source重复append。
                self._require_contract()
                if self._batch.source != self._source or self._batch.session_id != self._request.session_id:
                    raise ValueError('扫描read交付了另一来源或会话的batch')
                expected = (self._expected_counts[0] + 1,
                            self._expected_counts[1] + self._batch.sample_count)
                self._history.append(self._batch)
                if tuple(self._history.counts[self._source]) != expected:
                    raise ValueError('来源扫描实际历史追加计数未对应唯一原batch')
                self._expected_counts = expected
                self._expected_sha = self._history.hashes[self._source].hexdigest()
                self._batch = None
            self._require_contract()
            completion = self._history._completions.get(self._source)
            if (completion is None or not completion.source_eof or not self._validator.ended
                    or completion.session_id != self._request.session_id):
                raise ValueError('来源扫描没有本历史实际完整EOF进度')
            # 首末时间来自本次真实read或原冻结memory全输入，不从投影样本或request猜测。
            if isinstance(self._adapter, (BudgetedSignalCSVSourceAdapter, BudgetedLegacyCANSourceAdapter,BudgetedTextCANSourceAdapter)):
                fact = self._read.observation
                if (not self._read.exhausted or self._read.failed or fact.request is not self._request
                        or fact.read_identity != self._read.identity or fact.source != self._source
                        or fact.session_id != self._request.session_id or not fact.source_eof
                        or fact.last_ns != completion.observed_end_ns):
                    raise ValueError('来源实际读取事实与同一次历史EOF不一致')
                first, last, count = fact.first_ns, fact.last_ns, fact.row_count
                if isinstance(self._adapter,BudgetedTextCANSourceAdapter):
                    metadata=self._read.runtime_metadata
                    _reserve_owned_ram(self,65536+32*_metadata_bytes(metadata),'_runtime_cost')
                    self._runtime_metadata,self._read_identity=metadata,fact.read_identity
                    if self.retain_raw_frames:
                        self._read.take_raw_store(self,'_raw_store')
                        if (self._raw_store.count!=count or self._raw_store.state!='sealed'
                                or self._raw_store.read_identity!=fact.read_identity or self._raw_store.source_name!=self._source):
                            raise ValueError('同次文本原帧仓与实际观测身份不符')
                if isinstance(self._adapter, BudgetedLegacyCANSourceAdapter):
                    # 保留同次READY和原read身份；费用先预约，原store先安装本父再解除子责任。
                    metadata = self._read.runtime_metadata
                    _reserve_owned_ram(self, 65536 + 32 * _metadata_bytes(metadata), '_runtime_cost')
                    self._runtime_metadata, self._read_identity = metadata, fact.read_identity
                    if self.retain_raw_frames:
                        self._read.take_raw_store(self, '_raw_store')
                        if (self._raw_store.count != count or self._raw_store.state != 'sealed'
                                or self._raw_store.source_name != self._source):
                            raise ValueError('同次CAN原帧仓与真实扫描完成事实不一致')
                    if self._read.capture_message_updates is not self._capture_message_updates:
                        raise ValueError('同次CAN原read的消息捕获开关不符')
                    if self._capture_message_updates:
                        # 原对象先从完成read移入本父，核同次READY/身份/全帧数后才可关闭read。
                        self._read.take_message_store(self, '_message_store')
                        store = self._message_store
                        if (store.closed or store.state != 'sealed'
                                or (store.count != count if not store.sparse_sequences else
                                    store.count > count or store._last_sequence >= count)
                                or store.source_name != self._source or store.session_id != self._request.session_id
                                or store.read_identity != fact.read_identity
                                or store.decoder_profile != metadata['profile']):
                            raise ValueError('同次CAN消息仓与原读取及真实扫描事实不一致')
            else:
                config = self._source_plan.config
                count = len(config.rows)
                first = checked_add_ns(config.rows[0].time_ns, config.offset_ns) if count else None
                last = checked_add_ns(config.rows[-1].time_ns, config.offset_ns) if count else None
            start = self._description.observation_start_ns
            # CAN读取已经统计实际保留和完整检查回退数；普通历史扫描也须原样
            # 移交同次事实，不能在重建观测时落回默认0。CSV/memory保持原契约。
            can_fact = fact if isinstance(self._adapter, BudgetedLegacyCANSourceAdapter) else None
            observation = SourceScanObservation(self._source, self._request.session_id, first, last,
                count, first if start is None else start, completion.observed_end_ns, True,
                can_fact.time_scope if can_fact is not None else 'source',
                can_fact.retained_record_count if can_fact is not None else 0,
                can_fact.full_check_count if can_fact is not None else 0)
            digest, counts = self._expected_sha, self._expected_counts
            # 独立有限快照已在固定费内；原read真正关闭成功以后才对后继发布finished。
            self._close_read()
            self._observation, self._history_sha256, self._counts = observation, digest, counts
            self._finished = True
        except BaseException as exc:
            # 历史append可能自行进入failed/cancelled，原行为保留；这里只接本scan自有read。
            self._failed = True
            self._adopt_cleanup(exc)
            exc.observed_source_scan_cleanup_owner = self
            exc.add_note('恢复后调用observed_source_scan_cleanup_owner.close()')
            raise

    def _ensure_active(self):
        """拒绝关闭、清理或失败后的读取及事实访问。

        参数: 无。返回: None。异常: ResultClosedError为本owner不可用。
        """
        # 半关闭或失败实例不能被后继Scopes当作活的成功扫描证明。
        if self._closed or self._closing or self._failed:
            raise ResultClosedError('来源扫描已关闭、正在清理或失败')

    def _require_finished(self):
        """只允许活的成功scan提供数据流快照。参数: 无。返回: None。异常: ResultClosedError。
        """
        # 模型构造成功不代表读取成功，finished闸门与owner可用性必须同时成立。
        self._ensure_active()
        if not self._finished:
            raise ResultClosedError('来源扫描尚未正常完成')

    @property
    def capture_message_updates(self):
        """读取本scan原来源的消息捕获开关，不据此开放完成证明。

        参数: 无。返回: 原生bool；非CAN来源为False，关闭后仍保配置快照。
        异常: 无；readonly属性不能把尚未完成的消息仓改成可移交。
        """
        return self._capture_message_updates

    @property
    def history(self):
        """读取原历史对象。参数: 无。返回: DecodedHistoryStore。异常: ResultClosedError为不可用。
        """
        self._ensure_active()
        return self._history

    @property
    def source_plan(self):
        """读取原来源计划。参数: 无。返回: SourcePlan。异常: ResultClosedError为不可用。
        """
        self._ensure_active()
        return self._source_plan

    @property
    def request(self):
        """读取本次原request。参数: 无。返回: ReadRequest。异常: ResultClosedError为不可用。
        """
        self._ensure_active()
        return self._request

    @property
    def finished(self):
        """读取成功完成事实。参数: 无。返回: bool。异常: 无。"""
        # close不会抹掉曾完成的事实，后继仍须独立拒绝closed或failed的owner。
        return self._finished

    @property
    def closed(self):
        """读取完整关闭事实。参数: 无。返回: bool。异常: 无。"""
        # 所有自有read与固定费用实际清完后才成为True。
        return self._closed

    @property
    def failed(self):
        """读取失败事实。参数: 无。返回: bool。异常: 无。"""
        # 正常空来源也可以finished，不用failed表示无数据。
        return self._failed

    @property
    def history_sha256(self):
        """读取本source完成写入时的历史SHA。参数: 无。返回: str。异常: ResultClosedError。
        """
        self._require_finished()
        return self._history_sha256

    @property
    def counts(self):
        """读取进度数及样本数。参数: 无。返回: 二元素int tuple。异常: ResultClosedError。
        """
        self._require_finished()
        return self._counts

    @property
    def observation(self):
        """读取本scan完成的原行及观测范围事实。参数: 无。返回: SourceScanObservation。异常: ResultClosedError。
        """
        self._require_finished()
        return self._observation

    @property
    def runtime_metadata(self):
        """读取成功CAN扫描的同次READY。参数: 无。返回: 冻结映射。异常: 非CAN或未完成。
        """
        self._require_finished()
        if self._runtime_metadata is None:
            raise ValueError('此来源没有CAN运行元数据')
        return self._runtime_metadata

    @property
    def read_identity(self):
        """读取成功CAN扫描的原read身份。参数: 无。返回: str。异常: 非CAN或未完成。
        """
        self._require_finished()
        if self._read_identity is None:
            raise ValueError('此来源没有CAN读取身份')
        return self._read_identity

    def take_raw_store(self, receiver, slot='_raw_store'):
        """把同次原帧仓先装入真实父槽再解除本责任，取消时仍有可达owner。

        参数: receiver共享同一_budget；slot为空的已存在责任槽。返回: 原RawFrameStore。
        异常: 未完成、重复移交、预算或接收槽错误；安装后取消不丢父槽。
        """
        self._require_finished()
        store = self._raw_store
        if (store is None or getattr(receiver, '_budget', None) is not self._budget
                or not hasattr(receiver, slot) or getattr(receiver, slot) is not None):
            raise ValueError('原帧仓移交需同预算空父槽且只能一次')
        try:
            setattr(receiver, slot, store)
        finally:
            # setter可能在实际安装后抛取消；检查真实槽决定责任，不依赖返回成功。
            if getattr(receiver, slot, None) is store:
                self._raw_store = None
        return store

    def take_message_store(self, receiver, slot='_message_store'):
        """把实际同次decoded仓先安装接收父，再结束本scan唯一子责任。

        参数: receiver为同一_budget的可信内部owner；slot为其已存在且为空的实际槽。
        返回: 原DecodedMessageStore；只能在真实finished后成功移交一次。
        异常: 未完成/已关闭错误，ValueError为未开启、已移交或接收槽不符；
            安装前后取消保原异常和observed_source_scan_cleanup_owner。
        """
        self._require_finished()
        store = self._message_store
        if (not self._capture_message_updates or store is None
                or getattr(receiver, '_budget', None) is not self._budget or type(slot) is not str
                or not slot.startswith('_') or not hasattr(receiver, slot) or getattr(receiver, slot) is not None):
            raise ValueError('消息仓移交需已开启、同预算空父槽且只能一次')
        try:
            # 实际安装后才取消也属于新父，不依赖return是否顺利到达调用方。
            setattr(receiver, slot, store)
        except BaseException as exc:
            exc.observed_source_scan_cleanup_owner = self
            raise
        finally:
            if getattr(receiver, slot, None) is store:
                self._message_store = None
        return store

    def close(self):
        """关闭本scan的read、未移交仓和费用，保留借用来源、历史及磁盘文件。

        参数: 无。返回: None，成功后幂等。异常: 原read或预算取消，未完责任保留供同一owner重试。
        """
        if self._closed:
            return
        self._closing = True
        try:
            # read成功关闭才清有限快照引用，固定费用释放前后取消均按实际槽保留。
            self._close_read()
            if self._raw_store is not None:
                self._raw_store.close()
                if not self._raw_store.closed:
                    raise AnalysisError('CAN原帧仓尚未完成关闭')
                self._raw_store = None
            # 已移交仓槽为None，不能关闭新父；未移交仓持续失败则保本scan最高责任。
            if self._message_store is not None:
                self._message_store.close()
                if not self._message_store.closed:
                    raise AnalysisError('CAN消息仓尚未完成关闭')
                self._message_store = None
            self._runtime_metadata = self._read_identity = None
            _release_owned_ram(self, self._runtime_cost, '_runtime_cost')
            self._observation = self._history_sha256 = self._counts = None
            self._description = self._validator = self._expected_counts = self._expected_sha = None
            self._history = self._source_plan = self._adapter = self._request = self._source = None
            _release_owned_ram(self, self._fixed_cost, '_fixed_cost')
            if self._held_cost == 0:
                self._closed = True
        except BaseException as exc:
            # 新capture链直接close也保最高实际父；默认路径的异常归属保持原合同。
            if self._capture_message_updates:
                exc.observed_source_scan_cleanup_owner = self
            raise
