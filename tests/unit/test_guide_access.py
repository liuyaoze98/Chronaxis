"""验证指南默认入口只读、源码/安装目录选择及可选导出的文件保护。

使用临时普通文件模拟安装资源，不读取业务日志；结果和残件仅写测试目录。
"""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from chronaxis import user_guide
from chronaxis.cli import main


class GuideAccessTests(unittest.TestCase):
    """指南安装为普通文件；定位不能以导出、构建或解压作为前置。"""

    def setUp(self):
        """参数: 无。返回: 无。异常: 临时目录写入失败。建立独立假安装与两语言入口。"""
        self.area = tempfile.TemporaryDirectory(prefix="chronaxis-guide-")
        self.addCleanup(self.area.cleanup)
        self.root = Path(self.area.name)
        package = self.root / "Lib/site-packages/chronaxis"
        self.guide = package / "guide"
        (self.guide / "en").mkdir(parents=True)
        (self.guide / "README.md").write_text("中文入口", encoding="utf8")
        (self.guide / "en/README.md").write_text("English entry", encoding="utf8")
        (self.guide / "manifest.json").write_text(json.dumps({"sha256": {"README.md": "", "en/README.md": ""}}), encoding="utf8")
        replacement = patch.object(user_guide, "__file__", str(package / "user_guide.py"))
        replacement.start()
        self.addCleanup(replacement.stop)

    def test_default_and_english_cli_are_read_only(self):
        """参数: 无。返回: 无。异常: 定位写文件/调用生成器，或路径不正确时断言失败。"""
        before = {p.relative_to(self.guide).as_posix(): p.read_bytes() for p in self.guide.rglob("*") if p.is_file()}
        with patch.object(user_guide, "run_path", side_effect=AssertionError("阅读不能构建")), \
                patch.object(user_guide, "export_guide", side_effect=AssertionError("阅读不能导出")), \
                patch.object(Path, "write_bytes", side_effect=AssertionError("阅读不能写文件")):
            for args, expected in ((["guide"], self.guide / "README.md"),
                                   (["guide", "--language", "en"], self.guide / "en/README.md")):
                output = StringIO()
                with redirect_stdout(output):
                    self.assertEqual(main(args), 0)
                self.assertEqual(Path(output.getvalue().strip()), expected.resolve())
        after = {p.relative_to(self.guide).as_posix(): p.read_bytes() for p in self.guide.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_missing_entry_and_bad_language_fail(self):
        """参数: 无。返回: 无。异常: 缺资料不能返回虚构路径，未知语言不能静默回退。"""
        with self.assertRaises(ValueError):
            user_guide.guide_path("xx")
        (self.guide / "en/README.md").unlink()
        with self.assertRaises(FileNotFoundError):
            user_guide.guide_path("en")

    def test_source_uses_existing_manual(self):
        """参数: 无。返回: 无。异常: 源码入口依赖生成器或错误目录时断言失败。"""
        repo = self.root / "checkout"
        entry = repo / "Docs/AI/README.md"
        entry.parent.mkdir(parents=True)
        entry.write_text("Source entry", encoding="utf8")
        (entry.parent / "inputs.lock.json").write_text("{}", encoding="utf8")
        with patch.object(user_guide, "__file__", str(repo / "src/chronaxis/user_guide.py")), \
                patch.object(user_guide, "run_path", side_effect=AssertionError("源码阅读不能构建")):
            self.assertEqual(user_guide.guide_path(), entry)

    def test_optional_export_ignores_extra_files_and_refuses_overwrite(self):
        """参数: 无。返回: 无。异常: ZIP混入缓存、覆盖文件或改写源资料时失败。"""
        (self.guide / "unrelated.txt").write_text("not a release member", encoding="utf8")
        output = self.root / "guide.zip"
        user_guide.export_guide(output)
        with ZipFile(output) as archive:
            self.assertEqual(set(archive.namelist()), {"README.md", "en/README.md", "manifest.json"})
            self.assertEqual(archive.read("README.md"), (self.guide / "README.md").read_bytes())
        before = output.read_bytes()
        with self.assertRaises(FileExistsError):
            user_guide.export_guide(output)
        self.assertEqual(output.read_bytes(), before)
        named=self.root / "RefProjects/guide.zip"
        named.parent.mkdir()
        user_guide.export_guide(named)
        with ZipFile(named) as actual, ZipFile(output) as expected:
            self.assertEqual(actual.namelist(),expected.namelist())
            for name in actual.namelist():
                self.assertEqual(actual.read(name),expected.read(name))
        named_before=named.read_bytes()
        with self.assertRaises(FileExistsError):
            user_guide.export_guide(named)
        self.assertEqual(named.read_bytes(),named_before)

    def test_export_rejects_outside_manifest_member(self):
        """参数: 无。返回: 无。异常: 越界成员必须在读取外部文件或创建输出前拒绝。"""
        (self.guide / "manifest.json").write_text(json.dumps({"sha256": {"../private.txt": ""}}), encoding="utf8")
        output = self.root / "bad.zip"
        with self.assertRaises(ValueError):
            user_guide.export_guide(output)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
