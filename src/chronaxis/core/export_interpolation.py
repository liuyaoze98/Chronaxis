"""计算离线导出的线性值；不改变分析中的向后保持、事件或积分语义。

调用方已确定相邻有效端点、范围及最大间隔。参考实现用精确有理数计算后转
float64；NumPy实现以一维longdouble数组计算后转float64，计算内核独立。
整数纳秒先作精确相对差，避免把很大的绝对时间直接转浮点。输出为估计值，
不声称恢复真实观测；无文件、预算或全局状态。
"""

from fractions import Fraction
from math import isfinite
import numpy as np


def linear_reference(times, left_ns, right_ns, left_value, right_value):
    """独立标量线性参考。参数: times有限ns tuple、相邻端点时间/数值。返回: float tuple。

    异常: 时间/数值非法或结果不有限；只接受严格位于两个端点之间的目标。
    """
    if (not left_ns < right_ns or any(not left_ns < t < right_ns for t in times)
            or not isfinite(left_value) or not isfinite(right_value)):
        raise ValueError('插值需要有效有序两端与内部目标')
    left,right = Fraction(left_value),Fraction(right_value)
    result = tuple(float(left+(right-left)*Fraction(t-left_ns,right_ns-left_ns)) for t in times)
    if any(not isfinite(value) for value in result):
        raise ValueError('插值结果非有限')
    return result


def linear_numpy(times, left_ns, right_ns, left_value, right_value):
    """独立数组线性计算。参数: 同reference。返回: shape(N,) float64 ndarray。

    异常: 时间/值非法或结果不有限；数组副本限当前有限块，不使用object数组。
    """
    if (not left_ns < right_ns or any(not left_ns < t < right_ns for t in times)
            or not isfinite(left_value) or not isfinite(right_value)):
        raise ValueError('插值需要有效有序两端与内部目标')
    # 先精确减绝对坐标再装箱，按相同时间权重对整块执行真实数组运算。
    relative = np.asarray([t-left_ns for t in times],dtype=np.longdouble)
    span=np.longdouble(right_ns-left_ns)
    left,right=np.longdouble(left_value),np.longdouble(right_value)
    # Windows longdouble可能就是float64；用较近端点的增量，减少两项乘法及抵消误差。
    # 两个合法极大有限端点的差可能溢出，只在该明确中间状态采用凸组合。
    with np.errstate(over='ignore'):
        difference=right-left
    if np.isfinite(difference):
        from_right=np.asarray([right_ns-t for t in times],dtype=np.longdouble)
        values=np.where(relative<=from_right,left+difference*(relative/span),
                        right-difference*(from_right/span)).astype(np.float64)
    else:
        alpha=relative/span
        values=np.asarray((1-alpha)*left+alpha*right,dtype=np.float64)
    if not np.all(np.isfinite(values)):
        raise ValueError('插值结果非有限')
    return values
