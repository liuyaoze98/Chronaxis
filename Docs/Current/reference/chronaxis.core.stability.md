# `chronaxis.core.stability`

根据一个条件进行防抖，或根据两个条件进行迟滞报警。计时跨数据批次保持，数据未知会中断活动；详见[规则例子](../rules.md)。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ConditionTick](chronaxis.core.temporal.md#api-ConditionTick)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ReferenceTemporalDetector](chronaxis.core.temporal_reference.md#api-ReferenceTemporalDetector)、[Truth](chronaxis.core.types.md#api-Truth)

## 对象导航

|对象|用途|
|---|---|
|[`StabilitySpec`](#api-StabilitySpec)|保存进入和退出的独立等待时长；0表示条件满足即可转换。|
|[`StabilitySpec.__post_init__`](#api-StabilitySpec-__post_init__)|拒绝负值、bool及超int64时长。|
|[`invert_tick`](#api-invert_tick)|取得普通防抖条件的退出证据，UNKNOWN保留原原因。|
|[`StabilityDetector`](#api-StabilityDetector)|维护一个规则/会话的已确定状态、单个待转换候选及活动输出。|
|[`StabilityDetector.__init__`](#api-StabilityDetector-__init__)|建立独立迟滞状态，复用零时长活动检测器。|
|[`StabilityDetector._push_core`](#api-StabilityDetector-_push_core)|把已确认状态交给活动核，并按需累计左侧半开区间。|
|[`StabilityDetector.duration_counts`](#api-StabilityDetector-duration_counts)|读取完成后的已知报警/已知观测整数纳秒。|
|[`StabilityDetector.next_deadline_ns`](#api-StabilityDetector-next_deadline_ns)|读取域内待转换时间。|
|[`StabilityDetector._target`](#api-StabilityDetector-_target)|区分明确方向、中间区间、未知与矛盾条件。|
|[`StabilityDetector._settle`](#api-StabilityDetector-_settle)|兑现已持续达到门槛的转换。|
|[`StabilityDetector._point`](#api-StabilityDetector-_point)|判断当前点状态，不把零长度点累计到等待时间。|
|[`StabilityDetector._continuous`](#api-StabilityDetector-_continuous)|更新右侧持续状态和唯一候选，取消不连续的计时。|
|[`StabilityDetector.push`](#api-StabilityDetector-push)|推进成对条件组，可在两次实际更新之间精确兑现防抖计时。|
|[`StabilityDetector.drain_events`](#api-StabilityDetector-drain_events)|取走最终活动而不清计时。|
|[`StabilityDetector.finish`](#api-StabilityDetector-finish)|只在真实会话末尾封闭。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass, replace
from .temporal import ConditionTick
from .temporal_reference import ReferenceTemporalDetector, require_batch, require_detector
from .types import QualityFlag as Q, Truth
from ..timebase.conversion import require_int64_ns
```

</details>

<a id="api-StabilitySpec"></a>
## `StabilitySpec`

保存进入和退出的独立等待时长；0表示条件满足即可转换。

状态属于运行实例，本声明不保存已报警标志或候选计时。

```python
class StabilitySpec
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`enter_ns`|int|否|0|进入条件连续满足多久才切换为活动。|
|`exit_ns`|int|否|0|退出条件连续满足多久才切换为非活动。|
|`track_duration`|bool|否|False|仅显式需求累计，普通规则不增加逐步统计。|

源码：[`src/chronaxis/core/stability.py:19`](../../../src/chronaxis/core/stability.py#L19)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-StabilitySpec-__post_init__"></a>
### `StabilitySpec.__post_init__`

拒绝负值、bool及超int64时长。

```python
StabilitySpec.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

类型/范围错误。

本函数直接报告的具体错误：

- `TypeError`：track_duration必须bool。
- `ValueError`：防抖时长不能为负。

源码：[`src/chronaxis/core/stability.py:29`](../../../src/chronaxis/core/stability.py#L29)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-invert_tick"></a>
## `invert_tick`

取得普通防抖条件的退出证据，UNKNOWN保留原原因。

```python
invert_tick(tick)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`tick`|[ConditionTick](chronaxis.core.temporal.md#api-ConditionTick)|是|无|位置或关键字。tick为ConditionTick。|

### 返回说明

点/连续状态分别取反的新证据。

### 异常说明

TypeError为非ConditionTick；不修改输入。

本函数直接报告的具体错误：

- `TypeError`：防抖条件需要ConditionTick。

源码：[`src/chronaxis/core/stability.py:40`](../../../src/chronaxis/core/stability.py#L40)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-StabilityDetector"></a>
## `StabilityDetector`

维护一个规则/会话的已确定状态、单个待转换候选及活动输出。

未知起点不猜未报警；两条件都假时保持前态，二者同时为真则报告配置冲突。
一个条件未知会中断活动；恢复时从未知开始重新确认，不能跨缺口累计防抖。
每次push可有多组，只有真实terminal才能finish；drain只取走输出。

```python
StabilityDetector(rule, start_ns, end_ns, spec, source_refs=(), *, backend='reference', record_clock=False)
```


源码：[`src/chronaxis/core/stability.py:52`](../../../src/chronaxis/core/stability.py#L52)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-StabilityDetector-__init__"></a>
### `StabilityDetector.__init__`

建立独立迟滞状态，复用零时长活动检测器。

```python
StabilityDetector.__init__(rule, start_ns, end_ns, spec, source_refs=(), *, backend='reference', record_clock=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`rule`|TemporalRule|是|无|位置或关键字。rule为duration=0规则|
|`start_ns`|int|是|无|位置或关键字。本次会话范围的开始时间，单位为整数纳秒；start_ns不能晚于end_ns。检测器到结束边界停止累计，不把后续无记录时间算进活动。|
|`end_ns`|int|是|无|位置或关键字。本次会话范围的结束时间，单位为整数纳秒；start_ns不能晚于end_ns。检测器到结束边界停止累计，不把后续无记录时间算进活动。|
|`spec`|[StabilitySpec](chronaxis.core.stability.md#api-StabilitySpec)|是|无|位置或关键字。spec为StabilitySpec|
|`source_refs`|tuple[SourceRef, ...]|否|()|位置或关键字。本次事件依赖的原始数据位置。空元组表示没有附加来源定位，不影响事件的开始和结束时间。|
|`backend`|str|否|'reference'|仅关键字。backend为reference或numpy。|
|`record_clock`|bool|否|False|仅关键字。True按实际记录带来的累计步进处理时限；False沿日志真实时间推进，不另存完整计算时间轴。|

#### 返回说明

None；初始化实例状态。

#### 异常说明

规则、域、类型或后端错误。

本函数直接报告的具体错误：

- `ValueError`：迟滞需要StabilitySpec及duration=0活动规则。
- `ValueError`：迟滞后端需reference或numpy。

源码：[`src/chronaxis/core/stability.py:60`](../../../src/chronaxis/core/stability.py#L60)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-StabilityDetector-_push_core"></a>
### `StabilityDetector._push_core`

把已确认状态交给活动核，并按需累计左侧半开区间。

```python
StabilityDetector._push_core(tick, advance=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`tick`|[ConditionTick](chronaxis.core.temporal.md#api-ConditionTick)|是|无|位置或关键字。迟滞和去抖处理后的一步条件证据，交给基础持续条件检测器产生事件。|
|`advance`|int|否|None|位置或关键字。当前完整时间组增加的所选计时纳秒数；所选报文到达才增加周期，其他边界为0。|

#### 返回说明

原活动核Event tuple。

#### 异常说明

原活动核校验错误；失败实例不能继续使用。

源码：[`src/chronaxis/core/stability.py:88`](../../../src/chronaxis/core/stability.py#L88)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-StabilityDetector-duration_counts"></a>
### `StabilityDetector.duration_counts`

读取完成后的已知报警/已知观测整数纳秒。

```python
StabilityDetector.duration_counts
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

(active_ns,known_ns)或None（未请求统计）。

#### 异常说明

ValueError表示请求统计但尚未正常finish。

本函数直接报告的具体错误：

- `ValueError`：迟滞累计只能在finish后读取。

源码：[`src/chronaxis/core/stability.py:104`](../../../src/chronaxis/core/stability.py#L104)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-StabilityDetector-next_deadline_ns"></a>
### `StabilityDetector.next_deadline_ns`

读取域内待转换时间。

```python
StabilityDetector.next_deadline_ns
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

int或None。

#### 异常说明

无。

加法使用Python整数，域外结果不转换为int64或回绕。

源码：[`src/chronaxis/core/stability.py:117`](../../../src/chronaxis/core/stability.py#L117)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-StabilityDetector-_target"></a>
### `StabilityDetector._target`

区分明确方向、中间区间、未知与矛盾条件。

```python
StabilityDetector._target(enter, exit, quality)
```

装饰器：`staticmethod`。

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`enter`|[Truth](chronaxis.core.types.md#api-Truth)|是|无|位置或关键字。当前进入条件：TRUE满足，FALSE不满足，UNKNOWN表示缺数据、无法判断。|
|`exit`|[Truth](chronaxis.core.types.md#api-Truth)|是|无|位置或关键字。当前退出条件的三值结果；与enter一起结合已有状态决定是否开始确认进入或退出。|
|`quality`|QualityFlag|是|无|位置或关键字。本步的质量标记，可用按位或组合MISSING、NONFINITE等原因；NONE表示没有这些异常。全部标记见[结果说明](../results.md)。|

#### 返回说明

Truth或None（中间区间）。

#### 异常说明

ValueError为同时满足进出条件。

本函数直接报告的具体错误：

- `ValueError`：迟滞进入和退出条件同时成立，请设置不重叠的条件。

源码：[`src/chronaxis/core/stability.py:125`](../../../src/chronaxis/core/stability.py#L125)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-StabilityDetector-_settle"></a>
### `StabilityDetector._settle`

兑现已持续达到门槛的转换。

```python
StabilityDetector._settle()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

无。

源码：[`src/chronaxis/core/stability.py:141`](../../../src/chronaxis/core/stability.py#L141)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-StabilityDetector-_point"></a>
### `StabilityDetector._point`

判断当前点状态，不把零长度点累计到等待时间。

```python
StabilityDetector._point(target, quality)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`target`|[Truth](chronaxis.core.types.md#api-Truth) &#124; None|是|无|位置或关键字。TRUE表示进入活动状态，FALSE表示退出，UNKNOWN表示条件数据不足；None表示落在迟滞上下阈值之间，保持先前状态。|
|`quality`|QualityFlag|是|无|位置或关键字。本步的质量标记，可用按位或组合MISSING、NONFINITE等原因；NONE表示没有这些异常。全部标记见[结果说明](../results.md)。|

#### 返回说明

(Truth,Q)。

#### 异常说明

无。

源码：[`src/chronaxis/core/stability.py:147`](../../../src/chronaxis/core/stability.py#L147)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-StabilityDetector-_continuous"></a>
### `StabilityDetector._continuous`

更新右侧持续状态和唯一候选，取消不连续的计时。

```python
StabilityDetector._continuous(target, quality, time_ns)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`target`|[Truth](chronaxis.core.types.md#api-Truth) &#124; None|是|无|位置或关键字。TRUE表示进入活动状态，FALSE表示退出，UNKNOWN表示条件数据不足；None表示落在迟滞上下阈值之间，保持先前状态。|
|`quality`|QualityFlag|是|无|位置或关键字。本步的质量标记，可用按位或组合MISSING、NONFINITE等原因；NONE表示没有这些异常。全部标记见[结果说明](../results.md)。|
|`time_ns`|int|是|无|位置或关键字。当前计算时刻，单位为纳秒；推进检测器时不能早于上一次已处理的时刻。|

#### 返回说明

None，修改实例。

#### 异常说明

无；超域deadline仅用于比较。

源码：[`src/chronaxis/core/stability.py:160`](../../../src/chronaxis/core/stability.py#L160)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-StabilityDetector-push"></a>
### `StabilityDetector.push`

推进成对条件组，可在两次实际更新之间精确兑现防抖计时。

```python
StabilityDetector.push(ticks, exit_ticks=None, *, advances=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`ticks`|tuple|是|无|位置或关键字。ticks为进入条件tuple|
|`exit_ticks`|tuple &#124; None|否|None|位置或关键字。exit_ticks为同一时刻退出tuple，省略时为not进入。|
|`advances`|tuple[int, ...] &#124; None|否|None|仅关键字。与本批完整时间组等长的非负计时增量；固定/DBC模式首组为0，实际时间模式必须为None。|

#### 返回说明

本次新Event tuple；活动起点为进入转换时刻，不回填等待区间。

#### 异常说明

输入/顺序/同一时刻冲突/finish后推进错误；发生错误后调用方应丢弃实例。

本函数直接报告的具体错误：

- `ValueError`：迟滞检测器已finish。
- `ValueError`：迟滞两个条件必须在相同的完整时间组求值。

源码：[`src/chronaxis/core/stability.py:182`](../../../src/chronaxis/core/stability.py#L182)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-StabilityDetector-drain_events"></a>
### `StabilityDetector.drain_events`

取走最终活动而不清计时。

```python
StabilityDetector.drain_events()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

Event tuple。

#### 异常说明

分配错误。

源码：[`src/chronaxis/core/stability.py:241`](../../../src/chronaxis/core/stability.py#L241)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-StabilityDetector-finish"></a>
### `StabilityDetector.finish`

只在真实会话末尾封闭。

```python
StabilityDetector.finish()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

未取走活动。

#### 异常说明

缺terminal/重复。

源码：[`src/chronaxis/core/stability.py:245`](../../../src/chronaxis/core/stability.py#L245)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
