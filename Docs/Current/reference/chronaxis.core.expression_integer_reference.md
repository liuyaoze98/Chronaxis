# `chronaxis.core.expression_integer_reference`

在单点64位整数与浮点输入上执行取余、位提取和精确转整数。

输入为已编译节点与带有明确类型的标量元组。Python整数保存精确的中间数，
判定范围后才构造目标ScalarValue。转float复用公共精度检查。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)

## 对象导航

|对象|用途|
|---|---|
|[`integer_reference`](#api-integer_reference)|在标量域执行节点，拒绝0除数、整型范围外或有小数部分的转换。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .numeric import INTEGER_BOUNDS, ScalarValue
from .types import QualityFlag as Q
```

</details>

<a id="api-integer_reference"></a>
## `integer_reference`

在标量域执行节点，拒绝0除数、整型范围外或有小数部分的转换。

```python
integer_reference(node, args)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`node`|ExprNode|是|无|位置或关键字。已通过静态检查的操作节点，携带操作类型、输入依赖和输出单位。|
|`args`|Sequence[[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)]|是|无|位置或关键字。按配置位置排好的整数或显式类型转换操作数，每个保留本批数值与质量。|

### 返回说明

ScalarValue，质量非零时不产生有效值。

### 异常说明

ValueError为未登记的内部操作；有效输入的数值失败写入质量。

源码：[`src/chronaxis/core/expression_integer_reference.py:11`](../../../src/chronaxis/core/expression_integer_reference.py#L11)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
