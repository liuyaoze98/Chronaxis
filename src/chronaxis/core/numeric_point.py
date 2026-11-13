"""生产逐点计算的定宽数值原语，不构造单元素数组。

输入是编译器已核实类型和单位的ScalarValue。输出保留数值类型、无效原因和
有限精度要求；整数用无界临时值验证定宽结果，float转换先检查有效尾位。
这些函数不调用参考数值实现，不读写来源，也不持有跨点状态。
"""

from math import isfinite, sqrt
import operator

from .scalar import INTEGER_BOUNDS, ScalarValue
from .types import QualityFlag as Q, SignalDType as D, _QUALITY_BY_MASK

_COMPARE = {'eq': operator.eq, 'ne': operator.ne, 'lt': operator.lt,
            'le': operator.le, 'gt': operator.gt, 'ge': operator.ge}
_ARITHMETIC = {'add': operator.add, 'sub': operator.sub,
               'mul': operator.mul, 'div': operator.truediv}


def failed(dtype, quality, labels=()):
    """构造不可用结果。参数: 目标类型、真实原因、枚举域。返回: ScalarValue。异常: 模型合同错误。"""
    return ScalarValue(None, dtype, False, quality, labels)


def exact_float(value):
    """按整数幅度的有效尾位判断float64可表示性。

    参数: 原生int或float。返回: (有限float或None, 质量)。
    异常: 非数值结构错误；超大整数作为NONFINITE返回，不抛转换溢出。
    """
    if type(value) is float:
        return (value, Q.NONE) if isfinite(value) else (None, Q.NONFINITE)
    if type(value) is not int:
        raise TypeError('逐点浮点转换需要原生数值')
    magnitude = abs(value)
    shift = max(0, magnitude.bit_length() - 53)
    # 超出有限float64的幅度先归类，不能把无穷转换误报为一般精度失败。
    if magnitude.bit_length() > 1024:
        return None, Q.NONFINITE
    try:
        number = float(value)
    except OverflowError:
        return None, Q.NONFINITE
    if not isfinite(number):
        return None, Q.NONFINITE
    if shift and magnitude & ((1 << shift) - 1):
        return None, Q.PRECISION_LOSS
    return number, Q.NONE


def to_float_point(value):
    """无损转换当前数值。参数: ScalarValue。返回: FLOAT64值。异常: 非数值类型。"""
    if value.dtype not in (*INTEGER_BOUNDS, D.FLOAT64):
        raise TypeError('逐点浮点转换需要数值类型')
    if not value.valid:
        return failed(D.FLOAT64, value.quality)
    number, quality = exact_float(value.value)
    return failed(D.FLOAT64, quality) if quality else ScalarValue(number, D.FLOAT64)


def checked_result(number, dtype):
    """校验计算完成后的定宽范围或有限性。参数: 数值、静态类型。返回: typed值。异常: 非数值类型。"""
    if dtype in INTEGER_BOUNDS:
        lower, upper = INTEGER_BOUNDS[dtype]
        return (ScalarValue(number, dtype) if lower <= number <= upper
                else failed(dtype, Q.OVERFLOW))
    if dtype is D.FLOAT64:
        return ScalarValue(number, dtype) if isfinite(number) else failed(dtype, Q.NONFINITE)
    raise TypeError('逐点数值结果类型不合法')


def binary_point(op, left, right, dtype):
    """计算已通过静态类型检查的二元运算。

    参数: 固定操作名、两侧typed值、编译后的结果dtype。返回: ScalarValue。
    异常: 未登记操作或内部类型合同错误；除零和定宽失败转成质量。
    """
    quality = _QUALITY_BY_MASK[int(left.quality) | int(right.quality)]
    if quality:
        return failed(dtype, quality)
    if left.dtype is D.ENUM and left.labels != right.labels:
        raise ValueError('枚举比较需要相同标签域')
    a, b = left.value, right.value
    floating = dtype is D.FLOAT64 or op in _COMPARE and D.FLOAT64 in (left.dtype, right.dtype)
    if floating:
        a, aq = exact_float(a)
        b, bq = exact_float(b)
        quality = _QUALITY_BY_MASK[int(aq) | int(bq)]
        if quality:
            return failed(dtype, quality)
    # int64/uint64比较直接用精确整数，不经过NumPy混合提升或float。
    if op in _COMPARE:
        return ScalarValue(_COMPARE[op](a, b), D.BOOL)
    if op == 'div' and b == 0:
        return failed(dtype, Q.DOMAIN_ERROR)
    return checked_result(_ARITHMETIC[op](a, b), dtype)


def unary_point(op, value):
    """计算取负或绝对值。参数: 操作名、typed数值。返回: 同型值。异常: 未知操作。"""
    if not value.valid:
        return failed(value.dtype, value.quality)
    number = abs(value.value) if op == 'abs' else -value.value if op == 'neg' else None
    if number is None:
        raise ValueError('未登记的逐点单目运算')
    return checked_result(number, value.dtype)


def affine_point(value, scale, offset, dtype):
    """按完整value*scale+offset换算当前值，不进行第二次DBC换算。

    参数: 已编译的数值、系数和目标dtype。返回: ScalarValue。
    异常: 内部静态合同错误；数值失败保存为质量。
    """
    if not value.valid:
        return failed(dtype, value.quality)
    if dtype in INTEGER_BOUNDS:
        if value.dtype not in INTEGER_BOUNDS or type(scale) is not int or type(offset) is not int:
            raise ValueError('整数仿射转换需要整数输入及系数')
        return checked_result(value.value * scale + offset, dtype)
    number, nq = exact_float(value.value)
    factor, fq = exact_float(scale)
    shift, sq = exact_float(offset)
    quality = _QUALITY_BY_MASK[int(nq) | int(fq) | int(sq)]
    if quality:
        return failed(dtype, quality)
    result = number * factor + shift
    if not isfinite(result):
        return failed(dtype, Q.NONFINITE)
    # 偏移抵消为零合法，纯倍率把非零压成零才是精度丢失。
    if shift == 0 and factor != 0 and number != 0 and result == 0:
        return failed(dtype, Q.PRECISION_LOSS)
    return ScalarValue(result, dtype)


