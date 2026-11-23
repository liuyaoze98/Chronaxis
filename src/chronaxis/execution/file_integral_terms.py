"""按文件并行计算原序面积，父进程独自处理跨文件边界和误差求和。

工作进程只保留有限点块和当前同刻组；首组的出区间交给父进程，避免前一
文件的同刻值改变本文件首组。消息不包含原帧、历史文件或文件部分和。
"""

from dataclasses import dataclass, replace

from ..core.calculations import CalculationSeries
from ..core.integral_terms_reference import compute_integral_terms_reference
from ..core.models import Interval
from ..core.numeric import ScalarValue
from ..core.types import QualityFlag
from ..results.budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..results.errors import ResultClosedError
from ..sources.can_spec import can_field_from_key
from ..sources.can_updates import CANUpdateProjection
from .same_frame_integrals import (SameFrameEvaluator, same_frame_evaluator_cost,
                                  SAME_FRAME_EVALUATOR_BASE_COST, _same_value)
from .static_metadata import static_metadata_bytes


@dataclass(frozen=True)
class SameTimeGroupSummary:
    """保留解决跨文件同刻选择所需的首末值及最早冲突位置，大小不随组帧数增长。"""

    time_ns: int  # 同刻组实际时间，不创建第二套计算时钟。
    first_sequence: int  # 文件内首条原帧序号；父进程加之前文件的全部原帧数。
    last_sequence: int  # 本组最后原帧序号，供last_by_sequence使用。
    count: int  # 组内匹配帧数，不保存逐帧序号列表。
    first_values: tuple[ScalarValue, ...]  # 按冻结定义顺序，供跨文件error政策比较。
    last_values: tuple[ScalarValue, ...]  # 同顺序最终值；无效本条也覆盖上一条。
    first_conflicts: tuple[int | None, ...]  # 每个error信号首次冲突的局部序号，None表示未见冲突。


@dataclass(frozen=True)
class FileIntegralHead:
    """文件首个目标同刻组及下一组时间；首个出区间始终由父进程计算。"""

    group: SameTimeGroupSummary  # 仅首组可能受前文件的同刻值影响。
    next_time_ns: int | None  # 下一目标组的实际时间；单组或错误排空时尚未知。


@dataclass(frozen=True)
class IntegralColumnTerms:
    """一个计算项的原序面积、有效掩码和覆盖事实，不含局部和。"""

    areas: tuple[float, ...]  # 原序float64面积，尚未换算最终单位或求和。
    valid: tuple[bool, ...]  # 无效槽中的0不能作为有效零参与求和。
    covered_ns: int  # 该块与请求范围相交的实际覆盖长度。
    valid_ns: int  # 上述覆盖内具备有效数值的长度。
    quality: QualityFlag  # 原面积核已确认的质量位。


@dataclass(frozen=True)
class IntegralTermsChunk:
    """排除首组出区间后的有限内部区间块；列顺序与冻结计算项一致。"""

    left_ns: int  # 本块第一个点时间，和前块右端一致。
    right_ns: int  # 本块最后一个点时间，不另计尾面积。
    columns: tuple[IntegralColumnTerms, ...]  # 固定计算项顺序的各原序列。
    right_closed: bool = True  # True表示右端同刻组已关闭；False表示仍需等待跨文件同刻合并。


@dataclass(frozen=True)
class FileIntegralTail:
    """文件末组；same_as_head表示单组文件，不重复传其组值。"""

    group: SameTimeGroupSummary | None  # 多组文件的末组；无目标或单组时None。
    same_as_head: bool  # 单组文件与head共享，不再复制首末值。


@dataclass(frozen=True)
class FileIntegralFrontier:
    """异常排空时确认一个已经关闭的右端组；没有可另行组成面积块的区间。"""

    time_ns: int  # 已闭内部点，与父进程正在等待的面积右端一致。


