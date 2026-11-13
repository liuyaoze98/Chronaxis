"""提取公开文档正文，拒绝将履历后面的业务章节静默丢弃。

输入为维护用Markdown，返回去掉末尾履历的正文；不读写文件。
履历必须集中在末尾，历史记录由内部仓库保存。
"""
import re


def _reject_misplaced_history(text):
    """拒绝正文中的项目履历，保留业务时间和代码示例原文。

    只识别项目约定的“时间 | 任务 | [设备]”记录，不把普通日期当成履历。
    围栏内的内容属于可复制示例，不参与这项排版检查。
    """
    fence = None
    for number, line in enumerate(text.splitlines(), 1):
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            continue
        if fence is None and re.match(
            r"^\s*(?:[-*]\s+)?\d{4}-\d{2}-\d{2}T\S+\s*\|\s*"
            r"[A-Z][A-Z0-9/-]*\s*\|\s*\[(?:home|work|pending)\]", line
        ):
            raise ValueError(f"正文第{number}行含开发履历；请移入末尾履历章节")


def reading_text(text):
    """返回正文；履历之后出现章节标题时抛出ValueError。"""
    parts = re.split(r"(?m)^## (?:变更履历|版本记录|Change history|Revision history)\s*$", text)
    if len(parts) > 1 and re.search(r"(?m)^#{1,6} ", "\n".join(parts[1:])):
        raise ValueError("履历后包含正文标题；请将正文移到履历前")
    _reject_misplaced_history(parts[0])
    return parts[0].rstrip() + "\n"
