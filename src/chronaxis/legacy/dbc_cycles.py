"""核验明确请求的DBC报文周期，不读文件、不解码报文或生成逐条诊断。

周期取同次已加载DBC的message.cycle_time（毫秒），精确换算一次供运行状态复用。
缺失或非法周期直接拒绝，不用快速发送周期、信号周期或实际差作替代。
"""

from decimal import Decimal
from math import isfinite

from .records import LegacyCANField
from ..timebase.conversion import require_int64_ns


def require_cycle_fields(fields, channel=None):
    """核周期定位声明，不加载DBC。

    参数: fields为无重复LegacyCANField tuple；channel为可选固定通道。
    返回: 原tuple。异常: TypeError/ValueError为类型、数量、重复或通道不符。
    """
    if (type(fields) is not tuple or len(fields)>4096
            or any(type(field) is not LegacyCANField for field in fields)):
        raise TypeError('DBC周期字段需要有限LegacyCANField tuple')
    if len(set(fields)) != len(fields) or channel is not None and any(f.channel != channel for f in fields):
        raise ValueError('DBC周期字段不能重复且必须属于声明通道')
    return fields


def cycle_time_ns(value):
    """将DBC报文毫秒周期转为正整数纳秒，拒绝有损舍入。

    参数: value为message.cycle_time，允许原生int或有限float毫秒。
    返回: 正int64纳秒。异常: TypeError/ValueError/TimeOverflowError为缺失、类型、
        非正、非有限、不能精确到纳秒或越界；不为非法值选择默认周期。
    """
    if value is None:
        raise ValueError('所选DBC报文缺少cycle_time周期，请填写period或valid_for；DBC间隔消费者需改选固定间隔')
    if type(value) not in (int,float):
        raise TypeError('DBC报文周期需要数值毫秒，不能为bool或文本')
    if type(value) is float and not isfinite(value) or value <= 0:
        raise ValueError('DBC报文周期必须为有限正数')
    if type(value) is int:
        return require_int64_ns(value*1_000_000,'dbc.cycle_ns')
    # 用DBC公开十进制值转换，不引入二进制浮点乘法误差或静默截断。
    ns=Decimal(str(value))*1_000_000
    if ns != ns.to_integral_value():
        raise ValueError('DBC报文周期不能精确表示为整数纳秒')
    return require_int64_ns(int(ns),'dbc.cycle_ns')
