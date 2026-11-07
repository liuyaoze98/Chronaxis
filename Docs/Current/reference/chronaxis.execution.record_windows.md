# `chronaxis.execution.record_windows`

从最终事件表生成窗口，不再复制一份事件阶段或重扫原输入。

每个窗口只保最后可能继续合并的父组及有限新父；记录周期借共享实际时刻索引。
边界扩展/合并继续使用既有两个独立窗口核，默认输出精简片段。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Event](chronaxis.core.temporal.md#api-Event)、[Interval](chronaxis.core.models.md#api-Interval)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[ResultFormatError](chronaxis.results.errors.md#api-ResultFormatError)、[SummaryEventRow](chronaxis.results.summary.md#api-SummaryEventRow)、[TemporalRule](chronaxis.core.temporal.md#api-TemporalRule)、[WindowSpec](chronaxis.core.windows.md#api-WindowSpec)

## 对象导航

|对象|用途|
|---|---|
|[`RecordWindows`](#api-RecordWindows)|拥有最终事件表读槽和有限待合并父组；共享时点索引、结果仓均为借用。|
|[`RecordWindows.__init__`](#api-RecordWindows-__init__)|预付声明，不读取输入或事件表。|
|[`RecordWindows._bounds`](#api-RecordWindows-_bounds)|按所选周期定位实际边界；actual由原核直接扩展。|
|[`RecordWindows._coverage`](#api-RecordWindows-_coverage)|仅明确门槛请求才算窗口已取得部分比例，不保存各记录的第二时间。|
|[`RecordWindows._process`](#api-RecordWindows-_process)|复用窗口核，非末批只保最后合并组，其他片段直接输出。|
|[`RecordWindows.finish`](#api-RecordWindows-finish)|所有来源结束后只读一次最终事件表，并生成片段。|
|[`RecordWindows.closed`](#api-RecordWindows-closed)|返回资源关闭状态。|
|[`RecordWindows.close`](#api-RecordWindows-close)|关闭读槽并释放剩余父组，不删除最终事件表。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import replace
from fractions import Fraction
from ..core.models import Interval
from ..core.temporal import Event, TemporalRule
from ..core.windows import WindowSpec
from ..core.windows_reference import build_segments_reference
from ..core.windows_numpy import build_segments_numpy
from ..results.summary import SummaryEventRow
from ..results.codec import decode_row
from ..core.types import QualityFlag as Q
from ..results.errors import ResultClosedError, ResultFormatError
from ..results.spool import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from .history import _metadata_bytes
```

</details>

<a id="api-RecordWindows"></a>
## `RecordWindows`

拥有最终事件表读槽和有限待合并父组；共享时点索引、结果仓均为借用。

```python
RecordWindows(plan, budget, indexes, steps, consumer)
```


源码：[`src/chronaxis/execution/record_windows.py:21`](../../../src/chronaxis/execution/record_windows.py#L21)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordWindows-__init__"></a>
### `RecordWindows.__init__`

预付声明，不读取输入或事件表。

```python
RecordWindows.__init__(plan, budget, indexes, steps, consumer)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|AnalysisPlan|是|无|位置或关键字。已完成静态解析的分析计划，包含来源、绑定、规则、指标、间隔选择和输出要求。|
|`budget`|ResourceBudget|是|无|位置或关键字。本次分析共享的资源用量记录；新对象先预约所需内存和磁盘额度，关闭时归还自己的内存费用。|
|`indexes`|RecordTimeIndexes|是|无|位置或关键字。当前窗口实际需要的驱动时刻索引；仅在必须向前/后定位记录时存在。|
|`steps`|Mapping[str, int &#124; None]|是|无|位置或关键字。节点id到已解析周期的映射；None为实际间隔，正整数为固定或DBC纳秒周期。|
|`consumer`|Callable[[CompactSegment], None]|是|无|位置或关键字。接收已按选定间隔展开、按观测裁剪的实际片段。|

#### 返回说明

owner。

#### 异常说明

原构造错。

源码：[`src/chronaxis/execution/record_windows.py:24`](../../../src/chronaxis/execution/record_windows.py#L24)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordWindows-_bounds"></a>
### `RecordWindows._bounds`

按所选周期定位实际边界；actual由原核直接扩展。

```python
RecordWindows._bounds(window, event)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`window`|WindowPlan|是|无|位置或关键字。当前窗口配置，指定所属规则、事件锚点、前后范围及合并方式。|
|`event`|[Event](chronaxis.core.temporal.md#api-Event)|是|无|位置或关键字。本次规则产生的活动或点事件；保留实际开始、确认、结束和状态。|

#### 返回说明

四元组或None。

#### 异常说明

原查找错。

源码：[`src/chronaxis/execution/record_windows.py:54`](../../../src/chronaxis/execution/record_windows.py#L54)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordWindows-_coverage"></a>
### `RecordWindows._coverage`

仅明确门槛请求才算窗口已取得部分比例，不保存各记录的第二时间。

```python
RecordWindows._coverage(window, segment, parents)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`window`|WindowPlan|是|无|位置或关键字。当前窗口配置，指定所属规则、事件锚点、前后范围及合并方式。|
|`segment`|CompactSegment|是|无|位置或关键字。已确定的实际窗口片段，包含业务范围及父事件关联，供计算或导出使用。|
|`parents`|Sequence[[Event](chronaxis.core.temporal.md#api-Event)]|是|无|位置或关键字。组成当前片段的原活动/点事件集合；保留各父事件身份，不把合并范围当一条原活动。|

#### 返回说明

0—1或无法确定的None。

#### 异常说明

原时间读取错。
actual沿原请求秒数；周期模式按已选记录跨度与请求周期数比较。

源码：[`src/chronaxis/execution/record_windows.py:68`](../../../src/chronaxis/execution/record_windows.py#L68)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordWindows-_process"></a>
### `RecordWindows._process`

复用窗口核，非末批只保最后合并组，其他片段直接输出。

```python
RecordWindows._process(window, final=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`window`|WindowPlan|是|无|位置或关键字。当前窗口配置，指定所属规则、事件锚点、前后范围及合并方式。|
|`final`|bool|否|False|位置或关键字。是否已到真实EOF后的最终处理；True允许收紧观测末端和结束未完成状态。|

#### 返回说明

None。

#### 异常说明

预算/窗口/发布原错，责任保留到close。

源码：[`src/chronaxis/execution/record_windows.py:99`](../../../src/chronaxis/execution/record_windows.py#L99)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordWindows-finish"></a>
### `RecordWindows.finish`

所有来源结束后只读一次最终事件表，并生成片段。

```python
RecordWindows.finish(cursors, spool)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`cursors`|Sequence[RecordSourceCursor]|是|无|位置或关键字。本次实际打开的来源游标，借用其真实首末时刻和EOF状态；调用方保留关闭责任。|
|`spool`|ResultSpool|是|无|位置或关键字。接收或读取本次最终结果的有界暂存；不重新读取原始日志。|

#### 返回说明

None。

#### 异常说明

缺范围/短读/损坏/预算/发布原错。
未请求窗口时调用方不创建本对象，空事件不建立额外中间仓。

源码：[`src/chronaxis/execution/record_windows.py:146`](../../../src/chronaxis/execution/record_windows.py#L146)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordWindows-closed"></a>
### `RecordWindows.closed`

返回资源关闭状态。

```python
RecordWindows.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

bool。

#### 异常说明

无。

源码：[`src/chronaxis/execution/record_windows.py:219`](../../../src/chronaxis/execution/record_windows.py#L219)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordWindows-close"></a>
### `RecordWindows.close`

关闭读槽并释放剩余父组，不删除最终事件表。

```python
RecordWindows.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

原关闭错，可重试。

源码：[`src/chronaxis/execution/record_windows.py:223`](../../../src/chronaxis/execution/record_windows.py#L223)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
