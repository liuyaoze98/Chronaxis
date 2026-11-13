# `chronaxis.execution.record_sequences`

收齐同一时刻的请求、响应和条件后配对，直接交付最终结果。

只保留本次输入组之前的有限条件边界及尚待响应的请求。没有配对请求时不
建立本对象；不会为配对保存整段信号历史或另一时间轴。每个规则的观测终点
由其必要来源决定，响应来源提前结束只使后续响应未知，不提前结束其他来源。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[BudgetExceededError](chronaxis.results.errors.md#api-BudgetExceededError)、[ConditionTick](chronaxis.core.temporal.md#api-ConditionTick)、[IntervalChoice](chronaxis.planning.intervals.md#api-IntervalChoice)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[SequenceDetector](chronaxis.core.sequence_reference.md#api-SequenceDetector)、[SequenceRule](chronaxis.core.sequence.md#api-SequenceRule)、[SequenceTick](chronaxis.core.sequence.md#api-SequenceTick)、[T](chronaxis.core.types.md#api-Truth)

## 对象导航

|对象|用途|
|---|---|
|[`RecordSequences`](#api-RecordSequences)|拥有同一时刻合并队列及FIFO候选；计划、状态和结果消费者为借用。|
|[`RecordSequences.__init__`](#api-RecordSequences-__init__)|登记有限配对配置。|
|[`RecordSequences._open`](#api-RecordSequences-_open)|拒绝失败实例。|
|[`RecordSequences._entry`](#api-RecordSequences-_entry)|先付费再建立一组。|
|[`RecordSequences.bounds`](#api-RecordSequences-bounds)|从真实来源范围开始/收窄配对域，在末组交付之前调用。|
|[`RecordSequences.observe`](#api-RecordSequences-observe)|借用规则批时先付费再保留必要点，不保存不参与配对的规则。|
|[`RecordSequences.drivers`](#api-RecordSequences-drivers)|仅记录配对实际需要的驱动更新身份。|
|[`RecordSequences._consume`](#api-RecordSequences-_consume)|一次提交同一时刻A/B，候选到结果交付完毕才退费。|
|[`RecordSequences.flush_before`](#api-RecordSequences-flush_before)|所有规则已交付边界后，按实际时间处理一次；None仅用于真实全体EOF。|
|[`RecordSequences.closed`](#api-RecordSequences-closed)|返回资源关闭状态。|
|[`RecordSequences.close`](#api-RecordSequences-close)|放弃未发布候选并退还自有费用。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..planning.intervals import IntervalChoice
from dataclasses import replace
from ..core.sequence import SequenceRule, SequenceTick
from ..core.sequence_reference import SequenceDetector
from ..core.temporal import ConditionTick
from ..core.types import Truth as T, QualityFlag as Q
from ..results.errors import ResultClosedError, BudgetExceededError
from ..results.spool import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from .history import _metadata_bytes
```

</details>

<a id="api-RecordSequences"></a>
## `RecordSequences`

拥有同一时刻合并队列及FIFO候选；计划、状态和结果消费者为借用。

```python
RecordSequences(plan, state, budget, steps, consumer)
```


源码：[`src/chronaxis/execution/record_sequences.py:19`](../../../src/chronaxis/execution/record_sequences.py#L19)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RecordSequences-__init__"></a>
### `RecordSequences.__init__`

登记有限配对配置。

```python
RecordSequences.__init__(plan, state, budget, steps, consumer)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|AnalysisPlan|是|无|位置或关键字。已完成静态解析的分析计划，包含来源、绑定、规则、指标、间隔选择和输出要求。|
|`state`|LatestSignalState|是|无|位置或关键字。当前会话各依赖信号的最新有效状态；过期按实际时间判断，不能跨独立任务继承。|
|`budget`|ResourceBudget|是|无|位置或关键字。本次分析共享的资源用量记录；新对象先预约所需内存和磁盘额度，关闭时归还自己的内存费用。|
|`steps`|Mapping[str, int &#124; None]|是|无|位置或关键字。节点id到已解析周期的映射；None为实际间隔，正整数为固定或DBC纳秒周期。|
|`consumer`|Callable[[SequenceResult], None]|是|无|位置或关键字。接收当前请求完成的配对或超时判定，不收集未请求的输入历史。|

#### 返回说明

owner。

#### 异常说明

构造原错附owner。

源码：[`src/chronaxis/execution/record_sequences.py:22`](../../../src/chronaxis/execution/record_sequences.py#L22)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RecordSequences-_open"></a>
### `RecordSequences._open`

拒绝失败实例。

```python
RecordSequences._open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

ResultClosedError。

源码：[`src/chronaxis/execution/record_sequences.py:36`](../../../src/chronaxis/execution/record_sequences.py#L36)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RecordSequences-_entry"></a>
### `RecordSequences._entry`

先付费再建立一组。

```python
RecordSequences._entry(time_ns)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|位置或关键字。本次操作对应的实际时刻，单位纳秒；必须按输入的单调顺序推进，不是累计的固定周期数。|

#### 返回说明

可变组。

#### 异常说明

预算原错。

源码：[`src/chronaxis/execution/record_sequences.py:41`](../../../src/chronaxis/execution/record_sequences.py#L41)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RecordSequences-bounds"></a>
### `RecordSequences.bounds`

从真实来源范围开始/收窄配对域，在末组交付之前调用。

```python
RecordSequences.bounds(cursors, ends)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`cursors`|Sequence[RecordSourceCursor]|是|无|位置或关键字。本次实际打开的来源游标，借用其真实首末时刻和EOF状态；调用方保留关闭责任。|
|`ends`|Mapping[str, int]|是|无|位置或关键字。来源名到已知实际EOF纳秒时刻的映射，用于收尾和裁剪。|

#### 返回说明

None。

#### 异常说明

范围/预算错误。

源码：[`src/chronaxis/execution/record_sequences.py:48`](../../../src/chronaxis/execution/record_sequences.py#L48)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RecordSequences-observe"></a>
### `RecordSequences.observe`

借用规则批时先付费再保留必要点，不保存不参与配对的规则。

```python
RecordSequences.observe(rule, tick, events)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`rule`|str|是|无|位置或关键字。当前条件点和事件所属的规则ID，只处理配对实际依赖的规则。|
|`tick`|[ConditionTick](chronaxis.core.temporal.md#api-ConditionTick)|是|无|位置或关键字。一个完整实际时刻的条件真/假/未知状态，包含质量及终点标志。|
|`events`|tuple[Event, ...]|是|无|位置或关键字。当前实际时刻产生的事件集合；同一时刻事件先收齐再交给配对处理。|

#### 返回说明

None。

#### 异常说明

预算/重复点错误。

源码：[`src/chronaxis/execution/record_sequences.py:92`](../../../src/chronaxis/execution/record_sequences.py#L92)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RecordSequences-drivers"></a>
### `RecordSequences.drivers`

仅记录配对实际需要的驱动更新身份。

```python
RecordSequences.drivers(group)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`group`|DecodedTimeGroup|是|无|位置或关键字。同一实际时刻收齐的所需信号更新；本组全部到齐后再求值，避免来源遍历顺序影响结果。|

#### 返回说明

None。

#### 异常说明

预算错误。

源码：[`src/chronaxis/execution/record_sequences.py:108`](../../../src/chronaxis/execution/record_sequences.py#L108)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RecordSequences-_consume"></a>
### `RecordSequences._consume`

一次提交同一时刻A/B，候选到结果交付完毕才退费。

```python
RecordSequences._consume(time_ns, entry, active)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|位置或关键字。本次操作对应的实际时刻，单位纳秒；必须按输入的单调顺序推进，不是累计的固定周期数。|
|`entry`|list|是|无|位置或关键字。待提交同一时刻组的内部容器，依次保存规则点/事件映射、更新驱动集合和已付预算字节数。|
|`active`|list|是|无|位置或关键字。当前配对检测状态，依次为声明、检测器、上一条件、是否已有驱动及是否结束。|

#### 返回说明

None。

#### 异常说明

原计算错。

源码：[`src/chronaxis/execution/record_sequences.py:117`](../../../src/chronaxis/execution/record_sequences.py#L117)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RecordSequences-flush_before"></a>
### `RecordSequences.flush_before`

所有规则已交付边界后，按实际时间处理一次；None仅用于真实全体EOF。

```python
RecordSequences.flush_before(before=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`before`|int &#124; None|否|None|位置或关键字。仅提交早于该实际纳秒时刻的待处理组；None提交全部已排队组。|

#### 返回说明

None。

#### 异常说明

原错并封闭实例。

源码：[`src/chronaxis/execution/record_sequences.py:163`](../../../src/chronaxis/execution/record_sequences.py#L163)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RecordSequences-closed"></a>
### `RecordSequences.closed`

返回资源关闭状态。

```python
RecordSequences.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

bool。

#### 异常说明

无。

源码：[`src/chronaxis/execution/record_sequences.py:188`](../../../src/chronaxis/execution/record_sequences.py#L188)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RecordSequences-close"></a>
### `RecordSequences.close`

放弃未发布候选并退还自有费用。

```python
RecordSequences.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

预算释放原错可重试。

源码：[`src/chronaxis/execution/record_sequences.py:192`](../../../src/chronaxis/execution/record_sequences.py#L192)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
