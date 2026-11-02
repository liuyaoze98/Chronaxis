"""保存条件在各时刻的证据、检测规则及已确认事件，供两个检测后端共用。

输入为整数纳秒区间、条件状态、实际更新与观测结束证据；输出不可变且经过
检查的模型。TRUE和FALSE必须没有结果质量原因，UNKNOWN必须保留原因。
连续区间左闭右开；真实末点可单独观察，但不延长活动。来源或会话输入结束
不自动等于条件变假。事件以稳定内容生成标识，并保存SourceRef用于追溯。
本模块只依赖标准库及核心模型，不读取来源、不执行检测、不持有规则状态。
"""

# 冻结模型与默认字段便于保留显式证据。
from dataclasses import dataclass
# 稳定内容身份，不用秒数文件名充当事件ID。
from hashlib import sha256
# 已有规范身份与来源定位结构，不读旧资源。
from .binding import _identity
# 区间模型已检查跨度和来源引用结构。
from .models import Interval, SourceRef
# 三值状态不得隐式bool化。
from .types import QualityFlag as Q, Truth
# 数据标识规则复用，无静默改名。
from .validation import require_identifier, require_text
# 所有时间仍为显式int64纳秒。
from ..timebase.conversion import require_int64_ns


def _require_truth(state, quality):
    """检查已知结果无质量原因与UNKNOWN有原因的基础契约。

    参数: state为Truth，quality为已知Q组合。
    返回: None，不把UNKNOWN变False。
    异常: TypeError/ValueError为类型或质量矛盾。
    """
    # 已知结果不能携带基础策略禁止的质量位。
    if not isinstance(state, Truth) or not isinstance(quality, Q):
        # 裸bool或任意质量数值不能替代经过检查的条件证据。
        raise TypeError('条件需要Truth及QualityFlag')
    # unknown原因不能空，正常真/假质量只能NONE。
    if (state is Truth.UNKNOWN) != (quality != Q.NONE):
        # 诊断与结果质量通过独立字段保留。
        raise ValueError('条件truth与quality矛盾')


@dataclass(frozen=True)
class ConditionSpan:
    """保存条件连续成立、不成立或无法确定的一段纳秒区间。

    start_ns包含起点，end_ns排除终点；区间必须为正长度且跨度可由int64表示。
    state和quality共同说明条件及未知原因。模型不可变，不根据消息周期补齐间隙。
    """

    start_ns: int  # 连续区间包含起点。
    end_ns: int  # 连续区间不包含终点。
    state: Truth  # 真/假/未知，不靠数值truthiness。
    quality: Q = Q.NONE  # UNKNOWN原因，known为NONE。

    def __post_init__(self):
        """检查正区间与truth质量，禁止补齐缺观测。

        参数: 无；读取四个字段。
        返回: None，保持原声明。
        异常: TypeError/ValueError/OverflowError为结构/区间/质量。
        """
        # 复用已有半开时间区间不变量。
        interval = Interval(self.start_ns, self.end_ns)
        # 零长度不是连续条件区间。
        if interval.end_ns == interval.start_ns:
            # 真实点由ConditionTick.point_state另表达。
            raise ValueError('ConditionSpan需正长度')
        # 区间状态和原因严格一致。
        _require_truth(self.state, self.quality)


