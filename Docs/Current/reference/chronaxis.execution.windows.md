# `chronaxis.execution.windows`

在分配窗口临时数组和片段元数据前申请预算，并拥有可关闭的查询结果。

输入是caller已提供的完整有限Event tuple、WindowSpec和真实观测Interval。
独立参考/NumPy内核仍分别扩展、分组、裁剪和计算覆盖，本层不重写数值算法。
完整创建后不可修改的输入对象元数据与N事件临时量在内核前预留，整个workspace由SegmentBatch保有到close。
仅保守约束新查询层；caller预先物化的输入、外部另存引用和整个进程RSS另行说明。
不把独立batch当作可跨批分组的流式输入，不读取旧链/历史、不发布公共AnalysisRunner。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Event](chronaxis.core.temporal.md#api-Event)、[Interval](chronaxis.core.models.md#api-Interval)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[WindowSpec](chronaxis.core.windows.md#api-WindowSpec)、[_BatchRegistry](chronaxis.execution.temporal_buffer.md#api-_BatchRegistry)

## 对象导航

|对象|用途|
|---|---|
|[`SegmentBatch`](#api-SegmentBatch)|拥有一份完整窗口结果和预留成本，和其他已交付查询相互独立。|
|[`SegmentBatch.__init__`](#api-SegmentBatch-__init__)|在已预留成本中构造局部批，不负责登记。|
|[`SegmentBatch.closed`](#api-SegmentBatch-closed)|读取关闭状态。|
|[`SegmentBatch.segments`](#api-SegmentBatch-segments)|读取本查询全部片段。|
|[`SegmentBatch._discard`](#api-SegmentBatch-_discard)|脱离登记并丢弃输出，不重复扣账。|
|[`SegmentBatch.close`](#api-SegmentBatch-close)|释放输出成本，区分扣账前后取消，重复关闭幂等。|
|[`WindowQueries`](#api-WindowQueries)|为完整有限窗口输入提供预算边界，自有批必须及时close。|
|[`WindowQueries.__init__`](#api-WindowQueries-__init__)|校验配置并申请固定生命周期开销后选择实际数值入口。|
|[`WindowQueries.closed`](#api-WindowQueries-closed)|读取关闭状态。|
|[`WindowQueries._ensure_open`](#api-WindowQueries-_ensure_open)|拒绝关闭后执行。|
|[`WindowQueries._construct`](#api-WindowQueries-_construct)|构造局部结果。|
|[`WindowQueries.build`](#api-WindowQueries-build)|在预算门槛后执行一个完整窗口集合，保留全部真实父事件。|
|[`WindowQueries.close`](#api-WindowQueries-close)|关闭全部自有结果再抵销固定成本，支持关闭中断后重试。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..core.models import Interval
from ..core.temporal import Event
from ..core.windows import WindowSpec
from ..core.windows_reference import build_segments_reference
from ..core.windows_numpy import build_segments_numpy
from ..results.budget import ResourceBudget
from ..results.errors import ResultClosedError
from .history import _metadata_bytes
from .temporal_buffer import _BatchRegistry
```

</details>

<a id="api-SegmentBatch"></a>
## `SegmentBatch`

拥有一份完整窗口结果和预留成本，和其他已交付查询相互独立。

父事件ID/状态/完整SourceRef由片段引用，workspace覆盖这些冻结元数据的存活。
链指针放在本对象中，关闭不遗留随历史调用数增长的容器槽位。

```python
SegmentBatch(owner, cost, segments)
```


源码：[`src/chronaxis/execution/windows.py:22`](../../../src/chronaxis/execution/windows.py#L22)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SegmentBatch-__init__"></a>
### `SegmentBatch.__init__`

在已预留成本中构造局部批，不负责登记。

```python
SegmentBatch.__init__(owner, cost, segments)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|[WindowQueries](chronaxis.execution.windows.md#api-WindowQueries)|是|无|位置或关键字。产生这批片段的窗口查询器，负责登记结果和关闭时释放资源。|
|`cost`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|
|`segments`|tuple[Segment, ...]|是|无|位置或关键字。窗口内核本次生成的片段；元组中的片段边界和父事件ID已经确定。|

#### 返回说明

新批。

#### 异常说明

分配/取消由外层抵销成本，未发布不隐藏失败。

源码：[`src/chronaxis/execution/windows.py:29`](../../../src/chronaxis/execution/windows.py#L29)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SegmentBatch-closed"></a>
### `SegmentBatch.closed`

读取关闭状态。

```python
SegmentBatch.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/execution/windows.py:39`](../../../src/chronaxis/execution/windows.py#L39)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SegmentBatch-segments"></a>
### `SegmentBatch.segments`

读取本查询全部片段。

```python
SegmentBatch.segments
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

Segment tuple。

#### 异常说明

ResultClosedError。

本函数直接报告的具体错误：

- `ResultClosedError`：窗口片段批已关闭。

源码：[`src/chronaxis/execution/windows.py:44`](../../../src/chronaxis/execution/windows.py#L44)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SegmentBatch-_discard"></a>
### `SegmentBatch._discard`

脱离登记并丢弃输出，不重复扣账。

```python
SegmentBatch._discard()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

脱链取消传播，finally仍标closed并丢弃元数据。

源码：[`src/chronaxis/execution/windows.py:50`](../../../src/chronaxis/execution/windows.py#L50)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SegmentBatch-close"></a>
### `SegmentBatch.close`

释放输出成本，区分扣账前后取消，重复关闭幂等。

```python
SegmentBatch.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

预算/取消传播；已抵销时仍完成最小关闭。

源码：[`src/chronaxis/execution/windows.py:61`](../../../src/chronaxis/execution/windows.py#L61)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-WindowQueries"></a>
## `WindowQueries`

为完整有限窗口输入提供预算边界，自有批必须及时close。

此owner无跨批活动/分组状态，每次build都要求该窗口的完整事件集合。
数值或协议失败不改变先前输出，也不把一个查询当作下一查询的部分输入。

```python
WindowQueries(budget: ResourceBudget, *, backend='numpy')
```


源码：[`src/chronaxis/execution/windows.py:78`](../../../src/chronaxis/execution/windows.py#L78)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-WindowQueries-__init__"></a>
### `WindowQueries.__init__`

校验配置并申请固定生命周期开销后选择实际数值入口。

```python
WindowQueries.__init__(budget: ResourceBudget, *, backend='numpy')
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)|是|无|位置或关键字。本次运行共用的ResourceBudget对象，用于检查内存和临时磁盘用量。当前对象在分配前申请额度，用完后归还；同一次运行的组件应使用同一个对象。|
|`backend`|str|否|'numpy'|仅关键字。`"reference"`使用独立参考计算；`"numpy"`使用NumPy数组计算。须明确选择一种。|

#### 返回说明

新owner。

#### 异常说明

类型/后端/预算/取消传播，申请返回取消也抵销固定成本。

本函数直接报告的具体错误：

- `TypeError`：窗口查询需要ResourceBudget与reference/numpy后端。

源码：[`src/chronaxis/execution/windows.py:85`](../../../src/chronaxis/execution/windows.py#L85)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-WindowQueries-closed"></a>
### `WindowQueries.closed`

读取关闭状态。

```python
WindowQueries.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/execution/windows.py:108`](../../../src/chronaxis/execution/windows.py#L108)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-WindowQueries-_ensure_open"></a>
### `WindowQueries._ensure_open`

拒绝关闭后执行。

```python
WindowQueries._ensure_open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ResultClosedError。

本函数直接报告的具体错误：

- `ResultClosedError`：窗口查询已关闭。

源码：[`src/chronaxis/execution/windows.py:112`](../../../src/chronaxis/execution/windows.py#L112)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-WindowQueries-_construct"></a>
### `WindowQueries._construct`

构造局部结果。

```python
WindowQueries._construct(cost, segments)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`cost`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|
|`segments`|tuple[Segment, ...]|是|无|位置或关键字。窗口内核返回的Segment元组，保留请求/实际范围与父事件。|

#### 返回说明

SegmentBatch。

#### 异常说明

分配/取消。

源码：[`src/chronaxis/execution/windows.py:117`](../../../src/chronaxis/execution/windows.py#L117)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-WindowQueries-build"></a>
### `WindowQueries.build`

在预算门槛后执行一个完整窗口集合，保留全部真实父事件。

```python
WindowQueries.build(events: tuple[Event, ...], spec: WindowSpec, observation: Interval) -> SegmentBatch
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`events`|tuple[[Event](chronaxis.core.temporal.md#api-Event), ...]|是|无|位置或关键字。完整且按时间排列的父事件，按spec为每个事件计算窗口。|
|`spec`|[WindowSpec](chronaxis.core.windows.md#api-WindowSpec)|是|无|位置或关键字。窗口的起算位置、前后扩展、越界和合并设置。|
|`observation`|[Interval](chronaxis.core.models.md#api-Interval)|是|无|位置或关键字。真实观测到的范围；请求超出此范围时按clip/drop/strict处理，不能用请求范围补齐缺失数据。|

#### 返回说明

须close的SegmentBatch，空事件返回拥有成本的空批。

#### 异常说明

带有明确类型的协议/窗口归属/排序/时间溢出/预算/内核/交付取消均传播。
失败清理本次预留和局部登记，旧批仍可读；无数值状态变化，可再次合法查询。

本函数直接报告的具体错误：

- `TypeError`：窗口查询需要完整Event tuple/WindowSpec/真实Interval。

返回类型：[SegmentBatch](chronaxis.execution.windows.md#api-SegmentBatch)。

源码：[`src/chronaxis/execution/windows.py:121`](../../../src/chronaxis/execution/windows.py#L121)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-WindowQueries-close"></a>
### `WindowQueries.close`

关闭全部自有结果再抵销固定成本，支持关闭中断后重试。

```python
WindowQueries.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None。关闭成功后再次调用不会重复释放同一份资源。

#### 异常说明

子结果/预算/取消传播，已扣账字段最小清理。

源码：[`src/chronaxis/execution/windows.py:154`](../../../src/chronaxis/execution/windows.py#L154)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
