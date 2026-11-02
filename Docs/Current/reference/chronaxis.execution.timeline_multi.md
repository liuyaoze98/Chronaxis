# chronaxis.execution.timeline_multi

在同一完整组两侧推进一个数据集会话的多条件/多规则。

调用方先保留域前种子与真实下一完整组，最早边界由各条件TTL/来源EOF和对应规则deadline选择。
不同表达式对象槽全部prepare后至多一次state.apply，再全部complete并推进各自独立Detector。
迟滞的进出条件都参加该过程；防抖截止与条件TTL/EOF共同决定下一时刻。
同一编译对象被多个规则引用时只保存一份三视图；不共享数值核或改变原读写/解码调用。
固定配置与步workspace先计规则数预算，子条件/事件批各自保有预算，输出须close。
步骤失败不回滚已提交组或规则，禁止重试但保留原输出，单线程生命周期不承诺RSS。
没有全量轴/历史缓存、窗口指标或公共AnalysisRunner，固定事件绑定refs不等于全部原始行。
构造中的未安装Detector由父_uninstalled_detector持续持有；深子构造尚未返回
也按原异常上的temporal_detector_cleanup_owner接管，持续清理失败再交出真实父
multi_rule_timeline_cleanup_owner。恢复仅关闭自有步/Detector/固定配置，不关闭查询。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisError](chronaxis.results.errors.md#api-AnalysisError)、[BudgetedTemporalDetector](chronaxis.execution.temporal_buffer.md#api-BudgetedTemporalDetector)、[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)、[DecodedTimeGroup](chronaxis.execution.groups.md#api-DecodedTimeGroup)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[RuleDeadline](chronaxis.execution.boundaries.md#api-RuleDeadline)、[SignalDType](chronaxis.core.types.md#api-SignalDType)、[SourceRef](chronaxis.core.models.md#api-SourceRef)、[StabilitySpec](chronaxis.core.stability.md#api-StabilitySpec)、[StartEndSpec](chronaxis.core.start_end.md#api-StartEndSpec)、[TemporalRule](chronaxis.core.temporal.md#api-TemporalRule)、[_BatchRegistry](chronaxis.execution.temporal_buffer.md#api-_BatchRegistry)

## 对象导航

|对象|用途|
|---|---|
|[`TimelineRule`](#api-TimelineRule)|声明一个已编译条件与冻结规则的关联，固定来源位置由caller提供。|
|[`TimelineRule.__post_init__`](#api-TimelineRule-__post_init__)|校验创建后不可修改的输入对象结构，不创建Detector。|
|[`TimelineRule.expressions`](#api-TimelineRule-expressions)|收集进出条件供共享查询。|
|[`TimelineRule.dependencies`](#api-TimelineRule-dependencies)|收集两个条件的实际依赖。|
|[`MultiTimelineStep`](#api-MultiTimelineStep)|拥有全部已计账子结果与少量输出视图，顺序与固定槽/规则顺序对应。|
|[`MultiTimelineStep.__init__`](#api-MultiTimelineStep-__init__)|在已申请workspace中创建输出视图，不安装链。|
|[`MultiTimelineStep._ensure_open`](#api-MultiTimelineStep-_ensure_open)|拒绝释放后读取。|
|[`MultiTimelineStep.closed`](#api-MultiTimelineStep-closed)|读取关闭状态。|
|[`MultiTimelineStep.time_ns`](#api-MultiTimelineStep-time_ns)|读取准确时刻。|
|[`MultiTimelineStep.consumed_group`](#api-MultiTimelineStep-consumed_group)|查看本步骤是否已经处理了预先读取的下一组更新。|
|[`MultiTimelineStep.condition_slots`](#api-MultiTimelineStep-condition_slots)|读取ticks对应表达式登记槽。|
|[`MultiTimelineStep.ticks`](#api-MultiTimelineStep-ticks)|读取各不同条件证据。|
|[`MultiTimelineStep.source_refs`](#api-MultiTimelineStep-source_refs)|读取每条件当前点完整位置。|
|[`MultiTimelineStep.rule_keys`](#api-MultiTimelineStep-rule_keys)|读取事件批对应dataset/session/rule身份。|
|[`MultiTimelineStep.events_by_rule`](#api-MultiTimelineStep-events_by_rule)|读取各规则本次增量事件。|
|[`MultiTimelineStep._discard`](#api-MultiTimelineStep-_discard)|无扣账地脱离并清空自有视图。|
|[`MultiTimelineStep.close`](#api-MultiTimelineStep-close)|释放全部子结果再释放workspace，支持中途关闭取消后重试。|
|[`MultiRuleTimeline`](#api-MultiRuleTimeline)|单数据集会话的多规则同步游标，每真实组只提交一次。|
|[`MultiRuleTimeline.__init__`](#api-MultiRuleTimeline-__init__)|校验规则关联后先预算再建立固定槽和各独立Detector。|
|[`MultiRuleTimeline.closed`](#api-MultiRuleTimeline-closed)|读取关闭状态。|
|[`MultiRuleTimeline.failed`](#api-MultiRuleTimeline-failed)|读取禁止重试状态。|
|[`MultiRuleTimeline.cursor_ns`](#api-MultiRuleTimeline-cursor_ns)|读取已处理游标。|
|[`MultiRuleTimeline._ensure_active`](#api-MultiRuleTimeline-_ensure_active)|核对自身/上游。|
|[`MultiRuleTimeline._construct`](#api-MultiRuleTimeline-_construct)|仅构造局部输出。|
|[`MultiRuleTimeline.step`](#api-MultiRuleTimeline-step)|选择全局一个时刻，全部旧点捕获后只提交一次完整更新。|
|[`MultiRuleTimeline.duration_summaries`](#api-MultiRuleTimeline-duration_summaries)|在关闭前提取已完成规则的小型累计快照。|
|[`MultiRuleTimeline.close`](#api-MultiRuleTimeline-close)|关闭自有步、未安装/已安装Detector及固定配置，保留caller查询/状态/历史。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from ..core.expression import CompiledExpression
from ..core.models import SourceRef
from ..core.temporal import TemporalRule
from ..core.stability import StabilitySpec
from ..core.start_end import StartEndSpec
from ..core.types import SignalDType
from ..results.errors import AnalysisError, ResultClosedError
from ..results.spool import _cleanup_owner
from .boundaries import RuleDeadline, _require_native_ns
from .groups import DecodedTimeGroup
from .history import _metadata_bytes
from .temporal_buffer import BudgetedTemporalDetector, _BatchRegistry
from .timeline import _require_timeline_input
```

</details>

<a id="api-TimelineRule"></a>
## `TimelineRule`

声明一个已编译条件与冻结规则的关联，固定来源位置由caller提供。

不持有运行状态，实际owner/会话/起点由多规则游标校验；多个规则可引用相同compiled对象。

```python
class TimelineRule
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`rule`|[TemporalRule](chronaxis.core.temporal.md#api-TemporalRule)|是|无|当前数据集/会话中的唯一规则ID。|
|`compiled`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)|是|无|同一实际表达式owner登记的BOOL对象。|
|`source_refs`|tuple[[SourceRef](chronaxis.core.models.md#api-SourceRef), ...]|否|()|固定绑定定位，当前点物理行另在步骤返回。|
|`stability`|[StabilitySpec](chronaxis.core.stability.md#api-StabilitySpec) &#124; None|否|None|可选双向防抖；不改变普通条件时间线。|
|`exit_compiled`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression) &#124; None|否|None|迟滞退出或start_end结束BOOL；防抖可省略。|
|`start_end`|[StartEndSpec](chronaxis.core.start_end.md#api-StartEndSpec) &#124; None|否|None|开始/结束专用时限；与迟滞互斥。 None表示不采用start_end检测方式。|

源码：[`src/chronaxis/execution/timeline_multi.py:33`](../../../src/chronaxis/execution/timeline_multi.py#L33)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-TimelineRule-__post_init__"></a>
### `TimelineRule.__post_init__`

校验创建后不可修改的输入对象结构，不创建Detector。

```python
TimelineRule.__post_init__()
```

参数：无显式参数。


#### 参数说明

无，读取规则、进出条件、来源与可选防抖声明。

#### 返回说明

None，保留原对象。

#### 异常说明

TypeError为非规则/BOOL/SourceRef tuple或非法迟滞声明。

本函数直接报告的具体错误：

- `TypeError`：多规则声明需要冻结规则、BOOL编译对象及SourceRef tuple。
- `TypeError`：多规则防抖需要StabilitySpec。
- `TypeError`：start_end需要独立结束条件且不能混用迟滞。
- `TypeError`：独立结束/退出条件需要已编译BOOL和对应状态声明。

源码：[`src/chronaxis/execution/timeline_multi.py:46`](../../../src/chronaxis/execution/timeline_multi.py#L46)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-TimelineRule-expressions"></a>
### `TimelineRule.expressions`

收集进出条件供共享查询。

```python
TimelineRule.expressions
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

编译对象tuple。

#### 异常说明

无。

源码：[`src/chronaxis/execution/timeline_multi.py:67`](../../../src/chronaxis/execution/timeline_multi.py#L67)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-TimelineRule-dependencies"></a>
### `TimelineRule.dependencies`

收集两个条件的实际依赖。

```python
TimelineRule.dependencies
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

名称tuple。

#### 异常说明

无。

源码：[`src/chronaxis/execution/timeline_multi.py:72`](../../../src/chronaxis/execution/timeline_multi.py#L72)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-MultiTimelineStep"></a>
## `MultiTimelineStep`

拥有全部已计账子结果与少量输出视图，顺序与固定槽/规则顺序对应。

ticks按不同条件槽，events_by_rule按规则顺序，缓存仅小带有明确类型的值/事件引用。
refs通过仍打开的自有条件读取，不把大位置元数据复制到未计账缓存。

```python
MultiTimelineStep(owner, cost, time_ns, consumed, conditions, batches)
```


源码：[`src/chronaxis/execution/timeline_multi.py:77`](../../../src/chronaxis/execution/timeline_multi.py#L77)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-MultiTimelineStep-__init__"></a>
### `MultiTimelineStep.__init__`

在已申请workspace中创建输出视图，不安装链。

```python
MultiTimelineStep.__init__(owner, cost, time_ns, consumed, conditions, batches)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|[MultiRuleTimeline](chronaxis.execution.timeline_multi.md#api-MultiRuleTimeline)|是|无|位置或关键字。创建本步的多规则时间游标，用于管理本步占用的资源。|
|`cost`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|
|`time_ns`|int|是|无|位置或关键字。当前处理时刻，以整数纳秒表示，须在int64范围内。例如1秒写1_000_000_000；不是浮点秒。|
|`consumed`|bool|是|无|位置或关键字。True表示本步已消费调用方传入的整组同一时刻更新；False表示本步处理的是中间边界，下一步仍须保留该更新组。|
|`conditions`|list[PreparedConditionEvidence]|是|无|位置或关键字。各规则在本步的条件证据，保持规则顺序；关闭本步时逐个关闭。|
|`batches`|list[TemporalEventBatch]|是|无|位置或关键字。各规则在本步产生的事件批次，保持规则顺序；关闭本步时逐个关闭。|

#### 返回说明

None；初始化实例状态；子句柄移交到此对象。

#### 异常说明

构造错误由外层关闭局部句柄。

源码：[`src/chronaxis/execution/timeline_multi.py:84`](../../../src/chronaxis/execution/timeline_multi.py#L84)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-MultiTimelineStep-_ensure_open"></a>
### `MultiTimelineStep._ensure_open`

拒绝释放后读取。

```python
MultiTimelineStep._ensure_open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ResultClosedError。

本函数直接报告的具体错误：

- `ResultClosedError`：多规则时间步已关闭。

源码：[`src/chronaxis/execution/timeline_multi.py:98`](../../../src/chronaxis/execution/timeline_multi.py#L98)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-MultiTimelineStep-closed"></a>
### `MultiTimelineStep.closed`

读取关闭状态。

```python
MultiTimelineStep.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/execution/timeline_multi.py:104`](../../../src/chronaxis/execution/timeline_multi.py#L104)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-MultiTimelineStep-time_ns"></a>
### `MultiTimelineStep.time_ns`

读取准确时刻。

```python
MultiTimelineStep.time_ns
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

int ns。

#### 异常说明

对象处于下列状态时抛ResultClosedError：多规则时间步已关闭。

源码：[`src/chronaxis/execution/timeline_multi.py:109`](../../../src/chronaxis/execution/timeline_multi.py#L109)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-MultiTimelineStep-consumed_group"></a>
### `MultiTimelineStep.consumed_group`

查看本步骤是否已经处理了预先读取的下一组更新。

```python
MultiTimelineStep.consumed_group
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本步骤已经处理了预先读到的下一组更新；False表示该组仍需后续处理。

#### 异常说明

对象处于下列状态时抛ResultClosedError：多规则时间步已关闭。

源码：[`src/chronaxis/execution/timeline_multi.py:115`](../../../src/chronaxis/execution/timeline_multi.py#L115)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-MultiTimelineStep-condition_slots"></a>
### `MultiTimelineStep.condition_slots`

读取ticks对应表达式登记槽。

```python
MultiTimelineStep.condition_slots
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

int tuple。

#### 异常说明

对象处于下列状态时抛ResultClosedError：多规则时间步已关闭。

源码：[`src/chronaxis/execution/timeline_multi.py:121`](../../../src/chronaxis/execution/timeline_multi.py#L121)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-MultiTimelineStep-ticks"></a>
### `MultiTimelineStep.ticks`

读取各不同条件证据。

```python
MultiTimelineStep.ticks
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

ConditionTick tuple。

#### 异常说明

对象处于下列状态时抛ResultClosedError：多规则时间步已关闭。

源码：[`src/chronaxis/execution/timeline_multi.py:127`](../../../src/chronaxis/execution/timeline_multi.py#L127)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-MultiTimelineStep-source_refs"></a>
### `MultiTimelineStep.source_refs`

读取每条件当前点完整位置。

```python
MultiTimelineStep.source_refs
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

嵌套SourceRef tuple。

#### 异常说明

关闭。

源码：[`src/chronaxis/execution/timeline_multi.py:133`](../../../src/chronaxis/execution/timeline_multi.py#L133)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-MultiTimelineStep-rule_keys"></a>
### `MultiTimelineStep.rule_keys`

读取事件批对应dataset/session/rule身份。

```python
MultiTimelineStep.rule_keys
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

三元tuple的tuple。

#### 异常说明

关闭。

源码：[`src/chronaxis/execution/timeline_multi.py:139`](../../../src/chronaxis/execution/timeline_multi.py#L139)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-MultiTimelineStep-events_by_rule"></a>
### `MultiTimelineStep.events_by_rule`

读取各规则本次增量事件。

```python
MultiTimelineStep.events_by_rule
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

Event tuple的tuple。

#### 异常说明

关闭。

源码：[`src/chronaxis/execution/timeline_multi.py:145`](../../../src/chronaxis/execution/timeline_multi.py#L145)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-MultiTimelineStep-_discard"></a>
### `MultiTimelineStep._discard`

无扣账地脱离并清空自有视图。

```python
MultiTimelineStep._discard()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

脱链取消传播，finally仍关闭；owner随后只清理残留链。

源码：[`src/chronaxis/execution/timeline_multi.py:150`](../../../src/chronaxis/execution/timeline_multi.py#L150)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-MultiTimelineStep-close"></a>
### `MultiTimelineStep.close`

释放全部子结果再释放workspace，支持中途关闭取消后重试。

```python
MultiTimelineStep.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None。关闭成功后再次调用不会重复释放同一份资源。

#### 异常说明

子结果/预算/取消传播，已扣workspace最小关闭。

源码：[`src/chronaxis/execution/timeline_multi.py:162`](../../../src/chronaxis/execution/timeline_multi.py#L162)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-MultiRuleTimeline"></a>
## `MultiRuleTimeline`

单数据集会话的多规则同步游标，每真实组只提交一次。

只保存固定槽/规则顺序、当前游标和独立检测器；不同条件在同一组前全部捕获旧点。
不保存编译树或原组，既有表达式owner拥有树；关闭自有资源不关闭借用查询。
_uninstalled_detector负责尚未装入_detectors的真实子实例，安装成功才清空；
构造清理持续失败的父实例从原异常multi_rule_timeline_cleanup_owner恢复close。

```python
MultiRuleTimeline(evidence, boundaries, rules: tuple[TimelineRule, ...])
```


源码：[`src/chronaxis/execution/timeline_multi.py:185`](../../../src/chronaxis/execution/timeline_multi.py#L185)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-MultiRuleTimeline-__init__"></a>
### `MultiRuleTimeline.__init__`

校验规则关联后先预算再建立固定槽和各独立Detector。

```python
MultiRuleTimeline.__init__(evidence, boundaries, rules: tuple[TimelineRule, ...])
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`evidence`|bool|是|无|位置或关键字。同次ConditionEvidenceQueries，提供已登记布尔表达式在实际时间边界的条件证据。|
|`boundaries`|BoundaryQueries|是|无|位置或关键字。真实共享的边界查询对象，提供TTL/结束等下一边界。|
|`rules`|tuple[[TimelineRule](chronaxis.execution.timeline_multi.md#api-TimelineRule), ...]|是|无|位置或关键字。两真实共享查询、同一dataset/session且rule_id唯一的非空冻结rules。|

#### 返回说明

新游标，尚未处理起点。

#### 异常说明

配置/已有起点/预算/取消原错误传播；
    部分构造接管未返回Detector，持续清理失败从multi_rule_timeline_cleanup_owner恢复。

源码：[`src/chronaxis/execution/timeline_multi.py:194`](../../../src/chronaxis/execution/timeline_multi.py#L194)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-MultiRuleTimeline-closed"></a>
### `MultiRuleTimeline.closed`

读取关闭状态。

```python
MultiRuleTimeline.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/execution/timeline_multi.py:250`](../../../src/chronaxis/execution/timeline_multi.py#L250)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-MultiRuleTimeline-failed"></a>
### `MultiRuleTimeline.failed`

读取禁止重试状态。

```python
MultiRuleTimeline.failed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象已记录处理失败；False表示尚未记录失败。

#### 异常说明

无。

源码：[`src/chronaxis/execution/timeline_multi.py:255`](../../../src/chronaxis/execution/timeline_multi.py#L255)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-MultiRuleTimeline-cursor_ns"></a>
### `MultiRuleTimeline.cursor_ns`

读取已处理游标。

```python
MultiRuleTimeline.cursor_ns
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

int ns或None。

#### 异常说明

ResultClosedError。

本函数直接报告的具体错误：

- `ResultClosedError`：多规则游标已关闭。

源码：[`src/chronaxis/execution/timeline_multi.py:260`](../../../src/chronaxis/execution/timeline_multi.py#L260)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-MultiRuleTimeline-_ensure_active"></a>
### `MultiRuleTimeline._ensure_active`

核对自身/上游。

```python
MultiRuleTimeline._ensure_active()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

关闭/AnalysisError。

本函数直接报告的具体错误：

- `ResultClosedError`：多规则游标已关闭。
- `AnalysisError`：多规则游标已失败，禁止重试。

源码：[`src/chronaxis/execution/timeline_multi.py:266`](../../../src/chronaxis/execution/timeline_multi.py#L266)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-MultiRuleTimeline-_construct"></a>
### `MultiRuleTimeline._construct`

仅构造局部输出。

```python
MultiRuleTimeline._construct(cost, time_ns, consumed, conditions, batches)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`cost`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|
|`time_ns`|int|是|无|位置或关键字。当前处理时刻，以整数纳秒表示，须在int64范围内。例如1秒写1_000_000_000；不是浮点秒。|
|`consumed`|bool|是|无|位置或关键字。True表示本步已消费调用方传入的整组同一时刻更新；False表示本步处理的是中间边界，下一步仍须保留该更新组。|
|`conditions`|list[PreparedConditionEvidence]|是|无|位置或关键字。本步各规则的条件查询结果，交由新时间步统一管理。|
|`batches`|list[TemporalEventBatch]|是|无|位置或关键字。本步各规则的事件批次，交由新时间步统一管理。|

#### 返回说明

MultiTimelineStep。

#### 异常说明

分配/取消。

源码：[`src/chronaxis/execution/timeline_multi.py:275`](../../../src/chronaxis/execution/timeline_multi.py#L275)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-MultiRuleTimeline-step"></a>
### `MultiRuleTimeline.step`

选择全局一个时刻，全部旧点捕获后只提交一次完整更新。

```python
MultiRuleTimeline.step(next_group: DecodedTimeGroup | None=None) -> MultiTimelineStep | None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`next_group`|[DecodedTimeGroup](chronaxis.execution.groups.md#api-DecodedTimeGroup) &#124; None|否|None|位置或关键字。调用者保留的下一完整同时刻更新组；没有后续组时为None。|

#### 返回说明

须close的步，真正terminal处理后None。

#### 异常说明

入口/版本错误前置拒绝，首workspace申请失败可重试；开始后失败禁止重试，
    不回滚已提交state或已推进规则，原输出继续可读，本次子句柄仍有清理归属。

返回类型：[MultiTimelineStep](chronaxis.execution.timeline_multi.md#api-MultiTimelineStep) &#124; None。

源码：[`src/chronaxis/execution/timeline_multi.py:279`](../../../src/chronaxis/execution/timeline_multi.py#L279)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-MultiRuleTimeline-duration_summaries"></a>
### `MultiRuleTimeline.duration_summaries`

在关闭前提取已完成规则的小型累计快照。

```python
MultiRuleTimeline.duration_summaries
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

(rule_id,start_ns,end_ns,active_ns,known_ns)的tuple。

#### 异常说明

关闭/失败/未完成的原检测器错误；不保存全部事件或输入点。

本函数直接报告的具体错误：

- `ResultClosedError`：失败或关闭的时间线不能读取累计。

源码：[`src/chronaxis/execution/timeline_multi.py:368`](../../../src/chronaxis/execution/timeline_multi.py#L368)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-MultiRuleTimeline-close"></a>
### `MultiRuleTimeline.close`

关闭自有步、未安装/已安装Detector及固定配置，保留caller查询/状态/历史。

```python
MultiRuleTimeline.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None。关闭成功后再次调用不会重复释放同一份资源。

#### 异常说明

子结果/预算/取消传播；子句柄成功close才清字段，未释放可重试。
    固定已释放时最小关闭，不对借用查询或上游state调用close。

源码：[`src/chronaxis/execution/timeline_multi.py:383`](../../../src/chronaxis/execution/timeline_multi.py#L383)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
