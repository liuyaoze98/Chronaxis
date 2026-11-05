"""编码和严格解码当前扁平结果JSONL；内部叶子格式另用于历史和导出。

公开结果只登记当前行类型和编号。内部_pack/_unpack保留整数、tuple、枚举、
来源与非有限诊断标记；它们不提供旧结果包装或公开v1—v6读取。
最大行字节与递归深度显式限制；调用方须先预留编码与解析临时空间。"""

# 只访问登记dataclass字段，不开放表达式对象访问或反射导入。
from dataclasses import fields
from enum import Enum
import json
from math import isfinite
from sys import getsizeof
from ..core.models import Interval, SourceRef
from ..core.numeric import ScalarValue
from ..core.calculations import CalculationResult, CalculationDefinition
from ..core.selection import SelectionRow
from ..core.temporal import Event, TemporalRule
from ..core.sequence import SequenceRule, SequenceResult
from ..core.windows import Segment, WindowSpec
from ..core.types import QualityFlag, SignalDType, Truth
# CSV实际定位需要完整具体字段；只登记冻结协议，不打开来源或引入reader。
from ..sources.csv_spec import CSVSourceRef
# CAN引用只导入冻结位置模型，不加载原reader/DBC或产生额外扫描。
from ..sources.can_spec import CANSourceRef
from ..sources.text_can_ref import CANTextSourceRef
from .rows import ResultRow, row_table
from .errors import ResultFormatError
from .summary import SummaryCalculationRow, SUMMARY_FIELDS, summary_fields, SUMMARY_MODELS
# 行类型各有固定编号；只接受当前登记的格式，不提供旧版本解码。
_SUMMARY_VERSIONS = {version:(model,names) for model,(_,names,version) in SUMMARY_MODELS.items()}
_MODELS = {cls.__name__: cls for cls in (Interval, SourceRef, CSVSourceRef, CANSourceRef, CANTextSourceRef, ScalarValue, CalculationDefinition,
           CalculationResult, SelectionRow, Event, TemporalRule, Segment, WindowSpec,
           SequenceRule, SequenceResult)}
_ENUMS = {cls.__name__: cls for cls in (QualityFlag, SignalDType, Truth)}
def _pack(value, depth: int = 0):
    """递归编码固定模型、枚举、tuple和原生标量。

    参数: value为白名单树，depth为递归深度。返回: 仅JSON结构的树。
    异常: ResultFormatError表示类型或深度不受支持。
    """
    # 深度限制避免异常嵌套占用无界栈；序列长度由调用侧RAM预估限制。
    try:
        if depth > 32:
            raise ResultFormatError('结果行嵌套超过32层')
        value_type = type(value)
        # 原生叶子直接处理；无效数值仍保留诊断标签，不能变成普通JSON非有限值。
        if value_type is float and not isfinite(value):
            return {'diagnostic_float': 'nan' if value != value else 'inf' if value > 0 else '-inf'}
        if value is None or value_type in (str, int, bool, float):
            return value
        if isinstance(value, Enum) and type(value).__name__ in _ENUMS and type(value) is _ENUMS[type(value).__name__]:
            return {'enum': type(value).__name__, 'value': value.value}
        if type(value).__name__ in _MODELS and type(value) is _MODELS[type(value).__name__]:
            packed = {}
            for field in fields(value):
                if value_type is ScalarValue and field.name == 'code' and value.code is None:
                    continue  # 未请求的码视图不改变原始记录格式。
                if value_type is ScalarValue and field.name == 'partial' and not value.partial:
                    continue  # 完整标量仍写原格式，只有部分估算需要额外标记。
                if field.init:
                    packed[field.name] = _pack(getattr(value, field.name), depth + 1)
            return {'model': type(value).__name__, 'fields': packed}
        if type(value) is tuple:
            packed = []
            for item in value:
                packed.append(_pack(item, depth + 1))
            return {'tuple': packed}
        raise ResultFormatError(f'结果行含未注册类型{type(value).__name__}')
    finally:
        # 显式循环不留下comprehension迭代器；失败TB只断本层参数/新容器。
        value = packed = items = kwargs = field = key = item = None
        value_type = None


