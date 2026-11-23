"""time_order直接积分的文件工作进程端：把一个文件的目标帧归成同刻组点。

PERF-P5-ORDER-01 A1/A2合同。输入是本文件读取器逐条交付的已解码记录；输出是
按时间顺序的同刻组点（SameTimeGroupSummary）和至多一个延迟错误（DeferredPointError）。
本模块只做与串行主进程相同的投影、绑定匹配和归一化，然后按时间分组；
不求值表达式、不算面积、不累计，也不知道其他文件。跨文件合并、帧型核对、
求值和积分由主进程归并时完成。

组内位置约定（A2-2）：first_sequence为0，last_sequence为帧数减1，first_conflicts
记录每个error政策信号首次冲突的组内第几帧；不传来源原序号。

两类情况本文件之后不再产生组点，但读取器仍由调用方继续读到EOF，使同一文件
后面的读取错误照常报出（A1-7）：
- 投影、匹配或归一化抛出四种内建类型之一，作为延迟错误交给主进程按原类型报出；
- 本文件某时刻出现同刻冲突，冲突组立即交付，主进程归并到该时刻时报出。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..results.budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..results.errors import ResultClosedError
from ..sources.can_spec import can_field_from_key
from ..sources.can_updates import CANUpdateProjection
from .file_integral_terms import SameTimeGroupSummary
from .integral_blocks import DEFERRED_KINDS, POINT_MESSAGE_LIMIT
from .same_frame_integrals import (SameFrameEvaluator, same_frame_evaluator_cost,
                                   SAME_FRAME_EVALUATOR_BASE_COST, _same_value)
from .static_metadata import static_metadata_bytes


@dataclass(frozen=True)
class DeferredPointError:
    """串行时会在主进程归并到该帧才抛出的错误；只保存重建所需的类型与原文。"""

    time_ns: int  # 出错帧的实际时间纳秒，主进程按它确定归并位置。
    kind: type  # DEFERRED_KINDS之一，不保存子类或任意类。
    message: str  # str(错误)原文，不截断、不附加说明。


def file_points_minimum_cost(signal_count: int) -> int:
    """计算组点生成器不依赖DBC的必要费用下界。

    参数: signal_count为非负信号定义数。
    返回: int字节数，含固定状态、当前同刻组首末值和求值器基础费；不含声明图、读取器及通信包。
    异常: 信号数非法时ValueError；不构造状态、不读取文件。
    """
    if type(signal_count) is not int or signal_count < 0:
        raise ValueError('组点信号数需要非负整数')
    return 262144 + 8192 + 2048 * signal_count + SAME_FRAME_EVALUATOR_BASE_COST


def file_points_cost(definitions, expressions, derived=()) -> int:
    """报告组点生成器及其归一化用求值器的实际固定预约费用。

    参数: definitions、expressions、derived为冻结声明tuple；expressions只用于构造求值器的一致性检查。
    返回: int，保守预约的字节数。异常: 静态模型原错误继续传播。
    调用方另计读取器、通信包和任务重建；此函数不为它们重复占用预算。
    """
    return (file_points_minimum_cost(len(definitions)) + 64 * static_metadata_bytes(definitions)
            + same_frame_evaluator_cost(definitions, expressions, derived) - SAME_FRAME_EVALUATOR_BASE_COST)


class FileGroupPoints:
    """一个文件的有界同刻分组器，只保存当前一个同刻组和停止标志。

    不变量：当前组的时间不晚于下一条目标帧；交付的组点时间严格递增；停止后不再交付组点。
    """

    def __init__(self, budget, definitions, expressions, specs, binding, session_id,
                 *, derived=(), batch_intervals=64, domain=None, step_ns=None):
        """安装与面积生成器相同的已验证任务，首条原帧尚未读取。

        参数: budget为ResourceBudget；definitions、expressions、specs为同序声明tuple，specs、
            batch_intervals、domain、step_ns只为与restore_task结果同形而接收，分组不使用它们；
            binding为SameFrameBinding；session_id为会话名；derived为派生声明tuple，默认空。
        返回: None，构造新的组点owner，不读取原帧。
        异常: 计算项与表达式数量不一致时ValueError；预算不足时BudgetExceededError；
            求值器构造原错误继续传播；构造清理失败附file_group_points_cleanup_owner。
        """
        self._budget = budget
        self._held_cost = self._fixed_cost = 0
        self._closed = self._closing = self._failed = self._finished = False
        self._stopped = False
        self._evaluator = self._projection = self._current = None
        self._definitions = None
        self._binding = binding
        try:
            if len(expressions) != len(specs):
                raise ValueError('组点任务的表达式与计算项数量不一致')
            # 自身状态先付费，再由求值器按同一账本付它自己的固定费，不重复计算。
            _reserve_owned_ram(self, file_points_cost(definitions, expressions, derived)
                               - same_frame_evaluator_cost(definitions, expressions, derived), '_fixed_cost')
            try:
                self._evaluator = SameFrameEvaluator(budget, definitions, expressions, binding, session_id, derived=derived)
            except BaseException as error:
                self._evaluator = getattr(error, 'same_frame_evaluator_cleanup_owner', None)
                raise
            self._definitions = definitions
            fields = tuple(dict.fromkeys(can_field_from_key(item.field) for item in definitions))
            # 与FileIntegralTerms相同：借用父进程同次DBC证明的唯一帧型候选配置投影，不读DBC。
            self._projection = CANUpdateProjection(binding.source, session_id, fields)
            from ..legacy.records import field_to_dict
            self._projection.configure_metadata(tuple(dict(locator=field_to_dict(field),
                dbc_frames=((binding.extended, binding.dbc_fd),)) for field in fields))
        except BaseException as error:
            _cleanup_owner(self, error, 'file_group_points_cleanup_owner', '文件组点构造')
            raise
        finally:
            definitions = expressions = specs = binding = derived = fields = None

    @property
    def compatibility_fields(self):
        """借用同次投影记录的FD兼容提示。

        参数: 无。返回: CANField到实际扩展帧标志bool的映射；投影释放后返回空dict。
        异常: 无；调用方不能修改借用的映射。
        """
        return {} if self._projection is None else self._projection.compatibility_fields

    @property
    def frame_identity(self):
        """返回本文件目标帧实际的（扩展帧, FD）。

        参数: 无。返回: 两个bool的tuple；尚无目标帧或投影已释放时None。
        异常: 无。同一文件内帧型不一致时，投影或读取器已经报错，所以记录到的帧型唯一。
        """
        if self._projection is None or not self._projection._seen:
            return None
        return next(iter(self._projection._seen.values()))

    @property
    def stopped(self):
        """返回本文件是否已停止交付组点。参数: 无。返回: bool。异常: 无。"""
        return self._stopped

    def _require_open(self):
        """拒绝失败、完成或关闭后的推进。参数: 无。返回: None。异常: ResultClosedError。"""
        if self._closed or self._closing or self._failed or self._finished:
            raise ResultClosedError('文件组点已关闭、失败或完成')

    def _defer(self, time_ns, error):
        """把可延迟的错误转成事件并停止交付组点。

        参数: time_ns为出错帧的实际纳秒；error为DEFERRED_KINDS之一的异常对象。
        返回: 事件tuple：先交付尚未交付的当前组（可能是同一时刻的前缀），再交付DeferredPointError。
        异常: 出错帧没有时间或原文超过256KiB时原样抛出error，由调用方按读取段错误报告。
        """
        message = str(error)
        if type(time_ns) is not int or len(message.encode('utf-8')) > POINT_MESSAGE_LIMIT:
            raise error
        events = () if self._current is None else (self._current,)
        self._current = None
        self._stopped = True
        return events + (DeferredPointError(time_ns, type(error), message),)

    def feed(self, record):
        """消费读取器的一条已解码记录，必要时返回已完成的组点或延迟错误。

        参数: record为读取器交付的DecodedCANRecord。返回: 有界事件tuple，通常为空或含一个上一时刻的组点。
        异常: 不可延迟的错误（时间倒退、无时间记录、预算等）原样传播，标记失败；
            投影、匹配和归一化抛出的四种内建类型错误转成延迟错误事件，不抛出。
        停止后只返回空tuple；读取器仍由调用方继续推进到EOF。
        """
        self._require_open()
        if self._stopped:
            return ()
        raw = update = values = None
        try:
            raw = record.raw
            # 与串行主进程顺序相同：先投影（可能报帧型或值错误），再匹配绑定，最后归一化。
            try:
                update = self._projection.build(raw.frame, record.sequence, dict(record.values), raw.time_ns,
                                                canonical_keys=True)
                if update is None or not self._binding.matches(update):
                    return ()
                values = self._evaluator.normalize(update.values)
            except Exception as error:
                if type(error) not in DEFERRED_KINDS:
                    raise
                return self._defer(raw.time_ns, error)
            time = update.time_ns
            if type(time) is not int:
                # time_scope为source时目标记录都有时间；选择条件已保证，这里只防御不可能的输入。
                raise ValueError('组点需要带时间的目标记录')
            current, events = self._current, ()
            if current is not None and time < current.time_ns:
                # 文件内目标帧时间倒退时读取器已先报错；此处同样不能接受。
                raise ValueError('同帧积分需要非递减实际时间')
            if current is not None and time > current.time_ns:
                events, current = (current,), None
            if current is None:
                current = SameTimeGroupSummary(time, 0, 0, 1, values, values, (None,) * len(values))
            else:
                # 新帧是组内第position帧；error政策信号与首帧值不同即记下首次冲突位置。
                position = current.count
                conflicts = tuple(old if old is not None else position
                    if definition.same_time_policy == 'error' and not _same_value(first, value) else None
                    for definition, first, value, old in zip(self._definitions, current.first_values, values,
                                                             current.first_conflicts))
                current = SameTimeGroupSummary(time, 0, position, position + 1, current.first_values, values, conflicts)
            if any(value is not None for value in current.first_conflicts):
                # 冲突组立即交付并停止：主进程归并到此刻必然报错，之后的组点没有消费者。
                self._current, self._stopped = None, True
                return events + (current,)
            self._current = current
            return events
        except BaseException:
            self._failed = True
            raise
        finally:
            record = raw = update = values = None

    def finish(self):
        """读取器EOF后交付最后一个同刻组。

        参数: 无。返回: 事件tuple，最多一个组点；已停止或无目标帧时为空。
        异常: 已关闭、失败或完成时ResultClosedError。
        """
        self._require_open()
        events = () if self._current is None else (self._current,)
        self._current = None
        self._finished = True
        return events

    def drain_prefix_on_error(self):
        """读取失败时不交付前缀，与面积生成器接口同名。

        参数: 无。返回: 空tuple。读取段错误一律先于归并段，主进程丢弃本次全部组点，前缀没有消费者。
        异常: 已关闭时ResultClosedError。
        """
        if self._closed or self._closing:
            raise ResultClosedError('文件组点已关闭')
        self._current = None
        return ()

    def close(self):
        """断开当前组、投影和求值器引用并退还费用。参数: 无。返回: None。异常: 退款失败可重试。"""
        if self._closed:
            return
        self._closing = True
        self._current = self._projection = self._definitions = self._binding = None
        if self._evaluator is not None:
            self._evaluator.close()
            self._evaluator = None
        _release_owned_ram(self, self._fixed_cost, '_fixed_cost')
        self._closed = True
