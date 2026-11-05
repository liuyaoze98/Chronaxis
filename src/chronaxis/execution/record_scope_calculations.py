"""只对明确的事件指标保存必要计算值，并按事件真实范围回读。

同表达式、条件和驱动共享一份紧凑历史；每次查询复用已验证的记录积分/统计核。
窗口尚未确定前只接事件，默认会话统计不创建这个所有者。
"""
import heapq
from ..core.moments import SAMPLE_MOMENTS
from ..core.quantiles import SAMPLE_QUANTILES
from functools import partial as bind_consumer
from ..core.types import QualityFlag as Q
from dataclasses import replace
from ..core.models import Interval
from ..core.calculations import CalculationDefinition
from ..results.errors import ResultClosedError
from ..results.spool import _reserve_owned_ram,_release_owned_ram,_cleanup_owner
from .history import _metadata_bytes
from .driver_expression import DriverExpression
from .record_value_history import RecordValueHistory
from .record_integral import RecordIntegral
from .record_time_calculation import RecordTimeCalculation
from .record_selection import RecordSelection


class RecordScopeCalculations:
    """拥有必要表达式历史、等待右端的查询及当前统计器；计划/状态为借用。"""

    def __init__(self,plan,state,budget,path,steps,requests,ends,consumer,*,selection_consumer=None):
        """建立已请求的有限表达式分组。参数: 原计划/状态/预算/路径/周期/请求/EOF/回调。返回: owner。异常: 原构造错。"""
        self._plan,self._budget,self._path,self._consumer=plan,budget,path,consumer
        self._selection_consumer=selection_consumer
        self._requests,self._steps=requests,steps
        self._held_cost=self._fixed_cost=self._queue_cost=0
        self._streams,self._request_stream={},{}
        self._queue=[]
        self._serial=0
        self._pending=self._calculation=None
        self._calculators=[]
        self._closed=self._failed=False
        try:
            _reserve_owned_ram(self,131072+64*_metadata_bytes(requests),'_fixed_cost')
            choices=dict(plan.intervals.resolved)
            from ..planning.intervals import IntervalChoice
            self._hosted=plan.extensions.reductions if plan.extensions is not None else {}
            sample_ops=('sample_count','sample_minimum','sample_maximum','sample_mean','select', *SAMPLE_MOMENTS, *SAMPLE_QUANTILES,*self._hosted)
            for request in requests:
                if request.operation in sample_ops:choices[request.calculation_id]=IntervalChoice('actual')
            sample_keys={(r.signal.identity,None if r.condition is None else r.condition.identity,None)
                         for r in requests if r.operation in sample_ops}
            for request in requests:
                expression=request.signal if request.signal is not None else request.condition
                condition=request.condition if request.signal is not None else None
                driver=choices[request.calculation_id].driver
                key=(expression.identity,None if condition is None else condition.identity,driver)
                self._request_stream[request.calculation_id]=key
                if key in self._streams:
                    continue
                self._streams[key]=[None,None,None,expression,condition,
                    driver is None and not expression.dependencies and (condition is None or not condition.dependencies)]
                stream=self._streams[key]
                for index,static in enumerate((expression,condition)):
                    if static is not None:
                        stream[index]=self._new(DriverExpression,'driver_expression_cleanup_owner',static,state,driver,
                            backend=plan.execution.backend,derived=tuple(item.definition for item in plan.derived),observation_ends=ends)
                stream[2]=self._new(RecordValueHistory,'record_value_history_cleanup_owner',
                    budget,path,expression.root.dtype,condition is not None,sample_updates=key in sample_keys,
                    labels=expression.root.labels)
        except BaseException as error:
            _cleanup_owner(self,error,'record_scope_calculations_cleanup_owner','事件指标构造')
            raise

    def _new(self,factory,recovery,*args,**kwargs):
        """接住未返回的实际子owner。参数: 工厂/恢复字段/构造参数。返回: owner。异常: 原错。"""
        try:
            return factory(*args,**kwargs)
        except BaseException as error:
            self._pending=getattr(error,recovery,None)
            raise

    def _open(self):
        """拒绝已失败/关闭的执行。参数: 无。返回: None。异常: ResultClosedError。"""
        if self._closed or self._failed:
            raise ResultClosedError('事件指标已关闭或失败')

    def observe_group(self):
        """完整组已原子提交，更新各必要表达式一次。参数: 无。返回: None。异常: 求值/写入/预算原错。"""
        self._open()
        for value,condition,history,_,__,constant in self._streams.values():
            if constant:
                continue
            row=value.evaluate()
            selected=None if condition is None else condition.evaluate()
            if value.invalidated_at is not None:
                history.expire_at(value.invalidated_at)
            if condition is not None and condition.invalidated_at is not None:
                history.expire_at(condition.invalidated_at,condition=True)
            if row is not None:
                if condition is not None and (selected is None or selected[0]!=row[0]):
                    raise ValueError('事件值和条件必须共用驱动')
                actual=history._sample_updates and value.actual_update_at(row[0])
                history.append(row,selected,actual_update=actual)
        self._flush()

    def observe_event(self,event):
        """仅保等待计算需要的父ID和真实端点，不复制事件全文。参数: 事件。返回: None。异常: 预算/计算原错。"""
        self._open()
        requests=tuple(request for request in self._requests if request.scope=='event:'+event.rule.rule_id)
        if requests:
            end=event.start_ns if event.end_ns is None else event.end_ns
            # 选择起点只裁统计范围；事件自身仍保留原活动开始、确认和结束。
            rule=next(item for item in self._plan.rules if item.rule_id==event.rule.rule_id)
            start=event.confirmed_ns if rule.selection_origin=='confirmed' else event.start_ns
            cost=8192+16*_metadata_bytes(event.event_id)+128*len(requests)
            _reserve_owned_ram(self,cost,'_queue_cost')
            heapq.heappush(self._queue,(end,self._serial,requests,event.event_id,start,cost,
                                        bool(event.dependency_quality & Q.ESTIMATED)))
            self._serial+=1
        self._flush()

    def observe_segment(self,segment):
        """EOF后按实际片段范围计算，缺失扩展不伪装完整。

        参数: 精简核心片段。返回: None。异常: 原查询错；空片段只返回无观测值。
        """
        self._open()
        requests=tuple(request for request in self._requests if request.scope=='segment:'+segment.window_id)
        if not requests:
            return
        actual=segment.actual
        start=self._plan.dataset.domain.start_ns if actual is None else actual.start_ns
        end=start if actual is None else actual.end_ns
        self._calculate(requests,segment.segment_id,start,end,partial=segment.status!='complete',
            parent_coverage=segment.coverage,estimated=bool(segment.quality & Q.ESTIMATED))

    def _calculate(self,requests,parent,start_ns,end_ns,*,partial=False,parent_coverage=None,estimated=False):
        """同范围、同表达式的相邻指标共读一次；预算余量不足时缩为单项。

        参数: 原声明顺序的请求tuple/父ID/实际范围及覆盖。返回: None。异常: 原查询、预算或输出错误。
        不缓存整个范围；每次借一行同时交给有限计算器，仍按声明顺序发布。
        """
        from itertools import groupby
        for key,group in groupby(requests,key=lambda request:self._request_stream[request.calculation_id]):
            items=tuple(group)
            # 留出每项计算器和批数组的余量；所有真实分配仍由共享预算检查。
            available=self._budget.memory_budget_bytes-self._budget.ram_bytes
            width=max(1,min(8,available//(32*1024*1024)))
            for offset in range(0,len(items),width):
                chunk=items[offset:offset+width]
                self._calculate_chunk(key,chunk,parent,start_ns,end_ns,partial,parent_coverage,estimated)

    def _calculate_chunk(self,key,requests,parent,start_ns,end_ns,partial,parent_coverage,estimated):
        """建立有限计算器组并共享一次回读。参数: 流key/请求/范围/质量。返回: None。异常: 原错误保留owner。
        """
        history,expression,condition=self._streams[key][2:5]
        for request in requests:
            descriptor=self._hosted.get(request.operation)
            spec=CalculationDefinition(request.calculation_id,'sample_minimum' if descriptor else request.operation,Interval(start_ns,end_ns),request.partial_policy,
                            request.unit,request.scope.split(':',1)[0],request.minimum_coverage,config_version=self._plan.config_version, ddof=request.ddof, q=request.q)
            factory=RecordIntegral if request.operation=='integral' else RecordTimeCalculation
            recovery='record_integral_cleanup_owner' if request.operation=='integral' else 'record_time_cleanup_owner'
            extra={'work_dir':self._path} if request.operation=='time_weighted_mean' else {}
            if descriptor:
                extra={'hosted':descriptor}
            if request.operation=='select':
                factory,recovery=RecordSelection,'record_selection_cleanup_owner'
                extra={'consumer':bind_consumer(self._selection_consumer,request,parent)}
                if estimated:
                    extra['consumer']=bind_consumer(self._estimated_selection,request,parent)
            self._calculation=self._new(factory,recovery,self._budget,spec,expression.root.unit,expression.root.dtype,
                self._steps[request.calculation_id],backend=self._plan.execution.backend,
                batch_intervals=min(self._plan.execution.batch_rows,4096),conditioned=condition is not None,
                **extra)
            self._calculators.append(self._calculation);self._calculation=None
        for point in history.rows(start_ns,end_ns):
            time,value,deadline,selected,selected_end=point[:5]
            for calculation in self._calculators:
                calculation.consume(((time,value,deadline),),**({} if condition is None else
                    {'conditions':(selected,),'condition_valid_until_ns':(selected_end,)}),
                    **({'actual_value_updates':(point[5],)} if getattr(calculation,'_samples',False) else {}))
        for request,calculation in zip(requests,self._calculators):
            self._finish_observation_tail(key,calculation,end_ns)
            result=calculation.finish()
            if request.operation=='select':
                calculation.close()
                continue
            if estimated:
                from .transform_partial import partial_result
                result=partial_result(result,request.partial_policy)
            elif partial and result.value is not None:
                result=replace(result,value=None if request.partial_policy=='strict' else result.value,
                    status='indeterminate' if request.partial_policy=='strict' else 'partial',reason='partial_input')
            if request.scope.startswith('segment:') and request.minimum_coverage>0 and (
                    parent_coverage is None or parent_coverage<request.minimum_coverage):
                result=replace(result,coverage_status='indeterminate')
            self._consumer(request,parent,result)
            calculation.close()
        self._calculators.clear()

    def _estimated_selection(self,request,parent,row):
        """给部分父区间中的选中行标明估算。参数: 请求、父ID和行。返回: None。异常: 发布错误。"""
        from ..core.selection import partial_selection
        value,quality=partial_selection(row.value,row.quality,request)
        self._selection_consumer(request,parent,replace(row,value=value,quality=quality))

    def _finish_observation_tail(self,key,calculation,end_ns):
        """用真实来源终点补查询尾段，既不补固定周期也不增加真实样本。

        参数: key为共享表达式流，calculation为本次范围统计器，end_ns为查询右端。
        返回: None。异常: 表达式、预算或累计错误沿查询清理路径传播。
        只处理整个历史的最后一点；旧范围已有右邻点时绝不借用当前状态重新求值。
        """
        samples=getattr(calculation,'_samples',False)
        value,condition,history=self._streams[key][:3]
        if (not calculation._rows or not samples and calculation._step_ns is not None
                or calculation._last_time!=history.last_time or calculation._last_time>=end_ns):
            return
        sources={definition.source for expression in (value,condition) if expression is not None
                 for _,definition in expression._definitions}
        ends=value._observation_ends
        if not sources or ends is None or any(source not in ends for source in sources):
            return
        start=calculation._last_time
        end=min(end_ns,max(ends[source] for source in sources))
        if end<=start:
            return
        # 此点是整个流的最新相关更新；EOF已知后重新核对右侧保持，保留TTL及短路条件含义。
        current,deadline=value.evaluate_at(start)
        selected,condition_deadline=(None,None) if condition is None else condition.evaluate_at(start)
        if samples:
            previous=calculation._rows[-1]
            value_ends=tuple(t for t in (previous[2],deadline,start if not current.valid else None) if t is not None)
            condition_ends=tuple(t for t in (previous[4],condition_deadline,
                start if selected is not None and not selected.valid else None) if t is not None)
            calculation._rows[-1]=(start,previous[1],min(value_ends) if value_ends else None,
                previous[3],min(condition_ends) if condition_ends else None)+previous[5:]
        else:
            calculation._rows[-1]=(start,current,deadline,selected,condition_deadline)
        calculation.consume(((end,current,deadline),),
            **({'actual_value_updates':(False,)} if samples else {}),
            **({} if condition is None else
               {'conditions':(selected,),'condition_valid_until_ns':(condition_deadline,)}))

    def _flush(self,final=False):
        """右侧实际驱动到达才结算；EOF直接按已有点计算，不补周期。

        参数: final只在真实EOF时为True。返回: None。异常: 原查询错，未退费用由close清理。
        """
        pending=[]
        try:
            while self._queue:
                item=heapq.heappop(self._queue)
                end,_,requests,parent,start,cost,estimated=item
                histories=(self._streams[self._request_stream[request.calculation_id]][2] for request in requests)
                if not final and any(history.last_time is None or history.last_time<end for history in histories):
                    pending.append(item)
                    continue
                if estimated:
                    self._calculate(requests,parent,start,end,estimated=True)
                else:
                    self._calculate(requests,parent,start,end)
                item=None
                _release_owned_ram(self,cost,'_queue_cost')
        except BaseException:
            self._failed=True
            raise
        finally:
            for item in pending:
                heapq.heappush(self._queue,item)

    def finish(self,cursors):
        """来源全部完成后处理常量和剩余事件。参数: 实际来源游标。返回: None。异常: 原求值/计算错。"""
        self._open()
        starts=[c.observed_start for c in cursors if c.observed_start is not None]
        ends=[c.observed_end for c in cursors if c.observed_start is not None and c.observed_end is not None]
        if starts and ends:
            first,last=min(starts),max(ends)
            for value,condition,history,_,__,constant in self._streams.values():
                if constant:
                    result,_=value.evaluate_at(last)
                    selected=None if condition is None else condition.evaluate_at(last)[0]
                    for time in dict.fromkeys((first,last)):
                        history.append((time,result,None),None if condition is None else (time,selected,None))
        self._flush(final=True)

    @property
    def closed(self):
        """返回关闭事实。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    def close(self):
        """按责任关闭子资源，失败时保槽供重试。参数: 无。返回: None。异常: 原关闭错。"""
        if self._closed:
            return
        for slot in ('_pending','_calculation'):
            owner=getattr(self,slot)
            if owner is not None:
                owner.close()
                setattr(self,slot,None)
        for owner in self._calculators:
            owner.close()
        self._calculators.clear()
        for stream in self._streams.values():
            for index in range(3):
                if stream[index] is not None:
                    stream[index].close()
                    stream[index]=None
        self._streams.clear()
        self._queue.clear()
        self._requests=self._plan=self._consumer=self._request_stream=None
        _release_owned_ram(self,self._queue_cost,'_queue_cost')
        _release_owned_ram(self,self._fixed_cost,'_fixed_cost')
        self._closed=True
