"""从指定版本的固定Git对象生成完整Markdown参考，不修改产品代码。

输入为BASELINE下src/chronaxis的Python源文件及schema；输出在Docs/<版本>/reference，
清单记录文件哈希、定义、参数和字段，供独立覆盖检查。AST遍历包含私有、嵌套、
property和vendor定义；模块导出另列。人工教程不由本脚本覆盖。只读取Git对象，
不读取RefProjects、不执行reader、不混入工作区未提交或后续修改。Current公开签名
在隔离子进程中导入选定源码反射；其余模块只作AST分析。重复构建结果相同。
"""

import ast
import copy
import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from doc_type_links import imports as type_imports, type_cell
from doc_public_api import build_public
from doc_sources import DocSources
from public_api_catalog import refresh as refresh_public_catalog

# 固定接受本次M2范围，不把HEAD变化自动解释为手册升级。
ROOT = Path(__file__).resolve().parents[1]
BASELINE = '911ceef'
OUT = ROOT / 'Docs/M2/reference'
STAMP = '2026-10-22T21:07:29+08:00'
LABEL = 'home'
TASK = 'DOC-CURRENT-03'
EDITION = 'M2'
DOC = ROOT / 'Docs' / EDITION
LANGUAGE = {}
PUBLIC_SIGNATURES = {}
TYPE_LOCATIONS = {}
TYPE_IMPORTS = {}
SOURCES = None
SECTIONS = ('参数', '返回', '异常', '处理流程', '副作用', '边界与示例', '边界', '流程', '约束')
LAYER_GUIDES = {
    'core': ('时序与数值核心', '../concepts.md'),
    'execution': ('执行与历史回读', '../architecture.md'),
    'planning': ('配置解析与静态检查', '../configuration.md'),
    'sources': ('数据来源与批次', '../inputs.md'),
    'results': ('结果、预算与发布', '../results.md'),
    'legacy': ('旧链封装与逐消息累计', '../migration.md'),
    'migration': ('旧INI导入', '../migration.md'),
    'timebase': ('时间换算', '../concepts.md'),
}


def git_text(path):
    """读取固定提交的UTF-8文件，不受当前工作区内容影响。

    参数: path为仓库相对路径。返回: 解码后的文本。异常: Git读取失败或编码错误传播。
    """
    return SOURCES.text(path) if SOURCES is not None else subprocess.check_output(['git', 'show', f'{BASELINE}:{path}'], cwd=ROOT).decode('utf-8-sig')


def cell(text):
    """转义Markdown表格内容，保留换行和类型联合符号。

    参数: text为字符串或可显示对象。返回: 单个表格单元文本。异常: 原字符串转换错误传播。
    """
    return str(text).replace('|', '&#124;').replace('\n', '<br>').replace('\r', '')


def plain(text):
    """将已人工核对的固定短语改成普通中文，不触碰代码签名。

    参数: text为说明文字。返回: 使用统一词义的说明。异常: 无。
    """
    for old, new in LANGUAGE['phrases'].items():
        text = text.replace(old, new)
    return text


def module_terms(source):
    """按模块实际出现的词提供就近解释，不要求读者先理解内部术语。

    参数: source为固定基线模块文本。返回: Markdown术语表。异常: 无。
    """
    found = [item for item in LANGUAGE['terms'] if any(word in source for word in item['needles'])]
    if not found:
        return ''
    return ('## 本页术语\n\n|词语|在这个项目中的意思|\n|---|---|\n'
            + ''.join(f"|{cell(item['name'])}|{cell(item['description'])}|\n" for item in found)
            + '\n需要更多例子时见[术语解释](../terms.md)、[运行参数](../execution.md)与[表达式完整说明](../expressions.md)。\n\n')


def anchor(name):
    """给嵌套定义生成明确HTML锚点，避免依赖阅读器的中文标题规则。

    参数: name为模块内限定名称。返回: ASCII定义锚点。异常: 无。
    """
    return 'api-' + name.replace('.', '-')


