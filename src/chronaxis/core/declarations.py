"""在读取数据之前检查来源、信号和派生名称声明，生成不可变的声明绑定。

输入为来源定位、时基、请求范围、信号定义和同步证据；输出DeclarationBindings
及其SHA-256身份。函数只检查配置关系，不证明文件、DBC字段或实际观测存在，
也不创建虚拟样本。静态表达式检查可使用这些声明；实际解释器仍需包含内存数据
的SignalBindings。本模块只依赖标准库和核心模型，没有文件操作、样本计算、
全局注册或执行计划缓存。
"""

# 冻结声明并为规范身份计算稳定摘要。
from dataclasses import dataclass, field
from hashlib import sha256
# 复用已验契约与同步证据，不放宽实际绑定校验。
from .binding import SignalDefinition, SynchronizationEvidence, _identity
# 时基和范围已经独立验证，不借空SessionSpec制造实际来源。
from .models import Interval, TimebaseSpec
from .types import TimeType
from .validation import require_identifier, require_text
from ..timebase.conversion import require_int64_ns


@dataclass(frozen=True)
class DeclaredSource:
    """保存一个尚未读取的来源定位，以及其声明的固定时间映射。

    input_identity包含规范配置中的路径顺序、格式和处理配置标识，不是文件内容
    哈希。offset_ns是整数纳秒偏移；模型不会估计漂移。字段实际存在性由来源执行
    接口另行检查，不能凭声明认定数据已读取。全部字段不可变。
    """

    name: str  # 当前计划来源名。
    timebase: TimebaseSpec  # 原始来源坐标。
    input_identity: str  # 规范声明身份，与实际数据身份分别保存。
    offset_ns: int = 0  # 显式固定偏移，不自动估计漂移。

    def __post_init__(self) -> None:
        """校验声明结构，保持声明身份与实际内容证据保持分开。

        参数: 无；读取name/timebase/input_identity/offset_ns。
        返回: None，冻结声明。
        异常: TypeError/ValueError/TimeOverflowError为配置错误。
        """
        # 所有名称遵守统一安全规则。
        require_identifier(self.name, 'source.name')
        # 规范身份必须明确提供，不凭文件名猜测。
        require_text(self.input_identity, 'source.input_identity')
        # offset必须保持定宽整数。
        require_int64_ns(self.offset_ns)
        # 时基不得使用未校验字典。
        if not isinstance(self.timebase, TimebaseSpec):
            # 静态接口也不接无类型占位。
            raise TypeError('声明来源需要TimebaseSpec')


