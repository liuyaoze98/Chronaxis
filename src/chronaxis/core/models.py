"""把调用者提供的内存观测构造成不可变模型，并检查身份、时间和质量约束。

输入包括会话和来源标识、整数纳秒坐标、原字段值及显式质量原因；输出时间范围、
时基、内存行、来源、会话、数据集和信号样本。构造时检查结构及范围，复制字段
映射为只读快照，拒绝来源时间回退，不排序或补齐数据。样本归属和声明类型
通过显式方法检查，模型构造不会执行信号绑定、保持或分析。
本模块只依赖标准库和整数时间协议，不读取文件，不加载NumPy或CAN组件，
不持有运行状态；SourceSpec当前只接受内存行。
"""

# 标准库负责冻结对象/映射和非有限诊断，不加载数组或外部来源。
import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

# 时间协议已独立验证；共享输入校验不等于复用NumPy数值内核。
from ..timebase.conversion import INT64_MAX, INT64_MIN, checked_add_ns, require_int64_ns
from .types import QualityFlag, SignalDType, SourceType, TimeType
from .validation import require_identifier, require_scalar, require_sequence, require_text


@dataclass(frozen=True)
class Interval:
    """保存左闭右开纳秒范围，允许零长度，不允许反向或跨度溢出。

    构造校验时间/长度为int64；点上下文可显式包含end，不改变连续半开。
    """

    start_ns: int  # 包含的开始坐标，整数纳秒。
    end_ns: int  # 连续范围不包含的终点，允许等于开始。

    def __post_init__(self) -> None:
        """构造时验证边界及完整整数跨度。

        参数: 无额外参数；读取start_ns/end_ns，拒绝bool和float。
        返回: None；字段规范为精确Python整数并冻结。
        异常: TypeError为错误类型；ValueError为反向；TimeOverflowError为超界。
        副作用: 只在初始化中规范自身字段，不修改调用方输入。
        """
        # 两端各自必须合法，不能用越界输入互相抵消。
        start, end = require_int64_ns(self.start_ns, "start_ns"), require_int64_ns(self.end_ns, "end_ns")
        # 相等合法，严格回退才违反半开范围。
        if end < start:
            # 不交换边界或默认为空范围。
            raise ValueError("end_ns不能早于start_ns")
        # 两端合法仍可能跨度超MAX，在Python整数域相减后检查。
        require_int64_ns(end - start, "duration_ns")
        # 规范整数容器，不改变实际纳秒位值。
        object.__setattr__(self, "start_ns", start)
        # 构造结束后禁止外部修改终点。
        object.__setattr__(self, "end_ns", end)

    def duration_ns(self) -> int:
        """返回已经验证的半开范围长度，不补样本周期。

        参数: 无额外参数；读取当前边界。
        返回: int；非负int64纳秒，零长度返回0。
        异常: 无主动异常；构造已验证范围。
        """
        # 已验证跨度不会wrap，也不多包含一个终点周期。
        return self.end_ns - self.start_ns

    def contains(self, time_ns: int, *, point: bool = False) -> bool:
        """检查连续半开或显式点上下文成员关系。

        参数: time_ns为int64纳秒；point (bool)默认False，True包含实际末点。
        返回: bool；零长度连续范围为空，点上下文可包含唯一端点。
        异常: TypeError为时间/point类型错误；TimeOverflowError为坐标超界。
        """
        # 校验查询坐标，不用float或非法数值参与范围判断。
        time = require_int64_ns(time_ns)
        # 点模式须显式布尔，不能将任意非零对象当作开关。
        if type(point) is not bool:
            # 配置类型错误与正常范围外分开。
            raise TypeError("point必须为bool")
        # 点视图包含end；连续视图严格小于end，两者下界都包含。
        return self.start_ns <= time <= self.end_ns if point else self.start_ns <= time < self.end_ns


