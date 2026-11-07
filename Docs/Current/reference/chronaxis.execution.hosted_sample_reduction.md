# `chronaxis.execution.hosted_sample_reduction`

把有限真实样本块交给明确注册的宿主归约，复用原半开选择、覆盖与独立数值后端。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[HostedReduction](chronaxis.extension_runtime.md#api-HostedReduction)、[NumpySampleReduction](chronaxis.core.sample_reduction_numpy.md#api-NumpySampleReduction)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ReferenceSampleReduction](chronaxis.core.sample_reduction_reference.md#api-ReferenceSampleReduction)、[SampleReductionResult](chronaxis.core.sample_reduction.md#api-SampleReductionResult)

## 对象导航

|对象|用途|
|---|---|
|[`HostedSampleReduction`](#api-HostedSampleReduction)|一个会话、事件或窗口持有一个插件状态；插件不决定是否选入样本及结果显示单位。|
|[`HostedSampleReduction.__init__`](#api-HostedSampleReduction-__init__)|创建所选后端的覆盖计算器及宿主状态。|
|[`HostedSampleReduction.push`](#api-HostedSampleReduction-push)|沿同一选中掩码消费并返回覆盖事实。|
|[`HostedSampleReduction.finish`](#api-HostedSampleReduction-finish)|无参与值保留空结果，输出单位只变换一次。|
|[`HostedSampleReduction.close`](#api-HostedSampleReduction-close)|未正常结束时通知取消，释放宿主和覆盖状态。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import replace
from ..core.calculation_output_numpy import convert_result_numpy
from ..core.calculation_output_reference import convert_result_reference
from ..core.sample_reduction import SampleReductionResult
from ..core.sample_reduction_numpy import NumpySampleReduction
from ..core.sample_reduction_reference import ReferenceSampleReduction
from ..core.types import QualityFlag as Q
from ..extension_runtime import HostedReduction
from ..results.budget import _cleanup_owner
```

</details>

<a id="api-HostedSampleReduction"></a>
## `HostedSampleReduction`

一个会话、事件或窗口持有一个插件状态；插件不决定是否选入样本及结果显示单位。

```python
HostedSampleReduction(spec, input_unit, dtype, descriptor, conversion, backend, budget, partial_limit)
```


源码：[`src/chronaxis/execution/hosted_sample_reduction.py:14`](../../../src/chronaxis/execution/hosted_sample_reduction.py#L14)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HostedSampleReduction-__init__"></a>
### `HostedSampleReduction.__init__`

创建所选后端的覆盖计算器及宿主状态。

```python
HostedSampleReduction.__init__(spec, input_unit, dtype, descriptor, conversion, backend, budget, partial_limit)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|CalculationDefinition|是|无|位置或关键字。本范围的统计请求，包括样本选择、窗口、输出单位及部分覆盖政策。|
|`input_unit`|str|是|无|位置或关键字。实际交给宿主样本端口之前已核对的输入单位。|
|`dtype`|SignalDType|是|无|位置或关键字。本次输入表达式的静态类型，用于覆盖计算及宿主端口检查。|
|`descriptor`|ReductionSpec|是|无|位置或关键字。与配置操作同名的宿主归约注册，包含工厂与固定输入/输出约定。|
|`conversion`|CalculationConversion|是|无|位置或关键字。把宿主完成的标量从其输出端口单位换成用户所需单位。|
|`backend`|str|是|无|位置或关键字。选择实际消费tuple的reference工厂或消费数值列的numpy工厂。|
|`budget`|ResourceBudget|是|无|位置或关键字。与本次分析共享的RAM账本，为宿主状态和动态空间预付、退还费用。|
|`partial_limit`|int|是|无|位置或关键字。传给样本覆盖归约器的正整数误差项容量上限，沿用既有样本归约入口。|

#### 返回说明

独立归约owner。

#### 异常说明

宿主工厂或预算失败转交可重试清理句柄。

源码：[`src/chronaxis/execution/hosted_sample_reduction.py:17`](../../../src/chronaxis/execution/hosted_sample_reduction.py#L17)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HostedSampleReduction-push"></a>
### `HostedSampleReduction.push`

沿同一选中掩码消费并返回覆盖事实。

```python
HostedSampleReduction.push(series)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`series`|CalculationSeries|是|无|位置或关键字。当前有限时间块的数值、条件、真实更新标志和观测范围。|

#### 返回说明

本块 facts。

#### 异常说明

回调或输入错误。

源码：[`src/chronaxis/execution/hosted_sample_reduction.py:36`](../../../src/chronaxis/execution/hosted_sample_reduction.py#L36)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HostedSampleReduction-finish"></a>
### `HostedSampleReduction.finish`

无参与值保留空结果，输出单位只变换一次。

```python
HostedSampleReduction.finish()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

SampleReductionResult。

#### 异常说明

回调或转换错误。

源码：[`src/chronaxis/execution/hosted_sample_reduction.py:40`](../../../src/chronaxis/execution/hosted_sample_reduction.py#L40)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HostedSampleReduction-close"></a>
### `HostedSampleReduction.close`

未正常结束时通知取消，释放宿主和覆盖状态。

```python
HostedSampleReduction.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

清理失败可重试。

源码：[`src/chronaxis/execution/hosted_sample_reduction.py:54`](../../../src/chronaxis/execution/hosted_sample_reduction.py#L54)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
