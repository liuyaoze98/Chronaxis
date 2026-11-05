"""为三类时序变化率核对数值输入和单位，并选择逐点或数组后端。

时间线调用方提供有效边界值或窗口中的真实样本，以及实际/周期口径的相对
纳秒计量。此处不创建网格或驱动帧，不推断TTL、窗口完整性或max_gap。
输出为FLOAT64 ScalarValue，单位从输入的当前数值尺度和温度角色推导。
"""

from fractions import Fraction
from . import unit_registry as units
from .numeric import ScalarValue
from .types import QualityFlag as Q, SignalDType as D


def rate_unit(input_unit):
    """确定当前数值尺度的每秒自然单位，绝对温度先变为温差。

    参数: input_unit为已编译输入表达式的单位标签。
    返回: 可重新解析的单位，如V/s、mV/s、delta_K/s或Hz。
    异常: ValueError为未登记或非法单位，不以未知标签证明量纲。
    """
    source = units.resolve_unit(input_unit)
    if source is None:
        raise ValueError('变化率需要可推导的输入单位')
    # 先相减得到温差，摄氏/K之间的常量偏移不参与变化率。此目录中的两者温差倍率均为1。
    if source.temperature_role == 'absolute':
        source = units.resolve_unit('delta_K')
        input_unit = 'delta_K'
    natural = units.divide(source, units.resolve_unit('s'))
    return units.output_label(natural, input_unit + '/s')


def _quality(backend, samples):
    """检查已绑定的同型数值样本，并汇总全部必要输入的无效原因。

    参数: backend为reference或numpy，samples为有限样本序列。
    返回: 合并的QualityFlag。异常: TypeError/ValueError为模型或静态dtype不符。
    """
    if backend not in ('reference','numpy'):
        raise ValueError('变化率后端需要reference或numpy')
    combined = Q.NONE
    dtype = None
    for value in samples:
        if not isinstance(value, ScalarValue) or value.dtype not in (D.INT64,D.UINT64,D.FLOAT64):
            raise TypeError('变化率只接受有类型的数值样本')
        if dtype is not None and value.dtype is not dtype:
            raise ValueError('同一变化率序列的输入类型必须一致')
        dtype = value.dtype
        combined |= value.quality
    return combined


def _position(value):
    """校验内部实际纳秒或精确周期坐标，防止把大纪元时间先转浮点。

    参数: value为原生int或Fraction。返回: 原坐标。异常: TypeError为单位/类型不符。
    """
    if type(value) not in (int,Fraction):
        raise TypeError('变化率计量坐标须为精确int/Fraction纳秒')
    return value


def rate_difference(backend, left, right, elapsed_ns):
    """用两个边界值之差除以已选实际时间或折算周期跨度。

    参数: backend为数值后端，left/right为ScalarValue，elapsed_ns为精确纳秒。
    返回: FLOAT64数值或带原因的无效值，合法负斜率不受原无符号dtype限制。
    异常: 非数值、后端或坐标类型错误直接拒绝。非正跨度属于DOMAIN_ERROR。
    """
    quality = _quality(backend,(left,right))
    if _position(elapsed_ns) <= 0:
        quality |= Q.DOMAIN_ERROR
    if quality:
        return ScalarValue(None,D.FLOAT64,False,quality)
    if backend == 'reference':
        from .rate_reference import difference_reference
        return difference_reference(left,right,elapsed_ns)
    from .rate_numpy import difference_numpy
    return difference_numpy(left,right,elapsed_ns)


def rate_fit(backend, positions_ns, samples):
    """在至少两个不同时间的真实样本上求等权最小二乘斜率。

    参数: backend为数值后端，positions_ns为所选实际/周期口径纳秒序列，
        samples为同行序的ScalarValue。调用方已经完成同刻原子归组。
    返回: FLOAT64每秒斜率；少于两个样本为MISSING，非递增位置为DOMAIN_ERROR。
    异常: ValueError为长度不符，类型错误原样传播。
    """
    if len(positions_ns) != len(samples):
        raise ValueError('拟合坐标与真实样本数必须相等')
    quality = _quality(backend,samples)
    previous = None
    for position in positions_ns:
        if previous is not None and _position(position) <= previous:
            quality |= Q.DOMAIN_ERROR
        previous = _position(position)
    if len(samples) < 2:
        quality |= Q.MISSING
    if quality:
        return ScalarValue(None,D.FLOAT64,False,quality)
    if backend == 'reference':
        from .rate_reference import fit_reference
        return fit_reference(positions_ns,samples)
    from .rate_numpy import fit_numpy
    return fit_numpy(positions_ns,samples)
