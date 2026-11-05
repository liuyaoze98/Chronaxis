"""从CLI核对配置诊断与重复输出的完整用户操作。

使用三条合成功率记录，0—2秒的能量应为800J。先同时写入三个配置错误，
确认一次报告且不启动计算；修正后连续输出到同一目录，按返回清单读取结果。
所有文件属于TemporaryDirectory，不接触真实日志、DBC或历史项目。
"""

from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from chronaxis.cli import main


def _configuration():
    """返回两秒400W的最小计划。参数: 无。返回: 新dict。异常: 无。"""
    return {
        'config_version': 4,
        'dataset': {'name': 'repeat_energy', 'domain': {'start': '0s', 'end': '2s'}},
        'sources': [{'name': 'samples', 'source_type': 'memory', 'time': {'unit': 's'},
                     'rows': [{'time': time, 'values': {'power': value}}
                              for time, value in [('0s', 400), ('1s', 400), ('2s', 0)]]}],
        'signals': [{'name': 'power', 'field': 'power', 'dtype': 'float64',
                     'unit': 'W', 'valid_for': '3s'}],
        'calculations': [{'name': 'energy', 'operation': 'integral', 'expr': 'power',
                          'scope': 'session', 'unit': 'J'}],
    }


def _invoke(arguments):
    """捕获一次CLI。参数: 参数列表。返回: 退出码/输出/错误文本。异常: CLI未分类错误。"""
    output, errors = StringIO(), StringIO()
    with redirect_stdout(output), redirect_stderr(errors):
        status = main(arguments)
    return status, output.getvalue(), errors.getvalue()


class NextUXIntegrationTests(unittest.TestCase):
    """验证修正多错配置后可以重复执行，旧结果和用户文件均保持。"""

    def test_diagnose_then_repeat_in_one_directory(self):
        """走通诊断到两次输出。参数: 无。返回: None。异常: 断言或实际CLI错误。"""
        with tempfile.TemporaryDirectory(prefix='chronaxis-next-ux-') as temporary:
            root = Path(temporary)
            config = _configuration()
            config['execution'] = {'backend': 'gpu', 'batch_rows': 0}
            config['outputs'] = {'tables': 'xlsx'}
            plan = root / 'analysis.json'
            plan.write_text(json.dumps(config), encoding='utf-8')
            # 验证不调用分析，且三个互不依赖的错误在同次返回。
            with patch('chronaxis.analysis_cli.AnalysisRunner.run') as run:
                status, output, errors = _invoke(['validate', str(plan), '--format', 'json'])
                self.assertEqual(status, 2, errors)
                run.assert_not_called()
            report = json.loads(output)
            self.assertNotIn('error', report)
            paths = {item['path'] for item in report['errors']}
            self.assertTrue({'$.execution.backend', '$.execution.batch_rows',
                             '$.outputs.tables'}.issubset(paths), report)
            # 修复配置，输出根预先存在并含用户文件。
            plan.write_text(json.dumps(_configuration()), encoding='utf-8')
            destination = root / 'results'
            destination.mkdir()
            marker = destination / 'user.txt'
            marker.write_bytes(b'keep this file')
            snapshots = {}
            manifests = []
            for iteration in range(2):
                status, output, errors = _invoke([
                    'run', str(plan), '--output', str(destination),
                    '--backend', 'reference', '--work-dir', str(root / f'work-{iteration}')])
                self.assertEqual(status, 0, errors)
                published = json.loads(output)
                manifest = Path(published['manifest'])
                self.assertTrue(manifest.is_file())
                self.assertEqual(manifest.parent, destination)
                self.assertTrue(manifest.name.startswith('run_manifest_'))
                self.assertNotIn(manifest, manifests)
                manifests.append(manifest)
                tables = [destination / name for name in published['result_files']
                          if name.startswith('会话结果_') and name.endswith('.csv')]
                self.assertEqual(len(tables), 1, published)
                with tables[0].open(encoding='utf-8-sig', newline='') as handle:
                    rows = list(csv.DictReader(handle))
                self.assertEqual(len(rows), 1)
                self.assertEqual(float(rows[0]['energy（J）']), 800.0)
                self.assertEqual(rows[0]['energy：状态'], '完整')
                # 第二次完成后，第一次全部正式文件必须逐字保持。
                for path, content in snapshots.items():
                    self.assertEqual(path.read_bytes(), content)
                snapshots = {path: path.read_bytes() for path in destination.iterdir() if path.is_file()}
            self.assertEqual(marker.read_bytes(), b'keep this file')
