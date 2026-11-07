# `chronaxis.core.conditional_integral_terms_reference`

逐段计算条件积分面积，供NumPy实现作结果对照。只有筛选条件为真且数值有效时才计算面积。无法精确转换的值、溢出及非零值下溢都会记录原因；条件未知不会被补成零。返回各段面积，最后的求和由后续模块完成。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ConditionalIntegralFacts](chronaxis.core.conditional_integral_terms.md#api-ConditionalIntegralFacts)、[Interval](chronaxis.core.models.md#api-Interval)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ReferenceConditionalIntegralTerms](chronaxis.core.conditional_integral_terms.md#api-ReferenceConditionalIntegralTerms)、[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)

## 对象导航

|对象|用途|
|---|---|
|[`compute_conditional_integral_terms_reference`](#api-compute_conditional_integral_terms_reference)|按时间顺序计算各段面积，并分别统计数值有效时长和条件已知时长；面积仍使用输入单位。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from math import isfinite
from .conditional_integral_terms import ConditionalIntegralFacts, ReferenceConditionalIntegralTerms, require_conditional_integral_terms
from .calculations import merge_ranges
from .models import Interval
from .numeric import ScalarValue, to_float_reference
from .types import QualityFlag as Q
from .record_intervals import clipped_record_seconds
```

</details>

<a id="api-compute_conditional_integral_terms_reference"></a>
## `compute_conditional_integral_terms_reference`

按时间顺序计算各段面积，并分别统计数值有效时长和条件已知时长；面积仍使用输入单位。

```python
compute_conditional_integral_terms_reference(series, spec, *, step_ns=None, valid_until_ns=None, condition_valid_until_ns=None, retain_unknown_ranges=True)
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

ReferenceConditionalIntegralTerms；面积为输入单位乘秒，无效槽位0配False。

### 异常说明

输入、单位、时间与分配错误传播；精度、面积溢出/下溢写入质量及未知。

源码：[`src/chronaxis/core/conditional_integral_terms_reference.py:20`](../../../src/chronaxis/core/conditional_integral_terms_reference.py#L20)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
