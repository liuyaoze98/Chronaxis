# `chronaxis.core.rolling_values`

对已裁剪的有限保持区间求一个滚动网格值。

权重是实际纳秒或原周期按实际重叠分摊的计量纳秒。独立参考路径使用精确
有理数累计，数组路径对当次窗口执行 NumPy 掩码和缩放加权归约。历史维护、
覆盖门槛、网格原点和事件均由调用者处理；本模块不保存上一个窗口。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)

## 对象导航

|对象|用途|
|---|---|
|[`rolling_value`](#api-rolling_value)|计算选中窗口值。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from fractions import Fraction
from math import frexp, isfinite, ldexp
from .numeric import ScalarValue
from .types import SignalDType as D, QualityFlag as Q
```

</details>

<a id="api-rolling_value"></a>
## `rolling_value`

计算选中窗口值。

```python
rolling_value(operation, backend, values, weights, conversion, dtype)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`operation`|str|是|无|位置或关键字。选择滚动时间均值、积分、最小值或最大值的一种已登记算法。|
|`backend`|str|是|无|位置或关键字。为当前窗口选择独立的reference或numpy数值归约。|
|`values`|Sequence[int &#124; float]|是|无|位置或关键字。窗口内有效、占有正长度保持段的原生数值，与权重逐项对应。|
|`weights`|Sequence[int &#124; Fraction]|是|无|位置或关键字。每段覆盖的实际或周期折算纳秒，允许非整纳秒的精确重叠比例。|
|`conversion`|CalculationConversion|是|无|位置或关键字。将本次窗口归约的原单位结果转换到目标单位的倍率、偏移及类型规则。|
|`dtype`|SignalDType|是|无|位置或关键字。数值序列的原始整数或浮点类型，决定极值保型和精度检查。|

### 返回说明

ScalarValue。

### 异常说明

配置错误。

源码：[`src/chronaxis/core/rolling_values.py:13`](../../../src/chronaxis/core/rolling_values.py#L13)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
