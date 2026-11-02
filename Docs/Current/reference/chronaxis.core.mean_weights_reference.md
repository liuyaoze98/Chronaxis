# chronaxis.core.mean_weights_reference

复用标量均值的先归一化再相乘规则，避免先求面积导致溢出。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)

## 对象导航

|对象|用途|
|---|---|
|[`normalized_mean_terms`](#api-normalized_mean_terms)|将有限有效值按整窗正分母加权，返回原序项和计算质量。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from math import isfinite
from .types import QualityFlag as Q
```

</details>

<a id="api-normalized_mean_terms"></a>
## `normalized_mean_terms`

将有限有效值按整窗正分母加权，返回原序项和计算质量。

```python
normalized_mean_terms(values, weights, denominator)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`values`|Sequence[int &#124; float]|是|无|位置或关键字。当前有限批的有效数值，与权重按位置一一对应；按原序归约。|
|`weights`|Sequence[int &#124; float]|是|无|位置或关键字。与数值一一对应的非负权重；实际模式为纳秒，固定或DBC模式为所选周期的秒数。|
|`denominator`|int &#124; float|是|无|位置或关键字。已经累计的正权重总数；与weights使用相同单位，先除后乘以降低中间数溢出风险。|

### 返回说明

(tuple, QualityFlag)。

### 异常说明

结构或分配错误传播；非有限/下溢标质量。

源码：[`src/chronaxis/core/mean_weights_reference.py:7`](../../../src/chronaxis/core/mean_weights_reference.py#L7)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
