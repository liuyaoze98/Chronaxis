# chronaxis.execution.window_replay

从已封存的新解码历史逐段计算一个窗口的表达式视图。

输入为实际运行绑定、原保持上下文、已编译表达式及域内Interval，坐标为整数纳秒。
先校验原历史身份，再打开独立状态与完整组游标；窗口前组只建立种子。
每步按真实更新、依赖TTL、来源终点或窗口末端拆分，返回须close的点/连续视图帧。
参考与NumPy分别调用既有独立表达式核，不物化完整样本、时间轴或帧列表。
资源属于本回读对象；原历史、调用方lease和原state借用，不重读旧报文/DBC。
提前停止不提供本次全文件EOF证明；运行绑定已有完整校验证据与部分回读分开。
新层保守预算包含前瞻、种子、查询和输出，不能代表外部留存量或进程RSS。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[BoundaryQueries](chronaxis.execution.boundaries.md#api-BoundaryQueries)、[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)、[DecodedBindings](chronaxis.core.decoded_binding.md#api-DecodedBindings)、[DecodedHistoryStore](chronaxis.execution.history.md#api-DecodedHistoryStore)、[ExpressionQueries](chronaxis.execution.expressions.md#api-ExpressionQueries)、[HoldContext](chronaxis.execution.hold.md#api-HoldContext)、[HoldQueries](chronaxis.execution.hold.md#api-HoldQueries)、[Interval](chronaxis.core.models.md#api-Interval)、[LatestSignalState](chronaxis.execution.state.md#api-LatestSignalState)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[_BatchRegistry](chronaxis.execution.temporal_buffer.md#api-_BatchRegistry)

## 对象导航

|对象|用途|
|---|---|
|[`WindowReplayFrame`](#api-WindowReplayFrame)|拥有一个时刻的点视图、可选连续视图及本步workspace。|
|[`WindowReplayFrame.__init__`](#api-WindowReplayFrame-__init__)|接收已计账的表达式结果，暂不安装登记。|
|[`WindowReplayFrame._ensure_open`](#api-WindowReplayFrame-_ensure_open)|拒绝释放或部分关闭后的读取。|
|[`WindowReplayFrame.closed`](#api-WindowReplayFrame-closed)|读取资源完成状态。|
|[`WindowReplayFrame.time_ns`](#api-WindowReplayFrame-time_ns)|读取当前点坐标。|
|[`WindowReplayFrame.end_ns`](#api-WindowReplayFrame-end_ns)|读取连续区间排除的右端。|
|[`WindowReplayFrame.point_result`](#api-WindowReplayFrame-point_result)|读取当前点表达式结果，保留actual_update和原样本。|
|[`WindowReplayFrame.continuous_result`](#api-WindowReplayFrame-continuous_result)|读取左闭右开区间的值，末点没有连续面积。|
|[`WindowReplayFrame._discard`](#api-WindowReplayFrame-_discard)|解除完整或部分链登记，不再次扣账。|
|[`WindowReplayFrame.close`](#api-WindowReplayFrame-close)|关闭子结果后释放本步申请，取消前可重试、实际扣账后最小关闭。|
|[`HistoricalWindowReplay`](#api-HistoricalWindowReplay)|以独立种子状态回读一个有限窗口，原调用方状态不变。|
|[`HistoricalWindowReplay.__init__`](#api-HistoricalWindowReplay-__init__)|先预留元数据，再核对当前历史与绑定并创建独立回读资源。|
|[`HistoricalWindowReplay.closed`](#api-HistoricalWindowReplay-closed)|查看当前对象是否已经完成关闭。|
|[`HistoricalWindowReplay.failed`](#api-HistoricalWindowReplay-failed)|读取推进失败状态。|
|[`HistoricalWindowReplay._ensure_open`](#api-HistoricalWindowReplay-_ensure_open)|检查owner及借用历史仍可用，不允许故障后继续推进。|
|[`HistoricalWindowReplay.__iter__`](#api-HistoricalWindowReplay-__iter__)|返回当前独立回读者。|
|[`HistoricalWindowReplay._seed`](#api-HistoricalWindowReplay-_seed)|逐个消费窗口前完整组，保留第一个未消费前瞻。|
|[`HistoricalWindowReplay._query`](#api-HistoricalWindowReplay-_query)|在已预留本步空间内调用原独立后端查询。|
|[`HistoricalWindowReplay.__next__`](#api-HistoricalWindowReplay-__next__)|先预算再读种子或消费更新，返回一个准确区间及当前点。|
|[`HistoricalWindowReplay.close`](#api-HistoricalWindowReplay-close)|按资源依赖关闭自有帧/查询/状态/游标，保留借用历史与原state。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..core.decoded_binding import DecodedBindings
from ..core.expression import CompiledExpression
from ..core.models import Interval
from ..results.errors import ResultClosedError
from .bindings import _fingerprint
from .boundaries import BoundaryQueries
from .expressions import ExpressionQueries
from .history import DecodedHistoryStore, _metadata_bytes
from .hold import HoldContext, HoldQueries
from .state import LatestSignalState
from .temporal_buffer import _BatchRegistry
```

</details>

<a id="api-WindowReplayFrame"></a>
## `WindowReplayFrame`

拥有一个时刻的点视图、可选连续视图及本步workspace。

连续值适用于[time_ns,end_ns)，末点帧的两端相等且continuous_result为None。
点视图可能是保持值，只有ExpressionResult.actual_update才表示真实依赖更新。
两个子结果和链指针的预算在本帧close后释放，关闭过程中拒绝读取半关闭结果。

```python
WindowReplayFrame(owner, cost, time_ns, end_ns, point, continuous)
```


源码：[`src/chronaxis/execution/window_replay.py:27`](../../../src/chronaxis/execution/window_replay.py#L27)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-WindowReplayFrame-__init__"></a>
### `WindowReplayFrame.__init__`

接收已计账的表达式结果，暂不安装登记。

```python
WindowReplayFrame.__init__(owner, cost, time_ns, end_ns, point, continuous)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|[HistoricalWindowReplay](chronaxis.execution.window_replay.md#api-HistoricalWindowReplay)|是|无|位置或关键字。创建本回读帧的历史窗口读取器，管理帧的内存和查询资源。|
|`cost`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|
|`time_ns`|int|是|无|位置或关键字。当前处理时刻，以整数纳秒表示，须在int64范围内。例如1秒写1_000_000_000；不是浮点秒。|
|`end_ns`|int|是|无|位置或关键字。time_ns/end_ns为整数ns|
|`point`|ExpressionResult|是|无|位置或关键字。当前时刻的点值查询结果；保留实际更新和来源信息。|
|`continuous`|ExpressionResult &#124; None|是|无|位置或关键字。当前连续片段的表达式结果；不存在连续片段时为None。|

#### 返回说明

新帧。

#### 异常说明

构造失败由调用方回收子结果和workspace。

源码：[`src/chronaxis/execution/window_replay.py:35`](../../../src/chronaxis/execution/window_replay.py#L35)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-WindowReplayFrame-_ensure_open"></a>
### `WindowReplayFrame._ensure_open`

拒绝释放或部分关闭后的读取。

```python
WindowReplayFrame._ensure_open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ResultClosedError。

本函数直接报告的具体错误：

- `ResultClosedError`：窗口回读帧已关闭或正在关闭。

源码：[`src/chronaxis/execution/window_replay.py:47`](../../../src/chronaxis/execution/window_replay.py#L47)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-WindowReplayFrame-closed"></a>
### `WindowReplayFrame.closed`

读取资源完成状态。

```python
WindowReplayFrame.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/execution/window_replay.py:56`](../../../src/chronaxis/execution/window_replay.py#L56)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-WindowReplayFrame-time_ns"></a>
### `WindowReplayFrame.time_ns`

读取当前点坐标。

```python
WindowReplayFrame.time_ns
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

int纳秒。

#### 异常说明

关闭时拒绝。

源码：[`src/chronaxis/execution/window_replay.py:61`](../../../src/chronaxis/execution/window_replay.py#L61)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-WindowReplayFrame-end_ns"></a>
### `WindowReplayFrame.end_ns`

读取连续区间排除的右端。

```python
WindowReplayFrame.end_ns
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

int纳秒。

#### 异常说明

关闭时拒绝。

源码：[`src/chronaxis/execution/window_replay.py:67`](../../../src/chronaxis/execution/window_replay.py#L67)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-WindowReplayFrame-point_result"></a>
### `WindowReplayFrame.point_result`

读取当前点表达式结果，保留actual_update和原样本。

```python
WindowReplayFrame.point_result
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

ExpressionResult。

#### 异常说明

关闭时拒绝。

源码：[`src/chronaxis/execution/window_replay.py:73`](../../../src/chronaxis/execution/window_replay.py#L73)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-WindowReplayFrame-continuous_result"></a>
### `WindowReplayFrame.continuous_result`

读取左闭右开区间的值，末点没有连续面积。

```python
WindowReplayFrame.continuous_result
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

ExpressionResult或None。

#### 异常说明

关闭时拒绝。

源码：[`src/chronaxis/execution/window_replay.py:82`](../../../src/chronaxis/execution/window_replay.py#L82)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-WindowReplayFrame-_discard"></a>
### `WindowReplayFrame._discard`

解除完整或部分链登记，不再次扣账。

```python
WindowReplayFrame._discard()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

登记取消仍在finally关闭字段。

源码：[`src/chronaxis/execution/window_replay.py:90`](../../../src/chronaxis/execution/window_replay.py#L90)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-WindowReplayFrame-close"></a>
### `WindowReplayFrame.close`

关闭子结果后释放本步申请，取消前可重试、实际扣账后最小关闭。

```python
WindowReplayFrame.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None。关闭成功后再次调用不会重复释放同一份资源。

#### 异常说明

子关闭/预算/取消传播。

源码：[`src/chronaxis/execution/window_replay.py:103`](../../../src/chronaxis/execution/window_replay.py#L103)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalWindowReplay"></a>
## `HistoricalWindowReplay`

以独立种子状态回读一个有限窗口，原调用方状态不变。

_front由完整组游标持有且计账，消费以后才请求下一组；不另存历史列表。
输出帧登记在固定头指针链中，先前帧在后续失败后仍可读取。
单线程推进失败不可重试；close可重试并关闭自有查询、状态和游标。
迭代完成仍须close，以便调用方保留最后帧；完成窗口不等于全文件重放到EOF。

```python
HistoricalWindowReplay(history: DecodedHistoryStore, context: HoldContext, bindings: DecodedBindings, compiled: CompiledExpression, interval: Interval, *, backend='numpy')
```


源码：[`src/chronaxis/execution/window_replay.py:127`](../../../src/chronaxis/execution/window_replay.py#L127)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalWindowReplay-__init__"></a>
### `HistoricalWindowReplay.__init__`

先预留元数据，再核对当前历史与绑定并创建独立回读资源。

```python
HistoricalWindowReplay.__init__(history: DecodedHistoryStore, context: HoldContext, bindings: DecodedBindings, compiled: CompiledExpression, interval: Interval, *, backend='numpy')
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`history`|[DecodedHistoryStore](chronaxis.execution.history.md#api-DecodedHistoryStore)|是|无|位置或关键字。history为sealed新历史|
|`context`|[HoldContext](chronaxis.execution.hold.md#api-HoldContext)|是|无|位置或关键字。context为原域与来源EOF事实|
|`bindings`|[DecodedBindings](chronaxis.core.decoded_binding.md#api-DecodedBindings)|是|无|位置或关键字。bindings为实际绑定|
|`compiled`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)|是|无|位置或关键字。compiled为该绑定的表达式|
|`interval`|[Interval](chronaxis.core.models.md#api-Interval)|是|无|位置或关键字。interval为域内含点端的窗口|
|`backend`|str|否|'numpy'|仅关键字。`"reference"`使用独立参考计算；`"numpy"`使用NumPy数组计算。须明确选择一种。|

#### 返回说明

尚未读入种子的新回读者。

#### 异常说明

类型/域/来源身份/预算/构造取消；保留原异常，不关闭借用历史。
    持续清理失败时，从异常的window_replay_cleanup_owner取得自有恢复句柄。

源码：[`src/chronaxis/execution/window_replay.py:136`](../../../src/chronaxis/execution/window_replay.py#L136)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalWindowReplay-closed"></a>
### `HistoricalWindowReplay.closed`

查看当前对象是否已经完成关闭。

```python
HistoricalWindowReplay.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/execution/window_replay.py:222`](../../../src/chronaxis/execution/window_replay.py#L222)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalWindowReplay-failed"></a>
### `HistoricalWindowReplay.failed`

读取推进失败状态。

```python
HistoricalWindowReplay.failed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象已记录处理失败；False表示尚未记录失败。

#### 异常说明

无。

源码：[`src/chronaxis/execution/window_replay.py:227`](../../../src/chronaxis/execution/window_replay.py#L227)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalWindowReplay-_ensure_open"></a>
### `HistoricalWindowReplay._ensure_open`

检查owner及借用历史仍可用，不允许故障后继续推进。

```python
HistoricalWindowReplay._ensure_open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ResultClosedError。

本函数直接报告的具体错误：

- `ResultClosedError`：窗口回读已关闭、正在关闭或推进失败。

源码：[`src/chronaxis/execution/window_replay.py:231`](../../../src/chronaxis/execution/window_replay.py#L231)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalWindowReplay-__iter__"></a>
### `HistoricalWindowReplay.__iter__`

返回当前独立回读者。

```python
HistoricalWindowReplay.__iter__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回当前对象本身。后续迭代或with语句使用的仍是同一个对象。

#### 异常说明

无。

源码：[`src/chronaxis/execution/window_replay.py:240`](../../../src/chronaxis/execution/window_replay.py#L240)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalWindowReplay-_seed"></a>
### `HistoricalWindowReplay._seed`

逐个消费窗口前完整组，保留第一个未消费前瞻。

```python
HistoricalWindowReplay._seed()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

真实历史/原子state错误传播，外层标失败。

源码：[`src/chronaxis/execution/window_replay.py:244`](../../../src/chronaxis/execution/window_replay.py#L244)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalWindowReplay-_query"></a>
### `HistoricalWindowReplay._query`

在已预留本步空间内调用原独立后端查询。

```python
HistoricalWindowReplay._query(*, point)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`point`|bool|是|无|仅关键字。True查询该时刻的点值，False查询连续区间所用的保持值。|

#### 返回说明

须close的ExpressionResult。

#### 异常说明

原保持/表达式/预算错误传播；数组shape=(1,), int64纳秒。

源码：[`src/chronaxis/execution/window_replay.py:257`](../../../src/chronaxis/execution/window_replay.py#L257)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalWindowReplay-__next__"></a>
### `HistoricalWindowReplay.__next__`

先预算再读种子或消费更新，返回一个准确区间及当前点。

```python
HistoricalWindowReplay.__next__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

WindowReplayFrame；末点连续视图为None。

#### 异常说明

StopIteration表示窗口完成；任何推进故障标failed，先前输出保持。

源码：[`src/chronaxis/execution/window_replay.py:267`](../../../src/chronaxis/execution/window_replay.py#L267)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-HistoricalWindowReplay-close"></a>
### `HistoricalWindowReplay.close`

按资源依赖关闭自有帧/查询/状态/游标，保留借用历史与原state。

```python
HistoricalWindowReplay.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None。关闭成功后再次调用不会重复释放同一份资源。

#### 异常说明

子关闭/预算取消，保留尚未完成句柄供重试。

源码：[`src/chronaxis/execution/window_replay.py:325`](../../../src/chronaxis/execution/window_replay.py#L325)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
