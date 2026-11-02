"""定义已解码历史记录与严格JSONL格式，不再次归一化数值。

样本同时保存物理数组值、逻辑ScalarValue和可选原诊断，时间/序号保持整数。
进度记录保留空批、watermark和整个来源EOF；None观测终点不补齐。
编码复用结果层固定白名单标签，不注册动态类或允许任意对象反序列化。
格式只用于新执行层历史，不修改分析计划schema或旧读写格式。
"""

# 标准库冻结模型及严格JSON；共享既有标量验证与固定类型编码。
from dataclasses import dataclass
from math import isfinite
import json
from ..core.models import SourceRef, SignalSample, require_identifier, require_scalar
from ..sources.csv_spec import CSVSourceRef
from ..sources.can_spec import CANSourceRef
from ..sources.text_can_ref import CANTextSourceRef
from ..core.numeric import ScalarValue
from .record_sample import RecordSample
from ..timebase.conversion import require_int64_ns
from ..core.types import SignalDType
from ..results.codec import _pack, _unpack, _unique_object, _reject_constant, _estimate
from ..results.errors import ResultFormatError


@dataclass(frozen=True)
class HistorySample:
    """保存单个已归一化观测；array_value不被用来推断有效性。

value携带逻辑值、类型、掩码和质量，ENUM正常值是标签文本；array_value保留整数编码。
original_present区分没有原诊断列与该列中的真实None，原诊断允许非有限浮点。
batch_index只标识传输批次，不作为事件身份或绑定身份。
"""

    batch_index: int
    name: str
    time_ns: int
    sequence: int
    array_value: int | float | bool
    value: ScalarValue
    unit: str
    source_ref: SourceRef
    original_present: bool
    original_value: int | float | bool | str | None

    def __post_init__(self) -> None:
        """验证物理/逻辑值、身份和原诊断，不做scale或offset转换。

        参数: 无；读取冻结字段。返回: None。
        异常: TypeError/ValueError/OverflowError为记录矛盾或非法标量。
        """
        # 批次号为非负原生整数，不能用bool或任意精度增长隐藏开销。
        if type(self.batch_index) is not int or not 0 <= self.batch_index < 2 ** 63:
            raise ValueError('历史batch_index需要非负int64')
        if not isinstance(self.value, ScalarValue) or type(self.unit) is not str:
            raise TypeError('历史需要ScalarValue和字符串单位')
        # 核心样本检查时间、别名、原序号、质量与来源；不依赖某一数值后端。
        SignalSample(self.name, self.time_ns, self.value.value, self.value.valid,
                     self.value.quality, self.source_ref, self.sequence)
        expected = {SignalDType.INT64: int, SignalDType.UINT64: int,
                    SignalDType.FLOAT64: float, SignalDType.BOOL: bool, SignalDType.ENUM: int}[self.value.dtype]
        if type(self.array_value) is not expected or (type(self.array_value) is float and not isfinite(self.array_value)):
            raise TypeError('历史物理值必须符合固定数组类型且有限')
        # 数组即使无效也具有合法物理类型；无效占位仍由valid/quality明确解释。
        physical_dtype = SignalDType.INT64 if self.value.dtype is SignalDType.ENUM else self.value.dtype
        ScalarValue(self.array_value, physical_dtype)
        if self.value.valid:
            logical = self.value.labels[self.array_value] if self.value.dtype is SignalDType.ENUM and 0 <= self.array_value < len(self.value.labels) else self.array_value
            if type(logical) is not type(self.value.value) or logical != self.value.value:
                raise ValueError('历史物理值与正常逻辑值矛盾')
        # 原诊断存在性必须独立，不能把None强制解释为缺列。
        if type(self.original_present) is not bool:
            raise TypeError('original_present需要bool')
        require_scalar(self.original_value)
        if not self.original_present and self.original_value is not None:
            raise ValueError('缺原诊断列时不能附带诊断值')


