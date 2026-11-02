"""声明计算所用的间隔及可选诊断，不读取报文或建立额外时间轴。

输入是配置中的intervals/diagnostics和已编译计划。输出为冻结选择，
记录每个消费者采用actual、fixed或dbc，以及明确的驱动信号。
DBC周期只在运行初始化读取；这里检查来源种类和完整报文定位。
当前配置3支持这些声明；执行是否就绪由公共能力报告判断。
"""

from dataclasses import dataclass, replace

from ..core.validation import require_identifier
from ..sources.can_spec import can_field_from_key
from .checks import PlanValidationError, duration_at, model_at, object_at
from .sequences import sequence_dependencies


@dataclass(frozen=True)
class IntervalChoice:
    """选择一次计时依据；step_ns仅用于fixed，driver为原信号别名。

    actual沿既有真实时间推进，不额外指定驱动。fixed/dbc的驱动可以在
    配置解析时按唯一候选补齐；不在对象中保存逐帧时间或DBC实例。
    """

    mode: str = 'actual'  # 实际差、固定值或运行时读取的DBC周期。
    step_ns: int | None = None  # 仅fixed使用的正纳秒数；DBC在这里不提前填值。
    driver: str | None = None  # 推进累计的原信号别名；不存另一列时间。

    def __post_init__(self):
        """拒绝矛盾字段、布尔间隔及溢出；无I/O或隐式数值转换。

        参数: 无，读取mode、step_ns和driver。返回: None。异常: TypeError/ValueError为模式、纳秒范围或信号名错误。副作用: 无。
        """
        if type(self.mode) is not str or self.mode not in ('actual', 'fixed', 'dbc'):
            raise ValueError('interval.mode需要actual、fixed或dbc')
        if self.mode == 'fixed':
            if type(self.step_ns) is not int or not 0 < self.step_ns <= (1 << 63) - 1:
                raise ValueError('fixed间隔需要int64范围内正整数纳秒')
        elif self.step_ns is not None:
            raise ValueError('只有fixed接受间隔数值')
        if self.driver is not None:
            require_identifier(self.driver, 'interval.driver')
            if self.mode == 'actual':
                raise ValueError('actual沿既有更新时间推进，不接受driver')


@dataclass(frozen=True)
class IntervalPlan:
    """保存任务默认、显式覆盖及已解析的消费者选择。

    三组数据均为有限配置，不是样本历史。resolved按声明顺序列出实际
    消费者；legacy_sum自带period，不进入普通间隔解析。
    """

    default: IntervalChoice = IntervalChoice()  # 任务级缺省选择。
    overrides: tuple[tuple[str, IntervalChoice], ...] = ()  # 按稳定节点ID的显式选择。
    resolved: tuple[tuple[str, IntervalChoice], ...] = ()  # 当前消费者的唯一有效选择。

    def __post_init__(self):
        """检查冻结容器、唯一节点与选择类型，防止typed替换引入可变对象。

        参数: 无，读取default、overrides及resolved。返回: None。异常: TypeError/ValueError为非冻结选择、节点重复或非法名称。副作用: 无。
        """
        if type(self.default) is not IntervalChoice:
            raise TypeError('intervals.default需要IntervalChoice')
        for label, entries in (('overrides', self.overrides), ('resolved', self.resolved)):
            if type(entries) is not tuple:
                raise TypeError('intervals.' + label + '需要tuple')
            names = set()
            for entry in entries:
                if (type(entry) is not tuple or len(entry) != 2
                        or type(entry[1]) is not IntervalChoice):
                    raise TypeError('interval选择需要(node_id, IntervalChoice)')
                require_identifier(entry[0], 'interval.node_id')
                if entry[0] in names:
                    raise ValueError('interval节点重复：' + entry[0])
                names.add(entry[0])


@dataclass(frozen=True)
class DiagnosticPlan:
    """分别声明详细追溯、完整性诊断及现场留存，全部默认关闭。

    这些开关不取消必要输入检查，不代替outputs.contributions，彼此不捆绑。
    此对象不分配暂存或执行核验；实际资源能力接线前必须拒绝执行。
    """

    trace: bool = False  # 请求详细追溯，独立于贡献明细。
    integrity: bool = False  # 请求额外完整性诊断，不代替必要输入检查。
    retain_work: bool = False  # 请求保留本次自有现场，不授权保留无关用户数据。

    def __post_init__(self):
        """仅接受原生bool；不把0/1或文本解释成开关。

        参数: 无，读取三个独立开关。返回: None。异常: TypeError为任一值不是原生bool。副作用: 无。
        """
        if any(type(value) is not bool for value in (self.trace, self.integrity, self.retain_work)):
            raise TypeError('diagnostics各项需要bool')


