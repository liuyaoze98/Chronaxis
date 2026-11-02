"""把同轴的更新前点、连续后态及当前点求值结果组装成条件证据。

输入为调用方已经求出的三个BOOL视图、整数纳秒轴，以及实际更新、真实无效更新、
来源结束和会话terminal四种独立标志；输出冻结ConditionTick tuple。更新前点只用于
证明真实更新是否导致UNKNOWN，不把其反事实诊断加入当前真实诊断。terminal强制
连续状态UNKNOWN并叠加MISSING，当前点仍可保留真正末点的TRUE或FALSE。
参考实现逐点使用标量结果，数组实现独立执行valid/quality与因果掩码运算，最后装箱。
本模块不求值表达式、不读取来源、不访问state或时钟、不生成时间轴，也不更新检测器。
数组临时列及输出规模随N增长，后续调用方必须先申请预算；本纯内核不是有限执行器。
NumPy只在数组入口加载，参考入口及模块导入保持标准库核心的依赖边界。
"""

# 已求值结果和冻结证据共享协议；这里不调用任一表达式或保持数值核。
from .expression_reference import Evaluation
from .numeric import ScalarValue
from .temporal import ConditionTick
from .types import QualityFlag as Q, SignalDType as D, Truth
# 参考轴先要求原生int，再沿用已有int64端点检查，不进行t-1或差分运算。
from ..timebase.conversion import require_int64_ns


def _reference_truth(result):
    """把已经验证的BOOL标量转为三值，未知存储占位不参加真假判断。

    参数: result当前Evaluation，调用入口已检查ScalarValue及BOOL声明。
    返回: Truth.TRUE、Truth.FALSE或Truth.UNKNOWN。
    异常: 无主动异常；调用者必须先完成typed结果校验。
    """
    # valid先于值解释，无效None/False等占位都只表示UNKNOWN。
    if not result.value.valid:
        return Truth.UNKNOWN
    # 只有已验证的原生BOOL正常值进入二值分支，不对任意数值使用truthiness。
    return Truth.TRUE if result.value.value else Truth.FALSE


