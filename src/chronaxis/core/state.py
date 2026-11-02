"""检查内存样本的原行身份，并按有限有效期查询最新观测或提交同刻更新。

输入为当前SignalBindings下的规范样本和纳秒查询轴；输出SignalSeries、
StateValue或完整TimeGroup。先检查身份、声明类型及同时间冲突，再取最新更新，
结合有效期和来源、会话范围判断能否使用。无效更新同样覆盖历史，不能回退
取更早有效值。同刻多列更新先收齐，再交给调用者求值一次。
本模块只依赖标准库，没有文件操作或全局状态；不执行单位转换或表达式计算。
NumPy保持实现位于state_numpy，数值对齐算法独立。
"""

# 冻结结构承载已检查输入；heap只归并内存样本，不调整旧文件读取顺序。
from dataclasses import dataclass, field
# 合并已排序来源，不排序或重排原始输入。
from heapq import merge
# 无效NaN同时间证据需明确判断，不能普通相等比较。
from math import isnan

# 两后端可共享模型校验/提交协议，参考查询不调用NumPy对齐。
from .binding import SignalBindings
# 来源与规范样本定位保存原行身份。
from .models import SignalSample, SourceSpec
# 有效性/类型策略不由原值truthiness决定。
from .types import QualityFlag, SignalDType
# 精确整数时间先校验再运算，不允许wrap。
from ..timebase.conversion import checked_add_ns, require_int64_ns


def _collapse(bindings: SignalBindings, samples: tuple[SignalSample, ...]) -> tuple[SignalSample, int]:
    """解析同一别名同时间候选，保留稳定原序号及冲突数量。

    参数: bindings为当前冻结引用；samples为非空、同名同时间typed候选。
    返回: 选定SignalSample及不同事实被显式覆盖的候选数。
    异常: ValueError为默认error下不同事实冲突；不静默按遍历顺序选值。
    """
    # 每候选序号是来源内稳定身份，最大序号与遍历顺序无关。
    chosen = max(samples, key=lambda sample: sample.sequence)
    # 基线取首条仅用于判断是否一致，不作为冲突时默认结果。
    first = samples[0]
    # 无效NaN诊断可以与相同原因的NaN一致，不使用其普通比较结果。
    same = all(item.valid == first.valid and item.quality == first.quality and
               type(item.value) is type(first.value) and
               (item.value == first.value or (type(item.value) is float and isnan(item.value) and isnan(first.value)))
               for item in samples)
    # 不同值/质量/有效性属于真实同信号冲突。
    if not same and bindings.resolve(first.name).same_time_policy == "error":
        # 未配置last_by_sequence时不能依赖输入遍历顺序。
        raise ValueError(f"同信号同时间冲突：{first.name}@{first.time_ns}ns")
    # 明确选最后稳定序号，记录被处理的不同候选数量。
    return chosen, 0 if same else len(samples) - 1


