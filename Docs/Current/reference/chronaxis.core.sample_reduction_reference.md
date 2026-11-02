# chronaxis.core.sample_reduction_reference

逐个处理真实更新，计算样本最小值、最大值和算术平均值，供NumPy实现对照。整数极值保留整数精度；平均值按输入顺序累加。保持出来的值和窗口边界不算新样本。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)、[Interval](chronaxis.core.models.md#api-Interval)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ReferenceIntegralSum](chronaxis.core.integral_sum_reference.md#api-ReferenceIntegralSum)、[SampleCalculationFacts](chronaxis.core.sample_reduction.md#api-SampleCalculationFacts)、[SampleReductionResult](chronaxis.core.sample_reduction.md#api-SampleReductionResult)、[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)

## 对象导航

|对象|用途|
|---|---|
|[`ReferenceSampleReduction`](#api-ReferenceSampleReduction)|保存单原生候选、真实样本计数与有界误差项，不存历史输入列。|
|[`ReferenceSampleReduction.__init__`](#api-ReferenceSampleReduction-__init__)|核对原配置并建立本参考后端有限状态。|
|[`ReferenceSampleReduction.selected_duration_ns`](#api-ReferenceSampleReduction-selected_duration_ns)|读取累计TRUE值有效时长。|
|[`ReferenceSampleReduction.value_valid_duration_ns`](#api-ReferenceSampleReduction-value_valid_duration_ns)|读取累计值有效时长。|
|[`ReferenceSampleReduction.valid_sample_count`](#api-ReferenceSampleReduction-valid_sample_count)|读取有效真实样本数。|
|[`ReferenceSampleReduction.push`](#api-ReferenceSampleReduction-push)|处理下一块数据，更新数值和条件的覆盖统计，并累计真实更新的样本；保持出来的时间段不增加样本数。|
|[`ReferenceSampleReduction.finish`](#api-ReferenceSampleReduction-finish)|完成原单位总和、除真实样本数，再仅一次转换输出单位。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from math import isfinite
from .integral_sum_reference import ReferenceIntegralSum
from .calculations import merge_ranges
from .models import Interval
from .numeric import ScalarValue, to_float_reference
from .sample_reduction import SampleCalculationFacts, SampleReductionResult, require_sample_config, require_sample_series
from .types import QualityFlag as Q, SignalDType as D
```

</details>

<a id="api-ReferenceSampleReduction"></a>
## `ReferenceSampleReduction`

保存单原生候选、真实样本计数与有界误差项，不存历史输入列。

```python
ReferenceSampleReduction(spec, input_unit, dtype, *, partial_limit=4096)
```


源码：[`src/chronaxis/core/sample_reduction_reference.py:20`](../../../src/chronaxis/core/sample_reduction_reference.py#L20)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ReferenceSampleReduction-__init__"></a>
### `ReferenceSampleReduction.__init__`

核对原配置并建立本参考后端有限状态。

```python
ReferenceSampleReduction.__init__(spec, input_unit, dtype, *, partial_limit=4096)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|CalculationDefinition|是|无|位置或关键字。本次指标的设置，包括统计时间范围、计算种类、输出单位及数据不全时的处理方式。该对象由调用方先构造；本函数不会重新读取JSON配置。|
|`input_unit`|str|是|无|位置或关键字。输入信号当前使用的单位，例如功率填"W"。函数据此检查输出单位的换算关系，不会仅凭这个字符串修改样本值。|
|`dtype`|SignalDType|是|无|位置或关键字。输入值的逻辑类型，传SignalDType成员；整数极值计算保持整数精度，均值按本函数说明转换为浮点。|
|`partial_limit`|int|否|4096|仅关键字。大于0的整数，限制浮点累加时保留的误差补偿项数量。默认4096；它不是样本数上限，也不是允许出现多少次错误。超过容量会报错。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

配置或分配错误传播。

源码：[`src/chronaxis/core/sample_reduction_reference.py:23`](../../../src/chronaxis/core/sample_reduction_reference.py#L23)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ReferenceSampleReduction-selected_duration_ns"></a>
### `ReferenceSampleReduction.selected_duration_ns`

读取累计TRUE值有效时长。

```python
ReferenceSampleReduction.selected_duration_ns
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

原生int纳秒。

#### 异常说明

无。

源码：[`src/chronaxis/core/sample_reduction_reference.py:37`](../../../src/chronaxis/core/sample_reduction_reference.py#L37)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ReferenceSampleReduction-value_valid_duration_ns"></a>
### `ReferenceSampleReduction.value_valid_duration_ns`

读取累计值有效时长。

```python
ReferenceSampleReduction.value_valid_duration_ns
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

原生int纳秒。

#### 异常说明

无。

源码：[`src/chronaxis/core/sample_reduction_reference.py:42`](../../../src/chronaxis/core/sample_reduction_reference.py#L42)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ReferenceSampleReduction-valid_sample_count"></a>
### `ReferenceSampleReduction.valid_sample_count`

读取有效真实样本数。

```python
ReferenceSampleReduction.valid_sample_count
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

原生int。

#### 异常说明

无。

源码：[`src/chronaxis/core/sample_reduction_reference.py:47`](../../../src/chronaxis/core/sample_reduction_reference.py#L47)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ReferenceSampleReduction-push"></a>
### `ReferenceSampleReduction.push`

处理下一块数据，更新数值和条件的覆盖统计，并累计真实更新的样本；保持出来的时间段不增加样本数。

```python
ReferenceSampleReduction.push(series)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`series`|CalculationSeries|是|无|位置或关键字。本次要处理的一块时间和值，单位、dtype和绑定必须与构造时一致。带条件的计算还需要与值对齐的BOOL条件；push处理当前块后保留累计结果，下一块可继续调用。|

#### 返回说明

SampleCalculationFacts；mean精度失败进入输入覆盖，求和故障不改覆盖。

#### 异常说明

结构、身份、容量、分配或取消传播；外层异常后不能接着使用前缀状态。

本函数直接报告的具体错误：

- `ValueError`：样本归约不能跨绑定身份累计。

源码：[`src/chronaxis/core/sample_reduction_reference.py:51`](../../../src/chronaxis/core/sample_reduction_reference.py#L51)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ReferenceSampleReduction-finish"></a>
### `ReferenceSampleReduction.finish`

完成原单位总和、除真实样本数，再仅一次转换输出单位。

```python
ReferenceSampleReduction.finish()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

SampleReductionResult快照，不清空状态或分类覆盖政策。

#### 异常说明

配置/分配错误传播；原序和、除法、精度或换算故障返回None及质量。

源码：[`src/chronaxis/core/sample_reduction_reference.py:119`](../../../src/chronaxis/core/sample_reduction_reference.py#L119)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
