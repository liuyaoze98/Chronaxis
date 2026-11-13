# `chronaxis.fast.cli`

fast单会话及独立批量命令的JSON响应；静态命令不读取报文文件。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)

## 对象导航

|对象|用途|
|---|---|
|[`execute`](#api-execute)|参数为 CLI 已解析的配置路径和动作。成功返回 0，配置或执行失败返回非零。|
|[`_batch`](#api-_batch)|执行一份独立文件清单。CLI 保留实际报告位置，失败和取消返回非零。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .can_io import _prepare
from .config import compile_config
from .run import run_prepared
from ..planning.checks import PlanValidationError
```

</details>

<a id="api-execute"></a>
## `execute`

参数为 CLI 已解析的配置路径和动作。成功返回 0，配置或执行失败返回非零。

```python
execute(args)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`args`|argparse.Namespace|是|无|位置或关键字。命令行解析出的 fast 操作、配置路径、输出和总量选项。|

源码：[`src/chronaxis/fast/cli.py:12`](../../../src/chronaxis/fast/cli.py#L12)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_batch"></a>
## `_batch`

执行一份独立文件清单。CLI 保留实际报告位置，失败和取消返回非零。

```python
_batch(args)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`args`|argparse.Namespace|是|无|位置或关键字。命令行解析出的 fast 操作、配置路径、输出和总量选项。|

源码：[`src/chronaxis/fast/cli.py:54`](../../../src/chronaxis/fast/cli.py#L54)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
