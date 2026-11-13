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
from .._control_wire import ControlChannel
from ..results.budget import _cleanup_owner
from .models import BatchJob, BatchJobResult, CleanupHandle
from .process_tree import ProcessTree
from .._process_start import spawn_entry
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
        self.connection = self._child = self.process = self.tree = self._startup = None
        self.fast_cancel = None
        self.cancel_deadline = self.fast_rows = self.pid = None
        self.closed = self.pending = self._pipe_lost = self._stop_requested = False
        self._constructing = True
        try:
            self.connection, self._child = context.Pipe()
            self.connection = ControlChannel(self.connection,'batch',parent=True)
            self._child = ControlChannel(self._child,'batch',parent=False)
            self.fast_cancel = context.Event() if fast else None
            args = (self._child, self.fast_cancel) if fast else (self._child,)
            try:
                target,args,self._startup=spawn_entry(context,worker_main,args)
            except BaseException as error:
                self._startup=getattr(error,'process_start_cleanup_owner',None)
                raise
            self.process = context.Process(target=target, args=args, daemon=False)
            self.process.start()
            self.pid = self.process.pid
            try:
                self.tree = (ProcessTree(self.pid) if self._startup is None else
                    ProcessTree(self.pid,registration=self._startup,process=self.process))
            except BaseException as error:
                self.tree = getattr(error, 'process_tree_cleanup_owner', None)
                raise
            if self._startup is not None:
                self._startup.close();self._startup=None
            self._child.close()
            self._child = None
            self._constructing = False
        except BaseException as error:
            # 未成功返回的工作进程不参与握手；树或管道持续关闭失败仍保留真实owner。
            self._pipe_lost = True
            _cleanup_owner(self, error, 'batch_worker_cleanup_owner', '批量工作进程构造')
            raise

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
        """重试远程清理后关闭实际进程树及管道，半构造失败也可恢复。

        参数: 无。返回: None。异常: 清理失败保留尚未关闭对象供下一次close。
        已关闭进程不再次调用is_alive；构造后未启动的进程也关闭其本地句柄。
        """
        if self.closed:
            return
        process = self.process
        active = (process is not None and getattr(process, '_closed', False) is not True
                  and process.pid is not None)
        if active:
            if not self._pipe_lost and not self._stop_requested and process.is_alive():
                try:
                    if self.pending:
                        self.connection.send(('cleanup',))
                        if self.tree is not None and getattr(self.tree,'_linux',False) is True and not self.connection.poll(5):
                            self._pipe_lost=True
                            raise TimeoutError('等待工作进程清理回复超时；保留进程树关闭责任')
                        kind, detail = self.connection.recv()
                        if kind != 'cleaned':
                            raise RuntimeError('工作进程资源尚未关闭：' + '; '.join(detail))
                        self.pending = False
                    self.connection.send(('close',))
                    self._stop_requested = True
                except (EOFError, BrokenPipeError):
                    self._pipe_lost = True
            if self._pipe_lost:
                if not self._stop_requested:
                    if self.tree is not None:
                        self.tree.close()
                        self.tree = None
                        # 仅构造失败时作业可能尚未登记该进程，不能由空作业推断进程已结束。
                        if getattr(self, '_constructing', False) and process.is_alive():
                            process.kill()
                    elif process.is_alive():
                        process.kill()
                    self._stop_requested = True
                process.join(timeout=5)
                if process.is_alive():
                    raise TimeoutError('等待断管工作进程退出超时，PID=' + str(self.pid))
            else:
                if self.tree is not None and getattr(self.tree,'_linux',False) is True:
                    process.join(timeout=5)
                    if process.is_alive():
                        self.tree.close();self.tree=None
                        raise TimeoutError('工作进程未按关闭协议退出')
                else:process.join()
        if self.tree is not None:
            self.tree.close()
            self.tree = None
        for name in ('connection', '_child', '_startup'):
            connection = getattr(self, name, None)
            if connection is not None:
                try:
                    connection.close()
                finally:
                    if connection.closed:
                        setattr(self, name, None)
        if process is not None and getattr(process, '_closed', False) is not True:
            process.close()
        self.fast_cancel = None
        self.pending, self.closed = False, True
