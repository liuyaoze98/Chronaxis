"""从有限历史块得到完整的条件时间极值、时间均值或BOOL TRUE时长。

输入是已封存的新解码历史、原保持上下文、实际绑定、值/BOOL条件编译表达式和原指标请求。
每次step最多消费一个有限块；时间均值先取得整窗TRUE选择内的有效总时长，再重放同一新历史。
两遍不再读取原来源，数值分别使用独立参考或NumPy核，最终只换一次单位。
observation显式限制原domain内的计算观测域，条件两路和均值两遍都传同一范围；
None兼容原domain及预算，不证明实际观测，不修改原context、绑定或请求窗口。
完整窗口事实及来源诊断动态计费，超预算明确失败，不保留全窗时间轴或数值列表。
自有分块者、当前块和结果由close释放；借用历史、上下文、绑定及账本保持。
预算为新分析层保守估算，单线程账本交接，不承诺进程RSS或旧缓冲受控。
"""

# 仅组合新历史、独立纯核和既有结果政策，不改变旧来源读取或解码行为。
from ..core.decoded_binding import DecodedBindings
from ..core.expression import CompiledExpression
from ..core.calculations import CalculationDefinition, calculation_unit, make_calculation_result
from ..core.models import Interval
from ..core.time_reduction import TimeReductionResult
from ..core.conditional_time_reduction import ConditionalTimeCalculationFacts
from ..core.types import QualityFlag as Q
from ..results.errors import ResultClosedError
from .history import DecodedHistoryStore, _metadata_bytes
from .hold import HoldContext
from .calculation_blocks import _calculation_observation
from .historical_conditional_blocks import HistoricalConditionalBlocks


def _append_ranges(existing, incoming):
    """合并同一种未知的相邻范围，保留真实已知间隔。

    参数: existing/incoming为已校验有序Interval tuple。返回: 冻结有序tuple。
    异常: ValueError为重叠；实际分配错误传播，调用方须先预约全部候选元数据。
    """
    # 元数据合并不承担数值计算；只在新范围紧接当前末段时合并。
    result = list(existing)
    for item in incoming:
        if result and item.start_ns < result[-1].end_ns:
            raise ValueError('条件时间指标未知范围重叠')
        if result and item.start_ns == result[-1].end_ns:
            result[-1] = Interval(result[-1].start_ns, item.end_ns)
        else:
            result.append(item)
    return tuple(result)


