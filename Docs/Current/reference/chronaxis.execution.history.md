# `chronaxis.execution.history`

将已解码批次写入有限历史并单行重放，不重读旧输入。

输入为来源描述、读取请求和带有明确类型的 SignalBatch；输出为样本/进度迭代器。
每来源一个JSONL，列内有序数组以有限堆按时间/序号合并，保留所有同一时刻更新。
共享ResourceBudget覆盖现有批次数组nbytes、Python容器、协议pending和行副本；
预算在新增结构/写入前申请，累计spool包含失败部分，不承诺全进程RSS。
来源在生成批次前的预算接线尚未在本组件实现，不能据此声称完整AnalysisRunner有限。
失败保留诊断文件和原异常，关闭活动句柄；RefProjects与既有工作目录不修改。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisError](chronaxis.results.errors.md#api-AnalysisError)、[BatchValidator](chronaxis.sources.protocol.md#api-BatchValidator)、[DecodedTimeGroup](chronaxis.execution.groups.md#api-DecodedTimeGroup)、[ExtensionRegistry](chronaxis.extensions.md#api-ExtensionRegistry)、[FunctionSpec](chronaxis.extensions.md#api-FunctionSpec)、[HistoryProgress](chronaxis.execution.history_records.md#api-HistoryProgress)、[HistorySample](chronaxis.execution.history_records.md#api-HistorySample)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[QualityFlag](chronaxis.core.types.md#api-QualityFlag)、[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)、[ReductionSpec](chronaxis.extensions.md#api-ReductionSpec)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[ResultFormatError](chronaxis.results.errors.md#api-ResultFormatError)、[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)、[SignalBatch](chronaxis.sources.models.md#api-SignalBatch)、[SignalDType](chronaxis.core.types.md#api-SignalDType)、[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)、[SourceDescription](chronaxis.sources.models.md#api-SourceDescription)、[TransformSpec](chronaxis.extensions.md#api-TransformSpec)、[_TimeGroupIterator](chronaxis.execution.groups.md#api-_TimeGroupIterator)

## 对象导航

|对象|用途|
|---|---|
|[`_metadata_bytes`](#api-_metadata_bytes)|估算已校验来源/请求的冻结元数据，不改变结果层封闭类型注册。|
|[`_pending_bytes`](#api-_pending_bytes)|估算当前组去重状态，不保留历史所有sequence。|
|[`_batch_bytes`](#api-_batch_bytes)|核算调用方已提供批次数组和引用/原诊断容器。|
|[`DecodedHistoryStore`](#api-DecodedHistoryStore)|维护一次任务的分源历史、协议状态和独立读取句柄。|
|[`DecodedHistoryStore.__init__`](#api-DecodedHistoryStore-__init__)|为新目录建立历史，检查来源/请求并先申请固定元数据预算。|
|[`DecodedHistoryStore._check`](#api-DecodedHistoryStore-_check)|检查生命周期，不让关闭或失败历史继续使用。|
|[`DecodedHistoryStore._write_bytes`](#api-DecodedHistoryStore-_write_bytes)|先申请累计磁盘额度，循环完成合法短写。|
|[`DecodedHistoryStore._writer`](#api-DecodedHistoryStore-_writer)|复用当前来源的无缓冲写FD，切换来源或失败时关闭，诊断仍逐次关闭。|
|[`DecodedHistoryStore._close_handle`](#api-DecodedHistoryStore-_close_handle)|按实际FD状态关闭一个父持有句柄，实际未关时保留原对象。|
|[`DecodedHistoryStore._write_record`](#api-DecodedHistoryStore-_write_record)|申请单行编码临时RAM，写入成功后更新摘要。|
|[`DecodedHistoryStore.append`](#api-DecodedHistoryStore-append)|保存一批的全部异步样本和最终进度，空批仍写一条记录。|
|[`DecodedHistoryStore._record_failure`](#api-DecodedHistoryStore-_record_failure)|尽力保存有界失败标记，不将可能巨大的异常文本装入内存。|
|[`DecodedHistoryStore.seal`](#api-DecodedHistoryStore-seal)|所有配置来源EOF后封存，禁止用单文件EOF代替来源终点。|
|[`DecodedHistoryStore.iter_records`](#api-DecodedHistoryStore-iter_records)|建立一个有独立文件位置的有限重放迭代器。|
|[`DecodedHistoryStore.source_completions`](#api-DecodedHistoryStore-source_completions)|读取已封存来源EOF/终点原事实，不推断未知终点或有效期。|
|[`DecodedHistoryStore.iter_groups`](#api-DecodedHistoryStore-iter_groups)|按完整同时间组重放已封存历史，注册关闭所有权。|
|[`DecodedHistoryStore.close`](#api-DecodedHistoryStore-close)|幂等关闭所有活动迭代器并释放协议/固定状态RAM，保留历史文件。|
|[`_HistoryIterator`](#api-_HistoryIterator)|单行读取、核对批次计数与SHA256，不装入完整历史。|
|[`_HistoryIterator.__init__`](#api-_HistoryIterator-__init__)|先预留解析/句柄RAM再打开单个来源文件。|
|[`_HistoryIterator.__iter__`](#api-_HistoryIterator-__iter__)|返回本次独立游标。|
|[`_HistoryIterator.verified_eof`](#api-_HistoryIterator-verified_eof)|读取实际文件EOF核对事实。|
|[`_HistoryIterator.__next__`](#api-_HistoryIterator-__next__)|读取一行并检查身份、批次结构及终点完整性。|
|[`_HistoryIterator.close`](#api-_HistoryIterator-close)|关闭单个游标并抵销一次预留，重复关闭安全。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import fields, is_dataclass
from enum import Enum
from hashlib import sha256
from pathlib import Path
from sys import getsizeof
from types import MappingProxyType
from ..extensions import ExtensionRegistry, FunctionSpec, ReductionSpec, TransformSpec
from ..core.numeric import ScalarValue
from ..core.types import QualityFlag, SignalDType
from ..core.binding import SignalDefinition
from ..results.budget import ResourceBudget
from ..results.codec import _estimate
from ..results.errors import AnalysisError, ResultClosedError, ResultFormatError
from ..results.spool import _cleanup_owner, _reserve_owned_ram, _release_owned_ram
from ..sources.models import SignalBatch, SourceDescription, ReadRequest
from ..sources.protocol import BatchValidator
from .history_records import HistorySample, HistoryProgress, HistoryRecord, estimate_record_bytes, encode_record, decode_record
from .groups import DecodedTimeGroup, _TimeGroupIterator
```

</details>

<a id="api-_metadata_bytes"></a>
## `_metadata_bytes`

估算已校验来源/请求的冻结元数据，不改变结果层封闭类型注册。

```python
_metadata_bytes(value, depth: int=0) -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|object|是|无|位置或关键字。用于估算内存的元数据树，包含已登记模型、元组和原生标量；逐层计算对象及字段大小，不读取信号样本文件。|
|`depth`|int|否|0|位置或关键字。当前递归层数，供内部遍历元数据时检查嵌套深度。顶层使用0，每进入一层增加1。|

### 返回说明

基础bytes。

### 异常说明

ResultFormatError为深度或未支持元数据。

本函数直接报告的具体错误：

- `ResultFormatError`：历史元数据类型无法估算。
- `ResultFormatError`：历史元数据超过32层。

返回类型：int。

源码：[`src/chronaxis/execution/history.py:36`](../../../src/chronaxis/execution/history.py#L36)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_pending_bytes"></a>
## `_pending_bytes`

估算当前组去重状态，不保留历史所有sequence。

```python
_pending_bytes(validator: BatchValidator) -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`validator`|[BatchValidator](chronaxis.sources.protocol.md#api-BatchValidator)|是|无|位置或关键字。validator为一个来源协议状态。|

### 返回说明

保守bytes。

### 异常说明

已校验状态不主动抛错。

返回类型：int。

源码：[`src/chronaxis/execution/history.py:69`](../../../src/chronaxis/execution/history.py#L69)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_batch_bytes"></a>
## `_batch_bytes`

核算调用方已提供批次数组和引用/原诊断容器。

```python
_batch_bytes(batch: SignalBatch) -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`batch`|[SignalBatch](chronaxis.sources.models.md#api-SignalBatch)|是|无|位置或关键字。batch为带有明确类型的批次。|

### 返回说明

数组精确nbytes加容器保守bytes。

### 异常说明

深度/类型估算错误传播，不省略长字段开销。

返回类型：int。

源码：[`src/chronaxis/execution/history.py:79`](../../../src/chronaxis/execution/history.py#L79)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-DecodedHistoryStore"></a>
## `DecodedHistoryStore`

维护一次任务的分源历史、协议状态和独立读取句柄。

building仅能追加，sealed要求所有来源EOF；failed/cancelled禁止重放。
close幂等关闭读取句柄并释放状态RAM，磁盘文件留作恢复证据，不递归删除。
源数/字段数来自固定声明，样本数增长只体现在磁盘和整数计数中。

```python
DecodedHistoryStore(budget: ResourceBudget, work_dir: str | Path, descriptions: tuple[SourceDescription, ...], requests: Mapping[str, ReadRequest])
```


源码：[`src/chronaxis/execution/history.py:91`](../../../src/chronaxis/execution/history.py#L91)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-DecodedHistoryStore-__init__"></a>
### `DecodedHistoryStore.__init__`

为新目录建立历史，检查来源/请求并先申请固定元数据预算。

```python
DecodedHistoryStore.__init__(budget: ResourceBudget, work_dir: str | Path, descriptions: tuple[SourceDescription, ...], requests: Mapping[str, ReadRequest])
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)|是|无|位置或关键字。本次运行共用的ResourceBudget对象，用于检查内存和临时磁盘用量。当前对象在分配前申请额度，用完后归还；同一次运行的组件应使用同一个对象。|
|`work_dir`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。work_dir必须不存在|
|`descriptions`|tuple[[SourceDescription](chronaxis.sources.models.md#api-SourceDescription), ...]|是|无|位置或关键字。各来源实际取得的描述，顺序与requests一一对应。|
|`requests`|Mapping[str, [ReadRequest](chronaxis.sources.models.md#api-ReadRequest)]|是|无|位置或关键字。来源别名到实际ReadRequest的映射，每个来源均须有对应请求；与descriptions中的来源按名称匹配。|

#### 返回说明

building存储。

#### 异常说明

ValueError/TypeError/预算或实际目录创建原错；持续
    清理失败附history_cleanup_owner，已有目录不写失败标记也不抵销借用费用。

源码：[`src/chronaxis/execution/history.py:99`](../../../src/chronaxis/execution/history.py#L99)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-DecodedHistoryStore-_check"></a>
### `DecodedHistoryStore._check`

检查生命周期，不让关闭或失败历史继续使用。

```python
DecodedHistoryStore._check(state: str) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`state`|str|是|无|位置或关键字。state为所需状态。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ResultClosedError或AnalysisError为状态不允许。

本函数直接报告的具体错误：

- `ResultClosedError`：解码历史已关闭或正在清理。

返回类型：None。

源码：[`src/chronaxis/execution/history.py:152`](../../../src/chronaxis/execution/history.py#L152)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-DecodedHistoryStore-_write_bytes"></a>
### `DecodedHistoryStore._write_bytes`

先申请累计磁盘额度，循环完成合法短写。

```python
DecodedHistoryStore._write_bytes(handle, payload: bytes) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`handle`|BinaryIO|是|无|位置或关键字。本次操作已经打开的二进制文件对象；在此句柄上读写字节，不传文件路径。关闭责任仍由创建句柄的对象承担。|
|`payload`|bytes|是|无|位置或关键字。本次要追加的一行字节数据，包含该格式要求的行结束符。该方法将其写入已经打开的二进制文件。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

超限/OSError/零写立即失败，原部分文件保留。

本函数直接报告的具体错误：

- `OSError`：历史文件写入无进展或返回非法长度。

返回类型：None。

源码：[`src/chronaxis/execution/history.py:164`](../../../src/chronaxis/execution/history.py#L164)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-DecodedHistoryStore-_writer"></a>
### `DecodedHistoryStore._writer`

复用当前来源的无缓冲写FD，切换来源或失败时关闭，诊断仍逐次关闭。

```python
DecodedHistoryStore._writer(slot, path, mode)
```

装饰器：`contextmanager`。

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`slot`|str|是|无|位置或关键字。当前对象中用于保存资源或其费用的属性名，例如"_row_cost"；只能指向本对象实际管理的项。释放成功后才清空对应项。|
|`path`|[pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。历史仓内要打开的文件路径，写入来源样本或进度记录。|
|`mode`|str|是|无|位置或关键字。传给open的二进制打开模式，写入用"wb"或"ab"；由历史仓内部选择，不接收用户任意模式。|

#### 返回说明

上下文内借用实际FileIO。

#### 异常说明

打开或写入原错；已有主错时关闭
    副错只加note，失败FD留父close重试。成功数据批不关闭，EOF或seal/close收尾。

本函数直接报告的具体错误：

- `AnalysisError`：历史仍有未关闭诊断FD，不能覆盖恢复责任。

源码：[`src/chronaxis/execution/history.py:180`](../../../src/chronaxis/execution/history.py#L180)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-DecodedHistoryStore-_close_handle"></a>
### `DecodedHistoryStore._close_handle`

按实际FD状态关闭一个父持有句柄，实际未关时保留原对象。

```python
DecodedHistoryStore._close_handle(slot, primary=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`slot`|str|是|无|位置或关键字。本历史仓保存文件句柄的属性名；关闭后清空该属性并归还文件额度。|
|`primary`|BaseException &#124; None|否|None|位置或关键字。本次操作的原异常，供附加关闭失败信息并保留原因链。None表示此前没有异常。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

无主错时原close错误传播；有主错时只加note，最高
    history仍持失败句柄。释放后取消也以真实closed完成最小解除。

本函数直接报告的具体错误：

- `AnalysisError`：历史写FD close返回但实际尚未关闭。

源码：[`src/chronaxis/execution/history.py:208`](../../../src/chronaxis/execution/history.py#L208)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-DecodedHistoryStore-_write_record"></a>
### `DecodedHistoryStore._write_record`

申请单行编码临时RAM，写入成功后更新摘要。

```python
DecodedHistoryStore._write_record(handle, name: str, record: HistoryRecord) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`handle`|BinaryIO|是|无|位置或关键字。本次操作已经打开的二进制文件对象；在此句柄上读写字节，不传文件路径。关闭责任仍由创建句柄的对象承担。|
|`name`|str|是|无|位置或关键字。当前记录所属的来源别名，用于选择该来源的历史文件。|
|`record`|HistoryRecord|是|无|位置或关键字。待写入的一条HistorySample或HistoryProgress，保留实际样本或读取进度。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

格式/预算/文件错误传播，finally释放临时RAM。

返回类型：None。

源码：[`src/chronaxis/execution/history.py:232`](../../../src/chronaxis/execution/history.py#L232)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-DecodedHistoryStore-append"></a>
### `DecodedHistoryStore.append`

保存一批的全部异步样本和最终进度，空批仍写一条记录。

```python
DecodedHistoryStore.append(batch: SignalBatch) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`batch`|[SignalBatch](chronaxis.sources.models.md#api-SignalBatch)|是|无|位置或关键字。batch为已经归一化的带有明确类型的批次。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

AnalysisError保留格式/协议/预算/磁盘异常链；取消原样传播。

本函数直接报告的具体错误：

- `ValueError`：历史批次不属于声明来源。
- `OverflowError`：历史批次/样本计数超过int64。

#### 边界说明

接收到的数组已经分配，本方法计入其占用但不能追溯控制该分配。

返回类型：None。

源码：[`src/chronaxis/execution/history.py:259`](../../../src/chronaxis/execution/history.py#L259)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-DecodedHistoryStore-_record_failure"></a>
### `DecodedHistoryStore._record_failure`

尽力保存有界失败标记，不将可能巨大的异常文本装入内存。

```python
DecodedHistoryStore._record_failure(exc: BaseException) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`exc`|BaseException|是|无|位置或关键字。exc为原失败。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

写标记失败被记录为原异常附注。

返回类型：None。

源码：[`src/chronaxis/execution/history.py:342`](../../../src/chronaxis/execution/history.py#L342)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-DecodedHistoryStore-seal"></a>
### `DecodedHistoryStore.seal`

所有配置来源EOF后封存，禁止用单文件EOF代替来源终点。

```python
DecodedHistoryStore.seal() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

AnalysisError为未结束来源或错误状态。

本函数直接报告的具体错误：

- `AnalysisError`：全部来源EOF前不能封存解码历史。

返回类型：None。

源码：[`src/chronaxis/execution/history.py:364`](../../../src/chronaxis/execution/history.py#L364)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-DecodedHistoryStore-iter_records"></a>
### `DecodedHistoryStore.iter_records`

建立一个有独立文件位置的有限重放迭代器。

```python
DecodedHistoryStore.iter_records(source: str) -> Iterator[HistoryRecord]
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|str|是|无|位置或关键字。source为声明来源名。|

#### 返回说明

带有明确类型的记录Iterator。

#### 异常说明

关闭/未封存/未知来源/预算/打开错误。

本函数直接报告的具体错误：

- `ValueError`：未知历史来源。

返回类型：Iterator[HistoryRecord]。

源码：[`src/chronaxis/execution/history.py:376`](../../../src/chronaxis/execution/history.py#L376)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-DecodedHistoryStore-source_completions"></a>
### `DecodedHistoryStore.source_completions`

读取已封存来源EOF/终点原事实，不推断未知终点或有效期。

```python
DecodedHistoryStore.source_completions: Mapping[str, HistoryProgress]
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

只读Mapping；仅owner仍打开时可用。

#### 异常说明

关闭或未封存的历史状态错误。

返回类型：Mapping[str, [HistoryProgress](chronaxis.execution.history_records.md#api-HistoryProgress)]。

源码：[`src/chronaxis/execution/history.py:395`](../../../src/chronaxis/execution/history.py#L395)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-DecodedHistoryStore-iter_groups"></a>
### `DecodedHistoryStore.iter_groups`

按完整同时间组重放已封存历史，注册关闭所有权。

```python
DecodedHistoryStore.iter_groups(*, sources=None) -> Iterator[DecodedTimeGroup]
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`sources`|tuple[str, ...] &#124; None|否|None|仅关键字。要回读的来源别名；None回读全部来源，并将同一时刻的更新合为一组。|

#### 返回说明

独立组Iterator；组只包含所选来源，返回后须及时消费。

#### 异常说明

生命周期/来源子集类型、重复、未知名称/源游标/预算/历史读取错误。

#### 边界说明

子集EOF只证明所选来源；全历史摘要验证须另行遍历全部来源。

返回类型：Iterator[[DecodedTimeGroup](chronaxis.execution.groups.md#api-DecodedTimeGroup)]。

源码：[`src/chronaxis/execution/history.py:404`](../../../src/chronaxis/execution/history.py#L404)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-DecodedHistoryStore-close"></a>
### `DecodedHistoryStore.close`

幂等关闭所有活动迭代器并释放协议/固定状态RAM，保留历史文件。

```python
DecodedHistoryStore.close() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原句柄/预算/取消错误附history_cleanup_owner；
    子reader或任一费用未完成时保留父合同和实际责任，恢复后同一close重试。

返回类型：None。

源码：[`src/chronaxis/execution/history.py:423`](../../../src/chronaxis/execution/history.py#L423)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_HistoryIterator"></a>
## `_HistoryIterator`

单行读取、核对批次计数与SHA256，不装入完整历史。

cost与_held_cost记录同一笔自有reader费用；未返回构造或注册失败通过原异常恢复。
handle与登记只在真实FD关闭、费用抵销后解除，不归还调用方history的费用。

```python
_HistoryIterator(owner: DecodedHistoryStore, source: str)
```


源码：[`src/chronaxis/execution/history.py:467`](../../../src/chronaxis/execution/history.py#L467)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_HistoryIterator-__init__"></a>
### `_HistoryIterator.__init__`

先预留解析/句柄RAM再打开单个来源文件。

```python
_HistoryIterator.__init__(owner: DecodedHistoryStore, source: str)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|[DecodedHistoryStore](chronaxis.execution.history.md#api-DecodedHistoryStore)|是|无|位置或关键字。已经结束写入的历史仓，迭代期间借用其文件和资源额度。|
|`source`|str|是|无|位置或关键字。需要回读的来源别名，选择该来源对应的历史文件。|

#### 返回说明

新独立迭代器。

#### 异常说明

预算/打开/取消原错，持续清理失败时从history_iterator_cleanup_owner恢复close。

源码：[`src/chronaxis/execution/history.py:474`](../../../src/chronaxis/execution/history.py#L474)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_HistoryIterator-__iter__"></a>
### `_HistoryIterator.__iter__`

返回本次独立游标。

```python
_HistoryIterator.__iter__() -> '_HistoryIterator'
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回当前对象本身。后续迭代或with语句使用的仍是同一个对象。

#### 异常说明

无。

返回类型：'[_HistoryIterator](chronaxis.execution.history.md#api-_HistoryIterator)'。

源码：[`src/chronaxis/execution/history.py:504`](../../../src/chronaxis/execution/history.py#L504)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_HistoryIterator-verified_eof"></a>
### `_HistoryIterator.verified_eof`

读取实际文件EOF核对事实。

```python
_HistoryIterator.verified_eof: bool
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示已读到文件末尾且完成结束检查；False表示尚未完成检查。提前close时为False。

#### 异常说明

无；提前close为False。

返回类型：bool。

源码：[`src/chronaxis/execution/history.py:512`](../../../src/chronaxis/execution/history.py#L512)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_HistoryIterator-__next__"></a>
### `_HistoryIterator.__next__`

读取一行并检查身份、批次结构及终点完整性。

```python
_HistoryIterator.__next__() -> HistoryRecord
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

一条HistoryRecord。

#### 异常说明

StopIteration为已校验完整EOF；损坏/关闭/实际读错误传播并关闭句柄。

本函数直接报告的具体错误：

- `ResultClosedError`：解码历史已关闭或正在清理。
- `ResultClosedError`：解码历史游标正在关闭。
- `ResultFormatError`：历史来源EOF之后仍有记录。
- `ResultFormatError`：历史批次号不连续。
- `ResultFormatError`：解码历史EOF、计数或摘要不完整。
- `ResultFormatError`：历史样本身份/投影冲突。
- `ResultFormatError`：历史批次样本超限。
- `ResultFormatError`：历史进度身份/样本计数冲突。

返回类型：HistoryRecord。

源码：[`src/chronaxis/execution/history.py:516`](../../../src/chronaxis/execution/history.py#L516)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_HistoryIterator-close"></a>
### `_HistoryIterator.close`

关闭单个游标并抵销一次预留，重复关闭安全。

```python
_HistoryIterator.close() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None。关闭成功后再次调用不会重复释放同一份资源。

#### 异常说明

文件/预算/取消传播，真实文件未关闭或预算未抵销时保留登记供重试。

返回类型：None。

源码：[`src/chronaxis/execution/history.py:564`](../../../src/chronaxis/execution/history.py#L564)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
