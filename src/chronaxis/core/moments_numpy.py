"""按有限 NumPy 块维护加权中心矩或均方根，不收集历史。

由真实有效掩码选好的值和权重按相同的二进制幂缩放。块内围绕锚点求均值和
离均差，跨块用两总体均值差合并离散度。用根均方形式存储二阶量，开方与
目标倍率在可表示范围内求值，不把两个大均方相减，也不逐样本运行标量实现。
"""

from math import frexp, hypot, ldexp, sqrt
import numpy as np
from .types import QualityFlag as Q


class NumpyMoments:
    """持有一个锚点、相对均值、根二阶量、总权重和幂指数，跨块大小固定。"""

    def __init__(self, operation):
        """初始化归约器。参数: 操作名称。返回: 无。异常: 调用侧校验操作。"""
        self.operation = operation
        self.weight = self.anchor = self.mean = self.root = 0.
        self.exponent = None

    def push(self, values, weights=None):
        """整列合并活动行。参数: 有限浮点一维值，权重为正数列或等权None。返回: 无。异常: 非法权重。"""
        if not len(values):
            return
        x = np.asarray(values, dtype=np.float64)
        w = None if weights is None else np.asarray(weights, dtype=np.float64)
        if w is not None and (w.shape != x.shape or np.any(w <= 0) or not np.all(np.isfinite(w))):
            raise ValueError('二阶统计需要同长正有限权重列')
        weight = float(len(x)) if w is None else float(np.sum(w))
        peak = float(np.max(np.abs(x)))
        # 用2的整数幂共同缩放，保留高基数输入的相邻浮点差距。
        e = frexp(peak)[1] if peak else None
        if self.exponent is None or e is not None and e > self.exponent:
            if self.exponent is not None:
                shift = self.exponent - e
                self.mean, self.anchor, self.root = (ldexp(v, shift) for v in (self.mean, self.anchor, self.root))
            self.exponent = e
        exponent = self.exponent or 0
        scaled = np.ldexp(x, -exponent)
        if not self.weight:
            self.anchor = float(scaled[0])
        rms = self.operation.endswith('_rms')
        if rms:
            residual, mean = scaled, 0.
        else:
            # 在全局同一锚点坐标内保存小差值；窄分布可跨块保留半ULP的均值修正。
            offsets = scaled - scaled[0]
            correction = float(np.mean(offsets) if w is None else np.sum(offsets * (w / weight)))
            mean = float(scaled[0] - self.anchor) + correction
            residual = offsets - correction
        maximum = float(np.max(np.abs(residual)))
        if maximum:
            squared = np.square(residual / maximum)
            average = float(np.mean(squared) if w is None else np.sum(squared * (w / weight)))
            block_root = maximum * sqrt(min(1., average))
        else:
            block_root = 0.
        total = self.weight + weight
        left, right = self.weight / total, weight / total
        delta = mean - self.mean
        # 平方和用hypot实现，不直接平方极小的已缩放离散度。
        combined = hypot(sqrt(left) * self.root, sqrt(right) * block_root,
                         delta * sqrt(left * right) if not rms else 0.)
        # RMS 是两块 RMS 的加权平方平均，边界夹回只修正最后一个 ULP 的舍入，
        # 保证连批常数 float64 最大值也不会越出最大输入。
        self.root = min(combined, max(self.root, block_root)) if rms else combined
        self.mean += delta * right
        self.weight = total

    def finish(self, ddof, factor):
        """完成自由度和一次目标转换。参数: 自由度、正倍率。返回: (值或None,质量)。异常: 配置错误。"""
        if self.weight <= (ddof or 0):
            return None, Q.NONE
        if self.root == 0:
            return 0., Q.NONE
        correction = sqrt(self.weight / (self.weight - ddof)) if ddof else 1.
        mantissa, exponent = frexp(self.root * correction)
        exponent += self.exponent or 0
        if self.operation.endswith('_variance'):
            mantissa, exponent = mantissa * mantissa, 2 * exponent
        f, e = frexp(factor)
        try:
            value = ldexp(mantissa * f, exponent + e)
        except OverflowError:
            return None, Q.NONFINITE
        return (value, Q.NONE) if value != 0 else (None, Q.PRECISION_LOSS)
