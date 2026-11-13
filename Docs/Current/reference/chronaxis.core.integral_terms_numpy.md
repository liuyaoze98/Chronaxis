# `chronaxis.core.integral_terms_numpy`

用NumPy计算每个时间段的前值保持积分面积。先裁剪时间范围，再用左端有效值乘以实际秒数；返回面积数组、有效标记、覆盖时长和缺失原因。这里不先求各块总和，也不换算最终单位。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[IntegralFacts](chronaxis.core.integral_terms.md#api-IntegralFacts)、[Interval](chronaxis.core.models.md#api-Interval)、[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)

## 对象导航

|对象|用途|
|---|---|
|[`NumpyIntegralTerms`](#api-NumpyIntegralTerms)|持有只读面积及显式有效掩码，数组保持原区间顺序。|
|[`NumpyIntegralTerms.__post_init__`](#api-NumpyIntegralTerms-__post_init__)|检查真实一维同长只读数组，不接受object或非有限占位。|
|[`compute_integral_terms_numpy`](#api-compute_integral_terms_numpy)|批量生成未转换面积与有效掩码，独立计算覆盖和样本数。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from .integral_terms import IntegralFacts, require_integral_terms
from .calculations import merge_ranges
from .models import Interval
from .numeric_numpy import DTYPES, NumericArray, to_float_numpy
from .types import QualityFlag as Q
```

</details>

<a id="api-NumpyIntegralTerms"></a>
## `NumpyIntegralTerms`

持有只读面积及显式有效掩码，数组保持原区间顺序。

```python
class NumpyIntegralTerms
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`areas`|np.ndarray|是|无|float64形状(N-1,)，无效位置0只是存储。|
|`valid`|np.ndarray|是|无|bool形状(N-1,)，True位置可归约。|
|`facts`|[IntegralFacts](chronaxis.core.integral_terms.md#api-IntegralFacts)|是|无|当前块原请求/覆盖/诊断和完整真实来源。|

源码：[`src/chronaxis/core/integral_terms_numpy.py:21`](../../../src/chronaxis/core/integral_terms_numpy.py#L21)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-NumpyIntegralTerms-__post_init__"></a>
### `NumpyIntegralTerms.__post_init__`

检查真实一维同长只读数组，不接受object或非有限占位。

```python
NumpyIntegralTerms.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError为数组或事实错误。

本函数直接报告的具体错误：

- `TypeError`：数组积分项需要同长一维float64/bool及IntegralFacts。
- `ValueError`：数组积分项必须只读且有限，无效位置仅0存储。

源码：[`src/chronaxis/core/integral_terms_numpy.py:28`](../../../src/chronaxis/core/integral_terms_numpy.py#L28)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-compute_integral_terms_numpy"></a>
## `compute_integral_terms_numpy`

批量生成未转换面积与有效掩码，独立计算覆盖和样本数。

```python
compute_integral_terms_numpy(series, spec, *, step_ns=None, retain_unknown_ranges=True, valid_until_ns=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`series`|CalculationSeries|是|无|位置或关键字。当前计算窗口的数值片段和真实样本；有条件计算时还包含对应的TRUE、FALSE或UNKNOWN选择状态。|
|`spec`|CalculationDefinition|是|无|位置或关键字。当前指标请求，指定运算、窗口、结果单位及部分数据的处理方式。|
|`step_ns`|int &#124; None|否|None|仅关键字。所选固定或DBC周期，单位纳秒且大于0；None表示采用实际时间间隔，不生成第二套时间坐标。|
|`retain_unknown_ranges`|bool|否|True|仅关键字。是否收集未知区间列表；关闭时仍计算未知对数值和状态的影响，但不建立该区间明细。|
|`valid_until_ns`|Sequence[int &#124; None] &#124; None|否|None|仅关键字。每个值按真实时间计算的有效截止，单位纳秒；None沿原有效范围，不按固定周期延长旧值寿命。|

### 返回说明

NumpyIntegralTerms；实际临时/输出列为N或N-1，面积单位input_unit乘秒。

### 异常说明

输入/单位/时间/分配错误传播；浮点故障追加质量并使对应项无效。

源码：[`src/chronaxis/core/integral_terms_numpy.py:44`](../../../src/chronaxis/core/integral_terms_numpy.py#L44)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
