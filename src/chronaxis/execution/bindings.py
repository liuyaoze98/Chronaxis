"""核对实际封存解码历史，建立可执行表达式所需的独立运行绑定。

输入为当前DeclarationBindings和sealed DecodedHistoryStore，输出须close的元数据持有对象。
先核对请求/字段/完整归一化与时基指纹，再逐源有限重放到实际文件EOF，校验原SHA和计数。
运行身份同时包含声明、实际描述/投影/历史与原EOF范围；不以静态表达式或猜测SHA替代核对。
只重放新解码历史，不重读旧原日志/DBC，不保留全样本，不重新转换或计算表达式。
固定元数据和构造临时量先计账，单行读预算由历史游标拥有，失败/取消关闭自有游标。
外部保存已取得bindings/CompiledExpression超过lease寿命时须另负责该元数据持有量。
同一个真实DecodedBindingLease从首次预约前持有固定费、当前reader及有限临时状态；
未返回且持续清理失败时由原异常decoded_binding_lease_cleanup_owner交接。
单笔预约/释放返回后取消也按实际交易更新槽，不重复归还借用history或其他reader费用。
纯契约校验入口供不保存普通历史的内部扫描复用；它不生成读取证据，公共工厂仍检查实际磁盘EOF。
"""

# 受控类型树生成规范摘要，不执行任意对象repr或反射表达式。
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from hashlib import sha256
from ..core.binding import SignalDefinition, _identity
from ..core.decoded_binding import DecodedBindings, DecodedSourceEvidence
from ..core.declarations import DeclarationBindings, DeclaredSource
from ..core.types import SignalDType
from ..results.errors import ResultClosedError, ResultFormatError
from ..results.spool import _cleanup_owner, _reserve_owned_ram, _release_owned_ram
from ..sources.descriptions import describe_fields, source_timebase_identity
from ..sources.models import ReadRequest, SourceDescription
from .history import DecodedHistoryStore, _metadata_bytes
from .history_records import HistoryProgress, HistorySample


def _fingerprint_value(value):
    """把已校验冻结元数据转换为纯标量/tuple，不丢字段或来源定位。

    参数: value为当前typed描述/请求元数据树。返回: _identity支持的不可变树。
    异常: TypeError为未声明结构；调用方已申请元数据构造预算。
    """
    if is_dataclass(value) and not isinstance(value, type):
        return (type(value).__name__, tuple((item.name, _fingerprint_value(getattr(value, item.name))) for item in fields(value)))
    if isinstance(value, Mapping):
        # JSON键已检查为str；排序只用于身份，不改变读取/字段/文件次序。
        return tuple((key, _fingerprint_value(value[key])) for key in sorted(value))
    if type(value) is tuple:
        return tuple(_fingerprint_value(item) for item in value)
    if isinstance(value, Enum):
        return (type(value).__name__, value.value)
    if value is None or type(value) in (str, int, float, bool):
        return value
    raise TypeError('运行绑定元数据含未支持类型')


def _fingerprint(value):
    """计算完整typed树摘要。参数: value冻结元数据。返回: SHA256文本。异常: 树/分配错误。"""
    return sha256(_identity(_fingerprint_value(value)).encode('utf-8')).hexdigest()


