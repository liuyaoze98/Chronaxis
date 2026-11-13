"""保存配置解析得到的来源、信号、计算节点和执行选项声明。

配置解析器先检查字段与引用，再构造本模块的冻结数据类；调用者的自由
元数据在解析边界复制为只读快照。输出记录分析对象、会话范围、来源定位、
显式信号转换、条件规则、窗口、统计指标、当前消息计算及预算和输出格式。
当前消息计算明确新policy，不表示旧完整触发/cache兼容。本层不读取数据、
不调用旧reader或DBC，也不运行表达式。
规则、窗口与预算是配置声明；实际可用能力由计划报告另行说明。
"""

# 冻结数据类及明确元数据映射接口。
from dataclasses import dataclass, field
from collections.abc import Mapping
# 核心模型提供信号契约、静态表达式、时钟和内存来源声明。
from ..core.binding import SignalDefinition
from ..core.expression import DerivedDefinition, ExprNode, StaticExpression
from ..core.message_binding import ExpressionParameter, MessageDeclarations
from ..core.models import Interval, SourceSpec, TimebaseSpec
from ..core.types import SignalDType
from ..core.validation import require_identifier, require_text
from ..core.window_delta import WindowDeltaSpec
from ..core.stability import StabilitySpec
from ..core.start_end import StartEndSpec
# CSV/CAN仅导入静态配置，不实例化适配器、旧worker或打开文件。
from ..sources.csv_spec import SignalCSVSpec
from ..sources.can_spec import LegacyCANSpec
from ..sources.text_can_spec import CANTextSpec
from ..legacy.records import PROFILE_ID, normalize_frame_id
from ..legacy.disjunction import LegacyDisjunction
from .export_options import SignalCSVOutput,CANFramesOutput


@dataclass(frozen=True)
class DatasetPlan:
    """保存单个分析对象、会话及请求时间范围。

    dataset_id与entity命名数据集和对象，session_id确定会话。
    domain是用户请求的左闭右开区间，不证明实际输入已覆盖该范围。
    domain_explicit区分用户时间筛选与domain=None的整文件声明；后者不能
    当作观测时间或向运行结果报告为已采集范围。
    timebase保存来源声明确定的分析时钟，metadata保存只读附加信息。
    实例字段冻结，不维持运行状态。
    """

    dataset_id: str  # 单计划数据集ID。
    entity: str  # 分析对象ID，不内置车辆含义。
    session_id: str  # 当前单会话ID。
    domain: Interval | None  # 用户请求半开范围；None为整文件无筛选，不能当作实际空范围。
    timebase: TimebaseSpec  # 同步分析基准。
    metadata: Mapping  # 深冻结自由JSON元数据。
    domain_explicit: bool = True  # 旧位置构造保留显式请求；False仅供合格整文件消息任务。


@dataclass(frozen=True)
class SourcePlan:
    """保存一个已支持来源种类的配置和定位声明。

    name是唯一来源名，source_type区分memory、signal_csv、can_blf、can_asc和raw_can_csv。
    config保存对应静态来源规格，文本CAN使用CANTextSpec，供实际适配器构造。
    time_unit与timezone_text记录时间表示；input_identity规范记录路径顺序、
    格式和时间映射声明，不能证明文件内容。metadata是只读自由元数据。
    CSV/BLF/DBC尚未打开，实际列、单位与范围留待读取核实；不创建适配器或持有句柄。
    """

    name: str  # 当前唯一来源名。
    source_type: str  # 来源类型，由配置解析器检查允许的格式。
    config: SourceSpec | SignalCSVSpec | LegacyCANSpec | CANTextSpec  # 对应memory/信号表/旧BLF/新文本CAN。
    time_unit: str  # 原时间表示单位。
    timezone_text: str | None  # 明确声明原时区文本。
    input_identity: str  # 规范来源配置，包含路径顺序/格式/时间映射。
    metadata: Mapping  # 深冻结自由元数据。


