"""为已解码CAN记录定义有界批次字节包，不执行读取、解码或任意对象反序列化。

固定头保存版本、原始起始序号、原帧数、EOF和保留记录数。旧CXB1保全部原float64
时间；按需CXB2按source/selected/none保留所需时间与完整回退计数，再逐条传严格JSON。
允许仅保留计划需要的记录，原序号不重排，未采时间绝不以零秒补齐。
单条仍受原64KiB限制；整包最多256KiB、最多4096帧。调用者须先预约工作空间。
本模块仅依赖标准库和既有模型，不打开文件、导入CAN库或持有预算/进程资源。
"""

from dataclasses import dataclass
from math import isfinite
import struct

from .records import MAX_WIRE_BYTES, LegacyDecodedFrame, _decoded_from_packet
from .required_records import RequiredDecodedFrame, required_from_packet


MAX_BATCH_BYTES = 262144  # 数据包上限；控制包仍使用原64KiB严格JSON。
MAX_BATCH_ROWS = 4096  # 许可的是原始帧数，包括不保留完整值的帧。
BATCH_MAGIC = b'CXB1'  # 固定第一版批次格式，与旧JSON控制包可明确区分。
HEADER = struct.Struct('>4sQIBI')  # magic/start/count/eof/selected_count。
DEMAND_MAGIC = b'CXB2'  # 原帧计数独立于时间；明确不能按旧全时间包解释。
DEMAND_HEADER = struct.Struct('>4sQIBIBI')  # scope 0=none/1=selected/2=source，末项完整回退数。
FILE_MAGIC = b'CXF1'  # 连续输入批次的文件位置外壳；内部仍是CXB1/CXB2。
FILE_HEADER = struct.Struct('>4sI')  # 每批只属于一个输入，空文件可跳过。
LENGTH = struct.Struct('>I')  # 每条原记录的JSON长度，不隐含pickle或压缩。
MIN_BATCH_BYTES = HEADER.size + 8 + LENGTH.size + MAX_WIRE_BYTES


@dataclass(frozen=True)
class LegacyDecodedBatch:
    """持有已核批次的全量时间和稀疏完整记录，借用至read下一次推进或关闭。

    source的timestamps对应每个原yield，selected仅对应保留records，none为空；
    frame_count始终为原始跨度。records保严格递增原序号且可能为空。对象只能在解包完成后由内部建立，
    外部自行构造不构成输入已验证证明；保留借用对象的调用方另承担其内存费用。
    """

    start_sequence: int  # 本批第一个原yield序号，不是保留记录的密集序号。
    timestamps: tuple[float, ...]  # 所有原yield的精确二进制浮点秒。
    records: tuple[LegacyDecodedFrame | RequiredDecodedFrame, ...]  # source保完整原帧，其他保必要身份。
    raw_count: int | None = None  # 新包独立原帧数；旧包None兼容原timestamps长度。
    time_scope: str = 'source'  # source全来源，selected仅保留目标，none不采时间。
    full_check_count: int = 0  # 新auto包中非原生输入执行完整原帧检查的数量。
    protocol_version: int = 1  # 区分source全时间的新包与旧包，证明含义不可混用。

    input_index: int = 0  # 当前批所在原序文件；单文件为0，不逐条复制路径。

    @property
    def frame_count(self):
        """读取原帧数而非时间数量。参数: 无。返回: int。异常: 无。"""
        return len(self.timestamps) if self.raw_count is None else self.raw_count


