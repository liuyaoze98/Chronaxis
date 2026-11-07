# `chronaxis.execution.integral_reduction`

在同一个对象中管理积分求和、覆盖统计和资源占用。push接收下一块面积，finish整理最终结果，close归还资源额度。处理块后不长期保存原数组。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)、[IntegralFacts](chronaxis.core.integral_terms.md#api-IntegralFacts)、[IntegralFactsAccumulator](chronaxis.execution.integral_facts.md#api-IntegralFactsAccumulator)、[IntegralSumResult](chronaxis.core.integral_sum.md#api-IntegralSumResult)、[Interval](chronaxis.core.models.md#api-Interval)、[NumpyIntegralSum](chronaxis.core.integral_sum_numpy.md#api-NumpyIntegralSum)、[NumpyIntegralTerms](chronaxis.core.integral_terms_numpy.md#api-NumpyIntegralTerms)、[ReferenceIntegralSum](chronaxis.core.integral_sum_reference.md#api-ReferenceIntegralSum)、[ReferenceIntegralTerms](chronaxis.core.integral_terms.md#api-ReferenceIntegralTerms)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[SourceRef](chronaxis.core.models.md#api-SourceRef)

## 对象导航

|对象|用途|
|---|---|
|[`IntegralReduction`](#api-IntegralReduction)|管理一次积分的数值累计器和覆盖统计。push处理下一块；finish返回最终数值及统计。数值溢出会记录为结果错误，仍继续记录后续覆盖；输入顺序、容量或资源限额错误则使本对象失败。close清理自己管理的状态。|
|[`IntegralReduction.__init__`](#api-IntegralReduction-__init__)|先申请计算所需的内存，再创建数值累计器和覆盖统计累计器。|
|[`IntegralReduction.closed`](#api-IntegralReduction-closed)|读取实际关闭状态。|
|[`IntegralReduction.failed`](#api-IntegralReduction-failed)|读取推进异常状态。|
|[`IntegralReduction.result`](#api-IntegralReduction-result)|借出完成后的数值结果，不能将前缀当成整窗面积。|
|[`IntegralReduction.facts`](#api-IntegralReduction-facts)|借出完成后的整窗覆盖、质量及完整来源。|
|[`IntegralReduction._require_open`](#api-IntegralReduction-_require_open)|拒绝关闭及清理中操作。|
|[`IntegralReduction._require_finished`](#api-IntegralReduction-_require_finished)|验证借出整窗结果的门槛。|
|[`IntegralReduction._reserve`](#api-IntegralReduction-_reserve)|按真实预算增量登记申请，覆盖成功后取消。|
|[`IntegralReduction._release`](#api-IntegralReduction-_release)|按真实预算减少持有量，覆盖成功后取消。|
|[`IntegralReduction.push`](#api-IntegralReduction-push)|处理当前块的面积和覆盖统计，更新累计状态；处理后不保留调用方的输入数组。|
|[`IntegralReduction.finish`](#api-IntegralReduction-finish)|核对整个请求范围的覆盖统计，计算最终总和，并换算一次输出单位。|
|[`IntegralReduction.close`](#api-IntegralReduction-close)|关闭本对象的覆盖统计和数值累计状态，归还它们占用的额度；调用方其他资源的额度保持不变。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..core.integral_sum import IntegralSumResult, require_partial_limit
from ..core.integral_sum_reference import ReferenceIntegralSum
from ..core.integral_sum_numpy import NumpyIntegralSum
from ..core.integral_terms import ReferenceIntegralTerms, IntegralFacts
from ..core.integral_terms_numpy import NumpyIntegralTerms
from ..core.calculations import CalculationDefinition, calculation_unit
from ..core.models import Interval, SourceRef
from ..results.budget import ResourceBudget
from ..results.errors import ResultClosedError
from .integral_facts import IntegralFactsAccumulator
```

</details>

<a id="api-IntegralReduction"></a>
## `IntegralReduction`

管理一次积分的数值累计器和覆盖统计。push处理下一块；finish返回最终数值及统计。数值溢出会记录为结果错误，仍继续记录后续覆盖；输入顺序、容量或资源限额错误则使本对象失败。close清理自己管理的状态。

```python
IntegralReduction(budget: ResourceBudget, spec: CalculationDefinition, observation: Interval, input_unit: str, binding_identity: str, source_refs: tuple[SourceRef, ...]=(), backend: str='numpy', partial_limit: int=4096)
```


源码：[`src/chronaxis/execution/integral_reduction.py:23`](../../../src/chronaxis/execution/integral_reduction.py#L23)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-IntegralReduction-__init__"></a>
### `IntegralReduction.__init__`

先申请计算所需的内存，再创建数值累计器和覆盖统计累计器。

```python
IntegralReduction.__init__(budget: ResourceBudget, spec: CalculationDefinition, observation: Interval, input_unit: str, binding_identity: str, source_refs: tuple[SourceRef, ...]=(), backend: str='numpy', partial_limit: int=4096)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)|是|无|位置或关键字。本次运行共用的ResourceBudget对象，用于检查内存和临时磁盘用量。当前对象在分配前申请额度，用完后归还；同一次运行的组件应使用同一个对象。|
|`spec`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|位置或关键字。本次指标的设置，包括统计时间范围、计算种类、输出单位及数据不全时的处理方式。该对象由调用方先构造；本函数不会重新读取JSON配置。|
|`observation`|[Interval](chronaxis.core.models.md#api-Interval)|是|无|位置或关键字。spec/observation 为原请求及真实范围|
|`input_unit`|str|是|无|位置或关键字。输入信号当前使用的单位，例如功率填"W"。函数据此检查输出单位的换算关系，不会仅凭这个字符串修改样本值。|
|`binding_identity`|str|是|无|位置或关键字。实际来源/字段/转换与策略的绑定身份，用于防止混用另一输入；不是信号名。|
|`source_refs`|tuple[[SourceRef](chronaxis.core.models.md#api-SourceRef), ...]|否|()|位置或关键字。参与本次计算的来源定位元组，保留实际会话、来源和原字段。|
|`backend`|str|否|'numpy'|位置或关键字。`"reference"`使用独立参考计算；`"numpy"`使用NumPy数组计算。须明确选择一种。|
|`partial_limit`|int|否|4096|位置或关键字。大于0的整数，限制浮点累加时保留的误差补偿项数量。默认4096；它不是样本数上限，也不是允许出现多少次错误。超过容量会报错。|

#### 返回说明

None，初始化新 owner。

#### 异常说明

配置、预算、分配、取消原样传播。
持续清理失败时原异常.integral_reduction_cleanup_owner 可用于重试 close。

本函数直接报告的具体错误：

- `TypeError`：积分归约需要ResourceBudget和integral CalculationDefinition。
- `ValueError`：积分归约后端需要reference或numpy。

源码：[`src/chronaxis/execution/integral_reduction.py:31`](../../../src/chronaxis/execution/integral_reduction.py#L31)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-IntegralReduction-closed"></a>
### `IntegralReduction.closed`

读取实际关闭状态。

```python
IntegralReduction.closed: bool
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

返回类型：bool。

源码：[`src/chronaxis/execution/integral_reduction.py:83`](../../../src/chronaxis/execution/integral_reduction.py#L83)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-IntegralReduction-failed"></a>
### `IntegralReduction.failed`

读取推进异常状态。

```python
IntegralReduction.failed: bool
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象已记录处理失败；False表示尚未记录失败。

#### 异常说明

无。

返回类型：bool。

源码：[`src/chronaxis/execution/integral_reduction.py:88`](../../../src/chronaxis/execution/integral_reduction.py#L88)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-IntegralReduction-result"></a>
### `IntegralReduction.result`

借出完成后的数值结果，不能将前缀当成整窗面积。

```python
IntegralReduction.result: IntegralSumResult
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

冻结结果。

#### 异常说明

关闭、失败或未完成时拒绝。

返回类型：[IntegralSumResult](chronaxis.core.integral_sum.md#api-IntegralSumResult)。

源码：[`src/chronaxis/execution/integral_reduction.py:93`](../../../src/chronaxis/execution/integral_reduction.py#L93)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-IntegralReduction-facts"></a>
### `IntegralReduction.facts`

借出完成后的整窗覆盖、质量及完整来源。

```python
IntegralReduction.facts: IntegralFacts
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

冻结事实。

#### 异常说明

关闭、失败或未完成时拒绝。

返回类型：[IntegralFacts](chronaxis.core.integral_terms.md#api-IntegralFacts)。

源码：[`src/chronaxis/execution/integral_reduction.py:102`](../../../src/chronaxis/execution/integral_reduction.py#L102)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-IntegralReduction-_require_open"></a>
### `IntegralReduction._require_open`

拒绝关闭及清理中操作。

```python
IntegralReduction._require_open() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ResultClosedError。

本函数直接报告的具体错误：

- `ResultClosedError`：积分归约owner已关闭或正在清理。

返回类型：None。

源码：[`src/chronaxis/execution/integral_reduction.py:110`](../../../src/chronaxis/execution/integral_reduction.py#L110)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-IntegralReduction-_require_finished"></a>
### `IntegralReduction._require_finished`

验证借出整窗结果的门槛。

```python
IntegralReduction._require_finished() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

生命周期错误。

本函数直接报告的具体错误：

- `RuntimeError`：整窗积分归约尚未成功完成。

返回类型：None。

源码：[`src/chronaxis/execution/integral_reduction.py:115`](../../../src/chronaxis/execution/integral_reduction.py#L115)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-IntegralReduction-_reserve"></a>
### `IntegralReduction._reserve`

按真实预算增量登记申请，覆盖成功后取消。

```python
IntegralReduction._reserve(amount: int) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`amount`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原申请或取消错误。

返回类型：None。

源码：[`src/chronaxis/execution/integral_reduction.py:121`](../../../src/chronaxis/execution/integral_reduction.py#L121)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-IntegralReduction-_release"></a>
### `IntegralReduction._release`

按真实预算减少持有量，覆盖成功后取消。

```python
IntegralReduction._release(amount: int) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`amount`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原释放或取消错误。

返回类型：None。

源码：[`src/chronaxis/execution/integral_reduction.py:134`](../../../src/chronaxis/execution/integral_reduction.py#L134)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-IntegralReduction-push"></a>
### `IntegralReduction.push`

处理当前块的面积和覆盖统计，更新累计状态；处理后不保留调用方的输入数组。

```python
IntegralReduction.push(terms: ReferenceIntegralTerms | NumpyIntegralTerms) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`terms`|[ReferenceIntegralTerms](chronaxis.core.integral_terms.md#api-ReferenceIntegralTerms) &#124; [NumpyIntegralTerms](chronaxis.core.integral_terms_numpy.md#api-NumpyIntegralTerms)|是|无|位置或关键字。terms 必须与构造后端一致。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

协议、容量、预算、分配或取消错误；此后需要调用close关闭资源。

本函数直接报告的具体错误：

- `RuntimeError`：失败或完成的积分归约不能追加。
- `TypeError`：积分面积模型与归约后端不一致。

返回类型：None。

源码：[`src/chronaxis/execution/integral_reduction.py:147`](../../../src/chronaxis/execution/integral_reduction.py#L147)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-IntegralReduction-finish"></a>
### `IntegralReduction.finish`

核对整个请求范围的覆盖统计，计算最终总和，并换算一次输出单位。

```python
IntegralReduction.finish() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None，重复成功完成无副作用。

#### 异常说明

未覆盖真实目标、预算/分配/取消错误；失败后需要调用close关闭资源。

本函数直接报告的具体错误：

- `RuntimeError`：失败的积分归约只能关闭。

返回类型：None。

源码：[`src/chronaxis/execution/integral_reduction.py:175`](../../../src/chronaxis/execution/integral_reduction.py#L175)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-IntegralReduction-close"></a>
### `IntegralReduction.close`

关闭本对象的覆盖统计和数值累计状态，归还它们占用的额度；调用方其他资源的额度保持不变。

```python
IntegralReduction.close() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None，重复成功关闭无副作用。

#### 异常说明

原释放/取消错误；释放前取消保留句柄和金额供再次 close。

返回类型：None。

源码：[`src/chronaxis/execution/integral_reduction.py:196`](../../../src/chronaxis/execution/integral_reduction.py#L196)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
