# chronaxis.BatchJob

使用`from chronaxis import BatchJob`导入。本页只列直接公开成员与必要的构造/上下文协议；内部实现见[模块参考](../reference/chronaxis.batch.models.md)。

返回[公开API索引](../api.md)。参数表中的类型可跳转到定义；先核对必填、默认值与返回/异常说明。

## 成员导航

- [`BatchJob`](#api-BatchJob)

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
|`plan`|[AnalysisPlan](AnalysisPlan.md#api-AnalysisPlan) &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|提供待运行的AnalysisPlan或pathlib.Path，例如Path("analysis.yaml")；直接构造BatchJob时不能传裸字符串。路径在任务真正启动时加载。|

源码：[`src/chronaxis/batch/models.py:44`](../../../src/chronaxis/batch/models.py#L44)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
