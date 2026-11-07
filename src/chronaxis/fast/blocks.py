"""贡献块的有界二进制编码。浮点使用binary64，时间和记录序号保持整数。

同一帧多个贡献共享时间和记录位置；CRC检查暂存意外损坏。只处理本次会话
内部数据，不加载任意对象，不保存完整CAN帧或解码字典。
"""
import math
import struct
import zlib

ROWS = 1024
LIMIT = 262144
RAM = 4 * 1048576
HEADER = struct.Struct('<4sQQI')  # 固定版本、文件号、块号、帧数。
FRAME = struct.Struct('<qQI')
ENTRY = struct.Struct('<IdB')
CRC = struct.Struct('<I')


def encode(file_index, number, records):
    """编码一个有界块。参数: 文件号/块号/贡献记录。返回: bytes。
    异常: 超大块或非法数值；不会改成低精度或丢弃尾部。
    """
    payload = bytearray(HEADER.pack(b'CFS1', file_index, number, len(records)))
    if not 0 < len(records) <= ROWS:
        raise ValueError('贡献块记录数量非法')
    for timestamp, sequence, entries in records:
        payload.extend(FRAME.pack(timestamp, sequence, len(entries)))
        for metric, value, keep in entries:
            if type(value) is not float or not math.isfinite(value) or type(keep) is not bool:
                raise ValueError('贡献须为有限float64和布尔入选标志')
            payload.extend(ENTRY.pack(metric, value, keep))
        if len(payload) + CRC.size > LIMIT:
            raise ValueError('贡献块超出字节上限')
    payload.extend(CRC.pack(zlib.crc32(payload)))
    return bytes(payload)


def decode(payload, file_index, number, metric_count):
    """核验并逐帧解码。参数: bytes/预期身份/计算项数。返回: 记录生成器。
    异常: 身份、长度、CRC、序号、计算项或数值非法；不接受重复项。
    """
    if not HEADER.size + CRC.size <= len(payload) <= LIMIT:
        raise ValueError('贡献块长度非法')
    magic, actual_file, actual_number, count = HEADER.unpack_from(payload)
    if (magic, actual_file, actual_number) != (b'CFS1', file_index, number) or not 0 < count <= ROWS:
        raise ValueError('贡献块身份或数量不符')
    end = len(payload) - CRC.size
    if zlib.crc32(memoryview(payload)[:end]) != CRC.unpack_from(payload, end)[0]:
        raise ValueError('贡献块完整性校验失败')
    offset = HEADER.size
    previous = -1
    for _ in range(count):
        if offset + FRAME.size > end:
            raise ValueError('贡献块缺少帧头')
        timestamp, sequence, size = FRAME.unpack_from(payload, offset)
        offset += FRAME.size
        if sequence <= previous or not 0 < size <= metric_count or offset + size * ENTRY.size > end:
            raise ValueError('贡献记录顺序或数量非法')
        previous = sequence
        entries = []
        seen = set()
        for _ in range(size):
            metric, value, keep = ENTRY.unpack_from(payload, offset)
            offset += ENTRY.size
            if metric >= metric_count or metric in seen or keep not in (0, 1) or not math.isfinite(value):
                raise ValueError('贡献计算项/数值非法')
            seen.add(metric)
            entries.append((metric, value, bool(keep)))
        yield timestamp, sequence, tuple(entries)
    if offset != end:
        raise ValueError('贡献块有未消费尾部')


def batches(stream):
    """按记录数及字节双上限切块。参数: 单文件贡献流。返回: 有限列表生成器。
    异常: 单帧超限；不会拆散同帧元数据或整文件载入。
    """
    block = []
    size = HEADER.size + CRC.size
    for record in stream:
        cost = FRAME.size + ENTRY.size * len(record[2])
        if cost + HEADER.size + CRC.size > LIMIT:
            raise ValueError('单帧贡献超过字节上限')
        if len(block) == ROWS or size + cost > LIMIT:
            yield block
            block = []
            size = HEADER.size + CRC.size
        block.append(record)
        size += cost
    if block:
        yield block
