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
import posixpath
import re
from runpy import run_path
import tomllib
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
reading_text = run_path(str(ROOT / "tools/public_docs.py"))["reading_text"]
_resource_helpers = run_path(str(ROOT / "tools/ai_resource_bytes.py"))
resource_bytes = _resource_helpers["resource_bytes"]
validate_result_summaries = _resource_helpers["validate_result_summaries"]
AUTHOR = ROOT / "Docs/AI"
CURRENT = ROOT / "Docs/Current"


def json_bytes(value):
    """参数: value为JSON兼容数据。返回: 可直接检索的UTF-8 JSON。异常: 非法值报错。"""
    # 以稳定格式保留中文，禁止非标准数值。
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def source_bytes(path):
    """参数: path为锁定资料。返回: 规范换行的文本或原始二进制。异常: 读取失败传播。"""
    data = path.read_bytes()
    # 锁定和分发共用规则；结果CSV已有大小/哈希，不能按普通说明文本转换。
    return resource_bytes(path.relative_to(ROOT).as_posix(), data)


def public_card(page, *, language="", api_names=()):
    """参数: page为Current公开页文本。返回: 面向安装用户的独立成员/参数说明。异常: 缺少公开正文时报错。"""
    # 从第一个公开锚点起保留成员说明及完整调用例；只去除源码位置等开发导航。
    page = reading_text(page)
    if '<a id="api-' not in page:
        raise ValueError("公开参考缺少成员正文")
    body = page[page.index('<a id="api-'):]
    body = re.sub(r"(?m)^(?:源码：|Source:).*\n?", "", body)
    body = re.sub(r"(?ms)^## Source locations\s*\n.*?(?=^## |\Z)", "", body)
    # 调用例的导入和代码围栏必须一起保留；围栏内的#注释不是Markdown标题。
    body = body.replace("Docs/Current/examples/", "examples/")
    body = body.replace("从仓库根目录运行", "从AI指南根目录运行（该目录包含examples子目录）")
    body = body.replace("Run from the repository root", "Run from the AI guide root (the directory containing examples)")
    # 共享注册实例例从各语言README目录执行；路径转换与代码中的目录说明一起派生。
    if language:
        body = body.replace('# Run from the manual root (the directory containing examples).',
                            '# Run from the English AI README directory (en).')
        body = body.replace('load_analysis_plan("examples/calculation-minimal.yaml", extensions=registry)',
                            'load_analysis_plan("../examples/calculation-minimal.yaml", extensions=registry)')
    else:
        body = body.replace('# 从手册根目录（包含 examples 子目录）运行。',
                            '# 从中文 AI README 所在目录运行（该目录包含 examples 子目录）。')
    # HTML仍保留这些类型链接；独立卡片不含内部参考，不承诺存在已移除的链接。
    body = body.replace('The linked lower-level types are Chinese implementation references.\n', '')
    # 卡片链接以卡片文件所在目录为起点；命令仍按各阅读入口声明的工作目录执行。
    def rewrite(match):
        """改写随包链接。参数: Markdown匹配。返回: 链接或类型名称。异常: 无；不读写文件。"""
        label, target = match.groups()
        root = "../../" if language else "../"
        if target == "../host-extensions.md":
            config_label = "configuration" if language else "配置"
            return (f"[{label}]({root}examples/temporal/host_extensions.py) "
                    f"([{config_label}]({root}examples/temporal/host-analysis.yaml))")
        if target.startswith("../examples/"):
            return f"[{label}]({root}{target.removeprefix('../')})"
        filename = target.partition('#')[0]
        if target.startswith(("#", "https://", "http://")) or filename in {name + '.md' for name in api_names}:
            return f"[{label}]({target})"
        # 未随包分发的内部源码类型保留名称，不创建悬空网页链接。
        return label
    return re.sub(r"\[([^\[\]\n]+)\]\(([^\)\n]+)\)", rewrite, body).strip()


