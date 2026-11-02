"""有限步消费已创建的历史指标分块，交付最终条件积分 CalculationResult。

输入为调用方拥有的新鲜 HistoricalConditionalBlocks 及真实观测范围；不自行构造回读组件。
每个 step 最多取得一个有限块，独立面积核生成 Terms，条件归约累计跨块数值与值/条件覆盖、FALSE及真实样本事实。
EOF 后核对完整真实交集；只有正请求充分观测且全FALSE才可返回空选择0，再在已预约元数据空间内按 report/strict 等政策分类。
只拥有取得的当前块、归约及最终结果；借用 blocks/history/budget 均由调用方关闭。
新层 RAM 计费含有限块数组与随未知/来源增长的结果容器，不代表整进程 RSS。
文件读取由被借用的新历史分块执行，本层不写文件、不额外调用旧 reader/decoder。
"""

# 只组合已有真实模块；两条面积/归约数值路径独立，最终分类为共享非数值规则。
from ..core.conditional_integral_result import make_conditional_integral_result
from ..core.integral_sum import require_partial_limit
from ..core.conditional_integral_terms_reference import compute_conditional_integral_terms_reference
from ..core.conditional_integral_terms_numpy import compute_conditional_integral_terms_numpy
from ..core.models import Interval
from ..core.calculations import CalculationResult
from ..results.errors import ResultClosedError
from .history import _metadata_bytes
from .retained_metadata import retained_metadata_bytes
from .historical_conditional_blocks import HistoricalConditionalBlocks
from .conditional_integral_reduction import ConditionalIntegralReduction


