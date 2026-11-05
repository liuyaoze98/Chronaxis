# `chronaxis.core.integral_sum`

定义积分求和的返回值和容量限制。输入是各时间段已经算好的面积，输出包含总和及数值错误；有效时长和缺失区间另行保存。面积相加结束后才换算到输出单位。本模块本身不执行求和。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)

## 对象导航

|对象|用途|
|---|---|
|[`IntegralStateLimitError`](#api-IntegralStateLimitError)|表示误差项超过显式容量，调用方须停止当前归约并清理资源。|
|[`require_partial_limit`](#api-require_partial_limit)|校验误差项数量的硬上限。|
|[`require_sum_finish`](#api-require_sum_finish)|校验纯核的输出标签及一次性转换因子。|
|[`IntegralSumResult`](#api-IntegralSumResult)|保存已换单位的数值快照，不代替覆盖和最终 CalculationResult 分类。|
|[`IntegralSumResult.__post_init__`](#api-IntegralSumResult-__post_init__)|拒绝矛盾的冻结结果，不自动补零或修正故障。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from math import isfinite
from .types import QualityFlag as Q
from .validation import require_text
```

</details>

<a id="api-IntegralStateLimitError"></a>
## `IntegralStateLimitError`

表示误差项超过显式容量，调用方须停止当前归约并清理资源。

不截断误差项，也不把容量不足伪装为正常数值或 NONFINITE。

```python
class IntegralStateLimitError(ValueError)
```

继承关系：ValueError。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/core/integral_sum.py:15`](../../../src/chronaxis/core/integral_sum.py#L15)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-require_partial_limit"></a>
## `require_partial_limit`

校验误差项数量的硬上限。

```python
require_partial_limit(limit: int) -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`limit`|int|是|无|位置或关键字。limit 为正原生整数。|

### 返回说明

原值。

### 异常说明

ValueError 为 bool、非整数或非正数。

本函数直接报告的具体错误：

- `ValueError`：积分误差项容量需要正原生int。

返回类型：int。

源码：[`src/chronaxis/core/integral_sum.py:22`](../../../src/chronaxis/core/integral_sum.py#L22)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-require_sum_finish"></a>
## `require_sum_finish`

校验纯核的输出标签及一次性转换因子。

```python
require_sum_finish(unit: str, factor: float) -> tuple[str, float]
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`unit`|str|是|无|位置或关键字。unit 为非空标签|
|`factor`|float|是|无|位置或关键字。factor 为正有限原生 float。|

### 返回说明

(unit, factor)。

### 异常说明

TypeError/ValueError 为文字或因子错误；单位维度由外层 calculation_unit 校验。

本函数直接报告的具体错误：

- `ValueError`：积分转换因子需要正有限原生float。

返回类型：tuple[str, float]。

源码：[`src/chronaxis/core/integral_sum.py:33`](../../../src/chronaxis/core/integral_sum.py#L33)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-IntegralSumResult"></a>
## `IntegralSumResult`

保存已换单位的数值快照，不代替覆盖和最终 CalculationResult 分类。

valid_term_count 统计参与累计的有效面积项，与实际信号更新样本数不同。
无有效项时 value 为 None；有有效零面积时 value 为 0.0。

```python
class IntegralSumResult
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|float &#124; None|是|无|最终单位下的有限面积，未知或计算失败为 None。|
|`unit`|str|是|无|已由调用方声明的最终输出单位。|
|`calculation_failed`|bool|是|无|数值求和或最终转换失败，不表示输入全部未知。|
|`quality`|[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)|是|无|本次数值归约诊断，输入覆盖质量另保留在 IntegralFacts。|
|`valid_term_count`|int|是|无|原序有效面积项数，不冒充真实样本计数。|

源码：[`src/chronaxis/core/integral_sum.py:47`](../../../src/chronaxis/core/integral_sum.py#L47)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-IntegralSumResult-__post_init__"></a>
### `IntegralSumResult.__post_init__`

拒绝矛盾的冻结结果，不自动补零或修正故障。

```python
IntegralSumResult.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError 为结构或状态不一致。

本函数直接报告的具体错误：

- `TypeError`：积分数值结果需要真实状态、质量和非负整数计数。
- `ValueError`：积分数值结果只接受有限float或None。
- `ValueError`：积分计算失败需要有效项、None值及明确质量原因。
- `ValueError`：积分成功结果的数值、计数或质量不一致。

源码：[`src/chronaxis/core/integral_sum.py:60`](../../../src/chronaxis/core/integral_sum.py#L60)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
