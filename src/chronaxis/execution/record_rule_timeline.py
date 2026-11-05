"""用最新必要信号在线推进一条规则，不保存输入历史或第二时间轴。

只暂留一个完整条件组，等下一组或真实EOF确定其是否为末点。实际模式调度
必要TTL和规则截止；记录周期模式只在选定驱动更新时增加等待量。输出直接
交调用方结果消费者，输入/共享状态和结果仓不归本对象所有。
"""

from dataclasses import replace
from ..core.temporal import ConditionTick, TemporalRule
from ..core.types import Truth as T, QualityFlag as Q
from ..results.errors import ResultClosedError
from ..results.spool import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from .driver_expression import DriverExpression
from .temporal_buffer import BudgetedTemporalDetector
from .history import _metadata_bytes
from .record_alarm_duration import RecordAlarmDuration
from .record_delta_condition import RecordDeltaCondition


class RecordRuleTimeline:
    """拥有规则表达式、检测器和一个待定条件组；原始组由父会话原子提交。"""

    def __init__(self,plan,request,state,budget,step_ns,driver,observation_ends,consumer,step_consumer=None):
        """建立有限声明，不读来源，也不把请求域当作已观测范围。

        参数: plan/request同计划规则、state共享最新值、budget共享预算、step_ns
            为None或周期，driver为所选别名，observation_ends借用EOF终点，consumer接事件。
        返回: 新owner。异常: 原构造错误附record_rule_cleanup_owner。
        """
        self._plan,self._request,self._state,self._budget=plan,request,state,budget
        self._step,self._driver,self._ends,self._consumer=step_ns,driver,observation_ends,consumer
        self._step_consumer=step_consumer
        self._held_cost=self._fixed_cost=0
        self._expressions=[]
        self._detector=self._pending_owner=self._batch=None
        self._alarm=self._delta=None
        self._delta_emitted=False
        # 常量大小的业务概况，不保留条件轨迹；关闭仍由原固定预算负责。
        self._seen_true=self._seen_false=self._seen_unknown=False
        # 仅对象计数请求需要发现缺口的原因，并忽略EOF人为封口的UNKNOWN状态。
        self._count_quality = Q.NONE
        self._track_count = any(c.count_target == request.rule_id for c in plan.calculations
                                if c.operation in ('point_event_count', 'activity_count')) or any(
            w.event == request.rule_id and any(c.operation == 'segment_count' and c.count_target == w.window_id
                                               for c in plan.calculations) for w in plan.windows)
        self._event_count=0
        if plan.aggregations and not self._track_count:
            from .result_aggregations import discovery_rules
            self._track_count=any(request.rule_id in discovery_rules(plan,agg) for agg in plan.aggregations)
        self._required_aliases=set()
        self._pending=None
        self._next_expiry=self._last_driver=None
        self._start=None
        self._end=plan.dataset.domain.end_ns
        self._full_domain=not plan.dataset.domain_explicit
        self._closed=self._closing=self._failed=self._finished=False
        try:
            _reserve_owned_ram(self,131584+32*_metadata_bytes(request),'_fixed_cost')
            for expression in request.expressions:
                try:
                    owner=DriverExpression(expression,state,None,backend=plan.execution.backend,
                        derived=tuple(item.definition for item in plan.derived),observation_ends=observation_ends)
                except BaseException as error:
                    self._pending_owner=getattr(error,'driver_expression_cleanup_owner',None)
                    raise
                self._expressions.append(owner)
                if not owner._has_where:
                    self._required_aliases.update(expression.dependencies)
            if request.rule_type=='window_delta':
                try:
                    self._delta=RecordDeltaCondition(budget,request.window_delta,
                        request.condition.root.dtype,plan.execution.backend,step_ns)
                except BaseException as error:
                    self._delta=getattr(error,'record_delta_cleanup_owner',None)
                    raise
            from ..planning.transforms import physical_dependencies
            names=physical_dependencies(plan,set(request.dependencies)|({driver} if driver else set()))
            self.sources=frozenset(state.definitions[name].source for name in names)
            if not self.sources:
                self.sources=frozenset(source.name for source in plan.sources)
            if request.stability is not None and request.stability.track_duration:
                try:
                    self._alarm=RecordAlarmDuration(budget,step_ns,plan.execution.backend,plan.dataset.domain)
                except BaseException as error:
                    self._alarm=getattr(error,'record_alarm_cleanup_owner',None)
                    raise
        except BaseException as error:
            _cleanup_owner(self,error,'record_rule_cleanup_owner','在线规则构造')
            raise

    def extend_observation(self, end_ns):
        """更新单遍读取已见的末端；最后条件组仍等待后继或EOF。参数: 实际末端。返回: None。异常: 回退。"""
        if not self._full_domain or self._finished:
            return
        self._end=end_ns
        if self._detector is not None:
            self._detector.extend_observed_end(end_ns)
        if self._alarm is not None:
            self._alarm._window=self._plan.dataset.domain

    def _open(self):
        """拒绝失效实例。参数: 无。返回: None。异常: ResultClosedError。"""
        if self._closed or self._closing or self._failed:
            raise ResultClosedError('在线规则已关闭或失败')

    def begin(self,observed_start):
        """用实际观察起点建立检测器，空来源由父跳过。

        参数: observed_start实际首端。返回: None。异常: 构造/范围错误附可清理owner。
        """
        self._open()
        if self._start is not None:
            raise ValueError('在线规则不能重复开始')
        start=max(observed_start,self._plan.dataset.domain.start_ns)
        if start>self._end:
            self._finished=True
            return
        request=self._request
        rule=TemporalRule(request.rule_id,self._plan.dataset.dataset_id,self._plan.dataset.session_id,
            request.temporal_rule_type,request.minimum_duration_ns or 0,request.emit_initial,request.window_duration_ns or 0,
            duration_comparison=request.duration_comparison)
        try:
            self._detector=BudgetedTemporalDetector(self._budget,rule,start,self._end,
                backend=self._plan.execution.backend,
                stability=replace(request.stability,track_duration=False) if self._alarm is not None else request.stability,
                start_end=request.start_end,
                record_clock=self._step is not None)
            self._start=start
        except BaseException as error:
            self._detector=getattr(error,'temporal_detector_cleanup_owner',None)
            self._failed=True
            error.record_rule_cleanup_owner=self
            raise

    def _snapshot(self,time_ns,actual,terminal=False):
        """收齐进出条件的点/右侧值，保一个必要组。参数: 实际时间/更新/EOF。返回: None。异常: 求值原错。"""
        ticks=[]
        deadlines=[]
        selected=self._state.get(self._driver) if self._driver else None
        is_driver=actual and selected is not None and selected.time_ns==time_ns
        for expression in self._expressions:
            evidence=self._required_aliases if expression._has_where else None
            point,_=expression.evaluate_at(time_ns,continuous=False,unobserved=evidence)
            right,deadline=expression.evaluate_at(time_ns,unobserved=evidence if not terminal else None)
            if self._delta is not None:
                point,right=self._delta.update(time_ns,point,right,deadline,driver=is_driver)
                deadline=self._delta.next_deadline
            point_state=T.TRUE if point.valid and point.value else T.FALSE if point.valid else T.UNKNOWN
            right_state=T.TRUE if right.valid and right.value else T.FALSE if right.valid else T.UNKNOWN
            point_quality=Q.NONE if point.valid else point.quality
            quality=Q.NONE if right.valid else right.quality
            observed_end=any(self._ends.get(source)==time_ns for source in self.sources)
            if observed_end and expression._has_where:
                observed_end=expression.active_end_at(time_ns)
            updated=self._delta is not None or (actual and expression.actual_update_at(time_ns))
            actual_unknown=updated and not point.valid
            if actual_unknown and expression._has_where and self._delta is None:
                actual_unknown=expression.actual_unknown_at(time_ns,point)
            ticks.append(ConditionTick(time_ns,T.UNKNOWN if terminal else right_state,
                quality|Q.MISSING if terminal else quality,actual_update=updated,
                observation_end=observed_end,terminal=terminal,point_state=point_state,point_quality=point_quality,
                actual_unknown=actual_unknown,diagnostic_quality=point.quality|right.quality|
                (Q.ESTIMATED if point.partial or right.partial and not terminal else Q.NONE)))
            if deadline is not None:
                deadlines.append(deadline)
        advance=None
        is_driver=False
        if self._step is not None:
            selected=self._state.get(self._driver)
            is_driver=actual and selected is not None and selected.time_ns==time_ns
            advance=self._step if is_driver and self._last_driver is not None else 0
            if is_driver:
                self._last_driver=time_ns
        self._pending=(tuple(ticks),advance,is_driver)
        self._next_expiry=min(deadlines) if deadlines else None

    def _commit(self):
        """交付一个完整条件组和增量事件，消费失败不返回前缀。参数: 无。返回: None。异常: 原错。"""
        ticks,advance,driver=self._pending
        self._batch=self._detector.push((ticks[0],),None if len(ticks)==1 else (ticks[1],),
            advances=None if advance is None else (advance,))
        events=self._batch.events
        if self._delta is not None and self._request.retrigger=='once':
            if self._delta_emitted:
                events=()
            elif events:
                self._delta_emitted=True
        # 真实末点可以说明当时条件，但EOF人为补出的UNKNOWN不算数据缺口。
        tick=ticks[0]
        truths=(tick.point_state,) if tick.terminal else (tick.state,tick.point_state)
        self._seen_true |= T.TRUE in truths
        if self._track_count:
            for item in ticks:
                self._count_quality |= item.diagnostic_quality & Q.ESTIMATED
            for item in ticks:
                if item.point_state == T.UNKNOWN:
                    self._count_quality |= item.point_quality
                if not item.terminal and item.state == T.UNKNOWN:
                    self._count_quality |= item.quality
        self._seen_false |= T.FALSE in truths
        self._seen_unknown |= any(T.UNKNOWN in ((item.point_state,) if item.terminal
                                  else (item.state,item.point_state)) for item in ticks)
        self._event_count += len(events)
        primary=None
        try:
            if self._alarm is not None:
                state=T.UNKNOWN if ticks[0].terminal else self._detector._detector.state
                self._alarm.consume(ticks[0].time_ns,state)
            if self._step_consumer is not None:
                self._step_consumer(self._request.rule_id,ticks[0],events)
            for event in events:
                self._consumer(event)
        except BaseException as error:
            primary=error
            raise
        finally:
            event=ticks=None
            try:
                self._batch.close()
                self._batch=None
            except BaseException as cleanup:
                if primary is None:
                    raise
                primary.add_note('规则输出批清理失败：'+type(cleanup).__name__)
        self._pending=None

    def _drain_before(self,time_ns):
        """只推进已经由后续观测证明存在的区间。参数: 下个实际边界。返回: None。异常: 原推进错。"""
        if self._pending is None and self._detector._detector.last_time is None and self._start<time_ns:
            self._snapshot(self._start,False)
        while True:
            if self._pending is not None:
                if self._pending[0][0].time_ns>=time_ns:
                    return
                self._commit()
            next_times=[value for value in (self._next_expiry,self._detector.next_deadline_ns) if value is not None]
            if not next_times or min(next_times)>=time_ns:
                return
            self._snapshot(min(next_times),False)

    def before_group(self,time_ns):
        """父提交新组前处理旧状态上的TTL和实际等待。参数: 新组时间。返回: None。异常: 原错。"""
        self._open()
        if self._finished or self._start is None or time_ns<self._start:
            return
        try:
            if time_ns>self._end:
                self.finish(self._end)
            else:
                self._drain_before(time_ns)
        except BaseException as error:
            self._failed=True
            error.record_rule_cleanup_owner=self
            raise

    def after_group(self,time_ns):
        """父原子提交后保存新条件组；实际终点在同刻更新之后结算。

        参数: 新组时间。返回: None。异常: 原求值/事件错误，失败只能关闭。
        """
        self._open()
        if self._finished or self._start is None or time_ns<self._start:
            return
        try:
            terminal=time_ns==self._end and not self._full_domain
            self._snapshot(time_ns,True,terminal=terminal)
            if terminal:
                self._commit()
                self._batch=self._detector.finish()
                self._batch.close();self._batch=None
                self._finished=True
        except BaseException as error:
            self._failed=True
            error.record_rule_cleanup_owner=self
            raise

    def clock_group(self,group):
        """待定旧条件已经交付后，接收报警累计所需的完整驱动对。

        参数: 新的真实同刻组。返回: None。异常: 累计顺序/预算错误。
        不改变事件坐标，也不把请求域外样本算入报警；只借它们确定裁剪分母。
        """
        if self._alarm is not None and self._step is not None and any(s.name==self._driver for s in group.samples):
            self._alarm.driver(group.time_ns)

    def finish(self,observed_end):
        """所有必要来源EOF后按真实末端封口，不外推到请求结束。

        参数: observed_end必要来源联合末端。返回: None。异常: 原错，未完成不发布结果。
        """
        self._open()
        if self._finished or self._start is None:
            return
        try:
            end=min(observed_end,self._end)
            if end<self._start:
                self._finished=True
                return
            self._detector.set_observed_end(end)
            self._end=end
            self._drain_before(end)
            if self._pending is not None and self._pending[0][0].time_ns==end:
                ticks,advance,driver=self._pending
                self._pending=(tuple(replace(t,terminal=True,state=T.UNKNOWN,quality=t.quality|Q.MISSING) for t in ticks),advance,driver)
            else:
                self._snapshot(end,False,terminal=True)
            self._commit()
            self._batch=self._detector.finish()
            self._batch.close();self._batch=None
            self._finished=True
        except BaseException as error:
            self._failed=True
            error.record_rule_cleanup_owner=self
            raise

    def outcome(self):
        """冻结规则结果原因，不读取输入。参数: 无。返回: RuleOutcome。异常: 未完成或已关闭。

        有事件时始终保留计数；缺信号和UNKNOWN不被解释成条件为假。
        """
        self._open()
        if not self._finished and self._start is not None:
            raise ValueError('规则未结束，不能报告结果概况')
        from ..results.analysis_outcome import RuleOutcome
        # 无观测只报告实际求值需要且一直没有观测的别名。静态绑定仍校验两个分支。
        missing=tuple(name for name in self._request.dependencies if self._state.get(name) is None
                      and (self._start is None or name in self._required_aliases))
        # 已产生的事件与未观测/未知事实并存；无事件时才用数据充分性解释原因。
        if self._event_count:
            status='events_found'
        elif self._start is None or missing:
            status='no_observation'
        elif self._seen_unknown:
            status='insufficient_data'
        elif self._request.rule_type=='condition_duration' and self._seen_true:
            status='duration_not_met'
        elif not self._seen_true:
            status='condition_not_met'
        else:
            status='no_event'
        return RuleOutcome(self._request.rule_id,status,self._event_count,self._seen_unknown,missing)

    def count_evidence(self, domain):
        """判定规则实际观测是否覆盖整个目标会话，保留发现是否完整的证据。

        参数: domain为最终会话域。返回: 已观测、至少部分可判定、完整、质量位。
        异常: 规则尚未结束或已关闭时沿outcome检查传播。
        """
        outcome = self.outcome()
        observed = self._start is not None and outcome.status != 'no_observation'
        known = self._seen_true or self._seen_false
        # 已确认的末点可以产生点事件；显式请求域超出来源实际首末时仍有缺口。
        covers_request = (observed and domain is not None
                          and self._start <= domain.start_ns and self._end >= domain.end_ns)
        complete = covers_request and not self._seen_unknown and not outcome.unobserved_signals and not self._count_quality & Q.ESTIMATED
        quality = self._count_quality
        if not covers_request or outcome.unobserved_signals:
            quality |= Q.MISSING
        return observed, known, complete, quality

    @property
    def duration_result(self):
        """借出明确请求的最终累计；空来源返回无观测。参数: 无。返回: tuple或None。异常: 未完成错误。"""
        if self._alarm is None:
            return None
        if not self._finished and self._start is not None:
            raise ValueError('报警尚未完成')
        return self._alarm.finish()

    @property
    def closed(self):
        """返回资源关闭状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    def close(self):
        """释放自有批、表达式和检测器，保留失败槽供重试。参数: 无。返回: None。异常: 原关闭错。"""
        if self._closed:
            return
        self._closing=True
        for slot in ('_batch','_pending_owner','_detector','_alarm','_delta'):
            owner=getattr(self,slot)
            if owner is not None:
                owner.close()
                setattr(self,slot,None)
        for index,owner in enumerate(self._expressions):
            if owner is not None:
                owner.close();self._expressions[index]=None
        self._pending=self._consumer=self._step_consumer=self._state=self._plan=self._ends=self._required_aliases=None
        _release_owned_ram(self,self._fixed_cost,'_fixed_cost')
        self._closed=True
