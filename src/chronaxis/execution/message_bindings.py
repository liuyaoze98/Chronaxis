"""完整核验独立解码消息仓，为当前消息表达式取得有预算的运行绑定。

输入为已经冻结的MessageDeclarations及调用方拥有的sealed DecodedMessageStore。
工厂借用原声明和仓，先预约有限元数据，默认以一个独立reader逐条核验真实文件；
首次核验只有在实际EOF、全流SHA/count以及reader的FD和费用均成功关闭后，才开放
MessageBindings。首末时间来自全部decoded记录，空仓保持None；不根据表达式
别名裁剪仓、不要求每个字段出现，也不重读BLF、DBC或普通history。
同一实际sealed仓可借用已完成lease的核验结果；仍核同预算、封口事实和文件状态，
为新声明创建独立绑定及自有费用，不复用旧DBC解码或跨任务缓存。后续实际计算仍核全流EOF/SHA。

本域保留原SignalDefinition身份，执行数值转换和表达式由其他模块负责；这里
不应用TTL、保持、同刻去重或原请求范围筛选。profile/read_identity是仓已保存
的显式标签，真实文件EOF不证明该仓来自某次CAN读取或旧求值触发。

lease只拥有固定元数据及自己取得的reader，不关闭借用store、预算或其他reader，
不删除文件。原store的reader发生错误时仍会按原政策poison/清理父仓；本工厂
保留该最高恢复owner，不把这一原生行为误称为借仓在失败后必定仍开放。
未返回reader始终由实际store的pending/readers槽保活，不伪造半初始化对象。

预算仅覆盖本层新增摘要、身份编码及有限状态，单行费用由实际reader承担；
原声明、原仓元数据和调用方保留的异常诊断属于借用输入或输出，不代表RSS。
本模块只使用轻量预算helper、消息模型和原仓，不导入history/codec/spool或旧IO。
"""

# 模型只接独立消息域；原仓负责严格行编码及全流校验，工厂不复制这些算法。
from ..core.message_binding import MessageBindings, MessageDeclarations, MessageSourceEvidence
from ..legacy.message_store import DecodedMessageStore, StoredDecodedMessage
from ..results.budget import ResourceBudget, _cleanup_owner, _release_owned_ram, _reserve_owned_ram
from ..results.errors import ResultClosedError, ResultFormatError


def _fixed_estimate(declarations: MessageDeclarations, store: DecodedMessageStore) -> int:
    """在创建本层身份副本前按原生长度估算有限元数据及编码临时空间。

    参数: declarations为借用的冻结消息声明；store为借用的活sealed仓。
    返回: 保守bytes金额，不遍历原信号定义、参数树、raw_config或逐条记录。
    异常: TypeError/ValueError为仓公开元数据已变成非原生文本或非法条数；
        本函数不strip、encode、repr或创建字段副本，不为估费先建立大文本。
    """
    # 声明身份已由调用方构造；本层只支付新evidence和运行身份所需的有限编码。
    if type(declarations.identity) is not str:
        raise TypeError('消息声明identity必须为原生文本')
    characters = len(declarations.identity)
    for name in ('source_name', 'session_id', 'decoder_profile', 'read_identity', 'sha256'):
        value = getattr(store, name)
        if type(value) is not str:
            raise TypeError('解码仓绑定元数据必须为原生文本')
        characters += len(value)
    # 条数编码空间随整数位数计入；端点受int64约束，其固定空间已在基数内。
    if type(store.count) is not int or store.count < 0:
        raise ValueError('解码仓绑定条数必须为非负原生int')
    return 32768 + 32 * (characters + store.count.bit_length() + 1)


