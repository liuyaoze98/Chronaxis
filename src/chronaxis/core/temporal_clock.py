"""检查本批实际边界对应的计时增量，不构造另一条时间轴。

实际模式不传增量；固定/DBC模式由上游仅在所选驱动更新时传入一个周期，
其余有效期、EOF等边界传0。增量仅供检测器当前候选计时，不进入事件输出。
"""


def require_clock_advances(ticks, advances, record_clock, previous):
    """核对计时模式和有限批增量。

    参数: ticks为已校验完整组、advances为非负整数tuple或None，previous为上次实际时间。
    返回: None。异常: TypeError/ValueError，不推进任何状态；首点不能虚构前序周期。
    """
    if type(record_clock) is not bool:
        raise TypeError('record_clock需要bool')
    if not record_clock:
        if advances is not None:
            raise ValueError('实际计时不能混入固定周期增量')
        return
    if type(advances) is not tuple or len(advances) != len(ticks):
        raise TypeError('记录计时需要与完整组等长的增量tuple')
    if any(type(value) is not int or not 0 <= value < (1 << 63) for value in advances):
        raise ValueError('计时增量需要非负int64整数')
    if previous is None and advances and advances[0] != 0:
        raise ValueError('首条记录不能增加尚不存在的间隔')