@dataclass(frozen=True)
class SignalPlan:
    """保存一个原字段到简单表达式别名的显式信号定义。

    definition包含原字段、类型、单位、转换和valid_for_ns有效期等契约。
    有效期是有效样本最多保持的时长；None表示等待运行启动读取DBC周期，
    不能用于计算状态。实际过期判断由时间驱动层按真实更新时间执行。
    metadata独立冻结，不改变转换或基础质量规则。本类不保存信号值。
    """

    definition: SignalDefinition  # 已校验归一化/保持契约。
    metadata: Mapping  # 自由键不会修改基础质量政策。


@dataclass(frozen=True)
class DerivedPlan:
    """保存由已有信号计算的新信号声明及可选语义信息。

    definition保存名称、表达式和显式单位，类型由表达式静态检查推断。
    semantic_id和semantic_contract_version声明语义及版本，sign_convention
    与measurement_location声明方向及位置；这些字段不证明角色已核实。
    metadata为只读附加信息。派生值不能另行声明更长有效期或覆盖推断类型，
    实际有效性仍取决于输入依赖。本类不执行计算。
    """

    definition: DerivedDefinition  # 名称/表达式/显式单位。
    semantic_id: str | None  # 语义文本不是属性路径。
    semantic_contract_version: str | None  # 声明版本不代表角色已验。
    sign_convention: str | None  # 可选调用者方向声明。
    measurement_location: str | None  # 可选调用者位置声明。
    metadata: Mapping  # 深冻结自由JSON。


@dataclass(frozen=True)
class RulePlan:
    """保存持续、边沿、窗口变化量、迟滞和开始/结束规则的静态参数。

    rule_id与rule_type确定规则，condition通常是布尔表达式；window_delta时保存数值signal树。
    minimum_duration_ns与selection_origin仅用于持续条件，表示确认时长和选择起点。
    emit_initial说明初始触发策略；window_duration_ns是start_only的固定抑制时长。
    stability保存防抖时长；exit_condition保存迟滞退出或start_end结束条件。
    start_end保存专用时限/首次策略，不借普通emit_initial启动condition_duration检测器。
    实例不保存状态；迟滞复用普通条件时间线，窗口变化量使用有界历史回读。
    """

    rule_id: str  # 唯一规则ID。
    rule_type: str  # 明确首版规则种类。
    condition: StaticExpression  # 普通BOOL树或window_delta数值树，不能直接执行。
    minimum_duration_ns: int | None  # 仅condition_duration，非负纳秒。
    selection_origin: str | None  # 仅condition_duration的onset/confirmed。
    emit_initial: bool  # 边沿/start_only初始化策略。
    window_duration_ns: int | None  # 仅start_only正抑制窗口。
    window_delta: WindowDeltaSpec | None = None  # window_delta规则的完整回看契约。
    retrigger: str = 'edge'  # edge等待新False→True；once在本会话只触发一次。
    stability: StabilitySpec | None = None  # debounce/hysteresis的独立进入/退出防抖时长。
    exit_condition: StaticExpression | None = None  # hysteresis或start_end的独立退出条件。
    start_end: StartEndSpec | None = None  # 开始/结束的时限与首次启动，追加字段保持旧位置兼容。
    duration_comparison: str = '>='  # 持续条件达到/>门槛，其他规则只能保持默认。

    def __post_init__(self):
        """检查窗口、迟滞和开始/结束规则，保持原字段位置参数兼容。

        参数: 无。返回: None。异常: 新规则类型、配置或普通规则混入专用参数。
        """
        if self.duration_comparison not in ('>=', '>') or (self.rule_type != 'condition_duration' and self.duration_comparison != '>='):
            raise ValueError('duration_comparison仅持续条件支持>=或>')
        if self.rule_type == 'start_end':
            if (not isinstance(self.start_end, StartEndSpec)
                    or not isinstance(self.condition, StaticExpression)
                    or self.condition.root.dtype is not SignalDType.BOOL
                    or not isinstance(self.exit_condition, StaticExpression)
                    or self.exit_condition.root.dtype is not SignalDType.BOOL):
                raise TypeError('start_end需要两个BOOL条件及StartEndSpec')
            if (self.minimum_duration_ns is not None or self.selection_origin is not None
                    or self.emit_initial is not False or self.window_duration_ns is not None
                    or self.window_delta is not None or self.stability is not None or self.retrigger != 'edge'):
                raise ValueError('start_end不能混用其他规则参数')
            return
        if self.start_end is not None:
            raise ValueError('其他规则不接受StartEndSpec')
        if self.rule_type in ('debounce', 'hysteresis'):
            if (not isinstance(self.stability, StabilitySpec)
                    or not isinstance(self.condition, StaticExpression)
                    or self.condition.root.dtype is not SignalDType.BOOL):
                raise TypeError('迟滞/防抖需要BOOL条件及StabilitySpec')
            if self.rule_type == 'hysteresis':
                if not isinstance(self.exit_condition, StaticExpression) or self.exit_condition.root.dtype is not SignalDType.BOOL:
                    raise TypeError('hysteresis需要BOOL退出条件')
            elif self.exit_condition is not None:
                raise ValueError('debounce退出使用not condition，不接受exit_condition')
            if (self.minimum_duration_ns is not None or self.selection_origin is not None
                    or self.emit_initial is not False or self.window_duration_ns is not None
                    or self.window_delta is not None or self.retrigger != 'edge'):
                raise ValueError('迟滞/防抖不能混用其他规则参数')
        elif self.stability is not None or self.exit_condition is not None:
            raise ValueError('普通规则不接受迟滞/防抖参数')
        elif self.rule_type == 'window_delta':
            if (not isinstance(self.window_delta, WindowDeltaSpec)
                    or not isinstance(self.condition, StaticExpression)
                    or self.condition.root.dtype not in (SignalDType.INT64, SignalDType.UINT64, SignalDType.FLOAT64)):
                raise TypeError('window_delta需要数值signal与WindowDeltaSpec')
            if (self.minimum_duration_ns is not None or self.selection_origin is not None
                    or self.window_duration_ns is not None or type(self.emit_initial) is not bool
                    or self.retrigger not in ('edge', 'once')):
                raise ValueError('window_delta参数冲突或重触发策略非法')
        elif self.window_delta is not None or self.retrigger != 'edge':
            raise ValueError('普通规则不接受window_delta或retrigger参数')

    @property
    def temporal_rule_type(self):
        """读取交给事件检测器的类型。参数: 无。返回: str。异常: 无。

        window_delta使用rising_edge；迟滞/防抖确认后的状态使用condition_duration=0活动。
        完整窗口、条件、防抖和开始/结束时限保留在原计划；start_end也输出活动。
        """
        return ('rising_edge' if self.rule_type == 'window_delta' else
                'condition_duration' if self.rule_type in ('debounce', 'hysteresis', 'start_end') else self.rule_type)

    @property
    def expressions(self):
        """列出规则全部静态条件。参数: 无。返回: tuple。异常: 无。

        迟滞退出条件同样参与实际绑定、投影、同步与预算，不遗漏第二个来源。
        """
        return (self.condition,) if self.exit_condition is None else (self.condition, self.exit_condition)

    @property
    def dependencies(self):
        """取得进出条件的去重依赖。参数: 无。返回: 名称tuple。异常: 无。"""
        return tuple(dict.fromkeys(name for expression in self.expressions for name in expression.dependencies))


