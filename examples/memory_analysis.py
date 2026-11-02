"""用合成电压和电流找出两段持续活动，并计算每段及整个会话的能量。

这个示例从已经取得的信号开始：建立输入 → 计算功率 → 判断电流条件
→ 找到时间段 → 对功率积分。电压单位为V，电流为A，功率为W，能量为J。
运行方式（仓库根目录，先将src加入PYTHONPATH）：
    python -B examples/memory_analysis.py

合成输入如下；表中时间用秒展示，代码和输出时间均使用整数纳秒：
    时间(s)    raw_v(V)    raw_i(A)    raw_id
    0          400         10         2**53 + 1
    2          —            0         —
    3          —           20         —
    5          —            0         —
    6          —            —         2**53 + 1
“—”表示这一行没有更新该字段，仍按有效期使用上次值；不表示无效观测。
各信号的有效期都是10秒，分析范围为[0, 6)秒，即含0秒、不含6秒。
6秒处的真实输入行仍保留来源位置，但不增加连续区间的积分面积。

默认条件为current > 5 A，要求连续成立1秒才确认活动：
    第一段从0秒开始，1秒确认，2秒结束；400 × 10 × 2 = 8000 J。
    第二段从3秒开始，4秒确认，5秒结束；400 × 20 × 2 = 16000 J。
确认后保留条件最初成立的时间，所以第一段从0秒开始积分，而不是1秒。
两段之间电流为0，条件不成立；会话条件积分为8000 + 16000 = 24000 J。

main分别运行普通Python参考实现和NumPy实现，并打印同一结构的JSON。
events中每项依次为开始时间、确认时间、结束时间（纳秒）及结束状态；
event_energy_j为各活动能量，session_energy_j为会话条件积分，
condition_coverage为条件可判断的时间占比，本例应为1。
backends_equal比较两种实现的完整结果；手算值用于另行核对结果正确性。

本文件只向标准输出打印结果，不读写日志或DBC，不修改调用者的绑定对象。
需要NumPy依赖；会话条件和活动分别准备完整指标序列，同次运行中的活动
复用无条件功率序列。各窗口仍单独归约，不承诺生产预算或查询复杂度。
M2的公共AnalysisRunner、流式内存预算和CAN入口不在本例验证范围内。
"""

# 输出JSON，便于核对时间边界和手算能量。
import json
# 输入模型、表达式编译及普通Python参考实现来自核心模块。
from chronaxis.core import (DerivedDefinition, Interval, MemoryRow, CalculationDefinition, SessionSpec, SignalBindings,
                            SignalDefinition, SignalDType as D, SourceSpec, TemporalRule, TimebaseSpec, TimeType,
                            compile_expression, build_calculation_series_reference, compute_reference, detect_memory_reference)
# NumPy的完整列只准备一次，再交给同后端指标内核按窗口裁剪。
from chronaxis.core.calculations_memory_numpy import build_calculation_series_numpy
from chronaxis.core.calculations_numpy import compute_numpy
# NumPy的活动检测使用自己的计算实现。
from chronaxis.core.temporal_memory_numpy import detect_memory_numpy


def build_bindings():
    """建立上表的输入数据，并将原字段绑定到表达式使用的名称。

    参数:
        无。输入、分析范围和10秒有效期都在本函数内明确给出。
    返回:
        SignalBindings: 包含一个0—6秒会话，以及voltage、current、identifier
        三个信号。预先登记派生名称power，后续由run_analysis定义计算式。
    异常:
        TypeError、ValueError: 时钟、来源、会话或信号声明不符合模型要求时，
        保留底层校验异常。
    边界:
        raw_id使用INT64保存2**53 + 1，避免转换成浮点数后丢失精度。
        每次调用都创建新的输入与绑定，不从上一次分析继承状态。
    """
    # 所有合成行使用同一个相对时钟，起点由本例明确给出。
    clock = TimebaseSpec('clock', TimeType.RELATIVE, 'memory-analysis-v1')
    # 只更新每行给出的字段；2—3秒电流为0，将两段活动分开。
    data = ((0, {'raw_v': 400., 'raw_i': 10., 'raw_id': 2 ** 53+1}),
            (2_000_000_000, {'raw_i': 0.}), (3_000_000_000, {'raw_i': 20.}),
            (5_000_000_000, {'raw_i': 0.}), (6_000_000_000, {'raw_id': 2 ** 53+1}))
    # 保留输入顺序和每行序号，来源的观测范围明确为0—6秒。
    source = SourceSpec('sensor', clock, tuple(MemoryRow(time, values, index) for index, (time, values) in enumerate(data)), observation_start_ns=0, observation_end_ns=6_000_000_000)
    # 会话积分范围为[0, 6)秒；6秒行保留来源记录，不增加积分面积。
    session = SessionSpec('session', clock, 0, 6_000_000_000, (source,))
    # 将原字段映射为voltage、current和identifier；每次更新有效10秒。
    signals = (SignalDefinition('voltage', 'sensor', 'raw_v', D.FLOAT64, 'V', 10_000_000_000),
               SignalDefinition('current', 'sensor', 'raw_i', D.FLOAT64, 'A', 10_000_000_000),
               SignalDefinition('identifier', 'sensor', 'raw_id', D.INT64, '1', 10_000_000_000))
    # 标识保持整数类型；先登记power名称，后续编译时再给出计算式。
    return SignalBindings(session, signals, derived_names=('power',))


