"""验证英文阅读层不改配置约束，且源码/离线查询保留同一字段和示例。

只读公开资料；临时ZIP写系统临时目录。完整业务运行由发行安装验证承担。
"""
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
from runpy import run_path
import tempfile
import unittest
from unittest.mock import patch
import shutil
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
HELPER = run_path(str(ROOT / "tools/english_docs.py"))


def machine_values(value):
    """去掉阅读说明以比较规范。参数: JSON值。返回: 结构副本。异常: 无。"""
    if isinstance(value, dict):
        return {k: machine_values(v) for k, v in value.items()
                if not (k in ("title", "description") and isinstance(v, str))}
    if isinstance(value, list):
        return [machine_values(v) for v in value]
    return value


class SchemaTranslationTests(unittest.TestCase):
    """四份规范保持类型、默认、枚举、分支及边界；新增说明必须提供译文。"""

    def test_all_schema_machine_values_and_source_are_unchanged(self):
        """逐个原节点比较非说明内容，并确认函数没有原地改写。"""
        translations = HELPER["description_map"]()
        for name in HELPER["SCHEMAS"]:
            source = json.loads((ROOT / "Docs/Schema" / name).read_bytes())
            before = deepcopy(source)
            translated = HELPER["translate_schema"](source, translations)
            self.assertEqual(source, before)
            self.assertEqual(machine_values(source), machine_values(translated))
            self.assertNotEqual(source, translated)

    def test_new_description_requires_translation(self):
        """新说明不得静默留中文，也不能误翻译配置枚举或默认值。"""
        sample = {"description": "新增说明", "enum": ["接收"], "default": "接收"}
        with self.assertRaisesRegex(ValueError, "Missing English"):
            HELPER["translate_schema"](sample, {})
        output = HELPER["translate_schema"](sample, {"新增说明": "New description"})
        self.assertEqual(output, {"description": "New description", "enum": ["接收"], "default": "接收"})

    def test_standalone_cards_keep_members_without_repository_links(self):
        """实际英文卡片保留全部成员，不把未打包源码路径带给安装用户。"""
        import re
        card = run_path(str(ROOT / "tools/build_ai_guide.py"))["public_card"]
        for path in (ROOT / "Docs/Current/en/public-api").glob("*.md"):
            source = path.read_text(encoding="utf8")
            chinese = (ROOT / "Docs/Current/public-api" / path.name).read_text(encoding="utf8")
            members = re.findall(r'<a id="(api-[^"]+)"', source)
            self.assertCountEqual(members, re.findall(r'<a id="(api-[^"]+)"', chinese), path.name)
            output = card(source)
            self.assertEqual(members, re.findall(r'<a id="(api-[^"]+)"', output), path.name)
            self.assertNotIn("src/chronaxis/", output, path.name)

    def test_changed_source_or_translation_requires_review(self):
        """在临时副本真正改动正文；旧审阅清单必须拒绝两种漂移。"""
        current, ai = ROOT / "Docs/Current", ROOT / "Docs/AI"
        manuals = {*current.glob("*.md"), *(current / "public-api").glob("*.md")}
        expected = {(page, current / "en" / page.relative_to(current)) for page in manuals}
        expected.update((ai / name, ai / "en" / name)
                        for name in ("README.md", "workflow.md", "semantics.md", "tasks.json"))
        for name in ("calculations.md", "public-api/AnalysisPlan.md", "temporal-transforms.md", "host-extensions.md"):
            self.assertIn((current / name, current / "en" / name), expected)
        self.assertCountEqual(HELPER["translation_pairs"](), expected)
        with tempfile.TemporaryDirectory(prefix="chronaxis-en-review-") as directory:
            target = Path(directory)
            paths = {p for pair in expected for p in pair}
            paths.update(ROOT / "Docs/Schema" / name for name in HELPER["SCHEMAS"])
            paths.update(ROOT / name for name in ("Docs/Current/navigation.json",
                "Docs/Current/en/navigation.json", "Docs/Current/en/schema-translations.json",
                "Docs/Current/en/translation-status.json"))
            for source in paths:
                dest = target / source.relative_to(ROOT)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, dest)
            namespace = HELPER["check_reviewed"].__globals__
            with patch.dict(namespace, ROOT=target, CURRENT=target / "Docs/Current", ENGLISH=target / "Docs/Current/en"):
                self.assertEqual(HELPER["check_reviewed"](), len(expected))
                for relative in ("Docs/Current/calculations.md", "Docs/Current/en/calculations.md"):
                    path = target / relative
                    original = path.read_bytes()
                    path.write_bytes(b"Changed explanation.\n\n" + original)
                    with self.assertRaisesRegex(ValueError, "sources changed"):
                        HELPER["check_reviewed"]()
                    path.write_bytes(original)
                self.assertEqual(HELPER["check_reviewed"](), len(expected))


class EnglishGuideTests(unittest.TestCase):
    """英文任务、接口及字段同时支持源码布局和独立指南布局。"""

    @classmethod
    def setUpClass(cls):
        """构造独立测试资料；正式包另在无Git干净树校验运行源码。"""
        cls.temp = tempfile.TemporaryDirectory(prefix="chronaxis-en-guide-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.bundle = Path(cls.temp.name)
        data = run_path(str(ROOT / "tools/build_ai_guide.py"))["build"](verify_runtime=False)
        with ZipFile(BytesIO(data)) as archive:
            archive.extractall(cls.bundle)
        cls.source_query = staticmethod(run_path(str(ROOT / "Docs/AI/lookup.py"))["query"])
        cls.bundle_query = staticmethod(run_path(str(cls.bundle / "lookup.py"))["query"])

    def test_source_and_bundle_paths_and_constraints(self):
        """英文查询结果路径可打开，除自然语言外与中文相同。"""
        for query, folder in ((self.source_query, ROOT / "Docs/AI"), (self.bundle_query, self.bundle)):
            en = folder / "en"
            tasks = query("task", "CONDITION_ENERGY", language="en")
            self.assertEqual(len(tasks), 1)
            self.assertTrue((en / tasks[0]["example"]).is_file())
            for row in query("api", "AnalysisRunner", language="en"):
                filename, _, anchor = row["file"].partition("#")
                body = (en / filename).read_text(encoding="utf8")
                if anchor:
                    self.assertIn('id="' + anchor + '"', body)
            for term in ("valid_for", "period", "frame_id", "tables"):
                zh = query("field", term, "analysis")
                english = query("field", term, "analysis", language="en")
                self.assertTrue(english)
                self.assertEqual([x["path"] for x in zh], [x["path"] for x in english])
                self.assertEqual([machine_values(x["constraints"]) for x in zh],
                                 [machine_values(x["constraints"]) for x in english])
                for row in english:
                    self.assertTrue((en / row["source"].split("#")[0]).is_file())
        source = self.source_query("field", "valid_for", "analysis", language="en")
        bundle = self.bundle_query("field", "valid_for", "analysis", language="en")
        self.assertEqual(json.loads(json.dumps(source).replace("../../Schema/", "../schemas/")), bundle)


if __name__ == "__main__":
    unittest.main()