def _file_snapshot(store: DecodedMessageStore) -> tuple[int, ...]:
    """记录新消息暂存文件的有限状态，防止把已变化路径当作先前核验的同一文件。

    参数: store为已经封口的实际消息仓。返回: 设备、文件身份、大小及系统提供的时间信息tuple。
    异常: 原stat错误传播。边界: 这不是持续监控或新内容摘要，计算reader仍须核完整EOF/SHA；
        stat对象及tuple在lease固定元数据预算内，不接触原BLF或DBC。
    """
    state = None
    try:
        state = store.file_path.stat()
        return state.st_dev, state.st_ino, state.st_size, state.st_mtime_ns, state.st_ctime_ns
    finally:
        # 取消异常可保留本frame，不让已结束预算的stat对象留在诊断局部变量中。
        state = None


class MessageBindingLease:
    """持有自有reader和固定费，完整核验或同仓复用后借出不可变消息运行绑定。

    _fixed_cost/_held_cost只记录本层直接交易，reader的费用由原reader独立负责。
    _opening_reader标记取得子对象的窗口；未返回子仍属于借用store的真实责任槽。
    _verified_*保留同一借用仓的有限核验快照，仅供建立独立新绑定，不替其他lease付款。
    开始关闭或失败后不可借出bindings，只有自身子和费用都清完才closed。
    """

    def __init__(self, budget: ResourceBudget):
        """先安装全部责任槽，不预约费用，也不打开文件。

        参数: budget为实际消息仓使用的ResourceBudget。
        返回: 尚未完成的lease，供唯一工厂继续初始化。
        异常: TypeError为非ResourceBudget；不会接收已经支付却无owner的裸金额。
        """
        # 所有槽在首次预算或reader回调之前存在，预约返回后取消仍可恢复同一owner。
        self._budget = budget
        self._fixed_cost = self._held_cost = 0
        self._reader = self._current = self._bindings = None
        self._store = self._declarations = self._facts = self._evidence = None
        # 成功核验的有限证据保在本lease；借用仓不由它关闭，关闭lease即解除这些引用。
        self._verified_store = self._verified_facts = self._verified_file = None
        self._opening_reader = False
        self._closed = self._closing = self._failed = False
        if not isinstance(budget, ResourceBudget):
            raise TypeError('消息绑定lease需要ResourceBudget')

    @property
    def bindings(self) -> MessageBindings:
        """取得完整核验后形成的不可变消息绑定，不借出半成品。

        参数: 无。返回: 原MessageBindings对象。
        异常: ResultClosedError为尚未完成、已失败、关闭中或已经关闭。
        """
        # 即使bindings曾经创建成功，清理中的owner也不能继续参与新的求值。
        if self._closed or self._closing or self._failed or self._bindings is None:
            raise ResultClosedError('消息运行绑定未完成、已失败或正在关闭')
        return self._bindings

    @property
    def closed(self) -> bool:
        """读取本lease的实际清理状态。

        参数: 无。返回: reader和自有费用均清完时为True。
        异常: 无；不把借用store是否关闭混成本lease的状态。
        """
        return self._closed

    def _require_store(self) -> None:
        """核本次借用仓的当前合同及封口事实，拒绝回读期间替换元数据。

        参数: 无，读取本lease保存的原store、声明和有限事实。
        返回: None；不读取源CAN或额外打开仓文件。
        异常: 原仓生命周期错误；ValueError为来源、会话或预算不对应；
            ResultFormatError为本次回读前后封口事实被替换。
        """
        # 原仓必须真实仍可读；普通声明身份不代替其当前文件和生命周期。
        store, declarations = self._store, self._declarations
        store._require('sealed')
        if store.budget is not self._budget or store._budget is not self._budget:
            raise ValueError('消息仓绑定的原共享budget已被替换')
        if store.source_name != declarations.source or store.session_id != declarations.declarations.session_id:
            raise ValueError('消息仓来源或会话与当前消息声明不符')
        # 路径只作同一输入对象的保护，不把路径文本冒充内容SHA或CAN认证。
        current = (store.source_name, store.session_id, store.decoder_profile, store.read_identity,
                   store.sha256, store.count, store.file_path, store.max_row_bytes, store.sparse_sequences, store.line_limit)
        if self._facts is not None and current != self._facts:
            raise ResultFormatError('消息仓回读期间封口身份或条数已改变')

    def _close_reader(self) -> None:
        """关闭唯一已安装的真实reader，未完成责任保在原槽供重试。

        参数: 无。返回: None；正常EOF已关闭的reader也按原幂等接口收尾。
        异常: 原FD或费用释放错误；实际关闭后才取消时清槽，避免重复抵销。
        """
        # 当前记录必须先结束引用，子reader才可归还覆盖单行的实际费用。
        self._current = None
        if self._reader is None:
            return
        try:
            self._reader.close()
        except BaseException:
            if self._reader.closed:
                self._reader = None
            raise
        else:
            self._reader = None

    def _clear_temporary(self) -> None:
        """结束本工厂有限临时引用，不清调用方的原对象或异常traceback。

        参数: 无。返回: None。
        异常: 无主动异常；借用store与声明只解除引用，不执行它们的close。
        """
        # 临时槽解除引用；成功后用于同仓复用的少量事实由_verified_*持有并计入固定费。
        self._current = self._facts = self._evidence = None
        self._store = self._declarations = None

    def close(self) -> None:
        """只关闭本lease的实际reader，再归还逐笔自有固定费。

        参数: 无。返回: None，实际完成后重复调用幂等。
        异常: 原FD或预算取消错误，可恢复后在同一owner上重试；
            释放后取消按实际槽记账，不重复抵销其他借用费用。
        副作用: 不显式关闭借用仓、其他reader或共享budget，不删除任何文件。
        """
        # 关闭中禁止重新借出绑定；子FD持续失败时保留子及其实际责任，不先报closed。
        if self._closed:
            return
        self._closing = True
        try:
            self._close_reader()
            self._bindings = None
            self._clear_temporary()
            self._verified_store = self._verified_facts = self._verified_file = None
            self._opening_reader = False
            _release_owned_ram(self, self._fixed_cost, '_fixed_cost')
            self._closed = True
        except BaseException as exc:
            # 直接close也交出同一真实lease；不递归清理，不覆盖原store恢复属性。
            exc.message_binding_lease_cleanup_owner = self
            raise


