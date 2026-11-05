"""保存精确样本分位数的有限预算状态，结束时定位两个顺序统计值。

q为0或1时只维护原dtype的极值。其余q保留被选中的真实样本，增长前向
本次预算付款，排序临时空间另行预付并释放。标量及数组后端各自完成排序
和线性插值；本对象只共享寿命、秩、预算协议，不读取来源或生成临时文件。
"""

from fractions import Fraction
from math import isfinite
from .types import QualityFlag as Q, SignalDType as D


SAMPLE_QUANTILES = ('sample_quantile', 'sample_median')


def quantile_probability(operation, q):
    """校验操作与概率的固定组合，返回精确的配置概率。

    参数: operation为sample_quantile/sample_median，q为显式数值或None。
    返回: Fraction；中位数固定为1/2，其他概率按配置值的十进制表示解释。
    异常: ValueError为多余、缺失、非有限、越界或布尔概率。
    """
    if operation == 'sample_median':
        if q is not None:
            raise ValueError('sample_median固定使用q=0.5，请省略q')
        return Fraction(1, 2)
    if (operation != 'sample_quantile' or type(q) not in (int, float) or not 0 <= q <= 1
            or (type(q) is float and not isfinite(q))):
        raise ValueError('sample_quantile需要有限数值q，范围为0到1')
    return Fraction(str(q))


class ExactQuantileBuffer:
    """保存单个统计范围的已选样本或端点极值；只持有自己预付的空间。"""

    def __init__(self, operation, q, dtype, backend, budget=None):
        """配置确定的概率、输入dtype和真实后端，创建空存储。

        参数: operation/q见概率检查，dtype为数值声明，backend为reference或numpy，
            budget为共享ResourceBudget；独立调用省略时使用项目默认配额。
        返回: 新缓冲。异常: 非法参数在读取样本前失败。
        """
        from ..results.budget import ResourceBudget
        if backend not in ('reference','numpy') or dtype not in (D.INT64,D.UINT64,D.FLOAT64):
            raise ValueError('精确分位数需要数值dtype及已支持后端')
        self._q = quantile_probability(operation, q)
        self._dtype, self._backend = dtype, backend
        self._budget = ResourceBudget() if budget is None else budget
        self._held_cost = self._buffer_cost = self._sort_cost = self._size = 0
        self._chunks = [[]] if backend == 'reference' else []
        self._extreme = None
        self._failed = self._closed = self._closing = False

    def _reserve(self, amount, slot):
        """在保存样本或创建排序副本之前申请空间，保留具体预算错误。

        参数: amount为本次额外字节，slot为持有本笔费用的字段。
        返回: None。异常: BudgetExceededError或取消原样传播，close可重试清理。
        """
        from ..results.budget import _reserve_owned_ram
        from ..results.errors import BudgetExceededError
        try:
            _reserve_owned_ram(self, amount, slot)
        except BudgetExceededError as error:
            error.add_note('精确样本分位数的样本存储或排序空间超过可用RAM')
            raise

    def append(self, values, mask=None):
        """累加一批真正选中的有效样本；空批直接返回。

        参数: reference的values为已选原生数值序列；numpy的values为原dtype数组，
            mask为同长布尔选择列。输入所有权属于调用方。
        返回: None。异常: 值/掩码不符、预算不足、关闭后调用或分配失败。
        """
        if self._failed or self._closed or self._closing:
            from ..results.errors import ResultClosedError
            raise ResultClosedError('精确分位数缓冲已关闭或失败')
        try:
            if self._backend == 'reference':
                if mask is not None:
                    raise ValueError('标量分位数仅接已选样本')
                count = len(values)
            else:
                import numpy as np
                if mask is None or mask.dtype != np.bool_ or values.shape != mask.shape:
                    raise ValueError('数组分位数需要同长布尔掩码')
                count = int(np.count_nonzero(mask))
            if not count:
                return
            if self._q in (0, 1):
                # 端点不需要历史。where+原dtype上限/下限使数组极值不用复制所选列。
                if self._backend == 'reference':
                    candidate = (min if self._q == 0 else max)(values)
                else:
                    from .numeric import INTEGER_BOUNDS
                    lower, upper = INTEGER_BOUNDS.get(self._dtype, (-float('inf'), float('inf')))
                    candidate = (np.min(values, where=mask, initial=upper) if self._q == 0 else
                                 np.max(values, where=mask, initial=lower)).item()
                choose = min if self._q == 0 else max
                self._extreme = candidate if self._extreme is None else choose(self._extreme,candidate)
            else:
                # 预付块头/索引槽、标量对象保留费或数组nbytes，然后取得独占副本。
                if self._backend == 'reference':
                    self._reserve((0 if self._size else 256) + count * 64, '_buffer_cost')
                    self._chunks[0].extend(values)
                else:
                    self._reserve(256 + count * 8, '_buffer_cost')
                    self._chunks.append(values[mask])
            self._size += count
        except BaseException:
            self._failed = True
            raise

    def finish(self):
        """读取截至当前批次的分位数快照，不按块分别求分位数再合并。

        参数: 无。返回: (原生数值或None,质量)。空集合返回None及NONE，最终
            空/部分状态由具有完整观测范围的计算器判定。
        异常: 已关闭/失败时拒绝，排序额度不足或分配失败原样传播。
        """
        from ..results.budget import _release_owned_ram
        if self._failed or self._closed or self._closing:
            from ..results.errors import ResultClosedError
            raise ResultClosedError('精确分位数缓冲已关闭或失败')
        if not self._size or self._q in (0, 1):
            return self._extreme, Q.NONE
        if self._size == 1:
            value = self._chunks[0][0]
            return (value if self._backend == 'reference' else value.item()), Q.NONE
        try:
            # Python排序预付指针列表及排序缓冲。NumPy单一连续副本原地堆排序；
            # 固定项还覆盖列表/数组头与两个端点精确插值所需的临时数值。
            workspace = (32 * self._size if self._backend == 'reference' else
                         8 * self._size + 16 * len(self._chunks))
            self._reserve(8192 + workspace, '_sort_cost')
            rank = (self._size - 1) * self._q
            index, remainder = divmod(rank.numerator, rank.denominator)
            if self._backend == 'reference':
                from .quantile_reference import ordered_reference
                return ordered_reference(self._chunks,index,remainder,rank.denominator)
            from .quantile_numpy import ordered_numpy
            return ordered_numpy(self._chunks,index,remainder,rank.denominator)
        except BaseException:
            self._failed = True
            raise
        finally:
            try:
                _release_owned_ram(self,self._sort_cost,'_sort_cost')
            except BaseException:
                self._failed = True
                raise

    def close(self):
        """放弃样本并退回本实例的全部收费，释放被取消时可再次调用。

        参数: 无。返回: None。异常: 原预算释放异常传播，不改变其他owner的费用。
        """
        from ..results.budget import _release_owned_ram
        if self._closed:
            return
        self._closing = True
        self._chunks.clear()
        self._extreme = None
        try:
            _release_owned_ram(self,self._sort_cost,'_sort_cost')
            _release_owned_ram(self,self._buffer_cost,'_buffer_cost')
        finally:
            self._closed = self._held_cost == 0


