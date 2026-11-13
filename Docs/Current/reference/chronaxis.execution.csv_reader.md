# `chronaxis.execution.csv_reader`

在独立信号CSV读取、引用记录累积和数组分配前申请共享预算。

输入沿用SignalCSVSpec、声明及ReadRequest；输出沿用原SignalBatch和CSVSourceRef。
原csv.reader、解析和文件顺序保持；批次达到样本上限或剩余容量前交付。
物理行readline限制按当时剩余RAM计算，跨物理行的引用记录保守累计，超限失败。
原样本/ref、定宽Unicode提升、owned数组交接与协议pending副本分别计账。
close释放本来源/请求引用和预算，文件保留；不是全进程RSS或外部保留全部输出保证。
默认请求各自保存真实生成器、FD与用途费用槽，关闭取消后保留尚未完成的责任；
未返回构造以csv_source_cleanup_owner、csv_request_cleanup_owner或csv_resources_cleanup_owner恢复。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[BudgetExceededError](chronaxis.results.errors.md#api-BudgetExceededError)、[CSVObservationRead](chronaxis.execution.csv_observation.md#api-CSVObservationRead)、[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)、[SignalBatch](chronaxis.sources.models.md#api-SignalBatch)、[SignalCSVSourceAdapter](chronaxis.sources.signal_csv.md#api-SignalCSVSourceAdapter)、[SignalCSVSpec](chronaxis.sources.csv_spec.md#api-SignalCSVSpec)、[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)、[SourceClosedError](chronaxis.sources.protocol.md#api-SourceClosedError)、[SourceReadError](chronaxis.sources.protocol.md#api-SourceReadError)

## 对象导航

|对象|用途|
|---|---|
|[`_expanded_integer_bytes`](#api-_expanded_integer_bytes)|按十进制文本估算整数展开空间，不重复执行 Decimal 或实际整数转换。|
|[`BudgetedSignalCSVSourceAdapter`](#api-BudgetedSignalCSVSourceAdapter)|为各请求独立持有检查器，固定声明一次计账，关闭不删除输入。|
|[`BudgetedSignalCSVSourceAdapter.__init__`](#api-BudgetedSignalCSVSourceAdapter-__init__)|先计声明，再建立不读取文件的原CSV适配器。|
|[`BudgetedSignalCSVSourceAdapter.iter_batches`](#api-BudgetedSignalCSVSourceAdapter-iter_batches)|预留请求/validator固定结构，再建立原参数生成器。|
|[`BudgetedSignalCSVSourceAdapter.iter_batches_with_observation`](#api-BudgetedSignalCSVSourceAdapter-iter_batches_with_observation)|创建本次独立读取owner，完整耗尽并清理成功后才开放原时间行观测事实。|
|[`BudgetedSignalCSVSourceAdapter._ensure_open`](#api-BudgetedSignalCSVSourceAdapter-_ensure_open)|在固定声明已释放后仍抛明确关闭错误，不访问已丢弃spec。|
|[`BudgetedSignalCSVSourceAdapter._read_resources`](#api-BudgetedSignalCSVSourceAdapter-_read_resources)|在原迭代器实际打开文件前建立独立资源检查器。|
|[`BudgetedSignalCSVSourceAdapter._close_handle`](#api-BudgetedSignalCSVSourceAdapter-_close_handle)|仅在真实FD关闭后移除登记，业务根因不被附加清理错误覆盖。|
|[`BudgetedSignalCSVSourceAdapter.close`](#api-BudgetedSignalCSVSourceAdapter-close)|关闭全部包装请求、原句柄与检查器，最后抵销固定声明预算。|
|[`_CSVRequest`](#api-_CSVRequest)|拥有默认原生成器、真实FD和资源检查器，半关闭需要重试close来完成关闭。|
|[`_CSVRequest.__init__`](#api-_CSVRequest-__init__)|先预约原固定请求费用，再接住原生成器，未返回失败保实际恢复owner。|
|[`_CSVRequest._adopt_cleanup`](#api-_CSVRequest-_adopt_cleanup)|接住本次尚未返回的检查器，不接他请求或借用来源。|
|[`_CSVRequest._created_iterator`](#api-_CSVRequest-_created_iterator)|在原活动登记前接住同一个实际生成器。|
|[`_CSVRequest._read_resources`](#api-_CSVRequest-_read_resources)|建立本请求唯一检查器，登记前失败仍由本请求保留责任。|
|[`_CSVRequest._opened_handle`](#api-_CSVRequest-_opened_handle)|在原handles集合登记前接住真实只读FD。|
|[`_CSVRequest._close_handle`](#api-_CSVRequest-_close_handle)|执行原文件关闭责任，失败时保持本请求的实际FD引用。|
|[`_CSVRequest._end_file`](#api-_CSVRequest-_end_file)|抵销文件局部费用，已有业务原错或取消不被附加释放错误取代。|
|[`_CSVRequest._close_resources`](#api-_CSVRequest-_close_resources)|仅在真实FD已关闭后清理本请求检查器，保留原主异常。|
|[`_CSVRequest.__iter__`](#api-_CSVRequest-__iter__)|返回自有游标。|
|[`_CSVRequest.__next__`](#api-_CSVRequest-__next__)|推进原生成器，失败/EOF只清自有资源并保留原异常和最高恢复owner。|
|[`_CSVRequest.close`](#api-_CSVRequest-close)|依次关闭真实生成器/FD/检查器，最后抵销固定费用，成功后才closed。|
|[`_CSVResources`](#api-_CSVResources)|每请求按用途保存金额，固定读取缓冲、行/ref、数组和协议状态共同计账。|
|[`_CSVResources.__init__`](#api-_CSVResources-__init__)|预留文件解码缓冲及资源容器，不在申请前打开文件。|
|[`_CSVResources._sync`](#api-_CSVResources-_sync)|把真实付款槽同步到兼容charges视图，不从视图反推所有权。|
|[`_CSVResources._add`](#api-_CSVResources-_add)|事务式登记一次真实预约，未入账超限不增加自有金额。|
|[`_CSVResources._release_amount`](#api-_CSVResources-_release_amount)|只抵销本用途真实费用，释放前后取消均保留正确槽位。|
|[`_CSVResources._move`](#api-_CSVResources-_move)|转移已付款责任槽，总费用不变，不申请或归还共享余额。|
|[`_CSVResources._release`](#api-_CSVResources-_release)|抵销某用途全部预留。|
|[`_CSVResources.lines`](#api-_CSVResources-lines)|把真实TextIO交给限长物理行迭代器，不自己解释CSV。|
|[`_CSVResources.records`](#api-_CSVResources-records)|保持原reader的物理计数和解释，为表头/当前逻辑记录保存累积预算。|
|[`_CSVResources._sample_estimate`](#api-_CSVResources-_sample_estimate)|估算新记录独有的容器、数值和文本，不重复计算来源路径或声明。|
|[`_CSVResources._pack_estimate`](#api-_CSVResources-_pack_estimate)|分别计算最终列、归一化工作区和跨批同一时刻检查状态的峰值。|
|[`_CSVResources.should_flush`](#api-_CSVResources-should_flush)|在再接收一条样本之前判断是否应先交付当前批。|
|[`_CSVResources.before_sample`](#api-_CSVResources-before_sample)|在值解析及原记录 append 前预留记录独有的数据。|
|[`_CSVResources.before_pack`](#api-_CSVResources-before_pack)|在创建数组前预留实际候选批的峰值，不按最大批大小预先拒绝。|
|[`_CSVResources.after_pack`](#api-_CSVResources-after_pack)|校验完成后把工作预留转为当前owned数组和保留协议状态。|
|[`_CSVResources.clear_pending`](#api-_CSVResources-clear_pending)|原生成器恢复并清空缓冲后重置计数，不重复抵销已转交的共享费用。|
|[`_CSVResources.end_file`](#api-_CSVResources-end_file)|局部行/表头引用丢弃后抵销预算，跨文件样本与协议预算保留。|
|[`_CSVResources.close`](#api-_CSVResources-close)|释放本请求全部金额，不关闭他请求或删除输入文件。|
|[`_PhysicalLines`](#api-_PhysicalLines)|每次readline前按剩余RAM申请上限；引用记录跨行继续累积reading金额。|
|[`_PhysicalLines.__init__`](#api-_PhysicalLines-__init__)|保存真实只读句柄。|
|[`_PhysicalLines.__iter__`](#api-_PhysicalLines-__iter__)|返回物理行游标。|
|[`_PhysicalLines._retained_line_bytes`](#api-_PhysicalLines-_retained_line_bytes)|计算当前逻辑记录仍需保存的解析字符和字段开销。|
|[`_PhysicalLines.__next__`](#api-_PhysicalLines-__next__)|有界读完整物理行，超限不把截断内容交给csv.reader。|
|[`_CSVRecords`](#api-_CSVRecords)|包装原csv.reader，表头固定持有，当前/下一逻辑记录读取时预算重叠。|
|[`_CSVRecords.__init__`](#api-_CSVRecords-__init__)|保存原解析器。|
|[`_CSVRecords.__iter__`](#api-_CSVRecords-__iter__)|返回记录游标。|
|[`_CSVRecords.__next__`](#api-_CSVRecords-__next__)|推进原解析器，跨物理行累积到一条完整记录再转移预算。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from collections.abc import Iterator
from sys import getsizeof, int_info
from ..results.budget import ResourceBudget
from ..results.errors import BudgetExceededError
from ..results.spool import _cleanup_owner, _reserve_owned_ram, _release_owned_ram
from ..sources.signal_csv import SignalCSVSourceAdapter
from ..sources.protocol import SourceClosedError, SourceReadError
from ..sources.models import ReadRequest, SignalBatch
from ..sources.csv_spec import SignalCSVSpec
from ..core.binding import SignalDefinition
from .history import _metadata_bytes
```

</details>

<a id="api-_expanded_integer_bytes"></a>
## `_expanded_integer_bytes`

按十进制文本估算整数展开空间，不重复执行 Decimal 或实际整数转换。

```python
_expanded_integer_bytes(text)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`text`|str|是|无|位置或关键字。原单元格文本；只据长度和指数估算整数空间，不将估算当成数值校验。|

### 返回说明

最多 4096 位十进制整数所需的字节上界。

### 异常说明

不把坏文本提前当成合法数值；语法和指数边界仍由原解析器拒绝。

源码：[`src/chronaxis/execution/csv_reader.py:26`](../../../src/chronaxis/execution/csv_reader.py#L26)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-BudgetedSignalCSVSourceAdapter"></a>
## `BudgetedSignalCSVSourceAdapter`

为各请求独立持有检查器，固定声明一次计账，关闭不删除输入。

_held_cost只含本来源_input_cost；请求与资源各自拥有自己的费用。
_closing拒绝继续读取，只有真实子资源及固定槽均已清完才closed。
未安装请求和检查器保留在明确字段，不借共享余额差额补账。

```python
BudgetedSignalCSVSourceAdapter(budget: ResourceBudget, spec: SignalCSVSpec, session_id: str, signals: tuple[SignalDefinition, ...], *, backend: str='numpy', clock_only=(), retain_original=True, consumer_sample_bytes=0)
```

继承关系：[SignalCSVSourceAdapter](chronaxis.sources.signal_csv.md#api-SignalCSVSourceAdapter)。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/execution/csv_reader.py:50`](../../../src/chronaxis/execution/csv_reader.py#L50)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-BudgetedSignalCSVSourceAdapter-__init__"></a>
### `BudgetedSignalCSVSourceAdapter.__init__`

先计声明，再建立不读取文件的原CSV适配器。

```python
BudgetedSignalCSVSourceAdapter.__init__(budget: ResourceBudget, spec: SignalCSVSpec, session_id: str, signals: tuple[SignalDefinition, ...], *, backend: str='numpy', clock_only=(), retain_original=True, consumer_sample_bytes=0)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)|是|无|位置或关键字。本次运行共用的ResourceBudget对象，用于检查内存和临时磁盘用量。当前对象在分配前申请额度，用完后归还；同一次运行的组件应使用同一个对象。|
|`spec`|[SignalCSVSpec](chronaxis.sources.csv_spec.md#api-SignalCSVSpec)|是|无|位置或关键字。SignalCSVSpec，包含有序路径、时间列、单位、编码、分隔符和缺失标记。|
|`session_id`|str|是|无|位置或关键字。本次会话的名字，用来防止把不同试验的数据混在一起。|
|`signals`|tuple[[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition), ...]|是|无|位置或关键字。当前任务的信号定义/名称集合，见对应调用接口；不装入实际样本。|
|`backend`|str|否|'numpy'|仅关键字。`"reference"`使用独立参考计算；`"numpy"`使用NumPy数组计算。须明确选择一种。|
|`clock_only`|tuple[str, ...]|否|()|仅关键字。仅作为时间驱动的信号别名集合；保留真实更新时刻，不解析或构造该信号的数值样本。|
|`retain_original`|bool|否|True|仅关键字。是否保留解析前原始文本；关闭时仍解析并检查输入，只是不保存原文副本。|
|`consumer_sample_bytes`|int|否|0|仅关键字。retain_original=False省去逐行原文引用，默认保留旧入口行为。     consumer_sample_bytes为接收方每样本最坏排队费用，只用于容量协调，不重复预约。|

#### 返回说明

新预算CSV来源。

#### 异常说明

类型/配置/预算失败；持续清理失败附csv_source_cleanup_owner。

本函数直接报告的具体错误：

- `TypeError`：预算CSV需要ResourceBudget/SignalCSVSpec/信号tuple。

源码：[`src/chronaxis/execution/csv_reader.py:58`](../../../src/chronaxis/execution/csv_reader.py#L58)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-BudgetedSignalCSVSourceAdapter-iter_batches"></a>
### `BudgetedSignalCSVSourceAdapter.iter_batches`

预留请求/validator固定结构，再建立原参数生成器。

```python
BudgetedSignalCSVSourceAdapter.iter_batches(request: ReadRequest, *, observe_bounds=False) -> Iterator[SignalBatch]
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`request`|[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)|是|无|位置或关键字。request为ReadRequest，投影/会话由原入口验证|
|`observe_bounds`|bool|否|False|仅关键字。是否收集整个来源的实际观测起止；无信号的常量条件等消费者需要时才开启。|

#### 返回说明

独立预算游标，不生成额外观测报告。

#### 异常说明

关闭/配置/预算/读取错误传播；未返回请求持续清理失败保最高恢复owner，
    无自动后端回退或批次缩小。

本函数直接报告的具体错误：

- `SourceClosedError`：预算CSV来源尚有未返回请求或资源待清理。

返回类型：Iterator[[SignalBatch](chronaxis.sources.models.md#api-SignalBatch)]。

源码：[`src/chronaxis/execution/csv_reader.py:94`](../../../src/chronaxis/execution/csv_reader.py#L94)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-BudgetedSignalCSVSourceAdapter-iter_batches_with_observation"></a>
### `BudgetedSignalCSVSourceAdapter.iter_batches_with_observation`

创建本次独立读取owner，完整耗尽并清理成功后才开放原时间行观测事实。

```python
BudgetedSignalCSVSourceAdapter.iter_batches_with_observation(request: ReadRequest)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`request`|[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)|是|无|位置或关键字。request为原ReadRequest，不改变会话、投影、范围或batch_rows。|

#### 返回说明

CSVObservationRead；迭代交付原SignalBatch，真正StopIteration后
    observation给出本read独立的首末时间、原行数、请求及读取身份。

#### 异常说明

原配置、预算、读取或取消错误；持续构造清理失败时从原异常的
    csv_observation_read_cleanup_owner恢复close。

#### 副作用说明

增加本read自有固定预算，默认iter_batches不启用此采集。

源码：[`src/chronaxis/execution/csv_reader.py:124`](../../../src/chronaxis/execution/csv_reader.py#L124)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-BudgetedSignalCSVSourceAdapter-_ensure_open"></a>
### `BudgetedSignalCSVSourceAdapter._ensure_open`

在固定声明已释放后仍抛明确关闭错误，不访问已丢弃spec。

```python
BudgetedSignalCSVSourceAdapter._ensure_open() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

SourceClosedError为来源已关闭。

本函数直接报告的具体错误：

- `SourceClosedError`：预算CSV来源已关闭。

返回类型：None。

源码：[`src/chronaxis/execution/csv_reader.py:152`](../../../src/chronaxis/execution/csv_reader.py#L152)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-BudgetedSignalCSVSourceAdapter-_read_resources"></a>
### `BudgetedSignalCSVSourceAdapter._read_resources`

在原迭代器实际打开文件前建立独立资源检查器。

```python
BudgetedSignalCSVSourceAdapter._read_resources(request: ReadRequest) -> '_CSVResources'
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`request`|[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)|是|无|位置或关键字。request为已校验请求。|

#### 返回说明

_CSVResources。

#### 异常说明

固定预算不足或登记失败；持续清理失败保实际检查器及最高来源恢复owner。

本函数直接报告的具体错误：

- `SourceClosedError`：预算CSV来源尚有未返回资源待清理。

返回类型：'[_CSVResources](chronaxis.execution.csv_reader.md#api-_CSVResources)'。

源码：[`src/chronaxis/execution/csv_reader.py:160`](../../../src/chronaxis/execution/csv_reader.py#L160)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-BudgetedSignalCSVSourceAdapter-_close_handle"></a>
### `BudgetedSignalCSVSourceAdapter._close_handle`

仅在真实FD关闭后移除登记，业务根因不被附加清理错误覆盖。

```python
BudgetedSignalCSVSourceAdapter._close_handle(handle, primary)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`handle`|TextIO|是|无|位置或关键字。本次输入文件已经打开的文本读取对象；用于逐行读取或关闭，不传文件名字符串。|
|`primary`|BaseException|是|无|位置或关键字。本次操作的原异常，供附加关闭失败信息并保留原因链。不要用错误字符串代替异常对象。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

无主错或GeneratorExit时原关闭错误传播；其他主错只增加note。

源码：[`src/chronaxis/execution/csv_reader.py:184`](../../../src/chronaxis/execution/csv_reader.py#L184)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-BudgetedSignalCSVSourceAdapter-close"></a>
### `BudgetedSignalCSVSourceAdapter.close`

关闭全部包装请求、原句柄与检查器，最后抵销固定声明预算。

```python
BudgetedSignalCSVSourceAdapter.close() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None。关闭成功后再次调用不会重复释放同一份资源。

#### 异常说明

首个关闭错误，仍尝试其他独立请求；
    尚未结束的子责任及费用保留，恢复后可重复close。

返回类型：None。

源码：[`src/chronaxis/execution/csv_reader.py:200`](../../../src/chronaxis/execution/csv_reader.py#L200)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_CSVRequest"></a>
## `_CSVRequest`

拥有默认原生成器、真实FD和资源检查器，半关闭需要重试close来完成关闭。

```python
_CSVRequest(owner, request, *, observe_bounds=False)
```


源码：[`src/chronaxis/execution/csv_reader.py:274`](../../../src/chronaxis/execution/csv_reader.py#L274)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_CSVRequest-__init__"></a>
### `_CSVRequest.__init__`

先预约原固定请求费用，再接住原生成器，未返回失败保实际恢复owner。

```python
_CSVRequest.__init__(owner, request, *, observe_bounds=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|[BudgetedSignalCSVSourceAdapter](chronaxis.execution.csv_reader.md#api-BudgetedSignalCSVSourceAdapter)|是|无|位置或关键字。创建此请求的CSV适配器，负责资源预约和关闭请求。|
|`request`|[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)|是|无|位置或关键字。需要读取的信号、时间范围及批次大小，沿用来源接口的读取请求。|
|`observe_bounds`|bool|否|False|仅关键字。是否收集整个来源的实际观测起止；无信号的常量条件等消费者需要时才开启。|

#### 返回说明

独立默认请求。

#### 异常说明

原配置、预算、取消或登记错误；持续清理失败附csv_request_cleanup_owner。

源码：[`src/chronaxis/execution/csv_reader.py:277`](../../../src/chronaxis/execution/csv_reader.py#L277)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_CSVRequest-_adopt_cleanup"></a>
### `_CSVRequest._adopt_cleanup`

接住本次尚未返回的检查器，不接他请求或借用来源。

```python
_CSVRequest._adopt_cleanup(exc)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`exc`|BaseException|是|无|位置或关键字。本次操作的原异常，供附加关闭失败信息并保留原因链。不要用错误字符串代替异常对象。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

无预期异常。

源码：[`src/chronaxis/execution/csv_reader.py:300`](../../../src/chronaxis/execution/csv_reader.py#L300)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_CSVRequest-_created_iterator"></a>
### `_CSVRequest._created_iterator`

在原活动登记前接住同一个实际生成器。

```python
_CSVRequest._created_iterator(iterator)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`iterator`|Iterator[[SignalBatch](chronaxis.sources.models.md#api-SignalBatch)]|是|无|位置或关键字。该请求创建的样本批次生成器；资源接收器保留它以便显式关闭。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

无预期异常。

源码：[`src/chronaxis/execution/csv_reader.py:309`](../../../src/chronaxis/execution/csv_reader.py#L309)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_CSVRequest-_read_resources"></a>
### `_CSVRequest._read_resources`

建立本请求唯一检查器，登记前失败仍由本请求保留责任。

```python
_CSVRequest._read_resources()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

真实_CSVResources。

#### 异常说明

原预算、构造或集合登记错误。

本函数直接报告的具体错误：

- `SourceClosedError`：默认CSV请求尚有资源待清理。

源码：[`src/chronaxis/execution/csv_reader.py:316`](../../../src/chronaxis/execution/csv_reader.py#L316)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_CSVRequest-_opened_handle"></a>
### `_CSVRequest._opened_handle`

在原handles集合登记前接住真实只读FD。

```python
_CSVRequest._opened_handle(handle)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`handle`|TextIO|是|无|位置或关键字。本次输入文件已经打开的文本读取对象；用于逐行读取或关闭，不传文件名字符串。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

无预期异常。

源码：[`src/chronaxis/execution/csv_reader.py:332`](../../../src/chronaxis/execution/csv_reader.py#L332)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_CSVRequest-_close_handle"></a>
### `_CSVRequest._close_handle`

执行原文件关闭责任，失败时保持本请求的实际FD引用。

```python
_CSVRequest._close_handle(handle, primary)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`handle`|TextIO|是|无|位置或关键字。本次输入文件已经打开的文本读取对象；用于逐行读取或关闭，不传文件名字符串。|
|`primary`|BaseException|是|无|位置或关键字。本次操作的原异常，供附加关闭失败信息并保留原因链。不要用错误字符串代替异常对象。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

无主错或GeneratorExit时传播原关闭错误，其余主错保留并加note。

源码：[`src/chronaxis/execution/csv_reader.py:339`](../../../src/chronaxis/execution/csv_reader.py#L339)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_CSVRequest-_end_file"></a>
### `_CSVRequest._end_file`

抵销文件局部费用，已有业务原错或取消不被附加释放错误取代。

```python
_CSVRequest._end_file(resources, primary)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`resources`|[_CSVResources](chronaxis.execution.csv_reader.md#api-_CSVResources)|是|无|位置或关键字。负责当前CSV读取的缓冲、行大小和资源额度检查对象，必须与本次读取对应。|
|`primary`|BaseException|是|无|位置或关键字。本次操作的原异常，供附加关闭失败信息并保留原因链。不要用错误字符串代替异常对象。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

正常结束或GeneratorExit时传播原清理错误。

源码：[`src/chronaxis/execution/csv_reader.py:351`](../../../src/chronaxis/execution/csv_reader.py#L351)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_CSVRequest-_close_resources"></a>
### `_CSVRequest._close_resources`

仅在真实FD已关闭后清理本请求检查器，保留原主异常。

```python
_CSVRequest._close_resources(primary)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`primary`|BaseException|是|无|位置或关键字。本次操作的原异常，供附加关闭失败信息并保留原因链。不要用错误字符串代替异常对象。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

正常关闭失败原样传播。

本函数直接报告的具体错误：

- `SourceReadError`：默认CSV文件尚未成功关闭。

源码：[`src/chronaxis/execution/csv_reader.py:364`](../../../src/chronaxis/execution/csv_reader.py#L364)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_CSVRequest-__iter__"></a>
### `_CSVRequest.__iter__`

返回自有游标。

```python
_CSVRequest.__iter__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回当前对象本身。后续迭代或with语句使用的仍是同一个对象。

#### 异常说明

无。

源码：[`src/chronaxis/execution/csv_reader.py:380`](../../../src/chronaxis/execution/csv_reader.py#L380)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_CSVRequest-__next__"></a>
### `_CSVRequest.__next__`

推进原生成器，失败/EOF只清自有资源并保留原异常和最高恢复owner。

```python
_CSVRequest.__next__() -> SignalBatch
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

原SignalBatch。

#### 异常说明

原关闭、EOF、预算、读取或取消错误。

本函数直接报告的具体错误：

- `SourceClosedError`：默认CSV请求正在清理。

返回类型：[SignalBatch](chronaxis.sources.models.md#api-SignalBatch)。

源码：[`src/chronaxis/execution/csv_reader.py:384`](../../../src/chronaxis/execution/csv_reader.py#L384)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_CSVRequest-close"></a>
### `_CSVRequest.close`

依次关闭真实生成器/FD/检查器，最后抵销固定费用，成功后才closed。

```python
_CSVRequest.close() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None。关闭成功后再次调用不会重复释放同一份资源。

#### 异常说明

原关闭或预算错误；尚未清完附最高请求owner。

返回类型：None。

源码：[`src/chronaxis/execution/csv_reader.py:408`](../../../src/chronaxis/execution/csv_reader.py#L408)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_CSVResources"></a>
## `_CSVResources`

每请求按用途保存金额，固定读取缓冲、行/ref、数组和协议状态共同计账。

八个实际属性槽是付款依据，charges只提供兼容视图；_held_cost为槽位总和。
_closing后不再增加费用，所有用途真实抵销完成才closed并解除来源登记。

```python
_CSVResources(owner)
```


源码：[`src/chronaxis/execution/csv_reader.py:463`](../../../src/chronaxis/execution/csv_reader.py#L463)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_CSVResources-__init__"></a>
### `_CSVResources.__init__`

预留文件解码缓冲及资源容器，不在申请前打开文件。

```python
_CSVResources.__init__(owner)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|[BudgetedSignalCSVSourceAdapter](chronaxis.execution.csv_reader.md#api-BudgetedSignalCSVSourceAdapter)|是|无|位置或关键字。本次CSV来源适配器，提供资源计量与文件打开限制。|

#### 返回说明

独立检查器。

#### 异常说明

BudgetExceededError。

源码：[`src/chronaxis/execution/csv_reader.py:470`](../../../src/chronaxis/execution/csv_reader.py#L470)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_CSVResources-_sync"></a>
### `_CSVResources._sync`

把真实付款槽同步到兼容charges视图，不从视图反推所有权。

```python
_CSVResources._sync(key)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`key`|str|是|无|位置或关键字。本次资源申请的用途名称。归还额度时使用申请时登记的同一名称，便于核对哪一部分仍占用资源。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原字典登记错误可重试。

源码：[`src/chronaxis/execution/csv_reader.py:491`](../../../src/chronaxis/execution/csv_reader.py#L491)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_CSVResources-_add"></a>
### `_CSVResources._add`

事务式登记一次真实预约，未入账超限不增加自有金额。

```python
_CSVResources._add(key, amount)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`key`|str|是|无|位置或关键字。本次资源申请的用途名称。归还额度时使用申请时登记的同一名称，便于核对哪一部分仍占用资源。|
|`amount`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

账本超限/金额错误/取消；
    实际已入账而返回取消时仍保留真实付款槽。

本函数直接报告的具体错误：

- `SourceClosedError`：默认CSV资源已关闭或正在清理。

源码：[`src/chronaxis/execution/csv_reader.py:502`](../../../src/chronaxis/execution/csv_reader.py#L502)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_CSVResources-_release_amount"></a>
### `_CSVResources._release_amount`

只抵销本用途真实费用，释放前后取消均保留正确槽位。

```python
_CSVResources._release_amount(key, amount)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`key`|str|是|无|位置或关键字。本次资源申请的用途名称。归还额度时使用申请时登记的同一名称，便于核对哪一部分仍占用资源。|
|`amount`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原释放或取消。

源码：[`src/chronaxis/execution/csv_reader.py:515`](../../../src/chronaxis/execution/csv_reader.py#L515)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_CSVResources-_move"></a>
### `_CSVResources._move`

转移已付款责任槽，总费用不变，不申请或归还共享余额。

```python
_CSVResources._move(source, target, amount)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|str|是|无|位置或关键字。转出资源预约量的计数属性名。|
|`target`|str|是|无|位置或关键字。接收资源预约量的计数属性名；转移前后的预约总量保持不变。|
|`amount`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

金额矛盾ValueError。

本函数直接报告的具体错误：

- `ValueError`：默认CSV费用交接超出原用途余额。

源码：[`src/chronaxis/execution/csv_reader.py:525`](../../../src/chronaxis/execution/csv_reader.py#L525)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_CSVResources-_release"></a>
### `_CSVResources._release`

抵销某用途全部预留。

```python
_CSVResources._release(key)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`key`|str|是|无|位置或关键字。本次资源申请的用途名称。归还额度时使用申请时登记的同一名称，便于核对哪一部分仍占用资源。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

账本一致性错误。

源码：[`src/chronaxis/execution/csv_reader.py:538`](../../../src/chronaxis/execution/csv_reader.py#L538)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_CSVResources-lines"></a>
### `_CSVResources.lines`

把真实TextIO交给限长物理行迭代器，不自己解释CSV。

```python
_CSVResources.lines(handle)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`handle`|TextIO|是|无|位置或关键字。本次输入文件已经打开的文本读取对象；用于逐行读取或关闭，不传文件名字符串。|

#### 返回说明

_PhysicalLines。

#### 异常说明

构造错误传播。

源码：[`src/chronaxis/execution/csv_reader.py:542`](../../../src/chronaxis/execution/csv_reader.py#L542)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_CSVResources-records"></a>
### `_CSVResources.records`

保持原reader的物理计数和解释，为表头/当前逻辑记录保存累积预算。

```python
_CSVResources.records(reader)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`reader`|Iterator[list[str]]|是|无|位置或关键字。csv.reader创建的记录迭代器，每次返回一行单元格；引号内的换行仍属于同一条记录。|

#### 返回说明

_CSVRecords。

#### 异常说明

构造错误传播。

源码：[`src/chronaxis/execution/csv_reader.py:550`](../../../src/chronaxis/execution/csv_reader.py#L550)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_CSVResources-_sample_estimate"></a>
### `_CSVResources._sample_estimate`

估算新记录独有的容器、数值和文本，不重复计算来源路径或声明。

```python
_CSVResources._sample_estimate(time_text, text, definition)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_text`|str|是|无|位置或关键字。当前行时间单元格的原文本。|
|`text`|str|是|无|位置或关键字。当前信号原值单元格的文本，含缺失标记或原码。|
|`definition`|[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)|是|无|位置或关键字。当前信号声明，提供名称、枚举和原码类型。|

#### 返回说明

(记录费用, 字符串原值长度)，长度为零表示没有定宽字符串列。

#### 异常说明

输入已由读取器限定；声明查找错误直接传播。

源码：[`src/chronaxis/execution/csv_reader.py:557`](../../../src/chronaxis/execution/csv_reader.py#L557)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_CSVResources-_pack_estimate"></a>
### `_CSVResources._pack_estimate`

分别计算最终列、归一化工作区和跨批同一时刻检查状态的峰值。

```python
_CSVResources._pack_estimate(validator, count, columns, unicode_bytes)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`validator`|BatchValidator|是|无|位置或关键字。已有跨批协议校验器，提供尚需保留的同一时刻身份集合。|
|`count`|int|是|无|位置或关键字。候选批内的样本数，用来预留列和临时工作区。|
|`columns`|int|是|无|位置或关键字。候选批内实际有样本的信号列数。|
|`unicode_bytes`|int|是|无|位置或关键字。依次打包各列时，最大原码Unicode数组的字节数；reference后端为0。|

#### 返回说明

(保留列费用, 打包峰值费用)。

#### 异常说明

无预期异常。

源码：[`src/chronaxis/execution/csv_reader.py:582`](../../../src/chronaxis/execution/csv_reader.py#L582)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_CSVResources-should_flush"></a>
### `_CSVResources.should_flush`

在再接收一条样本之前判断是否应先交付当前批。

```python
_CSVResources.should_flush(time_text, text, definition, validator)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_text`|str|是|无|位置或关键字。当前CSV行的原时间单元格，用于估算新记录。|
|`text`|str|是|无|位置或关键字。当前信号的原值单元格；本方法只估算费用，不解析成数值。|
|`definition`|[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)|是|无|位置或关键字。当前信号声明，提供原码/枚举类型及列名。|
|`validator`|BatchValidator|是|无|位置或关键字。本读取请求已有的跨批同一时刻校验状态，用于估算保留身份集合。|

#### 返回说明

bool；已有样本且继续累积会挤占打包空间时为 True。

#### 异常说明

无预期异常；单条无法容纳由实际预约明确失败。

源码：[`src/chronaxis/execution/csv_reader.py:599`](../../../src/chronaxis/execution/csv_reader.py#L599)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_CSVResources-before_sample"></a>
### `_CSVResources.before_sample`

在值解析及原记录 append 前预留记录独有的数据。

```python
_CSVResources.before_sample(time_text, text, path, definition)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_text`|str|是|无|位置或关键字。当前行时间单元格的原文本，用于解析时间及定位错误。|
|`text`|str|是|无|位置或关键字。当前行信号值单元格的原文本，用于解析数值及定位错误。|
|`path`|[pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。即将读取样本的实际CSV文件，用于计入对应文件和行的资源。|
|`definition`|[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)|是|无|位置或关键字。当前信号声明，用于预留该样本独有的原值和字符串空间。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

预算超限或预约取消，仍保留真实已付金额。

源码：[`src/chronaxis/execution/csv_reader.py:629`](../../../src/chronaxis/execution/csv_reader.py#L629)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_CSVResources-before_pack"></a>
### `_CSVResources.before_pack`

在创建数组前预留实际候选批的峰值，不按最大批大小预先拒绝。

```python
_CSVResources.before_pack(pending, validator)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`pending`|list|是|无|位置或关键字。待打包成SignalBatch的原始样本缓冲；在构造数组前先按缓冲大小预约资源。|
|`validator`|BatchValidator|是|无|位置或关键字。本次读取请求的批次检查器，用它检查样本、进度和结束标记；不同请求不能共用推进状态。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

单批真实工作区超限或取消；不丢样本，也不切换计算后端。

源码：[`src/chronaxis/execution/csv_reader.py:643`](../../../src/chronaxis/execution/csv_reader.py#L643)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_CSVResources-after_pack"></a>
### `_CSVResources.after_pack`

校验完成后把工作预留转为当前owned数组和保留协议状态。

```python
_CSVResources.after_pack(validator)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`validator`|BatchValidator|是|无|位置或关键字。本次读取请求的批次检查器，用它检查样本、进度和结束标记；不同请求不能共用推进状态。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

内部账本一致性错误。

源码：[`src/chronaxis/execution/csv_reader.py:660`](../../../src/chronaxis/execution/csv_reader.py#L660)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_CSVResources-clear_pending"></a>
### `_CSVResources.clear_pending`

原生成器恢复并清空缓冲后重置计数，不重复抵销已转交的共享费用。

```python
_CSVResources.clear_pending()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

账本一致性错误。

源码：[`src/chronaxis/execution/csv_reader.py:675`](../../../src/chronaxis/execution/csv_reader.py#L675)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_CSVResources-end_file"></a>
### `_CSVResources.end_file`

局部行/表头引用丢弃后抵销预算，跨文件样本与协议预算保留。

```python
_CSVResources.end_file()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

账本一致性错误。

源码：[`src/chronaxis/execution/csv_reader.py:685`](../../../src/chronaxis/execution/csv_reader.py#L685)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_CSVResources-close"></a>
### `_CSVResources.close`

释放本请求全部金额，不关闭他请求或删除输入文件。

```python
_CSVResources.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None。关闭成功后再次调用不会重复释放同一份资源。

#### 异常说明

账本一致性错误。

源码：[`src/chronaxis/execution/csv_reader.py:694`](../../../src/chronaxis/execution/csv_reader.py#L694)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_PhysicalLines"></a>
## `_PhysicalLines`

每次readline前按剩余RAM申请上限；引用记录跨行继续累积reading金额。

```python
_PhysicalLines(resources, handle)
```


源码：[`src/chronaxis/execution/csv_reader.py:710`](../../../src/chronaxis/execution/csv_reader.py#L710)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_PhysicalLines-__init__"></a>
### `_PhysicalLines.__init__`

保存真实只读句柄。

```python
_PhysicalLines.__init__(resources, handle)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`resources`|[_CSVResources](chronaxis.execution.csv_reader.md#api-_CSVResources)|是|无|位置或关键字。负责当前CSV读取的缓冲、行大小和资源额度检查对象，必须与本次读取对应。|
|`handle`|TextIO|是|无|位置或关键字。本次输入文件已经打开的文本读取对象；用于逐行读取或关闭，不传文件名字符串。|

#### 返回说明

新行游标。

#### 异常说明

无。

源码：[`src/chronaxis/execution/csv_reader.py:713`](../../../src/chronaxis/execution/csv_reader.py#L713)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_PhysicalLines-__iter__"></a>
### `_PhysicalLines.__iter__`

返回物理行游标。

```python
_PhysicalLines.__iter__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回当前对象本身。后续迭代或with语句使用的仍是同一个对象。

#### 异常说明

无。

源码：[`src/chronaxis/execution/csv_reader.py:717`](../../../src/chronaxis/execution/csv_reader.py#L717)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_PhysicalLines-_retained_line_bytes"></a>
### `_PhysicalLines._retained_line_bytes`

计算当前逻辑记录仍需保存的解析字符和字段开销。

```python
_PhysicalLines._retained_line_bytes(text, first_line)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`text`|str|是|无|位置或关键字。刚读取的完整物理行，用于估算字符及分隔符字段开销。|
|`first_line`|bool|是|无|位置或关键字。当前物理行是否属于逻辑记录的第一行；固定容器费用只记一次。|

#### 返回说明

字节估算。

#### 异常说明

无预期异常。

源码：[`src/chronaxis/execution/csv_reader.py:721`](../../../src/chronaxis/execution/csv_reader.py#L721)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_PhysicalLines-__next__"></a>
### `_PhysicalLines.__next__`

有界读完整物理行，超限不把截断内容交给csv.reader。

```python
_PhysicalLines.__next__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

含原换行的str；EOF停止。

#### 异常说明

BudgetExceededError/原I/O错误。

本函数直接报告的具体错误：

- `BudgetExceededError`：CSV物理行/引用记录累积超出剩余RAM估算。
- `BudgetExceededError`：CSV物理行超过剩余RAM允许长度，未解析截断行。

源码：[`src/chronaxis/execution/csv_reader.py:734`](../../../src/chronaxis/execution/csv_reader.py#L734)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_CSVRecords"></a>
## `_CSVRecords`

包装原csv.reader，表头固定持有，当前/下一逻辑记录读取时预算重叠。

```python
_CSVRecords(resources, reader)
```


源码：[`src/chronaxis/execution/csv_reader.py:768`](../../../src/chronaxis/execution/csv_reader.py#L768)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_CSVRecords-__init__"></a>
### `_CSVRecords.__init__`

保存原解析器。

```python
_CSVRecords.__init__(resources, reader)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`resources`|[_CSVResources](chronaxis.execution.csv_reader.md#api-_CSVResources)|是|无|位置或关键字。负责当前CSV读取的缓冲、行大小和资源额度检查对象，必须与本次读取对应。|
|`reader`|Iterator[list[str]]|是|无|位置或关键字。csv.reader创建的记录迭代器，每次返回一行单元格；引号内的换行仍属于同一条记录。|

#### 返回说明

新记录游标。

#### 异常说明

无。

源码：[`src/chronaxis/execution/csv_reader.py:771`](../../../src/chronaxis/execution/csv_reader.py#L771)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_CSVRecords-__iter__"></a>
### `_CSVRecords.__iter__`

返回记录游标。

```python
_CSVRecords.__iter__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回当前对象本身。后续迭代或with语句使用的仍是同一个对象。

#### 异常说明

无。

源码：[`src/chronaxis/execution/csv_reader.py:775`](../../../src/chronaxis/execution/csv_reader.py#L775)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_CSVRecords-__next__"></a>
### `_CSVRecords.__next__`

推进原解析器，跨物理行累积到一条完整记录再转移预算。

```python
_CSVRecords.__next__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

原单元格list。

#### 异常说明

EOF/原csv错误/预算或I/O错误。

源码：[`src/chronaxis/execution/csv_reader.py:779`](../../../src/chronaxis/execution/csv_reader.py#L779)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
