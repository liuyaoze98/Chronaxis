"""校验 v4 一维标定表声明，并按已请求的插值方式生成只读计算表。

声明只保存配置点对和内容身份。被表达式引用时才将两列写为固定小端字节，
支持标量随机读取或 NumPy 零复制视图。无文件、全局缓存或第三方依赖。
"""

from dataclasses import dataclass, field, replace
from hashlib import sha256
from math import isfinite
from struct import Struct

from .types import SignalDType as D
from .unit_registry import resolve_unit
from .validation import require_identifier


MAX_TABLES = 64
MAX_POINTS = 4096
_FORMATS = {D.INT64: Struct('<q'), D.UINT64: Struct('<Q'), D.FLOAT64: Struct('<d')}


def _exact_f64(value):
    """校验 float64 转换。参数: 表内原生数。返回: float。异常: 非有限、整数超界或精度损失。"""
    if type(value) not in (int, float):
        raise TypeError('查表点必须为原生数值，不能是BOOL或文本')
    if type(value) is int and not -(1 << 63) <= value < (1 << 64):
        raise ValueError('查表整数超出64位范围')
    converted = float(value)
    if not isfinite(converted) or converted != value:
        raise ValueError('查表点必须可由有限float64精确表示')
    return converted


@dataclass(frozen=True)
class LookupTablePlan:
    """保存经校验的有限标定点。身份保留原生数字类型、单位和每一点的次序。"""

    name: str
    points: tuple[tuple[int | float, int | float], ...]
    input_unit: str
    unit: str
    dtype: D = field(init=False)
    identity: str = field(init=False)

    def __post_init__(self):
        """校验轴和阶梯输出的共同类型。参数: 无。返回: 无。异常: 类型、单位、次序、大小或精度错误。"""
        require_identifier(self.name, 'lookup.name')
        if resolve_unit(self.input_unit) is None or resolve_unit(self.unit) is None:
            raise ValueError('查表输入/输出须声明已登记的数值单位')
        if type(self.points) is not tuple or not 2 <= len(self.points) <= MAX_POINTS:
            raise ValueError(f'查表points需要2至{MAX_POINTS}个冻结点对')
        previous, low, high, floating = None, 0, 0, False
        for row in self.points:
            if type(row) is not tuple or len(row) != 2:
                raise ValueError('查表points须为输入/输出的二元点对')
            x, y = row
            axis = _exact_f64(x)
            if previous is not None and axis <= previous:
                raise ValueError('查表轴须严格递增且不允许重复')
            previous = axis
            if type(y) is float:
                _exact_f64(y)
                floating = True
            elif type(y) is int and -(1 << 63) <= y < (1 << 64):
                low, high = min(low, y), max(high, y)
            else:
                raise ValueError('查表输出须为有限浮点数或64位整数')
        # 整数阶梯不经过 float64，可以无损保存 uint64 最大值。
        if floating:
            for _, y in self.points:
                _exact_f64(y)
            dtype = D.FLOAT64
        elif high < (1 << 63):
            dtype = D.INT64
        elif low >= 0:
            dtype = D.UINT64
        else:
            raise ValueError('查表输出负数与大uint64无法共用定宽整数类型')
        object.__setattr__(self, 'dtype', dtype)
        # 延迟导入避免基础绑定依赖查表声明时循环加载。
        from .binding import _identity
        payload = ('lookup-table-v1', self.name, self.input_unit, self.unit, self.points)
        object.__setattr__(self, 'identity', sha256(_identity(payload).encode('utf-8')).hexdigest())

    def prepare(self, mode, bounds):
        """校验查表调用，不生成数值列。参数: 插值/越界模式。返回: PreparedLookup。异常: 模式或精度错误。"""
        if mode not in ('linear', 'previous', 'next') or bounds not in ('invalid', 'clamp'):
            raise ValueError('lookup仅支持linear/previous/next以及invalid/clamp')
        dtype = D.FLOAT64 if mode == 'linear' else self.dtype
        if dtype is D.FLOAT64 and self.dtype is not D.FLOAT64:
            for _, y in self.points:
                _exact_f64(y)
        return PreparedLookup(self.identity, mode, bounds, dtype, self.points)


@dataclass(frozen=True)
class PreparedLookup:
    """保存已校验的模式和冻结点引用；实际数组执行者可单独持有只读打包列。"""

    identity: str
    mode: str
    bounds: str
    dtype: D
    points: tuple = field(repr=False, compare=False)
    axis: bytes | None = field(default=None, repr=False, compare=False)
    values: bytes | None = field(default=None, repr=False, compare=False)

    def packed(self):
        """产生只读数组视图的底层列。参数: 无。返回: 定宽两列的执行副本。异常: 分配错误。"""
        if self.axis is not None:
            return self
        axis, values = bytearray(8 * len(self.points)), bytearray(8 * len(self.points))
        for index, (x, y) in enumerate(self.points):
            _FORMATS[D.FLOAT64].pack_into(axis, 8 * index, x)
            _FORMATS[self.dtype].pack_into(values, 8 * index, y)
        return replace(self, axis=bytes(axis), values=bytes(values))

    def axis_at(self, index):
        """按序号读取物理坐标。参数: 合法索引。返回: float。异常: 非法索引。"""
        return float(self.points[index][0])

    def value_at(self, index):
        """按序号读取定宽值。参数: 合法索引。返回: 原生int或float。异常: 非法索引。"""
        y = self.points[index][1]
        return float(y) if self.dtype is D.FLOAT64 else y


def pack_requested_lookups(expression):
    """只为实际执行的根建立数组查表列。参数: 执行者的表达式。返回: 局部执行副本。异常: 分配错误。

    共用同一配置及模式的调用只打包一次。未消费的派生定义不会进入此根，原声明保持不可变。
    """
    if not expression.bindings.lookups:
        return expression
    nodes, tables = {}, {}

    def visit(node):
        """改写本根的查表节点。参数: 原节点。返回: 原节点或带执行列的副本。异常: 分配错误。"""
        if id(node) not in nodes:
            args = tuple(visit(child) for child in node.args)
            if node.operator == 'lookup':
                if node.value not in tables:
                    tables[node.value] = node.value.packed()
                changed = replace(node, args=args, value=tables[node.value])
            elif any(a is not b for a, b in zip(args, node.args)):
                changed = replace(node, args=args)
            else:
                changed = node
            nodes[id(node)] = changed
        return nodes[id(node)]

    root = visit(expression.root)
    return expression if root is expression.root else replace(expression, root=root)


def validate_lookups(tables, version):
    """检查有限表集合。参数: 冻结表元组和配置版本。返回: 无。异常: 非v4、重复名或表过多。"""
    if type(tables) is not tuple or any(type(table) is not LookupTablePlan for table in tables):
        raise TypeError('lookups需为LookupTablePlan tuple')
    if tables and version != 4:
        raise ValueError('lookups需要config_version=4')
    if len(tables) > MAX_TABLES or len({t.name for t in tables}) != len(tables):
        raise ValueError(f'lookups表名须唯一且最多{MAX_TABLES}张')
