"""从封存信号历史逐窗计算变化量，交付已有点事件模型。

每次只执行一个规则，复用HistoricalWindowReplay的有限ZOH及两后端表达式查询。
新更新和旧边界移出窗口都推进判断；只保存当前窗口片段，内存不足明确失败。
数值核输出条件，独立边沿检测器负责初始化和重触发；once仅抑制后续事件，
不会把仍成立的条件伪装成FALSE。自有回读、当前帧、片段及事件批均计预算；
编译树、原历史和实际绑定借用。调用方必须close，不重读或修改原始来源。
"""

from collections import deque
from dataclasses import replace
from ..core.models import SourceRef
from ..core.temporal import ConditionTick, TemporalRule
from ..core.types import QualityFlag as Q, Truth
from ..core.window_delta import DeltaSpan
from ..core.window_delta_reference import window_delta_reference
from ..core.window_delta_numpy import window_delta_numpy
from ..results.errors import ResultClosedError
from ..results.spool import _cleanup_owner, _reserve_owned_ram, _release_owned_ram
from .history import _metadata_bytes
from .temporal_buffer import BudgetedTemporalDetector
from .window_replay import HistoricalWindowReplay


class WindowDeltaEvents:
    """拥有一个规则的滑动片段与事件批，失败后只能关闭；关闭可重试。"""

    def __init__(self, history, context, bindings, plan, compiled_rules, scopes=None):
        """保存借用合同并预约有限元数据，延迟打开第一条规则的回读。

        参数: 历史/context/绑定/计划，compiled_rules为(规则,实际表达式)tuple，scopes实际范围。
        返回: Event迭代owner。异常: 预算或取消，持续清理失败附window_delta_events_cleanup_owner。
        """
        self._budget, self._held_cost = history.budget, 0
        self._fixed_cost = self._buffer_cost = self._work_cost = 0
        self._history, self._context, self._bindings, self._plan = history, context, bindings, plan
        self._rules, self._scopes, self._index = compiled_rules, scopes, 0
        self._replay = self._frame = self._detector = self._batch = None
        self._spans = self._entry = self._compiled = self._domain = None
        self._query_time = None
        self._emitted = self._closed = self._failed = self._done = False
        try:
            _reserve_owned_ram(self, 65536 + 16 * _metadata_bytes(tuple(item[0] for item in compiled_rules)), '_fixed_cost')
            self._spans = deque()
        except BaseException as exc:
            _cleanup_owner(self, exc, 'window_delta_events_cleanup_owner', '窗口变化量构造')
            raise

    def __iter__(self):
        """返回本游标。参数: 无。返回: self。异常: 无。"""
        return self

    def _start_rule(self):
        """在上一规则资源关闭后打开下一有效观测范围。

        参数: 无。返回: bool表示已创建规则。异常: 构造、预算和实际范围错误。
        """
        while self._index < len(self._rules):
            self._entry, self._compiled = self._rules[self._index]
            self._index += 1
            self._domain = (self._context.domain if self._scopes is None else
                            self._scopes.for_dependencies(self._compiled.dependencies).actual)
            if self._domain is None:
                continue
            # 原样借用已检查表达式，点事件规则保留原计划ID；参数在plan中追溯。
            rule = TemporalRule(self._entry.rule_id, self._plan.dataset.dataset_id,
                                self._context.session_id, 'rising_edge', emit_initial=self._entry.emit_initial)
            refs = tuple(dict.fromkeys(SourceRef(self._context.session_id,
                self._bindings.resolve(name).source, self._bindings.resolve(name).field)
                for name in self._compiled.dependencies))
            self._detector = BudgetedTemporalDetector(self._budget, rule, self._domain.start_ns,
                self._domain.end_ns, refs, self._plan.execution.backend)
            self._replay = HistoricalWindowReplay(self._history, self._context, self._bindings, self._compiled,
                                       self._domain, backend=self._plan.execution.backend)
            self._emitted = False
            return True
        return False

    def _capture_value(self, result):
        """从一个已计账表达式视图取原生数值及质量。

        参数: result为参考或数组结果。返回: (value,quality)。异常: 上游结构错误。
        """
        if self._plan.execution.backend == 'reference':
            value = result.rows[0].value
            return (value.value if value.valid else None), value.quality
        value = result.arrays.value
        return (value.values[0].item() if value.valid[0] else None), Q(int(value.quality[0]))

    def _capture_frame(self):
        """预付当前片段，再保存点值与右侧有效性；不复制输入样本。

        参数: 无，使用自有当前frame。返回: None。异常: 预算、类型和上游错误。
        """
        _reserve_owned_ram(self, 2048, '_buffer_cost')
        value, point_quality = self._capture_value(self._frame.point_result)
        continuous = self._frame.continuous_result
        quality = Q.MISSING if continuous is None else self._capture_value(continuous)[1]
        self._spans.append(DeltaSpan(self._frame.time_ns, self._frame.end_ns,
                                     value, quality, point_quality))
        self._query_time = self._frame.time_ns

    def _evaluate(self):
        """计算当前窗口并推进独立边沿状态，最多借出一个事件。

        参数: 无。返回: Event或None，借至下一次迭代/关闭。异常: 数值契约、预算或取消。
        """
        time_ns, spec = self._query_time, self._entry.window_delta
        left = time_ns - spec.window_ns
        # 边界已离开窗口才移除；左端恰好等于旧起点时仍保留该点。
        while self._spans and self._spans[0].end_ns <= left and self._spans[0].start_ns < left:
            self._spans.popleft()
            _release_owned_ram(self, 2048, '_buffer_cost')
        _reserve_owned_ram(self, 65536 + 4096 * len(self._spans), '_work_cost')
        try:
            spans = tuple(self._spans)
            kernel = window_delta_reference if self._plan.execution.backend == 'reference' else window_delta_numpy
            point = kernel(spec, spans, time_ns, self._compiled.root.dtype)
            continuous = point
            terminal = time_ns == self._domain.end_ns
            # EOF真实点可以有效，右侧不能延长；其他点/连续差异也分别保留。
            if terminal:
                state, quality = Truth.UNKNOWN, Q.MISSING
            else:
                if spans[-1].start_ns == time_ns and spans[-1].point_quality != spans[-1].quality:
                    continuous = kernel(spec, spans[:-1] + (replace(spans[-1], point_quality=spans[-1].quality),),
                                        time_ns, self._compiled.root.dtype)
                state, quality = continuous.condition, continuous.quality
            tick = ConditionTick(time_ns, state, quality, actual_update=True, terminal=terminal,
                                 point_state=point.condition, point_quality=point.quality)
            # 窗口边界移动也是新条件证据，必须在该时刻识别边沿，不等下一条报文。
            self._batch = self._detector.push((tick,))
            event = self._batch.events[0] if self._batch.events else None
            if self._entry.retrigger == 'once' and self._emitted:
                event = None
            if event is not None:
                self._emitted = True
            # 当前源片段结束处由下一帧先提交实际更新，再判断同刻窗口。
            following = self._frame.end_ns
            for item in self._spans:
                shifted = item.start_ns + spec.window_ns
                if time_ns < shifted < following:
                    following = shifted
            self._query_time = following if time_ns < following < self._frame.end_ns else None
            return event
        finally:
            # 暂存tuple/数组只活在这次计算；事件由_batch独立计账。
            spans = point = continuous = tick = None
            _release_owned_ram(self, self._work_cost, '_work_cost')

    def __next__(self):
        """逐帧或窗口边界推进直到有事件，跨输入批次保留当前窗口。

        参数: 无。返回: Event。异常: StopIteration正常结束；失败后需close。
        """
        if self._closed or self._failed:
            raise ResultClosedError('窗口变化量已关闭或失败')
        if self._done:
            raise StopIteration
        try:
            while True:
                if self._batch is not None:
                    self._batch.close()
                    self._batch = None
                if self._replay is None and not self._start_rule():
                    self._done = True
                    break
                if self._query_time is None:
                    if self._frame is not None:
                        self._frame.close()
                        self._frame = None
                    self._frame = next(self._replay, None)
                    if self._frame is None:
                        self._batch = self._detector.finish()
                        self._close_rule()
                        continue
                    self._capture_frame()
                event = self._evaluate()
                if event is not None:
                    return event
        except BaseException as exc:
            self._failed = True
            # 深层构造没有返回时，接住它交出的真实owner，不丢清理责任。
            for slot, name in (('_replay', 'window_replay_cleanup_owner'),
                               ('_detector', 'temporal_detector_cleanup_owner')):
                child = getattr(exc, name, None)
                if child is not None and getattr(self, slot) is None:
                    setattr(self, slot, child)
            exc.window_delta_events_cleanup_owner = self
            raise
        raise StopIteration

    def _close_rule(self):
        """关闭本规则自有资源并释放窗口存储，成功后才清owner槽。

        参数: 无。返回: None。异常: 子关闭或预算取消，可再次调用。
        """
        for name in ('_batch', '_frame', '_replay', '_detector'):
            child = getattr(self, name)
            if child is not None:
                child.close()
                setattr(self, name, None)
        if self._spans is not None:
            self._spans.clear()
        _release_owned_ram(self, self._buffer_cost, '_buffer_cost')
        _release_owned_ram(self, self._work_cost, '_work_cost')
        self._query_time = None

    def close(self):
        """释放全部自有资源，保留原历史/绑定；关闭失败可重试。

        参数: 无。返回: None，幂等。异常: 子层或账本清理错误。
        """
        if self._closed:
            return
        self._close_rule()
        self._spans = self._rules = self._entry = self._compiled = self._domain = None
        self._history = self._context = self._bindings = self._plan = self._scopes = None
        _release_owned_ram(self, self._fixed_cost, '_fixed_cost')
        self._closed = self._held_cost == 0
