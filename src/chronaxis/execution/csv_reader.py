"""在独立信号CSV读取、引用记录累积和数组分配前申请共享预算。

输入沿用SignalCSVSpec、声明及ReadRequest；输出沿用原SignalBatch和CSVSourceRef。
原csv.reader、解析和文件顺序保持；批次达到样本上限或剩余容量前交付。
物理行readline限制按当时剩余RAM计算，跨物理行的引用记录保守累计，超限失败。
原样本/ref、定宽Unicode提升、owned数组交接与协议pending副本分别计账。
close释放本来源/请求引用和预算，文件保留；不是全进程RSS或外部保留全部输出保证。
默认请求各自保存真实生成器、FD与用途费用槽，关闭取消后保留尚未完成的责任；
未返回构造以csv_source_cleanup_owner、csv_request_cleanup_owner或csv_resources_cleanup_owner恢复。
"""

# 新来源仍使用既有CSV解释和数值归一化，资源模型不依赖旧CAN链。
from collections.abc import Iterator
from sys import getsizeof, int_info
from ..results.budget import ResourceBudget
from ..results.errors import BudgetExceededError
from ..results.spool import _cleanup_owner, _reserve_owned_ram, _release_owned_ram
from ..sources.signal_csv import SignalCSVSourceAdapter
from ..sources.protocol import SourceClosedError, SourceReadError
from ..sources.models import ReadRequest, SignalBatch
from ..sources.csv_spec import SignalCSVSpec
from ..core.binding import SignalDefinition
from .history import _metadata_bytes


def _expanded_integer_bytes(text):
    """按十进制文本估算整数展开空间，不重复执行 Decimal 或实际整数转换。

    参数: text 为待解析单元格。返回: 最多 4096 位十进制整数所需的字节上界。
    异常: 不把坏文本提前当成合法数值；语法和指数边界仍由原解析器拒绝。
    """
    # 普通短整数由记录的固定标量留量覆盖；仅指数或长数值需要额外空间。
    exponent_at = max(text.find('e'), text.find('E'))
    if exponent_at < 0 and len(text) <= 20:
        return 32
    digits = len(text) if exponent_at < 0 else exponent_at
    if exponent_at >= 0:
        exponent = text[exponent_at + 1:].strip()
        if not exponent.startswith('-'):
            exponent = exponent.lstrip('+').lstrip('0')
            if exponent and exponent.isdecimal():
                # 原解析器最多允许 4096 位；不为估算构造任意长度的指数整数。
                digits += int(exponent) if len(exponent) <= 4 else 4096
    digits = min(4096, max(1, digits))
    # log2(10) < 3.322；按本 Python 的 PyLong 数字位宽计算，不依赖 float 舍入。
    limbs = (digits * 3322 + int_info.bits_per_digit * 1000 - 1) // (int_info.bits_per_digit * 1000)
    return getsizeof(0) + max(0, limbs - 1) * int_info.sizeof_digit


