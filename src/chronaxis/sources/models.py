"""定义分析层接收的来源描述、读取请求和独立信号批次。

调用者提供来源元数据和已经归一化的信号数组，本模块检查名称、类型、
时间、序号与质量，再输出冻结模型。数组复制为模型自身拥有的只读数据，
嵌套元数据深度复制为只读映射和元组；不读取文件或DBC，也不注册全局来源。

SignalSeries只表示一次传输中的一列，区别于core.state中的完整内存历史。
每列允许为空，时间非递减，同时间更新完整保留；跨批身份和完整时间组
由BatchValidator及后续执行层处理。valid是有效性掩码，quality保存无效
原因；无效值的存储占位不能参与正常计算，original_values可另存原始诊断。
nbytes只统计五个数值数组的存储，Python容器和全任务预算须另外核算。
"""

# 标准库冻结结构和JSON元数据，元数据不含任意可执行对象。
from collections.abc import Mapping
# 数据类字段冻结不替代数组所有权与内容校验。
from dataclasses import dataclass, field
# JSON浮点元数据必须有限，原始无效样本另有专用诊断字段。
from math import isfinite
# 深冻结断开调用者后续字典修改。
from types import MappingProxyType
# 联合类型表明元数据不是无类型object占位。
from typing import TypeAlias
# NumPy只负责列布局，不负责CAN解码。
import numpy as np

# 原样本身份和半开范围使用既有已验证逻辑模型。
from ..core.models import Interval, SourceRef
# 复用数组结构校验，不把其数值计算作为独立参考内核。
from ..core.numeric_numpy import NumericArray
# dtype和质量是通用类型，来源模型不绑定业务信号名称。
from ..core.types import SignalDType
# 共享名称/不可变标量校验，不隐式cast错误输入。
from ..core.validation import require_identifier, require_scalar, require_text
# 所有观测和watermark坐标均为明确int64纳秒。
from ..timebase.conversion import require_int64_ns

# 冻结后的自由元数据只包含JSON标量、tuple数组和字符串键Mapping。
JsonValue: TypeAlias = str | int | float | bool | None | tuple['JsonValue', ...] | Mapping[str, 'JsonValue']


def freeze_metadata(value: JsonValue) -> JsonValue:
    """递归复制JSON元数据，避免共享调用者的可变容器。

    参数:
        value (JsonValue): JSON标量、字符串键映射、list或tuple；不接受任意对象。
    返回:
        JsonValue。映射变为新的只读Mapping，数组变为tuple，标量保持原值。
    异常:
        TypeError: 出现非JSON对象或非字符串键。
        ValueError: 浮点元数据包含NaN或无穷值。
    副作用:
        无。复制容器，不修改传入结构。
    """
    # JSON对象逐层冻结，不能仅冻结外层而共享嵌套字典。
    if isinstance(value, Mapping):
        # 所有键必须原生字符串，不把整数键静默变成文本。
        if any(type(key) is not str for key in value):
            # 与字段定位及JSON序列化含义保持一致。
            raise TypeError('metadata键必须为字符串')
        # 新字典与调用者脱离；递归只接受明确JSON类型。
        return MappingProxyType({key: freeze_metadata(item) for key, item in value.items()})
    # 元数据数组冻结为tuple，不产生object数值数组。
    if type(value) in (list, tuple):
        # 顺序是元数据身份，不能排序或去重。
        return tuple(freeze_metadata(item) for item in value)
    # 只有原生JSON标量可保留；bool与int分别明确支持。
    if type(value) not in (str, int, float, bool, type(None)):
        # 禁止任意对象repr或反射序列化。
        raise TypeError('metadata仅接受JSON类型')
    # JSON数值不能包含NaN/Infinity，避免清单不兼容。
    if type(value) is float and not isfinite(value):
        # 无效采样值不通过metadata伪装正常配置。
        raise ValueError('metadata浮点必须有限')
    # 已验证不可变标量不需要改变原值。
    return value