def condition_ticks_reference(times, before, continuous, point, actual_updates,
                              invalid_updates, observation_ends, terminals):
    """独立逐点组装完整条件证据，不从来源推断更新标志或补造时间。

    参数:
        times: 原生int构成的tuple，单位ns，int64范围内严格递增。
        before/continuous/point: 同长Evaluation tuple，三个视图的结果dtype均为BOOL。
        actual_updates: 同长原生bool tuple，当前条件依赖中是否有真实更新。
        invalid_updates: 同长原生bool tuple，实际选中的更新样本是否无效；
            不把保持值因TTL到期而无效算作真实无效更新，True必须同时有actual。
        observation_ends: 同长原生bool tuple，条件依赖的来源是否在此刻结束观测。
        terminals: 同长原生bool tuple，会话连续域是否结束；至多唯一末项，
            不要求同时存在来源EOF，普通批次全False与空输入均合法。
    返回:
        tuple[ConditionTick, ...]，保留连续/点质量、真实因果及当前依赖诊断。
    异常:
        TypeError为容器、原生元素、模型或非BOOL；ValueError为长度、回退/重复时间、
        非末terminal或invalid缺actual；OverflowError为时间越界；MemoryError为分配失败。
    副作用:
        只创建当前有限输入的输出模型，不修改任何输入；申请预算由调用者负责。
    """
    # 明确固定tuple协议，不能从任意迭代器隐式收集全量来源。
    columns = (before, continuous, point, actual_updates, invalid_updates, observation_ends, terminals)
    if type(times) is not tuple or any(type(column) is not tuple for column in columns):
        raise TypeError('参考条件证据需要时间、三视图及四标志tuple')
    # 行数必须已经对齐，禁止zip静默截断或广播修补错位证据。
    size = len(times)
    if any(len(column) != size for column in columns):
        raise ValueError('条件证据各输入长度必须相同')
    # 时间不接受bool/NumPy标量；直接比较避免极值差分或t-1溢出。
    previous = None
    for time in times:
        if type(time) is not int:
            raise TypeError('参考条件证据时间需要原生int纳秒')
        require_int64_ns(time)
        if previous is not None and time <= previous:
            raise ValueError('条件证据时间必须严格递增')
        previous = time
    # 四种标志不能用整数或字符串真假代替真实证据。
    for column in (actual_updates, invalid_updates, observation_ends, terminals):
        if any(type(value) is not bool for value in column):
            raise TypeError('参考条件证据标志需要原生bool')
    # 任一前置terminal都会违反唯一末组契约；普通批次允许完全没有terminal。
    if any(terminals[index] for index in range(max(0, size - 1))):
        raise ValueError('terminal只能唯一出现在输入末项')
    if any(invalid and not actual for invalid, actual in zip(invalid_updates, actual_updates)):
        raise ValueError('真实无效更新必须同时有actual_update')
    # Evaluation自身不验证字段，先核对真实标量/诊断协议与BOOL声明再解释值。
    for column in (before, continuous, point):
        for result in column:
            if (not isinstance(result, Evaluation) or not isinstance(result.value, ScalarValue)
                    or not isinstance(result.dependency_quality, Q)):
                raise TypeError('参考三视图需要typed Evaluation/ScalarValue/QualityFlag')
            if result.value.dtype is not D.BOOL:
                raise TypeError('条件证据三视图必须为BOOL，数值不能隐式转bool')
    # 参考逐点只使用当前三个结果；不调用数组实现或重新查询历史。
    ticks = []
    for index, time in enumerate(times):
        old, current, observed = before[index], continuous[index], point[index]
        old_state = _reference_truth(old)
        state, point_state = _reference_truth(current), _reference_truth(observed)
        # known更新前点、实际无效或新增结果质量位证明未知来自真实更新。
        causal = (invalid_updates[index] or old_state is not Truth.UNKNOWN
                  or bool(observed.value.quality & ~old.value.quality))
        actual_unknown = actual_updates[index] and point_state is Truth.UNKNOWN and causal
        # 半开连续域在真实terminal结束，但不更改闭区间当前点的证据。
        quality = current.value.quality
        if terminals[index]:
            state, quality = Truth.UNKNOWN, quality | Q.MISSING
        # 仅当前连续与当前点的依赖原因属于真实诊断，before反事实原因排除。
        diagnostic = current.dependency_quality | observed.dependency_quality
        ticks.append(ConditionTick(time, state, quality, actual_updates[index],
                                   observation_ends[index], terminals[index], point_state,
                                   observed.value.quality, actual_unknown, diagnostic))
    # 冻结输出供检测器按完整组推进；空输入自然得到空tuple。
    return tuple(ticks)


