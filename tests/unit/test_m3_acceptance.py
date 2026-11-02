"""验证M3多种状态机共用输入、历史、结果发布时的组合行为。

手算依据在公开合成例子中；同时检查内存和两文件CSV、不同批大小与两后端，
以及同一实例通过CLI/批量运行的结果隔离。所有产物置专用work目录。
"""

from configuration_fixtures import current_fixture

import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from uuid import uuid4

from jsonschema import Draft202012Validator
from chronaxis import AnalysisPlan, AnalysisRunner, BatchJob, BatchRunner, validate_analysis_plan
from examples.m3_combined_analysis import combined_config, check_result

ROOT = Path(__file__).resolve().parents[2]


class M3AcceptanceTests(unittest.TestCase):
    """对同计划联合结果做手算核对；每次运行保留独立证据目录。"""

    def setUp(self):
        """创建本例工作目录。参数: 无。返回: None。异常: 原文件错误。"""
        self.work = ROOT / 'work/m3-accept-home-20261023/tests' / uuid4().hex
        self.work.mkdir(parents=True)

    def csv_config(self):
        """在报警及请求等待期间拆为两个CSV文件。

        参数: 无。返回: 使用两文件来源的配置。异常: 原文件写入错误。
        """
        raw = combined_config()
        source = raw['sources'][0]
        rows = source.pop('rows')
        fields = [signal['field'] for signal in raw['signals']]
        paths = []
        for name, part in (('first', rows[:5]), ('second', rows[5:])):
            path = self.work / f'{name}.csv'
            paths.append(str(path))
            with path.open('w', encoding='utf-8', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow(['time', *fields])
                for row in part:
                    values = [row['values'][name] for name in fields]
                    writer.writerow([row['time'][:-1], *[
                        '' if value is None else str(value).lower() if isinstance(value, bool) else value
                        for value in values]])
        source.update(source_type='signal_csv', paths=paths, time_column='time')
        return raw

    def run_checked(self, raw, folder):
        """运行并核对联合结果，关闭后检查资源。

        参数: raw配置及folder全新工作目录。返回: 摘要和发布目录。异常: 执行/断言错误。
        """
        result = AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(raw)), work_dir=folder / 'run')
        budget = result.spool.budget
        try:
            summary = check_result(result)
            output = result.write(folder / 'output').output_dir
        finally:
            result.close()
        self.assertEqual(budget.ram_bytes, 0)
        return summary, output

    def test_joint_rules_across_files_batches_and_backends(self):
        """迟滞和待响应状态跨文件/批继续，六种组合均满足手算。参数: 无。返回: None。异常: 断言。"""
        schema = json.loads((ROOT / 'Docs/Schema/analysis.schema.json').read_text(encoding='utf-8'))
        summaries = []
        for source in ('memory', 'csv'):
            for backend, batch in (('reference', 1), ('numpy', 2), ('numpy', 64)):
                with self.subTest(source=source, backend=backend, batch=batch):
                    raw = combined_config() if source == 'memory' else self.csv_config()
                    raw['execution'].update(backend=backend, batch_rows=batch)
                    Draft202012Validator(schema).validate(raw)
                    self.assertTrue(validate_analysis_plan(AnalysisPlan.from_dict(current_fixture(raw))).execution_ready)
                    summary, _ = self.run_checked(raw, self.work / f'{source}-{backend}-{batch}')
                    summaries.append(summary)
        self.assertTrue(all(summary == summaries[0] for summary in summaries))
        (self.work / 'summaries.json').write_text(json.dumps(current_fixture(summaries), ensure_ascii=False, indent=2), encoding='utf-8')

    def test_cli_matches_api_and_optional_signal_output_preserves_analysis(self):
        """可选信号输出不改变事件/统计；真实CLI四表逐字节等于API。参数: 无。返回: None。异常: 断言。"""
        raw = self.csv_config()
        summary, baseline = self.run_checked(raw, self.work / 'baseline')
        raw['outputs']['signal_csv'] = dict(signals=['temperature', 'voltage'])
        exported, api = self.run_checked(raw, self.work / 'api')
        self.assertEqual(summary, exported)
        plan = self.work / 'plan.json'
        plan.write_text(json.dumps(current_fixture(raw), ensure_ascii=False, indent=2), encoding='utf-8')
        process = subprocess.run([sys.executable, '-B', '-m', 'chronaxis', 'run', str(plan),
            '--work-dir', str(self.work / 'cli-run'), '--output', str(self.work / 'cli-output')],
            cwd=ROOT, env=os.environ.copy(), capture_output=True, text=True, encoding='utf-8', timeout=90)
        (self.work / 'cli.json').write_text(json.dumps(current_fixture(dict(device_label='home', returncode=process.returncode,
            stdout=process.stdout, stderr=process.stderr)), ensure_ascii=False, indent=2), encoding='utf-8')
        self.assertEqual(process.returncode, 0, process.stderr)
        for table in ('events', 'segments', 'calculations', 'sequences'):
            filename = table + '.csv'
            self.assertEqual((baseline / filename).read_bytes(), (api / filename).read_bytes())
            self.assertEqual((api / filename).read_bytes(), (self.work / 'cli-output' / filename).read_bytes())

    def test_batch_joint_plans_do_not_share_alarm_state(self):
        """同时运行有报警与无报警的组合计划，串并行输出一致且任务状态不串用。参数: 无。返回: None。异常: 断言。"""
        high, low = combined_config(), combined_config()
        low['dataset']['name'] = 'no_alarm_demo'
        for row in low['sources'][0]['rows']:
            row['values']['temperature'] = 70
        jobs = tuple(BatchJob(name, AnalysisPlan.from_dict(current_fixture(raw))) for name, raw in (('high', high), ('low', low)))
        reports = [BatchRunner(process_count=count).run(jobs, self.work / f'batch-{count}',
                                     device_label='home') for count in (1, 2)]
        for report in reports:
            self.assertEqual(report.status, 'completed', report.to_dict())
        for sequential, concurrent in zip(reports[0].jobs, reports[1].jobs):
            for table in ('events', 'segments', 'calculations', 'sequences'):
                self.assertEqual((sequential.output_dir / (table + '.csv')).read_bytes(),
                                 (concurrent.output_dir / (table + '.csv')).read_bytes())
            with (sequential.output_dir / 'events.csv').open(encoding='utf-8-sig', newline='') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(sum(row['rule_id'] == 'alarm' for row in rows), int(sequential.job_id == 'high'))


if __name__ == '__main__':
    unittest.main()
