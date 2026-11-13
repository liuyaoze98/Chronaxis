"""保留单BLF协议的报文、解码值、定位和有界IPC字段。

输入为同次can.Message的公开写出字段、原parse_frame返回值与用户定位声明；
输出是冻结dataclass及最大65536字节的JSON包。data以hex无损表达，非有限
解码浮点使用明确标签；不执行eval、pickle或任意模型反序列化，不应用DBC缩放。
本文件只依赖标准库，无来源/DBC读取或进程副作用。父进程承担wire/记录副本预算，
worker在INIT后才加载真实库；记录模型不声称原reader已关闭或旧进程RSS受控。
"""

# 模型和wire不导入CAN库或数值核心，spawn加载本文件不会提前打开用户输入。
from collections.abc import Mapping
from dataclasses import dataclass
import json
from math import isfinite, isnan
from pathlib import Path
from re import fullmatch
from types import MappingProxyType

# profile标记既有解码语义，当前读取与写出已共用实现；wire限额仍是协议固定事实。
PROFILE_ID = 'sclicer-functions-v1'
MAX_WIRE_BYTES = 65536
_RAW_FIELDS = ('timestamp', 'arbitration_id', 'is_extended_id', 'is_remote_frame', 'is_error_frame',
    'channel', 'dlc', 'is_fd', 'is_rx', 'bitrate_switch', 'error_state_indicator')
_LOCATOR_FIELDS = ('channel', 'signal', 'frame_id', 'is_extended', 'is_fd')


def normalize_frame_id(value):
    """将配置报文ID统一成整数；无前缀始终按十进制。

    参数: value为原生int或十进制、0x十六进制、0b二进制文本。
    返回: 0至0x1FFFFFFF的原生int。异常: TypeError为其他类型；ValueError为格式或范围非法。
    副作用: 无；不用于ASC等原始文件的专有进制解析。
    """
    # bool也是int子类，必须先按精确类型排除，不能把开关当报文ID。
    if type(value) is str:
        if fullmatch(r'[0-9]+', value):
            value = int(value, 10)
        elif fullmatch(r'0[xX][0-9a-fA-F]+', value):
            value = int(value[2:], 16)
        elif fullmatch(r'0[bB][01]+', value):
            value = int(value[2:], 2)
        else:
            raise ValueError('frame_id需要十进制整数、0x十六进制或0b二进制')
    elif type(value) is not int:
        raise TypeError('frame_id需要整数或进制文本，不接受bool或浮点数')
    # 范围只证明是合法CAN数值；小ID仍可能是扩展帧，不在这里猜类型。
    if not 0 <= value <= 0x1FFFFFFF:
        raise ValueError('frame_id超出CAN范围0至0x1FFFFFFF')
    return value


# 只计算固定键名、标点、item文本、空values花括号和data_hex两端引号。
# 动态标量的位置故意留空，这不是待发送的JSON；字段顺序不影响字节总数。
# 下方独立编码器对照测试会捕捉原ITEM结构变动，不能另行放宽单条能力。
_ITEM_FIXED_BYTES = len(
    b'{"op":"item","request_id":,"record":{"sequence":,"frame":{'
    b'"timestamp":,"arbitration_id":,"is_extended_id":,"is_remote_frame":,'
    b'"is_error_frame":,"channel":,"dlc":,"is_fd":,"is_rx":,'
    b'"bitrate_switch":,"error_state_indicator":,"data_hex":""},"values":{}}}')


# 固定语法已包含values的{}与data_hex两引号。动态字段取确定上界：两个非负
# 64bit序号各20字符；有限binary64用32；29bit ID用9；DLC用2；64字节hex用128；
# 七个bool最多35。这里故意多算，只有完整上界不超过原限额时才能省掉精确计长。
_SMALL_ITEM_BASE_UPPER = _ITEM_FIXED_BYTES + 40 + 32 + 9 + 2 + 128 + 35


