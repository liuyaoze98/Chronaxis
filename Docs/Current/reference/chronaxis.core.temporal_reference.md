# `chronaxis.core.temporal_reference`

逐时间组检测持续条件和真实边沿，输出已经确认的活动或点事件。

输入为完整ConditionTick批次、会话范围和TemporalRule。持续候选跨批保留：
先结算此前TRUE区间的时长，再处理当前点更新和连续状态，最后处理观测结束。
确认时间记录为精确阈值到期时刻，不等待下一报文。空批次不重置状态，finish
只能在真正会话终点之后调用。默认保存全部事件；主动drain_events只转交并清空
已产生输出，不重置业务状态，此后finish返回尚未取走的事件。
这是独立的标准库参考状态机，只共享模型、身份和协议检查，不调用NumPy
检测算法。不读取来源、不持有全局状态，每个检测器对应一个规则和会话。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ConditionTick](chronaxis.core.temporal.md#api-ConditionTick)、[ConditionTimeline](chronaxis.core.temporal.md#api-ConditionTimeline)、[Interval](chronaxis.core.models.md#api-Interval)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[SourceRef](chronaxis.core.models.md#api-SourceRef)、[TemporalRule](chronaxis.core.temporal.md#api-TemporalRule)、[Truth](chronaxis.core.types.md#api-Truth)

## 对象导航

|对象|用途|
|---|---|
|[`require_batch`](#api-require_batch)|验证完整时刻组的批次顺序/边界，不检测状态。|
|[`require_detector`](#api-require_detector)|校验规则/域/来源范围，不初始化算法状态。|
|[`ReferenceTemporalDetector`](#api-ReferenceTemporalDetector)|保存一个规则在一个会话内的候选活动、确认时间和边沿前态。|
|[`ReferenceTemporalDetector.__init__`](#api-ReferenceTemporalDetector-__init__)|检查规则、会话范围和来源后，创建空的检测状态。|
|[`ReferenceTemporalDetector.next_deadline_ns`](#api-ReferenceTemporalDetector-next_deadline_ns)|给出待确认候选的精确下一deadline，不等待新报文时间。|
|[`ReferenceTemporalDetector._consume`](#api-ReferenceTemporalDetector-_consume)|结算旧TRUE区间，再处理当前更新及连续状态，最后处理会话终点。|
|[`ReferenceTemporalDetector.push`](#api-ReferenceTemporalDetector-push)|处理一批时间组，保留尚待确认的活动和边沿状态，返回这次新确定的事件。|
|[`ReferenceTemporalDetector.drain_events`](#api-ReferenceTemporalDetector-drain_events)|转交当前未取走的最终事件，并清空输出容器，不推进或重置业务状态。|
|[`ReferenceTemporalDetector.finish`](#api-ReferenceTemporalDetector-finish)|在已处理真正terminal后关闭并返回当前尚未取走的稳定事件。|
|[`detect_reference`](#api-detect_reference)|按batch_size分批处理条件时间轴；分批时保留检测状态，活动不会因批次结束而中断。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .temporal import ConditionTick, ConditionTimeline, TemporalRule, make_event
from .models import Interval, SourceRef
from .types import QualityFlag as Q, Truth
```

</details>

<a id="api-require_batch"></a>
## `require_batch`

验证完整时刻组的批次顺序/边界，不检测状态。

```python
require_batch(ticks, start_ns, end_ns, previous_time_ns, ended)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`ticks`|tuple[[ConditionTick](chronaxis.core.temporal.md#api-ConditionTick), ...]|是|无|位置或关键字。本批完整且有序的条件时间组，同一时刻不能拆开。|
|`start_ns`|int|是|无|位置或关键字。允许处理的时间范围起点，整数纳秒。|
|`end_ns`|int|是|无|位置或关键字。允许处理的时间范围终点，整数纳秒。|
|`previous_time_ns`|int &#124; None|是|无|位置或关键字。前一批最后处理的纳秒时刻；首批尚无前一时刻时为None。|
|`ended`|bool|是|无|位置或关键字。检测器是否已经处理会话终点；True时不能再接收后续时间组。|

### 返回说明

None，空批次允许但不产生EOF。

### 异常说明

TypeError/ValueError为错类型/回退/中途terminal/边界不符。

本函数直接报告的具体错误：

- `TypeError`：检测batch需tuple ConditionTick。
- `ValueError`：真实terminal之后不能push。
- `ValueError`：首组必须为domain start。
- `ValueError`：条件组重复/回退/超domain。
- `ValueError`：terminal与真实domain end不符。

源码：[`src/chronaxis/core/temporal_reference.py:20`](../../../src/chronaxis/core/temporal_reference.py#L20)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-require_detector"></a>
## `require_detector`

校验规则/域/来源范围，不初始化算法状态。

```python
require_detector(rule, start_ns, end_ns, refs)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`rule`|[TemporalRule](chronaxis.core.temporal.md#api-TemporalRule)|是|无|位置或关键字。当前时序规则，指定持续条件、边沿或start_only的检测要求。|
|`start_ns`|int|是|无|位置或关键字。完整检测范围的开始纳秒坐标。|
|`end_ns`|int|是|无|位置或关键字。完整检测范围的结束纳秒坐标，不得早于start。|
|`refs`|tuple[[SourceRef](chronaxis.core.models.md#api-SourceRef), ...]|是|无|位置或关键字。当前检测依赖的真实来源引用，保留在产生的事件中。|

### 返回说明

None，span/int64/会话一致则通过。

### 异常说明

TypeError/ValueError/OverflowError为配置或来源冲突。

本函数直接报告的具体错误：

- `TypeError`：检测需要TemporalRule及tuple refs。
- `ValueError`：检测来源session不一致。

源码：[`src/chronaxis/core/temporal_reference.py:53`](../../../src/chronaxis/core/temporal_reference.py#L53)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ReferenceTemporalDetector"></a>
## `ReferenceTemporalDetector`

保存一个规则在一个会话内的候选活动、确认时间和边沿前态。

candidate_start与confirmed分别保存起点和确认时刻；last_truth与last_time
保存上一完整组，seen_known控制首次已知条件。全部状态属于当前实例，普通
批次边界不清理；finish只在真实终点之后关闭实例。未确认候选不作为Event输出。
events默认累计；drain_events可增量取走输出，候选、边沿前态和抑制状态不变。
start_only额外保存blocked_until_ns；只接受真实rising_edge或明确首次初始化，
固定窗口内触发丢弃，到期不排队或自动重触发，右端真实边沿允许再次接受。

```python
ReferenceTemporalDetector(rule, start_ns, end_ns, source_refs=(), *, record_clock=False)
```


源码：[`src/chronaxis/core/temporal_reference.py:74`](../../../src/chronaxis/core/temporal_reference.py#L74)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ReferenceTemporalDetector-__init__"></a>
### `ReferenceTemporalDetector.__init__`

检查规则、会话范围和来源后，创建空的检测状态。

```python
ReferenceTemporalDetector.__init__(rule, start_ns, end_ns, source_refs=(), *, record_clock=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`rule`|[TemporalRule](chronaxis.core.temporal.md#api-TemporalRule)|是|无|位置或关键字。当前规则，不继承其他实例配置。 start_ns、end_ns (int): 完整会话起止坐标，单位为纳秒。|
|`start_ns`|int|是|无|位置或关键字。完整会话的开始纳秒坐标，包含该时刻。|
|`end_ns`|int|是|无|位置或关键字。完整会话的结束纳秒坐标，连续区间不包含该右端。|
|`source_refs`|tuple[[SourceRef](chronaxis.core.models.md#api-SourceRef), ...]|否|()|位置或关键字。当前来源引用，默认空tuple。|
|`record_clock`|bool|否|False|仅关键字。True按实际记录带来的累计步进处理时限；False沿日志真实时间推进，不另存完整计算时间轴。|

#### 返回说明

None: 候选、确认时间、边沿前态和事件集合均从初始状态开始。

#### 异常说明

TypeError、ValueError或OverflowError: 规则、时间范围或来源归属不合法。

#### 副作用说明

初始化本实例状态，没有全局缓存或文件操作。

源码：[`src/chronaxis/core/temporal_reference.py:85`](../../../src/chronaxis/core/temporal_reference.py#L85)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ReferenceTemporalDetector-next_deadline_ns"></a>
### `ReferenceTemporalDetector.next_deadline_ns`

给出待确认候选的精确下一deadline，不等待新报文时间。

```python
ReferenceTemporalDetector.next_deadline_ns
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无；读取候选/规则/完整domain。

#### 返回说明

int ns或None；超domain门槛永不误cast/wrap。

#### 异常说明

无主动异常；状态局部。

源码：[`src/chronaxis/core/temporal_reference.py:120`](../../../src/chronaxis/core/temporal_reference.py#L120)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ReferenceTemporalDetector-_consume"></a>
### `ReferenceTemporalDetector._consume`

结算旧TRUE区间，再处理当前更新及连续状态，最后处理会话终点。

```python
ReferenceTemporalDetector._consume(tick, advance=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`tick`|[ConditionTick](chronaxis.core.temporal.md#api-ConditionTick)|是|无|位置或关键字。已经过批次协议检查的完整时间组。|
|`advance`|int|否|None|位置或关键字。当前完整时间组增加的所选计时纳秒数；所选报文到达才增加周期，其他边界为0。|

#### 返回说明

None: 更新本实例候选、确认时间、诊断、边沿前态和最终事件。

#### 异常说明

TypeError、ValueError或OverflowError: 构造事件时模型检查失败，错误原样传播。

#### 边界说明

阈值恰好等于当前结束时间仍可确认；真实FALSE优先闭合，真实无效更新
    优先中断。单纯观测结束截断活动；会话终点不创建新持续候选。

源码：[`src/chronaxis/core/temporal_reference.py:136`](../../../src/chronaxis/core/temporal_reference.py#L136)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ReferenceTemporalDetector-push"></a>
### `ReferenceTemporalDetector.push`

处理一批时间组，保留尚待确认的活动和边沿状态，返回这次新确定的事件。

```python
ReferenceTemporalDetector.push(ticks: tuple[ConditionTick, ...], *, advances=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`ticks`|tuple[[ConditionTick](chronaxis.core.temporal.md#api-ConditionTick), ...]|是|无|位置或关键字。ticks已归并tuple，允许空batch不重置。|
|`advances`|tuple[int, ...] &#124; None|否|None|仅关键字。与本批完整时间组等长的非负计时增量；固定/DBC模式首组为0，实际时间模式必须为None。|

#### 返回说明

本批新增Event tuple，未结束pending/active不写伪事件。

#### 异常说明

ValueError为finish后/回退/边界错，带有明确类型的协议异常传播。

本函数直接报告的具体错误：

- `ValueError`：检测器已finish。

源码：[`src/chronaxis/core/temporal_reference.py:231`](../../../src/chronaxis/core/temporal_reference.py#L231)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ReferenceTemporalDetector-drain_events"></a>
### `ReferenceTemporalDetector.drain_events`

转交当前未取走的最终事件，并清空输出容器，不推进或重置业务状态。

```python
ReferenceTemporalDetector.drain_events()
```

参数：无显式参数。


#### 参数说明

无，读取本实例已经产生的events。

#### 返回说明

Event tuple；未产生输出或已经排空时为空tuple。

#### 异常说明

MemoryError为tuple构造失败，此时原输出保持未排空。

#### 副作用说明

成功后只清空events，候选/确认/前态/初始化/抑制及生命周期均保持。

源码：[`src/chronaxis/core/temporal_reference.py:256`](../../../src/chronaxis/core/temporal_reference.py#L256)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ReferenceTemporalDetector-finish"></a>
### `ReferenceTemporalDetector.finish`

在已处理真正terminal后关闭并返回当前尚未取走的稳定事件。

```python
ReferenceTemporalDetector.finish()
```

参数：无显式参数。


#### 参数说明

无，不制造EOF或读取额外输入。

#### 返回说明

尚未drain的Event tuple；未调用drain时仍返回全部事件，保持原API。

#### 异常说明

ValueError为缺terminal或重复finish。

本函数直接报告的具体错误：

- `ValueError`：finish需已消费真正terminal且不能重复。

源码：[`src/chronaxis/core/temporal_reference.py:269`](../../../src/chronaxis/core/temporal_reference.py#L269)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-detect_reference"></a>
## `detect_reference`

按batch_size分批处理条件时间轴；分批时保留检测状态，活动不会因批次结束而中断。

```python
detect_reference(rule: TemporalRule, timeline: ConditionTimeline, *, batch_rows: int=65536)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`rule`|[TemporalRule](chronaxis.core.temporal.md#api-TemporalRule)|是|无|位置或关键字。本次时序Rule声明，包含规则ID、种类及持续/边沿设置。|
|`timeline`|[ConditionTimeline](chronaxis.core.temporal.md#api-ConditionTimeline)|是|无|位置或关键字。按时间排列的ConditionTick时间线，包含条件变化、失效与结束信息。|
|`batch_rows`|int|否|65536|仅关键字。batch_rows正原生int，只切组，不切原子同一时刻事实。|

### 返回说明

独立参考Event tuple，ID与分割无关。

### 异常说明

TypeError/ValueError为模型/批大小，检测协议错误传播。

本函数直接报告的具体错误：

- `TypeError`：detect需ConditionTimeline及正int batch_rows。

源码：[`src/chronaxis/core/temporal_reference.py:286`](../../../src/chronaxis/core/temporal_reference.py#L286)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
