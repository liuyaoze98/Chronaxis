"""核验最终英文AI卡片的工作目录、配置路径及可执行代码，不计算业务结果。"""
import ast
from contextlib import chdir, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from build_ai_guide import build_files
from test_manual_review_i import render_cards


class EnglishCardPathTests(unittest.TestCase):
    """使用完整生成链及真实解析器，避免只测前一阶段的public_card中间结果。"""

    @classmethod
    def setUpClass(cls):
        """生成一次资料并在专用目录布置真实输入；不修改手册或安装环境。"""
        cls.files = build_files(verify_runtime=False)
        cls.temporary = TemporaryDirectory(prefix='english-card-', dir=ROOT / 'work')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.guide = Path(cls.temporary.name)
        for name, data in cls.files.items():
            target = cls.guide / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        cls.names = ('load_analysis_plan', 'validate_analysis_plan', 'explain_analysis_plan')
        cls.parsed = dict(zip(cls.names, render_cards([
            cls.files[f'en/api/{name}.md'].decode('utf8') for name in cls.names])))

    def example(self, name):
        """取带真实导入的完整Python示例；签名代码块不能充当示例。"""
        snippets = [code for language, code in self.parsed[name].codes
                    if language == 'language-python' and 'from chronaxis import ' in code]
        self.assertEqual(len(snippets), 1, name)
        ast.parse(snippets[0])
        return snippets[0]

    def test_three_paths_follow_english_readme_directory(self):
        """三卡没有目录例外，路径必须从en读取到同一份随包配置。"""
        self.assertIn('Relative commands use the directory containing this README',
                      self.files['en/README.md'].decode('utf8'))
        for name in self.names:
            with self.subTest(card=name):
                calls = [node for node in ast.walk(ast.parse(self.example(name)))
                         if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                         and node.func.id == 'load_analysis_plan']
                self.assertEqual(len(calls), 1)
                relative = ast.literal_eval(calls[0].args[0])
                self.assertEqual(relative, '../examples/analysis.yaml')
                self.assertEqual((self.guide / 'en' / relative).read_bytes(),
                                 self.files['examples/analysis.yaml'])

    def test_real_apis_run_from_english_directory(self):
        """逐页执行加载、校验和解释代码；不运行AnalysisRunner或生成分析结果。"""
        with chdir(self.guide / 'en'):
            for name in self.names:
                with self.subTest(card=name):
                    scope = {}
                    with redirect_stdout(StringIO()):
                        exec(compile(self.example(name), name, 'exec'), scope)
                    self.assertEqual(scope['plan'].config_version, 4)
                    if name == 'validate_analysis_plan':
                        self.assertTrue(scope['report'].valid)
                        self.assertTrue(scope['report'].execution_ready)

    def test_explicit_root_example_remains_valid(self):
        """AnalysisPlan已经声明根目录，不应被再次改成相对en的路径。"""
        text = self.files['en/api/AnalysisPlan.md'].decode('utf8')
        self.assertIn('Run from the AI guide root (the directory containing examples)', text)
        self.assertIn('load_analysis_plan("examples/preset-charge-minimal.yaml")', text)
        self.assertEqual((self.guide / 'examples/preset-charge-minimal.yaml').read_bytes(),
                         self.files['examples/preset-charge-minimal.yaml'])
        for name in self.names:
            self.assertNotIn('../examples/analysis.yaml', self.files[f'api/{name}.md'].decode('utf8'))
