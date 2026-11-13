"""解释已构建计划的声明检查结果、计算依赖和当前能力限制。

输入为AnalysisPlan，validate_analysis_plan生成ValidationReport，explain_analysis_plan
生成ExplainReport，列出依赖节点、需要保留的历史时长和预算声明。
报告不重新读取CSV或DBC，不运行旧reader或数值内核。
valid与execution_ready表示当前声明使用已接入的公共执行路径；typed计划被
替换为不支持的来源、算子或后端时会报告明确errors。静态可执行不证明来源
已读、真实字段已核实或峰值RAM一定满足预算。预算与历史需求不是实测结果。
"""

# 冻结报告与只读映射，不维护跨任务状态。
from ..core.moments import MOMENTS
from ..core.quantiles import SAMPLE_QUANTILES
from dataclasses import dataclass
from types import MappingProxyType
from collections.abc import Mapping
# 报告只消费已经静态校验的计划。
from .plan import AnalysisPlan
from .models import MessageCalculationPlan
from ..core.counts_v4 import COUNT_OPERATIONS, OBJECT_COUNTS
from .message_calculations import require_message_calculation
from .legacy_execution import require_can_decode_scope
from .input_requirements import InputRequirements, collect_input_requirements
from .sequences import sequence_dependencies
from .backend_selection import BACKENDS, select_backend
from .intervals import IntervalPlan, DiagnosticPlan, require_interval_declarations
from .export_options import require_export_options,SignalCSVOutput,CANFramesOutput
# 只检查原冻结来源配置的类型，不导入会读输入的adapter或重建原memory行。
from ..core.models import SourceSpec
from ..sources.csv_spec import SignalCSVSpec
from ..sources.can_spec import LegacyCANSpec, can_field_from_key
from ..sources.text_can_spec import CANTextSpec
from ..legacy.records import PROFILE_ID

# 静态校验和explain共用同一真实能力表，显式后端覆盖由调用方的有效plan view传入。
_BACKENDS = BACKENDS
_RULES = ('condition_duration', 'rising_edge', 'falling_edge', 'start_only', 'window_delta', 'debounce', 'hysteresis', 'start_end')
_MERGES = ('none', 'overlap', 'overlap_and_adjacent', 'exit_delay')
_CALCULATIONS = ('integral', 'sample_minimum', 'sample_maximum', 'sample_mean', 'min_time',
            'max_time', 'time_weighted_mean', 'duration', 'select')


@dataclass(frozen=True)
class ValidationReport:
    """区分静态有效、来源元数据未核实及产品执行接线状态。

    warnings保存事实限制；capability_status不以类名或schema字段存在冒充支持。
    """

    valid: bool  # 静态配置检查结果。
    errors: tuple[str, ...]  # 不支持的typed替换声明等静态能力错误；合法计划为空。
    warnings: tuple[str, ...]  # 实际字段/范围/角色及当前平台能力等限制。
    capability_status: Mapping[str, str]  # 明确implemented/partial/unavailable/declared状态。
    execution_ready: bool  # 当前声明是否有公共执行路径，不代表输入已读或RAM实测通过。


@dataclass(frozen=True)
class ExplainNode:
    """保存单声明节点的实际依赖和预计执行层。

    backend说明数值实现、状态驱动或未接线；numpy路径包含内建逐点与批量数组，
    不表示每个步骤都使用数组。
    """

    node_id: str  # 当前计划节点身份。
    node_type: str  # derived/rule/window/calculation/message_calculation。
    dependencies: tuple[str, ...]  # 展开原信号别名。
    unit: str | None  # 单位适用时保留。
    backend: str  # numpy/reference/state_driver/unavailable。


@dataclass(frozen=True)
class ExplainReport:
    """保存计划依赖、历史需求和未执行的预算声明。

    validation沿用静态能力报告，plan_identity只识别配置和来源定位声明。
    source_names保持来源顺序，nodes保存计算节点和展开的原信号依赖。
    history_ns仅对实际普通样本依赖，按valid_for_ns和窗口pre取需要保留的时长；
    显式all额外产生的诊断样本不计作结果需求，warnings单独说明其读取与核验范围。
    budget原样报告资源限额。实例不保存运行状态，也不估算实测峰值内存。
    input_requirements保存各来源实际选择的检查策略和时间范围；它是计划声明，
    不能代替运行结果记录的实际检查计数和来源观测证明。
    """

    validation: ValidationReport  # 同一静态校验限制。
    plan_identity: str  # 声明身份，不等于实际文件内容身份。
    source_names: tuple[str, ...]  # 来源原序。
    nodes: tuple[ExplainNode, ...]  # 可解释依赖节点。
    history_ns: Mapping[str, int | None]  # TTL/pre纳秒；None表示还需DBC周期，不能伪造估计值。
    budget: Mapping[str, int | None]  # 配置预算，尚未实测峰值。
    input_requirements: InputRequirements | None = None  # 来源检查和时间范围声明；非法typed计划为空。
    intervals: IntervalPlan | None = None  # 当前有限声明；不含实际DBC周期或运行记录。
    diagnostics: DiagnosticPlan | None = None  # 独立诊断开关；声明不证明已执行。
    source_execution: tuple[Mapping, ...] = ()  # 每来源文件组织/读取进程上限；不是实际运行进程数。
    requested_backend: str | None = None  # 本次配置或调用覆盖；auto不代表一个独立数值实现。
    selected_backend: str | None = None  # 整个计划实际将使用的数值后端。
    backend_reason: str | None = None  # 静态选择依据，不是实测耗时。


