"""检查计算条件、窗口和指标配置，保存静态依赖与边界声明。

输入是节点配置及当前信号绑定，输出RulePlan、WindowPlan和CalculationPlan。
表达式只允许受控语法，条件结果必须为布尔类型；窗口区分持续活动与时间点，
指标区分全会话、原事件和合并片段范围。检查引用、类型、单位及同步声明后，
节点按用户顺序保存。本模块不读来源或DBC，不运行时序规则或积分；
可配置的节点不等于运行接入完成，实际能力由计划报告说明。
"""

# 类型与静态单位校验均来自已验核心，不运行样本数值。
from ..core.expression import validate_expression
from ..core.calculations import CalculationDefinition, calculation_conversion
from ..core.models import Interval
from ..core.types import SignalDType as D
from ..core.unit_registry import resolve_unit
from ..core.window_delta import WindowDeltaSpec
from ..core.counts_v4 import COUNT_OPERATIONS, OBJECT_COUNTS
from ..core.moments import MOMENTS, WITH_DDOF, moment_ddof
from ..core.quantiles import SAMPLE_QUANTILES, quantile_probability
from ..core.stability import StabilitySpec
from ..core.start_end import StartEndSpec
# 严格JSON字段与可定位异常。
from .diagnostic_collection import usable_node, collect_node_error
from .checks import PlanValidationError, array_at, choice_at, duration_at, model_at, number_at, object_at, text_at
from .models import CalculationPlan, RulePlan, WindowPlan


def expression_at(text, path, bindings, derived, *, boolean=False, unit=None):
    """检查表达式声明，并将语法、类型或时钟错误关联到配置位置。

    参数:
        text (str): 使用已绑定简单别名的表达式文本。
        path (str): 表达式对应的配置位置。
        bindings (DeclarationBindings): 当前会话的名称、来源和时间声明关系。
        derived (tuple): 全部派生定义，供依赖展开和循环检查。
        boolean (bool): 默认False；True时要求结果为布尔类型。
        unit (str | None): 可选输出单位，默认None，按表达式推导。
    返回:
        StaticExpression。保留类型、单位和依赖，尚未读取数据或执行计算。
    异常:
        PlanValidationError: 受控语法、名称、依赖、类型、单位或同步声明不合法。
    """
    from .diagnostic_collection import require_expression_dependencies, expression_scope
    require_expression_dependencies(text, path, derived)
    bindings, derived = expression_scope(text, bindings, derived)
    # 所有静态配置表达式走同一严格白名单。
    result = model_at(validate_expression, path, text, bindings, derived=derived, unit=unit)
    # 不借数值truthiness生成条件。
    if boolean and result.root.dtype is not D.BOOL:
        # 编译完成也必须符合所在节点角色。
        raise PlanValidationError(path, 'condition必须为bool表达式')
    # 调用者可保存依赖/单位/静态身份。
    return result


def register_id(raw, path, ids) -> str:
    """将一个合法节点ID登记到本计划的名称集合。

    参数:
        raw (str): 用户声明的节点ID。
        path (str): ID对应的配置位置。
        ids (set[str]): 当前计划局部集合，供规则、窗口和指标共用。
    返回:
        str。原ID保持不变，并加入ids。
    异常:
        PlanValidationError: ID非法或已经存在，不自动改名或覆盖。
    副作用:
        只修改传入的局部集合，不注册全局名称。
    """
    # ID也禁止关键字/函数名称。
    name = text_at(raw, path, identifier=True)
    # 不同节点类型也不能悄悄使用同一稳定计划ID。
    if name in ids:
        # 第二定义位置准确报告。
        raise PlanValidationError(path, f'计划ID重复：{name}')
    # 只更新解析器局部集合，不用全局注册表。
    ids.add(name)
    # 不自动添加后缀。
    return name


