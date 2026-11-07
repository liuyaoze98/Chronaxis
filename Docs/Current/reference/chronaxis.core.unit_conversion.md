# `chronaxis.core.unit_conversion`

在配置编译时确定版本4的单位转换和数值类型。

输入是声明单位、完整转换系数和dtype，输出系数、校验状态及固定目标类型。
只复用不可变单位注册表；不读取DBC、不处理样本、不创建运行时全局状态。
当前只接受版本4；未知单位仍须明确转换，不隐式回退到旧单位规则。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[SignalDType](chronaxis.core.types.md#api-SignalDType)

## 对象导航

|对象|用途|
|---|---|
|[`require_config_version`](#api-require_config_version)|检查已有配置版本选择，不把bool当作整数版本。|
|[`binding_version`](#api-binding_version)|校验所有定义与可选显式版本，仅返回当前版本4。|
|[`affine_conversion`](#api-affine_conversion)|生成一次源单位到目标单位的完整转换。|
|[`validate_conversion_v4`](#api-validate_conversion_v4)|验证调用方已经确定的完整转换，不再次叠加单位倍率。|
|[`converted_dtype`](#api-converted_dtype)|在编译期决定单位转换是否需要浮点类型。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from fractions import Fraction
from .types import SignalDType
from .units import require_number
from .unit_registry import conversion, resolve_unit
```

</details>

<a id="api-require_config_version"></a>
## `require_config_version`

检查已有配置版本选择，不把bool当作整数版本。

```python
require_config_version(version: int) -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`version`|int|是|无|位置或关键字。version为原生整数4。|

### 返回说明

原版本。

### 异常说明

ValueError为未支持的版本或错误类型。

返回类型：int。

源码：[`src/chronaxis/core/unit_conversion.py:16`](../../../src/chronaxis/core/unit_conversion.py#L16)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-binding_version"></a>
## `binding_version`

校验所有定义与可选显式版本，仅返回当前版本4。

```python
binding_version(definitions, explicit: int | None=None) -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`definitions`|Iterable[SignalDefinition &#124; ExpressionParameter]|是|无|位置或关键字。具有 config_version 的已校验定义序列，各项必须使用同一版本。|
|`explicit`|int &#124; None|否|None|位置或关键字。definitions为已检查的定义序列，explicit可省略|

### 返回说明

4。

### 异常说明

ValueError为任一定义或显式参数不支持的版本。

返回类型：int。

源码：[`src/chronaxis/core/unit_conversion.py:29`](../../../src/chronaxis/core/unit_conversion.py#L29)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-affine_conversion"></a>
## `affine_conversion`

生成一次源单位到目标单位的完整转换。

```python
affine_conversion(input_unit: str, unit: str) -> tuple[int | float, int | float, str]
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`input_unit`|str|是|无|位置或关键字。原始信号已解码到的单位标签，作为换算起点。|
|`unit`|str|是|无|位置或关键字。希望绑定采用的目标单位标签，须与原始物理量兼容。|

### 返回说明

(scale, offset, status)；整数系数保留int，同名未知标签保持1、0、unverified。

### 异常说明

ValueError为已知单位冲突、异名未知关系、非法语法或float倍率不可表示。

返回类型：tuple[int &#124; float, int &#124; float, str]。

源码：[`src/chronaxis/core/unit_conversion.py:43`](../../../src/chronaxis/core/unit_conversion.py#L43)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-validate_conversion_v4"></a>
## `validate_conversion_v4`

验证调用方已经确定的完整转换，不再次叠加单位倍率。

```python
validate_conversion_v4(input_unit: str, unit: str, scale: int | float, offset: int | float, direction_factor: int=1) -> str
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`input_unit`|str|是|无|位置或关键字。原始信号已解码到的单位标签，作为换算起点。|
|`unit`|str|是|无|位置或关键字。希望绑定采用的目标单位标签，须与原始物理量兼容。|
|`scale`|int &#124; float|是|无|位置或关键字。已确定的完整有限倍率，先乘于解码后的原值。|
|`offset`|int &#124; float|是|无|位置或关键字。完成倍率换算后再加的有限偏移，例如摄氏到开尔文的温标差。|
|`direction_factor`|int|否|1|位置或关键字。direction_factor为已核实方向。|

### 返回说明

verified或unverified。

### 异常说明

TypeError为非原生系数；ValueError为单位或系数冲突。

返回类型：str。

源码：[`src/chronaxis/core/unit_conversion.py:63`](../../../src/chronaxis/core/unit_conversion.py#L63)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-converted_dtype"></a>
## `converted_dtype`

在编译期决定单位转换是否需要浮点类型。

```python
converted_dtype(dtype: SignalDType, scale: int | float, offset: int | float) -> SignalDType
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`dtype`|[SignalDType](chronaxis.core.types.md#api-SignalDType)|是|无|位置或关键字。换算前的声明类型，用于判断新尺度能否保留原整数类型。|
|`scale`|int &#124; float|是|无|位置或关键字。已确定的完整有限倍率，先乘于解码后的原值。|
|`offset`|int &#124; float|是|无|位置或关键字。完成倍率换算后再加的有限偏移，例如摄氏到开尔文的温标差。|

### 返回说明

有分数倍率或偏移的整数提升FLOAT64，其余保持原类型。

### 异常说明

TypeError为错误dtype或系数；ValueError为非有限系数。

返回类型：[SignalDType](chronaxis.core.types.md#api-SignalDType)。

源码：[`src/chronaxis/core/unit_conversion.py:89`](../../../src/chronaxis/core/unit_conversion.py#L89)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
