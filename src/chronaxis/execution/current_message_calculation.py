"""用三格式共用的消息计算一项逐报文累计，不建立消息历史或原帧副本。

输入是CAN读取进程投影后的有限LegacyDecodedUpdate批，公式使用本条值，不保持上一条。
复用既有归一化、参考/NumPy表达式、正负分桶及原序求和；period已经在公式
中时不再乘dt。结果是累计快照；来源是否完整读完由拥有读取器的调用方确认。
此组件由当前记录执行器调用，不创建旧绑定证明或额外核验扫描。
"""

from ..core import expression_reference, expression_numpy
from ..core.expression import validate_expression
from ..core.models import Interval
from ..core.numeric import to_float_reference
from ..core.numeric_numpy import to_float_numpy
from ..core.types import QualityFlag as Q
from ..core.where_updates import contains_where, numpy_active, reference_active
from ..core.enum_codes import code_dependencies
from dataclasses import replace
from ..legacy.sum import LegacySumAccumulator, LegacySumContribution, LegacySkipReason
from ..legacy.updates import LegacyDecodedUpdate
from ..planning.message_calculations import require_message_calculation
from ..results.budget import ResourceBudget, _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..results.errors import ResultClosedError
from ..sources.can_spec import can_field_from_key
from ..sources.packing import pack_message_values
from .calculation_values import scalar_from_column, direction_bucket_state, direction_skip_reason
from .history import _metadata_bytes
from ..core.lookup import pack_requested_lookups


