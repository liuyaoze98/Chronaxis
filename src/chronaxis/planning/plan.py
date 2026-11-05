"""把分析配置转换成经过静态检查的分析计划。

使用入口：
    AnalysisPlan.from_dict(config, base_dir=...)接收一个配置字典。
    load_analysis_plan(path)读取一个JSON/YAML配置文件，再调用from_dict检查内容。
输出都是AnalysisPlan，其中保存来源、信号、表达式、规则、窗口和指标，
以及计划采用的计算方式、资源预算和输出格式。

处理顺序是：检查字段与版本 → 复制配置 → 检查来源和信号声明
→ 检查表达式及相互引用 → 保存计划。静态检查是根据配置声明判断
是否合法，不读取待分析的日志或CSV；省略CAN信号元数据时按需读DBC，不执行计算。

from_dict的相对路径以base_dir为基准，省略时使用当前工作目录；
load_analysis_plan以各定义的声明文件所在目录为基准，一层imports先展开。路径只转换为绝对定位，不读取目标。
配置字典和列表会复制并冻结，调用者之后修改原配置不会改变计划快照。

当前计划支持的来源由parse_sources检查；预设先校验角色并合入公共节点；尚未接入的旧profile、
旧完整积分兼容和未接入原始输出格式会被拒绝。message_calculations仅显式
current_message-v1逐消息计算；原帧和重建帧统一由can_frames声明。
execution中的预算与outputs中的格式
只是经过检查的声明；实际执行由AnalysisRunner落实，文件发布由AnalysisResult.write负责。
配置通过不表示本次来源已读取、实际结果或输出已经验证。
identity用于区分配置和来源定位声明，不证明磁盘上的输入内容已经核实。

本模块依赖核心声明模型和planning中的字段检查、来源解析及节点解析。
from_dict不读分析数据，按需读取DBC元数据；load_analysis_plan还读取配置及一层公共定义并及时关闭句柄。
"""

# 创建不可变模型并计算声明哈希；语法解析交共享配置入口。
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from collections.abc import Mapping
# 核心模型提供本计划的名称、来源关系和时间范围检查。
from ..core.declarations import DeclarationBindings, DeclaredSource
from ..core.expression import DerivedDefinition, StaticExpression
from .config_groups import public_errors
from .diagnostic_collection import diagnose_plan, current_collection, usable_node, collect_node_error
from ..core.models import Interval
from ..core.types import TimeType
# 固定CAN配置和profile标识只含静态模型，不导入reader、writer或旧依赖。
from ..sources.can_spec import LegacyCANSpec
from ..legacy.records import PROFILE_ID
# 字段、来源和计算节点分别交给对应解析模块。
from ..configuration import load_configuration, ConfigurationError
from ..configuration.diagnostics import locate_error
from .checks import (PlanValidationError, configuration_error, array_at, canonical, choice_at, coordinate_at, json_value,
                     metadata_at, model_at, number_at, object_at, require_json_value, text_at, timezone_at)
from .inputs import parse_sources, parse_signals
from .aggregations import AggregationPlan, parse_aggregations
from .transforms import TemporalTransformPlan, build_transforms
from .lookups import parse_lookups
from .models import DatasetPlan, DerivedPlan, ExecutionPlan, MessageCalculationPlan, CalculationPlan, OutputPlan, RulePlan, SignalPlan, SourcePlan, WindowPlan
from .message_calculations import parse_message_calculations
from .legacy_execution import require_can_decode_scope
from .nodes import expression_at, parse_calculations, parse_rules, parse_windows
from .preset_models import PresetSpec, RoleBinding
from .sequences import SequencePlan, parse_sequences
from .intervals import IntervalPlan, DiagnosticPlan


