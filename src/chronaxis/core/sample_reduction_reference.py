"""独立标量归约有限真实样本，保留原dtype极值与原序样本算术均值。

push分别计算值/条件覆盖，只将半开窗中有效/TRUE原值真实更新计入候选。极值
保留原整数；mean先检查float精度，原单位样本按原序推进有界误差核，finish完成
原量纲总和后除真实样本数，再换输出单位一次。原序中间溢出沿既有故障政策保持
失败，不改为time_weighted_mean的规范化权重；除法/换算故障不改输入覆盖。不调用NumPy、
不读来源。精确分位数按专用配额保留被选中的原dtype样本，异常后由owner清理。
"""

# 标量覆盖及候选独立于数组后端；仅复用本参考原序误差状态。
from .moments import SAMPLE_MOMENTS
from .quantiles import SAMPLE_QUANTILES, ExactQuantileBuffer
from .moments_reference import ReferenceMoments
from math import isfinite
from .calculation_output_reference import convert_result_reference
from .integral_sum_reference import ReferenceIntegralSum
from .calculations import merge_ranges
from .models import Interval
from .numeric import ScalarValue, to_float_reference
from .sample_reduction import SampleCalculationFacts, SampleReductionResult, require_sample_config, require_sample_series
from .types import QualityFlag as Q, SignalDType as D


