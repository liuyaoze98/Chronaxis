# `chronaxis.core.calculations_memory_reference`

从现有内存信号计算表达式，接入参考统计、TRUE时长或选择行流。

输入为已编译表达式、CalculationDefinition和可选布尔条件。先检查真实绑定
及多来源同步依据，再从原行提取依赖，按更新、有效期和窗口边界建立
共同纳秒轴；参考对齐与表达式求值生成CalculationSeries，最后得到CalculationResult。
duration主表达式需BOOL，select可保留数值、BOOL或ENUM原值；选择行流返回
SelectionRow迭代器，其输入和中间历史仍完整物化，不能据此宣称生产预算完成。

真实样本标志只取数值表达式的依赖更新；条件独自更新和合成窗口边界
不能新增数值样本。每个左端值用于直到下一时间的区间，末点不增加面积。
数值与条件分别保存有效性，原依赖质量另存，UNKNOWN不能当作FALSE。

依赖参考转换、对齐、表达式和指标模块，不读取日志、调用旧解码或写出。
这是完整内存历史的便利入口，创建本次局部结果，不修改输入，不跨任务
继承绑定或信号值，也不调用NumPy数值内核。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)、[CalculationSeries](chronaxis.core.calculations.md#api-CalculationSeries)、[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)、[D](chronaxis.core.types.md#api-SignalDType)、[Interval](chronaxis.core.models.md#api-Interval)、[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)

## 对象导航

|对象|用途|
|---|---|
|[`_scalar_context`](#api-_scalar_context)|把同一时刻各信号的保持值整理为标量表达式输入。|
|[`require_calculation_plan`](#api-require_calculation_plan)|检查指标表达式类型及可选条件是否属于同一真实输入。|
|[`build_calculation_series_reference`](#api-build_calculation_series_reference)|从当前原行生成完整指标时间轴、值、条件和真实更新标志。|
|[`select_memory_reference`](#api-select_memory_reference)|从现有内存信号独立对齐求值，返回真实更新选择行流。|
|[`compute_memory_reference`](#api-compute_memory_reference)|从已有内存行执行参考表达式和指标计算，返回完整指标结果。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .enum_codes import memory_histories, aligned_scalar
from .expression import CompiledExpression
from .expression_reference import evaluate_reference
from .calculations import CalculationSeries, CalculationDefinition, calculation_conversion
from .calculations_reference import compute_reference, select_reference
from .models import Interval
from .numeric import ScalarValue, memory_series_reference
from .state import align_reference, common_timeline
from .types import SignalDType as D
from .where_updates import contains_where, reference_updates
```

</details>

<a id="api-_scalar_context"></a>
## `_scalar_context`

把同一时刻各信号的保持值整理为标量表达式输入。

```python
_scalar_context(bindings, aligned, index)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`bindings`|SignalBindings|是|无|位置或关键字。内存信号绑定，通过别名查找对应类型、枚举标签与原码设置。|
|`aligned`|Mapping[str, Sequence[StateValue]]|是|无|位置或关键字。别名到已按共同时间轴对齐的保持结果序列，保留有效性和质量。|
|`index`|int|是|无|位置或关键字。当前时刻在公共时间轴上的零基位置，从各序列取该位置的保持结果。|

### 返回说明

保留类型、有效性及枚举域的标量映射。

### 异常说明

无效绑定或位置直接报错。

源码：[`src/chronaxis/core/calculations_memory_reference.py:38`](../../../src/chronaxis/core/calculations_memory_reference.py#L38)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-require_calculation_plan"></a>
## `require_calculation_plan`

检查指标表达式类型及可选条件是否属于同一真实输入。

```python
require_calculation_plan(compiled, spec, condition)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiled`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)|是|无|位置或关键字。当前CompiledExpression；duration需BOOL，select可使用全部声明dtype。|
|`spec`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|位置或关键字。CalculationDefinition，其他标量统计要求数值根。|
|`condition`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)|是|无|位置或关键字。可选BOOL根的CompiledExpression，须与数值计划的绑定身份相同。|

### 返回说明

合并去重后的实际依赖名称元组，保留数值依赖在前的顺序。

### 异常说明

TypeError: 数值计划或请求模型类型错误。
    ValueError: 根与算子类型不匹配、条件不是BOOL、绑定身份冲突或同步不足。

本函数直接报告的具体错误：

- `TypeError`：memory指标需CompiledExpression及CalculationDefinition。
- `ValueError`：指标表达式dtype与算子不匹配。
- `ValueError`：指标条件需BOOL且真实binding identity相同。

### 边界说明

只合并分析层依赖并检查当前同步声明，不改变旧读取范围或解码调用。

源码：[`src/chronaxis/core/calculations_memory_reference.py:52`](../../../src/chronaxis/core/calculations_memory_reference.py#L52)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-build_calculation_series_reference"></a>
## `build_calculation_series_reference`

从当前原行生成完整指标时间轴、值、条件和真实更新标志。

```python
build_calculation_series_reference(compiled, spec, *, condition=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiled`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)|是|无|位置或关键字。当前已校验表达式，类型与spec算子匹配；spec为窗口与指标请求。|
|`spec`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|位置或关键字。compiled: 当前已校验表达式，类型与spec算子匹配；spec为窗口与指标请求。     condition: 可选且绑定身份一致的BOOL表达式，省略表示不按条件筛选。|
|`condition`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression) &#124; None|否|None|仅关键字。可选且绑定身份一致的BOOL表达式，省略表示不按条件筛选。|

### 返回说明

CalculationSeries。时间为整数纳秒，值与条件共用完整轴；窗口边界可参与
    积分保持，但actual_value_updates为False，不作为真实样本。

### 异常说明

绑定、时间、来源、同步或配置检查失败时传播底层异常。

### 流程说明

提取依赖并归一化，加入域内窗口端点，参考保持后逐时间组求值。
    条件依赖可增加时间边界，真实样本标志只来自数值依赖。
    保留完整内存历史和新结果，不延长会话观测域，也不额外读取或解码。

源码：[`src/chronaxis/core/calculations_memory_reference.py:93`](../../../src/chronaxis/core/calculations_memory_reference.py#L93)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-select_memory_reference"></a>
## `select_memory_reference`

从现有内存信号独立对齐求值，返回真实更新选择行流。

```python
select_memory_reference(compiled, spec, *, condition=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiled`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)|是|无|位置或关键字。compiled当前绑定表达式|
|`spec`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|位置或关键字。spec为select|
|`condition`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression) &#124; None|否|None|仅关键字。condition可选同身份BOOL表达式。|

### 返回说明

SelectionRow迭代器，不积累全部输出行。

### 异常说明

构造时间轴/求值时传播输入错误；筛选配置错误在消费时传播。

### 边界说明

输入和中间历史仍完整物化，不声明生产有界预算；不接旧reader/decoder。

源码：[`src/chronaxis/core/calculations_memory_reference.py:161`](../../../src/chronaxis/core/calculations_memory_reference.py#L161)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-compute_memory_reference"></a>
## `compute_memory_reference`

从已有内存行执行参考表达式和指标计算，返回完整指标结果。

```python
compute_memory_reference(compiled, spec, *, condition=None, budget=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiled`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|位置或关键字。当前表达式；spec为数值统计或BOOL duration的CalculationDefinition。|
|`spec`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|位置或关键字。spec为数值统计或BOOL duration的CalculationDefinition。     condition: 可选且关联同一真实输入的BOOL表达式。|
|`condition`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression) &#124; None|否|None|仅关键字。可选且关联同一真实输入的BOOL表达式。|
|`budget`|ResourceBudget &#124; None|否|None|仅关键字。可传入本次运行共享的内存账本。精确样本分位数据此为候选样本与排序空间预付费用，普通统计沿用原路径。|

### 返回说明

CalculationResult，保存面积、时间/样本统计或TRUE时长，以及覆盖、未知范围与来源。

### 异常说明

输入、绑定或配置检查失败时传播底层异常；数值失败由指标质量明确报告。

### 流程说明

先建立CalculationSeries，再独立执行参考指标计算；不修改原行或调用数组后端。

源码：[`src/chronaxis/core/calculations_memory_reference.py:174`](../../../src/chronaxis/core/calculations_memory_reference.py#L174)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
