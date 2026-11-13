"""把同一物理报文的简单数值表达式直接交给现役实际时间积分器。

本对象只保存一个待完成同刻组；不构造信号数组、历史或通用最新状态。
读取、DBC投影、范围推进、积分器及结果发布仍由原会话负责。只有首帧前
证明绑定一致的内部调用方使用本入口，运行错误不切换路径或重读输入。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isnan
from typing import Callable, Mapping, Sequence, TYPE_CHECKING

from ..core.binding import SignalDefinition
from ..core.expression import validate_expression
from ..core.expression_reference import _evaluate
from ..core.numeric import normalize_reference, ScalarValue
from ..core.scalar import _scalar_from_validated_fields
from ..core.types import SignalDType as D
from ..legacy.records import field_from_dict
from ..legacy.updates import LegacyDecodedUpdate
from ..planning.backend_selection import simple_numeric_expression
from ..results.budget import ResourceBudget, _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..results.errors import ResultClosedError
from ..sources.can_spec import can_field_from_key
from .history import _metadata_bytes
from .static_metadata import static_metadata_bytes

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


def _same_value(left: ScalarValue, right: ScalarValue) -> bool:
    """沿用同刻事实比较。参数: 归一化标量。返回: bool。异常: 无外部输入转换。"""
    return (left.valid == right.valid and left.quality == right.quality and left.code == right.code
            and type(left.value) is type(right.value)
            and (left.value == right.value or type(left.value) is float and isnan(left.value) and isnan(right.value)))


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
        except BaseException as error:
            _cleanup_owner(self, error, 'same_frame_cleanup_owner', '同帧积分构造')
            raise
        finally:
            definitions = expressions = calculations = fields = by_name = checked = expression = calculation = trees = None
            definition = declared = actual = field = binding = before_group = derived = None

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

    def _flush(self) -> None:
        """提交完整同刻值，复用原表达式核及积分器。参数: 无。返回: None。异常: 原计算/预算错误。"""
        if self._time is None:
            return
        context = cache = value = None
        primary = None
        try:
            # 点缓冲只在满批时使用范围计算面积；不为每条报文重建整份计划。
            # 即将结算前必须先取得已观测范围，尾部则由finish统一更新。
            if any(len(calculation._rows) >= calculation._limit for calculation in self._calculations):
                self._before_group()
            _reserve_owned_ram(self, self._workspace, '_work_cost')
            context = {name: item[1] for name, item in self._chosen.items()}
            cache = {}
            for expression, calculation in zip(self._expressions, self._calculations):
                value = _evaluate(expression.root, context, cache).value
                deadlines = (self._time + self._definitions[name].valid_for_ns
                             for name in expression.dependencies if context[name].valid)
                deadline = min((time for time in deadlines if time < (1 << 63)), default=None)
                calculation.consume(((self._time, value, deadline),))
            self._chosen.clear()
            self._seen.clear()
            self._time = None
            _release_owned_ram(self, self._group_cost, '_group_cost')
        except BaseException as error:
            primary, self._failed = error, True
            raise
        finally:
            context = cache = value = deadlines = expression = calculation = None
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
        _release_owned_ram(self, self._work_cost, '_work_cost')
        _release_owned_ram(self, self._group_cost, '_group_cost')
        _release_owned_ram(self, self._fixed_cost, '_fixed_cost')
        self._closed = True
