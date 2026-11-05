"""按需计算每段事件的持续时长，只为周期模式保存必要驱动时间。

实际模式直接使用事件范围。固定/DBC需要知道事件两端落在哪对报文中，因而
保存每条所选驱动的一个整数时间；按索引二分定位，只回读相关记录对。该文件
没有数值、原帧或另一时间轴，未请求此类统计时不建立；关闭自动删除。
"""

import heapq
from ..core.models import Interval
from ..core.calculations import CalculationDefinition
from ..core.numeric import ScalarValue
from ..core.types import SignalDType as D,QualityFlag as Q
from ..results.errors import ResultClosedError
from ..results.spool import _reserve_owned_ram,_release_owned_ram,_cleanup_owner
from .record_time_calculation import RecordTimeCalculation
from .history import _metadata_bytes
from ..planning.record_execution import is_event_duration


class RecordEventDurations:
    """拥有必要时点文件、尚缺右端的事件及一个短生命周期数值查询。"""

    def __init__(self,plan,budget,work_dir,steps,consumer,*,indexes=None):
        """预付有限索引状态，不为actual创建文件。参数: 计划/预算/目录/周期/回调；indexes借用共享必要时点，不在此重复保存。返回: owner。异常: 原构造错误。"""
        self._plan,self._budget,self._path,self._steps,self._consumer=plan,budget,work_dir,steps,consumer
        self._requests=tuple(item for item in plan.calculations if is_event_duration(item))
        self._choices=dict(plan.intervals.resolved)
        self._held_cost=self._fixed_cost=self._pending_cost=0
        self._indexes=indexes
        self._queue=[]
        self._serial=0
        self._calculation=None
        self._closed=self._failed=False
        try:
            _reserve_owned_ram(self,131072+32768*len(self._requests)+32*_metadata_bytes(self._requests),'_fixed_cost')
        except BaseException as error:
            _cleanup_owner(self,error,'record_event_duration_cleanup_owner','事件时长构造')
            raise

    def _open(self):
        """拒绝关闭/失败实例。参数: 无。返回: None。异常: ResultClosedError。"""
        if self._closed or self._failed:
            raise ResultClosedError('事件时长已关闭或失败')

    def observe_group(self,group):
        """父已更新共享时点索引，尝试完成等待中的事件。参数: 完整组。返回: None。异常: 查询原错。"""
        self._open()
        self._flush_ready()

    def observe_event(self,event):
        """只为匹配事件建立必要查询，缺右端时暂存端点和ID。参数: 事件。返回: None。异常: 预算/求值原错。"""
        self._open()
        for request in self._requests:
            if request.scope!='event:'+event.rule.rule_id:
                continue
            end=event.start_ns if event.end_ns is None else event.end_ns
            # 快捷时长与一般事件计算使用同一选择范围；确认等于结束时保留空区间。
            rule=next(item for item in self._plan.rules if item.rule_id==event.rule.rule_id)
            start=event.confirmed_ns if rule.selection_origin=='confirmed' else event.start_ns
            cost=8192+16*_metadata_bytes(event.event_id)
            _reserve_owned_ram(self,cost,'_pending_cost')
            heapq.heappush(self._queue,(end,self._serial,request,event.event_id,start,cost,
                                        bool(event.dependency_quality & Q.ESTIMATED)))
            self._serial+=1
        self._flush_ready()

    def _calculate(self,request,event_id,start_ns,end_ns,estimated=False):
        """只借取事件两侧及区间内的驱动点，复用原两后端时长核。

        参数: 请求/父ID/真实端点。返回: None，结果交回调。异常: 构造/数值/发布原错。
        """
        step=self._steps[request.calculation_id]
        spec=CalculationDefinition(request.calculation_id,'duration',Interval(start_ns,end_ns),request.partial_policy,
                        request.unit,'event',request.minimum_coverage,config_version=self._plan.config_version)
        try:
            self._calculation=RecordTimeCalculation(self._budget,spec,'1',D.BOOL,step,
                backend=self._plan.execution.backend,batch_intervals=64)
        except BaseException as error:
            self._calculation=getattr(error,'record_time_cleanup_owner',None)
            raise
        value=ScalarValue(True,D.BOOL,True,Q.NONE)
        if step is None:
            if start_ns<end_ns:
                self._calculation.consume(((start_ns,value),(end_ns,value)))
        else:
            driver=self._choices[request.calculation_id].driver
            count=self._indexes.count(driver)
            if count:
                first=self._indexes.lower(driver,start_ns)
                if first==count or first>0 and self._indexes.at(driver,first)>start_ns:
                    first-=1
                last=min(count-1,self._indexes.lower(driver,end_ns))
                for index in range(first,last+1):
                    self._calculation.consume(((self._indexes.at(driver,index),value),))
        result=self._calculation.finish()
        if estimated:
            from .transform_partial import partial_result
            result=partial_result(result,request.partial_policy)
        self._consumer(request,event_id,result)
        self._calculation.close();self._calculation=None

    def _flush_ready(self,final=False):
        """保留仍缺右端的请求，其余按必要范围计算；EOF不补记录。

        参数: final只在真实来源EOF后使用。返回: None。异常: 原查询错，费用留到close。
        """
        pending=[]
        try:
            while self._queue:
                item=heapq.heappop(self._queue)
                end,serial,request,event_id,start,cost,estimated=item
                driver=self._choices[request.calculation_id].driver
                last=None if self._indexes is None or driver is None else self._indexes.last(driver)
                if not final and self._steps[request.calculation_id] is not None and (last is None or last<end):
                    pending.append(item)
                    continue
                self._calculate(request,event_id,start,end,estimated)
                item=None
                _release_owned_ram(self,cost,'_pending_cost')
        except BaseException:
            self._failed=True
            raise
        finally:
            for item in pending:
                heapq.heappush(self._queue,item)

    def finish(self):
        """真实EOF后结算未完成范围，不假造周期尾段。参数: 无。返回: None。异常: 原计算错。"""
        self._open()
        self._flush_ready(final=True)

    @property
    def closed(self):
        """返回关闭状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    def close(self):
        """只关闭自己的临时文件，成功后才撤销责任。参数: 无。返回: None。异常: 原关闭错可重试。"""
        if self._closed:
            return
        if self._calculation is not None:
            self._calculation.close();self._calculation=None
        self._queue.clear()
        self._plan=self._requests=self._consumer=self._choices=None
        _release_owned_ram(self,self._pending_cost,'_pending_cost')
        _release_owned_ram(self,self._fixed_cost,'_fixed_cost')
        self._closed=True
