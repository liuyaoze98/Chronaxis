"""在外层多进程执行独立计划，复用公共AnalysisRunner完成分析、发布和关闭。

每个任务拥有自己的RunSession、预算和目录；不拆分一个会话的时间轴，不共用
活动、迟滞或配对状态。最多process_count个future在途，未开始的任务不读计划文件。
取消或fail_fast停止派发，已经开始的任务正常完成关闭；不向工作进程注入异常。
只承诺每任务原有预算及同时运行数，不承诺全进程RSS或固定进程数带来的性能收益。
"""

from dataclasses import replace
import time
import os
from pathlib import Path
from threading import Event
from time import perf_counter

from ..planning import load_analysis_plan
from ..planning.plan import AnalysisPlan
from ..runner import AnalysisRunner
from ..results.spool import _cleanup_owner
from .._batch_worker import _diagnostics
from .models import BatchJob, BatchJobResult, BatchReport, CleanupHandle


def _new_root(value) -> Path:
    """检查可复用批量目录。参数: value为str/Path。返回: 绝对Path。异常: 类型/已有/只读路径错误。"""
    from ..results.publication import output_root
    return output_root(value)


def _facts(job, plan=None) -> dict:
    """区分配置和输入事实。参数: job原声明；plan可选已加载计划。返回: 字段dict。异常: 无。"""
    loaded = plan if plan is not None else job.plan if isinstance(job.plan, AnalysisPlan) else None
    result = dict(job_id=job.job_id, plan_path=str(job.plan.absolute()) if isinstance(job.plan, Path) else None)
    if loaded is not None:
        result.update(plan_identity=loaded.identity, dataset_id=loaded.dataset.dataset_id,
                      entity_id=loaded.dataset.entity, session_id=loaded.dataset.session_id,
                      memory_budget_bytes=loaded.execution.memory_budget_bytes)
    return result


def _cancelled(job, reason) -> BatchJobResult:
    """记录未启动取消。参数: job原声明；reason原因。返回: 取消结果。异常: 无，不读取计划。"""
    return BatchJobResult(**_facts(job), status='cancelled', error_type='not_started', error_message=reason)


def _report(root, jobs, results, process_count, fail_fast, cancelled, label, reason) -> BatchReport:
    """补齐未启动项。参数: 原声明/结果及调度选项。返回: 完整报告。异常: 模型错误。"""
    outcomes = tuple(_cancelled(job, reason) if value is None else value
                     for job, value in zip(jobs, results))
    # worker中的真实KeyboardInterrupt也属于取消请求，不只记录主线程的Event。
    requested = cancelled or any(j.error_type in ('KeyboardInterrupt', 'SystemExit') for j in outcomes)
    return BatchReport(root, outcomes, process_count, fail_fast, requested, label)


def _run_job(job, directory, backend, stop, cancel) -> BatchJobResult:
    """执行一个独立任务并关闭所有资源。

    参数: job为BatchJob；directory为独占新子目录；backend为覆盖；stop/cancel为Event。
    返回: 含实际发布和身份的最终结果；恢复失败保最高owner，不把异常栈留在结果中。
    异常: 普通分析/发布/取消转换成该任务结果；无法构造结果的内部错误交由调度器收尾。
    """
    if stop.is_set() or cancel.is_set():
        return _cancelled(job, '任务启动前已停止派发')
    started = perf_counter()
    plan = result = manifest = recovery = None
    metadata = {'worker_pid': os.getpid()}
    try:
        # 路径计划到本任务实际开始才加载，未派发的坏文件不会影响其他任务。
        plan = job.plan if isinstance(job.plan, AnalysisPlan) else load_analysis_plan(job.plan)
        directory.mkdir(parents=True, exist_ok=False)
        result = AnalysisRunner(backend).run(plan, work_dir=directory / 'work')
        metadata.update(input_identity=result.metadata.input_identity, run_id=result.metadata.run_id)
        manifest = result.write(directory / 'output')
        metadata['output_dir'] = manifest.output_dir
        metadata['manifest_path'] = manifest.manifest_path
        result.close()
        return BatchJobResult(**_facts(job, plan), **metadata, status='completed',
                              elapsed_seconds=perf_counter() - started)
    except BaseException as error:
        completed = getattr(error, 'completed_manifest', None)
        if completed is not None:
            metadata.update(output_dir=completed.output_dir, manifest_path=completed.manifest_path)
        # 结果已经返回后由本层负责close；未返回的运行恢复owner继续沿AnalysisRunner原协议。
        if result is not None:
            _cleanup_owner(result, error, 'batch_cleanup_owner', '批量任务结果')
        owner = getattr(error, 'batch_cleanup_owner', None)
        if owner is None:
            owner = getattr(error, 'runner_cleanup_owner', None)
        # AnalysisRunner可能保留已经成功关闭的恢复属性；只有仍实际持有资源才转交报告。
        if owner is not None and not (getattr(owner, 'closed', False) or getattr(owner, '_closed', False)):
            recovery = CleanupHandle(owner)
        cancelled = isinstance(error, (KeyboardInterrupt, SystemExit))
        # 资源耗尽或真实取消应停止新派发；普通业务失败由fail_fast决定是否停止。
        if cancelled or isinstance(error, MemoryError):
            stop.set()
        return BatchJobResult(**_facts(job, plan), **metadata,
                              status='cancelled' if cancelled else 'failed',
                              error_type=type(error).__name__, error_message=str(error),
                              error_chain=_diagnostics(error), recovery=recovery,
                              elapsed_seconds=perf_counter() - started)


