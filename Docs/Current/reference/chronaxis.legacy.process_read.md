# chronaxis.legacy.process_read

在独立进程中逐次请求旧CAN函数，确认退出后才交付完整EOF。

输入是冻结的单BLF请求和借用ResourceBudget，输出原函数已经返回的
LegacyDecodedFrame。构造不启动进程；start只初始化旧DBC和公开元数据；
每次next只授权一个PULL，不预取下一帧，也不改变原读取或解码参数。
原reader没有公开的可靠关闭接口，因此本层关闭自己的管道并等待或终止
自己启动的进程。只有确认退出才释放进程责任；这没有修复旧reader。

固定状态、IPC最大包、元数据和当前记录分别计入新层保守RAM费用。
旧DBC、旧reader和解释器的整进程RSS未测，不能由本账本上限代替。
本层不写源文件、不导出BLF、不关闭共用的资源用量记录或其他read。失败时保留原父
异常；清理仍失败时以can_process_read_cleanup_owner暴露同一真实owner。
跨进程只能保留远端异常事实，不能承诺远端异常对象与父对象相同。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisError](chronaxis.results.errors.md#api-AnalysisError)、[LegacyCANRequest](chronaxis.legacy.records.md#api-LegacyCANRequest)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[SourceReadError](chronaxis.sources.protocol.md#api-SourceReadError)

## 对象导航

|对象|用途|
|---|---|
|[`_wire_metadata_bytes`](#api-_wire_metadata_bytes)|估算已通过有界wire检查的JSON树，复制冻结前先预约保留费用。|
|[`_freeze`](#api-_freeze)|复制一份已经通过JSON边界检查的元数据，拒绝后续原地修改。|
|[`RemoteLegacyError`](#api-RemoteLegacyError)|保存远端错误的有限事实，明确区别于父进程中的原异常对象。|
|[`RemoteLegacyError.__init__`](#api-RemoteLegacyError-__init__)|将有界错误包保存为供SourceReadError引用的cause。|
|[`LegacyCANProcessRead`](#api-LegacyCANProcessRead)|持有一次读取的真实进程、两端连接及各自费用，不与其他read共享。|
|[`LegacyCANProcessRead.__init__`](#api-LegacyCANProcessRead-__init__)|保存请求并预约固定状态，不启动进程或访问DBC。|
|[`LegacyCANProcessRead.closed`](#api-LegacyCANProcessRead-closed)|返回全部真实责任及费用是否已结束。|
|[`LegacyCANProcessRead.finished`](#api-LegacyCANProcessRead-finished)|返回本次真实协议EOF是否已完整交付。|
|[`LegacyCANProcessRead.worker_pid`](#api-LegacyCANProcessRead-worker_pid)|返回实际启动过的PID，进程对象关闭后仍可用于验证。|
|[`LegacyCANProcessRead.counters`](#api-LegacyCANProcessRead-counters)|区分许可发送尝试、已接收ITEM和实际交付记录的有限计数。|
|[`LegacyCANProcessRead.metadata`](#api-LegacyCANProcessRead-metadata)|读取已完成INIT的同次DBC公开元数据，不隐式启动。|
|[`LegacyCANProcessRead._require_open`](#api-LegacyCANProcessRead-_require_open)|阻止失败或半关闭对象再次授权读取。|
|[`LegacyCANProcessRead._fail`](#api-LegacyCANProcessRead-_fail)|以原父错误为主关闭实际owner，必要时包装来源位置。|
|[`LegacyCANProcessRead.start`](#api-LegacyCANProcessRead-start)|实际启动隔离进程并取得READY，不授权任何消息读取。|
|[`LegacyCANProcessRead._check_ready`](#api-LegacyCANProcessRead-_check_ready)|核INIT回应来自同一真实PID和同一字段请求，不猜元数据。|
|[`LegacyCANProcessRead._check_ready_metadata`](#api-LegacyCANProcessRead-_check_ready_metadata)|核两种READY共有的字段定位、单位、依赖与原vendor，不改协议头。|
|[`LegacyCANProcessRead._exchange`](#api-LegacyCANProcessRead-_exchange)|完成一个有界请求/回应；STATUS/ACK也不隐含PULL许可。|
|[`LegacyCANProcessRead._send_request`](#api-LegacyCANProcessRead-_send_request)|发送唯一在途许可；发送中断时仍保留实际连接和未确认责任。|
|[`LegacyCANProcessRead._receive_response`](#api-LegacyCANProcessRead-_receive_response)|接收先前发送的许可，并严格核对远端错误事实与请求身份。|
|[`LegacyCANProcessRead._receive_reply`](#api-LegacyCANProcessRead-_receive_reply)|读取本协议的一条严格JSON回应，供批次子类替换物理数据包边界。|
|[`LegacyCANProcessRead.__iter__`](#api-LegacyCANProcessRead-__iter__)|返回本次独立read，不因取得迭代器就启动或读取。|
|[`LegacyCANProcessRead.__next__`](#api-LegacyCANProcessRead-__next__)|只授权并返回一帧，真实完整EOF之后才StopIteration。|
|[`LegacyCANProcessRead._close_connection`](#api-LegacyCANProcessRead-_close_connection)|关闭一个真实自有连接，成功后取消也不丢失其实际关闭事实。|
|[`LegacyCANProcessRead._close_process`](#api-LegacyCANProcessRead-_close_process)|确认自己启动的进程退出后关闭其实际句柄，不动其他read。|
|[`LegacyCANProcessRead._release_closed_state`](#api-LegacyCANProcessRead-_release_closed_state)|实际连接和进程全部关闭后清状态、逐槽退费，供批次子类补充责任。|
|[`LegacyCANProcessRead.close`](#api-LegacyCANProcessRead-close)|停止授予许可，关闭自有IPC/进程，最后归还各自费用。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from collections.abc import Mapping
from sys import getsizeof
from types import MappingProxyType
from .records import MAX_WIRE_BYTES, LegacyCANRequest, decode_packet, decoded_from_dict, encode_packet, field_from_dict, field_to_dict
from .worker import VENDOR_SHA256, worker_main
from ..results.budget import ResourceBudget
from ..results.errors import AnalysisError, ResultClosedError
from ..results.spool import _cleanup_owner, _release_owned_ram, _reserve_owned_ram
from ..sources.protocol import SourceReadError
```

</details>

<a id="api-_wire_metadata_bytes"></a>
## `_wire_metadata_bytes`

估算已通过有界wire检查的JSON树，复制冻结前先预约保留费用。

```python
_wire_metadata_bytes(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|JSON值|是|无|位置或关键字。decode_packet产生的JSON树，计算这棵元数据树需要保留的内存。|

### 返回说明

基础字节估算。

### 异常说明

TypeError为内部未校验类型；不借用只接受冻结tuple的历史元数据估算器。

本函数直接报告的具体错误：

- `TypeError`：旧CAN元数据只接受已校验JSON树。

源码：[`src/chronaxis/legacy/process_read.py:33`](../../../src/chronaxis/legacy/process_read.py#L33)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_freeze"></a>
## `_freeze`

复制一份已经通过JSON边界检查的元数据，拒绝后续原地修改。

```python
_freeze(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|JSON值|是|无|位置或关键字。已通过大小和结构检查的JSON树；递归转为不可修改的映射和元组。|

### 返回说明

只读映射、tuple或原标量。

### 异常说明

原分配错误传播；本函数不读取文件或保留进程对象。

源码：[`src/chronaxis/legacy/process_read.py:50`](../../../src/chronaxis/legacy/process_read.py#L50)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RemoteLegacyError"></a>
## `RemoteLegacyError`

保存远端错误的有限事实，明确区别于父进程中的原异常对象。

```python
RemoteLegacyError(facts, phase, request_id)
```

继承关系：RuntimeError。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/legacy/process_read.py:64`](../../../src/chronaxis/legacy/process_read.py#L64)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RemoteLegacyError-__init__"></a>
### `RemoteLegacyError.__init__`

将有界错误包保存为供SourceReadError引用的cause。

```python
RemoteLegacyError.__init__(facts, phase, request_id)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`facts`|Mapping &#124; list &#124; tuple|是|无|位置或关键字。facts为错误字段映射|
|`phase`|str|是|无|位置或关键字。发生错误时正在执行的步骤名称；写入错误信息，帮助区分初始化、读取、解码或关闭失败。|
|`request_id`|int &#124; None|是|无|位置或关键字。本次协议请求的编号，供父进程关联响应；尚未取得请求编号的初始化错误使用None。|

#### 返回说明

新远端事实异常。

#### 异常说明

原分配/格式错误，不执行清理。

源码：[`src/chronaxis/legacy/process_read.py:67`](../../../src/chronaxis/legacy/process_read.py#L67)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessRead"></a>
## `LegacyCANProcessRead`

持有一次读取的真实进程、两端连接及各自费用，不与其他read共享。

_waiting表示已有一个发送尝试尚未取得完整回应，禁止叠加许可。
_process_stopped只在实际确认退出后置真；关闭失败保留真实对象。
finished仅表示真实协议EOF、正常退出和本owner关闭均成功。

```python
LegacyCANProcessRead(request, budget, *, _worker_target=None)
```


源码：[`src/chronaxis/legacy/process_read.py:82`](../../../src/chronaxis/legacy/process_read.py#L82)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessRead-__init__"></a>
### `LegacyCANProcessRead.__init__`

保存请求并预约固定状态，不启动进程或访问DBC。

```python
LegacyCANProcessRead.__init__(request, budget, *, _worker_target=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`request`|[LegacyCANRequest](chronaxis.legacy.records.md#api-LegacyCANRequest)|是|无|位置或关键字。request为LegacyCANRequest|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)|是|无|位置或关键字。本次运行共用的ResourceBudget对象，用于检查内存和临时磁盘用量。当前对象在分配前申请额度，用完后归还；同一次运行的组件应使用同一个对象。|
|`_worker_target`|Callable &#124; None|否|None|仅关键字。私有的子进程入口替换参数，用于故障测试；None使用模块默认worker_main。普通调用无需填写。|

#### 返回说明

尚未启动的独立read。

#### 异常说明

配置/预算/分配错误；清理持续失败
    在原异常上提供can_process_read_cleanup_owner，不补共享余额差。

本函数直接报告的具体错误：

- `TypeError`：旧CAN读取需要LegacyCANRequest和ResourceBudget。
- `ValueError`：当前单CAN来源最多声明256个字段，且初始化包不能超过64KiB。

源码：[`src/chronaxis/legacy/process_read.py:90`](../../../src/chronaxis/legacy/process_read.py#L90)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessRead-closed"></a>
### `LegacyCANProcessRead.closed`

返回全部真实责任及费用是否已结束。

```python
LegacyCANProcessRead.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无，不触碰已关闭Process属性。

源码：[`src/chronaxis/legacy/process_read.py:124`](../../../src/chronaxis/legacy/process_read.py#L124)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessRead-finished"></a>
### `LegacyCANProcessRead.finished`

返回本次真实协议EOF是否已完整交付。

```python
LegacyCANProcessRead.finished
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

bool；提前close或失败永远不伪装EOF。

#### 异常说明

无。

源码：[`src/chronaxis/legacy/process_read.py:132`](../../../src/chronaxis/legacy/process_read.py#L132)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessRead-worker_pid"></a>
### `LegacyCANProcessRead.worker_pid`

返回实际启动过的PID，进程对象关闭后仍可用于验证。

```python
LegacyCANProcessRead.worker_pid
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

int或None。

#### 异常说明

无，不重新启动进程。

源码：[`src/chronaxis/legacy/process_read.py:140`](../../../src/chronaxis/legacy/process_read.py#L140)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessRead-counters"></a>
### `LegacyCANProcessRead.counters`

区分许可发送尝试、已接收ITEM和实际交付记录的有限计数。

```python
LegacyCANProcessRead.counters
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

独立dict；发送中取消时issued是已授予序号的上界，
    不等于已被子进程接收或完成。

#### 异常说明

原小字典分配错误。

源码：[`src/chronaxis/legacy/process_read.py:148`](../../../src/chronaxis/legacy/process_read.py#L148)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessRead-metadata"></a>
### `LegacyCANProcessRead.metadata`

读取已完成INIT的同次DBC公开元数据，不隐式启动。

```python
LegacyCANProcessRead.metadata
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

冻结JSON映射，借用至close；长期保留须由消费者计费。

#### 异常说明

ResultClosedError为关闭中/已关闭，RuntimeError为尚未READY。

本函数直接报告的具体错误：

- `RuntimeError`：start完成前没有旧CAN运行元数据。

源码：[`src/chronaxis/legacy/process_read.py:158`](../../../src/chronaxis/legacy/process_read.py#L158)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessRead-_require_open"></a>
### `LegacyCANProcessRead._require_open`

阻止失败或半关闭对象再次授权读取。

```python
LegacyCANProcessRead._require_open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ResultClosedError为已关/正在关；
    SourceReadError为失败后继续推进；close仍可重试。

本函数直接报告的具体错误：

- `ResultClosedError`：旧CAN进程read已关闭或正在关闭。
- `SourceReadError`：失败的旧CAN进程read仅接受关闭。

源码：[`src/chronaxis/legacy/process_read.py:169`](../../../src/chronaxis/legacy/process_read.py#L169)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessRead-_fail"></a>
### `LegacyCANProcessRead._fail`

以原父错误为主关闭实际owner，必要时包装来源位置。

```python
LegacyCANProcessRead._fail(exc, stage)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`exc`|BaseException|是|无|位置或关键字。本次操作的原异常，供附加关闭失败信息并保留原因链。不要用错误字符串代替异常对象。|
|`stage`|str|是|无|位置或关键字。发生错误时正在执行的步骤名称；写入错误信息，帮助区分初始化、读取、解码或关闭失败。|

#### 返回说明

不返回。

#### 异常说明

父KI/SystemExit、预算及来源错误原对象传播；其他错误作为
    SourceReadError的cause，清理副错只附note/真实恢复owner。

源码：[`src/chronaxis/legacy/process_read.py:180`](../../../src/chronaxis/legacy/process_read.py#L180)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessRead-start"></a>
### `LegacyCANProcessRead.start`

实际启动隔离进程并取得READY，不授权任何消息读取。

```python
LegacyCANProcessRead.start()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

self，重复成功调用不重启/重载DBC。

#### 异常说明

启动、协议、远端或预算错误；父取消保原对象和关闭责任。

源码：[`src/chronaxis/legacy/process_read.py:199`](../../../src/chronaxis/legacy/process_read.py#L199)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessRead-_check_ready"></a>
### `LegacyCANProcessRead._check_ready`

核INIT回应来自同一真实PID和同一字段请求，不猜元数据。

```python
LegacyCANProcessRead._check_ready(packet)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`packet`|dict|是|无|位置或关键字。packet为有界READY dict。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

SourceReadError为profile/版本/PID/字段位置不符。

本函数直接报告的具体错误：

- `SourceReadError`：旧CAN READY身份、版本或实际PID不符。

源码：[`src/chronaxis/legacy/process_read.py:237`](../../../src/chronaxis/legacy/process_read.py#L237)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessRead-_check_ready_metadata"></a>
### `LegacyCANProcessRead._check_ready_metadata`

核两种READY共有的字段定位、单位、依赖与原vendor，不改协议头。

```python
LegacyCANProcessRead._check_ready_metadata(packet, *, cycle_fields=(), metadata_fields=())
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`packet`|dict[str, object]|是|无|位置或关键字。已经解码并检查字段的进程通信包，含op操作名及该操作的数据；本函数按当前协议步骤继续检查或发送它。|
|`cycle_fields`|tuple[LegacyCANField, ...]|否|()|仅关键字。需要读取DBC周期的字段定位集合；初始化时读取元数据，不逐帧读取DBC。|
|`metadata_fields`|tuple[LegacyCANField, ...]|否|()|仅关键字。仅请求驱动信号的DBC候选声明，默认空tuple；用于确认实际帧身份，不请求信号值，也不增加普通样本或值解码。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原SourceReadError；检查顺序和错误文本沿用逐条入口。
默认v1和显式按需v2分别检查各自头部，不能伪造v1包绕过策略核对。

本函数直接报告的具体错误：

- `SourceReadError`：旧CAN READY字段数量不符。
- `SourceReadError`：旧CAN READY依赖版本不符合已验证profile。
- `SourceReadError`：旧CAN READY原样vendor哈希不符。
- `SourceReadError`：旧CAN READY没有对应原请求的字段定位。
- `SourceReadError`：旧CAN READY字段定位类型非法。
- `SourceReadError`：旧CAN READY帧型兼容提示非法或与原定位不同。

源码：[`src/chronaxis/legacy/process_read.py:252`](../../../src/chronaxis/legacy/process_read.py#L252)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessRead-_exchange"></a>
### `LegacyCANProcessRead._exchange`

完成一个有界请求/回应；STATUS/ACK也不隐含PULL许可。

```python
LegacyCANProcessRead._exchange(packet)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`packet`|dict[str, object]|是|无|位置或关键字。已经解码并检查字段的进程通信包，含op操作名及该操作的数据；本函数按当前协议步骤继续检查或发送它。|

#### 返回说明

有界回应dict。

#### 异常说明

原父取消/管道错误、SourceReadError或明确远端cause。

#### 边界说明

最多一项在途，父每50ms回到Python检查取消；本方法发送后立即等待。

源码：[`src/chronaxis/legacy/process_read.py:310`](../../../src/chronaxis/legacy/process_read.py#L310)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessRead-_send_request"></a>
### `LegacyCANProcessRead._send_request`

发送唯一在途许可；发送中断时仍保留实际连接和未确认责任。

```python
LegacyCANProcessRead._send_request(packet)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`packet`|dict|是|无|位置或关键字。packet为调用方已经为相应工作空间付款的协议dict。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原编码/发送/取消错误；失败不可按未发送重试。

本函数直接报告的具体错误：

- `SourceReadError`：旧CAN连接不可用或已有一个在途请求。

#### 边界说明

原逐条入口立即接收；批次入口可在消费当前批时保留这一项在途请求。

源码：[`src/chronaxis/legacy/process_read.py:323`](../../../src/chronaxis/legacy/process_read.py#L323)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessRead-_receive_response"></a>
### `LegacyCANProcessRead._receive_response`

接收先前发送的许可，并严格核对远端错误事实与请求身份。

```python
LegacyCANProcessRead._receive_response(packet)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`packet`|dict[str, object]|是|无|位置或关键字。已经解码并检查字段的进程通信包，含op操作名及该操作的数据；本函数按当前协议步骤继续检查或发送它。|

#### 返回说明

有界回应dict。

#### 异常说明

原连接/格式/取消错误，或带RemoteLegacyError cause的来源错误。

本函数直接报告的具体错误：

- `SourceReadError`：旧CAN连接没有对应的在途请求。
- `SourceReadError`：旧CAN远端错误包缺少明确事实。
- `SourceReadError`：旧CAN远端错误不属于当前请求。

#### 边界说明

必须已有一个在途请求；没有真实协议EOF的退出仍是错误。

源码：[`src/chronaxis/legacy/process_read.py:340`](../../../src/chronaxis/legacy/process_read.py#L340)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessRead-_receive_reply"></a>
### `LegacyCANProcessRead._receive_reply`

读取本协议的一条严格JSON回应，供批次子类替换物理数据包边界。

```python
LegacyCANProcessRead._receive_reply()
```

参数：无显式参数。


#### 参数说明

无，使用本owner的实际Connection。

#### 返回说明

已校验的回应dict。

#### 异常说明

原管道、长度、JSON或取消错误。

#### 边界说明

原逐条入口仍只接收64KiB；子类不能绕过共享接收流程的在途及远端错误检查。

源码：[`src/chronaxis/legacy/process_read.py:377`](../../../src/chronaxis/legacy/process_read.py#L377)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessRead-__iter__"></a>
### `LegacyCANProcessRead.__iter__`

返回本次独立read，不因取得迭代器就启动或读取。

```python
LegacyCANProcessRead.__iter__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回当前对象本身。后续迭代或with语句使用的仍是同一个对象。

#### 异常说明

原错误只在实际next/start时报告。

源码：[`src/chronaxis/legacy/process_read.py:387`](../../../src/chronaxis/legacy/process_read.py#L387)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessRead-__next__"></a>
### `LegacyCANProcessRead.__next__`

只授权并返回一帧，真实完整EOF之后才StopIteration。

```python
LegacyCANProcessRead.__next__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

LegacyDecodedFrame；调用者保留引用须另计费。

#### 异常说明

StopIteration为已确认EOF；源/预算/协议错误或父原取消。

本函数直接报告的具体错误：

- `SourceReadError`：旧CAN回应不是本次唯一许可序号。
- `SourceReadError`：旧CAN EOF原帧计数不符。
- `SourceReadError`：旧CAN虽然发EOF，但没有正常退出。
- `SourceReadError`：旧CAN PULL必须得到ITEM或真实EOF。
- `SourceReadError`：旧CAN ITEM字段缺失或多余。
- `SourceReadError`：旧CAN原yield序号不连续，禁止重排或补号。

源码：[`src/chronaxis/legacy/process_read.py:394`](../../../src/chronaxis/legacy/process_read.py#L394)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessRead-_close_connection"></a>
### `LegacyCANProcessRead._close_connection`

关闭一个真实自有连接，成功后取消也不丢失其实际关闭事实。

```python
LegacyCANProcessRead._close_connection(slot)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`slot`|str|是|无|位置或关键字。保存本对象通信端点的属性名；关闭后清空该属性，防止重复关闭旧端点。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原close错误；未关闭对象仍在同槽，费用稍后单独归还。

源码：[`src/chronaxis/legacy/process_read.py:443`](../../../src/chronaxis/legacy/process_read.py#L443)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessRead-_close_process"></a>
### `LegacyCANProcessRead._close_process`

确认自己启动的进程退出后关闭其实际句柄，不动其他read。

```python
LegacyCANProcessRead._close_process()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None，实际exitcode保留供EOF判断。

#### 异常说明

join/terminate/kill/close错误保原process和停止确认状态以便重试。

#### 边界说明

三次显式join最多约6秒；Windows kill仍是TerminateProcess，
    必须实际取得exitcode，不能把终止请求成功当作进程已经退出。

源码：[`src/chronaxis/legacy/process_read.py:458`](../../../src/chronaxis/legacy/process_read.py#L458)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessRead-_release_closed_state"></a>
### `LegacyCANProcessRead._release_closed_state`

实际连接和进程全部关闭后清状态、逐槽退费，供批次子类补充责任。

```python
LegacyCANProcessRead._release_closed_state()
```

参数：无显式参数。


#### 参数说明

无；调用方必须已完成本owner实际资源关闭。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原预算回调错误；费用槽保留实际入账事实，同一close可继续恢复。

源码：[`src/chronaxis/legacy/process_read.py:492`](../../../src/chronaxis/legacy/process_read.py#L492)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessRead-close"></a>
### `LegacyCANProcessRead.close`

停止授予许可，关闭自有IPC/进程，最后归还各自费用。

```python
LegacyCANProcessRead.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None，完成后重复调用幂等。

#### 异常说明

实际关闭或预算回调错误；对象仍可同owner重试。

#### 边界说明

关管道令等待命令的child退出；在途旧IO不响应时有限等待后终止，
    不为关闭继续next，也不把强制退出当正常分析完成。

源码：[`src/chronaxis/legacy/process_read.py:504`](../../../src/chronaxis/legacy/process_read.py#L504)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
