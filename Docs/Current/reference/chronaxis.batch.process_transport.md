# `chronaxis.batch.process_transport`

传递独立计划快照和小型结果，保留工作进程中的失败清理责任。

管道仅连接本次创建的可信子进程，不读取外部序列化对象。计划重建后核对身份，
大型结果在子进程内写出并关闭。清理失败的进程暂停接活，由报告句柄远程重试。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)、[BatchJob](chronaxis.batch.models.md#api-BatchJob)、[BatchJobResult](chronaxis.batch.models.md#api-BatchJobResult)、[CleanupHandle](chronaxis.batch.models.md#api-CleanupHandle)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[ProcessTree](chronaxis.batch.process_tree.md#api-ProcessTree)

## 对象导航

|对象|用途|
|---|---|
|[`job_packet`](#api-job_packet)|提取无活动资源的计划。|
|[`restore_job`](#api-restore_job)|恢复独立计划。|
|[`ProcessWorker`](#api-ProcessWorker)|保存一个可复用工作进程、私有管道及其后代的清理责任。|
|[`ProcessWorker.__init__`](#api-ProcessWorker-__init__)|启动等待命令的spawn进程。|
|[`ProcessWorker.submit`](#api-ProcessWorker-submit)|发送独立任务。|
|[`ProcessWorker.submit_fast`](#api-ProcessWorker-submit_fast)|只传准备完成的文件参数，工作进程不重新解析模板或建立下层进程。|
|[`ProcessWorker.cancel_fast`](#api-ProcessWorker-cancel_fast)|通知在途文件，协作退出超过五秒才结束本次拥有的进程树。返回是否已强制回收。|
|[`ProcessWorker.ready`](#api-ProcessWorker-ready)|查询结果或异常退出。|
|[`ProcessWorker.receive`](#api-ProcessWorker-receive)|取结果并挂远程恢复句柄。|
|[`ProcessWorker.close`](#api-ProcessWorker-close)|停止本次工作进程并释放其作业、管道和进程句柄；再次调用时从尚未完成的阶段继续。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import replace
from pathlib import Path
from time import monotonic
from ..planning.plan import AnalysisPlan
from ..planning.checks import json_value
from .models import BatchJob, BatchJobResult, CleanupHandle
from .process_tree import ProcessTree
from .._batch_worker import worker_main
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

源码：[`src/chronaxis/batch/process_transport.py:19`](../../../src/chronaxis/batch/process_transport.py#L19)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

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

源码：[`src/chronaxis/batch/process_transport.py:27`](../../../src/chronaxis/batch/process_transport.py#L27)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ProcessWorker"></a>
## `ProcessWorker`

保存一个可复用工作进程、私有管道及其后代的清理责任。

```python
ProcessWorker(*, fast=False)
```


源码：[`src/chronaxis/batch/process_transport.py:37`](../../../src/chronaxis/batch/process_transport.py#L37)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ProcessWorker-__init__"></a>
### `ProcessWorker.__init__`

启动等待命令的spawn进程。

```python
ProcessWorker.__init__(*, fast=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`fast`|bool|否|False|仅关键字。启用 fast 的共享取消信号和文件级任务协议。|

#### 返回说明

新对象。

#### 异常说明

启动/树登记失败立即回收。

源码：[`src/chronaxis/batch/process_transport.py:40`](../../../src/chronaxis/batch/process_transport.py#L40)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

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

源码：[`src/chronaxis/batch/process_transport.py:68`](../../../src/chronaxis/batch/process_transport.py#L68)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ProcessWorker-submit_fast"></a>
### `ProcessWorker.submit_fast`

只传准备完成的文件参数，工作进程不重新解析模板或建立下层进程。

```python
ProcessWorker.submit_fast(job, directory, spec, total)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`job`|[BatchJob](chronaxis.batch.models.md#api-BatchJob)|是|无|位置或关键字。待派发的独立文件任务，其名称进入报告。|
|`directory`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。给本次任务独占的结果目录。|
|`spec`|dict|是|无|位置或关键字。一个文件的已绑定参数，包括 DBC、通道、数值公式和输出单位。|
|`total`|bool|是|无|位置或关键字。是否回传未舍入指标，供同一模板的成员按输入顺序相加。|

源码：[`src/chronaxis/batch/process_transport.py:72`](../../../src/chronaxis/batch/process_transport.py#L72)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ProcessWorker-cancel_fast"></a>
### `ProcessWorker.cancel_fast`

通知在途文件，协作退出超过五秒才结束本次拥有的进程树。返回是否已强制回收。

```python
ProcessWorker.cancel_fast()
```

参数：无显式参数。


源码：[`src/chronaxis/batch/process_transport.py:78`](../../../src/chronaxis/batch/process_transport.py#L78)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

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

管道探测或进程状态检查发生 EOFError 或 OSError 时抛出 ChildProcessError，携带工作进程 PID 并保留原异常。探测时确认 EOF 或断管后，关闭阶段跳过远程握手。

源码：[`src/chronaxis/batch/process_transport.py:89`](../../../src/chronaxis/batch/process_transport.py#L89)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

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

探测不到结果，或探测、读取遇到 EOF 或断管时，抛出带工作进程 PID 的 ChildProcessError。已收到的消息仍按正常协议校验，类型或种类不符报 RuntimeError，解包失败原样传播。

源码：[`src/chronaxis/batch/process_transport.py:98`](../../../src/chronaxis/batch/process_transport.py#L98)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ProcessWorker-close"></a>
### `ProcessWorker.close`

停止本次工作进程并释放其作业、管道和进程句柄；再次调用时从尚未完成的阶段继续。

```python
ProcessWorker.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

远程答复清理失败时抛 RuntimeError，仍可重试。断管后等待超过五秒且进程仍在运行时抛 TimeoutError。作业、管道或进程句柄关闭失败时原异常传播；此前已完成的停止步骤保留。

#### 处理流程说明

管道可用时，先让工作进程重试待办清理，再发送关闭命令并等待退出。已知断管或关闭握手时遇到 EOF、断管，则先关闭本次作业对象以结束其工作进程及后代。没有作业对象时，只终止该拥有者持有的工作进程。断管后的每次退出等待最多五秒。进程退出后关闭剩余句柄。

源码：[`src/chronaxis/batch/process_transport.py:119`](../../../src/chronaxis/batch/process_transport.py#L119)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
