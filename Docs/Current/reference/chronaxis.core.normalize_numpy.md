# `chronaxis.core.normalize_numpy`

按信号声明转换一列原字段值，并保留有效性、质量和原来源身份。

直接入口输入SignalDefinition、同质的已解码原列及uint16上游质量，输出
NumericArray。执行额外线性转换、编码映射、无效值及业务范围检查，不重复
DBC已完成的缩放。整数仿射先用精确配置常量求合法输入区间，再用无符号
距离按列计算，避免定宽中间回绕，不使用object数组进行数值运算。
memory_series_numpy按原生类型分组装箱，批量转换后按原行顺序恢复样本。
Python逐行操作负责类型分组和身份还原，不执行逐样本数值参考计算。
本模块依赖NumPy和核心模型，不读取文件或旧来源，不修改调用方原列；
完整内存历史会分配与行数成比例的存储，不保证生产执行预算。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)、[QualityFlag](chronaxis.core.types.md#api-QualityFlag)、[SignalBindings](chronaxis.core.binding.md#api-SignalBindings)、[SignalDType](chronaxis.core.types.md#api-SignalDType)、[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)、[SignalSample](chronaxis.core.models.md#api-SignalSample)、[SignalSeries](chronaxis.core.state.md#api-SignalSeries)

## 对象导航

|对象|用途|
|---|---|
|[`_affine_integer`](#api-_affine_integer)|用逆映射范围与幅度分段实现精确整数线性转换。|
|[`_float_limit`](#api-_float_limit)|将精确配置边界向区间内收至可表示float64端点。|
|[`normalize_numpy`](#api-normalize_numpy)|按声明批量转换原列，检查编码映射、无效原值和转换后的业务范围。|
|[`memory_series_numpy`](#api-memory_series_numpy)|按原字段类型分组装箱，批量转换后恢复原行顺序和来源身份。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from math import ceil, floor, isfinite
from .binding import SignalBindings, SignalDefinition
from .models import SignalSample
from .numeric import INTEGER_BOUNDS
from .numeric_numpy import DTYPES, NumericArray, _from_magnitude, _magnitude, _output, to_float_numpy
from .state import SignalSeries
from .types import QualityFlag, SignalDType
from ..timebase.conversion import checked_add_ns
```

</details>

<a id="api-_affine_integer"></a>
## `_affine_integer`

用逆映射范围与幅度分段实现精确整数线性转换。

```python
_affine_integer(raw, selected, dtype, scale, offset)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`raw`|numpy.ndarray[int64] &#124; numpy.ndarray[uint64]|是|无|位置或关键字。原始整数列，按信号声明的比例和偏移转换；保持整数边界，避免先转浮点导致大整数舍入。|
|`selected`|numpy.ndarray[bool]|是|无|位置或关键字。与输入列等长的布尔掩码；True的位置参加本次运算，False的位置跳过。|
|`dtype`|int|是|无|位置或关键字。dtype目标整数|
|`scale`|int|是|无|位置或关键字。整数换算倍率，公式为原值×scale＋offset；可以为负，以改变数值方向。|
|`offset`|int|是|无|位置或关键字。乘完scale后再加的整数偏移；运算前先检查结果是否能由目标整数类型表示。|

### 返回说明

目标定宽列及OVERFLOW mask；允许中间数学值越界但最终值合法。

### 异常说明

调用侧校验类型，分配错误传播；不逐样本用Python算数。

源码：[`src/chronaxis/core/normalize_numpy.py:34`](../../../src/chronaxis/core/normalize_numpy.py#L34)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_float_limit"></a>
## `_float_limit`

将精确配置边界向区间内收至可表示float64端点。

```python
_float_limit(value, *, lower)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; float|是|无|位置或关键字。信号有效范围的一端；整数或有限浮点数，不接受NaN和无穷值。|
|`lower`|bool|是|无|仅关键字。True表示正在检查下限，False表示正在检查上限。|

### 返回说明

float端点，大到不可表示的整数按方向得到Inf/最大有限值。

### 异常说明

配置类型已校验；数值转换溢出仅表示不可达端点。

源码：[`src/chronaxis/core/normalize_numpy.py:146`](../../../src/chronaxis/core/normalize_numpy.py#L146)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-normalize_numpy"></a>
## `normalize_numpy`

按声明批量转换原列，检查编码映射、无效原值和转换后的业务范围。

```python
normalize_numpy(definition: SignalDefinition, raw: np.ndarray, quality: np.ndarray | None=None) -> NumericArray
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`definition`|[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)|是|无|位置或关键字。当前信号类型、转换、编码和范围声明。|
|`raw`|np.ndarray|是|无|位置或关键字。同质原列，dtype为int64、uint64、float64、 bool或Unicode文本；不接受object数组和隐式广播。|
|`quality`|np.ndarray &#124; None|否|None|位置或关键字。已知上游质量原因；默认 None表示全部NONE。已有原因保留，无效位置不进入正常计算。|

### 返回说明

NumericArray: 目标声明类型的值、有效掩码和完整质量原因。无效值是
    存储占位；内存适配另外从原行保留诊断值。

### 异常说明

TypeError或ValueError: 输入布局、质量位或声明结构不合法。
    MemoryError: 数组分配失败。
    数值溢出、非有限值或精度损失记录为质量原因，不输出正常值。

### 副作用说明

输出和原因使用局部数组，不修改原列或调用者质量列。

返回类型：[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)。

源码：[`src/chronaxis/core/normalize_numpy.py:168`](../../../src/chronaxis/core/normalize_numpy.py#L168)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-memory_series_numpy"></a>
## `memory_series_numpy`

按原字段类型分组装箱，批量转换后恢复原行顺序和来源身份。

```python
memory_series_numpy(bindings: SignalBindings, name: str, *, capture_code=False) -> SignalSeries
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`bindings`|[SignalBindings](chronaxis.core.binding.md#api-SignalBindings)|是|无|位置或关键字。当前会话的已校验绑定。|
|`name`|str|是|无|位置或关键字。已绑定的原信号别名。|
|`capture_code`|bool|否|False|仅关键字。本次表达式需要 enum_code 时才保留映射前的整数。|

### 返回说明

SignalSeries: 正常值使用转换结果，无效值保留原字段诊断；时间只应用
    声明的固定偏移，原序号和来源引用保持不变。

### 异常说明

TypeError、ValueError或OverflowError: 定义、布局、同时间冲突、原行归属
    或时间映射检查失败。
    MemoryError: 装箱、结果或数组分配失败。

### 副作用说明

分配本次完整历史，不读取旧来源或修改原行。

返回类型：[SignalSeries](chronaxis.core.state.md#api-SignalSeries)。

源码：[`src/chronaxis/core/normalize_numpy.py:331`](../../../src/chronaxis/core/normalize_numpy.py#L331)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
