# `chronaxis.core.rate_numpy`

用原dtype列、局部时间和中心化NumPy归约计算差分与等权拟合。

仅运行当前窗口，整数先在无符号幅度列计算精确差，再按IEEE表示检查提升。
拟合使用整列点积，最终只对两个标量归约结果还原倍率、秒与输出质量。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)

## 对象导航

|对象|用途|
|---|---|
|[`_relative_column`](#api-_relative_column)|将已知数值打包为相对首样本的浮点列，给出纵轴缩放的二进制指数。|
|[`_restore`](#api-_restore)|还原局部纵轴数量级与所选纳秒跨度，不在中间乘法中溢出。|
|[`difference_numpy`](#api-difference_numpy)|以原dtype两点列求差，恢复为所选周期或实际秒数上的导数。|
|[`fit_numpy`](#api-fit_numpy)|将实际或周期横轴先局部化，用整列中心积求等权回归斜率。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .numeric import ScalarValue
from .numeric_numpy import DTYPES, _output, to_float_numpy
from .types import QualityFlag as Q, SignalDType as D
```

</details>

<a id="api-_relative_column"></a>
## `_relative_column`

将已知数值打包为相对首样本的浮点列，给出纵轴缩放的二进制指数。

```python
_relative_column(samples)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`samples`|Sequence[[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)]|是|无|位置或关键字。按真实更新时间排列的同类型样本，拟合时每个测量点权重相同。|

### 返回说明

(相对列,指数,质量)。

### 异常说明

内存分配或内部结构错误传播。整数差转float不精确时返回精度质量。

源码：[`src/chronaxis/core/rate_numpy.py:13`](../../../src/chronaxis/core/rate_numpy.py#L13)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_restore"></a>
## `_restore`

还原局部纵轴数量级与所选纳秒跨度，不在中间乘法中溢出。

```python
_restore(numerator, denominator, exponent, elapsed_ns)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`numerator`|float &#124; numpy.float64|是|无|位置或关键字。归一化后的变化量或中心积，是恢复斜率时的分子。|
|`denominator`|float &#124; numpy.float64|是|无|位置或关键字。差分时为1，拟合时是归一化横坐标的平方和。|
|`exponent`|int|是|无|位置或关键字。先前对纵轴用2的幂缩放的指数，最后恢复原数值尺度。|
|`elapsed_ns`|int &#124; Fraction|是|无|位置或关键字。两个端点之间所选的实际或折算周期跨度，单位纳秒；合法差分必须为正。|

### 返回说明

FLOAT64 ScalarValue。

### 异常说明

不可表示的最终数值以质量标识。

源码：[`src/chronaxis/core/rate_numpy.py:37`](../../../src/chronaxis/core/rate_numpy.py#L37)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-difference_numpy"></a>
## `difference_numpy`

以原dtype两点列求差，恢复为所选周期或实际秒数上的导数。

```python
difference_numpy(left, right, elapsed_ns)
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

输入结构和分配错误传播。

源码：[`src/chronaxis/core/rate_numpy.py:60`](../../../src/chronaxis/core/rate_numpy.py#L60)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-fit_numpy"></a>
## `fit_numpy`

将实际或周期横轴先局部化，用整列中心积求等权回归斜率。

```python
fit_numpy(positions, samples)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`positions`|Sequence[int &#124; Fraction]|是|无|位置或关键字。与真实样本一一对应的精确纳秒坐标；先相对首点平移，再进行窗口拟合。|
|`samples`|Sequence[[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)]|是|无|位置或关键字。按真实更新时间排列的同类型样本，拟合时每个测量点权重相同。|

### 返回说明

FLOAT64 ScalarValue。

### 异常说明

结构和空间错误传播。

源码：[`src/chronaxis/core/rate_numpy.py:72`](../../../src/chronaxis/core/rate_numpy.py#L72)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