def _unpack(value, depth: int = 0):
    """只从已登记标签重建冻结对象。

    参数: value为解析结构，depth为深度。返回: typed值。
    异常: ResultFormatError/TypeError/ValueError为结构或模型校验错误。
    """
    # 未标记数组/对象不得绕过tuple和模型校验。
    try:
        if depth > 32:
            raise ResultFormatError('结果行嵌套超过32层')
        # JSON的1e999也会被解析为Inf，不能绕过明确诊断标签。
        if type(value) is float and not isfinite(value):
            raise ResultFormatError('非有限结果必须使用诊断标签')
        if value is None or type(value) in (str, int, bool, float):
            return value
        if type(value) is not dict:
            raise ResultFormatError('结果结构需要明确类型标签')
        if set(value) == {'tuple'} and type(value['tuple']) is list:
            items = []
            for item in value['tuple']:
                items.append(_unpack(item, depth + 1))
            return tuple(items)
        if set(value) == {'diagnostic_float'} and value['diagnostic_float'] in ('nan', 'inf', '-inf'):
            return float(value['diagnostic_float'])
        if set(value) == {'enum', 'value'} and value['enum'] in _ENUMS:
            # enum原始值不能用bool冒充质量位整数。
            expected = int if value['enum'] == 'QualityFlag' else str
            if type(value['value']) is not expected:
                raise ResultFormatError('枚举底层值类型错误')
            return _ENUMS[value['enum']](value['value'])
        if set(value) == {'model', 'fields'} and value['model'] in _MODELS and type(value['fields']) is dict:
            cls = _MODELS[value['model']]
            expected = {field.name for field in fields(cls) if field.init}
            if cls is ScalarValue and 'code' not in value['fields']:
                expected.discard('code')
            if cls is ScalarValue and 'partial' not in value['fields']:
                expected.discard('partial')
            if set(value['fields']) != expected:
                raise ResultFormatError('结果模型字段缺失或出现未知字段')
            kwargs = {}
            for key, item in value['fields'].items():
                kwargs[key] = _unpack(item, depth + 1)
            return cls(**kwargs)
        raise ResultFormatError('未知或多余结果类型标签')
    finally:
        # 显式循环不留下comprehension迭代器；失败TB只断本层参数/新容器。
        value = packed = items = kwargs = field = key = item = None


def _unique_object(pairs):
    """拒绝重复JSON键，避免解析时后值覆盖前值。

    参数: pairs为JSON对象键值对。返回: dict。
    异常: ResultFormatError为重复字段。
    """
    # 精确键检查覆盖外层版本和所有嵌套对象。
    try:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ResultFormatError(f'结果JSON重复键{key}')
            result[key] = value
        return result
    finally:
        # 显式循环不留下comprehension迭代器；失败TB只断本层参数/新容器。
        pairs = result = key = value = None










def _reject_constant(value):
    """拒绝非标准JSON NaN/Infinity，诊断只能使用明确标签。

    参数: value为解析器识别的常量名。返回: 无。
    异常: ResultFormatError始终抛出。
    """
    raise ResultFormatError(f'结果JSON含非法数值{value}')


def estimate_row_bytes(row: ResultRow) -> int:
    """保守估计结果树、JSON转换与编码期间的新层RAM开销。

    参数: row为冻结行。返回: 正整数bytes估算，含容器/标签和字符串转义余量。
    异常: ResultFormatError为未登记类型或过深结构；不测量全进程RSS。
    """
    # 先确认根类型；递归只观察既有输入，不复制完整树。
    row_table(row)
    if type(row) is SummaryCalculationRow:
        return (getsizeof(row) + sum(256 + getsizeof(getattr(row, name)) for name in SUMMARY_FIELDS))*16 + 8192
    return _estimate(row) * 16 + 8192