def call_signature(name, node, qualified=''):
    """生成调用签名；实例接收者不作为用户参数，属性不显示调用括号。

    参数: name为限定对象名；node为AST定义；qualified用于查询经核对的公开构造签名。
    返回: 签名文本。异常: AST解析错误传播；不导入产品或推断继承构造器。
    """
    if isinstance(node, ast.ClassDef):
        if qualified in PUBLIC_SIGNATURES:
            return name + PUBLIC_SIGNATURES[qualified]
        constructor = next((x for x in node.body if isinstance(x, ast.FunctionDef) and x.name == '__init__'), None)
        if constructor:
            return call_signature(name, constructor)
        # 内部类声明只列真实基类；不把字段列表猜成完整构造签名。
        bases = ', '.join(ast.unparse(x) for x in node.bases)
        return f'class {name}' + (f'({bases})' if bases else '')
    decorators = [ast.unparse(x) for x in node.decorator_list]
    if 'property' in decorators:
        return name + (': ' + ast.unparse(node.returns) if node.returns else '')
    args = copy.deepcopy(node.args)
    candidates = args.posonlyargs or args.args
    if candidates and candidates[0].arg in ('self', 'cls'):
        candidates.pop(0)
    signature = name + '(' + ast.unparse(args) + ')'
    if node.returns:
        signature += ' -> ' + ast.unparse(node.returns)
    return signature


def split_doc(doc):
    """拆分原中文说明的参数、返回、异常等段落，支持同一行多个标题。

    参数: doc为AST提取的docstring。返回: 标题到说明映射及概述。异常: 无。
    """
    pattern = r'(' + '|'.join(SECTIONS) + r')\s*[:：]'
    parts = re.split(pattern, doc)
    result = {'概述': parts[0].strip()}
    for position in range(1, len(parts), 2):
        title, body = parts[position], parts[position + 1].strip()
        result[title] = (result.get(title, '') + '\n' + body).strip()
    return result


def parameters(node):
    """枚举全部显式参数及传参方式，保留位置限定、关键字限定与可变参数。

    参数: node为函数AST。返回: 名称/类型/默认值/种类字典列表。异常: AST结构错误传播。
    """
    args = node.args
    positional = args.posonlyargs + args.args
    defaults = [None] * (len(positional) - len(args.defaults)) + list(args.defaults)
    result = []
    # None在此表示语法上没有默认值；字面量None本身是ast.Constant，二者明确区分。
    for index, (arg, default) in enumerate(zip(positional, defaults)):
        result.append({'name': arg.arg, 'type': ast.unparse(arg.annotation) if arg.annotation else '',
                       'default': ast.unparse(default) if default is not None else '必填',
                       'kind': '仅位置' if index < len(args.posonlyargs) else '位置或关键字'})
    for arg, kind, default in [(args.vararg, '可变位置', '()')]:
        if arg is not None:
            result.append({'name': arg.arg, 'type': ast.unparse(arg.annotation) if arg.annotation else '',
                           'default': default, 'kind': kind})
    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        result.append({'name': arg.arg, 'type': ast.unparse(arg.annotation) if arg.annotation else '',
                       'default': ast.unparse(default) if default is not None else '必填', 'kind': '仅关键字'})
    if args.kwarg is not None:
        arg = args.kwarg
        result.append({'name': arg.arg, 'type': ast.unparse(arg.annotation) if arg.annotation else '',
                       'default': '{}', 'kind': '可变关键字'})
    return result


def describe_parameter(name, section, overrides, qualified):
    """将具体参数和原说明对应；语义补充优先于旧注释，缺项留给审核而不猜。

    参数: name参数名；section原参数段；overrides人工补充表；qualified完整对象名。
    返回: 说明文本及是否缺少对应说明。异常: 无。
    """
    supplied = overrides.get(qualified, {}).get('parameters', {}).get(name)
    if supplied:
        return supplied['description'] if isinstance(supplied, dict) else supplied, False
    if name in ('self', 'cls'):
        return ('当前实例，调用obj.method(...)时由Python传入。' if name == 'self'
                else '当前类，调用类方法时由Python传入。'), False
    # 正式参数段常换行续写。取到下一项参数为止，不能只显示名称所在的第一行。
    names_pattern = (r'\*{0,2}[A-Za-z_][A-Za-z0-9_]*(?:[/、][A-Za-z_][A-Za-z0-9_]*)*'
                     if EDITION in ('M3', 'Current') else r'\*{0,2}[A-Za-z_][A-Za-z0-9_]*')
    headings = list(re.finditer(
        r'(?m)^[ \t]*(' + names_pattern + r')(?:[ \t]*\([^\n]*?\))?[ \t]*[:：][ \t]*', section))
    for index, heading in enumerate(headings):
        if name in re.split(r'[/、]', heading.group(1).lstrip('*')):
            end = headings[index + 1].start() if index + 1 < len(headings) else len(section)
            return ' '.join(section[heading.end():end].split()), False
    # 短句组说明保留整组；先接回折行，再按分号划分，避免丢失句子后半段。
    pieces = re.split(r'[；;]', ' '.join(section.splitlines()))
    matches = [piece.strip() for piece in pieces if re.search(r'(?<![A-Za-z0-9_])' + re.escape(name) + r'(?![A-Za-z0-9_])', piece)]
    if matches:
        description = '；'.join(matches)
        # 只重复参数名不是解释；M3把这类历史短注释交回人工补充。
        return description, EDITION in ('M3', 'Current') and re.search(r'[\u4e00-\u9fff]', description) is None
    return section or '原说明没有单独解释此参数；调用位置与源码见下方。', True