class HistoricalConditionalIntegral:
    """持有一次独占推进的积分分析，完成前不开放前缀结果。

    blocks 必须尚未消费，存活期间不能由其他调用者推进；本对象不接管其所有权。
    推进/分类/取消异常后只允许 close，数值失败仍作为完整带诊断的结果交付。
    result 借用至 close；独立保留引用需由调用方另计预算。
    """

    def __init__(self, blocks: HistoricalConditionalBlocks, observation: Interval, *, partial_limit: int = 4096):
        """校验新鲜真实分块者，先预约固定状态再创建自有归约。

        参数: blocks 为已创建的借用分块者；observation 为原真实域；partial_limit 为误差容量。
        返回: None，初始化新的分析 owner。异常: 配置、预算、分配和取消原样传播。
        持续清理失败时原异常.historical_conditional_integral_cleanup_owner 提供重试 close 的句柄。
        """
        # 已有回读构造清理风险不在本层隐藏，必须由调用方先成功创建并保有句柄。
        if not isinstance(blocks, HistoricalConditionalBlocks) or not isinstance(observation, Interval):
            raise TypeError('历史积分需要真实HistoricalConditionalBlocks和Interval')
        if (blocks.closed or blocks.failed or blocks._closing or blocks._done
                or any(block is not None for block in blocks._current) or blocks._results):
            raise ValueError('条件历史积分需要尚未消费且开放的联合分块者')
        # 子对象可能已被错误地提前关闭或清理；先拒绝，再读取其可被清空的请求字段。
        if any(child.closed or child.failed or child._closing for child in blocks._blocks):
            raise ValueError('联合输入的子回读者已关闭、失败或正在清理')
        value_blocks = blocks._blocks[0]
        if value_blocks._spec.operation != 'integral':
            raise ValueError('条件历史积分只支持integral')
        if any(child._pending is not None or child._results or child._done
               for child in blocks._blocks):
            raise ValueError('联合输入的子回读者已被其他调用者推进')
        limit = require_partial_limit(partial_limit)
        left = max(observation.start_ns, value_blocks._spec.window.start_ns)
        right = min(observation.end_ns, value_blocks._spec.window.end_ns)
        actual = Interval(left, right) if left <= right else None
        if actual != blocks._actual:
            raise ValueError('真实观测与分块者的原请求交集不一致')
        # 集成层读取同包既有冻结元数据，身份/单位来自实际compiled，而非外部自由文字。
        self._blocks, self._budget = blocks, blocks._budget
        self._backend = value_blocks._backend
        self._held_cost = 0
        self._reduction = self._current_block = self._result = None
        self._failed = self._finished = self._closed = self._closing = False
        cost = 65536 + 16 * _metadata_bytes((value_blocks._spec, observation, value_blocks._compiled.identity))
        try:
            self._reserve(cost)
            self._reduction = ConditionalIntegralReduction(self._budget, value_blocks._spec, observation,
                                               value_blocks._compiled.root.unit, value_blocks._compiled.identity,
                                               backend=self._backend, partial_limit=limit)
        except BaseException as exc:
            # 自有归约构造持续清理失败时接管其公开恢复句柄，借用blocks仍不关闭。
            child = getattr(exc, 'conditional_integral_reduction_cleanup_owner', None)
            if child is not None:
                self._reduction = child
            try:
                self.close()
            except BaseException as cleanup:
                exc.add_note(f'历史积分构造清理失败: {type(cleanup).__name__}')
                if not self._closed:
                    try:
                        self.close()
                    except BaseException as retry:
                        exc.add_note(f'历史积分构造清理重试失败: {type(retry).__name__}')
                        if not self._closed:
                            exc.historical_conditional_integral_cleanup_owner = self
                            exc.add_note('释放恢复后调用historical_conditional_integral_cleanup_owner.close()')
            raise

    @property
    def closed(self) -> bool:
        """读取实际关闭状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed  # 仅自有金额及子owner已关闭才成立。

    @property
    def failed(self) -> bool:
        """读取操作失败状态。参数: 无。返回: bool。异常: 无。"""
        return self._failed  # 与可交付的数值失败CalculationResult区分。

    @property
    def finished(self) -> bool:
        """读取完整EOF分类事实。参数: 无。返回: bool。异常: 无。"""
        return self._finished  # 已读最后一块不等于分类完成。

    @property
    def result(self) -> CalculationResult:
        """借出完整窗口最终指标，关闭后不再开放。

        参数: 无。返回: CalculationResult。异常: 未完成、失败或关闭时拒绝。
        """
        self._require_open()
        if self._failed or not self._finished:
            raise RuntimeError('历史积分尚未成功完成')
        return self._result  # 所有来源/诊断仍由自有计费状态持有。

    def _require_open(self) -> None:
        """拒绝关闭或清理中操作。参数: 无。返回: None。异常: ResultClosedError。"""
        if self._closed or self._closing:
            raise ResultClosedError('历史积分已关闭或正在清理')

    def _reserve(self, amount: int) -> None:
        """按实际账本增加自有预算，覆盖成功后取消。

        参数: amount 为 bytes。返回: None。异常: 原预算或取消异常。
        """
        before = self._budget.ram_bytes
        try:
            self._budget.reserve_ram(amount)
        finally:
            # 单线程借用账本，成功后取消仍须持有该笔金额供关闭。
            if self._budget.ram_bytes == before + amount:
                self._held_cost += amount

    def _release(self, amount: int) -> None:
        """按实际账本减少自有预算，释放前取消仍可重试。

        参数: amount 为 bytes。返回: None。异常: 原释放或取消异常。
        """
        before = self._budget.ram_bytes
        try:
            self._budget.release_ram(amount)
        finally:
            if self._budget.ram_bytes == before - amount:
                self._held_cost -= amount  # 成功后取消不能再扣同一笔。

    def _finish(self) -> None:
        """在真实EOF后核对覆盖、预约完整元数据空间并分类。

        参数: 无。返回: None。异常: 覆盖、预算、分配或取消错误传播。
        """
        facts = number = result = None
        try:
            self._reduction.finish()
            facts, number = self._reduction.facts, self._reduction.result
            # refs不深复制；两类未知范围分类会分配新容器，按范围数另留实际工作余量。
            self._reserve(65536 + retained_metadata_bytes(facts) + 4096 * (
                len(facts.value_unknown_ranges) + len(facts.condition_unknown_ranges)))
            result = make_conditional_integral_result(facts, number)
            self._result = result
            self._finished = True  # 安装成功才开放整窗结果，完成后不再消费输入。
        finally:
            # 不把已释放费用覆盖的本层完成快照留在失败traceback局部中。
            facts = number = result = None

    def step(self) -> bool:
        """最多消费一个有限指标块；确认EOF并完成分类时返回False。

        参数: 无。返回: True为消费了一块，False为已完成；完成后重复调用安全。
        异常: 真实读取、预算、数值模型、分配、关闭或取消错误；此后只允许close。
        """
        self._require_open()
        if self._failed:
            raise RuntimeError('失败的历史积分只能关闭')
        if self._finished:
            return False
        terms = None
        try:
            # 只把next的StopIteration当EOF，核内异常不能被误解释为成功结束。
            try:
                self._current_block = next(self._blocks)
            except StopIteration:
                self._finish()
                return False
            # 当前块归本次分析所有；面积临时列(N或N-1)在计算前另行保守预约。
            workspace = 65536 + 1024 * len(self._current_block.series.times_ns)
            self._reserve(workspace)
            compute = compute_conditional_integral_terms_reference if self._backend == 'reference' else compute_conditional_integral_terms_numpy
            terms = compute(self._current_block.series, self._blocks._blocks[0]._spec)
            self._reduction.push(terms)
            terms = None  # 不让有限块输出越过其工作空间存活期。
            self._current_block.close()
            self._current_block = None
            self._release(workspace)
            return True
        except BaseException:
            self._failed = True  # 前缀和自有句柄保留以便显式关闭，不交付半成品。
            raise
        finally:
            # 条件分支同样不让push异常的TB钉住本层新面积/选择列。
            terms = None

    def close(self) -> None:
        """关闭自有块、归约和最终结果，不关闭借用分块者或账本。

        参数: 无。返回: None，重复成功关闭无副作用。
        异常: 子关闭或预算取消原样传播；实际释放前后按句柄/账本支持重试。
        """
        if self._closed:
            return
        self._closing = True
        try:
            # 每层只释放自己的金额，不能用总账差额替代未知的借用资源成本。
            if self._current_block is not None:
                self._current_block.close()
                self._current_block = None
            if self._reduction is not None:
                self._reduction.close()
            self._release(self._held_cost)
        finally:
            # 释放后取消也可结束；未关闭的子或当前块保留在owner上供再次close。
            reduction_closed = self._reduction is None or self._reduction.closed
            if self._current_block is None and reduction_closed and self._held_cost == 0:
                self._result = self._reduction = self._blocks = None
                self._closed = True
