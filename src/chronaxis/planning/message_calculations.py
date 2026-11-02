"""静态解析当前消息legacy_sum声明，保持解码profile和新计算policy分开。

输入为message_calculations原生JSON数组、当前来源/绑定和计划ID集合；输出冻结的
MessageCalculationPlan tuple。frame_id必填，channel默认采用来源通道，帧类型可省略；参数按FLOAT64处理，表达式
只访问本来源、本消息的完整CAN定位，不沿用全局派生、上一条值或普通TTL。
当前模式明确拒绝cache_policy，旧完整触发/缓存未接线不能靠同名字段冒充。
可选disjunction另声明方向别名和正负桶；方向可不在expr中，仍须有同一原消息
的完整定位。它选择本条原解码值，不改表达式、信号转换或旧读写调用。

require_message_calculation只检查已有typed计划与当前来源/声明的关系，供解析和
validate/explain共用；它不重新解析AST或raw_config。所有操作只处理有限配置，
不open/stat/resolve，不加载DBC、旧reader或执行流，不读取任何分析输入。
"""

# 只导入冻结模型、受限表达式及静态字段校验，不加载来源执行组件。
from ..core.declarations import DeclarationBindings
from ..core.message_binding import ExpressionParameter, MessageDeclarations
from ..legacy.records import PROFILE_ID
from ..legacy.disjunction import LegacyDisjunction
from ..core.types import SignalDType
from ..sources.can_spec import LegacyCANSpec, can_field_from_key
from ..sources.text_can_spec import CANTextSpec
from .checks import PlanValidationError, array_at, choice_at, model_at, object_at, text_at
from .models import LegacyMessageSelector, MessageCalculationPlan
from .nodes import expression_at, register_id


