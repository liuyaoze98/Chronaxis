"""将一个已校验数值换到目标单位，执行一次完整的乘法与偏移转换。

输入为 ScalarValue、编译期确定的倍率/偏移和目标类型；输出仍为 ScalarValue。
整数在 Python 精确整数域计算最终结果，再检查目标定宽；浮点先检查整数
输入的可表示性，再计算并检查有限性与纯倍率下溢。未知值保持原质量原因，
不会因为乘零或加偏移变成正常数据。本模块不依赖 NumPy，不读取文件，
不改变输入，也不保存转换前后副本或跨批次状态。单位关系由编译器验证。
"""

# 只复用标量路径已有的数值模型和精度检查，不调用数组实现。
from math import isfinite

from .numeric import INTEGER_BOUNDS, ScalarValue, _exact_float
from .types import QualityFlag, SignalDType


def _validate_affine(source_dtype, dtype, scale, offset) -> None:
    """检查编译器传入的仿射转换结构，数值合法性仍逐样本处理。

    参数: source_dtype、dtype分别为输入和输出数值类型；scale、offset为
        原生整数或有限浮点数，不接受bool。整数输出要求输入和系数均为整数。
    返回: None，无副作用。
    异常: TypeError为非数值类型/系数；ValueError为非有限系数或错误类型提升。
    """
    # 逻辑值和枚举不能借单位转换隐式进入数值计算。
    numeric_types = (*INTEGER_BOUNDS, SignalDType.FLOAT64)
    if source_dtype not in numeric_types or dtype not in numeric_types:
        raise TypeError('仿射转换仅接受明确的数值类型')
    # 系数来自静态编译，坏配置不能伪装为所有样本缺失。
    if any(type(item) not in (int, float) for item in (scale, offset)):
        raise TypeError('仿射系数必须为原生int或float，不能为bool')
    if any(type(item) is float and not isfinite(item) for item in (scale, offset)):
        raise ValueError('仿射系数必须有限')
    # 需要小数的转换应在编译时提升，不随样本碰巧整除而改变输出类型。
    if dtype in INTEGER_BOUNDS and (source_dtype not in INTEGER_BOUNDS
                                   or type(scale) is not int or type(offset) is not int):
        raise ValueError('整型仿射目标需要整数输入及整数系数；请先确定float64提升')


def affine_reference(value: ScalarValue, scale: int | float, offset: int | float,
                     dtype: SignalDType) -> ScalarValue:
    """按value*scale+offset完成标量单位转换，并保留精度及有效性。

    参数: value为已校验数值；scale、offset为有限编译期系数；dtype为静态
        目标数值类型。整数目标只接整数输入和系数，浮点目标检查大整数精度。
    返回: ScalarValue；超定宽为OVERFLOW，浮点非有限为NONFINITE，不能精确
        转为浮点或纯倍率下溢到零为PRECISION_LOSS，输入无效则保留原原因。
    异常: TypeError或ValueError为声明结构错误；不将配置错误变成样本质量。
    边界: -273.15乘1再加273.15得到正常0；整数中间乘积可以超过64位，
        只要完整仿射结果仍在目标范围。无副作用，不保留转换历史。
    """
    # 公共入口不接受裸数或逻辑值；静态系数检查先于逐样本运算。
    if not isinstance(value, ScalarValue):
        raise TypeError('仿射参考转换需要ScalarValue')
    _validate_affine(value.dtype, dtype, scale, offset)
    # 无效输入不计算，偏移不能把缺失变成一个看似正常的温度。
    if not value.valid:
        return ScalarValue(None, dtype, False, value.quality)
    # 完整整数仿射使用无界中间整数，最后再核对目标定宽。
    if dtype in INTEGER_BOUNDS:
        result = value.value * scale + offset
        lower, upper = INTEGER_BOUNDS[dtype]
        if not lower <= result <= upper:
            return ScalarValue(None, dtype, False, QualityFlag.OVERFLOW)
        return ScalarValue(result, dtype)
    # 三个操作数分别检查精度；整数2**53+1不能因换单位而默默舍入。
    number, number_quality = _exact_float(value.value)
    factor, factor_quality = _exact_float(scale)
    shift, shift_quality = _exact_float(offset)
    quality = number_quality | factor_quality | shift_quality
    if quality != QualityFlag.NONE:
        return ScalarValue(None, dtype, False, quality)
    # 对整个仿射结果检查；零偏移时才用非零输入判断下溢，避免误伤温度抵消。
    result = number * factor + shift
    if not isfinite(result):
        return ScalarValue(None, dtype, False, QualityFlag.NONFINITE)
    if shift == 0 and result == 0 and number != 0 and factor != 0:
        return ScalarValue(None, dtype, False, QualityFlag.PRECISION_LOSS)
    return ScalarValue(result, dtype)
