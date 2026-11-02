"""用有限记录计算时间统计和真实样本统计；仅时间均值暂存必要值/权重。

输入与RecordIntegral共享点缓冲、递增时间和失效处理。复用原时间/样本数值核；
样本统计保真实更新标志，不把条件/TTL更新当新样本，样本均值使用原序求和。
均值首遍仅写值与权重，实际权重为int64纳秒，周期权重为float秒；
次遍按已知总权重规范化，避免先求面积溢出。
临时文件由本owner关闭时删除，不默认留现场；结果不附历史、贡献或时间对照。
调用者必须先确认来源EOF及关闭成功再finish，本对象不替代公共AnalysisRunner发布。
"""

from dataclasses import dataclass
from pathlib import Path
from struct import Struct
from tempfile import TemporaryFile

import numpy as np

from ..core.calculations import CalculationDefinition, CalculationSeries, classify_calculation_value
from ..core.calculations import classify_coverage
from ..core.models import Interval
from ..core.types import SignalDType as D, QualityFlag as Q
from ..core.time_reduction import require_time_config, TimeReductionResult
from ..core.time_reduction_reference import ReferenceTimeReduction
from ..core.time_reduction_numpy import NumpyTimeReduction
from ..core.conditional_time_reduction_reference import ReferenceConditionalTimeReduction
from ..core.conditional_time_reduction_numpy import NumpyConditionalTimeReduction
from ..core.integral_sum_reference import ReferenceIntegralSum
from ..core.integral_sum_numpy import NumpyIntegralSum
from ..core.mean_weights_reference import normalized_mean_terms as reference_mean
from ..core.mean_weights_numpy import normalized_mean_terms as numpy_mean
from ..results.budget import ResourceBudget, _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..results.errors import BudgetExceededError
from .history import _metadata_bytes
from .record_point_buffer import RecordPointBuffer
from ..core.sample_reduction import require_sample_config
from ..core.sample_reduction_reference import ReferenceSampleReduction
from ..core.sample_reduction_numpy import NumpySampleReduction
from .record_sample_series import sample_series


@dataclass(frozen=True)
class RecordTimeResult:
    """保存时间统计的必要输出，整数极值不转成浮点数。"""

    value: int | float | None
    unit: str
    status: str
    reason: str
    quality: Q
    coverage_status: str | None = None


