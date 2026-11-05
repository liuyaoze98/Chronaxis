"""验证公开进程数、内存计划重建、真实PID和崩溃后代回收；不以线程模拟进程。"""

from dataclasses import replace
import json
import os
from pathlib import Path
import time
import unittest
from unittest.mock import Mock, call, patch
from uuid import uuid4

from chronaxis import AnalysisPlan, load_batch_plan, run_batch
from chronaxis.batch import BatchJob, BatchPlan, BatchRunner
from chronaxis.batch.process_transport import ProcessWorker, job_packet, restore_job
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

    def test_receive_reports_pipe_loss_at_poll_or_read(self):
        """分别在探测和读取注入断管或EOF，保留PID、原异常和协议错误。"""
        worker = ProcessWorker.__new__(ProcessWorker)
        worker.pid = 1234
        for stage in ('poll', 'recv'):
            for failure in (BrokenPipeError(), EOFError()):
                with self.subTest(stage=stage, failure=type(failure).__name__):
                    worker.connection = Mock(spec=['poll', 'recv'])
                    worker.connection.poll.return_value = True
                    getattr(worker.connection, stage).side_effect = failure
                    with self.assertRaisesRegex(ChildProcessError, '1234') as caught:
                        worker.receive()
                    self.assertIs(caught.exception.__cause__, failure)
                    self.assertEqual(worker.connection.recv.call_count, int(stage == 'recv'))
        worker.connection = Mock(spec=['poll', 'recv'])
        worker.connection.poll.return_value = True
        worker.connection.recv.return_value = ('unexpected', None, False)
        with self.assertRaisesRegex(RuntimeError, '无效结果'):
            worker.receive()

    def close_worker(self, pending=False):
        """构造可逐阶段注错的拥有者。参数: pending 指示远程资源。返回: worker及调用记录。异常: 无。"""
        calls = Mock()
        worker = ProcessWorker.__new__(ProcessWorker)
        worker.pid = 1234
        worker.connection, worker.tree, worker.process = calls.connection, calls.tree, calls.process
        worker.closed, worker.pending = False, pending
        worker._pipe_lost, worker._stop_requested = False, False
        return worker, calls

    def test_close_reclaims_tree_if_peer_disconnects_during_handshake(self):
        """在关闭命令、清理命令和应答断开时，先收作业再等待退出，重复关不重发。"""
        for stage, pending, error in (('send', False, BrokenPipeError()), ('send', True, BrokenPipeError()),
                                      ('recv', True, EOFError())):
            with self.subTest(stage=stage, pending=pending):
                worker, calls = self.close_worker(pending)
                calls.process.is_alive.side_effect = [True, False]
                getattr(calls.connection, stage).side_effect = error
                worker.close()
                worker.close()
                calls.connection.send.assert_called_once_with(('cleanup',) if pending else ('close',))
                calls.tree.close.assert_called_once_with()
                calls.process.join.assert_called_once_with(timeout=5)
                self.assertLess(calls.mock_calls.index(call.tree.close()), calls.mock_calls.index(call.process.join(timeout=5)))
                calls.connection.close.assert_called_once_with()
                calls.process.close.assert_called_once_with()
                self.assertTrue(worker.closed)
                self.assertFalse(worker.pending)

    def test_disconnected_close_retries_only_unfinished_steps(self):
        """作业关闭失败保留所有者；等待超时可重试；无作业时只终止自己持有的子进程。"""
        worker, calls = self.close_worker()
        worker._pipe_lost = True
        calls.tree.close.side_effect = [OSError('job handle'), None]
        calls.process.is_alive.side_effect = [True, False]
        with self.assertRaisesRegex(OSError, 'job handle'):
            worker.close()
        self.assertIs(worker.tree, calls.tree)
        calls.process.join.assert_not_called()
        with self.assertRaisesRegex(TimeoutError, '1234'):
            worker.close()
        calls.connection.close.assert_not_called()
        worker.close()
        self.assertTrue(worker.closed)
        self.assertEqual(calls.tree.close.call_count, 2)
        calls.process.kill.assert_not_called()
        worker, calls = self.close_worker()
        worker._pipe_lost = True
        worker.tree = None
        calls.process.is_alive.side_effect = [True, True, False]
        with self.assertRaisesRegex(TimeoutError, '1234'):
            worker.close()
        worker.close()
        calls.process.kill.assert_called_once_with()
        self.assertTrue(worker.closed)

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
        directories = tuple((self.root/'crashed').glob('crash_*'))
        self.assertEqual(len(directories), 1)
        pid = int((directories[0]/'child-pid.txt').read_text())
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