@dataclass(frozen=True)
class HistoryProgress:
    """保存一批结束时的读取事实，sample_count包含该批所有信号列。"""

    batch_index: int
    source: str
    session_id: str
    sample_count: int
    watermark_ns: int | None
    source_eof: bool
    observed_end_ns: int | None

    def __post_init__(self) -> None:
        """校验计数、身份和可未知的观测/进度坐标。

        参数: 无；读取全部字段。返回: None。
        异常: TypeError/ValueError/OverflowError为记录结构或时间错误。
        """
        # 空批合法，计数不能为负，也不能把bool当成1。
        for count in (self.batch_index, self.sample_count):
            if type(count) is not int or not 0 <= count < 2 ** 63:
                raise ValueError('历史计数需要非负int64')
        require_identifier(self.source, 'history.source')
        require_identifier(self.session_id, 'history.session_id')
        if type(self.source_eof) is not bool:
            raise TypeError('source_eof需要bool')
        for time in (self.watermark_ns, self.observed_end_ns):
            if time is not None:
                require_int64_ns(time)


HistoryRecord = HistorySample | HistoryProgress


def record_values(record: HistoryRecord) -> tuple:
    """按固定字段顺序提取白名单值，不将dataclass变成动态对象格式。

    参数: record为两种历史记录之一。返回: 字段tuple。
    异常: TypeError为未支持记录。
    """
    # 类型必须精确，不支持子类扩展隐式改变格式。
    if type(record) is HistorySample:
        # CSV位置使用历史层固定标签，基础来源仍沿用v1；不扩大结果模型注册表。
        reference = record.source_ref
        if type(reference) is CSVSourceRef:
            reference = ('csv_source_ref', SourceRef(reference.session_id, reference.source_name, reference.field),
                         reference.path, reference.line_number, reference.time_text,
                         reference.value_text, reference.time_quantized)
        elif type(reference) is CANSourceRef:
            # CAN v3使用固定原帧位置；不把原yield序号误当文件物理行号。
            reference = ('can_source_ref', SourceRef(reference.session_id, reference.source_name, reference.field),
                         reference.path, reference.profile, reference.channel,
                         reference.signal, reference.frame_id, reference.is_extended, reference.is_fd,
                         reference.yield_sequence, reference.timestamp, reference.time_quantized)
        elif type(reference) is CANTextSourceRef:
            # 新文本引用单列v4，物理行与原时间不可降级成旧浮点秒定位。
            reference = ('text_can_source_ref', SourceRef(reference.session_id, reference.source_name, reference.field),
                         reference.path, reference.parser_version, reference.line_number,
                         reference.input_index, reference.record_sequence, reference.yield_sequence,
                         reference.raw_time, reference.time_quantized)
        return (record.batch_index, record.name, record.time_ns, record.sequence,
                record.array_value, record.value, record.unit, reference,
                record.original_present, record.original_value)
    if type(record) is HistoryProgress:
        return (record.batch_index, record.source, record.session_id, record.sample_count,
                record.watermark_ns, record.source_eof, record.observed_end_ns)
    raise TypeError('未知历史记录类型')


def estimate_record_bytes(record: HistoryRecord) -> int:
    """保守估算一行装箱、JSON结构和UTF8副本的临时RAM。

    参数: record为已检查记录。返回: bytes估算，非全进程RSS。
    异常: 类型或深度错误传播。
    """
    # 系数覆盖Python容器、unicode及编码副本，长文本不按固定小行估计。
    if type(record) is RecordSample:
        return _estimate((record.name,record.time_ns,record.sequence,record.value,record.unit,record.source_ref,record.enum_code))*16+4096
    return _estimate(record_values(record)) * 16 + 8192