def _small_item_fits(values, sequence, channel):
    """证明已核原字段的小ITEM符合原限额；不能证明时返回False，不拒绝输入。

    参数: values已确认为Mapping；sequence已核原生非负int；channel已核原帧类型。
        同次原帧的有限float时间、29bit ID、DLC/data不超过64及七个bool也须已核。
    返回: bool。True表示完整原生dict均已检查且整个ITEM的保守上界不超过65536。
    异常: 取消、分配失败或原生dict并发变化等运行时错误原样传播，不伪装成正常回退。
    边界: 只接受非空原生ASCII键及原生bool、有限float或绝对值不超过64bit的int。
        非有限诊断、Unicode、大整数和近限额记录都交回原精确路径；不复制或缓存值。
    """
    name = value = None
    try:
        # 自定义Mapping/dict子类不在此额外调用len/items，仍只按原路径观察一次。
        if type(values) is not dict or sequence.bit_length() > 64:
            return False
        upper = _SMALL_ITEM_BASE_UPPER
        if channel is None:
            upper += 4
        elif type(channel) is int:
            if channel.bit_length() > 64:
                return False
            upper += 21  # 64bit绝对值最多20位十进制数字，再加可能的负号。
        elif type(channel) is str:
            upper += 6 * len(channel) + 2
            if upper > MAX_WIRE_BYTES or not channel.isascii():
                return False
        else:
            return False
        # ASCII字符最坏为六字节转义；键引号与冒号共3；数值取32；多计一个逗号。
        # 因而每个非空键至少占本证明的42字节。门禁失败只是需要精确检查。
        if len(values) > (MAX_WIRE_BYTES - upper) // 42:
            return False
        for name, value in values.items():
            if type(name) is not str or not name:
                return False
            upper += 6 * len(name) + 36
            if upper > MAX_WIRE_BYTES or not name.isascii():
                return False
            value_type = type(value)
            if value_type is float:
                # 有限binary64的JSON表示至多24字符，此处用32覆盖全部符号/指数格式。
                if not isfinite(value):
                    return False
            elif value_type is int:
                if value.bit_length() > 64:
                    return False
            elif value_type is not bool:
                return False
        return True
    finally:
        values = sequence = channel = name = value = None


def _integer(value, name, minimum=0, maximum=None):
    """检查原生整数边界，bool不能充当序号、通道或ID。

    参数: value为候选值；name定位字段；minimum/maximum为含端点范围，None无上界。
    返回: 原int。异常: TypeError为非int，ValueError为超范围；无转换或I/O。
    """
    if type(value) is not int:
        raise TypeError(name + '需要原生int')
    if value < minimum or maximum is not None and value > maximum:
        raise ValueError(name + '超出允许范围')
    return value


def _text(value, name):
    """检查有限非空原文本，不将DBC名称改成表达式标识符。

    参数: value为候选文本；name定位字段。返回: 原str。
    异常: TypeError/ValueError为类型、空文本或超过单包字符上限；不改大小写/空格。
    """
    if type(value) is not str:
        raise TypeError(name + '需要原生str')
    if not value or len(value) > MAX_WIRE_BYTES:
        raise ValueError(name + '为空或过长')
    return value


def _shape(value, names, name):
    """校验wire字典精确字段，拒绝额外对象标签或丢失字段。

    参数: value为候选dict；names为固定字段名容器；name定位对象。
    返回: 原dict。异常: TypeError/ValueError为容器或字段不符。
    """
    if type(value) is not dict:
        raise TypeError(name + '需要dict')
    if len(value) != len(names) or any(key not in names for key in value):
        raise ValueError(name + '字段缺失或多余')
    return value


