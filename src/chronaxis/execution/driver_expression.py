"""从已提交的同刻信号状态取得所选驱动的数值或BOOL表达式，不保存输入历史。

输入是经过来源校验、归一化和同刻政策处理的LatestSignalState，以及静态
表达式声明；每个驱动更新最多返回一个(time, value, valid_until)计算点。
按实际更新时间判断valid_for，参考及生产逐点数值核独立；真正批量数组入口不变。固定周期
不进入此组件。最新值归state持有，临时求值空间在共享预算中预付。
这是新按需执行的内部接点，不生成CompiledExpression或伪造EOF/绑定证据，
不改变公开表达式入口拒绝StaticExpression的契约。来源读取/同刻归组由调用方负责。
"""

from dataclasses import replace
from ..core import expression_reference
from ..core.expression import StaticExpression, validate_expression
from ..core.expression_point import PointProgram
from ..core.lookup import pack_requested_lookups
from ..core.where_updates import contains_where
from ..core.enum_codes import expire_value
from ..core.declarations import DeclarationBindings
from ..core.numeric import ScalarValue
from ..core.types import SignalDType as D, QualityFlag as Q
from ..results.budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..results.errors import ResultClosedError
from ..timebase.conversion import require_int64_ns
from .history import _metadata_bytes
from .static_metadata import static_metadata_bytes
from .state import LatestSignalState
from .where_state import before_context, group_updates, group_active