@dataclass(frozen=True)
class SignalSeries:
    """保存一个信号别名的规范内存观测，以及来源范围和同刻冲突计数。

    样本先按原顺序检查时间非递减，再按声明策略处理同刻候选，构造结果时间
    严格递增。有效值符合声明类型，无效原值保留作诊断。未声明的来源端点取
    实际首末行，不补采样周期。序列使用当前冻结绑定，没有全局执行缓存；
    原行转换由数值层提供。
    """

    bindings: SignalBindings  # 当前计划与会话引用。
    name: str  # 当前原信号别名。
    samples: tuple[SignalSample, ...]  # 已规范化typed样本，包含无效更新。
    source: SourceSpec = field(init=False)  # 校验所得实际来源。
    observation_start_ns: int = field(init=False)  # 分析坐标来源首端。
    observation_end_ns: int = field(init=False)  # 分析坐标来源末端。
    conflict_count: int = field(init=False)  # last_by_sequence显式覆盖数量。

    def __post_init__(self) -> None:
        """校验样本原身份、dtype、顺序，规范同时间候选并冻结来源域。

        参数: 无；bindings/name为真实引用，samples为tuple规范化观测。
        返回: None；只在构造时规范同时间组，不丢失无效状态。
        异常: TypeError为结构/dtype；ValueError为归属/原序号/顺序/冲突；
            时间溢出异常由既有时间协议传播。
        """
        # 只接受当前真实绑定和冻结样本容器。
        if not isinstance(self.bindings, SignalBindings) or not isinstance(self.samples, tuple):
            # 不接可变列表或未校验字典。
            raise TypeError("SignalSeries需要SignalBindings和tuple samples")
        # 别名先在当前计划解析，不能继承其他会话。
        definition = self.bindings.resolve(self.name)
        # 实际来源已经由绑定证明唯一。
        source = next(item for item in self.bindings.session.sources if item.name == definition.source)
        # 原行序号到字段/时间，用于证明规范化观测对应实际原行。
        rows = {row.sequence: row for row in source.rows}
        # 枚举逻辑域按第一次出现稳定去重，编码映射原样保留在定义。
        labels = tuple(dict.fromkeys(label for _, label in definition.choices)) if definition.dtype is SignalDType.ENUM else ()
        # 局部稳定身份和待提交时间组，不跨会话共享。
        seen, groups, pending = set(), [], []
        # 冲突计数只记录显式政策处理的不同事实。
        conflicts = 0
        # 输入顺序不自动修补，逐项检查后才规范同时间。
        for sample in self.samples:
            # typed样本已校验质量矛盾，当前入口仍拒绝占位对象。
            if not isinstance(sample, SignalSample):
                # 不把自由dict当作可计算观测。
                raise TypeError("samples必须包含SignalSample")
            # 会话/来源/字段范围必须属于当前冻结输入。
            self.bindings.session.validate_sample(sample)
            # 同别名的来源引用完整匹配，不能用另一字段冒充。
            if sample.name != self.name or sample.source_ref != self.bindings.source_ref(self.name):
                # 原引用冲突不是普通缺失值。
                raise ValueError("样本别名/来源与当前序列不一致")
            # 声明dtype只检查有效值，无效占位保留原诊断。
            sample.validate_dtype(definition.dtype, labels)
            # 同来源原序号必须真实且不能重复消费。
            if sample.sequence not in rows or sample.sequence in seen:
                # 不重编号或生成不存在的行。
                raise ValueError("样本原序号不存在或重复")
            # 定位实际行，再证明偏移映射与字段暴露事实。
            row = rows[sample.sequence]
            # 单个样本只能关联真正含该原字段的行。
            if definition.field not in row.values or sample.time_ns != checked_add_ns(row.time_ns, source.offset_ns):
                # 已归一化值可变化，但原时间/字段身份不能伪造。
                raise ValueError("样本不能定位对应原行时间/字段")
            # 来源序号只在当前序列登记，另一别名可引用同一原行。
            seen.add(sample.sequence)
            # 时间回退不排序以掩盖上游错误。
            if pending and sample.time_ns < pending[-1].time_ns:
                # 不提交回退之后的计算结果。
                raise ValueError("序列时间必须非递减")
            # 更大时间才证明上一时间组收齐。
            if pending and sample.time_ns != pending[-1].time_ns:
                # 公共校验协议处理同信号同时间冲突。
                selected, count = _collapse(self.bindings, tuple(pending))
                # 规范结果保留实际原样本，不伪造值。
                groups.append(selected)
                # 显式政策处理数量可追溯。
                conflicts += count
                # 仅结束上一组，不重置来源或会话状态。
                pending = []
            # 当前真实更新进入待规范组，无效样本同样保留。
            pending.append(sample)
        # 完整内存输入结束可以提交最后一组。
        if pending:
            # 该收尾是全序列结束，不是batch EOF。
            selected, count = _collapse(self.bindings, tuple(pending))
            # 末点仍保存为真实观测。
            groups.append(selected)
            # 最后一组冲突同样记录。
            conflicts += count
        # 未声明范围时只取实际来源首行/末行，绑定已保证来源非空。
        start = source.rows[0].time_ns if source.observation_start_ns is None else source.observation_start_ns
        # 实际末行不得加假设周期。
        end = source.rows[-1].time_ns if source.observation_end_ns is None else source.observation_end_ns
        # 构造冻结规范样本，不保留可变临时分组列表。
        object.__setattr__(self, "samples", tuple(groups))
        # 保存真实来源引用，后续两个对齐器共享该校验事实。
        object.__setattr__(self, "source", source)
        # 来源原坐标显式映射到分析时间。
        object.__setattr__(self, "observation_start_ns", checked_add_ns(start, source.offset_ns))
        # 点/连续对末端的使用由对齐入口明确指定。
        object.__setattr__(self, "observation_end_ns", checked_add_ns(end, source.offset_ns))
        # 结果数量只描述显式冲突政策，不称为旧帧去重。
        object.__setattr__(self, "conflict_count", conflicts)


