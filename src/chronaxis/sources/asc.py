"""逐行读取标准ASC及显式Sclicer布局，返回带物理行号的真实CAN记录。

支持标准经典CAN及统计尾、远程/错误帧和CAN FD数据行；header的absolute是段内累计时间，
relative是相邻事件时间差。relative输出以首段为零，epoch输出使用显式时区的日期。
日期/进制/通道/载荷长度严格检查；时间顺序默认全检，实际计算可限定所需帧。
未知行拒绝，不从头回退或修复输入文件。
只拥有一个有界文本行和当前记录；向调用方交出的记录若长期保留，须由调用方计费。
模块导入及ASCSpec构造无文件操作；ASCRead显式创建时预约预算并只读打开文件。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
import codecs
from pathlib import Path
import re

from ..legacy.records import LegacyRawFrame
from ..results.budget import ResourceBudget, _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..timebase.conversion import checked_add_ns, convert_time, require_int64_ns
from .raw_can import CANTextError, RawCANRecord

# 16Ki字符足以容纳64字节帧及标准附加字段；过长行显式失败而不无限读取。
MAX_ASC_LINE_CHARS = 16384
DLC_LENGTHS = (0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 32, 48, 64)
MONTHS = dict(zip(('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep',
                   'Oct', 'Nov', 'Dec'), range(1, 13)))


@dataclass(frozen=True)
class ASCSpec:
    """固定一次ASC读取的格式、编码、时间参考；不猜测本地时区。"""

    path: Path  # 单文件，连续多文件的时序合并由外层负责。
    parser_version: str = 'vector-asc-v1'  # 标准布局含统计尾；statistics保留显式入口，sclicer须显式选择。
    encoding: str = 'utf-8-sig'  # 严格解码，兼容UTF-8 BOM，不自动换编码。
    time_reference: str = 'relative'  # relative为首段原点，epoch为显式日期/时区。
    timezone_offset_minutes: int | None = None  # epoch必填，避免依赖宿主时区。
    offset_ns: int = 0  # 一次明确的int64平移，不更改原始时间文本。

    def __post_init__(self):
        """校验静态契约。参数: 无。返回: None。异常: 类型或不支持的选项。
        """
        # 路径只校验类型；是否存在、是否可读在ASCRead创建时验证。
        if not isinstance(self.path, Path) or type(self.encoding) is not str or not self.encoding:
            raise TypeError('ASC需要Path和明确编码')
        # 单行字节定位只接受换行由单字节LF表示的编码；UTF-16/32另需专门读取协议。
        if codecs.lookup(self.encoding).name not in ('utf-8', 'utf-8-sig', 'ascii', 'gbk', 'cp1252', 'iso8859-1'):
            raise ValueError('ASC当前只支持UTF-8/ASCII/GBK/CP1252/Latin-1逐行编码')
        if (self.parser_version not in ('vector-asc-v1', 'vector-asc-statistics-v1', 'sclicer-asc-v1')
                or self.time_reference not in ('relative', 'epoch')):
            raise ValueError('不支持的ASC解析版本或时间参考')
        zone = self.timezone_offset_minutes
        if zone is not None and (type(zone) is not int or not -1439 <= zone <= 1439):
            raise ValueError('ASC时区偏移需-1439到1439整数分钟')
        if self.time_reference == 'epoch' and zone is None:
            raise ValueError('ASC日历时间需要显式时区偏移')
        require_int64_ns(self.offset_ns)


def _date(text):
    """解析ASC英文日期，不调用宿主时区。参数: text为去掉星期后的日期。

    返回: 无时区datetime。异常: ValueError为月份或日期格式不支持。
    """
    # 月份用固定表，避免Windows语言环境影响；12/24小时及毫秒/微秒分别接受。
    parts = text.split()
    if len(parts) not in (4, 5) or parts[0] not in MONTHS:
        raise ValueError('ASC日期需要英文月份和明确年月日')
    parts[0] = str(MONTHS[parts[0]])
    for pattern in ('%m %d %I:%M:%S.%f %p %Y', '%m %d %I:%M:%S %p %Y',
                    '%m %d %H:%M:%S.%f %Y', '%m %d %H:%M:%S %Y'):
        try:
            return datetime.strptime(' '.join(parts), pattern)
        except ValueError:
            # 这里只尝试已声明日期布局，绝不重新打开数据或回退报文格式。
            continue
    raise ValueError('ASC日期格式或取值无效')


def _unsigned(text, base, maximum, label):
    """严格解析无符号字段。参数: text原文、base进制、maximum上限、label诊断名。

    返回: int。异常: ValueError为符号、非法字符、空值或越界；拒绝下划线和隐式前缀。
    """
    # int本身会接受正号/下划线；协议数值先限定字符，避免宽松解析隐藏坏行。
    alphabet = r'[0-9a-fA-F]+' if base == 16 else r'[0-9]+'
    if not re.fullmatch(alphabet, text):
        raise ValueError(label + '字符或进制错误')
    value = int(text, base)
    if value > maximum:
        raise ValueError(label + '越界')
    return value


def _status_event(tokens: list[str]) -> bool:
    """识别已知CAN控制器状态事件，验证格式后告知调用方不产生数据帧。

    参数: tokens为去掉时间的有界字段列表；时间累加必须由调用方预先完成。
    返回: bool；普通帧为False，完整的chip status事件为True，无文件或状态副作用。
    异常: ValueError为CAN事件的未知状态、通道、计数或残缺布局；不跳过未知事件。
    """
    # 仅接受明确的状态事件，避免把损坏帧和其他协议行当作可忽略的元数据。
    if not tokens or tokens[0] != 'CAN':
        return False
    match = re.fullmatch(
        r'CAN ([0-9]+) Status:\s*chip status '
        r'(?:error active|error passive|warning level|busoff|bus off)'
        r'(?: - TxErr: ([0-9]+) RxErr: ([0-9]+))?', ' '.join(tokens), re.IGNORECASE)
    if match is None:
        raise ValueError('不支持或损坏的ASC总线状态事件，需要chip status及完整的可选TxErr/RxErr计数')
    channel = _unsigned(match[1], 10, 65536, 'ASC状态事件通道')
    if channel == 0:
        raise ValueError('ASC状态事件通道从1开始')
    # 诊断计数仅验证为有界非负整数，不把状态行转换成信号样本或保存额外结果。
    if match[2] is not None:
        _unsigned(match[2], 10, 0xffffffffffffffff, 'ASC发送错误计数')
        _unsigned(match[3], 10, 0xffffffffffffffff, 'ASC接收错误计数')
    return True


def _fd_error_diagnostics(tokens: list[str]) -> int:
    """检查Vector CAN FD错误帧的结构，返回描述实际帧类型的扩展标志。

    参数: tokens为ErrorFrame后的错误文字、诊断字段、部分载荷和完整计时尾。
    返回: extFlags整数；不保留错误文字、部分载荷或诊断ID供正常信号解码。
    异常: ValueError为未知阶段、缺字段、无效数值、载荷数量不符或保留位非零。
    已损坏帧的DLC与已取得的DataLength可能不一致，不套用正常帧的长度关系。
    """
    # 错误描述含空格；Arb./Data.之后的位置字段结构固定，不能按描述的词数切割。
    phases = [index for index, token in enumerate(tokens) if token in ('Arb.', 'Data.')]
    if len(phases) != 1 or phases[0] < 4:
        raise ValueError('ASC CAN FD错误帧需要错误描述、flags/code/codeExt及Arb.或Data.阶段')
    phase = phases[0]
    for name, value in zip(('flags', 'code', 'codeExt'), tokens[phase - 3:phase]):
        _unsigned(value, 16, 0xffffffffffffffff, 'ASC CAN FD错误帧' + name)
    fields = tokens[phase + 1:]
    if len(fields) < 13:
        raise ValueError('ASC CAN FD错误帧诊断字段或计时尾不完整')
    position, identifier, brs, esi, dlc, length = fields[:6]
    _unsigned(position, 10, 0xffffffffffffffff, 'ASC CAN FD错误位置')
    numeric_id = identifier[:-1] if identifier[-1:].lower() == 'x' else identifier
    _unsigned(numeric_id, 16, 0xffffffff, 'ASC CAN FD诊断ID')
    if brs not in ('0', '1') or esi not in ('0', '1'):
        raise ValueError('ASC CAN FD错误帧BRS/ESI需要0或1')
    _unsigned(dlc, 16, 15, 'ASC CAN FD诊断DLC')
    size = _unsigned(length, 10, 64, 'ASC CAN FD诊断载荷长度')
    if len(fields) != 6 + size + 7:
        raise ValueError('ASC CAN FD错误帧载荷数量或七项计时尾不符')
    # 诊断字段固定为十六进制，Position、DataLength和MessageDuration使用十进制。
    for token in fields[6:6 + size]:
        _unsigned(token, 16, 255, 'ASC CAN FD诊断载荷字节')
    duration, extended, *timing = fields[6 + size:]
    _unsigned(duration, 10, 0xffffffffffffffff, 'ASC CAN FD错误帧持续时间')
    flags = _unsigned(extended, 16, 31, 'ASC CAN FD扩展错误标志')
    for token in timing:
        _unsigned(token, 16, 0xffffffffffffffff, 'ASC CAN FD错误帧CRC或位时序')
    return flags


def _error_diagnostics(tokens: list[str], *, fd: bool) -> int | None:
    """验证错误帧的已知诊断尾，不将可能受损的诊断ID或DLC当成正常帧字段。

    参数: tokens为ErrorFrame之后的字段；fd表明是否为CAN FD布局。
    返回: 完整FD诊断的extFlags，其他已知形式返回None；无副作用。
    异常: ValueError为未知/残缺诊断或无效数值。
    """
    # 裸错误帧继续可用；FD附诊断按自身完整布局核验，不套用经典ECC尾。
    if not tokens:
        return
    if fd:
        return _fd_error_diagnostics(tokens)
    text = ' '.join(tokens)
    if re.fullmatch(r'ECC:\s*[01]{8}', text):
        return
    names = ['Flags', 'CodeExt', 'Code', 'ID', 'DLC', 'Position', 'Length']
    if len(tokens) != 21 or tokens[0::3] != names or tokens[1::3] != ['='] * 7:
        raise ValueError('ASC错误帧诊断需8位ECC或完整Flags/CodeExt/Code/ID/DLC/Position/Length字段')
    # 此诊断格式明确使用0x前缀或十进制数，不跟随数据载荷的base头部。
    for name, value in zip(names, tokens[2::3]):
        hexadecimal = value.startswith(('0x', '0X'))
        _unsigned(value[2:] if hexadecimal else value, 16 if hexadecimal else 10,
                  0xffffffffffffffff, 'ASC错误帧' + name)


def _frame(tokens, base, seconds):
    """解析标准数据部分，精确检查长度。参数: tokens不含时间；base为10/16；seconds为兼容秒。

    返回: (LegacyRawFrame, DLC编码或None)。异常: ValueError为未知布局、身份或载荷错误。
    """
    # CAN FD标准顺序是CANFD 通道 方向 ID；经典CAN是通道 ID 方向 类型。
    if not tokens:
        raise ValueError('ASC行缺少帧或事件内容')
    fd = tokens[0] == 'CANFD'
    if fd:
        tokens = tokens[1:]
    channel = _unsigned(tokens[0], 10, 65536, 'ASC通道')
    if channel == 0:
        raise ValueError('ASC通道从1开始')
    fields = dict(timestamp=seconds, channel=channel - 1, is_fd=fd, is_rx=True,
                  is_extended_id=False, is_remote_frame=False, is_error_frame=False,
                  bitrate_switch=False, error_state_indicator=False, arbitration_id=0, dlc=0, data=b'')
    rest = tokens[1:]
    if fd:
        direction, rest = rest[0], rest[1:]
    elif rest and rest[0].lower() == 'errorframe':
        # 经典错误帧没有独立方向字段；后面可能是ECC或CAN-Core诊断，不能当作方向。
        direction = 'Rx'
    else:
        direction = rest[1] if len(rest) > 1 else 'Rx'
    # 错误帧没有载荷，但FD格式仍明确给出方向，必须在提前返回前保存。
    if direction not in ('Rx', 'Tx'):
        raise ValueError('ASC方向需要Rx或Tx')
    fields['is_rx'] = direction == 'Rx'
    if rest[0].lower() == 'errorframe':
        error_flags = _error_diagnostics(rest[1:], fd=fd)
        fields['is_error_frame'] = True
        if error_flags is not None:
            # CANFD通道也可能接收经典错误帧；使用扩展标志，不把部分诊断数据伪装成有效载荷。
            fields.update(is_fd=bool(error_flags & 1), bitrate_switch=bool(error_flags & 2),
                          error_state_indicator=bool(error_flags & 4))
        return LegacyRawFrame(**fields), None
    identifier = rest[0]
    extended = identifier[-1:].lower() == 'x'
    fields['is_extended_id'] = extended
    fields['arbitration_id'] = _unsigned(identifier[:-1] if extended else identifier,
                                        base, 0x1fffffff if extended else 0x7ff, 'ASC报文ID')
    if fd:
        rest = rest[1:]
        # 标准ASC可在ID后有一个符号名称；它不是载荷，也不从名称推断信号。
        if rest[0] not in ('0', '1'):
            rest = rest[1:]
        brs, esi, dlc_text, length_text, *payload = rest
        if brs not in ('0', '1') or esi not in ('0', '1'):
            raise ValueError('CAN FD BRS/ESI需要0或1')
        code = _unsigned(dlc_text, base, 15, 'CAN FD DLC编码')
        length = _unsigned(length_text, 10, 64, 'CAN FD载荷长度')
        if DLC_LENGTHS[code] != length:
            raise ValueError('CAN FD DLC编码与实际长度不一致')
        fields.update(bitrate_switch=brs == '1', error_state_indicator=esi == '1')
        # 可省略控制器计时尾；存在时必须是标准8个数值，不吞掉多余payload。
        tail = payload[length:]
        if len(tail) not in (0, 8):
            raise ValueError('CAN FD载荷或标准附加字段数量错误')
        for index, token in enumerate(tail):
            _unsigned(token, 16 if index >= 2 else 10, 0xffffffffffffffff, 'CAN FD附加字段')
        payload = payload[:length]
    else:
        if len(rest) < 3:
            raise ValueError('经典CAN行缺少ID、方向或d/r类型')
        _, _, frame_type, *tail = rest
        if frame_type not in ('d', 'r'):
            raise ValueError('经典CAN类型需要d或r')
        # 远程帧可省略DLC；None保留未知含义。兼容帧的0仅是内存占位，导出须看dlc_code。
        if frame_type == 'r' and not tail:
            fields['is_remote_frame'] = True
            return LegacyRawFrame(**fields), None
        if not tail:
            raise ValueError('经典CAN数据帧缺少DLC')
        dlc_text, *payload = tail
        code = length = _unsigned(dlc_text, base, 8, '经典CAN DLC')
        fields['is_remote_frame'] = frame_type == 'r'
        if fields['is_remote_frame']:
            length = 0
    if len(payload) != length:
        raise ValueError('ASC实际载荷与声明长度不一致')
    fields['dlc'] = code if fields['is_remote_frame'] else length
    fields['data'] = bytes(_unsigned(item, base, 255, 'ASC载荷字节') for item in payload)
    return LegacyRawFrame(**fields), code


def _repository_frame(tokens, base, seconds, version):
    """同次解析标准统计尾或显式Sclicer布局，再复用标准字段检查。

    参数: tokens为不含时间的有界字段；base为头部进制；seconds为兼容秒；version为选定版本。
    返回: (原帧快照, DLC编码)。异常: ValueError/IndexError为布局、统计身份或载荷错误。
    不探测后重新读取；同文件可含该版本规定的经典及FD行，未声明变体拒绝。
    """
    if not tokens:
        raise ValueError('ASC行缺少帧或事件内容')
    if tokens[0] == 'CANFD':
        if version != 'sclicer-asc-v1':
            return _frame(tokens, base, seconds)
        # Sclicer样例顺序固定为CANFD 通道 ID 方向 BRS ESI d 十进制DLC 十进制长度。
        _, channel, identifier, direction, brs, esi, frame_type, code_text, length, *payload = tokens
        if frame_type != 'd':
            raise ValueError('sclicer-asc-v1只接受明确的CAN FD数据行')
        code = _unsigned(code_text, 10, 15, 'Sclicer十进制DLC编码')
        if len(payload) != _unsigned(length, 10, 64, 'Sclicer载荷长度'):
            raise ValueError('Sclicer实际载荷与声明长度不一致')
        normalized = ['CANFD', channel, direction, identifier, brs, esi,
                      format(code, 'x') if base == 16 else str(code), length, *payload]
        return _frame(normalized, base, seconds)
    # 错误帧的诊断Length属于独立布局，不能当成普通报文的统计尾。
    if len(tokens) > 1 and tokens[1].lower() == 'errorframe':
        return _frame(tokens, base, seconds)
    # 统计尾必须完整且字段名/顺序正确；不能把任意多余内容当注释丢掉。
    if 'Length' not in tokens:
        return _frame(tokens, base, seconds)
    position = tokens.index('Length')
    tail = tokens[position:]
    if (len(tail) != 9 or tail[0::3] != ['Length', 'BitCount', 'ID']
            or tail[1::3] != ['=', '=', '=']):
        raise ValueError('ASC统计尾需Length = n BitCount = n ID = n')
    for item in tail[2::3]:
        _unsigned(item, 10, 0xffffffffffffffff, 'ASC统计字段')
    frame, code = _frame(tokens[:position], base, seconds)
    if int(tail[8], 10) != frame.arbitration_id:
        raise ValueError('ASC统计ID与报文ID不一致')
    return frame, code


class ASCRead:
    """拥有单个文件及固定行缓冲预算；完成、错误和取消均关闭，禁止中途重读。"""

    def __init__(self, spec, budget, *, check_cancel=None, retain_original=True, retain_source_time=True, time_selector=None, previous_exact_time=None):
        """预约后打开一次。参数: spec为ASCSpec；budget为共享账本；check_cancel为可选无参回调。

        time_selector可选接收原帧并返回bool，仅核选中帧的先后顺序；None严格核所有时间。
        所有帧仍返回原时间供必要的来源范围统计，relative增量仍逐行累加。
        previous_exact_time为上一文件最近参与检查的Decimal秒，已含偏移；只作比较状态。
        返回: 可迭代reader。异常: 类型、预算、打开失败；清理失败附asc_read_cleanup_owner。
        """
        if type(retain_original) is not bool or type(retain_source_time) is not bool:
            raise TypeError('原文/导出时间选择需要bool')
        self._retain_original=retain_original
        self._retain_source_time=retain_source_time
        if time_selector is not None and not callable(time_selector):
            raise TypeError('ASC时间选择器必须可调用')
        if previous_exact_time is not None and (type(previous_exact_time) is not Decimal
                                               or not previous_exact_time.is_finite()):
            raise TypeError('ASC前序比较时刻需要有限Decimal秒')
        self._time_selector = time_selector
        if type(spec) is not ASCSpec or not isinstance(budget, ResourceBudget):
            raise TypeError('ASCRead需要ASCSpec和ResourceBudget')
        if check_cancel is not None and not callable(check_cancel):
            raise TypeError('取消检查必须可调用')
        # 先安装关闭责任，再预约/打开；构造失败也保留恢复owner。
        self.spec, self._budget, self._check_cancel = spec, budget, check_cancel
        self._file, self._fixed_cost, self._held_cost, self._closed = None, 0, 0, False
        self.line_number = self.count = 0
        self._base = self._mode = self._date_origin = self._header_date = None
        self._block_ns, self._elapsed = 0, Decimal(0)
        self._last_exact = previous_exact_time
        self.first_exact_time = None  # 当前文件首个参与顺序检查的时刻，含无CAN帧的计时行。
        try:
            _reserve_owned_ram(self, MAX_ASC_LINE_CHARS * 64 + 8192, '_fixed_cost')
            self._file = spec.path.open('rb')
        except BaseException as error:
            _cleanup_owner(self, error, 'asc_read_cleanup_owner', 'ASC读取')
            raise

    @property
    def closed(self):
        """提供真实关闭状态。参数: 无。返回: bool。异常: 无。
        """
        return self._closed

    @property
    def last_exact_time(self):
        """返回最近参与检查的精确秒值，供连续文件接续比较。

        参数: 无。返回: Decimal或None，已含日期参考和offset；空文件保留前序值。
        异常: 无。不向逐帧记录或输出增加另一套时间，关闭后仍可取得该比较状态。
        """
        return self._last_exact

    def __iter__(self):
        """返回本次读取。参数: 无。返回: self。异常: 无；不启动第二次扫描。
        """
        return self

    def _set_date(self, value, trigger=False):
        """设置段基准。参数: value日期；trigger是否真实触发块。返回: None。异常: 时间越界。
        """
        if self._date_origin is None or trigger and not self.count:
            self._date_origin = value
        self._header_date = value
        # relative参考按段日期差保持连续；epoch用显式时区，不经过float timestamp。
        if self.spec.time_reference == 'epoch':
            zone = timezone(timedelta(minutes=self.spec.timezone_offset_minutes))
            delta = value.replace(tzinfo=zone) - datetime(1970, 1, 1, tzinfo=timezone.utc)
        else:
            delta = value - self._date_origin
        self._block_ns = require_int64_ns((delta.days * 86400 + delta.seconds) * 10**9
                                         + delta.microseconds * 1000)
        self._elapsed = Decimal(0)

    def _line(self, line):
        """解释一行。参数: line有界去空白文本。返回: RawCANRecord或元数据None。异常: 格式错误。
        """
        # 注释和已知非数据头不参与时间；未知内容拒绝，不能静默漏帧。
        if not line or line.startswith('//'):
            return None
        lower = line.lower()
        if lower.startswith('date '):
            if self.count:
                raise ValueError('数据中途不允许重新定义ASC日期')
            self._set_date(_date(line.split(None, 2)[2]))
            return None
        if lower.startswith('base '):
            if self.count or self._base is not None:
                raise ValueError('ASC进制只允许在头部定义一次')
            match = re.fullmatch(r'base\s+(hex|dec)\s+timestamps\s+(absolute|relative)', lower)
            if match is None:
                raise ValueError('ASC头需base hex/dec timestamps absolute/relative')
            self._base, self._mode = (16 if match[1] == 'hex' else 10), match[2]
            return None
        if lower in ('internal events logged', 'no internal events logged', 'end triggerblock'):
            return None
        if lower.startswith('begin triggerblock '):
            self._set_date(_date(line.split(None, 3)[3]), trigger=True)
            return None
        if self._base is None:
            raise ValueError('ASC数据前缺少明确base/timestamps头')
        if self.spec.time_reference == 'epoch' and self._header_date is None:
            raise ValueError('日历时间ASC缺少日期头')
        timestamp, *tokens = line.split()
        if not re.fullmatch(r'\d+(?:\.\d+)?', timestamp):
            raise ValueError('ASC时间需要非负十进制秒')
        # relative先精确累加再舍入；逐条先舍入会把两次0.5ns都变成0，丢掉真实的1ns。
        with localcontext() as context:
            context.prec = MAX_ASC_LINE_CHARS + 32
            value = Decimal(timestamp)
            self._elapsed = self._elapsed + value if self._mode == 'relative' else value
            exact = Decimal(self._block_ns).scaleb(-9) + self._elapsed
            converted = convert_time(exact, 's')
        ns = checked_add_ns(converted.time_ns, self.spec.offset_ns)
        # 完整读取保留先核时间再核载荷的错误顺序；选择模式元数据只推进relative时钟。
        if self._time_selector is None:
            self._check_order(exact)
        if ' '.join(tokens).lower() == 'start of measurement':
            return None
        # 状态事件也占relative时间，只在完成上面的时钟推进后跳过。
        if _status_event(tokens):
            return None
        # 标准入口同次处理可选统计尾；Sclicer FD仍须显式选择，不在失败后重读或换格式。
        frame, code = _repository_frame(tokens, self._base, ns / 10**9, self.spec.parser_version)
        # 不把无关帧当作已选时间序列的前点，仍保留其原始时间供范围统计。
        if self._time_selector is not None and self._time_selector(frame):
            self._check_order(exact)
        return RawCANRecord(frame, ns, self.spec.path, self.line_number, self.count,
                            timestamp if self._retain_original else None, self.spec.parser_version, code, converted.quantized,
                            converted.time_ns if self._retain_source_time else None)

    def _check_order(self, exact):
        """拒绝所需时间序列回退，包括舍入后相同的亚纳秒回退。

        参数: exact为已解析、尚未加offset的Decimal秒。返回: None。异常: ValueError为回退。
        只保存最近参与检查的时刻；不排序、不钳平，也不改写返回报文。
        """
        # 每个文件可能使用不同显式偏移；比较状态必须与返回坐标使用相同原点。
        shifted = exact
        if self.spec.offset_ns:
            with localcontext() as context:
                context.prec = MAX_ASC_LINE_CHARS + 32
                shifted = exact + Decimal(self.spec.offset_ns).scaleb(-9)
        if self._last_exact is not None and shifted < self._last_exact:
            raise ValueError('ASC来源时间回退')
        if self.first_exact_time is None:
            self.first_exact_time = shifted
        self._last_exact = shifted

    def __next__(self):
        """读取到下一帧或EOF。参数: 无。返回: RawCANRecord。异常: 定位格式错、I/O或取消原错。

        完成/失败后释放自有资源；已返回前缀不会重复。取消回调在每个物理行前检查。
        """
        if self._closed:
            raise StopIteration
        try:
            while True:
                if self._check_cancel is not None:
                    self._check_cancel()
                # 先按有界原字节取得一个物理行，再解码，避免文本缓冲提前解码后续坏行。
                raw = self._file.readline(MAX_ASC_LINE_CHARS * 4 + 1)
                if not raw:
                    self.close()
                    raise StopIteration
                self.line_number += 1
                if len(raw) > MAX_ASC_LINE_CHARS * 4:
                    raise CANTextError(self.spec.path, self.line_number, 'ASC行超过65536字节')
                try:
                    encoding = ('utf-8' if self.spec.encoding.lower() == 'utf-8-sig'
                                and self.line_number != 1 else self.spec.encoding)
                    line = raw.decode(encoding, errors='strict')
                except UnicodeError as error:
                    raise CANTextError(self.spec.path, self.line_number, 'ASC编码错误') from error
                if len(line) > MAX_ASC_LINE_CHARS:
                    raise CANTextError(self.spec.path, self.line_number, 'ASC行超过16384字符')
                try:
                    record = self._line(line.strip())
                except (ValueError, IndexError, OverflowError) as error:
                    raise CANTextError(self.spec.path, self.line_number, str(error)) from error
                if record is not None:
                    self.count += 1
                    return record
        except BaseException as error:
            _cleanup_owner(self, error, 'asc_read_cleanup_owner', 'ASC读取')
            raise

    def close(self):
        """关闭自有文件再归还预算，可重试。参数: 无。返回: None。异常: 关闭或预算原错。
        """
        if self._closed:
            return
        if self._file is not None:
            self._file.close()
            self._file = None
        if self._fixed_cost:
            _release_owned_ram(self, self._fixed_cost, '_fixed_cost')
        self._time_selector = None
        self._closed = True

    def __enter__(self):
        """支持显式读取上下文。参数: 无。返回: self。异常: 无。
        """
        return self

    def __exit__(self, exception_type, error, traceback):
        """保留原错并收尾。参数: exception_type/error/traceback异常信息。返回: False。异常: 无原错时的关闭失败。
        """
        if error is None:
            self.close()
        else:
            _cleanup_owner(self, error, 'asc_read_cleanup_owner', 'ASC读取')
        return False
