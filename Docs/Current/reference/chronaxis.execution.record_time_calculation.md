# `chronaxis.execution.record_time_calculation`

用有限记录计算时间统计和真实样本统计；仅时间均值暂存必要值/权重。

输入与RecordIntegral共享点缓冲、递增时间和失效处理。复用原时间/样本数值核；
样本统计保真实更新标志，不把条件/TTL更新当新样本，样本均值使用原序求和。
均值首遍仅写值与权重，实际权重为int64纳秒，周期权重为float秒；
次遍按已知总权重规范化，避免先求面积溢出。
临时文件由本owner关闭时删除，不默认留现场；结果不附历史、贡献或时间对照。
调用者必须先确认来源EOF及关闭成功再finish，本对象不替代公共AnalysisRunner发布。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[BudgetExceededError](chronaxis.results.errors.md#api-BudgetExceededError)、[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)、[CalculationSeries](chronaxis.core.calculations.md#api-CalculationSeries)、[D](chronaxis.core.types.md#api-SignalDType)、[Interval](chronaxis.core.models.md#api-Interval)、[NumpyConditionalTimeReduction](chronaxis.core.conditional_time_reduction_numpy.md#api-NumpyConditionalTimeReduction)、[NumpyIntegralSum](chronaxis.core.integral_sum_numpy.md#api-NumpyIntegralSum)、[NumpySampleReduction](chronaxis.core.sample_reduction_numpy.md#api-NumpySampleReduction)、[NumpyTimeReduction](chronaxis.core.time_reduction_numpy.md#api-NumpyTimeReduction)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[RecordPointBuffer](chronaxis.execution.record_point_buffer.md#api-RecordPointBuffer)、[ReferenceConditionalTimeReduction](chronaxis.core.conditional_time_reduction_reference.md#api-ReferenceConditionalTimeReduction)、[ReferenceIntegralSum](chronaxis.core.integral_sum_reference.md#api-ReferenceIntegralSum)、[ReferenceSampleReduction](chronaxis.core.sample_reduction_reference.md#api-ReferenceSampleReduction)、[ReferenceTimeReduction](chronaxis.core.time_reduction_reference.md#api-ReferenceTimeReduction)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)、[TimeReductionResult](chronaxis.core.time_reduction.md#api-TimeReductionResult)

## 对象导航

|对象|用途|
|---|---|
|[`RecordTimeResult`](#api-RecordTimeResult)|保存时间统计的必要输出，整数极值不转成浮点数。|
|[`RecordTimeCalculation`](#api-RecordTimeCalculation)|拥有一份点缓冲、数值状态及可选均值临时文件，失败后只能清理。|
|[`RecordTimeCalculation.__init__`](#api-RecordTimeCalculation-__init__)|预付有限状态，均值的文件延迟到首批有效项才创建。|
|[`RecordTimeCalculation._append_mean`](#api-RecordTimeCalculation-_append_mean)|只写本批选中的必要均值项；费用先预约，不缓存完整输入。|
|[`RecordTimeCalculation._flush`](#api-RecordTimeCalculation-_flush)|在共享预算内分块处理样本统计，保留每块的共同右端。|
|[`RecordTimeCalculation._flush_block`](#api-RecordTimeCalculation-_flush_block)|计算完整记录对，只留共享右端；均值写选中项，其他指标不写盘。|
|[`RecordTimeCalculation._finish_mean`](#api-RecordTimeCalculation-_finish_mean)|分批回读必要数值/权重，复用原归一化及原序求和，最终只换单位一次。|
|[`RecordTimeCalculation.finish`](#api-RecordTimeCalculation-finish)|上游确认EOF后结算，并关闭删除均值临时文件，再交付精简结果。|
|[`RecordTimeCalculation.closed`](#api-RecordTimeCalculation-closed)|读取自有文件/费用是否全部释放。|
|[`RecordTimeCalculation.close`](#api-RecordTimeCalculation-close)|清理自有数值状态和临时文件，释放失败保留重试入口，不碰输入文件。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..core.moments import SAMPLE_MOMENTS
from ..core.quantiles import SAMPLE_QUANTILES
from dataclasses import dataclass
from pathlib import Path
from struct import Struct
from tempfile import TemporaryFile
from ..core.calculations import CalculationDefinition, CalculationSeries, classify_calculation_value
from ..core.calculations import classify_coverage
from ..core.models import Interval
from ..core.types import SignalDType as D, QualityFlag as Q
from ..core.time_reduction import require_time_config, TimeReductionResult
from ..core.time_reduction_reference import ReferenceTimeReduction
from ..core.time_reduction_numpy import NumpyTimeReduction
from ..core.conditional_time_reduction_reference import ReferenceConditionalTimeReduction
from ..core.conditional_time_reduction_numpy import NumpyConditionalTimeReduction
from ..core.integral_sum_reference import ReferenceIntegralSum
from ..core.integral_sum_numpy import NumpyIntegralSum
from ..core.mean_weights_reference import normalized_mean_terms as reference_mean
from ..core.mean_weights_numpy import normalized_mean_terms as numpy_mean
from ..results.budget import ResourceBudget, _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..results.errors import BudgetExceededError
from .history import _metadata_bytes
from .record_point_buffer import RecordPointBuffer
from ..core.sample_reduction import require_sample_config
from ..core.calculation_output_reference import convert_result_reference
from ..core.calculation_output_numpy import convert_result_numpy
from ..core.sample_reduction_reference import ReferenceSampleReduction
from ..core.sample_reduction_numpy import NumpySampleReduction
from .record_sample_series import sample_series
```

</details>

<a id="api-RecordTimeResult"></a>
## `RecordTimeResult`

保存时间统计的必要输出，整数极值不转成浮点数。

```python
class RecordTimeResult
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; float &#124; None|是|无|计算所得的有限数值；None表示不能给出数值，需同时读取状态和原因，不能替换成0。|
|`unit`|str|是|无|物理量或结果单位，如W、J、s；按本接口的单位检查与换算规则使用。|
|`status`|str|是|无|complete表示结果完整，partial表示只包含可核实部分，indeterminate表示无法确定数值。|
|`reason`|str|是|无|说明数值完整、部分可用或不能确定的具体原因；与status一起读取，不能只看数值。|
|`quality`|[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)|是|无|该值或结果的质量位组合；缺失、过期等原因不能通过清零掩盖。|
|`coverage_status`|str &#124; None|否|None|对明确配置的覆盖门槛给出的结论；独立于数值本身的complete/partial/indeterminate状态。|

源码：[`src/chronaxis/execution/record_time_calculation.py:46`](../../../src/chronaxis/execution/record_time_calculation.py#L46)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordTimeCalculation"></a>
## `RecordTimeCalculation`

拥有一份点缓冲、数值状态及可选均值临时文件，失败后只能清理。

```python
RecordTimeCalculation(budget, spec, input_unit, dtype, step_ns, *, backend='numpy', batch_intervals=64, partial_limit=4096, conditioned=False, work_dir=None, hosted=None)
```

继承关系：[RecordPointBuffer](chronaxis.execution.record_point_buffer.md#api-RecordPointBuffer)。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/execution/record_time_calculation.py:57`](../../../src/chronaxis/execution/record_time_calculation.py#L57)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordTimeCalculation-__init__"></a>
### `RecordTimeCalculation.__init__`

预付有限状态，均值的文件延迟到首批有效项才创建。

```python
RecordTimeCalculation.__init__(budget, spec, input_unit, dtype, step_ns, *, backend='numpy', batch_intervals=64, partial_limit=4096, conditioned=False, work_dir=None, hosted=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)|是|无|位置或关键字。本次分析共享的资源用量记录；新对象先预约所需内存和磁盘额度，关闭时归还自己的内存费用。|
|`spec`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|位置或关键字。已核对的指标声明，包含算子、实际请求范围、数据不全时的处理方式和输出单位。|
|`input_unit`|str|是|无|位置或关键字。送入数值核的原计算值单位，用于校验输出单位以及积分的单位转换。|
|`dtype`|SignalDType|是|无|位置或关键字。计算值的数据类型；决定整数范围、浮点计算或枚举处理，不得隐式转float丢失整数精度。|
|`step_ns`|int &#124; None|是|无|位置或关键字。所选固定或DBC周期，单位纳秒且大于0；None表示采用实际时间间隔，不生成第二套时间坐标。|
|`backend`|str|否|'numpy'|仅关键字。计算实现：reference使用独立参考核，numpy使用数组核；两者遵守相同的业务和缺失数据规则。|
|`batch_intervals`|int|否|64|仅关键字。本对象一次交给数值核的相邻区间上限；为正整数，并受共享内存预算约束。|
|`partial_limit`|int|否|4096|仅关键字。一次数值归约允许保留的中间部分和数量上限，防止累计状态无界增长。|
|`conditioned`|bool|否|False|仅关键字。是否同时保存和处理筛选条件；False时不创建无用条件列或条件历史。|
|`work_dir`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) &#124; None|否|None|仅关键字。time_weighted_mean必须提供已存在的专用目录保存必要均值项；其他算子可省略，默认None。|
|`hosted`|ReductionSpec &#124; None|否|None|仅关键字。按宿主操作名解析的注册描述；省略时使用内置统计实现。|

#### 返回说明

新owner。

#### 异常说明

配置/预算失败；持续清理故障附record_time_cleanup_owner。

源码：[`src/chronaxis/execution/record_time_calculation.py:60`](../../../src/chronaxis/execution/record_time_calculation.py#L60)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordTimeCalculation-_append_mean"></a>
### `RecordTimeCalculation._append_mean`

只写本批选中的必要均值项；费用先预约，不缓存完整输入。

```python
RecordTimeCalculation._append_mean(values, weights)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`values`|Sequence[int &#124; float]|是|无|位置或关键字。当前有限批的有效数值，与权重按位置一一对应；按原序归约。|
|`weights`|Sequence[int &#124; float]|是|无|位置或关键字。与数值一一对应的非负权重；实际模式为纳秒，固定或DBC模式为所选周期的秒数。|

#### 返回说明

None。

#### 异常说明

配额、短写、IO或取消传播。

源码：[`src/chronaxis/execution/record_time_calculation.py:126`](../../../src/chronaxis/execution/record_time_calculation.py#L126)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordTimeCalculation-_flush"></a>
### `RecordTimeCalculation._flush`

在共享预算内分块处理样本统计，保留每块的共同右端。

```python
RecordTimeCalculation._flush()
```

参数：无显式参数。


#### 参数说明

无，使用已预付的点缓冲。

#### 返回说明

None。

#### 异常说明

最小两点工作区也放不下时报告计算项与用途；数值、取消原错传播。
不降低每行估算、不放宽限额，也不丢弃、重排或重复累计真实样本。

源码：[`src/chronaxis/execution/record_time_calculation.py:155`](../../../src/chronaxis/execution/record_time_calculation.py#L155)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordTimeCalculation-_flush_block"></a>
### `RecordTimeCalculation._flush_block`

计算完整记录对，只留共享右端；均值写选中项，其他指标不写盘。

```python
RecordTimeCalculation._flush_block()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

预算/数值结构/IO/取消，失败后不得交付前缀。

源码：[`src/chronaxis/execution/record_time_calculation.py:190`](../../../src/chronaxis/execution/record_time_calculation.py#L190)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordTimeCalculation-_finish_mean"></a>
### `RecordTimeCalculation._finish_mean`

分批回读必要数值/权重，复用原归一化及原序求和，最终只换单位一次。

```python
RecordTimeCalculation._finish_mean()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

TimeReductionResult。

#### 异常说明

临时数据短缺/多出、IO、预算或取消。

源码：[`src/chronaxis/execution/record_time_calculation.py:242`](../../../src/chronaxis/execution/record_time_calculation.py#L242)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordTimeCalculation-finish"></a>
### `RecordTimeCalculation.finish`

上游确认EOF后结算，并关闭删除均值临时文件，再交付精简结果。

```python
RecordTimeCalculation.finish()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

RecordTimeResult，重复调用同一结果。

#### 异常说明

失败拒绝前缀，close可重试。

源码：[`src/chronaxis/execution/record_time_calculation.py:292`](../../../src/chronaxis/execution/record_time_calculation.py#L292)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordTimeCalculation-closed"></a>
### `RecordTimeCalculation.closed`

读取自有文件/费用是否全部释放。

```python
RecordTimeCalculation.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

bool。

#### 异常说明

无。

源码：[`src/chronaxis/execution/record_time_calculation.py:336`](../../../src/chronaxis/execution/record_time_calculation.py#L336)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordTimeCalculation-close"></a>
### `RecordTimeCalculation.close`

清理自有数值状态和临时文件，释放失败保留重试入口，不碰输入文件。

```python
RecordTimeCalculation.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

文件关闭/费用释放失败可重试；重复关闭安全。

源码：[`src/chronaxis/execution/record_time_calculation.py:340`](../../../src/chronaxis/execution/record_time_calculation.py#L340)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
