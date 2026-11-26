# `chronaxis.execution.file_group_points`

time_order直接积分的文件工作进程端：把一个文件的目标帧归成同一时刻组点。

PERF-P5-ORDER-01 A1/A2合同。输入是本文件读取器逐条交付的已解码记录；输出是
按时间顺序的同一时刻组点（SameTimeGroupSummary）和至多一个延迟错误（DeferredPointError）。
本模块只做与串行主进程相同的投影、绑定匹配和归一化，然后按时间分组；
不求值表达式、不算面积、不累计，也不知道其他文件。跨文件合并、帧型核对、
求值和积分由主进程归并时完成。

组内位置约定（A2-2）：first_sequence为0，last_sequence为帧数减1，first_conflicts
记录每个error政策信号首次冲突的组内第几帧；不传来源原序号。

两类情况本文件之后不再产生组点，但读取器仍由调用方继续读到EOF，使同一文件
后面的读取错误照常报出（A1-7）：
- 投影、匹配或归一化抛出四种内建类型之一，作为延迟错误交给主进程按原类型报出；
- 本文件某时刻出现同一时刻冲突，冲突组立即交付，主进程归并到该时刻时报出。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CANUpdateProjection](chronaxis.sources.can_updates.md#api-CANUpdateProjection)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[SameFrameEvaluator](chronaxis.execution.same_frame_integrals.md#api-SameFrameEvaluator)、[SameTimeGroupSummary](chronaxis.execution.file_integral_terms.md#api-SameTimeGroupSummary)

## 对象导航

|对象|用途|
|---|---|
|[`DeferredPointError`](#api-DeferredPointError)|串行时会在主进程归并到该帧才抛出的错误；只保存重建所需的类型与原文。|
|[`file_points_minimum_cost`](#api-file_points_minimum_cost)|计算组点生成器不依赖DBC的必要费用下界。|
|[`file_points_cost`](#api-file_points_cost)|报告组点生成器及其归一化用求值器的实际固定预约费用。|
|[`FileGroupPoints`](#api-FileGroupPoints)|一个文件的有界同一时刻分组器，只保存当前一个同一时刻组和停止标志。|
|[`FileGroupPoints.__init__`](#api-FileGroupPoints-__init__)|安装与面积生成器相同的已验证任务，首条原帧尚未读取。|
|[`FileGroupPoints.compatibility_fields`](#api-FileGroupPoints-compatibility_fields)|借用同次投影记录的FD兼容提示。|
|[`FileGroupPoints.frame_identity`](#api-FileGroupPoints-frame_identity)|返回本文件目标帧实际的（扩展帧, FD）。|
|[`FileGroupPoints.stopped`](#api-FileGroupPoints-stopped)|返回本文件是否已停止交付组点。|
|[`FileGroupPoints._require_open`](#api-FileGroupPoints-_require_open)|拒绝失败、完成或关闭后的推进。|
|[`FileGroupPoints._defer`](#api-FileGroupPoints-_defer)|把可延迟的错误转成事件并停止交付组点。|
|[`FileGroupPoints.feed`](#api-FileGroupPoints-feed)|消费读取器的一条已解码记录，必要时返回已完成的组点或延迟错误。|
|[`FileGroupPoints.finish`](#api-FileGroupPoints-finish)|读取器EOF后交付最后一个同一时刻组。|
|[`FileGroupPoints.drain_prefix_on_error`](#api-FileGroupPoints-drain_prefix_on_error)|读取失败时不交付前缀，与面积生成器接口同名。|
|[`FileGroupPoints.close`](#api-FileGroupPoints-close)|断开当前组、投影和求值器引用并退还费用。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from __future__ import annotations
from dataclasses import dataclass
from ..results.budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..results.errors import ResultClosedError
from ..sources.can_spec import can_field_from_key
from ..sources.can_updates import CANUpdateProjection
from .file_integral_terms import SameTimeGroupSummary
from .integral_blocks import DEFERRED_KINDS, POINT_MESSAGE_LIMIT
from .same_frame_integrals import SameFrameEvaluator, same_frame_evaluator_cost, SAME_FRAME_EVALUATOR_BASE_COST, _same_value
from .static_metadata import static_metadata_bytes
```

</details>

<a id="api-DeferredPointError"></a>
## `DeferredPointError`

串行时会在主进程归并到该帧才抛出的错误；只保存重建所需的类型与原文。

```python
class DeferredPointError
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|出错帧的实际时间纳秒，主进程按它确定归并位置。|
|`kind`|type|是|无|DEFERRED_KINDS之一，不保存子类或任意类。|
|`message`|str|是|无|str(错误)原文，不截断、不附加说明。|

源码：[`src/chronaxis/execution/file_group_points.py:34`](../../../src/chronaxis/execution/file_group_points.py#L34)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-file_points_minimum_cost"></a>
## `file_points_minimum_cost`

计算组点生成器不依赖DBC的必要费用下界。

```python
file_points_minimum_cost(signal_count: int) -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`signal_count`|int|是|无|位置或关键字。signal_count为非负信号定义数。|

### 返回说明

int字节数，含固定状态、当前同一时刻组首末值和求值器基础费；不含声明图、读取器及通信包。

### 异常说明

信号数非法时ValueError；不构造状态、不读取文件。

返回类型：int。

源码：[`src/chronaxis/execution/file_group_points.py:42`](../../../src/chronaxis/execution/file_group_points.py#L42)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-file_points_cost"></a>
## `file_points_cost`

报告组点生成器及其归一化用求值器的实际固定预约费用。

```python
file_points_cost(definitions, expressions, derived=()) -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`definitions`|tuple[SignalDefinition, ...]|是|无|位置或关键字。组点任务的信号定义，按任务顺序。|
|`expressions`|tuple[StaticExpression, ...]|是|无|位置或关键字。与计算项同序的静态表达式；只用于构造归一化求值器时的一致性检查。|
|`derived`|tuple|否|()|位置或关键字。definitions、expressions、derived为冻结声明tuple|

### 返回说明

int，保守预约的字节数。

### 异常说明

静态模型原错误继续传播。
调用方另计读取器、通信包和任务重建；此函数不为它们重复占用预算。

返回类型：int。

源码：[`src/chronaxis/execution/file_group_points.py:54`](../../../src/chronaxis/execution/file_group_points.py#L54)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-FileGroupPoints"></a>
## `FileGroupPoints`

一个文件的有界同一时刻分组器，只保存当前一个同一时刻组和停止标志。

不变量：当前组的时间不晚于下一条目标帧；交付的组点时间严格递增；停止后不再交付组点。

```python
FileGroupPoints(budget, definitions, expressions, specs, binding, session_id, *, derived=(), batch_intervals=64, domain=None, step_ns=None)
```


源码：[`src/chronaxis/execution/file_group_points.py:65`](../../../src/chronaxis/execution/file_group_points.py#L65)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-FileGroupPoints-__init__"></a>
### `FileGroupPoints.__init__`

安装与面积生成器相同的已验证任务，首条原帧尚未读取。

```python
FileGroupPoints.__init__(budget, definitions, expressions, specs, binding, session_id, *, derived=(), batch_intervals=64, domain=None, step_ns=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|ResourceBudget|是|无|位置或关键字。工作进程本文件的预算账本，本owner与求值器都在其中预约。|
|`definitions`|tuple[SignalDefinition, ...]|是|无|位置或关键字。已补齐有效期的信号定义，组点里的值按此顺序排列。|
|`expressions`|tuple[StaticExpression, ...]|是|无|位置或关键字。与计算项同序的静态表达式；只用于求值器的一致性检查，工作进程不求值。|
|`specs`|tuple[CalculationDefinition, ...]|是|无|位置或关键字。与表达式同序的积分计算项；只为与restore_task结果同形而接收，分组不使用。|
|`binding`|SameFrameBinding|是|无|位置或关键字。父进程同次DBC证明的共同报文定位，用于投影和绑定匹配。|
|`session_id`|str|是|无|位置或关键字。当前会话名，须与表达式声明一致。|
|`derived`|tuple|否|()|仅关键字。derived为派生声明tuple，默认空。|
|`batch_intervals`|int|否|64|仅关键字。definitions、expressions、specs为同序声明tuple，specs、     batch_intervals、domain、step_ns只为与restore_task结果同形而接收，分组不使用它们|
|`domain`|Interval &#124; None|否|None|仅关键字。请求范围；只为同形而接收，分组不按范围裁剪。|
|`step_ns`|int &#124; None|否|None|仅关键字。积分间隔（None为实际间隔，正整数为固定纳秒）；只为同形而接收，分组不使用。|

#### 返回说明

None，构造新的组点owner，不读取原帧。

#### 异常说明

计算项与表达式数量不一致时ValueError；预算不足时BudgetExceededError；
    求值器构造原错误继续传播；构造清理失败附file_group_points_cleanup_owner。

源码：[`src/chronaxis/execution/file_group_points.py:71`](../../../src/chronaxis/execution/file_group_points.py#L71)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-FileGroupPoints-compatibility_fields"></a>
### `FileGroupPoints.compatibility_fields`

借用同次投影记录的FD兼容提示。

```python
FileGroupPoints.compatibility_fields
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

CANField到实际扩展帧标志bool的映射；投影释放后返回空dict。

#### 异常说明

无；调用方不能修改借用的映射。

源码：[`src/chronaxis/execution/file_group_points.py:114`](../../../src/chronaxis/execution/file_group_points.py#L114)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-FileGroupPoints-frame_identity"></a>
### `FileGroupPoints.frame_identity`

返回本文件目标帧实际的（扩展帧, FD）。

```python
FileGroupPoints.frame_identity
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

两个bool的tuple；尚无目标帧或投影已释放时None。

#### 异常说明

无。同一文件内帧型不一致时，投影或读取器已经报错，所以记录到的帧型唯一。

源码：[`src/chronaxis/execution/file_group_points.py:123`](../../../src/chronaxis/execution/file_group_points.py#L123)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-FileGroupPoints-stopped"></a>
### `FileGroupPoints.stopped`

返回本文件是否已停止交付组点。

```python
FileGroupPoints.stopped
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

bool。

#### 异常说明

无。

源码：[`src/chronaxis/execution/file_group_points.py:134`](../../../src/chronaxis/execution/file_group_points.py#L134)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-FileGroupPoints-_require_open"></a>
### `FileGroupPoints._require_open`

拒绝失败、完成或关闭后的推进。

```python
FileGroupPoints._require_open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

ResultClosedError。

源码：[`src/chronaxis/execution/file_group_points.py:138`](../../../src/chronaxis/execution/file_group_points.py#L138)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-FileGroupPoints-_defer"></a>
### `FileGroupPoints._defer`

把可延迟的错误转成事件并停止交付组点。

```python
FileGroupPoints._defer(time_ns, error)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int &#124; None|是|无|位置或关键字。出错帧的实际时间纳秒；为None时不能延迟，原样抛出error。|
|`error`|Exception|是|无|位置或关键字。投影、匹配或归一化抛出的异常，类型须恰为DEFERRED_KINDS之一。|

#### 返回说明

事件tuple：先交付尚未交付的当前组（可能是同一时刻的前缀），再交付DeferredPointError。

#### 异常说明

出错帧没有时间或原文超过256KiB时原样抛出error，由调用方按读取段错误报告。

源码：[`src/chronaxis/execution/file_group_points.py:143`](../../../src/chronaxis/execution/file_group_points.py#L143)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-FileGroupPoints-feed"></a>
### `FileGroupPoints.feed`

消费读取器的一条已解码记录，必要时返回已完成的组点或延迟错误。

```python
FileGroupPoints.feed(record)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`record`|DecodedCANRecord|是|无|位置或关键字。本文件读取器逐条交付的已解码记录。|

#### 返回说明

有界事件tuple，通常为空或含一个上一时刻的组点。

#### 异常说明

不可延迟的错误（时间倒退、无时间记录、预算等）原样传播，标记失败；
    投影、匹配和归一化抛出的四种内建类型错误转成延迟错误事件，不抛出。
停止后只返回空tuple；读取器仍由调用方继续推进到EOF。

源码：[`src/chronaxis/execution/file_group_points.py:158`](../../../src/chronaxis/execution/file_group_points.py#L158)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-FileGroupPoints-finish"></a>
### `FileGroupPoints.finish`

读取器EOF后交付最后一个同一时刻组。

```python
FileGroupPoints.finish()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

事件tuple，最多一个组点；已停止或无目标帧时为空。

#### 异常说明

已关闭、失败或完成时ResultClosedError。

源码：[`src/chronaxis/execution/file_group_points.py:215`](../../../src/chronaxis/execution/file_group_points.py#L215)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-FileGroupPoints-drain_prefix_on_error"></a>
### `FileGroupPoints.drain_prefix_on_error`

读取失败时不交付前缀，与面积生成器接口同名。

```python
FileGroupPoints.drain_prefix_on_error()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

空tuple。读取段错误一律先于归并段，主进程丢弃本次全部组点，前缀没有消费者。

#### 异常说明

已关闭时ResultClosedError。

源码：[`src/chronaxis/execution/file_group_points.py:227`](../../../src/chronaxis/execution/file_group_points.py#L227)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-FileGroupPoints-close"></a>
### `FileGroupPoints.close`

断开当前组、投影和求值器引用并退还费用。

```python
FileGroupPoints.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

退款失败可重试。

源码：[`src/chronaxis/execution/file_group_points.py:238`](../../../src/chronaxis/execution/file_group_points.py#L238)（行号对应 Chronaxis 0.1.0 源码）。
