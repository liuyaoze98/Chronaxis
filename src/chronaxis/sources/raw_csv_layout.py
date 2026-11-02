"""声明原始报文CSV的列和值含义，不按中文列名猜字段。

ColumnMapping选择一个列名、从1开始的列号或固定值，可明确把中文值映射到
布尔/帧类型。CANCSVLayout冻结编码、分隔符和映射，bind_header一次确定列位置，
随后只访问实际配置的列，输出规范字段；这里尚不解析时间、ID或十六进制载荷。
构造/绑定均无I/O；公共来源可先补入其唯一通道，独立布局仍须提供通道。
"""

import codecs
from dataclasses import dataclass, field
from types import MappingProxyType
from collections.abc import Mapping


# 名称指向物理字段，frame_kind与扩展/FD标志分开，避免“帧格式/帧类型”歧义。
REQUIRED_FIELDS = frozenset(('timestamp', 'frame_id', 'channel', 'data'))
BOOL_FIELDS = frozenset(('is_rx', 'is_extended', 'is_fd', 'bitrate_switch', 'error_state_indicator'))
LENGTH_FIELDS = frozenset(('payload_length', 'dlc_code'))
ALL_FIELDS = REQUIRED_FIELDS | BOOL_FIELDS | LENGTH_FIELDS | {'frame_kind'}
MAX_COLUMNS = 4096
MAX_FIXED_TEXT = 16384


def _scalar(value, label, *, limit=MAX_FIXED_TEXT):
    """限定可静态配置的值。参数: value候选；label定位；limit文本上限。返回: 原值。异常: 类型/长度错误。
    """
    # 不允许任意对象/浮点/None进入配置，也不把bool按int处理。
    if type(value) not in (str, int, bool):
        raise TypeError(label + '需要str/int/bool')
    if type(value) is str and len(value) > limit:
        raise ValueError(label + '文本过长')
    if type(value) is int and not -(2**63) <= value <= 2**64-1:
        raise ValueError(label + '整数超出64位范围')
    return value


def _fields(value, allowed, required, label):
    """检查严格配置键。参数: value字典、allowed允许键、required必需键、label定位。返回: 原dict。异常: 类型/未知缺失键。
    """
    # JSON形状必须明确；未知拼写不能静默变成另一种来源配置。
    if type(value) is not dict or any(type(key) is not str for key in value):
        raise TypeError(label + '需要字符串键dict')
    if set(value) - set(allowed) or set(required) - set(value):
        raise ValueError(label + '包含未知键或缺少必需键')
    return value


def _physical_value(name, value):
    """校验已映射的字段类型，避免文本被隐式转成True。

    参数: name规范字段、value已经取出/查表的值。返回: None。异常: 标志/帧类型或普通字段类型错误。
    """
    # 布尔和帧种类先核实实际含义；数值文字由原始CSV读取器按声明进制转换。
    if name in BOOL_FIELDS:
        if type(value) is not bool:
            raise ValueError('CSV标志需要显式bool映射: ' + name)
    elif name == 'frame_kind':
        if type(value) is not str or value not in ('data', 'remote', 'error'):
            raise ValueError('CSV帧种类需要data/remote/error映射')
    elif name == 'data':
        if type(value) is not str:
            raise ValueError('CSV载荷需要明确的十六进制文本')
    elif type(value) not in (str, int):
        raise ValueError('CSV字段需要文本或整数: ' + name)


def _common_value(name, value):
    """只识别含义明确的常用文字；显式value_map的结果不经过此函数。"""
    if type(value) is not str:
        return value
    key = value.casefold()
    if name == 'is_rx':
        return {'rx':True, 'tx':False, '接收':True, '发送':False,
                'true':True, 'false':False}.get(key, value)
    if name == 'frame_kind':
        return {'data':'data', '数据帧':'data', 'remote':'remote',
                '远程帧':'remote', 'error':'error', '错误帧':'error'}.get(key, value)
    if name in BOOL_FIELDS:
        return {'true':True, 'false':False}.get(key, value)
    return value


