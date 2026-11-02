"""从随包四份完整规范生成可查字段视图；不实现第二个配置验证器。

读取同一输入映射里的本地JSON Schema，记录精确指针、父级必填及变体条件。
遇到坏引用直接构建失败，跨规范引用保留目标文档身份；不访问网络。
"""
import json
from pathlib import PurePosixPath

DOCS = {"analysis.schema.json":"analysis", "batch-v1.schema.json":"batch",
        "definitions.schema.json":"definitions", "legacy-import-v1.schema.json":"mapping"}
KEYS = ("type","const","enum","default","description","examples","minimum","exclusiveMinimum",
        "maximum","exclusiveMaximum","minLength","maxLength","minItems","maxItems","pattern","$ref")
COMBINE = ("oneOf","anyOf","allOf","if","then","else","not","dependentRequired","dependentSchemas")


def escape(part):
    """参数: part为字段名。返回: 经过JSON Pointer转义的片段。异常: 非文本输入。"""
    return part.replace("~","~0").replace("/","~1")


def fields_for(schemas, doc, pointer, node, path, required, conditions=(), visited=()):
    """参数: 规范集合、当前规范/指针/对象/公开路径、父必填及条件与祖先。返回: 字段记录迭代器。异常: 坏指针。"""
    if not isinstance(node, dict) or (doc,pointer) in visited:
        return
    # required仅表示直接父对象约束；条件、互斥及外层必填通过规范指针查阅。
    identity = "schemas/" + doc + "#" + pointer
    guards = (*conditions, *(identity+"/"+k for k in COMBINE if k in node))
    yield dict(path=path, source=identity, required_in_parent=required,
               constraints={k:node[k] for k in KEYS if k in node}, conditions=list(guards))
    seen = (*visited, (doc,pointer))
    if "$ref" in node:
        # 解析本地引用；输入规范被锁定，未知目标或网络地址不能进入离线发行。
        name, _, ref = node["$ref"].partition("#")
        name = name or doc
        target = schemas[name]
        for key in ref.split("/")[1:]:
            key = key.replace("~1","/").replace("~0","~")
            target = target[int(key)] if isinstance(target,list) else target[key]
        yield from fields_for(schemas,name,ref,target,path,required,guards,seen)
    for key, child in node.get("properties",{}).items():
        yield from fields_for(schemas,doc,pointer+"/properties/"+escape(key),child,path+"."+key,
                              key in node.get("required",()),guards,seen)
    # 列表、字典自定义键及条件分支可在同一逻辑路径给出不同约束；保留全部结果。
    for key in ("items","additionalProperties"):
        if isinstance(node.get(key), dict):
            yield from fields_for(schemas,doc,pointer+"/"+key,node[key],path if key=="items" else path+".*",
                                  None,guards,seen)
    for key, child in node.get("patternProperties",{}).items():
        yield from fields_for(schemas,doc,pointer+"/patternProperties/"+escape(key),child,path+".*",None,guards,seen)
    for key in ("oneOf","anyOf","allOf"):
        for i, child in enumerate(node.get(key,[])):
            yield from fields_for(schemas,doc,f"{pointer}/{key}/{i}",child,path,required,guards,seen)
    for key in ("if","then","else","not"):
        if isinstance(node.get(key), dict):
            yield from fields_for(schemas,doc,pointer+"/"+key,node[key],path,required,guards,seen)


def views(files, encode, label):
    """参数: files为包内容，encode为JSON编码器，label为资料来源。返回: 无（补充视图）。异常: 缺规范等传播。"""
    schemas = {doc:json.loads(files["schemas/"+doc]) for doc in DOCS}
    shards = []
    for doc, kind in DOCS.items():
        schema = schemas[doc]
        for topic,node in schema["properties"].items():
            base = "/properties/"+escape(topic)
            choices = node.get("items",{}).get("oneOf",[])
            # 来源、规则及预设按公开类型切分；公共上层约束始终指回原规范。
            selections = [(base,node,"all")]
            if choices:
                selections = []
                for i,child in enumerate(choices):
                    properties = child.get("properties",{})
                    label_key = next((k for k in ("source_type","rule_type","preset_type") if k in properties),None)
                    tag = properties[label_key].get("const") if label_key else None
                    selections.append((f"{base}/items/oneOf/{i}", child, tag or f"variant-{i+1}"))
            for pointer,child,branch in selections:
                guards = ["schemas/"+doc+"#/"+key for key in COMBINE if key in schema]
                if choices:
                    guards.extend(["schemas/"+doc+"#"+base,"schemas/"+doc+"#"+base+"/items/oneOf"])
                records = list(fields_for(schemas,doc,pointer,child,topic,
                                          topic in schema.get("required",()),guards))
                # 用字节而不是条目数限制阅读量；优先保留同一参数的每个适用分支。
                pages = [[]]
                size = 0
                for row in records:
                    cost = len(encode(row)) + 180
                    if pages[-1] and size + cost > 16_384:
                        pages.append([])
                        size = 0
                    pages[-1].append(row)
                    size += cost
                for i,page in enumerate(pages):
                    name = f"fields/{kind}/{topic}-{branch}-{i+1}.json"
                    if name in files or PurePosixPath(name).parent != PurePosixPath("fields",kind):
                        raise ValueError("分片路径重复或不合法：" + name)
                    files[name] = encode(dict(device_label=label, schema=kind, topic=topic, branch=branch,
                                              original="schemas/"+doc+"#"+base, fields=page))
                    if len(files[name]) > 24_576:
                        raise ValueError("字段分片超过24KiB，请检查该字段的说明：" + name)
                    shards.append(dict(schema=kind,topic=topic,branch=branch,file=name,
                                       names=sorted({r["path"].split(".")[-1].casefold() for r in page})))
    files["fields/index.json"] = encode(dict(device_label=label,
        use="只辅助阅读。required_in_parent不是所有场景都必填，需结合分支、引用及完整计划检查。",
        shards=shards))
