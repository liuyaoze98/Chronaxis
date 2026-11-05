# `chronaxis.execution.memory_reader`

在既有内存适配器之外预留输入、批次与协议状态预算。

输入SourceSpec本来已完整存在于调用方内存；封装构造前核算它和信号声明，
不声称控制过去的分配或全进程RSS。输出为既有适配器实际SignalBatch，
归一化次数、backend、分批、原顺序、watermark/EOF和异常原因不改变。
每请求预留最坏两个交接批次及来源pending状态，再创建/推进内部生成器；
NumPy字符串按最大原宽度×N核算Unicode数组/临时副本，不能只计原字符串总长。
超限明确失败，不偷偷减小batch_rows、切换后端或丢样本。所有预算至EOF/close释放，
外部长期保存owned批次不在本封装内部预算保证内；不读取CSV、旧日志或DBC。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[MemorySourceAdapter](chronaxis.sources.memory.md#api-MemorySourceAdapter)、[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)、[SignalBatch](chronaxis.sources.models.md#api-SignalBatch)、[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)、[SourceClosedError](chronaxis.sources.protocol.md#api-SourceClosedError)、[SourceDescription](chronaxis.sources.models.md#api-SourceDescription)、[SourceSpec](chronaxis.core.models.md#api-SourceSpec)

## 对象导航

|对象|用途|
|---|---|
|[`BudgetedMemorySourceAdapter`](#api-BudgetedMemorySourceAdapter)|共享一个输入预留，为各读取请求保留独立批次/协议最坏预算。|
|[`BudgetedMemorySourceAdapter.__init__`](#api-BudgetedMemorySourceAdapter-__init__)|核算已有完整输入后建立原适配器，不提前生成数组。|
|[`BudgetedMemorySourceAdapter._ensure_open`](#api-BudgetedMemorySourceAdapter-_ensure_open)|拒绝已关闭来源，不以空批掩盖错误。|
|[`BudgetedMemorySourceAdapter.describe`](#api-BudgetedMemorySourceAdapter-describe)|直接返回原适配器静态描述，不提升来源能力或观测证据状态。|
|[`BudgetedMemorySourceAdapter._request_cost`](#api-BudgetedMemorySourceAdapter-_request_cost)|计算一个读取请求在全部next期间持有的最坏预留。|
|[`BudgetedMemorySourceAdapter.iter_batches`](#api-BudgetedMemorySourceAdapter-iter_batches)|预留整次请求的最坏缓冲/状态，再创建实际批次生成器。|
|[`BudgetedMemorySourceAdapter.close`](#api-BudgetedMemorySourceAdapter-close)|关闭所有请求及原适配器，释放本封装预留并保留调用方原输入。|
|[`_BudgetedBatches`](#api-_BudgetedBatches)|持有一请求的预留/原生成器/当前批，EOF或close时抵销一次预留。|
|[`_BudgetedBatches.__init__`](#api-_BudgetedBatches-__init__)|先申请再创建原请求，构造失败不保留请求状态。|
|[`_BudgetedBatches.__iter__`](#api-_BudgetedBatches-__iter__)|返回本独立游标。|
|[`_BudgetedBatches.__next__`](#api-_BudgetedBatches-__next__)|在整次预留覆盖下推进原适配器，不重复归一化或改进度。|
|[`_BudgetedBatches.close`](#api-_BudgetedBatches-close)|关闭本请求原生成器，释放当前批引用和最坏预留，其他请求保持独立。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from collections.abc import Iterator
from ..core.binding import SignalDefinition
from ..core.models import SourceSpec
from ..results.budget import ResourceBudget
from ..results.spool import _cleanup_owner, _reserve_owned_ram, _release_owned_ram
from ..sources.memory import MemorySourceAdapter
from ..sources.models import ReadRequest, SignalBatch, SourceDescription
from ..sources.protocol import SourceClosedError
from .history import _metadata_bytes
```

</details>

<a id="api-BudgetedMemorySourceAdapter"></a>
## `BudgetedMemorySourceAdapter`

共享一个输入预留，为各读取请求保留独立批次/协议最坏预算。

adapter只在预留成功后建立；info存每别名实际投影总数与最大原字符串字符数。
active登记活动请求，close尝试关闭全部并释放输入引用，原SourceSpec不修改。
_uninstalled_read保构造或登记未返回的真实请求；_closing先拒绝新读，closed仅在
所有子请求、原适配器及本层_input_cost实际释放后成立。

```python
BudgetedMemorySourceAdapter(budget: ResourceBudget, source: SourceSpec, session_id: str, signals: tuple[SignalDefinition, ...], *, backend: str='numpy', clock_only=(), retain_original=True)
```


源码：[`src/chronaxis/execution/memory_reader.py:24`](../../../src/chronaxis/execution/memory_reader.py#L24)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BudgetedMemorySourceAdapter-__init__"></a>
### `BudgetedMemorySourceAdapter.__init__`

核算已有完整输入后建立原适配器，不提前生成数组。

```python
BudgetedMemorySourceAdapter.__init__(budget: ResourceBudget, source: SourceSpec, session_id: str, signals: tuple[SignalDefinition, ...], *, backend: str='numpy', clock_only=(), retain_original=True)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)|是|无|位置或关键字。本次运行共用的ResourceBudget对象，用于检查内存和临时磁盘用量。当前对象在分配前申请额度，用完后归还；同一次运行的组件应使用同一个对象。|
|`source`|[SourceSpec](chronaxis.core.models.md#api-SourceSpec)|是|无|位置或关键字。内存来源声明，包含可控样本行及时间基准。|
|`session_id`|str|是|无|位置或关键字。本次会话的名字，用来防止把不同试验的数据混在一起。|
|`signals`|tuple[[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition), ...]|是|无|位置或关键字。该来源需要输出的信号定义，按别名、原字段和类型解释样本。|
|`backend`|str|否|'numpy'|仅关键字。`"reference"`使用独立参考计算；`"numpy"`使用NumPy数组计算。须明确选择一种。|
|`clock_only`|tuple[str, ...]|否|()|仅关键字。仅作为时间驱动的信号别名集合；保留真实更新时刻，不解析或构造该信号的数值样本。|
|`retain_original`|bool|否|True|仅关键字。是否保留解析前原始文本；关闭时仍解析并检查输入，只是不保存原文副本。|

#### 返回说明

新封装。

#### 异常说明

配置/预算/原适配器初始化原错；持续清理失败附
    memory_source_cleanup_owner，恢复后从该真实owner重试close。

源码：[`src/chronaxis/execution/memory_reader.py:33`](../../../src/chronaxis/execution/memory_reader.py#L33)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BudgetedMemorySourceAdapter-_ensure_open"></a>
### `BudgetedMemorySourceAdapter._ensure_open`

拒绝已关闭来源，不以空批掩盖错误。

```python
BudgetedMemorySourceAdapter._ensure_open() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

SourceClosedError为已关闭。

本函数直接报告的具体错误：

- `SourceClosedError`：预算内存来源已关闭或正在清理。

返回类型：None。

源码：[`src/chronaxis/execution/memory_reader.py:70`](../../../src/chronaxis/execution/memory_reader.py#L70)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BudgetedMemorySourceAdapter-describe"></a>
### `BudgetedMemorySourceAdapter.describe`

直接返回原适配器静态描述，不提升来源能力或观测证据状态。

```python
BudgetedMemorySourceAdapter.describe() -> SourceDescription
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

SourceDescription。

#### 异常说明

关闭/原描述错误传播。

返回类型：[SourceDescription](chronaxis.sources.models.md#api-SourceDescription)。

源码：[`src/chronaxis/execution/memory_reader.py:78`](../../../src/chronaxis/execution/memory_reader.py#L78)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BudgetedMemorySourceAdapter-_request_cost"></a>
### `BudgetedMemorySourceAdapter._request_cost`

计算一个读取请求在全部next期间持有的最坏预留。

```python
BudgetedMemorySourceAdapter._request_cost(request: ReadRequest) -> int
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`request`|[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)|是|无|位置或关键字。request为当前会话/投影/批次上限。|

#### 返回说明

保守bytes，非RSS。

#### 异常说明

ValueError为请求会话/别名错误，其他预算错误由申请点报告。

本函数直接报告的具体错误：

- `ValueError`：预算内存来源请求会话/投影错误。

返回类型：int。

源码：[`src/chronaxis/execution/memory_reader.py:86`](../../../src/chronaxis/execution/memory_reader.py#L86)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BudgetedMemorySourceAdapter-iter_batches"></a>
### `BudgetedMemorySourceAdapter.iter_batches`

预留整次请求的最坏缓冲/状态，再创建实际批次生成器。

```python
BudgetedMemorySourceAdapter.iter_batches(request: ReadRequest) -> Iterator[SignalBatch]
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`request`|[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)|是|无|位置或关键字。request为既有读取请求，不改变batch_rows。|

#### 返回说明

独立预算游标。

#### 异常说明

请求/预算/原来源错误传播；超限在数组归一化之前失败，持续清理
    失败附memory_read_cleanup_owner，来源也保留未返回read槽。

返回类型：Iterator[[SignalBatch](chronaxis.sources.models.md#api-SignalBatch)]。

源码：[`src/chronaxis/execution/memory_reader.py:107`](../../../src/chronaxis/execution/memory_reader.py#L107)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BudgetedMemorySourceAdapter-close"></a>
### `BudgetedMemorySourceAdapter.close`

关闭所有请求及原适配器，释放本封装预留并保留调用方原输入。

```python
BudgetedMemorySourceAdapter.close() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None。关闭成功后再次调用不会重复释放同一份资源。

#### 异常说明

首个原关闭错误附memory_source_cleanup_owner；
    其他独立read也尝试关闭，子责任未完成时保留来源合同与全部未释放槽。

返回类型：None。

源码：[`src/chronaxis/execution/memory_reader.py:133`](../../../src/chronaxis/execution/memory_reader.py#L133)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_BudgetedBatches"></a>
## `_BudgetedBatches`

持有一请求的预留/原生成器/当前批，EOF或close时抵销一次预留。

```python
_BudgetedBatches(owner: BudgetedMemorySourceAdapter, request: ReadRequest, cost: int)
```


源码：[`src/chronaxis/execution/memory_reader.py:173`](../../../src/chronaxis/execution/memory_reader.py#L173)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_BudgetedBatches-__init__"></a>
### `_BudgetedBatches.__init__`

先申请再创建原请求，构造失败不保留请求状态。

```python
_BudgetedBatches.__init__(owner: BudgetedMemorySourceAdapter, request: ReadRequest, cost: int)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|[BudgetedMemorySourceAdapter](chronaxis.execution.memory_reader.md#api-BudgetedMemorySourceAdapter)|是|无|位置或关键字。owner为预算来源|
|`request`|[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)|是|无|位置或关键字。request为原请求|
|`cost`|int|是|无|位置或关键字。cost为最坏预留。|

#### 返回说明

独立游标。

#### 异常说明

预算或原请求初始化原错，持续清理失败附memory_read_cleanup_owner；
    未实际入账不抵销，返回途中取消仍登记原cost槽。

源码：[`src/chronaxis/execution/memory_reader.py:176`](../../../src/chronaxis/execution/memory_reader.py#L176)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_BudgetedBatches-__iter__"></a>
### `_BudgetedBatches.__iter__`

返回本独立游标。

```python
_BudgetedBatches.__iter__() -> '_BudgetedBatches'
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回当前对象本身。后续迭代或with语句使用的仍是同一个对象。

#### 异常说明

无。

返回类型：'[_BudgetedBatches](chronaxis.execution.memory_reader.md#api-_BudgetedBatches)'。

源码：[`src/chronaxis/execution/memory_reader.py:195`](../../../src/chronaxis/execution/memory_reader.py#L195)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_BudgetedBatches-__next__"></a>
### `_BudgetedBatches.__next__`

在整次预留覆盖下推进原适配器，不重复归一化或改进度。

```python
_BudgetedBatches.__next__() -> SignalBatch
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

原适配器实际批次。

#### 异常说明

EOF/关闭/原来源错误，故障清理保留根因。

本函数直接报告的具体错误：

- `SourceClosedError`：预算内存请求正在清理。

返回类型：[SignalBatch](chronaxis.sources.models.md#api-SignalBatch)。

源码：[`src/chronaxis/execution/memory_reader.py:202`](../../../src/chronaxis/execution/memory_reader.py#L202)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_BudgetedBatches-close"></a>
### `_BudgetedBatches.close`

关闭本请求原生成器，释放当前批引用和最坏预留，其他请求保持独立。

```python
_BudgetedBatches.close() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None。关闭成功后再次调用不会重复释放同一份资源。

#### 异常说明

原生成器或释放错误附memory_read_cleanup_owner；
    原生成器未成功关闭时保留原对象和费用，其他请求保持独立。

返回类型：None。

源码：[`src/chronaxis/execution/memory_reader.py:223`](../../../src/chronaxis/execution/memory_reader.py#L223)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
