"""从已绑定的内存信号计算条件时间轴，再用参考检测器找出活动和点事件。

输入为编译后的布尔表达式和当前会话规则；输出ConditionTimeline或Event tuple。
先归一化原行，再用独立标量保持和表达式计算连续状态、当前点及更新前点。
这三个视图在同一时间检查有效期，用来区分真实更新导致未知与旧值到期。
最后插入域内持续阈值到期时刻，重新求值后交给检测器，避免确认时间落到
下一报文。本模块不读取报文或DBC，不修改输入，不持有全局状态；完整内存
原型会保存历史和时间轴，不能据此认定生产资源预算已经满足。
"""

# 静态配置协议及不可变时间证据可共享。
from .expression import CompiledExpression
# memory快捷路径只接受包含真实原行的绑定，解码历史使用独立执行驱动。
from .binding import SignalBindings
# 参考只调用独立标量数值/保持/解释，不导入数组后端。
from .expression_reference import evaluate_reference
# 原行归一化和typed标量保留原质量。
from .numeric import ScalarValue, memory_series_reference
# 共同轴是时间协议；状态查询由标量内核完成。
from .state import align_reference, common_timeline
# 真实事件检测与冻结模型。
from .temporal import ConditionTick, ConditionTimeline, TemporalRule
# 当前生命周期没有批次EOF假收尾。
from .temporal_reference import detect_reference
# 类型与三值严格分开。
from .types import SignalDType as D, QualityFlag as Q, Truth


def require_memory_rule(compiled, rule):
    """验证当前布尔计划与规则会话归属，不计算条件。

    参数: compiled真实CompiledExpression，rule真实TemporalRule。
    返回: None，纯常量也使用计划明示的会话域。
    异常: TypeError/ValueError为类型、非BOOL根或会话冲突。
    """
    # 无类型计划/规则不进入执行链。
    if not isinstance(compiled, CompiledExpression) or not isinstance(rule, TemporalRule):
        # 不能根据类名猜测协议。
        raise TypeError('memory时序需CompiledExpression及TemporalRule')
    if not isinstance(compiled.bindings, SignalBindings):
        raise TypeError('memory时序需要真实内存SignalBindings，不能使用解码历史绑定')
    # 时序条件必须为三值布尔，数值没有隐式truthiness。
    if compiled.root.dtype is not D.BOOL or rule.session_id != compiled.bindings.session.session_id:
        # 不跨session借用绑定或把数值当条件。
        raise ValueError('时序条件需BOOL且规则与绑定session一致')


def _evidence(compiled, histories, times):
    """独立参考计算连续、真实点和更新前点的完整证据。

    参数: compiled当前计划；histories当前归一化SignalSeries字典；times ns tuple。
    返回: ConditionTick tuple，实际因果、EOF及诊断保留。
    异常: 模型/保持/表达式校验错误传播，不吞UNKNOWN原因。
    """
    # 三个视图都在当前时刻检查有效期；strict_before直接排除同刻样本，避免计算t-1溢出。
    views = [
        {name: align_reference(history, times, point=point, strict_before=before) for name, history in histories.items()}
        for point, before in ((False, False), (True, False), (True, True))]
    # 每次调用新context/结果，不继承上个任务状态。
    ticks = []
    # 标量参考逐时间解释，每组原子结果已齐。
    for index, time in enumerate(times):
        # 三个结果只共享typed协议，不共享数组计算。
        results = []
        # 三视图分别运行当前表达式，保持因果检查明确。
        for view in views:
            # 当前绑定dtype与enum标签完整保留。
            context = {name: ScalarValue(states[index].value, compiled.bindings.resolve(name).dtype,
                                         states[index].valid, states[index].quality,
                                         tuple(dict.fromkeys(label for _, label in compiled.bindings.resolve(name).choices))
                                         if compiled.bindings.resolve(name).dtype is D.ENUM else ()) for name, states in view.items()}
            # 真实参考解释当前点，不调用NumPy内核。
            results.append(evaluate_reference(compiled, context, compiled.bindings))
        # 未知不能变False，normal结果无结果质量但保留独立诊断。
        states = [Truth.UNKNOWN if not result.value.valid else Truth.TRUE if result.value.value else Truth.FALSE for result in results]
        # 当前完整点是否包含任一真实依赖更新。
        actual = any(values[index].actual_update for values in views[1].values())
        # 真实无效更新可以证明实际中断；只有旧值到期不能证明发生了无效更新。
        invalid = any(values[index].actual_update and not values[index].sample.valid for values in views[1].values())
        # 新更新导致未知；任意有效旁列更新不能把并列TTL误判actual中断。
        actual_unknown = actual and states[1] is Truth.UNKNOWN and (invalid or states[2] is not Truth.UNKNOWN or bool(results[1].value.quality & ~results[2].value.quality))
        # 依赖来源提前结束不会延长其连续范围。
        source_end = any(history.observation_end_ns == time for history in histories.values())
        # Session终点连续视图强制结束，点视图仍保留真实更新。
        terminal = time == compiled.bindings.session.domain_end_ns
        # 原常量/决定性逻辑也不能在真实终点增加持续面积。
        state, quality = (Truth.UNKNOWN, Q.MISSING | results[0].value.quality) if terminal else (states[0], results[0].value.quality)
        # 反事实更新前质量不作为发生过的输入诊断。
        diagnostic = results[0].dependency_quality | results[1].dependency_quality
        # typed证据携带实际点与连续状态的独立原因。
        ticks.append(ConditionTick(time, state, quality, actual, source_end, terminal, states[1], results[1].value.quality, actual_unknown, diagnostic))
    # 冻结当前实际完整组，不隐藏中间FALSE/UNKNOWN。
    return tuple(ticks)


