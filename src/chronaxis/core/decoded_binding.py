"""把实际封存解码历史的来源证据关联为可执行的轻量信号绑定。

输入为DeclarationBindings及逐来源DecodedSourceEvidence，输出不可变的
DecodedBindings与独立运行身份。先检查SHA格式、投影、会话和whole-source EOF，
再把完整实际证据与原声明身份纳入摘要；运行依赖还须存在于实际读取投影中。
声明身份只证明配置，实际证据应由执行层工厂完整重放封存历史后生成。
单独构造合法SHA文本或EOF字段本身不证明文件已读取、校验或具有这些内容。
本模块仅依赖标准库和核心声明模型，不持有样本历史、不读写文件或加载NumPy。
模型无关闭资源；执行层持有元数据的预算与生命周期由对应lease负责。
"""

# 冻结证据和运行身份；不引入数组、来源适配器或磁盘操作。
from dataclasses import dataclass, field
from hashlib import sha256
from .binding import SignalDefinition, _identity
from .declarations import DeclarationBindings
from .validation import require_identifier
from ..timebase.conversion import require_int64_ns


def _require_sha256(value: str, name: str) -> None:
    """只校验固定SHA-256文本格式，不声称摘要来自已核实文件。

    参数: value为64位小写十六进制文本；name为错误定位字段。
    返回: None；无数据读取或字符串归一化。
    异常: TypeError为非原生str；ValueError为长度或字符不符。
    """
    # 明确拒绝隐式str转换，保留工厂生成的规范摘要。
    if type(value) is not str:
        raise TypeError(f'{name}需要原生SHA-256字符串')
    # 固定字符域同时拒绝大写、空白、换行和非十六进制字符。
    if len(value) != 64 or any(character not in '0123456789abcdef' for character in value):
        raise ValueError(f'{name}需要64位小写十六进制SHA-256')


@dataclass(frozen=True)
class DecodedSourceEvidence:
    """保存工厂已核对的一份来源历史事实，字段冻结且不保存逐条样本。

    三份摘要分别关联实际描述、请求和规范历史，不以文件名代替数据身份。
    counts记录全源重放总量，projected_aliases保存实际请求投影顺序。
    观测端点允许未知且保持None；EOF只接受整个来源结束，不能冒充批次结束。
    模型仅验证证据结构，实际文件、字段、计数和摘要由执行层工厂负责核实。
    """

    source: str  # 当前声明中的唯一来源名。
    session_id: str  # 当前实际重放所属会话。
    description_sha256: str  # 实际来源描述及完整转换契约摘要。
    request_sha256: str  # 本次读取范围、投影和批次声明摘要。
    history_sha256: str  # 已核实规范历史字节摘要，不冒充原始日志摘要。
    sample_count: int  # 全源实际样本总数，非负原生整数。
    progress_count: int  # 全源实际批次进度记录数，至少包含最终EOF。
    projected_aliases: tuple[str, ...]  # 实际读取的唯一简单别名，空投影合法。
    observation_start_ns: int | None  # 原描述中的已知会话坐标首端；未知不补0。
    observation_end_ns: int | None  # 最终EOF中的已知会话坐标终点；未知不补周期。
    source_eof: bool  # 必须为True，表示整个配置来源已完成。

    def __post_init__(self) -> None:
        """检查固定身份、摘要格式、全源计数、投影和精确观测端点。

        参数: 无，读取冻结字段；时间单位均为整数纳秒。
        返回: None；合法整数端点规范为原生int，None保持未知。
        异常: TypeError/ValueError为结构或事实矛盾；时间溢出异常原样传播。
        副作用: 仅在构造期规范本对象端点，不访问来源或验证文件内容。
        """
        # 来源/会话名称不能借点号路径或任意对象绕过身份检查。
        require_identifier(self.source, 'decoded.source')
        require_identifier(self.session_id, 'decoded.session_id')
        # 三种证据用途不同，逐项校验而不把任一摘要当另一个摘要使用。
        for name, value in (('description_sha256', self.description_sha256),
                            ('request_sha256', self.request_sha256),
                            ('history_sha256', self.history_sha256)):
            _require_sha256(value, f'decoded.{name}')
        # bool不是计数；最终EOF至少对应一条实际进度记录。
        if type(self.sample_count) is not int or self.sample_count < 0:
            raise ValueError('decoded.sample_count需要非负原生int')
        if type(self.progress_count) is not int or self.progress_count < 1:
            raise ValueError('decoded.progress_count需要至少为1的原生int')
        # 冻结投影顺序，不隐式消除重复或接受可变列表。
        if type(self.projected_aliases) is not tuple:
            raise TypeError('decoded.projected_aliases需要tuple')
        for alias in self.projected_aliases:
            require_identifier(alias, 'decoded.projected_alias')
        if len(set(self.projected_aliases)) != len(self.projected_aliases):
            raise ValueError('decoded.projected_aliases不能重复')
        # 单个已知端点独立检查；不凭请求域或投影首样本推断未知端点。
        start = None if self.observation_start_ns is None else require_int64_ns(self.observation_start_ns, 'decoded.observation_start_ns')
        end = None if self.observation_end_ns is None else require_int64_ns(self.observation_end_ns, 'decoded.observation_end_ns')
        if start is not None and end is not None and end < start:
            raise ValueError('decoded来源观测终点早于起点')
        # 普通批次结束不能升级为可执行证据，只接真正全源耗尽的明确bool。
        if type(self.source_eof) is not bool or not self.source_eof:
            raise ValueError('decoded证据需要真正whole-source EOF=True')
        # 身份编码只接原生标量，整数规范保留精确坐标，不改变端点含义。
        object.__setattr__(self, 'observation_start_ns', start)
        object.__setattr__(self, 'observation_end_ns', end)