@dataclass(frozen=True)
class ConditionTick:
    """保存一个完整时间组的连续状态、点状态及实际更新证据。

    state描述从当前时刻到下一时刻的连续状态；point_state描述当前点，包括真实
    末点。actual_unknown表示真实更新明确导致点结果未知，用于区分实际中断与
    同刻发生的有效期到期。observation_end和terminal分别表示依赖来源及会话
    观测结束。字段不可变，默认点状态继承连续状态，不制造实际更新。
    """

    time_ns: int  # 已归一化int64纳秒。
    state: Truth  # 连续右侧状态，不扩展终点。
    quality: Q = Q.NONE  # 连续unknown原因。
    actual_update: bool = True  # 完整组确有条件依赖更新/明确条件证据。
    observation_end: bool = False  # 当前有依赖来源观测结束。
    terminal: bool = False  # 当前会话真实连续终点，只能全输入末组。
    point_state: Truth | None = None  # None表示与continuous同证据。
    point_quality: Q | None = None  # None采用continuous质量。
    actual_unknown: bool = False  # 实际无效/实际更新导致未知，优先interrupted。
    diagnostic_quality: Q = Q.NONE  # 全部依赖和边界原因，保留原异常诊断。

    def __post_init__(self):
        """规范默认点证据并检查actual/terminal/quality结构。

        参数: 无，读取上述字段。
        返回: None，默认point只继承显式state，不制造新更新。
        异常: TypeError/ValueError为类型、状态或实际未知证据冲突。
        """
        # 精确纳秒，bool不作整数时间。
        require_int64_ns(self.time_ns)
        # 连续known/unknown契约独立校验。
        _require_truth(self.state, self.quality)
        # 每个证据标志严格bool。
        for value in (self.actual_update, self.observation_end, self.terminal, self.actual_unknown):
            # 不用任意字符串或整数真值推测证据。
            if type(value) is not bool:
                # 结构错误先于检测。
                raise TypeError('时序证据标志需bool')
        # 未提供point时继承当前明确状态。
        object.__setattr__(self, 'point_state', self.state if self.point_state is None else self.point_state)
        # 未提供point原因时只继承连续原因。
        object.__setattr__(self, 'point_quality', self.quality if self.point_quality is None else self.point_quality)
        # point与continuous质量政策相同，但范围语义不同。
        _require_truth(self.point_state, self.point_quality)
        # 诊断也需已知组合，不得存任意负位。
        if not isinstance(self.diagnostic_quality, Q):
            # 不静默cast非法mask。
            raise TypeError('diagnostic_quality需要QualityFlag')
        # 明确actual_unknown只能针对真正更新的点未知。
        if self.actual_unknown and (not self.actual_update or self.point_state is not Truth.UNKNOWN):
            # 有效期到期或观测结束而没有实际更新证据，不能算作实际中断。
            raise ValueError('actual_unknown需实际更新且点UNKNOWN')


@dataclass(frozen=True)
class TemporalRule:
    """声明一个数据集会话中的持续条件或边沿检测规则。

    rule_type接受condition_duration、rising_edge、falling_edge和start_only。minimum_duration_ns是非负int64阈值，
    边沿规则必须为0；rising_edge/start_only可用emit_initial输出首次已知TRUE初始化点。
    start_only的window_duration_ns必须为正，真实触发后的固定时长内抑制新边沿。
    对象不可变，只保存配置，不初始化检测器状态。
    """

    rule_id: str  # 稳定规则ID，与同名不同会话隔离。
    dataset_id: str  # 事件ID范围，不按秒数命名。
    session_id: str  # 当前分析会话。
    rule_type: str  # condition_duration/rising_edge/falling_edge/start_only实际已实现白名单。
    minimum_duration_ns: int = 0  # condition_duration阈值；edge必须0。
    emit_initial: bool = False  # rising_edge/start_only首次已知TRUE初始化策略。
    window_duration_ns: int = 0  # 仅start_only的固定抑制时长，其他模式必须0。
    duration_comparison: str = '>='  # 持续时长门槛：达到或严格超过；不改变实际起止。

    def __post_init__(self):
        """校验规则范围、非负时间及基础rule_type参数。

        参数: 无，读取规则字段。
        返回: None，不初始化任何全局运行状态。
        异常: TypeError/ValueError/OverflowError为配置错误。
        """
        # 独立命名范围不使用任意路径作为ID。
        for field in ('rule_id', 'dataset_id', 'session_id'):
            # 复用现有简单identifier协议。
            require_identifier(getattr(self, field), field)
        # 阈值精确ns，不猜秒或消息周期。
        require_int64_ns(self.minimum_duration_ns, 'minimum_duration_ns')
        # 严格比较只属于持续规则；其他规则不能携带无效开关。
        if self.duration_comparison not in ('>=', '>') or (self.rule_type != 'condition_duration' and self.duration_comparison != '>='):
            raise ValueError('duration_comparison仅持续条件支持>=或>')
        # 固定窗口和持续确认门槛不同，不能复用一个字段猜旧模式意义。
        object.__setattr__(self, 'window_duration_ns', require_int64_ns(self.window_duration_ns, 'window_duration_ns'))
        # 不负时长/隐式bool策略/未实现kind。
        if self.minimum_duration_ns < 0 or type(self.emit_initial) is not bool or self.rule_type not in ('condition_duration', 'rising_edge', 'falling_edge', 'start_only'):
            # sequence使用独立规则模型，不由本模型承载。
            raise ValueError('非法首版时序规则/阈值/初始化策略')
        # edge不能暗带持续门槛，falling_edge/condition_duration无初始化点参数。
        if self.rule_type != 'condition_duration' and self.minimum_duration_ns != 0 or self.emit_initial and self.rule_type not in ('rising_edge', 'start_only'):
            # 参数不混为旧模式的不同condition_duration。
            raise ValueError('规则参数与kind不匹配')
        # start_only窗口为正；其他kind不能暗带抑制或改变已有事件ID。
        if (self.rule_type == 'start_only' and self.window_duration_ns <= 0) or (self.rule_type != 'start_only' and self.window_duration_ns != 0):
            raise ValueError('window_duration_ns仅且必须用于正时长start_only')

    @property
    def qualifying_duration_ns(self):
        """返回最早满足比较的整数纳秒时长，不改变用户声明的门槛。

        参数: 无。返回: Python整数；严格大于最大int64时可超出int64，表示域内不可达到。
        异常: 无。时间模型精度为1ns，因此>60s的首个可表示时长为60000000001ns；
        这不是把用户阈值粗略提高到60.1秒，固定/DBC模式仍只随实际驱动记录确认。
        """
        return self.minimum_duration_ns + (self.duration_comparison == '>')


