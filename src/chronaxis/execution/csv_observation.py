"""在新CSV的同一次真实扫描中保存首末原时间行事实，独立管理读取寿命。

BudgetedSignalCSVSourceAdapter的可选入口返回CSVObservationRead。它转交原
SignalBatch，原解析器只在最终协议和装箱成功后提交一次首末时间候选；最后
EOF批交付还不是完成。必须原生成器真正StopIteration、文件及本请求预算资源
全部成功关闭后，observation才给出冻结CSVObservation。原请求按对象保留，
每个read有新的独立identity，同一request可同时创建多个read，不用适配器全局
last或按request值缓存。时间为转换及offset后的整数纳秒；空投影、缺失值行
仍计原时间行，空物理行不计，不从样本、请求domain或watermark推测首端。

read先预约请求、观测模型及有限资源责任容器的固定费用，完成事实保留到read
显式close，因此正常完成后借用adapter关闭不影响事实。提前close、失败、取消
或任何清理失败均不开放完成事实；close只释放本read，不关闭借用adapter和
其他请求。未返回构造及运行错误保留最高csv_observation_read_cleanup_owner。

可选资源检查器继承_CSVResources的样本和装箱估算，通过事务式金额槽交接
物理行费用，并支持重试close。CSV解析、文件顺序、批次和数值仍由原读取器
负责；预算估算不代表整个进程RSS。
"""

# 冻结事实与每次读取独立身份只依赖标准库，不保存全文件或全批次列表。
from dataclasses import dataclass
from uuid import uuid4
from ..core.validation import require_identifier, require_text
from ..timebase.conversion import require_int64_ns
from ..sources.models import ReadRequest
from ..sources.signal_csv import SignalCSVSourceAdapter
from ..sources.protocol import SourceReadError
from ..results.errors import BudgetExceededError, ResultClosedError
from ..results.spool import _cleanup_owner, _reserve_owned_ram, _release_owned_ram
from .csv_reader import _CSVResources, _PhysicalLines, _CSVRecords
from .history import _metadata_bytes


@dataclass(frozen=True)
class CSVObservation:
    """保存单个实际完成read的原行时间范围，不代替来源文件身份或同步证明。

    request是本read实际使用的原对象，read_identity对应生产它的read.identity。
    row_count为非空且通过原时间解析的行数；完整无时间行时两个端点均为None。
    模型只校验字段，后继调度仍须借实际read及其完成事实，不能凭手造模型证明读取。
    """

    source: str  # 本次实际来源名称。
    session_id: str  # 原请求所属会话。
    request: ReadRequest  # 真正读取所用原请求，保持对象身份而非复制值。
    read_identity: str  # 每次独立读取的新身份，同一request的两次读不会相同。
    first_ns: int | None  # 第一条实际原时间行的转换后整数ns，空输入为None。
    last_ns: int | None  # 最后一条实际原时间行的转换后整数ns，空输入为None。
    row_count: int  # 原时间行总数，空投影也计，不按信号列样本数计算。
    source_eof: bool  # 仅完整whole-source EOF的事实，完成模型必须为True。

    def __post_init__(self):
        """校验完成事实结构，不读取文件、推测端点或修改原请求。

        参数: 无，使用冻结字段。返回: None。异常: 类型、身份、整数时间或行数矛盾。
        """
        # 原来源和会话保持安全名称，读取身份只是非空独立文本。
        require_identifier(self.source, 'csv_observation.source')
        require_identifier(self.session_id, 'csv_observation.session_id')
        require_text(self.read_identity, 'csv_observation.read_identity')
        if not isinstance(self.request, ReadRequest) or self.request.session_id != self.session_id:
            raise ValueError('CSV观测须保留实际会话的原ReadRequest')
        if type(self.row_count) is not int or self.row_count < 0 or self.source_eof is not True:
            raise ValueError('CSV观测须为非负原生行数及完整来源EOF')
        # 空输入没有可猜测的0或请求范围；非空同刻原行允许首末相等。
        if self.row_count == 0:
            if self.first_ns is not None or self.last_ns is not None:
                raise ValueError('空CSV观测的首末时间须均为None')
        else:
            require_int64_ns(self.first_ns, 'csv_observation.first_ns')
            require_int64_ns(self.last_ns, 'csv_observation.last_ns')
            if self.first_ns > self.last_ns:
                raise ValueError('CSV观测首末时间不能回退')