def documented_item(item, override, node, *, is_field=False):
    """分开显示调用要求和源码默认表达式，保留原清单供独立AST核对。

    参数: item为AST条目；override为逐项人工说明；node为定义节点；is_field区分类成员。
    返回: 类型、必填、默认三个展示单元；不修改item中的源码证据。
    异常: 人工说明结构或字段表达式错误时传播KeyError、TypeError或SyntaxError。
    """
    supplied = override.get('fields' if is_field else 'parameters', {}).get(item['name'], {})
    supplied = supplied if isinstance(supplied, dict) else {}
    typename = supplied.get('type') or item['type']
    required = '是' if item['default'] == '必填' else '否'
    default = supplied.get('default', item['default'] if item['default'] != '必填' else '无')
    if item['name'] in ('self', 'cls') and not is_field:
        return ('当前实例' if item['name'] == 'self' else '当前类', '不手动传入', 'Python自动传入')
    if is_field and not any('dataclass' in ast.unparse(d) for d in node.decorator_list):
        required = '类成员，不作为构造参数填写'
        typename = typename or ('枚举成员' if any(ast.unparse(base).endswith(('Enum', 'IntFlag')) for base in node.bases) else '类属性')
    if is_field and item['default'].startswith('field('):
        # field(repr=False)仍可能没有默认值；只有default或default_factory才可省略。
        declaration = ast.parse(item['default'], mode='eval').body
        options = {entry.arg: entry.value for entry in declaration.keywords}
        if 'default' in options:
            default = ast.unparse(options['default'])
            required = '否'
        elif 'default_factory' in options:
            factory = ast.unparse(options['default_factory'])
            default = {'tuple': '()', 'list': '[]', 'dict': '{}', 'set': 'set()'}.get(factory, '调用 ' + factory + '() 生成')
            required = '否'
        else:
            required, default = '是', '无'
    if 'init=False' in item['default']:
        required, default = '不填写', '构造时计算'
    if is_field and any('dataclass' in ast.unparse(d) and 'init=False' in ast.unparse(d) for d in node.decorator_list):
        # 类自定义构造流程时，字段表展示对象内容，真正传参以__init__签名为准。
        required, default = '不直接填写', '由自定义构造器建立；见 __init__'
    if not typename:
        # Python接口未写类型注解时，只使用可核对的默认值，不猜名称对应的业务类型。
        try:
            value = ast.literal_eval(item['default'])
            if value is not None:
                typename = type(value).__name__
        except (ValueError, SyntaxError):
            pass
    return typename or 'object（此接口未限定类，具体要求见用途）', supplied.get('required', required), default


def definitions(tree):
    """递归枚举全部具名类和函数，包括条件分支与函数内部定义。

    参数: tree为模块AST。返回: (限定名, AST节点)列表。异常: 无。
    """
    result = []
    stack = [(child, '') for child in reversed(list(ast.iter_child_nodes(tree)))]
    while stack:
        node, prefix = stack.pop()
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            prefix = f'{prefix}.{node.name}' if prefix else node.name
            result.append((prefix, node))
        stack.extend((child, prefix) for child in reversed(list(ast.iter_child_nodes(node))))
    return result


def fields(node, lines):
    """提取类字段、枚举成员及其就近中文说明。

    参数: node为类AST；lines为源文件行列表。返回: 字段声明和说明列表。异常: 无。
    """
    result = []
    for item in node.body:
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            names = [item.target.id]
            annotation = ast.unparse(item.annotation)
            value = ast.unparse(item.value) if item.value else '必填'
        elif isinstance(item, ast.Assign) and all(isinstance(t, ast.Name) for t in item.targets):
            names = [target.id for target in item.targets]
            annotation, value = '', ast.unparse(item.value)
        else:
            continue
        # 字段后的注释优先；无行尾注释时借用直接相邻注释，不扫描其他定义。
        line = lines[item.end_lineno - 1]
        comment = line.split('#', 1)[1].strip() if '#' in line else ''
        if not comment and item.lineno > 1 and lines[item.lineno - 2].strip().startswith('#'):
            comment = lines[item.lineno - 2].strip().lstrip('#').strip()
        for name in names:
            result.append({'name': name, 'type': annotation, 'default': value, 'description': comment})
    return result


