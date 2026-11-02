"""验证离线HTML重复ID检测，不把静态解析当浏览器验收。"""
import unittest
from check_current_html import Page


class HtmlStructureTests(unittest.TestCase):
    """重复来自不同标签也必须报告；相邻页面不共享ID集合。"""

    def test_main_heading_collision_is_reported(self):
        """参数: 无。返回: None。异常: 漏报重复ID时断言失败。"""
        page=Page();page.feed('<main id="main"><h2 id="main">main</h2></main>')
        self.assertEqual(page.duplicate_ids,{'main'})

    def test_namespace_and_code_text_are_preserved(self):
        """参数: 无。返回: None。异常: 误报或高亮污染复制文本时失败。"""
        page=Page();page.feed('<main id="manual-main-content"><h2 id="main">main</h2><pre><code class="hljs"><span>unit:</span> &quot;1&quot;\n</code></pre></main>')
        self.assertFalse(page.duplicate_ids);self.assertEqual(page.codes,['unit: "1"\n'])


if __name__=='__main__':unittest.main()
