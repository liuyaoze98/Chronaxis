"""一个积分工作槽按许可读取文件并生成原序面积块或同刻组点块。

读取器和数值状态在子进程中关闭，父进程拥有整个进程生命周期。文件错误
先保留已经形成的边界/面积前缀，下一次许可才交付错误。eof数据包晚于
读取器和数值owner关闭，finished确认再证明包工作区已释放。没有许可时
不继续读取，不生成面积文件或最终结果。

任务的mode决定数值owner：terms构造FileIntegralTerms并发P5I1面积包（concatenate）；
points构造FileGroupPoints并发P5G1组点包（time_order，PERF-P5-ORDER-01）。
两种模式共用命令协议、许可与释放次序。points模式的错误信息只带str(错误)，
不附加notes，与现有time_order读取的格式一致；其父进程把各阶段错误都按读取段报告。
"""
import os
import signal
from time import perf_counter

from .._control_wire import ControlChannel
from ..results.budget import ResourceBudget
from ..sources.text_can_decode import CANTextDecodeRead
from .can_block_codec import encode_metadata
from .integral_blocks import (BLOCK_RAM, WIRE_LIMIT, MAX_EVENTS, MAX_POINTS, MODEL_LIMIT, event_cost, facts_cost,
                              point_cost, point_facts_cost, encode_packet, encode_points, restore_task, task_mode)
from .parallel_can_worker import plain

READ_LIMIT = 4096  # 一次读取许可最多推进4096条原记录；也可因事件数或字节上限提前返回。


def _points(terms):
    """判断数值owner是否为组点模式。参数: terms为FileIntegralTerms或FileGroupPoints。返回: bool。异常: 无。"""
    from .file_group_points import FileGroupPoints
    return type(terms) is FileGroupPoints


def _limits(terms):
    """取得当前模式的事件费用函数、事实费用函数和单包事件上限。

    参数: terms为FileIntegralTerms或FileGroupPoints。
    返回: tuple，依次为event费用函数、facts费用函数和单包最大事件数int。
    异常: 无；未知owner按面积模式处理，由原编码器拒绝未知事件。
    """
    return (point_cost,point_facts_cost,MAX_POINTS) if _points(terms) else (event_cost,facts_cost,MAX_EVENTS)


def _facts(reader, terms, compatibility):
    """摘取同次文件事实。

    参数: reader为CANTextDecodeRead；terms为FileIntegralTerms或FileGroupPoints；compatibility为本文件的提示缓存dict。
    返回: dict，含累计原帧/解码数、实际首末纳秒、精确顺序时间、帧型提示tuple和frame_identity
        （本文件目标帧实际帧型或None，两种模式都带，父进程据此跨文件核对）。
    异常: 非法内部对象时AttributeError；不读取下一帧。
    """
    fields=terms.compatibility_fields
    # 同一已证明物理帧的兼容字段只会增加；共享已冻结tuple，避免每块重复复制提示。
    if compatibility.get('size')!=len(fields):
        compatibility.update(size=len(fields),values=tuple((field.key,extended) for field,extended in fields.items()))
    facts=dict(count=reader.count,first_ns=reader.first_ns,last_ns=reader.last_ns,
        decode_calls=reader.decode_calls,first_order_time=reader.first_order_time,
        last_order_time=reader._last_selected_time,
        compatibility_fields=compatibility['values'],frame_identity=terms.frame_identity)
    return facts


def _error_text(error, notes=True):
    """保留原错误及有限清理说明。

    参数: error为BaseException；notes为False时只返回str(错误)（组点模式，与现有time_order读取格式一致）。
    返回: str。异常: 原对象字符串转换错误继续传播。
    """
    if not notes:return str(error)
    notes=getattr(error,'__notes__',())
    return str(error)+''.join('\n'+str(note)[:256] for note in notes[:4])