def history():
    """生成本轮文档履历；固定时间用于确定性重建，不伪造每次重新审阅。

    参数: 无。返回: Markdown履历。异常: 无。
    """
    if SOURCES is not None and SOURCES.tree:
        return ''
    if EDITION == 'Current':
        return f'\n## 变更履历\n\n- {STAMP} | {TASK} | 从{BASELINE}生成当前签名与释义；liuyaoze。\n'
    if EDITION != 'M2':
        return (f'\n## 变更履历\n\n|记录|时间|任务|说明|修改者|\n|---|---|---|---|---|\n'
                f'|{EDITION}-REF-1|2026-10-23T19:20:29+08:00|DOC-{EDITION}-01|按{BASELINE}建立完整参考；原始源码与签名保持该基线|liuyaoze|\n'
                f'|{EDITION}-REF-3|2026-10-23T22:27:00+08:00|DOC-{EDITION}-03|分列类型、必填、默认与用途；拆分合并参数说明，补选值、空值和资源含义|liuyaoze|\n'
                f'|{EDITION}-REF-4|{STAMP}|DOC-{EDITION}-04|按用途和实际结果改写模块、参数与返回说明，补具体异常条件；签名保持固定基线|liuyaoze|\n')
    return (f'\n## 变更履历\n\n|记录|时间|任务|说明|修改者|\n|---|---|---|---|---|\n'
            f'|M2-REF-1|{STAMP}|DOC-M2-01|从{BASELINE}静态提取，人工补充见annotations.json|liuyaoze|\n'
            '|M2-REF-2|2026-10-22T22:20:18+08:00|DOC-M2-02|按用户反馈补术语、改写抽象句；人工解释替换主说明，源码和签名保持基线|liuyaoze|\n')