@dataclass(frozen=True)
class Event:
    """保存一段已确认活动或一个真实触发点，并关联检测规则和原来源。

    point事件的start_ns等于confirmed_ns，end_ns为None，status为point。
    activity事件为正长度左闭右开区间；confirmed_ns可以恰好等于end_ns。
    活动的closed表示条件已知结束，interrupted表示连续性中断，truncated表示
    观测结束而没有实际结束证据。边界、质量、诊断和来源引用均不可变。
    timeout表示开始/结束规则在结束条件可判断时达到时限，结束质量必须为NONE。
    """

    event_id: str  # 按稳定内容SHA，不依批次/遍历次序。
    rule: TemporalRule  # 完整规则及dataset/session身份。
    event_type: str  # point或activity。
    start_ns: int  # 真实onset或点时间。
    confirmed_ns: int  # 精确门槛时间，不当活动起点。
    end_ns: int | None  # point为None，activity结束边界。
    status: str  # closed/timeout/interrupted/truncated/point；timeout用于开始结束时限。
    trigger_kind: str  # condition_duration/rising_edge/falling_edge/initial。
    quality: Q  # 结束原因质量，不用0恢复失败。
    dependency_quality: Q  # 期间及结束证据的完整诊断。
    source_refs: tuple[SourceRef, ...] = ()  # 真实绑定原来源定位，合成span可空。

    def __post_init__(self):
        """检查事件时间不变量、范围与来源，保留确认=end。

        参数: 无，读取事件字段。
        返回: None，不修改边界或生成片段。
        异常: TypeError/ValueError/OverflowError为事件结构/时间/身份错误。
        """
        # 正常输出须携带真实规则/质量及来源容器。
        if not isinstance(self.rule, TemporalRule) or not isinstance(self.quality, Q) or not isinstance(self.dependency_quality, Q) or not isinstance(self.source_refs, tuple):
            # 不接无类型事件字典作为完成事实。
            raise TypeError('Event字段需typed模型')
        # start/confirmed都是明确ns。
        require_int64_ns(self.start_ns, 'start_ns')
        # 确认不能先于真实onset。
        require_int64_ns(self.confirmed_ns, 'confirmed_ns')
        # ID需真实非空文本，稳定SHA由make_event产生。
        require_text(self.event_id, 'event_id')
        # 缺数据不能伪装已证实的超时；依赖诊断仍可保留不影响结束判断的原因。
        if self.status == 'timeout' and self.quality != Q.NONE:
            raise ValueError('timeout不能带未知结束质量')
        # 点事件只有单时刻，无连续范围。
        if self.event_type == 'point':
            # 新模式的触发种类与规则一致，不允许自由组装相反边沿或伪初始化。
            if self.rule.rule_type == 'start_only' and (self.trigger_kind not in ('start_only', 'initial') or self.trigger_kind == 'initial' and not self.rule.emit_initial) or self.rule.rule_type != 'start_only' and self.trigger_kind == 'start_only':
                raise ValueError('start_only点触发种类与规则不匹配')
            # 初始点/边沿都不能增面积。
            if self.status != 'point' or self.end_ns is not None or self.start_ns != self.confirmed_ns or self.trigger_kind not in ('rising_edge', 'falling_edge', 'initial', 'start_only') or self.rule.rule_type == 'condition_duration' or self.quality != Q.NONE:
                # 不把point伪装零长度活动。
                raise ValueError('point事件边界/类型矛盾')
        else:
            # 活动严格正长，已确认且终点可相等。
            if self.event_type != 'activity' or self.status not in ('closed', 'timeout', 'interrupted', 'truncated') or self.trigger_kind != 'condition_duration' or self.end_ns is None or self.rule.rule_type != 'condition_duration':
                # 不输出内部pending/active占位。
                raise ValueError('activity事件结构非法')
            # 区间跨度也需合法int64。
            interval = Interval(self.start_ns, self.end_ns)
            # 终点真实新TRUE不得建立零长度活动。
            if interval.start_ns == interval.end_ns or not self.start_ns <= self.confirmed_ns <= self.end_ns:
                # 门槛恰好end仍合法确认。
                raise ValueError('activity确认/连续边界矛盾')
        # 来源属于该会话，不能继承其他任务引用。
        for ref in self.source_refs:
            # 合成ConditionSpan允许无原SourceRef，但非空必须真实typed。
            if not isinstance(ref, SourceRef) or ref.session_id != self.rule.session_id:
                # 不接受仅同名来源作为归属证明。
                raise ValueError('Event来源与session不一致')


