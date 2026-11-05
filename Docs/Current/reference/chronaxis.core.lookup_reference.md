# `chronaxis.core.lookup_reference`

用标量二分搜索一维表，精确命中和两种阶梯模式直接取节点原值。

输入为编译节点保存的不可变表和已换到输入轴单位的标量。线性模式只在
严格内部点做浮点运算，无效输入、越界和非有限中间运算保留各自原因。
独立参考实现不导入 NumPy，不保存时序状态。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)

## 对象导航

|对象|用途|
|---|---|
|[`lookup_reference`](#api-lookup_reference)|查询一个标量。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from math import isfinite
from .numeric import ScalarValue, to_float_reference
from .types import QualityFlag as Q
```

</details>

<a id="api-lookup_reference"></a>
## `lookup_reference`

查询一个标量。

```python
lookup_reference(table, value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`table`|PreparedLookup|是|无|位置或关键字。静态校验并绑定了轴、输出类型、插值模式和越界政策的不可变表。|
|`value`|[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)|是|无|位置或关键字。已换算到标定轴单位的输入数值及质量，在有效输入上应用表内或越界规则。|

### 返回说明

表单位对应的标量。

### 异常说明

非法声明类型。

源码：[`src/chronaxis/core/lookup_reference.py:13`](../../../src/chronaxis/core/lookup_reference.py#L13)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
