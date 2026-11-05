"""为当前消息表达式声明参数，并把独立消息仓事实关联为运行绑定。

ExpressionParameter将显式单位的配置数值规范成精确FLOAT64。MessageDeclarations
引用当前DeclarationBindings中选定来源的原SignalDefinition，不复制或虚构信号、
普通历史或TTL；当前policy只使用本条消息原字典，不继承上一条值。
MessageSourceEvidence只检查显式来源标签、全仓摘要、条数和首末的结构；
MessageBindings将其与完整声明身份关联。真正封存文件的EOF/SHA/条数验证由
执行层bind_message_store负责，单独构造证据不证明来源文件已经读取。

本模块只保存冻结配置与有限事实，不读文件、不执行表达式、不加载NumPy或
CAN，也不证明仓来自同一次CAN捕获或DBC单位已核实。这些关联留给实际生产端。
身份使用新版本前缀与固定字段的长度前缀增量SHA，不改变普通绑定的身份协议。
模型及调用者保留的配置由调用者拥有；执行工厂另付其新运行元数据费用。
"""

# 参数、证据及绑定均不可变；数值配置不从对象隐式推断。
from dataclasses import dataclass, field
from hashlib import sha256
from math import isfinite

from .binding import SignalDefinition
from .declarations import DeclarationBindings
from .unit_conversion import binding_version, require_config_version
from .unit_registry import REGISTRY_VERSION, resolve_unit
from .types import SignalDType
from .validation import require_identifier, require_text
from ..timebase.conversion import require_int64_ns


def _hash_parts(parts: tuple[str, ...]) -> str:
    """按固定模型字段顺序增量编码文本身份，失败不保活新增整段编码副本。

    参数: parts为本模块已检查的原生文本tuple，首项含独立版本前缀。
    返回: 小写SHA-256文本；每段UTF-8字节有长度前缀，分隔符不能造成碰撞。
    异常: 原Unicode、内存或取消错误；不调用外部repr或保存全量canonical文本。
    """
    raw = None
    try:
        digest = sha256()
        for part in parts:
            # 每次只保留一段编码；不同文本和字段边界均进入新身份。
            if type(part) is not str:
                raise TypeError('消息身份只编码已检查的原生文本')
            raw = part.encode('utf-8')
            digest.update(str(len(raw)).encode('ascii'))
            digest.update(b':')
            digest.update(raw)
            raw = None
        return digest.hexdigest()
    finally:
        # 执行工厂可能在此异常后抵费，TB不得留下本层新编码或parts容器。
        raw = parts = None


@dataclass(frozen=True)
class ExpressionParameter:
    """保存一个有明确单位、不可被对方重赋单位的FLOAT64配置参数。

    只接受原生有限int/float；int须能精确转为有限float，不能静默舍入。
    该参数不是信号或裸数字literal，不产生来源依赖和时间保持状态。
    """

    name: str  # 表达式使用的安全简单名称。
    value: int | float  # 构造后规范为有限原生float。
    unit: str  # 明确单位标签；不按对方信号自动改写。
    config_version: int = field(default=4, kw_only=True)  # 参数与绑定同版本，默认使用当前规则。
    unit_status: str = field(init=False)  # 只说明标签是否属于已有单位表。

    def __post_init__(self) -> None:
        """验证参数名称、精确数值及单位，不执行来源或表达式。

        参数: 无，读取name/value/unit。
        返回: None，value规范成FLOAT64可精确表示的原生float。
        异常: TypeError为非原生数值；ValueError为非有限、有损整数或声明非法。
        """
        # 独立参数也携带规则版本，不由绑定事后重解释。
        require_config_version(self.config_version)
        if type(self.name) is not str or type(self.unit) is not str:
            raise TypeError('表达式参数名称和单位需要原生str')
        require_identifier(self.name, 'parameter.name')
        require_text(self.unit, 'parameter.unit')
        if type(self.value) not in (int, float):
            raise TypeError('表达式参数只接受原生int/float，不能为bool')
        # 在配置边界证明精确性，不把参数有损转换拖到每条消息求值中。
        try:
            number = float(self.value)
        except OverflowError as exc:
            raise ValueError('表达式参数不能表示为有限FLOAT64') from exc
        if not isfinite(number) or type(self.value) is int and int(number) != self.value:
            raise ValueError('表达式参数必须能精确表示为有限FLOAT64')
        object.__setattr__(self, 'value', number)
        known = resolve_unit(self.unit) is not None
        object.__setattr__(self, 'unit_status', 'verified' if known else 'unverified')

    @property
    def dtype(self) -> SignalDType:
        """读取固定数值类型；参数: 无；返回: FLOAT64；异常: 无。"""
        return SignalDType.FLOAT64


