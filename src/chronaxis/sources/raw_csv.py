"""直接把原始报文CSV/TXT读成带原行定位的CAN记录，不经过ASC中间文件。

CANCSVSpec使用不可变的原始报文列布局并声明时间/进制/通道起点。CANCSVRead只读打开一次，
逐记录经标准库CSV语法解析后提取所需列，严格核时间、ID、帧型、DLC和载荷。
CSV记录可以跨物理行，但整条记录字节数有界；任何错误停止并关闭，不静默跳过。
数字时间必须明确单位，日内时间默认禁止回退。clock-ms-us-v1明确把最后两段
分别解释为毫秒和微秒，例如.151.2为.151002秒；普通clock不自动采用这一规则。
模块不加载DBC/旧reader，不解码或保存整文件，已返回记录的长期保留由消费层计费。
"""

import codecs
import csv
from dataclasses import dataclass, field
from datetime import timezone, timedelta
from decimal import Decimal, localcontext
from pathlib import Path
import re

from ..legacy.records import LegacyRawFrame
from ..results.budget import ResourceBudget, _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..timebase.conversion import convert_time, checked_add_ns, parse_datetime_ns, require_int64_ns
from .raw_can import RawCANRecord, CANTextError
from .raw_csv_layout import CANCSVLayout, MAX_COLUMNS

# 同一表记录即使引号未闭合也不能无限累积；预算按整条记录的最坏文本/分列开销预约。
MAX_CSV_RECORD_BYTES = 65536
DAY_NS = 86400 * 10**9
FD_LENGTHS = (0,1,2,3,4,5,6,7,8,12,16,20,24,32,48,64)


@dataclass(frozen=True)
class CSVTimeSpec:
    """声明时间文字含义，固定偏移只施加一次，不用电脑日期或时区补值。"""

    format: str = 'numeric'  # numeric、clock、clock-ms-us-v1或iso8601，必须显式选择。
    unit: str = 's'  # numeric的s/ms/us/ns，其他格式只接受默认s，避免无效配置。
    offset_ns: int = 0  # 数值固定平移；日内时间可据明确原点映射到会话。
    timezone_offset_minutes: int | None = None  # 仅ISO无时区文本的显式补充。
    rollover_min_drop_ns: int | None = None  # 两种日内格式可选：回退至少此纳秒数才按次日解释。

    def __post_init__(self):
        """校验时间政策。参数: 无。返回: None。异常: 类型、格式、单位、时区或午夜规则非法。
        """
        # 每种写法只采用一种含义；不依文字长度猜秒/毫秒，也不默认跨午夜。
        if self.format not in ('numeric','clock','clock-ms-us-v1','iso8601') or self.unit not in ('s','ms','us','ns'):
            raise ValueError('CSV时间格式或单位不支持')
        # 日内和ISO文字已有单位，不能再额外乘一次numeric单位。
        if self.format != 'numeric' and self.unit != 's':
            raise ValueError('非数值时间不能额外声明数值单位')
        # 偏移必须能进入纳秒时间轴；只有无时区ISO文字可补显式时区。
        require_int64_ns(self.offset_ns)
        zone = self.timezone_offset_minutes
        if zone is not None and (self.format != 'iso8601' or type(zone) is not int or not -1439 <= zone <= 1439):
            raise ValueError('只有ISO时间可声明整数分钟时区偏移')
        # 午夜只适用于日内时钟；阈值为严格正值且小于一天，避免把任意乱序当作换日。
        drop = self.rollover_min_drop_ns
        if drop is not None and (self.format not in ('clock','clock-ms-us-v1') or type(drop) is not int or not 0 < drop < DAY_NS):
            raise ValueError('跨午夜阈值需日内时间格式的0到一天之间整数纳秒')


