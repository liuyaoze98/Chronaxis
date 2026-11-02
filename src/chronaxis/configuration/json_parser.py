"""标准库负责JSON语法和数值；轻量第二遍只定位字段，不再构造第二份配置树。"""
from bisect import bisect_right
import json
from math import isfinite
import re

from .models import ConfigurationError, ConfigurationLocation

MAX_DEPTH=64
_SPACE=re.compile(r'[ \t\r\n]*')


class _DuplicateKey(ValueError):
    """只用于让标准库停止覆盖重复键；随后位置扫描给出具体字段。"""


def _unique_pairs(pairs):
    """建立唯一键对象。参数: 标准库键值对。返回: dict。异常: 重复键。"""
    result={}
    for key,value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key]=value
    return result


class _Locations:
    """只记录JSON路径和偏移，不保留第二份值树；语法真值仍由json.loads决定。"""

    def __init__(self, text, source):
        """建立本次扫描状态。参数: 文本/显示来源。返回: owner。异常: 分配失败。"""
        self.text,self.source=text,source
        self.positions={}
        self.lines=[match.start() for match in re.finditer('\n',text)]
        self.decoder=json.JSONDecoder()

    def location(self, offset):
        """把字符偏移转换为1基行列。参数: 偏移。返回: 位置。异常: 无。"""
        line=bisect_right(self.lines,offset-1)
        previous=self.lines[line-1] if line else -1
        return ConfigurationLocation(line+1,offset-previous)

    def scan(self, offset=0, path=(), depth=0):
        """遍历合法JSON或已知含重复键的JSON。返回: 结束偏移。异常: 重复键/过深/语法错误。"""
        offset=_SPACE.match(self.text,offset).end()
        location=self.location(offset)
        if depth>MAX_DEPTH:
            raise ConfigurationError(self.source,path,location,'nesting_limit','配置嵌套不能超过64层')
        self.positions[path]=location
        first=self.text[offset]
        if first=='{':
            offset=_SPACE.match(self.text,offset+1).end()
            if self.text[offset]=='}':return offset+1
            seen=set()
            while True:
                key_at=offset
                key,offset=json.decoder.scanstring(self.text,offset+1,True)
                if key in seen:
                    raise ConfigurationError(self.source,(*path,key),self.location(key_at),
                        'duplicate_key',f'重复键：{key}')
                seen.add(key)
                offset=_SPACE.match(self.text,offset).end()+1  # 已通过JSON语法检查的冒号。
                offset=self.scan(offset,(*path,key),depth+1)
                offset=_SPACE.match(self.text,offset).end()
                if self.text[offset]=='}':return offset+1
                offset=_SPACE.match(self.text,offset+1).end()
        if first=='[':
            offset=_SPACE.match(self.text,offset+1).end()
            if self.text[offset]==']':return offset+1
            index=0
            while True:
                offset=self.scan(offset,(*path,index),depth+1)
                offset=_SPACE.match(self.text,offset).end()
                if self.text[offset]==']':return offset+1
                offset=_SPACE.match(self.text,offset+1).end()
                index+=1
        # raw_decode这里只接原子值，绝不重新解码整个容器。
        _,end=self.decoder.raw_decode(self.text,offset)
        return end


def _finite_values(value, source, locations, path=()):
    """拒绝JSON宽松接受的NaN/Infinity及指数溢出。返回: None。异常: 定位到实际值。"""
    if type(value) is float and not isfinite(value):
        raise ConfigurationError(source,path,locations[path],'nonfinite_number','数值必须有限，不能使用NaN或Infinity')
    if type(value) is dict:
        for key,item in value.items():_finite_values(item,source,locations,(*path,key))
    elif type(value) is list:
        for index,item in enumerate(value):_finite_values(item,source,locations,(*path,index))


def parse_json(text, source):
    """按标准JSON加载并附准确位置。参数: 文本/来源。返回: 数据和位置表。异常: ConfigurationError。"""
    try:
        try:
            data=json.loads(text,object_pairs_hook=_unique_pairs)
        except _DuplicateKey:
            # 标准库已找到实际重复；不从字符串搜索猜测它属于哪个嵌套对象。
            _Locations(text,source).scan()
            raise AssertionError('JSON重复键位置扫描没有发现重复')
        except json.JSONDecodeError:
            raise
        except (ValueError,OverflowError) as error:
            # Python的十进制整数安全长度限制等数值错误不能泄露为无文件定位的底层异常。
            raise ConfigurationError(source,(),None,'invalid_number','数字超出当前Python可解析的范围') from error
        scanner=_Locations(text,source)
        scanner.scan()
        _finite_values(data,source,scanner.positions)
        return data,scanner.positions
    except json.JSONDecodeError as error:
        raise ConfigurationError(source,(),ConfigurationLocation(error.lineno,error.colno),
            'invalid_json',error.msg) from error
    except RecursionError as error:
        raise ConfigurationError(source,(),None,'nesting_limit','配置嵌套不能超过64层') from error