@dataclass(frozen=True)
class TimebaseSpec:
    """保存时间坐标种类及其起点声明，供来源映射和同步检查使用。

    relative表示相对坐标，必须提供origin。absolute表示已经规范化的UTC纳秒，
    不再接受相对起点。字段不可变，不读取机器时区；相同timebase_id本身不能
    证明来源同步，联合计算仍须检查完整时基或显式同步证据。
    """

    timebase_id: str  # 当前显式时间基准ID，不从文件名猜测。
    time_type: TimeType  # 相对坐标或已规范化UTC绝对坐标。
    origin: str | None = None  # 相对来源明确起点标签；绝对坐标使用UTC epoch。

    def __post_init__(self) -> None:
        """检查时基类型和起点声明的一致性。

        参数: 无额外参数；读取timebase_id/time_type/origin。
        返回: None；保留调用者起点原文。
        异常: TypeError为错误类型；ValueError为名称/起点缺项或冲突。
        """
        # 时基ID采用简单标识，origin另作为非空来源事实。
        require_identifier(self.timebase_id, "timebase_id")
        # 字符串kind必须由配置层显式解析成类型，不能隐式猜测。
        if not isinstance(self.time_type, TimeType):
            # 未知类型在构造时失败，不静默采用relative。
            raise TypeError("kind必须为TimeType")
        # 相对0本身没有可核实公共起点，必须保留origin。
        if self.time_type is TimeType.RELATIVE:
            # 文本只校验，不能自动与其他origin合并。
            require_text(self.origin, "origin")
        elif self.origin is not None:
            # UTC epoch不同时接收另一套相对起点含义。
            raise ValueError("absolute时基不接受relative origin")


@dataclass(frozen=True)
class MemoryRow:
    """保存一条内存观测的原时间、来源序号和原字段值。

    values会复制为只读映射，None、NaN和无穷值保留供后续质量检查。一行可以
    包含多个字段或没有字段；sequence是稳定的非负来源序号，同时间不同序号
    分别保留。本模型不为原字段绑定表达式别名。
    """

    time_ns: int  # 来源原坐标，offset在分析层显式应用。
    values: Mapping[str, int | float | bool | str | None]  # 原字段到原值，非表达式名。
    sequence: int  # 来源内原序号，同时间不同序号不去重。

    def __post_init__(self) -> None:
        """验证行容器并冻结字段值快照。

        参数: 无额外参数；values接受Mapping，值仅原生不可变标量。
        返回: None；时间/序号规范为整数、values为新只读映射。
        异常: TypeError/ValueError为容器/字段/值/序号错误；TimeOverflowError为时间超界。
        副作用: 复制值映射，不改原映射，不持有可变嵌套值。
        """
        # 原时间先按整数协议校验，不能隐式猜测秒。
        time = require_int64_ns(self.time_ns)
        # 序号用于稳定身份，不用时间替代它。
        sequence = require_sequence(self.sequence)
        # 只接受明确键值映射，不从任意可迭代对象构造行。
        if not isinstance(self.values, Mapping):
            # 错误shape不能转成正常空行。
            raise TypeError("values必须为字段Mapping")
        # 新字典断开调用方后续修改，不使用共享全局缓存。
        copied = dict(self.values)
        # 每个原字段保持完整文本；原值不可变但可暂时无效。
        for field, value in copied.items():
            # 点号等合法原字段不转换为表达式别名。
            require_text(field, "field")
            # 容器或任意对象不能进入共享逻辑模型。
            require_scalar(value)
        # 只在构造期规范自己的坐标字段。
        object.__setattr__(self, "time_ns", time)
        # 序号保留原整数位值。
        object.__setattr__(self, "sequence", sequence)
        # 映射只读且各值不可变，冻结不是浅层共享原dict。
        object.__setattr__(self, "values", MappingProxyType(copied))


