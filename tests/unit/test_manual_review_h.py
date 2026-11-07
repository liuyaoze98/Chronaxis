"""核对H轮修复的独立阅读依赖与示例事实；只读资料，不运行完整文档构建。"""
from pathlib import Path
import json
import re
import sys
import unittest

from chronaxis.configuration import parse_configuration

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from build_ai_guide import add_task_topics, reading_text, source_bytes


def yaml_values(text):
    """通过产品配置入口读取示例，使用用户实际运行时相同的YAML规则。"""
    if isinstance(text, bytes):
        text = text.decode('utf8')
    return parse_configuration(text, format='yaml').data


class ManualReviewHTests(unittest.TestCase):
    """检查从当前人工来源生成的专题，避免只验证旧交付包。"""

    @classmethod
    def setUpClass(cls):
        """在内存生成阅读专题；输入为主文和已存在附件，不写文件。"""
        names = ('aggregations', 'message-calculations', 'expressions', 'continuous-files',
                 'results', 'example-results', 'examples', 'calculations',
                 'fast-energy', 'configuration-language')
        sources = {f'Docs/Current/{language}{name}.md':
                   source_bytes(ROOT / f'Docs/Current/{language}{name}.md')
                   for language in ('', 'en/') for name in names}
        example_root = ROOT / 'Docs/Current/examples'
        cls.files = {'examples/' + p.relative_to(example_root).as_posix(): source_bytes(p)
                     for p in example_root.rglob('*') if p.is_file()
                     and '__pycache__' not in p.parts and p.suffix not in ('.pyc', '.pyo')}
        add_task_topics(cls.files, sources)

    def test_fast_topic_retains_complete_plan_before_replacement(self):
        """替换片段之前必须已有与下载版相同的完整配置，资源表先于拒绝说明。"""
        expected = yaml_values(self.files['examples/fast/analysis.yaml'])
        for language in ('', 'en/'):
            with self.subTest(language=language):
                text = self.files[f'{language}topics/fast-energy.md'].decode('utf8')
                blocks = re.findall(r'```yaml\n(.*?)```', text, re.S)
                self.assertGreaterEqual(len(blocks), 2)
                self.assertEqual(yaml_values(blocks[0]), expected)
                replacement = yaml_values(blocks[1])
                self.assertEqual(set(replacement), {'sources', 'execution'})
                merged = dict(expected, **replacement)
                self.assertEqual(merged['signals'], expected['signals'])
                self.assertEqual(merged['message_calculations'], expected['message_calculations'])
                self.assertEqual(len(merged['sources'][0]['paths']), 2)
                resource = text.index('`execution.memory_budget_bytes`')
                rejected = text.index('## Check a rejected request' if language else '## 配置被拒绝时')
                self.assertLess(resource, rejected)

    def test_general_ai_navigation_distinguishes_runners(self):
        """通用入口先提供连续分析任务；fast任务须写出同帧累计条件。"""
        for language in ('', 'en/'):
            tasks = json.loads((ROOT / f'Docs/AI/{language}tasks.json').read_bytes())['tasks']
            self.assertTrue({'CONTINUOUS_FILES', 'FAST_CONTINUOUS_SESSION'} <=
                            {row['id'] for row in tasks})
            for name in ('README', 'semantics'):
                with self.subTest(language=language, page=name):
                    text = reading_text((ROOT / f'Docs/AI/{language}{name}.md').read_text(encoding='utf8'))
                    self.assertLess(text.index('`CONTINUOUS_FILES`'), text.index('`FAST_CONTINUOUS_SESSION`'))
                    self.assertIn('only when every signal input' if language else '只有公式的全部信号输入', text)
                    self.assertNotIn('For volumes of one recording, use `FAST_CONTINUOUS_SESSION`', text)

    def test_execution_example_source_and_parallel_limit(self):
        """两份30J配置保持相同ASC/DBC和上限4，不能把它们描述成内存输入。"""
        base = ROOT / 'Docs/Current/examples'
        plans = [yaml_values((base / name).read_text(encoding='utf8'))
                 for name in ('calculation-minimal.yaml', 'execution-diagnostics.yaml')]
        self.assertEqual(plans[0]['sources'], plans[1]['sources'])
        for plan in plans:
            self.assertEqual(plan['execution']['process_count'], 4)
            self.assertEqual(plan['sources'][0]['paths'], 'data/can/calculation-minimal.asc')
            self.assertTrue((base / plan['sources'][0]['paths']).is_file())
            self.assertTrue((base / plan['sources'][0]['dbc_by_channel']['1']).is_file())
        self.assertTrue(plans[1]['diagnostics']['trace'])

    def test_batch_pattern_matches_documented_single_job(self):
        """按正文规定的examples目录枚举模式，防止把相邻示例的任务数复制过来。"""
        base = ROOT / 'Docs/Current/examples'
        for language in ('', 'en/'):
            text = (ROOT / f'Docs/Current/{language}batch.md').read_text(encoding='utf8')
            plans = [yaml_values(block) for block in re.findall(r'```yaml\n(.*?)```', text, re.S)]
            template, = [plan for plan in plans if 'template' in plan]
            self.assertEqual(template['process_count'], 4)
            matches = [p.relative_to(base).as_posix() for p in base.glob(template['inputs'])]
            self.assertEqual(matches, ['data/can/quickstart.asc'])


if __name__ == '__main__':
    unittest.main()
