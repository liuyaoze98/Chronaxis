"""传递独立计划快照和小型结果，保留工作进程中的失败清理责任。

管道仅连接本次创建的可信子进程，不读取外部序列化对象。计划重建后核对身份，
大型结果在子进程内写出并关闭。清理失败的进程暂停接活，由报告句柄远程重试。
"""

from dataclasses import replace
import multiprocessing
from pathlib import Path
from time import monotonic

from ..planning.plan import AnalysisPlan
from ..planning.checks import json_value
from .models import BatchJob, BatchJobResult, CleanupHandle
from .process_tree import ProcessTree
from .._batch_worker import worker_main


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


class ProcessWorker:
    """保存一个可复用工作进程、私有管道及其后代的清理责任。"""

    def __init__(self, *, fast=False):
        """启动等待命令的spawn进程。参数: 无。返回: 新对象。异常: 启动/树登记失败立即回收。"""
        context = multiprocessing.get_context('spawn')
        self.connection, child = context.Pipe()
        self.fast_cancel = context.Event() if fast else None
        self.cancel_deadline = None
        self.fast_rows = None
        args = (child, self.fast_cancel) if fast else (child,)
        self.process = context.Process(target=worker_main, args=args, daemon=False)
        self.tree = None
        self.closed = False
        self.pending = False
        self._pipe_lost = False
        self._stop_requested = False
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

    def submit_fast(self, job, directory, spec, total):
        """只传准备完成的文件参数，工作进程不重新解析模板或建立下层进程。"""
        packet = dict(job_id=job.job_id, spec=spec, total=total,
                      path=str(job.plan) if isinstance(job.plan, Path) else None)
        self.connection.send(('fast', packet, str(directory), None))

    def cancel_fast(self):
        """通知在途文件，协作退出超过五秒才结束本次拥有的进程树。返回是否已强制回收。"""
        if self.cancel_deadline is None:
            self.fast_cancel.set()
            self.cancel_deadline = monotonic() + 5
        elif monotonic() >= self.cancel_deadline:
            self._pipe_lost = True
            self.close()
            return True
        return False

    def ready(self):
        """查询结果或异常退出。参数: 无。返回: bool。异常: 原管道错误。"""
        try:
            return self.connection.poll() or not self.process.is_alive()
        except (EOFError, OSError) as error:
            if isinstance(error, (EOFError, BrokenPipeError)):
                self._pipe_lost = True
            raise ChildProcessError('分析工作进程管道已断开，PID=' + str(self.pid)) from error

    def receive(self):
        """取结果并挂远程恢复句柄。参数: 无。返回: BatchJobResult。异常: 进程死亡或协议错误。"""
        try:
            # Windows 同伴退出时，探测或随后的读取都可能先报告断管。
            if not self.connection.poll():
                raise ChildProcessError('分析工作进程异常退出，PID=' + str(self.pid))
            message = self.connection.recv()
        except (EOFError, BrokenPipeError) as error:
            self._pipe_lost = True
            raise ChildProcessError('分析工作进程断开，PID=' + str(self.pid)) from error
        if len(message) == 4 and getattr(self,'fast_cancel',None) is not None:
            kind, result, self.pending, self.fast_rows = message
        else:
            kind, result, self.pending = message
        if kind == 'fast_result' and getattr(self,'fast_cancel',None) is not None and isinstance(result,dict):
            result = BatchJobResult(**result)
            kind = 'result'
        if kind != 'result' or not isinstance(result, BatchJobResult):
            raise RuntimeError('批量工作进程返回无效结果')
        return replace(result, recovery=CleanupHandle(self) if self.pending else None)

    def close(self):
        """重试远程清理后关闭进程树。参数: 无。返回: None。异常: 清理失败保留全部所有者。"""
        if self.closed:
            return
        if not self._pipe_lost and not self._stop_requested and self.process.is_alive():
            try:
                if self.pending:
                    self.connection.send(('cleanup',))
                    kind, detail = self.connection.recv()
                    if kind != 'cleaned':
                        raise RuntimeError('工作进程资源尚未关闭：' + '; '.join(detail))
                    self.pending = False
                self.connection.send(('close',))
                self._stop_requested = True
            except (EOFError, BrokenPipeError):
                self._pipe_lost = True
        if self._pipe_lost:
            # 管道可先于进程退出；无法再握手时由父进程先结束本次拥有的树。
            if not self._stop_requested:
                if self.tree is not None:
                    self.tree.close()
                    self.tree = None
                elif self.process.is_alive():
                    self.process.kill()
                self._stop_requested = True
            self.process.join(timeout=5)
            if self.process.is_alive():
                raise TimeoutError('等待断管工作进程退出超时，PID=' + str(self.pid))
        else:
            self.process.join()
        # 正常停止也需关闭作业，清除残余后代；前一步失败时保留所有者供重试。
        if self.tree is not None:
            self.tree.close()
            self.tree = None
        self.connection.close()
        self.process.close()
        self.pending, self.closed = False, True