def condition_ticks_numpy(times, before, continuous, point, actual_updates,
                          invalid_updates, observation_ends, terminals):
    """独立按列构造因果与三值证据，最后仅恢复不可变ConditionTick模型。

    参数:
        times: 精确ndarray，一维int64纳秒轴，严格递增。
        before/continuous/point: 同轴ArrayEvaluation，NumericArray逻辑dtype为BOOL。
        actual_updates: 精确ndarray，形状(N,)的bool真实更新列。
        invalid_updates: 同形状bool列，实际选中更新样本无效；TTL不属于真实更新，
            True必须有同时刻actual_updates=True。
        observation_ends: 同形状bool列，条件依赖的来源观测结束标志。
        terminals: 同形状bool列，会话连续域结束标志，至多唯一末项；
            不要求来源EOF同时成立，空轴及无terminal合法。
    返回:
        tuple[ConditionTick, ...]；数值/因果计算整列完成，装箱不调用参考实现。
    异常:
        TypeError为数组布局、模型或非BOOL；ValueError为shape、非递增时间或矛盾标志；
        MemoryError为列/输出分配失败。不隐式cast、不调用vectorize或标量参考数值核。
    内存与副作用:
        临时状态/quality/因果/诊断列均为(N,)，不修改借用的输入；预算须由调用者先申请。
    """
    # 延迟加载数组依赖，使只导入/使用参考入口时不引入NumPy。
    import numpy as np
    from .expression_numpy import ArrayEvaluation
    from .numeric_numpy import NumericArray
    # 轴的物理布局明确，不用asarray/astype隐式转换任意输入。
    if type(times) is not np.ndarray or times.ndim != 1 or times.dtype != np.dtype('int64'):
        raise TypeError('数组条件证据时间需要一维精确int64 ndarray')
    # 比较相邻坐标而非np.diff，INT64_MIN到INT64_MAX的合法递增不会回绕。
    if np.any(times[1:] <= times[:-1]):
        raise ValueError('条件证据时间必须严格递增')
    # 四标志是同形状bool列；禁止广播或对象数组真值进入因果运算。
    for column in (actual_updates, invalid_updates, observation_ends, terminals):
        if type(column) is not np.ndarray or column.ndim != 1 or column.dtype != np.dtype('bool'):
            raise TypeError('数组条件证据标志需要一维精确bool ndarray')
        if column.shape != times.shape:
            raise ValueError('条件证据标志与时间shape必须相同')
    # 终点只能是当前输入末项，真实无效标志必须有同时刻实际更新。
    if np.any(terminals[:-1]):
        raise ValueError('terminal只能唯一出现在输入末项')
    if np.any(invalid_updates & ~actual_updates):
        raise ValueError('真实无效更新必须同时有actual_update')
    # 三个静态视图复用已校验模型，仅检查本次BOOL和同轴布局；不复制或重新求值。
    for result in (before, continuous, point):
        if not isinstance(result, ArrayEvaluation) or not isinstance(result.value, NumericArray):
            raise TypeError('数组三视图需要typed ArrayEvaluation/NumericArray')
        if result.value.dtype is not D.BOOL:
            raise TypeError('条件证据三视图必须为BOOL，数值不能隐式转bool')
        if result.value.values.shape != times.shape or result.dependency_quality.shape != times.shape:
            raise ValueError('条件证据三视图与时间shape必须相同')
    # 因果来自实际invalid、更新前known或点结果新增质量位，整列掩码独立于参考。
    causal = (invalid_updates | before.value.valid
              | ((point.value.quality & ~before.value.quality) != 0))
    actual_unknown = actual_updates & ~point.value.valid & causal
    # 形状(N,)的整数状态列使用0/1/2对应TRUE/FALSE/UNKNOWN；无效False占位不决定真值。
    continuous_states = np.where(continuous.value.valid, np.where(continuous.value.values, 0, 1), 2)
    point_states = np.where(point.value.valid, np.where(point.value.values, 0, 1), 2)
    # 只修改新建连续列，terminal不延长面积；借用的点结果与质量保持原样。
    continuous_states[terminals] = 2
    quality = continuous.value.quality.copy()
    quality[terminals] |= np.uint16(Q.MISSING)
    # 当前实际诊断整列合并，刻意排除更新前反事实诊断。
    diagnostic = continuous.dependency_quality | point.dependency_quality
    # 列运算已完成，只在末端把形状(N,)存储恢复为原生int/bool及枚举模型。
    truths = (Truth.TRUE, Truth.FALSE, Truth.UNKNOWN)
    return tuple(ConditionTick(int(time), truths[int(continuous_states[index])], Q(int(quality[index])),
                               bool(actual_updates[index]), bool(observation_ends[index]), bool(terminals[index]),
                               truths[int(point_states[index])], Q(int(point.value.quality[index])),
                               bool(actual_unknown[index]), Q(int(diagnostic[index]))) for index, time in enumerate(times))
