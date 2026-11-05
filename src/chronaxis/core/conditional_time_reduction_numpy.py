"""用真实NumPy掩码归约有限条件时间极值、规范化均值和主BOOL时长。

typed值及外BOOL为(N,)列，正区间为(N-1,)精确int64差与独立bool掩码。极值在原
dtype上归约；duration同时保留外TRUE主FALSE零证据；mean首遍仅确认值精度和
TRUE有效选择，次遍计算x*(dt/D)，由本数组原序误差核推进。数值weight故障不改
双覆盖，最终单位只finish转换一次。装箱、恢复未知和固定标量状态驱动不冒充
数组数值核；不调用参考算法、不读来源、不存全轴，有限内存由外层owner预约。
"""

# 原序推进复用独立数组误差状态，只共享结构/typed协议，不调用标量后端。
import numpy as np
from .calculation_output_numpy import convert_result_numpy
from .conditional_time_reduction import ConditionalTimeCalculationFacts, require_conditional_time_series
from .integral_sum_numpy import NumpyIntegralSum
from .moments import TIME_MOMENTS
from .moments_numpy import NumpyMoments
from .calculations import merge_ranges
from .models import Interval
from .numeric_numpy import DTYPES, NumericArray, to_float_numpy
from .time_reduction import TimeReductionResult, require_time_config, require_time_options
from .integral_terms import require_valid_until
from .types import QualityFlag as Q

from .time_reduction import MeanTimeBlock
from .mean_weights_numpy import normalized_mean_terms