@dataclass(frozen=True)
class CANCSVSpec:
    """冻结单文件原始报文来源；布局/时间声明不打开输入或加载DBC。"""

    path: Path  # CSV/TXT只是文件名，不用于推断格式。
    layout: CANCSVLayout  # 编码、分隔符、列/中文映射及明确固定值。
    time: CSVTimeSpec = field(default_factory=CSVTimeSpec)  # 时间解释单独声明。
    id_base: int | str = 'auto'  # 0x十六进制、0b二进制、无前缀十进制；裸十六进制表可显式选16。
    length_base: int = 10  # DLC/字节数列的明确进制，原始CSV的0x08应设16。
    channel_origin: int = 0  # 原列从0或1开始，统一转换为0基通道。
    payload_style: str = 'spaced'  # spaced逐字节，或contiguous连续偶数位十六进制。

    def __post_init__(self):
        """核静态来源契约。参数: 无。返回: None。异常: 声明类型或不支持选项。
        """
        if not isinstance(self.path,Path) or type(self.layout) is not CANCSVLayout or type(self.time) is not CSVTimeSpec:
            raise TypeError('CANCSVSpec需要Path、CANCSVLayout及CSVTimeSpec')
        # 逐物理行字节定位要求LF可单字节分隔，其他编码不能假报准确行号。
        if codecs.lookup(self.layout.encoding).name not in ('utf-8','utf-8-sig','ascii','gbk','cp1252','iso8859-1'):
            raise ValueError('原始CAN CSV当前不支持该逐行编码')
        # 进制与通道起点由配置决定，bool不能借Python的整数继承关系混入。
        if not (type(self.id_base) is str and self.id_base == 'auto'
                or type(self.id_base) is int and self.id_base in (10,16)):
            raise ValueError('CSV ID进制需要auto、10或16')
        if type(self.length_base) is not int or self.length_base not in (10,16):
            raise ValueError('CSV长度进制需要10或16')
        if type(self.channel_origin) is not int or self.channel_origin not in (0,1) or self.payload_style not in ('spaced','contiguous'):
            raise ValueError('CSV通道起点或载荷布局错误')


def _uint(value, base, maximum, label):
    """解析明确进制的非负整数。参数: value文字/int；base进制；maximum上限；label定位。

    返回: int。异常: ValueError为符号/字符/隐式转换或越界，不允许bool/下划线。
    """
    # 已映射整数直接校范围；文字仅允许声明进制的数字，不隐式接受float或bool。
    if type(value) is int:
        result = value
    elif type(value) is str:
        if base == 'auto':
            prefix = value[:2].lower()
            base = 16 if prefix == '0x' else 2 if prefix == '0b' else 10
            if prefix == '0b':
                value = value[2:]
        text = value[2:] if base == 16 and value[:2].lower() == '0x' else value
        pattern = r'[0-9a-fA-F]+' if base == 16 else r'[01]+' if base == 2 else r'[0-9]+'
        if not re.fullmatch(pattern,text):
            raise ValueError(label+'字符或进制无效')
        result = int(text,base)
    else:
        raise ValueError(label+'需要文字或整数')
    # 不按ID大小改变标准/扩展标志，也不截断超出字段范围的数值。
    if not 0 <= result <= maximum:
        raise ValueError(label+'越界')
    return result


def _payload(text, style):
    """严格读取十六进制载荷，不补零/截短。参数: text原文字、style布局。返回: bytes。异常: 格式/长度错误。
    """
    # 连续格式必须完整匹配偶数字符数，不能把缺半字节的文字补成一个字节。
    if style == 'contiguous':
        if len(text) > 128 or not re.fullmatch(r'(?:[0-9a-fA-F]{2})*',text):
            raise ValueError('连续载荷需不超过64字节的偶数位十六进制')
        return bytes.fromhex(text)
    # 每字节允许一或两位hex，内部空白分隔；不吞0x前缀、控制字段或额外坏字节。
    parts = text.split()
    if len(parts) > 64 or any(not re.fullmatch(r'[0-9a-fA-F]{1,2}',value) for value in parts):
        raise ValueError('分隔载荷需不超过64个十六进制字节')
    return bytes(int(value,16) for value in parts)


