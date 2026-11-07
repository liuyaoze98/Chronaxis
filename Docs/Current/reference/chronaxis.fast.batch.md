# `chronaxis.fast.batch`

先检查整批 fast 配置，再交给文件级工作进程；结果按声明顺序发布。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[BatchPlan](chronaxis.batch.models.md#api-BatchPlan)、[BatchRunner](chronaxis.batch.runner.md#api-BatchRunner)、[ConfigurationError](chronaxis.configuration.models.md#api-ConfigurationError)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)

## 对象导航

|对象|用途|
|---|---|
|[`prepare_batch`](#api-prepare_batch)|返回批量计划、按输入顺序的可序列化文件参数及模板标识。此时不读报文。|
|[`run_batch`](#api-run_batch)|运行独立 fast jobs/template 配置，返回本次带时间的批量报告路径。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import replace
from pathlib import Path
from ..batch.models import BatchPlan
from ..batch.publication import _write_batch_report
from ..batch.runner import BatchRunner
from ..configuration import ConfigurationError, load_configuration
from ..configuration.diagnostics import locate_error
from ..planning.checks import PlanValidationError, configuration_error
from ..planning.dbc_defaults import scoped_dbc_cache
from .config import compile_config
from .worker import _dbc_digest
```

</details>

<a id="api-prepare_batch"></a>
## `prepare_batch`

返回批量计划、按输入顺序的可序列化文件参数及模板标识。此时不读报文。

```python
prepare_batch(plan_path)
```

装饰器：`scoped_dbc_cache()`。

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan_path`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。声明 jobs 或 template 的批量 YAML/JSON 路径。|

源码：[`src/chronaxis/fast/batch.py:18`](../../../src/chronaxis/fast/batch.py#L18)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-run_batch"></a>
## `run_batch`

运行独立 fast jobs/template 配置，返回本次带时间的批量报告路径。

失败或取消任务的报告仍可打开。基础设施异常保留 batch_report 以供检查或重试清理。
process_count 省略时使用批量计划配置，total 只接收显式布尔值。

```python
run_batch(plan_path, output, *, process_count=None, cancel_event=None, total=False)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan_path`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。声明 jobs 或 template 的批量 YAML/JSON 路径。|
|`output`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。接收本次结果表和完成清单的目录。|
|`process_count`|int &#124; None|否|None|仅关键字。限制同时工作的文件进程数，省略时采用批量配置。|
|`cancel_event`|Event &#124; None|否|None|仅关键字。已设置时取消本次操作，省略时按调用方的正常生命周期运行。|
|`total`|bool|否|False|仅关键字。是否回传未舍入指标，供同一模板的成员按输入顺序相加。|

源码：[`src/chronaxis/fast/batch.py:51`](../../../src/chronaxis/fast/batch.py#L51)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
