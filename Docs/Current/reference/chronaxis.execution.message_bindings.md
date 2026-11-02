# chronaxis.execution.message_bindings

检查已保存的逐报文数据，并建立MessageBindings，供旧版指标计算使用。输入是MessageDeclarations及已结束写入的DecodedMessageStore；检查内容包括完整读取、SHA校验、报文数量和文件末尾。只有检查成功并关闭检查用读取器后，才返回绑定。

记录的首末时间来自全部已保存报文；空存储返回None。这里不按别名筛选报文，不要求每个字段都至少出现一次，也不重新读取BLF、DBC或普通信号历史。请求窗口、旧值保持、过期判断和去重由各自的处理步骤负责。

同一存储已有成功检查记录时，可以复用该结果，但仍核对资源管理器、写入完成状态和文件。每个新绑定单独登记内存；后续计算读取数据时仍检查完整性。profile和读取方式等标记用于追溯，不能单凭这些标记证明数据来自CAN。

绑定只关闭自己创建的读取器并释放自身内存，不删除文件或关闭调用方的共享资源管理器。若读取器出错并引发存储清理，应沿异常中保留的对象继续关闭，不能假定传入存储在失败后一定仍可用。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[DecodedMessageStore](chronaxis.legacy.message_store.md#api-DecodedMessageStore)、[MessageBindings](chronaxis.core.message_binding.md#api-MessageBindings)、[MessageDeclarations](chronaxis.core.message_binding.md#api-MessageDeclarations)、[MessageSourceEvidence](chronaxis.core.message_binding.md#api-MessageSourceEvidence)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[ResultFormatError](chronaxis.results.errors.md#api-ResultFormatError)、[StoredDecodedMessage](chronaxis.legacy.message_store.md#api-StoredDecodedMessage)

## 对象导航

|对象|用途|
|---|---|
|[`_fixed_estimate`](#api-_fixed_estimate)|在创建本层身份副本前按原生长度估算有限元数据及编码临时空间。|
|[`_file_snapshot`](#api-_file_snapshot)|记录新消息暂存文件的有限状态，防止把已变化路径当作先前核验的同一文件。|
|[`MessageBindingLease`](#api-MessageBindingLease)|持有自有reader和固定费，完整核验或同仓复用后借出不可变消息运行绑定。|
|[`MessageBindingLease.__init__`](#api-MessageBindingLease-__init__)|先安装全部责任槽，不预约费用，也不打开文件。|
|[`MessageBindingLease.bindings`](#api-MessageBindingLease-bindings)|取得完整核验后形成的不可变消息绑定，不借出半成品。|
|[`MessageBindingLease.closed`](#api-MessageBindingLease-closed)|读取本lease的实际清理状态。|
|[`MessageBindingLease._require_store`](#api-MessageBindingLease-_require_store)|核本次借用仓的当前合同及封口事实，拒绝回读期间替换元数据。|
|[`MessageBindingLease._close_reader`](#api-MessageBindingLease-_close_reader)|关闭唯一已安装的真实reader，未完成责任保在原槽供重试。|
|[`MessageBindingLease._clear_temporary`](#api-MessageBindingLease-_clear_temporary)|结束本工厂有限临时引用，不清调用方的原对象或异常traceback。|
|[`MessageBindingLease.close`](#api-MessageBindingLease-close)|只关闭本lease的实际reader，再归还逐笔自有固定费。|
|[`bind_message_store`](#api-bind_message_store)|完整核验消息仓，或在同一未变仓上借用真实已完成核验，返回独立有预算绑定。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..core.message_binding import MessageBindings, MessageDeclarations, MessageSourceEvidence
from ..legacy.message_store import DecodedMessageStore, StoredDecodedMessage
from ..results.budget import ResourceBudget, _cleanup_owner, _release_owned_ram, _reserve_owned_ram
from ..results.errors import ResultClosedError, ResultFormatError
```

</details>

<a id="api-_fixed_estimate"></a>
## `_fixed_estimate`

在创建本层身份副本前按原生长度估算有限元数据及编码临时空间。

```python
_fixed_estimate(declarations: MessageDeclarations, store: DecodedMessageStore) -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`declarations`|[MessageDeclarations](chronaxis.core.message_binding.md#api-MessageDeclarations)|是|无|位置或关键字。declarations为借用的冻结消息声明|
|`store`|[DecodedMessageStore](chronaxis.legacy.message_store.md#api-DecodedMessageStore)|是|无|位置或关键字。store为借用的活sealed仓。|

### 返回说明

保守bytes金额，不遍历原信号定义、参数树、raw_config或逐条记录。

### 异常说明

TypeError/ValueError为仓公开元数据已变成非原生文本或非法条数；
    本函数不strip、encode、repr或创建字段副本，不为估费先建立大文本。

返回类型：int。

源码：[`src/chronaxis/execution/message_bindings.py:32`](../../../src/chronaxis/execution/message_bindings.py#L32)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_file_snapshot"></a>
## `_file_snapshot`

记录新消息暂存文件的有限状态，防止把已变化路径当作先前核验的同一文件。

```python
_file_snapshot(store: DecodedMessageStore) -> tuple[int, ...]
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`store`|[DecodedMessageStore](chronaxis.legacy.message_store.md#api-DecodedMessageStore)|是|无|位置或关键字。store为已经封口的实际消息仓。|

### 返回说明

设备、文件身份、大小及系统提供的时间信息tuple。

### 异常说明

原stat错误传播。

### 边界说明

这不是持续监控或新内容摘要，计算reader仍须核完整EOF/SHA；
    stat对象及tuple在lease固定元数据预算内，不接触原BLF或DBC。

返回类型：tuple[int, ...]。

源码：[`src/chronaxis/execution/message_bindings.py:55`](../../../src/chronaxis/execution/message_bindings.py#L55)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-MessageBindingLease"></a>
## `MessageBindingLease`

持有自有reader和固定费，完整核验或同仓复用后借出不可变消息运行绑定。

_fixed_cost/_held_cost只记录本层直接交易，reader的费用由原reader独立负责。
_opening_reader标记取得子对象的窗口；未返回子仍属于借用store的真实责任槽。
_verified_*保留同一借用仓的有限核验快照，仅供建立独立新绑定，不替其他lease付款。
开始关闭或失败后不可借出bindings，只有自身子和费用都清完才closed。

```python
MessageBindingLease(budget: ResourceBudget)
```


源码：[`src/chronaxis/execution/message_bindings.py:71`](../../../src/chronaxis/execution/message_bindings.py#L71)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-MessageBindingLease-__init__"></a>
### `MessageBindingLease.__init__`

先安装全部责任槽，不预约费用，也不打开文件。

```python
MessageBindingLease.__init__(budget: ResourceBudget)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)|是|无|位置或关键字。本次运行共用的ResourceBudget对象，用于检查内存和临时磁盘用量。当前对象在分配前申请额度，用完后归还；同一次运行的组件应使用同一个对象。|

#### 返回说明

尚未完成的lease，供唯一工厂继续初始化。

#### 异常说明

TypeError为非ResourceBudget；不会接收已经支付却无owner的裸金额。

本函数直接报告的具体错误：

- `TypeError`：消息绑定lease需要ResourceBudget。

源码：[`src/chronaxis/execution/message_bindings.py:80`](../../../src/chronaxis/execution/message_bindings.py#L80)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-MessageBindingLease-bindings"></a>
### `MessageBindingLease.bindings`

取得完整核验后形成的不可变消息绑定，不借出半成品。

```python
MessageBindingLease.bindings: MessageBindings
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

原MessageBindings对象。

#### 异常说明

ResultClosedError为尚未完成、已失败、关闭中或已经关闭。

本函数直接报告的具体错误：

- `ResultClosedError`：消息运行绑定未完成、已失败或正在关闭。

返回类型：[MessageBindings](chronaxis.core.message_binding.md#api-MessageBindings)。

源码：[`src/chronaxis/execution/message_bindings.py:100`](../../../src/chronaxis/execution/message_bindings.py#L100)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-MessageBindingLease-closed"></a>
### `MessageBindingLease.closed`

读取本lease的实际清理状态。

```python
MessageBindingLease.closed: bool
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

reader和自有费用均清完时为True。

#### 异常说明

无；不把借用store是否关闭混成本lease的状态。

返回类型：bool。

源码：[`src/chronaxis/execution/message_bindings.py:112`](../../../src/chronaxis/execution/message_bindings.py#L112)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-MessageBindingLease-_require_store"></a>
### `MessageBindingLease._require_store`

核本次借用仓的当前合同及封口事实，拒绝回读期间替换元数据。

```python
MessageBindingLease._require_store() -> None
```

参数：无显式参数。


#### 参数说明

无，读取本lease保存的原store、声明和有限事实。

#### 返回说明

None；不读取源CAN或额外打开仓文件。

#### 异常说明

原仓生命周期错误；ValueError为来源、会话或预算不对应；
    ResultFormatError为本次回读前后封口事实被替换。

本函数直接报告的具体错误：

- `ValueError`：消息仓绑定的原共享budget已被替换。
- `ValueError`：消息仓来源或会话与当前消息声明不符。
- `ResultFormatError`：消息仓回读期间封口身份或条数已改变。

返回类型：None。

源码：[`src/chronaxis/execution/message_bindings.py:120`](../../../src/chronaxis/execution/message_bindings.py#L120)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-MessageBindingLease-_close_reader"></a>
### `MessageBindingLease._close_reader`

关闭唯一已安装的真实reader，未完成责任保在原槽供重试。

```python
MessageBindingLease._close_reader() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None；正常EOF已关闭的reader也按原幂等接口收尾。

#### 异常说明

原FD或费用释放错误；实际关闭后才取消时清槽，避免重复抵销。

返回类型：None。

源码：[`src/chronaxis/execution/message_bindings.py:141`](../../../src/chronaxis/execution/message_bindings.py#L141)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-MessageBindingLease-_clear_temporary"></a>
### `MessageBindingLease._clear_temporary`

结束本工厂有限临时引用，不清调用方的原对象或异常traceback。

```python
MessageBindingLease._clear_temporary() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

无主动异常；借用store与声明只解除引用，不执行它们的close。

返回类型：None。

源码：[`src/chronaxis/execution/message_bindings.py:160`](../../../src/chronaxis/execution/message_bindings.py#L160)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-MessageBindingLease-close"></a>
### `MessageBindingLease.close`

只关闭本lease的实际reader，再归还逐笔自有固定费。

```python
MessageBindingLease.close() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None，实际完成后重复调用幂等。

#### 异常说明

原FD或预算取消错误，可恢复后在同一owner上重试；
    释放后取消按实际槽记账，不重复抵销其他借用费用。

#### 副作用说明

不显式关闭借用仓、其他reader或共享budget，不删除任何文件。

返回类型：None。

源码：[`src/chronaxis/execution/message_bindings.py:170`](../../../src/chronaxis/execution/message_bindings.py#L170)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-bind_message_store"></a>
## `bind_message_store`

完整核验消息仓，或在同一未变仓上借用真实已完成核验，返回独立有预算绑定。

```python
bind_message_store(declarations: MessageDeclarations, store: DecodedMessageStore, *, verified_by: MessageBindingLease | None=None) -> MessageBindingLease
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`declarations`|[MessageDeclarations](chronaxis.core.message_binding.md#api-MessageDeclarations)|是|无|位置或关键字。declarations为冻结MessageDeclarations|
|`store`|[DecodedMessageStore](chronaxis.legacy.message_store.md#api-DecodedMessageStore)|是|无|位置或关键字。store为调用方拥有的实际     DecodedMessageStore，须仍活且sealed，source/session与原声明一致|
|`verified_by`|[MessageBindingLease](chronaxis.execution.message_bindings.md#api-MessageBindingLease) &#124; None|否|None|仅关键字。verified_by     可为已成功且未关闭的真实lease，仅同一仓/预算/封口及文件状态一致时复用核验结果。 None表示本次自行完整核验消息仓。|

### 返回说明

MessageBindingLease，其bindings包含实际仓SHA/count/首末及显式标签；
    空仓首末为None，所有decoded帧都计数，不按字段缺失或请求范围筛掉。

### 异常说明

TypeError/ValueError为类型及声明不对应；原仓状态、IO、预算、取消错误
    原样传播；ResultFormatError为未完成真实EOF或当前封口事实变化。
    原错误附message_binding_lease_cleanup_owner；未返回reader的责任保在
    原decoded_message_store_cleanup_owner，不擅自关闭借用父仓。

返回类型：[MessageBindingLease](chronaxis.execution.message_bindings.md#api-MessageBindingLease)。

源码：[`src/chronaxis/execution/message_bindings.py:196`](../../../src/chronaxis/execution/message_bindings.py#L196)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