def _window_available(window, rules) -> bool:
    """核窗口是否引用当前支持的真实规则、锚点与合并路径。

    参数: window为原WindowPlan；rules为本计划rule_id到原RulePlan的映射。
    返回: bool，同一判断供validation和explain节点使用。异常: 非法typed属性错误原样传播。
    副作用: 无，不构造窗口、事件或遍历输入样本。
    """
    # 未知规则没有产生父事件的执行路径，不能只靠窗口类名声明支持。
    rule = rules.get(window.event)
    if rule is None or rule.rule_type not in _RULES:
        return False
    # 活动规则保完整活动区间，其他已支持规则产生时间点；锚点须沿原含义。
    expected_anchor = 'activity' if rule.temporal_rule_type == 'condition_duration' else 'point'
    return window.merge in _MERGES and window.anchor == expected_anchor


def _can_source_available(source) -> bool:
    """核一个typed来源是否具有当前单BLF固定profile的声明能力。

    参数: source为当前SourcePlan，允许调用方以typed replace制造不匹配声明。
    返回: bool，供来源、raw输出和能力表共享。异常: 非法外部对象属性错误原样传播。
    副作用: 只查有限模型字段，不打开输入、DBC、writer或重建原始配置。
    """
    config = source.config
    return (source.source_type == 'can_blf' and isinstance(config, LegacyCANSpec)
        and config.name == source.name and config.legacy_profile == PROFILE_ID and config.unit == 's'
        and source.time_unit == 's' and source.timezone_text is None)


