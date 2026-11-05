"""用真实数组处理有限块时间极值、规范化时间均值及BOOL TRUE时长。

push把有限CalculationSeries装成(N,)typed列，区间使用(N-1,)int64纳秒差与bool掩码。
min/max保留原dtype；duration用TRUE掩码精确累计纳秒；mean先独立检查整数
浮点精度，第二遍以全窗有效时长规范化权重，再推进本数组原序误差归约。
最终单位仅finish转换一次，不读旧来源、不保存全轴，也不调用参考数值核。
装箱和未知Interval恢复循环只处理协议；数值裁剪、掩码、权重和极值用数组。
状态驱动累计少量标量事实；数组及误差状态预算由外层owner提前预约。
指定step_ns只接收所选驱动真实点；时长/均值按实际交集折算，另有一份有限权重
求和状态。接线者须预约这份状态和当前权重数组，不能沿用actual的费用冒充已计费。
"""

# 本后端只复用数组原序核与静态模型，数值不委托参考实现。
import numpy as np
from .calculation_output_numpy import convert_result_numpy
from .integral_sum_numpy import NumpyIntegralSum
from .moments import TIME_MOMENTS
from .moments_numpy import NumpyMoments
from .models import Interval
from .numeric_numpy import NumericArray, DTYPES, to_float_numpy
from .types import QualityFlag as Q
from .time_reduction import (TimeCalculationFacts, TimeReductionResult,
                             require_time_config, require_time_series, require_time_options)

from .time_reduction import MeanTimeBlock
from .mean_weights_numpy import normalized_mean_terms


