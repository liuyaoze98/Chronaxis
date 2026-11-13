"""可复用文件worker：流式求贡献，获得父进程许可后直传或直接写暂存。

控制和数据独立，任一时刻只有一个尚未交付块。worker不累计总量、不创建
子进程；EOF包含最终块数与已成功关闭的文件事实。父进程拥有取消和回收责任。
"""
from hashlib import sha256
import os
from pathlib import Path
import signal
from time import perf_counter

from .._control_wire import ControlChannel
from .blocks import batches, encode, LIMIT
from ..dbc_loading import load_dbc_file


def worker_main(control, data, cancel):
    """运行父授权的文件任务。参数: 控制连接、单向数据连接、取消事件。返回: None。
    异常: 原错误通过控制通道报告；断管退出，finally释放读取器。
    """
    if type(control) is not ControlChannel:
        raise TypeError('fast工作进程需要固定字节控制端点')
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    reader = None
    database = None
    identity = None
    try:
        while True:
            command = control.recv()
            if command[0] == 'close':
                break
            if command[0] not in ('file', 'program_file'):
                raise ValueError('未知fast文件命令')
            programs_checked = command[0] == 'program_file'
            _, index, spec, directory, expected_digest = command
            from .stream import FileContributions
            import cantools
            # 复用DBC只限同一冻结内容；变化属于任务失败，不能混合解码口径。
            content = Path(spec['dbc']).read_bytes()
            digest = sha256(content).hexdigest()
            if digest != expected_digest:
                raise ValueError('运行期间DBC内容变化')
            if identity != digest:
                database = load_dbc_file(spec['dbc'], cantools)
                if sha256(Path(spec['dbc']).read_bytes()).hexdigest() != digest:
                    raise ValueError('加载期间DBC内容变化')
                identity = digest
            reader = FileContributions(spec, database, cancel, _programs_checked=programs_checked)
            count = 0
            clocks = dict(compute_seconds=0.0, credit_wait_seconds=0.0, send_seconds=0.0, write_seconds=0.0)
            blocks = iter(batches(reader))
            while True:
                if cancel.is_set():
                    raise InterruptedError('fast文件计算取消')
                started = perf_counter()
                try:
                    records = next(blocks)
                except StopIteration:
                    clocks['compute_seconds'] += perf_counter() - started
                    break
                packet = encode(index, count, records)
                records = None
                clocks['compute_seconds'] += perf_counter() - started
                control.send(('offer', index, count, len(packet)))
                started = perf_counter()
                route = control.recv()
                clocks['credit_wait_seconds'] += perf_counter() - started
                if route == ('close',):
                    return
                started = perf_counter()
                if route == ('direct',):
                    data.send_bytes(packet)
                    clocks['send_seconds'] += perf_counter() - started
                    control.send(('delivered', index, count, len(packet)))
                elif route == ('spool',):
                    path = Path(directory) / f'{index}-{count}.block'
                    temporary = path.with_suffix('.part')
                    with temporary.open('xb') as output:
                        if output.write(packet) != len(packet):
                            raise OSError('贡献暂存未完整写入')
                    from ..results.platform_files import move_no_replace
                    move_no_replace(temporary,path)
                    clocks['write_seconds'] += perf_counter() - started
                    control.send(('stored', index, count, len(packet)))
                else:
                    raise ValueError('未知贡献交付许可')
                packet = None
                count += 1
                # 等待父确认，直传缓冲不能随主进程处理速度无界累积。
                if control.recv() != ('next',):
                    return
            facts = reader.summary()
            if spec.get('_profile', False):
                clocks.update(reader.timings)
            reader = None
            control.send(('eof', index, count, facts, clocks, os.getpid()))
    except (EOFError, BrokenPipeError):
        pass
    except BaseException as error:
        try:
            control.send(('error', type(error).__name__, str(error)))
        except (EOFError, BrokenPipeError, OSError):
            pass
    finally:
        if reader is not None:
            reader.close()
        control.close()
        data.close()