class CSVObservationRead:
    """拥有一次原生成器、可选检查器和单当前批，固定事实费到显式close释放。

    _iterator、_resources及_handle分别保留最高真实责任，清理失败可重试。
    _candidate仅为原生成器的末端候选；_exhausted要求真正StopIteration和清理成功。
    正常完成后移除适配器活动登记，_observation可独立存活至本owner关闭。
    """

    def __init__(self, owner, request):
        """先预约本次请求及事实容器，再创建原参数生成器，不打开输入。

        参数: owner为实际BudgetedSignalCSVSourceAdapter；request为原ReadRequest。
        返回: 独立读取owner。异常: 原配置或预算异常；持续清理失败附最高恢复owner。
        """
        # 局部导入只作实际入口核对，避免模块载入时与预算来源形成循环。
        from .csv_reader import BudgetedSignalCSVSourceAdapter
        if not isinstance(owner, BudgetedSignalCSVSourceAdapter) or not isinstance(request, ReadRequest):
            raise TypeError('CSV观测读取需实际预算CSV来源及ReadRequest')
        owner._ensure_open()
        # 首次预算回调前安装所有责任槽；事实保留必要身份，不依赖adapter随后仍有spec。
        self._owner, self._budget, self._request = owner, owner.budget, request
        self._source, self._session_id = owner.spec.name, owner.session_id
        self._fixed_cost = self._held_cost = 0
        self._iterator = self._resources = self._handle = self._current = None
        self._identity = self._candidate = self._observation = None
        self._closed = self._closing = self._failed = self._exhausted = False
        try:
            # 原请求固定费加独立事实/身份/恢复容器上界，在UUID和原validator创建前先付。
            cost = 16384 + len(owner.signals) * 4096 + 32768 + 16 * _metadata_bytes((
                self._source, self._session_id, request))
            _reserve_owned_ram(self, cost, '_fixed_cost')
            self._identity = uuid4().hex
            self._iterator = SignalCSVSourceAdapter._request_batches(owner, request, observation_sink=self)
        except BaseException as exc:
            # 构造失败保留原预算/配置错误，清理失败不能丢失最高真实请求责任。
            self._failed = True
            self._adopt_cleanup(exc)
            _cleanup_owner(self, exc, 'csv_observation_read_cleanup_owner', 'CSV观测读取构造')
            raise

    @property
    def identity(self):
        """读取本read独立身份。参数: 无。返回: 非空str。异常: 无。"""
        # 身份不来自request值或adapter全局状态，同一请求的并发读取可明确区分。
        return self._identity

    @property
    def closed(self):
        """读取完整关闭事实。参数: 无。返回: bool。异常: 无。"""
        # 实际子句柄和固定费用都清完后才为True。
        return self._closed

    @property
    def failed(self):
        """读取操作失败事实。参数: 无。返回: bool。异常: 无。"""
        # 正常提前close也不产生完成事实，但不伪称为解析失败。
        return self._failed

    @property
    def exhausted(self):
        """读取正常耗尽事实。参数: 无。返回: bool。异常: 无。"""
        # 最后source_eof批已交付仍为False，直到下一真实StopIteration及清理成功。
        return self._exhausted

    @property
    def observation(self):
        """借读本次已完成的冻结观测，借期到本read的close。

        参数: 无。返回: CSVObservation。异常: ResultClosedError为未完成、失败或关闭。
        """
        # 不查询借用adapter，正常完成事实可在adapter关闭以后继续读取。
        if self._closed or self._closing or self._failed or not self._exhausted or self._observation is None:
            raise ResultClosedError('CSV观测读取尚未正常完成或已关闭')
        return self._observation

    def _read_resources(self):
        """为本次生成器建立独立事务式检查器，在文件打开前保留最高责任。

        参数: 无。返回: _ObservationCSVResources。异常: 原预算、登记或构造错误。
        """
        # 检查器构造与登记失败都由本read接管，不以request值查找或借其他请求资源。
        try:
            self._resources = _ObservationCSVResources(self._owner)
            self._owner._resources.add(self._resources)
        except BaseException as exc:
            self._adopt_cleanup(exc)
            raise
        return self._resources

    def _created_iterator(self, iterator):
        """在原活动set登记前接住本次实际生成器。

        参数: iterator为原请求包装生成器。返回: None。异常: 无预期异常。
        """
        # 原入口尚未返回也可能登记失败，构造清理须能关闭这个最高实际子对象。
        self._iterator = iterator

    def _opened_handle(self, handle):
        """在适配器set登记前接住本次真实文件句柄。

        参数: handle为原Path.open返回的实际只读句柄。返回: None。异常: 无预期异常。
        """
        # 原来源逐文件执行，最多一个实际文件；前一文件未关闭不能进入下一文件。
        self._handle = handle

    def _close_handle(self, handle, primary):
        """沿原文件关闭动作保根因，并保留实际未关闭句柄供重试。

        参数: handle为实际文件；primary为原读取错误、GeneratorExit或None。
        返回: None。异常: 无业务根因时原关闭错误传播，已有根因只补note。
        """
        # 原helper仍执行真正close及原登记处理；新增责任只补其失败后句柄可达性。
        try:
            self._owner._close_handle(handle, primary)
        except BaseException as cleanup:
            if primary is None or isinstance(primary, GeneratorExit):
                raise
            primary.add_note(f'CSV观测文件关闭附加失败: {type(cleanup).__name__}')
        finally:
            if handle.closed:
                self._handle = None

    def _close_resources(self, primary):
        """原生成器退出时清理本次检查器，清理失败不覆盖业务或取消根因。

        参数: primary为当前异常或None。返回: None。异常: 正常退出时的原资源关闭错误。
        """
        # 文件仍未关闭则保留其预算检查器，不能提前释放读取固定槽后丢失真实FD责任。
        if self._handle is not None:
            if primary is None:
                raise SourceReadError('CSV观测文件尚未成功关闭')
            return
        try:
            self._resources.close()
        except BaseException as cleanup:
            if primary is None or isinstance(primary, GeneratorExit):
                raise
            primary.add_note(f'CSV观测资源关闭附加失败: {type(cleanup).__name__}')

    def _end_file(self, resources, primary):
        """清理单文件表头及行费用，保留现场正在传播的读取或关闭主异常。

        参数: resources为本read的实际检查器；primary为原生成器finally现场的
            sys.exception()，可能为解析错误、取消、文件关闭失败、GeneratorExit或None。
        返回: None。异常: 正常文件结束或GeneratorExit时的原清理错误继续传播；
            已有其他主异常时仅给它增加note，事务式费用槽留待同一read.close重试。
        """
        # 不能事后从异常链猜主错；仅在已有真正业务或取消主异常时保护其原身份和分类。
        try:
            resources.end_file()
        except BaseException as cleanup:
            if primary is None or isinstance(primary, GeneratorExit):
                raise
            primary.add_note(f'CSV观测单文件资源清理附加失败: {type(cleanup).__name__}')

    def _accept_candidate(self, first, last, count):
        """仅接收原生成器最终协议成功后的候选，不在此声明完成。

        参数: first、last为原时间行首末ns或None，count为原sequence行数。
        返回: None。异常: 无预期异常，最终typed字段在真正耗尽后校验。
        """
        # 单个有限tuple早由固定费覆盖，不保存逐行回调或整个历史。
        self._candidate = (first, last, count)

    def _adopt_cleanup(self, exc):
        """接管本路径实际未返回的最高资源检查器。

        参数: exc为原异常。返回: None。异常: 无预期异常。
        """
        # 只接本次新资源属性，绝不接其他请求或把借用adapter当作自有资源。
        resources = getattr(exc, 'csv_observation_resources_cleanup_owner', None)
        if resources is not None and self._resources is None:
            self._resources = resources

    def __iter__(self):
        """返回唯一读取owner。参数: 无。返回: self。异常: ResultClosedError为不可推进。
        """
        # 失败或半关闭状态只允许close，不创建带第二份同源状态的新游标。
        self._ensure_active()
        return self

    def _ensure_active(self):
        """拒绝关闭、清理或失败后的推进。参数: 无。返回: None。异常: ResultClosedError。
        """
        # 完成后的重复next在独立检查后返回StopIteration，不再依赖借用adapter。
        if self._closed or self._closing or self._failed:
            raise ResultClosedError('CSV观测读取已关闭、正在清理或推进失败')

    def __next__(self):
        """转交原batch，真正StopIteration并成功清理后才安装完成事实。

        参数: 无。返回: 原SignalBatch。异常: 正常StopIteration；原读取、预算或取消错误
            保留csv_observation_read_cleanup_owner，失败后仅可close。
        """
        self._ensure_active()
        if self._exhausted:
            raise StopIteration
        try:
            self._owner._ensure_open()
            self._current = None
            try:
                self._current = next(self._iterator)
            except StopIteration:
                # EOF批交付后的生成器finally已真正成功返回，再确认全部自有读取资源关闭。
                self._close_request()
                if self._candidate is None:
                    raise ValueError('CSV观测缺少实际完整EOF候选')
                first, last, count = self._candidate
                self._observation = CSVObservation(self._source, self._session_id, self._request,
                    self._identity, first, last, count, True)
                self._candidate = None
                self._exhausted = True
            else:
                return self._current
        except BaseException as exc:
            # 真正正常StopIteration在外部产生；读取错误及清理取消不能被当作完成。
            self._failed = True
            self._adopt_cleanup(exc)
            exc.csv_observation_read_cleanup_owner = self
            exc.add_note('恢复后调用csv_observation_read_cleanup_owner.close()')
            raise
        raise StopIteration

    def _close_request(self):
        """关闭本次原生成器、文件和检查器，保原首错及每个未完责任供重试。

        参数: 无。返回: None。异常: 首个真实关闭错误，其他错误附note而不覆盖。
        """
        # 结束当前批借引用；原generator仍可能持批，必须先实际关闭再释放检查器数组槽。
        self._current = None
        failure = None
        if self._iterator is not None:
            try:
                self._iterator.close()
            except BaseException as exc:
                failure = exc
            else:
                self._owner.active.discard(self._iterator)
                self._iterator = None
        # 生成器关闭失败后仍尝试唯一真实文件，成功才丢句柄；不关闭其他请求文件。
        if self._handle is not None:
            try:
                self._handle.close()
            except BaseException as exc:
                if failure is None:
                    failure = exc
                else:
                    failure.add_note(f'CSV观测残留文件关闭附加失败: {type(exc).__name__}')
            finally:
                if self._handle.closed:
                    self._owner.handles.discard(self._handle)
                    self._handle = None
        if self._resources is not None and self._handle is None:
            try:
                self._resources.close()
            except BaseException as exc:
                if failure is None:
                    failure = exc
                else:
                    failure.add_note(f'CSV观测残留资源关闭附加失败: {type(exc).__name__}')
            else:
                self._resources = None
        # 原错仍需报告，即使后续尝试清了资源也不能把首次清理失败伪装成正常耗尽。
        if failure is not None:
            raise failure
        self._owner._requests.discard(self)

    def close(self):
        """可重试释放本read及事实费，不关闭借用来源、其他请求或删除文件。

        参数: 无。返回: None，成功后幂等。异常: 原文件、子资源或预算取消，未完责任保留。
        """
        # 提前结束只清候选，不补EOF；已完成事实到本close才停止开放。
        if self._closed:
            return
        self._closing = True
        self._candidate = self._observation = None
        self._close_request()
        self._request = None
        _release_owned_ram(self, self._fixed_cost, '_fixed_cost')
        if self._held_cost == 0:
            self._closed = True


