"""只读取最终AI资料ZIP，独立核对文件摘要、离线链接、版本、字段定位及任务引用。

输入为手册或wheel导出的ZIP；无仓库路径依赖，不执行其中的代码。
失败抛出带有原始位置的异常；成功返回可审阅的覆盖摘要。
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
from zipfile import ZipFile
from jsonschema import Draft202012Validator


def follow(docs, target):
    """参数: docs完整Schema映射、target文件与指针。返回: 指针所指值。异常: 未解析文件/键。"""
    file, pointer = target.split("#",1)
    value = docs[file]
    for part in pointer.split("/")[1:]:
        key = part.replace("~1","/").replace("~0","~")
        value = value[int(key)] if isinstance(value,list) else value[key]
    return value


def task_references(z, language, tasks):
    """只用ZIP实际内容打开任务后续参考，并核对JSON片段和核心专题的完整段落。"""
    opened = []
    for task in tasks:
        assert not re.search(r"\S+\.(?:md|html|json|ya?ml|py)(?:\b|#)", task["requires"]), (language, task["id"], 'requires contains a file path')
        for reference in task.get("references", []):
            assert set(reference) == {"path", "description"} and all(reference.values())
            target, _, pointer = reference['path'].partition('#')
            target = posixpath.normpath(language + target)
            body = z.read(target).decode('utf8')
            if pointer:
                assert target.endswith('.json') and pointer.startswith('/')
                node = follow({target: json.loads(body)}, target + '#' + pointer)
                assert isinstance(node, dict) and node, (target, pointer)
            if target.endswith('topics/aggregations.md'):
                for term in ('group_by', 'include_partial', 'partial_policy', 'discovery_complete', 'candidate_count'):
                    assert term in body, (target, term)
            if target.endswith('topics/message-calculations.md'):
                for term in ('parameters', 'message_policy', 'split_by_sign', 'outputs.contributions'):
                    assert term in body, (target, term)
            opened.append(target + ('#' + pointer if pointer else ''))
        if task['id'] in ('POWER_STATISTICS', 'MESSAGE_ENERGY'):
            assert len(task.get('references', [])) >= 2, task['id']
    return opened


def check_result_summaries(z, names):
    """从最终ZIP独立核对每份结果摘要，不借用构建器的检查结果。

    参数: z为已打开的ZipFile，names为包内实际路径集合。
    返回: 摘要数量与被引用结果文件数量。
    异常: AssertionError，路径、文件大小或哈希不符；缺失文件读取错误传播。
    """
    summaries = count = 0
    for name in sorted(names):
        if not name.startswith('examples/results/') or not name.endswith('/result-summary.json'):
            continue
        summaries += 1
        records = json.loads(z.read(name))['files']
        assert isinstance(records, list), name
        seen = set()
        for record in records:
            relative = record['path']
            assert isinstance(relative, str) and relative and '\\' not in relative and ':' not in relative, name
            path = PurePosixPath(relative)
            assert not path.is_absolute() and '..' not in path.parts, (name, relative)
            target = str(PurePosixPath(name).parent / path)
            assert target in names and target not in seen, (name, target)
            seen.add(target)
            data = z.read(target)
            assert type(record['bytes']) is int and len(data) == record['bytes'], (target, 'bytes')
            assert sha256(data).hexdigest() == record['sha256'], (target, 'sha256')
            count += 1
    return dict(result_summaries=summaries, result_files=count)


def check(file):
    """参数: file为待验ZIP。返回: 摘要。异常: 发行内容、字段或链接与清单不符。"""
    with ZipFile(file) as z:
        names = set(z.namelist())
        assert len(names)==len(z.infolist()) and z.testzip() is None
        manifest = json.loads(z.read("manifest.json"))
        assert set(manifest["sha256"])==names-{"manifest.json"}
        for name,expected in manifest["sha256"].items():
            assert not PurePosixPath(name).is_absolute() and ".." not in PurePosixPath(name).parts
            assert sha256(z.read(name)).hexdigest()==expected, name
        result_counts = check_result_summaries(z, names)
        schemas = {n:json.loads(z.read(n)) for n in names if n.startswith("schemas/")}
        assert len(schemas)==3
        analysis_version = schemas["schemas/analysis.schema.json"]["properties"]["config_version"]
        batch_version = schemas["schemas/batch-v1.schema.json"]["properties"]["batch_version"]
        assert manifest["config_version"] == 4 and manifest["supported_config_versions"] == [4]
        assert analysis_version["type"] == "integer" and analysis_version["const"] == 4
        assert batch_version["type"] == "integer" and batch_version["const"] == 1
        # 分别用发行包里的实际约束判定版本。独立批量清单不沿用分析计划的编号。
        for declaration, supported in ((analysis_version, (4,)), (batch_version, (1,))):
            validator = Draft202012Validator(declaration)
            for candidate in (0, 1, 2, 3, 4, 5, 3.5, "3", True, None):
                expected = type(candidate) is int and candidate in supported
                assert validator.is_valid(candidate) == expected, (declaration, candidate)
        # 逐条反查原字段，校验所有约束值及条件指针；单独测量分片的实际字节量。
        shards=json.loads(z.read("fields/index.json"))["shards"]
        size,records=0,0
        visited = set()
        for shard in shards:
            data=z.read(shard["file"]); size=max(size,len(data))
            for row in json.loads(data)["fields"]:
                node=follow(schemas,row["source"])
                visited.add(row["source"])
                for key,expected in row["constraints"].items():
                    assert node[key]==expected,(row["source"],key)
                for guard in row["conditions"]:
                    follow(schemas,guard)
                records+=1
        assert size<=24_576
        # 独立从完整规范（含条件分支）枚举属性，不能用生成器自身的条数证明无遗漏。
        def property_pointers(node, pointer):
            """参数: 原节点与指针。返回: 规范声明的属性位置。异常: 输入类型错误传播。"""
            if isinstance(node, dict):
                for name in node.get("properties",{}):
                    yield pointer+"/properties/"+name.replace("~","~0").replace("/","~1")
                for name,child in node.items():
                    yield from property_pointers(child,pointer+"/"+name.replace("~","~0").replace("/","~1"))
            elif isinstance(node,list):
                for i,child in enumerate(node):
                    yield from property_pointers(child,f"{pointer}/{i}")
        defined = {p for path,node in schemas.items() for p in property_pointers(node,path+"#")}
        assert not defined-visited, sorted(defined-visited)
        # 资料包中只能出现真实可用的本地导航；公开示例不能要求仓库根目录。
        for path in (n for n in names if n.endswith(".md")):
            body=z.read(path).decode()
            assert "Docs/Current/examples/" not in body,path
            for link in re.findall(r"\[[^\]\n]*\]\(([^\s)]+)\)",body):
                target=link.split("#",1)[0]
                if target and not target.startswith(("http://","https://")):
                    assert posixpath.normpath(posixpath.join(posixpath.dirname(path),target)) in names,(path,link)
        api={r["name"] for r in json.loads(z.read("api/index.json"))["objects"]}
        tasks=json.loads(z.read("tasks.json"))["tasks"]
        assert all(t["example"] in names and set(t["api"])<=api for t in tasks)
        assert manifest["guide_revision"] == 3 and manifest["languages"]["en"] == "en/README.md"
        en_api = {r["name"] for r in json.loads(z.read("en/api/index.json"))["objects"]}
        assert en_api == api
        en_tasks = json.loads(z.read("en/tasks.json"))["tasks"]
        assert [t["id"] for t in tasks] == [t["id"] for t in en_tasks]
        for left, right in zip(tasks, en_tasks):
            assert posixpath.normpath("en/" + right["example"]) == left["example"]
            assert all(task["example"] in task["verify"] for task in (left, right)), left["id"]
            for key in ("api", "fields", "templates"):
                assert left[key] == right[key], (left["id"], key)
        zh_references = task_references(z, '', tasks)
        en_references = task_references(z, 'en/', en_tasks)
        assert zh_references == [target.removeprefix('en/') for target in en_references]
        def without_prose(value):
            """比较全部机器约束，递归排除已翻译的说明文字。"""
            if isinstance(value, dict):
                return {k: without_prose(v) for k,v in value.items()
                        if not (k in ("title", "description") and isinstance(v, str))}
            if isinstance(value, list):
                return [without_prose(v) for v in value]
            return value
        en_visited, en_records, en_size = set(), 0, 0
        for shard in json.loads(z.read("en/fields/index.json"))["shards"]:
            data = z.read("en/" + shard["file"])
            en_size = max(en_size, len(data))
            for row in json.loads(data)["fields"]:
                source = row["source"].removeprefix("../")
                node = follow(schemas, source)
                en_visited.add(source)
                for key, expected in row["constraints"].items():
                    if key not in ("title", "description"):
                        assert without_prose(node[key]) == without_prose(expected), (source, key)
                for guard in row["conditions"]:
                    follow(schemas, guard.removeprefix("../"))
                en_records += 1
        assert en_visited == visited and en_records == records and en_size <= 24_576
        return dict(**result_counts, files=len(names),tasks=len(tasks),public_objects=len(api),shards=len(shards),
                    field_records=records,defined_properties=len(defined),max_shard_bytes=size,
                    english_tasks=len(en_tasks), english_objects=len(en_api), english_field_records=en_records,
                    english_max_shard_bytes=en_size, task_references=len(zh_references)+len(en_references))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip",type=Path)
    print(json.dumps(check(parser.parse_args().zip)))
