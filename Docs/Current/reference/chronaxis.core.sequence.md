# `chronaxis.core.sequence`

在同一会话内把请求点和响应点逐个配对。保存未匹配请求，按允许延迟匹配最早合格请求；区分成功、完整等待无响应和数据不足。详见[请求响应](../sequences.md)。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ConditionTick](chronaxis.core.temporal.md#api-ConditionTick)、[Event](chronaxis.core.temporal.md#api-Event)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[Truth](chronaxis.core.types.md#api-Truth)

## 对象导航

|对象|用途|
|---|---|
|[`SequenceRule`](#api-SequenceRule)|声明一组请求/响应规则及允许的延迟；例如0到2秒会接受恰好2秒的响应。不同会话各自配对。|
|[`SequenceRule.__post_init__`](#api-SequenceRule-__post_init__)|验证规则身份与整数延迟，不猜测缺省等待时间。|
|[`SequenceRule.check_event`](#api-SequenceRule-check_event)|检查事件来自指定规则和当前会话，不按同名信号跨会话配对。|
|[`SequenceTick`](#api-SequenceTick)|保存同一时刻全部A/B及响应是否可判断的证据。|
|[`SequenceTick.__post_init__`](#api-SequenceTick-__post_init__)|检查同一时刻的请求和响应是否已收齐；收齐前不交给检测器处理。|
|[`SequenceResult`](#api-SequenceResult)|一个请求最终得到的一条配对结果。成功时给出响应和延迟；资料缺失与确实无响应分别保存。|
|[`SequenceResult.__post_init__`](#api-SequenceResult-__post_init__)|拒绝不可能的结果组合，防止把未知观测组装成正常超时。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from .temporal import ConditionTick, Event
from .types import QualityFlag as Q, Truth
from .validation import require_identifier, require_text
from ..timebase.conversion import checked_add_ns, require_int64_ns
```

</details>

<a id="api-SequenceRule"></a>
## `SequenceRule`

声明一组请求/响应规则及允许的延迟；例如0到2秒会接受恰好2秒的响应。不同会话各自配对。

```python
class SequenceRule
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`rule_id`|str|是|无|本组请求响应配对的唯一ID。|
|`dataset_id`|str|是|无|所属数据集ID，用于结果身份与隔离。|
|`session_id`|str|是|无|当前独立会话的字符串ID，例如trial_a；不能混用另一试验的数据。|
|`start_rule_id`|str|是|无|产生请求点事件的规则ID。|
|`response_rule_id`|str|是|无|产生响应点事件的规则ID。|
|`min_delay_ns`|int|是|无|允许的最小响应延迟，非负整数纳秒，边界包含。|
|`max_delay_ns`|int|是|无|允许的最大响应延迟，整数纳秒且不小于min_delay_ns，边界包含。|
|`group_id`|str|否|'default'|标识已经划分的分析组；由调用侧提供，例如设备分组名称。默认default；各组独立配对，不从报文ID自动分组。|
|`record_clock`|bool|否|False|True时delay按所选记录间隔累计，事件坐标仍是实际时间。|

源码：[`src/chronaxis/core/sequence.py:19`](../../../src/chronaxis/core/sequence.py#L19)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SequenceRule-__post_init__"></a>
### `SequenceRule.__post_init__`

验证规则身份与整数延迟，不猜测缺省等待时间。

```python
SequenceRule.__post_init__()
```

参数：无显式参数。


#### 参数说明

无额外参数，读取创建后不可修改的字段。

#### 返回说明

None；纳秒规范为Python整数。

#### 异常说明

TypeError/ValueError/OverflowError表示非法身份、范围或类型。

本函数直接报告的具体错误：

- `ValueError`：需要0 <= min_delay_ns <= max_delay_ns。

源码：[`src/chronaxis/core/sequence.py:36`](../../../src/chronaxis/core/sequence.py#L36)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SequenceRule-check_event"></a>
### `SequenceRule.check_event`

检查事件来自指定规则和当前会话，不按同名信号跨会话配对。

```python
SequenceRule.check_event(event: Event, *, response: bool)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`event`|[Event](chronaxis.core.temporal.md#api-Event)|是|无|位置或关键字。event为既有Event|
|`response`|bool|是|无|仅关键字。response明确表示A或B角色。|

#### 返回说明

None，保留原事件及其来源引用。

#### 异常说明

TypeError为类型不符，ValueError为数据集/会话/规则不匹配。

本函数直接报告的具体错误：

- `TypeError`：需要Event及bool角色。
- `ValueError`：顺序事件的数据集、会话或规则不匹配。

源码：[`src/chronaxis/core/sequence.py:58`](../../../src/chronaxis/core/sequence.py#L58)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SequenceTick"></a>
## `SequenceTick`

保存同一时刻全部A/B及响应是否可判断的证据。

condition.state描述此刻之后的连续区间，point_state描述此刻本身；terminal的
人工连续UNKNOWN不污染真实末点。B出现时点证据必须已知。角色内重复ID拒绝，
事件顺序不参与业务配对，检测器会按稳定ID处理同一时刻并列事件。

```python
class SequenceTick
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`condition`|[ConditionTick](chronaxis.core.temporal.md#api-ConditionTick)|是|无|提供此刻响应条件的观测证据，传入ConditionTick。state描述此刻之后的区间，point_state描述此刻本身；须与starts/responses的确认时间相同。|
|`starts`|tuple[[Event](chronaxis.core.temporal.md#api-Event), ...]|否|()|当前时刻发生的请求Event元组；空元组表示没有请求。|
|`responses`|tuple[[Event](chronaxis.core.temporal.md#api-Event), ...]|否|()|当前时刻发生的响应Event元组；先收集同一时刻事件，再做配对。|

源码：[`src/chronaxis/core/sequence.py:74`](../../../src/chronaxis/core/sequence.py#L74)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SequenceTick-__post_init__"></a>
### `SequenceTick.__post_init__`

检查同一时刻的请求和响应是否已收齐；收齐前不交给检测器处理。

```python
SequenceTick.__post_init__()
```

参数：无显式参数。


#### 参数说明

无额外参数；condition及两个事件tuple。

#### 返回说明

None，不排序或修改调用者对象。

#### 异常说明

TypeError/ValueError为结构、时间、重复ID或观测矛盾。

本函数直接报告的具体错误：

- `TypeError`：condition需要ConditionTick。
- `ValueError`：响应事件缺少已知的点观测证据。
- `TypeError`：同一时刻事件需要Event tuple。
- `ValueError`：事件确认时间与同一时刻组不同。
- `ValueError`：同一角色内事件ID重复。

源码：[`src/chronaxis/core/sequence.py:86`](../../../src/chronaxis/core/sequence.py#L86)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SequenceResult"></a>
## `SequenceResult`

一个请求最终得到的一条配对结果。成功时给出响应和延迟；资料缺失与确实无响应分别保存。

```python
class SequenceResult
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`result_id`|str|是|无|由本次配对内容生成的稳定结果标识。|
|`rule`|[SequenceRule](chronaxis.core.sequence.md#api-SequenceRule)|是|无|产生此结果的SequenceRule，包括允许延迟和两端规则ID。|
|`request`|[Event](chronaxis.core.temporal.md#api-Event)|是|无|被判断的原请求点Event。|
|`response`|[Event](chronaxis.core.temporal.md#api-Event) &#124; None|是|无|匹配到的原响应点Event；未匹配时为None。|
|`status`|str|是|无|matched表示成功；no_response表示完整等满但没有响应；indeterminate表示观测不足。|
|`decided_ns`|int|是|无|作出本次配对结论的纳秒时刻：成功时为响应时刻，超时为截止时刻，观测提前结束则为结束时刻。|
|`delay_ns`|int &#124; None|是|无|成功时response.confirmed_ns减request.confirmed_ns，单位ns；未匹配时为None，不能当0。|
|`observation_quality`|QualityFlag|是|无|等待响应期间遇到的全部未知原因；即使最终配对成功，也保留此前缺失或失效的记录。|

源码：[`src/chronaxis/core/sequence.py:109`](../../../src/chronaxis/core/sequence.py#L109)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SequenceResult-__post_init__"></a>
### `SequenceResult.__post_init__`

拒绝不可能的结果组合，防止把未知观测组装成正常超时。

```python
SequenceResult.__post_init__()
```

参数：无显式参数。


#### 参数说明

无额外参数，读取结果字段。

#### 返回说明

None；不生成事件或写结果文件。

#### 异常说明

TypeError/ValueError/OverflowError为身份、时间或状态矛盾。

本函数直接报告的具体错误：

- `TypeError`：结果需要SequenceRule及QualityFlag。
- `ValueError`：决定时刻超出请求等待范围。
- `ValueError`：匹配时间或延迟与规则不符。
- `ValueError`：未知顺序结果状态。
- `ValueError`：未匹配结果不能包含响应或延迟。
- `ValueError`：no_response需要完整、已知的等待区间。
- `ValueError`：indeterminate必须说明缺失观测原因。

源码：[`src/chronaxis/core/sequence.py:126`](../../../src/chronaxis/core/sequence.py#L126)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