def _static_errors(plan: AnalysisPlan) -> tuple[str, ...]:
    """依据已构建typed声明检查公共执行路径，不重新解析配置或输入。

    参数: plan为已确认类型的AnalysisPlan，可含测试明确替换的不支持声明。
    返回: 错误tuple；已支持的构建计划为空。异常: 非法模型属性错误原样传播。
    边界: 这不是第二套配置解析器，不重算AST、原rows、绑定或计划identity。
    """
    # 当前只执行配置4；auto须在运行前选定已接入后端，不以raw_config覆盖typed替换。
    errors = []
    if type(plan.config_version) is not int or plan.config_version != 4:
        errors.append('当前执行只支持config_version=4')
    try:
        require_interval_declarations(plan)
        require_export_options(plan)
        from .record_execution import record_execution_errors
        errors.extend(record_execution_errors(plan))
    except (TypeError, ValueError, KeyError, StopIteration) as error:
        errors.append('间隔/诊断声明无效：' + str(error))
    if plan.execution.backend not in _BACKENDS:
        errors.append(f'未支持的执行backend：{plan.execution.backend}')
    # 类型与kind须同时对应实际reader路径，legacy/profile不会借memory配置冒充支持。
    source_types = {'memory': SourceSpec, 'signal_csv': SignalCSVSpec, 'can_blf': LegacyCANSpec,
                    'can_asc':CANTextSpec,'asc_or_blf':CANTextSpec,'raw_can_csv':CANTextSpec}
    if len({source.name for source in plan.sources}) != len(plan.sources):
        errors.append('来源名称不能重复')
    for source in plan.sources:
        expected = source_types.get(source.source_type)
        if expected is None or not isinstance(source.config, expected):
            errors.append(f'{source.name}：未支持或不匹配的来源kind：{source.source_type}')
        elif source.source_type == 'can_blf':
            # typed替换也不能跳过本profile的时间/名称能力限制；不重新读取或解析DBC。
            if not _can_source_available(source):
                errors.append(f'{source.name}：CAN只支持固定单BLF profile与无timezone的原秒时间')
        elif source.source_type in ('can_asc','asc_or_blf','raw_can_csv') and (source.config.source_type!=source.source_type or source.config.name!=source.name):
            errors.append(f'{source.name}：文本CAN种类或名称与实际声明不符')
    source_map = {source.name: source for source in plan.sources}
    for signal in plan.signals:
        source = source_map.get(signal.definition.source)
        if source is not None and isinstance(source.config, (LegacyCANSpec,CANTextSpec)):
            try:
                field = can_field_from_key(signal.definition.field)
                if field.channel != source.config.channel:
                    errors.append(f'{signal.definition.name}：CAN字段通道与来源不符')
            except (TypeError, ValueError):
                errors.append(f'{signal.definition.name}：CAN字段不是规范六字段定位')
    # 仅建立当前有限节点引用表，既不重编译表达式，也不访问来源内容。
    rules = {rule.rule_id: rule for rule in plan.rules}
    windows = {window.window_id: window for window in plan.windows}
    # 未支持状态机不能借已经构建的condition冒充可运行规则。
    for rule in plan.rules:
        if rule.rule_type not in _RULES:
            errors.append(f'{rule.rule_id}：未支持的规则kind：{rule.rule_type}')
    if type(plan.sequences) is not tuple:
        errors.append('sequences需要冻结tuple')
    else:
        sequence_ids = set(rules) | set(windows) | {item.calculation_id for item in plan.calculations}
        sequence_ids.update(item.calculation_id for item in plan.message_calculations)
        for sequence in plan.sequences:
            try:
                sequence_dependencies(sequence, plan.rules, plan.bindings)
                if sequence.sequence_id in sequence_ids:
                    raise ValueError('计划ID重复：' + sequence.sequence_id)
                sequence_ids.add(sequence.sequence_id)
            except (TypeError, ValueError) as error:
                errors.append('sequences：' + str(error))
    # 窗口路径和explain沿同一能力判断，缺父引用明确报告而不触发字典索引异常。
    for window in plan.windows:
        if not _window_available(window, rules):
            errors.append(f'{window.window_id}：未支持的窗口merge/anchor或规则引用')
    # 数值与选择仅有明确九种口径，积分固定使用左侧保持；不接受legacy_sum或新插值。
    for calculation in plan.calculations:
        if (calculation.operation not in _CALCULATIONS + (COUNT_OPERATIONS + MOMENTS + SAMPLE_QUANTILES)
                and (plan.extensions is None or calculation.operation not in plan.extensions.reductions)):
            errors.append(f'{calculation.calculation_id}：未支持的指标operation：{calculation.operation}')
        if calculation.operation in OBJECT_COUNTS:
            # typed计划同样须引用存在且对象类型相符的规则或窗口。
            target = calculation.count_target
            rule = rules.get(target)
            if (calculation.scope != 'session' or calculation.signal is not None or calculation.condition is not None
                    or calculation.unit != '1' or (target not in windows if calculation.operation == 'segment_count'
                    else rule is None or (rule.temporal_rule_type == 'condition_duration') != (calculation.operation == 'activity_count'))):
                errors.append(f'{calculation.calculation_id}：对象计数来源或范围不合法')
        if calculation.method != ('zoh' if calculation.operation == 'integral' else None):
            errors.append(f'{calculation.calculation_id}：未支持的指标method：{calculation.method}')
        # 未知范围不进入explain的字典索引，不能让unsupported报告变成KeyError。
        if calculation.scope != 'session':
            scope, separator, target = calculation.scope.partition(':') if type(calculation.scope) is str else ('', '', '')
            known_event = scope == 'event' and target in rules
            known_segment = scope == 'segment' and target in windows
            if not separator or not (known_event or known_segment):
                errors.append(f'{calculation.calculation_id}：未支持的指标scope：{calculation.scope}')
    # 新消息域独立于普通指标；typed替换仍核实际来源、完整定位和原声明身份。
    if type(plan.message_calculations) is not tuple:
        errors.append('message_calculations需要冻结tuple')
    elif plan.message_calculations:
        ids = {item.rule_id for item in plan.rules} | {item.window_id for item in plan.windows}
        ids.update(item.calculation_id for item in plan.calculations)
        for calculation in plan.message_calculations:
            try:
                require_message_calculation(calculation, plan.sources, plan.bindings)
            except (TypeError, ValueError) as error:
                name = calculation.calculation_id if type(calculation) is MessageCalculationPlan else 'message_calculations'
                errors.append(f'{name}：未支持的逐消息指标：{error}')
                continue
            if calculation.calculation_id in ids:
                errors.append(f'{calculation.calculation_id}：计划ID重复')
            ids.add(calculation.calculation_id)
    # 新结果表/清单与原始BLF请求分别检查，不让typed错误靠原raw_config冒充合法。
    if plan.outputs.tables not in ('readable_csv', 'csv', 'jsonl') or plan.outputs.manifest != 'json':
        errors.append('未支持的结果表或manifest格式')
    if type(plan.outputs.contributions) is not str or plan.outputs.contributions not in ('none', 'full'):
        errors.append('outputs.contributions需要none或full')
    # typed替换不能借旧raw_config绕过requested门禁；这里只收集静态错误，不打开来源。
    try:
        require_can_decode_scope(plan)
    except (TypeError, ValueError) as error:
        errors.append(str(error))
    return tuple(errors)


