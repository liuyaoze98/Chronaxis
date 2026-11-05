"""以精确有理数维护参考端的加权中心矩或均方。

输入是通过精度/质量门槛的有限二进制浮点数，正权重来自样本或实际选中区间。
Welford 更新只保存总权重、均值和中心矩。RMS 的有理数平方不会发生浮点中间
溢出；最后一次才按目标倍率和 float64 可表示性给出结果及质量。不依赖 NumPy。
"""

from fractions import Fraction
from math import ldexp, sqrt
from .types import QualityFlag as Q


class ReferenceMoments:
    """每个归约器独享累计量，无样本列表、临时文件或跨会话缓存。"""

    def __init__(self, operation):
        """创建零累计。参数: 操作名。返回: 无。异常: 调用方先做操作检查。"""
        self.operation = operation
        self.weight = self.mean = self.total = Fraction(0)

    def push(self, values, weights=None):
        """合并有限块。参数: 有效浮点序列和可选同长正权重。返回: 无。异常: 无效权重或输入。"""
        for index, item in enumerate(values):
            x = Fraction(item)
            weight = Fraction(weights[index]) if weights is not None else Fraction(1)
            if weight <= 0:
                raise ValueError('二阶统计只接收正权重')
            self.weight += weight
            if self.operation.endswith('_rms'):
                self.total += weight * x * x
            else:
                delta = x - self.mean
                self.mean += delta * weight / self.weight
                self.total += weight * delta * (x - self.mean)

    def finish(self, ddof, factor):
        """完成目标单位换算。参数: 自由度、正倍率。返回: (float或None,质量)。异常: 配置错误。"""
        denominator = self.weight - (ddof or 0)
        if denominator <= 0:
            return None, Q.NONE
        value = self.total / denominator
        if value == 0:
            return 0., Q.NONE
        try:
            if self.operation.endswith('_variance'):
                number = float(value * Fraction(factor))
            else:
                # 把倍率放到根号内并提取偶次二进制指数，避免平方范围决定根的可表示性。
                value *= Fraction(factor) ** 2
                exponent = (value.numerator.bit_length() - value.denominator.bit_length()) // 2
                scaled = value / (Fraction(2) ** (2 * exponent))
                number = ldexp(sqrt(float(scaled)), exponent)
        except OverflowError:
            return None, Q.NONFINITE
        return (number, Q.NONE) if number != 0 else (None, Q.PRECISION_LOSS)