@dataclass(frozen=True)
class StateValue:
    """保存某个查询时刻的最新观测、可用性和质量原因。

    sample用于追溯原时间、序号和来源；最新更新无效时保留它，不回退旧值。
    没有历史时value为None。actual_update只表示查询点恰好有真实样本更新，
    有效期到期或观测结束不能伪造更新。point模式可以包含真实末点，连续模式
    排除末端，两者均在有效期右端失效。结果不会修改原样本。
    """

    time_ns: int  # 本次查询的分析纳秒坐标。
    value: int | float | bool | str | None  # 最新观测或没有历史时None。
    valid: bool  # 质量/TTL/观测范围均满足才可使用。
    quality: QualityFlag  # 保留输入原因并叠加缺失/过期。
    sample: SignalSample | None  # 最新实际观测；不回退旧有效值。
    actual_update: bool  # 该点是否真正发生更新。


def align_reference(series: SignalSeries, times_ns: tuple[int, ...], *, point: bool = False, strict_before: bool = False) -> tuple[StateValue, ...]:
    """逐查询点取得最新历史观测，再检查有效期和来源、会话范围。

    参数:
        series (SignalSeries): 当前绑定下已经检查的规范序列。
        times_ns (tuple[int, ...]): 非递减int64纳秒查询轴，允许空轴和重复点。
        point (bool): 默认False，使用左闭右开连续范围；True包含来源及会话
            的真实末端，但有效期右端始终排除。
        strict_before (bool): 默认False；True只取sample_time < t的样本，
            仍在当前t检查有效期，用来区分实际更新与同刻到期。
    返回:
        tuple[StateValue, ...]: 每个查询点一个结果；无历史为MISSING，过期为STALE。
        最新无效更新不会被更早有效值替代，空轴返回空tuple。
    异常:
        TypeError: 序列、查询容器或模式标志类型错误，或者时间不是非布尔整数。
        ValueError: 查询时间回退。
        TimeOverflowError: 查询坐标超出int64范围。
    副作用:
        仅使用局部游标和结果集合，不调用NumPy对齐，不修改输入。
    """
    # 不接受未校验序列或可变查询容器。
    if not isinstance(series, SignalSeries) or not isinstance(times_ns, tuple) or type(point) is not bool or type(strict_before) is not bool:
        # point不能以数值truthiness切换契约。
        raise TypeError("参考对齐需要SignalSeries、tuple时间及bool point")
    # 只用精确Python整数，参考不调用NumPy索引/掩码内核。
    times = tuple(require_int64_ns(time, "query.time_ns") for time in times_ns)
    # 保证时间推进不回退，重复查询点允许。
    if any(right < left for left, right in zip(times, times[1:])):
        # 不排序查询掩盖执行器错误。
        raise ValueError("查询时间必须非递减")
    # 每次查询调用只有局部游标，不继承其他会话状态。
    cursor, result = -1, []
    # 当前会话范围明确，不延长来源保持。
    session = series.bindings.session
    # 有效期纳秒来自当前冻结定义，不根据消息周期推测。
    age = series.bindings.resolve(series.name).valid_for_ns
    # 小规模参考按时间逐点计算，数值/对齐独立于数组后端。
    for time in times:
        # 最新更新包含无效观测，不能只搜索有效值。
        while cursor + 1 < len(series.samples) and (series.samples[cursor + 1].time_ns < time if strict_before else series.samples[cursor + 1].time_ns <= time):
            # 精确取不晚于当前时刻的最新样本。
            cursor += 1
        # 连续域末端排除；point显式包含真实终点。
        in_domain = session.domain_start_ns <= time and (time <= session.domain_end_ns if point else time < session.domain_end_ns)
        # 会话外或无历史没有可用观测，不能取末元素。
        if not in_domain or cursor < 0:
            # 没有可用历史时保留None和MISSING原因，不用数值0代替未知结果。
            result.append(StateValue(time, None, False, QualityFlag.MISSING, None, False))
            # 当前点没有样本参与TTL或边沿。
            continue
        # 即使最新更新无效也取它，不回退到更早有效观测。
        sample = series.samples[cursor]
        # 质量在局部结果叠加，原样本原因保持不变。
        quality = sample.quality
        # TTL始终右端排除，Python整数差避免绝对时间浮点损失。
        if time - sample.time_ns >= age:
            # 自动计时失效无需等待新报文。
            quality |= QualityFlag.STALE
        # 来源末端与会话一样按point/连续显式区分。
        in_source = series.observation_start_ns <= time and (time <= series.observation_end_ns if point else time < series.observation_end_ns)
        # 更长的其他来源不能延长当前来源保持。
        if not in_source:
            # 来源观测不足与输入无效/TTL原因一起保留。
            quality |= QualityFlag.MISSING
        # 所有非零质量基础策略禁止使用，正常0仍然有效。
        valid = sample.valid and quality == QualityFlag.NONE
        # 只有真正实际更新可触发后续点事件。
        result.append(StateValue(time, sample.value, valid, quality, sample, time == sample.time_ns))
    # 冻结结果容器，不暴露局部列表。
    return tuple(result)


