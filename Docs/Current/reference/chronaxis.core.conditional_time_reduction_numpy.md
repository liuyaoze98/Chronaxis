# `chronaxis.core.conditional_time_reduction_numpy`

用NumPy计算带筛选条件的时间统计。最小值和最大值保留原数值类型；duration累计主条件和筛选条件同时为真的时长；time_weighted_mean先统计有效且选中的总时长，再按各段所占比例计算平均值。最终输出单位在finish时换算一次。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ConditionalTimeCalculationFacts](chronaxis.core.conditional_time_reduction.md#api-ConditionalTimeCalculationFacts)、[Interval](chronaxis.core.models.md#api-Interval)、[MeanTimeBlock](chronaxis.core.time_reduction.md#api-MeanTimeBlock)、[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)、[NumpyIntegralSum](chronaxis.core.integral_sum_numpy.md#api-NumpyIntegralSum)、[NumpyMoments](chronaxis.core.moments_numpy.md#api-NumpyMoments)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[TimeReductionResult](chronaxis.core.time_reduction.md#api-TimeReductionResult)

## 对象导航

|对象|用途|
|---|---|
|[`NumpyConditionalTimeReduction`](#api-NumpyConditionalTimeReduction)|分批计算带筛选条件的时间极值、时间加权平均或BOOL时长。每次push读取一块数据并保留累计状态；时间均值先统计总有效时长，再按各段时长占比累加，finish返回结果。|
|[`NumpyConditionalTimeReduction.__init__`](#api-NumpyConditionalTimeReduction-__init__)|校验原配置并建立本数组后端固定状态。|
|[`NumpyConditionalTimeReduction.selected_weight_seconds`](#api-NumpyConditionalTimeReduction-selected_weight_seconds)|读取必要周期权重。|
|[`NumpyConditionalTimeReduction.selected_duration_ns`](#api-NumpyConditionalTimeReduction-selected_duration_ns)|读取累计已选时长。|
|[`NumpyConditionalTimeReduction.value_valid_duration_ns`](#api-NumpyConditionalTimeReduction-value_valid_duration_ns)|读取累计值有效时长。|
|[`NumpyConditionalTimeReduction.push`](#api-NumpyConditionalTimeReduction-push)|计算有限块双覆盖并按原序推进本后端数值候选。|
|[`NumpyConditionalTimeReduction.finish`](#api-NumpyConditionalTimeReduction-finish)|生成原序统计快照并做一次最终换单位，双覆盖由外层分类。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .calculation_output_numpy import convert_result_numpy
from .conditional_time_reduction import ConditionalTimeCalculationFacts, require_conditional_time_series
from .integral_sum_numpy import NumpyIntegralSum
from .moments import TIME_MOMENTS
from .moments_numpy import NumpyMoments
from .calculations import merge_ranges
from .models import Interval
from .numeric_numpy import DTYPES, NumericArray, to_float_numpy
from .time_reduction import TimeReductionResult, require_time_config, require_time_options
from .integral_terms import require_valid_until
from .types import QualityFlag as Q
from .time_reduction import MeanTimeBlock
from .mean_weights_numpy import normalized_mean_terms
```

</details>

<a id="api-NumpyConditionalTimeReduction"></a>
## `NumpyConditionalTimeReduction`

分批计算带筛选条件的时间极值、时间加权平均或BOOL时长。每次push读取一块数据并保留累计状态；时间均值先统计总有效时长，再按各段时长占比累加，finish返回结果。

```python
NumpyConditionalTimeReduction(spec, input_unit, dtype, *, selected_duration_ns=None, partial_limit=4096, step_ns=None, selected_weight_seconds=None)
```


源码：[`src/chronaxis/core/conditional_time_reduction_numpy.py:28`](../../../src/chronaxis/core/conditional_time_reduction_numpy.py#L28)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-NumpyConditionalTimeReduction-__init__"></a>
### `NumpyConditionalTimeReduction.__init__`

校验原配置并建立本数组后端固定状态。

```python
NumpyConditionalTimeReduction.__init__(spec, input_unit, dtype, *, selected_duration_ns=None, partial_limit=4096, step_ns=None, selected_weight_seconds=None)
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

配置、数组分配错误传播。

源码：[`src/chronaxis/core/conditional_time_reduction_numpy.py:31`](../../../src/chronaxis/core/conditional_time_reduction_numpy.py#L31)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-NumpyConditionalTimeReduction-selected_weight_seconds"></a>
### `NumpyConditionalTimeReduction.selected_weight_seconds`

读取必要周期权重。

```python
NumpyConditionalTimeReduction.selected_weight_seconds
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

float或不适用None。

#### 异常说明

权重求和故障。

源码：[`src/chronaxis/core/conditional_time_reduction_numpy.py:54`](../../../src/chronaxis/core/conditional_time_reduction_numpy.py#L54)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-NumpyConditionalTimeReduction-selected_duration_ns"></a>
### `NumpyConditionalTimeReduction.selected_duration_ns`

读取累计已选时长。

```python
NumpyConditionalTimeReduction.selected_duration_ns
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

原生int纳秒。

#### 异常说明

无。

源码：[`src/chronaxis/core/conditional_time_reduction_numpy.py:64`](../../../src/chronaxis/core/conditional_time_reduction_numpy.py#L64)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-NumpyConditionalTimeReduction-value_valid_duration_ns"></a>
### `NumpyConditionalTimeReduction.value_valid_duration_ns`

读取累计值有效时长。

```python
NumpyConditionalTimeReduction.value_valid_duration_ns
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

原生int纳秒。

#### 异常说明

无。

源码：[`src/chronaxis/core/conditional_time_reduction_numpy.py:69`](../../../src/chronaxis/core/conditional_time_reduction_numpy.py#L69)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-NumpyConditionalTimeReduction-push"></a>
### `NumpyConditionalTimeReduction.push`

计算有限块双覆盖并按原序推进本后端数值候选。

```python
NumpyConditionalTimeReduction.push(series, *, valid_until_ns=None, condition_valid_until_ns=None, retain_unknown_ranges=True, retain_mean_terms=False)
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

ConditionalTimeCalculationFacts；权重故障仅改变数值失败状态，不改输入覆盖。

#### 异常说明

结构、身份、容量、分配或取消错误传播，外层异常后只能清理owner。
内存: 所有新输入/掩码列形状N或N-1，仅当前push存活，不修改调用者输入。

本函数直接报告的具体错误：

- `ValueError`：条件时间归约不能跨绑定身份累计。

源码：[`src/chronaxis/core/conditional_time_reduction_numpy.py:73`](../../../src/chronaxis/core/conditional_time_reduction_numpy.py#L73)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-NumpyConditionalTimeReduction-finish"></a>
### `NumpyConditionalTimeReduction.finish`

生成原序统计快照并做一次最终换单位，双覆盖由外层分类。

```python
NumpyConditionalTimeReduction.finish()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

既有TimeReductionResult。

#### 异常说明

mean首遍RuntimeError、次遍分母不符ValueError；
    配置/分配/取消传播，数值溢出和非零下溢返回计算失败。

本函数直接报告的具体错误：

- `RuntimeError`：条件时间均值首遍只收事实，不能生成数值。
- `ValueError`：条件均值次遍选择时长与全窗分母不同。

源码：[`src/chronaxis/core/conditional_time_reduction_numpy.py:194`](../../../src/chronaxis/core/conditional_time_reduction_numpy.py#L194)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
