# `chronaxis.core.temporal`

定义事件检测中使用的条件时间段、单个时刻的条件结果、规则和事件。条件有三种状态：TRUE表示成立，FALSE表示不成立，UNKNOWN表示数据不足以判断，必须同时保存原因。活动的时间范围包含起点、不包含终点；文件读完不等于条件变假。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Interval](chronaxis.core.models.md#api-Interval)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[SourceRef](chronaxis.core.models.md#api-SourceRef)、[Truth](chronaxis.core.types.md#api-Truth)

## 对象导航

|对象|用途|
|---|---|
|[`_require_truth`](#api-_require_truth)|检查条件状态和未知原因是否匹配：已知真或假不应带未知原因，UNKNOWN则必须说明原因。|
|[`ConditionSpan`](#api-ConditionSpan)|保存条件连续成立、不成立或无法确定的一段纳秒区间。|
|[`ConditionSpan.__post_init__`](#api-ConditionSpan-__post_init__)|构造后检查起点早于终点，并核对条件状态与未知原因。缺少的观测不会被补出。|
|[`ConditionTick`](#api-ConditionTick)|保存一个完整时间组的连续状态、点状态及实际更新证据。|
|[`ConditionTick.__post_init__`](#api-ConditionTick-__post_init__)|检查当前时刻的条件结果与更新标志；未单独提供点状态时，按字段默认规则使用连续状态。|
|[`TemporalRule`](#api-TemporalRule)|声明一个数据集会话中的持续条件或边沿检测规则。|
|[`TemporalRule.__post_init__`](#api-TemporalRule-__post_init__)|检查规则的种类、时间范围和时长设置是否相互匹配，时长不能为负数。|
|[`TemporalRule.qualifying_duration_ns`](#api-TemporalRule-qualifying_duration_ns)|返回最早满足比较的整数纳秒时长，不改变用户声明的门槛。|
|[`Event`](#api-Event)|保存一段已确认活动或一个真实触发点，并关联检测规则和原来源。|
|[`Event.__post_init__`](#api-Event-__post_init__)|检查事件起点、确认时刻、终点及来源是否一致。确认时刻可以恰好等于终点，此时从确认开始计算的范围长度为零。|
|[`make_event`](#api-make_event)|根据规则、时间和来源创建事件，并生成稳定标识；相同内容会得到相同标识。|
|[`ConditionTimeline`](#api-ConditionTimeline)|保存一个完整会话的条件时间轴，检测器可以按批消费其中的时间组。|
|[`ConditionTimeline.__post_init__`](#api-ConditionTimeline-__post_init__)|检查时间轴完整性，不填充未知间隙或末周期。|
|[`timeline_from_spans`](#api-timeline_from_spans)|把连续的ConditionSpan时间段转换成检测器使用的ConditionTimeline。适合构造可手算的小例子；最后一段结束只表示观测结束，不额外生成一次“条件变假”。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from hashlib import sha256
from .binding import _identity
from .models import Interval, SourceRef
from .types import QualityFlag as Q, Truth
from .validation import require_identifier, require_text
from ..timebase.conversion import require_int64_ns
```

</details>

<a id="api-_require_truth"></a>
## `_require_truth`

检查条件状态和未知原因是否匹配：已知真或假不应带未知原因，UNKNOWN则必须说明原因。

```python
_require_truth(state, quality)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`state`|[Truth](chronaxis.core.types.md#api-Truth)|是|无|位置或关键字。当前三值状态：TRUE为条件成立，FALSE为不成立，UNKNOWN为数据不足以判断。|
|`quality`|QualityFlag|是|无|位置或关键字。与state配套的质量原因；UNKNOWN需保留实际未知原因，已知状态按规则检查质量组合。|

### 返回说明

检查通过返回None，不改变传入状态。

### 异常说明

state或quality类型不正确时抛TypeError；已知状态带未知原因，或UNKNOWN没有原因时抛ValueError。

本函数直接报告的具体错误：

- `TypeError`：条件需要Truth及QualityFlag。
- `ValueError`：条件truth与quality矛盾。

源码：[`src/chronaxis/core/temporal.py:26`](../../../src/chronaxis/core/temporal.py#L26)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ConditionSpan"></a>
## `ConditionSpan`

保存条件连续成立、不成立或无法确定的一段纳秒区间。

start_ns包含起点，end_ns排除终点；区间必须为正长度且跨度可由int64表示。
state和quality共同说明条件及未知原因。模型不可变，不根据消息周期补齐间隙。

```python
class ConditionSpan
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`start_ns`|int|是|无|时间段的起点，整数纳秒。起点包含在时间段内，且必须早于end_ns。|
|`end_ns`|int|是|无|时间段的终点，整数纳秒。终点本身不包含在时间段内；例如0到2秒表示[0,2)，第2秒属于下一段。|
|`state`|[Truth](chronaxis.core.types.md#api-Truth)|是|无|条件的状态，填写Truth.TRUE（成立）、Truth.FALSE（不成立）或Truth.UNKNOWN（数据不足以判断）。该状态适用于start_ns到end_ns之间，包含起点、不包含终点。|
|`quality`|[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)|否|Q.NONE|条件未知的原因，使用QualityFlag标记，可以用按位或组合多个原因。state为TRUE或FALSE时使用QualityFlag.NONE；state为UNKNOWN时必须提供非NONE原因，例如MISSING表示缺少数据。|

源码：[`src/chronaxis/core/temporal.py:44`](../../../src/chronaxis/core/temporal.py#L44)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ConditionSpan-__post_init__"></a>
### `ConditionSpan.__post_init__`

构造后检查起点早于终点，并核对条件状态与未知原因。缺少的观测不会被补出。

```python
ConditionSpan.__post_init__()
```

参数：无显式参数。


#### 参数说明

无；读取四个字段。

#### 返回说明

None，保持原声明。

#### 异常说明

TypeError/ValueError/OverflowError为结构/区间/质量。

本函数直接报告的具体错误：

- `ValueError`：ConditionSpan需正长度。

源码：[`src/chronaxis/core/temporal.py:56`](../../../src/chronaxis/core/temporal.py#L56)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ConditionTick"></a>
## `ConditionTick`

保存一个完整时间组的连续状态、点状态及实际更新证据。

state描述从当前时刻到下一时刻的连续状态；point_state描述当前点，包括真实
末点。actual_unknown表示真实更新明确导致点结果未知，用于区分实际中断与
同一时刻发生的有效期到期。observation_end和terminal分别表示依赖来源及会话
观测结束。字段不可变，默认点状态继承连续状态，不制造实际更新。

```python
class ConditionTick
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|这一组条件结果对应的时刻，单位为整数纳秒。相同时间的输入更新应先收齐，再生成一个ConditionTick。|
|`state`|[Truth](chronaxis.core.types.md#api-Truth)|是|无|条件的状态，填写Truth.TRUE（成立）、Truth.FALSE（不成立）或Truth.UNKNOWN（数据不足以判断）。本字段描述从当前时刻到下一时刻之间的状态；当前时刻本身使用point_state。|
|`quality`|[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)|否|Q.NONE|条件未知的原因，使用QualityFlag标记，可以用按位或组合多个原因。state为TRUE或FALSE时使用QualityFlag.NONE；state为UNKNOWN时必须提供非NONE原因，例如MISSING表示缺少数据。|
|`actual_update`|bool|否|True|完整组确有条件依赖更新/明确条件证据。|
|`observation_end`|bool|否|False|当前有依赖来源观测结束。|
|`terminal`|bool|否|False|当前会话真实连续终点，只能全输入末组。|
|`point_state`|[Truth](chronaxis.core.types.md#api-Truth) &#124; None|否|None|None表示与continuous同证据。|
|`point_quality`|[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag) &#124; None|否|None|None采用continuous质量。|
|`actual_unknown`|bool|否|False|实际无效/实际更新导致未知，优先interrupted。|
|`diagnostic_quality`|[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)|否|Q.NONE|全部依赖和边界原因，保留原异常诊断。|

源码：[`src/chronaxis/core/temporal.py:74`](../../../src/chronaxis/core/temporal.py#L74)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ConditionTick-__post_init__"></a>
### `ConditionTick.__post_init__`

检查当前时刻的条件结果与更新标志；未单独提供点状态时，按字段默认规则使用连续状态。

```python
ConditionTick.__post_init__()
```

参数：无显式参数。


#### 参数说明

无，读取上述字段。

#### 返回说明

None，默认point只继承显式state，不制造新更新。

#### 异常说明

TypeError/ValueError为类型、状态或实际未知证据冲突。

本函数直接报告的具体错误：

- `TypeError`：diagnostic_quality需要QualityFlag。
- `ValueError`：actual_unknown需实际更新且点UNKNOWN。
- `TypeError`：时序证据标志需bool。

源码：[`src/chronaxis/core/temporal.py:94`](../../../src/chronaxis/core/temporal.py#L94)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-TemporalRule"></a>
## `TemporalRule`

声明一个数据集会话中的持续条件或边沿检测规则。

rule_type接受condition_duration、rising_edge、falling_edge和start_only。minimum_duration_ns是非负int64阈值，
边沿规则必须为0；rising_edge/start_only可用emit_initial输出首次已知TRUE初始化点。
start_only的window_duration_ns必须为正，真实触发后的固定时长内抑制新边沿。
对象不可变，只保存配置，不初始化检测器状态。

```python
class TemporalRule
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`rule_id`|str|是|无|稳定规则ID，与同名不同会话隔离。|
|`dataset_id`|str|是|无|事件ID范围，不按秒数命名。|
|`session_id`|str|是|无|当前分析会话。|
|`rule_type`|str|是|无|选择底层事件检测方法：condition_duration记录持续成立的活动，rising_edge记录由假变真，falling_edge记录由真变假，start_only在触发后的窗口内抑制重复点。其他公共规则由专用组件处理，不能直接传给此类。|
|`minimum_duration_ns`|int|否|0|condition_duration阈值；edge必须0。|
|`emit_initial`|bool|否|False|rising_edge/start_only首次已知TRUE初始化策略。|
|`window_duration_ns`|int|否|0|仅start_only的固定抑制时长，其他模式必须0。|
|`duration_comparison`|str|否|'>='|持续时长比较符：>=表示达到minimum_duration，>表示严格超过；此底层Python对象默认>=；用户配置中的condition_duration必须显式填写比较符。仅condition_duration使用。实际时间模式按整数纳秒比较，固定/DBC模式随所选报文推进；不改变onset/confirmed的积分起点选择。|

源码：[`src/chronaxis/core/temporal.py:128`](../../../src/chronaxis/core/temporal.py#L128)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-TemporalRule-__post_init__"></a>
### `TemporalRule.__post_init__`

检查规则的种类、时间范围和时长设置是否相互匹配，时长不能为负数。

```python
TemporalRule.__post_init__()
```

参数：无显式参数。


#### 参数说明

无，读取规则字段。

#### 返回说明

None，不初始化任何全局运行状态。

#### 异常说明

TypeError/ValueError/OverflowError为配置错误。

本函数直接报告的具体错误：

- `ValueError`：非法首版时序规则/阈值/初始化策略。
- `ValueError`：规则参数与kind不匹配。
- `ValueError`：window_duration_ns仅且必须用于正时长start_only。

源码：[`src/chronaxis/core/temporal.py:146`](../../../src/chronaxis/core/temporal.py#L146)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-TemporalRule-qualifying_duration_ns"></a>
### `TemporalRule.qualifying_duration_ns`

返回最早满足比较的整数纳秒时长，不改变用户声明的门槛。

```python
TemporalRule.qualifying_duration_ns
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

Python整数；严格大于最大int64时可超出int64，表示域内不可达到。

#### 异常说明

无。时间模型精度为1ns，因此>60s的首个可表示时长为60000000001ns；
这不是把用户阈值粗略提高到60.1秒，固定/DBC模式仍只随实际驱动记录确认。

源码：[`src/chronaxis/core/temporal.py:177`](../../../src/chronaxis/core/temporal.py#L177)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-Event"></a>
## `Event`

保存一段已确认活动或一个真实触发点，并关联检测规则和原来源。

point事件的start_ns等于confirmed_ns，end_ns为None，status为point。
activity事件为正长度左闭右开区间；confirmed_ns可以恰好等于end_ns。
活动的closed表示条件已知结束，interrupted表示连续性中断，truncated表示
观测结束而没有实际结束证据。边界、质量、诊断和来源引用均不可变。
timeout表示开始/结束规则在结束条件可判断时达到时限，结束质量必须为NONE。

```python
class Event
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`event_id`|str|是|无|按稳定内容SHA，不依批次/遍历次序。|
|`rule`|[TemporalRule](chronaxis.core.temporal.md#api-TemporalRule)|是|无|完整规则及dataset/session身份。|
|`event_type`|str|是|无|`"activity"`表示持续的一段活动，有开始和结束范围；`"point"`表示一个触发时刻，不据此推断持续了多久。|
|`start_ns`|int|是|无|真实onset或点时间。|
|`confirmed_ns`|int|是|无|精确门槛时间，不当活动起点。|
|`end_ns`|int &#124; None|是|无|point为None，activity结束边界。|
|`status`|str|是|无|`closed`：结束条件明确成立；`timeout`：开始后达到时限仍未正常结束；`interrupted`：所需数据失效，无法再判断活动；`truncated`：观测或请求范围结束时活动尚未正常结束；`point`：这是一次瞬间触发，没有持续结束点。|
|`trigger_kind`|str|是|无|condition_duration/rising_edge/falling_edge/initial。|
|`quality`|[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)|是|无|结束原因质量，不用0恢复失败。|
|`dependency_quality`|[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)|是|无|期间及结束证据的完整诊断。|
|`source_refs`|tuple[[SourceRef](chronaxis.core.models.md#api-SourceRef), ...]|否|()|真实绑定原来源定位，合成span可空。|

源码：[`src/chronaxis/core/temporal.py:188`](../../../src/chronaxis/core/temporal.py#L188)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-Event-__post_init__"></a>
### `Event.__post_init__`

检查事件起点、确认时刻、终点及来源是否一致。确认时刻可以恰好等于终点，此时从确认开始计算的范围长度为零。

```python
Event.__post_init__()
```

参数：无显式参数。


#### 参数说明

无，读取事件字段。

#### 返回说明

None，不修改边界或生成片段。

#### 异常说明

TypeError/ValueError/OverflowError为事件结构/时间/身份错误。

本函数直接报告的具体错误：

- `TypeError`：Event字段需带有明确类型的模型。
- `ValueError`：timeout不能带未知结束质量。
- `ValueError`：start_only点触发种类与规则不匹配。
- `ValueError`：point事件边界/类型矛盾。
- `ValueError`：activity事件结构非法。
- `ValueError`：activity确认/连续边界矛盾。
- `ValueError`：Event来源与session不一致。

源码：[`src/chronaxis/core/temporal.py:210`](../../../src/chronaxis/core/temporal.py#L210)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-make_event"></a>
## `make_event`

根据规则、时间和来源创建事件，并生成稳定标识；相同内容会得到相同标识。

```python
make_event(rule, start_ns, confirmed_ns, end_ns, status, quality, diagnostic, refs=(), *, trigger='condition_duration') -> Event
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`rule`|[TemporalRule](chronaxis.core.temporal.md#api-TemporalRule)|是|无|位置或关键字。当前检测规则，包含数据集和会话身份。 start、confirmed (int): 活动起点和确认时间，或触发点时间，单位为纳秒。|
|`start_ns`|int|是|无|位置或关键字。活动条件第一次成立的纳秒时刻；点事件为触发时刻。|
|`confirmed_ns`|int|是|无|位置或关键字。条件满足所需持续时长的纳秒时刻；没有等待时长的点事件与start相同。|
|`end_ns`|int &#124; None|是|无|位置或关键字。活动结束时间，单位为纳秒；点事件使用None。|
|`status`|str|是|无|位置或关键字。closed、timeout、interrupted、truncated或point。 quality、diagnostic (QualityFlag): 结束质量和完整依赖诊断。|
|`quality`|QualityFlag|是|无|位置或关键字。事件结束时的质量标记，例如因缺失数据中断时保留MISSING；NONE表示结束本身没有异常。|
|`diagnostic`|QualityFlag|是|无|位置或关键字。事件依赖信号的完整质量原因组合，包括未改变最终布尔判断的异常；与结束质量分别保留。|
|`refs`|tuple[[SourceRef](chronaxis.core.models.md#api-SourceRef), ...]|否|()|位置或关键字。当前实际来源引用，默认空tuple。|
|`trigger`|str|否|'condition_duration'|仅关键字。触发种类，默认duration，边沿或初始化点另行声明。|

### 返回说明

Event: 通过模型检查的事件。标识由规则及时间事实生成，不受批次切分、
    质量诊断或可选语义元数据变化影响。

### 异常说明

TypeError、ValueError或OverflowError: 事件模型或身份材料不符合约束。

### 副作用说明

无，不加载来源，不修改规则或检测器状态。

返回类型：[Event](chronaxis.core.temporal.md#api-Event)。

源码：[`src/chronaxis/core/temporal.py:258`](../../../src/chronaxis/core/temporal.py#L258)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ConditionTimeline"></a>
## `ConditionTimeline`

保存一个完整会话的条件时间轴，检测器可以按批消费其中的时间组。

首末时间组必须对应start_ns和end_ns；最后一组是唯一的terminal。时间严格
递增，同一时刻更新已经归并；模型不会排序或补齐缺口。source_refs保存原来源，
与规则会话的归属关系由检测器检查。批次切分不改变条件证据。

```python
class ConditionTimeline
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`start_ns`|int|是|无|连续分析起点。|
|`end_ns`|int|是|无|连续分析终点，真实点仍可观察。|
|`ticks`|tuple[[ConditionTick](chronaxis.core.temporal.md#api-ConditionTick), ...]|是|无|完整时间组，含TTL/source/EOF证据。|
|`source_refs`|tuple[[SourceRef](chronaxis.core.models.md#api-SourceRef), ...]|否|()|实际condition依赖源定位。|

源码：[`src/chronaxis/core/temporal.py:292`](../../../src/chronaxis/core/temporal.py#L292)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ConditionTimeline-__post_init__"></a>
### `ConditionTimeline.__post_init__`

检查时间轴完整性，不填充未知间隙或末周期。

```python
ConditionTimeline.__post_init__()
```

参数：无显式参数。


#### 参数说明

无，读取domain/ticks/source_refs。

#### 返回说明

None，保持显式时间证据。

#### 异常说明

TypeError/ValueError/OverflowError为结构/边界/顺序。

本函数直接报告的具体错误：

- `TypeError`：timeline需非空tuple ticks及tuple refs。
- `TypeError`：timeline需要ConditionTick。
- `ValueError`：timeline首末/terminal与domain不一致。
- `TypeError`：timeline source_refs需SourceRef。
- `ValueError`：timeline中途terminal/时间回退/重复组。

源码：[`src/chronaxis/core/temporal.py:305`](../../../src/chronaxis/core/temporal.py#L305)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-timeline_from_spans"></a>
## `timeline_from_spans`

把连续的ConditionSpan时间段转换成检测器使用的ConditionTimeline。适合构造可手算的小例子；最后一段结束只表示观测结束，不额外生成一次“条件变假”。

```python
timeline_from_spans(spans: tuple[ConditionSpan, ...], *, terminal_state: Truth | None=None, terminal_quality: Q=Q.NONE, terminal_actual: bool=False) -> ConditionTimeline
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spans`|tuple[[ConditionSpan](chronaxis.core.temporal.md#api-ConditionSpan), ...]|是|无|位置或关键字。spans为正长度、相邻、完整tuple|
|`terminal_state`|[Truth](chronaxis.core.types.md#api-Truth) &#124; None|否|None|仅关键字。可选的真实末点状态；None使用已有历史末点状态，不虚构新的更新。|
|`terminal_quality`|[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)|否|Q.NONE|仅关键字。真实末点的质量位，与terminal_state一起解释末点是否有效；不会制造EOF为False。|
|`terminal_actual`|bool|否|False|仅关键字。末点是否实际收到新样本；False表示仅用于结束时间轴的边界。|

### 返回说明

ConditionTimeline；末端continuous UNKNOWN/MISSING，仅point保留证据。

### 异常说明

TypeError/ValueError为结构/缺口/point更新声明矛盾。

本函数直接报告的具体错误：

- `TypeError`：spans需要非空tuple ConditionSpan。
- `ValueError`：terminal_actual需明确terminal_state。
- `ValueError`：ConditionSpan需完整相邻，不自动填充。

返回类型：[ConditionTimeline](chronaxis.core.temporal.md#api-ConditionTimeline)。

源码：[`src/chronaxis/core/temporal.py:338`](../../../src/chronaxis/core/temporal.py#L338)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
