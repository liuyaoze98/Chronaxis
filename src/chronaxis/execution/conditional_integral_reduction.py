"""为逐块条件积分数值归约和整窗事实提供预算、生命周期及故障清理。

输入为真实观测、原请求及同一后端的有限面积块，结束后借出数值与覆盖事实。
数值核保留有界误差项，事实 owner 保留诊断和完整来源；不保存全部面积或时间轴。
所有状态和候选数组先申请保守 RAM 预算，超限或取消后只允许关闭。
budget 为借用的单线程账本，本 owner 不关闭它；估算不代表全进程 RSS。
不执行文件 I/O、历史读写/解码或最终 CalculationResult 的覆盖状态分类。
"""

# 两核独立，仅在运行 owner 中选择；冻结协议和事实预算允许共享。
from ..core.integral_sum import IntegralSumResult, require_partial_limit
from ..core.integral_sum_reference import ReferenceIntegralSum
from ..core.integral_sum_numpy import NumpyIntegralSum
from ..core.conditional_integral_terms import ReferenceConditionalIntegralTerms, ConditionalIntegralFacts
from ..core.conditional_integral_terms_numpy import NumpyConditionalIntegralTerms
from ..core.calculations import CalculationDefinition, calculation_unit
from ..core.models import Interval, SourceRef
from ..results.budget import ResourceBudget
from ..results.errors import ResultClosedError
from .conditional_integral_facts import ConditionalIntegralFactsAccumulator


