"""验证严格批量配置、根包API、真实CLI及关闭后发布的汇总文件。

计划路径相对批量文件，分析仍调用公共AnalysisRunner。合成JSON/CSV及命令输出保留于
work；故障注入只作用于真实汇总写入或调度边界，不用手造成功输出。
"""

from contextlib import redirect_stdout, redirect_stderr
import csv
from decimal import Decimal
import io
import json
import os
from dataclasses import replace
from pathlib import Path
import subprocess
import sys
from threading import Event
import unittest
from publication_fixtures import published_path
from unittest.mock import patch
from uuid import uuid4
from jsonschema import Draft202012Validator

from chronaxis import BatchPlan, BatchJob, BatchRunner, load_batch_plan, run_batch, PlanValidationError
from chronaxis.batch import write_batch_report
from chronaxis.cli import main
import test_batch_runner as fixtures
import test_can_runner as can_fixtures

ROOT = fixtures.ROOT


class BatchPublicTests(unittest.TestCase):
    """复用真实输入构造，每例独立目录，命令实际从仓库根运行。"""

    # 复用A1同一套真实CSV和计划生成方法，避免重新发明另一份输入格式。
    job = fixtures.BatchRunnerTests.job

    def setUp(self):
        """建立本例工作目录。参数: 无。返回: None。异常: 原文件错误。"""
        self.work = ROOT/'work/m3-batch-home-20261023/public'/uuid4().hex
        self.work.mkdir(parents=True)
        self.command_index = 0

    def manifest(self, *, fail_fast=False):
        """保存指向两份真实计划的批量文件。参数: fail_fast策略。返回: 文件Path。异常: 原文件错误。"""
        first, second = self.job('first', csv_input=True), self.job('second')
        path = self.work/'batch.json'
        path.write_text(json.dumps(dict(batch_version=1, process_count=2, fail_fast=fail_fast,
            jobs=[dict(name=job.job_id, plan=job.plan.name) for job in (first, second)])), encoding='utf-8')
        return path

    def command(self, *arguments):
        """运行真实CLI并保存退出码及输出。参数: CLI文本参数。返回: CompletedProcess。异常: 子进程/文件错误。"""
        result = subprocess.run([sys.executable, '-B', '-m', 'chronaxis', *map(str, arguments)],
            cwd=ROOT, env=dict(os.environ,CHRONAXIS_DEVICE_LABEL='home'), capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.command_index += 1
        (self.work/f'command-{self.command_index}.json').write_text(json.dumps(dict(
            arguments=list(map(str, arguments)), returncode=result.returncode, stdout=result.stdout, stderr=result.stderr,
            device_label='home'), ensure_ascii=False, indent=2), encoding='utf-8')
        return result

    def test_strict_config_schema_and_static_relative_paths(self):
        """解析只读批量文件，任务计划缺失仍留待各自运行处理。参数: 无。返回: None。异常: 断言。"""
        raw = dict(batch_version=1, jobs=[dict(name='first', plan='not-yet.json')])
        schema = json.loads((ROOT/'Docs/Schema/batch-v1.schema.json').read_text(encoding='utf-8'))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(raw)
        plan = BatchPlan.from_dict(raw, base_dir=self.work)
        self.assertEqual(plan.jobs[0].plan, self.work/'not-yet.json')
        self.assertEqual((plan.process_count, plan.fail_fast, plan.backend), (1, False, None))
        path = self.work/'static.json'
        path.write_text(json.dumps(_current_plan(raw)), encoding='utf-8')
        with patch('chronaxis.batch.runner.load_analysis_plan', side_effect=AssertionError('不应读取任务计划')):
            self.assertEqual(load_batch_plan(path), plan)
        invalid = [dict(raw, unknown=1), dict(raw, batch_version=True), dict(raw, batch_version=2),
            dict(raw, process_count=True), dict(raw, process_count=0), dict(raw, process_count=2.0),
            dict(raw, fail_fast=1), dict(raw, backend='gpu'), dict(raw, jobs=[dict(name='x', plan='a', extra=1)]),
            dict(raw, jobs=[dict(name='same', plan='a'), dict(name='SAME', plan='b')]), dict(raw, jobs='folder')]
        for config in invalid:
            with self.subTest(config=config), self.assertRaises(PlanValidationError):
                BatchPlan.from_dict(config, base_dir=self.work)
        self.assertEqual(raw['jobs'][0]['plan'], 'not-yet.json')

    def test_loader_rejects_duplicate_nonfinite_and_bad_json_with_file_location(self):
        """错误配置保文件定位，不后项覆盖或接受NaN。参数: 无。返回: None。异常: 断言。"""
        path = self.work/'bad.json'
        for text in ('{"batch_version":1,"batch_version":1,"jobs":[]}',
                     '{"batch_version":1,"jobs":[],"process_count":NaN}', '{broken'):
            path.write_text(text, encoding='utf-8')
            with self.assertRaises(PlanValidationError) as caught:
                load_batch_plan(path)
            self.assertIn(str(path), str(caught.exception))

    def test_public_api_publishes_ordered_report_and_refuses_overwrite(self):
        """实际API保存完整身份，后续写同一报告拒绝且原字节不变。参数: 无。返回: None。异常: 断言/运行错误。"""
        plan = load_batch_plan(self.manifest())
        output = self.work/'api'
        report = run_batch(plan, output, device_label='home')
        self.addCleanup(report.close)
        data = json.loads(published_path(output/'batch_report.json').read_text(encoding='utf-8'))
        self.assertEqual(data['counts'], dict(completed=2, failed=0, cancelled=0))
        self.assertEqual([j['job_id'] for j in data['jobs']], ['first', 'second'])
        self.assertTrue(all(j['input_identity'] is None and j['plan_identity'] and not j['cleanup_pending'] for j in data['jobs']))
        self.assertEqual(data['device_label'], 'home')
        before = published_path(output/'batch_report.json').read_bytes()
        with self.assertRaises(FileExistsError):
            write_batch_report(report)
        self.assertEqual(published_path(output/'batch_report.json').read_bytes(), before)
        second = run_batch(plan, output)
        self.addCleanup(second.close)
        self.assertNotEqual(second.report_path, report.report_path)
        self.assertEqual(report.report_path.read_bytes(), before)

    def test_api_cancellation_is_published_without_loading_missing_plan(self):
        """取消后的清单保存未启动项和null输入身份。参数: 无。返回: None。异常: 断言。"""
        cancel = Event()
        cancel.set()
        plan = BatchPlan((BatchJob('later', self.work/'absent.json'),))
        report = run_batch(plan, self.work/'cancelled', cancel_event=cancel, device_label='home')
        data = json.loads(published_path(report.output_dir/'batch_report.json').read_text(encoding='utf-8'))
        self.assertEqual(data['status'], 'cancelled')
        self.assertIsNone(data['jobs'][0]['input_identity'])
        self.assertTrue(data['cancel_requested'])

    def test_summary_write_failure_preserves_real_completed_results_and_partial_file(self):
        """报告写入失败清理自有临时文件，保留已完成任务。参数: 无。返回: None。异常: 断言。"""
        plan, output = load_batch_plan(self.manifest()), self.work/'report-failure'
        with patch('chronaxis.batch.publication.json.dump', side_effect=OSError('disk fault')):
            with self.assertRaises(OSError) as caught:
                run_batch(plan, output)
        report = caught.exception.batch_report
        self.addCleanup(report.close)
        self.assertEqual(report.status, 'completed')
        self.assertFalse((output/'batch_report.json').exists())
        self.assertEqual(len(list(output.glob('.batch-report-*.incomplete.json'))), 0)
        self.assertTrue(all(j.manifest_path.is_file() for j in report.jobs))

    def test_scheduler_failure_persists_failed_report_and_preserves_exception(self):
        """调度基础设施错误不伪装completed，仍保已有任务清单。参数: 无。返回: None。异常: 断言。"""
        plan, output = load_batch_plan(self.manifest()), self.work/'scheduler-failure'
        with patch('chronaxis.batch.runner._pause', side_effect=RuntimeError('scheduler fault')):
            with self.assertRaises(RuntimeError) as caught:
                run_batch(plan, output)
        report = caught.exception.batch_report
        self.addCleanup(report.close)
        data = json.loads(published_path(output/'batch_report.json').read_text(encoding='utf-8'))
        self.assertEqual((report.status, data['status']), ('failed', 'failed'))
        self.assertIn('scheduler fault', data['infrastructure_error'])

    def test_real_cli_success_and_worker_override(self):
        """子进程从仓库根加载异目录配置并实际运行，workers覆盖写入汇总。参数: 无。返回: None。异常: 断言。"""
        plan, output = self.manifest(), self.work/'cli'
        result = self.command('batch', 'run', plan, '--output', output, '--process-count', '1')
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual(summary['counts'], dict(completed=2, failed=0, cancelled=0))
        report = json.loads(published_path(output/'batch_report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['process_count'], 1)
        self.assertEqual(report['device_label'], 'home')

    def test_real_cli_failure_list_default_continues_and_fail_fast(self):
        """坏计划默认只失败一项，fail_fast取消后续，CLI均退出1。参数: 无。返回: None。异常: 断言。"""
        plan = self.manifest()
        raw = json.loads(plan.read_text(encoding='utf-8'))
        raw['jobs'][0]['plan'] = 'missing.json'
        raw['process_count'] = 1
        for fast, expected in ((False, ['failed', 'completed']), (True, ['failed', 'cancelled'])):
            raw['fail_fast'] = fast
            plan.write_text(json.dumps(_current_plan(raw)), encoding='utf-8')
            output = self.work/('fast' if fast else 'continue')
            result = self.command('batch', 'run', plan, '--output', output)
            self.assertEqual(result.returncode, 1, result.stderr)
            report = json.loads(published_path(output/'batch_report.json').read_text(encoding='utf-8'))
            self.assertEqual([j['status'] for j in report['jobs']], expected)
            self.assertIn('missing.json', report['jobs'][0]['error_message'])

    def test_cli_errors_reject_before_creating_output(self):
        """非法workers、已有/只读目录和坏批量配置拒绝，不先打开分析输入。参数: 无。返回: None。异常: 断言。"""
        plan = self.manifest()
        for workers in ('0', '-2'):
            output = self.work/('bad_workers_'+workers)
            result = self.command('batch', 'run', plan, '--output', output, '--process-count', workers)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertFalse(output.exists())
        for target, code in ((self.work, 0), (self.work/'RefProjects'/'new', 2)):
            result = self.command('batch', 'run', plan, '--output', target)
            self.assertEqual(result.returncode, code, result.stderr)
        plan.write_text('{"batch_version":2,"jobs":[]}', encoding='utf-8')
        result = self.command('batch', 'run', plan, '--output', self.work/'bad_version')
        self.assertEqual(result.returncode, 2)
        self.assertFalse((self.work/'bad_version').exists())

    def test_cli_keyboard_interrupt_records_cancelled_and_returns_130(self):
        """实际CLI等待时收到取消，完整报告仍落盘且返回130。参数: 无。返回: None。异常: 断言。"""
        from chronaxis.batch.runner import _pause as real_wait
        plan, output = self.manifest(), self.work/'cli-cancel'
        calls = 0

        def once(*args, **kwargs):
            """第一次等待注入取消，后续真实等待资源关闭。参数: wait参数。返回: 原结果。异常: 首次取消。"""
            nonlocal calls
            calls += 1
            if calls == 1:
                raise KeyboardInterrupt()
            return real_wait(*args, **kwargs)

        out = io.StringIO()
        with patch('chronaxis.batch.runner._pause', once), redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = main(['batch','run',str(plan),'--output',str(output),'--process-count','1'])
        self.assertEqual(code, 130)
        self.assertEqual(json.loads(out.getvalue())['status'], 'cancelled')
        self.assertTrue(published_path(output/'batch_report.json').is_file())

    def test_help_and_root_import_remain_standard_library_only(self):
        """根包和帮助不加载NumPy或CAN，参数错误不要求依赖已安装。参数: 无。返回: None。异常: 断言。"""
        result = subprocess.run([sys.executable, '-B', '-S', '-c',
            'import chronaxis, chronaxis.cli, sys; assert "numpy" not in sys.modules; chronaxis.cli.main(["batch","run","--help"])'],
            cwd=ROOT, env=dict(os.environ,CHRONAXIS_DEVICE_LABEL='home'), capture_output=True, text=True, encoding='utf-8', timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--process-count', result.stdout)

    def test_standalone_report_rejects_ref_path_before_file_open(self):
        """独立报告写出也须保护只读目录，不依赖调用者一定先跑调度器。参数: 无。返回: None。异常: 断言。"""
        report = BatchRunner().run((), self.work/'empty-report')
        target = self.work/'RefProjects'/'uncreated'
        redirected = replace(report, output_dir=target)
        # 禁止实际打开文件；用故障边界证明拒绝发生在I/O之前，不创建历史目录。
        with patch.object(Path, 'open', side_effect=AssertionError('不得尝试打开Ref目标')):
            with self.assertRaises(ValueError):
                write_batch_report(redirected)
        self.assertFalse((self.work/'RefProjects').exists())

    def test_real_can_tasks_match_sequential_with_original_reader_processes(self):
        """两个真实合成BLF在外层工作进程中各启动原读取子进程，结果与顺序手算一致。参数: 无。返回: None。异常: 断言/原运行错误。"""
        factory = can_fixtures.CANRunnerTests(methodName='runTest')
        plans = (factory.fixture()[2], factory.fixture(frames=((0,b'\x02'),(1,b'\x04'),(2,b'\x06')))[2])
        jobs = tuple(BatchJob(f'can_{i}', plan) for i, plan in enumerate(plans))
        sequential = run_batch(BatchPlan(jobs), self.work/'can-sequential', device_label='home')
        parallel = run_batch(BatchPlan(jobs, process_count=2), self.work/'can-parallel', device_label='home')
        self.addCleanup(sequential.close)
        self.addCleanup(parallel.close)
        self.assertEqual((sequential.status, parallel.status), ('completed', 'completed'))
        for index, expected in enumerate((((0,1.0),(1000000000,5.0)), ((0,2.0),(1000000000,4.0)))):
            for report in (sequential, parallel):
                job = report.jobs[index]
                with published_path(job.output_dir/'选择结果.csv').open(encoding='utf-8-sig', newline='') as stream:
                    values = tuple((int(Decimal(row['时间（s）']) * 10**9),float(row['值'])) for row in csv.DictReader(stream))
                self.assertEqual(values, expected)
                document = json.loads(published_path(job.output_dir/'run_manifest.json').read_text(encoding='utf-8'))
                self.assertEqual(document['run']['input_diagnostics'][0]['record_count'], (4,3)[index])
            self.assertEqual(sequential.jobs[index].input_identity, parallel.jobs[index].input_identity)


def _current_plan(raw):
    """共享夹具使用当前公开结构；批量清单原样返回。"""
    from chronaxis.planning.config_groups import public_configuration
    return public_configuration(raw) if 'config_version' in raw else raw
