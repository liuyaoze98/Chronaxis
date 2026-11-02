# chronaxis.core

集中导出信号分析的模型、消息表达式绑定和标准库参考实现。

调用者可从本入口构造来源、会话与绑定，再执行信号保持、数值转换、受限表达式、
持续条件、边沿事件及指标计算。参考指标包含前值保持积分、样本/时间统计与BOOL时长；
选择行迭代器保留真实更新、UNKNOWN诊断与原类型。内存桥接连接原行、表达式与输出。
窗口入口扩展、合并和裁剪已完成事件，保存原活动关联；start_only固定窗口抑制跨批保持。
顺序核心将已有请求/响应事件配对，区分明确未响应与观测不足，跨批保存等待状态。
消息表达式另用实际记录仓绑定，参数不参与普通保持或TTL。
此文件只重导出实际模块，
不启动分析、不读取文件、不加载CAN组件或NumPy，也不保存全局会话状态。
数组实现须显式导入对应NumPy模块；完整产品配置和执行接口属于上层入口。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AtomicUpdateBuffer](chronaxis.core.state.md#api-AtomicUpdateBuffer)、[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)、[CalculationResult](chronaxis.core.calculations.md#api-CalculationResult)、[CalculationSeries](chronaxis.core.calculations.md#api-CalculationSeries)、[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)、[ConditionSpan](chronaxis.core.temporal.md#api-ConditionSpan)、[ConditionTick](chronaxis.core.temporal.md#api-ConditionTick)、[ConditionTimeline](chronaxis.core.temporal.md#api-ConditionTimeline)、[DatasetSpec](chronaxis.core.models.md#api-DatasetSpec)、[DeltaSpan](chronaxis.core.window_delta.md#api-DeltaSpan)、[DerivedDefinition](chronaxis.core.expression.md#api-DerivedDefinition)、[Evaluation](chronaxis.core.expression_reference.md#api-Evaluation)、[Event](chronaxis.core.temporal.md#api-Event)、[ExpressionParameter](chronaxis.core.message_binding.md#api-ExpressionParameter)、[Interval](chronaxis.core.models.md#api-Interval)、[MemoryRow](chronaxis.core.models.md#api-MemoryRow)、[MessageBindings](chronaxis.core.message_binding.md#api-MessageBindings)、[MessageDeclarations](chronaxis.core.message_binding.md#api-MessageDeclarations)、[MessageSourceEvidence](chronaxis.core.message_binding.md#api-MessageSourceEvidence)、[QualityFlag](chronaxis.core.types.md#api-QualityFlag)、[ReferenceTemporalDetector](chronaxis.core.temporal_reference.md#api-ReferenceTemporalDetector)、[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)、[Segment](chronaxis.core.windows.md#api-Segment)、[SelectionRow](chronaxis.core.selection.md#api-SelectionRow)、[SequenceDetector](chronaxis.core.sequence_reference.md#api-SequenceDetector)、[SequenceResult](chronaxis.core.sequence.md#api-SequenceResult)、[SequenceRule](chronaxis.core.sequence.md#api-SequenceRule)、[SequenceTick](chronaxis.core.sequence.md#api-SequenceTick)、[SessionSpec](chronaxis.core.models.md#api-SessionSpec)、[SignalBindings](chronaxis.core.binding.md#api-SignalBindings)、[SignalDType](chronaxis.core.types.md#api-SignalDType)、[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)、[SignalSample](chronaxis.core.models.md#api-SignalSample)、[SignalSeries](chronaxis.core.state.md#api-SignalSeries)、[SourceRef](chronaxis.core.models.md#api-SourceRef)、[SourceSpec](chronaxis.core.models.md#api-SourceSpec)、[SourceType](chronaxis.core.types.md#api-SourceType)、[StabilityDetector](chronaxis.core.stability.md#api-StabilityDetector)、[StabilitySpec](chronaxis.core.stability.md#api-StabilitySpec)、[StartEndDetector](chronaxis.core.start_end.md#api-StartEndDetector)、[StartEndSpec](chronaxis.core.start_end.md#api-StartEndSpec)、[StateValue](chronaxis.core.state.md#api-StateValue)、[StaticExpression](chronaxis.core.expression.md#api-StaticExpression)、[SynchronizationEvidence](chronaxis.core.binding.md#api-SynchronizationEvidence)、[TemporalRule](chronaxis.core.temporal.md#api-TemporalRule)、[TimeGroup](chronaxis.core.state.md#api-TimeGroup)、[TimeType](chronaxis.core.types.md#api-TimeType)、[TimebaseSpec](chronaxis.core.models.md#api-TimebaseSpec)、[Truth](chronaxis.core.types.md#api-Truth)、[WindowDeltaResult](chronaxis.core.window_delta.md#api-WindowDeltaResult)、[WindowDeltaSpec](chronaxis.core.window_delta.md#api-WindowDeltaSpec)、[WindowSpec](chronaxis.core.windows.md#api-WindowSpec)

## 对象导航

|对象|用途|
|---|---|

## 导出名称

`DatasetSpec`, `Interval`, `MemoryRow`, `SessionSpec`, `SignalSample`, `SourceRef`, `SourceSpec`, `TimebaseSpec`, `QualityFlag`, `SignalDType`, `SourceType`, `TimeType`, `Truth`, `SignalBindings`, `SignalDefinition`, `SynchronizationEvidence`, `SignalSeries`, `StateValue`, `TimeGroup`, `AtomicUpdateBuffer`, `align_reference`, `common_timeline`, `iter_time_groups`, `ScalarValue`, `binary_reference`, `memory_series_reference`, `normalize_reference`, `to_float_reference`, `unary_reference`, `CompiledExpression`, `DerivedDefinition`, `compile_expression`, `Evaluation`, `evaluate_reference`, `evaluate_memory_reference`, `ConditionSpan`, `ConditionTick`, `ConditionTimeline`, `Event`, `TemporalRule`, `timeline_from_spans`, `ReferenceTemporalDetector`, `detect_reference`, `build_timeline_reference`, `detect_memory_reference`, `CalculationResult`, `CalculationSeries`, `CalculationDefinition`, `compute_reference`, `build_calculation_series_reference`, `compute_memory_reference`, `SelectionRow`, `select_reference`, `select_memory_reference`, `WindowSpec`, `Segment`, `build_segments_reference`, `ExpressionParameter`, `MessageDeclarations`, `MessageSourceEvidence`, `MessageBindings`, `StaticExpression`, `validate_expression`, `SequenceRule`, `SequenceTick`, `SequenceResult`, `SequenceDetector`, `pair_sequence`, `DeltaSpan`, `WindowDeltaSpec`, `WindowDeltaResult`, `window_delta_reference`, `StabilitySpec`, `StabilityDetector`, `StartEndSpec`, `StartEndDetector`

重导出保持定义位置的签名；按上级[总索引](index.md)查找对象名。

公开重导出按[公开API索引](../api.md)查询定义、用途和调用示例。

<details><summary>导入与重导出来源（展开）</summary>

```python
from .models import DatasetSpec, Interval, MemoryRow, SessionSpec, SignalSample, SourceRef, SourceSpec, TimebaseSpec
from .binding import SignalBindings, SignalDefinition, SynchronizationEvidence
from .message_binding import ExpressionParameter, MessageDeclarations, MessageSourceEvidence, MessageBindings
from .state import AtomicUpdateBuffer, SignalSeries, StateValue, TimeGroup, align_reference, common_timeline, iter_time_groups
from .types import QualityFlag, SignalDType, SourceType, TimeType, Truth
from .numeric import ScalarValue, binary_reference, memory_series_reference, normalize_reference, to_float_reference, unary_reference
from .expression import CompiledExpression, StaticExpression, DerivedDefinition, compile_expression, validate_expression
from .expression_reference import Evaluation, evaluate_memory_reference, evaluate_reference
from .temporal import ConditionSpan, ConditionTick, ConditionTimeline, Event, TemporalRule, timeline_from_spans
from .temporal_reference import ReferenceTemporalDetector, detect_reference
from .temporal_memory_reference import build_timeline_reference, detect_memory_reference
from .calculations import CalculationResult, CalculationSeries, CalculationDefinition
from .calculations_reference import compute_reference, select_reference
from .calculations_memory_reference import build_calculation_series_reference, compute_memory_reference, select_memory_reference
from .selection import SelectionRow
from .windows import WindowSpec, Segment
from .windows_reference import build_segments_reference
from .sequence import SequenceRule, SequenceTick, SequenceResult
from .sequence_reference import SequenceDetector, pair_sequence
from .window_delta import DeltaSpan, WindowDeltaSpec, WindowDeltaResult
from .window_delta_reference import window_delta_reference
from .stability import StabilitySpec, StabilityDetector
from .start_end import StartEndSpec, StartEndDetector
```

</details>
