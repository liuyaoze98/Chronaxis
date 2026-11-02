# chronaxis.core.conditional_integral_terms_numpy

用NumPy同时计算一组时间段的条件积分面积。先按请求范围裁剪时间段，再对条件为真且数值有效的位置计算“值×持续秒数”。返回面积数组、有效标记和覆盖时长；面积尚未相加，也没有换算最终单位。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ConditionalIntegralFacts](chronaxis.core.conditional_integral_terms.md#api-ConditionalIntegralFacts)、[Interval](chronaxis.core.models.md#api-Interval)、[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)

## 对象导航

|对象|用途|
|---|---|
|[`NumpyConditionalIntegralTerms`](#api-NumpyConditionalIntegralTerms)|保存原序只读面积与明确掩码，不借用可写输入或隐式掩码数组。|
|[`NumpyConditionalIntegralTerms.__post_init__`](#api-NumpyConditionalIntegralTerms-__post_init__)|检查面积与有效标记是否为等长一维只读数组，并核对面积数值和覆盖统计。|
|[`compute_conditional_integral_terms_numpy`](#api-compute_conditional_integral_terms_numpy)|按真实数组掩码生成面积，独立归约值、条件和选择覆盖。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from .conditional_integral_terms import ConditionalIntegralFacts, require_conditional_integral_terms
from .calculations import merge_ranges
from .models import Interval
from .numeric_numpy import DTYPES, NumericArray, to_float_numpy
from .types import QualityFlag as Q
```

</details>

<a id="api-NumpyConditionalIntegralTerms"></a>
## `NumpyConditionalIntegralTerms`

保存原序只读面积与明确掩码，不借用可写输入或隐式掩码数组。

```python
class NumpyConditionalIntegralTerms
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`areas`|np.ndarray|是|无|float64形状(N-1,)，未转换的输入单位乘秒。|
|`valid`|np.ndarray|是|无|bool形状(N-1,)，仅TRUE且正常面积可归约。|
|`facts`|[ConditionalIntegralFacts](chronaxis.core.conditional_integral_terms.md#api-ConditionalIntegralFacts)|是|无|当前块双覆盖、样本与来源，不是全窗结果。|

源码：[`src/chronaxis/core/conditional_integral_terms_numpy.py:21`](../../../src/chronaxis/core/conditional_integral_terms_numpy.py#L21)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-NumpyConditionalIntegralTerms-__post_init__"></a>
### `NumpyConditionalIntegralTerms.__post_init__`

检查面积与有效标记是否为等长一维只读数组，并核对面积数值和覆盖统计。

```python
NumpyConditionalIntegralTerms.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError为类型、形状、可写或占位错误。

本函数直接报告的具体错误：

- `TypeError`：数组条件积分项需要同长一维float64/bool及ConditionalIntegralFacts。
- `ValueError`：数组条件积分项必须只读且有限，无效位置只能0存储。

源码：[`src/chronaxis/core/conditional_integral_terms_numpy.py:28`](../../../src/chronaxis/core/conditional_integral_terms_numpy.py#L28)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-compute_conditional_integral_terms_numpy"></a>
## `compute_conditional_integral_terms_numpy`

按真实数组掩码生成面积，独立归约值、条件和选择覆盖。

```python
compute_conditional_integral_terms_numpy(series, spec, *, step_ns=None, valid_until_ns=None, condition_valid_until_ns=None, retain_unknown_ranges=True)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`series`|CalculationSeries|是|无|位置或关键字。当前计算窗口的数值片段和真实样本；有条件计算时还包含对应的TRUE、FALSE或UNKNOWN选择状态。|
|`spec`|CalculationDefinition|是|无|位置或关键字。当前指标请求，指定运算、窗口、结果单位及部分数据的处理方式。|
|`step_ns`|int &#124; None|否|None|仅关键字。所选固定或DBC周期，单位纳秒且大于0；None表示采用实际时间间隔，不生成第二套时间坐标。|
|`valid_until_ns`|Sequence[int &#124; None] &#124; None|否|None|仅关键字。每个值按真实时间计算的有效截止，单位纳秒；None沿原有效范围，不按固定周期延长旧值寿命。|
|`condition_valid_until_ns`|Sequence[int &#124; None] &#124; None|否|None|仅关键字。各筛选条件的真实有效截止，单位纳秒；条件未知不能当作False或补零。|
|`retain_unknown_ranges`|bool|否|True|仅关键字。是否收集未知区间列表；关闭时仍计算未知对数值和状态的影响，但不建立该区间明细。|

### 返回说明

NumpyConditionalIntegralTerms；只读面积/掩码形状N-1，临时列形状N或N-1。

### 异常说明

输入、单位、时间和分配错误传播；浮点故障写质量并使对应值/面积失效。

源码：[`src/chronaxis/core/conditional_integral_terms_numpy.py:44`](../../../src/chronaxis/core/conditional_integral_terms_numpy.py#L44)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
