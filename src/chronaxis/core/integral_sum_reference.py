"""独立按原序累计积分面积，用有界浮点误差项保留大数抵消后的低位。

输入为 ReferenceIntegralTerms，输出为最终单位下的 IntegralSumResult 快照。
每项使用标量精确拆分，保存非重叠误差项；结束时用标准库 fsum 归约误差项。
任何原序中间溢出永久失败；不会靠后续抵消恢复，也不会按块先求和。
状态最多 partial_limit 项，不保存整窗面积；容量不足明确抛错而不截断。
纯核无文件副作用，状态及候选内存由外层 owner 在调用前申请预算。
"""

# 参考实现独立依赖标准库，不调用数组归约、数组面积或数组对齐实现。
from math import fsum, isfinite
from .integral_sum import (IntegralSumResult, IntegralStateLimitError,
                           require_partial_limit, require_sum_finish)
from .integral_terms import ReferenceIntegralTerms
from .types import QualityFlag as Q


class ReferenceIntegralSum:
    """持有有界非重叠误差项、有效面积计数及持久累计故障。

    push 为原序状态驱动；finish 不清空状态，最终转换故障仅影响返回快照。
    调用方在任意推进异常后须放弃当前累计并清理，不能接着使用半段输入。
    """

    def __init__(self, partial_limit: int = 4096):
        """建立空累计状态。参数: partial_limit 为硬容量。返回: None。异常: 非法容量。
        """
        # 初始零项没有面积证据；不能提前返回正常零值。
        self._limit = require_partial_limit(partial_limit)
        self._partials = []
        self._valid_terms = 0
        self._failed = False

    @property
    def valid_term_count(self) -> int:
        """读取有效面积项数。参数: 无。返回: int。异常: 无。"""
        return self._valid_terms  # 与真实更新样本计数分开。

    @property
    def calculation_failed(self) -> bool:
        """读取持久累计故障。参数: 无。返回: bool。异常: 无。"""
        return self._failed  # 后续抵消不会清除此状态。

    @property
    def partial_count(self) -> int:
        """读取当前误差项数量。参数: 无。返回: int。异常: 无。"""
        return len(self._partials)  # 仅报告有界数值状态，不含输入面积。

    def push(self, terms: ReferenceIntegralTerms) -> None:
        """按原顺序推进有效面积，保留块间误差状态。

        参数: terms 为有限冻结面积块。返回: None。
        异常: TypeError 为后端不符；IntegralStateLimitError/MemoryError 为状态容量或分配失败。
        """
        try:
            # 后端模型必须明确，不隐式把 NumPy 数据搬入标量参考核。
            if not isinstance(terms, ReferenceIntegralTerms):
                raise TypeError('参考归约需要ReferenceIntegralTerms')
            # 原积分入口仍检查真实模型；同后端数值推进可用于其他已定义的原序浮点项。
            self.push_values(terms.areas, terms.valid)
        finally:
            # 原异常及TB仍交调用方；只断本层借入参数、视图和临时，不清外部帧。
            self = terms = None

    def push_values(self, values: tuple[float, ...], valid: tuple[bool, ...]) -> None:
        """累计有限原序浮点项，不要求调用方伪造积分事实。

        参数: values/valid 为同长冻结tuple；数值为有限原生float，未知位置必须存0。
        返回: None；使用与原积分入口相同的误差状态、容量及中间失败规则。
        异常: TypeError/ValueError 为列结构；容量、分配或取消原样传播。
        边界: 仅复用本参考后端数值算法；调用方负责量纲、覆盖与候选内存预算。
        """
        try:
            # 完整门槛在推进前检查，错误输入不能留下半段新增状态。
            if type(values) is not tuple or type(valid) is not tuple or len(values) != len(valid):
                raise TypeError('原序参考归约需要同长tuple数值与掩码')
            # 显式循环保持原any的逐项/短路顺序；取消时没有genexpr的隐藏zip保留整列。
            for value, keep in zip(values, valid):
                if (type(value) is not float or not isfinite(value) or type(keep) is not bool
                        or not keep and value != 0):
                    raise ValueError('参考归约需有限float及bool，未知位置存0')
            # 保留原积分算法、原序、中间溢出和有界误差状态，不先归约块和。
            for area, keep in zip(values, valid):
                # 无效存储零不是数值证据；累计失败后仍统计后续有效项。
                if not keep:
                    continue
                if self._failed or area == 0:
                    self._valid_terms += 1
                    continue
                # state_driver: 每项在原序状态上拆分，不把块和作为新的输入。
                candidate, current = [], area
                for partial in self._partials:
                    large, small = (current, partial) if abs(current) >= abs(partial) else (partial, current)
                    high = large + small
                    if not isfinite(high):
                        # 原序中途溢出保持失败，后续负项不能把已失败计算恢复正常。
                        self._failed = True
                        candidate = []
                        break
                    low = small - (high - large)
                    if low != 0:
                        candidate.append(low)
                    current = high
                if self._failed:
                    self._partials = []
                    self._valid_terms += 1
                    continue
                # 零和不占用误差项；容量检查后才安装该项及其计数。
                if current != 0:
                    candidate.append(current)
                if len(candidate) > self._limit:
                    raise IntegralStateLimitError('积分误差项超过容量，不能截断继续')
                self._partials = candidate
                self._valid_terms += 1
        finally:
            # 原异常及TB仍交调用方；只断本层借入参数、视图和临时，不清外部帧。
            self = values = valid = candidate = None
            current = area = partial = large = small = high = low = None
            value = keep = None

    def finish(self, unit: str, factor: float = 1.0) -> IntegralSumResult:
        """归约有界误差项并只转换一次，保留原累计状态。

        参数: unit/factor 为外层核实的最终单位及倍率。返回: 冻结数值快照。
        异常: 非法配置或分配错误传播；数值溢出/转换下溢写入失败结果。
        """
        try:
            # 配置先校验，空证据和持久溢出保持 None，不能回退为零。
            unit, factor = require_sum_finish(unit, factor)
            if self._failed:
                return IntegralSumResult(None, unit, True, Q.NONFINITE, self._valid_terms)
            if self._valid_terms == 0:
                return IntegralSumResult(None, unit, False, Q.NONE, 0)
            try:
                # 仅归约有界误差项；独立标准库求和不调用 NumPy 内核。
                total = fsum(self._partials)
            except OverflowError:
                return IntegralSumResult(None, unit, True, Q.NONFINITE, self._valid_terms)
            value = total * factor
            if not isfinite(value):
                return IntegralSumResult(None, unit, True, Q.NONFINITE, self._valid_terms)
            if total != 0 and value == 0:
                return IntegralSumResult(None, unit, True, Q.PRECISION_LOSS, self._valid_terms)
            # 零值规范为 +0.0；成功的结果不混入输入未知质量。
            return IntegralSumResult(0.0 if value == 0 else value, unit, False, Q.NONE, self._valid_terms)
        finally:
            # 原异常及TB仍交调用方；只断本层借入参数、视图和临时，不清外部帧。
            self = unit = factor = total = value = None
