# `chronaxis.legacy.message_store`

把逐报文解码结果写入JSONL文件，随后按顺序读取，供旧版指标对照计算使用。写入时传入LegacyDecodedFrame、已换算的整数纳秒时间及时间量化信息；本模块不筛选、去重或再次换算时间和值，也不执行分析规则。

原始解码字段中的0和False会保留；非有限数值也保留相应诊断。单条内部记录有64 KiB上限，外层存储记录另加1024字节（含换行），不改变原进程通信格式。

只有整条记录写成功后才更新数量和校验值。写入失败后不能继续追加；只有写入文件关闭成功，才能seal结束写入。seal不代表原数据源已经读完。读取器须读到末尾、核对数量和校验值并关闭成功后，才将verified_eof标为True。

sparse_sequences启用时，可以只保存选中的报文，但必须保留它们严格递增的原编号；此时数量和校验值只描述已保存的报文。close关闭本对象的文件句柄并释放对应内存；磁盘文件仍保留，已占磁盘额度也不会因此归还。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[LegacyDecodedFrame](chronaxis.legacy.records.md#api-LegacyDecodedFrame)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[ResultFormatError](chronaxis.results.errors.md#api-ResultFormatError)

## 对象导航

|对象|用途|
|---|---|
|[`_clear_records_traceback`](#api-_clear_records_traceback)|断开当前错误中已结束records函数的临时引用，保原错误及traceback结构。|
|[`StoredDecodedMessage`](#api-StoredDecodedMessage)|冻结一条已映射时间的完整解码返回，不制造旧或新求值序号。|
|[`StoredDecodedMessage.__post_init__`](#api-StoredDecodedMessage-__post_init__)|核对单条存储模型，保原decoded引用及独立端点范围。|
|[`_encode_row`](#api-_encode_row)|分别严格编码小外壳和原decoded包，再拼固定的decoded末字段。|
|[`_decode_row`](#api-_decode_row)|在明确磁盘上限内拆固定边界，分别调用原严格包解析器。|
|[`DecodedMessageStore`](#api-DecodedMessageStore)|拥有一个新JSONL、封口事实和所有独立reader的实际资源责任。|
|[`DecodedMessageStore.__init__`](#api-DecodedMessageStore-__init__)|预付有限状态并在显式全新目录打开唯一writer，拒绝已有目录。|
|[`DecodedMessageStore.line_limit`](#api-DecodedMessageStore-line_limit)|读取完整成功写入行的实际最大字节数，空仓取1以保持有限读上界。|
|[`DecodedMessageStore.closed`](#api-DecodedMessageStore-closed)|读取实际完整关闭事实；|
|[`DecodedMessageStore.spool_bytes`](#api-DecodedMessageStore-spool_bytes)|读取本owner累计磁盘预留；|
|[`DecodedMessageStore._require`](#api-DecodedMessageStore-_require)|校验活owner及所需构建状态，不把关闭或poison伪装成空流。|
|[`DecodedMessageStore._fail`](#api-DecodedMessageStore-_fail)|保原异常并poison，有限尝试清理，持续失败保最高真实仓owner。|
|[`DecodedMessageStore._reserve_spool`](#api-DecodedMessageStore-_reserve_spool)|写入前累计本笔磁盘预留，更新后取消也记录实际归属且不倒扣文件。|
|[`DecodedMessageStore._write_pending`](#api-DecodedMessageStore-_write_pending)|处理真实短写，并在错误传播前释放所有新建memoryview引用。|
|[`DecodedMessageStore.append`](#api-DecodedMessageStore-append)|完整保存一次原yield，原序和完整写入成立后才推进count/SHA。|
|[`DecodedMessageStore._close_writer`](#api-DecodedMessageStore-_close_writer)|按真实FD关闭事实清writer槽，持续close前失败保留原handle。|
|[`DecodedMessageStore.seal`](#api-DecodedMessageStore-seal)|flush并实际关闭writer后才固定SHA及sealed，不证明原来源EOF。|
|[`DecodedMessageStore.iter_records`](#api-DecodedMessageStore-iter_records)|创建独立有预算原序reader，构造未返回责任先由本父真实槽保存。|
|[`DecodedMessageStore.close`](#api-DecodedMessageStore-close)|可重试关闭所有自有stream及实际费用，保留文件与累计磁盘申请。|
|[`_DecodedMessageReader`](#api-_DecodedMessageReader)|拥有独立FD、SHA/count和有界单行空间，不持有已交付记录列表。|
|[`_DecodedMessageReader.__init__`](#api-_DecodedMessageReader-__init__)|先安装真实未返回子槽，再预约、打开和登记独立reader。|
|[`_DecodedMessageReader.__iter__`](#api-_DecodedMessageReader-__iter__)|返回同一独立位置；|
|[`_DecodedMessageReader.__next__`](#api-_DecodedMessageReader-__next__)|限长读一行并核原序，完整EOF且成功close后才产生verified_eof。|
|[`_DecodedMessageReader.close`](#api-_DecodedMessageReader-close)|只关闭本reader，可从持续真实FD或预算失败恢复而不影响其他位置。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from ..core.validation import require_identifier, require_text
from ..results.budget import ResourceBudget, _cleanup_owner, _release_owned_ram, _reserve_owned_ram
from ..results.errors import ResultClosedError, ResultFormatError
from ..timebase.conversion import require_int64_ns
from .records import MAX_WIRE_BYTES, LegacyDecodedFrame, _decoded_from_packet, decoded_to_dict
from .records import decode_packet, encode_packet
```

</details>

<a id="api-_clear_records_traceback"></a>
## `_clear_records_traceback`

断开当前错误中已结束records函数的临时引用，保原错误及traceback结构。

```python
_clear_records_traceback(exc: BaseException) -> None
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`exc`|BaseException|是|无|位置或关键字。本次操作的原异常，供附加关闭失败信息并保留原因链。不要用错误字符串代替异常对象。|

### 返回说明

None；只清精确chronaxis.legacy.records模块的已结束frame局部引用。

### 异常说明

活跃frame.clear的RuntimeError表示不可清，原样跳过；不递归cause/context，
    不清用户、测试、stdlib、CAN或本仓活跃帧，也不删JSON/Unicode错误诊断字段。

返回类型：None。

源码：[`src/chronaxis/legacy/message_store.py:43`](../../../src/chronaxis/legacy/message_store.py#L43)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-StoredDecodedMessage"></a>
## `StoredDecodedMessage`

冻结一条已映射时间的完整解码返回，不制造旧或新求值序号。

time_ns仅按共享时间协议规范，time_quantized必须由调用方明确提供。
decoded保原LegacyDecodedFrame对象；合法值域沿原records，不额外开放
None/str解码值。原channel的None/str/int类型不受目标帧通道规则改写。

```python
class StoredDecodedMessage
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|调用方显式映射后的会话坐标，不在仓中再次加偏移。|
|`time_quantized`|bool|是|无|原转换的量化事实，不由浮点时间猜测。|
|`decoded`|[LegacyDecodedFrame](chronaxis.legacy.records.md#api-LegacyDecodedFrame)|是|无|一次原yield和parse的完整冻结返回。|

源码：[`src/chronaxis/legacy/message_store.py:64`](../../../src/chronaxis/legacy/message_store.py#L64)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-StoredDecodedMessage-__post_init__"></a>
### `StoredDecodedMessage.__post_init__`

核对单条存储模型，保原decoded引用及独立端点范围。

```python
StoredDecodedMessage.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无，读取三个构造字段。

#### 返回说明

None；只将time_ns规范成原生int，不重建decoded或计算时间跨度。

#### 异常说明

TypeError为类型不符；TimeOverflowError为时间超int64。

本函数直接报告的具体错误：

- `TypeError`：time_quantized必须为原生bool。
- `TypeError`：decoded必须为LegacyDecodedFrame。

返回类型：None。

源码：[`src/chronaxis/legacy/message_store.py:76`](../../../src/chronaxis/legacy/message_store.py#L76)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_encode_row"></a>
## `_encode_row`

分别严格编码小外壳和原decoded包，再拼固定的decoded末字段。

```python
_encode_row(record: LegacyDecodedFrame, time_ns: int, time_quantized: bool) -> bytes
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`record`|[LegacyDecodedFrame](chronaxis.legacy.records.md#api-LegacyDecodedFrame)|是|无|位置或关键字。record为原冻结返回|
|`time_ns`|int|是|无|位置或关键字。当前处理时刻，以整数纳秒表示，须在int64范围内。例如1秒写1_000_000_000；不是浮点秒。|
|`time_quantized`|bool|是|无|位置或关键字。time_ns和time_quantized已经由append校验。|

### 返回说明

bytes；完整JSON对象加换行，原decoded payload不超过MAX_WIRE_BYTES。

### 异常说明

原records类型、限额、编码、分配或取消异常，不修改全局wire限额。

返回类型：bytes。

源码：[`src/chronaxis/legacy/message_store.py:92`](../../../src/chronaxis/legacy/message_store.py#L92)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_decode_row"></a>
## `_decode_row`

在明确磁盘上限内拆固定边界，分别调用原严格包解析器。

```python
_decode_row(payload: bytes) -> StoredDecodedMessage
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`payload`|bytes|是|无|位置或关键字。payload为带完整换行的有界磁盘行，decoded必须为最后字段。|

### 返回说明

StoredDecodedMessage，原diagnostic标签按现records模型恢复。

### 异常说明

ResultFormatError为外壳、重复/多余字段、原包或模型不合法；
    内存或取消错误保持原样，不用不受限JSON解析绕过IPC边界。

本函数直接报告的具体错误：

- `ResultFormatError`：解码仓行缺少完整外层或换行。
- `ResultFormatError`：解码仓固定decoded边界缺失或header超限。
- `ResultFormatError`：解码仓外壳字段缺失、多余或decoded位置错误。
- `ResultFormatError`：解码仓store_version必须为原生整数1。
- `ResultFormatError`：解码仓time_quantized必须为原生bool。
- `ResultFormatError`：解码仓行结构或原decoded包损坏。

返回类型：[StoredDecodedMessage](chronaxis.legacy.message_store.md#api-StoredDecodedMessage)。

源码：[`src/chronaxis/legacy/message_store.py:117`](../../../src/chronaxis/legacy/message_store.py#L117)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-DecodedMessageStore"></a>
## `DecodedMessageStore`

拥有一个新JSONL、封口事实和所有独立reader的实际资源责任。

state为building/sealed/failed/cancelled；closed仅在自有FD和费用全部完成后真。
_pending_reader在子构造副作用前安装，_readers只保活reader。固定/append槽
与累计_spool_bytes各自记真实交易，不由共用的资源用量记录余额猜测本owner归属。

```python
DecodedMessageStore(budget, work_dir, source_name, session_id, *, decoder_profile, read_identity, max_row_bytes=MAX_DECODED_MESSAGE_ROW_BYTES, sparse_sequences=False, integrity=True)
```


源码：[`src/chronaxis/legacy/message_store.py:161`](../../../src/chronaxis/legacy/message_store.py#L161)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-DecodedMessageStore-__init__"></a>
### `DecodedMessageStore.__init__`

预付有限状态并在显式全新目录打开唯一writer，拒绝已有目录。

```python
DecodedMessageStore.__init__(budget, work_dir, source_name, session_id, *, decoder_profile, read_identity, max_row_bytes=MAX_DECODED_MESSAGE_ROW_BYTES, sparse_sequences=False, integrity=True)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)|是|无|位置或关键字。本次运行共用的ResourceBudget对象，用于检查内存和临时磁盘用量。当前对象在分配前申请额度，用完后归还；同一次运行的组件应使用同一个对象。|
|`work_dir`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。本次运行独占的工作目录，用来保存中间文件。自行指定时要求尚不存在；不会覆盖旧目录。|
|`source_name`|str|是|无|位置或关键字。计划中已声明的来源名，例如bus；不是信号别名。|
|`session_id`|str|是|无|位置或关键字。本次会话的名字，用来防止把不同试验的数据混在一起。|
|`decoder_profile`|str|是|无|仅关键字。decoder_profile/read_identity为原生非空文本|
|`read_identity`|str|是|无|仅关键字。这一次实际读取的唯一标识；不同次读取即使文件同名也不能混用此标识。|
|`max_row_bytes`|int|否|MAX_DECODED_MESSAGE_ROW_BYTES|仅关键字。max_row_bytes为     1至MAX_DECODED_MESSAGE_ROW_BYTES，包含换行|
|`sparse_sequences`|bool|否|False|仅关键字。sparse_sequences显式允许原序号有间隔，     仍严格递增，count/SHA仅表示实际保存的记录，默认仍要求从0连续。|
|`integrity`|bool|否|True|仅关键字。是否执行本对象的额外内容摘要或认证核验；False仍保留结构、类型、预算及必要文件变化检查。|

#### 返回说明

building仓；不读取BLF/DBC或证明来源EOF。

#### 异常说明

类型、路径、预算、文件或取消原错；持续清理失败保最高
    decoded_message_store_cleanup_owner，恢复后对同一owner.close。

源码：[`src/chronaxis/legacy/message_store.py:169`](../../../src/chronaxis/legacy/message_store.py#L169)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-DecodedMessageStore-line_limit"></a>
### `DecodedMessageStore.line_limit`

读取完整成功写入行的实际最大字节数，空仓取1以保持有限读上界。

```python
DecodedMessageStore.line_limit
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

正int，只由本仓成功append推进；公开硬限仍为max_row_bytes。

#### 异常说明

无；文件损坏、未完成写入和外部stat都不会提高此值。

源码：[`src/chronaxis/legacy/message_store.py:231`](../../../src/chronaxis/legacy/message_store.py#L231)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-DecodedMessageStore-closed"></a>
### `DecodedMessageStore.closed`

读取实际完整关闭事实；

```python
DecodedMessageStore.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无；

#### 返回说明

bool；

#### 异常说明

无。

源码：[`src/chronaxis/legacy/message_store.py:240`](../../../src/chronaxis/legacy/message_store.py#L240)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-DecodedMessageStore-spool_bytes"></a>
### `DecodedMessageStore.spool_bytes`

读取本owner累计磁盘预留；

```python
DecodedMessageStore.spool_bytes
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无；

#### 返回说明

bytes整数；

#### 异常说明

无。

源码：[`src/chronaxis/legacy/message_store.py:245`](../../../src/chronaxis/legacy/message_store.py#L245)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-DecodedMessageStore-_require"></a>
### `DecodedMessageStore._require`

校验活owner及所需构建状态，不把关闭或poison伪装成空流。

```python
DecodedMessageStore._require(state)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`state`|str|是|无|位置或关键字。期望的仓状态："building"表示仍可追加记录，"sealed"表示已经结束写入、可以回读；当前状态不匹配时报错。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ResultClosedError为关闭中；RuntimeError为状态不匹配。

本函数直接报告的具体错误：

- `ResultClosedError`：解码仓已关闭或正在清理。

源码：[`src/chronaxis/legacy/message_store.py:249`](../../../src/chronaxis/legacy/message_store.py#L249)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-DecodedMessageStore-_fail"></a>
### `DecodedMessageStore._fail`

保原异常并poison，有限尝试清理，持续失败保最高真实仓owner。

```python
DecodedMessageStore._fail(exc)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`exc`|BaseException|是|无|位置或关键字。本次操作的原异常，供附加关闭失败信息并保留原因链。不要用错误字符串代替异常对象。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

清理副错只加notes，不覆盖同一普通错误、KeyboardInterrupt或SystemExit。

源码：[`src/chronaxis/legacy/message_store.py:260`](../../../src/chronaxis/legacy/message_store.py#L260)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-DecodedMessageStore-_reserve_spool"></a>
### `DecodedMessageStore._reserve_spool`

写入前累计本笔磁盘预留，更新后取消也记录实际归属且不倒扣文件。

```python
DecodedMessageStore._reserve_spool(amount)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`amount`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原配额或取消错误；未入账不增加本owner累计。

源码：[`src/chronaxis/legacy/message_store.py:270`](../../../src/chronaxis/legacy/message_store.py#L270)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-DecodedMessageStore-_write_pending"></a>
### `DecodedMessageStore._write_pending`

处理真实短写，并在错误传播前释放所有新建memoryview引用。

```python
DecodedMessageStore._write_pending()
```

参数：无显式参数。


#### 参数说明

无；读取本owner已预付、已预约磁盘的_pending_payload。

#### 返回说明

None，全部字节已交真实writer。

#### 异常说明

原写入/取消错误或OSError无推进；失败前缀由父保留并poison。

本函数直接报告的具体错误：

- `OSError`：解码仓写入未推进或返回非法长度。

源码：[`src/chronaxis/legacy/message_store.py:283`](../../../src/chronaxis/legacy/message_store.py#L283)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-DecodedMessageStore-append"></a>
### `DecodedMessageStore.append`

完整保存一次原yield，原序和完整写入成立后才推进count/SHA。

```python
DecodedMessageStore.append(record, time_ns, *, time_quantized)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`record`|[LegacyDecodedFrame](chronaxis.legacy.records.md#api-LegacyDecodedFrame)|是|无|位置或关键字。record为LegacyDecodedFrame|
|`time_ns`|int|是|无|位置或关键字。当前处理时刻，以整数纳秒表示，须在int64范围内。例如1秒写1_000_000_000；不是浮点秒。|
|`time_quantized`|bool|是|无|仅关键字。time_quantized     为明确原生bool。全部channel和值沿原模型，不套目标帧或求值规则。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

类型、时间、顺序、编码、行长、预算、磁盘、写入或取消
    原错；任意追加失败poison，最高owner可恢复但不能再seal或读前缀。

本函数直接报告的具体错误：

- `TypeError`：解码仓仅接受LegacyDecodedFrame。
- `TypeError`：time_quantized必须为原生bool。
- `ValueError`：解码仓sequence不满足声明连续/稀疏顺序或time_ns回退。
- `ValueError`：解码仓行超过max_row_bytes。

源码：[`src/chronaxis/legacy/message_store.py:311`](../../../src/chronaxis/legacy/message_store.py#L311)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-DecodedMessageStore-_close_writer"></a>
### `DecodedMessageStore._close_writer`

按真实FD关闭事实清writer槽，持续close前失败保留原handle。

```python
DecodedMessageStore._close_writer()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原FD或取消错误；实际closed后抛错也不重关已经完成的handle。

源码：[`src/chronaxis/legacy/message_store.py:349`](../../../src/chronaxis/legacy/message_store.py#L349)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-DecodedMessageStore-seal"></a>
### `DecodedMessageStore.seal`

flush并实际关闭writer后才固定SHA及sealed，不证明原来源EOF。

```python
DecodedMessageStore.seal()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None；空仓也可完整封口。

#### 异常说明

原flush、close、摘要或取消错误；poison后不再读或重试seal。

源码：[`src/chronaxis/legacy/message_store.py:363`](../../../src/chronaxis/legacy/message_store.py#L363)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-DecodedMessageStore-iter_records"></a>
### `DecodedMessageStore.iter_records`

创建独立有预算原序reader，构造未返回责任先由本父真实槽保存。

```python
DecodedMessageStore.iter_records()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

逐条StoredDecodedMessage reader；各自位置互不干扰。

#### 异常说明

状态、预算、打开、登记或取消原错，最高仓owner可恢复全部实际子资源。

源码：[`src/chronaxis/legacy/message_store.py:379`](../../../src/chronaxis/legacy/message_store.py#L379)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-DecodedMessageStore-close"></a>
### `DecodedMessageStore.close`

可重试关闭所有自有stream及实际费用，保留文件与累计磁盘申请。

```python
DecodedMessageStore.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None；所有责任闭合才closed=True，重复close幂等。

#### 异常说明

首个关闭/抵销错误原样传播，其他错误只note；最高owner不变，不关闭
    借用budget或释放其他owner费用，不删除文件及已交付调用方的记录。

源码：[`src/chronaxis/legacy/message_store.py:394`](../../../src/chronaxis/legacy/message_store.py#L394)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_DecodedMessageReader"></a>
## `_DecodedMessageReader`

拥有独立FD、SHA/count和有界单行空间，不持有已交付记录列表。

verified_eof只在真实EOF、完整SHA/count和实际FD/费用/登记全部关闭后为True。
提前close不产生证明；关闭中拒绝读，未返回构造实例先由父pending槽接管。

```python
_DecodedMessageReader(owner)
```


源码：[`src/chronaxis/legacy/message_store.py:459`](../../../src/chronaxis/legacy/message_store.py#L459)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_DecodedMessageReader-__init__"></a>
### `_DecodedMessageReader.__init__`

先安装真实未返回子槽，再预约、打开和登记独立reader。

```python
_DecodedMessageReader.__init__(owner)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|[DecodedMessageStore](chronaxis.legacy.message_store.md#api-DecodedMessageStore)|是|无|位置或关键字。已经结束写入且尚未关闭的消息仓；读取器从此仓按原消息顺序回读。|

#### 返回说明

None；初始化实例状态；父工厂成功返回前一直可从_pending_reader找到本实例。

#### 异常说明

原预算、打开、登记或取消错误，由父工厂保原错并统一清理最高owner。

源码：[`src/chronaxis/legacy/message_store.py:466`](../../../src/chronaxis/legacy/message_store.py#L466)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_DecodedMessageReader-__iter__"></a>
### `_DecodedMessageReader.__iter__`

返回同一独立位置；

```python
_DecodedMessageReader.__iter__()
```

参数：无显式参数。


#### 参数说明

无；

#### 返回说明

返回当前对象本身。后续迭代或with语句使用的仍是同一个对象。

#### 异常说明

无。

源码：[`src/chronaxis/legacy/message_store.py:487`](../../../src/chronaxis/legacy/message_store.py#L487)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_DecodedMessageReader-__next__"></a>
### `_DecodedMessageReader.__next__`

限长读一行并核原序，完整EOF且成功close后才产生verified_eof。

```python
_DecodedMessageReader.__next__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

StoredDecodedMessage；最后一行交付仍未验证EOF。

#### 异常说明

StopIteration仅在关闭或真正完成；ResultFormatError为损坏；原IO、
    预算或取消错误保留并poison父，最高decoded_message_store_cleanup_owner可恢复。

源码：[`src/chronaxis/legacy/message_store.py:491`](../../../src/chronaxis/legacy/message_store.py#L491)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_DecodedMessageReader-close"></a>
### `_DecodedMessageReader.close`

只关闭本reader，可从持续真实FD或预算失败恢复而不影响其他位置。

```python
_DecodedMessageReader.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None；FD、费用及父登记都成功完成才closed=True。

#### 异常说明

原FD、抵销、登记或取消错误，最高父owner可达；真实已关闭handle不重关，
    已抵销费用不重扣，提前close不设置verified_eof。

源码：[`src/chronaxis/legacy/message_store.py:537`](../../../src/chronaxis/legacy/message_store.py#L537)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
