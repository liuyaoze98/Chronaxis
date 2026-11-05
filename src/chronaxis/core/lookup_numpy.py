"""通过 NumPy searchsorted 为整批活动样本查表并计算线性或阶梯输出。

从冻结字节借用小端定宽列，不为每个样本或批次复制标定表。输入先按
既有无损规则转为浮点轴，只有有效且位于开区间内部时才执行插值。
临时列随本批行数增长，不调用标量核，也不改变输入与其质量。
"""

import numpy as np
from .numeric_numpy import DTYPES, NumericArray, to_float_numpy
from .types import QualityFlag as Q


def lookup_numpy(table, value):
    """批量查表。参数: 已准备表和一维数值列。返回: 同长的表值列。异常: 类型、分配或布局错误。"""
    x = to_float_numpy(value)
    # 低层直接数组 API 没有流式 owner 时只持有本批打包列；驱动所有者复用自己的执行副本。
    table = table.packed()
    axis = np.frombuffer(table.axis, dtype='<f8')
    nodes = np.frombuffer(table.values, dtype=DTYPES[table.dtype].newbyteorder('<'))
    quality = x.quality.copy()
    values = np.zeros(len(x.values), dtype=DTYPES[table.dtype])
    # 输入缺失时不读取其占位值。精确节点包括闭端点，三种模式使用同一组比较。
    rows = np.flatnonzero(x.valid)
    query = x.values[rows]
    hi = np.searchsorted(axis, query, side='left')
    safe_hi = np.minimum(hi, len(axis) - 1)
    hit = query == axis[safe_hi]
    values[rows[hit]] = nodes[safe_hi[hit]]
    outside = ~hit & ((hi == 0) | (hi == len(axis)))
    if table.bounds == 'clamp':
        values[rows[outside]] = nodes[safe_hi[outside]]
    else:
        quality[rows[outside]] |= int(Q.OUT_OF_RANGE)
    inside = ~hit & ~outside
    rows, query, hi = rows[inside], query[inside], hi[inside]
    if table.mode != 'linear':
        values[rows] = nodes[hi - 1 if table.mode == 'previous' else hi]
    else:
        # 仅运算内部点；先标记非有限轴差，再区分内部点坐标折叠与正常端点。
        left, right = axis[hi - 1], axis[hi]
        y0, y1 = nodes[hi - 1], nodes[hi]
        flat = y0 == y1
        values[rows[flat]] = y0[flat]
        rows, query, left, right = rows[~flat], query[~flat], left[~flat], right[~flat]
        y0, y1 = y0[~flat], y1[~flat]
        with np.errstate(over='ignore', invalid='ignore', under='ignore'):
            span = right - left
            fraction = (query - left) / span
            same_sign = (y0 >= 0) == (y1 >= 0)
            result = np.empty_like(fraction)
            result[same_sign] = y0[same_sign] + fraction[same_sign] * (y1[same_sign] - y0[same_sign])
            result[~same_sign] = (1.0 - fraction[~same_sign]) * y0[~same_sign] + fraction[~same_sign] * y1[~same_sign]
        finite = np.isfinite(span) & np.isfinite(result)
        loss = finite & ((fraction == 0.0) | (fraction == 1.0))
        quality[rows[~finite]] |= int(Q.NONFINITE)
        quality[rows[loss]] |= int(Q.PRECISION_LOSS)
        keep = finite & ~loss
        values[rows[keep]] = result[keep]
    return NumericArray(table.dtype, values, quality == 0, quality)
