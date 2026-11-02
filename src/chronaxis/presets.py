"""校验领域预设v1的角色契约，展开为可序列化的类型化公共声明。

输入PresetSpec与当前SignalDefinition tuple，输出PlanFragment；不读取来源或执行分析。
先严格校验参数，再显式优先解析角色/检查转换后契约，最后生成简单别名表达式和节点。
候选语义名只属于本模块的版本化契约，不是通用核心领域目录或行业标准。
声明会交给AnalysisPlan正常编译；不使用eval、不推断方向/位置/阈值或补造真实数据。
输入/输出均不可变；JSON序列化返回独立副本。执行、资源预算和报文导出由执行层负责。
"""

# 算法与公开声明模型分开，避免AnalysisPlan/构建器循环。
from .core.binding import SignalDefinition
from .core.expression import DerivedDefinition
from .core.types import SignalDType as D
from .core.windows import WindowSpec
from .planning.checks import (PlanValidationError, choice_at, duration_at, json_value,
                              array_at, number_at, object_at, text_at)
from .planning.preset_models import (RoleContract, RoleBinding, PresetSpec, PresetRule,
                                    PresetCalculation, PlanFragment, CHARGE_ROLES, FAULT_ROLES, COMMAND_ROLES)
from .planning.sequences import SequencePlan
from .timebase.conversion import INT64_MIN, INT64_MAX


def _parameters(spec, signals=()):
    """按kind检查工程参数，保持原数值并将时长转换为整数ns。

    参数: spec为PresetSpec；参数值来自独立JSON快照。
    返回: 新dict，仅内部使用已校验参数，不作为公开无类型片段。
    异常: PlanValidationError为缺项、未知参数、bool伪数值、非有限或错误范围。
    """
    # 将不可变快照还原为局部原生对象，严格拒绝未声明参数。
    path = '$.preset.parameters'
    if spec.preset_type == 'charge_session':
        raw = object_at(json_value(spec.parameters), path, ('mode_value', 'current_min', 'minimum_duration'),
                        ('compute_energy', 'compute_charge', 'minimum_coverage', 'partial_policy'))
        result = {'mode_value': number_at(raw['mode_value'], path + '.mode_value', integer=True),
                  'current_min': number_at(raw['current_min'], path + '.current_min'),
                  'minimum_duration': duration_at(raw['minimum_duration'], path + '.minimum_duration'),
                  'compute_energy': choice_at(raw.get('compute_energy', False), (False, True), path + '.compute_energy'),
                  'compute_charge': choice_at(raw.get('compute_charge', False), (False, True), path + '.compute_charge'),
                  'minimum_coverage': number_at(raw.get('minimum_coverage', 0), path + '.minimum_coverage', minimum=0, maximum=1),
                  'partial_policy': choice_at(raw['partial_policy'], ('report', 'strict'), path + '.partial_policy') if 'partial_policy' in raw else None}
    elif spec.preset_type == 'fault_context':
        raw = object_at(json_value(spec.parameters), path, (), ('pre', 'post', 'emit_initial'))
        result = {'pre': duration_at(raw.get('pre', '0s'), path + '.pre'), 'post': duration_at(raw.get('post', '0s'), path + '.post'),
                  'emit_initial': choice_at(raw.get('emit_initial', False), (False, True), path + '.emit_initial')}
        if result['pre'] == result['post'] == 0:
            raise PlanValidationError(path, 'fault_context至少一个pre/post为正')
    elif spec.preset_type == 'threshold_excursion':
        # v1明确高阈值进入、低阈值退出；拒绝重叠，不能在阈值相等时猜优先级。
        raw = object_at(json_value(spec.parameters), path, ('enter_threshold', 'exit_threshold'),
                        ('unit', 'enter_delay', 'exit_delay'))
        if 'unit' in raw:
            unit = text_at(raw['unit'], path + '.unit')
        else:
            alias = spec.role_bindings.get('signal')
            candidates = [item for item in signals if item.name == alias]
            if len(candidates) != 1:
                raise PlanValidationError('$.preset.role_bindings.signal', '请指定唯一的已绑定信号以继承单位')
            unit = candidates[0].unit
        result = dict(unit=unit,
            enter_threshold=number_at(raw['enter_threshold'], path + '.enter_threshold'),
            exit_threshold=number_at(raw['exit_threshold'], path + '.exit_threshold'),
            enter_delay=duration_at(raw.get('enter_delay', '0ns'), path + '.enter_delay'),
            exit_delay=duration_at(raw.get('exit_delay', '0ns'), path + '.exit_delay'))
        if result['enter_threshold'] <= result['exit_threshold']:
            raise PlanValidationError(path, '进入阈值必须大于退出阈值；v1高于进入、低于退出，均含等号')
    else:
        raw = object_at(json_value(spec.parameters), path, ('max_delay',), ('min_delay', 'emit_initial', 'max_pending'))
        result = dict(min_delay=duration_at(raw.get('min_delay', '0s'), path + '.min_delay'),
            max_delay=duration_at(raw['max_delay'], path + '.max_delay'),
            emit_initial=choice_at(raw.get('emit_initial', False), (False, True), path + '.emit_initial'),
            max_pending=number_at(raw.get('max_pending', 65536), path + '.max_pending', integer=True, minimum=1))
        if result['min_delay'] > result['max_delay']:
            raise PlanValidationError(path, 'min_delay不能大于max_delay')
    return result