class RecordTimeCalculation(RecordPointBuffer):
    """拥有一份点缓冲、数值状态及可选均值临时文件，失败后只能清理。"""

    def __init__(self, budget, spec, input_unit, dtype, step_ns, *, backend='numpy',
                 batch_intervals=64, partial_limit=4096, conditioned=False, work_dir=None):
        """预付有限状态，均值的文件延迟到首批有效项才创建。

        参数: 共享budget、时间统计spec、已求值类型/单位；step_ns为None实际差或正周期；
            后端和批上限明确；
            conditioned表示外BOOL条件，time_weighted_mean需要既存work_dir。
        返回: 新owner。异常: 配置/预算失败；持续清理故障附record_time_cleanup_owner。
        """
        if not isinstance(budget, ResourceBudget) or not isinstance(spec, CalculationDefinition):
            raise TypeError('记录时间统计需要共享预算和CalculationDefinition')
        if backend not in ('reference', 'numpy') or type(conditioned) is not bool:
            raise ValueError('时间统计需要明确后端及bool条件开关')
        if type(batch_intervals) is not int or not 1 <= batch_intervals <= 4096:
            raise ValueError('记录批上限需要1到4096')
        self._samples=spec.operation in ('sample_minimum','sample_maximum','sample_mean')
        if self._samples:
            if step_ns is not None:raise ValueError('样本统计不使用固定或DBC周期')
            self._unit,self._factor=require_sample_config(spec,input_unit,dtype,partial_limit)
        else:
            self._unit, self._factor = require_time_config(spec, input_unit, dtype, None, partial_limit, step_ns=step_ns)
        self._work_dir = None
        if spec.operation == 'time_weighted_mean':
            if work_dir is None or not Path(work_dir).is_dir():
                raise ValueError('均值需要已存在的专用工作目录')
            self._work_dir = Path(work_dir)
        self._budget, self._spec, self._input_unit, self._dtype = budget, spec, input_unit, dtype
        self._step_ns, self._limit, self._conditioned = step_ns, batch_intervals, conditioned
        self._backend, self._partial_limit = backend, partial_limit
        self._held_cost = self._fixed_cost = self._workspace_cost = 0
        self._closed = self._closing = self._failed = self._finished = False
        self._rows = self._reduction = self._result = self._file = self._mean_sum = None
        self._last_time = None
        self._covered_ns = self._known_ns = self._selected_ns = self._selected_unknown_ns = self._false_ns = 0
        self._quality = Q.NONE
        self._coverage_value_ns=0 if spec.minimum_coverage>0 else None
        self._record_count = 0
        self._codec = Struct('>dq' if step_ns is None else '>dd')  # 仅值/权重，实际纳秒不降为浮点。
        try:
            _reserve_owned_ram(self, 65536 + partial_limit * 512 + (batch_intervals+1)*1024
                + 16*_metadata_bytes((spec, input_unit)), '_fixed_cost')
            self._rows = []
            kernel = ((ReferenceConditionalTimeReduction if backend == 'reference' else NumpyConditionalTimeReduction)
                      if conditioned else (ReferenceTimeReduction if backend == 'reference' else NumpyTimeReduction))
            self._reduction = ((ReferenceSampleReduction if backend=='reference' else NumpySampleReduction)
                (spec,input_unit,dtype,partial_limit=partial_limit) if self._samples else
                kernel(spec, input_unit, dtype, step_ns=step_ns, partial_limit=partial_limit))
        except BaseException as exc:
            _cleanup_owner(self, exc, 'record_time_cleanup_owner', '记录时间统计')
            raise

    def _append_mean(self, values, weights):
        """只写本批选中的必要均值项；费用先预约，不缓存完整输入。

        参数: 已由核校验的有限数值/权重。返回: None。异常: 配额、短写、IO或取消传播。
        """
        if len(values) == 0:
            return
        if self._file is None:
            self._file = TemporaryFile(mode='w+b', buffering=0, dir=self._work_dir, prefix='mean-')
        payload = bytearray(len(values)*self._codec.size)
        view = None
        try:
            for index, (value, weight) in enumerate(zip(values, weights)):
                self._codec.pack_into(payload, index*self._codec.size, float(value),
                    int(weight) if self._step_ns is None else float(weight))
            self._budget.reserve_spool(len(payload))
            view = memoryview(payload)
            position = 0
            while position < len(view):
                written = self._file.write(view[position:])
                if type(written) is not int or not 0 < written <= len(view)-position:
                    raise OSError('均值暂存短写或无写入进展')
                position += written
            self._record_count += len(values)
        finally:
            if view is not None:
                view.release()
            values = weights = payload = view = None

    def _flush(self):
        """在共享预算内分块处理样本统计，保留每块的共同右端。

        参数: 无，使用已预付的点缓冲。返回: None。
        异常: 最小两点工作区也放不下时报告计算项与用途；数值、取消原错传播。
        不降低每行估算、不放宽限额，也不丢弃、重排或重复累计真实样本。
        """
        if not self._samples:
            return self._flush_block()
        remaining = None
        try:
            while len(self._rows) >= 2:
                # 读取队列和其他指标仍存活，不能假定本指标可独占整个预算。
                # 系数沿用原样本核对最多两个TTL插入点的保守预付。
                available = self._budget.memory_budget_bytes - self._budget.ram_bytes
                count = min(len(self._rows), (available - 65536) // 36864)
                if count < 2:
                    raise BudgetExceededError(
                        f'计算项 {self._spec.calculation_id}（{self._spec.operation}）'
                        f'样本统计工作区不足：最小两点需要139264字节，当前可用{available}字节；'
                        '已尝试按可用预算分块，请减少同时运行的计算项或读取批量，'
                        '核实必要状态后再调整memory_budget_bytes')
                if count == len(self._rows):
                    self._flush_block()
                    break
                # 两份短列表的引用槽由既有点缓冲1024字节/行覆盖；不复制值对象。
                # 右端在前块半开范围内不计样本，下一块再作为左端处理一次。
                remaining = self._rows[count - 1:]
                self._rows = self._rows[:count]
                self._flush_block()
                self._rows, remaining = remaining, None
        finally:
            # 中途失败不能持有已退款缓冲以外的尾部引用；外层负责标失败并关闭。
            remaining = None

    def _flush_block(self):
        """计算完整记录对，只留共享右端；均值写选中项，其他指标不写盘。

        参数: 无。返回: None。异常: 预算/数值结构/IO/取消，失败后不得交付前缀。
        """
        if len(self._rows) < 2:
            return
        series = block = facts = None
        primary = None
        try:
            _reserve_owned_ram(self, 65536 + len(self._rows)*(36864 if self._samples else 12288), '_workspace_cost')
            times = tuple(row[0] for row in self._rows)
            values = tuple(row[1] for row in self._rows)
            deadlines = tuple(row[2] for row in self._rows) if any(row[2] is not None for row in self._rows) else None
            conditions = tuple(row[3] for row in self._rows) if self._conditioned else None
            options = {'condition_valid_until_ns': tuple(row[4] for row in self._rows)} if self._conditioned else {}
            series = (sample_series(self._rows,self._input_unit,self._conditioned) if self._samples else
                CalculationSeries(Interval(times[0], times[-1]), times, values, (True,)*len(times), self._input_unit, conditions=conditions))
            mean = self._spec.operation == 'time_weighted_mean'
            block = (self._reduction.push(series) if self._samples else
                self._reduction.push(series, valid_until_ns=deadlines,
                    retain_unknown_ranges=False, retain_mean_terms=mean, **options))
            facts = block.facts if mean else block
            if self._coverage_value_ns is not None:
                self._coverage_value_ns+=facts.value_valid_duration_ns
            if mean:
                self._append_mean(block.values, block.weights)
            span = 0 if facts.actual_window is None else facts.actual_window.end_ns-facts.actual_window.start_ns
            self._covered_ns += span
            self._known_ns += facts.condition_known_duration_ns if self._conditioned else span
            self._selected_ns += facts.selected_duration_ns
            self._selected_unknown_ns += facts.selected_value_unknown_duration_ns if self._conditioned else span-facts.value_valid_duration_ns
            if self._conditioned:
                self._false_ns += facts.false_duration_ns
            self._quality |= facts.quality
            self._rows[:] = self._rows[-1:]
        except BaseException as exc:
            primary, self._failed = exc, True
            raise
        finally:
            series = block = facts = times = values = deadlines = conditions = options = None
            try:
                _release_owned_ram(self, self._workspace_cost, '_workspace_cost')
            except BaseException as cleanup:
                self._failed = True
                if primary is None:
                    raise
                primary.add_note('时间统计临时费用释放失败：'+type(cleanup).__name__)

    def _finish_mean(self):
        """分批回读必要数值/权重，复用原归一化及原序求和，最终只换单位一次。

        参数: 无。返回: TimeReductionResult。异常: 临时数据短缺/多出、IO、预算或取消。
        """
        if self._record_count == 0:
            return TimeReductionResult(None, self._unit, False, Q.NONE, 0)
        denominator = (self._reduction.selected_duration_ns if self._step_ns is None
                       else self._reduction.selected_weight_seconds)
        self._file.seek(0)
        self._mean_sum = (ReferenceIntegralSum if self._backend == 'reference' else NumpyIntegralSum)(self._partial_limit)
        remaining, quality = self._record_count, Q.NONE
        payload = pairs = values = weights = terms = keep = None
        try:
            while remaining:
                count = min(remaining, self._limit)
                payload = self._file.read(count*self._codec.size)
                if len(payload) != count*self._codec.size:
                    raise ValueError('均值必要暂存数据不完整')
                if self._backend == 'reference':
                    pairs = tuple(self._codec.iter_unpack(payload))
                    values, weights = tuple(item[0] for item in pairs), tuple(item[1] for item in pairs)
                    terms, failure = reference_mean(values, weights, denominator)
                    keep = (True,)*len(terms)
                else:
                    pairs = np.frombuffer(payload, dtype=[('value', '>f8'),
                        ('weight', '>i8' if self._step_ns is None else '>f8')])
                    values, weights = pairs['value'], pairs['weight']
                    terms, failure = numpy_mean(values, weights, denominator)
                    keep = np.ones(len(terms), dtype=bool)
                    keep.setflags(write=False)
                quality |= failure
                if quality == Q.NONE:
                    self._mean_sum.push_values(terms, keep)
                remaining -= count
            if self._file.read(1):
                raise ValueError('均值必要暂存含未登记数据')
            if quality != Q.NONE:
                return TimeReductionResult(None, self._unit, True, quality, self._record_count)
            number = self._mean_sum.finish(self._unit, self._factor)
            return TimeReductionResult(number.value, number.unit, number.calculation_failed, number.quality, self._record_count)
        finally:
            payload = pairs = values = weights = terms = keep = None

    def finish(self):
        """上游确认EOF后结算，并关闭删除均值临时文件，再交付精简结果。

        参数: 无。返回: RecordTimeResult，重复调用同一结果。异常: 失败拒绝前缀，close可重试。
        """
        self._require_open()
        if self._finished:
            return self._result
        primary = None
        try:
            self._flush()
            workspace = 65536 + (self._limit+1)*12288 if self._spec.operation == 'time_weighted_mean' else 4096
            _reserve_owned_ram(self, workspace, '_workspace_cost')
            number = self._finish_mean() if self._spec.operation == 'time_weighted_mean' else self._reduction.finish()
            value, status, reason = classify_calculation_value(self._spec, number.value, self._covered_ns,
                self._known_ns, self._selected_ns, self._selected_unknown_ns,
                all_false=self._conditioned and self._covered_ns>0 and self._false_ns==self._covered_ns,
                calculation_failed=number.calculation_failed)
            if self._file is not None:
                self._file.close()
                self._file = None
            coverage=None if self._coverage_value_ns is None else classify_coverage(
                self._spec,self._covered_ns,self._coverage_value_ns,self._known_ns)
            self._result = RecordTimeResult(value, self._unit, status, reason, self._quality | number.quality,coverage)
            self._finished = True
            return self._result
        except BaseException as exc:
            primary, self._failed = exc, True
            raise
        finally:
            number = None
            try:
                _release_owned_ram(self, self._workspace_cost, '_workspace_cost')
            except BaseException as cleanup:
                self._failed = True
                if primary is None:
                    raise
                primary.add_note('时间统计结算费用释放失败：'+type(cleanup).__name__)

    @property
    def closed(self):
        """读取自有文件/费用是否全部释放。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    def close(self):
        """清理自有数值状态和临时文件，释放失败保留重试入口，不碰输入文件。

        参数: 无。返回: None。异常: 文件关闭/费用释放失败可重试；重复关闭安全。
        """
        if self._closed:
            return
        self._closing = True
        self._rows = self._reduction = self._mean_sum = self._result = None
        if self._file is not None:
            self._file.close()
            self._file = None
        _release_owned_ram(self, self._workspace_cost, '_workspace_cost')
        _release_owned_ram(self, self._fixed_cost, '_fixed_cost')
        self._closed = True
