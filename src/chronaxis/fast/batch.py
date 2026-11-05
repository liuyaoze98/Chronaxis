"""先检查整批 fast 配置，再交给文件级工作进程；结果按声明顺序发布。"""

from dataclasses import replace
from pathlib import Path

from ..batch.models import BatchPlan
from ..batch.publication import _write_batch_report
from ..batch.runner import BatchRunner
from ..configuration import ConfigurationError, load_configuration
from ..configuration.diagnostics import locate_error
from ..planning.checks import PlanValidationError, configuration_error
from ..planning.dbc_defaults import scoped_dbc_cache
from .config import compile_config
from .worker import _dbc_digest


@scoped_dbc_cache()
def prepare_batch(plan_path):
    """返回批量计划、按输入顺序的可序列化文件参数及模板标识。此时不读报文。"""
    path = Path(plan_path).absolute()
    try:
        document = load_configuration(path)
    except ConfigurationError as exc:
        raise configuration_error(exc) from exc
    raw = document.data
    try:
        plan = BatchPlan.from_dict(raw,base_dir=path.parent)
        if 'backend' in raw:
            raise PlanValidationError('$.backend','fast 批量入口已确定执行方式，不能指定 backend')
    except PlanValidationError as exc:
        raise locate_error(exc,document)
    template = 'template' in raw
    specs, errors, blocked = {}, [], []
    for job in plan.jobs:
        try:
            if template:
                from .config import compile_template_plan
                specs[job.job_id] = compile_template_plan(job.plan,template_path=path.parent/raw['template'])
            else:
                specs[job.job_id] = compile_config(job.plan)
        except PlanValidationError as exc:
            errors.extend(exc.diagnostics)
            blocked.extend(exc.blocked_checks)
    if errors:
        raise PlanValidationError.from_diagnostics(errors,blocked)
    return plan, specs, template


def run_batch(plan_path, output, *, process_count=None, cancel_event=None, total=False):
    """运行独立 fast jobs/template 配置，返回本次带时间的批量报告路径。

    失败或取消任务的报告仍可打开。基础设施异常保留 batch_report 以供检查或重试清理。
    process_count 省略时使用批量计划配置，total 只接收显式布尔值。
    """
    if type(total) is not bool:
        raise TypeError('total 需要布尔值')
    plan, specs, template = prepare_batch(plan_path)
    accumulator = outcomes = None
    if total:
        from .totals import FastTotals
        accumulator = FastTotals.from_specs(specs,template=template)
        if specs:
            digest = _dbc_digest(next(iter(specs.values()))['dbc'])
            for spec in specs.values():
                spec['_dbc_digest'] = digest
        outcomes = dict.fromkeys(specs)
    count = plan.process_count if process_count is None else process_count
    runner = BatchRunner(count,fail_fast=plan.fail_fast)
    extra = dict(engine='base_hpc_v1',budget_scope='whole_file_per_worker')
    try:
        report = runner._run(plan.jobs,output,cancel_event=cancel_event,device_label='pending',
                             fast_specs=specs,fast_rows=outcomes)
    except BaseException as exc:
        report = getattr(exc,'batch_report',None)
        if report is not None:
            try:
                path = _write_batch_report(report,extra)
                exc.batch_report = replace(report,report_path=path)
            except BaseException as publication_error:
                exc.add_note('无法完成批量失败报告：' + str(publication_error))
        raise
    try:
        if accumulator is not None:
            try:
                extra['totals'] = accumulator.finish(outcomes)
            except OverflowError as exc:
                report = replace(report,infrastructure_error='总量溢出：'+str(exc))
        return _write_batch_report(report,extra)
    finally:
        report.close()
