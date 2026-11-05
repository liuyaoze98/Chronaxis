"""逐点解释已统一dtype和单位的极值、限幅与平方根节点。

输入是白名单操作及本时刻的ScalarValue，输出保留必要输入及数值错误原因。
使用标准库标量计算；定宽平方在编译时展开为现有的精确乘法。
"""

from math import sqrt
from .numeric import ScalarValue, to_float_reference
from .types import QualityFlag as Q, SignalDType as D


def math_reference(name, args):
    """按标量数值协议执行一个极值、限幅或开方节点。

    参数: name为编译好的函数名，args为依次排列的ScalarValue。
    返回: ScalarValue；有效极值/限幅保持dtype，开方输出FLOAT64。
    异常: ValueError为内部未注册名称。缺失、倒置或开方不可计算表示为质量。
    """
    value = args[0]
    if name == 'sqrt':
        # 先在原数域判负，不把很大的负整数舍入或当作一般转换失败。
        if value.valid and value.value < 0:
            return ScalarValue(None, D.FLOAT64, False, Q.DOMAIN_ERROR)
        converted = to_float_reference(value)
        if not converted.valid:
            return converted
        return ScalarValue(sqrt(converted.value), D.FLOAT64)
    # 任何必要输入的既有异常都进入输出，不能静默少比较一个通道。
    quality = Q.NONE
    for arg in args:
        quality |= arg.quality
    if name == 'clip':
        lower, upper = args[1:]
        if lower.valid and upper.valid and lower.value > upper.value:
            quality |= Q.DOMAIN_ERROR
    if quality != Q.NONE:
        return ScalarValue(None, value.dtype, False, quality)
    # 相等时保留首操作数的表示（包括带符号零），两后端共用同一择值契约。
    if name == 'minimum':
        return min(args, key=lambda arg: arg.value)
    if name == 'maximum':
        return max(args, key=lambda arg: arg.value)
    if name == 'clip':
        if value.value < lower.value:
            return lower
        if value.value > upper.value:
            return upper
        return value
    raise ValueError('未注册的逐点数值函数')
