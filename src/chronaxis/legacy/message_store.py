"""独立封存一次解码返回的完整原值，供后续消息分析回读。

append输入LegacyDecodedFrame、已显式映射的int64纳秒及量化标志；磁盘每行
保留固定store_version/time_ns/time_quantized外壳和原decoded包。内层仍用
现有64KiB严格records编码，外层只额外允许1024字节且包含换行，不改变IPC。
所有原帧、通道类型、原字段、0/False及非有限诊断均保留；不筛选、去重、
转换时间或数值，不生成evaluation_index或执行计算；求值记录由消息分析层产生。

完整写入才推进条数和流SHA；任意追加错误poison，封口须writer实际关闭。
独立reader按原序读取，真正EOF核全SHA/count并成功关闭FD及费用后才给
verified_eof。sealed仅证明本仓完整封口，不证明原来源已耗尽。

固定状态、单行编解码与各活reader均在分配前预付；只保存当前行和活reader，
返回记录和返回异常中的原wire有界诊断由调用方拥有并承担保留空间，预算估算
不含这些输出、调用方已有输入或整个进程RSS。close只关
本owner真实FD和实际费用，文件及累计磁盘预留保留，不抵销借用账本其他费用。
本模块只依赖标准库、现有冻结模型与轻量budget，不导入NumPy或旧CAN库。
若work_dir已是调用方Path，其首次str表示可能缓存于该借用输入；这部分表示与
原Path归调用方。本仓新建Path、语法验证及resolve等均在自身预付之后执行。
显式sparse_sequences只保存调用方选定的原记录，sequence保原值且严格递增；
count/SHA/line_limit均描述实际保存内容，不证明全输入条数或未保存内容。
"""

# 原包模型与严格JSON边界复用现有实现，文件与预算责任只由本仓承担。
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from ..core.validation import require_identifier, require_text
from ..results.budget import ResourceBudget, _cleanup_owner, _release_owned_ram, _reserve_owned_ram
from ..results.errors import ResultClosedError, ResultFormatError
from ..timebase.conversion import require_int64_ns
from .records import MAX_WIRE_BYTES, LegacyDecodedFrame, _decoded_from_packet, decoded_to_dict
from .records import decode_packet, encode_packet


# 外壳大小独立于原IPC；含换行的磁盘行始终不能超过此明确上限。
MAX_DECODED_MESSAGE_ROW_BYTES = MAX_WIRE_BYTES + 1024
_HEADER_LIMIT = 1024
_DECODED_BOUNDARY = b',"decoded":'


def _clear_records_traceback(exc: BaseException) -> None:
    """断开当前错误中已结束records函数的临时引用，保原错误及traceback结构。

    参数: exc为当前编码或解析原异常，只沿其自身__traceback__逐节点检查。
    返回: None；只清精确chronaxis.legacy.records模块的已结束frame局部引用。
    异常: 活跃frame.clear的RuntimeError表示不可清，原样跳过；不递归cause/context，
        不清用户、测试、stdlib、CAN或本仓活跃帧，也不删JSON/Unicode错误诊断字段。
    """
    # 不收集TB或异常链，避免因错误context环或历史异常建立无界遍历/visited状态。
    current = exc.__traceback__
    while current is not None:
        frame = current.tb_frame
        if frame.f_globals.get('__name__') == 'chronaxis.legacy.records':
            try:
                frame.clear()
            except RuntimeError:
                pass
        current = current.tb_next


