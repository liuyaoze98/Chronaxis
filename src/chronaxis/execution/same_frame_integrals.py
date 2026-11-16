"""把同一物理报文的简单数值表达式直接交给现役实际时间积分器。

本对象只保存一个待完成同刻组；不构造信号数组、历史或通用最新状态。
读取、DBC投影、范围推进、积分器及结果发布仍由原会话负责。只有首帧前
证明绑定一致的内部调用方使用本入口，运行错误不切换路径或重读输入。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite, isnan
from typing import Callable, Mapping, Sequence, TYPE_CHECKING

from ..core.binding import SignalDefinition
from ..core.expression import validate_expression
from ..core.expression_reference import _evaluate
from ..core.numeric import _exact_float, normalize_reference, ScalarValue
from ..core.scalar import _scalar_from_validated_fields
from ..core.types import QualityFlag as Q, SignalDType as D
from ..legacy.records import field_from_dict
from ..legacy.updates import LegacyDecodedUpdate
from ..planning.backend_selection import simple_numeric_expression
from ..results.budget import ResourceBudget, _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..results.errors import ResultClosedError
from ..sources.can_spec import can_field_from_key
from .history import _metadata_bytes
from .static_metadata import static_metadata_bytes

SAME_FRAME_EVALUATOR_BASE_COST = 196608  # 求值状态固定费用；启动前下界与真实预约共用。

if TYPE_CHECKING:
    from ..core.expression import StaticExpression
    from ..planning.plan import AnalysisPlan
    from .record_integral import RecordIntegral


def direct_integral_inputs(plan: AnalysisPlan) -> tuple[SignalDefinition, ...] | None:
    """检查直接积分的完整静态边界，不读取DBC或数据。

    参数: 已选reference的计划。返回: 本次必要定义tuple；不适用为None。
    异常: 非法typed结构，不把运行错误当成选择其他路径的理由。
    """
    if (plan.execution.backend != 'reference' or plan.extensions is not None
            or plan.rules or plan.windows or plan.sequences or plan.transforms or plan.aggregations
            or plan.message_calculations or not plan.calculations
            or plan.outputs.signal_csv is not None or plan.outputs.can_frames is not None
            or plan.diagnostics.trace or plan.diagnostics.integrity):
        return None
    choices, used = dict(plan.intervals.resolved), set()
    for item in plan.calculations:
        if (item.operation != 'integral' or item.scope != 'session' or item.method != 'zoh'
                or item.condition is not None or not simple_numeric_expression(item.signal)
                or item.calculation_id not in choices or choices[item.calculation_id].mode != 'actual'
                or choices[item.calculation_id].driver is not None):
            return None
        used.update(item.signal.dependencies)
    definitions = tuple(item.definition for item in plan.signals if item.definition.name in used)
    if {item.name for item in definitions} != used or len({item.source for item in definitions}) != 1:
        return None
    source = next((item for item in plan.sources if item.name == definitions[0].source), None)
    if source is None or source.source_type not in ('can_blf', 'can_asc', 'asc_or_blf', 'raw_can_csv'):
        return None
    fields = tuple(can_field_from_key(item.field) for item in definitions)
    if len({(f.channel, f.frame_id, f.is_extended, f.is_fd) for f in fields}) != 1:
        return None
    if any(item.dtype not in (D.INT64, D.UINT64, D.FLOAT64) or item.capture_code for item in definitions):
        return None
    return definitions


@dataclass(frozen=True)
class SameFrameBinding:
    """保存同次DBC证明的共同定位；fd可为None，真实歧义继续由原投影器检查。"""

    source: str  # 当前计划中的来源名称。
    channel: int  # 已转换为内部零起序号的通道。
    frame_id: int  # DBC和原配置共同定位的报文编号。
    extended: bool  # 同次DBC字段事实已经确定的标准/扩展标记。
    fd: bool | None  # 原配置的CAN/FD约束；None保留原投影器的自动识别。
    dbc_fd: bool  # DBC声明的FD属性，沿用经典CAN兼容规则。

    def matches(self, update: LegacyDecodedUpdate) -> bool:
        """匹配已投影更新。参数: 更新。返回: bool。异常: 非法内部对象属性错误。"""
        return (update.source == self.source and update.channel == self.channel
                and update.frame_id == self.frame_id and update.is_extended == self.extended
                and (self.fd is None or update.is_fd == self.fd)
                and (self.dbc_fd or not update.is_fd)
                and not update.is_remote and not update.is_error)


def same_frame_binding(definitions: tuple[SignalDefinition, ...], facts: Sequence[Mapping]) -> SameFrameBinding | None:
    """复用同次DBC字段事实证明唯一共同绑定，不加载文件。

    参数: 实际所需信号定义和metadata.fields。返回: 共同定位或None（交回普通路径）。
    异常: 已有元数据结构损坏；不能将损坏当不支持而吞错。
    """
    if not definitions:
        return None
    by_field = {field_from_dict(dict(fact['locator'])).key: fact for fact in facts}
    chosen = None
    for definition in definitions:
        if definition.dtype not in (D.FLOAT64, D.INT64, D.UINT64) or definition.capture_code:
            return None
        field = can_field_from_key(definition.field)
        fact = by_field.get(definition.field)
        if fact is None:
            return None
        if 'dbc_frames' in fact:
            candidates = tuple(tuple(pair) for pair in fact['dbc_frames'])
        elif field.is_extended is not None and field.is_fd is not None:
            # 显式帧型沿用现有READY结构，不要求读取器增加重复候选字段。
            # 字段事实已由同次DBC核对；仅单向FD兼容时使用已有兼容提示。
            dbc_fd = field.is_fd or 'frame_format_compatibility' in fact
            candidates = ((field.is_extended, dbc_fd),)
        else:
            return None
        if len(candidates) != 1:
            return None
        extended, fd = candidates[0]
        if field.is_extended is not None and field.is_extended != extended:
            return None
        binding = SameFrameBinding(definition.source, field.channel, field.frame_id, extended, field.is_fd, fd)
        if chosen is not None and chosen != binding:
            return None
        chosen = binding
    return chosen


class _NotCompilable(Exception):
    """静态表达式或信号声明不在浮点快速子集内；调用方保留原通用求值。"""


# 快速子集的取值表示：(float, None) 为有效值，(None, QualityFlag) 为无效值及其原因。
# 与参考核相同：无效结果不保留数值，有效float必有限。
_SEQUENCE_SLOT_BYTES = 512 + 16 * _metadata_bytes((1 << 64) - 1)


def _has_shared_composite_nodes(roots):
    """检查闭包递归是否会重复展开同一个复合节点。

    参数: 已校验表达式根节点序列。返回: 存在共享复合子树时为True，否则False。
    异常: 非法内部树的属性错误；不改变合法表达式或求值规则。
    只遍历一次实际节点；共享派生树继续使用原求值核的单次结果缓存。
    """
    seen, pending = set(), list(roots)
    while pending:
        node = pending.pop()
        identity = id(node)
        if identity in seen:
            if node.args:
                return True
            continue
        seen.add(identity)
        pending.extend(node.args)
    return False


def _compile_float_program(node):
    """把全FLOAT64的简单表达式编译为闭包，逐项复刻参考核的数值与质量规则。

    参数: 已校验ExprNode。返回: callable(context)->(value, quality)。
    异常: _NotCompilable为非FLOAT64节点、非简单算子或编译期常量/系数不能精确表示为float。
    规则来源: binary_reference（两侧原因并集、除零DOMAIN_ERROR、非有限NONFINITE）、
        unary_reference、to_float_reference、affine_reference（含纯倍率下溢PRECISION_LOSS）。
    """
    op = node.operator
    if op == 'const':
        if type(node.value) not in (int, float):
            raise _NotCompilable(op)
        value, quality = _exact_float(node.value)
        if quality != Q.NONE:
            raise _NotCompilable('const')
        pair = (value, None)
        return lambda context: pair
    if node.dtype is not D.FLOAT64:
        raise _NotCompilable(node.dtype)
    if op == 'name':
        name = node.name
        return lambda context: context[name]
    if op in ('add', 'sub', 'mul', 'div'):
        left, right = (_compile_float_program(arg) for arg in node.args)

        def binary(context, left=left, right=right, op=op):
            """计算两侧并合并质量。参数: 已归一化上下文及捕获的子程序/算子。

            返回: 有限float与None，或None与原因并集。异常: 内部上下文缺键KeyError。
            """
            a, qa = left(context)
            b, qb = right(context)
            if qa is not None or qb is not None:
                return None, (qa or Q.NONE) | (qb or Q.NONE)
            if op == 'add':
                result = a + b
            elif op == 'sub':
                result = a - b
            elif op == 'mul':
                result = a * b
            else:
                if b == 0:
                    return None, Q.DOMAIN_ERROR
                result = a / b
            if not isfinite(result):
                return None, Q.NONFINITE
            return result, None
        return binary
    if op in ('neg', 'abs', 'to_float'):
        child = _compile_float_program(node.args[0])
        if op == 'to_float':
            return child  # 有效输入已是有限float，to_float_reference原样返回；无效原因原样传播
        negate = op == 'neg'

        def unary(context, child=child, negate=negate):
            """取负值或绝对值。参数: 上下文及捕获的子程序/选择标志。

            返回: 数值质量二元组。异常: 内部上下文缺键KeyError。
            """
            a, qa = child(context)
            if qa is not None:
                return None, qa
            return (-a if negate else abs(a)), None
        return unary
    if op == 'unit_convert':
        child = _compile_float_program(node.args[0])
        scale, offset = node.value
        factor, fq = _exact_float(scale)
        shift, sq = _exact_float(offset)
        if fq != Q.NONE or sq != Q.NONE:
            raise _NotCompilable('unit_convert')

        def affine(context, child=child, factor=factor, shift=shift):
            """执行已编译单位换算。参数: 上下文及捕获的子程序/倍率/偏移。

            返回: 数值质量二元组。异常: 内部上下文缺键KeyError；数值失败作为质量返回。
            """
            number, qa = child(context)
            if qa is not None:
                return None, qa
            result = number * factor + shift
            if not isfinite(result):
                return None, Q.NONFINITE
            if shift == 0 and result == 0 and number != 0 and factor != 0:
                return None, Q.PRECISION_LOSS
            return result, None
        return affine
    raise _NotCompilable(op)


def _float_normalizer(definition):
    """FLOAT64信号的快速归一化：普通有限数直接按原顺序计算value*scale+offset。

    参数: SignalDefinition。返回: callable(raw)->(value, quality)。
    其余情况（缺失、非有限、超宽整数、整数转float丢精度、显式无效值、结果非有限或超范围、
    非数值原值）全部交normalize_reference，结果与原路径相同。
    异常: 内部定义结构不合法时保留原TypeError或ValueError。
    """
    scale, sq = _exact_float(definition.scale)
    offset, oq = _exact_float(definition.offset)
    exact = sq == Q.NONE and oq == Q.NONE and not definition.invalid_values
    bounds = definition.valid_range

    def slow(raw):
        """复用参考归一化。参数: 已解码原值。返回: 数值质量二元组。

        异常: 原值不符合标量协议时保留参考核TypeError。
        """
        value = normalize_reference(definition, raw)
        return (value.value, None) if value.valid else (None, value.quality)

    if not exact:
        return slow

    def normalize(raw):
        """直接换算有限原数值，其他输入交参考核。参数: 已解码原值。

        返回: 数值质量二元组。异常: 不支持的原值结构沿参考核报TypeError。
        """
        kind = type(raw)
        if kind is float:
            if not isfinite(raw):
                return slow(raw)
            number = raw
        elif kind is int and -(1 << 63) <= raw <= (1 << 64) - 1:
            number = float(raw)
            if int(number) != raw:
                return slow(raw)
        else:
            return slow(raw)
        result = number * scale + offset
        if not isfinite(result) or bounds is not None and not bounds[0] <= result <= bounds[1]:
            return slow(raw)
        return result, None
    return normalize


def _same_value(left: ScalarValue, right: ScalarValue) -> bool:
    """沿用同刻事实比较。参数: 归一化标量。返回: bool。异常: 无外部输入转换。"""
    return (left.valid == right.valid and left.quality == right.quality and left.code == right.code
            and type(left.value) is type(right.value)
            and (left.value == right.value or type(left.value) is float and isnan(left.value) and isnan(right.value)))


def _reference_group_values(expressions, definitions, time, context):
    """共用标量表达式及真实TTL求值，既有单进程与文件工作进程使用相同算法。

    参数: expressions为StaticExpression tuple；definitions为信号名到SignalDefinition的映射；
        time为实际纳秒int；context为本组信号名到ScalarValue的映射。
    返回: 生成器，按计算项顺序产生(ScalarValue, int | None)；第二项是有效截止纳秒，
        没有可表示的有限截止时为None，全部表达式完成后自然结束。
    异常: 原表达式求值异常继续传播，不用空值代替错误。
    """
    try:
        cache = {}
        for expression in expressions:
            value = _evaluate(expression.root, context, cache).value
            deadlines = (time + definitions[name].valid_for_ns
                         for name in expression.dependencies if context[name].valid)
            yield value, min((candidate for candidate in deadlines if candidate < (1 << 63)), default=None)
    finally:
        expressions = definitions = context = cache = expression = value = deadlines = None


def same_frame_evaluator_cost(definitions, expressions, derived=()):
    """计算求值器实际预约费用，供首帧前预算选择与构造共用。

    参数: definitions为SignalDefinition tuple；expressions为StaticExpression tuple；
        derived为DerivedDefinition tuple，默认空。
    返回: int，非负的保守预约字节数。异常: 非法静态模型的原类型或属性错误。
    """
    trees = tuple((expr.root, expr.text, expr.normalized_ast, expr.dependencies) for expr in expressions)
    return SAME_FRAME_EVALUATOR_BASE_COST + 64 * static_metadata_bytes((definitions, trees, derived))


class SameFrameEvaluator:
    """共享归一化、表达式和TTL的有限求值器，不归组、不累计面积。"""

    def __init__(self, budget, definitions, expressions, binding, session_id, *, derived=()):
        """验证实际定义与已冻结表达式并预约静态及求值空间。

        参数: budget为ResourceBudget；definitions为SignalDefinition tuple；expressions为StaticExpression tuple；
            binding为SameFrameBinding；session_id为会话名；derived为DerivedDefinition tuple，默认空。
        返回: None，构造新的有限求值owner。
        异常: 参数类型错误时TypeError；定义、绑定或表达式不一致时ValueError；
            预算不足时BudgetExceededError，清理失败附same_frame_evaluator_cleanup_owner。
        """
        self._budget = budget
        self._held_cost = self._fixed_cost = 0
        self._closed = self._closing = False
        self.definitions = self.expressions = self._fields = self._normalizers = None
        self._programs = None
        try:
            if not isinstance(budget, ResourceBudget) or type(definitions) is not tuple or not definitions:
                raise TypeError('同帧求值需要预算及非空定义tuple')
            if type(expressions) is not tuple or not expressions or type(binding) is not SameFrameBinding:
                raise TypeError('同帧求值需要表达式tuple及已证明定位')
            _reserve_owned_ram(self, same_frame_evaluator_cost(definitions, expressions, derived), '_fixed_cost')
            by_name = {item.name: item for item in definitions}
            if len(by_name) != len(definitions) or any(type(item) is not SignalDefinition
                    or item.dtype not in (D.INT64, D.UINT64, D.FLOAT64) or item.capture_code
                    or item.valid_for_ns is None for item in definitions):
                raise ValueError('同帧求值需要唯一数值定义及已知有效期')
            fields = tuple(can_field_from_key(item.field) for item in definitions)
            for definition, field in zip(definitions, fields):
                if (definition.source != binding.source or field.channel != binding.channel
                        or field.frame_id != binding.frame_id
                        or field.is_extended is not None and field.is_extended != binding.extended
                        or field.is_fd != binding.fd):
                    raise ValueError('同帧实际定义与已证明定位不一致')
            for expression in expressions:
                if not simple_numeric_expression(expression):
                    raise ValueError('同帧求值仅接受简单内建数值表达式')
                checked = validate_expression(expression.text, expression.bindings, derived=derived, unit=expression.root.unit)
                if checked != expression or expression.bindings.session_id != session_id:
                    raise ValueError('同帧表达式与当前声明或会话不一致')
                for name in expression.dependencies:
                    declared, actual = expression.bindings.resolve(name), by_name.get(name)
                    if declared.valid_for_ns is None and actual is not None:
                        declared = replace(declared, valid_for_ns=actual.valid_for_ns)
                    if declared != actual:
                        raise ValueError('同帧表达式与实际定义不一致：' + name)
                expression.bindings.require_synchronized(expression.dependencies)
            self.definitions, self.expressions, self._fields = by_name, expressions, fields
            if (all(item.dtype is D.FLOAT64 for item in definitions)
                    and not _has_shared_composite_nodes(expr.root for expr in expressions)):
                try:
                    self._programs = tuple(_compile_float_program(expr.root) for expr in expressions)
                except _NotCompilable:
                    self._programs = None
            self._normalizers = tuple(_float_normalizer(item) for item in definitions) if self._programs else None
        except BaseException as error:
            _cleanup_owner(self, error, 'same_frame_evaluator_cleanup_owner', '同帧求值构造')
            raise
        finally:
            definitions = expressions = derived = trees = by_name = fields = checked = expression = None
            declared = actual = definition = field = binding = None

    def normalize(self, values):
        """归一化一条已投影报文，保留原质量规则。

        参数: values为DBC信号名到本条解码值的映射；本条无效值不沿用上一条。
        返回: tuple[ScalarValue, ...]，与definitions的声明顺序一致。
        异常: 已关闭时ResultClosedError，缺少已证明字段时ValueError；原归一化异常继续传播。
        """
        if self._closed or self._closing:
            raise ResultClosedError('同帧求值器已关闭')
        if any(field.signal not in values for field in self._fields):
            raise ValueError('同帧投影没有交付全部已证明字段')
        result = []
        for index, (definition, field) in enumerate(zip(self.definitions.values(), self._fields)):
            if self._normalizers is not None:
                value, quality = self._normalizers[index](values[field.signal])
                scalar = (_scalar_from_validated_fields(value, D.FLOAT64) if quality is None else
                          _scalar_from_validated_fields(None, D.FLOAT64, False, quality))
            else:
                scalar = normalize_reference(definition, values[field.signal])
                if not scalar.valid:
                    scalar = _scalar_from_validated_fields(None, scalar.dtype, False, scalar.quality)
            result.append(scalar)
        return tuple(result)

    def evaluate(self, time, values):
        """对一个已解决同刻选择的组求值。

        参数: time为实际纳秒int；values为按definitions顺序排列的ScalarValue tuple。
        返回: tuple[tuple[ScalarValue, int | None], ...]，与计算项同序；第二项为有效截止纳秒，
            没有可表示的有限截止时为None。
        异常: 已关闭时ResultClosedError；原表达式求值异常继续传播。
        """
        if self._closed or self._closing:
            raise ResultClosedError('同帧求值器已关闭')
        context = dict(zip(self.definitions, values))
        if self._programs is None:
            return tuple(_reference_group_values(self.expressions, self.definitions, time, context))
        pairs = {name: (value.value, None if value.valid else value.quality) for name, value in context.items()}
        result = []
        for program, expression in zip(self._programs, self.expressions):
            value, quality = program(pairs)
            scalar = (_scalar_from_validated_fields(value, D.FLOAT64) if quality is None else
                      _scalar_from_validated_fields(None, D.FLOAT64, False, quality))
            deadlines = (time + self.definitions[name].valid_for_ns
                         for name in expression.dependencies if context[name].valid)
            deadline = min((candidate for candidate in deadlines if candidate < (1 << 63)), default=None)
            result.append((scalar, deadline))
        return tuple(result)

    def close(self):
        """先解除闭包和声明引用再退款。参数: 无。返回: None。异常: 预算退款失败可重试。"""
        if self._closed:
            return
        self._closing = True
        self.definitions = self.expressions = self._fields = self._normalizers = self._programs = None
        _release_owned_ram(self, self._fixed_cost, '_fixed_cost')
        self._closed = True


class SameFrameIntegrals:
    """拥有同刻选择和表达式上下文；借用积分器，关闭时不代替父会话关闭它们。"""

    def __init__(self, budget: ResourceBudget, definitions: tuple[SignalDefinition, ...],
                 expressions: tuple[StaticExpression, ...], calculations: tuple[RecordIntegral, ...],
                 binding: SameFrameBinding, session_id: str, before_group: Callable[[], None], *, derived: tuple = ()) -> None:
        """检查静态表达式与实定义，预付有界状态，不读取输入。

        参数: 共享预算、已补齐TTL的定义、静态表达式tuple、对应积分器tuple、
            已证明共同定位、会话ID、积分缓冲结算前刷新已观测范围的同步回调；derived为原派生声明。
        返回: owner。异常: 声明/预算/取消；未返回时附same_frame_cleanup_owner。
        """
        if not isinstance(budget, ResourceBudget) or type(definitions) is not tuple:
            raise TypeError('同帧积分需要预算和定义tuple')
        if (type(expressions) is not tuple or type(calculations) is not tuple
                or not expressions or len(expressions) != len(calculations)
                or type(binding) is not SameFrameBinding or not callable(before_group)):
            raise TypeError('同帧积分需要对应表达式/积分器、已证明定位和范围回调')
        self._budget = budget
        self._held_cost = self._fixed_cost = self._group_cost = self._work_cost = 0
        self._closed = self._closing = self._failed = self._finished = False
        self._definitions = self._fields = self._expressions = self._calculations = None
        self._chosen = self._seen = self._before_group = None
        self._time = self._last_time = None
        self._binding, self._session = binding, session_id
        self._fast = False
        self._programs = self._normalizers = self._deps = self._ttl = None
        try:
            # bindings由父计划持有；这里只计校验树、当前字段索引和必要同刻槽。
            trees = tuple((expr.root, expr.text, expr.normalized_ast, expr.dependencies) for expr in expressions)
            _reserve_owned_ram(self, 131072 + 32 * static_metadata_bytes((definitions, trees, derived)), '_fixed_cost')
            by_name = {item.name: item for item in definitions}
            if len(by_name) != len(definitions) or any(type(item) is not SignalDefinition
                    or item.dtype not in (D.INT64, D.UINT64, D.FLOAT64) or item.capture_code
                    or item.valid_for_ns is None for item in definitions):
                raise ValueError('同帧积分需要唯一数值定义及已知有效期')
            fields = tuple((item, can_field_from_key(item.field).signal) for item in definitions)
            for definition in definitions:
                field = can_field_from_key(definition.field)
                if (definition.source != binding.source or field.channel != binding.channel
                        or field.frame_id != binding.frame_id
                        or field.is_extended is not None and field.is_extended != binding.extended
                        or field.is_fd != binding.fd):
                    raise ValueError('同帧实际定义与已证明定位不一致')
            for expression, calculation in zip(expressions, calculations):
                if not simple_numeric_expression(expression):
                    raise ValueError('同帧积分仅接受简单内建数值表达式')
                checked = validate_expression(expression.text, expression.bindings, derived=derived, unit=expression.root.unit)
                if checked != expression or expression.bindings.session_id != session_id:
                    raise ValueError('同帧表达式与当前声明或会话不一致')
                for name in expression.dependencies:
                    declared = expression.bindings.resolve(name)
                    actual = by_name.get(name)
                    if declared.valid_for_ns is None and actual is not None:
                        declared = replace(declared, valid_for_ns=actual.valid_for_ns)
                    if declared != actual:
                        raise ValueError('同帧表达式与实际定义不一致：' + name)
                expression.bindings.require_synchronized(expression.dependencies)
                if (calculation._step_ns is not None or calculation._conditioned
                        or calculation._dtype != expression.root.dtype
                        or calculation._input_unit != expression.root.unit):
                    raise ValueError('同帧表达式与实际时间积分器不一致')
            self._definitions, self._fields = by_name, fields
            self._expressions, self._calculations = expressions, calculations
            self._chosen, self._seen = {}, set()
            self._before_group = before_group
            # 输入原值仍由借用的消息持有；这里只构造数值标量和有限表达式工作区。
            self._workspace = 65536 + 32 * static_metadata_bytes(tuple(expr.root for expr in expressions))
            # 全FLOAT64声明且每个表达式都可编译时启用浮点快速路径；否则保留下面的通用逐帧路径。
            programs = None
            if (all(item.dtype is D.FLOAT64 for item in definitions)
                    and not _has_shared_composite_nodes(expr.root for expr in expressions)):
                try:
                    programs = tuple(_compile_float_program(expr.root) for expr in expressions)
                except _NotCompilable:
                    programs = None
            if programs is not None:
                # 固定工作区和首个同刻槽在生命周期内预留一次，替代逐帧申请/释放；同刻多帧时仍逐帧预付。
                _reserve_owned_ram(self, self._workspace + _SEQUENCE_SLOT_BYTES, '_fixed_cost')
                self._programs = programs
                self._normalizers = tuple((item.name, name, _float_normalizer(item), item.same_time_policy)
                                          for item, name in fields)
                self._deps = tuple(tuple(expr.dependencies) for expr in expressions)
                self._ttl = {item.name: item.valid_for_ns for item in definitions}
                self._fast = True
        except BaseException as error:
            _cleanup_owner(self, error, 'same_frame_cleanup_owner', '同帧积分构造')
            raise
        finally:
            definitions = expressions = calculations = fields = by_name = checked = expression = calculation = trees = None
            definition = declared = actual = field = binding = before_group = derived = programs = None

    def _require_open(self) -> None:
        """失败后仅允许关闭。参数: 无。返回: None。异常: ResultClosedError。"""
        if self._closed or self._closing or self._failed or self._finished:
            raise ResultClosedError('同帧积分已关闭、失败或完成')

    def consume(self, update: LegacyDecodedUpdate) -> None:
        """接收一条已投影报文，完整同刻组才推进积分。

        参数: 当前LegacyDecodedUpdate。返回: None。异常: 身份、同刻冲突、预算、计算原错。
        无效字段覆盖本次值，不沿用前条。未选择的帧只由原读取器维护观测范围。
        """
        self._require_open()
        if self._fast:
            return self._consume_fast(update)
        values = value = None
        primary = None
        try:
            if not isinstance(update, LegacyDecodedUpdate) or update.source_ref.session_id != self._session:
                raise ValueError('同帧更新不属于当前会话')
            if not self._binding.matches(update):
                return
            if update.time_ns is None or self._last_time is not None and update.time_ns < self._last_time:
                raise ValueError('同帧积分需要非递减实际时间')
            if self._time is not None and update.time_ns > self._time:
                self._flush()
            if update.sequence in self._seen:
                raise ValueError('完整组同别名原sequence重复')
            # 共同投影器对本帧解码失败会插入None；缺少键说明绑定证明失效，不能偷用旧值。
            if any(name not in update.values for _, name in self._fields):
                raise ValueError('同帧投影没有交付全部已证明字段')
            _reserve_owned_ram(self, self._workspace, '_work_cost')
            values = {}
            for definition, name in self._fields:
                value = normalize_reference(definition, update.values[name])
                if not value.valid:
                    value = _scalar_from_validated_fields(None, value.dtype, False, value.quality)
                previous = self._chosen.get(definition.name)
                if previous is not None and definition.same_time_policy == 'error' and not _same_value(previous[1], value):
                    raise ValueError(f'同信号同时间冲突：{definition.name}@{update.time_ns}ns')
                values[definition.name] = (update.sequence, value) if previous is None or update.sequence > previous[0] else previous
            # 只保一套选定值及同刻原序号；集合每新增一项先付费，不随总文件长度增长。
            _reserve_owned_ram(self, 512 + 16 * _metadata_bytes(update.sequence), '_group_cost')
            self._seen.add(update.sequence)
            self._chosen = values
            values = None
            self._last_time = self._time = update.time_ns
        except BaseException as error:
            primary, self._failed = error, True
            raise
        finally:
            values = value = update = previous = definition = None
            try:
                _release_owned_ram(self, self._work_cost, '_work_cost')
            except BaseException as cleanup:
                self._failed = True
                if primary is None:
                    raise
                primary.add_note('同帧积分临时费用清理失败：' + type(cleanup).__name__)

    def _consume_fast(self, update: LegacyDecodedUpdate) -> None:
        """浮点快速路径逐帧接收；检查、同刻选择和冲突规则与consume相同。

        普通有限值使用数值/质量对，特殊输入沿用参考归一化。

        参数: 当前LegacyDecodedUpdate。返回: None。异常: 身份、同刻冲突、预算、计算原错。
        """
        try:
            if not isinstance(update, LegacyDecodedUpdate) or update.source_ref.session_id != self._session:
                raise ValueError('同帧更新不属于当前会话')
            if not self._binding.matches(update):
                return
            time = update.time_ns
            if time is None or self._last_time is not None and time < self._last_time:
                raise ValueError('同帧积分需要非递减实际时间')
            if self._time is not None and time > self._time:
                self._flush()
            sequence = update.sequence
            if sequence in self._seen:
                raise ValueError('完整组同别名原sequence重复')
            raw = update.values
            if any(name not in raw for _, name, _, _ in self._normalizers):
                raise ValueError('同帧投影没有交付全部已证明字段')
            # 原序号允许任意非负整数；普通64位序号复用固定槽，超宽序号补付实际差额。
            slot_cost = (_SEQUENCE_SLOT_BYTES if sequence.bit_length() <= 64
                         else 512 + 16 * _metadata_bytes(sequence))
            additional_cost = slot_cost if self._seen else max(0, slot_cost - _SEQUENCE_SLOT_BYTES)
            chosen = self._chosen
            # 需要另付同刻槽时先核实数值冲突，再申请空间并更新；保留原错误先后顺序。
            pending = {} if additional_cost else chosen
            for alias, name, normalize, policy in self._normalizers:
                pair = normalize(raw[name])
                previous = chosen.get(alias)
                if previous is not None:
                    # 有效值为有限float、无效值为None+原因，元组相等即原_same_value相等。
                    if policy == 'error' and previous[1] != pair:
                        raise ValueError(f'同信号同时间冲突：{alias}@{time}ns')
                    if sequence <= previous[0]:
                        continue
                pending[alias] = (sequence, pair)
            if additional_cost:
                _reserve_owned_ram(self, additional_cost, '_group_cost')
                chosen.update(pending)
            self._seen.add(sequence)
            self._last_time = self._time = time
        except BaseException:
            self._failed = True
            raise
        finally:
            # 与consume相同：异常回溯不钉住本帧消息、原值映射或选择状态。
            update = raw = chosen = pending = pair = previous = normalize = None

    def _flush_fast(self) -> None:
        """提交完整同刻组，取最早有效截止并追加到借用积分器。

        参数: 无；读取当前组和已编译程序。返回: None。
        异常: 保留范围回调、积分器和预算原错误，外层_flush统一标记失败。
        """
        context = scalar = value = None
        try:
            if any(len(calculation._rows) >= calculation._limit for calculation in self._calculations):
                self._before_group()
            context = {alias: entry[1] for alias, entry in self._chosen.items()}
            time, ttl = self._time, self._ttl
            for program, deps, calculation in zip(self._programs, self._deps, self._calculations):
                value, quality = program(context)
                deadline = None
                for name in deps:
                    if context[name][1] is None:
                        candidate = time + ttl[name]
                        if candidate < (1 << 63) and (deadline is None or candidate < deadline):
                            deadline = candidate
                scalar = (_scalar_from_validated_fields(value, D.FLOAT64) if quality is None
                          else _scalar_from_validated_fields(None, D.FLOAT64, False, quality))
                calculation._append_validated(time, scalar, deadline)
            self._chosen.clear()
            self._seen.clear()
            self._time = None
            if self._group_cost:
                _release_owned_ram(self, self._group_cost, '_group_cost')
        finally:
            context = scalar = value = program = calculation = None

    def _flush(self) -> None:
        """按已选求值路径提交完整同刻值并复用积分器。参数: 无。返回: None。异常: 原计算/预算错误。"""
        if self._time is None:
            return
        if self._fast:
            try:
                return self._flush_fast()
            except BaseException:
                self._failed = True
                raise
        context = cache = value = None
        primary = None
        try:
            # 点缓冲只在满批时使用范围计算面积；不为每条报文重建整份计划。
            # 即将结算前必须先取得已观测范围，尾部则由finish统一更新。
            if any(len(calculation._rows) >= calculation._limit for calculation in self._calculations):
                self._before_group()
            _reserve_owned_ram(self, self._workspace, '_work_cost')
            context = {name: item[1] for name, item in self._chosen.items()}
            evaluated = _reference_group_values(self._expressions, self._definitions, self._time, context)
            for (value, deadline), calculation in zip(evaluated, self._calculations):
                calculation.consume(((self._time, value, deadline),))
            self._chosen.clear()
            self._seen.clear()
            self._time = None
            _release_owned_ram(self, self._group_cost, '_group_cost')
        except BaseException as error:
            primary, self._failed = error, True
            raise
        finally:
            context = cache = value = deadlines = expression = calculation = evaluated = None
            try:
                _release_owned_ram(self, self._work_cost, '_work_cost')
            except BaseException as cleanup:
                self._failed = True
                if primary is None:
                    raise
                primary.add_note('同帧表达式工作区清理失败：' + type(cleanup).__name__)

    def finish(self, observed_end: int | None) -> None:
        """在原读取器确认EOF并关闭后，补算到来源真实末端的保持尾段。

        参数: 来源实际末端或None。返回: None。异常: 原数值、预算或取消错误。
        不替代EOF证明，不把domain.end当采集终点，不虚构固定周期。
        """
        self._require_open()
        try:
            self._before_group()
            self._flush()
            if observed_end is not None:
                for calculation in self._calculations:
                    if calculation._rows and calculation._last_time < observed_end:
                        time, value, deadline, _, _ = calculation._rows[-1]
                        deadline = observed_end if deadline is None else min(deadline, observed_end)
                        calculation._rows[-1] = (time, value, deadline, None, None)
                        calculation.consume(((observed_end, value, deadline),))
            self._finished = True
        except BaseException:
            self._failed = True
            raise
        finally:
            calculation = value = None

    def close(self) -> None:
        """释放自有上下文及费用，借用积分器由父会话关闭。参数: 无。返回: None。异常: 释放失败可重试。"""
        if self._closed:
            return
        self._closing = True
        self._chosen = self._seen = self._definitions = self._fields = None
        self._expressions = self._calculations = self._before_group = self._binding = None
        # 编译程序和归一化闭包也属于本对象，先丢弃引用再释放它们的固定预算。
        self._programs = self._normalizers = self._deps = self._ttl = None
        _release_owned_ram(self, self._work_cost, '_work_cost')
        _release_owned_ram(self, self._group_cost, '_group_cost')
        _release_owned_ram(self, self._fixed_cost, '_fixed_cost')
        self._closed = True
