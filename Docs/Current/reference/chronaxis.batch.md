# chronaxis.batch

公开独立批量任务模型和调度器，不自动创建进程或读取输入。

每个BatchJob调用同一公共AnalysisRunner，输出单独发布，BatchReport只汇总状态和身份。
调用者可设置process_count工作进程数、fail_fast和取消Event；在途任务完成关闭后才返回。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[BatchJob](chronaxis.batch.models.md#api-BatchJob)、[BatchJobResult](chronaxis.batch.models.md#api-BatchJobResult)、[BatchPlan](chronaxis.batch.models.md#api-BatchPlan)、[BatchReport](chronaxis.batch.models.md#api-BatchReport)、[BatchRunner](chronaxis.batch.runner.md#api-BatchRunner)

## 对象导航

|对象|用途|
|---|---|

## 导出名称

`BatchJob`, `BatchJobResult`, `BatchReport`, `BatchRunner`, `BatchPlan`, `load_batch_plan`, `run_batch`, `write_batch_report`

重导出保持定义位置的签名；按上级[总索引](index.md)查找对象名。

公开重导出按[公开API索引](../api.md)查询定义、用途和调用示例。

<details><summary>导入与重导出来源（展开）</summary>

```python
from .models import BatchJob, BatchJobResult, BatchReport, BatchPlan
from .runner import BatchRunner
from .config import load_batch_plan
from .api import run_batch
from .publication import write_batch_report
```

</details>
