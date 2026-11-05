"""从有限历史块得到完整的样本极值或算术均值，可附独立BOOL选择条件。

输入是已封存的新解码历史、原保持上下文、实际绑定、编译表达式和原指标请求。
每次step最多消费一个有限块；均值不建立第二遍块源，也不重新扫描原来源。
样本均值累计原序真实更新的原单位总和，完整EOF后除总样本数并换单位一次。
TTL、条件更新和裁剪保持不增加样本；完整双覆盖、未知和来源动态先预约费用。
observation显式限制原domain内的计算观测域，样本只取该域半开范围内真实更新；
None兼容原domain及原预算，不证明实际观测。原context、绑定和请求窗口不改变。
自有分块者、当前块、数值状态和结果由close释放；借用历史、上下文与绑定保持。
预算是新分析层保守估算，超限明确失败，不承诺进程RSS或旧来源缓冲受控。
"""

# 只组合新分析分块者、独立样本核和既有结果政策，历史读写与解码保持原样。
from ..core.moments import SAMPLE_MOMENTS
from ..core.quantiles import SAMPLE_QUANTILES
from ..core.decoded_binding import DecodedBindings
from ..core.expression import CompiledExpression
from ..core.calculations import CalculationDefinition, make_calculation_result
from ..core.models import Interval
from ..core.sample_reduction import SampleCalculationFacts
from ..core.types import QualityFlag as Q
from ..results.errors import ResultClosedError
from .history import DecodedHistoryStore, _metadata_bytes
from .hold import HoldContext
from .calculation_blocks import HistoricalCalculationBlocks, _calculation_observation
from .historical_conditional_blocks import HistoricalConditionalBlocks


def _append_ranges(existing, incoming):
    """合并同一种未知的相邻范围，保留真实已知间隔。

    参数: existing/incoming为已校验有序Interval tuple。返回: 冻结有序tuple。
    异常: ValueError为重叠；分配错误传播，调用方须先预约全部候选元数据。
    """
    # 仅合并首尾相接的诊断，不填补中间已知值或可判断条件。
    result = list(existing)
    for item in incoming:
        if result and item.start_ns < result[-1].end_ns:
            raise ValueError('样本指标未知范围重叠')
        if result and item.start_ns == result[-1].end_ns:
            result[-1] = Interval(result[-1].start_ns, item.end_ns)
        else:
            result.append(item)
    return tuple(result)


