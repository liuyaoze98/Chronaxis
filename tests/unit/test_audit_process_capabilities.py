"""核对 Linux 只读能力提示与普通、fast、batch 的实际调度边界。

能力错误由限定系统调用注入；静态入口禁止读日志、启动进程或建立输出。
另用一个真实内存批量任务证明告警不改变成功状态，平台真实探测单独标明。
"""

from contextlib import ExitStack, redirect_stdout
import csv
from io import StringIO
import errno
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import call, patch
import warnings

from chronaxis import AnalysisPlan, AnalysisRunner
from chronaxis import process_capabilities as capabilities
from chronaxis.batch import BatchJob, BatchRunner
from chronaxis.cli import _parser
from chronaxis.fast.cli import execute
from test_session_process_config import config
from publication_fixtures import published_path
from workspace_fixtures import TemporaryDirectory


class ProcessCapabilityTests(unittest.TestCase):
    """系统调用只接本进程及信号0，未知结果不能被改成明确不支持。"""

    def probe(self, outcomes):
        """注入两次信号0结果。参数: 返回或OSError序列。返回: 状态、调用列表。异常: 测试断言。"""
        with patch.object(capabilities.os, 'pidfd_open', create=True, return_value=123) as opened, \
                patch.object(capabilities.os, 'getpid', return_value=456), \
                patch.object(capabilities.signal, 'pidfd_send_signal', create=True, side_effect=outcomes) as sent, \
                patch.object(capabilities.os, 'close') as closed:
            result = capabilities._pidfd_group_capability()
        opened.assert_called_once_with(456, 0)
        closed.assert_called_once_with(123)
        self.assertTrue(all(item.args[0:3] == (123, 0, None) for item in sent.call_args_list))
        return result, sent.call_args_list

    def test_supported_uses_only_zero_signal_then_group_flag(self):
        """两次只读检查成功后不产生额外告警。参数: 无。返回: None。异常: 断言失败。"""
        result, calls = self.probe([None, None])
        self.assertEqual(result, ('supported', ''))
        self.assertEqual(calls, [call(123, 0, None, 0), call(123, 0, None, 4)])

    def test_known_unavailable_is_distinct_from_permission_or_nonleader(self):
        """基线成功才将组标志EINVAL判为不可用，ESRCH/EPERM保持未知。参数: 无。返回: None。异常: 断言失败。"""
        for number, expected in ((errno.EINVAL, 'unavailable'), (errno.ENOSYS, 'unavailable'),
                                 (errno.ESRCH, 'unknown'), (errno.EPERM, 'unknown')):
            with self.subTest(errno=number):
                result, _ = self.probe([None, OSError(number, 'probe')])
                self.assertEqual(result[0], expected)
                self.assertIn(f'errno={number}', result[1])
        result, calls = self.probe([OSError(errno.EINVAL, 'baseline')])
        self.assertEqual(result[0], 'unknown')
        self.assertEqual(len(calls), 1)

    def test_missing_python_interface_does_not_open_descriptor(self):
        """缺少必要Python接口时直接提示，不做后续调用。参数: 无。返回: None。异常: 断言失败。"""
        with patch.object(capabilities.os, 'pidfd_open', None, create=True), \
                patch.object(capabilities.signal, 'pidfd_send_signal', create=True) as sent:
            self.assertEqual(capabilities._pidfd_group_capability()[0], 'unavailable')
        sent.assert_not_called()

    def test_open_and_close_failures_are_not_hidden(self):
        """打开失败保留errno，关闭失败仍传播，不能伪报能力通过。参数: 无。返回: None。异常: 断言失败。"""
        with patch.object(capabilities.os, 'pidfd_open', create=True,
                          side_effect=OSError(errno.EPERM, 'open')), \
                patch.object(capabilities.signal, 'pidfd_send_signal', create=True), \
                patch.object(capabilities.os, 'close') as closed:
            result = capabilities._pidfd_group_capability()
        self.assertEqual(result[0], 'unknown')
        closed.assert_not_called()
        failure = OSError('close failed')
        with patch.object(capabilities.os, 'pidfd_open', create=True, return_value=123), \
                patch.object(capabilities.signal, 'pidfd_send_signal', create=True), \
                patch.object(capabilities.os, 'close', side_effect=failure):
            with self.assertRaises(OSError) as caught:
                capabilities._pidfd_group_capability()
        self.assertIs(caught.exception, failure)

    def test_no_probe_for_inline_or_other_platform_and_no_cached_state(self):
        """只在需要且当前Linux时探测，每次重新读取环境。参数: 无。返回: None。异常: 断言失败。"""
        with patch.object(capabilities, '_pidfd_group_capability') as probe:
            with patch.object(capabilities.sys, 'platform', 'linux'):
                self.assertEqual(capabilities.managed_worker_warnings(False, 'inline'), ())
            with patch.object(capabilities.sys, 'platform', 'win32'):
                self.assertEqual(capabilities.managed_worker_warnings(True, 'worker'), ())
            probe.assert_not_called()
        with patch.object(capabilities.sys, 'platform', 'linux'), \
                patch.object(capabilities, '_pidfd_group_capability',
                             side_effect=[('unknown', 'errno=1'), ('supported', '')]) as probe:
            self.assertIn('尚无法确认', capabilities.managed_worker_warnings(True, 'worker')[0])
            self.assertEqual(capabilities.managed_worker_warnings(True, 'worker'), ())
            self.assertEqual(probe.call_count, 2)

    @unittest.skipUnless(sys.platform.startswith('linux'), '本机不是Linux，真实只读探测由Linux环境运行')
    def test_real_linux_probe_closes_its_descriptor(self):
        """真实探测不创建worker并关闭本次fd。参数: 无。返回: None。异常: 探测或断言错误。"""
        before = set(Path('/proc/self/fd').iterdir())
        state, _ = capabilities._pidfd_group_capability()
        self.assertIn(state, ('supported', 'unknown', 'unavailable'))
        self.assertEqual(set(Path('/proc/self/fd').iterdir()), before)


