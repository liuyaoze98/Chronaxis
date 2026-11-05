"""在NumPy列上执行极值、限幅与开方，结果与质量均按行输出。

输入为已通过表达式编译器统一数值类型/尺度的等长列。运算沿同一行跨参数
择值或开方；掩码控制无效位置。没有逐样本Python循环，不修改借用输入。
"""

import numpy as np
from .numeric_numpy import _output, to_float_numpy
from .types import QualityFlag as Q, SignalDType as D


def math_numpy(name, args):
    """用掩码和ufunc求同长数值列的逐行结果。

    参数: name为编译好的函数名；args为同长NumericArray元组。
    返回: 同行数NumericArray，开方返回FLOAT64，其余保持公共dtype。
    异常: ValueError为内部未注册名称。内存分配异常直接传播。
    """
    value = args[0]
    quality = value.quality.copy()
    if name == 'sqrt':
        # 负值直接归类为DOMAIN_ERROR；仅非负有效整数才进入精确float转换。
        quality[value.valid & (value.values < 0)] |= np.uint16(Q.DOMAIN_ERROR)
        converted = to_float_numpy(_output(value.dtype, value.values, quality))
        out = np.zeros(len(quality), dtype=np.float64)
        np.sqrt(converted.values, out=out, where=converted.valid)
        return _output(D.FLOAT64, out, converted.quality)
    for arg in args[1:]:
        quality |= arg.quality
    out = value.values.copy()
    if name == 'clip':
        # 只要两条边界均可用即可诊断倒置，即便当前输入也有其他质量原因。
        lower, upper = args[1:]
        bad = lower.valid & upper.valid & (lower.values > upper.values)
        quality[bad] |= np.uint16(Q.DOMAIN_ERROR)
        valid = quality == 0
        np.copyto(out, lower.values, where=valid & (value.values < lower.values))
        np.copyto(out, upper.values, where=valid & (value.values > upper.values))
    elif name in ('minimum', 'maximum'):
        # 循环只遍历静态参数，每次比较整列；严格比较使相等值保留第一参数的符号。
        valid = quality == 0
        compare = np.less if name == 'minimum' else np.greater
        for arg in args[1:]:
            np.copyto(out, arg.values, where=valid & compare(arg.values, out))
    else:
        raise ValueError('未注册的逐点数值函数')
    return _output(value.dtype, out, quality)
