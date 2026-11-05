"""从现有内存信号计算表达式，接入参考统计、TRUE时长或选择行流。

输入为已编译表达式、CalculationDefinition和可选布尔条件。先检查真实绑定
及多来源同步依据，再从原行提取依赖，按更新、有效期和窗口边界建立
共同纳秒轴；参考对齐与表达式求值生成CalculationSeries，最后得到CalculationResult。
duration主表达式需BOOL，select可保留数值、BOOL或ENUM原值；选择行流返回
SelectionRow迭代器，其输入和中间历史仍完整物化，不能据此宣称生产预算完成。

真实样本标志只取数值表达式的依赖更新；条件独自更新和合成窗口边界
不能新增数值样本。每个左端值用于直到下一时间的区间，末点不增加面积。
数值与条件分别保存有效性，原依赖质量另存，UNKNOWN不能当作FALSE。

依赖参考转换、对齐、表达式和指标模块，不读取日志、调用旧解码或写出。
这是完整内存历史的便利入口，创建本次局部结果，不修改输入，不跨任务
继承绑定或信号值，也不调用NumPy数值内核。
"""

# 类型/身份协议明确检查，不使用无类型计划。
from .enum_codes import memory_histories, aligned_scalar
from .expression import CompiledExpression
# 真标量表达式解释，与NumPy数值独立。
from .expression_reference import evaluate_reference
# 当前指标/行流共享typed协议，数值与选择各有独立真实入口。
from .calculations import CalculationSeries, CalculationDefinition, calculation_conversion
# 实际ZOH/样本/coverage逐区间参考。
from .calculations_reference import compute_reference, select_reference
# 当前分析域用精确半开模型。
from .models import Interval
# 原行规范化和typed值，不重复DBCfactor。
from .numeric import ScalarValue, memory_series_reference
# 更新/TTL时间协议可共享，保持参考独立。
from .state import align_reference, common_timeline
# BOOL条件与数值类型严格分开。
from .types import SignalDType as D
from .where_updates import contains_where, reference_updates


def _scalar_context(bindings, aligned, index):
    """把同一时刻各信号的保持值整理为标量表达式输入。

    参数: bindings为运行绑定，aligned为各列视图，index为时间位置。
    返回: 保留类型、有效性及枚举域的标量映射。
    异常: 无效绑定或位置直接报错。
    """
    context = {}
    for name, states in aligned.items():
        definition, state = bindings.resolve(name), states[index]
        context[name] = aligned_scalar(definition, state)
    return context


def require_calculation_plan(compiled, spec, condition):
    """检查指标表达式类型及可选条件是否属于同一真实输入。

    参数:
        compiled: 当前CompiledExpression；duration需BOOL，select可使用全部声明dtype。
        spec: CalculationDefinition，其他标量统计要求数值根。
        condition: 可选BOOL根的CompiledExpression，须与数值计划的绑定身份相同。
    返回:
        合并去重后的实际依赖名称元组，保留数值依赖在前的顺序。
    异常:
        TypeError: 数值计划或请求模型类型错误。
        ValueError: 根与算子类型不匹配、条件不是BOOL、绑定身份冲突或同步不足。
    边界:
        只合并分析层依赖并检查当前同步声明，不改变旧读取范围或解码调用。
    """
    # 配置必须真实已编译，不用metadata名称冒充运行。
    if not isinstance(compiled, CompiledExpression) or not isinstance(spec, CalculationDefinition):
        # 不隐式编译任意代码文本。
        raise TypeError('memory指标需CompiledExpression及CalculationDefinition')
    # duration只收BOOL；select可读取全部dtype；其他数值统计不将bool/enum当编码。
    allowed = tuple(D) if spec.operation == 'select' else (D.BOOL,) if spec.operation == 'duration' else (D.INT64, D.UINT64, D.FLOAT64)
    if compiled.root.dtype not in allowed:
        # 程序错误不降为未知值。
        raise ValueError('指标表达式dtype与算子不匹配')
    if spec.operation == 'select':
        # 在回读和申请预算前校验输出；块中仍是原值，两个选择核各自在交付行时换算一次。
        calculation_conversion(spec, compiled.root.unit).dtype(compiled.root.dtype)
    # 可选条件身份必须当前完整绑定，不继承另一个任务。
    if condition is not None:
        # 只合法三值BOOL，与同名但不同值的绑定区分。
        if not isinstance(condition, CompiledExpression) or condition.root.dtype is not D.BOOL or condition.bindings.identity != compiled.bindings.identity:
            # 不自动重绑定或取第一个候选。
            raise ValueError('指标条件需BOOL且真实binding identity相同')
    # 合并静态依赖，不改变原旧路径调用/扫描范围。
    names = tuple(dict.fromkeys(compiled.dependencies + (() if condition is None else condition.dependencies)))
    # 多来源同步必须明确，单纯offset没有证明作用。
    compiled.bindings.require_synchronized(names)
    # 每次当前依赖列表隔离，不存全局缓存。
    return names


