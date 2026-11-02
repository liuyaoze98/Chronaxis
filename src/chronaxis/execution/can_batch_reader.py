"""将有界CAN批次接成按需历史，保留每条原yield的时间及必要记录的原序。

旧读取/解码仍由批进程逐条执行。这里只省去无关帧的重复装箱和历史：全部原时间
用于首末/计数/倒退检查，目标记录保存完整values，信号按样本总数分批。
无BLF导出不建立原帧仓。所有批次、转换、引用和数组在共享预算内预付；不保整文件。
"""

from math import isfinite
from ..legacy.records import LegacyDecodedFrame, LegacyRawFrame
from ..results.spool import _reserve_owned_ram, _release_owned_ram
from ..sources.can_spec import CANSourceRef
from ..sources.models import SignalBatch
from ..sources.packing import pack_decoded
from ..sources.protocol import SourceReadError
from ..timebase.conversion import checked_add_ns, INT64_MIN, INT64_MAX, TimeOverflowError, require_int64_ns
from .can_reader import CANObservationRead
from .history import _pending_bytes


def _float_seconds_ns(value):
    """精确把已有二进制float秒舍入至纳秒，不经Decimal文本和逐位展开。

    参数: value为原生有限float秒。返回: (int64纳秒, 是否量化)，最近偶数舍入。
    异常: TypeError/ValueError为输入类型/非有限；TimeOverflowError为舍入后越界。
    边界: 整数比精确保留float已有位值；负零、负半值和次正规数均不先乘float。
    """
    if type(value) is not float:
        raise TypeError('原CAN时间需要float')
    if not isfinite(value):
        raise ValueError('原CAN时间必须有限')
    numerator, denominator = value.as_integer_ratio()
    quotient, remainder = divmod(abs(numerator) * 1000000000, denominator)
    if remainder * 2 > denominator or remainder * 2 == denominator and quotient & 1:
        quotient += 1
    # 上面的原生float整数比与divmod只产生Python int，无需重复Integral类型分流。
    ns = -quotient if numerator < 0 else quotient
    if not INT64_MIN <= ns <= INT64_MAX:
        raise TimeOverflowError('time_ns超出int64纳秒范围')
    return ns, remainder != 0


def _dense_time_tail(owner, timestamps, offset, mapped_times):
    """首条已按原规则提交后，继续原顺序校验余下时间，不提前报告末点错误。

    参数: owner为当前read；timestamps为同批原时间；offset已核int64；mapped_times只含首条。
    返回: 完整映射tuple。异常: 原时间/偏移溢出、倒退或取消；保实际已完成观测前缀。
    流程: 稀疏证明不成立时逐项换算，微小float回退仍允许量化成同一纳秒。
    """
    try:
        for index, timestamp in enumerate(timestamps):
            if index == 0:
                continue
            ns, quantized = _float_seconds_ns(timestamp)
            mapped = ns + offset
            if not INT64_MIN <= mapped <= INT64_MAX:
                raise TimeOverflowError('shifted_time_ns超出int64纳秒范围')
            if mapped < owner._last_ns:
                raise SourceReadError('CAN原yield时间回退，禁止重排')
            owner._last_ns, owner._row_count = mapped, owner._row_count + 1
            mapped_times.append((mapped, quantized))
        return tuple(mapped_times)
    finally:
        owner = timestamps = mapped_times = None


def _retained_time_indices(batch):
    """确认保留记录能按原序号使用稀疏时间表，不替代传输包的完整认证。

    参数: batch的时间已确认是原生有限非降float。返回: 索引列表，或None表示走完整换算。
    异常: 取消/分配错误原样传播；非典型记录回原路径，不新增业务拒绝条件。
    """
    indices = record = None
    try:
        indices, previous = [], -1
        for record in batch.records:
            if (type(record) is not LegacyDecodedFrame or type(record.sequence) is not int
                    or type(record.frame) is not LegacyRawFrame or type(record.frame.timestamp) is not float):
                return None
            index = record.sequence - batch.start_sequence
            if (not previous < index < len(batch.timestamps)
                    or record.frame.timestamp != batch.timestamps[index]):
                return None
            indices.append(index)
            previous = index
        return indices
    finally:
        batch = record = indices = None


