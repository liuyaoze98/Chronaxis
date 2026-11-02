# chronaxis.execution.record_event_durations

按需计算每段事件的持续时长，只为周期模式保存必要驱动时间。

实际模式直接使用事件范围。固定/DBC需要知道事件两端落在哪对报文中，因而
保存每条所选驱动的一个整数时间；按索引二分定位，只回读相关记录对。该文件
没有数值、原帧或另一时间轴，未请求此类统计时不建立；关闭自动删除。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)、[D](chronaxis.core.types.md#api-SignalDType)、[Interval](chronaxis.core.models.md#api-Interval)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[RecordTimeCalculation](chronaxis.execution.record_time_calculation.md#api-RecordTimeCalculation)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)

## 对象导航

|对象|用途|
|---|---|
|[`RecordEventDurations`](#api-RecordEventDurations)|拥有必要时点文件、尚缺右端的事件及一个短生命周期数值查询。|
|[`RecordEventDurations.__init__`](#api-RecordEventDurations-__init__)|预付有限索引状态，不为actual创建文件。|
|[`RecordEventDurations._open`](#api-RecordEventDurations-_open)|拒绝关闭/失败实例。|
|[`RecordEventDurations.observe_group`](#api-RecordEventDurations-observe_group)|父已更新共享时点索引，尝试完成等待中的事件。|
|[`RecordEventDurations.observe_event`](#api-RecordEventDurations-observe_event)|只为匹配事件建立必要查询，缺右端时暂存端点和ID。|
|[`RecordEventDurations._calculate`](#api-RecordEventDurations-_calculate)|只借取事件两侧及区间内的驱动点，复用原两后端时长核。|
|[`RecordEventDurations._flush_ready`](#api-RecordEventDurations-_flush_ready)|保留仍缺右端的请求，其余按必要范围计算；EOF不补记录。|
|[`RecordEventDurations.finish`](#api-RecordEventDurations-finish)|真实EOF后结算未完成范围，不假造周期尾段。|
|[`RecordEventDurations.closed`](#api-RecordEventDurations-closed)|返回关闭状态。|
|[`RecordEventDurations.close`](#api-RecordEventDurations-close)|只关闭自己的临时文件，成功后才撤销责任。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..core.models import Interval
from ..core.calculations import CalculationDefinition
from ..core.numeric import ScalarValue
from ..core.types import SignalDType as D, QualityFlag as Q
from ..results.errors import ResultClosedError
from ..results.spool import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from .record_time_calculation import RecordTimeCalculation
from .history import _metadata_bytes
from ..planning.record_execution import is_event_duration
```

</details>

<a id="api-RecordEventDurations"></a>
## `RecordEventDurations`

拥有必要时点文件、尚缺右端的事件及一个短生命周期数值查询。

```python
RecordEventDurations(plan, budget, work_dir, steps, consumer, *, indexes=None)
```


源码：[`src/chronaxis/execution/record_event_durations.py:20`](../../../src/chronaxis/execution/record_event_durations.py#L20)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordEventDurations-__init__"></a>
### `RecordEventDurations.__init__`

预付有限索引状态，不为actual创建文件。

```python
RecordEventDurations.__init__(plan, budget, work_dir, steps, consumer, *, indexes=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|AnalysisPlan|是|无|位置或关键字。已完成静态解析的分析计划，包含来源、绑定、规则、指标、间隔选择和输出要求。|
|`budget`|ResourceBudget|是|无|位置或关键字。本次分析共享的资源用量记录；新对象先预约所需内存和磁盘额度，关闭时归还自己的内存费用。|
|`work_dir`|str &#124; Path &#124; None|是|无|位置或关键字。本次专用工作目录，用于确实需要的临时资源；不得使用原始输入或RefProjects。是否可省略由本表签名默认值明确给出。|
|`steps`|Mapping[str, int &#124; None]|是|无|位置或关键字。节点id到已解析周期的映射；None为实际间隔，正整数为固定或DBC纳秒周期。|
|`consumer`|Callable[[CalculationPlan, str, RecordTimeResult], None]|是|无|位置或关键字。接收指标声明、父事件ID和按该事件范围计算的持续时长结果。|
|`indexes`|RecordTimeIndexes|否|None|仅关键字。当前窗口实际需要的驱动时刻索引；仅在必须向前/后定位记录时存在。|

#### 返回说明

owner。

#### 异常说明

原构造错误。

源码：[`src/chronaxis/execution/record_event_durations.py:23`](../../../src/chronaxis/execution/record_event_durations.py#L23)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordEventDurations-_open"></a>
### `RecordEventDurations._open`

拒绝关闭/失败实例。

```python
RecordEventDurations._open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

ResultClosedError。

源码：[`src/chronaxis/execution/record_event_durations.py:40`](../../../src/chronaxis/execution/record_event_durations.py#L40)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordEventDurations-observe_group"></a>
### `RecordEventDurations.observe_group`

父已更新共享时点索引，尝试完成等待中的事件。

```python
RecordEventDurations.observe_group(group)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`group`|DecodedTimeGroup|是|无|位置或关键字。同一实际时刻收齐的所需信号更新；本组全部到齐后再求值，避免来源遍历顺序影响结果。|

#### 返回说明

None。

#### 异常说明

查询原错。

源码：[`src/chronaxis/execution/record_event_durations.py:45`](../../../src/chronaxis/execution/record_event_durations.py#L45)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordEventDurations-observe_event"></a>
### `RecordEventDurations.observe_event`

只为匹配事件建立必要查询，缺右端时暂存端点和ID。

```python
RecordEventDurations.observe_event(event)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`event`|Event|是|无|位置或关键字。本次规则产生的活动或点事件；保留实际开始、确认、结束和状态。|

#### 返回说明

None。

#### 异常说明

预算/求值原错。

源码：[`src/chronaxis/execution/record_event_durations.py:50`](../../../src/chronaxis/execution/record_event_durations.py#L50)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordEventDurations-_calculate"></a>
### `RecordEventDurations._calculate`

只借取事件两侧及区间内的驱动点，复用原两后端时长核。

```python
RecordEventDurations._calculate(request, event_id, start_ns, end_ns)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`request`|CalculationPlan|是|无|位置或关键字。当前指标请求，包含ID、统计范围、算子、表达式和缺失处理政策。|
|`event_id`|str|是|无|位置或关键字。本次事件的稳定id，用于指标、窗口及配对结果引用。|
|`start_ns`|int|是|无|位置或关键字。本次查询或计算的实际开始时刻，单位纳秒。|
|`end_ns`|int|是|无|位置或关键字。本次查询或计算的实际结束时刻，单位纳秒；按具体函数保留必要右端点供半开范围计算。|

#### 返回说明

None，结果交回调。

#### 异常说明

构造/数值/发布原错。

源码：[`src/chronaxis/execution/record_event_durations.py:66`](../../../src/chronaxis/execution/record_event_durations.py#L66)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordEventDurations-_flush_ready"></a>
### `RecordEventDurations._flush_ready`

保留仍缺右端的请求，其余按必要范围计算；EOF不补记录。

```python
RecordEventDurations._flush_ready(final=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`final`|bool|否|False|位置或关键字。是否已到真实EOF后的最终处理；True允许收紧观测末端和结束未完成状态。|

#### 返回说明

None。

#### 异常说明

原查询错，费用留到close。

源码：[`src/chronaxis/execution/record_event_durations.py:98`](../../../src/chronaxis/execution/record_event_durations.py#L98)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordEventDurations-finish"></a>
### `RecordEventDurations.finish`

真实EOF后结算未完成范围，不假造周期尾段。

```python
RecordEventDurations.finish()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

原计算错。

源码：[`src/chronaxis/execution/record_event_durations.py:123`](../../../src/chronaxis/execution/record_event_durations.py#L123)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordEventDurations-closed"></a>
### `RecordEventDurations.closed`

返回关闭状态。

```python
RecordEventDurations.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

bool。

#### 异常说明

无。

源码：[`src/chronaxis/execution/record_event_durations.py:129`](../../../src/chronaxis/execution/record_event_durations.py#L129)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordEventDurations-close"></a>
### `RecordEventDurations.close`

只关闭自己的临时文件，成功后才撤销责任。

```python
RecordEventDurations.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

原关闭错可重试。

源码：[`src/chronaxis/execution/record_event_durations.py:133`](../../../src/chronaxis/execution/record_event_durations.py#L133)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
