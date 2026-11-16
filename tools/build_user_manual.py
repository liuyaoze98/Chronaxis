"""从锁定的公开手册输入生成随安装包附带的Markdown用户手册。

输入为`Docs/AI/inputs.lock.json`中`manual_inputs`登记并核对过摘要的Current中英文章节、公开API页及全部示例，
以及pyproject中的版本和项目网址；不导入产品、不读取业务日志、不需要Node。
输出为“手册内相对路径→字节”的映射，由setup.py写入`chronaxis/manual/`。
正文按公开导出规则去掉末尾履历；包内目标的相对链接保持不变，AI指南链接改到同包guide，
网页手册首页改为Documentation地址，其余包外目标改为Repository在`v<版本>`标签下的同一文件。
改写后仍有无法在包内找到的相对链接、或链接指向公开源码以外的位置时报错，不生成残缺手册。
"""
import argparse
from hashlib import sha256
import json
import posixpath
import re
from pathlib import Path
from runpy import run_path
import tomllib
from urllib.parse import quote, unquote

ROOT = Path(__file__).resolve().parents[1]
reading_text = run_path(str(ROOT / "tools/public_docs.py"))["reading_text"]
resource_bytes = run_path(str(ROOT / "tools/ai_resource_bytes.py"))["resource_bytes"]
CURRENT = "Docs/Current/"
# 公开源码导出包含的顶层位置；只有这些目标才能改写为发行标签下的仓库链接。
PUBLIC_TARGETS = ("src/chronaxis/", "Docs/Current/", "Docs/Schema/", "Docs/Release/", "Docs/AI/",
                  "examples/", "requirements/", "README.md", "README.en.md", "LICENSE")
LINK = re.compile(r"(\]\()([^)\s]+)")
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def is_manual_source(relative):
    """判断仓库相对路径是否属于随包用户手册。

    参数: relative为使用/分隔的仓库相对路径。返回: bool。异常: 无。
    包含Current中英文章节、中英文公开API页和全部示例；内部模块参考、生成目录及其他JSON不随包。
    """
    if not relative.startswith(CURRENT):
        return False
    parts = relative.removeprefix(CURRENT).split("/")
    if parts[0] == "examples":
        return len(parts) > 1 and "_build" not in parts
    if not parts[-1].endswith(".md"):
        return False
    # 章节只取根层与en根层；公开API只取两种语言各自的一层目录。
    return (len(parts) == 1 or (len(parts) == 2 and parts[0] in ("en", "public-api"))
            or (len(parts) == 3 and parts[:2] == ["en", "public-api"]))


def project_links():
    """读取发行版本和公开网址。参数: 无。返回: (版本, 文档首页, 仓库地址)。异常: pyproject缺字段时KeyError。"""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf8"))["project"]
    documentation = project["urls"]["Documentation"]
    # 首页地址统一以/结尾，便于拼接en/等子路径。
    return project["version"], documentation.rstrip("/") + "/", project["urls"]["Repository"].rstrip("/")


def rewrite_target(page, target, members, links):
    """把一条相对链接改成安装后可用的目标。

    参数: page为手册内页面路径，target为原链接，members为手册成员集合，links为project_links结果。
    返回: 改写后的链接文本；包内目标原样返回。
    异常: ValueError，链接越出仓库、指向未公开位置或未知生成物。
    """
    if SCHEME.match(target) or target.startswith(("#", "/")):
        return target
    path, separator, fragment = target.partition("#")
    if not path:
        return target
    suffix = separator + fragment
    resolved = posixpath.normpath(posixpath.join(CURRENT + posixpath.dirname(page), unquote(path)))
    inside = resolved.removeprefix(CURRENT) if resolved.startswith(CURRENT) else None
    # 包内文件或包内目录保持原相对写法，读者在编辑器中可直接跳转。
    if inside is not None and (inside in members or any(name.startswith(inside + "/") for name in members)):
        return target
    page_dir = posixpath.dirname("manual/" + page)
    if inside is not None and inside.startswith("_build/html/ai-guide/"):
        # 网页手册附带的AI指南在安装包中位于manual的同级guide目录。
        return posixpath.relpath("guide/" + inside.removeprefix("_build/html/ai-guide/"), page_dir) + suffix
    version, documentation, repository = links
    if inside in ("_build/html/index.html", "_build/html/en/index.html"):
        return documentation + inside.removeprefix("_build/html/").removesuffix("index.html") + suffix
    if inside is not None and inside.startswith("_build/"):
        raise ValueError(f"{page}链接到未随包的生成物：{target}")
    if resolved.startswith("..") or not resolved.startswith(PUBLIC_TARGETS):
        raise ValueError(f"{page}链接到公开源码以外的位置：{target}")
    # 其余公开目标链接到同版本标签，避免阅读安装包时看到其他版本的说明或源码。
    return f"{repository}/blob/v{version}/{quote(resolved, safe='/')}" + suffix


