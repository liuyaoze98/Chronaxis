"""传递独立计划快照和小型结果，保留工作进程中的失败清理责任。

管道仅连接本次创建的可信子进程，不读取外部序列化对象。计划重建后核对身份，
大型结果在子进程内写出并关闭。清理失败的进程暂停接活，由报告句柄远程重试。
"""

from dataclasses import replace
import multiprocessing
import os
from pathlib import Path
import signal
from threading import Event

from ..planning.plan import AnalysisPlan
from ..planning.checks import json_value
from .models import BatchJob, BatchJobResult, CleanupHandle
from .process_tree import ProcessTree


def job_packet(job):
    """提取无活动资源的计划。参数: BatchJob。返回: 原生dict。异常: 配置转换错误。"""
    if isinstance(job.plan, Path):
        return dict(job_id=job.job_id, path=str(job.plan.absolute()))
    return dict(job_id=job.job_id, config=json_value(job.plan.raw_config),
                base_dir=str(job.plan.base_dir), identity=job.plan.identity)


def restore_job(packet):
    """恢复独立计划。参数: 本进程收到的声明。返回: BatchJob。异常: 重建或身份不一致。"""
    if 'path' in packet:
        return BatchJob(packet['job_id'], Path(packet['path']))
    plan = AnalysisPlan.from_dict(packet['config'], base_dir=packet['base_dir'])
    if plan.identity != packet['identity']:
        raise ValueError('跨进程重建后的计划身份不一致')
    return BatchJob(packet['job_id'], plan)


def worker_main(connection):
    """处理run/cleanup/close命令。参数: 私有管道。返回: None。异常: 断管退出，父进程负责树清理。"""
    from .runner import _run_job, _diagnostics
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
            connection.send(('result', replace(outcome, recovery=None, worker_pid=os.getpid()), pending))
    except EOFError:
        if recovery is not None:
            recovery.close()
    finally:
        connection.close()


class ProcessWorker:
    """保存一个可复用工作进程、私有管道及其后代的清理责任。"""

    def __init__(self):
        """启动等待命令的spawn进程。参数: 无。返回: 新对象。异常: 启动/树登记失败立即回收。"""
        context = multiprocessing.get_context('spawn')
        self.connection, child = context.Pipe()
        self.process = context.Process(target=worker_main, args=(child,), daemon=False)
        self.tree = None
        self.closed = False
        self.pending = False
        try:
            self.process.start()
            self.tree = ProcessTree(self.process.pid)
        except BaseException:
            if self.process.pid is not None:
                self.process.terminate()
                self.process.join()
            self.connection.close()
            self.process.close()
            raise
        finally:
            child.close()
        self.pid = self.process.pid

    def submit(self, job, directory, backend):
        """发送独立任务。参数: job/目录/后端。返回: None。异常: 转换或通信错误。"""
        self.connection.send(('run', job_packet(job), str(directory), backend))

    def ready(self):
        """查询结果或异常退出。参数: 无。返回: bool。异常: 原管道错误。"""
        try:
            return self.connection.poll() or not self.process.is_alive()
        except (EOFError, OSError) as error:
            raise ChildProcessError('分析工作进程管道已断开，PID=' + str(self.pid)) from error

    def receive(self):
        """取结果并挂远程恢复句柄。参数: 无。返回: BatchJobResult。异常: 进程死亡或协议错误。"""
        if not self.connection.poll():
            raise ChildProcessError('分析工作进程异常退出，PID=' + str(self.pid))
        try:
            kind, result, self.pending = self.connection.recv()
        except EOFError as error:
            raise ChildProcessError('分析工作进程断开，PID=' + str(self.pid)) from error
        if kind != 'result' or not isinstance(result, BatchJobResult):
            raise RuntimeError('批量工作进程返回无效结果')
        return replace(result, recovery=CleanupHandle(self) if self.pending else None)

    def close(self):
        """重试远程清理后关闭进程树。参数: 无。返回: None。异常: 清理失败保留全部所有者。"""
        if self.closed:
            return
        if self.process.is_alive():
            if self.pending:
                self.connection.send(('cleanup',))
                kind, detail = self.connection.recv()
                if kind != 'cleaned':
                    raise RuntimeError('工作进程资源尚未关闭：' + '; '.join(detail))
                self.pending = False
            self.connection.send(('close',))
            self.process.join()
        else:
            self.process.join()
        # 工作进程已退出后关闭作业，清除故障残余的CAN读取后代。
        if self.tree is not None:
            self.tree.close()
        self.connection.close()
        self.process.close()
        self.closed = True