class CurrentMessageCalculation:
    """持有一项公式与固定累计状态；输入批及明细回调都只在consume期间借用。"""

    def __init__(self, calculation, sources, bindings, session_id, budget, *, backend='numpy',
                 batch_rows=64, domain=None, contribution_consumer=None):
        """先核有限声明，再预约公式和累计状态，不读输入或DBC。

        参数: calculation/sources/bindings为同一计划声明；session_id为会话；budget为
            共享预算；backend为独立数值核；batch_rows为批上限；domain为可选
            实际时间筛选；contribution_consumer仅显式请求明细时接收(贡献,本次质量)。
        返回: 新累计组件。异常: 声明/预算/取消错误；失败构造携带可重试清理句柄。
        """
        require_message_calculation(calculation, sources, bindings)
        if not isinstance(budget, ResourceBudget) or backend not in ('reference', 'numpy'):
            raise TypeError('逐消息计算需要共享预算及明确数值后端')
        if type(batch_rows) is not int or not 1 <= batch_rows <= 4096:
            raise ValueError('逐消息计算批上限需要1到4096')
        if domain is not None and not isinstance(domain, Interval):
            raise TypeError('消息时间筛选需要Interval或None')
        if contribution_consumer is not None and not callable(contribution_consumer):
            raise TypeError('贡献消费者需要可调用对象或None')
        self._budget = budget
        self._held_cost = self._fixed_cost = self._batch_cost = 0
        self._accumulator = self._compiled = self._fields = self._match_fields = None
        self._closed = self._failed = self._closing = False
        self._calculation, self._domain = calculation, domain
        self._session, self._backend, self._batch_rows = session_id, backend, batch_rows
        self._consumer = contribution_consumer
        self._quality = Q.NONE
        try:
            # 配置仅保存一次；批内列空间另按当前实际条数预约，不保逐条原文或证明。
            _reserve_owned_ram(self, 65536 + 32 * _metadata_bytes(calculation), '_fixed_cost')
            self._compiled = validate_expression(calculation.expr.text, calculation.expr.bindings, unit=calculation.unit)
            self._has_where = contains_where(self._compiled.root)
            if (self._compiled.normalized_ast != calculation.expr.normalized_ast
                    or repr(self._compiled.root) != repr(calculation.expr.root)):
                raise ValueError('当前消息公式与已校验声明不同')
            if backend == 'numpy':
                self._compiled = pack_requested_lookups(self._compiled)
            self._fields = tuple((name, bindings.resolve(name), can_field_from_key(bindings.resolve(name).field))
                                 for name in self._compiled.dependencies)
            requested_codes = code_dependencies(self._compiled.root)
            if requested_codes:
                self._fields = tuple((name, replace(item, capture_code=True) if name in requested_codes else item, field)
                                     for name, item, field in self._fields)
            # 树只在初始化数一次；运行批次不为计费重新遍历或编码公式。
            pending, node_count = [self._compiled.root], 0
            while pending:
                node = pending.pop()
                node_count += 1
                pending.extend(node.args)
            self._row_cost = 2048 + 2048 * len(self._fields) + 512 * node_count
            self._direction = (None if calculation.disjunction is None else
                               can_field_from_key(bindings.resolve(calculation.disjunction.signal).field))
            # 固定类型约束只整理一次，不在每帧构造新的依赖列表。
            self._match_fields = tuple(field for _, _, field in self._fields)
            if self._direction is not None:
                self._match_fields += (self._direction,)
            self._actual_identity = None
            # 单条累计需要的固定工作区在读输入前预留；多条批仅申请超出部分。
            self._accumulator = LegacySumAccumulator(budget, session_id, calculation.source,
                legacy_policy=calculation.message_policy, backend=backend, max_batch_rows=batch_rows,
                prepay_single=True)
        except BaseException as exc:
            child = getattr(exc, 'legacy_sum_cleanup_owner', None)
            if child is not None:
                self._accumulator = child
            _cleanup_owner(self, exc, 'current_message_calculation_cleanup_owner', '共同消息计算')
            raise

    def _require_open(self):
        """阻止失败后继续交付结果。参数: 无。返回: None。异常: ResultClosedError。"""
        if self._closed or self._closing or self._failed:
            raise ResultClosedError('共同消息计算已关闭、失败或正在清理')

    def _matches(self, update):
        """核真实消息来源后选择本指标帧。参数: update。返回: bool。异常: 类型/身份错。"""
        if not isinstance(update, LegacyDecodedUpdate):
            raise TypeError('共同消息计算需要已投影的真实更新')
        if update.source != self._calculation.source or update.source_ref.session_id != self._session:
            raise ValueError('消息不属于当前来源或会话')
        selector = self._calculation.update_message
        if (update.is_remote or update.is_error or
                (update.channel, update.frame_id) != (selector.channel, selector.frame_id)
                or selector.is_extended is not None and selector.is_extended != update.is_extended
                or selector.is_fd is not None and selector.is_fd != update.is_fd):
            return False
        # 选择器未限制类型时，各依赖仍须来自本条实际帧，不能拿另一帧的同名信号。
        if any(field.is_extended is not None and field.is_extended != update.is_extended
               or field.is_fd is not None and field.is_fd != update.is_fd for field in self._match_fields):
            return False
        # 自动绑定的投影只保留本帧所属信号；真正解码缺值会显式保留None。
        # 显式类型的低层调用仍允许缺键表示缺值，保持原有输入合同。
        if any((field.is_extended is None or field.is_fd is None)
               and field.signal not in update.values for field in self._match_fields):
            return False
        identity = (update.is_extended, update.is_fd)
        if self._actual_identity is not None and self._actual_identity != identity:
            raise ValueError('逐消息选择匹配多种帧类型，请补充is_extended或is_fd')
        self._actual_identity = identity
        if self._domain is not None:
            if update.time_ns is None:
                raise ValueError('有时间筛选的消息不能省略时间')
            return self._domain.start_ns <= update.time_ns < self._domain.end_ns
        return True

    def consume(self, updates):
        """按原序计算有限批；默认只累计，明细仅交给显式回调，不保存历史。

        参数: updates为最多batch_rows条更新的tuple。返回: None。
        异常: 输入/数值/预算/回调/取消错误原样传播；失败后只能close。
        """
        self._require_open()
        selected = columns = context = arrays = floats = missing = nonfinite = contributions = qualities = None
        primary = None
        try:
            if type(updates) is not tuple or len(updates) > self._batch_rows:
                raise ValueError('共同消息计算需要不超批上限的tuple')
            if not updates:
                return
            # 借用输入值，不复制原消息；预付筛选、归一化列、表达式临时列和贡献包装。
            cost = 16384 + len(updates) * self._row_cost
            _reserve_owned_ram(self, cost, '_batch_cost')
            selected = tuple(update for update in updates if self._matches(update))
            if not selected:
                return
            columns = {name: pack_message_values(definition, tuple(update.values.get(field.signal)
                       for update in selected), self._backend) for name, definition, field in self._fields}
            if self._backend == 'numpy':
                arrays = expression_numpy._evaluate(self._compiled.root, columns, len(selected), {})
                floats = to_float_numpy(arrays.value)
                if self._has_where and not floats.valid.all():
                    # 输入错误与算术错误必须分开；只看每条消息实际选到的输入。
                    missing, nonfinite = (numpy_active(self._compiled.root, columns,
                        {name: (col.quality & int(flag)) != 0 for name, col in columns.items()},
                        len(selected)) for flag in (Q.MISSING, Q.NONFINITE))
            contributions = []
            qualities = [] if self._consumer is not None else None
            for index, update in enumerate(selected):
                if self._backend == 'reference':
                    context = {name: scalar_from_column(column, index) for name, column in columns.items()}
                    value = to_float_reference(expression_reference._evaluate(self._compiled.root, context, {}).value)
                else:
                    value = scalar_from_column(floats, index)
                # 保旧原因优先级，缺值明确跳过，不能恢复上一条有效值。
                reason = None
                if not value.valid:
                    if self._has_where and self._backend == 'reference':
                        has_missing, has_nonfinite = (reference_active(self._compiled.root, context,
                            {name: bool(item.quality & flag) for name, item in context.items()})
                            for flag in (Q.MISSING, Q.NONFINITE))
                    elif self._has_where:
                        has_missing, has_nonfinite = missing[index], nonfinite[index]
                    else:
                        flags = [int(column.quality[index]) for column in columns.values()]
                        has_missing = any(flag & int(Q.MISSING) for flag in flags)
                        has_nonfinite = any(flag & int(Q.NONFINITE) for flag in flags)
                    reason = (LegacySkipReason.MISSING_INPUT if has_missing
                              else LegacySkipReason.NONFINITE_INPUT if has_nonfinite
                              else LegacySkipReason.EVALUATION_ERROR)
                contribution_quality = update.quality | value.quality
                if self._direction is not None:
                    quality, keep = direction_bucket_state(update.values.get(self._direction.signal), self._calculation.disjunction.bucket)
                    reason = direction_skip_reason(value, reason, quality, keep)
                    contribution_quality |= quality
                # 业务结果需要的质量直接来自本次求值；未选中的另一桶不制造缺失诊断。
                if reason is not LegacySkipReason.CONDITION_FALSE:
                    self._quality |= value.quality
                    if self._direction is not None:
                        self._quality |= quality
                contributions.append(LegacySumContribution(update,
                    value.value if value.valid and reason is None else None, reason))
                if qualities is not None:
                    qualities.append(contribution_quality)
            self._accumulator.consume(tuple(contributions))
            if self._consumer is not None:
                for contribution, quality in zip(contributions, qualities):
                    self._consumer(contribution, quality)
        except BaseException as exc:
            primary = exc
            self._failed = True
            raise
        finally:
            # 清理先断当前有限列；释放失败仍保owner费用，不能继续累计或返回快照。
            selected = columns = context = arrays = floats = missing = nonfinite = contributions = qualities = None
            try:
                _release_owned_ram(self, self._batch_cost, '_batch_cost')
            except BaseException as cleanup:
                self._failed = True
                if primary is None:
                    raise
                primary.add_note('共同消息批费用清理失败：' + type(cleanup).__name__)

    def snapshot(self):
        """读取当前累计，不冒充文件EOF。参数: 无。返回: LegacySumSnapshot。异常: 状态错。"""
        self._require_open()
        return self._accumulator.snapshot()

    @property
    def quality(self):
        """读取实际参与计算的质量汇总，不构造逐条诊断。参数: 无。返回: QualityFlag。异常: 状态错。"""
        self._require_open()
        return self._quality

    @property
    def closed(self):
        """读取释放完成状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    def close(self):
        """仅关闭自有累计与费用。参数: 无。返回: None。异常: 释放失败保留句柄供重试。"""
        if self._closed:
            return
        self._closing = True
        if self._accumulator is not None:
            self._accumulator.close()
        self._compiled = self._fields = self._match_fields = self._calculation = self._consumer = self._direction = None
        self._actual_identity = None
        _release_owned_ram(self, self._batch_cost, '_batch_cost')
        _release_owned_ram(self, self._fixed_cost, '_fixed_cost')
        self._closed = True