@dataclass(frozen=True)
class MessageDeclarations:
    """为一个选定来源建立独立的当前消息名称空间，不制造运行证明。

    signals引用原声明中的同一SignalDefinition对象。原定义的转换声明保留，
    其TTL不在本模型执行；依赖仅能来自selected source。parameters及局部
    derived_names不能覆盖原计划任何signal/derived，也不能互相覆盖。
    """

    declarations: DeclarationBindings  # 完整原配置声明及身份，非实际文件证明。
    source: str  # 只允许这个原来源的信号参与当前消息表达式。
    parameters: tuple[ExpressionParameter, ...] = ()  # 有明确单位的配置参数。
    derived_names: tuple[str, ...] = ()  # 当前指标显式登记的局部派生名。
    message_policy: str = 'current_message-v1'  # 只看当前字典，不沿用缓存或TTL。
    config_version: int | None = field(default=None, kw_only=True)  # 继承原声明，参数必须同版。
    identity: str = field(init=False)  # 完整原配置与消息配置的独立声明SHA。

    def __post_init__(self) -> None:
        """核对来源、完整名称空间与policy，生成静态消息声明身份。

        参数: 无，读取冻结字段，不读取文件或DBC。
        返回: None；保原定义对象，不将声明身份当真实仓EOF证明。
        异常: TypeError为模型/容器错误；ValueError为来源、名称或policy冲突。
        """
        if not isinstance(self.declarations, DeclarationBindings):
            raise TypeError('消息声明需要DeclarationBindings')
        if type(self.source) is not str:
            raise TypeError('消息来源需要原生str')
        require_identifier(self.source, 'message.source')
        if self.source not in {item.name for item in self.declarations.sources}:
            raise ValueError('消息来源不在原声明中')
        if (type(self.parameters) is not tuple or type(self.derived_names) is not tuple
                or any(type(item) is not ExpressionParameter for item in self.parameters)):
            raise TypeError('消息参数与局部派生名称需要typed tuple')
        # 原声明即使无信号也有明确版本，参数不能引入另一套单位规则。
        version = self.declarations.config_version
        if self.config_version is not None and require_config_version(self.config_version) != version:
            raise ValueError('消息声明config_version与原声明不一致')
        binding_version(self.parameters, version)
        object.__setattr__(self, 'config_version', version)
        if type(self.message_policy) is not str or self.message_policy != 'current_message-v1':
            raise ValueError('消息policy仅支持current_message-v1')
        # 全原计划名称都受保护，不能利用selected source隐藏其他来源的名称冲突。
        names = {item.name for item in self.declarations.signals} | set(self.declarations.derived_names)
        for parameter in self.parameters:
            if parameter.name in names:
                raise ValueError('消息参数与原声明或其他参数名称冲突：' + parameter.name)
            names.add(parameter.name)
        for name in self.derived_names:
            if type(name) is not str:
                raise TypeError('消息局部派生名称需要原生str')
            require_identifier(name, 'message.derived_name')
            if name in names:
                raise ValueError('消息局部派生名称冲突：' + name)
            names.add(name)
        parts = None
        try:
            # 数量字段固定参数与派生分段；完整base身份含未选来源，不能遗漏配置变化。
            parts = ('message-declaration-v1', self.declarations.identity, self.source,
                     self.message_policy, str(len(self.parameters)))
            parts += tuple(value for item in self.parameters
                           for value in (item.name, item.value.hex(), item.unit, item.unit_status))
            parts += (str(len(self.derived_names)), *self.derived_names)
            # 空信号/仅参数绑定也必须携带当前规则版本。
            parts += (str(self.config_version), REGISTRY_VERSION)
            object.__setattr__(self, 'identity', _hash_parts(parts))
        finally:
            # 只清本层新身份容器，原声明/参数仍由调用者持有。
            parts = None

    @property
    def extensions(self):
        """读取宿主注册。参数: 无。返回: 冻结注册或None。异常: 无。"""
        return self.declarations.extensions

    @property
    def lookups(self):
        """读取普通声明中的标定表。参数: 无。返回: 冻结tuple。异常: 无。"""
        return self.declarations.lookups

    @property
    def signals(self) -> tuple[SignalDefinition, ...]:
        """选择同一原定义对象；参数: 无；返回: tuple；异常: 无主动异常。"""
        return tuple(item for item in self.declarations.signals if item.source == self.source)

    def resolve(self, name: str) -> SignalDefinition:
        """只定位本来源原信号，参数名称另由编译器处理。

        参数: name为安全简单信号别名。返回: 原SignalDefinition对象。
        异常: ValueError为未知、其他来源或非法名称；不从点号猜测原字段。
        """
        require_identifier(name, 'message.signal_alias')
        for definition in self.signals:
            if definition.name == name:
                return definition
        raise ValueError('未知或不属消息来源的信号别名：' + name)

    def require_synchronized(self, names: tuple[str, ...]) -> None:
        """检查实际依赖均在本来源，不借其他来源的同步声明引入缓存值。

        参数: names为展开后的原信号依赖tuple，空依赖合法。
        返回: None；单源当前字典不需要合并其他来源时钟。
        异常: TypeError为容器错误；ValueError为非本来源或未知依赖。
        """
        if type(names) is not tuple:
            raise TypeError('消息依赖names需要tuple')
        for name in names:
            self.resolve(name)


