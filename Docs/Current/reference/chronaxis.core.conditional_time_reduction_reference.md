# `chronaxis.core.conditional_time_reduction_reference`

逐段计算带筛选条件的时间统计，供NumPy实现对照。push接收下一块数据并保留累计结果；time_weighted_mean需要两遍读取，第一遍统计总有效时长，第二遍按时长比例计算平均值。每块处理完后不再保存该块的整列输入。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ConditionalTimeCalculationFacts](chronaxis.core.conditional_time_reduction.md#api-ConditionalTimeCalculationFacts)、[Interval](chronaxis.core.models.md#api-Interval)、[MeanTimeBlock](chronaxis.core.time_reduction.md#api-MeanTimeBlock)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ReferenceIntegralSum](chronaxis.core.integral_sum_reference.md#api-ReferenceIntegralSum)、[ReferenceMoments](chronaxis.core.moments_reference.md#api-ReferenceMoments)、[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)、[TimeReductionResult](chronaxis.core.time_reduction.md#api-TimeReductionResult)

## 对象导航

|对象|用途|
|---|---|
|[`ReferenceConditionalTimeReduction`](#api-ReferenceConditionalTimeReduction)|保存一个原dtype候选、精确时长与有界误差项，mean两遍实例不能混用。|
|[`ReferenceConditionalTimeReduction.__init__`](#api-ReferenceConditionalTimeReduction-__init__)|验证原配置并建立本后端有限状态。|
|[`ReferenceConditionalTimeReduction.selected_weight_seconds`](#api-ReferenceConditionalTimeReduction-selected_weight_seconds)|读取必要周期权重。|
|[`ReferenceConditionalTimeReduction.selected_duration_ns`](#api-ReferenceConditionalTimeReduction-selected_duration_ns)|读取累计选择时长。|
|[`ReferenceConditionalTimeReduction.value_valid_duration_ns`](#api-ReferenceConditionalTimeReduction-value_valid_duration_ns)|读取累计值有效时长。|
|[`ReferenceConditionalTimeReduction.push`](#api-ReferenceConditionalTimeReduction-push)|处理下一块数值和条件，返回两者各自的覆盖统计，并更新当前累计值；此时尚未换算输出单位。|
|[`ReferenceConditionalTimeReduction.finish`](#api-ReferenceConditionalTimeReduction-finish)|生成数值快照并只转换一次，覆盖与全外FALSE分类由外层处理。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from math import isfinite
from .calculation_output_reference import convert_result_reference
from .conditional_time_reduction import ConditionalTimeCalculationFacts, require_conditional_time_series
from .integral_sum_reference import ReferenceIntegralSum
from .moments import TIME_MOMENTS
from .moments_reference import ReferenceMoments
from .calculations import merge_ranges
from .models import Interval
from .numeric import ScalarValue, to_float_reference
from .time_reduction import TimeReductionResult, require_time_config, require_time_options
from .integral_terms import require_valid_until
from .record_intervals import clipped_record_seconds
from .types import QualityFlag as Q
from .time_reduction import MeanTimeBlock
from .mean_weights_reference import normalized_mean_terms
```

</details>

<a id="api-ReferenceConditionalTimeReduction"></a>
## `ReferenceConditionalTimeReduction`

保存一个原dtype候选、精确时长与有界误差项，mean两遍实例不能混用。

```python
ReferenceConditionalTimeReduction(spec, input_unit, dtype, *, selected_duration_ns=None, partial_limit=4096, step_ns=None, selected_weight_seconds=None)
```


源码：[`src/chronaxis/core/conditional_time_reduction_reference.py:29`](../../../src/chronaxis/core/conditional_time_reduction_reference.py#L29)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ReferenceConditionalTimeReduction-__init__"></a>
### `ReferenceConditionalTimeReduction.__init__`

验证原配置并建立本后端有限状态。

```python
ReferenceConditionalTimeReduction.__init__(spec, input_unit, dtype, *, selected_duration_ns=None, partial_limit=4096, step_ns=None, selected_weight_seconds=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|CalculationDefinition|是|无|位置或关键字。本次指标的设置，包括统计时间范围、计算种类、输出单位及数据不全时的处理方式。该对象由调用方先构造；本函数不会重新读取JSON配置。|
|`input_unit`|str|是|无|位置或关键字。输入信号当前使用的单位，例如功率填"W"。函数据此检查输出单位的换算关系，不会仅凭这个字符串修改样本值。|
|`dtype`|SignalDType|是|无|位置或关键字。输入值的逻辑类型，传SignalDType成员；整数极值计算保持整数精度，均值按本函数说明转换为浮点。|
|`selected_duration_ns`|int &#124; None|否|None|仅关键字。已选中且有效的总时长，单位纳秒，作为时间均值的分母。None表示先统计这个时长；第二遍把第一遍得到的时长传进来，累计每段值×该段时长÷总时长。|
|`partial_limit`|int|否|4096|仅关键字。大于0的整数，限制浮点累加时保留的误差补偿项数量。默认4096；它不是样本数上限，也不是允许出现多少次错误。超过容量会报错。|
|`step_ns`|int &#124; None|否|None|仅关键字。所选固定或DBC周期，单位纳秒且大于0；None表示采用实际时间间隔，不生成第二套时间坐标。|
|`selected_weight_seconds`|float &#124; None|否|None|仅关键字。固定或DBC周期均值第二遍使用的有效权重总秒数，必须有限且大于0；None表示尚未提供第二遍分母。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

配置或分配错误传播。

源码：[`src/chronaxis/core/conditional_time_reduction_reference.py:32`](../../../src/chronaxis/core/conditional_time_reduction_reference.py#L32)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ReferenceConditionalTimeReduction-selected_weight_seconds"></a>
### `ReferenceConditionalTimeReduction.selected_weight_seconds`

读取必要周期权重。

```python
ReferenceConditionalTimeReduction.selected_weight_seconds
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

float或不适用None。

#### 异常说明

权重求和故障。

源码：[`src/chronaxis/core/conditional_time_reduction_reference.py:55`](../../../src/chronaxis/core/conditional_time_reduction_reference.py#L55)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ReferenceConditionalTimeReduction-selected_duration_ns"></a>
### `ReferenceConditionalTimeReduction.selected_duration_ns`

读取累计选择时长。

```python
ReferenceConditionalTimeReduction.selected_duration_ns
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

原生int纳秒。

#### 异常说明

无。

源码：[`src/chronaxis/core/conditional_time_reduction_reference.py:65`](../../../src/chronaxis/core/conditional_time_reduction_reference.py#L65)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ReferenceConditionalTimeReduction-value_valid_duration_ns"></a>
### `ReferenceConditionalTimeReduction.value_valid_duration_ns`

读取累计值有效时长。

```python
ReferenceConditionalTimeReduction.value_valid_duration_ns
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

原生int纳秒。

#### 异常说明

无。

源码：[`src/chronaxis/core/conditional_time_reduction_reference.py:70`](../../../src/chronaxis/core/conditional_time_reduction_reference.py#L70)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ReferenceConditionalTimeReduction-push"></a>
### `ReferenceConditionalTimeReduction.push`

处理下一块数值和条件，返回两者各自的覆盖统计，并更新当前累计值；此时尚未换算输出单位。

```python
ReferenceConditionalTimeReduction.push(series, *, valid_until_ns=None, condition_valid_until_ns=None, retain_unknown_ranges=True, retain_mean_terms=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`series`|CalculationSeries|是|无|位置或关键字。本次要处理的一块时间和值，单位、dtype和绑定必须与构造时一致。带条件的计算还需要与值对齐的BOOL条件；push处理当前块后保留累计结果，下一块可继续调用。|
|`valid_until_ns`|Sequence[int &#124; None] &#124; None|否|None|仅关键字。每个值按真实时间计算的有效截止，单位纳秒；None沿原有效范围，不按固定周期延长旧值寿命。|
|`condition_valid_until_ns`|Sequence[int &#124; None] &#124; None|否|None|仅关键字。各筛选条件的真实有效截止，单位纳秒；条件未知不能当作False或补零。|
|`retain_unknown_ranges`|bool|否|True|仅关键字。是否收集未知区间列表；关闭时仍计算未知对数值和状态的影响，但不建立该区间明细。|
|`retain_mean_terms`|bool|否|False|仅关键字。是否保留本批均值计算需要的值和权重；False从构造处跳过这些项。|

#### 返回说明

ConditionalTimeCalculationFacts；mean权重故障只记数值质量，不改覆盖。

#### 异常说明

结构、身份、容量或分配错误传播；外层不得继续使用异常前缀状态。

本函数直接报告的具体错误：

- `ValueError`：条件时间归约不能跨绑定身份累计。

源码：[`src/chronaxis/core/conditional_time_reduction_reference.py:74`](../../../src/chronaxis/core/conditional_time_reduction_reference.py#L74)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ReferenceConditionalTimeReduction-finish"></a>
### `ReferenceConditionalTimeReduction.finish`

生成数值快照并只转换一次，覆盖与全外FALSE分类由外层处理。

```python
ReferenceConditionalTimeReduction.finish()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

既有TimeReductionResult。

#### 异常说明

mean首遍RuntimeError、次遍分母不符ValueError；
    配置/分配错误传播，数值故障保留None和质量。

本函数直接报告的具体错误：

- `RuntimeError`：条件时间均值首遍只收事实，不能生成数值。
- `ValueError`：条件均值次遍选择时长与全窗分母不同。

源码：[`src/chronaxis/core/conditional_time_reduction_reference.py:186`](../../../src/chronaxis/core/conditional_time_reduction_reference.py#L186)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
