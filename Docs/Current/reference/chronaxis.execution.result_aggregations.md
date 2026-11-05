# `chronaxis.execution.result_aggregations`

在最终结果行产生时按具名引用分组。只保存归约状态和精确分位数所需的样本。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)、[ExactQuantileBuffer](chronaxis.core.quantiles.md#api-ExactQuantileBuffer)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[SummaryAggregationRow](chronaxis.results.aggregation_row.md#api-SummaryAggregationRow)、[SummaryCalculationRow](chronaxis.results.summary.md#api-SummaryCalculationRow)、[SummaryEventRow](chronaxis.results.summary.md#api-SummaryEventRow)、[SummarySegmentRow](chronaxis.results.summary.md#api-SummarySegmentRow)、[SummarySequenceRow](chronaxis.results.summary.md#api-SummarySequenceRow)

## 对象导航

|对象|用途|
|---|---|
|[`discovery_rules`](#api-discovery_rules)|定位总体发现所依赖的原规则。|
|[`_Group`](#api-_Group)|一个实际键的有限状态。二阶和在精确有理数域累计，输出边界检查数值范围。|
|[`_Group.__init__`](#api-_Group-__init__)|创建空候选和零计数。|
|[`_Group.accept`](#api-_Group-accept)|从一条源行提取候选、分类及实际数值。|
|[`_Group.value`](#api-_Group-value)|最终一次换算，不平均行覆盖率或块分位数。|
|[`ResultAggregations`](#api-ResultAggregations)|订阅同一次运行的必要源行，分组先预约，异常由拥有者统一关闭。|
|[`ResultAggregations.__init__`](#api-ResultAggregations-__init__)|预留有限声明、已知空组和结果元数据。|
|[`ResultAggregations._input_dtype`](#api-ResultAggregations-_input_dtype)|确定分位数排序列的原类型。|
|[`ResultAggregations._group`](#api-ResultAggregations-_group)|按稳定字段取得或创建组。|
|[`ResultAggregations.accept`](#api-ResultAggregations-accept)|只分派实际受订阅的结果行。|
|[`ResultAggregations.rows`](#api-ResultAggregations-rows)|在原规则完成后交付总体判定及组结果。|
|[`ResultAggregations.close`](#api-ResultAggregations-close)|释放精确分位数和自己的分组费用，可重试。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from fractions import Fraction
from math import isfinite
from ..core.quantiles import ExactQuantileBuffer
from ..core.types import SignalDType as D, QualityFlag as Q
from ..planning.aggregations import aggregation_unit
from ..results.aggregation_row import SummaryAggregationRow
from ..results.summary import SummaryCalculationRow, SummaryEventRow, SummarySegmentRow, SummarySequenceRow
from ..results.budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
```

</details>

<a id="api-discovery_rules"></a>
## `discovery_rules`

定位总体发现所依赖的原规则。

```python
discovery_rules(plan, spec)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|AnalysisPlan|是|无|位置或关键字。本次执行的已校验计划，其中具名指标、配对、规则和窗口可供追溯发现证据。|
|`spec`|AggregationPlan|是|无|位置或关键字。已编译的单项结果聚合，确定来源、数值操作、单位、分组顺序与部分总体政策。|

### 返回说明

规则ID元组。

### 异常说明

引用未校验。

源码：[`src/chronaxis/execution/result_aggregations.py:13`](../../../src/chronaxis/execution/result_aggregations.py#L13)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_Group"></a>
## `_Group`

一个实际键的有限状态。二阶和在精确有理数域累计，输出边界检查数值范围。

```python
_Group()
```


源码：[`src/chronaxis/execution/result_aggregations.py:33`](../../../src/chronaxis/execution/result_aggregations.py#L33)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_Group-__init__"></a>
### `_Group.__init__`

创建空候选和零计数。

```python
_Group.__init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

新组。

#### 异常说明

分配错误传播。

源码：[`src/chronaxis/execution/result_aggregations.py:36`](../../../src/chronaxis/execution/result_aggregations.py#L36)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_Group-accept"></a>
### `_Group.accept`

从一条源行提取候选、分类及实际数值。

```python
_Group.accept(spec, row, budget, backend, dtype, needs_coverage)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|AggregationPlan|是|无|位置或关键字。已编译的单项结果聚合，确定来源、数值操作、单位、分组顺序与部分总体政策。|
|`row`|[SummaryCalculationRow](chronaxis.results.summary.md#api-SummaryCalculationRow) &#124; [SummarySequenceRow](chronaxis.results.summary.md#api-SummarySequenceRow) &#124; [SummaryEventRow](chronaxis.results.summary.md#api-SummaryEventRow) &#124; [SummarySegmentRow](chronaxis.results.summary.md#api-SummarySegmentRow)|是|无|位置或关键字。本组的一条实际来源行。先判定候选、定义排除或质量排除，再从可参与的行取得数值。|
|`budget`|ResourceBudget|是|无|位置或关键字。本次运行共享的资源预算，按需为分组状态和精确分位数保留空间。|
|`backend`|str|是|无|位置或关键字。当前运行的数值后端，决定精确分位数使用标量或 NumPy 样本缓冲。|
|`dtype`|SignalDType|是|无|位置或关键字。用于精确分位数的源列类型，决定排序和插值前保留的数值精度。|
|`needs_coverage`|bool|是|无|位置或关键字。来源指标是否配置了正覆盖门槛；需要该判定但结果行缺少它时，按质量排除。|

#### 返回说明

None。

#### 异常说明

预算或模型错误。

源码：[`src/chronaxis/execution/result_aggregations.py:45`](../../../src/chronaxis/execution/result_aggregations.py#L45)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_Group-value"></a>
### `_Group.value`

最终一次换算，不平均行覆盖率或块分位数。

```python
_Group.value(spec, factor, shift)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|AggregationPlan|是|无|位置或关键字。已编译的单项结果聚合，确定来源、数值操作、单位、分组顺序与部分总体政策。|
|`factor`|Fraction &#124; int|是|无|位置或关键字。源结果单位换到目标单位的倍率。方差使用方差单位之间的倍率。|
|`shift`|Fraction &#124; int|是|无|位置或关键字。源单位转换到目标单位的偏移。求和时按参与数累积偏移，其余位置统计仅应用一次。|

#### 返回说明

数值、原因、质量。

#### 异常说明

原预算/排序错误。

源码：[`src/chronaxis/execution/result_aggregations.py:107`](../../../src/chronaxis/execution/result_aggregations.py#L107)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ResultAggregations"></a>
## `ResultAggregations`

订阅同一次运行的必要源行，分组先预约，异常由拥有者统一关闭。

```python
ResultAggregations(plan, budget)
```


源码：[`src/chronaxis/execution/result_aggregations.py:144`](../../../src/chronaxis/execution/result_aggregations.py#L144)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ResultAggregations-__init__"></a>
### `ResultAggregations.__init__`

预留有限声明、已知空组和结果元数据。

```python
ResultAggregations.__init__(plan, budget)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|AnalysisPlan|是|无|位置或关键字。本次执行的已校验计划，其中具名指标、配对、规则和窗口可供追溯发现证据。|
|`budget`|ResourceBudget|是|无|位置或关键字。本次运行共享的资源预算，按需为分组状态和精确分位数保留空间。|

#### 返回说明

owner。

#### 异常说明

配置/预算错误含清理句柄。

源码：[`src/chronaxis/execution/result_aggregations.py:147`](../../../src/chronaxis/execution/result_aggregations.py#L147)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ResultAggregations-_input_dtype"></a>
### `ResultAggregations._input_dtype`

确定分位数排序列的原类型。

```python
ResultAggregations._input_dtype(spec)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|AggregationPlan|是|无|位置或关键字。已编译的单项结果聚合，确定来源、数值操作、单位、分组顺序与部分总体政策。|

#### 返回说明

dtype。

#### 异常说明

引用不符。

源码：[`src/chronaxis/execution/result_aggregations.py:171`](../../../src/chronaxis/execution/result_aggregations.py#L171)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ResultAggregations-_group"></a>
### `ResultAggregations._group`

按稳定字段取得或创建组。

```python
ResultAggregations._group(spec, row)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|AggregationPlan|是|无|位置或关键字。已编译的单项结果聚合，确定来源、数值操作、单位、分组顺序与部分总体政策。|
|`row`|[SummaryCalculationRow](chronaxis.results.summary.md#api-SummaryCalculationRow) &#124; [SummarySequenceRow](chronaxis.results.summary.md#api-SummarySequenceRow) &#124; [SummaryEventRow](chronaxis.results.summary.md#api-SummaryEventRow) &#124; [SummarySegmentRow](chronaxis.results.summary.md#api-SummarySegmentRow) &#124; None|是|无|位置或关键字。实际源行提供分组身份。已知固定分组尚无候选时可传 None；父身份只能从实际行取得。|

#### 返回说明

状态。

#### 异常说明

预算或键不合法。

源码：[`src/chronaxis/execution/result_aggregations.py:193`](../../../src/chronaxis/execution/result_aggregations.py#L193)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ResultAggregations-accept"></a>
### `ResultAggregations.accept`

只分派实际受订阅的结果行。

```python
ResultAggregations.accept(row)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`row`|[SummaryCalculationRow](chronaxis.results.summary.md#api-SummaryCalculationRow) &#124; [SummarySequenceRow](chronaxis.results.summary.md#api-SummarySequenceRow) &#124; [SummaryEventRow](chronaxis.results.summary.md#api-SummaryEventRow) &#124; [SummarySegmentRow](chronaxis.results.summary.md#api-SummarySegmentRow)|是|无|位置或关键字。刚输出的指标、配对、事件或片段行，按其类型和稳定来源名称分派到订阅组。|

#### 返回说明

None。

#### 异常说明

预算/输入矛盾。

源码：[`src/chronaxis/execution/result_aggregations.py:209`](../../../src/chronaxis/execution/result_aggregations.py#L209)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ResultAggregations-rows"></a>
### `ResultAggregations.rows`

在原规则完成后交付总体判定及组结果。

```python
ResultAggregations.rows(rules, sequence)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`rules`|Sequence[RecordRuleTimeline]|是|无|位置或关键字。执行结束后保存原规则判定覆盖的时间线，用来核对候选总体是否已完整发现。|
|`sequence`|int|是|无|位置或关键字。第一条聚合结果的序号。每发出一组结果递增一次。|

#### 返回说明

逐组行。

#### 异常说明

未完成或预算错误。

源码：[`src/chronaxis/execution/result_aggregations.py:225`](../../../src/chronaxis/execution/result_aggregations.py#L225)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ResultAggregations-close"></a>
### `ResultAggregations.close`

释放精确分位数和自己的分组费用，可重试。

```python
ResultAggregations.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

原账本错误传播。

源码：[`src/chronaxis/execution/result_aggregations.py:261`](../../../src/chronaxis/execution/result_aggregations.py#L261)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
