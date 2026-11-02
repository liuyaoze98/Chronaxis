# chronaxis.execution.window_delta_events

从封存信号历史逐窗计算变化量，交付已有点事件模型。

每次只执行一个规则，复用HistoricalWindowReplay的有限ZOH及两后端表达式查询。
新更新和旧边界移出窗口都推进判断；只保存当前窗口片段，内存不足明确失败。
数值核输出条件，独立边沿检测器负责初始化和重触发；once仅抑制后续事件，
不会把仍成立的条件伪装成FALSE。自有回读、当前帧、片段及事件批均计预算；
编译树、原历史和实际绑定借用。调用方必须close，不重读或修改原始来源。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[BudgetedTemporalDetector](chronaxis.execution.temporal_buffer.md#api-BudgetedTemporalDetector)、[ConditionTick](chronaxis.core.temporal.md#api-ConditionTick)、[DeltaSpan](chronaxis.core.window_delta.md#api-DeltaSpan)、[HistoricalWindowReplay](chronaxis.execution.window_replay.md#api-HistoricalWindowReplay)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[SourceRef](chronaxis.core.models.md#api-SourceRef)、[TemporalRule](chronaxis.core.temporal.md#api-TemporalRule)、[Truth](chronaxis.core.types.md#api-Truth)

## 对象导航

|对象|用途|
|---|---|
|[`WindowDeltaEvents`](#api-WindowDeltaEvents)|拥有一个规则的滑动片段与事件批，失败后只能关闭；关闭可重试。|
|[`WindowDeltaEvents.__init__`](#api-WindowDeltaEvents-__init__)|保存借用合同并预约有限元数据，延迟打开第一条规则的回读。|
|[`WindowDeltaEvents.__iter__`](#api-WindowDeltaEvents-__iter__)|返回本游标。|
|[`WindowDeltaEvents._start_rule`](#api-WindowDeltaEvents-_start_rule)|在上一规则资源关闭后打开下一有效观测范围。|
|[`WindowDeltaEvents._capture_value`](#api-WindowDeltaEvents-_capture_value)|从一个已计账表达式视图取原生数值及质量。|
|[`WindowDeltaEvents._capture_frame`](#api-WindowDeltaEvents-_capture_frame)|预付当前片段，再保存点值与右侧有效性；不复制输入样本。|
|[`WindowDeltaEvents._evaluate`](#api-WindowDeltaEvents-_evaluate)|计算当前窗口并推进独立边沿状态，最多借出一个事件。|
|[`WindowDeltaEvents.__next__`](#api-WindowDeltaEvents-__next__)|逐帧或窗口边界推进直到有事件，跨输入批次保留当前窗口。|
|[`WindowDeltaEvents._close_rule`](#api-WindowDeltaEvents-_close_rule)|关闭本规则自有资源并释放窗口存储，成功后才清owner槽。|
|[`WindowDeltaEvents.close`](#api-WindowDeltaEvents-close)|释放全部自有资源，保留原历史/绑定；关闭失败可重试。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from collections import deque
from dataclasses import replace
from ..core.models import SourceRef
from ..core.temporal import ConditionTick, TemporalRule
from ..core.types import QualityFlag as Q, Truth
from ..core.window_delta import DeltaSpan
from ..core.window_delta_reference import window_delta_reference
from ..core.window_delta_numpy import window_delta_numpy
from ..results.errors import ResultClosedError
from ..results.spool import _cleanup_owner, _reserve_owned_ram, _release_owned_ram
from .history import _metadata_bytes
from .temporal_buffer import BudgetedTemporalDetector
from .window_replay import HistoricalWindowReplay
```

</details>

<a id="api-WindowDeltaEvents"></a>
## `WindowDeltaEvents`

拥有一个规则的滑动片段与事件批，失败后只能关闭；关闭可重试。

```python
WindowDeltaEvents(history, context, bindings, plan, compiled_rules, scopes=None)
```


源码：[`src/chronaxis/execution/window_delta_events.py:25`](../../../src/chronaxis/execution/window_delta_events.py#L25)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-WindowDeltaEvents-__init__"></a>
### `WindowDeltaEvents.__init__`

保存借用合同并预约有限元数据，延迟打开第一条规则的回读。

```python
WindowDeltaEvents.__init__(history, context, bindings, plan, compiled_rules, scopes=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`history`|DecodedHistoryStore|是|无|位置或关键字。本次读取建立的信号历史仓。写入已经结束；分析从仓内回读，不重新打开原始日志。|
|`context`|HoldContext|是|无|位置或关键字。本次历史读取的会话和来源范围信息，用来建立保持查询。|
|`bindings`|DecodedBindings|是|无|位置或关键字。本次读取对应的信号绑定，记录别名实际对应的来源与定义；不能替换成另一次运行的绑定。|
|`plan`|AnalysisPlan|是|无|位置或关键字。包含window_delta规则与计算设置的AnalysisPlan。|
|`compiled_rules`|tuple[tuple[RulePlan, CompiledExpression], ...]|是|无|位置或关键字。每项依次为窗口增量规则和该规则实际使用的编译表达式。|
|`scopes`|HistoricalObservationScopes &#124; None|否|None|位置或关键字。各来源及信号依赖的实际观测范围，防止窗口越过已知数据边界。 None沿用context.domain作为计算范围。|

#### 返回说明

Event迭代owner。

#### 异常说明

预算或取消，持续清理失败附window_delta_events_cleanup_owner。

源码：[`src/chronaxis/execution/window_delta_events.py:28`](../../../src/chronaxis/execution/window_delta_events.py#L28)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-WindowDeltaEvents-__iter__"></a>
### `WindowDeltaEvents.__iter__`

返回本游标。

```python
WindowDeltaEvents.__iter__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回当前对象本身。后续迭代或with语句使用的仍是同一个对象。

#### 异常说明

无。

源码：[`src/chronaxis/execution/window_delta_events.py:49`](../../../src/chronaxis/execution/window_delta_events.py#L49)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-WindowDeltaEvents-_start_rule"></a>
### `WindowDeltaEvents._start_rule`

在上一规则资源关闭后打开下一有效观测范围。

```python
WindowDeltaEvents._start_rule()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

bool表示已创建规则。

#### 异常说明

构造、预算和实际范围错误。

源码：[`src/chronaxis/execution/window_delta_events.py:53`](../../../src/chronaxis/execution/window_delta_events.py#L53)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-WindowDeltaEvents-_capture_value"></a>
### `WindowDeltaEvents._capture_value`

从一个已计账表达式视图取原生数值及质量。

```python
WindowDeltaEvents._capture_value(result)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`result`|Evaluation &#124; ArrayEvaluation|是|无|位置或关键字。参考实现的单点结果，或NumPy实现的结果列；从中保留当前值及质量用于窗口增量判断。|

#### 返回说明

(value,quality)。

#### 异常说明

上游结构错误。

源码：[`src/chronaxis/execution/window_delta_events.py:79`](../../../src/chronaxis/execution/window_delta_events.py#L79)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-WindowDeltaEvents-_capture_frame"></a>
### `WindowDeltaEvents._capture_frame`

预付当前片段，再保存点值与右侧有效性；不复制输入样本。

```python
WindowDeltaEvents._capture_frame()
```

参数：无显式参数。


#### 参数说明

无，使用自有当前frame。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

预算、类型和上游错误。

源码：[`src/chronaxis/execution/window_delta_events.py:90`](../../../src/chronaxis/execution/window_delta_events.py#L90)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-WindowDeltaEvents-_evaluate"></a>
### `WindowDeltaEvents._evaluate`

计算当前窗口并推进独立边沿状态，最多借出一个事件。

```python
WindowDeltaEvents._evaluate()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

Event或None，借至下一次迭代/关闭。

#### 异常说明

数值契约、预算或取消。

源码：[`src/chronaxis/execution/window_delta_events.py:103`](../../../src/chronaxis/execution/window_delta_events.py#L103)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-WindowDeltaEvents-__next__"></a>
### `WindowDeltaEvents.__next__`

逐帧或窗口边界推进直到有事件，跨输入批次保留当前窗口。

```python
WindowDeltaEvents.__next__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

Event。

#### 异常说明

StopIteration正常结束；失败后需close。

本函数直接报告的具体错误：

- `ResultClosedError`：窗口变化量已关闭或失败。

源码：[`src/chronaxis/execution/window_delta_events.py:151`](../../../src/chronaxis/execution/window_delta_events.py#L151)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-WindowDeltaEvents-_close_rule"></a>
### `WindowDeltaEvents._close_rule`

关闭本规则自有资源并释放窗口存储，成功后才清owner槽。

```python
WindowDeltaEvents._close_rule()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

子关闭或预算取消，可再次调用。

源码：[`src/chronaxis/execution/window_delta_events.py:193`](../../../src/chronaxis/execution/window_delta_events.py#L193)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-WindowDeltaEvents-close"></a>
### `WindowDeltaEvents.close`

释放全部自有资源，保留原历史/绑定；关闭失败可重试。

```python
WindowDeltaEvents.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None。关闭成功后再次调用不会重复释放同一份资源。

#### 异常说明

子层或账本清理错误。

源码：[`src/chronaxis/execution/window_delta_events.py:209`](../../../src/chronaxis/execution/window_delta_events.py#L209)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
