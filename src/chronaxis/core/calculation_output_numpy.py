"""将一个数组归约结果换到目标单位，不调用参考数值核。

输入为归约标量、原类型和编译期转换；用单元素typed列复用数组仿射核，
输出值与质量。这里只转换最终结果，不按样本循环或创建额外历史。
"""

import numpy as np
from .affine_numpy import affine_numpy
from .numeric_numpy import NumericArray, DTYPES
from .types import SignalDType as D, QualityFlag as Q


def convert_result_numpy(value, input_dtype, conversion):
    """用NumPy仿射核完成一个非空结果的单位转换。

    参数: value为int/float或None；input_dtype为原数值类型；conversion为单位描述符。
    返回: (Python数值或None, QualityFlag)，空值保持空值。
    异常: 非法模型、分配或系数错误传播；数值故障写入质量。
    """
    # 空值没有数值证据，不为应用偏移制造一个零输入。
    if value is None:
        return None, Q.NONE
    if conversion.factor == 1 and conversion.offset == 0:
        return value, Q.NONE
    dtype = D.FLOAT64 if type(value) is float else input_dtype
    column = NumericArray(dtype, np.array([value], dtype=DTYPES[dtype]),
                          np.array([True]), np.array([0], dtype=np.uint16))
    converted = affine_numpy(column, conversion.factor, conversion.offset, conversion.dtype(dtype))
    return converted.values[0].item() if converted.valid[0] else None, Q(int(converted.quality[0]))
