# chronaxis.batch.templates

把一个分析模板应用于明确输入集合，每个文件形成独立任务，不读取日志。

路径按模板目录解释；输入目录按批量配置目录解释。复用已有自然序和4096文件限制，
来源有多个候选时要求source，绝不把连续会话自动拆开。本入口由用户显式选择。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)

## 对象导航

|对象|用途|
|---|---|
|[`template_jobs`](#api-template_jobs)|参数为批量对象和路径基准；返回独立BatchJob列表。配置错误抛PlanValidationError，不写文件。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from copy import deepcopy
from pathlib import Path
from ..configuration import load_configuration
from ..configuration.imports import expand_document_imports
from ..planning.checks import PlanValidationError, text_at
from ..planning.input_paths import expand_source_files
```

</details>

<a id="api-template_jobs"></a>
## `template_jobs`

参数为批量对象和路径基准；返回独立BatchJob列表。配置错误抛PlanValidationError，不写文件。

```python
template_jobs(raw, base)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`raw`|dict|是|无|位置或关键字。当前批量模板声明，含template、inputs及可选source。|
|`base`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。批量配置所在目录；用于解释模板与输入集合的相对路径。|

源码：[`src/chronaxis/batch/templates.py:15`](../../../src/chronaxis/batch/templates.py#L15)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
