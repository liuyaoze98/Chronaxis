# chronaxis.core.sequence_reference

按时间组将请求与响应FIFO配对，区分未响应和无法确定。

输入为同一组完整有序的SequenceTick，输出为每次push新确定的SequenceResult。
检测器保存尚未决定的请求；返回的结果不再在内部累积。候选数有明确上限，
任何失败均封闭实例，调用者不能把部分结果宣告为完整任务成功。
响应可判断性来自既有ConditionTick的连续/点视图，TTL等边界必须由上游提供。
状态循环只依赖标准库，不冒称NumPy数组优化，不读取来源或写盘。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ConditionTimeline](chronaxis.core.temporal.md#api-ConditionTimeline)、[Event](chronaxis.core.temporal.md#api-Event)、[Interval](chronaxis.core.models.md#api-Interval)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[SequenceResult](chronaxis.core.sequence.md#api-SequenceResult)、[SequenceRule](chronaxis.core.sequence.md#api-SequenceRule)、[SequenceTick](chronaxis.core.sequence.md#api-SequenceTick)、[Truth](chronaxis.core.types.md#api-Truth)

## 对象导航

|对象|用途|
|---|---|
|[`SequenceDetector`](#api-SequenceDetector)|维护一个dataset/session/group/rule的等待队列与观测状态。|
|[`SequenceDetector.__init__`](#api-SequenceDetector-__init__)|建立独立状态，不从别的组或会话复制候选。|
|[`SequenceDetector.pending_count`](#api-SequenceDetector-pending_count)|返回尚未决定的请求数量，不暴露可修改队列。|
|[`SequenceDetector._note`](#api-SequenceDetector-_note)|累计本段未知原因，供各请求按自己的起点查询。|
|[`SequenceDetector._advance`](#api-SequenceDetector-_advance)|结算上个时间组至指定时刻的连续观测，不推断额外响应。|
|[`SequenceDetector._result`](#api-SequenceDetector-_result)|把一个请求的匹配、超时或无法判断状态转换为结果，并保留原请求和响应事件。|
|[`SequenceDetector._consume`](#api-SequenceDetector-_consume)|按先前截止点、同一时刻配对、同一时刻超时、EOF的顺序处理一组。|
|[`SequenceDetector.push`](#api-SequenceDetector-push)|处理一批已收齐同一时刻更新的数据，返回这次已经能够确定的配对结果；等待中的请求保留到后续批次。|
|[`SequenceDetector.finish`](#api-SequenceDetector-finish)|确认已经收到真正EOF，不制造额外响应或超时。|
|[`pair_sequence`](#api-pair_sequence)|将既有事件与完整响应条件轴接到顺序核心，适合可控内存分析。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from collections import deque
from hashlib import sha256
from .binding import _identity
from .models import Interval
from .sequence import SequenceResult, SequenceRule, SequenceTick
from .temporal import ConditionTimeline, Event
from .temporal_reference import require_batch
from .types import QualityFlag as Q, Truth
from ..timebase.conversion import checked_add_ns
```

</details>

<a id="api-SequenceDetector"></a>
## `SequenceDetector`

维护一个dataset/session/group/rule的等待队列与观测状态。

候选按A时间和同一时刻稳定ID排序。B只消费最早的合格A；截止点先匹配再超时。
输入跨批连续、批尾不当EOF；每次push立即转交已决定结果。max_pending限制
同时存在的请求数量，不是整进程RAM保证，公共AnalysisRunner的SequenceRows另行计费。

```python
SequenceDetector(rule: SequenceRule, start_ns: int, end_ns: int, *, max_pending: int=65536)
```


源码：[`src/chronaxis/core/sequence_reference.py:25`](../../../src/chronaxis/core/sequence_reference.py#L25)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-SequenceDetector-__init__"></a>
### `SequenceDetector.__init__`

建立独立状态，不从别的组或会话复制候选。

```python
SequenceDetector.__init__(rule: SequenceRule, start_ns: int, end_ns: int, *, max_pending: int=65536)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`rule`|[SequenceRule](chronaxis.core.sequence.md#api-SequenceRule)|是|无|位置或关键字。SequenceRule，声明请求规则、响应规则和允许的最小/最大延迟。|
|`start_ns`|int|是|无|位置或关键字。本次会话范围的开始时间，单位为整数纳秒；start_ns不能晚于end_ns。检测器到结束边界停止累计，不把后续无记录时间算进活动。|
|`end_ns`|int|是|无|位置或关键字。本次会话范围的结束时间，单位为整数纳秒；start_ns不能晚于end_ns。检测器到结束边界停止累计，不把后续无记录时间算进活动。|
|`max_pending`|int|否|65536|仅关键字。max_pending为正原生整数。|

#### 返回说明

新检测器，尚未消费任何时间组。

#### 异常说明

TypeError/ValueError/OverflowError为规则、范围或容量错误。

本函数直接报告的具体错误：

- `TypeError`：需要SequenceRule及正int max_pending。

源码：[`src/chronaxis/core/sequence_reference.py:33`](../../../src/chronaxis/core/sequence_reference.py#L33)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-SequenceDetector-pending_count"></a>
### `SequenceDetector.pending_count`

返回尚未决定的请求数量，不暴露可修改队列。

```python
SequenceDetector.pending_count
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

非负整数；已结束或失败时为0。

#### 异常说明

无主动异常。

源码：[`src/chronaxis/core/sequence_reference.py:55`](../../../src/chronaxis/core/sequence_reference.py#L55)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-SequenceDetector-_note"></a>
### `SequenceDetector._note`

累计本段未知原因，供各请求按自己的起点查询。

```python
SequenceDetector._note(quality)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`quality`|QualityFlag|是|无|位置或关键字。本步的质量标记，可用按位或组合MISSING、NONFINITE等原因；NONE表示没有这些异常。全部标记见[结果说明](../results.md)。|

#### 返回说明

None，更新固定长度计数器。

#### 异常说明

无主动异常；只由内部协议调用。

源码：[`src/chronaxis/core/sequence_reference.py:65`](../../../src/chronaxis/core/sequence_reference.py#L65)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-SequenceDetector-_advance"></a>
### `SequenceDetector._advance`

结算上个时间组至指定时刻的连续观测，不推断额外响应。

```python
SequenceDetector._advance(time_ns)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|位置或关键字。将配对检测器推进到此纳秒时刻；不得早于内部游标，推进时结算已经到期的请求。|

#### 返回说明

None；正长度未知区间计入质量，零长度不增加区间证据。

#### 异常说明

无主动异常，外层已验证时间顺序。

源码：[`src/chronaxis/core/sequence_reference.py:77`](../../../src/chronaxis/core/sequence_reference.py#L77)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-SequenceDetector-_result"></a>
### `SequenceDetector._result`

把一个请求的匹配、超时或无法判断状态转换为结果，并保留原请求和响应事件。

```python
SequenceDetector._result(pending, time_ns, response=None, *, early_end=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`pending`|tuple[[Event](chronaxis.core.temporal.md#api-Event), tuple[int, ...], int]|是|无|位置或关键字。一个待响应请求：依次保存请求事件、当时各质量原因的累计计数快照、超时截止纳秒时刻。|
|`time_ns`|int|是|无|位置或关键字。当前计算时刻，单位为纳秒；推进检测器时不能早于上一次已处理的时刻。|
|`response`|[Event](chronaxis.core.temporal.md#api-Event) &#124; None|否|None|位置或关键字。与请求配成一对的响应事件；超时或观测提前结束而无响应时为None。|
|`early_end`|bool|否|False|仅关键字。early_end表示提前EOF。|

#### 返回说明

SequenceResult，匹配或有质量依据的未匹配结果。

#### 异常说明

模型校验或内存异常传播，不输出伪成功。

源码：[`src/chronaxis/core/sequence_reference.py:89`](../../../src/chronaxis/core/sequence_reference.py#L89)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-SequenceDetector-_consume"></a>
### `SequenceDetector._consume`

按先前截止点、同一时刻配对、同一时刻超时、EOF的顺序处理一组。

```python
SequenceDetector._consume(tick, output, advance=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`tick`|[SequenceTick](chronaxis.core.sequence.md#api-SequenceTick)|是|无|位置或关键字。已经检查过的当前时间组，包含请求事件、响应事件和条件证据。|
|`output`|list[[SequenceResult](chronaxis.core.sequence.md#api-SequenceResult)]|是|无|位置或关键字。本批输出列表，新产生的配对或超时结果追加到这里。|
|`advance`|int|否|None|位置或关键字。当前完整时间组增加的所选计时纳秒数；所选报文到达才增加周期，其他边界为0。|

#### 返回说明

None；更新候选和游标，不存储已经转交的结果。

#### 异常说明

MemoryError为候选上限；结果构造失败传播。

本函数直接报告的具体错误：

- `MemoryError`：sequence待响应请求超过max_pending。

源码：[`src/chronaxis/core/sequence_reference.py:117`](../../../src/chronaxis/core/sequence_reference.py#L117)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-SequenceDetector-push"></a>
### `SequenceDetector.push`

处理一批已收齐同一时刻更新的数据，返回这次已经能够确定的配对结果；等待中的请求保留到后续批次。

```python
SequenceDetector.push(ticks: tuple[SequenceTick, ...], *, advances=None) -> tuple[SequenceResult, ...]
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`ticks`|tuple[[SequenceTick](chronaxis.core.sequence.md#api-SequenceTick), ...]|是|无|位置或关键字。ticks为有序tuple，可为空，首末与声明会话范围一致|
|`advances`|tuple[int, ...] &#124; None|否|None|仅关键字。与本批完整时间组等长的非负计时增量；固定/DBC模式首组为0，实际时间模式必须为None。|

#### 返回说明

新SequenceResult tuple；调用者负责消费，不在实例中重复保留。

#### 异常说明

TypeError/ValueError/OverflowError为协议错误；MemoryError为容量不足。

本函数直接报告的具体错误：

- `ValueError`：sequence实例已失败或finish。
- `TypeError`：push需要SequenceTick tuple。

#### 副作用说明

失败后释放候选并封闭实例，已转交的早先批次不能视为完整成功。

返回类型：tuple[[SequenceResult](chronaxis.core.sequence.md#api-SequenceResult), ...]。

源码：[`src/chronaxis/core/sequence_reference.py:162`](../../../src/chronaxis/core/sequence_reference.py#L162)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-SequenceDetector-finish"></a>
### `SequenceDetector.finish`

确认已经收到真正EOF，不制造额外响应或超时。

```python
SequenceDetector.finish()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None；结果已经由各次push转交。

#### 异常说明

ValueError为缺EOF、失败或重复finish。

本函数直接报告的具体错误：

- `ValueError`：finish需要完整terminal且实例未关闭。

源码：[`src/chronaxis/core/sequence_reference.py:198`](../../../src/chronaxis/core/sequence_reference.py#L198)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-pair_sequence"></a>
## `pair_sequence`

将既有事件与完整响应条件轴接到顺序核心，适合可控内存分析。

```python
pair_sequence(rule: SequenceRule, starts: tuple[Event, ...], responses: tuple[Event, ...], timeline: ConditionTimeline, *, batch_rows: int=65536, max_pending: int=65536)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`rule`|[SequenceRule](chronaxis.core.sequence.md#api-SequenceRule)|是|无|位置或关键字。本组SequenceRule；例如min_delay_ns=0、max_delay_ns=2000000000允许0—2秒响应。|
|`starts`|tuple[[Event](chronaxis.core.temporal.md#api-Event), ...]|是|无|位置或关键字。已经确认的请求点事件，按时间顺序排列；活动事件不能作为请求点。|
|`responses`|tuple[[Event](chronaxis.core.temporal.md#api-Event), ...]|是|无|位置或关键字。已经确认的响应点事件，按时间顺序排列；每个响应最多使用一次。|
|`timeline`|[ConditionTimeline](chronaxis.core.temporal.md#api-ConditionTimeline)|是|无|位置或关键字。timeline含全部条件变化、TTL及EOF|
|`batch_rows`|int|否|65536|仅关键字。一次处理的完整时间组数量，必须是正整数；同一时间的更新不能拆到两个批次。|
|`max_pending`|int|否|65536|仅关键字。同时等待响应的请求数量上限，必须为正整数；超过时报告容量错误，不静默丢弃请求。|

### 返回说明

SequenceResult tuple；只为此内存便利入口收集全部输出。

### 异常说明

TypeError/ValueError为类型/归属/缺失事件时刻；容量与时间溢出传播。

本函数直接报告的具体错误：

- `TypeError`：需要ConditionTimeline及正int batch_rows。
- `ValueError`：响应观测来源不属于当前会话。
- `ValueError`：事件确认时刻不在响应条件时间轴中。
- `TypeError`：完整事件输入需要tuple。
- `ValueError`：同一角色内事件ID重复。

### 边界说明

不补采样、解析文件或推断同步；大数据上层直接分批使用SequenceDetector。

源码：[`src/chronaxis/core/sequence_reference.py:211`](../../../src/chronaxis/core/sequence_reference.py#L211)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

## 内部匿名回调


<a id="lambda-140"></a>
### 第140行匿名函数

```python
lambda item: item.event_id
```

|参数|含义|返回/异常|
|---|---|---|
|`item`|本时间刻度的请求或响应事件。|返回event_id，按事件标识稳定排序。|

<a id="lambda-146"></a>
### 第146行匿名函数

```python
lambda item: item.event_id
```

|参数|含义|返回/异常|
|---|---|---|
|`item`|本时间刻度的请求或响应事件。|返回event_id，按事件标识稳定排序。|
