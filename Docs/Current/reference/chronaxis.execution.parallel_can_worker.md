# `chronaxis.execution.parallel_can_worker`

单个可复用CAN文件工作进程：读取、解码并按许可交付有限数据块。

每个工作进程只解析一个当前文件，不启动子进程，不运行事件或积分状态机。
父进程预付全部工作空间后授予一次next许可；控制错误独立于数据块发送。
文件EOF保留观测事实，等待下一文件任务；来源EOF由父进程统一判定。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CANTextDecodeRead](chronaxis.sources.text_can_decode.md#api-CANTextDecodeRead)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)

## 对象导航

|对象|用途|
|---|---|
|[`plain`](#api-plain)|转换有限冻结元数据为可传输结构。|
|[`facts`](#api-facts)|摘取同次读取得到的有限事实，不把观测末点当水位。|
|[`read_block`](#api-read_block)|在固定预付空间内读取一块，不为凑满64条继续读取宽记录。|
|[`worker_main`](#api-worker_main)|等待文件/读取许可并发送有界结果。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from collections.abc import Mapping
from dataclasses import replace
from time import perf_counter
from ..results.budget import ResourceBudget
from ..sources.text_can_decode import CANTextDecodeRead
```

</details>

<a id="api-plain"></a>
## `plain`

转换有限冻结元数据为可传输结构。

```python
plain(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|object|是|无|位置或关键字。有限且已核的冻结元数据；映射和序列递归变成可传输容器，原生叶值保留。|

### 返回说明

独立容器。

### 异常说明

无。

源码：[`src/chronaxis/execution/parallel_can_worker.py:25`](../../../src/chronaxis/execution/parallel_can_worker.py#L25)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-facts"></a>
## `facts`

摘取同次读取得到的有限事实，不把观测末点当水位。

```python
facts(reader)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`reader`|[CANTextDecodeRead](chronaxis.sources.text_can_decode.md#api-CANTextDecodeRead)|是|无|位置或关键字。本文件同次读取owner，提供原行数、已见时间范围、顺序检查端点和解码次数；这些事实不当作消费水位。|

### 返回说明

dict。

### 异常说明

无。

源码：[`src/chronaxis/execution/parallel_can_worker.py:35`](../../../src/chronaxis/execution/parallel_can_worker.py#L35)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-read_block"></a>
## `read_block`

在固定预付空间内读取一块，不为凑满64条继续读取宽记录。

```python
read_block(reader)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`reader`|Iterator[DecodedCANRecord]|是|无|位置或关键字。按原顺序交付解码记录的游标；本函数只读取当前可容纳的一批，不预读下一批，也不关闭游标。|

### 返回说明

(records, eof)；只有实际读到EOF才置真。

### 异常说明

单条记录超过原4MiB估算上限或读取失败；不丢弃、回读或重排记录。

源码：[`src/chronaxis/execution/parallel_can_worker.py:43`](../../../src/chronaxis/execution/parallel_can_worker.py#L43)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-worker_main"></a>
## `worker_main`

等待文件/读取许可并发送有界结果。

```python
worker_main(control, data)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`control`|Connection|是|无|位置或关键字。父进程为本槽创建的双向控制连接，传文件任务、next许可、错误及完成通知。|
|`data`|Connection|是|无|位置或关键字。单向数据连接的发送端；只发送不超过WIRE_LIMIT的已序列化块，与控制通道分离。|

### 返回说明

None。

### 异常说明

父断连退出。

生命周期由父拥有；正常文件结束关闭解析器，异常先发错误控制消息再关闭。
任意时刻取消可由父终止工作进程；不等待满数据管道才能报告错误。

源码：[`src/chronaxis/execution/parallel_can_worker.py:71`](../../../src/chronaxis/execution/parallel_can_worker.py#L71)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