def _pause():
    """让出调度CPU等待下一次结果。参数: 无。返回: None。异常: 主进程取消。"""
    time.sleep(0.01)


class BatchRunner:
    """通过有限spawn工作进程执行独立任务；同一任务的连续文件保持原顺序。"""

    def __init__(self, process_count=1, *, fail_fast=False, backend=None):
        """配置调度。参数: process_count正整数；fail_fast布尔；backend可选计算实现。

        返回: None。异常: 参数不合法；构造时不启动进程或读取业务输入。
        """
        if type(process_count) is not int or process_count < 1:
            raise ValueError('process_count需要正原生int')
        if type(fail_fast) is not bool:
            raise TypeError('fail_fast需要bool')
        if backend is not None:
            AnalysisRunner(backend)
        self.process_count, self.fail_fast, self.backend = process_count, fail_fast, backend

    def run(self, jobs, output_dir, *, cancel_event=None, device_label='pending') -> BatchReport:
        """运行独立任务，原声明顺序返回报告。

        参数: jobs为BatchJob tuple；output_dir可复用目录；cancel_event可选threading.Event；
            device_label为报告来源标签。返回: BatchReport，close可重试子进程内失败清理。
        异常: 声明和路径错误在启动前拒绝；调度基础设施错误携带batch_report。
        副作用: 启动最多process_count个工作进程，每任务独立发布；取消只阻止未派发任务。
        """
        return self._run(jobs, output_dir, cancel_event=cancel_event, device_label=device_label)

    def _run(self, jobs, output_dir, *, cancel_event, device_label, fast_specs=None, fast_rows=None):
        """共享派发/清理循环；fast_specs 仅由 fast 校验入口构造，可选 fast_rows 接收汇总所需小行。"""
        from .process_transport import ProcessWorker
        if type(jobs) is not tuple or any(not isinstance(j, BatchJob) for j in jobs):
            raise TypeError('批量任务需要BatchJob tuple')
        if len({j.job_id.casefold() for j in jobs}) != len(jobs):
            raise ValueError('批量job_id不能重复，大小写冲突也拒绝')
        if cancel_event is not None and not isinstance(cancel_event, Event):
            raise TypeError('cancel_event需要threading.Event')
        if type(device_label) is not str or not device_label.strip():
            raise ValueError('device_label需要非空文本')
        # 有待派发任务的独立batch即使上限为1也会创建受管工作进程。
        # 在创建输出前提示；不修改既有派发、失败报告或退出码。
        from ..process_capabilities import warn_managed_worker
        warn_managed_worker(bool(jobs) and not (cancel_event is not None and cancel_event.is_set()),
                            '本独立批量任务')
        root = _new_root(output_dir)
        from ..results.publication import PublicationNames
        publication = PublicationNames(root, (*[j.job_id for j in jobs], 'batch_report.json'))
        cancel = Event() if cancel_event is None else cancel_event
        workers, free, active, last_job = [], [], {}, {}
        results = [None] * len(jobs)
        next_job, stopped, interrupted, infrastructure = 0, False, False, None
        while next_job < len(jobs) or active:
            try:
                if cancel.is_set():
                    stopped = True
                # 先收齐本轮已完成结果再派发，避免观察到失败后继续启动下一任务。
                for worker, index in list(active.items()):
                    try:
                        if worker.ready():
                            outcome = worker.receive()
                            if fast_rows is not None and outcome.status == 'completed':
                                fast_rows[jobs[index].job_id] = worker.fast_rows
                        elif (fast_specs is not None and (cancel.is_set() or interrupted or infrastructure is not None)
                              and worker.cancel_fast()):
                            outcome = replace(_cancelled(jobs[index], '取消后工作进程未及时退出，已回收'),
                                              worker_pid=worker.pid,error_type='cancel_timeout')
                        else:
                            continue
                    except Exception as error:
                        outcome = BatchJobResult(**_facts(jobs[index]), status='failed',
                            worker_pid=worker.pid, error_type=type(error).__name__,
                            error_message=str(error), error_chain=_diagnostics(error))
                        infrastructure = infrastructure or error
                        stopped = True
                    results[index] = outcome
                    del active[worker]
                    if self.fail_fast and outcome.status == 'failed':
                        stopped = True
                    if outcome.error_type in ('MemoryError', 'KeyboardInterrupt', 'SystemExit'):
                        stopped = True
                    if not worker.pending:
                        free.append(worker)
                while not stopped and next_job < len(jobs):
                    if cancel.is_set():
                        stopped = True
                        break
                    if free:
                        worker = free.pop()
                    elif len(workers) < min(self.process_count, len(jobs)):
                        worker = ProcessWorker() if fast_specs is None else ProcessWorker(fast=True)
                        workers.append(worker)
                    else:
                        break
                    index = next_job
                    try:
                        directory = root / publication.names[jobs[index].job_id]
                        if fast_specs is None:
                            worker.submit(jobs[index], directory, self.backend)
                        else:
                            worker.submit_fast(jobs[index], directory, fast_specs[jobs[index].job_id], fast_rows is not None)
                    except Exception as error:
                        results[index] = BatchJobResult(**_facts(jobs[index]), status='failed',
                            worker_pid=worker.pid, error_type=type(error).__name__, error_message=str(error))
                        infrastructure = infrastructure or error
                        stopped = True
                        break
                    active[worker], last_job[worker] = index, index
                    next_job += 1
                if not active:
                    # 所有工作进程若都因未完成清理而暂停，剩余任务不再派发。
                    break
                _pause()
            except KeyboardInterrupt as error:
                interrupted, stopped = True, True
                # 构造取消且清理持续失败时，原异常拥有尚未关闭的真实worker；
                # 不能仅返回取消报告而丢失该恢复入口。已清理的Ctrl+C仍按原流程返回。
                if getattr(error, 'batch_worker_cleanup_owner', None) is not None:
                    infrastructure = infrastructure or error
            except Exception as error:
                infrastructure, stopped = infrastructure or error, True
        # 在途任务已结束；持续关闭失败留远程owner，不因结束调度而丢掉恢复入口。
        for worker in workers:
            if worker.pending:
                continue
            try:
                worker.close()
            except BaseException as error:
                index = last_job.get(worker)
                if index is not None:
                    results[index] = replace(results[index], status='failed',
                        error_type=type(error).__name__, error_message=str(error),
                        recovery=CleanupHandle(worker))
                infrastructure = infrastructure or error
        reason = '用户取消，尚未启动' if cancel.is_set() or interrupted else '失败或未完成清理后停止派发'
        report = _report(root, jobs, results, self.process_count, self.fail_fast,
                         cancel.is_set() or interrupted, device_label, reason)
        report = replace(report, worker_process_count=len(workers), _publication=publication)
        if infrastructure is not None:
            report = replace(report, infrastructure_error=type(infrastructure).__name__ + ': ' + str(infrastructure))
            infrastructure.batch_report = report
            raise infrastructure
        return report