def build_calculation_series_reference(compiled, spec, *, condition=None):
    """从当前原行生成完整指标时间轴、值、条件和真实更新标志。

    参数:
        compiled: 当前已校验表达式，类型与spec算子匹配；spec为窗口与指标请求。
        condition: 可选且绑定身份一致的BOOL表达式，省略表示不按条件筛选。
    返回:
        CalculationSeries。时间为整数纳秒，值与条件共用完整轴；窗口边界可参与
        积分保持，但actual_value_updates为False，不作为真实样本。
    异常:
        绑定、时间、来源、同步或配置检查失败时传播底层异常。
    流程:
        提取依赖并归一化，加入域内窗口端点，参考保持后逐时间组求值。
        条件依赖可增加时间边界，真实样本标志只来自数值依赖。
        保留完整内存历史和新结果，不延长会话观测域，也不额外读取或解码。
    """
    # 在运行前核实数值与条件的输入绑定，并检查合并依赖所需的同步依据。
    names = require_calculation_plan(compiled, spec, condition)
    # 独立参考原行归一化，仅当前已暴露输入。
    histories = memory_histories(compiled, names, memory_series_reference, condition)
    # 实际域不按请求范围延长，EOF外不补周期。
    session = compiled.bindings.session
    # 只插入域内请求边界，协议轴也包括updates/TTL/source边界。
    boundaries = tuple(time for time in (spec.window.start_ns, spec.window.end_ns) if session.domain_start_ns <= time <= session.domain_end_ns)
    # 常量无依赖也明确当前会话域。
    times = common_timeline(tuple(histories.values()), boundaries) if histories else tuple(sorted({session.domain_start_ns, session.domain_end_ns, *boundaries}))
    # 当前连续保持独立标量求值，不采用数组参考。
    aligned = {name: align_reference(history, times) for name, history in histories.items()}
    # where 的分支切换也能产生样本；只为这种表达式取同刻报文到来前的状态。
    before = ({name: align_reference(histories[name], times, point=True, strict_before=True, left_limit=True) for name in compiled.dependencies}
              if contains_where(compiled.root) else None)
    # 每个输出列都保存typed原结果和独立诊断。
    values, conditions, actual, diagnostics = [], [], [], []
    # 参考逐完整时间组构造当前局部context。
    for index in range(len(times)):
        # 同时刻全部依赖已收齐，不逐字段更新产生瞬态选择。
        context = _scalar_context(compiled.bindings, aligned, index)
        # 数值表达式只传它自己的精确依赖键。
        numeric = evaluate_reference(compiled, {name: context[name] for name in compiled.dependencies}, compiled.bindings)
        # 保存实际数值及原依赖质量，不将invalid变成正常零。
        values.append(numeric.value)
        # 窗口/TTL边界的保持值不冒充样本；条件独自更新也不是数值样本。
        if before is None:
            actual.append(any(aligned[name][index].actual_update for name in compiled.dependencies))
        else:
            updates = {name: aligned[name][index].actual_update for name in compiled.dependencies}
            actual.append(reference_updates(compiled.root, context, _scalar_context(compiled.bindings, before, index), updates))
        # 条件可决定known且仍有原未知依赖诊断。
        diagnostic = numeric.dependency_quality
        # 只显式条件参与选择，无条件不同于全UNKNOWN。
        if condition is not None:
            # 当前绑定和精确依赖键通过公共执行门槛。
            selected = evaluate_reference(condition, {name: context[name] for name in condition.dependencies}, compiled.bindings)
            # TRUE/FALSE/UNKNOWN结果与数值独立保留。
            conditions.append(selected.value)
            # known选择不抹去原未知依赖质量。
            diagnostic |= selected.dependency_quality
        # 本组诊断不跨任务继承。
        diagnostics.append(diagnostic)
    # 当前完整值和可选条件计划身份一并关联。
    identity = compiled.identity + ('' if condition is None else ':' + condition.identity)
    # 真实原字段定位保留全部依赖，metadata不是绑定证明。
    refs = tuple(compiled.bindings.source_ref(name) for name in names)
    # 数值/条件都已按同一完整轴独立计算。
    return CalculationSeries(Interval(session.domain_start_ns, session.domain_end_ns), times, tuple(values), tuple(actual), compiled.root.unit,
                        tuple(conditions) if condition is not None else None, tuple(diagnostics), identity, refs)


def select_memory_reference(compiled, spec, *, condition=None):
    """从现有内存信号独立对齐求值，返回真实更新选择行流。

    参数: compiled当前绑定表达式；spec为select；condition可选同身份BOOL表达式。
    返回: SelectionRow迭代器，不积累全部输出行。
    异常: 构造时间轴/求值时传播输入错误；筛选配置错误在消费时传播。
    边界: 输入和中间历史仍完整物化，不声明生产有界预算；不接旧reader/decoder。
    """
    # 参考桥接与数组桥接独立提取、对齐和求值。
    series = build_calculation_series_reference(compiled, spec, condition=condition)
    return select_reference(series, spec)


def compute_memory_reference(compiled, spec, *, condition=None, budget=None):
    """从已有内存行执行参考表达式和指标计算，返回完整指标结果。

    参数:
        compiled: 当前表达式；spec为数值统计或BOOL duration的CalculationDefinition。
        condition: 可选且关联同一真实输入的BOOL表达式。
        budget为精确分位数的可选共享RAM账本，省略时采用项目默认配额。
    返回:
        CalculationResult，保存面积、时间/样本统计或TRUE时长，以及覆盖、未知范围与来源。
    异常:
        输入、绑定或配置检查失败时传播底层异常；数值失败由指标质量明确报告。
    流程:
        先建立CalculationSeries，再独立执行参考指标计算；不修改原行或调用数组后端。
    """
    # 将内存绑定的原始行和表达式结果交给指标计算器。
    series = build_calculation_series_reference(compiled, spec, condition=condition)
    # 独立参考面积/统计/覆盖，不调用数组后端。
    return compute_reference(series, spec, budget=budget)