@dataclass(frozen=True)
class AnalysisPlan:
    """保存一个会话的分析配置，以及静态检查得到的对象。

    通过from_dict或load_analysis_plan构建，依次保存输入来源、信号、派生计算、
    条件规则、窗口与指标。实例字段不能重新赋值；原配置及自由元数据
    保存为独立的只读快照，不保留调用者可变字典或列表的引用。

    bindings只描述“哪个信号来自哪里”，derived_expressions是已检查的
    表达式结构；二者不表示真实数据已经读取或能够直接运行。
    execution与outputs保存执行及输出声明，创建本类不会启动计算或发布文件。

    identity由配置和来源定位声明计算，用于区分计划；不能据此断言CSV内容、
    实际列、内存使用或分析结果已核实。各次构建的绑定和声明相互独立。
    """

    config_version: int  # 当前固定为4；拒绝旧配置，实际能力由已接线节点约束。
    dataset: DatasetPlan  # 分析对象、会话和请求时间范围。
    sources: tuple[SourcePlan, ...]  # 已解析的来源配置，保持用户声明顺序。
    signals: tuple[SignalPlan, ...]  # 原字段与信号名称、类型、单位及有效期声明。
    derived: tuple[DerivedPlan, ...]  # 由已有信号计算的新信号，例如功率及其元数据。
    rules: tuple[RulePlan, ...]  # 已经检查的布尔条件和时序规则。
    windows: tuple[WindowPlan, ...]  # 已检查的活动或时间点窗口，以及所引用的规则。
    calculations: tuple[CalculationPlan, ...]  # 统计指标及其范围、计算口径、单位和缺失数据策略。
    presets: tuple[PresetSpec, ...]  # 原预设v1声明，冻结并保留生成参数。
    preset_bindings: tuple[tuple[RoleBinding, ...], ...]  # 本次解析角色的原定义与契约，不继承旧来源。
    execution: ExecutionPlan  # 计算方式、分批大小和资源预算声明，尚未实际执行。
    outputs: OutputPlan  # 结果表及清单的格式声明，尚未写出文件。
    bindings: DeclarationBindings  # 名称与来源之间的声明关系，不含实际读取的信号值。
    derived_expressions: tuple[StaticExpression, ...]  # 全部派生表达式的检查结果，已拒绝循环依赖。
    metadata: Mapping  # 调用者附加的只读元数据，不改变计算规则。
    raw_config: Mapping  # 原配置的独立只读副本。
    base_dir: Path  # 相对来源路径的解释基准，保存为绝对路径。
    identity: str  # 配置及来源定位声明的SHA-256哈希，不是文件内容哈希。
    message_calculations: tuple[MessageCalculationPlan, ...] = ()  # 显式当前消息计算；旧位置参数及缺省行为保留。
    sequences: tuple[SequencePlan, ...] = ()  # 可选点事件FIFO配对；旧计划不增加结果表。
    intervals: 'IntervalPlan | None' = None  # 当前记录流的有限间隔声明。
    diagnostics: 'DiagnosticPlan | None' = None  # 分别声明追溯、完整性检查与现场留存。
    aggregations: tuple[AggregationPlan, ...] = ()  # 仅配置后消费必要结果及总体证据。
    transforms: tuple[TemporalTransformPlan, ...] = ()  # 依赖在前的离散分析序列。

    def __post_init__(self):
        """拒绝直接构造或replace得到的旧版本计划，不只检查字典入口。"""
        from ..core.unit_conversion import require_config_version
        require_config_version(self.config_version)

    @property
    def extensions(self):
        """读取计划使用的宿主注册。参数: 无。返回: ExtensionRegistry或None。异常: 无。"""
        return self.bindings.extensions

    @property
    def lookups(self):
        """读取本配置声明的标定表。参数: 无。返回: LookupTablePlan 元组。异常: 无。"""
        return self.bindings.lookups

    @classmethod
    @public_errors
    @diagnose_plan
    def from_dict(cls, config: dict, *, base_dir: Path | str | None = None, extensions=None) -> 'AnalysisPlan':
        """复制配置字典，按唯一支持的版本4检查静态要求；执行能力由所选后端决定。

        参数:
            extensions: 仅宿主 Python 可提供的不可变 ExtensionRegistry。省略时只识别内置操作。
            config (dict): 使用Python原生字典、列表和标量的分析声明；可由YAML加载取得。
                必填config_version、dataset、sources、signals；derived、rules、windows、
                sequences、calculations、message_calculations、presets、execution、outputs、
                intervals、diagnostics和metadata按需提供。版本4可用lookups声明标定表。
                字段、名称、表达式和引用都按对应规则检查。
            base_dir (Path | str | None): 相对来源路径的解释基准；默认None，
                使用当前工作目录。传入Path或文本时转换为绝对路径。
        返回:
            AnalysisPlan: 保存经过静态检查的来源、信号及计算节点。
                raw_config和metadata是独立的只读快照；创建计划不读取分析数据。
        异常:
            PlanValidationError: 字段或版本不合法，名称冲突、表达式或引用错误，
                输入模型不合规，或配置请求尚未接入的能力；错误保留配置位置。
            OSError: 获取当前工作目录或转换路径时发生系统错误，可原样传播。
        处理流程:
            1. 检查顶层字段、复制JSON结构，并核对当前配置结构版本。
            2. 解析来源、会话范围和信号声明，建立本计划的名称与来源关系。
            3. 检查全部派生表达式、规则、窗口、指标及执行和输出选项。
            4. 计算声明哈希并返回计划；此阶段不打开来源文件或执行分析。
        """
        # 先检查顶层必填项和允许项；附加信息只能放在metadata中。
        if type(config) is dict and 'imports' in config:
            raise PlanValidationError('$.imports','from_dict不读取公共定义文件','unresolved_imports',
                                      hint='使用load_analysis_plan加载配置文件，或传入config resolve展开后的字典')
        collection = current_collection()
        if type(config) is not dict or any(key not in config for key in ('config_version','dataset','sources','signals')):
            collection.finish()
        root = config
        # 复制并冻结配置，拒绝非JSON值、非有限数和非文本键。
        # 先保留原JSON类型及循环诊断，再冻结，避免tuple被隐式转为合法数组。
        require_json_value(root, '$')
        frozen = metadata_at(root, '$')
        # 用副本继续解析，避免调用者之后修改原配置影响本次检查。
        root = json_value(frozen)
        from .config_groups import normalize_configuration
        with collection.stage('$', check=False) as ready:
            root = normalize_configuration(root)
        # 当前唯一结构采用记录间隔和按需输出默认值。
        version = None
        with collection.stage('$.config_version') as ready:
            if ready:
                version = choice_at(root['config_version'], (4,), '$.config_version')
        lookups = ()
        if 'lookups' in root:
            with collection.stage('$.lookups', requires=version is not None) as ready:
                if ready:
                    lookups = parse_lookups(root['lookups'], version)
        # 只接受Path或文本路径；这里不读取目标或解析符号链接。
        if base_dir is not None and not isinstance(base_dir, (Path, str)):
            # 拒绝其他对象，避免配置触发自定义路径转换代码。
            raise PlanValidationError('$', 'base_dir必须为Path或文本')
        # 省略base_dir时使用当前工作目录，否则将基准转为绝对路径。
        base = Path.cwd() if base_dir is None else Path(base_dir).absolute()
        # 解析来源配置，保存定位和格式声明；此时仍不打开CSV。
        sources = ()
        with collection.stage('$.sources', requires=True, check=False) as ready:
            if ready:
                sources = parse_sources(root['sources'], base)
        # 以首个来源声明的时钟作为分析基准，多源关系在依赖检查时核对。
        timebase = sources[0].config.timebase if sources else None
        # dataset只接受规定的单对象、单会话和时间范围字段。
        dataset = None
        with collection.stage('$.dataset', requires=bool(sources), check=True) as ready:
            if ready:
                raw_dataset = object_at(root['dataset'], '$.dataset', ('name',), ('entity', 'session', 'domain', 'metadata'))
                # 检查数据集名称，避免把路径或表达式当作标识。
                dataset_id = text_at(raw_dataset['name'], '$.dataset.name', identifier=True)
                # 普通单任务沿用数据集名；对象与会话仍由本次计划实例隔离，不共享状态。
                entity = text_at(raw_dataset.get('entity', dataset_id), '$.dataset.entity', identifier=True)
                session = text_at(raw_dataset.get('session', dataset_id), '$.dataset.session', identifier=True)
                # 省略domain是真正的无时间筛选声明，不制造假端点或实际观测范围。
                domain_explicit = 'domain' in raw_dataset
                domain = None
                if domain_explicit:
                    # 只有用户显式请求时间域才解析坐标；显式null仍是配置错误。
                    raw_domain = object_at(raw_dataset['domain'], '$.dataset.domain', ('start', 'end'))
                    tz = timezone_at(sources[0].timezone_text, '$.dataset.domain.timezone')
                    start = coordinate_at(raw_domain['start'], '$.dataset.domain.start', absolute=timebase.time_type is TimeType.ABSOLUTE, tz=tz)
                    end = coordinate_at(raw_domain['end'], '$.dataset.domain.end', absolute=timebase.time_type is TimeType.ABSOLUTE, tz=tz)
                    domain = model_at(Interval, '$.dataset.domain', start, end)
                # 保存对象、会话、范围和只读元数据，供后续引用。
                dataset = DatasetPlan(dataset_id, entity, session, domain, timebase,
                    metadata_at(raw_dataset.get('metadata', {}), '$.dataset.metadata'), domain_explicit)
        # 检查每个信号的原字段、类型、单位转换、有效期和来源定位。
        signals = ()
        with collection.stage('$.signals', requires=bool(sources) and version is not None, check=False) as ready:
            if ready:
                from .dbc_defaults import requested_enum_codes
                signals = parse_signals(root['signals'], sources, config_version=version,
                                        enum_codes=requested_enum_codes(root))
        # 延迟导入避免公开预设直接导入时产生模块循环；只对局部副本展开，无来源I/O。
        from ..presets import expand_presets
        presets, preset_bindings = (), ()
        with collection.stage('$.presets', requires=not root.get('presets') or collection.usable('$.signals')) as ready:
            if ready:
                presets, preset_bindings = expand_presets(root, tuple(item.definition for item in signals))
        # 派生项按名称组织；类型由表达式推导，不单独指定有效期。
        raw_derived = root.get('derived', {})
        # 派生项必须是名称到配置的字典，不能由数组位置猜名称。
        if type(raw_derived) is not dict:
            raw_derived = {}
        # 保持用户声明顺序，收集已经检查的派生项。
        derived = []
        # 逐项检查字段与元数据；收集完成后再检查整个表达式依赖图。
        for name, item in raw_derived.items():
            # 记录当前派生项的配置位置，供错误信息定位。
            path = f'$.derived.{name}'
            # 先检查名称是否合法；表达式别名不能包含属性访问语法。
            if not usable_node(path, {'name': name}):
                continue
            try:
                text_at(name, path, identifier=True)
                # 只接受规定的表达式、单位和可选语义字段，拒绝未知字段。
                item = object_at(item, path, ('expr',), ('unit', 'semantic_id', 'semantic_contract_version', 'sign_convention', 'measurement_location', 'metadata'))
                # 建立派生声明，由核心检查表达式文本和单位是否有效。
                unit = text_at(item['unit'], path + '.unit') if 'unit' in item else None
                definition = model_at(DerivedDefinition, path, name, item['expr'], unit)
                # 保存可选语义信息；名称相同不能证明测量含义一致。
                annotations = tuple(text_at(item[key], path + '.' + key) if key in item else None for key in ('semantic_id', 'semantic_contract_version', 'sign_convention', 'measurement_location'))
                # 保存只读元数据；表达式不能通过对象属性访问这些信息。
                derived.append(DerivedPlan(definition, *annotations, metadata_at(item.get('metadata', {}), path + '.metadata')))
            except PlanValidationError as error:
                collect_node_error(error, path, {'name': name})
        # 将来源名称、时钟、定位声明和偏移组合为检查用对象。
        declared_sources = tuple(DeclaredSource(item.name, item.config.timebase, item.input_identity, item.config.offset_ns) for item in sources)
        # 在当前会话内统一检查来源、信号和派生名称，建立声明关系。
        bindings = None
        with collection.stage('$.signals/derived', requires=dataset is not None and version is not None, check=True) as ready:
            if ready:
                bindings = model_at(DeclarationBindings, '$.signals/derived', dataset.session_id, timebase, dataset.domain, declared_sources,
                                    tuple(item.definition for item in signals), tuple(item.definition.name for item in derived),
                                    config_version=version, lookups=lookups, extensions=extensions)
        # 检查所有派生定义，包括未被引用的项，拒绝未知名称或循环依赖。
        definitions = tuple(item.definition for item in derived)
        transforms = ()
        if 'transforms' in root:
            with collection.stage('$.transforms', requires=bindings is not None) as ready:
                if ready:
                    bindings, transforms = build_transforms(root['transforms'],bindings,definitions,
                        timezone=timezone_at(sources[0].timezone_text,'$.transforms.origin'))
        # 保存已经检查的表达式结构，不把配置文本当作Python代码执行。
        expressions_list = []
        collection.checking_derived = True
        for item in definitions:
            previous_count = len(expressions_list)
            with collection.stage(f'$.derived.{item.name}', requires=bindings is not None) as ready:
                if ready:
                    expressions_list.append(expression_at(item.name, f'$.derived.{item.name}.expr', bindings, definitions, unit=item.unit))
            if len(expressions_list) == previous_count:
                collection.invalid_names.add(item.name)
        expressions = tuple(expressions_list)
        collection.checking_derived = False
        if not collection.errors:
            # 运行侧保留完整绑定身份；逐项隔离检查只用于定位错误，不能流入执行器。
            expressions = tuple(expression_at(item.name, f'$.derived.{item.name}.expr', bindings, definitions, unit=item.unit) for item in definitions)
        # 坏派生项已单列；无关规则不因编译器扫描整个派生集合而重复收到同一个错误。
        definitions = tuple(item for item in definitions if item.name not in collection.invalid_names)
        # 逐项检查执行选项及默认值；资源预算由实际执行器落实。
        execution = None
        with collection.stage('$.execution', requires=True, check=True) as ready:
            if ready:
                raw_execution = object_at(root.get('execution', {}), '$.execution', (), ('backend', 'batch_rows', 'memory_budget_bytes', 'result_buffer_rows', 'partial_policy', 'on_budget_exceeded', 'spool_quota_bytes'))
                # 只允许'numpy'或'reference'，不为未知实现名称自动回退。
                backend = choice_at(raw_execution.get('backend', 'numpy'), ('numpy', 'reference'), '$.execution.backend')
                # 分批行数、内存预算和结果缓冲行数必须为正整数，不能是布尔值。
                limits = tuple(number_at(raw_execution.get(key, default), '$.execution.' + key, integer=True, minimum=1) for key, default in (('batch_rows', 65536), ('memory_budget_bytes', 268435456), ('result_buffer_rows', 4096)))
                # 检查数据覆盖不完整时采用'report'还是'strict'策略。
                partial = choice_at(raw_execution.get('partial_policy', 'report'), ('report', 'strict'), '$.execution.partial_policy')
                # 超出资源预算的处理只接受'error'，不允许静默丢数据。
                choice_at(raw_execution.get('on_budget_exceeded', 'error'), ('error',), '$.execution.on_budget_exceeded')
                # 磁盘配额若给出则必须为正整数；None表示没有配置该配额。
                quota = number_at(raw_execution['spool_quota_bytes'], '$.execution.spool_quota_bytes', integer=True, minimum=1) if raw_execution.get('spool_quota_bytes') is not None else None
                # 保存检查后的执行选项，包含本次实际采用的默认值。
                execution = ExecutionPlan(backend, *limits, partial, quota)
        # 规则、窗口和指标共用标识集合，避免同一计划出现重复ID。
        ids = {t.name for t in transforms}
        # 先检查条件和规则，供窗口按当前规则名称建立引用。
        rules = ()
        with collection.stage('$.rules', requires=bindings is not None, check=False) as ready:
            if ready:
                rules = parse_rules(root.get('rules', []), bindings, definitions, ids)
        # 检查活动合并或固定窗口的边界与引用关系。
        windows = ()
        with collection.stage('$.windows', requires=bindings is not None, check=False) as ready:
            if ready:
                windows = parse_windows(root.get('windows', []), rules, ids)
        # 检查指标所用值、条件、统计范围、联合来源依赖和单位。
        calculations = ()
        with collection.stage('$.calculations', requires=bindings is not None and execution is not None, check=False) as ready:
            if ready:
                calculations = parse_calculations(root.get('calculations', []), bindings, definitions, rules, windows, execution, ids)
        # 新消息模式在同一ID空间解析；不向原配置副本补默认，旧plan身份recipe保持。
        message_calculations = ()
        with collection.stage('$.message_calculations', requires=bindings is not None, check=False) as ready:
            if ready:
                message_calculations = parse_message_calculations(root.get('message_calculations', []), sources, bindings, ids)
        sequences = ()
        with collection.stage('$.sequences', requires=bindings is not None, check=False) as ready:
            if ready:
                sequences = parse_sequences(root.get('sequences', []), rules, bindings, ids)
        aggregations = ()
        if 'aggregations' in root:
            with collection.stage('$.aggregations', requires=execution is not None and version is not None) as ready:
                if ready:
                    aggregations = parse_aggregations(root['aggregations'],version,calculations,rules,windows,sequences,execution,ids)
        # 检查结果输出配置，此处仅保存格式，不创建输出文件。
        outputs = None
        with collection.stage('$.outputs', requires=bindings is not None, check=True) as ready:
            if ready:
                raw_outputs = object_at(root.get('outputs', {}), '$.outputs', (), ('tables', 'manifest', 'contributions','signal_csv','can_frames'))
                # 结果表只接受CSV或JSONL，清单只接受JSON。
                outputs = OutputPlan(choice_at(raw_outputs.get('tables', 'readable_csv'), ('readable_csv', 'csv', 'jsonl'), '$.outputs.tables'), choice_at(raw_outputs.get('manifest', 'json'), ('json',), '$.outputs.manifest'),
                    choice_at(raw_outputs.get('contributions', 'none'), ('none', 'full'), '$.outputs.contributions'))
                # 新导出默认关闭；解析只核引用和时间政策，不创建原始读取器或加载DBC。
                from dataclasses import replace
                from .export_options import parse_signal_output,parse_frame_output
                outputs=replace(outputs,signal_csv=parse_signal_output(raw_outputs.get('signal_csv'),signals,windows,sources=sources),
                    can_frames=parse_frame_output(raw_outputs.get('can_frames'),sources,windows))
        # 在构造完整计划前拒绝任何结构/依赖错误，不输出部分可执行对象。
        collection.finish()
        from dataclasses import replace
        # 对配置副本和来源定位声明计算哈希，不读取文件内容。
        identity_parts = {'plan_version': 'config4-static-v1', 'config': frozen, 'sources': [item.input_identity for item in sources]}
        if extensions is not None:
            identity_parts['extensions'] = extensions.identity
        identity = sha256(canonical(identity_parts).encode('utf-8')).hexdigest()
        # 返回完整计划；原配置和附加元数据均保存为独立的只读副本。
        plan = cls(version, dataset, sources, signals, tuple(derived), rules, windows, calculations, presets, preset_bindings, execution, outputs,
                   bindings, expressions, metadata_at(root.get('metadata', {}), '$.metadata'), frozen, base, identity,
                   message_calculations=message_calculations, sequences=sequences, aggregations=aggregations,
                   transforms=transforms)
        # 在全部消费者已确定后解析有限间隔选择，DBC实际周期留运行初始化。
        from .intervals import parse_intervals, parse_diagnostics
        plan = replace(plan, intervals=parse_intervals(root.get('intervals', {}), plan),
                       diagnostics=parse_diagnostics(root.get('diagnostics', {})))
        # 省略范围由同一次读取的实际观测确定，不提前扫描或补造时间端点。
        # 来源策略依赖最终输出与全部节点；完整计划确定后再拒绝不支持的requested组合。
        require_can_decode_scope(plan)
        return plan



