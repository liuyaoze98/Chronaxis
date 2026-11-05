"""维护英文参考及译文来源清单，复用中文手册的接口和配置定义。

输入为三份原始Schema、人工英文说明和已审阅的翻译文件；输出英文字段参考、
公开API导航及来源摘要。只翻译title/description，不生成第二份运行规范。
"""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
from runpy import run_path

ROOT = Path(__file__).resolve().parents[1]
reading_text = run_path(str(ROOT / "tools/public_docs.py"))["reading_text"]
CURRENT = ROOT / "Docs/Current"
ENGLISH = CURRENT / "en"
SCHEMAS = ("analysis.schema.json", "batch-v1.schema.json", "definitions.schema.json")


def translate_schema(schema, translations):
    """仅替换规范说明。参数: 原规范、中文到英文映射。返回: 新对象。异常: 缺译报错。"""
    def visit(value):
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if key in ("title", "description") and isinstance(item, str) and re.search(r"[\u4e00-\u9fff]", item):
                    translated = translations.get(item)
                    if not isinstance(translated, str) or not translated.strip():
                        raise ValueError("Missing English schema description: " + item)
                    result[key] = translated
                else:
                    result[key] = visit(item)
            return result
        if isinstance(value, list):
            return [visit(item) for item in value]
        return deepcopy(value)
    return visit(schema)


def description_map():
    """读取人工译文。返回: 中文原文到英文的映射。异常: 文件或结构错误传播。"""
    return json.loads((ENGLISH / "schema-translations.json").read_bytes())["translations"]


def translated_schemas():
    """读取三份原规范并翻译说明。返回: 文件名到规范对象。异常: 缺译/文件错误。"""
    translations = description_map()
    return {name: translate_schema(json.loads((ROOT / "Docs/Schema" / name).read_bytes()), translations)
            for name in SCHEMAS}


def schema_sections(schema):
    """递归列出全部规范节点。返回: 路径/节点迭代器。异常: 无，JSON结构由调用方读取。"""
    # 包含if/then等组合分支，不能为了英文导航省掉条件约束。
    stack = [("$", schema)]
    while stack:
        path, node = stack.pop()
        if not isinstance(node, dict):
            continue
        yield path, node
        for key in ("properties", "$defs", "definitions", "patternProperties", "dependentSchemas"):
            for name, value in reversed(list(node.get(key, {}).items())):
                stack.append((path + "." + key + "." + name, value))
        for key in ("items", "additionalProperties", "if", "then", "else", "not", "contains"):
            if isinstance(node.get(key), dict):
                stack.append((path + "." + key, node[key]))
        for key in ("oneOf", "anyOf", "allOf", "prefixItems"):
            for index, value in reversed(list(enumerate(node.get(key, [])))):
                stack.append((f"{path}.{key}[{index}]", value))


def build_references():
    """生成英文规范参考及API索引。返回: 规范节点数。异常: 缺译/未知分组直接失败。"""
    schemas = translated_schemas()
    out = ["# Complete configuration schema reference\n\n",
           "Start with the [configuration guide](../configuration.md). The paths below locate nodes in JSON Schema, "
           "not literal keys to paste into YAML. `$defs` holds reusable definitions and `$ref` points to them. "
           "This page translates descriptions; the linked original schemas define validation. Runtime plan checks "
           "also validate references, units, and supported combinations.\n\n"]
    count = 0
    for name, schema in schemas.items():
        out.append(f"## {name}\n\n[Original validation schema](../../../Schema/{name})\n\n")
        for path, node in schema_sections(schema):
            constraints = {key: value for key, value in node.items()
                           if key not in ("properties", "$defs", "definitions", "patternProperties", "dependentSchemas",
                                          "items", "additionalProperties", "if", "then", "else", "not", "contains",
                                          "oneOf", "anyOf", "allOf", "prefixItems")}
            # Boolean additionalProperties/items/not carry constraints of their own.
            constraints.update({key: value for key, value in node.items()
                                if key in ("additionalProperties", "items", "not") and isinstance(value, bool)})
            if constraints:
                out.append(f"### `{name}: {path}`\n\n```json\n" +
                           json.dumps(constraints, ensure_ascii=False, indent=2) + "\n```\n\n")
                count += 1
    target = ENGLISH / "reference/configuration-schema.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("".join(out).rstrip() + "\n", encoding="utf8", newline="\n")
    public = json.loads((CURRENT / "public-api.json").read_bytes())
    # Object identities, signatures, and targets stay identical between languages.
    public["language"] = "en"
    groups = {"业务预设": "Domain presets", "执行与结果": "Execution and results",
              "批量任务": "Batch tasks", "时间转换": "Time conversion", "计划加载与检查": "Loading and checking plans",
              "高性能积分器": "High-performance integrator", "宿主扩展": "Host extensions"}
    for row in public["objects"]:
        row["group"] = groups[row["group"]]
    (ENGLISH / "public-api.json").write_text(json.dumps(public, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    from public_api_english import synchronize
    synchronize(CURRENT)
    return count


def translation_pairs():
    """列出当前主手册/API/AI的对应来源。返回: 路径对。异常: 无，不把内部实现当用户页。"""
    for source in sorted(CURRENT.glob("*.md")):
        yield source, ENGLISH / source.name
    for source in sorted((CURRENT / "public-api").glob("*.md")):
        yield source, ENGLISH / "public-api" / source.name
    for name in ("README.md", "workflow.md", "semantics.md", "tasks.json"):
        yield ROOT / "Docs/AI" / name, ROOT / "Docs/AI/en" / name


def digest(path):
    """取得用户正文摘要。参数: 路径。返回: SHA256。异常: 缺失文件传播。"""
    text = path.read_text(encoding="utf8").replace("\r\n", "\n")
    if path.suffix == ".md":
        text = reading_text(text)
    return sha256(text.encode("utf8")).hexdigest()


def inventory():
    """生成待审阅清单。返回: 每份译文及来源摘要。异常: 任一对应页缺失报错。"""
    rows = []
    for source, target in translation_pairs():
        rows.append(dict(source=source.relative_to(ROOT).as_posix(), target=target.relative_to(ROOT).as_posix(),
                         source_sha256=digest(source), target_sha256=digest(target)))
    return dict(language="en", author="liuyaoze", pages=rows,
                schemas={name: digest(ROOT / "Docs/Schema" / name) for name in SCHEMAS},
                navigation={"source": digest(CURRENT / "navigation.json"),
                            "english": digest(ENGLISH / "navigation.json")},
                schema_description_sha256=digest(ENGLISH / "schema-translations.json"))


def check_reviewed():
    """对照已审阅来源清单。返回: 页数。异常: 页面或来源改变时拒绝冒用旧翻译。"""
    expected = json.loads((ENGLISH / "translation-status.json").read_bytes())
    actual = inventory()
    if actual != expected:
        raise ValueError("English documents changed or their sources changed; review translations before recording a new inventory.")
    translated_schemas()
    return len(actual["pages"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record-reviewed", action="store_true",
                        help="Record source and translation hashes only after human/model review and validation")
    parser.add_argument("--references-only", action="store_true")
    args = parser.parse_args()
    count = build_references()
    if args.record_reviewed:
        (ENGLISH / "translation-status.json").write_text(json.dumps(inventory(), ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    pages = None if args.references_only else check_reviewed()
    print(json.dumps(dict(schema_nodes=count, translated_pages=pages)))