@dataclass(frozen=True)
class StoredDecodedMessage:
    """冻结一条已映射时间的完整解码返回，不制造旧或新求值序号。

    time_ns仅按共享时间协议规范，time_quantized必须由调用方明确提供。
    decoded保原LegacyDecodedFrame对象；合法值域沿原records，不额外开放
    None/str解码值。原channel的None/str/int类型不受目标帧通道规则改写。
    """

    time_ns: int  # 调用方显式映射后的会话坐标，不在仓中再次加偏移。
    time_quantized: bool  # 原转换的量化事实，不由浮点时间猜测。
    decoded: LegacyDecodedFrame  # 一次原yield和parse的完整冻结返回。

    def __post_init__(self) -> None:
        """核对单条存储模型，保原decoded引用及独立端点范围。

        参数: 无，读取三个构造字段。
        返回: None；只将time_ns规范成原生int，不重建decoded或计算时间跨度。
        异常: TypeError为类型不符；TimeOverflowError为时间超int64。
        """
        # 模型不要求通道为int；那是后续目标帧政策，不能在原序仓提前施加。
        mapped = require_int64_ns(self.time_ns)
        if type(self.time_quantized) is not bool:
            raise TypeError('time_quantized必须为原生bool')
        if type(self.decoded) is not LegacyDecodedFrame:
            raise TypeError('decoded必须为LegacyDecodedFrame')
        object.__setattr__(self, 'time_ns', mapped)


def _encode_row(record: LegacyDecodedFrame, time_ns: int, time_quantized: bool) -> bytes:
    """分别严格编码小外壳和原decoded包，再拼固定的decoded末字段。

    参数: record为原冻结返回；time_ns和time_quantized已经由append校验。
    返回: bytes；完整JSON对象加换行，原decoded payload不超过MAX_WIRE_BYTES。
    异常: 原records类型、限额、编码、分配或取消异常，不修改全局wire限额。
    """
    header = packet = inner = result = None
    try:
        # header无自由文本或嵌套；原值树始终单独经过原64KiB边界。
        header = encode_packet({'store_version': 1, 'time_ns': time_ns,
                                'time_quantized': time_quantized})
        packet = decoded_to_dict(record)
        inner = encode_packet(packet)
        result = header[:-1] + _DECODED_BOUNDARY + inner + b'}\n'
        return result
    except BaseException as exc:
        # 原codec失败frame也可能保留payload树；只清其已结束局部，不替换异常或TB节点。
        _clear_records_traceback(exc)
        raise
    finally:
        # 调用方可能长期保留原异常，不能由本层frame继续保活编码副本。
        header = packet = inner = result = None


def _decode_row(payload: bytes) -> StoredDecodedMessage:
    """在明确磁盘上限内拆固定边界，分别调用原严格包解析器。

    参数: payload为带完整换行的有界磁盘行，decoded必须为最后字段。
    返回: StoredDecodedMessage，原diagnostic标签按现records模型恢复。
    异常: ResultFormatError为外壳、重复/多余字段、原包或模型不合法；
        内存或取消错误保持原样，不用不受限JSON解析绕过IPC边界。
    """
    header_bytes = inner_bytes = header = decoded = None
    try:
        # 外层只允许固定小header；取第一个边界，不被原信号名中的同形文本干扰。
        if not payload.endswith(b'}\n'):
            raise ResultFormatError('解码仓行缺少完整外层或换行')
        boundary = payload.find(_DECODED_BOUNDARY)
        if boundary < 0 or boundary + 1 > _HEADER_LIMIT:
            raise ResultFormatError('解码仓固定decoded边界缺失或header超限')
        header_bytes = payload[:boundary] + b'}'
        inner_bytes = payload[boundary + len(_DECODED_BOUNDARY):-2]
        header = decode_packet(header_bytes)
        if set(header) != {'store_version', 'time_ns', 'time_quantized'}:
            raise ResultFormatError('解码仓外壳字段缺失、多余或decoded位置错误')
        if type(header['store_version']) is not int or header['store_version'] != 1:
            raise ResultFormatError('解码仓store_version必须为原生整数1')
        # 小header先校验完，坏端点或量化标志不应先生成一份大decoded记录。
        mapped = require_int64_ns(header['time_ns'], 'message_store.time_ns')
        if type(header['time_quantized']) is not bool:
            raise ResultFormatError('解码仓time_quantized必须为原生bool')
        # 原payload仍独立核完整JSON/模型及64KiB/ITEM上限；固定小包可用正证明
        # 省重复遍历，复杂输入回原严格入口，不将整个超64KiB磁盘行当作原包解析。
        decoded = _decoded_from_packet(inner_bytes)
        return StoredDecodedMessage(mapped, header['time_quantized'], decoded)
    except (TypeError, ValueError, OverflowError) as exc:
        # 结构错误保为格式错误的原cause；先结束records帧的临时责任，再由父收尾费用。
        _clear_records_traceback(exc)
        raise ResultFormatError('解码仓行结构或原decoded包损坏') from exc
    except BaseException as exc:
        # 取消/内存错误不包装，也只处理本次TB中的records临时引用。
        _clear_records_traceback(exc)
        raise
    finally:
        # 返回对象由调用方拥有；失败时本层临时字典和bytes不留在traceback中。
        payload = header_bytes = inner_bytes = header = decoded = None