def _require_series_group(series: tuple[SignalSeries, ...]) -> SignalBindings:
    """检查局部依赖结构、同绑定和同步，不分配完整时间轴。

    参数: series为同一冻结绑定下非空tuple SignalSeries。
    返回: 当前SignalBindings；空间只与局部依赖列数有关。
    异常: TypeError为结构；ValueError为不同绑定或同步缺项。
    """
    # 只处理显式局部依赖，不建立全信号宽表。
    if not isinstance(series, tuple) or not series or not all(isinstance(item, SignalSeries) for item in series):
        # 空依赖需要由调用者明确给出纯常量轴，本入口不猜会话。
        raise TypeError("共同轴需要非空tuple SignalSeries")
    # 同一绑定身份才能形成联合任务轴。
    binding = series[0].bindings
    # 来源输入变化不能只因同别名而共用时间轴。
    if any(item.bindings.identity != binding.identity for item in series):
        # 不把不同会话串接计算。
        raise ValueError("共同轴序列必须来自同一绑定")
    # 参与联合计算的原信号必须通过公共时基检查。
    binding.require_synchronized(tuple(item.name for item in series))
    # 仅返回校验后的绑定，不遍历全历史生成索引或轴。
    return binding


def common_timeline(series: tuple[SignalSeries, ...], extra_ns: tuple[int, ...] = ()) -> tuple[int, ...]:
    """构造当前依赖的更新、TTL及来源/会话边界共同轴。

    参数: series为同一绑定下所需序列tuple；extra_ns为后续规则deadline/window边界。
    返回: 排序唯一tuple int64纳秒，限制在会话闭域以保留末点上下文。
    异常: TypeError/ValueError为结构或不同绑定；时间错误传播。
    副作用: 显式分配当前依赖共同轴，归并入口不调用本生成操作。
    """
    # 校验协议与完整轴构造分开，局部归并不额外分配全历史轴。
    binding = _require_series_group(series)
    # 不接无限或可变边界容器。
    if not isinstance(extra_ns, tuple):
        # 调用侧显式提供后续规则边界。
        raise TypeError("extra_ns必须为tuple")
    # 会话闭域只保留真实终点，不增加连续持续时间。
    start, end = binding.session.domain_start_ns, binding.session.domain_end_ns
    # 当前任务必要端点都保留，纯EOF不是实际更新。
    axis = {start, end}
    # 显式规则边界使用同一精确时间校验。
    axis.update(require_int64_ns(time, "extra_ns") for time in extra_ns)
    # 每信号的保持边界进入轴，不等新更新才失效。
    for item in series:
        # 来源起止是局部覆盖事实，不能借其他列延长。
        axis.update((item.observation_start_ns, item.observation_end_ns))
        # 有效期从明示定义读取。
        age = binding.resolve(item.name).valid_for_ns
        # 更新和TTL用精确整数计算，不先转绝对float秒。
        for sample in item.samples:
            # 真实更新时刻用于原子提交及点事件。
            axis.add(sample.time_ns)
            # 超出会话的TTL不进入int64轴，先在Python整数域裁剪。
            expiry = sample.time_ns + age
            # 只保存会话内可发生的deadline。
            if start <= expiry <= end:
                # 包含与EOF并列的TTL，后续状态机可保留并列诊断。
                axis.add(expiry)
    # 排序仅作用于新核心共同轴，不排序修补来源输入。
    return tuple(sorted(time for time in axis if start <= time <= end))