def load_analysis_plan(path: Path | str, *, extensions=None) -> AnalysisPlan:
    """读取JSON/YAML配置及一层公共定义，按各自声明目录解释相对来源路径。

    参数:
        extensions: 宿主可选的不可变注册；文件中不能声明或导入代码。
        path (Path | str): 配置文件路径；不接受目录扫描或任意路径对象。
            配置按UTF-8读取，允许文件开头带BOM。
    返回:
        AnalysisPlan: 经过from_dict静态检查的计划。只读取主配置和显式公共定义文件，
            不打开其中声明的日志或CSV；省略信号元数据时按需读取DBC。
    异常:
        PlanValidationError: 路径类型错误、文件读取或编码错误、JSON/YAML语法错误、
            重复键、非有限常量或配置声明错误。加载错误带配置文件定位，
            通过原异常链保留更详细的原因。
    副作用:
        打开指定配置文件，正常或异常退出时均关闭句柄；不写文件。
    """
    # 与from_dict一致，只接受Path或文本配置路径。
    if not isinstance(path, (Path, str)):
        # 类型错误直接定位到配置路径参数。
        raise PlanValidationError('$', '配置路径必须为Path或文本')
    # 转为绝对路径，用于打开指定配置及关联错误位置。
    target = Path(path).absolute()
    # 将文件读取、编码、语法和配置检查错误统一关联到该文件。
    try:
        document = load_configuration(target)
        from ..configuration.imports import expand_document_imports
        document = expand_document_imports(document)
        # 配置文件的词法父目录继续作为相对来源定位基准，不读取来源。
        return AnalysisPlan.from_dict(document.data, base_dir=target.parent, extensions=extensions)
    except ConfigurationError as error:
        raise configuration_error(error) from error
    except PlanValidationError as error:
        raise locate_error(error,document)
    # 包装读取与配置检查异常，并保留原异常链。
    except (OSError, UnicodeError, ValueError, TypeError) as error:
        # 已有配置错误保留错误码，其他加载错误使用'load_error'。
        raise PlanValidationError('$',str(error),'load_error',source=str(target)) from error
