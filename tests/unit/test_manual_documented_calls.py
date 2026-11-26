"""核对用户文档中可照抄的Python调用与实际公开签名一致（BUG-DEV6-001）。

先用构造的小段文字证明工具能报出把方法参数写进构造函数、拼错关键字、多余位置参数和不存在的方法，
再证明占位写法、其他模块的同名函数、命令行与YAML不会误报，最后核对仓库当前的用户文档。
不执行被核对的代码，不读取分析输入，不写文件。
"""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


def load_tool():
    """按路径加载校核工具。参数: 无。返回: 模块。异常: 工具缺失或加载失败传播。"""
    spec = importlib.util.spec_from_file_location('check_documented_calls', ROOT / 'tools/check_documented_calls.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DocumentedCallTests(unittest.TestCase):
    """每个用例都直接给出文档片段和应有的结论，不依赖当前文档内容。"""

    @classmethod
    def setUpClass(cls):
        """加载工具与公开对象。参数: 无。返回: None。异常: 加载失败传播。"""
        cls.tool = load_tool()
        cls.objects = cls.tool.public_objects()

    def problems(self, text):
        """返回一段Markdown的不符项。参数: 文本。返回: [(行号, 调用, 错误)]。异常: 无。"""
        return self.tool.check_text(text, self.objects)

    def test_reports_wrong_constructor_keyword_in_inline_code(self):
        """构造函数不接受process_count，行内代码与代码块都应报出。"""
        for text in ('写`AnalysisRunner(process_count=4)`即可。',
                     '```python\nfrom chronaxis import AnalysisRunner\nrunner = AnalysisRunner(process_count=4)\n```\n'):
            with self.subTest(text=text):
                found = self.problems(text)
                self.assertEqual([row[1] for row in found], ['AnalysisRunner'])
                self.assertIn('process_count', found[0][2])

    def test_reports_keyword_misplaced_on_run_and_missing_method(self):
        """方法只接受自己的关键字，变量上的方法与不存在的方法都能报出。"""
        misplaced = self.problems('`AnalysisRunner().run(plan, work_directory="x")`')
        self.assertEqual([row[1] for row in misplaced], ['AnalysisRunner.run'])
        self.assertIn('work_directory', misplaced[0][2])
        missing = self.problems('```python\nfrom chronaxis import AnalysisRunner\nr = AnalysisRunner()\nr.execute(plan)\n```\n')
        self.assertEqual([row[1:] for row in missing], [('AnalysisRunner.execute', '公开类没有这个方法')])
        extra = self.problems('`AnalysisRunner("reference", 4)`')
        self.assertEqual([row[1] for row in extra], ['AnalysisRunner'])

    def test_reports_line_numbers(self):
        """报告的行号指向片段所在行，便于直接修改。"""
        text = '第一行\n\n第三行`AnalysisRunner(process_count=4)`\n'
        self.assertEqual([row[0] for row in self.problems(text)], [3])

    def test_accepts_documented_usage_and_placeholders(self):
        """方法级参数、占位写法、类方法及注册参数是合法写法，不应误报。"""
        for text in ('`AnalysisRunner().run(plan, process_count=4)`', '`AnalysisRunner().validate(plan, process_count=4)`',
                     '`AnalysisRunner(...).run(plan, work_dir=None, process_count=None)`',
                     '`AnalysisRunner(backend="reference")`', '`AnalysisRunner(backend, extensions=registry)`',
                     '`AnalysisPlan.from_dict(config)`',
                     '```python\nwith AnalysisRunner().run(plan, process_count=4) as result:\n    result.write("out")\n```\n',
                     '`AnalysisRunner(backend=None, *, extensions=None)`'):
            with self.subTest(text=text):
                self.assertEqual(self.problems(text), [])

    def test_ignores_other_modules_same_name_and_non_python(self):
        """其他模块的同名函数按页面导入解析；命令行与YAML不参与核对。"""
        text = ('```python\nfrom chronaxis.fast.batch import run_batch\nrun_batch("b.yaml", "out", total=True)\n```\n'
                '`run_batch("b.yaml", "out", total=True)`\n'
                '`python -m chronaxis run plan.yaml --process-count 4`\n'
                '```yaml\nexecution:\n  process_count: 4\n```\n')
        self.assertEqual(self.problems(text), [])

    def test_current_documents_have_no_wrong_calls(self):
        """仓库当前用户文档（含中英文与AI指南）全部通过；失败时给出文件、行号和调用。"""
        paths = self.tool.documents(ROOT)
        self.assertTrue(len(paths) > 50, '没有找到用户文档')
        problems = {}
        for path in paths:
            found = self.problems(path.read_text(encoding='utf-8'))
            if found:
                problems[path.relative_to(ROOT).as_posix()] = found
        self.assertEqual(problems, {})


if __name__ == '__main__':
    unittest.main()