def encode_batch(start_sequence, timestamps, records, eof, byte_limit, *, raw_count=None, time_scope='source',
                 input_check='full', full_check_count=0):
    """拼接已经逐条严格编码的记录，检查物理容量后才创建最终包。

    参数: start_sequence为原起点；timestamps为有限float列表；records为已编码bytes列表；
        eof为真实原StopIteration标记；byte_limit为本次已获准字节上限；raw_count为原跨度，
        input_check/time_scope决定旧全时间或新按需包，full_check_count为非原生完整检查数。
    返回: bytes数据包。异常: 类型、容量或边界错误；不调用旧读取器或补帧。
    边界: 这是内部编码器，记录语义由原模型/编码器及接收端再次严格检查。
    """
    if input_check not in ('auto', 'full'):
        raise ValueError('输入检查范围需要auto/full')
    if input_check == 'full' and time_scope != 'source':
        raise ValueError('完整检查必须保留全来源时间')
    if time_scope != 'source' or input_check == 'auto':
        return _encode_required_batch(start_sequence, timestamps, records, eof, byte_limit,
            raw_count=raw_count, time_scope=time_scope, full_check_count=full_check_count)
    if raw_count is not None and (type(raw_count) is not int or raw_count != len(timestamps)):
        raise ValueError('全来源时间批次原帧计数必须与时间数量一致')
    if type(start_sequence) is not int or not 0 <= start_sequence < 2**64 or type(eof) is not bool:
        raise ValueError('批次起点或EOF类型非法')
    if (type(byte_limit) is not int or not MIN_BATCH_BYTES <= byte_limit <= MAX_BATCH_BYTES
            or not 0 <= len(timestamps) <= MAX_BATCH_ROWS or len(records) > len(timestamps)
            or start_sequence + len(timestamps) >= 2**64):
        raise ValueError('批次容量、计数或序号越界')
    if not timestamps and not eof:
        raise ValueError('空批次只能报告真实EOF')
    if any(type(t) is not float or not isfinite(t) for t in timestamps):
        raise ValueError('原报文timestamp需要有限float秒')
    if any(type(row) is not bytes or not 0 < len(row) <= MAX_WIRE_BYTES for row in records):
        raise ValueError('批次单条记录必须是原限额内bytes')
    size = HEADER.size + 8*len(timestamps) + sum(LENGTH.size+len(row) for row in records)
    if size > byte_limit:
        raise ValueError('批次编码超过已授权字节上限')
    # 拼接时保留原顺序；有限列表/最终副本由父预付的批次工作空间覆盖。
    chunks = [HEADER.pack(BATCH_MAGIC, start_sequence, len(timestamps), int(eof), len(records)),
              struct.pack('>'+str(len(timestamps))+'d', *timestamps)]
    for row in records:
        chunks.extend((LENGTH.pack(len(row)), row))
    return b''.join(chunks)


