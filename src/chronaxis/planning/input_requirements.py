"""从请求结果收集实际输入需求，不把全部信号声明当作运行任务。

输入为已完成静态检查的 AnalysisPlan，输出有限、冻结的来源需求。规则、
窗口和两类指标都是结果根；表达式依赖已经展开到原信号，未引用的派生项
不单独成为根。普通时序样本与逐消息字段分开，方向字段和纯参数指标的
报文选择器独立保留。预设按已展开的公共节点处理，不按全部角色增加需求。
本模块不读取日志、CSV、DBC，不执行归一化或数值计算，也不创建运行证明。
普通分析来源保留既定会话观测范围；纯消息总计按实际需求省去时间或仅保留
相关记录时间。原帧导出单独列出，不能用空信号依赖推断原始帧可以丢弃。
完整声明的语法、单位、名称和循环校验不由此替代。
"""

from ..core.counts_v4 import OBJECT_COUNTS
from dataclasses import dataclass

from ..sources.can_spec import LegacyCANSpec, can_field_from_key


@dataclass(frozen=True)
class SourceInputRequirements:
    """保存一个来源的有限需求，不持有输入行、表达式树或可变配置。

    别名按 signals 原声明序；字段和 ID 按首次出现顺序去重。decode_frame_ids
    包含所需 CAN 字段的 ID 和所有逐消息选择器 ID，不是实际观测到的 ID 集合。
    非 CAN 来源的两个 ID 字段为空，required_fields 仍为原字段定位字符串。
    """

    source: str  # 原来源名。
    ordinary_sample_aliases: tuple[str, ...]  # 普通时序结果实际读取的别名。
    message_aliases: tuple[str, ...]  # 当次消息公式及方向使用的别名。
    required_aliases: tuple[str, ...]  # 两类消费者的字段并集。
    required_fields: tuple[str, ...]  # 去重后的原规范定位，不重新解释信号名。
    decode_frame_ids: tuple[int, ...]  # 所需字段和消息触发ID；非CAN为空。
    selector_ids: tuple[int, ...]  # 即使公式无字段也保留的触发ID。
    time_scope: str = 'source'  # none不采时间；selected仅相关记录；source保全部来源时间。
    input_check: str = 'auto'  # 实际选择：auto按需检查；full完整诊断，含显式all覆盖。
    reasons: tuple[str, ...] = ()  # 计划阶段选择原因，不冒充实际执行或观测证明。
    active: bool = True  # 只为实际消费者打开来源。
    clock_aliases: tuple[str, ...] = ()  # 只用于推进周期的定位，不因此读取该信号数值。


@dataclass(frozen=True)
class InputRequirements:
    """保存同一计划的样本、逐消息、观测及原帧需求，保留原声明顺序。

    ordinary_sample_aliases 供普通信号批和历史使用；message_aliases 供同条
    消息求值使用。required_aliases 是二者并集，不能用它强制生成普通样本。
    sources保留全部声明；observation_sources仅列实际需要完整来源观测的来源。
    raw_sources 只来自显式原帧导出请求，不由解码或指标依赖推导。
    """

    ordinary_sample_aliases: tuple[str, ...]  # 全计划所需普通样本，保原声明序。
    message_aliases: tuple[str, ...]  # 全计划所需逐消息字段。
    required_aliases: tuple[str, ...]  # 两类输入的声明序并集。
    sources: tuple[SourceInputRequirements, ...]  # 每来源独立需求，不省略观测来源。
    observation_sources: tuple[str, ...]  # time_scope=source的来源；不是目标记录时间范围。
    raw_sources: tuple[str, ...]  # 仅显式原始片段输出需要保存原帧的来源。

    analysis_sample_aliases: tuple[str, ...] = ()  # 普通计算所需值，不含纯导出列。
    constant_observation: bool = False  # 无信号常量规则/统计需要会话观测范围。
    transform_names: tuple[str, ...] = ()  # 按拓扑序实际消费的离散序列；不属于reader投影。

    def for_source(self, name: str) -> SourceInputRequirements:
        """按来源名称取得本计划的需求，不创建新副本。

        参数: name为原生来源名称字符串。
        返回: 同一冻结 SourceInputRequirements。
        异常: TypeError 为非原生文本；ValueError 为未知来源。
        """
        if type(name) is not str:
            raise TypeError('需求来源名称必须为原生str')
        for source in self.sources:
            if source.source == name:
                return source
        raise ValueError('未知需求来源：' + name)


def supports_unbounded_message_summary(plan) -> bool:
    """检查计划是否只请求整文件逐消息累计，不据此读取或计算数据。

    参数: plan为已解析的AnalysisPlan；自由声明或未引用派生不产生运行消费者。
    返回: bool；True允许用户省略dataset.domain，仍需另选实际检查和时间范围。
    异常: 非法typed对象的属性错误原样传播；本函数不吞配置或来源错误。
    """
    # 消息表达式仅使用本条值和显式参数，没有普通TTL或窗口消费者。
    needed = {item.source for item in plan.message_calculations}
    source_ok = bool(needed) and all(item.source_type in ('can_blf', 'can_asc', 'asc_or_blf', 'raw_can_csv')
        for item in plan.sources if item.name in needed)
    return ((source_ok) and (bool(plan.message_calculations)) and (all(item.message_policy == 'current_message-v1' for item in plan.message_calculations)) and (not plan.rules) and (not plan.windows) and (not plan.calculations) and (plan.outputs.signal_csv is None) and (plan.outputs.can_frames is None))


