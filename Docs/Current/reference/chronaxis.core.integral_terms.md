# `chronaxis.core.integral_terms`

定义积分求和之前的各段面积。每段使用左端最近一次有效值乘以该段秒数，这种计算方式称为前值保持积分。面积按原时间顺序保存，另有有效标记；无效位置即使存了0，也不能当成测得的零。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)、[CalculationSeries](chronaxis.core.calculations.md#api-CalculationSeries)、[Interval](chronaxis.core.models.md#api-Interval)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[SourceRef](chronaxis.core.models.md#api-SourceRef)

## 对象导航

|对象|用途|
|---|---|
|[`IntegralFacts`](#api-IntegralFacts)|保存积分所用的时间范围、有效时长、缺失区间和样本数。它不保存最后的能量总和；这些字段用于解释总和覆盖了多少数据。|
|[`IntegralFacts.__post_init__`](#api-IntegralFacts-__post_init__)|检查积分记录中的时间、样本数和质量字段是否合法。例如有效时长不能为负，实际范围不能超过所请求的范围。|
|[`ReferenceIntegralTerms`](#api-ReferenceIntegralTerms)|保存标量参考的原序面积和显式有效掩码，不累计全窗口项。|
|[`ReferenceIntegralTerms.__post_init__`](#api-ReferenceIntegralTerms-__post_init__)|校验同长不可修改的数据列及有限面积，拒绝用无效非零占位。|
|[`require_valid_until`](#api-require_valid_until)|校验有限块的必要有效截止列。|
|[`require_integral_terms`](#api-require_integral_terms)|共享输入/单位/可表示时长门槛，不共享数值内核。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from math import isfinite
from .calculations import CalculationSeries, CalculationDefinition, calculation_unit
from .calculations_reference import require_calculation
from .models import Interval, SourceRef
from .types import QualityFlag as Q
from .validation import require_text
```

</details>

<a id="api-IntegralFacts"></a>
## `IntegralFacts`

保存积分所用的时间范围、有效时长、缺失区间和样本数。它不保存最后的能量总和；这些字段用于解释总和覆盖了多少数据。

```python
class IntegralFacts
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|原请求窗口及最终数据不全时的处理方式，不按块覆盖重写。|
|`actual_window`|[Interval](chronaxis.core.models.md#api-Interval) &#124; None|是|无|本块实际参与统计的时间范围，是请求范围与观测范围的交集。没有交集时为None，不把未观察到的时间补入结果。|
|`value_valid_duration_ns`|int|是|无|可核实面积时长，整数ns。|
|`valid_sample_count`|int|是|无|半开当前块内实际更新且可核实的样本数。|
|`value_unknown_ranges`|tuple[[Interval](chronaxis.core.models.md#api-Interval), ...]|是|无|数值无法用于本次计算的时间段元组，每段包含起点、不包含终点。缺失、失效或数值转换失败等原因另保存在quality字段。|
|`quality`|[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)|是|无|来源及精度/非有限/下溢等计算诊断。|
|`input_unit`|str|是|无|本次计算输入值的工程单位，例如功率为W。这里记录原输入单位，最终结果的输出单位另由spec指定。|
|`binding_identity`|str|是|无|产生这份数值输入的信号绑定标识。调用方用它检查各块是否来自同一次配置和输入，不能把不同绑定的块混在一起累计。|
|`source_refs`|tuple[[SourceRef](chronaxis.core.models.md#api-SourceRef), ...]|是|无|参与计算的数据来源及其位置，例如来源名、字段名和原记录位置。保留具体SourceRef子类，便于从结果追溯输入。|

源码：[`src/chronaxis/core/integral_terms.py:21`](../../../src/chronaxis/core/integral_terms.py#L21)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-IntegralFacts-__post_init__"></a>
### `IntegralFacts.__post_init__`

检查积分记录中的时间、样本数和质量字段是否合法。例如有效时长不能为负，实际范围不能超过所请求的范围。

```python
IntegralFacts.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

字段不是规定类型时抛TypeError；有效时长或范围与窗口矛盾时抛ValueError。

本函数直接报告的具体错误：

- `TypeError`：积分项事实需要integral CalculationDefinition。
- `TypeError`：积分项实际范围需要Interval或None。
- `ValueError`：积分项覆盖或样本数不合法。
- `ValueError`：积分项未知范围必须位于实际窗口。
- `TypeError`：积分项需要带有明确类型的质量与完整来源tuple。

源码：[`src/chronaxis/core/integral_terms.py:38`](../../../src/chronaxis/core/integral_terms.py#L38)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ReferenceIntegralTerms"></a>
## `ReferenceIntegralTerms`

保存标量参考的原序面积和显式有效掩码，不累计全窗口项。

```python
class ReferenceIntegralTerms
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`areas`|tuple[float, ...]|是|无|每个原区间的面积，未观察/无效位置为0存储占位。|
|`valid`|tuple[bool, ...]|是|无|只有True位置可参与后续数值归约。|
|`facts`|[IntegralFacts](chronaxis.core.integral_terms.md#api-IntegralFacts)|是|无|当前块覆盖/原请求/诊断，不是最终CalculationResult。|

源码：[`src/chronaxis/core/integral_terms.py:68`](../../../src/chronaxis/core/integral_terms.py#L68)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ReferenceIntegralTerms-__post_init__"></a>
### `ReferenceIntegralTerms.__post_init__`

校验同长不可修改的数据列及有限面积，拒绝用无效非零占位。

```python
ReferenceIntegralTerms.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError为列/掩码/面积错误。

本函数直接报告的具体错误：

- `TypeError`：参考积分项需要同长tuple及IntegralFacts。
- `ValueError`：参考积分面积需有限float，未知使用掩码及0存储。

源码：[`src/chronaxis/core/integral_terms.py:75`](../../../src/chronaxis/core/integral_terms.py#L75)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-require_valid_until"></a>
## `require_valid_until`

校验有限块的必要有效截止列。

```python
require_valid_until(times, valid_until_ns)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`times`|tuple[int, ...]|是|无|位置或关键字。本批实际纳秒时刻，按输入顺序排列，用于核对有效截止列长度及边界。|
|`valid_until_ns`|Sequence[int &#124; None] &#124; None|是|无|位置或关键字。每个值按真实时间计算的有效截止，单位纳秒；None沿原有效范围，不按固定周期延长旧值寿命。|

### 返回说明

None。

### 异常说明

类型/长度/范围错误。

源码：[`src/chronaxis/core/integral_terms.py:88`](../../../src/chronaxis/core/integral_terms.py#L88)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-require_integral_terms"></a>
## `require_integral_terms`

共享输入/单位/可表示时长门槛，不共享数值内核。

```python
require_integral_terms(series, spec, *, step_ns=None, valid_until_ns=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`series`|[CalculationSeries](chronaxis.core.calculations.md#api-CalculationSeries)|是|无|位置或关键字。当前计算窗口的数值片段和真实样本；有条件计算时还包含对应的TRUE、FALSE或UNKNOWN选择状态。|
|`spec`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|位置或关键字。当前指标请求，指定运算、窗口、结果单位及部分数据的处理方式。|
|`step_ns`|int &#124; None|否|None|仅关键字。所选固定或DBC周期，单位纳秒且大于0；None表示采用实际时间间隔，不生成第二套时间坐标。|
|`valid_until_ns`|Sequence[int &#124; None] &#124; None|否|None|仅关键字。每个值按真实时间计算的有效截止，单位纳秒；None沿原有效范围，不按固定周期延长旧值寿命。|

### 返回说明

返回None，不返回额外的计算值。

### 异常说明

类型/dtype/算子/条件/单位配置错误；OverflowError为int64不可表示跨度。

本函数直接报告的具体错误：

- `ValueError`：当前积分项只支持无选择条件的integral。
- `OverflowError`：积分区间时长不能超过正int64。

源码：[`src/chronaxis/core/integral_terms.py:98`](../../../src/chronaxis/core/integral_terms.py#L98)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