@dataclass(frozen=True)
class MessageSourceEvidence:
    """保存独立解码消息仓的有限事实，仅校结构而不声明真实回读已发生。

    decoder_profile/read_identity是仓内显式标签，不认证旧CAN来源。原序SHA
    包含记录和值/映射时间；首末可相同，空仓必须两端None且条数为0。
    """

    source: str  # 本消息来源。
    session_id: str  # 原声明会话。
    decoder_profile: str  # 显式解码来源标签，不冒充计算policy。
    read_identity: str  # 仓的显式读取标识，CAN同次关联由生产端另核。
    store_sha256: str  # 已封口全消息行流摘要。
    record_count: int  # 全decoded条数，不是普通历史样本数。
    first_time_ns: int | None  # 全仓首条映射坐标，空仓为None。
    last_time_ns: int | None  # 全仓最后坐标，不补采样周期。

    def __post_init__(self) -> None:
        """验证有限证据一致性，单独构造不能替代实际EOF校验。

        参数: 无，读取冻结字段。返回: None，已知时间规范成原生int。
        异常: TypeError/ValueError为类型、SHA、条数或首末矛盾；时间超界原样传播。
        """
        if any(type(value) is not str for value in (self.source, self.session_id,
                                                   self.decoder_profile, self.read_identity)):
            raise TypeError('消息证据来源、会话及读取标签需要原生str')
        require_identifier(self.source, 'message_evidence.source')
        require_identifier(self.session_id, 'message_evidence.session_id')
        require_text(self.decoder_profile, 'message_evidence.decoder_profile')
        require_text(self.read_identity, 'message_evidence.read_identity')
        if type(self.store_sha256) is not str:
            raise TypeError('消息仓摘要需要原生str')
        if (len(self.store_sha256) != 64
                or any(char not in '0123456789abcdef' for char in self.store_sha256)):
            raise ValueError('消息仓摘要需要64位小写十六进制SHA-256')
        if type(self.record_count) is not int or self.record_count < 0:
            raise ValueError('消息条数需要非负原生int')
        if self.record_count == 0:
            if self.first_time_ns is not None or self.last_time_ns is not None:
                raise ValueError('空消息仓首末必须为None')
            return
        if self.first_time_ns is None or self.last_time_ns is None:
            raise ValueError('非空消息仓必须有真实首末时间')
        # 共享int64单端点规则允许真实零长观测，不计算两端差值造成溢出。
        first = require_int64_ns(self.first_time_ns, 'message_evidence.first_time_ns')
        last = require_int64_ns(self.last_time_ns, 'message_evidence.last_time_ns')
        if last < first:
            raise ValueError('消息仓终点早于起点')
        object.__setattr__(self, 'first_time_ns', first)
        object.__setattr__(self, 'last_time_ns', last)


