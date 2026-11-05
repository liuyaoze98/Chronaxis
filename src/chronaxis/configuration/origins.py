"""按请求说明定义或叶字段来自哪个配置文件；不作为执行计划的持久状态。

只读主配置与明确的一层公共定义，先复用静态校验再生成小型来源记录。
默认报告定义位置及来源文件路径；fields模式列全部显式叶字段，不虚构默认值来源。
不读取ASC/BLF/CSV中的数据记录；校验可能读取显式DBC以补齐信号元数据。
不写报告文件；调用者决定显示或重定向。
"""
from pathlib import Path

from . import load_configuration
from .imports import expand_document_imports
from .file_tools import validate_document
from .models import field_path_text


def _at(data, path):
    """读取存在的字段，跳过展开后已删除的imports位置。参数: 原生树/tuple路径。返回: (存在,值)。异常: 无。"""
    current=data
    for key in path:
        if type(current) is dict and key in current:current=current[key]
        elif type(current) is list and type(key) is int and 0<=key<len(current):current=current[key]
        else:return False,None
    return True,current


def _record(document, path, name=None):
    """复制一项有限来源事实。参数: 文档、路径、可选定义名。返回: dict。异常: 无。"""
    origin=document.origin_for(path)
    location=origin.location if origin else document.location_for(path)
    return dict(name=name,effective_path=field_path_text(path),
                declared_path=field_path_text(origin.field_path if origin else path),
                file=origin.source if origin else document.source,
                line=None if location is None else location.line,
                column=None if location is None else location.column)


def configuration_origins(source, *, fields=False):
    """读取实际定义或叶字段的声明位置。参数: 配置路径、是否逐字段。返回: 来源报告dict。异常: 配置/读取错误。

    分析配置列其定义；批量只列本文件的任务，不读取子计划。省略的默认字段
    不在报告内。fields只保位置而不复制值；路径声明单独说明最终指向。
    """
    path=Path(source).absolute()
    document=expand_document_imports(load_configuration(path))
    kind=validate_document(document,path.parent)
    items=[]
    if fields:
        for parts in document.locations:
            exists,value=_at(document.data,parts)
            if exists and type(value) not in (dict,list):items.append(_record(document,parts))
    else:
        analysis=document.data
        if kind=='batch' and 'template' in analysis:
            item=_record(document,('template',),'template')
            item['resolved_paths']=[str((path.parent/analysis['template']).absolute())]
            items.append(item)
            items.append(_record(document,('inputs',),'inputs'))
        sections=('jobs',) if kind=='batch' else ('sources','signals','derived')
        for section in sections:
            values=analysis.get(section,{} if section=='derived' else [])
            entries=values.items() if section=='derived' else enumerate(values)
            for key,value in entries:
                if section=='signals' and 'signals' in value:
                    for child_index,child in enumerate(value['signals']):
                        items.append(_record(document,(section,key,'signals',child_index),child['name']))
                    continue
                name=key if section=='derived' else value.get('name')
                item=_record(document,(section,key),name)
                # 文件位置只按已知路径字段说明；metadata内路径文字不解释。
                if section=='sources':
                    from ..planning.input_paths import source_path_fields
                    declared=[owner[key] for owner,key in source_path_fields(value)]
                    declared.extend(value.get('dbc_by_channel',{}).values())
                    item['resolved_paths']=[str((path.parent/entry).absolute()) for entry in declared]
                elif section=='jobs':item['resolved_paths']=[str((path.parent/value['plan']).absolute())]
                items.append(item)
    return dict(configuration=str(path),configuration_type=kind,
                scope='fields' if fields else 'definitions',items=items)


def render_origins(report):
    """将有限来源记录显示为中文文本。参数: configuration_origins报告。返回: str。异常: 内部报告结构错误。"""
    lines=['配置来源：'+report['configuration'],
           '只列显式声明；未读取数据记录。批量任务的子配置需单独查看。']
    for item in report['items']:
        place=item['file']
        if item['line'] is not None:place+=f":{item['line']}:{item['column']}"
        lines.append(item['effective_path']+' ← '+place+' '+item['declared_path'])
        for path in item.get('resolved_paths',[]):lines.append('  文件路径：'+path)
    return '\n'.join(lines)+'\n'
