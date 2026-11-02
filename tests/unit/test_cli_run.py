"""用真实CLI子进程及同计划API验证run、结果发布和失败关闭边界。

每例在work/m2-cli-tests/<uuid>写小CSV与完整计划，正常命令使用当前Python的
-B -m chronaxis，继承根正式PYTHONPATH。手算为2W持续1秒得到2J，活动[1,2)、
片段[0,3)，两后端/两格式与实际API生成的三表及清单关键事实交叉核对。

有限故障子脚本调用真正main，先让AnalysisRunner.run返回真实最终AnalysisResult，
再只对该同一对象观察或注入write/close故障，内部阶段结果始终透传。记录真实
close前后RAM及成功stdout时序，不以假成功对象证明资源已关。fatal cause例仅
验证异常分类，明确不作为资源关闭证据；悬空链接仅使用真实系统链接。

所有命令stdout/stderr/退出码和子进程观察事实保存在work，失败不删证据。
测试不导入Ref资源、不改生产逻辑、不宣称失败发布已回滚或内部账本等同RSS。
"""

from configuration_fixtures import current_fixture

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from uuid import uuid4

from chronaxis import AnalysisRunner, load_analysis_plan


ROOT = Path(__file__).absolute().parents[2]

# 只用于有限观察/故障例；正常路径始终真正-m。原方法透传，target来自实际run返回。
OBSERVE_SCRIPT = '''"""观察真正main的最终结果和原方法，事实写独立文件而非假造成功stdout。"""
from contextlib import ExitStack
import builtins
import json
from pathlib import Path
import sys
from unittest.mock import patch
from chronaxis import AnalysisRunner, AnalysisResult
from chronaxis.cli import main
from chronaxis.results.errors import AnalysisError
from chronaxis.execution.csv_reader import BudgetedSignalCSVSourceAdapter

mode, facts_path, *arguments = sys.argv[1:]
facts = dict(mode=mode, source_calls=0, runner_calls=0, target_returned=False,
    target_close_calls=0, completed_prints=0, completed_after_close=False, main_returned=False)
target = None
run, write = AnalysisRunner.run, AnalysisResult.write
close, install = AnalysisResult.close, AnalysisResult._install_directory
source = BudgetedSignalCSVSourceAdapter.iter_batches
output_print = builtins.print
fatal_inner, fatal_outer = MemoryError('fatal_memory_cause'), AnalysisError('fatal_outer_analysis')
cancel = KeyboardInterrupt('controlled_final_result_write_cancel')

def actual_run(owner, plan, work_dir=None):
    """参数: 原AnalysisRunner实参；返回: 原真实结果；异常: fatal分类例或原run错误。"""
    global target
    facts['runner_calls'] += 1
    if mode == 'fatal_chain':
        # 此单一分类例没有真实结果，不把异常构造当资源恢复证据。
        raise fatal_outer from fatal_inner
    target = run(owner, plan, work_dir=work_dir)
    facts['target_returned'] = True
    facts['target_run_id'] = target.metadata.run_id
    return target

def actual_source(owner, request, **kwargs):
    """参数: 实际CSV adapter/request；返回: 原read owner；异常: 原读取错误。"""
    facts['source_calls'] += 1
    return source(owner, request, **kwargs)

def actual_write(owner, destination):
    """参数: 实际结果/目标；返回: 原write清单；异常: 目标真实结果write前/后指定取消。"""
    if owner is target and mode == 'cancel_before_write':
        raise cancel
    manifest = write(owner, destination)
    if owner is target:
        facts['published'] = True
        if mode == 'cancel_after_write':
            raise cancel
    return manifest

def actual_install(owner, temporary, destination):
    """参数: 实际结果及目录；返回: 原安装结果；异常: 仅最终结果原安装前指定OSError。"""
    if owner is target and mode == 'install_error':
        facts['install_reached'] = True
        raise OSError('publish_install_controlled')
    return install(owner, temporary, destination)

def actual_close(owner):
    """参数: 实际结果；返回: 原close结果；异常: 真实目标已关后一次指定OSError。"""
    if owner is not target:
        return close(owner)
    facts['target_close_calls'] += 1
    returned = close(owner)
    facts['target_closed'] = owner._closed
    facts['ram_after_actual_close'] = owner.spool.budget.ram_bytes
    if mode == 'close_after_install' and not facts.get('close_fault_injected', False):
        facts['close_fault_injected'] = True
        raise OSError('close_after_install_controlled')
    return returned

def observed_print(*values, **keywords):
    """参数: 原print参数；返回: 原print结果；异常: 原输出错误，不重写stdout内容。"""
    if values and keywords.get('file', sys.stdout) is sys.stdout and type(values[0]) is str:
        try:
            payload = json.loads(values[0])
        except (json.JSONDecodeError, TypeError):
            payload = None
        if type(payload) is dict and payload.get('status') == 'completed':
            facts['completed_prints'] += 1
            facts['completed_after_close'] = (target is not None and target._closed
                and target.spool.budget.ram_bytes == 0)
    return output_print(*values, **keywords)

try:
    with ExitStack() as stack:
        stack.enter_context(patch.object(AnalysisRunner, 'run', new=actual_run))
        stack.enter_context(patch.object(BudgetedSignalCSVSourceAdapter, 'iter_batches', new=actual_source))
        stack.enter_context(patch.object(AnalysisResult, 'write', new=actual_write))
        stack.enter_context(patch.object(AnalysisResult, '_install_directory', new=actual_install))
        stack.enter_context(patch.object(AnalysisResult, 'close', new=actual_close))
        stack.enter_context(patch.object(builtins, 'print', new=observed_print))
        code = main(arguments)
        facts['main_returned'] = True
except BaseException as error:
    facts['escaped_type'] = type(error).__name__
    facts['fatal_outer_same'] = error is fatal_outer
    facts['fatal_cause_same'] = error.__cause__ is fatal_inner
    raise
finally:
    # 先保CLI自身收尾事实，再用原close作测试兜底；不得用兜底0冒充CLI正确释放。
    if target is not None:
        facts['closed_before_probe_cleanup'] = target._closed
        facts['ram_before_probe_cleanup'] = target.spool.budget.ram_bytes
        facts['iterators_before_probe_cleanup'] = len(target._iterators)
        try:
            close(target)
        finally:
            facts['ram_after_probe_cleanup'] = target.spool.budget.ram_bytes
    Path(facts_path).write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding='utf-8')
raise SystemExit(code)
'''