@dataclass(frozen=True)
class DecodedBindings:
    """冻结当前声明与实际解码历史证据，供编译和两个数值context入口使用。

    sources必须与声明来源一一对应，投影只能包含该来源声明的原信号别名。
    identity使用decoded-binding-v1前缀与完整证据，不能与声明或memory身份混用。
    resolve仅委托冻结声明；执行前仍检查实际投影和已有同步政策。
    本对象不保存SourceSpec.rows，也不能交给材料化完整内存历史的快捷入口。
    """

    declarations: DeclarationBindings  # 原配置关系与同步依据；其身份仍只是声明证明。
    sources: tuple[DecodedSourceEvidence, ...]  # 已核对来源事实，保留工厂的固定顺序。
    identity: str = field(init=False)  # 声明加实际证据的独立SHA-256运行身份。

    def __post_init__(self) -> None:
        """检查来源/会话/投影归属，再生成与完整实际证据关联的身份。

        参数: 无，读取declarations与sources；所有容器必须冻结。
        返回: None；构造identity，不重新读取历史或改变声明。
        异常: TypeError/ValueError为模型、重复/缺少来源、会话或投影冲突。
        """
        # 只接明确类型，声明或自由dict不能自行冒充实际来源证据。
        if (not isinstance(self.declarations, DeclarationBindings) or type(self.sources) is not tuple
                or any(not isinstance(item, DecodedSourceEvidence) for item in self.sources)):
            raise TypeError('解码绑定需要DeclarationBindings和DecodedSourceEvidence tuple')
        names = {item.source for item in self.sources}
        if len(names) != len(self.sources) or names != {item.name for item in self.declarations.sources}:
            raise ValueError('解码证据来源必须唯一且与声明完全对应')
        for evidence in self.sources:
            # 来源事实不能跨会话借用，即使字段/摘要文本相同也不接受。
            if evidence.session_id != self.declarations.session_id:
                raise ValueError('解码证据会话与当前声明不一致')
            aliases = {item.name for item in self.declarations.signals if item.source == evidence.source}
            if not set(evidence.projected_aliases).issubset(aliases):
                raise ValueError('解码投影包含其他来源或未声明别名')
        # 完整证据保留来源/请求/历史摘要、原范围、全源计数和实际投影；不只哈希配置。
        payload = ('decoded-binding-v1', self.declarations.identity,
                   tuple((item.source, item.session_id, item.description_sha256, item.request_sha256,
                          item.history_sha256, item.sample_count, item.progress_count, item.projected_aliases,
                          item.observation_start_ns, item.observation_end_ns, item.source_eof) for item in self.sources))
        object.__setattr__(self, 'identity', sha256(_identity(payload).encode('utf-8')).hexdigest())

    @property
    def signals(self) -> tuple[SignalDefinition, ...]:
        """读取当前冻结信号声明，不创建原始行或数值历史。

        参数: 无。返回: SignalDefinition tuple。异常: 无；属性不能重新赋值。
        """
        return self.declarations.signals

    @property
    def projected_signals(self) -> tuple[SignalDefinition, ...]:
        """按原声明顺序返回实际历史投影中的定义，不把未读取声明当作运行状态。

        参数: 无，使用当前已校验sources中的projected_aliases。
        返回: 原SignalDefinition对象组成的tuple；signals仍保留完整声明。
        异常: 分配或取消错误原样传播。调用执行层须先为有限索引和tuple预付费用。
        不读取历史、不改变绑定身份，也不把不同来源的投影误判为同步依据。
        """
        selected = None
        try:
            selected = {name for source in self.sources for name in source.projected_aliases}
            return tuple(item for item in self.declarations.signals if item.name in selected)
        finally:
            selected = None

    @property
    def derived_names(self) -> tuple[str, ...]:
        """读取当前统一名称空间中的派生别名。

        参数: 无。返回: str tuple。异常: 无；不把派生名称当实际读入列。
        """
        return self.declarations.derived_names

    def resolve(self, name: str) -> SignalDefinition:
        """按当前声明查找原信号定义，不推断字段或执行数值转换。

        参数: name为安全简单别名。返回: 当前SignalDefinition。
        异常: ValueError为非法或未声明名称；查找本身不证明该别名已投影。
        """
        return self.declarations.resolve(name)

    def require_synchronized(self, names: tuple[str, ...]) -> None:
        """先证明全部实际依赖已读取，再应用既有多源同步政策。

        参数: names为展开后的原信号依赖tuple；空依赖合法。
        返回: None；不修改投影、偏移或同步声明。
        异常: TypeError为错误容器；ValueError为未知/未投影依赖或同步缺项。
        """
        # 可变/无限依赖容器不能绕过冻结编译协议。
        if type(names) is not tuple:
            raise TypeError('解码联合依赖names必须为tuple')
        evidence_by_source = {item.source: item for item in self.sources}
        for name in names:
            definition = self.resolve(name)
            if name not in evidence_by_source[definition.source].projected_aliases:
                raise ValueError(f'运行依赖未在实际解码投影中：{name}')
        # offset数值或同名时基不替代原有核实同步依据；不另立宽松政策。
        self.declarations.require_synchronized(names)