class DecodedMessageStore:
    """拥有一个新JSONL、封口事实和所有独立reader的实际资源责任。

    state为building/sealed/failed/cancelled；closed仅在自有FD和费用全部完成后真。
    _pending_reader在子构造副作用前安装，_readers只保活reader。固定/append槽
    与累计_spool_bytes各自记真实交易，不由共享账本余额猜测本owner归属。
    """

    def __init__(self, budget, work_dir, source_name, session_id, *, decoder_profile,
                 read_identity, max_row_bytes=MAX_DECODED_MESSAGE_ROW_BYTES, sparse_sequences=False, integrity=True):
        """预付有限状态并在显式全新目录打开唯一writer，拒绝已有目录。

        参数: budget为借用ResourceBudget；work_dir为新原生str/Path；source_name/session_id
            为原生str简单名称；decoder_profile/read_identity为原生非空文本；max_row_bytes为
            1至MAX_DECODED_MESSAGE_ROW_BYTES，包含换行；sparse_sequences显式允许原序号有间隔，
            仍严格递增，count/SHA仅表示实际保存的记录，默认仍要求从0连续。
        返回: building仓；不读取BLF/DBC或证明来源EOF。
        异常: 类型、路径、预算、文件或取消原错；持续清理失败保最高
            decoded_message_store_cleanup_owner，恢复后对同一owner.close。
        """
        if not isinstance(budget, ResourceBudget) or not (type(work_dir) is str or isinstance(work_dir, Path)):
            raise TypeError('解码仓需要ResourceBudget及显式新目录')
        # 先装全部真实责任槽，之后reserve更新后取消或mkdir失败都可从本owner恢复。
        if type(integrity) is not bool: raise TypeError('integrity需要bool')
        self.integrity=integrity
        self.budget = self._budget = budget
        self.source_name, self.session_id = source_name, session_id
        self.decoder_profile, self.read_identity = decoder_profile, read_identity
        self.max_row_bytes = max_row_bytes
        self.sparse_sequences, self._last_sequence = sparse_sequences, -1
        self._line_limit = 1
        self.path = self.work_dir = self.file_path = None
        self._writer = self._pending_reader = self._pending_payload = None
        self._readers = self._digest = None
        self._fixed_cost = self._append_cost = self._held_cost = self._spool_bytes = 0
        self.count, self.sha256, self._last_time_ns = 0, None, None
        self.state, self._closed, self._closing = 'building', False, False
        try:
            # 先用无副本类型及长度估费，避免长文本strip或新Path解析先于预算拒绝。
            if any(type(value) is not str for value in (source_name, session_id, decoder_profile, read_identity)):
                raise TypeError('解码仓来源、会话、profile和read_identity需要原生str')
            if type(sparse_sequences) is not bool:
                raise TypeError('sparse_sequences必须为原生bool')
            if type(max_row_bytes) is not int or not 1 <= max_row_bytes <= MAX_DECODED_MESSAGE_ROW_BYTES:
                raise ValueError('解码仓行上限需要合法范围内的原生int')
            # 原生str直接取len；已有Path的str缓存属于借用输入，不创建本仓Path副本。
            path_length = len(work_dir) if type(work_dir) is str else len(str(work_dir))
            cost = 65536 + 32 * (path_length + len(source_name) + len(session_id)
                                 + len(decoder_profile) + len(read_identity))
            _reserve_owned_ram(self, cost, '_fixed_cost')
            # 费用已实际归属后才允许语法验证的strip临时文本和本仓路径构造。
            require_identifier(source_name, 'message_store.source_name')
            require_identifier(session_id, 'message_store.session_id')
            require_text(decoder_profile, 'decoder_profile')
            require_text(read_identity, 'read_identity')
            requested = Path(work_dir)
            # 先解析实际路径并检查存在性，不写已有目录或错误诊断文件。
            resolved = requested.resolve()
            if resolved.exists():
                raise FileExistsError(resolved)
            self.path = self.work_dir = resolved
            self._readers, self._digest = set(), sha256() if integrity else None
            resolved.mkdir(parents=True, exist_ok=False)
            self.file_path = resolved / 'decoded_messages.jsonl'
            self._writer = self.file_path.open('xb', buffering=0)
        except BaseException as exc:
            self._fail(exc)
            raise

    @property
    def line_limit(self):
        """读取完整成功写入行的实际最大字节数，空仓取1以保持有限读上界。

        参数: 无。返回: 正int，只由本仓成功append推进；公开硬限仍为max_row_bytes。
        异常: 无；文件损坏、未完成写入和外部stat都不会提高此值。
        """
        return self._line_limit

    @property
    def closed(self):
        """读取实际完整关闭事实；参数: 无；返回: bool；异常: 无。"""
        return self._closed

    @property
    def spool_bytes(self):
        """读取本owner累计磁盘预留；参数: 无；返回: bytes整数；异常: 无。"""
        return self._spool_bytes

    def _require(self, state):
        """校验活owner及所需构建状态，不把关闭或poison伪装成空流。

        参数: state为building或sealed。返回: None。
        异常: ResultClosedError为关闭中；RuntimeError为状态不匹配。
        """
        if self._closed or self._closing:
            raise ResultClosedError('解码仓已关闭或正在清理')
        if self.state != state:
            raise RuntimeError('解码仓状态不允许此操作: ' + self.state)

    def _fail(self, exc):
        """保原异常并poison，有限尝试清理，持续失败保最高真实仓owner。

        参数: exc为主异常。返回: None。
        异常: 清理副错只加notes，不覆盖同一普通错误、KeyboardInterrupt或SystemExit。
        """
        self.state = 'cancelled' if isinstance(exc, (KeyboardInterrupt, SystemExit)) else 'failed'
        exc.decoded_message_store_cleanup_owner = self
        _cleanup_owner(self, exc, 'decoded_message_store_cleanup_owner', '解码仓')

    def _reserve_spool(self, amount):
        """写入前累计本笔磁盘预留，更新后取消也记录实际归属且不倒扣文件。

        参数: amount为本行bytes。返回: None。
        异常: 原配额或取消错误；未入账不增加本owner累计。
        """
        before = self._budget.spool_bytes
        try:
            self._budget.reserve_spool(amount)
        finally:
            if self._budget.spool_bytes == before + amount:
                self._spool_bytes += amount

    def _write_pending(self):
        """处理真实短写，并在错误传播前释放所有新建memoryview引用。

        参数: 无；读取本owner已预付、已预约磁盘的_pending_payload。
        返回: None，全部字节已交真实writer。
        异常: 原写入/取消错误或OSError无推进；失败前缀由父保留并poison。
        """
        view = part = None
        try:
            # 使用可释放view，避免短写切片复制及错误wrapper保活本层待写bytes。
            view = memoryview(self._pending_payload)
            offset = 0
            while offset < len(view):
                try:
                    part = view[offset:]
                    written = self._writer.write(part)
                    if type(written) is not int or not 0 < written <= len(part):
                        raise OSError('解码仓写入未推进或返回非法长度')
                    offset += written
                finally:
                    if part is not None:
                        part.release()
                        part = None
        finally:
            if view is not None:
                view.release()
            view = part = None

    def append(self, record, time_ns, *, time_quantized):
        """完整保存一次原yield，原序和完整写入成立后才推进count/SHA。

        参数: record为LegacyDecodedFrame；time_ns已由调用方映射；time_quantized
            为明确原生bool。全部channel和值沿原模型，不套目标帧或求值规则。
        返回: None。异常: 类型、时间、顺序、编码、行长、预算、磁盘、写入或取消
            原错；任意追加失败poison，最高owner可恢复但不能再seal或读前缀。
        """
        self._require('building')
        try:
            # 身份序号必须0起连续，时间可同刻；只校单端点，不计算可能溢出的跨度。
            if type(record) is not LegacyDecodedFrame:
                raise TypeError('解码仓仅接受LegacyDecodedFrame')
            mapped = require_int64_ns(time_ns, 'message_store.time_ns')
            if type(time_quantized) is not bool:
                raise TypeError('time_quantized必须为原生bool')
            if (record.sequence <= self._last_sequence if self.sparse_sequences else record.sequence != self.count) or self._last_time_ns is not None and mapped < self._last_time_ns:
                raise ValueError('解码仓sequence不满足声明连续/稀疏顺序或time_ns回退')
            # 按完整能力预付编码拒绝路径，不因用户设置很小的行上限漏算内层包工作区。
            _reserve_owned_ram(self, 65536 + 64 * MAX_DECODED_MESSAGE_ROW_BYTES, '_append_cost')
            self._pending_payload = _encode_row(record, mapped, time_quantized)
            if len(self._pending_payload) > self.max_row_bytes:
                raise ValueError('解码仓行超过max_row_bytes')
            self._reserve_spool(len(self._pending_payload))
            self._write_pending()
            # 当前行已完整写入；后续任何故障仍poison，不把部分或不确定状态重新开放。
            if self._digest is not None:
                self._digest.update(self._pending_payload)
            self.count += 1
            self._line_limit = max(self._line_limit, len(self._pending_payload))
            self._last_time_ns, self._last_sequence = mapped, record.sequence
            self._pending_payload = None
            _release_owned_ram(self, self._append_cost, '_append_cost')
        except BaseException as exc:
            self._pending_payload = None
            self._fail(exc)
            raise

    def _close_writer(self):
        """按真实FD关闭事实清writer槽，持续close前失败保留原handle。

        参数: 无。返回: None。
        异常: 原FD或取消错误；实际closed后抛错也不重关已经完成的handle。
        """
        # close返回或抛错都检查同一真实handle；只在实际closed后撤除父writer槽。
        if self._writer is not None:
            try:
                self._writer.close()
            finally:
                if self._writer.closed:
                    self._writer = None

    def seal(self):
        """flush并实际关闭writer后才固定SHA及sealed，不证明原来源EOF。

        参数: 无。返回: None；空仓也可完整封口。
        异常: 原flush、close、摘要或取消错误；poison后不再读或重试seal。
        """
        self._require('building')
        try:
            # 先完成真实输入FD责任，再开放可读事实，不能只因最后append成功就sealed。
            self._writer.flush()
            self._close_writer()
            self.sha256, self.state = (self._digest.hexdigest() if self._digest is not None else None), 'sealed'
        except BaseException as exc:
            self._fail(exc)
            raise

    def iter_records(self):
        """创建独立有预算原序reader，构造未返回责任先由本父真实槽保存。

        参数: 无。返回: 逐条StoredDecodedMessage reader；各自位置互不干扰。
        异常: 状态、预算、打开、登记或取消原错，最高仓owner可恢复全部实际子资源。
        """
        self._require('sealed')
        try:
            reader = _DecodedMessageReader(self)
            self._pending_reader = None
            return reader
        except BaseException as exc:
            self._fail(exc)
            raise

    def close(self):
        """可重试关闭所有自有stream及实际费用，保留文件与累计磁盘申请。

        参数: 无。返回: None；所有责任闭合才closed=True，重复close幂等。
        异常: 首个关闭/抵销错误原样传播，其他错误只note；最高owner不变，不关闭
            借用budget或释放其他owner费用，不删除文件及已交付调用方的记录。
        """
        # 完全关闭才幂等返回；开始关闭立即拒新操作，未封口构建只留下取消前缀。
        if self._closed:
            return
        self._closing = True
        if self.state == 'building':
            self.state = 'cancelled'
        first_error = None
        # 未返回实例先关；成功时子会解除登记，剩余活stream再逐一处理。
        if self._pending_reader is not None:
            try:
                self._pending_reader.close()
            except BaseException as exc:
                first_error = exc
        readers = None
        try:
            # 当前活stream数受各reader费用限制；快照分配失败也保留父实际登记继续恢复。
            readers = () if self._readers is None else tuple(self._readers)
            for reader in readers:
                try:
                    reader.close()
                except BaseException as exc:
                    if first_error is None:
                        first_error = exc
                    else:
                        first_error.add_note('解码仓其他reader关闭附加失败: ' + type(exc).__name__)
        except BaseException as exc:
            if first_error is None:
                first_error = exc
            else:
                first_error.add_note('解码仓reader关闭快照附加失败: ' + type(exc).__name__)
        finally:
            # 原异常不保活一个已抵费的全stream快照，真正未关实例仍在父登记中。
            readers = None
        try:
            self._close_writer()
        except BaseException as exc:
            if first_error is None:
                first_error = exc
            else:
                first_error.add_note('解码仓writer关闭附加失败: ' + type(exc).__name__)
        # 每个活reader费用覆盖其登记及关闭快照；父固定费必须等所有子和writer闭合。
        if self._writer is None and self._pending_reader is None and not self._readers:
            self._pending_payload = None
            for slot in ('_append_cost', '_fixed_cost'):
                try:
                    _release_owned_ram(self, getattr(self, slot), slot)
                except BaseException as exc:
                    if first_error is None:
                        first_error = exc
                    else:
                        first_error.add_note('解码仓费用抵销附加失败: ' + type(exc).__name__)
            if self._held_cost == 0:
                self._closed = True
        if first_error is not None:
            first_error.decoded_message_store_cleanup_owner = self
            raise first_error


