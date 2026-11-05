"""独立用标量处理有限块时间极值、规范化时间均值和BOOL TRUE时长。

push接收原单位CalculationSeries，返回该块的覆盖、更新、未知及来源事实。
min/max保留原整数；duration精确累计纳秒；mean第一遍只查有效性，第二遍
使用已知全窗有效时长计算每项x*(dt/D)，并由本参考后端原序误差核归约。
最终单位只在finish转换一次，不先求块均值或块面积、不保存全窗列。
指定step_ns时只接收所选驱动真实记录对，按实际交集折算周期；时长/均值额外
使用一份有界权重求和状态，不把浮点权重冒充实际纳秒覆盖。外层须为其预付费用。
本纯核只依赖标准库与参考算法，不执行I/O、资源预约或关闭；有限临时列表、
误差状态及返回事实必须由外层owner预先计费，推进异常后外层须放弃该状态。
"""

# 参考核不导入NumPy；复用同后端已验证的原序误差状态，不复用数组算法。
from math import isfinite
from .calculation_output_reference import convert_result_reference
from .integral_sum_reference import ReferenceIntegralSum
from .moments import TIME_MOMENTS
from .moments_reference import ReferenceMoments
from .models import Interval
from .numeric import ScalarValue, to_float_reference
from .types import QualityFlag as Q
from .time_reduction import (TimeCalculationFacts, TimeReductionResult,
                             require_time_config, require_time_series, require_time_options)
from .record_intervals import clipped_record_seconds

from .time_reduction import MeanTimeBlock
from .mean_weights_reference import normalized_mean_terms


