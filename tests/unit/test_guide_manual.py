"""验证随包用户手册入口：安装/源码布局选择、语言选择、只读及缺失报错。

使用临时目录模拟安装包和源码检出，不读取业务日志、不构建手册；只在测试目录写入假入口。
"""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from chronaxis import user_guide
from chronaxis.cli import main


class ManualAccessTests(unittest.TestCase):
    """手册安装为普通Markdown文件；定位命令只返回首页路径，不复制或改写资料。"""

    def setUp(self):
        """参数: 无。返回: 无。异常: 临时目录写入失败。建立假安装包的manual中英文首页。"""
        self.area = tempfile.TemporaryDirectory(prefix="chronaxis-manual-")
        self.addCleanup(self.area.cleanup)
        self.root = Path(self.area.name)
        self.package = self.root / "Lib/site-packages/chronaxis"
        self.manual = self.package / "manual"
        (self.manual / "en").mkdir(parents=True)
        (self.manual / "index.md").write_text("# 手册首页", encoding="utf8")
        (self.manual / "en/index.md").write_text("# Manual", encoding="utf8")
        replacement = patch.object(user_guide, "__file__", str(self.package / "user_guide.py"))
        replacement.start()
        self.addCleanup(replacement.stop)

    def test_cli_prints_both_languages_without_writing(self):
        """参数: 无。返回: 无。异常: 命令写文件、路径错误或退出码非0时断言失败。"""
        before = {p.relative_to(self.manual).as_posix(): p.read_bytes() for p in self.manual.rglob("*") if p.is_file()}
        # 阅读入口不能借机写文件；任何写入都会让测试立即失败。
        with patch.object(Path, "write_bytes", side_effect=AssertionError("阅读不能写文件")), \
                patch.object(Path, "write_text", side_effect=AssertionError("阅读不能写文件")):
            for args, expected in ((["manual"], self.manual / "index.md"),
                                   (["manual", "--language", "en"], self.manual / "en/index.md")):
                output = StringIO()
                with redirect_stdout(output):
                    self.assertEqual(main(args), 0)
                self.assertEqual(Path(output.getvalue().strip()), expected.resolve())
        after = {p.relative_to(self.manual).as_posix(): p.read_bytes() for p in self.manual.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_bad_language_and_missing_entry_fail(self):
        """参数: 无。返回: 无。异常: 未知语言静默回退或缺失入口返回虚构路径时断言失败。"""
        with self.assertRaises(ValueError):
            user_guide.manual_path("xx")
        (self.manual / "en/index.md").unlink()
        with self.assertRaises(FileNotFoundError):
            user_guide.manual_path("en")
        # CLI把缺失资料报告为文件操作失败，退出码1，不打印路径。
        output, errors = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            self.assertEqual(main(["manual", "--language", "en"]), 1)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("用户手册入口缺失", errors.getvalue())

    def test_source_layout_uses_current_manual(self):
        """参数: 无。返回: 无。异常: 源码布局未使用Docs/Current或缺资料未报错时断言失败。"""
        repo = self.root / "checkout"
        current = repo / "Docs/Current"
        (current / "en").mkdir(parents=True)
        (current / "index.md").write_text("# 源码首页", encoding="utf8")
        (current / "en/index.md").write_text("# Source manual", encoding="utf8")
        with patch.object(user_guide, "__file__", str(repo / "src/chronaxis/user_guide.py")):
            # 缺少文档元数据时不能把任意同名目录当作手册。
            with self.assertRaises(FileNotFoundError):
                user_guide.manual_path()
            (current / "documentation.json").write_text("{}", encoding="utf8")
            self.assertEqual(user_guide.manual_path(), (current / "index.md").resolve())
            self.assertEqual(user_guide.manual_path("en"), (current / "en/index.md").resolve())


if __name__ == "__main__":
    unittest.main()