def _extension_backend_errors(plan):
    """检查此次输出实际用到的宿主操作。参数: 已构建计划。返回: 后端诊断。异常: 非法计划。

    在打开日志前检查，只查看编译好的表达式与变换。未引用的函数不要求提供当前后端。
    """
    registry = plan.extensions
    if registry is None:
        return ()
    from .transforms import active_transforms
    expressions = [expr for rule in plan.rules for expr in rule.expressions]
    expressions.extend(expr for item in plan.calculations for expr in (item.condition, item.signal) if expr is not None)
    expressions.extend(item.expr for item in plan.message_calculations)
    names = {alias for expr in expressions for alias in expr.dependencies}
    active = active_transforms(plan, names)
    expressions.extend(item.expression for item in active)
    required = {item.operation: registry.reductions[item.operation] for item in plan.calculations
                if item.operation in registry.reductions}
    required.update({item.operation: registry.transforms[item.operation] for item in active
                     if item.operation in registry.transforms})
    todo = [expr.root for expr in expressions]
    seen = set()
    while todo:
        node = todo.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        if node.operator == 'host_function':
            required[node.name] = registry.functions[node.name]
        todo.extend(node.args)
    errors = []
    for name, spec in sorted(required.items()):
        try:
            spec.require_backend(select_backend(plan).selected)
        except ValueError as error:
            errors.append(f'{name}: {error}')
    return tuple(errors)


