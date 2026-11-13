# `chronaxis.core.rate_transforms`

为三类时序变化率核对数值输入和单位，并选择逐点或数组后端。

时间线调用方提供有效边界值或窗口中的真实样本，以及实际/周期口径的相对
纳秒计量。此处不创建网格或驱动帧，不推断TTL、窗口完整性或max_gap。
输出为FLOAT64 ScalarValue，单位从输入的当前数值尺度和温度角色推导。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)

## 对象导航

|对象|用途|
|---|---|
|[`rate_unit`](#api-rate_unit)|确定当前数值尺度的每秒自然单位，绝对温度先变为温差。|
|[`_quality`](#api-_quality)|检查已绑定的同型数值样本，并汇总全部必要输入的无效原因。|
|[`_position`](#api-_position)|校验内部实际纳秒或精确周期坐标，防止把大纪元时间先转浮点。|
|[`rate_difference`](#api-rate_difference)|用两个边界值之差除以已选实际时间或折算周期跨度。|
|[`rate_fit`](#api-rate_fit)|在至少两个不同时间的真实样本上求等权最小二乘斜率。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from fractions import Fraction
from . import unit_registry as units
from .numeric import ScalarValue
from .types import QualityFlag as Q, SignalDType as D
```

</details>

<a id="api-rate_unit"></a>
## `rate_unit`

确定当前数值尺度的每秒自然单位，绝对温度先变为温差。

```python
rate_unit(input_unit)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`input_unit`|str|是|无|位置或关键字。输入样本当前的单位文本；数值尺度决定每秒速率的自然单位，绝对温度先转为温差角色。|

### 返回说明

可重新解析的单位，如V/s、mV/s、delta_K/s或Hz。

### 异常说明

ValueError为未登记或非法单位，不以未知标签证明量纲。

源码：[`src/chronaxis/core/rate_transforms.py:14`](../../../src/chronaxis/core/rate_transforms.py#L14)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_quality"></a>
## `_quality`

检查已绑定的同型数值样本，并汇总全部必要输入的无效原因。

```python
_quality(backend, samples)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`backend`|str|是|无|位置或关键字。选择reference标量核或numpy数组核；两者计算相同定义的每秒变化率。|
|`samples`|Sequence[[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)]|是|无|位置或关键字。按真实更新时间排列的同类型样本，拟合时每个测量点权重相同。|

### 返回说明

合并的QualityFlag。

### 异常说明

TypeError/ValueError为模型或静态dtype不符。

源码：[`src/chronaxis/core/rate_transforms.py:32`](../../../src/chronaxis/core/rate_transforms.py#L32)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_position"></a>
## `_position`

校验内部实际纳秒或精确周期坐标，防止把大纪元时间先转浮点。

```python
_position(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; Fraction|是|无|位置或关键字。待校验的原始纳秒或精确周期坐标，不接受浮点时间。|

### 返回说明

原坐标。

### 异常说明

TypeError为单位/类型不符。

源码：[`src/chronaxis/core/rate_transforms.py:52`](../../../src/chronaxis/core/rate_transforms.py#L52)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-rate_difference"></a>
## `rate_difference`

用两个边界值之差除以已选实际时间或折算周期跨度。

```python
rate_difference(backend, left, right, elapsed_ns)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`backend`|str|是|无|位置或关键字。选择reference标量核或numpy数组核；两者计算相同定义的每秒变化率。|
|`left`|[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)|是|无|位置或关键字。差分区间起点的已绑定数值及其质量，不用数组下标推断时间。|
|`right`|[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)|是|无|位置或关键字。差分区间终点的同类型数值；用其减去起点值。|
|`elapsed_ns`|int &#124; Fraction|是|无|位置或关键字。两个端点之间所选的实际或折算周期跨度，单位纳秒；合法差分必须为正。|

### 返回说明

FLOAT64数值或带原因的无效值，合法负斜率不受原无符号dtype限制。

### 异常说明

非数值、后端或坐标类型错误直接拒绝。非正跨度属于DOMAIN_ERROR。

源码：[`src/chronaxis/core/rate_transforms.py:62`](../../../src/chronaxis/core/rate_transforms.py#L62)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-rate_fit"></a>
## `rate_fit`

在至少两个不同时间的真实样本上求等权最小二乘斜率。

```python
rate_fit(backend, positions_ns, samples)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`backend`|str|是|无|位置或关键字。选择reference标量核或numpy数组核；两者计算相同定义的每秒变化率。|
|`positions_ns`|Sequence[int &#124; Fraction]|是|无|位置或关键字。与真实样本一一对应的精确纳秒坐标；先相对首点平移，再进行窗口拟合。|
|`samples`|Sequence[[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)]|是|无|位置或关键字。按真实更新时间排列的同类型样本，拟合时每个测量点权重相同。|

### 返回说明

FLOAT64每秒斜率；少于两个样本为MISSING，非递增位置为DOMAIN_ERROR。

### 异常说明

ValueError为长度不符，类型错误原样传播。

源码：[`src/chronaxis/core/rate_transforms.py:81`](../../../src/chronaxis/core/rate_transforms.py#L81)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
