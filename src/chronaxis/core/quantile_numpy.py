"""为已付费的样本数组作原dtype全局排序，然后仅恢复两个标量端点。"""

import numpy as np
from .types import QualityFlag as Q


def ordered_numpy(chunks, index, remainder, denominator):
    """用NumPy原地堆排序得到顺序统计值，并从其精确比值一次舍入插值。

    参数: chunks为原dtype样本块，index为下秩，正分母与余数定义上秩权重。
    返回: (原生数值或None,质量)，整数端点不转float。
    异常: 预算由外层预付，数组分配或索引错误直接传播。
    """
    values = None
    try:
        # 连接只产生一个全长副本，堆排序原地执行，不把uint64先改成float64。
        values = np.concatenate(chunks)
        values.sort(kind='heapsort')
        lo = values[index].item()
        if not remainder:
            return lo, Q.NONE
        hi = values[index + 1].item()
        integer = type(lo) is int
        if integer and (int(float(lo)) != lo or int(float(hi)) != hi):
            return None, Q.PRECISION_LOSS
        # 排序和选择均在列上完成。只对这两个端点用整数比计算加权分子，避免
        # max_float - (-max_float)溢出；一次除法给出最终的float64舍入结果。
        a, b = lo.as_integer_ratio()
        c, d = hi.as_integer_ratio()
        numerator = a * d * (denominator - remainder) + c * b * remainder
        divisor = b * d * denominator
        value = numerator / divisor
        if (value == 0 and numerator) or (integer and numerator % divisor == 0 and int(value) != numerator // divisor):
            return None, Q.PRECISION_LOSS
        return value, Q.NONE
    finally:
        # 费用由外层释放；本层回溯只保留错误位置，不继续占用排序副本。
        # chunks 是借用输入，只断开本层参数，不修改或清空调用者的数据。
        chunks = values = None
