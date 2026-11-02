"""声明积分、样本/时间统计及选择行流的协议，并统一结果状态。

CalculationDefinition说明算子、整数纳秒窗口、输出单位及部分结果政策。
CalculationSeries保存完整时间轴、typed值、可选三值条件、真实更新标志和来源。
CalculationResult保存数值、状态、覆盖率、未知区间和质量原因，使正常零、
无法计算的None及部分结果能明确区分。

输入按零阶保持处理：每个左端值用于直到下一时间的区间，窗口左闭右开，
末点只提供边界，不贡献积分面积。值有效性与条件可判断性分别记录，
UNKNOWN（未知）不能填成FALSE，也不能以零补齐未知区间。

BOOL仅用于duration与select，ENUM仅用于保留标签的select行流。minimum_coverage
单独判断值、条件和请求三种覆盖是否达到门槛，不重写report/strict数值政策。
本模块只检查模型、推导单位并分类结果；面积、时间/样本归约和覆盖时长由
独立的参考与NumPy实现计算。仅依赖标准库和核心模型，不读写文件，
不修改调用者输入，也不保存可变全局状态。
"""

# 冻结协议及默认元数据；不会持有可变任务全局状态。
from dataclasses import dataclass
# 输出数值必须有限，配置单位转换也不猜测。
from math import isfinite
# 精确静态单位因子来自已验证转换表。
from .units import UNIT_TABLE
# 已实现半开区间/来源引用结构。
from .models import Interval, SourceRef
# 标量结果仅用于typed输入协议，不共享参考计算。
from .numeric import ScalarValue
# 类型/质量严格区分，BOOL只允许TRUE时长或原值行流。
from .types import SignalDType as D, QualityFlag as Q
# 明确ID、文本与int64时间协议。
from .validation import require_identifier, require_text
# 精确时间坐标校验，不经float转换。
from ..timebase.conversion import require_int64_ns


@dataclass(frozen=True)
class CalculationDefinition:
    """声明一个指标如何计算，以及对不完整覆盖采用什么政策。

    operation区分integral、明确samples/time极值与均值、BOOL duration及独立select行流。
    window使用左闭右开的整数纳秒范围，允许零长度，但此时不能计算面积。
    partial_policy为report时报告已核实部分，为strict时覆盖不足不返回正常值。
    scope说明窗口属于会话、活动或片段；本类不负责寻找或绑定对应活动。
    实例不可重新赋值，不持有计算进度。
    minimum_coverage为0—1有限比例；只有三种覆盖均达到门槛时覆盖质量充分。
    select输出SelectionRow迭代器，不形成CalculationResult标量或隐式单位转换。
    """

    calculation_id: str  # 当前任务指标唯一简单名称。
    operation: str  # 明确的数值/时长口径或select，select不能当作标量归约。
    window: Interval  # 请求半开ns范围，零长度允许但没有面积。
    partial_policy: str = 'report'  # report部分值，strict覆盖不足为null。
    output_unit: str | None = None  # 明确单位转换，省略时按输入推导。
    scope: str = 'session'  # 区间含义，不将上下文指标写成event指标。
    minimum_coverage: float = 0.0  # 0—1质量门槛，不删除report可核实诊断值。

    def __post_init__(self):
        """验证指标类型/政策/范围，不隐式选择mean口径。

        参数: 无；读取当前冻结声明字段。
        返回: None，保持原请求窗口与scope。
        异常: TypeError/ValueError为ID/窗口/未知算子或政策。
        """
        # 指标身份遵循当前简单名称规则。
        require_identifier(self.calculation_id, 'calculation_id')
        # 未实现算子不能仅声明名就称支持。
        if self.operation not in ('integral', 'sample_minimum', 'sample_maximum', 'sample_mean', 'min_time', 'max_time', 'time_weighted_mean', 'duration', 'select') or not isinstance(self.window, Interval):
            # 只有已接线口径才接受，不开放模糊mean或线性模型。
            raise ValueError('指标需明确已实现算子及Interval')
        # 部分政策必须显式受支持，不默认猜UNKNOWN处理。
        if self.partial_policy not in ('report', 'strict') or self.scope not in ('session', 'event', 'segment'):
            # 原窗口scope不会随片段合并改变。
            raise ValueError('未知partial_policy或scope')
        # 非空单位文本保留大小写。
        if self.output_unit is not None:
            # 没有静默常量映射或工程方向推断。
            require_text(self.output_unit, 'output_unit')
        # 覆盖门槛仅判断质量，bool不能借整数继承关系进入比例。
        if type(self.minimum_coverage) not in (int, float) or not 0 <= self.minimum_coverage <= 1 or not isfinite(self.minimum_coverage):
            raise ValueError('minimum_coverage需0—1有限数值')


