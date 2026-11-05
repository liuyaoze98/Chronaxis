"""收齐同刻的请求、响应和条件后配对，直接交付最终结果。

只保留本次输入组之前的有限条件边界及尚待响应的请求。没有配对请求时不
建立本对象；不会为配对保存整段信号历史或另一时间轴。每个规则的观测终点
由其必要来源决定，响应来源提前结束只使后续响应未知，不提前结束其他来源。
"""

from ..planning.intervals import IntervalChoice
from dataclasses import replace
from ..core.sequence import SequenceRule, SequenceTick
from ..core.sequence_reference import SequenceDetector
from ..core.temporal import ConditionTick
from ..core.types import Truth as T, QualityFlag as Q
from ..results.errors import ResultClosedError, BudgetExceededError
from ..results.spool import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from .history import _metadata_bytes


class RecordSequences:
    """拥有同刻合并队列及FIFO候选；计划、状态和结果消费者为借用。"""

    def __init__(self,plan,state,budget,steps,consumer):
        """登记有限配对配置。参数: 计划、共享状态/预算、周期映射、结果回调。返回: owner。异常: 构造原错附owner。"""
        self._plan,self._state,self._budget,self._steps,self._consumer=plan,state,budget,steps,consumer
        self._held_cost=self._fixed_cost=self._queue_cost=self._pending_cost=self._step_cost=0
        self._queue,self._active,self._costs={},{},{}
        self._closed=self._failed=False
        self._rules={r.rule_id:r for r in plan.rules}
        self._needed={name for s in plan.sequences for name in (s.start_rule,s.response_rule)}
        try:
            _reserve_owned_ram(self,65536+32*_metadata_bytes(plan.sequences),'_fixed_cost')
        except BaseException as error:
            _cleanup_owner(self,error,'record_sequences_cleanup_owner','在线配对构造')
            raise

    def _open(self):
        """拒绝失败实例。参数: 无。返回: None。异常: ResultClosedError。"""
        if self._closed or self._failed:
            raise ResultClosedError('在线配对已关闭或失败')

    def _entry(self,time_ns):
        """先付费再建立一组。参数: 实际时间。返回: 可变组。异常: 预算原错。"""
        if time_ns not in self._queue:
            _reserve_owned_ram(self,8192,'_queue_cost')
            self._queue[time_ns]=[{},set(),8192]
        return self._queue[time_ns]

    def bounds(self,cursors,ends):
        """从真实来源范围开始/收窄配对域，在末组交付之前调用。

        参数: 已前瞻的来源和确认EOF终点。返回: None。异常: 范围/预算错误。
        """
        self._open()
        choices=dict(self._plan.intervals.resolved)
        for spec in self._plan.sequences:
            names=set(self._rules[spec.start_rule].dependencies)|set(self._rules[spec.response_rule].dependencies)
            driver=choices[spec.sequence_id].driver
            if driver:
                names.add(driver)
            from ..planning.transforms import physical_dependencies
            sources={self._state.definitions[name].source for name in physical_dependencies(self._plan,names)}
            if any(not self._rules[name].dependencies and choices.get(name,IntervalChoice('actual')).driver is None
                   for name in (spec.start_rule,spec.response_rule)):
                sources.update(source.name for source in self._plan.sources)
            starts=[c.observed_start for c in cursors if c.source_name in sources and c.observed_start is not None]
            if not starts:
                continue
            start=max(min(starts),self._plan.dataset.domain.start_ns)
            end=self._plan.dataset.domain.end_ns
            finished={c.source_name for c in cursors if c._finished}
            final=bool(sources) and sources<=finished
            if final:
                end=min(end,max(ends[source] for source in sources if source in ends))
            if start>end:
                continue
            if spec.sequence_id not in self._active:
                rule=SequenceRule(spec.sequence_id,self._plan.dataset.dataset_id,self._plan.dataset.session_id,
                    spec.start_rule,spec.response_rule,spec.min_delay_ns,spec.max_delay_ns,
                    self._plan.dataset.entity,record_clock=self._steps[spec.sequence_id] is not None)
                detector=SequenceDetector(rule,start,end,max_pending=spec.max_pending)
                self._active[spec.sequence_id]=[spec,detector,None,False,False]
                self._entry(start)
            detector=self._active[spec.sequence_id][1]
            if not self._plan.dataset.domain_explicit and not detector._ended:
                detector.end_ns=end
            if final and not detector._ended:
                if detector._last_time is not None and end<=detector._last_time:
                    raise ValueError('配对末组已提交，不能回退观测范围')
                detector.end_ns=end
                self._entry(end)

    def observe(self,rule,tick,events):
        """借用规则批时先付费再保留必要点，不保存不参与配对的规则。

        参数: 规则ID、条件点及事件tuple。返回: None。异常: 预算/重复点错误。
        """
        self._open()
        if rule not in self._needed:
            return
        entry=self._entry(tick.time_ns)
        if rule in entry[0]:
            raise ValueError('配对收到重复规则时间组')
        cost=8192+16*_metadata_bytes(events)
        _reserve_owned_ram(self,cost,'_queue_cost')
        entry[2]+=cost
        entry[0][rule]=(tick,events)

    def drivers(self,group):
        """仅记录配对实际需要的驱动更新身份。参数: 完整原始组。返回: None。异常: 预算错误。"""
        self._open()
        names={choice.driver for name,choice in self._plan.intervals.resolved
               if name in self._steps and choice.driver is not None}
        selected={sample.name for sample in group.samples}&names
        if selected:
            self._entry(group.time_ns)[1].update(selected)

    def _consume(self,time_ns,entry,active):
        """一次提交同刻A/B，候选到结果交付完毕才退费。参数: 时间/组/检测状态。返回: None。异常: 原计算错。"""
        spec,detector,last,seen,finished=active
        if finished or not detector.start_ns<=time_ns<=detector.end_ns:
            return
        a=entry[0].get(spec.start_rule)
        b=entry[0].get(spec.response_rule)
        if b is not None:
            condition=b[0]
        elif last is None:
            condition=ConditionTick(time_ns,T.UNKNOWN,Q.MISSING)
        else:
            condition=ConditionTick(time_ns,last.state,last.quality)
        terminal=time_ns==detector.end_ns
        condition=replace(condition,terminal=terminal,
            state=T.UNKNOWN if terminal else condition.state,
            quality=condition.quality|Q.MISSING if terminal else condition.quality)
        starts=() if a is None else a[1]
        responses=() if b is None else b[1]
        _reserve_owned_ram(self,16384+16*_metadata_bytes(responses),'_step_cost')
        for event in starts:
            cost=32768+16*_metadata_bytes((event,detector.rule))
            _reserve_owned_ram(self,cost,'_pending_cost')
            self._costs[(spec.sequence_id,event.event_id)]=cost
        step=self._steps[spec.sequence_id]
        choice=dict(self._plan.intervals.resolved)[spec.sequence_id]
        selected=choice.driver in entry[1]
        advance=step if selected and seen else 0
        active[3]=seen or selected
        try:
            results=detector.push((SequenceTick(condition,starts,responses),),
                advances=None if step is None else (advance,))
        except MemoryError as error:
            raise BudgetExceededError('配对等待候选超过限制：'+spec.sequence_id) from error
        released=0
        for result in results:
            self._consumer(result)
            released+=self._costs.pop((spec.sequence_id,result.request.event_id))
        result=results=None
        _release_owned_ram(self,released,'_pending_cost')
        _release_owned_ram(self,self._step_cost,'_step_cost')
        active[2]=condition
        if terminal:
            detector.finish()
            active[4]=True

    def flush_before(self,before=None):
        """所有规则已交付边界后，按实际时间处理一次；None仅用于真实全体EOF。

        参数: 下一个尚未提交的实际组。返回: None。异常: 原错并封闭实例。
        """
        self._open()
        try:
            for time in sorted(self._queue):
                if before is not None and time>=before:
                    break
                entry=self._queue[time]
                for active in self._active.values():
                    self._consume(time,entry,active)
                cost=entry[2]
                del self._queue[time]
                entry=None
                _release_owned_ram(self,cost,'_queue_cost')
            if before is None and any(not active[4] for active in self._active.values()):
                raise ValueError('配对尚未收到实际终点')
        except BaseException as error:
            self._failed=True
            error.record_sequences_cleanup_owner=self
            raise

    @property
    def closed(self):
        """返回资源关闭状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    def close(self):
        """放弃未发布候选并退还自有费用。参数: 无。返回: None。异常: 预算释放原错可重试。"""
        if self._closed:
            return
        self._queue.clear();self._active.clear();self._costs.clear()
        self._plan=self._state=self._consumer=self._steps=self._rules=None
        for slot in ('_pending_cost','_step_cost','_queue_cost','_fixed_cost'):
            _release_owned_ram(self,getattr(self,slot),slot)
        self._closed=True
