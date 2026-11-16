"""依据整个计划的静态类别选择数值后端，不读取输入或试跑计算。

auto 覆盖已测量的简单积分和已完成对照验证的普通流式类别，后者可包含规则、窗口。
选择依据是当前验证范围，不代表任意表达式与数据的两后端结果均已逐位验证；
其他组合沿用 NumPy，显式选择始终优先。
选择结果供校验、说明和运行共用，不保存逐条执行记录，也不在失败后重试。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.expression import StaticExpression
    from .plan import AnalysisPlan


BACKENDS = ('reference', 'numpy', 'auto')
_SIMPLE = frozenset(('name', 'const', 'add', 'sub', 'mul', 'div', 'neg', 'abs',
                     'unit_convert', 'to_float'))
_RAW = frozenset(('can_blf', 'can_asc', 'asc_or_blf', 'raw_can_csv'))
# 已完成对照验证的流式类别：极值、计数、选择和采用误差补偿求和的面积类统计。
# 此集合用于静态选择，不替代新增表达式、数据边界或算子组合的结果核验。
# 样本均值、方差、标准差和分位数的块内求和方式不同，结果可能差最后几位，继续沿用 NumPy。
_STREAMING_OPERATIONS = frozenset(('integral', 'duration', 'time_weighted_mean', 'min_time', 'max_time',
                              'sample_minimum', 'sample_maximum', 'sample_count', 'point_event_count',
                              'activity_count', 'segment_count', 'select'))
# 已用基准矩阵测量过的计划结构；其余结构（变换、序列、聚合、逐消息计算、宿主扩展）未测，保持 NumPy。
_STREAMING_REASON = '该计划属于已验证的流式类别（支持规则/窗口），采用 reference'


@dataclass(frozen=True)
class BackendSelection:
    """保存一次静态选择：请求值、实际后端及可读原因，不代表已运行。"""

    requested: str  # 原配置或调用覆盖。
    selected: str  # reference/numpy；非法 typed 声明为 unavailable。
    reason: str  # 解释选择依据，不承诺具体提速比例。


def simple_numeric_expression(expression: StaticExpression | None) -> bool:
    """检查首批实测的简单数值表达式。参数: 静态表达式。返回: bool。异常: 非法 typed 结构。

    仅遍历配置树；短路、查表、宿主函数和时序运算留在通用类别。
    """
    if expression is None or not expression.dependencies:
        return False
    from ..core.types import SignalDType
    if expression.root.dtype not in (SignalDType.INT64, SignalDType.UINT64, SignalDType.FLOAT64):
        return False
    pending = [expression.root]
    while pending:
        node = pending.pop()
        if node.operator not in _SIMPLE:
            return False
        pending.extend(node.args)
    return True


def select_backend(plan: AnalysisPlan) -> BackendSelection:
    """为整个计划选择一次后端。参数: AnalysisPlan。返回: BackendSelection。

    异常: 非法 typed 结构的属性错误；未知后端作为 unavailable 交给静态诊断。
    不读取 DBC、日志或路径元数据，不修改原计划、身份或用户配置。
    """
    requested = plan.execution.backend
    if requested in ('reference', 'numpy'):
        return BackendSelection(requested, requested, '使用显式指定的数值后端')
    if requested != 'auto':
        return BackendSelection(requested, 'unavailable', '不支持的数值后端')
    conservative = BackendSelection('auto', 'numpy', '该计划不属于已验证的自动选择类别，沿用 NumPy')
    if (plan.extensions is not None or plan.transforms or plan.aggregations or plan.sequences
            or plan.message_calculations or not plan.calculations):
        return conservative
    if plan.rules or plan.windows:
        # 原两类直接积分都不含规则/窗口；这里只按算子集合放宽，不启用直接积分路径。
        return _streaming_selection(plan, conservative)
    choices = dict(plan.intervals.resolved)
    used = set()
    for calculation in plan.calculations:
        if (calculation.operation != 'integral' or calculation.scope != 'session'
                or calculation.method != 'zoh' or calculation.condition is not None
                or not simple_numeric_expression(calculation.signal)
                or calculation.calculation_id not in choices
                or choices[calculation.calculation_id].mode != 'actual'):
            return _streaming_selection(plan, conservative)
        used.update(calculation.signal.dependencies)
    definitions = tuple(item.definition for item in plan.signals if item.definition.name in used)
    if {item.name for item in definitions} != used:
        return _streaming_selection(plan, conservative)
    sources = {item.source for item in definitions}
    if len(sources) != 1:
        return _streaming_selection(plan, conservative)
    source = next((item for item in plan.sources if item.name in sources), None)
    if source is None:
        return _streaming_selection(plan, conservative)
    if source.source_type in _RAW and len(definitions) <= 2:
        from ..sources.can_spec import can_field_from_key
        fields = tuple(can_field_from_key(item.field) for item in definitions)
        if len({(f.channel, f.frame_id, f.is_extended, f.is_fd) for f in fields}) == 1:
            return BackendSelection('auto', 'reference', '同一报文定位的简单实际时间积分采用 reference')
    if source.source_type == 'signal_csv' and len(definitions) == 1:
        return BackendSelection('auto', 'reference', '单信号 CSV 实际时间积分采用 reference')
    return _streaming_selection(plan, conservative)


def _streaming_selection(plan: AnalysisPlan, conservative: BackendSelection) -> BackendSelection:
    """按已验证的算子范围为普通流式计划选择 reference，其余保留 NumPy。

    参数: 已排除扩展/变换/序列/聚合/逐消息计算的计划，及原保守结果。返回: BackendSelection。
    异常: 无；只读静态声明，不读取数据，不启用直接积分路径（该路径仍由原两类条件决定）。
    """
    if all(item.operation in _STREAMING_OPERATIONS for item in plan.calculations):
        return BackendSelection('auto', 'reference', _STREAMING_REASON)
    return conservative


def execution_plan(plan: AnalysisPlan) -> AnalysisPlan:
    """取得实际执行视图。参数: 原计划。返回: 原计划或仅后端变化的视图。

    异常: 未支持后端为 ValueError；不修改 raw_config/identity，不重载来源。
    """
    selected = select_backend(plan)
    if selected.selected == 'unavailable':
        raise ValueError('未支持的执行backend：' + str(selected.requested))
    return plan if selected.selected == plan.execution.backend else replace(
        plan, execution=replace(plan.execution, backend=selected.selected))