@dataclass(frozen=True)
class CalculationSeries:
    """保存一段明确观测范围内的保持值，以及真实样本的证据。

    times_ns严格递增并包含观测首末端；values与各标志均与时间轴等长。
    每个values位置描述从当前时间到下一时间的左闭右开区间，末值仅是点，
    不能贡献面积。零长度观测域只需一个边界点，不外推文件结束后的周期。
    actual_value_updates区分真实数值依赖更新与窗口边界、有效期到期等合成边界；
    条件单独更新不能成为数值样本。conditions保留TRUE、FALSE和UNKNOWN三值，
    diagnostics另存依赖原因；所有值使用同一声明类型与已经归一化的unit。
    字段均为不可变模型或元组，不修改来源，也不保存流式批次状态。
    """

    observation: Interval  # 实际连续分析域，不外推EOF。
    times_ns: tuple[int, ...]  # 严格递增，完整首/末端；零域一点。
    values: tuple[ScalarValue, ...]  # 同一dtype；BOOL用于duration/select，ENUM只用于select。
    actual_value_updates: tuple[bool, ...]  # 同长真实数值依赖更新标志。
    unit: str  # 当前分析值单位，已经归一化，不能重复DBC factor。
    conditions: tuple[ScalarValue, ...] | None = None  # 可选BOOL三值选择。
    diagnostics: tuple[Q, ...] = ()  # 原依赖质量，与逻辑结果质量分开。
    binding_identity: str = 'explicit-synthetic'  # 当前输入执行身份/外部合成声明。
    source_refs: tuple[SourceRef, ...] = ()  # 所有实际依赖原字段关联。

    def __post_init__(self):
        """验证完整域、同长typed列/三值、来源与实际更新协议。

        参数: 无；读取全部冻结输入。
        返回: None；省略diagnostics时仅按输入原因生成元数据。
        异常: TypeError/ValueError/OverflowError为结构/回退/范围/dtype。
        """
        # 输入是已明确分析域和冻结列，不排序或补观测。
        if not isinstance(self.observation, Interval) or not isinstance(self.times_ns, tuple) or not self.times_ns:
            # 没有观测也必须明确零域和边界。
            raise TypeError('CalculationSeries需Interval及非空tuple时间轴')
        # 同长typed输入不能broadcast/truncate。
        if not isinstance(self.values, tuple) or not isinstance(self.actual_value_updates, tuple) or len(self.values) != len(self.times_ns) or len(self.actual_value_updates) != len(self.times_ns):
            # 存储错不降为UNKNOWN。
            raise ValueError('指标时间/值/actual列必须同长tuple')
        # 类型由算子门槛检查，BOOL/ENUM不会隐式形成面积。
        if any(not isinstance(value, ScalarValue) for value in self.values):
            # 无类型对象不能冒充含完整质量的逻辑值。
            raise TypeError('指标输入需typed ScalarValue')
        # 整列不隐式把整数提升为float。
        if any(value.dtype is not self.values[0].dtype for value in self.values) or any(type(flag) is not bool for flag in self.actual_value_updates):
            # 原定义dtype与实际更新布尔协议严格一致。
            raise TypeError('指标dtype需相同且actual需bool')
        # ENUM行流需同一标签域，不混合不同字典的相同编码。
        if any(value.labels != self.values[0].labels for value in self.values):
            raise ValueError('指标枚举标签域必须相同')
        # 当前连续域首末完整，不猜缺失外部边界。
        if self.times_ns[0] != self.observation.start_ns or self.times_ns[-1] != self.observation.end_ns:
            # 请求范围另裁剪，不修改观测域。
            raise ValueError('指标轴首末必须完整覆盖声明观测域')
        # 静态时间协议逐组校验，不承担数值归约。
        for index, time in enumerate(self.times_ns):
            # 相邻差可由已验证Interval跨度保证安全。
            require_int64_ns(time, 'calculation.time_ns')
            # 同时刻原子组只提交一次，不能按顺序采样两次。
            if index and time <= self.times_ns[index-1]:
                # 无默默排序或同刻去重。
                raise ValueError('指标完整时间组必须严格递增')
        # 条件已知FALSE和未知分别typed保存。
        if self.conditions is not None:
            # 未知选择不能以空数组代替。
            if not isinstance(self.conditions, tuple) or len(self.conditions) != len(self.times_ns) or any(not isinstance(value, ScalarValue) or value.dtype is not D.BOOL for value in self.conditions):
                # 错结构属于配置错误，不是全FALSE。
                raise TypeError('条件需同长tuple BOOL ScalarValue')
        # 省略诊断只用原质量元数据，不检测或推算面积。
        if not self.diagnostics:
            # 可决定known逻辑仍需来源质量时由调用者传完整diagnostics。
            object.__setattr__(self, 'diagnostics', tuple(value.quality | (self.conditions[index].quality if self.conditions else Q.NONE) for index, value in enumerate(self.values)))
        # 每组原因必须是合法typed组合。
        if not isinstance(self.diagnostics, tuple) or len(self.diagnostics) != len(self.times_ns) or any(not isinstance(q, Q) for q in self.diagnostics):
            # 不丢掉未识别质量位。
            raise TypeError('诊断需同长tuple QualityFlag')
        # 单位与绑定身份是元数据，不是通用领域目录。
        require_text(self.unit, 'calculation.unit')
        # 当前计划可追溯，不用语法文本代替绑定。
        require_text(self.binding_identity, 'binding_identity')
        # 来源定位必须typed且完整保留。
        if not isinstance(self.source_refs, tuple) or any(not isinstance(ref, SourceRef) for ref in self.source_refs):
            # 无类型路径不可冒充实际信号来源。
            raise TypeError('source_refs需tuple SourceRef')