@dataclass(frozen=True)
class FieldLocation:
    """保存原字段在来源中的位置，区分原字段与表达式别名。

    source是来源名，field保存表列或内存字段原文，允许含点号。
    locator保存额外的JSON定位信息，并在构造时深度冻结。
    定位信息只说明如何查找字段，不能证明对应文件或旧来源能力已经核实。
    """

    source: str  # 来源名，不从路径猜测。
    field: str  # 列或已解码字段原文，允许点号。
    locator: Mapping[str, JsonValue] = field(default_factory=dict)  # profile额外定位证据。

    def __post_init__(self) -> None:
        """检查来源和原字段，冻结附加定位信息。

        参数:
            无。读取source、field和locator。
        返回:
            None。将locator替换为独立的只读快照。
        异常:
            TypeError或ValueError: 名称、字段文本或JSON定位信息不合法。
        """
        # 来源名参与当前计划名称空间，原字段不改名。
        require_identifier(self.source, 'field.source')
        # 字段文本保持原定位，不能解释为DSL属性。
        require_text(self.field, 'field.field')
        # 定位必须是对象，不能接孤立列表或字符串。
        if not isinstance(self.locator, Mapping):
            # 错误结构不假装为空定位。
            raise TypeError('locator必须为Mapping')
        # 所有嵌套层与外部调用者断开共享。
        object.__setattr__(self, 'locator', freeze_metadata(self.locator))


@dataclass(frozen=True)
class FieldDescription:
    """描述一个可请求的输出别名及其原字段、类型和单位。

    name是输出别名，field保留原定位；dtype与unit描述归一化后的输出。
    metadata保存只读转换和可选语义声明，不强制普通分析加入领域目录。
    枚举类型必须在metadata.labels中声明非空、唯一的标签集合，供跨批核对。
    同一原字段可以有不同显式转换，各别名分别保存描述。
    """

    name: str  # iter_batches可请求的输出别名。
    field: FieldLocation  # 完整原定位，区别于semantic_id。
    dtype: SignalDType  # 已归一化输出的逻辑类型。
    unit: str  # 已归一化输出单位，未知标签不自动verified。
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)  # 可选声明与转换证据。

    def __post_init__(self) -> None:
        """校验字段描述，并冻结用于跨批核对的元数据。

        参数:
            无。读取name、field、dtype、unit和metadata。
        返回:
            None。metadata成为只读快照；不会读取来源来核实单位或定位。
        异常:
            TypeError或ValueError: 名称、定位、类型、单位文本、JSON结构或枚举标签域错误。
        """
        # 输出别名遵守首版安全名称规则。
        require_identifier(self.name, 'field.name')
        # 字段位置和dtype不可用无类型字典/字符串代替。
        if not isinstance(self.field, FieldLocation) or not isinstance(self.dtype, SignalDType):
            # 配置层应先显式解析类型。
            raise TypeError('field需要FieldLocation和SignalDType')
        # 标签保留原文；物理单位契约另由绑定检查。
        require_text(self.unit, 'field.unit')
        # 自由元数据只接受对象结构。
        if not isinstance(self.metadata, Mapping):
            # 不自动将错误输入转换为空对象。
            raise TypeError('metadata必须为Mapping')
        # 深冻结先规范元数据数组，enum标签域必须可跨批核对。
        metadata = freeze_metadata(self.metadata)
        # enum的逻辑标签在描述中明确，不能每批重新猜编码顺序。
        if self.dtype is SignalDType.ENUM:
            # labels属于该dtype的必要元数据，普通业务键仍可自由声明。
            labels = metadata.get('labels', ())
            # 只接受非空唯一文本域，不放行字符串本身或重复码。
            if not isinstance(labels, tuple) or not labels or any(type(item) is not str or not item.strip() for item in labels) or len(set(labels)) != len(labels):
                # enum无域就无法证明跨批类型契约。
                raise ValueError('enum描述metadata需要非空唯一labels')
        # 保存不可变描述，不从上一次计划继承。
        object.__setattr__(self, 'metadata', metadata)