def validate_analysis_plan(plan: AnalysisPlan) -> ValidationReport:
    """报告静态配置有效性及当前读取、执行和发布能力限制。

    参数:
        plan (AnalysisPlan): from_dict或load_analysis_plan已经构建的不可变计划。
    返回:
        ValidationReport。合法已接入计划valid为True且errors为空；warnings保留尚未核实的
        字段、观测范围和单位状态，capability_status记录当前接入情况。
        execution_ready随静态能力错误为False或True，不表示已读取或保证实际RAM。
    异常:
        TypeError: 输入不是AnalysisPlan；配置构建错误应由构建入口先报告。
    副作用:
        无来源读取，不重新核实CSV、BLF/DBC、实际字段或物理测量含义。
    """
    # 不把自由配置或类名占位当已校验计划。
    if not isinstance(plan, AnalysisPlan):
        # 用户应先调用严格构建入口。
        raise TypeError('validate_analysis_plan需要AnalysisPlan')
    # 限制逐来源保留，不以dataset.domain冒充观测范围。
    errors, warnings = _static_errors(plan) + _extension_backend_errors(plan), []
    # 仅实际会创建受管读取进程的来源检查当前Linux能力；普通串行不需该接口。
    from .process_execution import source_execution_facts
    from ..process_capabilities import managed_worker_warnings
    if not errors:
        warnings.extend(managed_worker_warnings(
            any(item['read_process_limit'] > 0 for item in source_execution_facts(plan)), '本分析计划'))
    # 明示待查周期，静态报告不能把None误解为无限保持或完成了DBC核实。
    pending_validity = tuple(item.definition.name for item in plan.signals
                             if item.definition.valid_for_ns is None)
    if pending_validity:
        warnings.append('这些信号的valid_for将在运行时取DBC周期的3倍：'
                        + ', '.join(pending_validity) + '；DBC缺少周期时须填写period或valid_for。')
    requirements = None
    if not errors:
        try:
            requirements = collect_input_requirements(plan)
        except (TypeError, ValueError) as error:
            errors += ('输入需求无法确定：' + str(error),)
    # 状态来自当前实际接线，没有导入旧reader。
    capabilities = {'configuration_static': 'implemented', 'memory': 'implemented', 'signal_csv': 'implemented',
                    'can_blf': 'implemented', PROFILE_ID: 'implemented', 'can_asc': 'implemented','asc_or_blf':'implemented','raw_can_csv':'implemented',
                    'runner': 'implemented', 'bounded_result_publish': 'implemented',
                    'legacy_profiles': 'partial' if any(item.source_type == 'can_blf' for item in plan.sources) else 'unavailable',
                    'preset_expansion': 'implemented', 'legacy_sum': 'unavailable',
                    'time_calculations': 'implemented', 'selection_rows': 'implemented',
                    'window_segments': 'implemented', 'start_only': 'implemented'}
    if plan.sequences:
        capabilities['sequence_timeout'] = 'implemented' if not errors else 'unavailable'
        warnings.append('sequence按点事件FIFO配对；延迟包含两端。只有完整响应观测才能判未响应；缺数据或提前EOF为indeterminate。')
    if any(rule.stability is not None for rule in plan.rules):
        capabilities['stability'] = 'implemented' if not errors else 'unavailable'
        warnings.append('迟滞/防抖输出转换确认后的活动；中间区间保留前态，无前序证据为UNKNOWN，进出条件重叠时报错。连续文件/批次不重置；当前不能直接作为sequence输入。')
    if any(preset.preset_type == 'threshold_excursion' for preset in plan.presets):
        capabilities['threshold_excursion'] = 'implemented' if not errors else 'unavailable'
        warnings.append('threshold_excursion：高阈值进入、低阈值退出，均含等号；逐段duration输出秒，'
            'run.threshold_durations保存同次已知报警累计及未知时长；有未知时完整总数为null，'
            '无观测为no_observation。自定义单位仅核显式同名无转换，保留unverified状态。')
    if any(rule.start_end is not None for rule in plan.rules):
        capabilities['start_end'] = 'implemented' if not errors else 'unavailable'
        warnings.append('start_end从开始条件的新上升沿记录到结束条件或时限；首次启动可配置。timeout表示可判断结束条件下超时，缺数据保留interrupted/truncated；活动中不排队重复开始，文件/批次不重置。')
    if any(rule.rule_type == 'window_delta' for rule in plan.rules):
        capabilities['window_delta'] = 'implemented' if not errors else 'unavailable'
        warnings.append('window_delta按完整有限ZOH窗口判断；不足或缺口为UNKNOWN。输出为rising点事件，窗口参数保留在原计划；当前不能作为sequence输入。')
    if plan.message_calculations:
        # 只在显式请求新模式时增加能力事实；旧空计划报告不因新模型出现而改变。
        available = type(plan.message_calculations) is tuple
        if available:
            for calculation in plan.message_calculations:
                try:
                    require_message_calculation(calculation, plan.sources, plan.bindings)
                except (TypeError, ValueError):
                    available = False
        capabilities.update(legacy_sum='partial',
            legacy_sum_current_message='implemented' if available else 'unavailable',
            legacy_sum_profile_compat='unavailable')
        scope_text = '按原请求[start,end)逐条匹配' if plan.dataset.domain_explicit else '整文件逐条匹配，不施时间筛选'
        warnings.append('legacy_sum：仅显式current_message-v1、session范围，' + scope_text + '；'
            '本条缺值记无效并跳过，不沿用上一条值、不施普通TTL、不再乘真实dt')
        warnings.append('legacy_sum：profile仅原解码路径；原legacy_evaluation_output=false不变，'
            '旧ChrgInfo完整触发/缓存兼容未接线，静态通过不证明同次CAN捕获或结果已经验证')
        warnings.append('legacy_sum：原始贡献不舍入，摘要仅最终round(raw_sum,6)；无求值/全skip为None，'
            '不填连续时间覆盖率；history_ns只解释普通分析的保持需求')
        if type(plan.message_calculations) is tuple and any(
                type(item) is MessageCalculationPlan and item.disjunction is not None for item in plan.message_calculations):
            capabilities['legacy_sum_disjunction'] = 'implemented' if available else 'unavailable'
            warnings.append('disjunction：按本条原解码字段正负路由原贡献，不取绝对值、不施额外scale/offset；'
                '零和另一桶跳过，缺方向及非有限方向保原因；静态声明不证明实际桶结果')
    # CSV表头/实际范围尚未打开，memory空也无观测证明。
    for source in plan.sources:
        # 所有来源实际观测范围须由运行进度另证明。
        if plan.dataset.domain_explicit:
            warnings.append(f'{source.name}：请求domain不证明实际观测范围')
        else:
            warnings.append(f'{source.name}：未声明时间筛选；domain=None不表示空文件或无观测数据')
        # file source尚未核实列/文件，metadata声明不等于verified。
        if source.source_type == 'signal_csv':
            # 无额外reader/DBC加载兑现静态字段验证。
            warnings.append(f'{source.name}：文件存在性与实际表头尚未读取，metadata_status=declared')
        elif source.source_type == 'can_blf':
            # 静态声明不能证明实际DBC字段/单位；进程行为由当前来源调度单独报告。
            warnings.append(f'{source.name}：实际输入及DBC字段、单位将在读取时核对，metadata_status=declared')
            warnings.append(f'{source.name}：匹配报文缺少所需信号时记为无效，其他报文不更新该信号；解码策略按本来源配置执行')
            warnings.append(f'{source.name}：内存预算记录本层估算费用，不代表读取库或工作进程的RSS上限')
            if isinstance(source.config, LegacyCANSpec) and source.config.decode_scope == 'requested':
                warnings.append(f'{source.name}：只解码本次结果实际需要的信号和逐消息选择器对应报文；'
                    '所有报文仍按原顺序读取，其他报文不调用DBC解码；时间按实际消费者处理。')
            elif isinstance(source.config, LegacyCANSpec) and source.config.decode_scope == 'all':
                warnings.append(f'{source.name}：显式all解码全部报文，并为本来源全部声明生成普通样本、'
                    '核对实际字段和单位；history_ns仍只列结果需要的TTL/pre，不表示这些诊断样本已裁剪。')
        elif source.source_type == 'memory' and isinstance(source.config, SourceSpec) and not source.config.rows:
            # 空memory也不伪造字段/覆盖。
            warnings.append(f'{source.name}：空memory，无实际字段或观测证明')
    # 未注册单位标签保留unverified事实。
    for signal in plan.signals:
        # 普通分析允许未知单位标签，但不能称已核实转换。
        if signal.definition.unit_status != 'verified':
            # 预设角色契约后续需要额外严格检查。
            warnings.append(f'{signal.definition.name}：单位关系unverified')
    if requirements is not None:
        # 完整声明仍通过静态检查；这里不把声明、消息字段和实际普通样本混为一谈。
        used = set(requirements.required_aliases)
        diagnostic_sources = {source.name for source in plan.sources
            if source.source_type == 'can_blf' and isinstance(source.config, LegacyCANSpec)
            and source.config.decode_scope == 'all'}
        diagnostic_aliases = {item.definition.name for item in plan.signals
            if item.definition.source in diagnostic_sources}
        unused = tuple(item.definition.name for item in plan.signals
            if item.definition.name not in used and item.definition.name not in diagnostic_aliases)
        message_only = tuple(name for name in requirements.message_aliases
            if name not in requirements.ordinary_sample_aliases and name not in diagnostic_aliases)
        warnings.append('信号声明与实际输入需求分开；结果仅在普通分析依赖上需要时序样本，'
            '逐消息依赖按当前消息求值；本报告尚未核验任何运行时值。')
        if unused:
            warnings.append('未被结果引用的信号仅保留静态声明检查，不请求其运行时值：' + '、'.join(unused))
        if message_only:
            warnings.append('仅供逐消息计算，不生成普通样本或TTL历史：' + '、'.join(message_only))
        for source_requirement in requirements.sources:
            warnings.append(f'{source_requirement.source}：input_check={source_requirement.input_check}，'
                f'time_scope={source_requirement.time_scope}；' + ' '.join(source_requirement.reasons))
            if source_requirement.time_scope == 'none':
                warnings.append(f'{source_requirement.source}：未采集报文时间，不生成全文件观测时间范围或全部时间校验摘要。')
            elif source_requirement.time_scope == 'selected':
                warnings.append(f'{source_requirement.source}：仅所需记录参与时间筛选，目标记录范围不能冒充全文件观测范围。')
            else:
                warnings.append(f'{source_requirement.source}：保留全来源时间观测；没有信号依赖不代表可以跳过来源。')
    if plan.message_calculations:
        warnings.append('逐消息计算使用当前记录流；贡献明细仅在outputs.contributions=full时生成。')
    # ready只说明代码路径可用；真实输入、实际预算及发布成功仍由运行与write分别验证。
    warnings.append('公共AnalysisRunner及有限结果暂存/Windows发布已接线；静态可执行不证明输入已读取或实际RAM峰值满足预算')
    # 所有输出容器只读，调用者不能改能力状态。
    capabilities['interval_execution'] = 'implemented'
    capabilities['demand_lifecycle'] = 'implemented'
    warnings.append('当前配置默认不生成贡献、追溯或完整性摘要；间隔与按需执行已接线，实际输入及结果仍须运行验证。')
    return ValidationReport(not errors, errors, tuple(warnings), MappingProxyType(capabilities), not errors)