def _close_file(reader, terms, primary=None):
    """关闭数值和读取资源，保留首个错误。

    参数: reader为CANTextDecodeRead或None；terms为FileIntegralTerms或None；
        primary为已有BaseException或None，默认None。
    返回: BaseException或None；保留已有主错，把后续清理错误写入其说明。
    异常: 两资源的close异常作为返回值交付，不直接抛出。
    """
    for owner in (terms,reader):
        if owner is None:continue
        try:owner.close()
        except BaseException as error:
            if primary is None:primary=error
            else:primary.add_note('积分文件清理失败：'+type(error).__name__)
    return primary


def read_events(reader, terms, compatibility):
    """读取一批原记录，返回已形成事件及真实EOF或原错误。

    参数: reader为同次CANTextDecodeRead；terms为FileIntegralTerms或FileGroupPoints；
        compatibility为本文件有限提示缓存dict。
    返回: 五元tuple，依次为(event, facts)条目的tuple、eof bool、Exception或None、
        阶段str（read或compute）及最新facts dict。此eof尚未证明后续资源关闭成功。
    异常: KeyboardInterrupt/SystemExit原样抛；数据错误保留在返回值，先交付数值前缀；
        没有主错时，事实整理失败原样传播。
    组点模式下FileGroupPoints停止交付后仍继续读取，使同一文件后面的读取错误照常报出。
    """
    events=[];eof=False;failure=None;phase='read';wire=model=0;fact_costs={}
    cost_of,facts_cost_of,maximum=_limits(terms)
    facts=_facts(reader,terms,compatibility)
    def append(items):
        """只为实际事件保存同次事实。参数: 有限事件tuple。返回: None。异常: 编码模型错误。"""
        nonlocal wire,model,facts
        facts=_facts(reader,terms,compatibility)
        for event in items:
            cost=cost_of(event);wire+=cost[0];model+=cost[1]+1024
            events.append((event,facts))
    try:
        for _ in range(READ_LIMIT):
            phase='read'
            try:record=next(reader)
            except StopIteration:
                phase='compute'
                append(terms.finish());eof=True;break
            phase='compute'
            emitted=terms.feed(record)
            if emitted:
                append(emitted)
                # 同一许可允许真正批量读取/计算；宽列按字节和展开量提前结束。
                # 最后一次feed/finish额外产生的少数事件由发送层继续分包，不重读或丢弃。
                facts_wire,facts_model=facts_cost_of(facts,fact_costs)
                if len(events)>=maximum or wire+facts_wire>=WIRE_LIMIT or model+facts_model>=MODEL_LIMIT:break
    except (KeyboardInterrupt,SystemExit):raise
    except Exception as error:
        failure=error
        try:append(terms.drain_prefix_on_error())
        except BaseException as finish_error:
            failure.add_note('积分错误前缀终结失败：'+type(finish_error).__name__)
    try:facts=_facts(reader,terms,compatibility)
    except BaseException as error:
        if failure is None:raise
        failure.add_note('积分错误事实整理失败：'+type(error).__name__)
    return tuple(events),eof,failure,phase,facts


def take_events(items, last_facts, *, points=False):
    """从已形成前缀中取得一份有界多事件包，不触发下一次读取。

    参数: items为(event, facts)条目tuple；last_facts为本批最后读取事实dict；
        points为True时按组点包的费用和每包2048个事件封包，默认False按面积包。
    返回: 三元tuple，依次为本包事件tuple、剩余(event, facts)条目tuple、本包facts dict；
        items为空时仍校验并交付last_facts。
    异常: 单事件连同事实或空包事实超限时ValueError；未知事件时IntegralBlockError，原事实错误继续传播。
    不扩大队列、不截短精确时间，也不丢弃尚未发送的事件。
    """
    cost_of,facts_cost_of,maximum=(point_cost,point_facts_cost,MAX_POINTS) if points else (event_cost,facts_cost,MAX_EVENTS)
    count=wire=model=0;fact_costs={}
    for index,(event,event_facts) in enumerate(items):
        size,expanded=cost_of(event)
        facts_wire,facts_model=facts_cost_of(last_facts if index==len(items)-1 else event_facts,fact_costs)
        if size+facts_wire>WIRE_LIMIT or expanded+facts_model>MODEL_LIMIT:
            raise ValueError('积分单事件超过预付块空间')
        if count>=maximum or wire+size+facts_wire>WIRE_LIMIT or model+expanded+facts_model>MODEL_LIMIT:break
        wire+=size;model+=expanded;count+=1
    chosen=items[:count];remaining=items[count:]
    facts=chosen[-1][1] if remaining else last_facts
    if not items:
        facts_wire,facts_model=facts_cost_of(facts,fact_costs)
        if facts_wire>WIRE_LIMIT or facts_model>MODEL_LIMIT:raise ValueError('积分事实超过预付块空间')
    return tuple(item[0] for item in chosen),remaining,facts


