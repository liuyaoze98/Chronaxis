"""从最终事件表生成窗口，不再复制一份事件阶段或重扫原输入。

每个窗口只保最后可能继续合并的父组及有限新父；记录周期借共享实际时刻索引。
边界扩展/合并继续使用既有两个独立窗口核，默认输出精简片段。
"""
from dataclasses import replace
from fractions import Fraction
from ..core.models import Interval
from ..core.temporal import Event,TemporalRule
from ..core.windows import WindowSpec
from ..core.windows_reference import build_segments_reference
from ..core.windows_numpy import build_segments_numpy
from ..results.summary import SummaryEventRow
from ..results.codec import decode_row
from ..core.types import QualityFlag as Q
from ..results.errors import ResultClosedError,ResultFormatError
from ..results.spool import _reserve_owned_ram,_release_owned_ram,_cleanup_owner
from .history import _metadata_bytes


class RecordWindows:
    """拥有最终事件表读槽和有限待合并父组；共享时点索引、结果仓均为借用。"""

    def __init__(self,plan,budget,indexes,steps,consumer):
        """预付声明，不读取输入或事件表。参数: 计划/预算/时点索引/周期/片段回调。返回: owner。异常: 原构造错。"""
        self._plan,self._budget,self._indexes,self._steps,self._consumer=plan,budget,indexes,steps,consumer
        self._held_cost=self._fixed_cost=self._parents_cost=self._reader_cost=self._workspace_cost=0
        self._handle=None
        self._parents={}
        self._since={}
        self._observation={}
        self._specs={}
        self._rules={}
        self._closed=self._failed=False
        self._choices=dict(plan.intervals.resolved)
        self._coverage_needed={calculation.scope.split(":",1)[1] for calculation in plan.calculations
            if calculation.scope.startswith("segment:") and calculation.minimum_coverage>0}
        try:
            _reserve_owned_ram(self,131072+64*_metadata_bytes(plan.windows),'_fixed_cost')
            for request in plan.windows:
                self._parents[request.window_id]=[]
                self._since[request.window_id]=0
                self._specs[request.window_id]=WindowSpec(request.window_id,request.event,request.anchor,
                    request.pre_ns,request.post_ns,request.merge,request.exit_delay_ns)
            for rule in plan.rules:
                self._rules[rule.rule_id]=TemporalRule(rule.rule_id,plan.dataset.dataset_id,plan.dataset.session_id,
                    rule.temporal_rule_type,rule.minimum_duration_ns or 0,rule.emit_initial,rule.window_duration_ns or 0,
                    duration_comparison=rule.duration_comparison)
            self._build=build_segments_reference if plan.execution.backend=='reference' else build_segments_numpy
        except BaseException as error:
            _cleanup_owner(self,error,'record_windows_cleanup_owner','按需窗口构造')
            raise

    def _bounds(self,window,event):
        """按所选周期定位实际边界；actual由原核直接扩展。参数: 窗口/事件。返回: 四元组或None。异常: 原查找错。"""
        step=self._steps[window.window_id]
        if step is None:
            return None
        driver=self._choices[window.window_id].driver
        if not self._indexes.count(driver):
            return event.start_ns,event.start_ns,True,True
        end=event.start_ns if event.end_ns is None else event.end_ns
        extension=window.exit_delay_ns if window.merge=='exit_delay' else window.post_ns
        left,left_clip=self._indexes.shift(driver,event.start_ns,-window.pre_ns,step)
        right,right_clip=self._indexes.shift(driver,end,extension,step)
        return left,right,left_clip,right_clip

    def _coverage(self,window,segment,parents):
        """仅明确门槛请求才算窗口已取得部分比例，不保存各记录的第二时间。

        参数: 窗口/结果/本组父事件。返回: 0—1或无法确定的None。异常: 原时间读取错。
        actual沿原请求秒数；周期模式按已选记录跨度与请求周期数比较。
        """
        if segment.actual is None:
            return 0.
        ids=set(segment.parent_event_ids)
        selected=tuple(parent for parent in parents if parent.event_id in ids)
        extension=window.exit_delay_ns if window.merge=='exit_delay' else window.post_ns
        step=self._steps[window.window_id]
        if step is None:
            left=min(parent.start_ns-window.pre_ns for parent in selected)
            right=max((parent.start_ns if parent.end_ns is None else parent.end_ns)+extension for parent in selected)
            return segment.actual.duration_ns()/(right-left)
        driver=self._choices[window.window_id].driver
        starts=[]
        ends=[]
        for parent in selected:
            start,outside=self._indexes.position(driver,parent.start_ns)
            end,outside_end=self._indexes.position(driver,parent.start_ns if parent.end_ns is None else parent.end_ns)
            if outside or outside_end:
                return None
            starts.append(start-Fraction(window.pre_ns,step))
            ends.append(end+Fraction(extension,step))
        actual_left,_=self._indexes.position(driver,segment.actual.start_ns)
        actual_right,_=self._indexes.position(driver,segment.actual.end_ns)
        length=max(ends)-min(starts)
        return 0. if length==0 else min(1.,max(0.,float((actual_right-actual_left)/length)))

    def _process(self,window,final=False):
        """复用窗口核，非末批只保最后合并组，其他片段直接输出。

        参数: 窗口/真实EOF标识。返回: None。异常: 预算/窗口/发布原错，责任保留到close。
        """
        name=window.window_id
        entries=self._parents[name]
        if not entries:
            return
        parents=bounds=segments=None
        primary=None
        try:
            _reserve_owned_ram(self,65536+sum(8192+16*_metadata_bytes(item[0]) for item in entries),'_workspace_cost')
            parents=tuple(item[0] for item in entries)
            bounds=None if self._steps[name] is None else tuple(item[2] for item in entries)
            segments=self._build(parents,self._specs[name],self._observation[name],bounds=bounds,compact=True)
            limit=len(segments) if final else max(0,len(segments)-1)
            for index in range(limit):
                segment=segments[index]
                if name in self._coverage_needed:
                    segment=replace(segment,coverage=self._coverage(window,segment,parents))
                self._consumer(segment)
            segment=None
            keep=0
            if not final:
                first=segments[-1].parent_event_ids[0]
                keep=next(index for index,item in enumerate(entries) if item[0].event_id==first)
            else:
                keep=len(entries)
            cost=sum(item[1] for item in entries[:keep])
            del entries[:keep]
            parents=bounds=segments=None
            _release_owned_ram(self,cost,'_parents_cost')
            self._since[name]=0
        except BaseException as error:
            primary=error
            raise
        finally:
            parents=bounds=segments=None
            try:
                _release_owned_ram(self,self._workspace_cost,'_workspace_cost')
            except BaseException as cleanup:
                if primary is None:
                    raise
                # 真实写出/计算错误优先；未退费用仍在本owner，交由父会话恢复。
                primary.add_note('窗口工作区清理附加失败：'+type(cleanup).__name__)

    def finish(self,cursors,spool):
        """所有来源结束后只读一次最终事件表，并生成片段。

        参数: 真正EOF的游标、同次最终结果仓。返回: None。异常: 缺范围/短读/损坏/预算/发布原错。
        未请求窗口时调用方不创建本对象，空事件不建立额外中间仓。
        """
        if self._closed or self._failed:
            raise ResultClosedError('窗口已关闭或失败')
        if not spool.counts.get('events',0):
            return
        row=event=payload=None
        try:
            definitions={item.definition.name:item.definition for item in self._plan.signals}
            rules={rule.rule_id:rule for rule in self._plan.rules}
            for window in self._plan.windows:
                names=set(rules[window.event].dependencies)
                driver=self._choices[window.window_id].driver
                if driver:
                    names.add(driver)
                from ..planning.transforms import physical_dependencies
                names=physical_dependencies(self._plan,names)
                sources={definitions[name].source for name in names} if names else {source.name for source in self._plan.sources}
                starts=[c.observed_start for c in cursors if c.source_name in sources and c.observed_start is not None]
                ends=[c.observed_end for c in cursors if c.source_name in sources and c.observed_start is not None and c.observed_end is not None]
                if starts and ends:
                    left=max(min(starts),self._plan.dataset.domain.start_ns)
                    right=min(max(ends),self._plan.dataset.domain.end_ns)
                    if left<=right:
                        self._observation[window.window_id]=Interval(left,right)
            path=spool._seal_table('events')
            _reserve_owned_ram(self,spool.reader_cost_for('events'),'_reader_cost')
            self._handle=path.open('rb',buffering=8192)
            maximum=spool.row_limit('events')
            count=0
            while True:
                payload=self._handle.readline(maximum+1)
                if not payload:
                    break
                if len(payload)>maximum or not payload.endswith(b'\n'):
                    raise ResultFormatError('窗口事件输入短读或行超限')
                row=decode_row(payload,maximum)
                if type(row) is not SummaryEventRow:
                    raise ResultFormatError('窗口需要同次精简事件表')
                count+=1
                event=Event(row.event_id,self._rules[row.rule_id],'point' if row.end_ns is None else 'activity',
                    row.start_ns,row.confirmed_ns,row.end_ns,row.status,row.trigger,
                    row.quality & ~Q.ESTIMATED if row.status in ('point','timeout','closed') else row.quality,row.quality)
                for window in self._plan.windows:
                    if window.event!=row.rule_id:
                        continue
                    if window.window_id not in self._observation:
                        raise ValueError('有事件却没有实际窗口观测范围')
                    cost=8192+32*_metadata_bytes(event)
                    _reserve_owned_ram(self,cost,'_parents_cost')
                    bounds=self._bounds(window,event)
                    self._parents[window.window_id].append((event,cost,bounds))
                    self._since[window.window_id]+=1
                    if self._since[window.window_id]>=min(self._plan.execution.batch_rows,64):
                        self._process(window)
                row=event=payload=None
            if count!=spool.counts['events']:
                raise ResultFormatError('窗口事件表记录缺失')
            self._handle.close();self._handle=None
            _release_owned_ram(self,self._reader_cost,'_reader_cost')
            for window in self._plan.windows:
                self._process(window,final=True)
        except BaseException:
            self._failed=True
            raise
        finally:
            row=event=payload=None

    @property
    def closed(self):
        """返回资源关闭状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    def close(self):
        """关闭读槽并释放剩余父组，不删除最终事件表。参数: 无。返回: None。异常: 原关闭错，可重试。"""
        if self._closed:
            return
        if self._handle is not None:
            self._handle.close();self._handle=None
        self._parents.clear()
        self._plan=self._consumer=self._indexes=None
        for slot in ('_parents_cost','_workspace_cost','_reader_cost','_fixed_cost'):
            _release_owned_ram(self,getattr(self,slot),slot)
        self._closed=True
