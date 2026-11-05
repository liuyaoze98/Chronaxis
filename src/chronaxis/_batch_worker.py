"""批量工作进程控制消息；只在收到对应任务时加载计算实现。"""
from dataclasses import replace
import os
from pathlib import Path
import signal
from threading import Event

def _diagnostics(error) -> tuple[str, ...]:
    """保留有限异常链而不持有栈。参数: error原异常。返回: 文本tuple。异常: 原异常格式错误。"""
    seen, details = set(), []
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        details.append(type(error).__name__ + ': ' + str(error))
        details.extend(getattr(error, '__notes__', ()))
        error = error.__cause__
    return tuple(details)


def worker_main(connection, fast_cancel=None):
    """处理run/cleanup/close命令。参数: 私有管道。返回: None。异常: 断管退出，父进程负责树清理。"""
    if fast_cancel is None:
        from .batch.runner import _run_job
        from .batch.process_transport import restore_job
        from .batch.models import BatchJobResult
    # Ctrl+C只由调度主进程接收，正在写结果的工作进程继续完整收尾。
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    recovery = None
    try:
        while True:
            command = connection.recv()
            if command[0] == 'close':
                if recovery is not None:
                    recovery.close()
                return
            if command[0] == 'cleanup':
                try:
                    if recovery is not None:
                        recovery.close()
                    recovery = None
                    connection.send(('cleaned', None))
                except BaseException as error:
                    connection.send(('cleanup_failed', _diagnostics(error)))
                continue
            if recovery is not None:
                raise RuntimeError('存在未关闭资源的工作进程不能接收新任务')
            _, packet, directory, backend = command
            if fast_cancel is not None:
                if command[0] != 'fast':
                    raise RuntimeError('fast 工作进程收到未知命令')
                from .fast.worker import file_response
                connection.send(file_response(packet, Path(directory), fast_cancel))
                continue
            try:
                job = restore_job(packet)
                outcome = _run_job(job, Path(directory), backend, Event(), Event())
            except BaseException as error:
                outcome = BatchJobResult(packet['job_id'], 'failed',
                    plan_path=packet.get('path'), error_type=type(error).__name__,
                    error_message=str(error), error_chain=_diagnostics(error))
            recovery = outcome.recovery
            pending = recovery is not None and not recovery.closed
            # 只发送冻结的纯结果字段；CleanupHandle的原资源必须留在拥有它的进程。
            response = ('result', replace(outcome, recovery=None, worker_pid=os.getpid()), pending)
            connection.send(response)
    except EOFError:
        if recovery is not None:
            recovery.close()
    finally:
        connection.close()
