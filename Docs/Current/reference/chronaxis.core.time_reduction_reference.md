# `chronaxis.core.time_reduction_reference`

逐段计算时间最小值、最大值、加权平均值或条件成立时长，供NumPy实现对照。push接收下一块数据，finish整理最终值。time_weighted_mean需要先统计总有效时长，再按时长比例计算；整数极值不先转成浮点数。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Interval](chronaxis.core.models.md#api-Interval)、[MeanTimeBlock](chronaxis.core.time_reduction.md#api-MeanTimeBlock)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ReferenceIntegralSum](chronaxis.core.integral_sum_reference.md#api-ReferenceIntegralSum)、[ReferenceMoments](chronaxis.core.moments_reference.md#api-ReferenceMoments)、[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)、[TimeCalculationFacts](chronaxis.core.time_reduction.md#api-TimeCalculationFacts)、[TimeReductionResult](chronaxis.core.time_reduction.md#api-TimeReductionResult)

## 对象导航

|对象|用途|
|---|---|
|[`ReferenceTimeReduction`](#api-ReferenceTimeReduction)|保留有限数值状态，第一遍与第二遍的mean实例不能混用。|
|[`ReferenceTimeReduction.__init__`](#api-ReferenceTimeReduction-__init__)|检查明确配置，再建立本后端有限状态。|
|[`ReferenceTimeReduction.selected_weight_seconds`](#api-ReferenceTimeReduction-selected_weight_seconds)|读取周期模式的必要累计权重。|
|[`ReferenceTimeReduction.selected_duration_ns`](#api-ReferenceTimeReduction-selected_duration_ns)|读取累计已选时长。|
|[`ReferenceTimeReduction.value_valid_duration_ns`](#api-ReferenceTimeReduction-value_valid_duration_ns)|读取累计有效时长。|
|[`ReferenceTimeReduction.push`](#api-ReferenceTimeReduction-push)|处理当前数据块并返回覆盖统计；处理后只保留累计状态，不保存此前整列输入。|
|[`ReferenceTimeReduction.finish`](#api-ReferenceTimeReduction-finish)|仅完整调用者确认后生成数值快照，最终转换一次。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from math import isfinite
from .calculation_output_reference import convert_result_reference
from .integral_sum_reference import ReferenceIntegralSum
from .moments import TIME_MOMENTS
from .moments_reference import ReferenceMoments
from .models import Interval
from .numeric import ScalarValue, to_float_reference
from .types import QualityFlag as Q
from .time_reduction import TimeCalculationFacts, TimeReductionResult, require_time_config, require_time_series, require_time_options
from .record_intervals import clipped_record_seconds
from .time_reduction import MeanTimeBlock
from .mean_weights_reference import normalized_mean_terms
```

</details>

<a id="api-ReferenceTimeReduction"></a>
## `ReferenceTimeReduction`

保留有限数值状态，第一遍与第二遍的mean实例不能混用。

极值只保留一个原生候选，actual时长只保留整数；周期权重与均值误差项
分别受partial_limit限制，原调用方的费用估算不能直接沿用到新周期模式。
finish为不破坏状态的快照，未指定均值全窗分母时禁止生成候选数值。

```python
ReferenceTimeReduction(spec, input_unit, dtype, *, selected_duration_ns=None, partial_limit=4096, step_ns=None, selected_weight_seconds=None)
```


源码：[`src/chronaxis/core/time_reduction_reference.py:30`](../../../src/chronaxis/core/time_reduction_reference.py#L30)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ReferenceTimeReduction-__init__"></a>
### `ReferenceTimeReduction.__init__`

检查明确配置，再建立本后端有限状态。

```python
ReferenceTimeReduction.__init__(spec, input_unit, dtype, *, selected_duration_ns=None, partial_limit=4096, step_ns=None, selected_weight_seconds=None)
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

配置或分配错误原样传播。

源码：[`src/chronaxis/core/time_reduction_reference.py:38`](../../../src/chronaxis/core/time_reduction_reference.py#L38)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ReferenceTimeReduction-selected_weight_seconds"></a>
### `ReferenceTimeReduction.selected_weight_seconds`

读取周期模式的必要累计权重。

```python
ReferenceTimeReduction.selected_weight_seconds
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

float或不适用None。

#### 异常说明

数值故障。

源码：[`src/chronaxis/core/time_reduction_reference.py:62`](../../../src/chronaxis/core/time_reduction_reference.py#L62)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ReferenceTimeReduction-selected_duration_ns"></a>
### `ReferenceTimeReduction.selected_duration_ns`

读取累计已选时长。

```python
ReferenceTimeReduction.selected_duration_ns
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

原生int纳秒。

#### 异常说明

无。

源码：[`src/chronaxis/core/time_reduction_reference.py:72`](../../../src/chronaxis/core/time_reduction_reference.py#L72)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ReferenceTimeReduction-value_valid_duration_ns"></a>
### `ReferenceTimeReduction.value_valid_duration_ns`

读取累计有效时长。

```python
ReferenceTimeReduction.value_valid_duration_ns
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

原生int纳秒。

#### 异常说明

无。

源码：[`src/chronaxis/core/time_reduction_reference.py:77`](../../../src/chronaxis/core/time_reduction_reference.py#L77)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ReferenceTimeReduction-push"></a>
### `ReferenceTimeReduction.push`

处理当前数据块并返回覆盖统计；处理后只保留累计状态，不保存此前整列输入。

```python
ReferenceTimeReduction.push(series, *, valid_until_ns=None, retain_unknown_ranges=True, retain_mean_terms=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`series`|CalculationSeries|是|无|位置或关键字。本次要处理的一块时间和值，单位、dtype和绑定必须与构造时一致。带条件的计算还需要与值对齐的BOOL条件；push处理当前块后保留累计结果，下一块可继续调用。|
|`valid_until_ns`|Sequence[int &#124; None] &#124; None|否|None|仅关键字。每个值按真实时间计算的有效截止，单位纳秒；None沿原有效范围，不按固定周期延长旧值寿命。|
|`retain_unknown_ranges`|bool|否|True|仅关键字。是否收集未知区间列表；关闭时仍计算未知对数值和状态的影响，但不建立该区间明细。|
|`retain_mean_terms`|bool|否|False|仅关键字。是否保留本批均值计算需要的值和权重；False从构造处跳过这些项。|

#### 返回说明

TimeCalculationFacts；mean权重故障另记数值失败，不改变有效覆盖。
    step_ns模式只接受驱动真实点，不把合成TTL/窗口点当新周期。

#### 异常说明

结构、身份、容量或分配错误原样传播；外层不得继续使用异常前缀。

本函数直接报告的具体错误：

- `ValueError`：时间归约不能跨绑定身份累计。

源码：[`src/chronaxis/core/time_reduction_reference.py:81`](../../../src/chronaxis/core/time_reduction_reference.py#L81)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ReferenceTimeReduction-finish"></a>
### `ReferenceTimeReduction.finish`

仅完整调用者确认后生成数值快照，最终转换一次。

```python
ReferenceTimeReduction.finish()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

TimeReductionResult，覆盖分类由外层负责。

#### 异常说明

RuntimeError为mean第一遍；ValueError为第二遍有效时长与分母不符；
    配置/分配错误传播，数值范围错误按calculation_failed返回。

源码：[`src/chronaxis/core/time_reduction_reference.py:175`](../../../src/chronaxis/core/time_reduction_reference.py#L175)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
