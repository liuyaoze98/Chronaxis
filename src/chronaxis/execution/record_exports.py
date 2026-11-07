"""只为显式导出接同次读取的帧或样本；复用既有writer和结果发布。

会话范围在真实EOF后确定；片段由窗口消费者直接交付，不复制片段表。
不再次读原日志或解码，默认精简导出不产生逐帧旁表。
"""
from ..core.models import Interval
from .record_signal_export import RecordSignalExport
from .legacy_frame_samples import LegacyFrameSamples
from ..results.frame_rebuild import FrameRebuildRead
from ..results.artifact_exports import ArtifactExportStore
from ..results.frame_exports import export_can_frames
from ..results.errors import ResultClosedError
from ..results.budget import _reserve_owned_ram,_release_owned_ram,_cleanup_owner


class RecordExports:
    """拥有导出索引、在线信号写出与当前帧游标；原帧仓由来源游标所有。"""
    def __init__(self,plan,budget,path,cursors):
        """建立仅显式请求的索引。参数: 计划/预算/新路径/借用来源。返回: owner。异常: 原构造错。"""
        self._plan,self._budget,self._cursors=plan,budget,cursors
        self._held_cost=self._fixed_cost=0
        self._exports=self._reader=self._export_owner=self._signal=self._rebuild=None
        self._closed=self._failed=self._finished=False
        self._option=plan.outputs.can_frames
        try:
            _reserve_owned_ram(self,65536,'_fixed_cost')
            self._require_clock()
            try:
                self._exports=ArtifactExportStore(budget,path,plan.dataset.session_id,plan.metadata.get('device_label','pending'),integrity=plan.diagnostics.integrity)
            except BaseException as error:
                self._exports=getattr(error,'artifact_export_store_cleanup_owner',None);raise
            if plan.outputs.signal_csv is not None:
                try:
                    self._signal=RecordSignalExport(plan,budget,cursors,self._exports,path)
                except BaseException as error:
                    self._signal=getattr(error,'record_signal_export_cleanup_owner',None);raise
        except BaseException as error:
            _cleanup_owner(self,error,'record_exports_cleanup_owner','记录流原帧导出');raise

    def _require_clock(self):
        """多来源片段须有可比时钟；单来源不强求映射。参数: 无。返回: None。异常: 缺同步依据。"""
        plan=self._plan
        options=[]
        if self._option is not None:
            options.append((self._option,{self._option.source}))
        if plan.outputs.signal_csv is not None:
            option=plan.outputs.signal_csv
            options.append((option,{plan.bindings.resolve(n).source for n in option.spec.signals}))
        for option,sources in options:
            if option.scope!='segments':continue
            for window in (w for w in plan.windows if option.window is None or w.window_id==option.window):
                checked_sources=set(sources)
                rule=next(r for r in plan.rules if r.rule_id==window.event)
                names=set(rule.dependencies)
                choice=dict(plan.intervals.resolved)[window.window_id]
                if choice.driver:names.add(choice.driver)
                checked_sources.update(plan.bindings.resolve(n).source for n in names)
                if not names:checked_sources.update(s.name for s in plan.sources)
                evidenced={item.source for item in plan.bindings.synchronization}
                keys=set()
                for source in plan.bindings.sources:
                    if source.name not in checked_sources:continue
                    clock=source.timebase
                    if source.name in evidenced or clock==plan.dataset.timebase or clock.time_type.value=='absolute' and plan.dataset.timebase.time_type.value=='absolute':
                        keys.add(('dataset',))
                    else:
                        keys.add(('utc',) if clock.time_type.value=='absolute' else ('relative',clock.timebase_id,clock.origin))
                if len(keys)>1:raise ValueError('导出与片段缺少共同时间基准')

    def _export(self,actual,segment_id=None):
        """借同次封口原帧写一份所需输出。参数: 实际范围/父片段。返回: None。异常: 原消费/发布错。"""
        option=self._option
        cursor=next(c for c in self._cursors if c.source_name==option.source)
        store=cursor._raw_store
        if store is None or store.closed or store.state!='sealed':
            raise ValueError('原帧导出缺少同次封口输入')
        interval=actual or Interval(self._plan.dataset.domain.start_ns,self._plan.dataset.domain.start_ns)
        try:
            if option.resampling is None:
                self._reader=store.iter_frames()
            else:
                context=cursor._dbc_context
                if context is None:raise ValueError('报文重采样缺同次编码定义')
                if cursor.legacy_frame_storage:
                    source=next(s for s in self._plan.sources if s.name==option.source)
                    try:
                        self._reader=LegacyFrameSamples(store,cursor._message_store,context,self._budget,
                            read_identity=cursor._read_identity,session_id=self._plan.dataset.session_id,channel=source.config.channel,trace=False)
                    except BaseException as error:
                        self._reader=getattr(error,'legacy_frame_samples_cleanup_owner',None);raise
                else:
                    self._reader=store.iter_samples()
                try:
                    self._rebuild=FrameRebuildRead(self._reader,option.resampling,interval,context.pairs(),self._budget,
                        self._exports.path/f'rebuild-{self._exports.count:08d}',backend=self._plan.execution.backend,
                        periods=context.periods,integrity=self._plan.diagnostics.integrity,trace=False)
                except BaseException as error:
                    self._rebuild=getattr(error,'frame_rebuild_cleanup_owner',None);raise
                self._reader=None
            files=[]
            export_can_frames(self._rebuild or self._reader,option.spec,interval,self._exports.next_path(),self._budget,
                source=option.source,device_label=self._plan.metadata.get('device_label','pending'),compact=True,
                integrity=self._plan.diagnostics.integrity,file_consumer=files.extend)
            if self._rebuild is not None:self._rebuild.close();self._rebuild=None
            if self._reader is not None:self._reader.close();self._reader=None
            self._exports.append('can_frames',option.scope,actual,segment_id=segment_id,completed_files=files)
        except BaseException as error:
            self._export_owner=getattr(error,'export_cleanup_owner',None)
            self._failed=True;error.record_exports_cleanup_owner=self;raise

    def session(self):
        """EOF后裁实际会话范围，空输入保持空输出。参数: 无。返回: None。异常: 原导出错。"""
        if self._signal is not None:self._signal.finish()
        if self._option is None or self._option.scope!='session': return
        cursor=next(c for c in self._cursors if c.source_name==self._option.source)
        actual=None
        if cursor.observed_start is not None and cursor.observed_end is not None:
            domain=self._plan.dataset.domain
            start,end=max(domain.start_ns,cursor.observed_start),min(domain.end_ns,cursor.observed_end)
            if start<=end: actual=Interval(start,end)
        self._export(actual)

    def segment(self,segment):
        """直接接最终片段，不保存第二份片段历史。参数: CompactSegment。返回: None。异常: 原导出错。"""
        if self._signal is not None:self._signal.segment(segment)
        if self._option is not None and self._option.scope=='segments' and (self._option.window is None or segment.window_id==self._option.window):
            self._export(segment.actual,segment.segment_id)

    def seal(self):
        """全部请求完成后封索引。参数: 无。返回: None。异常: 原封口错。"""
        self._exports.seal();self._finished=True

    def take_exports(self,receiver):
        """唯一移交已完成结果；失败前责任仍可达。参数: 同预算父owner。返回: None。异常: 状态错。"""
        if not self._finished or self._closed or receiver._budget is not self._budget or receiver._artifact_exports is not None:
            raise ResultClosedError('原帧输出尚不可移交')
        owner=self._exports
        try:
            receiver._artifact_exports=owner
        finally:
            if receiver._artifact_exports is owner: self._exports=None

    @property
    def closed(self):
        """返回实际关闭状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    def close(self):
        """先关当前输出及索引，再释放自有状态；不关闭借用原帧。参数: 无。返回: None。异常: 原关闭错。"""
        if self._closed:return
        for slot in ('_signal','_export_owner','_rebuild','_reader','_exports'):
            owner=getattr(self,slot)
            if owner is not None: owner.close();setattr(self,slot,None)
        self._plan=self._cursors=self._option=None
        _release_owned_ram(self,self._fixed_cost,'_fixed_cost');self._closed=True