def _conflict(group, definitions):
    """按原帧位置和声明顺序抛出最早同刻冲突。参数: 组及定义。返回: None。异常: ValueError。"""
    candidates = [(sequence, index) for index, sequence in enumerate(group.first_conflicts) if sequence is not None]
    if candidates:
        sequence, index = min(candidates)
        error = ValueError(f'同信号同时间冲突：{definitions[index].name}@{group.time_ns}ns')
        error.sequence = sequence
        raise error


def _offset_group(group, offset):
    """将局部原帧序号提升到连续来源全局序号。

    参数: group为SameTimeGroupSummary；offset为此前文件全部原帧数量的非负int。
    返回: SameTimeGroupSummary，保持时间和值，仅平移原帧序号。
    异常: 内部字段不符合模型时传播TypeError或AttributeError。
    """
    return replace(group, first_sequence=group.first_sequence + offset,
                   last_sequence=group.last_sequence + offset,
                   first_conflicts=tuple(None if value is None else value + offset for value in group.first_conflicts))


def _merge_group(left, right, definitions):
    """有界合并跨文件同刻组；不会为相等组保留逐帧序号集合。

    参数: left和right为同刻且全局序号递增的SameTimeGroupSummary；
        definitions为与摘要值同序的SignalDefinition tuple。
    返回: 合并后的SameTimeGroupSummary，不保存逐帧序号集合。
    异常: 非同刻或原序号倒退时ValueError；业务冲突先记录到摘要，由调用方按序抛出。
    """
    if left.time_ns != right.time_ns or left.last_sequence >= right.first_sequence:
        raise ValueError('跨文件同刻组时间或全局原序号不合法')
    conflicts = []
    for index, definition in enumerate(definitions):
        candidates = [item for item in (left.first_conflicts[index], right.first_conflicts[index]) if item is not None]
        if definition.same_time_policy == 'error' and not _same_value(left.first_values[index], right.first_values[index]):
            candidates.append(right.first_sequence)
        conflicts.append(min(candidates) if candidates else None)
    return SameTimeGroupSummary(left.time_ns, left.first_sequence, right.last_sequence,
                                left.count + right.count, left.first_values, right.last_values, tuple(conflicts))


def _columns(points, expressions, specs, domain, step_ns=None):
    """调用现役参考面积核，不先累计、不改变乘除顺序。

    参数: points为有界(实际纳秒, 求值结果)点列；expressions和specs为同序的
        StaticExpression与CalculationDefinition tuple；domain为Interval或None；
        step_ns为None（实际间隔）或固定间隔正纳秒，与父积分器相同。
    返回: tuple[IntegralColumnTerms, ...]，按计算项顺序保留各区间面积。
    异常: 原面积核的类型、时间及数值结构错误原样传播。
    固定间隔时每对相邻点的面积为左值×间隔×实际交集÷实际跨度，交集仍按实际时间
    和有效期截止裁剪；覆盖时长和有效时长继续报告实际纳秒，不换成间隔。
    """
    times = tuple(item[0] for item in points)
    observation = Interval(times[0], times[-1])
    columns = []
    for index, (expression, spec) in enumerate(zip(expressions, specs)):
        values = tuple(item[1][index][0] for item in points)
        deadlines = tuple(item[1][index][1] for item in points)
        series = CalculationSeries(observation, times, values, (True,) * len(times), expression.root.unit)
        terms = compute_integral_terms_reference(series, replace(spec, window=domain or observation),
                                                 step_ns=step_ns, valid_until_ns=deadlines,
                                                 retain_unknown_ranges=False)
        facts = terms.facts
        covered = 0 if facts.actual_window is None else facts.actual_window.end_ns - facts.actual_window.start_ns
        columns.append(IntegralColumnTerms(terms.areas, terms.valid, covered, facts.value_valid_duration_ns, facts.quality))
    return tuple(columns)


