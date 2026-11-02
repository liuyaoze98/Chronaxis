# chronaxis.execution.can_batch_reader

将有界CAN批次接成按需历史，保留每条原yield的时间及必要记录的原序。

旧读取/解码仍由批进程逐条执行。这里只省去无关帧的重复装箱和历史：全部原时间
用于首末/计数/倒退检查，目标记录保存完整values，信号按样本总数分批。
无BLF导出不建立原帧仓。所有批次、转换、引用和数组在共享预算内预付；不保整文件。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CANObservationRead](chronaxis.execution.can_reader.md#api-CANObservationRead)、[CANSourceRef](chronaxis.sources.can_spec.md#api-CANSourceRef)、[LegacyDecodedFrame](chronaxis.legacy.records.md#api-LegacyDecodedFrame)、[LegacyRawFrame](chronaxis.legacy.records.md#api-LegacyRawFrame)、[SignalBatch](chronaxis.sources.models.md#api-SignalBatch)、[SourceReadError](chronaxis.sources.protocol.md#api-SourceReadError)、[TimeOverflowError](chronaxis.timebase.conversion.md#api-TimeOverflowError)

## 对象导航

|对象|用途|
|---|---|
|[`_float_seconds_ns`](#api-_float_seconds_ns)|精确把已有二进制float秒舍入至纳秒，不经Decimal文本和逐位展开。|
|[`_dense_time_tail`](#api-_dense_time_tail)|首条已按原规则提交后，继续原顺序校验余下时间，不提前报告末点错误。|
|[`_retained_time_indices`](#api-_retained_time_indices)|确认保留记录能按原序号使用稀疏时间表，不替代传输包的完整认证。|
|[`_sparse_batch_times`](#api-_sparse_batch_times)|先检查本批全部原始时间是否合法，再只转换批次首末点及后续计算真正需要的记录时间。没有转换成纳秒的其他记录仍已经过原时间检查。|
|[`CANBatchObservationRead`](#api-CANBatchObservationRead)|复用真实read责任槽与完成协议，追加一个有界批次及其游标。|
|[`CANBatchObservationRead.__init__`](#api-CANBatchObservationRead-__init__)|安装批游标后调用原责任初始化。|
|[`CANBatchObservationRead._load_batch`](#api-CANBatchObservationRead-_load_batch)|读取下一批并检查其中所有原始时间；读到整个来源末尾后结束暂存写入。|
|[`CANBatchObservationRead._advance_record`](#api-CANBatchObservationRead-_advance_record)|推进到下一保留原记录，最多追加一次raw及消息历史。|
|[`CANBatchObservationRead._packed_batch`](#api-CANBatchObservationRead-_packed_batch)|跨保留记录装箱至总样本上限，不为每条非目标原帧生成空历史。|
|[`CANBatchObservationRead.__next__`](#api-CANBatchObservationRead-__next__)|返回下一批信号，或最后一个标记来源结束的空批；迭代真正结束后才能读取完整观测信息或移交暂存。|
|[`CANBatchObservationRead.close`](#api-CANBatchObservationRead-close)|释放当前批次的引用，再按既定顺序关闭本对象管理的资源。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from math import isfinite
from ..legacy.records import LegacyDecodedFrame, LegacyRawFrame
from ..results.spool import _reserve_owned_ram, _release_owned_ram
from ..sources.can_spec import CANSourceRef
from ..sources.models import SignalBatch
from ..sources.packing import pack_decoded
from ..sources.protocol import SourceReadError
from ..timebase.conversion import checked_add_ns, INT64_MIN, INT64_MAX, TimeOverflowError, require_int64_ns
from .can_reader import CANObservationRead
from .history import _pending_bytes
```

</details>

<a id="api-_float_seconds_ns"></a>
## `_float_seconds_ns`

精确把已有二进制float秒舍入至纳秒，不经Decimal文本和逐位展开。

```python
_float_seconds_ns(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|float|是|无|位置或关键字。原始秒时间戳，必须是有限的Python浮点数；转换后得到纳秒坐标。|

### 返回说明

(int64纳秒, 是否量化)，最近偶数舍入。

### 异常说明

TypeError/ValueError为输入类型/非有限；TimeOverflowError为舍入后越界。

本函数直接报告的具体错误：

- `TypeError`：原CAN时间需要float。
- `ValueError`：原CAN时间必须有限。
- `TimeOverflowError`：time_ns超出int64纳秒范围。

### 边界说明

整数比精确保留float已有位值；负零、负半值和次正规数均不先乘float。

源码：[`src/chronaxis/execution/can_batch_reader.py:20`](../../../src/chronaxis/execution/can_batch_reader.py#L20)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_dense_time_tail"></a>
## `_dense_time_tail`

首条已按原规则提交后，继续原顺序校验余下时间，不提前报告末点错误。

```python
_dense_time_tail(owner, timestamps, offset, mapped_times)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|[CANBatchObservationRead](chronaxis.execution.can_batch_reader.md#api-CANBatchObservationRead)|是|无|位置或关键字。当前批量读取对象，持有时间转换所需内存额度和来源偏移量。|
|`timestamps`|Sequence[float]|是|无|位置或关键字。本批原始秒时间戳，按原帧顺序转换成纳秒。|
|`offset`|int|是|无|位置或关键字。已经核对过的纳秒偏移，用于把来源时间映射到会话时间。|
|`mapped_times`|list[int]|是|无|位置或关键字。转换结果缓冲；调用时已有首帧时间，函数在后面补入其余帧时间。|

### 返回说明

完整映射tuple。

### 异常说明

原时间/偏移溢出、倒退或取消；保实际已完成观测前缀。

本函数直接报告的具体错误：

- `TimeOverflowError`：shifted_time_ns超出int64纳秒范围。
- `SourceReadError`：CAN原yield时间回退，禁止重排。

### 流程说明

稀疏证明不成立时逐项换算，微小float回退仍允许量化成同一纳秒。

源码：[`src/chronaxis/execution/can_batch_reader.py:42`](../../../src/chronaxis/execution/can_batch_reader.py#L42)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_retained_time_indices"></a>
## `_retained_time_indices`

确认保留记录能按原序号使用稀疏时间表，不替代传输包的完整认证。

```python
_retained_time_indices(batch)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`batch`|LegacyDecodedBatch|是|无|位置或关键字。已检查时间为有限且非递减的帧批次，按其中保留帧的位置取得时间索引。|

### 返回说明

索引列表，或None表示走完整换算。

### 异常说明

取消/分配错误原样传播；非典型记录回原路径，不新增业务拒绝条件。

源码：[`src/chronaxis/execution/can_batch_reader.py:66`](../../../src/chronaxis/execution/can_batch_reader.py#L66)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_sparse_batch_times"></a>
## `_sparse_batch_times`

先检查本批全部原始时间是否合法，再只转换批次首末点及后续计算真正需要的记录时间。没有转换成纳秒的其他记录仍已经过原时间检查。

```python
_sparse_batch_times(owner, batch)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|[CANBatchObservationRead](chronaxis.execution.can_batch_reader.md#api-CANBatchObservationRead)|是|无|位置或关键字。当前读取对象，已经为时间转换预留内存额度。|
|`batch`|LegacyDecodedBatch|是|无|位置或关键字。16至4096帧的批次，目标帧不超过四分之一；使用稀疏路径读取所需帧时间。|

### 返回说明

按原序号索引的tuple；无需消费的位置为None，证明失败则返回完整映射。

### 异常说明

业务错误沿原顺序产生；取消/MemoryError保原异常，只保已提交的真实前缀。
依据: 有限float非降时，精确乘十亿后最近偶数舍入仍单调；固定int偏移也保持顺序。
    首末原纳秒与偏移后纳秒均在int64范围，即证明所有内部时间有界。保留点仍精确
    换算其纳秒和量化标志。末点失败不能抢先报错，必须回原后缀寻找第一处错误。
费用: 最多4096个槽和1024个保留索引，含回退表仍小于原4MiB预付，无缓存或新owner。

源码：[`src/chronaxis/execution/can_batch_reader.py:90`](../../../src/chronaxis/execution/can_batch_reader.py#L90)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANBatchObservationRead"></a>
## `CANBatchObservationRead`

复用真实read责任槽与完成协议，追加一个有界批次及其游标。

_incoming由进程保活原记录，转换表单独预付。原yield总数与消息仓保存条数分开；
同一时刻记录跨SignalBatch不合并，尚未输出的同一时刻别名不提前推进watermark。

```python
CANBatchObservationRead(owner, request)
```

继承关系：[CANObservationRead](chronaxis.execution.can_reader.md#api-CANObservationRead)。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/execution/can_batch_reader.py:146`](../../../src/chronaxis/execution/can_batch_reader.py#L146)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANBatchObservationRead-__init__"></a>
### `CANBatchObservationRead.__init__`

安装批游标后调用原责任初始化。

```python
CANBatchObservationRead.__init__(owner, request)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|BudgetedLegacyCANSourceAdapter|是|无|位置或关键字。创建此读取的CAN来源适配器，提供配置、资源额度和关闭管理。|
|`request`|ReadRequest|是|无|位置或关键字。本次读取请求，指定所需信号、时间范围和批次大小。|

#### 返回说明

read。

#### 异常说明

原错误。

源码：[`src/chronaxis/execution/can_batch_reader.py:153`](../../../src/chronaxis/execution/can_batch_reader.py#L153)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANBatchObservationRead-_load_batch"></a>
### `CANBatchObservationRead._load_batch`

读取下一批并检查其中所有原始时间；读到整个来源末尾后结束暂存写入。

```python
CANBatchObservationRead._load_batch()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

bool是否取到批次，空时间批也算真实返回。

#### 异常说明

原进程、时间倒退、预算/仓错误；调用者统一保留最高恢复owner。

本函数直接报告的具体错误：

- `SourceReadError`：CAN批次原序跨度不连续。
- `SourceReadError`：CAN批次时间范围与实际来源不同。
- `TimeOverflowError`：shifted_time_ns超出int64纳秒范围。
- `SourceReadError`：CAN原yield时间回退，禁止重排。
- `SourceReadError`：CAN批进程未完成真实EOF及关闭。
- `SourceReadError`：CAN所需记录时间回退，禁止重排。

源码：[`src/chronaxis/execution/can_batch_reader.py:161`](../../../src/chronaxis/execution/can_batch_reader.py#L161)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANBatchObservationRead-_advance_record"></a>
### `CANBatchObservationRead._advance_record`

推进到下一保留原记录，最多追加一次raw及消息历史。

```python
CANBatchObservationRead._advance_record()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

bool是否有记录，跳过无目标批但保其全部观测。

#### 异常说明

原记录/定位/仓/预算/取消；不在别名分片处重复保存。

本函数直接报告的具体错误：

- `SourceReadError`：目标CAN frame_id的通道/标准/FD标志歧义。

源码：[`src/chronaxis/execution/can_batch_reader.py:247`](../../../src/chronaxis/execution/can_batch_reader.py#L247)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANBatchObservationRead-_packed_batch"></a>
### `CANBatchObservationRead._packed_batch`

跨保留记录装箱至总样本上限，不为每条非目标原帧生成空历史。

```python
CANBatchObservationRead._packed_batch()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

已校验SignalBatch，或者None表示真实输入耗尽且无剩余样本。

#### 异常说明

原模型/归一化/预算/IO错误；样本时间和sequence均来自同次原记录。

源码：[`src/chronaxis/execution/can_batch_reader.py:280`](../../../src/chronaxis/execution/can_batch_reader.py#L280)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANBatchObservationRead-__next__"></a>
### `CANBatchObservationRead.__next__`

返回下一批信号，或最后一个标记来源结束的空批；迭代真正结束后才能读取完整观测信息或移交暂存。

```python
CANBatchObservationRead.__next__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

SignalBatch。

#### 异常说明

StopIteration为真实完成；其他原错误poison本read。

源码：[`src/chronaxis/execution/can_batch_reader.py:323`](../../../src/chronaxis/execution/can_batch_reader.py#L323)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANBatchObservationRead-close"></a>
### `CANBatchObservationRead.close`

释放当前批次的引用，再按既定顺序关闭本对象管理的资源。

```python
CANBatchObservationRead.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原可恢复错误。

源码：[`src/chronaxis/execution/can_batch_reader.py:353`](../../../src/chronaxis/execution/can_batch_reader.py#L353)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