def decode_batch(payload, *, expected_start, row_limit, byte_limit, frame_ids, time_scope='source',
                 input_check='full'):
    """核物理边界、原序号、时间和投影完整性，解包后才交付不可变批次。

    参数: payload为recv_bytes取得的受限bytes；expected_start/row_limit/byte_limit
        为本次唯一许可；frame_ids=None要求全量，tuple表示允许保留的ID；
        input_check/time_scope必须与READY确认策略相同，不能按另一个范围解释字节。
    返回: (LegacyDecodedBatch, eof)；EOF仍须由read确认子退出和关闭才生效。
    异常: 原JSON/模型检查错误或ValueError为坏包、乱序、长度/时间不符。
    边界: 父先付费；本函数不依靠头内数量分配无限数组，也不忽略尾随字节。
    """
    if input_check not in ('auto', 'full'):
        raise ValueError('输入检查范围需要auto/full')
    if input_check == 'full' and time_scope != 'source':
        raise ValueError('完整检查必须保留全来源时间')
    if time_scope != 'source' or input_check == 'auto':
        return _decode_required_batch(payload, expected_start=expected_start, row_limit=row_limit,
            byte_limit=byte_limit, frame_ids=frame_ids, time_scope=time_scope)
    timestamps = records = record = None
    try:
        if type(payload) is not bytes or not HEADER.size <= len(payload) <= byte_limit:
            raise ValueError('批次字节长度非法')
        magic, start, count, eof, retained = HEADER.unpack_from(payload)
        if (magic != BATCH_MAGIC or start != expected_start or not 0 <= count <= row_limit
                or eof not in (0, 1) or retained > count or start+count >= 2**64
                or count == 0 and not eof):
            raise ValueError('批次头与本次许可不符')
        position = HEADER.size + count*8
        if position > len(payload):
            raise ValueError('批次时间数组被截断')
        timestamps = struct.unpack_from('>'+str(count)+'d', payload, HEADER.size)
        if any(not isfinite(value) for value in timestamps):
            raise ValueError('原报文timestamp需要有限float秒')
        records, previous = [], start-1
        try:
            for _ in range(retained):
                if position+LENGTH.size > len(payload):
                    raise ValueError('批次记录长度被截断')
                size = LENGTH.unpack_from(payload, position)[0]
                position += LENGTH.size
                if not 0 < size <= MAX_WIRE_BYTES or position+size > len(payload):
                    raise ValueError('批次记录超限或被截断')
                # 专用入口保UTF-8/重复键、完整frame/值及ITEM限额；能证明固定小包
                # 合法时只解析构造一次，复杂输入仍由原完整入口决定精确错误顺序。
                record = _decoded_from_packet(payload[position:position+size])
                position += size
                if not previous < record.sequence < start+count:
                    raise ValueError('批次记录原序号乱序、重复或越界')
                if record.frame.timestamp.hex() != timestamps[record.sequence-start].hex():
                    raise ValueError('批次原时间与记录时间不一致')
                if frame_ids is not None and record.frame.arbitration_id not in frame_ids:
                    raise ValueError('批次返回未声明保留的报文ID')
                previous = record.sequence
                records.append(record)
            if position != len(payload) or frame_ids is None and retained != count:
                raise ValueError('批次存在尾随字节或全量记录缺项')
            return LegacyDecodedBatch(start, timestamps, tuple(records)), bool(eof)
        finally:
            # 失败异常可能由外层保存，不让已结束解包frame额外保活整批缓冲/模型。
            payload = timestamps = records = record = None
    finally:
        # 原错误可留在调用方；已结束调用的临时引用不继续占有整批对象。
        payload = timestamps = records = record = None


def record_payload_offset(batch):
    """定位已验证包中记录长度前缀区域。参数: batch为已解包批次。返回: 字节偏移。异常: ValueError为未知scope。"""
    if batch.protocol_version == 1 and batch.time_scope == 'source':
        return HEADER.size + 8*batch.frame_count
    if batch.protocol_version == 2 and batch.time_scope in ('none', 'selected', 'source'):
        return DEMAND_HEADER.size + (8*batch.frame_count if batch.time_scope == 'source' else 0)
    raise ValueError('未知批次时间范围')


def _encode_required_batch(start_sequence, timestamps, records, eof, byte_limit, *, raw_count, time_scope,
                           full_check_count):
    """建立独立原帧计数的稀疏包，时间仅在目标JSON内。

    参数: start_sequence/raw_count为原序跨度；timestamps在selected与目标数相同，none必须空；
        records为已严格编码的按需记录；其余限制沿原包。返回: bytes。异常: 类型或容量错误。
    """
    if time_scope not in ('none', 'selected', 'source'):
        raise ValueError('批次时间范围需要source/selected/none')
    if (type(start_sequence) is not int or not 0 <= start_sequence < 2**64 or type(eof) is not bool
            or type(raw_count) is not int or not 0 <= raw_count <= MAX_BATCH_ROWS
            or start_sequence+raw_count >= 2**64 or len(records) > raw_count
            or raw_count == 0 and not eof or type(full_check_count) is not int
            or not 0 <= full_check_count <= raw_count):
        raise ValueError('按需批次起点、原计数或EOF非法')
    if (type(byte_limit) is not int or not MIN_BATCH_BYTES <= byte_limit <= MAX_BATCH_BYTES
            or time_scope == 'none' and timestamps
            or time_scope == 'selected' and len(timestamps) != len(records)
            or time_scope == 'source' and len(timestamps) != raw_count):
        raise ValueError('按需批次容量或时间数量非法')
    if any(type(t) is not float or not isfinite(t) for t in timestamps):
        raise ValueError('所需报文timestamp需要有限float秒')
    if any(type(row) is not bytes or not 0 < len(row) <= MAX_WIRE_BYTES for row in records):
        raise ValueError('批次单条记录必须是原限额内bytes')
    time_bytes = 8*raw_count if time_scope == 'source' else 0
    if DEMAND_HEADER.size + time_bytes + sum(LENGTH.size+len(row) for row in records) > byte_limit:
        raise ValueError('批次编码超过已授权字节上限')
    # 不传输任何未使用的原时间数组；selected时间已经包含在目标记录内。
    chunks = [DEMAND_HEADER.pack(DEMAND_MAGIC, start_sequence, raw_count, int(eof), len(records),
                                 {'none': 0, 'selected': 1, 'source': 2}[time_scope], full_check_count)]
    if time_scope == 'source':
        chunks.append(struct.pack('>'+str(raw_count)+'d', *timestamps))
    for row in records:
        chunks.extend((LENGTH.pack(len(row)), row))
    return b''.join(chunks)


