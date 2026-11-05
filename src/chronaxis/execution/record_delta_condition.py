"""在当前窗口内保留必要数值片段，输出窗口变化量的三值条件。

实际模式在旧边界移出窗口时继续求值；固定/DBC只在选定驱动到达时移动窗口，
其他更新只处理失效。原实际坐标和TTL不改变，变化量仍交原独立两后端核计算。
"""
from collections import deque
from dataclasses import replace
from fractions import Fraction
from ..core.numeric import ScalarValue
from ..core.types import SignalDType as D,QualityFlag as Q,Truth as T
from ..core.window_delta import DeltaSpan
from ..core.window_delta_reference import window_delta_reference
from ..core.window_delta_numpy import window_delta_numpy
from ..results.errors import ResultClosedError
from ..results.spool import _reserve_owned_ram,_release_owned_ram,_cleanup_owner


class RecordDeltaCondition:
    """拥有当前窗口片段和有限驱动时刻；不创建整段历史或对照时间轴。"""

    def __init__(self,budget,spec,dtype,backend,step_ns):
        """预付有限状态，动态窗口按实际容量收费。参数: 预算/配置/数值类型/后端/周期。返回: owner。异常: 原构造错。"""
        self._budget,self._spec,self._dtype,self._step=budget,spec,dtype,step_ns
        self._held_cost=self._fixed_cost=self._span_cost=self._clock_cost=self._work_cost=0
        self._spans,self._clocks=deque(),deque()
        self._held_number=self._held_right=None
        self._held_deadline=None
        self._point=self._right=ScalarValue(None,D.BOOL,False,Q.MISSING)
        self._last_time=None
        self.next_deadline=None
        self._closed=self._failed=False
        try:
            _reserve_owned_ram(self,65536,'_fixed_cost')
            self._kernel=window_delta_reference if backend=='reference' else window_delta_numpy
        except BaseException as error:
            _cleanup_owner(self,error,'record_delta_cleanup_owner','窗口变化条件构造')
            raise

    @staticmethod
    def _condition(result):
        """转换既有数值核的三值结果，不把未知变False。参数: 结果。返回: ScalarValue。异常: 原类型错。"""
        valid=result.condition is not T.UNKNOWN
        return ScalarValue(result.condition is T.TRUE if valid else None,D.BOOL,valid,result.quality)

    def _append(self,time_ns,point,right):
        """只保存值或质量真正变化的边界，查询末点临时构造。

        参数: 实际时刻、点值/右侧值。返回: None。异常: 预算/时间回退。
        """
        value=point.value if point.valid else None
        pq=Q.NONE if point.valid else point.quality
        cq=Q.NONE if right.valid else right.quality
        if self._spans:
            last=self._spans[-1]
            if last.start_ns==time_ns:
                self._spans[-1]=DeltaSpan(time_ns,time_ns,value,cq,pq,right.partial,point.partial)
                return
            self._spans[-1]=replace(last,end_ns=time_ns)
            if last.value==value and last.quality==cq==pq and last.partial==right.partial==point.partial:
                return
        _reserve_owned_ram(self,2048,'_span_cost')
        self._spans.append(DeltaSpan(time_ns,time_ns,value,cq,pq,right.partial,point.partial))

    def _left(self,time_ns):
        """只根据当前窗口需要的驱动记录确定左端。参数: 实际时刻。返回: 左端或不足时None。异常: 无。"""
        if self._step is None:
            return time_ns-self._spec.window_ns
        count=len(self._clocks)
        offset=Fraction(self._spec.window_ns,self._step)
        target=Fraction(count-1)-offset
        if target<0:
            return None
        index=target.numerator//target.denominator
        if target==index:
            return self._clocks[index]
        return round(Fraction(self._clocks[index])+(target-index)*(self._clocks[index+1]-self._clocks[index]))

    def update(self,time_ns,point,right,expires_at_ns,*,driver=False):
        """推进真实值和当前窗口，返回点/右侧条件；不输出变化值副本。

        参数: 实际时刻、求值点/右侧值、实际TTL截止及是否选定驱动。
        返回: 两个BOOL ScalarValue。异常: 倒序、预算或原数值错误；失败只能清理。
        """
        if self._closed or self._failed:
            raise ResultClosedError('窗口变化条件已关闭或失败')
        spans=point_result=right_result=None
        try:
            if self._last_time is not None and time_ns<self._last_time:
                raise ValueError('窗口变化时间回退')
            self._last_time=time_ns
            if self._step is not None:
                if driver:
                    if not self._clocks or self._clocks[-1]!=time_ns:
                        _reserve_owned_ram(self,128,'_clock_cost')
                        self._clocks.append(time_ns)
                    limit=(self._spec.window_ns+self._step-1)//self._step+1
                    while len(self._clocks)>limit:
                        self._clocks.popleft()
                        _release_owned_ram(self,128,'_clock_cost')
                    self._held_number,self._held_right,self._held_deadline=point,right,expires_at_ns
                else:
                    unknown=ScalarValue(None,self._dtype,False,Q.MISSING)
                    if self._held_number is None:
                        point=right=unknown
                    else:
                        expired=self._held_deadline is not None and time_ns>=self._held_deadline
                        if expired:
                            point=right=ScalarValue(None,self._dtype,False,Q.STALE)
                        else:
                            point=self._held_number if point.valid else point
                            right=self._held_right if right.valid else right
                        if not point.valid or not right.valid:
                            self._held_number,self._held_right=point,right
                self.next_deadline=(self._held_deadline if self._held_deadline is not None and self._held_deadline>time_ns else None)
            self._append(time_ns,point,right)
            if self._step is not None and not driver:
                if not point.valid:
                    self._point=ScalarValue(None,D.BOOL,False,point.quality)
                if not right.valid:
                    self._right=ScalarValue(None,D.BOOL,False,right.quality)
                return self._point,self._right
            left=self._left(time_ns)
            if left is None or left>=time_ns:
                self._point=self._right=ScalarValue(None,D.BOOL,False,Q.MISSING)
                return self._point,self._right
            while len(self._spans)>1 and self._spans[0].end_ns<=left and self._spans[0].start_ns<left:
                self._spans.popleft()
                _release_owned_ram(self,2048,'_span_cost')
            _reserve_owned_ram(self,65536+4096*(len(self._spans)+1),'_work_cost')
            tail=DeltaSpan(time_ns,time_ns,point.value if point.valid else None,
                Q.NONE if right.valid else right.quality,Q.NONE if point.valid else point.quality,right.partial,point.partial)
            spans=tuple(self._spans)
            spans=spans if spans[-1].start_ns==time_ns else spans+(tail,)
            spec=self._spec if self._step is None else replace(self._spec,window_ns=time_ns-left)
            point_result=self._kernel(spec,spans,time_ns,self._dtype)
            right_result=point_result
            if tail.point_quality!=tail.quality:
                right_result=self._kernel(spec,spans[:-1]+(replace(tail,point_quality=tail.quality),),time_ns,self._dtype)
            self._point,self._right=self._condition(point_result),self._condition(right_result)
            # 净变化只依赖端点数值，要求单调时中间实际观测值也参与判断。
            history_partial=any((s.point_partial if s.start_ns==left else s.partial)
                                for s in spans if s.start_ns<=left<s.end_ns)
            if spec.monotonic:
                history_partial|=any(s.point_partial for s in spans if left<s.start_ns<time_ns)
            if self._point.valid and (history_partial or point.partial):
                self._point=replace(self._point,partial=True)
            if self._right.valid and (history_partial or right.partial):
                self._right=replace(self._right,partial=True)
            if self._step is None:
                candidates=[span.start_ns+self._spec.window_ns for span in self._spans
                            if time_ns<span.start_ns+self._spec.window_ns<(1<<63)]
                if expires_at_ns is not None and expires_at_ns>time_ns:
                    candidates.append(expires_at_ns)
                self.next_deadline=min(candidates) if candidates else None
            return self._point,self._right
        except BaseException:
            self._failed=True
            raise
        finally:
            spans=point_result=right_result=None
            _release_owned_ram(self,self._work_cost,'_work_cost')

    @property
    def closed(self):
        """返回资源关闭状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    def close(self):
        """释放有界片段与驱动记录，不写文件。参数: 无。返回: None。异常: 原预算关闭错，可重试。"""
        if self._closed:
            return
        self._spans.clear();self._clocks.clear()
        self._held_number=self._held_right=None
        for slot in ('_span_cost','_clock_cost','_work_cost','_fixed_cost'):
            _release_owned_ram(self,getattr(self,slot),slot)
        self._closed=True
