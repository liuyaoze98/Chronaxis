"""将内存来源的原字段与当前计划的信号别名明确关联，并保存可追溯身份。

输入为SessionSpec、SignalDefinition、派生名称和可选同步证据；输出不可变的
SignalBindings及SHA-256身份。先检查信号转换声明，再检查名称冲突、实际字段
存在性和来源归属；联合计算另按实际依赖检查公共时间基准。身份包含实际内存
内容、时间映射、转换、有效期和策略，避免同名不同输入混用。
本模块只依赖标准库及核心模型，不读取文件，不加载DBC，不持有全局缓存；
样本转换、保持和表达式计算由相应执行模块完成。
"""

# 冻结数据类存元数据，哈希只处理明确的不可变原生输入。
from dataclasses import dataclass, field as dataclass_field
from hashlib import sha256

# 共享已校验模型和精确时间协议，不依赖被保护的旧链。
from .models import SessionSpec, SourceRef, SourceSpec, TimebaseSpec
from .types import BASE_FORBIDDEN_QUALITY, SignalDType, TimeType
from .units import require_number
from .unit_conversion import binding_version, converted_dtype, require_config_version, validate_conversion_v4
from .unit_registry import REGISTRY_VERSION
from .lookup import LookupTablePlan, validate_lookups
from .validation import require_identifier, require_scalar, require_text
from ..timebase.conversion import require_int64_ns


def _identity(value) -> str:
    """把已知不可变元数据编码为带类型的确定身份文本。

    参数: value为本模块内部的原生标量或tuple，可含无效原NaN/Inf。
    返回: str；保留bool/int区别及浮点位值，tuple用长度前缀防歧义。
    异常: TypeError为内部未声明结构；不读取文件或执行任意对象repr。
    """
    # tuple逐项编码并保留结构，避免分隔符碰撞。
    if isinstance(value, tuple):
        # 局部输出只用于计划身份，不是产品JSON序列化。
        parts = tuple(_identity(item) for item in value)
        # 每段字符长度明确，字段中的点号/冒号不会改变层级。
        return "t" + "".join(f"{len(item)}:{item}" for item in parts)
    # None与缺失观测保留明确类型。
    if value is None:
        # 不将None等价为0或空文本。
        return "n"
    # 原生类型分别编码，不让True与1共享身份。
    if type(value) is bool:
        # 布尔身份只存在两个值。
        return "b1" if value else "b0"
    # Python整数保留全部位值，不经float。
    if type(value) is int:
        # 负号和十进制值构成精确身份。
        return "i" + str(value)
    # float.hex保留-0及有限浮点身份，诊断NaN/Inf可稳定表示。
    if type(value) is float:
        # NaN不参与普通有效计算，但可存在原始行的输入身份。
        return "f" + value.hex()
    # 已校验文本原样保留，大小写及semantic点号不归一化。
    if type(value) is str:
        # 字符串类型标记避免与整数文本同一身份。
        return "s" + value
    # 只允许本模块明确构造的身份值。
    raise TypeError("绑定身份含未声明结构")