def _mismatches(definition, contract, *, generic_unit=False):
    """列出转换后声明未满足的角色字段，不能用自由metadata放宽质量。

    参数: definition为SignalDefinition；contract为本v1角色；generic_unit允许明确同名无转换的自定义单位。
    返回: tuple[str, ...]，空表示字段契约通过，不证明真实数据正确。
    异常: 无主动异常；输入类型由公共解析入口证明。
    """
    # 逐字段诊断方便缺项/歧义时列出候选不满足原因。
    errors = []
    if definition.dtype not in contract.dtypes:
        errors.append('dtype须为' + '/'.join(item.value for item in contract.dtypes))
    identity_unit = (generic_unit and definition.input_unit == definition.unit
                     and definition.scale == 1 and definition.offset == 0 and definition.direction_factor == 1)
    if definition.unit != contract.unit or definition.unit_status != 'verified' and not identity_unit:
        errors.append(f'目标unit须为{contract.unit}且关系verified')
    if contract.sign_convention is not None and definition.sign_convention != contract.sign_convention:
        errors.append('sign_convention须为' + contract.sign_convention)
    if contract.measurement_location is not None and definition.measurement_location != contract.measurement_location:
        errors.append('measurement_location须为' + contract.measurement_location)
    # DBC默认有效期在运行启动时核实；声明阶段不为角色校验额外加载DBC。
    if (definition.valid_for_ns is not None and definition.valid_for_ns <= 0
            or definition.sample_policy != 'backward_hold' or definition.identity()[-1] != contract.forbidden_quality):
        errors.append('正valid_for/backward_hold/固定基础质量策略未满足')
    return tuple(errors)


def resolve_preset_roles(spec: PresetSpec, signals: tuple[SignalDefinition, ...]) -> tuple[RoleBinding, ...]:
    """显式优先解析本次实际角色，否则按版本化语义契约寻找唯一合格候选。

    参数: spec为公开不可变预设；signals为当前计划SignalDefinition tuple。
    返回: RoleBinding tuple，保留原定义与explicit/semantic_unique路径。
    异常: PlanValidationError为类型、重复别名、未知角色、缺项、候选歧义或契约冲突。
    边界: 显式别名无需semantic_id，仍检查类型/单位/方向/位置/质量；不选第一个候选。
    """
    if not isinstance(spec, PresetSpec) or not isinstance(signals, tuple) or any(not isinstance(item, SignalDefinition) for item in signals):
        raise PlanValidationError('$.preset', '需要PresetSpec与SignalDefinition tuple')
    parameters = _parameters(spec, signals)
    if spec.preset_type == 'threshold_excursion':
        # 任意物理量显式绑定；未填单位则继承该信号，不猜温度等领域名称。
        if 'signal' not in spec.role_bindings:
            raise PlanValidationError('$.preset.role_bindings.signal', 'threshold_excursion必须显式指定signal角色')
        from .planning.preset_models import RoleContract
        contracts = (RoleContract('signal', (D.INT64, D.UINT64, D.FLOAT64), parameters['unit'], 'threshold.signal'),)
    else:
        contracts = {'charge_session': CHARGE_ROLES, 'fault_context': FAULT_ROLES,
                     'command_response': COMMAND_ROLES}[spec.preset_type]
    catalog = {item.name: item for item in signals}
    if len(catalog) != len(signals):
        raise PlanValidationError('$.signals', 'signal别名重复')
    unknown = set(spec.role_bindings) - {item.role for item in contracts}
    if unknown:
        raise PlanValidationError('$.preset.role_bindings', '未知角色：' + ', '.join(sorted(unknown)))
    result = []
    for contract in contracts:
        # voltage只在请求能量或明确提供该可选绑定时检查，不强迫无能量任务配置电压。
        if contract.role == 'voltage' and not parameters['compute_energy'] and contract.role not in spec.role_bindings:
            continue
        path = '$.preset.role_bindings.' + contract.role
        if contract.role in spec.role_bindings:
            alias = spec.role_bindings[contract.role]
            if alias not in catalog:
                raise PlanValidationError(path, f'未知别名：{alias}；可用：{", ".join(catalog)}')
            definition = catalog[alias]
            errors = _mismatches(definition, contract, generic_unit=spec.preset_type == 'threshold_excursion')
            if errors:
                raise PlanValidationError(path, f'{alias}契约不满足：{"; ".join(errors)}')
            result.append(RoleBinding(contract, definition, 'explicit'))
        else:
            # 只取本模块公开候选标识/版本，所有合格候选统计完才决定。
            candidates = [item for item in signals if item.semantic_id == contract.semantic_id]
            valid = [item for item in candidates if item.semantic_contract_version == contract.version and not _mismatches(item, contract)]
            if len(valid) != 1:
                details = '; '.join(item.name + ': ' + ', '.join(_mismatches(item, contract) +
                           (() if item.semantic_contract_version == contract.version else ('semantic_contract_version须为1',))) for item in candidates)
                reason = '歧义候选：' + ', '.join(item.name for item in valid) if valid else '缺少符合契约的候选'
                raise PlanValidationError(path, reason + f'（{contract.semantic_id} v1）；' + details)
            result.append(RoleBinding(contract, valid[0], 'semantic_unique'))
    return tuple(result)


