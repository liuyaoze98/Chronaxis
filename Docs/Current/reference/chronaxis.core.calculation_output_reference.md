# `chronaxis.core.calculation_output_reference`

将一个已归约的数值换到目标单位，保留空值和数值质量。

输入为标量归约结果、原类型和编译期转换；输出数值及质量标志。
复用参考仿射核，在归约结束后只换算一次，不重算样本，不读写文件。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)

## 对象导航

|对象|用途|
|---|---|
|[`convert_result_reference`](#api-convert_result_reference)|以参考数值核换算单个非空结果，合法温度抵消为零保持有效。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .affine import affine_reference
from .numeric import ScalarValue
from .types import SignalDType as D, QualityFlag as Q
```

</details>

<a id="api-convert_result_reference"></a>
## `convert_result_reference`

以参考数值核换算单个非空结果，合法温度抵消为零保持有效。

```python
convert_result_reference(value, input_dtype, conversion)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; float &#124; None|是|无|位置或关键字。归约后的原数值，空值不参与换算，即使变换有温度偏移也保持为空。|
|`input_dtype`|SignalDType|是|无|位置或关键字。转换前的数值类型；据此区分可保留的整数与须提升的浮点结果。|
|`conversion`|CalculationConversion|是|无|位置或关键字。编译时选定的输出单位换算，提供倍率、偏移以及结果数值类型。|

### 返回说明

(数值或None, QualityFlag)，失败不把结果当成正常零。

### 异常说明

非法模型或系数错误传播，数值范围错误由质量表示。

源码：[`src/chronaxis/core/calculation_output_reference.py:12`](../../../src/chronaxis/core/calculation_output_reference.py#L12)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