def _sparse_batch_times(owner, batch):
    """证明全部原时间合法后，仅换算首末和实际消费记录，保完整观测事实。

    参数: owner为已支付转换空间的read；batch为16至4096帧、目标不超过四分之一的批。
    返回: 按原序号索引的tuple；无需消费的位置为None，证明失败则返回完整映射。
    异常: 业务错误沿原顺序产生；取消/MemoryError保原异常，只保已提交的真实前缀。
    依据: 有限float非降时，精确乘十亿后最近偶数舍入仍单调；固定int偏移也保持顺序。
        首末原纳秒与偏移后纳秒均在int64范围，即证明所有内部时间有界。保留点仍精确
        换算其纳秒和量化标志。末点失败不能抢先报错，必须回原后缀寻找第一处错误。
    费用: 最多4096个槽和1024个保留索引，含回退表仍小于原4MiB预付，无缓存或新owner。
    """
    timestamps = batch.timestamps
    mapped_times = indices = sparse = result = None
    try:
        # 第一条保原检查/提交顺序，坏时间先于坏偏移，跨批回退也在这里拒绝。
        first = timestamps[0]
        ns, quantized = _float_seconds_ns(first)
        offset = require_int64_ns(owner._spec.offset_ns, 'offset_ns')
        mapped = ns + offset
        if not INT64_MIN <= mapped <= INT64_MAX:
            raise TimeOverflowError('shifted_time_ns超出int64纳秒范围')
        if owner._last_ns is not None and mapped < owner._last_ns:
            raise SourceReadError('CAN原yield时间回退，禁止重排')
        if owner._first_ns is None:
            owner._first_ns = mapped
        owner._last_ns, owner._row_count = mapped, owner._row_count + 1
        mapped_times, previous = [(mapped, quantized)], first
        for timestamp in timestamps:
            if type(timestamp) is not float or not isfinite(timestamp) or timestamp < previous:
                return _dense_time_tail(owner, timestamps, offset, mapped_times)
            previous = timestamp
        indices = _retained_time_indices(batch)
        if indices is None:
            return _dense_time_tail(owner, timestamps, offset, mapped_times)
        try:
            last_ns, last_quantized = _float_seconds_ns(timestamps[-1])
        except TimeOverflowError:
            return _dense_time_tail(owner, timestamps, offset, mapped_times)
        last_mapped = last_ns + offset
        if not INT64_MIN <= last_mapped <= INT64_MAX:
            return _dense_time_tail(owner, timestamps, offset, mapped_times)
        sparse = [None] * len(timestamps)
        sparse[0], sparse[-1] = mapped_times[0], (last_mapped, last_quantized)
        for index in indices:
            if index == 0 or index == len(timestamps) - 1:
                continue
            ns, quantized = _float_seconds_ns(timestamps[index])
            sparse[index] = (ns + offset, quantized)
        result = tuple(sparse)
        # 全部所需映射完成后才提交其余原观测；取消不能冒充整批已经处理完成。
        owner._last_ns, owner._row_count = last_mapped, owner._row_count + len(timestamps) - 1
        return result
    finally:
        owner = batch = timestamps = mapped_times = indices = sparse = result = None


