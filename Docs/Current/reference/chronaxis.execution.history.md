# `chronaxis.execution.history`

估算现役来源/表达式元数据和未完成批协议状态，不保存或回放历史。

保留现有内部导入路径；费用公式与异常边界不因旧历史仓退出而改变。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[BatchValidator](chronaxis.sources.protocol.md#api-BatchValidator)、[ExprNode](chronaxis.core.expression.md#api-ExprNode)、[ExtensionRegistry](chronaxis.extensions.md#api-ExtensionRegistry)、[FunctionSpec](chronaxis.extensions.md#api-FunctionSpec)、[ReductionSpec](chronaxis.extensions.md#api-ReductionSpec)、[ResultFormatError](chronaxis.results.errors.md#api-ResultFormatError)、[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)、[TransformSpec](chronaxis.extensions.md#api-TransformSpec)

## 对象导航

|对象|用途|
|---|---|
|[`_metadata_bytes`](#api-_metadata_bytes)|估算已校验来源/请求的冻结元数据，不改变结果层封闭类型注册。|
|[`_metadata_cost`](#api-_metadata_cost)|按原费用公式估算一个元数据位置，并检测当前容器路径上的环。|
|[`_expression_metadata_cost`](#api-_expression_metadata_cost)|非递归估算已编译表达式，同时保留原节点、字段和重复引用槽费用。|
|[`_pending_bytes`](#api-_pending_bytes)|估算当前组去重状态，不保留历史所有sequence。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from sys import getsizeof
from ..extensions import ExtensionRegistry, FunctionSpec, ReductionSpec, TransformSpec
from ..core.binding import SignalDefinition
from ..core.expression import ExprNode
from ..results.errors import ResultFormatError
from ..sources.protocol import BatchValidator
```

</details>

<a id="api-_metadata_bytes"></a>
## `_metadata_bytes`

估算已校验来源/请求的冻结元数据，不改变结果层封闭类型注册。

```python
_metadata_bytes(value, depth: int=0) -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|object|是|无|位置或关键字。用于估算内存的元数据树，包含已登记模型、元组和原生标量；逐层计算对象及字段大小，不读取信号样本文件。|
|`depth`|int|否|0|位置或关键字。当前递归层数，供内部遍历元数据时检查嵌套深度。顶层使用0，每进入一层增加1。|

### 返回说明

基础bytes。

### 异常说明

ResultFormatError为深度或未支持元数据。

本函数直接报告的具体错误：

- `ResultFormatError`：历史元数据类型无法估算。
- `ResultFormatError`：历史元数据超过32层。

返回类型：int。

源码：[`src/chronaxis/execution/history.py:15`](../../../src/chronaxis/execution/history.py#L15)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_metadata_cost"></a>
## `_metadata_cost`

按原费用公式估算一个元数据位置，并检测当前容器路径上的环。

```python
_metadata_cost(value, depth, active, expression_costs)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|dataclass &#124; Mapping &#124; tuple &#124; Enum &#124; str &#124; bytes &#124; int &#124; bool &#124; float &#124; None|是|无|位置或关键字。已检查的冻结元数据位置，包括已编译表达式及已登记宿主描述；不遍历任意回调。|
|`depth`|int|是|无|位置或关键字。普通容器递归深度，超过 32 层拒绝；表达式子树由专用栈遍历。|
|`active`|set[int]|是|无|位置或关键字。当前遍历路径中的对象身份，用于检测循环；退出当前位置时移除。|
|`expression_costs`|dict[tuple[int, int], tuple[[chronaxis.core.expression.ExprNode](chronaxis.core.expression.md#api-ExprNode), int]]|是|无|位置或关键字。本次估算中按节点身份和普通深度保存的表达式费用缓存，重复引用仍累计完整费用。|

### 返回说明

此引用位置的完整费用。

### 异常说明

深度、环或未知结构的ResultFormatError。

### 副作用说明

临时登记当前路径；返回或异常时移除，不修改调用方元数据。

源码：[`src/chronaxis/execution/history.py:26`](../../../src/chronaxis/execution/history.py#L26)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_expression_metadata_cost"></a>
## `_expression_metadata_cost`

非递归估算已编译表达式，同时保留原节点、字段和重复引用槽费用。

```python
_expression_metadata_cost(root, depth, active, costs)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`root`|[chronaxis.core.expression.ExprNode](chronaxis.core.expression.md#api-ExprNode)|是|无|位置或关键字。待用显式栈遍历的已编译表达式根节点。|
|`depth`|int|是|无|位置或关键字。表达式外部普通容器的深度，不把每层 args 元组另算为数据协议层级。|
|`active`|set[int]|是|无|位置或关键字。当前容器路径的身份集合，检测环并在成功或失败退出时清理本次登记。|
|`costs`|dict[tuple[int, int], tuple[[chronaxis.core.expression.ExprNode](chronaxis.core.expression.md#api-ExprNode), int]]|是|无|位置或关键字。本次元数据估算的节点与费用缓存，只避免重复遍历，不减少重复引用费用。|

### 返回说明

根的完整费用，重复子树每出现一次仍收一次原费用。

### 异常说明

子节点不是ExprNode、args不是tuple、环或字段结构错误的ResultFormatError。

### 副作用说明

缓存只活到本次_metadata_bytes返回，不持有样本或跨任务状态。

源码：[`src/chronaxis/execution/history.py:72`](../../../src/chronaxis/execution/history.py#L72)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_pending_bytes"></a>
## `_pending_bytes`

估算当前组去重状态，不保留历史所有sequence。

```python
_pending_bytes(validator: BatchValidator) -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`validator`|[BatchValidator](chronaxis.sources.protocol.md#api-BatchValidator)|是|无|位置或关键字。validator为一个来源协议状态。|

### 返回说明

保守bytes。

### 异常说明

已校验状态不主动抛错。

返回类型：int。

源码：[`src/chronaxis/execution/history.py:118`](../../../src/chronaxis/execution/history.py#L118)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