@dataclass(frozen=True)
class CalculationResult:
    """保存指标值和解释该值所需的窗口、覆盖与质量事实。

    spec保留原请求、政策和统计范围；actual_window给出与真实观测的交集。
    所有duration字段使用整数纳秒，coverage为0—1比例，分母为零时用None。
    value=None表示没有可核实的正常结果，与正常零值不同；status和reason
    共同说明完整、部分或无法判断的结果。值未知和条件未知分别保存区间。
    模型不可重新赋值，只检查事实的一致性，不修补结果或重新计算覆盖时长。
    """

    spec: CalculationDefinition  # 原请求/政策/scope不被EOF重写。
    value: int | float | None  # 正常有限结果、合法零或无法核实null。
    unit: str  # 结果单位，转换已经应用一次。
    status: str  # complete/partial/indeterminate。
    reason: str  # 明确empty_selection/no_observation等原因。
    actual_window: Interval | None  # 与真实域交集，无交集为None。
    window_duration_ns: int  # 实际观测窗口时长。
    value_valid_duration_ns: int  # 可用于本算子的正常数值时长。
    condition_known_duration_ns: int  # 条件可判断时长，无条件等于实际窗口。
    selected_duration_ns: int  # 有效值与TRUE选择交集；duration额外要求主BOOL为TRUE。
    value_coverage: float | None  # 值正常时长/实际窗口，零分母null。
    condition_coverage: float | None  # 条件已知时长/实际窗口。
    requested_coverage: float | None  # 实际窗口/请求窗口。
    valid_sample_count: int  # 真实数值更新且有效并选中的样本数。
    value_unknown_ranges: tuple[Interval, ...]  # 值不可核实范围。
    condition_unknown_ranges: tuple[Interval, ...]  # 条件未知范围，FALSE不在内。
    quality: Q  # 原依赖及计算诊断组合，不以零掩盖未知。
    binding_identity: str  # 当前完整执行输入身份。
    source_refs: tuple[SourceRef, ...]  # 当前实际原字段关联。
    coverage_status: str = 'sufficient'  # sufficient或indeterminate，区别于诊断数值和partial状态。

    def __post_init__(self):
        """校验结果事实一致性，不能构造正常非有限或不可能覆盖。

        参数: 无；读取结果字段，全部duration精确ns。
        返回: None，不更正或补齐错误结果。
        异常: TypeError/ValueError为模型/数值/状态/覆盖/范围矛盾。
        """
        # 结果必须保留真实请求模型，scope与政策不会被重写。
        if not isinstance(self.spec, CalculationDefinition) or not isinstance(self.quality, Q):
            # 必须使用规定的指标定义和质量标记类型。
            raise TypeError('指标结果需CalculationDefinition及QualityFlag')
        # null与正常有限数值分开，bool不当统计值。
        if self.value is not None and (type(self.value) not in (int, float) or type(self.value) is float and not isfinite(self.value)):
            # 不接受NaN/Inf作为可用结果。
            raise ValueError('指标结果需有限原生数值或None')
        # 结果分类只使用已实现政策状态。
        if self.status not in ('complete', 'partial', 'indeterminate'):
            # 不以自由字符串掩盖未知完成状态。
            raise ValueError('未知指标status')
        # 最低覆盖率只给质量判断，不强制删除可核实report结果。
        if self.coverage_status not in ('sufficient', 'indeterminate'):
            raise ValueError('未知coverage_status')
        # 文本元数据不能空或任意对象化。
        require_text(self.reason, 'calculation.reason')
        # 输出单位保留明确数学含义。
        require_text(self.unit, 'calculation.unit')
        # 当前真实执行身份可追溯。
        require_text(self.binding_identity, 'binding_identity')
        # 无观测交集为None，零域不能补周期。
        if self.actual_window is not None and not isinstance(self.actual_window, Interval):
            # 原请求与实际观测必须有typed范围。
            raise TypeError('actual_window需Interval或None')
        # 所有时长/计数是非负原生整数。
        durations = (self.window_duration_ns, self.value_valid_duration_ns, self.condition_known_duration_ns, self.selected_duration_ns, self.valid_sample_count)
        # 不把浮点秒数塞进ns字段。
        if any(type(value) is not int or value < 0 for value in durations):
            # 布尔计数也不允许。
            raise TypeError('指标时长及计数需非负原生int')
        # 覆盖不能超过实际观测范围。
        if self.value_valid_duration_ns > self.window_duration_ns or self.condition_known_duration_ns > self.window_duration_ns or self.selected_duration_ns > min(self.value_valid_duration_ns, self.condition_known_duration_ns):
            # 不自动裁剪不可信结果。
            raise ValueError('指标覆盖时长不一致')
        # 实际区间长度必须等于保存的观测窗口时长。
        if self.window_duration_ns != (0 if self.actual_window is None else self.actual_window.end_ns-self.actual_window.start_ns):
            # 没有观测不能声称正覆盖。
            raise ValueError('actual_window与window_duration矛盾')
        # 比例为有限0—1或明确零分母null。
        for coverage in (self.value_coverage, self.condition_coverage, self.requested_coverage):
            # 不用NaN代表零分母。
            if coverage is not None and (type(coverage) is not float or not isfinite(coverage) or not 0 <= coverage <= 1):
                # 正常JSON结果可无歧义表达。
                raise ValueError('coverage需0—1有限float或None')
        # 诊断范围与来源必须保持冻结typed结构。
        if any(not isinstance(ranges, tuple) or any(not isinstance(interval, Interval) for interval in ranges) for ranges in (self.value_unknown_ranges, self.condition_unknown_ranges)):
            # 未知不以自由字符串或被吞空数组代替。
            raise TypeError('未知范围需tuple Interval')
        # 原字段身份不可被自由路径文本冒充。
        if not isinstance(self.source_refs, tuple) or any(not isinstance(ref, SourceRef) for ref in self.source_refs):
            # 不从另一个运行全局对象继承来源。
            raise TypeError('结果来源需tuple SourceRef')


