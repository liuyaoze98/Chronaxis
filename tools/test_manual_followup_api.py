"""核对DOC-REVIEW-11共享实例例的来源、派生路径和完整代码提取。

只读取教学配置与DBC，不运行分析。临时指南仅含该例的三份输入，
成品HTML和独立ZIP另由check_manual_followup_api逐份提取原代码验收。
"""
from contextlib import redirect_stdout
from html import escape
from io import StringIO
import json
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import build_m2_docs
from build_ai_guide import public_card
from check_manual_followup_api import registry_fragment
from chronaxis.planning.checks import PlanValidationError
from doc_public_api import public_page

ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT/'Docs/Current'


def sources():
    """返回真实中英文资料源，不手写近似示例。参数: 无。异常: 来源缺失或JSON错误。"""
    annotations = json.loads((CURRENT/'annotations.json').read_text(encoding='utf-8'))
    code = annotations['chronaxis.runner.AnalysisRunner.validate']['example']
    chinese = '<a id="api-AnalysisRunner-validate"></a>\n```python\n'+code+'\n```\n'
    english = (CURRENT/'en/public-api/AnalysisRunner.md').read_text(encoding='utf-8')
    return chinese, english


def execute(code, cwd):
    """从声明工作目录运行提取的原片段。返回: stdout。异常: 保留示例真实错误。"""
    original = Path.cwd()
    output = StringIO()
    try:
        os.chdir(cwd)
        with redirect_stdout(output):
            exec(compile(code, '<actual-documentation-fragment>', 'exec'), {})
    finally:
        os.chdir(original)
    return output.getvalue()


class ManualFollowupAPI(unittest.TestCase):
    """验证完整片段与实际输入；不只检查替代代码中含某个路径字符串。"""

    def test_both_source_examples_run_from_manual_root(self):
        """参数: 无。返回: None。异常: 实际源码片段加载、验证或解释失败。"""
        for source in sources():
            self.assertEqual(execute(registry_fragment(source), CURRENT),
                             'True True\nExplainReport\n')

    def test_chinese_example_reaches_generated_public_runner_page(self):
        """参数: 无。返回: None。异常: 资料源示例未进入真实公开页生成链时失败。"""
        annotations = json.loads((CURRENT/'annotations.json').read_text(encoding='utf-8'))
        source = (ROOT/'src/chronaxis/runner.py').read_text(encoding='utf-8')
        catalog = json.loads((CURRENT/'public-api.json').read_text(encoding='utf-8'))
        item = next(row for row in catalog['objects'] if row['name'] == 'AnalysisRunner')
        language = json.loads((CURRENT/'reference-language.json').read_text(encoding='utf-8'))
        signatures = {row['module']+'.'+row['qualified']: row['signature']
                      for row in catalog['objects'] if row.get('signature')}
        with patch.multiple(build_m2_docs, EDITION='Current', LANGUAGE=language,
                            PUBLIC_SIGNATURES=signatures):
            module, record, _ = build_m2_docs.render_module('src/chronaxis/runner.py', source, annotations)
            page = public_page(item, record, module, {}, build_m2_docs.anchor)
        expected = annotations['chronaxis.runner.AnalysisRunner.validate']['example']
        self.assertEqual(registry_fragment(page).strip(), expected.strip())
        self.assertEqual(execute(registry_fragment(page), CURRENT), 'True True\nExplainReport\n')

    def test_both_cards_run_from_their_readme_directories(self):
        """参数: 无。返回: None。异常: 语言目录或任一配套输入缺失时失败。"""
        with TemporaryDirectory(prefix='chronaxis-registry-cards-') as temporary:
            guide = Path(temporary)
            (guide/'en').mkdir()
            for name in ('calculation-minimal.yaml', 'data/can/calculation-minimal.asc',
                         'data/can/teaching.dbc'):
                target = guide/'examples'/name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(CURRENT/'examples'/name, target)
            for language, source in zip(('', 'en/'), sources()):
                card = public_card(source, language=language, api_names=['AnalysisRunner'])
                code = registry_fragment(card)
                self.assertEqual(execute(code, guide/language), 'True True\nExplainReport\n')
                self.assertIn('../examples/' if language else '"examples/', code)
                broken = code.replace('calculation-minimal.yaml', 'missing-registry-example.yaml')
                with self.assertRaises(PlanValidationError):
                    execute(broken, guide/language)

    def test_html_extracts_highlighted_code_without_rewriting_it(self):
        """参数: 无。返回: None。异常: 高亮标签或实体改变片段时失败。"""
        code = registry_fragment(sources()[0])
        highlighted = escape(code).replace('registry =', '<span class="hljs-name">registry</span> =')
        page = '<pre><code class="hljs language-python">'+highlighted+'</code></pre>'
        self.assertEqual(registry_fragment(page, html=True), code)
        with self.assertRaisesRegex(ValueError, '实际2个'):
            registry_fragment(page+page, html=True)
        with self.assertRaisesRegex(ValueError, '实际0个'):
            registry_fragment('```python\nprint("unrelated")\n```')

    def test_plan_fragment_keeps_html_references_but_drops_card_promise(self):
        """参数: 无。返回: None。异常: 删除HTML链接或保留卡片空承诺时失败。"""
        source = (CURRENT/'en/public-api/PlanFragment.md').read_text(encoding='utf-8')
        self.assertIn('The linked lower-level types', source)
        rows = '\n'.join(line for line in source.splitlines() if line.startswith('|'))
        self.assertEqual(rows.count('](../../reference/'), 5)
        card = public_card(source, language='en/', api_names=['PlanFragment'])
        self.assertNotIn('The linked lower-level types', card)
        self.assertNotIn('](../../reference/', card)
        for name in ('DerivedDefinition', 'PresetRule', 'WindowSpec', 'PresetCalculation', 'SequencePlan'):
            self.assertIn('tuple['+name+', ...]', card)


if __name__ == '__main__':
    unittest.main()
