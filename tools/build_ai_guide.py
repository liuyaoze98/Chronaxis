"""从锁定的公开手册输入生成同一套普通文件和可选ZIP，供安装与离线阅读共用。

输入为本发行的人工导航、Current公开页、Schema及合成输入；不导入产品或读取业务日志。
输出固定顺序、时间和相对路径；资料缺失、冻结摘要不符或导航悬空即报错。
"""
import argparse
import ast
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import re
from runpy import run_path
import tomllib
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
reading_text = run_path(str(ROOT / "tools/public_docs.py"))["reading_text"]
AUTHOR = ROOT / "Docs/AI"
CURRENT = ROOT / "Docs/Current"


def json_bytes(value):
    """参数: value为JSON兼容数据。返回: 可直接检索的UTF-8 JSON。异常: 非法值报错。"""
    # 以稳定格式保留中文，禁止非标准数值。
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def source_bytes(path):
    """参数: path为锁定资料。返回: 规范换行的文本或原始二进制。异常: 读取失败传播。"""
    data = path.read_bytes()
    # 只规范明确的文本格式；BLF等二进制必须逐字节保持。
    if path.suffix.lower() in {".json", ".yaml", ".md", ".csv", ".asc", ".dbc", ".ini", ".py"}:
        data = data.replace(b"\r\n", b"\n")
    return data


def public_card(page):
    """参数: page为Current公开页文本。返回: 面向安装用户的独立成员/参数说明。异常: 缺少公开正文时报错。"""
    # 从第一个公开锚点起保留所有成员说明；去除源码行、开发者导航及仓库专用调用例。
    page = reading_text(page)
    if '<a id="api-' not in page:
        raise ValueError("公开参考缺少成员正文")
    body = page[page.index('<a id="api-'):]
    body = re.sub(r"(?m)^(?:源码：|Source:).*\n?", "", body)
    body = re.sub(r"(?ms)^## Source locations\s*\n.*?(?=^## |\Z)", "", body)
    body = re.sub(r"(?ms)^#{2,5} (?:调用示例|Call examples?)\s*\n.*?(?=^<a id=|^#{1,5} |\Z)", "", body)
    body = body.replace("Docs/Current/examples/", "examples/").replace("从仓库根目录运行", "从资料解压目录运行")
    # 内容保留类型名称；本资料中的API文件与Current网页的相对目录不同。
    return re.sub(r"\[([^\]\n]+)\]\([^\)\n]+\)", r"\1", body).strip()


def add_english(files, sources, meta):
    """添加英文阅读层。参数: ZIP文件映射、锁定来源、元数据。返回: 无。异常: 对应关系缺失报错。"""
    # 示例、运行器和原始规范各保留一份；英文只增加说明与可检索字段视图。
    for name in ("README.md", "workflow.md", "semantics.md", "tasks.json"):
        text = sources["Docs/AI/en/" + name].decode("utf8")
        if name.endswith(".md"):
            text = reading_text(text)
        for source, target in (
            ("../../Current/examples/", "../examples/"),
            ("../../Current/documentation.json", "../manifest.json"),
            ("../../Current/en/public-api.json", "api/index.json"),
            ("../../Current/en/public-api/", "api/"),
            ("../../Current/en/reference/configuration-schema.md", "fields/index.json"),
            ("../../Schema/", "../schemas/"),
        ):
            text = text.replace(source, target)
        files["en/" + name] = text.encode("utf8")
    original = json.loads(files["tasks.json"])["tasks"]
    translated = json.loads(files["en/tasks.json"])["tasks"]
    if [t["id"] for t in original] != [t["id"] for t in translated]:
        raise ValueError("English task IDs differ from the reviewed task list")
    for left, right in zip(original, translated):
        for key in ("example", "api", "templates", "fields"):
            expected = "../" + left[key] if key == "example" else left[key]
            if right[key] != expected:
                raise ValueError(f"English task changed machine data: {left['id']}.{key}")
    api = []
    for item in json.loads(sources["Docs/Current/en/public-api.json"])["objects"]:
        name = item["name"]
        card = public_card(sources[f"Docs/Current/en/public-api/{name}.md"].decode("utf8"))
        card = card.replace("Docs/Current/examples/", "../examples/")
        card = card.replace("Run from the repository root", "Run from the guide's en directory")
        # public_card已将源码示例改成examples/，英文页面位于en下。
        card = re.sub(r"(?<![./])examples/", "../examples/", card)
        files[f"en/api/{name}.md"] = (f"# {name}\n\nImport: `from chronaxis import {name}`\n\n{card}\n").encode("utf8")
        api.append(dict(name=name, group=item["group"], signature=item["signature"], file=f"api/{name}.md"))
    files["en/api/index.json"] = json_bytes(dict(language="en", objects=api))
    helper = run_path(str(ROOT / "tools/english_docs.py"))
    translations = json.loads(sources["Docs/Current/en/schema-translations.json"])["translations"]
    english = {name: json_bytes(helper["translate_schema"](json.loads(data), translations))
               for name, data in files.items() if name.startswith("schemas/")}
    run_path(str(ROOT / "tools/ai_field_views.py"))["views"](english, json_bytes, meta["device_label"])
    for name, data in english.items():
        if not name.startswith("fields/"):
            continue
        value = json.loads(data)
        if name == "fields/index.json":
            value["use"] = "Look up a field within its schema and branch; validate the complete plan before running it."
        else:
            for row in value["fields"]:
                row["source"] = row["source"].replace("schemas/", "../schemas/", 1)
                row["conditions"] = [x.replace("schemas/", "../schemas/", 1) for x in row["conditions"]]
        files["en/" + name] = json_bytes(value)


