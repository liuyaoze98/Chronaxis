"""从有限历史输入逐行借出真实更新的SelectionRow，保留TRUE与UNKNOWN。

输入为已封存的新解码历史、保持上下文、实际绑定、值表达式、select请求和可选
BOOL条件。只回读新历史，由原单值/联合分块者保留TTL、同刻和半开更新标志；
每块复用独立select_reference或select_numpy，不重扫来源adapter，不物化全窗行表。
FALSE过滤，UNKNOWN诊断行保留；数值行按已核实的目标单位换算。
observation显式限制原domain内的计算域；该域右端点及之后的真实更新和UNKNOWN行
不再输出。None兼容原domain及预算，不证明实际观测，不改变原context、绑定或请求。

资源分为七类：借用history、context、bindings及共享budget不由本owner关闭；自有
分块者及其回读/登记归_blocks，单当前CalculationBlock归_current，选择核生成器及有限
数组/索引归_rows；固定描述费用由_held_cost持有，核workspace归_workspace_cost，
单当前借出行及完整定位归_row/_row_cost。核和行分配前预约费用，取消按真实账本
更新归属，生成器close成功才丢句柄。返回行只借出至下一次next或close；外部独立
保存行须另计预算，ResultSpool编码/写入费用也另付。不承诺旧来源缓冲或进程RSS。
"""

# 仅组合有限新历史分块与现有独立选择核，不修改完整核或结果schema。
from dataclasses import replace
from ..core.decoded_binding import DecodedBindings
from ..core.expression import CompiledExpression
from ..core.calculations import CalculationDefinition
from ..core.calculations_memory_reference import require_calculation_plan
from ..results.errors import ResultClosedError
from .history import DecodedHistoryStore, _metadata_bytes
from .hold import HoldContext
from .calculation_blocks import HistoricalCalculationBlocks, _calculation_observation
from .historical_conditional_blocks import HistoricalConditionalBlocks