def calculation_unit(spec, input_unit):
    """根据算子和输入单位推导结果单位，并给出一次输出转换因子。

    参数:
        spec: CalculationDefinition，提供算子和可选output_unit；input_unit为当前分析值单位。
    返回:
        (unit, factor)元组。unit为输出标签，factor为最终结果需乘的float因子。
        积分按秒累计；未注册单位保留input_unit + '*s'，不猜测工程意义。
    异常:
        ValueError: 要求的单位不在同一已知维度，转换未注册或因子非有限。
    边界:
        例如功率积分推导能量单位；输入工程单位已由上游完成转换，本函数
        不重复DBC缩放。转换仅在最终结果处应用一次，方向符号不在这里推断。
    """
    # 零阶保持积分将区间值乘以时长（秒），常见结果单位按数学维度推导。
    base = input_unit
    # 输入单位已是分析值单位；乘秒的维度转换不重复输入factor。
    input_factor = 1.0
    # TRUE时长只输出秒，布尔值不能借数值单位转换形成电量或面积。
    if spec.operation == 'duration':
        if input_unit != '1' or spec.output_unit not in (None, 's'):
            raise ValueError('duration需无量纲BOOL输入及s输出')
        return 's', 1.0
    # 积分仅对已注册类别推导，其他保留明确乘秒标签。
    if spec.operation == 'integral':
        # 已核实power/current/dimensionless类别的基准面积单位。
        category = UNIT_TABLE[input_unit][0] if input_unit in UNIT_TABLE else None
        # 同类别明确单位因子来自静态Fraction表，不凭文本前缀猜测。
        base = {'power': 'J', 'current': 'A·s', 'dimensionless': 's'}.get(category, input_unit + '*s')
        # 只有已推导的数学类别需要乘基准倍率。
        if category in ('power', 'current', 'dimensionless'):
            # 例如kW*s→J为1000，不是再对原行重复DBC缩放。
            input_factor = float(UNIT_TABLE[input_unit][1])
    # 缺省按声明维度输出，不猜Ah或充放电名称。
    target = spec.output_unit if spec.output_unit is not None else base
    # 相同单位没有多余转换。
    if target == base:
        # 不重复旧DBC缩放。
        return target, input_factor
    # 已知维度才能转换，未知文本不当已核实单位。
    if base not in UNIT_TABLE or target not in UNIT_TABLE or UNIT_TABLE[base][0] != UNIT_TABLE[target][0]:
        # 不静默猜测输入已经积分或单位前缀。
        raise ValueError(f'指标单位不能明确转换：{base}→{target}')
    # 静态Fraction比例只做显式配置转换。
    factor = input_factor * float(UNIT_TABLE[base][1] / UNIT_TABLE[target][1])
    # 配置因子也必须正常有限。
    if not isfinite(factor):
        # 不让坏配置进入数值UNKNOWN。
        raise ValueError('指标单位转换非有限')
    # 输出转换仅在最终值处一次应用。
    return target, factor


