# chronaxis.core.temporal_memory_reference

从已绑定的内存信号计算条件时间轴，再用参考检测器找出活动和点事件。

输入为编译后的布尔表达式和当前会话规则；输出ConditionTimeline或Event tuple。
先归一化原行，再用独立标量保持和表达式计算连续状态、当前点及更新前点。
这三个视图在同一时间检查有效期，用来区分真实更新导致未知与旧值到期。
最后插入域内持续阈值到期时刻，重新求值后交给检测器，避免确认时间落到
下一报文。本模块不读取报文或DBC，不修改输入，不持有全局状态；完整内存
原型会保存历史和时间轴，不能据此认定生产资源预算已经满足。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)、[ConditionTick](chronaxis.core.temporal.md#api-ConditionTick)、[ConditionTimeline](chronaxis.core.temporal.md#api-ConditionTimeline)、[D](chronaxis.core.types.md#api-SignalDType)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)、[SignalBindings](chronaxis.core.binding.md#api-SignalBindings)、[TemporalRule](chronaxis.core.temporal.md#api-TemporalRule)、[Truth](chronaxis.core.types.md#api-Truth)

## 对象导航

|对象|用途|
|---|---|
|[`require_memory_rule`](#api-require_memory_rule)|验证当前布尔计划与规则会话归属，不计算条件。|
|[`_evidence`](#api-_evidence)|独立参考计算连续、真实点和更新前点的完整证据。|
|[`build_timeline_reference`](#api-build_timeline_reference)|汇集信号更新、有效期和观测边界，并插入域内持续阈值时刻。|
|[`detect_memory_reference`](#api-detect_memory_reference)|从原内存信号到完整活动/点事件执行参考链。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .expression import CompiledExpression
from .binding import SignalBindings
from .expression_reference import evaluate_reference
from .numeric import ScalarValue, memory_series_reference
from .state import align_reference, common_timeline
from .temporal import ConditionTick, ConditionTimeline, TemporalRule
from .temporal_reference import detect_reference
from .types import SignalDType as D, QualityFlag as Q, Truth
```

</details>

<a id="api-require_memory_rule"></a>
## `require_memory_rule`

验证当前布尔计划与规则会话归属，不计算条件。

```python
require_memory_rule(compiled, rule)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiled`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)|是|无|位置或关键字。本次绑定下编译完成的表达式，保留类型、单位和依赖信号。|
|`rule`|[TemporalRule](chronaxis.core.temporal.md#api-TemporalRule)|是|无|位置或关键字。当前时序规则，指定持续条件、边沿或start_only的检测要求。|

### 返回说明

None，纯常量也使用计划明示的会话域。

### 异常说明

TypeError/ValueError为类型、非BOOL根或会话冲突。

本函数直接报告的具体错误：

- `TypeError`：memory时序需CompiledExpression及TemporalRule。
- `TypeError`：memory时序需要真实内存SignalBindings，不能使用解码历史绑定。
- `ValueError`：时序条件需BOOL且规则与绑定session一致。

源码：[`src/chronaxis/core/temporal_memory_reference.py:29`](../../../src/chronaxis/core/temporal_memory_reference.py#L29)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_evidence"></a>
## `_evidence`

独立参考计算连续、真实点和更新前点的完整证据。

```python
_evidence(compiled, histories, times)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiled`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)|是|无|位置或关键字。compiled当前计划|
|`histories`|SignalSeries|是|无|位置或关键字。histories当前归一化SignalSeries字典|
|`times`|tuple[int, ...]|是|无|位置或关键字。需要判断条件的整数纳秒时间元组，来自本次时间线。|

### 返回说明

ConditionTick tuple，实际因果、EOF及诊断保留。

### 异常说明

模型/保持/表达式校验错误传播，不吞UNKNOWN原因。

源码：[`src/chronaxis/core/temporal_memory_reference.py:48`](../../../src/chronaxis/core/temporal_memory_reference.py#L48)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-build_timeline_reference"></a>
## `build_timeline_reference`

汇集信号更新、有效期和观测边界，并插入域内持续阈值时刻。

```python
build_timeline_reference(compiled, rule)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiled`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)|是|无|位置或关键字。当前会话的已绑定布尔表达式。|
|`rule`|[TemporalRule](chronaxis.core.temporal.md#api-TemporalRule)|是|无|位置或关键字。同一会话的检测规则；所有时间使用整数纳秒。|

### 返回说明

ConditionTimeline: 完整条件证据，包括没有新样本的精确阈值时刻。

### 异常说明

TypeError、ValueError或OverflowError: 计划、同步、输入或时间协议检查失败。

### 副作用说明

分配本次依赖历史和完整时间轴，不重排原行，不读取或解码旧来源。

源码：[`src/chronaxis/core/temporal_memory_reference.py:96`](../../../src/chronaxis/core/temporal_memory_reference.py#L96)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-detect_memory_reference"></a>
## `detect_memory_reference`

从原内存信号到完整活动/点事件执行参考链。

```python
detect_memory_reference(compiled, rule, *, batch_rows=65536)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiled`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)|是|无|位置或关键字。本次绑定下编译完成的表达式，保留类型、单位和依赖信号。|
|`rule`|[TemporalRule](chronaxis.core.temporal.md#api-TemporalRule)|是|无|位置或关键字。当前时序规则，指定持续条件、边沿或start_only的检测要求。|
|`batch_rows`|int|否|65536|仅关键字。batch_rows为正原生int的完整组批大小。|

### 返回说明

Event tuple，来源/质量/稳定ID均来自当前任务。

### 异常说明

时间/计划/批大小错误传播，内部候选不作为最终输出。

源码：[`src/chronaxis/core/temporal_memory_reference.py:151`](../../../src/chronaxis/core/temporal_memory_reference.py#L151)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
