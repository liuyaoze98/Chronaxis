"""查询源码或离线资料中的任务、公开接口及字段，不运行用户配置。

输入为命令行查询词及可选规范或分支；输出JSON记录、原始指针和约束位置。
源码直接复用Current与Schema；字段查询时才在内存生成索引，不落盘、不需要
第三方库。字段命中只代表该分支存在定义，实际计划仍须用完整加载器验证。
"""
import argparse
from functools import lru_cache
import json
from pathlib import Path
from runpy import run_path

ROOT = Path(__file__).resolve().parent


def source_layout():
    """判断是否为源码目录。参数: 无。返回: bool。异常: 无，不为损坏的离线包补读源码。"""
    return not (ROOT / "manifest.json").is_file() and (ROOT.parent / "Current/public-api.json").is_file()


@lru_cache(maxsize=2)
def source_fields(root, language="zh"):
    """按需构造源码字段索引。参数: root为指南目录。返回: 内存文件映射。异常: 规范缺失或损坏。"""
    # 复用发行生成器，既不复制规范文件，也不把索引写进用户的源码目录。
    helper = run_path(str(root.parent.parent / "tools/ai_field_views.py"))
    files = {"schemas/" + name: (root.parent / "Schema" / name).read_bytes() for name in helper["DOCS"]}
    def encode(value):
        """编码生成器输入。参数: JSON兼容值。返回: UTF-8字节。异常: 非法JSON值。"""
        return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf8")
    if language == "en":
        translated = run_path(str(root.parent.parent / "tools/english_docs.py"))["translated_schemas"]()
        files = {"schemas/" + name: encode(value) for name, value in translated.items()}
    helper["views"](files, encode, "source")
    return files


def read(path, language="zh"):
    """参数: path为逻辑资料路径。返回: JSON数据。异常: 文件缺失或格式损坏，不静默换版本。"""
    if source_layout():
        if path == "api/index.json":
            folder = "Current/en" if language == "en" else "Current"
            public = json.loads((ROOT.parent / folder / "public-api.json").read_bytes())
            return dict(objects=[dict(name=row["name"], group=row["group"], signature=row["signature"],
                                      file=("../../Current/en/" if language == "en" else "../Current/") + row["target"])
                                 for row in public["objects"]])
        if path.startswith("fields/"):
            return json.loads(source_fields(ROOT, language)[path])
    return json.loads((ROOT / ("en" if language == "en" else "") / path).read_bytes())


def query(kind, term, schema=None, branch=None, language="zh"):
    """参数: kind类别、term名称/词、schema文档、branch分支。返回: 匹配条目列表。异常: 读取失败。"""
    term = term.casefold()
    if kind == "task":
        # 只查询意图、场景与相关字段，不用答案关键词误匹配别的任务。
        return [row for row in read("tasks.json", language)["tasks"] if term in
                " ".join([row["id"],row["intent"],*row["fields"]]).casefold()]
    if kind == "api":
        return [row for row in read("api/index.json", language)["objects"] if term in row["name"].casefold()]
    hits = []
    # 先按主题和分支缩小范围；逐字段返回准确指针以及所在分支的检查条件。
    for card in read("fields/index.json", language)["shards"]:
        if schema and card["schema"] != schema or branch and card["branch"] != branch:
            continue
        if term not in card["names"] and not term.startswith(card["topic"].casefold()+"."):
            continue
        for row in read(card["file"], language)["fields"]:
            if term in (row["path"].casefold(),row["path"].split(".")[-1].casefold()):
                hit = dict(schema=card["schema"], branch=card["branch"], **row)
                if source_layout():
                    # 返回当前阅读位置可直接打开的规范，不暴露仅存在于ZIP内的路径。
                    prefix = "../../Schema/" if language == "en" else "../Schema/"
                    hit["source"] = hit["source"].replace("schemas/", prefix, 1)
                    hit["conditions"] = [value.replace("schemas/", prefix, 1) for value in hit["conditions"]]
                hits.append(hit)
    return hits


if __name__ == "__main__":
    # 区分“没有匹配项”和成功命中，绝不自动改名或选第一个歧义项。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("task","api","field"))
    parser.add_argument("term")
    parser.add_argument("--schema")
    parser.add_argument("--branch")
    parser.add_argument("--language", choices=("zh", "en"), default="zh")
    args = parser.parse_args()
    matches = query(args.kind, args.term, args.schema, args.branch, args.language)
    print(json.dumps(matches, ensure_ascii=False, indent=2))
    raise SystemExit(0 if matches else 1)