@dataclass(frozen=True)
class SourceSpec:
    """描述冻结内存来源及固定时钟偏移，不执行读取或绑定。

    rows为原坐标、非递减顺序；sequence唯一，同时间不同序号保留。
    observation边界是来源原坐标，未知端点为None，不补假设周期。
    所有已知坐标加offset必须合法；无任何自动排序、同步推断或缓存优化。
    """

    name: str  # 会话内来源名，须唯一；跨会话可复用同名。
    timebase: TimebaseSpec  # 显式来源时基/起点，不继承上次任务。
    rows: tuple[MemoryRow, ...]  # 原顺序只读行；空来源合法。
    offset_ns: int = 0  # 明确固定偏移，默认0不构成同步证明。
    observation_start_ns: int | None = None  # 已知来源开始坐标，否则unknown。
    observation_end_ns: int | None = None  # 已知来源末点坐标，否则unknown。
    source_type: SourceType = SourceType.MEMORY  # 此模型只描述内存行来源。

    def __post_init__(self) -> None:
        """检查来源形状、顺序、身份和固定偏移范围。

        参数: 无额外参数；rows必须tuple[MemoryRow]，不隐式转换列表/生成器。
        返回: None；offset及已知观测边界规范为整数，原rows保持顺序。
        异常: TypeError为结构；ValueError为回退/重复序号/边界冲突；TimeOverflowError为坐标/偏移溢出。
        副作用: 只用局部校验集合，无数据读写/排序/归并或后端数值执行。
        """
        # 来源名不会从路径或语义名称自动生成。
        require_identifier(self.name, "source.name")
        # 明确typed时基、支持kind与不可变行容器。
        if not isinstance(self.timebase, TimebaseSpec) or self.source_type is not SourceType.MEMORY or not isinstance(self.rows, tuple):
            # 外部来源不能仅声明名字就冒充已接线。
            raise TypeError("source需要TimebaseSpec、SourceType.MEMORY和tuple rows")
        # 空来源也检查偏移，不跳过非法配置。
        offset = require_int64_ns(self.offset_ns, "offset_ns")
        # 未知端点保留None，已知端点不能为bool/float或超界。
        start = None if self.observation_start_ns is None else require_int64_ns(self.observation_start_ns, "observation_start_ns")
        # 起止独立可未知，不能从空数据假造完整范围。
        end = None if self.observation_end_ns is None else require_int64_ns(self.observation_end_ns, "observation_end_ns")
        # 双端已知才验证完整范围，不将unknown当0。
        if start is not None and end is not None:
            # 原观测范围不允许反向或超界跨度。
            Interval(start, end)
        # 已知端点的固定映射必须在纳秒协议内。
        for boundary in (start, end):
            # 只校验真实已声明端点，不扩展unknown。
            if boundary is not None:
                # 检查偏移后的完整坐标，无浮点运算。
                checked_add_ns(boundary, offset)
        # 前一坐标与身份集合只属于本次构造，不泄漏其他来源。
        previous, sequences = None, set()
        # 逐行验证模型；执行调度和数组计算由对应模块负责。
        for row in self.rows:
            # 同一tuple不能混入字典或任意对象。
            if not isinstance(row, MemoryRow):
                # 不在此隐式解析配置行。
                raise TypeError("rows元素必须为MemoryRow")
            # 相同时间允许，严格回退违背来源内有序契约。
            if previous is not None and row.time_ns < previous:
                # 不重新排序旧来源或掩盖输入错误。
                raise ValueError("source rows时间必须非递减")
            # sequence是来源内身份，同时间不同序号合法，重复身份拒绝。
            if row.sequence in sequences:
                # 不通过删除重复行修补身份冲突。
                raise ValueError("source rows sequence重复")
            # 已知观测边界的点视图两端包含。
            if (start is not None and row.time_ns < start) or (end is not None and row.time_ns > end):
                # 实际行不能超出自声明观测范围。
                raise ValueError("source row超出已声明观测边界")
            # 每个原坐标的固定偏移映射可表示，仍不证明公共起点。
            checked_add_ns(row.time_ns, offset)
            # 更新当前来源局部顺序检查状态。
            previous = row.time_ns
            # 保留全部唯一序号，不仅按时间去重。
            sequences.add(row.sequence)
        # 构造后冻结规范化偏移，原值意义不变。
        object.__setattr__(self, "offset_ns", offset)
        # 已知/未知起点事实原样保留。
        object.__setattr__(self, "observation_start_ns", start)
        # 不推断空来源或最后样本之后的周期。
        object.__setattr__(self, "observation_end_ns", end)


@dataclass(frozen=True)
class SourceRef:
    """用会话、来源和原字段定位内存样本，不以别名当全局数据键。

    字段文本保持点号和大小写；会话、来源和字段共同构成不可变身份。
    """

    session_id: str  # 输入所属会话，跨会话同名来源不相等。
    source_name: str  # 会话内来源名。
    field: str  # 内存原字段；不是semantic_id或Python属性路径。

    def __post_init__(self) -> None:
        """验证可追溯身份，不解析字段为表达式。

        参数: 无额外参数；读取三个定位字段。
        返回: None；冻结完整来源身份。
        异常: TypeError/ValueError为名称/字段缺失或非法。
        """
        # 会话身份必须明确，不从当前全局对象继承。
        require_identifier(self.session_id, "source_ref.session_id")
        # 来源名依会话范围校验，具体归属由SessionSpec检查。
        require_identifier(self.source_name, "source_ref.source_name")
        # 原字段允许点号，不进行隐藏改名。
        require_text(self.field, "source_ref.field")