class CSVClock:
    """保存一次来源的时间进度，默认拒绝回退，显式阈值才把大幅日内回退解释为次日。"""

    def __init__(self, spec):
        """只建立状态。参数: spec为CSVTimeSpec。返回: 时钟。异常: 类型错误。
        """
        if type(spec) is not CSVTimeSpec:
            raise TypeError('CSVClock需要CSVTimeSpec')
        self.spec, self._last_ns, self._last_clock_ns, self._day_offset = spec, None, None, 0

    def parse(self, value):
        """按声明转换并推进。参数: value映射后的时间文字/int。返回: (int64纳秒,量化bool)。异常: 格式/时区/回退/越界。
        """
        # 失败前只修改局部候选状态，错误时间不能污染下一次显式调用。
        if type(value) not in (str,int) or type(value) is str and len(value) > MAX_CSV_RECORD_BYTES:
            raise ValueError('CSV时间需要有限文字或整数')
        day_offset,last_clock = self._day_offset,self._last_clock_ns
        if self.spec.format == 'numeric':
            result = convert_time(value,self.spec.unit)
            ns, quantized = result.time_ns, result.quantized
        elif self.spec.format == 'iso8601':
            # 仅用声明的时区补充无时区ISO输入，不读取执行电脑的时区。
            zone = self.spec.timezone_offset_minutes
            tz = None if zone is None else timezone(timedelta(minutes=zone))
            result = parse_datetime_ns(value,source_timezone=tz)
            ns, quantized = result.time_ns, result.quantized
        else:
            # 两种日内格式各自严格匹配；不能根据一行文字临时切换时间含义。
            if type(value) is not str:
                raise ValueError('日内时间需要明确时分秒文字')
            grouped = self.spec.format == 'clock-ms-us-v1'
            pattern = (r'([0-9]{2}):([0-9]{2}):([0-9]{2})\.([0-9]{1,3})\.([0-9]{1,3})'
                       if grouped else r'(\d{2}):(\d{2}):(\d{2})(\.\d+)?')
            match = re.fullmatch(pattern,value)
            if match is None:
                expected = 'HH:MM:SS.毫秒.微秒，各末段为0到999' if grouped else 'HH:MM:SS[.小数]；多段小数需显式clock-ms-us-v1'
                raise ValueError('日内时间需'+expected)
            hour,minute,second = (int(match[index]) for index in (1,2,3))
            if hour > 23 or minute > 59 or second > 59:
                raise ValueError('日内时分秒越界')
            if grouped:
                # 两段是各自的整数单位，不按字符拼接小数；微秒规则不引入float舍入。
                clock_ns = (hour*3600+minute*60+second)*10**9 + int(match[4])*10**6 + int(match[5])*1000
                quantized = False
            else:
                # 普通小数秒仍沿既有Decimal转纳秒协议，保留更细输入的量化事实。
                with localcontext() as context:
                    context.prec = MAX_CSV_RECORD_BYTES + 32
                    seconds = Decimal(hour*3600+minute*60+second) + Decimal(match[4] or '0')
                    result = convert_time(seconds,'s')
                clock_ns, quantized = result.time_ns, result.quantized
            # 只在明确允许且回退量达到阈值时进入次日；小幅乱序仍是错误。
            if self._last_clock_ns is not None and clock_ns < self._last_clock_ns:
                drop = self.spec.rollover_min_drop_ns
                if drop is None or self._last_clock_ns-clock_ns < drop:
                    raise ValueError('CSV日内时间回退，未满足明确跨午夜规则')
                day_offset = checked_add_ns(day_offset,DAY_NS)
            ns = checked_add_ns(day_offset,clock_ns)
            last_clock = clock_ns
        ns = checked_add_ns(ns,self.spec.offset_ns)
        # 排序在公开纳秒时间轴核对；更细的文本精度由quantized和raw_time明确保留。
        if self._last_ns is not None and ns < self._last_ns:
            raise ValueError('CSV来源时间回退')
        self._last_ns,self._day_offset,self._last_clock_ns = ns,day_offset,last_clock
        return ns,quantized