class BudgetedSignalCSVSourceAdapter(SignalCSVSourceAdapter):
    """为各请求独立持有检查器，固定声明一次计账，关闭不删除输入。

    _held_cost只含本来源_input_cost；请求与资源各自拥有自己的费用。
    _closing拒绝继续读取，只有真实子资源及固定槽均已清完才closed。
    未安装请求和检查器保留在明确字段，不借共享余额差额补账。
    """

    def __init__(self, budget: ResourceBudget, spec: SignalCSVSpec, session_id: str,
                 signals: tuple[SignalDefinition, ...], *, backend: str = 'numpy', clock_only=(), retain_original=True, consumer_sample_bytes=0):
        """先计声明，再建立不读取文件的原CSV适配器。

        参数: budget为共享RAM账本；其余沿用原CSV入口，backend默认numpy。
            clock_only只取时间；retain_original=False省去逐行原文引用，默认保留旧入口行为。
            consumer_sample_bytes为接收方每样本最坏排队费用，只用于容量协调，不重复预约。
        返回: 新预算CSV来源。异常: 类型/配置/预算失败；持续清理失败附csv_source_cleanup_owner。
        """
        if not isinstance(budget, ResourceBudget) or not isinstance(spec, SignalCSVSpec) or type(signals) is not tuple:
            raise TypeError('预算CSV需要ResourceBudget/SignalCSVSpec/信号tuple')
        if type(consumer_sample_bytes) is not int or consumer_sample_bytes < 0:
            raise ValueError('CSV接收方样本费用须为非负整数')
        self._consumer_sample_bytes = consumer_sample_bytes
        # 路径/元数据和choices固定容器在原适配器构造前保守计数。
        # Path/tzinfo不是结果层可序列化模型；路径计原文本，时区只保留原对象引用。
        declaration = (spec.name, spec.timebase,
                       spec.time_column, spec.unit, spec.offset_ns, spec.encoding, spec.delimiter,
                       spec.missing_values, session_id, signals)
        # 逐路径计数避免在申请前再复制完整路径tuple；每次只持一个路径文本。
        cost = 20480 + _metadata_bytes(declaration) * 16 + sum(512 + _metadata_bytes(str(path)) * 16 for path in spec.paths)
        # 首次预算回调前建立可关闭的真实空壳；父构造尚未返回也不依赖未初始化字段。
        self.budget = self._budget = budget
        self._input_cost = self._held_cost = 0
        self.closed = self._closing = False
        self.spec, self.session_id, self.signals, self.backend, self.choices = spec, session_id, signals, backend, {}
        self.active, self.handles = set(), set()
        self._requests, self._resources = set(), set()
        self._uninstalled_request = self._uninstalled_resources = None
        try:
            _reserve_owned_ram(self, cost, '_input_cost')
            super().__init__(spec, session_id, signals, backend=backend,clock_only=clock_only,retain_original=retain_original)
        except BaseException as exc:
            _cleanup_owner(self, exc, 'csv_source_cleanup_owner', '预算CSV来源构造')
            raise

    def iter_batches(self, request: ReadRequest, *, observe_bounds=False) -> Iterator[SignalBatch]:
        """预留请求/validator固定结构，再建立原参数生成器。

        参数: request为ReadRequest，投影/会话由原入口验证；observe_bounds仅收计算所需首末时刻。
        返回: 独立预算游标，不生成额外观测报告。
        异常: 关闭/配置/预算/读取错误传播；未返回请求持续清理失败保最高恢复owner，
            不切换后端；batch_rows 是上限，容量不足时提前交付已有样本。
        """
        self._ensure_open()
        # 只限制创建新请求；已有其他活read仍可推进，不能覆盖尚未返回的最高子责任。
        if self._uninstalled_request is not None or self._uninstalled_resources is not None:
            raise SourceClosedError('预算CSV来源尚有未返回请求或资源待清理')
        try:
            iterator = _CSVRequest(self, request, observe_bounds=observe_bounds)
            self._uninstalled_request = iterator
            self._requests.add(iterator)
            self._uninstalled_request = None
        except BaseException as exc:
            iterator = self._uninstalled_request or getattr(exc, 'csv_request_cleanup_owner', None)
            if iterator is not None:
                _cleanup_owner(iterator, exc, 'csv_request_cleanup_owner', '默认CSV请求登记')
                if iterator.closed or iterator in self._requests:
                    self._uninstalled_request = None
                else:
                    self._uninstalled_request = iterator
                if not iterator.closed:
                    exc.csv_source_cleanup_owner = self
            raise
        return iterator

    def iter_batches_with_observation(self, request: ReadRequest):
        """创建本次独立读取owner，完整耗尽并清理成功后才开放原时间行观测事实。

        参数: request为原ReadRequest，不改变会话、投影、范围或batch_rows。
        返回: CSVObservationRead；迭代交付原SignalBatch，真正StopIteration后
            observation给出本read独立的首末时间、原行数、请求及读取身份。
        异常: 原配置、预算、读取或取消错误；持续构造清理失败时从原异常的
            csv_observation_read_cleanup_owner恢复close。
        副作用: 增加本read自有固定预算，默认iter_batches不启用此采集。
        """
        # 延迟导入避免预算来源与它的可选资源子类循环；默认入口不导入或构造新owner。
        from .csv_observation import CSVObservationRead
        from ..results.spool import _cleanup_owner
        self._ensure_open()
        # 可选观测同样不能越过默认路径遗留的未返回责任，但不改变其他read的开放检查。
        if self._uninstalled_request is not None or self._uninstalled_resources is not None:
            raise SourceClosedError('预算CSV来源尚有未返回请求或资源待清理')
        read = CSVObservationRead(self, request)
        try:
            # 每个read按对象登记，同一request可独立同时扫描，不用request值作全局key。
            self._requests.add(read)
        except BaseException as exc:
            # 未返回的登记失败也不是可恢复推进状态，最高read只保留关闭责任。
            read._failed = True
            _cleanup_owner(read, exc, 'csv_observation_read_cleanup_owner', 'CSV观测读取登记')
            raise
        return read

    def _ensure_open(self) -> None:
        """在固定声明已释放后仍抛明确关闭错误，不访问已丢弃spec。

        参数: 无。返回: None。异常: SourceClosedError为来源已关闭。
        """
        if self.closed or self._closing:
            raise SourceClosedError('预算CSV来源已关闭')

    def _read_resources(self, request: ReadRequest) -> '_CSVResources':
        """在原迭代器实际打开文件前建立独立资源检查器。

        参数: request为已校验请求。返回: _CSVResources。
        异常: 固定预算不足或登记失败；持续清理失败保实际检查器及最高来源恢复owner。
        """
        # 此入口只管理未被请求owner接管的原资源，禁止覆盖已有未安装检查器。
        if self._uninstalled_resources is not None:
            raise SourceClosedError('预算CSV来源尚有未返回资源待清理')
        try:
            resources = _CSVResources(self)
            self._uninstalled_resources = resources
            self._resources.add(resources)
            self._uninstalled_resources = None
        except BaseException as exc:
            resources = self._uninstalled_resources or getattr(exc, 'csv_resources_cleanup_owner', None)
            if resources is not None:
                _cleanup_owner(resources, exc, 'csv_resources_cleanup_owner', '默认CSV资源登记')
                self._uninstalled_resources = None if resources.closed or resources in self._resources else resources
                if not resources.closed:
                    exc.csv_source_cleanup_owner = self
            raise
        return resources

    def _close_handle(self, handle, primary):
        """仅在真实FD关闭后移除登记，业务根因不被附加清理错误覆盖。

        参数: handle实际文件；primary已有原错或None。返回: None。
        异常: 无主错或GeneratorExit时原关闭错误传播；其他主错只增加note。
        """
        try:
            handle.close()
        except BaseException as cleanup:
            if primary is None or isinstance(primary, GeneratorExit):
                raise
            primary.add_note(f'预算CSV文件关闭附加失败: {type(cleanup).__name__}')
        finally:
            if handle.closed:
                self.handles.discard(handle)

    def close(self) -> None:
        """关闭全部包装请求、原句柄与检查器，最后抵销固定声明预算。

        参数: 无。返回: None，成功后幂等。异常: 首个关闭错误，仍尝试其他独立请求；
            尚未结束的子责任及费用保留，恢复后可重复close。
        """
        if self.closed:
            return
        self._closing = True
        first_error = None
        # 未登记子对象仍由本来源拥有；已在集合中的同一对象不会再保留第二个未安装槽。
        if self._uninstalled_request is not None:
            try:
                self._uninstalled_request.close()
                self._uninstalled_request = None
            except BaseException as exc:
                first_error = exc
        # 一个生成器关闭失败也不能跳过其他独立请求及原句柄。
        for iterator in tuple(self._requests):
            try:
                iterator.close()
            except BaseException as exc:
                if first_error is None:
                    first_error = exc
                else:
                    first_error.add_note(f'其他预算CSV请求清理失败: {type(exc).__name__}')
        # 活请求已经负责其生成器/FD/资源；这里只关闭没有更高请求owner的残留资源。
        requests = tuple(self._requests) + (() if self._uninstalled_request is None else (self._uninstalled_request,))
        for iterator in tuple(self.active):
            if any(getattr(request, 'iterator', getattr(request, '_iterator', None)) is iterator for request in requests):
                continue
            try:
                iterator.close()
                self.active.discard(iterator)
            except BaseException as exc:
                if first_error is None:
                    first_error = exc
        for handle in tuple(self.handles):
            if any(getattr(request, '_handle', None) is handle for request in requests):
                continue
            try:
                self._close_handle(handle, None)
            except BaseException as exc:
                if first_error is None:
                    first_error = exc
        resources_to_close = tuple(self._resources) + (() if self._uninstalled_resources is None else (self._uninstalled_resources,))
        for resources in resources_to_close:
            if any(getattr(request, '_resources', None) is resources for request in requests):
                continue
            try:
                resources.close()
                if resources is self._uninstalled_resources:
                    self._uninstalled_resources = None
            except BaseException as exc:
                if first_error is None:
                    first_error = exc
        children_closed = (not self._requests and not self._resources and not self.active and not self.handles
            and self._uninstalled_request is None and self._uninstalled_resources is None)
        if children_closed:
            try:
                _release_owned_ram(self, self._input_cost, '_input_cost')
            except BaseException as exc:
                if first_error is None:
                    first_error = exc
            finally:
                if self._input_cost == 0:
                    self.spec, self.signals, self.choices = None, (), {}
                    self.closed = True
        if first_error is not None:
            if not self.closed:
                first_error.csv_source_cleanup_owner = self
            raise first_error