@dataclass(frozen=True)
class WindowPlan:
    """保存事件的上下文窗口及片段合并声明。

    window_id标识窗口，event引用规则，anchor区分时间点和持续活动。
    pre_ns与post_ns声明前后扩展纳秒范围，merge决定窗口的合并方式。
    exit_delay_ns只用于退出延迟合并，该模式要求活动锚点且post_ns为0。
    声明不会改写原事件边界；实际运行还须保存合并片段的全部父事件身份。
    """

    window_id: str  # 唯一窗口ID。
    event: str  # 当前计划规则ID。
    anchor: str  # point或activity，与规则kind一致。
    pre_ns: int  # 非负请求前扩范围。
    post_ns: int  # 非负请求后扩范围。
    merge: str  # 显式none/overlap/overlap_and_adjacent/exit_delay。
    exit_delay_ns: int | None  # 仅exit_delay模式有效。


@dataclass(frozen=True)
class CalculationPlan:
    """保存要统计的信号、选择条件、范围和结果政策。

    calculation_id标识指标，scope区分全会话、原事件和合并片段的统计范围。
    operation确定选择、积分、时长或统计口径，signal与condition是静态表达式结构。
    unit保存已检查的输出单位，partial_policy规定未知部分如何报告，
    minimum_coverage是覆盖率质量门槛；method仅用于积分，当前为左侧保持'zoh'。
    本类只保存声明，不生成数值或选择行；片段合并不改变原事件的统计范围。
    """

    calculation_id: str  # 唯一指标ID。
    scope: str  # session/event:ID/segment:ID。
    operation: str  # 首版明确算子，不接受模糊mean/min/max。
    signal: StaticExpression | None  # 数值/BOOL信号或派生别名树。
    condition: StaticExpression | None  # 可选BOOL选择或condition_duration条件。
    unit: str  # 已推断/校验输出单位。
    partial_policy: str  # report或strict。
    minimum_coverage: int | float  # 0—1质量判断阈值，不补未知。
    method: str | None  # 仅integral为zoh。
    count_target: str | None = None  # v4对象计数显式引用的规则或窗口名。
    ddof: int | None = field(default=None, kw_only=True)  # 样本/时间方差和标准差的分母选择。
    q: int | float | None = field(default=None, kw_only=True)  # 仅sample_quantile显式指定概率。


