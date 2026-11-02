"""以独立NumPy运算执行均值权重归一化，不调用标量数值核。"""

import numpy as np
from .types import QualityFlag as Q


def normalized_mean_terms(values, weights, denominator):
    """对有限数值列先除整窗正分母再乘值，返回只读项和质量。

    参数: 同形一维有效值/权重数组及已核实正分母。返回: (ndarray, QualityFlag)。
    异常: 结构或分配错误传播；非有限和非零下溢记质量，不修补结果。
    """
    try:
        if values.ndim != 1 or weights.shape != values.shape or not np.isfinite(denominator) or denominator <= 0:
            raise ValueError('均值需要同形一维输入和有限正分母')
        if np.any(~np.isfinite(values)) or np.any(~np.isfinite(weights)) or np.any(weights <= 0):
            raise ValueError('均值回读需要有限数值和正权重')
        with np.errstate(over='ignore', under='ignore', invalid='ignore'):
            terms = np.multiply(values, weights / denominator)
        quality = Q.NONE
        if np.any(~np.isfinite(terms)):
            quality |= Q.NONFINITE
        if np.any((terms == 0) & (values != 0)):
            quality |= Q.PRECISION_LOSS
        terms.setflags(write=False)
        return terms, quality
    finally:
        # 保留原异常，断开本帧借用列，避免调用方保存traceback时延长其生命周期。
        values = weights = terms = None
