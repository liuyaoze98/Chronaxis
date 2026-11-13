"""普通 CAN 有界数据块；只恢复固定记录，绝不加载任意 Python 对象。

CND1 头为 4 字节版本和网络序 uint32 主体长度。主体先存字符串表，再按
固定字段依次存块、来源和原帧。字符串只在本块共享；原数值保留位型和整数精度。
"""
from decimal import Decimal
from pathlib import Path
import struct

LIMIT = 524288
ROWS = 64
_HEADER = struct.Struct('!4sI')
_U32 = struct.Struct('!I')
_I64 = struct.Struct('!q')
_F64 = struct.Struct('!d')
_STATUSES = ('decoded', 'unknown', 'unselected', 'non_data')
_FLAGS = ('is_extended_id', 'is_remote_frame', 'is_error_frame',
          'is_fd', 'bitrate_switch', 'error_state_indicator')


class CANBlockError(ValueError):
    """固定 CAN 编码结构不完整或不合法。"""


class _Writer:
    """单块临时编码空间；所有增长先核原有包长上限。"""

    def __init__(self):
        """建立单块临时空间。

        参数: 无。
        返回: 新编码器。
        异常: 内存分配错误。
        """
        self.body = bytearray()
        self.strings = []
        self.indices = {}
        self.string_bytes = 4

    def add(self, data):
        """追加已编码字节并先核包长。

        参数: data为bytes类片段。
        返回: None。
        异常: 超过512KiB时CANBlockError。
        """
        if len(self.body) + self.string_bytes + len(data) + 8 > LIMIT:
            raise CANBlockError('CAN数据块超过512KiB')
        self.body.extend(data)

    def byte(self, value):
        """写一个uint8。

        参数: value为0到255整数。
        返回: None。
        异常: 范围或包长错误。
        """
        self.add(bytes((value,)))

    def uint(self, value):
        """写网络序uint32。

        参数: value为0到2**32-1整数。
        返回: None。
        异常: 范围或包长错误。
        """
        self.add(_U32.pack(value))

    def text(self, value):
        """写本块字符串表索引。

        参数: value为原生str。
        返回: None，首次出现时登记UTF8/surrogatepass内容。
        异常: 类型或包长错误。
        """
        if type(value) is not str:
            raise CANBlockError('CAN文本字段必须是str')
        index = self.indices.get(value)
        if index is None:
            encoded = value.encode('utf-8', 'surrogatepass')
            if len(self.body) + self.string_bytes + len(encoded) + 16 > LIMIT:
                raise CANBlockError('CAN字符串表超过512KiB')
            index = len(self.strings)
            self.indices[value] = index
            self.strings.append(encoded)
            self.string_bytes += 4 + len(encoded)
        self.uint(index)

    def scalar(self, value):
        # bool 单独编码；大整数不经过 float，也不把非有限原值替换成 None。
        """无损写有限种类原值。

        参数: value为None/bool/int/float，原float允许NaN/Inf。
        返回: None。
        异常: 未支持类型或包长错误。
        """
        kind = type(value)
        if value is None:
            self.byte(0)
        elif kind is bool:
            self.byte(2 if value else 1)
        elif kind is int:
            self.byte(3 if value >= 0 else 4)
            width = max(1, (abs(value).bit_length() + 7) // 8)
            if width > LIMIT:
                raise CANBlockError('CAN整数超过块长')
            self.uint(width)
            self.add(abs(value).to_bytes(width, 'big'))
        elif kind is float:
            self.byte(5)
            self.add(_F64.pack(value))
        else:
            raise CANBlockError('CAN原值只接受int/float/bool/None')

    def optional_text(self, value):
        """写可空文本。

        参数: value为str或None。
        返回: None。
        异常: 类型或包长错误。
        """
        self.byte(value is not None)
        if value is not None:
            self.text(value)

    def pairs(self, values):
        """写字段值对。

        参数: values为已经校验的名称和值对序列。
        返回: None。
        异常: 字段类型或包长错误。
        """
        self.uint(len(values))
        for name, value in values:
            self.text(name)
            self.scalar(value)

    def decimal(self, value):
        """写精确比较时间事实。

        参数: value为有限Decimal或None。
        返回: None，不按指数展开文本。
        异常: 类型、非有限值或包长错误。
        """
        self.byte(value is not None)
        if value is not None:
            if type(value) is not Decimal or not value.is_finite():
                raise CANBlockError('CAN精确时间事实需要有限Decimal')
            sign, digits, exponent = value.as_tuple()
            self.byte(sign)
            self.scalar(exponent)
            self.uint(len(digits))
            self.add(bytes(digits))

    def finish(self, magic=b'CND1'):
        """拼接单一头、字符串表和主体。

        参数: magic为内部写定的CND1或CMT1版本。
        返回: 对应固定格式的完整bytes。
        异常: 超过512KiB时CANBlockError。
        """
        table = bytearray(_U32.pack(len(self.strings)))
        for value in self.strings:
            table.extend(_U32.pack(len(value)))
            table.extend(value)
        size = len(table) + len(self.body)
        if size + 8 > LIMIT:
            raise CANBlockError('CAN数据块超过512KiB')
        table.extend(self.body)
        if magic not in (b'CND1',b'CMT1'):
            raise CANBlockError('内部CAN格式未知')
        return _HEADER.pack(magic, size) + table


class _Reader:
    """只按固定顺序取字段；长度检查在切片或容器分配之前执行。"""

    def __init__(self, packet, expected=b'CND1', *, on_expand=None):
        """核固定头并读取本块字符串表。

        参数: packet为完整bytes，expected为本固定入口写定的版本；on_expand在模型新增分配前核预约。
        返回: 新读取器，拥有游标及局部展开计数。
        异常: 版本、长度、编码或展开上限错误。
        """
        if type(packet) is not bytes or not 12 <= len(packet) <= LIMIT:
            raise CANBlockError('CAN数据块长度非法')
        magic, size = _HEADER.unpack_from(packet)
        if expected not in (b'CND1',b'CMT1') or magic != expected or size != len(packet) - 8:
            raise CANBlockError('CAN数据块版本或声明长度不符')
        self.data = memoryview(packet)
        # 数据块仍用原6MiB模型部分。READY固定图最多4096字段、8195文本、
        # 每字段3个整数；4*包长 + 128*8195 + (1024+3*64)*4096 < 8MiB。
        # READY的原生图和冻结图并存另由父on_expand在分配前预约，8MiB不是其总峰值。
        self.expansion_limit = (8 if expected==b'CMT1' else 6)*1048576
        self.on_expand = on_expand
        self.expansion = 0
        self.position = 8
        self.strings = []
        value = None
        try:
            count = self.uint()
            if count > self.remaining // 4 or expected==b'CMT1' and count>8195:
                raise CANBlockError('CAN字符串表计数超出剩余包')
            self.charge(count * 128)
            for _ in range(count):
                size = self.uint()
                self.charge(size * 4)
                try:
                    value = bytes(self.take(size)).decode('utf-8', 'surrogatepass')
                except UnicodeDecodeError as error:
                    raise CANBlockError('CAN字符串不是有效内部UTF8') from error
                self.strings.append(value)
        except BaseException:
            self.close()
            value = packet = None
            raise

    def close(self):
        """清除仅属解码器的视图与字符串表引用。

        参数: 无。返回: None；返回模型继续持有其实际使用的不可变文本。
        异常: 无，重复调用无副作用。
        """
        if self.data is not None:
            self.data.release()
            self.data = None
        self.strings.clear()
        self.on_expand = None

    def charge(self, amount):
        """累计本块模型展开上界。

        参数: amount为本次新增保守字节数。
        返回: None，不改变ResourceBudget账本。
        异常: 超过本固定图边界时CANBlockError；父预约不足或取消原样传播。
        """
        candidate = self.expansion + amount
        if candidate > self.expansion_limit:
            raise CANBlockError('CAN解码展开超过固定图上界')
        if self.on_expand is not None:
            self.on_expand(candidate)
        self.expansion = candidate

    @property
    def remaining(self):
        """取得未消费字节数。

        参数: 无。
        返回: 非负int。
        异常: 无。
        """
        return len(self.data) - self.position

    def take(self, size):
        """取得有界字节视图并移动游标。

        参数: size为非负字节数。
        返回: memoryview，不复制包主体。
        异常: 长度越界或截断时CANBlockError。
        """
        if size < 0 or size > self.remaining:
            raise CANBlockError('CAN数据块截断')
        offset = self.position
        self.position += size
        return self.data[offset:self.position]

    def byte(self):
        """读一个uint8。

        参数: 无。
        返回: int。
        异常: 截断时CANBlockError。
        """
        position = self.position
        if position >= len(self.data):
            raise CANBlockError('CAN数据块截断')
        value = self.data[position]
        self.position = position + 1
        return value

    def uint(self):
        """读网络序uint32。

        参数: 无。
        返回: int。
        异常: 截断时CANBlockError。
        """
        position = self.position
        if position + 4 > len(self.data):
            raise CANBlockError('CAN数据块截断')
        value = _U32.unpack_from(self.data, position)[0]
        self.position = position + 4
        return value

    def boolean(self):
        """读严格布尔位。

        参数: 无。
        返回: bool。
        异常: 非0/1或截断时CANBlockError。
        """
        value = self.byte()
        if value not in (0, 1):
            raise CANBlockError('CAN布尔字段非法')
        return bool(value)

    def text(self):
        """取本块已有字符串。

        参数: 无。
        返回: str，不复制共享文本。
        异常: 索引越界或截断时CANBlockError。
        """
        index = self.uint()
        if index >= len(self.strings):
            raise CANBlockError('CAN字符串索引越界')
        return self.strings[index]

    def scalar(self):
        """读固定种类数值。

        参数: 无。
        返回: None/bool/int/float，保留原位型。
        异常: 未知标记、非最短整数、展开或截断错误。
        """
        tag = self.byte()
        if tag == 0:
            return None
        if tag in (1, 2):
            return tag == 2
        if tag in (3, 4):
            width = self.uint()
            if not 1 <= width <= self.remaining:
                raise CANBlockError('CAN整数长度非法')
            self.charge(width * 2 + 64)
            raw = self.take(width)
            value = None
            try:
                if width > 1 and raw[0] == 0:
                    raise CANBlockError('CAN整数不能使用非最短表示')
                value = int.from_bytes(raw, 'big')
                if tag == 4 and value == 0:
                    raise CANBlockError('CAN整数不能使用负零表示')
                return value if tag == 3 else -value
            finally:
                # 内层格式错误的异常栈不能通过切片视图继续持有整包。
                raw.release()
                raw = value = None
        if tag == 5:
            return _F64.unpack(self.take(8))[0]
        raise CANBlockError('CAN原值标记未知')

    def nonnegative(self):
        """读原生非负序号。

        参数: 无。
        返回: int。
        异常: 负数、bool、其他类型或截断错误。
        """
        value = self.scalar()
        if type(value) is not int or value < 0:
            raise CANBlockError('CAN序号需要非负整数')
        return value

    def optional_text(self):
        """读可空文本。

        参数: 无。
        返回: str或None。
        异常: 存在位、索引或截断错误。
        """
        return self.text() if self.boolean() else None

    def pairs(self, *, maximum=4096):
        """读有限字段对。

        参数: maximum为条数上限，默认4096。
        返回: tuple名称值对。
        异常: 计数、展开、标记或截断错误。
        """
        count = self.uint()
        if count > maximum or count > self.remaining // 5:
            raise CANBlockError('CAN字段对计数超限')
        self.charge(count * 256)
        return tuple((self.text(), self.scalar()) for _ in range(count))

    def decimal(self):
        """读精确比较时间事实。

        参数: 无。
        返回: 有限Decimal或None。
        异常: 符号、数字、指数、展开或截断错误。
        """
        if not self.boolean():
            return None
        sign = self.byte()
        exponent = self.scalar()
        count = self.uint()
        if sign not in (0, 1) or type(exponent) is not int or not count:
            raise CANBlockError('CAN Decimal结构非法')
        self.charge(count * 16 + 256)
        digits = self.take(count)
        value = None
        try:
            if any(value > 9 for value in digits):
                raise CANBlockError('CAN Decimal数字非法')
            try:
                value = Decimal((sign, tuple(digits), exponent))
            except (ValueError, OverflowError) as error:
                raise CANBlockError('CAN Decimal指数非法') from error
            if not value.is_finite():
                raise CANBlockError('CAN Decimal必须有限')
            return value
        finally:
            digits.release()
            digits = value = exponent = None


def _write_frame(writer, frame):
    """写原帧固定公开字段。

    参数: writer块编码器，frame为已知原帧。
    返回: None。
    异常: 字段或包长错误。
    """
    writer.add(_F64.pack(frame.timestamp))
    writer.uint(frame.arbitration_id)
    writer.byte(sum(int(getattr(frame, name)) << index for index, name in enumerate(_FLAGS)))
    writer.byte(2 if frame.is_rx is None else int(frame.is_rx))
    writer.byte(type(frame.channel) is str)
    if type(frame.channel) is str:
        writer.text(frame.channel)
    else:
        writer.scalar(frame.channel)
    writer.scalar(frame.dlc)
    writer.uint(len(frame.data))
    writer.add(frame.data)


def _read_frame(reader, timed):
    """恢复已知原帧类型。

    参数: reader块读取器，timed指是否为有时间RawCANRecord。
    返回: LegacyRawFrame或已知can.Message。
    异常: 固定字段或原模型校验错误，无时间模式不增加时间有限性检查。
    """
    timestamp = _F64.unpack(reader.take(8))[0]
    frame_id, flags, direction = reader.uint(), reader.byte(), reader.byte()
    if flags & ~63 or direction not in (0, 1, 2):
        raise CANBlockError('CAN原帧标志非法')
    channel = reader.text() if reader.boolean() else reader.scalar()
    if channel is not None and type(channel) not in (int, str):
        raise CANBlockError('CAN通道字段非法')
    dlc = reader.scalar()
    size = reader.uint()
    if size > 64:
        raise CANBlockError('CAN载荷超过64字节')
    arguments = dict(timestamp=timestamp, arbitration_id=frame_id, channel=channel,
                     dlc=dlc, data=bytes(reader.take(size)),
                     is_rx=None if direction == 2 else bool(direction),
                     **{name: bool(flags & (1 << index)) for index, name in enumerate(_FLAGS)})
    if timed:
        from ..legacy.records import LegacyRawFrame
        return LegacyRawFrame(**arguments)
    # 没有时间消费者的 BLF 不额外执行有限时间检查；只能恢复这个已知帧类型。
    from ..can_dependencies import import_can_dependency
    return import_can_dependency('can').Message(**arguments, check=False)


def encode_block(number, records, eof, facts):
    """编码一个已校验CAN块。

    参数: number非负块号，records最多64条，eof真实结束，facts六项文件事实。
    返回: CND1 bytes。
    异常: 数量、字段或原512KiB包长错误。
    """
    from ..sources.raw_can import RawCANRecord
    if type(number) is not int or number < 0 or type(eof) is not bool or len(records) > ROWS:
        raise CANBlockError('CAN块号、EOF或条数非法')
    writer = _Writer()
    writer.scalar(number)
    writer.byte(eof)
    writer.uint(len(records))
    for record in records:
        writer.text(record.source)
        writer.scalar(record.input_index)
        writer.scalar(record.sequence)
        writer.byte(_STATUSES.index(record.status))
        raw = record.raw
        timed = type(raw) is RawCANRecord
        writer.byte(timed)
        _write_frame(writer, raw.frame)
        writer.text(str(raw.path))
        writer.scalar(raw.sequence)
        if timed:
            writer.add(_I64.pack(raw.time_ns))
            writer.scalar(raw.line_number)
            writer.optional_text(raw.raw_time)
            writer.text(raw.parser_version)
            writer.scalar(raw.dlc_code)
            writer.byte(raw.time_quantized)
            writer.scalar(raw.source_time_ns)
        writer.pairs(record.values)
        writer.pairs(record.frame_values)
        writer.pairs(record.frame_layout)
    expected = {'count', 'first_ns', 'last_ns', 'decode_calls', 'first_order_time', 'last_order_time'}
    if set(facts) != expected:
        raise CANBlockError('CAN文件事实字段不符')
    for name in ('count', 'first_ns', 'last_ns', 'decode_calls'):
        writer.scalar(facts[name])
    for name in ('first_order_time', 'last_order_time'):
        writer.decimal(facts[name])
    return writer.finish()


def decode_block(packet):
    """恢复一个固定CAN块；失败只保留原诊断，不保留已经解码的整批记录。

    参数: packet为完整CND1 bytes。
    返回: 块号、records列表、EOF和facts字典；成功时记录所有权交给调用方。
    异常: 结构、模型、展开、截断或尾随字节错误；保留原异常与原因链。
    """
    from ..sources.raw_can import RawCANRecord
    from ..sources.blf import _UntimedBLFRecord
    from ..sources.text_can_decode import DecodedCANRecord
    from ..sources.can_spec import can_field_from_key
    reader = None
    records = []
    frame = raw = facts = source = path = None
    known_fields = values = frame_values = frame_layout = pair = key = None
    try:
        reader = _Reader(packet)
        number, eof, count = reader.nonnegative(), reader.boolean(), reader.uint()
        if count > ROWS:
            raise CANBlockError('CAN记录数超过64')
        reader.charge(count * 2048)
        if count:
            # 集合只引用本块已有字符串；基础空间及扩容峰值在实际分配前计入6MiB。
            reader.charge(512)
            known_fields = set()
        for _ in range(count):
            source, input_index, sequence = reader.text(), reader.nonnegative(), reader.nonnegative()
            status = reader.byte()
            if status >= len(_STATUSES):
                raise CANBlockError('CAN状态标记未知')
            timed = reader.boolean()
            frame = _read_frame(reader, timed)
            path, raw_sequence = Path(reader.text()), reader.nonnegative()
            if timed:
                raw = RawCANRecord(frame, _I64.unpack(reader.take(8))[0], path,
                    reader.scalar(), raw_sequence, reader.optional_text(), reader.text(),
                    reader.scalar(), reader.boolean(), reader.scalar())
            else:
                raw = _UntimedBLFRecord(frame, path, raw_sequence)
            values, frame_values, frame_layout = reader.pairs(), reader.pairs(), reader.pairs()
            # 只有values中的规范CAN键需要完整解析；原物理字段名称不套用这条规则。
            # 私有坏包先核实际出现的键，不承诺与原pickle恢复有相同的首个错误。
            for pair in values:
                key = pair[0]
                if key not in known_fields:
                    can_field_from_key(key)
                    reader.charge(192)
                    known_fields.add(key)
            records.append(DecodedCANRecord._from_bound_values(source, input_index, sequence, raw,
                values, _STATUSES[status], frame_values, frame_layout, known_fields))
        facts = {name: reader.scalar() for name in ('count', 'first_ns', 'last_ns', 'decode_calls')}
        if any(type(facts[name]) is not int or facts[name] < 0 for name in ('count', 'decode_calls')):
            raise CANBlockError('CAN文件计数非法')
        if any(value is not None and (type(value) is not int or not -(2**63) <= value < 2**63)
               for value in (facts['first_ns'], facts['last_ns'])):
            raise CANBlockError('CAN文件纳秒事实非法')
        for name in ('first_order_time', 'last_order_time'):
            facts[name] = reader.decimal()
        if reader.remaining:
            raise CANBlockError('CAN数据块含未消费字节')
        return number, records, eof, facts
    except BaseException:
        # 当前模型的构造诊断可保留该条记录；已经完成但尚未交付的其他记录不属于诊断。
        records.clear()
        raise
    finally:
        if known_fields is not None:
            known_fields.clear()
        if reader is not None:
            reader.close()
        # 成功的返回值已经持有所需模型；这里只撤销当前调用的引用，不修改交付列表。
        packet = records = frame = raw = facts = source = path = None
        known_fields = values = frame_values = frame_layout = pair = key = None


_METADATA_KEYS = {'profile','dbc_path','dbc_sha256','fields','decode_choices','allow_truncated',
    'selected_length_check','decode_scope','cantools_version','record_check_scope','time_order_check_scope'}


def _metadata(value):
    """核当前CAN读取器字段事实。

    参数: value为固定元数据映射。
    返回: 原生dict。
    异常: 缺项、未知字段或类型不符。
    """
    item=hint=None
    try:
        from ..legacy.records import field_from_dict
        # 固定字段已经单独检查；只读校验不再复制整份元数据容器。
        if type(value) is not dict or set(value) != _METADATA_KEYS:
            raise CANBlockError('CAN元数据根字段不符')
        if (value['profile'] != 'can-text-v1' or value['decode_choices'] is not False
                or value['allow_truncated'] is not True or value['decode_scope'] != 'requested'
                or value['selected_length_check'] not in ('legacy','partial','exact')
                or value['record_check_scope'] not in ('source','selected_ids')
                or value['time_order_check_scope'] not in ('source','selected_ids','none')
                or type(value['fields']) not in (list,tuple) or len(value['fields']) > 4096):
            raise CANBlockError('CAN元数据政策或字段数量非法')
        for name in ('dbc_path','cantools_version'):
            if type(value[name]) is not str:
                raise CANBlockError('CAN元数据文本非法')
        digest = value['dbc_sha256']
        if digest is not None and (type(digest) is not str or len(digest)!=64
                                  or any(c not in '0123456789abcdef' for c in digest)):
            raise CANBlockError('CAN元数据摘要非法')
        for item in value['fields']:
            allowed = {'locator','unit','dbc_frames','frame_format_compatibility','cycle_ns'}
            if type(item) is not dict or not {'locator','unit'} <= set(item) or not set(item)<=allowed:
                raise CANBlockError('CAN字段事实结构非法')
            field_from_dict(item['locator'])
            if item['unit'] is not None and type(item['unit']) is not str:
                raise CANBlockError('CAN单位事实非法')
            if 'cycle_ns' in item and (type(item['cycle_ns']) is not int or not 0<item['cycle_ns']<2**63):
                raise CANBlockError('CAN周期事实非法')
            if 'dbc_frames' in item:
                if type(item['dbc_frames']) not in (list,tuple) or any(type(pair) not in (list,tuple) or len(pair)!=2
                        or any(type(flag) is not bool for flag in pair) for pair in item['dbc_frames']):
                    raise CANBlockError('CAN DBC帧型事实非法')
            if 'frame_format_compatibility' in item:
                hint=item['frame_format_compatibility']
                if (type(hint) is not dict or set(hint)!={'code','dbc_is_fd','requested_is_fd'}
                        or hint['code']!='dbc_fd_classic_selector' or hint['dbc_is_fd'] is not True
                        or hint['requested_is_fd'] is not False):
                    raise CANBlockError('CAN帧型兼容事实非法')
        return value
    finally:
        value=item=hint=None


def encode_metadata(value):
    """编码READY事实，并复用单块字符串表避免宽字段的重复JSON键膨胀。

    参数: value为当前固定元数据。
    返回: CMT1 bytes，仍受原512KiB上限。
    异常: 字段、类型或包长错误。
    """
    value=_metadata(value)
    writer=_Writer()
    writer.text(value['dbc_path'])
    writer.optional_text(value['dbc_sha256'])
    writer.text(value['cantools_version'])
    writer.byte(('legacy','partial','exact').index(value['selected_length_check']))
    writer.byte(('source','selected_ids').index(value['record_check_scope']))
    writer.byte(('source','selected_ids','none').index(value['time_order_check_scope']))
    writer.uint(len(value['fields']))
    for item in value['fields']:
        locator=item['locator']
        writer.scalar(locator['channel'])
        writer.text(locator['signal'])
        writer.scalar(locator['frame_id'])
        for key in ('is_extended','is_fd'):
            writer.byte(2 if locator.get(key) is None else int(locator[key]))
        writer.optional_text(item['unit'])
        flags=sum(bit for name,bit in (('dbc_frames',1),('frame_format_compatibility',2),('cycle_ns',4)) if name in item)
        writer.byte(flags)
        if flags&1:
            frames=item['dbc_frames']
            if len(frames)>4:
                raise CANBlockError('DBC帧型组合超过四种')
            writer.byte(len(frames))
            for extended,fd in frames:
                writer.byte(int(extended)|(int(fd)<<1))
        if flags&4:
            writer.scalar(item['cycle_ns'])
    return writer.finish(b'CMT1')


def decode_metadata(packet, *, on_expand=None):
    """恢复固定READY事实；只按明确字段解释CMT1，不支持旧pickle。

    参数: packet为完整CMT1 bytes；on_expand在新增固定模型分配前核父端实际额度。
    返回: 固定元数据dict，随后由既有模型冻结。
    异常: 版本、字段、包长、索引、展开或截断错误。
    """
    reader=None
    value=fields=item=locator=frames=None
    try:
        reader=_Reader(packet,b'CMT1',on_expand=on_expand)
        value=dict(profile='can-text-v1',dbc_path=reader.text(),dbc_sha256=reader.optional_text(),
            cantools_version=reader.text(),decode_choices=False,allow_truncated=True,decode_scope='requested')
        for name,choices in (
                ('selected_length_check',('legacy','partial','exact')),
                ('record_check_scope',('source','selected_ids')),
                ('time_order_check_scope',('source','selected_ids','none'))):
            index=reader.byte()
            if index>=len(choices):
                raise CANBlockError('CAN元数据策略索引非法')
            value[name]=choices[index]
        count=reader.uint()
        if count>4096 or count>reader.remaining//10:
            raise CANBlockError('CAN元数据字段数量非法')
        reader.charge(count*1024)
        fields=[]
        for _ in range(count):
            locator=dict(channel=reader.nonnegative(),signal=reader.text(),frame_id=reader.nonnegative())
            for key in ('is_extended','is_fd'):
                flag=reader.byte()
                if flag not in (0,1,2):
                    raise CANBlockError('CAN定位帧型标志非法')
                if flag!=2:
                    locator[key]=bool(flag)
            item=dict(locator=locator,unit=reader.optional_text())
            flags=reader.byte()
            if flags&~7:
                raise CANBlockError('CAN字段事实标志未知')
            if flags&1:
                combinations=reader.byte()
                if combinations>4:
                    raise CANBlockError('DBC帧型组合超过四种')
                frames=[]
                for _ in range(combinations):
                    pair=reader.byte()
                    if pair>3:
                        raise CANBlockError('DBC帧型组合非法')
                    frames.append([bool(pair&1),bool(pair&2)])
                item['dbc_frames']=frames
            if flags&2:
                item['frame_format_compatibility']=dict(code='dbc_fd_classic_selector',dbc_is_fd=True,requested_is_fd=False)
            if flags&4:
                item['cycle_ns']=reader.nonnegative()
            fields.append(item)
        value['fields']=fields
        if reader.remaining:
            raise CANBlockError('CAN元数据含未消费字节')
        return _metadata(value)
    finally:
        if reader is not None:
            reader.close()
        packet=value=fields=item=locator=frames=None
