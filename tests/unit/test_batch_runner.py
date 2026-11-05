"""以真实公共分析验证独立批量的顺序/并发对照和关闭责任。

内存、真实CSV和路径计划都通过同一AnalysisRunner运行，不用伪结果替代计算。
只在真实执行与关闭边界加入屏障或故障；产物放work专用目录，保留失败证据。
"""

import csv
import json
from pathlib import Path
from threading import Barrier, Event, Lock
import unittest
from publication_fixtures import published_path
from unittest.mock import patch
from uuid import uuid4

from chronaxis import AnalysisPlan
from chronaxis.batch import BatchJob, BatchRunner
from chronaxis.execution.run_session import RunSession
from chronaxis.results.result import AnalysisResult
from test_start_end_runner import start_end_config
from test_stability_runner import stable_config

ROOT = Path(__file__).absolute().parents[2]


class BatchRunnerTests(unittest.TestCase):
    """每例建立独立批次目录，不在测试之间共享任务或状态。"""

    def setUp(self):
        """建立合成夹具根。参数: 无。返回: None。异常: 文件系统错误。"""
        self.work = ROOT / 'work/m3-batch-home-20261023/tests' / uuid4().hex
        self.work.mkdir(parents=True)

    def job(self, name, *, csv_input=False):
        """保存真实计划及可选CSV。参数: name任务名；csv_input选择文件。返回: BatchJob。异常: 原文件/配置错误。"""
        raw = start_end_config()
        # 本组比对原交换表字节，显式选择csv；默认可读另有公共入口验收。
        raw['outputs'] = {'tables': 'csv'}
        raw['dataset']['name'] = name
        if csv_input:
            # 与内存样本完全相同的实际信号表，保留显式时间单位及字段声明。
            source = raw['sources'][0]
            path = self.work / (name + '.csv')
            with path.open('w', encoding='utf-8', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow(['ns', 'begin', 'done', 'value'])
                for row in source.pop('rows'):
                    writer.writerow([row['time'].removesuffix('ns'), *row['values'].values()])
            source.update(source_type='signal_csv', path=str(path), time_column='ns')
        from chronaxis.planning.config_groups import public_configuration
        raw=public_configuration(raw)
        path = self.work / (name + '.json')
        path.write_text(json.dumps(_current_plan(raw)), encoding='utf-8')
        return BatchJob(name, path)

    def test_real_parallel_matches_sequential_and_is_bounded(self):
        """四任务真实双进程重叠，结果与顺序相同，完成顺序不改变清单顺序。"""
        from batch_process_fixtures import overlap_worker
        jobs = tuple(self.job(f'job_{i}', csv_input=i%2 == 0) for i in range(4))
        sequential = BatchRunner().run(jobs, self.work/'sequential')
        with patch('chronaxis.batch.process_transport.worker_main', overlap_worker):
            parallel = BatchRunner(2).run(jobs, self.work/'parallel')
        self.assertEqual((sequential.status, parallel.status), ('completed', 'completed'))
        events = []
        for job in jobs:
            events += [(float((parallel.output_dir/(job.job_id+'.start')).read_text()),1),
                       (float((parallel.output_dir/(job.job_id+'.end')).read_text()),-1)]
        active = peak = 0
        for _, delta in sorted(events):
            active += delta
            peak = max(peak, active)
        self.assertEqual(peak, 2)
        self.assertEqual(len({j.worker_pid for j in parallel.jobs}), 2)
        for left, right in zip(sequential.jobs, parallel.jobs):
            self.assertEqual(left.job_id, right.job_id)
            for table in ('events.csv','segments.csv','calculations.csv'):
                self.assertEqual(published_path(left.output_dir/table).read_bytes(),published_path(right.output_dir/table).read_bytes())

    def test_hysteresis_state_does_not_cross_independent_sessions(self):
        """85到77已报警，另一任务从77开始无前序证据，不能继承报警。参数: 无。返回: None。异常: 断言/运行错误。"""
        configs = []
        for values in (((0, 85), (3, 77), (6, 77)), ((0, 77), (3, 70), (6, 70))):
            raw = stable_config()
            raw['dataset']['domain']['end'] = '6ns'
            raw['sources'][0]['rows'] = [dict(time=f'{t}ns', values=dict(temperature=v)) for t, v in values]
            raw['outputs'] = dict(tables='csv')
            configs.append(AnalysisPlan.from_dict(_current_plan(raw)))
        report = BatchRunner(2).run(tuple(BatchJob(f'part_{i}', p) for i, p in enumerate(configs)), self.work / 'isolated')
        self.assertEqual(report.status, 'completed')
        rows = []
        for job in report.jobs:
            with published_path(job.output_dir / 'events.csv').open(encoding='utf-8', newline='') as stream:
                rows.append(list(csv.DictReader(stream)))
        self.assertEqual([len(r) for r in rows], [1, 0])

    def test_failure_continues_and_retains_identity_without_false_input_proof(self):
        """坏计划文件失败不污染后续CSV任务，未知输入身份保持空。参数: 无。返回: None。异常: 断言/运行错误。"""
        jobs = (BatchJob('missing', self.work / 'absent.json'), self.job('valid', csv_input=True))
        report = BatchRunner().run(jobs, self.work / 'mixed')
        self.assertEqual([j.status for j in report.jobs], ['failed', 'completed'])
        self.assertEqual(report.status, 'failed')
        self.assertIn('absent.json', report.jobs[0].error_message)
        self.assertIsNone(report.jobs[0].input_identity)
        # 默认不生成输入证明；成功身份由实际计划和run_id给出。
        self.assertIsNone(report.jobs[1].input_identity)
        self.assertTrue(report.jobs[1].run_id)
        self.assertTrue(report.jobs[1].plan_identity)
        self.assertEqual(report.to_dict()['counts'], dict(completed=1, failed=1, cancelled=0))

    def test_real_analysis_failure_is_closed_without_recovery_flag(self):
        """真实运行预算不足时AnalysisRunner已关好，不得再报cleanup_pending。参数: 无。返回: None。异常: 断言/运行错误。"""
        raw = start_end_config()
        # 本组比对原交换表字节，显式选择csv；默认可读另有公共入口验收。
        raw['outputs'] = {'tables': 'csv'}
        raw['execution']['memory_budget_bytes'] = 1
        report = BatchRunner().run((BatchJob('small', AnalysisPlan.from_dict(_current_plan(raw))),), self.work / 'budget')
        self.assertEqual(report.jobs[0].status, 'failed')
        self.assertFalse(report.jobs[0].to_dict()['cleanup_pending'])

    def test_fail_fast_stops_unstarted_and_does_not_load_next_plan(self):
        """首任务失败后第二个真实配置不加载，不假报分析失败。参数: 无。返回: None。异常: 断言。"""
        report = BatchRunner(fail_fast=True).run((BatchJob('bad', self.work/'bad.json'), self.job('later')), self.work/'fast')
        self.assertEqual([j.status for j in report.jobs], ['failed', 'cancelled'])
        self.assertIsNone(report.jobs[1].plan_identity)
        self.assertFalse((report.output_dir/'later').exists())

    def test_cancel_before_start_preserves_all_jobs_without_inputs(self):
        """提前取消不加载不存在计划；空批次也可完成。参数: 无。返回: None。异常: 断言。"""
        cancel = Event()
        cancel.set()
        report = BatchRunner(2).run((BatchJob('first', self.work/'missing.json'),), self.work/'cancel', cancel_event=cancel)
        self.assertEqual((report.status, report.jobs[0].status, report.cancel_requested), ('cancelled', 'cancelled', True))
        empty = BatchRunner().run((), self.work/'empty')
        self.assertEqual((empty.status, empty.jobs), ('completed', ()))

    def test_cancel_allows_running_job_to_publish_and_close(self):
        """派发后请求取消，首任务完整发布，下一任务不启动。"""
        from chronaxis.batch.process_transport import ProcessWorker
        original, cancel = ProcessWorker.submit, Event()
        def submit(worker, *args):
            """先真实发送再取消后续派发。参数: worker/任务。返回: None。异常: 原发送错误。"""
            original(worker, *args)
            cancel.set()
        with patch.object(ProcessWorker, 'submit', submit):
            report = BatchRunner().run((self.job('active'), self.job('next')), self.work/'during', cancel_event=cancel)
        self.assertEqual([j.status for j in report.jobs], ['completed', 'cancelled'])
        self.assertTrue(report.jobs[0].manifest_path.is_file())

    def test_keyboard_interrupt_waits_for_running_job(self):
        """主线程等待时被取消，已启动任务仍完成关闭，剩余不启动。参数: 无。返回: None。异常: 断言。"""
        from chronaxis.batch.runner import _pause as real_wait
        calls = 0

        def once(*args, **kwargs):
            """只在第一次等待注入主线程取消。参数: 原wait参数。返回: 原wait。异常: 首次KeyboardInterrupt。"""
            nonlocal calls
            calls += 1
            if calls == 1:
                raise KeyboardInterrupt()
            return real_wait(*args, **kwargs)

        with patch('chronaxis.batch.runner._pause', once):
            report = BatchRunner().run((self.job('current'), self.job('later')), self.work/'interrupt')
        self.assertTrue(report.cancel_requested)
        self.assertIn(report.jobs[0].status, ('completed', 'cancelled'))
        self.assertEqual(report.jobs[1].status, 'cancelled')

    def test_close_failure_remains_failed_and_can_be_retried(self):
        """子进程真实结果关闭失败，父报告远程重试，解除故障后释放实际资源。"""
        from batch_process_fixtures import cleanup_worker
        with patch('chronaxis.batch.process_transport.worker_main', cleanup_worker):
            report = BatchRunner().run((self.job('pending'), self.job('later')), self.work/'close')
        marker = report.jobs[0].output_dir.parent/'release'
        def release():
            """测试即使断言失败也先解锁再关闭。参数: 无。返回: None。异常: 原清理错误。"""
            marker.touch()
            report.close()
        self.addCleanup(release)
        self.assertEqual([j.status for j in report.jobs], ['failed', 'cancelled'])
        self.assertTrue(report.jobs[0].to_dict()['cleanup_pending'])
        self.assertTrue(report.jobs[0].manifest_path.exists())
        with self.assertRaisesRegex(RuntimeError, 'test remote close blocked'):
            report.close()
        marker.touch()
        report.close()
        report.close()
        self.assertFalse(report.jobs[0].to_dict()['cleanup_pending'])

    def test_preflight_rejects_bad_declarations_and_protected_or_existing_paths(self):
        """非法ID、选项、重复任务及已有目录在启动前拒绝，不改原文件。参数: 无。返回: None。异常: 断言。"""
        good = self.job('valid')
        for args in ((0,), (True,), (-1,)):
            with self.assertRaises(ValueError):
                BatchRunner(*args)
        with self.assertRaises(TypeError):
            BatchRunner(fail_fast='yes')
        with self.assertRaises(ValueError):
            BatchJob('../escape', good.plan)
        for jobs in ([good], (good, good), (good, BatchJob('VALID', good.plan))):
            with self.assertRaises((ValueError, TypeError)):
                BatchRunner().run(jobs, self.work/'not_created')
        self.assertFalse((self.work/'not_created').exists())
        for target in (self.work/'RefProjects'/'new',):
            with self.assertRaises((ValueError, FileExistsError)):
                BatchRunner().run((good,), target)
        self.assertFalse((self.work/'RefProjects').exists())
        reused = BatchRunner().run((good,), self.work)
        self.addCleanup(reused.close)
        self.assertEqual(reused.status, 'completed')

    def test_worker_cancel_stops_next_job_and_records_request(self):
        """子进程内真实运行边界取消会停止后续派发。"""
        from batch_process_fixtures import cancelled_worker
        with patch('chronaxis.batch.process_transport.worker_main', cancelled_worker):
            report = BatchRunner().run((self.job('first'), self.job('next')), self.work/'worker-cancel')
        self.assertEqual([j.status for j in report.jobs], ['cancelled', 'cancelled'])
        self.assertTrue(report.cancel_requested)
        self.assertFalse(report.jobs[0].to_dict()['cleanup_pending'])

    def test_scheduler_failure_waits_and_exposes_completed_report(self):
        """主调度等待故障后保留已派发真实任务的成功输出。"""
        with patch('chronaxis.batch.runner._pause', side_effect=RuntimeError('scheduler unavailable')):
            with self.assertRaises(RuntimeError) as caught:
                BatchRunner().run((self.job('active'), self.job('later')), self.work/'scheduler-error')
        report = caught.exception.batch_report
        self.assertEqual([j.status for j in report.jobs], ['completed', 'cancelled'])
        self.assertTrue(report.jobs[0].manifest_path.is_file())
        report.close()

    def test_backend_override_uses_same_public_plan_without_mutation(self):
        """批量覆盖参考后端仍与NumPy三表一致，并记录实际后端。参数: 无。返回: None。异常: 断言/运行错误。"""
        job = self.job('same')
        original = job.plan.read_bytes()
        numpy = BatchRunner().run((job,), self.work/'numpy')
        reference = BatchRunner(2, backend='reference').run((job,), self.work/'reference')
        self.assertEqual((numpy.status, reference.status), ('completed', 'completed'))
        self.assertEqual(job.plan.read_bytes(), original)
        for table in ('events.csv', 'segments.csv', 'calculations.csv'):
            self.assertEqual(published_path(numpy.jobs[0].output_dir/table).read_bytes(), published_path(reference.jobs[0].output_dir/table).read_bytes())
        manifest = json.loads(published_path(reference.jobs[0].output_dir/'run_manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['run']['backend'], 'reference')


def _current_plan(raw):
    """共享夹具使用当前公开结构；批量清单原样返回。"""
    from chronaxis.planning.config_groups import public_configuration
    return public_configuration(raw) if 'config_version' in raw else raw
