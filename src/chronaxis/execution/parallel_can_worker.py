"""单个可复用CAN文件工作进程：读取、解码并按许可交付有限数据块。

每个工作进程只解析一个当前文件，不启动子进程，不运行事件或积分状态机。
父进程预付全部工作空间后授予一次next许可；控制错误独立于数据块发送。
文件EOF保留观测事实，等待下一文件任务；来源EOF由父进程统一判定。
"""
from collections.abc import Mapping
from dataclasses import replace
import os
import signal
from time import perf_counter

from .._control_wire import ControlChannel
from .can_block_codec import encode_block, encode_metadata
from ..results.budget import ResourceBudget
from ..sources.text_can_decode import CANTextDecodeRead

# 条数和估算占用共同决定何时交付；合法记录不能因同批信号较多而被拒绝。
BLOCK_ROWS = 64
WIRE_LIMIT = 524288
BLOCK_RAM = 8 * 1048576
RECORD_RAM_LIMIT = BLOCK_RAM // 2
BLOCK_OBJECT_TARGET = BLOCK_RAM // 4


def plain(value):
    """转换有限冻结元数据为可传输结构。参数: JSON式值。返回: 独立容器。异常: 无。
    """
    if isinstance(value, Mapping):
        return {key: plain(item) for key,item in value.items()}
    if isinstance(value,(tuple,list)):
        return tuple(plain(item) for item in value)
    return value


def facts(reader):
    """摘取同次读取得到的有限事实，不把观测末点当水位。参数: reader。返回: dict。异常: 无。
    """
    return dict(count=reader.count,first_ns=reader.first_ns,last_ns=reader.last_ns,
                decode_calls=reader.decode_calls,first_order_time=reader.first_order_time,
                last_order_time=reader._last_selected_time)


def read_block(reader):
    """在固定预付空间内读取一块，不为凑满64条继续读取宽记录。

    参数: reader为逐条解码游标。返回: (records, eof)；只有实际读到EOF才置真。
    异常: 单条记录超过原4MiB估算上限或读取失败；不丢弃、回读或重排记录。
    """
    from .history import _metadata_bytes
    records=[]
    record_cost=0
    for _ in range(BLOCK_ROWS):
        try:
            record=next(reader)
        except StopIteration:
            return records,True
        cost=16384+32*_metadata_bytes((record.values,record.frame_values,
            record.frame_layout,str(record.raw.path),getattr(record.raw,'raw_time',None),
            bytes(record.raw.frame.data)))
        if cost>RECORD_RAM_LIMIT:
            raise ValueError('CAN单条记录对象超过已预约空间')
        records.append(record)
        record_cost+=cost
        # 加入前不足2MiB，末条至多4MiB，所以整块不足6MiB；原8MiB预付中
        # 仍有至少2MiB容纳512KiB传输块及编码副本。达到目标就交付，不预读下一条。
        if record_cost>=BLOCK_OBJECT_TARGET:
            break
    return records,False


def worker_main(control, data):
    """等待文件/读取许可并发送有界结果。参数: 独立控制和数据连接。返回: None。异常: 父断连退出。

    生命周期由父拥有；正常文件结束关闭解析器，异常先发错误控制消息再关闭。
    任意时刻取消可由父终止工作进程；不等待满数据管道才能报告错误。
    """
    if type(control) is not ControlChannel:
        raise TypeError('CAN工作进程需要固定字节控制端点')
    reader = context = None
    block_number = 0
    # 控制台取消由父负责结束完整进程树，不能让子在写块中途单独捕获Ctrl+C。
    signal.signal(signal.SIGINT,signal.SIG_IGN)
    try:
        while True:
            waited=perf_counter()
            command=control.recv()
            wait_seconds=perf_counter()-waited
            if command[0]=='close':
                break
            if command[0]=='file':
                _,spec,signals,options,limit,frame_context=command
                budget=ResourceBudget(limit)
                # 固定块工作空间涵盖构造、序列化及发送副本；父已预约同一额度。
                budget.reserve_ram(BLOCK_RAM)
                if frame_context is not None:
                    from .frame_capture import FrameDBCContext
                    rules,cycles,integrity=frame_context
                    context=FrameDBCContext(spec.dbc_path,rules,budget,cycle_periods=cycles,integrity=integrity)
                reader=CANTextDecodeRead(spec,budget,signals,database_context=context,**options)
                metadata=plain(reader.prepare_metadata())
                packet=encode_metadata(metadata)
                if len(packet)>WIRE_LIMIT:
                    raise ValueError('CAN文件元数据超过传输块上限')
                # 先给控制通知，父再接有上限的数据，避免等待相反通道造成死锁。
                control.send(('ready',os.getpid(),len(packet)))
                data.send_bytes(packet)
                block_number=0
                continue
            if command[0]!='next' or reader is None:
                raise ValueError('CAN工作进程收到非法读取许可')
            started=perf_counter()
            records,eof=read_block(reader)
            decoded=perf_counter()-started
            started=perf_counter()
            packet=encode_block(block_number,records,eof,facts(reader))
            serialized=perf_counter()-started
            if len(packet)>WIRE_LIMIT:
                raise ValueError('CAN数据块超过字节上限；不能扩大队列或丢弃记录')
            if eof:
                # 文件结束确认必须晚于解析器和DBC成功关闭，不能先发送成功EOF再报清理错。
                reader.close();reader=None
                if context is not None:
                    context.close();context=None
                budget.release_ram(BLOCK_RAM)
                if budget.ram_bytes:
                    raise RuntimeError('CAN文件结束后仍持有未释放资源')
            control.send(('block',len(packet),decoded,serialized,wait_seconds))
            started=perf_counter()
            data.send_bytes(packet)
            # 数据管道阻塞与等待下一许可分别计量；父确认发送完成后才复用槽。
            control.send(('sent',perf_counter()-started))
            records=record=packet=None
            block_number+=1
    except (EOFError,BrokenPipeError):
        pass
    except BaseException as error:
        # 仅传定位和原因，不发送完整栈、原始载荷或未完成的累计值。
        try:
            control.send(('error',type(error).__name__,str(error)))
        except (EOFError,BrokenPipeError,OSError):
            pass
    finally:
        if reader is not None:
            reader.close()
        if context is not None:
            context.close()
        control.close();data.close()