@dataclass(frozen=True)
class SourceCapabilities:
    """逐项记录来源适配器声明的能力和限制。

    decoded_output、raw_export、repeat_scan和random_access分别表示已解码输出、
    原始导出、可重复读取和随机访问能力，必须使用真实布尔值。
    diagnostics与limitations是不可变说明元组。模型只校验声明结构，
    不会运行来源来证明能力，也不因repeat_scan为True自动增加旧日志扫描。
    """

    decoded_output: bool  # 是否实际能返回逐次已解码信号。
    raw_export: bool  # 原路径已支持原始导出时才可为True。
    repeat_scan: bool  # 可重复调用的能力，不授权多次旧扫描。
    random_access: bool  # 是否可随机定位，普通迭代不等同此能力。
    diagnostics: tuple[str, ...] = ()  # 已实际暴露的诊断。
    limitations: tuple[str, ...] = ()  # 未获得的元数据或兼容限制。

    def __post_init__(self) -> None:
        """检查能力开关及诊断、限制文本的结构。

        参数:
            无。读取四个能力开关、diagnostics和limitations。
        返回:
            None。保留原声明，不推断或测试来源能力。
        异常:
            TypeError或ValueError: 开关不是bool，文本列表不是tuple，或说明文本为空。
        """
        # 禁止把整数1当作已经审核的能力。
        if any(type(value) is not bool for value in (self.decoded_output, self.raw_export, self.repeat_scan, self.random_access)):
            # 不用truthiness扩大声明。
            raise TypeError('capability必须为bool')
        # 诊断和限制只作为事实文本，不能执行。
        for items in (self.diagnostics, self.limitations):
            # 不共享可变列表或不明确顺序的集合。
            if not isinstance(items, tuple):
                # 错误形状在构造前拒绝。
                raise TypeError('diagnostics/limitations必须为tuple')
            # 每条非空说明保留大小写及原语义。
            for item in items:
                # 不能用空文本冒充限制已说明。
                require_text(item, 'capability说明')


@dataclass(frozen=True)
class SourceDescription:
    """保存一个来源的静态字段、时钟及能力声明。

    name标识来源，fields保存唯一输出别名，timebase_id标识声明的时间基准。
    observation_start_ns和observation_end_ns保存已知观测边界，未知端点各自为None。
    capabilities记录能力说明，legacy_profile可保存旧来源的契约标识。
    metadata_status区分'verified'已核实、'declared'仅声明和'unavailable'不可用。
    模型校验不会读取来源，也不会自动将声明状态升级为已核实。
    """

    name: str  # 当前计划来源名。
    fields: tuple[FieldDescription, ...]  # 已描述的输出别名和原定位。
    timebase_id: str  # 明确来源时基ID。
    observation_start_ns: int | None  # 未知开始保留None。
    observation_end_ns: int | None  # 未知终点不补周期。
    capabilities: SourceCapabilities  # 逐项审核能力。
    legacy_profile: str | None = None  # 仅旧来源需要冻结profile身份。
    metadata_status: str = 'declared'  # verified/declared/unavailable。

    def __post_init__(self) -> None:
        """检查描述归属、别名唯一性和已知的观测范围。

        参数:
            无。读取来源名称、字段元组、时钟、观测端点、能力和证据状态。
        返回:
            None。已知双端点按时间区间检查，未知端点保持None。
        异常:
            TypeError或ValueError: 描述类型、归属、重复名称、状态或旧契约标识错误。
            OverflowError: 时间坐标或区间跨度超出范围。
        副作用:
            无输入读取；名称合法不表示来源实际存在。
        """
        # 来源和时基各有明确安全名称。
        require_identifier(self.name, 'description.name')
        # 相同ID不等于共同起点，同步仍由计划验证。
        require_identifier(self.timebase_id, 'description.timebase_id')
        # 全部字段有类型，不能只有类名和dict占位。
        if not isinstance(self.fields, tuple) or any(not isinstance(item, FieldDescription) for item in self.fields) or not isinstance(self.capabilities, SourceCapabilities):
            # 错误描述不能进入执行能力检查。
            raise TypeError('description需要typed fields/capabilities')
        # 输出别名唯一且原字段确实属于当前来源。
        if len({item.name for item in self.fields}) != len(self.fields) or any(item.field.source != self.name for item in self.fields):
            # 不取第一个冲突或使用他源字段。
            raise ValueError('description字段重名或来源冲突')
        # 未知边界分别保留；已知才规范精确纳秒。
        for value in (self.observation_start_ns, self.observation_end_ns):
            # None不是0，也不表示完整覆盖。
            if value is not None:
                # bool/float坐标在模型边界拒绝。
                require_int64_ns(value)
        # 双端都有事实才判断完整范围。
        if self.observation_start_ns is not None and self.observation_end_ns is not None:
            # 同时检查反向和跨度溢出。
            Interval(self.observation_start_ns, self.observation_end_ns)
        # 证据状态是固定词汇，不能自由标verified。
        if self.metadata_status not in ('verified', 'declared', 'unavailable'):
            # 错误版本/状态应执行前失败。
            raise ValueError('未知metadata_status')
        # 旧profile非空，但不假装已经登记/可调用。
        if self.legacy_profile is not None:
            # profile登记和哈希是adapter的另一个责任。
            require_text(self.legacy_profile, 'legacy_profile')


