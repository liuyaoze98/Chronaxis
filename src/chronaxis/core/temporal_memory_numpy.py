"""通过NumPy保持和表达式计算内存信号的条件时间轴，再检测事件。

输入为当前会话已绑定的布尔计划和规则；输出完整条件轴或稳定Event tuple。
归一化、二分时间索引、条件计算及TRUE起点的阈值安排按列执行。连续、
当前点和更新前点三个视图在相同时间检查有效期，区分真实更新与同刻到期。
输出装箱循环只恢复ConditionTick模型，数值计算不调用标量参考算法。
本模块依赖NumPy和当前核心模型，不读取旧来源或DBC，不修改输入，也没有
全局绑定。完整内存历史和时间轴需占用内存，不保证生产资源预算。
"""

# 实际数组计算，不用object数组或vectorize包装标量算法。
import numpy as np
# 独立整列表达式解释。
from .expression_numpy import evaluate_numpy
# 独立原行归一化，typed列包装不做重复转换。
from .normalize_numpy import memory_series_numpy
# 输出valid/quality与enum域保持明确。
from .numeric_numpy import NumericArray
# 新分析轴协议复用，不调用参考保持算法。
from .state import common_timeline
# NumPy保持通过searchsorted/列掩码实现。
from .state_numpy import align_numpy, build_signal_array
# 实际条件证据与域模型。
from .temporal import ConditionTick, ConditionTimeline
# 仅复用静态BOOL/归属检查，不调用参考计算/检测。
from .temporal_memory_reference import require_memory_rule
# 独立数组run/edge检测器。
from .temporal_numpy import detect_numpy
# 明确三值、质量标志。
from .types import QualityFlag as Q, Truth


def _evidence_numpy(compiled, histories, arrays, times):
    """按列计算连续状态、当前点和更新前点，保留实际未知的因果证据。

    参数:
        compiled (CompiledExpression): 当前已绑定的布尔表达式。
        histories (dict): 当前依赖名称到SignalSeries的映射。
        arrays (dict): 同一依赖名称到SignalArray的映射。
        times (ndarray[int64], shape=(N,)): 当前完整查询轴，单位为纳秒。
    返回:
        tuple[ConditionTick, ...]: 每个查询时刻的完整状态、质量及更新证据。
        状态和原因先按列计算，最后恢复不可变模型。
    异常:
        TypeError、ValueError或OverflowError: 列类型、形状、计划或数值协议错误。
        MemoryError: 数组分配失败；不丢弃数据继续执行。
    """
    # 三视图同时间检查TTL，strict_before不计算time-1。
    views = [
        {name: align_numpy(array, times, point=point, strict_before=before) for name, array in arrays.items()}
        for point, before in ((False, False), (True, False), (True, True))]
    # 表达式每视图独立批量执行，无参考数值调用。
    results = []
    # 循环静态三个视图，不逐样本解释。
    for view in views:
        # 列dtype/enum域来自当前计划及归一化历史。
        context = {name: NumericArray(compiled.bindings.resolve(name).dtype, states.values, states.valid, states.quality,
                                      arrays[name].labels) for name, states in view.items()}
        # 核对实际绑定身份和数组形状后，执行NumPy数值运算及逻辑掩码。
        results.append(evaluate_numpy(compiled, context, compiled.bindings, size=len(times)))
    # 无依赖也明确N，不依赖数组truthiness。
    actual = np.zeros(len(times), dtype=bool)
    # 真实invalid和TTL旧值失效分离。
    invalid = np.zeros(len(times), dtype=bool)
    # 每依赖来源结束仅影响当前规则，空依赖没有来源边界。
    source_end = np.zeros(len(times), dtype=bool)
    # 循环维度是依赖信号，采样列掩码整体执行。
    for name, states in views[1].items():
        # 同时刻原子多列更新汇总，不使用处理顺序。
        actual |= states.actual_update
        # 只有有真实更新位置访问历史valid，避免-1取末项。
        positions = np.flatnonzero(states.actual_update)
        # 真实invalid是完整样本valid，旧TTL不混入此证据。
        invalid[positions] |= ~arrays[name].valid[states.sample_indices[positions]]
        # 当前来源的结束边界在分析坐标。
        source_end |= times == histories[name].observation_end_ns
    # known更新前结果或新增质量位证明actual导致未知。
    causal = invalid | results[2].value.valid | ((results[1].value.quality & ~results[2].value.quality) != 0)
    # 只有真实更新且当前点结果未知时才记录实际中断；被决定性逻辑屏蔽的未知依赖不结束已知活动。
    actual_unknown = actual & ~results[1].value.valid & causal
    # Session终点只有点含真实更新，连续区间仍半开。
    terminal = times == compiled.bindings.session.domain_end_ns
    # 连续known/unknown按结果valid决定，不以诊断强行改truth。
    continuous = np.where(results[0].value.valid, np.where(results[0].value.values, 0, 1), 2)
    # 真实terminal连续UNKNOWN，没有终点之后活动。
    continuous[terminal] = 2
    # 状态质量复制后叠加EOF，无原位修改只读计算结果。
    quality = results[0].value.quality.copy()
    # EOF并列TTL诊断保留。
    quality[terminal] |= np.uint16(Q.MISSING)
    # point保留闭区间真实更新与TTL右端排除。
    point = np.where(results[1].value.valid, np.where(results[1].value.values, 0, 1), 2)
    # 反事实更新前诊断不属于真实发生的质量。
    diagnostic = results[0].dependency_quality | results[1].dependency_quality
    # 仅在最后装箱阶段恢复枚举/原生bool/int，检测计算已整列完成。
    truths = (Truth.TRUE, Truth.FALSE, Truth.UNKNOWN)
    # 输入原时间/来源/质量均保留，不用数组invalid占位当值。
    return tuple(ConditionTick(int(time), truths[int(continuous[index])], Q(int(quality[index])),
                               bool(actual[index]), bool(source_end[index]), bool(terminal[index]),
                               truths[int(point[index])], Q(int(results[1].value.quality[index])),
                               bool(actual_unknown[index]), Q(int(diagnostic[index]))) for index, time in enumerate(times))


