"""按文件并行解码并恢复一个来源的连续记录流。

concatenate只预读每个工作进程的一块，按文件顺序消费；time_order先把已校验
的有序文件流写入本次受配额约束的暂存，再稳定归并。父层继续使用原同刻组及
状态机。所有工作进程、管道、暂存和费用归本owner，关闭不会删除输入或他人文件。
"""
from dataclasses import replace
import heapq
from hashlib import sha256
import multiprocessing
import os
from pathlib import Path
import struct
from time import perf_counter
from uuid import uuid4

from .._control_wire import ControlChannel
from .can_block_codec import decode_block, decode_metadata
from ..results.budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..sources.models import freeze_metadata
from ..sources.protocol import SourceReadError
from .history import _metadata_bytes
from .parallel_can_worker import BLOCK_RAM, WIRE_LIMIT, worker_main


def _with_position(record, input_index, sequence):
    """给本入口刚从固定块核验完成的记录重编号，不再解析其不可变字段键。

    参数: record只能来自本次decode_block；input_index和sequence是待写入的新非负编号。
    返回: 新冻结记录；原始帧、字段值、状态和重建事实继续共享已核不可变内容。
    异常: 新编号、类型、状态或字段对结构非法时沿用内部工厂检查。
    仅供本模块已核记录使用；外部记录构造和新块解码仍完整解析规范字段。
    临时键集合至多4096项，按512+192*4096字节小于1MiB；它在已有8MiB
    接收/归并空间中、6MiB模型上界以外的2MiB余量内，用完即释放，不跨记录缓存。
    """
    from ..sources.text_can_decode import DecodedCANRecord
    if type(record) is not DecodedCANRecord:
        raise TypeError('CAN重编号需要本次已核解码记录')
    keys = None
    try:
        keys = {pair[0] for pair in record.values}
        return DecodedCANRecord._from_bound_values(record.source, input_index, sequence,
            record.raw, record.values, record.status, record.frame_values, record.frame_layout, keys)
    finally:
        if keys is not None:
            keys.clear()
        keys = None


