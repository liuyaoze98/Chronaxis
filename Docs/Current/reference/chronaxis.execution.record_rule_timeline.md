# chronaxis.execution.record_rule_timeline

用最新必要信号在线推进一条规则，不保存输入历史或第二时间轴。

只暂留一个完整条件组，等下一组或真实EOF确定其是否为末点。实际模式调度
必要TTL和规则截止；记录周期模式只在选定驱动更新时增加等待量。输出直接
交调用方结果消费者，输入/共享状态和结果仓不归本对象所有。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[BudgetedTemporalDetector](chronaxis.execution.temporal_buffer.md#api-BudgetedTemporalDetector)、[ConditionTick](chronaxis.core.temporal.md#api-ConditionTick)、[DriverExpression](chronaxis.execution.driver_expression.md#api-DriverExpression)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[RecordAlarmDuration](chronaxis.execution.record_alarm_duration.md#api-RecordAlarmDuration)、[RecordDeltaCondition](chronaxis.execution.record_delta_condition.md#api-RecordDeltaCondition)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[RuleOutcome](chronaxis.results.analysis_outcome.md#api-RuleOutcome)、[T](chronaxis.core.types.md#api-Truth)、[TemporalRule](chronaxis.core.temporal.md#api-TemporalRule)

## 对象导航

|对象|用途|
|---|---|
|[`RecordRuleTimeline`](#api-RecordRuleTimeline)|拥有规则表达式、检测器和一个待定条件组；原始组由父会话原子提交。|
|[`RecordRuleTimeline.__init__`](#api-RecordRuleTimeline-__init__)|建立有限声明，不读来源，也不把请求域当作已观测范围。|
|[`RecordRuleTimeline.extend_observation`](#api-RecordRuleTimeline-extend_observation)|更新单遍读取已见的末端；最后条件组仍等待后继或EOF。|
|[`RecordRuleTimeline._open`](#api-RecordRuleTimeline-_open)|拒绝失效实例。|
|[`RecordRuleTimeline.begin`](#api-RecordRuleTimeline-begin)|用实际观察起点建立检测器，空来源由父跳过。|
|[`RecordRuleTimeline._snapshot`](#api-RecordRuleTimeline-_snapshot)|收齐进出条件的点/右侧值，保一个必要组。|
|[`RecordRuleTimeline._commit`](#api-RecordRuleTimeline-_commit)|交付一个完整条件组和增量事件，消费失败不返回前缀。|
|[`RecordRuleTimeline._drain_before`](#api-RecordRuleTimeline-_drain_before)|只推进已经由后续观测证明存在的区间。|
|[`RecordRuleTimeline.before_group`](#api-RecordRuleTimeline-before_group)|父提交新组前处理旧状态上的TTL和实际等待。|
|[`RecordRuleTimeline.after_group`](#api-RecordRuleTimeline-after_group)|父原子提交后保存新条件组；实际终点在同一时刻更新之后结算。|
|[`RecordRuleTimeline.clock_group`](#api-RecordRuleTimeline-clock_group)|待定旧条件已经交付后，接收报警累计所需的完整驱动对。|
|[`RecordRuleTimeline.finish`](#api-RecordRuleTimeline-finish)|所有必要来源EOF后按真实末端封口，不外推到请求结束。|
|[`RecordRuleTimeline.outcome`](#api-RecordRuleTimeline-outcome)|冻结规则结果原因，不读取输入。|
|[`RecordRuleTimeline.duration_result`](#api-RecordRuleTimeline-duration_result)|借出明确请求的最终累计；空来源返回无观测。|
|[`RecordRuleTimeline.closed`](#api-RecordRuleTimeline-closed)|返回资源关闭状态。|
|[`RecordRuleTimeline.close`](#api-RecordRuleTimeline-close)|释放自有批、表达式和检测器，保留失败槽供重试。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import replace
from ..core.temporal import ConditionTick, TemporalRule
from ..core.types import Truth as T, QualityFlag as Q
from ..results.errors import ResultClosedError
from ..results.spool import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from .driver_expression import DriverExpression
from .temporal_buffer import BudgetedTemporalDetector
from .history import _metadata_bytes
from .record_alarm_duration import RecordAlarmDuration
from .record_delta_condition import RecordDeltaCondition
```

</details>

<a id="api-RecordRuleTimeline"></a>
## `RecordRuleTimeline`

拥有规则表达式、检测器和一个待定条件组；原始组由父会话原子提交。

```python
RecordRuleTimeline(plan, request, state, budget, step_ns, driver, observation_ends, consumer, step_consumer=None)
```


源码：[`src/chronaxis/execution/record_rule_timeline.py:20`](../../../src/chronaxis/execution/record_rule_timeline.py#L20)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordRuleTimeline-__init__"></a>
### `RecordRuleTimeline.__init__`

建立有限声明，不读来源，也不把请求域当作已观测范围。

```python
RecordRuleTimeline.__init__(plan, request, state, budget, step_ns, driver, observation_ends, consumer, step_consumer=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|AnalysisPlan|是|无|位置或关键字。已完成静态解析的分析计划，包含来源、绑定、规则、指标、间隔选择和输出要求。|
|`request`|RulePlan|是|无|位置或关键字。当前规则声明及已经编译的依赖表达式；与plan属于同一任务。|
|`state`|LatestSignalState|是|无|位置或关键字。当前会话各依赖信号的最新有效状态；过期按实际时间判断，不能跨独立任务继承。|
|`budget`|ResourceBudget|是|无|位置或关键字。本次分析共享的资源用量记录；新对象先预约所需内存和磁盘额度，关闭时归还自己的内存费用。|
|`step_ns`|int &#124; None|是|无|位置或关键字。所选固定或DBC周期，单位纳秒且大于0；None表示采用实际时间间隔，不生成第二套时间坐标。|
|`driver`|str &#124; None|是|无|位置或关键字。推进该计算的原信号别名；None按实际更新组求值，固定/DBC模式使用已解析的唯一别名。|
|`observation_ends`|Mapping[str, int]|是|无|位置或关键字。已知来源EOF实际纳秒时刻；尚未结束的来源没有条目。|
|`consumer`|Callable[[Event], None]|是|无|位置或关键字。接收该规则已确定的原始事件；窗口扩展和合并由后续消费者处理。|
|`step_consumer`|Callable[[str, [ConditionTick](chronaxis.core.temporal.md#api-ConditionTick), tuple[Event, ...]], None] &#124; None|否|None|位置或关键字。接收规则ID、完整条件点及同一时刻事件，供配对使用；None不保留这项中间交付。|

#### 返回说明

新owner。

#### 异常说明

原构造错误附record_rule_cleanup_owner。

源码：[`src/chronaxis/execution/record_rule_timeline.py:23`](../../../src/chronaxis/execution/record_rule_timeline.py#L23)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordRuleTimeline-extend_observation"></a>
### `RecordRuleTimeline.extend_observation`

更新单遍读取已见的末端；最后条件组仍等待后继或EOF。

```python
RecordRuleTimeline.extend_observation(end_ns)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`end_ns`|int|是|无|位置或关键字。本次读到的实际观测末端，纳秒；只延长既有时间线，不重复读取输入。|

#### 返回说明

None。

#### 异常说明

回退。

源码：[`src/chronaxis/execution/record_rule_timeline.py:78`](../../../src/chronaxis/execution/record_rule_timeline.py#L78)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordRuleTimeline-_open"></a>
### `RecordRuleTimeline._open`

拒绝失效实例。

```python
RecordRuleTimeline._open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

ResultClosedError。

源码：[`src/chronaxis/execution/record_rule_timeline.py:88`](../../../src/chronaxis/execution/record_rule_timeline.py#L88)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordRuleTimeline-begin"></a>
### `RecordRuleTimeline.begin`

用实际观察起点建立检测器，空来源由父跳过。

```python
RecordRuleTimeline.begin(observed_start)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`observed_start`|int|是|无|位置或关键字。实际观察到的来源起点，单位纳秒；不能从请求范围虚构输入起点。|

#### 返回说明

None。

#### 异常说明

构造/范围错误附可清理owner。

源码：[`src/chronaxis/execution/record_rule_timeline.py:93`](../../../src/chronaxis/execution/record_rule_timeline.py#L93)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordRuleTimeline-_snapshot"></a>
### `RecordRuleTimeline._snapshot`

收齐进出条件的点/右侧值，保一个必要组。

```python
RecordRuleTimeline._snapshot(time_ns, actual, terminal=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|位置或关键字。本次操作对应的实际时刻，单位纳秒；必须按输入的单调顺序推进，不是累计的固定周期数。|
|`actual`|bool|是|无|位置或关键字。是否由真实输入更新生成快照；False表示到期或终点边界，不能增加记录周期。|
|`terminal`|bool|否|False|位置或关键字。是否为真实观测终点的条件快照；终点不再建立新的持续活动或补时长。|

#### 返回说明

None。

#### 异常说明

求值原错。

源码：[`src/chronaxis/execution/record_rule_timeline.py:122`](../../../src/chronaxis/execution/record_rule_timeline.py#L122)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordRuleTimeline-_commit"></a>
### `RecordRuleTimeline._commit`

交付一个完整条件组和增量事件，消费失败不返回前缀。

```python
RecordRuleTimeline._commit()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

原错。

源码：[`src/chronaxis/execution/record_rule_timeline.py:159`](../../../src/chronaxis/execution/record_rule_timeline.py#L159)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordRuleTimeline-_drain_before"></a>
### `RecordRuleTimeline._drain_before`

只推进已经由后续观测证明存在的区间。

```python
RecordRuleTimeline._drain_before(time_ns)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|位置或关键字。本次操作对应的实际时刻，单位纳秒；必须按输入的单调顺序推进，不是累计的固定周期数。|

#### 返回说明

None。

#### 异常说明

原推进错。

源码：[`src/chronaxis/execution/record_rule_timeline.py:201`](../../../src/chronaxis/execution/record_rule_timeline.py#L201)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordRuleTimeline-before_group"></a>
### `RecordRuleTimeline.before_group`

父提交新组前处理旧状态上的TTL和实际等待。

```python
RecordRuleTimeline.before_group(time_ns)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|位置或关键字。本次操作对应的实际时刻，单位纳秒；必须按输入的单调顺序推进，不是累计的固定周期数。|

#### 返回说明

None。

#### 异常说明

原错。

源码：[`src/chronaxis/execution/record_rule_timeline.py:215`](../../../src/chronaxis/execution/record_rule_timeline.py#L215)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordRuleTimeline-after_group"></a>
### `RecordRuleTimeline.after_group`

父原子提交后保存新条件组；实际终点在同一时刻更新之后结算。

```python
RecordRuleTimeline.after_group(time_ns)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|位置或关键字。本次操作对应的实际时刻，单位纳秒；必须按输入的单调顺序推进，不是累计的固定周期数。|

#### 返回说明

None。

#### 异常说明

原求值/事件错误，失败只能关闭。

源码：[`src/chronaxis/execution/record_rule_timeline.py:230`](../../../src/chronaxis/execution/record_rule_timeline.py#L230)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordRuleTimeline-clock_group"></a>
### `RecordRuleTimeline.clock_group`

待定旧条件已经交付后，接收报警累计所需的完整驱动对。

```python
RecordRuleTimeline.clock_group(group)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`group`|DecodedTimeGroup|是|无|位置或关键字。同一实际时刻收齐的所需信号更新；本组全部到齐后再求值，避免来源遍历顺序影响结果。|

#### 返回说明

None。

#### 异常说明

累计顺序/预算错误。
不改变事件坐标，也不把请求域外样本算入报警；只借它们确定裁剪分母。

源码：[`src/chronaxis/execution/record_rule_timeline.py:251`](../../../src/chronaxis/execution/record_rule_timeline.py#L251)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordRuleTimeline-finish"></a>
### `RecordRuleTimeline.finish`

所有必要来源EOF后按真实末端封口，不外推到请求结束。

```python
RecordRuleTimeline.finish(observed_end)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`observed_end`|int|是|无|位置或关键字。实际来源EOF时刻，单位纳秒；终点只负责收尾，不补造一条真实更新。|

#### 返回说明

None。

#### 异常说明

原错，未完成不发布结果。

源码：[`src/chronaxis/execution/record_rule_timeline.py:260`](../../../src/chronaxis/execution/record_rule_timeline.py#L260)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordRuleTimeline-outcome"></a>
### `RecordRuleTimeline.outcome`

冻结规则结果原因，不读取输入。

```python
RecordRuleTimeline.outcome()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

RuleOutcome。

#### 异常说明

未完成或已关闭。

有事件时始终保留计数；缺信号和UNKNOWN不被解释成条件为假。

源码：[`src/chronaxis/execution/record_rule_timeline.py:290`](../../../src/chronaxis/execution/record_rule_timeline.py#L290)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordRuleTimeline-duration_result"></a>
### `RecordRuleTimeline.duration_result`

借出明确请求的最终累计；空来源返回无观测。

```python
RecordRuleTimeline.duration_result
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

tuple或None。

#### 异常说明

未完成错误。

源码：[`src/chronaxis/execution/record_rule_timeline.py:316`](../../../src/chronaxis/execution/record_rule_timeline.py#L316)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordRuleTimeline-closed"></a>
### `RecordRuleTimeline.closed`

返回资源关闭状态。

```python
RecordRuleTimeline.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

bool。

#### 异常说明

无。

源码：[`src/chronaxis/execution/record_rule_timeline.py:325`](../../../src/chronaxis/execution/record_rule_timeline.py#L325)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordRuleTimeline-close"></a>
### `RecordRuleTimeline.close`

释放自有批、表达式和检测器，保留失败槽供重试。

```python
RecordRuleTimeline.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

原关闭错。

源码：[`src/chronaxis/execution/record_rule_timeline.py:329`](../../../src/chronaxis/execution/record_rule_timeline.py#L329)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
