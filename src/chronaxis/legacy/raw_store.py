"""按首次CAN读取的原序暂存完整报文，供片段发布回读而不重扫原输入。

RawFrameStore借用ResourceBudget，append接收同次LegacyDecodedFrame和已显式映射的
int64纳秒，仅保存sequence/time_ns/原frame，不存decoded.values。每行是有界records
JSON包加一个换行；未知ID、同刻帧及全部公开写出字段保留，不排序、筛选或去重。
完整写入后才推进计数和流SHA；部分写入、预算、编码或取消错误均poison，禁止seal。
seal须真实writer关闭成功才开放原序reader；reader逐行校验结构、原序和时间，真实
EOF核条数及完整SHA，关闭也成功后才verified_eof。提前close不产生完整读取证明。

本层只使用标准库、冻结records和新分析层预算工具，不导入旧CAN库或调用解码器。
固定、append工作空间与各活reader分别预付；reader数量受共享预算约束，未保存
全部帧或全部文件路径。账本是保守估算而非整进程RSS；调用方长期保留已返回行须
自行承担空间。close只关闭自有真实FD/费用，保留文件及累计spool预留，不关借用
budget。全部槽先初始化，关闭失败可重试；原异常/KI不被清理覆盖，未返回reader
及持续失败资源从最高raw_frame_store_cleanup_owner恢复，不凭余额差补账。
"""

# 只封装新暂存和typed记录；原reader/parse/writer实现及调用次数由外层保持。
from hashlib import sha256
from pathlib import Path
from ..core.validation import require_identifier
from ..results.budget import ResourceBudget
from ..results.errors import ResultClosedError, ResultFormatError
from ..results.spool import _cleanup_owner, _reserve_owned_ram, _release_owned_ram
from ..timebase.conversion import require_int64_ns
from .records import (MAX_WIRE_BYTES, LegacyDecodedFrame, StoredRawFrame,
                      frame_to_dict, frame_from_dict, encode_packet, decode_packet)


