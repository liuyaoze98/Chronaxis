"""用原dtype列、局部时间和中心化NumPy归约计算差分与等权拟合。

仅运行当前窗口，整数先在无符号幅度列计算精确差，再按IEEE表示检查提升。
拟合使用整列点积，最终只对两个标量归约结果还原倍率、秒与输出质量。
"""

import numpy as np
from .numeric import ScalarValue
from .numeric_numpy import DTYPES, _output, to_float_numpy
from .types import QualityFlag as Q, SignalDType as D


def _relative_column(samples):
    """将已知数值打包为相对首样本的浮点列，给出纵轴缩放的二进制指数。

    参数: samples为同型有效ScalarValue序列。返回: (相对列,指数,质量)。
    异常: 内存分配或内部结构错误传播。整数差转float不精确时返回精度质量。
    """
    dtype = samples[0].dtype
    raw = np.fromiter((v.value for v in samples),dtype=DTYPES[dtype],count=len(samples))
    if dtype is D.FLOAT64:
        # 先按2的幂缩放，异号相减不会产生无穷；单位倍率最后一次恢复。
        _, power = np.frexp(np.max(np.abs(raw)))
        scaled = np.ldexp(raw,-int(power))
        return scaled - scaled[0], int(power), Q.NONE
    # 对有符号整数翻转符号位后，uint64比较顺序恰好等于原带符号大小。
    ordered = raw.view(np.uint64)
    if dtype is D.INT64:
        ordered = ordered ^ np.uint64(1 << 63)
    base = ordered[0]
    magnitudes = np.maximum(ordered,base) - np.minimum(ordered,base)
    converted = to_float_numpy(_output(D.UINT64,magnitudes,np.zeros(len(samples),dtype=np.uint16)))
    quality = Q(int(np.bitwise_or.reduce(converted.quality,initial=0)))
    return np.where(ordered < base,-converted.values,converted.values), 0, quality


def _restore(numerator, denominator, exponent, elapsed_ns):
    """还原局部纵轴数量级与所选纳秒跨度，不在中间乘法中溢出。

    参数: 前两项为浮点归约的分子分母；exponent为纵轴2的幂；elapsed_ns为正数。
    返回: FLOAT64 ScalarValue。异常: 不可表示的最终数值以质量标识。
    """
    a,b = float(numerator).as_integer_ratio()
    c,d = float(denominator).as_integer_ratio()
    top = a * d * 1_000_000_000 * elapsed_ns.denominator
    bottom = b * c * elapsed_ns.numerator
    if exponent > 0:
        top <<= exponent
    else:
        bottom <<= -exponent
    try:
        value = top / bottom
    except OverflowError:
        return ScalarValue(None,D.FLOAT64,False,Q.NONFINITE)
    if value == 0 and top:
        return ScalarValue(None,D.FLOAT64,False,Q.PRECISION_LOSS)
    return ScalarValue(value,D.FLOAT64)


def difference_numpy(left, right, elapsed_ns):
    """以原dtype两点列求差，恢复为所选周期或实际秒数上的导数。

    参数: 同型有效的left/right及正elapsed_ns。返回: FLOAT64 ScalarValue。
    异常: 输入结构和分配错误传播。
    """
    values, exponent, quality = _relative_column((left,right))
    if quality:
        return ScalarValue(None,D.FLOAT64,False,quality)
    return _restore(values[-1],1.,exponent,elapsed_ns)


def fit_numpy(positions, samples):
    """将实际或周期横轴先局部化，用整列中心积求等权回归斜率。

    参数: positions为严格递增精确纳秒序列，samples为同行序有效样本。
    返回: FLOAT64 ScalarValue。异常: 结构和空间错误传播。
    """
    first, span = positions[0], positions[-1]-positions[0]
    if (all(type(t) is int for t in positions) and -(1 << 63) <= first
            and positions[-1] < (1 << 63) and span < (1 << 63)):
        # 普通实际时间在int64域先相减，靠近纪元上限的1ns仍然可区分。
        axis = np.asarray(positions,dtype=np.int64)
        x = (axis - axis[0]).astype(np.float64) / span
    else:
        # 介于两个驱动记录间的位置具有有理数表示，先在精确域移除起点；
        # 只打包相对坐标，后续中心化和每个样本的乘法均执行整列运算。
        x = np.fromiter((float((t-first)/span) for t in positions),dtype=np.float64,count=len(positions))
    y, exponent, quality = _relative_column(samples)
    if quality:
        return ScalarValue(None,D.FLOAT64,False,quality)
    x -= np.mean(x)
    y -= np.mean(y)
    return _restore(np.dot(x,y),np.dot(x,x),exponent,span)
