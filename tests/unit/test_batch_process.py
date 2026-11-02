"""验证公开进程数、内存计划重建、真实PID和崩溃后代回收；不以线程模拟进程。"""

from dataclasses import replace
import json
import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from chronaxis import AnalysisPlan, load_batch_plan, run_batch
from chronaxis.batch import BatchJob, BatchPlan, BatchRunner
from chronaxis.batch.process_transport import job_packet, restore_job
from test_start_end_runner import start_end_config
from chronaxis.planning.config_groups import public_configuration
from batch_process_fixtures import crash_worker


class BatchProcessTests(unittest.TestCase):
    """小型真实任务覆盖身份、参数和进程生命周期。"""

    def setUp(self):
        """建立独占测试目录。参数: 无。返回: None。异常: 文件错误。"""
        self.root = Path(__file__).resolve().parents[2] / 'Docs/Current/_build/batch-process/tests' / uuid4().hex
        self.root.mkdir(parents=True)

    def plan(self):
        """构建手算事件夹具。参数: 无。返回: AnalysisPlan。异常: 配置错误。"""
        return AnalysisPlan.from_dict(public_configuration(start_end_config()), base_dir=self.root)

    def test_snapshot_and_process_override(self):
        """同一内存配置在子进程重建身份不变，API覆盖不改变计划。"""
        job = BatchJob('first', self.plan())
        self.assertEqual(restore_job(job_packet(job)).plan.identity, job.plan.identity)
        broken = job_packet(job)
        broken['identity'] = 'bad'
        with self.assertRaisesRegex(ValueError, '身份'):
            restore_job(broken)
        plan = BatchPlan((job, replace(job, job_id='second')), process_count=1)
        report = run_batch(plan, self.root / 'output', process_count=2)
        self.addCleanup(report.close)
        self.assertEqual((report.status, report.process_count, report.worker_process_count), ('completed', 2, 2))
        self.assertEqual(plan.process_count, 1)
        self.assertEqual(len({j.worker_pid for j in report.jobs}), 2)
        self.assertNotIn(os.getpid(), {j.worker_pid for j in report.jobs})
        self.assertTrue(all(j.plan_identity == job.plan.identity for j in report.jobs))

    def test_count_validation_and_old_names(self):
        """拒绝非正整数和旧拼写，不因Python布尔是整数子类而放行。"""
        for value in (0, -1, True, 1.5, '4', None):
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                BatchPlan((), process_count=value)
        for key in ('workers', 'max_workers'):
            with self.assertRaisesRegex(ValueError, 'process_count'):
                BatchPlan.from_dict(dict(batch_version=1, jobs=[], **{key: 2}))
        empty = run_batch(BatchPlan((), process_count=8), self.root / 'empty')
        self.assertEqual(empty.worker_process_count, 0)

    def test_reuse_one_worker_and_small_job_count(self):
        """一个进程复用处理三项，八进程上限面对一个任务只启动一个。"""
        jobs = tuple(BatchJob(f'job_{i}', self.plan()) for i in range(3))
        first = run_batch(BatchPlan(jobs), self.root / 'serial')
        second = run_batch(BatchPlan(jobs[:1], process_count=8), self.root / 'one')
        self.assertEqual((first.status, second.status), ('completed', 'completed'))
        self.assertEqual(len({j.worker_pid for j in first.jobs}), 1)
        self.assertEqual(second.worker_process_count, 1)

    def test_worker_death_closes_descendant(self):
        """工作进程非正常退出，实际睡眠子进程必须被作业对象回收。"""
        import ctypes
        from ctypes import wintypes
        job = BatchJob('crash', self.plan())
        with patch('chronaxis.batch.process_transport.worker_main', crash_worker):
            with self.assertRaises(ChildProcessError) as caught:
                BatchRunner().run((job,), self.root / 'crashed')
        report = caught.exception.batch_report
        report.close()
        self.assertEqual(report.jobs[0].status, 'failed')
        pid = int((self.root/'crashed/crash/child-pid.txt').read_text())
        api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.OpenProcess.restype = wintypes.HANDLE
        api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = api.OpenProcess(0x100000, False, pid)
        if handle:
            try:
                self.assertEqual(api.WaitForSingleObject(handle, 5000), 0)
            finally:
                api.CloseHandle(handle)