class _CSVRequest:
    """拥有默认原生成器、真实FD和资源检查器，半关闭只允许重试close。"""

    def __init__(self, owner, request, *, observe_bounds=False):
        """先预约原固定请求费用，再接住原生成器，未返回失败保实际恢复owner。

        参数: owner为预算CSV来源；request沿原结构；observe_bounds按需保存两个时间整数。返回: 独立默认请求。
        异常: 原配置、预算、取消或登记错误；持续清理失败附csv_request_cleanup_owner。
        """
        if type(observe_bounds) is not bool:
            raise TypeError("observe_bounds需要bool")
        self.observe_bounds=observe_bounds
        self.observed_start=self.observed_end=None
        self.owner, self._budget = owner, owner.budget
        self.closed = self._closing = False
        self.current = self.iterator = self._resources = self._handle = None
        self.cost = self._held_cost = 0
        try:
            # 金额与旧请求完全一致；resource_sink只接资源，不采集首末原行事实。
            _reserve_owned_ram(self, 16384 + len(owner.signals) * 4096, 'cost')
            self.iterator = SignalCSVSourceAdapter._request_batches(owner, request, resource_sink=self)
        except BaseException as exc:
            self._adopt_cleanup(exc)
            _cleanup_owner(self, exc, 'csv_request_cleanup_owner', '默认CSV请求构造')
            raise

    def _adopt_cleanup(self, exc):
        """接住本次尚未返回的检查器，不接他请求或借用来源。

        参数: exc原异常。返回: None。异常: 无预期异常。
        """
        resources = getattr(exc, 'csv_resources_cleanup_owner', None)
        if resources is not None and self._resources is None:
            self._resources = resources

    def _created_iterator(self, iterator):
        """在原活动登记前接住同一个实际生成器。

        参数: iterator原生成器。返回: None。异常: 无预期异常。
        """
        self.iterator = iterator

    def _read_resources(self):
        """建立本请求唯一检查器，登记前失败仍由本请求保留责任。

        参数: 无。返回: 真实_CSVResources。异常: 原预算、构造或集合登记错误。
        """
        # 同一次原生成器只建立一个检查器；失败后的旧责任须先由同owner关闭。
        if self._resources is not None:
            raise SourceClosedError('默认CSV请求尚有资源待清理')
        try:
            self._resources = _CSVResources(self.owner)
            self.owner._resources.add(self._resources)
        except BaseException as exc:
            self._adopt_cleanup(exc)
            raise
        return self._resources

    def _opened_handle(self, handle):
        """在原handles集合登记前接住真实只读FD。

        参数: handle实际文件。返回: None。异常: 无预期异常。
        """
        self._handle = handle

    def _close_handle(self, handle, primary):
        """执行原文件关闭责任，失败时保持本请求的实际FD引用。

        参数: handle实际FD；primary已有业务原错或None。返回: None。
        异常: 无主错或GeneratorExit时传播原关闭错误，其余主错保留并加note。
        """
        try:
            self.owner._close_handle(handle, primary)
        finally:
            if handle.closed:
                self._handle = None

    def _end_file(self, resources, primary):
        """抵销文件局部费用，已有业务原错或取消不被附加释放错误取代。

        参数: resources本请求检查器；primary为生成器现场原错。
        返回: None。异常: 正常结束或GeneratorExit时传播原清理错误。
        """
        try:
            resources.end_file()
        except BaseException as cleanup:
            if primary is None or isinstance(primary, GeneratorExit):
                raise
            primary.add_note(f'默认CSV文件费用清理附加失败: {type(cleanup).__name__}')

    def _close_resources(self, primary):
        """仅在真实FD已关闭后清理本请求检查器，保留原主异常。

        参数: primary原错或None。返回: None。异常: 正常关闭失败原样传播。
        """
        if self._handle is not None:
            if primary is None:
                raise SourceReadError('默认CSV文件尚未成功关闭')
            return
        try:
            self._resources.close()
        except BaseException as cleanup:
            if primary is None or isinstance(primary, GeneratorExit):
                raise
            primary.add_note(f'默认CSV资源关闭附加失败: {type(cleanup).__name__}')

    def __iter__(self):
        """返回自有游标。参数: 无。返回: self。异常: 无。"""
        return self

    def __next__(self) -> SignalBatch:
        """推进原生成器，失败/EOF只清自有资源并保留原异常和最高恢复owner。

        参数: 无。返回: 原SignalBatch。异常: 原关闭、EOF、预算、读取或取消错误。
        """
        self.owner._ensure_open()
        if self.closed:
            raise StopIteration
        if self._closing:
            raise SourceClosedError('默认CSV请求正在清理')
        # 结束上一批借引用，原生成器及检查器仍持有原费用直到原交接完成。
        self.current = None
        try:
            self.current = next(self.iterator)
            return self.current
        except StopIteration:
            # 真实EOF尚须本请求固定费用关闭成功；此时没有业务主错，不能用StopIteration遮蔽清理取消。
            self.close()
            raise
        except BaseException as exc:
            self._adopt_cleanup(exc)
            _cleanup_owner(self, exc, 'csv_request_cleanup_owner', '默认CSV请求推进')
            raise

    def close(self) -> None:
        """依次关闭真实生成器/FD/检查器，最后抵销固定费用，成功后才closed。

        参数: 无。返回: None，幂等。异常: 原关闭或预算错误；尚未清完附最高请求owner。
        """
        if self.closed:
            self.owner._requests.discard(self)
            return
        self._closing = True
        first_error = None
        # 生成器可能已在第一次close中退出finally，FD与检查器字段仍须独立重试。
        if self.iterator is not None:
            try:
                self.iterator.close()
            except BaseException as exc:
                first_error = exc
        if self._handle is not None:
            try:
                self.owner._close_handle(self._handle, None)
            except BaseException as exc:
                if first_error is None:
                    first_error = exc
            finally:
                if self._handle.closed:
                    self._handle = None
        if self._handle is None and self._resources is not None:
            try:
                self._resources.close()
            except BaseException as exc:
                if first_error is None:
                    first_error = exc
            finally:
                if self._resources.closed:
                    self._resources = None
        # 实际生成器已关闭且所有子责任结束才释放其固定请求槽；不抵销借用adapter费用。
        iterator_closed = self.iterator is None or self.iterator.gi_frame is None
        if iterator_closed and self._handle is None and self._resources is None:
            self.owner.active.discard(self.iterator)
            self.current = None
            try:
                _release_owned_ram(self, self.cost, 'cost')
            except BaseException as exc:
                if first_error is None:
                    first_error = exc
            finally:
                if self.cost == 0:
                    self.closed = True
                    self.iterator = None
                    self.owner._requests.discard(self)
        if first_error is not None:
            if not self.closed:
                first_error.csv_request_cleanup_owner = self
            raise first_error