@dataclass(frozen=True)
class SignalSample:
    """保留观测原值、显式有效性、质量原因及完整内存来源身份。

    基础策略禁止全部非零质量位；有效0合法，None/NaN不能伪装有效。
    invalid必须有原因但可保留原值；定义dtype另显式校验，不推断绑定。
    """

    name: str  # 计划内简单别名，尚不证明绑定已完成。
    time_ns: int  # 当前分析坐标；来源映射/会话归属另显式检查。
    value: int | float | bool | str | None  # 保留原逻辑标量，不自动补0。
    valid: bool  # 明确基础质量有效性，不接受0/1代替bool。
    quality: QualityFlag  # 可以组合的原因，NONE不替代valid。
    source_ref: SourceRef  # typed会话/来源/字段，不复用跨会话绑定。
    sequence: int  # 来源内稳定原序号。
    code: 'ScalarValue | None' = None  # 仅请求枚举原码时保留独立类型与质量。

    def __post_init__(self) -> None:
        """拒绝类型/质量自相矛盾的样本，保留非法观测的诊断值。

        参数: 无额外参数；valid/quality/source_ref须用明确类型。
        返回: None；时间/序号规范为整数，其他事实冻结保留。
        异常: TypeError为结构/标量类型；ValueError为有效性矛盾；TimeOverflowError为坐标超界。
        副作用: 不更改原值/质量，不推断缺失为0，不运行绑定或数值变换。
        """
        # 别名遵循安全简单名称，不能用semantic点号替代。
        require_identifier(self.name, "sample.name")
        # 模型时间遵循已有int64纳秒协议。
        time = require_int64_ns(self.time_ns)
        # 原值必须不可变，但无效值允许None或非有限浮点。
        require_scalar(self.value)
        # 原序号不由时间或其他任务自动填补。
        sequence = require_sequence(self.sequence)
        # 有效性/质量/来源需要typed声明，不使用整数truthiness。
        if type(self.valid) is not bool or not isinstance(self.quality, QualityFlag) or not isinstance(self.source_ref, SourceRef):
            # 未知质量位已由严格枚举构造拒绝，这里拒绝裸整数或字符串来源。
            raise TypeError("sample需要bool valid、QualityFlag及SourceRef")
        # 有效样本不能带基础禁止质量、缺值或非有限浮点。
        if self.valid and (self.quality != QualityFlag.NONE or self.value is None or (type(self.value) is float and not math.isfinite(self.value))):
            # 矛盾输入应明确失败，不能自动清质量或补0。
            raise ValueError("valid=True与禁止质量、None或非有限值矛盾")
        # 无效观测必须携带原因，NONE不能证明已知的失败。
        if not self.valid and self.quality == QualityFlag.NONE:
            # 让后续质量传播有可追溯事实，而不是无原因False。
            raise ValueError("invalid样本必须保留非零质量原因")
        # 只规范整数容器，不改变数据值或来源关系。
        object.__setattr__(self, "time_ns", time)
        # 冻结序号保持原位值。
        object.__setattr__(self, "sequence", sequence)

    def validate_dtype(self, dtype: SignalDType, choices: tuple[str, ...] = ()) -> None:
        """在已声明定义类型下验证有效值，不执行隐式归一化。

        参数: dtype为SignalDType；choices仅ENUM使用，非空唯一原标签tuple。
        返回: None；invalid占位不参与dtype数值校验，但声明域仍须合法。
        异常: TypeError为类型不符；ValueError为枚举域/标签；OverflowError为整数范围超界。
        副作用: 不转换原值、不推断dtype，也不修改质量；数值失败的质量标志由数值层产生。
        """
        # dtype须由定义层显式声明，不从值推断。
        if not isinstance(dtype, SignalDType) or not isinstance(choices, tuple):
            # 字符串类型名和自由choice容器由配置层解析。
            raise TypeError("dtype必须为SignalDType，choices必须为tuple")
        # 枚举必须有明确唯一标签域，即使当前观测无效也先验证声明。
        if dtype is SignalDType.ENUM:
            # 空域不是有效枚举定义。
            if not choices:
                # 不把任意字符串当作正常枚举。
                raise ValueError("enum需要非空choices")
            # 标签保留完整字符串与大小写，不转表达式名。
            for label in choices:
                # 明确标签类型/非空约束，不以数值truthiness判断。
                require_text(label, "choices.label")
            # 同标签重复无法提供唯一声明域。
            if len(set(choices)) != len(choices):
                # 不自动去重以掩盖定义错误。
                raise ValueError("choices标签重复")
        elif choices:
            # 非枚举不能接受未定义的choices含义。
            raise ValueError("仅enum可声明choices")
        # invalid占位可以保留原错误值，不应进入正常数值检查/计算。
        if not self.valid:
            # 原原因已经构造校验，返回不改变任何输入事实。
            return
        # bool和enum分别检查，Python bool不是整数。
        expected_type = {SignalDType.INT64: int, SignalDType.UINT64: int,
                         SignalDType.FLOAT64: float, SignalDType.BOOL: bool, SignalDType.ENUM: str}[dtype]
        # 原生类型严格匹配，不默认将整数转换为float或数值转换为bool。
        if type(self.value) is not expected_type:
            # 需要转换时由显式归一化层承担精度/质量检查。
            raise TypeError(f"value与声明{dtype.value}类型不一致")
        # 定宽整数检查仅针对有效位置，没有中间wrap。
        if dtype in (SignalDType.INT64, SignalDType.UINT64):
            # 独立声明signed/unsigned范围，其他逻辑类型不参与数值检查。
            lower, upper = (INT64_MIN, INT64_MAX) if dtype is SignalDType.INT64 else (0, 2 ** 64 - 1)
            # 超界输入不能通过Python无界整数放行。
            if not lower <= self.value <= upper:
                # 模型拒绝矛盾有效输入；数值计算层将溢出标为OVERFLOW并产生无效结果。
                raise OverflowError(f"value超出{dtype.value}范围")
        elif dtype is SignalDType.ENUM and self.value not in choices:
            # 未声明标签不是正常的其他/默认枚举值。
            raise ValueError("value不在声明枚举域")