@dataclass(frozen=True)
class MessageBindings:
    """关联消息声明与实际仓证据，保持独立于普通DecodedBindings的运行身份。

    证据实际性由bind_message_store完整回读负责；本模型只校结构/归属。
    不证明普通历史、TTL、DBC字段单位或同次CAN捕获，也不保存逐条记录。
    """

    declarations: MessageDeclarations  # 单源消息配置及完整原声明身份。
    evidence: MessageSourceEvidence  # 执行工厂核实后的仓事实，非手造即证明。
    config_version: int | None = field(default=None, kw_only=True)  # 继承消息声明，不允许运行时切换。
    identity: str = field(init=False)  # 独立message-binding-v1身份。

    def __post_init__(self) -> None:
        """核对声明与证据来源/会话，增量生成有限运行身份。

        参数: 无，读取declarations/evidence。返回: None，不再次打开消息仓。
        异常: TypeError为模型错误；ValueError为来源/会话不符；编码或取消原错传播。
        """
        if not isinstance(self.declarations, MessageDeclarations) or not isinstance(self.evidence, MessageSourceEvidence):
            raise TypeError('消息运行绑定需要MessageDeclarations和MessageSourceEvidence')
        # 运行绑定不重设消息参数和信号的已冻结版本。
        version = self.declarations.config_version
        if self.config_version is not None and require_config_version(self.config_version) != version:
            raise ValueError('消息运行绑定config_version与声明不一致')
        object.__setattr__(self, 'config_version', version)
        if (self.evidence.source != self.declarations.source
                or self.evidence.session_id != self.declarations.declarations.session_id):
            raise ValueError('消息仓证据的来源或会话与当前声明不符')
        parts = None
        try:
            # 每一证据字段都进入独立身份，不把read标签或同名配置单独当输入证明。
            evidence = self.evidence
            parts = ('message-binding-v1', self.declarations.identity, evidence.source,
                     evidence.session_id, evidence.decoder_profile, evidence.read_identity,
                     evidence.store_sha256, str(evidence.record_count),
                     'none' if evidence.first_time_ns is None else str(evidence.first_time_ns),
                     'none' if evidence.last_time_ns is None else str(evidence.last_time_ns))
            object.__setattr__(self, 'identity', _hash_parts(parts))
        finally:
            # 原错误可被调用者保留，执行层抵费后不由本TB留下新身份容器。
            parts = None

    @property
    def extensions(self):
        """读取宿主注册。参数: 无。返回: 冻结注册或None。异常: 无。"""
        return self.declarations.extensions

    @property
    def lookups(self):
        """读取消息声明中的标定表。参数: 无。返回: 冻结tuple。异常: 无。"""
        return self.declarations.lookups

    @property
    def signals(self) -> tuple[SignalDefinition, ...]:
        """读取同一原信号定义；参数: 无；返回: tuple；异常: 无主动异常。"""
        return self.declarations.signals

    @property
    def parameters(self) -> tuple[ExpressionParameter, ...]:
        """读取冻结配置参数；参数: 无；返回: tuple；异常: 无。"""
        return self.declarations.parameters

    @property
    def derived_names(self) -> tuple[str, ...]:
        """读取显式局部派生名；参数: 无；返回: tuple；异常: 无。"""
        return self.declarations.derived_names

    def resolve(self, name: str) -> SignalDefinition:
        """按单来源原定义定位信号，不从证据标签生成字段。

        参数: name为安全别名。返回: 原SignalDefinition。
        异常: ValueError为非法、未知或其他来源名称。
        """
        return self.declarations.resolve(name)

    def require_synchronized(self, names: tuple[str, ...]) -> None:
        """执行前复核全部依赖属于本来源，不执行普通TTL或时钟合并。

        参数: names为原信号依赖tuple。返回: None。
        异常: TypeError/ValueError为容器或非本来源依赖。
        """
        self.declarations.require_synchronized(names)
