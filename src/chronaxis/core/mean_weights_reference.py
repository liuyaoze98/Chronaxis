"""复用标量均值的先归一化再相乘规则，避免先求面积导致溢出。"""

from math import isfinite
from .types import QualityFlag as Q


def normalized_mean_terms(values, weights, denominator):
    """将有限有效值按整窗正分母加权，返回原序项和计算质量。

    参数: 同长有效数值/正权重序列，denominator为已核实总权重。
    返回: (tuple, QualityFlag)。异常: 结构或分配错误传播；非有限/下溢标质量。
    """
    try:
        if len(values) != len(weights) or not isfinite(denominator) or denominator <= 0:
            raise ValueError('均值需要同长输入和有限正分母')
        terms, quality = [], Q.NONE
        for value, weight in zip(values, weights):
            if not isfinite(value) or not isfinite(weight) or weight <= 0:
                raise ValueError('均值回读需要有限数值和正权重')
            term = value * (weight / denominator)
            failure = Q.NONFINITE if not isfinite(term) else Q.PRECISION_LOSS if term == 0 and value != 0 else Q.NONE
            quality |= failure
            terms.append(term if failure == Q.NONE else 0.0)
        return tuple(terms), quality
    finally:
        # 保留原异常，断开本帧借用列，避免调用方保存traceback时延长其生命周期。
        values = weights = terms = None