@dataclass(frozen=True)
class SessionSpec:
    """保存一个会话的分析范围和来源集合。

    sources必须为tuple，来源名在本会话内唯一，声明顺序保留。连续范围左闭右开，
    实际点查询可包含末端。不同来源可以有不同origin；身份检查不能替代联合计算的
    同步检查。本模型不可变，不保存执行缓存或跨任务状态。
    """

    session_id: str  # 明确会话边界身份。
    timebase: TimebaseSpec  # 会话分析坐标声明。
    domain_start_ns: int  # 连续开始包含。
    domain_end_ns: int  # 连续末端不含，真实点上下文包含。
    sources: tuple[SourceSpec, ...] = ()  # 会话内来源名唯一；空会话描述合法。

    def __post_init__(self) -> None:
        """校验会话范围、typed来源和唯一名称。

        参数: 无额外参数；读取session_id、timebase、domain和sources。
        返回: None；规范边界为整数，保留来源原顺序。
        异常: TypeError为结构；ValueError为名称/重复来源/反向；TimeOverflowError为边界/跨度。
        """
        # 会话ID不能从别的计划继承。
        require_identifier(self.session_id, "session_id")
        # 来源和时基需明确模型，不解析无类型配置字典。
        if not isinstance(self.timebase, TimebaseSpec) or not isinstance(self.sources, tuple):
            # 可变列表或未校验时基不进入冻结会话。
            raise TypeError("session需要TimebaseSpec及tuple sources")
        # 一次使用统一半开契约验证两个边界/跨度。
        domain = Interval(self.domain_start_ns, self.domain_end_ns)
        # 名称集合局部于当前会话，不影响其他同名来源。
        names = set()
        # 保留原来源声明顺序，不根据内容重排。
        for source in self.sources:
            # 每项都需真正实现的SourceSpec。
            if not isinstance(source, SourceSpec):
                # 只有类名/字典声明不能冒充已校验来源。
                raise TypeError("sources元素必须为SourceSpec")
            # 同会话名称重复时无法唯一定位样本。
            if source.name in names:
                # 跨会话同名允许，当前会话不能取第一个。
                raise ValueError(f"session来源名重复：{source.name}")
            # 仅登记当前会话已验证来源名。
            names.add(source.name)
        # 构造后只保留精确规范坐标。
        object.__setattr__(self, "domain_start_ns", domain.start_ns)
        # 末点语义由显式点模式表达，不加假设周期。
        object.__setattr__(self, "domain_end_ns", domain.end_ns)

    def validate_sample(self, sample: SignalSample) -> None:
        """检查样本会话/来源/字段和观测范围，不执行绑定或读取。

        参数: sample为typed SignalSample，时间为分析坐标；原来源offset已显式应用。
        返回: None；归属/点范围匹配才通过，不证明值与某行/定义已绑定。
        异常: TypeError为非样本；ValueError为身份、字段或范围不符。
        """
        # 校验实际模型后再使用typed来源信息。
        if not isinstance(sample, SignalSample):
            # 字典不能绕过样本质量构造检查。
            raise TypeError("sample必须为SignalSample")
        # 同名来源跨会话不能复用旧输入引用。
        if sample.source_ref.session_id != self.session_id:
            # 身份不匹配不是正常缺失值，执行前拒绝。
            raise ValueError("sample的session_id与当前会话不一致")
        # 逐来源寻找明确名称；构造已证明最多一个匹配。
        source = next((item for item in self.sources if item.name == sample.source_ref.source_name), None)
        # 未定义来源不能靠别名或semantic_id补齐。
        if source is None:
            # 不默认选择第一个来源。
            raise ValueError("sample来源未在当前会话声明")
        # 原字段须在本内存来源实际行中出现，空来源不能伪造字段存在。
        if not any(sample.source_ref.field in row.values for row in source.rows):
            # 列定位与别名绑定是不同事实，字段缺项明确失败。
            raise ValueError("sample原字段在当前memory来源不存在")
        # 会话真实点范围包含end，不增加终点之后连续时间。
        if not Interval(self.domain_start_ns, self.domain_end_ns).contains(sample.time_ns, point=True):
            # 模型范围外不当作有效会话输入。
            raise ValueError("sample时间超出会话点范围")
        # 已知来源观测边界映射到分析坐标后同样包含真实末点。
        if source.observation_start_ns is not None and sample.time_ns < checked_add_ns(source.observation_start_ns, source.offset_ns):
            # 来源开始之前不能借其他来源延长覆盖。
            raise ValueError("sample早于来源观测开始")
        # unknown端点不伪装完整覆盖；这里只校验明确声明边界。
        if source.observation_end_ns is not None and sample.time_ns > checked_add_ns(source.observation_end_ns, source.offset_ns):
            # 来源结束之后不能用更长会话假造来源观测。
            raise ValueError("sample晚于来源观测结束")