def bind_message_store(declarations: MessageDeclarations, store: DecodedMessageStore, *,
                       verified_by: MessageBindingLease | None = None) -> MessageBindingLease:
    """完整核验消息仓，或在同一未变仓上借用真实已完成核验，返回独立有预算绑定。

    参数: declarations为冻结MessageDeclarations；store为调用方拥有的实际
        DecodedMessageStore，须仍活且sealed，source/session与原声明一致；verified_by
        可为已成功且未关闭的真实lease，仅同一仓/预算/封口及文件状态一致时复用核验结果。
    返回: MessageBindingLease，其bindings包含实际仓SHA/count/首末及显式标签；
        空仓首末为None，所有decoded帧都计数，不按字段缺失或请求范围筛掉。
    异常: TypeError/ValueError为类型及声明不对应；原仓状态、IO、预算、取消错误
        原样传播；ResultFormatError为未完成真实EOF或当前封口事实变化。
        原错误附message_binding_lease_cleanup_owner；未返回reader的责任保在
        原decoded_message_store_cleanup_owner，不擅自关闭借用父仓。
    """
    # 只接现有真实仓与消息声明，不以普通history、结构证据或同名字符串伪装输入。
    if not isinstance(declarations, MessageDeclarations) or not isinstance(store, DecodedMessageStore):
        raise TypeError('消息运行绑定需要MessageDeclarations和DecodedMessageStore')
    if verified_by is not None and type(verified_by) is not MessageBindingLease:
        raise TypeError('共享核验需要真实MessageBindingLease，不能用结构证据代替')
    store._require('sealed')
    owner = MessageBindingLease(store.budget)
    previous = evidence = None
    try:
        # 长标签先按原生长度付费，随后才创建事实tuple、模型及身份编码临时副本。
        owner._store, owner._declarations = store, declarations
        _reserve_owned_ram(owner, _fixed_estimate(declarations, store), '_fixed_cost')
        owner._require_store()
        owner._facts = (store.source_name, store.session_id, store.decoder_profile, store.read_identity,
                        store.sha256, store.count, store.file_path, store.max_row_bytes, store.sparse_sequences, store.line_limit)
        if verified_by is not None:
            # bindings属性拒绝未完成/失败/关闭的lease；对象身份和原封口事实防跨仓借证。
            previous = verified_by.bindings
            if (verified_by._budget is not owner._budget or verified_by._verified_store is not store
                    or verified_by._verified_facts != owner._facts):
                raise ResultFormatError('共享核验的消息仓、预算或封口事实已改变')
            owner._verified_file = _file_snapshot(store)
            if verified_by._verified_file != owner._verified_file:
                raise ResultFormatError('共享核验的消息仓文件状态已改变')
            evidence = previous.evidence
            owner._evidence = MessageSourceEvidence(evidence.source, evidence.session_id,
                evidence.decoder_profile, evidence.read_identity, evidence.store_sha256,
                evidence.record_count, evidence.first_time_ns, evidence.last_time_ns)
            owner._bindings = MessageBindings(declarations, owner._evidence)
            owner._require_store()
            if _file_snapshot(store) != owner._verified_file:
                raise ResultFormatError('共享绑定创建期间消息仓文件状态已改变')
            owner._verified_store, owner._verified_facts = store, owner._facts
            owner._clear_temporary()
            return owner
        owner._verified_file = _file_snapshot(store)
        count = 0
        first_time_ns = last_time_ns = None
        # 此窗口内未返回的真实reader仍在store.pending/readers中，不制造第二个父owner。
        owner._opening_reader = True
        owner._reader = store.iter_records()
        owner._opening_reader = False
        for owner._current in owner._reader:
            if not isinstance(owner._current, StoredDecodedMessage):
                raise ResultFormatError('消息仓回读返回非StoredDecodedMessage')
            if first_time_ns is None:
                first_time_ns = owner._current.time_ns
            last_time_ns = owner._current.time_ns
            count += 1
            # 下一次next可能在真实EOF释放子费用，不能跨该动作保留上一行完整values。
            owner._current = None
        # 提前close同样能使for停止；只有真EOF与实际FD/费用关闭才允许生成运行证据。
        if not owner._reader.verified_eof or not owner._reader.closed:
            raise ResultFormatError('消息绑定未完成真实仓EOF及reader关闭')
        owner._require_store()
        digest = owner._reader._digest.hexdigest()
        if count != owner._facts[5] or owner._reader._count != count or digest != owner._facts[4]:
            raise ResultFormatError('消息绑定实际SHA或条数与原封口事实不符')
        if _file_snapshot(store) != owner._verified_file:
            raise ResultFormatError('消息仓核验期间文件状态已改变')
        owner._close_reader()
        # 首末取全仓实际行，时间已在仓中映射，不施offset、TTL或连续观测域裁剪。
        owner._evidence = MessageSourceEvidence(source=store.source_name, session_id=store.session_id,
            decoder_profile=store.decoder_profile, read_identity=store.read_identity,
            store_sha256=digest, record_count=count, first_time_ns=first_time_ns,
            last_time_ns=last_time_ns)
        owner._bindings = MessageBindings(declarations, owner._evidence)
        owner._verified_store, owner._verified_facts = store, owner._facts
        owner._clear_temporary()
        return owner
    except BaseException as exc:
        # 先断开本层单行引用，原输入与必要异常诊断仍归调用方；不清他人traceback帧。
        owner._current = None
        owner._failed = True
        if owner._opening_reader and owner._reader is None:
            # 调用返回到父赋值之间取消时，原仓仍登记实际子；父属性只供调用方恢复。
            if getattr(exc, 'decoded_message_store_cleanup_owner', None) is None:
                exc.decoded_message_store_cleanup_owner = store
        exc.message_binding_lease_cleanup_owner = owner
        _cleanup_owner(owner, exc, 'message_binding_lease_cleanup_owner', '消息绑定工厂')
        raise
    finally:
        # 原异常可能长期保留；不由本层frame继续保活其他lease已交接的绑定/证据。
        previous = evidence = None
