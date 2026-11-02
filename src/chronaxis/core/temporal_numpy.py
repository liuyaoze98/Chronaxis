"""按列查找连续TRUE区间和真实边沿，再将匹配结果构造成事件。

输入为完整条件时间组；每批构造成int64时间、内部状态码和uint16诊断列。
布尔掩码找出TRUE区间起止和边沿，整数数组计算持续时长与确认时间。
Python循环负责输入装箱及按活动或匹配点生成Event，不逐点调用参考状态机。
持续候选及边沿前态跨批保留，空批不重置，只在真实会话终点收尾。
默认累计全部事件；主动drain_events仅转交当前输出，finish随后返回剩余未取走事件。
本模块依赖NumPy和核心模型，与参考检测共享协议检查及事件身份，检测算法
独立；不读取来源、不修改输入、不持有全局规则状态。
"""

# 真正列运算，不调用reference状态推进。
import numpy as np
# 冻结证据与稳定事件身份属于共享模型。
from .temporal import ConditionTimeline, make_event
# 仅这两个函数检查范围/输入协议，无参考数值或状态逻辑。
from .temporal_reference import require_batch, require_detector
# 标准typed三值/原因，物理列编码在本模块明确。
from .types import QualityFlag as Q, Truth


class NumpyTemporalDetector:
    """保存一个规则在一个会话内的开放TRUE区间和边沿前态。

    开放区间的起点、确认时间和诊断跨批保存；内部状态码0、1、2分别表示TRUE、
    FALSE和UNKNOWN，只用于数组存储。会话跨度先经过检查，数组时间减法据此
    保证范围安全。事件及生命周期属于当前实例，finish后不能继续输入。
    start_only边沿候选由数组掩码定位，仅候选索引上的固定窗口抑制保留状态循环；
    blocked_until_ns跨批保存，到期不制造边沿，被抑制候选不排队。
    drain_events只清空输出，不重置run/前态/抑制或EOF状态；未使用时finish行为不变。
    """

    def __init__(self, rule, start_ns, end_ns, source_refs=(), *, record_clock=False):
        """校验规则范围并创建全新run/边沿生命周期。

        参数: rule、ns域和当前source_refs。
        返回: None，没有共享参考实例或全局缓存。
        异常: 规则/范围/来源结构错误传播。
        """
        # 校验协议可共享，检测算法完整独立。
        # record_clock仅接受调用方显式周期增量；实际坐标仍用于事件。
        require_detector(rule, start_ns, end_ns, source_refs)
        if type(record_clock) is not bool:
            raise TypeError('record_clock需要bool')
        self.record_clock = record_clock
        self.candidate_elapsed = self.blocked_remaining = 0
        # 当前规则身份保留，不从上次任务继承。
        self.rule, self.start_ns, self.end_ns, self.refs = rule, start_ns, end_ns, source_refs
        # 第一个批次之前没有已知连续前态。
        self.last_time, self.last_state, self.seen_known = None, 2, False
        # 未结束TRUE run可跨任意batch保留。
        self.candidate_start, self.confirmed, self.diagnostic = None, None, Q.NONE
        # 未主动排空时累计全部最终事件；输出和EOF/关闭状态独立保存。
        self.events, self.ended, self.finished = [], False, False
        # start_only只保存一个接受触发后的截止时间；普通batch不重置，不排队。
        self.blocked_until_ns = None

    @property
    def next_deadline_ns(self):
        """提供当前开放run的精确未确认deadline。

        参数: 无；读取当前候选/规则及域。
        返回: 合法ns或None，域外deadline不wrap。
        异常: 无主动异常。
        """
        # 无候选/已确认不会安排额外门槛。
        if self.record_clock or self.candidate_start is None or self.confirmed is not None:
            # edge规则没有开放TRUE run。
            return None
        # 只计算一个状态常量，不逐样本数值循环。
        deadline = self.candidate_start + self.rule.qualifying_duration_ns
        # 完整domain以外不产生确认。
        return deadline if deadline <= self.end_ns else None

    def _duration(self, ticks, times, states, diagnostic, advances=None):
        """按布尔掩码寻找TRUE区间并计算门槛，只在活动边界构造事件。

        参数:
            ticks (tuple[ConditionTick, ...]): 已校验的完整时间组。
            times (ndarray[int64], shape=(N,)): 当前批的纳秒坐标。
            states (ndarray[int8], shape=(N,)): 内部状态码，0为TRUE、1为FALSE、2为UNKNOWN。
            diagnostic (ndarray[uint16], shape=(N,)): 各组完整质量原因组合。
        返回:
            None: 更新本实例未结束区间、确认时间和最终事件，保留跨批状态。
        异常:
            TypeError、ValueError或OverflowError: 事件模型检查失败。
            MemoryError: 数组分配失败；不会丢弃输入继续计算。
        边界:
            会话终点不创建新区间；达到门槛的已结束区间输出事件，未结束区间只
            保存状态。输入会话跨度已证明可表示，数组时长及域内确认时间安全。
        """
        # 终点即使真实TRUE也不建立任何新持续区间。
        true = (states == 0) & ~np.array([tick.terminal for tick in ticks], dtype=bool)
        # 上一批开放run作为本批前一连续状态。
        carried = self.candidate_start is not None
        # 当前各行前态用于真正批量转入/转出掩码。
        previous = np.concatenate((np.array([carried], dtype=bool), true[:-1]))
        # 只找静态数组边界，不逐样本解释状态。
        starts = np.flatnonzero(true & ~previous)
        # 转出位置本身就是结束证据时间，包含跨批0位置。
        ends = np.flatnonzero(~true & previous)
        # 跨批前缀run没有本地onset行，使用当前0位置作为诊断片段起点。
        positions = np.concatenate((np.array([0], dtype=np.int64), starts)) if carried else starts
        # 明确当前批末是否还有真实持续区间，普通批末不close。
        open_last = bool(true[-1])
        # 未结束区间到本批最新时间的跨度只用于确认，不作为最终结束边界。
        finish_positions = np.concatenate((ends, np.array([len(ticks)-1], dtype=np.int64))) if open_last else ends
        # 起点物理列独立复制，前缀改为真实上批onset。
        onsets = times[positions].copy()
        # 跨批真实onset不能被batch0时间覆盖。
        if carried:
            # 原onset已在当前domain内。
            onsets[0] = self.candidate_start
        # 每个run到真实结束或本批watermark的可观测时长。
        finishes = times[finish_positions]
        # domain跨度已证明≤int64 max，先验允许安全向量减法。
        durations = finishes - onsets
        carried_confirmed = self.confirmed
        if self.record_clock:
            # 本批增量只用于定位达到门槛的实际行；不用合成时间坐标返回事件。
            cumulative = np.cumsum(np.asarray(advances, dtype=object))
            bases = cumulative[positions].copy()
            if carried:
                bases[0] = -self.candidate_elapsed
            durations = cumulative[finish_positions] - bases
        # 门槛恰等end也确认，unknown时长从未混进run。
        eligible = (durations > self.rule.minimum_duration_ns if self.rule.duration_comparison == ">"
                    else durations >= self.rule.minimum_duration_ns)
        # 仅在已证明起点加阈值不超过结束点和会话终点的位置执行加法，防止回绕。
        confirmations = np.zeros(len(onsets), dtype=np.int64)
        # 输出精确deadline，不用当前实际更新时间替代。
        if not self.record_clock and np.any(eligible):
            np.add(onsets, np.int64(self.rule.qualifying_duration_ns), out=confirmations, where=eligible)
        elif self.record_clock:
            for index in np.flatnonzero(eligible):
                if carried and index == 0 and carried_confirmed is not None:
                    confirmations[index] = carried_confirmed
                else:
                    first = int(positions[index])
                    offsets = cumulative[first:int(finish_positions[index])+1] - bases[index]
                    hit = first + int(np.flatnonzero(offsets >= self.rule.qualifying_duration_ns)[0])
                    confirmations[index] = times[hit]
        # 保存旧前缀诊断，之后按新run重新初始化。
        carried_diagnostic = self.diagnostic
        # 默认没有跨到下一批的run，open_last时再赋真实最后run。
        self.candidate_start, self.confirmed, self.diagnostic = None, None, Q.NONE
        # 循环次数是本批活动run数量，数值门槛已整列计算。
        for index, position in enumerate(positions):
            # 包含结束证据行的全部uint16诊断reduce不会数值sum溢出。
            trace = Q(int(np.bitwise_or.reduce(diagnostic[position:finish_positions[index]+1], initial=np.uint16(0))))
            # 前缀继承旧活动诊断，新run不继承旧未知缺口。
            if carried and index == 0:
                # 保留上批期间所有原因，不跨别的活动传播。
                trace |= carried_diagnostic
            # 最后开放run只存状态，不写内部active伪事件。
            if open_last and index == len(positions)-1:
                # 真实onset保留跨批/跨文件。
                self.candidate_start = int(onsets[index])
                # 当前watermark已到精确deadline时确认。
                self.confirmed = int(confirmations[index]) if eligible[index] else None
                if self.record_clock:
                    self.candidate_elapsed = min(self.rule.qualifying_duration_ns, int(durations[index]))
                # 诊断状态与onset共同跨batch保存。
                self.diagnostic = trace
                # 普通batch尾禁止收尾。
                continue
            # 未达到门槛的run直接丢候选，不输出已确认Event。
            if not eligible[index]:
                # UNKNOWN缺口不能帮它累计后续TRUE。
                continue
            # 当前真实结束组来自run的转出索引。
            tick = ticks[int(finish_positions[index])]
            # 独立结束分类：实际knownFalse优先closed。
            if tick.actual_update and tick.point_state is Truth.FALSE:
                # 不因EOF并列降为truncated。
                status, quality = 'closed', Q.NONE
            # 真实无效/真实更新导致未知优先interrupted。
            elif tick.actual_unknown:
                # actual_unknown是明确因果证据，不是任意更新布尔值。
                status, quality = 'interrupted', tick.point_quality
            # 观测边界且无实际结束才truncated，保留TTL诊断。
            elif tick.terminal or tick.observation_end:
                # source EOF只结束受影响run，其他规则轴仍继续。
                status, quality = 'truncated', tick.quality | tick.point_quality
            # 显式FALSE连续证据也可闭合。
            elif tick.state is Truth.FALSE:
                # knownFALSE不能当未知中断。
                status, quality = 'closed', Q.NONE
            else:
                # TTL早于EOF或未知缺口为interrupted。
                status, quality = 'interrupted', tick.quality
            # 输出正半开已确认活动，identity与batch无关。
            self.events.append(make_event(self.rule, int(onsets[index]), int(confirmations[index]), int(finishes[index]),
                                          status, quality, trace, self.refs))

    def _edges(self, ticks, times, states, advances=None):
        """比较前一连续状态与当前真实点状态，输出已知上升沿或下降沿。

        参数:
            ticks (tuple[ConditionTick, ...]): 完整时间组，含实际更新证据。
            times (ndarray[int64], shape=(N,)): 纳秒坐标。
            states (ndarray[int8], shape=(N,)): 当前连续状态码，0为TRUE、1为FALSE、2为UNKNOWN。
        返回:
            None: 只遍历匹配索引构造点事件；start_only候选执行依赖前次接受触发的
            抑制状态循环，实际边沿定位已数组化，不逐样本推进参考状态机。
        异常:
            TypeError、ValueError或OverflowError: 事件模型检查失败。
            MemoryError: 数组分配失败。
        边界:
            纯计时器及观测结束不产生边沿；UNKNOWN不能当作FALSE。emit_initial
            仅允许首次已知TRUE的实际更新产生初始化点。
        """
        # 旧连续态跨批保留，未知代码2不当False代码1。
        previous = np.concatenate((np.array([self.last_state], dtype=np.int8), states[:-1]))
        # point可能含真实terminal更新，不强行用连续EOF UNKNOWN。
        point = np.array([0 if tick.point_state is Truth.TRUE else 1 if tick.point_state is Truth.FALSE else 2 for tick in ticks], dtype=np.int8)
        # 没有实际更新的deadline/EOF不能凭空产生point。
        actual = np.array([tick.actual_update for tick in ticks], dtype=bool)
        # 首次known之前的mask用真实整列前缀或，不Python数组truthiness。
        known_before = np.concatenate((np.array([self.seen_known], dtype=bool), np.logical_or.accumulate(point != 2)[:-1]))
        # 前一批已有known时后续各行均非首次known。
        known_before |= self.seen_known
        # rising_edge/FALSE→TRUE或falling_edge/TRUE→FALSE，UNKNOWN都不匹配。
        selected = actual & ((previous == 1) & (point == 0) if self.rule.rule_type in ('rising_edge', 'start_only') else (previous == 0) & (point == 1))
        # 显式初始化仅首次known TRUE，不会在未知恢复重触发。
        initial = actual & ~known_before & (point == 0) if self.rule.rule_type in ('rising_edge', 'start_only') and self.rule.emit_initial else np.zeros(len(ticks), dtype=bool)
        # 事件循环只遍历匹配indices，不逐点检测。
        cumulative = np.cumsum(np.asarray(advances, dtype=object)) if self.record_clock else None
        consumed = 0
        for index in np.flatnonzero(selected | initial):
            # 真末点start=confirmed，end=None，无法增加面积。
            time = int(times[index])
            # 固定窗口抑制依赖上次接受触发，是允许的事件候选状态循环；边沿检测已数组化。
            if self.rule.rule_type == 'start_only':
                if self.record_clock:
                    self.blocked_remaining = max(0, self.blocked_remaining - int(cumulative[index]) + consumed)
                    consumed = int(cumulative[index])
                    if self.blocked_remaining:
                        continue
                elif self.blocked_until_ns is not None and time < self.blocked_until_ns:
                    continue
            # 当前完整point诊断与活动continuous诊断分开。
            self.events.append(make_event(self.rule, time, time, None, 'point', Q.NONE, ticks[int(index)].diagnostic_quality,
                                          self.refs, trigger='initial' if initial[index] else self.rule.rule_type))
            # 只接受触发更新截止，UNKNOWN或被抑制边沿不影响固定结束时间。
            if self.rule.rule_type == 'start_only':
                if self.record_clock:
                    self.blocked_remaining = self.rule.window_duration_ns
                else:
                    self.blocked_until_ns = time + self.rule.window_duration_ns
        if self.record_clock and self.rule.rule_type == 'start_only':
            self.blocked_remaining = max(0, self.blocked_remaining - int(cumulative[-1]) + consumed)

    def push(self, ticks, *, advances=None):
        """验证组序后批量检测，空批不改任何跨批状态。

        参数: ticks完整ConditionTick tuple。
        返回: 本批新最终Event tuple；开放run保留实例状态。
        异常: ValueError为finish后/回退/边界；布局模型错误传播。
        """
        # 真正关闭后不允许复用状态。
        if self.finished:
            # 新会话创建新实例。
            raise ValueError('检测器已finish')
        # 仅共享时间/类型协议校验，没有参考状态算法。
        require_batch(ticks, self.start_ns, self.end_ns, self.last_time, self.ended)
        from .temporal_clock import require_clock_advances
        require_clock_advances(ticks, advances, self.record_clock, self.last_time)
        # 空batch不伪造terminal，不重置候选。
        if not ticks:
            # 不分配无用列或制造事件。
            return ()
        # 本次新增事实起始序号，不用batch序号作事件ID。
        previous_count = len(self.events)
        # 完整条件组逐项装入数组，随后用列运算和掩码执行检测。
        times = np.array([tick.time_ns for tick in ticks], dtype=np.int64)
        # 物理状态码明确0/1/2，不把UNKNOWN编码为False。
        states = np.array([0 if tick.state is Truth.TRUE else 1 if tick.state is Truth.FALSE else 2 for tick in ticks], dtype=np.int8)
        # 完整诊断OR包含端点并列原因。
        diagnostic = np.array([int(tick.diagnostic_quality | tick.quality | tick.point_quality) for tick in ticks], dtype=np.uint16)
        # 不同kind只执行对应真实算法，不空宣称其他规则。
        if self.rule.rule_type == 'condition_duration':
            # 批量run与安全整数deadline独立于reference。
            self._duration(ticks, times, states, diagnostic, advances)
        else:
            # 实际point掩码检测与source EOF分离。
            self._edges(ticks, times, states, advances)
        # 本批最后真实continuous前态跨到下一批。
        self.last_time, self.last_state = int(times[-1]), int(states[-1])
        # 全批有任何known point即完成初始化判据。
        self.seen_known |= any(tick.point_state is not Truth.UNKNOWN for tick in ticks)
        # 只真正terminal结束流，普通batch尾不结束。
        self.ended |= ticks[-1].terminal
        # 不返回尚未结束内部active候选。
        return tuple(self.events[previous_count:])

    def drain_events(self):
        """转交当前未取走的最终事件，保留所有批量run和边沿业务状态。

        参数: 无，读取本实例已经产生的events。
        返回: Event tuple，连续排空允许返回空tuple。
        异常: MemoryError为tuple构造失败；失败时输出列表保持原内容。
        副作用: 成功只清空events，候选/确认/诊断/前态/抑制及生命周期均不变。
        """
        # 先完成结果分配再清空列表，调用方预算须覆盖列表和tuple同时存活的瞬间。
        events = tuple(self.events)
        self.events.clear()
        return events

    def finish(self):
        """在真正terminal已消费后关闭并返回当前剩余未取走的事件。

        参数: 无，不能补造EOF或触发额外扫描。
        返回: 尚未drain的Event tuple；未使用drain时仍是全部事件，ID/边界/质量不变。
        异常: ValueError为缺terminal或重复finish。
        """
        # 检查真实输入已齐，batch/file尾没有结束授权。
        if not self.ended or self.finished:
            # 无数据时也需显式完整域terminal证据。
            raise ValueError('finish需真正terminal且不能重复')
        # 完整状态封闭，不跨session复用。
        self.finished = True
        # 此时没有未收尾的活动；返回尚未主动drain取走的输出，未drain时仍为全部。
        return tuple(self.events)


def detect_numpy(rule, timeline: ConditionTimeline, *, batch_rows=65536):
    """真实逐批NumPy检测完整条件轴，跨batch保存run/边沿。

    参数: rule/timeline以及正原生int batch_rows。
    返回: 稳定Event tuple；不是把reference包在NumPy入口。
    异常: TypeError/ValueError为配置/批大小/模型，检测错误传播。
    """
    # 实际timeline及可检查批大小，拒绝bool或无类型dict。
    if not isinstance(timeline, ConditionTimeline) or type(batch_rows) is not int or batch_rows <= 0:
        # 不截断余组或丢数据。
        raise TypeError('detect需timeline及正int batch_rows')
    # 单一当前会话实例，整个输入周期共享状态。
    detector = NumpyTemporalDetector(rule, timeline.start_ns, timeline.end_ns, timeline.source_refs)
    # 循环维度是batch，批内使用真正run/边沿向量掩码。
    for start in range(0, len(timeline.ticks), batch_rows):
        # batch末没有finish/reset，候选保留。
        detector.push(timeline.ticks[start:start+batch_rows])
    # 唯一真实terminal组之后才能收齐结果。
    return detector.finish()
