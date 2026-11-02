"""保存独立批量任务及其完成、失败和取消事实。

输入是已构建计划或计划文件路径；输出保留任务、计划、会话和实际输入身份。
模型不读取来源、不建立进程，也不将多个任务的数值结果相加。清理失败时只保留
可显式重试的最高资源所有者，错误本身转成文本，避免长期保存异常栈和输入数组。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ..core.validation import require_identifier
from ..planning.plan import AnalysisPlan


class Closable(Protocol):
    """表示已经存在、由调用者负责关闭的资源，不创建占位执行对象。"""

    def close(self) -> None:
        """关闭资源。参数: 无。返回: None。异常: 原关闭错误，可恢复后重试。"""
        ...


class CleanupHandle:
    """只持有未关闭的最高所有者；关闭成功后撤销引用，重复关闭无副作用。"""

    def __init__(self, owner: Closable):
        """接管真实恢复对象。参数: owner有close方法。返回: 新句柄。异常: 无。"""
        self._owner = owner

    @property
    def closed(self) -> bool:
        """读取恢复是否完成。参数: 无。返回: bool。异常: 无。"""
        return self._owner is None

    def close(self) -> None:
        """重试关闭，不在失败时丢所有者。参数: 无。返回: None。异常: 原关闭错误。"""
        if self._owner is not None:
            self._owner.close()
            self._owner = None


@dataclass(frozen=True)
class BatchJob:
    """声明一个独立分析；同会话连续文件应包含在本任务的一个计划中。"""

    job_id: str  # 批量范围内唯一的简单标识，不用它拼接任意相对路径。
    plan: AnalysisPlan | Path  # 冻结计划或文件路径；路径到真正启动时才加载。

    def __post_init__(self):
        """检查声明而不读文件。参数: 无。返回: None。异常: 名称或计划类型错误。"""
        require_identifier(self.job_id, 'job_id')
        if not isinstance(self.plan, (AnalysisPlan, Path)):
            raise TypeError('BatchJob.plan需要AnalysisPlan或Path')


@dataclass(frozen=True)
class BatchPlan:
    """保存批量配置；只关联独立计划路径，不能把一个会话拆成多个时间任务。"""

    jobs: tuple[BatchJob, ...]  # 声明顺序就是最终清单顺序。
    process_count: int = 1  # 工作进程上限，默认1；各任务仍有独立预算。
    fail_fast: bool = False  # 默认继续其他独立任务。
    backend: str | None = None  # 可选统一覆盖，不修改原计划文件。

    def __post_init__(self):
        """检查冻结声明。参数: 无。返回: None。异常: 类型、范围或重复任务错误；无I/O。"""
        if type(self.jobs) is not tuple or any(not isinstance(j, BatchJob) for j in self.jobs):
            raise TypeError('jobs需要BatchJob tuple')
        if len({j.job_id.casefold() for j in self.jobs}) != len(self.jobs):
            raise ValueError('批量job_id不能重复或仅大小写不同')
        if type(self.process_count) is not int or self.process_count < 1:
            raise ValueError('process_count需要正原生int')
        if type(self.fail_fast) is not bool:
            raise TypeError('fail_fast需要bool')
        if self.backend is not None and (type(self.backend) is not str or self.backend not in ('reference', 'numpy')):
            raise ValueError('backend需要reference、numpy或null')

    @classmethod
    def from_dict(cls, config, *, base_dir=None):
        """检查批量配置；jobs只关联路径，template读取模板并展开文件集合。

        参数: config原生dict；base_dir为计划路径相对基准，默认当前目录。
        返回: 冻结BatchPlan。异常: PlanValidationError定位字段；不读取业务报文，模板可读取DBC元数据。
        """
        from ..planning.checks import object_at, array_at, text_at, model_at, PlanValidationError, number_at, choice_at
        if type(config) is dict and ('workers' in config or 'max_workers' in config):
            raise PlanValidationError('$.process_count', '请使用process_count设置分析工作进程数；workers/max_workers不再接受')
        raw = object_at(config, '$', ('batch_version',), ('jobs', 'template', 'inputs', 'source', 'process_count', 'fail_fast', 'backend'))
        choice_at(raw['batch_version'],(1,),'$.batch_version')
        base, jobs = Path.cwd() if base_dir is None else Path(base_dir).absolute(), []
        if 'template' in raw:
            if 'jobs' in raw or 'inputs' not in raw:
                raise PlanValidationError('$','template需要inputs且不能同时提供jobs')
            from .templates import template_jobs
            jobs=template_jobs(raw,base)
        elif 'jobs' not in raw or 'inputs' in raw or 'source' in raw:
            raise PlanValidationError('$','需要jobs，或template与inputs')
        names=set()
        for index, value in enumerate(array_at(raw.get('jobs', []), '$.jobs')):
            path = '$.jobs[' + str(index) + ']'
            item = object_at(value, path, ('plan',), ('name',))
            job_id = text_at(item.get('name',f'job_{index+1}'), path + '.name', identifier=True)
            if job_id.casefold() in names:
                raise PlanValidationError(path+'.name','任务名称不能重复或仅大小写不同','duplicate_id',
                    hint='为每个独立任务指定唯一name')
            names.add(job_id.casefold())
            target = Path(text_at(item['plan'], path + '.plan'))
            if not target.is_absolute():
                target = base / target
            jobs.append(BatchJob(job_id, target.absolute()))
        return model_at(cls, '$', tuple(jobs),
            number_at(raw.get('process_count',1),'$.process_count',integer=True,minimum=1),
            choice_at(raw.get('fail_fast',False),(False,True),'$.fail_fast'),
            choice_at(raw.get('backend'),(None,'reference','numpy'),'$.backend'))


@dataclass(frozen=True)
class BatchJobResult:
    """保存一个任务的最终状态；发布后关闭失败仍为failed，并保留已发布路径。"""

    job_id: str  # 原任务身份。
    status: str  # completed、failed或cancelled。
    plan_path: str | None = None  # 路径计划的原绝对位置；内存计划无路径。
    plan_identity: str | None = None  # 配置身份，不冒充实际输入内容身份。
    dataset_id: str | None = None  # 无法加载计划时三项会话字段均为空。
    entity_id: str | None = None
    session_id: str | None = None
    input_identity: str | None = None  # 只有实际分析返回后才记录。
    run_id: str | None = None  # 同计划重跑仍有独立运行身份。
    output_dir: Path | None = None  # 实际发布成功的目录，不预填未生成输出。
    error_type: str | None = None  # 原异常类型或未启动取消原因。
    error_message: str | None = None  # 原错误说明，不用成功值覆盖失败。
    error_chain: tuple[str, ...] = ()  # cause链和清理notes，保留错误来源。
    elapsed_seconds: float = 0.0  # 单任务墙钟秒，含发布及关闭，不宣称CPU耗时。
    memory_budget_bytes: int | None = None  # 该任务的新分析层预算；不是整进程RSS。
    worker_pid: int | None = None  # 实际执行任务的工作进程PID；未启动项为空。
    recovery: CleanupHandle | None = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        """拒绝伪成功状态。参数: 无。返回: None。异常: 非法状态或成功缺少事实。"""
        if self.status not in ('completed', 'failed', 'cancelled'):
            raise ValueError('批量任务状态无效')
        if self.status == 'completed' and (self.output_dir is None or self.run_id is None):
            raise ValueError('completed需要实际发布目录及运行身份')

    def to_dict(self) -> dict:
        """生成可保存的事实。参数: 无。返回: JSON对象。异常: 无；不序列化资源对象。"""
        names = ('job_id', 'status', 'plan_path', 'plan_identity', 'dataset_id', 'entity_id',
                 'session_id', 'input_identity', 'run_id', 'error_type', 'error_message',
                 'elapsed_seconds', 'memory_budget_bytes', 'worker_pid')
        result = {name: getattr(self, name) for name in names}
        result.update(output_dir=None if self.output_dir is None else str(self.output_dir),
                      error_chain=list(self.error_chain),
                      cleanup_pending=self.recovery is not None and not self.recovery.closed)
        return result


@dataclass(frozen=True)
class BatchReport:
    """按原任务顺序汇总结果；每个任务数值表仍在各自目录，不跨口径归约。"""

    output_dir: Path  # 本批新目录，已有目标不会被覆盖。
    jobs: tuple[BatchJobResult, ...]  # 最终结果顺序不受工作进程完成先后影响。
    process_count: int  # 本次配置的工作进程上限。
    fail_fast: bool  # 是否在观察到失败后停止派发。
    cancel_requested: bool  # 用户取消或KeyboardInterrupt是否曾被观察到。
    device_label: str  # 调用方明确提供；缺省pending，不猜测机器。
    worker_process_count: int = 0  # 本次实际启动的工作进程数，空批次为0。
    infrastructure_error: str | None = None  # 调度或汇总基础设施错误，与任务业务失败分开。

    @property
    def status(self) -> str:
        """汇总失败优先状态。参数: 无。返回: failed/cancelled/completed。异常: 无。"""
        if self.infrastructure_error is not None or any(job.status == 'failed' for job in self.jobs):
            return 'failed'
        return 'cancelled' if any(job.status == 'cancelled' for job in self.jobs) else 'completed'

    def to_dict(self) -> dict:
        """输出身份和计数。参数: 无。返回: JSON对象。异常: 无。不合并指标值。"""
        return dict(batch_version=1, status=self.status, output_dir=str(self.output_dir),
                    process_count=self.process_count, executor='processes', worker_process_count=self.worker_process_count, fail_fast=self.fail_fast,
                    cancel_requested=self.cancel_requested, device_label=self.device_label,
                    infrastructure_error=self.infrastructure_error,
                    budget_scope='per_task_new_analysis_layer',
                    counts={s: sum(j.status == s for j in self.jobs)
                            for s in ('completed', 'failed', 'cancelled')},
                    jobs=[job.to_dict() for job in self.jobs])

    def close(self) -> None:
        """重试所有未完清理。参数: 无。返回: None。异常: 首个关闭错误，其他项仍尝试。"""
        first = None
        for job in self.jobs:
            if job.recovery is not None:
                try:
                    job.recovery.close()
                except BaseException as error:
                    # 一项失败不能阻止其他独立任务释放资源；原句柄仍由本报告保留。
                    if first is None:
                        first = error
        if first is not None:
            raise first
