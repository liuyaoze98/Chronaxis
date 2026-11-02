"""在完整组之间查询最新信号的有限保持，独立计算参考与NumPy有效性。

输入为LatestSignalState、声明来源描述/封存EOF事实及请求域，输出须关闭的查询结果。
最新观测不可回溯：查询不能早于最后已提交组，驱动器须先查旧状态再提交新组。
先检查精确时间与来源身份，再按domain/来源半开或point范围、严格TTL叠加质量。
参考用Python整数逐点计算，NumPy用真实数组掩码及uint64时间差，均不再归一化。
结果独立持有样本引用预算，state更新/关闭不会使仍存活的查询漏计；owner关闭全部结果。
本模块不读取文件/旧链，不执行表达式、事件或指标；预算为保守估算而非整进程RSS。
"""

# 冻结模型共享协议，不共享两个有效性计算内核。
from dataclasses import dataclass
from types import MappingProxyType
import numpy as np
from ..core.models import Interval
from ..core.types import QualityFlag, SignalDType
from ..core.validation import require_identifier
from ..results.errors import ResultClosedError
from ..sources.models import SourceDescription
from ..timebase.conversion import INT64_MAX, require_int64_ns
from .history import _metadata_bytes
from .history_records import HistoryProgress, HistorySample, estimate_record_bytes
from .state import LatestSignalState

# (N,)物理列保持声明类型，ENUM代码必须用labels解释，不能提升大uint为float。
_DTYPES = MappingProxyType({SignalDType.INT64: np.dtype('int64'), SignalDType.UINT64: np.dtype('uint64'),
                           SignalDType.FLOAT64: np.dtype('float64'), SignalDType.BOOL: np.dtype('bool'),
                           SignalDType.ENUM: np.dtype('int64')})


@dataclass(frozen=True)
class HoldContext:
    """保存原来源端点与whole-source EOF事实；未知首端保持None，不补假设周期。

    输入应来自当前描述和已seal历史；模型检查事实一致性，不凭传入EOF宣称文件已校验。
    """

    session_id: str
    domain: Interval
    descriptions: tuple[SourceDescription, ...]
    completions: tuple[HistoryProgress, ...]

    def __post_init__(self):
        """校验固定身份/EOF及已知端点一致性，不读取文件或推断未知端点。

        参数: 无，读取冻结字段。返回: None。异常: TypeError/ValueError为协议不一致。
        """
        require_identifier(self.session_id, 'hold.session_id')
        if (not isinstance(self.domain, Interval) or type(self.descriptions) is not tuple or not self.descriptions
                or any(not isinstance(item, SourceDescription) for item in self.descriptions)
                or type(self.completions) is not tuple or any(not isinstance(item, HistoryProgress) for item in self.completions)):
            raise TypeError('保持上下文需要Interval与typed tuple描述/EOF')
        # 每源只有一份最终事实；批次sample_count不能冒充全源样本总数。
        descriptions = {item.name: item for item in self.descriptions}
        completions = {item.source: item for item in self.completions}
        if (len(descriptions) != len(self.descriptions) or len(completions) != len(self.completions)
                or descriptions.keys() != completions.keys()):
            raise ValueError('保持描述与EOF来源必须唯一且完全对应')
        for name, completion in completions.items():
            description = descriptions[name]
            if not completion.source_eof or completion.session_id != self.session_id:
                raise ValueError('保持上下文需要当前会话whole-source EOF')
            end, start = completion.observed_end_ns, description.observation_start_ns
            if description.observation_end_ns is not None and end != description.observation_end_ns:
                raise ValueError('EOF终点与原描述不一致')
            if start is not None and end is not None and end < start:
                raise ValueError('EOF终点早于原来源起点')


@dataclass(frozen=True)
class HoldPoint:
    """保存一个参考查询点；无效值仍保留原逻辑诊断，无历史时sample/value为None。"""

    time_ns: int
    value: int | float | bool | str | None
    valid: bool
    quality: QualityFlag
    sample: HistorySample | None
    actual_update: bool