def build_preset(spec: PresetSpec, signals: tuple[SignalDefinition, ...]) -> PlanFragment:
    """校验v1预设并展开公共声明，不执行I/O或数值分析。

    参数: spec为PresetSpec，保存id/preset_type/version/显式角色及参数；signals为当前类型化信号tuple。
    返回: PlanFragment，生成请求的功率/Wh/Ah、报警、阈值迟滞/逐段时长或响应配对。
    异常: PlanValidationError为参数/角色契约、模式编码范围及生成ID与信号冲突。
    流程: 检查角色→生成简单别名DSL→构造类型化节点→拒绝当前可见ID冲突。
        用户其他节点/多个预设的冲突由AnalysisPlan合入时继续检查。
    """
    resolved = resolve_preset_roles(spec, signals)
    roles = {item.contract.role: item.definition for item in resolved}
    parameters = _parameters(spec, signals)
    if spec.preset_type == 'charge_session':
        mode, current = roles['mode'], roles['current']
        minimum, maximum = (INT64_MIN, INT64_MAX) if mode.dtype is D.INT64 else (0, 2**64-1)
        code = parameters['mode_value']
        if not minimum <= code <= maximum or mode.valid_range is not None and not mode.valid_range[0] <= code <= mode.valid_range[1]:
            raise PlanValidationError('$.preset.parameters.mode_value', '模式编码超出已声明dtype/valid_range')
        # 只拼接已验证别名与原生有限数值字面量，不能注入属性或任意函数。
        condition = f'{mode.name} == {code!r} and {current.name} > {parameters["current_min"]!r}'
        rule = PresetRule(spec.id + '_activity', 'condition_duration', condition, parameters['minimum_duration'], 'onset')
        derived, calculations = [], []
        for requested, suffix, signal, unit in (
                (parameters['compute_energy'], 'energy', spec.id + '_power', 'Wh'),
                (parameters['compute_charge'], 'charge', current.name, 'Ah')):
            if requested:
                calculations.append(PresetCalculation(spec.id + '_' + suffix, 'event:' + rule.id, signal, unit,
                                           parameters['minimum_coverage'], parameters['partial_policy']))
        if parameters['compute_energy']:
            derived.append(DerivedDefinition(spec.id + '_power', roles['voltage'].name + ' * ' + current.name, 'W'))
        fragment = PlanFragment(tuple(derived), (rule,), (), tuple(calculations))
    elif spec.preset_type == 'fault_context':
        rule = PresetRule(spec.id + '_alarm', 'rising_edge', roles['alarm'].name, emit_initial=parameters['emit_initial'])
        window = WindowSpec(spec.id + '_context', rule.id, 'point', parameters['pre'], parameters['post'])
        fragment = PlanFragment((), (rule,), (window,), ())
    elif spec.preset_type == 'threshold_excursion':
        # 普通迟滞规则负责全部状态，逐段时长复用原duration核；总计由同一次状态推进保存。
        alias = roles['signal'].name
        rule = PresetRule(spec.id + '_activity', 'hysteresis', None,
            enter_condition=f'{alias} >= {parameters["enter_threshold"]!r}',
            exit_condition=f'{alias} <= {parameters["exit_threshold"]!r}',
            enter_delay_ns=parameters['enter_delay'], exit_delay_ns=parameters['exit_delay'])
        calculation = PresetCalculation(spec.id + '_duration', 'event:' + rule.id, None, 's',
                              operation='duration', condition='True')
        fragment = PlanFragment(rules=(rule,), calculations=(calculation,))
    else:
        # 布尔角色变为两条普通rising_edge规则，配对仍走公开SequencePlan，没有隐藏计算器。
        request = PresetRule(spec.id + '_request', 'rising_edge', roles['request'].name, emit_initial=parameters['emit_initial'])
        response = PresetRule(spec.id + '_response', 'rising_edge', roles['response'].name, emit_initial=parameters['emit_initial'])
        sequence = SequencePlan(spec.id + '_pair', request.id, response.id,
            parameters['min_delay'], parameters['max_delay'], parameters['max_pending'])
        fragment = PlanFragment(rules=(request, response), sequences=(sequence,))
    # 不自动改生成名称，当前signal碰撞在公共构建器立即拒绝。
    generated = [item.name for item in fragment.derived] + [item.id for item in fragment.rules] + [item.window_id for item in fragment.windows] + [item.id for item in fragment.calculations]
    generated.extend(item.sequence_id for item in fragment.sequences)
    conflicts = set(generated) & {item.name for item in signals}
    if conflicts:
        raise PlanValidationError('$.preset.name', '生成ID冲突：' + ', '.join(sorted(conflicts)))
    return fragment


