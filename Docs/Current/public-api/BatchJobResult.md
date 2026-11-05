# chronaxis.BatchJobResult

使用`from chronaxis import BatchJobResult`导入。本页只列直接公开成员与必要的构造/上下文协议；内部实现见[模块参考](../reference/chronaxis.batch.models.md)。

返回[公开API索引](../api.md)。参数表中的类型可跳转到定义；先核对必填、默认值与返回/异常说明。

## 成员导航

- [`BatchJobResult`](#api-BatchJobResult)
- [`BatchJobResult.to_dict`](#api-BatchJobResult-to_dict)

<a id="api-BatchJobResult"></a>
## `BatchJobResult`

保存一个任务的最终状态；发布后关闭失败仍为failed，并保留已发布路径。

```python
BatchJobResult(job_id: str, status: str, plan_path: str | None = None, plan_identity: str | None = None, dataset_id: str | None = None, entity_id: str | None = None, session_id: str | None = None, input_identity: str | None = None, run_id: str | None = None, output_dir: pathlib.Path | None = None, manifest_path: pathlib.Path | None = None, error_type: str | None = None, error_message: str | None = None, error_chain: tuple[str, ...] = (), elapsed_seconds: float = 0.0, memory_budget_bytes: int | None = None, worker_pid: int | None = None, recovery: chronaxis.batch.models.CleanupHandle | None = None) -> None
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
|`manifest_path`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) &#124; None|否|None|本任务实际发布的带时间后缀完成清单路径；尚未发布为None。按清单outputs定位本次表，不猜固定文件名。|
|`error_type`|str &#124; None|否|None|失败异常类名或未启动取消标识not_started；正常完成时为None。结合status和error_chain查看。|
|`error_message`|str &#124; None|否|None|失败或取消的具体说明；正常完成时为None。异常cause与清理说明保存在error_chain。|
|`error_chain`|tuple[str, ...]|否|()|cause链和清理notes，保留错误来源。|
|`elapsed_seconds`|float|否|0.0|单任务墙钟秒，含发布及关闭，不宣称CPU耗时。|
|`memory_budget_bytes`|int &#124; None|否|None|已取得计划的新分析层预算，单位字节；文件计划尚未加载/加载失败时为None，不表示0字节。|
|`worker_pid`|int &#124; None|否|None|实际执行此任务的分析工作进程PID；未启动的任务为None。复用同一进程的任务可具有相同PID。|
|`recovery`|[CleanupHandle](../reference/chronaxis.batch.models.md#api-CleanupHandle) &#124; None|否|None|关闭失败后保留的CleanupHandle；调用close()重试释放资源，正常关闭时为None；不写入JSON。|

源码：[`src/chronaxis/batch/models.py:136`](../../../src/chronaxis/batch/models.py#L136)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

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

源码：[`src/chronaxis/batch/models.py:165`](../../../src/chronaxis/batch/models.py#L165)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