def build_timeline_reference(compiled, rule):
    """汇集信号更新、有效期和观测边界，并插入域内持续阈值时刻。

    参数:
        compiled (CompiledExpression): 当前会话的已绑定布尔表达式。
        rule (TemporalRule): 同一会话的检测规则；所有时间使用整数纳秒。
    返回:
        ConditionTimeline: 完整条件证据，包括没有新样本的精确阈值时刻。
    异常:
        TypeError、ValueError或OverflowError: 计划、同步、输入或时间协议检查失败。
    副作用:
        分配本次依赖历史和完整时间轴，不重排原行，不读取或解码旧来源。
    """
    # 当前会话/BOOL根先验证再计算。
    require_memory_rule(compiled, rule)
    # 仅取当前依赖的既有原行，不额外读取/解码。
    histories = {name: memory_series_reference(compiled.bindings, name) for name in compiled.dependencies}
    # 显式跨来源同步证据仍为执行前门槛。
    compiled.bindings.require_synchronized(compiled.dependencies)
    # 纯常量也用明示会话端点，非空依赖的轴含TTL/来源边界。
    session = compiled.bindings.session
    # 轴协议复用，数值保持/表达式及事件算法独立。
    times = common_timeline(tuple(histories.values())) if histories else tuple(sorted({session.domain_start_ns, session.domain_end_ns}))
    # 初步条件仅用来安排计时器，不产生最终事件。
    ticks = _evidence(compiled, histories, times)
    # 使用精确Python整数判断deadline是否在域内，禁止wrap。
    deadlines = set()
    # 参考逐组识别新的TRUE起点，取消候选后的旧timer可安全空推进。
    if rule.rule_type == 'condition_duration':
        # 第一组之前没有已知连续TRUE。
        previous = Truth.UNKNOWN
        # 没有实际报文也必须安排精确计时器。
        for tick in ticks:
            # 真终点不得建立新候选或deadline。
            if tick.state is Truth.TRUE and previous is not Truth.TRUE and not tick.terminal:
                # 先在宽整数域计算，不先cast int64。
                deadline = tick.time_ns + rule.qualifying_duration_ns
                # 超会话的候选不追加域外时间。
                if deadline <= session.domain_end_ns:
                    # 同时间update/TTL/deadline合并为唯一完整组。
                    deadlines.add(deadline)
            # 连续truth用于下个真实起点判定，不看样本数量。
            previous = tick.state
    # 新timer通过当前保持重新求值，不复制过期条件或伪造actual。
    if deadlines.difference(times):
        # 所有坐标排序仅限新分析轴，不改变原数据/旧文件顺序。
        times = tuple(sorted(set(times) | deadlines))
        # 精确deadline处无更新也检查TTL/source范围。
        ticks = _evidence(compiled, histories, times)
    # 来源定位来自当前绑定；同名不同会话不继承。
    refs = tuple(compiled.bindings.source_ref(name) for name in compiled.dependencies)
    # 完整轴每个boundary只提交一次。
    return ConditionTimeline(session.domain_start_ns, session.domain_end_ns, ticks, refs)


def detect_memory_reference(compiled, rule, *, batch_rows=65536):
    """从原内存信号到完整活动/点事件执行参考链。

    参数: compiled/rule当前输入；batch_rows为正原生int的完整组批大小。
    返回: Event tuple，来源/质量/稳定ID均来自当前任务。
    异常: 时间/计划/批大小错误传播，内部候选不作为最终输出。
    """
    # 完整证据包含精确deadline，不额外读旧链。
    timeline = build_timeline_reference(compiled, rule)
    # 同一检测器跨batch保持状态，唯一真正EOF后finish。
    return detect_reference(rule, timeline, batch_rows=batch_rows)
