# `chronaxis.core.expression_math_numpy`

在NumPy列上执行极值、限幅与开方，结果与质量均按行输出。

输入为已通过表达式编译器统一数值类型/尺度的等长列。运算沿同一行跨参数
择值或开方；掩码控制无效位置。没有逐样本Python循环，不修改借用输入。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)

## 对象导航

|对象|用途|
|---|---|
|[`math_numpy`](#api-math_numpy)|用掩码和ufunc求同长数值列的逐行结果。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .numeric_numpy import _output, to_float_numpy
from .types import QualityFlag as Q, SignalDType as D
```

</details>

<a id="api-math_numpy"></a>
## `math_numpy`

用掩码和ufunc求同长数值列的逐行结果。

```python
math_numpy(name, args)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|位置或关键字。编译器交给此核的逐点数组操作名，选择最小、最大、限幅或平方根。|
|`args`|Sequence[NumericArray]|是|无|位置或关键字。各个已求值的数值实参，按原始调用位置顺序提交。|

### 返回说明

同行数NumericArray，开方返回FLOAT64，其余保持公共dtype。

### 异常说明

ValueError为内部未注册名称。内存分配异常直接传播。

源码：[`src/chronaxis/core/expression_math_numpy.py:12`](../../../src/chronaxis/core/expression_math_numpy.py#L12)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