class ConditionalIntegralReduction:
    """持有一个积分归约 owner，完成前不开放整窗结果；条件真假与数值未知均在事实owner累计。

    纯核的非有限累计是数值结果故障，仍消费后续事实；协议/容量/预算异常使 owner 失败。
    关闭途中禁止借出引用，释放前取消可重试，释放后取消不会重复扣账。
    借出的结果和事实由本 owner 计费到 close，调用方另行留存须承担预算。
    """

    def __init__(self, budget: ResourceBudget, spec: CalculationDefinition, observation: Interval,
                 input_unit: str, binding_identity: str, source_refs: tuple[SourceRef, ...] = (),
                 backend: str = 'numpy', partial_limit: int = 4096):
        """先申请数值工作空间，再创建独立核和事实 owner。

        参数: budget 为借用账本；spec/observation 为原请求及真实范围；
        input_unit/identity/refs 保留表达式身份；backend 为 reference/numpy；partial_limit 为误差容量。
        返回: None，初始化新 owner。异常: 配置、预算、分配、取消原样传播。
        持续清理失败时原异常.conditional_integral_reduction_cleanup_owner 可用于重试 close。
        """
        # 配置验证不分配面积数组；事实详细门槛由子 owner 原样实施。
        if not isinstance(budget, ResourceBudget) or not isinstance(spec, CalculationDefinition) or spec.operation != 'integral':
            raise TypeError('积分归约需要ResourceBudget和integral CalculationDefinition')
        if type(backend) is not str or backend not in ('reference', 'numpy'):
            raise ValueError('积分归约后端需要reference或numpy')
        limit = require_partial_limit(partial_limit)
        unit, factor = calculation_unit(spec, input_unit)
        # 句柄与计费状态先建立，构造中取消也有可恢复清理入口。
        self._budget, self._backend = budget, backend
        self._unit, self._factor = unit, factor
        self._held_cost = 0
        self._kernel = self._facts_owner = self._result = None
        self._failed = self._finished = self._closing = self._closed = False
        self._numeric_cost = 65536 + 512 * limit
        try:
            # 512 bytes/项覆盖旧/候选误差列、参考 float 对象和数组拆分临时列。
            self._reserve(self._numeric_cost)
            kernel = ReferenceIntegralSum if backend == 'reference' else NumpyIntegralSum
            self._kernel = kernel(limit)
            self._facts_owner = ConditionalIntegralFactsAccumulator(budget, spec, observation, input_unit,
                                                       binding_identity, source_refs)
        except BaseException as exc:
            # 子构造清理持续失败时接管其句柄，不让嵌套 owner 的资源变成不可达。
            child = getattr(exc, 'conditional_integral_facts_cleanup_owner', None)
            if child is not None:
                self._facts_owner = child
            try:
                self.close()
            except BaseException as cleanup:
                exc.add_note(f'积分归约构造清理失败: {type(cleanup).__name__}')
                if not self._closed:
                    # 只重试一次，持续故障由显式恢复句柄处理，不能无限循环。
                    try:
                        self.close()
                    except BaseException as retry:
                        exc.add_note(f'积分归约构造清理重试失败: {type(retry).__name__}')
                        if not self._closed:
                            exc.conditional_integral_reduction_cleanup_owner = self
                            exc.add_note('释放恢复后调用conditional_integral_reduction_cleanup_owner.close()')
            raise

    @property
    def closed(self) -> bool:
        """读取实际关闭状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed  # 以两个 owner 实际归还预算为准。

    @property
    def failed(self) -> bool:
        """读取推进异常状态。参数: 无。返回: bool。异常: 无。"""
        return self._failed  # 与正常交付的数值失败结果不同。

    @property
    def result(self) -> IntegralSumResult:
        """借出完成后的数值结果，不能将前缀当成整窗面积。

        参数: 无。返回: 冻结结果。异常: 关闭、失败或未完成时拒绝。
        """
        self._require_finished()  # 借出引用由本 owner 计费到 close。
        return self._result

    @property
    def facts(self) -> ConditionalIntegralFacts:
        """借出完成后的整窗覆盖、质量及完整来源。

        参数: 无。返回: 冻结事实。异常: 关闭、失败或未完成时拒绝。
        """
        self._require_finished()  # 子 owner 同时验证完整真实交集。
        return self._facts_owner.facts

    def _require_open(self) -> None:
        """拒绝关闭及清理中操作。参数: 无。返回: None。异常: ResultClosedError。"""
        if self._closed or self._closing:
            raise ResultClosedError('积分归约owner已关闭或正在清理')

    def _require_finished(self) -> None:
        """验证借出整窗结果的门槛。参数: 无。返回: None。异常: 生命周期错误。"""
        self._require_open()
        if self._failed or not self._finished:
            raise RuntimeError('整窗积分归约尚未成功完成')

    def _reserve(self, amount: int) -> None:
        """按真实预算增量登记申请，覆盖成功后取消。

        参数: amount 为 bytes。返回: None。异常: 原申请或取消错误。
        """
        before = self._budget.ram_bytes
        try:
            self._budget.reserve_ram(amount)
        finally:
            # 单线程借用账本下，成功申请后的取消也须由本 owner 持有并归还。
            if self._budget.ram_bytes == before + amount:
                self._held_cost += amount

    def _release(self, amount: int) -> None:
        """按真实预算减少持有量，覆盖成功后取消。

        参数: amount 为 bytes。返回: None。异常: 原释放或取消错误。
        """
        before = self._budget.ram_bytes
        try:
            self._budget.release_ram(amount)
        finally:
            # 成功后取消不再重复扣账，释放前取消则保留金额供 close 重试。
            if self._budget.ram_bytes == before - amount:
                self._held_cost -= amount

    def push(self, terms: ReferenceConditionalIntegralTerms | NumpyConditionalIntegralTerms) -> None:
        """即时消费有限面积块及事实，不保留调用方输入数组。

        参数: terms 必须与构造后端一致。返回: None。
        异常: 协议、容量、预算、分配或取消错误；此后只允许 close。
        """
        try:
            self._require_open()
            if self._failed or self._finished:
                raise RuntimeError('失败或完成的积分归约不能追加')
            try:
                # 输入归调用方块 workspace；先计费有效索引/候选列，再执行任何数值核。
                expected = ReferenceConditionalIntegralTerms if self._backend == 'reference' else NumpyConditionalIntegralTerms
                if not isinstance(terms, expected):
                    raise TypeError('积分面积模型与归约后端不一致')
                workspace = 4096 + 64 * len(terms.areas)
                self._reserve(workspace)
                self._facts_owner.push(terms.facts)
                self._kernel.push_values(terms.areas, terms.valid)
                # 输入没有被持有，有限块临时列可归还；固定误差空间留到关闭。
                self._release(workspace)
            except BaseException:
                self._failed = True  # 已推进的前缀不再借出，不假装撤销成功。
                raise
        finally:
            # 原异常及TB仍交调用方；只断本层借入参数、视图和临时，不清外部帧。
            self = terms = None

    def finish(self) -> None:
        """核对整窗事实后归约并应用一次输出单位因子。

        参数: 无。返回: None，重复成功完成无副作用。
        异常: 未覆盖真实目标、预算/分配/取消错误；失败后只允许 close。
        """
        self._require_open()
        if self._failed:
            raise RuntimeError('失败的积分归约只能关闭')
        if self._finished:
            return
        try:
            # 不能从最后一个已见块猜 EOF，数值结果也不能先于覆盖门槛交付。
            self._facts_owner.finish()
            result = self._kernel.finish(self._unit, self._factor)
            self._result = result
            self._finished = True
        except BaseException:
            self._failed = True
            raise

    def close(self) -> None:
        """关闭自有事实与数值状态，保留调用方已有预算。

        参数: 无。返回: None，重复成功关闭无副作用。
        异常: 原释放/取消错误；释放前取消保留句柄和金额供再次 close。
        """
        if self._closed:
            return
        self._closing = True
        try:
            # 子 owner 自行处理释放前后取消；父 owner 不能把子金额当成自己的释放。
            if self._facts_owner is not None:
                self._facts_owner.close()
            self._release(self._held_cost)
        finally:
            # 父释放后取消也可结束；子释放后取消时父金额仍在，需再次 close 收尾。
            child_closed = self._facts_owner is None or self._facts_owner.closed
            if child_closed and self._held_cost == 0:
                self._kernel = self._facts_owner = self._result = None
                self._unit = self._factor = None
                self._closed = True
