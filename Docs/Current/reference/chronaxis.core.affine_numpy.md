# `chronaxis.core.affine_numpy`

按列执行单位的完整仿射转换，保持固定类型和逐位置质量掩码。

输入为 NumericArray、静态倍率/偏移与目标类型；输出形状保持(N,)的独立
只读 NumericArray。整数复用已有数组仿射核的精确逆区间算法；浮点使用
NumPy ufunc与有效掩码，不调用标量参考数值计算，不使用object数组或
逐样本Python回调。无效位置不参与运算，已有质量原因保留；不读写文件、
不改调用方数组、不保存样本历史。单位关系由表达式或结果编译器事先证明。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)、[QualityFlag](chronaxis.core.types.md#api-QualityFlag)、[SignalDType](chronaxis.core.types.md#api-SignalDType)

## 对象导航

|对象|用途|
|---|---|
|[`_float_coefficient`](#api-_float_coefficient)|仅转换一个编译期系数，不对样本调用Python标量参考。|
|[`affine_numpy`](#api-affine_numpy)|在有效位置执行value*scale+offset，不以中间回绕或舍入替代结果。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from math import isfinite
from .affine import _validate_affine
from .normalize_numpy import _affine_integer
from .numeric import INTEGER_BOUNDS
from .numeric_numpy import NumericArray, _output, to_float_numpy
from .types import QualityFlag, SignalDType
```

</details>

<a id="api-_float_coefficient"></a>
## `_float_coefficient`

仅转换一个编译期系数，不对样本调用Python标量参考。

```python
_float_coefficient(value: int | float) -> tuple[float | None, QualityFlag]
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; float|是|无|位置或关键字。value为已验证的原生整数或有限浮点系数。|

### 返回说明

有限浮点值与NONE，或None与NONFINITE/PRECISION_LOSS。

### 异常说明

无主动异常；整数超出浮点范围转换成NONFINITE。

返回类型：tuple[float &#124; None, [QualityFlag](chronaxis.core.types.md#api-QualityFlag)]。

源码：[`src/chronaxis/core/affine_numpy.py:22`](../../../src/chronaxis/core/affine_numpy.py#L22)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-affine_numpy"></a>
## `affine_numpy`

在有效位置执行value*scale+offset，不以中间回绕或舍入替代结果。

```python
affine_numpy(value: NumericArray, scale: int | float, offset: int | float, dtype: SignalDType) -> NumericArray
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)|是|无|位置或关键字。value为(N,)数值列|
|`scale`|int &#124; float|是|无|位置或关键字。源物理值先乘的有限倍率；整数输出要求倍率为原生整数。|
|`offset`|int &#124; float|是|无|位置或关键字。乘完倍率再加的有限偏移量；纯比例换算填零。|
|`dtype`|[SignalDType](chronaxis.core.types.md#api-SignalDType)|是|无|位置或关键字。dtype为目标     数值类型。整数目标要求整数输入和整数系数|

### 返回说明

同长独立只读NumericArray；无效位置仅存零占位，原因保持或增加
    OVERFLOW、NONFINITE、PRECISION_LOSS。输入和有效/质量列不被修改。

### 异常说明

TypeError/ValueError为声明结构错误；MemoryError等分配异常传播。

### 边界说明

温度偏移抵消为零有效；只有零偏移、非零因子的非零值变成零时，
    才按纯倍率下溢报告精度损失。全部数值操作按数组执行。

返回类型：[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)。

源码：[`src/chronaxis/core/affine_numpy.py:41`](../../../src/chronaxis/core/affine_numpy.py#L41)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