class ProcessCapabilityEntryTests(unittest.TestCase):
    """调用现有校验/说明入口，警告不改变配置有效性和命令退出码。"""

    def test_ordinary_validate_explain_follow_source_scheduling(self):
        """普通time_order单工作槽也检查，接续有效上限1不检查。参数: 无。返回: None。异常: 断言失败。"""
        for files in (1, 2):
            for count in (1, 4):
                for merge in ('concatenate', 'time_order'):
                    raw = config()
                    raw['sources'][0]['paths'] = raw['sources'][0]['paths'][:files]
                    raw['sources'][0]['file_merge'] = merge
                    raw['execution'] = {'process_count': count}
                    plan = AnalysisPlan.from_dict(raw)
                    with self.subTest(files=files, count=count, merge=merge), ExitStack() as stack:
                        stack.enter_context(patch.object(capabilities.sys, 'platform', 'linux'))
                        probe = stack.enter_context(patch.object(capabilities, '_pidfd_group_capability',
                                                                 return_value=('unavailable', 'synthetic')))
                        stack.enter_context(patch.object(Path, 'open', side_effect=AssertionError('不应读取日志')))
                        stack.enter_context(patch('multiprocessing.process.BaseProcess.start',
                                                 side_effect=AssertionError('不应启动进程')))
                        runner = AnalysisRunner()
                        validation, explanation = runner.validate(plan), runner.explain(plan)
                    expected = min(count, files) > 1 or merge == 'time_order'
                    self.assertEqual(probe.call_count, 2 if expected else 0)
                    self.assertTrue(validation.valid)
                    self.assertEqual(any('pidfd' in text for text in validation.warnings), expected)
                    self.assertEqual(explanation.validation.warnings, validation.warnings)

    def test_fast_validate_explain_keep_inline_time_order(self):
        """fast实际有效上限1始终内联，校验和说明返回0且只按需附告警。参数: 无。返回: None。异常: 断言失败。"""
        for command in ('validate', 'explain'):
            for files in (1, 2):
                for count in (1, 4):
                    for merge in ('concatenate', 'time_order'):
                        args = _parser().parse_args(['fast', command, 'unused.json'])
                        spec = dict(process_count=count, inputs=[{'path': f'missing{i}.asc'} for i in range(files)],
                                    file_merge=merge, _database=object())
                        stdout = StringIO()
                        with self.subTest(command=command, files=files, count=count, merge=merge), \
                                patch('chronaxis.fast.cli.compile_config', return_value=spec), \
                                patch('chronaxis.fast.cli._prepare'), \
                                patch.object(capabilities.sys, 'platform', 'linux'), \
                                patch.object(capabilities, '_pidfd_group_capability',
                                             return_value=('unknown', 'errno=3')) as probe, \
                                patch.object(Path, 'open', side_effect=AssertionError('不应读取日志')), \
                                patch('multiprocessing.process.BaseProcess.start', side_effect=AssertionError('不应启动进程')), \
                                redirect_stdout(stdout):
                            code = execute(args)
                        response = json.loads(stdout.getvalue())
                        expected = min(count, files) > 1
                        self.assertEqual(code, 0)
                        self.assertEqual(probe.call_count, int(expected))
                        self.assertEqual('warnings' in response, expected)

    def test_batch_count_one_warns_before_output_for_both_engines(self):
        """两种batch共用准备入口，上限1仍提示且在创建输出以前发生。参数: 无。返回: None。异常: 断言失败。"""
        job = BatchJob('job', Path('missing.json'))
        for fast_specs in (None, {'job': {}}):
            with self.subTest(fast=fast_specs is not None), warnings.catch_warnings(record=True) as recorded, \
                    patch.object(capabilities, 'managed_worker_warnings', return_value=('batch pidfd warning',)) as hints, \
                    patch('chronaxis.batch.runner._new_root', side_effect=OSError('stop before output')) as create:
                warnings.simplefilter('always')
                with self.assertRaisesRegex(OSError, 'stop before output'):
                    BatchRunner(1)._run((job,), 'unused', cancel_event=None, device_label='pending', fast_specs=fast_specs)
            hints.assert_called_once_with(True, '本独立批量任务')
            self.assertEqual(str(recorded[0].message), 'batch pidfd warning')
            create.assert_called_once()

    def test_batch_warning_does_not_change_successful_result(self):
        """真实batch输出保持成功，新增提示仅走Python告警。参数: 无。返回: None。异常: 执行或断言错误。"""
        raw = dict(config_version=4, dataset={'name': 'small', 'domain': {'start': '0s', 'end': '2s'}},
                   sources=[dict(name='values', source_type='memory', rows=[
                       dict(time='0s', values={'v': 10}), dict(time='2s', values={'v': 20})])],
                   signals=[dict(name='v', field='v', unit='V', dtype='int64', valid_for='3s')],
                   calculations=[dict(name='value', operation='sample_maximum', expr='v')],
                   outputs={'tables': 'csv'})
        plan = AnalysisPlan.from_dict(raw)
        with TemporaryDirectory(dir='work') as folder, warnings.catch_warnings(record=True) as recorded, \
                patch.object(capabilities, 'managed_worker_warnings', return_value=('batch pidfd warning',)):
            warnings.simplefilter('always')
            report = BatchRunner(1).run((BatchJob('job', plan),), Path(folder) / 'output')
            try:
                self.assertEqual(report.status, 'completed', report.to_dict())
                self.assertEqual(report.jobs[0].status, 'completed')
                with published_path(report.jobs[0].output_dir / 'calculations.csv').open(
                        encoding='utf-8', newline='') as stream:
                    rows = list(csv.DictReader(stream))
                # 2s为右端，不是参与样本；与告警无关的半开范围仍只取0s的10V。
                self.assertEqual(float(rows[0]['value']), 10.0)
                self.assertEqual(rows[0]['unit'], 'V')
            finally:
                report.close()
        self.assertEqual(str(recorded[0].message), 'batch pidfd warning')
