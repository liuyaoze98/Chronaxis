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
import pickle
import struct
from time import perf_counter
from uuid import uuid4

from ..results.budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..sources.models import freeze_metadata
from ..sources.protocol import SourceReadError
from .history import _metadata_bytes
from .parallel_can_worker import BLOCK_RAM, WIRE_LIMIT, worker_main


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
        self._slots=[];self._file_slots={};self._facts={}
        self._next_file=self._index=self._offset=self._sequence=0
        self._records=();self._position=0;self._pending_eof=False
        self._last_time=self._last_order=None
        self._metadata=None;self._root=None;self._paths=[];self._handles=[];self._heap=[]
        self._closed=self._exhausted=self._started=self._spooled=False
        self.count=self.decode_calls=self.retained_count=0
        self.first_ns=self.last_ns=None
        self.timings=dict(worker_read_seconds=0.,worker_serialize_seconds=0.,worker_wait_seconds=0.,
                          worker_send_seconds=0.,main_wait_seconds=0.,received_bytes=0,worker_pids=[],files={})
        try:
            _reserve_owned_ram(self,1048576+32*_metadata_bytes((
                tuple(str(item.path) for item in spec.inputs),signals,self._options)), '_fixed_cost')
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
        metadata=freeze_metadata(pickle.loads(self._bytes(slot,reply[2])))
        if self._metadata is None:
            self._metadata=metadata
        elif metadata!=self._metadata:
            raise SourceReadError('并行文件使用的DBC元数据不一致')
        self._file_slots[index]=slot
        # 每槽只许可一个块；许可之前已在父账本支付远端及接收空间。
        slot['control'].send(('next',))

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
                slot=dict(process=None,control=None,data=None,tree=None,file=self._next_file,started=False)
                self._slots.append(slot)
                child_control=child_data=None
                try:
                    parent_control,child_control=context.Pipe();slot['control']=parent_control
                    parent_data,child_data=context.Pipe(duplex=False);slot['data']=parent_data
                    process=context.Process(target=worker_main,args=(child_control,child_data));slot['process']=process
                    process.start();slot['started']=True
                    if os.name=='nt':
                        from ..batch.process_tree import ProcessTree
                        slot['tree']=ProcessTree(process.pid)
                finally:
                    if child_control is not None:
                        child_control.close()
                    if child_data is not None:
                        child_data.close()
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
        number,records,eof,facts=pickle.loads(packet)
        if number!=slot['block'] or type(records) is not list or len(records)>64:
            raise SourceReadError('CAN文件数据块序号或长度不符')
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
            # 已完成时温和退出；未完成/背压/崩溃统一结束本次树，不触及其他进程。
            if slot['started'] and process is not None:
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
                if slot['tree'] is not None:
                    slot['tree'].close();slot['tree']=None
                if process.is_alive():
                    raise SourceReadError('CAN工作进程尚未退出')
                if completed and process.exitcode!=0:
                    failure=SourceReadError(f'CAN工作进程退出码不是0：{process.exitcode}')
                process.close()
                slot['process']=None
            for key in ('control','data'):
                if slot[key] is not None:
                    slot[key].close();slot[key]=None
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
                    self._budget.reserve_spool(4+len(packet)+(32 if self._integrity else 0))
                    writers[index].write(struct.pack('!I',len(packet)))
                    if self._integrity:
                        writers[index].write(sha256(packet).digest())
                    writers[index].write(packet)
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
        for index in range(len(self._handles)):
            self._push(index)
        self._spooled=True

    def _push(self,index):
        """为一个有序文件取下一记录，堆键固定时间/文件位置/局部序号。参数: index。返回: None。异常: 暂存截断。
        """
        records,position=self._stream_records[index]
        while position==len(records):
            header=self._handles[index].read(4)
            if not header:
                self._stream_records[index]=((),0)
                return
            if len(header)!=4:
                raise SourceReadError('CAN归并暂存长度头截断')
            size=struct.unpack('!I',header)[0]
            if not 0<size<=WIRE_LIMIT:
                raise SourceReadError('CAN归并暂存数据块长度非法')
            expected=self._handles[index].read(32) if self._integrity else None
            packet=self._handles[index].read(size)
            if len(packet)!=size:
                raise SourceReadError('CAN归并暂存数据块截断')
            if expected is not None and sha256(packet).digest()!=expected:
                raise SourceReadError('CAN归并暂存完整性校验失败')
            _,records,_,_=pickle.loads(packet);position=0
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
                result=replace(record,input_index=index,sequence=self._sequence)
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
                result=replace(record,input_index=self._index,sequence=self._offset+record.raw.sequence)
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
        self._metadata=None
        _release_owned_ram(self,self._merge_cost,'_merge_cost')
        _release_owned_ram(self,self._fixed_cost,'_fixed_cost')
        self._closed=True
