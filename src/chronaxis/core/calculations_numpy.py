"""用数组计算保持值积分、时间统计、TRUE时长及真实样本统计。

compute_numpy接收CalculationSeries和CalculationDefinition，打包成同长数值与质量列，
裁剪时间端点，计算区间掩码，再归约面积、样本及覆盖时长，输出CalculationResult。
时间轴为形状(N,)的int64纳秒列，积分区间为形状(N-1,)；先用整数端点
求差再换算秒。数值列保留声明类型，积分与样本平均先检查float64精度。
时间极值在正裁剪区间取左端值，time_weighted_mean先规范化有效时长权重，duration
用BOOL TRUE掩码归约时长；select_numpy批量筛选真实更新后逐行恢复typed输出。

条件以known和condition两个bool掩码区分已知真假与UNKNOWN（未知）。
无效数值的零和条件的False仅是存储占位，不能当作正常数据。
样本统计只含半开窗口内的真实数值更新，窗口与有效期边界不造新样本。

依赖NumPy与核心模型；只共享检查、单位和结果分类，不调用参考数值。
所有计算使用新数组，不修改输入，不读写文件；完整内存布局不代表已满足
生产流式内存预算，性能提升也需要另行测量。
"""

# 真正列计算与归约，禁止object/vectorize替代数值内核。
import numpy as np
# 单位和输出政策不包含被测面积/覆盖算法。
from .calculations import make_calculation_result, calculation_conversion
# 仅共享typed输入门槛，无参考计算调用。
from .calculations_reference import require_calculation
# 完整未知诊断区间恢复模型。
from .models import Interval
# 独立数组定宽→float精度判据及物理存储布局。
from .numeric_numpy import DTYPES, NumericArray, to_float_numpy
# 原因明确，不将UNKNOWN存储占位当真值。
from .types import QualityFlag as Q, Truth
# 共享冻结行模型，不调用参考筛选或归约。
from .selection import SelectionRow, require_selection, partial_selection
# 复用本数组后端的独立误差项算法，不调用参考归约或重新计算覆盖事实。
from .integral_sum_numpy import NumpyIntegralSum
from .calculation_output_numpy import convert_result_numpy
from .affine_numpy import affine_numpy
from .moments import MOMENTS, compute_moment_series
from .quantiles import SAMPLE_QUANTILES, compute_quantile_series
from .numeric import ScalarValue


def _sum_finite_numpy(values):
    """保留原顺序归约一列有限浮点项，避免大数消去时丢掉低位。

    参数: values 为当前调用独占的一维 float64 选中列，不含未知占位或非有限项。
    返回: (原量纲总和或None, 计算失败bool, QualityFlag)，不转换物理单位。
    异常: 结构错误、分配和取消直接传播；原序中间溢出由返回诊断说明。
    流程: 原面积、真实样本或已规范化权重项依次推进同一个数组误差核。
        容量取本次项数M：每项最多增加一个partial，因此不会引入固定4096阈值。
        完整内存入口仍为O(M)，不宣称有限批预算；不调用参考核或math.fsum。
    """
    # 调用点均提供私有选择/乘法结果；只冻结本层列，不修改CalculationSeries原值。
    keep = kernel = number = None
    try:
        values.setflags(write=False)
        # 输入已选出有效项，(M,)全TRUE列不把未选Inf或未知占位送入归约。
        keep = np.ones(len(values), dtype=bool)
        keep.setflags(write=False)
        # K个旧partial只可能产生K个lo加一个hi，任意前缀K不超过已消费项数。
        kernel = NumpyIntegralSum(max(1, len(values)))
        kernel.push_values(values, keep)
        # raw_sum只是内部数值标签；factor保持1，外层仍只转换一次实际单位。
        number = kernel.finish('raw_sum')
        return number.value, number.calculation_failed, number.quality
    finally:
        # 异常traceback不额外保留本层选中列；原异常及其诊断不改变。
        values = keep = kernel = number = None