def file_terms_minimum_cost(calculation_count: int, *, batch_intervals: int = 64) -> int:
    """计算文件面积状态不依赖DBC的必要费用下界。

    参数: calculation_count为非负计算项数；batch_intervals为1至4096的区间批上限。
    返回: int字节数，仅含固定状态和批容量，未计声明、表达式及读取费用。
    异常: 计算项数或批上限非法时ValueError；不构造数值状态、不读取文件。
    """
    if type(calculation_count) is not int or calculation_count < 0:
        raise ValueError('文件面积计算项数需要非负整数')
    if type(batch_intervals) is not int or not 1 <= batch_intervals <= 4096:
        raise ValueError('文件面积块需要1到4096个区间')
    return (262144 + (batch_intervals + 1) * (8192 + calculation_count * 8192)
            + SAME_FRAME_EVALUATOR_BASE_COST)


def parent_terms_minimum_cost(calculation_count: int, *, batch_intervals: int = 64) -> int:
    """计算父边界状态不依赖DBC的必要费用下界。

    参数: calculation_count为非负计算项数；batch_intervals为1至4096的全局积分批上限。
    返回: int字节数，覆盖固定状态和全局余量；不含声明图及借用的RecordIntegral。
    异常: 计算项数或批上限非法时ValueError；不申请预算或构造求值器。
    """
    if type(calculation_count) is not int or calculation_count < 0:
        raise ValueError('父进程积分计算项数需要非负整数')
    if type(batch_intervals) is not int or not 1 <= batch_intervals <= 4096:
        raise ValueError('父进程积分批需要1到4096个区间')
    return (262144 + calculation_count * (32768 + (batch_intervals + 4096) * 256)
            + SAME_FRAME_EVALUATOR_BASE_COST)


def file_terms_cost(definitions, expressions, specs, derived=(), *, batch_intervals=64):
    """报告文件面积owner及其求值器的实际固定预约费用。

    参数: definitions、expressions、specs、derived为冻结声明tuple；
        batch_intervals为1至4096的区间数上限，默认64。
    返回: int，保守预约的字节数。异常: 批上限非法时ValueError；静态模型原错传播。
    调用方另计读取器、通信包和任务重建；此函数不为它们重复占用预算。
    """
    return (file_terms_minimum_cost(len(expressions), batch_intervals=batch_intervals)
            + 64 * static_metadata_bytes((definitions, specs))
            + same_frame_evaluator_cost(definitions, expressions, derived) - SAME_FRAME_EVALUATOR_BASE_COST)


def parent_terms_cost(definitions, expressions, derived=(), *, batch_intervals=64):
    """报告父边界owner及求值器固定费用，覆盖全局余量、一个通信块和切片副本。

    参数: definitions、expressions、derived为冻结声明tuple；
        batch_intervals为1至4096的全局积分批上限，默认64。
    返回: int，保守预约的字节数。异常: 批上限非法时ValueError；静态模型原错传播。
    不包含借用的RecordIntegral，其预算仍由父会话独立申请。
    """
    return (parent_terms_minimum_cost(len(expressions), batch_intervals=batch_intervals)
            + 64 * static_metadata_bytes(definitions)
            + same_frame_evaluator_cost(definitions, expressions, derived) - SAME_FRAME_EVALUATOR_BASE_COST)


