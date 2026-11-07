# `chronaxis.execution.historical_conditional_integral`

分步读取已保存的数据块并计算条件积分。每次step最多处理一块；读到末尾并整理好最终结果后返回False。完成前不能把目前的累计值当作完整结果。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CalculationResult](chronaxis.core.calculations.md#api-CalculationResult)、[ConditionalIntegralReduction](chronaxis.execution.conditional_integral_reduction.md#api-ConditionalIntegralReduction)、[HistoricalConditionalBlocks](chronaxis.execution.historical_conditional_blocks.md#api-HistoricalConditionalBlocks)、[Interval](chronaxis.core.models.md#api-Interval)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)

## 对象导航

|对象|用途|
|---|---|
|[`HistoricalConditionalIntegral`](#api-HistoricalConditionalIntegral)|逐步读取数值和筛选条件，完成一次条件积分。每次step最多处理一块；全部处理完毕后result提供最终结果。输入blocks由调用方管理，使用期间不能让其他调用者同时读取它。|
|[`HistoricalConditionalIntegral.__init__`](#api-HistoricalConditionalIntegral-__init__)|校验新鲜真实分块者，先预约固定状态再创建自有归约。|
|[`HistoricalConditionalIntegral.closed`](#api-HistoricalConditionalIntegral-closed)|读取实际关闭状态。|
|[`HistoricalConditionalIntegral.failed`](#api-HistoricalConditionalIntegral-failed)|读取操作失败状态。|
|[`HistoricalConditionalIntegral.finished`](#api-HistoricalConditionalIntegral-finished)|查看是否已经读完全部输入并整理好最终结果。|
|[`HistoricalConditionalIntegral.result`](#api-HistoricalConditionalIntegral-result)|借出完整窗口最终指标，关闭后不再开放。|
|[`HistoricalConditionalIntegral._require_open`](#api-HistoricalConditionalIntegral-_require_open)|拒绝关闭或清理中操作。|
|[`HistoricalConditionalIntegral._reserve`](#api-HistoricalConditionalIntegral-_reserve)|按实际账本增加自有预算，覆盖成功后取消。|
|[`HistoricalConditionalIntegral._release`](#api-HistoricalConditionalIntegral-_release)|按实际账本减少自有预算，释放前取消仍可重试。|
|[`HistoricalConditionalIntegral._finish`](#api-HistoricalConditionalIntegral-_finish)|在真实EOF后核对覆盖、预约完整元数据空间并分类。|
|[`HistoricalConditionalIntegral.step`](#api-HistoricalConditionalIntegral-step)|每次最多处理一个指标数据块；仍需继续时返回True，读完输入并整理好结果后返回False。|
|[`HistoricalConditionalIntegral.close`](#api-HistoricalConditionalIntegral-close)|关闭自有块、归约和最终结果，不关闭借用分块者或账本。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..core.conditional_integral_result import make_conditional_integral_result
from ..core.integral_sum import require_partial_limit
from ..core.conditional_integral_terms_reference import compute_conditional_integral_terms_reference
from ..core.conditional_integral_terms_numpy import compute_conditional_integral_terms_numpy
from ..core.models import Interval
from ..core.calculations import CalculationResult
from ..results.errors import ResultClosedError
from .history import _metadata_bytes
from .retained_metadata import retained_metadata_bytes
from .historical_conditional_blocks import HistoricalConditionalBlocks
from .conditional_integral_reduction import ConditionalIntegralReduction
```

</details>

<a id="api-HistoricalConditionalIntegral"></a>
## `HistoricalConditionalIntegral`

逐步读取数值和筛选条件，完成一次条件积分。每次step最多处理一块；全部处理完毕后result提供最终结果。输入blocks由调用方管理，使用期间不能让其他调用者同时读取它。

```python
HistoricalConditionalIntegral(blocks: HistoricalConditionalBlocks, observation: Interval, *, partial_limit: int=4096)
```


源码：[`src/chronaxis/execution/historical_conditional_integral.py:25`](../../../src/chronaxis/execution/historical_conditional_integral.py#L25)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalConditionalIntegral-__init__"></a>
### `HistoricalConditionalIntegral.__init__`

校验新鲜真实分块者，先预约固定状态再创建自有归约。

```python
HistoricalConditionalIntegral.__init__(blocks: HistoricalConditionalBlocks, observation: Interval, *, partial_limit: int=4096)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`blocks`|[HistoricalConditionalBlocks](chronaxis.execution.historical_conditional_blocks.md#api-HistoricalConditionalBlocks)|是|无|位置或关键字。blocks 为已创建的借用分块者|
|`observation`|[Interval](chronaxis.core.models.md#api-Interval)|是|无|位置或关键字。实际观测到的时间范围，必须传Interval，不能省略或填None。它与指标请求范围相交后，必须等于blocks创建时确定的实际范围。|
|`partial_limit`|int|否|4096|仅关键字。浮点累加过程中保留的误差补偿项数量上限，须大于0；不是可忽略的错误次数。|

#### 返回说明

None，初始化新的分析 owner。

#### 异常说明

配置、预算、分配和取消原样传播。
持续清理失败时原异常.historical_conditional_integral_cleanup_owner 提供重试 close 的句柄。

源码：[`src/chronaxis/execution/historical_conditional_integral.py:33`](../../../src/chronaxis/execution/historical_conditional_integral.py#L33)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalConditionalIntegral-closed"></a>
### `HistoricalConditionalIntegral.closed`

读取实际关闭状态。

```python
HistoricalConditionalIntegral.closed: bool
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

源码：[`src/chronaxis/execution/historical_conditional_integral.py:93`](../../../src/chronaxis/execution/historical_conditional_integral.py#L93)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalConditionalIntegral-failed"></a>
### `HistoricalConditionalIntegral.failed`

读取操作失败状态。

```python
HistoricalConditionalIntegral.failed: bool
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

源码：[`src/chronaxis/execution/historical_conditional_integral.py:98`](../../../src/chronaxis/execution/historical_conditional_integral.py#L98)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalConditionalIntegral-finished"></a>
### `HistoricalConditionalIntegral.finished`

查看是否已经读完全部输入并整理好最终结果。

```python
HistoricalConditionalIntegral.finished: bool
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示规定的处理步骤已全部完成；False表示尚未完成。完成处理和关闭资源是两个独立状态。

#### 异常说明

无。

返回类型：bool。

源码：[`src/chronaxis/execution/historical_conditional_integral.py:103`](../../../src/chronaxis/execution/historical_conditional_integral.py#L103)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalConditionalIntegral-result"></a>
### `HistoricalConditionalIntegral.result`

借出完整窗口最终指标，关闭后不再开放。

```python
HistoricalConditionalIntegral.result: CalculationResult
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

CalculationResult。

#### 异常说明

未完成、失败或关闭时拒绝。

本函数直接报告的具体错误：

- `RuntimeError`：历史积分尚未成功完成。

返回类型：[CalculationResult](chronaxis.core.calculations.md#api-CalculationResult)。

源码：[`src/chronaxis/execution/historical_conditional_integral.py:108`](../../../src/chronaxis/execution/historical_conditional_integral.py#L108)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalConditionalIntegral-_require_open"></a>
### `HistoricalConditionalIntegral._require_open`

拒绝关闭或清理中操作。

```python
HistoricalConditionalIntegral._require_open() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ResultClosedError。

本函数直接报告的具体错误：

- `ResultClosedError`：历史积分已关闭或正在清理。

返回类型：None。

源码：[`src/chronaxis/execution/historical_conditional_integral.py:118`](../../../src/chronaxis/execution/historical_conditional_integral.py#L118)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalConditionalIntegral-_reserve"></a>
### `HistoricalConditionalIntegral._reserve`

按实际账本增加自有预算，覆盖成功后取消。

```python
HistoricalConditionalIntegral._reserve(amount: int) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`amount`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原预算或取消异常。

返回类型：None。

源码：[`src/chronaxis/execution/historical_conditional_integral.py:123`](../../../src/chronaxis/execution/historical_conditional_integral.py#L123)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalConditionalIntegral-_release"></a>
### `HistoricalConditionalIntegral._release`

按实际账本减少自有预算，释放前取消仍可重试。

```python
HistoricalConditionalIntegral._release(amount: int) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`amount`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原释放或取消异常。

返回类型：None。

源码：[`src/chronaxis/execution/historical_conditional_integral.py:136`](../../../src/chronaxis/execution/historical_conditional_integral.py#L136)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalConditionalIntegral-_finish"></a>
### `HistoricalConditionalIntegral._finish`

在真实EOF后核对覆盖、预约完整元数据空间并分类。

```python
HistoricalConditionalIntegral._finish() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

覆盖、预算、分配或取消错误传播。

返回类型：None。

源码：[`src/chronaxis/execution/historical_conditional_integral.py:148`](../../../src/chronaxis/execution/historical_conditional_integral.py#L148)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalConditionalIntegral-step"></a>
### `HistoricalConditionalIntegral.step`

每次最多处理一个指标数据块；仍需继续时返回True，读完输入并整理好结果后返回False。

```python
HistoricalConditionalIntegral.step() -> bool
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

True为消费了一块，False为已完成；完成后重复调用安全。

#### 异常说明

真实读取、预算、数值模型、分配、关闭或取消错误；此后需要调用close关闭资源。

本函数直接报告的具体错误：

- `RuntimeError`：失败的历史积分只能关闭。

返回类型：bool。

源码：[`src/chronaxis/execution/historical_conditional_integral.py:167`](../../../src/chronaxis/execution/historical_conditional_integral.py#L167)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HistoricalConditionalIntegral-close"></a>
### `HistoricalConditionalIntegral.close`

关闭自有块、归约和最终结果，不关闭借用分块者或账本。

```python
HistoricalConditionalIntegral.close() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None，重复成功关闭无副作用。

#### 异常说明

子关闭或预算取消原样传播；实际释放前后按句柄/账本支持重试。

返回类型：None。

源码：[`src/chronaxis/execution/historical_conditional_integral.py:204`](../../../src/chronaxis/execution/historical_conditional_integral.py#L204)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
