# chronaxis.batch.runner

同时运行多份彼此独立的分析计划，最多启动process_count个任务。每个任务各用自己的状态、资源限额和目录。取消或fail_fast触发后不再启动新任务；已经启动的任务完成清理后退出。process_count限制任务数，并不限制整个Python进程的总内存。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)、[AnalysisRunner](chronaxis.runner.md#api-AnalysisRunner)、[BatchJob](chronaxis.batch.models.md#api-BatchJob)、[BatchJobResult](chronaxis.batch.models.md#api-BatchJobResult)、[BatchReport](chronaxis.batch.models.md#api-BatchReport)、[CleanupHandle](chronaxis.batch.models.md#api-CleanupHandle)、[threading.Event](https://docs.python.org/3.12/library/threading.html#event-objects)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)

## 对象导航

|对象|用途|
|---|---|
|[`_new_root`](#api-_new_root)|检查批量新目录。|
|[`_facts`](#api-_facts)|分别提取计划标识和实际输入标识，写入任务结果。|
|[`_diagnostics`](#api-_diagnostics)|保留有限异常链而不持有栈。|
|[`_cancelled`](#api-_cancelled)|记录未启动取消。|
|[`_report`](#api-_report)|补齐未启动项。|
|[`_run_job`](#api-_run_job)|执行一个独立任务并关闭所有资源。|
|[`_pause`](#api-_pause)|让出调度CPU等待下一次结果。|
|[`BatchRunner`](#api-BatchRunner)|通过有限spawn工作进程执行独立任务；同一任务的连续文件保持原顺序。|
|[`BatchRunner.__init__`](#api-BatchRunner-__init__)|配置调度。|
|[`BatchRunner.run`](#api-BatchRunner-run)|运行独立任务，原声明顺序返回报告。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import replace
from pathlib import Path
from threading import Event
from time import perf_counter
from ..planning import load_analysis_plan
from ..planning.plan import AnalysisPlan
from ..runner import AnalysisRunner
from ..results.spool import _cleanup_owner
from .models import BatchJob, BatchJobResult, BatchReport, CleanupHandle
```

</details>

<a id="api-_new_root"></a>
## `_new_root`

检查批量新目录。

```python
_new_root(value) -> Path
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|str &#124; [pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。本批任务的根输出目录，必须是尚不存在的新目录；创建后各任务在其中使用独立子目录。|

### 返回说明

绝对Path。

### 异常说明

类型/已有/只读路径错误。

本函数直接报告的具体错误：

- `TypeError`：批量输出需要str或Path。
- `ValueError`：批量输出不能位于RefProjects。

返回类型：[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)。

源码：[`src/chronaxis/batch/runner.py:23`](../../../src/chronaxis/batch/runner.py#L23)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_facts"></a>
## `_facts`

分别提取计划标识和实际输入标识，写入任务结果。

```python
_facts(job, plan=None) -> dict
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`job`|[BatchJob](chronaxis.batch.models.md#api-BatchJob)|是|无|位置或关键字。当前批量任务声明，包含job_id、plan路径及所用实现。|
|`plan`|[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan) &#124; None|否|None|位置或关键字。已成功加载的分析计划；加载失败或任务尚未启动时为None。|

### 返回说明

字段dict。

### 异常说明

无。

返回类型：dict。

源码：[`src/chronaxis/batch/runner.py:38`](../../../src/chronaxis/batch/runner.py#L38)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_diagnostics"></a>
## `_diagnostics`

保留有限异常链而不持有栈。

```python
_diagnostics(error) -> tuple[str, ...]
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`error`|BaseException|是|无|位置或关键字。本次操作产生的原异常对象；用于保留原因链、附加清理失败信息或继续抛出，不应换成一段字符串。|

### 返回说明

文本tuple。

### 异常说明

原异常格式错误。

返回类型：tuple[str, ...]。

源码：[`src/chronaxis/batch/runner.py:49`](../../../src/chronaxis/batch/runner.py#L49)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_cancelled"></a>
## `_cancelled`

记录未启动取消。

```python
_cancelled(job, reason) -> BatchJobResult
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`job`|[BatchJob](chronaxis.batch.models.md#api-BatchJob)|是|无|位置或关键字。需要标记为取消的任务声明，保留其原job_id与计划路径。|
|`reason`|str|是|无|位置或关键字。取消原因，写入该任务结果，便于区分主动取消和前序失败后停止。|

### 返回说明

取消结果。

### 异常说明

无，不读取计划。

返回类型：[BatchJobResult](chronaxis.batch.models.md#api-BatchJobResult)。

源码：[`src/chronaxis/batch/runner.py:60`](../../../src/chronaxis/batch/runner.py#L60)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_report"></a>
## `_report`

补齐未启动项。

```python
_report(root, jobs, results, process_count, fail_fast, cancelled, label, reason) -> BatchReport
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`root`|[pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。本批已经建立的根输出目录；批次清单在此发布。|
|`jobs`|[BatchJob](chronaxis.batch.models.md#api-BatchJob)|是|无|位置或关键字。按声明顺序排列的BatchJob序列。|
|`results`|list[[BatchJobResult](chronaxis.batch.models.md#api-BatchJobResult) &#124; None]|是|无|位置或关键字。与jobs按位置一一对应的结果列表；尚未启动的任务为None，汇总时补成取消结果。|
|`process_count`|int|是|无|位置或关键字。实际允许的最大并发任务数，正整数。|
|`fail_fast`|bool|是|无|位置或关键字。发生失败后是否停止启动新任务的布尔开关。|
|`cancelled`|bool|是|无|位置或关键字。本次调度是否已收到取消请求，决定批次汇总的取消状态。|
|`label`|str|是|无|位置或关键字。实际产出设备标签字符串，传入报告。|
|`reason`|str|是|无|位置或关键字。未启动任务的取消原因文字。|

### 返回说明

完整报告。

### 异常说明

模型错误。

返回类型：[BatchReport](chronaxis.batch.models.md#api-BatchReport)。

源码：[`src/chronaxis/batch/runner.py:65`](../../../src/chronaxis/batch/runner.py#L65)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_run_job"></a>
## `_run_job`

执行一个独立任务并关闭所有资源。

```python
_run_job(job, directory, backend, stop, cancel) -> BatchJobResult
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`job`|[BatchJob](chronaxis.batch.models.md#api-BatchJob)|是|无|位置或关键字。一个独立任务，含任务id和计划对象或计划文件路径。|
|`directory`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。本任务独占的新子目录；内部work存暂存，output存正式结果。|
|`backend`|str|是|无|位置或关键字。`"reference"`使用独立参考计算；`"numpy"`使用NumPy数组计算。须明确选择一种。|
|`stop`|[threading.Event](https://docs.python.org/3.12/library/threading.html#event-objects)|是|无|位置或关键字。批量调度器的停止标记；发现失败且启用fail_fast后设置，用于阻止启动后续任务。|
|`cancel`|[threading.Event](https://docs.python.org/3.12/library/threading.html#event-objects) &#124; None|是|无|位置或关键字。调用者提供的取消标记；为None表示未提供。它不强行终止已经运行的分析。|

### 返回说明

含实际发布和身份的最终结果；恢复失败保最高owner，不把异常栈留在结果中。

### 异常说明

普通分析/发布/取消转换成该任务结果；无法构造结果的内部错误交由调度器收尾。

返回类型：[BatchJobResult](chronaxis.batch.models.md#api-BatchJobResult)。

源码：[`src/chronaxis/batch/runner.py:74`](../../../src/chronaxis/batch/runner.py#L74)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_pause"></a>
## `_pause`

让出调度CPU等待下一次结果。

```python
_pause()
```

参数：无显式参数。


### 参数说明

无。

### 返回说明

None。

### 异常说明

主进程取消。

源码：[`src/chronaxis/batch/runner.py:118`](../../../src/chronaxis/batch/runner.py#L118)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BatchRunner"></a>
## `BatchRunner`

通过有限spawn工作进程执行独立任务；同一任务的连续文件保持原顺序。

```python
BatchRunner(process_count=1, *, fail_fast=False, backend=None)
```


源码：[`src/chronaxis/batch/runner.py:123`](../../../src/chronaxis/batch/runner.py#L123)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BatchRunner-__init__"></a>
### `BatchRunner.__init__`

配置调度。

```python
BatchRunner.__init__(process_count=1, *, fail_fast=False, backend=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`process_count`|int|否|1|位置或关键字。控制最多启动几个分析工作进程。填正整数，例如4；默认1。任务少于该值时按任务数启动，空批次不启动。此数量不包含调度主进程和CAN读取子进程。|
|`fail_fast`|bool|否|False|仅关键字。False时某任务失败仍继续尝试后续任务；True时发现失败后停止启动新任务，但等待已启动任务收尾。|
|`backend`|str &#124; None|否|None|仅关键字。`"reference"`使用独立参考计算；`"numpy"`使用NumPy数组计算。None沿用计划中的选择。|

#### 返回说明

None。初始化调度选项；调用BatchRunner(...)才创建并取得实例。此时不启动工作进程或读取输入。

#### 异常说明

类型、范围或计算后端无效。构造时不读取业务数据，也不启动工作进程。

本函数直接报告的具体错误：

- `ValueError`：process_count需要正原生int。
- `TypeError`：fail_fast需要bool。

源码：[`src/chronaxis/batch/runner.py:126`](../../../src/chronaxis/batch/runner.py#L126)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BatchRunner-run"></a>
### `BatchRunner.run`

运行独立任务，原声明顺序返回报告。

```python
BatchRunner.run(jobs, output_dir, *, cancel_event=None, device_label='pending') -> BatchReport
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`jobs`|tuple|是|无|位置或关键字。提供BatchJob元组，例如load_batch_plan("batch.yaml").jobs；每项含独立分析的ID与计划，顺序决定报告排列。|
|`output_dir`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。新批量结果目录，每个任务按id创建子目录；目标已经存在时拒绝覆盖。|
|`cancel_event`|[threading.Event](https://docs.python.org/3.12/library/threading.html#event-objects) &#124; None|否|None|仅关键字。可选取消标记；None表示没有。其他线程调用set()后停止派发新任务，正在执行的任务继续收尾。|
|`device_label`|str|否|'pending'|仅关键字。产出记录的设备标签，例如已核实的"home"或"work"；未确定时用"pending"。这是来源说明，不参与数值计算，也不根据文件路径猜测。|

#### 返回说明

BatchReport，close可重试子进程内失败清理。

#### 异常说明

声明/路径错误在创建工作进程前拒绝；工作进程调度器等基础设施错误收尾后传播。

本函数直接报告的具体错误：

- `TypeError`：批量任务需要BatchJob tuple。
- `ValueError`：批量job_id不能重复，大小写冲突也拒绝。
- `TypeError`：cancel_event需要threading.Event。
- `ValueError`：device_label需要非空文本。

#### 副作用说明

启动最多process_count个工作进程，每任务独立发布；取消只阻止未派发任务。

返回类型：[BatchReport](chronaxis.batch.models.md#api-BatchReport)。

源码：[`src/chronaxis/batch/runner.py:138`](../../../src/chronaxis/batch/runner.py#L138)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
