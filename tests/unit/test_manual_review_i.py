"""通过实际Markdown解析和公开API调用，验证AI卡片保留完整代码与成员结构。"""
import ast
from contextlib import redirect_stdout
from html.parser import HTMLParser
from io import StringIO
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from build_ai_guide import public_card, reading_text


class ParsedCard(HTMLParser):
    """记录真正渲染的代码块、标题和锚点；代码内的标签文字不算HTML节点。"""

    def __init__(self, html):
        """解析已生成HTML；保存可检查结构，不执行其中任何脚本。"""
        super().__init__(convert_charrefs=True)
        self.codes, self.headings, self.anchors = [], [], []
        self._code, self._heading, self._pre = None, None, False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        """识别代码块、标题及位于代码外的显式API锚点。"""
        attrs = dict(attrs)
        if tag == "pre":
            self._pre = True
        elif tag == "code" and self._pre:
            self._code = [attrs.get("class", ""), ""]
        if re.fullmatch(r"h[1-6]", tag):
            self._heading = [int(tag[1]), ""]
        if not self._pre and attrs.get("id", "").startswith("api-"):
            self.anchors.append(attrs["id"])

    def handle_data(self, data):
        """收集显示文字；Python注释只有在错误地变成标题时才进入标题集合。"""
        if self._code is not None:
            self._code[1] += data
        if self._heading is not None:
            self._heading[1] += data

    def handle_endtag(self, tag):
        """在节点结束时保存完整文本，避免仅以围栏数量判断结构。"""
        if tag == "code" and self._code is not None:
            self.codes.append(tuple(self._code))
            self._code = None
        if tag == "pre":
            self._pre = False
        if re.fullmatch(r"h[1-6]", tag) and self._heading is not None:
            self.headings.append(tuple(self._heading))
            self._heading = None


def render_cards(texts):
    """使用手册构建采用的marked渲染器；缺依赖或解析失败即报错，不跳过验收。"""
    node = shutil.which("node")
    parser = ROOT / "Docs/Current/_build/tooling/node_modules/marked/lib/marked.esm.js"
    if node is None or not parser.is_file():
        raise RuntimeError("需要手册构建环境中的Node和marked，不能用正则代替结构验收")
    script = """
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
const { marked } = await import(pathToFileURL(process.argv[1]).href);
const cards = JSON.parse(readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(cards.map(card => marked.parse(card))));
"""
    result = subprocess.run(
        [node, "--input-type=module", "-e", script, str(parser)],
        input=json.dumps(texts, ensure_ascii=False), text=True, encoding="utf8",
        capture_output=True, check=True,
    )
    return [ParsedCard(html) for html in json.loads(result.stdout)]


