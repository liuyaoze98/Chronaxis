"""会话信号CSV随同次合并流在线写出；只暂留最后一个所需时刻组。

最后组在真实EOF范围确定后才写，保半开范围而不保存整段信号历史。
线性网格仍使用原SignalGrid；未请求的别名不进入本owner。
"""
from dataclasses import replace
from ..core.models import Interval
from ..sources.can_spec import can_field_from_key
from ..legacy.records import field_to_dict
from ..results.signal_exports import SignalCSVWriter,export_signal_csv
from .record_export_samples import RecordExportSamples
from ..results.budget import _reserve_owned_ram,_release_owned_ram,_cleanup_owner
from .history import _metadata_bytes


class RecordSignalExport:
    """拥有一个在线writer和待定末组，借用最终导出索引。"""
    def __init__(self,plan,budget,cursors,exports,path):
        """预约必要别名状态，不读取文件。参数: 计划/预算/游标/结果索引。返回: owner。异常: 构造原错。"""
        self._plan,self._budget,self._cursors,self._exports=plan,budget,cursors,exports
        self._held_cost=self._fixed_cost=self._pending_cost=0
        self._writer=self._history=None;self._pending=()
        self._closed=False
        self._option=plan.outputs.signal_csv
        self._definitions=tuple(s.definition for s in plan.signals if s.definition.name in self._option.spec.signals)
        self._names=set(self._option.spec.signals)
        self._sources={d.source for d in self._definitions}
        try:
            _reserve_owned_ram(self,65536+32*_metadata_bytes(self._definitions),'_fixed_cost')
            plan.bindings.require_synchronized(tuple(self._names))
            if self._option.period_driver is not None:
                definition=next(d for d in self._definitions if d.name==self._option.period_driver)
                cursor=next(c for c in cursors if c.source_name==definition.source)
                locator=field_to_dict(can_field_from_key(definition.field))
                period=next(f['cycle_ns'] for f in cursor.metadata['fields'] if f['locator']==locator)
                self._option=replace(self._option,period_driver=None,spec=replace(self._option.spec,
                    resampling=replace(self._option.spec.resampling,period_ns=period)))
            if self._option.scope=='segments':
                try:
                    self._history=RecordExportSamples(budget,path,self._definitions,plan.dataset.session_id)
                except BaseException as error:
                    self._history=getattr(error,'record_export_samples_cleanup_owner',None);raise
        except BaseException as error:
            _cleanup_owner(self,error,'record_signal_export_cleanup_owner','在线信号导出');raise

    def update_observation(self, plan):
        """接收同次读取已见范围，在线writer不会预造末端样本。参数: 内部计划。返回: None。异常: 无。"""
        self._plan=plan
        if self._writer is not None:
            self._writer.interval=Interval(self._writer.interval.start_ns,plan.dataset.domain.end_ns)
            if self._writer.worker is not None:
                self._writer.worker.interval=self._writer.interval

    def _bounds(self):
        """只查所选来源实际首末，不扫描输入。参数: 无。返回: 实际范围或None。异常: 无。"""
        starts=[c.observed_start for c in self._cursors if c.source_name in self._sources and c.observed_start is not None]
        ends=[c.observed_end for c in self._cursors if c.source_name in self._sources and c.observed_end is not None]
        if not starts or not ends:return None
        domain=self._plan.dataset.domain
        start,end=max(min(starts),domain.start_ns),min(max(ends),domain.end_ns)
        return Interval(start,end) if start<=end else None

    def _begin(self,final=False):
        """第一次需要写出时确定真实起点，末端暂以请求上限约束。参数: 是否EOF。返回: None。异常: 构造原错。"""
        if self._writer is not None:return
        actual=self._bounds();domain=self._plan.dataset.domain
        interval=(actual or Interval(domain.start_ns,domain.start_ns)) if final else Interval(
            domain.start_ns if actual is None else actual.start_ns,domain.end_ns)
        try:
            self._writer=SignalCSVWriter(self._option.spec,interval,self._exports.next_path(),self._budget,
                device_label=self._plan.metadata.get('device_label','pending'),definitions=self._definitions,
                backend=self._plan.execution.backend,compact=True,integrity=self._plan.diagnostics.integrity)
        except BaseException as error:
            self._writer=getattr(error,'export_cleanup_owner',None);raise

    def _flush(self):
        """交出上一实际组并释放待定费用。参数: 无。返回: None。异常: 原写入/清理错。"""
        for sample in self._pending:self._writer.push(sample)
        self._pending=()
        _release_owned_ram(self,self._pending_cost,'_pending_cost')

    def observe(self,group):
        """仅保所选样本的一个完整时刻；不在最新值状态里重复保存导出值。参数: 真实组。返回: None。异常: 原错。"""
        samples=tuple(sample for sample in group.samples if sample.name in self._names)
        if not samples:return
        if self._history is not None:
            for sample in samples:self._history.append(sample)
            return
        self._begin()
        self._flush()
        _reserve_owned_ram(self,4096+sum(4096+_metadata_bytes(s)*16 for s in samples),'_pending_cost')
        self._pending=samples

    def finish(self):
        """EOF收紧末端，再交末组和网格，登记唯一输出。参数: 无。返回: None。异常: 原发布错。"""
        if self._option.scope!='session':return
        self._begin(final=True)
        actual=self._bounds()
        end=self._writer.interval.start_ns if actual is None else actual.end_ns
        self._writer.observed_end(end)
        self._flush()
        self._writer.complete()
        self._exports.append('signal_csv','session',actual,completed_files=self._writer.files)
        self._writer=None

    def segment(self,segment):
        """片段确定后只读必要样本，复用同一导出器。参数: CompactSegment。返回: None。异常: 原导出错。"""
        if self._option.scope!='segments' or self._option.window!=segment.window_id:return
        actual=segment.actual
        interval=actual or Interval(self._plan.dataset.domain.start_ns,self._plan.dataset.domain.start_ns)
        try:
            files=[]
            export_signal_csv(self._history.rows(interval),self._option.spec,interval,self._exports.next_path(),
                self._budget,device_label=self._plan.metadata.get('device_label','pending'),definitions=self._definitions,
                backend=self._plan.execution.backend,compact=True,integrity=self._plan.diagnostics.integrity,
                file_consumer=files.extend)
            self._exports.append('signal_csv','segments',actual,segment_id=segment.segment_id,completed_files=files)
        except BaseException as error:
            self._writer=getattr(error,'export_cleanup_owner',None);raise

    @property
    def closed(self):
        """返回资源关闭状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    def close(self):
        """关闭尚未发布writer及末组，保留原输入和借用索引。参数: 无。返回: None。异常: 原关闭错。"""
        if self._closed:return
        if self._writer is not None:self._writer.close();self._writer=None
        if self._history is not None:self._history.close();self._history=None
        self._pending=();self._plan=self._cursors=self._exports=self._definitions=None
        _release_owned_ram(self,self._pending_cost,'_pending_cost')
        _release_owned_ram(self,self._fixed_cost,'_fixed_cost');self._closed=True
