# `chronaxis.core.temporal_memory_numpy`

通过NumPy保持和表达式计算内存信号的条件时间轴，再检测事件。

输入为当前会话已绑定的布尔计划和规则；输出完整条件轴或稳定Event tuple。
归一化、二分时间索引、条件计算及TRUE起点的阈值安排按列执行。连续、
当前点和更新前点三个视图在相同时间检查有效期，区分真实更新与同一时刻到期。
输出装箱循环只恢复ConditionTick模型，数值计算不调用标量参考算法。
本模块依赖NumPy和当前核心模型，不读取旧来源或DBC，不修改输入，也没有
全局绑定。完整内存历史和时间轴需占用内存，不保证生产资源预算。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ConditionTick](chronaxis.core.temporal.md#api-ConditionTick)、[ConditionTimeline](chronaxis.core.temporal.md#api-ConditionTimeline)、[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[Truth](chronaxis.core.types.md#api-Truth)

## 对象导航

|对象|用途|
|---|---|
|[`_evidence_numpy`](#api-_evidence_numpy)|按列计算连续状态、当前点和更新前点，保留实际未知的因果证据。|
|[`build_timeline_numpy`](#api-build_timeline_numpy)|独立数组安排TRUE起点deadline并生成完整实际条件证据。|
|[`detect_memory_numpy`](#api-detect_memory_numpy)|从原内存行通过实际数组保持/表达式/run检测输出事件。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .enum_codes import memory_histories, aligned_column
from .expression_numpy import evaluate_numpy
from .normalize_numpy import memory_series_numpy
from .numeric_numpy import NumericArray
from .state import common_timeline
from .state_numpy import align_numpy, build_signal_array
from .temporal import ConditionTick, ConditionTimeline
from .temporal_memory_reference import require_memory_rule
from .temporal_numpy import detect_numpy
from .types import QualityFlag as Q, Truth
from .where_updates import contains_where, numpy_active, numpy_updates
```

</details>

<a id="api-_evidence_numpy"></a>
## `_evidence_numpy`

按列计算连续状态、当前点和更新前点，保留实际未知的因果证据。

```python
_evidence_numpy(compiled, histories, arrays, times)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiled`|CompiledExpression|是|无|位置或关键字。当前已绑定的布尔表达式。|
|`histories`|dict|是|无|位置或关键字。当前依赖名称到SignalSeries的映射。|
|`arrays`|dict|是|无|位置或关键字。同一依赖名称到SignalArray的映射。|
|`times`|np.ndarray|是|无|位置或关键字。当前完整查询轴，单位为纳秒。|

### 返回说明

tuple[ConditionTick, ...]: 每个查询时刻的完整状态、质量及更新证据。
    状态和原因先按列计算，最后恢复不可变模型。

### 异常说明

TypeError、ValueError或OverflowError: 列类型、形状、计划或数值协议错误。
    MemoryError: 数组分配失败；不丢弃数据继续执行。

源码：[`src/chronaxis/core/temporal_memory_numpy.py:35`](../../../src/chronaxis/core/temporal_memory_numpy.py#L35)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-build_timeline_numpy"></a>
## `build_timeline_numpy`

独立数组安排TRUE起点deadline并生成完整实际条件证据。

```python
build_timeline_numpy(compiled, rule)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiled`|CompiledExpression|是|无|位置或关键字。本次绑定下编译完成的表达式，保留类型、单位和依赖信号。|
|`rule`|TemporalRule|是|无|位置或关键字。当前时序规则，指定持续条件、边沿或start_only的检测要求。|

### 返回说明

ConditionTimeline；计时器没有actual更新，不产生假边沿。

### 异常说明

输入/同步/类型/时间错误传播；超域deadline不会wrap。

源码：[`src/chronaxis/core/temporal_memory_numpy.py:121`](../../../src/chronaxis/core/temporal_memory_numpy.py#L121)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-detect_memory_numpy"></a>
## `detect_memory_numpy`

从原内存行通过实际数组保持/表达式/run检测输出事件。

```python
detect_memory_numpy(compiled, rule, *, batch_rows=65536)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiled`|CompiledExpression|是|无|位置或关键字。本次绑定下编译完成的表达式，保留类型、单位和依赖信号。|
|`rule`|TemporalRule|是|无|位置或关键字。当前时序规则，指定持续条件、边沿或start_only的检测要求。|
|`batch_rows`|int|否|65536|仅关键字。一次处理的完整时间组数量，必须是正整数；同一时间的更新不能拆到两个批次。|

### 返回说明

Event tuple；结果/质量/来源/稳定ID可与独立参考比较。

### 异常说明

当前模型/时间/配置/批大小错误传播，不静默截断。

源码：[`src/chronaxis/core/temporal_memory_numpy.py:170`](../../../src/chronaxis/core/temporal_memory_numpy.py#L170)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