@dataclass(frozen=True)
class ReadRequest:
    """说明本次会话要读取的信号别名、分析范围和批次上限。

    session_id绑定当前会话，signal_names指定列顺序并允许空投影。
    domain_start_ns与domain_end_ns是分析请求坐标，不表示来源实际观测范围。
    batch_rows限制每批全部信号列的样本数之和，不能按宽表行数计算。
    请求范围不授权修改旧读取链；适配器保留分析开始前的必要更新及真实终点。
    同一时间组可以跨批，分批上限不代表该组已经完整。
    """

    session_id: str  # 明确会话身份。
    signal_names: tuple[str, ...]  # 当前绑定输出别名，允许空投影。
    domain_start_ns: int | None  # 分析域起点；纯消息整文件请求可未声明。
    domain_end_ns: int | None  # 分析域终点；与起点同时未声明。
    batch_rows: int  # 所有series样本数总和上限。

    def __post_init__(self) -> None:
        """检查请求会话、唯一别名、时间范围和正整数批次上限。

        参数:
            无。读取session_id、signal_names、domain_start_ns、domain_end_ns和batch_rows。
        返回:
            None。保持别名顺序，不去重或裁剪来源数据。
        异常:
            TypeError或ValueError: 名称、容器、重复别名、时间范围或批次大小错误。
            OverflowError: 时间范围超出整数纳秒约束。
        """
        # 会话不能从全局当前任务猜测。
        require_identifier(self.session_id, 'request.session_id')
        # 投影顺序明确，同一别名不能重复计样本。
        if not isinstance(self.signal_names, tuple) or len(set(self.signal_names)) != len(self.signal_names):
            # 不自动去重。
            raise ValueError('signal_names需要唯一tuple')
        # 每个名字必须是当前计划可以安全绑定的简单别名。
        for name in self.signal_names:
            # 来源字段的点号不是表达式别名。
            require_identifier(name, 'request.signal_name')
        # 半开范围和极值跨度按统一时间契约。
        if self.domain_start_ns is None or self.domain_end_ns is None:
            if self.domain_start_ns is not None or self.domain_end_ns is not None:
                raise ValueError('未声明时间域请求必须双端同时为None')
        else:
            Interval(self.domain_start_ns, self.domain_end_ns)
        # 不能把True当成单行预算，也不能允许零缓冲。
        if type(self.batch_rows) is not int or self.batch_rows <= 0:
            # 限额不靠默认值掩盖错误。
            raise ValueError('batch_rows必须为正整数')