class _DecodedMessageReader:
    """拥有独立FD、SHA/count和有界单行空间，不持有已交付记录列表。

    verified_eof只在真实EOF、完整SHA/count和实际FD/费用/登记全部关闭后为True。
    提前close不产生证明；关闭中拒绝读，未返回构造实例先由父pending槽接管。
    """

    def __init__(self, owner):
        """先安装真实未返回子槽，再预约、打开和登记独立reader。

        参数: owner为活sealed DecodedMessageStore。
        返回: None；初始化实例状态；父工厂成功返回前一直可从_pending_reader找到本实例。
        异常: 原预算、打开、登记或取消错误，由父工厂保原错并统一清理最高owner。
        """
        self.owner, self._budget = owner, owner.budget
        self.handle = self._digest = None
        self._fixed_cost = self._held_cost = self._count = 0
        self._last_time_ns, self._last_sequence = None, -1
        self.closed = self._closing = self.verified_eof = False
        # 父先接责任，register前后取消都不让真实FD或已经入账的费用脱离owner。
        owner._pending_reader = self
        # 新暂存允许8192字节有限预读；另预付16384覆盖buffer及对象，仍按逻辑行核限长/EOF。
        # 旧CAN读取不变；新暂存底层调用次数/取消时机可变化，handle仍负责buffer及raw FD。
        _reserve_owned_ram(self, 65536 + 64 * owner.max_row_bytes + 16384, '_fixed_cost')
        self._digest = sha256() if owner.integrity else None
        self.handle = owner.file_path.open('rb', buffering=8192)
        owner._readers.add(self)

    def __iter__(self):
        """返回同一独立位置；参数: 无；返回: self；异常: 无。"""
        return self

    def __next__(self):
        """限长读一行并核原序，完整EOF且成功close后才产生verified_eof。

        参数: 无。返回: StoredDecodedMessage；最后一行交付仍未验证EOF。
        异常: StopIteration仅在关闭或真正完成；ResultFormatError为损坏；原IO、
            预算或取消错误保留并poison父，最高decoded_message_store_cleanup_owner可恢复。
        """
        if self.closed:
            raise StopIteration
        self.owner._require('sealed')
        if self._closing:
            raise ResultClosedError('解码仓reader正在清理')
        payload = record = None
        try:
            # 多读至多1字节识别超限；没有完整换行的尾行不能当作正常最后记录。
            limit = min(self.owner.max_row_bytes, self.owner.line_limit)
            payload = self.handle.readline(limit + 1)
            if payload:
                if len(payload) > limit or not payload.endswith(b'\n'):
                    raise ResultFormatError('解码仓行超过封口实测上限/公共硬限或缺少换行')
                if self._count >= self.owner.count:
                    raise ResultFormatError('解码仓封口后存在额外后缀')
                record = _decode_row(payload)
                if (record.decoded.sequence <= self._last_sequence if self.owner.sparse_sequences
                        else record.decoded.sequence != self._count) or (
                        self._last_time_ns is not None and record.time_ns < self._last_time_ns):
                    raise ResultFormatError('解码仓原sequence或时间顺序损坏')
                if self._digest is not None:
                    self._digest.update(payload)
                self._count += 1
                self._last_time_ns, self._last_sequence = record.time_ns, record.decoded.sequence
                return record
            # 真实EOF才核全流，不以已交付行数、最后一次readline或seal事实代替核验。
            if self._count != self.owner.count or self._digest is not None and self._digest.hexdigest() != self.owner.sha256:
                raise ResultFormatError('解码仓EOF条数或SHA不匹配')
            self.close()
        except BaseException as exc:
            payload = record = None
            self.owner._fail(exc)
            raise
        finally:
            # 调用方保留的异常或已返回记录不应使本reader继续保活已抵费单行副本。
            payload = record = None
        self.verified_eof = True
        raise StopIteration

    def close(self):
        """只关闭本reader，可从持续真实FD或预算失败恢复而不影响其他位置。

        参数: 无。返回: None；FD、费用及父登记都成功完成才closed=True。
        异常: 原FD、抵销、登记或取消错误，最高父owner可达；真实已关闭handle不重关，
            已抵销费用不重扣，提前close不设置verified_eof。
        """
        # 重试仅处理未完成责任，不能因先前部分成功再次关闭FD或抵销其他owner费用。
        if self.closed:
            return
        self._closing = True
        try:
            # 实际FD关闭前不解除父责任，失败后仍保留原handle供close重试。
            if self.handle is not None and not self.handle.closed:
                self.handle.close()
            _release_owned_ram(self, self._fixed_cost, '_fixed_cost')
            if self.owner._readers is not None:
                self.owner._readers.discard(self)
            if self.owner._pending_reader is self:
                self.owner._pending_reader = None
            self.closed = True
        except BaseException as exc:
            exc.decoded_message_store_cleanup_owner = self.owner
            raise
