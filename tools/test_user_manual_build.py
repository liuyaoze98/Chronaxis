"""验证随包Markdown用户手册的选文、链接改写、链接检查和按锁构建结果。

前几项用内存中的小样本检查规则；最后一项按当前锁定资料实际构建一次，只读源码树、不写文件。
"""
import json
from pathlib import Path
from runpy import run_path
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
MANUAL = run_path(str(ROOT / "tools/build_user_manual.py"))
LINKS = ("0.1.0.dev5", "https://example.test/docs/", "https://example.test/repo")


class ManualRuleTests(unittest.TestCase):
    """链接改写只依赖页面位置、成员集合和项目网址，可用固定样本覆盖每种目标。"""

    def rewrite(self, page, target, members=("index.md", "examples/a.yaml", "en/index.md")):
        """参数: page页面、target原链接、members成员。返回: 改写结果。异常: 规则拒绝时ValueError。"""
        return MANUAL["rewrite_target"](page, target, set(members), LINKS)

    def test_selection_excludes_reference_and_build(self):
        """参数: 无。返回: 无。异常: 选文范围与约定不符时断言失败。"""
        select = MANUAL["is_manual_source"]
        for name in ("Docs/Current/index.md", "Docs/Current/en/rules.md", "Docs/Current/public-api/AnalysisPlan.md",
                     "Docs/Current/en/public-api/AnalysisPlan.md", "Docs/Current/examples/data/can/x.asc"):
            self.assertTrue(select(name), name)
        for name in ("Docs/Current/reference/chronaxis.cli.md", "Docs/Current/en/reference/index.md",
                     "Docs/Current/_build/html/index.html", "Docs/Current/documentation.json", "Docs/AI/README.md"):
            self.assertFalse(select(name), name)

    def test_targets_inside_and_outside_bundle(self):
        """参数: 无。返回: 无。异常: 包内链接被改动、包外目标未固定版本或锚点丢失时断言失败。"""
        self.assertEqual(self.rewrite("index.md", "examples/a.yaml"), "examples/a.yaml")
        self.assertEqual(self.rewrite("en/index.md", "../examples/a.yaml#top"), "../examples/a.yaml#top")
        self.assertEqual(self.rewrite("index.md", "examples/"), "examples/")
        self.assertEqual(self.rewrite("index.md", "reference/chronaxis.cli.md#api-main"),
                         "https://example.test/repo/blob/v0.1.0.dev5/Docs/Current/reference/chronaxis.cli.md#api-main")
        self.assertEqual(self.rewrite("public-api/X.md", "../../../src/chronaxis/cli.py"),
                         "https://example.test/repo/blob/v0.1.0.dev5/src/chronaxis/cli.py")
        self.assertEqual(self.rewrite("index.md", "_build/html/ai-guide/README.md"), "../guide/README.md")
        self.assertEqual(self.rewrite("en/index.md", "../_build/html/ai-guide/en/README.md"), "../../guide/en/README.md")
        self.assertEqual(self.rewrite("index.md", "_build/html/en/index.html"), "https://example.test/docs/en/")
        self.assertEqual(self.rewrite("index.md", "https://other.test/x"), "https://other.test/x")
        self.assertEqual(self.rewrite("index.md", "#local"), "#local")

    def test_private_or_unknown_targets_rejected(self):
        """参数: 无。返回: 无。异常: 内部记录、越界路径或未知生成物没有被拒绝时断言失败。"""
        for target in ("../Verification/R.md", "../../outside.md", "_build/html/other.html", "../../work/x.md"):
            with self.assertRaises(ValueError, msg=target):
                self.rewrite("index.md", target)

    def test_fenced_examples_and_broken_links(self):
        """参数: 无。返回: 无。异常: 围栏内文本被改写，或残留坏链接未报错时断言失败。"""
        text = "[外部](reference/a.md)\n```yaml\nx: '[不是链接](reference/a.md)'\n```\n"
        result = MANUAL["rewrite_links"]("index.md", text, {"index.md"}, LINKS)
        self.assertIn("https://example.test/repo/blob/v0.1.0.dev5/Docs/Current/reference/a.md", result)
        self.assertIn("x: '[不是链接](reference/a.md)'", result)
        with self.assertRaises(ValueError):
            MANUAL["check_links"]({"index.md": b"[missing](nothing.md)\n"})
        self.assertEqual(MANUAL["check_links"]({"index.md": b"[guide](../guide/README.md)\n[ok](a.md)\n", "a.md": b""}), 2)


class ManualBuildTests(unittest.TestCase):
    """按当前锁定资料完整构建，核对首页、无履历、无内部参考及示例完整。"""

    def test_locked_build(self):
        """参数: 无。返回: 无。异常: 锁漂移、缺页、履历残留或示例缺失时断言失败。"""
        files = MANUAL["build_files"]()
        lock = json.loads((ROOT / "Docs/AI/inputs.lock.json").read_bytes())
        version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf8"))["project"]["version"]
        manifest = json.loads(files["manifest.json"])
        self.assertEqual(manifest["package_version"], version)
        self.assertEqual(set(manifest["sha256"]), set(files) - {"manifest.json"})
        for entry in ("index.md", "en/index.md", "quickstart.md", "en/quickstart.md",
                      "public-api/AnalysisPlan.md", "examples/analysis.yaml", "examples/activity.yaml"):
            self.assertIn(entry, files)
        self.assertFalse([name for name in files if name.startswith(("reference/", "en/reference/", "_build/"))])
        for name, data in files.items():
            if name.endswith(".md") and not name.startswith("examples/"):
                text = data.decode("utf8")
                self.assertNotRegex(text, r"(?m)^## (变更履历|版本记录|Change history|Revision history)", name)
                self.assertNotIn("](../src/", text, name)
        locked_examples = {n.removeprefix("Docs/Current/") for n in lock["manual_inputs"]
                           if n.startswith("Docs/Current/examples/")}
        self.assertEqual(locked_examples, {n for n in files if n.startswith("examples/")})
        # 手册单独登记，不能把全部示例并入AI指南已审核的输入集合。
        self.assertLess(sum(n.startswith("Docs/Current/examples/") for n in lock["inputs"]), len(locked_examples))


if __name__ == "__main__":
    unittest.main()
