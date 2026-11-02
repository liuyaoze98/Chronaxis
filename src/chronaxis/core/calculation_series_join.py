"""把两段已经求值的有限列合成数值与三值条件共用的指标输入。

输入是覆盖同一指定窗口的两个CalculationSeries，条件列必须是BOOL且无量纲。
按双方更新/失效边界划分左闭右开区间；仅真实数值依赖更新成为样本。
输出保留原数值类型、FALSE/UNKNOWN、双方依赖诊断和完整来源子类。
末点只提供边界值；本模块不计算面积，不把未知替换为FALSE或0。

先用双游标计数，超过max_intervals时在建立输出列前拒绝；不先拼整轴排序。
这是有限输入的纯时间协议，不是历史读取器或预算owner。调用方必须事先
校验真实表达式绑定/联合同步，并预约最大输出行、来源与诊断容器费用。
数值列的binding_identity原样保留，不能单凭该字符串证明条件同属一个计划。
不读取文件、不修改输入、不保留全局状态，不声称公共AnalysisRunner已支持条件。
"""

# 整数纳秒轴只用有序查找和双游标，保持定宽值与三值对象原样。
from bisect import bisect_right
from .calculations import CalculationSeries
from .models import Interval
from .types import SignalDType as D


def _joint_times(value, condition, window):
    """依次产生窗口首末及两轴内部边界，不保存合并轴。

    参数: value/condition为已校验有限列；window是共同覆盖的Interval。
    返回: 严格递增的整数纳秒生成器，点窗口只产生一点。
    异常: 已校验模型外的存储或分配异常原样传播。
    """
    # 左边界即便不是原更新也须存在；右边界不能形成额外正区间。
    yield window.start_ns
    if window.start_ns == window.end_ns:
        return
    i = bisect_right(value.times_ns, window.start_ns)
    j = bisect_right(condition.times_ns, window.start_ns)
    while True:
        # 两个原轴均覆盖窗口；到终点后统一使用窗口末端作为哨兵。
        a = value.times_ns[i] if i < len(value.times_ns) else window.end_ns
        b = condition.times_ns[j] if j < len(condition.times_ns) else window.end_ns
        time = min(a, b, window.end_ns)
        yield time
        if time == window.end_ns:
            return
        # 同刻双方更新只生成一个原子边界，不能重复结算或重计样本。
        if a == time:
            i += 1
        if b == time:
            j += 1


def join_calculation_series(value, condition, *, window=None, max_intervals=64):
    """合并有限数值和BOOL输入，保留条件单独更新与真正样本的区别。

    参数: value是原值列；condition是BOOL列；window需被双方完整覆盖，
        省略时两列观测域必须相同；max_intervals是允许输出的正区间数。
    返回: 新冻结CalculationSeries，conditions包含TRUE/FALSE/UNKNOWN。
    异常: TypeError为模型或容量类型错误；ValueError为条件、窗口或容量超限。
    边界: 允许点窗口，但不外推EOF；调用方负责真实绑定/同步和先行预算预约。
    """
    # 嵌套选择不是本接口的语义；BOOL不能借整数继承关系成为容量。
    if not isinstance(value, CalculationSeries) or not isinstance(condition, CalculationSeries):
        raise TypeError('联合指标输入需要两个有限CalculationSeries')
    if type(max_intervals) is not int:
        raise TypeError('max_intervals需要原生int')
    if max_intervals < 1:
        raise ValueError('max_intervals必须为正整数')
    if value.conditions is not None or condition.conditions is not None:
        raise ValueError('联合输入不接受已经带选择条件的列')
    if condition.values[0].dtype is not D.BOOL or condition.unit != '1':
        raise ValueError('选择条件需要无量纲BOOL列')
    if window is None:
        if value.observation != condition.observation:
            raise ValueError('不同观测域必须显式给出共同窗口')
        window = value.observation
    if not isinstance(window, Interval):
        raise TypeError('联合窗口需要Interval')
    if any(window.start_ns < series.observation.start_ns or
           window.end_ns > series.observation.end_ns for series in (value, condition)):
        raise ValueError('联合窗口必须由双方实际观测完整覆盖')

    # 第一遍仅计数，不创建整轴或输出列；容量不足时不返回截断结果。
    for index, _ in enumerate(_joint_times(value, condition, window)):
        if index > max_intervals:
            raise ValueError('联合指标输入超过max_intervals，不丢弃边界')
    times, values, conditions, updates, diagnostics = [], [], [], [], []
    i = bisect_right(value.times_ns, window.start_ns) - 1
    j = bisect_right(condition.times_ns, window.start_ns) - 1
    for time in _joint_times(value, condition, window):
        # 在边界先采用该时刻真实更新/TTL的新状态，保持值只看现在和过去。
        while i + 1 < len(value.times_ns) and value.times_ns[i + 1] <= time:
            i += 1
        while j + 1 < len(condition.times_ns) and condition.times_ns[j + 1] <= time:
            j += 1
        times.append(time)
        values.append(value.values[i])
        conditions.append(condition.values[j])
        # 条件边界与裁剪左端不可凭保持值制造真实数值样本。
        updates.append(time == value.times_ns[i] and value.actual_value_updates[i])
        diagnostics.append(value.diagnostics[i] | condition.diagnostics[j])

    # 原来源的具体子类和完整字段保留；不同子类即使文字相同也不合并。
    refs = list(value.source_refs)
    for ref in condition.source_refs:
        if not any(type(old) is type(ref) and old == ref for old in refs):
            refs.append(ref)
    return CalculationSeries(window, tuple(times), tuple(values), tuple(updates), value.unit,
                        tuple(conditions), tuple(diagnostics), value.binding_identity, tuple(refs))