class ReferenceSampleReduction:
    """累计当前范围的真实样本；分位数仅在请求时按共享预算保留原dtype样本。"""

    def __init__(self, spec, input_unit, dtype, *, partial_limit=4096, quantile_budget=None):
        """核对原配置并建立本参考后端有限状态。

        参数: spec/input_unit/dtype为原声明，partial_limit为正原生int误差容量。
        quantile_budget为精确分位数单独申请存储/排序空间时使用的共享预算。
        返回: None。异常: 配置或分配错误传播。
        """
        # 共享静态门槛先检查明确样本能力、数值类型和输出单位。
        self._conversion = require_sample_config(spec, input_unit, dtype, partial_limit)
        self._unit, self._factor = self._conversion.unit, self._conversion.factor
        self._spec, self._input_unit, self._dtype = spec, input_unit, dtype
        self._identity = self._candidate = None
        # 精确分位数单独保存被选中的原dtype；其他样本指标无需创建存储。
        self._quantile = (ExactQuantileBuffer(spec.operation,spec.q,dtype,'reference',quantile_budget)
                          if spec.operation in SAMPLE_QUANTILES else None)
        self._moments = ReferenceMoments(spec.operation) if spec.operation in SAMPLE_MOMENTS else None
        self._value_duration = self._selected_duration = self._samples = 0
        self._sum = ReferenceIntegralSum(partial_limit) if spec.operation == 'sample_mean' else None

    @property
    def selected_duration_ns(self):
        """读取累计TRUE值有效时长。参数: 无。返回: 原生int纳秒。异常: 无。"""
        return self._selected_duration  # 不作为样本均值分母。

    @property
    def value_valid_duration_ns(self):
        """读取累计值有效时长。参数: 无。返回: 原生int纳秒。异常: 无。"""
        return self._value_duration  # 与条件TRUE/FALSE/UNKNOWN独立。

    @property
    def valid_sample_count(self):
        """读取有效真实样本数。参数: 无。返回: 原生int。异常: 无。"""
        return self._samples  # TTL/条件更新或裁剪保持不增加此数。

    def push(self, series, *, sample_consumer=None):
        """消费有限块双覆盖与真实样本，不以保持区间代替样本。

        参数: series为同unit/dtype有限CalculationSeries，条件可省略为全TRUE。
        返回: SampleCalculationFacts；mean精度失败进入输入覆盖，求和故障不改覆盖。
        异常: 结构、身份、容量、分配或取消传播；外层异常后不能接着使用前缀状态。
        """
        # 输入结构和交集先核对，跨块原表达式绑定身份必须保持。
        actual = require_sample_series(series, self._spec, self._input_unit, self._dtype)
        if self._identity is not None and self._identity != series.binding_identity:
            raise ValueError('样本归约不能跨绑定身份累计')
        self._identity = series.binding_identity
        # 只有mean走浮点精度门槛，min/max不把大整数舍入为float。
        values = tuple(to_float_reference(value) for value in series.values) if self._spec.operation == 'sample_mean' or self._moments is not None else series.values
        unconditional = ScalarValue(True, D.BOOL)
        start, end = (actual.start_ns, actual.end_ns) if actual is not None else (0, 0)
        value_duration = known_duration = selected_duration = selected_unknown = false_duration = samples = 0
        value_unknown, condition_unknown, chosen = [], [], []
        quality = Q.NONE
        # 独立逐正区间计算双覆盖；这只说明保持事实，不向数值样本归约添加值。
        for index in range(len(series.times_ns)-1):
            left, right = max(series.times_ns[index], start), min(series.times_ns[index+1], end)
            if left >= right:
                continue
            value = values[index]
            condition = series.conditions[index] if series.conditions is not None else unconditional
            dt = right-left
            quality |= series.diagnostics[index] | value.quality | condition.quality
            if value.valid:
                value_duration += dt
            else:
                value_unknown.append(Interval(left, right))
            if condition.valid:
                known_duration += dt
                if not condition.value:
                    false_duration += dt
                elif value.valid:
                    selected_duration += dt
                else:
                    selected_unknown += dt
            else:
                condition_unknown.append(Interval(left, right))
        # 半开窗口真实原值更新才进入候选；外条件变化和共享右端不产生样本。
        for index, time in enumerate(series.times_ns):
            if not start <= time < end or not series.actual_value_updates[index]:
                continue
            value = values[index]
            condition = series.conditions[index] if series.conditions is not None else unconditional
            quality |= series.diagnostics[index] | value.quality | condition.quality
            if not value.valid or not condition.valid or not condition.value:
                continue
            samples += 1
            if sample_consumer is not None:
                chosen.append(value)
            elif self._spec.operation == 'sample_mean' or self._moments is not None:
                chosen.append(value.value)
            elif self._quantile is not None:
                # 虽可在同一批中见到许多样本，先预付每个被保留的值，再追加。
                self._quantile.append((value.value,))
            elif self._spec.operation != 'sample_count':
                # 极值只存一个原dtype候选，不按时长加权或保留跨块样本集合。
                self._candidate = value.value if self._candidate is None else (min if self._spec.operation == 'sample_minimum' else max)(self._candidate, value.value)
        # raw原单位样本按原序推进；中间溢出不会因后续抵消恢复正常。
        if sample_consumer is not None and chosen:
            sample_consumer(tuple(chosen))
        if self._sum is not None:
            self._sum.push_values(tuple(chosen), (True,)*len(chosen))
        elif self._moments is not None:
            self._moments.push(chosen)
        # 跨块只留精确计数，返回的有限双未知和来源仍需外层owner计费及管理生命周期。
        self._value_duration += value_duration
        self._selected_duration += selected_duration
        self._samples += samples
        return SampleCalculationFacts(self._spec, actual, value_duration, known_duration, selected_duration,
            selected_unknown, false_duration, samples, merge_ranges(value_unknown), merge_ranges(condition_unknown),
            quality, self._input_unit, self._dtype, series.binding_identity, series.source_refs)

    def finish(self):
        """完成原单位总和、除真实样本数，再仅一次转换输出单位。

        参数: 无。返回: SampleReductionResult快照，不清空状态或分类覆盖政策。
        异常: 配置/分配错误传播；原序和、除法、精度或换算故障返回None及质量。
        """
        # 空真实样本没有数值证据，即使保持值长期有效也不能补正常零。
        if self._spec.operation == 'sample_count' and self._samples:
            # 整数计数已跨块累计；不需要任何原数值候选或单位换算。
            return SampleReductionResult(self._samples, '1', False, Q.NONE, self._samples)
        if self._quantile is not None:
            value, quality = self._quantile.finish()
            if value is not None:
                value, quality = convert_result_reference(value, self._dtype, self._conversion)
            return SampleReductionResult(value, self._unit, quality != Q.NONE, quality, self._samples)
        if self._moments is not None:
            value, quality = self._moments.finish(self._spec.ddof, self._conversion.factor)
            return SampleReductionResult(value, self._unit, quality != Q.NONE, quality, self._samples,
                                         insufficient_samples=self._spec.ddof == 1 and self._samples == 1)
        if self._samples == 0:
            return SampleReductionResult(None, self._unit, False, Q.NONE, 0)
        quality = Q.NONE
        if self._sum is not None:
            # 此处原单位factor=1先完成总和，不能先输出换单位或先归约块均值。
            number = self._sum.finish(self._input_unit)
            if number.calculation_failed:
                return SampleReductionResult(None, self._unit, True, number.quality, self._samples)
            value = number.value / self._samples
            if not isfinite(value) or value == 0 and number.value != 0:
                quality |= Q.NONFINITE if not isfinite(value) else Q.PRECISION_LOSS
        else:
            value = self._candidate
        # v4换算包含偏移；输入/归约故障不能被正常单位结果覆盖。
        if quality == Q.NONE:
            value, quality = convert_result_reference(value, self._dtype, self._conversion)
        # 成功浮点零统一+0.0；所有数值故障保留真实样本数而不改输入覆盖。
        if quality == Q.NONE and type(value) is float and value == 0:
            value = 0.0
        return SampleReductionResult(None if quality != Q.NONE else value, self._unit, quality != Q.NONE, quality, self._samples)

    def close(self):
        """退回按需分位数存储；无动态存储的样本归约无需释放费用。

        参数: 无。返回: None。异常: 预算释放失败时保留可重试的子缓冲。
        """
        if self._quantile is not None:
            self._quantile.close()
