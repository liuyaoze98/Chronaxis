# `chronaxis.execution.bindings`

重读本次已保存的信号历史，核对字段、记录数量、摘要和读取结束标记，然后建立表达式使用的信号对应关系。输入来自已经结束写入的历史文件，不能用尚未读完的一部分数据代替完整输入。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[DeclarationBindings](chronaxis.core.declarations.md#api-DeclarationBindings)、[DeclaredSource](chronaxis.core.declarations.md#api-DeclaredSource)、[DecodedBindings](chronaxis.core.decoded_binding.md#api-DecodedBindings)、[DecodedHistoryStore](chronaxis.execution.history.md#api-DecodedHistoryStore)、[DecodedSourceEvidence](chronaxis.core.decoded_binding.md#api-DecodedSourceEvidence)、[HistoryProgress](chronaxis.execution.history_records.md#api-HistoryProgress)、[HistorySample](chronaxis.execution.history_records.md#api-HistorySample)、[ObservedSourceScan](chronaxis.execution.observed_ingestion.md#api-ObservedSourceScan)、[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[ResultFormatError](chronaxis.results.errors.md#api-ResultFormatError)、[SignalDType](chronaxis.core.types.md#api-SignalDType)、[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)、[SourceDescription](chronaxis.sources.models.md#api-SourceDescription)

## 对象导航

|对象|用途|
|---|---|
|[`_fingerprint_value`](#api-_fingerprint_value)|把已校验冻结元数据转换为纯标量/tuple，不丢字段或来源定位。|
|[`_fingerprint`](#api-_fingerprint)|计算完整带有明确类型的树摘要。|
|[`DecodedBindingLease`](#api-DecodedBindingLease)|从首次预约到返回绑定持有唯一真实费用及当前回放reader。|
|[`DecodedBindingLease.__init__`](#api-DecodedBindingLease-__init__)|在首次外部操作前初始化真实责任槽，不申请预算或打开文件。|
|[`DecodedBindingLease.bindings`](#api-DecodedBindingLease-bindings)|读取不可变运行绑定。|
|[`DecodedBindingLease.closed`](#api-DecodedBindingLease-closed)|读取lease状态。|
|[`DecodedBindingLease._close_reader`](#api-DecodedBindingLease-_close_reader)|关闭本lease唯一实际reader，失败仍保留未完成的子责任。|
|[`DecodedBindingLease._clear_temporary`](#api-DecodedBindingLease-_clear_temporary)|结束有限工厂临时引用，不关闭借用对象。|
|[`DecodedBindingLease.close`](#api-DecodedBindingLease-close)|先关真实reader，再丢自有元数据并逐笔归还固定费。|
|[`_require_empty_source_scan`](#api-_require_empty_source_scan)|用本历史的真实扫描证明无字段来源的完整时钟，不从空描述猜测。|
|[`require_decoded_source_contract`](#api-require_decoded_source_contract)|只核一来源的声明、实际描述和请求合同，保留所有原信号定义。|
|[`bind_decoded_history`](#api-bind_decoded_history)|先核对当前契约，再完整重放所有来源，只有实际EOF校验后才返回运行绑定。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from hashlib import sha256
from ..core.binding import SignalDefinition, _identity
from ..core.decoded_binding import DecodedBindings, DecodedSourceEvidence
from ..core.declarations import DeclarationBindings, DeclaredSource
from ..core.types import SignalDType
from ..results.errors import ResultClosedError, ResultFormatError
from ..results.spool import _cleanup_owner, _reserve_owned_ram, _release_owned_ram
from ..sources.descriptions import describe_fields, source_timebase_identity
from ..sources.models import ReadRequest, SourceDescription
from .history import DecodedHistoryStore, _metadata_bytes
from .history_records import HistoryProgress, HistorySample
```

</details>

<a id="api-_fingerprint_value"></a>
## `_fingerprint_value`

把已校验冻结元数据转换为纯标量/tuple，不丢字段或来源定位。

```python
_fingerprint_value(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|object|是|无|位置或关键字。信号描述或请求的元数据树，可包含原生标量、元组和创建后不可修改的对象；递归生成可重复计算的身份材料。|

### 返回说明

_identity支持的不可变树。

### 异常说明

TypeError为未声明结构；调用方已申请元数据构造预算。

本函数直接报告的具体错误：

- `TypeError`：运行绑定元数据含未支持类型。

源码：[`src/chronaxis/execution/bindings.py:32`](../../../src/chronaxis/execution/bindings.py#L32)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_fingerprint"></a>
## `_fingerprint`

计算完整带有明确类型的树摘要。

```python
_fingerprint(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|object|是|无|位置或关键字。已冻结的绑定元数据树；根据内容计算摘要，用于检查绑定是否在执行期间变化。|

### 返回说明

SHA256文本。

### 异常说明

树/分配错误。

源码：[`src/chronaxis/execution/bindings.py:52`](../../../src/chronaxis/execution/bindings.py#L52)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-DecodedBindingLease"></a>
## `DecodedBindingLease`

从首次预约到返回绑定持有唯一真实费用及当前回放reader。

_cost/_held_cost只含工厂原固定金额；_reader拥有独立FD及它自己的费用。
_bindings仅在完整EOF和当前reader清完后开放。_closing/_failed期间禁止借出，
直到实际reader和固定费都清完才closed，不关闭借用history/scan或删除文件。

```python
DecodedBindingLease(budget)
```


源码：[`src/chronaxis/execution/bindings.py:57`](../../../src/chronaxis/execution/bindings.py#L57)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-DecodedBindingLease-__init__"></a>
### `DecodedBindingLease.__init__`

在首次外部操作前初始化真实责任槽，不申请预算或打开文件。

```python
DecodedBindingLease.__init__(budget)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|ResourceBudget|是|无|位置或关键字。本次运行共用的ResourceBudget对象，用于检查内存和临时磁盘用量。当前对象在分配前申请额度，用完后归还；同一次运行的组件应使用同一个对象。|

#### 返回说明

尚未取得固定费或完成绑定的lease。

#### 异常说明

无主动异常；构造不接已经付费的裸金额，也不复制样本。

源码：[`src/chronaxis/execution/bindings.py:65`](../../../src/chronaxis/execution/bindings.py#L65)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-DecodedBindingLease-bindings"></a>
### `DecodedBindingLease.bindings`

读取不可变运行绑定。

```python
DecodedBindingLease.bindings: DecodedBindings
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

DecodedBindings。

#### 异常说明

ResultClosedError为关闭。

本函数直接报告的具体错误：

- `ResultClosedError`：解码运行绑定未完成、已关闭或正在清理。

返回类型：[DecodedBindings](chronaxis.core.decoded_binding.md#api-DecodedBindings)。

源码：[`src/chronaxis/execution/bindings.py:79`](../../../src/chronaxis/execution/bindings.py#L79)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-DecodedBindingLease-closed"></a>
### `DecodedBindingLease.closed`

读取lease状态。

```python
DecodedBindingLease.closed: bool
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

返回类型：bool。

源码：[`src/chronaxis/execution/bindings.py:86`](../../../src/chronaxis/execution/bindings.py#L86)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-DecodedBindingLease-_close_reader"></a>
### `DecodedBindingLease._close_reader`

关闭本lease唯一实际reader，失败仍保留未完成的子责任。

```python
DecodedBindingLease._close_reader()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原reader.close错误传播；完成后取消不留重复释放槽。

源码：[`src/chronaxis/execution/bindings.py:90`](../../../src/chronaxis/execution/bindings.py#L90)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-DecodedBindingLease-_clear_temporary"></a>
### `DecodedBindingLease._clear_temporary`

结束有限工厂临时引用，不关闭借用对象。

```python
DecodedBindingLease._clear_temporary()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

无主动异常；不遍历原rows或删除历史。

源码：[`src/chronaxis/execution/bindings.py:107`](../../../src/chronaxis/execution/bindings.py#L107)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-DecodedBindingLease-close"></a>
### `DecodedBindingLease.close`

先关真实reader，再丢自有元数据并逐笔归还固定费。

```python
DecodedBindingLease.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None，完成后幂等。

#### 异常说明

原FD/预算错误可重试，释放后取消不重复扣账。

#### 副作用说明

只关闭本lease的当前reader，不关闭调用方history/scan/其他reader。

源码：[`src/chronaxis/execution/bindings.py:115`](../../../src/chronaxis/execution/bindings.py#L115)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_require_empty_source_scan"></a>
## `_require_empty_source_scan`

用本历史的真实扫描证明无字段来源的完整时钟，不从空描述猜测。

```python
_require_empty_source_scan(source, history, observed_scans)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|[DeclaredSource](chronaxis.core.declarations.md#api-DeclaredSource)|是|无|位置或关键字。source为原DeclaredSource|
|`history`|[DecodedHistoryStore](chronaxis.execution.history.md#api-DecodedHistoryStore)|是|无|位置或关键字。本次读取建立的信号历史仓。写入已经结束；分析从仓内回读，不重新打开原始日志。|
|`observed_scans`|tuple[[ObservedSourceScan](chronaxis.execution.observed_ingestion.md#api-ObservedSourceScan), ...]|是|无|位置或关键字。各来源的实际扫描记录；检查无样本的来源也有相应读取证据，不能把未读误写成空数据。|

### 返回说明

返回None，不返回额外的计算值。

### 异常说明

ValueError/ResultClosedError为缺失、重复、失效或不对应的证明。
不重新读取原CSV，不复制原行；后续工厂仍须逐源核当前历史文件的真实EOF。

源码：[`src/chronaxis/execution/bindings.py:134`](../../../src/chronaxis/execution/bindings.py#L134)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-require_decoded_source_contract"></a>
## `require_decoded_source_contract`

只核一来源的声明、实际描述和请求合同，保留所有原信号定义。

```python
require_decoded_source_contract(declarations: DeclarationBindings, source: DeclaredSource, description: SourceDescription, request: ReadRequest) -> dict[str, SignalDefinition]
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`declarations`|[DeclarationBindings](chronaxis.core.declarations.md#api-DeclarationBindings)|是|无|位置或关键字。当前计划的静态来源和信号声明，用来核对实际读取合同。|
|`source`|[DeclaredSource](chronaxis.core.declarations.md#api-DeclaredSource)|是|无|位置或关键字。当前计划中的来源声明，必须属于declarations；与实际description和request逐项核对。|
|`description`|[SourceDescription](chronaxis.sources.models.md#api-SourceDescription)|是|无|位置或关键字。来源实际返回的字段、类型和时间描述，不能用计划声明冒充读取结果。|
|`request`|[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)|是|无|位置或关键字。本来源真正使用的读取请求；检查所需字段与描述一致。|

### 返回说明

该来源全部别名到原SignalDefinition对象的dict；不裁成表达式依赖子集，
    不生成DecodedBindings、DecodedSourceEvidence或假历史SHA。

### 异常说明

TypeError为非规定模型；ValueError为会话、domain、来源、完整时钟、
    投影或字段/类型/单位/完整转换指纹不符。分配和取消错误原样传播。

### 副作用说明

无文件、读取、预算或数值操作。调用方预付有限元数据工作区并负责后续
    样本、全量观测和真实EOF证明；公共历史绑定仍必须完整核验实际磁盘文件。

返回类型：dict[str, [SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)]。

源码：[`src/chronaxis/execution/bindings.py:168`](../../../src/chronaxis/execution/bindings.py#L168)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-bind_decoded_history"></a>
## `bind_decoded_history`

先核对当前契约，再完整重放所有来源，只有实际EOF校验后才返回运行绑定。

```python
bind_decoded_history(declarations: DeclarationBindings, history: DecodedHistoryStore, *, observed_scans=()) -> DecodedBindingLease
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`declarations`|[DeclarationBindings](chronaxis.core.declarations.md#api-DeclarationBindings)|是|无|位置或关键字。declarations当前配置声明|
|`history`|[DecodedHistoryStore](chronaxis.execution.history.md#api-DecodedHistoryStore)|是|无|位置或关键字。history该会话已seal的新历史，不能是building/closed|
|`observed_scans`|tuple|否|()|仅关键字。observed_scans可选真实完成扫描tuple，只为无声明字段来源补完整时钟证明。|

### 返回说明

DecodedBindingLease，样本不保留，来源摘要/计数/投影/EOF事实纳入bindings身份。

### 异常说明

契约/损坏/预算/文件/取消错误原样传播；持续清理失败由原异常的
    decoded_binding_lease_cleanup_owner持真实reader及费用，恢复后可close。

返回类型：[DecodedBindingLease](chronaxis.execution.bindings.md#api-DecodedBindingLease)。

源码：[`src/chronaxis/execution/bindings.py:221`](../../../src/chronaxis/execution/bindings.py#L221)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
