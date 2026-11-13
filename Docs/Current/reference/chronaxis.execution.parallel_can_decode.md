# `chronaxis.execution.parallel_can_decode`

按文件并行解码并恢复一个来源的连续记录流。

concatenate只预读每个工作进程的一块，按文件顺序消费；time_order先把已校验
的有序文件流写入本次受配额约束的暂存，再稳定归并。父层继续使用原同一时刻组及
状态机。所有工作进程、管道、暂存和费用归本owner，关闭不会删除输入或他人文件。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ControlChannel](chronaxis._control_wire.md#api-ControlChannel)、[DecodedCANRecord](chronaxis.sources.text_can_decode.md#api-DecodedCANRecord)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[SourceReadError](chronaxis.sources.protocol.md#api-SourceReadError)

## 对象导航

|对象|用途|
|---|---|
|[`_with_position`](#api-_with_position)|给本入口刚从固定块核验完成的记录重编号，不再解析其不可变字段键。|
|[`ParallelCANDecodeRead`](#api-ParallelCANDecodeRead)|拥有有限文件工作槽及唯一有序输出；文件EOF不结束来源。|
|[`ParallelCANDecodeRead.__init__`](#api-ParallelCANDecodeRead-__init__)|保存冻结文件任务，不读输入。|
|[`ParallelCANDecodeRead.closed`](#api-ParallelCANDecodeRead-closed)|返回实际关闭事实。|
|[`ParallelCANDecodeRead.exhausted`](#api-ParallelCANDecodeRead-exhausted)|返回完整来源结束事实。|
|[`ParallelCANDecodeRead.metadata`](#api-ParallelCANDecodeRead-metadata)|返回同次DBC元数据。|
|[`ParallelCANDecodeRead._receive`](#api-ParallelCANDecodeRead-_receive)|接收独立控制消息并监测退出。|
|[`ParallelCANDecodeRead._bytes`](#api-ParallelCANDecodeRead-_bytes)|接收已预付且限定长度的数据。|
|[`ParallelCANDecodeRead._assign`](#api-ParallelCANDecodeRead-_assign)|给空闲进程一个冻结文件并核元数据。|
|[`ParallelCANDecodeRead._accept_metadata`](#api-ParallelCANDecodeRead-_accept_metadata)|在原费用份额内接收READY，仅为实际超出的固定图预付差额。|
|[`ParallelCANDecodeRead._accept_metadata.reserve_model`](#api-ParallelCANDecodeRead-_accept_metadata-reserve_model)|先给新图及冻结副本付费。|
|[`ParallelCANDecodeRead.prepare_metadata`](#api-ParallelCANDecodeRead-prepare_metadata)|启动有限工作槽，只初始化DBC再授予首块。|
|[`ParallelCANDecodeRead._block`](#api-ParallelCANDecodeRead-_block)|收一块并记录已见事实，原始计数不以传输记录数替代。|
|[`ParallelCANDecodeRead._record_identity`](#api-ParallelCANDecodeRead-_record_identity)|核当前包的来源和文件身份，不将包内路径用作新文件打开目标。|
|[`ParallelCANDecodeRead._next_task`](#api-ParallelCANDecodeRead-_next_task)|完成文件后复用同一工作槽；没有下一文件时保留槽待统一关闭。|
|[`ParallelCANDecodeRead._stop_workers`](#api-ParallelCANDecodeRead-_stop_workers)|关闭全部本次进程和管道，不等待满管道自行排空。|
|[`ParallelCANDecodeRead._prepare_sorted`](#api-ParallelCANDecodeRead-_prepare_sorted)|先流式暂存已校验文件，再释放进程额度开始归并。|
|[`ParallelCANDecodeRead._push`](#api-ParallelCANDecodeRead-_push)|为一个有序文件取下一记录，堆键固定时间/文件位置/局部序号。|
|[`ParallelCANDecodeRead.__iter__`](#api-ParallelCANDecodeRead-__iter__)|返回本次游标。|
|[`ParallelCANDecodeRead.__next__`](#api-ParallelCANDecodeRead-__next__)|返回按明确归并政策排序的下一记录。|
|[`ParallelCANDecodeRead.close`](#api-ParallelCANDecodeRead-close)|释放本次进程、块和登记暂存。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from uuid import uuid4
from .._control_wire import ControlChannel
from .can_block_codec import decode_block, decode_metadata
from ..results.budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..sources.models import freeze_metadata
from ..sources.protocol import SourceReadError
from .history import _metadata_bytes
from .parallel_can_worker import BLOCK_RAM, WIRE_LIMIT, worker_main
```

</details>

<a id="api-_with_position"></a>
## `_with_position`

给本入口刚从固定块核验完成的记录重编号，不再解析其不可变字段键。

```python
_with_position(record, input_index, sequence)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`record`|[DecodedCANRecord](chronaxis.sources.text_can_decode.md#api-DecodedCANRecord)|是|无|位置或关键字。本次已核过的解码记录；复用其原帧、值与状态，不重新解析字段键。|
|`input_index`|int|是|无|位置或关键字。归并后对应原输入列表的非负位置，用来替换工作文件内的局部输入编号。|
|`sequence`|int|是|无|位置或关键字。归并后的非负来源序号，用来替换记录的局部交付序号；raw位置仍保原样。|

### 返回说明

新冻结记录；原始帧、字段值、状态和重建事实继续共享已核不可变内容。

### 异常说明

新编号、类型、状态或字段对结构非法时沿用内部工厂检查。
仅供本模块已核记录使用；外部记录构造和新块解码仍完整解析规范字段。
临时键集合至多4096项，按512+192*4096字节小于1MiB；它在已有8MiB
接收/归并空间中、6MiB模型上界以外的2MiB余量内，用完即释放，不跨记录缓存。

源码：[`src/chronaxis/execution/parallel_can_decode.py:26`](../../../src/chronaxis/execution/parallel_can_decode.py#L26)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ParallelCANDecodeRead"></a>
## `ParallelCANDecodeRead`

拥有有限文件工作槽及唯一有序输出；文件EOF不结束来源。

各槽最多一个在途块。父预付子账本上限及接收展开空间，记录的长期消费者
自行计费；归并时工作进程已退出，再为每个打开的暂存块预付空间。

```python
ParallelCANDecodeRead(spec, budget, signals, *, process_count, work_dir, emit_frame_ids=None, **options)
```


源码：[`src/chronaxis/execution/parallel_can_decode.py:50`](../../../src/chronaxis/execution/parallel_can_decode.py#L50)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ParallelCANDecodeRead-__init__"></a>
### `ParallelCANDecodeRead.__init__`

保存冻结文件任务，不读输入。

```python
ParallelCANDecodeRead.__init__(spec, budget, signals, *, process_count, work_dir, emit_frame_ids=None, **options)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|CANTextSpec|是|无|位置或关键字。冻结的同一来源文件、DBC、通道、时间及file_merge声明。文件按inputs位置标识，不把文件当独立会话。|
|`budget`|ResourceBudget|是|无|位置或关键字。整个分析任务共享的预算，预付工作进程空间、传输缓冲和归并输入；不是每进程一份额度。|
|`signals`|tuple[SignalDefinition, ...]|是|无|位置或关键字。本次消费者需要解码的同来源信号定义；只按这些字段及额外重建字段投影DBC物理值。|
|`process_count`|int|是|无|仅关键字。正整数读取/解码进程上限，实际不超过文件数，不包含主进程。|
|`work_dir`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|仅关键字。本次运行已分配的专用工作目录；time_order在其中创建唯一归并子目录，不使用输入目录。|
|`emit_frame_ids`|tuple[int, ...] &#124; None|否|None|仅关键字。限定实际交付的报文ID集合。None交付全部已解析帧；筛选不自动缩小任务要求的时间检查和观测范围。|
|`options`|dict|否|{}|可变关键字。传给同次CANTextDecodeRead的已核内部选项，包括trace、integrity、时间检查集合、周期字段及可重建的DBC上下文声明。不是任意用户回调。|

#### 返回说明

owner。

#### 异常说明

类型/预算。

源码：[`src/chronaxis/execution/parallel_can_decode.py:57`](../../../src/chronaxis/execution/parallel_can_decode.py#L57)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ParallelCANDecodeRead-closed"></a>
### `ParallelCANDecodeRead.closed`

返回实际关闭事实。

```python
ParallelCANDecodeRead.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

bool。

#### 异常说明

无。

源码：[`src/chronaxis/execution/parallel_can_decode.py:94`](../../../src/chronaxis/execution/parallel_can_decode.py#L94)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ParallelCANDecodeRead-exhausted"></a>
### `ParallelCANDecodeRead.exhausted`

返回完整来源结束事实。

```python
ParallelCANDecodeRead.exhausted
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

bool。

#### 异常说明

无。

源码：[`src/chronaxis/execution/parallel_can_decode.py:99`](../../../src/chronaxis/execution/parallel_can_decode.py#L99)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ParallelCANDecodeRead-metadata"></a>
### `ParallelCANDecodeRead.metadata`

返回同次DBC元数据。

```python
ParallelCANDecodeRead.metadata
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

冻结映射。

#### 异常说明

未开始时拒绝。

源码：[`src/chronaxis/execution/parallel_can_decode.py:104`](../../../src/chronaxis/execution/parallel_can_decode.py#L104)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ParallelCANDecodeRead-_receive"></a>
### `ParallelCANDecodeRead._receive`

接收独立控制消息并监测退出。

```python
ParallelCANDecodeRead._receive(slot)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`slot`|dict|是|无|位置或关键字。本owner拥有的一个工作槽，保存process/control/data/tree及当前file/block/reply；不能传其他任务的进程槽。|

#### 返回说明

tuple。

#### 异常说明

子错误/崩溃/取消。

源码：[`src/chronaxis/execution/parallel_can_decode.py:110`](../../../src/chronaxis/execution/parallel_can_decode.py#L110)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ParallelCANDecodeRead-_bytes"></a>
### `ParallelCANDecodeRead._bytes`

接收已预付且限定长度的数据。

```python
ParallelCANDecodeRead._bytes(slot, size)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`slot`|dict|是|无|位置或关键字。本owner拥有的一个工作槽，保存process/control/data/tree及当前file/block/reply；不能传其他任务的进程槽。|
|`size`|int|是|无|位置或关键字。控制消息声明的数据块字节数，须在1至WIRE_LIMIT之间；实收长度必须相等。|

#### 返回说明

bytes。

#### 异常说明

断连/协议错。

源码：[`src/chronaxis/execution/parallel_can_decode.py:139`](../../../src/chronaxis/execution/parallel_can_decode.py#L139)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ParallelCANDecodeRead-_assign"></a>
### `ParallelCANDecodeRead._assign`

给空闲进程一个冻结文件并核元数据。

```python
ParallelCANDecodeRead._assign(slot, index)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`slot`|dict|是|无|位置或关键字。本owner拥有的一个工作槽，保存process/control/data/tree及当前file/block/reply；不能传其他任务的进程槽。|
|`index`|int|是|无|位置或关键字。来源inputs中的零基文件位置，限定在本次已登记文件范围；不是工作进程编号。|

#### 返回说明

None。

#### 异常说明

读取或声明不符。

源码：[`src/chronaxis/execution/parallel_can_decode.py:153`](../../../src/chronaxis/execution/parallel_can_decode.py#L153)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ParallelCANDecodeRead-_accept_metadata"></a>
### `ParallelCANDecodeRead._accept_metadata`

在原费用份额内接收READY，仅为实际超出的固定图预付差额。

```python
ParallelCANDecodeRead._accept_metadata(packet)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`packet`|bytes|是|无|位置或关键字。从工作进程收到的完整CMT1 READY包；恢复前按实际展开预留RAM，接受后由本owner持有冻结事实。|

#### 返回说明

None，首份冻结事实保留到close，后续只比较后释放。

#### 异常说明

包错误、事实不同、预算或取消；退款失败附注保原错及可重试拥有者。

源码：[`src/chronaxis/execution/parallel_can_decode.py:167`](../../../src/chronaxis/execution/parallel_can_decode.py#L167)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ParallelCANDecodeRead-_accept_metadata-reserve_model"></a>
### `ParallelCANDecodeRead._accept_metadata.reserve_model`

先给新图及冻结副本付费。

```python
ParallelCANDecodeRead._accept_metadata.reserve_model(amount)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`amount`|int|是|无|位置或关键字。解码器报告的累计原生图展开估算；父端据此预付当前峰值所需RAM，不是额外收费次数。|

#### 返回说明

None。

#### 异常说明

原预算错误。

源码：[`src/chronaxis/execution/parallel_can_decode.py:177`](../../../src/chronaxis/execution/parallel_can_decode.py#L177)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ParallelCANDecodeRead-prepare_metadata"></a>
### `ParallelCANDecodeRead.prepare_metadata`

启动有限工作槽，只初始化DBC再授予首块。

```python
ParallelCANDecodeRead.prepare_metadata()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

元数据。

#### 异常说明

启动/预算/元数据错。

源码：[`src/chronaxis/execution/parallel_can_decode.py:215`](../../../src/chronaxis/execution/parallel_can_decode.py#L215)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ParallelCANDecodeRead-_block"></a>
### `ParallelCANDecodeRead._block`

收一块并记录已见事实，原始计数不以传输记录数替代。

```python
ParallelCANDecodeRead._block(index)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`index`|int|是|无|位置或关键字。来源inputs中的零基文件位置，限定在本次已登记文件范围；不是工作进程编号。|

#### 返回说明

块。

#### 异常说明

协议/读取错误。

源码：[`src/chronaxis/execution/parallel_can_decode.py:269`](../../../src/chronaxis/execution/parallel_can_decode.py#L269)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ParallelCANDecodeRead-_record_identity"></a>
### `ParallelCANDecodeRead._record_identity`

核当前包的来源和文件身份，不将包内路径用作新文件打开目标。

```python
ParallelCANDecodeRead._record_identity(index, records)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`index`|int|是|无|位置或关键字。当前输入文件在原始列表中的位置，用于选取必须匹配的来源路径；本方法只校验，不改变序号。|
|`records`|list[[DecodedCANRecord](chronaxis.sources.text_can_decode.md#api-DecodedCANRecord)]|是|无|位置或关键字。本包已恢复的记录列表；来源名、局部输入编号0、原路径及记录/raw序号必须相符，不打开包内路径或重编号。|

#### 返回说明

None。

#### 异常说明

来源、原文件或序号不同步时SourceReadError。

源码：[`src/chronaxis/execution/parallel_can_decode.py:303`](../../../src/chronaxis/execution/parallel_can_decode.py#L303)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ParallelCANDecodeRead-_next_task"></a>
### `ParallelCANDecodeRead._next_task`

完成文件后复用同一工作槽；没有下一文件时保留槽待统一关闭。

```python
ParallelCANDecodeRead._next_task(index)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`index`|int|是|无|位置或关键字。来源inputs中的零基文件位置，限定在本次已登记文件范围；不是工作进程编号。|

#### 返回说明

None。

#### 异常说明

初始化错。

源码：[`src/chronaxis/execution/parallel_can_decode.py:315`](../../../src/chronaxis/execution/parallel_can_decode.py#L315)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ParallelCANDecodeRead-_stop_workers"></a>
### `ParallelCANDecodeRead._stop_workers`

关闭全部本次进程和管道，不等待满管道自行排空。

```python
ParallelCANDecodeRead._stop_workers(*, completed=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`completed`|bool|否|False|仅关键字。True要求所有工作进程在完整EOF后正常退出；False用于失败或取消，可终止本次仍在途进程。|

#### 返回说明

None。

#### 异常说明

真实关闭失败保留槽。

源码：[`src/chronaxis/execution/parallel_can_decode.py:323`](../../../src/chronaxis/execution/parallel_can_decode.py#L323)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ParallelCANDecodeRead-_prepare_sorted"></a>
### `ParallelCANDecodeRead._prepare_sorted`

先流式暂存已校验文件，再释放进程额度开始归并。

```python
ParallelCANDecodeRead._prepare_sorted()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

配额/IO/原输入错误。

源码：[`src/chronaxis/execution/parallel_can_decode.py:367`](../../../src/chronaxis/execution/parallel_can_decode.py#L367)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ParallelCANDecodeRead-_push"></a>
### `ParallelCANDecodeRead._push`

为一个有序文件取下一记录，堆键固定时间/文件位置/局部序号。

```python
ParallelCANDecodeRead._push(index)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`index`|int|是|无|位置或关键字。来源inputs中的零基文件位置，限定在本次已登记文件范围；不是工作进程编号。|

#### 返回说明

None。

#### 异常说明

暂存截断。

源码：[`src/chronaxis/execution/parallel_can_decode.py:414`](../../../src/chronaxis/execution/parallel_can_decode.py#L414)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ParallelCANDecodeRead-__iter__"></a>
### `ParallelCANDecodeRead.__iter__`

返回本次游标。

```python
ParallelCANDecodeRead.__iter__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

self。

#### 异常说明

无。

源码：[`src/chronaxis/execution/parallel_can_decode.py:451`](../../../src/chronaxis/execution/parallel_can_decode.py#L451)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ParallelCANDecodeRead-__next__"></a>
### `ParallelCANDecodeRead.__next__`

返回按明确归并政策排序的下一记录。

```python
ParallelCANDecodeRead.__next__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

DecodedCANRecord。

#### 异常说明

EOF或读取/预算错。

源码：[`src/chronaxis/execution/parallel_can_decode.py:455`](../../../src/chronaxis/execution/parallel_can_decode.py#L455)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ParallelCANDecodeRead-close"></a>
### `ParallelCANDecodeRead.close`

释放本次进程、块和登记暂存。

```python
ParallelCANDecodeRead.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

清理失败可重试。

源码：[`src/chronaxis/execution/parallel_can_decode.py:505`](../../../src/chronaxis/execution/parallel_can_decode.py#L505)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