def logic_point(op, values):
    """按对称三值规则求布尔值。参数: 固定逻辑操作和typed值。返回: BOOL。异常: 未知操作。"""
    if op == 'not':
        value = values[0]
        return ScalarValue(not value.value, D.BOOL) if value.valid else failed(D.BOOL, value.quality)
    if op not in ('and', 'or'):
        raise ValueError('未登记的逐点逻辑操作')
    deciding = op == 'or'
    quality = Q.NONE
    for value in values:
        quality = _QUALITY_BY_MASK[int(quality) | int(value.quality)]
        if value.valid and value.value is deciding:
            return ScalarValue(deciding, D.BOOL)
    return failed(D.BOOL, quality) if quality else ScalarValue(not deciding, D.BOOL)


def math_point(op, values):
    """执行极值、限幅和开方。参数: 已统一类型/单位的实参。返回: typed结果。异常: 未知操作。"""
    first = values[0]
    if op == 'sqrt':
        if not first.valid:
            return failed(D.FLOAT64, first.quality)
        if first.value < 0:
            return failed(D.FLOAT64, Q.DOMAIN_ERROR)
        number = to_float_point(first)
        return number if not number.valid else ScalarValue(sqrt(number.value), D.FLOAT64)
    quality = Q.NONE
    for value in values:
        quality = _QUALITY_BY_MASK[int(quality) | int(value.quality)]
    if op == 'clip':
        lower, upper = values[1:]
        # 即使输入无效，只要两边界有效且倒置，也应保留这个域错误。
        if lower.valid and upper.valid and lower.value > upper.value:
            quality = _QUALITY_BY_MASK[int(quality) | int(Q.DOMAIN_ERROR)]
        if quality:
            return failed(first.dtype, quality)
        result = lower if first.value < lower.value else upper if first.value > upper.value else first
        return ScalarValue(result.value, first.dtype)
    if op not in ('minimum', 'maximum'):
        raise ValueError('未登记的逐点数值函数')
    if quality:
        return failed(first.dtype, quality)
    number = first.value
    compare = operator.lt if op == 'minimum' else operator.gt
    # 严格比较保留第一个相等参数及其负零符号。
    for value in values[1:]:
        if compare(value.value, number):
            number = value.value
    return ScalarValue(number, first.dtype)


def integer_point(node, values):
    """执行定宽取余、位操作和精确转整数。

    参数: 编译节点及typed实参。返回: 静态dtype结果。
    异常: 未知操作；小数、越界、零除保存对应质量。
    """
    value = values[0]
    quality = value.quality
    for item in values[1:]:
        quality = _QUALITY_BY_MASK[int(quality) | int(item.quality)]
    if quality:
        return failed(node.dtype, quality)
    number = value.value
    if node.operator == 'mod':
        divisor = values[1].value
        return failed(node.dtype, Q.DOMAIN_ERROR) if divisor == 0 else ScalarValue(number % divisor, node.dtype)
    if node.operator in ('bit_test', 'bit_extract'):
        start, width = node.value
        bits = ((number & ((1 << 64) - 1)) >> start) & ((1 << width) - 1)
        return ScalarValue(bool(bits) if node.dtype is D.BOOL else bits, node.dtype)
    if node.operator not in ('to_int64', 'to_uint64'):
        raise ValueError('未登记的逐点整数操作')
    if value.dtype is D.FLOAT64 and not number.is_integer():
        return failed(node.dtype, Q.PRECISION_LOSS)
    number = int(number)
    return checked_result(number, node.dtype)


def lookup_point(table, axis, nodes, value):
    """用准备期只读表视图查一个有效点，不建立单元素列。

    参数: 已核表、只读轴和值列、typed输入。返回: 表声明类型的值。
    异常: 静态表结构错误；范围、精度及非有限结果保存为质量。
    """
    query = to_float_point(value)
    if not query.valid:
        return failed(table.dtype, query.quality)
    x = query.value
    # searchsorted只返回标量下标；轴和值视图由计划持有，不在每点重建。
    hi = int(axis.searchsorted(x, side='left'))
    count = len(axis)
    index = min(hi, count - 1)
    if x == float(axis[index]):
        return ScalarValue(nodes[index].item(), table.dtype)
    if hi == 0 or hi == count:
        return (ScalarValue(nodes[index].item(), table.dtype) if table.bounds == 'clamp'
                else failed(table.dtype, Q.OUT_OF_RANGE))
    if table.mode != 'linear':
        return ScalarValue(nodes[hi - 1 if table.mode == 'previous' else hi].item(), table.dtype)
    left, right = float(axis[hi - 1]), float(axis[hi])
    y0, y1 = float(nodes[hi - 1]), float(nodes[hi])
    if y0 == y1:
        return ScalarValue(y0, table.dtype)
    span = right - left
    fraction = (x - left) / span
    # 同号避免不必要的乘加抵消；异号不形成可能溢出的y1-y0。
    result = (y0 + fraction * (y1 - y0) if (y0 >= 0) == (y1 >= 0)
              else (1.0 - fraction) * y0 + fraction * y1)
    if not isfinite(span) or not isfinite(result):
        return failed(table.dtype, Q.NONFINITE)
    if fraction == 0 or fraction == 1:
        return failed(table.dtype, Q.PRECISION_LOSS)
    return ScalarValue(result, table.dtype)
