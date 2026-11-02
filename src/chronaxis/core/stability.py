"""把进入/退出条件转换为带迟滞和双向防抖的活动。

输入为同一会话、同一时刻的两组ConditionTick和非负纳秒防抖时长。
先结算此前已持续满足的条件，再处理当前更新；中间区间保持已确定状态，
UNKNOWN清除候选和此前状态。普通批次/文件边界不参与状态重置。
输出沿用活动Event，起点等于实际进入确认时刻；退出等待期间仍属于活动。
本模块仅实现有序状态转换，活动组装委托既有独立参考/NumPy检测器；
不声称状态循环是数值数组化，不读取文件，也不保存全量信号历史。
"""

from dataclasses import dataclass, replace
from .temporal import ConditionTick
from .temporal_reference import ReferenceTemporalDetector, require_batch, require_detector
from .types import QualityFlag as Q, Truth
from ..timebase.conversion import require_int64_ns


@dataclass(frozen=True)
class StabilitySpec:
    """保存进入和退出的独立等待时长；0表示条件满足即可转换。

    状态属于运行实例，本声明不保存已报警标志或候选计时。
    """

    enter_ns: int = 0  # 进入条件连续满足多久才切换为活动。
    exit_ns: int = 0  # 退出条件连续满足多久才切换为非活动。
    track_duration: bool = False  # 仅显式需求累计，普通规则不增加逐步统计。

    def __post_init__(self):
        """拒绝负值、bool及超int64时长。参数: 无。返回: None。异常: 类型/范围错误。"""
        if type(self.track_duration) is not bool:
            raise TypeError('track_duration必须bool')
        for name in ('enter_ns', 'exit_ns'):
            value = require_int64_ns(getattr(self, name), name)
            if value < 0:
                raise ValueError('防抖时长不能为负')
            object.__setattr__(self, name, value)


def invert_tick(tick):
    """取得普通防抖条件的退出证据，UNKNOWN保留原原因。

    参数: tick为ConditionTick。返回: 点/连续状态分别取反的新证据。
    异常: TypeError为非ConditionTick；不修改输入。
    """
    if not isinstance(tick, ConditionTick):
        raise TypeError('防抖条件需要ConditionTick')
    opposite = {Truth.TRUE: Truth.FALSE, Truth.FALSE: Truth.TRUE, Truth.UNKNOWN: Truth.UNKNOWN}
    return replace(tick, state=opposite[tick.state], point_state=opposite[tick.point_state])