class NumpyTimeReduction:
    """保留单候选、精确时长计数及有限误差数组，不保留历史输入列。

    mean分母为None时只处理第一遍事实，不能finish；第二遍须逐块消费同一历史。
    原序浮点累计属于state_driver，每项误差推进与块掩码均是实际数组运算。
    """

    def __init__(self, spec, input_unit, dtype, *, selected_duration_ns=None, partial_limit=4096,
                 step_ns=None, selected_weight_seconds=None):
        """检查无条件时间配置并建立本数组后端状态。

        参数: spec/单位/dtype为原配置；selected_duration_ns为均值全窗有效时长；
            partial_limit为误差容量；step_ns可选周期，周期均值第二遍改用
            selected_weight_seconds。返回: None。异常: 配置、数组分配错误传播。
        """
        self._conversion = require_time_config(spec, input_unit, dtype, selected_duration_ns, partial_limit,
            step_ns=step_ns, selected_weight_seconds=selected_weight_seconds)
        self._unit, self._factor = self._conversion.unit, self._conversion.factor
        self._moments = NumpyMoments(spec.operation) if spec.operation in TIME_MOMENTS else None
        self._spec, self._input_unit, self._dtype = spec, input_unit, dtype
        self._step_ns = step_ns
        self._denominator = selected_duration_ns if step_ns is None else selected_weight_seconds
        # 固定状态不随输入块数增长，输入列生命周期只限当前push。
        self._identity = self._candidate = None
        self._value_duration = self._selected_duration = self._terms = 0
        self._numeric_quality = Q.NONE
        self._sum = NumpyIntegralSum(partial_limit) if spec.operation == 'time_weighted_mean' and self._denominator is not None else None
        self._weight_sum = NumpyIntegralSum(partial_limit) if step_ns is not None and spec.operation in ('duration', 'time_weighted_mean') else None

    @property
    def selected_weight_seconds(self):
        """读取必要的周期累计权重。参数: 无。返回: float或不适用None。异常: 数值故障。"""
        if self._weight_sum is None:
            return None
        result = self._weight_sum.finish('s')
        if result.calculation_failed:
            raise OverflowError('周期权重累计失败')
        return 0.0 if result.value is None else result.value

    @property
    def selected_duration_ns(self):
        """读取累计选择时长。参数: 无。返回: 原生int纳秒。异常: 无。"""
        return self._selected_duration

    @property
    def value_valid_duration_ns(self):
        """读取累计有效时长。参数: 无。返回: 原生int纳秒。异常: 无。"""
        return self._value_duration

    def push(self, series, *, valid_until_ns=None, retain_unknown_ranges=True, retain_mean_terms=False):
        """数组计算有限块事实，并推进对应原单位数值状态。

        参数: series为无条件、同dtype和原单位CalculationSeries；末点不贡献区间或样本。
        valid_until_ns按实际时间截断；retain_unknown_ranges=False省去未知位置构造。
        retain_mean_terms仅均值首遍返回MeanTimeBlock，其他调用返回事实。
        返回: TimeCalculationFacts；数值权重故障与输入覆盖有效性分别记录。
        异常: 结构、身份、容量或分配错误传播；外层异常后只能清理owner。
        内存: 新数组都是当前(N,)或(N-1,)有限列，不修改输入，也不存入跨块状态。
        """
        actual = require_time_series(series, self._spec, self._input_unit, self._dtype)
        require_time_options(series, self._step_ns, valid_until_ns, retain_unknown_ranges)
        if type(retain_mean_terms) is not bool or retain_mean_terms and (self._spec.operation != 'time_weighted_mean' or self._denominator is not None):
            raise ValueError('仅均值首遍可请求必要回读项')
        if self._identity is not None and self._identity != series.binding_identity:
            raise ValueError('时间归约不能跨绑定身份累计')
        self._identity = series.binding_identity
        # 装箱仅恢复typed列；无效位置0需要显式valid和quality，不能作为正常值。
        column = NumericArray(self._dtype,
                              np.array([value.value if value.valid else 0 for value in series.values], dtype=DTYPES[self._dtype]),
                              np.array([value.valid for value in series.values], dtype=bool),
                              np.array([int(value.quality) for value in series.values], dtype=np.uint16))
        values = to_float_numpy(column) if self._spec.operation == 'time_weighted_mean' or self._moments is not None else column
        times = np.array(series.times_ns, dtype=np.int64)
        start, end = (actual.start_ns, actual.end_ns) if actual is not None else (0, 0)
        # 先裁剪整数端点，仅在正交集做差，避免域外反序减法wrap。
        left = np.maximum(times[:-1], np.int64(start))
        right = np.minimum(times[1:], np.int64(end))
        observed = right > left
        deadlines = np.array([2**63-1 if item is None else item for item in valid_until_ns], dtype=np.int64) if valid_until_ns is not None else None
        value_end = right.copy() if deadlines is None else np.minimum(right, deadlines[:-1])
        value_end = np.maximum(left, np.where(values.valid[:-1], value_end, left))
        durations = np.zeros(len(left), dtype=np.int64)
        usable = observed & (value_end > left)
        np.subtract(value_end, left, out=durations, where=usable)
        selected = usable & values.values[:-1] if self._spec.operation == 'duration' else usable
        # 非负时长总和不超过已校验观测跨度，int64不会wrap；全窗由Python整数累加。
        value_duration = int(np.sum(durations[usable], dtype=np.int64))
        selected_duration = int(np.sum(durations[selected], dtype=np.int64))
        seconds = None
        if self._weight_sum is not None or (self._step_ns is not None and self._moments is not None):
            # 只计算当前有限块；求和后列只读，后续归一化另生成数值结果。
            seconds = durations[selected].astype(np.float64)
            seconds /= np.diff(times)[selected]
            seconds *= self._step_ns / 1_000_000_000
            weight_valid = np.ones(len(seconds), dtype=bool)
            seconds.setflags(write=False)
            weight_valid.setflags(write=False)
            if self._weight_sum is not None:
                self._weight_sum.push_values(seconds, weight_valid)
        terms = int(np.count_nonzero(usable))
        samples = (times >= start) & (times < end) & np.array(series.actual_value_updates, dtype=bool) & values.valid
        if deadlines is not None:
            samples &= times < deadlines
        if self._spec.operation == 'duration':
            samples &= values.values
        # 依赖诊断覆盖正区间与实际更新点；EOF右端不凭点增加时长或样本。
        relevant = np.concatenate((observed, np.array([False]))) | ((times >= start) & (times < end) & np.array(series.actual_value_updates, dtype=bool))
        diagnostics = np.array([int(item) for item in series.diagnostics], dtype=np.uint16) | values.quality
        quality = Q(int(np.bitwise_or.reduce(diagnostics[relevant], initial=np.uint16(0))))
        if np.any(observed & values.valid[:-1] & (value_end < right)):
            quality |= Q.STALE
        unknown = (tuple(Interval(int(value_end[index]), int(right[index])) for index in np.flatnonzero(observed & (value_end < right)))
                   if retain_unknown_ranges else ())
        if self._spec.operation in ('min_time', 'max_time') and terms:
            # 每块极值由原dtype数组归约，跨块仅保存一个精确原生候选。
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
        facts = TimeCalculationFacts(self._spec, actual, value_duration, selected_duration,
                               int(np.count_nonzero(samples)), unknown, quality, self._input_unit,
                               self._dtype, series.binding_identity, series.source_refs, retain_unknown_ranges)
        if retain_mean_terms:
            selected_values = values.values[:-1][usable]
            selected_weights = durations[usable].copy() if self._step_ns is None else seconds
            selected_values.setflags(write=False)
            selected_weights.setflags(write=False)
            return MeanTimeBlock(facts, selected_values, selected_weights)
        return facts

    def finish(self):
        """正确舍入并做一次最终转换，生成本后端数值快照。

        参数: 无。返回: TimeReductionResult，不执行覆盖状态分类。
        异常: RuntimeError为mean第一遍；ValueError为有效时长与全窗分母不符；
            分配或取消传播，数值溢出与非零下溢写成计算失败。
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
            # 数组原序核直接执行一次输出转换；映射冻结结果不再次做数值处理。
            number = self._sum.finish(self._input_unit,
                                      1.0)
            if not number.calculation_failed:
                value, quality = convert_result_numpy(number.value, self._dtype, self._conversion)
                return TimeReductionResult(value, self._unit, quality != Q.NONE, quality, self._terms)
            return TimeReductionResult(number.value, self._unit, number.calculation_failed, number.quality, self._terms)
        if self._terms == 0:
            return TimeReductionResult(None, self._unit, False, Q.NONE, 0)
        # BOOL时长先保持精确整数纳秒，再最终换成秒；极值保持原native dtype。
        value = ((float(np.divide(np.float64(self._selected_duration), np.float64(1_000_000_000)))
                  if self._step_ns is None else self.selected_weight_seconds)
                 if self._spec.operation == 'duration' else self._candidate)
        quality = Q.NONE
        # v4换算包含偏移；输入/归约故障不能被正常单位结果覆盖。
        if quality == Q.NONE:
            value, quality = convert_result_numpy(value, self._dtype, self._conversion)
        return TimeReductionResult(None if quality != Q.NONE else value, self._unit,
                                   quality != Q.NONE, quality, self._terms)
