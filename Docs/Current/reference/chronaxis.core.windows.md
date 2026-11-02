# chronaxis.core.windows

声明事件窗口和片段结果，校验归属并保存请求、实际边界与原活动关联。

输入是WindowSpec、已完成Event元组及真实观测Interval；独立后端负责扩展、
分组和裁剪，再由本模块包装Segment。片段合并不重写Event或填平条件未知。
核心执行模型独立于上层JSON WindowPlan，由执行层显式转换，避免核心导入配置/I/O。
本模块只验证协议、归类和生成稳定ID；不计算窗口数值、不读取旧日志或调用writer。
输入与返回均为完整内存模型；资源预算和原始报文导出由上层负责。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Event](chronaxis.core.temporal.md#api-Event)、[Interval](chronaxis.core.models.md#api-Interval)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[SourceRef](chronaxis.core.models.md#api-SourceRef)

## 对象导航

|对象|用途|
|---|---|
|[`WindowSpec`](#api-WindowSpec)|声明围绕同一规则事件的前后范围及明确合并政策。|
|[`WindowSpec.__post_init__`](#api-WindowSpec-__post_init__)|检查窗口声明，不计算边界或创建运行状态。|
|[`Segment`](#api-Segment)|保存一个片段的请求与实际范围，并关联全部原事件。|
|[`Segment.__post_init__`](#api-Segment-__post_init__)|检查片段归属、范围、覆盖及原事件引用的一致性。|
|[`require_windows`](#api-require_windows)|验证已完成事件的排序、规则/会话归属和真实观测范围。|
|[`CompactSegment`](#api-CompactSegment)|仅保实际业务范围和父事件关联，不输出重复请求边界、覆盖比例或来源副本。|
|[`require_resolved_windows`](#api-require_resolved_windows)|检查预先按选定周期取得的实际边界，未提供时沿旧实际扩展。|
|[`make_segment`](#api-make_segment)|用已经算出的请求边界、实际边界和覆盖情况创建窗口片段，同时保留原事件信息。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from hashlib import sha256
from math import isclose, isfinite
from .models import Interval, SourceRef
from .temporal import Event
from .types import QualityFlag as Q
from .validation import require_identifier, require_text
from ..timebase.conversion import require_int64_ns
```

</details>

<a id="api-WindowSpec"></a>
## `WindowSpec`

声明围绕同一规则事件的前后范围及明确合并政策。

anchor为point或activity；pre/post为非负int64纳秒。point至少一项正。
exit_delay仅用于activity且post=0，根据真实活动间隔分组，不能按pre重叠扩大。
实例不保存执行状态，不依赖上层配置或旧模式的隐式参数解释。

```python
class WindowSpec
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`window_id`|str|是|无|当前窗口唯一简单标识。|
|`event_rule_id`|str|是|无|已完成事件的规则标识。|
|`anchor`|str|是|无|`"activity"`：围绕整段活动扩展；`"point"`：围绕一个触发时刻扩展。须与规则产生的事件类型一致。|
|`pre_ns`|int|否|0|非负前扩展，不使用confirmed代替onset。|
|`post_ns`|int|否|0|非负后扩展，exit_delay模式必须0。|
|`merge`|str|否|'none'|多段窗口如何合并，四种值见下表。|
|`exit_delay_ns`|int &#124; None|否|None|只用于同名合并模式，不能重复附加post。 merge为exit_delay时必须填写非负纳秒数；其他合并模式填写None。|

源码：[`src/chronaxis/core/windows.py:24`](../../../src/chronaxis/core/windows.py#L24)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-WindowSpec-__post_init__"></a>
### `WindowSpec.__post_init__`

检查窗口声明，不计算边界或创建运行状态。

```python
WindowSpec.__post_init__()
```

参数：无显式参数。


#### 参数说明

无；读取创建后不可修改的字段。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError/OverflowError为标识、参数或时间协议错误。

本函数直接报告的具体错误：

- `ValueError`：窗口锚点、扩展或合并政策错误。
- `ValueError`：point窗口至少一个扩展为正。
- `ValueError`：exit_delay要求activity、post=0及非负delay。
- `ValueError`：exit_delay_ns仅用于exit_delay合并。

源码：[`src/chronaxis/core/windows.py:40`](../../../src/chronaxis/core/windows.py#L40)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-Segment"></a>
## `Segment`

保存一个片段的请求与实际范围，并关联全部原事件。

requested永不因EOF裁剪重写；actual为真实交集或None。覆盖为实际/请求时长。
status为complete、partial或empty；event_statuses保留closed/timeout/interrupted/truncated/point。
parent_event_ids、质量和字段来源不可变；合并不改变原事件数量或统计scope。

```python
class Segment
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`segment_id`|str|是|无|内容SHA，区别于旧整数秒文件名。|
|`dataset_id`|str|是|无|当前数据集归属。|
|`session_id`|str|是|无|当前真实会话，不跨会话合并。|
|`window`|[WindowSpec](chronaxis.core.windows.md#api-WindowSpec)|是|无|原窗口声明，保留合并政策。|
|`requested`|[Interval](chronaxis.core.models.md#api-Interval)|是|无|完整请求半开范围。|
|`actual`|[Interval](chronaxis.core.models.md#api-Interval) &#124; None|是|无|裁剪后实际范围，无交集为None。|
|`requested_coverage`|float|是|无|两后端独立计算的时长比。|
|`status`|str|是|无|`complete`表示实际取得的范围完整覆盖请求窗口；`partial`表示只取得其中一部分；`empty`表示没有可用的时间范围。这里描述片段覆盖情况，不表示输出文件是否写成功。|
|`parent_event_ids`|tuple[str, ...]|是|无|全部原活动/点事件稳定关联。|
|`event_statuses`|tuple[str, ...]|是|无|同长原事件结束状态，UNKNOWN中断不改closed。|
|`quality`|[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)|是|无|全部原事件的结束质量及依赖诊断。|
|`source_refs`|tuple[[SourceRef](chronaxis.core.models.md#api-SourceRef), ...]|是|无|当前所有依赖原字段引用。|

源码：[`src/chronaxis/core/windows.py:68`](../../../src/chronaxis/core/windows.py#L68)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-Segment-__post_init__"></a>
### `Segment.__post_init__`

检查片段归属、范围、覆盖及原事件引用的一致性。

```python
Segment.__post_init__()
```

参数：无显式参数。


#### 参数说明

无；读取全部创建后不可修改的字段。

#### 返回说明

None，不补范围或静默改覆盖。

#### 异常说明

TypeError/ValueError/OverflowError为非法结果模型。

本函数直接报告的具体错误：

- `TypeError`：Segment需WindowSpec及正请求Interval。
- `ValueError`：Segment实际范围必须是请求子区间。
- `ValueError`：Segment状态或覆盖错误。
- `ValueError`：Segment覆盖与时间事实不一致。
- `ValueError`：Segment需非空唯一parent_event_ids。
- `ValueError`：Segment事件状态需同长完整tuple。
- `TypeError`：Segment质量与来源需带有明确类型的模型。

源码：[`src/chronaxis/core/windows.py:89`](../../../src/chronaxis/core/windows.py#L89)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-require_windows"></a>
## `require_windows`

验证已完成事件的排序、规则/会话归属和真实观测范围。

```python
require_windows(events, spec, observation)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`events`|tuple|是|无|位置或关键字。events为已排序Event tuple|
|`spec`|[WindowSpec](chronaxis.core.windows.md#api-WindowSpec)|是|无|位置或关键字。spec为WindowSpec|
|`observation`|[Interval](chronaxis.core.models.md#api-Interval)|是|无|位置或关键字。observation为真实Interval。|

### 返回说明

None，只校验协议，不扩展或合并窗口。

### 异常说明

TypeError/ValueError为类型、重复、回退、归属或锚点不匹配。

本函数直接报告的具体错误：

- `TypeError`：窗口执行需Event tuple/WindowSpec/Interval。
- `ValueError`：窗口事件规则、锚点或唯一性不匹配。
- `ValueError`：start_only窗口需merge=none且post等于固定时长。
- `ValueError`：窗口事件不能回退或跨会话合并。
- `ValueError`：同一规则真实活动不能重叠。
- `ValueError`：事件事实超出实际观测范围。

源码：[`src/chronaxis/core/windows.py:124`](../../../src/chronaxis/core/windows.py#L124)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-CompactSegment"></a>
## `CompactSegment`

仅保实际业务范围和父事件关联，不输出重复请求边界、覆盖比例或来源副本。

```python
class CompactSegment
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`segment_id`|str|是|无|所处理的片段id；会话导出没有父片段，使用None。|
|`dataset_id`|str|是|无|配置声明的数据集标识，用于关联本次结果所属的数据集。|
|`session_id`|str|是|无|本次连续分析会话的标识；跨连续文件保持同一会话，独立任务各自隔离。|
|`window_id`|str|是|无|产生窗口的配置id；通过它找到锚点、前后范围及合并设置。|
|`actual`|[Interval](chronaxis.core.models.md#api-Interval) &#124; None|是|无|裁剪后实际可用的半开范围；None表示没有可导出的交集。|
|`status`|str|是|无|complete为完整窗口，partial为观测不足而裁剪，empty为没有实际交集。|
|`parent_event_ids`|tuple[str, ...]|是|无|产生该片段的全部事件id；窗口合并后仍保留全部父事件关联。|
|`quality`|[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)|是|无|该值或结果的质量位组合；缺失、过期等原因不能通过清零掩盖。|
|`coverage`|float &#124; None|否|None|仅下游明确设置覆盖门槛时计算，默认不保存。|

源码：[`src/chronaxis/core/windows.py:155`](../../../src/chronaxis/core/windows.py#L155)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-require_resolved_windows"></a>
## `require_resolved_windows`

检查预先按选定周期取得的实际边界，未提供时沿旧实际扩展。

```python
require_resolved_windows(events, bounds, compact)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`events`|tuple[[Event](chronaxis.core.temporal.md#api-Event), ...]|是|无|位置或关键字。当前实际时刻产生的事件集合；同一时刻事件先收齐再交给配对处理。|
|`bounds`|tuple[tuple[int, int, bool, bool], ...] &#124; None|是|无|位置或关键字。与事件同长的实际窗口边界，每项为起点、终点、左裁剪标志、右裁剪标志；None按原实际时长展开。|
|`compact`|bool|是|无|位置或关键字。声明是否使用精简窗口模型。True才允许传入预解析bounds；False且bounds非None时报错。该函数只检查，不生成导出文件。|

### 返回说明

None。

### 异常说明

类型/长度/边界错误。

### 副作用说明

不构造另一时间轴。

源码：[`src/chronaxis/core/windows.py:168`](../../../src/chronaxis/core/windows.py#L168)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-make_segment"></a>
## `make_segment`

用已经算出的请求边界、实际边界和覆盖情况创建窗口片段，同时保留原事件信息。

```python
make_segment(spec, requested, actual, coverage, parents, *, compact=False, clipped=False)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|[WindowSpec](chronaxis.core.windows.md#api-WindowSpec)|是|无|位置或关键字。当前窗口配置，指定起算位置、前后扩展和越界处理方式。|
|`requested`|[Interval](chronaxis.core.models.md#api-Interval)|是|无|位置或关键字。按窗口配置算出的原始请求范围，尚未按实际观测裁剪。|
|`actual`|[Interval](chronaxis.core.models.md#api-Interval) &#124; None|是|无|位置或关键字。请求范围与观测范围的交集；没有交集时为None。|
|`coverage`|float|是|无|位置或关键字。实际覆盖时长占请求时长的比例，取0至1；由调用方按两种范围计算。|
|`parents`|tuple[[Event](chronaxis.core.temporal.md#api-Event), ...]|是|无|位置或关键字。parents非空Event tuple。|
|`compact`|bool|否|False|仅关键字。选择返回的窗口模型：True生成CompactSegment，保留实际区间、父事件ID、状态和质量；False生成含请求范围、覆盖等详细信息的Segment。默认False；这不改变输入事件。|
|`clipped`|bool|否|False|仅关键字。请求范围是否因观测不足而被裁剪；用于生成partial或empty状态。|

### 返回说明

Segment，稳定ID包含窗口语义、原事件引用与请求/实际边界。

### 异常说明

输出模型不满足约束时传播检查异常。

### 副作用说明

无；不计算扩展、分组或窗口覆盖，不修改Event。

源码：[`src/chronaxis/core/windows.py:186`](../../../src/chronaxis/core/windows.py#L186)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
