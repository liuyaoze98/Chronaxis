# `chronaxis.legacy.batch_read`

在共享预算内按批取得原CAN解码结果，保全量观测时间与需要的完整原记录。

复用逐条read的INIT/READY验证、实际进程关闭和失败恢复，不改变原逐条入口。
父在授予一批许可前预付两端缓冲、解析模型和时间数组的保守费用；同时只一批在途。
每批最多4096原帧且256KiB，预算较小时缩字节上限。默认同步；显式开启预取时，
当前批交付前可再预付并授权一批，使子读取与父计算重叠。取消或当前批处理失败时
可能额外读出这一批；预约/发送失败则当前批也不交付。预算不足时同步读取。
最后数据批可含真实EOF，下一次next完成退出/关闭才finished。
低层默认full/source保旧协议；auto结合固定requested范围使用v4 READY与CXB2，
原帧数独立于时间数量，计数和预取不会因跳过无用时间而丢失读取进度。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[BudgetExceededError](chronaxis.results.errors.md#api-BudgetExceededError)、[LegacyCANProcessRead](chronaxis.legacy.process_read.md#api-LegacyCANProcessRead)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[SourceReadError](chronaxis.sources.protocol.md#api-SourceReadError)

## 对象导航

|对象|用途|
|---|---|
|[`LegacyCANBatchRead`](#api-LegacyCANBatchRead)|持有当前借用结果及可选下一批许可，全部费用由共享关闭流程归还。|
|[`LegacyCANBatchRead.__init__`](#api-LegacyCANBatchRead-__init__)|保存批次上限与解码后选择，不打开文件或启动子进程。|
|[`LegacyCANBatchRead._check_ready`](#api-LegacyCANBatchRead-_check_ready)|默认沿用原v1验证；requested核v3，auto核v4及检查/时间范围。|
|[`LegacyCANBatchRead._check_ready_metadata`](#api-LegacyCANBatchRead-_check_ready_metadata)|周期只为显式请求字段核验；默认维持原元数据契约。|
|[`LegacyCANBatchRead.counters`](#api-LegacyCANBatchRead-counters)|区分批次许可上界、收到的原帧与保留记录，不把未消费批次伪称已完成。|
|[`LegacyCANBatchRead.full_check_count`](#api-LegacyCANBatchRead-full_check_count)|读取已验收批次中非原生输入执行完整检查的实际回退数。|
|[`LegacyCANBatchRead._receive_reply`](#api-LegacyCANBatchRead-_receive_reply)|在已预付的上限内接收批数据或原严格控制JSON，拒绝错误版本和超长包。|
|[`LegacyCANBatchRead.__next__`](#api-LegacyCANBatchRead-__next__)|授予一批有界许可并交付原序数据；确认真实EOF及退出后才结束迭代。|
|[`LegacyCANBatchRead._new_packet`](#api-LegacyCANBatchRead-_new_packet)|为下一原序号建立有限批次许可，不触碰管道。|
|[`LegacyCANBatchRead._set_prefetch_headroom`](#api-LegacyCANBatchRead-_set_prefetch_headroom)|更新仅供下一次额外预取的动态消费余量，不收费且不改变同步许可。|
|[`LegacyCANBatchRead._available_limit`](#api-LegacyCANBatchRead-_available_limit)|在当前共享余额中留下消费者余量，计算完整可付款的批次上限。|
|[`LegacyCANBatchRead._try_prefetch`](#api-LegacyCANBatchRead-_try_prefetch)|余量足够时全额预付并发送下一批；否则留到下一次同步读取。|
|[`LegacyCANBatchRead._release_closed_state`](#api-LegacyCANBatchRead-_release_closed_state)|共享close确认实际资源全关后清预取责任，再按原槽逐笔归还。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from functools import partial
from dataclasses import replace
from pathlib import Path
from .batch_wire import BATCH_MAGIC, DEMAND_MAGIC, HEADER, DEMAND_HEADER, MAX_BATCH_BYTES, MAX_BATCH_ROWS, MIN_BATCH_BYTES, FILE_HEADER, FILE_MAGIC, decode_batch
from .batch_worker import REQUESTED_VALUES_POLICY, batch_worker_main
from .process_read import LegacyCANProcessRead
from .records import MAX_WIRE_BYTES, decode_packet
from ..results.budget import _reserve_owned_ram, _release_owned_ram
from ..results.errors import BudgetExceededError
from ..sources.protocol import SourceReadError
```

</details>

<a id="api-LegacyCANBatchRead"></a>
## `LegacyCANBatchRead`

持有当前借用结果及可选下一批许可，全部费用由共享关闭流程归还。

_current保存已验证批次，_current_cost预付两端全部批次工作空间；
_prefetch_packet/_prefetch_cost独立持有至多一个下一批许可及其完整费用，
所有共用的资源用量记录操作均在父调用线程完成，没有后台线程预约或无界队列。
_batch_eof仅表示收到EOF候选，实际.finished仍要求子正常退出和父关闭成功。

```python
LegacyCANBatchRead(request, budget, *, frame_ids=None, batch_rows=MAX_BATCH_ROWS, consumer_headroom_bytes=0, prefetch=False, decode_scope='all', decode_frame_ids=None, input_check='full', time_scope='source', _worker_target=None, input_paths=None, decode_policy='legacy', cycle_fields=(), metadata_fields=())
```

继承关系：[LegacyCANProcessRead](chronaxis.legacy.process_read.md#api-LegacyCANProcessRead)。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/legacy/batch_read.py:27`](../../../src/chronaxis/legacy/batch_read.py#L27)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-LegacyCANBatchRead-__init__"></a>
### `LegacyCANBatchRead.__init__`

保存批次上限与解码后选择，不打开文件或启动子进程。

```python
LegacyCANBatchRead.__init__(request, budget, *, frame_ids=None, batch_rows=MAX_BATCH_ROWS, consumer_headroom_bytes=0, prefetch=False, decode_scope='all', decode_frame_ids=None, input_check='full', time_scope='source', _worker_target=None, input_paths=None, decode_policy='legacy', cycle_fields=(), metadata_fields=())
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`request`|LegacyCANRequest|是|无|位置或关键字。已经检查的旧CAN读取请求，保留原文件、DBC、解码和时间设置。|
|`budget`|ResourceBudget|是|无|位置或关键字。本次运行共用的ResourceBudget对象，用于检查内存和临时磁盘用量。当前对象在分配前申请额度，用完后归还；同一次运行的组件应使用同一个对象。|
|`frame_ids`|tuple &#124; None|否|None|仅关键字。要保留的报文ID元组；None表示保留全部原记录。它决定哪些记录传回父进程，不等同于decode_frame_ids所控制的DBC解码范围；两项分别设置。|
|`batch_rows`|int|否|MAX_BATCH_ROWS|仅关键字。batch_rows为1至4096原帧上限|
|`consumer_headroom_bytes`|int|否|0|仅关键字。consumer_headroom_bytes为调用方处理本批时     仍需预约的工作空间，此处只留余量、不代其付款|
|`prefetch`|bool|否|False|仅关键字。prefetch为显式bool，     True允许额外一个已付批次在途|
|`decode_scope`|str|否|'all'|仅关键字。"all"沿用全部消息解码；"requested"只解码显式所需ID。两者仍按原顺序读取帧。|
|`decode_frame_ids`|tuple[int, ...] &#124; None|否|None|仅关键字。requested模式需要解码的ID集合；all模式为None，表示不按ID缩小解码范围。|
|`input_check`|str|否|'full'|仅关键字。`"auto"`按实际使用的报文和字段检查；`"full"`检查全部原始帧及时间。发送端与接收端必须使用同一次读取确认的设置。|
|`time_scope`|str|否|'source'|仅关键字。`"none"`不收集时间范围；`"selected"`只收集选中记录的时间；`"source"`收集全部来源时间。发送端与接收端必须使用同一次读取确认的设置。full检查要求time_scope为source。|
|`_worker_target`|Callable &#124; None|否|None|仅关键字。私有的子进程入口替换参数，用于故障测试；None使用模块默认worker_main。普通调用无需填写。|
|`input_paths`|tuple[str, ...] &#124; None|否|None|仅关键字。有序且同格式的连续输入文件；按给定顺序读取，文件边界不中断计算状态。|
|`decode_policy`|str|否|'legacy'|仅关键字。strict要求DBC长度一致，partial允许短载荷可解部分，legacy沿用旧格式路径；不接受未知取值。|
|`cycle_fields`|tuple[LegacyCANField, ...]|否|()|仅关键字。需要读取DBC周期的字段定位集合；初始化时读取元数据，不逐帧读取DBC。|
|`metadata_fields`|tuple[LegacyCANField, ...]|否|()|仅关键字。仅请求驱动信号的DBC候选声明，默认空tuple；用于确认实际帧身份，不请求信号值，也不增加普通样本或值解码。|

#### 返回说明

尚未启动read。

#### 异常说明

原配置/预算错误，未返回owner仍可恢复close。

本函数直接报告的具体错误：

- `TypeError`：CAN批次预取开关必须是bool。
- `ValueError`：批次需要1至4096条原帧上限。
- `ValueError`：消费批次的后续工作余量必须是非负整数。
- `ValueError`：解码后保留ID必须是无重复29位整数tuple或None。
- `ValueError`：CAN解码范围需要all或requested。
- `ValueError`：CAN输入检查需要auto/full。
- `ValueError`：CAN时间范围需要source/selected/none。
- `ValueError`：完整检查必须保留全来源时间。
- `ValueError`：自动按需检查需要固定requested解码范围。
- `ValueError`：全解码模式不能另设固定解码ID。
- `ValueError`：按需解码ID必须是无重复29位整数tuple。
- `ValueError`：所需字段的报文ID必须属于固定解码集合。

源码：[`src/chronaxis/legacy/batch_read.py:36`](../../../src/chronaxis/legacy/batch_read.py#L36)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-LegacyCANBatchRead-_check_ready"></a>
### `LegacyCANBatchRead._check_ready`

默认沿用原v1验证；requested核v3，auto核v4及检查/时间范围。

```python
LegacyCANBatchRead._check_ready(packet)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`packet`|dict[str, object]|是|无|位置或关键字。已经解码并检查字段的进程通信包，含op操作名及该操作的数据；本函数按当前协议步骤继续检查或发送它。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

SourceReadError。
ID先逐项核原生int再比较tuple，拒绝bool/int混同、缺项、额外字段或顺序改变；
显式测试worker也必须确认同策略，不能用旧v1/v2应答冒充字段已裁剪。

源码：[`src/chronaxis/legacy/batch_read.py:149`](../../../src/chronaxis/legacy/batch_read.py#L149)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-LegacyCANBatchRead-_check_ready_metadata"></a>
### `LegacyCANBatchRead._check_ready_metadata`

周期只为显式请求字段核验；默认维持原元数据契约。

```python
LegacyCANBatchRead._check_ready_metadata(packet)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`packet`|dict|是|无|位置或关键字。子进程ready元数据包；必须匹配本次请求的字段和周期元数据后才能继续读取。|

#### 返回说明

None。

#### 异常说明

原字段、周期或依赖校验错误。

源码：[`src/chronaxis/legacy/batch_read.py:208`](../../../src/chronaxis/legacy/batch_read.py#L208)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-LegacyCANBatchRead-counters"></a>
### `LegacyCANBatchRead.counters`

区分批次许可上界、收到的原帧与保留记录，不把未消费批次伪称已完成。

```python
LegacyCANBatchRead.counters
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

独立dict；frames_authorized包含许可但可能没读到的余量。

#### 异常说明

原小字典分配错误。

#### 边界说明

items计全部原帧；accepted为接收校验完成，
returned为已交付，records_returned计已交付的保留记录，预取失败不会虚增交付数。

源码：[`src/chronaxis/legacy/batch_read.py:216`](../../../src/chronaxis/legacy/batch_read.py#L216)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-LegacyCANBatchRead-full_check_count"></a>
### `LegacyCANBatchRead.full_check_count`

读取已验收批次中非原生输入执行完整检查的实际回退数。

```python
LegacyCANBatchRead.full_check_count
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

非负int；不计尚在预取中的包，关闭后仍保留统计。

#### 异常说明

无。此属性不把完整检查默认模式中的原帧数误作按需回退数量。

源码：[`src/chronaxis/legacy/batch_read.py:228`](../../../src/chronaxis/legacy/batch_read.py#L228)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-LegacyCANBatchRead-_receive_reply"></a>
### `LegacyCANBatchRead._receive_reply`

在已预付的上限内接收批数据或原严格控制JSON，拒绝错误版本和超长包。

```python
LegacyCANBatchRead._receive_reply()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

批次回应dict或原READY/ERROR/STATUS。

#### 异常说明

原管道/格式/取消错误。
内部观察者仅在整包严格解码成功后调用一次；只借用本槽中的payload与batch，
不改变所有权。回调失败沿next的同一read清理，不交付或再次处理该批。

源码：[`src/chronaxis/legacy/batch_read.py:236`](../../../src/chronaxis/legacy/batch_read.py#L236)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-LegacyCANBatchRead-__next__"></a>
### `LegacyCANBatchRead.__next__`

授予一批有界许可并交付原序数据；确认真实EOF及退出后才结束迭代。

```python
LegacyCANBatchRead.__next__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

LegacyDecodedBatch，借至下次next或close。

#### 异常说明

真StopIteration、原预算/来源/取消错误；持续清理失败保同一owner。

本函数直接报告的具体错误：

- `SourceReadError`：旧CAN批次发EOF但没有正常退出。
- `SourceReadError`：批次许可未得到对应批次回应。
- `SourceReadError`：预取许可与实际已消费位置不符。
- `BudgetExceededError`：CAN批次预算不足以保留一条最大记录及两端工作空间。

源码：[`src/chronaxis/legacy/batch_read.py:278`](../../../src/chronaxis/legacy/batch_read.py#L278)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-LegacyCANBatchRead-_new_packet"></a>
### `LegacyCANBatchRead._new_packet`

为下一原序号建立有限批次许可，不触碰管道。

```python
LegacyCANBatchRead._new_packet(byte_limit)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`byte_limit`|int|是|无|位置或关键字。本次已经许可的最大协议字节数；不能扩充超过预算的包。|

#### 返回说明

小dict。

#### 异常说明

原分配错误。

源码：[`src/chronaxis/legacy/batch_read.py:341`](../../../src/chronaxis/legacy/batch_read.py#L341)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-LegacyCANBatchRead-_set_prefetch_headroom"></a>
### `LegacyCANBatchRead._set_prefetch_headroom`

更新仅供下一次额外预取的动态消费余量，不收费且不改变同步许可。

```python
LegacyCANBatchRead._set_prefetch_headroom(extra_bytes)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`extra_bytes`|int|是|无|位置或关键字。extra_bytes为调用方证明所需的非负原生int，在每次next前更新。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError为非法余量；关闭后拒绝更新。

本函数直接报告的具体错误：

- `TypeError`：预取额外消费余量必须是原生int。
- `ValueError`：预取额外消费余量不能为负数。

#### 边界说明

本线程直接设置有限整数，没有后台预算回调；不足时只停预取。

源码：[`src/chronaxis/legacy/batch_read.py:350`](../../../src/chronaxis/legacy/batch_read.py#L350)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-LegacyCANBatchRead-_available_limit"></a>
### `LegacyCANBatchRead._available_limit`

在当前共享余额中留下消费者余量，计算完整可付款的批次上限。

```python
LegacyCANBatchRead._available_limit(*, additional_headroom=0)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`additional_headroom`|int|否|0|仅关键字。additional_headroom为预取专用额外余量，原同步读取固定为0。|

#### 返回说明

不超过MAX_BATCH_BYTES的整数，可能不足一条。

#### 异常说明

原账本读取错误；这里只看余额，不取得额外空间。

源码：[`src/chronaxis/legacy/batch_read.py:364`](../../../src/chronaxis/legacy/batch_read.py#L364)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-LegacyCANBatchRead-_try_prefetch"></a>
### `LegacyCANBatchRead._try_prefetch`

余量足够时全额预付并发送下一批；否则留到下一次同步读取。

```python
LegacyCANBatchRead._try_prefetch()
```

参数：无显式参数。


#### 参数说明

无，当前批已完成全部接包校验。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原预约/发送/取消错误；失败不重发，也不交付当前批，由next统一清理。

本函数直接报告的具体错误：

- `SourceReadError`：预取已有一个在途请求或费用责任。

#### 边界说明

EOF不再发许可；至多一个在途批，消费余量不用于预付。

源码：[`src/chronaxis/legacy/batch_read.py:375`](../../../src/chronaxis/legacy/batch_read.py#L375)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-LegacyCANBatchRead-_release_closed_state"></a>
### `LegacyCANBatchRead._release_closed_state`

共享close确认实际资源全关后清预取责任，再按原槽逐笔归还。

```python
LegacyCANBatchRead._release_closed_state()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原退费错误；同一close可从实际剩余槽恢复。

源码：[`src/chronaxis/legacy/batch_read.py:396`](../../../src/chronaxis/legacy/batch_read.py#L396)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
