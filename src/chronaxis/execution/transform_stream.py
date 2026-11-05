"""在原始记录流及下游规则之间插入按需的时序变换。

每一层只持有自己的最新输入、滚动窗口，以及固定周期等待后帧确认时尚未
交付的有界原组。待同一时刻的原更新与变换值均齐全，再原子交给下层。
无全会话网格、输入重扫或对照时间列；预算、取消和真实EOF沿主执行器。
"""
from collections import deque
from dataclasses import replace
from fractions import Fraction
from ..core.numeric import ScalarValue
from ..core.types import QualityFlag as Q, SignalDType as D
from ..core.models import SourceRef
from ..results.budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from .driver_expression import DriverExpression
from .groups import DecodedTimeGroup
from .history_records import estimate_record_bytes
from .record_sample import RecordSample
from .state import LatestSignalState
from .transform_window import TransformSpan, TransformWindow, first_grid


class TransformStage:
    """拥有一层的状态与前瞻，向唯一后继按实际时间递增地交付组。"""

    def __init__(self, plan, item, defs, choice, period, ends, cursors, budget, emit):
        """参数: 计划/变换、有效定义、原时钟/周期、EOF/游标、预算及后继。返回: owner。异常: 预算/绑定错误。"""
        self.item,self.backend,self._budget,self.emit=item,plan.execution.backend,budget,emit
        self._held_cost=self._fixed_cost=self._queue_cost=self._work_cost=0
        self.state=self.driver=self.history=None
        self.host = None
        self.host_finished = False
        self.waiting=deque()
        self.epoch=self.next_grid=self.last=None
        self.last_point=self.last_right=self.last_deadline=None
        self.last_update=False
        self.adjacent=self.clock_start=None
        self.adjacent_weight=Fraction(0)
        self.adjacent_known=True
        self.sequence=0
        self.ends,self.cursors=ends,cursors
        self.period,self.clock=period,choice.driver
        self.sources={plan.bindings.resolve(n).source for n in item.physical}
        if not self.sources:
            self.sources=set(cursors)
        self.domain=plan.bindings.domain
        self.ref=SourceRef(plan.dataset.session_id,item.output.source,item.output.field)
        self.names=set(item.expression.dependencies)|({self.clock} if self.clock else set())
        self.closed=False
        try:
            _reserve_owned_ram(self,65536+1024*len(self.names),'_fixed_cost')
            self.state=LatestSignalState(budget,tuple(d for d in defs if d.name in self.names),plan.dataset.session_id)
            # 时钟决定区间长度，数值始终按输入表达式的真实更新独立推进。
            self.driver=DriverExpression(item.expression,self.state,None,backend=self.backend,
                derived=tuple(d.definition for d in plan.derived),observation_ends=ends)
            self.history=TransformWindow(budget,item.window_ns or item.max_gap_ns,period)
            if item.host_spec is not None:
                from ..extension_runtime import HostedTransform
                self.host = HostedTransform(item.host_spec,self.backend,budget)
        except BaseException as error:
            if self.host is None and getattr(error,'extension_cleanup_owner',None) is not None:
                self.host = error.extension_cleanup_owner
            if self.driver is None:
                self.driver=getattr(error,'driver_expression_cleanup_owner',None)
            if self.state is None:
                self.state=getattr(error,'state_cleanup_owner',None)
            _cleanup_owner(self,error,'transform_cleanup_owner','时序变换')
            raise

    def bounds(self):
        """取得实际可观测起点和已知终点。参数: 无。返回: 起点/可选终点。异常: 游标错误。"""
        start=min((self.cursors[n].observed_start for n in self.sources
                   if self.cursors[n].observed_start is not None),default=None)
        complete=all(self.cursors[n]._finished for n in self.sources)
        end=max((self.cursors[n].observed_end for n in self.sources if self.cursors[n].observed_end is not None),
                default=None) if complete else None
        if self.domain is not None:
            if start is not None:
                start=max(start,self.domain.start_ns)
            end=self.domain.end_ns if end is None else min(self.domain.end_ns,end)
        if complete and end is not None:
            self.ends[self.item.output.source]=end
        return start,end

    def _invalid(self,quality):
        """构造明确未知的输出。参数: 原因。返回: ScalarValue。异常: 非法质量位。"""
        return ScalarValue(None,self.item.output.dtype,False,quality or Q.MISSING)

    def _sample(self,t,value):
        """构造离散输出。参数: 网格/实际样本坐标和值。返回: RecordSample。异常: 模型错误。"""
        sample=RecordSample(self.item.name,t,self.sequence,value,self.item.output.unit,self.ref)
        self.sequence+=1
        return sample

    def _at_grid(self,t,point,update):
        """从原区间读取[t-W,t)及变化率端点。参数: 网格时刻、可选同刻点和更新。返回: ScalarValue。异常: 预算/数值错误。"""
        op=self.item.operation
        values,weights,fit=[],[],[]
        valid=Fraction(0)
        width=Fraction(0)
        quality=Q.NONE
        left_value=right_value=None
        partial=False
        for span,left,right,ratio in self.history.slices(t):
            w=(right-left)*ratio
            if right_value is None:
                right_value=span.value if span.deadline is None or t<span.deadline else self._invalid(Q.STALE)
            left_value=span.value if span.deadline is None or left<span.deadline else self._invalid(Q.STALE)
            good=max(0,min(right,span.deadline)-left)*ratio if span.deadline is not None else w
            if span.value.valid and good:
                valid+=good
                partial |= span.value.partial
                weights.append(good)
                values.append(span.value.value)
            if not span.value.valid:
                quality|=span.value.quality
            elif good<w:
                quality|=Q.STALE
            width+=w
            if op=='sample_fit_slope' and span.update and span.start>=left and span.point.valid:
                fit.append((-width,span.point))
                partial |= span.point.partial
        # 斜率会使用右端新读数；即使此前整个窗口都有完整实测值，新读数也可能是估值。
        if point is not None and point.partial and (op=='window_rate' or op=='sample_fit_slope' and update):
            partial=True
            quality|=Q.ESTIMATED
        window=self.item.window_ns
        if width<window:
            quality|=Q.MISSING
        partial |= valid<window
        if (not valid or partial and self.item.partial_policy=='strict'
                or valid < Fraction(str(self.item.minimum_coverage))*window):
            return self._invalid(quality)
        if self.host is not None:
            from ..extension_runtime import advance_grid
            value = advance_grid(self.host,t,window,values,weights,self.item.conversion)
        elif op.startswith('rolling_'):
            from ..core.rolling_values import rolling_value
            value=rolling_value(op,self.backend,values,weights,self.item.conversion,self.item.expression.root.dtype)
        else:
            from ..core.rate_transforms import rate_difference, rate_fit
            right_value=point if point is not None else right_value
            if op=='window_rate':
                if width!=window or left_value is None or right_value is None:
                    return self._invalid(Q.MISSING)
                value=rate_difference(self.backend,left_value,right_value,window)
            else:
                fit.reverse()
                if update and point is not None and point.valid:
                    fit.append((0,point))
                value=rate_fit(self.backend,[p for p,_ in fit],[s for _,s in fit])
            value=self._convert_rate(value)
        return replace(value,partial=True) if value.valid and partial else value

    def _convert_rate(self,value):
        """换算变化率目标单位。参数: 自然单位结果。返回: 新标量。异常: 转换错误。"""
        if self.item.conversion.factor==1:
            return value
        if self.backend=='reference':
            from ..core.affine import affine_reference
            return affine_reference(value,self.item.conversion.factor,0,D.FLOAT64)
        from ..core.affine_numpy import affine_numpy
        from .where_state import scalar_columns
        from .calculation_values import scalar_from_column
        return scalar_from_column(affine_numpy(scalar_columns({'v':value})['v'],self.item.conversion.factor,0,D.FLOAT64),0)

    def _deliver(self,group,t,value=None):
        """同刻真实更新与离散输出一次交付。参数: 可选原组、实际时刻、可选结果。返回: 无。异常: 下游错误。"""
        if value is None:
            if group is not None:
                self.emit(group)
        else:
            samples=() if group is None else group.samples
            self.emit(DecodedTimeGroup(t,(*samples,self._sample(t,value))))

    def _drain(self,group,point=None,update=False,*,through=None,unresolved=False):
        """按网格和原组时间归并。参数: 当前组/点、真实更新或EOF截止。返回: 无。异常: 下游/预算错误。"""
        t=group.time_ns if group is not None else through
        start,end=self.bounds()
        if self.next_grid is None and start is not None:
            self.next_grid=first_grid(start,self.item.origin_ns,self.item.step_ns)
        limit=t if end is None else min(t,end)
        while True:
            clock=group.time_ns if group is not None else None
            tick=self.next_grid if self.next_grid is not None and self.next_grid<=limit else None
            if clock is None and tick is None:
                break
            when=clock if tick is None else tick if clock is None else min(clock,tick)
            value=None
            if tick==when:
                _reserve_owned_ram(self,8192+1024*len(self.history.spans),'_work_cost')
                try:
                    value=self._invalid(Q.MISSING) if unresolved else self._at_grid(when,point if when==t else None,
                                                                                 update and when==t)
                finally:
                    _release_owned_ram(self,self._work_cost,'_work_cost')
                self.next_grid+=self.item.step_ns
            self._deliver(group if clock==when else None,when,value)
            if clock==when:
                group=None

    def _append_span(self,t,pair_width=None):
        """闭合上一条原始保持。参数: 后继实际时刻和所属驱动对跨度。返回: 无。异常: 预算/顺序错误。"""
        if self.last is not None and self.last<t:
            self.history.append(TransformSpan(self.last,t,self.last_right,self.last_deadline,self.last_update,
                                              self.last_point,pair_width))

    def push(self,group):
        """消费上游完整组。参数: 原子组。返回: 无；向后继交付。异常: 原输入/预算/求值错误。"""
        t=group.time_ns
        if self.period is None:
            self._process(group,None)
            return
        drive=any(s.name==self.clock for s in group.samples)
        if self.clock_start is None:
            if drive:
                self.clock_start=t
            self._process(group,None,unresolved=True)
            return
        if drive:
            width=t-self.clock_start
            self._flush_waiting(width)
            self._process(group,width)
            self.clock_start=t
        elif self.ends.get(self.state.definitions[self.clock].source,t)>=t:
            # 等原驱动右端确定后，以原时间顺序回放这几组；每个真实值只求值一次。
            cost=1024+sum(estimate_record_bytes(s) for s in group.samples)
            _reserve_owned_ram(self,cost,'_queue_cost')
            self.waiting.append((group,cost))
        else:
            self._flush_waiting(None)
            self._process(group,None,unresolved=True)

    def _flush_waiting(self,width):
        """以已确认的原对处理所有待定组。参数: 驱动实际跨度或EOF的None。返回: 无。异常: 交付/退款错误。"""
        while self.waiting:
            group,cost=self.waiting[0]
            self._process(group,width,unresolved=width is None)
            self.waiting.popleft()
            _release_owned_ram(self,cost,'_queue_cost')

    def _process(self,group,width,*,unresolved=False):
        """按已知计量推进原更新和网格。参数: 完整组、原驱动跨度、计量未知标志。返回: 无。异常: 原错。"""
        t=group.time_ns
        start,end=self.bounds()
        if start is None or t<start:
            self.emit(group)
            return
        if self.item.operation!='adjacent_rate' and self.last is None and self.period is None and start<t:
            self.last=start
            self.last_right,self.last_deadline=self.driver.evaluate_at(start)
            self.last_point=self.last_right
        # 后帧可能刚揭示来源EOF；在覆盖旧状态之前，按真实末端重新确定左侧有效截止。
        if self.last is not None:
            self.last_right,self.last_deadline=self.driver.evaluate_at(self.last)
        selected=tuple(s for s in group.samples if s.name in self.names)
        if selected:
            self.state.apply(DecodedTimeGroup(t,selected))
        updated=self.driver.actual_update_at(t)
        point,_=self.driver.evaluate_at(t,continuous=False)
        if self.item.operation=='adjacent_rate':
            output=None
            if self.last is not None:
                elapsed=t-self.last
                if not unresolved:
                    self.adjacent_weight+=Fraction(elapsed*self.period,width) if width else elapsed
                self.adjacent_known &= (not unresolved and self.last_right.valid and
                                        (self.last_deadline is None or self.last_deadline>=t))
            if updated and (end is None or t<=end):
                from ..core.rate_transforms import rate_difference
                ok=(self.adjacent is not None and t-self.adjacent[0]<=self.item.max_gap_ns
                    and self.adjacent_known and self.adjacent_weight>0)
                output=(self._convert_rate(rate_difference(self.backend,self.adjacent[1],point,self.adjacent_weight))
                        if ok else self._invalid(point.quality or Q.MISSING))
                if output.valid and (point.partial or self.adjacent[1].partial):
                    output=replace(output,partial=True)
                self.adjacent,self.adjacent_known,self.adjacent_weight=(t,point),point.valid,Fraction(0)
            self.last=t
            self._deliver(group,t,output)
            return
        if not unresolved:
            self._append_span(t,width)
        self._drain(group,point,updated,unresolved=unresolved)
        self.last,self.last_point,self.last_update=t,point,updated
        self.last_right,self.last_deadline=self.driver.evaluate_at(t)
        self.history.trim()

    def finish(self):
        """完成真正EOF后标记宿主状态正常结束。参数: 无。返回: None。异常: 最后网格失败仍通知取消。"""
        self._finish_grid()
        self.host_finished = True

    def _finish_grid(self):
        """按真实来源EOF补最后可定网格，缺少后继原帧不外推周期。参数: 无。返回: 无。异常: 交付错误。"""
        start,end=self.bounds()
        self._flush_waiting(None)
        if self.item.operation=='adjacent_rate' or start is None or end is None:
            return
        if self.period is None:
            if self.last is None:
                self.last=start
                self.last_right,self.last_deadline=self.driver.evaluate_at(start)
                self.last_point=self.last_right
            self.last_right,self.last_deadline=self.driver.evaluate_at(self.last)
            self._append_span(end)
        self._drain(None,through=end,unresolved=self.period is not None)

    def close(self):
        """清理等待组、真实区间和最新值。参数: 无。返回: 无。异常: 退款失败可重试。"""
        if self.closed:
            return
        for owner in (self.driver,self.state,self.history):
            if owner is not None:
                owner.close()
        if self.host is not None:
            self.host.close(cancelled=not self.host_finished)
            self.host = None
        self.waiting.clear()
        self.emit=self.last_point=self.last_right=None
        for field in ('_work_cost','_queue_cost','_fixed_cost'):
            _release_owned_ram(self,getattr(self,field),field)
        self.closed=True
