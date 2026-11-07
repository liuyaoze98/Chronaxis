# `chronaxis.execution.conditional_integral_facts`

逐块累加条件积分所需的有效时长、已知条件时长、缺失区间和来源信息。完整处理目标范围后才能读取整段汇总。保存新的诊断信息之前会检查内存限额。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)、[ConditionalIntegralFacts](chronaxis.core.conditional_integral_terms.md#api-ConditionalIntegralFacts)、[Interval](chronaxis.core.models.md#api-Interval)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[SourceRef](chronaxis.core.models.md#api-SourceRef)

## 对象导航

|对象|用途|
|---|---|
|[`_refs_cost`](#api-_refs_cost)|估算完整来源实体及冻结容器，不承担JSON工作副本。|
|[`_unique_refs`](#api-_unique_refs)|按完整类型和值保留第一次出现的定位，保持原出现顺序。|
|[`_join_unknown`](#api-_join_unknown)|合并连续块边界处及块内相邻的未知范围，不填补有效区间。|
|[`ConditionalIntegralFactsAccumulator`](#api-ConditionalIntegralFactsAccumulator)|逐块分别累计数值有效时间和筛选条件已知时间，并保存缺失区间及来源。每块必须紧接上一块；finish确认请求范围全部处理后才提供整段统计。处理失败后应close，归还本对象的内存额度。|
|[`ConditionalIntegralFactsAccumulator.__init__`](#api-ConditionalIntegralFactsAccumulator-__init__)|固定真实观测交集并申请初始状态预算。|
|[`ConditionalIntegralFactsAccumulator.closed`](#api-ConditionalIntegralFactsAccumulator-closed)|提供关闭状态。|
|[`ConditionalIntegralFactsAccumulator.failed`](#api-ConditionalIntegralFactsAccumulator-failed)|提供失败状态。|
|[`ConditionalIntegralFactsAccumulator.facts`](#api-ConditionalIntegralFactsAccumulator-facts)|finish成功后返回整个请求范围的覆盖统计；诊断对象由当前累计器管理，不额外复制。|
|[`ConditionalIntegralFactsAccumulator._require_open`](#api-ConditionalIntegralFactsAccumulator-_require_open)|拒绝关闭及正在清理时读取或推进。|
|[`ConditionalIntegralFactsAccumulator._reserve`](#api-ConditionalIntegralFactsAccumulator-_reserve)|申请前后按真实账本增量登记，覆盖成功后取消。|
|[`ConditionalIntegralFactsAccumulator._release`](#api-ConditionalIntegralFactsAccumulator-_release)|释放前后按真实账本减少持有量，取消后不会再次扣同一笔。|
|[`ConditionalIntegralFactsAccumulator._validate_block`](#api-ConditionalIntegralFactsAccumulator-_validate_block)|检查当前块是否紧接上一块、覆盖统计是否完整，以及输入标识是否一致。|
|[`ConditionalIntegralFactsAccumulator.push`](#api-ConditionalIntegralFactsAccumulator-push)|累加当前块的覆盖统计。面积值仍由调用方交给数值累计器处理，不保存在这里。|
|[`ConditionalIntegralFactsAccumulator.finish`](#api-ConditionalIntegralFactsAccumulator-finish)|检查目标范围是否已全部处理。没有交集时可直接结束；零长度窗口仍需提供该时刻的记录。|
|[`ConditionalIntegralFactsAccumulator.close`](#api-ConditionalIntegralFactsAccumulator-close)|归还当前对象占用的内存额度。归还前被取消时可重试close；共用的资源管理对象不由这里关闭。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..core.conditional_integral_terms import ConditionalIntegralFacts
from ..core.calculations import CalculationDefinition, calculation_unit
from ..core.models import Interval, SourceRef
from ..core.types import QualityFlag as Q
from ..core.validation import require_text
from ..results.budget import ResourceBudget
from ..results.errors import ResultClosedError
from .history import _metadata_bytes
from .retained_metadata import retained_metadata_bytes, reference_workspace
```

</details>

<a id="api-_refs_cost"></a>
## `_refs_cost`

估算完整来源实体及冻结容器，不承担JSON工作副本。

```python
_refs_cost(refs: tuple[SourceRef, ...]) -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`refs`|tuple[[SourceRef](chronaxis.core.models.md#api-SourceRef), ...]|是|无|位置或关键字。refs 为调用方已经提供的冻结定位。|

### 返回说明

保守 bytes。

### 异常说明

ResultFormatError 为既有估算协议无法处理的字段。

返回类型：int。

源码：[`src/chronaxis/execution/conditional_integral_facts.py:23`](../../../src/chronaxis/execution/conditional_integral_facts.py#L23)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_unique_refs"></a>
## `_unique_refs`

按完整类型和值保留第一次出现的定位，保持原出现顺序。

```python
_unique_refs(existing, incoming)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`existing`|tuple[[SourceRef](chronaxis.core.models.md#api-SourceRef), ...]|是|无|位置或关键字。此前已保留的来源引用，合并时保留原顺序并去重。|
|`incoming`|tuple[[SourceRef](chronaxis.core.models.md#api-SourceRef), ...]|是|无|位置或关键字。本次新增的来源引用，与已有引用合并并去重。|

### 返回说明

去重后的 tuple。

### 异常说明

MemoryError 为预算已申请后的实际分配失败。

源码：[`src/chronaxis/execution/conditional_integral_facts.py:37`](../../../src/chronaxis/execution/conditional_integral_facts.py#L37)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_join_unknown"></a>
## `_join_unknown`

合并连续块边界处及块内相邻的未知范围，不填补有效区间。

```python
_join_unknown(existing, incoming)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`existing`|tuple[[Interval](chronaxis.core.models.md#api-Interval), ...]|是|无|位置或关键字。此前累计的有序、不重叠未知Interval元组。|
|`incoming`|tuple[[Interval](chronaxis.core.models.md#api-Interval), ...]|是|无|位置或关键字。本批新发现的有序、不重叠未知Interval元组。|

### 返回说明

紧凑区间 tuple。

### 异常说明

MemoryError 为已申请工作空间内的实际分配失败。

源码：[`src/chronaxis/execution/conditional_integral_facts.py:62`](../../../src/chronaxis/execution/conditional_integral_facts.py#L62)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ConditionalIntegralFactsAccumulator"></a>
## `ConditionalIntegralFactsAccumulator`

逐块分别累计数值有效时间和筛选条件已知时间，并保存缺失区间及来源。每块必须紧接上一块；finish确认请求范围全部处理后才提供整段统计。处理失败后应close，归还本对象的内存额度。

```python
ConditionalIntegralFactsAccumulator(budget: ResourceBudget, spec: CalculationDefinition, observation: Interval, input_unit: str, binding_identity: str, source_refs: tuple[SourceRef, ...]=())
```


源码：[`src/chronaxis/execution/conditional_integral_facts.py:83`](../../../src/chronaxis/execution/conditional_integral_facts.py#L83)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ConditionalIntegralFactsAccumulator-__init__"></a>
### `ConditionalIntegralFactsAccumulator.__init__`

固定真实观测交集并申请初始状态预算。

```python
ConditionalIntegralFactsAccumulator.__init__(budget: ResourceBudget, spec: CalculationDefinition, observation: Interval, input_unit: str, binding_identity: str, source_refs: tuple[SourceRef, ...]=())
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)|是|无|位置或关键字。本次运行共用的ResourceBudget对象，用于检查内存和临时磁盘用量。当前对象在分配前申请额度，用完后归还；同一次运行的组件应使用同一个对象。|
|`spec`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|位置或关键字。spec 为原积分请求|
|`observation`|[Interval](chronaxis.core.models.md#api-Interval)|是|无|位置或关键字。observation 为真实观测范围|
|`input_unit`|str|是|无|位置或关键字。input_unit/identity 为原表达式事实|
|`binding_identity`|str|是|无|位置或关键字。实际来源/字段/转换与策略的绑定身份，用于防止混用另一输入；不是信号名。|
|`source_refs`|tuple[[SourceRef](chronaxis.core.models.md#api-SourceRef), ...]|否|()|位置或关键字。source_refs 为已知完整定位。|

#### 返回说明

新 owner。

#### 异常说明

TypeError/ValueError 为协议错误；预算/分配/取消原样传播。
清理仍失败时，原异常.conditional_integral_facts_cleanup_owner 提供可重试 close 的 owner。

源码：[`src/chronaxis/execution/conditional_integral_facts.py:91`](../../../src/chronaxis/execution/conditional_integral_facts.py#L91)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ConditionalIntegralFactsAccumulator-closed"></a>
### `ConditionalIntegralFactsAccumulator.closed`

提供关闭状态。

```python
ConditionalIntegralFactsAccumulator.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/execution/conditional_integral_facts.py:148`](../../../src/chronaxis/execution/conditional_integral_facts.py#L148)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ConditionalIntegralFactsAccumulator-failed"></a>
### `ConditionalIntegralFactsAccumulator.failed`

提供失败状态。

```python
ConditionalIntegralFactsAccumulator.failed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象已记录处理失败；False表示尚未记录失败。

#### 异常说明

无。

源码：[`src/chronaxis/execution/conditional_integral_facts.py:154`](../../../src/chronaxis/execution/conditional_integral_facts.py#L154)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ConditionalIntegralFactsAccumulator-facts"></a>
### `ConditionalIntegralFactsAccumulator.facts`

finish成功后返回整个请求范围的覆盖统计；诊断对象由当前累计器管理，不额外复制。

```python
ConditionalIntegralFactsAccumulator.facts: ConditionalIntegralFacts
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

原 spec 与完整覆盖/来源事实。

#### 异常说明

关闭、失败或未完成时拒绝。

本函数直接报告的具体错误：

- `RuntimeError`：整窗事实尚未成功完成。

#### 副作用说明

返回引用只由本 owner 计费至 close；独立留存由调用方承担。

返回类型：[ConditionalIntegralFacts](chronaxis.core.conditional_integral_terms.md#api-ConditionalIntegralFacts)。

源码：[`src/chronaxis/execution/conditional_integral_facts.py:160`](../../../src/chronaxis/execution/conditional_integral_facts.py#L160)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ConditionalIntegralFactsAccumulator-_require_open"></a>
### `ConditionalIntegralFactsAccumulator._require_open`

拒绝关闭及正在清理时读取或推进。

```python
ConditionalIntegralFactsAccumulator._require_open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ResultClosedError。

本函数直接报告的具体错误：

- `ResultClosedError`：积分事实owner已关闭或正在清理。

源码：[`src/chronaxis/execution/conditional_integral_facts.py:172`](../../../src/chronaxis/execution/conditional_integral_facts.py#L172)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ConditionalIntegralFactsAccumulator-_reserve"></a>
### `ConditionalIntegralFactsAccumulator._reserve`

申请前后按真实账本增量登记，覆盖成功后取消。

```python
ConditionalIntegralFactsAccumulator._reserve(amount)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`amount`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原预算或取消异常。

源码：[`src/chronaxis/execution/conditional_integral_facts.py:177`](../../../src/chronaxis/execution/conditional_integral_facts.py#L177)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ConditionalIntegralFactsAccumulator-_release"></a>
### `ConditionalIntegralFactsAccumulator._release`

释放前后按真实账本减少持有量，取消后不会再次扣同一笔。

```python
ConditionalIntegralFactsAccumulator._release(amount)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`amount`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原释放或取消异常。

源码：[`src/chronaxis/execution/conditional_integral_facts.py:190`](../../../src/chronaxis/execution/conditional_integral_facts.py#L190)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ConditionalIntegralFactsAccumulator-_validate_block"></a>
### `ConditionalIntegralFactsAccumulator._validate_block`

检查当前块是否紧接上一块、覆盖统计是否完整，以及输入标识是否一致。

```python
ConditionalIntegralFactsAccumulator._validate_block(facts)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`facts`|[ConditionalIntegralFacts](chronaxis.core.conditional_integral_terms.md#api-ConditionalIntegralFacts)|是|无|位置或关键字。facts 为有限块事实。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError 为协议错误。

本函数直接报告的具体错误：

- `TypeError`：需要ConditionalIntegralFacts。
- `ValueError`：积分块请求、单位或绑定身份不一致。
- `ValueError`：没有实际目标或块观测。
- `ValueError`：积分块有缺口、重叠或超出目标。
- `ValueError`：选中样本数超过可核实的正整数纳秒时间点。
- `ValueError`：零窗口仅接收一个真实点块。
- `ValueError`：正窗口不接受不推进的块。

源码：[`src/chronaxis/execution/conditional_integral_facts.py:203`](../../../src/chronaxis/execution/conditional_integral_facts.py#L203)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ConditionalIntegralFactsAccumulator-push"></a>
### `ConditionalIntegralFactsAccumulator.push`

累加当前块的覆盖统计。面积值仍由调用方交给数值累计器处理，不保存在这里。

```python
ConditionalIntegralFactsAccumulator.push(facts: ConditionalIntegralFacts) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`facts`|[ConditionalIntegralFacts](chronaxis.core.conditional_integral_terms.md#api-ConditionalIntegralFacts)|是|无|位置或关键字。facts 为连续块的真实 ConditionalIntegralFacts。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

协议、预算、分配或取消错误；此后需要调用close关闭资源。

本函数直接报告的具体错误：

- `RuntimeError`：失败或完成的积分事实owner不能追加。

返回类型：None。

源码：[`src/chronaxis/execution/conditional_integral_facts.py:232`](../../../src/chronaxis/execution/conditional_integral_facts.py#L232)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ConditionalIntegralFactsAccumulator-finish"></a>
### `ConditionalIntegralFactsAccumulator.finish`

检查目标范围是否已全部处理。没有交集时可直接结束；零长度窗口仍需提供该时刻的记录。

```python
ConditionalIntegralFactsAccumulator.finish() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None；成功后 facts 可读，重复 finish 无副作用。

#### 异常说明

RuntimeError 为失败状态；ValueError 为观测前缀不足。

本函数直接报告的具体错误：

- `RuntimeError`：失败owner只能关闭。
- `ValueError`：尚未覆盖完整实际窗口。

返回类型：None。

源码：[`src/chronaxis/execution/conditional_integral_facts.py:279`](../../../src/chronaxis/execution/conditional_integral_facts.py#L279)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ConditionalIntegralFactsAccumulator-close"></a>
### `ConditionalIntegralFactsAccumulator.close`

归还当前对象占用的内存额度。归还前被取消时可重试close；共用的资源管理对象不由这里关闭。

```python
ConditionalIntegralFactsAccumulator.close() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None；重复关闭不再扣账。

#### 异常说明

原释放/取消错误，是否已关闭以实际账本释放结果为准。

返回类型：None。

源码：[`src/chronaxis/execution/conditional_integral_facts.py:294`](../../../src/chronaxis/execution/conditional_integral_facts.py#L294)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
