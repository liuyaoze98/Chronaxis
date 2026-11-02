# chronaxis.planning.input_defaults

补齐来源的常用声明，只有唯一候选时自动选择引用。

输入为已检查JSON结构的配置；输出独立字典或来源名称。不打开数据/DBC，
不改输入值和时间戳。相对时间缺省采用来源专属基准，不声称多来源已经同步。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)

## 对象导航

|对象|用途|
|---|---|
|[`source_defaults`](#api-source_defaults)|补来源名、ASC/BLF格式及时间默认值，不修改调用方字典。|
|[`source_reference`](#api-source_reference)|取显式来源名，或选择唯一适用来源；多候选不选第一项。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from pathlib import Path
from .checks import PlanValidationError, array_at, object_at, text_at
```

</details>

<a id="api-source_defaults"></a>
## `source_defaults`

补来源名、ASC/BLF格式及时间默认值，不修改调用方字典。

```python
source_defaults(raw, index, *, inferred_type=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`raw`|dict|是|无|位置或关键字。一条来源配置；已有显式字段保留。|
|`index`|int|是|无|位置或关键字。来源在数组中的零基序号，省略名称时生成source_N。|
|`inferred_type`|str &#124; None|否|None|仅关键字。已编译来源格式；None按明确路径后缀推导ASC/BLF，CSV/内存须显式类型。|

### 返回说明

新字典；已有计划的调用方可避免重复展开目录。

### 异常说明

PlanValidationError表示未知格式、显式空时间或非法名称。

源码：[`src/chronaxis/planning/input_defaults.py:12`](../../../src/chronaxis/planning/input_defaults.py#L12)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-source_reference"></a>
## `source_reference`

取显式来源名，或选择唯一适用来源；多候选不选第一项。

```python
source_reference(raw, sources, path, *, can_only=False)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`raw`|dict|是|无|位置或关键字。含可选source引用的节点配置。|
|`sources`|tuple[SourcePlan, ...]|是|无|位置或关键字。当前来源计划；无显式引用时必须恰有一个适用候选。|
|`path`|str|是|无|位置或关键字。节点配置位置，用于报告引用错误。|
|`can_only`|bool|否|False|仅关键字。True只把原始CAN来源纳入候选，默认False。|

### 返回说明

来源名称字符串。

### 异常说明

PlanValidationError表示无候选、多候选或非法显式名称。

源码：[`src/chronaxis/planning/input_defaults.py:48`](../../../src/chronaxis/planning/input_defaults.py#L48)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