def require_message_calculation(calculation, sources, bindings: DeclarationBindings) -> None:
    """核已有typed逐消息指标与当前计划一致，不借旧配置覆盖typed替换。

    参数: calculation为MessageCalculationPlan；sources为当前SourcePlan tuple；bindings
        为当前DeclarationBindings。
        返回: None，来源、帧定位和原声明均一致。
    异常: TypeError为指标/绑定模型错误；ValueError为来源能力、声明或定位冲突。
    边界: 不重编译AST，不读DBC；字段存在性和单位实况仍由同次READY另行验证。
    """
    if type(calculation) is not MessageCalculationPlan or not isinstance(bindings, DeclarationBindings):
        raise TypeError('逐消息指标需要MessageCalculationPlan及当前DeclarationBindings')
    matching = tuple(source for source in sources if source.name == calculation.source)
    if len(matching) != 1:
        raise ValueError('逐消息指标必须引用当前唯一来源')
    source = matching[0]
    # 计算只取当条解码值；格式仍由各自真实读取profile标识，不能冒充旧解码器。
    if source.source_type == 'can_blf' and isinstance(source.config, LegacyCANSpec):
        if (source.config.legacy_profile != PROFILE_ID or source.config.unit != 's'
                or source.time_unit != 's' or source.timezone_text is not None):
            raise ValueError('BLF逐消息来源需保原profile和秒时间声明')
        profile = PROFILE_ID
    elif (source.source_type in ('can_asc', 'asc_or_blf', 'raw_can_csv')) and (isinstance(source.config, CANTextSpec)):
        if source.source_type != source.config.source_type:
            raise ValueError('文本报文来源种类与解析声明不同')
        profile = 'can-text-v1'
    else:
        raise ValueError('逐消息计算需要BLF、ASC或原始报文CSV来源')
    if source.config.name != source.name or calculation.profile != profile:
        raise ValueError('逐消息指标profile和名称必须等于实际来源')
    declared = next((item for item in bindings.sources if item.name == calculation.source), None)
    if (declared is None or declared.input_identity != source.input_identity
            or declared.timebase != source.config.timebase or declared.offset_ns != source.config.offset_ns):
        raise ValueError('逐消息来源定位、原时基或offset与当前完整声明不符')
    if calculation.update_message.channel != source.config.channel:
        raise ValueError('逐消息选择器channel与来源声明不一致')
    declaration = calculation.expr.bindings
    if (declaration.declarations.identity != bindings.identity or declaration.source != calculation.source
            or declaration.parameters != calculation.parameters or declaration.derived_names
            or declaration.message_policy != calculation.message_policy):
        raise ValueError('逐消息表达式必须属于当前完整原声明、来源和参数')
    # 依赖必须是编译树的真实别名，不能由外层投影遗漏或偷偷增加其他消息。
    if type(calculation.expr.dependencies) is not tuple or calculation.expr.dependencies != calculation.expr.root.aliases:
        raise ValueError('逐消息表达式依赖与静态树不一致')
    selector = calculation.update_message
    required_flags = [selector.is_extended, selector.is_fd]
    # 方向可以独立于公式，但仍必须来自本条同一原消息，不能借缓存跨消息取值。
    dependencies = calculation.expr.dependencies
    if calculation.disjunction is not None:
        direction = bindings.resolve(calculation.disjunction.signal)
        if direction.dtype not in (SignalDType.INT64, SignalDType.UINT64, SignalDType.FLOAT64, SignalDType.BOOL):
            raise ValueError('disjunction方向仅接受数值或bool声明，不接受enum')
        dependencies = tuple(dict.fromkeys((*dependencies, calculation.disjunction.signal)))
    for alias in dependencies:
        definition = bindings.resolve(alias)
        if definition.source != calculation.source or declaration.resolve(alias) is not definition:
            raise ValueError('逐消息依赖须保当前来源的同一原SignalDefinition')
        field = can_field_from_key(definition.field)
        # 静态声明允许省略类型；明确给出的约束不能冲突，实际唯一性由读取阶段检查。
        if ((field.channel, field.frame_id) != (selector.channel, selector.frame_id)
                or any(left is not None and right is not None and left != right for left, right in
                       ((field.is_extended, selector.is_extended), (field.is_fd, selector.is_fd)))):
            raise ValueError('逐消息依赖的帧定位与update_message不一致')
        # 未限制的选择器不能掩盖两个依赖相互矛盾的明确帧类型。
        for index, value in enumerate((field.is_extended, field.is_fd)):
            if value is not None:
                if required_flags[index] is not None and required_flags[index] != value:
                    raise ValueError('逐消息表达式的依赖必须属于同一实际帧类型')
                required_flags[index] = value


