"""通过独立纯Python安全解析器读取YAML1.2受限子集，不构造任意标签对象。"""
from math import isfinite

from .models import ConfigurationError, ConfigurationLocation
from .json_parser import MAX_DEPTH


def parse_yaml(text, source):
    """用事件流构造一次原生值树。参数: 文本/来源。返回: 数据和位置表。异常: 受限语法错误。"""
    # JSON入口不依赖YAML导入；每次新实例，失败或并发加载不共享解析器状态。
    from ruamel.yaml import YAML
    from ruamel.yaml.events import (StreamStartEvent,StreamEndEvent,DocumentStartEvent,
        DocumentEndEvent,ScalarEvent,SequenceStartEvent,SequenceEndEvent,
        MappingStartEvent,MappingEndEvent,AliasEvent)
    from ruamel.yaml.nodes import ScalarNode
    from ruamel.yaml.error import YAMLError

    class Yaml12(YAML):
        """版本在交给依赖校验前受限，避免依赖对1.3等版本抛出AssertionError。"""

        @YAML.version.setter
        def version(self, selected):
            """只允许默认或1.2。参数: 解析器版本。返回: None。异常: 明确配置版本错误。"""
            if selected is not None and tuple(selected)!=(1,2):
                # 依赖在文档起点事件前设版本；没有可靠mark时只报告文件，不猜行号。
                raise ConfigurationError(source,(),None,'yaml_version','只支持YAML 1.2')
            YAML.version.fset(self,selected)

    parser=Yaml12(typ='safe',pure=True)
    parser.version=(1,2)
    parser.allow_duplicate_keys=False
    positions={}
    events=parser.parse(text)

    def location(event):
        """复制事件位置，不让结果引用整份输入文本。参数: 事件。返回: 标量位置。异常: 无。"""
        return ConfigurationLocation(event.start_mark.line+1,event.start_mark.column+1)

    def reject(event,path,code,message):
        """抛定位错误。参数: 事件/路径/代码/原因。返回: 无。异常: ConfigurationError。"""
        raise ConfigurationError(source,path,location(event),code,message)

    def check(event,path):
        """在构造前拒绝别名、锚点和显式标签。返回: None。异常: 定位配置错误。"""
        if isinstance(event,AliasEvent):reject(event,path,'yaml_alias','不支持YAML别名；请直接写出配置内容')
        if getattr(event,'anchor',None) is not None:reject(event,path,'yaml_anchor','不支持YAML锚点')
        if getattr(event,'tag',None) is not None:reject(event,path,'yaml_tag','不支持显式标签；字符串请加引号')

    def scalar(event,path):
        """仅转换JSON原生标量；日期时间保文本。返回: 原生值。异常: 不支持类型或非有限数。"""
        check(event,path)
        tag=str(parser.resolver.resolve(ScalarNode,event.value,event.implicit))
        if tag in ('tag:yaml.org,2002:str','tag:yaml.org,2002:timestamp',
                   'tag:yaml.org,2002:merge','tag:yaml.org,2002:value'):
            # <<只在未加引号的映射键位置有合并含义；普通值仍是原始文本。
            return event.value
        if tag not in {'tag:yaml.org,2002:null','tag:yaml.org,2002:bool',
                       'tag:yaml.org,2002:int','tag:yaml.org,2002:float'}:
            reject(event,path,'yaml_scalar','仅支持文本、布尔、有限数字和null')
        # 报文ID只接受约定的三种进制；不能让YAML的0o或下划线数字先转换后绕过检查。
        if path and path[-1] == 'frame_id' and tag == 'tag:yaml.org,2002:int':
            from ..legacy.records import normalize_frame_id
            try:
                return normalize_frame_id(event.value)
            except (TypeError, ValueError) as error:
                reject(event, path, 'invalid_frame_id', str(error))
        # 直接调用安全标量构造，不创建带缓存的YAML节点树或任意Python对象。
        try:
            value=parser.constructor.yaml_constructors[tag](parser.constructor,ScalarNode(tag,event.value))
        except (ValueError,OverflowError) as error:
            raise ConfigurationError(source,path,location(event),'invalid_number',
                '数字超出当前Python可解析的范围') from error
        if type(value) is float and not isfinite(value):
            reject(event,path,'nonfinite_number','数值必须有限，不能使用NaN或Infinity')
        return value

    def value(event,path=(),depth=0):
        """递归消费一次事件流并保位置。返回: 原生值。异常: 受限语法或嵌套超限。"""
        check(event,path)
        if depth>MAX_DEPTH:reject(event,path,'nesting_limit','配置嵌套不能超过64层')
        positions[path]=location(event)
        if isinstance(event,ScalarEvent):return scalar(event,path)
        if isinstance(event,SequenceStartEvent):
            result=[]
            for child in events:
                if isinstance(child,SequenceEndEvent):return result
                result.append(value(child,(*path,len(result)),depth+1))
        elif isinstance(event,MappingStartEvent):
            result={}
            for key_event in events:
                if isinstance(key_event,MappingEndEvent):return result
                check(key_event,path)
                if not isinstance(key_event,ScalarEvent):reject(key_event,path,'non_string_key','配置对象的键必须为字符串')
                if key_event.value=='<<' and key_event.style is None:
                    reject(key_event,path,'yaml_merge','不支持YAML合并键')
                key=scalar(key_event,path)
                if type(key) is not str:reject(key_event,path,'non_string_key','配置对象的键必须为字符串；数字键请加引号')
                child_path=(*path,key)
                if key in result:reject(key_event,child_path,'duplicate_key',f'重复键：{key}')
                result[key]=value(next(events),child_path,depth+1)
        reject(event,path,'invalid_yaml','配置值结构不完整')

    try:
        if not isinstance(next(events),StreamStartEvent):raise AssertionError('YAML解析器缺少流起点')
        start=next(events)
        if isinstance(start,StreamEndEvent):return None,{():ConfigurationLocation(1,1)}
        if not isinstance(start,DocumentStartEvent):reject(start,(),'invalid_yaml','需要一个YAML文档')
        if start.version not in (None,(1,2)):reject(start,(),'yaml_version','只支持YAML 1.2')
        if start.tags:reject(start,(),'yaml_tag','不支持标签指令')
        data=value(next(events))
        end=next(events)
        if not isinstance(end,DocumentEndEvent):reject(end,(),'invalid_yaml','文档结束位置不正确')
        end=next(events)
        if not isinstance(end,StreamEndEvent):reject(end,(),'multiple_documents','一个配置文件只能包含一个YAML文档')
        return data,positions
    except YAMLError as error:
        mark=getattr(error,'problem_mark',None)
        place=None if mark is None else ConfigurationLocation(mark.line+1,mark.column+1)
        offset=getattr(error,'position',None)
        if place is None and type(offset) is int:
            place=ConfigurationLocation(text.count('\n',0,offset)+1,offset-text.rfind('\n',0,offset))
        message=getattr(error,'problem',None) or getattr(error,'reason',None) or 'YAML语法无效'
        raise ConfigurationError(source,(),place,'invalid_yaml',message) from error
    finally:
        events.close()