class FileIntegralTerms:
    """文件工作进程的有界归组及面积生产器，不拥有求和状态。"""

    def __init__(self, budget, definitions, expressions, specs, binding, session_id,
                 *, derived=(), batch_intervals=64, domain=None, step_ns=None):
        """安装已验证任务及投影，首条原帧尚未读取。

        参数: budget为ResourceBudget；definitions、expressions、specs为同序声明tuple；
            binding为SameFrameBinding；session_id为会话名；derived为派生声明tuple，默认空；
            batch_intervals为1至4096的区间数上限，默认64；domain为Interval或None；
            step_ns为None（实际间隔）或int64范围内的固定间隔正纳秒，由父进程任务传入。
        返回: None，构造新的文件面积owner，不读取原帧。
        异常: 非法声明、批上限或间隔时ValueError，范围类型错误时TypeError，预算不足时BudgetExceededError；
            原求值器异常继续传播，构造清理失败附file_integral_terms_cleanup_owner。
        """
        self._budget = budget
        self._held_cost = self._fixed_cost = 0
        self._closed = self._closing = self._failed = self._finished = False
        self._evaluator = self._projection = self._points = self._current = None
        self._definitions = self._expressions = self._specs = None
        self._head = False
        self._last_sequence = None
        self._binding = binding
        try:
            if type(batch_intervals) is not int or not 1 <= batch_intervals <= 4096:
                raise ValueError('文件面积块需要1到4096个区间')
            if len(expressions) != len(specs) or any(spec.operation != 'integral' or spec.scope != 'session' for spec in specs):
                raise ValueError('文件面积需要对应ZOH积分项')
            if domain is not None and type(domain) is not Interval:
                raise TypeError('文件面积范围需要Interval或None')
            # 间隔来自外部任务，先按积分器的同一规则检查，避免工作进程用非法值算出面积。
            if step_ns is not None and (type(step_ns) is not int or not 0 < step_ns <= (1 << 63) - 1):
                raise ValueError('文件面积固定间隔需要int64范围内正整数纳秒')
            # 覆盖当前组的首末值、有限求值点、面积核临时列与待交付的一块DTO。
            cost = file_terms_cost(definitions, expressions, specs, derived, batch_intervals=batch_intervals)
            cost -= same_frame_evaluator_cost(definitions, expressions, derived)
            _reserve_owned_ram(self, cost, '_fixed_cost')
            try:
                self._evaluator = SameFrameEvaluator(budget, definitions, expressions, binding, session_id, derived=derived)
            except BaseException as error:
                self._evaluator = getattr(error, 'same_frame_evaluator_cleanup_owner', None)
                raise
            self._definitions, self._expressions, self._specs = definitions, expressions, specs
            self._limit, self._domain, self._step_ns = batch_intervals, domain, step_ns
            self._points = []
            fields = tuple(dict.fromkeys(can_field_from_key(item.field) for item in definitions))
            self._projection = CANUpdateProjection(binding.source, session_id, fields)
            # 此处借用父进程同次DBC已经证明的唯一候选，不重新读取DBC。
            from ..legacy.records import field_to_dict
            self._projection.configure_metadata(tuple(dict(locator=field_to_dict(field),
                dbc_frames=((binding.extended, binding.dbc_fd),)) for field in fields))
        except BaseException as error:
            _cleanup_owner(self, error, 'file_integral_terms_cleanup_owner', '文件积分面积构造')
            raise
        finally:
            definitions = expressions = specs = binding = derived = fields = None

    @property
    def compatibility_fields(self):
        """借用同次投影的FD兼容提示。

        参数: 无。返回: CANField到实际扩展帧标志bool的映射；投影释放后返回空dict。
        异常: 无；调用方不能修改借用的映射。
        """
        return {} if self._projection is None else self._projection.compatibility_fields

    @property
    def frame_identity(self):
        """返回本文件目标帧实际的（扩展帧, FD），供父进程跨文件核对帧型（BUG-P5-005）。

        参数: 无。返回: 两个bool的tuple；尚无目标帧或投影已释放时None。
        异常: 无。同一文件内帧型不一致时读取器或投影已经报错，所以记录到的帧型唯一。
        """
        if self._projection is None or not self._projection._seen:
            return None
        return next(iter(self._projection._seen.values()))

    def _require_open(self):
        """拒绝失败、完成或关闭后的推进。参数: 无。返回: None。异常: ResultClosedError。"""
        if self._closed or self._closing or self._failed or self._finished:
            raise ResultClosedError('文件积分面积已关闭、失败或完成')

    def _flush_points(self, *, right_closed=True):
        """将完整内部区间交付为一个有限块，留下共享末点。

        参数: right_closed为bool，默认True；False表示右端同刻组尚可能与下一文件合并。
        返回: IntegralTermsChunk；不足两个点时返回None。
        异常: 原面积核的类型、时间及数值结构错误原样传播。
        """
        if len(self._points) < 2:
            return None
        block = IntegralTermsChunk(self._points[0][0], self._points[-1][0],
                                   _columns(self._points, self._expressions, self._specs, self._domain,
                                            self._step_ns), right_closed)
        self._points[:] = self._points[-1:]
        return block

    def _append_group(self, group, *, check_conflict=True, right_closed=True):
        """保存一组必要求值点，并在区间数达到上限时交付块。

        参数: group为SameTimeGroupSummary；check_conflict默认True，控制是否立即报告组内冲突；
            right_closed默认True，标明此组是否已关闭，供交付块的右端状态使用。
        返回: IntegralTermsChunk；尚未达到块上限时返回None。
        异常: 同刻冲突时ValueError；原求值器和面积核异常继续传播。
        """
        if check_conflict:
            _conflict(group, self._definitions)
        self._points.append((group.time_ns, self._evaluator.evaluate(group.time_ns, group.last_values)))
        return self._flush_points(right_closed=right_closed) if len(self._points) >= self._limit + 1 else None

    def feed(self, record):
        """消费读取器的一条已解码记录，必要时返回首组或一个内部面积块。

        参数: DecodedCANRecord。返回: 有界事件tuple。异常: 原投影、原序、归一化或面积错误。
        无关帧只在读取层参与观测事实；这里不缓存其载荷或重复解码。
        """
        self._require_open()
        try:
            raw = record.raw
            update = self._projection.build(raw.frame, record.sequence, dict(record.values), raw.time_ns, canonical_keys=True)
            if update is None or not self._binding.matches(update):
                return ()
            if self._last_sequence is not None and update.sequence <= self._last_sequence:
                raise ValueError('文件积分原sequence需要严格递增')
            self._last_sequence = update.sequence
            current, events = self._current, []
            if current is not None and update.time_ns < current.time_ns:
                raise ValueError('同帧积分需要非递减实际时间')
            if current is not None and update.time_ns > current.time_ns:
                if not self._head:
                    events.append(FileIntegralHead(current, update.time_ns))
                    self._head = True
                else:
                    block = self._append_group(current)
                    if block is not None:
                        events.append(block)
                current = None
            values = self._evaluator.normalize(update.values)
            if current is None:
                current = SameTimeGroupSummary(update.time_ns, update.sequence, update.sequence, 1,
                                               values, values, (None,) * len(values))
            else:
                conflicts = tuple(old if old is not None else update.sequence
                    if definition.same_time_policy == 'error' and not _same_value(first, value) else None
                    for definition, first, value, old in zip(self._definitions, current.first_values, values, current.first_conflicts))
                current = replace(current, last_sequence=update.sequence, count=current.count + 1,
                                  last_values=values, first_conflicts=conflicts)
            self._current = current
            # 内部冲突按实际接收时立即停止；首组同样停止，但其摘要由异常排空交给父进程，
            # 使跨文件更早冲突仍先于此文件后续错误。不能等到下一不同时间再发现冲突。
            _conflict(current, self._definitions)
            return tuple(events)
        except BaseException:
            self._failed = True
            raise
        finally:
            record = raw = update = values = None

    def finish(self):
        """完成有限数值缓冲；读取器EOF和关闭成功由传输层单独证明。

        参数: 无。返回: 事件tuple，包含首组/内部面积块及文件末组标志；无目标帧也返回末标志。
        异常: 已关闭、失败或完成时ResultClosedError；原数值异常继续传播，失败后只能关闭。
        """
        self._require_open()
        try:
            current, events = self._current, []
            if current is None:
                events.append(FileIntegralTail(None, False))
            elif not self._head:
                events.extend((FileIntegralHead(current, None), FileIntegralTail(None, True)))
            else:
                # 末组只作内部最后一个右端点；其冲突由父进程收到末组时报告。
                block = self._append_group(current, check_conflict=False, right_closed=False)
                if block is None:
                    block = self._flush_points(right_closed=False)
                if block is not None:
                    events.append(block)
                events.append(FileIntegralTail(current, False))
            self._current = None
            self._points.clear()
            self._finished = True
            return tuple(events)
        except BaseException:
            self._failed = True
            raise

    def drain_prefix_on_error(self):
        """读取或求值失败后交付此前真正关闭的有限组，不假设当前组已经结束。

        参数: 无。返回: 事件tuple，可含FileIntegralHead、IntegralTermsChunk或FileIntegralFrontier；
            没有可交付前缀或已经完成时为空tuple。
        异常: 已关闭时ResultClosedError；原数值异常继续传播。
        首组摘要也携带已看到的冲突位置，父进程可先判定更早的跨文件冲突。
        """
        if self._closed or self._closing:
            raise ResultClosedError('文件积分面积已关闭')
        if self._finished:
            return ()
        if not self._head and self._current is not None:
            event = FileIntegralHead(self._current, None)
            self._head = True
            return (event,)
        block = self._flush_points()
        if block is not None:
            return (block,)
        return (FileIntegralFrontier(self._points[0][0]),) if self._points else ()

    def close(self):
        """断开缓冲和投影引用并退还本owner费用。参数: 无。返回: None。异常: 退款失败可重试。"""
        if self._closed:
            return
        self._closing = True
        self._current = self._points = self._projection = self._definitions = self._expressions = self._specs = None
        self._binding = None
        if self._evaluator is not None:
            self._evaluator.close()
            self._evaluator = None
        _release_owned_ram(self, self._fixed_cost, '_fixed_cost')
        self._closed = True


