"""确定信号的有效期声明，不读取DBC或日志。

显式valid_for优先；否则使用本信号period的三倍。原始报文未填period时
保留None，执行启动再从本次已有DBC元数据取得周期。已解码数据不能借用
别的信号或计算驱动的周期。所有数值以正int64纳秒表示，无I/O或全局缓存。
"""

from .checks import PlanValidationError, duration_at
from ..timebase.conversion import require_int64_ns


def triple_period(period_ns, path):
    """将周期乘三并检查溢出，避免产生无限或负有效期。

    参数: period_ns为正整数纳秒；path为配置错误位置。
    返回: 正int64纳秒有效期。异常: PlanValidationError为非法周期或乘积超界。
    副作用: 无，不读取文件。
    """
    try:
        # bool不表示一个纳秒；先核周期，再核乘积，保持精确整数运算。
        if type(period_ns) is not int or period_ns <= 0:
            raise ValueError('信号周期必须是正整数纳秒')
        return require_int64_ns(period_ns * 3, 'valid_for_ns')
    except (TypeError, ValueError, OverflowError) as error:
        raise PlanValidationError(path, '周期的3倍不能作为有效期：' + str(error)) from error


def declared_valid_for(raw, path, *, dbc_available):
    """按显式有效期、信号周期、待查DBC的优先顺序解析声明。

    参数: raw为单信号配置；path为其配置位置；dbc_available说明原始来源有DBC。
    返回: 正int纳秒或None（只用于尚待DBC的声明）。
    异常: PlanValidationError为显式空值、周期/有效期错误或没有周期依据。
    副作用: 无；validate/explain不会因此打开DBC。
    """
    # 即使有效期已覆盖默认值，用户填写的周期也必须合法，不能静默忽略错误。
    period = duration_at(raw['period'], path + '.period', positive=True) if 'period' in raw else None
    if 'valid_for' in raw:
        return duration_at(raw['valid_for'], path + '.valid_for', positive=True)
    if period is not None:
        return triple_period(period, path + '.valid_for')
    # 原始报文可在运行启动借用同次DBC；静态阶段不为默认值提前读文件。
    if dbc_available:
        return None
    raise PlanValidationError(path + '.valid_for',
        '未填写valid_for且无法取得信号周期；请填写本信号period或valid_for')
