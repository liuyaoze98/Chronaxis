"""独立标量归约有限真实样本，保留原dtype极值与原序样本算术均值。

push分别计算值/条件覆盖，只将半开窗中有效/TRUE原值真实更新计入候选。极值
保留原整数；mean先检查float精度，原单位样本按原序推进有界误差核，finish完成
原量纲总和后除真实样本数，再换输出单位一次。原序中间溢出沿既有故障政策保持
失败，不改为time_weighted_mean的规范化权重；除法/换算故障不改输入覆盖。不调用NumPy、
不读来源、不保留全轴；有限临时样本和误差项须由外层owner计费，异常后须清理。
"""

# 标量覆盖及候选独立于数组后端；仅复用本参考原序误差状态。
from math import isfinite
from .integral_sum_reference import ReferenceIntegralSum
from .calculations import merge_ranges
from .models import Interval
from .numeric import ScalarValue, to_float_reference
from .sample_reduction import SampleCalculationFacts, SampleReductionResult, require_sample_config, require_sample_series
from .types import QualityFlag as Q, SignalDType as D


class ReferenceSampleReduction:
    """保存单原生候选、真实样本计数与有界误差项，不存历史输入列。"""

    def __init__(self, spec, input_unit, dtype, *, partial_limit=4096):
        """核对原配置并建立本参考后端有限状态。

        参数: spec/input_unit/dtype为原声明，partial_limit为正原生int误差容量。
        返回: None。异常: 配置或分配错误传播。
        """
        # 共享静态门槛先检查明确样本能力、数值类型和输出单位。
        self._unit, self._factor = require_sample_config(spec, input_unit, dtype, partial_limit)
        self._spec, self._input_unit, self._dtype = spec, input_unit, dtype
        self._identity = self._candidate = None
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

    def push(self, series):
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
        values = tuple(to_float_reference(value) for value in series.values) if self._spec.operation == 'sample_mean' else series.values
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
            if self._spec.operation == 'sample_mean':
                chosen.append(value.value)
            else:
                # 极值只存一个原dtype候选，不按时长加权或保留跨块样本集合。
                self._candidate = value.value if self._candidate is None else (min if self._spec.operation == 'sample_minimum' else max)(self._candidate, value.value)
        # raw原单位样本按原序推进；中间溢出不会因后续抵消恢复正常。
        if self._sum is not None:
            self._sum.push_values(tuple(chosen), (True,)*len(chosen))
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
        # 非1倍率极值先检查整数可精确float表示；倍率1保留原生整数。
        if quality == Q.NONE and self._factor != 1 and type(value) is int:
            converted = to_float_reference(ScalarValue(value, self._dtype))
            if not converted.valid:
                quality |= converted.quality
            else:
                value = converted.value
        if quality == Q.NONE and self._factor != 1:
            original = value
            value *= self._factor
            if not isfinite(value) or value == 0 and original != 0:
                quality |= Q.NONFINITE if not isfinite(value) else Q.PRECISION_LOSS
        # 成功浮点零统一+0.0；所有数值故障保留真实样本数而不改输入覆盖。
        if quality == Q.NONE and type(value) is float and value == 0:
            value = 0.0
        return SampleReductionResult(None if quality != Q.NONE else value, self._unit, quality != Q.NONE, quality, self._samples)
