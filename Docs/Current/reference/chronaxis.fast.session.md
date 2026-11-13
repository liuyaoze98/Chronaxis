# `chronaxis.fast.session`

一个fast会话的多文件调度和最终累计。

worker只求当前帧贡献；主进程控制统一预算、交付顺序及成功发布前的完整性。
concatenate可暂停可选预读；time_order必要暂存完成后稳定归并。临时目录和
进程均属于本次调用，异常不返回部分结果。内联与batch不经传输协议。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[BudgetExceededError](chronaxis.results.errors.md#api-BudgetExceededError)、[ControlChannel](chronaxis._control_wire.md#api-ControlChannel)、[FileContributions](chronaxis.fast.stream.md#api-FileContributions)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)、[_Accumulator](chronaxis.fast.compute.md#api-_Accumulator)

## 对象导航

|对象|用途|
|---|---|
|[`effective_spec`](#api-effective_spec)|取得不修改原声明的执行视图。|
|[`_worker_process_limit`](#api-_worker_process_limit)|从已验证的进程上限和文件数取得文件工作进程数，不包含主进程。|
|[`file_specs`](#api-file_specs)|展开有限文件声明。|
|[`_checked_file_specs`](#api-_checked_file_specs)|取得实际文件声明，并复用本会话已经检查过的同一组公式。|
|[`SessionAccumulator`](#api-SessionAccumulator)|只有主会话持有的标量累计器。计数、目标缺失和帧身份按计算项分别核验。|
|[`SessionAccumulator.__init__`](#api-SessionAccumulator-__init__)|准备纯累计状态。|
|[`SessionAccumulator.consume`](#api-SessionAccumulator-consume)|按输入顺序逐项相加。|
|[`SessionAccumulator.finish_file`](#api-SessionAccumulator-finish_file)|合并已关闭文件的事实。|
|[`SessionAccumulator.result`](#api-SessionAccumulator-result)|核完整消费后生成业务行。|
|[`FilePool`](#api-FilePool)|管理有限工作槽及每文件连续块前缀；不在内存保存所有暂存块描述。|
|[`FilePool.__init__`](#api-FilePool-__init__)|初始化但不启动。|
|[`FilePool.check_cancel`](#api-FilePool-check_cancel)|传递外部取消。|
|[`FilePool.start`](#api-FilePool-start)|预付真实工作槽后启动；任何部分构造失败仍由本池关闭已登记资源。|
|[`FilePool.assign`](#api-FilePool-assign)|按文件声明顺序派发下一文件。|
|[`FilePool.grant`](#api-FilePool-grant)|授权一个完整块的唯一交付路径。|
|[`FilePool.pump`](#api-FilePool-pump)|推进有限控制和数据消息，优先响应所有worker错误。|
|[`FilePool.message`](#api-FilePool-message)|核验工作槽状态及块序号。|
|[`FilePool.packet_records`](#api-FilePool-packet_records)|验证块间顺序并展开一块。|
|[`FilePool.read_spool`](#api-FilePool-read_spool)|读取并删除一个已提交块。|
|[`FilePool.concatenate`](#api-FilePool-concatenate)|消费当前文件，后续文件同时预读。|
|[`FilePool.file_records`](#api-FilePool-file_records)|逐块读取一个已完整暂存文件。|
|[`FilePool.time_order`](#api-FilePool-time_order)|完成必要暂存后k路稳定归并。|
|[`FilePool.close`](#api-FilePool-close)|先结束实际写入者，再关闭句柄和自有费用；失败槽保留到后续重试。|
|[`_SessionResources`](#api-_SessionResources)|仅管理一个fast会话的固定费用、读取器、工作池和自有目录。|
|[`_SessionResources.__init__`](#api-_SessionResources-__init__)|建立空责任槽。|
|[`_SessionResources.open_reader`](#api-_SessionResources-open_reader)|创建并登记本会话读取器，收编构造中未能关闭的真实子所有者。|
|[`_SessionResources.close_reader`](#api-_SessionResources-close_reader)|关闭实际读取器；仅在真实关闭完成后清槽。|
|[`_SessionResources.create_directory`](#api-_SessionResources-create_directory)|独占创建并登记目录，避免自动终结器在写入者未结束时删除目录。|
|[`_SessionResources.close`](#api-_SessionResources-close)|依次停止工作池、读取器、删除自有目录并退款，任一步失败保留重试责任。|
|[`run_session`](#api-run_session)|运行一个连续fast任务。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from hashlib import sha256
from multiprocessing.connection import wait
from pathlib import Path
from tempfile import mkdtemp
from time import perf_counter
from ..results.budget import ResourceBudget, _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..results.errors import BudgetExceededError
from ..dbc_loading import load_dbc_file
from .._control_wire import ControlChannel
from .blocks import RAM, LIMIT, encode, decode, batches
from .compute import _Accumulator, _check_program_spec
from .stream import FileContributions
```

</details>

<a id="api-effective_spec"></a>
## `effective_spec`

取得不修改原声明的执行视图。

```python
effective_spec(spec, process_count=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|dict|是|无|位置或关键字。本次已编译会话或单文件声明，包含来源、公式、顺序和执行资源；调用过程不改写它。|
|`process_count`|int &#124; None|否|None|位置或关键字。本次读取、解码、求值工作进程上限覆盖；None沿用声明，正整数且不接受布尔值。|

### 返回说明

新dict。

### 异常说明

非正原生整数；不接受bool、字符串或浮点数。

源码：[`src/chronaxis/fast/session.py:26`](../../../src/chronaxis/fast/session.py#L26)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_worker_process_limit"></a>
## `_worker_process_limit`

从已验证的进程上限和文件数取得文件工作进程数，不包含主进程。

参数为正整数。返回至多文件数的工作进程上限；只能并发处理一份时返回0，
表示在当前进程执行。时间归并的内联暂存不改变这个判定；无输入或输出操作。

```python
_worker_process_limit(process_count: int, file_count: int) -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`process_count`|int|是|无|位置或关键字。已通过校验的正整数工作进程上限，不包含主进程。|
|`file_count`|int|是|无|位置或关键字。已经展开的输入文件数；仅能同时处理一份时在当前进程执行，返回0。|

返回类型：int。

源码：[`src/chronaxis/fast/session.py:36`](../../../src/chronaxis/fast/session.py#L36)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-file_specs"></a>
## `file_specs`

展开有限文件声明。

```python
file_specs(spec)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|dict|是|无|位置或关键字。本次已编译会话或单文件声明，包含来源、公式、顺序和执行资源；调用过程不改写它。|

### 返回说明

每文件字典列表。

### 异常说明

无输入IO。

源码：[`src/chronaxis/fast/session.py:46`](../../../src/chronaxis/fast/session.py#L46)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_checked_file_specs"></a>
## `_checked_file_specs`

取得实际文件声明，并复用本会话已经检查过的同一组公式。

```python
_checked_file_specs(spec, programs_checked)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|dict[str, object]|是|无|位置或关键字。本次独立会话的可修改声明视图；准备其 metrics 后展开每文件声明。|
|`programs_checked`|bool|是|无|位置或关键字。公共编译器是否已经检查顶层公式；文件覆盖的不同公式仍须单独核对。|

### 返回说明

文件声明列表；低层inputs覆盖的公式仍检查原文本和指令。

### 异常说明

非法公式或声明错误；不因顶层已编译就放行另一组覆盖值。

源码：[`src/chronaxis/fast/session.py:54`](../../../src/chronaxis/fast/session.py#L54)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SessionAccumulator"></a>
## `SessionAccumulator`

只有主会话持有的标量累计器。计数、目标缺失和帧身份按计算项分别核验。

```python
SessionAccumulator(spec)
```


源码：[`src/chronaxis/fast/session.py:77`](../../../src/chronaxis/fast/session.py#L77)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SessionAccumulator-__init__"></a>
### `SessionAccumulator.__init__`

准备纯累计状态。

```python
SessionAccumulator.__init__(spec)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|dict|是|无|位置或关键字。本次已编译会话或单文件声明，包含来源、公式、顺序和执行资源；调用过程不改写它。|

#### 返回说明

新对象。

#### 异常说明

名称或单位字段缺失。

源码：[`src/chronaxis/fast/session.py:80`](../../../src/chronaxis/fast/session.py#L80)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SessionAccumulator-consume"></a>
### `SessionAccumulator.consume`

按输入顺序逐项相加。

```python
SessionAccumulator.consume(record)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`record`|tuple|是|无|位置或关键字。一条已求值贡献：(整数纳秒时间, 原始记录序号, (计算项序号, float64贡献, 入选bool)元组)。|

#### 返回说明

None。

#### 异常说明

累计溢出。

源码：[`src/chronaxis/fast/session.py:92`](../../../src/chronaxis/fast/session.py#L92)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SessionAccumulator-finish_file"></a>
### `SessionAccumulator.finish_file`

合并已关闭文件的事实。

```python
SessionAccumulator.finish_file(facts)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`facts`|dict|是|无|位置或关键字。已成功关闭文件的最终记录、目标、有效、入选、帧型和兼容信息；必须与实际消费相符。|

#### 返回说明

None。

#### 异常说明

计数或身份非法。

源码：[`src/chronaxis/fast/session.py:100`](../../../src/chronaxis/fast/session.py#L100)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SessionAccumulator-result"></a>
### `SessionAccumulator.result`

核完整消费后生成业务行。

```python
SessionAccumulator.result()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

(行list, 提示list)。

#### 异常说明

贡献计数不符。

源码：[`src/chronaxis/fast/session.py:120`](../../../src/chronaxis/fast/session.py#L120)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-FilePool"></a>
## `FilePool`

管理有限工作槽及每文件连续块前缀；不在内存保存所有暂存块描述。

```python
FilePool(specs, budget, directory, cancel, statistics, *, _programs_checked=False)
```


源码：[`src/chronaxis/fast/session.py:135`](../../../src/chronaxis/fast/session.py#L135)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-FilePool-__init__"></a>
### `FilePool.__init__`

初始化但不启动。

```python
FilePool.__init__(specs, budget, directory, cancel, statistics, *, _programs_checked=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`specs`|list[dict]|是|无|位置或关键字。按声明顺序展开的单文件任务；所有成员共用一套会话计算定义。|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)|是|无|位置或关键字。本次会话共享的受管理资源用量记录；先预约空间，再构造缓冲或暂存。|
|`directory`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。本次会话私有暂存目录；所有贡献块均写到该目录，清理不涉及输入或旧结果。|
|`cancel`|Event &#124; None|是|无|位置或关键字。调用方取消事件；is_set为真时停止继续读取或调度，None表示没有外部取消信号。|
|`statistics`|dict|是|无|位置或关键字。接收本次执行统计的字典；记录实际工作进程、暂存量和关闭后的预算，None使用内部字典。|
|`_programs_checked`|bool|否|False|仅关键字。仅由内部调用传入的公式已检查标志；默认 False，普通入口仍核对原始公式和指令，不读取配置中的同名值。|

#### 返回说明

新调度器。

#### 异常说明

无；start安装进程资源的关闭责任。
_programs_checked只来自父会话的实际准备结果，不读取配置中的标志。

源码：[`src/chronaxis/fast/session.py:138`](../../../src/chronaxis/fast/session.py#L138)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-FilePool-check_cancel"></a>
### `FilePool.check_cancel`

传递外部取消。

```python
FilePool.check_cancel()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

InterruptedError。

源码：[`src/chronaxis/fast/session.py:161`](../../../src/chronaxis/fast/session.py#L161)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-FilePool-start"></a>
### `FilePool.start`

预付真实工作槽后启动；任何部分构造失败仍由本池关闭已登记资源。

```python
FilePool.start(count)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`count`|int|是|无|位置或关键字。这次实际启动的工作槽数量，已经按用户上限与输入文件数限制，不根据CPU自动增加。|

#### 返回说明

None。

#### 异常说明

原预算/启动/归属错误；
持续清理失败在原异常的fast_pool_cleanup_owner保留内部恢复入口。

源码：[`src/chronaxis/fast/session.py:169`](../../../src/chronaxis/fast/session.py#L169)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-FilePool-assign"></a>
### `FilePool.assign`

按文件声明顺序派发下一文件。

```python
FilePool.assign(slot)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`slot`|dict|是|无|位置或关键字。一个实际工作进程的控制/数据连接及交付状态；由父调度器持有并管理关闭。|

#### 返回说明

None。

#### 异常说明

断管。

源码：[`src/chronaxis/fast/session.py:225`](../../../src/chronaxis/fast/session.py#L225)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-FilePool-grant"></a>
### `FilePool.grant`

授权一个完整块的唯一交付路径。

```python
FilePool.grant(slot)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`slot`|dict|是|无|位置或关键字。一个实际工作进程的控制/数据连接及交付状态；由父调度器持有并管理关闭。|

#### 返回说明

None。

#### 异常说明

必要暂存超额。

源码：[`src/chronaxis/fast/session.py:235`](../../../src/chronaxis/fast/session.py#L235)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-FilePool-pump"></a>
### `FilePool.pump`

推进有限控制和数据消息，优先响应所有worker错误。

```python
FilePool.pump(blocking=True)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`blocking`|bool|否|True|位置或关键字。True允许本次等待消息最多50毫秒，False只处理已经到达的消息；均检查取消和错误。|

#### 返回说明

None。

#### 异常说明

协议、worker退出、取消或IO错误。

源码：[`src/chronaxis/fast/session.py:256`](../../../src/chronaxis/fast/session.py#L256)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-FilePool-message"></a>
### `FilePool.message`

核验工作槽状态及块序号。

```python
FilePool.message(slot, message)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`slot`|dict|是|无|位置或关键字。一个实际工作进程的控制/数据连接及交付状态；由父调度器持有并管理关闭。|
|`message`|tuple|是|无|位置或关键字。worker发送的有限控制消息，包含类型、所属文件及块序号；按当前交付状态核验。|

#### 返回说明

None。

#### 异常说明

错误或协议不符。

源码：[`src/chronaxis/fast/session.py:299`](../../../src/chronaxis/fast/session.py#L299)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-FilePool-packet_records"></a>
### `FilePool.packet_records`

验证块间顺序并展开一块。

```python
FilePool.packet_records(index, number, packet)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`index`|int|是|无|位置或关键字。当前处理文件在本次输入列表中的从0开始位置，不能借完成先后改变它。|
|`number`|int|是|无|位置或关键字。本文件从0递增的贡献块序号；消费者要求连续且只消费一次。|
|`packet`|bytes|是|无|位置或关键字。当前完整贡献块的二进制内容；与预期文件、块号和计算项数量一起核验。|

#### 返回说明

贡献生成器。

#### 异常说明

顺序或协议错误。

源码：[`src/chronaxis/fast/session.py:338`](../../../src/chronaxis/fast/session.py#L338)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-FilePool-read_spool"></a>
### `FilePool.read_spool`

读取并删除一个已提交块。

```python
FilePool.read_spool(index, number)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`index`|int|是|无|位置或关键字。当前处理文件在本次输入列表中的从0开始位置，不能借完成先后改变它。|
|`number`|int|是|无|位置或关键字。本文件从0递增的贡献块序号；消费者要求连续且只消费一次。|

#### 返回说明

bytes。

#### 异常说明

缺失、超长、IO。
删除仅减少当前占用，不返还累计预约额度。

源码：[`src/chronaxis/fast/session.py:355`](../../../src/chronaxis/fast/session.py#L355)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-FilePool-concatenate"></a>
### `FilePool.concatenate`

消费当前文件，后续文件同时预读。

```python
FilePool.concatenate(accumulator)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`accumulator`|[SessionAccumulator](chronaxis.fast.session.md#api-SessionAccumulator)|是|无|位置或关键字。本次会话唯一的最终累计器；消费者按确定顺序逐条调用它，不能先按文件求和。|

#### 返回说明

None。

#### 异常说明

运行或累计错误。

源码：[`src/chronaxis/fast/session.py:370`](../../../src/chronaxis/fast/session.py#L370)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-FilePool-file_records"></a>
### `FilePool.file_records`

逐块读取一个已完整暂存文件。

```python
FilePool.file_records(index)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`index`|int|是|无|位置或关键字。当前处理文件在本次输入列表中的从0开始位置，不能借完成先后改变它。|

#### 返回说明

贡献生成器。

#### 异常说明

缺块/完整性错。

源码：[`src/chronaxis/fast/session.py:400`](../../../src/chronaxis/fast/session.py#L400)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-FilePool-time_order"></a>
### `FilePool.time_order`

完成必要暂存后k路稳定归并。

```python
FilePool.time_order(accumulator)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`accumulator`|[SessionAccumulator](chronaxis.fast.session.md#api-SessionAccumulator)|是|无|位置或关键字。本次会话唯一的最终累计器；消费者按确定顺序逐条调用它，不能先按文件求和。|

#### 返回说明

None。

#### 异常说明

输入/资源/计算错误。

源码：[`src/chronaxis/fast/session.py:410`](../../../src/chronaxis/fast/session.py#L410)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-FilePool-close"></a>
### `FilePool.close`

先结束实际写入者，再关闭句柄和自有费用；失败槽保留到后续重试。

```python
FilePool.close(success=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`success`|bool|否|False|位置或关键字。True要求worker按协议正常退出；False进入失败清理并停止仍在工作的进程。|

#### 返回说明

None。

#### 异常说明

原取消或汇总关闭错误；
不删除任何暂存目录，未关闭资源仍由本池持有。

源码：[`src/chronaxis/fast/session.py:435`](../../../src/chronaxis/fast/session.py#L435)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_SessionResources"></a>
## `_SessionResources`

仅管理一个fast会话的固定费用、读取器、工作池和自有目录。

```python
_SessionResources(budget)
```


源码：[`src/chronaxis/fast/session.py:523`](../../../src/chronaxis/fast/session.py#L523)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_SessionResources-__init__"></a>
### `_SessionResources.__init__`

建立空责任槽。

```python
_SessionResources.__init__(budget)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|[chronaxis.results.budget.ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)|是|无|位置或关键字。当前 fast 会话的共享预算，固定费用由该资源对象记录和释放。|

#### 返回说明

新对象。

#### 异常说明

无资源创建。

源码：[`src/chronaxis/fast/session.py:526`](../../../src/chronaxis/fast/session.py#L526)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_SessionResources-open_reader"></a>
### `_SessionResources.open_reader`

创建并登记本会话读取器，收编构造中未能关闭的真实子所有者。

```python
_SessionResources.open_reader(spec, database, cancel)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|dict[str, object]|是|无|位置或关键字。已经完成公式准备的单文件内部声明，供本会话创建 FileContributions。|
|`database`|cantools.database.can.Database|是|无|位置或关键字。当前任务已加载的 DBC 数据库，供本文件解码使用。|
|`cancel`|object &#124; None|是|无|位置或关键字。提供 is_set() 的取消对象，或 None；读取器沿用其信号，不在这里创建另一套取消状态。|

#### 返回说明

FileContributions。

#### 异常说明

原构造错误。
ASC/BLF构造失败均收编实际未关闭的来源owner，直到成功关闭才清槽。

源码：[`src/chronaxis/fast/session.py:532`](../../../src/chronaxis/fast/session.py#L532)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_SessionResources-close_reader"></a>
### `_SessionResources.close_reader`

关闭实际读取器；仅在真实关闭完成后清槽。

```python
_SessionResources.close_reader()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

原关闭错误。

源码：[`src/chronaxis/fast/session.py:553`](../../../src/chronaxis/fast/session.py#L553)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_SessionResources-create_directory"></a>
### `_SessionResources.create_directory`

独占创建并登记目录，避免自动终结器在写入者未结束时删除目录。

```python
_SessionResources.create_directory(work_dir)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`work_dir`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) &#124; None|是|无|位置或关键字。新会话暂存目录的父路径；None 使用系统临时目录。本方法只登记自己独占创建的子目录。|

#### 返回说明

Path。

#### 异常说明

创建或身份登记错误，已有目录不删除。

源码：[`src/chronaxis/fast/session.py:566`](../../../src/chronaxis/fast/session.py#L566)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_SessionResources-close"></a>
### `_SessionResources.close`

依次停止工作池、读取器、删除自有目录并退款，任一步失败保留重试责任。

```python
_SessionResources.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

原清理错误；未确认停止写入者时不删除目录。

源码：[`src/chronaxis/fast/session.py:578`](../../../src/chronaxis/fast/session.py#L578)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-run_session"></a>
## `run_session`

运行一个连续fast任务。

```python
run_session(spec, database=None, *, work_dir=None, cancel_event=None, statistics=None, _programs_checked=False)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|dict|是|无|位置或关键字。本次已编译会话或单文件声明，包含来源、公式、顺序和执行资源；调用过程不改写它。|
|`database`|cantools.database.Database &#124; None|否|None|位置或关键字。已加载的DBC定义，可在本进程复用；省略时由会话加载，不能与冻结声明冲突。|
|`work_dir`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) &#124; None|否|None|仅关键字。本次暂存目录的父路径；None使用系统临时目录，每次调用创建独立子目录。|
|`cancel_event`|Event &#124; None|否|None|仅关键字。外部取消事件，支持is_set()；设置后停止本次会话并清理，不返回成功结果。|
|`statistics`|dict &#124; None|否|None|仅关键字。接收本次执行统计的字典；记录实际工作进程、暂存量和关闭后的预算，None使用内部字典。|
|`_programs_checked`|bool|否|False|仅关键字。仅由内部调用传入的公式已检查标志；默认 False，普通入口仍核对原始公式和指令，不读取配置中的同名值。|

### 返回说明

(业务行list, 提示list)。

### 异常说明

配置/读取/公式/资源/协议/取消；不返回部分结果。
_programs_checked由公共编译后的内部入口传入；直接调用默认仍检查文本和指令。

源码：[`src/chronaxis/fast/session.py:606`](../../../src/chronaxis/fast/session.py#L606)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
