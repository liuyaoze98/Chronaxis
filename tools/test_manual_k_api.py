"""验证第K轮离线API路径及可省略进程上限。

输入为API说明来源、双语示例和教学配置。离线探测仅复制两个配置及其依赖，
使用公开加载/检查入口；不读取分析记录、不生成业务结果。临时目录自动清理。
"""

from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
import json
import argparse
import html
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from ruamel.yaml import YAML
from chronaxis import AnalysisPlan, explain_analysis_plan, validate_analysis_plan

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / 'Docs/Current/examples'
API_NAMES = ('load_analysis_plan', 'validate_analysis_plan', 'explain_analysis_plan', 'AnalysisPlan')


class ManualKAPI(unittest.TestCase):
    """独立目录复制运行API例，并检查省略/显填进程上限的实际计划行为。"""

    def test_eight_offline_examples_without_repository_layout(self):
        """参数: 无。返回: 无。异常: 八个来源示例依赖仓库目录或执行失败时断言失败。"""
        annotations = json.loads((ROOT / 'Docs/Current/annotations.json').read_text(encoding='utf8'))
        snippets = {}
        for name in API_NAMES:
            record = next(value for key, value in annotations.items() if key.endswith('.' + name))
            snippets['zh/' + name] = record['example']
            text = (ROOT / 'Docs/Current/en/public-api' / (name + '.md')).read_text(encoding='utf8')
            snippets['en/' + name] = next(block for block in re.findall(r'```python\n(.*?)```', text, re.S)
                                          if 'load_analysis_plan("examples/' in block)
        # 仅提供离线根的examples树，故意不创建Docs/Current替代目录。
        with tempfile.TemporaryDirectory(prefix='manual-k-api-') as folder:
            base = Path(folder)
            for relative in ('analysis.yaml', 'preset-charge-minimal.yaml',
                             'data/can/teaching.dbc', 'data/can/quickstart.asc',
                             'data/can/preset-charge-minimal.asc'):
                target = base / 'examples' / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(EXAMPLES / relative, target)
            previous = Path.cwd()
            try:
                os.chdir(base)
                for name, code in snippets.items():
                    with self.subTest(name=name), redirect_stdout(StringIO()):
                        self.assertNotIn('Docs/Current/examples/', code)
                        namespace = {}
                        exec(compile(code, name, 'exec'), namespace)
                        self.assertIsInstance(namespace['plan'], AnalysisPlan)
                        if 'report' in namespace:
                            self.assertTrue(namespace['report'].valid)
            finally:
                os.chdir(previous)

    def test_default_one_and_explicit_limits(self):
        """参数: 无。返回: 无。异常: CSV/内存/多来源省略或1无效、2有效时断言失败。"""
        for name in ('input-csv-minimal.yaml', 'input-memory-minimal.yaml', 'can-joint-analysis.yaml'):
            original = YAML(typ='safe').load((EXAMPLES / name).read_text(encoding='utf8'))
            for count in (None, 1, 2):
                with self.subTest(example=name, process_count=count):
                    raw = deepcopy(original)
                    raw.pop('execution', None)
                    if count is not None:
                        raw['execution'] = {'process_count': count}
                    plan = AnalysisPlan.from_dict(raw, base_dir=EXAMPLES)
                    self.assertEqual(plan.execution.process_count, count or 1)
                    self.assertEqual(validate_analysis_plan(plan).valid, count != 2)

    def test_time_order_remains_distinct_from_default_concatenation(self):
        """参数: 无。返回: 无。异常: 单CAN时间归并或多来源限制发生改变时断言失败。"""
        raw = YAML(typ='safe').load((EXAMPLES / 'analysis.yaml').read_text(encoding='utf8'))
        raw.pop('execution', None)
        raw['sources'][0]['file_merge'] = 'time_order'
        plan = AnalysisPlan.from_dict(raw, base_dir=EXAMPLES)
        self.assertTrue(validate_analysis_plan(plan).valid)
        self.assertEqual(explain_analysis_plan(plan).source_execution[0]['read_process_limit'], 1)
        other = deepcopy(raw['sources'][0])
        raw['sources'][0]['name'] = 'first'
        other['name'] = 'second'
        raw['sources'].append(other)
        for signal in raw['signals']:
            signal['source'] = 'first'
        plan = AnalysisPlan.from_dict(raw, base_dir=EXAMPLES)
        self.assertFalse(validate_analysis_plan(plan).valid)


def check_html(manual, python, output):
    """用指定安装解释器运行最终HTML原代码。

    参数: manual为解压根，python为已安装解释器，output为新JSON证据路径。
    返回: 八项检查记录。异常: 路径、片段选择、子进程或报告写入失败传播。
    子进程清除PYTHONPATH；以手册根为工作目录，不修改示例代码或调用仓库源码。
    """
    manual = manual.resolve()
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1')
    environment.pop('PYTHONPATH', None)
    records = []
    for language in ('', 'en/'):
        for name in API_NAMES:
            page = manual / language / 'public-api' / (name + '.html')
            text = page.read_text(encoding='utf8')
            blocks = [html.unescape(re.sub(r'<[^>]+>', '', block))
                      for block in re.findall(r'<pre[^>]*>(.*?)</pre>', text, re.S)]
            candidates = [block for block in blocks if 'plan = load_analysis_plan(' in block
                          and ('analysis.yaml' in block or 'preset-charge-minimal.yaml' in block)]
            if len(candidates) != 1:
                raise AssertionError('最终HTML示例必须唯一：' + str(page))
            code = candidates[0]
            if 'Docs/Current/examples/' in code:
                raise AssertionError('离线示例仍依赖仓库路径：' + str(page))
            completed = subprocess.run([str(python), '-X', 'utf8', '-B', '-c', code],
                                       cwd=manual, env=environment, capture_output=True,
                                       encoding='utf8', timeout=60)
            records.append(dict(page=str(page), code=code, returncode=completed.returncode,
                                stdout=completed.stdout, stderr=completed.stderr))
            if completed.returncode:
                raise AssertionError('最终HTML代码失败：' + str(page) + '\n' + completed.stderr)
    # 报告来源取调用方传入的实测设备标签；未传时记pending，不再固定写home。
    label = os.environ.get('CHRONAXIS_DEVICE_LABEL', 'pending')
    with output.open('x', encoding='utf8') as stream:
        json.dump(dict(device_label=label, python=str(python), status='passed', checks=records),
                  stream, ensure_ascii=False, indent=2)
    return records


if __name__ == '__main__':
    import sys
    if '--manual' in sys.argv:
        parser = argparse.ArgumentParser()
        parser.add_argument('--manual', type=Path, required=True)
        parser.add_argument('--python', type=Path, required=True)
        parser.add_argument('--output', type=Path, required=True)
        args = parser.parse_args()
        print('最终HTML示例通过：', len(check_html(args.manual, args.python, args.output)))
    else:
        unittest.main()
