# `chronaxis.execution.static_metadata`

按实际对象身份估算一次运行借用的静态声明，不展开重复引用。

输入只限已经校验的声明模型；返回浅对象及其独有子对象的字节估计。
此函数用于计划、编译树的固定费用，不改变样本、历史或动态工作区的计费。
已有父资源持有的对象可显式排除；这里只计算费用，不接管它们的生命周期。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ExprNode](chronaxis.core.expression.md#api-ExprNode)、[ExtensionRegistry](chronaxis.extensions.md#api-ExtensionRegistry)、[FunctionSpec](chronaxis.extensions.md#api-FunctionSpec)、[ReductionSpec](chronaxis.extensions.md#api-ReductionSpec)、[ResultFormatError](chronaxis.results.errors.md#api-ResultFormatError)、[TransformSpec](chronaxis.extensions.md#api-TransformSpec)

## 对象导航

|对象|用途|
|---|---|
|[`static_metadata_bytes`](#api-static_metadata_bytes)|遍历不可变声明图，一次调用内每个实际对象只计一次。|
|[`_static_metadata_cost`](#api-_static_metadata_cost)|累加尚未登记的对象并更新本次身份集合。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from sys import getsizeof
from ..core.expression import ExprNode
from ..extensions import ExtensionRegistry, FunctionSpec, ReductionSpec, TransformSpec
from ..results.errors import ResultFormatError
```

</details>

<a id="api-static_metadata_bytes"></a>
## `static_metadata_bytes`

遍历不可变声明图，一次调用内每个实际对象只计一次。

```python
static_metadata_bytes(value, *, borrowed=())
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|None、bool、int、float、str、bytes、Enum、tuple、Mapping、dataclass实例或宿主扩展声明|是|无|位置或关键字。要估算的已校验静态声明及其子对象；按对象身份计算一次，不读取样本或函数全局变量。|
|`borrowed`|tuple[object, ...]|否|()|仅关键字。由仍开放的父资源实际持有且已计费的对象；只排除相同对象及其子对象，空tuple表示全部自行计费。|

### 返回说明

对象、容器和实例属性字典的保守字节数；只读映射另计背后字典槽。

### 异常说明

ResultFormatError为循环、未知结构或普通容器超过32层。
表达式args用显式栈处理，不将合法表达式长度当成外部协议深度。

源码：[`src/chronaxis/execution/static_metadata.py:18`](../../../src/chronaxis/execution/static_metadata.py#L18)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_static_metadata_cost"></a>
## `_static_metadata_cost`

累加尚未登记的对象并更新本次身份集合。

```python
_static_metadata_cost(value, seen)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|None、bool、int、float、str、bytes、Enum、tuple、Mapping、dataclass实例或宿主扩展声明|是|无|位置或关键字。本次从该声明开始遍历并累加尚未登记的对象费用。|
|`seen`|set[int]|是|无|位置或关键字。已由父对象或本次遍历计费的实际对象id集合；函数会登记新增对象。|

### 返回说明

新增费用。

### 异常说明

循环、深度或类型错误。集合只活在本次估算调用内。

源码：[`src/chronaxis/execution/static_metadata.py:33`](../../../src/chronaxis/execution/static_metadata.py#L33)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