def parse_rules(value, bindings, derived, ids) -> tuple[RulePlan, ...]:
    """检查普通布尔规则或数值窗口规则，保存参数与静态依赖。

    参数:
        value (list): 规则配置数组。
        bindings (DeclarationBindings): 当前来源和名称声明关系。
        derived (tuple): 完整派生定义。
        ids (set[str]): 本计划节点ID集合，成功登记的规则ID加入其中。
    返回:
        tuple[RulePlan, ...]。保持规则顺序，参数按kind互斥；不产生事件或活动状态。
    异常:
        PlanValidationError: 字段、ID、kind、条件类型、初始触发或持续参数错误。
    """
    # 不排序规则，结果保持声明次序。
    result = []
    # 每种kind只接受自己的字段，不以大并集容忍无效参数。
    for index, raw in enumerate(array_at(value, '$.rules')):
        # 精确数组项路径。
        path = f'$.rules[{index}]'
        if not usable_node(path, raw):
            continue
        try:
            path = f'$.rules[{index}]'
            # 基本对象先检查，防止任意对象方法调用。
            if type(raw) is not dict:
                # 不将字符串规则当自由DSL。
                raise PlanValidationError(path, 'rule必须为对象')
            # 仅接受下列支持的规则类型，未知类型在加载配置时拒绝。
            rule_type = choice_at(raw.get('rule_type'), ('condition_duration', 'rising_edge', 'falling_edge', 'start_only', 'window_delta', 'debounce', 'hysteresis', 'start_end'), path + '.rule_type')
            if rule_type == 'start_end':
                raw = object_at(raw, path, ('name', 'rule_type', 'start_condition', 'end_condition'), ('timeout', 'emit_initial'))
                rule_id = register_id(raw['name'], path + '.name', ids)
                condition = expression_at(raw['start_condition'], path + '.start_condition', bindings, derived, boolean=True)
                end_condition = expression_at(raw['end_condition'], path + '.end_condition', bindings, derived, boolean=True)
                model_at(bindings.require_synchronized, path, tuple(sorted(set(condition.dependencies + end_condition.dependencies))))
                timeout = raw.get('timeout')
                timeout_ns = None if timeout is None else duration_at(timeout, path + '.timeout', positive=True)
                spec = StartEndSpec(timeout_ns, choice_at(raw.get('emit_initial', True), (False, True), path + '.emit_initial'))
                result.append(model_at(RulePlan, path, rule_id, rule_type, condition, None, None, False, None,
                                       exit_condition=end_condition, start_end=spec))
                continue
            if rule_type in ('debounce', 'hysteresis'):
                # 迟滞用明确的两个BOOL条件；普通防抖只需要一个条件和相反方向。
                required = ('name', 'rule_type', 'condition') if rule_type == 'debounce' else ('name', 'rule_type', 'enter_condition', 'exit_condition')
                raw = object_at(raw, path, required, ('enter_delay', 'exit_delay'))
                rule_id = register_id(raw['name'], path + '.name', ids)
                field = 'condition' if rule_type == 'debounce' else 'enter_condition'
                condition = expression_at(raw[field], path + '.' + field, bindings, derived, boolean=True)
                exit_condition = (expression_at(raw['exit_condition'], path + '.exit_condition', bindings, derived, boolean=True)
                                  if rule_type == 'hysteresis' else None)
                dependencies = condition.dependencies + (() if exit_condition is None else exit_condition.dependencies)
                # 两条件即使分别合法，联合判断仍须证明时钟可比较。
                model_at(bindings.require_synchronized, path, tuple(sorted(set(dependencies))))
                spec = StabilitySpec(duration_at(raw.get('enter_delay', '0s'), path + '.enter_delay'),
                                     duration_at(raw.get('exit_delay', '0s'), path + '.exit_delay'))
                result.append(model_at(RulePlan, path, rule_id, rule_type, condition, None, None, False, None,
                                       stability=spec, exit_condition=exit_condition))
                continue
            if rule_type == 'window_delta':
                # 数值窗口先生成条件，重触发另由边沿检测承担；不向DSL加入有状态函数。
                raw = object_at(raw, path, ('name', 'rule_type', 'signal', 'window', 'direction', 'threshold'),
                                ('monotonic', 'coverage_policy', 'emit_initial', 'retrigger'))
                rule_id = register_id(raw['name'], path + '.name', ids)
                signal = expression_at(raw['signal'], path + '.signal', bindings, derived)
                spec = model_at(WindowDeltaSpec, path,
                    duration_at(raw['window'], path + '.window', positive=True),
                    number_at(raw['threshold'], path + '.threshold'),
                    choice_at(raw['direction'], ('rise', 'fall', 'any'), path + '.direction'),
                    choice_at(raw.get('monotonic', False), (False, True), path + '.monotonic'),
                    choice_at(raw.get('coverage_policy', 'full'), ('full',), path + '.coverage_policy'))
                emit = choice_at(raw.get('emit_initial', False), (False, True), path + '.emit_initial')
                retrigger = choice_at(raw.get('retrigger', 'edge'), ('edge', 'once'), path + '.retrigger')
                result.append(model_at(RulePlan, path, rule_id, rule_type, signal, None, None, emit, None, spec, retrigger))
                continue
            # condition_duration与start_only有不同必须持续参数。
            required = ('name', 'rule_type', 'condition') + (('minimum_duration',) if rule_type == 'condition_duration' else ('window_duration',) if rule_type == 'start_only' else ())
            # condition_duration不接emit_initial，避免错误活动政策。
            raw = object_at(raw, path, required, ('selection_origin', 'duration_comparison') if rule_type == 'condition_duration' else ('emit_initial',))
            # ID和DSL都静态校验，不读取来源。
            rule_id = register_id(raw['name'], path + '.name', ids)
            # 条件必须为bool，并检查依赖来源是否声明共同时间基准；这不核实真实时钟误差。
            condition = expression_at(raw['condition'], path + '.condition', bindings, derived, boolean=True)
            # 仅condition_duration使用选择起点。
            selection = choice_at(raw.get('selection_origin', 'onset'), ('onset', 'confirmed'), path + '.selection_origin') if rule_type == 'condition_duration' else None
            # 开关严格bool，不能把文本false当True。
            emit = choice_at(raw.get('emit_initial', False), (False, True), path + '.emit_initial')
            # falling_edge不支持初始已知TRUE触发。
            if rule_type == 'falling_edge' and emit:
                # 不偷换首次状态的下降沿含义。
                raise PlanValidationError(path + '.emit_initial', 'falling不接受emit_initial=true')
            # condition_duration允许0，固定窗口必须正数。
            duration = duration_at(raw['minimum_duration'], path + '.minimum_duration') if rule_type == 'condition_duration' else None
            # 固定抑制不能以0长度循环重触发。
            fixed = duration_at(raw['window_duration'], path + '.window_duration', positive=True) if rule_type == 'start_only' else None
            # 保存声明，不在解析器内创建时序活动状态。
            comparison = choice_at(raw.get('duration_comparison', '>='), ('>=', '>'), path + '.duration_comparison')
            result.append(RulePlan(rule_id, rule_type, condition, duration, selection, emit, fixed,
                                   duration_comparison=comparison))
        except PlanValidationError as error:
            collect_node_error(error, path, raw)
    # 不保留用户可变数组。
    return tuple(result)