def select_numpy(series, spec):
    """通过NumPy掩码筛选真实更新，再逐行装箱输出。

    参数: series完整CalculationSeries；spec为select请求。
    返回: SelectionRow迭代器，TRUE与UNKNOWN保留，FALSE排除。
    异常: 开始消费时传播输入/配置错误，分配失败不吞。
    流程: 建立(N,)时间、actual、known和TRUE列，批量选取输出索引。
        输出循环只恢复typed行，不承担筛选计算。索引占O(N)内存，输出不攒列表。
    """
    # 输入协议共享，实际选择计算用数组独立完成。
    require_selection(series, spec)
    start = max(spec.window.start_ns, series.observation.start_ns)
    end = min(spec.window.end_ns, series.observation.end_ns)
    # 精确纳秒列与同长布尔掩码，不将UNKNOWN的存储False当成已知FALSE。
    times = np.array(series.times_ns, dtype=np.int64)
    actual = np.array(series.actual_value_updates, dtype=bool)
    known = np.ones(len(times), dtype=bool) if series.conditions is None else np.array([value.valid for value in series.conditions], dtype=bool)
    truth = np.ones(len(times), dtype=bool) if series.conditions is None else np.array([value.value if value.valid else False for value in series.conditions], dtype=bool)
    keep = actual & (times >= start) & (times < end) & (~known | truth)
    # 只对真实选中行组列执行单位换算，循环仍只负责装箱，不逐样本调用参考核。
    indices = np.flatnonzero(keep)
    conversion = calculation_conversion(spec, series.unit)
    converted = None
    if conversion is not None and (conversion.factor != 1 or conversion.offset != 0):
        dtype = series.values[0].dtype
        column = NumericArray(dtype,
            np.array([series.values[i].value if series.values[i].valid else 0 for i in indices], dtype=DTYPES[dtype]),
            np.array([series.values[i].valid for i in indices], dtype=bool),
            np.array([int(series.values[i].quality) for i in indices], dtype=np.uint16))
        converted = affine_numpy(column, conversion.factor, conversion.offset, conversion.dtype(dtype))
    # 索引数组先筛选；循环仅打包输出，不调用参考筛选。
    for position, index in enumerate(indices):
        selection = Truth.TRUE if known[index] else Truth.UNKNOWN
        value = series.values[index]
        if converted is not None:
            value = ScalarValue(converted.values[position].item(), converted.dtype,
                                bool(converted.valid[position]), Q(int(converted.quality[position])))
        condition_quality = Q.NONE if series.conditions is None else series.conditions[index].quality
        quality=series.diagnostics[index] | value.quality | condition_quality
        if series.values[index].partial or series.conditions is not None and series.conditions[index].partial:
            value,quality=partial_selection(value,quality,spec)
        yield SelectionRow(int(times[index]), value, selection, quality,
                           series.binding_identity, series.source_refs, series.unit if conversion is None else conversion.unit)


