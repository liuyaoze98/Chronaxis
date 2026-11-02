# chronaxis.core.time_reduction_numpy

用NumPy逐块计算时间最小值、最大值、加权平均值或条件成立时长。每段用左端值代表该段持续时间；time_weighted_mean先取得总有效时长，再按各段时长比例累计。块之间只保留计算状态，不保存此前整列数据。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Interval](chronaxis.core.models.md#api-Interval)、[MeanTimeBlock](chronaxis.core.time_reduction.md#api-MeanTimeBlock)、[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)、[NumpyIntegralSum](chronaxis.core.integral_sum_numpy.md#api-NumpyIntegralSum)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[TimeCalculationFacts](chronaxis.core.time_reduction.md#api-TimeCalculationFacts)、[TimeReductionResult](chronaxis.core.time_reduction.md#api-TimeReductionResult)

## 对象导航

|对象|用途|
|---|---|
|[`NumpyTimeReduction`](#api-NumpyTimeReduction)|保留单候选、精确时长计数及有限误差数组，不保留历史输入列。|
|[`NumpyTimeReduction.__init__`](#api-NumpyTimeReduction-__init__)|检查无条件时间配置并建立本数组后端状态。|
|[`NumpyTimeReduction.selected_weight_seconds`](#api-NumpyTimeReduction-selected_weight_seconds)|读取必要的周期累计权重。|
|[`NumpyTimeReduction.selected_duration_ns`](#api-NumpyTimeReduction-selected_duration_ns)|读取累计选择时长。|
|[`NumpyTimeReduction.value_valid_duration_ns`](#api-NumpyTimeReduction-value_valid_duration_ns)|读取累计有效时长。|
|[`NumpyTimeReduction.push`](#api-NumpyTimeReduction-push)|用数组计算当前块的覆盖统计，并更新原输入单位下的累计结果。|
|[`NumpyTimeReduction.finish`](#api-NumpyTimeReduction-finish)|正确舍入并做一次最终转换，生成本后端数值快照。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .integral_sum_numpy import NumpyIntegralSum
from .models import Interval
from .numeric_numpy import NumericArray, DTYPES, to_float_numpy
from .types import QualityFlag as Q
from .time_reduction import TimeCalculationFacts, TimeReductionResult, require_time_config, require_time_series, require_time_options
from .time_reduction import MeanTimeBlock
from .mean_weights_numpy import normalized_mean_terms
```

</details>

<a id="api-NumpyTimeReduction"></a>
## `NumpyTimeReduction`

保留单候选、精确时长计数及有限误差数组，不保留历史输入列。

mean分母为None时只处理第一遍事实，不能finish；第二遍须逐块消费同一历史。
原序浮点累计属于state_driver，每项误差推进与块掩码均是实际数组运算。

```python
NumpyTimeReduction(spec, input_unit, dtype, *, selected_duration_ns=None, partial_limit=4096, step_ns=None, selected_weight_seconds=None)
```


源码：[`src/chronaxis/core/time_reduction_numpy.py:26`](../../../src/chronaxis/core/time_reduction_numpy.py#L26)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-NumpyTimeReduction-__init__"></a>
### `NumpyTimeReduction.__init__`

检查无条件时间配置并建立本数组后端状态。

```python
NumpyTimeReduction.__init__(spec, input_unit, dtype, *, selected_duration_ns=None, partial_limit=4096, step_ns=None, selected_weight_seconds=None)
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

源码：[`src/chronaxis/core/time_reduction_numpy.py:33`](../../../src/chronaxis/core/time_reduction_numpy.py#L33)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-NumpyTimeReduction-selected_weight_seconds"></a>
### `NumpyTimeReduction.selected_weight_seconds`

读取必要的周期累计权重。

```python
NumpyTimeReduction.selected_weight_seconds
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

float或不适用None。

#### 异常说明

数值故障。

源码：[`src/chronaxis/core/time_reduction_numpy.py:54`](../../../src/chronaxis/core/time_reduction_numpy.py#L54)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-NumpyTimeReduction-selected_duration_ns"></a>
### `NumpyTimeReduction.selected_duration_ns`

读取累计选择时长。

```python
NumpyTimeReduction.selected_duration_ns
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

原生int纳秒。

#### 异常说明

无。

源码：[`src/chronaxis/core/time_reduction_numpy.py:64`](../../../src/chronaxis/core/time_reduction_numpy.py#L64)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-NumpyTimeReduction-value_valid_duration_ns"></a>
### `NumpyTimeReduction.value_valid_duration_ns`

读取累计有效时长。

```python
NumpyTimeReduction.value_valid_duration_ns
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

原生int纳秒。

#### 异常说明

无。

源码：[`src/chronaxis/core/time_reduction_numpy.py:69`](../../../src/chronaxis/core/time_reduction_numpy.py#L69)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-NumpyTimeReduction-push"></a>
### `NumpyTimeReduction.push`

用数组计算当前块的覆盖统计，并更新原输入单位下的累计结果。

```python
NumpyTimeReduction.push(series, *, valid_until_ns=None, retain_unknown_ranges=True, retain_mean_terms=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`series`|CalculationSeries|是|无|位置或关键字。本次要处理的一块时间和值，单位、dtype和绑定必须与构造时一致。带条件的计算还需要与值对齐的BOOL条件；push处理当前块后保留累计结果，下一块可继续调用。|
|`valid_until_ns`|Sequence[int &#124; None] &#124; None|否|None|仅关键字。每个值按真实时间计算的有效截止，单位纳秒；None沿原有效范围，不按固定周期延长旧值寿命。|
|`retain_unknown_ranges`|bool|否|True|仅关键字。是否收集未知区间列表；关闭时仍计算未知对数值和状态的影响，但不建立该区间明细。|
|`retain_mean_terms`|bool|否|False|仅关键字。是否保留本批均值计算需要的值和权重；False从构造处跳过这些项。|

#### 返回说明

TimeCalculationFacts；数值权重故障与输入覆盖有效性分别记录。

#### 异常说明

结构、身份、容量或分配错误传播；外层异常后只能清理owner。
内存: 新数组都是当前(N,)或(N-1,)有限列，不修改输入，也不存入跨块状态。

本函数直接报告的具体错误：

- `ValueError`：时间归约不能跨绑定身份累计。

源码：[`src/chronaxis/core/time_reduction_numpy.py:73`](../../../src/chronaxis/core/time_reduction_numpy.py#L73)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-NumpyTimeReduction-finish"></a>
### `NumpyTimeReduction.finish`

正确舍入并做一次最终转换，生成本后端数值快照。

```python
NumpyTimeReduction.finish()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

TimeReductionResult，不执行覆盖状态分类。

#### 异常说明

RuntimeError为mean第一遍；ValueError为有效时长与全窗分母不符；
    分配或取消传播，数值溢出与非零下溢写成计算失败。

本函数直接报告的具体错误：

- `RuntimeError`：时间均值第一遍只收事实，不能生成数值。
- `ValueError`：时间均值第二遍有效时长与整窗分母不同。

源码：[`src/chronaxis/core/time_reduction_numpy.py:166`](../../../src/chronaxis/core/time_reduction_numpy.py#L166)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