def parse_windows(value, rules, ids) -> tuple[WindowPlan, ...]:
    """检查事件窗口锚点、前后扩展和合并参数，不改变原事件声明。

    参数:
        value (list): 窗口配置数组。
        rules (tuple[RulePlan, ...]): 可引用的已检查规则。
        ids (set[str]): 当前计划节点ID集合。
    返回:
        tuple[WindowPlan, ...]。持续规则只能使用activity锚点，其余使用point。
        exit_delay要求activity且post为0，start_only的post须等于固定窗口时长。
    异常:
        PlanValidationError: 引用、ID、锚点、扩展时间或合并参数冲突。
    副作用:
        登记窗口ID，但不运行合并或生成片段。
    """
    # 引用只允许当前计划规则。
    catalog = {item.rule_id: item for item in rules}
    # 结果保持声明顺序。
    result = []
    # 每项范围和合并约束都先于执行。
    for index, raw in enumerate(array_at(value, '$.windows')):
        # 错误关联具体窗口。
        path = f'$.windows[{index}]'
        if not usable_node(path, raw):
            continue
        try:
            path = f'$.windows[{index}]'
            # 没有自由metadata或未定义延迟参数。
            raw = object_at(raw, path, ('name', 'rule'), ('anchor', 'pre', 'post', 'merge', 'exit_delay'))
            # 窗口ID不能与其他节点冲突。
            window_id = register_id(raw['name'], path + '.name', ids)
            # 事件关联不是Python属性语法。
            event = text_at(raw['rule'], path + '.rule', identifier=True)
            # 未知规则不能通过空窗口回退。
            if event not in catalog:
                # 不自动生成新规则或选择首个事件。
                raise PlanValidationError(path + '.rule', f'未知规则：{event}','invalid_reference',
                    hint='填写rules中已声明的name：'+', '.join(catalog))
            # 活动锚点和真实point严格区分。
            # condition_duration及迟滞/防抖输出活动；窗口变化与普通边沿输出点。
            expected = 'activity' if catalog[event].temporal_rule_type == 'condition_duration' else 'point'
            # 事件已唯一决定锚点，只有显式填写时才需要核对一致性。
            anchor = choice_at(raw.get('anchor', expected), ('point', 'activity'), path + '.anchor')
            # 不能靠post窗口把point假称活动。
            if anchor != expected:
                # 保存事件本来语义。
                raise PlanValidationError(path + '.anchor', f'{catalog[event].rule_type}要求anchor={expected}')
            # pre/post不允许负数，包括量化前负小值。
            pre = duration_at(raw.get('pre', '0s'), path + '.pre')
            # 固定窗口抑制以post声明为准。
            # start_only的窗口继承规则时长，其他窗口未扩展的一侧为零。
            default_post = f'{catalog[event].window_duration_ns}ns' if catalog[event].rule_type == 'start_only' else '0s'
            post = duration_at(raw.get('post', default_post), path + '.post')
            # 合并政策只接受设计明确列出的种类。
            merge = choice_at(raw.get('merge', 'none'), ('none', 'overlap', 'overlap_and_adjacent', 'exit_delay'), path + '.merge')
            # exit_delay不能与其他merge模式一起隐藏。
            if (merge == 'exit_delay') != ('exit_delay' in raw):
                # 默认值不能使缺关键参数悄悄成功。
                raise PlanValidationError(path + '.exit_delay', 'exit_delay字段仅且必须用于同名merge模式')
            # exit_delay活动只扩合并上下文，不写回原事件统计区间。
            if merge == 'exit_delay' and (anchor != 'activity' or post != 0):
                # 不允许post再次扩大single分组。
                raise PlanValidationError(path + '.merge', 'exit_delay要求activity且post=0')
            # 关联start_only固定post不能改变抑制时长。
            if catalog[event].rule_type == 'start_only' and post != catalog[event].window_duration_ns:
                # 终点到期不自动重触发的运行政策由WINDOW验证。
                raise PlanValidationError(path + '.post', 'start_only关联post必须等于window_duration')
            # 延迟存在才解析，保留未使用None。
            delay = duration_at(raw['exit_delay'], path + '.exit_delay') if merge == 'exit_delay' else None
            # 不运行活动或合并事件，仅保存参数。
            result.append(WindowPlan(window_id, event, anchor, pre, post, merge, delay))
        except PlanValidationError as error:
            collect_node_error(error, path, raw)
    # 完整冻结声明顺序。
    return tuple(result)