def _decode_required_batch(payload, *, expected_start, row_limit, byte_limit, frame_ids, time_scope):
    """严格核对稀疏包原跨度、scope、目标顺序及每条必要身份和值。

    参数: 与decode_batch相同，time_scope必须为none/selected。返回: (批次,真实EOF候选)。
    异常: 未许可范围、坏包、JSON/模型或取消错误；不会用假时间凑原帧数量。
    """
    records = record = timestamps = None
    try:
        if (time_scope not in ('none', 'selected', 'source') or type(payload) is not bytes
                or not DEMAND_HEADER.size <= len(payload) <= byte_limit):
            raise ValueError('按需批次时间范围或字节长度非法')
        magic, start, count, eof, retained, scope, full_checks = DEMAND_HEADER.unpack_from(payload)
        if (magic != DEMAND_MAGIC or start != expected_start or not 0 <= count <= row_limit
                or scope != {'none': 0, 'selected': 1, 'source': 2}[time_scope] or eof not in (0, 1)
                or not 0 <= full_checks <= count
                or retained > count or start+count >= 2**64 or count == 0 and not eof):
            raise ValueError('按需批次头与本次许可不符')
        records, timestamps, previous, position = [], [], start-1, DEMAND_HEADER.size
        if time_scope == 'source':
            position += 8*count
            if position > len(payload):
                raise ValueError('批次时间数组被截断')
            timestamps = list(struct.unpack_from('>'+str(count)+'d', payload, DEMAND_HEADER.size))
            if any(not isfinite(value) for value in timestamps):
                raise ValueError('原报文timestamp需要有限float秒')
        for _ in range(retained):
            if position+LENGTH.size > len(payload):
                raise ValueError('批次记录长度被截断')
            size = LENGTH.unpack_from(payload, position)[0]
            position += LENGTH.size
            if not 0 < size <= MAX_WIRE_BYTES or position+size > len(payload):
                raise ValueError('批次记录超限或被截断')
            record = (_decoded_from_packet if time_scope == 'source' else required_from_packet)(
                payload[position:position+size])
            position += size
            if not previous < record.sequence < start+count:
                raise ValueError('批次记录原序号乱序、重复或越界')
            if frame_ids is not None and record.frame.arbitration_id not in frame_ids:
                raise ValueError('批次返回未声明保留的报文ID')
            if time_scope == 'none':
                if record.frame.timestamp is not None:
                    raise ValueError('未采时间批次不能携带伪造或额外时间')
            elif time_scope == 'selected':
                if record.frame.timestamp is None:
                    raise ValueError('所选时间批次缺少目标时间')
                timestamps.append(record.frame.timestamp)
            elif record.frame.timestamp.hex() != timestamps[record.sequence-start].hex():
                raise ValueError('批次原时间与记录时间不一致')
            previous = record.sequence
            records.append(record)
        if position != len(payload) or frame_ids is None and retained != count:
            raise ValueError('批次存在尾随字节或全量记录缺项')
        return LegacyDecodedBatch(start, tuple(timestamps), tuple(records), count, time_scope,
                                  full_checks, 2), bool(eof)
    finally:
        # 已结束异常frame不继续持有整批JSON、模型或传输包。
        payload = records = record = timestamps = None