class HistoricalSelectionRows:
    """拥有单当前块、有限核生成器和当前行费用，失败后只可重试关闭。

    数值与筛选由所选独立核完成，strict/minimum_coverage沿原行流语义，不造伪标量。
    exhausted为正常EOF，与显式closed不同；EOF释放回读、当前块、核与行，固定描述费用保留至close。
    再次next仍StopIteration，不将耗尽当作显式关闭。
    任何清理失败保留实际句柄及金额，半关闭后不再交付行，不关闭借用历史或原状态。
    """

    def __init__(self, history, context, bindings, compiled, spec, condition=None, *,
                 backend='numpy', batch_intervals=64, observation=None):
        """检查真实select契约，先计费固定描述，再构造自有分块者。

        参数: history/context/bindings/compiled为真实新历史及原执行契约，spec为select；
            condition为可选同绑定BOOL条件；backend为reference/numpy，batch_intervals为正区间上限。
            observation为原domain内已核实Interval；None兼容原domain及原预算。
        返回: 尚未消费历史的行owner。异常: 类型、能力、同步、预算、构造或取消错误；
            持续清理失败时原异常附historical_selection_rows_cleanup_owner用于恢复close。
        """
        # 真实身份、联合同步和当前版本的选择输出单位在构造资源前检查。
        if (not isinstance(history, DecodedHistoryStore) or not isinstance(context, HoldContext)
                or not isinstance(bindings, DecodedBindings) or not isinstance(compiled, CompiledExpression)
                or not isinstance(spec, CalculationDefinition)
                or condition is not None and not isinstance(condition, CompiledExpression)):
            raise TypeError('历史选择行需真实历史、上下文、绑定、表达式和CalculationDefinition')
        if spec.operation != 'select':
            raise ValueError('历史选择行需select')
        if (backend not in ('reference', 'numpy') or type(batch_intervals) is not int or batch_intervals < 1):
            raise ValueError('历史选择行需合法后端与正原生int块大小')
        if compiled.bindings.identity != bindings.identity:
            raise ValueError('选择行表达式与实际绑定不同')
        require_calculation_plan(compiled, spec, condition)
        # 只验证显式范围，不创建派生context；块层按半开实际域裁剪原值更新和UNKNOWN行。
        _calculation_observation(context, observation)
        # 构造失败前准备可清理字段；借用引用与自有句柄明确区分，金额从0开始。
        self._history, self._context, self._bindings = history, context, bindings
        self._observation = observation
        self._compiled, self._spec, self._condition, self._backend = compiled, spec, condition, backend
        self._batch_intervals, self._budget = batch_intervals, history.budget
        self._blocks = self._current = self._rows = self._row = None
        self._held_cost = self._workspace_cost = self._row_cost = self._row_estimate = 0
        self._closed = self._closing = self._failed = self._exhausted = False
        try:
            # 固定描述费用在自有子对象创建前预约，动态完整refs和核/行费用按当前块另计。
            identity = None if condition is None else condition.identity
            self._reserve(65536 + 16 * _metadata_bytes((context, bindings.sources, compiled.identity, identity, spec))
                          + (0 if observation is None else 16 * _metadata_bytes(observation)))
            self._blocks = self._make_blocks()
        except BaseException as exc:
            # 子构造未返回也可能拥有历史读取句柄，接管原异常上的真实恢复入口。
            attr = 'calculation_blocks_cleanup_owner' if condition is None else 'conditional_blocks_cleanup_owner'
            child = getattr(exc, attr, None)
            if child is not None:
                self._blocks = child
            for attempt in range(2):
                try:
                    self.close()
                    break
                except BaseException as cleanup:
                    exc.add_note(f'历史选择行构造清理第{attempt+1}次失败: {type(cleanup).__name__}')
            if not self._closed:
                exc.historical_selection_rows_cleanup_owner = self
                exc.add_note('释放恢复后调用historical_selection_rows_cleanup_owner.close()')
            raise

    def _make_blocks(self):
        """创建一次自有单值或联合回读者，借用资源不接管关闭。

        参数: 无。返回: HistoricalCalculationBlocks或HistoricalConditionalBlocks。
        异常: 原构造/身份/同步/预算错误，恢复句柄由父构造接管。
        """
        # 两输入能力已明确支持select，条件BOOL内部保持与原分块/TTL行为相同。
        if self._condition is None:
            return HistoricalCalculationBlocks(self._history, self._context, self._bindings,
                self._compiled, self._spec, backend=self._backend, batch_intervals=self._batch_intervals,
                observation=self._observation)
        return HistoricalConditionalBlocks(self._history, self._context, self._bindings,
            self._compiled, self._spec, self._condition, backend=self._backend, batch_intervals=self._batch_intervals,
            observation=self._observation)

    @property
    def closed(self):
        """读取全部自有资源关闭事实。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    @property
    def failed(self):
        """读取操作失败状态。参数: 无。返回: bool。异常: 无。"""
        return self._failed

    @property
    def exhausted(self):
        """读取正常EOF事实。参数: 无。返回: bool。异常: 无。"""
        return self._exhausted

    def __iter__(self):
        """返回本行owner。参数: 无。返回: self。异常: 无。"""
        return self

    def _reserve(self, amount, *, slot=None):
        """申请固定/工作区/当前行费用，并接管预约成功后取消的真实金额。

        参数: amount为bytes，slot可为_workspace_cost或_row_cost；None为固定描述。
        返回: None。异常: 预算或取消传播，未真正增加账本时不记所有权。
        """
        before = self._budget.ram_bytes
        try:
            self._budget.reserve_ram(amount)
        finally:
            # 本次预约不含子操作，只按真实新增amount同时登记总额与费用所属槽位。
            if self._budget.ram_bytes == before + amount:
                self._held_cost += amount
                if slot is not None:
                    setattr(self, slot, getattr(self, slot) + amount)

    def _release(self, amount, *, slot=None):
        """抵销实际自有费用，释放前取消保留金额，释放后取消立即更新归属。

        参数: amount为bytes，slot为对应工作区/行槽位或None。返回: None。
        异常: 原释放/取消传播，恢复后close不能再次抵销已释放费用。
        """
        before = self._budget.ram_bytes
        try:
            self._budget.release_ram(amount)
        finally:
            if self._budget.ram_bytes == before - amount:
                self._held_cost -= amount
                if slot is not None:
                    setattr(self, slot, getattr(self, slot) - amount)

    def _drop_row(self):
        """结束当前借出行生命周期，释放取消时保留真实未抵销金额。

        参数: 无。返回: None。异常: 行费用释放或取消传播，之后只允许close。
        """
        # 先丢自有行引用，再按实际账本释放；外部独立保留引用须由外部另行计费。
        self._row = None
        if self._row_cost:
            self._release(self._row_cost, slot='_row_cost')

    def _drop_current(self):
        """先关闭核生成器再关当前块，全部成功后释放当前核workspace。

        参数: 无。返回: None。异常: generator/block关闭、释放或取消传播，可重试。
        """
        # 生成器可能仍持有当前series和数组，close成功前不能丢句柄或归还工作区费用。
        if self._rows is not None:
            self._rows.close()
            self._rows = None
        if self._current is not None:
            self._current.close()
            self._current = None
        if self._workspace_cost:
            self._release(self._workspace_cost, slot='_workspace_cost')
        self._row_estimate = 0

    def _load_current(self):
        """取得一个有限块，在第一次消费选择核前预约全部核及行上界元数据。

        参数: 无。返回: None。异常: EOF为StopIteration；读取、预算、核构造或取消传播。
        """
        # 自有分块者被外部关闭/失败时明确拒绝，不能把损坏生命周期当正常EOF。
        if self._blocks.closed or self._blocks.failed or self._blocks._closing:
            raise ResultClosedError('选择行自有分块者已关闭、失败或正在清理')
        self._current = next(self._blocks)
        series = self._current.series
        # N行数组/布尔掩码/索引和完整refs动态费用先预约；不会累计全窗行列表。
        workspace = 65536 + 2048 * len(series.times_ns) + 16 * _metadata_bytes(series.source_refs)
        self._reserve(workspace, slot='_workspace_cost')
        if self._condition is not None:
            # 联合身份沿既有内存select入口；replace只在workspace已取得后复制冻结模型。
            identity = self._compiled.identity + ':' + self._condition.identity
            series = replace(series, binding_identity=identity)
        # 当前行上界含最长原值/枚举标签、单位、联合身份和完整来源，分配前按此费用预约。
        value_metadata = max(_metadata_bytes(value) for value in series.values)
        self._row_estimate = 4096 + 16 * (_metadata_bytes((series.source_refs, series.binding_identity, series.unit)) + value_metadata)
        if self._backend == 'reference':
            from ..core.calculations_reference import select_reference
            self._rows = select_reference(series, self._spec)
        else:
            from ..core.calculations_numpy import select_numpy
            self._rows = select_numpy(series, self._spec)

    def _finish_exhaustion(self):
        """正常EOF释放当前核/行/块费用，保留固定描述至explicit close。

        参数: 无。返回: None。异常: 关闭/释放取消传播，失败后仅可close恢复。
        """
        # EOF不等于显式close，但自有当前行、生成器、当前块和分块者都不再需要。
        self._drop_row()
        self._drop_current()
        if self._blocks is not None:
            self._blocks.close()
            self._blocks = None
        # 原配置、identity和exhausted状态仍由owner持有，固定描述费用只在explicit close归还。
        self._exhausted = True

    def __next__(self):
        """借出至下一次推进/close的单SelectionRow，TRUE/UNKNOWN原样交付。

        参数: 无。返回: 一个SelectionRow；FALSE、非实际更新和半开右端由原核过滤。
        异常: 正常EOF可重复StopIteration；关闭/半关闭ResultClosedError；其他操作失败后仅close。
        """
        if self._closed or self._closing:
            raise ResultClosedError('历史选择行已关闭或正在清理')
        if self._failed:
            raise RuntimeError('失败的历史选择行只能关闭')
        if self._exhausted:
            raise StopIteration
        try:
            # 当前核可能仍持有已关闭输入的series；子owner/块失效后不得继续借出悬挂前缀行。
            if (self._blocks is not None and (self._blocks.closed or self._blocks.failed or self._blocks._closing)
                    or self._current is not None and (self._current.closed or self._current._closing)):
                raise ResultClosedError('选择行自有输入已关闭、失败或正在清理')
            # 下一次推进结束上一行借出费用；块内只留一行，不积累输出历史。
            self._drop_row()
            while True:
                if self._rows is None:
                    try:
                        self._load_current()
                    except StopIteration:
                        self._finish_exhaustion()
                        raise StopIteration
                # 生成器第一次next会执行NumPy数组与索引；workspace和当前行费用已先取得。
                self._reserve(self._row_estimate, slot='_row_cost')
                try:
                    row = next(self._rows)
                except StopIteration:
                    self._drop_row()
                    self._drop_current()
                    continue
                self._row = row
                return row
        except StopIteration:
            raise
        except BaseException:
            self._failed = True
            raise

    def close(self):
        """关闭核、当前块、分块者和自有费用，借用资源保持，重复关闭安全。

        参数: 无。返回: None。异常: generator/block/分块者关闭或金额释放取消可重试。
        """
        if self._closed:
            return
        # 进入清理后禁推进；句柄只在对应close成功后丢弃，不让持续取消丢失恢复入口。
        self._closing = True
        try:
            # 先结束自有行引用并关闭generator；其frame/数组仍在时不释放任何核费用。
            self._row = None
            if self._rows is not None:
                self._rows.close()
                self._rows = None
            if self._current is not None:
                self._current.close()
                self._current = None
            if self._blocks is not None:
                self._blocks.close()
                self._blocks = None
            # 自有句柄全关后统一抵销固定/核/当前行金额；前后取消由实际held账本恢复。
            if self._held_cost:
                self._release(self._held_cost)
        finally:
            # 自有各句柄和实际持有金额全部清零才closed，不以借用账本全局余额代替证明。
            if self._rows is None and self._current is None and self._blocks is None and self._held_cost == 0:
                self._workspace_cost = self._row_cost = self._row_estimate = 0
                self._history = self._context = self._bindings = self._compiled = self._condition = None
                self._observation = None
                self._closed = True
