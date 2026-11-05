# `chronaxis.execution.temporal_buffer`

在运行时序规则前，先为本次输入和可能产生的事件申请内存。输入是一组完整的ConditionTick，以及规则、会话范围和来源引用；可选配置包括持续稳定要求和迟滞退出条件。返回TemporalEventBatch，使用完后须调用close。

内存申请覆盖本批次的时刻、条件数组、质量标记和事件数量上限。返回的批次只保存实际事件，但在close前保留整批申请量；已返回的各批次可分别关闭。

如果内存申请失败而规则尚未运行，规则状态不变，可以重试。如果规则开始处理后发生错误或取消，本对象会标为失败，不能继续推进；此前成功返回的批次仍有效。这种失败不表示已把规则状态恢复到调用前。

本模块不读取数据源，也不计算条件表达式。关闭失败时，异常中的temporal_detector_cleanup_owner保留待清理对象，供调用方继续关闭；不会关闭传入的共享资源管理器。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisError](chronaxis.results.errors.md#api-AnalysisError)、[ConditionTick](chronaxis.core.temporal.md#api-ConditionTick)、[NumpyTemporalDetector](chronaxis.core.temporal_numpy.md#api-NumpyTemporalDetector)、[ReferenceTemporalDetector](chronaxis.core.temporal_reference.md#api-ReferenceTemporalDetector)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[SourceRef](chronaxis.core.models.md#api-SourceRef)、[StabilityDetector](chronaxis.core.stability.md#api-StabilityDetector)、[StabilitySpec](chronaxis.core.stability.md#api-StabilitySpec)、[StartEndDetector](chronaxis.core.start_end.md#api-StartEndDetector)、[StartEndSpec](chronaxis.core.start_end.md#api-StartEndSpec)、[TemporalRule](chronaxis.core.temporal.md#api-TemporalRule)

## 对象导航

|对象|用途|
|---|---|
|[`_BatchRegistry`](#api-_BatchRegistry)|用已有批对象的双向指针登记活动结果，新增/移除不分配容器容量。|
|[`_BatchRegistry.__init__`](#api-_BatchRegistry-__init__)|建立固定大小登记器。|
|[`_BatchRegistry.__bool__`](#api-_BatchRegistry-__bool__)|检查是否有活动批。|
|[`_BatchRegistry.__len__`](#api-_BatchRegistry-__len__)|读取活动批数量。|
|[`_BatchRegistry.__iter__`](#api-_BatchRegistry-__iter__)|遍历当前活动批。|
|[`_BatchRegistry.add`](#api-_BatchRegistry-add)|把新批安装到首端，不分配额外节点。|
|[`_BatchRegistry.discard`](#api-_BatchRegistry-discard)|移除一个完整或部分安装的批，保留其他活动批。|
|[`TemporalEventBatch`](#api-TemporalEventBatch)|持有本批最终事件及独立申请，owner失败后仍可读至本批或owner关闭。|
|[`TemporalEventBatch.__init__`](#api-TemporalEventBatch-__init__)|在完整预留中转交事件，不复制来源元数据或保留输入ticks。|
|[`TemporalEventBatch.closed`](#api-TemporalEventBatch-closed)|读取批关闭状态。|
|[`TemporalEventBatch.events`](#api-TemporalEventBatch-events)|读取只读最终事件。|
|[`TemporalEventBatch.close`](#api-TemporalEventBatch-close)|抵销一次完整本批申请，不修改其它批或检测业务状态。|
|[`BudgetedTemporalDetector`](#api-BudgetedTemporalDetector)|维护一个私有core、固定申请及活动事件批，预算外不累计旧events。|
|[`BudgetedTemporalDetector.__init__`](#api-BudgetedTemporalDetector-__init__)|先申请完整规则/来源固定空间，再创建新的独立后端检测器。|
|[`BudgetedTemporalDetector._ensure_open`](#api-BudgetedTemporalDetector-_ensure_open)|拒绝关闭后访问。|
|[`BudgetedTemporalDetector._ensure_active`](#api-BudgetedTemporalDetector-_ensure_active)|拒绝关闭或失败后继续推进/读取deadline，不尝试恢复部分core状态。|
|[`BudgetedTemporalDetector.rule`](#api-BudgetedTemporalDetector-rule)|读取冻结规则。|
|[`BudgetedTemporalDetector.start_ns`](#api-BudgetedTemporalDetector-start_ns)|读取domain起点。|
|[`BudgetedTemporalDetector.end_ns`](#api-BudgetedTemporalDetector-end_ns)|读取domain终点。|
|[`BudgetedTemporalDetector.next_deadline_ns`](#api-BudgetedTemporalDetector-next_deadline_ns)|读取core准确待确认截止。|
|[`BudgetedTemporalDetector.closed`](#api-BudgetedTemporalDetector-closed)|读取资源关闭状态。|
|[`BudgetedTemporalDetector.failed`](#api-BudgetedTemporalDetector-failed)|读取推进失败状态。|
|[`BudgetedTemporalDetector.duration_counts`](#api-BudgetedTemporalDetector-duration_counts)|借出已结束迟滞核的固定累计值，其他检测器无额外结果。|
|[`BudgetedTemporalDetector.extend_observed_end`](#api-BudgetedTemporalDetector-extend_observed_end)|将在线上界推进到新读到的真实末端，不交付terminal或分配输入历史。|
|[`BudgetedTemporalDetector.set_observed_end`](#api-BudgetedTemporalDetector-set_observed_end)|将请求上界收窄为实际观测终点，必须在交付该终点组之前调用。|
|[`BudgetedTemporalDetector._workspace_cost`](#api-BudgetedTemporalDetector-_workspace_cost)|估算输入持有、批量数组、最多N事件及其稳定ID临时串的同时存活上界。|
|[`BudgetedTemporalDetector._register`](#api-BudgetedTemporalDetector-_register)|只构造结果；外层取得本地引用后才登记并负责异常清理。|
|[`BudgetedTemporalDetector._discard_unreturned`](#api-BudgetedTemporalDetector-_discard_unreturned)|撤销本次未交付结果，预算仍由外层一次抵销，不关闭先前批。|
|[`BudgetedTemporalDetector._fail`](#api-BudgetedTemporalDetector-_fail)|丢弃部分推进的core并永久禁止重试，保留此前结果和固定元数据诊断。|
|[`BudgetedTemporalDetector.push`](#api-BudgetedTemporalDetector-push)|在预算内整批推进独立core，随后正式排空当前最终事件。|
|[`BudgetedTemporalDetector.finish`](#api-BudgetedTemporalDetector-finish)|在core已消费真正terminal后封闭检测器，返回剩余增量批且不重发旧事件。|
|[`BudgetedTemporalDetector.close`](#api-BudgetedTemporalDetector-close)|关闭全部自有批和固定申请，不关闭调用方budget或删除任何数据。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..core.models import SourceRef
from ..core.temporal import ConditionTick, TemporalRule
from ..core.temporal_reference import ReferenceTemporalDetector
from ..core.temporal_numpy import NumpyTemporalDetector
from ..core.stability import StabilitySpec, StabilityDetector
from ..core.start_end import StartEndSpec, StartEndDetector
from ..results.budget import ResourceBudget
from ..results.errors import AnalysisError, ResultClosedError
from ..results.spool import _cleanup_owner
from .history import _metadata_bytes
```

</details>

<a id="api-_BatchRegistry"></a>
## `_BatchRegistry`

用已有批对象的双向指针登记活动结果，新增/移除不分配容器容量。

只保存首指针；每个成员的前后指针由其已申请的批对象持有。长度按需遍历，
owner推进和关闭不计算长度。移除支持新增首节点尚未完全安装时的失败清理。

```python
_BatchRegistry()
```


源码：[`src/chronaxis/execution/temporal_buffer.py:34`](../../../src/chronaxis/execution/temporal_buffer.py#L34)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_BatchRegistry-__init__"></a>
### `_BatchRegistry.__init__`

建立固定大小登记器。

```python
_BatchRegistry.__init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

新登记器。

#### 异常说明

MemoryError。

源码：[`src/chronaxis/execution/temporal_buffer.py:41`](../../../src/chronaxis/execution/temporal_buffer.py#L41)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_BatchRegistry-__bool__"></a>
### `_BatchRegistry.__bool__`

检查是否有活动批。

```python
_BatchRegistry.__bool__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

True表示仍登记着未释放的结果批；False表示没有。

#### 异常说明

无。

源码：[`src/chronaxis/execution/temporal_buffer.py:46`](../../../src/chronaxis/execution/temporal_buffer.py#L46)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_BatchRegistry-__len__"></a>
### `_BatchRegistry.__len__`

读取活动批数量。

```python
_BatchRegistry.__len__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

int。

#### 异常说明

内部链损坏。

该诊断接口按需遍历，不建立随批数增长的辅助计数容器。

源码：[`src/chronaxis/execution/temporal_buffer.py:51`](../../../src/chronaxis/execution/temporal_buffer.py#L51)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_BatchRegistry-__iter__"></a>
### `_BatchRegistry.__iter__`

遍历当前活动批。

```python
_BatchRegistry.__iter__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

常量空间迭代器。

#### 异常说明

内部链损坏。

源码：[`src/chronaxis/execution/temporal_buffer.py:64`](../../../src/chronaxis/execution/temporal_buffer.py#L64)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_BatchRegistry-add"></a>
### `_BatchRegistry.add`

把新批安装到首端，不分配额外节点。

```python
_BatchRegistry.add(result)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`result`|[TemporalEventBatch](chronaxis.execution.temporal_buffer.md#api-TemporalEventBatch) &#124; PreparedConditionEvidence|是|无|位置或关键字。尚未登记的结果对象，包含_registry、_previous和_next链接属性；加入后可在关闭时统一追踪。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ValueError为重复/跨登记器安装；取消由owner撤销部分安装。

本函数直接报告的具体错误：

- `ValueError`：时序事件批已登记。

源码：[`src/chronaxis/execution/temporal_buffer.py:73`](../../../src/chronaxis/execution/temporal_buffer.py#L73)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_BatchRegistry-discard"></a>
### `_BatchRegistry.discard`

移除一个完整或部分安装的批，保留其他活动批。

```python
_BatchRegistry.discard(result)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`result`|[TemporalEventBatch](chronaxis.execution.temporal_buffer.md#api-TemporalEventBatch) &#124; PreparedConditionEvidence|是|无|位置或关键字。已登记且要移除的结果对象；只更新登记链，具体内存由其所属管理器释放。|

#### 返回说明

None；不属于本登记器时无副作用。

#### 异常说明

内部链损坏；不抵销批预算，由其生命周期边界负责释放。

源码：[`src/chronaxis/execution/temporal_buffer.py:90`](../../../src/chronaxis/execution/temporal_buffer.py#L90)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TemporalEventBatch"></a>
## `TemporalEventBatch`

持有本批最终事件及独立申请，owner失败后仍可读至本批或owner关闭。

events为冻结tuple，事件模型不随后续core推进改变。外部另存已取得的事件
超过close时刻须自行负责引用，不把释放申请解释为强制销毁外部对象。

```python
TemporalEventBatch(owner, cost, events)
```


源码：[`src/chronaxis/execution/temporal_buffer.py:111`](../../../src/chronaxis/execution/temporal_buffer.py#L111)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TemporalEventBatch-__init__"></a>
### `TemporalEventBatch.__init__`

在完整预留中转交事件，不复制来源元数据或保留输入ticks。

```python
TemporalEventBatch.__init__(owner, cost, events)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|[BudgetedTemporalDetector](chronaxis.execution.temporal_buffer.md#api-BudgetedTemporalDetector)|是|无|位置或关键字。产生该批事件的检测器，负责登记和回收结果占用的内存。|
|`cost`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|
|`events`|tuple[Event, ...]|是|无|位置或关键字。events已排空的Event tuple。|

#### 返回说明

新批结果，随后由owner登记。

#### 异常说明

MemoryError为构造失败，由owner清理本次申请并进入failed。

源码：[`src/chronaxis/execution/temporal_buffer.py:118`](../../../src/chronaxis/execution/temporal_buffer.py#L118)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TemporalEventBatch-closed"></a>
### `TemporalEventBatch.closed`

读取批关闭状态。

```python
TemporalEventBatch.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/execution/temporal_buffer.py:131`](../../../src/chronaxis/execution/temporal_buffer.py#L131)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TemporalEventBatch-events"></a>
### `TemporalEventBatch.events`

读取只读最终事件。

```python
TemporalEventBatch.events
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

Event tuple。

#### 异常说明

ResultClosedError。

本函数直接报告的具体错误：

- `ResultClosedError`：时序事件批已关闭。

源码：[`src/chronaxis/execution/temporal_buffer.py:137`](../../../src/chronaxis/execution/temporal_buffer.py#L137)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TemporalEventBatch-close"></a>
### `TemporalEventBatch.close`

抵销一次完整本批申请，不修改其它批或检测业务状态。

```python
TemporalEventBatch.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None，重复关闭安全。

#### 异常说明

内部账本不一致或取消；若已抵销则完成最小脱链/关闭后传播，
    尚未抵销时保持开放，可再次关闭。共用的资源用量记录遵守其单线程契约。

源码：[`src/chronaxis/execution/temporal_buffer.py:145`](../../../src/chronaxis/execution/temporal_buffer.py#L145)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BudgetedTemporalDetector"></a>
## `BudgetedTemporalDetector`

维护一个私有core、固定申请及活动事件批，预算外不累计旧events。

规则和domain只读，候选/run/前态跨普通批保存。每次push后正式drain输出，
已交付事件由批独立计账；调用方不直接操作core。failed与closed分别表示
推进失败和资源关闭，失败丢弃core但不隐式关闭先前批。

```python
BudgetedTemporalDetector(budget: ResourceBudget, rule: TemporalRule, start_ns: int, end_ns: int, source_refs: tuple[SourceRef, ...]=(), backend: str='numpy', *, stability=None, start_end=None, record_clock=False)
```


源码：[`src/chronaxis/execution/temporal_buffer.py:178`](../../../src/chronaxis/execution/temporal_buffer.py#L178)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BudgetedTemporalDetector-__init__"></a>
### `BudgetedTemporalDetector.__init__`

先申请完整规则/来源固定空间，再创建新的独立后端检测器。

```python
BudgetedTemporalDetector.__init__(budget: ResourceBudget, rule: TemporalRule, start_ns: int, end_ns: int, source_refs: tuple[SourceRef, ...]=(), backend: str='numpy', *, stability=None, start_end=None, record_clock=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)|是|无|位置或关键字。本次运行共用的ResourceBudget对象，用于检查内存和临时磁盘用量。当前对象在分配前申请额度，用完后归还；同一次运行的组件应使用同一个对象。|
|`rule`|[TemporalRule](chronaxis.core.temporal.md#api-TemporalRule)|是|无|位置或关键字。rule冻结规则|
|`start_ns`|int|是|无|位置或关键字。本次会话范围的开始时间，单位为整数纳秒；start_ns不能晚于end_ns。检测器到结束边界停止累计，不把后续无记录时间算进活动。|
|`end_ns`|int|是|无|位置或关键字。本次会话范围的结束时间，单位为整数纳秒；start_ns不能晚于end_ns。检测器到结束边界停止累计，不把后续无记录时间算进活动。|
|`source_refs`|tuple[[SourceRef](chronaxis.core.models.md#api-SourceRef), ...]|否|()|位置或关键字。source_refs固定引用|
|`backend`|str|否|'numpy'|位置或关键字。`"reference"`使用独立参考计算；`"numpy"`使用NumPy数组计算。须明确选择一种。|
|`stability`|[StabilitySpec](chronaxis.core.stability.md#api-StabilitySpec) &#124; None|否|None|仅关键字。迟滞或去抖配置；None表示不使用该检测方式，与start_end不能同时设置。|
|`start_end`|[StartEndSpec](chronaxis.core.start_end.md#api-StartEndSpec) &#124; None|否|None|仅关键字。开始和结束条件配置；None表示不使用该方式，与stability不能同时设置。|
|`record_clock`|bool|否|False|仅关键字。True按实际记录带来的累计步进处理时限；False沿日志真实时间推进，不另存完整计算时间轴。|

#### 返回说明

新owner，未消费任何tick。

#### 异常说明

类型/后端/规则/域/来源/预算/构造原错误；本次固定申请清理持续失败时，
    原异常附temporal_detector_cleanup_owner供恢复close，不改变调用方预算所有权。

源码：[`src/chronaxis/execution/temporal_buffer.py:186`](../../../src/chronaxis/execution/temporal_buffer.py#L186)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BudgetedTemporalDetector-_ensure_open"></a>
### `BudgetedTemporalDetector._ensure_open`

拒绝关闭后访问。

```python
BudgetedTemporalDetector._ensure_open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ResultClosedError。

本函数直接报告的具体错误：

- `ResultClosedError`：预算时序检测器已关闭。

源码：[`src/chronaxis/execution/temporal_buffer.py:244`](../../../src/chronaxis/execution/temporal_buffer.py#L244)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BudgetedTemporalDetector-_ensure_active"></a>
### `BudgetedTemporalDetector._ensure_active`

拒绝关闭或失败后继续推进/读取deadline，不尝试恢复部分core状态。

```python
BudgetedTemporalDetector._ensure_active()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ResultClosedError或AnalysisError为不可继续。

本函数直接报告的具体错误：

- `AnalysisError`：预算时序检测器已失败，禁止重试当前状态。

源码：[`src/chronaxis/execution/temporal_buffer.py:250`](../../../src/chronaxis/execution/temporal_buffer.py#L250)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BudgetedTemporalDetector-rule"></a>
### `BudgetedTemporalDetector.rule`

读取冻结规则。

```python
BudgetedTemporalDetector.rule
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

TemporalRule。

#### 异常说明

对象处于下列状态时抛ResultClosedError：预算时序检测器已关闭。

源码：[`src/chronaxis/execution/temporal_buffer.py:261`](../../../src/chronaxis/execution/temporal_buffer.py#L261)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BudgetedTemporalDetector-start_ns"></a>
### `BudgetedTemporalDetector.start_ns`

读取domain起点。

```python
BudgetedTemporalDetector.start_ns
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

int ns。

#### 异常说明

对象处于下列状态时抛ResultClosedError：预算时序检测器已关闭。

源码：[`src/chronaxis/execution/temporal_buffer.py:268`](../../../src/chronaxis/execution/temporal_buffer.py#L268)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BudgetedTemporalDetector-end_ns"></a>
### `BudgetedTemporalDetector.end_ns`

读取domain终点。

```python
BudgetedTemporalDetector.end_ns
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

int ns。

#### 异常说明

对象处于下列状态时抛ResultClosedError：预算时序检测器已关闭。

源码：[`src/chronaxis/execution/temporal_buffer.py:275`](../../../src/chronaxis/execution/temporal_buffer.py#L275)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BudgetedTemporalDetector-next_deadline_ns"></a>
### `BudgetedTemporalDetector.next_deadline_ns`

读取core准确待确认截止。

```python
BudgetedTemporalDetector.next_deadline_ns
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

int或None。

#### 异常说明

关闭或失败。

源码：[`src/chronaxis/execution/temporal_buffer.py:282`](../../../src/chronaxis/execution/temporal_buffer.py#L282)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BudgetedTemporalDetector-closed"></a>
### `BudgetedTemporalDetector.closed`

读取资源关闭状态。

```python
BudgetedTemporalDetector.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/execution/temporal_buffer.py:289`](../../../src/chronaxis/execution/temporal_buffer.py#L289)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BudgetedTemporalDetector-failed"></a>
### `BudgetedTemporalDetector.failed`

读取推进失败状态。

```python
BudgetedTemporalDetector.failed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象已记录处理失败；False表示尚未记录失败。

#### 异常说明

无；close不掩盖失败。

源码：[`src/chronaxis/execution/temporal_buffer.py:295`](../../../src/chronaxis/execution/temporal_buffer.py#L295)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BudgetedTemporalDetector-duration_counts"></a>
### `BudgetedTemporalDetector.duration_counts`

借出已结束迟滞核的固定累计值，其他检测器无额外结果。

```python
BudgetedTemporalDetector.duration_counts
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

整数纳秒对或None。

#### 异常说明

关闭、失败或尚未结束错误。

源码：[`src/chronaxis/execution/temporal_buffer.py:301`](../../../src/chronaxis/execution/temporal_buffer.py#L301)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BudgetedTemporalDetector-extend_observed_end"></a>
### `BudgetedTemporalDetector.extend_observed_end`

将在线上界推进到新读到的真实末端，不交付terminal或分配输入历史。

```python
BudgetedTemporalDetector.extend_observed_end(end_ns)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`end_ns`|int|是|无|位置或关键字。已到达的观测末端纳秒；延长运行中的观测边界。|

#### 返回说明

None。

#### 异常说明

已封闭或末端回退。

源码：[`src/chronaxis/execution/temporal_buffer.py:309`](../../../src/chronaxis/execution/temporal_buffer.py#L309)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BudgetedTemporalDetector-set_observed_end"></a>
### `BudgetedTemporalDetector.set_observed_end`

将请求上界收窄为实际观测终点，必须在交付该终点组之前调用。

```python
BudgetedTemporalDetector.set_observed_end(end_ns)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`end_ns`|int &#124; None|是|无|位置或关键字。实际结束时刻，单位纳秒；点事件或空片段按模型规定使用None，不填伪造的0。|

#### 返回说明

None。不生成terminal或结果，不回撤已处理组。

#### 异常说明

类型/范围或已完成错误；非法调用不改变core与owner边界。

源码：[`src/chronaxis/execution/temporal_buffer.py:323`](../../../src/chronaxis/execution/temporal_buffer.py#L323)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BudgetedTemporalDetector-_workspace_cost"></a>
### `BudgetedTemporalDetector._workspace_cost`

估算输入持有、批量数组、最多N事件及其稳定ID临时串的同时存活上界。

```python
BudgetedTemporalDetector._workspace_cost(ticks, maximum_events)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`ticks`|tuple|是|无|位置或关键字。ticks已提供带有明确类型的 tuple|
|`maximum_events`|int|是|无|位置或关键字。当前这一批最多可能产生的事件数，用于在计算前申请足够内存。|

#### 返回说明

非负int bytes，空批也覆盖固定工作容器。

#### 异常说明

元数据估算错误；尚未调用core，不改变业务状态。

源码：[`src/chronaxis/execution/temporal_buffer.py:341`](../../../src/chronaxis/execution/temporal_buffer.py#L341)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BudgetedTemporalDetector-_register"></a>
### `BudgetedTemporalDetector._register`

只构造结果；外层取得本地引用后才登记并负责异常清理。

```python
BudgetedTemporalDetector._register(cost, events)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`cost`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|
|`events`|tuple[Event, ...]|是|无|位置或关键字。内核本次已取出的事件，不含仍在等待确认的活动；登记后交给调用方。|

#### 返回说明

尚未登记的TemporalEventBatch。

#### 异常说明

构造/返回取消由推进边界抵销并failed。

源码：[`src/chronaxis/execution/temporal_buffer.py:353`](../../../src/chronaxis/execution/temporal_buffer.py#L353)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BudgetedTemporalDetector-_discard_unreturned"></a>
### `BudgetedTemporalDetector._discard_unreturned`

撤销本次未交付结果，预算仍由外层一次抵销，不关闭先前批。

```python
BudgetedTemporalDetector._discard_unreturned(result)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`result`|[TemporalEventBatch](chronaxis.execution.temporal_buffer.md#api-TemporalEventBatch) &#124; None|是|无|位置或关键字。已经构造但尚未交付的批次；None表示尚未构造完成，按失败清理路径处理。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

内部登记不一致；不调用result.close以免重复释放本批申请。

源码：[`src/chronaxis/execution/temporal_buffer.py:362`](../../../src/chronaxis/execution/temporal_buffer.py#L362)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BudgetedTemporalDetector-_fail"></a>
### `BudgetedTemporalDetector._fail`

丢弃部分推进的core并永久禁止重试，保留此前结果和固定元数据诊断。

```python
BudgetedTemporalDetector._fail()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

无主动异常；不声称旧业务状态已回滚。

源码：[`src/chronaxis/execution/temporal_buffer.py:377`](../../../src/chronaxis/execution/temporal_buffer.py#L377)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BudgetedTemporalDetector-push"></a>
### `BudgetedTemporalDetector.push`

在预算内整批推进独立core，随后正式排空当前最终事件。

```python
BudgetedTemporalDetector.push(ticks: tuple[ConditionTick, ...], exit_ticks=None, *, advances=None) -> TemporalEventBatch
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`ticks`|tuple[[ConditionTick](chronaxis.core.temporal.md#api-ConditionTick), ...]|是|无|位置或关键字。ticks完整组tuple，允许空批|
|`exit_ticks`|tuple &#124; None|否|None|位置或关键字。迟滞可另给同一时刻exit_ticks，start_end必须提供结束组，普通防抖省略。     批次不重置候选/边沿状态。|
|`advances`|tuple[int, ...] &#124; None|否|None|仅关键字。与本批完整时间组等长的非负计时增量；固定/DBC模式首组为0，实际时间模式必须为None。|

#### 返回说明

须close的TemporalEventBatch，最多len(ticks)个最终事件。

#### 异常说明

预算拒绝或申请取消发生在core前，可恢复；core调用或后续任何异常/取消使owner failed，
    抵销本批申请，先前批保持可读和计账。

本函数直接报告的具体错误：

- `TypeError`：预算时序push需要完整ConditionTick tuple。
- `TypeError`：start_end必须提供结束条件。
- `TypeError`：独立结束/退出仅供start_end或迟滞，且需完整ConditionTick tuple。
- `AnalysisError`：时序检测输出超过预先申请的每tick一个事件上界。

返回类型：[TemporalEventBatch](chronaxis.execution.temporal_buffer.md#api-TemporalEventBatch)。

源码：[`src/chronaxis/execution/temporal_buffer.py:386`](../../../src/chronaxis/execution/temporal_buffer.py#L386)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BudgetedTemporalDetector-finish"></a>
### `BudgetedTemporalDetector.finish`

在core已消费真正terminal后封闭检测器，返回剩余增量批且不重发旧事件。

```python
BudgetedTemporalDetector.finish() -> TemporalEventBatch
```

参数：无显式参数。


#### 参数说明

无，不能补造终点或消费新的输入。

#### 返回说明

须close的批；本owner每次push均排空，因此正常finish.events为空。

#### 异常说明

预算拒绝/申请取消在core前可重试；缺terminal/重复finish或后续失败使owner failed。

本函数直接报告的具体错误：

- `AnalysisError`：预算检测器finish出现未在push中增量交付的事件。

返回类型：[TemporalEventBatch](chronaxis.execution.temporal_buffer.md#api-TemporalEventBatch)。

源码：[`src/chronaxis/execution/temporal_buffer.py:443`](../../../src/chronaxis/execution/temporal_buffer.py#L443)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BudgetedTemporalDetector-close"></a>
### `BudgetedTemporalDetector.close`

关闭全部自有批和固定申请，不关闭调用方budget或删除任何数据。

```python
BudgetedTemporalDetector.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None，幂等且支持部分构造失败。

#### 异常说明

内部账本不一致或取消；已释放固定申请时完成最小收尾后传播。
    failed标志保留用于说明此前失败；尚未释放时可重试关闭。

源码：[`src/chronaxis/execution/temporal_buffer.py:481`](../../../src/chronaxis/execution/temporal_buffer.py#L481)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