class HistoricalConditionalTimeCalculation:
    """拥有有限分块与完整事实，完整EOF后才开放最终CalculationResult。

    第一遍确定双覆盖与TRUE有效选择的时间均值分母；均值第二遍重新计算相同事实并核对一致。
    失败后只可关闭，清理取消保留自有句柄及金额，不能代扣借用资源。
    """

    def __init__(self, history, context, bindings, compiled, spec, condition, *, backend='numpy',
                 batch_intervals=64, partial_limit=4096, observation=None):
        """校验输入，预留固定状态，再创建自有分块者与纯数值核。

        参数: history/context/bindings/compiled为真实新历史及其原运行契约；condition为BOOL条件；spec为
            带BOOL选择条件的min_time/max_time/time_weighted_mean/duration；backend为两实际后端之一；
            batch_intervals限制每块正区间数，partial_limit限制浮点误差状态项数。
            observation为原domain内已核实Interval；None兼容原domain及原预算。
        返回: 尚未消费历史的新owner。
        异常: 类型、能力、预算或构造错误；持续清理失败的原异常附
            historical_conditional_time_calculation_cleanup_owner，恢复环境后可调用其close。
        """
        # 所有来源身份仍由真实分块者校验；本层先拒绝错误模型和未接线能力。
        if (not isinstance(history, DecodedHistoryStore) or not isinstance(context, HoldContext)
                or not isinstance(bindings, DecodedBindings) or not isinstance(compiled, CompiledExpression)
                or not isinstance(spec, CalculationDefinition) or not isinstance(condition, CompiledExpression)):
            raise TypeError('历史时间指标需真实历史、保持上下文、运行绑定、表达式和CalculationDefinition')
        if spec.operation not in ('min_time', 'max_time', 'time_weighted_mean', 'duration'):
            raise ValueError('当前条件时间归约只接时间极值、均值及BOOL时长')
        if (backend not in ('reference', 'numpy') or type(batch_intervals) is not int
                or batch_intervals < 1 or type(partial_limit) is not int or partial_limit < 1):
            raise ValueError('历史时间指标需合法后端、正块大小与误差项容量')
        # TRUE选择/值覆盖均使用同一个计算域，不改变原上下文或来源同步身份。
        observed = _calculation_observation(context, observation)
        left = max(observed.start_ns, spec.window.start_ns)
        right = min(observed.end_ns, spec.window.end_ns)
        self._actual = Interval(left, right) if left <= right else None
        self._history, self._context, self._bindings = history, context, bindings
        self._observation = observation
        self._compiled, self._spec, self._condition, self._backend = compiled, spec, condition, backend
        self._batch_intervals, self._partial_limit = batch_intervals, partial_limit
        self._budget, self._held_cost = history.budget, 0
        self._blocks = self._current = self._reducer = self._result = self._first_facts = None
        self._closed = self._closing = self._failed = self._finished = False
        self._second_pass = False
        self._fact_cost = 0
        self._reset_facts()
        try:
            # 允许新旧均值核短暂重叠；动态未知/完整refs与有限数组另行先预约。
            self._reserve(131072 + 1024 * partial_limit +
                          16 * _metadata_bytes((context, bindings.sources, compiled.identity, condition.identity, spec))
                          + (0 if observation is None else 16 * _metadata_bytes(observation)))
            self._reducer = self._make_reducer()
            self._blocks = self._make_blocks()
        except BaseException as exc:
            # 分块构造尚未赋值时，接管其已公开的自有恢复句柄，借用历史仍不关闭。
            child = getattr(exc, 'conditional_blocks_cleanup_owner', None)
            if child is not None:
                self._blocks = child
            try:
                self.close()
            except BaseException as cleanup:
                exc.add_note(f'历史时间指标构造清理失败: {type(cleanup).__name__}')
                if not self._closed:
                    try:
                        self.close()
                    except BaseException as retry:
                        exc.add_note(f'历史时间指标构造清理重试失败: {type(retry).__name__}')
                        if not self._closed:
                            exc.historical_conditional_time_calculation_cleanup_owner = self
            raise

    def _make_reducer(self, denominator=None):
        """创建当前后端纯核，均值分母只来自第一遍完整事实。

        参数: denominator为有效时长ns或第一遍None。返回: 对应独立TimeReduction。
        异常: 配置、数值模型或分配错误传播。
        """
        if self._backend == 'reference':
            from ..core.conditional_time_reduction_reference import ReferenceConditionalTimeReduction
            factory = ReferenceConditionalTimeReduction
        else:
            from ..core.conditional_time_reduction_numpy import NumpyConditionalTimeReduction
            factory = NumpyConditionalTimeReduction
        # 静态表达式已有合法dtype/单位；每个块仍须由纯核验证实际一致性。
        return factory(self._spec, self._compiled.root.unit, self._compiled.root.dtype,
                       selected_duration_ns=denominator, partial_limit=self._partial_limit)

    def _make_blocks(self):
        """重新回读同一封存新历史，不再次扫描原来源。

        参数: 无。返回: 新HistoricalConditionalBlocks。异常: 原构造/身份/预算错误。
        """
        # 含time_weighted_mean第二遍的每次新块源都保留相同显式域，两个条件输入再共同传播。
        return HistoricalConditionalBlocks(self._history, self._context, self._bindings,
                                      self._compiled, self._spec, self._condition, backend=self._backend,
                                      batch_intervals=self._batch_intervals, observation=self._observation)

    def _reset_facts(self):
        """清空本遍计数，新空tuple不复制旧未知诊断。

        参数: 无。返回: None。异常: 无。
        """
        self._cursor = None if self._actual is None else self._actual.start_ns
        self._value_duration = self._selected_duration = self._sample_count = 0
        self._unknown, self._condition_unknown, self._refs, self._quality = (), (), (), Q.NONE
        self._known_duration = self._selected_value_unknown = self._false_duration = self._selected_false_duration = 0

    @property
    def closed(self):
        """读取实际关闭状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    @property
    def failed(self):
        """读取操作失败状态。参数: 无。返回: bool。异常: 无。"""
        return self._failed

    @property
    def finished(self):
        """读取完整分类状态。参数: 无。返回: bool。异常: 无。"""
        return self._finished

    @property
    def result(self):
        """借出完整窗口结果，close后不再开放。

        参数: 无。返回: CalculationResult。异常: 未完成/失败/关闭时拒绝。
        """
        self._require_open()
        if self._failed or not self._finished:
            raise RuntimeError('历史时间指标尚未成功完成')
        return self._result

    def _require_open(self):
        """拒绝半关闭或已关闭操作。参数: 无。返回: None。异常: ResultClosedError。"""
        if self._closed or self._closing:
            raise ResultClosedError('历史时间指标已关闭或正在清理')

    def _reserve(self, amount):
        """先申请本owner费用，并按实际账本接管成功后取消。

        参数: amount为bytes。返回: None。异常: 预算或取消错误。
        """
        before = self._budget.ram_bytes
        try:
            self._budget.reserve_ram(amount)
        finally:
            if self._budget.ram_bytes == before + amount:
                self._held_cost += amount

    def _release(self, amount):
        """扣账后即更新自有金额，释放前取消保留重试。

        参数: amount为bytes。返回: None。异常: 原释放/取消错误。
        """
        before = self._budget.ram_bytes
        try:
            self._budget.release_ram(amount)
        finally:
            if self._budget.ram_bytes == before - amount:
                self._held_cost -= amount

    def _append_facts(self, facts):
        """核对连续完整划分，先计费再保存未知区间和完整来源。

        参数: facts为纯核当前有限ConditionalTimeCalculationFacts。返回: None。
        异常: 结构、身份、重复范围、预算或复制失败，此后只可关闭。
        """
        if (not isinstance(facts, ConditionalTimeCalculationFacts) or not facts.ranges_retained or facts.spec != self._spec
                or facts.input_unit != self._compiled.root.unit or facts.dtype != self._compiled.root.dtype
                or facts.binding_identity != self._compiled.identity):
            raise ValueError('时间指标块事实与原请求或真实表达式不同')
        actual = facts.actual_window
        if actual is None:
            if self._actual is not None:
                raise ValueError('时间指标块缺失真实交集')
        else:
            if self._actual is None or actual.start_ns != self._cursor or actual.end_ns > self._actual.end_ns:
                raise ValueError('时间指标块必须按原请求真实交集连续推进')
            unknown = sum(item.end_ns - item.start_ns for item in facts.value_unknown_ranges)
            if unknown + facts.value_valid_duration_ns != actual.end_ns - actual.start_ns:
                raise ValueError('时间指标块有效与未知未完整划分')
        # 候选复制期间旧事实仍存在；保守金额含旧/新完整元数据，不靠固定64KiB容纳长诊断。
        candidate_cost = 65536 + 16 * (_metadata_bytes((self._unknown, self._condition_unknown, self._refs)) + _metadata_bytes(facts))
        self._reserve(candidate_cost)
        # 两类未知分别合并，不能将值缺失与条件UNKNOWN相互覆盖或填补已知洞。
        value_unknown = _append_ranges(self._unknown, facts.value_unknown_ranges)
        condition_unknown = _append_ranges(self._condition_unknown, facts.condition_unknown_ranges)
        refs = list(self._refs)
        for item in facts.source_refs:
            if not any(type(item) is type(previous) and item == previous for previous in refs):
                refs.append(item)
        # 只安装已验证候选；即便随后释放取消，本owner仍拥有足够金额并禁止交付前缀。
        old_cost = self._fact_cost
        self._unknown, self._condition_unknown, self._refs = value_unknown, condition_unknown, tuple(refs)
        self._value_duration += facts.value_valid_duration_ns
        self._selected_duration += facts.selected_duration_ns
        self._sample_count += facts.valid_sample_count
        self._known_duration += facts.condition_known_duration_ns
        self._selected_value_unknown += facts.selected_value_unknown_duration_ns
        self._false_duration += facts.false_duration_ns
        self._selected_false_duration += facts.selected_false_duration_ns
        self._quality |= facts.quality
        self._cursor = None if actual is None else actual.end_ns
        self._fact_cost = candidate_cost
        self._release(old_cost)

    def _facts_snapshot(self):
        """完整EOF后构造本遍事实，不能以未完前缀冒充整窗。

        参数: 无。返回: ConditionalTimeCalculationFacts。异常: 完整范围或覆盖矛盾。
        """
        if self._actual is not None and self._cursor != self._actual.end_ns:
            raise ValueError('时间指标尚未完整消费真实交集')
        duration = 0 if self._actual is None else self._actual.end_ns - self._actual.start_ns
        if self._value_duration + sum(item.end_ns - item.start_ns for item in self._unknown) != duration:
            raise ValueError('时间指标全窗覆盖划分不完整')
        # 条件分区也必须覆盖全部实际域；FALSE已知，不能计入条件未知。
        if self._known_duration + sum(item.end_ns - item.start_ns for item in self._condition_unknown) != duration:
            raise ValueError('条件时间指标全窗条件覆盖划分不完整')
        return ConditionalTimeCalculationFacts(self._spec, self._actual, self._value_duration,
            self._known_duration, self._selected_duration, self._selected_value_unknown,
            self._false_duration, self._selected_false_duration, self._sample_count,
            self._unknown, self._condition_unknown, self._quality, self._compiled.root.unit,
            self._compiled.root.dtype, self._compiled.identity, self._refs)

    def _finish_pass(self):
        """均值第一遍切换到第二遍，或完整分类最终结果。

        参数: 无。返回: True表示进入第二遍，False表示最终完成。
        异常: 覆盖/数值/新分块构造/预算或取消错误传播。
        """
        # 事实模型和最终分类复制都先预约，借出的第一遍完整诊断也保持计费。
        self._reserve(65536 + 16 * _metadata_bytes((self._unknown, self._condition_unknown, self._refs)))
        facts = self._facts_snapshot()
        if self._spec.operation == 'time_weighted_mean' and not self._second_pass and facts.selected_duration_ns > 0:
            self._first_facts = facts
            self._blocks.close()
            self._blocks = None
            self._reducer = self._make_reducer(facts.selected_duration_ns)
            self._second_pass = True
            # 第一遍诊断由_first_facts持有，其费用保留至close；第二遍另行计费。
            self._fact_cost = 0
            self._reset_facts()
            try:
                self._blocks = self._make_blocks()
            except BaseException as exc:
                child = getattr(exc, 'conditional_blocks_cleanup_owner', None)
                if child is not None:
                    self._blocks = child
                raise
            return True
        if self._second_pass and facts != self._first_facts:
            raise ValueError('两遍时间均值的真实覆盖或来源不同')
        if self._spec.operation == 'time_weighted_mean' and not self._second_pass:
            # 全未知或无观测不构造空归约正常0，也不调用第一遍禁止的数值finish。
            unit, _ = calculation_unit(self._spec, facts.input_unit)
            number = TimeReductionResult(None, unit, False, Q.NONE, 0)
        else:
            number = self._reducer.finish()
        duration = 0 if facts.actual_window is None else facts.actual_window.end_ns - facts.actual_window.start_ns
        # 外条件充分全FALSE才证明空选择；主BOOL FALSE且外TRUE的正常零由数值核证据给出。
        all_false = (facts.actual_window == self._spec.window and duration > 0
                     and facts.false_duration_ns == duration)
        self._result = make_calculation_result(self._spec, facts, number.value, number.unit, facts.actual_window,
            facts.value_valid_duration_ns, facts.condition_known_duration_ns, facts.selected_duration_ns,
            facts.selected_value_unknown_duration_ns, facts.valid_sample_count,
            facts.value_unknown_ranges, facts.condition_unknown_ranges, facts.quality | number.quality,
            all_false=all_false, calculation_failed=number.calculation_failed)
        self._finished = True
        return False

    def step(self):
        """处理至多一个有限块；换遍继续True，最终完整分类才返回False。

        参数: 无。返回: bool；完成后重复False。异常: 读取/数值/预算/取消错误，随后仅close。
        """
        self._require_open()
        if self._failed:
            raise RuntimeError('失败的时间指标只能关闭')
        if self._finished:
            return False
        try:
            try:
                self._current = next(self._blocks)
            except StopIteration:
                return self._finish_pass()
            # 按当前有限行数和完整来源预约纯核数组、权重及事实临时，不保存所有窗口值。
            series = self._current.series
            workspace = 65536 + 2048 * len(series.times_ns) + 16 * _metadata_bytes(series.source_refs)
            self._reserve(workspace)
            facts = self._reducer.push(series)
            self._append_facts(facts)
            del facts, series
            self._current.close()
            self._current = None
            self._release(workspace)
            return True
        except BaseException:
            self._failed = True
            raise

    def close(self):
        """关闭自有当前块/分块者和金额，保留借用历史及原调用方状态。

        参数: 无。返回: None，重复关闭安全。异常: 关闭或释放取消可重试。
        """
        if self._closed:
            return
        self._closing = True
        try:
            if self._current is not None:
                self._current.close()
                self._current = None
            if self._blocks is not None:
                self._blocks.close()
                self._blocks = None
            self._release(self._held_cost)
        finally:
            if self._current is None and self._blocks is None and self._held_cost == 0:
                self._result = self._reducer = self._first_facts = None
                self._history = self._context = self._bindings = self._compiled = self._condition = None
                self._observation = None
                self._unknown = self._condition_unknown = self._refs = ()
                self._closed = True
