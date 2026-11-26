"""核对用户文档中可照抄的Python调用与实际公开签名一致，防止文档把方法参数写成构造参数。

输入是手册、AI指南与README的Markdown；只取行内代码和python代码块中能解析为Python且调用公开类、
公开函数或公开类方法的片段，用`inspect.signature`核对关键字名与位置参数个数。
不执行被核对的代码，不读取分析输入；占位写法（`...`、`*args`）跳过位置个数。
文字描述没有代码形式时本工具无法判断，应先改写成代码再核对。
2026-11-25 | [school] BUG-DEV6-001；liuyaoze。
"""
from __future__ import annotations

import argparse
import ast
import importlib
import inspect
import json
from pathlib import Path
import re
import sys
import warnings

ROOT = Path(__file__).resolve().parents[1]
FENCE = re.compile(r'^(?P<mark>```+|~~~+)\s*(?P<lang>[\w+-]*)[^\n]*\n(?P<body>.*?)^(?P=mark)\s*$', re.M | re.S)
SPAN = re.compile(r'(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)')


def public_objects():
    """取公开名称对应的类与函数。参数: 无。返回: {名称: 对象}。异常: 导入公开入口失败时传播。"""
    import chronaxis
    found = {}
    for name in chronaxis.__all__:
        item = getattr(chronaxis, name)
        if inspect.isclass(item) or inspect.isfunction(item):
            found[name] = item
    return found


def documents(root=ROOT):
    """列出需要核对的用户文档。参数: 仓库根。返回: 路径列表（不含生成参考与构建目录）。异常: 无。"""
    paths = []
    for pattern in ('README.md', 'README.en.md', 'Docs/Current/*.md', 'Docs/Current/en/*.md',
                    'Docs/AI/*.md', 'Docs/AI/en/*.md'):
        paths += sorted(root.glob(pattern))
    return paths


def snippets(text):
    """取行内代码与python代码块。参数: Markdown文本。返回: [(行号, 片段)]；行号从1开始。异常: 无。

    代码块先取出并从正文移除，避免块内反引号被当作行内代码；保留换行以维持行号。
    """
    found, kept = [], text
    for match in FENCE.finditer(text):
        line = text.count('\n', 0, match.start()) + 2
        if match.group('lang').lower() in ('python', 'py', 'pycon'):
            found.append((line, match.group('body')))
    kept = FENCE.sub(lambda m: '\n' * m.group(0).count('\n'), text)
    for match in SPAN.finditer(kept):
        found.append((kept.count('\n', 0, match.start()) + 1, match.group(2)))
    return found


def parse(code):
    """把片段解析为语法树；with头等不完整语句补占位。参数: 片段。返回: ast.AST或None（不是Python时）。"""
    for candidate in (code, code.rstrip() + '\n    pass'):
        try:
            with warnings.catch_warnings():
                # 说明文字里的反斜杠不是本工具核对的内容，不把它当作警告输出。
                warnings.simplefilter('ignore', SyntaxWarning)
                return ast.parse(candidate)
        except SyntaxError:
            continue
    return None


def page_objects(codes, objects):
    """按页面代码中的导入覆盖同名公开对象，避免把其他模块的同名函数当作顶层公开接口。

    参数: 本页全部片段、公开对象。返回: 本页使用的{名称: 对象}。异常: 无，导入失败的名称从核对中移除。
    """
    result = dict(objects)
    for code in codes:
        tree = parse(code)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.level or not (node.module or '').startswith('chronaxis.'):
                continue
            for alias in node.names:
                if alias.name not in objects:
                    continue
                name = alias.asname or alias.name
                try:
                    item = getattr(importlib.import_module(node.module), alias.name)
                except (ImportError, AttributeError):
                    result.pop(name, None)
                    continue
                if item is not objects[alias.name]:
                    result[name] = item
    return result


def resolve(node, objects, variables):
    """求调用目标的可检查签名对象。参数: ast.Call、公开对象、变量到类的映射。返回: (名称, 签名或None)或None。

    签名为None表示公开类没有该方法；返回None表示不是公开调用，不核对。
    """
    func = node.func
    if isinstance(func, ast.Name):
        target = objects.get(func.id)
        return None if target is None else (func.id, inspect.signature(target))
    if not isinstance(func, ast.Attribute):
        return None
    owner, cls = func.value, None
    if isinstance(owner, ast.Call) and isinstance(owner.func, ast.Name):
        cls = objects.get(owner.func.id)
    elif isinstance(owner, ast.Name):
        cls = variables.get(owner.id, objects.get(owner.id))
    if not inspect.isclass(cls):
        return None
    label = f'{cls.__name__}.{func.attr}'
    member = inspect.getattr_static(cls, func.attr, None)
    if member is None:
        return label, None
    if isinstance(member, (classmethod, staticmethod)):
        # 类方法与静态方法从类上取得时已不含首个参数。
        return label, inspect.signature(getattr(cls, func.attr))
    if not inspect.isfunction(member):
        return None
    parameters = list(inspect.signature(member).parameters.values())[1:]
    return label, inspect.signature(member).replace(parameters=parameters)


def check_call(node, signature):
    """核对一次调用的关键字名与位置个数。参数: ast.Call、签名。返回: 错误文本或None。"""
    positional, placeholder = [], False
    for arg in node.args:
        if isinstance(arg, ast.Starred) or (isinstance(arg, ast.Constant) and arg.value is Ellipsis):
            placeholder = True
        else:
            positional.append(None)
    keywords = {}
    for item in node.keywords:
        if item.arg is None:
            placeholder = True
        else:
            keywords[item.arg] = None
    parameters = signature.parameters.values()
    variadic = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters)
    if not variadic:
        unknown = [name for name in keywords if name not in signature.parameters
                   or signature.parameters[name].kind is inspect.Parameter.POSITIONAL_ONLY]
        if unknown:
            return '不支持关键字参数：' + '、'.join(unknown)
    if placeholder:
        return None
    try:
        signature.bind_partial(*positional, **keywords)
    except TypeError as error:
        return str(error)
    return None


def check_text(text, objects):
    """核对一段Markdown。参数: 文本、公开对象。返回: [(行号, 调用, 错误)]。异常: 无。"""
    problems, codes = [], snippets(text)
    objects = page_objects([code for _, code in codes], objects)
    for line, code in codes:
        tree = parse(code)
        if tree is None:
            continue
        variables = {}
        for node in ast.walk(tree):
            # 片段内“变量 = 公开类(...)”让后续的变量.方法(...)也能核对。
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
                cls = objects.get(node.value.func.id)
                if inspect.isclass(cls):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            variables[target.id] = cls
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            found = resolve(node, objects, variables)
            if found is None:
                continue
            name, signature = found
            if signature is None:
                problems.append((line + node.lineno - 1, name, '公开类没有这个方法'))
                continue
            error = check_call(node, signature)
            if error is not None:
                problems.append((line + node.lineno - 1, name, error))
    return problems


def main(argv=None):
    """核对默认文档并打印JSON摘要。参数: 可选命令行。返回: 0通过，1有不符。异常: 文件读取错误传播。"""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('paths', nargs='*', type=Path, help='可选，只核对指定Markdown')
    args = parser.parse_args(argv)
    objects, problems = public_objects(), {}
    paths = args.paths or documents()
    for path in paths:
        found = check_text(Path(path).read_text(encoding='utf-8'), objects)
        if found:
            problems[str(path)] = found
    print(json.dumps(dict(documents=len(paths), objects=len(objects), problems=problems), ensure_ascii=False, indent=1))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
