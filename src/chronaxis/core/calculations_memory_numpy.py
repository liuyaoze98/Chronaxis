"""把已有内存行的表达式与三值条件接入NumPy指标计算。

输入为当前表达式、CalculationDefinition和可选BOOL条件，输出CalculationSeries
或CalculationResult。先按依赖列独立归一化，用searchsorted定位最近观测并按
有效期保持，再批量求值、计算零阶保持面积或真实样本统计。
时间统计和BOOL duration接同一独立数组链；select保留枚举标签及UNKNOWN诊断，
返回SelectionRow迭代器，完整输入和中间列仍占用内存。

共同时间轴为int64纳秒列，形状(N,)；数值、条件、质量与真实更新标志
均与之等长。窗口和有效期边界不能伪造样本，条件单独更新也不计数值样本。
打包ScalarValue只是恢复结果模型，实际数值由数组计算承担，不调用参考内核。

依赖NumPy及数组转换、对齐、表达式和指标模块；只共享静态计划检查。
不修改原输入，也不调用旧读取、解码或写出链。此入口保存完整内存历史
及中间列，不承诺生产内存或磁盘预算，性能效果需要另行测量。
"""

# 数组shape/UFUNC由实际NumPy执行。
import numpy as np
# 整列表达式独立解释，不逐样本参考调用。
from .enum_codes import memory_histories, aligned_column
from .expression_numpy import evaluate_numpy
# 当前协议与独立真正数组指标内核。
from .calculations import CalculationSeries
# 数值覆盖/面积/样本归约不共享参考实现。
from .calculations_numpy import compute_numpy, select_numpy
# 只共享静态计划/绑定/依赖校验。
from .calculations_memory_reference import require_calculation_plan
# 当前实际域严格半开。
from .models import Interval
# 独立数组原行规范化。
from .normalize_numpy import memory_series_numpy
# ScalarValue用于结果协议装箱，不执行参考运算。
from .numeric import ScalarValue
# 物理数值列保留有效性/质量/enum域。
from .numeric_numpy import NumericArray
# 时间轴协议可共享，数组保持独立执行。
from .state import common_timeline
# 明确searchsorted/质量掩码内核，不借参考保持。
from .state_numpy import align_numpy, build_signal_array
# 原因包装与数据类型明确。
from .types import QualityFlag as Q
from .where_updates import contains_where, numpy_updates


