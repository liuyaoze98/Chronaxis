"""用独立 NumPy 误差数组归约原序积分面积，最后一次换算输出单位。

输入是有限块 NumpyIntegralTerms，只消费 valid 为 True 的 float64 面积；
面积已经带有 input_unit 乘秒的量纲，本核不重复乘区间时长、不累计覆盖事实。
跨块保存按绝对值递增、互不重叠的误差项，默认最多 4096 项；不保留历史面积。
原序面积推进属于 state_driver；每项内部用真实 accumulate、ufunc 和掩码处理
误差数组，不调用参考模块或 math.fsum，也不把整窗宣称为无状态数组求和。
状态与临时数组均受 partial_limit 限制，输入索引受当前有限块长度限制；
本纯核不管理预算或关闭资源，调用方须先预约相应空间并负责异常后的生命周期。
finish 是不破坏状态的快照，单位换算故障只影响返回结果；原量纲累计溢出永久保留。
"""

# 仅共享结果模型、参数门槛和输入模型；数值误差推进由本模块独立实现。
import numpy as np
from .integral_sum import (IntegralStateLimitError, IntegralSumResult,
                           require_partial_limit, require_sum_finish)
from .integral_terms_numpy import NumpyIntegralTerms
from .types import QualityFlag as Q


class NumpyIntegralSum:
    """保存有限 float64 误差项和有效项计数，保持跨块原序及持久溢出状态。

    partials 只在完整单项候选满足容量后安装，不按输入项数增长；中途溢出
    清空数值状态并永久标失败，但后续有效面积仍计数。输入和已返回结果不被修改。
    """

    def __init__(self, partial_limit: int = 4096):
        """建立独立的空数组误差状态。

        参数: partial_limit 为正原生 int，表示误差状态的最大项数。
        返回: 无；初始化有效项数 0、累计故障 False 及空 float64 数组。
        异常: TypeError/ValueError 为限额不合法；内存分配错误直接传播。
        """
        # 状态容量受显式限额约束；预约责任属于调用方，纯核不另开预算。
        self._partial_limit = require_partial_limit(partial_limit)
        self._partials = np.empty(0, dtype=np.float64)
        self._valid_term_count = 0
        self._calculation_failed = False

    @property
    def valid_term_count(self) -> int:
        """读取已消费的有效面积数，包含导致中途溢出的项及其后续项。

        参数: 无。返回: 非负原生 int。异常: 无。
        """
        # 计数不等同于有效时间或真实更新样本数，覆盖信息由外层独立累计。
        return self._valid_term_count

    @property
    def calculation_failed(self) -> bool:
        """读取原量纲累计中途非有限的持久标志。

        参数: 无。返回: bool；finish 的单位换算故障不修改本属性。异常: 无。
        """
        # 失败不能通过后来抵消或再调用 finish 恢复为成功。
        return self._calculation_failed

    @property
    def partial_count(self) -> int:
        """读取当前持有的非零误差项数，不暴露可修改的数组。

        参数: 无。返回: 不超过 partial_limit 的原生 int。异常: 无。
        """
        # 返回标量规模，调用方不能通过属性改写数值不变量。
        return len(self._partials)

    def push(self, terms: NumpyIntegralTerms) -> None:
        """按输入顺序消费当前有限块的有效面积，不先对块求和。

        参数: terms 为已校验的只读 float64 面积、bool 掩码和 IntegralFacts。
        返回: None；安装成功的单项更新状态和有效计数，输入数组保持原样。
        异常: TypeError 为输入类型错误；IntegralStateLimitError 为候选容量超限；
        分配或取消错误传播。超限项不安装，其前面已成功消费的项保留。
        """
        try:
            # typed 输入已保证同长有限面积；UNKNOWN 占位不能作为有效零参与归约。
            if not isinstance(terms, NumpyIntegralTerms):
                raise TypeError('数组积分归约需要 NumpyIntegralTerms')
            # 保留原积分typed门槛，同后端通用入口承接完全相同的数值推进。
            self.push_values(terms.areas, terms.valid)
        finally:
            # 原异常及TB仍交调用方；只断本层借入参数、视图和临时，不清外部帧。
            self = terms = None

    def push_values(self, values: np.ndarray, valid: np.ndarray) -> None:
        """用本数组后端累计有限浮点项，不构造虚假的积分事实。

        参数: values/valid 为同长只读普通一维float64/bool数组；未知位置只能存0。
        返回: None；原序推进、容量、中间溢出及finish行为与积分入口相同。
        异常: TypeError/ValueError 为结构或写保护错误；容量、分配和取消传播。
        内存: 检查掩码与索引均为当前有限(N,)临时列，调用方必须先预约预算。
        """
        try:
            # 拒绝自动cast、广播或可写别名；不把未知占位当正常数值。
            if (type(values) is not np.ndarray or type(valid) is not np.ndarray
                    or values.ndim != 1 or valid.ndim != 1
                    or values.dtype != np.dtype('float64') or valid.dtype != np.dtype('bool')
                    or len(values) != len(valid) or values.flags.writeable or valid.flags.writeable):
                raise TypeError('数组原序归约需要同长只读float64/bool一维列')
            if np.any(~np.isfinite(values)) or np.any(values[~valid] != 0):
                raise ValueError('数组原序项需有限，未知位置只能存0')
            # 当前块的索引空间为 O(N)，属于调用方有限块预约；不保存索引到跨块状态。
            indices = np.flatnonzero(valid)
            if self._calculation_failed:
                self._valid_term_count += len(indices)
                return
            # 原序外层属于 state_driver；每项内的误差推进是独立的真实数组运算。
            for index in indices:
                if self._calculation_failed:
                    self._valid_term_count += 1
                    continue
                candidate = self._advance(values[index])
                # 容量检查已完成才安装；数值溢出单项仍计数，清空不再使用的误差状态。
                if candidate is None:
                    self._partials = np.empty(0, dtype=np.float64)
                    self._calculation_failed = True
                else:
                    self._partials = candidate
                self._valid_term_count += 1
        finally:
            # 原异常及TB仍交调用方；只断本层借入参数、视图和临时，不清外部帧。
            self = values = valid = indices = candidate = None

    def _advance(self, area: np.float64) -> np.ndarray | None:
        """生成一项的独立误差候选，不提前改写当前状态。

        参数: area 为有限 float64 面积，量纲仍为 input_unit 乘秒。
        返回: float64 形状 (K,) 的新候选，K 不超过限额；中途非有限返回 None。
        异常: IntegralStateLimitError 为候选超限；分配和取消错误传播。
        """
        try:
            # (K+1,) accumulate 保留每一步 hi，递推顺序与原序 FastTwoSum 相同。
            chain = np.concatenate((np.array([area], dtype=np.float64), self._partials))
            with np.errstate(over='ignore', under='ignore', invalid='ignore'):
                highs = np.add.accumulate(chain, dtype=np.float64)
            if not np.all(np.isfinite(highs)):
                return None
            # 每一步的旧 x 与 partial 并列为 (K,)；交换只用于找出绝对值较大的加数。
            incoming, old = highs[:-1], self._partials
            swap = np.abs(incoming) < np.abs(old)
            large = np.where(swap, old, incoming)
            small = np.where(swap, incoming, old)
            with np.errstate(over='ignore', under='ignore', invalid='ignore'):
                lows = np.subtract(small, np.subtract(highs[1:], large))
            # 非零 lo 按原误差顺序压紧；末 hi 为零时不追加，保留全零的空状态。
            kept = lows[lows != 0]
            last = highs[-1]
            count = len(kept) + int(last != 0)
            if count > self._partial_limit:
                raise IntegralStateLimitError('数组积分误差状态超过 partial_limit')
            # 新数组不借用 chain 的底层空间，跨块状态容量只包含实际保留的 K 项。
            if last != 0:
                return np.concatenate((kept, np.array([last], dtype=np.float64)))
            return kept.copy()
        finally:
            # 原异常及TB仍交调用方；只断本层借入参数、视图和临时，不清外部帧。
            self = area = chain = highs = incoming = old = None
            swap = large = small = lows = kept = last = None

    def finish(self, unit: str, factor: float = 1.0) -> IntegralSumResult:
        """正确舍入当前误差状态，再做一次输出单位换算，返回独立快照。

        参数: unit 为非空输出单位；factor 为正有限原生 float，仅在最后相乘。
        返回: IntegralSumResult；没有有效项为 None，有效全零为 +0.0；累计或
        换算非有限为 NONFINITE，非零换算下溢为 PRECISION_LOSS，均标计算失败。
        异常: TypeError/ValueError 为参数错误；分配或取消错误传播。
        """
        try:
            # 参数先校验；快照不消费或清空状态，外层 owner 决定是否锁定后续输入。
            unit, factor = require_sum_finish(unit, factor)
            if self._calculation_failed:
                return IntegralSumResult(None, unit, True, Q.NONFINITE, self._valid_term_count)
            if self._valid_term_count == 0:
                return IntegralSumResult(None, unit, False, Q.NONE, 0)
            # 空误差状态表示有效面积精确抵消或全零，不等同于没有有效面积。
            raw = self._rounded() if len(self._partials) else np.float64(0.0)
            with np.errstate(over='ignore', under='ignore', invalid='ignore'):
                converted = np.multiply(raw, np.float64(factor))
            if not np.isfinite(raw) or not np.isfinite(converted):
                return IntegralSumResult(None, unit, True, Q.NONFINITE, self._valid_term_count)
            if raw != 0 and converted == 0:
                return IntegralSumResult(None, unit, True, Q.PRECISION_LOSS, self._valid_term_count)
            # 转为 Python float 仅用于冻结结果，不把数值推进交给参考或标量求和核。
            return IntegralSumResult(float(converted), unit, False, Q.NONE, self._valid_term_count)
        finally:
            # 原异常及TB仍交调用方；只断本层借入参数、视图和临时，不清外部帧。
            self = unit = factor = raw = converted = None

    def _rounded(self) -> np.float64:
        """从最大误差项向小项求和，在首个舍入误差处完成半偶修正。

        参数: 无；当前状态必须至少包含一个非零有限 partial。
        返回: 当前原量纲的正确舍入 float64；不修改误差数组。
        异常: 分配或取消错误传播；数值非有限由 finish 分类。
        """
        try:
            # 逆序是只读视图；后续向量计算全部局限于 (K,) 或 (K-1,) 的固定容量。
            reverse = self._partials[::-1]
            with np.errstate(over='ignore', under='ignore', invalid='ignore'):
                highs = np.add.accumulate(reverse, dtype=np.float64)
                lows = np.subtract(reverse[1:], np.subtract(highs[1:], highs[:-1]))
            inexact = np.flatnonzero(lows != 0)
            if len(inexact) == 0:
                return highs[-1]
            # 首个非零 lo 已界定舍入位置，不能用后来多算的 hi 或故障污染这个结果。
            position = int(inexact[0])
            hi, lo = highs[position + 1], lows[position]
            next_position = position + 2
            if next_position < len(reverse):
                smaller = reverse[next_position]
                if (lo < 0 and smaller < 0) or (lo > 0 and smaller > 0):
                    # 与下一更小 partial 同号时探测半偶修正；比较差值确保只跨正确的 ULP。
                    with np.errstate(over='ignore', under='ignore', invalid='ignore'):
                        doubled = np.multiply(lo, np.float64(2.0))
                        corrected = np.add(hi, doubled)
                        difference = np.subtract(corrected, hi)
                    if doubled == difference:
                        hi = corrected
            return hi
        finally:
            # 原异常及TB仍交调用方；只断本层借入参数、视图和临时，不清外部帧。
            self = reverse = highs = lows = inexact = None
            hi = lo = smaller = doubled = corrected = difference = None
