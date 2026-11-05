# `chronaxis.core.quantile_reference`

在标量原dtype域排序并对唯一一对相邻样本作精确加权插值。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)

## 对象导航

|对象|用途|
|---|---|
|[`ordered_reference`](#api-ordered_reference)|在全部已选标量中定位顺序统计值，再计算线性插值。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from fractions import Fraction
from itertools import chain
from .numeric import _exact_float
from .types import QualityFlag as Q
```

</details>

<a id="api-ordered_reference"></a>
## `ordered_reference`

在全部已选标量中定位顺序统计值，再计算线性插值。

```python
ordered_reference(chunks, index, remainder, denominator)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`chunks`|Sequence[Sequence[int &#124; float]]|是|无|位置或关键字。此前各批保留的非重叠已选样本，按原类型合并后在全总体上排序。|
|`index`|int|是|无|位置或关键字。从零起算的下侧顺序统计位置，即 (N−1)×q 的整数部分。|
|`remainder`|int|是|无|位置或关键字。分位位置的小数部分的分子；为零时直接返回下侧的原类型值。|
|`denominator`|int|是|无|位置或关键字。插值权重的正分母，上侧顺序统计值的权重为 remainder/denominator。|

### 返回说明

(数值或None,质量)，精确秩保持原dtype。

### 异常说明

排序需要的内存由调用方预付，分配错误直接传播。

源码：[`src/chronaxis/core/quantile_reference.py:9`](../../../src/chronaxis/core/quantile_reference.py#L9)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
