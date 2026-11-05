"""独立标量归约有限条件极值、规范化时间均值和主BOOL持续时间。

push保留值与外条件各自的覆盖、真实更新、未知及完整来源；跨块仅保存候选与时长。
min/max保留原整数，duration累计外TRUE主TRUE的精确ns并保留主FALSE零证据。
mean首遍只查有效/选择事实，次遍以全窗TRUE有效时长D计算x*(dt/D)，不先算面积。
权重及原序求和故障与输入覆盖分开；单位仅finish转换一次。纯核不读来源、不预约
预算或保存全轴，有限临时列及误差项须由外层owner计费，推进异常后须放弃状态。
"""

# 仅使用标量及同后端原序误差核，不调用数组面积、对齐或归约。
from math import isfinite
from .calculation_output_reference import convert_result_reference
from .conditional_time_reduction import ConditionalTimeCalculationFacts, require_conditional_time_series
from .integral_sum_reference import ReferenceIntegralSum
from .moments import TIME_MOMENTS
from .moments_reference import ReferenceMoments
from .calculations import merge_ranges
from .models import Interval
from .numeric import ScalarValue, to_float_reference
from .time_reduction import TimeReductionResult, require_time_config, require_time_options
from .integral_terms import require_valid_until
from .record_intervals import clipped_record_seconds
from .types import QualityFlag as Q

from .time_reduction import MeanTimeBlock
from .mean_weights_reference import normalized_mean_terms


