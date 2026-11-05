"""从完整参考提取公开对象视图，内部方法仍保留在模块参考。

输入公开清单、AST清单和已渲染参考；输出public-api目录，不修改来源模块文档。
"""
from pathlib import Path
import re
import json
import os
from public_api_notes import NOTES, render_note

SPECIAL={'__init__','__enter__','__exit__','__iter__','__next__'}


def members(root, objects):
    """参数: 根对象名及模块对象记录。返回: 根及直接公开成员。异常: 无。"""
    result=[]
    for obj in objects:
        name=obj['name']
        if name==root:result.append(name)
        elif name.startswith(root+'.'):
            tail=name[len(root)+1:]
            if '.' not in tail and (not tail.startswith('_') or tail in SPECIAL):result.append(name)
    return result


def public_page(item, record, content, routes, anchor):
    """参数: 公开声明、模块记录、参考正文、路由和锚点函数。返回: 页面文本。异常: 缺正文报错。"""
    chosen=members(item['qualified'],record['objects'])
    sections={}
    markers=list(re.finditer(r'<a id="(api-[^"]+)"></a>',content))
    for i,m in enumerate(markers):
        end=markers[i+1].start() if i+1<len(markers) else len(content)
        sections[m[1]]=re.split(r'\n## (?:内部匿名回调|变更履历)',content[m.start():end],maxsplit=1)[0]
    selected={anchor(name) for name in chosen}
    module, symbol = item.get('import_module', 'chronaxis'), item.get('import_name', item['name'])
    out=[f'# {module}.{symbol}\n\n使用`from {module} import {symbol}`导入。本页只列直接公开成员与必要的构造/上下文协议；内部实现见[模块参考](../reference/{record["module"]}.md)。\n\n',
         '返回[公开API索引](../api.md)。参数表中的类型可跳转到定义；先核对必填、默认值与返回/异常说明。\n\n',
         '## 成员导航\n\n'+ '\n'.join(f'- [`{name}`](#{anchor(name)})' for name in chosen)+'\n\n']
    def rewrite(m):
        """参数: Markdown目标。返回: 保持公开路由或明确指向开发参考。异常: 无。"""
        target=m[1]
        if target.startswith('#'):
            return ']('+target+')' if target[1:] in selected else ']('+ '../reference/'+record['module']+'.md'+target+')'
        key=target if not target.startswith('../') else None
        if key in routes:return ']('+routes[key]+')'
        if re.match(r'^[\w.-]+\.md(?:#|$)',target):return '](../reference/'+target+')'
        return m[0]
    for name in chosen:
        key=anchor(name)
        if key not in sections:raise ValueError('公开对象没有参考正文：'+item['name']+'.'+name)
        out.append(re.sub(r'\]\(([^)]+)\)',rewrite,sections[key]))
    return ''.join(out)


def build_public(doc, public, records, anchor):
    """参数: Docs版本目录、公开清单、模块清单、锚点函数。返回: 页数。异常: I/O或缺定义。"""
    output=doc/'public-api';output.mkdir(exist_ok=True)
    by_module={r['module']:r for r in records};routes={}
    for item in public['objects']:
        record=by_module[item['module']]
        for name in members(item['qualified'],record['objects']):routes[item['module']+'.md#'+anchor(name)]=item['name']+'.md#'+anchor(name)
    for item in public['objects']:
        record=by_module[item['module']];content=(doc/'reference'/(item['module']+'.md')).read_text(encoding='utf8')
        text=public_page(item,record,content,routes,anchor)
        if item['name'] in NOTES:
            text = render_note(item, text, 'zh')
        metadata=json.loads((doc/'documentation.json').read_text(encoding='utf8'))
        if os.environ.get('CHRONAXIS_DOC_SOURCE_TREE') != '1':
            text+='\n## 变更履历\n\n'+f'- {metadata["updated_at"]} | {metadata["task"]} | 从固定源码{metadata["baseline"]}生成公开视图；liuyaoze。\n'
        else:
            # 与公开导出的正文使用相同结尾，避免仅空行差异触发发行摘要漂移。
            text = text.rstrip()+'\n'
        (output/(item['name']+'.md')).write_text(text,encoding='utf8',newline='\n')
    return len(public['objects'])
