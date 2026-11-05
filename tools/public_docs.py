"""提取公开文档正文，拒绝将履历后面的业务章节静默丢弃。

输入为维护用Markdown，返回去掉末尾履历的正文；不读写文件。
履历必须集中在末尾，历史记录由内部仓库保存。
"""
import re


def reading_text(text):
    """返回正文；履历之后出现章节标题时抛出ValueError。"""
    parts = re.split(r"(?m)^## (?:变更履历|版本记录|Change history|Revision history)\s*$", text)
    if len(parts) > 1 and re.search(r"(?m)^#{1,6} ", "\n".join(parts[1:])):
        raise ValueError("履历后包含正文标题；请将正文移到履历前")
    return parts[0].rstrip() + "\n"
