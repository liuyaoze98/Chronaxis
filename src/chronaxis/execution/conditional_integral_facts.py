"""逐块累计条件积分的数值/条件覆盖、质量和来源，并为保留的诊断申请预算。

输入为真实观测范围、原 CalculationDefinition 和有限块 ConditionalIntegralFacts；输出为冻结整窗事实。
先检查连续性与未知覆盖，再申请候选工作空间，最后整体替换当前前缀。
值与条件未知分别累计，TRUE选中和FALSE证据独立保留；不保存面积或时间轴，不执行浮点求和、单位转换或 CalculationResult 分类。
未知区间与完整来源可能随窗口增长；超过 ResourceBudget 明确失败，不截断诊断。
预算采用既有保守元数据估算，不代表全进程 RSS；不读写文件或历史快照。
budget 属于调用方。本对象关闭后不再持有 facts；调用方独立保留返回引用须另计预算。
"""

# 复用冻结事实、整数时间及预算协议，数值核仍由两个原积分项后端独立执行。
from ..core.conditional_integral_terms import ConditionalIntegralFacts
from ..core.calculations import CalculationDefinition, calculation_unit
from ..core.models import Interval, SourceRef
from ..core.types import QualityFlag as Q
from ..core.validation import require_text
from ..results.budget import ResourceBudget
from ..results.errors import ResultClosedError
from .history import _metadata_bytes
from .retained_metadata import retained_metadata_bytes, reference_workspace


def _refs_cost(refs: tuple[SourceRef, ...]) -> int:
    """估算完整来源实体及冻结容器，不承担JSON工作副本。

    参数: refs 为调用方已经提供的冻结定位。返回: 保守 bytes。
    异常: ResultFormatError 为既有估算协议无法处理的字段。
    """
    # 逐字段实体估算含实例字典/长文本；2048另覆盖每项持有和局部状态余量。
    try:
        return retained_metadata_bytes(refs) + 2048 * len(refs)
    finally:
        # 费用估算中取消也不让本层参数在TB持有完整定位tuple。
        refs = None


def _unique_refs(existing, incoming):
    """按完整类型和值保留第一次出现的定位，保持原出现顺序。

    参数: existing/incoming 为已校验来源 tuple。返回: 去重后的 tuple。
    异常: MemoryError 为预算已申请后的实际分配失败。
    """
    # 无未计费的全量哈希表；此函数只在调用方已申请候选预算后执行。
    result = None
    try:
        result = list(existing)
        for ref in incoming:
            # 显式短路和原any相同；不留下会在异步取消时保全list的生成器帧。
            duplicate = False
            for old in result:
                if type(ref) is type(old) and ref == old:
                    duplicate = True
                    break
            if not duplicate:
                result.append(ref)
        return tuple(result)
    finally:
        # 原异常TB可以存活；本层新list不能在已抵费栈帧中继续保活。
        result = existing = incoming = ref = old = None


def _join_unknown(existing, incoming):
    """合并连续块边界处及块内相邻的未知范围，不填补有效区间。

    参数: 两个 tuple 均为有序、不重叠的正区间。返回: 紧凑区间 tuple。
    异常: MemoryError 为已申请工作空间内的实际分配失败。
    """
    # 旧范围保持顺序；仅当前末段可能和新段相邻，不能跨有效间隔合并。
    result = None
    try:
        result = list(existing)
        for interval in incoming:
            if result and result[-1].end_ns == interval.start_ns:
                result[-1] = Interval(result[-1].start_ns, interval.end_ns)
            else:
                result.append(interval)
        return tuple(result)
    finally:
        # 只断本层临时引用，调用方原tuple和Interval完全不改。
        result = existing = incoming = interval = None