@dataclass(frozen=True)
class LegacyRawFrame:
    """保留同次原msg全部公开写出字段，不重构消息或推断DBC质量。"""

    timestamp: float  # 原浮点秒；有限性不代表上游精度可恢复。
    arbitration_id: int  # 原29位以内报文ID，不把channel拼进ID。
    is_extended_id: bool  # 原标准/扩展帧标志。
    is_remote_frame: bool  # 原远程帧标志，不按投影滤掉。
    is_error_frame: bool  # 原错误帧标志。
    channel: int | str | None  # 原公开通道值，不猜缺失通道。
    dlc: int  # 原公开DLC，不根据data长度重算。
    data: bytes  # 原payload的独立无损bytes副本。
    is_fd: bool  # 原CAN FD标志。
    is_rx: bool | None  # 原收发方向；CSV未提供时为None，不能据此导出Rx/Tx。
    bitrate_switch: bool  # 原FD速率切换标志。
    error_state_indicator: bool  # 原FD错误状态指示。

    def __post_init__(self):
        """校验公开字段类型，不补帧、缩放或改变原顺序。

        参数: 无。返回: None。异常: TypeError/ValueError为非法字段或超过CAN最大payload。
        """
        if type(self.timestamp) is not float or not isfinite(self.timestamp):
            raise ValueError('原报文timestamp需要有限float秒')
        _integer(self.arbitration_id, 'arbitration_id', maximum=0x1FFFFFFF)
        _integer(self.dlc, 'dlc', maximum=64)
        if type(self.data) is not bytes or len(self.data) > 64:
            raise ValueError('原报文data需要不超过64字节的bytes')
        if self.channel is not None and type(self.channel) not in (int, str):
            raise TypeError('原报文channel需要int/str/None')
        if type(self.channel) is str and len(self.channel) > MAX_WIRE_BYTES:
            raise ValueError('原报文channel文本过长')
        if self.is_rx is not None and type(self.is_rx) is not bool:
            raise TypeError('is_rx需要bool或未知None')
        for name in ('is_extended_id', 'is_remote_frame', 'is_error_frame', 'is_fd',
                'bitrate_switch', 'error_state_indicator'):
            if type(getattr(self, name)) is not bool:
                raise TypeError(name + '需要bool')


@dataclass(frozen=True)
class LegacyDecodedFrame:
    """保存一次原yield和一次parse的结果，values独立只读且保留非有限诊断值。"""

    sequence: int  # 本次来源从0开始的原yield序号，不是物理文件行号。
    frame: LegacyRawFrame  # 同次原msg公开快照。
    values: Mapping[str, int | float | bool]  # 原返回字典，空dict不推断错误原因。

    def __post_init__(self):
        """冻结原数值映射，不把缺键或非有限浮点替换为零。

        参数: 无。返回: None。异常: TypeError/ValueError为序号、frame或数值类型错误。
        """
        _integer(self.sequence, 'sequence')
        if type(self.frame) is not LegacyRawFrame or not isinstance(self.values, Mapping):
            raise TypeError('解码记录需要LegacyRawFrame与数值Mapping')
        # ITEM外壳也属于64KiB能力；先完整预检，再复制有界映射，避免大Mapping先复制后拒绝。
        base = _wire_tree({'op': 'item', 'request_id': self.sequence,
            'record': {'sequence': self.sequence, 'frame': frame_to_dict(self.frame), 'values': {}}})
        available = MAX_WIRE_BYTES - base + 2
        _decoded_values_size(self.values, available)
        values = {}
        used = 2
        for name, value in self.values.items():
            # 第二遍仍逐项检查后才插入，Mapping在两遍间变化也不能扩大已复制前缀。
            separator = 1 if values else 0
            used += separator + _decoded_entry_size(name, value, available - used - separator)
            values[name] = value
        object.__setattr__(self, 'values', MappingProxyType(values))


@dataclass(frozen=True)
class StoredRawFrame:
    """为首次读取保存原frame与分析坐标，供后续导出从新暂存回读。"""

    sequence: int  # 原yield顺序，含同刻不同消息。
    time_ns: int  # 明确映射后的int64纳秒，不改变原frame.timestamp。
    frame: LegacyRawFrame  # 原公开写出字段。

    def __post_init__(self):
        """检查原序号和新分析坐标，拒绝越界或替代模型。

        参数: 无。返回: None。异常: TypeError/ValueError为字段或int64范围不符。
        """
        _integer(self.sequence, 'sequence')
        _integer(self.time_ns, 'time_ns', -(1 << 63), (1 << 63) - 1)
        if type(self.frame) is not LegacyRawFrame:
            raise TypeError('原始暂存需要LegacyRawFrame')