def render_module(path, source, overrides):
    """把模块说明、每个定义和参数表写为一份可链接的参考页。

    参数: path源码路径；source固定版本正文；overrides人工解释。返回: 页面文本、机器清单、待审参数。
    异常: Python语法或说明结构异常传播。副作用: 无文件写入。
    """
    tree = ast.parse(source)
    module = path.removeprefix('src/').removesuffix('.py').replace('/', '.')
    module = module.removesuffix('.__init__')
    layer = module.split('.')[1] if '.' in module else 'root'
    aliases = type_imports(source, module, package=path.endswith('/__init__.py'))
    title, guide = LAYER_GUIDES.get(layer, ('公开入口与命令行', '../api-usage.md'))
    if EDITION == 'Current' and layer in ('legacy', 'migration'):
        # 当前共用CAN读取层保留；旧版手册的迁移入口不改写为新版本行为。
        title, guide = 'CAN读取与逐报文计算', '../inputs.md'
    doc = ast.get_docstring(tree) or overrides.get(module, {}).get('summary', '')
    header = f'# {module}\n\n> {EDITION} `{BASELINE}` · device_label: {LABEL} · {title}\n\n'
    intro = overrides.get(module, {}).get('summary', '')
    out = [header, plain(intro or doc) + '\n\n',
           f'先读[使用场景]({guide})，返回[模块索引](index.md)。\n\n',
           '**阅读说明：** 下列签名和默认值来自固定版本源码。完整说明保留返回值、异常和资源约束。'
           '下划线/嵌套对象用于理解实现，不作为稳定调用承诺；自动生成的数据类方法不重复展开，计算字段与普通构造字段在表中区分。'
           + ('类型记法及必填列见[如何读参数表](../api-usage.md#api-table-reading)。' if EDITION in ('M3', 'Current') else '')
           + '旧docstring中的任务编号表示编写时点；当前可用能力见[能力表](../status.md)。\n\n', module_terms(source)]
    if EDITION == 'Current':
        # 模块标识符中的双下划线不能被Markdown当作强调标记吞掉。
        out = [f'# `{module}`\n\n', plain(intro or doc) + '\n\n',
               '这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。'
               '签名来自固定源码，公开类构造签名经实际Python接口核对。\n\n']
    if intro and doc and intro != doc and EDITION not in ('M3', 'Current'):
        out += ['<details><summary>原代码模块说明（供维护者核对）</summary>\n\n', plain(doc), '\n\n</details>\n\n']
    symbols = definitions(tree)
    out += ['## 对象导航\n\n|对象|用途|\n|---|---|\n']
    for name, node in symbols:
        brief = overrides.get(module + '.' + name, {}).get('summary') or split_doc(ast.get_docstring(node) or '')['概述'].split('\n')[0]
        # 导航只放首段；完整解释和例子留在对象正文，避免整段说明挤进导航表。
        if EDITION in ('M3', 'Current'):
            brief = brief.split('\n', 1)[0]
        out.append(f'|[`{name}`](#{anchor(name)})|{cell(plain(brief))}|\n')
    # __all__列明重导出对象；导入语句保留真实来源，用户无需猜测根包别名。
    exports = []
    imports = []
    for item in tree.body:
        if isinstance(item, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '__all__' for t in item.targets):
            exports = ast.literal_eval(item.value)
        if isinstance(item, ast.ImportFrom):
            imports.append(ast.unparse(item))
    if exports:
        out += ['\n## 导出名称\n\n', ', '.join(f'`{e}`' for e in exports) + '\n\n',
                '重导出保持定义位置的签名；按上级[总索引](index.md)查找对象名。\n']
        if EDITION == 'Current':
            out.append('\n公开重导出按[公开API索引](../api.md)查询定义、用途和调用示例。\n')
    if imports:
        out += ['\n<details><summary>导入与重导出来源（展开）</summary>\n\n```python\n',
                '\n'.join(imports), '\n```\n\n</details>\n']
    inventory = {'module': module, 'path': path, 'sha256': hashlib.sha256(source.encode()).hexdigest(),
                 'exports': exports, 'objects': []}
    unresolved = []
    lines = source.splitlines()
    for name, node in symbols:
        qualified = module + '.' + name
        record = {'name': name, 'kind': 'class' if isinstance(node, ast.ClassDef) else 'function', 'line': node.lineno}
        sections = split_doc(ast.get_docstring(node) or '')
        level = '###' if EDITION == 'Current' and '.' in name else '##'
        detail_level = level + '#'
        out += [f'\n<a id="{anchor(name)}"></a>\n{level} `{name}`\n\n']
        override = overrides.get(qualified, {})
        # 人工核对可修正旧说明中的具体限制，原始代码仍从冻结源码页查阅。
        sections.update({key: override[key] for key in SECTIONS if key in override})
        overview = plain(override.get('summary') or sections['概述'])
        out += [overview + '\n\n']
        record['summary'] = overview.split('\n')[0]
        if isinstance(node, ast.ClassDef):
            bases = ', '.join(ast.unparse(base) for base in node.bases)
            signature = f'class {node.name}' + (f'({bases})' if bases else '')
            record['fields'] = fields(node, lines)
            record['bases'] = [ast.unparse(base) for base in node.bases]
        else:
            signature = f'{name}({ast.unparse(node.args)})'
            if node.returns:
                signature += ' -> ' + ast.unparse(node.returns)
            record['parameters'] = parameters(node)
            record['decorators'] = [ast.unparse(d) for d in node.decorator_list]
        if EDITION == 'Current':
            signature = call_signature(name, node, qualified)
        out += ['```python\n' + signature + '\n```\n\n']
        if EDITION == 'Current' and isinstance(node, ast.ClassDef) and node.bases:
            # 继承字段不冒充本类新增字段；给出可达的完整基类字段入口。
            inherited = ', '.join(type_cell(ast.unparse(base),module,aliases,TYPE_LOCATIONS,TYPE_IMPORTS) for base in node.bases)
            out += ['继承关系：' + inherited + '。下表列本类声明的字段；基类字段及其约束见对应类型链接。\n\n']
        if record.get('decorators'):
            out += ['装饰器：' + ', '.join(f'`{d}`' for d in record['decorators']) + '。\n\n']
        items = record.get('parameters', record.get('fields', []))
        if EDITION == 'Current' and not isinstance(node, ast.ClassDef):
            items = [item for item in items if item['name'] not in ('self', 'cls')]
        if items:
            out += [detail_level + ' ' + ('属性与数据字段' if isinstance(node, ast.ClassDef) and EDITION == 'Current' else '构造字段与类成员' if isinstance(node, ast.ClassDef) else '参数') + '\n\n',
                    ('|名称|数据类型|必填|省略时的值|用途、取值和效果|\n|---|---|---|---|---|\n' if EDITION in ('M3', 'Current')
                     else '|名称|类型注解|默认值|说明|\n|---|---|---|---|\n')]
            for item in items:
                if isinstance(node, ast.ClassDef):
                    supplied = override.get('fields', {}).get(item['name'])
                    description = (supplied.get('description') if isinstance(supplied, dict) else supplied) or item['description']
                    if not description:
                        # 类概述描述整个对象，不能冒充某个同名字段的独立用途。
                        if EDITION == 'Current':
                            description, missing = '此字段尚缺独立说明；请核对源码及审核清单。', True
                        else:
                            description, missing = describe_parameter(item['name'], sections['概述'], overrides, qualified)
                        if missing:
                            unresolved.append(qualified + ':' + item['name'])
                else:
                    description, missing = describe_parameter(item['name'], sections.get('参数', ''), overrides, qualified)
                    if missing:
                        unresolved.append(qualified + ':' + item['name'])
                    description = f"{item['kind']}。{description}"
                if EDITION in ('M3', 'Current'):
                    typename, required, default = documented_item(item, override, node, is_field=isinstance(node, ast.ClassDef))
                    shown_type = type_cell(typename,module,aliases,TYPE_LOCATIONS,TYPE_IMPORTS) if EDITION=='Current' else typename
                    out.append(f"|`{item['name']}`|{cell(shown_type)}|{cell(required)}|{cell(default)}|{cell(plain(description))}|\n")
                else:
                    out.append(f"|`{item['name']}`|{cell(item['type'] or '源码未注解；见说明')}|`{cell(item['default'])}`|{cell(plain(description))}|\n")
        elif not isinstance(node, ast.ClassDef):
            out += [('读取属性，不使用调用括号。\n\n' if EDITION == 'Current' and 'property' in record.get('decorators', []) else '参数：无显式参数。\n\n')]
        for title in SECTIONS:
            if sections.get(title):
                # 逐参数表已经给出完整解释；保留原段落供核对，不重复展示缩写式参数串。
                if EDITION in ('M3', 'Current') and title == '参数' and items:
                    # 原参数缩写在冻结源码链接中可核对，用户页不重复展示容易误读的合并句。
                    continue
                out += [f'\n{detail_level} {title}说明\n\n', plain(sections[title]) + '\n']
        if EDITION=='Current' and isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.returns:
            out += ['\n返回类型：'+cell(type_cell(ast.unparse(node.returns),module,aliases,TYPE_LOCATIONS,TYPE_IMPORTS))+'。\n']
        if override.get('example'):
            out += [f'\n{detail_level} 调用示例\n\n```python\n', override['example'], '\n```\n']
        # 链到当前仓库源文件时显式附基线行号，网页另提供冻结源文件以避开M3偏移。
        out += [f'\n源码：[`{path}:{node.lineno}`](../../../{path}#L{node.lineno})（行号属于 `{BASELINE}`）。\n']
        inventory['objects'].append(record)
    # 匿名排序/分组键没有公共名称，以源码行定位并允许逐个补充解释。
    lambdas = [node for node in ast.walk(tree) if isinstance(node, ast.Lambda)]
    inventory['lambdas'] = []
    if lambdas:
        out += ['\n## 内部匿名回调\n\n']
    for node in lambdas:
        params = parameters(node)
        inventory['lambdas'].append({'line': node.lineno, 'parameters': params, 'expression': ast.unparse(node)})
        explanation = overrides.get(f'{module}.lambda@{node.lineno}', {})
        out += [f'\n<a id="lambda-{node.lineno}"></a>\n### 第{node.lineno}行匿名函数\n\n',
                '```python\n' + ast.unparse(node) + '\n```\n\n',
                '|参数|含义|返回/异常|\n|---|---|---|\n']
        for param in params:
            description = explanation.get('parameter', '参数按上方签名传入；具体调用语义尚待补充。')
            result = explanation.get('result', '返回值由上方表达式决定；具体用途和异常尚待核对，不据模板推断。')
            out += [f"|`{param['name']}`|{cell(description)}|{cell(result)}|\n"]
    out += [history()]
    return ''.join(out), inventory, unresolved