class HistoricalSampleCalculation:
    """拥有一次有限回读及整窗事实，完整EOF后才开放最终CalculationResult。

    极值只留单候选，均值只留有界误差项和真实样本数，不累计全窗值列。
    数值故障与覆盖事实分开；操作异常后只可close，清理取消保留重试金额和句柄。
    """

    def __init__(self, history, context, bindings, compiled, spec, condition=None, *,
                 backend='numpy', batch_intervals=64, partial_limit=4096, observation=None):
        """校验输入，预留固定状态，再创建自有分块者和纯样本核。

        参数: history/context/bindings/compiled为真实新历史及原运行契约；spec为三samples请求；
            condition为可选BOOL表达式，None表示全TRUE；backend为reference或numpy；
            batch_intervals为有限正区间数，partial_limit为浮点误差项容量。
            observation为原domain内已核实Interval；None保留原domain，不是观测证明。
        返回: 尚未消费历史的新owner。
        异常: 类型、能力、预算或构造错误；持续清理失败的原异常附
            historical_sample_calculation_cleanup_owner，恢复环境后可调用其close。
        """
        # 来源身份与BOOL条件仍由真实分块者校验；本层先拒绝模型和能力错误。
        if (not isinstance(history, DecodedHistoryStore) or not isinstance(context, HoldContext)
                or not isinstance(bindings, DecodedBindings) or not isinstance(compiled, CompiledExpression)
                or not isinstance(spec, CalculationDefinition)
                or condition is not None and not isinstance(condition, CompiledExpression)):
            raise TypeError('历史样本指标需真实历史、保持上下文、绑定、表达式和CalculationDefinition')
        if spec.operation not in ('sample_count', 'sample_minimum', 'sample_maximum', 'sample_mean', *SAMPLE_MOMENTS, *SAMPLE_QUANTILES):
            raise ValueError('当前样本归约只接三种samples算子')
        if (backend not in ('reference', 'numpy') or type(batch_intervals) is not int
                or batch_intervals < 1 or type(partial_limit) is not int or partial_limit < 1):
            raise ValueError('历史样本指标需合法后端、正块大小与误差项容量')
        # 冻结原请求的真实交集和初始自有状态，借用资源只保存引用，不接管其生命周期。
        observed = _calculation_observation(context, observation)
        left = max(observed.start_ns, spec.window.start_ns)
        right = min(observed.end_ns, spec.window.end_ns)
        self._actual = Interval(left, right) if left <= right else None
        self._history, self._context, self._bindings = history, context, bindings
        self._observation = observation
        self._compiled, self._spec, self._condition, self._backend = compiled, spec, condition, backend
        self._batch_intervals, self._partial_limit = batch_intervals, partial_limit
        self._budget, self._held_cost = history.budget, 0
        self._blocks = self._current = self._reducer = self._result = None
        self._closed = self._closing = self._failed = self._finished = False
        self._fact_cost = 0
        self._cursor = None if self._actual is None else self._actual.start_ns
        self._value_duration = self._selected_duration = self._sample_count = 0
        self._known_duration = self._selected_value_unknown = self._false_duration = 0
        self._unknown, self._condition_unknown, self._refs, self._quality = (), (), (), Q.NONE
        try:
            # 固定有界误差状态与原契约先计费，动态诊断与有限核工作区另行预约。
            identity = None if condition is None else condition.identity
            self._reserve(131072 + 1024 * partial_limit +
                          16 * _metadata_bytes((context, bindings.sources, compiled.identity, identity, spec))
                          + (0 if observation is None else 16 * _metadata_bytes(observation)))
            self._reducer = self._make_reducer()
            self._blocks = self._make_blocks()
        except BaseException as exc:
            # 子构造未返回时接管其原异常上的实际自有恢复句柄，不关闭借用历史。
            attr = 'calculation_blocks_cleanup_owner' if condition is None else 'conditional_blocks_cleanup_owner'
            child = getattr(exc, attr, None)
            if child is not None:
                self._blocks = child
            try:
                self.close()
            except BaseException as cleanup:
                exc.add_note(f'历史样本指标构造清理失败: {type(cleanup).__name__}')
                if not self._closed:
                    try:
                        self.close()
                    except BaseException as retry:
                        exc.add_note(f'历史样本指标构造清理重试失败: {type(retry).__name__}')
                        if not self._closed:
                            exc.historical_sample_calculation_cleanup_owner = self
            raise

    def _make_reducer(self):
        """创建所选后端的独立样本核，不需要预先知道均值分母。

        参数: 无。返回: 对应SampleReduction。异常: 原配置、数值模型或分配错误。
        """
        if self._backend == 'reference':
            from ..core.sample_reduction_reference import ReferenceSampleReduction
            factory = ReferenceSampleReduction
        else:
            from ..core.sample_reduction_numpy import NumpySampleReduction
            factory = NumpySampleReduction
        # 实际每块仍校验unit/dtype，均值计数来自原值实际更新，不能按块数平均。
        return factory(self._spec, self._compiled.root.unit, self._compiled.root.dtype,
                       partial_limit=self._partial_limit, quantile_budget=self._budget)

    def _make_blocks(self):
        """创建一次自有历史回读者，按可选条件选择单源或联合边界。

        参数: 无。返回: HistoricalCalculationBlocks或HistoricalConditionalBlocks。
        异常: 原构造、身份、条件或预算错误；持续清理入口由构造调用方接管。
        """
        # 同一观测域决定半开真实样本截止；条件两路不能回退到原domain。
        if self._condition is None:
            return HistoricalCalculationBlocks(self._history, self._context, self._bindings,
                self._compiled, self._spec, backend=self._backend, batch_intervals=self._batch_intervals,
                observation=self._observation)
        return HistoricalConditionalBlocks(self._history, self._context, self._bindings,
            self._compiled, self._spec, self._condition, backend=self._backend,
            batch_intervals=self._batch_intervals, observation=self._observation)

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
        """借出完整窗口结果，关闭或失败后不再开放。

        参数: 无。返回: CalculationResult。异常: 未完成/失败/关闭时拒绝。
        """
        self._require_open()
        if self._failed or not self._finished:
            raise RuntimeError('历史样本指标尚未成功完成')
        return self._result

    def _require_open(self):
        """拒绝半关闭或已关闭操作。参数: 无。返回: None。异常: ResultClosedError。"""
        if self._closed or self._closing:
            raise ResultClosedError('历史样本指标已关闭或正在清理')

    def _reserve(self, amount):
        """先申请本owner费用，按实际账本接管成功后取消。

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

        参数: amount为bytes。返回: None。异常: 原释放或取消错误。
        """
        before = self._budget.ram_bytes
        try:
            self._budget.release_ram(amount)
        finally:
            if self._budget.ram_bytes == before - amount:
                self._held_cost -= amount

    def _append_facts(self, facts):
        """核对连续完整划分，先计费再保存双未知和完整来源。

        参数: facts为纯核当前有限SampleCalculationFacts。返回: None。
        异常: 结构、身份、重复范围、预算或复制失败，此后只可关闭。
        """
        if (not isinstance(facts, SampleCalculationFacts) or facts.spec != self._spec
                or facts.input_unit != self._compiled.root.unit or facts.dtype != self._compiled.root.dtype
                or facts.binding_identity != self._compiled.identity):
            raise ValueError('样本块事实与原请求或真实表达式不同')
        actual = facts.actual_window
        if actual is None:
            if self._actual is not None:
                raise ValueError('样本块缺失真实交集')
        elif self._actual is None or actual.start_ns != self._cursor or actual.end_ns > self._actual.end_ns:
            raise ValueError('样本块必须按真实交集连续推进')
        # 候选复制时旧事实仍存在，动态计费含双未知及完整SourceRef子类的全部定位。
        candidate_cost = 65536 + 16 * (_metadata_bytes((self._unknown, self._condition_unknown, self._refs))
                                     + _metadata_bytes(facts))
        self._reserve(candidate_cost)
        value_unknown = _append_ranges(self._unknown, facts.value_unknown_ranges)
        condition_unknown = _append_ranges(self._condition_unknown, facts.condition_unknown_ranges)
        refs = list(self._refs)
        for item in facts.source_refs:
            if not any(type(item) is type(previous) and item == previous for previous in refs):
                refs.append(item)
        # 只安装已校验候选；释放旧费用取消时，全部金额仍归本owner，不能交付前缀结果。
        old_cost = self._fact_cost
        self._unknown, self._condition_unknown, self._refs = value_unknown, condition_unknown, tuple(refs)
        self._value_duration += facts.value_valid_duration_ns
        self._selected_duration += facts.selected_duration_ns
        self._sample_count += facts.valid_sample_count
        self._known_duration += facts.condition_known_duration_ns
        self._selected_value_unknown += facts.selected_value_unknown_duration_ns
        self._false_duration += facts.false_duration_ns
        self._quality |= facts.quality
        self._cursor = None if actual is None else actual.end_ns
        self._fact_cost = candidate_cost
        self._release(old_cost)

    def _facts_snapshot(self):
        """完整EOF后构造整窗事实，不以未完成前缀冒充整窗。

        参数: 无。返回: SampleCalculationFacts。异常: 完整范围或双覆盖矛盾。
        """
        if self._actual is not None and self._cursor != self._actual.end_ns:
            raise ValueError('样本指标尚未完整消费真实交集')
        duration = 0 if self._actual is None else self._actual.end_ns - self._actual.start_ns
        # 两个独立分区均需覆盖实际域，FALSE已知，不能计入条件未知。
        if self._value_duration + sum(item.end_ns - item.start_ns for item in self._unknown) != duration:
            raise ValueError('样本全窗值覆盖不完整')
        if self._known_duration + sum(item.end_ns - item.start_ns for item in self._condition_unknown) != duration:
            raise ValueError('样本全窗条件覆盖不完整')
        return SampleCalculationFacts(self._spec, self._actual, self._value_duration,
            self._known_duration, self._selected_duration, self._selected_value_unknown,
            self._false_duration, self._sample_count, self._unknown, self._condition_unknown,
            self._quality, self._compiled.root.unit, self._compiled.root.dtype,
            self._compiled.identity, self._refs)

    def _finish(self):
        """按完整事实和最终数值分类一次，原序样本和无需第二遍。

        参数: 无。返回: False表示最终完成。异常: 覆盖、数值快照、预算或取消错误。
        """
        # 快照与分类复制前先预约完整双未知和来源；费用持有至close，不是临时裸分配。
        self._reserve(65536 + 16 * _metadata_bytes((self._unknown, self._condition_unknown, self._refs)))
        facts = self._facts_snapshot()
        number = self._reducer.finish()
        duration = 0 if facts.actual_window is None else facts.actual_window.end_ns - facts.actual_window.start_ns
        # 只有请求全窗充分FALSE才证明空选择；无真实样本与UNKNOWN仍按既有政策区分。
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
        """处理至多一个有限块，完整EOF分类后才返回False。

        参数: 无。返回: bool；完成后重复False。异常: 读取/数值/预算/取消错误，随后仅close。
        """
        self._require_open()
        if self._failed:
            raise RuntimeError('失败的样本指标只能关闭')
        if self._finished:
            return False
        try:
            try:
                self._current = next(self._blocks)
            except StopIteration:
                return self._finish()
            # 有限N行数组、掩码和样本临时先预约；不累积全窗值，原单位总和只留有界状态。
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
        """关闭自有当前块、分块者和金额，保留借用历史及原调用方状态。

        参数: 无。返回: None，重复关闭安全。异常: 关闭或释放取消可重试。
        """
        if self._closed:
            return
        # 进入清理即禁止结果访问；每个自有句柄仅在close成功后移除，取消时留待重试。
        self._closing = True
        try:
            if self._current is not None:
                self._current.close()
                self._current = None
            if self._blocks is not None:
                self._blocks.close()
                self._blocks = None
            if self._reducer is not None:
                self._reducer.close()
            self._release(self._held_cost)
        finally:
            # 所有句柄已释放且实际自有金额为0才清空状态；不拿借用账本总额充当关闭证明。
            if self._current is None and self._blocks is None and self._held_cost == 0:
                self._result = self._reducer = None
                self._history = self._context = self._bindings = self._compiled = self._condition = None
                self._observation = None
                self._unknown = self._condition_unknown = self._refs = ()
                self._closed = True
