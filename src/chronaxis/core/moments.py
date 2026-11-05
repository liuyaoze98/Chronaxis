"""声明 v4 样本与时间二阶统计的操作、自由度和输出量纲。

这里只校验静态契约。归约器使用实际有效更新或选中区间的权重，
其标量算法与数组算法各自实现，不在本模块累计任何历史。
"""

SAMPLE_MOMENTS = ('sample_variance', 'sample_stddev', 'sample_rms')
TIME_MOMENTS = ('time_variance', 'time_stddev', 'time_rms')
MOMENTS = SAMPLE_MOMENTS + TIME_MOMENTS
WITH_DDOF = ('sample_variance', 'sample_stddev', 'time_variance', 'time_stddev')


def moment_ddof(operation, value):
    """检查显式自由度。参数: 操作及原生整数或None。返回: 适用的整数或None。异常: 不适用或越界。"""
    if operation not in WITH_DDOF:
        if value is not None:
            raise ValueError('ddof仅用于方差或标准差')
        return None
    if value is None:
        return 0
    if type(value) is not int or value not in ((0, 1) if operation in SAMPLE_MOMENTS else (0,)):
        raise ValueError('样本方差/标准差ddof为整数0或1，时间统计仅接受整数0')
    return value


def moment_source_unit(operation, unit):
    """推导归约数值的自然单位。参数: 操作及已登记输入Unit。返回: Unit。异常: 未知单位或偏移RMS。"""
    from .unit_registry import resolve_unit, square
    if unit is None:
        raise ValueError('二阶统计需要已登记单位，无法推导未知量纲')
    if operation.endswith('_rms'):
        if unit.offset:
            raise ValueError('摄氏绝对温度RMS须先显式to_unit(...,"K")')
        return unit
    if unit.temperature_role == 'absolute':
        # 绝对温度的离均差是温差，不在差的平方或标准差上加回摄氏偏移。
        unit = resolve_unit('delta_degC' if unit.offset else 'delta_K')
    return square(unit) if operation.endswith('_variance') else unit


def compute_moment_series(series, spec, sample_kernel, time_kernel, conditioned_kernel, step_ns):
    """让内存入口沿同后端的分块归约协议执行一次，返回完整数值和覆盖。

    参数: 已验证序列、请求、对应后端的三种归约类和记录周期。
    返回: CalculationResult。异常: 与分块公开执行相同的类型、单位和时间错误。
    """
    from .calculations import make_calculation_result
    args = spec, series.unit, series.values[0].dtype
    sample = spec.operation in SAMPLE_MOMENTS
    if sample:
        reducer = sample_kernel(*args)
    else:
        factory = conditioned_kernel if series.conditions is not None else time_kernel
        reducer = factory(*args, step_ns=step_ns)
    facts = reducer.push(series)
    number = reducer.finish()
    actual = facts.actual_window
    span = 0 if actual is None else actual.end_ns - actual.start_ns
    if sample or series.conditions is not None:
        known = facts.condition_known_duration_ns
        unknown = facts.selected_value_unknown_duration_ns
        missing_conditions = facts.condition_unknown_ranges
        all_false = actual == spec.window and span > 0 and facts.false_duration_ns == span
    else:
        known, unknown, missing_conditions, all_false = span, span - facts.value_valid_duration_ns, (), False
    return make_calculation_result(spec, series, number.value, number.unit, actual, facts.value_valid_duration_ns,
        known, facts.selected_duration_ns, unknown, facts.valid_sample_count, facts.value_unknown_ranges,
        missing_conditions, facts.quality | number.quality, all_false=all_false, calculation_failed=number.calculation_failed)
