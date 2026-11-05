"""用标量二分搜索一维表，精确命中和两种阶梯模式直接取节点原值。

输入为编译节点保存的不可变表和已换到输入轴单位的标量。线性模式只在
严格内部点做浮点运算，无效输入、越界和非有限中间运算保留各自原因。
独立参考实现不导入 NumPy，不保存时序状态。
"""

from math import isfinite
from .numeric import ScalarValue, to_float_reference
from .types import QualityFlag as Q


def lookup_reference(table, value):
    """查询一个标量。参数: 已准备表和数值输入。返回: 表单位对应的标量。异常: 非法声明类型。"""
    x = to_float_reference(value)
    if not x.valid:
        return ScalarValue(None, table.dtype, False, x.quality)
    count = len(table.points)
    lo, hi = 0, count
    while lo < hi:
        middle = (lo + hi) // 2
        if table.axis_at(middle) < x.value:
            lo = middle + 1
        else:
            hi = middle
    # 精确命中先返回节点，极大端点不会因相邻差溢出丢失。
    if lo < count and table.axis_at(lo) == x.value:
        return ScalarValue(table.value_at(lo), table.dtype)
    if lo == 0 or lo == count:
        if table.bounds == 'invalid':
            return ScalarValue(None, table.dtype, False, Q.OUT_OF_RANGE)
        return ScalarValue(table.value_at(0 if lo == 0 else count - 1), table.dtype)
    if table.mode != 'linear':
        return ScalarValue(table.value_at(lo - 1 if table.mode == 'previous' else lo), table.dtype)
    # 有限的极端坐标相减仍可能溢出；不能因随后除以无穷而静默得到端点。
    left, right = table.axis_at(lo - 1), table.axis_at(lo)
    y0, y1 = table.value_at(lo - 1), table.value_at(lo)
    if y0 == y1:
        return ScalarValue(y0, table.dtype)
    span = right - left
    if not isfinite(span):
        return ScalarValue(None, table.dtype, False, Q.NONFINITE)
    fraction = (x.value - left) / span
    if fraction == 0.0 or fraction == 1.0:
        return ScalarValue(None, table.dtype, False, Q.PRECISION_LOSS)
    # 同号用差值式，异号用加权和，避免相减溢出或等号端点无故改变。
    result = (y0 + fraction * (y1 - y0) if (y0 >= 0) == (y1 >= 0) else
              (1.0 - fraction) * y0 + fraction * y1)
    return (ScalarValue(result, table.dtype) if isfinite(result) else
            ScalarValue(None, table.dtype, False, Q.NONFINITE))
