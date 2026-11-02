"""当前配置的格式转换和新文件发布；不推断业务参数，不执行分析。"""
from io import StringIO
import json
import math
from pathlib import Path

from . import load_configuration, parse_configuration
from .diagnostics import locate_error


def configuration_type(data):
    """识别三个独立当前入口。参数: 原生配置。返回: analysis/batch/mapping。异常: ValueError。

    版本不能猜测或迁移；旧INI由独立legacy import入口处理。
    """
    from ..planning.checks import PlanValidationError
    versions={'config_version':('analysis',3),'batch_version':('batch',1),'mapping_version':('mapping',1)}
    present=[key for key in versions if type(data) is dict and key in data]
    if len(present)!=1:raise PlanValidationError('$','需要且只能有一种配置版本字段','invalid_version')
    key=present[0];name,version=versions[key]
    if type(data[key]) is not int or data[key]!=version:
        raise PlanValidationError('$.'+key,'仅接受当前版本'+str(version)+'，不转换旧结构','invalid_version')
    return name


def validate_document(document, base, *, return_plan=False):
    """调用现有模型；return_plan=True时同时返回计划，避免配置工具重复加载DBC。

    批量不加载子任务，映射只核映射与其分析部分；INI模式与段名需在实际导入时核对。
    """
    from ..planning import AnalysisPlan
    from ..planning.checks import PlanValidationError
    from .imports import expand_document_imports
    try:
        document=expand_document_imports(document)
        name=configuration_type(document.data)
        if name=='analysis':plan=AnalysisPlan.from_dict(document.data,base_dir=base)
        elif name=='batch':
            from ..batch.models import BatchPlan
            plan=BatchPlan.from_dict(document.data,base_dir=base)
        else:
            from ..migration.api import _prepare_mapping
            from ..migration.ini import ImportProblem
            try:_prepare_mapping(document.data,base)
            except ImportProblem as error:
                raise PlanValidationError(error.issue.path,error.issue.message,error.issue.code) from error
            try:plan=AnalysisPlan.from_dict(document.data['analysis'],base_dir=base)
            except PlanValidationError as error:
                error.path='$.analysis'+error.path[1:];error.refresh_text();raise
        return (name,plan) if return_plan else name
    except PlanValidationError as error:raise locate_error(error,document)


def path_fields(data, config_type):
    """枚举声明的文件路径位置。参数: 已校验配置及类型。返回: (容器,键)迭代器。异常: 内部结构错误。

    只认来源文件/DBC、批量子计划和公共定义；metadata与表达式中的path文字保持原样。
    """
    if config_type=='batch':
        for job in data.get('jobs',[]):yield job,'plan'
        if 'template' in data:
            yield data,'template'
            from ..planning.input_paths import source_path_fields
            holder={'paths':data['inputs']}
            for owner,key in source_path_fields(holder):
                yield (data,'inputs') if owner is holder else (owner,key)
        return
    analysis=data['analysis'] if config_type=='mapping' else data
    for source in analysis.get('sources',[]):
        from ..planning.input_paths import source_path_fields
        yield from source_path_fields(source)
        for channel in source.get('dbc_by_channel',{}):yield source['dbc_by_channel'],channel
    for index in range(len(analysis.get('imports',[]))):yield analysis['imports'],index


def same_native_value(left,right):
    """核类型/顺序/数值不漂移，包含负零和大整数。参数: 原生值。返回: bool。异常: 无。"""
    if type(left) is not type(right):return False
    if type(left) is dict:
        return list(left)==list(right) and all(same_native_value(left[key],right[key]) for key in left)
    if type(left) is list:
        return len(left)==len(right) and all(same_native_value(a,b) for a,b in zip(left,right))
    if type(left) is float and left==0:return left==right and math.copysign(1,left)==math.copysign(1,right)
    return left==right


def serialize_configuration(data, format):
    """输出可被受限解析器再读取的文本。参数: 配置及json/yaml。返回: str。异常: ValueError。

    输出后独立重解析并核类型和值，避免YAML隐式类型或浮点表示改写含义。注释不参与互转。
    """
    if format=='json':text=json.dumps(data,ensure_ascii=False,allow_nan=False,indent=2)+'\n'
    elif format=='yaml':
        from ruamel.yaml import YAML
        yaml=YAML(typ='safe',pure=True);yaml.version=(1,2);yaml.default_flow_style=False
        yaml.sort_base_mapping_type_on_output=False
        yaml.representer.ignore_aliases=lambda value:True
        stream=StringIO();yaml.dump(data,stream);text=stream.getvalue()
    else:raise ValueError('输出格式仅支持json或yaml')
    if not same_native_value(data,parse_configuration(text,format=format).data):
        raise ValueError('格式转换不能保持原配置类型、顺序和值；未写文件')
    return text


def output_format(path):
    """由扩展名选择格式。参数: Path。返回: json/yaml。异常: ValueError。"""
    suffix=path.suffix.lower()
    if suffix not in ('.json','.yaml','.yml'):raise ValueError('新文件需要.json、.yaml或.yml扩展名')
    return 'json' if suffix=='.json' else 'yaml'


def write_new_configuration(path, text):
    """独占写新文件。参数: 路径及已校验文本。返回: Path。异常: IO/取消。

    已存在文件、硬链接和符号链接都由独占打开拒绝；部分写失败仅清理本次创建的文件。
    """
    target=Path(path).absolute()
    stream=target.open('x',encoding='utf-8',newline='\n')
    try:
        with stream:stream.write(text);stream.flush()
    except BaseException as error:
        try:stream.close()
        except OSError as cleanup:error.add_note('未能关闭部分配置 '+str(target)+': '+str(cleanup))
        try:target.unlink()
        except OSError as cleanup:error.add_note('未能清理部分配置 '+str(target)+': '+str(cleanup))
        raise
    return target


def convert_configuration(source, output):
    """仅改变当前配置的JSON/YAML表示。参数: 输入、新文件。返回: 输出Path。异常: 配置/IO错误。

    相对路径存在时只允许同目录输出；跨目录需使用resolve显式重定位，不静默修改原值。
    """
    source=Path(source).absolute();target=Path(output).absolute()
    document=load_configuration(source);name=validate_document(document,source.parent)
    if source.parent!=target.parent and any(not Path(owner[key]).is_absolute() for owner,key in path_fields(document.data,name)):
        raise ValueError('配置含相对路径，convert只能写入同目录；跨目录请用config resolve --output重新定位')
    text=serialize_configuration(document.data,output_format(target))
    return write_new_configuration(target,text)
