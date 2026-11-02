"""关闭批量汇总JSON后独占安装正式报告，保留各任务已发布的独立输出。

报告只汇总状态、身份和错误，不合并指标或把失败会话当作零结果。沿现有结果
发布的Windows平台范围使用不覆盖rename；其他平台明确拒绝，失败暂存保留。
"""

import json
from pathlib import Path
import platform
from uuid import uuid4
from .models import BatchReport


def write_batch_report(report: BatchReport) -> Path:
    """发布固定汇总文件。参数: report实际结果。返回: batch_report.json路径。

    异常: 类型、只读路径、未支持平台、已有目标或原文件错误；关闭失败不安装正式文件。
    副作用: 只写本批目录的唯一暂存文件，失败不删除任务结果或覆盖已有报告。
    """
    if not isinstance(report, BatchReport):
        raise TypeError('需要BatchReport')
    root = report.output_dir.absolute()
    # 本函数也可独立调用；不能仅依赖调度器已经检查过模型中的路径。
    if any(p.casefold() == 'refprojects' for p in (*root.parts, *root.resolve().parts)):
        raise ValueError('批量报告不能位于RefProjects')
    if platform.system() != 'Windows':
        raise NotImplementedError('批量报告原子发布目前只验收Windows')
    destination = root / 'batch_report.json'
    try:
        destination.lstat()
    except FileNotFoundError:
        pass
    else:
        raise FileExistsError('批量报告已存在，拒绝覆盖：' + str(destination))
    temporary = root / ('.batch-report-' + uuid4().hex + '.incomplete.json')
    # 编码、写入和真实close全部成功才安装；Windows rename在目标已存在时拒绝。
    with temporary.open('x', encoding='utf-8', newline='') as stream:
        json.dump(report.to_dict(), stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')
    temporary.rename(destination)
    return destination
