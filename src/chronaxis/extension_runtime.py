"""托管可信回调的后端调用、有限资源、返回形状及取消和关闭责任。

逐点调用只拥有本次工作区；样本归约和时序状态分别活到当前统计范围或
会话结束。共享ResourceBudget只为请求的实现付费，回调可在分配额外内存前
预约并归还自己的金额。宿主代码必须遵守该协议，这不是Python代码沙箱。
"""

from .extensions import _BUDGET, FunctionSpec, ReductionSpec, TransformSpec
from .core.numeric import ScalarValue
from .results.budget import ResourceBudget, _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from .results.errors import ResultClosedError


class ExtensionResources:
    """一次调用或状态所有的预算视图；动态费用与固定状态费用分开登记。"""

    def __init__(self, budget, fixed=0):
        """参数: 共享budget或None及固定状态字节。返回: 资源所有者。异常: 预约失败可清理。"""
        self._budget = budget if budget is not None else _BUDGET.get()
        if self._budget is None:
            self._budget = ResourceBudget()
        self._held_cost = self._fixed_cost = self._dynamic_cost = 0
        self._closed = self._closing = False
        try:
            if fixed:
                _reserve_owned_ram(self,fixed,'_fixed_cost')
        except BaseException as error:
            _cleanup_owner(self,error,'extension_cleanup_owner','扩展状态预约')
            raise

    def reserve(self, amount):
        """参数: 即将分配的非负字节数。返回: None。异常: 预算超额、取消或已关闭。"""
        if self._closed or self._closing:
            raise ResultClosedError('扩展资源已关闭')
        _reserve_owned_ram(self,amount,'_dynamic_cost')

    def release(self, amount):
        """参数: 本回调已预付的动态字节数。返回: None。异常: 不允许退其他所有者或固定额度。"""
        if self._closed or self._closing:
            raise ResultClosedError('扩展资源已关闭')
        if type(amount) is not int or amount < 0 or amount > self._dynamic_cost:
            raise ValueError('扩展只能归还自己实际申请的动态费用')
        _release_owned_ram(self,amount,'_dynamic_cost')

    def close(self,cancelled=False):
        """退回全部自有费用。参数: cancelled为上游取消提示。返回: None。异常: 账本异常后可重试。"""
        if self._closed:
            return
        self._closing = True
        try:
            _release_owned_ram(self,self._dynamic_cost,'_dynamic_cost')
            _release_owned_ram(self,self._fixed_cost,'_fixed_cost')
        finally:
            self._closed = self._held_cost == 0


def _check_scalar(value, port):
    """验证回调输出模型。参数: value与静态输出端口。返回: 原ScalarValue。异常: 类型错误。"""
    if not isinstance(value,ScalarValue) or value.dtype is not port.dtype:
        raise TypeError('宿主扩展返回的ScalarValue与声明dtype不符')
    return value


def _check_values(values, port, backend):
    """验证已选样本的布局和类型。参数: 输入、静态端口及后端。返回: 个数。异常: 布局或质量异常。"""
    if backend == 'reference':
        if type(values) is not tuple or any(not _check_scalar(v,port).valid for v in values):
            raise ValueError('标量归约/网格扩展只接已选有效样本tuple')
        return len(values)
    from .core.numeric_numpy import NumericArray
    if not isinstance(values,NumericArray) or values.dtype is not port.dtype or not values.valid.all():
        raise ValueError('数组归约/网格扩展只接已选有效的同型NumericArray')
    return len(values.values)