@dataclass(frozen=True)
class _HeldArrays:
    """保存内部已检查的(N,)只读列，values为物理dtype，sample保留原逻辑诊断。

    has_sample区分domain外/无历史与域内无效更新；NumPy写保护是正常使用约定。
    """

    time_ns: np.ndarray
    values: np.ndarray
    valid: np.ndarray
    quality: np.ndarray
    actual_update: np.ndarray
    has_sample: np.ndarray
    dtype: SignalDType
    labels: tuple[str, ...]
    sample: HistorySample | None


class HoldResult:
    """持有一份结果和原样本预算直到close；外部另存已取得数组/rows需自行负责。"""

    def __init__(self, owner, cost, definition, sample, payload):
        """仅由已预留预算的查询owner构造；不再复制大列。

        参数: owner/cost自有申请、definition声明、sample原记录、payload已构造结果。
        返回: None；初始化实例状态。异常: 分配错误传播给owner抵销申请。
        """
        self._owner, self._cost, self._definition = owner, cost, definition
        self._sample, self._payload, self._closed = sample, payload, False

    def _ensure_open(self):
        """拒绝关闭后访问。参数: 无。返回: None。异常: ResultClosedError。"""
        if self._closed:
            raise ResultClosedError('保持查询结果已关闭')

    @property
    def closed(self):
        """返回持有状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    @property
    def definition(self):
        """读取原冻结声明。参数: 无。返回: SignalDefinition。异常: ResultClosedError。"""
        self._ensure_open()
        return self._definition

    @property
    def sample(self):
        """读取原最新记录。参数: 无。返回: HistorySample或None。异常: ResultClosedError。"""
        self._ensure_open()
        return self._sample

    @property
    def rows(self):
        """读取参考结果。参数: 无。返回: tuple[HoldPoint]。异常: 关闭或后端类型错误。"""
        self._ensure_open()
        if type(self._payload) is not tuple:
            raise TypeError('NumPy查询请读取arrays')
        return self._payload

    @property
    def arrays(self):
        """读取NumPy列。参数: 无。返回: _HeldArrays。异常: 关闭或后端类型错误。"""
        self._ensure_open()
        if not isinstance(self._payload, _HeldArrays):
            raise TypeError('参考查询请读取rows')
        return self._payload

    def close(self):
        """丢弃自有引用并抵销完整查询预算，状态可已先关闭。

        参数: 无。返回: None，幂等。异常: 内部账本一致性错误。
        """
        if self._closed:
            return
        # 单线程账本快照区分未扣账与已扣账的返回取消，只处理本结果申请。
        budget, cost = self._owner._budget, self._cost
        before = budget.ram_bytes
        released = False
        try:
            budget.release_ram(cost)
            released = True
        finally:
            # 操作已经扣账时即使抛取消也完成最小脱离；未扣账保持可重试。
            if released or budget.ram_bytes == before - cost:
                self._discard()

    def _discard(self):
        """移除登记并丢弃引用，不再次抵销申请。

        参数: 无；仅在预算已经释放或查询失败由外层持有金额时调用。
        返回: None，结果关闭。
        异常: 登记容器错误传播，finally仍标记关闭避免再次扣账。
        """
        # 外层负责一次性抵销成本；即使脱离被取消也不再留下可重复释放的结果。
        try:
            self._owner._results.discard(self)
        finally:
            self._closed, self._cost = True, 0
            self._payload = self._sample = self._definition = self._owner = None


class HoldQueries:
    """持有固定上下文/声明及活动查询；查询快照不会随state后续更新改变。"""

    def __init__(self, state: LatestSignalState, context: HoldContext):
        """先申请context/声明容器空间，再校验当前绑定与来源描述。

        参数: state当前打开最新状态；context已seal输入事实及请求域。
        返回: 新owner。异常: 绑定/预算/构造错误，保留原异常并清理固定申请。
            持续清理失败时，原异常的hold_queries_cleanup_owner提供本次查询owner的恢复close入口。
        """
        if not isinstance(state, LatestSignalState) or not isinstance(context, HoldContext):
            raise TypeError('保持查询需要最新状态和HoldContext')
        state._ensure_open()
        if state.session_id != context.session_id:
            raise ValueError('保持会话与最新状态不一致')
        # 元数据深成本覆盖owner在state关闭后仍持有的声明和原描述。
        cost = 32768 + len(state.definitions) * 8192 + _metadata_bytes((context, tuple(state.definitions.values()))) * 16
        self._budget, self._closed, self._fixed_cost = state.budget, False, 0
        self._state = self._context = self._definitions = self._bounds = self._labels = self._results = None
        before = self._budget.ram_bytes
        try:
            # 申请包含在构造保护内，返回取消仍能辨认已经记账的固定成本。
            self._budget.reserve_ram(cost)
            self._fixed_cost = cost
            self._state, self._context = state, context
            self._results = set()
            self._definitions = MappingProxyType(dict(state.definitions))
            descriptions = {item.name: item for item in context.descriptions}
            self._bounds = MappingProxyType({item.source: (descriptions[item.source].observation_start_ns, item.observed_end_ns)
                                             for item in context.completions})
            labels_by_name = {}
            # 原字段/dtype/单位/标签域与当前声明完全相同，不能借context换来源身份。
            for name, definition in self._definitions.items():
                description = descriptions.get(definition.source)
                field = next((item for item in description.fields if item.name == name), None) if description is not None else None
                labels = tuple(dict.fromkeys(label for _, label in definition.choices)) if definition.dtype is SignalDType.ENUM else ()
                labels_by_name[name] = labels
                if (field is None or field.field.field != definition.field or field.dtype is not definition.dtype
                        or field.unit != definition.unit or definition.dtype is SignalDType.ENUM and field.metadata.get('labels') != labels):
                    raise ValueError('保持上下文与当前信号绑定不一致')
            # 标签域可任意大；固定申请覆盖一次构造，所有查询借用同一冻结tuple。
            self._labels = MappingProxyType(labels_by_name)
        except BaseException as exc:
            # 申请成功而赋值前取消时，将该金额交给同一部分构造关闭边界。
            if self._fixed_cost == 0 and self._budget.ram_bytes == before + cost:
                self._fixed_cost = cost
            # 只关闭当前查询owner；借用state保持打开，清理错误不替换原构造异常。
            try:
                self.close()
            except BaseException as cleanup:
                exc.add_note(f'保持查询初始化清理附加失败: {type(cleanup).__name__}')
                if not self._closed:
                    try:
                        self.close()
                    except BaseException as retry:
                        exc.add_note(f'保持查询初始化清理重试失败: {type(retry).__name__}')
                        if not self._closed:
                            exc.hold_queries_cleanup_owner = self
                            exc.add_note('释放恢复后调用hold_queries_cleanup_owner.close()')
            raise

    @property
    def closed(self):
        """返回owner状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    def _ensure_open(self):
        """拒绝关闭owner或state后的新查询。参数: 无。返回: None。异常: ResultClosedError。"""
        if self._closed:
            raise ResultClosedError('保持查询owner已关闭')
        self._state._ensure_open()

    def _capture(self, name, point):
        """取得当前固定声明/最新记录及原范围，拒绝无法证明的非空EOF范围。

        参数: name别名/point显式bool。返回: definition/sample/(start,end)。
        异常: 关闭、未知名、模式或来源事实错误；不计算两后端有效性。
        """
        self._ensure_open()
        if type(point) is not bool:
            raise TypeError('point需要bool')
        definition, sample = self._definitions[name], self._state.get(name)
        bounds = self._bounds[definition.source]
        if sample is not None:
            start, end = bounds
            if end is None:
                raise ValueError('非空状态缺少来源观测终点，不能证明保持范围')
            if sample.time_ns > end or start is not None and sample.time_ns < start:
                raise ValueError('当前样本超出来源观测事实')
        return definition, sample, bounds

    def _cost(self, count, sample):
        """估算所有轴/结果/临时副本及查询独立持有样本空间。

        参数: count点数/sample可选原记录。返回: int bytes。异常: 记录估算错误。
        """
        # 每点1024保守覆盖Python行/标量或数组ufunc多份掩码，引用大文本另单独计入。
        return 8192 + count * 1024 + (0 if sample is None else estimate_record_bytes(sample))

    def _register(self, cost, definition, sample, payload):
        """在预留内构造待登记结果，让外层先取得局部所有权。

        参数: cost申请/definition/sample/payload已完成对象。返回: HoldResult。
        异常: 构造错误传播；不在本方法内安装，返回取消由查询抵销申请。
        """
        # 外层必须先取得对象再执行add，才能撤销部分安装且不扫描其他结果。
        return HoldResult(self, cost, definition, sample, payload)

    def query_reference(self, name, times_ns: tuple[int, ...], *, point=False):
        """独立Python整数参考保持，输出保留原逻辑值的逐点结果。

        参数: name别名、times_ns非递减tuple整数ns、point是否包含domain/来源末端。
        返回: HoldResult；使用后close。异常: 时间/范围/预算/构造错误，无状态副作用。
        """
        definition, sample, (start, end) = self._capture(name, point)
        if type(times_ns) is not tuple:
            raise TypeError('参考保持轴需要tuple')
        cost = self._cost(len(times_ns), sample)
        before, reserved, result = self._budget.ram_bytes, False, None
        try:
            # 先申请再构造时间/行；成功返回前的取消也位于本保护边界内。
            self._budget.reserve_ram(cost)
            reserved = True
            # 规范精确整数在预留后执行，空轴合法，重复点不去重。
            times = tuple(require_int64_ns(time, 'hold.time_ns') for time in times_ns)
            if any(right < left for left, right in zip(times, times[1:])):
                raise ValueError('保持查询轴回退')
            if times and self._state.last_time_ns is not None and times[0] < self._state.last_time_ns:
                raise ValueError('最新状态不能回溯已经提交的过去')
            rows, domain = [], self._context.domain
            for time in times:
                in_domain = domain.start_ns <= time and (time <= domain.end_ns if point else time < domain.end_ns)
                if not in_domain or sample is None:
                    rows.append(HoldPoint(time, None, False, QualityFlag.MISSING, None, False))
                    continue
                # 源首端未知仍保留None；当前真实样本已证明后续查询的起点，不证明更早覆盖。
                quality = sample.value.quality
                if time - sample.time_ns >= definition.valid_for_ns:
                    quality |= QualityFlag.STALE
                if (start is not None and time < start) or (time > end if point else time >= end):
                    quality |= QualityFlag.MISSING
                valid = sample.value.valid and quality == QualityFlag.NONE
                rows.append(HoldPoint(time, sample.value.value, valid, quality, sample, time == sample.time_ns))
            # 取得局部结果后才安装，半add取消只撤销当前对象，不影响已有结果。
            result = self._register(cost, definition, sample, tuple(rows))
            self._results.add(result)
            return result
        except BaseException:
            # 失败结果关闭不再自行扣账，金额由本查询保护边界唯一抵销。
            try:
                if result is not None:
                    result._discard()
            finally:
                if reserved or self._budget.ram_bytes == before + cost:
                    self._budget.release_ram(cost)
            raise

    def query_numpy(self, name, times_ns: np.ndarray, *, point=False):
        """用独立数组掩码计算(N,)保持列，精确无符号差覆盖负到正大age。

        参数: name别名、times_ns完整一维int64 ndarray、point显式bool。
        返回: HoldResult.arrays只读自有列；无效物理占位不替代sample逻辑诊断。
        异常: 轴/范围/预算/分配错误；不调用参考保持、不隐式cast时间或信号类型。
        """
        definition, sample, (start, end) = self._capture(name, point)
        if type(times_ns) is not np.ndarray or times_ns.dtype != np.dtype('int64') or times_ns.ndim != 1:
            raise TypeError('NumPy保持轴需要一维完整int64 ndarray')
        cost = self._cost(len(times_ns), sample)
        before, reserved, result = self._budget.ram_bytes, False, None
        try:
            # 列申请在保护内，返回取消不会遗留尚无结果对象的预算。
            self._budget.reserve_ram(cost)
            reserved = True
            # 轴副本/比较掩码均在预留内，非连续输入不会被原地改写。
            axis = times_ns.copy()
            if np.any(axis[1:] < axis[:-1]):
                raise ValueError('保持查询轴回退')
            if len(axis) and self._state.last_time_ns is not None and int(axis[0]) < self._state.last_time_ns:
                raise ValueError('最新状态不能回溯已经提交的过去')
            domain = self._context.domain
            in_domain = (axis >= domain.start_ns) & (axis <= domain.end_ns if point else axis < domain.end_ns)
            values = np.zeros(len(axis), dtype=_DTYPES[definition.dtype])
            quality = np.full(len(axis), int(QualityFlag.MISSING), dtype='uint16')
            valid, actual, has_sample = np.zeros(len(axis), dtype='bool'), np.zeros(len(axis), dtype='bool'), np.zeros(len(axis), dtype='bool')
            if sample is not None:
                # 所有查询已保证>=最新组>=样本；按uint64位值相减得到0..2**64-1精确age。
                ages = np.subtract(axis.view('uint64'), np.uint64(sample.time_ns % (1 << 64)))
                stale = ages >= np.uint64(definition.valid_for_ns)
                in_source = (axis <= end if point else axis < end)
                if start is not None:
                    in_source &= axis >= start
                quality[in_domain] = int(sample.value.quality)
                quality[in_domain & stale] |= int(QualityFlag.STALE)
                quality[in_domain & ~in_source] |= int(QualityFlag.MISSING)
                has_sample = in_domain.copy()
                values[in_domain] = sample.array_value
                valid = in_domain & (quality == 0) & sample.value.valid
                actual = in_domain & (axis == sample.time_ns)
            labels = self._labels[name]
            # 列皆为自有(N,)内存；常规写保护不宣称可防恶意重设flags。
            for column in (axis, values, valid, quality, actual, has_sample):
                column.flags.writeable = False
            payload = _HeldArrays(axis, values, valid, quality, actual, has_sample, definition.dtype, labels, sample)
            # 整列数值核完成后才取得/安装冻结输出，不改变数组有效性计算。
            result = self._register(cost, definition, sample, payload)
            self._results.add(result)
            return result
        except BaseException:
            # 当前局部对象可能已经半安装，先脱离，再抵销本次一次性金额。
            try:
                if result is not None:
                    result._discard()
            finally:
                if reserved or self._budget.ram_bytes == before + cost:
                    self._budget.release_ram(cost)
            raise

    def next_expiry(self, name, after_ns):
        """返回当前样本下一TTL边界，超域/来源终点或int64时返回None。

        参数: name别名/after_ns不早于最后提交组的整数ns。返回: int ns或None，严格晚于after。
        异常: 关闭、时间、绑定或来源事实错误；不把TTL伪造为实际更新。
        """
        definition, sample, (_, end) = self._capture(name, False)
        after = require_int64_ns(after_ns, 'hold.after_ns')
        if self._state.last_time_ns is not None and after < self._state.last_time_ns:
            raise ValueError('TTL查询不能回退已提交时间')
        if sample is None:
            return None
        # Python整数相加不wrap；结束边界可同时承载EOF与TTL诊断，但不增加持续面积。
        deadline, domain = sample.time_ns + definition.valid_for_ns, self._context.domain
        return deadline if after < deadline <= INT64_MAX and domain.start_ns <= deadline <= min(domain.end_ns, end) else None

    def close(self):
        """关闭全部活动结果及固定上下文，不关闭调用方state或删除历史。

        参数: 无。返回: None，幂等。异常: 内部账本一致性错误。
        """
        if self._closed:
            return
        # 用逐项pop避免关闭时再分配完整活动结果副本，允许部分构造失败收尾。
        while self._results:
            result = next(iter(self._results))
            result.close()
            # 已关闭但脱离取消的结果不再扣账；后续owner关闭可移除其残留登记。
            self._results.discard(result)
        cost, before = self._fixed_cost, self._budget.ram_bytes
        released = False
        try:
            self._budget.release_ram(cost)
            released = True
        finally:
            # 固定申请未抵销时保留owner供重试，已抵销的取消只完成引用收尾。
            if released or self._budget.ram_bytes == before - cost:
                self._finish_close()

    def _finish_close(self):
        """丢弃已释放固定成本的owner引用，不再操作账本。

        参数: 无。返回: None，owner关闭。
        异常: 无主动异常；仅供已完成释放的正常或取消收尾使用。
        """
        # 与调用方state不共享关闭责任，丢弃本owner引用而不关闭上游。
        self._closed, self._fixed_cost = True, 0
        self._state = self._context = self._definitions = self._bounds = self._labels = self._results = None