class RawFrameStore:
    """拥有一个原序JSONL和所有独立reader，完成事实不等于FD已经全部关闭。

    state为building/sealed/failed/cancelled；closed另记所有自有资源实际释放完成。
    _pending_reader先安装未返回实例，_readers保存已注册实例；两者均由本父close。
    固定/当前append费用是实际交易槽，累计spool只增加，不从共享账本推测归属。
    """

    def __init__(self, budget, work_dir, source_name, *, max_row_bytes=MAX_WIRE_BYTES, integrity=True):
        """预付有限状态，在显式新目录独占打开原始帧暂存。

        参数: budget为借用ResourceBudget；work_dir为必须不存在的str/Path；source_name
            为安全来源名；max_row_bytes为含换行行上限，1到MAX_WIRE_BYTES，默认65536。
        返回: building存储。异常: 类型/路径/预算/文件/取消原错；持续清理失败保最高owner。
        """
        if not isinstance(budget, ResourceBudget) or not isinstance(work_dir, (str, Path)):
            raise TypeError('原始帧暂存需ResourceBudget及显式新目录')
        if type(max_row_bytes) is not int or not 1 <= max_row_bytes <= MAX_WIRE_BYTES:
            raise ValueError('原始帧行上限需1到MAX_WIRE_BYTES的原生int')
        require_identifier(source_name, 'raw_store.source_name')
        # 先装全部关闭责任，首次reserve更新后取消也不会留下未归属费用或FD。
        if type(integrity) is not bool: raise TypeError('integrity需要bool')
        self.integrity=integrity
        self.budget = self._budget = budget
        self.source_name, self.max_row_bytes = source_name, max_row_bytes
        self.path = self.work_dir = self.file_path = None
        self._writer = self._pending_reader = self._pending_payload = None
        self._readers = self._digest = None
        self._fixed_cost = self._append_cost = self._held_cost = self._spool_bytes = 0
        self.count, self.sha256, self._last_time_ns = 0, None, None
        self.state, self._closed, self._closing = 'building', False, False
        try:
            # 路径字符串只作有限身份，不深遍历来源配置或已解码values。
            requested = Path(work_dir)
            cost = 65536 + 32 * (len(str(requested)) + len(source_name))
            _reserve_owned_ram(self, cost, '_fixed_cost')
            resolved = requested.resolve()
            if resolved.exists():
                raise FileExistsError(resolved)
            self.path = self.work_dir = resolved
            self._readers, self._digest = set(), sha256() if integrity else None
            resolved.mkdir(parents=True, exist_ok=False)
            self.file_path = resolved / 'raw_frames.jsonl'
            self._writer = self.file_path.open('xb', buffering=0)
        except BaseException as exc:
            self._fail(exc)
            raise

    @property
    def closed(self):
        """读取真实关闭事实。参数: 无。返回: bool。异常: 无；费用/FD未清不能为True。"""
        return self._closed

    @property
    def spool_bytes(self):
        """读取本owner直接预留的累计暂存金额。参数: 无。返回: int字节。异常: 无。"""
        return self._spool_bytes

    def _require(self, state):
        """拒绝半关闭或错误状态，不能把poison前缀当完整输入。

        参数: state为所需building/sealed。返回: None。异常: ResultClosedError/RuntimeError。
        """
        if self._closed or self._closing:
            raise ResultClosedError('原始帧暂存已关闭或正在清理')
        if self.state != state:
            raise RuntimeError('原始帧暂存状态不允许此操作: ' + self.state)

    def _fail(self, exc):
        """保原根因、安装最高恢复owner，再有限尝试真实资源关闭。

        参数: exc为实际主异常。返回: None。异常: 清理副错只加note，不替换原错或取消对象。
        """
        self.state = 'cancelled' if isinstance(exc, (KeyboardInterrupt, SystemExit)) else 'failed'
        exc.raw_frame_store_cleanup_owner = self
        _cleanup_owner(self, exc, 'raw_frame_store_cleanup_owner', '原始帧暂存')

    def _reserve_spool(self, amount):
        """写入前逐笔预留累计磁盘，成功后取消也记录本笔，不倒扣保留文件。

        参数: amount为本行bytes。返回: None。异常: 原配额/取消；未成功不增加本owner金额。
        """
        before = self._budget.spool_bytes
        try:
            self._budget.reserve_spool(amount)
        finally:
            if self._budget.spool_bytes == before + amount:
                self._spool_bytes += amount

    def append(self, record, time_ns):
        """追加同次原帧，保0起连续sequence、非递减ns及全部同刻/未知ID。

        参数: record为LegacyDecodedFrame；time_ns为显式映射后int64整数，非原浮点秒。
        返回: None。异常: 原类型/顺序/编码/行长/预算/写入/取消；任何失败poison且不可seal。
        """
        self._require('building')
        try:
            if type(record) is not LegacyDecodedFrame:
                raise TypeError('原始帧暂存仅接受LegacyDecodedFrame')
            mapped = require_int64_ns(time_ns, 'raw_store.time_ns')
            if record.sequence != self.count or self._last_time_ns is not None and mapped < self._last_time_ns:
                raise ValueError('原始帧sequence必须从0连续且时间不能回退')
            # 编码前付完整wire工作空间；小max_row_bytes也不能漏算超长channel的拒绝路径。
            _reserve_owned_ram(self, 65536 + 64 * MAX_WIRE_BYTES, '_append_cost')
            body = encode_packet({'sequence': record.sequence, 'time_ns': mapped,
                                  'frame': frame_to_dict(record.frame)})
            self._pending_payload = body + b'\n'
            if len(self._pending_payload) > self.max_row_bytes:
                raise ValueError('原始帧编码行超过max_row_bytes')
            self._reserve_spool(len(self._pending_payload))
            # 真实unbuffered写可能只完成前缀；只要未完整成功，文件保留且流永久poison。
            offset = 0
            while offset < len(self._pending_payload):
                written = self._writer.write(self._pending_payload[offset:])
                if type(written) is not int or written <= 0:
                    raise OSError('原始帧写入未推进')
                offset += written
            if self._digest is not None:
                self._digest.update(self._pending_payload)
            self.count += 1
            self._last_time_ns = mapped
            self._pending_payload = None
            _release_owned_ram(self, self._append_cost, '_append_cost')
        except BaseException as exc:
            self._fail(exc)
            raise

    def _close_writer(self):
        """真实FD关闭后才清writer槽，close前持续失败保留同一handle。

        参数: 无。返回: None。异常: 原close/取消；close后抛错也据真实closed清槽。
        """
        if self._writer is not None:
            try:
                self._writer.close()
            finally:
                if self._writer.closed:
                    self._writer = None

    def seal(self):
        """成功关闭writer后固定整流SHA和条数，空来源亦可完整封口。

        参数: 无。返回: None。异常: 原flush/close/摘要/取消，失败不能读或再次seal。
        """
        self._require('building')
        try:
            self._writer.flush()
            self._close_writer()
            digest = self._digest.hexdigest() if self._digest is not None else None
            self.sha256, self.state = digest, 'sealed'
        except BaseException as exc:
            self._fail(exc)
            raise

    def iter_frames(self):
        """为已封口文件创建独立有限reader，不复用其他reader位置或原CAN输入。

        参数: 无。返回: 逐行StoredRawFrame迭代器。异常: 状态/预算/打开/注册/取消；
            未返回reader先在本父槽可达，持续关闭失败从最高raw_frame_store_cleanup_owner恢复。
        """
        self._require('sealed')
        try:
            reader = _RawFrameReader(self)
            self._pending_reader = None
            return reader
        except BaseException as exc:
            self._fail(exc)
            raise

    def close(self):
        """关闭本store的所有实际reader/writer及自有费用，文件和累计磁盘保留。

        参数: 无。返回: None，完成后重复调用安全。异常: 首个实际关闭/抵销错误原样传播，
            其他清理错仅note；未完槽不清，最高恢复owner就是本store，不接管借用账本。
        """
        if self._closed:
            return
        self._closing = True
        if self.state == 'building':
            self.state = 'cancelled'
        first_error = None
        # 未返回子对象先处理；close会解除自身登记，再处理其余活reader避免重复责任。
        if self._pending_reader is not None:
            try:
                self._pending_reader.close()
            except BaseException as exc:
                first_error = exc
        for reader in () if self._readers is None else tuple(self._readers):
            try:
                reader.close()
            except BaseException as exc:
                if first_error is None:
                    first_error = exc
                else:
                    first_error.add_note('原始帧其他reader关闭附加失败: ' + type(exc).__name__)
        try:
            self._close_writer()
        except BaseException as exc:
            if first_error is None:
                first_error = exc
            else:
                first_error.add_note('原始帧writer关闭附加失败: ' + type(exc).__name__)
        # 活stream数量的元数据和此关闭快照由每个reader费用覆盖，不与原行总数挂钩。
        if self._writer is None and self._pending_reader is None and not self._readers:
            self._pending_payload = None
            for slot in ('_append_cost', '_fixed_cost'):
                try:
                    _release_owned_ram(self, getattr(self, slot), slot)
                except BaseException as exc:
                    if first_error is None:
                        first_error = exc
                    else:
                        first_error.add_note('原始帧费用抵销附加失败: ' + type(exc).__name__)
            if self._held_cost == 0:
                self._closed = True
        if first_error is not None:
            first_error.raw_frame_store_cleanup_owner = self
            raise first_error


