"""展开明确列出的一层本地公共定义，供分析文件和INI映射文件加载使用。

主配置按imports顺序引入sources/signals/derived，最后追加本地声明；重复名称
直接拒绝。导入文件不能再导入文件，也不能声明运行、规则或输出字段。
仅打开配置文件，数据/DBC路径按各自声明文件转为词法绝对路径；不读取业务输入。
位置随本次加载保留，成功计划不持有原文或第二份配置，不执行环境替换或模板。
"""
from copy import deepcopy
from pathlib import Path
from types import MappingProxyType

from . import load_configuration
from .diagnostics import locate_error
from .models import ConfigurationDocument, ConfigurationOrigin, field_path_text

SECTIONS=('sources','signals','derived')  # 唯一允许共享的定义，不包含执行节点。


def _reject(document, path, message, code='invalid_import', hint=None):
    """在实际声明处拒绝导入。参数: 文档、tuple路径、原因/代码/建议。返回: 不返回。异常: PlanValidationError。"""
    from ..planning.checks import PlanValidationError
    raise locate_error(PlanValidationError(field_path_text(path),message,code,hint=hint),document)


def _source_paths(source, base, path, document):
    """固定一项来源中的公开文件路径。参数: 来源副本、声明目录、字段路径、原文档。返回: None。异常: 字段错误。

    只改本次副本，metadata内任意path不解释为文件；不调用stat或resolve。
    """
    from ..planning.checks import absolute_path, array_at, PlanValidationError
    try:
        # 路径文字、列表和带offset的文件对象共用路径定位，不展开输入目录。
        from ..planning.input_paths import source_path_fields
        for owner,key in source_path_fields(source,field_path_text(path)):
            owner[key]=str(absolute_path(owner[key],base,field_path_text((*path,key))))
        if 'dbc_by_channel' in source:
            values=source['dbc_by_channel']
            if type(values) is not dict:
                _reject(document,(*path,'dbc_by_channel'),'DBC通道映射必须为对象')
            source['dbc_by_channel']={key:str(absolute_path(value,base,field_path_text((*path,'dbc_by_channel',key))))
                                      for key,value in values.items()}
    except PlanValidationError as error:
        raise locate_error(error,document)


def _append_definitions(data, prefix, document, source_prefix, merged, locations, origins, names):
    """追加一个文件的定义并迁移字段位置。参数: 原定义/目标前缀/原文档/原前缀及本次容器。返回: None。异常: 定义/重复错误。

    names保存首个同名声明的位置；所有修改仅发生在本次展开容器，无全局状态。
    """
    for section in SECTIONS:
        if section not in data:continue
        values=data[section]
        expected=dict if section=='derived' else list
        if type(values) is not expected:
            _reject(document,(*source_prefix,section),
                    'derived必须为名称到表达式的对象' if section=='derived' else '来源/信号定义必须为数组')
        offset=len(merged[section])
        entries=values.items() if section=='derived' else enumerate(values)
        for index,value in entries:
            path=(*source_prefix,section,index)
            if section!='derived' and type(value) is not dict:
                _reject(document,path,'每项公共定义必须为对象')
            if section=='signals' and 'signals' in value:
                children=value['signals']
                if type(children) is not list or any(type(child) is not dict for child in children):
                    _reject(document,(*path,'signals'),'组内signals必须为信号对象数组')
                declarations=[(child.get('name'),(*path,'signals',child_index,'name'))
                              for child_index,child in enumerate(children)]
            else:
                name=index if section=='derived' else value.get('name')
                declarations=[(name,path if section=='derived' else (*path,'name'))]
            for name,name_path in declarations:
                if type(name) is not str or not name:
                    _reject(document,name_path,'每项公共定义必须明确填写非空名称')
                # 集中声明和普通信号仍共用一个名字空间，组本身没有额外名称。
                identity=('sources' if section=='sources' else 'signals/derived',name)
                if identity in names:
                    first_source,first_path=names[identity]
                    _reject(document,name_path,'重复定义 '+name,'duplicate_definition',
                            '删除或改名；首次声明在 '+first_source+' '+field_path_text(first_path))
                names[identity]=(document.source,name_path)
            copied=deepcopy(value)
            if section=='sources':_source_paths(copied,Path(document.source).parent,path,document)
            if section=='derived':merged[section][name]=copied
            else:merged[section].append(copied)
        # 整个数组只遍历一次位置表，主文件项追加后仍指向主文件原索引。
        original_prefix=(*source_prefix,section)
        for original,location in document.locations.items():
            if original[:len(original_prefix)]!=original_prefix:continue
            suffix=original[len(original_prefix):]
            if not suffix:continue
            target=(*prefix,section,suffix[0] if section=='derived' else offset+suffix[0],*suffix[1:])
            locations[target]=location
            origins[target]=ConfigurationOrigin(document.source,original,location)


def expand_document_imports(document):
    """展开分析配置或映射中analysis的公共定义。参数: 已解析文档。返回: 可直接静态检查的文档。异常: 配置/读取错误。

    未声明imports时原样返回，不增加复制或文件读取。批量文件通过每个子计划
    自行使用imports；纯字典API不调用此函数。版本错误由原入口拒绝，不读其导入。
    """
    data=document.data
    if type(data) is not dict:return document
    prefix=('analysis',) if 'mapping_version' in data else ()
    analysis=data.get('analysis') if prefix else data
    if type(analysis) is not dict or 'imports' not in analysis:return document
    if type(analysis.get('config_version')) is not int or analysis['config_version']!=3:return document
    entries=analysis['imports']
    if type(entries) is not list:
        _reject(document,(*prefix,'imports'),'imports必须为本地配置路径数组')
    # 定义数组重新构造；先清除被移动数组的旧位置，避免缺失字段误用旧索引行列。
    raw=deepcopy(data)
    target=raw['analysis'] if prefix else raw
    merged={'sources':[],'signals':[],'derived':{}}
    locations={path:location for path,location in document.locations.items()
               if not (path[:len(prefix)]==prefix and len(path)>len(prefix)+1
                       and path[len(prefix)] in SECTIONS)}
    origins={path:ConfigurationOrigin(document.source,path,location) for path,location in locations.items()}
    names={}
    for index,entry in enumerate(entries):
        path=(*prefix,'imports',index)
        if type(entry) is not str or not entry.strip() or '://' in entry or any(char in entry for char in '*?[]'):
            _reject(document,path,'导入路径必须为明确的本地JSON/YAML文件，不支持URL、通配符或空值')
        imported=load_configuration(Path(document.source).parent/entry)
        fragment=imported.data
        if type(fragment) is not dict or not fragment:
            _reject(imported,(),'公共定义文件必须是非空对象，只能包含sources、signals、derived')
        unknown=set(fragment)-set(SECTIONS)
        if unknown:
            key=next(key for key in fragment if key in unknown)
            _reject(imported,(key,),'公共定义只允许sources、signals、derived；不支持嵌套imports或版本包装')
        _append_definitions(fragment,prefix,imported,(),merged,locations,origins,names)
    _append_definitions(analysis,prefix,document,prefix,merged,locations,origins,names)
    # 展开后不保留imports，执行计划只见一份普通配置；来源位置只在加载期使用。
    target.pop('imports')
    for section in SECTIONS:
        if section!='derived' or merged[section] or section in target:
            target[section]=merged[section]
    from .overrides import apply_overrides
    apply_overrides(target,document,prefix,locations,origins)
    return ConfigurationDocument(raw,document.source,document.format,
                                 MappingProxyType(locations),MappingProxyType(origins))
