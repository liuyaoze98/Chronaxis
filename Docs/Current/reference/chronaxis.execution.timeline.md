# `chronaxis.execution.timeline`

逐个准确边界驱动一个真实条件规则，不建立全量分析轴。

调用方保留真实下一完整组直到consumed_group=True，域前完整组由调用方先提交作种子。
本游标直接处理domain.start，随后选择TTL、当前duration deadline、更新和来源/会话末。
每步prepare旧点→可选一次完整组提交→complete三视图→独立预算Detector，终点正式finish。
输出TimelineStep拥有条件结果和事件批，须close；固定与步workspace先申请，输出不复制
事件/位置，不保留完整组。旧已交付步在后续失败后仍可读，失败游标禁止继续。
只驱动单规则；多规则共用提交、窗口/指标和公共AnalysisRunner另接，不改旧I/O或业务算法。
使用同一单线程账本，保证新层保守计账，不代表整进程RSS或外部另存引用被强制回收。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisError](chronaxis.results.errors.md#api-AnalysisError)、[BoundaryQueries](chronaxis.execution.boundaries.md#api-BoundaryQueries)、[BudgetedTemporalDetector](chronaxis.execution.temporal_buffer.md#api-BudgetedTemporalDetector)、[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)、[ConditionEvidenceQueries](chronaxis.execution.condition_evidence.md#api-ConditionEvidenceQueries)、[DecodedTimeGroup](chronaxis.execution.groups.md#api-DecodedTimeGroup)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[RuleDeadline](chronaxis.execution.boundaries.md#api-RuleDeadline)、[SignalDType](chronaxis.core.types.md#api-SignalDType)、[SourceRef](chronaxis.core.models.md#api-SourceRef)、[TemporalRule](chronaxis.core.temporal.md#api-TemporalRule)、[_BatchRegistry](chronaxis.execution.temporal_buffer.md#api-_BatchRegistry)

## 对象导航

|对象|用途|
|---|---|
|[`_require_timeline_input`](#api-_require_timeline_input)|共用单/多规则的已有起点与实际会话校验，不推进或分配分析数组。|
|[`TimelineStep`](#api-TimelineStep)|拥有一个时刻的条件证据和本次增量事件，三个申请各自唯一释放。|
|[`TimelineStep.__init__`](#api-TimelineStep-__init__)|接收已计账子结果，不安装登记。|
|[`TimelineStep._ensure_open`](#api-TimelineStep-_ensure_open)|拒绝释放后读取。|
|[`TimelineStep.closed`](#api-TimelineStep-closed)|读取资源状态。|
|[`TimelineStep.time_ns`](#api-TimelineStep-time_ns)|读取准确时刻。|
|[`TimelineStep.consumed_group`](#api-TimelineStep-consumed_group)|查看本步骤是否已经处理了预先读取的下一组更新。|
|[`TimelineStep.tick`](#api-TimelineStep-tick)|借读自有一点证据。|
|[`TimelineStep.source_refs`](#api-TimelineStep-source_refs)|借读当前点完整位置。|
|[`TimelineStep.events`](#api-TimelineStep-events)|借读本次增量输出。|
|[`TimelineStep._discard`](#api-TimelineStep-_discard)|无扣账地解除登记与关闭引用。|
|[`TimelineStep.close`](#api-TimelineStep-close)|依次关闭两子结果与workspace，未扣账可重试。|
|[`TemporalTimeline`](#api-TemporalTimeline)|借用单条件查询/边界并拥有一个新检测器的严格递增游标。|
|[`TemporalTimeline.__init__`](#api-TemporalTimeline-__init__)|校验共享真实上游与单规则后创建预算检测器。|
|[`TemporalTimeline.closed`](#api-TemporalTimeline-closed)|读取关闭状态。|
|[`TemporalTimeline.failed`](#api-TemporalTimeline-failed)|读取不可重试状态。|
|[`TemporalTimeline.cursor_ns`](#api-TemporalTimeline-cursor_ns)|读取已处理游标。|
|[`TemporalTimeline._ensure_active`](#api-TemporalTimeline-_ensure_active)|核对自身/上游可用。|
|[`TemporalTimeline._construct`](#api-TemporalTimeline-_construct)|仅构造局部步。|
|[`TemporalTimeline.step`](#api-TemporalTimeline-step)|推进一个准确时刻，只有consumed_group为True时调用方才取下一完整组。|
|[`TemporalTimeline.close`](#api-TemporalTimeline-close)|关闭所有自有步、检测器与固定空间，保留借用查询/状态/历史。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..core.expression import CompiledExpression
from ..core.models import SourceRef
from ..core.temporal import TemporalRule
from ..core.types import SignalDType
from ..results.errors import AnalysisError, ResultClosedError
from .boundaries import BoundaryQueries, RuleDeadline, _require_native_ns
from .condition_evidence import ConditionEvidenceQueries
from .groups import DecodedTimeGroup
from .temporal_buffer import BudgetedTemporalDetector, _BatchRegistry
```

</details>

<a id="api-_require_timeline_input"></a>
## `_require_timeline_input`

共用单/多规则的已有起点与实际会话校验，不推进或分配分析数组。

```python
_require_timeline_input(evidence, boundaries, compiled, rule, source_refs)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`evidence`|[ConditionEvidenceQueries](chronaxis.execution.condition_evidence.md#api-ConditionEvidenceQueries)|是|无|位置或关键字。同次ConditionEvidenceQueries，提供已登记布尔表达式在实际时间边界的条件证据。|
|`boundaries`|[BoundaryQueries](chronaxis.execution.boundaries.md#api-BoundaryQueries)|是|无|位置或关键字。真实共享的边界查询对象，提供TTL/结束等下一边界。|
|`compiled`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)|是|无|位置或关键字。本次已检查/编译的表达式对象，包含树、单位、类型和依赖。|
|`rule`|[TemporalRule](chronaxis.core.temporal.md#api-TemporalRule)|是|无|位置或关键字。已冻结的当前时序规则，不在此修改条件或门槛。|
|`source_refs`|tuple|是|无|位置或关键字。参与本次计算的来源定位元组，保留实际会话、来源和原字段。|

### 返回说明

原表达式整数登记槽；不持有编译树。

### 异常说明

类型/上游/会话/已处理起点错误，保留全部caller状态。

本函数直接报告的具体错误：

- `TypeError`：时间游标需要真实条件与边界查询。
- `ValueError`：时间游标两查询必须借用同一真实表达式owner。
- `ValueError`：时间游标两查询必须使用同一实际观测范围。
- `TypeError`：时间游标需要已登记BOOL条件。
- `ValueError`：时间游标条件未登记。
- `TypeError`：时间游标需要冻结规则和SourceRef tuple。
- `ValueError`：时间游标规则/来源会话与实际绑定不一致。
- `ValueError`：时间游标必须从未处理的起点开始，种子仅接受域前完整组。

源码：[`src/chronaxis/execution/timeline.py:24`](../../../src/chronaxis/execution/timeline.py#L24)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TimelineStep"></a>
## `TimelineStep`

拥有一个时刻的条件证据和本次增量事件，三个申请各自唯一释放。

条件和事件不复制，workspace覆盖本对象/链字段；关闭子结果后释放workspace。
私有链仅登记本owner，后续失败不撤销先前已交付对象。

```python
TimelineStep(owner, cost, time_ns, consumed, condition, events)
```


源码：[`src/chronaxis/execution/timeline.py:59`](../../../src/chronaxis/execution/timeline.py#L59)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TimelineStep-__init__"></a>
### `TimelineStep.__init__`

接收已计账子结果，不安装登记。

```python
TimelineStep.__init__(owner, cost, time_ns, consumed, condition, events)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|[TemporalTimeline](chronaxis.execution.timeline.md#api-TemporalTimeline)|是|无|位置或关键字。创建本时间步的游标，负责登记该步并在关闭后释放其资源。|
|`cost`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|
|`time_ns`|int|是|无|位置或关键字。当前处理时刻，以整数纳秒表示，须在int64范围内。例如1秒写1_000_000_000；不是浮点秒。|
|`consumed`|bool|是|无|位置或关键字。True表示本步已消费调用方传入的整组同一时刻更新；False表示本步处理的是中间边界，下一步仍须保留该更新组。|
|`condition`|PreparedConditionEvidence|是|无|位置或关键字。本步已经完成的条件证据，随时间步一并关闭。|
|`events`|TemporalEventBatch|是|无|位置或关键字。本步检测得到的事件批次，随时间步一并关闭。|

#### 返回说明

尚未登记的步。

#### 异常说明

构造失败由step外层清理。

源码：[`src/chronaxis/execution/timeline.py:66`](../../../src/chronaxis/execution/timeline.py#L66)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TimelineStep-_ensure_open"></a>
### `TimelineStep._ensure_open`

拒绝释放后读取。

```python
TimelineStep._ensure_open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ResultClosedError。

本函数直接报告的具体错误：

- `ResultClosedError`：时间游标步已关闭。

源码：[`src/chronaxis/execution/timeline.py:77`](../../../src/chronaxis/execution/timeline.py#L77)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TimelineStep-closed"></a>
### `TimelineStep.closed`

读取资源状态。

```python
TimelineStep.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/execution/timeline.py:83`](../../../src/chronaxis/execution/timeline.py#L83)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TimelineStep-time_ns"></a>
### `TimelineStep.time_ns`

读取准确时刻。

```python
TimelineStep.time_ns
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

原生int ns。

#### 异常说明

对象处于下列状态时抛ResultClosedError：时间游标步已关闭。

源码：[`src/chronaxis/execution/timeline.py:88`](../../../src/chronaxis/execution/timeline.py#L88)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TimelineStep-consumed_group"></a>
### `TimelineStep.consumed_group`

查看本步骤是否已经处理了预先读取的下一组更新。

```python
TimelineStep.consumed_group
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本步骤已经处理了预先读到的下一组更新；False表示该组仍需后续处理。

#### 异常说明

对象处于下列状态时抛ResultClosedError：时间游标步已关闭。

源码：[`src/chronaxis/execution/timeline.py:94`](../../../src/chronaxis/execution/timeline.py#L94)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TimelineStep-tick"></a>
### `TimelineStep.tick`

借读自有一点证据。

```python
TimelineStep.tick
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

ConditionTick。

#### 异常说明

对象处于下列状态时抛ResultClosedError：时间游标步已关闭。

源码：[`src/chronaxis/execution/timeline.py:100`](../../../src/chronaxis/execution/timeline.py#L100)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TimelineStep-source_refs"></a>
### `TimelineStep.source_refs`

借读当前点完整位置。

```python
TimelineStep.source_refs
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

SourceRef tuple。

#### 异常说明

对象处于下列状态时抛ResultClosedError：时间游标步已关闭。

源码：[`src/chronaxis/execution/timeline.py:106`](../../../src/chronaxis/execution/timeline.py#L106)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TimelineStep-events"></a>
### `TimelineStep.events`

借读本次增量输出。

```python
TimelineStep.events
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

Event tuple。

#### 异常说明

对象处于下列状态时抛ResultClosedError：时间游标步已关闭。

源码：[`src/chronaxis/execution/timeline.py:112`](../../../src/chronaxis/execution/timeline.py#L112)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TimelineStep-_discard"></a>
### `TimelineStep._discard`

无扣账地解除登记与关闭引用。

```python
TimelineStep._discard()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

脱链取消传播，finally仍关闭，owner可重试移除。

源码：[`src/chronaxis/execution/timeline.py:117`](../../../src/chronaxis/execution/timeline.py#L117)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TimelineStep-close"></a>
### `TimelineStep.close`

依次关闭两子结果与workspace，未扣账可重试。

```python
TimelineStep.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None。关闭成功后再次调用不会重复释放同一份资源。

#### 异常说明

子结果/预算/取消传播，已扣workspace则最小收尾且不会再次扣账。

源码：[`src/chronaxis/execution/timeline.py:128`](../../../src/chronaxis/execution/timeline.py#L128)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TemporalTimeline"></a>
## `TemporalTimeline`

借用单条件查询/边界并拥有一个新检测器的严格递增游标。

起点前可有已提交种子；开始后只能由此游标提交state，revision检测外部错位。
不缓存输入组、全轴或事件全集；每个已交付步独立持有预算到close。

```python
TemporalTimeline(evidence: ConditionEvidenceQueries, boundaries: BoundaryQueries, compiled: CompiledExpression, rule: TemporalRule, *, source_refs: tuple[SourceRef, ...]=())
```


源码：[`src/chronaxis/execution/timeline.py:152`](../../../src/chronaxis/execution/timeline.py#L152)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TemporalTimeline-__init__"></a>
### `TemporalTimeline.__init__`

校验共享真实上游与单规则后创建预算检测器。

```python
TemporalTimeline.__init__(evidence: ConditionEvidenceQueries, boundaries: BoundaryQueries, compiled: CompiledExpression, rule: TemporalRule, *, source_refs: tuple[SourceRef, ...]=())
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`evidence`|[ConditionEvidenceQueries](chronaxis.execution.condition_evidence.md#api-ConditionEvidenceQueries)|是|无|位置或关键字。条件证据查询对象，必须与boundaries使用同一个表达式查询管理器。|
|`boundaries`|[BoundaryQueries](chronaxis.execution.boundaries.md#api-BoundaryQueries)|是|无|位置或关键字。边界查询对象，提供下一更新、过期和范围终点；与evidence共享表达式来源。|
|`compiled`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)|是|无|位置或关键字。compiled已登记BOOL|
|`rule`|[TemporalRule](chronaxis.core.temporal.md#api-TemporalRule)|是|无|位置或关键字。rule创建后不可修改的配置|
|`source_refs`|tuple[[SourceRef](chronaxis.core.models.md#api-SourceRef), ...]|否|()|仅关键字。source_refs调用方提供的固定规则绑定位置，不等于全部事件原始行。|

#### 返回说明

新游标，尚未处理start。

#### 异常说明

类型/登记/会话/已有推进/预算/取消传播并清理自有申请。

源码：[`src/chronaxis/execution/timeline.py:159`](../../../src/chronaxis/execution/timeline.py#L159)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TemporalTimeline-closed"></a>
### `TemporalTimeline.closed`

读取关闭状态。

```python
TemporalTimeline.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/execution/timeline.py:188`](../../../src/chronaxis/execution/timeline.py#L188)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TemporalTimeline-failed"></a>
### `TemporalTimeline.failed`

读取不可重试状态。

```python
TemporalTimeline.failed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象已记录处理失败；False表示尚未记录失败。

#### 异常说明

无。

源码：[`src/chronaxis/execution/timeline.py:193`](../../../src/chronaxis/execution/timeline.py#L193)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TemporalTimeline-cursor_ns"></a>
### `TemporalTimeline.cursor_ns`

读取已处理游标。

```python
TemporalTimeline.cursor_ns
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

int ns或起步前None。

#### 异常说明

ResultClosedError。

本函数直接报告的具体错误：

- `ResultClosedError`：时间游标已关闭。

源码：[`src/chronaxis/execution/timeline.py:198`](../../../src/chronaxis/execution/timeline.py#L198)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TemporalTimeline-_ensure_active"></a>
### `TemporalTimeline._ensure_active`

核对自身/上游可用。

```python
TemporalTimeline._ensure_active()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

关闭或AnalysisError。

本函数直接报告的具体错误：

- `ResultClosedError`：时间游标已关闭。
- `AnalysisError`：时间游标已失败，禁止重试。

源码：[`src/chronaxis/execution/timeline.py:204`](../../../src/chronaxis/execution/timeline.py#L204)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TemporalTimeline-_construct"></a>
### `TemporalTimeline._construct`

仅构造局部步。

```python
TemporalTimeline._construct(cost, time_ns, consumed, condition, events)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`cost`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|
|`time_ns`|int|是|无|位置或关键字。当前处理时刻，以整数纳秒表示，须在int64范围内。例如1秒写1_000_000_000；不是浮点秒。|
|`consumed`|bool|是|无|位置或关键字。True表示本步已消费调用方传入的整组同一时刻更新；False表示本步处理的是中间边界，下一步仍须保留该更新组。|
|`condition`|PreparedConditionEvidence|是|无|位置或关键字。本步条件查询的结果，构造时间步后由该步管理其生命周期。|
|`events`|TemporalEventBatch|是|无|位置或关键字。本步产生的事件结果批次；没有事件时批次内容为空。|

#### 返回说明

TimelineStep。

#### 异常说明

分配/取消。

源码：[`src/chronaxis/execution/timeline.py:213`](../../../src/chronaxis/execution/timeline.py#L213)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TemporalTimeline-step"></a>
### `TemporalTimeline.step`

推进一个准确时刻，只有consumed_group为True时调用方才取下一完整组。

```python
TemporalTimeline.step(next_group: DecodedTimeGroup | None=None) -> TimelineStep | None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`next_group`|[DecodedTimeGroup](chronaxis.execution.groups.md#api-DecodedTimeGroup) &#124; None|否|None|位置或关键字。next_group真实前瞻或明确无后续组的None，域前种子已由调用方提交。|

#### 返回说明

须close的TimelineStep；已处理terminal后为None。

#### 异常说明

入口/外部revision错位前置拒绝；workspace不足未推进可重试；开始后的错误标failed，
    不回滚state/Detector，保留以前输出且清理本次未交付申请。

返回类型：[TimelineStep](chronaxis.execution.timeline.md#api-TimelineStep) &#124; None。

源码：[`src/chronaxis/execution/timeline.py:217`](../../../src/chronaxis/execution/timeline.py#L217)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TemporalTimeline-close"></a>
### `TemporalTimeline.close`

关闭所有自有步、检测器与固定空间，保留借用查询/状态/历史。

```python
TemporalTimeline.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None。关闭成功后再次调用不会重复释放同一份资源。

#### 异常说明

子关闭/预算/取消传播，未完成可重试，固定已释放则最小关闭。

源码：[`src/chronaxis/execution/timeline.py:287`](../../../src/chronaxis/execution/timeline.py#L287)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
