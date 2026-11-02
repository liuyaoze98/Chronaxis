"""独立计算保持值积分、时间统计、TRUE时长和真实样本统计。

compute_reference接收CalculationSeries和CalculationDefinition，先裁剪观测与请求窗口，
再独立计算面积、样本归约、覆盖时长及未知区间，输出CalculationResult。
积分使用零阶保持：左端值乘以相邻区间裁剪后的时长。先对整数纳秒端点
求差，再换算秒，不把较大的绝对时间先转成浮点数。
时间极值包含裁剪边界的保持值，time_weighted_mean按有效选择时长加权；duration
累计有效主BOOL为TRUE的区间。select_reference保留真实TRUE/UNKNOWN更新行。

样本统计只取actual_value_updates为True的真实数值更新，不包含窗口或
有效期到期边界，也不包括半开窗口末点。值有效与条件已知分别统计，
条件FALSE是已知未选中，UNKNOWN（未知）不能视作FALSE或补成零。

本实现只使用标准库与核心模型，数值和覆盖不调用NumPy。可共享输入
检查、单位与结果分类，但归约独立实现。保留完整内存输入，不读写文件，
不修改原数据或持有跨任务状态；本模块不提供流式内存预算保证。
"""

# 独立标量有限性/稳定求和，不调用数组归约。
from math import fsum, isfinite
# 共享模型、单位与条件始终为FALSE时的空选择规则，不共享数值计算。
from .calculations import CalculationSeries, CalculationDefinition, make_calculation_result, calculation_unit
# 诊断区间与请求都保持精确纳秒。
from .models import Interval
# 独立参考定宽到float转换先检查精度。
from .numeric import ScalarValue, to_float_reference
# 未知/计算质量与正常零严格分开。
from .types import QualityFlag as Q, SignalDType as D, Truth
# 选择只共享冻结协议，标量筛选独立于NumPy掩码。
from .selection import SelectionRow, require_selection
from .record_intervals import clipped_record_seconds, require_record_step


def require_calculation(series, spec, *, step_ns=None):
    """验证实际指标输入模型，不执行任何面积或统计。

    参数: series真实CalculationSeries，spec真实CalculationDefinition；step_ns可指定记录对周期，
        仅连续统计算子可用，输入必须是所选驱动真实更新。
    返回: None，模型内部完整轴和dtype已校验。
    异常: TypeError为无类型占位输入；ValueError为select标量执行或dtype不匹配。
    """
    # 后端共享typed协议，不复用被测数值。
    if not isinstance(series, CalculationSeries) or not isinstance(spec, CalculationDefinition):
        # 不猜dict内不完整状态。
        raise TypeError('指标执行需CalculationSeries和CalculationDefinition')
    # 行流具有独立返回类型，不能作为标量统计执行。
    if spec.operation == 'select':
        raise ValueError('select需选择行流入口')
    # 布尔只用于TRUE时长；数值统计不接受布尔或枚举编码。
    allowed = (D.BOOL,) if spec.operation == 'duration' else (D.INT64, D.UINT64, D.FLOAT64)
    if series.values[0].dtype not in allowed:
        raise ValueError('指标算子与输入dtype不匹配')
    if step_ns is not None and spec.operation not in ('integral', 'duration', 'time_weighted_mean', 'min_time', 'max_time'):
        raise ValueError('样本统计不接受记录对周期')
    require_record_step(step_ns, series.actual_value_updates)


