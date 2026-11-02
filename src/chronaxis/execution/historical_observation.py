"""把真实来源扫描与封存历史核对为按时钟分组的实际观测范围。

输入为原history、HoldContext、DecodedBindings、AnalysisPlan及全部真实完成且
仍存活的ObservedSourceScan。构造先为有限证明、时钟组及摘要工作区付费，再逐源
完整读取新history，核对实际EOF、SHA、计数和最终进度；不重扫原CSV，不接手造
端点模型冒充扫描证明。最多同时持一个自有历史reader，失败保存最高恢复owner。

同组范围取该组所有有真实原时间行来源的外包络，各源的独立首末事实同时保留。
空投影仍有原行；row_count=0不借声明端点制造观测。原端点按整数ns分别保存，
只对与原请求domain的交集构造Interval，避免域外原范围跨越int64跨度上限。
真正相交的单点保留Interval(t,t)，完全域外或空输入使用actual=None。

依赖选择先应用原bindings.require_synchronized，独立来源不因其他时钟缺同步
而拒绝；联合依赖不能跨不可比较组。无依赖使用dataset组，不借其他origin填域。
已有offset不再施加。稳定identity包含原请求、绑定、实际历史及原行/范围/分组
事实，空投影下不同原首端仍可区分，不改原bindings.identity或任何结果schema。

getters检查原对象、扫描活性及当前元数据，不为每次查询重复扫文件。显式close
只释放本owner的小型副本和reader，不关闭借用扫描、来源、history或binding lease。
预算是本层保守持有估算，不代表进程RSS；默认旧入口不在本模块改变。
"""

# 只复用原冻结合同、同步规则和实际历史游标，不读取原来源或数值数据数组。
from dataclasses import dataclass, replace
from ..core.decoded_binding import DecodedBindings
from ..core.models import Interval
from ..core.types import TimeType
from ..core.validation import require_identifier
from ..planning.plan import AnalysisPlan
from ..results.errors import ResultClosedError, ResultFormatError
from ..results.spool import _cleanup_owner, _reserve_owned_ram, _release_owned_ram
from ..timebase.conversion import require_int64_ns
from .bindings import _fingerprint
from .history import DecodedHistoryStore, _metadata_bytes
from .history_records import HistoryProgress, HistorySample
from .hold import HoldContext
from .observed_ingestion import ObservedSourceScan, SourceScanObservation


@dataclass(frozen=True)
class ObservationScope:
    """保存一个可比时钟组的有限范围事实，本身不提供真实读取证明。"""

    clock_key: tuple  # 完整时钟组身份；dataset、独立relative和独立UTC分开。
    sources: tuple[str, ...]  # 同组全部来源名称，顺序为原计划来源顺序。
    observed_start_ns: int | None  # 有原行来源的组外包络首端，单位整数ns。
    observed_end_ns: int | None  # 外包络末端，逐端检查，不先计算域外跨度。
    actual: Interval | None  # 与原domain的交集；None为空，Interval(t,t)是真实单点。

    def __post_init__(self):
        """校验冻结组和标量端点，不把完整域外范围建成Interval。

        参数: 无，读取冻结字段。返回: None。异常: 类型、来源重复或端点矛盾。
        """
        if (type(self.clock_key) is not tuple or not self.clock_key
                or any(value is not None and type(value) is not str for value in self.clock_key)
                or type(self.sources) is not tuple):
            raise TypeError('观测范围需要冻结时钟key及来源tuple')
        for source in self.sources:
            require_identifier(source, 'observation_scope.source')
        if len(set(self.sources)) != len(self.sources):
            raise ValueError('观测时钟组来源不能重复')
        if (self.observed_start_ns is None) != (self.observed_end_ns is None):
            raise ValueError('观测时钟组首末端须同时已知或同时无观测')
        if self.observed_start_ns is not None:
            require_int64_ns(self.observed_start_ns, 'observation_scope.start')
            require_int64_ns(self.observed_end_ns, 'observation_scope.end')
            if self.observed_start_ns > self.observed_end_ns:
                raise ValueError('观测时钟组末端不能早于首端')
        if self.actual is not None:
            if not isinstance(self.actual, Interval):
                raise TypeError('actual须为Interval或明确None')
            if (self.observed_start_ns is None or self.actual.start_ns < self.observed_start_ns
                    or self.actual.end_ns > self.observed_end_ns):
                raise ValueError('实际交集不能超出已核实组端点')