def parse_calculations(value, bindings, derived, rules, windows, execution, ids) -> tuple[CalculationPlan, ...]:
    """检查指标统计范围、信号、条件、单位和覆盖政策。

    参数:
        value (list): 指标配置数组。
        bindings (DeclarationBindings): 当前名称及来源同步声明。
        derived (tuple): 完整派生定义，用于静态依赖展开。
        rules (tuple[RulePlan, ...]): 原事件范围可引用的规则。
        windows (tuple[WindowPlan, ...]): 片段范围可引用的窗口。
        execution (ExecutionPlan): 提供默认partial_policy。
        ids (set[str]): 当前计划节点ID集合。
    返回:
        tuple[CalculationPlan, ...]。保存全会话、原事件或片段范围，明确样本统计、
        时间统计和选择行等口径；只检查声明，不生成数值或结果行。
    异常:
        PlanValidationError: 算子、ID、引用、信号类型、条件、单位或覆盖政策错误。
    处理流程:
        范围条件、数值信号和选择条件的原始依赖一起检查同步声明。
        select保留原单位；积分仅接受左侧保持'zoh'；其他算子拒绝method字段。
    """
    # 当前计划范围引用不继承其他任务。
    rule_map, window_map = {item.rule_id: item for item in rules}, {item.window_id: item for item in windows}
    # 节点顺序与声明一致。
    result = []
    # 逐配置节点处理，不是逐样本数值计算。
    for index, raw in enumerate(array_at(value, '$.calculations')):
        # 数组错误位置明确。
        path = f'$.calculations[{index}]'
        if not usable_node(path, raw):
            continue
        try:
            path = f'$.calculations[{index}]'
            # 非integral的method字段稍后明确拒绝。
            version = getattr(bindings, 'config_version', 4)
            count_target = None
            is_object = isinstance(raw, dict) and raw.get('operation') in OBJECT_COUNTS
            if is_object:
                target_key = 'window' if raw['operation'] == 'segment_count' else 'rule'
                raw = object_at(raw, path, ('name', 'operation', target_key), ('scope', 'unit', 'partial_policy'))
                count_target = text_at(raw[target_key], path + '.' + target_key)
                targets = window_map if target_key == 'window' else rule_map
                if count_target not in targets:
                    raise PlanValidationError(path + '.' + target_key, '对象计数引用未声明的规则或窗口')
                if target_key == 'rule':
                    activity = rule_map[count_target].temporal_rule_type == 'condition_duration'
                    if activity != (raw['operation'] == 'activity_count'):
                        raise PlanValidationError(path + '.rule', '被计规则须产生相应的点事件或活动')
            else:
                optional = ('scope', 'expr', 'condition', 'unit', 'method', 'partial_policy', 'minimum_coverage')
                if isinstance(raw, dict) and raw.get('operation') in WITH_DDOF:
                    optional += ('ddof',)
                if isinstance(raw, dict) and raw.get('operation') == 'sample_quantile':
                    optional += ('q',)
                raw = object_at(raw, path, ('name', 'operation'), optional)
            # 所有节点ID唯一，不能覆盖窗口或规则。
            calculation_id = register_id(raw['name'], path + '.name', ids)
            # 模糊mean/min/max不进入执行计划。
            supported = ('select', 'sample_minimum', 'sample_maximum', 'sample_mean', 'min_time', 'max_time', 'time_weighted_mean', 'duration', 'integral')
            extensions = bindings.extensions.reductions if bindings.extensions is not None else {}
            operation = choice_at(raw['operation'], supported + (COUNT_OPERATIONS + MOMENTS + SAMPLE_QUANTILES) + tuple(extensions), path + '.operation')
            hosted=extensions.get(operation)
            q = raw.get('q')
            if operation in SAMPLE_QUANTILES:
                model_at(quantile_probability, path + '.q', operation, q)
            ddof = model_at(moment_ddof, path + '.ddof', operation,
                            number_at(raw['ddof'], path + '.ddof', integer=True) if 'ddof' in raw else None)
            # scope是配置前缀语法，不交给PythonDSL解析。
            scope = text_at(raw.get('scope', 'session'), path + '.scope')
            if is_object and scope != 'session':
                raise PlanValidationError(path + '.scope', '对象计数的首版范围为session')
            # 定义统计范围的条件依赖也加入来源同步声明检查。
            dependencies = set()
            # 全会话范围使用session，只有事件或片段范围需要引用ID。
            if scope != 'session':
                # 仅支持明确event/segment前缀和现有ID。
                prefix, separator, target = scope.partition(':')
                # 引用前缀和目标必须正确且唯一。
                if not separator or prefix not in ('event', 'segment') or target not in (rule_map if prefix == 'event' else window_map):
                    # 不自动选首个事件/片段。
                    raise PlanValidationError(path + '.scope', 'scope须为session或已定义的{rule: 名称}/{window: 名称}',
                        'invalid_reference',hint='核对统计范围；可用值：'+', '.join(
                            ['session']+['{rule: '+name+'}' for name in rule_map]+['{window: '+name+'}' for name in window_map]))
                # segment实际由窗口所关联规则产生。
                event = target if prefix == 'event' else window_map[target].event
                # 指标值与产生范围的条件也必须同步。
                dependencies.update(rule_map[event].dependencies)
            # 明确选择政策，不将低覆盖补成已知。
            partial = choice_at(raw.get('partial_policy', execution.partial_policy), ('report', 'strict'), path + '.partial_policy')
            # minimum_coverage只作质量门槛，保留原数值。
            coverage = number_at(raw.get('minimum_coverage', 0), path + '.minimum_coverage', minimum=0, maximum=1)
            # condition可选，但存在时必须BOOLDSL。
            condition = expression_at(raw['condition'], path + '.condition', bindings, derived, boolean=True) if 'condition' in raw else None
            # expr统一接收简单别名或白名单表达式；依赖和单位仍按现有编译器检查。
            name = text_at(raw['expr'], path + '.expr') if 'expr' in raw else None
            # 只编译受限表达式，不执行Python或属性访问。
            signal = expression_at(name, path + '.expr', bindings, derived,unit=hosted.input.unit if hosted else None) if name is not None else None
            if hosted and signal is not None and signal.root.dtype is not hosted.input.dtype:
                raise PlanValidationError(path+'.expr','宿主归约输入 dtype 与描述不符')
            # duration选择BOOL信号或明确条件，避免两个持续条件含义歧义。
            if is_object:
                unit = choice_at(raw.get('unit', '1'), ('1',), path + '.unit')
            elif operation == 'duration':
                # BOOL值不经过数值truthiness。
                if (signal is None) == (condition is None) or signal is not None and signal.root.dtype is not D.BOOL:
                    # 一项必要条件必须明确。
                    raise PlanValidationError(path, 'duration必须且只能提供BOOL expr或condition')
                # 设计首版持续结果统一秒。
                unit = choice_at(raw.get('unit', 's'), ('s',), path + '.unit')
            else:
                # select和数值统计都必须有实际列声明。
                if signal is None:
                    # 条件本身不能替代数值输入。
                    raise PlanValidationError(path + '.expr', '该指标必须提供expr')
                # select允许保留BOOL/ENUM行，其余数值口径明确排除。
                if operation != 'select' and signal.root.dtype not in (D.INT64, D.UINT64, D.FLOAT64):
                    # 不把业务标签或bool隐式数值化。
                    raise PlanValidationError(path + '.expr', '数值指标必须int64/uint64/float64')
                # 选择行流与标量使用同一完整转换描述符检查目标单位。
                version = getattr(bindings, 'config_version', 4)
                if operation in ('integral', 'sample_rms', 'time_rms'):
                    # 默认显示规范化不能绕过摄氏直接积分限制；显式to_unit(K)是用户已选尺度。
                    input_root = signal.root
                    while input_root.operator == 'unit_convert' and not input_root.unit_explicit:
                        input_root = input_root.args[0]
                    input_unit = model_at(resolve_unit, path + '.expr', input_root.unit)
                    if input_unit is not None and input_unit.offset:
                        raise PlanValidationError(path + '.expr', f'摄氏绝对温度{operation}请先显式to_unit(...,"K")')
                if hosted is not None:
                    # 已选真实样本的单位转换在输入表达式完成；归约输出可能属于不同量纲。
                    unit_spec = CalculationDefinition(calculation_id,'sample_minimum',Interval(0,0),
                        output_unit=raw.get('unit',hosted.output.unit),config_version=4)
                    output = model_at(calculation_conversion,path+'.unit',unit_spec,hosted.output.unit)
                    model_at(output.dtype,path+'.unit',hosted.output.dtype)
                    unit=output.unit
                else:
                    spec = model_at(CalculationDefinition, path, calculation_id, operation, Interval(0, 0),
                                    partial, raw.get('unit'), config_version=version, ddof=ddof, q=q)
                    conversion = model_at(calculation_conversion, path + '.unit', spec, signal.root.unit)
                    # 在开始读取前拒绝BOOL/ENUM换数值单位，目标值类型由系数静态决定。
                    if operation == 'select':
                        model_at(conversion.dtype, path + '.unit', signal.root.dtype)
                    unit = conversion.unit
            # method只允许积分zoh，不静默忽略其他算子字段。
            if 'method' in raw and operation != 'integral':
                # 模糊method可能改变业务统计含义。
                raise PlanValidationError(path + '.method', 'method仅用于integral')
            # 首版积分固定左侧保持，不开放未实现插值。
            method = choice_at(raw.get('method', 'zoh'), ('zoh',), path + '.method') if operation == 'integral' else None
            # 值与条件依赖都包含在当前节点同步证明中。
            for expression in (signal, condition):
                # 未配置条件不制造额外来源。
                if expression is not None:
                    # 使用已经展开的原信号依赖。
                    dependencies.update(expression.dependencies)
            # 条件和统计范围跨来源时，也须声明共同时间起点。
            model_at(bindings.require_synchronized, path, tuple(sorted(dependencies)))
            # 保存明确统计范围，窗口合并不能改变原事件指标的区间。
            result.append(CalculationPlan(calculation_id, scope, operation, signal, condition, unit, partial, coverage,
                                          method, count_target, ddof=ddof, q=q))
        except PlanValidationError as error:
            collect_node_error(error, path, raw)
    # 后续运行只读这些声明，不持有用户数组。
    return tuple(result)