class _CSVResources:
    """每请求按用途保存金额，固定读取缓冲、行/ref、数组和协议状态共同计账。

    八个实际属性槽是付款依据，charges只提供兼容视图；_held_cost为槽位总和。
    _closing后不再增加费用，所有用途真实抵销完成才closed并解除来源登记。
    """

    def __init__(self, owner):
        """预留文件解码缓冲及资源容器，不在申请前打开文件。

        参数: owner为预算CSV来源。返回: 独立检查器。异常: BudgetExceededError。
        """
        self.owner, self.budget, self.closed = owner, owner.budget, False
        self._budget, self._held_cost, self._closing = owner.budget, 0, False
        self._fixed_cost = self._reading_cost = self._header_cost = self._row_cost = 0
        self._pending_cost = self._work_cost = self._array_cost = self._protocol_cost = 0
        self.charges, self.line_source, self.array_cost = {}, None, 0
        self._sample_count, self._column_count = 0, {}
        self._string_layout = {}
        # TextIO解码缓冲和固定容器保守64KiB，不声称整进程RSS。
        try:
            self._add('fixed', 65536)
        except BaseException as exc:
            # 可选观测子类已有同一真实恢复边界，默认构造只处理自己的未返回资源。
            if type(self) is _CSVResources:
                _cleanup_owner(self, exc, 'csv_resources_cleanup_owner', '默认CSV资源构造')
            raise

    def _sync(self, key):
        """把真实付款槽同步到兼容charges视图，不从视图反推所有权。

        参数: key为八个固定用途之一。返回: None。异常: 原字典登记错误可重试。
        """
        amount = getattr(self, '_' + key + '_cost')
        if amount:
            self.charges[key] = amount
        else:
            self.charges.pop(key, None)

    def _add(self, key, amount):
        """事务式登记一次真实预约，未入账超限不增加自有金额。

        参数: key为用途；amount为bytes。返回: None。异常: 账本超限/金额错误/取消；
            实际已入账而返回取消时仍保留真实付款槽。
        """
        if self.closed or self._closing:
            raise SourceClosedError('默认CSV资源已关闭或正在清理')
        try:
            _reserve_owned_ram(self, amount, '_' + key + '_cost')
        finally:
            self._sync(key)

    def _release_amount(self, key, amount):
        """只抵销本用途真实费用，释放前后取消均保留正确槽位。

        参数: key固定用途；amount不超过本槽bytes。返回: None。异常: 原释放或取消。
        """
        try:
            _release_owned_ram(self, amount, '_' + key + '_cost')
        finally:
            self._sync(key)

    def _move(self, source, target, amount):
        """转移已付款责任槽，总费用不变，不申请或归还共享余额。

        参数: source/target固定用途，amount为真实已有bytes。返回: None。异常: 金额矛盾ValueError。
        """
        source_slot, target_slot = '_' + source + '_cost', '_' + target + '_cost'
        if amount < 0 or amount > getattr(self, source_slot):
            raise ValueError('默认CSV费用交接超出原用途余额')
        setattr(self, source_slot, getattr(self, source_slot) - amount)
        setattr(self, target_slot, getattr(self, target_slot) + amount)
        self._sync(source)
        self._sync(target)

    def _release(self, key):
        """抵销某用途全部预留。参数: key用途。返回: None。异常: 账本一致性错误。"""
        self._release_amount(key, getattr(self, '_' + key + '_cost'))

    def lines(self, handle):
        """把真实TextIO交给限长物理行迭代器，不自己解释CSV。

        参数: handle为原适配器只读文件。返回: _PhysicalLines。异常: 构造错误传播。
        """
        self.line_source = _PhysicalLines(self, handle)
        return self.line_source

    def records(self, reader):
        """保持原reader的物理计数和解释，为表头/当前逻辑记录保存累积预算。

        参数: reader为原csv.reader。返回: _CSVRecords。异常: 构造错误传播。
        """
        return _CSVRecords(self, reader)

    def _sample_estimate(self, time_text, text, definition):
        """估算新记录独有的容器、数值和文本，不重复计算来源路径或声明。

        参数: time_text/text 为原单元格；definition 为当前信号声明。
        返回: (记录费用, 字符串原值长度)，长度为零表示没有定宽字符串列。
        异常: 输入已由读取器限定；声明查找错误直接传播。
        """
        # 四项 tuple、list 槽、时间/序号/原值和 CSVSourceRef 的实例/字典留量。
        # 路径、字段、会话和来源名均引用固定声明；不按每条样本重新递归收费。
        cost = 384 + getsizeof(text) + getsizeof(time_text)
        width = 0
        if text not in self.owner.spec.missing_values:
            choices = self.owner.choices[definition.name]
            if text in choices:
                original = choices[text]
                width = len(original) if type(original) is str else 0
                if type(original) is int:
                    cost += max(0, getsizeof(original) - 32)
            elif any(type(code) is str for code, _ in definition.choices):
                width = len(text)
            else:
                # 例如 1e4095 只有六个字符，却会在原解析器中展开为 1840B 整数。
                cost += max(0, _expanded_integer_bytes(text) - 32)
        return cost, width

    def _pack_estimate(self, validator, count, columns, unicode_bytes):
        """分别计算最终列、归一化工作区和跨批同刻检查状态的峰值。

        参数: validator 为现有协议状态，其余为候选批大小、列数和字节估算。
        返回: (保留列费用, 打包峰值费用)。异常: 无预期异常。
        """
        # 输出五个数组每项至多 27B，附原码列、引用 tuple 和数组对象留量。
        # 输出仍引用的原值/CSVSourceRef/文本已在 pending 付费，交付时转交 array，
        # 不在临时工作区再付第二次；这里只预留新增数组、指针 tuple 和模型对象。
        retained = 4096 + columns * 1024 + count * 64
        # 384B/样本覆盖类型分组 tuple/索引、临时 records、原值指针、数值数组及掩码。
        # Unicode 仅归一化时存在一份原始 UTF32 数组，不是八份长期输出。
        identities = sum(len(state[1]) for state in validator.pending.values())
        state_cost = 4096 + len(self.owner.signals) * 512 + identities * 256 + count * 256
        workspace = retained + count * 384 + unicode_bytes + state_cost
        return retained, workspace

    def should_flush(self, time_text, text, definition, validator):
        """在再接收一条样本之前判断是否应先交付当前批。

        参数: 原文本、声明和当前协议状态；不解析值、不修改缓冲或预算。
        返回: bool；已有样本且继续累积会挤占打包空间时为 True。
        异常: 无预期异常；单条无法容纳由实际预约明确失败。
        """
        if not self._sample_count:
            return False
        cost, width = self._sample_estimate(time_text, text, definition)
        columns = len(self._column_count) + (definition.name not in self._column_count)
        old_count, old_width = self._string_layout.get(definition.name, (0, 0))
        unicode_bytes = max((n * w * 4 for name, (n, w) in self._string_layout.items()
                             if name != definition.name), default=0)
        if width:
            unicode_bytes = max(unicode_bytes, (old_count + 1) * max(old_width, width) * 4)
        else:
            unicode_bytes = max(unicode_bytes, old_count * old_width * 4)
        if self.owner.backend != 'numpy':
            unicode_bytes = 0
        _, workspace = self._pack_estimate(validator, self._sample_count + 1, columns,
                                           unicode_bytes)
        # 为下一物理行和当前解析结果交接保留 64KiB；不修改用户的 batch_rows。
        available = self.budget.memory_budget_bytes - self.budget.ram_bytes
        receiver_peak = (self._sample_count + 1) * self.owner._consumer_sample_bytes
        # 有接收队列时，输入打包与队列最多使用当前余量的一半，另一半供正在
        # 计算的积分/统计申请临时数组。此处只决定批大小，不把余量重复登记为费用。
        capacity = available // 2 if self.owner._consumer_sample_bytes else available
        return cost + workspace + receiver_peak + 65536 > capacity

    def before_sample(self, time_text, text, path, definition):
        """在值解析及原记录 append 前预留记录独有的数据。

        参数: 原单元格、实际路径及信号声明；路径已在来源构造时计费。
        返回: None。异常: 预算超限或预约取消，仍保留真实已付金额。
        """
        cost, width = self._sample_estimate(time_text, text, definition)
        self._add('pending', cost)
        self._sample_count += 1
        self._column_count[definition.name] = self._column_count.get(definition.name, 0) + 1
        if width:
            count, maximum = self._string_layout.get(definition.name, (0, 0))
            self._string_layout[definition.name] = (count + 1, max(maximum, width))

    def before_pack(self, pending, validator):
        """在创建数组前预留实际候选批的峰值，不按最大批大小预先拒绝。

        参数: pending 为有限原缓冲；validator 为跨批协议状态。返回: None。
        异常: 单批真实工作区超限或取消；不丢样本，也不切换计算后端。
        """
        count = sum(len(records) for records in pending.values())
        unicode_bytes = 0
        if self.owner.backend == 'numpy':
            for records in pending.values():
                # 各列依次打包，原始 Unicode 数组在返回数值列前释放，只取最大列峰值。
                widths = [len(item[2]) for item in records if type(item[2]) is str]
                unicode_bytes = max(unicode_bytes, len(widths) * max(widths, default=0) * 4)
        retained, workspace = self._pack_estimate(validator, count, len(pending), unicode_bytes)
        self._add('work', workspace)
        self.array_cost = retained

    def after_pack(self, validator):
        """校验完成后把工作预留转为当前owned数组和保留协议状态。

        参数: validator为已accept状态。返回: None。异常: 内部账本一致性错误。
        """
        state_cost = sum(512 + len(state[1]) * 256 for state in validator.pending.values())
        # 旧batch已被原生成器和包装游标交接；新数组预留早已申请，不重复申请。
        self._release('array')
        self._release('protocol')
        # 原对象由缓冲与新列共享，既有付款转交输出责任，不申请第二份费用。
        self._move('pending', 'array', self._pending_cost)
        self._move('work', 'array', self.array_cost)
        self._move('work', 'protocol', state_cost)
        self._release('work')

    def clear_pending(self):
        """原生成器恢复并清空缓冲后重置计数，不重复抵销已转交的共享费用。

        参数: 无。返回: None。异常: 账本一致性错误。
        """
        self._release('pending')
        self._sample_count = 0
        self._column_count.clear()
        self._string_layout.clear()

    def end_file(self):
        """局部行/表头引用丢弃后抵销预算，跨文件样本与协议预算保留。

        参数: 无。返回: None。异常: 账本一致性错误。
        """
        self.line_source = None
        for key in ('reading', 'header', 'row'):
            self._release(key)

    def close(self):
        """释放本请求全部金额，不关闭他请求或删除输入文件。

        参数: 无。返回: None，幂等。异常: 账本一致性错误。
        """
        if self.closed:
            return
        self._closing = True
        self.line_source = None
        for key in ('fixed', 'reading', 'header', 'row', 'pending', 'work', 'array', 'protocol'):
            self._release(key)
        if self._held_cost == 0:
            self.closed = True
            self.owner._resources.discard(self)


