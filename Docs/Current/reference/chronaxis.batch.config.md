# `chronaxis.batch.config`

加载批量清单；显式jobs保存路径，template展开为每文件独立计划。

JSON/YAML重复键、非有限值和错误定位沿用共享配置语法规则；实际独立计划到
jobs在worker启动时加载；template在此时读取模板和必要DBC元数据，均不预读业务日志。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[BatchPlan](chronaxis.batch.models.md#api-BatchPlan)、[ConfigurationError](chronaxis.configuration.models.md#api-ConfigurationError)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)

## 对象导航

|对象|用途|
|---|---|
|[`load_batch_plan`](#api-load_batch_plan)|读取批量YAML或JSON文件，建立独立任务及其调度设置。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from pathlib import Path
from ..configuration import load_configuration, ConfigurationError
from ..configuration.diagnostics import locate_error
from ..planning.checks import PlanValidationError, configuration_error
from .models import BatchPlan
```

</details>

<a id="api-load_batch_plan"></a>
## `load_batch_plan`

读取批量YAML或JSON文件，建立独立任务及其调度设置。

```python
load_batch_plan(path: str | Path) -> BatchPlan
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。批量JSON/YAML路径；子计划、模板和inputs的路径以批量文件为基准。jobs在任务启动时加载，template在本调用中展开并编译各独立计划。|

### 返回说明

BatchPlan: 已检查批量结构的不可变计划；template已展开，jobs仍保存路径，均未读取业务输入。

### 异常说明

PlanValidationError表示路径、语法、批量字段或模板展开失败，按异常位置修正。jobs子计划错误在任务启动时记入报告；template编译错误在本调用返回前报告。

### 副作用说明

读取批量文件，template模式还读取模板与必要DBC、枚举输入集合；不创建输出目录。

返回类型：[BatchPlan](chronaxis.batch.models.md#api-BatchPlan)。

### 调用示例

```python
from chronaxis import load_batch_plan
# 先按批量指南准备batch.yaml和它引用的子计划。
plan = load_batch_plan("batch.yaml")
```

源码：[`src/chronaxis/batch/config.py:14`](../../../src/chronaxis/batch/config.py#L14)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
