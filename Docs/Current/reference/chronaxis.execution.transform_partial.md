# `chronaxis.execution.transform_partial`

区分滚动输入窗口的部分性和下游查询轴的覆盖率，只标记确实参与的原值。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)

## 对象导航

|对象|用途|
|---|---|
|[`partial_in_block`](#api-partial_in_block)|核实当前有限块是否实际使用部分值或部分选择条件。|
|[`partial_result`](#api-partial_result)|保留原失败，或将有限估算按当前指标政策输出。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import replace
from ..core.types import QualityFlag as Q
```

</details>

<a id="api-partial_in_block"></a>
## `partial_in_block`

核实当前有限块是否实际使用部分值或部分选择条件。

```python
partial_in_block(rows, window, *, samples)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`rows`|Sequence[tuple]|是|无|位置或关键字。同一有限块中的时间、数值、截止、条件、条件截止及可选真实更新标志。|
|`window`|Interval|是|无|位置或关键字。判定样本或正时长区间是否属于所请求范围的半开区间。|
|`samples`|bool|是|无|仅关键字。为真时只检查有效且被选的真实更新；为假时检查有正持续时间的参与区间。|

### 返回说明

有属于半开窗口的真实选中样本，或有选中且有效的正长度保持区间时返回 True。

### 异常说明

内部行损坏时传播结构错误；不把末端共享点计入两块。

源码：[`src/chronaxis/execution/transform_partial.py:7`](../../../src/chronaxis/execution/transform_partial.py#L7)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-partial_result"></a>
## `partial_result`

保留原失败，或将有限估算按当前指标政策输出。

```python
partial_result(result, policy)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`result`|RecordIntegralResult &#124; RecordTimeResult|是|无|位置或关键字。已经结算的冻结结果，若有部分输入则在副本中补上状态与质量。|
|`policy`|str|是|无|位置或关键字。当前请求的report或strict政策，决定部分数值能否作为结果保留。|

### 返回说明

新结果。

### 异常说明

非结果对象。

源码：[`src/chronaxis/execution/transform_partial.py:36`](../../../src/chronaxis/execution/transform_partial.py#L36)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
