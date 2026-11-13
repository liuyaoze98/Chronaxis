# `chronaxis.core.integral_terms_reference`

逐段计算当前区间时沿用的最近值保持积分面积，供NumPy实现对照。每段先确定落在请求范围内的实际时长，再乘以左端有效值。未知数据不会补成零；无法精确转成浮点数、面积溢出或下溢时记录原因。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[IntegralFacts](chronaxis.core.integral_terms.md#api-IntegralFacts)、[Interval](chronaxis.core.models.md#api-Interval)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ReferenceIntegralTerms](chronaxis.core.integral_terms.md#api-ReferenceIntegralTerms)、[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)

## 对象导航

|对象|用途|
|---|---|
|[`compute_integral_terms_reference`](#api-compute_integral_terms_reference)|逐区间计算原序未转换面积与明确有效掩码。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from math import isfinite
from .integral_terms import IntegralFacts, ReferenceIntegralTerms, require_integral_terms
from .calculations import merge_ranges
from .models import Interval
from .numeric import ScalarValue, to_float_reference
from .types import QualityFlag as Q
from .record_intervals import clipped_record_seconds
```

</details>

<a id="api-compute_integral_terms_reference"></a>
## `compute_integral_terms_reference`

逐区间计算原序未转换面积与明确有效掩码。

```python
compute_integral_terms_reference(series, spec, *, step_ns=None, retain_unknown_ranges=True, valid_until_ns=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`series`|CalculationSeries|是|无|位置或关键字。series为有限CalculationSeries|
|`spec`|CalculationDefinition|是|无|位置或关键字。spec为无条件integral CalculationDefinition。|
|`step_ns`|int &#124; None|否|None|仅关键字。所选固定或DBC周期，单位纳秒且大于0；None表示采用实际时间间隔，不生成第二套时间坐标。|
|`retain_unknown_ranges`|bool|否|True|仅关键字。是否收集未知区间列表；关闭时仍计算未知对数值和状态的影响，但不建立该区间明细。|
|`valid_until_ns`|Sequence[int &#124; None] &#124; None|否|None|仅关键字。每个值按真实时间计算的有效截止，单位纳秒；None沿原有效范围，不按固定周期延长旧值寿命。|

### 返回说明

ReferenceIntegralTerms，areas/valid长度N-1；面积单位为input_unit乘秒。

### 异常说明

输入/单位/时间/分配错误传播；数值精度/溢出/下溢写入质量并使面积无效。

源码：[`src/chronaxis/core/integral_terms_reference.py:20`](../../../src/chronaxis/core/integral_terms_reference.py#L20)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
