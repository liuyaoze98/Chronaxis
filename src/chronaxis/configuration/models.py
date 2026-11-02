"""配置加载期的原生数据、字段位置和语法错误，不参与分析执行或来源读取。"""
from dataclasses import dataclass, field
from collections.abc import Mapping
import json


def field_path_text(path):
    """把键/数组下标路径变成无歧义文本。参数: tuple。返回: JSON路径。异常: 非内部路径。"""
    result='$'
    for part in path:
        if type(part) is int:
            result+=f'[{part}]'
        elif type(part) is str:
            result+=('.'+part if part.isidentifier() else '['+json.dumps(part,ensure_ascii=False)+']')
        else:
            raise TypeError('配置字段路径只接受文本键或整数下标')
    return result


@dataclass(frozen=True, slots=True)
class ConfigurationLocation:
    """一处源码位置；行列从1开始，列按Unicode字符计，不按UTF-8字节计。"""
    line: int
    column: int


@dataclass(frozen=True, slots=True)
class ConfigurationOrigin:
    """展开字段的声明位置；只保存文件名、字段路径及行列，不保存第二份配置。"""
    source: str  # 实际声明文件的词法绝对路径。
    field_path: tuple  # 声明文件内部路径，索引尚未被合并重排。
    location: ConfigurationLocation | None  # 原文一基行列；无法取得时为None。


@dataclass(frozen=True, slots=True)
class ConfigurationDocument:
    """只在加载期间持有原生值和必要位置；调用者构造计划后释放本对象。"""
    data: object
    source: str
    format: str
    locations: Mapping
    origins: Mapping = field(default_factory=dict)  # 仅文件导入展开时填充，计划构造后释放。

    def origin_for(self, field_path):
        """查最近声明来源并保留缺失字段后缀。参数: tuple路径。返回: 来源或None。异常: 无。"""
        original=tuple(field_path)
        path=original
        # 缺少字段只能沿所属对象定位，不能捏造它在原文件中的行列。
        while path not in self.origins and path:
            path=path[:-1]
        origin=self.origins.get(path)
        if origin is None:return None
        return ConfigurationOrigin(origin.source,origin.field_path+original[len(path):],origin.location)

    def location_for(self, field_path):
        """取具体值位置，缺少字段时回溯最近父对象。参数: tuple路径。返回: 位置或None。异常: 无。"""
        path=tuple(field_path)
        while path not in self.locations and path:
            path=path[:-1]
        return self.locations.get(path)


class ConfigurationError(ValueError):
    """保存语法错误码、文件和字段位置；消息不打印整份配置或执行任意内容。"""

    def __init__(self, source, field_path, location, code, message):
        """建立错误事实。参数: 来源/tuple路径/位置/代码/原因。返回: None。异常: 无。"""
        self.source=source
        self.field_path=tuple(field_path)
        self.location=location
        self.code=code
        self.message=message
        place=source if location is None else f'{source}:{location.line}:{location.column}'
        super().__init__(f'{place} {field_path_text(self.field_path)}: {message}')
