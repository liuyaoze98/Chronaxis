# chronaxis.load_batch_plan

从`chronaxis`导入本对象。本页只列直接公开成员与必要的构造/上下文协议；内部实现见[模块参考](../reference/chronaxis.batch.config.md)。

返回[公开API索引](../api.md)。参数表中的类型可跳转到定义；先核对必填、默认值与返回/异常说明。

## 成员导航

- [load_batch_plan](#api-load_batch_plan)

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

返回类型：[BatchPlan](BatchPlan.md#api-BatchPlan)。

### 调用示例

```python
from chronaxis import load_batch_plan
# 先按批量指南准备batch.yaml和它引用的子计划。
plan = load_batch_plan("batch.yaml")
```

源码：[`src/chronaxis/batch/config.py:14`](../../../src/chronaxis/batch/config.py#L14)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