@dataclass(frozen=True)
class SignalSeries:
    """保存一批中的单个信号列及每个样本的来源身份。

    time_ns、values、valid、quality和sequence都是等长一维数组，形状为(N,)。
    time_ns与sequence使用int64，时间单位为纳秒；时间非递减，序号非负且列内唯一。
    valid明确值是否有效，quality保存原因；不能凭values中的占位判断有效性。
    name、dtype和unit说明别名、逻辑类型及输出单位；枚举用整数码和labels表示。
    source_ref与可选original_values均与样本等长，保留位置及原始诊断。

    构造时复制数组并设为只读，调用者修改原数组不影响本列。
    本类不折叠同时间冲突，也不执行valid_for保持或过期判断；这些属于后续时间驱动。
    """

    name: str  # 简单表达式别名。
    dtype: SignalDType  # 逻辑类型，enum存储int64 code。
    unit: str  # 已显式归一化输出单位。
    time_ns: np.ndarray  # shape(N,), int64，当前会话分析坐标ns。
    values: np.ndarray  # shape(N,), 精确dtype。
    valid: np.ndarray  # shape(N,), bool，不能单用值占位判断。
    quality: np.ndarray  # shape(N,), uint16九位原因。
    sequence: np.ndarray  # shape(N,), int64，原来源稳定非负序号。
    source_ref: tuple[SourceRef, ...]  # 每行实际来源/字段/会话。
    labels: tuple[str, ...] = ()  # enum固定域，其他类型为空。
    original_values: tuple[int | float | bool | str | None, ...] | None = None  # 原无效诊断可保留。

    def __post_init__(self) -> None:
        """检查单列布局、有效性和样本身份，再复制为只读数组。

        参数:
            无。读取信号描述、五个数组、source_ref、labels和original_values。
        返回:
            None。时间、序号及数值数组成为本模型独立拥有的只读数据。
        异常:
            TypeError或ValueError: 名称、数组形状或类型、质量、时间顺序、序号、
                来源引用或原始诊断不符合要求；不通过广播或隐式转换修正。
        副作用:
            分配数组副本，不修改调用者输入。无效原浮点可保留在诊断中。
        """
        # 输出别名和单位仍需明确，不推断字段语义。
        require_identifier(self.name, 'series.name')
        # 标签有效性与转换一致性由上游绑定提供。
        require_text(self.unit, 'series.unit')
        # 数值结构校验包括enum域、非有限正常值与禁止原因。
        numeric = NumericArray(self.dtype, self.values, self.valid, self.quality, self.labels)
        # 时间与稳定序号始终分列int64，禁止混宽表float。
        for array in (self.time_ns, self.sequence):
            # ndarray子类或隐式cast均不接受。
            if type(array) is not np.ndarray or array.ndim != 1 or array.dtype != np.dtype('int64') or len(array) != len(numeric.values):
                # 错误shape不能广播补齐。
                raise TypeError('time/sequence需要同长1维int64列')
        # 先比较不相减，避免极值坐标之差wrap。
        if np.any(self.time_ns[1:] < self.time_ns[:-1]):
            # 不排序输入来掩盖来源乱序。
            raise ValueError('series时间回退')
        # 来源序号非负且列内唯一；无需用时间替代它。
        if np.any(self.sequence < 0) or len(np.unique(self.sequence)) != len(self.sequence):
            # 保留相同时间不同序号，拒绝重复同一观测身份。
            raise ValueError('series sequence负值或重复')
        # 原定位每行等长，批次归属另外在SignalBatch检查。
        if not isinstance(self.source_ref, tuple) or len(self.source_ref) != len(self.time_ns) or any(not isinstance(ref, SourceRef) for ref in self.source_ref):
            # 少一个来源位置也不能假设复用第一条。
            raise ValueError('source_ref需要同长typed tuple')
        # 原诊断可省略，但存在时必须严格等长且不可变。
        if self.original_values is not None:
            # 不接受可变list或不同长度的原始事实。
            if not isinstance(self.original_values, tuple) or len(self.original_values) != len(self.time_ns):
                # 不能截断诊断或用值占位重建。
                raise ValueError('original_values长度/容器错误')
            # 无效原浮点可保留NaN，正常数值已由valid校验。
            for value in self.original_values:
                # 禁止可变对象进入跨规则共享输入。
                require_scalar(value)
        # NumericArray已复制校验列，不再重复制相同三个数组。
        for name in ('values', 'valid', 'quality'):
            # 安全只读列仍携带各自精确dtype。
            object.__setattr__(self, name, getattr(numeric, name))
        # 时间与序号独立复制，调用者更改原数组无影响。
        for name in ('time_ns', 'sequence'):
            # 新数组独立拥有存储，其复制后大小由nbytes反映。
            copied = getattr(self, name).copy()
            # 只读约定防止普通写操作污染其他规则。
            copied.flags.writeable = False
            # 只在构造期安装新数组。
            object.__setattr__(self, name, copied)

    @property
    def nbytes(self) -> int:
        """统计本列五个数组的存储字节数。

        参数:
            无。读取time_ns、values、valid、quality和sequence的nbytes。
        返回:
            int。数组字节总和；不含枚举标签、来源引用、原诊断或其他Python容器。
        异常:
            无主动异常；数组结构已在构造时检查。
        """
        # 时间与序号各占8字节，有效性占1字节、质量占2字节；值按类型占1或8字节，标签另计。
        return sum(array.nbytes for array in (self.time_ns, self.values, self.valid, self.quality, self.sequence))


