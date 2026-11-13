"""只供真实spawn测试使用的顶层工作入口，在子进程内注入可恢复故障。"""

import os
from pathlib import Path
from unittest.mock import patch


def cleanup_worker(connection):
    """发布后按输出目录的release文件控制关闭故障。参数: 管道。返回: None。异常: 原worker错误。"""
    from chronaxis.batch.process_transport import worker_main
    from chronaxis.results.result import AnalysisResult
    original_close, original_write = AnalysisResult.close, AnalysisResult.write
    published = {}

    def write(result, output):
        """真实发布后标记目标。参数: 结果/目录。返回: 原清单。异常: 原写入错误。"""
        manifest = original_write(result, output)
        published[id(result)] = Path(output).parent / 'release'
        return manifest

    def close(result):
        """未解除故障时拒绝关闭最终结果。参数: 结果。返回: None。异常: 注入OSError。"""
        marker = published.get(id(result))
        if marker is not None and not marker.exists():
            raise OSError('test remote close blocked')
        return original_close(result)

    with patch.object(AnalysisResult, 'write', write), patch.object(AnalysisResult, 'close', close):
        worker_main(connection)


def cancelled_worker(connection):
    """在真实来源运行边界抛取消。参数: 管道。返回: None。异常: 原worker错误。"""
    from chronaxis.batch.process_transport import worker_main
    from chronaxis.execution.run_session import RunSession
    with patch.object(RunSession, 'execute', side_effect=KeyboardInterrupt('worker cancel')):
        worker_main(connection)


def crash_worker(connection):
    """启动真实后代后异常退出，用于验证平台进程树回收。参数: 管道。返回: 不返回。"""
    import subprocess
    import sys
    command = connection.recv()
    directory = Path(command[2])
    directory.mkdir(parents=True)
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'])
    (directory / 'child-pid.txt').write_text(str(child.pid), encoding='utf-8')
    os._exit(17)


def overlap_worker(connection):
    """记录真实子进程执行区间；短等待使微型任务可稳定观察并发。参数: 管道。返回: None。"""
    import time
    from chronaxis.batch.process_transport import worker_main
    from chronaxis.batch.runner import _run_job

    def observed(job, directory, backend, stop, cancel):
        """在任务自己的目录外保存测试时钟。参数: 原任务参数。返回: 真实结果。异常: 原错误。"""
        marker = directory.parent / (job.job_id + '.start')
        marker.write_text(str(time.perf_counter()), encoding='utf-8')
        time.sleep(0.3)
        result = _run_job(job, directory, backend, stop, cancel)
        marker.with_suffix('.end').write_text(str(time.perf_counter()), encoding='utf-8')
        return result

    with patch('chronaxis.batch.runner._run_job', observed):
        worker_main(connection)
