# chronaxis.batch.models

定义批量任务及其报告。BatchJob说明一个任务用哪份计划，BatchPlan说明同时运行几个任务，BatchJobResult记录单个任务结果，BatchReport按原任务顺序汇总。每个任务的数值结果仍保存在自己的目录。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)

## 对象导航

|对象|用途|
|---|---|
|[`Closable`](#api-Closable)|表示已经存在、由调用者负责关闭的资源，不创建占位执行对象。|
|[`Closable.close`](#api-Closable-close)|关闭资源。|
|[`CleanupHandle`](#api-CleanupHandle)|只持有未关闭的最高所有者；关闭成功后撤销引用，重复关闭无副作用。|
|[`CleanupHandle.__init__`](#api-CleanupHandle-__init__)|接管真实恢复对象。|
|[`CleanupHandle.closed`](#api-CleanupHandle-closed)|读取恢复是否完成。|
|[`CleanupHandle.close`](#api-CleanupHandle-close)|重试关闭，不在失败时丢所有者。|
|[`BatchJob`](#api-BatchJob)|声明一个独立分析；同会话连续文件应包含在本任务的一个计划中。|
|[`BatchJob.__post_init__`](#api-BatchJob-__post_init__)|检查声明而不读文件。|
|[`BatchPlan`](#api-BatchPlan)|保存批量配置；只关联独立计划路径，不能把一个会话拆成多个时间任务。|
|[`BatchPlan.__post_init__`](#api-BatchPlan-__post_init__)|检查冻结声明。|
|[`BatchPlan.from_dict`](#api-BatchPlan-from_dict)|检查批量配置；jobs只关联路径，template读取模板并展开文件集合。|
|[`BatchJobResult`](#api-BatchJobResult)|保存一个任务的最终状态；发布后关闭失败仍为failed，并保留已发布路径。|
|[`BatchJobResult.__post_init__`](#api-BatchJobResult-__post_init__)|拒绝伪成功状态。|
|[`BatchJobResult.to_dict`](#api-BatchJobResult-to_dict)|把本任务的状态、结果目录和错误信息转换为可写入报告的字典。|
|[`BatchReport`](#api-BatchReport)|按原任务顺序汇总结果；每个任务数值表仍在各自目录，不跨口径归约。|
|[`BatchReport.status`](#api-BatchReport-status)|汇总失败优先状态。|
|[`BatchReport.to_dict`](#api-BatchReport-to_dict)|输出身份和计数。|
|[`BatchReport.close`](#api-BatchReport-close)|重试所有未完清理。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from ..core.validation import require_identifier
from ..planning.plan import AnalysisPlan
```

</details>

<a id="api-Closable"></a>
## `Closable`

表示已经存在、由调用者负责关闭的资源，不创建占位执行对象。

```python
class Closable(Protocol)
```

继承关系：Protocol。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/batch/models.py:16`](../../../src/chronaxis/batch/models.py#L16)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-Closable-close"></a>
### `Closable.close`

关闭资源。

```python
Closable.close() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原关闭错误，可恢复后重试。

返回类型：None。

源码：[`src/chronaxis/batch/models.py:19`](../../../src/chronaxis/batch/models.py#L19)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-CleanupHandle"></a>
## `CleanupHandle`

只持有未关闭的最高所有者；关闭成功后撤销引用，重复关闭无副作用。

```python
CleanupHandle(owner: Closable)
```


源码：[`src/chronaxis/batch/models.py:24`](../../../src/chronaxis/batch/models.py#L24)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-CleanupHandle-__init__"></a>
### `CleanupHandle.__init__`

接管真实恢复对象。

```python
CleanupHandle.__init__(owner: Closable)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|[Closable](chronaxis.batch.models.md#api-Closable)|是|无|位置或关键字。owner有close方法。|

#### 返回说明

新句柄。

#### 异常说明

无。

源码：[`src/chronaxis/batch/models.py:27`](../../../src/chronaxis/batch/models.py#L27)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-CleanupHandle-closed"></a>
### `CleanupHandle.closed`

读取恢复是否完成。

```python
CleanupHandle.closed: bool
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

返回类型：bool。

源码：[`src/chronaxis/batch/models.py:32`](../../../src/chronaxis/batch/models.py#L32)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-CleanupHandle-close"></a>
### `CleanupHandle.close`

重试关闭，不在失败时丢所有者。

```python
CleanupHandle.close() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原关闭错误。

返回类型：None。

源码：[`src/chronaxis/batch/models.py:36`](../../../src/chronaxis/batch/models.py#L36)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BatchJob"></a>
## `BatchJob`

声明一个独立分析；同会话连续文件应包含在本任务的一个计划中。

```python
BatchJob(job_id: str, plan: chronaxis.planning.plan.AnalysisPlan | pathlib.Path) -> None
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`job_id`|str|是|无|设置批量内唯一任务名称，例如test_a；用于结果目录及报告定位，不能与其他任务仅大小写不同。|
|`plan`|[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan) &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|提供待运行的AnalysisPlan或pathlib.Path，例如Path("analysis.yaml")；直接构造BatchJob时不能传裸字符串。路径在任务真正启动时加载。|

源码：[`src/chronaxis/batch/models.py:44`](../../../src/chronaxis/batch/models.py#L44)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BatchJob-__post_init__"></a>
### `BatchJob.__post_init__`

检查声明而不读文件。

```python
BatchJob.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

名称或计划类型错误。

本函数直接报告的具体错误：

- `TypeError`：BatchJob.plan需要AnalysisPlan或Path。

源码：[`src/chronaxis/batch/models.py:50`](../../../src/chronaxis/batch/models.py#L50)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BatchPlan"></a>
## `BatchPlan`

保存批量配置；只关联独立计划路径，不能把一个会话拆成多个时间任务。

```python
BatchPlan(jobs: tuple[chronaxis.batch.models.BatchJob, ...], process_count: int = 1, fail_fast: bool = False, backend: str | None = None) -> None
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`jobs`|tuple[[BatchJob](chronaxis.batch.models.md#api-BatchJob), ...]|是|无|提供BatchJob元组，例如(BatchJob("a", Path("a.yaml")),)；也可通过load_batch_plan读取YAML取得。元组顺序就是最终报告顺序。|
|`process_count`|int|否|1|控制最多启动几个分析工作进程。填正整数，例如4；默认1。任务少于该值时按任务数启动，空批次不启动。此数量不包含调度主进程和CAN读取子进程。|
|`fail_fast`|bool|否|False|控制某任务失败后的调度：False继续其他独立任务；True停止提交新任务，已运行任务按批量执行器的取消流程收尾。|
|`backend`|str &#124; None|否|None|`"reference"`使用独立参考计算，`"numpy"`使用NumPy数组计算。None沿用计划的设置。|

源码：[`src/chronaxis/batch/models.py:58`](../../../src/chronaxis/batch/models.py#L58)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BatchPlan-__post_init__"></a>
### `BatchPlan.__post_init__`

检查冻结声明。

```python
BatchPlan.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

类型、范围或重复任务错误；无I/O。

本函数直接报告的具体错误：

- `TypeError`：jobs需要BatchJob tuple。
- `ValueError`：批量job_id不能重复或仅大小写不同。
- `ValueError`：process_count需要正原生int。
- `TypeError`：fail_fast需要bool。
- `ValueError`：backend需要reference、numpy或null。

源码：[`src/chronaxis/batch/models.py:66`](../../../src/chronaxis/batch/models.py#L66)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BatchPlan-from_dict"></a>
### `BatchPlan.from_dict`

检查批量配置；jobs只关联路径，template读取模板并展开文件集合。

```python
BatchPlan.from_dict(config, *, base_dir=None)
```

装饰器：`classmethod`。

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`config`|dict[str, object]|是|无|位置或关键字。批量配置：batch_version=1；jobs与template+inputs二选一。jobs每项plan必填，name省略按位置生成job_N；template有多来源时用source明确目标。可选process_count、fail_fast、backend。见[独立批量任务](../batch.md)。|
|`base_dir`|str &#124; [pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) &#124; None|否|None|仅关键字。解析计划中相对路径所用的目录；None表示使用当前工作目录。|

#### 返回说明

冻结BatchPlan。

#### 异常说明

PlanValidationError定位非法字段、重名、缺少模板输入或来源歧义。jobs可为空；jobs只保留计划路径，template会读取模板、展开文件集合并按需读取DBC元数据，不扫描业务报文。

源码：[`src/chronaxis/batch/models.py:80`](../../../src/chronaxis/batch/models.py#L80)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BatchJobResult"></a>
## `BatchJobResult`

保存一个任务的最终状态；发布后关闭失败仍为failed，并保留已发布路径。

```python
BatchJobResult(job_id: str, status: str, plan_path: str | None = None, plan_identity: str | None = None, dataset_id: str | None = None, entity_id: str | None = None, session_id: str | None = None, input_identity: str | None = None, run_id: str | None = None, output_dir: pathlib.Path | None = None, error_type: str | None = None, error_message: str | None = None, error_chain: tuple[str, ...] = (), elapsed_seconds: float = 0.0, memory_budget_bytes: int | None = None, worker_pid: int | None = None, recovery: chronaxis.batch.models.CleanupHandle | None = None) -> None
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`job_id`|str|是|无|原任务身份。|
|`status`|str|是|无|`completed`：分析、结果发布和资源关闭均成功；`failed`：任一步骤失败，查看error_type/error_message等诊断；`cancelled`：取消或fail_fast使该任务没有继续执行。失败与取消不是同一状态。|
|`plan_path`|str &#124; None|否|None|原任务使用文件路径时保存其绝对路径；直接传AnalysisPlan的正常任务为None。|
|`plan_identity`|str &#124; None|否|None|已取得计划的声明身份；文件计划未加载或加载失败时为None，不能当作输入文件内容摘要。|
|`dataset_id`|str &#124; None|否|None|已取得计划的dataset.name；未加载或加载失败时为None。结果属性仍名为dataset_id。|
|`entity_id`|str &#124; None|否|None|已取得计划的对象标识：取可选dataset.entity，省略则沿用dataset.name；未加载或加载失败时为None。|
|`session_id`|str &#124; None|否|None|已取得计划的会话标识：取可选dataset.session，省略则沿用dataset.name；未加载或加载失败时为None。|
|`input_identity`|str &#124; None|否|None|AnalysisRunner返回的输入摘要身份；没有返回结果或未请求该摘要时为None，正常运行也可能为None。|
|`run_id`|str &#124; None|否|None|AnalysisRunner已返回结果时记录运行ID；尚未返回结果就失败或取消时为None。|
|`output_dir`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) &#124; None|否|None|发布成功后记录的正式目录；尚未发布成功为None。发布后关闭失败仍保留该路径，任务状态为failed。|
|`error_type`|str &#124; None|否|None|失败异常类名或未启动取消标识not_started；正常完成时为None。结合status和error_chain查看。|
|`error_message`|str &#124; None|否|None|失败或取消的具体说明；正常完成时为None。异常cause与清理说明保存在error_chain。|
|`error_chain`|tuple[str, ...]|否|()|cause链和清理notes，保留错误来源。|
|`elapsed_seconds`|float|否|0.0|单任务墙钟秒，含发布及关闭，不宣称CPU耗时。|
|`memory_budget_bytes`|int &#124; None|否|None|已取得计划的新分析层预算，单位字节；文件计划尚未加载/加载失败时为None，不表示0字节。|
|`worker_pid`|int &#124; None|否|None|实际执行此任务的分析工作进程PID；未启动的任务为None。复用同一进程的任务可具有相同PID。|
|`recovery`|[CleanupHandle](chronaxis.batch.models.md#api-CleanupHandle) &#124; None|否|None|关闭失败后保留的CleanupHandle；调用close()重试释放资源，正常关闭时为None；不写入JSON。|

源码：[`src/chronaxis/batch/models.py:119`](../../../src/chronaxis/batch/models.py#L119)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BatchJobResult-__post_init__"></a>
### `BatchJobResult.__post_init__`

拒绝伪成功状态。

```python
BatchJobResult.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

非法状态或成功缺少事实。

本函数直接报告的具体错误：

- `ValueError`：批量任务状态无效。
- `ValueError`：completed需要实际发布目录及运行身份。

源码：[`src/chronaxis/batch/models.py:140`](../../../src/chronaxis/batch/models.py#L140)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BatchJobResult-to_dict"></a>
### `BatchJobResult.to_dict`

把本任务的状态、结果目录和错误信息转换为可写入报告的字典。

```python
BatchJobResult.to_dict() -> dict
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

JSON对象。

#### 异常说明

无；不序列化资源对象。

返回类型：dict。

源码：[`src/chronaxis/batch/models.py:147`](../../../src/chronaxis/batch/models.py#L147)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BatchReport"></a>
## `BatchReport`

按原任务顺序汇总结果；每个任务数值表仍在各自目录，不跨口径归约。

```python
BatchReport(output_dir: pathlib.Path, jobs: tuple[chronaxis.batch.models.BatchJobResult, ...], process_count: int, fail_fast: bool, cancel_requested: bool, device_label: str, worker_process_count: int = 0, infrastructure_error: str | None = None) -> None
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`output_dir`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|本批新目录，已有目标不会被覆盖。|
|`jobs`|tuple[[BatchJobResult](chronaxis.batch.models.md#api-BatchJobResult), ...]|是|无|最终结果顺序不受工作进程完成先后影响。|
|`process_count`|int|是|无|控制最多启动几个分析工作进程。填正整数，例如4；默认1。任务少于该值时按任务数启动，空批次不启动。此数量不包含调度主进程和CAN读取子进程。|
|`fail_fast`|bool|是|无|是否在观察到失败后停止派发。|
|`cancel_requested`|bool|是|无|用户取消或KeyboardInterrupt是否曾被观察到。|
|`device_label`|str|是|无|标记本次批量报告的来源设备。直接构造BatchReport时必填非空文本；run_batch或BatchRunner.run的device_label参数省略时才采用pending。不会覆盖子分析metadata.device_label。|
|`worker_process_count`|int|否|0|本次实际启动的分析工作进程数量；可能少于process_count，空批次或开始前取消时为0。不包含CAN读取子进程。|
|`infrastructure_error`|str &#124; None|否|None|调度/汇总基础设施异常的说明；None表示未记录这类错误，不代表每个任务成功。任务错误查看jobs中的status、error_type、error_message及error_chain。|

源码：[`src/chronaxis/batch/models.py:160`](../../../src/chronaxis/batch/models.py#L160)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BatchReport-status"></a>
### `BatchReport.status`

汇总失败优先状态。

```python
BatchReport.status: str
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

failed/cancelled/completed。

#### 异常说明

无。

返回类型：str。

源码：[`src/chronaxis/batch/models.py:173`](../../../src/chronaxis/batch/models.py#L173)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BatchReport-to_dict"></a>
### `BatchReport.to_dict`

输出身份和计数。

```python
BatchReport.to_dict() -> dict
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

JSON对象。

#### 异常说明

无。不合并指标值。

返回类型：dict。

源码：[`src/chronaxis/batch/models.py:179`](../../../src/chronaxis/batch/models.py#L179)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BatchReport-close"></a>
### `BatchReport.close`

重试所有未完清理。

```python
BatchReport.close() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

首个关闭错误，其他项仍尝试。

返回类型：None。

源码：[`src/chronaxis/batch/models.py:190`](../../../src/chronaxis/batch/models.py#L190)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