def compute_numpy(series, spec, *, step_ns=None, budget=None):
    """批量计算保持面积、样本/时间统计、BOOL TRUE时长和覆盖。

    参数:
        series: 完整CalculationSeries；spec为CalculationDefinition，声明半开纳秒窗口与算子。
        spec还提供输出单位及report或strict部分结果政策；duration需BOOL输入。
        step_ns为可选固定/DBC周期，只接收所选驱动真实更新；按交集比例计算
        面积、时长和均值权重，不改变实际坐标或输出第二套时间。
        budget为精确分位数的可选共享RAM账本，省略时采用项目默认配额。
    返回:
        CalculationResult，保存数值、覆盖、未知范围、来源与质量原因；select另用行流入口。
        积分区间使用(N-1,)数组，真实样本选择使用(N,)掩码；正常零与None分开。
    异常:
        类型、模型或单位配置错误直接传播；内存分配异常不转换成质量问题。
        非有限计算、下溢和精度失败写入质量原因。
    流程:
        先打包列并检查精度，再裁剪整数时间区间、按有效值与TRUE掩码计算。
        各覆盖时长独立归约，最后恢复未知区间并应用一次输出单位转换。
        不逐样本调用参考计算，不广播错位输入，也不修改原列。
    """
    # 静态模型门槛与数值实现分开。
    require_calculation(series, spec, step_ns=step_ns)
    if spec.operation in SAMPLE_QUANTILES:
        from .sample_reduction_numpy import NumpySampleReduction
        return compute_quantile_series(series, spec, NumpySampleReduction, budget)
    if spec.operation in MOMENTS:
        from .sample_reduction_numpy import NumpySampleReduction
        from .time_reduction_numpy import NumpyTimeReduction
        from .conditional_time_reduction_numpy import NumpyConditionalTimeReduction
        return compute_moment_series(series, spec, NumpySampleReduction, NumpyTimeReduction,
                                     NumpyConditionalTimeReduction, step_ns)
    # 输出维度及因子由明确单位表验证，不重复DBC缩放。
    conversion = calculation_conversion(spec, series.unit)
    unit, factor = conversion.unit, conversion.factor
    # Python仅求两个配置区间交集，不执行逐样本数值。
    start = max(spec.window.start_ns, series.observation.start_ns)
    # 不在EOF外补未知周期或面积。
    end = min(spec.window.end_ns, series.observation.end_ns)
    # 无实际交集明确None，不用空数组猜选择FALSE。
    actual = Interval(start, end) if start <= end else None
    # typed输入装箱N列，invalid位置存储0但有明确质量。
    column = NumericArray(series.values[0].dtype, np.array([value.value if value.valid else 0 for value in series.values], dtype=DTYPES[series.values[0].dtype]),
                          np.array([value.valid for value in series.values], dtype=bool), np.array([int(value.quality) for value in series.values], dtype=np.uint16))
    # 只有需要浮点面积/mean的算子检查整数精度，min/max保持精确整数。
    values = to_float_numpy(column) if spec.operation in ('integral', 'sample_mean', 'time_weighted_mean') else column
    # copy允许新增计算原因，绝不改只读输入列。
    quality_values = values.quality.copy()
    # 实际边界均为int64，绝对时间不先转float。
    times = np.array(series.times_ns, dtype=np.int64)
    # 全列端点先裁剪，不按完整相邻区间算面积。
    left = np.maximum(times[:-1], np.int64(start))
    # EOF/窗口右端不包含，point不会增加面积。
    right = np.minimum(times[1:], np.int64(end))
    # 只有正相交范围才允许端点减法，避免域外反序差wrap。
    observed = right > left
    # 默认0仅为明确没有面积，不意味着未知值0。
    durations = np.zeros(len(left), dtype=np.int64)
    # 正差≤已校验观测域跨度，安全int64减法。
    np.subtract(right, left, out=durations, where=observed)
    # 无条件为明确选择全部；条件未知单独掩码。
    known = np.ones(len(times), dtype=bool) if series.conditions is None else np.array([value.valid for value in series.conditions], dtype=bool)
    # 无效FALSE存储占位只能与known共同使用。
    condition = np.ones(len(times), dtype=bool) if series.conditions is None else np.array([value.value if value.valid else False for value in series.conditions], dtype=bool)
    # 条件结果原因不是known逻辑全部依赖原因，诊断另列。
    condition_quality = np.zeros(len(times), dtype=np.uint16) if series.conditions is None else np.array([int(value.quality) for value in series.conditions], dtype=np.uint16)
    # 只有效/TRUE/正观测区间可计算面积。
    selected = observed & values.valid[:-1] & known[:-1] & condition[:-1]
    # BOOL FALSE仍计值覆盖，但不增加TRUE持续时间。
    if spec.operation == 'duration':
        selected &= values.values[:-1]
    # 面积数组形状为(N-1,)，单位为输入值单位乘秒；掩码外的占位不用于结果。
    areas = np.zeros(len(durations), dtype=np.float64)
    seconds = None
    if spec.operation == 'integral' or step_ns is not None and spec.operation in ('duration', 'time_weighted_mean'):
        seconds = durations.astype(np.float64)
        if step_ns is None:
            seconds /= 1_000_000_000
        else:
            # 分母是未裁剪的真实记录对跨度；只为当前计算生成权重，不保存另一条轴。
            seconds /= np.diff(times)
            seconds *= step_ns / 1_000_000_000
    # 统计算子不计算无关浮点面积。
    if spec.operation == 'integral':
        # 仅预期浮点范围错误转质量，配置/分配异常照常传播。
        with np.errstate(over='ignore', under='ignore', invalid='ignore'):
            # 实际UFUNC掩码乘法，不逐样本Python回调。
            np.multiply(values.values[:-1], seconds, out=areas, where=selected)
        # 有限性失败与非零面积下溢区别于有效0。
        nonfinite = selected & ~np.isfinite(areas)
        # 最小正输入乘正dt消失为0时明确精度原因。
        underflow = selected & (areas == 0) & (values.values[:-1] != 0)
        # 计算质量追加到当前值可用性；末point不参与面积。
        quality_values[:-1][nonfinite] |= np.uint16(Q.NONFINITE)
        # 下溢不能作为正常0进入归约。
        quality_values[:-1][underflow] |= np.uint16(Q.PRECISION_LOSS)
    # 每个算子的数值可用性按完整已知质量计算。
    valid = quality_values == 0
    # 重新排除面积溢出/精度失败，FALSE不构造未知选中集。
    selected = observed & valid[:-1] & known[:-1] & condition[:-1]
    # 再次建立完整选择掩码，保留FALSE的已知状态。
    if spec.operation == 'duration':
        selected &= values.values[:-1]
    # 各duration求和非负且≤观测域跨度，已证明int64归约不wrap。
    value_duration = int(np.sum(durations[valid[:-1]], dtype=np.int64))
    # TRUE和FALSE都计入条件覆盖；UNKNOWN才不计。
    known_duration = int(np.sum(durations[known[:-1]], dtype=np.int64))
    # 正常数值与TRUE相交的真实时长。
    selected_duration = int(np.sum(durations[selected], dtype=np.int64))
    # 所选值未知独立于条件未知。
    selected_unknown = int(np.sum(durations[observed & known[:-1] & condition[:-1] & ~valid[:-1]], dtype=np.int64))
    # 明确FALSE占满实际域才有空选择证明。
    false_duration = int(np.sum(durations[observed & known[:-1] & ~condition[:-1]], dtype=np.int64))
    # 样本统计只计真实数值更新，窗口/TTL边界不是样本。
    samples = (times >= start) & (times < end) & np.array(series.actual_value_updates, dtype=bool) & valid & known & condition
    # duration的样本诊断计数只取真实TRUE更新，时长仍由(N-1,)区间归约。
    if spec.operation == 'duration':
        samples &= values.values
    # 所有被观测区间左端或真实样本都有可追溯诊断。
    relevant = np.concatenate((observed, np.array([False]))) | ((times >= start) & (times < end) & np.array(series.actual_value_updates, dtype=bool))
    # 诊断列独立于结果valid，known决断也保留原依赖原因。
    diagnostic = np.array([int(q) for q in series.diagnostics], dtype=np.uint16) | quality_values | condition_quality
    # bitwise OR不会像sum质量整数溢出，不忽略失败原因。
    quality = Q(int(np.bitwise_or.reduce(diagnostic[relevant], initial=np.uint16(0))))
    # 未知范围循环只恢复输出interval，不做数值/覆盖计算。
    value_unknown = tuple(Interval(int(left[index]), int(right[index])) for index in np.flatnonzero(observed & ~valid[:-1]))
    # 条件FALSE已有明确判断，不进入条件未知区间。
    condition_unknown = tuple(Interval(int(left[index]), int(right[index])) for index in np.flatnonzero(observed & ~known[:-1]))
    # 无可核实面积或样本的归约保持None，不偷用空sum=0。
    result, failed = None, False
    # 浮点归约范围错误按质量记录，其他异常不吞。
    with np.errstate(over='ignore', under='ignore', invalid='ignore'):
        # 每种口径明确选择，不能叫模糊mean。
        if spec.operation == 'integral' and np.any(selected):
            # 原面积按时间顺序保留低位；覆盖、面积质量和最终单位转换仍走原路径。
            result, failed, reduction_quality = _sum_finite_numpy(areas[selected])
            quality |= reduction_quality
        # 整数min仍精确，不隐式转大整数float。
        elif spec.operation == 'sample_count':
            result = int(np.count_nonzero(samples))
        elif np.any(samples) and spec.operation == 'sample_minimum':
            # 只实际样本，不插入窗口左端保持值。
            result = np.min(values.values[samples]).item()
        # UINT64最大值保持原生Python int输出。
        elif np.any(samples) and spec.operation == 'sample_maximum':
            # 原统计值dtype保留。
            result = np.max(values.values[samples]).item()
        # 样本mean以样本数为分母，与下方时间权重归约分开。
        elif np.any(samples) and spec.operation == 'sample_mean':
            # 先原序求真实样本总和，再除原样本数；不预平均以掩盖中间溢出。
            result, failed, reduction_quality = _sum_finite_numpy(values.values[samples])
            quality |= reduction_quality
            if not failed:
                result = np.divide(np.float64(result), np.count_nonzero(samples)).item()
        # 时间极值包含裁剪边界的保持值；数组原dtype保证整数精度。
        elif np.any(selected) and spec.operation == 'min_time':
            result = np.min(values.values[:-1][selected]).item()
        elif np.any(selected) and spec.operation == 'max_time':
            result = np.max(values.values[:-1][selected]).item()
        # 规范化时长权重再乘值，避免中间值乘纳秒溢出。
        elif np.any(selected) and spec.operation == 'time_weighted_mean':
            selected_values = values.values[:-1][selected]
            if step_ns is None:
                weights = durations[selected].astype(np.float64) / selected_duration
            else:
                weights = seconds[selected]
                denominator, _, _ = _sum_finite_numpy(weights)
                # 原序求和会冻结借入列；归一化生成当前计算结果，不能原地改只读列。
                weights = np.divide(weights, denominator)
            terms = np.multiply(selected_values, weights)
            if np.any(~np.isfinite(terms)):
                failed, quality = True, quality | Q.NONFINITE
            elif np.any((terms == 0) & (selected_values != 0)):
                failed, quality = True, quality | Q.PRECISION_LOSS
            else:
                # 权重与逐项有限/下溢检查不变，仅让有效权重项的消去保留低位。
                result, failed, reduction_quality = _sum_finite_numpy(terms)
                quality |= reduction_quality
        # 有已知布尔区间才产生可核实TRUE时长，全未知保持None。
        elif spec.operation == 'duration' and np.any(observed & valid[:-1] & known[:-1] & condition[:-1]):
            if step_ns is None:
                result = selected_duration / 1_000_000_000
            elif np.any(selected):
                result, failed, reduction_quality = _sum_finite_numpy(seconds[selected])
                quality |= reduction_quality
            else:
                result = 0.0
    # 归约后应用一次完整仿射转换，并检查目标数值精度。
    if result is not None and not failed and spec.operation != 'sample_count':
        result, conversion_quality = convert_result_numpy(result, column.dtype, conversion)
        failed = conversion_quality != Q.NONE
        quality |= conversion_quality
    # 总归约/转换非有限为计算失败，不正常Inf。
    if type(result) is float and not np.isfinite(result):
        # 覆盖事实不会改成0来掩盖算术失败。
        failed, quality = True, quality | Q.NONFINITE
    # 空选择证明必须有明确条件及非零连续观测。
    all_false = series.conditions is not None and actual is not None and end > start and false_duration == end-start
    # 只共享结果分类，全部聚合数值来自本独立数组内核。
    return make_calculation_result(spec, series, result, unit, actual, value_duration, known_duration, selected_duration,
                              selected_unknown, int(np.count_nonzero(samples)), value_unknown, condition_unknown, quality,
                              all_false=all_false, calculation_failed=failed)