def select_reference(series, spec):
    """按真实更新逐行返回TRUE与UNKNOWN选择结果，不累计输出列表。

    参数: series完整内存CalculationSeries；spec为select请求。
    返回: SelectionRow迭代器；UNKNOWN保留诊断，FALSE排除，窗口右端不输出。
    异常: 开始迭代时传播模型/算子/单位错误。
    流程: 遍历完整时间轴，只处理请求与观测交集内的真实目标依赖更新。
        合成边界与条件独自更新不产生行；无效值保持原质量，不填正常零。
    """
    # 生成器检查发生在消费时；只共享输入门槛。
    require_selection(series, spec)
    start = max(spec.window.start_ns, series.observation.start_ns)
    end = min(spec.window.end_ns, series.observation.end_ns)
    # 输入已经完整物化，输出每次只创建当前行。
    for index, time in enumerate(series.times_ns):
        # 不插入保持值行、不读取EOF之后的数据。
        if not start <= time < end or not series.actual_value_updates[index]:
            continue
        # 未提供条件就是明确TRUE，未知条件单独诊断。
        condition = series.conditions[index] if series.conditions is not None else ScalarValue(True, D.BOOL)
        selection = Truth.UNKNOWN if not condition.valid else Truth.TRUE if condition.value else Truth.FALSE
        if selection is Truth.FALSE:
            continue
        # 原值保持dtype/质量/标签与绑定，UNKNOWN不是自动选择成功。
        value = series.values[index]
        yield SelectionRow(time, value, selection, series.diagnostics[index] | value.quality | condition.quality,
                           series.binding_identity, series.source_refs, series.unit)


