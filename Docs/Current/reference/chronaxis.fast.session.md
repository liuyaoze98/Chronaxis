# `chronaxis.fast.session`

一个fast会话的多文件调度和最终累计。

worker只求当前帧贡献；主进程控制统一预算、交付顺序及成功发布前的完整性。
concatenate可暂停可选预读；time_order必要暂存完成后稳定归并。临时目录和
进程均属于本次调用，异常不返回部分结果。内联与batch不经传输协议。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[BudgetExceededError](chronaxis.results.errors.md#api-BudgetExceededError)、[FileContributions](chronaxis.fast.stream.md#api-FileContributions)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)

## 对象导航

|对象|用途|
|---|---|
|[`effective_spec`](#api-effective_spec)|取得不修改原声明的执行视图。|
|[`_worker_process_limit`](#api-_worker_process_limit)|从已验证的进程上限和文件数取得文件工作进程数，不包含主进程。|
|[`file_specs`](#api-file_specs)|展开有限文件声明。|
|[`SessionAccumulator`](#api-SessionAccumulator)|只有主会话持有的标量累计器。计数、目标缺失和帧身份按计算项分别核验。|
|[`SessionAccumulator.__init__`](#api-SessionAccumulator-__init__)|准备累计器。|
|[`SessionAccumulator.consume`](#api-SessionAccumulator-consume)|按输入顺序逐项相加。|
|[`SessionAccumulator.finish_file`](#api-SessionAccumulator-finish_file)|合并已关闭文件的事实。|
|[`SessionAccumulator.result`](#api-SessionAccumulator-result)|核完整消费后生成业务行。|
|[`FilePool`](#api-FilePool)|管理有限工作槽及每文件连续块前缀；不在内存保存所有暂存块描述。|
|[`FilePool.__init__`](#api-FilePool-__init__)|初始化但不启动。|
|[`FilePool.check_cancel`](#api-FilePool-check_cancel)|传递外部取消。|
|[`FilePool.start`](#api-FilePool-start)|预付全部工作槽后启动spawn。|
|[`FilePool.assign`](#api-FilePool-assign)|按文件声明顺序派发下一文件。|
|[`FilePool.grant`](#api-FilePool-grant)|授权一个完整块的唯一交付路径。|
|[`FilePool.pump`](#api-FilePool-pump)|推进有限控制和数据消息，优先响应所有worker错误。|
|[`FilePool.message`](#api-FilePool-message)|核验工作槽状态及块序号。|
|[`FilePool.packet_records`](#api-FilePool-packet_records)|验证块间顺序并展开一块。|
|[`FilePool.read_spool`](#api-FilePool-read_spool)|读取并删除一个已提交块。|
|[`FilePool.concatenate`](#api-FilePool-concatenate)|消费当前文件，后续文件同时预读。|
|[`FilePool.file_records`](#api-FilePool-file_records)|逐块读取一个已完整暂存文件。|
|[`FilePool.time_order`](#api-FilePool-time_order)|完成必要暂存后k路稳定归并。|
|[`FilePool.close`](#api-FilePool-close)|关闭自有工作树。|
|[`run_session`](#api-run_session)|运行一个连续fast任务。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from hashlib import sha256
from contextlib import ExitStack
from multiprocessing.connection import wait
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from ..results.budget import ResourceBudget
from ..results.errors import BudgetExceededError
from .blocks import RAM, LIMIT, encode, decode, batches
from .compute import prepare_metric
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

源码：[`src/chronaxis/fast/session.py:25`](../../../src/chronaxis/fast/session.py#L25)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

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

源码：[`src/chronaxis/fast/session.py:35`](../../../src/chronaxis/fast/session.py#L35)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

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

源码：[`src/chronaxis/fast/session.py:45`](../../../src/chronaxis/fast/session.py#L45)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-SessionAccumulator"></a>
## `SessionAccumulator`

只有主会话持有的标量累计器。计数、目标缺失和帧身份按计算项分别核验。

```python
SessionAccumulator(spec)
```


源码：[`src/chronaxis/fast/session.py:53`](../../../src/chronaxis/fast/session.py#L53)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-SessionAccumulator-__init__"></a>
### `SessionAccumulator.__init__`

准备累计器。

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

公式声明错误。

源码：[`src/chronaxis/fast/session.py:56`](../../../src/chronaxis/fast/session.py#L56)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

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

源码：[`src/chronaxis/fast/session.py:68`](../../../src/chronaxis/fast/session.py#L68)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

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

源码：[`src/chronaxis/fast/session.py:76`](../../../src/chronaxis/fast/session.py#L76)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

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

源码：[`src/chronaxis/fast/session.py:96`](../../../src/chronaxis/fast/session.py#L96)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-FilePool"></a>
## `FilePool`

管理有限工作槽及每文件连续块前缀；不在内存保存所有暂存块描述。

```python
FilePool(specs, budget, directory, cancel, statistics)
```


源码：[`src/chronaxis/fast/session.py:111`](../../../src/chronaxis/fast/session.py#L111)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-FilePool-__init__"></a>
### `FilePool.__init__`

初始化但不启动。

```python
FilePool.__init__(specs, budget, directory, cancel, statistics)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`specs`|list[dict]|是|无|位置或关键字。按声明顺序展开的单文件任务；所有成员共用一套会话计算定义。|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)|是|无|位置或关键字。本次会话共享的受管理资源用量记录；先预约空间，再构造缓冲或暂存。|
|`directory`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。本次会话私有暂存目录；所有贡献块均写到该目录，清理不涉及输入或旧结果。|
|`cancel`|Event &#124; None|是|无|位置或关键字。调用方取消事件；is_set为真时停止继续读取或调度，None表示没有外部取消信号。|
|`statistics`|dict|是|无|位置或关键字。接收本次执行统计的字典；记录实际工作进程、暂存量和关闭后的预算，None使用内部字典。|

#### 返回说明

新调度器。

#### 异常说明

无；start安装进程资源的关闭责任。

源码：[`src/chronaxis/fast/session.py:114`](../../../src/chronaxis/fast/session.py#L114)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

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

源码：[`src/chronaxis/fast/session.py:133`](../../../src/chronaxis/fast/session.py#L133)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-FilePool-start"></a>
### `FilePool.start`

预付全部工作槽后启动spawn。

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

预算/启动/归属失败。

源码：[`src/chronaxis/fast/session.py:139`](../../../src/chronaxis/fast/session.py#L139)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

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

源码：[`src/chronaxis/fast/session.py:164`](../../../src/chronaxis/fast/session.py#L164)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

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

源码：[`src/chronaxis/fast/session.py:173`](../../../src/chronaxis/fast/session.py#L173)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

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

源码：[`src/chronaxis/fast/session.py:194`](../../../src/chronaxis/fast/session.py#L194)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

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

源码：[`src/chronaxis/fast/session.py:226`](../../../src/chronaxis/fast/session.py#L226)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

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

源码：[`src/chronaxis/fast/session.py:265`](../../../src/chronaxis/fast/session.py#L265)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

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

源码：[`src/chronaxis/fast/session.py:282`](../../../src/chronaxis/fast/session.py#L282)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

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

源码：[`src/chronaxis/fast/session.py:297`](../../../src/chronaxis/fast/session.py#L297)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

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

源码：[`src/chronaxis/fast/session.py:327`](../../../src/chronaxis/fast/session.py#L327)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

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

源码：[`src/chronaxis/fast/session.py:337`](../../../src/chronaxis/fast/session.py#L337)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-FilePool-close"></a>
### `FilePool.close`

关闭自有工作树。

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

关闭/异常退出错误。
失败时先取消再终止；不等待仍被背压阻塞的worker自行退出。

源码：[`src/chronaxis/fast/session.py:361`](../../../src/chronaxis/fast/session.py#L361)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-run_session"></a>
## `run_session`

运行一个连续fast任务。

```python
run_session(spec, database=None, *, work_dir=None, cancel_event=None, statistics=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|dict|是|无|位置或关键字。本次已编译会话或单文件声明，包含来源、公式、顺序和执行资源；调用过程不改写它。|
|`database`|cantools.database.Database &#124; None|否|None|位置或关键字。已加载的DBC定义，可在本进程复用；省略时由会话加载，不能与冻结声明冲突。|
|`work_dir`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) &#124; None|否|None|仅关键字。本次暂存目录的父路径；None使用系统临时目录，每次调用创建独立子目录。|
|`cancel_event`|Event &#124; None|否|None|仅关键字。外部取消事件，支持is_set()；设置后停止本次会话并清理，不返回成功结果。|
|`statistics`|dict &#124; None|否|None|仅关键字。接收本次执行统计的字典；记录实际工作进程、暂存量和关闭后的预算，None使用内部字典。|

### 返回说明

(业务行list, 提示list)。

### 异常说明

配置/读取/公式/资源/协议/取消；不返回部分结果。

源码：[`src/chronaxis/fast/session.py:400`](../../../src/chronaxis/fast/session.py#L400)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
