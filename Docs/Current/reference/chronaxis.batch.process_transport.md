# chronaxis.batch.process_transport

传递独立计划快照和小型结果，保留工作进程中的失败清理责任。

管道仅连接本次创建的可信子进程，不读取外部序列化对象。计划重建后核对身份，
大型结果在子进程内写出并关闭。清理失败的进程暂停接活，由报告句柄远程重试。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)、[BatchJob](chronaxis.batch.models.md#api-BatchJob)、[BatchJobResult](chronaxis.batch.models.md#api-BatchJobResult)、[CleanupHandle](chronaxis.batch.models.md#api-CleanupHandle)、[threading.Event](https://docs.python.org/3.12/library/threading.html#event-objects)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[ProcessTree](chronaxis.batch.process_tree.md#api-ProcessTree)

## 对象导航

|对象|用途|
|---|---|
|[`job_packet`](#api-job_packet)|提取无活动资源的计划。|
|[`restore_job`](#api-restore_job)|恢复独立计划。|
|[`worker_main`](#api-worker_main)|处理run/cleanup/close命令。|
|[`ProcessWorker`](#api-ProcessWorker)|保存一个可复用工作进程、私有管道及其后代的清理责任。|
|[`ProcessWorker.__init__`](#api-ProcessWorker-__init__)|启动等待命令的spawn进程。|
|[`ProcessWorker.submit`](#api-ProcessWorker-submit)|发送独立任务。|
|[`ProcessWorker.ready`](#api-ProcessWorker-ready)|查询结果或异常退出。|
|[`ProcessWorker.receive`](#api-ProcessWorker-receive)|取结果并挂远程恢复句柄。|
|[`ProcessWorker.close`](#api-ProcessWorker-close)|重试远程清理后关闭进程树。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import replace
from pathlib import Path
from threading import Event
from ..planning.plan import AnalysisPlan
from ..planning.checks import json_value
from .models import BatchJob, BatchJobResult, CleanupHandle
from .process_tree import ProcessTree
```

</details>

<a id="api-job_packet"></a>
## `job_packet`

提取无活动资源的计划。

```python
job_packet(job)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`job`|[BatchJob](chronaxis.batch.models.md#api-BatchJob)|是|无|位置或关键字。本次独立任务；提取路径或原生配置快照，不传递运行资源。|

### 返回说明

原生dict。

### 异常说明

配置转换错误。

源码：[`src/chronaxis/batch/process_transport.py:20`](../../../src/chronaxis/batch/process_transport.py#L20)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-restore_job"></a>
## `restore_job`

恢复独立计划。

```python
restore_job(packet)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`packet`|dict|是|无|位置或关键字。本批由job_packet产生的声明；路径模式保延迟加载，内存模式重建后核对identity。|

### 返回说明

BatchJob。

### 异常说明

重建或身份不一致。

源码：[`src/chronaxis/batch/process_transport.py:28`](../../../src/chronaxis/batch/process_transport.py#L28)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-worker_main"></a>
## `worker_main`

处理run/cleanup/close命令。

```python
worker_main(connection)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`connection`|multiprocessing.connection.PipeConnection|是|无|位置或关键字。本次spawn建立的私有双向Windows管道，只接受所属主进程发送的run、cleanup和close命令。|

### 返回说明

None。

### 异常说明

断管退出，父进程负责树清理。

源码：[`src/chronaxis/batch/process_transport.py:38`](../../../src/chronaxis/batch/process_transport.py#L38)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ProcessWorker"></a>
## `ProcessWorker`

保存一个可复用工作进程、私有管道及其后代的清理责任。

```python
ProcessWorker()
```


源码：[`src/chronaxis/batch/process_transport.py:81`](../../../src/chronaxis/batch/process_transport.py#L81)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ProcessWorker-__init__"></a>
### `ProcessWorker.__init__`

启动等待命令的spawn进程。

```python
ProcessWorker.__init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

新对象。

#### 异常说明

启动/树登记失败立即回收。

源码：[`src/chronaxis/batch/process_transport.py:84`](../../../src/chronaxis/batch/process_transport.py#L84)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ProcessWorker-submit"></a>
### `ProcessWorker.submit`

发送独立任务。

```python
ProcessWorker.submit(job, directory, backend)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`job`|[BatchJob](chronaxis.batch.models.md#api-BatchJob)|是|无|位置或关键字。本次待运行的独立任务；发送其路径或不可变配置快照，不传递活跃文件或结果对象。|
|`directory`|[pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。该任务独占的输出根目录，不能复用其他任务目录。|
|`backend`|str &#124; None|是|无|位置或关键字。本批可选计算实现覆盖：None沿用任务配置，reference或numpy使用对应实现。|

#### 返回说明

None。

#### 异常说明

转换或通信错误。

源码：[`src/chronaxis/batch/process_transport.py:106`](../../../src/chronaxis/batch/process_transport.py#L106)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ProcessWorker-ready"></a>
### `ProcessWorker.ready`

查询结果或异常退出。

```python
ProcessWorker.ready()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

bool。

#### 异常说明

原管道错误。

源码：[`src/chronaxis/batch/process_transport.py:110`](../../../src/chronaxis/batch/process_transport.py#L110)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ProcessWorker-receive"></a>
### `ProcessWorker.receive`

取结果并挂远程恢复句柄。

```python
ProcessWorker.receive()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

BatchJobResult。

#### 异常说明

进程死亡或协议错误。

源码：[`src/chronaxis/batch/process_transport.py:117`](../../../src/chronaxis/batch/process_transport.py#L117)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ProcessWorker-close"></a>
### `ProcessWorker.close`

重试远程清理后关闭进程树。

```python
ProcessWorker.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

清理失败保留全部所有者。

源码：[`src/chronaxis/batch/process_transport.py:129`](../../../src/chronaxis/batch/process_transport.py#L129)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