def _csv_frame(values, spec, time_ns, flag_resolver=None):
    """把已明确映射的列转换成原帧，不按载荷/ID大小猜帧型。

    参数: values规范字段映射、spec来源声明、time_ns精确纳秒；flag_resolver仅补缺少的帧型。
    返回: (LegacyRawFrame, DLC编码或None)。异常: ID/通道/载荷/标志/DLC不一致。
    """
    # 布局已校验身份枚举；ID范围按显式标准/扩展标志决定，通道转为0基。
    fd,extended,frame_type = values.get('is_fd'),values.get('is_extended'),values['frame_kind']
    identifier = _uint(values['frame_id'],spec.id_base,0x1fffffff,'CSV ID')
    channel = _uint(values['channel'],10,65536,'CSV通道') - spec.channel_origin
    if channel < 0:
        raise ValueError('CSV通道低于明确起点')
    if fd is None or extended is None:
        if flag_resolver is None:
            raise ValueError('CSV缺少is_extended或is_fd；请补列映射，或通过带DBC的分析入口自动识别')
        extended, fd = flag_resolver(channel, identifier, extended, fd)
    if type(extended) is not bool or type(fd) is not bool or not extended and identifier > 0x7ff:
        raise ValueError('CSV报文ID与标准/扩展帧声明不符')
    # DLC编码和载荷字节数分别解析，CAN FD的编码9对应12字节，不能混用。
    data = _payload(values['data'],spec.payload_style)
    code = (_uint(values['dlc_code'],spec.length_base,15 if fd else 8,'CSV DLC编码')
            if 'dlc_code' in values else None)
    length = (_uint(values['payload_length'],spec.length_base,64 if fd else 8,'CSV载荷长度')
              if 'payload_length' in values else len(data))
    if len(data) != length:
        raise ValueError('CSV声明载荷长度与实际字节数不一致')
    if frame_type == 'remote':
        # 远程请求的DLC可非零，实际载荷必须为空；FD协议没有远程帧。
        if fd or data or code is None:
            raise ValueError('远程帧需经典CAN、空载荷和明确DLC编码')
        dlc = code
    elif frame_type == 'error':
        # 当前错误帧格式不接受数据载荷；不伪造普通数据帧或用它参与DBC解码。
        if data or code not in (None,0):
            raise ValueError('当前CSV错误帧需空载荷/零长度')
        code,dlc = None,0
    else:
        # 数据帧必须同时满足实际载荷长度和协议DLC；缺编码时才由长度导出。
        expected = FD_LENGTHS[code] if fd and code is not None else code
        if code is not None and expected != length:
            raise ValueError('CSV DLC编码与载荷长度不一致')
        if fd and length not in FD_LENGTHS:
            raise ValueError('CAN FD字节数不能对应合法DLC编码')
        if code is None:
            code = FD_LENGTHS.index(length) if fd else length
        dlc = length
    brs,esi = values.get('bitrate_switch',False),values.get('error_state_indicator',False)
    # FD专用标志不能套在经典帧上；float秒仅为既有原帧模型的兼容表示。
    if not fd and (brs or esi):
        raise ValueError('经典CAN不能携带FD BRS/ESI标志')
    return LegacyRawFrame(timestamp=time_ns/10**9,arbitration_id=identifier,is_extended_id=extended,
                          is_remote_frame=frame_type=='remote',is_error_frame=frame_type=='error',channel=channel,
                          dlc=dlc,data=data,is_fd=fd,is_rx=values.get('is_rx'),bitrate_switch=brs,
                          error_state_indicator=esi),code


class _CSVLines:
    """把一次有界表记录的物理行交给标准CSV解析器，位置/字节累计由父reader持有。"""

    def __init__(self, owner):
        """借用父对象。参数: owner为CANCSVRead。返回: 行迭代器。异常: 无。
        """
        self.owner = owner

    def __iter__(self):
        """不重新打开文件。参数: 无。返回: self。异常: 无。
        """
        return self

    def __next__(self):
        """提供一个实际物理行。参数: 无。返回: 含换行str。异常: EOF、定位编码错、超限或取消。
        """
        owner = self.owner
        if owner._check_cancel is not None:
            owner._check_cancel()
        # 配额在CSV读取每条表记录前归零；跨引号的多行仍共用一个65536字节上限。
        remaining = MAX_CSV_RECORD_BYTES-owner._record_bytes
        raw = owner._file.readline(remaining+1)
        if not raw:
            raise StopIteration
        # 实际读到物理行才推进计数；超长记录定位其开始行，坏编码定位当前物理行。
        owner.line_number += 1
        owner._record_bytes += len(raw)
        if owner._record_bytes > MAX_CSV_RECORD_BYTES:
            raise CANTextError(owner.spec.path,owner._record_start,'CSV记录超过65536字节')
        encoding = owner._encoding
        # BOM只在文件第一行解释；后续单元格开头相同字节应保留为实际内容。
        if encoding == 'utf-8-sig' and owner.line_number != 1:
            encoding = 'utf-8'
        try:
            return raw.decode(encoding,errors='strict')
        except UnicodeError as error:
            raise CANTextError(owner.spec.path,owner.line_number,'CSV编码错误') from error


