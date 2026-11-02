"""将已解码批次写入有限历史并单行重放，不重读旧输入。

输入为来源描述、读取请求和typed SignalBatch；输出为样本/进度迭代器。
每来源一个JSONL，列内有序数组以有限堆按时间/序号合并，保留所有同刻更新。
共享ResourceBudget覆盖现有批次数组nbytes、Python容器、协议pending和行副本；
预算在新增结构/写入前申请，累计spool包含失败部分，不承诺全进程RSS。
来源在生成批次前的预算接线尚未在本组件实现，不能据此声称完整AnalysisRunner有限。
失败保留诊断文件和原异常，关闭活动句柄；RefProjects与既有工作目录不修改。
"""

# 标准库文件、摘要和有限堆；只读取解码后的数组，不依赖旧CAN模块。
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import fields, is_dataclass
from enum import Enum
from hashlib import sha256
import heapq
from pathlib import Path
from sys import getsizeof
from types import MappingProxyType
from ..core.numeric import ScalarValue
from ..core.types import QualityFlag, SignalDType
from ..results.budget import ResourceBudget
from ..results.codec import _estimate
from ..results.errors import AnalysisError, ResultClosedError, ResultFormatError
from ..results.spool import _cleanup_owner, _reserve_owned_ram, _release_owned_ram
from ..sources.models import SignalBatch, SourceDescription, ReadRequest
from ..sources.protocol import BatchValidator
from .history_records import (HistorySample, HistoryProgress, HistoryRecord,
                              estimate_record_bytes, encode_record, decode_record)
from .groups import DecodedTimeGroup, _TimeGroupIterator


def _metadata_bytes(value, depth: int = 0) -> int:
    """估算已校验来源/请求的冻结元数据，不改变结果层封闭类型注册。

    参数: value为typed描述树，depth为递归深度。返回: 基础bytes。
    异常: ResultFormatError为深度或未支持元数据。
    """
    # 仅计数，不执行序列化或调用任意对象方法；所有描述先经typed模型检查。
    if depth > 32:
        raise ResultFormatError('历史元数据超过32层')
    if is_dataclass(value) and not isinstance(value, type):
        return getsizeof(value) + sum(256 + _metadata_bytes(getattr(value, field.name), depth + 1) for field in fields(value))
    if isinstance(value, Mapping):
        return getsizeof(value) + sum(128 + _metadata_bytes(key, depth + 1) + _metadata_bytes(item, depth + 1) for key, item in value.items())
    if type(value) is tuple:
        return getsizeof(value) + sum(32 + _metadata_bytes(item, depth + 1) for item in value)
    if isinstance(value, Enum):
        return 512
    if value is None or type(value) in (str, int, bool, float):
        return getsizeof(value) + 64
    raise ResultFormatError('历史元数据类型无法估算')


def _pending_bytes(validator: BatchValidator) -> int:
    """估算当前组去重状态，不保留历史所有sequence。

    参数: validator为一个来源协议状态。返回: 保守bytes。
    异常: 已校验状态不主动抛错。
    """
    # set每身份计256bytes，覆盖槽位、整数与局部复制；列固定项单独计。
    return sum(512 + len(sequences) * 256 for _, sequences in validator.pending.values())


def _batch_bytes(batch: SignalBatch) -> int:
    """核算调用方已提供批次数组和引用/原诊断容器。

    参数: batch为typed批次。返回: 数组精确nbytes加容器保守bytes。
    异常: 深度/类型估算错误传播，不省略长字段开销。
    """
    # 数组形状(N,)、整数ns和固定值dtype已经由SignalSeries检查。
    # 定位可含CSVSourceRef子类，完整字段用描述估算；结果编码注册保持封闭。
    return 4096 + sum(column.nbytes + 2048 + 16 * (_estimate((column.name, column.unit,
                       column.labels, column.original_values)) + _metadata_bytes(column.source_ref)) for column in batch.series.values())


