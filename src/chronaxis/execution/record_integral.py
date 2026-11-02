"""在有限内存内累计已求值的驱动记录对，保留实际端点直到比例裁剪完成。

输入为已归一化并按驱动同刻政策归组的(time_ns, ScalarValue[, valid_until_ns])有限批；输出仅含
积分值、单位、完成状态和质量的内部结果。复用原两后端面积及原序误差求和，
一次只持当前批和一条跨批前值，不创建历史文件、原帧副本、贡献或未知范围列表。
调用方负责绑定/表达式/有效期判定，并在输入确实结束后调用finish；本组件不
读取文件或证明来源EOF。实际间隔使用必要更新间的真实差，固定/DBC使用
所选驱动记录对；有效期都按实际截止裁剪，没有完整记录对时不虚构尾段。
"""

from dataclasses import dataclass

from ..core.integral_sum import require_partial_limit
from ..core.integral_sum_reference import ReferenceIntegralSum
from ..core.integral_sum_numpy import NumpyIntegralSum
from ..core.integral_terms_reference import compute_integral_terms_reference
from ..core.integral_terms_numpy import compute_integral_terms_numpy
from ..core.conditional_integral_terms_reference import compute_conditional_integral_terms_reference
from ..core.conditional_integral_terms_numpy import compute_conditional_integral_terms_numpy
from ..core.calculations import CalculationDefinition, CalculationSeries, calculation_unit, classify_calculation_value
from ..core.calculations import classify_coverage
from ..core.models import Interval
from ..core.numeric import ScalarValue
from ..core.record_intervals import require_record_step
from ..core.types import SignalDType as D, QualityFlag as Q
from ..results.budget import ResourceBudget, _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..results.errors import ResultClosedError
from .record_point_buffer import RecordPointBuffer
from .history import _metadata_bytes


@dataclass(frozen=True)
class RecordIntegralResult:
    """内部积分结果，不附逐条输入、时间对照或默认贡献记录；不充当公开发布清单。"""

    value: float | None  # 已换到请求单位；未知与有效零分开。
    unit: str  # 输出单位，仅最终转换一次。
    status: str  # 沿既有complete/partial/indeterminate政策。
    reason: str  # 正常、观测不足或数值失败等必要原因。
    quality: Q  # 输入和数值计算质量，不包含逐条副本。
    coverage_status: str | None = None