def build_timeline_numpy(compiled, rule):
    """独立数组安排TRUE起点deadline并生成完整实际条件证据。

    参数: compiled当前BOOL计划，rule当前规则，时间均int64 ns。
    返回: ConditionTimeline；计时器没有actual更新，不产生假边沿。
    异常: 输入/同步/类型/时间错误传播；超域deadline不会wrap。
    """
    # 仅共享配置协议，不参考被测数值内核。
    require_memory_rule(compiled, rule)
    # 当前真实依赖，不从上次绑定或原DBC重新取数据。
    histories = {name: memory_series_numpy(compiled.bindings, name) for name in compiled.dependencies}
    # 完整当前多源同步门槛，偏移独自不是证据。
    compiled.bindings.require_synchronized(compiled.dependencies)
    # 归一化历史只转换一次，三个视图复用当前typed输入列。
    arrays = {name: build_signal_array(history) for name, history in histories.items()}
    # 纯常量也用明示当前会话范围。
    session = compiled.bindings.session
    # 分析共同轴共享时间协议，不重新排序原行/旧文件。
    base = common_timeline(tuple(histories.values())) if histories else tuple(sorted({session.domain_start_ns, session.domain_end_ns}))
    # 真int64数组，没有大绝对时间先转float。
    times = np.array(base, dtype=np.int64)
    # 真实独立整列三视图条件计算。
    ticks = _evidence_numpy(compiled, histories, arrays, times)
    # edge规则没有持续deadline。
    if rule.rule_type == 'condition_duration':
        # 存储打包truth后独立整列定位新的TRUE区间。
        true = np.array([tick.state is Truth.TRUE and not tick.terminal for tick in ticks], dtype=bool)
        # 只新起点安排计时器，未知缺口不累计旧候选。
        onsets = times[true & ~np.concatenate((np.array([False]), true[:-1]))]
        # 当前域跨度已证明int64可表示，remaining减法安全。
        remaining = np.int64(session.domain_end_ns) - onsets
        # 先筛域内deadline，再加法，不依赖wrap后的比较。
        eligible = onsets[remaining > rule.minimum_duration_ns] if rule.duration_comparison == ">" else onsets[remaining >= rule.minimum_duration_ns]
        # 已证明onset+d≤end，整列精确int64加法。
        deadlines = eligible + np.int64(rule.qualifying_duration_ns) if len(eligible) else eligible
        # 同刻update/TTL/计时器只构造一个完整组。
        extended = np.union1d(times, deadlines)
        # 没有新增时间避免无意义重复计算。
        if len(extended) != len(times):
            # 整列重新保持保证deadline处TTL/观测范围真实有效。
            times = extended
            # 不把旧TRUE复制到失效timer，更不伪造actual。
            ticks = _evidence_numpy(compiled, histories, arrays, times)
    # 每事件保存完整当前来源字段身份。
    refs = tuple(compiled.bindings.source_ref(name) for name in compiled.dependencies)
    # typed完整轴原封不动交给独立数组状态检测。
    return ConditionTimeline(session.domain_start_ns, session.domain_end_ns, ticks, refs)


def detect_memory_numpy(compiled, rule, *, batch_rows=65536):
    """从原内存行通过实际数组保持/表达式/run检测输出事件。

    参数: compiled/rule当前计划，batch_rows正原生int的完整组批大小。
    返回: Event tuple；结果/质量/来源/稳定ID可与独立参考比较。
    异常: 当前模型/时间/配置/批大小错误传播，不静默截断。
    """
    # 将时间轴更新和到期时间交给规则检测器。
    timeline = build_timeline_numpy(compiled, rule)
    # 独立NumPy detector跨批状态，没有reference算法调用。
    return detect_numpy(rule, timeline, batch_rows=batch_rows)
