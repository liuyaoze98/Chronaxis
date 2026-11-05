"""关闭批量汇总JSON后独占安装正式报告，保留各任务已发布的独立输出。

报告只汇总状态、身份和错误，不合并指标或把失败会话当作零结果。沿现有结果
发布的Windows平台范围使用不覆盖rename；其他平台明确拒绝，失败暂存保留。
"""

import json
from pathlib import Path
import platform
import tempfile
from .models import BatchReport


def write_batch_report(report: BatchReport) -> Path:
    """发布带本批时间的汇总文件。参数: report实际结果。返回: 实际报告路径。

    异常: 类型、只读路径、未支持平台、已有目标或原文件错误；关闭失败不安装正式文件。
    副作用: 只写本批目录的唯一暂存文件，失败不删除任务结果或覆盖已有报告。
    """
    return _write_batch_report(report, {})


def _write_batch_report(report, extra):
    """先完成可选的 fast 总量计算，再一次发布同一批报告。"""
    if not isinstance(report, BatchReport):
        raise TypeError('需要BatchReport')
    root = report.output_dir.absolute()
    # 本函数也可独立调用；不能仅依赖调度器已经检查过模型中的路径。
    if any(p.casefold() == 'refprojects' for p in (*root.parts, *root.resolve().parts)):
        raise ValueError('批量报告不能位于RefProjects')
    if platform.system() != 'Windows':
        raise NotImplementedError('批量报告原子发布目前只验收Windows')
    from ..results.publication import PublicationNames
    publication = report._publication or PublicationNames(root, ('batch_report.json',))
    destination = root / publication.names['batch_report.json']
    from ..results.owned_directory import directory_identity, remove_owned_directory
    temporary = identity = None
    # 编码、写入和真实close全部成功才安装；Windows rename在目标已存在时拒绝。
    try:
        temporary = Path(tempfile.mkdtemp(prefix='.batch-report-', suffix='.incomplete', dir=root))
        identity = directory_identity(temporary)
        with (temporary/'batch_report.json').open('x', encoding='utf-8', newline='') as stream:
            json.dump(dict(report.to_dict(), **extra), stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.write('\n')
        publication.publish(temporary, 'batch_report.json', only=('batch_report.json',))
        temporary.rmdir()
        return destination
    except BaseException as error:
        if publication.completed:
            error.published_report_path = destination
        # 不撤销已完成任务；只清理本次报告临时目录，保留最初的写出错误。
        try:
            if temporary is not None and identity is not None:
                remove_owned_directory(temporary, identity)
        except BaseException as cleanup:
            error.add_note('批量报告暂存清理失败：' + str(cleanup))
        try:
            publication.close()
        except BaseException as cleanup:
            error.add_note('批量命名锁释放失败：' + str(cleanup))
        raise
