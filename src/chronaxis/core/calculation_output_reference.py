"""将一个已归约的数值换到目标单位，保留空值和数值质量。

输入为标量归约结果、原类型和编译期转换；输出数值及质量标志。
复用参考仿射核，在归约结束后只换算一次，不重算样本，不读写文件。
"""

from .affine import affine_reference
from .numeric import ScalarValue
from .types import SignalDType as D, QualityFlag as Q


def convert_result_reference(value, input_dtype, conversion):
    """以参考数值核换算单个非空结果，合法温度抵消为零保持有效。

    参数: value为int/float或None；input_dtype为原数值类型；conversion为单位描述符。
    返回: (数值或None, QualityFlag)，失败不把结果当成正常零。
    异常: 非法模型或系数错误传播，数值范围错误由质量表示。
    """
    # 无样本的空值不能因为有温度偏移而产生数值。
    if value is None:
        return None, Q.NONE
    if conversion.factor == 1 and conversion.offset == 0:
        return value, Q.NONE
    dtype = D.FLOAT64 if type(value) is float else input_dtype
    converted = affine_reference(ScalarValue(value, dtype), conversion.factor,
                                 conversion.offset, conversion.dtype(dtype))
    return converted.value if converted.valid else None, converted.quality
