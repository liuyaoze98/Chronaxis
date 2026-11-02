"""按源码导入作用域生成类型链接；不以同名类猜测绑定。

输入为冻结源码和已知定义位置，输出Markdown类型单元。仅静态分析，不导入产品。
"""
import ast
import re

STANDARD={'threading.Event':'https://docs.python.org/3.12/library/threading.html#event-objects',
          'pathlib.Path':'https://docs.python.org/3.12/library/pathlib.html#pathlib.Path'}


def imports(source, module, *, package=False):
    """参数: 源码、限定模块、是否包入口。返回: 无歧义名称映射。异常: 语法错误传播。"""
    candidates={}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node,ast.ImportFrom):
            parts=module.split('.') if package else module.split('.')[:-1]
            prefix='.'.join(parts[:len(parts)-node.level+1]) if node.level else ''
            origin='.'.join(x for x in (prefix,node.module) if x)
            for item in node.names:
                if item.name!='*':candidates.setdefault(item.asname or item.name,set()).add(origin+'.'+item.name)
        elif isinstance(node,ast.Import):
            for item in node.names:candidates.setdefault(item.asname or item.name.split('.')[0],set()).add(item.name if item.asname else item.name.split('.')[0])
    return {name:next(iter(values)) for name,values in candidates.items() if len(values)==1}


def resolve(name,module,aliases,locations,all_imports):
    """参数: 类型名及导入/定义索引。返回: (完整名称,链接)或None。异常: 无。"""
    first,_,tail=name.partition('.')
    qualified=aliases.get(first,first)+('.'+tail if tail else '')
    if first not in aliases and module+'.'+name in locations:qualified=module+'.'+name
    # 静态重导出最多追十六层；循环或不明确时保留原文本。
    seen=set()
    for _ in range(16):
        if qualified in locations:return qualified,locations[qualified]
        if qualified in STANDARD:return qualified,STANDARD[qualified]
        if qualified in seen:break
        seen.add(qualified)
        owner,_,local=qualified.rpartition('.')
        target=all_imports.get(owner,{}).get(local)
        if not target:break
        qualified=target
    return None


def type_cell(text,module,aliases,locations,all_imports):
    """参数: 类型文本及静态上下文。返回: 保留组合类型的Markdown。异常: 无。"""
    def link(match):
        """参数: 单个类型词。返回: 已确认链接或原词。异常: 无。"""
        token=match[0];found=resolve(token,module,aliases,locations,all_imports)
        if not found:return token
        full,target=found;label=token
        if token=='Q' and full.endswith('.QualityFlag'):label='QualityFlag（源码别名Q）'
        elif full=='threading.Event':label='threading.Event'
        return f'[{label}]({target})'
    return re.sub(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*',link,text)