def schema_reference(schema):
    """递归列出schema的每个属性与约束，结构分支通过JSON路径定位。

    参数: schema为固定版本JSON schema。返回: 完整字段Markdown。异常: JSON结构错误传播。
    """
    out = [f'# 配置字段完整参考\n\n> 基线{BASELINE}；device_label: {LABEL}。\n\n',
           '先读[配置教程](../configuration.md)。JSON路径含`$defs`的条目是可复用结构；'
           '`$ref`指向这些结构。schema描述形状，运行能力由计划解析和AnalysisRunner校验决定，不能据枚举值推断已接线。\n\n']
    stack = [('$', schema)]
    while stack:
        path, node = stack.pop()
        if not isinstance(node, dict):
            continue
        constraints = {key: value for key, value in node.items()
                       if key not in ('properties', '$defs', 'definitions', 'items', 'oneOf', 'anyOf', 'allOf')}
        if constraints:
            out += [f'## `{path}`\n\n```json\n', json.dumps(constraints, ensure_ascii=False, indent=2), '\n```\n\n']
        for key in ('properties', '$defs', 'definitions'):
            for name, value in reversed(list(node.get(key, {}).items())):
                stack.append((path + '.' + key + '.' + name, value))
        if 'items' in node:
            stack.append((path + '.items', node['items']))
        for key in ('oneOf', 'anyOf', 'allOf'):
            for index, branch in reversed(list(enumerate(node.get(key, [])))):
                stack.append((f'{path}.{key}[{index}]', branch))
    return ''.join(out) + history()