@dataclass(frozen=True)
class ColumnMapping:
    """固定一种取值来源及可选值映射；复制后不可被调用方字典修改。"""

    column: str | int | None = None  # 列名或从1开始的整数列号，字符串数字仍是列名。
    fixed: str | int | bool | None = None  # 缺少实际列时声明固定值；False/0/空字符串都有效。
    value_map: Mapping[str, str | int | bool] | None = None  # 严格逐值对应，未登记值报错。
    strip: bool = True  # 是否去掉取出单元格两端空白，不改变载荷内部空格。

    def __post_init__(self):
        """校验来源并冻结映射。参数: 无。返回: None。异常: 模糊来源、坏类型或超限。
        """
        # None只代表未指定；不能用真假判断而误拒固定的False、0或空载荷。
        if (self.column is None) == (self.fixed is None):
            raise ValueError('列映射必须且只能指定column或fixed')
        if self.column is not None:
            if type(self.column) is int:
                if not 1 <= self.column <= MAX_COLUMNS:
                    raise ValueError('列号从1开始且不超过4096')
            elif type(self.column) is not str or not self.column or len(self.column) > 256:
                raise ValueError('列名需非空且不超过256字符')
        else:
            _scalar(self.fixed, 'fixed')
        # 查表行为提前冻结；被调用方随后改写的字典不能影响同一分析计划。
        if type(self.strip) is not bool:
            raise TypeError('strip需要bool')
        if self.value_map is not None:
            if not isinstance(self.value_map, Mapping) or not 1 <= len(self.value_map) <= 256:
                raise ValueError('value_map需要1到256项映射')
            values = {}
            for key, value in self.value_map.items():
                if type(key) is not str or len(key) > 256:
                    raise ValueError('value_map键需不超过256字符的文本')
                # strip发生在查表前；拒绝永远匹配不到的边缘空白键。
                if self.strip and key != key.strip():
                    raise ValueError('strip模式的映射键不能有边缘空白')
                values[key] = _scalar(value, 'value_map值', limit=256)
            object.__setattr__(self, 'value_map', MappingProxyType(values))

    @classmethod
    def from_dict(cls, value):
        """从严格JSON形状构造。参数: value配置dict。返回: ColumnMapping。异常: 未知键/值错误。
        """
        if type(value) in (str, int):
            return cls(column=value)
        _fields(value, ('column', 'fixed', 'value_map', 'strip'), (), 'column_mapping')
        return cls(**value)

    def to_dict(self):
        """保存明确声明，保留False/0/空值差异。参数: 无。返回: 独立dict。异常: 无。
        """
        result = {'strip':self.strip}
        result['column' if self.column is not None else 'fixed'] = self.column if self.column is not None else self.fixed
        if self.value_map is not None:
            result['value_map'] = dict(self.value_map)
        return result


