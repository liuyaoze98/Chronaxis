# `chronaxis.core.calculation_output_numpy`

将一个数组归约结果换到目标单位，不调用参考数值核。

输入为归约标量、原类型和编译期转换；用单元素带有明确类型的列复用数组仿射核，
输出值与质量。这里只转换最终结果，不按样本循环或创建额外历史。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)、[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)

## 对象导航

|对象|用途|
|---|---|
|[`convert_result_numpy`](#api-convert_result_numpy)|用NumPy仿射核完成一个非空结果的单位转换。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .affine_numpy import affine_numpy
from .numeric_numpy import NumericArray, DTYPES
from .types import SignalDType as D, QualityFlag as Q
```

</details>

<a id="api-convert_result_numpy"></a>
## `convert_result_numpy`

用NumPy仿射核完成一个非空结果的单位转换。

```python
convert_result_numpy(value, input_dtype, conversion)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; float &#124; None|是|无|位置或关键字。归约后的原数值，空值不参与换算，即使变换有温度偏移也保持为空。|
|`input_dtype`|SignalDType|是|无|位置或关键字。转换前的数值类型；据此区分可保留的整数与须提升的浮点结果。|
|`conversion`|CalculationConversion|是|无|位置或关键字。编译时选定的输出单位换算，提供倍率、偏移以及结果数值类型。|

### 返回说明

(Python数值或None, QualityFlag)，空值保持空值。

### 异常说明

非法模型、分配或系数错误传播；数值故障写入质量。

源码：[`src/chronaxis/core/calculation_output_numpy.py:13`](../../../src/chronaxis/core/calculation_output_numpy.py#L13)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