class ParallelCANDecodeRead:
    """拥有有限文件工作槽及唯一有序输出；文件EOF不结束来源。

    各槽最多一个在途块。父预付子账本上限及接收展开空间，记录的长期消费者
    自行计费；归并时工作进程已退出，再为每个打开的暂存块预付空间。
    """

    def __init__(self,spec,budget,signals,*,process_count,work_dir,emit_frame_ids=None,**options):
        """保存冻结文件任务，不读输入。参数: 来源/共享预算/绑定及执行选项。返回: owner。异常: 类型/预算。
        """
        self.spec,self._budget,self.signals=spec,budget,signals
        self._process_count=min(process_count,len(spec.inputs))
        self._work_dir=Path(work_dir)
        self._options=dict(options,emit_frame_ids=emit_frame_ids)
        self._integrity=options.get('integrity',True)
        context=self._options.pop('database_context',None)
        self._frame_context=None if context is None else (context.rules,context._cycle_periods,context._integrity if hasattr(context,'_integrity') else options.get('integrity',True))
        self._held_cost=self._fixed_cost=self._workers_cost=self._merge_cost=0
        self._metadata_extra_cost=0
        self._metadata_credit=self._metadata_model_cost=self._ready_model_cost=0
        self._slots=[];self._file_slots={};self._facts={}
        self._next_file=self._index=self._offset=self._sequence=0
        self._records=();self._position=0;self._pending_eof=False
        self._last_time=self._last_order=None
        self._metadata=None;self._root=None;self._paths=[];self._handles=[];self._heap=[]
        self._disk_blocks=[];self._disk_eof=[]
        self._closed=self._exhausted=self._started=self._spooled=False
        self.count=self.decode_calls=self.retained_count=0
        self.first_ns=self.last_ns=None
        self.timings=dict(worker_read_seconds=0.,worker_serialize_seconds=0.,worker_wait_seconds=0.,
                          worker_send_seconds=0.,main_wait_seconds=0.,received_bytes=0,worker_pids=[],files={})
        try:
            declarations = _metadata_bytes((tuple(str(item.path) for item in spec.inputs),signals,self._options))
            # 原32D预约不变。其中8D只用于持久READY及其暂存，不再算作其它阶段余量。
            # 余24D+1MiB覆盖原声明D、两份固定控制容器至多2D，以及最坏JSON转义下
            # 当前文本/ASCII片/累计编码三份至多18D；小头、64KiB片和其它槽用固定余量。
            # send返回即释放编码树，READY不与本槽控制编码或前一数据块重叠。
            self._metadata_credit=8*declarations
            _reserve_owned_ram(self,1048576+32*declarations, '_fixed_cost')
        except BaseException as error:
            _cleanup_owner(self,error,'text_can_cleanup_owner','并行CAN构造')
            raise

    @property
    def closed(self):
        """返回实际关闭事实。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    @property
    def exhausted(self):
        """返回完整来源结束事实。参数: 无。返回: bool。异常: 无。"""
        return self._exhausted

    @property
    def metadata(self):
        """返回同次DBC元数据。参数: 无。返回: 冻结映射。异常: 未开始时拒绝。"""
        if self._metadata is None:
            raise SourceReadError('并行CAN尚未初始化元数据')
        return self._metadata

    def _receive(self,slot):
        """接收独立控制消息并监测退出。参数: 工作槽。返回: tuple。异常: 子错误/崩溃/取消。
        """
        started=perf_counter()
        while slot.get('reply') is None:
            # 每个槽最多保留一个控制通知；后续文件的错误不必等前文件读完才暴露。
            for other in self._slots:
                if other.get('control') is not None and other.get('reply') is None and other['control'].poll():
                    try:
                        message=other['control'].recv()
                    except EOFError as error:
                        raise SourceReadError('CAN工作进程控制连接提前关闭') from error
                    if message[0]=='error':
                        raise SourceReadError(f"{self.spec.inputs[other['file']].path}: {message[1]}: {message[2]}")
                    other['reply']=message
            if slot.get('reply') is not None:
                break
            if slot['process'].exitcode is not None:
                raise SourceReadError(f"CAN工作进程意外退出：{self.spec.inputs[slot['file']].path}，退出码{slot['process'].exitcode}")
            slot['control'].poll(0.05)
        self.timings['main_wait_seconds']+=perf_counter()-started
        try:
            reply=slot.pop('reply')
        except EOFError as error:
            raise SourceReadError('CAN工作进程控制连接提前关闭') from error
        if reply[0]=='error':
            raise SourceReadError(f"{self.spec.inputs[slot['file']].path}: {reply[1]}: {reply[2]}")
        return reply

    def _bytes(self,slot,size):
        """接收已预付且限定长度的数据。参数: 槽/声明长度。返回: bytes。异常: 断连/协议错。
        """
        if type(size) is not int or not 0<size<=WIRE_LIMIT:
            raise SourceReadError('CAN数据块声明长度非法')
        while not slot['data'].poll(0.05):
            if slot['process'].exitcode is not None:
                raise SourceReadError('CAN工作进程在传输中退出')
        packet=slot['data'].recv_bytes(WIRE_LIMIT)
        if len(packet)!=size:
            raise SourceReadError('CAN数据块长度不符')
        self.timings['received_bytes']+=size
        return packet

    def _assign(self,slot,index):
        """给空闲进程一个冻结文件并核元数据。参数: 槽/文件位置。返回: None。异常: 读取或声明不符。
        """
        slot.update(file=index,block=0)
        spec=replace(self.spec,inputs=(self.spec.inputs[index],),file_merge='concatenate')
        slot['control'].send(('file',spec,self.signals,self._options,self._worker_limit,self._frame_context))
        reply=self._receive(slot)
        if reply[0]!='ready' or reply[1]!=slot['process'].pid:
            raise SourceReadError('CAN工作进程初始化身份不符')
        self._accept_metadata(self._bytes(slot,reply[2]))
        self._file_slots[index]=slot
        # 每槽只许可一个块；许可之前已在父账本支付远端及接收空间。
        slot['control'].send(('next',))

    def _accept_metadata(self,packet):
        """在原费用份额内接收READY，仅为实际超出的固定图预付差额。

        参数: packet为已按512KiB上限接收的当前包。
        返回: None，首份冻结事实保留到close，后续只比较后释放。
        异常: 包错误、事实不同、预算或取消；退款失败附注保原错及可重试拥有者。
        """
        decoded=metadata=None
        self._ready_model_cost=0
        size=len(packet)
        def reserve_model(amount):
            """先给新图及冻结副本付费。参数: amount单图上界。返回: None。异常: 原预算错误。"""
            self._ready_model_cost=amount
            # 首份已保留的图先占8D；超过8D的持久差额另有真实_metadata_extra_cost。
            # 当前槽8MiB只在没有数据块时使用。未知DBC单位由包内文本费用覆盖。
            free_credit=max(0,self._metadata_credit-self._metadata_model_cost)
            persistent=max(0,self._metadata_model_cost-self._metadata_credit)
            required=persistent+max(0,2*amount+size-BLOCK_RAM-free_credit)
            if required>self._metadata_extra_cost:
                _reserve_owned_ram(self,required-self._metadata_extra_cost,'_metadata_extra_cost')
        try:
            decoded=decode_metadata(packet,on_expand=reserve_model)
            metadata=freeze_metadata(decoded)
            if self._metadata is None:
                extra=max(0,self._ready_model_cost-self._metadata_credit)
                if extra>self._metadata_extra_cost:
                    # 同一费用槽从暂存转为持久事实，只补差额，不把同一冻结图付两次。
                    # 数据槽仍持有当前图时完成预约，worker退出后仍有真实登记。
                    _reserve_owned_ram(self,extra-self._metadata_extra_cost,'_metadata_extra_cost')
                self._metadata=metadata
                self._metadata_model_cost=self._ready_model_cost
            elif metadata!=self._metadata:
                raise SourceReadError('并行文件使用的DBC元数据不一致')
        except BaseException as error:
            decoded=metadata=packet=None
            try:
                persistent=max(0,self._metadata_model_cost-self._metadata_credit)
                _release_owned_ram(self,self._metadata_extra_cost-persistent,'_metadata_extra_cost')
            except BaseException as cleanup:
                error.add_note('READY暂存退款失败: '+type(cleanup).__name__)
            raise
        else:
            decoded=metadata=packet=None
            persistent=max(0,self._metadata_model_cost-self._metadata_credit)
            _release_owned_ram(self,self._metadata_extra_cost-persistent,'_metadata_extra_cost')
        finally:
            self._ready_model_cost=0

    def prepare_metadata(self):
        """启动有限工作槽，只初始化DBC再授予首块。参数: 无。返回: 元数据。异常: 启动/预算/元数据错。
        """
        if self._closed:
            raise SourceReadError('并行CAN已关闭')
        if self._started:
            return self.metadata
        try:
            # DBC估算与现有文本读取器一致，另计绑定图、单块构造及父接收展开。
            self._worker_limit=BLOCK_RAM+4*1048576+self.spec.dbc_path.stat().st_size*64+64*_metadata_bytes((self.signals,self._options,self._frame_context))
            _reserve_owned_ram(self,self._process_count*(self._worker_limit+BLOCK_RAM),'_workers_cost')
            context=multiprocessing.get_context('spawn')
            for _ in range(self._process_count):
                slot=dict(process=None,control=None,data=None,child_control=None,child_data=None,
                          tree=None,startup=None,file=self._next_file,started=False)
                self._slots.append(slot)
                slot['control'],slot['child_control']=context.Pipe()
                slot['control']=ControlChannel(slot['control'],'can',parent=True,max_bytes=self._worker_limit)
                slot['child_control']=ControlChannel(slot['child_control'],'can',parent=False,max_bytes=self._worker_limit)
                slot['data'],slot['child_data']=context.Pipe(duplex=False)
                from .._process_start import spawn_entry
                try:
                    target,args,slot['startup']=spawn_entry(context,worker_main,(slot['child_control'],slot['child_data']))
                except BaseException as error:
                    slot['startup']=getattr(error,'process_start_cleanup_owner',None)
                    raise
                process=context.Process(target=target,args=args)
                slot['process']=process
                process.start();slot['started']=True
                from ..batch.process_tree import ProcessTree
                try:
                    slot['tree']=(ProcessTree(process.pid) if slot['startup'] is None else
                        ProcessTree(process.pid,registration=slot['startup'],process=process))
                except BaseException as error:
                    slot['tree']=getattr(error,'process_tree_cleanup_owner',None)
                    raise
                if slot['startup'] is not None:
                    slot['startup'].close();slot['startup']=None
                for key in ('child_control','child_data'):
                    connection=slot[key]
                    try:
                        connection.close()
                    finally:
                        if connection.closed:
                            slot[key]=None
                self.timings['worker_pids'].append(process.pid)
                self._assign(slot,self._next_file)
                self._next_file+=1
            self._started=True
            return self.metadata
        except BaseException as error:
            _cleanup_owner(self,error,'text_can_cleanup_owner','并行CAN启动')
            raise

    def _block(self,index):
        """收一块并记录已见事实，原始计数不以传输记录数替代。参数: 文件位置。返回: 块。异常: 协议/读取错误。
        """
        slot=self._file_slots[index]
        reply=self._receive(slot)
        if reply[0]!='block':
            raise SourceReadError('CAN数据块控制类型不符')
        packet=self._bytes(slot,reply[1])
        sent=self._receive(slot)
        if sent[0]!='sent':
            raise SourceReadError('CAN数据块缺少发送完成确认')
        number,records,eof,facts=decode_block(packet)
        if number!=slot['block'] or type(records) is not list or len(records)>64:
            raise SourceReadError('CAN文件数据块序号或长度不符')
        self._record_identity(index,records)
        slot['block']+=1
        self.timings['worker_read_seconds']+=reply[2]
        self.timings['worker_serialize_seconds']+=reply[3]
        self.timings['worker_wait_seconds']+=reply[4]
        self.timings['worker_send_seconds']+=sent[1]
        profile=self.timings['files'].setdefault(str(index),dict(pid=slot['process'].pid,read_seconds=0.,
            serialize_seconds=0.,credit_wait_seconds=0.,send_seconds=0.,bytes=0,max_block_bytes=0))
        for name,value in zip(('read_seconds','serialize_seconds','credit_wait_seconds','send_seconds'),(*reply[2:5],sent[1])):
            profile[name]+=value
        profile['bytes']+=len(packet);profile['max_block_bytes']=max(profile['max_block_bytes'],len(packet))
        self._facts[index]=facts
        self.count=sum(f['count'] for f in self._facts.values())
        self.decode_calls=sum(f['decode_calls'] for f in self._facts.values())
        starts=[f['first_ns'] for f in self._facts.values() if f['first_ns'] is not None]
        ends=[f['last_ns'] for f in self._facts.values() if f['last_ns'] is not None]
        self.first_ns=min(starts) if starts else None
        self.last_ns=max(ends) if ends else None
        return records,eof,facts,packet

    def _record_identity(self,index,records):
        """核当前包的来源和文件身份，不将包内路径用作新文件打开目标。

        参数: index为当前输入位置，records为本包已恢复记录。
        返回: None。
        异常: 来源、原文件或序号不同步时SourceReadError。
        """
        expected=self.spec.inputs[index].path
        if any(record.source!=self.spec.name or record.input_index!=0
                or record.raw.path!=expected or record.sequence!=record.raw.sequence for record in records):
            raise SourceReadError('CAN数据块来源或原文件身份不符')

    def _next_task(self,index):
        """完成文件后复用同一工作槽；没有下一文件时保留槽待统一关闭。参数: 文件位置。返回: None。异常: 初始化错。
        """
        slot=self._file_slots.pop(index)
        if self._next_file<len(self.spec.inputs):
            self._assign(slot,self._next_file)
            self._next_file+=1

    def _stop_workers(self,*,completed=False):
        """关闭全部本次进程和管道，不等待满管道自行排空。参数: 无。返回: None。异常: 真实关闭失败保留槽。
        """
        failure=None
        while self._slots:
            slot=self._slots[-1];process=slot['process']
            # 按实际PID识别start已经生效后取消，不能只依赖尚未来得及写入的started标志。
            if process is not None and not getattr(process,'_closed',False) and process.pid is not None:
                if process.is_alive():
                    try:
                        slot['control'].send(('close',))
                    except (OSError,EOFError):
                        pass
                    process.join(2 if completed else 0.15)
                if process.is_alive():
                    process.terminate();process.join(2)
                    if completed:
                        failure=SourceReadError('CAN工作进程未正常结束')
                if process.is_alive() and slot['tree'] is not None:
                    slot['tree'].close();slot['tree']=None
                if process.is_alive():
                    raise SourceReadError('CAN工作进程尚未退出')
                if completed and process.exitcode!=0:
                    failure=SourceReadError(f'CAN工作进程退出码不是0：{process.exitcode}')
            if slot['tree'] is not None:
                slot['tree'].close();slot['tree']=None
            if process is not None:
                if not getattr(process,'_closed',False):
                    process.close()
                slot['process']=None
            for key in ('control','data','child_control','child_data','startup'):
                connection=slot.get(key)
                if connection is not None:
                    try:
                        connection.close()
                    finally:
                        if connection.closed:
                            slot[key]=None
            self._slots.pop()
        self._file_slots.clear()
        _release_owned_ram(self,self._workers_cost,'_workers_cost')
        if failure is not None:
            raise failure

    def _prepare_sorted(self):
        """先流式暂存已校验文件，再释放进程额度开始归并。参数: 无。返回: None。异常: 配额/IO/原输入错误。
        """
        root=self._work_dir/('file-merge-'+uuid4().hex)
        root.mkdir(parents=True,exist_ok=False)
        self._root=root
        writers={}
        try:
            # 轮询已就绪槽，不让慢文件阻止其他文件继续解码和受配额约束地落盘。
            while self._file_slots:
                ready=[index for index,slot in self._file_slots.items() if slot.get('reply') is not None or slot['control'].poll() or slot['process'].exitcode is not None]
                if not ready:
                    index=next(iter(self._file_slots))
                    self._file_slots[index]['control'].poll(0.05)
                    continue
                for index in ready:
                    records,eof,facts,packet=self._block(index)
                    if index not in writers:
                        path=self._root/(str(index)+'.blocks')
                        handle=path.open('xb');self._paths.append(path);writers[index]=handle
                    # CND1本身的8字节头提供落盘分帧，不再重复保存一份包长。
                    self._budget.reserve_spool(len(packet)+(32 if self._integrity else 0))
                    writers[index].write(packet[:8])
                    if self._integrity:
                        writers[index].write(sha256(packet).digest())
                    writers[index].write(memoryview(packet)[8:])
                    # 释放接收对象后再许可下一块，禁止两块同时占用同一额度。
                    records=packet=None
                    if eof:
                        writers.pop(index).close();self._next_task(index)
                    else:
                        self._file_slots[index]['control'].send(('next',))
        finally:
            for handle in writers.values():
                handle.close()
        self._stop_workers(completed=True)
        # 每个归并输入最多保留一个有界块；过多文件不足预算时明确失败。
        _reserve_owned_ram(self,len(self.spec.inputs)*BLOCK_RAM,'_merge_cost')
        for index in range(len(self.spec.inputs)):
            handle=(self._root/(str(index)+'.blocks')).open('rb');self._handles.append(handle)
        self._stream_records=[((),0) for _ in self._handles]
        self._disk_blocks=[0 for _ in self._handles]
        self._disk_eof=[False for _ in self._handles]
        for index in range(len(self._handles)):
            self._push(index)
        self._spooled=True

    def _push(self,index):
        """为一个有序文件取下一记录，堆键固定时间/文件位置/局部序号。参数: index。返回: None。异常: 暂存截断。
        """
        records,position=self._stream_records[index]
        while position==len(records):
            header=self._handles[index].read(8)
            if not header:
                if not self._disk_eof[index]:
                    raise SourceReadError('CAN归并暂存缺少文件EOF')
                self._stream_records[index]=((),0)
                return
            if self._disk_eof[index]:
                raise SourceReadError('CAN归并暂存在EOF后仍有数据')
            if len(header)!=8:
                raise SourceReadError('CAN归并暂存长度头截断')
            magic,size=struct.unpack('!4sI',header)
            if magic!=b'CND1' or not 0<size<=WIRE_LIMIT-8:
                raise SourceReadError('CAN归并暂存数据块版本或长度非法')
            expected=self._handles[index].read(32) if self._integrity else None
            body=self._handles[index].read(size)
            if len(body)!=size:
                raise SourceReadError('CAN归并暂存数据块截断')
            packet=header+body
            body=None
            if expected is not None and sha256(packet).digest()!=expected:
                raise SourceReadError('CAN归并暂存完整性校验失败')
            number,records,eof,_=decode_block(packet)
            if number!=self._disk_blocks[index]:
                raise SourceReadError('CAN归并暂存块序号不符')
            self._record_identity(index,records)
            self._disk_blocks[index]+=1
            self._disk_eof[index]=eof
            position=0
        record=records[position]
        self._stream_records[index]=(records,position+1)
        heapq.heappush(self._heap,(record.raw.time_ns,index,record.raw.sequence,record))

    def __iter__(self):
        """返回本次游标。参数: 无。返回: self。异常: 无。"""
        return self

    def __next__(self):
        """返回按明确归并政策排序的下一记录。参数: 无。返回: DecodedCANRecord。异常: EOF或读取/预算错。
        """
        if self._closed or self._exhausted:
            raise StopIteration
        try:
            self.prepare_metadata()
            if self.spec.file_merge=='time_order':
                if not self._spooled:
                    self._prepare_sorted()
                if not self._heap:
                    self._exhausted=True
                    raise StopIteration
                _,index,_,record=heapq.heappop(self._heap)
                result=_with_position(record,index,self._sequence)
                self._sequence+=1
                self._push(index)
            else:
                while self._position==len(self._records):
                    self._records=()
                    if self._pending_eof:
                        fact=self._facts[self._index]
                        if fact['first_order_time'] is not None and self._last_order is not None and fact['first_order_time']<self._last_order:
                            raise SourceReadError('CAN文件边界时间回退；请核对时间或显式选择file_merge: time_order')
                        self._last_order=fact['last_order_time'] if fact['last_order_time'] is not None else self._last_order
                        self._offset+=fact['count'];self._next_task(self._index);self._index+=1
                        self._pending_eof=False
                    if self._index==len(self.spec.inputs):
                        self._stop_workers(completed=True);self._exhausted=True
                        raise StopIteration
                    records,eof,fact,packet=self._block(self._index)
                    if fact['first_order_time'] is not None and self._last_order is not None and fact['first_order_time']<self._last_order:
                        raise SourceReadError('CAN文件边界时间回退；请核对时间或显式选择file_merge: time_order')
                    self._records=records;self._position=0;self._pending_eof=eof
                    # 当前块已由父接收额度承担，子侧原额度可构造下一块；二者费用分别预付。
                    packet=None
                    if not eof:
                        self._file_slots[self._index]['control'].send(('next',))
                record=self._records[self._position];self._position+=1
                result=_with_position(record,self._index,self._offset+record.raw.sequence)
            if result.raw.time_ns is not None and self._last_time is not None and result.raw.time_ns<self._last_time:
                raise SourceReadError('CAN归并输出时间回退')
            self._last_time=result.raw.time_ns;self.retained_count+=1
            return result
        except StopIteration:
            raise
        except BaseException as error:
            _cleanup_owner(self,error,'text_can_cleanup_owner','并行CAN读取')
            raise

    def close(self):
        """释放本次进程、块和登记暂存。参数: 无。返回: None。异常: 清理失败可重试。
        """
        if self._closed:
            return
        self._records=();self._heap.clear()
        if hasattr(self,'_stream_records'):
            self._stream_records.clear()
        self._stop_workers()
        while self._handles:
            self._handles[-1].close();self._handles.pop()
        while self._paths:
            self._paths[-1].unlink(missing_ok=True);self._paths.pop()
        if self._root is not None:
            self._root.rmdir();self._root=None
        self._metadata=None;self._metadata_model_cost=0
        _release_owned_ram(self,self._metadata_extra_cost,'_metadata_extra_cost')
        _release_owned_ram(self,self._merge_cost,'_merge_cost')
        _release_owned_ram(self,self._fixed_cost,'_fixed_cost')
        self._closed=True
