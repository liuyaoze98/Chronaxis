# `chronaxis.batch.cli`

从严格批量配置调用公共API，打印精简计数并保留完整逐任务报告。

成功退出0、任一任务失败退出1、取消退出130；配置错误沿外层CLI退出2。
输出失败保已完成任务，原异常恢复报告在传播前尝试关闭，不清除诊断文件。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)

## 对象导航

|对象|用途|
|---|---|
|[`run_batch_cli`](#api-run_batch_cli)|执行真实批量入口。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import replace
from ..planning.checks import PlanValidationError
from ..results.spool import _cleanup_owner
from .api import run_batch
from .config import load_batch_plan
from .runner import _new_root
```

</details>

<a id="api-run_batch_cli"></a>
## `run_batch_cli`

执行真实批量入口。

```python
run_batch_cli(arguments) -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`arguments`|argparse.Namespace|是|无|位置或关键字。命令行解析后得到的参数对象；属性包括该命令的plan路径，以及output、backend、process_count等适用选项。字段由[CLI](../cli.md)生成，通常直接使用命令行入口。|

### 返回说明

0/1/130。

### 异常说明

外层CLI处理的原错或配置错。

本函数直接报告的具体错误：

- `PlanValidationError`：$.cli。

返回类型：int。

源码：[`src/chronaxis/batch/cli.py:18`](../../../src/chronaxis/batch/cli.py#L18)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