def parse_message_calculations(value, sources, bindings, ids) -> tuple[MessageCalculationPlan, ...]:
    """按声明顺序解析独立逐消息指标，ID与原规则/窗口/指标共用集合。

    参数: value为原生JSON数组；sources/bindings为原计划静态模型；ids为本次
        已使用ID集合。返回: MessageCalculationPlan tuple。
    异常: PlanValidationError保具体JSON路径；cache_policy报旧完整缓存能力未接线。
    副作用: 只向本次局部ids登记名称，不读输入、DBC或执行表达式。
    """
    result = []
    for index, raw in enumerate(array_at(value, '$.message_calculations')):
        path = f'$.message_calculations[{index}]'
        # 旧配置即使尚无新policy字段，也先说明旧完整cache模式为何不能运行。
        if type(raw) is dict and 'cache_policy' in raw:
            raise PlanValidationError(path + '.cache_policy',
                '旧profile完整触发/cache模式尚未接线；current_message-v1仅用本条消息，不接受cache_policy',
                'capability_unavailable')
        raw = object_at(raw, path, ('name', 'update_message', 'expr', 'unit'),
                        ('parameters', 'split_by_sign', 'source', 'profile', 'operation', 'message_policy'))
        calculation_id = register_id(raw['name'], path + '.name', ids)
        from .input_defaults import source_reference
        source_name = source_reference(raw, sources, path, can_only=True)
        source = next((item for item in sources if item.name == source_name), None)
        if source is None:
            raise PlanValidationError(path + '.source', '逐消息指标来源不存在')
        text_source = ((source.source_type in ('can_asc', 'asc_or_blf', 'raw_can_csv')) and (isinstance(source.config, CANTextSpec)))
        if not text_source and (source.source_type != 'can_blf' or not isinstance(source.config, LegacyCANSpec)):
            raise PlanValidationError(path + '.source', '逐消息计算需要can_blf、can_asc或raw_can_csv来源', 'capability_unavailable')
        expected_profile = 'can-text-v1' if text_source else source.config.legacy_profile
        profile = choice_at(raw.get('profile', expected_profile), (expected_profile,), path + '.profile')
        if profile != expected_profile:
            raise PlanValidationError(path + '.profile', 'profile必须等于来源legacy_profile')
        # 当前只有一种逐消息累计策略；省略采用它，显式未知策略仍拒绝。
        operation = choice_at(raw.get('operation', 'legacy_sum'), ('legacy_sum',), path + '.operation')
        policy = choice_at(raw.get('message_policy', 'current_message-v1'), ('current_message-v1',), path + '.message_policy')
        selector_raw = object_at(raw['update_message'], path + '.update_message',
                                 ('frame_id',), ('channel', 'is_extended', 'is_fd'))
        for flag in ('is_extended', 'is_fd'):
            if flag in selector_raw and type(selector_raw[flag]) is not bool:
                raise PlanValidationError(path + '.update_message.' + flag, '填写时需要bool，不能为null')
        from .channels import channel_index
        channel = (channel_index(selector_raw['channel'], path + '.update_message.channel')
                   if 'channel' in selector_raw else source.config.channel)
        selector = model_at(LegacyMessageSelector, path + '.update_message',
            channel, selector_raw['frame_id'], selector_raw.get('is_extended'), selector_raw.get('is_fd'))
        if selector.channel != source.config.channel:
            raise PlanValidationError(path + '.update_message.channel', '选择器channel必须等于来源通道')
        parameters_raw = raw.get('parameters', {})
        # 参数名称可由用户声明，但容器及每个value/unit对象仍严格校验。
        parameters_raw = object_at(parameters_raw, path + '.parameters', (),
                                   tuple(parameters_raw) if type(parameters_raw) is dict else ())
        parameters = []
        for name, item in parameters_raw.items():
            parameter_path = path + '.parameters.' + name
            item = object_at(item, parameter_path, ('value', 'unit'))
            parameters.append(model_at(ExpressionParameter, parameter_path, name, item['value'], item['unit']))
        parameters = tuple(parameters)
        # 不接普通全局派生；当前表达式仅原别名与本指标显式参数，没有保持语义。
        declaration = model_at(MessageDeclarations, path + '.parameters', bindings, source_name, parameters,
                               message_policy=policy)
        unit = text_at(raw['unit'], path + '.unit')
        expression = expression_at(raw['expr'], path + '.expr', declaration, (), unit=unit)
        # 三字段显式选择原值政策，不把配置缺失、null或自由条件当作分桶。
        disjunction = None
        if 'split_by_sign' in raw:
            item = object_at(raw['split_by_sign'], path + '.split_by_sign', ('signal', 'bucket'), ('value_policy',))
            disjunction = model_at(LegacyDisjunction, path + '.split_by_sign',
                item['signal'], item['bucket'], item.get('value_policy', 'raw_decoded-v1'))
            model_at(bindings.resolve, path + '.split_by_sign.signal', disjunction.signal)
        calculation = model_at(MessageCalculationPlan, path, calculation_id, source_name, profile, operation,
                          selector, expression, unit, parameters, policy, disjunction)
        # 校验共享于validate/explain，typed替换不能绕过跨对象完整定位关系。
        model_at(require_message_calculation, path + '.expr', calculation, sources, bindings)
        result.append(calculation)
    return tuple(result)