class RecordIntegral(RecordPointBuffer):
    """拥有有限驱动点缓冲和累计状态；失败后只能关闭，完成后只读结果。

    consume借用外部有限批；留下的点只含整数时间和冻结数值，费用归本实例。
    同刻冲突须由上游既有同刻政策解决，不能在此任意覆盖或累计零跨度记录。
    """

    def __init__(self, budget, spec, input_unit, dtype, step_ns, *, backend='numpy',
                 batch_intervals=64, partial_limit=4096, conditioned=False):
        """预付有界状态及点缓冲，数值临时数组在每次归约前另预约。

        参数: budget共享账本，spec为integral请求；input_unit/dtype为已
            求值列单位/类型；step_ns为None（实际差）或固定/已核实DBC正周期；后端独立选择；
            batch_intervals为1—4096区间数，partial_limit为误差项容量；conditioned指定显式BOOL条件。
        返回: 新owner。异常: 配置/预算/取消错误；构造清理失败通过异常的
            record_integral_cleanup_owner提供重试入口。
        """
        if not isinstance(budget, ResourceBudget) or not isinstance(spec, CalculationDefinition):
            raise TypeError('记录流积分需要共享预算和CalculationDefinition')
        if spec.operation != 'integral':
            raise ValueError('记录流积分需要integral')
        if backend not in ('reference', 'numpy') or dtype not in (D.INT64, D.UINT64, D.FLOAT64):
            raise ValueError('记录流积分需要明确后端和数值dtype')
        if type(batch_intervals) is not int or not 1 <= batch_intervals <= 4096:
            raise ValueError('记录流区间批上限需要1到4096')
        if type(conditioned) is not bool:
            raise TypeError('条件选择需要bool')
        require_record_step(step_ns, ())
        limit = require_partial_limit(partial_limit)
        self._unit, self._factor = calculation_unit(spec, input_unit)
        self._budget, self._spec, self._input_unit, self._dtype = budget, spec, input_unit, dtype
        self._step_ns, self._limit = step_ns, batch_intervals
        self._conditioned = conditioned
        self._held_cost = self._fixed_cost = self._workspace_cost = 0
        self._closed = self._closing = self._failed = self._finished = False
        self._rows = self._sum = self._result = None
        self._last_time = None
        self._covered_ns = 0
        self._known_ns = self._selected_ns = self._selected_unknown_ns = self._false_ns = 0
        self._quality = Q.NONE
        self._coverage_value_ns=0 if spec.minimum_coverage>0 else None
        try:
            # 固定费覆盖误差求和的有限候选及点缓冲，不按总记录数扩大。
            _reserve_owned_ram(self, 65536 + limit * 256 + (batch_intervals + 1) * 1024
                               + 16 * _metadata_bytes((spec, input_unit)), '_fixed_cost')
            self._rows = []
            self._sum = (ReferenceIntegralSum if backend == 'reference' else NumpyIntegralSum)(limit)
            self._compute = compute_integral_terms_reference if backend == 'reference' else compute_integral_terms_numpy
            if conditioned:
                self._compute = (compute_conditional_integral_terms_reference if backend == 'reference'
                                 else compute_conditional_integral_terms_numpy)
        except BaseException as exc:
            _cleanup_owner(self, exc, 'record_integral_cleanup_owner', '记录流积分')
            raise

    def _flush(self):
        """消费当前完整记录对并留下一个共享端点，首条/末条不凭空增加周期。

        参数: 无，使用当前自有缓冲。返回: None。异常: 数值结构/预算/取消；
            清理异常不覆盖原错误，临时申请保留在owner供close重试。
        """
        if len(self._rows) < 2:
            return
        series = terms = None
        primary = None
        try:
            _reserve_owned_ram(self, 65536 + len(self._rows) * 8192, '_workspace_cost')
            times = tuple(item[0] for item in self._rows)
            values = tuple(item[1] for item in self._rows)
            # 截止仅为本批计算所需；不保存来源副本或另一列累计时钟。
            deadlines = (tuple(item[2] for item in self._rows)
                         if any(item[2] is not None for item in self._rows) else None)
            conditions = tuple(item[3] for item in self._rows) if self._conditioned else None
            condition_deadlines = (tuple(item[4] for item in self._rows)
                if self._conditioned and any(item[4] is not None for item in self._rows) else None)
            series = CalculationSeries(Interval(times[0], times[-1]), times, values,
                                  (True,) * len(times), self._input_unit, conditions=conditions)
            # 窗口仍由原spec裁剪，分母保留完整记录对。按请求省去未知范围对象。
            options = {'condition_valid_until_ns': condition_deadlines} if self._conditioned else {}
            terms = self._compute(series, self._spec, step_ns=self._step_ns,
                                  retain_unknown_ranges=False, valid_until_ns=deadlines, **options)
            self._sum.push_values(terms.areas, terms.valid)
            facts = terms.facts
            if self._coverage_value_ns is not None:
                self._coverage_value_ns+=facts.value_valid_duration_ns
            if facts.actual_window is not None:
                span = facts.actual_window.end_ns - facts.actual_window.start_ns
                self._covered_ns += span
                self._known_ns += facts.condition_known_duration_ns if self._conditioned else span
                self._selected_ns += facts.selected_duration_ns if self._conditioned else facts.value_valid_duration_ns
                self._selected_unknown_ns += (facts.selected_value_unknown_duration_ns if self._conditioned
                                              else span - facts.value_valid_duration_ns)
                if self._conditioned:
                    self._false_ns += facts.false_duration_ns
            self._quality |= facts.quality
            self._rows[:] = self._rows[-1:]
        except BaseException as exc:
            primary = exc
            self._failed = True
            raise
        finally:
            # 断开有限临时列后再退款；释放失败不允许调用方取得成功结果。
            series = terms = times = values = facts = deadlines = conditions = condition_deadlines = options = None
            try:
                _release_owned_ram(self, self._workspace_cost, '_workspace_cost')
            except BaseException as cleanup:
                self._failed = True
                if primary is None:
                    raise
                primary.add_note('记录流积分临时费用清理失败：' + type(cleanup).__name__)

    def finish(self):
        """输入调用方确认结束后结算最后完整记录对，返回精简内部结果。

        参数: 无；不能代替读取器EOF/关闭成功的确认。返回: RecordIntegralResult，
            重复调用返回同一结果。异常: 预算/数值结构/取消错误，不发布前缀。
        """
        self._require_open()
        if self._finished:
            return self._result
        try:
            self._flush()
            number = self._sum.finish(self._unit, self._factor)
            value, status, reason = classify_calculation_value(self._spec, number.value, self._covered_ns,
                self._known_ns, self._selected_ns, self._selected_unknown_ns,
                calculation_failed=number.calculation_failed,
                all_false=self._conditioned and self._covered_ns > 0 and self._false_ns == self._covered_ns)
            coverage=None if self._coverage_value_ns is None else classify_coverage(
                self._spec,self._covered_ns,self._coverage_value_ns,self._known_ns)
            self._result = RecordIntegralResult(value, self._unit, status, reason, self._quality | number.quality,coverage)
            self._finished = True
            return self._result
        except BaseException:
            self._failed = True
            raise

    @property
    def closed(self):
        """读取自有费用完全释放状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    def close(self):
        """释放自有缓冲/数值状态及费用，不操作外部输入和目录。

        参数: 无。返回: None；重复关闭安全。异常: 预算释放失败可重试，不假报已关闭。
        """
        if self._closed:
            return
        self._closing = True
        self._rows = self._sum = self._result = None
        _release_owned_ram(self, self._workspace_cost, '_workspace_cost')
        _release_owned_ram(self, self._fixed_cost, '_fixed_cost')
        self._closed = True