def point_call(spec, backend, args):
    """按声明后端运行有限逐点函数，任何退出路径都清理本次工作区。

    参数: spec为编译好的FunctionSpec；args为typed值tuple，按静态端口数量排列。
    返回: ScalarValue或NumericArray。异常: 能力、结构、回调、取消或额度错误原样传播。
    """
    if type(spec) is not FunctionSpec or len(args) != len(spec.inputs):
        raise ValueError('逐点扩展实参与声明不同')
    implementation = spec.require_backend(backend)
    resources = ExtensionResources(None)
    try:
        if backend == 'reference':
            # 任一必要输入无效时直接传播全部质量原因，不要求回调解释无效占位。
            from .core.types import QualityFlag as Q
            quality = Q.NONE
            for value,port in zip(args,spec.inputs):
                quality |= _check_scalar(value,port).quality
            result = (ScalarValue(None,spec.output.dtype,False,quality) if quality else
                      _check_scalar(implementation(args,resources),spec.output))
        else:
            import numpy as np
            from .core.numeric_numpy import DTYPES, NumericArray, _output
            size = len(args[0].values)
            if any(not isinstance(v,NumericArray) or v.dtype is not p.dtype or len(v.values) != size
                   for v,p in zip(args,spec.inputs)):
                raise TypeError('数组逐点扩展的输入dtype或行数错误')
            quality = np.zeros(size,dtype=np.uint16)
            for value in args:
                quality |= value.quality
            selected = quality == 0
            valid_count = int(np.count_nonzero(selected))
            out = np.zeros(size,dtype=DTYPES[spec.output.dtype])
            if valid_count:
                # 只把全部必要值已知的行交给宿主，输出仍须回到原批坐标。
                operands = args if valid_count == size else tuple(v.take(selected) for v in args)
                column = implementation(operands,resources)
                if not isinstance(column,NumericArray) or column.dtype is not spec.output.dtype or len(column.values) != valid_count:
                    raise TypeError('数组逐点扩展返回的dtype或行数错误')
                out[selected] = column.values
                quality[selected] = column.quality
            result = _output(spec.output.dtype,out,quality)
        resources.close()
        return result
    except BaseException as error:
        _cleanup_owner(resources,error,'extension_cleanup_owner','逐点扩展')
        raise


class _HostedState:
    """持有一个工厂状态及其独立资源账本；失败后只允许取消和关闭。"""

    def __init__(self,spec,backend,budget,methods):
        """参数: typed描述、后端、共享预算、必需方法。返回: owner。异常: 工厂或协议错误。"""
        factory = spec.require_backend(backend)
        self.spec,self.backend = spec,backend
        self.state = None
        self._closed = self._closing = self._failed = self._cancelled = False
        self.resources = ExtensionResources(budget,spec.state_bytes)
        try:
            self.state = factory(self.resources)
            if any(not callable(getattr(self.state,m,None)) for m in (*methods,'cancel','close')):
                raise TypeError(f'扩展 {spec.name} 的工厂状态缺少协议方法')
        except BaseException as error:
            self._failed = True
            # 不合格状态也尽量归还可关闭的宿主资源，不能因缺cancel遗失预算。
            if not callable(getattr(self.state,'close',None)):
                self.state = None
            _cleanup_owner(self,error,'extension_cleanup_owner','宿主扩展构造')
            raise

    def _require_open(self):
        """参数: 无。返回: None。异常: 拒绝使用已失败或已关闭状态。"""
        if self._closed or self._closing or self._failed:
            raise ResultClosedError('宿主扩展已经失败或关闭')

    def close(self,cancelled=False):
        """通知取消、关闭状态、归还费用。参数: cancelled为上游取消。返回: None。异常: 原清理错误可重试。"""
        if self._closed:
            return
        self._closing = True
        if self.state is not None:
            if (cancelled or self._failed) and not self._cancelled:
                self._cancelled = True
                cancel = getattr(self.state,'cancel',None)
                if callable(cancel):
                    cancel()
            self.state.close()
            self.state = None
        self.resources.close()
        self._closed = True


class HostedReduction(_HostedState):
    """每个统计范围独享一次样本归约，已结束的状态不会再次消费。"""

    def __init__(self,spec,backend,budget):
        """参数: ReductionSpec、声明后端和共享账本。返回: owner。异常: 工厂、预算或能力错。"""
        if type(spec) is not ReductionSpec:
            raise TypeError('归约需要ReductionSpec')
        self._result = None
        super().__init__(spec,backend,budget,('consume','finalize','merge') if spec.mergeable else ('consume','finalize'))

    def consume(self,values):
        """参数: 本块已选真实有效值。返回: None。异常: 错类型、已结束或回调/预算失败。"""
        self._require_open()
        if self._result is not None:
            raise ResultClosedError('宿主归约已结算')
        try:
            if _check_values(values,self.spec.input,self.backend):
                self.state.consume(values)
        except BaseException:
            self._failed = True
            raise

    def merge(self,other):
        """参数: 同一描述/后端的另一未结算状态。返回: None。异常: 不可合并或回调失败。"""
        self._require_open()
        if (not self.spec.mergeable or not isinstance(other,HostedReduction) or other is self
                or other.spec is not self.spec or other.backend != self.backend):
            raise ValueError('只能合并明确支持且描述/后端相同的不同归约状态')
        other._require_open()
        if self._result is not None or other._result is not None:
            raise ResultClosedError('已结算归约不能合并')
        try:
            self.state.merge(other.state)
        except BaseException:
            self._failed = True
            raise

    def finalize(self):
        """参数: 无。返回: 静态声明dtype的最终ScalarValue。异常: 错误输出或回调失败。"""
        self._require_open()
        if self._result is None:
            try:
                self._result = _check_scalar(self.state.finalize(),self.spec.output)
            except BaseException:
                self._failed = True
                raise
        return self._result


