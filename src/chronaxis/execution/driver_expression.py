"""从已提交的同刻信号状态取得所选驱动的数值或BOOL表达式，不保存输入历史。

输入是经过来源校验、归一化和同刻政策处理的LatestSignalState，以及静态
表达式声明；每个驱动更新最多返回一个(time, value, valid_until)计算点。
按实际更新时间判断valid_for，复用既有独立参考/NumPy算术内核；固定周期
不进入此组件。最新值归state持有，临时求值空间在共享预算中预付。
这是新按需执行的内部接点，不生成CompiledExpression或伪造EOF/绑定证据，
不改变公开表达式入口拒绝StaticExpression的契约。来源读取/同刻归组由调用方负责。
"""

from dataclasses import replace
from ..core import expression_reference, expression_numpy
from ..core.expression import StaticExpression, validate_expression
from ..core.declarations import DeclarationBindings
from ..core.numeric import ScalarValue
from ..core.types import SignalDType as D, QualityFlag as Q
from ..results.budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..results.errors import ResultClosedError
from ..timebase.conversion import require_int64_ns
from .history import _metadata_bytes
from .calculation_values import scalar_from_column
from .state import LatestSignalState


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
        self._static = self._definitions = None
        self._last_revision = 0
        self._last_group_time = None
        self._invalidated_at = None
        self._last_value = None
        self._driver, self._backend = driver, backend
        self._observation_ends = observation_ends
        try:
            _reserve_owned_ram(self, 65536 + 32 * _metadata_bytes((static, derived)), '_fixed_cost')
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
            self._static = checked
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
                value = ScalarValue(None, definition.dtype, False, sample.value.quality | Q.MISSING, sample.value.labels)
            elif time_ns - sample.time_ns >= definition.valid_for_ns:
                value = ScalarValue(None, definition.dtype, False, sample.value.quality | Q.STALE, sample.value.labels)
            else:
                value = sample.value
                expires = sample.time_ns + definition.valid_for_ns
                if value.valid and expires < (1 << 63):
                    deadlines.append(expires)
                if value.valid and end is not None:
                    deadlines.append(end)
            context[name] = value
        return context, deadlines

    def _evaluate_values(self, context):
        """复用选定后端的独立数值核。参数: 已付费当前typed值映射。返回: ScalarValue。异常: 原计算/分配错误。"""
        result = columns = value = None
        try:
            if self._backend == 'reference':
                return expression_reference._evaluate(self._static.root, context, {}).value
            import numpy as np
            from ..core.numeric_numpy import NumericArray, DTYPES
            columns = {}
            for name, value in context.items():
                physical = value.labels.index(value.value) if value.valid and value.dtype is D.ENUM else value.value if value.valid else 0
                columns[name] = NumericArray(value.dtype, np.array([physical], dtype=DTYPES[value.dtype]),
                    np.array([value.valid], dtype=bool), np.array([int(value.quality)], dtype=np.uint16), value.labels)
            result = expression_numpy._evaluate(self._static.root, columns, 1, {})
            return scalar_from_column(result.value, 0)
        finally:
            context = result = columns = value = None

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
            if not is_driver and not check_condition:
                self._last_revision = revision
                return None
            _reserve_owned_ram(self, self._workspace, '_work_cost')
            context, deadlines = self._context_at(time, continuous=not is_driver)
            output = self._evaluate_values(context)
            if not is_driver:
                if (self._last_value is not None and output.valid and self._last_value.valid
                        and output.value == self._last_value.value):
                    self._invalidated_at = None
                self._last_revision = revision
                return None
            deadline = min(deadlines) if deadlines else None
            if output.dtype is D.BOOL:
                if output.valid and self._last_value is not None and self._last_value.valid and output.value == self._last_value.value:
                    self._invalidated_at = None
                # 依赖逐个过期可能不改变三值结论，只在结论不再成立的首个截止停止保持。
                if self._boolean_short_circuit:
                    deadline = None
                if output.valid and self._boolean_short_circuit:
                    for candidate in sorted(set(deadlines)):
                        future_context, _ = self._context_at(candidate, continuous=True)
                        future = self._evaluate_values(future_context)
                        if not future.valid or future.value != output.value:
                            deadline = candidate
                            break
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

    def evaluate_at(self, time_ns, *, continuous=True):
        """在当前最新状态上查询实际边界，供规则的TTL和等待调度使用。

        参数: time_ns不得早于已提交组；continuous=False查询实际点，True查询右侧保持。
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
            output = self._evaluate_values(context)
            deadline = None
            if output.valid:
                for candidate in sorted(set(value for value in deadlines if value > time)):
                    if not self._boolean_short_circuit:
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
        self._static = self._definitions = self._state = self._last_value = self._observation_ends = None
        _release_owned_ram(self, self._work_cost, '_work_cost')
        _release_owned_ram(self, self._fixed_cost, '_fixed_cost')
        self._closed = True
