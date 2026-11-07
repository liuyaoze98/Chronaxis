"""把新ASC/原始CSV的同次解码接到公共信号批次和真实观测协议。

适配器声明字段和时基，不读文件；每个TextCANObservationRead拥有独立解析器、
有限原帧块和预算。每次交付同时段各别名批，总样本数不超过batch_rows；同刻别名未全部
交付前不越过其watermark。完整EOF并关闭解析器后才开放观测证明和可选原帧仓。
原帧仓仅显式导出时创建，共用已解码值，不另扫描原文件。
"""

from pathlib import Path
from uuid import uuid4

from ..core.validation import require_identifier
from ..sources.text_can_spec import CANTextSpec
from ..sources.text_can_decode import CANTextDecodeRead,pack_text_records
from ..sources.descriptions import describe_fields,source_timebase_identity
from ..sources.models import ReadRequest,SignalBatch,SourceDescription,SourceCapabilities,freeze_metadata
from ..sources.protocol import BatchValidator,SourceClosedError
from ..results.budget import _reserve_owned_ram,_release_owned_ram,_cleanup_owner
from ..results.errors import ResultClosedError
from .can_reader import CANObservation
from .frame_capture import TextFrameStore
from .history import _metadata_bytes,_pending_bytes


class BudgetedTextCANSourceAdapter:
    """拥有静态描述和活read集合，借用导出DBC上下文；关闭不会释放借用上下文。"""

    def __init__(self,budget,spec,session_id,signals,*,backend='numpy',work_dir=None,retain_raw_frames=False,database_context=None,message_consumer=None,cycle_fields=(), metadata_fields=(),message_keys=(),integrity=True,trace=True,selected_ids=None,time_frame_ids=None,process_count=1,emit_frame_ids=None,blf_time_scope='source',legacy_blf_decode=False):
        """构造声明，不读取输入。参数: 预算/spec/会话/定义、后端、可选暂存目录及DBC上下文；message_keys为无值公式的完整触发定位；message_consumer同步接收必要消息，保留需自付预算；cycle_fields显式请求初始化DBC周期；metadata_fields仅确认驱动候选，两者不增加值解码。返回: adapter。异常: 配置/预算错。

        time_frame_ids将所需通道/ID的单调性检查与全来源范围统计分开，不改变原帧时间。
        selected_ids是纯消息计算需要的有限ID集合；仅在不要求全来源时间或原帧导出时
        下推给原始CSV读取器。此时观测范围是保留记录的范围，不能冒称全部来源范围。
        legacy_blf_decode仅由纯can_blf并行转接设置，保留原legacy长度及解码失败政策；不是用户配置字段。
        """
        if type(spec) is not CANTextSpec or backend not in ('reference','numpy') or type(retain_raw_frames) is not bool:
            raise ValueError('文本CAN来源配置或后端非法')
        from ..sources.can_updates import require_message_keys
        require_message_keys(message_keys, channel=spec.channel)
        if message_keys and message_consumer is None:
            raise ValueError('消息触发定位必须有实际消费者')
        if message_consumer is not None and not callable(message_consumer):
            raise TypeError('message_consumer需要同步可调用对象')
        if retain_raw_frames and work_dir is None:
            raise ValueError('显式原帧保存需要新工作目录')
        from ..legacy.dbc_cycles import require_cycle_fields
        require_cycle_fields(cycle_fields,spec.channel)
        require_cycle_fields(metadata_fields,spec.channel)
        if retain_raw_frames and time_frame_ids is not None:
            raise ValueError('原帧导出需要完整时间顺序检查')
        self._process_count = process_count
        self._emit_frame_ids = emit_frame_ids
        self._blf_time_scope=blf_time_scope
        self._legacy_blf_decode=legacy_blf_decode
        self._metadata_fields = metadata_fields
        self._selected_ids = selected_ids
        self._time_frame_ids = time_frame_ids
        self._cycle_fields=cycle_fields
        self._integrity=integrity
        self._trace=trace
        require_identifier(session_id,'text_can.session_id')
        self.budget=self._budget=budget; self.spec=spec; self.session_id=session_id
        self.signals=signals; self.backend=backend; self.work_dir=None if work_dir is None else Path(work_dir)
        self._retain_raw_frames=retain_raw_frames; self.database_context=database_context
        self._update_consumer=message_consumer; self._update_projection=None
        self._held_cost=self._fixed_cost=0; self._closed=False; self._requests=set(); self._pending=None
        try:
            cost=131072+_metadata_bytes((signals,selected_ids,time_frame_ids))*32+sum(1024+len(str(i.path).encode('utf-8'))*32 for i in spec.inputs)
            if message_keys:
                cost += 8192 + 2048 * len(message_keys)
            if cycle_fields or metadata_fields:
                cost += 16384 + _metadata_bytes((cycle_fields,metadata_fields))*32
            _reserve_owned_ram(self,cost,'_fixed_cost')
            if message_consumer is not None:
                from ..sources.can_updates import CANUpdateProjection
                from ..sources.can_spec import can_field_from_key
                self._update_projection=CANUpdateProjection(spec.name,session_id,tuple(can_field_from_key(s.field) for s in signals),message_keys=message_keys,clock_fields=metadata_fields)
            locator={'paths':tuple(str(i.path) for i in spec.inputs),'dbc_path':str(spec.dbc_path),
                'channel':spec.channel,'profile':'can-text-v1','offset_ns':0,'time_unit':'ns',
                'source_timebase_sha256':source_timebase_identity(spec.timebase,0)}
            self._description=SourceDescription(spec.name,describe_fields(spec.name,signals,locator),
                spec.timebase.timebase_id,None,None,SourceCapabilities(True,True,True,False,
                    ('ASC/CSV按文本转换时间并保原行；混合BLF沿用库浮点秒转纳秒并以记录序号定位；CSV按ID筛选时仅观测保留记录',),
                    (('所需通道/ID按声明顺序时间非递减；其他帧仅参与来源范围统计；DBC缺单位仍未核实'
                      if time_frame_ids is not None else '输入必须按声明顺序时间非递减；DBC缺单位仍未核实'),)),legacy_profile='can-text-v1')
        except BaseException as error:
            _cleanup_owner(self,error,'text_can_source_cleanup_owner','文本CAN来源构造')
            raise

    @property
    def retain_raw_frames(self):
        """返回本来源冻结的原帧保存选择。参数: 无。返回: bool。异常: 无。
        """
        return self._retain_raw_frames

    def _ensure_open(self):
        """拒绝使用已关闭适配器。参数: 无。返回: None。异常: SourceClosedError。
        """
        if self._closed:
            raise SourceClosedError('文本CAN来源已关闭')

    def describe(self):
        """返回静态字段及时间声明。参数: 无。返回: SourceDescription。异常: 已关闭。
        """
        self._ensure_open(); return self._description

    def iter_batches_with_observation(self,request):
        """创建具有同次观测的独立read。参数: request。返回: read。异常: 合同/预算错及可恢复owner。
        """
        self._ensure_open()
        if self._pending is not None:
            raise ResultClosedError('文本CAN仍有未返回read待清理')
        try:
            self._pending=TextCANObservationRead(self,request)
            read=self._pending; self._requests.add(read); self._pending=None
            return read
        except BaseException as error:
            self._pending=self._pending or getattr(error,'text_can_observation_cleanup_owner',None)
            _cleanup_owner(self._pending,error,'text_can_observation_cleanup_owner','文本CAN读取登记') if self._pending is not None else None
            if self._pending is not None and self._pending.closed:
                self._pending=None
            if self._pending is not None:
                error.text_can_source_cleanup_owner=self
            raise

    def iter_batches(self,request):
        """沿同一批次合同创建read，不另读输入。参数: request。返回: read。异常: 原工厂错。
        """
        return self.iter_batches_with_observation(request)

    def close(self):
        """关闭所有本来源活read，再释放描述费用。参数: 无。返回: None。异常: 关闭/费用错可重试。
        """
        if self._closed:
            return
        if self._pending is not None:
            self._pending.close(); self._pending=None
        while self._requests:
            next(iter(self._requests)).close()
        self._description=None
        self._update_projection=self._update_consumer=None
        _release_owned_ram(self,self._fixed_cost,'_fixed_cost'); self._closed=True


