# `chronaxis.core.integral_sum_reference`

逐项累加积分面积，并保存浮点误差，供NumPy实现对照。例如很大的正负数抵消后，仍需尽量保留夹在其中的小数。误差项最多保存partial_limit个，超过时抛错。finish返回当前结果，不删除累计状态；中途溢出会持续标记为错误。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[IntegralStateLimitError](chronaxis.core.integral_sum.md#api-IntegralStateLimitError)、[IntegralSumResult](chronaxis.core.integral_sum.md#api-IntegralSumResult)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ReferenceIntegralTerms](chronaxis.core.integral_terms.md#api-ReferenceIntegralTerms)

## 对象导航

|对象|用途|
|---|---|
|[`ReferenceIntegralSum`](#api-ReferenceIntegralSum)|持有有界非重叠误差项、有效面积计数及持久累计故障。|
|[`ReferenceIntegralSum.__init__`](#api-ReferenceIntegralSum-__init__)|建立空累计状态。|
|[`ReferenceIntegralSum.valid_term_count`](#api-ReferenceIntegralSum-valid_term_count)|读取有效面积项数。|
|[`ReferenceIntegralSum.calculation_failed`](#api-ReferenceIntegralSum-calculation_failed)|读取持久累计故障。|
|[`ReferenceIntegralSum.partial_count`](#api-ReferenceIntegralSum-partial_count)|读取当前误差项数量。|
|[`ReferenceIntegralSum.push`](#api-ReferenceIntegralSum-push)|按原顺序推进有效面积，保留块间误差状态。|
|[`ReferenceIntegralSum.push_values`](#api-ReferenceIntegralSum-push_values)|按原顺序直接累加给定的浮点数序列，不要求调用方先构造积分面积对象。|
|[`ReferenceIntegralSum.finish`](#api-ReferenceIntegralSum-finish)|归约有界误差项并只转换一次，保留原累计状态。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from math import fsum, isfinite
from .integral_sum import IntegralSumResult, IntegralStateLimitError, require_partial_limit, require_sum_finish
from .integral_terms import ReferenceIntegralTerms
from .types import QualityFlag as Q
```

</details>

<a id="api-ReferenceIntegralSum"></a>
## `ReferenceIntegralSum`

持有有界非重叠误差项、有效面积计数及持久累计故障。

push 为原序状态驱动；finish 不清空状态，最终转换故障仅影响返回快照。
调用方在任意推进异常后须放弃当前累计并清理，不能接着使用半段输入。

```python
ReferenceIntegralSum(partial_limit: int=4096)
```


源码：[`src/chronaxis/core/integral_sum_reference.py:18`](../../../src/chronaxis/core/integral_sum_reference.py#L18)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ReferenceIntegralSum-__init__"></a>
### `ReferenceIntegralSum.__init__`

建立空累计状态。

```python
ReferenceIntegralSum.__init__(partial_limit: int=4096)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`partial_limit`|int|否|4096|位置或关键字。大于0的整数，限制浮点累加时保留的误差补偿项数量。默认4096；它不是样本数上限，也不是允许出现多少次错误。超过容量会报错。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

非法容量。

源码：[`src/chronaxis/core/integral_sum_reference.py:25`](../../../src/chronaxis/core/integral_sum_reference.py#L25)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ReferenceIntegralSum-valid_term_count"></a>
### `ReferenceIntegralSum.valid_term_count`

读取有效面积项数。

```python
ReferenceIntegralSum.valid_term_count: int
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

int。

#### 异常说明

无。

返回类型：int。

源码：[`src/chronaxis/core/integral_sum_reference.py:35`](../../../src/chronaxis/core/integral_sum_reference.py#L35)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ReferenceIntegralSum-calculation_failed"></a>
### `ReferenceIntegralSum.calculation_failed`

读取持久累计故障。

```python
ReferenceIntegralSum.calculation_failed: bool
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示累计过程中出现数值错误；False表示尚未出现数值错误。

#### 异常说明

无。

返回类型：bool。

源码：[`src/chronaxis/core/integral_sum_reference.py:40`](../../../src/chronaxis/core/integral_sum_reference.py#L40)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ReferenceIntegralSum-partial_count"></a>
### `ReferenceIntegralSum.partial_count`

读取当前误差项数量。

```python
ReferenceIntegralSum.partial_count: int
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

int。

#### 异常说明

无。

返回类型：int。

源码：[`src/chronaxis/core/integral_sum_reference.py:45`](../../../src/chronaxis/core/integral_sum_reference.py#L45)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ReferenceIntegralSum-push"></a>
### `ReferenceIntegralSum.push`

按原顺序推进有效面积，保留块间误差状态。

```python
ReferenceIntegralSum.push(terms: ReferenceIntegralTerms) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`terms`|[ReferenceIntegralTerms](chronaxis.core.integral_terms.md#api-ReferenceIntegralTerms)|是|无|位置或关键字。terms 为有限冻结面积块。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError 为后端不符；IntegralStateLimitError/MemoryError 为状态容量或分配失败。

本函数直接报告的具体错误：

- `TypeError`：参考归约需要ReferenceIntegralTerms。

返回类型：None。

源码：[`src/chronaxis/core/integral_sum_reference.py:49`](../../../src/chronaxis/core/integral_sum_reference.py#L49)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ReferenceIntegralSum-push_values"></a>
### `ReferenceIntegralSum.push_values`

按原顺序直接累加给定的浮点数序列，不要求调用方先构造积分面积对象。

```python
ReferenceIntegralSum.push_values(values: tuple[float, ...], valid: tuple[bool, ...]) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`values`|tuple[float, ...]|是|无|位置或关键字。当前这批要累加的数值；按输入顺序处理，不修改输入。|
|`valid`|tuple[bool, ...]|是|无|位置或关键字。每个值是否有效，与values等长；True参加累加，False位置不贡献数值。|

#### 返回说明

None；使用与原积分入口相同的误差状态、容量及中间失败规则。

#### 异常说明

TypeError/ValueError 为列结构；容量、分配或取消原样传播。

本函数直接报告的具体错误：

- `TypeError`：原序参考归约需要同长tuple数值与掩码。
- `ValueError`：参考归约需有限float及bool，未知位置存0。
- `IntegralStateLimitError`：积分误差项超过容量，不能截断继续。

#### 边界说明

仅复用本参考后端数值算法；调用方负责量纲、覆盖与候选内存预算。

返回类型：None。

源码：[`src/chronaxis/core/integral_sum_reference.py:65`](../../../src/chronaxis/core/integral_sum_reference.py#L65)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ReferenceIntegralSum-finish"></a>
### `ReferenceIntegralSum.finish`

归约有界误差项并只转换一次，保留原累计状态。

```python
ReferenceIntegralSum.finish(unit: str, factor: float=1.0) -> IntegralSumResult
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`unit`|str|是|无|位置或关键字。最终结果的单位，已由外层检查与输入物理量相容。|
|`factor`|int &#124; float|否|1.0|位置或关键字。把内部累计值换算到最终单位时乘的倍率；只在结束时应用一次，例如J换成Wh时为1/3600。|

#### 返回说明

冻结数值快照。

#### 异常说明

非法配置或分配错误传播；数值溢出/转换下溢写入失败结果。

返回类型：[IntegralSumResult](chronaxis.core.integral_sum.md#api-IntegralSumResult)。

源码：[`src/chronaxis/core/integral_sum_reference.py:121`](../../../src/chronaxis/core/integral_sum_reference.py#L121)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
