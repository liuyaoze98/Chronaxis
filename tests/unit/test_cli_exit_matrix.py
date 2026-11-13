"""核对普通、fast和独立批量各阶段的真实CLI退出码，不改变既有分类。"""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
from workspace_fixtures import TemporaryDirectory
import unittest
from unittest.mock import patch

from chronaxis.cli import main
from chronaxis.configuration import load_configuration
from chronaxis.batch.runner import BatchRunner


ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / 'Docs/Current/examples'


class CLIExitMatrixTests(unittest.TestCase):
    """全部输入故障实际发生在专用目录；输出路径用普通文件制造确定的创建失败。"""

    def setUp(self):
        """建立能被普通和fast接受的同帧800J任务，不依赖外部真实日志。"""
        temporary = TemporaryDirectory(prefix='cli-exit-', dir=ROOT / 'work')
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.raw = load_configuration(EXAMPLES / 'message-minimal.yaml').data
        self.raw['execution'] = {'process_count': 1}
        self.raw['sources'][0].update(paths=str(EXAMPLES / 'data/message-clean.asc'),
                                     dbc_by_channel={'1': str(EXAMPLES / 'data/power.dbc')})
        self.raw['outputs'] = {'tables': 'jsonl'}

    def save(self, name: str, data: dict) -> Path:
        """写本例的JSON配置，返回绝对路径；文件错误原样抛出。"""
        path = self.folder / name
        path.write_text(json.dumps(data), encoding='utf8')
        return path

    def matrix(self, scenario: str, expected: tuple[int, ...]) -> None:
        """运行适用入口并核对约定退出码；stdout/stderr仅用于失败定位。"""
        raw = deepcopy(self.raw)
        if scenario == 'missing_dbc':
            raw['sources'][0]['dbc_by_channel']['1'] = str(self.folder / 'missing.dbc')
        elif scenario == 'empty_directory':
            directory = self.folder / 'empty'
            directory.mkdir()
            raw['sources'][0]['paths'] = str(directory)
        elif scenario == 'empty_glob':
            raw['sources'][0]['paths'] = str(self.folder / 'absent-*.asc')
        elif scenario == 'missing_recording':
            raw['sources'][0]['paths'] = str(self.folder / 'missing.asc')
        plan = self.save('analysis.json', raw)
        batch = self.save('batch.json', {'batch_version': 1, 'process_count': 1,
                                        'jobs': [{'plan': str(plan)}]})
        if scenario == 'missing_config':
            plan = batch = self.folder / 'missing.json'
        commands = [('validate',), ('explain',), ('run',), ('fast', 'validate'),
                    ('fast', 'explain'), ('fast', 'run'), ('batch', 'run'), ('fast', 'batch')]
        for index, command in enumerate(commands):
            with self.subTest(scenario=scenario, command=' '.join(command)):
                args = [*command, str(batch if index >= 6 else plan)]
                running = index in (2, 5, 6, 7)
                if running:
                    output = self.folder / f'output-{index}'
                    if scenario == 'output_is_file':
                        output.write_text('keep this file', encoding='utf8')
                    args.extend(['--output', str(output)])
                stdout, stderr = StringIO(), StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = main(args)
                diagnostic = stdout.getvalue() + stderr.getvalue()
                print(json.dumps({'scenario': scenario, 'command': ' '.join(command), 'exit': code}))
                self.assertEqual(code, expected[index], diagnostic[-1500:])
                if scenario == 'output_is_file' and running:
                    self.assertEqual(output.read_text(encoding='utf8'), 'keep this file')

    def test_missing_configuration(self):
        """缺配置在普通入口按文件失败归类，fast准备阶段按2归类。"""
        self.matrix('missing_config', (1, 1, 1, 2, 2, 2, 1, 2))

    def test_missing_dbc(self):
        """实际缺DBC不得与报文文件静态不读取混淆。"""
        self.matrix('missing_dbc', (1, 1, 1, 2, 2, 2, 1, 2))

    def test_empty_directory(self):
        """目录确实可枚举但没有输入；普通jobs批量将子计划失败记录为任务失败。"""
        self.matrix('empty_directory', (2, 2, 2, 2, 2, 2, 1, 2))

    def test_unmatched_glob(self):
        """通配符无匹配在单任务中为准备失败，在普通jobs批量子项中为任务失败。"""
        self.matrix('empty_glob', (2, 2, 2, 2, 2, 2, 1, 2))

    def test_explicit_recording_missing_at_run(self):
        """静态入口不读显式ASC，运行和批量才报告文件失败。"""
        self.matrix('missing_recording', (0, 0, 1, 0, 0, 1, 1, 1))

    def test_output_directory_is_existing_file(self):
        """保留已有文件；fast批量在报告建立前拒绝输出目标时返回2。"""
        self.matrix('output_is_file', (0, 0, 1, 0, 0, 1, 1, 2))

    def test_failure_after_analysis_at_publication(self):
        """在真实分析之后注入发布I/O故障，区分单任务和批量报告的处理路径。"""
        plan = self.save('analysis.json', self.raw)
        batch = self.save('batch.json', {'batch_version': 1, 'process_count': 1,
                                        'jobs': [{'plan': str(plan)}]})
        commands = [('run',), ('fast', 'run'), ('batch', 'run'), ('fast', 'batch')]
        for index, command in enumerate(commands):
            with self.subTest(command=' '.join(command)):
                output = self.folder / f'publish-output-{index}'
                stdout, stderr = StringIO(), StringIO()
                # 子进程照常完成分析和发布；这里只让当前CLI进程的最终发布失败。
                with patch('chronaxis.results.publication.PublicationNames.publish',
                           side_effect=PermissionError('synthetic final-publication failure')) as publish:
                    with redirect_stdout(stdout), redirect_stderr(stderr):
                        code = main([*command, str(batch if index >= 2 else plan), '--output', str(output)])
                print(json.dumps({'scenario': 'final_publication_io', 'command': ' '.join(command), 'exit': code}))
                self.assertTrue(publish.called)
                self.assertEqual(code, 2 if index == 3 else 1, stdout.getvalue() + stderr.getvalue())
                self.assertIn('synthetic final-publication failure', stdout.getvalue() + stderr.getvalue())
                if index >= 2:
                    self.assertTrue(list(output.rglob('*manifest*.json')), '批量任务已完成的输出必须保留')

    def batch_phase(self, config: Path, output: Path, *, fast: bool = False) -> tuple:
        """调用真实CLI和调度器；旁观是否进入调度，并读取实际写出的批量报告。"""
        stdout, stderr = StringIO(), StringIO()
        command = ['fast', 'batch'] if fast else ['batch', 'run']
        # 普通batch和fast.batch.run_batch共用BatchRunner._run；fast通过fast_specs选择执行分支。
        # spy仍调用原实现；合法fast对照的实际PID证明覆盖该路径，不用伪报告替代启动证据。
        original = BatchRunner._run
        with patch.object(BatchRunner, '_run', autospec=True, side_effect=original) as dispatch:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = main([*command, str(config), '--output', str(output)])
        reports = [json.loads(path.read_bytes()) for path in output.glob('batch_report_*.json')]
        workers = [job['worker_pid'] for report in reports for job in report['jobs']]
        print(json.dumps({'scenario': 'batch_loading_phase', 'config': config.name,
                          'command': ' '.join(command), 'exit': code,
                          'dispatch_entered': dispatch.called, 'reports': len(reports),
                          'worker_pids': workers}))
        return code, dispatch.called, reports, stdout.getvalue() + stderr.getvalue()

    def test_jobs_template_and_fast_fail_at_distinct_stages(self):
        """合法双CSV模板只替换primary；auxiliary空输入在jobs任务内或template加载时失败。"""
        first = self.folder / 'primary.csv'
        second = self.folder / 'replacement.csv'
        auxiliary = self.folder / 'auxiliary.csv'
        for path in (first, second, auxiliary):
            path.write_text('time,power\n0,10\n1,10\n2,10\n', encoding='ascii')
        raw = load_configuration(EXAMPLES / 'input-csv-minimal.yaml').data
        raw['dataset'] = {'name': 'two_csv', 'domain': {'start': '0s', 'end': '2s'}}
        clock = {'unit': 's', 'clock': 'synthetic_shared_clock'}
        primary_source = dict(raw['sources'][0], name='primary', path=str(first), time=dict(clock))
        auxiliary_source = dict(raw['sources'][0], name='auxiliary', path=str(auxiliary), time=dict(clock))
        raw['sources'] = [primary_source, auxiliary_source]
        signal = raw['signals'][0]
        raw['signals'] = [dict(signal, name='primary_power', source='primary'),
                          dict(signal, name='auxiliary_power', source='auxiliary')]
        raw['calculations'][0]['expr'] = 'primary_power + auxiliary_power'
        raw['outputs'] = {'tables': 'jsonl'}
        plan = self.save('two-csv.json', raw)
        jobs = self.save('csv-jobs.json', {'batch_version': 1, 'process_count': 1,
                                         'jobs': [{'plan': str(plan)}]})
        template = self.save('csv-template.json', {'batch_version': 1, 'process_count': 1,
                                                  'template': str(plan), 'source': 'primary',
                                                  'inputs': [str(second)]})
        # 先证明同一多来源配置、source选择及inputs都是合法的，不能让其他配置错误假冒空输入。
        for name, config in (('jobs', jobs), ('template', template)):
            with self.subTest(control=name):
                code, started, reports, diagnostic = self.batch_phase(config, self.folder / f'valid-{name}')
                self.assertEqual(code, 0, diagnostic)
                self.assertTrue(started)
                self.assertEqual(len(reports), 1)
                self.assertEqual(reports[0]['status'], 'completed')
                self.assertGreater(reports[0]['jobs'][0]['worker_pid'], 0)

        fast_valid = self.save('fast-valid.json', self.raw)
        fast_control = self.save('fast-valid-batch.json', {'batch_version': 1, 'process_count': 1,
                                                         'jobs': [{'plan': str(fast_valid)}]})
        code, started, reports, diagnostic = self.batch_phase(fast_control, self.folder / 'valid-fast', fast=True)
        self.assertEqual(code, 0, diagnostic)
        self.assertTrue(started)
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]['status'], 'completed')
        self.assertGreater(reports[0]['jobs'][0]['worker_pid'], 0)

        empty = self.folder / 'empty-csv'
        empty.mkdir()
        for kind, missing in (('directory', str(empty)),
                              ('glob', str(self.folder / 'absent-*.csv'))):
            broken = deepcopy(raw)
            broken['sources'][1]['path'] = missing
            plan.write_text(json.dumps(broken), encoding='utf8')
            for name, config in (('jobs', jobs), ('template', template)):
                with self.subTest(kind=kind, mode=name):
                    output = self.folder / f'{kind}-{name}'
                    code, started, reports, diagnostic = self.batch_phase(config, output)
                    if name == 'jobs':
                        self.assertEqual(code, 1, diagnostic)
                        self.assertTrue(started)
                        self.assertEqual(len(reports), 1)
                        self.assertEqual(reports[0]['status'], 'failed')
                        outcome = reports[0]['jobs'][0]
                        self.assertEqual(outcome['status'], 'failed')
                        self.assertGreater(outcome['worker_pid'], 0)
                        self.assertIn('sources[1]', outcome['error_message'])
                        self.assertIn('目录或通配符没有匹配的输入文件', outcome['error_message'])
                    else:
                        self.assertEqual(code, 2, diagnostic)
                        self.assertFalse(started)
                        self.assertEqual(reports, [])
                        self.assertFalse(output.exists())
                        self.assertIn('sources[1]', diagnostic)
                        self.assertIn('目录或通配符没有匹配的输入文件', diagnostic)

            # fast只接受CAN，因此用其合法CAN子计划验证同类空输入，不用不支持的CSV制造错误。
            fast_raw = deepcopy(self.raw)
            fast_raw['sources'][0]['paths'] = (str(empty) if kind == 'directory'
                                              else str(self.folder / 'absent-*.asc'))
            fast_plan = self.save(f'fast-{kind}.json', fast_raw)
            fast_batch = self.save(f'fast-batch-{kind}.json', {'batch_version': 1,
                'process_count': 1, 'jobs': [{'plan': str(fast_plan)}]})
            with self.subTest(kind=kind, mode='fast'):
                output = self.folder / f'{kind}-fast'
                code, started, reports, diagnostic = self.batch_phase(fast_batch, output, fast=True)
                self.assertEqual(code, 2, diagnostic)
                self.assertFalse(started)
                self.assertEqual(reports, [])
                self.assertFalse(output.exists())
                errors = json.loads(diagnostic)['errors']
                self.assertTrue(any(error['path'] == '$.sources[0].paths[0]' and
                                    '目录或通配符没有匹配的输入文件' in error['message'] for error in errors))
                self.assertTrue(all(error['code'] != 'unsupported_fast' for error in errors))


if __name__ == '__main__':
    unittest.main()