class CANBatchObservationRead(CANObservationRead):
    """复用真实read责任槽与完成协议，追加一个有界批次及其游标。

    _incoming由进程保活原记录，转换表单独预付。原yield总数与消息仓保存条数分开；
    同刻记录跨SignalBatch不合并，尚未输出的同刻别名不提前推进watermark。
    """

    def __init__(self, owner, request):
        """安装批游标后调用原责任初始化。参数: owner/request同原read。返回: read。异常: 原错误。"""
        self._incoming = self._mapped_times = None
        self._incoming_index = 0
        self._input_ended = False
        self._progress_ns = None
        super().__init__(owner, request)

    def _load_batch(self):
        """读取一批并检查所有原时间，记录全部观测，EOF才封口实际仓。

        参数: 无。返回: bool是否取到批次，空时间批也算真实返回。
        异常: 原进程、时间倒退、预算/仓错误；调用者统一保留最高恢复owner。
        """
        try:
            self._record = self._incoming = self._mapped_times = None
            _release_owned_ram(self, self._record_cost, '_record_cost')
            # 4096项时间转换及当前引用副本的保守空间，进程另支付完整records树。
            _reserve_owned_ram(self, 4259840, '_record_cost')
            if getattr(self._process, '_prefetch', False):
                aliases = len(self._selected)
                # 当前原批最多R*A个样本，跨原批尚未accept的装箱最多S个。
                # pending每新增身份计256字节、每列512；留存最多增长G，之后
                # accept还会预约2*(P+G)，相对当前已付P共需额外2*P+3*G。
                # 固定余量另覆盖装箱和4096+1024*S；动态只约束预取，不误拒同步。
                growth = (512 * aliases + 256 * (self._process._batch_rows * aliases
                          + self._request.batch_rows)) if aliases else 0
                self._process._set_prefetch_headroom(
                    2 * _pending_bytes(self._validator) + 3 * growth)
            try:
                batch = next(self._process)
            except StopIteration:
                if not self._process.finished:
                    raise SourceReadError('CAN批进程未完成真实EOF及关闭')
                self._input_ended = True
                if self._raw_store is not None:
                    self._raw_store.seal()
                if self._message_store is not None:
                    self._message_store.seal()
                _release_owned_ram(self, self._record_cost, '_record_cost')
                return False
            self._incoming = batch
            if batch.start_sequence != self._row_count:
                raise SourceReadError('CAN批次原序跨度不连续')
            if batch.time_scope != self._owner.time_scope:
                raise SourceReadError('CAN批次时间范围与实际来源不同')
            self._retained_record_count += len(batch.records)
            self._full_check_count += batch.full_check_count or 0
            if batch.time_scope != 'source':
                # 无关帧不进入时间循环。所需时间仅以原记录序号索引；none保存明确None。
                mapped_times = {}
                for record in batch.records:
                    if batch.time_scope == 'none':
                        mapped_times[record.sequence - batch.start_sequence] = (None, None)
                        continue
                    ns, quantized = _float_seconds_ns(record.frame.timestamp)
                    mapped = checked_add_ns(ns, self._spec.offset_ns)
                    if self._last_ns is not None and mapped < self._last_ns:
                        raise SourceReadError('CAN所需记录时间回退，禁止重排')
                    if self._first_ns is None:
                        self._first_ns = mapped
                    self._last_ns = mapped
                    mapped_times[record.sequence - batch.start_sequence] = (mapped, quantized)
                self._row_count += batch.frame_count
                self._mapped_times, self._incoming_index = mapped_times, 0
                return True
            if (type(batch.timestamps) is tuple and type(batch.records) is tuple
                    and type(batch.start_sequence) is int and 16 <= len(batch.timestamps) <= 4096
                    and len(batch.records) * 4 <= len(batch.timestamps)):
                self._mapped_times, self._incoming_index = _sparse_batch_times(self, batch), 0
                return True
            # 密集/短批保留原循环，避免为没有可省换算的输入增加逐帧分支。
            mapped_times, offset = [], None
            for timestamp in batch.timestamps:
                ns, quantized = _float_seconds_ns(timestamp)
                # 保原顺序：时间换算成功才核偏移。冻结spec的偏移每批核一次；
                # 空时间批仍不触碰偏移。此循环没有会改变spec的外部回调。
                if offset is None:
                    offset = require_int64_ns(self._spec.offset_ns, 'offset_ns')
                mapped = ns + offset
                if not INT64_MIN <= mapped <= INT64_MAX:
                    raise TimeOverflowError('shifted_time_ns超出int64纳秒范围')
                if self._last_ns is not None and mapped < self._last_ns:
                    raise SourceReadError('CAN原yield时间回退，禁止重排')
                if self._first_ns is None:
                    self._first_ns = mapped
                self._last_ns, self._row_count = mapped, self._row_count + 1
                mapped_times.append((mapped, quantized))
            self._mapped_times, self._incoming_index = tuple(mapped_times), 0
            return True
        finally:
            batch = mapped_times = None


    def _advance_record(self):
        """推进到下一保留原记录，最多追加一次raw及消息历史。

        参数: 无。返回: bool是否有记录，跳过无目标批但保其全部观测。
        异常: 原记录/定位/仓/预算/取消；不在别名分片处重复保存。
        """
        try:
            self._record = None
            while self._incoming is None or self._incoming_index == len(self._incoming.records):
                if self._incoming is not None and self._incoming.timestamps:
                    self._progress_ns = self._last_ns
                if not self._load_batch():
                    return False
            record = self._incoming.records[self._incoming_index]
            self._incoming_index += 1
            mapped, quantized = self._mapped_times[record.sequence - self._incoming.start_sequence]
            if self._raw_store is not None:
                self._raw_store.append(record, mapped)
            ids = self._owner.message_frame_ids
            if self._message_store is not None and (ids is None or record.frame.arbitration_id in ids):
                self._message_store.append(record, mapped, time_quantized=quantized)
            self._binding_projection.fields_for(record.frame)
            if self._owner._frame_observer is not None:
                self._owner._frame_observer(record.frame)
            self._record, self._mapped, self._conversion, self._alias_index = record, mapped, quantized, 0
            self._progress_ns = mapped
            # 在实际定位/时间检查成功后交给新分析层；不改变旧解码或原记录顺序。
            self._deliver_message(record, mapped)
            return True
        finally:
            record = None


    def _packed_batch(self):
        """跨保留记录装箱至总样本上限，不为每条非目标原帧生成空历史。

        参数: 无。返回: 已校验SignalBatch，或者None表示真实输入耗尽且无剩余样本。
        异常: 原模型/归一化/预算/IO错误；样本时间和sequence均来自同次原记录。
        """
        try:
            _reserve_owned_ram(self, 65536, '_pack_cost')
            records, references, count = {}, {}, 0
            while count < self._request.batch_rows:
                if self._record is None or self._alias_index >= len(self._selected):
                    if not self._advance_record():
                        break
                while self._alias_index < len(self._selected) and count < self._request.batch_rows:
                    definition, field = self._selected[self._alias_index]
                    self._alias_index += 1
                    if self._spec.decode_policy != 'legacy' and (self._record.frame.is_remote_frame or self._record.frame.is_error_frame):
                        continue
                    if field not in self._binding_projection.fields_for(self._record.frame):
                        continue
                    # 包含完整定位引用、列表/tuple转换及pack数组，而非只付标量大小。
                    _reserve_owned_ram(self, self._sample_pack_costs[self._alias_index - 1], '_pack_cost')
                    ref = CANSourceRef(self._request.session_id, self._spec.name, definition.field,
                        str(self._spec.input_paths[self._incoming.input_index]), self._spec.legacy_profile, field.channel,
                        field.signal, field.frame_id, self._record.frame.is_extended_id, self._record.frame.is_fd, self._record.sequence,
                        self._record.frame.timestamp, self._conversion)
                    records.setdefault(definition.name, []).append((self._mapped, self._record.sequence,
                        self._record.values.get(field.signal)))
                    references.setdefault(definition.name, []).append(ref)
                    count += 1
            if not count:
                return None
            columns = {definition.name: pack_decoded(definition, tuple(records[definition.name]),
                tuple(references[definition.name]), self._owner.backend)
                for definition, _ in self._selected if definition.name in records}
            progress = self._progress_ns
            watermark = None if progress == -(1 << 63) else progress - 1
            return self._accept(SignalBatch(self._spec.name, self._request.session_id,
                columns, watermark, False, None))
        finally:
            records = references = columns = ref = None


    def __next__(self):
        """交付有样本批或唯一EOF空批，下一次耗尽才开放观测与移交。

        参数: 无。返回: SignalBatch。异常: StopIteration为真实完成；其他原错误poison本read。
        """
        if self._finished:
            raise StopIteration
        self._require_open()
        try:
            self._release_current()
            if not self._started:
                self._start()
            if self._eof_delivered:
                self._finish()
            else:
                batch = None if self._input_ended else self._packed_batch()
                if batch is not None:
                    return batch
                if not self._pack_cost:
                    _reserve_owned_ram(self, 65536, '_pack_cost')
                batch = SignalBatch(self._spec.name, self._request.session_id, {}, self._last_ns,
                    True, self._last_ns)
                self._accept(batch)
                self._eof_delivered = True
                return batch
        except BaseException as exc:
            self._fail(exc)
            raise
        raise StopIteration

    def close(self):
        """释放本批引用后按原真实owner顺序关闭。参数: 无。返回: None。异常: 原可恢复错误。"""
        self._incoming = self._mapped_times = None
        super().close()
