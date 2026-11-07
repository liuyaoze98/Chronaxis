# `chronaxis.core.quantile_numpy`

为已付费的样本数组作原dtype全局排序，然后仅恢复两个标量端点。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)

## 对象导航

|对象|用途|
|---|---|
|[`ordered_numpy`](#api-ordered_numpy)|用NumPy原地堆排序得到顺序统计值，并从其精确比值一次舍入插值。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .types import QualityFlag as Q
```

</details>

<a id="api-ordered_numpy"></a>
## `ordered_numpy`

用NumPy原地堆排序得到顺序统计值，并从其精确比值一次舍入插值。

```python
ordered_numpy(chunks, index, remainder, denominator)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`chunks`|Sequence[numpy.ndarray]|是|无|位置或关键字。此前各批保留的非重叠已选样本，按原类型合并后在全总体上排序。|
|`index`|int|是|无|位置或关键字。从零起算的下侧顺序统计位置，即 (N−1)×q 的整数部分。|
|`remainder`|int|是|无|位置或关键字。分位位置的小数部分的分子；为零时直接返回下侧的原类型值。|
|`denominator`|int|是|无|位置或关键字。插值权重的正分母，上侧顺序统计值的权重为 remainder/denominator。|

### 返回说明

(原生数值或None,质量)，整数端点不转float。

### 异常说明

预算由外层预付，数组分配或索引错误直接传播。

源码：[`src/chronaxis/core/quantile_numpy.py:7`](../../../src/chronaxis/core/quantile_numpy.py#L7)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
