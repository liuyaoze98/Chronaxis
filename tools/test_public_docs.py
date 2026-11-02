"""验证公开资料过滤不会把后续有效正文当作履历静默删掉。"""
from pathlib import Path
import unittest
from public_docs import reading_text

ROOT = Path(__file__).resolve().parents[1]


class PublicDocsTests(unittest.TestCase):
    """覆盖履历、混放正文与两个曾经遗漏的实际章节。"""

    def test_trailing_history_is_excluded(self):
        """公开正文不携带维护日志。"""
        self.assertEqual(reading_text('# 说明\n\n正文\n\n## 变更履历\n\n旧记录\n'), '# 说明\n\n正文\n')

    def test_body_after_history_is_rejected(self):
        """错误排版应暴露给维护者，不能输出不完整正文。"""
        for heading in ('## 新章节', '### 补充行为'):
            with self.subTest(heading=heading), self.assertRaises(ValueError):
                reading_text('# 说明\n## 变更履历\n旧记录\n'+heading+'\n有效说明\n')

    def test_actual_manual_sections_survive(self):
        """两处漏渲染内容及AI正文必须保留到公开稿。"""
        for name, phrase in (
            ('Docs/Current/rules.md', '严格超过指定时长'),
            ('Docs/Current/text-inputs.md', '无关报文的时间回退'),
            ('Docs/AI/semantics.md', '迁移数值与后端核对'),
        ):
            with self.subTest(name=name):
                self.assertIn(phrase, reading_text((ROOT/name).read_text(encoding='utf8')))


if __name__ == '__main__':
    unittest.main()