@dataclass(frozen=True)
class LegacyMessageSelector:
    """明确选择当前消息计算的CAN帧，不猜旧profile的求值选择器默认。

    通道与ID必须提供，两个帧类型可省略。ID支持整数或带进制文本，不接受bool或
    float；实际记录保留remote/error等标志，消息计算只处理数据帧。
    本声明不读DBC，也不证明该消息在输入中出现。
    """

    channel: int  # 显式声明的原通道。
    frame_id: int  # 原报文ID，不以零代表缺项。
    is_extended: bool | None = None  # 省略时由实际帧确定；不能默认标准帧。
    is_fd: bool | None = None  # 省略时由实际帧确定经典CAN/FD。

    def __post_init__(self) -> None:
        """核原生类型和帧ID范围，不进行输入过滤或DBC查找。

        参数: 无，读取冻结字段。返回: None，ID统一为整数，省略类型保留None。
        异常: TypeError为非法类型；ValueError为ID格式、负通道或ID超相应帧范围。
        """
        if type(self.channel) is not int:
            raise TypeError('消息选择器channel需要原生int')
        object.__setattr__(self, 'frame_id', normalize_frame_id(self.frame_id))
        if any(value is not None and type(value) is not bool for value in (self.is_extended, self.is_fd)):
            raise TypeError('消息选择器is_extended/is_fd需要bool或省略')
        # 不根据数值大小猜帧类型，也不复制旧ChrgInfo对ID0的缺失判断。
        maximum = 0x7FF if self.is_extended is False else 0x1FFFFFFF
        if self.channel < 0 or not 0 <= self.frame_id <= maximum:
            raise ValueError('消息选择器通道或帧ID范围非法')


