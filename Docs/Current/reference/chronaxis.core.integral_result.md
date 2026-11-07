# `chronaxis.core.integral_result`

将积分数值和同一次计算的有效时长、缺失区间组合成CalculationResult。根据report或strict以及最低覆盖要求确定是否保留数值。这里不重新计算面积，也不再次转换单位；调用方应把同一个积分器返回的两部分一起传入。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CalculationResult](chronaxis.core.calculations.md#api-CalculationResult)、[IntegralFacts](chronaxis.core.integral_terms.md#api-IntegralFacts)、[IntegralSumResult](chronaxis.core.integral_sum.md#api-IntegralSumResult)

## 对象导航

|对象|用途|
|---|---|
|[`make_integral_result`](#api-make_integral_result)|把同一归约的数值及完整覆盖按现有政策归类。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .integral_terms import IntegralFacts
from .integral_sum import IntegralSumResult
from .calculations import CalculationResult, calculation_unit, make_calculation_result
```

</details>

<a id="api-make_integral_result"></a>
## `make_integral_result`

把同一归约的数值及完整覆盖按现有政策归类。

```python
make_integral_result(facts: IntegralFacts, number: IntegralSumResult) -> CalculationResult
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`facts`|[IntegralFacts](chronaxis.core.integral_terms.md#api-IntegralFacts)|是|无|位置或关键字。facts 为完整真实交集事实|
|`number`|[IntegralSumResult](chronaxis.core.integral_sum.md#api-IntegralSumResult)|是|无|位置或关键字。number 为已经换成最终单位的数值快照。|

### 返回说明

CalculationResult，保留原请求、样本、未知范围、质量及完整来源子类。

### 异常说明

TypeError/ValueError 为模型、单位、范围或计数矛盾；分配错误传播。

本函数直接报告的具体错误：

- `TypeError`：积分分类需要IntegralFacts和IntegralSumResult。
- `ValueError`：积分数值输出单位与原请求不一致。
- `ValueError`：积分实际观测越过原请求。
- `ValueError`：积分面积项数、有效时长与真实样本不一致。
- `ValueError`：积分有效与未知时长未完整划分实际窗口。
- `ValueError`：积分未知范围需有序且不重叠。

### 边界说明

无条件积分，已知条件时长等于实际跨度；没有全 FALSE 的选择证据。

返回类型：[CalculationResult](chronaxis.core.calculations.md#api-CalculationResult)。

源码：[`src/chronaxis/core/integral_result.py:16`](../../../src/chronaxis/core/integral_result.py#L16)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