def main():
    """生成所选版本全部模块参考、完整对象索引、schema和可机读清单。

    参数: 无。返回: None。异常: Git、语法、文件或未读懂说明等错误保留给调用者。
    副作用: 仅写所选Docs版本的reference和_build中的审阅清单，不修改人工手册或产品。
    """
    # 版本由调用者明确指定；元数据固定Git提交，避免当前HEAD变化悄悄改变手册。
    global EDITION, DOC, OUT, BASELINE, STAMP, LABEL, TASK, LANGUAGE, PUBLIC_SIGNATURES, TYPE_LOCATIONS, TYPE_IMPORTS, SOURCES
    parser = argparse.ArgumentParser(description='从固定Git版本生成完整API参考')
    parser.add_argument('--edition', choices=('M2', 'M3', 'Current'), default='M2')
    EDITION = parser.parse_args().edition
    DOC = ROOT / 'Docs' / EDITION
    OUT = DOC / 'reference'
    if EDITION != 'M2':
        metadata = json.loads((DOC / 'documentation.json').read_text(encoding='utf-8'))
        BASELINE, STAMP, LABEL = metadata['baseline'], metadata['updated_at'], metadata['device_label']
        TASK = metadata['task']
    LANGUAGE = json.loads((DOC / 'reference-language.json').read_text(encoding='utf-8'))
    if EDITION == 'Current':
        # 先验证来源，再由同一基线反射签名；根导出与公开子模块统一建索引。
        DocSources(ROOT, BASELINE, EDITION)
        public = refresh_public_catalog(ROOT, BASELINE,
                                        source_tree=os.environ.get('CHRONAXIS_DOC_SOURCE_TREE') == '1')
        PUBLIC_SIGNATURES = {item['module'] + '.' + item['qualified']: item['signature']
                             for item in public['objects'] if item.get('signature')}
    OUT.mkdir(parents=True, exist_ok=True)
    overrides = json.loads((DOC / 'annotations.json').read_text(encoding='utf-8'))
    SOURCES = DocSources(ROOT, BASELINE, EDITION)
    paths = SOURCES.paths()
    # 先取得完整限定名和真实导入，再渲染链接；禁止把threading.Event按短名猜成业务Event。
    sources={path:git_text(path) for path in paths if path.endswith('.py')}
    # 生成页以本次模块清单为准，删除已从产品中移除的旧模块页。
    expected_pages = {path.removeprefix('src/').removesuffix('.py').replace('/', '.')
                      .removesuffix('.__init__') + '.md' for path in sources}
    for old_page in OUT.glob('chronaxis.*.md'):
        if old_page.name not in expected_pages:
            old_page.unlink()
    TYPE_LOCATIONS={};TYPE_IMPORTS={}
    for path,source in sources.items():
        module=path.removeprefix('src/').removesuffix('.py').replace('/','.').removesuffix('.__init__')
        TYPE_IMPORTS[module]=type_imports(source,module,package=path.endswith('/__init__.py'))
        for name,node in definitions(ast.parse(source)):
            if isinstance(node,ast.ClassDef):TYPE_LOCATIONS[module+'.'+name]=module+'.md#'+anchor(name)
    records, unresolved = [], []
    index = [f'# {EDITION}完整API参考\n\n> 固定源码基线{BASELINE}；device_label: {LABEL}。\n\n',
             '覆盖包内全部Python模块、类、手写方法、函数、私有/嵌套函数、构造字段和参数。'
             '测试、示例、tools不是包API，见[示例索引](../examples.md)及[维护说明](../maintenance.md)。'
             'vendor模块原样保留，只在本参考解释；不包含RefProjects及未跟踪的同步冲突副本。\n\n',
             '用户优先从[公开API用法](../api-usage.md)开始；需要修改内部实现时再按包查找。'
             '源码无类型注解时不会伪造签名，业务类型/单位以说明为准。\n\n',
             '## 模块\n\n|模块|职责|定义数|\n|---|---|---|\n']
    for path in paths:
        if not path.endswith('.py'):
            continue
        source = sources[path]
        text, record, missing = render_module(path, source, overrides)
        # 网页使用相同冻结源码及哈希，避免Node子进程权限影响并防止混入工作区修改。
        frozen = DOC / '_build/source' / path
        frozen.parent.mkdir(parents=True, exist_ok=True)
        frozen.write_text(source, encoding='utf-8', newline='')
        filename = record['module'] + '.md'
        (OUT / filename).write_text(text, encoding='utf-8', newline='\n')
        records.append(record)
        unresolved.extend(missing)
        first = (overrides.get(record['module'], {}).get('summary') or ast.get_docstring(ast.parse(source)) or '原样旧链模块；见页面说明').split('\n')[0]
        index.append(f"|[{record['module']}]({filename})|{cell(plain(first))}|{len(record['objects'])}|\n")
    # 明确继承字段入口；基类名不唯一时保留限定范围而不猜一个错误链接。
    class_locations = {}
    for record in records:
        for obj in record['objects']:
            if obj['kind'] == 'class':
                class_locations.setdefault(obj['name'], []).append((record['module'], obj))
    for record in records:
        inherited = []
        for obj in record['objects']:
            for base in obj.get('bases', []):
                matches = class_locations.get(base, [])
                if len(matches) == 1 and matches[0][1]['fields']:
                    module_name, base_obj = matches[0]
                    inherited.append(f"- `{obj['name']}`同时继承[{base}]({module_name}.md#{anchor(base)})字段：" + ', '.join(f"`{item['name']}`" for item in base_obj['fields']) + '。构造时须一并提供基类的必填字段；类型、默认值及约束按基类表。\n')
        if inherited:
            page = OUT / (record['module'] + '.md')
            page.write_text(page.read_text(encoding='utf-8').replace('\n## 对象导航', '\n## 继承字段\n\n' + ''.join(inherited) + '\n## 对象导航'), encoding='utf-8', newline='\n')
        if EDITION == 'Current':
            page = OUT / (record['module'] + '.md')
            content = page.read_text(encoding='utf-8')
            related = []
            for typename in sorted(TYPE_IMPORTS.get(record['module'],{})):
                linked=type_cell(typename,record['module'],TYPE_IMPORTS[record['module']],TYPE_LOCATIONS,TYPE_IMPORTS)
                if linked!=typename and re.search(r'\b'+re.escape(typename)+r'\b',content):related.append(linked)
            if related:
                content = content.replace('\n## 对象导航', '\n## 相关类型\n\n' + '、'.join(related) + '\n\n## 对象导航', 1)
                page.write_text(content, encoding='utf-8', newline='\n')
    index += ['\n## 全部对象（按限定名称）\n\n|对象|种类|\n|---|---|\n']
    for record in records:
        for obj in record['objects']:
            index.append(f"|[`{record['module']}.{obj['name']}`]({record['module']}.md#{anchor(obj['name'])})|{obj['kind']}|\n")
    (OUT / 'index.md').write_text(''.join(index) + history(), encoding='utf-8', newline='\n')
    (OUT / 'configuration-schema.md').write_text(schema_reference(json.loads(git_text('Docs/Schema/analysis.schema.json' if EDITION == 'Current' else 'Docs/Schema/analysis-v1.schema.json'))), encoding='utf-8', newline='\n')
    manifest = {'baseline': SOURCES.revision(),
                'device_label': LABEL, 'modules': records}
    (OUT / 'inventory.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if EDITION=='Current':build_public(DOC,public,records,anchor)
    build = DOC / '_build'
    build.mkdir(exist_ok=True)
    (build / 'unresolved-parameters.json').write_text(json.dumps(unresolved, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'modules': len(records), 'objects': sum(len(m['objects']) for m in records),
                      'parameters_needing_review': len(unresolved)}, ensure_ascii=False))


# 直接调用才写参考页；被验证脚本导入时仅暴露纯构建函数。
if __name__ == '__main__':
    main()
