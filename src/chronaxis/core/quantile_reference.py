"""在标量原dtype域排序并对唯一一对相邻样本作精确加权插值。"""

from fractions import Fraction
from itertools import chain
from .numeric import _exact_float
from .types import QualityFlag as Q


def ordered_reference(chunks, index, remainder, denominator):
    """在全部已选标量中定位顺序统计值，再计算线性插值。

    参数: chunks为不重叠的已选原值块；index为下秩，余数/分母给出上秩权重。
    返回: (数值或None,质量)，精确秩保持原dtype。
    异常: 排序需要的内存由调用方预付，分配错误直接传播。
    """
    ordered = None
    try:
        # 仅精确秩才直接返回整数；其他情况先证明两个端点能精确进入浮点域。
        ordered = sorted(chain.from_iterable(chunks))
        lo = ordered[index]
        if not remainder:
            return lo, Q.NONE
        hi = ordered[index + 1]
        left, qa = _exact_float(lo)
        right, qb = _exact_float(hi)
        if qa or qb:
            return None, qa | qb
        # 两个有限端点的凸组合仍在其范围内，使用精确分数避免异号差溢出及消去。
        exact = (Fraction(left) * (denominator - remainder) + Fraction(right) * remainder) / denominator
        value = float(exact)
        if (value == 0 and exact) or (type(lo) is int and exact.denominator == 1 and int(value) != exact):
            return None, Q.PRECISION_LOSS
        return value, Q.NONE
    finally:
        # 费用由外层释放；本层回溯只保留错误位置，不继续占用排序副本。
        # chunks 是借用输入，只断开本层参数，不修改或清空调用者的数据。
        chunks = ordered = None
