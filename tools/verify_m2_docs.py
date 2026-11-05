"""独立核对所选版本文档清单、源码定义、参数与本地导航。

只读取固定Git对象和所选Docs版本，不导入生成器或产品。检查全部具名定义及显式参数、
类字段、默认值、模块哈希、文档锚点、链接和快速上手JSON。输出小型JSON证据到
_build，不用结构通过替代人工语义审阅或实际运行验证。
"""

import ast
import copy
import argparse
from doc_sources import DocSources
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / 'Docs/M2'


class InventoryVisitor(ast.NodeVisitor):
    """独立收集限定名与节点，不复用文档生成器的遍历算法。

    stack保存当前词法作用域，objects保存所有类/函数定义；离开作用域后恢复栈。
    """

    def __init__(self):
        """初始化本模块专用状态。

        参数: 无。返回: None。异常: 分配错误原样传播。
        """
        self.stack, self.objects = [], {}

    def visit_ClassDef(self, node):
        """登记类及其内部定义。

        参数: node为类AST。返回: None。异常: 重复限定名触发AssertionError。
        """
        self._record(node)

    def visit_FunctionDef(self, node):
        """登记函数及嵌套定义。

        参数: node为函数AST。返回: None。异常: 重复限定名触发AssertionError。
        """
        self._record(node)

    def visit_AsyncFunctionDef(self, node):
        """登记异步函数，保持同一覆盖口径。

        参数: node为异步函数AST。返回: None。异常: 重复限定名触发AssertionError。
        """
        self._record(node)

    def _record(self, node):
        """进入定义作用域后递归，退出时恢复父作用域。

        参数: node为有name的定义AST。返回: None。异常: 重名/分配等错误传播。
        """
        self.stack.append(node.name)
        name = '.'.join(self.stack)
        assert name not in self.objects, name
        self.objects[name] = node
        self.generic_visit(node)
        self.stack.pop()


