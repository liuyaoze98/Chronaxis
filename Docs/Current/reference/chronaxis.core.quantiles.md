# `chronaxis.core.quantiles`

保存精确样本分位数的有限预算状态，结束时定位两个顺序统计值。

q为0或1时只维护原dtype的极值。其余q保留被选中的真实样本，增长前向
本次预算付款，排序临时空间另行预付并释放。标量及数组后端各自完成排序
和线性插值；本对象只共享寿命、秩、预算协议，不读取来源或生成临时文件。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)

## 对象导航

|对象|用途|
|---|---|
|[`quantile_probability`](#api-quantile_probability)|校验操作与概率的固定组合，返回精确的配置概率。|
|[`ExactQuantileBuffer`](#api-ExactQuantileBuffer)|保存单个统计范围的已选样本或端点极值；只持有自己预付的空间。|
|[`ExactQuantileBuffer.__init__`](#api-ExactQuantileBuffer-__init__)|配置确定的概率、输入dtype和真实后端，创建空存储。|
|[`ExactQuantileBuffer._reserve`](#api-ExactQuantileBuffer-_reserve)|在保存样本或创建排序副本之前申请空间，保留具体预算错误。|
|[`ExactQuantileBuffer.append`](#api-ExactQuantileBuffer-append)|累加一批真正选中的有效样本；空批直接返回。|
|[`ExactQuantileBuffer.finish`](#api-ExactQuantileBuffer-finish)|读取截至当前批次的分位数快照，不按块分别求分位数再合并。|
|[`ExactQuantileBuffer.close`](#api-ExactQuantileBuffer-close)|放弃样本并退回本实例的全部收费，释放被取消时可再次调用。|
|[`compute_quantile_series`](#api-compute_quantile_series)|把有时间轴的单块内存输入送入对应后端的精确样本归约器。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from fractions import Fraction
from math import isfinite
from .types import QualityFlag as Q, SignalDType as D
```

</details>

<a id="api-quantile_probability"></a>
## `quantile_probability`

校验操作与概率的固定组合，返回精确的配置概率。

```python
quantile_probability(operation, q)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`operation`|str|是|无|位置或关键字。精确样本统计名称，sample_quantile 使用显式概率，sample_median 固定中位数。|
|`q`|float &#124; int &#124; None|是|无|位置或关键字。有限概率，含端点 0 和 1。中位数必须传 None，其他分位数使用该值确定相邻秩。|

### 返回说明

Fraction；中位数固定为1/2，其他概率按配置值的十进制表示解释。

### 异常说明

ValueError为多余、缺失、非有限、越界或布尔概率。

源码：[`src/chronaxis/core/quantiles.py:16`](../../../src/chronaxis/core/quantiles.py#L16)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ExactQuantileBuffer"></a>
## `ExactQuantileBuffer`

保存单个统计范围的已选样本或端点极值；只持有自己预付的空间。

```python
ExactQuantileBuffer(operation, q, dtype, backend, budget=None)
```


源码：[`src/chronaxis/core/quantiles.py:33`](../../../src/chronaxis/core/quantiles.py#L33)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ExactQuantileBuffer-__init__"></a>
### `ExactQuantileBuffer.__init__`

配置确定的概率、输入dtype和真实后端，创建空存储。

```python
ExactQuantileBuffer.__init__(operation, q, dtype, backend, budget=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`operation`|str|是|无|位置或关键字。精确样本统计名称，sample_quantile 使用显式概率，sample_median 固定中位数。|
|`q`|float &#124; int &#124; None|是|无|位置或关键字。有限概率，含端点 0 和 1。中位数必须传 None，其他分位数使用该值确定相邻秩。|
|`dtype`|SignalDType|是|无|位置或关键字。经过单位与表达式类型检查的数值列类型，排序前保留原整数或浮点域。|
|`backend`|str|是|无|位置或关键字。选择 reference 标量排序或 numpy 原类型数组排序。|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget) &#124; None|否|None|位置或关键字。本次运行共享的资源用量记录，接收样本和排序临时空间都需预付。独立调用省略时采用默认预算。|

#### 返回说明

新缓冲。

#### 异常说明

非法参数在读取样本前失败。

源码：[`src/chronaxis/core/quantiles.py:36`](../../../src/chronaxis/core/quantiles.py#L36)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ExactQuantileBuffer-_reserve"></a>
### `ExactQuantileBuffer._reserve`

在保存样本或创建排序副本之前申请空间，保留具体预算错误。

```python
ExactQuantileBuffer._reserve(amount, slot)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`amount`|int|是|无|位置或关键字。本次追加进入账本的字节数，增长容量或准备排序前先预留。|
|`slot`|str|是|无|位置或关键字。当前缓冲记录本次持有的费用字段，以便按所属用途释放。|

#### 返回说明

None。

#### 异常说明

BudgetExceededError或取消原样传播，close可重试清理。

源码：[`src/chronaxis/core/quantiles.py:54`](../../../src/chronaxis/core/quantiles.py#L54)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ExactQuantileBuffer-append"></a>
### `ExactQuantileBuffer.append`

累加一批真正选中的有效样本；空批直接返回。

```python
ExactQuantileBuffer.append(values, mask=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`values`|Sequence[int &#124; float] &#124; numpy.ndarray|是|无|位置或关键字。新到的一批原类型真实样本。标量端传已选的值，数组端按同批掩码选择。|
|`mask`|numpy.ndarray &#124; None|否|None|位置或关键字。数组后端同长布尔掩码，真值指向应参与精确排序的有效样本。标量端省略。|

#### 返回说明

None。

#### 异常说明

值/掩码不符、预算不足、关闭后调用或分配失败。

源码：[`src/chronaxis/core/quantiles.py:68`](../../../src/chronaxis/core/quantiles.py#L68)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ExactQuantileBuffer-finish"></a>
### `ExactQuantileBuffer.finish`

读取截至当前批次的分位数快照，不按块分别求分位数再合并。

```python
ExactQuantileBuffer.finish()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

(原生数值或None,质量)。空集合返回None及NONE，最终
    空/部分状态由具有完整观测范围的计算器判定。

#### 异常说明

已关闭/失败时拒绝，排序额度不足或分配失败原样传播。

源码：[`src/chronaxis/core/quantiles.py:114`](../../../src/chronaxis/core/quantiles.py#L114)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ExactQuantileBuffer-close"></a>
### `ExactQuantileBuffer.close`

放弃样本并退回本实例的全部收费，释放被取消时可再次调用。

```python
ExactQuantileBuffer.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

原预算释放异常传播，不改变其他owner的费用。

源码：[`src/chronaxis/core/quantiles.py:153`](../../../src/chronaxis/core/quantiles.py#L153)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-compute_quantile_series"></a>
## `compute_quantile_series`

把有时间轴的单块内存输入送入对应后端的精确样本归约器。

```python
compute_quantile_series(series, spec, sample_kernel, budget)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`series`|CalculationSeries|是|无|位置或关键字。含区间、数值、实际更新及可选选择条件的内存时间序列。|
|`spec`|CalculationDefinition|是|无|位置或关键字。已校验的统计定义，提供操作、请求范围、选择政策和结果单位。|
|`sample_kernel`|type|是|无|位置或关键字。与所选后端相同的真实样本归约器类，复用既有选择、覆盖与更新语义。|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget) &#124; None|是|无|位置或关键字。此范围共享的内存预算，在保留原值和排序之前预约，用毕释放。|

### 返回说明

包含观测范围、诊断及精确秩结果的CalculationResult。

### 异常说明

配置、预算或计算器失败传播；正常/异常退出均释放临时所有权。

源码：[`src/chronaxis/core/quantiles.py:171`](../../../src/chronaxis/core/quantiles.py#L171)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