class _ObservationCSVResources(_CSVResources):
    """只为可选新路径补事务式预算责任，沿用原样本及装箱估算和金额。

    各用途实际金额既保留在固定属性槽也同步到原charges检查接口；_held_cost
    仅为本资源的实际总额。清理取消前后均能重试，不提前closed或丢已付款槽。
    """

    def __init__(self, owner):
        """建立实际槽后调用原检查器构造，固定读取费用仍为原65536字节。

        参数: owner为借用预算CSV来源。返回: 独立检查器。异常: 原预算或取消错误，附恢复owner。
        """
        # 在原构造的第一次_add前安装所有有限用途槽，费用名称不随原行数增长。
        self._budget, self._held_cost = owner.budget, 0
        self._fixed_cost = self._reading_cost = self._header_cost = self._row_cost = 0
        self._pending_cost = self._work_cost = self._array_cost = self._protocol_cost = 0
        try:
            super().__init__(owner)
        except BaseException as exc:
            _cleanup_owner(self, exc, 'csv_observation_resources_cleanup_owner', 'CSV观测资源构造')
            raise

    def _sync(self, key):
        """同步原charges视图与实际属性槽。参数: key为有限用途名。返回: None。异常: 无预期异常。
        """
        # 只在本资源预付固定容器内更新至多八个键，不产生逐样本费用字典。
        amount = getattr(self, '_' + key + '_cost')
        if amount:
            self.charges[key] = amount
        else:
            self.charges.pop(key, None)

    def _add(self, key, amount):
        """申请成功前后取消均登记实际自有槽，不从其他owner余额推测。

        参数: key为原用途；amount为原估算字节。返回: None。异常: 原预算或取消错误。
        """
        # helper仅围绕一笔真实预算调用判断余额，finally同步实际登记而非预先增加。
        try:
            _reserve_owned_ram(self, amount, '_' + key + '_cost')
        finally:
            self._sync(key)

    def _release_amount(self, key, amount):
        """只抵销某用途一笔实际金额，释放前后取消都保留正确剩余。

        参数: key为原用途；amount为本用途已有字节。返回: None。异常: 原释放或取消错误。
        """
        # 实际释放后取消也及时清槽，重试不多扣共享预算或借用来源费用。
        try:
            _release_owned_ram(self, amount, '_' + key + '_cost')
        finally:
            self._sync(key)

    def _release(self, key):
        """抵销用途完整余额。参数: key为有限用途名。返回: None。异常: 原释放取消。
        """
        # 空用途沿helper不触发外部释放回调，不把未付款金额抵销给其他owner。
        self._release_amount(key, getattr(self, '_' + key + '_cost'))

    def _move(self, source, target, amount):
        """在已付款用途间交接金额，不增加或释放共享预算。

        参数: source、target为用途名，amount为已付款字节。返回: None。异常: ValueError为内部金额矛盾。
        """
        # 真实数组和当前行交接只变本资源责任槽，总_held_cost始终不变。
        source_slot, target_slot = '_' + source + '_cost', '_' + target + '_cost'
        if amount < 0 or amount > getattr(self, source_slot):
            raise ValueError('CSV观测资源交接超出原用途余额')
        setattr(self, source_slot, getattr(self, source_slot) - amount)
        setattr(self, target_slot, getattr(self, target_slot) + amount)
        self._sync(source)
        self._sync(target)

    def lines(self, handle):
        """建立原物理行读取的事务式费用包装。参数: handle为真实文件。返回: 行游标。异常: 无预期异常。
        """
        # CSV解释仍由原csv.reader负责，只更换释放前后取消不会丢账的物理读取计费。
        self.line_source = _ObservationPhysicalLines(self, handle)
        return self.line_source

    def records(self, reader):
        """包装原csv.reader的费用交接。参数: reader为原解释器。返回: 原记录游标。异常: 无预期异常。
        """
        # 表头、行内容及reader.line_num均来自原解释器，不复制解析规则。
        return _ObservationCSVRecords(self, reader)

    def after_pack(self, validator):
        """沿原金额把装箱workspace交给数组与协议，余量释放取消仍保持可恢复。

        参数: validator为已accept的原协议状态。返回: None。异常: 原账本或取消错误。
        """
        # 与原after_pack逐项金额相同，只把尚未实际释放的workspace留在真实_work_cost。
        state_cost = sum(512 + len(state[1]) * 256 for state in validator.pending.values())
        self._release('array')
        self._release('protocol')
        self._move('work', 'array', self.array_cost)
        self._move('work', 'protocol', state_cost)
        self._release('work')

    def close(self):
        """逐实际用途抵销，全部成功后才closed和移除自有登记。

        参数: 无。返回: None，成功后幂等。异常: 原释放取消，尚未抵销槽保留供重试。
        """
        # 不在释放前pop费用或声明closed；持续故障后原对象仍保有准确金额责任。
        if self.closed:
            return
        self.line_source = None
        for key in ('fixed', 'reading', 'header', 'row', 'pending', 'work', 'array', 'protocol'):
            self._release(key)
        if self._held_cost == 0:
            self.closed = True
            self.owner._resources.discard(self)