class NumpyConditionalTimeReduction:
    """保存单原dtype候选、整数时长与有界误差列，不存跨块输入数组。"""

    def __init__(self, spec, input_unit, dtype, *, selected_duration_ns=None, partial_limit=4096,
                 step_ns=None, selected_weight_seconds=None):
        """校验原配置并建立本数组后端固定状态。

        参数: spec/input_unit/dtype为原配置；selected_duration_ns为mean次遍全TRUE有效分母；
            partial_limit为误差容量；step_ns选周期，周期均值次遍传selected_weight_seconds。返回: None。异常: 配置、数组分配错误传播。
        """
        # 静态门槛只检查明确配置，两个后端不共享后续数值或覆盖计算。
        self._conversion = require_time_config(spec, input_unit, dtype, selected_duration_ns, partial_limit,
            step_ns=step_ns, selected_weight_seconds=selected_weight_seconds)
        self._unit, self._factor = self._conversion.unit, self._conversion.factor
        self._moments = NumpyMoments(spec.operation) if spec.operation in TIME_MOMENTS else None
        self._spec, self._input_unit, self._dtype = spec, input_unit, dtype
        self._step_ns = step_ns
        self._denominator = selected_duration_ns if step_ns is None else selected_weight_seconds
        # mean首遍不建立误差列，固定候选/计数不随块数增长。
        self._identity = self._candidate = None
        self._value_duration = self._selected_duration = self._terms = 0
        self._numeric_quality = Q.NONE
        self._sum = NumpyIntegralSum(partial_limit) if spec.operation == 'time_weighted_mean' and self._denominator is not None else None
        self._weight_sum = NumpyIntegralSum(partial_limit) if step_ns is not None and spec.operation in ('duration', 'time_weighted_mean') else None

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
        """读取累计已选时长。参数: 无。返回: 原生int纳秒。异常: 无。"""
        return self._selected_duration  # duration仅主TRUE；mean为规范化分母事实。

    @property
    def value_valid_duration_ns(self):
        """读取累计值有效时长。参数: 无。返回: 原生int纳秒。异常: 无。"""
        return self._value_duration  # 独立于外条件FALSE/UNKNOWN。

    def push(self, series, *, valid_until_ns=None, condition_valid_until_ns=None, retain_unknown_ranges=True, retain_mean_terms=False):
        """计算有限块双覆盖并按原序推进本后端数值候选。

        参数: series为同dtype/原单位且显式BOOL条件的有限CalculationSeries。
        valid_until_ns/condition_valid_until_ns分别截断实际有效期；
            retain_unknown_ranges=False省去两类未知范围。
        retain_mean_terms仅均值首遍返回MeanTimeBlock，其他调用返回事实。
        返回: ConditionalTimeCalculationFacts；权重故障仅改变数值失败状态，不改输入覆盖。
        异常: 结构、身份、容量、分配或取消错误传播，外层异常后只能清理owner。
        内存: 所有新输入/掩码列形状N或N-1，仅当前push存活，不修改调用者输入。
        """
        # 当前输入先核对显式条件/单位/dtype和交集，跨块原值绑定不能变化。
        actual = require_conditional_time_series(series, self._spec, self._input_unit, self._dtype)
        require_time_options(series, self._step_ns, valid_until_ns, retain_unknown_ranges)
        require_valid_until(series.times_ns, condition_valid_until_ns)
        if type(retain_mean_terms) is not bool or retain_mean_terms and (self._spec.operation != 'time_weighted_mean' or self._denominator is not None):
            raise ValueError('仅均值首遍可请求必要回读项')
        if self._identity is not None and self._identity != series.binding_identity:
            raise ValueError('条件时间归约不能跨绑定身份累计')
        self._identity = series.binding_identity
        # typed装箱仅恢复协议，值精度转换只对mean执行，极值保持int64/uint64原数组。
        column = NumericArray(self._dtype,
            np.array([value.value if value.valid else 0 for value in series.values], dtype=DTYPES[self._dtype]),
            np.array([value.valid for value in series.values], dtype=bool),
            np.array([int(value.quality) for value in series.values], dtype=np.uint16))
        values = to_float_numpy(column) if self._spec.operation == 'time_weighted_mean' or self._moments is not None else column
        known = np.array([condition.valid for condition in series.conditions], dtype=bool)
        truth = np.array([condition.value if condition.valid else False for condition in series.conditions], dtype=bool)
        condition_quality = np.array([int(condition.quality) for condition in series.conditions], dtype=np.uint16)
        times = np.array(series.times_ns, dtype=np.int64)
        start, end = (actual.start_ns, actual.end_ns) if actual is not None else (0, 0)
        # 整数端点先裁剪，只对正区间做差，域外反序不发生int64减法wrap。
        left, right = np.maximum(times[:-1], np.int64(start)), np.minimum(times[1:], np.int64(end))
        observed = right > left
        deadlines = np.array([2**63-1 if item is None else item for item in valid_until_ns], dtype=np.int64) if valid_until_ns is not None else None
        condition_deadlines = np.array([2**63-1 if item is None else item for item in condition_valid_until_ns], dtype=np.int64) if condition_valid_until_ns is not None else None
        value_end = right.copy() if deadlines is None else np.minimum(right, deadlines[:-1])
        condition_end = right.copy() if condition_deadlines is None else np.minimum(right, condition_deadlines[:-1])
        value_end = np.maximum(left, np.where(values.valid[:-1], value_end, left))
        condition_end = np.maximum(left, np.where(known[:-1], condition_end, left))
        # 三种交集独立做安全整数差，原始记录对仍留作周期权重分母。
        value_dt = np.zeros(len(left), dtype=np.int64)
        condition_dt = np.zeros(len(left), dtype=np.int64)
        durations = np.zeros(len(left), dtype=np.int64)
        np.subtract(value_end, left, out=value_dt, where=observed)
        np.subtract(condition_end, left, out=condition_dt, where=observed)
        np.subtract(np.minimum(value_end, condition_end), left, out=durations, where=observed)
        usable = observed & (durations > 0) & truth[:-1]
        selected = usable & values.values[:-1] if self._spec.operation == 'duration' else usable
        selected_false_mask = usable & ~values.values[:-1] if self._spec.operation == 'duration' else np.zeros(len(left), dtype=bool)
        # 所有非负dt归约不超过已检查int64实际跨度，跨块由Python整数累加。
        value_duration = int(np.sum(value_dt, dtype=np.int64))
        known_duration = int(np.sum(condition_dt, dtype=np.int64))
        selected_duration = int(np.sum(durations, where=selected, dtype=np.int64))
        selected_unknown = int(np.sum(condition_dt - durations, where=truth[:-1], dtype=np.int64))
        false_duration = int(np.sum(condition_dt, where=~truth[:-1], dtype=np.int64))
        selected_false = int(np.sum(durations, where=selected_false_mask, dtype=np.int64))
        terms = int(np.count_nonzero(usable))
        seconds = None
        if self._weight_sum is not None or (self._step_ns is not None and self._moments is not None):
            seconds = durations[selected].astype(np.float64)
            seconds /= np.diff(times)[selected]
            seconds *= self._step_ns / 1_000_000_000
            keep_weights = np.ones(len(seconds), dtype=bool)
            seconds.setflags(write=False)
            keep_weights.setflags(write=False)
            if self._weight_sum is not None:
                self._weight_sum.push_values(seconds, keep_weights)
        # 半开原值真实更新且外TRUE才成为样本；duration另要求主TRUE，条件更新不计。
        actual_samples = (times >= start) & (times < end) & np.array(series.actual_value_updates, dtype=bool)
        samples = actual_samples & values.valid & known & truth
        if deadlines is not None:
            samples &= times < deadlines
        if condition_deadlines is not None:
            samples &= times < condition_deadlines
        if self._spec.operation == 'duration':
            samples &= values.values
        relevant = actual_samples.copy()
        relevant[:-1] |= observed
        diagnostics = np.array([int(flag) for flag in series.diagnostics], dtype=np.uint16) | values.quality | condition_quality
        quality = Q(int(np.bitwise_or.reduce(diagnostics, where=relevant, initial=0)))
        # 元数据循环只恢复两种未知Interval，覆盖和数值运算均已由真实数组完成。
        if np.any(observed & ((values.valid[:-1] & (value_end < right)) | (known[:-1] & (condition_end < right)))):
            quality |= Q.STALE
        value_unknown = (tuple(Interval(int(value_end[index]), int(right[index])) for index in np.flatnonzero(observed & (value_end < right)))
                         if retain_unknown_ranges else ())
        condition_unknown = (tuple(Interval(int(condition_end[index]), int(right[index])) for index in np.flatnonzero(observed & (condition_end < right)))
                             if retain_unknown_ranges else ())
        if self._spec.operation in ('min_time', 'max_time') and terms:
            # 当前块原dtype极值，跨块仅比较一个同dtype候选，避免uint64精度舍入。
            candidate = (np.min if self._spec.operation == 'min_time' else np.max)(values.values[:-1][usable])
            if self._candidate is not None:
                previous = DTYPES[self._dtype].type(self._candidate)
                candidate = (np.minimum if self._spec.operation == 'min_time' else np.maximum)(previous, candidate)
            self._candidate = candidate.item()
        elif self._moments is not None:
            measures = durations[usable] if self._step_ns is None else seconds
            self._moments.push(values.values[:-1][usable], measures)
        elif self._spec.operation == 'time_weighted_mean' and self._denominator is not None:
            chosen = values.values[:-1][usable]
            measures = durations[usable].astype(np.float64) if self._step_ns is None else seconds
            weighted, weight_quality = normalized_mean_terms(chosen, measures, self._denominator)
            self._numeric_quality |= weight_quality
            if self._numeric_quality == Q.NONE:
                keep = np.ones(len(weighted), dtype=bool)
                keep.setflags(write=False)
                self._sum.push_values(weighted, keep)
        self._value_duration += value_duration
        self._selected_duration += selected_duration
        self._terms += terms
        facts = ConditionalTimeCalculationFacts(self._spec, actual, value_duration, known_duration, selected_duration,
            selected_unknown, false_duration, selected_false, int(np.count_nonzero(samples)), merge_ranges(value_unknown),
            merge_ranges(condition_unknown), quality, self._input_unit, self._dtype, series.binding_identity, series.source_refs, retain_unknown_ranges)
        if retain_mean_terms:
            selected_values = values.values[:-1][usable]
            selected_weights = durations[usable].copy() if self._step_ns is None else seconds
            selected_values.setflags(write=False)
            selected_weights.setflags(write=False)
            return MeanTimeBlock(facts, selected_values, selected_weights)
        return facts

    def finish(self):
        """生成原序统计快照并做一次最终换单位，双覆盖由外层分类。

        参数: 无。返回: 既有TimeReductionResult。异常: mean首遍RuntimeError、次遍分母不符ValueError；
            配置/分配/取消传播，数值溢出和非零下溢返回计算失败。
        """
        # mean首遍禁交付数值；次遍需要实际TRUE有效累计时长与全窗D相等。
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
            number = self._sum.finish(self._input_unit,
                                      1.0)
            if not number.calculation_failed:
                value, quality = convert_result_numpy(number.value, self._dtype, self._conversion)
                return TimeReductionResult(value, self._unit, quality != Q.NONE, quality, self._terms)
            return TimeReductionResult(number.value, self._unit, number.calculation_failed, number.quality, self._terms)
        # 没有正区间数值证据不补0；全外FALSE空0由外层完整请求分类证明。
        if self._terms == 0:
            return TimeReductionResult(None, self._unit, False, Q.NONE, 0)
        # 主FALSE为有效duration项而时长0；极值未换单位时保持原生精确整数。
        value = ((float(np.divide(np.float64(self._selected_duration), np.float64(1_000_000_000)))
                  if self._step_ns is None else self.selected_weight_seconds)
                 if self._spec.operation == 'duration' else self._candidate)
        quality = Q.NONE
        # v4换算包含偏移；输入/归约故障不能被正常单位结果覆盖。
        if quality == Q.NONE:
            value, quality = convert_result_numpy(value, self._dtype, self._conversion)
        return TimeReductionResult(None if quality != Q.NONE else value, self._unit, quality != Q.NONE, quality, self._terms)