def make_event(rule, start_ns, confirmed_ns, end_ns, status, quality, diagnostic, refs=(), *, trigger='condition_duration') -> Event:
    """根据规则和时间事实生成稳定事件标识，再构造已确认事件。

    参数:
        rule (TemporalRule): 当前检测规则，包含数据集和会话身份。
        start_ns、confirmed_ns (int): 活动起点和确认时间，或触发点时间，单位为纳秒。
        end_ns (int | None): 活动结束时间，单位为纳秒；点事件使用None。
        status (str): closed、timeout、interrupted、truncated或point。
        quality、diagnostic (QualityFlag): 结束质量和完整依赖诊断。
        refs (tuple[SourceRef, ...]): 当前实际来源引用，默认空tuple。
        trigger (str): 触发种类，默认condition_duration，边沿或初始化点另行声明。
    返回:
        Event: 通过模型检查的事件。标识由规则及时间事实生成，不受批次切分、
        质量诊断或可选语义元数据变化影响。
    异常:
        TypeError、ValueError或OverflowError: 事件模型或身份材料不符合约束。
    副作用:
        无，不加载来源，不修改规则或检测器状态。
    """
    # 规则范围和事件内容稳定，质量/metadata变化不冒充另一时间事实。
    payload = (rule.dataset_id, rule.session_id, rule.rule_id, rule.rule_type, rule.minimum_duration_ns, rule.emit_initial, start_ns, confirmed_ns, end_ns, status, trigger)
    # 仅新模式增加固定窗口身份材料；已有三个kind的SHA内容逐字保持。
    if rule.rule_type == 'start_only':
        payload += (rule.window_duration_ns,)
    # 旧默认事件ID保持；严格比较作为新的规则身份，避免同端点混淆。
    if rule.duration_comparison != '>=':
        payload += (rule.duration_comparison,)
    # 完整SHA避免同起止秒数/不同规则碰撞。
    identity = sha256(_identity(payload).encode('utf-8')).hexdigest()
    # source_refs保留当前真实来源，不参与规则时间事实的隐式改写。
    return Event(identity, rule, 'point' if status == 'point' else 'activity', start_ns, confirmed_ns, end_ns, status, trigger, quality, diagnostic, refs)