@dataclass(frozen=True)
class _SourceScopeProof:
    """保留有限逐源证明副本，不持有原行、SourceSpec.rows或整个计划副本。"""

    source: str  # 原来源名。
    description_sha256: str  # 当前实际描述完整指纹。
    request_sha256: str  # 真正写入该history的原请求指纹。
    history_sha256: str  # 构造中实际读到文件EOF后核实的规范历史SHA。
    counts: tuple[int, int]  # 原进度记录数、原信号样本数。
    observation: SourceScanObservation  # 本owner拥有的有限原行和端点事实副本。
    clock_key: tuple  # 该来源实际进入的可比时钟组。


class HistoricalObservationScopes:
    """拥有预建组、有限证明及一个历史reader，关闭不接管任何借用资源。"""

    def __init__(self, history, context, bindings, plan, source_scans):
        """核对全部真实扫描、原合同及当前文件EOF，再冻结按时钟分组的范围。

        参数: 前四项为本次原history/context/运行bindings/plan；source_scans为全部
            活且完成的ObservedSourceScan tuple，可乱序但须唯一覆盖原计划来源。
        返回: 可按真实依赖借读预建ObservationScope的owner。
        异常: 类型、身份、投影、同步元数据、实际历史或预算原错；持续清理失败从
            historical_observation_scopes_cleanup_owner恢复close。
        """
        if (not isinstance(history, DecodedHistoryStore) or not isinstance(context, HoldContext)
                or not isinstance(bindings, DecodedBindings) or not isinstance(plan, AnalysisPlan)
                or type(source_scans) is not tuple
                or any(type(scan) is not ObservedSourceScan for scan in source_scans)):
            raise TypeError('范围需实际history/context/bindings/plan及真实扫描tuple')
        if len(source_scans) != len(plan.sources):
            raise ValueError('范围扫描须唯一且完整覆盖计划全部来源')
        history._check('sealed')
        # 首次预算回调前安装全部恢复字段；借用引用不深复制原配置或memory行。
        self._history, self._context, self._bindings, self._plan = history, context, bindings, plan
        self._source_scans, self._budget = source_scans, history.budget
        self._reader = None
        self._fixed_cost = self._held_cost = 0
        self._scan_by_source = self._proofs = self._scope_by_key = self._scope_by_source = None
        self._source_observations = self._dataset_key = self._identity = None
        self._closed = self._closing = self._failed = False
        try:
            # 先付小型初始化槽，再按有限描述和来源数付配置/摘要/副本上界。
            _reserve_owned_ram(self, 4096, '_fixed_cost')
            cost = (65536 + 16384 * (len(plan.sources) + len(bindings.signals))
                + 16 * (_metadata_bytes(context) + _metadata_bytes(bindings.sources))
                + 16 * sum(_metadata_bytes((item.name, item.timebase)) for item in plan.bindings.sources))
            _reserve_owned_ram(self, cost, '_fixed_cost')
            self._require_contract()
            self._scan_by_source = {}
            for scan in source_scans:
                source = scan.source_plan
                if not any(source is item for item in plan.sources) or source.name in self._scan_by_source:
                    raise ValueError('扫描须属于本计划原SourcePlan且每来源仅一次')
                self._scan_by_source[source.name] = scan
            if set(self._scan_by_source) != {source.name for source in plan.sources}:
                raise ValueError('实际扫描来源与计划不对应')
            self._dataset_key = self._clock_key(plan.dataset.timebase, dataset=True)
            self._proofs = {}
            declarations = {item.name: item for item in plan.bindings.sources}
            evidenced = {item.source for item in plan.bindings.synchronization}
            for source in plan.sources:
                scan = self._scan_by_source[source.name]
                observation, description_sha, request_sha, digest, counts = self._validate_source(source, scan)
                # 只逐源重放新history，实际EOF/SHA核实后才复制该来源有限范围事实。
                self._verify_source(source.name, digest, counts)
                clock = declarations[source.name].timebase
                mapped = (clock == plan.dataset.timebase or source.name in evidenced
                    or clock.time_type is TimeType.ABSOLUTE and plan.dataset.timebase.time_type is TimeType.ABSOLUTE)
                key = self._dataset_key if mapped else self._clock_key(clock)
                self._proofs[source.name] = _SourceScopeProof(source.name, description_sha, request_sha,
                    digest, counts, replace(observation), key)
            self._build_scopes()
            self._source_observations = tuple(self._proofs[source.name].observation for source in plan.sources)
            # 摘要只含有限证明；没有随机read身份、临时目录或原rows，等价事实可稳定重放。
            self._identity = _fingerprint(('historical-observation-scopes-v1', plan.identity,
                bindings.identity, tuple(self._proofs.values()), tuple(self._scope_by_key.values())))
            self.assert_current(history, context, bindings, plan)
        except BaseException as exc:
            self._failed = True
            self._adopt_cleanup(exc)
            _cleanup_owner(self, exc, 'historical_observation_scopes_cleanup_owner', '历史观测范围构造')
            raise

    def _clock_key(self, clock, *, dataset=False):
        """返回完整可比组键。参数: 原TimebaseSpec/dataset标记。返回: tuple。异常: 无预期异常。"""
        # UTC绝对坐标可比较；relative必须保留完整ID/kind/origin，不能仅靠数值相同。
        if dataset:
            return ('dataset', clock.timebase_id, clock.time_type.value, clock.origin)
        if clock.time_type is TimeType.ABSOLUTE:
            return ('utc',)
        return ('relative', clock.timebase_id, clock.time_type.value, clock.origin)

    def _require_contract(self):
        """核原会话、domain、声明绑定及来源集合。参数: 无。返回: None。异常: 契约不一致。"""
        self._history._check('sealed')
        if (self._history.budget is not self._budget or self._bindings.declarations is not self._plan.bindings
                or self._context.session_id != self._plan.dataset.session_id
                or self._context.domain != self._plan.dataset.domain):
            raise ValueError('范围须保原计划绑定、会话及请求domain')
        names = {source.name for source in self._plan.sources}
        if (set(self._history.validators) != names or {item.source for item in self._bindings.sources} != names
                or {item.name for item in self._context.descriptions} != names
                or {item.source for item in self._context.completions} != names):
            raise ValueError('范围计划、历史、绑定及上下文来源须完全对应')

    def _validate_source(self, source, scan):
        """逐项核真实扫描、当前元数据与绑定，不访问原输入行。

        参数: 原SourcePlan/对应真实scan。返回: 原观测、描述SHA、请求SHA、历史SHA、计数。
        异常: 生命周期、对象身份、指纹、投影、计数或EOF矛盾。
        """
        if scan.closed or scan.failed or not scan.finished:
            raise ResultClosedError('观测扫描已关闭、失败或尚未真实完成')
        validator = self._history.validators[source.name]
        request, description = validator.request, validator.description
        if scan.history is not self._history or scan.source_plan is not source or scan.request is not request:
            raise ValueError('范围扫描必须保同一history、原SourcePlan和实际原request')
        completion = self._history.source_completions[source.name]
        proof = next(item for item in self._bindings.sources if item.source == source.name)
        context_description = next(item for item in self._context.descriptions if item.name == source.name)
        context_completion = next(item for item in self._context.completions if item.source == source.name)
        description_sha, request_sha = _fingerprint(description), _fingerprint(request)
        digest, counts = scan.history_sha256, scan.counts
        observation = scan.observation
        if (type(observation) is not SourceScanObservation or observation.source != source.name
                or observation.session_id != self._context.session_id or observation.source_eof is not True
                or context_description != description or context_completion != completion
                or proof.description_sha256 != description_sha or proof.request_sha256 != request_sha
                or proof.history_sha256 != digest or digest != self._history.hashes[source.name].hexdigest()
                or counts != tuple(self._history.counts[source.name])
                or counts != (proof.progress_count, proof.sample_count)
                or proof.projected_aliases != request.signal_names or proof.session_id != request.session_id
                or request.session_id != self._context.session_id
                or (request.domain_start_ns, request.domain_end_ns)
                    != (self._context.domain.start_ns, self._context.domain.end_ns)
                or proof.observation_start_ns != description.observation_start_ns
                or proof.observation_end_ns != completion.observed_end_ns
                or not proof.source_eof or not completion.source_eof
                or observation.observed_start_ns != (description.observation_start_ns
                    if description.observation_start_ns is not None else observation.first_ns)
                or observation.observed_end_ns != completion.observed_end_ns):
            raise ValueError('范围扫描、实际描述/请求/历史SHA/计数/投影/EOF事实不一致')
        return observation, description_sha, request_sha, digest, counts

    def _verify_source(self, source, digest, counts):
        """用一个真实reader核当前文件完整EOF，拒绝提前close冒充耗尽。

        参数: source原名/digest真实扫描摘要/counts原进度与样本计数。
        返回: None。异常: 原读取、预算、损坏或关闭错误，reader责任保持可恢复。
        """
        self._reader = self._history.iter_records(source)
        progress_count = sample_count = 0
        final_progress = None
        for record in self._reader:
            if isinstance(record, HistoryProgress):
                progress_count += 1
                final_progress = record
            elif isinstance(record, HistorySample):
                sample_count += 1
        # 最后一条是小型最终progress，由固定证明槽覆盖；不保留任何大样本值引用。
        record = None
        if (not self._reader.verified_eof or self._reader.digest.hexdigest() != digest
                or (progress_count, sample_count) != counts
                or final_progress != self._history.source_completions[source]):
            raise ResultFormatError('观测范围未完成当前实际历史EOF、摘要或计数核对')
        self._reader.close()
        self._reader = None

    def _build_scopes(self):
        """按原计划来源序建立全部组及domain内交集。参数: 无。返回: None。异常: 原范围模型错误。"""
        members = {self._dataset_key: []}
        endpoints = {}
        for source in self._plan.sources:
            proof = self._proofs[source.name]
            members.setdefault(proof.clock_key, []).append(source.name)
            observation = proof.observation
            # 没有原时间行就没有观测，即使memory description声明了范围也不能制造假点。
            if observation.row_count == 0:
                continue
            start, end = observation.observed_start_ns, observation.observed_end_ns
            if start is None or end is None:
                raise ValueError('非空原时间行缺少已核实的观测首末端')
            previous = endpoints.get(proof.clock_key)
            endpoints[proof.clock_key] = (start, end) if previous is None else (min(start, previous[0]), max(end, previous[1]))
        self._scope_by_key = {}
        domain = self._context.domain
        for key, sources in members.items():
            pair, actual = endpoints.get(key), None
            if pair is not None:
                left, right = max(domain.start_ns, pair[0]), min(domain.end_ns, pair[1])
                # 相等是真实接触点；只有left>right或无原行才是明确None。
                if left <= right:
                    actual = Interval(left, right)
            self._scope_by_key[key] = ObservationScope(key, tuple(sources),
                None if pair is None else pair[0], None if pair is None else pair[1], actual)
        self._scope_by_source = {name: scope for scope in self._scope_by_key.values() for name in scope.sources}

    def _adopt_cleanup(self, exc):
        """接管实际未返回的历史reader。参数: 原异常。返回: None。异常: 无预期异常。"""
        reader = getattr(exc, 'history_iterator_cleanup_owner', None)
        if self._reader is None and reader is not None:
            self._reader = reader

    @property
    def closed(self):
        """读取自有关闭状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    def assert_current(self, history, context, bindings, plan):
        """核调用方仍使用原四对象、活扫描和同一当前历史元数据。

        参数: 原history/context/bindings/plan。返回: None；不重复读取历史字节。
        异常: ResultClosedError为本层/扫描/历史失效，ValueError为对象或证明已改变。
        """
        if self._closed or self._closing or self._failed:
            raise ResultClosedError('历史观测范围已关闭、正在清理或构造失败')
        if (history is not self._history or context is not self._context
                or bindings is not self._bindings or plan is not self._plan):
            raise ValueError('观测范围必须与调用方原history/context/bindings/plan共同使用')
        self._require_contract()
        for source in plan.sources:
            values = self._validate_source(source, self._scan_by_source[source.name])
            proof = self._proofs[source.name]
            if values != (proof.observation, proof.description_sha256, proof.request_sha256,
                          proof.history_sha256, proof.counts):
                raise ValueError('观测范围所借扫描或当前历史证明已改变')

    @property
    def identity(self):
        """借读包含实际原行/分组的稳定摘要。参数: 无。返回: str。异常: 当前证明或活性失效。"""
        self.assert_current(self._history, self._context, self._bindings, self._plan)
        return self._identity

    @property
    def source_observations(self):
        """按原计划序借读有限分源事实副本。参数: 无。返回: tuple。异常: 当前证明或活性失效。"""
        self.assert_current(self._history, self._context, self._bindings, self._plan)
        return self._source_observations

    @property
    def dataset_scope(self):
        """借读无依赖的dataset时钟组。参数: 无。返回: ObservationScope。异常: 证明或活性失效。"""
        return self.for_dependencies(())

    def for_dependencies(self, names):
        """按展开后的原信号依赖借读预建范围，保留原同步及实际投影门槛。

        参数: names为原别名tuple，空tuple使用dataset组；派生依赖应由编译器展开。
        返回: 借用到本owner关闭的ObservationScope，同组依赖返回同一预建对象。
        异常: 原未知/未投影/同步错误；跨不可比较组或本层/扫描活性失效。
        """
        self.assert_current(self._history, self._context, self._bindings, self._plan)
        self._bindings.require_synchronized(names)
        if not names:
            return self._scope_by_key[self._dataset_key]
        selected = None
        for name in names:
            scope = self._scope_by_source[self._bindings.resolve(name).source]
            if selected is not None and scope.clock_key != selected.clock_key:
                raise ValueError('联合依赖不属于同一可比时钟组')
            selected = scope
        return selected

    def for_source(self, name):
        """借读实际来源所属的已核时钟组，空信号投影也必须有同次来源证明。

        参数: name为本次原来源安全名。返回: 借用ObservationScope，范围为所属组联合，
            不是该来源独占的观测首末。异常: 原证明失效或ValueError为未知/非文本来源。
        """
        # source_observations仅含原行事实，不暴露时钟键；此入口复用已经建立的组映射。
        self.assert_current(self._history, self._context, self._bindings, self._plan)
        if type(name) is not str or name not in self._scope_by_source:
            raise ValueError('未知观测来源或来源名称类型错误')
        return self._scope_by_source[name]

    def close(self):
        """可重试关闭自有reader与有限副本，不关闭任何原扫描/history/lease。

        参数: 无。返回: None，成功后幂等。异常: 原reader或预算取消，未完责任保留。
        """
        if self._closed:
            return
        self._closing = True
        if self._reader is not None:
            self._reader.close()
            self._reader = None
        # 先丢自有副本及借用引用，再抵销覆盖它们的固定槽；失败重试只处理真实剩余责任。
        self._scan_by_source = self._proofs = self._scope_by_key = self._scope_by_source = None
        self._source_observations = self._dataset_key = self._identity = None
        self._source_scans = ()
        self._history = self._context = self._bindings = self._plan = None
        _release_owned_ram(self, self._fixed_cost, '_fixed_cost')
        if self._held_cost == 0:
            self._closed = True
