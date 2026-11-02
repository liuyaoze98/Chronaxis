"""把冻结批量计划交给同一调度器并保存完整报告，不重新实现分析算法。

正常返回的BatchReport包含所有独立任务的最终状态。调度或报告写出失败时，
原异常保留batch_report，使调用方能访问已完成结果并重试未关闭的资源。
"""

from dataclasses import replace
from .models import BatchPlan
from .runner import BatchRunner
from .publication import write_batch_report


def run_batch(plan: BatchPlan, output_dir, *, process_count: int | None = None, cancel_event=None, device_label='pending'):
    """运行并发布批量报告。

    参数: plan为load_batch_plan取得的BatchPlan，规定本次独立任务及调度设置；process_count为可选正整数覆盖，None沿用计划；output_dir全新目录；cancel_event为可选Event；device_label为实际标签。
    返回: BatchReport；failed/cancelled保留在报告，不伪装全部成功。
    异常: TypeError为非BatchPlan或取消对象类型不符；ValueError为无效并发、后端或
        任务声明；目录创建、调度、报告发布错误按原类型传播。单任务失败记录在jobs中，
        不等于本函数抛错。已产生报告后发生基础设施错误时，异常的batch_report保存
        当次实际报告，可检查已完成任务并调用close重试清理。
    """
    if not isinstance(plan, BatchPlan):
        raise TypeError('run_batch需要BatchPlan')
    if process_count is not None:
        plan = replace(plan, process_count=process_count)
    runner = BatchRunner(plan.process_count, fail_fast=plan.fail_fast, backend=plan.backend)
    try:
        report = runner.run(plan.jobs, output_dir, cancel_event=cancel_event, device_label=device_label)
    except BaseException as error:
        report = getattr(error, 'batch_report', None)
        if report is not None:
            report = replace(report, infrastructure_error=type(error).__name__ + ': ' + str(error))
            error.batch_report = report
            try:
                write_batch_report(report)
            except BaseException as diagnostic:
                error.add_note('批量失败报告未发布: ' + type(diagnostic).__name__)
        raise
    try:
        write_batch_report(report)
    except BaseException as error:
        # 已完成任务绝不因汇总文件失败而丢失，未清理资源仍可从原异常恢复。
        error.batch_report = report
        raise
    return report
