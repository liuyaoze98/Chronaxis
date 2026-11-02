# chronaxis.core.units

检查信号声明的线性单位转换是否与已知单位关系一致。

输入为原单位、目标单位、scale、offset和方向因子；输出verified或unverified。
已知单位用精确分数核对倍率，未知单位保留未校验状态。本模块检查转换声明，
不转换样本值，也不推断物理方向。仅依赖标准库，没有文件操作或会话状态；
温度和复杂量纲不在当前单位表中。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`require_number`](#api-require_number)|要求有限原生数值，拒绝bool及未经声明的隐式标量转换。|
|[`validate_conversion`](#api-validate_conversion)|核对已知单位的转换系数，无法识别单位时返回unverified。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from fractions import Fraction
from math import isfinite
from types import MappingProxyType
```

</details>

<a id="api-require_number"></a>
## `require_number`

要求有限原生数值，拒绝bool及未经声明的隐式标量转换。

```python
require_number(value: int | float, field: str) -> int | float
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; float|是|无|位置或关键字。value为原生int或有限float|
|`field`|str|是|无|位置或关键字。field用于诊断位置。|

### 返回说明

原数值，不改变整数精度。

### 异常说明

TypeError为其他类型；ValueError为非有限float。

返回类型：int &#124; float。

源码：[`src/chronaxis/core/units.py:25`](../../../src/chronaxis/core/units.py#L25)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-validate_conversion"></a>
## `validate_conversion`

核对已知单位的转换系数，无法识别单位时返回unverified。

```python
validate_conversion(input_unit: str, unit: str, scale: int | float, offset: int | float, direction_factor: int) -> str
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`input_unit`|str|是|无|位置或关键字。已校验的非空原单位标签。|
|`unit`|str|是|无|位置或关键字。已校验的非空目标单位标签。|
|`scale`|int &#124; float|是|无|位置或关键字。显式倍率，必须已经包含direction_factor。|
|`offset`|int &#124; float|是|无|位置或关键字。显式偏移；已知单位的当前转换只接受0。|
|`direction_factor`|int|是|无|位置或关键字。已声明的1或-1，表示方向保持或反转。|

### 返回说明

str: 已知单位关系通过时为verified，任一单位未知时为unverified。
    函数不会补全系数、推断方向或执行样本转换。

### 异常说明

ValueError: 已知单位量纲不兼容，倍率不符合单位关系，或偏移不为0。

返回类型：str。

源码：[`src/chronaxis/core/units.py:44`](../../../src/chronaxis/core/units.py#L44)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