class HostedTransform(_HostedState):
    """只持有此时序请求的状态，按原时基的实际网格递增推进。"""

    def __init__(self,spec,backend,budget):
        """参数: TransformSpec、后端和共享账本。返回: owner。异常: 工厂、预算或能力错。"""
        if type(spec) is not TransformSpec:
            raise TypeError('时序扩展需要TransformSpec')
        self._last = None
        super().__init__(spec,backend,budget,('advance',))

    def advance(self,time_ns,window_ns,values,weights_ns):
        """参数: 实际递增网格、已声明窗口及等长有效值/正纳秒权重。返回: ScalarValue。异常: 协议或回调失败。"""
        self._require_open()
        if (type(time_ns) is not int or self._last is not None and time_ns <= self._last
                or type(window_ns) is not int or not 0 < window_ns <= self.spec.history_ns):
            raise ValueError('时序扩展需要递增网格及声明历史内的窗口')
        try:
            if len(weights_ns) != _check_values(values,self.spec.input,self.backend):
                raise ValueError('时序扩展的有效区间权重与值长度不同')
            if self.backend == 'reference':
                from fractions import Fraction
                if type(weights_ns) is not tuple or any(type(w) not in (int,Fraction) or w <= 0 for w in weights_ns):
                    raise ValueError('参考时序权重须为正int/Fraction纳秒tuple')
            else:
                import numpy as np
                if (type(weights_ns) is not np.ndarray or weights_ns.ndim != 1
                        or weights_ns.dtype not in (np.dtype('int64'),np.dtype('float64'))
                        or np.any(weights_ns <= 0) or not np.isfinite(weights_ns).all()):
                    raise ValueError('数组时序权重须为正的一维有限int64/float64纳秒列')
            result = _check_scalar(self.state.advance(time_ns,window_ns,values,weights_ns),self.spec.output)
            self._last = time_ns
            return result
        except BaseException:
            self._failed = True
            raise


def advance_grid(host, time_ns, window_ns, latest_first, weights, conversion):
    """将已覆盖区间按正序交给宿主，并保留实际或所选周期的纳秒权重。

    参数: host为当前有状态网格，time_ns/window_ns为实际网格/窗口，latest_first为
        从右向左读到的有效原值，weights为相应纳秒，conversion为已验证的目标单位换算。
    返回: ScalarValue，保留宿主自身失败质量或部分状态。异常: 权重/回调或协议异常。
    """
    integral = all(w.denominator == 1 for w in weights)
    if host.backend == 'reference':
        from .core.calculation_output_reference import convert_result_reference as convert
        inputs = tuple(ScalarValue(v,host.spec.input.dtype) for v in reversed(latest_first))
        durations = tuple(int(w) if w.denominator == 1 else w for w in reversed(weights))
    else:
        import numpy as np
        from .core.numeric_numpy import DTYPES,_output
        from .core.calculation_output_numpy import convert_result_numpy as convert
        array = np.asarray(latest_first,dtype=DTYPES[host.spec.input.dtype])[::-1]
        inputs = _output(host.spec.input.dtype,array,np.zeros(len(array),dtype=np.uint16))
        # 只为数值加权转换分数，时间线的窗口裁剪与驱动位置仍保持精确有理数。
        durations = np.fromiter(reversed(weights),dtype=np.int64 if integral else np.float64,count=len(weights))
    result = host.advance(time_ns,window_ns,inputs,durations)
    target = conversion.dtype(result.dtype)
    if not result.valid:
        return ScalarValue(None,target,False,result.quality)
    value, quality = convert(result.value,result.dtype,conversion)
    return ScalarValue(value,target,not quality,quality,partial=result.partial and not quality)