def run_analysis(bindings, *, backend='numpy', batch_rows=65536, duration_ns=1_000_000_000):
    """按电流条件检测持续活动，计算活动能量和会话条件积分。

    参数:
        bindings (SignalBindings): 已建立的信号与会话绑定；需提供voltage、
            current和已登记的power名称，分别使用V、A和W单位。
        backend (str): 'reference'使用普通Python实现，'numpy'使用NumPy实现；
            默认'numpy'，其他值会被拒绝。
        batch_rows (int): 每批输入的样本数限制，默认65536，必须为正整数。
        duration_ns (int): 条件需要连续成立的时长，单位纳秒，默认1000000000；
            必须为非负整数，实际约束由TemporalRule校验。
    返回:
        tuple: (活动Event元组, 会话CalculationResult, (event_id, CalculationResult)元组)。
            会话结果只累计current > 5的区间；每个活动结果在其[开始, 结束)
            时间范围内积分。结果保留单位、覆盖情况和来源信息。
    异常:
        ValueError: backend不是允许值，或表达式、规则、指标配置不合法。
        TypeError: 输入对象或整数参数类型不满足底层要求。
        底层绑定、检测和积分异常原样传播。
    处理流程:
        1. 编译power = voltage * current和current > 5条件。
        2. 按指定实现检测持续活动，跨输入批次保留计时状态。
        3. 计算整个会话的条件积分；有活动时另准备一次无条件功率序列，
           再按每段活动的原窗口计算积分。
    副作用与边界:
        每次运行使用独立的计算状态，不修改bindings。
        活动检测按批次处理；指标序列只在本次调用内复用，不跨运行缓存。
        每个窗口仍扫描已准备的完整序列，不承诺流式内存上限或查询复杂度。
    """
    # 拒绝未知实现名称，避免调用者选择的计算方式被悄悄替换。
    if backend not in ('reference', 'numpy'):
        # 错误包含允许的实现名称，方便调用者修正参数。
        raise ValueError('backend需reference或numpy')
    # 功率等于电压乘电流，单位为W；在编译时检查表达式和单位。
    derived = (DerivedDefinition('power', 'voltage * current', 'W'),)
    # 将power名称与已声明的电压、电流绑定，创建本次计算的表达式。
    power = compile_expression('power', bindings, derived=derived)
    # 条件读取绑定后的current；裸常量5按电流单位解释为5 A。
    condition = compile_expression('current > 5', bindings, derived=derived)
    # 持续规则要求条件连续成立duration_ns，活动归属于当前会话。
    rule = TemporalRule('active', 'memory_demo', bindings.session.session_id, 'condition_duration', duration_ns)
    # 按backend选择对应的活动检测与积分函数；两种实现分别计算结果。
    detector = detect_memory_reference if backend == 'reference' else detect_memory_numpy
    # 同后端独立准备和归约，复用已经求值的typed列，不重复归一化原行。
    prepare = build_calculation_series_reference if backend == 'reference' else build_calculation_series_numpy
    calculation = compute_reference if backend == 'reference' else compute_numpy
    # 跨批次保留尚未确认的活动计时；输入结束时统一处理未结束活动。
    events = detector(condition, rule, batch_rows=batch_rows)
    # 会话指标覆盖整个分析范围，随后用条件挑出需要积分的时间段。
    session_spec = CalculationDefinition('session_energy', 'integral', Interval(bindings.session.domain_start_ns, bindings.session.domain_end_ns))
    # 条件不成立的区间不累加能量，但仍计入可判断条件的时间。
    session_result = calculation(prepare(power, session_spec, condition=condition), session_spec)
    # 只在第一个activity出现时准备无条件功率；不能继承会话筛选条件。
    event_series, event_results = None, []
    for event in events:
        # point事件没有持续区间，不创建活动积分或为它准备完整序列。
        if event.event_type != 'activity':
            continue
        if event_series is None:
            # 会话域保留全部更新/TTL边界，各指标内核会独立裁剪其实际窗口。
            event_series = prepare(power, session_spec)
        # 各活动仍使用原始[开始, 结束)范围、原ID及独立CalculationDefinition。
        spec = CalculationDefinition('event_energy', 'integral', Interval(event.start_ns, event.end_ns), scope='event')
        event_results.append((event.event_id, calculation(event_series, spec)))
    # 返回完整活动和指标对象，保留时间、覆盖情况和来源信息。
    return events, session_result, tuple(event_results)


def main():
    """运行合成任务，打印两种实现的对照结果和可核对的能量。

    参数:
        无。调用build_bindings取得本文件说明的合成输入。
    返回:
        None。向标准输出打印一个JSON对象；时间为纳秒，能量为J。
    异常:
        TypeError、ValueError及底层分析异常原样传播，不输出成功结果。
    处理流程:
        参考实现使用每批1行，NumPy实现使用每批2行；比较完整结果，
        并输出两段活动、各段能量、会话条件积分及条件覆盖率。
    """
    # 两种实现使用同一份输入；各次运行的计算状态独立。
    bindings = build_bindings()
    # 参考实现每批1行，用于检查活动计时能跨越批次边界。
    reference = run_analysis(bindings, backend='reference', batch_rows=1)
    # NumPy实现每批2行；随后比较完整对象，包含时间、能量和状态。
    array = run_analysis(bindings, backend='numpy', batch_rows=2)
    # 输出两段活动和能量；每项活动时间均使用纳秒，中间空档不合并。
    result = {'input_id': 'memory-analysis-v1', 'backends_equal': reference == array,
              'events': [[event.start_ns, event.confirmed_ns, event.end_ns, event.status] for event in reference[0]],
              'event_energy_j': [calculation.value for _, calculation in reference[2]],
              'session_energy_j': reference[1].value, 'condition_coverage': reference[1].condition_coverage}
    # 打印本次合成任务结果；手算应为8000 J、16000 J和总计24000 J。
    print(json.dumps(result, ensure_ascii=False))


# 导入此文件时只定义函数；直接运行文件时才执行示例。
if __name__ == '__main__':
    # 执行入口打印JSON，分析失败时保留异常。
    main()
