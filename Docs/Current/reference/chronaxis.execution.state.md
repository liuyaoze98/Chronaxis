# `chronaxis.execution.state`

保存每个信号最新的值。同一时刻的全部更新收齐后一起写入状态，表达式不会看到“电压已更新、电流还未更新”的半成品。状态还保存时间、有效期和质量原因。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[DecodedTimeGroup](chronaxis.execution.groups.md#api-DecodedTimeGroup)、[HistorySample](chronaxis.execution.history_records.md#api-HistorySample)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[RunSession](chronaxis.execution.run_session.md#api-RunSession)、[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)、[SignalDType](chronaxis.core.types.md#api-SignalDType)、[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)

## 对象导航

|对象|用途|
|---|---|
|[`CommittedUpdates`](#api-CommittedUpdates)|保存一次原子提交结果，别名唯一，原seq/ref/质量及显式冲突数量保留。|
|[`CommittedUpdates.__post_init__`](#api-CommittedUpdates-__post_init__)|复用完整组检查时间/身份，再限制每别名仅有一个选定观测。|
|[`_committed_from_validated_fields`](#api-_committed_from_validated_fields)|包装本次已完成绑定/冲突选择的结果，不再遍历一次时间组。|
|[`_same_fact`](#api-_same_fact)|按现有核心比较逻辑值/类型/valid/quality，NaN诊断可以同因一致。|
|[`_StateSnapshot`](#api-_StateSnapshot)|持有一次完整提交的只读映射、时间、冲突计数与预算量；安装后字段不可改。|
|[`LatestSignalState`](#api-LatestSignalState)|持有固定声明与每别名一个最新记录；成功完整组严格递增，不按批次重置。|
|[`LatestSignalState.__init__`](#api-LatestSignalState-__init__)|先申请声明/容器预算，再检查唯一别名并创建空状态。|
|[`LatestSignalState.budget`](#api-LatestSignalState-budget)|返回共用的资源用量记录引用。|
|[`LatestSignalState.session_id`](#api-LatestSignalState-session_id)|返回固定会话标识。|
|[`LatestSignalState.closed`](#api-LatestSignalState-closed)|返回关闭状态。|
|[`LatestSignalState.definitions`](#api-LatestSignalState-definitions)|返回固定声明只读视图。|
|[`LatestSignalState.latest`](#api-LatestSignalState-latest)|返回当前快照只读视图。|
|[`LatestSignalState.fixed_cost`](#api-LatestSignalState-fixed_cost)|返回声明预算量。|
|[`LatestSignalState.retained_cost`](#api-LatestSignalState-retained_cost)|返回最新记录预算量。|
|[`LatestSignalState._transaction_delta`](#api-LatestSignalState-_transaction_delta)|取得实际已付量与当前快照的差额。|
|[`LatestSignalState.last_time_ns`](#api-LatestSignalState-last_time_ns)|返回最后完整组时间。|
|[`LatestSignalState.conflict_count`](#api-LatestSignalState-conflict_count)|返回累计显式冲突数。|
|[`LatestSignalState.revision`](#api-LatestSignalState-revision)|读取成功完整组的提交版本，失败提交不推进该版本。|
|[`LatestSignalState._ensure_open`](#api-LatestSignalState-_ensure_open)|拒绝关闭后访问。|
|[`LatestSignalState.get`](#api-LatestSignalState-get)|返回当前原样规范观测；无更新是None，无效更新不会回退旧值。|
|[`LatestSignalState._before_group`](#api-LatestSignalState-_before_group)|查组前标量。|
|[`LatestSignalState.apply`](#api-LatestSignalState-apply)|整个组检查/选择成功后一次替换最新状态，任何失败保持旧状态。|
|[`LatestSignalState._change_budget`](#api-LatestSignalState-_change_budget)|为一次直接预算操作登记实际增减，操作完成后取消也不会遗失归属。|
|[`LatestSignalState._restore_transaction`](#api-LatestSignalState-_restore_transaction)|恢复未提交事务的实际费用差额，清理失败不替换最先发生的错误。|
|[`LatestSignalState.close`](#api-LatestSignalState-close)|丢弃自有声明与最新记录，抵销账本，不删除历史或修改返回对象。|
|[`_sequence`](#api-_sequence)|选定稳定原序号。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass, replace
from math import isnan
from types import MappingProxyType
from ..core.binding import SignalDefinition
from ..core.numeric import ScalarValue
from ..core.scalar import _scalar_from_validated_fields
from ..core.types import SignalDType
from ..core.validation import require_identifier
from ..results.budget import ResourceBudget, _reserve_owned_ram
from ..results.errors import ResultClosedError
from .groups import DecodedTimeGroup
from .history import _metadata_bytes
from .history_records import HistorySample, estimate_record_bytes
```

</details>

<a id="api-CommittedUpdates"></a>
## `CommittedUpdates`

保存一次原子提交结果，别名唯一，原seq/ref/质量及显式冲突数量保留。

```python
class CommittedUpdates
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|当前事实对应的整数纳秒时间，不经过浮点二次取整。|
|`updates`|tuple[[HistorySample](chronaxis.execution.history_records.md#api-HistorySample), ...]|是|无|当前时刻完整原子提交的别名到更新映射，不能拆开同时刻更新。|
|`conflict_count`|int|是|无|同一时刻冲突的显式累计/本次计数，按当前模型范围解释，不隐藏丢弃。|

源码：[`src/chronaxis/execution/state.py:28`](../../../src/chronaxis/execution/state.py#L28)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-CommittedUpdates-__post_init__"></a>
### `CommittedUpdates.__post_init__`

复用完整组检查时间/身份，再限制每别名仅有一个选定观测。

```python
CommittedUpdates.__post_init__()
```

参数：无显式参数。


#### 参数说明

无，读取字段。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError为非法结果。

本函数直接报告的具体错误：

- `ValueError`：提交结果需唯一别名与非负原生冲突数。

源码：[`src/chronaxis/execution/state.py:35`](../../../src/chronaxis/execution/state.py#L35)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_committed_from_validated_fields"></a>
## `_committed_from_validated_fields`

包装本次已完成绑定/冲突选择的结果，不再遍历一次时间组。

```python
_committed_from_validated_fields(time_ns, updates, conflict_count)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|位置或关键字。已经完成冲突检查的完整组时刻，原生纳秒整数。|
|`updates`|tuple[[HistorySample](chronaxis.execution.history_records.md#api-HistorySample), ...]|是|无|位置或关键字。每个别名已选定且唯一的规范更新；沿用原始序号、来源和质量。|
|`conflict_count`|int|是|无|位置或关键字。本组实际冲突数量，已经检查为非负原生整数。|

### 返回说明

CommittedUpdates。

### 异常说明

分配错误传播，不安装部分状态。
只由LatestSignalState.apply在全部检查后使用；公开构造仍完整验证。

源码：[`src/chronaxis/execution/state.py:45`](../../../src/chronaxis/execution/state.py#L45)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_same_fact"></a>
## `_same_fact`

按现有核心比较逻辑值/类型/valid/quality，NaN诊断可以同因一致。

```python
_same_fact(left: HistorySample, right: HistorySample) -> bool
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`left`|[HistorySample](chronaxis.execution.history_records.md#api-HistorySample)|是|无|位置或关键字。同一别名、同一时刻的第一条历史样本，比较其原始值及质量。|
|`right`|[HistorySample](chronaxis.execution.history_records.md#api-HistorySample)|是|无|位置或关键字。同一别名、同一时刻的第二条历史样本，用于检查是否与left冲突。|

### 返回说明

bool事实一致。

### 异常说明

内部已校验类型错误传播；不把不同CSV位置本身算数值冲突。

返回类型：bool。

源码：[`src/chronaxis/execution/state.py:59`](../../../src/chronaxis/execution/state.py#L59)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_StateSnapshot"></a>
## `_StateSnapshot`

持有一次完整提交的只读映射、时间、冲突计数与预算量；安装后字段不可改。

```python
class _StateSnapshot
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`latest`|MappingProxyType|是|无|完整组提交后的只读最新信号映射。|
|`last_time_ns`|int &#124; None|是|无|上一次完整提交时刻，初始无提交时为None。|
|`conflict_count`|int|是|无|同一时刻冲突的显式累计/本次计数，按当前模型范围解释，不隐藏丢弃。|
|`retained_cost`|int|是|无|该状态快照持有并计入预算的字节数。|
|`revision`|int|是|无|成功完整组提交次数，仅用于内部两段查询证明提交顺序。|
|`costs`|MappingProxyType|是|无|每别名最新记录的已核费用；与latest在同一快照内替换。|
|`prior`|dict &#124; None|否|None|仅v4最近一组被替换的(时间,规范标量)，无原记录定位。|

源码：[`src/chronaxis/execution/state.py:72`](../../../src/chronaxis/execution/state.py#L72)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-LatestSignalState"></a>
## `LatestSignalState`

持有固定声明与每别名一个最新记录；成功完整组严格递增，不按批次重置。

```python
LatestSignalState(budget: ResourceBudget, definitions: tuple[SignalDefinition, ...], session_id: str, *, declaration_owner=None)
```


源码：[`src/chronaxis/execution/state.py:84`](../../../src/chronaxis/execution/state.py#L84)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-LatestSignalState-__init__"></a>
### `LatestSignalState.__init__`

先申请声明/容器预算，再检查唯一别名并创建空状态。

```python
LatestSignalState.__init__(budget: ResourceBudget, definitions: tuple[SignalDefinition, ...], session_id: str, *, declaration_owner=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)|是|无|位置或关键字。本次运行共用的ResourceBudget对象，用于检查内存和临时磁盘用量。当前对象在分配前申请额度，用完后归还；同一次运行的组件应使用同一个对象。|
|`definitions`|tuple[[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition), ...]|是|无|位置或关键字。definitions当前冻结声明，常量计划可为空tuple|
|`session_id`|str|是|无|位置或关键字。本次会话的名字，用来防止把不同试验的数据混在一起。|
|`declaration_owner`|[RunSession](chronaxis.execution.run_session.md#api-RunSession) &#124; None|否|None|仅关键字。持有共享声明的父运行会话。仅接受同一账本中仍开放的实际owner；省略时状态独立计入声明费用。|

#### 返回说明

新状态。

#### 异常说明

配置/预算/取消；保留原异常并清理成功申请，包括申请返回取消。
    持续清理失败时，原异常的state_cleanup_owner提供本次状态的恢复close入口。

源码：[`src/chronaxis/execution/state.py:87`](../../../src/chronaxis/execution/state.py#L87)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-LatestSignalState-budget"></a>
### `LatestSignalState.budget`

返回共用的资源用量记录引用。

```python
LatestSignalState.budget: ResourceBudget
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

ResourceBudget。

#### 异常说明

无；不转移所有权。

返回类型：[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)。

源码：[`src/chronaxis/execution/state.py:155`](../../../src/chronaxis/execution/state.py#L155)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-LatestSignalState-session_id"></a>
### `LatestSignalState.session_id`

返回固定会话标识。

```python
LatestSignalState.session_id: str
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

str。

#### 异常说明

无。

返回类型：str。

源码：[`src/chronaxis/execution/state.py:160`](../../../src/chronaxis/execution/state.py#L160)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-LatestSignalState-closed"></a>
### `LatestSignalState.closed`

返回关闭状态。

```python
LatestSignalState.closed: bool
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

返回类型：bool。

源码：[`src/chronaxis/execution/state.py:165`](../../../src/chronaxis/execution/state.py#L165)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-LatestSignalState-definitions"></a>
### `LatestSignalState.definitions`

返回固定声明只读视图。

```python
LatestSignalState.definitions: MappingProxyType
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

映射。

#### 异常说明

ResultClosedError为关闭。

返回类型：MappingProxyType。

源码：[`src/chronaxis/execution/state.py:170`](../../../src/chronaxis/execution/state.py#L170)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-LatestSignalState-latest"></a>
### `LatestSignalState.latest`

返回当前快照只读视图。

```python
LatestSignalState.latest: MappingProxyType
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

映射。

#### 异常说明

ResultClosedError为关闭。

调用方跨提交保存旧视图会延长旧观测寿命，该外部保留量不由状态预算负责。

返回类型：MappingProxyType。

源码：[`src/chronaxis/execution/state.py:176`](../../../src/chronaxis/execution/state.py#L176)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-LatestSignalState-fixed_cost"></a>
### `LatestSignalState.fixed_cost`

返回声明预算量。

```python
LatestSignalState.fixed_cost: int
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

int bytes，关闭后0。

#### 异常说明

无。

返回类型：int。

源码：[`src/chronaxis/execution/state.py:185`](../../../src/chronaxis/execution/state.py#L185)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-LatestSignalState-retained_cost"></a>
### `LatestSignalState.retained_cost`

返回最新记录预算量。

```python
LatestSignalState.retained_cost: int
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

int bytes，关闭后0。

#### 异常说明

无。

返回类型：int。

源码：[`src/chronaxis/execution/state.py:190`](../../../src/chronaxis/execution/state.py#L190)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-LatestSignalState-_transaction_delta"></a>
### `LatestSignalState._transaction_delta`

取得实际已付量与当前快照的差额。

```python
LatestSignalState._transaction_delta: int
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

带符号bytes。

#### 异常说明

无。

返回类型：int。

源码：[`src/chronaxis/execution/state.py:195`](../../../src/chronaxis/execution/state.py#L195)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-LatestSignalState-last_time_ns"></a>
### `LatestSignalState.last_time_ns`

返回最后完整组时间。

```python
LatestSignalState.last_time_ns: int | None
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

int ns或None。

#### 异常说明

无。

返回类型：int &#124; None。

源码：[`src/chronaxis/execution/state.py:200`](../../../src/chronaxis/execution/state.py#L200)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-LatestSignalState-conflict_count"></a>
### `LatestSignalState.conflict_count`

返回累计显式冲突数。

```python
LatestSignalState.conflict_count: int
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

int，关闭后0。

#### 异常说明

无。

返回类型：int。

源码：[`src/chronaxis/execution/state.py:205`](../../../src/chronaxis/execution/state.py#L205)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-LatestSignalState-revision"></a>
### `LatestSignalState.revision`

读取成功完整组的提交版本，失败提交不推进该版本。

```python
LatestSignalState.revision: int
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

原生非负int，初始0，每成功提交增加1。

#### 异常说明

ResultClosedError为状态关闭；不能通过此属性修改快照。

返回类型：int。

源码：[`src/chronaxis/execution/state.py:210`](../../../src/chronaxis/execution/state.py#L210)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-LatestSignalState-_ensure_open"></a>
### `LatestSignalState._ensure_open`

拒绝关闭后访问。

```python
LatestSignalState._ensure_open() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ResultClosedError。

本函数直接报告的具体错误：

- `ResultClosedError`：最新信号状态已关闭。

返回类型：None。

源码：[`src/chronaxis/execution/state.py:220`](../../../src/chronaxis/execution/state.py#L220)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-LatestSignalState-get"></a>
### `LatestSignalState.get`

返回当前原样规范观测；无更新是None，无效更新不会回退旧值。

```python
LatestSignalState.get(name: str) -> HistorySample | None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|位置或关键字。name当前简单别名。|

#### 返回说明

HistorySample或None。

#### 异常说明

KeyError为未知别名；ResultClosedError为关闭。不检查TTL或观测范围。

返回类型：[HistorySample](chronaxis.execution.history_records.md#api-HistorySample) &#124; None。

源码：[`src/chronaxis/execution/state.py:225`](../../../src/chronaxis/execution/state.py#L225)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-LatestSignalState-_before_group"></a>
### `LatestSignalState._before_group`

查组前标量。

```python
LatestSignalState._before_group(name)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|位置或关键字。要查询最近一次原子更新之前保持状态的已声明信号别名。|

#### 返回说明

(时间,标量)或None。

#### 异常说明

未声明别名。

源码：[`src/chronaxis/execution/state.py:234`](../../../src/chronaxis/execution/state.py#L234)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-LatestSignalState-apply"></a>
### `LatestSignalState.apply`

整个组检查/选择成功后一次替换最新状态，任何失败保持旧状态。

```python
LatestSignalState.apply(group: DecodedTimeGroup) -> CommittedUpdates
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`group`|[DecodedTimeGroup](chronaxis.execution.groups.md#api-DecodedTimeGroup)|是|无|位置或关键字。group已收齐的同一时刻更新，time_ns严格晚于上次提交。|

#### 返回说明

CommittedUpdates，选定更新按别名排序、每别名一次，冲突数遵循核心政策。

#### 异常说明

类型/时间/绑定/同一时刻冲突错误或预算超限；不部分更新或重做转换。

本函数直接报告的具体错误：

- `TypeError`：状态只能提交完整DecodedTimeGroup。
- `ValueError`：状态完整组必须严格递增，不能重复提交或回退。
- `ValueError`：状态内部预估不足，拒绝提交。
- `ValueError`：完整组包含未声明别名。
- `ValueError`：完整组当前绑定/dtype/单位不匹配。
- `ValueError`：完整组ENUM标签域与当前声明不匹配。
- `ValueError`：完整组同别名原sequence重复。

返回类型：[CommittedUpdates](chronaxis.execution.state.md#api-CommittedUpdates)。

源码：[`src/chronaxis/execution/state.py:242`](../../../src/chronaxis/execution/state.py#L242)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-LatestSignalState-_change_budget"></a>
### `LatestSignalState._change_budget`

为一次直接预算操作登记实际增减，操作完成后取消也不会遗失归属。

```python
LatestSignalState._change_budget(delta)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`delta`|int|是|无|位置或关键字。本次直接预算操作的带符号字节数：正数申请，负数退回，零不操作。|

#### 返回说明

None。

#### 异常说明

原预算或取消传播；只观察本次直接调用，不按共享余额计算其他费用。

源码：[`src/chronaxis/execution/state.py:351`](../../../src/chronaxis/execution/state.py#L351)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-LatestSignalState-_restore_transaction"></a>
### `LatestSignalState._restore_transaction`

恢复未提交事务的实际费用差额，清理失败不替换最先发生的错误。

```python
LatestSignalState._restore_transaction(primary)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`primary`|BaseException|是|无|位置或关键字。提交事务最先发生的异常；费用恢复失败作为附注和清理 owner 附加，不替换它。|

#### 返回说明

None。

#### 异常说明

不主动替换主异常；
两次恢复仍失败时附state_cleanup_owner，禁止再次apply，由同一对象close处理。

源码：[`src/chronaxis/execution/state.py:369`](../../../src/chronaxis/execution/state.py#L369)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-LatestSignalState-close"></a>
### `LatestSignalState.close`

丢弃自有声明与最新记录，抵销账本，不删除历史或修改返回对象。

```python
LatestSignalState.close() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None。关闭成功后再次调用不会重复释放同一份资源。

#### 异常说明

预算/取消传播；抵销前可重试，已抵销仍最小关闭。

返回类型：None。

源码：[`src/chronaxis/execution/state.py:389`](../../../src/chronaxis/execution/state.py#L389)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_sequence"></a>
## `_sequence`

选定稳定原序号。

```python
_sequence(sample: HistorySample) -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`sample`|[HistorySample](chronaxis.execution.history_records.md#api-HistorySample)|是|无|位置或关键字。sample规范观测。|

### 返回说明

int sequence。

### 异常说明

无。

返回类型：int。

源码：[`src/chronaxis/execution/state.py:410`](../../../src/chronaxis/execution/state.py#L410)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