@dataclass(frozen=True)
class TimeGroup:
    """保存一个分析时刻所有信号真实更新，供求值一次使用。

    不在逐条样本之间求值；updates按冻结定义顺序排列，保持原样本身份。
    """

    time_ns: int  # 该组公共分析坐标。
    updates: tuple[SignalSample, ...]  # 各信号最多一项，冲突已处理。
    conflict_count: int = 0  # 本组显式last_by_sequence处理数量。


class AtomicUpdateBuffer:
    """跨批收集同时间的信号更新，收齐后输出一次完整求值组。

    看到更大时间或完整输入finish后才提交当前组，普通批末保留_pending。
    输入须已经按时间归并并完成归一化；本类不读取来源或排序。finish后实例
    关闭，新会话须创建新实例。缓冲大小取决于同刻更新数量；生产预算由上层
    执行入口约束，不能只凭分批就认为整体内存有界。
    """

    def __init__(self, bindings: SignalBindings):
        """创建当前会话的空原子提交缓冲。

        参数: bindings为当前真实冻结引用。
        返回: None；pending空，closed=False，无全局状态。
        异常: TypeError为非绑定输入。
        """
        # 缓冲不能关联无类型计划。
        if not isinstance(bindings, SignalBindings):
            # 不从上一个任务继承会话。
            raise TypeError("buffer需要SignalBindings")
        # 当前绑定不会随运行中值更新改变。
        self.bindings = bindings
        # 只缓存当前未证明收齐的同时间组。
        self._pending = []
        # 真正会话完成后禁止继续输入。
        self._closed = False
        # 已见时间用于拒绝跨batch回退。
        self._last_time = None

    def _commit(self) -> TimeGroup:
        """将已收齐的pending原子规范为一次求值组。

        参数: 无；pending须非空且同时间。
        返回: TimeGroup，信号按定义顺序，显式冲突有计数。
        异常: ValueError为默认冲突；只修改当前pending。
        """
        # 当前组各别名候选先收齐再决策，不在采集过程中求值。
        grouped = {}
        # 原观测顺序仅用于采集，冲突选择依稳定sequence。
        for sample in self._pending:
            # 不同别名更新各自收集。
            grouped.setdefault(sample.name, []).append(sample)
        # 求值组顺序由当前计划定义决定，不受批次切法影响。
        updates, conflicts = [], 0
        # 只处理本时刻确有更新的别名。
        for definition in self.bindings.signals:
            # 未更新列继续保持，不能伪造当前新样本。
            if definition.name in grouped:
                # 统一已定义冲突政策，不改变数值对齐内核独立性。
                sample, count = _collapse(self.bindings, tuple(grouped[definition.name]))
                # 一列最多一项原子更新。
                updates.append(sample)
                # 记录显式覆盖的候选数。
                conflicts += count
        # 所有原候选都处于同一个时间。
        time = self._pending[0].time_ns
        # 只在组实际完成后清空pending，不销毁会话绑定。
        self._pending = []
        # 冻结本组供后续状态驱动器求值一次。
        return TimeGroup(time, tuple(updates), conflicts)

    def push(self, samples: tuple[SignalSample, ...]) -> tuple[TimeGroup, ...]:
        """消费一批已归并更新，返回已经收齐的更早时间组。

        参数: samples为非递减tuple样本，可为空，batch尾可处于未完成同时间组。
        返回: tuple TimeGroup；最后时间仍留pending，不能在batch尾提前求值。
        异常: TypeError为结构；ValueError为已finish、归属/回退/冲突。
        """
        # 整个会话EOF才关闭，不把普通批次当成会话结束。
        if self._closed:
            # 不能在新会话复用旧执行状态。
            raise ValueError("buffer已finish，需新会话实例")
        # 可变或无限批次容器不进入已定义内存协议。
        if not isinstance(samples, tuple):
            # 当前入口显式有界批次。
            raise TypeError("samples batch必须为tuple")
        # 完成组结果只属于当前调用。
        result = []
        # 每条样本先校验当前归属，再推进原子组。
        for sample in samples:
            # 完整样本类型/会话检查，不允许旧引用污染新任务。
            self.bindings.session.validate_sample(sample)
            # 当前别名必须实际绑定到同来源字段。
            if sample.source_ref != self.bindings.source_ref(sample.name):
                # 绑定冲突不能被吞为无效数值。
                raise ValueError("buffer样本绑定不匹配")
            # 已规范化有效值仍须与当前声明dtype和域一致。
            definition = self.bindings.resolve(sample.name)
            # enum目标逻辑域与编码映射分开，重复标签只保留一个。
            labels = tuple(dict.fromkeys(label for _, label in definition.choices)) if definition.dtype is SignalDType.ENUM else ()
            # 无效更新允许保留原诊断占位，不参与正常数值校验。
            sample.validate_dtype(definition.dtype, labels)
            # 同组同别名不能重复消费同一稳定原样本。
            if any(item.name == sample.name and item.sequence == sample.sequence for item in self._pending):
                # 不把重复输入吞成一次正常更新。
                raise ValueError("buffer同组原序号重复")
            # 跨batch同样禁止时间回退。
            if self._last_time is not None and sample.time_ns < self._last_time:
                # 不重排上游样本。
                raise ValueError("buffer时间回退")
            # 更大时间证明上一组已收齐。
            if self._pending and sample.time_ns > self._last_time:
                # 一组的所有列先提交，调用侧随后求值一次。
                result.append(self._commit())
            # 当前样本纳入未完成组，无效更新也要覆盖旧状态。
            self._pending.append(sample)
            # 记录最新输入时间，普通batch边界保留。
            self._last_time = sample.time_ns
        # 冻结结果，最后pending保留到下一批或真正finish。
        return tuple(result)

    def finish(self) -> tuple[TimeGroup, ...]:
        """在完整输入EOF提交最后时间组并关闭当前会话缓冲。

        参数: 无；调用者已证明所有参与来源输入结束。
        返回: 剩余一个TimeGroup或空tuple。
        异常: ValueError为重复finish或未处理冲突；batch尾不能调用本方法。
        """
        # 不接受重复收尾，否则可能重复积分或事件。
        if self._closed:
            # 新任务必须创建独立状态对象。
            raise ValueError("buffer不能重复finish")
        # 真EOF才允许提交最终同时间组。
        result = (self._commit(),) if self._pending else ()
        # 当前会话输入不可继续复用。
        self._closed = True
        # 空输入合法，不伪造末点更新。
        return result