class CANCSVRead:
    """拥有一个文件、CSV语法迭代器和时钟，正常/失败/取消均关闭自有资源。"""

    def __init__(self, spec, budget, *, check_cancel=None, retain_original=True, retain_source_time=True, flag_resolver=None, selected_ids=None):
        """预约并只读打开一次。参数: spec为CANCSVSpec、budget共享预算、check_cancel无参取消回调；selected_ids仅在不需全原帧/来源时间的入口限定ID。

        返回: reader，不预读数据。异常: 类型/预算/I/O原错；清理失败保raw_csv_cleanup_owner。
        """
        if type(retain_original) is not bool or type(retain_source_time) is not bool:
            raise TypeError('原文/导出时间选择需要bool')
        self._retain_original=retain_original
        self._retain_source_time=retain_source_time
        if flag_resolver is not None and not callable(flag_resolver):
            raise TypeError('flag_resolver需要可调用对象')
        self._flag_resolver = flag_resolver
        if selected_ids is not None and (type(selected_ids) is not tuple or len(selected_ids)>4096
                or any(type(value) is not int or not 0 <= value <= 0x1fffffff for value in selected_ids)):
            raise ValueError('CSV按需ID需要有限合法整数tuple')
        self._selected_ids = None
        # 构造错误在取得文件和预算之前拒绝，不向外暴露半初始化来源。
        if type(spec) is not CANCSVSpec or not isinstance(budget,ResourceBudget):
            raise TypeError('CANCSVRead需要CANCSVSpec和ResourceBudget')
        if check_cancel is not None and not callable(check_cancel):
            raise TypeError('CSV取消检查需要可调用对象')
        # 先登记全部资源归属和进度，构造任意后续步骤失败都可由同一close回收。
        self.spec,self._budget,self._check_cancel = spec,budget,check_cancel
        self._encoding = codecs.lookup(spec.layout.encoding).name
        self._file,self._reader,self._bound,self._clock = None,None,None,None
        self._fixed_cost,self._held_cost,self._closed,self._initialized = 0,0,False,False
        self.line_number,self.count,self._record_bytes,self._record_start = 0,0,0,1
        self._time_position = None
        try:
            # 文本/分列/CSV引号缓存和有界表头一起计费；不加载或预分配整文件。
            _reserve_owned_ram(self,MAX_CSV_RECORD_BYTES*64+MAX_COLUMNS*256+8192+128*len(selected_ids or ()),'_fixed_cost')
            self._selected_ids = None if selected_ids is None else frozenset(selected_ids)
            self._file = spec.path.open('rb')
            self._reader = csv.reader(_CSVLines(self),delimiter=spec.layout.delimiter,strict=True)
            self._clock = CSVClock(spec.time)
        except BaseException as error:
            _cleanup_owner(self,error,'raw_csv_cleanup_owner','原始CSV读取')
            raise

    @property
    def closed(self):
        """返回真实关闭事实。参数: 无。返回: bool。异常: 无。
        """
        return self._closed

    def __iter__(self):
        """迭代同次扫描。参数: 无。返回: self。异常: 无，不另开文件。
        """
        return self

    def _next_row(self):
        """取得一条有界CSV表记录。参数: 无。返回: str列表。异常: EOF/定位语法错/取消。
        """
        # 一条CSV记录可能跨多行，因此在请求首行前记住开始位置并重置整记录配额。
        self._record_bytes,self._record_start = 0,self.line_number+1
        try:
            row = next(self._reader)
        except csv.Error as error:
            # 保留CSV库的具体原因，同时提供文件与记录开始的物理行。
            raise CANTextError(self.spec.path,self._record_start,'CSV语法错误: '+str(error)) from error
        # 即便总字节有限，也限制空列造成的列表和字符串对象数量。
        if len(row) > MAX_COLUMNS:
            raise CANTextError(self.spec.path,self._record_start,'CSV列数超过4096')
        return row

    def _initialize(self):
        """按声明跳过记录/绑定表头一次。参数: 无。返回: None。异常: 缺表头/缺列或EOF。
        """
        # 跳过的是显式声明的CSV记录数；输入不足是错误，不能当作正常空数据。
        for _ in range(self.spec.layout.skip_rows):
            try:
                self._next_row()
            except StopIteration as error:
                raise CANTextError(self.spec.path,self.line_number+1,'CSV声明跳过记录数超过实际输入') from error
        # 只有声明表头才消费这一条；绑定后所有数据行复用相同列位置。
        if self.spec.layout.has_header:
            try:
                header = self._next_row()
            except StopIteration as error:
                raise CANTextError(self.spec.path,self.line_number+1,'CSV缺少已声明的表头') from error
        else:
            header = None
        try:
            self._bound = self.spec.layout.bind_header(header)
        except (ValueError,TypeError) as error:
            raise CANTextError(self.spec.path,self._record_start,str(error)) from error
        # 时间原文取原始单元格，strip/值映射之后仍保留它的输入证据。
        self._time_position = next(position for name,_,position in self._bound.bindings if name=='timestamp')
        self._initialized = True

    def __next__(self):
        """返回下一原始CAN记录。参数: 无。返回: RawCANRecord。异常: EOF/定位坏行/预算/取消原错。
        """
        # 已关闭来源不会重新打开或重放已产出的记录。
        if self._closed:
            raise StopIteration
        try:
            if not self._initialized:
                self._initialize()
            while True:
                try:
                    row = self._next_row()
                except StopIteration:
                    self.close()
                    raise
                try:
                    if self._selected_ids is not None:
                        # 仅消息汇总且无需来源时间/原帧时，先看ID；无关行不补造帧型。
                        identity = self._bound.map_row(row, names=('frame_id',))
                        identifier = _uint(identity['frame_id'],self.spec.id_base,0x1fffffff,'CSV ID')
                        if identifier not in self._selected_ids:
                            # 显式跨午夜需所有日内时钟推进；只取这一个必要字段，仍不解析帧型和载荷。
                            if self.spec.time.rollover_min_drop_ns is not None:
                                clock = self._bound.map_row(row, names=('timestamp',))
                                self._clock.parse(clock['timestamp'])
                            self.count += 1
                            continue
                    values = self._bound.map_row(row)
                except (ValueError,TypeError,OverflowError) as error:
                    raise CANTextError(self.spec.path,self._record_start,str(error)) from error
                break
            try:
                time_ns,quantized = self._clock.parse(values['timestamp'])
                frame,code = _csv_frame(values,self.spec,time_ns,self._flag_resolver)
                mapping = self.spec.layout.fields['timestamp']
                raw_time = (str(mapping.fixed) if self._time_position is None else row[self._time_position]) if self._retain_original else None
                # 时钟已完成换日/时区解释，撤去且仅撤去显式分析平移，保精确原坐标供导出。
                source_ns = require_int64_ns(time_ns-self.spec.time.offset_ns) if self._retain_source_time else None
                record = RawCANRecord(frame,time_ns,self.spec.path,self._record_start,self.count,
                                      raw_time,'raw-can-csv-v1',code,quantized,source_ns)
            except (ValueError,TypeError,OverflowError) as error:
                # 数据问题携带原行定位，不吞掉程序错误、取消或资源错误。
                raise CANTextError(self.spec.path,self._record_start,str(error)) from error
            # 序号包括按ID跳过的实际输入行；同刻不同原帧不合并。
            self.count += 1
            return record
        except StopIteration:
            raise
        except BaseException as error:
            # 保留原错，关闭持续失败时把真实reader附回异常，供调用方重试清理。
            _cleanup_owner(self,error,'raw_csv_cleanup_owner','原始CSV读取')
            raise

    def close(self):
        """关闭文件和解析状态再归还自有预算，可重试。参数: 无。返回: None。异常: 关闭/预算原错。
        """
        # 关闭幂等；句柄关闭成功后才丢弃引用，失败时仍能对同一对象重试。
        if self._closed:
            return
        if self._file is not None:
            self._file.close()
            self._file = None
        # 文件已关闭才释放解析状态与本对象实际持有的预算，不能释放其他来源费用。
        self._reader,self._bound,self._clock = None,None,None
        if self._fixed_cost:
            _release_owned_ram(self,self._fixed_cost,'_fixed_cost')
        self._closed = True
        self._flag_resolver = self._selected_ids = None

    def __enter__(self):
        """提供受控读取上下文。参数: 无。返回: self。异常: 无。
        """
        return self

    def __exit__(self, exception_type, error, traceback):
        """保留原错并收尾。参数: exception_type/error/traceback异常信息。返回: False。异常: 无原错时关闭失败。
        """
        # 正常退出直接报告关闭错误；已有业务错误时保原错及必要的恢复owner。
        if error is None:
            self.close()
        else:
            _cleanup_owner(self,error,'raw_csv_cleanup_owner','原始CSV读取')
        return False
