# `chronaxis.execution.calculation_values`

读取计算列中的有效标量，并按当前消息原值决定方向桶及跳过原因。

这些纯函数不访问来源、消息历史或结果仓；参考与数组执行共用相同边界语义。
无效占位不当有效数值，方向字段不应用普通信号转换，表达式失败原因优先。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[LegacySkipReason](chronaxis.legacy.sum.md#api-LegacySkipReason)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)

## 对象导航

|对象|用途|
|---|---|
|[`scalar_from_column`](#api-scalar_from_column)|取一项实际归一化值，失效时保留原诊断而不把数组占位当正常值。|
|[`_scalar_from_validated_column`](#api-_scalar_from_validated_column)|借用当前适配器刚核过且未交给外部的列，不重验每个标签域。|
|[`_extract_scalar`](#api-_extract_scalar)|按列原有规则取值并交给内部选定的构造器。|
|[`direction_bucket_state`](#api-direction_bucket_state)|按同条原值判桶，既不转换单位也不把缺值或非有限当正常零。|
|[`direction_skip_reason`](#api-direction_skip_reason)|保表达式失败优先，只有有效表达式才用原方向决定是否跳过。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from math import isfinite
from ..core.numeric import ScalarValue
from ..core.scalar import _scalar_from_validated_fields
from ..core.types import QualityFlag as Q, _QUALITY_BY_MASK
from ..legacy.sum import LegacySkipReason
```

</details>

<a id="api-scalar_from_column"></a>
## `scalar_from_column`

取一项实际归一化值，失效时保留原诊断而不把数组占位当正常值。

```python
scalar_from_column(column, index)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`column`|SignalSeries 或 NumericArray|是|无|位置或关键字。当前批次的归一化数据列，提供值、有效掩码、质量和类型；枚举有效值恢复为标签。|
|`index`|int|是|无|位置或关键字。该列内要读取的元素下标；必须对应同一批次有效位置，不是原文件行号。|

### 返回说明

ScalarValue。

### 异常说明

原类型/布局错误；不做第二次数值转换。

源码：[`src/chronaxis/execution/calculation_values.py:13`](../../../src/chronaxis/execution/calculation_values.py#L13)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_scalar_from_validated_column"></a>
## `_scalar_from_validated_column`

借用当前适配器刚核过且未交给外部的列，不重验每个标签域。

```python
_scalar_from_validated_column(column, index)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`column`|NumericArray &#124; SignalSeries|是|无|位置或关键字。当前调用链已经检查的数值列；保留既有dtype、质量、标签和原值含义。|
|`index`|int|是|无|位置或关键字。要提取的位置，须在当前列的范围内。|

### 返回说明

ScalarValue；不复制列或保留另一份值。

### 异常说明

索引/分配原错。
公开或来源不明的列须用scalar_from_column，不使用本内部入口。

源码：[`src/chronaxis/execution/calculation_values.py:22`](../../../src/chronaxis/execution/calculation_values.py#L22)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_extract_scalar"></a>
## `_extract_scalar`

按列原有规则取值并交给内部选定的构造器。

```python
_extract_scalar(column, index, factory)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`column`|NumericArray &#124; SignalSeries|是|无|位置或关键字。当前调用链已经检查的数值列；保留既有dtype、质量、标签和原值含义。|
|`index`|int|是|无|位置或关键字。要提取的位置，须在当前列的范围内。|
|`factory`|Callable[..., [ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)]|是|无|位置或关键字。构造提取值的内部函数：公开路径使用ScalarValue完整检查，内部已核路径使用受限工厂。|

### 返回说明

ScalarValue。

### 异常说明

索引、标签或构造错误传播；无效值不读取数组占位为真值。

源码：[`src/chronaxis/execution/calculation_values.py:32`](../../../src/chronaxis/execution/calculation_values.py#L32)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-direction_bucket_state"></a>
## `direction_bucket_state`

按同条原值判桶，既不转换单位也不把缺值或非有限当正常零。

```python
direction_bucket_state(raw, bucket)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`raw`|int、float、bool 或 None|是|无|位置或关键字。同一条消息中的原方向数值，不做单位换算；None表示缺失，非有限值不能选桶。|
|`bucket`|str|是|无|位置或关键字。已校验的positive或negative；分别选严格大于0或严格小于0，零值不选中。|

### 返回说明

方向质量及是否选中。

### 异常说明

TypeError为非原生数值，不接受NumPy标量。

源码：[`src/chronaxis/execution/calculation_values.py:53`](../../../src/chronaxis/execution/calculation_values.py#L53)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-direction_skip_reason"></a>
## `direction_skip_reason`

保表达式失败优先，只有有效表达式才用原方向决定是否跳过。

```python
direction_skip_reason(value, reason, direction_quality, selected)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)|是|无|位置或关键字。表达式的带有明确类型的数值及有效标志；仅有效值继续结合方向质量与筛选，原求值失败不被覆盖。|
|`reason`|[LegacySkipReason](chronaxis.legacy.sum.md#api-LegacySkipReason) 或 None|是|无|位置或关键字。表达式已有的跳过原因；表达式无效时保原原因，有效时才结合方向筛选。|
|`direction_quality`|QualityFlag|是|无|位置或关键字。方向信号的质量位；缺失优先产生missing_input，非有限产生nonfinite_input。|
|`selected`|bool|是|无|位置或关键字。原方向筛选是否选中当前消息；表达式有效且False时返回condition_false。|

### 返回说明

最终LegacySkipReason或None。

### 异常说明

无主动异常；不修改累计器或原质量。

源码：[`src/chronaxis/execution/calculation_values.py:67`](../../../src/chronaxis/execution/calculation_values.py#L67)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