@dataclass(frozen=True)
class SignalBatch:
    """传送一个来源在当前会话中的异步信号列和读取进度。

    source与session_id确定归属，series按输出别名保存列，允许零列。
    watermark_ns是进度承诺：后续不会再出现小于或等于该坐标的更新。
    它可以落后于当前尚未完整的时间组，不能当作实际观测终点。
    source_eof只表示整个配置来源耗尽；observed_end_ns保存观测终点事实，
    未知时保留None。单批结构检查不替代BatchValidator的跨批校验。
    """

    source: str  # 已解码来源名称。
    session_id: str  # 本次读取的明确会话。
    series: Mapping[str, SignalSeries]  # 输出别名到真实列，允许零列。
    watermark_ns: int | None  # 已完整的时间组进度，否则None。
    source_eof: bool  # 整个来源终点，不能仅单文件EOF。
    observed_end_ns: int | None  # 观测未知保留None，不补周期。

    def __post_init__(self) -> None:
        """检查批次归属、列名称和观测终点，冻结列映射。

        参数:
            无。读取来源、会话、series、watermark_ns、source_eof和observed_end_ns。
        返回:
            None。series成为新只读映射，列数组保持已有独立所有权。
        异常:
            TypeError或ValueError: 映射或结束标记类型、别名、样本归属或观测边界错误。
            OverflowError: 已知时间坐标超出整数纳秒范围。
        """
        # 来源与会话必须真实、明确。
        require_identifier(self.source, 'batch.source')
        # 会话边界不会从上个请求继承。
        require_identifier(self.session_id, 'batch.session_id')
        # 列须为已定义的信号模型，来源结束标记须为bool，不能用整数代替。
        if not isinstance(self.series, Mapping) or type(self.source_eof) is not bool:
            # 不将未知输入当作空批或已结束。
            raise TypeError('batch需要Mapping series与bool EOF')
        # 所有输出名字与列自己的绑定一致。
        for name, column in self.series.items():
            # 未绑定名字/错误列结构在执行前拒绝。
            if not isinstance(column, SignalSeries) or name != column.name:
                # 不能用键映射把其他信号冒充当前列。
                raise ValueError('batch列类型/名称冲突')
            # 每个样本来源引用都属于本batch会话和来源。
            if any(ref.session_id != self.session_id or ref.source_name != self.source for ref in column.source_ref):
                # 即使值相同也不能丢失真实归属。
                raise ValueError('batch sample来源/会话冲突')
        # unknown端点和watermark独立保留None。
        for value in (self.watermark_ns, self.observed_end_ns):
            # 不将None转成0或当前时间。
            if value is not None:
                # 所有进度和观测时间遵守精确ns协议。
                require_int64_ns(value)
        # 已知观测终点必须包含该批真实末点。
        if self.observed_end_ns is not None and any(len(column.time_ns) and int(column.time_ns[-1]) > self.observed_end_ns for column in self.series.values()):
            # 不能在自称结束之后继续提供真实样本。
            raise ValueError('样本超出observed_end')
        # 冻结外部别名字典，列内容已复制只读。
        object.__setattr__(self, 'series', MappingProxyType(dict(self.series)))

    @property
    def sample_count(self) -> int:
        """按所有列的样本数总和计算本批大小。

        参数:
            无。读取series中各列的长度。
        返回:
            int。空批为0；同一时间的多个信号分别计数，用于核对batch_rows上限。
        异常:
            无主动异常；列结构已在构造时检查。
        """
        # 同时间多信号仍各算一个样本，同刻可跨传输批次。
        return sum(len(column.time_ns) for column in self.series.values())
