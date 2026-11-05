"""核对源码AI指南可直接阅读、查询，并与独立ZIP保持相同任务和字段含义。

只读取公开文档和合成资料，在临时目录解压生成包；不导入分析库、不读取业务日志。
验证实际路径和规范指针，避免仅用存在一个README证明源码入口已修复。
"""
import json
from pathlib import Path
import re
from runpy import run_path
import tempfile
import unittest
from zipfile import ZipFile
from io import BytesIO


ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "Docs/AI"


class AISourceEntryTests(unittest.TestCase):
    """源码与打包指南共享语义，各自返回所在目录可用的文件路径。"""

    @classmethod
    def setUpClass(cls):
        """准备临时资料包。参数: 无。返回: None。异常: 构建或文件缺失错误。"""
        cls.temp = tempfile.TemporaryDirectory(prefix="chronaxis-source-guide-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.bundle = Path(cls.temp.name)
        build = run_path(str(ROOT / "tools/build_ai_guide.py"))["build"]
        # 工作区保留用户冲突副本；此测试只核资料结构，正式发行另从干净树核运行摘要。
        with ZipFile(BytesIO(build(verify_runtime=False))) as archive:
            archive.extractall(cls.bundle)
        cls.source_query = staticmethod(run_path(str(GUIDE / "lookup.py"))["query"])
        cls.bundle_query = staticmethod(run_path(str(cls.bundle / "lookup.py"))["query"])

    def test_source_markdown_links_and_task_paths_exist(self):
        """从源码直接打开导航与示例。参数: 无。返回: None。异常: 悬空引用时报错。"""
        for path in GUIDE.glob("*.md"):
            body = path.read_text(encoding="utf8").split("## 变更履历")[0].split("## 版本记录")[0]
            for link in re.findall(r"\[[^\]\n]*\]\(([^\s)]+)\)", body):
                target = link.split("#", 1)[0]
                if target and not target.startswith(("https://", "http://")):
                    self.assertTrue((path.parent / target).is_file(), (path, link))
        for directory in (GUIDE, GUIDE / "en"):
            tasks = json.loads((directory / "tasks.json").read_bytes())["tasks"]
            for row in tasks:
                path = (directory / row["example"]).resolve()
                self.assertTrue(path.is_relative_to(ROOT / "Docs/Current/examples"), row)
                self.assertTrue(path.is_file(), row)
                self.assertIn(row["example"], row["verify"])

    def test_task_and_api_queries_return_current_layout_paths(self):
        """核对查询命中内容和可打开路径。参数: 无。返回: None。异常: 路径或任务不一致。"""
        for query, folder in ((self.source_query, GUIDE), (self.bundle_query, self.bundle)):
            tasks = query("task", "持续")
            self.assertTrue(any(row["id"] == "CONDITION_ENERGY" for row in tasks))
            for row in tasks:
                self.assertTrue((folder / row["example"]).is_file())
            for row in query("api", "AnalysisRunner"):
                file, _, anchor = row["file"].partition("#")
                self.assertTrue((folder / file).is_file())
                if anchor:
                    self.assertIn('id="' + anchor + '"', (folder / file).read_text(encoding="utf8"))
        self.assertEqual([row["name"] for row in self.source_query("api", "AnalysisRunner")],
                         [row["name"] for row in self.bundle_query("api", "AnalysisRunner")])

    def test_field_queries_agree_and_resolve_source_schema_pointers(self):
        """反查规范而非仅比较字段名。参数: 无。返回: None。异常: 错指针或约束差异。"""
        for term, branch in (("valid_for", None), ("source_type", "can_asc")):
            source = self.source_query("field", term, "analysis", branch)
            bundle = self.bundle_query("field", term, "analysis", branch)
            self.assertTrue(source)
            normalized = json.loads(json.dumps(source).replace("../Schema/", "schemas/"))
            self.assertEqual(normalized, bundle)
            for row in source:
                file, pointer = row["source"].split("#", 1)
                node = json.loads((GUIDE / file).read_bytes())
                for part in pointer.split("/")[1:]:
                    key = part.replace("~1", "/").replace("~0", "~")
                    node = node[int(key)] if isinstance(node, list) else node[key]
                for name, expected in row["constraints"].items():
                    self.assertEqual(node[name], expected)

    def test_enum_code_constraint_indexes_direct_and_grouped_signals(self):
        """按分析规范本身检索原码触发条件。参数：无。返回：无。异常：遗漏路径或错误标注触发字段。"""
        dependency = "/dependentSchemas/code_dtype"
        for language in ("zh", "en"):
            hits = self.bundle_query("field", "dtype", "analysis", "conditions", language)
            selected = [row for row in hits if row["source"].endswith(dependency + "/properties/dtype")]
            self.assertCountEqual([row["path"] for row in selected], ["signals.dtype", "signals.signals.dtype"])
            for row in selected:
                self.assertEqual(row["constraints"]["const"], "enum")
                self.assertIn(row["source"].rsplit("/properties/", 1)[0], row["conditions"])

    def test_bundle_has_no_source_directory_dependency(self):
        """完整独立ZIP不留下仓库路径。参数: 无。返回: None。异常: 逃逸或缺文件。"""
        for name in ("README.md", "workflow.md", "semantics.md", "tasks.json"):
            body = (self.bundle / name).read_text(encoding="utf8")
            self.assertNotIn("../Current/", body)
            self.assertNotIn("../Schema/", body)
        check = run_path(str(ROOT / "tests/ai_release/check_bundle.py"))["check"]
        archive = self.bundle.parent / (self.bundle.name + ".zip")
        self.addCleanup(archive.unlink, missing_ok=True)
        with ZipFile(archive, "w") as stream:
            for path in self.bundle.rglob("*"):
                if path.is_file():
                    stream.write(path, path.relative_to(self.bundle).as_posix())
        published = check(archive)
        source_ids = [item["id"] for item in json.loads((GUIDE / "tasks.json").read_bytes())["tasks"]]
        self.assertTrue({"HOST_EXTENSION", "TEMPORAL_CURRENT", "POWER_STATISTICS", "CALIBRATION"} <= set(source_ids))
        for tasks in (self.bundle / "tasks.json", self.bundle / "en/tasks.json"):
            self.assertEqual([item["id"] for item in json.loads(tasks.read_bytes())["tasks"]], source_ids)
        self.assertEqual((published["tasks"], published["english_tasks"]), (len(source_ids), len(source_ids)))


if __name__ == "__main__":
    unittest.main()
