# `chronaxis.execution.transform_stream`

在原始记录流及下游规则之间插入按需的时序变换。

每一层只持有自己的最新输入、滚动窗口，以及固定周期等待后帧确认时尚未
交付的有界原组。待同一时刻的原更新与变换值均齐全，再原子交给下层。
无全会话网格、输入重扫或对照时间列；预算、取消和真实EOF沿主执行器。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)、[DecodedTimeGroup](chronaxis.execution.groups.md#api-DecodedTimeGroup)、[DriverExpression](chronaxis.execution.driver_expression.md#api-DriverExpression)、[LatestSignalState](chronaxis.execution.state.md#api-LatestSignalState)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[RecordSample](chronaxis.execution.record_sample.md#api-RecordSample)、[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)、[SourceRef](chronaxis.core.models.md#api-SourceRef)、[TransformSpan](chronaxis.execution.transform_window.md#api-TransformSpan)、[TransformWindow](chronaxis.execution.transform_window.md#api-TransformWindow)

## 对象导航

|对象|用途|
|---|---|
|[`TransformStage`](#api-TransformStage)|拥有一层的状态与前瞻，向唯一后继按实际时间递增地交付组。|
|[`TransformStage.__init__`](#api-TransformStage-__init__)||
|[`TransformStage._ensure_active`](#api-TransformStage-_ensure_active)|拒绝关闭或失败后的继续推进，避免重发未完成网格。|
|[`TransformStage.bounds`](#api-TransformStage-bounds)|取得实际可观测起点和已知终点。|
|[`TransformStage._invalid`](#api-TransformStage-_invalid)|构造明确未知的输出。|
|[`TransformStage._sample`](#api-TransformStage-_sample)|构造离散输出。|
|[`TransformStage._at_grid`](#api-TransformStage-_at_grid)|从原区间读取[t-W,t)及变化率端点。|
|[`TransformStage._convert_rate`](#api-TransformStage-_convert_rate)|换算变化率目标单位。|
|[`TransformStage._deliver`](#api-TransformStage-_deliver)|同一时刻真实更新与离散输出一次交付。|
|[`TransformStage._drain`](#api-TransformStage-_drain)|按网格和原组时间归并。|
|[`TransformStage._append_span`](#api-TransformStage-_append_span)|闭合上一条原始保持。|
|[`TransformStage.push`](#api-TransformStage-push)|消费上游完整组。|
|[`TransformStage._flush_waiting`](#api-TransformStage-_flush_waiting)|以已确认的原对处理所有待定组。|
|[`TransformStage._process`](#api-TransformStage-_process)|按已知计量推进原更新和网格。|
|[`TransformStage.finish`](#api-TransformStage-finish)|完成真正EOF后标记宿主状态正常结束。|
|[`TransformStage._finish_grid`](#api-TransformStage-_finish_grid)|按真实来源EOF补最后可定网格，缺少后继原帧不外推周期。|
|[`TransformStage.close`](#api-TransformStage-close)|清理等待组、真实区间和最新值。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from collections import deque
from dataclasses import replace
from fractions import Fraction
from ..core.numeric import ScalarValue
from ..core.types import QualityFlag as Q, SignalDType as D
from ..core.models import SourceRef
from ..results.budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from .driver_expression import DriverExpression
from .groups import DecodedTimeGroup
from .history_records import estimate_record_bytes
from .record_sample import RecordSample
from .state import LatestSignalState
from .transform_window import TransformSpan, TransformWindow, first_grid
```

</details>

<a id="api-TransformStage"></a>
## `TransformStage`

拥有一层的状态与前瞻，向唯一后继按实际时间递增地交付组。

```python
TransformStage(plan, item, defs, choice, period, ends, cursors, budget, emit)
```


源码：[`src/chronaxis/execution/transform_stream.py:22`](../../../src/chronaxis/execution/transform_stream.py#L22)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-TransformStage-__init__"></a>
### `TransformStage.__init__`



```python
TransformStage.__init__(plan, item, defs, choice, period, ends, cursors, budget, emit)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|AnalysisPlan|是|无|位置或关键字。本次实际执行的完整计划，提供后端、会话、绑定及输入依赖。|
|`item`|TemporalTransformPlan|是|无|位置或关键字。该阶段单独负责的一个时序声明，包含运算、输入、窗口和输出身份。|
|`defs`|Sequence[SignalDefinition]|是|无|位置或关键字。上游已核实的信号定义，包括本级可能消费的先前时序输出。|
|`choice`|IntervalChoice|是|无|位置或关键字。解析出的actual、fixed或dbc口径及其原报文驱动名。|
|`period`|int &#124; None|是|无|位置或关键字。已核实的固定或DBC周期纳秒；actual模式没有替代周期。|
|`ends`|dict[str, int]|是|无|位置或关键字。父执行器共享的各来源观测结束时间表，用于界定有效保持与EOF。|
|`cursors`|Mapping[str, RecordSourceCursor]|是|无|位置或关键字。原始来源名到实际读取游标的映射，用于查询观测首末和读取是否完成。|
|`budget`|ResourceBudget|是|无|位置或关键字。本会话共用的资源用量记录，计入本级状态、待后帧补算的组及窗口工作数组。|
|`emit`|Callable[[[DecodedTimeGroup](chronaxis.execution.groups.md#api-DecodedTimeGroup)], None]|是|无|位置或关键字。下一级唯一的组消费者，将按实际时间和原子归组顺序接收结果。|

#### 返回说明

owner。

#### 异常说明

预算/绑定错误。

源码：[`src/chronaxis/execution/transform_stream.py:25`](../../../src/chronaxis/execution/transform_stream.py#L25)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-TransformStage-_ensure_active"></a>
### `TransformStage._ensure_active`

拒绝关闭或失败后的继续推进，避免重发未完成网格。

```python
TransformStage._ensure_active()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

生命周期错误。

源码：[`src/chronaxis/execution/transform_stream.py:69`](../../../src/chronaxis/execution/transform_stream.py#L69)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-TransformStage-bounds"></a>
### `TransformStage.bounds`

取得实际可观测起点和已知终点。

```python
TransformStage.bounds()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

起点/可选终点。

#### 异常说明

游标错误。

源码：[`src/chronaxis/execution/transform_stream.py:75`](../../../src/chronaxis/execution/transform_stream.py#L75)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-TransformStage-_invalid"></a>
### `TransformStage._invalid`

构造明确未知的输出。

```python
TransformStage._invalid(quality)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`quality`|QualityFlag|是|无|位置或关键字。构造无效时序结果的具体原因位，未提供原因时使用MISSING。|

#### 返回说明

ScalarValue。

#### 异常说明

非法质量位。

源码：[`src/chronaxis/execution/transform_stream.py:90`](../../../src/chronaxis/execution/transform_stream.py#L90)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-TransformStage-_sample"></a>
### `TransformStage._sample`

构造离散输出。

```python
TransformStage._sample(t, value)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`t`|int|是|无|位置或关键字。当前实际时间的整数纳秒，用于定位新样本、网格或区间终点。|
|`value`|[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)|是|无|位置或关键字。当前网格或实测右侧计算得到的变换值，带输出dtype和有效性。|

#### 返回说明

RecordSample。

#### 异常说明

模型错误。

源码：[`src/chronaxis/execution/transform_stream.py:94`](../../../src/chronaxis/execution/transform_stream.py#L94)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-TransformStage-_at_grid"></a>
### `TransformStage._at_grid`

从原区间读取[t-W,t)及变化率端点。

```python
TransformStage._at_grid(t, point, update)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`t`|int|是|无|位置或关键字。当前实际时间的整数纳秒，用于定位新样本、网格或区间终点。|
|`point`|[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue) &#124; None|是|无|位置或关键字。同一时刻可用的输入点查询结果；没有真实同一时刻点时可为空。|
|`update`|bool|是|无|位置或关键字。该点是否确有活动数值依赖更新，用来区分真实样本与保持/裁剪边界。|

#### 返回说明

ScalarValue。

#### 异常说明

预算/数值错误。

源码：[`src/chronaxis/execution/transform_stream.py:100`](../../../src/chronaxis/execution/transform_stream.py#L100)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-TransformStage-_convert_rate"></a>
### `TransformStage._convert_rate`

换算变化率目标单位。

```python
TransformStage._convert_rate(value)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)|是|无|位置或关键字。使用输入自然尺度每秒表示的差分或拟合值，之后换为声明的速率单位。|

#### 返回说明

新标量。

#### 异常说明

转换错误。

源码：[`src/chronaxis/execution/transform_stream.py:166`](../../../src/chronaxis/execution/transform_stream.py#L166)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-TransformStage-_deliver"></a>
### `TransformStage._deliver`

同一时刻真实更新与离散输出一次交付。

```python
TransformStage._deliver(group, t, value=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`group`|[DecodedTimeGroup](chronaxis.execution.groups.md#api-DecodedTimeGroup) &#124; None|是|无|位置或关键字。与输出同一时刻的原始组；纯定时网格输出可能没有上游组。|
|`t`|int|是|无|位置或关键字。当前实际时间的整数纳秒，用于定位新样本、网格或区间终点。|
|`value`|[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue) &#124; None|否|None|位置或关键字。此次需要附加到组中的离散变换值，若无产出则只转发原组。|

#### 返回说明

无。

#### 异常说明

下游错误。

源码：[`src/chronaxis/execution/transform_stream.py:178`](../../../src/chronaxis/execution/transform_stream.py#L178)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-TransformStage-_drain"></a>
### `TransformStage._drain`

按网格和原组时间归并。

```python
TransformStage._drain(group, point=None, update=False, *, through=None, unresolved=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`group`|[DecodedTimeGroup](chronaxis.execution.groups.md#api-DecodedTimeGroup) &#124; None|是|无|位置或关键字。等待与已定网格结果归并的上游组，EOF补齐时可为空。|
|`point`|[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue) &#124; None|否|None|位置或关键字。同一时刻可用的输入点查询结果；没有真实同一时刻点时可为空。|
|`update`|bool|否|False|位置或关键字。该点是否确有活动数值依赖更新，用来区分真实样本与保持/裁剪边界。|
|`through`|int &#124; None|否|None|仅关键字。无原组时允许补网格到的实际截止纳秒，不能超出已知观测。|
|`unresolved`|bool|否|False|仅关键字。为真表示固定/DBC驱动缺少后继帧，不能推断不完整周期的宽度。|

#### 返回说明

无。

#### 异常说明

下游/预算错误。

源码：[`src/chronaxis/execution/transform_stream.py:187`](../../../src/chronaxis/execution/transform_stream.py#L187)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-TransformStage-_append_span"></a>
### `TransformStage._append_span`

闭合上一条原始保持。

```python
TransformStage._append_span(t, pair_width=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`t`|int|是|无|位置或关键字。当前实际时间的整数纳秒，用于定位新样本、网格或区间终点。|
|`pair_width`|int &#124; None|否|None|位置或关键字。相邻两次原驱动的实际间隔纳秒，用于将组内重叠比例折算为选定周期；未知时为空。|

#### 返回说明

无。

#### 异常说明

预算/顺序错误。

源码：[`src/chronaxis/execution/transform_stream.py:229`](../../../src/chronaxis/execution/transform_stream.py#L229)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-TransformStage-push"></a>
### `TransformStage.push`

消费上游完整组。

```python
TransformStage.push(group)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`group`|[DecodedTimeGroup](chronaxis.execution.groups.md#api-DecodedTimeGroup)|是|无|位置或关键字。来自上游的一个已原子归并的实际时间组，包括信号更新和来源。|

#### 返回说明

无；向后继交付。

#### 异常说明

原输入/预算/求值错误。

源码：[`src/chronaxis/execution/transform_stream.py:235`](../../../src/chronaxis/execution/transform_stream.py#L235)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-TransformStage-_flush_waiting"></a>
### `TransformStage._flush_waiting`

以已确认的原对处理所有待定组。

```python
TransformStage._flush_waiting(width)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`width`|int &#124; None|是|无|位置或关键字。相邻两次原驱动的实际间隔纳秒，用于将组内重叠比例折算为选定周期；未知时为空。|

#### 返回说明

无。

#### 异常说明

交付/退款错误。

源码：[`src/chronaxis/execution/transform_stream.py:262`](../../../src/chronaxis/execution/transform_stream.py#L262)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-TransformStage-_process"></a>
### `TransformStage._process`

按已知计量推进原更新和网格。

```python
TransformStage._process(group, width, *, unresolved=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`group`|[DecodedTimeGroup](chronaxis.execution.groups.md#api-DecodedTimeGroup)|是|无|位置或关键字。来自上游的一个已原子归并的实际时间组，包括信号更新和来源。|
|`width`|int &#124; None|是|无|位置或关键字。相邻两次原驱动的实际间隔纳秒，用于将组内重叠比例折算为选定周期；未知时为空。|
|`unresolved`|bool|否|False|仅关键字。为真表示固定/DBC驱动缺少后继帧，不能推断不完整周期的宽度。|

#### 返回说明

无。

#### 异常说明

原错。

源码：[`src/chronaxis/execution/transform_stream.py:270`](../../../src/chronaxis/execution/transform_stream.py#L270)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-TransformStage-finish"></a>
### `TransformStage.finish`

完成真正EOF后标记宿主状态正常结束。

```python
TransformStage.finish()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

最后网格失败仍通知取消。

源码：[`src/chronaxis/execution/transform_stream.py:316`](../../../src/chronaxis/execution/transform_stream.py#L316)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-TransformStage-_finish_grid"></a>
### `TransformStage._finish_grid`

按真实来源EOF补最后可定网格，缺少后继原帧不外推周期。

```python
TransformStage._finish_grid()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

无。

#### 异常说明

交付错误。

源码：[`src/chronaxis/execution/transform_stream.py:322`](../../../src/chronaxis/execution/transform_stream.py#L322)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-TransformStage-close"></a>
### `TransformStage.close`

清理等待组、真实区间和最新值。

```python
TransformStage.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

无。

#### 异常说明

退款失败可重试。

源码：[`src/chronaxis/execution/transform_stream.py:337`](../../../src/chronaxis/execution/transform_stream.py#L337)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