class ManualReviewITests(unittest.TestCase):
    """从当前公开资料生成卡片，检查中英文全部成员并运行三份出问题的示例。"""

    @classmethod
    def setUpClass(cls):
        """一次渲染全部源正文与派生卡片，仅在内存操作，不重建手册。"""
        cls.paths = sorted((ROOT / "Docs/Current/public-api").glob("*.md"))
        cls.paths += sorted((ROOT / "Docs/Current/en/public-api").glob("*.md"))
        texts = []
        for path in cls.paths:
            page = path.read_text(encoding="utf8")
            body = reading_text(page)
            body = body[body.index('<a id="api-'):]
            # 源码位置章节不属于安装用户资料；成员说明和所有示例都必须保留。
            body = re.sub(r"(?ms)^## Source locations\s*\n.*?(?=^## |\Z)", "", body)
            texts.extend((body, public_card(page)))
        parsed = render_cards(texts)
        cls.cards = {path.relative_to(ROOT / "Docs/Current").as_posix():
                     (parsed[2 * index], parsed[2 * index + 1])
                     for index, path in enumerate(cls.paths)}

    def example_code(self, name, imported):
        """取包含真实导入的Python块；丢失导入或围栏时直接失败。"""
        card = self.cards[f"public-api/{name}.md"][1]
        matches = [code for language, code in card.codes
                   if language == "language-python"
                   and f"from chronaxis import {imported}" in code]
        self.assertEqual(len(matches), 1, name)
        ast.parse(matches[0])
        return matches[0]

    def test_all_public_cards_preserve_parsed_structure(self):
        """实际解析全部中英卡片；标题、代码、代码外API锚点与公开来源一致。"""
        chinese = {path.name for path in self.paths if path.parent.parent.name == "Current"}
        english = {path.name for path in self.paths if path.parent.parent.name == "en"}
        self.assertTrue(chinese)
        self.assertEqual(chinese, english)
        for name, (source, card) in self.cards.items():
            with self.subTest(card=name):
                self.assertEqual(card.anchors, source.anchors)
                self.assertEqual(card.headings, source.headings)
                expected = [(language, code.replace("Docs/Current/examples/", "examples/")
                             .replace("从仓库根目录运行", "从AI指南根目录运行（该目录包含examples子目录）")
                             .replace("Run from the repository root", "Run from the AI guide root (the directory containing examples)"))
                            for language, code in source.codes]
                self.assertEqual(card.codes, expected)
        print(f"Markdown结构已核对：{len(chinese)}份中文 + {len(english)}份英文公开卡片")

    def test_python_comments_do_not_consume_following_member(self):
        """#注释留在完整Python代码块，后续extensions仍是实际标题和HTML锚点。"""
        card = self.cards["public-api/AnalysisPlan.md"][1]
        self.assertIn("api-AnalysisPlan-extensions", card.anchors)
        self.assertIn((3, "AnalysisPlan.extensions"), card.headings)
        self.assertFalse(any("demo_preset" in text or "从AI指南根目录运行" in text
                             for _, text in card.headings))
        code = self.example_code("AnalysisPlan", "load_analysis_plan")
        self.assertIn("# demo_preset mode mode explicit", code)
        self.assertNotIn('id="api-AnalysisPlan-extensions"', code)

    def test_analysis_plan_example_runs(self):
        """按资料根目录执行完整加载示例，核对真实预设绑定及已导入的公开入口。"""
        code = self.example_code("AnalysisPlan", "load_analysis_plan")
        self.assertIn("从AI指南根目录运行（该目录包含examples子目录）", code)
        english, = [value for language, value in self.cards["en/public-api/AnalysisPlan.md"][1].codes
                    if language == "language-python" and "from chronaxis import load_analysis_plan" in value]
        self.assertIn("Run from the AI guide root (the directory containing examples)", english)
        self.assertIn('load_analysis_plan("examples/preset-charge-minimal.yaml")', english)
        output, namespace, previous = StringIO(), {}, Path.cwd()
        try:
            os.chdir(ROOT / "Docs/Current")
            with redirect_stdout(output):
                exec(compile(code, "AI/AnalysisPlan.md", "exec"), namespace)
        finally:
            os.chdir(previous)
        self.assertEqual(output.getvalue().splitlines(),
                         ["demo_preset mode mode explicit", "demo_preset current current explicit"])
        self.assertEqual(len(namespace["plan"].presets), 1)

    def test_preset_spec_example_runs(self):
        """完整构造示例可直接执行，并形成与文字一致的阈值预设声明。"""
        namespace, output = {}, StringIO()
        with redirect_stdout(output):
            exec(compile(self.example_code("PresetSpec", "PresetSpec"),
                         "AI/PresetSpec.md", "exec"), namespace)
        self.assertEqual(namespace["spec"].id, "heat_alarm")
        self.assertEqual(namespace["spec"].preset_type, "threshold_excursion")
        self.assertEqual(output.getvalue().strip(), "heat_alarm threshold_excursion")

    def test_batch_plan_example_runs_with_documented_prerequisite(self):
        """准备说明所要求的批量文件，再执行原示例；jobs只保存子计划路径。"""
        code = self.example_code("load_batch_plan", "load_batch_plan")
        previous = Path.cwd()
        with tempfile.TemporaryDirectory(prefix="manual-review-i-") as directory:
            base = Path(directory)
            child = ROOT / "Docs/Current/examples/calculation-minimal.yaml"
            (base / "batch.yaml").write_text(json.dumps({
                "batch_version": 1, "process_count": 4,
                "jobs": [{"name": "demo", "plan": str(child)}],
            }), encoding="utf8")
            namespace = {}
            try:
                os.chdir(base)
                exec(compile(code, "AI/load_batch_plan.md", "exec"), namespace)
            finally:
                os.chdir(previous)
            self.assertEqual(namespace["plan"].process_count, 4)
            self.assertEqual(namespace["plan"].jobs[0].plan, child)


if __name__ == "__main__":
    unittest.main()
