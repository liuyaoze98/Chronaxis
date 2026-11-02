"""通过真实-m子进程验证静态validate/explain，不运行分析来源或结果发布。

输入为本测试在work/m2-cli-tests内生成的完整JSON配置；CSV、BLF和DBC仅声明
不存在的路径。输出逐字段对照同一公共AnalysisRunner报告，错误核退出码及具体位置。
每个命令保stdout/stderr和退出码；标准库帮助/参数测试使用-B-S且PYTHONPATH仅src。
内嵌脚本只观察真实配置读取并禁止运行层、输入I/O、mkdir及spawn；取消在真实
共享配置解析完成后注入，不能以未命中故障的正常退出伪装取消恢复。
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
from chronaxis.planning.config_groups import public_configuration
from chronaxis.planning import AnalysisPlan

ROOT = Path(__file__).absolute().parents[2]

# 此脚本进入真实__main__，仅设置不允许发生的副作用哨兵，不替换公开AnalysisRunner报告。
GUARD_SCRIPT = '''"""观察静态CLI的真实配置读取，阻止分析I/O；仅用于独立子进程测试。"""
import builtins
import importlib.abc
import json
import os
from pathlib import Path
import multiprocessing
import runpy
import sys

config, audit = Path(sys.argv[1]).absolute(), Path(sys.argv[2]).absolute()
blocked = {Path(value).absolute() for value in json.loads(sys.argv[3])}
arguments = sys.argv[4:]
facts = {'config_opens': 0, 'forbidden_calls': []}
original_path_open, original_open, original_stat = Path.open, builtins.open, Path.stat

def checked(value):
    """核被禁止的真实输入定位；参数: 路径或FD；返回: Path或None；异常: AssertionError。"""
    if isinstance(value, bytes):
        value = os.fsdecode(value)
    path = Path(value).absolute() if isinstance(value, (str, os.PathLike)) else None
    if path in blocked:
        facts['forbidden_calls'].append(str(path))
        raise AssertionError('静态命令触碰来源或DBC：' + str(path))
    return path

def path_open(path, *args, **kwargs):
    """透传真实配置open；参数: Path及原参数；返回: 原FD；异常: 原I/O或禁止输入。"""
    selected = checked(path)
    if selected == config:
        facts['config_opens'] += 1
    return original_path_open(path, *args, **kwargs)

def builtin_open(path, *args, **kwargs):
    """守住builtin输入入口；参数: 原open参数；返回: 原FD；异常: 原I/O或禁止输入。"""
    checked(path)
    return original_open(path, *args, **kwargs)

def path_stat(path, *args, **kwargs):
    """禁止来源存在性探测；参数: 原stat参数；返回: 原stat；异常: 禁止输入或原I/O。"""
    checked(path)
    return original_stat(path, *args, **kwargs)

def forbidden(*args, **kwargs):
    """拒mkdir或spawn；参数: 任意原参数；返回: 无；异常: AssertionError。"""
    facts['forbidden_calls'].append('mkdir_or_spawn')
    raise AssertionError('静态命令不能mkdir或spawn')

class NoRunSession(importlib.abc.MetaPathFinder):
    """运行层模块不能因静态命令被加载，避免仅靠不存在来源掩盖提前执行。"""
    def find_spec(self, fullname, path=None, target=None):
        """检查导入名称；参数: 标准finder参数；返回: None；异常: 禁止运行层AssertionError。"""
        if fullname == 'chronaxis.execution.run_session':
            facts['forbidden_calls'].append(fullname)
            raise AssertionError('静态命令不能加载RunSession')
        return None

Path.open, builtins.open, Path.stat = path_open, builtin_open, path_stat
Path.mkdir, multiprocessing.get_context = forbidden, forbidden
sys.meta_path.insert(0, NoRunSession())
sys.argv = ['chronaxis', *arguments]
try:
    runpy.run_module('chronaxis', run_name='__main__')
finally:
    audit.write_text(json.dumps(facts), encoding='utf-8')
'''

# 共享解析已完成且真实配置FD关闭后取消，CLI必须返回130。
CANCEL_SCRIPT = '''"""在实际配置读取后取消静态命令并记录真实FD关闭，不替换数据执行器。"""
import json
from pathlib import Path
import runpy
import sys

config, audit = Path(sys.argv[1]).absolute(), Path(sys.argv[2]).absolute()
arguments = sys.argv[3:]
import chronaxis.configuration as configuration
original_open, original_parse, captured = Path.open, configuration.parse_configuration, {}

def observed_open(path, *args, **kwargs):
    """保留实际配置FD用于关闭核对。参数: 原打开参数。返回: FD。异常: 原IO错误。"""
    handle = original_open(path, *args, **kwargs)
    if path.absolute() == config:
        captured['handle'] = handle
    return handle

def interrupted_parse(text, **kwargs):
    """透传实际共享解析再取消。参数: 原文本/选项。返回: 文档。异常: 原KI或解析错误。"""
    value = original_parse(text, **kwargs)
    if Path(value.source).absolute() == config:
        captured['config_version'] = value.data['config_version']
        raise KeyboardInterrupt('static-config-read-cancel')
    return value

Path.open = observed_open
configuration.parse_configuration = interrupted_parse
sys.argv = ['chronaxis', *arguments]
try:
    runpy.run_module('chronaxis', run_name='__main__')
finally:
    handle = captured.get('handle')
    audit.write_text(json.dumps({'hit': handle is not None, 'fd_closed': None if handle is None else handle.closed,
        'config_version': captured.get('config_version')}), encoding='utf-8')
'''


def static_configuration(backend='numpy', *, can=False):
    """生成不存在来源的完整静态计划；参数: 后端/是否CAN；返回: dict；异常: 无。"""
    source = {'name': 'table', 'source_type': 'signal_csv', 'path': 'absent/table.csv', 'time_column': 't',
              'time': {'time_type': 'relative', 'unit': 's', 'origin': 'synthetic_common'}}
    signals = [{'name': name, 'source': 'table', 'field': raw, 'dtype': 'float64',
                'unit': unit, 'valid_for': '3s'} for name, raw, unit in (
                    ('voltage', 'Voltage', 'V'), ('current', 'Current', 'A'))]
    if can:
        source = {'name': 'table', 'source_type': 'can_blf', 'path': 'absent/input.blf',
            'dbc_by_channel': {'1': 'absent/input.dbc'}, 'legacy_profile': 'sclicer-functions-v1',
            'time': {'time_type': 'relative', 'unit': 's', 'origin': 'synthetic_common'}}
        for signal in signals:
            signal['field'] = {'channel': 1,  'signal': signal['field'],
                               'frame_id': 256, 'is_extended': False, 'is_fd': False}
    return public_configuration({'config_version': 3,
        'dataset': {'name': 'static_cli', 'entity': 'synthetic', 'session': 'trial',
                    'domain': {'start': '0s', 'end': '10s'}},
        'sources': [source], 'signals': signals, 'derived': {'power': {'expr': 'voltage * current', 'unit': 'W'}},
        'rules': [{'name': 'active', 'rule_type': 'condition_duration', 'condition': 'current > 0', 'minimum_duration': '1s'}],
        'windows': [{'name': 'context', 'rule': 'active', 'anchor': 'activity', 'pre': '1s',
                     'post': '0s', 'merge': 'exit_delay', 'exit_delay': '2s'}],
        'calculations': [{'name': 'energy', 'scope': 'segment:context', 'operation': 'integral', 'expr': 'power', 'unit': 'J'},
                    {'name': 'samples', 'scope': 'session', 'operation': 'select', 'expr': 'current'}],
        'execution': {'backend': backend, 'batch_rows': 2, 'result_buffer_rows': 2}})


def validation_dict(report):
    """按公开固定JSON合同展开原AnalysisRunner报告；参数: ValidationReport；返回: dict；异常: 属性错误传播。"""
    return {'valid': report.valid, 'errors': list(report.errors), 'warnings': list(report.warnings),
            'capability_status': dict(report.capability_status), 'execution_ready': report.execution_ready}


def explanation_dict(report):
    """保公开解释字段和节点原序；参数: ExplainReport；返回: dict；异常: 属性错误传播。"""
    # 独立展开新版公开需求字段，不调用被测CLI序列化器生成自身预期。
    requirements = report.input_requirements
    scopes = [] if requirements is None else [{'source': item.source,
        'input_check': item.input_check, 'time_scope': item.time_scope,
        'required_aliases': list(item.required_aliases), 'decode_frame_ids': list(item.decode_frame_ids),
        'reasons': list(item.reasons), 'active': item.active} for item in requirements.sources]
    return {'input_requirements': scopes, 'validation': validation_dict(report.validation), 'plan_identity': report.plan_identity,
        'source_names': list(report.source_names), 'nodes': [{'node_id': item.node_id, 'node_type': item.node_type,
            'dependencies': list(item.dependencies), 'unit': item.unit, 'backend': item.backend} for item in report.nodes],
        'history_ns': dict(report.history_ns), 'budget': dict(report.budget),
        'intervals': {name: dict(mode=choice.mode, step_ns=choice.step_ns, driver=choice.driver)
                      for name, choice in report.intervals.resolved},
        'diagnostics': dict(trace=report.diagnostics.trace, integrity=report.diagnostics.integrity,
                            retain_work=report.diagnostics.retain_work)}


class StaticCLITests(unittest.TestCase):
    """每例拥有独立work配置/命令日志，使用实际子进程且不安装console script。"""

    def setUp(self):
        """建本测试的配置与日志目录；参数: 无；返回: None；异常: 原文件系统错误。"""
        self.work = ROOT / 'work' / 'm2-cli-tests' / 'static' / uuid4().hex
        self.inputs, self.logs = self.work / 'configuration directory', self.work / 'logs'
        self.inputs.mkdir(parents=True)
        self.logs.mkdir()
        self.config = self.inputs / '分析 configuration.json'
        self.index = 0

    def prepare(self, configuration=None):
        """写实际JSON配置；参数: 可选完整dict；返回: 原bytes；异常: 原编码/文件错误。"""
        value = static_configuration() if configuration is None else configuration
        encoded = json.dumps(current_fixture(value), ensure_ascii=False, indent=2).encode('utf-8')
        self.config.write_bytes(encoded)
        return encoded

    def invoke(self, arguments, *, stdlib=False, script=None, script_arguments=()):
        """运行实际-m或观察脚本并保留全部命令结果。

        参数: CLI arguments；stdlib选择-B-S/PYTHONPATH仅src；script/其参数仅用于
        副作用及取消观察。返回: CompletedProcess。异常: 启动/超时/UTF8错误原样传播。
        """
        environment = os.environ.copy()
        environment.update(PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
        if stdlib:
            environment['PYTHONPATH'] = str(ROOT / 'src')
        command = [sys.executable, '-B'] + (['-S'] if stdlib else [])
        command += ['-m', 'chronaxis'] if script is None else ['-c', script, *map(str, script_arguments)]
        # 本套验证固定机器报告，显式声明JSON；默认人读输出由独立专项覆盖。
        arguments=list(arguments)
        if arguments and arguments[0] in ('validate','explain') and '--help' not in arguments:
            arguments+=['--format','json']
        command += list(map(str, arguments))
        completed = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True,
            text=True, encoding='utf-8', errors='strict', timeout=60)
        self.index += 1
        (self.logs / ('command-' + str(self.index) + '.json')).write_text(json.dumps(current_fixture({
            'device_label': 'home', 'cwd': str(ROOT), 'command': command,
            'returncode': completed.returncode, 'stdout': completed.stdout, 'stderr': completed.stderr}),
            ensure_ascii=False, indent=2), encoding='utf-8')
        return completed

    def success(self, completed):
        """核成功单行JSON和stderr；参数: 实际子进程；返回: JSON对象；异常: AssertionError/JSON错误。"""
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stderr, '')
        self.assertEqual(len(completed.stdout.strip().splitlines()), 1, completed.stdout)
        return json.loads(completed.stdout)

    def test_validate_csv_matches_runner_and_keeps_unverified_warnings(self):
        """不存在CSV仍仅作静态校验；参数: 无；返回: None；异常: AssertionError。"""
        encoded = self.prepare()
        expected = validation_dict(AnalysisRunner().validate(load_analysis_plan(self.config)))
        actual = self.success(self.invoke(['validate', self.config]))
        self.assertEqual(actual, expected)
        self.assertEqual(set(actual), {'valid', 'errors', 'warnings', 'capability_status', 'execution_ready'})
        self.assertIs(actual['valid'], True)
        self.assertIs(actual['execution_ready'], True)
        self.assertEqual(actual['errors'], [])
        self.assertTrue(actual['warnings'])
        self.assertEqual(self.config.read_bytes(), encoded)
        self.assertFalse((self.inputs / 'absent').exists())

    def test_explain_preserves_fixed_nodes_and_configuration_directory_identity(self):
        """解释身份依配置目录且节点完整；参数: 无；返回: None；异常: AssertionError。"""
        configuration = static_configuration()
        self.prepare(configuration)
        plan = load_analysis_plan(self.config)
        actual = self.success(self.invoke(['explain', self.config]))
        self.assertEqual(actual, explanation_dict(AnalysisRunner().explain(plan)))
        self.assertEqual(set(actual), {'input_requirements', 'validation', 'plan_identity', 'source_names', 'nodes', 'history_ns', 'budget', 'intervals', 'diagnostics'})
        self.assertEqual(len(actual['input_requirements']), 1)
        scope = actual['input_requirements'][0]
        self.assertEqual((scope['source'], scope['input_check'], scope['time_scope']), ('table', 'auto', 'source'))
        self.assertEqual(scope['required_aliases'], ['voltage', 'current'])
        self.assertEqual(scope['decode_frame_ids'], [])
        self.assertTrue(scope['reasons'])
        self.assertEqual(actual['source_names'], ['table'])
        self.assertEqual(len(actual['nodes']), 5)
        self.assertEqual({item['node_id'] for item in actual['nodes']}, {'power', 'active', 'context', 'energy', 'samples'})
        self.assertEqual(plan.sources[0].config.paths, (self.inputs / 'absent/table.csv',))
        wrong_base = AnalysisPlan.from_dict(current_fixture(configuration), base_dir=ROOT)
        self.assertNotEqual(actual['plan_identity'], wrong_base.identity)

    def test_backend_override_both_directions_keeps_original_plan_identity(self):
        """ref↔np覆盖只改变有效解释后端；参数: 无；返回: None；异常: AssertionError。"""
        for original, effective in (('numpy', 'reference'), ('reference', 'numpy')):
            with self.subTest(original=original, effective=effective):
                encoded = self.prepare(static_configuration(original))
                plan = load_analysis_plan(self.config)
                identity = plan.identity
                actual = self.success(self.invoke(['explain', self.config, '--backend', effective]))
                self.assertEqual(actual, explanation_dict(AnalysisRunner(backend=effective).explain(plan)))
                nodes = {item['node_id']: item for item in actual['nodes']}
                self.assertEqual(nodes['power']['backend'], effective)
                self.assertEqual(nodes['energy']['backend'], effective)
                self.assertEqual(nodes['active']['backend'], 'state_driver')
                self.assertEqual((actual['plan_identity'], plan.identity, plan.execution.backend), (identity, identity, original))
                self.assertEqual(self.config.read_bytes(), encoded)
                validation = self.success(self.invoke(['validate', self.config, '--backend', effective]))
                self.assertEqual(validation, validation_dict(AnalysisRunner(backend=effective).validate(plan)))

    def test_can_validate_and_explain_do_not_need_real_blf_or_dbc(self):
        """CAN完整声明只静态检查，实际单位/字段未核；参数: 无；返回: None；异常: AssertionError。"""
        self.prepare(static_configuration(can=True))
        plan = load_analysis_plan(self.config)
        actual = self.success(self.invoke(['validate', self.config]))
        self.assertEqual(actual, validation_dict(AnalysisRunner().validate(plan)))
        self.assertTrue(actual['warnings'])
        explanation = self.success(self.invoke(['explain', self.config]))
        self.assertEqual(explanation, explanation_dict(AnalysisRunner().explain(plan)))
        self.assertFalse((self.inputs / 'absent/input.blf').exists())
        self.assertFalse((self.inputs / 'absent/input.dbc').exists())

    def test_guarded_module_entry_never_reads_data_or_loads_run_session(self):
        """真实__main__加I/O哨兵仍成功；参数: 无；返回: None；异常: AssertionError。"""
        for can in (False, True):
            for action in ('validate', 'explain'):
                with self.subTest(can=can, action=action):
                    encoded = self.prepare(static_configuration(can=can))
                    audit = self.logs / ('guard-' + str(can) + '-' + action + '.json')
                    blocked = [str(self.inputs / 'absent' / name) for name in ('table.csv', 'input.blf', 'input.dbc')]
                    completed = self.invoke([action, self.config], script=GUARD_SCRIPT,
                        script_arguments=(self.config, audit, json.dumps(current_fixture(blocked))))
                    self.success(completed)
                    facts = json.loads(audit.read_text(encoding='utf-8'))
                    self.assertEqual(facts, {'config_opens': 1, 'forbidden_calls': []})
                    self.assertEqual(self.config.read_bytes(), encoded)
                    self.assertEqual(set(self.work.iterdir()), {self.inputs, self.logs})

    def test_help_and_argument_errors_need_only_standard_library(self):
        """-B-S只给src仍可帮助和参数拒绝；参数: 无；返回: None；异常: AssertionError。"""
        for arguments in (['--help'], ['validate', '--help'], ['explain', '--help']):
            with self.subTest(arguments=arguments):
                completed = self.invoke(arguments, stdlib=True)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertIn('usage:', completed.stdout.lower())
                self.assertEqual(completed.stderr, '')
        for arguments in (['validate'], ['explain'], ['validate', 'absent.json', '--backend', 'auto'],
                          ['explain', 'absent.json', '--output', 'forbidden-output']):
            with self.subTest(arguments=arguments):
                completed = self.invoke(arguments, stdlib=True)
                self.assertEqual(completed.returncode, 2, completed.stderr)
                self.assertIn('usage:', completed.stderr.lower())
                self.assertNotIn('ModuleNotFoundError', completed.stderr)
                self.assertNotIn('Traceback', completed.stderr)

    def test_real_missing_configuration_is_io_exit_one(self):
        """真实缺文件与配置语义错误分开；参数: 无；返回: None；异常: AssertionError。"""
        missing = self.inputs / 'not-present.json'
        for action in ('validate', 'explain'):
            with self.subTest(action=action):
                completed = self.invoke([action, missing])
                self.assertEqual(completed.returncode, 1, completed.stderr)
                payload=json.loads(completed.stdout)
                self.assertFalse(payload['valid'])
                self.assertEqual(payload['error']['source'],str(missing))
                self.assertEqual(payload['error']['code'],'load_error')
                self.assertEqual(completed.stderr,'')
                self.assertNotIn('Traceback', completed.stderr)

    def test_bad_json_unknown_key_and_ast_have_config_exit_and_exact_path(self):
        """坏JSON/未知字段/Attribute各自定位；参数: 无；返回: None；异常: AssertionError。"""
        unknown = static_configuration()
        unknown['signals'][0]['unrecognized'] = 1
        unsafe = static_configuration()
        unsafe['derived']['power']['expr'] = 'voltage.real * current'
        cases = ((b'{ invalid JSON', str(self.config)),
                 (json.dumps(current_fixture(unknown)).encode(), '$.signals[0]'),
                 (json.dumps(current_fixture(unsafe)).encode(), '$.derived.power.expr'))
        for action in ('validate', 'explain'):
            for content, path in cases:
                with self.subTest(action=action, path=path):
                    self.config.write_bytes(content)
                    completed = self.invoke([action, self.config])
                    self.assertEqual(completed.returncode, 2, completed.stderr)
                    payload=json.loads(completed.stdout)
                    self.assertFalse(payload['valid'])
                    self.assertIn(path,payload['error']['source']+' '+payload['error']['path'])
                    self.assertEqual(completed.stderr,'')
                    self.assertNotIn('Traceback', completed.stderr)
                    self.assertEqual(self.config.read_bytes(), content)

    def test_actual_json_read_cancel_returns_130_and_closes_configuration_fd(self):
        """真实配置读取/解析后KI命中且配置FD已关；参数: 无；返回: None；异常: AssertionError。"""
        encoded = self.prepare()
        for action in ('validate', 'explain'):
            with self.subTest(action=action):
                audit = self.logs / ('cancel-' + action + '.json')
                completed = self.invoke([action, self.config], script=CANCEL_SCRIPT,
                                        script_arguments=(self.config, audit))
                self.assertEqual(completed.returncode, 130, completed.stderr)
                self.assertEqual(completed.stdout, '')
                self.assertTrue(completed.stderr.strip())
                self.assertNotIn('Traceback', completed.stderr)
                self.assertEqual(json.loads(audit.read_text(encoding='utf-8')),
                                 {'hit': True, 'fd_closed': True, 'config_version': 3})
                self.assertEqual(self.config.read_bytes(), encoded)
                self.assertEqual(set(self.work.iterdir()), {self.inputs, self.logs})


if __name__ == '__main__':
    unittest.main()
