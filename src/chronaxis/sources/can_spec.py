"""声明固定旧函数链的有序BLF来源，并保存解码样本的完整CAN定位。

LegacyCANSpec接收首个Path、可选连续paths、一个DBC Path、明确通道、TimebaseSpec和原浮点秒
表示，输出冻结声明；构造只查类型、后缀和纳秒偏移，不open/stat/resolve，不加载
旧模块、CAN库或DBC，也不猜时区、单位、方向、实际观测范围和解码质量。
CANSourceRef在通用会话/来源/field上保留原路径、profile、通道、信号、实际帧型、
yield序号、原浮点秒及时间量化标志。field是ID/信号及可选帧类型的规范JSON，
不能把原名称当DSL变量、隐藏改名、再次施加DBC缩放或声称原物理行号。
仅依赖通用模型和基于标准库的CAN读取记录协议；无文件、子进程、reader或预算生命周期。
"""

# 冻结声明和显式路径不访问文件；原浮点秒只检查有限性，不恢复丢失精度。
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from ..core.models import SourceRef, TimebaseSpec
from ..core.validation import require_identifier, require_text
from ..legacy.records import (LegacyCANField, MAX_WIRE_BYTES, PROFILE_ID, decode_packet, field_from_dict)
from ..timebase.conversion import require_int64_ns


def _nonnegative_integer(value, name):
    """检查原生非负通道/序号，不接受bool或外部整数子类替代。

    参数: value为候选值；name为字段诊断名。返回: None，不重编号或转换类型。
    异常: TypeError为非原生int，ValueError为负数；无I/O。
    """
    if type(value) is not int:
        raise TypeError(name + '需要原生int')
    if value < 0:
        raise ValueError(name + '需要非负整数')


def can_field_from_key(text):
    """从严格规范JSON恢复完整原定位，复用CAN定位模型，不解析DBC。

    参数: text为LegacyCANField.key生成的原生str，UTF-8包不超过65536字节。
    返回: LegacyCANField，保信号名大小写、点号及可选帧类型，不读取DBC。
    异常: TypeError/ValueError/UnicodeError为类型、JSON、重复键、字段、数值或非规范键；
        不接受仅语义相同但空白、键序或转义不同的文本，不eval或反序列化任意对象。
    """
    if type(text) is not str:
        raise TypeError('CAN field需要规范JSON str')
    # 先以字符数拒绝明显超长输入，再核UTF-8字节、JSON树和唯一定位字段。
    if not text or len(text) > MAX_WIRE_BYTES:
        raise ValueError('CAN field为空或超过wire上限')
    field = field_from_dict(decode_packet(text.encode('utf-8')))
    if text != field.key:
        raise ValueError('CAN field不是规范JSON定位键')
    return field


@dataclass(frozen=True)
class LegacyCANSpec:
    """冻结有序同格式BLF、单通道和单DBC声明，不认证输入文件或实际旧链能力。"""

    name: str  # 当前计划来源的安全简单名称，不是DBC消息名。
    path: Path  # 首个BLF声明；不扫描目录，连续文件由paths显式提供。
    dbc_path: Path  # 同次worker原load_file的唯一DBC声明，不在此读取。
    channel: int  # 明确单通道，非负原生int，不猜缺失通道。
    timebase: TimebaseSpec  # 完整时基声明，来源名称相同不自动证明同步。
    unit: str = 's'  # 原函数返回浮点秒，首版只接受s，不按文件名推断。
    offset_ns: int = 0  # 明确int64固定纳秒偏移，不更改原timestamp。
    legacy_profile: str = PROFILE_ID  # 唯一冻结sclicer-functions-v1，不自动回退profile。
    decode_scope: str = 'requested'  # 默认仅处理本次实际需要的报文/字段；all显式保留完整诊断。
    input_check: str = 'auto'  # auto按实际消费者检查；full显式检查全部原帧和时间。

    paths: tuple[Path, ...] = ()  # 显式连续BLF；空tuple沿用path单文件，首项必须等于path。
    decode_policy: str = 'legacy'  # 新版本默认strict；旧调用保原宽松解码。

    @property
    def input_paths(self):
        """取得原序文件。参数: 无。返回: tuple。异常: 无；不扫描目录。"""
        return self.paths or (self.path,)

    def __post_init__(self):
        """检查静态来源约束，路径和时基对象均原样保留。

        参数: 无，读取本冻结声明字段。返回: None。
        异常: TypeError为路径/通道/时基/单位/profile/偏移/解码范围类型错误；ValueError为名称、
            后缀、通道、单位、profile或解码/检查范围不符；OverflowError为offset_ns超出int64。
        副作用: 无open/stat/resolve/DBC/依赖加载，不核实存在性或实际BLF内容。
        """
        require_identifier(self.name, 'can.name')
        # 后缀只限定本次支持范围；DBC保Path，不额外猜格式、改路径或检查内容。
        if not isinstance(self.path, Path) or not isinstance(self.dbc_path, Path):
            raise TypeError('CAN path/dbc_path需要Path')
        if self.path.suffix.lower() != '.blf':
            raise ValueError('首版CAN仅声明单BLF来源')
        from ..legacy.decode_policy import validate_decode_policy
        validate_decode_policy(self.decode_policy)
        if (type(self.paths) is not tuple or len(self.paths) > 4096
                or any(not isinstance(p, Path) or p.suffix.lower() != '.blf' for p in self.paths)
                or self.paths and self.paths[0] != self.path):
            raise ValueError('连续BLF需要原序Path tuple且首项等于path')
        _nonnegative_integer(self.channel, 'can.channel')
        if not isinstance(self.timebase, TimebaseSpec):
            raise TypeError('CAN timebase需要TimebaseSpec')
        if type(self.unit) is not str or type(self.legacy_profile) is not str:
            raise TypeError('CAN unit/legacy_profile需要原生str')
        if self.unit != 's' or self.legacy_profile != PROFILE_ID:
            raise ValueError('CAN仅支持原浮点秒与sclicer-functions-v1')
        # 通用时间校验允许其他Integral；此静态契约额外要求原生int而非隐式归一化。
        if type(self.offset_ns) is not int:
            raise TypeError('CAN offset_ns需要原生int')
        require_int64_ns(self.offset_ns, 'can.offset_ns')
        # 本模型只检查选项值；requested与整个计划的兼容性由静态规划统一检查。
        if type(self.decode_scope) is not str:
            raise TypeError('CAN decode_scope需要原生str')
        if self.decode_scope not in ('all', 'requested'):
            raise ValueError('CAN decode_scope需要all或requested')
        # 检查策略与解码范围分开；完整计划负责确定实际时间消费者。
        if type(self.input_check) is not str:
            raise TypeError('CAN input_check需要原生str')
        if self.input_check not in ('auto', 'full'):
            raise ValueError('CAN input_check需要auto或full')


