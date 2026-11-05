"""从严格批量配置调用公共API，打印精简计数并保留完整逐任务报告。

成功退出0、任一任务失败退出1、取消退出130；配置错误沿外层CLI退出2。
输出失败保已完成任务，原异常恢复报告在传播前尝试关闭，不清除诊断文件。
"""

from dataclasses import replace
import json
import os
import sys
from ..planning.checks import PlanValidationError
from ..results.spool import _cleanup_owner
from .api import run_batch
from .config import load_batch_plan
from .runner import _new_root


def run_batch_cli(arguments) -> int:
    """执行真实批量入口。参数: argparse参数。返回: 0/1/130。异常: 外层CLI处理的原错或配置错。"""
    plan = load_batch_plan(arguments.plan)
    try:
        if arguments.process_count is not None:
            plan = replace(plan, process_count=arguments.process_count)
        _new_root(arguments.output)
    except ValueError as error:
        raise PlanValidationError('$.cli', str(error)) from error
    label = os.environ.get('CHRONAXIS_DEVICE_LABEL', '').strip() or 'pending'
    try:
        report = run_batch(plan, arguments.output, device_label=label)
    except BaseException as error:
        report = getattr(error, 'batch_report', None)
        if report is not None:
            _cleanup_owner(report, error, 'batch_report', '批量异常报告')
        raise
    # 一般失败已经清理完；持续故障再尝试，完整报告仍保存初始失败及恢复位置。
    cleanup_failed = False
    try:
        report.close()
    except Exception as error:
        cleanup_failed = True
        print('批量结果清理失败：' + type(error).__name__ + ': ' + str(error), file=sys.stderr)
    document = report.to_dict()
    print(json.dumps(dict(status=report.status, counts=document['counts'],
        output=str(report.output_dir), report=str(report.report_path),
        cleanup_pending=cleanup_failed, device_label=label), ensure_ascii=False, allow_nan=False))
    if cleanup_failed or report.status == 'failed':
        return 1
    return 130 if report.status == 'cancelled' else 0