@dataclass(frozen=True)
class CANCSVLayout:
    """声明原始报文表，不与已解码signal_csv混淆；绑定表头以前不访问文件。"""

    fields: Mapping[str, ColumnMapping]  # 长度省略时取实际载荷字节数；方向省略时保持未知。
    encoding: str = 'utf-8-sig'  # 严格编码，无探测/自动重试，仓库样例明确设置gbk。
    delimiter: str = ','  # 一个明确字符，制表样例设置\t，不由扩展名推断。
    has_header: bool = True  # 无表头时只允许整数列号/固定值。
    skip_rows: int = 0  # 从文件开始明确跳过的表记录数，不自动寻找“像表头”的行。
    layout_version: str = 'raw-can-csv-layout-v1'  # 显式版本，不等于公共analysis schema已接通。

    def __post_init__(self):
        """冻结布局并校验完整字段声明。参数: 无。返回: None。异常: 类型/缺失/未知字段或编码错误。
        """
        # 明确格式与编码/分隔方式，禁止依文件名猜测或遇错换编码。
        if self.layout_version != 'raw-can-csv-layout-v1':
            raise ValueError('不支持的原始报文CSV布局版本')
        if type(self.encoding) is not str or not self.encoding:
            raise TypeError('CSV编码必须明确')
        codecs.lookup(self.encoding)
        if (type(self.delimiter) is not str or len(self.delimiter) != 1
                or self.delimiter in ('\r', '\n', '\x00', '"')):
            raise ValueError('CSV分隔符需一个非换行/引号/NUL字符')
        if type(self.has_header) is not bool or type(self.skip_rows) is not int or not 0 <= self.skip_rows <= 100000:
            raise ValueError('CSV需要bool表头开关和0到100000的跳过记录数')
        # 长度可由载荷取得；显式长度和DLC仍分别检查，不能互相替代。
        if not isinstance(self.fields, Mapping):
            raise TypeError('CSV fields需要映射')
        if (any(type(key) is not str for key in self.fields) or set(self.fields) - ALL_FIELDS
                or REQUIRED_FIELDS - set(self.fields)):
            raise ValueError('CSV物理字段缺失或未知')
        copied = dict(self.fields)
        if any(type(value) is not ColumnMapping for value in copied.values()):
            raise TypeError('CSV fields值需要ColumnMapping')
        if not self.has_header and any(type(value.column) is str for value in copied.values()):
            raise ValueError('无表头CSV不能按列名取值')
        # 普通数据帧和未置位的FD选项使用默认值；收发方向不补造。
        for name in ('bitrate_switch', 'error_state_indicator'):
            copied.setdefault(name, ColumnMapping(fixed=False))
        copied.setdefault('frame_kind', ColumnMapping(fixed='data'))
        # 固定值和枚举结果在开读前就能核实，不能把配置错误拖到第一条数据才暴露。
        for name, mapping in copied.items():
            if mapping.value_map is not None:
                for value in mapping.value_map.values():
                    _physical_value(name, value)
            if mapping.column is None:
                value = mapping.fixed
                if mapping.value_map is not None:
                    if type(value) is not str or value not in mapping.value_map:
                        raise ValueError('CSV固定值未在value_map声明: ' + name)
                    value = mapping.value_map[value]
                else:
                    value = _common_value(name, value)
                _physical_value(name, value)
        object.__setattr__(self, 'fields', MappingProxyType(copied))

    @classmethod
    def from_dict(cls, value):
        """加载严格布局配置。参数: value原生dict。返回: CANCSVLayout。异常: 未知键/字段/列映射错误。
        """
        # 使用同一静态校验创建实例，解释/运行不会各用一套宽松规则。
        _fields(value, ('fields', 'encoding', 'delimiter', 'has_header', 'skip_rows', 'layout_version'), ('fields',), 'raw_csv_layout')
        if type(value['fields']) is not dict:
            raise TypeError('raw_csv_layout.fields需要dict')
        options = {key:item for key,item in value.items() if key != 'fields'}
        return cls({key:ColumnMapping.from_dict(item) for key,item in value['fields'].items()}, **options)

    def to_dict(self):
        """输出完整已采用布局供解释/追溯。参数: 无。返回: 独立JSON字典。异常: 无。
        """
        return dict(layout_version=self.layout_version, encoding=self.encoding, delimiter=self.delimiter,
                    has_header=self.has_header, skip_rows=self.skip_rows,
                    fields={key:item.to_dict() for key,item in self.fields.items()})

    def bind_header(self, header=None):
        """只解析一次表头列位置。参数: header为有表头时的str列表/tuple，无表头必须None。

        返回: BoundCANCSVLayout。异常: 表头类型/重复/缺列或表头开关矛盾；不读任何记录。
        """
        # 表头每次来源绑定只检查一次，有界列数防止构造无限名称索引。
        if self.has_header:
            if type(header) not in (tuple, list) or not 1 <= len(header) <= MAX_COLUMNS:
                raise ValueError('CSV表头需要1到4096列')
            if any(type(item) is not str or len(item) > 256 for item in header):
                raise ValueError('CSV表头需要有限文本')
            # 允许未使用的空表头（仓库制表样例尾列）；非空重复名不能有歧义。
            names = [item for item in header if item]
            if len(names) != len(set(names)):
                raise ValueError('CSV表头存在重复列名')
            header = tuple(header)
        elif header is not None:
            raise ValueError('无表头配置不能另传表头')
        # 名称按原样匹配；整数只在这里从1基转成0基，后续逐行不再搜索表头。
        bound = []
        for name, mapping in self.fields.items():
            if type(mapping.column) is str:
                if mapping.column not in header:
                    raise ValueError('CSV缺少映射列: ' + mapping.column)
                position = header.index(mapping.column)
            elif type(mapping.column) is int:
                position = mapping.column - 1
                if header is not None and position >= len(header):
                    raise ValueError('CSV映射列号超出表头')
            else:
                position = None
            bound.append((name, mapping, position))
        return BoundCANCSVLayout(tuple(bound))


