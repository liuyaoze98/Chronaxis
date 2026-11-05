"""声明事件窗口和片段结果，校验归属并保存请求、实际边界与原活动关联。

输入是WindowSpec、已完成Event元组及真实观测Interval；独立后端负责扩展、
分组和裁剪，再由本模块包装Segment。片段合并不重写Event或填平条件未知。
核心执行模型独立于上层JSON WindowPlan，由执行层显式转换，避免核心导入配置/I/O。
本模块只验证协议、归类和生成稳定ID；不计算窗口数值、不读取旧日志或调用writer。
输入与返回均为完整内存模型；资源预算和原始报文导出由上层负责。
"""

# 冻结结构保留边界和身份，标准库hash只生成结果标识。
from dataclasses import dataclass
from hashlib import sha256
import json
from math import isclose, isfinite
# 所有时间与来源位置为typed模型。
from .models import Interval, SourceRef
from .temporal import Event
from .types import QualityFlag as Q
from .validation import require_identifier, require_text
from ..timebase.conversion import require_int64_ns


@dataclass(frozen=True)
class WindowSpec:
    """声明围绕同一规则事件的前后范围及明确合并政策。

    anchor为point或activity；pre/post为非负int64纳秒。point至少一项正。
    exit_delay仅用于activity且post=0，根据真实活动间隔分组，不能按pre重叠扩大。
    实例不保存执行状态，不依赖上层配置或旧模式的隐式参数解释。
    """

    window_id: str  # 当前窗口唯一简单标识。
    event_rule_id: str  # 已完成事件的规则标识。
    anchor: str  # point或activity，以onset/点时刻为锚。
    pre_ns: int = 0  # 非负前扩展，不使用confirmed代替onset。
    post_ns: int = 0  # 非负后扩展，exit_delay模式必须0。
    merge: str = 'none'  # none/overlap/overlap_and_adjacent/exit_delay。
    exit_delay_ns: int | None = None  # 只用于同名合并模式，不能重复附加post。

    def __post_init__(self):
        """检查窗口声明，不计算边界或创建运行状态。

        参数: 无；读取冻结字段。
        返回: None。
        异常: TypeError/ValueError/OverflowError为标识、参数或时间协议错误。
        """
        # 名称与真实引用分开，不能用自由路径冒充规则标识。
        require_identifier(self.window_id, 'window_id')
        require_identifier(self.event_rule_id, 'event_rule_id')
        # 精确非负纳秒，不接受bool、float或非法模式。
        object.__setattr__(self, 'pre_ns', require_int64_ns(self.pre_ns, 'pre_ns'))
        object.__setattr__(self, 'post_ns', require_int64_ns(self.post_ns, 'post_ns'))
        if self.pre_ns < 0 or self.post_ns < 0 or self.anchor not in ('point', 'activity') or self.merge not in ('none', 'overlap', 'overlap_and_adjacent', 'exit_delay'):
            raise ValueError('窗口锚点、扩展或合并政策错误')
        # 点本身没有持续长度，必须明确扩展出窗口。
        if self.anchor == 'point' and self.pre_ns == self.post_ns == 0:
            raise ValueError('point窗口至少一个扩展为正')
        # single只有退出延迟扩展，不能再附加同值post。
        if self.merge == 'exit_delay':
            object.__setattr__(self, 'exit_delay_ns', require_int64_ns(self.exit_delay_ns, 'exit_delay_ns'))
            if self.anchor != 'activity' or self.post_ns != 0 or self.exit_delay_ns < 0:
                raise ValueError('exit_delay要求activity、post=0及非负delay')
        elif self.exit_delay_ns is not None:
            raise ValueError('exit_delay_ns仅用于exit_delay合并')