def compute_quantile_series(series, spec, sample_kernel, budget):
    """把有时间轴的单块内存输入送入对应后端的精确样本归约器。

    参数: series为持有值、真实更新及覆盖；spec为quantile/median；sample_kernel
        为该后端的归约器类；budget为空时使用默认配额。
    返回: 包含观测范围、诊断及精确秩结果的CalculationResult。
    异常: 配置、预算或计算器失败传播；正常/异常退出均释放临时所有权。
    """
    from .calculations import make_calculation_result
    from ..results.budget import _cleanup_owner
    reducer = sample_kernel(spec,series.unit,series.values[0].dtype,quantile_budget=budget)
    try:
        facts = reducer.push(series)
        number = reducer.finish()
        actual = facts.actual_window
        span = 0 if actual is None else actual.end_ns - actual.start_ns
        result = make_calculation_result(spec, series, number.value, number.unit, actual,
            facts.value_valid_duration_ns, facts.condition_known_duration_ns, facts.selected_duration_ns,
            facts.selected_value_unknown_duration_ns, facts.valid_sample_count, facts.value_unknown_ranges,
            facts.condition_unknown_ranges, facts.quality | number.quality,
            all_false=actual == spec.window and span > 0 and facts.false_duration_ns == span,
            calculation_failed=number.calculation_failed)
        # 快照已独立，不把排序缓冲带出低层便捷入口。
        reducer.close()
        return result
    except BaseException as error:
        _cleanup_owner(reducer._quantile,error,'quantile_cleanup_owner','内存分位数')
        raise