@dataclass(frozen=True)
class ConditionTimeline:
    """保存一个完整会话的条件时间轴，检测器可以按批消费其中的时间组。

    首末时间组必须对应start_ns和end_ns；最后一组是唯一的terminal。时间严格
    递增，同刻更新已经归并；模型不会排序或补齐缺口。source_refs保存原来源，
    与规则会话的归属关系由检测器检查。批次切分不改变条件证据。
    """

    start_ns: int  # 连续分析起点。
    end_ns: int  # 连续分析终点，真实点仍可观察。
    ticks: tuple[ConditionTick, ...]  # 完整时间组，含TTL/source/EOF证据。
    source_refs: tuple[SourceRef, ...] = ()  # 实际condition依赖源定位。

    def __post_init__(self):
        """检查时间轴完整性，不填充未知间隙或末周期。

        参数: 无，读取domain/ticks/source_refs。
        返回: None，保持显式时间证据。
        异常: TypeError/ValueError/OverflowError为结构/边界/顺序。
        """
        # 域跨度必须可表示，零域只含真实末点。
        Interval(self.start_ns, self.end_ns)
        # 不能用可变列表或空轴冒充完整会话。
        if not isinstance(self.ticks, tuple) or not self.ticks or not isinstance(self.source_refs, tuple):
            # 空观测可显式一个terminal UNKNOWN点，不自动补。
            raise TypeError('timeline需非空tuple ticks及tuple refs')
        # typed组本身已检查continuous/point质量。
        if any(not isinstance(tick, ConditionTick) for tick in self.ticks):
            # 不接自由字典作为完整证据。
            raise TypeError('timeline需要ConditionTick')
        # 真实domain首末完整，不丢EOF边界。
        if self.ticks[0].time_ns != self.start_ns or self.ticks[-1].time_ns != self.end_ns or not self.ticks[-1].terminal:
            # 保证检测finish只发生真正会话末点。
            raise ValueError('timeline首末/terminal与domain不一致')
        # 全轴严格递增，原子同时间组已在上游收齐。
        for index, tick in enumerate(self.ticks):
            # terminal只能出现在真实末组。
            if index < len(self.ticks)-1 and tick.terminal or index and tick.time_ns <= self.ticks[index-1].time_ns:
                # 不将batch/file尾当EOF或排序掩盖回退。
                raise ValueError('timeline中途terminal/时间回退/重复组')
        # 来源结构真实typed，归属稍后与rule.session核对。
        if any(not isinstance(ref, SourceRef) for ref in self.source_refs):
            # 不用名字字符串冒充定位。
            raise TypeError('timeline source_refs需SourceRef')


def timeline_from_spans(spans: tuple[ConditionSpan, ...], *, terminal_state: Truth | None = None,
                        terminal_quality: Q = Q.NONE, terminal_actual: bool = False) -> ConditionTimeline:
    """把完整手算半开区间转换为明确边界证据，不伪造EOF FALSE。

    参数: spans为正长度、相邻、完整tuple；terminal_state/quality为可选真实
        末点状态，terminal_actual明确是否真实更新，默认EOF沿用历史点状态。
    返回: ConditionTimeline；末端continuous UNKNOWN/MISSING，仅point保留证据。
    异常: TypeError/ValueError为结构/缺口/point更新声明矛盾。
    """
    # 合成条件资料也必须typed完整，不填补missing域。
    if not isinstance(spans, tuple) or not spans or any(not isinstance(item, ConditionSpan) for item in spans):
        # 零域用ConditionTick直接声明，无正区间不能猜范围。
        raise TypeError('spans需要非空tuple ConditionSpan')
    # 手算明确条件更新可作为边沿证据。
    ticks = []
    # 区间边界是静态输入协议，不是参考/数组状态算法。
    for index, span in enumerate(spans):
        # 间隙/重叠都不能静默补齐或合并真实活动。
        if index and spans[index-1].end_ns != span.start_ns:
            # 用显式UNKNOWN span表达缺口。
            raise ValueError('ConditionSpan需完整相邻，不自动填充')
        # 给定边界是真实状态证据；unknown说明实际无效。
        ticks.append(ConditionTick(span.start_ns, span.state, span.quality, actual_unknown=span.state is Truth.UNKNOWN, diagnostic_quality=span.quality))
    # 默认末点沿用最后明示span的历史状态，不制造更新。
    point_state = spans[-1].state if terminal_state is None else terminal_state
    # 未覆写point时保留末span的原质量。
    point_quality = spans[-1].quality if terminal_state is None else terminal_quality
    # 真实末点覆写必须明确actual，不能冒充纯EOF。
    if terminal_actual and terminal_state is None:
        # 默认历史值不算新末点证据。
        raise ValueError('terminal_actual需明确terminal_state')
    # 连续EOF排除而point包含，真实false/invalid优先结束事实。
    ticks.append(ConditionTick(spans[-1].end_ns, Truth.UNKNOWN, Q.MISSING, terminal_actual, True, True,
                               point_state, point_quality, terminal_actual and point_state is Truth.UNKNOWN, Q.MISSING | point_quality))
    # 域与完整时间组由模型统一校验。
    return ConditionTimeline(spans[0].start_ns, spans[-1].end_ns, tuple(ticks))