class DecodedBindingLease:
    """从首次预约到返回绑定持有唯一真实费用及当前回放reader。

    _cost/_held_cost只含工厂原固定金额；_reader拥有独立FD及它自己的费用。
    _bindings仅在完整EOF和当前reader清完后开放。_closing/_failed期间禁止借出，
    直到实际reader和固定费都清完才closed，不关闭借用history/scan或删除文件。
    """

    def __init__(self, budget):
        """在首次外部操作前初始化真实责任槽，不申请预算或打开文件。

        参数: budget为调用方历史的共享预算。返回: 尚未取得固定费或完成绑定的lease。
        异常: 无主动异常；构造不接已经付费的裸金额，也不复制样本。
        """
        # 费用与子reader必须先可清理；工厂后续每笔真实交易才登记已取得金额。
        self._budget, self._cost, self._held_cost = budget, 0, 0
        self._bindings = self._reader = self._current = None
        self._history = self._declarations = None
        self._evidence = self._definitions = self._described = None
        self._closed = self._closing = self._failed = False

    @property
    def bindings(self) -> DecodedBindings:
        """读取不可变运行绑定。参数: 无。返回: DecodedBindings。异常: ResultClosedError为关闭。"""
        if self._closed or self._closing or self._failed or self._bindings is None:
            raise ResultClosedError('解码运行绑定未完成、已关闭或正在清理')
        return self._bindings

    @property
    def closed(self) -> bool:
        """读取lease状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    def _close_reader(self):
        """关闭本lease唯一实际reader，失败仍保留未完成的子责任。

        参数: 无。返回: None。异常: 原reader.close错误传播；完成后取消不留重复释放槽。
        """
        if self._reader is None:
            return
        # 正常返回即结束责任；真实reader已经closed后才抛错也已完成，不再二次抵销。
        try:
            self._reader.close()
        except BaseException:
            if getattr(self._reader, 'closed', False):
                self._reader = None
            raise
        else:
            self._reader = None

    def _clear_temporary(self):
        """结束有限工厂临时引用，不关闭借用对象。

        参数: 无。返回: None。异常: 无主动异常；不遍历原rows或删除历史。
        """
        self._current = self._evidence = self._definitions = self._described = None
        self._history = self._declarations = None

    def close(self):
        """先关真实reader，再丢自有元数据并逐笔归还固定费。

        参数: 无。返回: None，完成后幂等。异常: 原FD/预算错误可重试，释放后取消不重复扣账。
        副作用: 只关闭本lease的当前reader，不关闭调用方history/scan/其他reader。
        """
        if self._closed:
            return
        # 一旦开始清理就拒绝借出绑定；子FD和子费用未清完时保留本固定费及全部责任。
        self._closing = True
        # 单行内容借reader费用存活，先结束引用，避免子释放后取消仍留下长样本。
        self._current = None
        self._close_reader()
        self._bindings = None
        self._clear_temporary()
        _release_owned_ram(self, self._cost, '_cost')
        self._closed = True


def _require_empty_source_scan(source, history, observed_scans):
    """用本历史的真实扫描证明无字段来源的完整时钟，不从空描述猜测。

    参数: source为原DeclaredSource；history为sealed历史；observed_scans为真实扫描tuple。
    返回: None。异常: ValueError/ResultClosedError为缺失、重复、失效或不对应的证明。
    不重新读取原CSV，不复制原行；后续工厂仍须逐源核当前历史文件的真实EOF。
    """
    matches = 0
    for scan in observed_scans:
        # getter只在scan仍活且成功完成时可用；同名不同历史不能冒充本次读取。
        if scan.closed or scan.failed or not scan.finished:
            raise ValueError('无字段来源的扫描证明须真实完成且仍可用')
        plan = scan.source_plan
        if plan.name not in history.validators:
            raise ValueError('无字段来源的扫描不能包含当前历史之外的来源')
        if plan.name != source.name:
            continue
        matches += 1
        validator = history.validators[source.name]
        completion = history.source_completions[source.name]
        observation = scan.observation
        if (scan.history is not history or scan.request is not validator.request
                or plan.input_identity != source.input_identity
                or plan.config.timebase != source.timebase or plan.config.offset_ns != source.offset_ns
                or scan.history_sha256 != history.hashes[source.name].hexdigest()
                or scan.counts != tuple(history.counts[source.name])
                or observation.source != source.name or observation.session_id != validator.request.session_id
                or not observation.source_eof or not completion.source_eof
                or observation.observed_end_ns != completion.observed_end_ns):
            raise ValueError('无字段来源的真实扫描与当前声明、请求或历史证明不符')
    if matches != 1:
        raise ValueError('无字段来源需唯一真实扫描的完整时基偏移证明')


def require_decoded_source_contract(declarations: DeclarationBindings, source: DeclaredSource,
                                    description: SourceDescription, request: ReadRequest) -> dict[str, SignalDefinition]:
    """只核一来源的声明、实际描述和请求合同，保留所有原信号定义。

    参数: declarations/source为同一当前声明；description/request为调用方实际读取
        使用的原typed对象。未用声明可以保留，但无实际字段时投影必须为空；调用方仍须独立核实
        同一次真实扫描的完整时基/偏移/来源身份和完成事实，本函数不认证扫描或EOF。
    返回: 该来源全部别名到原SignalDefinition对象的dict；不裁成表达式依赖子集，
        不生成DecodedBindings、DecodedSourceEvidence或假历史SHA。
    异常: TypeError为非规定模型；ValueError为会话、domain、来源、完整时钟、
        投影或字段/类型/单位/完整转换指纹不符。分配和取消错误原样传播。
    副作用: 无文件、读取、预算或数值操作。调用方预付有限元数据工作区并负责后续
        样本、全量观测和真实EOF证明；公共历史绑定仍必须完整核验实际磁盘文件。
    """
    definitions = described = clock_identity = definition = field = expected = None
    try:
        # 模型构造已经保证名称唯一与字段来源一致；纯入口不能依赖某个历史构造器
        # 曾替调用方做过类型检查，也不能接受同名却不属于当前声明的来源。
        if (not isinstance(declarations, DeclarationBindings) or not isinstance(source, DeclaredSource)
                or not isinstance(description, SourceDescription) or not isinstance(request, ReadRequest)):
            raise TypeError('来源合同需要typed声明/来源/描述/请求')
        if source not in declarations.sources or description.name != source.name:
            raise ValueError('实际描述来源与当前声明不对应')
        if (request.session_id != declarations.session_id or request.domain_start_ns != (declarations.domain.start_ns if declarations.domain is not None else None)
                or request.domain_end_ns != (declarations.domain.end_ns if declarations.domain is not None else None) or description.timebase_id != source.timebase.timebase_id):
            raise ValueError('实际读取会话/domain/时基与当前声明不符')
        definitions = {item.name: item for item in declarations.signals if item.source == source.name}
        described = {item.name: item for item in description.fields}
        clock_identity = source_timebase_identity(source.timebase, source.offset_ns)
        # 时钟检查覆盖全部描述字段，不因当前请求空投影或未使用某字段而跳过。
        if not description.fields:
            if request.signal_names:
                raise ValueError('无实际字段描述时读取投影必须为空，时钟须另以真实扫描证明')
        elif any(item.field.locator.get('source_timebase_sha256') != clock_identity
                 or item.field.locator.get('offset_ns') != source.offset_ns for item in description.fields):
            raise ValueError('实际来源缺完整时基偏移证据或与当前声明不符')
        if not set(request.signal_names) <= definitions.keys():
            raise ValueError('实际读取投影包含当前未声明别名')
        # 部分投影只核实际请求字段；未用声明保留为静态定义，不声称已经读取。
        for name in request.signal_names:
            definition = definitions[name]
            field = described.get(name)
            expected = describe_fields(source.name, (definition,))[0]
            if (field is None or field.field.field != definition.field or field.dtype is not definition.dtype
                    or field.unit != definition.unit or any(field.metadata.get(key) != value for key, value in expected.metadata.items())):
                raise ValueError('实际字段/完整转换/原时基偏移与当前声明不符或缺指纹')
        return definitions
    finally:
        # 失败后调用方可释放其合同费用；本层原异常frame不额外保活新索引/描述副本。
        definitions = described = clock_identity = definition = field = expected = None
        declarations = source = description = request = None


def bind_decoded_history(declarations: DeclarationBindings, history: DecodedHistoryStore,
                         *, observed_scans=()) -> DecodedBindingLease:
    """先核对当前契约，再完整重放所有来源，只有实际EOF校验后才返回运行绑定。

    参数: declarations当前配置声明；history该会话已seal的新历史，不能是building/closed；
        observed_scans可选真实完成扫描tuple，只为无声明字段来源补完整时钟证明。
    返回: DecodedBindingLease，样本不保留，来源摘要/计数/投影/EOF事实纳入bindings身份。
    异常: 契约/损坏/预算/文件/取消错误原样传播；持续清理失败由原异常的
        decoded_binding_lease_cleanup_owner持真实reader及费用，恢复后可close。
    """
    if not isinstance(declarations, DeclarationBindings) or not isinstance(history, DecodedHistoryStore):
        raise TypeError('运行绑定需要DeclarationBindings和DecodedHistoryStore')
    # 局部导入避免一般绑定入口提前加载来源读取协调器；不接受手造观测端点模型。
    from .observed_ingestion import ObservedSourceScan
    if type(observed_scans) is not tuple or any(type(scan) is not ObservedSourceScan for scan in observed_scans):
        raise TypeError('无字段绑定证明需实际ObservedSourceScan tuple')
    history._check('sealed')
    if {item.name for item in declarations.sources} != set(history.validators):
        raise ValueError('当前声明与实际历史来源不对应')
    # 同一个真实owner贯穿预约、回放及返回，首次预算更新后取消不会落在保护块之外。
    owner = DecodedBindingLease(history.budget)
    try:
        # 固定公式保持原额；单行读取另由原游标预算承担，不依据共享余额猜测所有权。
        owner._history, owner._declarations = history, declarations
        cost = 32768 + len(declarations.sources) * 8192 + len(declarations.signals) * 2048 + 16 * _metadata_bytes(
            (declarations, tuple((item.description, item.request) for item in history.validators.values())))
        _reserve_owned_ram(owner, cost, '_cost')
        owner._evidence = []
        completions = history.source_completions
        for source in declarations.sources:
            validator = history.validators[source.name]
            description, request = validator.description, validator.request
            owner._definitions = require_decoded_source_contract(declarations, source, description, request)
            # 纯合同先拒绝无字段却有投影；随后仍以同一真实scan补完整空源时钟证明。
            if not description.fields:
                _require_empty_source_scan(source, history, observed_scans)
            completion = completions[source.name]
            if completion.session_id != declarations.session_id or not completion.source_eof:
                raise ValueError('当前会话缺whole-source EOF事实')
            sample_count, progress_count, final_progress = 0, 0, None
            owner._reader = history.iter_records(source.name)
            # 每次仅一条记录；样本经原游标核对来源/会话/投影/批次和实际SHA。
            for owner._current in owner._reader:
                if isinstance(owner._current, HistorySample):
                    definition = owner._definitions[owner._current.name]
                    labels = tuple(dict.fromkeys(label for _, label in definition.choices)) if definition.dtype is SignalDType.ENUM else ()
                    if (owner._current.source_ref.field != definition.field or owner._current.value.dtype is not definition.dtype
                            or owner._current.unit != definition.unit or owner._current.value.labels != labels):
                        raise ResultFormatError('实际历史样本与当前绑定契约不符')
                    sample_count += 1
                elif isinstance(owner._current, HistoryProgress):
                    progress_count += 1
                    final_progress = owner._current
                # 本行已完成校验；下次实际读可能自行EOF/清理，不跨该动作借留样本。
                owner._current = None
            # 提前close也会令for结束，但不能提供真实文件EOF证明。
            if not owner._reader.verified_eof or final_progress != completion:
                raise ResultFormatError('运行绑定未完成实际EOF核对或最终事实不一致')
            owner._evidence.append(DecodedSourceEvidence(source=source.name, session_id=declarations.session_id,
                description_sha256=_fingerprint(description), request_sha256=_fingerprint(request),
                history_sha256=owner._reader.digest.hexdigest(), sample_count=sample_count, progress_count=progress_count,
                projected_aliases=request.signal_names, observation_start_ns=description.observation_start_ns,
                observation_end_ns=completion.observed_end_ns, source_eof=completion.source_eof))
            # 原reader正常已在真实EOF处关闭；显式收尾成功后才结束唯一子责任槽。
            owner._close_reader()
        owner._bindings = DecodedBindings(declarations, tuple(owner._evidence))
        owner._clear_temporary()
        return owner
    except BaseException as exc:
        owner._failed = True
        # reader构造/注册尚未返回时原工厂负责交出实际对象，禁止伪造半初始化owner。
        child = getattr(exc, 'history_iterator_cleanup_owner', None)
        if owner._reader is None and child is not None:
            owner._reader = child
        _cleanup_owner(owner, exc, 'decoded_binding_lease_cleanup_owner', '解码绑定工厂')
        raise
