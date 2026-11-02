# chronaxis.core.calculations_memory_numpy

把已有内存行的表达式与三值条件接入NumPy指标计算。

输入为当前表达式、CalculationDefinition和可选BOOL条件，输出CalculationSeries
或CalculationResult。先按依赖列独立归一化，用searchsorted定位最近观测并按
有效期保持，再批量求值、计算零阶保持面积或真实样本统计。
时间统计和BOOL duration接同一独立数组链；select保留枚举标签及UNKNOWN诊断，
返回SelectionRow迭代器，完整输入和中间列仍占用内存。

共同时间轴为int64纳秒列，形状(N,)；数值、条件、质量与真实更新标志
均与之等长。窗口和有效期边界不能伪造样本，条件单独更新也不计数值样本。
打包ScalarValue只是恢复结果模型，实际数值由数组计算承担，不调用参考内核。

依赖NumPy及数组转换、对齐、表达式和指标模块；只共享静态计划检查。
不修改原输入，也不调用旧读取、解码或写出链。此入口保存完整内存历史
及中间列，不承诺生产内存或磁盘预算，性能效果需要另行测量。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CalculationSeries](chronaxis.core.calculations.md#api-CalculationSeries)、[Interval](chronaxis.core.models.md#api-Interval)、[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)

## 对象导航

|对象|用途|
|---|---|
|[`build_calculation_series_numpy`](#api-build_calculation_series_numpy)|把原行对齐到共同时间轴，批量求值并标记真实数值更新。|
|[`select_memory_numpy`](#api-select_memory_numpy)|用独立数组原行、保持和表达式链返回选择行迭代器。|
|[`compute_memory_numpy`](#api-compute_memory_numpy)|从已有内存行执行数组表达式及指标计算，返回可追溯结果。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .expression_numpy import evaluate_numpy
from .calculations import CalculationSeries
from .calculations_numpy import compute_numpy, select_numpy
from .calculations_memory_reference import require_calculation_plan
from .models import Interval
from .normalize_numpy import memory_series_numpy
from .numeric import ScalarValue
from .numeric_numpy import NumericArray
from .state import common_timeline
from .state_numpy import align_numpy, build_signal_array
from .types import QualityFlag as Q
```

</details>

<a id="api-build_calculation_series_numpy"></a>
## `build_calculation_series_numpy`

把原行对齐到共同时间轴，批量求值并标记真实数值更新。

```python
build_calculation_series_numpy(compiled, spec, *, condition=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiled`|CompiledExpression|是|无|位置或关键字。当前已校验表达式，类型与spec算子匹配；spec为明确窗口与指标请求。|
|`spec`|CalculationDefinition|是|无|位置或关键字。compiled: 当前已校验表达式，类型与spec算子匹配；spec为明确窗口与指标请求。     condition: 可选同绑定身份的BOOL表达式，省略表示不按条件筛选。|
|`condition`|CompiledExpression &#124; None|否|None|仅关键字。可选同绑定身份的BOOL表达式，省略表示不按条件筛选。|

### 返回说明

CalculationSeries。所有列使用形状(N,)的共同纳秒轴，真实更新标志只来自
    数值依赖。恢复ScalarValue的逐位置循环只打包类型和质量，不执行数值运算。

### 异常说明

绑定、时间、类型、形状或同步检查失败时传播底层异常。

### 流程说明

独立归一化各依赖列，加入域内窗口边界，对齐后整列计算数值与条件。
    输出模型复制并冻结本次结果，保留完整历史，不广播或额外读取旧链。

源码：[`src/chronaxis/core/calculations_memory_numpy.py:44`](../../../src/chronaxis/core/calculations_memory_numpy.py#L44)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-select_memory_numpy"></a>
## `select_memory_numpy`

用独立数组原行、保持和表达式链返回选择行迭代器。

```python
select_memory_numpy(compiled, spec, *, condition=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiled`|CompiledExpression|是|无|位置或关键字。compiled当前表达式|
|`spec`|CalculationDefinition|是|无|位置或关键字。spec为select|
|`condition`|CompiledExpression &#124; None|否|None|仅关键字。condition可选同绑定BOOL表达式。|

### 返回说明

SelectionRow迭代器；值、标签与未知诊断完整保留。

### 异常说明

输入、绑定或表达式错误传播；筛选配置错误在消费时传播。

### 边界说明

完整输入/中间数组占用内存，输出不攒列表，不改旧I/O或原输入。

源码：[`src/chronaxis/core/calculations_memory_numpy.py:106`](../../../src/chronaxis/core/calculations_memory_numpy.py#L106)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-compute_memory_numpy"></a>
## `compute_memory_numpy`

从已有内存行执行数组表达式及指标计算，返回可追溯结果。

```python
compute_memory_numpy(compiled, spec, *, condition=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiled`|CalculationDefinition|是|无|位置或关键字。当前表达式；spec为数值统计或BOOL duration的CalculationDefinition。|
|`spec`|CalculationDefinition|是|无|位置或关键字。spec为数值统计或BOOL duration的CalculationDefinition。     condition: 可选同绑定身份的BOOL表达式。|
|`condition`|CompiledExpression &#124; None|否|None|仅关键字。可选同绑定身份的BOOL表达式。|

### 返回说明

CalculationResult，保存面积、时间/样本统计或TRUE时长，以及覆盖、未知范围与来源。

### 异常说明

配置、输入或数值模型不满足要求时传播底层异常，不静默删数据或补零。

### 流程说明

先用数组转换、对齐和表达式生成CalculationSeries，再调用独立数组指标内核。
    只创建本次结果，不修改原行，也不调用参考数值计算。

源码：[`src/chronaxis/core/calculations_memory_numpy.py:119`](../../../src/chronaxis/core/calculations_memory_numpy.py#L119)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
