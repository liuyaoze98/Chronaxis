# chronaxis.core.integral_sum_numpy

按原顺序累加各段积分面积，并用NumPy保存浮点误差项，减少大数相减后丢失小数的情况。每次push处理一块面积，finish返回当前总和并换算输出单位。partial_limit限制误差项数量；容量不足会报错。中途溢出后，后续抵消不会把结果恢复为正常值。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[IntegralStateLimitError](chronaxis.core.integral_sum.md#api-IntegralStateLimitError)、[IntegralSumResult](chronaxis.core.integral_sum.md#api-IntegralSumResult)、[NumpyIntegralTerms](chronaxis.core.integral_terms_numpy.md#api-NumpyIntegralTerms)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)

## 对象导航

|对象|用途|
|---|---|
|[`NumpyIntegralSum`](#api-NumpyIntegralSum)|保存有限 float64 误差项和有效项计数，保持跨块原序及持久溢出状态。|
|[`NumpyIntegralSum.__init__`](#api-NumpyIntegralSum-__init__)|建立独立的空数组误差状态。|
|[`NumpyIntegralSum.valid_term_count`](#api-NumpyIntegralSum-valid_term_count)|返回已经处理的有效面积项数；即使累计中途溢出，导致溢出的项及后续有效项仍计数。|
|[`NumpyIntegralSum.calculation_failed`](#api-NumpyIntegralSum-calculation_failed)|返回累计是否已经发生数值计算失败，例如累加结果变成无穷大。True表示本次累计不能作为正常积分值，即使后续又读到了有效数据也不能当先前错误没发生。|
|[`NumpyIntegralSum.partial_count`](#api-NumpyIntegralSum-partial_count)|读取当前持有的非零误差项数，不暴露可修改的数组。|
|[`NumpyIntegralSum.push`](#api-NumpyIntegralSum-push)|按原顺序逐项累加当前块中的有效面积，不先把整块相加成一个数。|
|[`NumpyIntegralSum.push_values`](#api-NumpyIntegralSum-push_values)|直接累加给定的浮点数序列，不要求调用方先构造积分面积对象。|
|[`NumpyIntegralSum._advance`](#api-NumpyIntegralSum-_advance)|生成一项的独立误差候选，不提前改写当前状态。|
|[`NumpyIntegralSum.finish`](#api-NumpyIntegralSum-finish)|正确舍入当前误差状态，再做一次输出单位换算，返回独立快照。|
|[`NumpyIntegralSum._rounded`](#api-NumpyIntegralSum-_rounded)|从最大误差项向小项求和，在首个舍入误差处完成半偶修正。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .integral_sum import IntegralStateLimitError, IntegralSumResult, require_partial_limit, require_sum_finish
from .integral_terms_numpy import NumpyIntegralTerms
from .types import QualityFlag as Q
```

</details>

<a id="api-NumpyIntegralSum"></a>
## `NumpyIntegralSum`

保存有限 float64 误差项和有效项计数，保持跨块原序及持久溢出状态。

partials 只在完整单项候选满足容量后安装，不按输入项数增长；中途溢出
清空数值状态并永久标失败，但后续有效面积仍计数。输入和已返回结果不被修改。

```python
NumpyIntegralSum(partial_limit: int=4096)
```


源码：[`src/chronaxis/core/integral_sum_numpy.py:21`](../../../src/chronaxis/core/integral_sum_numpy.py#L21)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-NumpyIntegralSum-__init__"></a>
### `NumpyIntegralSum.__init__`

建立独立的空数组误差状态。

```python
NumpyIntegralSum.__init__(partial_limit: int=4096)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`partial_limit`|int|否|4096|位置或关键字。大于0的整数，限制浮点累加时保留的误差补偿项数量。默认4096；它不是样本数上限，也不是允许出现多少次错误。超过容量会报错。|

#### 返回说明

无；初始化有效项数 0、累计故障 False 及空 float64 数组。

#### 异常说明

TypeError/ValueError 为限额不合法；内存分配错误直接传播。

源码：[`src/chronaxis/core/integral_sum_numpy.py:28`](../../../src/chronaxis/core/integral_sum_numpy.py#L28)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-NumpyIntegralSum-valid_term_count"></a>
### `NumpyIntegralSum.valid_term_count`

返回已经处理的有效面积项数；即使累计中途溢出，导致溢出的项及后续有效项仍计数。

```python
NumpyIntegralSum.valid_term_count: int
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

非负原生 int。

#### 异常说明

无。

返回类型：int。

源码：[`src/chronaxis/core/integral_sum_numpy.py:42`](../../../src/chronaxis/core/integral_sum_numpy.py#L42)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-NumpyIntegralSum-calculation_failed"></a>
### `NumpyIntegralSum.calculation_failed`

返回累计是否已经发生数值计算失败，例如累加结果变成无穷大。True表示本次累计不能作为正常积分值，即使后续又读到了有效数据也不能当先前错误没发生。

```python
NumpyIntegralSum.calculation_failed: bool
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

bool；finish 的单位换算故障不修改本属性。

#### 异常说明

无。

返回类型：bool。

源码：[`src/chronaxis/core/integral_sum_numpy.py:51`](../../../src/chronaxis/core/integral_sum_numpy.py#L51)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-NumpyIntegralSum-partial_count"></a>
### `NumpyIntegralSum.partial_count`

读取当前持有的非零误差项数，不暴露可修改的数组。

```python
NumpyIntegralSum.partial_count: int
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

不超过 partial_limit 的原生 int。

#### 异常说明

无。

返回类型：int。

源码：[`src/chronaxis/core/integral_sum_numpy.py:60`](../../../src/chronaxis/core/integral_sum_numpy.py#L60)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-NumpyIntegralSum-push"></a>
### `NumpyIntegralSum.push`

按原顺序逐项累加当前块中的有效面积，不先把整块相加成一个数。

```python
NumpyIntegralSum.push(terms: NumpyIntegralTerms) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`terms`|[NumpyIntegralTerms](chronaxis.core.integral_terms_numpy.md#api-NumpyIntegralTerms)|是|无|位置或关键字。terms 为已校验的只读 float64 面积、bool 掩码和 IntegralFacts。|

#### 返回说明

None；安装成功的单项更新状态和有效计数，输入数组保持原样。

#### 异常说明

TypeError 为输入类型错误；IntegralStateLimitError 为候选容量超限；
分配或取消错误传播。超限项不安装，其前面已成功消费的项保留。

返回类型：None。

源码：[`src/chronaxis/core/integral_sum_numpy.py:68`](../../../src/chronaxis/core/integral_sum_numpy.py#L68)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-NumpyIntegralSum-push_values"></a>
### `NumpyIntegralSum.push_values`

直接累加给定的浮点数序列，不要求调用方先构造积分面积对象。

```python
NumpyIntegralSum.push_values(values: np.ndarray, valid: np.ndarray) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`values`|numpy.ndarray[float64]|是|无|位置或关键字。当前这批要累加的数值；按输入顺序处理，不修改输入。|
|`valid`|numpy.ndarray[bool]|是|无|位置或关键字。每个值是否有效，与values等长；True参加累加，False位置不贡献数值。|

#### 返回说明

None；原序推进、容量、中间溢出及finish行为与积分入口相同。

#### 异常说明

TypeError/ValueError 为结构或写保护错误；容量、分配和取消传播。
内存: 检查掩码与索引均为当前有限(N,)临时列，调用方必须先预约预算。

返回类型：None。

源码：[`src/chronaxis/core/integral_sum_numpy.py:86`](../../../src/chronaxis/core/integral_sum_numpy.py#L86)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-NumpyIntegralSum-_advance"></a>
### `NumpyIntegralSum._advance`

生成一项的独立误差候选，不提前改写当前状态。

```python
NumpyIntegralSum._advance(area: np.float64) -> np.ndarray | None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`area`|np.float64|是|无|位置或关键字。area 为有限 float64 面积，量纲仍为 input_unit 乘秒。|

#### 返回说明

float64 形状 (K,) 的新候选，K 不超过限额；中途非有限返回 None。

#### 异常说明

IntegralStateLimitError 为候选超限；分配和取消错误传播。

本函数直接报告的具体错误：

- `IntegralStateLimitError`：数组积分误差状态超过 partial_limit。

返回类型：np.ndarray &#124; None。

源码：[`src/chronaxis/core/integral_sum_numpy.py:125`](../../../src/chronaxis/core/integral_sum_numpy.py#L125)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-NumpyIntegralSum-finish"></a>
### `NumpyIntegralSum.finish`

正确舍入当前误差状态，再做一次输出单位换算，返回独立快照。

```python
NumpyIntegralSum.finish(unit: str, factor: float=1.0) -> IntegralSumResult
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`unit`|str|是|无|位置或关键字。unit 为非空输出单位|
|`factor`|float|否|1.0|位置或关键字。factor 为正有限原生 float，仅在最后相乘。|

#### 返回说明

IntegralSumResult；没有有效项为 None，有效全零为 +0.0；累计或
换算非有限为 NONFINITE，非零换算下溢为 PRECISION_LOSS，均标计算失败。

#### 异常说明

TypeError/ValueError 为参数错误；分配或取消错误传播。

返回类型：[IntegralSumResult](chronaxis.core.integral_sum.md#api-IntegralSumResult)。

源码：[`src/chronaxis/core/integral_sum_numpy.py:161`](../../../src/chronaxis/core/integral_sum_numpy.py#L161)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-NumpyIntegralSum-_rounded"></a>
### `NumpyIntegralSum._rounded`

从最大误差项向小项求和，在首个舍入误差处完成半偶修正。

```python
NumpyIntegralSum._rounded() -> np.float64
```

参数：无显式参数。


#### 参数说明

无；当前状态必须至少包含一个非零有限 partial。

#### 返回说明

当前原量纲的正确舍入 float64；不修改误差数组。

#### 异常说明

分配或取消错误传播；数值非有限由 finish 分类。

返回类型：np.float64。

源码：[`src/chronaxis/core/integral_sum_numpy.py:190`](../../../src/chronaxis/core/integral_sum_numpy.py#L190)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
