"""把源码README内的相对文件链接转换为发行标签网页链接。

仅构建包元数据时调用，返回正文，不改源码文件、不生成第二份README或联网。
处理当前README使用的内联链接；代码围栏和外部链接保持原文。
"""
from pathlib import Path, PurePosixPath
import re
import tomllib
from urllib.parse import quote, urlsplit


def render(text, repository, version):
    """转换内联链接。参数: Markdown正文、仓库HTTPS地址、包版本。返回: 正文字符串。

    异常: 非HTTPS仓库地址或指向仓库外的相对路径ValueError。无文件或网络副作用。
    """
    address = urlsplit(repository)
    if address.scheme != "https" or not address.netloc or address.query or address.fragment:
        raise ValueError("Repository必须是无查询/片段的HTTPS仓库地址")
    base = repository.rstrip("/") + "/blob/" + quote("v" + version, safe="") + "/"

    def replace(match):
        """参数: 当前链接正则匹配。返回: 原链接或带标签的网页地址。异常: 越界路径。"""
        target = match.group(2)
        parts = urlsplit(target)
        if parts.scheme or parts.netloc or target.startswith("#"):
            return match.group(0)
        path = PurePosixPath(parts.path)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("README链接必须指向仓库内文件：" + target)
        url = base + quote(path.as_posix(), safe="/%")
        if parts.query:
            url += "?" + parts.query
        if parts.fragment:
            url += "#" + parts.fragment
        return match.group(1) + url + ")"

    # 围栏内是给用户复制的命令/数据，不能因链接外观改写代码。
    result, fence = [], None
    for line in text.splitlines(keepends=True):
        mark = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if mark:
            token = mark.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence) and not line[mark.end():].strip():
                fence = None
            result.append(line)
        elif fence:
            result.append(line)
        else:
            result.append(re.sub(r"(\[[^\]\n]+\]\()([^\s)]+)\)", replace, line))
    return "".join(result)


def build(root):
    """参数: 项目根目录Path。返回: PyPI正文。异常: 缺少配置/README或非法链接。"""
    root = Path(root)
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf8"))["project"]
    return render((root / "README.md").read_text(encoding="utf8"),
                  project["urls"]["Repository"], project["version"])
