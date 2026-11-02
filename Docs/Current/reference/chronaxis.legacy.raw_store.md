# chronaxis.legacy.raw_store

按首次CAN读取的原序暂存完整报文，供片段发布回读而不重扫原输入。

RawFrameStore借用ResourceBudget，append接收同次LegacyDecodedFrame和已显式映射的
int64纳秒，仅保存sequence/time_ns/原frame，不存decoded.values。每行是有界records
JSON包加一个换行；未知ID、同一时刻帧及全部公开写出字段保留，不排序、筛选或去重。
完整写入后才推进计数和流SHA；部分写入、预算、编码或取消错误均poison，禁止seal。
seal须真实writer关闭成功才开放原序reader；reader逐行校验结构、原序和时间，真实
EOF核条数及完整SHA，关闭也成功后才verified_eof。提前close不产生完整读取证明。

本层只使用标准库、冻结records和新分析层预算工具，不导入旧CAN库或调用解码器。
固定、append工作空间与各活reader分别预付；reader数量受共享预算约束，未保存
全部帧或全部文件路径。账本是保守估算而非整进程RSS；调用方长期保留已返回行须
自行承担空间。close只关闭自有真实FD/费用，保留文件及累计spool预留，不关借用
budget。全部槽先初始化，关闭失败可重试；原异常/KI不被清理覆盖，未返回reader
及持续失败资源从最高raw_frame_store_cleanup_owner恢复，不凭余额差补账。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[LegacyDecodedFrame](chronaxis.legacy.records.md#api-LegacyDecodedFrame)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[ResultFormatError](chronaxis.results.errors.md#api-ResultFormatError)、[StoredRawFrame](chronaxis.legacy.records.md#api-StoredRawFrame)

## 对象导航

|对象|用途|
|---|---|
|[`RawFrameStore`](#api-RawFrameStore)|拥有一个原序JSONL和所有独立reader，完成事实不等于FD已经全部关闭。|
|[`RawFrameStore.__init__`](#api-RawFrameStore-__init__)|预付有限状态，在显式新目录独占打开原始帧暂存。|
|[`RawFrameStore.closed`](#api-RawFrameStore-closed)|查看本对象是否已经完成关闭。|
|[`RawFrameStore.spool_bytes`](#api-RawFrameStore-spool_bytes)|返回本对象累计申请的临时磁盘字节数。|
|[`RawFrameStore._require`](#api-RawFrameStore-_require)|拒绝半关闭或错误状态，不能把poison前缀当完整输入。|
|[`RawFrameStore._fail`](#api-RawFrameStore-_fail)|保原根因、安装最高恢复owner，再有限尝试真实资源关闭。|
|[`RawFrameStore._reserve_spool`](#api-RawFrameStore-_reserve_spool)|写入前逐笔预留累计磁盘，成功后取消也记录本笔，不倒扣保留文件。|
|[`RawFrameStore.append`](#api-RawFrameStore-append)|追加同次原帧，保0起连续sequence、非递减ns及全部同一时刻/未知ID。|
|[`RawFrameStore._close_writer`](#api-RawFrameStore-_close_writer)|真实FD关闭后才清writer槽，close前持续失败保留同一handle。|
|[`RawFrameStore.seal`](#api-RawFrameStore-seal)|成功关闭writer后固定整流SHA和条数，空来源亦可完整封口。|
|[`RawFrameStore.iter_frames`](#api-RawFrameStore-iter_frames)|为已封口文件创建独立有限reader，不复用其他reader位置或原CAN输入。|
|[`RawFrameStore.close`](#api-RawFrameStore-close)|关闭本store的所有实际reader/writer及自有费用，文件和累计磁盘保留。|
|[`_RawFrameReader`](#api-_RawFrameReader)|持有一个文件位置、摘要和有界读槽，父只保实际活stream引用。|
|[`_RawFrameReader.__init__`](#api-_RawFrameReader-__init__)|先安装本父未返回槽，再预约/打开/登记真实reader。|
|[`_RawFrameReader.__iter__`](#api-_RawFrameReader-__iter__)|返回原位置。|
|[`_RawFrameReader.__next__`](#api-_RawFrameReader-__next__)|限长读取并核原序/时间，完整EOF核流身份再关闭。|
|[`_RawFrameReader.close`](#api-_RawFrameReader-close)|可重试关闭本reader，不关闭父或其他独立reader。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from hashlib import sha256
from pathlib import Path
from ..core.validation import require_identifier
from ..results.budget import ResourceBudget
from ..results.errors import ResultClosedError, ResultFormatError
from ..results.spool import _cleanup_owner, _reserve_owned_ram, _release_owned_ram
from ..timebase.conversion import require_int64_ns
from .records import MAX_WIRE_BYTES, LegacyDecodedFrame, StoredRawFrame, frame_to_dict, frame_from_dict, encode_packet, decode_packet
```

</details>

<a id="api-RawFrameStore"></a>
## `RawFrameStore`

拥有一个原序JSONL和所有独立reader，完成事实不等于FD已经全部关闭。

state为building/sealed/failed/cancelled；closed另记所有自有资源实际释放完成。
_pending_reader先安装未返回实例，_readers保存已注册实例；两者均由本父close。
固定/当前append费用是实际交易槽，累计spool只增加，不从共用的资源用量记录推测归属。

```python
RawFrameStore(budget, work_dir, source_name, *, max_row_bytes=MAX_WIRE_BYTES, integrity=True)
```


源码：[`src/chronaxis/legacy/raw_store.py:30`](../../../src/chronaxis/legacy/raw_store.py#L30)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RawFrameStore-__init__"></a>
### `RawFrameStore.__init__`

预付有限状态，在显式新目录独占打开原始帧暂存。

```python
RawFrameStore.__init__(budget, work_dir, source_name, *, max_row_bytes=MAX_WIRE_BYTES, integrity=True)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)|是|无|位置或关键字。本次运行共用的ResourceBudget对象，用于检查内存和临时磁盘用量。当前对象在分配前申请额度，用完后归还；同一次运行的组件应使用同一个对象。|
|`work_dir`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。本次运行独占的工作目录，用来保存中间文件。自行指定时要求尚不存在；不会覆盖旧目录。|
|`source_name`|str|是|无|位置或关键字。计划中已声明的来源名，例如bus；不是信号别名。|
|`max_row_bytes`|int|否|MAX_WIRE_BYTES|仅关键字。max_row_bytes为含换行行上限，1到MAX_WIRE_BYTES，默认65536。|
|`integrity`|bool|否|True|仅关键字。是否执行本对象的额外内容摘要或认证核验；False仍保留结构、类型、预算及必要文件变化检查。|

#### 返回说明

building存储。

#### 异常说明

类型/路径/预算/文件/取消原错；持续清理失败保最高owner。

本函数直接报告的具体错误：

- `TypeError`：原始帧暂存需ResourceBudget及显式新目录。
- `ValueError`：原始帧行上限需1到MAX_WIRE_BYTES的原生int。
- `ValueError`：原始帧暂存禁止写入RefProjects。

源码：[`src/chronaxis/legacy/raw_store.py:38`](../../../src/chronaxis/legacy/raw_store.py#L38)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RawFrameStore-closed"></a>
### `RawFrameStore.closed`

查看本对象是否已经完成关闭。

```python
RawFrameStore.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无；费用/FD未清不能为True。

源码：[`src/chronaxis/legacy/raw_store.py:81`](../../../src/chronaxis/legacy/raw_store.py#L81)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RawFrameStore-spool_bytes"></a>
### `RawFrameStore.spool_bytes`

返回本对象累计申请的临时磁盘字节数。

```python
RawFrameStore.spool_bytes
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

int字节。

#### 异常说明

无。

源码：[`src/chronaxis/legacy/raw_store.py:86`](../../../src/chronaxis/legacy/raw_store.py#L86)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RawFrameStore-_require"></a>
### `RawFrameStore._require`

拒绝半关闭或错误状态，不能把poison前缀当完整输入。

```python
RawFrameStore._require(state)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`state`|str|是|无|位置或关键字。期望的仓状态："building"表示仍可追加记录，"sealed"表示已经结束写入、可以回读；当前状态不匹配时报错。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ResultClosedError/RuntimeError。

本函数直接报告的具体错误：

- `ResultClosedError`：原始帧暂存已关闭或正在清理。

源码：[`src/chronaxis/legacy/raw_store.py:90`](../../../src/chronaxis/legacy/raw_store.py#L90)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RawFrameStore-_fail"></a>
### `RawFrameStore._fail`

保原根因、安装最高恢复owner，再有限尝试真实资源关闭。

```python
RawFrameStore._fail(exc)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`exc`|BaseException|是|无|位置或关键字。本次操作的原异常，供附加关闭失败信息并保留原因链。不要用错误字符串代替异常对象。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

清理副错只加note，不替换原错或取消对象。

源码：[`src/chronaxis/legacy/raw_store.py:100`](../../../src/chronaxis/legacy/raw_store.py#L100)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RawFrameStore-_reserve_spool"></a>
### `RawFrameStore._reserve_spool`

写入前逐笔预留累计磁盘，成功后取消也记录本笔，不倒扣保留文件。

```python
RawFrameStore._reserve_spool(amount)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`amount`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原配额/取消；未成功不增加本owner金额。

源码：[`src/chronaxis/legacy/raw_store.py:109`](../../../src/chronaxis/legacy/raw_store.py#L109)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RawFrameStore-append"></a>
### `RawFrameStore.append`

追加同次原帧，保0起连续sequence、非递减ns及全部同一时刻/未知ID。

```python
RawFrameStore.append(record, time_ns)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`record`|[LegacyDecodedFrame](chronaxis.legacy.records.md#api-LegacyDecodedFrame)|是|无|位置或关键字。record为LegacyDecodedFrame|
|`time_ns`|int|是|无|位置或关键字。当前处理时刻，以整数纳秒表示，须在int64范围内。例如1秒写1_000_000_000；不是浮点秒。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原类型/顺序/编码/行长/预算/写入/取消；任何失败poison且不可seal。

本函数直接报告的具体错误：

- `TypeError`：原始帧暂存仅接受LegacyDecodedFrame。
- `ValueError`：原始帧sequence必须从0连续且时间不能回退。
- `ValueError`：原始帧编码行超过max_row_bytes。
- `OSError`：原始帧写入未推进。

源码：[`src/chronaxis/legacy/raw_store.py:121`](../../../src/chronaxis/legacy/raw_store.py#L121)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RawFrameStore-_close_writer"></a>
### `RawFrameStore._close_writer`

真实FD关闭后才清writer槽，close前持续失败保留同一handle。

```python
RawFrameStore._close_writer()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原close/取消；close后抛错也据真实closed清槽。

源码：[`src/chronaxis/legacy/raw_store.py:159`](../../../src/chronaxis/legacy/raw_store.py#L159)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RawFrameStore-seal"></a>
### `RawFrameStore.seal`

成功关闭writer后固定整流SHA和条数，空来源亦可完整封口。

```python
RawFrameStore.seal()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原flush/close/摘要/取消，失败不能读或再次seal。

源码：[`src/chronaxis/legacy/raw_store.py:171`](../../../src/chronaxis/legacy/raw_store.py#L171)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RawFrameStore-iter_frames"></a>
### `RawFrameStore.iter_frames`

为已封口文件创建独立有限reader，不复用其他reader位置或原CAN输入。

```python
RawFrameStore.iter_frames()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

逐行StoredRawFrame迭代器。

#### 异常说明

状态/预算/打开/注册/取消；
    未返回reader先在本父槽可达，持续关闭失败从最高raw_frame_store_cleanup_owner恢复。

源码：[`src/chronaxis/legacy/raw_store.py:186`](../../../src/chronaxis/legacy/raw_store.py#L186)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RawFrameStore-close"></a>
### `RawFrameStore.close`

关闭本store的所有实际reader/writer及自有费用，文件和累计磁盘保留。

```python
RawFrameStore.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None，完成后重复调用安全。

#### 异常说明

首个实际关闭/抵销错误原样传播，
    其他清理错仅note；未完槽不清，最高恢复owner就是本store，不接管共用的资源用量记录。

源码：[`src/chronaxis/legacy/raw_store.py:201`](../../../src/chronaxis/legacy/raw_store.py#L201)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_RawFrameReader"></a>
## `_RawFrameReader`

持有一个文件位置、摘要和有界读槽，父只保实际活stream引用。

关闭中禁止继续读；真实FD/本笔费用/父登记全部成功后closed。
verified_eof须真实EOF、完整SHA/count和成功关闭，不从最后一条交付推断。

```python
_RawFrameReader(owner)
```


源码：[`src/chronaxis/legacy/raw_store.py:252`](../../../src/chronaxis/legacy/raw_store.py#L252)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_RawFrameReader-__init__"></a>
### `_RawFrameReader.__init__`

先安装本父未返回槽，再预约/打开/登记真实reader。

```python
_RawFrameReader.__init__(owner)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|[RawFrameStore](chronaxis.legacy.raw_store.md#api-RawFrameStore)|是|无|位置或关键字。已经结束写入且尚未关闭的原帧仓，提供文件位置及资源额度。|

#### 返回说明

独立reader。

#### 异常说明

原预算/打开/注册/取消；
    本构造不遗失self，由父工厂统一清理并附最高store恢复属性。

源码：[`src/chronaxis/legacy/raw_store.py:259`](../../../src/chronaxis/legacy/raw_store.py#L259)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_RawFrameReader-__iter__"></a>
### `_RawFrameReader.__iter__`

返回原位置。

```python
_RawFrameReader.__iter__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回当前对象本身。后续迭代或with语句使用的仍是同一个对象。

#### 异常说明

无，不重新打开文件。

源码：[`src/chronaxis/legacy/raw_store.py:278`](../../../src/chronaxis/legacy/raw_store.py#L278)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_RawFrameReader-__next__"></a>
### `_RawFrameReader.__next__`

限长读取并核原序/时间，完整EOF核流身份再关闭。

```python
_RawFrameReader.__next__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

StoredRawFrame。

#### 异常说明

StopIteration仅完整EOF；损坏/预算/关闭/取消
    保原错且poison父，最高raw_frame_store_cleanup_owner可清全部真实资源。

源码：[`src/chronaxis/legacy/raw_store.py:282`](../../../src/chronaxis/legacy/raw_store.py#L282)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_RawFrameReader-close"></a>
### `_RawFrameReader.close`

可重试关闭本reader，不关闭父或其他独立reader。

```python
_RawFrameReader.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原FD/预算/解除登记错误，最高父恢复属性保持同一责任；
    真实FD关闭后抛取消也不重关，已释放费用不重复抵销。

源码：[`src/chronaxis/legacy/raw_store.py:321`](../../../src/chronaxis/legacy/raw_store.py#L321)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