def parse_diagnostics(value) -> DiagnosticPlan:
    """解析可选诊断对象；未知键或非bool报配置错误，不打开文件。

    参数: value(dict)为可省略的三个bool开关。返回: DiagnosticPlan，省略项为False。异常: PlanValidationError为未知键或非bool。副作用: 无。
    """
    raw = object_at(value, '$.diagnostics', (), ('trace', 'integrity', 'retain_work'))
    return model_at(DiagnosticPlan, '$.diagnostics', **raw)


def _choice(value, path) -> IntervalChoice:
    """将显式单位数值解析为纳秒；不查询DBC或猜测缺失的fixed数值。

    参数: value(dict)为mode及可选带单位value/driver；path(str)定位错误。返回: IntervalChoice，固定间隔以整数ns保存。异常: PlanValidationError为缺项、矛盾、单位或类型错误。副作用: 无。
    """
    raw = object_at(value, path, ('mode',), ('value', 'driver'))
    if 'driver' in raw and type(raw['driver']) is not str:
        raise PlanValidationError(path + '.driver', '显式driver需要原信号名称，不能为null或其他类型')
    if (raw['mode'] == 'fixed') != ('value' in raw):
        raise PlanValidationError(path + '.value', 'fixed必须给value，其他模式不接受value')
    step = duration_at(raw['value'], path + '.value', positive=True) if 'value' in raw else None
    return model_at(IntervalChoice, path, raw['mode'], step, raw.get('driver'))


def _consumers(plan):
    """列出规则、配对、窗口和需时长指标的原信号依赖，保持计划顺序。

    返回(node_id, aliases)元组。样本min/max/select与旧逐消息求和没有
    普通dt消费者；对它们单独配置覆盖属于无效需求，不能静默忽略。

    参数: plan(AnalysisPlan)为已校验引用的计划。返回: tuple，每项为节点ID及原信号别名tuple，无消费者为空。异常: 错误typed引用的KeyError/StopIteration由外层验证报告捕获。副作用: 无。
    """
    rules = {rule.rule_id: rule for rule in plan.rules}
    # 纯上升/下降沿不使用帧间时长，不能因任务默认fixed而强迫它选择驱动。
    entries = [(rule.rule_id, rule.dependencies) for rule in plan.rules
               if rule.rule_type not in ('rising_edge', 'falling_edge')]
    entries.extend((item.sequence_id, sequence_dependencies(item, plan.rules, plan.bindings))
                   for item in plan.sequences)
    entries.extend((item.window_id, rules[item.event].dependencies) for item in plan.windows)
    for item in plan.calculations:
        if item.operation not in ('integral', 'duration', 'time_weighted_mean', 'min_time', 'max_time'):
            continue
        aliases = {alias for expression in (item.signal, item.condition)
                   if expression is not None for alias in expression.dependencies}
        # event/segment的区间也由父规则决定，不能漏掉其唯一驱动或多源歧义。
        if item.scope != 'session':
            scope, target = item.scope.split(':', 1)
            event = target if scope == 'event' else next(window.event for window in plan.windows if window.window_id == target)
            aliases.update(rules[event].dependencies)
        entries.append((item.calculation_id, tuple(sorted(aliases))))
    return tuple(entries)


def _driver_key(plan, alias):
    """按真实报文定位合并同帧信号候选；已解析信号各自独立。

    返回来源与报文身份或来源与字段；只读已校验声明，不加载DBC。

    参数: plan为当前计划，alias为原信号别名。返回: tuple物理更新身份。异常: 无效别名/报文定位的ValueError或缺来源StopIteration。副作用: 无。
    """
    definition = plan.bindings.resolve(alias)
    source = next(item for item in plan.sources if item.name == definition.source)
    if source.source_type in ('can_blf', 'can_asc', 'asc_or_blf', 'raw_can_csv'):
        field = can_field_from_key(definition.field)
        return (source.name, field.channel, field.frame_id, field.is_extended, field.is_fd)
    return (source.name, definition.field)


