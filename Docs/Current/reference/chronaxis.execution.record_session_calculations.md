# chronaxis.execution.record_session_calculations

在原AnalysisRunner会话内合并所需来源并执行会话时间指标。

共享同一时刻最新状态；每项指标只保自己的驱动点和归约状态。输入只读一次，
不创建普通历史、消息历史或完整贡献。均值仅保其算法必需的值与权重暂存。
每来源只保有界前瞻，同一时刻跨来源更新收齐后求值。所有输入真正EOF并关闭
后才交付最终结果，失败不发布已累计的前缀。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisError](chronaxis.results.errors.md#api-AnalysisError)、[AnalysisOutcome](chronaxis.results.analysis_outcome.md#api-AnalysisOutcome)、[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)、[CurrentMessageCalculation](chronaxis.execution.current_message_calculation.md#api-CurrentMessageCalculation)、[DecodedTimeGroup](chronaxis.execution.groups.md#api-DecodedTimeGroup)、[DriverExpression](chronaxis.execution.driver_expression.md#api-DriverExpression)、[Interval](chronaxis.core.models.md#api-Interval)、[IntervalChoice](chronaxis.planning.intervals.md#api-IntervalChoice)、[LatestSignalState](chronaxis.execution.state.md#api-LatestSignalState)、[LegacySkipReason](chronaxis.legacy.sum.md#api-LegacySkipReason)、[RecordDiagnostics](chronaxis.execution.record_diagnostics.md#api-RecordDiagnostics)、[RecordEventDurations](chronaxis.execution.record_event_durations.md#api-RecordEventDurations)、[RecordExports](chronaxis.execution.record_exports.md#api-RecordExports)、[RecordIntegral](chronaxis.execution.record_integral.md#api-RecordIntegral)、[RecordRuleTimeline](chronaxis.execution.record_rule_timeline.md#api-RecordRuleTimeline)、[RecordScopeCalculations](chronaxis.execution.record_scope_calculations.md#api-RecordScopeCalculations)、[RecordSelection](chronaxis.execution.record_selection.md#api-RecordSelection)、[RecordSequences](chronaxis.execution.record_sequences.md#api-RecordSequences)、[RecordSourceCursor](chronaxis.execution.record_source_cursor.md#api-RecordSourceCursor)、[RecordTimeCalculation](chronaxis.execution.record_time_calculation.md#api-RecordTimeCalculation)、[RecordTimeIndexes](chronaxis.execution.record_time_indexes.md#api-RecordTimeIndexes)、[RecordWindows](chronaxis.execution.record_windows.md#api-RecordWindows)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[SummaryCalculationRow](chronaxis.results.summary.md#api-SummaryCalculationRow)、[SummaryContributionRow](chronaxis.results.summary.md#api-SummaryContributionRow)、[SummaryCoverageCalculationRow](chronaxis.results.summary.md#api-SummaryCoverageCalculationRow)、[SummaryEventRow](chronaxis.results.summary.md#api-SummaryEventRow)、[SummaryInputRow](chronaxis.results.summary.md#api-SummaryInputRow)、[SummarySegmentRow](chronaxis.results.summary.md#api-SummarySegmentRow)、[SummarySelectionRow](chronaxis.results.summary.md#api-SummarySelectionRow)、[SummarySequenceRow](chronaxis.results.summary.md#api-SummarySequenceRow)

## 对象导航

|对象|用途|
|---|---|
|[`RecordSessionCalculations`](#api-RecordSessionCalculations)|拥有实时计算和读取子资源；计划与最终结果仓只借用。|
|[`RecordSessionCalculations.__init__`](#api-RecordSessionCalculations-__init__)|预约有限声明空间，不启动读取。|
|[`RecordSessionCalculations._new`](#api-RecordSessionCalculations-_new)|保留尚未交付的真实子owner。|
|[`RecordSessionCalculations._consume_group`](#api-RecordSessionCalculations-_consume_group)|先原子提交同一时刻组，再分别按所选报文推进各指标。|
|[`RecordSessionCalculations._emit_selection`](#api-RecordSessionCalculations-_emit_selection)|按请求保存一份选择值及状态。|
|[`RecordSessionCalculations._emit_input_trace`](#api-RecordSessionCalculations-_emit_input_trace)|仅按trace请求写最终追溯表。|
|[`RecordSessionCalculations._emit_contribution`](#api-RecordSessionCalculations-_emit_contribution)|仅按请求写计算定位和值/跳过。|
|[`RecordSessionCalculations.execute_into`](#api-RecordSessionCalculations-execute_into)|一次读取并向原结果仓追加已完成指标；不发布文件。|
|[`RecordSessionCalculations._finish_actual_tails`](#api-RecordSessionCalculations-_finish_actual_tails)|以实际来源EOF结算连续计算和样本统计，固定周期不凭空加报文。|
|[`RecordSessionCalculations._consume_constants`](#api-RecordSessionCalculations-_consume_constants)|常量只需真实首末范围，EOF后复用相同统计核，不创建假信号或逐行值。|
|[`RecordSessionCalculations._emit_event`](#api-RecordSessionCalculations-_emit_event)|将必要事件字段直接写一次最终结果仓。|
|[`RecordSessionCalculations._emit_event_duration`](#api-RecordSessionCalculations-_emit_event_duration)|把每段事件指标直接写最终指标表。|
|[`RecordSessionCalculations._emit_segment`](#api-RecordSessionCalculations-_emit_segment)|只写实际片段与父关联，后续指标借用同一片段。|
|[`RecordSessionCalculations._count_outcome`](#api-RecordSessionCalculations-_count_outcome)|随已写出的指标计数。|
|[`RecordSessionCalculations.analysis_outcome`](#api-RecordSessionCalculations-analysis_outcome)|取得同次规则和指标概况。|
|[`RecordSessionCalculations.threshold_summaries`](#api-RecordSessionCalculations-threshold_summaries)|生成明确预设请求的有限汇总，不复制状态轨迹。|
|[`RecordSessionCalculations._emit_sequence`](#api-RecordSessionCalculations-_emit_sequence)|只写最终配对结论，不复制事件全文。|
|[`RecordSessionCalculations._consume_message`](#api-RecordSessionCalculations-_consume_message)|按原序收集有限目标批，供同来源各累计器共用。|
|[`RecordSessionCalculations._flush_messages`](#api-RecordSessionCalculations-_flush_messages)|共享当前目标批完成各汇总计算，不创建历史或逐次输出。|
|[`RecordSessionCalculations._advance_observed_domain`](#api-RecordSessionCalculations-_advance_observed_domain)|用已付费游标的真实首末更新在线范围，不读取更多输入或保存时间序列。|
|[`RecordSessionCalculations._merge_sources`](#api-RecordSessionCalculations-_merge_sources)|每来源只取已付费前瞻，收齐同一时刻更新再求值。|
|[`RecordSessionCalculations._close_slot`](#api-RecordSessionCalculations-_close_slot)|关闭成功才解除责任。|
|[`RecordSessionCalculations._require_closed`](#api-RecordSessionCalculations-_require_closed)|核实子资源真实关闭再撤槽。|
|[`RecordSessionCalculations.close`](#api-RecordSessionCalculations-close)|反向释放自有资源，保留失败槽供父会话重试。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import replace
from ..core.models import Interval
from functools import partial
from ..core.calculations import CalculationDefinition
from ..legacy.records import field_to_dict
from ..results.errors import ResultClosedError, AnalysisError
from ..results.spool import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..results.summary import SummaryCalculationRow
from ..results.summary import SummaryCoverageCalculationRow
from ..results.summary import SummaryEventRow
from ..results.summary import SummarySequenceRow
from ..sources.can_spec import can_field_from_key
from .history import _metadata_bytes
from .state import LatestSignalState
from .driver_expression import DriverExpression
from .record_integral import RecordIntegral
from .record_time_calculation import RecordTimeCalculation
from .record_source_cursor import RecordSourceCursor
from .groups import DecodedTimeGroup
from .current_message_calculation import CurrentMessageCalculation
from ..legacy.sum import LegacySkipReason
from .record_rule_timeline import RecordRuleTimeline
from .record_sequences import RecordSequences
from ..planning.intervals import IntervalChoice
from .record_event_durations import RecordEventDurations, is_event_duration
from .record_scope_calculations import RecordScopeCalculations
from .record_time_indexes import RecordTimeIndexes
from .record_windows import RecordWindows
from .record_exports import RecordExports
from ..results.summary import SummarySegmentRow
from ..results.summary import SummaryContributionRow
from ..results.summary import SummaryInputRow
from .record_diagnostics import RecordDiagnostics
from .record_selection import RecordSelection
from ..results.summary import SummarySelectionRow
```

</details>

<a id="api-RecordSessionCalculations"></a>
## `RecordSessionCalculations`

拥有实时计算和读取子资源；计划与最终结果仓只借用。

```python
RecordSessionCalculations(plan, budget, work_dir, *, requirements=None)
```


源码：[`src/chronaxis/execution/record_session_calculations.py:46`](../../../src/chronaxis/execution/record_session_calculations.py#L46)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordSessionCalculations-__init__"></a>
### `RecordSessionCalculations.__init__`

预约有限声明空间，不启动读取。

```python
RecordSessionCalculations.__init__(plan, budget, work_dir, *, requirements=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|AnalysisPlan|是|无|位置或关键字。已完成静态解析的分析计划，包含来源、绑定、规则、指标、间隔选择和输出要求。|
|`budget`|ResourceBudget|是|无|位置或关键字。本次分析共享的资源用量记录；新对象先预约所需内存和磁盘额度，关闭时归还自己的内存费用。|
|`work_dir`|str &#124; Path &#124; None|是|无|位置或关键字。本次专用工作目录，用于确实需要的临时资源；不得使用原始输入或RefProjects。是否可省略由本表签名默认值明确给出。|
|`requirements`|InputRequirements &#124; SourceInputRequirements|否|None|仅关键字。需求分析所得的当前任务或单来源输入范围，用来跳过没有消费者的值、时间和历史。|

#### 返回说明

新owner。

#### 异常说明

构造原错附record_session_cleanup_owner供父会话接管。

源码：[`src/chronaxis/execution/record_session_calculations.py:49`](../../../src/chronaxis/execution/record_session_calculations.py#L49)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordSessionCalculations-_new"></a>
### `RecordSessionCalculations._new`

保留尚未交付的真实子owner。

```python
RecordSessionCalculations._new(factory, recovery, *args, **kwargs)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`factory`|Callable|是|无|位置或关键字。要调用的资源构造器；失败时按recovery取回真实拥有者，不吞掉原始异常。|
|`recovery`|str|是|无|位置或关键字。构造异常上用于取回未返回资源拥有者的属性名，确保失败后仍能关闭和退款。|
|`args`|tuple|否|()|可变位置。传给factory的位置参数，保持原有参数顺序。|
|`kwargs`|dict|否|{}|可变关键字。传给factory的关键字参数，保持原有名称与值。|

#### 返回说明

owner。

#### 异常说明

原错。

源码：[`src/chronaxis/execution/record_session_calculations.py:95`](../../../src/chronaxis/execution/record_session_calculations.py#L95)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordSessionCalculations-_consume_group"></a>
### `RecordSessionCalculations._consume_group`

先原子提交同一时刻组，再分别按所选报文推进各指标。

```python
RecordSessionCalculations._consume_group(group)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`group`|[DecodedTimeGroup](chronaxis.execution.groups.md#api-DecodedTimeGroup)|是|无|位置或关键字。同一实际时刻收齐的所需信号更新；本组全部到齐后再求值，避免来源遍历顺序影响结果。|

#### 返回说明

None。

#### 异常说明

表达式/预算/累计原错。
非驱动无效更新仅截断待算值，不新增周期；条件截止独立处理。

源码：[`src/chronaxis/execution/record_session_calculations.py:103`](../../../src/chronaxis/execution/record_session_calculations.py#L103)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordSessionCalculations-_emit_selection"></a>
### `RecordSessionCalculations._emit_selection`

按请求保存一份选择值及状态。

```python
RecordSessionCalculations._emit_selection(request, parent, row)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`request`|CalculationPlan|是|无|位置或关键字。当前指标请求，包含ID、统计范围、算子、表达式和缺失处理政策。|
|`parent`|str &#124; None|是|无|位置或关键字。当前结果关联的事件或片段ID；会话级结果使用None。|
|`row`|SelectionRow|是|无|位置或关键字。样本选择内核给出的一条结果，保留实际时间、业务值和真/未知选择状态。|

#### 返回说明

None。

#### 异常说明

暂存错误。

源码：[`src/chronaxis/execution/record_session_calculations.py:169`](../../../src/chronaxis/execution/record_session_calculations.py#L169)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordSessionCalculations-_emit_input_trace"></a>
### `RecordSessionCalculations._emit_input_trace`

仅按trace请求写最终追溯表。

```python
RecordSessionCalculations._emit_input_trace(source, sequence, time_ns, record_type, locator, values, quality)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|str|是|无|位置或关键字。当前结果或记录所属的来源名称，必须对应计划中已经定义的source。|
|`sequence`|int|是|无|位置或关键字。当前记录的非负顺序号；同一时刻记录仍有独立序号，不能当作时间戳。|
|`time_ns`|int &#124; None|是|无|位置或关键字。当前记录的实际纳秒时刻；仅明确不需要采集时间的输入诊断可为None。|
|`record_type`|str|是|无|位置或关键字。输入记录种类：decoded_message表示所需报文解码值，signal_sample表示普通信号值，signal_clock表示只保留更新时间的记录。|
|`locator`|str|是|无|位置或关键字。当前报文或字段的非空定位文本，配合来源和原记录序号定位所需输入。|
|`values`|str|是|无|位置或关键字。已经规范化的所需输入值JSON文本；直接写最终追溯行，不再重复编码整份输入。|
|`quality`|QualityFlag|是|无|位置或关键字。该值或结果的质量位组合；缺失、过期等原因不能通过清零掩盖。|

#### 返回说明

None。

#### 异常说明

暂存错误。

源码：[`src/chronaxis/execution/record_session_calculations.py:178`](../../../src/chronaxis/execution/record_session_calculations.py#L178)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordSessionCalculations-_emit_contribution"></a>
### `RecordSessionCalculations._emit_contribution`

仅按请求写计算定位和值/跳过。

```python
RecordSessionCalculations._emit_contribution(request, contribution, quality)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`request`|MessageCalculationPlan|是|无|位置或关键字。产生该贡献的逐消息指标声明，提供结果身份、单位和分桶政策。|
|`contribution`|LegacySumContribution|是|无|位置或关键字。一次分别用每条消息中的值计算表达式或跳过的结果，不附完整原帧和原值副本。|
|`quality`|QualityFlag|是|无|位置或关键字。本次贡献的质量位，写入对应结果行；不能因结果值存在而清除已观察到的质量问题。|

#### 返回说明

None。

#### 异常说明

暂存原错。

源码：[`src/chronaxis/execution/record_session_calculations.py:185`](../../../src/chronaxis/execution/record_session_calculations.py#L185)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordSessionCalculations-execute_into"></a>
### `RecordSessionCalculations.execute_into`

一次读取并向原结果仓追加已完成指标；不发布文件。

```python
RecordSessionCalculations.execute_into(spool)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spool`|ResultSpool|是|无|位置或关键字。接收或读取本次最终结果的有界暂存；不重新读取原始日志。|

#### 返回说明

None。

#### 异常说明

任一输入/计算失败附真实恢复owner。
只构造所需字段；独立驱动仅传帧定位，DBC周期在首帧前取得一次。

源码：[`src/chronaxis/execution/record_session_calculations.py:195`](../../../src/chronaxis/execution/record_session_calculations.py#L195)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordSessionCalculations-_finish_actual_tails"></a>
### `RecordSessionCalculations._finish_actual_tails`

以实际来源EOF结算连续计算和样本统计，固定周期不凭空加报文。

```python
RecordSessionCalculations._finish_actual_tails()
```

参数：无显式参数。


#### 参数说明

无，读取已耗尽游标、最新状态及尚待结算的末点。

#### 返回说明

None。

#### 异常说明

表达式、预算或累计错误原样传播。
不新增样本、贡献或追溯；观察结束和TTL都来自真实输入，domain仅负责裁剪。

源码：[`src/chronaxis/execution/record_session_calculations.py:418`](../../../src/chronaxis/execution/record_session_calculations.py#L418)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordSessionCalculations-_consume_constants"></a>
### `RecordSessionCalculations._consume_constants`

常量只需真实首末范围，EOF后复用相同统计核，不创建假信号或逐行值。

```python
RecordSessionCalculations._consume_constants()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

求值/预算/计算原错；无观测不喂任何点。

源码：[`src/chronaxis/execution/record_session_calculations.py:457`](../../../src/chronaxis/execution/record_session_calculations.py#L457)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordSessionCalculations-_emit_event"></a>
### `RecordSessionCalculations._emit_event`

将必要事件字段直接写一次最终结果仓。

```python
RecordSessionCalculations._emit_event(event)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`event`|Event|是|无|位置或关键字。本次规则产生的活动或点事件；保留实际开始、确认、结束和状态。|

#### 返回说明

None。

#### 异常说明

原写入错。

源码：[`src/chronaxis/execution/record_session_calculations.py:478`](../../../src/chronaxis/execution/record_session_calculations.py#L478)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordSessionCalculations-_emit_event_duration"></a>
### `RecordSessionCalculations._emit_event_duration`

把每段事件指标直接写最终指标表。

```python
RecordSessionCalculations._emit_event_duration(request, event_id, result)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`request`|CalculationPlan|是|无|位置或关键字。当前指标请求，包含ID、统计范围、算子、表达式和缺失处理政策。|
|`event_id`|str|是|无|位置或关键字。本次事件的稳定id，用于指标、窗口及配对结果引用。|
|`result`|RecordTimeResult|是|无|位置或关键字。事件时长计算的数值、单位、质量及完整/部分/未知状态。|

#### 返回说明

None。

#### 异常说明

原发布错。

源码：[`src/chronaxis/execution/record_session_calculations.py:493`](../../../src/chronaxis/execution/record_session_calculations.py#L493)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordSessionCalculations-_emit_segment"></a>
### `RecordSessionCalculations._emit_segment`

只写实际片段与父关联，后续指标借用同一片段。

```python
RecordSessionCalculations._emit_segment(segment)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`segment`|CompactSegment|是|无|位置或关键字。已确定的实际窗口片段，包含业务范围及父事件关联，供计算或导出使用。|

#### 返回说明

None。

#### 异常说明

原发布/计算错。

源码：[`src/chronaxis/execution/record_session_calculations.py:504`](../../../src/chronaxis/execution/record_session_calculations.py#L504)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordSessionCalculations-_count_outcome"></a>
### `RecordSessionCalculations._count_outcome`

随已写出的指标计数。

```python
RecordSessionCalculations._count_outcome(status, reason)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`status`|str|是|无|位置或关键字。已经写出的计算行状态，限complete、partial或indeterminate；对应概况计数加1。|
|`reason`|str &#124; None|是|无|位置或关键字。该计算行的实际原因；no_observation或no_evaluations额外计入无观测行数，其余原因不增加该项。|

#### 返回说明

None。

#### 异常说明

未支持的内部状态。

源码：[`src/chronaxis/execution/record_session_calculations.py:518`](../../../src/chronaxis/execution/record_session_calculations.py#L518)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordSessionCalculations-analysis_outcome"></a>
### `RecordSessionCalculations.analysis_outcome`

取得同次规则和指标概况。

```python
RecordSessionCalculations.analysis_outcome()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

AnalysisOutcome。

#### 异常说明

规则未完成。

源码：[`src/chronaxis/execution/record_session_calculations.py:524`](../../../src/chronaxis/execution/record_session_calculations.py#L524)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordSessionCalculations-threshold_summaries"></a>
### `RecordSessionCalculations.threshold_summaries`

生成明确预设请求的有限汇总，不复制状态轨迹。

```python
RecordSessionCalculations.threshold_summaries()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

tuple。

#### 异常说明

未完成统计错误。

源码：[`src/chronaxis/execution/record_session_calculations.py:529`](../../../src/chronaxis/execution/record_session_calculations.py#L529)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordSessionCalculations-_emit_sequence"></a>
### `RecordSessionCalculations._emit_sequence`

只写最终配对结论，不复制事件全文。

```python
RecordSessionCalculations._emit_sequence(result)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`result`|SequenceResult|是|无|位置或关键字。一次请求的配对或超时判定，关联原事件并保留所选计时依据下的延迟。|

#### 返回说明

None。

#### 异常说明

原写入错。

源码：[`src/chronaxis/execution/record_session_calculations.py:542`](../../../src/chronaxis/execution/record_session_calculations.py#L542)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordSessionCalculations-_consume_message"></a>
### `RecordSessionCalculations._consume_message`

按原序收集有限目标批，供同来源各累计器共用。

```python
RecordSessionCalculations._consume_message(update)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`update`|LegacyDecodedUpdate|是|无|位置或关键字。当前一条所需报文更新，保留原输入序号、所需字段和有效状态；同一时刻不同报文仍分别处理。|

#### 返回说明

None。

#### 异常说明

预算、计算或取消原错；完整明细仍逐消息交付。

源码：[`src/chronaxis/execution/record_session_calculations.py:554`](../../../src/chronaxis/execution/record_session_calculations.py#L554)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordSessionCalculations-_flush_messages"></a>
### `RecordSessionCalculations._flush_messages`

共享当前目标批完成各汇总计算，不创建历史或逐次输出。

```python
RecordSessionCalculations._flush_messages()
```

参数：无显式参数。


#### 参数说明

无，使用已付费的有限消息缓冲。

#### 返回说明

None。

#### 异常说明

原计算/取消错误优先；清理失败保留费用，供close重试。

源码：[`src/chronaxis/execution/record_session_calculations.py:595`](../../../src/chronaxis/execution/record_session_calculations.py#L595)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordSessionCalculations-_advance_observed_domain"></a>
### `RecordSessionCalculations._advance_observed_domain`

用已付费游标的真实首末更新在线范围，不读取更多输入或保存时间序列。

```python
RecordSessionCalculations._advance_observed_domain()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。显式范围保持原裁剪规则；省略范围只保一个当前并集。

#### 异常说明

非法时间或已封闭检测器的推进错误沿原清理路径传播。

源码：[`src/chronaxis/execution/record_session_calculations.py:623`](../../../src/chronaxis/execution/record_session_calculations.py#L623)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordSessionCalculations-_merge_sources"></a>
### `RecordSessionCalculations._merge_sources`

每来源只取已付费前瞻，收齐同一时刻更新再求值。

```python
RecordSessionCalculations._merge_sources()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None，所有实际来源EOF才返回。

#### 异常说明

原读取/计算/预算错误。
不按文件顺序拼接不同来源，不为跨源合并建磁盘历史。

源码：[`src/chronaxis/execution/record_session_calculations.py:655`](../../../src/chronaxis/execution/record_session_calculations.py#L655)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordSessionCalculations-_close_slot"></a>
### `RecordSessionCalculations._close_slot`

关闭成功才解除责任。

```python
RecordSessionCalculations._close_slot(slot)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`slot`|str|是|无|位置或关键字。资源拥有者中登记句柄的属性名；关闭成功才清空该槽，失败保留以便重试。|

#### 返回说明

None。

#### 异常说明

原关闭错，槽保留以便重试。

源码：[`src/chronaxis/execution/record_session_calculations.py:712`](../../../src/chronaxis/execution/record_session_calculations.py#L712)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordSessionCalculations-_require_closed"></a>
### `RecordSessionCalculations._require_closed`

核实子资源真实关闭再撤槽。

```python
RecordSessionCalculations._require_closed(owner)
```

装饰器：`staticmethod`。

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|具备close()和closed属性的资源对象|是|无|位置或关键字。本次已登记的子资源；关闭失败保留对象供重试，不清理外部资源。|

#### 返回说明

None。

#### 异常说明

AnalysisError保留原责任。

源码：[`src/chronaxis/execution/record_session_calculations.py:721`](../../../src/chronaxis/execution/record_session_calculations.py#L721)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordSessionCalculations-close"></a>
### `RecordSessionCalculations.close`

反向释放自有资源，保留失败槽供父会话重试。

```python
RecordSessionCalculations.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

原关闭/预算错误；不会抵销其他owner的费用。

源码：[`src/chronaxis/execution/record_session_calculations.py:726`](../../../src/chronaxis/execution/record_session_calculations.py#L726)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