class DecodedHistoryStore:
    """维护一次任务的分源历史、协议状态和独立读取句柄。

building仅能追加，sealed要求所有来源EOF；failed/cancelled禁止重放。
close幂等关闭读取句柄并释放状态RAM，磁盘文件留作恢复证据，不递归删除。
源数/字段数来自固定声明，样本数增长只体现在磁盘和整数计数中。
"""

    def __init__(self, budget: ResourceBudget, work_dir: str | Path,
                 descriptions: tuple[SourceDescription, ...], requests: Mapping[str, ReadRequest]):
        """为新目录建立历史，检查来源/请求并先申请固定元数据预算。

        参数: budget为共享账本；work_dir必须不存在；descriptions/requests按来源对应。
        返回: building存储。异常: ValueError/TypeError/预算或实际目录创建原错；持续
            清理失败附history_cleanup_owner，已有目录不写失败标记也不抵销借用费用。
        """
        # 先检查固定配置，不能将同名来源后值覆盖前值或混用会话。
        if not isinstance(budget, ResourceBudget) or type(descriptions) is not tuple or not descriptions or any(not isinstance(item, SourceDescription) for item in descriptions):
            raise TypeError('历史需要账本和非空typed来源tuple')
        names = tuple(item.name for item in descriptions)
        if len(set(names)) != len(names) or not isinstance(requests, Mapping) or set(requests) != set(names) or any(not isinstance(item, ReadRequest) for item in requests.values()):
            raise ValueError('历史来源和请求必须唯一对应')
        if len({item.session_id for item in requests.values()}) != 1:
            raise ValueError('一个历史任务只支持一个明确session')
        path = Path(work_dir)
        # 首次预算与文件检查前安装所有实际责任槽；None表示尚未分配对应容器。
        self.budget = self._budget = budget
        self.work_dir = path
        self._state_cost = self._pending_cost = self._append_cost = 0
        self._record_cost = self._diagnostic_cost = self._held_cost = 0
        self.validators = self.paths = self.counts = self.hashes = self.line_limits = None
        self._completions = self._iterators = self._groups = None
        self._write_handle = self._diagnostic_handle = None
        # 固定状态预算覆盖一个无缓冲写FD及路径借引用；来源再多也不同时持有多个写FD。
        self._write_path = None
        self.closed = self._closing = False
        self.state = 'building'
        try:
            if path.exists():
                raise FileExistsError(path)
            # 保留原费用公式；reserve成功返回途中取消也由实际state槽接住。
            state_cost = 8192 + len(names) * 4096 + 16 * _metadata_bytes(descriptions) + 16 * _metadata_bytes(tuple(requests.values()))
            _reserve_owned_ram(self, state_cost, '_state_cost')
            # 固定结构的所有分配都纳入释放边界，全部成功后才创建外部目录。
            self.validators = {item.name: BatchValidator(item, requests[item.name]) for item in descriptions}
            self.paths = {name: path / f'{name}.jsonl' for name in names}
            self.counts = {name: [0, 0] for name in names}
            self.hashes = {name: sha256() for name in names}
            self.line_limits = {name: 1 for name in names}
            self._completions: dict[str, HistoryProgress] = {}
            self.max_line_bytes = max(1, budget.memory_budget_bytes // 256)
            self.reader_cost = self.max_line_bytes * 64 + 8192
            self._iterators: set[_HistoryIterator] = set()
            self._groups: set[_TimeGroupIterator] = set()
            path.mkdir(parents=True, exist_ok=False)
        except BaseException as exc:
            # mkdir原错不被释放失败覆盖；不再对半构造对象猜费用或重复释放state。
            self.state = 'cancelled' if isinstance(exc, (KeyboardInterrupt, SystemExit)) else 'failed'
            _cleanup_owner(self, exc, 'history_cleanup_owner', '解码历史构造')
            raise

    def _check(self, state: str) -> None:
        """检查生命周期，不让关闭或失败历史继续使用。

        参数: state为所需状态。返回: None。
        异常: ResultClosedError或AnalysisError为状态不允许。
        """
        # closed先判断，避免关闭后又读损坏文件。
        if self.closed or self._closing:
            raise ResultClosedError('解码历史已关闭或正在清理')
        if self.state != state:
            raise AnalysisError(f'历史状态{self.state}，需要{state}')

    def _write_bytes(self, handle, payload: bytes) -> None:
        """先申请累计磁盘额度，循环完成合法短写。

        参数: handle为二进制文件，payload为单行bytes。返回: None。
        异常: 超限/OSError/零写立即失败，原部分文件保留。
        """
        self.budget.reserve_spool(len(payload))
        offset = 0
        while offset < len(payload):
            # memoryview避免每次短写复制剩余整行。
            written = handle.write(memoryview(payload)[offset:])
            if written is None or written <= 0 or written > len(payload) - offset:
                raise OSError('历史文件写入无进展或返回非法长度')
            offset += written

    @contextmanager
    def _writer(self, slot, path, mode):
        """复用当前来源的无缓冲写FD，切换来源或失败时关闭，诊断仍逐次关闭。

        参数: slot为写入或诊断句柄槽；path/mode为原路径和原打开方式。
        返回: 上下文内借用实际FileIO。异常: 打开或写入原错；已有主错时关闭
            副错只加note，失败FD留父close重试。成功数据批不关闭，EOF或seal/close收尾。
        """
        persistent = slot == '_write_handle'
        if persistent and self._write_handle is not None and self._write_path != path:
            # 先关旧来源再打开新来源，关闭失败立即传播，禁止覆盖原FD的恢复责任。
            self._close_handle(slot)
        if getattr(self, slot) is None:
            setattr(self, slot, path.open(mode, buffering=0))
            if persistent:
                self._write_path = path
        elif not persistent:
            raise AnalysisError('历史仍有未关闭诊断FD，不能覆盖恢复责任')
        failure = None
        try:
            yield getattr(self, slot)
        except BaseException as exc:
            failure = exc
            raise
        finally:
            # failure明确来自本次with主体，不用调用方外层except状态猜真正主异常。
            if not persistent or failure is not None:
                self._close_handle(slot, failure)

    def _close_handle(self, slot, primary=None):
        """按实际FD状态关闭一个父持有句柄，实际未关时保留原对象。

        参数: slot为本父句柄字段；primary为本次已传播主错误或None。
        返回: None。异常: 无主错时原close错误传播；有主错时只加note，最高
            history仍持失败句柄。释放后取消也以真实closed完成最小解除。
        """
        handle = getattr(self, slot)
        if handle is None:
            return
        try:
            handle.close()
            if not handle.closed:
                raise AnalysisError('历史写FD close返回但实际尚未关闭')
        except BaseException as cleanup:
            if primary is None:
                raise
            primary.add_note(f'历史{slot}关闭附加失败: {type(cleanup).__name__}')
        finally:
            if handle.closed:
                setattr(self, slot, None)
                if slot == '_write_handle':
                    self._write_path = None

    def _write_record(self, handle, name: str, record: HistoryRecord) -> None:
        """申请单行编码临时RAM，写入成功后更新摘要。

        参数: handle/name为当前来源文件，record为typed记录。返回: None。
        异常: 格式/预算/文件错误传播，finally释放临时RAM。
        """
        cost = estimate_record_bytes(record)
        failure = None
        try:
            _reserve_owned_ram(self, cost, '_record_cost')
            payload = encode_record(record, self.max_line_bytes)
            self._write_bytes(handle, payload)
            self.hashes[name].update(payload)
            # 实际成功写入最大行是读预算的可靠上限，避免源数>4永远无法同时开游标。
            self.line_limits[name] = max(self.line_limits[name], len(payload))
        except BaseException as exc:
            failure = exc
            raise
        finally:
            # 编码/写入原错优先；释放取消保留单行槽给最高history重试，不丢账或盖根因。
            try:
                _release_owned_ram(self, self._record_cost, '_record_cost')
            except BaseException as cleanup:
                if failure is None:
                    raise
                failure.add_note(f'历史编码槽清理附加失败: {type(cleanup).__name__}')

    def append(self, batch: SignalBatch) -> None:
        """保存一批的全部异步样本和最终进度，空批仍写一条记录。

        参数: batch为已经归一化的typed批次。返回: None。
        异常: AnalysisError保留格式/协议/预算/磁盘异常链；取消原样传播。
        边界: 接收到的数组已经分配，本方法计入其占用但不能追溯控制该分配。
        """
        self._check('building')
        try:
            if not isinstance(batch, SignalBatch) or batch.source not in self.validators:
                raise ValueError('历史批次不属于声明来源')
            validator = self.validators[batch.source]
            batch_index, total = self.counts[batch.source]
            if batch_index >= 2 ** 63 - 1 or total + batch.sample_count >= 2 ** 63:
                raise OverflowError('历史批次/样本计数超过int64')
            # 验证器会复制pending，并可能为本批所有sequence建set，提前覆盖最坏瞬时开销。
            growth = batch.sample_count * 256 + len(batch.series) * 512
            requested = _batch_bytes(batch) + _pending_bytes(validator) + growth + 4096 + len(batch.series) * 512
            _reserve_owned_ram(self, requested, '_append_cost')
            validator.accept(batch)
            # 把新增协议状态的预留从临时lease转为持久账目，不在分配后再申请。
            new_pending = sum(_pending_bytes(item) for item in self.validators.values())
            retained = max(0, new_pending - self._pending_cost)
            if new_pending < self._pending_cost:
                _release_owned_ram(self, self._pending_cost - new_pending, '_pending_cost')
            else:
                # 同一owner内部把本批已付金额交给协议pending，不再申请或借余额补账。
                self._append_cost -= retained
                self._pending_cost += retained
            # 每列仅持一个索引，有限堆按(time,sequence,列顺序)合并，不拼接全批列表。
            columns = tuple(batch.series.values())
            heap = [(int(column.time_ns[0]), int(column.sequence[0]), order, 0)
                    for order, column in enumerate(columns) if len(column.time_ns)]
            heapq.heapify(heap)
            with self._writer('_write_handle', self.paths[batch.source], 'ab') as handle:
                while heap:
                    time, sequence, order, index = heapq.heappop(heap)
                    column = columns[order]
                    physical = column.values[index].item()
                    original_present = column.original_values is not None
                    original = column.original_values[index] if original_present else None
                    valid = bool(column.valid[index])
                    logical = column.labels[physical] if valid and column.dtype is SignalDType.ENUM else physical
                    # 无效原诊断仅作诊断，不参与计算；数组占位仍独立保留。
                    if not valid and original_present:
                        logical = original
                    value = ScalarValue(logical, column.dtype, valid, QualityFlag(int(column.quality[index])), column.labels)
                    record = HistorySample(batch_index, column.name, time, sequence, physical, value,
                                           column.unit, column.source_ref[index], original_present, original)
                    self._write_record(handle, batch.source, record)
                    next_index = index + 1
                    if next_index < len(column.time_ns):
                        heapq.heappush(heap, (int(column.time_ns[next_index]), int(column.sequence[next_index]), order, next_index))
                # 进度必须在全部样本之后写；部分批次故障不会形成完成历史。
                progress = HistoryProgress(batch_index, batch.source, batch.session_id,
                    batch.sample_count, batch.watermark_ns, batch.source_eof, batch.observed_end_ns)
                self._write_record(handle, batch.source, progress)
            if batch.source_eof:
                # 成功EOF必须先真实关闭写FD，随后才登记该来源完成；失败仍走原poison/清理路径。
                self._close_handle('_write_handle')
            self.counts[batch.source] = [batch_index + 1, total + batch.sample_count]
            if batch.source_eof:
                # 固定每来源一条完成事实，不收集所有历史进度；状态预估覆盖这些冻结对象。
                self._completions[batch.source] = progress
            # 正常金额和释放时刻保持；交接取消同样会进入失败路径而不能伪报完成。
            _release_owned_ram(self, self._append_cost, '_append_cost')
        except BaseException as exc:
            self.state = 'cancelled' if isinstance(exc, (KeyboardInterrupt, SystemExit)) else 'failed'
            # 最小失败标记尽力写入；额度/物理磁盘不足时不覆盖真正失败原因。
            self._record_failure(exc)
            _cleanup_owner(self, exc, 'history_cleanup_owner', '解码历史写入')
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            error = AnalysisError('已解码历史写入失败')
            recovery = getattr(exc, 'history_cleanup_owner', None)
            if recovery is not None:
                error.history_cleanup_owner = recovery
            for note in getattr(exc, '__notes__', ()):
                error.add_note(note)
            raise error from exc

    def _record_failure(self, exc: BaseException) -> None:
        """尽力保存有界失败标记，不将可能巨大的异常文本装入内存。

        参数: exc为原失败。返回: None。异常: 写标记失败被记录为原异常附注。
        """
        try:
            _reserve_owned_ram(self, 8192, '_diagnostic_cost')
            payload = f'state={self.state}\nexception={type(exc).__name__}\n'.encode('utf-8')
            with self._writer('_diagnostic_handle', self.work_dir / 'failure.txt', 'xb') as handle:
                self._write_bytes(handle, payload)
        except BaseException as diagnostic:
            # 系统取消原因仍在原异常链；这里仅作最小诊断收尾。
            exc.add_note(f'历史失败标记未写完: {type(diagnostic).__name__}')
        finally:
            # 诊断自身也可能在reserve/release返回途中取消，未抵销金额仍归history。
            try:
                # 诊断FD持续未关时仍保留原8192描述费，只有父close能完成这笔责任。
                if self._diagnostic_handle is None:
                    _release_owned_ram(self, self._diagnostic_cost, '_diagnostic_cost')
            except BaseException as cleanup:
                exc.add_note(f'历史失败标记槽清理附加失败: {type(cleanup).__name__}')

    def seal(self) -> None:
        """所有配置来源EOF后封存，禁止用单文件EOF代替来源终点。

        参数: 无。返回: None。异常: AnalysisError为未结束来源或错误状态。
        """
        self._check('building')
        if any(not validator.ended for validator in self.validators.values()):
            raise AnalysisError('全部来源EOF前不能封存解码历史')
        # 正常EOF追加已经关闭写FD；封存再次收尾，不能把未关写FD交给重放阶段。
        self._close_handle('_write_handle')
        self.state = 'sealed'

    def iter_records(self, source: str) -> Iterator[HistoryRecord]:
        """建立一个有独立文件位置的有限重放迭代器。

        参数: source为声明来源名。返回: typed记录Iterator。
        异常: 关闭/未封存/未知来源/预算/打开错误。
        """
        self._check('sealed')
        if source not in self.validators:
            raise ValueError('未知历史来源')
        iterator = _HistoryIterator(self, source)
        try:
            self._iterators.add(iterator)
        except BaseException as exc:
            # 注册未成功时对象还未返回；保留注册原错并由正式属性交出持续清理失败的实际reader。
            _cleanup_owner(iterator, exc, 'history_iterator_cleanup_owner', '历史游标注册')
            raise
        return iterator

    @property
    def source_completions(self) -> Mapping[str, HistoryProgress]:
        """读取已封存来源EOF/终点原事实，不推断未知终点或有效期。

        参数: 无。返回: 只读Mapping；仅owner仍打开时可用。
        异常: 关闭或未封存的历史状态错误。
        """
        self._check('sealed')
        return MappingProxyType(self._completions)

    def iter_groups(self, *, sources=None) -> Iterator[DecodedTimeGroup]:
        """按完整同时间组重放已封存历史，注册关闭所有权。

        参数: sources为来源名tuple或None；None保留全部来源，空tuple不打开源游标。
        返回: 独立组Iterator；组只包含所选来源，返回后须及时消费。
        异常: 生命周期/来源子集类型、重复、未知名称/源游标/预算/历史读取错误。
        边界: 子集EOF只证明所选来源；全历史摘要验证须另行遍历全部来源。
        """
        self._check('sealed')
        # 默认参数沿用原构造调用及费用；显式子集的校验和预约由同一真实游标负责。
        iterator = _TimeGroupIterator(self) if sources is None else _TimeGroupIterator(self, sources=sources)
        try:
            self._groups.add(iterator)
        except BaseException as exc:
            # 未登记的实际group仍拥有子reader；清理失败不能替换注册原错或丢失顶层恢复责任。
            _cleanup_owner(iterator, exc, 'time_group_iterator_cleanup_owner', '时间组游标注册')
            raise
        return iterator

    def close(self) -> None:
        """幂等关闭所有活动迭代器并释放协议/固定状态RAM，保留历史文件。

        参数: 无。返回: None。异常: 原句柄/预算/取消错误附history_cleanup_owner；
            子reader或任一费用未完成时保留父合同和实际责任，恢复后同一close重试。
        """
        if self.closed:
            return
        self._closing = True
        try:
            cleanup_error = None
            for slot in ('_write_handle', '_diagnostic_handle'):
                try:
                    self._close_handle(slot)
                except BaseException as exc:
                    if cleanup_error is None:
                        cleanup_error = exc
                    else:
                        cleanup_error.add_note(f'其他历史写FD关闭失败: {type(exc).__name__}')
            for iterator in tuple(self._groups or ()) + tuple(self._iterators or ()):
                try:
                    iterator.close()
                except BaseException as exc:
                    # 一个句柄关闭出错仍尝试其余句柄，最后报告首个错误。
                    if cleanup_error is None:
                        cleanup_error = exc
                    else:
                        cleanup_error.add_note(f'其他历史游标关闭失败: {type(exc).__name__}')
            if cleanup_error is not None:
                raise cleanup_error
            # 全部实际子游标成功关闭后才清元数据，失败的FD仍能用原owner重试。
            for slot in ('validators', 'paths', 'counts', 'hashes', 'line_limits', '_completions'):
                value = getattr(self, slot)
                if value is not None:
                    value.clear()
            for slot in ('_record_cost', '_diagnostic_cost', '_append_cost', '_pending_cost', '_state_cost'):
                _release_owned_ram(self, getattr(self, slot), slot)
            if self._held_cost == 0:
                self.closed = True
        except BaseException as exc:
            exc.history_cleanup_owner = self
            raise


class _HistoryIterator:
    """单行读取、核对批次计数与SHA256，不装入完整历史。

    cost与_held_cost记录同一笔自有reader费用；未返回构造或注册失败通过原异常恢复。
    handle与登记只在真实FD关闭、费用抵销后解除，不归还调用方history的费用。
    """

    def __init__(self, owner: DecodedHistoryStore, source: str):
        """先预留解析/句柄RAM再打开单个来源文件。

        参数: owner为封存历史，source为来源名。返回: 新独立迭代器。
        异常: 预算/打开/取消原错，持续清理失败时从history_iterator_cleanup_owner恢复close。
        """
        # 行上限来自封存前实际成功写入的数据，读取先限长再解析，篡改长行不能越过预算。
        self.max_line_bytes = owner.line_limits[source]
        # 8192字节buffer只用于新history有限预读；额外16384先覆盖其存储与对象，再open。
        # 原逻辑行限长、真实空读EOF/摘要/计数不变，底层调用次数及取消时机不保证相同。
        cost = self.max_line_bytes * 64 + 8192 + 16384
        # 最小关闭字段先建立，固定申请/摘要/打开都纳入同一所有权保护区。
        self.owner, self.source, self.handle, self.cost = owner, source, None, 0
        self._budget, self._held_cost = owner.budget, 0
        self.closed = self._closing = self._verified_eof = False
        try:
            # finally只围绕本次直接预约登记，成功后取消也保留实际自有费用。
            _reserve_owned_ram(self, cost, 'cost')
            # 摘要/固定结构先建好，文件最后打开，后段初始化失败不会泄漏句柄或预留。
            self.batch_index = self.samples = self.total = 0
            self.ended = False
            # 只有真实读到文件EOF并完成摘要/计数核对才能提供此证明，提前close不算。
            self._verified_eof = False
            self.digest = sha256()
            self.handle = owner.paths[source].open('rb', buffering=8192)
        except BaseException as exc:
            # 未返回的self仍有真实费用/句柄，瞬时清理重试一次，持续失败挂原错供调用方恢复。
            _cleanup_owner(self, exc, 'history_iterator_cleanup_owner', '历史游标构造')
            raise

    def __iter__(self) -> '_HistoryIterator':
        """返回本次独立游标。

        参数: 无。返回: self。异常: 无。
        """
        return self

    @property
    def verified_eof(self) -> bool:
        """读取实际文件EOF核对事实。参数: 无。返回: bool。异常: 无；提前close为False。"""
        return self._verified_eof

    def __next__(self) -> HistoryRecord:
        """读取一行并检查身份、批次结构及终点完整性。

        参数: 无。返回: 一条HistoryRecord。
        异常: StopIteration为已校验完整EOF；损坏/关闭/实际读错误传播并关闭句柄。
        """
        if self.owner.closed or self.owner._closing:
            raise ResultClosedError('解码历史已关闭或正在清理')
        if self.closed:
            raise StopIteration
        # 文件已关闭但预算交接尚未完成时只允许重试close，不从半关闭游标读取。
        if self._closing:
            raise ResultClosedError('解码历史游标正在关闭')
        try:
            payload = self.handle.readline(self.max_line_bytes + 1)
            if not payload:
                # 提前迭代终止不算全部通过；只有实际EOF才核对完整摘要与计数。
                if not self.ended or self.samples or [self.batch_index, self.total] != self.owner.counts[self.source] or self.digest.digest() != self.owner.hashes[self.source].digest():
                    raise ResultFormatError('解码历史EOF、计数或摘要不完整')
                self._verified_eof = True
                self.close()
                raise StopIteration
            if self.ended:
                raise ResultFormatError('历史来源EOF之后仍有记录')
            record = decode_record(payload, self.max_line_bytes)
            if record.batch_index != self.batch_index:
                raise ResultFormatError('历史批次号不连续')
            validator = self.owner.validators[self.source]
            if isinstance(record, HistorySample):
                if record.source_ref.source_name != self.source or record.source_ref.session_id != validator.request.session_id or record.name not in validator.request.signal_names:
                    raise ResultFormatError('历史样本身份/投影冲突')
                self.samples += 1
                if self.samples > validator.request.batch_rows:
                    raise ResultFormatError('历史批次样本超限')
            else:
                if record.source != self.source or record.session_id != validator.request.session_id or record.sample_count != self.samples:
                    raise ResultFormatError('历史进度身份/样本计数冲突')
                self.total += self.samples
                self.samples = 0
                self.batch_index += 1
                self.ended = record.source_eof
            self.digest.update(payload)
            return record
        except BaseException as exc:
            # EOF/解析/IO原错保持；清理失败只附notes与恢复入口，不改读取、摘要或计数算法。
            _cleanup_owner(self, exc, 'history_iterator_cleanup_owner', '历史游标读取')
            raise

    def close(self) -> None:
        """关闭单个游标并抵销一次预留，重复关闭安全。

        参数: 无。返回: None，幂等。
        异常: 文件/预算/取消传播，真实文件未关闭或预算未抵销时保留登记供重试。
        """
        if self.closed:
            # 已抵销但脱链返回取消的孤儿，重试只清登记，不再次扣账。
            self.owner._iterators.discard(self)
            return
        self._closing = True
        try:
            if self.handle is not None:
                self.handle.close()
        finally:
            # 以真实FD.closed判断关闭返回取消；文件未关闭不释放其预留或丢重试权。
            if self.handle is None or self.handle.closed:
                try:
                    _release_owned_ram(self, self.cost, 'cost')
                finally:
                    if self.cost == 0:
                        # 运行绑定在实际EOF关闭之后还需读取最终SHA，保留固定大小摘要对象。
                        self.closed, self.cost = True, 0
                        self.owner._iterators.discard(self)
