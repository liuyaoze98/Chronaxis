"""按文件原序交付面积事件的有限工作进程池。

每槽只拥有一份待交付块。后文件的元数据、数据块和文件错误可先到达，
但只在轮到该文件时生效；基础设施故障立即结束。所有子进程、端点及预算
归本owner，取消不会等待堵塞的数据管道自行排空。
"""
from dataclasses import replace
import multiprocessing
from sys import getsizeof
from time import perf_counter

from .._control_wire import ControlChannel, ControlProtocolError
from ..results.budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..sources.models import freeze_metadata
from ..sources.protocol import SourceReadError
from .can_block_codec import decode_metadata
from .history import _metadata_bytes
from .integral_blocks import BLOCK_RAM, WIRE_LIMIT, decode_packet, pack_task
from .parallel_integral_worker import worker_main

_TASK_BASE_COST = 1048576  # 每份任务的固定编码/重建空间，前置下界与真实预约共用。


def _configuration_rows(batch_intervals: int, calculation_count: int) -> int:
    """取得实际工作块行数。参数: 正批上限和非负计算项数。返回: 1至64。异常: ValueError。"""
    if type(batch_intervals) is not int or batch_intervals < 1:
        raise ValueError('积分批次上限需要正整数')
    if type(calculation_count) is not int or calculation_count < 0:
        raise ValueError('积分计算项数需要非负整数')
    return min(batch_intervals,64,max(1,131072//max(64,calculation_count*9+64)))


def _task_bytes(value):
    """估算本模块已生成JSON树的实际容器费用。

    参数: value为pack_task产生的有限dict/list及原生标量。返回: int，保守预约字节数。
    异常: 发现非固定类型时TypeError；不把list传给只接受冻结容器的历史估算器。
    """
    if type(value) is dict:
        return getsizeof(value)+sum(128+_task_bytes(key)+_task_bytes(item) for key,item in value.items())
    if type(value) is list:return getsizeof(value)+sum(32+_task_bytes(item) for item in value)
    if value is None or type(value) in (str,int,float,bool):return getsizeof(value)+64
    raise TypeError('积分任务费用只接受固定JSON树')


def _startup_costs(spec,signals,process_count,options):
    """只读估算基础工作槽，不打开原报文。

    参数: spec为CANTextSpec；signals为SignalDefinition序列；process_count为正整数上限；
        options为共用读取选项dict。
    返回: tuple[int, int, int]，单位均为字节，依次为池固定费、每工作进程额度和全部槽费用；
        槽费用含每子额度与对应父接收空间，不含数值任务和READY实际图。
    异常: DBC文件stat失败时OSError；静态声明估算原错误继续传播。
    """
    declarations=_metadata_bytes((tuple(str(item.path) for item in spec.inputs),tuple(signals),options))
    fixed=1048576+32*declarations
    worker=BLOCK_RAM+4*1048576+spec.dbc_path.stat().st_size*64+64*_metadata_bytes((tuple(signals),options))
    return fixed,worker,min(process_count,len(spec.inputs))*(worker+BLOCK_RAM)


class ParallelIntegralPool:
    """持有一个连续来源的工作槽及有界待交付状态，不累计数值总量。"""

    _FILE_MERGE = 'concatenate'  # 本类接受的来源文件合并方式；子类按自己的模式覆盖。

    def __init__(self,spec,budget,signals,*,process_count,**options):
        """登记来源并预约固定声明空间，不读原文件。

        参数: CANTextSpec、共享预算、原信号定义、正整数进程上限和既有读取选项。
        返回: None，构造新的池owner。
        异常: 非法进程数、非接续来源、空文件列表或原帧捕获上下文时ValueError；
            预算不足时BudgetExceededError，构造清理失败附parallel_integral_pool_cleanup_owner。
        """
        # 本类只服务concatenate面积；time_order组点由子类ParallelPointPool放宽此项。
        if type(process_count) is not int or process_count<1 or spec.file_merge!=self._FILE_MERGE:
            raise ValueError('并行积分需要正整数进程数及'+self._FILE_MERGE+'来源')
        if not spec.inputs:raise ValueError('并行积分需要至少一个文件')
        self.spec,self._budget,self.signals=spec,budget,tuple(signals)
        self._options=dict(options);self._frame_context=self._options.pop('database_context',None)
        if self._frame_context is not None:raise ValueError('并行积分不保留原帧上下文')
        self._process_count=min(process_count,len(spec.inputs))
        self._held_cost=self._fixed_cost=self._workers_cost=self._task_cost=self._metadata_cost=0
        self._persistent_metadata=0
        self._slots=[];self._file_slots={};self._next_file=self._current=0
        self._started=self._closed=self._configured=self._iterating=False
        self._task=None;self._metadata=None;self._worker_limit=0
        self.file_facts={};self.compatibility_fields={}
        self.count=self.decode_calls=0;self.first_ns=self.last_ns=None
        self.first_order_time=self.last_order_time=None
        self._previous_order=None
        self.timings=dict(worker_compute_seconds=0.0,main_wait_seconds=0.0,received_bytes=0,
                          worker_pids=[],files={})
        try:
            amount=_metadata_bytes((tuple(str(item.path) for item in spec.inputs),self.signals,self._options))
            _reserve_owned_ram(self,1048576+32*amount,'_fixed_cost')
        except BaseException as error:
            _cleanup_owner(self,error,'parallel_integral_pool_cleanup_owner','积分池构造');raise

    @staticmethod
    def startup_cost(spec,signals,*,process_count,**options):
        """查询构造和启动全部槽的额外费用，供首帧前选择路径。

        参数: 与构造相同的spec、signals、process_count及读取options。
        返回: int，全部启动预约字节数，不含数值任务和READY实际图。
        异常: 进程数或上下文不合法时ValueError，DBC stat失败时OSError；声明估算原错继续传播。
        不创建进程、不读取报文、不修改账本。
        """
        if type(process_count) is not int or process_count<1:raise ValueError('积分进程数需要正整数')
        context=options.pop('database_context',None)
        if context is not None:raise ValueError('并行积分不保留原帧上下文')
        fixed,_,workers=_startup_costs(spec,signals,process_count,options)
        return fixed+workers

    @staticmethod
    def configuration_minimum_cost(calculation_count: int, *, process_count: int,
                                   file_count: int, batch_intervals: int = 64) -> int:
        """查询全部工作槽数值任务的必要费用下界，用于创建进程前排除必然不足的预算。

        参数: calculation_count为非负计算项数；process_count/file_count为正进程上限/文件数；
            batch_intervals为用户正整数区间批上限，与真实配置共用行数限制。
        返回: int字节数，含父任务与每个工作槽的固定重建、数值状态；不含DBC和声明图。
        异常: 非法数量或批上限时ValueError；不创建进程、任务树或修改预算。
        """
        from .file_integral_terms import file_terms_minimum_cost
        if any(type(value) is not int or value < 1 for value in (process_count,file_count)):
            raise ValueError('积分进程数和文件数需要正整数')
        rows=_configuration_rows(batch_intervals,calculation_count)
        worker=_TASK_BASE_COST+file_terms_minimum_cost(calculation_count,batch_intervals=rows)
        return _TASK_BASE_COST+min(process_count,file_count)*worker

    @property
    def closed(self):
        """返回实际关闭事实。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    @property
    def metadata(self):
        """返回首文件DBC事实。参数: 无。返回: Mapping[str, object]，只读冻结映射。异常: 尚未准备时SourceReadError。"""
        if self._metadata is None:raise SourceReadError('积分池尚未准备元数据')
        return self._metadata

    def _dispatch(self,slot,index):
        """给空槽派发下一文件，不等待其初始化。参数: 槽/文件序号。返回: None。异常: 发送失败。"""
        slot.update(file=index,number=0,ready=False,metadata=None,packet=None,error=None,configured=False,requested=False,idle=False,await_finish=False,finished=False)
        spec=replace(self.spec,inputs=(self.spec.inputs[index],),file_merge='concatenate')
        slot['control'].send(('file',index,spec,self.signals,self._options,self._worker_limit,None))
        self._file_slots[index]=slot

    def _start(self):
        """创建有界槽并按文件序派发。参数: 无。返回: None。异常: 启动/预算/端点错误。"""
        if self._started:return
        _,self._worker_limit,workers=_startup_costs(self.spec,self.signals,self._process_count,self._options)
        # 父接收区同时覆盖READY冻结图及一个面积包；worker额度单独预付。
        _reserve_owned_ram(self,workers,'_workers_cost')
        context=multiprocessing.get_context('spawn')
        from .._process_start import spawn_entry
        from ..batch.process_tree import ProcessTree
        for _ in range(self._process_count):
            slot=dict(process=None,control=None,data=None,child_control=None,child_data=None,
                      tree=None,startup=None,file=self._next_file,packet=None,error=None,ready=False)
            self._slots.append(slot)
            slot['control'],slot['child_control']=context.Pipe()
            slot['control']=ControlChannel(slot['control'],'integral',parent=True,max_bytes=self._worker_limit)
            slot['child_control']=ControlChannel(slot['child_control'],'integral',parent=False,max_bytes=self._worker_limit)
            slot['data'],slot['child_data']=context.Pipe(duplex=False)
            try:target,args,slot['startup']=spawn_entry(context,worker_main,(slot['child_control'],slot['child_data']))
            except BaseException as error:
                slot['startup']=getattr(error,'process_start_cleanup_owner',None);raise
            process=context.Process(target=target,args=args);slot['process']=process;process.start()
            try:
                slot['tree']=(ProcessTree(process.pid) if slot['startup'] is None else
                    ProcessTree(process.pid,registration=slot['startup'],process=process))
            except BaseException as error:
                slot['tree']=getattr(error,'process_tree_cleanup_owner',None);raise
            if slot['startup'] is not None:slot['startup'].close();slot['startup']=None
            for key in ('child_control','child_data'):
                slot[key].close();slot[key]=None
            self.timings['worker_pids'].append(process.pid)
            self._dispatch(slot,self._next_file);self._next_file+=1
        self._started=True

    def _bytes(self,slot,size):
        """接收已预付的一个包。参数: 槽/声明大小。返回: bytes。异常: 断连/长度错误。"""
        if type(size) is not int or not 0<size<=WIRE_LIMIT:raise ControlProtocolError('积分包声明长度非法')
        while not slot['data'].poll(0.05):
            if slot['process'].exitcode is not None:raise SourceReadError('积分工作进程在传输中退出')
        packet=slot['data'].recv_bytes(WIRE_LIMIT)
        if len(packet)!=size:raise ControlProtocolError('积分包长度不符')
        self.timings['received_bytes']+=size
        return packet

    def _configure_slot(self,slot):
        """仅在READY后安装数值任务并许可首块。参数: 槽。返回: None。异常: 发送错误。"""
        if (self._task is None or not slot.get('ready') or slot.get('configured') or slot.get('error') is not None):return
        # 新任务的临时编码及编译额度已在configure中预付，端点上限同步到实际worker额度。
        slot['control'].maximum=self._worker_limit
        slot['control'].send(('budget',self._worker_limit))
        slot['control'].send(('configure',slot['file'],self._task,self._worker_limit))
        slot['configured']=True
        self._request(slot)

    def _request(self,slot):
        """授予单块额度，不允许同时保留待交付包和另一个在途包。参数: 槽。返回: None。异常: 状态错误。"""
        if slot.get('requested') or slot.get('packet') is not None or slot.get('error') is not None or slot.get('await_finish'):
            raise ControlProtocolError('积分槽重复申请块')
        slot['control'].send(('next',));slot['requested']=True

    def _poll_controls(self):
        """缓存各文件控制消息，数据错误不抢先抛给用户。

        参数: 无。返回: bool，是否接收到至少一条控制消息。
        异常: 协议不一致时ControlProtocolError，工作进程退出时SourceReadError；
            端点错误立即传播，未来文件的数据错误仅缓存，不抢先作为当前文件错误抛出。
        """
        changed=False
        for slot in self._slots:
            if slot.get('idle') or slot.get('error') is not None or slot.get('packet') is not None:continue
            control=slot['control']
            if control.poll():
                message=control.recv();changed=True
                if message[0]=='error':
                    if message[1]!=slot['file'] or message[2]!=slot['number']:
                        raise ControlProtocolError('积分错误的文件或块序号不符')
                    slot['error']=(message[3],message[4],message[5]);slot['requested']=False
                elif message[0]=='ready':
                    if slot['ready'] or message[1]!=slot['file'] or message[2]!=slot['process'].pid:
                        raise ControlProtocolError('积分READY身份不符')
                    slot['metadata']=self._bytes(slot,message[3])
                    slot['ready']=True;self._configure_slot(slot)
                elif message[0]=='block':
                    if not slot.get('requested') or message[1]!=slot['file'] or message[2]!=slot['number']:
                        raise ControlProtocolError('积分块许可或序号不符')
                    slot['packet']=self._bytes(slot,message[3]);slot['requested']=False
                    self.timings['worker_compute_seconds']+=message[4]
                    clock=self.timings['files'].setdefault(str(slot['file']),dict(pid=slot['process'].pid,compute_seconds=0.0,bytes=0))
                    clock['compute_seconds']+=message[4];clock['bytes']+=len(slot['packet'])
                elif message[0]=='finished':
                    if (not slot.get('await_finish') or slot.get('finished')
                            or message[1]!=slot['file'] or message[2]!=slot['number']):
                        raise ControlProtocolError('积分文件释放确认的状态或序号不符')
                    slot['finished']=True
                else:raise ControlProtocolError('积分工作进程响应非法')
            elif slot['process'].exitcode is not None:
                # 进程崩溃是基础设施故障；不能等待未来数据或把退出当成合法EOF。
                raise SourceReadError(f"积分工作进程意外退出：{self.spec.inputs[slot['file']].path}，退出码{slot['process'].exitcode}")
        return changed

    def _wait(self,slot,*,metadata=False,finished=False):
        """等待当前文件状态，并接收其他工作槽的有限通知。

        参数: slot为当前文件槽dict；metadata和finished默认False，分别选择等待READY或资源释放确认；
            两者都为False时等数据包，metadata为True时优先等待READY。
        返回: None，指定状态已到达。
        异常: 当前文件错误按原阶段传播；任何工作槽的协议、端点或进程故障立即传播。
        """
        started=perf_counter()
        try:
            while not (slot.get('ready') if metadata else slot.get('finished') if finished else slot.get('packet') is not None):
                if slot.get('error') is not None:self._raise_file(slot)
                if not self._poll_controls():slot['control'].poll(0.05)
            if slot.get('error') is not None:self._raise_file(slot)
        finally:self.timings['main_wait_seconds']+=perf_counter()-started

    def _raise_file(self,slot):
        """按固定阶段保留异常类型，不按远端字符串导入任意类。

        参数: 当前文件槽。返回: 不返回。异常: 读取/清理包装SourceReadError；
            数值阶段仅恢复明确列出的标准及项目异常，其余仍保留类型文本。
        """
        phase,name,message=slot['error']
        if phase=='compute':
            from ..results.errors import BudgetExceededError, ResultFormatError, ResultClosedError
            from ..core.integral_sum import IntegralStateLimitError
            from ..timebase.conversion import TimeOverflowError
            known=(ValueError,TypeError,OverflowError,ZeroDivisionError,RuntimeError,
                   BudgetExceededError,ResultFormatError,ResultClosedError,IntegralStateLimitError,TimeOverflowError)
            exception=next((kind for kind in known if kind.__name__==name),None)
            if exception is not None:raise exception(message)
        raise SourceReadError(f"{self.spec.inputs[slot['file']].path}: {name}: {message}")

    def _accept_metadata(self,slot):
        """按文件序核共同DBC事实。参数: READY槽。返回: None。异常: 元数据不一致。"""
        packet=slot['metadata'];amount=0;candidate=decoded=None
        def reserve_model(size):
            """先预约正在展开的两份元数据图。参数: 单图bytes。返回: None。异常: 预算原错。"""
            nonlocal amount
            amount=size
            required=self._persistent_metadata+2*size
            if required>self._metadata_cost:
                _reserve_owned_ram(self,required-self._metadata_cost,'_metadata_cost')
        try:
            decoded=decode_metadata(packet,on_expand=reserve_model);candidate=freeze_metadata(decoded)
            if self._metadata is None:self._metadata=candidate;self._persistent_metadata=amount
            elif candidate!=self._metadata:raise SourceReadError('连续文件的同次DBC元数据不一致')
        finally:
            decoded=candidate=packet=None;slot['metadata']=None
            _release_owned_ram(self,self._metadata_cost-self._persistent_metadata,'_metadata_cost')

    def prepare_metadata(self):
        """准备首文件元数据，不读取任何原帧。参数: 无。返回: 冻结元数据。异常: 启动/文件错。"""
        if self._closed:raise SourceReadError('积分池已经关闭')
        if self._metadata is not None:return self._metadata
        try:
            self._start();slot=self._file_slots[0];self._wait(slot,metadata=True);self._accept_metadata(slot)
            return self._metadata
        except BaseException as error:
            _cleanup_owner(self,error,'parallel_integral_pool_cleanup_owner','积分池准备');raise

    def _configuration(self,definitions,expressions,specs,binding,session_id,derived,domain,batch_intervals,step_ns=None):
        """构造固定任务并计算配置实际需要的额外预约费用。

        参数: definitions、expressions、specs、binding、session_id、derived和domain为已验证数值声明；
            batch_intervals为用户的正整数区间批上限，传输块会进一步限到64项及字节预算；
            step_ns为None（实际间隔）或固定间隔正纳秒，写入任务后由工作进程核验。
        返回: tuple[dict, int, int]，依次为固定task、父任务字节费和每子数值/任务额外字节费；
            不包含已预约的启动费。
        异常: 批上限非法时ValueError；原声明展开或静态费用错误继续传播。
        """
        from .file_integral_terms import file_terms_cost
        rows=_configuration_rows(batch_intervals,len(specs))
        declared=_metadata_bytes((definitions,expressions[0].bindings,
            tuple((item.text,item.root.unit) for item in expressions),specs,binding,derived,domain))
        task=pack_task(definitions,expressions,specs,binding,session_id,derived=derived,domain=domain,batch_intervals=rows,
                       step_ns=step_ns)
        task_size=_task_bytes(task)
        parent=_TASK_BASE_COST+32*max(declared,task_size)
        # 32D覆盖控制JSON最坏转义、编码副本、解析树和重建声明；数值状态另按真正构造费预约。
        worker=_TASK_BASE_COST+32*task_size+file_terms_cost(definitions,expressions,specs,derived,batch_intervals=rows)
        return task,parent,worker

    def configuration_cost(self,definitions,expressions,specs,binding,session_id,*,derived=(),domain=None,batch_intervals=64,
                           step_ns=None):
        """查询configure还将预约的总费用，供首帧前预算准入。

        参数: 与configure相同的实际声明，含同一step_ns。返回: int，父任务费与全部工作槽额外费之和，单位字节；不修改账本、不启动读取。
        异常: 声明错误；调用方应在原计划已有固定工作区内使用短暂的任务结构。
        """
        _,parent,worker=self._configuration(definitions,expressions,specs,binding,session_id,derived,domain,batch_intervals,
                                            step_ns)
        return parent+self._process_count*worker

    def configure(self,definitions,expressions,specs,binding,session_id,*,derived=(),domain=None,batch_intervals=64,
                  step_ns=None):
        """安装实际有效期与表达式，之后才允许读取。

        参数: 实际定义、静态表达式、指标、共同定位、会话及原派生/请求域；batch_intervals为用户上限；
            step_ns为父积分器共用的间隔（None为实际间隔），随任务发给每个工作进程。
        返回: None。异常: 未准备、重复安装或预算/声明错误。
        """
        if self._closed or self._configured or self._metadata is None:raise ValueError('积分池数值配置时机错误')
        try:
            if type(batch_intervals) is not int or batch_intervals<1:raise ValueError('积分批次上限需要正整数')
            # 原计划图由调用方持有；在复制任务JSON树之前先预付新增容器及控制编码空间。
            declaration_size=_metadata_bytes((definitions,expressions[0].bindings,
                tuple((item.text,item.root.unit) for item in expressions),specs,binding,derived,domain))
            _reserve_owned_ram(self,_TASK_BASE_COST+32*declaration_size,'_task_cost')
            task,amount,extra=self._configuration(definitions,expressions,specs,binding,session_id,derived,domain,batch_intervals,
                                                  step_ns)
            if amount>self._task_cost:_reserve_owned_ram(self,amount-self._task_cost,'_task_cost')
            _reserve_owned_ram(self,self._process_count*extra,'_workers_cost')
            self._worker_limit+=extra;self._task=task;self._configured=True
            for slot in self._slots:self._configure_slot(slot)
        except BaseException as error:
            _cleanup_owner(self,error,'parallel_integral_pool_cleanup_owner','积分池配置');raise

    def _accept_facts(self,index,facts):
        """按消费顺序更新同次读取得到的事实。参数: 文件号/固定facts。返回: None。异常: 计数或字段回退。"""
        from ..sources.can_spec import can_field_from_key
        if (facts['first_order_time'] is not None and self._previous_order is not None
                and facts['first_order_time']<self._previous_order):
            raise SourceReadError('CAN文件边界时间回退；请核对时间或显式选择file_merge: time_order')
        previous=self.file_facts.get(index)
        if previous is not None and (facts['count']<previous['count'] or facts['decode_calls']<previous['decode_calls']):
            raise ControlProtocolError('积分文件计数回退')
        # 同一文件已记录的实际帧型不会改变；文件内混用已由读取器报错。
        if (previous is not None and previous['frame_identity'] is not None
                and facts['frame_identity']!=previous['frame_identity']):
            raise ControlProtocolError('积分文件的实际帧型改变')
        self.file_facts[index]=facts
        self.count+=facts['count']-(0 if previous is None else previous['count'])
        self.decode_calls+=facts['decode_calls']-(0 if previous is None else previous['decode_calls'])
        if facts['first_ns'] is not None:
            self.first_ns=facts['first_ns'] if self.first_ns is None else min(self.first_ns,facts['first_ns'])
        if facts['last_ns'] is not None:
            self.last_ns=facts['last_ns'] if self.last_ns is None else max(self.last_ns,facts['last_ns'])
        if self.first_order_time is None:self.first_order_time=facts['first_order_time']
        if facts['last_order_time'] is not None:self.last_order_time=facts['last_order_time']
        for key,extended in facts['compatibility_fields']:
            self.compatibility_fields[can_field_from_key(key)]=extended

    def iter_file(self,index):
        """按配置文件序交付固定事件；未来文件错误在轮到时才抛。

        参数: index为下一待消费文件的零起序号int，必须按来源声明顺序单次消费。
        返回: 生成器，依次产生FileIntegralHead、IntegralTermsChunk、FileIntegralTail或FileIntegralFrontier；
            收到eof数据包后仍等待finished资源释放确认，之后才自然结束并复用槽。
        异常: 调用次序不合法时ValueError；文件数据错误按阶段传播，协议故障时ControlProtocolError；
            失败自动清理自有进程与费用。
        """
        if self._closed or not self._configured or self._iterating or index!=self._current:
            raise ValueError('积分文件必须按原序单次消费')
        self._iterating=True
        try:
            slot=self._file_slots[index];self._wait(slot,metadata=True)
            if slot['metadata'] is not None:self._accept_metadata(slot)
            while True:
                self._wait(slot);raw=slot.pop('packet');slot['packet']=None
                packet=decode_packet(raw);raw=None
                if packet.file_index!=index or packet.number!=slot['number']:raise ControlProtocolError('积分包内身份不符')
                slot['number']+=1;self._accept_facts(index,packet.facts)
                slot['await_finish']=packet.eof
                for event in packet.events:yield event
                eof=packet.eof;packet=None;event=None
                if eof:
                    # 最后数据送达并不等于资源释放成功；确认后才可复用槽或公布整文件成功。
                    self._wait(slot,finished=True)
                    break
                self._request(slot)
            self._file_slots.pop(index);self._current+=1
            if self.file_facts[index]['last_order_time'] is not None:
                self._previous_order=self.file_facts[index]['last_order_time']
            if self._next_file<len(self.spec.inputs):
                self._dispatch(slot,self._next_file);self._next_file+=1
            else:slot['idle']=True
        except GeneratorExit:
            self.close();raise
        except BaseException as error:
            _cleanup_owner(self,error,'parallel_integral_pool_cleanup_owner','积分池读取');raise
        finally:
            # 诊断异常不能在迭代帧中保留已经退款的数据块或工作槽。
            raw=packet=event=slot=None
            self._iterating=False

    def close(self):
        """关闭进程、管道和费用；失败保留真实owner以便重试。

        参数: 无。返回: None，可重复调用。异常: 持续退出/关闭/预算释放失败。
        """
        if self._closed:return
        completed=self._current==len(self.spec.inputs);failure=None
        while self._slots:
            slot=self._slots[-1];process=slot['process']
            if process is not None and not getattr(process,'_closed',False) and process.pid is not None:
                if process.is_alive():
                    try:slot['control'].send(('close',))
                    except (OSError,EOFError):pass
                    process.join(2 if completed else .15)
                if process.is_alive():
                    process.terminate();process.join(2)
                    if completed:failure=SourceReadError('积分工作进程未正常关闭')
                if process.is_alive() and slot['tree'] is not None:
                    slot['tree'].close();slot['tree']=None
                if process.is_alive():raise SourceReadError('积分工作进程尚未退出')
                if completed and process.exitcode!=0:failure=SourceReadError('积分工作进程退出码不是0')
            if slot['tree'] is not None:slot['tree'].close();slot['tree']=None
            if process is not None and not getattr(process,'_closed',False):process.close()
            slot['process']=None
            for key in ('control','data','child_control','child_data','startup'):
                connection=slot.get(key)
                if connection is not None:
                    try:connection.close()
                    finally:
                        if connection.closed:slot[key]=None
            self._slots.pop()
            slot.clear()
        self._file_slots.clear();self._task=None;self._metadata=None;self._persistent_metadata=0
        _release_owned_ram(self,self._metadata_cost,'_metadata_cost')
        _release_owned_ram(self,self._workers_cost,'_workers_cost')
        _release_owned_ram(self,self._task_cost,'_task_cost')
        _release_owned_ram(self,self._fixed_cost,'_fixed_cost')
        self._closed=True
        if failure is not None:raise failure
