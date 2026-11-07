# `chronaxis.core.rate_reference`

用独立标量差分和中心化等权回归计算有效真实样本的每秒变化率。

相邻/窗口的两个端点只做一次精确差，再转浮点输出。拟合使用局部时间和按
二进制指数缩放的值，避免绝对时间精度损失及大温度/电压背景造成的相消。
没有跨调用状态，窗口、真实间隔有效性及临时预算由时间线调用者提供。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)

## 对象导航

|对象|用途|
|---|---|
|[`_result`](#api-_result)|将已经得到的有限有理数转为一个每秒FLOAT64斜率。|
|[`difference_reference`](#api-difference_reference)|按原值精确相减，再除以秒数，免去巨大相近整数的绝对值舍入。|
|[`fit_reference`](#api-fit_reference)|用局部时间、真实样本等权及补偿求和计算最小二乘斜率。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from fractions import Fraction
from math import frexp, fsum, ldexp
from .numeric import ScalarValue, _exact_float
from .types import QualityFlag as Q, SignalDType as D
```

</details>

<a id="api-_result"></a>
## `_result`

将已经得到的有限有理数转为一个每秒FLOAT64斜率。

```python
_result(exact)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`exact`|Fraction|是|无|位置或关键字。在参考核中按差量和秒数计算出的最终有理斜率，最后才舍入为float64。|

### 返回说明

ScalarValue，真溢出或下溢有独立原因。

### 异常说明

内存不足原样传播。

源码：[`src/chronaxis/core/rate_reference.py:14`](../../../src/chronaxis/core/rate_reference.py#L14)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-difference_reference"></a>
## `difference_reference`

按原值精确相减，再除以秒数，免去巨大相近整数的绝对值舍入。

```python
difference_reference(left, right, elapsed_ns)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`left`|[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)|是|无|位置或关键字。差分区间起点的已绑定数值及其质量，不用数组下标推断时间。|
|`right`|[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)|是|无|位置或关键字。差分区间终点的同类型数值；用其减去起点值。|
|`elapsed_ns`|int &#124; Fraction|是|无|位置或关键字。两个端点之间所选的实际或折算周期跨度，单位纳秒；合法差分必须为正。|

### 返回说明

FLOAT64 ScalarValue。

### 异常说明

内部调用需先校验模型。不能精确进入浮点的整数差量报PRECISION_LOSS。

源码：[`src/chronaxis/core/rate_reference.py:29`](../../../src/chronaxis/core/rate_reference.py#L29)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-fit_reference"></a>
## `fit_reference`

用局部时间、真实样本等权及补偿求和计算最小二乘斜率。

```python
fit_reference(positions, samples)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`positions`|Sequence[int &#124; Fraction]|是|无|位置或关键字。与真实样本一一对应的精确纳秒坐标；先相对首点平移，再进行窗口拟合。|
|`samples`|Sequence[[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)]|是|无|位置或关键字。按真实更新时间排列的同类型样本，拟合时每个测量点权重相同。|

### 返回说明

FLOAT64 ScalarValue。

### 异常说明

内部结构错误传播，数值失效转为质量。

源码：[`src/chronaxis/core/rate_reference.py:44`](../../../src/chronaxis/core/rate_reference.py#L44)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