class _PhysicalLines:
    """每次readline前按剩余RAM申请上限；引用记录跨行继续累积reading金额。"""

    def __init__(self, resources, handle):
        """保存真实只读句柄。参数: resources检查器/handle文件。返回: 新行游标。异常: 无。"""
        self.resources, self.handle = resources, handle

    def __iter__(self):
        """返回物理行游标。参数: 无。返回: self。异常: 无。"""
        return self

    def _retained_line_bytes(self, text, first_line):
        """计算当前逻辑记录仍需保存的解析字符和字段开销。

        参数: text 为刚读取的物理行；first_line 表示该逻辑记录的第一行。
        返回: 字节估算。异常: 无预期异常。
        """
        if not text:
            return 0
        # 原文本、CSV 的 UTF32 字符缓冲及结果字符串按 16B/字符预留。
        # 每个分隔符另加字段对象/列表槽费用；引号内分隔符保守计入。
        # 固定容器按逻辑记录计一次，不能对引用单元格的每一行重复收 8KiB。
        return (256 if first_line else 0) + len(text) * 16 + text.count(self.resources.owner.spec.delimiter) * 48

    def __next__(self):
        """有界读完整物理行，超限不把截断内容交给csv.reader。

        参数: 无。返回: 含原换行的str；EOF停止。异常: BudgetExceededError/原I/O错误。
        """
        budget = self.resources.budget
        # 16B/字符先覆盖文本与字符缓冲；实际分隔符对应的字段费用在交给 CSV 解析器前另加。
        capacity = (budget.memory_budget_bytes - budget.ram_bytes - 8192) // 16 - 1
        if capacity <= 0:
            raise BudgetExceededError('CSV物理行/引用记录累积超出剩余RAM估算')
        amount = 8192 + (capacity + 1) * 16
        first_line = not self.resources._reading_cost
        self.resources._add('reading', amount)
        try:
            # 多读一字符仅判别完整物理行，不能把部分未闭合引号当另一记录。
            text = self.handle.readline(capacity + 1)
        except BaseException as exc:
            try:
                self.resources._release_amount('reading', amount)
            except BaseException as cleanup:
                exc.add_note(f'默认CSV物理行清理附加失败: {type(cleanup).__name__}')
            raise
        retained = self._retained_line_bytes(text, first_line)
        if retained > amount:
            self.resources._add('reading', retained - amount)
        else:
            self.resources._release_amount('reading', amount - retained)
        if len(text) > capacity:
            raise BudgetExceededError('CSV物理行超过剩余RAM允许长度，未解析截断行')
        if not text:
            raise StopIteration
        return text


class _CSVRecords:
    """包装原csv.reader，表头固定持有，当前/下一逻辑记录读取时预算重叠。"""

    def __init__(self, resources, reader):
        """保存原解析器。参数: resources检查器/reader原csv.reader。返回: 新记录游标。异常: 无。"""
        self.resources, self.reader, self.first = resources, reader, True

    def __iter__(self):
        """返回记录游标。参数: 无。返回: self。异常: 无。"""
        return self

    def __next__(self):
        """推进原解析器，跨物理行累积到一条完整记录再转移预算。

        参数: 无。返回: 原单元格list。异常: EOF/原csv错误/预算或I/O错误。
        """
        # 上一cells在调用next期间仍由原生成器保存，先完成新解析再释放旧行预算。
        cells = next(self.reader)
        key = 'header' if self.first else 'row'
        self.resources._release(key)
        self.resources._move('reading', key, self.resources._reading_cost)
        self.first = False
        return cells