def merge_ranges(ranges):
    """合并同一种未知证据的相邻区间，仅用于诊断序列化。

    参数: 已排序正Interval序列，不是真实Event序列。
    返回: Interval tuple，不修改原活动/条件或填平已知缺口。
    异常: 模型错误传播，无数值分析副作用。
    """
    # 原未知边界完整保留，不跨known缺口。
    result = []
    # 此循环处理输出诊断区间，不是NumPy数值内核。
    for interval in ranges:
        # 只同类相邻未知范围可紧凑表示。
        if result and result[-1].end_ns == interval.start_ns:
            # 不改变选中集或真实活动边界。
            result[-1] = Interval(result[-1].start_ns, interval.end_ns)
        else:
            # 中间有已知部分时必须保留独立范围。
            result.append(interval)
    # 不返回可变内部诊断列表。
    return tuple(result)


def classify_calculation_value(spec, value, observed_duration_ns, known_duration_ns, selected_duration_ns,
                          selected_unknown_duration_ns, *, all_false=False, calculation_failed=False):
    """按既有政策分类数值，供完整结果和精简内部结果共用。

    参数: spec为已校验请求；各时长参数均为实际覆盖整数纳秒，value为候选值；
        all_false表示完整已知空选择，calculation_failed表示数值归约失败。
    返回: (value, status, reason)。异常: 内部参数错误原样传播；不构造范围或追溯记录。
    """
    # 请求窗口不随EOF裁剪重写。
    requested_duration_ns = spec.window.end_ns - spec.window.start_ns
    # 无交集明确0，零长度actual仍不是充分观测非零选择。
    # 必要条件未知、选中值未知或请求被裁剪均为不完整。
    incomplete = known_duration_ns < observed_duration_ns or selected_unknown_duration_ns > 0 or observed_duration_ns < requested_duration_ns
    # 正常候选值与结果状态由覆盖政策一起解释。
    status, reason = 'complete', 'ok'
    # 零请求不能借全FALSE返回正常0。
    if requested_duration_ns == 0:
        # 无面积与无选择充分观测严格分开。
        value, status, reason = None, 'indeterminate', 'zero_length_window'
    # 有请求但没有实际连续观测。
    elif observed_duration_ns == 0:
        # 不把空数组sum的0当真值。
        value, status, reason = None, 'indeterminate', 'no_observation'
    # 非有限归约/转换不能报正常结果。
    elif calculation_failed:
        # 保留覆盖/原因，但数值不能使用。
        value, status, reason = None, 'indeterminate', 'calculation_failed'
    # 完整观测且条件始终为FALSE时，积分为零，样本统计保留None。
    elif all_false and observed_duration_ns == requested_duration_ns:
        # 输入数值无效诊断仍保留，不是结果需要的选中值未知。
        value, reason = (0.0, 'empty_selection') if spec.operation in ('integral', 'duration') else (None, 'empty_selection')
    # 没有可核实选中数据，不区分真假补零。
    elif value is None:
        # 已知无样本/全未知/条件未知原因明确。
        status, reason = 'indeterminate', 'unknown_selection' if known_duration_ns < observed_duration_ns else 'no_samples' if spec.operation != 'integral' and selected_duration_ns > 0 else 'no_valid_selected_data'
    # 有候选部分值仍按政策附明确状态。
    elif incomplete:
        # strict不返回部分正常值，但事实覆盖照常保存。
        status, reason = ('indeterminate', 'insufficient_coverage') if spec.partial_policy == 'strict' else ('partial', 'partial_coverage')
        # report保留已核实部分面积/样本统计。
        if spec.partial_policy == 'strict':
            # 不用零填补unknown或EOF外时间。
            value = None
    return value, status, reason


