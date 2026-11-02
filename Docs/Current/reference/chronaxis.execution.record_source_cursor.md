# chronaxis.execution.record_source_cursor

按需读取一个来源并提供完整同一时刻组，供多来源按时间合并。

原始报文沿共同解码更新，解析数据沿既有SignalBatch。每次只保一个读取批
及尚未消费的同一时刻组，所有缓存逐笔付费；不建立磁盘历史或重复扫描输入。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisError](chronaxis.results.errors.md#api-AnalysisError)、[BatchSignalGroups](chronaxis.execution.batch_signal_groups.md#api-BatchSignalGroups)、[BudgetedLegacyCANSourceAdapter](chronaxis.execution.can_reader.md#api-BudgetedLegacyCANSourceAdapter)、[BudgetedMemorySourceAdapter](chronaxis.execution.memory_reader.md#api-BudgetedMemorySourceAdapter)、[BudgetedSignalCSVSourceAdapter](chronaxis.execution.csv_reader.md#api-BudgetedSignalCSVSourceAdapter)、[BudgetedTextCANSourceAdapter](chronaxis.execution.text_can_reader.md#api-BudgetedTextCANSourceAdapter)、[FrameDBCContext](chronaxis.execution.frame_capture.md#api-FrameDBCContext)、[RawSignalGroups](chronaxis.execution.raw_signal_groups.md#api-RawSignalGroups)、[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)

## 对象导航

|对象|用途|
|---|---|
|[`RecordSourceCursor`](#api-RecordSourceCursor)|拥有来源、实际游标、同一时刻归组与已付费前瞻队列。|
|[`RecordSourceCursor.__init__`](#api-RecordSourceCursor-__init__)|建立所需来源，原始报文只初始化一次DBC，不读首帧。|
|[`RecordSourceCursor._consume_message`](#api-RecordSourceCursor-_consume_message)|同次解码先交逐消息消费者，再按需归组。|
|[`RecordSourceCursor._new`](#api-RecordSourceCursor-_new)|接实际未返回的子owner。|
|[`RecordSourceCursor._enqueue`](#api-RecordSourceCursor-_enqueue)|在上游释放组费用前接管必要组。|
|[`RecordSourceCursor.peek`](#api-RecordSourceCursor-peek)|读取到下一个完整组或真实EOF，返回借用组。|
|[`RecordSourceCursor.advance`](#api-RecordSourceCursor-advance)|消费当前组并释放其费用，不主动读取下一组。|
|[`RecordSourceCursor._retain_frame_notices`](#api-RecordSourceCursor-_retain_frame_notices)|在同次真实EOF后保留已核DBC帧型提示，不借清单声明代替读取。|
|[`RecordSourceCursor._require_closed`](#api-RecordSourceCursor-_require_closed)|关闭未完成时保留槽。|
|[`RecordSourceCursor._close_slot`](#api-RecordSourceCursor-_close_slot)|成功关闭后才撤槽。|
|[`RecordSourceCursor.close`](#api-RecordSourceCursor-close)|按责任释放当前批/队列和输入；提前关闭不交付末组。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from collections import deque
from ..results.errors import AnalysisError, ResultClosedError
from ..results.spool import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..sources.can_spec import can_field_from_key
from ..sources.models import ReadRequest
from .history import _metadata_bytes
from .raw_signal_groups import RawSignalGroups
from .batch_signal_groups import BatchSignalGroups
from .can_reader import BudgetedLegacyCANSourceAdapter
from .text_can_reader import BudgetedTextCANSourceAdapter
from .memory_reader import BudgetedMemorySourceAdapter
from .csv_reader import BudgetedSignalCSVSourceAdapter
from .frame_capture import FrameDBCContext
```

</details>

<a id="api-RecordSourceCursor"></a>
## `RecordSourceCursor`

拥有来源、实际游标、同一时刻归组与已付费前瞻队列。

```python
RecordSourceCursor(plan, source, definitions, values, clocks, budget, work_dir, *, group_names=None, message_consumer=None, message_keys=(), observe_bounds=False, retain_frames=False, requirements=None)
```


源码：[`src/chronaxis/execution/record_source_cursor.py:22`](../../../src/chronaxis/execution/record_source_cursor.py#L22)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordSourceCursor-__init__"></a>
### `RecordSourceCursor.__init__`

建立所需来源，原始报文只初始化一次DBC，不读首帧。

```python
RecordSourceCursor.__init__(plan, source, definitions, values, clocks, budget, work_dir, *, group_names=None, message_consumer=None, message_keys=(), observe_bounds=False, retain_frames=False, requirements=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|AnalysisPlan|是|无|位置或关键字。已完成静态解析的分析计划，包含来源、绑定、规则、指标、间隔选择和输出要求。|
|`source`|SourcePlan|是|无|位置或关键字。当前单一来源的类型、文件路径和读取配置；不代表已经打开或完成读取。|
|`definitions`|tuple[SignalDefinition, ...]|是|无|位置或关键字。当前来源全部声明的信号定义；values和clocks再裁出实际需要的字段。|
|`values`|set[str]|是|无|位置或关键字。当前来源中实际需要解码/读取数值的信号别名集合；未用别名不构造普通样本。|
|`clocks`|set[str]|是|无|位置或关键字。仅用于推进计时的原信号别名；不要求为这些别名生成无用的普通数值样本。|
|`budget`|ResourceBudget|是|无|位置或关键字。本次分析共享的资源用量记录；新对象先预约所需内存和磁盘额度，关闭时归还自己的内存费用。|
|`work_dir`|str &#124; Path &#124; None|是|无|位置或关键字。本次专用工作目录，用于确实需要的临时资源；不得使用原始输入或RefProjects。是否可省略由本表签名默认值明确给出。|
|`group_names`|set[str] &#124; None|否|None|仅关键字。需要进入时序同一时刻组的别名集合；None采用当前来源定义，空集合不构造组。|
|`message_consumer`|Callable[[LegacyDecodedUpdate], None] &#124; None|否|None|仅关键字。接收当前所需报文解码更新的函数；None不启用额外逐消息交付。|
|`message_keys`|tuple[tuple[int, int, bool, bool], ...]|否|()|仅关键字。所需报文定位，依次为通道、ID、扩展帧标志、FD标志；空集合表示没有额外逐消息需求。|
|`observe_bounds`|bool|否|False|仅关键字。是否收集整个来源的实际观测起止；无信号的常量条件等消费者需要时才开启。|
|`retain_frames`|bool|否|False|仅关键字。是否为明确请求的原帧导出保留同次读取的帧；False不保存原始帧副本。|
|`requirements`|InputRequirements &#124; SourceInputRequirements|否|None|仅关键字。需求分析所得的当前任务或单来源输入范围，用来跳过没有消费者的值、时间和历史。|

#### 返回说明

游标owner。

#### 异常说明

原构造错误，恢复入口record_source_cleanup_owner。

源码：[`src/chronaxis/execution/record_source_cursor.py:25`](../../../src/chronaxis/execution/record_source_cursor.py#L25)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordSourceCursor-_consume_message"></a>
### `RecordSourceCursor._consume_message`

同次解码先交逐消息消费者，再按需归组。

```python
RecordSourceCursor._consume_message(update)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`update`|LegacyDecodedUpdate|是|无|位置或关键字。当前一条所需报文更新，保留原输入序号、所需字段和有效状态；同一时刻不同报文仍分别处理。|

#### 返回说明

None。

#### 异常说明

原消费错误。

源码：[`src/chronaxis/execution/record_source_cursor.py:136`](../../../src/chronaxis/execution/record_source_cursor.py#L136)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordSourceCursor-_new"></a>
### `RecordSourceCursor._new`

接实际未返回的子owner。

```python
RecordSourceCursor._new(factory, recovery, *args, **kwargs)
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

源码：[`src/chronaxis/execution/record_source_cursor.py:146`](../../../src/chronaxis/execution/record_source_cursor.py#L146)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordSourceCursor-_enqueue"></a>
### `RecordSourceCursor._enqueue`

在上游释放组费用前接管必要组。

```python
RecordSourceCursor._enqueue(group)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`group`|DecodedTimeGroup|是|无|位置或关键字。同一实际时刻收齐的所需信号更新；本组全部到齐后再求值，避免来源遍历顺序影响结果。|

#### 返回说明

None。

#### 异常说明

预算/取消。

源码：[`src/chronaxis/execution/record_source_cursor.py:154`](../../../src/chronaxis/execution/record_source_cursor.py#L154)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordSourceCursor-peek"></a>
### `RecordSourceCursor.peek`

读取到下一个完整组或真实EOF，返回借用组。

```python
RecordSourceCursor.peek()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

DecodedTimeGroup或EOF的None。

#### 异常说明

原输入/预算错误；失败后只清理。

源码：[`src/chronaxis/execution/record_source_cursor.py:163`](../../../src/chronaxis/execution/record_source_cursor.py#L163)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordSourceCursor-advance"></a>
### `RecordSourceCursor.advance`

消费当前组并释放其费用，不主动读取下一组。

```python
RecordSourceCursor.advance()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

预算/取消。

源码：[`src/chronaxis/execution/record_source_cursor.py:222`](../../../src/chronaxis/execution/record_source_cursor.py#L222)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordSourceCursor-_retain_frame_notices"></a>
### `RecordSourceCursor._retain_frame_notices`

在同次真实EOF后保留已核DBC帧型提示，不借清单声明代替读取。

```python
RecordSourceCursor._retain_frame_notices()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

已核元数据不一致或预算失败；最高游标负责清理。
只复制实际差异及原绑定，不保留完整READY、样本或历史仓。

源码：[`src/chronaxis/execution/record_source_cursor.py:228`](../../../src/chronaxis/execution/record_source_cursor.py#L228)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordSourceCursor-_require_closed"></a>
### `RecordSourceCursor._require_closed`

关闭未完成时保留槽。

```python
RecordSourceCursor._require_closed(owner)
```

装饰器：`staticmethod`。

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|具备close()和closed属性的资源对象|是|无|位置或关键字。本次已登记的子资源；关闭失败保留对象供重试，不清理外部资源。|

#### 返回说明

None。

#### 异常说明

AnalysisError。

源码：[`src/chronaxis/execution/record_source_cursor.py:263`](../../../src/chronaxis/execution/record_source_cursor.py#L263)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordSourceCursor-_close_slot"></a>
### `RecordSourceCursor._close_slot`

成功关闭后才撤槽。

```python
RecordSourceCursor._close_slot(slot)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`slot`|str|是|无|位置或关键字。资源拥有者中登记句柄的属性名；关闭成功才清空该槽，失败保留以便重试。|

#### 返回说明

None。

#### 异常说明

原关闭错。

源码：[`src/chronaxis/execution/record_source_cursor.py:268`](../../../src/chronaxis/execution/record_source_cursor.py#L268)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordSourceCursor-close"></a>
### `RecordSourceCursor.close`

按责任释放当前批/队列和输入；提前关闭不交付末组。

```python
RecordSourceCursor.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

原关闭/预算错，可从同一owner重试。

源码：[`src/chronaxis/execution/record_source_cursor.py:276`](../../../src/chronaxis/execution/record_source_cursor.py#L276)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
