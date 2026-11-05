# `chronaxis.sources.memory`

把调用者已经提供的内存信号按有限批次交给分析层。

输入是冻结的SourceSpec、当前会话名称和SignalDefinition信号定义。
构造时检查来源归属与字段是否存在；describe只返回这些内存声明。
iter_batches按原行顺序取得已解码值，调用选定的归一化后端，输出SignalBatch。
这里没有日志读取、DBC解码或全历史保持序列的构建。

batch_rows限制所有信号列的样本总数，同一时间的更新可以分在多批。
watermark_ns表示已经完整传送的时间进度：后续不会再出现小于或等于
该坐标的更新。只有看见更晚原行或整个来源结束，才能推进这个承诺。
source_eof只在整个内存来源结束时为True，不把普通分批当作来源结束。

请求时间范围不用于裁剪原行，分析开始前的保持样本仍会传送。
close关闭活动生成器并拒绝后续操作，保留原输入。各次请求的缓冲和
跨批校验状态独立；原输入可以是全量内存数据，有限批次不代表它已释放。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[BatchValidator](chronaxis.sources.protocol.md#api-BatchValidator)、[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)、[SignalBatch](chronaxis.sources.models.md#api-SignalBatch)、[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)、[SourceCapabilities](chronaxis.sources.models.md#api-SourceCapabilities)、[SourceClosedError](chronaxis.sources.protocol.md#api-SourceClosedError)、[SourceDescription](chronaxis.sources.models.md#api-SourceDescription)、[SourceReadError](chronaxis.sources.protocol.md#api-SourceReadError)、[SourceRef](chronaxis.core.models.md#api-SourceRef)、[SourceSpec](chronaxis.core.models.md#api-SourceSpec)

## 对象导航

|对象|用途|
|---|---|
|[`MemorySourceAdapter`](#api-MemorySourceAdapter)|按原顺序传送一个内存来源的已解码字段。|
|[`MemorySourceAdapter.__init__`](#api-MemorySourceAdapter-__init__)|检查内存来源与信号定义，建立实例的读取生命周期。|
|[`MemorySourceAdapter._ensure_open`](#api-MemorySourceAdapter-_ensure_open)|检查生命周期，关闭后连静态describe也不接受。|
|[`MemorySourceAdapter.describe`](#api-MemorySourceAdapter-describe)|返回已有内存声明及字段转换信息，保持未知观测边界。|
|[`MemorySourceAdapter.iter_batches`](#api-MemorySourceAdapter-iter_batches)|为一次读取请求创建独立生成器，并登记其清理责任。|
|[`MemorySourceAdapter.iter_batches.iterate`](#api-MemorySourceAdapter-iter_batches-iterate)|转发本次请求的批次，并在退出时移除活动登记。|
|[`MemorySourceAdapter._iterate`](#api-MemorySourceAdapter-_iterate)|逐行传送更新，完整时间组结束后才推进跨批进度。|
|[`MemorySourceAdapter._make_batch`](#api-MemorySourceAdapter-_make_batch)|将当前缓冲中的已解码原值归一化，生成独立信号列。|
|[`MemorySourceAdapter.close`](#api-MemorySourceAdapter-close)|关闭本实例的全部活动生成器，保留原内存输入。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from collections.abc import Iterator
from ..core.binding import SignalDefinition
from ..core.models import SourceRef, SourceSpec
from ..core.validation import require_identifier
from ..timebase.conversion import checked_add_ns
from .models import ReadRequest, SignalBatch, SourceCapabilities, SourceDescription
from .descriptions import describe_fields, source_timebase_identity
from .packing import pack_decoded
from .protocol import BatchValidator, SourceClosedError, SourceReadError
```

</details>

<a id="api-MemorySourceAdapter"></a>
## `MemorySourceAdapter`

按原顺序传送一个内存来源的已解码字段。

source保存只读原行，session_id标明所属会话，signals保存字段到别名的
显式转换，backend选择reference标量实现或numpy数组实现。
closed记录实例是否关闭，active登记本实例创建的请求生成器。
每次读取另建缓冲和BatchValidator，不继承其他请求的信号值或进度。
本类没有文件句柄；close释放生成器引用，不删除source中的原行。

```python
MemorySourceAdapter(source: SourceSpec, session_id: str, signals: tuple[SignalDefinition, ...], *, backend: str='numpy', clock_only=(), retain_original=True) -> None
```


源码：[`src/chronaxis/sources/memory.py:38`](../../../src/chronaxis/sources/memory.py#L38)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-MemorySourceAdapter-__init__"></a>
### `MemorySourceAdapter.__init__`

检查内存来源与信号定义，建立实例的读取生命周期。

```python
MemorySourceAdapter.__init__(source: SourceSpec, session_id: str, signals: tuple[SignalDefinition, ...], *, backend: str='numpy', clock_only=(), retain_original=True) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|[SourceSpec](chronaxis.core.models.md#api-SourceSpec)|是|无|位置或关键字。已冻结的原行、时钟和偏移声明。|
|`session_id`|str|是|无|位置或关键字。本来源所属的明确会话名称。|
|`signals`|tuple[[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition), ...]|是|无|位置或关键字。仅属于source的信号定义，别名须唯一。|
|`backend`|str|否|'numpy'|仅关键字。`"reference"`使用独立参考计算；`"numpy"`使用NumPy数组计算。须明确选择一种。|
|`clock_only`|tuple[str, ...]|否|()|仅关键字。仅作为时间驱动的信号别名集合；保留真实更新时刻，不解析或构造该信号的数值样本。|
|`retain_original`|bool|否|True|仅关键字。是否保留解析前原始文本；关闭时仍解析并检查输入，只是不保存原文副本。|

#### 返回说明

None。保存输入定义，并初始化关闭状态和活动请求集合。

#### 异常说明

TypeError: 来源或信号容器类型错误，或backend不受支持。
    ValueError: 会话名称非法、信号归属或别名冲突，或非空来源缺少声明字段。

#### 副作用说明

遍历已有原行核对字段；不修改输入，也不预先归一化全部历史。

返回类型：None。

源码：[`src/chronaxis/sources/memory.py:48`](../../../src/chronaxis/sources/memory.py#L48)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-MemorySourceAdapter-_ensure_open"></a>
### `MemorySourceAdapter._ensure_open`

检查生命周期，关闭后连静态describe也不接受。

```python
MemorySourceAdapter._ensure_open() -> None
```

参数：无显式参数。


#### 参数说明

无额外参数；读取closed。

#### 返回说明

None；开放时没有副作用。

#### 异常说明

SourceClosedError包含来源名称。

返回类型：None。

源码：[`src/chronaxis/sources/memory.py:92`](../../../src/chronaxis/sources/memory.py#L92)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-MemorySourceAdapter-describe"></a>
### `MemorySourceAdapter.describe`

返回已有内存声明及字段转换信息，保持未知观测边界。

```python
MemorySourceAdapter.describe() -> SourceDescription
```

参数：无显式参数。


#### 参数说明

无。读取source和signals，不取得新的样本。

#### 返回说明

SourceDescription。明确声明的观测端点加上来源偏移，未知端点保留None；
    metadata_status为'declared'，字段元数据不被自动提升为核实结果。

#### 异常说明

SourceClosedError: 实例已经关闭。
    TypeError或ValueError: 字段描述不符合公共模型要求。
    OverflowError: 端点加偏移后超出整数纳秒范围。

#### 副作用说明

无文件读取，不从投影样本的首末时间猜测完整观测范围。

返回类型：[SourceDescription](chronaxis.sources.models.md#api-SourceDescription)。

源码：[`src/chronaxis/sources/memory.py:104`](../../../src/chronaxis/sources/memory.py#L104)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-MemorySourceAdapter-iter_batches"></a>
### `MemorySourceAdapter.iter_batches`

为一次读取请求创建独立生成器，并登记其清理责任。

```python
MemorySourceAdapter.iter_batches(request: ReadRequest) -> Iterator[SignalBatch]
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`request`|[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)|是|无|位置或关键字。当前会话、请求信号别名、分析范围及batch_rows上限。|

#### 返回说明

Iterator[SignalBatch]。每批所有列的样本总数不超过batch_rows；
    最后一批标记整个来源结束，允许没有样本。

#### 异常说明

SourceClosedError: 实例已经关闭。
    ValueError: 请求类型或会话不符，或请求了描述中没有的别名。
    SourceReadError: 实际迭代时读取或批次校验失败，原异常保存在异常链中。

#### 副作用说明

立即检查请求并登记生成器；取得样本的工作在迭代时执行。

返回类型：Iterator[[SignalBatch](chronaxis.sources.models.md#api-SignalBatch)]。

源码：[`src/chronaxis/sources/memory.py:133`](../../../src/chronaxis/sources/memory.py#L133)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-MemorySourceAdapter-iter_batches-iterate"></a>
### `MemorySourceAdapter.iter_batches.iterate`

转发本次请求的批次，并在退出时移除活动登记。

```python
MemorySourceAdapter.iter_batches.iterate() -> Iterator[SignalBatch]
```

参数：无显式参数。


#### 参数说明

无。闭包使用本次request、validator及iterator引用。

#### 返回说明

每次产生一个SignalBatch，顺序和进度与内部生成器一致。

#### 异常说明

内部读取或协议发生异常时直接交给调用者处理；finally仅移除本请求的登记。

返回类型：Iterator[[SignalBatch](chronaxis.sources.models.md#api-SignalBatch)]。

源码：[`src/chronaxis/sources/memory.py:157`](../../../src/chronaxis/sources/memory.py#L157)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-MemorySourceAdapter-_iterate"></a>
### `MemorySourceAdapter._iterate`

逐行传送更新，完整时间组结束后才推进跨批进度。

```python
MemorySourceAdapter._iterate(request: ReadRequest, validator: BatchValidator) -> Iterator[SignalBatch]
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`request`|[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)|是|无|位置或关键字。本次请求；signal_names确定列顺序和样本计数。|
|`validator`|[BatchValidator](chronaxis.sources.protocol.md#api-BatchValidator)|是|无|位置或关键字。本请求独立的来源、身份和进度校验状态。|

#### 返回说明

每次产生SignalBatch；最后一批source_eof为True。

#### 异常说明

SourceReadError: 转换、生命周期或协议校验失败，保留来源名和原异常链。

#### 处理流程说明

按原行加偏移后收集请求字段，缓冲满时先发布已有样本。
    字段未出现在原行中表示没有更新；显式None则是覆盖旧值的缺失更新。
    更晚原行证明上一时间组完整，整个来源耗尽后确认最后一组。
    退出时清空本次缓冲，不修改输入或已经返回的独立数组。

返回类型：Iterator[[SignalBatch](chronaxis.sources.models.md#api-SignalBatch)]。

源码：[`src/chronaxis/sources/memory.py:181`](../../../src/chronaxis/sources/memory.py#L181)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-MemorySourceAdapter-_make_batch"></a>
### `MemorySourceAdapter._make_batch`

将当前缓冲中的已解码原值归一化，生成独立信号列。

```python
MemorySourceAdapter._make_batch(pending, watermark: int | None, eof: bool, observed_end: int | None) -> SignalBatch
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`pending`|dict|是|无|位置或关键字。别名对应的(time_ns, sequence, 原值)记录列表。|
|`watermark`|int &#124; None|是|无|位置或关键字。已完整传送的时间组坐标，单位为纳秒。|
|`eof`|bool|是|无|位置或关键字。是否已经耗尽整个配置来源。|
|`observed_end`|int &#124; None|是|无|位置或关键字。已知观测终点，单位为纳秒；未知时为None。|

#### 返回说明

SignalBatch。各列保留本会话、来源及原字段引用；转换对每值应用一次。

#### 异常说明

TypeError、ValueError或OverflowError: 归一化或列模型校验失败。

#### 副作用说明

分配独立数组，不保留上一批的值，也不修改原行。

返回类型：[SignalBatch](chronaxis.sources.models.md#api-SignalBatch)。

源码：[`src/chronaxis/sources/memory.py:253`](../../../src/chronaxis/sources/memory.py#L253)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-MemorySourceAdapter-close"></a>
### `MemorySourceAdapter.close`

关闭本实例的全部活动生成器，保留原内存输入。

```python
MemorySourceAdapter.close() -> None
```

参数：无显式参数。


#### 参数说明

无。使用closed状态和active生成器集合。

#### 返回说明

None。重复调用直接返回；后续描述和读取操作被拒绝。

#### 异常说明

活动生成器的清理异常会传播。

#### 副作用说明

先标记关闭，再关闭活动生成器并清空登记；没有文件删除操作。

返回类型：None。

源码：[`src/chronaxis/sources/memory.py:276`](../../../src/chronaxis/sources/memory.py#L276)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