def encode_record(record: HistoryRecord, max_bytes: int) -> bytes:
    """编码一条历史JSONL；基础v1、信号CSV v2、旧CAN v3、文本CAN v4。

    参数: record为typed记录，max_bytes为单行上限。返回: 含换行UTF8 bytes。
    异常: ResultFormatError为超长/不支持结构。
    """
    # 固定record_type与版本，复用封闭模型标签；非有限诊断使用明确标签。
    reference_type = type(record.source_ref) if type(record) is HistorySample else None
    version = (4 if reference_type is CANTextSourceRef else 3 if reference_type is CANSourceRef
               else 2 if reference_type is CSVSourceRef else 1)
    packed = {'history_version': version, 'record_type': 'sample' if type(record) is HistorySample else 'progress',
              'values': _pack(record_values(record))}
    payload = (json.dumps(packed, ensure_ascii=False, allow_nan=False, separators=(',', ':'), sort_keys=True) + '\n').encode('utf-8')
    if len(payload) > max_bytes:
        raise ResultFormatError('历史单行超过有限读取上限')
    return payload


def decode_record(payload: bytes, max_bytes: int) -> HistoryRecord:
    """严格重建单行typed记录，拒绝重复键、额外字段和损坏换行。

    参数: payload为含换行UTF8行，max_bytes为上限。返回: HistoryRecord。
    异常: ResultFormatError并保留原格式/模型异常链。
    """
    # readline由调用侧限长；这里再核对完整边界，不接收最后的半行。
    if len(payload) > max_bytes or not payload.endswith(b'\n'):
        raise ResultFormatError('历史行过长或未完整写入')
    try:
        packed = json.loads(payload, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        if type(packed) is not dict or set(packed) != {'history_version', 'record_type', 'values'} or type(packed['history_version']) is not int or packed['history_version'] not in (1, 2, 3, 4):
            raise ResultFormatError('历史版本或字段错误')
        values = _unpack(packed['values'])
        cls = {'sample': HistorySample, 'progress': HistoryProgress}.get(packed['record_type'])
        if cls is None or type(values) is not tuple:
            raise ResultFormatError('历史record_type或值容器错误')
        if packed['history_version'] == 2:
            # v2只能是明确CSV样本，未知标签/额外定位字段不能降级成基础来源。
            if cls is not HistorySample or len(values) != 10 or type(values[7]) is not tuple or len(values[7]) != 7 or values[7][0] != 'csv_source_ref' or type(values[7][1]) is not SourceRef:
                raise ResultFormatError('历史v2需要完整CSV固定定位')
            base = values[7][1]
            reference = CSVSourceRef(base.session_id, base.source_name, base.field, *values[7][2:])
            values = values[:7] + (reference,) + values[8:]
        elif packed['history_version'] == 3:
            # 固定tag、长度和基础身份齐全才恢复CAN，禁止退化或混用CSV标签。
            if (cls is not HistorySample or len(values) != 10 or type(values[7]) is not tuple
                    or len(values[7]) != 12 or values[7][0] != 'can_source_ref'
                    or type(values[7][1]) is not SourceRef):
                raise ResultFormatError('历史v3需要完整CAN固定定位')
            base = values[7][1]
            reference = CANSourceRef(base.session_id, base.source_name, base.field, *values[7][2:])
            values = values[:7] + (reference,) + values[8:]
        elif packed['history_version'] == 4:
            # 精确固定字段重建，禁止旧CAN/CSV引用换版本冒充文本物理行。
            if (cls is not HistorySample or len(values) != 10 or type(values[7]) is not tuple
                    or len(values[7]) != 10 or values[7][0] != 'text_can_source_ref'
                    or type(values[7][1]) is not SourceRef):
                raise ResultFormatError('历史v4需要完整文本CAN定位')
            base = values[7][1]
            reference = CANTextSourceRef(base.session_id, base.source_name, base.field, *values[7][2:])
            values = values[:7] + (reference,) + values[8:]
        elif cls is HistorySample and len(values) == 10 and type(values[7]) in (CANSourceRef,CANTextSourceRef):
            # 结果模型注册不能为历史v1另开CAN入口；CAN仅接受上述v3固定定位。
            raise ResultFormatError('CAN历史定位必须使用对应v3/v4固定格式')
        return cls(*values)
    except (TypeError, ValueError, OverflowError, UnicodeError, KeyError, IndexError) as exc:
        # 不把坏行当空批跳过，保留具体解析原因。
        raise ResultFormatError('历史记录结构/模型非法') from exc
