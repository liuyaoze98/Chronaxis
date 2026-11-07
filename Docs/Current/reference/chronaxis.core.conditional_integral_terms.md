# `chronaxis.core.conditional_integral_terms`

定义条件积分的中间结果。每个时间段保存“当前值×持续秒数”得到的面积，并另存数值是否有效、筛选条件是否已知。条件为假时不计算该段面积；条件未知也不能当成假。面积尚未求和，也尚未转换到最终输出单位。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)、[CalculationSeries](chronaxis.core.calculations.md#api-CalculationSeries)、[D](chronaxis.core.types.md#api-SignalDType)、[Interval](chronaxis.core.models.md#api-Interval)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[SourceRef](chronaxis.core.models.md#api-SourceRef)

## 对象导航

|对象|用途|
|---|---|
|[`_unknown_duration`](#api-_unknown_duration)|校验一种未知范围完整有序、不重叠且不越过实际窗口。|
|[`ConditionalIntegralFacts`](#api-ConditionalIntegralFacts)|保存当前块原请求与完整覆盖，值缺失和条件未知分别说明。|
|[`ConditionalIntegralFacts.__post_init__`](#api-ConditionalIntegralFacts-__post_init__)|检查数值有效/未知时长、条件已知/未知时长是否各自覆盖实际范围，并核对选中与未选中时长。字段互相矛盾时直接报错。|
|[`ReferenceConditionalIntegralTerms`](#api-ReferenceConditionalIntegralTerms)|保存有限原序面积，无效数据位置暂存的值0只能与False掩码一起解释。|
|[`ReferenceConditionalIntegralTerms.__post_init__`](#api-ReferenceConditionalIntegralTerms-__post_init__)|检查每段积分面积及其有效标记是否一一对应。每项面积必须是有限数；标记无效的位置必须用0占位，不能在无效位置混入会被误加到总量的数值。|
|[`require_conditional_integral_terms`](#api-require_conditional_integral_terms)|校验带有明确类型的数值、BOOL条件、明确积分单位及可表示正跨度。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from math import isfinite
from .calculations import CalculationDefinition, CalculationSeries, calculation_unit
from .models import Interval, SourceRef
from .types import QualityFlag as Q, SignalDType as D
from .validation import require_text
```

</details>

<a id="api-_unknown_duration"></a>
## `_unknown_duration`

校验一种未知范围完整有序、不重叠且不越过实际窗口。

```python
_unknown_duration(ranges, actual)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`ranges`|tuple[[Interval](chronaxis.core.models.md#api-Interval), ...]|是|无|位置或关键字。按时间排列且已合并的未知区间，用于计算实际观测范围内的未知时长。|
|`actual`|[Interval](chronaxis.core.models.md#api-Interval) &#124; None|是|无|位置或关键字。请求范围与实际观测范围的交集；没有交集时为None。|

### 返回说明

原生int纳秒未知总时长。

### 异常说明

TypeError/ValueError为结构或不可能范围。

本函数直接报告的具体错误：

- `TypeError`：条件积分未知范围需要tuple。
- `ValueError`：条件积分未知范围必须有序、不重叠且在实际窗口内。

源码：[`src/chronaxis/core/conditional_integral_terms.py:20`](../../../src/chronaxis/core/conditional_integral_terms.py#L20)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ConditionalIntegralFacts"></a>
## `ConditionalIntegralFacts`

保存当前块原请求与完整覆盖，值缺失和条件未知分别说明。

known包含TRUE和FALSE；selected只计TRUE且面积可核实的时长。
selected_value_unknown只计TRUE而值/面积不可核实的时长，不混入条件UNKNOWN。
FALSE不乘面积，原值的类型和精度检查仍保留在值覆盖及质量中。

```python
class ConditionalIntegralFacts
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|原integral请求、scope和数据不全时的处理方式。|
|`actual_window`|[Interval](chronaxis.core.models.md#api-Interval) &#124; None|是|无|本块实际参与统计的时间范围，是请求范围与观测范围的交集。没有交集时为None，不把未观察到的时间补入结果。|
|`value_valid_duration_ns`|int|是|无|原值经积分可用性检查后的有效时长。|
|`condition_known_duration_ns`|int|是|无|筛选条件能够确定为真或假的总时长，单位为纳秒。条件已知为假也计入已知时长；UNKNOWN不计入。|
|`selected_duration_ns`|int|是|无|TRUE且值/面积可核实的时长。|
|`selected_value_unknown_duration_ns`|int|是|无|筛选条件为真、但数值无法使用的时长，单位为纳秒。它与筛选条件本身未知的时长分开统计。|
|`false_duration_ns`|int|是|无|已知FALSE时长，只有完整窗才证明没有数据满足筛选条件零。|
|`valid_sample_count`|int|是|无|半开当前块内原值真实更新且有效/TRUE的数量。|
|`value_unknown_ranges`|tuple[[Interval](chronaxis.core.models.md#api-Interval), ...]|是|无|数值无法用于本次计算的时间段元组，每段包含起点、不包含终点。缺失、失效或数值转换失败等原因另保存在quality字段。|
|`condition_unknown_ranges`|tuple[[Interval](chronaxis.core.models.md#api-Interval), ...]|是|无|筛选条件无法判断真假的时间段列表。它独立于数值是否有效，不应当作条件为假。|
|`quality`|[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)|是|无|输入、依赖和精度/面积故障原因完整OR。|
|`input_unit`|str|是|无|本次计算输入值的工程单位，例如功率为W。这里记录原输入单位，最终结果的输出单位另由spec指定。|
|`binding_identity`|str|是|无|产生这份数值输入的信号绑定标识。调用方用它检查各块是否来自同一次配置和输入，不能把不同绑定的块混在一起累计。|
|`source_refs`|tuple[[SourceRef](chronaxis.core.models.md#api-SourceRef), ...]|是|无|参与计算的数据来源及其位置，例如来源名、字段名和原记录位置。保留具体SourceRef子类，便于从结果追溯输入。|
|`ranges_retained`|bool|否|True|仅明确请求时保留未知范围；False不能用于完整明细归约。|

源码：[`src/chronaxis/core/conditional_integral_terms.py:39`](../../../src/chronaxis/core/conditional_integral_terms.py#L39)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ConditionalIntegralFacts-__post_init__"></a>
### `ConditionalIntegralFacts.__post_init__`

检查数值有效/未知时长、条件已知/未知时长是否各自覆盖实际范围，并核对选中与未选中时长。字段互相矛盾时直接报错。

```python
ConditionalIntegralFacts.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError为类型、覆盖或未知几何错误。

本函数直接报告的具体错误：

- `TypeError`：条件积分事实需要integral CalculationDefinition。
- `TypeError`：条件积分实际范围需要Interval或None。
- `ValueError`：条件积分实际范围越过原请求。
- `ValueError`：条件积分覆盖时长需要实际跨度内的非负原生int。
- `ValueError`：条件积分样本、选择、FALSE与已知时长矛盾。
- `ValueError`：条件积分值有效与未知未完整划分实际窗口。
- `ValueError`：条件积分已知与条件未知未完整划分实际窗口。
- `TypeError`：条件积分事实需要带有明确类型的质量和完整来源tuple。

源码：[`src/chronaxis/core/conditional_integral_terms.py:63`](../../../src/chronaxis/core/conditional_integral_terms.py#L63)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ReferenceConditionalIntegralTerms"></a>
## `ReferenceConditionalIntegralTerms`

保存有限原序面积，无效数据位置暂存的值0只能与False掩码一起解释。

```python
class ReferenceConditionalIntegralTerms
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`areas`|tuple[float, ...]|是|无|形状N-1的原序有限float面积，未换最终单位。|
|`valid`|tuple[bool, ...]|是|无|只有TRUE选择且正常面积为True。|
|`facts`|[ConditionalIntegralFacts](chronaxis.core.conditional_integral_terms.md#api-ConditionalIntegralFacts)|是|无|当前块覆盖与完整定位，不是整窗最终状态。|

源码：[`src/chronaxis/core/conditional_integral_terms.py:104`](../../../src/chronaxis/core/conditional_integral_terms.py#L104)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ReferenceConditionalIntegralTerms-__post_init__"></a>
### `ReferenceConditionalIntegralTerms.__post_init__`

检查每段积分面积及其有效标记是否一一对应。每项面积必须是有限数；标记无效的位置必须用0占位，不能在无效位置混入会被误加到总量的数值。

```python
ReferenceConditionalIntegralTerms.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError为列结构、面积或事实类型。

本函数直接报告的具体错误：

- `TypeError`：参考条件积分项需要同长tuple及ConditionalIntegralFacts。
- `ValueError`：条件积分面积需有限float/bool，无效位置只能存0。

源码：[`src/chronaxis/core/conditional_integral_terms.py:111`](../../../src/chronaxis/core/conditional_integral_terms.py#L111)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-require_conditional_integral_terms"></a>
## `require_conditional_integral_terms`

校验带有明确类型的数值、BOOL条件、明确积分单位及可表示正跨度。

```python
require_conditional_integral_terms(series, spec, *, step_ns=None, valid_until_ns=None, condition_valid_until_ns=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`series`|[CalculationSeries](chronaxis.core.calculations.md#api-CalculationSeries)|是|无|位置或关键字。当前计算窗口的数值片段和真实样本；有条件计算时还包含对应的TRUE、FALSE或UNKNOWN选择状态。|
|`spec`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|位置或关键字。当前指标请求，指定运算、窗口、结果单位及部分数据的处理方式。|
|`step_ns`|int &#124; None|否|None|仅关键字。所选固定或DBC周期，单位纳秒且大于0；None表示采用实际时间间隔，不生成第二套时间坐标。|
|`valid_until_ns`|Sequence[int &#124; None] &#124; None|否|None|仅关键字。每个值按真实时间计算的有效截止，单位纳秒；None沿原有效范围，不按固定周期延长旧值寿命。|
|`condition_valid_until_ns`|Sequence[int &#124; None] &#124; None|否|None|仅关键字。各筛选条件的真实有效截止，单位纳秒；条件未知不能当作False或补零。|

### 返回说明

返回None，不返回额外的计算值。

### 异常说明

TypeError/ValueError/OverflowError为模型、能力、单位或时间错误。

本函数直接报告的具体错误：

- `TypeError`：条件积分需要CalculationSeries和CalculationDefinition。
- `ValueError`：条件积分只支持数值integral及显式BOOL选择条件。
- `OverflowError`：条件积分正交集跨度超过int64。

源码：[`src/chronaxis/core/conditional_integral_terms.py:124`](../../../src/chronaxis/core/conditional_integral_terms.py#L124)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
