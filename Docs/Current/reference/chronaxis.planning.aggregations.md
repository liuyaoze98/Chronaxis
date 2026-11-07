# `chronaxis.planning.aggregations`

校验 v4 结果表聚合的来源、字段、分组、总体政策与输出单位。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)

## 对象导航

|对象|用途|
|---|---|
|[`AggregationPlan`](#api-AggregationPlan)|一次已编译的归约，只消费同一分析中的一个具名结果来源。|
|[`aggregation_unit`](#api-aggregation_unit)|核实已输出量的尺度，方差用平方温差，返回可复算的输出换算。|
|[`parse_aggregations`](#api-parse_aggregations)|把声明列表解析为不可变归约计划，拒绝选择行或任意字段访问。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from fractions import Fraction
from .checks import PlanValidationError, array_at, object_at, choice_at
from .nodes import register_id
from ..core.unit_registry import resolve_unit, output_label, conversion
from ..core.moments import moment_source_unit
from ..core.quantiles import quantile_probability
```

</details>

<a id="api-AggregationPlan"></a>
## `AggregationPlan`

一次已编译的归约，只消费同一分析中的一个具名结果来源。

```python
class AggregationPlan
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|本聚合项的唯一名称，以 aggregation_id 写入输出结果。|
|`source_kind`|str|是|无|结果来源种类，取 calculation、sequence、rule 或 window。|
|`source_id`|str|是|无|此种类下的具名结果生产者，仅从该项实际产出的行收集候选。|
|`operation`|str|是|无|要在组内执行的 count、sum、mean、variance、quantile 或 median。|
|`field`|str &#124; None|是|无|数值来源字段为指标 value 或配对 delay_ns。对象计数不读取数值字段。|
|`group_by`|tuple[str, ...]|是|无|决定各组身份的有序键；空元组表示全体候选同属一组。|
|`input_unit`|str|是|无|归约前用于解释来源数值的单位，延迟为 ns，对象计数为 1。|
|`unit`|str|是|无|组结果输出使用的单位。解析时已验证可换算性，方差的单位是平方量纲。|
|`include_partial`|bool|是|无|是否允许本身仍有可用数值的部分指标行参与数值聚合，默认排除。|
|`partial_policy`|str|是|无|总体不完整时 report 保留可计算的部分值，strict 隐去该值。|
|`q`|int &#124; float &#124; None|是|无|quantile 用于计算精确顺序统计位置的概率，其他操作省略。|
|`ddof`|int|是|无|variance 的自由度修正，可为 0 或 1；当参与数不大于此值时方差不可定。|

源码：[`src/chronaxis/planning/aggregations.py:13`](../../../src/chronaxis/planning/aggregations.py#L13)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-aggregation_unit"></a>
## `aggregation_unit`

核实已输出量的尺度，方差用平方温差，返回可复算的输出换算。

```python
aggregation_unit(operation, source_unit, target)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`operation`|str|是|无|位置或关键字。聚合操作名称，决定是否无量纲计数、平方单位或按来源尺度换算。|
|`source_unit`|str|是|无|位置或关键字。具名指标或延迟字段实际输出的单位，作为换算起点。|
|`target`|str &#124; None|是|无|位置或关键字。显式配置的输出单位，省略时按操作的自然量纲输出。|

### 返回说明

输出单位、倍率、偏移；偏移在求和时按参与数累计。

### 异常说明

单位不可比或未知变换。

源码：[`src/chronaxis/planning/aggregations.py:30`](../../../src/chronaxis/planning/aggregations.py#L30)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-parse_aggregations"></a>
## `parse_aggregations`

把声明列表解析为不可变归约计划，拒绝选择行或任意字段访问。

```python
parse_aggregations(raw, version, calculations, rules, windows, sequences, execution, ids)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`raw`|list[dict]|是|无|位置或关键字。配置根级 aggregations 的原始声明列表，逐项检查来源、字段、分组和计算政策。|
|`version`|int|是|无|位置或关键字。当前配置版本，只有版本 4 允许声明结果聚合。|
|`calculations`|Sequence[CalculationPlan]|是|无|位置或关键字。已编译的指标目录，核对标量来源、父范围和原输出单位。|
|`rules`|Sequence[RulePlan]|是|无|位置或关键字。已编译的事件规则目录，用于校验按规则计行的具名引用。|
|`windows`|Sequence[WindowPlan]|是|无|位置或关键字。已编译的窗口目录，用于校验按最终片段计行的窗口引用。|
|`sequences`|Sequence[SequencePlan]|是|无|位置或关键字。已编译的请求响应目录，用于校验待汇总请求及延迟的来源。|
|`execution`|ExecutionPlan|是|无|位置或关键字。本次执行设置，聚合项省略数据不全时的处理方式时从中继承。|
|`ids`|set[str]|是|无|位置或关键字。计划内已用标识集合，每个合法聚合名称登记一次以检测冲突。|

### 返回说明

AggregationPlan 元组，顺序与配置一致。

### 异常说明

PlanValidationError 定位错误条目。

源码：[`src/chronaxis/planning/aggregations.py:58`](../../../src/chronaxis/planning/aggregations.py#L58)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