@dataclass(frozen=True)
class LegacyCANField:
    """按通道、ID和信号定位；可选帧类型由运行时实际记录消除歧义。"""

    channel: int  # 用户明确通道；首版定位不接受缺失或自由文本。
    signal: str  # DBC原signal名称。
    frame_id: int  # 同次DBC核对的原报文ID。
    is_extended: bool | None = None  # None表示未限制帧类型，不等于标准帧。
    is_fd: bool | None = None  # None表示未限制经典CAN/FD。

    def __post_init__(self):
        """校验定位形状，实际唯一性由worker同次公开DBC元数据核实。

        参数: 无。返回: None。异常: TypeError/ValueError为声明字段非法。
        """
        _integer(self.channel, 'field.channel')
        object.__setattr__(self, 'frame_id', normalize_frame_id(self.frame_id))
        _text(self.signal, 'field.signal')
        if any(value is not None and type(value) is not bool for value in (self.is_extended, self.is_fd)):
            raise TypeError('字段is_extended/is_fd需要bool或省略')
        if self.is_extended is False and self.frame_id > 0x7FF:
            raise ValueError('标准帧frame_id不能超过0x7FF')

    @property
    def key(self):
        """提供稳定原定位键，供新绑定层引用；不改signal名称。

        参数: 无。返回: 规范紧凑JSON str。异常: 原json编码错误；无I/O或DBC查询。
        """
        return encode_packet(field_to_dict(self)).decode('utf-8')


@dataclass(frozen=True)
class LegacyCANRequest:
    """声明单BLF、单DBC和有限原定位；构造只校验模型，不访问文件。"""

    input_path: Path  # 原BLF路径，不在模型中resolve或新增扫描。
    dbc_path: Path  # 只供worker加载一次DBC。
    fields: tuple[LegacyCANField, ...]  # 空tuple可原样读取全部帧，不省decode。

    def __post_init__(self):
        """拒绝替代路径/定位及重复完整定位，保留原tuple顺序。

        参数: 无。返回: None。异常: TypeError/ValueError为路径类型或重复定位错误。
        """
        if not isinstance(self.input_path, Path) or not isinstance(self.dbc_path, Path):
            raise TypeError('原CAN请求路径需要Path')
        if type(self.fields) is not tuple:
            raise TypeError('原CAN请求fields需要LegacyCANField tuple')
        if len(self.fields) > MAX_WIRE_BYTES // 2:
            raise ValueError('原CAN定位数量超过wire能力')
        if any(type(item) is not LegacyCANField for item in self.fields):
            raise TypeError('原CAN请求fields需要LegacyCANField tuple')
        # 路径和字段集先累计INIT字节，再创建重复键集合；不为任意大fields复制全部key。
        for path in (self.input_path, self.dbc_path):
            if sum(len(part) for part in path.parts) > MAX_WIRE_BYTES:
                raise ValueError('原CAN路径超过wire能力')
        used = _wire_tree({'op': 'init', 'version': 1, 'path': str(self.input_path),
            'dbc_path': str(self.dbc_path), 'fields': []})
        for index, field in enumerate(self.fields):
            separator = 1 if index else 0
            used += separator + _wire_tree(field_to_dict(field), remaining=MAX_WIRE_BYTES - used - separator)
        if len({item.key for item in self.fields}) != len(self.fields):
            raise ValueError('原CAN请求完整定位重复')

    @property
    def profile(self):
        """读取唯一受支持profile。参数: 无。返回: 固定str。异常: 无。
        """
        return PROFILE_ID


def frame_to_dict(frame):
    """将原frame编码为固定JSON字段，data_hex不丢失任一字节。

    参数: frame为LegacyRawFrame。返回: 新dict。异常: TypeError为非法模型。
    """
    if type(frame) is not LegacyRawFrame:
        raise TypeError('需要LegacyRawFrame')
    return {**{name: getattr(frame, name) for name in _RAW_FIELDS}, 'data_hex': frame.data.hex()}


def frame_from_dict(value):
    """只从固定字段重建原frame，不加载任意类或调用CAN构造器。

    参数: value为wire dict。返回: LegacyRawFrame。
    异常: TypeError/ValueError为形状、hex或原frame字段非法。
    """
    _shape(value, (*_RAW_FIELDS, 'data_hex'), 'raw frame')
    text = value['data_hex']
    if type(text) is not str or len(text) > 128 or len(text) % 2 or any(char not in '0123456789abcdefABCDEF' for char in text):
        raise ValueError('data_hex需要不超过64字节的完整hex')
    return LegacyRawFrame(**{name: value[name] for name in _RAW_FIELDS}, data=bytes.fromhex(text))