def main():
    """核对文档覆盖与本地文件链接，保存事实统计并在失败时退出非零。

    参数: 无。返回: None。异常: 任一覆盖/链接/配置差异抛AssertionError；I/O错误传播。
    副作用: 写入_build/coverage.json，不修改手册或基线。
    """
    # 只切换待核对目录；事实仍由独立AST遍历从固定Git对象重新提取。
    global DOC
    parser = argparse.ArgumentParser(description='独立检查版本化手册的接口覆盖及链接')
    parser.add_argument('--edition', choices=('M2', 'M3', 'Current'), default='M2')
    DOC = ROOT / 'Docs' / parser.parse_args().edition
    manifest = json.loads((DOC / 'reference/inventory.json').read_text(encoding='utf-8'))
    revision = manifest['baseline']
    sources = DocSources(ROOT, revision, DOC.name)
    actual_paths = sources.paths()
    actual_paths = {p for p in actual_paths if p.endswith('.py')}
    assert actual_paths == {m['path'] for m in manifest['modules']}
    counts = dict(modules=0, classes=0, functions=0, parameters=0, fields=0, exports=0, links=0, pages=0, lambdas=0)
    explanations = json.loads((DOC / 'annotations.json').read_text(encoding='utf-8'))
    # 比较独立AST事实与机器清单，再检查每个定义和参数确实出现在相应参考页。
    for module in manifest['modules']:
        source = sources.text(module['path'])
        assert hashlib.sha256(source.encode()).hexdigest() == module['sha256'], module['path']
        tree = ast.parse(source)
        visitor = InventoryVisitor()
        visitor.visit(tree)
        records = {obj['name']: obj for obj in module['objects']}
        assert set(visitor.objects) == set(records), module['module']
        page = (DOC / 'reference' / (module['module'] + '.md')).read_text(encoding='utf-8')
        counts['modules'] += 1
        counts['exports'] += len(module['exports'])
        counts['lambdas'] += sum(isinstance(n, ast.Lambda) for n in ast.walk(tree))
        for node in (n for n in ast.walk(tree) if isinstance(n, ast.Lambda)):
            assert f'id="lambda-{node.lineno}"' in page and ast.unparse(node) in page
        for name, node in visitor.objects.items():
            record = records[name]
            if DOC.name in ('M3', 'Current'):
                # 每项只检查自己的定义区；同页其他函数中的同名参数不能代替本项说明。
                marker = '<a id="api-' + name.replace('.', '-') + '"></a>'
                block_start = page.index(marker)
                block_end = page.find('\n<a id=', block_start + len(marker))
                block = page[block_start:block_end if block_end >= 0 else len(page)]
                category = 'fields' if isinstance(node, ast.ClassDef) else 'parameters'
                items = record.get(category, [])
                supplied = explanations.get(module['module'] + '.' + name, {}).get(category, {})
                # 人工说明必须对应实际字段，避免改名后旧说明留存却没有显示出来。
                assert set(supplied) <= {item['name'] for item in items}, (name, 'stale explanation')
                descriptions = []
                for item in items:
                    if DOC.name == 'Current' and category == 'parameters' and item['name'] in ('self', 'cls'):
                        # 接收者仍保留在机器清单，用户参数表不要求手动传入。
                        continue
                    # 单元格内部竖线由生成器转义，因此五列可独立计数并检查缺项。
                    prefix = '|`' + item['name'] + '`|'
                    matches = [line for line in block.splitlines() if line.startswith(prefix)]
                    assert len(matches) == 1, (name, item['name'], 'missing or duplicate row')
                    cells = matches[0].strip('|').split('|')
                    assert len(cells) == 5 and all(cell.strip() for cell in cells), (name, item['name'], cells)
                    assert not any(text in cells[4] for text in ('原说明没有单独解释', '须满足本行所述内容', '具体角色见本行用途')), (name, item['name'])
                    assert 'object（此接口未限定类' not in cells[1], (name, item['name'], 'missing type review')
                    if item['name'] not in ('self', 'cls'):
                        descriptions.append(cells[4])
                # 同一段话重复填入几个字段不是逐项解释，回到人工说明处拆分。
                assert len(descriptions) == len(set(descriptions)), (name, 'combined parameter descriptions')
            assert record['line'] == node.lineno
            assert f'id="api-{name.replace(".", "-")}"' in page
            if isinstance(node, ast.ClassDef):
                counts['classes'] += 1
                fields = []
                for item in node.body:
                    if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        fields.append(item.target.id)
                    elif isinstance(item, ast.Assign) and all(isinstance(t, ast.Name) for t in item.targets):
                        fields.extend(t.id for t in item.targets)
                assert fields == [item['name'] for item in record['fields']], name
                # 字段名相同仍可能默认值过期；独立比较类型及赋值表达式。
                declarations = {}
                for item in node.body:
                    if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        declarations[item.target.id] = (ast.unparse(item.annotation), ast.unparse(item.value) if item.value is not None else '必填')
                    elif isinstance(item, ast.Assign) and all(isinstance(t, ast.Name) for t in item.targets):
                        for target in item.targets:
                            declarations[target.id] = ('', ast.unparse(item.value))
                for field in record['fields']:
                    assert (field['type'], field['default']) == declarations[field['name']], (name, field['name'])
                counts['fields'] += len(fields)
                for field in fields:
                    assert f'|`{field}`|' in page
            else:
                counts['functions'] += 1
                args = node.args
                names = [a.arg for a in args.posonlyargs + args.args]
                if args.vararg:
                    names.append(args.vararg.arg)
                names.extend(a.arg for a in args.kwonlyargs)
                if args.kwarg:
                    names.append(args.kwarg.arg)
                assert names == [item['name'] for item in record['parameters']], name
                if DOC.name == 'Current':
                    if any(ast.unparse(d) == 'property' for d in node.decorator_list):
                        assert f'{name}()' not in block, name
                        assert name + (': ' + ast.unparse(node.returns) if node.returns else '') in block
                    else:
                        display_args = copy.deepcopy(args)
                        positional = display_args.posonlyargs or display_args.args
                        if positional and positional[0].arg in ('self', 'cls'):
                            positional.pop(0)
                        assert f'{name}({ast.unparse(display_args)})' in block, name
                else:
                    assert f'{name}({ast.unparse(args)})' in page
                # 参数表的类型也要与源码一致；完整签名已同时核对默认值与传参方式。
                arguments = args.posonlyargs + args.args + args.kwonlyargs
                arguments += [a for a in (args.vararg, args.kwarg) if a is not None]
                annotations = {a.arg: ast.unparse(a.annotation) if a.annotation else '' for a in arguments}
                for parameter in record['parameters']:
                    assert parameter['type'] == annotations[parameter['name']], (name, parameter['name'])
                counts['parameters'] += len(names)
                for parameter in names:
                    if DOC.name == 'Current' and parameter in ('self', 'cls'):
                        continue
                    assert f'|`{parameter}`|' in page
        for exported in module['exports']:
            assert f'`{exported}`' in page
    # 限定检查本手册；外部历史记录只检查目标文件，避免把旧导航误算成新页验收。
    for path in sorted(DOC.rglob('*.md')):
        if '_build' in path.parts:
            continue
        counts['pages'] += 1
        text = path.read_text(encoding='utf-8')
        from check_current_html import fenced_blocks
        fenced_blocks(text)
        # 英文页采用独立译文来源清单，不要求复制中文维护履历；正文和链接仍逐页校核。
        english_page = DOC.name == 'Current' and path.relative_to(DOC).parts[0] == 'en'
        if not sources.tree and not english_page:
            assert 'liuyaoze' in text and '变更履历' in text, path
        # JSON schema中的正则可能长得像Markdown链接；代码围栏不参与导航解析。
        prose = re.sub(r'^(`{3,}|~{3,})[^\n]*\n.*?^\1\s*$', '', text, flags=re.M | re.S)
        for url in re.findall(r'\[[^\]\n]+\]\(([^)\n]+)\)', prose):
            if '://' in url:
                continue
            target, _, fragment = url.partition('#')
            target_path = (path.parent / target.strip('<>')).resolve() if target else path
            assert target_path.exists(), (path, url)
            if fragment.startswith('api-'):
                assert f'id="{fragment}"' in target_path.read_text(encoding='utf-8'), (path, url)
            counts['links'] += 1
    guide = (DOC / 'quickstart.md').read_text(encoding='utf-8')
    if DOC.name == 'Current':
        from ruamel.yaml import YAML
        config = YAML(typ='safe').load(re.search(r'```yaml\n(.*?)\n```', guide, re.S).group(1))
        assert config == YAML(typ='safe').load((DOC / 'examples/analysis.yaml').read_text(encoding='utf-8'))
    else:
        config = json.loads(re.search(r'```json\n(.*?)\n```', guide, re.S).group(1))
    assert config == json.loads((DOC / 'examples/analysis.json').read_text(encoding='utf-8'))
    missing = json.loads((DOC / '_build/unresolved-parameters.json').read_text(encoding='utf-8'))
    assert not missing, missing
    result = {'device_label': 'home', 'baseline': revision, 'checked_at': datetime.now(timezone(timedelta(hours=8))).isoformat(),
              'status': 'passed', 'counts': counts, 'parameter_review_gaps': len(missing),
              'scope': '具名定义/显式参数/声明字段全覆盖；lambda表达式另计，未伪造公共函数名'}
    (DOC / '_build/coverage.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


# 直接调用才运行验证；不在导入时访问Git或写证据。
if __name__ == '__main__':
    main()