def add_english(files, sources, meta):
    """添加英文阅读层。参数: ZIP文件映射、锁定来源、元数据。返回: 无。异常: 对应关系缺失报错。"""
    # 示例、运行器和原始规范各保留一份；英文只增加说明与可检索字段视图。
    for name in ("README.md", "workflow.md", "semantics.md", "tasks.json"):
        text = sources["Docs/AI/en/" + name].decode("utf8")
        if name.endswith(".md"):
            text = reading_text(text)
        for source, target in (
            ("../../Current/en/continuous-files.md", "topics/continuous-files.md"),
            ("../../Current/en/fast-energy.md", "topics/fast-energy.md"),
            ("../../Current/en/aggregations.md", "topics/aggregations.md"),
            ("../../Current/en/message-calculations.md", "topics/message-calculations.md"),
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
    public = json.loads(sources["Docs/Current/en/public-api.json"])["objects"]
    for item in public:
        name = item["name"]
        card = public_card(sources[f"Docs/Current/en/public-api/{name}.md"].decode("utf8"),
                           language="en/", api_names=[row["name"] for row in public])
        # 这三页沿用英文README的en工作目录；AnalysisPlan已显式声明根目录，保持其例外。
        if name in {"load_analysis_plan", "validate_analysis_plan", "explain_analysis_plan"}:
            card = card.replace('load_analysis_plan("examples/analysis.yaml")',
                                'load_analysis_plan("../examples/analysis.yaml")')
        module, symbol = item.get("import_module", "chronaxis"), item.get("import_name", name)
        files[f"en/api/{name}.md"] = (f"# {name}\n\nImport: `from {module} import {symbol}`\n\n{card}\n").encode("utf8")
        api.append(dict(name=name, import_module=module, import_name=symbol, group=item["group"], signature=item["signature"], file=f"api/{name}.md"))
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
            value["original"] = value["original"].replace("schemas/", "../schemas/", 1)
            for row in value["fields"]:
                row["source"] = row["source"].replace("schemas/", "../schemas/", 1)
                row["conditions"] = [x.replace("schemas/", "../schemas/", 1) for x in row["conditions"]]
        files["en/" + name] = json_bytes(value)


def reading_section(text, heading):
    """提取一个完整功能小节，保留子标题，排除下一同级章节。

    参数: text为已去除开发履历的Markdown，heading为包含#的完整标题行。
    返回: 从标题到下一同级或更高级标题之前的正文，不包含其他节的锚点。
    异常: ValueError表示指定标题缺失；不猜测替代章节。
    """
    lines = text.splitlines(keepends=True)
    start = next((i for i, line in enumerate(lines) if line.strip() == heading), None)
    if start is None:
        raise ValueError("专题所需章节不存在：" + heading)
    level = len(heading) - len(heading.lstrip('#'))
    end = len(lines)
    for index in range(start + 1, len(lines)):
        match = re.match(r"^(#{1,6}) ", lines[index])
        if match and len(match[1]) <= level:
            end = index
            break
    # 下一节可能在标题前带HTML锚点；它不属于当前章节。
    while end > start and (not lines[end - 1].strip() or lines[end - 1].lstrip().startswith('<a id=')):
        end -= 1
    return ''.join(lines[start:end]).rstrip() + '\n'


def add_task_topics(files, sources):
    """从锁定的双语专题生成完整阅读页；只调整分发路径，不删字段或语义正文。"""
    for language in ("", "en/"):
        en = bool(language)
        root = "../../" if en else "../"
        destinations = {
            "inputs.md": root + "schemas/analysis.schema.json#/properties/sources",
            "continuous-files.md": "continuous-files.md",
            "fast-energy.md": "fast-energy.md",
            "expressions.md": "expressions.md",
            "inputs.md#can-field": root + "schemas/analysis.schema.json#/properties/signals",
            "dataset.md": root + "schemas/analysis.schema.json#/properties/dataset/properties/domain",
            "examples.md#message-energy": "message-example.md",
            "example-results.md#power-statistics-yaml": "power-statistics-results.md",
            "results.md#v4-aggregations": "aggregation-results.md",
            "concepts.md": "../semantics.md",
            "aggregations.md": "aggregations.md",
            "intervals.md": root + "schemas/analysis.schema.json#/properties/intervals",
            "calculations.md#integrators": "integrators.md",
            "calculations.md#v4-power-statistics": "power-statistics.md",
            "execution.md": root + "schemas/analysis.schema.json#/properties/execution",
            "configuration-language.md": "#yaml-values",
        }
        pages = {name: reading_text(sources[f"Docs/Current/{language}{name}.md"].decode("utf8"))
                 for name in ("aggregations", "message-calculations", "expressions", "continuous-files")}
        # 原标签承诺的内容必须随包提供：结果链接不能仅跳到配置，选型不能仅跳到API。
        sections = (
            ("aggregation-results", "results", "## Read aggregation results" if en else "## 聚合结果怎样读"),
            ("power-statistics-results", "example-results", "## power-statistics.yaml"),
            ("message-example", "examples", "### Contributions and skipped CAN messages" if en else "### 每条CAN消息的贡献与跳过"),
            ("integrators", "calculations", "## Choose an integrator" if en else "## 积分器的选择"),
            ("power-statistics", "calculations", "## Count readings or loads, and measure power over time" if en else "## 同一次功率试验，按报文、时长或加载次数统计"),
        )
        for name, source, heading in sections:
            page = reading_text(sources[f"Docs/Current/{language}{source}.md"].decode("utf8"))
            pages[name] = reading_section(page, heading)
        fast = reading_text(sources[f"Docs/Current/{language}fast-energy.md"].decode("utf8"))
        # 先保留完整声明，再介绍替换片段和资源；拒绝表中的“上述额度”依赖这些内容。
        headings = (
            "## Single-file plan and result" if en else "## 一份配置与实际数值",
            "## Multiple volumes from one recording" if en else "## 同一次记录的多个分卷",
            "## Check a rejected request" if en else "## 配置被拒绝时",
        )
        pages["fast-energy"] = fast.split('\n## ', 1)[0] + '\n\n' + '\n\n'.join(
            reading_section(fast, heading) for heading in headings)
        for topic, body in pages.items():
            if topic == "expressions":
                # 保留整套运算/函数/单位/类型说明；准备输入和派生信号教程由任务示例承担。
                start = "## Literals, names, and parentheses" if en else "## 数字、名字和括号"
                if start not in body:
                    raise ValueError("表达式完整参考章节未找到：" + language)
                body = ("# Expression operators and types\n\n" if en else "# 表达式运算和类型参考\n\n") + body[body.index(start):]
                syntax = reading_text(sources[f"Docs/Current/{language}configuration-language.md"].decode("utf8"))
                section = "## Values, quotation marks, and expressions" if en else "## 值、引号与表达式"
                if section not in syntax:
                    raise ValueError("YAML值说明章节未找到：" + language)
                excerpt = syntax[syntax.index(section):].split('\n## ', 1)[0]
                body += '\n\n<a id="yaml-values"></a>\n' + excerpt

            def replace(match):
                """只改阅读链接的地址，保留原句中的字段、动作和条件。

                参数: match为正文中的Markdown链接。
                返回: 使用已登记分发地址、保留原标签的Markdown链接。
                异常: ValueError表示目标未登记或示例附件缺失。
                """
                label, target = match.groups()
                if target.startswith('#'):
                    return match[0]
                if target.startswith(("examples/", "../examples/")):
                    relative = target.removeprefix("../")
                    if relative not in files:
                        raise ValueError("专题示例缺少发行附件：" + relative)
                    return f"[{label}]({root}{relative})"
                if target not in destinations:
                    raise ValueError("专题新增未登记的后续阅读链接：" + target)
                # 链接文字可能是句子的一部分，例如“省略dataset.domain”；
                # 目标页面标题不能替换它，否则文件可达但条件含义已经改变。
                return f"[{label}]({destinations[target]})"

            body = re.sub(r"\[([^\]\n]+)\]\(([^)\n]+)\)", replace, body)
            directory = root + "examples/"
            note = (f"Other tasks: [task index](../tasks.json). Run example commands from the referenced configuration's directory under `{directory}`, not from this reading page's directory.\n\n"
                    if en else f"其他任务见上方入口[任务索引](../tasks.json)。下方示例命令在所引用配置文件所在目录执行；示例位于 `{directory}`，不在本阅读页目录执行。\n\n")
            body = body.replace('\n\n', '\n\n' + note, 1)
            files[f"{language}topics/{topic}.md"] = (body + "\n").encode("utf8")


def validate_task_references(files):
    """校核所有任务的结构化后续阅读文件/JSON指针，并拒绝requires中的裸文件地址。"""
    checked = 0
    normalized = {}
    for language in ("", "en/"):
        tasks = json.loads(files[language + "tasks.json"])["tasks"]
        for task in tasks:
            if re.search(r"\S+\.(?:md|html|json|ya?ml|py)(?:\b|#)", task["requires"]):
                raise ValueError("后续资料路径须放入references：" + language + task["id"])
            references = task.get("references", [])
            if not isinstance(references, list):
                raise ValueError("references必须为列表：" + task["id"])
            targets = []
            for item in references:
                if set(item) != {"path", "description"} or not all(isinstance(v, str) and v for v in item.values()):
                    raise ValueError("references需要非空path和description：" + task["id"])
                relative, _, pointer = item["path"].partition("#")
                destination = posixpath.normpath(language + relative)
                if destination not in files:
                    raise ValueError("任务后续资料缺失：" + destination)
                if pointer:
                    if not destination.endswith(".json") or not pointer.startswith("/"):
                        raise ValueError("任务片段只接受完整JSON指针：" + item["path"])
                    node = json.loads(files[destination])
                    for part in pointer.split("/")[1:]:
                        key = part.replace("~1", "/").replace("~0", "~")
                        node = node[int(key)] if isinstance(node, list) else node[key]
                    if not isinstance(node, dict):
                        raise ValueError("任务规范指针须指向定义对象：" + item["path"])
                targets.append(destination.removeprefix("en/") + ("#" + pointer if pointer else ""))
                checked += 1
            normalized[(language, task["id"])] = targets
    for (language, name), targets in normalized.items():
        if not language and normalized[("en/", name)] != targets:
            raise ValueError("双语任务引用目标不一致：" + name)
    return checked


def validate_field_references(files):
    """校核双语字段分片的全部规范定位，不只验证内层字段。

    参数: files为最终指南相对路径到bytes的映射。返回: 实际检查的指针数量。
    异常: ValueError表示文件或JSON Pointer缺失；只读内存，不改Schema。
    """
    schemas = {}
    checked = 0
    for name, content in files.items():
        language = 'en/' if name.startswith('en/') else ''
        relative = name.removeprefix(language)
        if not relative.startswith('fields/') or not relative.endswith('.json') or relative == 'fields/index.json':
            continue
        page = json.loads(content)
        references = [page['original']]
        for row in page['fields']:
            references.extend([row['source'], *row['conditions']])
        for reference in references:
            path, separator, fragment = reference.partition('#')
            target = posixpath.normpath(language + path)
            if target not in files or not target.startswith('schemas/') or not separator or (fragment and not fragment.startswith('/')):
                raise ValueError('字段规范定位无效：' + name + ' -> ' + reference)
            if target not in schemas:
                schemas[target] = json.loads(files[target])
            node = schemas[target]
            try:
                for part in fragment.split('/')[1:]:
                    key = part.replace('~1', '/').replace('~0', '~')
                    if isinstance(node, list):
                        if not re.fullmatch(r'0|[1-9][0-9]*', key):
                            raise ValueError('数组定位必须为规范的非负整数')
                        node = node[int(key)]
                    else:
                        node = node[key]
            except (KeyError, IndexError, ValueError, TypeError) as error:
                raise ValueError('字段JSON Pointer无效：' + name + ' -> ' + reference) from error
            checked += 1
    return checked


def validate_api_links(files):
    """检查独立API卡片保留的链接及锚点。

    参数: files为最终分发映射。返回: 本地链接数量。异常: ValueError表示目标缺失。
    链接相对于卡片本身，不把中文/英文命令的工作目录当作Markdown解析起点。
    """
    checked = 0
    for name, data in files.items():
        if not name.endswith('.md') or not name.startswith(('api/', 'en/api/')):
            continue
        for target in re.findall(r'\[[^\[\]\n]+\]\(([^)\n]+)\)', data.decode('utf8')):
            if target.startswith(('https://', 'http://')):
                continue
            path, _, fragment = target.partition('#')
            destination = posixpath.normpath(posixpath.dirname(name) + '/' + path) if path else name
            if destination not in files:
                raise ValueError('API卡片链接缺少随包文件：' + name + ' -> ' + target)
            if fragment and f'id="{fragment}"' not in files[destination].decode('utf8'):
                raise ValueError('API卡片锚点不存在：' + name + ' -> ' + target)
            checked += 1
    return checked


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
    if sorted(exports) != sorted(row["name"] for row in public if row.get("import_module", "chronaxis") == "chronaxis"):
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
                ("../Current/continuous-files.md", "topics/continuous-files.md"),
                ("../Current/fast-energy.md", "topics/fast-energy.md"),
                ("../Current/aggregations.md", "topics/aggregations.md"),
                ("../Current/message-calculations.md", "topics/message-calculations.md"),
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
        card = public_card(sources[f"Docs/Current/public-api/{name}.md"].decode(),
                           api_names=[row["name"] for row in public])
        module, symbol = item.get("import_module", "chronaxis"), item.get("import_name", name)
        files[rel] = (f"# {name}\n\n推荐导入：`from {module} import {symbol}`\n\n{card}\n").encode()
        api.append(dict(name=name, import_module=module, import_name=symbol, group=item["group"], signature=item["signature"], file=rel))
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
    if any(set(t["api"])-{row["name"] for row in public} or set(t["templates"])-templates for t in tasks):
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
    add_task_topics(files, sources)
    validate_task_references(files)
    validate_field_references(files)
    validate_api_links(files)
    validate_result_summaries(files)
    files["manifest.json"] = json_bytes(dict(package="chronaxis", package_version=version,
        guide_revision=3, languages={"zh": "README.md", "en": "en/README.md"},
        config_version=4, supported_config_versions=[4], product_baseline=meta["baseline"], manual_revision=lock["manual_revision"],
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