class CLIRunTests(unittest.TestCase):
    """每项使用独立目录和真正来源，错误路径不依赖其它TestCase或假owner。"""

    def setUp(self):
        """创建本项有限证据根。参数: 无。返回: None。异常: 原mkdir错误。"""
        self.work = ROOT / 'work' / 'm2-cli-tests' / uuid4().hex
        self.work.mkdir(parents=True)
        self.command_count = 0

    def fixture(self, *, tables='jsonl', suffix='case', retain_work=False):
        """保存真实四行CSV及1事件/1片段/1积分计划，不创建任何内部运行对象。

        参数: tables为csv/jsonl；suffix为本项独立子目录；retain_work显式保留现场。返回: (目录,计划Path,CSVPath)。
        异常: 原文件/JSON错误；声明backend固定numpy，使reference覆盖可核原身份不改。
        """
        directory = self.work / suffix
        directory.mkdir()
        source, path = directory / 'signal.csv', directory / 'analysis.json'
        source.write_text('t,Power\n0,0\n1,2\n2,0\n3,0\n', encoding='utf-8')
        config = dict(config_version=3,
            dataset=dict(name='cli_run', entity='synthetic', session='trial', domain=dict(start='0s', end='4s')),
            sources=[dict(name='table', source_type='signal_csv', path='signal.csv', time_column='t',
                time=dict(time_type='relative', unit='s', origin='cli_clock'))],
            signals=[dict(name='power', source='table', field='Power', dtype='float64', unit='W', valid_for='10s')],
            rules=[dict(name='active', rule_type='condition_duration', condition='power > 0', minimum_duration='0s')],
            windows=[dict(name='context', rule='active', anchor='activity', pre='1s', post='1s', merge='none')],
            calculations=[dict(name='energy', scope='session', operation='integral', expr='power', unit='J')],
            execution=dict(backend='numpy', batch_rows=2, result_buffer_rows=1, memory_budget_bytes=256 * 1024**2),
            outputs=dict(tables=tables), diagnostics=dict(retain_work=retain_work), metadata=dict(device_label='home', data_kind='synthetic'))
        path.write_text(json.dumps(current_fixture(config), ensure_ascii=False), encoding='utf-8')
        return directory, path, source

    def arguments(self, plan, output, work_dir=None, backend=None):
        """构造公开run参数。参数: plan/output及可选work/backend。返回: list。异常: 无。"""
        values = ['run', str(plan), '--output', str(output)]
        if work_dir is not None:
            values += ['--work-dir', str(work_dir)]
        if backend is not None:
            values += ['--backend', backend]
        return values

    def invoke(self, arguments, *, observe=None):
        """运行实际-m或受控main子脚本，保stdout/stderr/退出码与观察文件。

        参数: arguments为CLI参数；observe为有限故障/观察模式或None。
        返回: (CompletedProcess, 观察dict或None)。异常: 原启动/超时/编码或证据写入错误。
        """
        self.command_count += 1
        evidence = self.work / ('command-' + str(self.command_count))
        facts_path = evidence.with_suffix('.facts.json')
        environment = os.environ.copy()
        environment['PYTHONDONTWRITEBYTECODE'] = '1'
        environment['PYTHONIOENCODING'] = 'utf-8'
        environment['CHRONAXIS_DEVICE_LABEL'] = 'home'
        command = [sys.executable, '-B']
        # 常规成功和输入失败走真正模块入口；观察例仍调用原main及实际AnalysisRunner/Result方法。
        command += (['-m', 'chronaxis'] if observe is None else ['-c', OBSERVE_SCRIPT, observe, str(facts_path)])
        command += list(map(str, arguments))
        completed = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True,
            text=True, encoding='utf-8', errors='strict', timeout=90)
        evidence.with_suffix('.json').write_text(json.dumps(current_fixture(dict(device_label='home', command=command,
            cwd=str(ROOT), returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)),
            ensure_ascii=False, indent=2), encoding='utf-8')
        facts = None if observe is None else json.loads(facts_path.read_text(encoding='utf-8'))
        return completed, facts

    def summary(self, completed, plan, output, backend):
        """强核真实stdout的执行身份、业务概况及已安装manifest，不以退出0代替成功事实。

        参数: completed为真实命令结果；plan为原AnalysisPlan；output/实际backend明确。
        返回: (摘要dict, manifest dict)。异常: AssertionError/文件/JSON错误。
        """
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stderr, '')
        self.assertEqual(len(completed.stdout.strip().splitlines()), 1)
        value = json.loads(completed.stdout)
        self.assertEqual(set(value), {'status', 'run_id', 'plan_identity', 'backend', 'output', 'manifest', 'row_counts', 'device_label', 'analysis_outcome'})
        self.assertEqual((value['status'], value['plan_identity'], value['backend'], value['device_label']),
            ('completed', plan.identity, backend, 'home'))
        self.assertEqual((value['output'], value['manifest']), (str(output), str(output / 'run_manifest.json')))
        self.assertTrue(Path(value['output']).is_absolute())
        manifest = json.loads(Path(value['manifest']).read_text(encoding='utf-8'))
        self.assertEqual(manifest['status'], 'completed')
        self.assertEqual((manifest['run']['run_id'], manifest['run']['plan_hash'], manifest['run']['backend']),
            (value['run_id'], plan.identity, backend))
        self.assertEqual(value['row_counts'], dict(events=1, segments=1, calculations=1))
        self.assertEqual(manifest['row_counts'], value['row_counts'])
        self.assertEqual(value['analysis_outcome'], manifest['run']['analysis_outcome'])
        counts=value['analysis_outcome']['calculations']
        self.assertEqual(sum(counts[key] for key in ('complete','partial','indeterminate')),1)
        return value, manifest

    def assert_cli_closed(self, facts):
        """核兜底清理之前的真实最终结果已关且费用归零。

        参数: facts为观察子进程实录。返回: None。异常: AssertionError，拒绝假owner或兜底掩盖。
        """
        self.assertTrue(facts['target_returned'])
        self.assertTrue(facts['closed_before_probe_cleanup'])
        self.assertEqual(facts['ram_before_probe_cleanup'], 0)
        self.assertEqual(facts['iterators_before_probe_cleanup'], 0)
        self.assertEqual(facts['ram_after_probe_cleanup'], 0)

    def one_row(self, reader):
        """只取本夹具恰好一条typed行并核真实EOF，任何路径都关闭实际游标。

        参数: reader为新公开游标。返回: 唯一typed行，不积全表列表。
        异常: 原读取/关闭或计数断言错误；关闭副错只附主错，不盖掉原读错。
        """
        primary = None
        try:
            row = next(reader)
            with self.assertRaises(StopIteration):
                next(reader)
            return row
        except BaseException as error:
            primary = error
            raise
        finally:
            try:
                reader.close()
                self.assertTrue(reader.closed)
            except BaseException as cleanup:
                if primary is None:
                    raise
                primary.add_note('CLI测试游标关闭副错: ' + type(cleanup).__name__)
                if not reader.closed:
                    primary.row_iterator_cleanup_owner = reader

    def test_real_module_run_matches_api_tables_and_manifest_both_backends_formats(self):
        """四个真实-m组合与独立API逐表bytes相同；2J/活动/片段来自手算而非被测内核。

        参数: 无。返回: None。异常: 原输入、摘要、手算、身份、表内容或真实关闭不符即失败。
        """
        for backend in ('reference', 'numpy'):
            for tables in ('csv', 'jsonl'):
                with self.subTest(backend=backend, tables=tables):
                    directory, path, _ = self.fixture(tables=tables, suffix=backend + '-' + tables)
                    original_bytes, plan = path.read_bytes(), load_analysis_plan(path)
                    output = directory / 'cli-output'
                    completed, _ = self.invoke(self.arguments(path, output, directory / 'cli-work', backend))
                    value, manifest = self.summary(completed, plan, output, backend)
                    with AnalysisRunner(backend=backend).run(plan, work_dir=directory / 'api-work') as result:
                        calculation = self.one_row(result.iter_calculations())
                        self.assertEqual((calculation.value, calculation.unit), (2.0, 'J'))
                        event = self.one_row(result.iter_events())
                        segment = self.one_row(result.iter_segments())
                        self.assertEqual((event.start_ns, event.end_ns, event.status), (10**9, 2 * 10**9, 'closed'))
                        self.assertEqual((segment.start_ns, segment.end_ns), (0, 3 * 10**9))
                        api_manifest = result.write(directory / 'api-output')
                        self.assertEqual(dict(api_manifest.row_counts), value['row_counts'])
                        self.assertIsNone(result.metadata.input_identity)
                        self.assertNotIn('input_identity', manifest['run'])
                        self.assertEqual(result.metadata.plan_hash, manifest['run']['plan_hash'])
                        self.assertEqual(result.metadata.backend, backend)
                        for table in ('events', 'segments', 'calculations'):
                            self.assertEqual((output / (table + '.' + tables)).read_bytes(),
                                (api_manifest.output_dir / (table + '.' + tables)).read_bytes())
                        budget = result.spool.budget
                    self.assertEqual(budget.ram_bytes, 0)
                    self.assertEqual(path.read_bytes(), original_bytes)
                    self.assertEqual(plan.execution.backend, 'numpy')

    def test_real_result_close_finishes_before_stdout_and_output_can_be_inside_work(self):
        """透传真实run/write/close，只有最终RAM0后才出现成功stdout；允许output位于work内部。

        参数: 无。返回: None。异常: 原资源、一次CSV扫描或输出关闭顺序不符即失败。
        """
        directory, path, _ = self.fixture(retain_work=True)
        work_dir = directory / 'analysis-work'
        output = work_dir / 'published'
        completed, facts = self.invoke(self.arguments(path, output, work_dir), observe='normal')
        value, _ = self.summary(completed, load_analysis_plan(path), output, 'numpy')
        self.assert_cli_closed(facts)
        self.assertEqual((facts['source_calls'], facts['runner_calls'], facts['completed_prints']), (1, 1, 1))
        self.assertTrue(facts['completed_after_close'])
        self.assertEqual(facts['target_run_id'], value['run_id'])

    def test_input_config_io_analysis_and_fatal_cause_errors_do_not_publish_success(self):
        """配置2、缺文件1、真实坏时间读取1分别保cause；fatal MemoryError链不被普通返回吞掉。

        参数: 无。返回: None。异常: 退出分类、原错误可见性或意外completed即失败。
        """
        for mode in ('bad_json', 'missing_plan', 'bad_csv'):
            with self.subTest(mode=mode):
                directory, path, source = self.fixture(suffix=mode)
                expected, token = 1, path.name
                if mode == 'bad_json':
                    path.write_bytes(b'{"config_version":')
                    expected = 2
                elif mode == 'missing_plan':
                    path = directory / 'missing-plan.json'
                    token = path.name
                else:
                    source.write_text('t,Power\n0,0\nbroken_time,2\n', encoding='utf-8')
                    token = source.name + ':3'
                output = directory / 'output'
                completed, _ = self.invoke(self.arguments(path, output, directory / 'work'))
                self.assertEqual(completed.returncode, expected)
                self.assertEqual(completed.stdout, '')
                self.assertIn(token, completed.stderr)
                if mode == 'bad_csv':
                    # 原reader公开文件/物理行与真实cause，不为测试补读或猜原坏值回显。
                    for diagnosis in ('SourceReadError', 'ValueError', '非法十进制时间文本', 'InvalidOperation'):
                        self.assertIn(diagnosis, completed.stderr)
                self.assertFalse(output.exists())
        directory, path, _ = self.fixture(suffix='fatal-chain')
        output = directory / 'output'
        completed, facts = self.invoke(self.arguments(path, output, directory / 'work'), observe='fatal_chain')
        self.assertNotEqual(completed.returncode, 0)
        self.assertFalse(facts['main_returned'])
        self.assertTrue(facts['fatal_outer_same'] and facts['fatal_cause_same'])
        self.assertIn('MemoryError', completed.stderr)
        self.assertIn('fatal_memory_cause', completed.stderr)
        self.assertEqual(completed.stdout, '')
        self.assertFalse(output.exists())

    def test_existing_file_and_directory_are_rejected_before_runner_or_source(self):
        """output/work任一已有文件或目录均拒覆盖，真实CSV迭代计数为0。

        参数: 无。返回: None。异常: 预检次序、sentinel bytes或目录内容改变即失败。
        """
        for position in ('output', 'work'):
            for kind in ('file', 'directory'):
                with self.subTest(position=position, kind=kind):
                    directory, path, _ = self.fixture(suffix=position + '-' + kind)
                    output, work_dir = directory / 'output', directory / 'work'
                    existing = output if position == 'output' else work_dir
                    sentinel = existing
                    if kind == 'directory':
                        existing.mkdir()
                        sentinel = existing / 'keep.bin'
                    sentinel.write_bytes(b'preexisting\x00\r\n')
                    completed, facts = self.invoke(self.arguments(path, output, work_dir), observe='preflight')
                    self.assertEqual(completed.returncode, 1)
                    self.assertEqual((facts['runner_calls'], facts['source_calls']), (0, 0))
                    self.assertEqual(sentinel.read_bytes(), b'preexisting\x00\r\n')
                    # 已有那一侧必须保留；另一侧在预检拒绝时不得先创建。
                    self.assertFalse((work_dir if position == 'output' else output).exists())
                    self.assertEqual(completed.stdout, '')
                    if kind == 'directory':
                        self.assertEqual(set(existing.iterdir()), {sentinel})

    def test_actual_dangling_link_is_rejected_without_scanning_or_replacing(self):
        """output/work实际悬空目录链接即使exists为False仍须预拒，不用假lstat代替。

        参数: 无。返回: None。异常: 链接保护/预检失败；缺实际系统链接权限明确skip记录。
        """
        cases = []
        # 先建立两条实际链接；缺系统权限仅skip本方法，不把其它路径保护方法一并跳过。
        for position in ('output', 'work'):
            directory, path, _ = self.fixture(suffix='dangling-' + position)
            missing = directory / 'missing-link-target'
            output, work_dir = directory / 'output', directory / 'work'
            link = output if position == 'output' else work_dir
            try:
                link.symlink_to(missing, target_is_directory=True)
            except OSError as error:
                if getattr(error, 'winerror', None) == 1314 or isinstance(error, PermissionError):
                    self.skipTest('当前实际环境不允许创建Windows符号链接: ' + str(error))
                raise
            cases.append((position, path, missing, output, work_dir, link))
        for position, path, missing, output, work_dir, link in cases:
            with self.subTest(position=position):
                before = os.readlink(link)
                self.assertTrue(link.is_symlink())
                self.assertFalse(link.exists())
                completed, facts = self.invoke(self.arguments(path, output, work_dir), observe='preflight')
                self.assertEqual(completed.returncode, 1)
                self.assertEqual((facts['runner_calls'], facts['source_calls']), (0, 0))
                self.assertEqual(os.readlink(link), before)
                self.assertTrue(link.is_symlink())
                self.assertFalse(missing.exists())
                self.assertFalse((work_dir if position == 'output' else output).exists())
                self.assertEqual(completed.stdout, '')

    def test_ref_output_work_and_impossible_work_output_nesting_are_preflight_errors(self):
        """Ref输出/工作路径及work等于或位于output内均先拒，不写原目录也不读取CSV。

        参数: 无。返回: None。异常: 路径拒绝分类、创建顺序或原Ref目录mtime改变即失败。
        """
        directory, path, _ = self.fixture()
        # 合成受保护目录，不依赖或改动开发仓库里的历史项目。
        ref = directory / 'RefProjects'
        ref.mkdir()
        protected = ref / ('cli-run-rejected-' + uuid4().hex)
        output = directory / 'output'
        cases = ((protected / 'output', directory / 'work-ref-output'),
            (directory / 'output-ref-work', protected / 'work'),
            (output, output), (directory / 'ancestor', directory / 'ancestor' / 'nested-work'))
        before = ref.stat().st_mtime_ns
        for destination, work_dir in cases:
            with self.subTest(output=str(destination), work=str(work_dir)):
                completed, facts = self.invoke(self.arguments(path, destination, work_dir), observe='preflight')
                self.assertEqual(completed.returncode, 2)
                self.assertEqual((facts['runner_calls'], facts['source_calls']), (0, 0))
                self.assertFalse(destination.exists())
                self.assertFalse(work_dir.exists())
                self.assertEqual(completed.stdout, '')
        self.assertFalse(protected.exists())
        self.assertEqual(ref.stat().st_mtime_ns, before)

    def test_real_publish_install_error_retains_cause_closes_result_and_has_no_completed_target(self):
        """实际write已生成表后在原安装前失败；原OSError可见、结果真实关闭且目标未完成。

        参数: 无。返回: None。异常: cause被隐藏、伪成功、遗留费用或临时completed未改标即失败。
        """
        directory, path, _ = self.fixture(retain_work=True)
        output = directory / 'output'
        completed, facts = self.invoke(self.arguments(path, output, directory / 'work'), observe='install_error')
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stdout, '')
        self.assertIn('publish_install_controlled', completed.stderr)
        self.assertTrue(facts['install_reached'])
        self.assert_cli_closed(facts)
        self.assertFalse(output.exists())
        markers = tuple(directory.glob('.output.incomplete-*/run_manifest.json'))
        self.assertTrue(markers)
        for marker in markers:
            self.assertNotEqual(json.loads(marker.read_text(encoding='utf-8'))['status'], 'completed')

    def test_keyboard_interrupt_before_and_after_real_write_is_130_with_actual_close(self):
        """真实最终结果write前/后取消均关闭并退出130，已安装的完整输出如实保留。

        参数: 无。返回: None。异常: 取消被吞、成功stdout提前或真实关闭/安装事实不符即失败。
        """
        for mode in ('cancel_before_write', 'cancel_after_write'):
            with self.subTest(mode=mode):
                directory, path, _ = self.fixture(suffix=mode)
                output = directory / 'output'
                completed, facts = self.invoke(self.arguments(path, output, directory / 'work'), observe=mode)
                self.assertEqual(completed.returncode, 130)
                self.assertEqual(completed.stdout, '')
                self.assertEqual(facts['completed_prints'], 0)
                self.assert_cli_closed(facts)
                if mode == 'cancel_before_write':
                    self.assertFalse(output.exists())
                else:
                    self.assertTrue(facts['published'])
                    self.assertEqual(json.loads((output / 'run_manifest.json').read_text(encoding='utf-8'))['status'], 'completed')

    def test_close_error_after_real_close_never_prints_success_or_claims_output_rollback(self):
        """真实发布及原close已完成后抛错仍退出1，保已安装目录并明确提示可能已发布。

        参数: 无。返回: None。异常: stdout误报成功、错误路径/cause不可见或账本不为0即失败。
        """
        directory, path, _ = self.fixture()
        output = directory / 'output'
        completed, facts = self.invoke(self.arguments(path, output, directory / 'work'), observe='close_after_install')
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stdout, '')
        self.assertEqual(facts['completed_prints'], 0)
        self.assertTrue(facts['published'] and facts['close_fault_injected'])
        self.assert_cli_closed(facts)
        self.assertIn('close_after_install_controlled', completed.stderr)
        self.assertIn('可能已发布', completed.stderr)
        self.assertIn(str(output), completed.stderr)
        self.assertEqual(json.loads((output / 'run_manifest.json').read_text(encoding='utf-8'))['status'], 'completed')


if __name__ == '__main__':
    # 实际CLI仅由根统一正式执行本测试时运行，导入不生成来源或启动分析。
    unittest.main()
