# `chronaxis.core.start_end`

从开始条件到结束条件记录活动，并区分超时与缺观测。

输入是同一会话中按时间严格递增的两组ConditionTick。开始采用已知上升沿，
可选择首次已知TRUE也启动；活动期间只等待结束条件或时限，不排队重复开始。
输出沿用正长度Event，status=timeout表示在可判断的结束条件下等到时限。
UNKNOWN/真实失效与EOF继续区分interrupted/truncated，不能凭缺数据判超时。
这是有界有序状态转换，不读取来源、不保留全量历史，也不属于数值数组核。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[T](chronaxis.core.types.md#api-Truth)

## 对象导航

|对象|用途|
|---|---|
|[`StartEndSpec`](#api-StartEndSpec)|保存最长等待时长与首次启动策略；None明确表示不限时。|
|[`StartEndSpec.__post_init__`](#api-StartEndSpec-__post_init__)|拒绝零/负时限及假布尔。|
|[`StartEndDetector`](#api-StartEndDetector)|为单个规则保存至多一段活动和开始条件前态；批次边界不重置。|
|[`StartEndDetector.__init__`](#api-StartEndDetector-__init__)|建立独立的活动状态，规则沿用condition_duration=0输出模型。|
|[`StartEndDetector.next_deadline_ns`](#api-StartEndDetector-next_deadline_ns)|提供域内时限供时间线推进。|
|[`StartEndDetector._close`](#api-StartEndDetector-_close)|保存有正长度的活动后清理计时，绝不延长零长度点。|
|[`StartEndDetector._unknown_status`](#api-StartEndDetector-_unknown_status)|按真实失效与观测结束区分原因。|
|[`StartEndDetector._advance`](#api-StartEndDetector-_advance)|推进一个完整时间组，先补精确时限，再处理实际结束和新开始。|
|[`StartEndDetector.push`](#api-StartEndDetector-push)|处理同一时间范围内成对到达的开始条件与结束条件；同一时刻的两种条件必须一起提供。|
|[`StartEndDetector.drain_events`](#api-StartEndDetector-drain_events)|转交当前输出，不清活动状态。|
|[`StartEndDetector.finish`](#api-StartEndDetector-finish)|仅在已收到真实末组后封闭。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from .temporal import make_event
from .temporal_reference import require_batch, require_detector
from .types import QualityFlag as Q, Truth as T
from ..timebase.conversion import require_int64_ns
```

</details>

<a id="api-StartEndSpec"></a>
## `StartEndSpec`

保存最长等待时长与首次启动策略；None明确表示不限时。

```python
class StartEndSpec
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`timeout_ns`|int &#124; None|否|None|从开始时刻算起；正纳秒或显式不限时。 None表示不设置超时上限，等待结束条件或实际观测结束。|
|`emit_initial`|bool|否|True|首次已知开始条件为TRUE时允许启动。|

源码：[`src/chronaxis/core/start_end.py:18`](../../../src/chronaxis/core/start_end.py#L18)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-StartEndSpec-__post_init__"></a>
### `StartEndSpec.__post_init__`

拒绝零/负时限及假布尔。

```python
StartEndSpec.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

类型/范围错误。

本函数直接报告的具体错误：

- `TypeError`：emit_initial必须为bool。
- `ValueError`：start_end时限必须为正或None。

源码：[`src/chronaxis/core/start_end.py:24`](../../../src/chronaxis/core/start_end.py#L24)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-StartEndDetector"></a>
## `StartEndDetector`

为单个规则保存至多一段活动和开始条件前态；批次边界不重置。

活动中忽略重复开始；首次真实结束优先同一时刻时限。结束条件未知会终止已知
活动，恢复后需要新的开始边沿；当前开始和结束同时成立不制造零长度活动。
source_refs在构造时固定，输出可drain移交，未移交事件才留在实例中。

```python
StartEndDetector(rule, start_ns, end_ns, spec, source_refs=(), *, backend='reference', record_clock=False)
```


源码：[`src/chronaxis/core/start_end.py:35`](../../../src/chronaxis/core/start_end.py#L35)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-StartEndDetector-__init__"></a>
### `StartEndDetector.__init__`

建立独立的活动状态，规则沿用condition_duration=0输出模型。

```python
StartEndDetector.__init__(rule, start_ns, end_ns, spec, source_refs=(), *, backend='reference', record_clock=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`rule`|TemporalRule|是|无|位置或关键字。rule为TemporalRule|
|`start_ns`|int|是|无|位置或关键字。本次会话范围的开始时间，单位为整数纳秒；start_ns不能晚于end_ns。检测器到结束边界停止累计，不把后续无记录时间算进活动。|
|`end_ns`|int|是|无|位置或关键字。本次会话范围的结束时间，单位为整数纳秒；start_ns不能晚于end_ns。检测器到结束边界停止累计，不把后续无记录时间算进活动。|
|`spec`|[StartEndSpec](chronaxis.core.start_end.md#api-StartEndSpec)|是|无|位置或关键字。spec为StartEndSpec|
|`source_refs`|tuple[SourceRef, ...]|否|()|位置或关键字。本次事件依赖的原始数据位置。空元组表示没有附加来源定位，不影响事件的开始和结束时间。|
|`backend`|str|否|'reference'|仅关键字。`"reference"`使用独立参考计算；`"numpy"`使用NumPy数组计算。须明确选择一种。|
|`record_clock`|bool|否|False|仅关键字。True按实际记录带来的累计步进处理时限；False沿日志真实时间推进，不另存完整计算时间轴。|

#### 返回说明

None；初始化实例状态。

#### 异常说明

规则/范围/参数错误。状态算法没有数值后端分叉。

本函数直接报告的具体错误：

- `ValueError`：start_end需要StartEndSpec和duration=0输出规则。
- `ValueError`：start_end后端需reference或numpy。

源码：[`src/chronaxis/core/start_end.py:43`](../../../src/chronaxis/core/start_end.py#L43)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-StartEndDetector-next_deadline_ns"></a>
### `StartEndDetector.next_deadline_ns`

提供域内时限供时间线推进。

```python
StartEndDetector.next_deadline_ns
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

int或None。

#### 异常说明

无。

源码：[`src/chronaxis/core/start_end.py:67`](../../../src/chronaxis/core/start_end.py#L67)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-StartEndDetector-_close"></a>
### `StartEndDetector._close`

保存有正长度的活动后清理计时，绝不延长零长度点。

```python
StartEndDetector._close(time_ns, status, quality=Q.NONE)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int &#124; None|是|无|位置或关键字。time_ns结束纳秒|
|`status`|str|是|无|位置或关键字。status/quality表示实际结束原因。|
|`quality`|QualityFlag|否|Q.NONE|位置或关键字。本步的质量标记，可用按位或组合MISSING、NONFINITE等原因；NONE表示没有这些异常。全部标记见[结果说明](../results.md)。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

Event结构或分配错误；失败后调用方丢弃实例。

源码：[`src/chronaxis/core/start_end.py:71`](../../../src/chronaxis/core/start_end.py#L71)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-StartEndDetector-_unknown_status"></a>
### `StartEndDetector._unknown_status`

按真实失效与观测结束区分原因。

```python
StartEndDetector._unknown_status(end_condition)
```

装饰器：`staticmethod`。

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`end_condition`|ConditionTick|是|无|位置或关键字。结束条件在当前时刻的证据；由其中的未知或观测终止原因决定事件结束状态。|

#### 返回说明

str。

#### 异常说明

无。

源码：[`src/chronaxis/core/start_end.py:85`](../../../src/chronaxis/core/start_end.py#L85)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-StartEndDetector-_advance"></a>
### `StartEndDetector._advance`

推进一个完整时间组，先补精确时限，再处理实际结束和新开始。

```python
StartEndDetector._advance(start_condition, end_condition, advance=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`start_condition`|ConditionTick|是|无|位置或关键字。当前时刻的开始条件证据，含更新前、连续时间和点时刻状态。|
|`end_condition`|ConditionTick|是|无|位置或关键字。同一时刻的结束条件证据，用来决定已有活动是否正常结束；须与start时刻一致。|
|`advance`|int|否|None|位置或关键字。当前完整时间组增加的所选计时纳秒数；所选报文到达才增加周期，其他边界为0。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

输出构造错误。

#### 边界说明

跨过时限前未出现其它组，表示此前连续结束条件已知不成立；
同一时刻未知则不能证明截止点没有end_condition，保留未知/EOF原因。

源码：[`src/chronaxis/core/start_end.py:90`](../../../src/chronaxis/core/start_end.py#L90)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-StartEndDetector-push"></a>
### `StartEndDetector.push`

处理同一时间范围内成对到达的开始条件与结束条件；同一时刻的两种条件必须一起提供。

```python
StartEndDetector.push(ticks, end_ticks, *, advances=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`ticks`|tuple[ConditionTick, ...]|是|无|位置或关键字。一批按时间排列的开始条件证据，可以为空；处理结束后保留活动状态供下一批继续。|
|`end_ticks`|tuple[ConditionTick, ...]|是|无|位置或关键字。与ticks逐一对应的结束条件证据；两端时间必须一致。|
|`advances`|tuple[int, ...] &#124; None|否|None|仅关键字。与本批完整时间组等长的非负计时增量；固定/DBC模式首组为0，实际时间模式必须为None。|

#### 返回说明

本批新增Event tuple；
同时保留到drain。

#### 异常说明

协议/排序/结束后推进错误；输入失败不排序或补齐。

本函数直接报告的具体错误：

- `ValueError`：start_end检测器已finish。
- `ValueError`：start_end两个条件必须在相同完整时间组求值。

源码：[`src/chronaxis/core/start_end.py:137`](../../../src/chronaxis/core/start_end.py#L137)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-StartEndDetector-drain_events"></a>
### `StartEndDetector.drain_events`

转交当前输出，不清活动状态。

```python
StartEndDetector.drain_events()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

Event tuple。

#### 异常说明

分配错误。

源码：[`src/chronaxis/core/start_end.py:158`](../../../src/chronaxis/core/start_end.py#L158)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-StartEndDetector-finish"></a>
### `StartEndDetector.finish`

仅在已收到真实末组后封闭。

```python
StartEndDetector.finish()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

未移交Event tuple。

#### 异常说明

协议错误。

本函数直接报告的具体错误：

- `ValueError`：start_end需要唯一finish且已有真实terminal。

源码：[`src/chronaxis/core/start_end.py:164`](../../../src/chronaxis/core/start_end.py#L164)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