def collect_input_requirements(plan) -> InputRequirements:
    """从全部请求结果收集原始输入需求，不进行输入 I/O 或运行时值校验。

    参数:
        plan: 已静态检查的 AnalysisPlan；不根据 raw_config 重新解析或猜测引用。
    返回:
        InputRequirements。别名、来源和去重字段保留声明顺序，纯参数逐消息
        指标即使没有信号依赖，也保留 update_message.frame_id。
    异常:
        TypeError 为非计划对象或依赖容器错误；ValueError 为未声明依赖、
        缺少规则/窗口/来源引用或错误 CAN 字段。模型属性错误原样传播。
    边界:
        仅收集依赖，不替代完整配置校验；不用的声明仍由计划构建器校验。
        所有声明规则和窗口本身都是输出根，不只收集被指标引用的节点。
    """
    # 延迟导入避免计划构建器与需求报告之间形成模块循环。
    from .plan import AnalysisPlan

    if not isinstance(plan, AnalysisPlan):
        raise TypeError('输入需求需要AnalysisPlan')
    definitions = tuple(item.definition for item in plan.signals)
    names = {item.name for item in definitions}
    virtual = {t.name for t in plan.transforms}
    ordinary, messages = set(), set()
    rules = {item.rule_id: item for item in plan.rules}
    windows = {item.window_id: item for item in plan.windows}
    sources = {item.name: item for item in plan.sources}
    selectors = {name: [] for name in sources}

    def add(expression, destination):
        """将已展开依赖加入本次有限集合，拒绝未知别名。

        参数: expression为原静态表达式；destination为本次局部set。
        返回: None。异常: 依赖类型错误或未声明名称抛 TypeError/ValueError。
        """
        dependencies = expression.dependencies
        if type(dependencies) is not tuple or any(type(name) is not str for name in dependencies):
            raise TypeError('表达式依赖必须为原生str tuple')
        if not set(dependencies) <= (names if destination is messages else names|virtual):
            raise ValueError('表达式依赖包含未声明信号')
        destination.update(dependencies)

    def add_rule(rule_id):
        """收集定义结果范围的原规则条件，不用空依赖掩盖缺失引用。

        参数: rule_id为本计划规则ID。返回: None。
        异常: ValueError 为未知规则；条件依赖错误沿 add 原样传播。
        """
        if rule_id not in rules:
            raise ValueError('输入需求引用未知规则：' + str(rule_id))
        for expression in rules[rule_id].expressions:
            add(expression, ordinary)

    for rule in plan.rules:
        for expression in rule.expressions:
            add(expression, ordinary)
    for window in plan.windows:
        add_rule(window.event)
    for calculation in plan.calculations:
        for expression in (calculation.signal, calculation.condition):
            if expression is not None:
                add(expression, ordinary)
        if calculation.scope != 'session':
            prefix, separator, target = calculation.scope.partition(':')
            if not separator or prefix not in ('event', 'segment'):
                raise ValueError('输入需求需要合法指标范围')
            if prefix == 'segment':
                if target not in windows:
                    raise ValueError('输入需求引用未知窗口：' + target)
                target = windows[target].event
            add_rule(target)
    for calculation in plan.message_calculations:
        add(calculation.expr, messages)
        if calculation.disjunction is not None:
            alias = calculation.disjunction.signal
            if alias not in names:
                raise ValueError('逐消息方向引用未声明信号')
            messages.add(alias)
        if calculation.source not in sources or sources[calculation.source].source_type not in ('can_blf', 'can_asc', 'asc_or_blf', 'raw_can_csv'):
            raise ValueError('逐消息选择器需要本计划CAN来源')
        selectors[calculation.source].append(calculation.update_message.frame_id)

    from .transforms import active_transforms, physical_dependencies
    transforms = active_transforms(plan,ordinary)
    ordinary = set(physical_dependencies(plan,ordinary))
    analysis = set(ordinary)
    choices = dict(() if plan.intervals is None else plan.intervals.resolved)
    constant_observation = (any(not rule.dependencies and
        (rule.rule_id not in choices or choices[rule.rule_id].driver is None) for rule in plan.rules) or any(
        calculation.scope=='session' and calculation.operation not in OBJECT_COUNTS and (calculation.calculation_id not in choices or choices[calculation.calculation_id].driver is None) and
        not any(e.dependencies for e in (calculation.signal,calculation.condition) if e is not None) for calculation in plan.calculations))
    # 导出是实际消费者：原始信号表所需字段进入普通历史，不依赖表达式恰好引用它。
    if plan.outputs.signal_csv is not None:
        exported=set(plan.outputs.signal_csv.spec.signals)
        if not exported<=names:
            raise ValueError('信号导出引用未定义别名')
        ordinary.update(exported)
    active = {t.name for t in transforms}
    clocks = {choice.driver for name, choice in (() if plan.intervals is None else plan.intervals.resolved)
              if choice.driver is not None and (name not in virtual or name in active)}
    constant_observation |= any(not t.physical for t in transforms)
    if not clocks <= names:
        raise ValueError('间隔驱动引用未声明信号')
    required = ordinary | messages | clocks
    # 只有整文件消息总计可完全省时间；显式时间域始终保留筛选所需时间。
    summary_only = supports_unbounded_message_summary(plan)
    if type(plan.dataset.domain_explicit) is not bool:
        raise TypeError('dataset.domain_explicit需要原生bool')
    if plan.dataset.domain_explicit != (plan.dataset.domain is not None):
        raise ValueError('dataset.domain_explicit必须与实际domain声明是否存在一致')
    entries = []
    for source in plan.sources:
        selected = tuple(item for item in definitions if item.source == source.name and item.name in required)
        fields = tuple(dict.fromkeys(item.field for item in selected if item.name in ordinary | messages))
        clock_ids = tuple(can_field_from_key(item.field).frame_id for item in selected
                          if item.name in clocks and source.source_type in ('can_blf','can_asc','asc_or_blf','raw_can_csv'))
        selector_ids = tuple(dict.fromkeys((*selectors[source.name], *clock_ids)))
        frame_output=plan.outputs.can_frames
        export_ids=tuple(rule.frame_id for rule in frame_output.rules) if frame_output is not None and frame_output.source==source.name else ()
        frame_ids = (tuple(dict.fromkeys(
            (*[can_field_from_key(field).frame_id for field in fields], *selector_ids,*export_ids)))
            if source.source_type in ('can_blf','can_asc','asc_or_blf','raw_can_csv') else ())
        # 非CAN与混合任务保留原观测契约；完整诊断不随空依赖被裁剪。
        input_check, time_scope = 'auto', 'source'
        reasons = ('普通分析、混合任务或非CAN来源保留全来源观测时间。',)
        if source.source_type == 'can_blf' and isinstance(source.config, LegacyCANSpec):
            input_check = source.config.input_check
            if type(input_check) is not str or input_check not in ('auto', 'full'):
                raise ValueError('CAN input_check需要auto或full')
            if input_check == 'full' or source.config.decode_scope == 'all':
                input_check = 'full'
                reasons = ('显式完整输入检查或all解码保留全部原帧与时间诊断。',)
            elif summary_only:
                time_scope = 'selected' if plan.dataset.domain_explicit else 'none'
                reasons = (('用户显式配置domain，仅处理所需记录时间以执行时间筛选。',)
                    if plan.dataset.domain_explicit else
                    ('整文件固定周期当前消息总计无时间消费者，不采集报文时间。',))
        if source.source_type in ('can_asc','asc_or_blf','raw_can_csv'):
            input_check=source.config.input_check
            if input_check=='full':
                reasons=('显式完整输入检查保留全部原帧时间顺序检查。',)
        active = True
        raw_needed=frame_output is not None and frame_output.source==source.name
        active=bool(selected or selectors[source.name] or constant_observation or raw_needed)
        if not active:
            time_scope='none'; reasons=('未被计算、观测或导出引用，不打开来源。',)
        elif source.source_type in ('can_blf','can_asc','asc_or_blf','raw_can_csv') and input_check!='full':
            observed=bool(set(item.name for item in selected)&(ordinary|clocks) or constant_observation or raw_needed)
            time_scope='source' if observed else 'selected' if plan.dataset.domain is not None or source.source_type!='can_blf' else 'none'
            reasons=(('所需时序计算/导出使用实际来源观测范围。' if observed else
                '逐消息累计只检查时间筛选所需记录。' if time_scope=='selected' else
                '整文件逐消息累计无时间消费者，不采时间。'),)
        if (active and source.source_type in ('can_asc','asc_or_blf')
                and input_check=='auto' and not raw_needed):
            reasons=('按原顺序读取；仅检查所需通道/ID的时间先后顺序，无关帧不进入计算；观测范围按time_scope所列需求处理。',)
        entries.append(SourceInputRequirements(
            source.name, tuple(item.name for item in selected if item.name in ordinary),
            tuple(item.name for item in selected if item.name in messages),
            tuple(item.name for item in selected), fields, frame_ids, selector_ids,
            time_scope, input_check, reasons, active, tuple(item.name for item in selected if item.name in clocks)))
    return InputRequirements(
        tuple(item.name for item in definitions if item.name in ordinary),
        tuple(item.name for item in definitions if item.name in messages),
        tuple(item.name for item in definitions if item.name in required),
        tuple(entries), tuple(item.source for item in entries if item.time_scope == 'source'),
        (() if plan.outputs.can_frames is None else (plan.outputs.can_frames.source,)),
        tuple(item.name for item in definitions if item.name in analysis), constant_observation,
        tuple(t.name for t in transforms))
