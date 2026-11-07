# `chronaxis.core.sample_reduction`

定义按真实样本计算最小值、最大值和算术平均值时使用的数据对象。样本数来自实际更新，不把一个值保持了多少时间段当成多个样本。数值与筛选条件的缺失时间分别保存；本模块只检查数据，不执行统计。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)、[CalculationSeries](chronaxis.core.calculations.md#api-CalculationSeries)、[D](chronaxis.core.types.md#api-SignalDType)、[Interval](chronaxis.core.models.md#api-Interval)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[SourceRef](chronaxis.core.models.md#api-SourceRef)

## 对象导航

|对象|用途|
|---|---|
|[`_unknown_duration`](#api-_unknown_duration)|校验一种未知范围并精确累计纳秒，不用总长度掩盖重复位置。|
|[`SampleCalculationFacts`](#api-SampleCalculationFacts)|保存有限块双覆盖与真实选中样本，样本数不代替区间数或时长。|
|[`SampleCalculationFacts.__post_init__`](#api-SampleCalculationFacts-__post_init__)|检查数值和筛选条件各自的有效/未知时长、选中范围以及字段类型；矛盾数据会报错。|
|[`SampleReductionResult`](#api-SampleReductionResult)|保存最终单位数值与真实样本数，不复用时间统计的区间项数语义。|
|[`SampleReductionResult.__post_init__`](#api-SampleReductionResult-__post_init__)|拒绝样本数、正常数值和失败状态之间的矛盾。|
|[`require_sample_config`](#api-require_sample_config)|校验三samples能力、数值dtype与明确单位，不计算样本。|
|[`require_sample_series`](#api-require_sample_series)|核对有限输入unit/dtype及精确交集，保留可选BOOL条件。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .moments import SAMPLE_MOMENTS
from .quantiles import SAMPLE_QUANTILES
from dataclasses import dataclass
from math import isfinite
from .integral_sum import require_partial_limit
from .calculations import CalculationSeries, CalculationDefinition, calculation_conversion
from .models import Interval, SourceRef
from .types import QualityFlag as Q, SignalDType as D
from .validation import require_text
```

</details>

<a id="api-_unknown_duration"></a>
## `_unknown_duration`

校验一种未知范围并精确累计纳秒，不用总长度掩盖重复位置。

```python
_unknown_duration(ranges, actual)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`ranges`|tuple|是|无|位置或关键字。ranges为冻结正Interval tuple|
|`actual`|[Interval](chronaxis.core.models.md#api-Interval) &#124; None|是|无|位置或关键字。请求范围与实际观测范围的交集；无交集时为None，未知时长按没有观测处理。|

### 返回说明

原生int未知总时长。

### 异常说明

TypeError/ValueError为类型、反序、重叠或越界。

本函数直接报告的具体错误：

- `TypeError`：样本事实未知范围需要tuple。
- `ValueError`：样本未知范围必须有序、不重叠且在实际窗口内。

源码：[`src/chronaxis/core/sample_reduction.py:22`](../../../src/chronaxis/core/sample_reduction.py#L22)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-SampleCalculationFacts"></a>
## `SampleCalculationFacts`

保存有限块双覆盖与真实选中样本，样本数不代替区间数或时长。

selected只计条件TRUE且数值可用的正时长，selected_value_unknown只计TRUE值未知。
无条件known等于实际跨度、false为0；mean精度失败属于值未知，数值累计失败不改事实。

```python
class SampleCalculationFacts
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|原samples请求、scope与覆盖政策。|
|`actual_window`|[Interval](chronaxis.core.models.md#api-Interval) &#124; None|是|无|本块实际参与统计的时间范围，是请求范围与观测范围的交集。没有交集时为None，不把未观察到的时间补入结果。|
|`value_valid_duration_ns`|int|是|无|通过本算子值门槛的有效纳秒。|
|`condition_known_duration_ns`|int|是|无|筛选条件能够确定为真或假的总时长，单位为纳秒。条件已知为假也计入已知时长；UNKNOWN不计入。|
|`selected_duration_ns`|int|是|无|条件TRUE且值有效的保持纳秒，不是样本分母。|
|`selected_value_unknown_duration_ns`|int|是|无|筛选条件为真、但数值无法使用的时长，单位为纳秒。它与筛选条件本身未知的时长分开统计。|
|`false_duration_ns`|int|是|无|明确FALSE纳秒，不包含条件UNKNOWN。|
|`valid_sample_count`|int|是|无|半开窗口中有效/TRUE的原值真实更新。|
|`value_unknown_ranges`|tuple[[Interval](chronaxis.core.models.md#api-Interval), ...]|是|无|数值无法用于本次计算的时间段元组，每段包含起点、不包含终点。缺失、失效或数值转换失败等原因另保存在quality字段。|
|`condition_unknown_ranges`|tuple[[Interval](chronaxis.core.models.md#api-Interval), ...]|是|无|筛选条件无法判断真假的时间段列表。它独立于数值是否有效，不应当作条件为假。|
|`quality`|[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)|是|无|输入、精度与依赖原因，不含归约数值故障。|
|`input_unit`|str|是|无|本次计算输入值的工程单位，例如功率为W。这里记录原输入单位，最终结果的输出单位另由spec指定。|
|`dtype`|[D](chronaxis.core.types.md#api-SignalDType)|是|无|SignalDType枚举成员：INT64是有符号64位整数，UINT64是无符号64位整数，FLOAT64是双精度浮点，BOOL是真/假，ENUM是预先声明的状态标签。这里传枚举成员，不传字符串；当前运算支持哪些类型仍见本对象的约束。|
|`binding_identity`|str|是|无|产生这份数值输入的信号绑定标识。调用方用它检查各块是否来自同一次配置和输入，不能把不同绑定的块混在一起累计。|
|`source_refs`|tuple[[SourceRef](chronaxis.core.models.md#api-SourceRef), ...]|是|无|参与计算的数据来源及其位置，例如来源名、字段名和原记录位置。保留具体SourceRef子类，便于从结果追溯输入。|

源码：[`src/chronaxis/core/sample_reduction.py:41`](../../../src/chronaxis/core/sample_reduction.py#L41)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-SampleCalculationFacts-__post_init__"></a>
### `SampleCalculationFacts.__post_init__`

检查数值和筛选条件各自的有效/未知时长、选中范围以及字段类型；矛盾数据会报错。

```python
SampleCalculationFacts.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError为配置、覆盖、类型或几何矛盾。

本函数直接报告的具体错误：

- `TypeError`：样本实际范围需要Interval或None。
- `ValueError`：样本事实实际范围超出原请求。
- `ValueError`：样本事实计数、选择与双覆盖交集矛盾。
- `ValueError`：样本值有效与未知未完整划分实际窗口。
- `ValueError`：样本条件已知与未知未完整划分实际窗口。
- `TypeError`：样本事实需要带有明确类型的质量和完整来源tuple。

源码：[`src/chronaxis/core/sample_reduction.py:64`](../../../src/chronaxis/core/sample_reduction.py#L64)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-SampleReductionResult"></a>
## `SampleReductionResult`

保存最终单位数值与真实样本数，不复用时间统计的区间项数语义。

极值可保留精确int，均值为float；有效零、无样本None和数值失败分别表示。
输入覆盖与最终report/strict/没有数据满足筛选条件分类由外层负责，数值快照不补正常零。

```python
class SampleReductionResult
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; float &#124; None|是|无|最终单位有限候选，无法核实为None。|
|`unit`|str|是|无|最终输出标签，已换单位一次。|
|`calculation_failed`|bool|是|无|原序和、除法或最终转换失败。|
|`quality`|[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)|是|无|仅数值故障，输入原因另存facts。|
|`valid_sample_count`|int|是|无|实际参与候选的有效真实样本数。|
|`insufficient_samples`|bool|否|False|单个样本无法定义ddof=1的离散度。|

源码：[`src/chronaxis/core/sample_reduction.py:99`](../../../src/chronaxis/core/sample_reduction.py#L99)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-SampleReductionResult-__post_init__"></a>
### `SampleReductionResult.__post_init__`

拒绝样本数、正常数值和失败状态之间的矛盾。

```python
SampleReductionResult.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError为字段类型或不可能数值状态。

本函数直接报告的具体错误：

- `ValueError`：样本结果需要有限int/float或None。
- `TypeError`：样本结果需要真实失败状态、质量和非负原生int计数。
- `ValueError`：样本数值失败需要有效样本、None与明确原因。
- `ValueError`：样本成功结果数值、计数或质量矛盾。

源码：[`src/chronaxis/core/sample_reduction.py:113`](../../../src/chronaxis/core/sample_reduction.py#L113)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-require_sample_config"></a>
## `require_sample_config`

校验三samples能力、数值dtype与明确单位，不计算样本。

```python
require_sample_config(spec, input_unit, dtype, partial_limit)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|位置或关键字。本次指标的设置，包括统计时间范围、计算种类、输出单位及数据不全时的处理方式。该对象由调用方先构造；本函数不会重新读取JSON配置。|
|`input_unit`|str|是|无|位置或关键字。输入信号当前使用的单位，例如功率填"W"。函数据此检查输出单位的换算关系，不会仅凭这个字符串修改样本值。|
|`dtype`|SignalDType|是|无|位置或关键字。输入值的逻辑类型，传SignalDType成员；整数极值计算保持整数精度，均值按本函数说明转换为浮点。|
|`partial_limit`|int|是|无|位置或关键字。大于0的整数，限制浮点累加时保留的误差补偿项数量。默认4096；它不是样本数上限，也不是允许出现多少次错误。超过容量会报错。|

### 返回说明

CalculationConversion。

### 异常说明

TypeError/ValueError为类型、能力、单位或容量。

本函数直接报告的具体错误：

- `TypeError`：样本归约仅支持sample_minimum/sample_maximum/sample_mean。
- `ValueError`：样本统计只接受数值dtype。

源码：[`src/chronaxis/core/sample_reduction.py:139`](../../../src/chronaxis/core/sample_reduction.py#L139)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-require_sample_series"></a>
## `require_sample_series`

核对有限输入unit/dtype及精确交集，保留可选BOOL条件。

```python
require_sample_series(series, spec, input_unit, dtype)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`series`|[CalculationSeries](chronaxis.core.calculations.md#api-CalculationSeries)|是|无|位置或关键字。待检查的CalculationSeries。函数核对它与spec、input_unit和dtype是否一致，并确定实际数据范围与请求范围的交集；这里不会累计数值。|
|`spec`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|位置或关键字。本次指标的设置，包括统计时间范围、计算种类、输出单位及数据不全时的处理方式。该对象由调用方先构造；本函数不会重新读取JSON配置。|
|`input_unit`|str|是|无|位置或关键字。输入信号当前使用的单位，例如功率填"W"。函数据此检查输出单位的换算关系，不会仅凭这个字符串修改样本值。|
|`dtype`|SignalDType|是|无|位置或关键字。输入值的逻辑类型，传SignalDType成员；整数极值计算保持整数精度，均值按本函数说明转换为浮点。|

### 返回说明

实际交集Interval或None。

### 异常说明

TypeError/ValueError/OverflowError。

本函数直接报告的具体错误：

- `TypeError`：样本归约需要CalculationSeries。
- `ValueError`：样本归约只接受同unit及同dtype输入。
- `OverflowError`：样本正交集跨度超过int64。

源码：[`src/chronaxis/core/sample_reduction.py:155`](../../../src/chronaxis/core/sample_reduction.py#L155)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
