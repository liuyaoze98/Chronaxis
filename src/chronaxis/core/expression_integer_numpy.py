"""整列处理64位取余、位操作和精确转整数，保留每行无效原因。

输入是已统一类型的NumericArray和编译期位号。先用掩码排除危险除法、
越界和精度失败，再在可表示范围内执行NumPy运算。所有结果均为同长列。
"""

import numpy as np
from .numeric_numpy import DTYPES, _output
from .types import QualityFlag as Q, SignalDType as D


def integer_numpy(node, args):
    """在有效行上对数值列执行已编译的整数操作。

    参数: node提供操作/输出dtype/位范围，args为同长(N,)的NumericArray。
    返回: 同长结果列，输入无效位与本次产生的逐行原因保留。
    异常: ValueError为未知内部节点。分配异常原样传播。
    """
    value = args[0]
    source = value.values
    quality = value.quality.copy()
    result = np.zeros(len(quality), dtype=DTYPES[node.dtype])
    if node.operator == 'mod':
        divisor = args[1]
        quality |= divisor.quality
        quality[(quality == 0) & (divisor.values == 0)] |= np.uint16(Q.DOMAIN_ERROR)
        selected = quality == 0
        if value.dtype is D.INT64:
            # INT64_MIN / -1的商会越界，但要求的余数精确为零。该点用初始0，
            # 不向机器有符号除法传入这对参数。
            selected &= ~((source == np.iinfo(np.int64).min) & (divisor.values == -1))
        np.remainder(source, divisor.values, out=result, where=selected)
    elif node.operator in ('bit_test', 'bit_extract'):
        # view重解释符号位而不做浮点或算术转换。全宽mask恰好是uint64最大值。
        start, width = node.value
        bits = np.right_shift(source.view(np.uint64), np.uint64(start)) & np.uint64((1 << width) - 1)
        result[value.valid] = bits[value.valid]
    elif node.operator in ('to_int64', 'to_uint64'):
        # 转换前在源dtype中判界，2^63/2^64是float64能精确表示的开区间端点。
        if value.dtype is D.FLOAT64:
            # 避免对无效行原来的NaN等占位作浮点运算。小数优先报精度原因，
            # 其余整数值用可精确表示的半开区间比较，不能先astype后判界。
            valid = value.valid
            numbers = source[valid]
            lower, limit = (-float(1 << 63), float(1 << 63)) if node.dtype is D.INT64 else (0., float(1 << 64))
            fractional = numbers != np.trunc(numbers)
            flags = np.zeros(len(numbers), dtype=np.uint16)
            flags[fractional] = np.uint16(Q.PRECISION_LOSS)
            flags[~fractional & ((numbers < lower) | (numbers >= limit))] = np.uint16(Q.OVERFLOW)
            quality[valid] = flags
        elif value.dtype is D.INT64 and node.dtype is D.UINT64:
            quality[value.valid & (source < 0)] |= np.uint16(Q.OVERFLOW)
        elif value.dtype is D.UINT64 and node.dtype is D.INT64:
            quality[value.valid & (source >= np.uint64(1 << 63))] |= np.uint16(Q.OVERFLOW)
        # 只对已核实可表示的源位置转换，溢出或NaN占位不会进入astype。
        selected = quality == 0
        result[selected] = source[selected].astype(result.dtype)
    else:
        raise ValueError('未登记的整数操作')
    return _output(node.dtype, result, quality)