def build_calculation_series_numpy(compiled, spec, *, condition=None):
    """把原行对齐到共同时间轴，批量求值并标记真实数值更新。

    参数:
        compiled: 当前已校验表达式，类型与spec算子匹配；spec为明确窗口与指标请求。
        condition: 可选同绑定身份的BOOL表达式，省略表示不按条件筛选。
    返回:
        CalculationSeries。所有列使用形状(N,)的共同纳秒轴，真实更新标志只来自
        数值依赖。恢复ScalarValue的逐位置循环只打包类型和质量，不执行数值运算。
    异常:
        绑定、时间、类型、形状或同步检查失败时传播底层异常。
    流程:
        独立归一化各依赖列，加入域内窗口边界，对齐后整列计算数值与条件。
        输出模型复制并冻结本次结果，保留完整历史，不广播或额外读取旧链。
    """
    # 静态当前输入门槛，无参考数值调用。
    names = require_calculation_plan(compiled, spec, condition)
    # 实际独立原行转换，只读现有内存输出。
    histories = memory_histories(compiled, names, memory_series_numpy, condition)
    # 每列typed存储一次，不合并不同dtype为object宽表。
    arrays = {name: build_signal_array(history) for name, history in histories.items()}
    # 当前会话实际范围与请求区分，EOF外没有假数据。
    session = compiled.bindings.session
    # 域内窗口端点纳入积分轴，但不能当真实样本。
    boundaries = tuple(time for time in (spec.window.start_ns, spec.window.end_ns) if session.domain_start_ns <= time <= session.domain_end_ns)
    # 共同轴仅在分析层建立，不重新安排原文件/旧读取。
    times = common_timeline(tuple(histories.values()), boundaries) if histories else tuple(sorted({session.domain_start_ns, session.domain_end_ns, *boundaries}))
    # 绝对时间精确int64，不先float舍入。
    axis = np.array(times, dtype=np.int64)
    # 当前全列保持/searchsorted/TTL独立于标量参考。
    aligned = {name: align_numpy(array, axis) for name, array in arrays.items()}
    # 依赖列dtype/质量/enum标签必须同当前绑定。
    context = {name: aligned_column(states) for name, states in aligned.items()}
    # 数值表达式的精确依赖鍵，全部shape相同。
    numeric = evaluate_numpy(compiled, {name: context[name] for name in compiled.dependencies}, compiled.bindings, size=len(times))
    # 只有明确布尔条件才执行选择，空条件不同于UNKNOWN。
    selected = evaluate_numpy(condition, {name: context[name] for name in condition.dependencies}, compiled.bindings, size=len(times)) if condition is not None else None
    # 样本标志只来自当前数值依赖更新，不包括条件独自更新。
    if contains_where(compiled.root):
        # 同刻更新前后的选择决定样本；未选支路刷新不能额外加权。
        previous = {name: align_numpy(arrays[name], axis, point=True, strict_before=True, left_limit=True) for name in compiled.dependencies}
        before = {name: aligned_column(state)
                  for name, state in previous.items()}
        actual = numpy_updates(compiled.root, context, before, {n: aligned[n].actual_update for n in previous}, len(times))
    else:
        actual = np.zeros(len(times), dtype=bool)
        for name in compiled.dependencies:
            actual |= aligned[name].actual_update
    # typed装箱仅恢复输出模型，invalid占位不成为正常0。
    # ENUM物理列保存整数码；公开行恢复标签字符串，invalid仍为None并保留标签域。
    values = tuple(ScalarValue((numeric.value.labels[int(numeric.value.values[index])] if numeric.value.labels else numeric.value.values[index].item())
                              if numeric.value.valid[index] else None, numeric.value.dtype, bool(numeric.value.valid[index]),
                              Q(int(numeric.value.quality[index])), numeric.value.labels) for index in range(len(times)))
    # 三值条件结果与数值独立，未知保留quality/None。
    conditions = None if selected is None else tuple(ScalarValue(selected.value.values[index].item() if selected.value.valid[index] else None,
                                                                selected.value.dtype, bool(selected.value.valid[index]), Q(int(selected.value.quality[index]))) for index in range(len(times)))
    # 条件已能判定时也保留原依赖诊断，使被逻辑结果遮蔽的异常仍可追溯。
    diagnostic = numeric.dependency_quality if selected is None else numeric.dependency_quality | selected.dependency_quality
    # 当前数值/选择完整执行身份，不缓存上次任务值。
    identity = compiled.identity + ('' if condition is None else ':' + condition.identity)
    # 所有原字段可追溯，名称声明不冒充绑定。
    refs = tuple(compiled.bindings.source_ref(name) for name in names)
    # 冻结协议会校验同长/完整域/类型，不截断。
    return CalculationSeries(Interval(session.domain_start_ns, session.domain_end_ns), times, values, tuple(bool(flag) for flag in actual),
                        compiled.root.unit, conditions, tuple(Q(int(q)) for q in diagnostic), identity, refs)


def select_memory_numpy(compiled, spec, *, condition=None):
    """用独立数组原行、保持和表达式链返回选择行迭代器。

    参数: compiled当前表达式；spec为select；condition可选同绑定BOOL表达式。
    返回: SelectionRow迭代器；值、标签与未知诊断完整保留。
    异常: 输入、绑定或表达式错误传播；筛选配置错误在消费时传播。
    边界: 完整输入/中间数组占用内存，输出不攒列表，不改旧I/O或原输入。
    """
    # 全链使用数组归一化、保持与表达式；未调用参考数值。
    series = build_calculation_series_numpy(compiled, spec, condition=condition)
    return select_numpy(series, spec)


def compute_memory_numpy(compiled, spec, *, condition=None, budget=None):
    """从已有内存行执行数组表达式及指标计算，返回可追溯结果。

    参数:
        compiled: 当前表达式；spec为数值统计或BOOL duration的CalculationDefinition。
        condition: 可选同绑定身份的BOOL表达式。
        budget为精确分位数的可选共享RAM账本，省略时采用项目默认配额。
    返回:
        CalculationResult，保存面积、时间/样本统计或TRUE时长，以及覆盖、未知范围与来源。
    异常:
        配置、输入或数值模型不满足要求时传播底层异常，不静默删数据或补零。
    流程:
        先用数组转换、对齐和表达式生成CalculationSeries，再调用独立数组指标内核。
        只创建本次结果，不修改原行，也不调用参考数值计算。
    """
    # 原行到typed指标列由独立数组链执行。
    series = build_calculation_series_numpy(compiled, spec, condition=condition)
    # 实际掩码/UFUNC/归约内核，不调用参考compute。
    return compute_numpy(series, spec, budget=budget)
