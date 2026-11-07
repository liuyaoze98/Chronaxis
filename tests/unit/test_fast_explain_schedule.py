"""用公开explain和真实fast执行核对工作进程，不以两个公式相同替代运行验证。"""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from io import StringIO
import json
import multiprocessing
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from chronaxis.cli import main
from chronaxis.configuration import load_configuration
from chronaxis.fast.run import run


ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / 'Docs/Current/examples'
HEADER = 'date Mon Jan 01 00:00:00.000 2024\nbase hex timestamps absolute\ninternal events logged\n'


class FastExplainScheduleTests(unittest.TestCase):
    """每份合成文件贡献400J；比较解释上限、实际子进程和最终能量。"""

    def setUp(self):
        """创建两份连续ASC；DBC只读复用已有教学定义，产物在专用work下。"""
        temporary = TemporaryDirectory(prefix='fast-explain-', dir=ROOT / 'work')
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.raw = load_configuration(EXAMPLES / 'message-minimal.yaml').data
        self.raw['dataset'] = {'name': 'schedule'}
        self.raw['outputs'] = {'tables': 'jsonl'}
        self.raw['sources'][0]['dbc_by_channel']['1'] = str(EXAMPLES / 'data/power.dbc')
        self.inputs = []
        for index in range(2):
            path = self.folder / f'part{index}.asc'
            path.write_text(HEADER + f'{index}.000000 1 100 Rx d 2 A0 0F\n', encoding='ascii')
            self.inputs.append(str(path))

    def test_explain_matches_actual_workers_and_results(self):
        """单/双文件×1/4进程×接续/归并的8种组合均与实际执行一致。"""
        for files in (1, 2):
            for requested in (1, 4):
                for merge in ('concatenate', 'time_order'):
                    with self.subTest(files=files, requested=requested, merge=merge):
                        raw = deepcopy(self.raw)
                        raw['sources'][0].update(paths=self.inputs[:files], file_merge=merge)
                        raw['execution'] = {'process_count': requested}
                        path = self.folder / 'plan.json'
                        path.write_text(json.dumps(raw), encoding='utf8')
                        stdout, stderr = StringIO(), StringIO()
                        with redirect_stdout(stdout), redirect_stderr(stderr):
                            code = main(['fast', 'explain', str(path)])
                        self.assertEqual(code, 0, stderr.getvalue())
                        explained = json.loads(stdout.getvalue())
                        expected = 2 if files == 2 and requested == 4 else 0
                        self.assertEqual(explained['worker_process_limit'], expected)
                        before = {child.pid for child in multiprocessing.active_children()}
                        manifest = run(path, self.folder / 'output', work_dir=self.folder / 'temporary')
                        report = json.loads(manifest.read_bytes())
                        self.assertEqual(len(report['execution']['worker_pids']), expected)
                        self.assertEqual(report['execution']['ram_estimated_bytes'], 0)
                        rows = [json.loads(line) for line in
                                (manifest.parent / report['outputs'][0]['name']).read_text().splitlines()]
                        self.assertEqual(rows[0]['value'], 400.0 * files)
                        self.assertEqual({child.pid for child in multiprocessing.active_children()}, before)


if __name__ == '__main__':
    unittest.main()