def rewrite_links(page, text, members, links):
    """改写一页正文中代码围栏外的Markdown链接。

    参数: page为手册内路径，text为已去履历正文，members为成员集合，links为项目网址。
    返回: 改写后的文本。异常: rewrite_target的ValueError原样传播。
    """
    output, fence = [], None
    for line in text.splitlines(keepends=True):
        marker = FENCE.match(line)
        if marker:
            token = marker.group(1)
            # 围栏开闭按同种字符且长度不短于开头判断，与公开正文提取规则一致。
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            output.append(line)
            continue
        if fence is not None:
            output.append(line)
            continue
        output.append(LINK.sub(lambda match: match.group(1) + rewrite_target(page, match.group(2), members, links), line))
    return "".join(output)


def check_links(files):
    """确认手册中剩余的每条相对链接都能在安装目录找到。

    参数: files为手册内路径到字节的映射。返回: 已检查的相对链接数。
    异常: ValueError，任何相对链接的文件不在手册内且不是同包AI指南入口。
    """
    members, checked = set(files), 0
    for page, data in files.items():
        if not page.endswith(".md"):
            continue
        fence = None
        for line in data.decode("utf8").splitlines():
            marker = FENCE.match(line)
            if marker:
                token = marker.group(1)
                if fence is None:
                    fence = token
                elif token[0] == fence[0] and len(token) >= len(fence):
                    fence = None
                continue
            if fence is not None:
                continue
            for target in LINK.findall(line):
                link = target[1]
                if SCHEME.match(link) or link.startswith(("#", "/")) or not link.partition("#")[0]:
                    continue
                resolved = posixpath.normpath(posixpath.join("manual/" + posixpath.dirname(page),
                                                             unquote(link.partition("#")[0])))
                # 只有两种语言的AI指南入口允许跨出manual目录，它们由同一wheel提供。
                if resolved in ("guide/README.md", "guide/en/README.md"):
                    checked += 1
                    continue
                inside = resolved.removeprefix("manual/") if resolved.startswith("manual/") else None
                if inside is None or not (inside in members or any(n.startswith(inside + "/") for n in members)):
                    raise ValueError(f"随包手册链接无法解析：{page} -> {link}")
                checked += 1
    return checked


def build_files():
    """生成随包手册文件。

    参数: 无。返回: 手册内相对路径到字节的有序映射，含manifest.json。
    异常: ValueError，锁内缺手册首页、文件摘要与锁不符、版本不符或链接无法解析；读取失败传播。
    """
    lock = json.loads((ROOT / "Docs/AI/inputs.lock.json").read_bytes())
    links = project_links()
    if links[0] != lock["package_version"]:
        raise ValueError("包版本与已审核的手册资料不符")
    sources = {}
    # 只读取锁中manual_inputs登记的手册文件；用户放入目录的日志或未审核资料不会被递归带入。
    for relative, digest in lock.get("manual_inputs", {}).items():
        if not is_manual_source(relative):
            raise ValueError("锁中的手册输入不属于随包手册范围：" + relative)
        data = resource_bytes(relative, (ROOT / relative).read_bytes())
        if sha256(data).hexdigest() != digest:
            raise ValueError("随包手册资料与冻结清单不一致：" + relative)
        sources[relative.removeprefix(CURRENT)] = data
    if "index.md" not in sources or "en/index.md" not in sources:
        raise ValueError("锁定资料缺少手册首页；请先用lock_ai_inputs.py重新登记")
    members = set(sources)
    files = {}
    for name, data in sorted(sources.items()):
        if name.endswith(".md") and not name.startswith("examples/"):
            # 安装用户只收到使用正文；维护履历留在源码仓库。
            text = reading_text(data.decode("utf8"))
            files[name] = rewrite_links(name, text, members, links).encode("utf8")
        else:
            files[name] = data
    checked = check_links(files)
    files["manifest.json"] = (json.dumps(dict(
        package="chronaxis", package_version=links[0], manual_revision=lock["manual_revision"],
        languages={"zh": "index.md", "en": "en/index.md"}, online=links[1], checked_links=checked,
        sha256={name: sha256(data).hexdigest() for name, data in sorted(files.items())}),
        ensure_ascii=False, indent=2) + "\n").encode("utf8")
    return files


if __name__ == "__main__":
    # 维护者可生成到新目录预览；目录必须不存在，避免混入旧文件。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="不存在的新目录")
    args = parser.parse_args()
    contents = build_files()
    args.directory.mkdir(parents=True)
    for relative, content in contents.items():
        target = args.directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    print(json.dumps(dict(directory=str(args.directory), files=len(contents)), ensure_ascii=False))