class DriverExpression:
    """借用最新状态，持有已核实的表达式树与依赖；不跨组缓存计算值。"""

    def __init__(self, static, state, driver, *, backend='numpy', derived=(), observation_ends=None):
        """核对声明与实际状态映射，预付树和依赖引用费用。

        参数: static为StaticExpression；state为已校验来源的共享最新状态；
            driver为所选原信号别名；None用于实际间隔，每个完整必要更新组求值。
            backend选择数值核；derived为原派生声明。
        返回: 新owner。异常: 声明不一致、非数值/BOOL表达式、预算或取消错误；
            构造清理失败提供driver_expression_cleanup_owner重试句柄。
        """
        if (type(static) is not StaticExpression or type(static.bindings) is not DeclarationBindings
                or not isinstance(state, LatestSignalState)):
            raise TypeError('驱动求值需要静态表达式及真实最新状态')
        if backend not in ('reference', 'numpy'):
            raise ValueError('驱动求值后端需要reference或numpy')
        if static.root.dtype not in (D.FLOAT64, D.INT64, D.UINT64, D.BOOL,D.ENUM):
            raise ValueError('驱动求值需要数值、BOOL或ENUM表达式')
        self._budget, self._state = state.budget, state
        self._held_cost = self._fixed_cost = self._work_cost = 0
        self._closed = self._closing = self._failed = False
        self._static = self._definitions = self._point_program = None
        self._last_revision = 0
        self._last_group_time = None
        self._invalidated_at = None
        self._last_value = None
        self._driver, self._backend = driver, backend
        self._observation_ends = observation_ends
        try:
            # 新校验树、派生展开、点求值索引仍预付；bindings借用state/原计划，
            # 不再为每个指标复制计入整份信号声明。32倍只覆盖本次真实构造的树和临时结构。
            _reserve_owned_ram(self, 65536 + 32 * static_metadata_bytes(
                (static.root, static.text, static.normalized_ast, static.dependencies, derived)), '_fixed_cost')
            checked = validate_expression(static.text, static.bindings, derived=derived, unit=static.root.unit)
            if checked != static:
                raise ValueError('驱动表达式与原声明不一致')
            if static.bindings.session_id != state.session_id:
                raise ValueError('驱动表达式不属于当前会话')
            names = set(static.dependencies) | ({driver} if driver is not None else set())
            for name in names:
                declared = static.bindings.resolve(name)
                actual = state.definitions.get(name)
                # 唯一允许的启动补全是待DBC的有效期；字段、转换及其他身份仍逐项相同。
                if declared.valid_for_ns is None and actual is not None:
                    declared = replace(declared, valid_for_ns=actual.valid_for_ns)
                if actual != declared:
                    raise ValueError('驱动表达式与实际信号定义不同：' + str(name))
            static.bindings.require_synchronized(tuple(sorted(names)))
            # 固定申请已覆盖完整点对及每点16字节的只读列，参考后端直接二分原点对。
            self._static = pack_requested_lookups(checked) if backend == 'numpy' else checked
            # 内建单点直接计算；NumPy宿主只在自己的列接口边界装箱。
            # 原固定预算已预付节点/常量/查表引用，准备结果随当前owner关闭。
            self._point_program = PointProgram(self._static.root) if backend == 'numpy' else None
            self._has_where = contains_where(checked.root)
            self._definitions = tuple((name, state.definitions[name]) for name in static.dependencies)
            # 费用随表达式复杂度和依赖数增长，不随输入记录数增长。
            nodes, pending = 0, [checked.root]
            self._boolean_short_circuit = False
            while pending:
                node = pending.pop()
                nodes += 1
                self._boolean_short_circuit |= node.operator in ('and', 'or')
                pending.extend(node.args)
            self._workspace = 65536 + nodes * 4096 + len(self._definitions) * 4096
        except BaseException as exc:
            _cleanup_owner(self, exc, 'driver_expression_cleanup_owner', '驱动表达式')
            raise
        finally:
            # 构造失败保留异常栈时，不让临时编译树在退款后继续存活。
            checked = pending = node = static = state = derived = None

    def _require_open(self):
        """拒绝失败或关闭后的求值。参数: 无。返回: None。异常: ResultClosedError。"""
        if self._closed or self._closing or self._failed or self._state.closed:
            raise ResultClosedError('驱动表达式或借用状态已关闭/失败')

    def _context_at(self, time_ns, *, continuous=False):
        """读取当前持有值在实际时刻的有效性。参数: time_ns整数ns。返回: context及未来到期点。异常: 模型/分配错误。"""
        context, deadlines = {}, []
        for name, definition in self._definitions:
            sample = self._state.get(name)
            end = None if self._observation_ends is None else self._observation_ends.get(definition.source)
            if sample is None:
                # bool 的 choices 是输入编码到真假值的映射，只有 enum 才携带文字域。
                # 首样本未到时保持 MISSING，不把配置映射误当成观测值或枚举标签。
                value = ScalarValue(None, definition.dtype, False, Q.MISSING,
                                    tuple(dict.fromkeys(label for _, label in definition.choices))
                                    if definition.dtype is D.ENUM else ())
            elif end is not None and (time_ns >= end if continuous else time_ns > end):
                value = expire_value(sample.value, Q.MISSING)
            elif time_ns - sample.time_ns >= definition.valid_for_ns:
                value = expire_value(sample.value, Q.STALE)
            else:
                value = sample.value
                expires = sample.time_ns + definition.valid_for_ns
                available = value.valid or value.code is not None and value.code.valid
                if available and expires < (1 << 63):
                    deadlines.append(expires)
                if available and end is not None:
                    deadlines.append(end)
            context[name] = value
        return context, deadlines

    def _evaluate_values(self, context, unobserved=None):
        """使用独立逐点实现。参数: typed值及可选规则缺项集合。返回: ScalarValue。异常: 原计算/分配错误。"""
        value = names = None
        cache = {}
        try:
            if self._backend == 'reference':
                value = expression_reference._evaluate(self._static.root, context, cache).value
                names = (node.name for node in cache if node.operator == 'name')
            else:
                value = self._point_program.evaluate(context, cache).value
                names = self._point_program.used_names(cache)
            # 缺项和部分质量只来自实际访问的分支，不能扫描静态依赖全集。
            partial = value.partial
            for name in names:
                if unobserved is not None and self._state.get(name) is None:
                    unobserved.add(name)
                partial |= context[name].partial
            if value.valid and not value.partial and partial:
                value = replace(value,partial=True)
            return value
        finally:
            context = value = cache = names = None

    def actual_update_at(self, time_ns):
        """检查真实数值更新。参数: 完整组纳秒。返回: bool。异常: 状态/预算/后端错误。"""
        return self._point_evidence(time_ns, 'updated')

    def active_end_at(self, time_ns):
        """检查活动来源末端。参数: 查询纳秒。返回: bool。异常: 状态/预算/后端错误。"""
        return self._point_evidence(time_ns, 'source_end')

    def actual_unknown_at(self, time_ns, point):
        """区分真实中断与并列 TTL。参数: 完整组纳秒、已知无效点值。返回: bool。异常: 状态/求值错误。"""
        return self._point_evidence(time_ns, 'invalid', point)

    def _point_evidence(self, time_ns, kind, point=None):
        """检查点上的活动更新、未知原因或活动来源末端，不推进驱动。

        参数: 查询纳秒、证据种类，invalid 另传当前实际点。返回: bool。
        异常: 状态、预算及后端求值错误；失败后只允许关闭。
        """
        self._require_open()
        source_end = kind == 'source_end'
        if not source_end and self._state.last_time_ns != time_ns:
            return False
        names = self._static.dependencies
        ends = self._observation_ends or {}
        if source_end and not any(ends.get(d.source) == time_ns for _, d in self._definitions):
            return False
        if not self._has_where:
            return source_end or any((sample := self._state.get(name)) is not None and sample.time_ns == time_ns for name in names)
        primary = None
        try:
            _reserve_owned_ram(self, self._workspace, '_work_cost')
            current, _ = self._context_at(time_ns)
            if source_end:
                return group_active(self._static.root, current,
                    {name: ends.get(d.source) == time_ns for name, d in self._definitions}, self._backend,
                    point_program=self._point_program)
            flags = {name: (sample := self._state.get(name)) is not None and sample.time_ns == time_ns for name in names}
            if kind == 'invalid':
                # 判定实际中断使用“同一 t 排除真实更新”而非左侧保持；否则 TTL 到期
                # 与旁列真实有效更新恰好同刻，会被误判为样本导致的中断。
                invalid = {n: real and not self._state.get(n).value.valid for n, real in flags.items()}
                if group_active(self._static.root, current, invalid, self._backend, point_program=self._point_program):
                    return True
                prior = before_context(self._state, names, time_ns, ends=self._observation_ends)
                old = self._evaluate_values(prior)
                return old.valid or bool(point.quality & ~old.quality)
            previous = before_context(self._state, names, time_ns, ends=self._observation_ends, left_limit=True)
            return group_updates(self._static.root, current, previous, flags, self._backend,
                                 point_program=self._point_program)
        except BaseException as error:
            primary, self._failed = error, True
            raise
        finally:
            try:
                _release_owned_ram(self, self._work_cost, '_work_cost')
            except BaseException as cleanup:
                self._failed = True
                if primary is None:
                    raise
                primary.add_note('活动依赖检查费用释放失败：' + type(cleanup).__name__)

    def _output_deadline(self, time, output, deadlines):
        """选取首次可见失效。参数: 当前纳秒、输出、TTL/来源候选末端。
        返回: 整数截止或 None。异常: 候选边界上的求值错误。
        """
        if not self._has_where and not (output.dtype is D.BOOL and self._boolean_short_circuit):
            return min(deadlines, default=None)
        if output.valid:
            for candidate in sorted(set(deadlines)):
                if candidate >= time:
                    future_context, _ = self._context_at(candidate, continuous=True)
                    future = self._evaluate_values(future_context)
                    if not future.valid or future.value != output.value:
                        return candidate
        return None

    def evaluate(self):
        """仅在最新完整组包含驱动更新时求值一次；其他组仅由state保存最新值。

        参数: 无，读取借用state的当前完整组。返回: None或(time_ns, ScalarValue,
            实际有效截止)；None截止表示所有依赖在int64时间域内没有未来过期点。
        异常: 跳过未消费组、预算、计算结构或取消错误；失败后不再交付结果。
        约束: 必须在每次完整组提交后调用，不能用最新状态补算丢掉的历史组。
        """
        self._require_open()
        context = result = output = sample = None
        primary = None
        try:
            revision = self._state.revision
            if revision == self._last_revision:
                return None
            if revision != self._last_revision + 1:
                raise ValueError('驱动求值不能跳过已提交的完整组')
            time = self._state.last_time_ns
            previous_time, self._last_group_time = self._last_group_time, time
            self._invalidated_at = None
            # 非驱动依赖的无效更新也立即停止旧值保持，不能等下一条驱动才处理。
            # 只传必要的截止，不制造一个会参与N−1计数的驱动点。
            for name, _ in self._definitions:
                changed = self._state.get(name)
                definition = self._state.definitions[name]
                ended = None if self._observation_ends is None else self._observation_ends.get(definition.source)
                if ended is not None and ended <= time and (previous_time is None or ended > previous_time):
                    self._invalidated_at = ended if self._invalidated_at is None else min(ended,self._invalidated_at)
                if changed is not None and changed.time_ns == time and not changed.value.valid:
                    self._invalidated_at = time if self._invalidated_at is None else min(time,self._invalidated_at)
            driver_sample = self._state.get(self._driver) if self._driver is not None else None
            is_driver = self._driver is None or driver_sample is not None and driver_sample.time_ns == time
            # 已知FALSE and UNKNOWN等不能因为无关分支失效而被整体改成UNKNOWN。
            check_condition = (self._static.root.dtype is D.BOOL and self._boolean_short_circuit
                               and self._invalidated_at is not None)
            if not is_driver and not check_condition and not self._has_where:
                self._last_revision = revision
                return None
            _reserve_owned_ram(self, self._workspace, '_work_cost')
            context, deadlines = self._context_at(time, continuous=not is_driver)
            output = self._evaluate_values(context)
            if self._has_where:
                # EOF 可能随下一条真实记录才确定。按该时间上仍生效的旧组求值，
                # 避免把新分支的失效倒填到旧区间，或让未选来源提前截止。
                self._invalidated_at = None
                ends = self._observation_ends or {}
                cutoffs = {ends[d.source] for _, d in self._definitions if d.source in ends and
                           previous_time is not None and previous_time <= ends[d.source] <= time}
                for cutoff in sorted(cutoffs):
                    point = before_context(self._state, self._static.dependencies, cutoff, ends=ends)
                    if not group_active(self._static.root, point,
                            {n: ends.get(d.source) == cutoff for n, d in self._definitions}, self._backend,
                            point_program=self._point_program):
                        continue
                    prior = before_context(self._state, self._static.dependencies, cutoff, ends=ends, continuous=True)
                    if not self._evaluate_values(prior).valid:
                        self._invalidated_at = cutoff
                        break
                if self._invalidated_at is None and not output.valid:
                    self._invalidated_at = time
            if not is_driver:
                if (self._last_value is not None and output.valid and self._last_value.valid
                        and output.value == self._last_value.value):
                    self._invalidated_at = None
                self._last_revision = revision
                return None
            deadline = self._output_deadline(time, output, deadlines)
            if output.dtype is D.BOOL:
                if output.valid and self._last_value is not None and self._last_value.valid and output.value == self._last_value.value:
                    self._invalidated_at = None
            self._last_value = output if output.dtype is D.BOOL else None
            self._last_revision = revision
            return time, output, deadline
        except BaseException as exc:
            primary = exc
            self._failed = True
            raise
        finally:
            context = columns = result = output = sample = driver_sample = value = changed = None
            deadlines = future_context = future = None
            try:
                _release_owned_ram(self, self._work_cost, '_work_cost')
            except BaseException as cleanup:
                self._failed = True
                if primary is None:
                    raise
                primary.add_note('驱动表达式清理失败：' + type(cleanup).__name__)

    @property
    def invalidated_at(self):
        """当前已消费组使数值依赖失效的实际时刻。参数: 无。返回: int或None。异常: 关闭/失败。"""
        self._require_open()
        return self._invalidated_at

    def evaluate_at(self, time_ns, *, continuous=True, unobserved=None):
        """在当前最新状态上查询实际边界，供规则的TTL和等待调度使用。

        参数: time_ns不得早于已提交组；continuous=False查询实际点，True查询右侧保持；
            unobserved可收集当前活动路径从未观测的别名，不记录未来推算中的缺项。
        返回: (ScalarValue, 下一次可能改变已知结果的实际截止或None)。不提交组、
            不改变驱动游标，不制造报文，也不保存查询轨迹。
        异常: 时间/状态/预算/数值错误；失败后仅可关闭，费用释放失败仍保原责任。
        """
        self._require_open()
        context = output = future_context = future = deadlines = None
        primary = None
        try:
            time = require_int64_ns(time_ns,'expression.query_time')
            if type(continuous) is not bool or self._state.last_time_ns is not None and time < self._state.last_time_ns:
                raise ValueError('边界查询需要bool视图且不能回读已覆盖的旧状态')
            _reserve_owned_ram(self,self._workspace,'_work_cost')
            context,deadlines = self._context_at(time,continuous=continuous)
            output = self._evaluate_values(context, unobserved)
            deadline = None
            if output.valid:
                for candidate in sorted(set(value for value in deadlines if value > time)):
                    if not self._boolean_short_circuit and not self._has_where:
                        deadline = candidate
                        break
                    future_context,_ = self._context_at(candidate,continuous=True)
                    future = self._evaluate_values(future_context)
                    if not future.valid or future.value != output.value:
                        deadline = candidate
                        break
            return output,deadline
        except BaseException as error:
            primary,self._failed = error,True
            raise
        finally:
            context = output = future_context = future = deadlines = None
            try:
                _release_owned_ram(self,self._work_cost,'_work_cost')
            except BaseException as cleanup:
                self._failed=True
                if primary is None:
                    raise
                primary.add_note('规则边界求值费用释放失败：'+type(cleanup).__name__)

    def close(self):
        """释放自有树/费用，借用state保持原所有者负责。参数: 无。返回: None。异常: 释放失败可重试。"""
        if self._closed:
            return
        self._closing = True
        self._static = self._definitions = self._state = self._last_value = self._observation_ends = self._point_program = None
        _release_owned_ram(self, self._work_cost, '_work_cost')
        _release_owned_ram(self, self._fixed_cost, '_fixed_cost')
        self._closed = True