def _value_to_wire(value):
    """给非有限原解码float明确标签，有限数字和bool保原类型。

    参数: value为原生int/float/bool。返回: JSON标量或diagnostic_float字典。
    异常: TypeError为未支持值；不按数值truthiness丢弃False或0。
    """
    if type(value) not in (int, float, bool):
        raise TypeError('解码wire值仅支持数值或bool')
    if type(value) is float and not isfinite(value):
        return {'diagnostic_float': 'nan' if isnan(value) else 'inf' if value > 0 else '-inf'}
    return value


def _value_from_wire(value):
    """恢复固定非有限标签，拒绝裸NaN和任意标签对象。

    参数: value为JSON数值/bool或固定诊断dict。返回: 原生int/float/bool。
    异常: TypeError/ValueError为未知类型、标签或未标记非有限数值。
    """
    if type(value) is dict:
        _shape(value, ('diagnostic_float',), 'decoded diagnostic')
        if value['diagnostic_float'] not in ('nan', 'inf', '-inf'):
            raise ValueError('未知非有限解码标签')
        return float(value['diagnostic_float'])
    if type(value) not in (int, float, bool) or type(value) is float and not isfinite(value):
        raise TypeError('解码wire值非法或非有限标签缺失')
    return value


def decoded_to_dict(record):
    """编码一次原yield的完整解码记录，不投影或过滤返回键。

    参数: record为LegacyDecodedFrame。返回: 固定dict。
    异常: TypeError为非法模型；原值编码错误传播。
    """
    if type(record) is not LegacyDecodedFrame:
        raise TypeError('需要LegacyDecodedFrame')
    return {'sequence': record.sequence, 'frame': frame_to_dict(record.frame),
        'values': {name: _value_to_wire(value) for name, value in record.values.items()}}


def decoded_from_dict(value):
    """重建单次原返回，空dict与非有限诊断均保持，不猜解码失败原因。

    参数: value为固定wire dict。返回: LegacyDecodedFrame。
    异常: TypeError/ValueError为形状或值非法。
    """
    _shape(value, ('sequence', 'frame', 'values'), 'decoded frame')
    if type(value['values']) is not dict:
        raise TypeError('decoded values需要dict')
    # direct helper调用也不能绕过decode_packet，在新values字典复制前核原JSON树上限。
    _wire_tree(value)
    return LegacyDecodedFrame(value['sequence'], frame_from_dict(value['frame']),
        {name: _value_from_wire(item) for name, item in value['values'].items()})


def _decoded_from_checked_dict(value):
    """在同次严格JSON解包后重建原记录，原值只检查一次后冻结自有字典。

    参数: value为消息仓或批次解包中同次decode_packet刚返回的原生dict；
        两者之间不能调用外部代码、修改子树或把检查结果缓存到其他请求。
    返回: LegacyDecodedFrame，原字段、数值类型及非有限诊断按公共入口相同方式恢复。
    异常: 原形状、frame、数值、模型限额或分配/取消错误；调用方保持原错误包装。
    约束: 首次解包已检查UTF-8、重复键、深度和64KiB；本函数不是独立解析入口，
        不开放trusted参数。公共decoded_from_dict仍独立完整检查，不能改走本路径省略边界。
        本层新建的values只含原生不可变标量，未向外暴露；常见完整值可用保守上界
        证明ITEM不超限，不能证明时沿原精确路径。核完ITEM外壳/全部值
        后可直接冻结，不需要公开构造器为外部可变Mapping设置的第二遍检查和复制。
    副作用: 仅建立本条有界模型；不持有跨调用状态，不读写文件或改变预算。
        清理只断开本模块已结束异常frame的临时引用，保留原异常、诊断与traceback结构。
    """
    sequence = frame = values = record = current = None
    try:
        _shape(value, ('sequence', 'frame', 'values'), 'decoded frame')
        if type(value['values']) is not dict:
            raise TypeError('decoded values需要dict')
        # 原构造表达式先取sequence，再构造frame及转换全部values；sequence的类型
        # 检查在这三项求值之后，不能因合并步骤改变同时存在多个错误时的优先级。
        sequence = value['sequence']
        frame = frame_from_dict(value['frame'])
        values = {name: _value_from_wire(item) for name, item in value['values'].items()}
        _integer(sequence, 'sequence')
        if type(frame) is not LegacyRawFrame:
            raise TypeError('解码记录需要LegacyRawFrame与数值Mapping')
        # 原decoded包在64KiB内，不等于加ITEM外壳后仍在限额内。此处frame及序号
        # 已完成原检查，values也已在本层转换；只在完整保守上界成立时省精确计长。
        # Unicode/非有限诊断/大整数/近限额沿原公式和错误先后，不凭wire成功放行。
        if not _small_item_fits(values, sequence, frame.channel):
            base = _wire_tree({'op': 'item', 'request_id': sequence,
                'record': {'sequence': sequence, 'frame': frame_to_dict(frame), 'values': {}}})
            _decoded_values_size(values, MAX_WIRE_BYTES - base + 2)
        # 字典只在本层创建和检查，无用户Mapping回调或借入可变别名；不调用公开
        # 构造器重做第二遍。同一真实record持有冻结后的唯一dict，不借原parsed树。
        record = object.__new__(LegacyDecodedFrame)
        object.__setattr__(record, 'sequence', sequence)
        object.__setattr__(record, 'frame', frame)
        object.__setattr__(record, 'values', MappingProxyType(values))
        return record
    except BaseException as exc:
        # 调用方可能保留原取消/错误；只清本模块已结束的辅助frame，不清用户或
        # 标准库诊断，不沿cause/context扩展遍历。活跃的本函数由finally清其责任槽。
        current = exc.__traceback__
        while current is not None:
            if current.tb_frame.f_globals.get('__name__') == __name__:
                try:
                    current.tb_frame.clear()
                except RuntimeError:
                    pass
            current = current.tb_next
        raise
    finally:
        value = sequence = frame = values = record = current = None