@dataclass(frozen=True)
class DatasetSpec:
    """保存一个分析对象、一个会话及其数据集身份。

    dataset_id和entity_id分别标明输入集合与试验对象，session必须为SessionSpec。
    模型不可变，不把多个实体或会话接成同一条时间轴，也不会创建运行状态。
    批量独立计划需由另外的执行能力处理。
    """

    dataset_id: str  # 当前输入数据集ID。
    entity_id: str  # 试验对象身份，不写死车辆或电池领域。
    session: SessionSpec  # 首版单会话，来源在会话中明确声明。

    def __post_init__(self) -> None:
        """检查首版数据集身份与单会话类型。

        参数: 无额外参数；dataset_id/entity_id为简单标识，session为SessionSpec。
        返回: None；保留冻结会话描述，不创建运行状态。
        异常: TypeError/ValueError为身份或会话类型错误。
        """
        # 数据集与实体分别校验，不把两者混为时间基准。
        require_identifier(self.dataset_id, "dataset_id")
        # 任意试验对象都可用，不加入领域本体。
        require_identifier(self.entity_id, "entity_id")
        # 多会话列表或无类型配置不隐式串接为单会话。
        if not isinstance(self.session, SessionSpec):
            # 单个Dataset只接受一个SessionSpec；批量任务由批量执行接口管理。
            raise TypeError("dataset首版需要一个SessionSpec")