class _ObservationPhysicalLines(_PhysicalLines):
    """沿原readline限长算法，在临时物理行费用释放前后取消时保留实际槽。"""

    def __next__(self):
        """按原容量真实读取一物理行，只更换实际金额的事务式抵销。

        参数: 无。返回: 原含换行文本，真实EOF停止。异常: 原I/O、预算或取消错误。
        """
        # 64/字符和8192固定余量与原物理行入口完全相同，不缩小批次或截断后继续解释。
        budget = self.resources.budget
        capacity = (budget.memory_budget_bytes - budget.ram_bytes - 8192) // 64 - 1
        if capacity <= 0:
            raise BudgetExceededError('CSV物理行/引用记录累积超出剩余RAM估算')
        amount = 8192 + (capacity + 1) * 64
        self.resources._add('reading', amount)
        try:
            text = self.handle.readline(capacity + 1)
        except BaseException as exc:
            try:
                self.resources._release_amount('reading', amount)
            except BaseException as cleanup:
                exc.add_note(f'CSV观测物理行清理附加失败: {type(cleanup).__name__}')
            raise
        # 原文本已受全容量预算覆盖，释放多余部分失败也不会丢失已保留的读取费用。
        retained = 0 if not text else 8192 + len(text) * 64
        self.resources._release_amount('reading', amount - retained)
        if len(text) > capacity:
            raise BudgetExceededError('CSV物理行超过剩余RAM允许长度，未解析截断行')
        if not text:
            raise StopIteration
        return text


class _ObservationCSVRecords(_CSVRecords):
    """保留原csv.reader记录与物理行语义，只显式交接已付款的读取责任槽。"""

    def __next__(self):
        """先从原解释器取完整记录，再把reading费用转给表头或当前行。

        参数: 无。返回: 原单元格list。异常: 原EOF、CSV、I/O、预算或取消错误。
        """
        # 上一原记录仍可能由生成器引用，新读取费用与旧记录按原方式重叠计费。
        cells = next(self.reader)
        key = 'header' if self.first else 'row'
        self.resources._release(key)
        self.resources._move('reading', key, self.resources._reading_cost)
        self.first = False
        return cells
