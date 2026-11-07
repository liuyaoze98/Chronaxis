# `chronaxis.execution.hold`

在完整组之间查询最新信号的有限保持，独立计算参考与NumPy有效性。

输入为LatestSignalState、声明来源描述/封存EOF事实及请求域，输出须关闭的查询结果。
最新观测不可回溯：查询不能早于最后已提交组，驱动器须先查旧状态再提交新组。
先检查精确时间与来源身份，再按domain/来源半开或point范围、严格TTL叠加质量。
参考用Python整数逐点计算，NumPy用真实数组掩码及uint64时间差，均不再归一化。
结果独立持有样本引用预算，state更新/关闭不会使仍存活的查询漏计；owner关闭全部结果。
本模块不读取文件/旧链，不执行表达式、事件或指标；预算为保守估算而非整进程RSS。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[HistoryProgress](chronaxis.execution.history_records.md#api-HistoryProgress)、[HistorySample](chronaxis.execution.history_records.md#api-HistorySample)、[Interval](chronaxis.core.models.md#api-Interval)、[LatestSignalState](chronaxis.execution.state.md#api-LatestSignalState)、[QualityFlag](chronaxis.core.types.md#api-QualityFlag)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[SignalDType](chronaxis.core.types.md#api-SignalDType)、[SourceDescription](chronaxis.sources.models.md#api-SourceDescription)

## 对象导航

|对象|用途|
|---|---|
|[`HoldContext`](#api-HoldContext)|保存本会话的请求范围、各来源描述和读完后的进度。用这些信息判断旧样本还能保持到哪里；来源未知的起点仍用None，不自行补一个采样周期。|
|[`HoldContext.__post_init__`](#api-HoldContext-__post_init__)|校验固定身份/EOF及已知端点一致性，不读取文件或推断未知端点。|
|[`HoldPoint`](#api-HoldPoint)|保存一个参考查询点；无效值仍保留原逻辑诊断，无历史时sample/value为None。|
|[`_HeldArrays`](#api-_HeldArrays)|保存内部已检查的(N,)只读列，values为物理dtype，sample保留原逻辑诊断。|
|[`HoldResult`](#api-HoldResult)|持有一份结果和原样本预算直到close；外部另存已取得数组/rows需自行负责。|
|[`HoldResult.__init__`](#api-HoldResult-__init__)|仅由已预留预算的查询owner构造；不再复制大列。|
|[`HoldResult._ensure_open`](#api-HoldResult-_ensure_open)|拒绝关闭后访问。|
|[`HoldResult.closed`](#api-HoldResult-closed)|返回持有状态。|
|[`HoldResult.definition`](#api-HoldResult-definition)|读取原冻结声明。|
|[`HoldResult.sample`](#api-HoldResult-sample)|读取原最新记录。|
|[`HoldResult.rows`](#api-HoldResult-rows)|读取参考结果。|
|[`HoldResult.arrays`](#api-HoldResult-arrays)|读取NumPy列。|
|[`HoldResult.close`](#api-HoldResult-close)|丢弃自有引用并抵销完整查询预算，状态可已先关闭。|
|[`HoldResult._discard`](#api-HoldResult-_discard)|移除登记并丢弃引用，不再次抵销申请。|
|[`HoldQueries`](#api-HoldQueries)|持有固定上下文/声明及活动查询；查询快照不会随state后续更新改变。|
|[`HoldQueries.__init__`](#api-HoldQueries-__init__)|先申请context/声明容器空间，再校验当前绑定与来源描述。|
|[`HoldQueries.closed`](#api-HoldQueries-closed)|返回当前对象是否已经关闭。|
|[`HoldQueries._ensure_open`](#api-HoldQueries-_ensure_open)|拒绝关闭owner或state后的新查询。|
|[`HoldQueries._capture`](#api-HoldQueries-_capture)|取得当前固定声明/最新记录及原范围，拒绝无法证明的非空EOF范围。|
|[`HoldQueries._cost`](#api-HoldQueries-_cost)|估算所有轴/结果/临时副本及查询独立持有样本空间。|
|[`HoldQueries._register`](#api-HoldQueries-_register)|在预留内构造待登记结果，让外层先取得局部所有权。|
|[`HoldQueries.query_reference`](#api-HoldQueries-query_reference)|独立Python整数参考保持，输出保留原逻辑值的逐点结果。|
|[`HoldQueries.query_numpy`](#api-HoldQueries-query_numpy)|用独立数组掩码计算(N,)保持列，精确无符号差覆盖负到正大age。|
|[`HoldQueries.next_expiry`](#api-HoldQueries-next_expiry)|返回当前样本下一TTL边界，超域/来源终点或int64时返回None。|
|[`HoldQueries.close`](#api-HoldQueries-close)|关闭全部活动结果及固定上下文，不关闭调用方state或删除历史。|
|[`HoldQueries._finish_close`](#api-HoldQueries-_finish_close)|丢弃已释放固定成本的owner引用，不再操作账本。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from types import MappingProxyType
from ..core.models import Interval
from ..core.types import QualityFlag, SignalDType
from ..core.validation import require_identifier
from ..results.errors import ResultClosedError
from ..sources.models import SourceDescription
from ..timebase.conversion import INT64_MAX, require_int64_ns
from .history import _metadata_bytes
from .history_records import HistoryProgress, HistorySample, estimate_record_bytes
from .state import LatestSignalState
```

</details>

<a id="api-HoldContext"></a>
## `HoldContext`

保存本会话的请求范围、各来源描述和读完后的进度。用这些信息判断旧样本还能保持到哪里；来源未知的起点仍用None，不自行补一个采样周期。

```python
class HoldContext
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`session_id`|str|是|无|当前会话的名称，必须与completions中每项进度记录的session_id一致。|
|`domain`|[Interval](chronaxis.core.models.md#api-Interval)|是|无|本次要求分析的时间范围，使用Interval表示起止纳秒；它不等于来源实际拥有数据的范围。|
|`descriptions`|tuple[[SourceDescription](chronaxis.sources.models.md#api-SourceDescription), ...]|是|无|各个来源的SourceDescription组成的元组，记录来源名称和已知的观测起止时间；来源名称不能重复。|
|`completions`|tuple[[HistoryProgress](chronaxis.execution.history_records.md#api-HistoryProgress), ...]|是|无|各个来源读完后保存的HistoryProgress组成的元组，与descriptions一一对应。每项的source_eof必须为True，表示已读到该来源末尾；observed_end_ns记录实际观测终点。|

源码：[`src/chronaxis/execution/hold.py:32`](../../../src/chronaxis/execution/hold.py#L32)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HoldContext-__post_init__"></a>
### `HoldContext.__post_init__`

校验固定身份/EOF及已知端点一致性，不读取文件或推断未知端点。

```python
HoldContext.__post_init__()
```

参数：无显式参数。


#### 参数说明

无，读取创建后不可修改的字段。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError为协议不一致。

本函数直接报告的具体错误：

- `TypeError`：保持上下文需要Interval与带有明确类型的 tuple描述/EOF。
- `ValueError`：保持描述与EOF来源必须唯一且完全对应。
- `ValueError`：保持上下文需要当前会话whole-source EOF。
- `ValueError`：EOF终点与原描述不一致。
- `ValueError`：EOF终点早于原来源起点。

源码：[`src/chronaxis/execution/hold.py:43`](../../../src/chronaxis/execution/hold.py#L43)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HoldPoint"></a>
## `HoldPoint`

保存一个参考查询点；无效值仍保留原逻辑诊断，无历史时sample/value为None。

```python
class HoldPoint
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|当前事实对应的整数纳秒时间，不经过浮点二次取整。|
|`value`|int &#124; float &#124; bool &#124; str &#124; None|是|无|当前保持的原生数值或状态标签；没有历史样本时为None，有效性分别查看valid和quality。|
|`valid`|bool|是|无|值是否有效的布尔标记/数组；不能仅凭数值有限推断有效。|
|`quality`|[QualityFlag](chronaxis.core.types.md#api-QualityFlag)|是|无|值/结果的QualityFlag质量位，保留缺失、过期和数值错误等原因。|
|`sample`|[HistorySample](chronaxis.execution.history_records.md#api-HistorySample) &#124; None|是|无|提供这个保持值的原始历史样本，用于回查位置；无历史样本时为None。|
|`actual_update`|bool|是|无|查询点是否存在真实样本更新；保持值或TTL边界不冒充真实更新。|

源码：[`src/chronaxis/execution/hold.py:71`](../../../src/chronaxis/execution/hold.py#L71)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_HeldArrays"></a>
## `_HeldArrays`

保存内部已检查的(N,)只读列，values为物理dtype，sample保留原逻辑诊断。

has_sample区分domain外/无历史与域内无效更新；NumPy写保护是正常使用约定。

```python
class _HeldArrays
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|np.ndarray|是|无|当前事实对应的整数纳秒时间，不经过浮点二次取整。|
|`values`|numpy.ndarray|是|无|长度为N的物理数值列，元素类型与信号声明一致；有效性须结合质量和has_sample判断。|
|`valid`|np.ndarray|是|无|值是否有效的布尔标记/数组；不能仅凭数值有限推断有效。|
|`quality`|np.ndarray|是|无|值/结果的QualityFlag质量位，保留缺失、过期和数值错误等原因。|
|`actual_update`|np.ndarray|是|无|查询点是否存在真实样本更新；保持值或TTL边界不冒充真实更新。|
|`has_sample`|numpy.ndarray[bool]|是|无|与values等长。True表示此位置有历史样本，False表示无历史或在观测范围外；True仍可能对应无效样本。|
|`dtype`|[SignalDType](chronaxis.core.types.md#api-SignalDType)|是|无|SignalDType枚举成员：INT64是有符号64位整数，UINT64是无符号64位整数，FLOAT64是双精度浮点，BOOL是真/假，ENUM是预先声明的状态标签。这里传枚举成员，不传字符串；当前运算支持哪些类型仍见本对象的约束。|
|`labels`|tuple[str, ...]|是|无|枚举数组使用的标签域，整数编码只能在该域中解释。|
|`sample`|[HistorySample](chronaxis.execution.history_records.md#api-HistorySample) &#124; None|是|无|本次保持查询所依据的最近原始样本，保留原值及诊断；没有历史时为None。|

源码：[`src/chronaxis/execution/hold.py:83`](../../../src/chronaxis/execution/hold.py#L83)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HoldResult"></a>
## `HoldResult`

持有一份结果和原样本预算直到close；外部另存已取得数组/rows需自行负责。

```python
HoldResult(owner, cost, definition, sample, payload)
```


源码：[`src/chronaxis/execution/hold.py:100`](../../../src/chronaxis/execution/hold.py#L100)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HoldResult-__init__"></a>
### `HoldResult.__init__`

仅由已预留预算的查询owner构造；不再复制大列。

```python
HoldResult.__init__(owner, cost, definition, sample, payload)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|[HoldQueries](chronaxis.execution.hold.md#api-HoldQueries)|是|无|位置或关键字。创建本结果的保持查询对象，负责登记结果并在close时释放其内存额度。|
|`cost`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|
|`definition`|SignalDefinition|是|无|位置或关键字。当前信号的原始定义，包含类型、单位、来源和valid_for_ns有效期。|
|`sample`|[HistorySample](chronaxis.execution.history_records.md#api-HistorySample) &#124; None|是|无|位置或关键字。本次保持使用的最近一条历史样本，带原始来源定位；此前没有样本时为None。|
|`payload`|tuple[[HoldPoint](chronaxis.execution.hold.md#api-HoldPoint), ...] &#124; [_HeldArrays](chronaxis.execution.hold.md#api-_HeldArrays)|是|无|位置或关键字。在查询时间轴上得到的保持值；参考实现为HoldPoint元组，数组实现使用_HeldArrays。|

#### 返回说明

None；初始化实例状态。

#### 异常说明

分配错误传播给owner抵销申请。

源码：[`src/chronaxis/execution/hold.py:103`](../../../src/chronaxis/execution/hold.py#L103)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HoldResult-_ensure_open"></a>
### `HoldResult._ensure_open`

拒绝关闭后访问。

```python
HoldResult._ensure_open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ResultClosedError。

本函数直接报告的具体错误：

- `ResultClosedError`：保持查询结果已关闭。

源码：[`src/chronaxis/execution/hold.py:112`](../../../src/chronaxis/execution/hold.py#L112)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HoldResult-closed"></a>
### `HoldResult.closed`

返回持有状态。

```python
HoldResult.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/execution/hold.py:118`](../../../src/chronaxis/execution/hold.py#L118)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HoldResult-definition"></a>
### `HoldResult.definition`

读取原冻结声明。

```python
HoldResult.definition
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

SignalDefinition。

#### 异常说明

对象处于下列状态时抛ResultClosedError：保持查询结果已关闭。

源码：[`src/chronaxis/execution/hold.py:123`](../../../src/chronaxis/execution/hold.py#L123)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HoldResult-sample"></a>
### `HoldResult.sample`

读取原最新记录。

```python
HoldResult.sample
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

HistorySample或None。

#### 异常说明

对象处于下列状态时抛ResultClosedError：保持查询结果已关闭。

源码：[`src/chronaxis/execution/hold.py:129`](../../../src/chronaxis/execution/hold.py#L129)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HoldResult-rows"></a>
### `HoldResult.rows`

读取参考结果。

```python
HoldResult.rows
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

tuple[HoldPoint]。

#### 异常说明

关闭或后端类型错误。

本函数直接报告的具体错误：

- `TypeError`：NumPy查询请读取arrays。

源码：[`src/chronaxis/execution/hold.py:135`](../../../src/chronaxis/execution/hold.py#L135)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HoldResult-arrays"></a>
### `HoldResult.arrays`

读取NumPy列。

```python
HoldResult.arrays
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

_HeldArrays。

#### 异常说明

关闭或后端类型错误。

本函数直接报告的具体错误：

- `TypeError`：参考查询请读取rows。

源码：[`src/chronaxis/execution/hold.py:143`](../../../src/chronaxis/execution/hold.py#L143)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HoldResult-close"></a>
### `HoldResult.close`

丢弃自有引用并抵销完整查询预算，状态可已先关闭。

```python
HoldResult.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None。关闭成功后再次调用不会重复释放同一份资源。

#### 异常说明

内部账本一致性错误。

源码：[`src/chronaxis/execution/hold.py:150`](../../../src/chronaxis/execution/hold.py#L150)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HoldResult-_discard"></a>
### `HoldResult._discard`

移除登记并丢弃引用，不再次抵销申请。

```python
HoldResult._discard()
```

参数：无显式参数。


#### 参数说明

无；仅在预算已经释放或查询失败由外层持有金额时调用。

#### 返回说明

None，结果关闭。

#### 异常说明

登记容器错误传播，finally仍标记关闭避免再次扣账。

源码：[`src/chronaxis/execution/hold.py:169`](../../../src/chronaxis/execution/hold.py#L169)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HoldQueries"></a>
## `HoldQueries`

持有固定上下文/声明及活动查询；查询快照不会随state后续更新改变。

```python
HoldQueries(state: LatestSignalState, context: HoldContext)
```


源码：[`src/chronaxis/execution/hold.py:184`](../../../src/chronaxis/execution/hold.py#L184)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HoldQueries-__init__"></a>
### `HoldQueries.__init__`

先申请context/声明容器空间，再校验当前绑定与来源描述。

```python
HoldQueries.__init__(state: LatestSignalState, context: HoldContext)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`state`|[LatestSignalState](chronaxis.execution.state.md#api-LatestSignalState)|是|无|位置或关键字。state当前打开最新状态|
|`context`|[HoldContext](chronaxis.execution.hold.md#api-HoldContext)|是|无|位置或关键字。context已seal输入事实及请求域。|

#### 返回说明

新owner。

#### 异常说明

绑定/预算/构造错误，保留原异常并清理固定申请。
    持续清理失败时，原异常的hold_queries_cleanup_owner提供本次查询owner的恢复close入口。

源码：[`src/chronaxis/execution/hold.py:187`](../../../src/chronaxis/execution/hold.py#L187)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HoldQueries-closed"></a>
### `HoldQueries.closed`

返回当前对象是否已经关闭。

```python
HoldQueries.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/execution/hold.py:246`](../../../src/chronaxis/execution/hold.py#L246)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HoldQueries-_ensure_open"></a>
### `HoldQueries._ensure_open`

拒绝关闭owner或state后的新查询。

```python
HoldQueries._ensure_open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ResultClosedError。

本函数直接报告的具体错误：

- `ResultClosedError`：保持查询owner已关闭。

源码：[`src/chronaxis/execution/hold.py:250`](../../../src/chronaxis/execution/hold.py#L250)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HoldQueries-_capture"></a>
### `HoldQueries._capture`

取得当前固定声明/最新记录及原范围，拒绝无法证明的非空EOF范围。

```python
HoldQueries._capture(name, point)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|位置或关键字。当前已绑定信号的简单别名，例如current；用它取得对应状态。|
|`point`|bool|是|无|位置或关键字。name别名/point显式bool。|

#### 返回说明

definition/sample/(start,end)。

#### 异常说明

关闭、未知名、模式或来源事实错误；不计算两后端有效性。

本函数直接报告的具体错误：

- `TypeError`：point需要bool。
- `ValueError`：非空状态缺少来源观测终点，不能证明保持范围。
- `ValueError`：当前样本超出来源观测事实。

源码：[`src/chronaxis/execution/hold.py:256`](../../../src/chronaxis/execution/hold.py#L256)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HoldQueries-_cost"></a>
### `HoldQueries._cost`

估算所有轴/结果/临时副本及查询独立持有样本空间。

```python
HoldQueries._cost(count, sample)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`count`|int|是|无|位置或关键字。本次查询的时间点数量，须非负；用于估计结果列所需内存。|
|`sample`|[HistorySample](chronaxis.execution.history_records.md#api-HistorySample) &#124; None|是|无|位置或关键字。本次保持使用的最近一条历史样本，带原始来源定位；此前没有样本时为None。|

#### 返回说明

int bytes。

#### 异常说明

记录估算错误。

源码：[`src/chronaxis/execution/hold.py:275`](../../../src/chronaxis/execution/hold.py#L275)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HoldQueries-_register"></a>
### `HoldQueries._register`

在预留内构造待登记结果，让外层先取得局部所有权。

```python
HoldQueries._register(cost, definition, sample, payload)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`cost`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|
|`definition`|SignalDefinition|是|无|位置或关键字。当前信号的原始定义，包含类型、单位、来源和valid_for_ns有效期。|
|`sample`|[HistorySample](chronaxis.execution.history_records.md#api-HistorySample) &#124; None|是|无|位置或关键字。本次保持使用的最近一条历史样本，带原始来源定位；此前没有样本时为None。|
|`payload`|tuple[[HoldPoint](chronaxis.execution.hold.md#api-HoldPoint), ...] &#124; [_HeldArrays](chronaxis.execution.hold.md#api-_HeldArrays)|是|无|位置或关键字。在查询时间轴上得到的保持值；参考实现为HoldPoint元组，数组实现使用_HeldArrays。|

#### 返回说明

HoldResult。

#### 异常说明

构造错误传播；不在本方法内安装，返回取消由查询抵销申请。

源码：[`src/chronaxis/execution/hold.py:283`](../../../src/chronaxis/execution/hold.py#L283)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HoldQueries-query_reference"></a>
### `HoldQueries.query_reference`

独立Python整数参考保持，输出保留原逻辑值的逐点结果。

```python
HoldQueries.query_reference(name, times_ns: tuple[int, ...], *, point=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|位置或关键字。已绑定的信号别名，例如"u"，从该信号历史中查询保持值或下一过期时间。|
|`times_ns`|tuple[int, ...]|是|无|位置或关键字。按非递减顺序排列的纳秒查询时刻；NumPy输入须为一维int64数组。|
|`point`|bool|否|False|仅关键字。True查询点值，包含实际观测末点；False查询连续区间保持值，区间右端不计入。|

#### 返回说明

HoldResult；使用后close。

#### 异常说明

时间/范围/预算/构造错误，无状态副作用。

本函数直接报告的具体错误：

- `TypeError`：参考保持轴需要tuple。
- `ValueError`：保持查询轴回退。
- `ValueError`：最新状态不能回溯已经提交的过去。

源码：[`src/chronaxis/execution/hold.py:292`](../../../src/chronaxis/execution/hold.py#L292)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HoldQueries-query_numpy"></a>
### `HoldQueries.query_numpy`

用独立数组掩码计算(N,)保持列，精确无符号差覆盖负到正大age。

```python
HoldQueries.query_numpy(name, times_ns: np.ndarray, *, point=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|位置或关键字。已绑定的信号别名，例如"u"，从该信号历史中查询保持值或下一过期时间。|
|`times_ns`|numpy.ndarray[int64]|是|无|位置或关键字。按非递减顺序排列的纳秒查询时刻；NumPy输入须为一维int64数组。|
|`point`|bool|否|False|仅关键字。True查询点值，包含实际观测末点；False查询连续区间保持值，区间右端不计入。|

#### 返回说明

HoldResult.arrays只读自有列；无效物理占位不替代sample逻辑诊断。

#### 异常说明

轴/范围/预算/分配错误；不调用参考保持、不隐式cast时间或信号类型。

本函数直接报告的具体错误：

- `TypeError`：NumPy保持轴需要一维完整int64 ndarray。
- `ValueError`：保持查询轴回退。
- `ValueError`：最新状态不能回溯已经提交的过去。

源码：[`src/chronaxis/execution/hold.py:341`](../../../src/chronaxis/execution/hold.py#L341)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HoldQueries-next_expiry"></a>
### `HoldQueries.next_expiry`

返回当前样本下一TTL边界，超域/来源终点或int64时返回None。

```python
HoldQueries.next_expiry(name, after_ns)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|位置或关键字。已绑定的信号别名，例如"u"，从该信号历史中查询保持值或下一过期时间。|
|`after_ns`|int|是|无|位置或关键字。从此纳秒时刻之后寻找下一过期边界；不能早于最近提交的更新组。|

#### 返回说明

int ns或None，严格晚于after。

#### 异常说明

关闭、时间、绑定或来源事实错误；不把TTL伪造为实际更新。

本函数直接报告的具体错误：

- `ValueError`：TTL查询不能回退已提交时间。

源码：[`src/chronaxis/execution/hold.py:401`](../../../src/chronaxis/execution/hold.py#L401)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HoldQueries-close"></a>
### `HoldQueries.close`

关闭全部活动结果及固定上下文，不关闭调用方state或删除历史。

```python
HoldQueries.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None。关闭成功后再次调用不会重复释放同一份资源。

#### 异常说明

内部账本一致性错误。

源码：[`src/chronaxis/execution/hold.py:417`](../../../src/chronaxis/execution/hold.py#L417)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-HoldQueries-_finish_close"></a>
### `HoldQueries._finish_close`

丢弃已释放固定成本的owner引用，不再操作账本。

```python
HoldQueries._finish_close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None，owner关闭。

#### 异常说明

无主动异常；仅供已完成释放的正常或取消收尾使用。

源码：[`src/chronaxis/execution/hold.py:440`](../../../src/chronaxis/execution/hold.py#L440)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