@dataclass(frozen=True)
class CANSourceRef(SourceRef):
    """保留一次原yield对应样本的CAN身份，不替代实际绑定或质量检查。

    继承session_id/source_name/field；实际定位须满足field声明的可选类型约束。
    yield_sequence从0开始且保原来源顺序，同刻消息不会被去重；不是物理行号。
    原timestamp和量化标志同时保留，不用新纳秒坐标覆盖原浮点诊断。
    """

    path: str  # 原单BLF路径文本，是否真实打开由实际read证明。
    profile: str  # 实际固定旧函数链标识。
    channel: int  # 明确来源通道。
    signal: str  # 原DBC信号名，不裁剪、替换点号或改大小写。
    frame_id: int  # 原报文ID，与field一致。
    is_extended: bool  # 原定位标准/扩展帧标志。
    is_fd: bool  # 原定位经典CAN/FD标志。
    yield_sequence: int  # 0起原函数yield序号，不是legacy_sum的历史求值序号。
    timestamp: float  # 有限原浮点秒，可保负数和-0.0；精度已损失时不能恢复。
    time_quantized: bool  # 显式时间转换是否按纳秒量化，不等于浮点精度完好。

    def __post_init__(self):
        """校验通用身份与完整原定位相等，不访问路径或重新解码。

        参数: 无。返回: None，全部原声明保持冻结。
        异常: TypeError/ValueError/UnicodeError为身份、profile、JSON定位、序号、原时间
            或量化标志非法，或field与附加定位冲突；没有失效补零或隐式别名。
        """
        super().__post_init__()
        require_text(self.path, 'can_ref.path')
        if type(self.profile) is not str or self.profile != PROFILE_ID:
            raise ValueError('CANSourceRef仅支持sclicer-functions-v1')
        # field保留用户的可选选择器，附加帧类型记录实际帧；无需逐条重新解析JSON。
        _nonnegative_integer(self.channel, 'can_ref.channel')
        if type(self.frame_id) is not int or type(self.signal) is not str:
            raise TypeError('CANSourceRef实际ID需要int、信号名需要str')
        if type(self.is_extended) is not bool or type(self.is_fd) is not bool:
            raise TypeError('CANSourceRef必须保存实际帧类型bool')
        actual = LegacyCANField(self.channel, self.signal, self.frame_id, self.is_extended, self.is_fd).key
        # 规范键按名称排序，这两个字段都在signal之前；只删除完整键值及逗号。
        # 信号文本中的双引号会被JSON转义，因此不能误删文本中的相似片段。
        extended = '"is_extended":' + str(self.is_extended).lower() + ','
        fd = '"is_fd":' + str(self.is_fd).lower() + ','
        if type(self.field) is not str or self.field not in (
                actual, actual.replace(extended, ''), actual.replace(fd, ''),
                actual.replace(extended, '').replace(fd, '')):
            raise ValueError('CANSourceRef实际帧与绑定定位不一致')
        _nonnegative_integer(self.yield_sequence, 'can_ref.yield_sequence')
        if type(self.timestamp) is not float:
            raise TypeError('CANSourceRef timestamp需要原生float秒')
        if not isfinite(self.timestamp):
            raise ValueError('CANSourceRef timestamp必须有限')
        if type(self.time_quantized) is not bool:
            raise TypeError('CANSourceRef time_quantized需要bool')

    @property
    def evaluation_index(self):
        """提供本次原yield位置的只读别名，明确不声称legacy_sum求值流已存在。

        参数: 无。返回: 与yield_sequence完全相同的int。异常: 无；不产生额外求值或计数。
        """
        return self.yield_sequence