class ConditionalIntegralFactsAccumulator:
    """持有一个已接收的连续前缀，完整结束后才开放整窗事实。

    构造时固定目标交集；不会从前缀猜测 EOF。失败只允许关闭，完成后拒绝追加。
    所有保留状态及候选容器均先 reserve；预算单线程协议下取消前后精确记账。
    close 释放成功后即结束，即使该次调用随后被取消；释放前取消则可重试。
    """

    def __init__(self, budget: ResourceBudget, spec: CalculationDefinition,
                 observation: Interval, input_unit: str, binding_identity: str,
                 source_refs: tuple[SourceRef, ...] = ()):
        """固定真实观测交集并申请初始状态预算。

        参数: budget 为借用账本；spec 为原积分请求；observation 为真实观测范围；
        input_unit/identity 为原表达式事实；source_refs 为已知完整定位。
        返回: 新 owner。异常: TypeError/ValueError 为协议错误；预算/分配/取消原样传播。
        清理仍失败时，原异常.conditional_integral_facts_cleanup_owner 提供可重试 close 的 owner。
        """
        # 在申请前拒绝非法输入，不把任意对象或缺失观测伪装成空窗口。
        if not isinstance(budget, ResourceBudget) or not isinstance(spec, CalculationDefinition) or spec.operation != 'integral':
            raise TypeError('需要ResourceBudget和integral CalculationDefinition')
        if not isinstance(observation, Interval):
            raise TypeError('观测范围需要真实Interval')
        require_text(input_unit, 'integral.input_unit')
        require_text(binding_identity, 'integral.binding_identity')
        if type(source_refs) is not tuple or any(not isinstance(ref, SourceRef) for ref in source_refs):
            raise TypeError('完整来源需要SourceRef tuple')
        calculation_unit(spec, input_unit)  # 仅校验输出单位兼容性，此处没有数值转换。
        # 沿用积分项的闭合观测交集表示；相接端点保留点事实，不等同于无交集。
        left, right = max(spec.window.start_ns, observation.start_ns), min(spec.window.end_ns, observation.end_ns)
        actual = Interval(left, right) if left <= right else None
        # owner 账本在第一次 reserve 前建立，取消后仍能在构造清理中准确释放。
        self._budget, self._spec, self._actual = budget, spec, actual
        self._unit, self._identity = input_unit, binding_identity
        self._held_cost, self._state = 0, None
        self._closed = self._closing = self._failed = self._finished = False
        self._base_cost = 65536 + 16 * _metadata_bytes((spec, observation, input_unit, binding_identity))
        try:
            # 来源去重容器、冻结状态及旧输入引用均由这次保守申请覆盖。
            self._reserve(self._base_cost + _refs_cost(source_refs)
                          + reference_workspace(0, len(source_refs)))
            refs = _unique_refs((), source_refs)
            self._state = ConditionalIntegralFacts(spec, None, 0, 0, 0, 0, 0, 0, (), (), Q.NONE, input_unit, binding_identity, refs)
            self._release(self._held_cost - self._base_cost - _refs_cost(refs))
        except BaseException as exc:
            # 构造不会正常交付 owner；清理异常不能覆盖原失败或丢掉重试入口。
            try:
                self.close()
            except BaseException as cleanup:
                exc.add_note(f'积分事实构造清理失败: {type(cleanup).__name__}')
                if not self._closed:
                    # 仅一次最小重试，处理清理本身被取消；持续失败不无限循环。
                    try:
                        self.close()
                    except BaseException as retry:
                        exc.add_note(f'积分事实构造清理重试失败: {type(retry).__name__}')
                        if not self._closed:
                            exc.conditional_integral_facts_cleanup_owner = self
                            exc.add_note('释放恢复后调用conditional_integral_facts_cleanup_owner.close()')
            raise
        finally:
            # 快照已由_state或真实恢复owner负责，本层临时tuple不随TB保留。
            refs = None

    @property
    def closed(self):
        """提供关闭状态。参数: 无。返回: bool。异常: 无。"""
        # 是否结束以实际释放结果为准，不能仅凭进入 close 判定。
        return self._closed

    @property
    def failed(self):
        """提供失败状态。参数: 无。返回: bool。异常: 无。"""
        # 推进失败后保留资源供清理，此标志不表示已经关闭。
        return self._failed

    @property
    def facts(self) -> ConditionalIntegralFacts:
        """在完整 finish 后借用冻结整窗事实，不额外复制诊断。

        参数: 无。返回: 原 spec 与完整覆盖/来源事实。异常: 关闭、失败或未完成时拒绝。
        副作用: 返回引用只由本 owner 计费至 close；独立留存由调用方承担。
        """
        # 未完成前缀不能冒充整窗事实，关闭过程中也禁止借出状态。
        self._require_open()
        if self._failed or not self._finished:
            raise RuntimeError('整窗事实尚未成功完成')
        return self._state

    def _require_open(self):
        """拒绝关闭及正在清理时读取或推进。参数: 无。返回: None。异常: ResultClosedError。"""
        if self._closed or self._closing:
            raise ResultClosedError('积分事实owner已关闭或正在清理')

    def _reserve(self, amount):
        """申请前后按真实账本增量登记，覆盖成功后取消。

        参数: amount 为非负 bytes。返回: None。异常: 原预算或取消异常。
        """
        before = self._budget.ram_bytes
        try:
            self._budget.reserve_ram(amount)
        finally:
            # ResourceBudget 单线程契约下，只有成功申请才改变账本。
            if self._budget.ram_bytes == before + amount:
                self._held_cost += amount

    def _release(self, amount):
        """释放前后按真实账本减少持有量，取消后不会再次扣同一笔。

        参数: amount 为 owner 当前持有部分。返回: None。异常: 原释放或取消异常。
        """
        before = self._budget.ram_bytes
        try:
            self._budget.release_ram(amount)
        finally:
            # 释放后取消也已归还；释放前取消仍保留全部持有量，等待 close 重试。
            if self._budget.ram_bytes == before - amount:
                self._held_cost -= amount

    def _validate_block(self, facts):
        """检查当前块接在已接收前缀之后，覆盖事实完整且身份一致。

        参数: facts 为有限块事实。返回: None。异常: TypeError/ValueError 为协议错误。
        """
        # 原请求、单位和绑定身份一致才能连接；不做隐式换单位或重绑定。
        if not isinstance(facts, ConditionalIntegralFacts):
            raise TypeError('需要ConditionalIntegralFacts')
        if not facts.ranges_retained:
            raise ValueError('完整事实归约不能接未保留范围的精简计算事实')
        if facts.spec != self._spec or facts.input_unit != self._unit or facts.binding_identity != self._identity:
            raise ValueError('积分块请求、单位或绑定身份不一致')
        # 固定最终目标；None 不接受人为块，点窗口只允许一次真实点事实。
        block, target = facts.actual_window, self._actual
        if block is None or target is None:
            raise ValueError('没有实际目标或块观测')
        previous = self._state.actual_window
        cursor = target.start_ns if previous is None else previous.end_ns
        if block.start_ns != cursor or block.end_ns > target.end_ns:
            raise ValueError('积分块有缺口、重叠或超出目标')
        if target.start_ns == target.end_ns:
            if previous is not None or block != target:
                raise ValueError('零窗口仅接收一个真实点块')
        elif block.start_ns >= block.end_ns:
            raise ValueError('正窗口不接受不推进的块')
        # 冻结模型已核对两类未知的有序范围和完整时长划分；这里补连续块样本上界。
        if facts.valid_sample_count > facts.selected_duration_ns:
            raise ValueError('选中样本数超过可核实的正整数纳秒时间点')

    def push(self, facts: ConditionalIntegralFacts) -> None:
        """顺序累计一块覆盖事实，面积仍留在调用方的有限块内消费。

        参数: facts 为连续块的真实 ConditionalIntegralFacts。返回: None。
        异常: 协议、预算、分配或取消错误；此后只允许 close。
        """
        # 检查生命周期后才推进，拒绝在失败前缀或已交付整窗结果上追加。
        self._require_open()
        if self._failed or self._finished:
            raise RuntimeError('失败或完成的积分事实owner不能追加')
        old = value_unknown = condition_unknown = refs = candidate = window = None
        try:
            self._validate_block(facts)
            old = self._state
            # 旧refs实体仍在前缀费用内；新候选付指针容器而非旧payload深副本。
            old_dynamic = 4096 * (len(old.value_unknown_ranges) + len(old.condition_unknown_ranges))
            incoming = 4096 * (len(facts.value_unknown_ranges) + len(facts.condition_unknown_ranges)) + _refs_cost(facts.source_refs)
            self._reserve(65536 + old_dynamic + incoming
                          + reference_workspace(len(old.source_refs), len(facts.source_refs)))
            value_unknown = _join_unknown(old.value_unknown_ranges, facts.value_unknown_ranges)
            condition_unknown = _join_unknown(old.condition_unknown_ranges, facts.condition_unknown_ranges)
            refs = _unique_refs(old.source_refs, facts.source_refs)
            window = Interval(self._actual.start_ns, facts.actual_window.end_ns)
            # 两类覆盖与FALSE证据逐整数ns累计；新冻结状态重新核对完整分区。
            candidate = ConditionalIntegralFacts(self._spec, window,
                old.value_valid_duration_ns + facts.value_valid_duration_ns,
                old.condition_known_duration_ns + facts.condition_known_duration_ns,
                old.selected_duration_ns + facts.selected_duration_ns,
                old.selected_value_unknown_duration_ns + facts.selected_value_unknown_duration_ns,
                old.false_duration_ns + facts.false_duration_ns,
                old.valid_sample_count + facts.valid_sample_count, value_unknown, condition_unknown,
                old.quality | facts.quality, self._unit, self._identity, refs)
            # 单个冻结状态原子安装；异常前的前缀不会被零散字段部分更新。
            self._state = candidate
            retained = self._base_cost + 4096 * (len(value_unknown) + len(condition_unknown)) + _refs_cost(refs)
            # 旧状态与临时容器停止持有后，归还保守候选余额。
            old = candidate = None
            self._release(self._held_cost - retained)
        except BaseException as exc:
            # 保留当前可追踪状态及已申请金额，不在异常路径悄悄丢失资源句柄。
            self._failed = True
            exc.conditional_integral_facts_cleanup_owner = self
            raise
        finally:
            # 同时清两类未知候选，避免清理后的原TB保活本层全前缀。
            old = value_unknown = condition_unknown = refs = candidate = window = facts = None

    def finish(self) -> None:
        """确认真实目标全部覆盖；无交集可直接完成，点窗口必须收到点事实。

        参数: 无。返回: None；成功后 facts 可读，重复 finish 无副作用。
        异常: RuntimeError 为失败状态；ValueError 为观测前缀不足。
        """
        self._require_open()
        if self._failed:
            raise RuntimeError('失败owner只能关闭')
        # 不把当前最后一块当 EOF；原始真实交集在构造时已经固定。
        if self._actual is not None and self._state.actual_window != self._actual:
            self._failed = True
            raise ValueError('尚未覆盖完整实际窗口')
        self._finished = True

    def close(self) -> None:
        """归还本 owner 的 RAM；释放前取消可重试，不关闭借用账本。

        参数: 无。返回: None；重复关闭不再扣账。
        异常: 原释放/取消错误，是否已关闭以实际账本释放结果为准。
        """
        if self._closed:
            return
        self._closing = True
        try:
            self._release(self._held_cost)
        finally:
            # 成功释放或成功后取消均清除引用；失败前取消仍保留状态供重试。
            if self._held_cost == 0:
                self._state = self._spec = self._actual = None
                self._unit = self._identity = None
                self._closed = True