def explain_analysis_plan(plan: AnalysisPlan) -> ExplainReport:
    """列出计划依赖、各节点计算方式、历史需求和预算声明。

    参数:
        plan (AnalysisPlan): 已通过静态构建的不可变计划。
    返回:
        ExplainReport。包括同一校验限制、依赖节点、history_ns和budget只读映射。
        已有数值内核与尚未接入节点分别标记，不能将整份计划当作全数组执行。
    异常:
        TypeError: 输入不是AnalysisPlan。
    处理流程:
        展开派生、规则、窗口和指标依赖；事件或片段范围的条件也参与依赖收集。
        原信号有效期与所需窗口pre取较大时长，只报告需求，不修改输入读取范围。
    副作用:
        不运行分析、不读取数据，也不测量内存峰值。
    """
    # 与validate使用同一能力判断，避免两个入口不一致。
    validation = validate_analysis_plan(plan)
    requirements = collect_input_requirements(plan) if validation.valid else None
    # 节点依赖由实际白名单编译结果提供；有效view仅覆盖backend，不重建声明身份。
    nodes = []
    backend_selection = select_backend(plan)
    backend = backend_selection.selected
    for transform in plan.transforms:
        nodes.append(ExplainNode(transform.name,'transform:'+transform.operation,transform.expression.dependencies,
                                 transform.output.unit,backend))
    # 派生声明选择数值实现；实际执行可用生产逐点或批量数组核，此处不运行数据。
    for item, expression in zip(plan.derived, plan.derived_expressions):
        # 不把semantic名称当原依赖。
        nodes.append(ExplainNode(item.definition.name, 'derived', expression.dependencies, expression.root.unit, backend))
    for aggregation in plan.aggregations:
        nodes.append(ExplainNode(aggregation.name,'aggregation:'+aggregation.operation,
                                 (aggregation.source_id,),aggregation.unit,'state_driver'))
    # 活动/边沿生命周期允许状态驱动，不伪称数组ufunc。
    for rule in plan.rules:
        # 已接线规则保持state_driver，未知typed kind不能被名称占位冒充真实检测器。
        nodes.append(ExplainNode(rule.rule_id, 'rule:' + rule.rule_type, rule.dependencies, None,
            'state_driver' if rule.rule_type in _RULES else 'unavailable'))
    if type(plan.sequences) is tuple:
        for sequence in plan.sequences:
            try:
                dependencies = sequence_dependencies(sequence, plan.rules, plan.bindings)
            except (TypeError, ValueError):
                dependencies = ()
            nodes.append(ExplainNode(getattr(sequence, 'sequence_id', 'sequences'), 'sequence:timeout',
                dependencies, 'ns', 'state_driver' if validation.valid else 'unavailable'))
    # 窗口引用的实际规则依赖明确。
    rules = {item.rule_id: item for item in plan.rules}
    # 两个独立窗口扩展/合并/裁剪算法已有入口，原始导出能力另行报告。
    for window in plan.windows:
        # 原规则与窗口依赖明确保留。
        rule = rules.get(window.event)
        available = _window_available(window, rules)
        nodes.append(ExplainNode(window.window_id, 'window:' + window.merge,
            () if rule is None else rule.dependencies, None, backend if available else 'unavailable'))
    # segment范围必须定位产生窗口的原规则。
    windows = {item.window_id: item for item in plan.windows}
    # 结果统计范围的联合依赖已由解析器检查。
    for calculation in plan.calculations:
        # 值/条件依赖在报告中保留，不包含其他无关来源。
        used = {name for expression in (calculation.signal, calculation.condition) if expression is not None for name in expression.dependencies}
        # event/segment范围条件也是指标的真实依赖。
        available = (calculation.operation in _CALCULATIONS + (COUNT_OPERATIONS + MOMENTS + SAMPLE_QUANTILES)
                     or plan.extensions is not None and calculation.operation in plan.extensions.reductions) and calculation.method == ('zoh' if calculation.operation == 'integral' else None)
        if calculation.operation in OBJECT_COUNTS:
            target = calculation.count_target
            window = windows.get(target) if calculation.operation == 'segment_count' else None
            rule = rules.get(window.event if window is not None else target)
            if rule is not None:
                used.update(rule.dependencies)
        if calculation.scope != 'session':
            # 正常配置已验证；typed负例仍报告unavailable及errors，不以缺引用触发KeyError。
            scope, _, target = calculation.scope.partition(':') if type(calculation.scope) is str else ('', '', '')
            # segment间接关联原活动/点事件条件。
            window = windows.get(target) if scope == 'segment' else None
            event = target if scope == 'event' else None if window is None else window.event
            # 不遗漏仅用于定义统计范围的来源。
            rule = rules.get(event)
            if rule is None:
                available = False
            else:
                used.update(rule.dependencies)
                if rule.rule_type not in _RULES or window is not None and not _window_available(window, rules):
                    available = False
        # 排序只用于规范报告，不改变来源调用顺序。
        dependencies = tuple(sorted(used))
        # 数值节点采用有效backend；范围或算子不支持时明确保留unavailable。
        nodes.append(ExplainNode(calculation.calculation_id, 'calculation:' + calculation.operation, dependencies, calculation.unit,
            backend if available else 'unavailable'))
    if type(plan.message_calculations) is tuple:
        for calculation in plan.message_calculations:
            if type(calculation) is not MessageCalculationPlan:
                continue
            try:
                require_message_calculation(calculation, plan.sources, plan.bindings)
                available = True
            except (TypeError, ValueError):
                available = False
            # 参数不伪装成来源列；状态/累计为有序驱动，表达式使用本次真实后端。
            dependencies = calculation.expr.dependencies
            if calculation.disjunction is not None:
                dependencies = tuple(sorted(set((*dependencies, calculation.disjunction.signal))))
            nodes.append(ExplainNode(calculation.calculation_id, 'message_calculation:legacy_sum',
                dependencies, calculation.unit, backend if available else 'unavailable'))
    # 普通样本才有TTL/pre历史；逐消息字段与未引用声明不产生此项需求。
    for name,expected in (('signal_csv',SignalCSVOutput),('can_frames',CANFramesOutput)):
        option=getattr(plan.outputs,name)
        if type(option) is expected:
            dependencies=option.spec.signals if name=='signal_csv' else (option.source,)
            if option.window is not None:
                dependencies=(*dependencies,option.window)
            nodes.append(ExplainNode('outputs.'+name,'output:'+name,dependencies,None,
                backend if validation.execution_ready else 'unavailable'))
    ordinary = () if requirements is None else requirements.ordinary_sample_aliases
    history = {item.definition.name: item.definition.valid_for_ns for item in plan.signals
               if item.definition.name in ordinary}
    if requirements is not None and requirements.transform_names:
        # 级联实际窗口的前史相加；固定周期的实际跨度需读到相邻原帧才确定。
        choices=dict(plan.intervals.resolved)
        horizons={}
        for t in plan.transforms:
            if t.name not in requirements.transform_names:
                continue
            own=t.max_gap_ns if t.max_gap_ns is not None else t.window_ns
            inherited=[horizons[n] for n in t.expression.dependencies if n in horizons]
            unknown=any(v is None for v in inherited) or (t.window_ns is not None and choices[t.name].mode!='actual')
            horizon=None if unknown else own+max(inherited,default=0)
            horizons[t.name]=horizon
            for n in t.physical:
                if n in history:
                    history[n]=None if history[n] is None or horizon is None else max(history[n],horizon)
    # 回看窗口也是必要历史，不能只报告TTL而漏掉新条件保留的片段。
    for rule in plan.rules:
        if rule.rule_type == 'window_delta':
            for name in rule.dependencies:
                if name in history and history[name] is not None:
                    history[name] = max(history[name], rule.window_delta.window_ns)
    # pre上下文可能需要原依赖更多历史，仅声明需求，不影响旧读范围。
    for window in plan.windows:
        rule = rules.get(window.event)
        if rule is None:
            continue
        # 同一原依赖保留更大必要上下文。
        for name in rule.dependencies:
            # typed非法计划没有可执行需求，不靠缺失依赖制造历史证明。
            if name in history and history[name] is not None:
                history[name] = max(history[name], window.pre_ns)
    # 片段内指标值/选择条件也可能需要pre历史。
    for calculation in plan.calculations:
        # 仅segment请求会把窗口pre应用于该指标。
        if type(calculation.scope) is str and calculation.scope.startswith('segment:'):
            # 引用已由严格解析器验证。
            window = windows.get(calculation.scope.partition(':')[2])
            if window is None:
                continue
            # 值及选择条件都保留必要历史声明。
            for expression in (calculation.signal, calculation.condition):
                # 未配置选择不制造依赖。
                if expression is not None:
                    # 原依赖的有效期与前置上下文pre取较大时长，声明必要历史范围。
                    for name in expression.dependencies:
                        # 不宣称整任务峰值内存或读取下推。
                        if name in history and history[name] is not None:
                            history[name] = max(history[name], window.pre_ns)
    # 原样报告配置限额，不能假称其已执行。
    budget = {'memory_budget_bytes': plan.execution.memory_budget_bytes, 'batch_rows': plan.execution.batch_rows,
              'result_buffer_rows': plan.execution.result_buffer_rows, 'spool_quota_bytes': plan.execution.spool_quota_bytes,
              'process_count': plan.execution.process_count}
    # 冻结所有结果容器以保留当前计划身份。
    from .process_execution import source_execution_facts
    return ExplainReport(validation, plan.identity, tuple(item.name for item in plan.sources),
        tuple(nodes), MappingProxyType(history), MappingProxyType(budget), requirements,
        plan.intervals if type(plan.intervals) is IntervalPlan else None,
        plan.diagnostics if type(plan.diagnostics) is DiagnosticPlan else None,
        tuple(MappingProxyType(item) for item in source_execution_facts(plan)),
        backend_selection.requested, backend_selection.selected, backend_selection.reason)
