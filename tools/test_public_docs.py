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

    def test_english_history_is_excluded(self):
        """英文维护记录同样过滤；记录之后误放业务章节仍须报错。"""
        for heading in ("Change history", "Revision history"):
            with self.subTest(heading=heading):
                self.assertEqual(reading_text("# Guide\n\nTask\n\n## " + heading + "\ninternal\n"), "# Guide\n\nTask\n")
                with self.assertRaises(ValueError):
                    reading_text("# Guide\n## " + heading + "\ninternal\n## Instructions\nDo this\n")

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
            ('Docs/AI/semantics.md', '数值与后端核对'),
        ):
            with self.subTest(name=name):
                self.assertIn(phrase, reading_text((ROOT/name).read_text(encoding='utf8')))

    def test_unheaded_project_history_is_rejected(self):
        """缺少履历标题会泄露维护日志，必须让生成失败而不是悄悄删行。"""
        with self.assertRaisesRegex(ValueError, '正文第3行'):
            reading_text('# Exports\n\n- 2026-11-14T00:13:07+08:00 | DOC-REVIEW-10/J23 | [home] Changed docs.\n')

    def test_business_dates_and_fenced_examples_are_preserved(self):
        """业务采集日期和示例中的日志不是源文档履历。"""
        text = ('# 时间\n\n2026-11-14T00:13:07+08:00 为采集时刻。\n'
                '```text\n- 2026-11-14T00:13:07+08:00 | DOC-REVIEW-10/J23 | [home] Example\n```\n')
        self.assertEqual(reading_text(text), text)

    def test_exports_body_excludes_developer_records(self):
        """英文导出页保留输出说明，维护记录仅留在源文件履历中。"""
        text = reading_text((ROOT/'Docs/Current/en/exports.md').read_text(encoding='utf8'))
        self.assertIn('exports.index_file', text)
        self.assertNotIn('AUDIT-FIX-02/B2', text)
        self.assertNotIn('DOC-REVIEW-10/J23', text)


if __name__ == '__main__':
    unittest.main()
