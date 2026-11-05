"""为配置错误附上原文位置与有限的上下文；成功计划不保存此处的文档对象。

这里只消费已解析的原生值，不重新读取配置或来源。字段路径采用带引号键的
JSON路径；不存在字段回指最近所属对象，不能给缺少的值捏造行列。
"""
import json
import re

from .models import field_path_text


def field_path_parts(text):
    """读取内部字段路径。参数: $开头文本。返回: tuple或无法定位时None。异常: 无。

    引号键用标准JSON解码，不执行表达式；组合诊断如$.signals/derived不能冒充字段。
    """
    if not isinstance(text,str) or not text.startswith('$'):
        return None
    parts=[]
    position=1
    while position<len(text):
        if text[position]=='.':
            match=re.match(r'[^.\[\]/]+',text[position+1:])
            if match is None:
                return None
            parts.append(match[0])
            position+=len(match[0])+1
        elif text[position:position+2]=='["':
            try:
                key,end=json.JSONDecoder().raw_decode(text,position+1)
            except ValueError:
                return None
            if type(key) is not str or text[end:end+1]!=']':
                return None
            parts.append(key)
            position=end+1
        else:
            match=re.match(r'\[(0|[1-9][0-9]*)\]',text[position:])
            if match is None:
                return None
            parts.append(int(match[1]))
            position+=len(match[0])
    return tuple(parts)


def child_path(path,key):
    """追加一层真实键。参数: 字段路径/字符串键。返回: 无歧义路径。异常: 内部路径不合法。
    """
    return path+field_path_text((key,))[1:]


def value_preview(value):
    """只显示有限值摘要。参数: JSON原生值。返回: 最多180字符。异常: 无。

    容器仅报类型/大小，防止错误输出整份配置、内存行或自由元数据。
    """
    if type(value) is dict:
        return f'对象（{len(value)}个字段）'
    if type(value) is list:
        return f'数组（{len(value)}项）'
    text=json.dumps(value,ensure_ascii=False,allow_nan=False)
    return text if len(text)<=180 else text[:177]+'…'


def locate_error(error,document):
    """给计划异常补充有限诊断字段。参数: 计划异常/原文档。返回: 同一异常。异常: 无。

    不保存document、原字典或位置表；只复制源码名、单一位置、对象名和短值。
    """
    # 集合的每项分别通过导入来源表定位，不把首项位置套到整份报告。
    if getattr(error, '_diagnostics', None) is not None:
        for item in error.diagnostics:
            locate_error(item, document)
        first = error.diagnostics[0]
        for name in ('path','source','location','object_name','value_preview','hint'):
            setattr(error, name, getattr(first, name))
        error.refresh_text()
        return error
    # 导入器可能已经把异常定位到另一个文件；外层不得用主文件覆盖真实来源。
    if error.source is not None:return error
    parts=field_path_parts(error.path)
    error.source=document.source
    if parts is None:
        error.refresh_text()
        return error
    error.location=document.location_for(parts)
    current=document.data
    name=None
    labels={'signals':'信号','sources':'来源','rules':'规则','windows':'窗口',
            'calculations':'计算项','sequences':'序列','jobs':'任务','presets':'预设'}
    label=next((labels[part] for part in parts if part in labels),'对象')
    # 从根走向出错字段，最近的命名对象比根dataset更能解释该处声明。
    missing=False
    for part in (*parts,None):
        if type(current) is dict:
            candidate=current.get('name')
            if type(candidate) is str:
                name=candidate[:120]
        if part is None:
            break
        if type(current) is dict and type(part) is str and part in current:
            current=current[part]
        elif type(current) is list and type(part) is int and part<len(current):
            current=current[part]
        else:
            missing=True
            break
    error.object_name=None if name is None else label+' '+name
    error.value_preview='未提供' if missing else value_preview(current)
    origin=document.origin_for(parts)
    if origin is not None:
        error.source=origin.source
        error.path=field_path_text(origin.field_path)
        error.location=origin.location
    error.refresh_text()
    return error