def _try_decoded_small_packet(payload):
    """解析并证明常见完整decoded小包合法，不能证明时返回None交回原入口。

    参数: payload为本次已预付工作空间内的有界bytes，不借外部JSON树或验证标志。
    返回: 独立冻结的LegacyDecodedFrame；None只表示需走完整原路径，不表示输入非法。
    异常: 原JSON/模型错误、MemoryError或取消；外层只对普通错误重走原错误顺序。
    流程: 保留UTF-8、重复键、裸非有限常量检查及完整frame/sequence校验；只有
        原生ASCII键和有限数值/bool满足完整ITEM保守上界，才省去重复JSON树遍历。
        固定字段结构的深度与标量已由模型核定，ITEM上界也覆盖较小decoded包。
        复杂值、Unicode、近限额等均返回原路径；成功只创建一份frame及自有values。
    副作用: 无I/O、跨行缓存或新预算owner。回退前释放本次临时模型，原错误仅清理
        本模块已结束frame的借入引用；取消及内存错误不重试，不清用户诊断frame。
    """
    parsed = raw_values = values = sequence = frame = result = current = None
    try:
        if type(payload) is not bytes or not payload or len(payload) > MAX_WIRE_BYTES:
            return None
        parsed = json.loads(payload.decode('utf-8'), object_pairs_hook=_unique_object,
                            parse_constant=_reject_constant)
        _shape(parsed, ('sequence', 'frame', 'values'), 'decoded frame')
        raw_values = parsed['values']
        if type(raw_values) is not dict:
            return None
        frame = frame_from_dict(parsed['frame'])
        sequence = parsed['sequence']
        _integer(sequence, 'sequence')
        if not _small_item_fits(raw_values, sequence, frame.channel):
            return None
        # 正证明仅接受原生有限数值/bool；_value_from_wire对此域原样返回。
        # parsed未暴露给调用方，复制一次可使最终冻结字典与解析树独立。
        values = raw_values.copy()
        result = object.__new__(LegacyDecodedFrame)
        object.__setattr__(result, 'sequence', sequence)
        object.__setattr__(result, 'frame', frame)
        object.__setattr__(result, 'values', MappingProxyType(values))
        return result
    except BaseException as exc:
        current = exc.__traceback__
        while current is not None:
            if current.tb_frame.f_globals.get('__name__') == __name__:
                try:
                    current.tb_frame.clear()
                except RuntimeError:
                    pass
            current = current.tb_next
        raise
    finally:
        payload = parsed = raw_values = values = sequence = frame = result = current = None


