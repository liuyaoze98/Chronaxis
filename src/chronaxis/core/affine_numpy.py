"""按列执行单位的完整仿射转换，保持固定类型和逐位置质量掩码。

输入为 NumericArray、静态倍率/偏移与目标类型；输出形状保持(N,)的独立
只读 NumericArray。整数复用已有数组仿射核的精确逆区间算法；浮点使用
NumPy ufunc与有效掩码，不调用标量参考数值计算，不使用object数组或
逐样本Python回调。无效位置不参与运算，已有质量原因保留；不读写文件、
不改调用方数组、不保存样本历史。单位关系由表达式或结果编译器事先证明。
"""

# 共享静态声明检查；实际数组计算与标量参考分开。
from math import isfinite

import numpy as np

from .affine import _validate_affine
from .normalize_numpy import _affine_integer
from .numeric import INTEGER_BOUNDS
from .numeric_numpy import NumericArray, _output, to_float_numpy
from .types import QualityFlag, SignalDType


def _float_coefficient(value: int | float) -> tuple[float | None, QualityFlag]:
    """仅转换一个编译期系数，不对样本调用Python标量参考。

    参数: value为已验证的原生整数或有限浮点系数。
    返回: 有限浮点值与NONE，或None与NONFINITE/PRECISION_LOSS。
    异常: 无主动异常；整数超出浮点范围转换成NONFINITE。
    """
    # 配置常量数量固定，与样本数量无关；整数往返不能先舍入原整数。
    try:
        result = float(value)
    except OverflowError:
        return None, QualityFlag.NONFINITE
    if not isfinite(result):
        return None, QualityFlag.NONFINITE
    if type(value) is int and int(result) != value:
        return None, QualityFlag.PRECISION_LOSS
    return result, QualityFlag.NONE


def affine_numpy(value: NumericArray, scale: int | float, offset: int | float,
                 dtype: SignalDType) -> NumericArray:
    """在有效位置执行value*scale+offset，不以中间回绕或舍入替代结果。

    参数: value为(N,)数值列；scale、offset为有限静态系数；dtype为目标
        数值类型。整数目标要求整数输入和整数系数；需要小数时应声明float64。
    返回: 同长独立只读NumericArray；无效位置仅存零占位，原因保持或增加
        OVERFLOW、NONFINITE、PRECISION_LOSS。输入和有效/质量列不被修改。
    异常: TypeError/ValueError为声明结构错误；MemoryError等分配异常传播。
    边界: 温度偏移抵消为零有效；只有零偏移、非零因子的非零值变成零时，
        才按纯倍率下溢报告精度损失。全部数值操作按数组执行。
    """
    # 结构与静态目标类型错误不能悄悄当成数据缺失。
    if not isinstance(value, NumericArray):
        raise TypeError('仿射数组转换需要NumericArray')
    _validate_affine(value.dtype, dtype, scale, offset)
    # 整数复用已验数组算法，先求完整仿射的合法输入区间，再执行安全乘加。
    if dtype in INTEGER_BOUNDS:
        values, overflow = _affine_integer(value.values, value.valid, dtype, scale, offset)
        quality = value.quality.copy()
        quality[overflow] |= np.uint16(QualityFlag.OVERFLOW)
        return _output(dtype, values, quality)
    # 输入整数的精度用数组尾位掩码核实，不能先astype再与已舍入值比较。
    converted = to_float_numpy(value)
    quality = converted.quality.copy()
    factor, factor_quality = _float_coefficient(scale)
    shift, shift_quality = _float_coefficient(offset)
    coefficient_quality = factor_quality | shift_quality
    values = np.zeros(len(value.values), dtype=np.float64)
    # 系数精度失败影响原本有效的输入，保留同时发生的输入精度原因。
    if coefficient_quality != QualityFlag.NONE:
        quality[value.valid] |= np.uint16(coefficient_quality)
        return _output(dtype, values, quality)
    # ufunc只触碰通过精度检查的位置；中间浮点异常在完整结果上明确分类。
    selected = converted.valid
    with np.errstate(over='ignore', under='ignore', invalid='ignore'):
        np.multiply(converted.values, factor, out=values, where=selected)
        np.add(values, shift, out=values, where=selected)
    quality[selected & ~np.isfinite(values)] |= np.uint16(QualityFlag.NONFINITE)
    # 偏移抵消为零是合法数值，不将-273.15℃转换到0K标成下溢。
    if shift == 0 and factor != 0:
        underflow = selected & (converted.values != 0) & (values == 0)
        quality[underflow] |= np.uint16(QualityFlag.PRECISION_LOSS)
    return _output(dtype, values, quality)
