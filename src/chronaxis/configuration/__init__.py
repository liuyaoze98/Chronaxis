"""共享配置语法入口；只读指定文件，返回原生值和加载期位置，不读取业务输入。"""
from pathlib import Path
from types import MappingProxyType

from .models import ConfigurationDocument, ConfigurationError, ConfigurationLocation, field_path_text
from .json_parser import parse_json

__all__=['ConfigurationDocument','ConfigurationError','ConfigurationLocation',
         'field_path_text','parse_configuration','load_configuration']


def parse_configuration(text, *, format, source='<configuration>'):
    """解析显式格式文本。参数: str文本、json/yaml格式、显示来源。返回: 文档。异常: 语法或参数错误。

    不替换环境变量或执行模板。UTF-8文件开头的BOM可选；字段原始字符串保留。
    """
    if type(text) is not str or type(source) is not str:
        raise TypeError('配置内容和来源名称需要文本')
    if type(format) is not str or format not in ('json','yaml'):
        raise ConfigurationError(source,(),None,'unsupported_format','配置格式只支持json或yaml')
    if text.startswith('\ufeff'):text=text[1:]
    if format=='json':
        data,locations=parse_json(text,source)
    else:
        from .yaml_parser import parse_yaml
        data,locations=parse_yaml(text,source)
    return ConfigurationDocument(data,source,format,MappingProxyType(locations))


def load_configuration(path):
    """按.json/.yaml/.yml加载UTF-8文件。返回: 文档。异常: 定位读取/语法错误；取消原样传播。

    后缀不识别时不打开文件；读取结束即关闭句柄，再解析文本，不持有调用者输入文件。
    """
    if not isinstance(path,(str,Path)):
        raise TypeError('配置路径需要Path或文本')
    target=Path(path).absolute()
    format={'.json':'json','.yaml':'yaml','.yml':'yaml'}.get(target.suffix.lower())
    if format is None:
        raise ConfigurationError(str(target),(),None,'unsupported_format','配置后缀需要.json、.yaml或.yml')
    try:
        with target.open('r',encoding='utf-8-sig') as stream:
            text=stream.read()
    except (OSError,UnicodeError) as error:
        raise ConfigurationError(str(target),(),None,'load_error',str(error)) from error
    return parse_configuration(text,format=format,source=str(target))