class _RawFrameReader:
    """持有一个文件位置、摘要和有界读槽，父只保实际活stream引用。

    关闭中禁止继续读；真实FD/本笔费用/父登记全部成功后closed。
    verified_eof须真实EOF、完整SHA/count和成功关闭，不从最后一条交付推断。
    """

    def __init__(self, owner):
        """先安装本父未返回槽，再预约/打开/登记真实reader。

        参数: owner为活sealed RawFrameStore。返回: 独立reader。异常: 原预算/打开/注册/取消；
            本构造不遗失self，由父工厂统一清理并附最高store恢复属性。
        """
        self.owner, self._budget = owner, owner.budget
        self.handle = self._digest = None
        self._fixed_cost = self._held_cost = self._count = 0
        self._last_time_ns = None
        self.closed = self._closing = self.verified_eof = False
        owner._pending_reader = self
        # 仅新原帧暂存预读8192字节，另预付16384；不改变旧reader或原逻辑行/EOF验证。
        # 同一handle持缓冲及raw FD，关闭失败继续由原pending/readers槽保责。
        _reserve_owned_ram(self, 65536 + 64 * owner.max_row_bytes + 16384, '_fixed_cost')
        self._digest = sha256() if owner.integrity else None
        self.handle = owner.file_path.open('rb', buffering=8192)
        owner._readers.add(self)

    def __iter__(self):
        """返回原位置。参数: 无。返回: self。异常: 无，不重新打开文件。"""
        return self

    def __next__(self):
        """限长读取并核原序/时间，完整EOF核流身份再关闭。

        参数: 无。返回: StoredRawFrame。异常: StopIteration仅完整EOF；损坏/预算/关闭/取消
            保原错且poison父，最高raw_frame_store_cleanup_owner可清全部真实资源。
        """
        if self.closed:
            raise StopIteration
        self.owner._require('sealed')
        if self._closing:
            raise ResultClosedError('原始帧reader正在清理')
        try:
            payload = self.handle.readline(self.owner.max_row_bytes + 1)
            if payload:
                if len(payload) > self.owner.max_row_bytes or not payload.endswith(b'\n'):
                    raise ResultFormatError('原始帧行超限或缺少完整换行')
                if self._count >= self.owner.count:
                    raise ResultFormatError('原始帧封口后出现额外后缀')
                packet = decode_packet(payload[:-1])
                if set(packet) != {'sequence', 'time_ns', 'frame'}:
                    raise ResultFormatError('原始帧暂存字段不完整或多余')
                record = StoredRawFrame(packet['sequence'], packet['time_ns'], frame_from_dict(packet['frame']))
                if record.sequence != self._count or self._last_time_ns is not None and record.time_ns < self._last_time_ns:
                    raise ResultFormatError('原始帧原序或纳秒时间被破坏')
                if self._digest is not None:
                    self._digest.update(payload)
                self._count += 1
                self._last_time_ns = record.time_ns
                return record
            # 仅实际文件EOF比较完整hash/count；最后一条已交付仍不能提前证明完整。
            if self._count != self.owner.count or self._digest is not None and self._digest.hexdigest() != self.owner.sha256:
                raise ResultFormatError('原始帧EOF条数或SHA不匹配')
            self.close()
        except BaseException as exc:
            self.owner._fail(exc)
            raise
        self.verified_eof = True
        raise StopIteration

    def close(self):
        """可重试关闭本reader，不关闭父或其他独立reader。

        参数: 无。返回: None。异常: 原FD/预算/解除登记错误，最高父恢复属性保持同一责任；
            真实FD关闭后抛取消也不重关，已释放费用不重复抵销。
        """
        if self.closed:
            return
        self._closing = True
        try:
            if self.handle is not None and not self.handle.closed:
                self.handle.close()
            _release_owned_ram(self, self._fixed_cost, '_fixed_cost')
            if self.owner._readers is not None:
                self.owner._readers.discard(self)
            if self.owner._pending_reader is self:
                self.owner._pending_reader = None
            self.closed = True
        except BaseException as exc:
            exc.raw_frame_store_cleanup_owner = self.owner
            raise