def check_runtime(lock):
    """参数: lock为带产品树摘要的发行清单。返回: 无。异常: 可分发产品文件改变或增删时报错。"""
    material = []
    for path in sorted((ROOT/"src/chronaxis").rglob("*"),key=lambda p:p.as_posix()):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix in (".pyc",".pyo"):
            continue
        # 对Windows/Git的文本换行归一化，不归一化二进制。文件名及内容一并计入身份。
        relative = path.relative_to(ROOT).as_posix()
        material.append(relative + "\0" + sha256(source_bytes(path)).hexdigest() + "\n")
    if sha256("".join(material).encode()).hexdigest() != lock["runtime_sha256"]:
        raise ValueError("产品源码或模板与已审核指南不一致；请使用干净发行树，版本变更后先校核资料")


def build_files(*, verify_runtime=True):
    """参数: verify_runtime为安装构建核验。返回: 相对文件名到字节映射。异常: 漂移或文件缺失。"""
    # 两种交付读取同一显式清单。绝不递归打包用户新放入目录的日志或未验资料。
    lock = json.loads((AUTHOR / "inputs.lock.json").read_bytes())
    if verify_runtime:
        check_runtime(lock)
    sources = {}
    for relative, digest in lock["inputs"].items():
        path = ROOT / relative
        data = source_bytes(path)
        if sha256(data).hexdigest() != digest:
            raise ValueError("发行资料与冻结清单不一致：" + relative)
        sources[relative] = data
    meta = json.loads(sources["Docs/Current/documentation.json"])
    if meta["baseline"] != lock["product_baseline"]:
        raise ValueError("手册与资料基线不符")
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf8"))["project"]["version"]
    if version != lock["package_version"]:
        raise ValueError("包版本与已审核的用户指南不符")
    # 公开名称以当前产品根包为准；不要求额外安装运行依赖来构建资料。
    tree = ast.parse((ROOT / "src/chronaxis/__init__.py").read_text(encoding="utf8"))
    exports = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "__all__" for t in n.targets))
    public = json.loads(sources["Docs/Current/public-api.json"])["objects"]
    if sorted(exports) != sorted(row["name"] for row in public):
        raise ValueError("公开导出与资料清单不一致")
    files = {name: source_bytes(AUTHOR / name) for name in
             ("README.md", "tasks.json", "run_analysis.py", "semantics.md", "lookup.py", "workflow.md")}
    # 人工来源保留维护履历；安装用户只收到已核实的使用说明。
    for name in tuple(files):
        if name.endswith((".md", ".json")):
            text = files[name].decode("utf8")
            if name.endswith(".md"):
                text = reading_text(text)
            # 源码入口直接引用已有资料；独立包只改路径，正文和任务定义保持同一来源。
            for source, target in (
                ("../Current/examples/", "examples/"),
                ("../Current/documentation.json", "manifest.json"),
                ("../Current/public-api.json", "api/index.json"),
                ("../Current/public-api/", "api/"),
                ("../Current/reference/configuration-schema.md", "fields/index.json"),
                ("../Schema/", "schemas/"),
            ):
                text = text.replace(source, target)
            files[name] = text.encode("utf8")
    api = []
    for item in public:
        name = item["name"]
        rel = f"api/{name}.md"
        card = public_card(sources[f"Docs/Current/public-api/{name}.md"].decode())
        files[rel] = (f"# {name}\n\n推荐导入：`from chronaxis import {name}`\n\n{card}\n").encode()
        api.append(dict(name=name, group=item["group"], signature=item["signature"], file=rel))
    files["api/index.json"] = json_bytes(dict(device_label=meta["device_label"], objects=api))
    # 保持示例相对路径；配置规范原样附带，任何阅读索引都不替代完整校验器。
    for path, data in sources.items():
        if path.startswith("Docs/Current/examples/"):
            files[path.removeprefix("Docs/Current/")] = data
        elif path.startswith("Docs/Schema/"):
            files["schemas/" + Path(path).name] = data
    tasks = json.loads(files["tasks.json"])["tasks"]
    if len({t["id"] for t in tasks}) != len(tasks) or any(t["example"] not in files for t in tasks):
        raise ValueError("任务重复或范例缺失")
    catalog = json.loads((ROOT / "src/chronaxis/configuration/templates/catalog.json").read_bytes())
    templates = {entry["name"] for entry in catalog["templates"]}
    if any(set(t["api"])-set(exports) or set(t["templates"])-templates for t in tasks):
        raise ValueError("任务引用的API或初始化模板不属于本发行")
    # 生成字段说明后校验每条路由引用的主题，防止过期卡片指向不存在的配置键。
    run_path(str(ROOT / "tools/ai_field_views.py"))["views"](files, json_bytes, meta["device_label"])
    topics = {row["topic"] for row in json.loads(files["fields/index.json"])["shards"]}
    if any(set(task["fields"]) - topics for task in tasks):
        raise ValueError("任务关联了不存在的配置主题")
    for card in api:
        # 每个保留的代码片段均须能从解压目录找到实际文件，不依赖源码路径。
        for linked in re.findall(r'examples/[\w./-]+\.(?:yaml|json|py|csv)', files[card["file"]].decode()):
            if linked not in files:
                raise ValueError("公开接口例子缺附件：" + linked)
    add_english(files, sources, meta)
    files["manifest.json"] = json_bytes(dict(package="chronaxis", package_version=version,
        guide_revision=3, languages={"zh": "README.md", "en": "en/README.md"},
        config_version=3, product_baseline=meta["baseline"], manual_revision=lock["manual_revision"],
        runtime_revision=lock["runtime_revision"], runtime_sha256=lock["runtime_sha256"],
        device_label=meta["device_label"], entry="README.md", tested_platform="Windows / Python 3.12",
        evidence="公开契约与合成教学资料；不代表真实业务日志或其他平台验收。",
        sha256={n: sha256(d).hexdigest() for n,d in sorted(files.items())}))
    return files


def zip_files(files):
    """打包已组装的资料。参数: 文件映射。返回: ZIP字节。异常: 压缩失败。"""
    # 固定ZIP元数据，使两个发行渠道可直接比较完整摘要。
    out = BytesIO()
    with ZipFile(out, "w", compression=ZIP_DEFLATED) as archive:
        for name,data in sorted(files.items()):
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data, compress_type=ZIP_DEFLATED)
    return out.getvalue()


def build(*, verify_runtime=True):
    """生成可选离线ZIP。参数: 是否核运行源码。返回: ZIP字节。异常: 来源漂移或构建失败。"""
    return zip_files(build_files(verify_runtime=verify_runtime))


if __name__ == "__main__":
    # 维护者显式指定构建目标，用户导出使用独立的不覆盖入口。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--directory", type=Path, help="同时生成普通资料文件，目录必须不存在")
    args = parser.parse_args()
    if args.output is None and args.directory is None:
        parser.error("指定ZIP输出或--directory")
    contents = build_files(verify_runtime=os.environ.get('CHRONAXIS_DOC_SOURCE_TREE') == '1')
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(zip_files(contents))
    if args.directory is not None:
        args.directory.mkdir(parents=True, exist_ok=False)
        for name, data in contents.items():
            target = args.directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