@dataclass(frozen=True)
class BoundCANCSVLayout:
    """保存有结构检查的列位置，只访问选择列；不认证实际文件表头或内容。"""

    bindings: tuple = field(repr=False)  # (规范字段名,冻结映射,0基列位置或None)。

    def __post_init__(self):
        """校验可独立构造的绑定。参数: 无。返回: None。异常: 绑定结构、字段或列号错误。
        """
        # 公开构造也要守住字段唯一性和列范围；这只是结构检查，不冒充实际表头证据。
        if type(self.bindings) is not tuple or not len(REQUIRED_FIELDS) <= len(self.bindings) <= len(ALL_FIELDS):
            raise ValueError('CSV绑定数量错误')
        names = set()
        for entry in self.bindings:
            if type(entry) is not tuple or len(entry) != 3:
                raise ValueError('CSV绑定需要字段/映射/位置三元组')
            name, mapping, position = entry
            if type(name) is not str or name not in ALL_FIELDS or name in names or type(mapping) is not ColumnMapping:
                raise ValueError('CSV绑定字段或映射错误')
            if (mapping.column is None) != (position is None):
                raise ValueError('CSV固定值与列位置矛盾')
            if position is not None and (type(position) is not int or not 0 <= position < MAX_COLUMNS):
                raise ValueError('CSV绑定列位置错误')
            if type(mapping.column) is int and position != mapping.column - 1:
                raise ValueError('CSV绑定列号与位置矛盾')
            names.add(name)
        if REQUIRED_FIELDS - names:
            raise ValueError('CSV绑定缺少物理字段')

    def map_row(self, row, *, names=None):
        """提取并明确映射一条表记录。参数: row为list/tuple单元格；names为内部按需字段集合，省略时提取声明全部列。

        返回: 只读规范字段字典；时间、数值和载荷由原始CSV读取器解析。
        异常: 缺列、所需单元格非文本、未登记枚举、布尔/帧类型或值类型错误。
        """
        # 只触碰有消费者的列，未选择的列不做内容类型检查或数值转换。
        if type(row) not in (tuple, list) or len(row) > MAX_COLUMNS:
            raise ValueError('CSV记录需要不超过4096列')
        result = {}
        for name, mapping, position in self.bindings:
            if names is not None and name not in names:
                continue
            if position is None:
                value = mapping.fixed
            else:
                if position >= len(row) or type(row[position]) is not str:
                    raise ValueError('CSV缺少所需文本列: ' + name)
                value = row[position].strip() if mapping.strip else row[position]
                if len(value) > MAX_FIXED_TEXT:
                    raise ValueError('CSV所需单元格过长: ' + name)
            # 声明了值表就必须匹配，不能在未知中文状态上回退成某个默认身份。
            if mapping.value_map is not None:
                if type(value) is not str or value not in mapping.value_map:
                    raise ValueError('CSV值未在value_map声明: ' + name)
                value = mapping.value_map[value]
            else:
                value = _common_value(name, value)
            # 标志/数据与远程类型必须明确，不能把非空中文字符串普遍当True。
            _physical_value(name, value)
            result[name] = value
        return MappingProxyType(result)
