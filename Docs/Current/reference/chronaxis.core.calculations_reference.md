# chronaxis.core.calculations_reference

独立计算保持值积分、时间统计、TRUE时长和真实样本统计。

compute_reference接收CalculationSeries和CalculationDefinition，先裁剪观测与请求窗口，
再独立计算面积、样本归约、覆盖时长及未知区间，输出CalculationResult。
积分使用零阶保持：左端值乘以相邻区间裁剪后的时长。先对整数纳秒端点
求差，再换算秒，不把较大的绝对时间先转成浮点数。
时间极值包含裁剪边界的保持值，time_weighted_mean按有效选择时长加权；duration
累计有效主BOOL为TRUE的区间。select_reference保留真实TRUE/UNKNOWN更新行。

样本统计只取actual_value_updates为True的真实数值更新，不包含窗口或
有效期到期边界，也不包括半开窗口末点。值有效与条件已知分别统计，
条件FALSE是已知未选中，UNKNOWN（未知）不能视作FALSE或补成零。

本实现只使用标准库与核心模型，数值和覆盖不调用NumPy。可共享输入
检查、单位与结果分类，但归约独立实现。保留完整内存输入，不读写文件，
不修改原数据或持有跨任务状态；本模块不提供流式内存预算保证。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)、[CalculationSeries](chronaxis.core.calculations.md#api-CalculationSeries)、[D](chronaxis.core.types.md#api-SignalDType)、[Interval](chronaxis.core.models.md#api-Interval)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)、[SelectionRow](chronaxis.core.selection.md#api-SelectionRow)、[Truth](chronaxis.core.types.md#api-Truth)

## 对象导航

|对象|用途|
|---|---|
|[`require_calculation`](#api-require_calculation)|验证实际指标输入模型，不执行任何面积或统计。|
|[`select_reference`](#api-select_reference)|按真实更新逐行返回TRUE与UNKNOWN选择结果，不累计输出列表。|
|[`compute_reference`](#api-compute_reference)|独立计算请求窗口内的积分、样本/时间统计或BOOL TRUE时长。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from math import fsum, isfinite
from .calculations import CalculationSeries, CalculationDefinition, make_calculation_result, calculation_unit
from .models import Interval
from .numeric import ScalarValue, to_float_reference
from .types import QualityFlag as Q, SignalDType as D, Truth
from .selection import SelectionRow, require_selection
from .record_intervals import clipped_record_seconds, require_record_step
```

</details>

<a id="api-require_calculation"></a>
## `require_calculation`

验证实际指标输入模型，不执行任何面积或统计。

```python
require_calculation(series, spec, *, step_ns=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`series`|[CalculationSeries](chronaxis.core.calculations.md#api-CalculationSeries)|是|无|位置或关键字。当前计算窗口的数值片段和真实样本；有条件计算时还包含对应的TRUE、FALSE或UNKNOWN选择状态。|
|`spec`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|位置或关键字。当前指标请求，指定运算、窗口、结果单位及部分数据的处理方式。|
|`step_ns`|int &#124; None|否|None|仅关键字。所选固定或DBC周期，单位纳秒且大于0；None表示采用实际时间间隔，不生成第二套时间坐标。|

### 返回说明

None，模型内部完整轴和dtype已校验。

### 异常说明

TypeError为无类型占位输入；ValueError为select标量执行或dtype不匹配。

本函数直接报告的具体错误：

- `TypeError`：指标执行需CalculationSeries和CalculationDefinition。
- `ValueError`：select需选择行流入口。
- `ValueError`：指标算子与输入dtype不匹配。

源码：[`src/chronaxis/core/calculations_reference.py:34`](../../../src/chronaxis/core/calculations_reference.py#L34)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-select_reference"></a>
## `select_reference`

按真实更新逐行返回TRUE与UNKNOWN选择结果，不累计输出列表。

```python
select_reference(series, spec)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`series`|[CalculationSeries](chronaxis.core.calculations.md#api-CalculationSeries)|是|无|位置或关键字。series完整内存CalculationSeries|
|`spec`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|位置或关键字。spec为select请求。|

### 返回说明

SelectionRow迭代器；UNKNOWN保留诊断，FALSE排除，窗口右端不输出。

### 异常说明

开始迭代时传播模型/算子/单位错误。

### 流程说明

遍历完整时间轴，只处理请求与观测交集内的真实目标依赖更新。
    合成边界与条件独自更新不产生行；无效值保持原质量，不填正常零。

源码：[`src/chronaxis/core/calculations_reference.py:58`](../../../src/chronaxis/core/calculations_reference.py#L58)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-compute_reference"></a>
## `compute_reference`

独立计算请求窗口内的积分、样本/时间统计或BOOL TRUE时长。

```python
compute_reference(series, spec, *, step_ns=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`series`|[CalculationSeries](chronaxis.core.calculations.md#api-CalculationSeries)|是|无|位置或关键字。完整CalculationSeries；数值统计需同一数值dtype，duration需BOOL。|
|`spec`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|位置或关键字。CalculationDefinition，给出左闭右开纳秒窗口、算子、输出单位和数据不全时的处理方式。|
|`step_ns`|int &#124; None|否|None|仅关键字。所选固定或DBC周期，单位纳秒且大于0；None表示采用实际时间间隔，不生成第二套时间坐标。|

### 返回说明

CalculationResult。未换单位的整数极值可保持精确整数；积分和样本平均
    返回浮点值；时间平均先规范化时长权重，duration输出秒。无法核实时
    为None，并保留覆盖、来源与质量原因；select使用独立行流入口。

### 异常说明

输入模型或单位配置错误直接传播TypeError或ValueError。
    非有限结果、下溢或转换丢精度作为质量原因返回，不吞配置错误。

### 流程说明

裁剪窗口后逐区间计算保持面积与三值选择交集，再按真实更新归约样本，
    最后应用一次输出单位转换并分类结果。正常零与无效数据位置暂存的值分别处理。
    临时值和诊断列表只用于本次计算，不修改调用者的CalculationSeries。

源码：[`src/chronaxis/core/calculations_reference.py:87`](../../../src/chronaxis/core/calculations_reference.py#L87)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
