# `chronaxis.execution.file_integral_terms`

按文件并行计算原序面积，父进程独自处理跨文件边界和误差求和。

工作进程只保留有限点块和当前同一时刻组；首组的出区间交给父进程，避免前一
文件的同一时刻值改变本文件首组。消息不包含原帧、历史文件或文件部分和。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CANUpdateProjection](chronaxis.sources.can_updates.md#api-CANUpdateProjection)、[CalculationSeries](chronaxis.core.calculations.md#api-CalculationSeries)、[Interval](chronaxis.core.models.md#api-Interval)、[QualityFlag](chronaxis.core.types.md#api-QualityFlag)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[SameFrameEvaluator](chronaxis.execution.same_frame_integrals.md#api-SameFrameEvaluator)、[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)

## 对象导航

|对象|用途|
|---|---|
|[`SameTimeGroupSummary`](#api-SameTimeGroupSummary)|保留解决跨文件同一时刻选择所需的首末值及最早冲突位置，大小不随组帧数增长。|
|[`FileIntegralHead`](#api-FileIntegralHead)|文件首个目标同一时刻组及下一组时间；首个出区间始终由父进程计算。|
|[`IntegralColumnTerms`](#api-IntegralColumnTerms)|一个计算项的原序面积、有效掩码和覆盖事实，不含局部和。|
|[`IntegralTermsChunk`](#api-IntegralTermsChunk)|排除首组出区间后的有限内部区间块；列顺序与冻结计算项一致。|
|[`FileIntegralTail`](#api-FileIntegralTail)|文件末组；same_as_head表示单组文件，不重复传其组值。|
|[`FileIntegralFrontier`](#api-FileIntegralFrontier)|异常排空时确认一个已经关闭的右端组；没有可另行组成面积块的区间。|
|[`_conflict`](#api-_conflict)|按原帧位置和声明顺序抛出最早同一时刻冲突。|
|[`_offset_group`](#api-_offset_group)|将局部原帧序号提升到连续来源全局序号。|
|[`_merge_group`](#api-_merge_group)|有界合并跨文件同一时刻组；不会为相等组保留逐帧序号集合。|
|[`_columns`](#api-_columns)|调用现役参考面积核，不先累计、不改变乘除顺序。|
|[`file_terms_minimum_cost`](#api-file_terms_minimum_cost)|计算文件面积状态不依赖DBC的必要费用下界。|
|[`parent_terms_minimum_cost`](#api-parent_terms_minimum_cost)|计算父边界状态不依赖DBC的必要费用下界。|
|[`file_terms_cost`](#api-file_terms_cost)|报告文件面积owner及其求值器的实际固定预约费用。|
|[`parent_terms_cost`](#api-parent_terms_cost)|报告父边界owner及求值器固定费用，覆盖全局余量、一个通信块和切片副本。|
|[`FileIntegralTerms`](#api-FileIntegralTerms)|文件工作进程的有界归组及面积生产器，不拥有求和状态。|
|[`FileIntegralTerms.__init__`](#api-FileIntegralTerms-__init__)|安装已验证任务及投影，首条原帧尚未读取。|
|[`FileIntegralTerms.compatibility_fields`](#api-FileIntegralTerms-compatibility_fields)|借用同次投影的FD兼容提示。|
|[`FileIntegralTerms._require_open`](#api-FileIntegralTerms-_require_open)|拒绝失败、完成或关闭后的推进。|
|[`FileIntegralTerms._flush_points`](#api-FileIntegralTerms-_flush_points)|将完整内部区间交付为一个有限块，留下共享末点。|
|[`FileIntegralTerms._append_group`](#api-FileIntegralTerms-_append_group)|保存一组必要求值点，并在区间数达到上限时交付块。|
|[`FileIntegralTerms.feed`](#api-FileIntegralTerms-feed)|消费读取器的一条已解码记录，必要时返回首组或一个内部面积块。|
|[`FileIntegralTerms.finish`](#api-FileIntegralTerms-finish)|完成有限数值缓冲；读取器EOF和关闭成功由传输层单独证明。|
|[`FileIntegralTerms.drain_prefix_on_error`](#api-FileIntegralTerms-drain_prefix_on_error)|读取或求值失败后交付此前真正关闭的有限组，不假设当前组已经结束。|
|[`FileIntegralTerms.close`](#api-FileIntegralTerms-close)|断开缓冲和投影引用并退还本owner费用。|
|[`ParentIntegralTerms`](#api-ParentIntegralTerms)|按文件顺序修复同一时刻及边界，并将原序面积交给父进程唯一积分器。|
|[`ParentIntegralTerms.__init__`](#api-ParentIntegralTerms-__init__)|建立有界边界状态，借用外部积分器。|
|[`ParentIntegralTerms._require_open`](#api-ParentIntegralTerms-_require_open)|失败或结束后仅允许关闭。|
|[`ParentIntegralTerms.begin_file`](#api-ParentIntegralTerms-begin_file)|切换到下一个已按顺序交付的文件。|
|[`ParentIntegralTerms._drain`](#api-ParentIntegralTerms-_drain)|按原全局批界依次推进各指标，不提前累计尚未关闭的右端组。|
|[`ParentIntegralTerms._mark_closed`](#api-ParentIntegralTerms-_mark_closed)|确认待定右端同一时刻组关闭后允许满批归约。|
|[`ParentIntegralTerms._accept`](#api-ParentIntegralTerms-_accept)|保存一块原序面积并累计已经收到的覆盖事实。|
|[`ParentIntegralTerms._boundary`](#api-ParentIntegralTerms-_boundary)|使用现役面积核计算一条跨文件或首组出区间。|
|[`ParentIntegralTerms.consume`](#api-ParentIntegralTerms-consume)|接收当前文件的首组、面积块或末组；文件顺序由池保证。|
|[`ParentIntegralTerms.finish`](#api-ParentIntegralTerms-finish)|读取池已证明全部EOF后，仅补到实际观测末端。|
|[`ParentIntegralTerms.close`](#api-ParentIntegralTerms-close)|释放自有边界状态，外部积分器由父会话关闭。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass, replace
from ..core.calculations import CalculationSeries
from ..core.integral_terms_reference import compute_integral_terms_reference
from ..core.models import Interval
from ..core.numeric import ScalarValue
from ..core.types import QualityFlag
from ..results.budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..results.errors import ResultClosedError
from ..sources.can_spec import can_field_from_key
from ..sources.can_updates import CANUpdateProjection
from .same_frame_integrals import SameFrameEvaluator, same_frame_evaluator_cost, SAME_FRAME_EVALUATOR_BASE_COST, _same_value
from .static_metadata import static_metadata_bytes
```

</details>

<a id="api-SameTimeGroupSummary"></a>
## `SameTimeGroupSummary`

保留解决跨文件同一时刻选择所需的首末值及最早冲突位置，大小不随组帧数增长。

```python
class SameTimeGroupSummary
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|同一时刻组实际时间，不创建第二套计算时钟。|
|`first_sequence`|int|是|无|文件内首条原帧序号；父进程加之前文件的全部原帧数。|
|`last_sequence`|int|是|无|本组最后原帧序号，供last_by_sequence使用。|
|`count`|int|是|无|组内匹配帧数，不保存逐帧序号列表。|
|`first_values`|tuple[[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue), ...]|是|无|按冻结定义顺序，供跨文件error政策比较。|
|`last_values`|tuple[[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue), ...]|是|无|同顺序最终值；无效本条也覆盖上一条。|
|`first_conflicts`|tuple[int &#124; None, ...]|是|无|每个error信号首次冲突的局部序号，None表示未见冲突。|

源码：[`src/chronaxis/execution/file_integral_terms.py:24`](../../../src/chronaxis/execution/file_integral_terms.py#L24)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-FileIntegralHead"></a>
## `FileIntegralHead`

文件首个目标同一时刻组及下一组时间；首个出区间始终由父进程计算。

```python
class FileIntegralHead
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`group`|[SameTimeGroupSummary](chronaxis.execution.file_integral_terms.md#api-SameTimeGroupSummary)|是|无|仅首组可能受前文件的同一时刻值影响。|
|`next_time_ns`|int &#124; None|是|无|下一目标组的实际时间；单组或错误排空时尚未知。|

源码：[`src/chronaxis/execution/file_integral_terms.py:37`](../../../src/chronaxis/execution/file_integral_terms.py#L37)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-IntegralColumnTerms"></a>
## `IntegralColumnTerms`

一个计算项的原序面积、有效掩码和覆盖事实，不含局部和。

```python
class IntegralColumnTerms
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`areas`|tuple[float, ...]|是|无|原序float64面积，尚未换算最终单位或求和。|
|`valid`|tuple[bool, ...]|是|无|无效槽中的0不能作为有效零参与求和。|
|`covered_ns`|int|是|无|该块与请求范围相交的实际覆盖长度。|
|`valid_ns`|int|是|无|上述覆盖内具备有效数值的长度。|
|`quality`|[QualityFlag](chronaxis.core.types.md#api-QualityFlag)|是|无|原面积核已确认的质量位。|

源码：[`src/chronaxis/execution/file_integral_terms.py:45`](../../../src/chronaxis/execution/file_integral_terms.py#L45)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-IntegralTermsChunk"></a>
## `IntegralTermsChunk`

排除首组出区间后的有限内部区间块；列顺序与冻结计算项一致。

```python
class IntegralTermsChunk
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`left_ns`|int|是|无|本块第一个点时间，和前块右端一致。|
|`right_ns`|int|是|无|本块最后一个点时间，不另计尾面积。|
|`columns`|tuple[[IntegralColumnTerms](chronaxis.execution.file_integral_terms.md#api-IntegralColumnTerms), ...]|是|无|固定计算项顺序的各原序列。|
|`right_closed`|bool|否|True|True表示右端同一时刻组已关闭；False表示仍需等待跨文件同一时刻合并。|

源码：[`src/chronaxis/execution/file_integral_terms.py:56`](../../../src/chronaxis/execution/file_integral_terms.py#L56)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-FileIntegralTail"></a>
## `FileIntegralTail`

文件末组；same_as_head表示单组文件，不重复传其组值。

```python
class FileIntegralTail
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`group`|[SameTimeGroupSummary](chronaxis.execution.file_integral_terms.md#api-SameTimeGroupSummary) &#124; None|是|无|多组文件的末组；无目标或单组时None。|
|`same_as_head`|bool|是|无|单组文件与head共享，不再复制首末值。|

源码：[`src/chronaxis/execution/file_integral_terms.py:66`](../../../src/chronaxis/execution/file_integral_terms.py#L66)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-FileIntegralFrontier"></a>
## `FileIntegralFrontier`

异常排空时确认一个已经关闭的右端组；没有可另行组成面积块的区间。

```python
class FileIntegralFrontier
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|已闭内部点，与父进程正在等待的面积右端一致。|

源码：[`src/chronaxis/execution/file_integral_terms.py:74`](../../../src/chronaxis/execution/file_integral_terms.py#L74)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_conflict"></a>
## `_conflict`

按原帧位置和声明顺序抛出最早同一时刻冲突。

```python
_conflict(group, definitions)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`group`|[SameTimeGroupSummary](chronaxis.execution.file_integral_terms.md#api-SameTimeGroupSummary)|是|无|位置或关键字。已合并或单文件同一时刻组，first_conflicts保存每信号首次冲突位置。|
|`definitions`|tuple[SignalDefinition, ...]|是|无|位置或关键字。本次积分实际依赖的信号定义，按冻结顺序排列；已由同次DBC事实补齐有效期。|

### 返回说明

None。

### 异常说明

ValueError。

源码：[`src/chronaxis/execution/file_integral_terms.py:80`](../../../src/chronaxis/execution/file_integral_terms.py#L80)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_offset_group"></a>
## `_offset_group`

将局部原帧序号提升到连续来源全局序号。

```python
_offset_group(group, offset)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`group`|[SameTimeGroupSummary](chronaxis.execution.file_integral_terms.md#api-SameTimeGroupSummary)|是|无|位置或关键字。使用文件内原帧序号的摘要。|
|`offset`|int|是|无|位置或关键字。此前文件全部原帧数量的非负偏移，包含未参与积分的原帧。|

### 返回说明

SameTimeGroupSummary，仅平移原帧序号，时间和值保持不变。

### 异常说明

内部字段不符合模型时传播TypeError或AttributeError。

源码：[`src/chronaxis/execution/file_integral_terms.py:90`](../../../src/chronaxis/execution/file_integral_terms.py#L90)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_merge_group"></a>
## `_merge_group`

有界合并跨文件同一时刻组；不会为相等组保留逐帧序号集合。

```python
_merge_group(left, right, definitions)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`left`|[SameTimeGroupSummary](chronaxis.execution.file_integral_terms.md#api-SameTimeGroupSummary)|是|无|位置或关键字。前一文件或已合并的同一时刻组，使用全局原帧序号。|
|`right`|[SameTimeGroupSummary](chronaxis.execution.file_integral_terms.md#api-SameTimeGroupSummary)|是|无|位置或关键字。后一文件同一时刻组；时间必须与left相等，首序号必须晚于left末序号。|
|`definitions`|tuple[SignalDefinition, ...]|是|无|位置或关键字。本次积分实际依赖的信号定义，按冻结顺序排列；已由同次DBC事实补齐有效期。|

### 返回说明

SameTimeGroupSummary，保留首值、最终值和最早冲突位置；不保存逐帧序号列表。

### 异常说明

非同一时刻或原序号倒退时ValueError；业务冲突先记录到摘要，由调用方按序抛出。

源码：[`src/chronaxis/execution/file_integral_terms.py:102`](../../../src/chronaxis/execution/file_integral_terms.py#L102)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_columns"></a>
## `_columns`

调用现役参考面积核，不先累计、不改变乘除顺序。

```python
_columns(points, expressions, specs, domain)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`points`|Sequence[tuple[int, tuple[tuple[[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue), int &#124; None], ...]]]|是|无|位置或关键字。按时间递增的有限点列；每点包含实际纳秒及各表达式的值、有效截止纳秒。|
|`expressions`|tuple[StaticExpression, ...]|是|无|位置或关键字。已验证的简单数值表达式，与积分计算项顺序一致。|
|`specs`|tuple[CalculationDefinition, ...]|是|无|位置或关键字。与表达式逐项对应的会话积分请求，保留请求单位及完整性规则。|
|`domain`|[Interval](chronaxis.core.models.md#api-Interval) &#124; None|是|无|位置或关键字。实际纳秒坐标中的请求范围；None表示按已有观测范围处理，不创建第二套时钟。|

### 返回说明

tuple[IntegralColumnTerms, ...]，按计算项顺序保留面积、掩码和覆盖事实，不先求和。

### 异常说明

原面积核的类型、时间及数值结构错误原样传播。

源码：[`src/chronaxis/execution/file_integral_terms.py:122`](../../../src/chronaxis/execution/file_integral_terms.py#L122)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-file_terms_minimum_cost"></a>
## `file_terms_minimum_cost`

计算文件面积状态不依赖DBC的必要费用下界。

```python
file_terms_minimum_cost(calculation_count: int, *, batch_intervals: int=64) -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`calculation_count`|int|是|无|位置或关键字。本次会话的积分计算项数量，允许非负原生整数，不接受bool；用于估算每项必须保留的状态，不是报文数。|
|`batch_intervals`|int|否|64|仅关键字。文件内每批面积区间数上限，默认64，允许1至4096的原生整数；据此估算批容量，不改变采样周期。|

### 返回说明

int，文件面积固定状态、批容量和求值器固定费的必要字节下界；尚未计入DBC、声明图、表达式及读取费用。

### 异常说明

计算项数不是非负原生整数，或批上限不是1至4096的原生整数时抛ValueError；只计算费用，不构造数值状态或读取文件。

返回类型：int。

源码：[`src/chronaxis/execution/file_integral_terms.py:145`](../../../src/chronaxis/execution/file_integral_terms.py#L145)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-parent_terms_minimum_cost"></a>
## `parent_terms_minimum_cost`

计算父边界状态不依赖DBC的必要费用下界。

```python
parent_terms_minimum_cost(calculation_count: int, *, batch_intervals: int=64) -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`calculation_count`|int|是|无|位置或关键字。本次会话的积分计算项数量，允许非负原生整数，不接受bool；用于估算每项必须保留的状态，不是报文数。|
|`batch_intervals`|int|否|64|仅关键字。父进程按原顺序累计的全局区间批上限，默认64，允许1至4096的原生整数；用于估算固定状态和待处理余量。|

### 返回说明

int，父边界固定状态、全局余量及求值器固定费的必要字节下界；声明图和借用的RecordIntegral另计。

### 异常说明

计算项数不是非负原生整数，或批上限不是1至4096的原生整数时抛ValueError；不申请预算或构造求值器。

返回类型：int。

源码：[`src/chronaxis/execution/file_integral_terms.py:160`](../../../src/chronaxis/execution/file_integral_terms.py#L160)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-file_terms_cost"></a>
## `file_terms_cost`

报告文件面积owner及其求值器的实际固定预约费用。

```python
file_terms_cost(definitions, expressions, specs, derived=(), *, batch_intervals=64)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`definitions`|tuple[SignalDefinition, ...]|是|无|位置或关键字。本次积分实际依赖的信号定义，按冻结顺序排列；已由同次DBC事实补齐有效期。|
|`expressions`|tuple[StaticExpression, ...]|是|无|位置或关键字。已验证的简单数值表达式，与积分计算项顺序一致。|
|`specs`|tuple[CalculationDefinition, ...]|是|无|位置或关键字。与表达式逐项对应的会话积分请求，保留请求单位及完整性规则。|
|`derived`|tuple[DerivedDefinition, ...]|否|()|位置或关键字。原计划的派生声明，默认空tuple；用于核对表达式身份，不新增输出。|
|`batch_intervals`|int|否|64|仅关键字。每批区间数上限，默认64，允许1至4096的原生整数；与报文采样周期无关。|

### 返回说明

int，文件面积状态与求值器的保守预约字节数；不含读取器、通信包和任务重建。

### 异常说明

批上限非法时ValueError；静态模型原错传播。
调用方另计读取器、通信包和任务重建；此函数不为它们重复占用预算。

源码：[`src/chronaxis/execution/file_integral_terms.py:175`](../../../src/chronaxis/execution/file_integral_terms.py#L175)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-parent_terms_cost"></a>
## `parent_terms_cost`

报告父边界owner及求值器固定费用，覆盖全局余量、一个通信块和切片副本。

```python
parent_terms_cost(definitions, expressions, derived=(), *, batch_intervals=64)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`definitions`|tuple[SignalDefinition, ...]|是|无|位置或关键字。本次积分实际依赖的信号定义，按冻结顺序排列；已由同次DBC事实补齐有效期。|
|`expressions`|tuple[StaticExpression, ...]|是|无|位置或关键字。已验证的简单数值表达式，与积分计算项顺序一致。|
|`derived`|tuple[DerivedDefinition, ...]|否|()|位置或关键字。原计划的派生声明，默认空tuple；用于核对表达式身份，不新增输出。|
|`batch_intervals`|int|否|64|仅关键字。每批区间数上限，默认64，允许1至4096的原生整数；与报文采样周期无关。|

### 返回说明

int，父边界状态与求值器的保守预约字节数；借用的RecordIntegral另行预约。

### 异常说明

批上限非法时ValueError；静态模型原错传播。
不包含借用的RecordIntegral，其预算仍由父会话独立申请。

源码：[`src/chronaxis/execution/file_integral_terms.py:188`](../../../src/chronaxis/execution/file_integral_terms.py#L188)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-FileIntegralTerms"></a>
## `FileIntegralTerms`

文件工作进程的有界归组及面积生产器，不拥有求和状态。

```python
FileIntegralTerms(budget, definitions, expressions, specs, binding, session_id, *, derived=(), batch_intervals=64, domain=None)
```


源码：[`src/chronaxis/execution/file_integral_terms.py:201`](../../../src/chronaxis/execution/file_integral_terms.py#L201)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-FileIntegralTerms-__init__"></a>
### `FileIntegralTerms.__init__`

安装已验证任务及投影，首条原帧尚未读取。

```python
FileIntegralTerms.__init__(budget, definitions, expressions, specs, binding, session_id, *, derived=(), batch_intervals=64, domain=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|ResourceBudget|是|无|位置或关键字。与父会话共享的受管理预算；本对象只预约和归还自身持有的费用。|
|`definitions`|tuple[SignalDefinition, ...]|是|无|位置或关键字。本次积分实际依赖的信号定义，按冻结顺序排列；已由同次DBC事实补齐有效期。|
|`expressions`|tuple[StaticExpression, ...]|是|无|位置或关键字。已验证的简单数值表达式，与积分计算项顺序一致。|
|`specs`|tuple[CalculationDefinition, ...]|是|无|位置或关键字。与表达式逐项对应的会话积分请求，保留请求单位及完整性规则。|
|`binding`|SameFrameBinding|是|无|位置或关键字。首帧前由同次DBC元数据证明的唯一共同报文定位。|
|`session_id`|str|是|无|位置或关键字。本次连续分析的会话名称，文件切换时保持不变。|
|`derived`|tuple[DerivedDefinition, ...]|否|()|仅关键字。原计划的派生声明，默认空tuple；用于核对表达式身份，不新增输出。|
|`batch_intervals`|int|否|64|仅关键字。每批区间数上限，默认64，允许1至4096的原生整数；与报文采样周期无关。|
|`domain`|[Interval](chronaxis.core.models.md#api-Interval) &#124; None|否|None|仅关键字。实际纳秒坐标中的请求范围；None表示按已有观测范围处理，不创建第二套时钟。|

#### 返回说明

None，构造新的文件面积owner，不读取原帧。

#### 异常说明

非法声明或批上限时ValueError，范围类型错误时TypeError，预算不足时BudgetExceededError；
    原求值器异常继续传播，构造清理失败附file_integral_terms_cleanup_owner。

源码：[`src/chronaxis/execution/file_integral_terms.py:204`](../../../src/chronaxis/execution/file_integral_terms.py#L204)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-FileIntegralTerms-compatibility_fields"></a>
### `FileIntegralTerms.compatibility_fields`

借用同次投影的FD兼容提示。

```python
FileIntegralTerms.compatibility_fields
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

CANField到实际扩展帧标志bool的映射；投影释放后返回空dict。

#### 异常说明

无；调用方不能修改借用的映射。

源码：[`src/chronaxis/execution/file_integral_terms.py:255`](../../../src/chronaxis/execution/file_integral_terms.py#L255)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-FileIntegralTerms-_require_open"></a>
### `FileIntegralTerms._require_open`

拒绝失败、完成或关闭后的推进。

```python
FileIntegralTerms._require_open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

ResultClosedError。

源码：[`src/chronaxis/execution/file_integral_terms.py:263`](../../../src/chronaxis/execution/file_integral_terms.py#L263)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-FileIntegralTerms-_flush_points"></a>
### `FileIntegralTerms._flush_points`

将完整内部区间交付为一个有限块，留下共享末点。

```python
FileIntegralTerms._flush_points(*, right_closed=True)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`right_closed`|bool|否|True|仅关键字。默认True表示块右端同一时刻组已经关闭；False表示仍需等待跨文件同一时刻合并后才能归约最后一个区间。|

#### 返回说明

IntegralTermsChunk；不足两个点时返回None。

#### 异常说明

原面积核的类型、时间及数值结构错误原样传播。

源码：[`src/chronaxis/execution/file_integral_terms.py:268`](../../../src/chronaxis/execution/file_integral_terms.py#L268)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-FileIntegralTerms-_append_group"></a>
### `FileIntegralTerms._append_group`

保存一组必要求值点，并在区间数达到上限时交付块。

```python
FileIntegralTerms._append_group(group, *, check_conflict=True, right_closed=True)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`group`|[SameTimeGroupSummary](chronaxis.execution.file_integral_terms.md#api-SameTimeGroupSummary)|是|无|位置或关键字。同一时刻组的冻结摘要，包含首末值和原帧序号。|
|`check_conflict`|bool|否|True|仅关键字。默认True，立即按原帧顺序报告组内冲突；文件末组由父进程报告时传False。|
|`right_closed`|bool|否|True|仅关键字。默认True表示块右端同一时刻组已经关闭；False表示仍需等待跨文件同一时刻合并后才能归约最后一个区间。|

#### 返回说明

IntegralTermsChunk；尚未达到块上限时返回None。

#### 异常说明

同一时刻冲突时ValueError；原求值器和面积核异常继续传播。

源码：[`src/chronaxis/execution/file_integral_terms.py:282`](../../../src/chronaxis/execution/file_integral_terms.py#L282)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-FileIntegralTerms-feed"></a>
### `FileIntegralTerms.feed`

消费读取器的一条已解码记录，必要时返回首组或一个内部面积块。

```python
FileIntegralTerms.feed(record)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`record`|DecodedCANRecord|是|无|位置或关键字。读取器交付的一条已解码原帧记录；保留本条真实时间和文件内sequence，无关帧不缓存载荷。|

#### 返回说明

tuple[FileIntegralHead | IntegralTermsChunk, ...]；没有新边界或完整块时为空tuple。

#### 异常说明

原投影、原序、归一化或面积错误。
无关帧只在读取层参与观测事实；这里不缓存其载荷或重复解码。

源码：[`src/chronaxis/execution/file_integral_terms.py:295`](../../../src/chronaxis/execution/file_integral_terms.py#L295)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-FileIntegralTerms-finish"></a>
### `FileIntegralTerms.finish`

完成有限数值缓冲；读取器EOF和关闭成功由传输层单独证明。

```python
FileIntegralTerms.finish()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

事件tuple，包含首组/内部面积块及文件末组标志；无目标帧也返回末标志。

#### 异常说明

已关闭、失败或完成时ResultClosedError；原数值异常继续传播，失败后只能关闭。

源码：[`src/chronaxis/execution/file_integral_terms.py:343`](../../../src/chronaxis/execution/file_integral_terms.py#L343)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-FileIntegralTerms-drain_prefix_on_error"></a>
### `FileIntegralTerms.drain_prefix_on_error`

读取或求值失败后交付此前真正关闭的有限组，不假设当前组已经结束。

```python
FileIntegralTerms.drain_prefix_on_error()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

事件tuple，可含FileIntegralHead、IntegralTermsChunk或FileIntegralFrontier；
    没有可交付前缀或已经完成时为空tuple。

#### 异常说明

已关闭时ResultClosedError；原数值异常继续传播。
首组摘要也携带已看到的冲突位置，父进程可先判定更早的跨文件冲突。

源码：[`src/chronaxis/execution/file_integral_terms.py:372`](../../../src/chronaxis/execution/file_integral_terms.py#L372)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-FileIntegralTerms-close"></a>
### `FileIntegralTerms.close`

断开缓冲和投影引用并退还本owner费用。

```python
FileIntegralTerms.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

退款失败可重试。

源码：[`src/chronaxis/execution/file_integral_terms.py:393`](../../../src/chronaxis/execution/file_integral_terms.py#L393)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-ParentIntegralTerms"></a>
## `ParentIntegralTerms`

按文件顺序修复同一时刻及边界，并将原序面积交给父进程唯一积分器。

```python
ParentIntegralTerms(budget, definitions, expressions, calculations, binding, session_id, *, derived=(), domain=None)
```


源码：[`src/chronaxis/execution/file_integral_terms.py:407`](../../../src/chronaxis/execution/file_integral_terms.py#L407)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-ParentIntegralTerms-__init__"></a>
### `ParentIntegralTerms.__init__`

建立有界边界状态，借用外部积分器。

```python
ParentIntegralTerms.__init__(budget, definitions, expressions, calculations, binding, session_id, *, derived=(), domain=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|ResourceBudget|是|无|位置或关键字。与父会话共享的受管理预算；本对象只预约和归还自身持有的费用。|
|`definitions`|tuple[SignalDefinition, ...]|是|无|位置或关键字。本次积分实际依赖的信号定义，按冻结顺序排列；已由同次DBC事实补齐有效期。|
|`expressions`|tuple[StaticExpression, ...]|是|无|位置或关键字。已验证的简单数值表达式，与积分计算项顺序一致。|
|`calculations`|tuple[RecordIntegral, ...]|是|无|位置或关键字。父会话拥有的实际时间reference积分器，顺序对应expressions；本对象不代替父会话关闭它们。|
|`binding`|SameFrameBinding|是|无|位置或关键字。首帧前由同次DBC元数据证明的唯一共同报文定位。|
|`session_id`|str|是|无|位置或关键字。本次连续分析的会话名称，文件切换时保持不变。|
|`derived`|tuple[DerivedDefinition, ...]|否|()|仅关键字。原计划的派生声明，默认空tuple；用于核对表达式身份，不新增输出。|
|`domain`|[Interval](chronaxis.core.models.md#api-Interval) &#124; None|否|None|仅关键字。实际纳秒坐标中的请求范围；None表示按已有观测范围处理，不创建第二套时钟。|

#### 返回说明

None，构造新的父边界owner，借用外部积分器。

#### 异常说明

声明、范围或积分器不一致时ValueError，预算不足时BudgetExceededError；
    原求值器异常继续传播，构造清理失败附parent_integral_terms_cleanup_owner。

源码：[`src/chronaxis/execution/file_integral_terms.py:410`](../../../src/chronaxis/execution/file_integral_terms.py#L410)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-ParentIntegralTerms-_require_open"></a>
### `ParentIntegralTerms._require_open`

失败或结束后仅允许关闭。

```python
ParentIntegralTerms._require_open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

ResultClosedError。

源码：[`src/chronaxis/execution/file_integral_terms.py:460`](../../../src/chronaxis/execution/file_integral_terms.py#L460)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-ParentIntegralTerms-begin_file"></a>
### `ParentIntegralTerms.begin_file`

切换到下一个已按顺序交付的文件。

```python
ParentIntegralTerms.begin_file(sequence_offset)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`sequence_offset`|int|是|无|位置或关键字。之前全部文件的原帧总数，非负原生整数；用于把当前文件局部sequence转为全局序号。|

#### 返回说明

None。

#### 异常说明

状态/偏移错。

源码：[`src/chronaxis/execution/file_integral_terms.py:465`](../../../src/chronaxis/execution/file_integral_terms.py#L465)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-ParentIntegralTerms-_drain"></a>
### `ParentIntegralTerms._drain`

按原全局批界依次推进各指标，不提前累计尚未关闭的右端组。

```python
ParentIntegralTerms._drain(*, final=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`final`|bool|否|False|仅关键字。默认False，只归约完整全局批；整体EOF后为True，允许处理不足一批的已关闭区间。|

#### 返回说明

None。

#### 异常说明

原累计容量/状态错误。

源码：[`src/chronaxis/execution/file_integral_terms.py:473`](../../../src/chronaxis/execution/file_integral_terms.py#L473)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-ParentIntegralTerms-_mark_closed"></a>
### `ParentIntegralTerms._mark_closed`

确认待定右端同一时刻组关闭后允许满批归约。

```python
ParentIntegralTerms._mark_closed()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

原累计错误。

源码：[`src/chronaxis/execution/file_integral_terms.py:488`](../../../src/chronaxis/execution/file_integral_terms.py#L488)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-ParentIntegralTerms-_accept"></a>
### `ParentIntegralTerms._accept`

保存一块原序面积并累计已经收到的覆盖事实。

```python
ParentIntegralTerms._accept(columns, *, right_closed=True)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`columns`|tuple[[IntegralColumnTerms](chronaxis.execution.file_integral_terms.md#api-IntegralColumnTerms), ...]|是|无|位置或关键字。与父积分器同序的有限面积列；各列长度一致且为1至4096，覆盖事实可先于末区间归约。|
|`right_closed`|bool|否|True|仅关键字。默认True表示块右端同一时刻组已经关闭；False表示仍需等待跨文件同一时刻合并后才能归约最后一个区间。|

#### 返回说明

None。

#### 异常说明

原结构/累计错。

源码：[`src/chronaxis/execution/file_integral_terms.py:493`](../../../src/chronaxis/execution/file_integral_terms.py#L493)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-ParentIntegralTerms-_boundary"></a>
### `ParentIntegralTerms._boundary`

使用现役面积核计算一条跨文件或首组出区间。

```python
ParentIntegralTerms._boundary(group, right)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`group`|[SameTimeGroupSummary](chronaxis.execution.file_integral_terms.md#api-SameTimeGroupSummary)|是|无|位置或关键字。边界区间左端已解决同一时刻选择的组。|
|`right`|int|是|无|位置或关键字。边界区间右端实际纳秒，必须严格大于group.time_ns。|

#### 返回说明

None。

#### 异常说明

原计算错。

源码：[`src/chronaxis/execution/file_integral_terms.py:511`](../../../src/chronaxis/execution/file_integral_terms.py#L511)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-ParentIntegralTerms-consume"></a>
### `ParentIntegralTerms.consume`

接收当前文件的首组、面积块或末组；文件顺序由池保证。

```python
ParentIntegralTerms.consume(event)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`event`|[FileIntegralHead](chronaxis.execution.file_integral_terms.md#api-FileIntegralHead) &#124; [IntegralTermsChunk](chronaxis.execution.file_integral_terms.md#api-IntegralTermsChunk) &#124; [FileIntegralTail](chronaxis.execution.file_integral_terms.md#api-FileIntegralTail) &#124; [FileIntegralFrontier](chronaxis.execution.file_integral_terms.md#api-FileIntegralFrontier)|是|无|位置或关键字。当前文件按读取顺序交付的冻结事件；Frontier确认已关闭右端，不自行增加面积。|

#### 返回说明

None。

#### 异常说明

同一时刻冲突、时间/消息次序或原累计错误。

源码：[`src/chronaxis/execution/file_integral_terms.py:519`](../../../src/chronaxis/execution/file_integral_terms.py#L519)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-ParentIntegralTerms-finish"></a>
### `ParentIntegralTerms.finish`

读取池已证明全部EOF后，仅补到实际观测末端。

```python
ParentIntegralTerms.finish(observed_end)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`observed_end`|int &#124; None|是|无|位置或关键字。所有文件真正EOF后的实际观测末端纳秒；无观测时为None，不超出输入范围补造尾段。|

#### 返回说明

None。

#### 异常说明

未完成文件、时间倒退或原累计错误。

源码：[`src/chronaxis/execution/file_integral_terms.py:578`](../../../src/chronaxis/execution/file_integral_terms.py#L578)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-ParentIntegralTerms-close"></a>
### `ParentIntegralTerms.close`

释放自有边界状态，外部积分器由父会话关闭。

```python
ParentIntegralTerms.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

退款失败可重试。

源码：[`src/chronaxis/execution/file_integral_terms.py:600`](../../../src/chronaxis/execution/file_integral_terms.py#L600)（行号对应 Chronaxis 0.1.0.dev5 源码）。
