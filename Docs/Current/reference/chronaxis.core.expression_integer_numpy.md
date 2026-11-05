# `chronaxis.core.expression_integer_numpy`

整列处理64位取余、位操作和精确转整数，保留每行无效原因。

输入是已统一类型的NumericArray和编译期位号。先用掩码排除危险除法、
越界和精度失败，再在可表示范围内执行NumPy运算。所有结果均为同长列。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)

## 对象导航

|对象|用途|
|---|---|
|[`integer_numpy`](#api-integer_numpy)|在有效行上对数值列执行已编译的整数操作。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .numeric_numpy import DTYPES, _output
from .types import QualityFlag as Q, SignalDType as D
```

</details>

<a id="api-integer_numpy"></a>
## `integer_numpy`

在有效行上对数值列执行已编译的整数操作。

```python
integer_numpy(node, args)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`node`|ExprNode|是|无|位置或关键字。已通过静态检查的操作节点，携带操作类型、输入依赖和输出单位。|
|`args`|Sequence[NumericArray]|是|无|位置或关键字。按配置位置排好的整数或显式类型转换操作数，每个保留本批数值与质量。|

### 返回说明

同长结果列，输入无效位与本次产生的逐行原因保留。

### 异常说明

ValueError为未知内部节点。分配发生异常时直接交给调用者处理。

源码：[`src/chronaxis/core/expression_integer_numpy.py:12`](../../../src/chronaxis/core/expression_integer_numpy.py#L12)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
