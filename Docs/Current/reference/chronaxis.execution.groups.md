# chronaxis.execution.groups

把已封存且全部来源EOF的历史归并为完整同一时刻更新组。

输入只来自已解码磁盘历史，整数纳秒排序不会重读或重排旧文件链。
每来源一个前瞻样本，跨批同一时刻更新全部收入同一组；不同原序号不collapse。
游标、有限堆和当前组计入共用的资源用量记录，超大组明确失败，不缓存全量历史。
本组件是离线封存重放，不冒充未完成输入的在线watermark调度或算子执行。
返回组须即时消费，调用方自行长期保留输出的内存不在内部预算保证内。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisError](chronaxis.results.errors.md#api-AnalysisError)、[HistoryProgress](chronaxis.execution.history_records.md#api-HistoryProgress)、[HistorySample](chronaxis.execution.history_records.md#api-HistorySample)、[RecordSample](chronaxis.execution.record_sample.md#api-RecordSample)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[ResultFormatError](chronaxis.results.errors.md#api-ResultFormatError)

## 对象导航

|对象|用途|
|---|---|
|[`DecodedTimeGroup`](#api-DecodedTimeGroup)|保存一个session在同一整数ns的全部更新；来源和原sequence仍独立。|
|[`DecodedTimeGroup.__post_init__`](#api-DecodedTimeGroup-__post_init__)|检查同一时刻、同会话和唯一原身份，不执行绑定或表达式。|
|[`_TimeGroupIterator`](#api-_TimeGroupIterator)|保留有限来源前瞻、当前组预算及活动游标。|
|[`_TimeGroupIterator.__init__`](#api-_TimeGroupIterator-__init__)|先申请状态预算，再为已封存历史打开各来源独立游标。|
|[`_TimeGroupIterator._advance`](#api-_TimeGroupIterator-_advance)|略过保留在历史中的批次进度，读取该来源下一个真实更新。|
|[`_TimeGroupIterator.__iter__`](#api-_TimeGroupIterator-__iter__)|返回当前独立组游标。|
|[`_TimeGroupIterator.__next__`](#api-_TimeGroupIterator-__next__)|一次提交全部同一时刻更新，跨批/跨来源不拆成部分上下文。|
|[`_TimeGroupIterator.close`](#api-_TimeGroupIterator-close)|幂等关闭全部源游标并释放当前组/固定状态，不删除历史文件。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from sys import getsizeof
from ..timebase.conversion import require_int64_ns
from ..results.codec import _estimate
from ..results.errors import AnalysisError, ResultClosedError, ResultFormatError
from ..results.spool import _cleanup_owner, _reserve_owned_ram, _release_owned_ram
from .record_sample import RecordSample
from .history_records import HistorySample, HistoryProgress, estimate_record_bytes
```

</details>

<a id="api-DecodedTimeGroup"></a>
## `DecodedTimeGroup`

保存一个session在同一整数ns的全部更新；来源和原sequence仍独立。

```python
class DecodedTimeGroup
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|完整组的共同纳秒坐标。|
|`samples`|tuple[[HistorySample](chronaxis.execution.history_records.md#api-HistorySample), ...]|是|无|同组全部原观测，不套用last_by_sequence策略。|

源码：[`src/chronaxis/execution/groups.py:23`](../../../src/chronaxis/execution/groups.py#L23)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-DecodedTimeGroup-__post_init__"></a>
### `DecodedTimeGroup.__post_init__`

检查同一时刻、同会话和唯一原身份，不执行绑定或表达式。

```python
DecodedTimeGroup.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无；读取time_ns/samples。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError/OverflowError为结构或身份错误。

本函数直接报告的具体错误：

- `TypeError`：完整时间组需要非空HistorySample tuple。
- `ValueError`：时间组不能混用时间或session。
- `ValueError`：完整时间组重复原观测。

返回类型：None。

源码：[`src/chronaxis/execution/groups.py:29`](../../../src/chronaxis/execution/groups.py#L29)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_TimeGroupIterator"></a>
## `_TimeGroupIterator`

保留有限来源前瞻、当前组预算及活动游标。

readers为预分配槽位，未安装子游标由_uninstalled_reader单独持有。
close中断后保留尚未释放的句柄、组登记和预算，_closing期间需要重试close来完成关闭。
closed只在真实子资源关闭且组预算抵销后成立，不能凭尝试关闭就解除所有权。
_held_cost仅含本层_state_cost与_group_cost，不包含子reader或借用history金额。

```python
_TimeGroupIterator(owner, *, sources=None)
```


源码：[`src/chronaxis/execution/groups.py:46`](../../../src/chronaxis/execution/groups.py#L46)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_TimeGroupIterator-__init__"></a>
### `_TimeGroupIterator.__init__`

先申请状态预算，再为已封存历史打开各来源独立游标。

```python
_TimeGroupIterator.__init__(owner, *, sources=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|DecodedHistoryStore|是|无|位置或关键字。owner为DecodedHistoryStore|
|`sources`|tuple &#124; None|否|None|仅关键字。sources为唯一已知来源名tuple，None选择全部。|

#### 返回说明

新组迭代器，只有所选来源参与完整同一时刻组。

#### 异常说明

生命周期/预算/打开或解析原错；持续清理失败从time_group_iterator_cleanup_owner恢复。

本函数直接报告的具体错误：

- `TypeError`：时间组来源子集需要来源名tuple或None。
- `ValueError`：时间组来源子集包含未知来源。
- `ValueError`：时间组来源子集不能重复。

源码：[`src/chronaxis/execution/groups.py:55`](../../../src/chronaxis/execution/groups.py#L55)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_TimeGroupIterator-_advance"></a>
### `_TimeGroupIterator._advance`

略过保留在历史中的批次进度，读取该来源下一个真实更新。

```python
_TimeGroupIterator._advance(index: int) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`index`|int|是|无|位置或关键字。index为固定来源游标编号。|

#### 返回说明

None，必要时heap增加一个前瞻。

#### 异常说明

历史损坏/读取错误传播；真实EOF由游标校验完整计数与摘要。

本函数直接报告的具体错误：

- `ResultFormatError`：解码历史重放时间回退。

返回类型：None。

源码：[`src/chronaxis/execution/groups.py:110`](../../../src/chronaxis/execution/groups.py#L110)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_TimeGroupIterator-__iter__"></a>
### `_TimeGroupIterator.__iter__`

返回当前独立组游标。

```python
_TimeGroupIterator.__iter__() -> '_TimeGroupIterator'
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回当前对象本身。后续迭代或with语句使用的仍是同一个对象。

#### 异常说明

无。

返回类型：'[_TimeGroupIterator](chronaxis.execution.groups.md#api-_TimeGroupIterator)'。

源码：[`src/chronaxis/execution/groups.py:128`](../../../src/chronaxis/execution/groups.py#L128)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_TimeGroupIterator-__next__"></a>
### `_TimeGroupIterator.__next__`

一次提交全部同一时刻更新，跨批/跨来源不拆成部分上下文。

```python
_TimeGroupIterator.__next__() -> DecodedTimeGroup
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

一个DecodedTimeGroup。

#### 异常说明

StopIteration为全部历史校验完成；预算/损坏/关闭错误不丢组继续。

本函数直接报告的具体错误：

- `ResultClosedError`：解码历史已关闭。
- `ResultClosedError`：完整时间组游标正在关闭。

返回类型：[DecodedTimeGroup](chronaxis.execution.groups.md#api-DecodedTimeGroup)。

源码：[`src/chronaxis/execution/groups.py:135`](../../../src/chronaxis/execution/groups.py#L135)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_TimeGroupIterator-close"></a>
### `_TimeGroupIterator.close`

幂等关闭全部源游标并释放当前组/固定状态，不删除历史文件。

```python
_TimeGroupIterator.close() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None，重复关闭安全。

#### 异常说明

首个真实子关闭错误，仍尝试其余游标；预算/取消传播。
    动作前失败保留所有权供重试，实际释放后的取消只完成最小关闭。

返回类型：None。

源码：[`src/chronaxis/execution/groups.py:184`](../../../src/chronaxis/execution/groups.py#L184)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

## 内部匿名回调


<a id="lambda-167"></a>
### 第167行匿名函数

```python
lambda item: (item.source_ref.source_name, item.sequence, item.name)
```

|参数|含义|返回/异常|
|---|---|---|
|`item`|已绑定的信号样本。|返回来源名、原序号、信号名的元组，确定同刻提交顺序。|