def iter_time_groups(series: tuple[SignalSeries, ...], batch_rows: int = 65536):
    """对当前局部memory序列有界归并并跨batch原子提交。

    参数: series为同绑定、不同别名的规范序列tuple；batch_rows为正原生整数。
    返回: 逐个yield TimeGroup；完整内存输入结束后才提交最后组。
    异常: TypeError/ValueError为结构/不同绑定/重复列/批次参数或冲突。
    副作用: 只维护局部heap/一批/pending，不读取旧日志或改样本顺序。
    """
    # 纯依赖校验不生成完整共同轴，不调用任何数值对齐内核。
    _require_series_group(series)
    # 同别名的两个序列不能当成不同输入列重复消费。
    if len({item.name for item in series}) != len(series):
        # 不自动选择某一输入序列。
        raise ValueError("归并序列别名重复")
    # bool不能伪装成批次行数1。
    if type(batch_rows) is not int or batch_rows <= 0:
        # 不接受无界或无效批次参数。
        raise ValueError("batch_rows必须为正原生整数")
    # 缓冲只属于本次输入，不在批次之间重建。
    buffer = AtomicUpdateBuffer(series[0].bindings)
    # heap归并每列已经排序的规范样本，不排序修补任何来源。
    stream = merge(*(item.samples for item in series), key=lambda sample: sample.time_ns)
    # 当前局部批次最多batch_rows条，组可跨边界。
    batch = []
    # 依来源真实更新时间逐项收集。
    for sample in stream:
        # 当前样本保留原稳定身份。
        batch.append(sample)
        # 达到批次预算才将批交给同一个状态缓冲。
        if len(batch) == batch_rows:
            # 已证明收齐的时间组可逐个消费。
            yield from buffer.push(tuple(batch))
            # 普通批次完成只清批，不清pending或会话状态。
            batch = []
    # 完整输入最后不满批同样进入状态缓冲。
    if batch:
        # 同时刻更新可与上一批pending合并。
        yield from buffer.push(tuple(batch))
    # 所有memory来源结束后才执行最后组收尾。
    yield from buffer.finish()