def compute_reference(series, spec, *, step_ns=None):
    """独立计算请求窗口内的积分、样本/时间统计或BOOL TRUE时长。

    参数:
        series: 完整CalculationSeries；数值统计需同一数值dtype，duration需BOOL。
        spec: CalculationDefinition，给出左闭右开纳秒窗口、算子、输出单位和部分结果政策。
        step_ns: 可选固定/DBC周期，仅用于所选驱动的真实记录对；按交集比例
            计算面积、时长和均值权重，不改变实际坐标或输出第二套时间。
    返回:
        CalculationResult。未换单位的整数极值可保持精确整数；积分和样本平均
        返回浮点值；时间平均先规范化时长权重，duration输出秒。无法核实时
        为None，并保留覆盖、来源与质量原因；select使用独立行流入口。
    异常:
        输入模型或单位配置错误直接传播TypeError或ValueError。
        非有限结果、下溢或转换丢精度作为质量原因返回，不吞配置错误。
    流程:
        裁剪窗口后逐区间计算保持面积与三值选择交集，再按真实更新归约样本，
        最后应用一次输出单位转换并分类结果。正常零与未知占位分别处理。
        临时值和诊断列表只用于本次计算，不修改调用者的CalculationSeries。
    """
    # 配置错误不能吞成未知数据。
    require_calculation(series, spec, step_ns=step_ns)
    # 仅显式已知维度转换，保留有符号面积。
    unit, factor = calculation_unit(spec, series.unit)
    # 先求真实观测与请求交集，不外推末点/EOF。
    start = max(spec.window.start_ns, series.observation.start_ns)
    # 半开窗口右端实际观测不足必须裁剪。
    end = min(spec.window.end_ns, series.observation.end_ns)
    # 完全无交集与零域分别由政策解释。
    actual = Interval(start, end) if start <= end else None
    # 整数输入进入float面积/mean前先严格验证，不影响精确min/max。
    values = [to_float_reference(value) if spec.operation in ('integral', 'sample_mean', 'time_weighted_mean') else value for value in series.values]
    # 全部覆盖时长使用Python精确整数，不按样本数量估算。
    value_duration, known_duration, selected_duration, selected_unknown = 0, 0, 0, 0
    # 明确FALSE时长用来证明充分观测空选择，不靠sum空数组。
    false_duration = 0
    # 真实未知区间按原因类型分别记录，不改变原输入。
    value_unknown, condition_unknown, areas = [], [], []
    # 时间统计保留每个正裁剪区间的左端保持值和整数纳秒时长。
    timed_values = []
    # duration必须至少有可核实的主布尔值与TRUE选择区间，不能靠外部UNKNOWN补零。
    duration_evidence = 0
    # 原诊断与计算原因完整OR，不将KNOWN逻辑结果改成UNKNOWN。
    quality = Q.NONE
    # 独立参考逐区间求裁剪/面积/三值交集。
    for index in range(len(series.times_ns)-1):
        # 先裁剪精确整数端点，不先转float绝对坐标。
        left, right = max(series.times_ns[index], start), min(series.times_ns[index+1], end)
        # 窗口外或零区间不产生面积/未知时长。
        if left >= right:
            # 边界point不是额外周期。
            continue
        # 先整数差再换算秒，保留大绝对时间的小间隔。
        duration = right - left
        # 当前ZOH值与当前选择独立有效性。
        value = values[index]
        # 无条件表示明确选择全部，而不是未知选择。
        condition = series.conditions[index] if series.conditions is not None else ScalarValue(True, D.BOOL)
        # 原依赖、数值与条件质量均可追溯。
        quality |= series.diagnostics[index] | value.quality | condition.quality
        # 正常积分面积先计算，非有限/下溢不变成正常0。
        area = None
        # 只计算真实选择的有效值，FALSE不制造所选值缺失。
        if spec.operation == 'integral' and value.valid and condition.valid and condition.value:
            # 相对dt转秒，默认ZOH保持当前左端值。
            seconds = (duration / 1_000_000_000 if step_ns is None else
                       clipped_record_seconds(series.times_ns[index], series.times_ns[index + 1],
                                              spec.window, step_ns=step_ns))
            area = value.value * seconds
            # 有限输入乘积溢出和非零乘积下溢显式失效。
            failure = Q.NONFINITE if not isfinite(area) else Q.PRECISION_LOSS if area == 0 and value.value != 0 else Q.NONE
            # 不参与不可信面积的正常归约。
            if failure != Q.NONE:
                # 元数据值仍保留，只有计算输出置未知。
                value = ScalarValue(value.value, D.FLOAT64, False, failure)
                # 相同真实样本的积分可用性也更新。
                values[index] = value
                # 新原因不覆盖原诊断。
                quality |= failure
        # 值有效时长与条件真假独立统计。
        if value.valid:
            # 有效零值计入覆盖，区别于UNKNOWN。
            value_duration += duration
        else:
            # 不跨窗口外范围保存未知。
            value_unknown.append(Interval(left, right))
        # 条件UNKNOWN独立保存；FALSE属于已知条件覆盖。
        if condition.valid:
            # 真假都可判断，不把FALSE当缺失。
            known_duration += duration
            # 只有明确FALSE累计空选择证据。
            if not condition.value:
                # 不凭无选中结果推测FALSE。
                false_duration += duration
            # 真与有效值交集才算选中时长。
            elif value.valid:
                # FALSE主值仍证明已知零时长；外部条件未知不提供该证据。
                duration_evidence += duration
                # 所选面积和时长分别保留。
                selected_duration += duration if spec.operation != 'duration' or value.value else 0
                # 其他样本算子没有连续面积。
                if spec.operation == 'integral':
                    # 正常零面积合法进入归约。
                    areas.append(area)
                # min/max_time包含裁剪左边界保持值，time_weighted_mean使用同一有效选择集合。
                if spec.operation in ('min_time', 'max_time', 'time_weighted_mean'):
                    weight = (clipped_record_seconds(series.times_ns[index], series.times_ns[index + 1],
                                                     spec.window, step_ns=step_ns)
                              if spec.operation == 'time_weighted_mean' and step_ns is not None else duration)
                    timed_values.append((value.value, weight))
                elif spec.operation == 'duration' and value.value and step_ns is not None:
                    areas.append(clipped_record_seconds(series.times_ns[index], series.times_ns[index + 1],
                                                        spec.window, step_ns=step_ns))
            else:
                # 所选值未知时strict/report有必要覆盖不足。
                selected_unknown += duration
        else:
            # 条件未知不能当FALSE产生空选择零。
            condition_unknown.append(Interval(left, right))
    # 样本口径只计真实原依赖更新，不计TTL/裁剪合成边界。
    selected_samples = []
    # 参考逐原完整时间组统计当前值/条件，不跨域复制末点。
    for index, time in enumerate(series.times_ns):
        # 半开实际窗口内真实更新，末点排除。
        if not start <= time < end or not series.actual_value_updates[index]:
            # 不把窗口左端保持值伪装成真实样本。
            continue
        # 未知样本保留在诊断，只有有效/TRUE进入样本统计。
        value = values[index]
        # 无选择条件全部真实有效样本可用。
        condition = series.conditions[index] if series.conditions is not None else ScalarValue(True, D.BOOL)
        # 完整实际样本的质量也纳入诊断。
        quality |= series.diagnostics[index] | value.quality | condition.quality
        # 不将无效原数据存储占位0当正常样本。
        if value.valid and condition.valid and condition.value and (spec.operation != 'duration' or value.value):
            # 仅恢复当前原生逻辑数值，未改原输入。
            selected_samples.append(value.value)
    # 空归约保持None；仅明确all_false时按空选择规则处理。
    result, failed = None, False
    # 已选可核实面积或样本才计算正常值。
    try:
        # 面积与样本统计使用不同明确口径。
        if spec.operation == 'integral' and areas:
            # fsum减少标量累计舍入，但不替代NumPy归约。
            result = fsum(areas)
        # 精确整数极值无需浮点转换。
        elif selected_samples and spec.operation == 'sample_minimum':
            # 窗口裁剪不增加边界合成样本。
            result = min(selected_samples)
        # 同样保留uint64大整数精度。
        elif selected_samples and spec.operation == 'sample_maximum':
            # min/max不按时间加权。
            result = max(selected_samples)
        # mean明确样本算术平均，不叫模糊mean。
        elif selected_samples and spec.operation == 'sample_mean':
            # 有效样本数量作分母，不能用时长替代。
            result = fsum(selected_samples) / len(selected_samples)
        # 时间极值只计正时长保持区间，保留大整数的原生精度。
        elif timed_values and spec.operation == 'min_time':
            result = min(value for value, _ in timed_values)
        elif timed_values and spec.operation == 'max_time':
            result = max(value for value, _ in timed_values)
        # 先规范化权重，避免平均值有限但值乘纳秒的中间面积溢出。
        elif timed_values and spec.operation == 'time_weighted_mean':
            denominator = selected_duration if step_ns is None else fsum(weight for _, weight in timed_values)
            terms = [value * (duration / denominator) for value, duration in timed_values]
            if any(not isfinite(term) for term in terms):
                failed, quality = True, quality | Q.NONFINITE
            elif any(term == 0 and value != 0 for term, (value, _) in zip(terms, timed_values)):
                failed, quality = True, quality | Q.PRECISION_LOSS
            else:
                result = fsum(terms)
        # 已知FALSE可核实为零；全未知没有候选值，不能返回正常零。
        elif spec.operation == 'duration' and duration_evidence > 0:
            result = selected_duration / 1_000_000_000 if step_ns is None else fsum(areas)
    # 只把明确浮点累计溢出转计算质量，不吞接口错误。
    except OverflowError:
        # 无法核实总值不报正常Inf。
        failed, quality = True, quality | Q.NONFINITE
    # 输出转换仅一次；未转换整数极值保持整数。
    if result is not None and not failed:
        # 非单位1倍率转换整数前仍检查精度。
        if factor != 1 and type(result) is int:
            # 静态单位不会授权无声丢大整数精度。
            converted = to_float_reference(ScalarValue(result, series.values[0].dtype))
            # 失败输出null且原覆盖/来源诊断保留。
            if not converted.valid:
                # 明确PRECISION_LOSS，不截断原整数。
                failed, quality = True, quality | converted.quality
            else:
                # 仅已证明正常整数才浮点换单位。
                result = converted.value
        # 不把失败结果继续乘因子。
        if not failed:
            # factor1保留整数，避免无必要cast。
            original = result
            # 数学单位转换，不改变符号方向。
            result = result * factor if factor != 1 else result
            # 非有限和非零下溢都不能报正常0。
            if type(result) is float and (not isfinite(result) or result == 0 and original != 0):
                # 明确归约/转换失败；不修改coverage来伪造通过。
                failed, quality = True, quality | (Q.NONFINITE if not isfinite(result) else Q.PRECISION_LOSS)
    # 完整全FALSE证明需要非零实际域，最后政策还检查请求充分覆盖。
    all_false = series.conditions is not None and actual is not None and end > start and false_duration == end-start
    # 共同政策仅包装各独立内核已计算的事实。
    return make_calculation_result(spec, series, result, unit, actual, value_duration, known_duration, selected_duration,
                              selected_unknown, len(selected_samples), value_unknown, condition_unknown, quality,
                              all_false=all_false, calculation_failed=failed)
