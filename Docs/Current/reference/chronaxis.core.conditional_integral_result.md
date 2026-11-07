# `chronaxis.core.conditional_integral_result`

把已经算出的条件积分、有效时长和缺失区间整理成CalculationResult。只有完整观察到请求范围、且条件始终为假时，才能返回“没有选中数据”的零值。数据不足时按report或strict处理。数值和统计信息必须来自同一次计算，本模块不会再次积分或换算单位。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CalculationResult](chronaxis.core.calculations.md#api-CalculationResult)、[ConditionalIntegralFacts](chronaxis.core.conditional_integral_terms.md#api-ConditionalIntegralFacts)、[IntegralSumResult](chronaxis.core.integral_sum.md#api-IntegralSumResult)

## 对象导航

|对象|用途|
|---|---|
|[`make_conditional_integral_result`](#api-make_conditional_integral_result)|把完整覆盖与数值快照分类，保留TRUE/FALSE/UNKNOWN和原来源。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .conditional_integral_terms import ConditionalIntegralFacts
from .integral_sum import IntegralSumResult
from .calculations import CalculationResult, calculation_unit, make_calculation_result
```

</details>

<a id="api-make_conditional_integral_result"></a>
## `make_conditional_integral_result`

把完整覆盖与数值快照分类，保留TRUE/FALSE/UNKNOWN和原来源。

```python
make_conditional_integral_result(facts: ConditionalIntegralFacts, number: IntegralSumResult) -> CalculationResult
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`facts`|[ConditionalIntegralFacts](chronaxis.core.conditional_integral_terms.md#api-ConditionalIntegralFacts)|是|无|位置或关键字。整段请求的覆盖时长、未知区间、样本数和来源记录；用于判断积分结果是否完整。|
|`number`|[IntegralSumResult](chronaxis.core.integral_sum.md#api-IntegralSumResult)|是|无|位置或关键字。同一累计器最后得到且已换算结果单位的数值快照；与facts共同决定最终积分值和覆盖状态。|

### 返回说明

CalculationResult；原数值质量与输入原因完整合并，FALSE零由既有政策产生。

### 异常说明

TypeError/ValueError为类型、单位或样本/面积项数矛盾；分配错误传播。

本函数直接报告的具体错误：

- `TypeError`：条件积分分类需要ConditionalIntegralFacts和IntegralSumResult。
- `ValueError`：条件积分数值单位与原请求不一致。
- `ValueError`：条件积分样本、正常面积项数与选择时长不一致。

返回类型：[CalculationResult](chronaxis.core.calculations.md#api-CalculationResult)。

源码：[`src/chronaxis/core/conditional_integral_result.py:16`](../../../src/chronaxis/core/conditional_integral_result.py#L16)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