def _decoded_from_packet(payload):
    """在同次专用decoded包解析中复用小包证明，保原完整入口的输出及错误顺序。

    参数: payload为完整decoded JSON bytes，仍受原64KiB及ITEM外壳限制。
    返回: LegacyDecodedFrame；完整字段、原值类型、量化前时间及非有限诊断不变。
    异常: 与decode_packet后接私有构建相同的原错误；MemoryError/取消原样传播。
    边界: 普通失败退出except并释放试算对象后，重新由原完整解析/构建决定报错；
        不提前把frame错误置于wire错误前。公共decode_packet及decoded_from_dict不变。
    """
    result = None
    try:
        try:
            result = _try_decoded_small_packet(payload)
        except (TypeError, ValueError, OverflowError, RecursionError):
            pass
        if result is not None:
            return result
        return _decoded_from_checked_dict(decode_packet(payload))
    finally:
        payload = result = None


def field_to_dict(field):
    """按唯一定位合同输出原字段，不带样本或隐式别名。

    参数: field为LegacyCANField。返回: 固定dict。异常: TypeError为非法模型。
    """
    if type(field) is not LegacyCANField:
        raise TypeError('需要LegacyCANField')
    return {name: getattr(field, name) for name in _LOCATOR_FIELDS if getattr(field, name) is not None}


def field_from_dict(value):
    """只构建固定定位模型，不接受多余元数据或对象标签。

    参数: value为固定dict。返回: LegacyCANField。异常: TypeError/ValueError为形状或字段非法。
    """
    # 省略与显式null区分；旧message不能静默忽略，避免误以为它仍约束匹配。
    if type(value) is not dict:
        raise TypeError('CAN field需要dict')
    if 'message' in value:
        raise ValueError('message参数已删除；请删除message，保留signal并用frame_id定位')
    if set(value) - set(_LOCATOR_FIELDS) or not {'channel', 'signal', 'frame_id'} <= set(value):
        raise ValueError('CAN field需要channel、frame_id、signal；仅可附加is_extended/is_fd')
    if any(name in value and type(value[name]) is not bool for name in ('is_extended', 'is_fd')):
        raise TypeError('is_extended/is_fd填写时必须为bool，不能为null')
    return LegacyCANField(**value)