@dataclass(frozen=True)
class MessageCalculationPlan:
    """保存一个会话内按当前匹配消息逐次求值的明确计算声明。

    expr来自本来源MessageDeclarations，parameters为同一冻结参数tuple。
    operation仅legacy_sum，message_policy必须显式current_message-v1；这里不设置
    旧触发器、跨消息缓存、普通TTL、连续时间覆盖率或事件/片段范围。
    profile标识原解码路径，与新计算policy分别保存，不冒充旧完整兼容。
    可选disjunction只把本条贡献路由到正/负桶；原方向定位关系由计划交叉校验。
    """

    calculation_id: str  # 与rules/windows/普通calculations共用计划ID空间。
    source: str  # 当前单一CAN来源。
    profile: str  # 原解码profile，须与实际来源声明对应。
    operation: str  # 固定legacy_sum，不放入普通CalculationDefinition。
    update_message: LegacyMessageSelector  # 通道/ID必填，帧类型可省略的当前帧选择器。
    expr: StaticExpression  # 逐消息表达式的静态语法树；构建它不会读取或执行分析。
    unit: str  # 一次贡献及累计结果的单位，必须等于表达式结果单位。
    parameters: tuple[ExpressionParameter, ...]  # 原单位、规范FLOAT64参数。
    message_policy: str  # 固定current_message-v1，不能与旧完整cache等义。
    disjunction: LegacyDisjunction | None = None  # 可选原解码方向选择，不进入表达式或TTL。

    def __post_init__(self) -> None:
        """检查固定模式及静态消息表达式的一致性，不打开任何来源。

        参数: 无，读取冻结声明。返回: None，不重编译AST或重建原信号。
        异常: TypeError为模型/容器错误；ValueError为模式、来源、单位或参数冲突。
        """
        require_identifier(self.calculation_id, 'message_calculation.name')
        require_identifier(self.source, 'message_calculation.source')
        require_text(self.unit, 'message_calculation.unit')
        # 末尾缺省保既有位置构造；只有明确冻结选择器才启用分桶。
        if self.disjunction is not None and type(self.disjunction) is not LegacyDisjunction:
            raise TypeError('逐消息disjunction需要LegacyDisjunction或None')
        if (type(self.profile) is not str or self.profile not in (PROFILE_ID, 'can-text-v1')
                or type(self.operation) is not str or self.operation != 'legacy_sum'
                or type(self.message_policy) is not str or self.message_policy != 'current_message-v1'):
            raise ValueError('当前逐消息计算仅支持固定解码profile、legacy_sum及current_message-v1')
        if (type(self.update_message) is not LegacyMessageSelector
                or not isinstance(self.expr, StaticExpression)
                or type(self.expr.bindings) is not MessageDeclarations
                or not isinstance(self.expr.root, ExprNode)
                or type(self.parameters) is not tuple
                or any(type(item) is not ExpressionParameter for item in self.parameters)):
            raise TypeError('逐消息计划需要选择器、消息域StaticExpression及参数tuple')
        # 声明不是原始字符串；保原单位和参数，不能借包装重写编译结果。
        declaration = self.expr.bindings
        if (declaration.source != self.source or declaration.message_policy != self.message_policy
                or declaration.parameters != self.parameters or declaration.derived_names):
            raise ValueError('逐消息计划来源、policy或参数与消息表达式声明不符')
        if self.expr.root.dtype not in (SignalDType.INT64, SignalDType.UINT64, SignalDType.FLOAT64):
            raise ValueError('legacy_sum表达式必须为数值，不接受bool或enum')
        if self.expr.root.unit != self.unit:
            raise ValueError('legacy_sum单位必须与表达式结果一致')


@dataclass(frozen=True)
class ExecutionPlan:
    """保存后端和资源限额，实际执行器负责落实这些声明。

    backend选择'numpy'、'reference'或按静态类别选择的'auto'，batch_rows限制来源批次总样本数。
    memory_budget_bytes声明新分析层内存预算，result_buffer_rows限制结果缓冲，
    spool_quota_bytes声明磁盘暂存配额，None表示没有显式配额。
    partial_policy是全局默认结果政策；on_budget_exceeded当前只允许'error'。
    构造计划不测量内存或磁盘，也不启动运行、暂存或发布。
    """

    backend: str  # numpy、reference或auto；运行前解析为具体后端。
    batch_rows: int  # 来源批次样本上限。
    memory_budget_bytes: int  # 新分析层RAM预算。
    result_buffer_rows: int  # 结果流缓冲上限。
    partial_policy: str  # 全局指标默认部分政策。
    spool_quota_bytes: int | None  # 磁盘配额，None表示未显式限额。
    on_budget_exceeded: str = 'error'  # 首版不丢数据或增加旧扫描。
    process_count: int = 1  # 本次分析读取/解码工作进程上限；不包含主分析进程。




@dataclass(frozen=True)
class OutputPlan:
    """保存新结果表和清单的输出格式声明。

    tables接受普通使用默认'readable_csv'，或供程序使用的'csv'/'jsonl'；manifest使用'json'。
    contributions仅控制逐消息贡献明细，none仍保留统计汇总和其他请求结果；省略为none。
    本类不创建目录或写文件；run生成本次实际原始片段，write只复制已封口输出。
    """

    tables: str  # readable_csv、csv或jsonl；只生成所选的一套表。
    manifest: str  # json。
    contributions: str = 'none'  # 只有明确请求full时生成逐消息贡献明细。
    signal_csv: SignalCSVOutput | None = None  # 显式请求的信号长表，可单独设置线性网格。
    can_frames: CANFramesOutput | None = None  # 显式原帧/重建帧输出，默认不保额外原始数据。