class ReferenceTimeReduction:
    """保留有限数值状态，第一遍与第二遍的mean实例不能混用。

    极值只保留一个原生候选，actual时长只保留整数；周期权重与均值误差项
    分别受partial_limit限制，原调用方的费用估算不能直接沿用到新周期模式。
    finish为不破坏状态的快照，未指定均值全窗分母时禁止生成候选数值。
    """

    def __init__(self, spec, input_unit, dtype, *, selected_duration_ns=None, partial_limit=4096,
                 step_ns=None, selected_weight_seconds=None):
        """检查明确配置，再建立本后端有限状态。

        参数: spec/单位/dtype为原输入；selected_duration_ns为均值第二遍整窗有效时长；
            partial_limit为误差容量；step_ns可选周期；周期均值第二遍使用
            selected_weight_seconds。返回: None。异常: 配置或分配错误原样传播。
        """
        self._conversion = require_time_config(spec, input_unit, dtype, selected_duration_ns, partial_limit,
            step_ns=step_ns, selected_weight_seconds=selected_weight_seconds)
        self._unit, self._factor = self._conversion.unit, self._conversion.factor
        self._moments = ReferenceMoments(spec.operation) if spec.operation in TIME_MOMENTS else None
        self._spec, self._input_unit, self._dtype = spec, input_unit, dtype
        self._step_ns = step_ns
        self._denominator = selected_duration_ns if step_ns is None else selected_weight_seconds
        # 常量状态不随着输入块数增长；输入身份在第一块确认后禁止变化。
        self._identity = self._candidate = None
        self._value_duration = self._selected_duration = self._terms = 0
        self._numeric_quality = Q.NONE
        self._sum = ReferenceIntegralSum(partial_limit) if spec.operation == 'time_weighted_mean' and self._denominator is not None else None
        # 只在周期时长/均值确实需要时保存有限权重误差项；不存逐条时间或输入。
        self._weight_sum = ReferenceIntegralSum(partial_limit) if step_ns is not None and spec.operation in ('duration', 'time_weighted_mean') else None

    @property
    def selected_weight_seconds(self):
        """读取周期模式的必要累计权重。参数: 无。返回: float或不适用None。异常: 数值故障。"""
        if self._weight_sum is None:
            return None
        result = self._weight_sum.finish('s')
        if result.calculation_failed:
            raise OverflowError('周期权重累计失败')
        return 0.0 if result.value is None else result.value

    @property
    def selected_duration_ns(self):
        """读取累计已选时长。参数: 无。返回: 原生int纳秒。异常: 无。"""
        return self._selected_duration

    @property
    def value_valid_duration_ns(self):
        """读取累计有效时长。参数: 无。返回: 原生int纳秒。异常: 无。"""
        return self._value_duration

    def push(self, series, *, valid_until_ns=None, retain_unknown_ranges=True, retain_mean_terms=False):
        """独立消费有限块并返回事实，不跨块保存输入列。

        参数: series为同dtype/原单位的无条件CalculationSeries，末点不参与正区间或样本。
        valid_until_ns按实际时间截断；retain_unknown_ranges=False省去未知位置构造。
        retain_mean_terms仅均值首遍返回MeanTimeBlock，其他调用返回事实。
        返回: TimeCalculationFacts；mean权重故障另记数值失败，不改变有效覆盖。
            step_ns模式只接受驱动真实点，不把合成TTL/窗口点当新周期。
        异常: 结构、身份、容量或分配错误原样传播；外层不得继续使用异常前缀。
        """
        actual = require_time_series(series, self._spec, self._input_unit, self._dtype)
        require_time_options(series, self._step_ns, valid_until_ns, retain_unknown_ranges)
        if type(retain_mean_terms) is not bool or retain_mean_terms and (self._spec.operation != 'time_weighted_mean' or self._denominator is not None):
            raise ValueError('仅均值首遍可请求必要回读项')
        if self._identity is not None and self._identity != series.binding_identity:
            raise ValueError('时间归约不能跨绑定身份累计')
        self._identity = series.binding_identity
        # 仅mean需要浮点精度门槛，极值不把大整数无声转成浮点数。
        values = tuple(to_float_reference(value) for value in series.values) if self._spec.operation == 'time_weighted_mean' or self._moments is not None else series.values
        start = actual.start_ns if actual is not None else 0
        end = actual.end_ns if actual is not None else 0
        value_duration = selected_duration = samples = terms = 0
        unknown, weighted = [], []
        period_weights = [] if self._weight_sum is not None else None
        mean_values = [] if self._moments is not None or (self._spec.operation == 'time_weighted_mean' and
                            (self._denominator is not None or retain_mean_terms)) else None
        mean_weights = [] if mean_values is not None else None
        quality, weight_quality = Q.NONE, Q.NONE
        # 逐正区间独立计算整数裁剪差与有效性，完全不调用NumPy。
        for index in range(len(series.times_ns) - 1):
            left, right = max(series.times_ns[index], start), min(series.times_ns[index + 1], end)
            if left >= right:
                continue
            value = values[index]
            quality |= series.diagnostics[index] | value.quality
            deadline = None if valid_until_ns is None else valid_until_ns[index]
            value_end = max(left, min(right, deadline)) if deadline is not None else right
            if not value.valid:
                value_end = left
            if value_end < right:
                if retain_unknown_ranges:
                    unknown.append(Interval(value_end, right))
                if value.valid:
                    quality |= Q.STALE
            if value_end <= left:
                continue
            dt = value_end - left
            value_duration += dt
            terms += 1
            # FALSE是有效主BOOL，仍提供零时长证据；只有TRUE增加选择时长。
            selected_duration += dt if self._spec.operation != 'duration' or value.value else 0
            measure = dt
            if (period_weights is not None or (self._step_ns is not None and self._moments is not None)) and (self._spec.operation != 'duration' or value.value):
                measure = clipped_record_seconds(series.times_ns[index], series.times_ns[index + 1],
                                                 Interval(left, value_end), step_ns=self._step_ns)
                if period_weights is not None:
                    period_weights.append(measure)
            if self._spec.operation in ('min_time', 'max_time'):
                if self._candidate is None:
                    self._candidate = value.value
                elif self._spec.operation == 'min_time':
                    self._candidate = min(self._candidate, value.value)
                else:
                    self._candidate = max(self._candidate, value.value)
            elif mean_values is not None:
                mean_values.append(value.value)
                mean_weights.append(measure)
        # 真实更新的点诊断与计数独立于保持区间，不把右端重复计算。
        for index, time in enumerate(series.times_ns):
            if not start <= time < end or not series.actual_value_updates[index]:
                continue
            value = values[index]
            quality |= series.diagnostics[index] | value.quality
            deadline = None if valid_until_ns is None else valid_until_ns[index]
            if value.valid and (deadline is None or time < deadline) and (self._spec.operation != 'duration' or value.value):
                samples += 1
        # 原序状态只接受正常权重项；任一权重失败使整次均值失败，覆盖仍完整保留。
        if self._denominator is not None:
            weighted, weight_quality = normalized_mean_terms(mean_values, mean_weights, self._denominator)
        if self._moments is not None:
            self._moments.push(mean_values, mean_weights)
        self._numeric_quality |= weight_quality
        if period_weights is not None:
            self._weight_sum.push_values(tuple(period_weights), (True,) * len(period_weights))
        if self._sum is not None and self._numeric_quality == Q.NONE:
            self._sum.push_values(tuple(weighted), (True,) * len(weighted))
        self._value_duration += value_duration
        self._selected_duration += selected_duration
        self._terms += terms
        facts = TimeCalculationFacts(self._spec, actual, value_duration, selected_duration, samples,
                               tuple(unknown), quality, self._input_unit, self._dtype,
                               series.binding_identity, series.source_refs, retain_unknown_ranges)
        return MeanTimeBlock(facts, tuple(mean_values), tuple(mean_weights)) if retain_mean_terms else facts

    def finish(self):
        """仅完整调用者确认后生成数值快照，最终转换一次。

        参数: 无。返回: TimeReductionResult，覆盖分类由外层负责。
        异常: RuntimeError为mean第一遍；ValueError为第二遍有效时长与分母不符；
            配置/分配错误传播，数值范围错误按calculation_failed返回。
        """
        if self._moments is not None:
            value, quality = self._moments.finish(self._spec.ddof, self._conversion.factor)
            return TimeReductionResult(value, self._unit, quality != Q.NONE, quality, self._terms)
        if self._spec.operation == 'time_weighted_mean':
            if self._denominator is None:
                raise RuntimeError('时间均值第一遍只收事实，不能生成数值')
            measured = self._selected_duration if self._step_ns is None else self.selected_weight_seconds
            if measured != self._denominator:
                raise ValueError('时间均值第二遍有效时长与整窗分母不同')
            if self._numeric_quality != Q.NONE:
                return TimeReductionResult(None, self._unit, True, self._numeric_quality, self._terms)
            # 本参考原序核finish直接执行一次转换；输出映射不再乘因子。
            number = self._sum.finish(self._input_unit,
                                      1.0)
            if not number.calculation_failed:
                value, quality = convert_result_reference(number.value, self._dtype, self._conversion)
                return TimeReductionResult(value, self._unit, quality != Q.NONE, quality, self._terms)
            return TimeReductionResult(number.value, self._unit, number.calculation_failed, number.quality, self._terms)
        # 没有有效正区间不能借sum空输入产生正常零。
        if self._terms == 0:
            return TimeReductionResult(None, self._unit, False, Q.NONE, 0)
        value = ((self._selected_duration / 1_000_000_000 if self._step_ns is None else self.selected_weight_seconds)
                 if self._spec.operation == 'duration' else self._candidate)
        quality = Q.NONE
        # 非1倍率的整数极值先校验精确float表示，再转换；倍率1保持原生整数。
        # v4换算包含偏移；输入/归约故障不能被正常单位结果覆盖。
        if quality == Q.NONE:
            value, quality = convert_result_reference(value, self._dtype, self._conversion)
        return TimeReductionResult(None if quality != Q.NONE else value, self._unit,
                                   quality != Q.NONE, quality, self._terms)
