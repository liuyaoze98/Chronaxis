"""用真实NumPy样本与覆盖掩码归约有限min/max/sample_mean。

输入值及可选BOOL为(N,)typed列，覆盖为(N-1,)精确int64差与bool掩码；真实样本
按半开窗口原值actual更新、有效和条件TRUE选择。极值保持原dtype，mean只转换
可核实值，并将原序样本推进本后端有界误差核。finish先完成原单位总和、除真实
样本数，再转换输出一次；原量纲中间溢出不改为时间规范权重。输入覆盖与数值
故障分开，不调用参考核、不重读来源、不保留全轴，有限临时内存由外层计费。
"""

# 数值与覆盖均用独立真实数组运算，仅共享typed模型与本数组原序误差状态。
import numpy as np
from .integral_sum_numpy import NumpyIntegralSum
from .calculations import merge_ranges
from .models import Interval
from .numeric_numpy import DTYPES, NumericArray, to_float_numpy
from .sample_reduction import SampleCalculationFacts, SampleReductionResult, require_sample_config, require_sample_series
from .types import QualityFlag as Q


class NumpySampleReduction:
    """保存单原dtype候选、真实样本数和有界误差列，不留存历史样本数组。"""

    def __init__(self, spec, input_unit, dtype, *, partial_limit=4096):
        """检查原配置并建立本数组后端有限状态。

        参数: spec/input_unit/dtype为原声明，partial_limit为正原生int误差容量。
        返回: None。异常: 配置、分配错误传播。
        """
        # 共享静态门槛不执行样本、浮点或覆盖计算。
        self._unit, self._factor = require_sample_config(spec, input_unit, dtype, partial_limit)
        self._spec, self._input_unit, self._dtype = spec, input_unit, dtype
        self._identity = self._candidate = None
        self._value_duration = self._selected_duration = self._samples = 0
        self._sum = NumpyIntegralSum(partial_limit) if spec.operation == 'sample_mean' else None

    @property
    def selected_duration_ns(self):
        """读取累计TRUE有效保持时长。参数: 无。返回: 原生int纳秒。异常: 无。"""
        return self._selected_duration  # 不是样本mean分母。

    @property
    def value_valid_duration_ns(self):
        """读取累计值有效时长。参数: 无。返回: 原生int纳秒。异常: 无。"""
        return self._value_duration  # 与选择条件独立。

    @property
    def valid_sample_count(self):
        """读取有效真实样本数。参数: 无。返回: 原生int。异常: 无。"""
        return self._samples  # 条件/TTL/边界更新不计入。

    def push(self, series):
        """独立数组计算双覆盖、真实样本掩码并推进对应候选。

        参数: series为同unit/dtype有限CalculationSeries，可选条件None表示全TRUE。
        返回: SampleCalculationFacts；mean精度入值覆盖，数值归约故障不改覆盖。
        异常: 结构、身份、容量、分配或取消传播；异常后外层只能清理owner。
        内存: 新列形状N/N-1或当前所选样本数，当前push存活，不修改输入列。
        """
        # 有限输入结构和整数交集先验证，禁止跨块更换原值绑定。
        actual = require_sample_series(series, self._spec, self._input_unit, self._dtype)
        if self._identity is not None and self._identity != series.binding_identity:
            raise ValueError('样本归约不能跨绑定身份累计')
        self._identity = series.binding_identity
        # N个typed原值、有效性与uint16质量独立装箱；无效0只是掩码约束的存储占位。
        column = NumericArray(self._dtype,
            np.array([value.value if value.valid else 0 for value in series.values], dtype=DTYPES[self._dtype]),
            np.array([value.valid for value in series.values], dtype=bool),
            np.array([int(value.quality) for value in series.values], dtype=np.uint16))
        # mean独立数组精度门槛，极值原int64/uint64保持；无条件显式全TRUE而非UNKNOWN。
        values = to_float_numpy(column) if self._spec.operation == 'sample_mean' else column
        size = len(series.times_ns)
        known = np.ones(size, dtype=bool) if series.conditions is None else np.array([condition.valid for condition in series.conditions], dtype=bool)
        truth = np.ones(size, dtype=bool) if series.conditions is None else np.array([condition.value if condition.valid else False for condition in series.conditions], dtype=bool)
        condition_quality = np.zeros(size, dtype=np.uint16) if series.conditions is None else np.array([int(condition.quality) for condition in series.conditions], dtype=np.uint16)
        times = np.array(series.times_ns, dtype=np.int64)
        start, end = (actual.start_ns, actual.end_ns) if actual is not None else (0, 0)
        # 覆盖只对正裁剪区间求int64差，绝对时间不转float，域外反序差不wrap。
        left, right = np.maximum(times[:-1], np.int64(start)), np.minimum(times[1:], np.int64(end))
        observed = right > left
        durations = np.zeros(len(left), dtype=np.int64)
        np.subtract(right, left, out=durations, where=observed)
        value_valid = observed & values.valid[:-1]
        selected = value_valid & known[:-1] & truth[:-1]
        value_duration = int(np.sum(durations, where=value_valid, dtype=np.int64))
        known_duration = int(np.sum(durations, where=observed & known[:-1], dtype=np.int64))
        selected_duration = int(np.sum(durations, where=selected, dtype=np.int64))
        selected_unknown = int(np.sum(durations, where=observed & known[:-1] & truth[:-1] & ~values.valid[:-1], dtype=np.int64))
        false_duration = int(np.sum(durations, where=observed & known[:-1] & ~truth[:-1], dtype=np.int64))
        # 样本(N,)掩码单独使用actual更新，不能由区间selected或条件变化推算。
        actual_samples = (times >= start) & (times < end) & np.array(series.actual_value_updates, dtype=bool)
        samples = actual_samples & values.valid & known & truth
        sample_count = int(np.count_nonzero(samples))
        relevant = actual_samples.copy()
        relevant[:-1] |= observed
        diagnostics = np.array([int(flag) for flag in series.diagnostics], dtype=np.uint16) | values.quality | condition_quality
        quality = Q(int(np.bitwise_or.reduce(diagnostics, where=relevant, initial=0)))
        # Python仅恢复有限未知定位；时长和样本计数均已由真实数组掩码归约。
        value_unknown = tuple(Interval(int(left[index]), int(right[index])) for index in np.flatnonzero(observed & ~values.valid[:-1]))
        condition_unknown = tuple(Interval(int(left[index]), int(right[index])) for index in np.flatnonzero(observed & ~known[:-1]))
        if self._sum is not None:
            # 按原(N,)位置顺序选择原单位样本，不先块求和或块均值；只读列交给本后端误差核。
            chosen = values.values[samples]
            keep = np.ones(len(chosen), dtype=bool)
            chosen.setflags(write=False)
            keep.setflags(write=False)
            self._sum.push_values(chosen, keep)
        elif sample_count:
            # 极值当前样本列用原dtype数组归约，跨块仅保留一个同dtype候选。
            candidate = (np.min if self._spec.operation == 'sample_minimum' else np.max)(values.values[samples])
            if self._candidate is not None:
                previous = DTYPES[self._dtype].type(self._candidate)
                candidate = (np.minimum if self._spec.operation == 'sample_minimum' else np.maximum)(previous, candidate)
            self._candidate = candidate.item()
        # 跨块仅累计三个原生计数；冻结事实保留原请求、双未知与完整真实来源。
        self._value_duration += value_duration
        self._selected_duration += selected_duration
        self._samples += sample_count
        return SampleCalculationFacts(self._spec, actual, value_duration, known_duration, selected_duration,
            selected_unknown, false_duration, sample_count, merge_ranges(value_unknown), merge_ranges(condition_unknown),
            quality, self._input_unit, self._dtype, series.binding_identity, series.source_refs)

    def finish(self):
        """完成原单位样本总和后除计数，并仅一次转换最终单位。

        参数: 无。返回: SampleReductionResult快照，覆盖政策由外层分类。
        异常: 配置、分配或取消传播；原序和、除法、精度、换算故障写None与质量。
        """
        # 没有真实有效样本只能无候选，保持时长不能替代此计数证明0。
        if self._samples == 0:
            return SampleReductionResult(None, self._unit, False, Q.NONE, 0)
        quality = Q.NONE
        if self._sum is not None:
            # 原单位factor=1先完成raw总和，原量纲中途溢出保持失败，不预规范化样本。
            number = self._sum.finish(self._input_unit)
            if number.calculation_failed:
                return SampleReductionResult(None, self._unit, True, number.quality, self._samples)
            with np.errstate(over='ignore', under='ignore', invalid='ignore'):
                value = np.divide(np.float64(number.value), np.float64(self._samples)).item()
            if not np.isfinite(value) or value == 0 and number.value != 0:
                quality |= Q.NONFINITE if not np.isfinite(value) else Q.PRECISION_LOSS
        else:
            value = self._candidate
        # 极值factor=1保留原生整数；明确换单位先用本数组精度核核对可表示性。
        if quality == Q.NONE and self._factor != 1 and type(value) is int:
            converted = to_float_numpy(NumericArray(self._dtype,
                np.array([value], dtype=DTYPES[self._dtype]), np.array([True]), np.array([0], dtype=np.uint16)))
            if not converted.valid[0]:
                quality |= Q(int(converted.quality[0]))
            else:
                value = converted.values[0].item()
        if quality == Q.NONE and self._factor != 1:
            original = value
            with np.errstate(over='ignore', under='ignore', invalid='ignore'):
                value = np.multiply(np.float64(value), np.float64(self._factor)).item()
            if not np.isfinite(value) or value == 0 and original != 0:
                quality |= Q.NONFINITE if not np.isfinite(value) else Q.PRECISION_LOSS
        # 只规范成功浮点零，不清除数值故障或改写真实样本/输入覆盖事实。
        if quality == Q.NONE and type(value) is float and value == 0:
            value = 0.0
        return SampleReductionResult(None if quality != Q.NONE else value, self._unit, quality != Q.NONE, quality, self._samples)