@dataclass(frozen=True)
class Segment:
    """保存一个片段的请求与实际范围，并关联全部原事件。

    requested永不因EOF裁剪重写；actual为真实交集或None。覆盖为实际/请求时长。
    status为complete、partial或empty；event_statuses保留closed/timeout/interrupted/truncated/point。
    parent_event_ids、质量和字段来源不可变；合并不改变原事件数量或统计scope。
    """

    segment_id: str  # 内容SHA，区别于旧整数秒文件名。
    dataset_id: str  # 当前数据集归属。
    session_id: str  # 当前真实会话，不跨会话合并。
    window: WindowSpec  # 原窗口声明，保留合并政策。
    requested: Interval  # 完整请求半开范围。
    actual: Interval | None  # 裁剪后实际范围，无交集为None。
    requested_coverage: float  # 两后端独立计算的时长比。
    status: str  # complete/partial/empty，不冒充文件发布完成。
    parent_event_ids: tuple[str, ...]  # 全部原活动/点事件稳定关联。
    event_statuses: tuple[str, ...]  # 同长原事件结束状态，UNKNOWN中断不改closed。
    quality: Q  # 全部原事件的结束质量及依赖诊断。
    source_refs: tuple[SourceRef, ...]  # 当前所有依赖原字段引用。

    def __post_init__(self):
        """检查片段归属、范围、覆盖及原事件引用的一致性。

        参数: 无；读取全部冻结字段。
        返回: None，不补范围或静默改覆盖。
        异常: TypeError/ValueError/OverflowError为非法结果模型。
        """
        # 稳定文本与简单会话标识各自校验。
        require_text(self.segment_id, 'segment_id')
        require_identifier(self.dataset_id, 'dataset_id')
        require_identifier(self.session_id, 'session_id')
        if not isinstance(self.window, WindowSpec) or not isinstance(self.requested, Interval) or self.requested.duration_ns() == 0:
            raise TypeError('Segment需WindowSpec及正请求Interval')
        # 交集必须在原请求内，不能外推或接受自由对象。
        if self.actual is not None and (not isinstance(self.actual, Interval) or self.actual.start_ns < self.requested.start_ns or self.actual.end_ns > self.requested.end_ns):
            raise ValueError('Segment实际范围必须是请求子区间')
        actual_duration = 0 if self.actual is None else self.actual.duration_ns()
        # 完整/部分/空范围由真实边界判定，不仅靠浮点比值。
        expected_status = 'complete' if self.actual == self.requested else 'partial' if actual_duration else 'empty'
        if self.status != expected_status or type(self.requested_coverage) not in (int, float) or not isfinite(self.requested_coverage) or not 0 <= self.requested_coverage <= 1:
            raise ValueError('Segment状态或覆盖错误')
        # 独立float64比值只容许相对舍入差；绝对容差为0，极小正覆盖不能伪报为0。
        if not isclose(self.requested_coverage, actual_duration / self.requested.duration_ns(), rel_tol=1e-15, abs_tol=0.):
            raise ValueError('Segment覆盖与时间事实不一致')
        # 每个原事件都有唯一ID与保留的结束状态。
        if not isinstance(self.parent_event_ids, tuple) or not self.parent_event_ids or len(set(self.parent_event_ids)) != len(self.parent_event_ids):
            raise ValueError('Segment需非空唯一parent_event_ids')
        for identity in self.parent_event_ids:
            require_text(identity, 'parent_event_id')
        if not isinstance(self.event_statuses, tuple) or len(self.event_statuses) != len(self.parent_event_ids) or any(status not in ('closed', 'timeout', 'interrupted', 'truncated', 'point') for status in self.event_statuses):
            raise ValueError('Segment事件状态需同长完整tuple')
        if not isinstance(self.quality, Q) or not isinstance(self.source_refs, tuple) or any(not isinstance(ref, SourceRef) for ref in self.source_refs):
            raise TypeError('Segment质量与来源需typed模型')


def require_windows(events, spec, observation):
    """验证已完成事件的排序、规则/会话归属和真实观测范围。

    参数: events为已排序Event tuple；spec为WindowSpec；observation为真实Interval。
    返回: None，只校验协议，不扩展或合并窗口。
    异常: TypeError/ValueError为类型、重复、回退、归属或锚点不匹配。
    """
    # 上层负责取得真实观测，不以请求domain补齐EOF。
    if not isinstance(events, tuple) or not isinstance(spec, WindowSpec) or not isinstance(observation, Interval) or any(not isinstance(event, Event) for event in events):
        raise TypeError('窗口执行需Event tuple/WindowSpec/Interval')
    identities = set()
    previous = None
    for event in events:
        # 同一窗口仅使用同一规则/数据集/会话；不重新排序以掩盖回退。
        if event.rule.rule_id != spec.event_rule_id or event.event_type != spec.anchor or event.event_id in identities:
            raise ValueError('窗口事件规则、锚点或唯一性不匹配')
        # start_only的固定结束与抑制时长是同一声明，不能额外合并或改变post。
        if event.rule.rule_type == 'start_only' and (spec.merge != 'none' or spec.post_ns != event.rule.window_duration_ns):
            raise ValueError('start_only窗口需merge=none且post等于固定时长')
        if previous is not None and (event.start_ns < previous.start_ns or (event.rule.dataset_id, event.rule.session_id) != (previous.rule.dataset_id, previous.rule.session_id)):
            raise ValueError('窗口事件不能回退或跨会话合并')
        # 相同持续规则的真实活动不能重叠；点同刻不同规则已被上面拒绝。
        if previous is not None and spec.anchor == 'activity' and event.start_ns < previous.end_ns:
            raise ValueError('同一规则真实活动不能重叠')
        if event.start_ns < observation.start_ns or (event.start_ns if event.end_ns is None else event.end_ns) > observation.end_ns:
            raise ValueError('事件事实超出实际观测范围')
        identities.add(event.event_id)
        previous = event


