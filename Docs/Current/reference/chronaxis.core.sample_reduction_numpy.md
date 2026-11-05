# `chronaxis.core.sample_reduction_numpy`

用NumPy从真实更新中计算样本最小值、最大值和算术平均值。筛选条件为真且数值有效的样本才参与计算；条件未知会单独记录。结果累计器只保留后续计算需要的状态，不保存此前每个样本。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ExactQuantileBuffer](chronaxis.core.quantiles.md#api-ExactQuantileBuffer)、[Interval](chronaxis.core.models.md#api-Interval)、[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)、[NumpyIntegralSum](chronaxis.core.integral_sum_numpy.md#api-NumpyIntegralSum)、[NumpyMoments](chronaxis.core.moments_numpy.md#api-NumpyMoments)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[SampleCalculationFacts](chronaxis.core.sample_reduction.md#api-SampleCalculationFacts)、[SampleReductionResult](chronaxis.core.sample_reduction.md#api-SampleReductionResult)

## 对象导航

|对象|用途|
|---|---|
|[`NumpySampleReduction`](#api-NumpySampleReduction)|累计当前范围的真实样本；分位数仅在请求时按共享预算保留原dtype样本。|
|[`NumpySampleReduction.__init__`](#api-NumpySampleReduction-__init__)|检查原配置并建立本数组后端有限状态。|
|[`NumpySampleReduction.selected_duration_ns`](#api-NumpySampleReduction-selected_duration_ns)|读取累计TRUE有效保持时长。|
|[`NumpySampleReduction.value_valid_duration_ns`](#api-NumpySampleReduction-value_valid_duration_ns)|读取累计值有效时长。|
|[`NumpySampleReduction.valid_sample_count`](#api-NumpySampleReduction-valid_sample_count)|读取有效真实样本数。|
|[`NumpySampleReduction.push`](#api-NumpySampleReduction-push)|独立数组计算双覆盖、真实样本掩码并推进对应候选。|
|[`NumpySampleReduction.finish`](#api-NumpySampleReduction-finish)|完成原单位样本总和后除计数，并仅一次转换最终单位。|
|[`NumpySampleReduction.close`](#api-NumpySampleReduction-close)|退回按需分位数存储；无动态存储的样本归约无需释放费用。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .moments import SAMPLE_MOMENTS
from .quantiles import SAMPLE_QUANTILES, ExactQuantileBuffer
from .moments_numpy import NumpyMoments
from .calculation_output_numpy import convert_result_numpy
from .integral_sum_numpy import NumpyIntegralSum
from .calculations import merge_ranges
from .models import Interval
from .numeric_numpy import DTYPES, NumericArray, to_float_numpy
from .sample_reduction import SampleCalculationFacts, SampleReductionResult, require_sample_config, require_sample_series
from .types import QualityFlag as Q
```

</details>

<a id="api-NumpySampleReduction"></a>
## `NumpySampleReduction`

累计当前范围的真实样本；分位数仅在请求时按共享预算保留原dtype样本。

```python
NumpySampleReduction(spec, input_unit, dtype, *, partial_limit=4096, quantile_budget=None)
```


源码：[`src/chronaxis/core/sample_reduction_numpy.py:24`](../../../src/chronaxis/core/sample_reduction_numpy.py#L24)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-NumpySampleReduction-__init__"></a>
### `NumpySampleReduction.__init__`

检查原配置并建立本数组后端有限状态。

```python
NumpySampleReduction.__init__(spec, input_unit, dtype, *, partial_limit=4096, quantile_budget=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|CalculationDefinition|是|无|位置或关键字。本次指标的设置，包括统计时间范围、计算种类、输出单位及数据不全时的处理方式。该对象由调用方先构造；本函数不会重新读取JSON配置。|
|`input_unit`|str|是|无|位置或关键字。输入信号当前使用的单位，例如功率填"W"。函数据此检查输出单位的换算关系，不会仅凭这个字符串修改样本值。|
|`dtype`|SignalDType|是|无|位置或关键字。输入值的逻辑类型，传SignalDType成员；整数极值计算保持整数精度，均值按本函数说明转换为浮点。|
|`partial_limit`|int|否|4096|仅关键字。大于0的整数，限制浮点累加时保留的误差补偿项数量。默认4096；它不是样本数上限，也不是允许出现多少次错误。超过容量会报错。|
|`quantile_budget`|ResourceBudget &#124; None|否|None|仅关键字。可选的共享排序预算，仅配置精确分位数或中位数时用于保存所选样本。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

配置、分配错误传播。

源码：[`src/chronaxis/core/sample_reduction_numpy.py:27`](../../../src/chronaxis/core/sample_reduction_numpy.py#L27)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-NumpySampleReduction-selected_duration_ns"></a>
### `NumpySampleReduction.selected_duration_ns`

读取累计TRUE有效保持时长。

```python
NumpySampleReduction.selected_duration_ns
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

原生int纳秒。

#### 异常说明

无。

源码：[`src/chronaxis/core/sample_reduction_numpy.py:47`](../../../src/chronaxis/core/sample_reduction_numpy.py#L47)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-NumpySampleReduction-value_valid_duration_ns"></a>
### `NumpySampleReduction.value_valid_duration_ns`

读取累计值有效时长。

```python
NumpySampleReduction.value_valid_duration_ns
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

原生int纳秒。

#### 异常说明

无。

源码：[`src/chronaxis/core/sample_reduction_numpy.py:52`](../../../src/chronaxis/core/sample_reduction_numpy.py#L52)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-NumpySampleReduction-valid_sample_count"></a>
### `NumpySampleReduction.valid_sample_count`

读取有效真实样本数。

```python
NumpySampleReduction.valid_sample_count
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

原生int。

#### 异常说明

无。

源码：[`src/chronaxis/core/sample_reduction_numpy.py:57`](../../../src/chronaxis/core/sample_reduction_numpy.py#L57)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-NumpySampleReduction-push"></a>
### `NumpySampleReduction.push`

独立数组计算双覆盖、真实样本掩码并推进对应候选。

```python
NumpySampleReduction.push(series, *, sample_consumer=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`series`|CalculationSeries|是|无|位置或关键字。本次要处理的一块时间和值，单位、dtype和绑定必须与构造时一致。带条件的计算还需要与值对齐的BOOL条件；push处理当前块后保留累计结果，下一块可继续调用。|
|`sample_consumer`|Callable[[[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)], None] &#124; None|否|None|仅关键字。可选宿主数组消费入口；把同一真实更新掩码选中的行组成带有明确类型的列传入。|

#### 返回说明

SampleCalculationFacts；mean精度入值覆盖，数值归约故障不改覆盖。

#### 异常说明

结构、身份、容量、分配或取消传播；异常后外层只能清理owner。
内存: 新列形状N/N-1或当前所选样本数，当前push存活，不修改输入列。

本函数直接报告的具体错误：

- `ValueError`：样本归约不能跨绑定身份累计。

源码：[`src/chronaxis/core/sample_reduction_numpy.py:61`](../../../src/chronaxis/core/sample_reduction_numpy.py#L61)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-NumpySampleReduction-finish"></a>
### `NumpySampleReduction.finish`

完成原单位样本总和后除计数，并仅一次转换最终单位。

```python
NumpySampleReduction.finish()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

SampleReductionResult快照，覆盖政策由外层分类。

#### 异常说明

配置、分配或取消传播；原序和、除法、精度、换算故障写None与质量。

源码：[`src/chronaxis/core/sample_reduction_numpy.py:138`](../../../src/chronaxis/core/sample_reduction_numpy.py#L138)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-NumpySampleReduction-close"></a>
### `NumpySampleReduction.close`

退回按需分位数存储；无动态存储的样本归约无需释放费用。

```python
NumpySampleReduction.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

预算释放失败时保留可重试的子缓冲。

源码：[`src/chronaxis/core/sample_reduction_numpy.py:179`](../../../src/chronaxis/core/sample_reduction_numpy.py#L179)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