def _source_identity(source: SourceSpec) -> str:
    """保存内存来源定位、时间映射、观测域和实际行内容的身份。

    参数: source为已校验SourceSpec；原时间单位ns，原sequence不变。
    返回: SHA256文本；不同原内容不会只因同名来源而复用绑定。
    异常: TypeError为内部结构错误；无文件或旧reader副作用。
    """
    # 字典字段按名称规范排列，仅用于身份，不改变更新顺序。
    rows = tuple((row.time_ns, row.sequence, tuple(sorted(row.values.items()))) for row in source.rows)
    # 保留原始坐标/offset/范围，不把局部从0开始视为公共起点。
    payload = (source.name, source.source_type.value, source.timebase.timebase_id, source.timebase.time_type.value,
               source.timebase.origin, source.offset_ns, source.observation_start_ns,
               source.observation_end_ns, rows)
    # SHA输入完全来源于冻结模型，不调用任意外部序列化器。
    return sha256(_identity(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SignalDefinition:
    """声明原字段如何映射为分析信号，以及转换后值的类型、单位和有效期。

    name是表达式使用的简单别名，field保留原字段文本；valid_for_ns为正的有限
    有效期，None仅表示声明阶段等待DBC周期，不能交给实际状态计算。
    choices保存不可变的原编码与目标标签或bool配对。基础质量策略
    拒绝全部非零质量位，不接受任意质量策略。方向、位置及可选语义信息只保存
    调用者声明，不推断业务含义；本对象不保存随时间变化的值。
    input_sign_convention等方向证据属于核心模型元数据，不能据此认为公开JSON
    配置已经支持同名扩展字段。
    """

    name: str  # 当前计划简单别名。
    source: str  # 会话内显式来源名称。
    field: str  # memory原字段，不替换点号。
    dtype: SignalDType  # 转换后逻辑类型。
    unit: str  # 转换后单位，未知标签保留未校验状态。
    valid_for_ns: int | None  # 有限有效期，单位纳秒；None为尚待DBC周期的声明。
    input_unit: str | None = None  # 缺省使用unit，不推测原DBC单位。
    scale: int | float = 1  # 已解码值之后额外转换，包含方向因子。
    offset: int | float = 0  # 已解码值之后额外偏移。
    choices: tuple[tuple[int | bool | str, str | bool], ...] = ()  # 明示编码映射。
    valid_range: tuple[int | float, int | float] | None = None  # 转换后业务范围。
    invalid_values: tuple[int | float | bool | str | None, ...] = ()  # 明示原输入无效值。
    sample_policy: str = "backward_hold"  # 首版只实施有限向后保持。
    same_time_policy: str = "error"  # 可显式选择last_by_sequence，由状态模块按来源序号取最后值。
    semantic_id: str | None = None  # 可选领域字符串，不是DSL路径。
    semantic_contract_version: str | None = None  # 声明身份，不证明契约通过。
    mapping_version: str | None = None  # 当前映射版本身份。
    sign_convention: str | None = None  # 转换后方向，由调用者声明。
    measurement_location: str | None = None  # 可选测量位置，不从名称猜测。
    input_sign_convention: str | None = None  # 转换前方向证据，core typed元数据。
    direction_factor: int = 1  # 方向不变1，显式反转-1。
    config_version: int = dataclass_field(default=4, kw_only=True)  # 规则版本；低层系数已确定，不按省略推导。
    input_dtype: SignalDType | None = dataclass_field(default=None, kw_only=True)  # 配置推导前类型；不新增用户字段。
    code_dtype: SignalDType | None = dataclass_field(default=None, kw_only=True)  # 仅 v4 枚举的原始整数类型。
    capture_code: bool = dataclass_field(default=False, kw_only=True, compare=False, repr=False)  # 当前执行投影要求。
    unit_status: str = dataclass_field(init=False)  # 构造校验所得单位状态。

    def __post_init__(self) -> None:
        """校验完整声明并冻结默认输入单位及精确有效期。

        参数: 无额外参数；valid_for_ns为正int64纳秒，或尚待DBC周期的None。
        返回: None；unit_status为verified/unverified，未修改输入值。
        异常: TypeError为字段结构；ValueError为缺项/策略/映射/转换冲突；
            TimeOverflowError为有效期超界。数值样本失败由数值层生成质量原因。
        """
        # 配置版本决定单位规则，不能因新增目录改变旧声明。
        require_config_version(self.config_version)
        if self.code_dtype is not None:
            from .enum_codes import validate_code_dtype
            if self.config_version != 4 or self.dtype is not SignalDType.ENUM:
                raise ValueError('code_dtype 仅适用于 v4 枚举信号')
            validate_code_dtype(self.code_dtype, self.choices)
        if type(self.capture_code) is not bool or self.capture_code and self.code_dtype is None:
            raise ValueError('保留原始枚举码需声明 code_dtype')
        # 别名和来源都服从简单名称，不接受属性路径。
        require_identifier(self.name, "signal.name")
        # 当前会话显式定位来源，不能继承上次任务。
        require_identifier(self.source, "signal.source")
        # 原字段独立保留文本，合法同名绑定由名称空间校验。
        require_text(self.field, "signal.field")
        # dtype不是字符串占位，也不从值推断。
        if not isinstance(self.dtype, SignalDType):
            # 未解析的配置不能冒充typed定义。
            raise TypeError("signal.dtype必须为SignalDType")
        # 原始声明类型仅用于证明单位换算引起的提升，低层调用不猜缺省来源类型。
        if self.input_dtype is not None:
            if not isinstance(self.input_dtype, SignalDType):
                raise TypeError("input_dtype必须为SignalDType或None")
            if self.config_version != 4 or converted_dtype(self.input_dtype, self.scale, self.offset) is not self.dtype:
                raise ValueError("input_dtype与已确定的单位转换类型不一致")
        # 目标单位必填，未知标签可以显式未校验。
        require_text(self.unit, "signal.unit")
        # 默认表示没有额外单位变化，不补DBC信息。
        input_unit = self.unit if self.input_unit is None else require_text(self.input_unit, "signal.input_unit")
        # 声明可以等待DBC；已有数值仍须精确且有限，0不代表无限保持。
        valid_for_ns = (None if self.valid_for_ns is None else
                        require_int64_ns(self.valid_for_ns, "valid_for_ns"))
        if valid_for_ns is not None and valid_for_ns <= 0:
            # 错误工程声明执行前失败。
            raise ValueError("valid_for_ns必须大于0")
        # 转换系数拒绝bool、非有限和任意对象。
        require_number(self.scale, "signal.scale")
        # 偏移同样在配置入口校验。
        require_number(self.offset, "signal.offset")
        # 方向因子只支持明确不变或反转。
        if type(self.direction_factor) is not int or self.direction_factor not in (-1, 1):
            # 不接受truthiness或任意工程倍率作为方向。
            raise ValueError("direction_factor必须为1或-1")
        # 可选领域/版本/位置只保存非空原字符串，不建立全局目录。
        for key in ("semantic_id", "semantic_contract_version", "mapping_version", "sign_convention",
                    "measurement_location", "input_sign_convention"):
            # 只读取已声明dataclass字段，不用于表达式对象访问。
            value = getattr(self, key)
            # None表示未声明，不伪造缺省契约。
            if value is not None:
                # 空声明不等于有效可选元数据。
                require_text(value, f"signal.{key}")
        # 契约版本没有语义声明时不能独立伪装为绑定证明。
        if self.semantic_contract_version is not None and self.semantic_id is None:
            # 版本须关联可选语义身份。
            raise ValueError("semantic_contract_version需要semantic_id")
        # 明示反转同时保留原/目标方向，不从负scale猜测业务。
        if self.direction_factor == -1 and (self.input_sign_convention is None or self.sign_convention is None):
            # 缺少方向证据的反转不能用于契约校验。
            raise ValueError("方向反转必须声明转换前和转换后方向")
        # 只接受向后保持及明确的同时间策略，行为由状态模块实现。
        if self.sample_policy != "backward_hold" or self.same_time_policy not in ("error", "last_by_sequence"):
            # 不接受插值/未实现策略作为已支持声明。
            raise ValueError("首版仅支持backward_hold及error/last_by_sequence")
        # 固定不可变容器，避免后续外部修改映射或无效值。
        if not isinstance(self.choices, tuple) or not isinstance(self.invalid_values, tuple):
            # 不隐式接受可变dict/list。
            raise TypeError("choices/invalid_values必须为tuple")
        # 输入无效值保留类型，不让bool自动等同整数编码。
        for value in self.invalid_values:
            # 无效原标量可含NaN，数值层另行标记NONFINITE。
            require_scalar(value)
        # 编码身份类型化，避免Python的True==1掩盖冲突。
        keys = set()
        # 每条映射都需明确原编码和目标标签。
        for choice in self.choices:
            # tuple配对之外的结构不可定位。
            if not isinstance(choice, tuple) or len(choice) != 2:
                # 配置层不能传入半个声明。
                raise TypeError("choices各项必须为二元tuple")
            # 明示映射两端，不按顺序自动编号。
            code, label = choice
            # 原编码只接可精确比较的固定类型。
            if type(code) not in (int, bool, str):
                # 浮点/容器不能作为首版枚举编码。
                raise TypeError("choices原编码仅支持int/bool/str")
            # 类型加值构成明确原编码身份。
            key = (type(code), code)
            # 重复编码无法唯一定位业务标签。
            if key in keys:
                # 不取第一条或最后一条隐式覆盖。
                raise ValueError("choices原编码重复")
            # 当前声明中的唯一编码在局部集合登记。
            keys.add(key)
            # enum目标是公开逻辑标签，不允许数值别名。
            if self.dtype is SignalDType.ENUM:
                # 标签保留大小写和领域文本。
                require_text(label, "choices.label")
            elif self.dtype is SignalDType.BOOL:
                # 任意数值truthiness不属于声明布尔映射。
                if type(label) is not bool:
                    # 1不是合法目标True。
                    raise TypeError("bool choices目标必须为bool")
            else:
                # 数值信号的编码可作为数值处理，不套业务标签映射。
                raise ValueError("choices仅用于enum或bool")
        # enum必须有明确编码/标签域，不接任意字符串。
        if self.dtype is SignalDType.ENUM and not self.choices:
            # 空域不是可执行枚举声明。
            raise ValueError("enum需要非空choices")
        # 标签可由多个编码指向同一含义，域按第一次出现顺序稳定保留。
        if self.dtype in (SignalDType.BOOL, SignalDType.ENUM) and (self.scale != 1 or self.offset != 0):
            # 不对逻辑值施加数值缩放。
            raise ValueError("bool/enum不能声明数值转换")
        # 范围只支持转换后数值，两个端点都要明确。
        if self.valid_range is not None:
            # 不接列表或不完整端点。
            if not isinstance(self.valid_range, tuple) or len(self.valid_range) != 2:
                # 配置结构必须完整。
                raise TypeError("valid_range必须为二元tuple")
            # 逻辑bool/enum不得以数值区间验证业务含义。
            if self.dtype in (SignalDType.BOOL, SignalDType.ENUM):
                # 使用choices声明逻辑域。
                raise ValueError("bool/enum不能使用数值valid_range")
            # 范围端点原生有限，保留整数精度。
            lower = require_number(self.valid_range[0], "valid_range.lower")
            # 上限与下限采用相同入口。
            upper = require_number(self.valid_range[1], "valid_range.upper")
            # 不自动交换反向范围。
            if upper < lower:
                # 声明冲突须执行前拒绝。
                raise ValueError("valid_range上限必须不小于下限")
        # 已知单位校验关系，未知单位明确保留状态。
        status = validate_conversion_v4(input_unit, self.unit, self.scale, self.offset, self.direction_factor)
        # v4整数转换中的1.0等整数系数规范为int，保留安全定宽整数计算路径。
        if self.dtype in (SignalDType.INT64, SignalDType.UINT64):
            for coefficient in ('scale', 'offset'):
                value = getattr(self, coefficient)
                if type(value) is float and value.is_integer():
                    object.__setattr__(self, coefficient, int(value))
        # 冻结缺省输入单位，后续身份与转换都读取同一事实。
        object.__setattr__(self, "input_unit", input_unit)
        # 规范有效期为Python整数纳秒，不改变数值。
        object.__setattr__(self, "valid_for_ns", valid_for_ns)
        # 状态来自真实校验，不允许调用者填verified。
        object.__setattr__(self, "unit_status", status)

    def identity(self) -> tuple:
        """返回声明字段完整身份，供执行计划缓存和追溯使用。

        参数: 无；读取当前冻结声明。
        返回: tuple；含实际定位、转换、有效期、质量及语义/版本元数据。
        异常: 无主动异常；不使用全局缓存或当前样本值。
        """
        # 全部影响绑定/质量/单位的字段进入身份，基础质量固定九位全禁。
        payload = (self.name, self.source, self.field, self.dtype.value, self.unit, self.valid_for_ns,
                self.input_unit, self.scale, self.offset, self.choices, self.valid_range,
                self.invalid_values, self.sample_policy, self.same_time_policy, self.semantic_id,
                self.semantic_contract_version, self.mapping_version, self.sign_convention,
                self.measurement_location, self.input_sign_convention, self.direction_factor,
                self.unit_status)
        # 身份包含固定单位规则，避免不同规则的结果复用。
        if self.code_dtype is not None:
            payload += ('code_dtype', self.code_dtype.value)
        # 预设核对真实身份的末项质量策略；版本和原码类型不能占据该位置。
        return (*payload, self.config_version, REGISTRY_VERSION,
                None if self.input_dtype is None else self.input_dtype.value, BASE_FORBIDDEN_QUALITY)

    @property
    def unit_conversion_promoted(self) -> bool:
        """说明浮点类型是否由已知整数输入的单位换算引起。

        参数: 无。
        返回: 仅有整数输入证据且实际提升时为True。
        异常: 无；不依据样本数值猜类型。
        """
        # 显式FLOAT64但没有原输入声明时不能冒称整数提升。
        return (self.dtype is SignalDType.FLOAT64
                and self.input_dtype in (SignalDType.INT64, SignalDType.UINT64)
                and converted_dtype(self.input_dtype, self.scale, self.offset) is SignalDType.FLOAT64)


@dataclass(frozen=True)
class SynchronizationEvidence:
    """保存来源使用固定时间偏移进入公共分析时基的核实说明。

    source指定会话内来源，analysis_timebase指定目标时基，evidence保留调用者
    提供的依据。本模型检查声明结构，不检查物理设备、不估计漂移或改动偏移。
    来源缺少同步依据时仍可独立分析；参与联合计算时须满足同步检查。
    """

    source: str  # 明确会话内来源。
    analysis_timebase: TimebaseSpec  # offset映射后的公共分析基准。
    evidence: str  # 调用者声明的核实依据，不自动生成业务事实。

    def __post_init__(self) -> None:
        """校验显式来源和时基证据结构。

        参数: 无；读取source、analysis_timebase及evidence。
        返回: None；不更改来源或推断时间映射。
        异常: TypeError/ValueError为无效声明。
        """
        # 来源必须能在当前会话唯一定位。
        require_identifier(self.source, "synchronization.source")
        # 空依据不能当作已核实同步。
        require_text(self.evidence, "synchronization.evidence")
        # 目标分析时基也必须通过模型构造门槛。
        if not isinstance(self.analysis_timebase, TimebaseSpec):
            # 字典或字符串不提供完整公共起点身份。
            raise TypeError("analysis_timebase必须为TimebaseSpec")


@dataclass(frozen=True)
class SignalBindings:
    """检查并冻结一个会话的信号定义、实际来源和同步证据。

    signals与derived_names共用简单名称空间，每个原字段必须出现在本会话内存行中。
    identity包含实际内容、时基、转换和策略，来源同名也不能替代完整身份。
    本对象没有全局注册表，不继承其他任务绑定；值更新由状态执行器读取冻结输入，
    不会修改本对象。
    """

    session: SessionSpec  # 当前计划单会话来源上下文。
    signals: tuple[SignalDefinition, ...]  # 已声明原字段到别名的关联。
    derived_names: tuple[str, ...] = ()  # 实际派生定义由表达式层提供，此处只检查名称冲突。
    synchronization: tuple[SynchronizationEvidence, ...] = ()  # 明示固定offset依据。
    config_version: int | None = dataclass_field(default=None, kw_only=True)  # 缺省继承定义；空绑定默认4。
    extensions: object = dataclass_field(default=None, kw_only=True, repr=False)  # 仅接收宿主传入的不可变注册。
    lookups: tuple[LookupTablePlan, ...] = dataclass_field(default=(), kw_only=True)  # 数值标定表声明。
    identity: str = dataclass_field(init=False)  # 实际校验所得完整绑定SHA。

    def __post_init__(self) -> None:
        """检查统一名称空间、来源定位和同步证据，再构建身份。

        参数: 无；session/signals及可选derived_names/synchronization均为已校验且不可变的模型输入。
        返回: None；通过后所有字段保持不可变。
        异常: TypeError为结构；ValueError为名称、来源字段或证据冲突。
        """
        # 顶层结构不能以可变列表或未校验对象进入计划。
        if not isinstance(self.session, SessionSpec) or not all(isinstance(item, tuple) for item in
                (self.signals, self.derived_names, self.synchronization)):
            # 不隐式解析自由配置或无限迭代器。
            raise TypeError("绑定需要SessionSpec及tuple声明")
        # 来源名唯一性已由SessionSpec构造证明。
        sources = {source.name: source for source in self.session.sources}
        # 名称集合局部于当前计划，signals/derived不能各自重复。
        names = set()
        # 保留信号声明顺序，不取某个冲突项覆盖。
        for definition in self.signals:
            # 每项必须通过完整SignalDefinition校验。
            if not isinstance(definition, SignalDefinition):
                # 类名或dict占位不属于真实定义。
                raise TypeError("signals必须包含SignalDefinition")
            # 实际内存绑定没有待查询DBC，不允许未确定的有效期进入对齐内核。
            if definition.valid_for_ns is None:
                raise ValueError(f"{definition.name}有效期尚未确定；请提供period或valid_for")
            # 重复别名不能解析为唯一原字段。
            if definition.name in names:
                # 不自动加后缀或取第一项。
                raise ValueError(f"signal别名重复：{definition.name}")
            # 登记唯一别名供派生名称冲突检查。
            names.add(definition.name)
            # 来源必须在本会话存在，不能靠语义名称补齐。
            if definition.source not in sources:
                # 错误定位在编译前拒绝。
                raise ValueError(f"{definition.name}来源不存在：{definition.source}")
            # memory字段必须已在实际行中暴露，不猜列或读旧DBC。
            if not any(definition.field in row.values for row in sources[definition.source].rows):
                # 空来源没有已声明字段schema，不能声称字段可解析。
                raise ValueError(f"{definition.name}原字段不存在：{definition.field}")
        # 所有定义属于同一不可变版本；空绑定也可显式选择4。
        object.__setattr__(self, "config_version", binding_version(self.signals, self.config_version))
        validate_lookups(self.lookups, self.config_version)
        if self.extensions is not None:
            from ..extensions import ExtensionRegistry
            if type(self.extensions) is not ExtensionRegistry or self.config_version != 4:
                raise ValueError('extensions需要版本4及宿主ExtensionRegistry')
        # 派生声明也遵守同一简单别名规则。
        for name in self.derived_names:
            # 包括关键字及首版函数名冲突。
            require_identifier(name, "derived.name")
            # signals和derived统一校验，未生成表达式也不能隐藏同名。
            if name in names:
                # 不修改用户声明名称。
                raise ValueError(f"signals/derived名称冲突：{name}")
            # 保留派生名称登记事实，供后续表达式层接线。
            names.add(name)
        # 同步证据也只能一个来源一个明确目标。
        evidence_names = set()
        # 所有显式证据须关联实际来源和当前分析时基。
        for evidence in self.synchronization:
            # 保留typed证据结构，不接自由字典。
            if not isinstance(evidence, SynchronizationEvidence):
                # 不能以名称声明冒充完整同步依据。
                raise TypeError("synchronization需要SynchronizationEvidence")
            # 不存在/重复来源证据都是配置错误。
            if evidence.source not in sources or evidence.source in evidence_names:
                # 不默认选第一条同步说明。
                raise ValueError("同步证据来源不存在或重复")
            # 所有校准声明必须进入当前会话分析基准。
            if evidence.analysis_timebase != self.session.timebase:
                # 不接受指向其他会话时基的旧映射。
                raise ValueError("同步证据目标与会话分析时基不一致")
            # 记录该来源已有明确证据。
            evidence_names.add(evidence.source)
        # 完整实际输入身份避免跨任务同名不同数据误复用执行缓存。
        payload = (self.session.session_id, self.session.timebase.timebase_id, self.session.timebase.time_type.value,
                   self.session.timebase.origin, self.session.domain_start_ns, self.session.domain_end_ns,
                   tuple(_source_identity(source) for source in self.session.sources),
                   tuple(definition.identity() for definition in self.signals), self.derived_names,
                   tuple((item.source, item.analysis_timebase.timebase_id, item.analysis_timebase.time_type.value,
                          item.analysis_timebase.origin, item.evidence) for item in self.synchronization))
        # 即使没有信号，v4绑定也不能与旧空绑定共享身份。
        payload += (self.config_version, REGISTRY_VERSION)
        if self.extensions is not None:
            payload += ('host-extensions-v1', self.extensions.identity)
        if self.lookups:
            payload += ('lookup-table-v1', tuple(t.identity for t in self.lookups))
        # 身份由全部校验事实生成，不允许调用者提供假SHA。
        object.__setattr__(self, "identity", sha256(_identity(payload).encode("utf-8")).hexdigest())

    def resolve(self, name: str) -> SignalDefinition:
        """解析当前计划真实信号别名，不自动寻找semantic候选。

        参数: name为简单别名；派生名称由表达式层另行处理。
        返回: 对应冻结SignalDefinition。
        异常: ValueError为非法或未知别名；不访问Python对象属性。
        """
        # 与声明使用相同名称规则，不转换点号。
        require_identifier(name, "signal alias")
        # 当前会话逐项查找明确唯一引用。
        for definition in self.signals:
            # 比较原大小写完整别名。
            if definition.name == name:
                # 不返回其他任务中同名定义。
                return definition
        # 未注册名字不能推断为字段或领域语义。
        raise ValueError(f"未知信号别名：{name}；可用：{', '.join(item.name for item in self.signals)}")

    def source_ref(self, name: str) -> SourceRef:
        """给出当前会话下解析后的完整memory字段引用。

        参数: name为已定义信号别名。
        返回: SourceRef；含当前session_id、source_name和原field。
        异常: ValueError为未定义或非法别名。
        """
        # 先证明引用属于当前定义，不从全局映射继承。
        definition = self.resolve(name)
        # 完整会话身份使跨会话同名输入可以明确区别。
        return SourceRef(self.session.session_id, definition.source, definition.field)

    def require_synchronized(self, names: tuple[str, ...]) -> None:
        """在联合依赖执行前检查实际来源的公共分析基准。

        参数: names为参与同一表达式/指标的原信号别名tuple；单来源允许独立分析。
        返回: None；公共起点或显式固定offset依据齐全时通过。
        异常: TypeError为容器；ValueError为未知别名或同步缺项。
        """
        # 不接会被调用者更改的依赖容器。
        if not isinstance(names, tuple):
            # 编译器需显式给出当前节点依赖。
            raise TypeError("联合依赖names必须为tuple")
        # 同一来源多个信号不会制造额外同步要求。
        used = {self.resolve(name).source for name in names}
        # 单来源可在自己坐标上独立分析。
        if len(used) <= 1:
            # 未使用来源不参与当前绑定的证据检查。
            return
        # 只检查实际参与联合计算的来源。
        sources = {source.name: source for source in self.session.sources if source.name in used}
        # 显式证据已在构造时证明指向当前分析基准。
        evidenced = {item.source for item in self.synchronization}
        # 没有校准声明的来源需直接拥有相同公共起点。
        for source in sources.values():
            # 明示证据提供固定offset映射依据，不估计漂移。
            if source.name in evidenced:
                # offset在SourceSpec已检查范围，执行器按原映射应用。
                continue
            # absolute统一UTC；relative需timebase_id/origin共同一致。
            same = source.timebase.time_type is self.session.timebase.time_type and (
                source.timebase.time_type is TimeType.ABSOLUTE or source.timebase == self.session.timebase)
            # 仅offset数值或各自首点0不证明公共起点。
            if not same:
                # 错误列出缺项来源，调用者可补核实声明或独立分析。
                raise ValueError(f"联合依赖缺少同步依据：{source.name}；需要公共起点或固定offset核实证据")