class ParentIntegralTerms:
    """按文件顺序修复同刻及边界，并将原序面积交给父进程唯一积分器。"""

    def __init__(self, budget, definitions, expressions, calculations, binding, session_id,
                 *, derived=(), domain=None):
        """建立有界边界状态，借用外部积分器。

        参数: budget为ResourceBudget；definitions、expressions、calculations为同序声明及RecordIntegral tuple；
            binding为SameFrameBinding；session_id为会话名；derived为派生声明tuple，默认空；
            domain为Interval或None，默认沿实际观测范围。
        返回: None，构造新的父边界owner，借用外部积分器。
        异常: 声明、范围、积分器或间隔不一致时ValueError，预算不足时BudgetExceededError；
            原求值器异常继续传播，构造清理失败附parent_integral_terms_cleanup_owner。
        积分器共用的间隔（实际或同一固定间隔）同时用于跨文件边界面积和末端处理。
        """
        self._budget = budget
        self._held_cost = self._fixed_cost = 0
        self._closed = self._closing = self._failed = self._finished = False
        self._evaluator = self._pending = None
        self._definitions = self._expressions = self._calculations = None
        self._file_open = self._head = False
        self._next = None
        self._areas = self._valid = None
        self._right_closed = True
        self._step_ns = None  # 构造核实后为积分器共用间隔：None为实际间隔，正整数为固定纳秒。
        try:
            if len(expressions) != len(calculations) or domain is not None and type(domain) is not Interval:
                raise ValueError('父进程面积需要对应计算项及可选范围')
            for expression, calculation in zip(expressions, calculations):
                if (calculation._conditioned
                        or calculation._dtype != expression.root.dtype or calculation._input_unit != expression.root.unit):
                    raise ValueError('父进程面积与积分器不一致')
            # 边界面积和工作进程面积必须按同一种间隔计算，混用时没有唯一的末端规则。
            steps = {calculation._step_ns for calculation in calculations}
            if len(steps) != 1:
                raise ValueError('并行积分各计算项必须共用实际间隔或同一个固定间隔')
            self._step_ns = next(iter(steps))
            limits = {calculation._limit for calculation in calculations}
            if len(limits) != 1:
                raise ValueError('并行积分各计算项必须使用同一全局批上限')
            self._limit = next(iter(limits))
            # 最多一个不足全局批的余量加当前通信块；后者最多4096项，并包含切片临时副本。
            cost = parent_terms_cost(definitions, expressions, derived, batch_intervals=self._limit)
            cost -= same_frame_evaluator_cost(definitions, expressions, derived)
            _reserve_owned_ram(self, cost, '_fixed_cost')
            try:
                self._evaluator = SameFrameEvaluator(budget, definitions, expressions, binding, session_id, derived=derived)
            except BaseException as error:
                self._evaluator = getattr(error, 'same_frame_evaluator_cleanup_owner', None)
                raise
            self._definitions, self._expressions, self._calculations = definitions, expressions, calculations
            self._domain = domain
            self._areas = [[] for _ in calculations]
            self._valid = [[] for _ in calculations]
        except BaseException as error:
            _cleanup_owner(self, error, 'parent_integral_terms_cleanup_owner', '父进程积分边界构造')
            raise
        finally:
            definitions = expressions = calculations = binding = derived = expression = calculation = None

    def _require_open(self):
        """失败或结束后仅允许关闭。参数: 无。返回: None。异常: ResultClosedError。"""
        if self._closed or self._closing or self._failed or self._finished:
            raise ResultClosedError('父进程积分边界已关闭、失败或完成')

    def begin_file(self, sequence_offset):
        """切换到下一个已按顺序交付的文件。参数: 之前全部原帧数。返回: None。异常: 状态/偏移错。"""
        self._require_open()
        if self._file_open or type(sequence_offset) is not int or sequence_offset < 0:
            raise ValueError('文件边界尚未结束或原序号偏移不合法')
        self._offset = sequence_offset
        self._file_open, self._head, self._next = True, False, None

    def _drain(self, *, final=False):
        """按原全局批界依次推进各指标，不提前累计尚未关闭的右端组。

        参数: final仅整体EOF时允许不足一批。返回: None。异常: 原累计容量/状态错误。
        """
        available = len(self._areas[0]) - (0 if self._right_closed else 1)
        while available >= self._limit or final and available:
            count = min(available, self._limit)
            for areas, valid, calculation in zip(self._areas, self._valid, self._calculations):
                calculation.consume_terms(tuple(areas[:count]), tuple(valid[:count]), 0, 0, QualityFlag.NONE,
                                          step_ns=self._step_ns)
            for areas, valid in zip(self._areas, self._valid):
                del areas[:count]
                del valid[:count]
            available -= count

    def _mark_closed(self):
        """确认待定右端同刻组关闭后允许满批归约。参数: 无。返回: None。异常: 原累计错误。"""
        self._right_closed = True
        self._drain()

    def _accept(self, columns, *, right_closed=True):
        """保存一块原序面积并累计已经收到的覆盖事实。参数: 对应列及右端关闭标志。返回: None。异常: 原结构/累计错。"""
        if len(columns) != len(self._calculations):
            raise ValueError('面积列与计算项数量不一致')
        counts = {len(column.areas) for column in columns}
        if len(counts) != 1 or not 1 <= next(iter(counts)) <= 4096 or type(right_closed) is not bool:
            raise ValueError('面积列长度或右端关闭标志不合法')
        # 新内部块左端已经关闭，先前悬而未决的一个区间现在可以进入全局归约。
        self._mark_closed()
        for column, calculation, areas, valid in zip(columns, self._calculations, self._areas, self._valid):
            if len(column.valid) != len(column.areas):
                raise ValueError('面积与有效掩码长度不同')
            calculation.consume_terms((), (), column.covered_ns, column.valid_ns, column.quality,
                                      step_ns=self._step_ns)
            areas.extend(column.areas)
            valid.extend(column.valid)
        self._right_closed = right_closed
        self._drain()

    def _boundary(self, group, right):
        """使用现役面积核计算一条跨文件或首组出区间。参数: 左组和右端时间。返回: None。异常: 原计算错。"""
        if right <= group.time_ns:
            raise ValueError('积分边界需要严格递增时间')
        evaluated = self._evaluator.evaluate(group.time_ns, group.last_values)
        points = ((group.time_ns, evaluated), (right, evaluated))
        self._accept(_columns(points, self._expressions, tuple(c._spec for c in self._calculations), self._domain,
                              self._step_ns), right_closed=False)

    def consume(self, event):
        """接收当前文件的首组、面积块或末组；文件顺序由池保证。

        参数: 文件面积或边界冻结事件。返回: None。异常: 同刻冲突、时间/消息次序或原累计错误。
        """
        self._require_open()
        try:
            if not self._file_open:
                raise ValueError('面积事件没有当前文件')
            if type(event) is FileIntegralHead:
                if self._head:
                    raise ValueError('文件首组重复')
                group = _offset_group(event.group, self._offset)
                previous = self._pending
                if previous is not None:
                    if previous.time_ns > group.time_ns:
                        raise ValueError('同帧积分需要非递减实际时间')
                    if previous.time_ns == group.time_ns:
                        group = _merge_group(previous, group, self._definitions)
                    else:
                        _conflict(previous, self._definitions)
                        self._mark_closed()
                        self._boundary(previous, group.time_ns)
                _conflict(group, self._definitions)
                self._head, self._next = True, event.next_time_ns
                self._pending = group
                if event.next_time_ns is not None:
                    self._mark_closed()
                    self._boundary(group, event.next_time_ns)
                    self._pending = None
            elif type(event) is IntegralTermsChunk:
                if not self._head or self._next is None or event.left_ns != self._next or event.right_ns <= event.left_ns:
                    raise ValueError('文件内部面积块不连续')
                self._accept(event.columns, right_closed=event.right_closed)
                self._next = event.right_ns
            elif type(event) is FileIntegralFrontier:
                if not self._head or self._next != event.time_ns:
                    raise ValueError('已关闭组前沿与面积端点不一致')
                self._mark_closed()
            elif type(event) is FileIntegralTail:
                if event.same_as_head:
                    if not self._head or self._next is not None or event.group is not None:
                        raise ValueError('单组文件末标志不合法')
                elif event.group is None:
                    if self._head:
                        raise ValueError('有目标帧的文件缺少末组')
                else:
                    group = _offset_group(event.group, self._offset)
                    if not self._head or self._next != group.time_ns:
                        raise ValueError('文件末组与内部面积终点不一致')
                    _conflict(group, self._definitions)
                    self._pending = group
                self._file_open = False
            else:
                raise TypeError('未知文件面积事件')
        except BaseException:
            self._failed = True
            raise

    def finish(self, observed_end):
        """读取池已证明全部EOF后，实际间隔仅补到实际观测末端。

        参数: 真实末端或None。返回: None。异常: 未完成文件、时间倒退或原累计错误。
        固定间隔只在相邻两次驱动更新之间计面积；最后一组之后没有下一次更新，
        因此不补尾段，与通用路径一致。观测末端仍须不早于最后一组。
        """
        self._require_open()
        try:
            if self._file_open:
                raise ValueError('文件尚未交付末组')
            if self._pending is not None:
                if observed_end is None or observed_end < self._pending.time_ns:
                    raise ValueError('观测末端早于目标帧')
                self._mark_closed()
                if self._step_ns is None and observed_end > self._pending.time_ns:
                    self._boundary(self._pending, observed_end)
            self._right_closed = True
            self._drain(final=True)
            self._finished = True
        except BaseException:
            self._failed = True
            raise

    def close(self):
        """释放自有边界状态，外部积分器由父会话关闭。参数: 无。返回: None。异常: 退款失败可重试。"""
        if self._closed:
            return
        self._closing = True
        self._pending = self._definitions = self._expressions = self._calculations = None
        self._areas = self._valid = None
        if self._evaluator is not None:
            self._evaluator.close()
            self._evaluator = None
        _release_owned_ram(self, self._fixed_cost, '_fixed_cost')
        self._closed = True