def worker_main(control, data):
    """处理固定文件、配置及next命令，不创建子工作进程。

    参数: control为integral族的ControlChannel；data为只发送二进制包的Connection。
    返回: None，收到关闭指令或父进程断连后结束。
    异常: control类型或通道族不符时TypeError；运行数据错误按阶段发回父进程，
        与父进程通信的EOFError、BrokenPipeError或OSError导致退出；最终未能清理的资源错误原样抛出。
    """
    if type(control) is not ControlChannel or control.family!='integral':raise TypeError('积分工作进程需要固定控制端点')
    signal.signal(signal.SIGINT,signal.SIG_IGN)
    reader=terms=budget=None;index=number=0;pending_error=None;workspace=False
    points=False  # 当前文件的任务模式；terms关闭后仍用它选择包格式和错误文本。
    file_mode=None  # 文件命令声明的模式；None表示由configure的任务决定。
    packet=events=packet_facts=None
    pending_events=();pending_facts=None;pending_eof=False;pending_phase='read';compatibility={}
    try:
        while True:
            command=control.recv()
            if command[0]=='close':break
            phase='read' if command[0]=='file' else 'compute'
            try:
                if command[0]=='file':
                    if reader is not None or terms is not None or workspace:raise ValueError('积分槽尚未关闭上一文件')
                    _,index,spec,signals,options,limit,context,*declared=command
                    if context is not None:raise ValueError('并行积分不接受原帧捕获上下文')
                    number=0;pending_error=None;pending_events=();pending_facts=None;pending_eof=False;compatibility={}
                    # 文件命令带模式时，READY前的错误也按该模式报告（points不附notes）；缺省时等configure决定。
                    file_mode=declared[0] if declared else None
                    points=file_mode=='points'
                    budget=ResourceBudget(limit);budget.reserve_ram(BLOCK_RAM);workspace=True
                    reader=CANTextDecodeRead(spec,budget,signals,**options)
                    packet=encode_metadata(plain(reader.prepare_metadata()))
                    control.send(('ready',index,os.getpid(),len(packet)));data.send_bytes(packet);packet=None
                    continue
                if command[0]=='configure':
                    if command[1]!=index or reader is None or terms is not None or pending_error is not None:
                        raise ValueError('积分数值任务的文件或状态不符')
                    from .file_integral_terms import FileIntegralTerms
                    from .file_group_points import FileGroupPoints
                    if command[3]<budget.memory_budget_bytes:raise ValueError('积分工作预算不能缩减已预约份额')
                    budget.memory_budget_bytes=command[3]
                    # 任务模式决定构造面积生成器还是组点生成器；两者接收同一组重建参数。
                    mode=task_mode(command[2])
                    if file_mode is not None and mode!=file_mode:raise ValueError('积分任务模式与文件命令不符')
                    points=mode=='points'
                    terms=(FileGroupPoints if points else FileIntegralTerms)(budget,**restore_task(command[2]))
                    continue
                if command[0]=='budget':
                    if reader is None or terms is not None or command[1]<budget.memory_budget_bytes:
                        raise ValueError('积分预算安装时机或金额非法')
                    budget.memory_budget_bytes=command[1];control.maximum=command[1]
                    continue
                if command[0]!='next':raise ValueError('积分工作进程收到未知命令')
                if pending_error is not None and not pending_events:
                    pending_error=_close_file(reader,terms,pending_error);reader=terms=None
                    # 前缀已经交付；先撤销所有引用，再退其工作区。清理错不能取代数据主错。
                    pending_facts=packet_facts=packet=events=None;compatibility.clear()
                    if workspace:
                        try:budget.release_ram(BLOCK_RAM);workspace=False
                        except BaseException as cleanup:pending_error.add_note('积分块退款失败：'+type(cleanup).__name__)
                    control.send(('error',index,number,pending_phase,type(pending_error).__name__,_error_text(pending_error,not points)))
                    pending_error=None
                    continue
                started=perf_counter()
                if not pending_events:
                    if reader is None or terms is None:raise ValueError('积分文件尚未准备数值任务')
                    pending_events,pending_eof,pending_error,pending_phase,pending_facts=read_events(reader,terms,compatibility)
                    if pending_eof or pending_error is not None:
                        original=pending_error
                        # EOF只关闭读取器。尚待发送的数值事件继续占有数值费用和块工作区。
                        pending_error=_close_file(reader,None,pending_error)
                        if original is None and pending_error is not None:pending_phase='cleanup'
                        reader=None
                        pending_eof=pending_eof and pending_error is None
                events,pending_events,packet_facts=take_events(pending_events,pending_facts,points=points)
                final=pending_eof and not pending_events
                if final:
                    # 只剩至多一包展开量时由BLOCK_RAM覆盖；数值owner先完成自己的清理。
                    pending_error=_close_file(None,terms);terms=None
                    if pending_error is not None:pending_phase='cleanup';final=pending_eof=False
                packet=(encode_points if points else encode_packet)(index,number,events,final,packet_facts)
                control.send(('block',index,number,len(packet),perf_counter()-started))
                data.send_bytes(packet)
                packet=events=packet_facts=None;number+=1
                if final:
                    pending_facts=None;compatibility.clear()
                    phase='cleanup'
                    # 成功确认必须晚于最后数据包发送和实际持有费用释放。
                    if workspace:budget.release_ram(BLOCK_RAM);workspace=False
                    if budget.ram_bytes:raise RuntimeError('积分文件结束后仍有未释放预算')
                    control.send(('finished',index,number))
            except (EOFError,BrokenPipeError):raise
            except BaseException as error:
                # 已有读取/计算主错时，前缀编码或退款失败只能补充说明，不能换掉主错。
                primary=pending_error if pending_error is not None else error
                if primary is not error:primary.add_note('积分错误前缀交付失败：'+type(error).__name__)
                reported_phase=pending_phase if pending_error is not None else phase
                failure=_close_file(reader,terms,primary);reader=terms=None
                pending_events=();pending_facts=packet_facts=packet=events=None;compatibility.clear()
                if workspace:
                    try:budget.release_ram(BLOCK_RAM);workspace=False
                    except BaseException as cleanup:failure.add_note('积分块退款失败：'+type(cleanup).__name__)
                control.send(('error',index,number,reported_phase,type(failure).__name__,_error_text(failure,not points)))
                pending_error=None
    except (EOFError,BrokenPipeError,OSError):
        pass
    finally:
        failure=_close_file(reader,terms)
        pending_events=();pending_facts=packet_facts=packet=events=None;compatibility.clear()
        if workspace:
            try:budget.release_ram(BLOCK_RAM);workspace=False
            except BaseException as cleanup:
                if failure is None:failure=cleanup
                else:failure.add_note('积分块最终退款失败：'+type(cleanup).__name__)
        try:control.close()
        finally:data.close()
        if failure is not None:raise failure