def expand_presets(config, signals):
    """在独立配置副本中合入预设片段，保留用户节点并拒绝全部生成ID冲突。

    参数: config为dict，是调用方复制后的配置映射；本函数原地合入生成节点。
        signals为tuple[SignalDefinition, ...]，提供当前信号定义和预设角色匹配依据。
    返回: (PresetSpec tuple, 各预设RoleBinding tuple)，供计划保留原声明及角色追溯。
    异常: PlanValidationError为预设/用户结构或生成ID与用户/其他预设重名。
    副作用: 仅修改传入的局部derived/rules/windows/calculations/sequences；不修改raw_config快照或来源。
    """
    raw_derived = config.get('derived', {})
    if type(raw_derived) is not dict:
        raise PlanValidationError('$.derived', 'derived必须为别名对象')
    # 全部当前用户名称及节点ID都保留，生成项不得隐藏覆盖。
    occupied = {item.name for item in signals} | set(raw_derived)
    arrays = {}
    for key in ('rules', 'windows', 'calculations', 'sequences'):
        arrays[key] = array_at(config.get(key, []), '$.' + key)
        for index, row in enumerate(arrays[key]):
            if type(row) is dict and 'id' in row:
                raise PlanValidationError(f'$.{key}[{index}].id', '名称字段已统一为name，请替换id', 'unknown_field')
            if type(row) is not dict or 'name' not in row:
                raise PlanValidationError(f'$.{key}[{index}]', '节点必须包含name')
            occupied.add(text_at(row['name'], f'$.{key}[{index}].name', identifier=True))
    specs, bindings, preset_ids = [], [], set()
    for index, raw in enumerate(array_at(config.get('presets', []), '$.presets')):
        path = f'$.presets[{index}]'
        try:
            spec = PresetSpec.from_dict(raw)
            if spec.id in preset_ids:
                raise PlanValidationError('$.preset.name', 'preset id重复：' + spec.id)
            fragment = build_preset(spec, signals)
            bound = resolve_preset_roles(spec, signals)
            # to_dict承诺可直接合入用户配置；内部展开再转换到同一解析器形式。
            from .planning.config_groups import normalize_configuration
            serialized = normalize_configuration({'sources': [], 'signals': [], **fragment.to_dict()})
            generated = set(serialized['derived']) | {item['name'] for key in arrays for item in serialized.get(key, ())}
            if generated & occupied:
                raise PlanValidationError('$.preset.name', '生成ID冲突：' + ', '.join(sorted(generated & occupied)))
        except PlanValidationError as error:
            # 外层配置位置替换统一公共spec路径，不丢角色/参数诊断。
            raise PlanValidationError(error.path.replace('$.preset', path, 1), error.message, error.code) from error
        # 校验整个片段后再合入，失败不发布半个公开计划。
        raw_derived.update(serialized['derived'])
        for key in arrays:
            arrays[key].extend(serialized.get(key, ()))
        occupied.update(generated)
        preset_ids.add(spec.id)
        specs.append(spec)
        bindings.append(bound)
    config['derived'] = raw_derived
    config.update(arrays)
    return tuple(specs), tuple(bindings)