def _resolve(plan, choice, aliases, path):
    """选定唯一驱动，检查DBC适用性；多候选/常量无驱动时要求明确填写。

    参数: plan为当前计划；choice为IntervalChoice；aliases为原依赖tuple；path为错误位置。返回: 补齐driver的IntervalChoice，actual原样返回。异常: PlanValidationError为歧义、未知驱动、时基不符或DBC不适用。副作用: 无。
    """
    if choice.mode == 'actual':
        return choice
    driver = choice.driver
    if driver is None:
        candidates = {}
        for alias in aliases:
            candidates.setdefault(_driver_key(plan, alias), alias)
        if len(candidates) != 1:
            raise PlanValidationError(path + '.driver', '需要显式指定驱动信号；候选数量=' + str(len(candidates)))
        driver = next(iter(candidates.values()))
    # 显式驱动允许作为独立时钟信号，但必须是当前原信号，而非派生名称。
    declared = {item.definition.name: item.definition for item in plan.signals}
    if driver not in declared:
        raise PlanValidationError(path + '.driver', 'driver必须是当前已声明的原信号')
    source = next(item for item in plan.sources if item.name == declared[driver].source)
    # 独立时钟驱动也必须与表达式来源可比较，不能把不同相对起点直接计成同一段。
    model_at(plan.bindings.require_synchronized, path + '.driver',
             tuple(dict.fromkeys((*aliases, driver))))
    if choice.mode == 'dbc' and source.source_type not in ('can_blf', 'can_asc', 'asc_or_blf', 'raw_can_csv'):
        raise PlanValidationError(path + '.mode', 'DBC周期仅适用于原始报文，已解析数据不可选择')
    return replace(choice, driver=driver)


def resolve_intervals(plan, default, overrides) -> IntervalPlan:
    """把有限声明解析为消费者选择；typed校验与JSON解析共用本函数。

    输入是已构造的计划和冻结选择；返回新的IntervalPlan。未知节点、
    无用覆盖或不适用DBC报ValueError/PlanValidationError；无数据读取。

    参数: plan为当前计划；default为IntervalChoice；overrides为(node_id, choice)冻结tuple。返回: IntervalPlan，resolved保持消费者声明顺序。异常: TypeError/ValueError及PlanValidationError为非法声明或不明确驱动。副作用: 无。
    """
    declared = IntervalPlan(default, overrides)
    consumers = _consumers(plan)
    names = {name for name, _ in consumers}
    unknown = set(dict(overrides)) - names
    if unknown:
        raise PlanValidationError('$.intervals.overrides', '不是间隔消费者：' + ', '.join(sorted(unknown)))
    if not consumers and default != IntervalChoice():
        raise PlanValidationError('$.intervals.default', '本任务没有普通间隔消费者；legacy_sum保留表达式period')
    lookup = dict(declared.overrides)
    resolved = tuple((name, _resolve(plan, lookup.get(name, default), aliases,
                                    '$.intervals.overrides.' + name)) for name, aliases in consumers)
    return IntervalPlan(default, overrides, resolved)


def parse_intervals(value, plan) -> IntervalPlan:
    """解析任务默认和节点覆盖；显式null与未知字段均拒绝，缺省使用actual。

    参数: value(dict)为default及overrides；plan为已解析消费者的计划。返回: IntervalPlan。异常: PlanValidationError为结构、取值或引用错误。副作用: 无。
    """
    raw = object_at(value, '$.intervals', (), ('default', 'overrides'))
    default = _choice(raw.get('default', {'mode': 'actual'}), '$.intervals.default')
    overrides = raw.get('overrides', {})
    if type(overrides) is not dict:
        raise PlanValidationError('$.intervals.overrides', '需要以节点ID为键的对象')
    entries = tuple((name, _choice(choice, '$.intervals.overrides.' + name))
                    for name, choice in overrides.items())
    return model_at(resolve_intervals, '$.intervals', plan, default, entries)


def require_interval_declarations(plan):
    """核对类型化计划中的间隔和诊断声明未被替换为不一致的解析结果。

    参数: plan为待验证的AnalysisPlan。返回: None。异常: TypeError/ValueError为版本、新类型或解析结果不一致；引用错误由公共报告收集。副作用: 无，不重编译表达式。
    """
    if type(plan.intervals) is not IntervalPlan or type(plan.diagnostics) is not DiagnosticPlan:
        raise TypeError('当前计划需要IntervalPlan与DiagnosticPlan')
    expected = resolve_intervals(plan, plan.intervals.default, plan.intervals.overrides)
    if expected != plan.intervals:
        raise ValueError('intervals.resolved与当前消费者或驱动不一致')
