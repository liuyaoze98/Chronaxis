"""在单点64位整数与浮点输入上执行取余、位提取和精确转整数。

输入为已编译节点与typed标量元组。Python整数保存精确的中间数，
判定范围后才构造目标ScalarValue。转float复用公共精度检查。
"""

from .numeric import INTEGER_BOUNDS, ScalarValue
from .types import QualityFlag as Q


def integer_reference(node, args):
    """在标量域执行节点，拒绝0除数、整型范围外或有小数部分的转换。

    参数: node提供操作、静态dtype与必要的位范围，args为ScalarValue。
    返回: ScalarValue，质量非零时不产生有效值。
    异常: ValueError为未登记的内部操作；有效输入的数值失败写入质量。
    """
    quality = Q.NONE
    for arg in args:
        quality |= arg.quality
    if quality != Q.NONE:
        return ScalarValue(None, node.dtype, False, quality)
    value = args[0].value
    if node.operator == 'mod':
        divisor = args[1].value
        if divisor == 0:
            return ScalarValue(None, node.dtype, False, Q.DOMAIN_ERROR)
        # 原生整数余数随除数符号；INT64_MIN % -1为0，不构造越界商。
        result = value % divisor
    elif node.operator in ('bit_test', 'bit_extract'):
        # 即使原数为负，也只解释其低64位补码，bit0始终是最低位。
        start, width = node.value
        result = ((value & ((1 << 64) - 1)) >> start) & ((1 << width) - 1)
        if node.operator == 'bit_test':
            result = bool(result)
    elif node.operator in ('to_int64', 'to_uint64'):
        # 精确整数比较不把2^63-1或2^64-1先近似为float64。
        if type(value) is float and not value.is_integer():
            return ScalarValue(None, node.dtype, False, Q.PRECISION_LOSS)
        lo, hi = INTEGER_BOUNDS[node.dtype]
        if not lo <= value <= hi:
            return ScalarValue(None, node.dtype, False, Q.OVERFLOW)
        result = int(value)
    else:
        raise ValueError('未登记的整数操作')
    return ScalarValue(result, node.dtype)