def _estimate(value, depth: int = 0) -> int:
    """累计原生对象及字段容器成本，重复引用也保守重复计数。

    参数: value为固定树，depth为深度。返回: 基础bytes估算。
    异常: ResultFormatError为类型/深度不支持。
    """
    if depth > 32:
        raise ResultFormatError('结果行嵌套超过32层')
    value_type = type(value)
    if value is None or value_type in (str, int, bool, float):
        return getsizeof(value) + 64
    # 字段键与临时dict的开销按每字段256bytes留余量。
    if type(value) in SUMMARY_MODELS or (type(value).__name__ in _MODELS and type(value) is _MODELS[type(value).__name__]):
        return getsizeof(value) + sum(256 + _estimate(getattr(value, field.name), depth + 1)
                                    for field in fields(value) if field.init and
                                    not (value_type is ScalarValue and
                                         (field.name=='code' and value.code is None or field.name=='partial' and not value.partial)))
    if type(value) is tuple:
        return getsizeof(value) + sum(_estimate(item, depth + 1) + 32 for item in value)
    if isinstance(value, Enum) and type(value).__name__ in _ENUMS:
        return 512
    raise ResultFormatError('不能估算未登记结果对象')


def encode_row(row: ResultRow, max_bytes: int) -> bytes:
    """生成一条确定JSONL，包含行结束符且限制字节数。

    参数: row为typed行；max_bytes为正原生int。
    返回: UTF-8 bytes，整数不经过浮点数转换。
    异常: ResultFormatError/ValueError为类型、大小或格式错误。
    """
    # 限额由资源账本给出；此函数不自行声称RAM已预留。
    try:
        row_table(row)
        if type(max_bytes) is not int or max_bytes <= 0:
            raise ValueError('max_bytes需正原生int')
        packed = {'row_schema_version': SUMMARY_MODELS[type(row)][2], 'row': summary_fields(row)}
        payload = (json.dumps(packed, ensure_ascii=False, allow_nan=False, sort_keys=True,
                              separators=(',', ':')) + '\n').encode('utf-8')
        if len(payload) > max_bytes:
            raise ResultFormatError('结果行超过max_bytes')
        return payload
    finally:
        # 原异常/TB和返回值保持；只断本层临时引用，不清调用方帧。
        packed = payload = row = None


def decode_row(payload: bytes, max_bytes: int) -> ResultRow:
    """从单行版本化JSONL恢复并重新校验所有模型。

    参数: payload为UTF-8 bytes；max_bytes为正原生int。
    返回: 当前登记的平坦结果行；旧版本1—6不再读取。
    异常: ResultFormatError为解析/版本/模型错误，ValueError为限额配置错误。
    """
    try:
        if type(max_bytes) is not int or max_bytes <= 0:
            raise ValueError('max_bytes需正原生int')
        if type(payload) is not bytes or len(payload) > max_bytes:
            raise ResultFormatError('结果行类型或字节限额错误')
        try:
            # 禁止重复键、隐式非有限值和未知外层字段。
            packed = json.loads(payload, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
            if type(packed) is not dict or set(packed) != {'row_schema_version', 'row'}:
                raise ResultFormatError('结果行外层字段错误')
            version = packed['row_schema_version']
            if type(version) is int and version in _SUMMARY_VERSIONS:
                model, names = _SUMMARY_VERSIONS[version]
                fields_ = packed['row']
                if (type(fields_) is not dict or set(fields_) != set(names)
                        or type(fields_['quality']) is not int or fields_['quality'] < 0):
                    raise ResultFormatError('结果字段集合或质量类型错误')
                fields_['quality'] = QualityFlag(fields_['quality'])
                if version == 15:
                    for name in ('group_keys','group_values'):
                        if type(fields_[name]) is not list:
                            raise ResultFormatError('聚合分组字段需要JSON数组')
                        fields_[name]=tuple(fields_[name])
                if version==11:
                    if type(fields_['parent_event_ids']) is not list:
                        raise ResultFormatError('片段父ID需要JSON数组')
                    fields_['parent_event_ids']=tuple(fields_['parent_event_ids'])
                return model(**fields_)
            raise ResultFormatError('不支持的结果行版本')
        except (ValueError, TypeError, OverflowError, RecursionError, UnicodeError) as exc:
            # 保留原模型报错原因，不吞异常或给出正常零。
            raise ResultFormatError(f'结果行无法解析: {exc}') from exc
    finally:
        # 原异常/TB和返回值保持；只断本层临时引用，不清调用方帧。
        packed = payload = row = fields_ = None
