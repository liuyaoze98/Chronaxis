"""核对发行README链接转换，不访问网络或修改来源文件。"""
from pathlib import Path
from runpy import run_path
import re
import unittest
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
HELPER = run_path(str(ROOT / "tools/pypi_readme.py"))
REPO = "https://github.com/liuyaoze98/Chronaxis"


class PyPIReadmeTests(unittest.TestCase):
    """发行链接绑定版本，源文档与可复制代码不随构建改变。"""

    def test_links_keep_code_and_external_targets(self):
        """参数: 无。返回: 无。异常: 代码、外链或锚点被改写时断言失败。"""
        text = "[doc](Docs/说明.md#part) [web](https://example.org) [mail](mailto:x@y.org) [anchor](#a)\n```text\n[x](keep.md)\n```\n~~~\n[y](also.md)\n~~~\n"
        result = HELPER["render"](text, REPO, "0.1.0.dev0")
        self.assertIn(REPO + "/blob/v0.1.0.dev0/Docs/%E8%AF%B4%E6%98%8E.md#part", result)
        self.assertEqual(result.split(" [web]", 1)[1], text.split(" [web]", 1)[1])

    def test_rejects_invalid_base_or_parent_paths(self):
        """参数: 无。返回: 无。异常: 仓库外相对链接或错误仓库地址未被拒绝。"""
        with self.assertRaises(ValueError):
            HELPER["render"]("[x](../private.md)", REPO, "0.1.0.dev0")
        with self.assertRaises(ValueError):
            HELPER["render"]("[x](README.md)", "file:///private", "0.1.0.dev0")

    def test_actual_readme_targets_exist_and_source_is_unchanged(self):
        """参数: 无。返回: 无。异常: 实际正文遗漏链接、指向缺文件或改写原文。"""
        path = ROOT / "README.md"
        before = path.read_bytes()
        result = HELPER["build"](ROOT)
        links = re.findall(r"\]\(([^)]+)\)", result)
        self.assertGreater(len(links), 20)
        prefix = REPO + "/blob/v0.1.0.dev0/"
        for target in links:
            self.assertTrue(target.startswith(("https://", "mailto:", "#")), target)
            if target.startswith(prefix):
                self.assertTrue((ROOT / unquote(target[len(prefix):].split("#")[0])).is_file(), target)
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
