"""把显式信号定义转成来源的静态字段描述。

输入是来源名称、SignalDefinition元组和可选定位信息，输出FieldDescription
元组。每项保留表达式别名、原字段、输出类型与单位，并保存转换、有效期、
可选语义、方向、测量位置和枚举标签。内存来源与已解码CSV共用该转换。
本模块不读取输入文件或DBC，也不核实声明是否与实际表头或物理测量一致。
"""

# 自由元数据仍使用JSON结构，类型在模型边界深冻结。
from collections.abc import Mapping
# 完整配置契约只保存稳定摘要，避免把原无效NaN等塞进JSON元数据。
from hashlib import sha256
# 明确绑定定义是已验收的配置契约。
from ..core.binding import SignalDefinition, _identity
from ..core.models import TimebaseSpec
from ..timebase.conversion import require_int64_ns
# enum固定域由声明提供，不能在batch内猜测。
from ..core.types import SignalDType
# 公开字段描述保留原定位，与表达式别名分开。
from .models import FieldDescription, FieldLocation, JsonValue


def source_timebase_identity(timebase: TimebaseSpec, offset_ns: int) -> str:
    """为实际适配器使用的时基种类/原点/固定偏移生成独立摘要。

    参数: timebase已校验TimebaseSpec；offset_ns为整数纳秒偏移。
    返回: SHA256文本，仅标识配置，不证明物理时钟同步已核实。
    异常: TypeError/OverflowError为未声明时基或非法偏移；不读取输入。
    """
    if not isinstance(timebase, TimebaseSpec):
        raise TypeError('时基身份需要TimebaseSpec')
    offset = require_int64_ns(offset_ns, 'source.offset_ns')
    # 单凭相同ID不能证明相同起点；完整原点/种类进入配置指纹。
    payload = ('source-timebase-v1', timebase.timebase_id, timebase.time_type.value, timebase.origin, offset)
    return sha256(_identity(payload).encode('utf-8')).hexdigest()


def describe_fields(source: str, signals: tuple[SignalDefinition, ...], locator: Mapping[str, JsonValue] | None = None) -> tuple[FieldDescription, ...]:
    """逐项保存字段定位和转换声明，不把声明当作实际数据核实。

    参数:
        source (str): 当前来源名称。
        signals (tuple[SignalDefinition, ...]): 该来源已解析的显式信号定义。
        locator (Mapping | None): 可附加的静态定位信息，默认None，使用空对象。
    返回:
        tuple[FieldDescription, ...]。保持定义顺序，元数据和定位映射深度冻结。
        valid_for_ns是有效值最多保持的时长声明；本函数不在此执行保持或过期判断。
        原始CAN的None表示等待同次DBC周期解析，不表示无限保持。
    异常:
        TypeError或ValueError: 字段描述或定位信息不符合公共模型要求。
    副作用:
        无输入扫描；同一原字段的多个别名分别保留自己的显式转换。
    """
    # 未给定位时为空对象，不从路径猜通道/消息或工程语义。
    location = {} if locator is None else locator
    # 每别名描述自己的转换，允许同原字段显式不同映射。
    return tuple(FieldDescription(item.name, FieldLocation(source, item.field, location), item.dtype, item.unit,
                                  {'normalization_sha256': sha256(_identity(('normalization-v1', item.identity())).encode('utf-8')).hexdigest(),
                                   'input_unit': item.input_unit, 'scale': item.scale, 'offset': item.offset,
                                   'valid_for_ns': item.valid_for_ns, 'semantic_id': item.semantic_id, 'unit_status': item.unit_status,
                                   'mapping_version': item.mapping_version, 'semantic_contract_version': item.semantic_contract_version,
                                   'sign_convention': item.sign_convention, 'input_sign_convention': item.input_sign_convention,
                                   'direction_factor': item.direction_factor, 'measurement_location': item.measurement_location,
                                   'same_time_policy': item.same_time_policy,
                                   'labels': tuple(dict.fromkeys(label for _, label in item.choices)) if item.dtype is SignalDType.ENUM else ()}) for item in signals)
