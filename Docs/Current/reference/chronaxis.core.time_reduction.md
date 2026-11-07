# `chronaxis.core.time_reduction`

定义按持续时间计算统计结果时保存的内容，包括有效时长、缺失区间、样本数量及计算值。min_time/max_time寻找实际持续过的最小/最大值，time_weighted_mean按持续时间加权，duration累计条件成立的秒数。本模块定义这些数据和检查规则，不执行计算。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)、[CalculationSeries](chronaxis.core.calculations.md#api-CalculationSeries)、[D](chronaxis.core.types.md#api-SignalDType)、[Interval](chronaxis.core.models.md#api-Interval)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[SourceRef](chronaxis.core.models.md#api-SourceRef)

## 对象导航

|对象|用途|
|---|---|
|[`TimeCalculationFacts`](#api-TimeCalculationFacts)|保存有限块的真实覆盖事实；FALSE仍是有效BOOL，不能算成未知。|
|[`TimeCalculationFacts.__post_init__`](#api-TimeCalculationFacts-__post_init__)|检查有效和未知时长是否正确划分实际范围，并检查字段类型；不一致时直接报错。|
|[`TimeReductionResult`](#api-TimeReductionResult)|保存整窗时间统计的数值快照，覆盖与report/strict由外层分类。|
|[`TimeReductionResult.__post_init__`](#api-TimeReductionResult-__post_init__)|拒绝未知、正常零和故障之间的矛盾，不补候选值。|
|[`MeanTimeBlock`](#api-MeanTimeBlock)|借出一批均值所需数值和权重；不含原帧、双时间或逐条来源。|
|[`require_time_config`](#api-require_time_config)|检查无条件时间归约配置，不执行数值转换或计算。|
|[`require_time_series`](#api-require_time_series)|校验有限输入身份类型与正交集时长，不共享数值运算。|
|[`require_time_options`](#api-require_time_options)|检查记录周期、实际截止和范围输出开关，不执行数值计算。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .moments import TIME_MOMENTS
from dataclasses import dataclass
from math import isfinite
from .calculations import CalculationDefinition, CalculationSeries, calculation_conversion
from .models import Interval, SourceRef
from .types import SignalDType as D, QualityFlag as Q
from .validation import require_text
from .integral_sum import require_partial_limit
from .record_intervals import require_record_step
from .integral_terms import require_valid_until
```

</details>

<a id="api-TimeCalculationFacts"></a>
## `TimeCalculationFacts`

保存有限块的真实覆盖事实；FALSE仍是有效BOOL，不能算成未知。

selected_duration_ns在数值算子等于有效时长，在duration只计有效TRUE。
sample_count只计半开块内真实更新，duration另要求TRUE，不计共享右端。
time_weighted_mean的值有效性已包含整数到float的精度检查；权重计算故障不改覆盖。

```python
class TimeCalculationFacts
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|原请求、政策和scope，不按当前块重写。|
|`actual_window`|[Interval](chronaxis.core.models.md#api-Interval) &#124; None|是|无|本块实际参与统计的时间范围，是请求范围与观测范围的交集。没有交集时为None，不把未观察到的时间补入结果。|
|`value_valid_duration_ns`|int|是|无|所有有效值的整数纳秒时长。|
|`selected_duration_ns`|int|是|无|数值有效时长，或BOOL TRUE时长。|
|`valid_sample_count`|int|是|无|已选真实更新计数，不是保持区间数。|
|`value_unknown_ranges`|tuple[[Interval](chronaxis.core.models.md#api-Interval), ...]|是|无|数值无法用于本次计算的时间段元组，每段包含起点、不包含终点。缺失、失效或数值转换失败等原因另保存在quality字段。|
|`quality`|[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)|是|无|输入、精度及依赖原因，不表示必须全数值失败。|
|`input_unit`|str|是|无|本次计算输入值的工程单位，例如功率为W。这里记录原输入单位，最终结果的输出单位另由spec指定。|
|`dtype`|[D](chronaxis.core.types.md#api-SignalDType)|是|无|SignalDType枚举成员：INT64是有符号64位整数，UINT64是无符号64位整数，FLOAT64是双精度浮点，BOOL是真/假，ENUM是预先声明的状态标签。这里传枚举成员，不传字符串；当前运算支持哪些类型仍见本对象的约束。|
|`binding_identity`|str|是|无|产生这份数值输入的信号绑定标识。调用方用它检查各块是否来自同一次配置和输入，不能把不同绑定的块混在一起累计。|
|`source_refs`|tuple[[SourceRef](chronaxis.core.models.md#api-SourceRef), ...]|是|无|参与计算的数据来源及其位置，例如来源名、字段名和原记录位置。保留具体SourceRef子类，便于从结果追溯输入。|
|`ranges_retained`|bool|否|True|精简执行可不构造未知位置，不能用于完整覆盖证据。|

源码：[`src/chronaxis/core/time_reduction.py:24`](../../../src/chronaxis/core/time_reduction.py#L24)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-TimeCalculationFacts-__post_init__"></a>
### `TimeCalculationFacts.__post_init__`

检查有效和未知时长是否正确划分实际范围，并检查字段类型；不一致时直接报错。

```python
TimeCalculationFacts.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError为结构或矛盾时长。

本函数直接报告的具体错误：

- `TypeError`：时间事实实际范围需要Interval或None。
- `ValueError`：时间事实范围超出原请求。
- `ValueError`：时间事实有效时长、选择或样本计数矛盾。
- `ValueError`：无条件数值的选择时长必须等于有效时长。
- `TypeError`：时间事实未知范围需要tuple。
- `ValueError`：时间事实未完整划分有效和未知时长。
- `TypeError`：时间事实需要带有明确类型的质量和完整来源tuple。
- `ValueError`：时间事实未知范围无序、重叠或越界。

源码：[`src/chronaxis/core/time_reduction.py:45`](../../../src/chronaxis/core/time_reduction.py#L45)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-TimeReductionResult"></a>
## `TimeReductionResult`

保存整窗时间统计的数值快照，覆盖与report/strict由外层分类。

极值可为精确int；均值与时长为float。有效零和无有效证据的None分别保存。
valid_term_count统计有效正区间，不等于真实更新样本数或TRUE区间数。

```python
class TimeReductionResult
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; float &#124; None|是|无|最终单位下的有限候选值。|
|`unit`|str|是|无|已核对的输出单位，不再逐块换算。|
|`calculation_failed`|bool|是|无|权重、原序求和或最终转换故障。|
|`quality`|[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)|是|无|仅本次数值归约故障，输入原因在facts。|
|`valid_term_count`|int|是|无|原值经算子门槛后有效的正区间数。|

源码：[`src/chronaxis/core/time_reduction.py:87`](../../../src/chronaxis/core/time_reduction.py#L87)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-TimeReductionResult-__post_init__"></a>
### `TimeReductionResult.__post_init__`

拒绝未知、正常零和故障之间的矛盾，不补候选值。

```python
TimeReductionResult.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError为字段或状态矛盾。

本函数直接报告的具体错误：

- `ValueError`：时间归约值需要有限int/float或None。
- `TypeError`：时间归约状态、质量和项数类型错误。
- `ValueError`：时间计算故障需要有效项、None和质量原因。
- `ValueError`：时间成功数值、项数或质量矛盾。

源码：[`src/chronaxis/core/time_reduction.py:100`](../../../src/chronaxis/core/time_reduction.py#L100)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-MeanTimeBlock"></a>
## `MeanTimeBlock`

借出一批均值所需数值和权重；不含原帧、双时间或逐条来源。

values/weights为参考tuple或NumPy有限列，调用者为其内存付费。
仅均值首遍显式请求时生成；facts仍用于必要的结果分类。

```python
class MeanTimeBlock
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`facts`|object|是|无|无条件或条件时间事实。|
|`values`|object|是|无|已通过均值精度门槛的有限数值列。|
|`weights`|object|是|无|与values同长的正权重，周期模式为折算秒数。|

源码：[`src/chronaxis/core/time_reduction.py:122`](../../../src/chronaxis/core/time_reduction.py#L122)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-require_time_config"></a>
## `require_time_config`

检查无条件时间归约配置，不执行数值转换或计算。

```python
require_time_config(spec, input_unit, dtype, selected_duration_ns, partial_limit, *, step_ns=None, selected_weight_seconds=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|位置或关键字。本次指标的设置，包括统计时间范围、计算种类、输出单位及数据不全时的处理方式。该对象由调用方先构造；本函数不会重新读取JSON配置。|
|`input_unit`|str|是|无|位置或关键字。输入信号当前使用的单位，例如功率填"W"。函数据此检查输出单位的换算关系，不会仅凭这个字符串修改样本值。|
|`dtype`|SignalDType|是|无|位置或关键字。输入值的逻辑类型，传SignalDType成员；整数极值计算保持整数精度，均值按本函数说明转换为浮点。|
|`selected_duration_ns`|int &#124; None|是|无|位置或关键字。已选中且有效的总时长，单位纳秒，作为时间均值的分母。None表示先统计这个时长；第二遍把第一遍得到的时长传进来，累计每段值×该段时长÷总时长。|
|`partial_limit`|int|是|无|位置或关键字。大于0的整数，限制浮点累加时保留的误差补偿项数量。默认4096；它不是样本数上限，也不是允许出现多少次错误。超过容量会报错。|
|`step_ns`|int &#124; None|否|None|仅关键字。所选固定或DBC周期，单位纳秒且大于0；None表示采用实际时间间隔，不生成第二套时间坐标。|
|`selected_weight_seconds`|float &#124; None|否|None|仅关键字。固定或DBC周期均值第二遍使用的有效权重总秒数，必须有限且大于0；None表示尚未提供第二遍分母。|

### 返回说明

CalculationConversion。

### 异常说明

TypeError/ValueError为不支持能力或非法配置。

本函数直接报告的具体错误：

- `TypeError`：有限时间归约仅支持明确无条件时间算子。
- `ValueError`：时间算子与dtype不匹配。
- `ValueError`：仅时间均值第二遍接受正原生int64整窗有效时长。

源码：[`src/chronaxis/core/time_reduction.py:134`](../../../src/chronaxis/core/time_reduction.py#L134)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-require_time_series"></a>
## `require_time_series`

校验有限输入身份类型与正交集时长，不共享数值运算。

```python
require_time_series(series, spec, input_unit, dtype)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`series`|[CalculationSeries](chronaxis.core.calculations.md#api-CalculationSeries)|是|无|位置或关键字。待检查的CalculationSeries。函数核对它与spec、input_unit和dtype是否一致，并确定实际数据范围与请求范围的交集；这里不会累计数值。|
|`spec`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|位置或关键字。本次指标的设置，包括统计时间范围、计算种类、输出单位及数据不全时的处理方式。该对象由调用方先构造；本函数不会重新读取JSON配置。|
|`input_unit`|str|是|无|位置或关键字。输入信号当前使用的单位，例如功率填"W"。函数据此检查输出单位的换算关系，不会仅凭这个字符串修改样本值。|
|`dtype`|SignalDType|是|无|位置或关键字。输入值的逻辑类型，传SignalDType成员；整数极值计算保持整数精度，均值按本函数说明转换为浮点。|

### 返回说明

当前实际交集Interval或None。

### 异常说明

TypeError/ValueError/OverflowError。

本函数直接报告的具体错误：

- `TypeError`：时间归约需要CalculationSeries。
- `ValueError`：时间归约只接受同单位同dtype的无条件输入。
- `OverflowError`：时间统计正交集时长超过int64。

源码：[`src/chronaxis/core/time_reduction.py:165`](../../../src/chronaxis/core/time_reduction.py#L165)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-require_time_options"></a>
## `require_time_options`

检查记录周期、实际截止和范围输出开关，不执行数值计算。

```python
require_time_options(series, step_ns, valid_until_ns, retain_unknown_ranges)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`series`|[CalculationSeries](chronaxis.core.calculations.md#api-CalculationSeries)|是|无|位置或关键字。有界的数值、条件、真实更新标志及实际观测范围；不代表整个输入文件已装入内存。|
|`step_ns`|int &#124; None|是|无|位置或关键字。所选固定或DBC周期，单位纳秒且大于0；None表示采用实际时间间隔，不生成第二套时间坐标。|
|`valid_until_ns`|Sequence[int &#124; None] &#124; None|是|无|位置或关键字。每个值按真实时间计算的有效截止，单位纳秒；None沿原有效范围，不按固定周期延长旧值寿命。|
|`retain_unknown_ranges`|bool|是|无|位置或关键字。是否收集未知区间列表；关闭时仍计算未知对数值和状态的影响，但不建立该区间明细。|

### 返回说明

None。

### 异常说明

类型、长度或将合成边界当周期记录时拒绝。

源码：[`src/chronaxis/core/time_reduction.py:182`](../../../src/chronaxis/core/time_reduction.py#L182)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
