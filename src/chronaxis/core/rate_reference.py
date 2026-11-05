"""用独立标量差分和中心化等权回归计算有效真实样本的每秒变化率。

相邻/窗口的两个端点只做一次精确差，再转浮点输出。拟合使用局部时间和按
二进制指数缩放的值，避免绝对时间精度损失及大温度/电压背景造成的相消。
没有跨调用状态，窗口、真实间隔有效性及临时预算由时间线调用者提供。
"""

from fractions import Fraction
from math import frexp, fsum, ldexp
from .numeric import ScalarValue, _exact_float
from .types import QualityFlag as Q, SignalDType as D


def _result(exact):
    """将已经得到的有限有理数转为一个每秒FLOAT64斜率。

    参数: exact为最终斜率。返回: ScalarValue，真溢出或下溢有独立原因。
    异常: 内存不足原样传播。
    """
    try:
        value = float(exact)
    except OverflowError:
        return ScalarValue(None,D.FLOAT64,False,Q.NONFINITE)
    if not value and exact:
        return ScalarValue(None,D.FLOAT64,False,Q.PRECISION_LOSS)
    return ScalarValue(value,D.FLOAT64)


def difference_reference(left, right, elapsed_ns):
    """按原值精确相减，再除以秒数，免去巨大相近整数的绝对值舍入。

    参数: 两个同型有效标量与正的精确纳秒跨度。返回: FLOAT64 ScalarValue。
    异常: 内部调用需先校验模型。不能精确进入浮点的整数差量报PRECISION_LOSS。
    """
    delta = Fraction(right.value) - Fraction(left.value)
    if left.dtype is not D.FLOAT64:
        _, reason = _exact_float(delta.numerator)
        if reason:
            return ScalarValue(None,D.FLOAT64,False,reason)
    # 数学凸/差值仅用于两个端点，避免极大异号值先相减溢出但最终斜率可表示。
    return _result(delta * 1_000_000_000 / elapsed_ns)


def fit_reference(positions, samples):
    """用局部时间、真实样本等权及补偿求和计算最小二乘斜率。

    参数: 严格递增的精确纳秒与至少两个同型有效样本。
    返回: FLOAT64 ScalarValue。异常: 内部结构错误传播，数值失效转为质量。
    """
    first, span = positions[0], positions[-1] - positions[0]
    # 先在精确坐标域去掉纪元，再缩到[0,1]，最大64位绝对时间不影响相邻差。
    x = [float(Fraction(t-first,span)) for t in positions]
    if samples[0].dtype is D.FLOAT64:
        exponent = frexp(max(abs(sample.value) for sample in samples))[1]
        base = ldexp(samples[0].value, -exponent)
        y = [ldexp(sample.value,-exponent) - base for sample in samples]
    else:
        # 精确相减后才提升，uint64也允许相对首值为负。
        exponent, y = 0, []
        for sample in samples:
            value, reason = _exact_float(sample.value - samples[0].value)
            if reason:
                return ScalarValue(None,D.FLOAT64,False,reason)
            y.append(value)
    mean_x, mean_y = fsum(x)/len(x), fsum(y)/len(y)
    cross = fsum((t-mean_x)*(v-mean_y) for t,v in zip(x,y))
    spread = fsum((t-mean_x)**2 for t in x)
    # 还原纵轴二进制倍率及横轴真实跨度时只做一次最终浮点舍入。
    return _result(Fraction(cross) * Fraction(2)**exponent * 1_000_000_000 / (Fraction(spread)*span))
