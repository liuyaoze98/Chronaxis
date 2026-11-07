# `chronaxis.core.calculation_series_join`

把数值列与筛选条件列对齐，形成一份CalculationSeries。例如功率每秒更新，开关每两秒更新时，要按双方的更新时间拆出共同时间段。条件的真假和未知状态分别保留；只有数值列的真实更新才计作新样本。超过max_intervals时停止并报错。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CalculationSeries](chronaxis.core.calculations.md#api-CalculationSeries)、[D](chronaxis.core.types.md#api-SignalDType)、[Interval](chronaxis.core.models.md#api-Interval)

## 对象导航

|对象|用途|
|---|---|
|[`_joint_times`](#api-_joint_times)|依次产生窗口首末及两轴内部边界，不保存合并轴。|
|[`join_calculation_series`](#api-join_calculation_series)|合并有限数值和BOOL输入，保留条件单独更新与真正样本的区别。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from bisect import bisect_right
from .calculations import CalculationSeries
from .models import Interval
from .types import SignalDType as D
```

</details>

<a id="api-_joint_times"></a>
## `_joint_times`

依次产生窗口首末及两轴内部边界，不保存合并轴。

```python
_joint_times(value, condition, window)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|[CalculationSeries](chronaxis.core.calculations.md#api-CalculationSeries)|是|无|位置或关键字。数值信号的时间序列，提供其更新时刻与观测范围。|
|`condition`|[CalculationSeries](chronaxis.core.calculations.md#api-CalculationSeries)|是|无|位置或关键字。BOOL筛选条件的时间序列；与数值序列共同确定需要切分的时间点。|
|`window`|[Interval](chronaxis.core.models.md#api-Interval)|是|无|位置或关键字。window是共同覆盖的Interval。|

### 返回说明

严格递增的整数纳秒生成器，点窗口只产生一点。

### 异常说明

已校验模型外的存储或分配发生异常时直接交给调用者处理。

源码：[`src/chronaxis/core/calculation_series_join.py:22`](../../../src/chronaxis/core/calculation_series_join.py#L22)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-join_calculation_series"></a>
## `join_calculation_series`

合并有限数值和BOOL输入，保留条件单独更新与真正样本的区别。

```python
join_calculation_series(value, condition, *, window=None, max_intervals=64)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|[CalculationSeries](chronaxis.core.calculations.md#api-CalculationSeries)|是|无|位置或关键字。主数值的时间片段和真实样本；与条件轴合并后决定哪些片段参加指标计算。|
|`condition`|[CalculationSeries](chronaxis.core.calculations.md#api-CalculationSeries)|是|无|位置或关键字。condition是BOOL列|
|`window`|[Interval](chronaxis.core.models.md#api-Interval) &#124; None|否|None|仅关键字。window需被双方完整覆盖，     省略时两列观测域必须相同|
|`max_intervals`|int|否|64|仅关键字。max_intervals是允许输出的正区间数。|

### 返回说明

新冻结CalculationSeries，conditions包含TRUE/FALSE/UNKNOWN。

### 异常说明

TypeError为模型或容量类型错误；ValueError为条件、窗口或容量超限。

本函数直接报告的具体错误：

- `TypeError`：联合指标输入需要两个有限CalculationSeries。
- `TypeError`：max_intervals需要原生int。
- `ValueError`：max_intervals必须为正整数。
- `ValueError`：联合输入不接受已经带选择条件的列。
- `ValueError`：选择条件需要无量纲BOOL列。
- `TypeError`：联合窗口需要Interval。
- `ValueError`：联合窗口必须由双方实际观测完整覆盖。
- `ValueError`：不同观测域必须显式给出共同窗口。
- `ValueError`：联合指标输入超过max_intervals，不丢弃边界。

### 边界说明

允许点窗口，但不外推EOF；调用方负责真实绑定/同步和先行预算预约。

源码：[`src/chronaxis/core/calculation_series_join.py:50`](../../../src/chronaxis/core/calculation_series_join.py#L50)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
