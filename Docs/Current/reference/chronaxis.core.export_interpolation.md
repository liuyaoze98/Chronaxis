# `chronaxis.core.export_interpolation`

计算离线导出的线性值；不改变分析中的向后保持、事件或积分语义。

调用方已确定相邻有效端点、范围及最大间隔。参考实现用精确有理数计算后转
float64；NumPy实现以一维longdouble数组计算后转float64，计算内核独立。
整数纳秒先作精确相对差，避免把很大的绝对时间直接转浮点。输出为估计值，
不声称恢复真实观测；无文件、预算或全局状态。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`linear_reference`](#api-linear_reference)|独立标量线性参考。|
|[`linear_numpy`](#api-linear_numpy)|独立数组线性计算。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from fractions import Fraction
from math import isfinite
```

</details>

<a id="api-linear_reference"></a>
## `linear_reference`

独立标量线性参考。

```python
linear_reference(times, left_ns, right_ns, left_value, right_value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`times`|int|是|无|位置或关键字。一维目标时间序列，整数纳秒；每个点必须在两端点之间。|
|`left_ns`|int|是|无|位置或关键字。左端实测点的整数纳秒时间。|
|`right_ns`|int|是|无|位置或关键字。右端实测点的整数纳秒时间，必须严格晚于left_ns。|
|`left_value`|int &#124; float|是|无|位置或关键字。左端已解码的有限物理数值；两端单位相同，按目标时刻在两端之间的位置做线性插值。|
|`right_value`|int &#124; float|是|无|位置或关键字。右端已解码的有限物理数值；两端单位相同，按目标时刻在两端之间的位置做线性插值。|

### 返回说明

float tuple。

### 异常说明

时间/数值非法或结果不有限；只接受严格位于两个端点之间的目标。

本函数直接报告的具体错误：

- `ValueError`：插值需要有效有序两端与内部目标。
- `ValueError`：插值结果非有限。

源码：[`src/chronaxis/core/export_interpolation.py:14`](../../../src/chronaxis/core/export_interpolation.py#L14)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-linear_numpy"></a>
## `linear_numpy`

独立数组线性计算。

```python
linear_numpy(times, left_ns, right_ns, left_value, right_value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`times`|int|是|无|位置或关键字。一维目标时间序列，整数纳秒；每个点必须在两端点之间。|
|`left_ns`|int|是|无|位置或关键字。左端实测点的整数纳秒时间。|
|`right_ns`|int|是|无|位置或关键字。右端实测点的整数纳秒时间，必须严格晚于left_ns。|
|`left_value`|int &#124; float|是|无|位置或关键字。左端已解码的有限物理数值；两端单位相同，按目标时刻在两端之间的位置做线性插值。|
|`right_value`|int &#124; float|是|无|位置或关键字。右端已解码的有限物理数值；两端单位相同，按目标时刻在两端之间的位置做线性插值。|

### 返回说明

shape(N,) float64 ndarray。

### 异常说明

时间/值非法或结果不有限；数组副本限当前有限块，不使用object数组。

本函数直接报告的具体错误：

- `ValueError`：插值需要有效有序两端与内部目标。
- `ValueError`：插值结果非有限。

源码：[`src/chronaxis/core/export_interpolation.py:29`](../../../src/chronaxis/core/export_interpolation.py#L29)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