@dataclass(frozen=True)
class CompactSegment:
    """仅保实际业务范围和父事件关联，不输出重复请求边界、覆盖比例或来源副本。"""
    segment_id: str
    dataset_id: str
    session_id: str
    window_id: str
    actual: Interval | None
    status: str
    parent_event_ids: tuple[str,...]
    quality: Q
    coverage: float | None = None  # 仅下游明确设置覆盖门槛时计算，默认不保存。


def require_resolved_windows(events,bounds,compact):
    """检查预先按选定周期取得的实际边界，未提供时沿旧实际扩展。

    参数: 原事件、可选同长(start,end,left_clipped,right_clipped)tuple、精简开关。
    返回: None。异常: 类型/长度/边界错误。副作用: 不构造另一时间轴。
    """
    if type(compact) is not bool:
        raise TypeError('compact需要bool')
    if bounds is None:
        return
    if not compact or type(bounds) is not tuple or len(bounds)!=len(events):
        raise ValueError('已解析边界仅用于精简窗口且需同长tuple')
    for item in bounds:
        if type(item) is not tuple or len(item)!=4 or any(type(v) is not bool for v in item[2:]):
            raise TypeError('窗口边界需起止与两侧裁剪标识')
        Interval(item[0],item[1])


def make_segment(spec, requested, actual, coverage, parents, *, compact=False, clipped=False):
    """包装独立后端的边界/覆盖事实，保留全部原活动元数据。

    参数: spec原窗口；requested/actual已算边界；coverage独立时长比；parents非空Event tuple；
        compact仅构造精简业务输出，clipped说明选定周期已在输入首尾裁剪。
    返回: Segment，稳定ID包含窗口语义、原事件引用与请求/实际边界。
    异常: 输出模型不满足约束时传播检查异常。
    副作用: 无；不计算扩展、分组或窗口覆盖，不修改Event。
    """
    # 原活动ID与状态保持顺序；元数据归并不涉及数值或旧扫描。
    identities = tuple(event.event_id for event in parents)
    if compact:
        quality=Q.NONE
        for event in parents:
            quality|=event.quality | (event.dependency_quality & Q.ESTIMATED)
        if actual is not None and not actual.duration_ns():
            actual=None
        status='empty' if actual is None else 'partial' if clipped or actual!=requested else 'complete'
        payload=('window-v2',spec.window_id,identities,None if actual is None else (actual.start_ns,actual.end_ns),status)
        identity=sha256(json.dumps(payload,separators=(',',':')).encode('utf-8')).hexdigest()
        return CompactSegment(identity,parents[0].rule.dataset_id,parents[0].rule.session_id,
                              spec.window_id,actual,status,identities,quality)
    statuses = tuple(event.status for event in parents)
    quality = Q.NONE
    refs = []
    for event in parents:
        quality |= event.quality | event.dependency_quality
        for ref in event.source_refs:
            if ref not in refs:
                refs.append(ref)
    # 稳定规范JSON生成ID；裁剪范围和配置变化对应不同片段身份。
    payload = ('window-v1', spec.window_id, spec.event_rule_id, spec.anchor, spec.pre_ns, spec.post_ns,
               spec.merge, spec.exit_delay_ns, identities, requested.start_ns, requested.end_ns,
               None if actual is None else (actual.start_ns, actual.end_ns))
    identity = sha256(json.dumps(payload, separators=(',', ':')).encode('utf-8')).hexdigest()
    # 分类只是输出政策，不复用任一后端的扩展或分组算法。
    status = 'complete' if actual == requested else 'partial' if actual is not None and actual.duration_ns() else 'empty'
    return Segment(identity, parents[0].rule.dataset_id, parents[0].rule.session_id, spec, requested, actual,
                   coverage, status, identities, statuses, quality, tuple(refs))