def _scalar_size(value, remaining):
    """计算原生JSON标量字节，普通标量直接计数，复杂文本仍交原JSON编码器。

    参数: value为JSON标量；remaining为本包剩余字节。返回: 精确UTF-8编码长度。
    异常: TypeError/ValueError/UnicodeError为类型/数值/限额；标量暂态最多单包有限倍数。
    """
    if type(value) is str:
        if len(value) + 2 > remaining:
            raise ValueError('wire文本超过单包上限')
        # 可打印ASCII中只需排除引号和反斜杠，其他字符一字节且不转义，另计两端引号。
        # 控制字符、DEL、Unicode及转义文本保留原编码路径，不重写JSON转义/UTF-8规则。
        if value.isascii() and value.isprintable() and '"' not in value and '\\' not in value:
            size = len(value) + 2
        else:
            size = len(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8'))
    elif value is None:
        size = 4  # JSON的null固定四个ASCII字节，不为尺寸检查重复构造编码器。
    elif type(value) is bool:
        size = 4 if value else 5  # JSON原样写true/false，不能按整数1/0的长度计算。
    elif type(value) is int:
        if value.bit_length() > MAX_WIRE_BYTES * 4:
            raise ValueError('wire整数超过单包能力')
        # 原生int的十进制表示与JSON一致，保符号及Python本身的超长整数转换限制。
        size = len(str(value))
    elif type(value) is float:
        if not isfinite(value):
            raise ValueError('wire非有限数值必须显式标签')
        # 标准库JSON对有限原生float使用其repr，包含指数及-0.0；全为ASCII。
        # 此处只计长度，最终输出仍由JSON编码器产生，非有限值继续由上方拒绝。
        size = len(repr(value))
    else:
        raise TypeError('wire标量类型不受支持')
    if size > remaining:
        raise ValueError('wire包超过65536字节')
    return size


def _decoded_entry_size(name, value, remaining):
    """在插入新values字典前核单项完整wire成本，保0/False和非有限原值。

    参数: name为原信号str；value为原数值/bool；remaining为剩余值域字节。
    返回: 键、冒号和值的精确长度。异常: 原类型、非空名称或wire限额错误。
    """
    _text(name, 'decoded signal')
    size = _scalar_size(name, remaining)
    return size + 1 + _wire_tree(_value_to_wire(value), remaining=remaining - size - 1)


def _decoded_values_size(values, remaining):
    """不复制Mapping先预检全部解码值，累计成本限制无界或动态items前缀。

    参数: values为原Mapping；remaining为含两花括号的wire可用字节。
    返回: 精确值字典长度。异常: 类型/限额错误，尚未创建values副本。
    """
    if len(values) > remaining // 4:
        raise ValueError('解码信号数量超过64KiB wire能力')
    used = 2
    for index, (name, value) in enumerate(values.items()):
        separator = 1 if index else 0
        used += separator + _decoded_entry_size(name, value, remaining - used - separator)
    return used


def _wire_tree(value, depth=0, remaining=MAX_WIRE_BYTES):
    """在JSON复制前累计精确包大小，嵌套子树共享剩余额度而非各自重置上限。

    参数: value为JSON树；depth为递归层；remaining为整包尚余字节。
    返回: 紧凑UTF-8 JSON精确长度。异常: TypeError/ValueError为类型/深度/总量；无任意类构建。
    """
    if depth > 16 or remaining < 0:
        raise ValueError('wire嵌套或累计大小超过上限')
    if value is None or type(value) in (bool, int, float, str):
        return _scalar_size(value, remaining)
    if type(value) not in (dict, list):
        raise TypeError('wire仅接JSON结构，不接任意对象')
    if len(value) > remaining // 2:
        raise ValueError('wire容器超过单包上限')
    used = 2
    if type(value) is dict:
        for index, (name, item) in enumerate(value.items()):
            if type(name) is not str:
                raise TypeError('wire字典键需要str')
            used += 1 if index else 0
            # 键已确认为原生str，直接计数；仍先执行原递归入口的深度/剩余守卫。
            # 守卫顺序及错误消息不变，不能因省去类型分流而放过第17层或负剩余额度。
            key_remaining = remaining - used
            if depth + 1 > 16 or key_remaining < 0:
                raise ValueError('wire嵌套或累计大小超过上限')
            used += _scalar_size(name, key_remaining)
            used += 1
            used += _wire_tree(item, depth + 1, remaining - used)
    else:
        for index, item in enumerate(value):
            used += 1 if index else 0
            used += _wire_tree(item, depth + 1, remaining - used)
    if used > remaining:
        raise ValueError('wire包超过65536字节')
    return used


def encode_packet(value):
    """编码最大65536字节的单个JSON对象包，不带换行或pickle。

    参数: value为dict根、有限JSON树。返回: UTF-8 bytes。
    异常: TypeError/ValueError为类型/非有限/深度/字节上限或JSON编码失败。
    """
    if type(value) is not dict:
        raise TypeError('wire包根需要dict')
    _wire_tree(value)
    # 树预检已限制整包精确长度；一次编码避免逐JSON片段调用Python循环和UTF-8转换。
    # 保留原排序、紧凑格式和严格UTF-8，并再次核对实际字节，不依赖尺寸预检独自守边界。
    result = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
        separators=(',', ':')).encode('utf-8')
    if len(result) > MAX_WIRE_BYTES:
        raise ValueError('wire包超过65536字节')
    return result


def _unique_object(pairs):
    """拒绝重复JSON键，防止后值覆盖已核过的协议字段。

    参数: pairs为解析器键值对。返回: 新dict。异常: ValueError为重复字段。
    """
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError('wire存在重复JSON键')
        result[name] = value
    return result


def _reject_constant(value):
    """拒绝NaN/Infinity非标准JSON常量。

    参数: value为解析器常量文本。返回: 无。异常: ValueError总是抛出。
    """
    raise ValueError('wire非法JSON数值: ' + value)


def decode_packet(payload):
    """从有界JSON bytes校验包形状，不反序列化任意Python对象。

    参数: payload为不超过MAX_WIRE_BYTES的bytes。返回: 已校验dict。
    异常: TypeError/ValueError/UnicodeError为类型、大小、格式或结构非法。
    """
    if type(payload) is not bytes or not payload or len(payload) > MAX_WIRE_BYTES:
        raise ValueError('wire包需要1至65536字节的bytes')
    value = json.loads(payload.decode('utf-8'), object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    if type(value) is not dict:
        raise TypeError('wire包根需要dict')
    _wire_tree(value)
    return value