def classify_coverage(spec,observed_duration_ns,value_duration_ns,known_duration_ns):
    """只在请求门槛时判断三种真实覆盖，不影响report/strict的数值政策。

    参数: spec及已有实际范围/有效/已知时长。返回: sufficient或indeterminate。
    异常: 无主动异常；内部量由各数值核独立求得，不构造区间明细。
    """
    requested_duration_ns=spec.window.end_ns-spec.window.start_ns
    ratios=(value_duration_ns/observed_duration_ns if observed_duration_ns else None,
            known_duration_ns/observed_duration_ns if observed_duration_ns else None,observed_duration_ns/requested_duration_ns if requested_duration_ns else None)
    return 'sufficient' if all(value is not None and value>=spec.minimum_coverage for value in ratios) else 'indeterminate'


def make_calculation_result(spec, series, value, unit, actual, value_duration_ns, known_duration_ns, selected_duration_ns,
                       selected_unknown_duration_ns, sample_count, value_unknown, condition_unknown, quality,
                       *, all_false=False, calculation_failed=False):
    """把独立计算的数值与覆盖事实归类，生成可追溯指标结果。

    参数:
        spec、series: 当前请求和输入；value为候选值，unit为结果单位。
        actual: 请求与观测范围的交集，无交集时为None。
        value_duration_ns、known_duration_ns、selected_duration_ns: 值有效、条件已知、
        有效值与TRUE选择相交的时长，均为整数纳秒；时长计算还要求主BOOL为TRUE。
        selected_unknown_duration_ns: 条件TRUE但值未知的时长，单位为纳秒。
        sample_count: 已选真实有效样本数；value_unknown、condition_unknown为未知区间。
        quality: 完整质量原因；all_false默认False，表示是否已有全程FALSE证据。
        calculation_failed: 默认False，表示归约或输出转换是否失败。
    返回:
        CalculationResult，保留覆盖、来源与原因。完整观测且全程FALSE时积分为零，
        空选择的样本统计为None；其他缺失情形不能据空归约推断正常零。
    异常:
        输出事实不满足CalculationResult要求时传播模型的TypeError或ValueError。
    流程:
        先判断零窗口、无观测和计算失败，再处理空选择与未知数据；
        有部分候选值时，report保留并标partial，strict清为None。
        本函数不计算积分或样本归约，各时长和候选值由调用者独立计算。
    """
    # 与精简内部结果共享分类；只有本完整结果入口继续构造覆盖明细。
    requested_duration_ns = spec.window.end_ns - spec.window.start_ns
    observed_duration_ns = 0 if actual is None else actual.end_ns - actual.start_ns
    value, status, reason = classify_calculation_value(spec, value, observed_duration_ns, known_duration_ns,
        selected_duration_ns, selected_unknown_duration_ns, all_false=all_false, calculation_failed=calculation_failed)
    # 三种既定覆盖率同时满足质量门槛才充分；零分母保持无法判断。
    coverages = (value_duration_ns / observed_duration_ns if observed_duration_ns else None,
                 known_duration_ns / observed_duration_ns if observed_duration_ns else None,
                 observed_duration_ns / requested_duration_ns if requested_duration_ns else None)
    coverage_status = 'sufficient' if all(item is not None and item >= spec.minimum_coverage for item in coverages) else 'indeterminate'
    # 最低门槛不改动以上数值政策或事实时长。
    return CalculationResult(spec, value, unit, status, reason, actual, observed_duration_ns, value_duration_ns, known_duration_ns,
                        selected_duration_ns, value_duration_ns / observed_duration_ns if observed_duration_ns else None,
                        known_duration_ns / observed_duration_ns if observed_duration_ns else None, observed_duration_ns / requested_duration_ns if requested_duration_ns else None,
                        sample_count, merge_ranges(value_unknown), merge_ranges(condition_unknown), quality,
                        series.binding_identity, series.source_refs, coverage_status)
