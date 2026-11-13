# `chronaxis.core.affine`

将一个已校验数值换到目标单位，执行一次完整的乘法与偏移转换。

输入为 ScalarValue、编译期确定的倍率/偏移和目标类型；输出仍为 ScalarValue。
整数在 Python 精确整数域计算最终结果，再检查目标定宽；浮点先检查整数
输入的可表示性，再计算并检查有限性与纯倍率下溢。未知值保持原质量原因，
不会因为乘零或加偏移变成正常数据。本模块不依赖 NumPy，不读取文件，
不改变输入，也不保存转换前后副本或跨批次状态。单位关系由编译器验证。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[QualityFlag](chronaxis.core.types.md#api-QualityFlag)、[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)、[SignalDType](chronaxis.core.types.md#api-SignalDType)

## 对象导航

|对象|用途|
|---|---|
|[`_validate_affine`](#api-_validate_affine)|检查编译器传入的仿射转换结构，数值合法性仍逐样本处理。|
|[`affine_reference`](#api-affine_reference)|按value*scale+offset完成标量单位转换，并保留精度及有效性。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from math import isfinite
from .numeric import INTEGER_BOUNDS, ScalarValue, _exact_float
from .types import QualityFlag, SignalDType
```

</details>

<a id="api-_validate_affine"></a>
## `_validate_affine`

检查编译器传入的仿射转换结构，数值合法性仍逐样本处理。

```python
_validate_affine(source_dtype, dtype, scale, offset) -> None
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source_dtype`|[SignalDType](chronaxis.core.types.md#api-SignalDType)|是|无|位置或关键字。转换前的原数值类型，用来校验是否允许保留整数输出。|
|`dtype`|[SignalDType](chronaxis.core.types.md#api-SignalDType)|是|无|位置或关键字。静态确定的目标定宽数值类型，决定输出采用整数还是 float64。|
|`scale`|int &#124; float|是|无|位置或关键字。源物理值先乘的有限倍率；整数输出要求倍率为原生整数。|
|`offset`|int &#124; float|是|无|位置或关键字。乘完倍率再加的有限偏移量；纯比例换算填零。|

### 返回说明

None，无副作用。

### 异常说明

TypeError为非数值类型/系数；ValueError为非有限系数或错误类型提升。

返回类型：None。

源码：[`src/chronaxis/core/affine.py:17`](../../../src/chronaxis/core/affine.py#L17)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-affine_reference"></a>
## `affine_reference`

按value*scale+offset完成标量单位转换，并保留精度及有效性。

```python
affine_reference(value: ScalarValue, scale: int | float, offset: int | float, dtype: SignalDType) -> ScalarValue
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)|是|无|位置或关键字。value为已校验数值|
|`scale`|int &#124; float|是|无|位置或关键字。源物理值先乘的有限倍率；整数输出要求倍率为原生整数。|
|`offset`|int &#124; float|是|无|位置或关键字。乘完倍率再加的有限偏移量；纯比例换算填零。|
|`dtype`|[SignalDType](chronaxis.core.types.md#api-SignalDType)|是|无|位置或关键字。dtype为静态     目标数值类型。整数目标只接整数输入和系数，浮点目标检查大整数精度。|

### 返回说明

ScalarValue；超定宽为OVERFLOW，浮点非有限为NONFINITE，不能精确
    转为浮点或纯倍率下溢到零为PRECISION_LOSS，输入无效则保留原原因。

### 异常说明

TypeError或ValueError为声明结构错误；不将配置错误变成样本质量。

### 边界说明

-273.15乘1再加273.15得到正常0；整数中间乘积可以超过64位，
    只要完整仿射结果仍在目标范围。无副作用，不保留转换历史。

返回类型：[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)。

源码：[`src/chronaxis/core/affine.py:40`](../../../src/chronaxis/core/affine.py#L40)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
