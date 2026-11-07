# `chronaxis.core.conditional_time_reduction`

定义带筛选条件的时间统计结果：时间最小值、时间最大值、时间加权平均和条件成立时长。数值有效时间与筛选条件已知时间分别记录。例如筛选条件已知为假，是“没有选中”，不属于“无法判断”。本模块定义数据和检查规则，不执行统计。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)、[CalculationSeries](chronaxis.core.calculations.md#api-CalculationSeries)、[D](chronaxis.core.types.md#api-SignalDType)、[Interval](chronaxis.core.models.md#api-Interval)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[SourceRef](chronaxis.core.models.md#api-SourceRef)

## 对象导航

|对象|用途|
|---|---|
|[`_unknown_duration`](#api-_unknown_duration)|核对一种未知范围的顺序与几何，返回精确整数时长。|
|[`ConditionalTimeCalculationFacts`](#api-ConditionalTimeCalculationFacts)|保存有限块双覆盖和选择交集，主FALSE只为duration保留有效零证据。|
|[`ConditionalTimeCalculationFacts.__post_init__`](#api-ConditionalTimeCalculationFacts-__post_init__)|检查各类时长能否正确划分实际范围、选中范围是否落在有效范围内，并核对来源标识。|
|[`require_conditional_time_series`](#api-require_conditional_time_series)|核对有限联合输入的条件、单位、类型与正交集几何。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from .calculations import CalculationDefinition, CalculationSeries
from .models import Interval, SourceRef
from .time_reduction import require_time_config
from .types import QualityFlag as Q, SignalDType as D
from .validation import require_text
```

</details>

<a id="api-_unknown_duration"></a>
## `_unknown_duration`

核对一种未知范围的顺序与几何，返回精确整数时长。

```python
_unknown_duration(ranges, actual)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`ranges`|tuple[[Interval](chronaxis.core.models.md#api-Interval), ...]|是|无|位置或关键字。按时间排列且已合并的未知区间，用于计算实际观测范围内的未知时长。|
|`actual`|[Interval](chronaxis.core.models.md#api-Interval) &#124; None|是|无|位置或关键字。请求范围与实际观测范围的交集；没有交集时为None。|

### 返回说明

原生int未知纳秒。

### 异常说明

TypeError/ValueError为类型、重叠、反序或越界。

本函数直接报告的具体错误：

- `TypeError`：条件时间未知范围需要tuple。
- `ValueError`：条件时间未知范围必须有序、不重叠且在实际窗口内。

源码：[`src/chronaxis/core/conditional_time_reduction.py:19`](../../../src/chronaxis/core/conditional_time_reduction.py#L19)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ConditionalTimeCalculationFacts"></a>
## `ConditionalTimeCalculationFacts`

保存有限块双覆盖和选择交集，主FALSE只为duration保留有效零证据。

数值算子selected包含外TRUE有效值；duration的selected只含外TRUE主TRUE。
selected_false只含duration外TRUE主FALSE，其他算子为0；真实样本遵循相同选择。
两未知元组分别完整划分值与外条件，不用UNKNOWN填零或代替FALSE。

```python
class ConditionalTimeCalculationFacts
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|原时间统计请求与政策，不按块重写。|
|`actual_window`|[Interval](chronaxis.core.models.md#api-Interval) &#124; None|是|无|本块实际参与统计的时间范围，是请求范围与观测范围的交集。没有交集时为None，不把未观察到的时间补入结果。|
|`value_valid_duration_ns`|int|是|无|原值通过本算子门槛后的有效纳秒。|
|`condition_known_duration_ns`|int|是|无|筛选条件能够确定为真或假的总时长，单位为纳秒。条件已知为假也计入已知时长；UNKNOWN不计入。|
|`selected_duration_ns`|int|是|无|外TRUE有效数值，duration另须主TRUE。|
|`selected_value_unknown_duration_ns`|int|是|无|筛选条件为真、但数值无法使用的时长，单位为纳秒。它与筛选条件本身未知的时长分开统计。|
|`false_duration_ns`|int|是|无|外条件已知FALSE纳秒，只有完整窗才证明没有数据满足筛选条件。|
|`selected_false_duration_ns`|int|是|无|duration外TRUE主FALSE有效零证据，其他算子0。|
|`valid_sample_count`|int|是|无|已选真实值更新，不是条件更新/保持区间数。|
|`value_unknown_ranges`|tuple[[Interval](chronaxis.core.models.md#api-Interval), ...]|是|无|数值无法用于本次计算的时间段元组，每段包含起点、不包含终点。缺失、失效或数值转换失败等原因另保存在quality字段。|
|`condition_unknown_ranges`|tuple[[Interval](chronaxis.core.models.md#api-Interval), ...]|是|无|筛选条件无法判断真假的时间段列表。它独立于数值是否有效，不应当作条件为假。|
|`quality`|[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)|是|无|输入、精度与依赖原因，不包含数值weight失败。|
|`input_unit`|str|是|无|本次计算输入值的工程单位，例如功率为W。这里记录原输入单位，最终结果的输出单位另由spec指定。|
|`dtype`|[D](chronaxis.core.types.md#api-SignalDType)|是|无|SignalDType枚举成员：INT64是有符号64位整数，UINT64是无符号64位整数，FLOAT64是双精度浮点，BOOL是真/假，ENUM是预先声明的状态标签。这里传枚举成员，不传字符串；当前运算支持哪些类型仍见本对象的约束。|
|`binding_identity`|str|是|无|产生这份数值输入的信号绑定标识。调用方用它检查各块是否来自同一次配置和输入，不能把不同绑定的块混在一起累计。|
|`source_refs`|tuple[[SourceRef](chronaxis.core.models.md#api-SourceRef), ...]|是|无|参与计算的数据来源及其位置，例如来源名、字段名和原记录位置。保留具体SourceRef子类，便于从结果追溯输入。|
|`ranges_retained`|bool|否|True|False只留分类所需计数，不构造未知范围。|

源码：[`src/chronaxis/core/conditional_time_reduction.py:38`](../../../src/chronaxis/core/conditional_time_reduction.py#L38)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ConditionalTimeCalculationFacts-__post_init__"></a>
### `ConditionalTimeCalculationFacts.__post_init__`

检查各类时长能否正确划分实际范围、选中范围是否落在有效范围内，并核对来源标识。

```python
ConditionalTimeCalculationFacts.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError为配置、几何或交集矛盾。

本函数直接报告的具体错误：

- `TypeError`：条件时间实际范围需要Interval或None。
- `ValueError`：条件时间实际范围越过原请求。
- `ValueError`：条件时间覆盖需要实际跨度内原生非负int。
- `ValueError`：条件时间样本、选择、有效FALSE及已知交集矛盾。
- `ValueError`：条件时间值有效与未知未完整划分实际窗口。
- `ValueError`：条件时间已知与外条件未知未完整划分实际窗口。
- `TypeError`：条件时间需要带有明确类型的质量和完整来源tuple。

源码：[`src/chronaxis/core/conditional_time_reduction.py:64`](../../../src/chronaxis/core/conditional_time_reduction.py#L64)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-require_conditional_time_series"></a>
## `require_conditional_time_series`

核对有限联合输入的条件、单位、类型与正交集几何。

```python
require_conditional_time_series(series, spec, input_unit, dtype)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`series`|[CalculationSeries](chronaxis.core.calculations.md#api-CalculationSeries)|是|无|位置或关键字。待检查的CalculationSeries。函数核对它与spec、input_unit和dtype是否一致，并确定实际数据范围与请求范围的交集；这里不会累计数值。必须包含明确的BOOL筛选条件。|
|`spec`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|位置或关键字。本次指标的设置，包括统计时间范围、计算种类、输出单位及数据不全时的处理方式。该对象由调用方先构造；本函数不会重新读取JSON配置。|
|`input_unit`|str|是|无|位置或关键字。输入信号当前使用的单位，例如功率填"W"。函数据此检查输出单位的换算关系，不会仅凭这个字符串修改样本值。|
|`dtype`|SignalDType|是|无|位置或关键字。输入值的逻辑类型，传SignalDType成员；整数极值计算保持整数精度，均值按本函数说明转换为浮点。|

### 返回说明

当前实际交集Interval或None。

### 异常说明

TypeError/ValueError/OverflowError。

本函数直接报告的具体错误：

- `TypeError`：条件时间归约需要CalculationSeries。
- `ValueError`：条件时间归约需要同单位同dtype及显式BOOL条件。
- `OverflowError`：条件时间正交集跨度超过int64。

源码：[`src/chronaxis/core/conditional_time_reduction.py:104`](../../../src/chronaxis/core/conditional_time_reduction.py#L104)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