class TextCANObservationRead:
    """拥有一个有限原帧块和一个归一化批，完整EOF前不开放完成事实。"""

    def __init__(self,owner,request):
        """验证原会话/投影并构造未开始的解码器。参数: adapter/request。返回: read。异常: 合同/预算错。
        """
        owner._ensure_open()
        if type(request) is not ReadRequest or request.session_id!=owner.session_id:
            raise ValueError('文本CAN读取需要原会话ReadRequest')
        definitions={s.name:s for s in owner.signals}
        if not set(request.signal_names)<=set(definitions):
            raise ValueError('文本CAN请求包含未声明信号')
        self._owner=owner; self._request=request; self._budget=owner.budget
        self.identity=uuid4().hex; self._definitions=tuple(definitions[n] for n in request.signal_names)
        self._held_cost=self._fixed_cost=self._records_cost=self._batch_cost=self._pending_cost=self._validation_cost=self._runtime_cost=self._update_cost=0
        self._decoder=self._raw_store=self._current=self._validator=self._runtime_metadata=self._observation=None
        self._binding_projection=None
        self._records=[]; self._column=0; self._raw_eof=self._eof_sent=False
        self._closed=self._exhausted=self._failed=False
        try:
            _reserve_owned_ram(self,131072+_metadata_bytes((request,owner.signals))*32,'_fixed_cost')
            self._validator=BatchValidator(owner.describe(),request)
            try:
                factory = CANTextDecodeRead
                parallel_options = {}
                if owner._process_count > 1 or owner.spec.file_merge == 'time_order':
                    from .parallel_can_decode import ParallelCANDecodeRead
                    factory = ParallelCANDecodeRead
                    parallel_options = dict(process_count=owner._process_count,work_dir=owner.work_dir,
                                            emit_frame_ids=owner._emit_frame_ids,blf_time_scope=owner._blf_time_scope)
                self._decoder=factory(owner.spec,self._budget,
                    owner.signals if owner._update_consumer is not None else self._definitions,
                    **parallel_options,
                    database_context=owner.database_context, integrity=owner._integrity, trace=owner._trace,retain_source_time=owner.retain_raw_frames,
                    legacy_blf_decode=owner._legacy_blf_decode,
                    classify_unselected=owner._update_consumer is None,
                    **({'cycle_fields':owner._cycle_fields} if owner._cycle_fields else {}),
                    **({'metadata_fields':owner._metadata_fields} if owner._metadata_fields else {}),
                    **({'selected_ids':owner._selected_ids} if owner._selected_ids is not None else {}),
                    **({'time_frame_ids':owner._time_frame_ids} if owner._time_frame_ids is not None else {}))
            except BaseException as error:
                self._decoder=getattr(error,'text_can_cleanup_owner',None); raise
            if owner.retain_raw_frames:
                try:
                    self._raw_store=TextFrameStore(owner.work_dir/('frames-'+self.identity),self._budget,
                        owner.spec.name,owner.session_id,self.identity,database_context=owner.database_context,channel=owner.spec.channel,integrity=owner._integrity,trace=owner._trace)
                except BaseException as error:
                    self._raw_store=getattr(error,'text_frame_store_cleanup_owner',None); raise
        except BaseException as error:
            _cleanup_owner(self,error,'text_can_observation_cleanup_owner','文本CAN观测构造')
            raise

    @property
    def closed(self):
        """返回真实关闭状态。参数: 无。返回: bool。异常: 无。
        """
        return self._closed

    @property
    def failed(self):
        """返回当前读取是否失败。参数: 无。返回: bool。异常: 无。
        """
        return self._failed

    @property
    def exhausted(self):
        """返回完整EOF及解析器关闭事实。参数: 无。返回: bool。异常: 无。
        """
        return self._exhausted

    @property
    def observation(self):
        """仅交付本read已完成的真实观测。参数: 无。返回: CANObservation。异常: 未完成/失败。
        """
        if not self._exhausted or self._failed or self._observation is None:
            raise ResultClosedError('文本CAN观测尚未完成')
        return self._observation

    @property
    def observed_bounds(self):
        """返回同次解析已经看到的首末时间，不额外扫描或冒充EOF。

        参数: 无。返回: (first,last)，空输入为None。异常: 失败/关闭状态拒绝借读。
        """
        if self._closed or self._failed:
            raise ResultClosedError('文本CAN观测已关闭或失败')
        if self._observation is not None:
            return self._observation.first_ns,self._observation.last_ns
        return self._decoder.first_ns,self._decoder.last_ns

    @property
    def runtime_metadata(self):
        """交付同次DBC身份与解码次数。参数: 无。返回: 冻结元数据。异常: 未完成。
        """
        self.observation
        return self._runtime_metadata

    def prepare_metadata(self):
        """在读取前取得同次DBC周期，不冒充最终解码计数。

        参数: 无。返回: 冻结DBC事实。异常: 关闭/失败或启动原错；清理由本read负责。
        """
        if self._closed or self._failed or self._decoder is None:
            raise ResultClosedError('文本CAN读取已关闭或失败')
        try:
            facts = self._decoder.prepare_metadata()
            if self._binding_projection is None and self._owner._update_projection is not None:
                self._binding_projection = self._owner._update_projection.for_read(facts['fields'])
            return facts
        except BaseException as error:
            self._failed = True
            _cleanup_owner(self, error, 'text_can_observation_cleanup_owner', '文本CAN初始化')
            raise

    def __iter__(self):
        """返回独立游标。参数: 无。返回: self。异常: 无。
        """
        return self

    def _accept(self,batch):
        """按既有批合同核同刻组，保留所需pending费用。参数: batch。返回: 原批。异常: 校验/预算错。
        """
        _reserve_owned_ram(self,4096+2*_pending_bytes(self._validator)+1024*batch.sample_count,'_validation_cost')
        self._validator.accept(batch)
        retained=_pending_bytes(self._validator)
        _release_owned_ram(self,self._pending_cost,'_pending_cost')
        self._validation_cost-=retained; self._pending_cost+=retained
        _release_owned_ram(self,self._validation_cost,'_validation_cost')
        self._current=batch; return batch

    def _fill(self):
        """按全部别名的样本容量取有限原记录，所有值只解码一次。参数: 无。返回: None。异常: 原读/预算/暂存错。
        """
        self._records.clear(); self._column=0
        if self._binding_projection is None:
            self.prepare_metadata()
        _release_owned_ram(self,self._records_cost,'_records_cost')
        raw_rows=min(256,max(1,self._request.batch_rows//max(1,len(self._definitions))))
        for _ in range(raw_rows):
            try:
                record=next(self._decoder)
            except StopIteration:
                self._raw_eof=True; break
            cost=16384+_metadata_bytes((record.values,record.frame_values,record.frame_layout,
                str(record.raw.path),record.raw.raw_time))*32
            _reserve_owned_ram(self,cost,'_records_cost'); self._records.append(record)
            if self._raw_store is not None:
                self._raw_store.append(record)
            if self._owner._update_consumer is not None:
                from .message_delivery import deliver_message
                deliver_message(self,self._binding_projection,self._owner._update_consumer,
                    record.raw.frame,record.sequence,dict(record.values),record.raw.time_ns,canonical_keys=True)

    def __next__(self):
        """交付全局时间非递减的有界批，最终EOF后保完成事实。参数: 无。返回: SignalBatch。异常: EOF/原读/预算/合同错。
        """
        if self._closed or self._exhausted:
            raise StopIteration
        if self._failed:
            raise ResultClosedError('失败的文本CAN读取只能清理')
        try:
            self._owner._ensure_open()
            self._current=None; _release_owned_ram(self,self._batch_cost,'_batch_cost')
            if self._eof_sent:
                self._finish(); raise StopIteration
            if not self._records or self._column>=max(1,len(self._definitions)):
                self._fill()
            if not self._records and self._raw_eof:
                self._eof_sent=True
                return self._accept(SignalBatch(self._owner.spec.name,self._request.session_id,{},
                    self._decoder.last_ns,True,self._decoder.last_ns))
            column_count=min(self._request.batch_rows,max(1,len(self._definitions)-self._column))
            _reserve_owned_ram(self,65536+(2*self._records_cost+16384)*column_count,'_batch_cost')
            columns={}
            if self._definitions:
                for definition in self._definitions[self._column:self._column+column_count]:
                    columns[definition.name]=pack_text_records(definition,tuple(self._records),self._request.session_id,self._owner.backend)
            self._column+=column_count
            # watermark含端点；尚待交付的别名可能从块首开始，因此只能推进到首点前1ns。
            progress=self._records[-1].raw.time_ns if self._column>=max(1,len(self._definitions)) else self._records[0].raw.time_ns
            watermark=None if progress is None or progress==-(1<<63) else progress-1
            return self._accept(SignalBatch(self._owner.spec.name,self._request.session_id,columns,watermark,False,None))
        except StopIteration:
            raise
        except BaseException as error:
            self._failed=True
            _cleanup_owner(self,error,'text_can_observation_cleanup_owner','文本CAN观测读取')
            raise

    def _finish(self):
        """封口可选原帧仓，解析器真正关闭后提交完整事实。参数: 无。返回: None。异常: 封口/关闭/预算错。
        """
        if not self._decoder.exhausted:
            raise ValueError('文本原始解析器没有真正到达EOF')
        raw=self._decoder
        fact=CANObservation(self._owner.spec.name,self._request.session_id,self._request,self.identity,
            raw.first_ns,raw.last_ns,raw.count,True,
            self._owner._blf_time_scope if self._owner._blf_time_scope!='source' else
            'selected' if self._owner._selected_ids is not None and self._owner.spec.source_type=='raw_can_csv' else 'source',
            raw.retained_count)
        metadata=dict(raw.metadata,decode_calls=raw.decode_calls,record_count=raw.count,source_kind=self._owner.spec.source_type)
        _reserve_owned_ram(self,65536+_metadata_bytes(metadata)*32,'_runtime_cost')
        self._runtime_metadata=freeze_metadata(metadata)
        if self._raw_store is not None:
            self._raw_store.seal()
        self._decoder.close(); self._decoder=None
        self._observation=fact; self._exhausted=True

    def take_raw_store(self,receiver,slot):
        """移交本read的同次封口原帧仓。参数: receiver空槽及slot名。返回: None。异常: 未完成/已有责任。
        """
        self.observation
        if self._raw_store is None or self._raw_store.state!='sealed' or getattr(receiver,slot,None) is not None:
            raise ValueError('文本原帧仓不能移交')
        setattr(receiver,slot,self._raw_store); self._raw_store=None

    def close(self):
        """关闭实际解析器/原帧仓并释放自身费用，不释放共享DBC。参数: 无。返回: None。异常: 原清理错可恢复。
        """
        if self._closed:
            return
        self._current=None; self._records.clear(); self._validator=None
        if self._decoder is not None:
            self._decoder.close(); self._decoder=None
        if self._raw_store is not None:
            self._raw_store.close(); self._raw_store=None
        self._runtime_metadata=self._observation=self._binding_projection=None
        for slot in ('_update_cost','_batch_cost','_records_cost','_pending_cost','_validation_cost','_runtime_cost','_fixed_cost'):
            _release_owned_ram(self,getattr(self,slot),slot)
        self._owner._requests.discard(self); self._closed=True