@dataclass(frozen=True)
class DeclarationBindings:
    """冻结一个计划的来源、信号名称和同步关系，供执行前检查使用。

    signals与derived_names共用名称空间。identity只证明配置声明；来源路径、
    处理配置、转换或有效期变化会改变它。模型不验证文件内容、实际列或DBC
    元数据，不能代替执行数据绑定。同步检查只针对当前节点实际使用的来源。
    """

    session_id: str  # 当前会话声明。
    timebase: TimebaseSpec  # 计划分析坐标。
    domain: Interval | None  # 用户请求范围；None声明整文件无时间筛选，不表示无观测。
    sources: tuple[DeclaredSource, ...]  # 保留声明原顺序。
    signals: tuple[SignalDefinition, ...]  # 已校验单信号契约。
    derived_names: tuple[str, ...] = ()  # signals统一名称空间。
    synchronization: tuple[SynchronizationEvidence, ...] = ()  # 显式核实依据。
    identity: str = field(init=False)  # 配置身份，不是执行绑定SHA。

    def __post_init__(self) -> None:
        """检查名称、来源和显式同步关系，并生成声明身份。

        参数: 无；输入均为已经校验的不可变声明模型。
        返回: None；不读取任何样本、文件或DBC。
        异常: TypeError/ValueError为结构错误、名称冲突、来源错误或同步关系冲突。
        """
        # 会话名采用同一标识符规则。
        require_identifier(self.session_id, 'dataset.session')
        # 容器不得在构造后被调用者改写。
        if (not isinstance(self.timebase, TimebaseSpec)
                or self.domain is not None and not isinstance(self.domain, Interval)
                or any(type(items) is not tuple for items in (self.sources, self.signals, self.derived_names, self.synchronization))):
            # 不冻结任意迭代器或未知对象。
            raise TypeError('声明绑定需要typed时基/范围与tuple容器')
        # 单项必须由对应模型校验，不使用duck typing。
        if any(not isinstance(item, DeclaredSource) for item in self.sources) or any(not isinstance(item, SignalDefinition) for item in self.signals):
            # 静态编译也不接受伪造类名。
            raise TypeError('声明绑定需要DeclaredSource/SignalDefinition')
        # 来源表只属于当前计划。
        sources = {item.name: item for item in self.sources}
        # 重复来源不能字典覆盖。
        if len(sources) != len(self.sources):
            # 没有自动选取第一个来源的回退。
            raise ValueError('source.name重复')
        # 所有原信号和派生名称必须唯一。
        names = set()
        # 原字段只检查已声明来源，不声称实际存在。
        for definition in self.signals:
            # 完整单信号契约已经校验。
            if definition.source not in sources or definition.name in names:
                # 定位声明中实际冲突的信号。
                raise ValueError(f'{definition.name}来源不存在或别名重复')
            # 防止派生与当前信号重名。
            names.add(definition.name)
        # 派生名称不以点号或函数名绕过白名单。
        for name in self.derived_names:
            # 与实际执行绑定使用同一规则。
            require_identifier(name, 'derived.name')
            # 声明整个名称空间，未引用也不能隐藏冲突。
            if name in names:
                # 保留用户名称，不加后缀。
                raise ValueError(f'signals/derived名称冲突：{name}')
            # 登记下一个冲突校验点。
            names.add(name)
        # 同步声明必须唯一且指向当前计划。
        evidenced = set()
        # 不从机器时钟或两文件首点为0推断同步。
        for evidence in self.synchronization:
            # 正确类型和目标是声明有效性的必要条件。
            if not isinstance(evidence, SynchronizationEvidence):
                # 不以文字字符串冒充typed同步说明。
                raise TypeError('同步需要SynchronizationEvidence')
            # 重复/未知来源及不同分析时基都拒绝。
            if evidence.source not in sources or evidence.source in evidenced or evidence.analysis_timebase != self.timebase:
                # 不静默选一个映射。
                raise ValueError('同步来源重复/未知或目标时基不一致')
            # 保留已核实来源声明集合。
            evidenced.add(evidence.source)
        # 静态身份显式使用独立版本前缀，不与真实绑定共用证明。
        # 已有显式Interval仍使用原v1字节；无筛选声明以独立v2前缀和None端点表示。
        version = 'declaration-v1' if self.domain is not None else 'declaration-v2-no-time-request'
        payload = (version, self.session_id, self.timebase.timebase_id, self.timebase.time_type.value, self.timebase.origin,
                   None if self.domain is None else self.domain.start_ns,
                   None if self.domain is None else self.domain.end_ns,
                   tuple((item.name, item.timebase.timebase_id, item.timebase.time_type.value, item.timebase.origin, item.offset_ns, item.input_identity) for item in self.sources),
                   tuple(item.identity() for item in self.signals), self.derived_names,
                   tuple((item.source, item.evidence) for item in self.synchronization))
        # 所有身份材料是已校验结构，不调用外部对象repr。
        object.__setattr__(self, 'identity', sha256(_identity(payload).encode('utf-8')).hexdigest())

    def resolve(self, name: str) -> SignalDefinition:
        """定位当前声明中的唯一信号别名。

        参数: name简单别名。
        返回: 当前计划SignalDefinition。
        异常: ValueError为名称非法或未知。
        """
        # 不把semantic点号转换成别名。
        require_identifier(name, 'signal alias')
        # 只查当前声明集合。
        for definition in self.signals:
            # 保留大小写敏感身份。
            if definition.name == name:
                # 不继承上个任务的输入。
                return definition
        # 未知信号不能通过空数据隐式创建。
        raise ValueError(f'未知信号别名：{name}')

    def require_synchronized(self, names: tuple[str, ...]) -> None:
        """按实际联合依赖检查声明的公共时间基准。

        参数: names为原信号简单别名tuple。
        返回: None，单来源或公共起点/显式同步依据齐备时通过。
        异常: TypeError/ValueError为容器、别名或同步缺项。
        """
        # 与实际绑定保持相同的依赖接口。
        if type(names) is not tuple:
            # 不接受可变或无限依赖列表。
            raise TypeError('联合依赖names必须为tuple')
        # 单来源多个信号只产生一个同步成员。
        used = {self.resolve(name).source for name in names}
        # 独立来源可在自己坐标中校验。
        if len(used) <= 1:
            # 未使用来源不参与当前声明的证据检查。
            return
        # 构造已校验所有证据的来源/目标关系。
        evidenced = {item.source for item in self.synchronization}
        # 联合计算只检查实际参与来源。
        for source in self.sources:
            # 未参与或已有显式固定映射的来源无需重复声明公共起点。
            if source.name not in used or source.name in evidenced:
                # 不自动估计其他来源的漂移。
                continue
            # absolute坐标已统一为UTC；relative坐标须有相同的完整起点声明。
            same = source.timebase.time_type is self.timebase.time_type and (source.timebase.time_type is TimeType.ABSOLUTE or source.timebase == self.timebase)
            # 数值offset本身不能证明同步。
            if not same:
                # 提供具体缺项位置供配置修正。
                raise ValueError(f'联合依赖缺少同步依据：{source.name}；需要公共起点或固定offset核实证据')