class StabilityDetector:
    """维护一个规则/会话的已确定状态、单个待转换候选及活动输出。

    未知起点不猜未报警；两条件都假时保持前态，二者同时为真则报告配置冲突。
    一个条件未知会中断活动；恢复时从未知开始重新确认，不能跨缺口累计防抖。
    每次push可有多组，只有真实terminal才能finish；drain只取走输出。
    """

    def __init__(self, rule, start_ns, end_ns, spec, source_refs=(), *, backend='reference', record_clock=False):
        """建立独立迟滞状态，复用零时长活动检测器。

        参数: rule为condition_duration=0规则；start_ns/end_ns为会话域；spec为StabilitySpec；
            source_refs为来源定位；backend为reference或numpy。
        返回: None；初始化实例状态。异常: 规则、域、类型或后端错误。
        """
        require_detector(rule, start_ns, end_ns, source_refs)
        if not isinstance(spec, StabilitySpec) or rule.rule_type != 'condition_duration' or rule.minimum_duration_ns != 0:
            raise ValueError('迟滞需要StabilitySpec及duration=0活动规则')
        if backend not in ('reference', 'numpy'):
            raise ValueError('迟滞后端需reference或numpy')
        # 参考入口不导入NumPy；两者共用状态转换协议，活动核独立执行。
        detector_type = ReferenceTemporalDetector
        if backend == 'numpy':
            from .temporal_numpy import NumpyTemporalDetector
            detector_type = NumpyTemporalDetector
        self.rule, self.spec = rule, spec
        self.start_ns, self.end_ns = int(start_ns), int(end_ns)
        self.state, self.quality = Truth.UNKNOWN, Q.MISSING
        self.pending, self.deadline = None, None
        self.record_clock, self.remaining = record_clock, 0
        self.last_time, self.ended, self.finished = None, False, False
        self._core = detector_type(rule, self.start_ns, self.end_ns, source_refs, record_clock=record_clock)
        # 固定三个整数/一个状态，不保存逐点轨迹或额外扫描。UNKNOWN时间不会算成未报警。
        self._duration_time, self._duration_state = self.start_ns, Truth.UNKNOWN
        self._active_ns = self._known_ns = 0

    def _push_core(self, tick, advance=None):
        """把已确认状态交给活动核，并按需累计左侧半开区间。

        参数: tick为状态转换后的证据，advance为记录模式本组累计量。返回: 原活动核Event tuple。
        异常: 原活动核校验错误；失败实例不能继续使用。
        """
        if self.spec.track_duration:
            duration = advance if self.record_clock else int(tick.time_ns) - self._duration_time
            if self._duration_state is not Truth.UNKNOWN:
                self._known_ns += duration
                if self._duration_state is Truth.TRUE:
                    self._active_ns += duration
            self._duration_time, self._duration_state = int(tick.time_ns), tick.state
        return self._core.push((tick,), advances=(advance,) if self.record_clock else None)

    @property
    def duration_counts(self):
        """读取完成后的已知报警/已知观测整数纳秒。

        参数: 无。返回: (active_ns,known_ns)或None（未请求统计）。
        异常: ValueError表示请求统计但尚未正常finish。
        """
        if not self.spec.track_duration:
            return None
        if not self.finished:
            raise ValueError('迟滞累计只能在finish后读取')
        return self._active_ns, self._known_ns

    @property
    def next_deadline_ns(self):
        """读取域内待转换时间。参数: 无。返回: int或None。异常: 无。

        加法使用Python整数，域外结果不转换为int64或回绕。
        """
        return self.deadline if not self.record_clock and self.deadline is not None and self.deadline <= self.end_ns else None

    @staticmethod
    def _target(enter, exit, quality):
        """区分明确方向、中间区间、未知与矛盾条件。

        参数: enter/exit为Truth；quality为两个条件原因并集。
        返回: Truth或None（中间区间）。异常: ValueError为同时满足进出条件。
        """
        if enter is Truth.TRUE and exit is Truth.TRUE:
            raise ValueError('迟滞进入和退出条件同时成立，请设置不重叠的条件')
        if enter is Truth.UNKNOWN or exit is Truth.UNKNOWN:
            return Truth.UNKNOWN
        if enter is Truth.TRUE:
            return Truth.TRUE
        if exit is Truth.TRUE:
            return Truth.FALSE
        return None

    def _settle(self):
        """兑现已持续达到门槛的转换。参数: 无。返回: None。异常: 无。"""
        self.state, self.quality = self.pending, Q.NONE
        self.pending, self.deadline = None, None
        self.remaining = 0

    def _point(self, target, quality):
        """判断当前点状态，不把零长度点累计到等待时间。

        参数: target为目标或None，quality为点原因。返回: (Truth,Q)。异常: 无。
        """
        if target is Truth.UNKNOWN:
            return Truth.UNKNOWN, quality
        if target is not None:
            delay = self.spec.enter_ns if target is Truth.TRUE else self.spec.exit_ns
            if delay == 0:
                return target, Q.NONE
        return self.state, self.quality

    def _continuous(self, target, quality, time_ns):
        """更新右侧持续状态和唯一候选，取消不连续的计时。

        参数: target为目标/None；quality为原因；time_ns为当前纳秒。
        返回: None，修改实例。异常: 无；超域deadline仅用于比较。
        """
        if target is Truth.UNKNOWN:
            self.state, self.quality = Truth.UNKNOWN, quality
            self.pending, self.deadline = None, None
        elif target is None or target is self.state:
            # 返回中间区间仍保留已确认状态，但未满时长的进/出请求撤销。
            self.pending, self.deadline = None, None
        else:
            delay = self.spec.enter_ns if target is Truth.TRUE else self.spec.exit_ns
            if delay == 0:
                self.state, self.quality = target, Q.NONE
                self.pending, self.deadline = None, None
            elif self.pending is not target:
                self.pending = target
                self.deadline = None if self.record_clock else time_ns + delay
                self.remaining = delay

    def push(self, ticks, exit_ticks=None, *, advances=None):
        """推进成对条件组，可在两次实际更新之间精确兑现防抖计时。

        参数: ticks为进入条件tuple；exit_ticks为同刻退出tuple，省略时为not进入；
            advances仅record_clock模式传入本组周期增量，无驱动边界为0。
        返回: 本次新Event tuple；活动起点为进入转换时刻，不回填等待区间。
        异常: 输入/顺序/同刻冲突/finish后推进错误；发生错误后调用方应丢弃实例。
        """
        if self.finished:
            raise ValueError('迟滞检测器已finish')
        require_batch(ticks, self.start_ns, self.end_ns, self.last_time, self.ended)
        from .temporal_clock import require_clock_advances
        require_clock_advances(ticks, advances, self.record_clock, self.last_time)
        if exit_ticks is None:
            exit_ticks = tuple(invert_tick(tick) for tick in ticks)
        require_batch(exit_ticks, self.start_ns, self.end_ns, self.last_time, self.ended)
        if len(ticks) != len(exit_ticks) or any(a.time_ns != b.time_ns for a, b in zip(ticks, exit_ticks)):
            raise ValueError('迟滞两个条件必须在相同的完整时间组求值')
        output = []
        for index, (enter, exit) in enumerate(zip(ticks, exit_ticks)):
            time_ns = int(enter.time_ns)
            advance = None if advances is None else advances[index]
            # 先结算前一个半开区间，即使当前点恰好变假或失效也不抹去已得时长。
            if self.record_clock and self.pending is not None:
                self.remaining = max(0, self.remaining - advance)
            settled = (self.pending is not None and self.remaining == 0 if self.record_clock
                       else self.deadline is not None and self.deadline <= time_ns)
            if settled:
                deadline = time_ns if self.record_clock else self.deadline
                self._settle()
                if deadline < time_ns:
                    output.extend(self._push_core(ConditionTick(deadline, self.state)))
            diagnostic = enter.diagnostic_quality | exit.diagnostic_quality | enter.quality | exit.quality
            diagnostic |= enter.point_quality | exit.point_quality
            point_quality = enter.point_quality | exit.point_quality
            point_target = self._target(enter.point_state, exit.point_state, point_quality)
            point_state, point_quality = self._point(point_target, point_quality)
            # 退出等待已在左侧完整满足；同刻EOF/失效不能把这个已知退出改成缺观测。
            if settled and self.state is Truth.FALSE and point_state is Truth.UNKNOWN:
                point_state, point_quality = Truth.FALSE, Q.NONE
            if enter.terminal:
                # 末点能解除旧活动，但不能开始新的正长度活动或假造末点后的保持。
                state, quality = Truth.UNKNOWN, enter.quality | exit.quality | Q.MISSING
                self.pending, self.deadline = None, None
            else:
                quality = enter.quality | exit.quality
                target = self._target(enter.state, exit.state, quality)
                self._continuous(target, quality, time_ns)
                state, quality = self.state, self.quality
            tick = ConditionTick(time_ns, state, quality,
                actual_update=enter.actual_update or exit.actual_update or settled,
                observation_end=enter.observation_end or exit.observation_end, terminal=enter.terminal,
                point_state=point_state, point_quality=point_quality,
                actual_unknown=(enter.actual_unknown or exit.actual_unknown) and point_state is Truth.UNKNOWN,
                diagnostic_quality=diagnostic)
            output.extend(self._push_core(tick, advance))
            self.last_time, self.ended = time_ns, enter.terminal
        return tuple(output)

    def drain_events(self):
        """取走最终活动而不清计时。参数: 无。返回: Event tuple。异常: 分配错误。"""
        return self._core.drain_events()

    def finish(self):
        """只在真实会话末尾封闭。参数: 无。返回: 未取走活动。异常: 缺terminal/重复。"""
        result = self._core.finish()
        self.finished = True
        return result