class ReferenceConditionalTimeReduction:
    """保存一个原dtype候选、精确时长与有界误差项，mean两遍实例不能混用。"""

    def __init__(self, spec, input_unit, dtype, *, selected_duration_ns=None, partial_limit=4096,
                 step_ns=None, selected_weight_seconds=None):
        """验证原配置并建立本后端有限状态。

        参数: spec/input_unit/dtype为原配置；selected_duration_ns为mean次遍全TRUE有效分母；
            partial_limit为误差项容量；step_ns选周期，周期均值次遍传selected_weight_seconds。返回: None。异常: 配置或分配错误传播。
        """
        # 共享的静态门槛先核对算子、类型、单位及mean分母，不执行数值计算。
        self._conversion = require_time_config(spec, input_unit, dtype, selected_duration_ns, partial_limit,
            step_ns=step_ns, selected_weight_seconds=selected_weight_seconds)
        self._unit, self._factor = self._conversion.unit, self._conversion.factor
        self._moments = ReferenceMoments(spec.operation) if spec.operation in TIME_MOMENTS else None
        self._spec, self._input_unit, self._dtype = spec, input_unit, dtype
        self._step_ns = step_ns
        self._denominator = selected_duration_ns if step_ns is None else selected_weight_seconds
        # 固定状态不随块数增加；mean首遍不建立数值误差状态。
        self._identity = self._candidate = None
        self._value_duration = self._selected_duration = self._terms = 0
        self._numeric_quality = Q.NONE
        self._sum = ReferenceIntegralSum(partial_limit) if spec.operation == 'time_weighted_mean' and self._denominator is not None else None
        self._weight_sum = ReferenceIntegralSum(partial_limit) if step_ns is not None and spec.operation in ('duration', 'time_weighted_mean') else None

    @property
    def selected_weight_seconds(self):
        """读取必要周期权重。参数: 无。返回: float或不适用None。异常: 权重求和故障。"""
        if self._weight_sum is None:
            return None
        result = self._weight_sum.finish('s')
        if result.calculation_failed:
            raise OverflowError('条件周期权重累计失败')
        return 0.0 if result.value is None else result.value

    @property
    def selected_duration_ns(self):
        """读取累计选择时长。参数: 无。返回: 原生int纳秒。异常: 无。"""
        return self._selected_duration  # duration仅主TRUE；mean为全TRUE有效分母事实。

    @property
    def value_valid_duration_ns(self):
        """读取累计值有效时长。参数: 无。返回: 原生int纳秒。异常: 无。"""
        return self._value_duration  # 外FALSE/UNKNOWN不改变原值可用性。

    def push(self, series, *, valid_until_ns=None, condition_valid_until_ns=None, retain_unknown_ranges=True, retain_mean_terms=False):
        """独立消费有限联合块，返回完整双覆盖并推进原单位候选。

        参数: series为同单位/dtype且有显式BOOL条件的有限CalculationSeries。
        valid_until_ns/condition_valid_until_ns分别截断实际有效期；
            retain_unknown_ranges=False省去两类未知范围。
        retain_mean_terms仅均值首遍返回MeanTimeBlock，其他调用返回事实。
        返回: ConditionalTimeCalculationFacts；mean权重故障只记数值质量，不改覆盖。
        异常: 结构、身份、容量或分配错误传播；外层不得继续使用异常前缀状态。
        """
        # 输入先过明确条件/单位/dtype与交集门槛，跨块不能更换原值绑定身份。
        actual = require_conditional_time_series(series, self._spec, self._input_unit, self._dtype)
        require_time_options(series, self._step_ns, valid_until_ns, retain_unknown_ranges)
        require_valid_until(series.times_ns, condition_valid_until_ns)
        if type(retain_mean_terms) is not bool or retain_mean_terms and (self._spec.operation != 'time_weighted_mean' or self._denominator is not None):
            raise ValueError('仅均值首遍可请求必要回读项')
        if self._identity is not None and self._identity != series.binding_identity:
            raise ValueError('条件时间归约不能跨绑定身份累计')
        self._identity = series.binding_identity
        # 只有mean检查to_float精度；极值和主BOOL不被提升成浮点类型。
        values = tuple(to_float_reference(value) for value in series.values) if self._spec.operation == 'time_weighted_mean' or self._moments is not None else series.values
        start, end = (actual.start_ns, actual.end_ns) if actual is not None else (0, 0)
        value_duration = known_duration = selected_duration = selected_unknown = false_duration = selected_false = samples = terms = 0
        value_unknown, condition_unknown, weighted = [], [], []
        period_weights = [] if self._weight_sum is not None else None
        mean_values = [] if self._moments is not None or (self._spec.operation == 'time_weighted_mean' and
                            (self._denominator is not None or retain_mean_terms)) else None
        mean_weights = [] if mean_values is not None else None
        quality, weight_quality = Q.NONE, Q.NONE
        # 每个正区间先核对双覆盖，再决定TRUE有效数值是否推进，末点没有区间。
        for index in range(len(series.times_ns) - 1):
            left, right = max(series.times_ns[index], start), min(series.times_ns[index+1], end)
            if left >= right:
                continue
            value, condition = values[index], series.conditions[index]
            quality |= series.diagnostics[index] | value.quality | condition.quality
            deadline = None if valid_until_ns is None else valid_until_ns[index]
            condition_deadline = None if condition_valid_until_ns is None else condition_valid_until_ns[index]
            value_end = max(left, min(right, deadline)) if deadline is not None else right
            condition_end = max(left, min(right, condition_deadline)) if condition_deadline is not None else right
            value_end = value_end if value.valid else left
            condition_end = condition_end if condition.valid else left
            value_duration += value_end - left
            known_duration += condition_end - left
            if value_end < right:
                if retain_unknown_ranges:
                    value_unknown.append(Interval(value_end, right))
                if value.valid:
                    quality |= Q.STALE
            if condition_end < right:
                if retain_unknown_ranges:
                    condition_unknown.append(Interval(condition_end, right))
                if condition.valid:
                    quality |= Q.STALE
            if condition_end <= left:
                continue
            if not condition.value:
                false_duration += condition_end - left
                continue
            chosen_end = min(value_end, condition_end)
            selected_unknown += condition_end - chosen_end
            if chosen_end <= left:
                continue
            dt = chosen_end - left
            # 外TRUE主FALSE仍是duration正常0证据，但不增加已选时长与真实样本。
            terms += 1
            if self._spec.operation == 'duration' and not value.value:
                selected_false += dt
            else:
                selected_duration += dt
            measure = dt
            if (period_weights is not None or (self._step_ns is not None and self._moments is not None)) and (self._spec.operation != 'duration' or value.value):
                measure = clipped_record_seconds(series.times_ns[index], series.times_ns[index+1],
                    Interval(left, chosen_end), step_ns=self._step_ns)
                if period_weights is not None:
                    period_weights.append(measure)
            if self._spec.operation in ('min_time', 'max_time'):
                # 每次只比较一个原dtype候选，跨块不转float，保留大整数的精确极值。
                self._candidate = value.value if self._candidate is None else (min if self._spec.operation == 'min_time' else max)(self._candidate, value.value)
            elif mean_values is not None:
                mean_values.append(value.value)
                mean_weights.append(measure)
        # 原值真实更新才计样本，外条件TRUE且duration另须主TRUE；右端与条件更新不计。
        for index, time in enumerate(series.times_ns):
            if not start <= time < end or not series.actual_value_updates[index]:
                continue
            value, condition = values[index], series.conditions[index]
            quality |= series.diagnostics[index] | value.quality | condition.quality
            deadline = None if valid_until_ns is None else valid_until_ns[index]
            condition_deadline = None if condition_valid_until_ns is None else condition_valid_until_ns[index]
            if (value.valid and condition.valid and condition.value
                    and (deadline is None or time < deadline) and (condition_deadline is None or time < condition_deadline)
                    and (self._spec.operation != 'duration' or value.value)):
                samples += 1
        # 任意权重故障使整次数值失败，不清除前述可核实覆盖；正常权重按原序推进。
        if self._denominator is not None:
            weighted, weight_quality = normalized_mean_terms(mean_values, mean_weights, self._denominator)
        if self._moments is not None:
            self._moments.push(mean_values, mean_weights)
        self._numeric_quality |= weight_quality
        if period_weights is not None:
            self._weight_sum.push_values(tuple(period_weights), (True,)*len(period_weights))
        if self._sum is not None and self._numeric_quality == Q.NONE:
            self._sum.push_values(tuple(weighted), (True,)*len(weighted))
        self._value_duration += value_duration
        self._selected_duration += selected_duration
        self._terms += terms
        facts = ConditionalTimeCalculationFacts(self._spec, actual, value_duration, known_duration, selected_duration,
            selected_unknown, false_duration, selected_false, samples, merge_ranges(value_unknown),
            merge_ranges(condition_unknown), quality, self._input_unit, self._dtype, series.binding_identity, series.source_refs, retain_unknown_ranges)
        return MeanTimeBlock(facts, tuple(mean_values), tuple(mean_weights)) if retain_mean_terms else facts

    def finish(self):
        """生成数值快照并只转换一次，覆盖与全外FALSE分类由外层处理。

        参数: 无。返回: 既有TimeReductionResult。异常: mean首遍RuntimeError、次遍分母不符ValueError；
            配置/分配错误传播，数值故障保留None和质量。
        """
        # mean首遍没有候选；次遍只有累计选择时长与原确认分母一致才能交付。
        if self._moments is not None:
            value, quality = self._moments.finish(self._spec.ddof, self._conversion.factor)
            return TimeReductionResult(value, self._unit, quality != Q.NONE, quality, self._terms)
        if self._spec.operation == 'time_weighted_mean':
            if self._denominator is None:
                raise RuntimeError('条件时间均值首遍只收事实，不能生成数值')
            measured = self._selected_duration if self._step_ns is None else self.selected_weight_seconds
            if measured != self._denominator:
                raise ValueError('条件均值次遍选择时长与全窗分母不同')
            if self._numeric_quality != Q.NONE:
                return TimeReductionResult(None, self._unit, True, self._numeric_quality, self._terms)
            # 同后端原序核负责一次最终单位转换，不在映射结果时再次乘因子。
            number = self._sum.finish(self._input_unit,
                                      1.0)
            if not number.calculation_failed:
                value, quality = convert_result_reference(number.value, self._dtype, self._conversion)
                return TimeReductionResult(value, self._unit, quality != Q.NONE, quality, self._terms)
            return TimeReductionResult(number.value, self._unit, number.calculation_failed, number.quality, self._terms)
        # 外FALSE/UNKNOWN或值全未知没有有效项，空证据分类由外层负责。
        if self._terms == 0:
            return TimeReductionResult(None, self._unit, False, Q.NONE, 0)
        value = ((self._selected_duration / 1_000_000_000 if self._step_ns is None else self.selected_weight_seconds)
                 if self._spec.operation == 'duration' else self._candidate)
        quality = Q.NONE
        # 极值factor=1保留精确整数；显式换单位先检查整数浮点可表示性。
        # v4换算包含偏移；输入/归约故障不能被正常单位结果覆盖。
        if quality == Q.NONE:
            value, quality = convert_result_reference(value, self._dtype, self._conversion)
        return TimeReductionResult(None if quality != Q.NONE else value, self._unit, quality != Q.NONE, quality, self._terms)
