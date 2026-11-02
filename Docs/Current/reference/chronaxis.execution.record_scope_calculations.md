# chronaxis.execution.record_scope_calculations

只对明确的事件指标保存必要计算值，并按事件真实范围回读。

同表达式、条件和驱动共享一份紧凑历史；每次查询复用已验证的记录积分/统计核。
窗口尚未确定前只接事件，默认会话统计不创建这个所有者。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)、[DriverExpression](chronaxis.execution.driver_expression.md#api-DriverExpression)、[Interval](chronaxis.core.models.md#api-Interval)、[RecordIntegral](chronaxis.execution.record_integral.md#api-RecordIntegral)、[RecordSelection](chronaxis.execution.record_selection.md#api-RecordSelection)、[RecordTimeCalculation](chronaxis.execution.record_time_calculation.md#api-RecordTimeCalculation)、[RecordValueHistory](chronaxis.execution.record_value_history.md#api-RecordValueHistory)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)

## 对象导航

|对象|用途|
|---|---|
|[`RecordScopeCalculations`](#api-RecordScopeCalculations)|拥有必要表达式历史、等待右端的查询及当前统计器；计划/状态为借用。|
|[`RecordScopeCalculations.__init__`](#api-RecordScopeCalculations-__init__)|建立已请求的有限表达式分组。|
|[`RecordScopeCalculations._new`](#api-RecordScopeCalculations-_new)|接住未返回的实际子owner。|
|[`RecordScopeCalculations._open`](#api-RecordScopeCalculations-_open)|拒绝已失败/关闭的执行。|
|[`RecordScopeCalculations.observe_group`](#api-RecordScopeCalculations-observe_group)|完整组已原子提交，更新各必要表达式一次。|
|[`RecordScopeCalculations.observe_event`](#api-RecordScopeCalculations-observe_event)|仅保等待计算需要的父ID和真实端点，不复制事件全文。|
|[`RecordScopeCalculations.observe_segment`](#api-RecordScopeCalculations-observe_segment)|EOF后按实际片段范围计算，缺失扩展不伪装完整。|
|[`RecordScopeCalculations._calculate`](#api-RecordScopeCalculations-_calculate)|同范围、同表达式的相邻指标共读一次；预算余量不足时缩为单项。|
|[`RecordScopeCalculations._calculate_chunk`](#api-RecordScopeCalculations-_calculate_chunk)|建立有限计算器组并共享一次回读。|
|[`RecordScopeCalculations._finish_observation_tail`](#api-RecordScopeCalculations-_finish_observation_tail)|用真实来源终点补查询尾段，既不补固定周期也不增加真实样本。|
|[`RecordScopeCalculations._flush`](#api-RecordScopeCalculations-_flush)|右侧实际驱动到达才结算；EOF直接按已有点计算，不补周期。|
|[`RecordScopeCalculations.finish`](#api-RecordScopeCalculations-finish)|来源全部完成后处理常量和剩余事件。|
|[`RecordScopeCalculations.closed`](#api-RecordScopeCalculations-closed)|返回关闭事实。|
|[`RecordScopeCalculations.close`](#api-RecordScopeCalculations-close)|按责任关闭子资源，失败时保槽供重试。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from functools import partial as bind_consumer
from dataclasses import replace
from ..core.models import Interval
from ..core.calculations import CalculationDefinition
from ..results.errors import ResultClosedError
from ..results.spool import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from .history import _metadata_bytes
from .driver_expression import DriverExpression
from .record_value_history import RecordValueHistory
from .record_integral import RecordIntegral
from .record_time_calculation import RecordTimeCalculation
from .record_selection import RecordSelection
```

</details>

<a id="api-RecordScopeCalculations"></a>
## `RecordScopeCalculations`

拥有必要表达式历史、等待右端的查询及当前统计器；计划/状态为借用。

```python
RecordScopeCalculations(plan, state, budget, path, steps, requests, ends, consumer, *, selection_consumer=None)
```


源码：[`src/chronaxis/execution/record_scope_calculations.py:21`](../../../src/chronaxis/execution/record_scope_calculations.py#L21)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordScopeCalculations-__init__"></a>
### `RecordScopeCalculations.__init__`

建立已请求的有限表达式分组。

```python
RecordScopeCalculations.__init__(plan, state, budget, path, steps, requests, ends, consumer, *, selection_consumer=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|AnalysisPlan|是|无|位置或关键字。已完成静态解析的分析计划，包含来源、绑定、规则、指标、间隔选择和输出要求。|
|`state`|LatestSignalState|是|无|位置或关键字。当前会话各依赖信号的最新有效状态；过期按实际时间判断，不能跨独立任务继承。|
|`budget`|ResourceBudget|是|无|位置或关键字。本次分析共享的资源用量记录；新对象先预约所需内存和磁盘额度，关闭时归还自己的内存费用。|
|`path`|str &#124; Path|是|无|位置或关键字。本次任务专用路径；只操作本次登记的资源，不能指向原始输入或历史项目目录。|
|`steps`|Mapping[str, int &#124; None]|是|无|位置或关键字。节点id到已解析周期的映射；None为实际间隔，正整数为固定或DBC纳秒周期。|
|`requests`|Sequence[CalculationPlan]|是|无|位置或关键字。本次范围内需要计算的指标请求，保持声明顺序并共享必要回读。|
|`ends`|Mapping[str, int]|是|无|位置或关键字。来源名到已知实际EOF纳秒时刻的映射，用于收尾和裁剪。|
|`consumer`|Callable[[CalculationPlan, str, RecordTimeResult], None]|是|无|位置或关键字。接收指标请求、父事件/片段ID和计算结果；同一范围多指标保持声明次序。|
|`selection_consumer`|Callable[[CalculationPlan, str &#124; None, SelectionRow], None] &#124; None|否|None|仅关键字。接收指标请求、父事件/片段ID及一条选择结果；没有select需求时为None。|

#### 返回说明

owner。

#### 异常说明

原构造错。

源码：[`src/chronaxis/execution/record_scope_calculations.py:24`](../../../src/chronaxis/execution/record_scope_calculations.py#L24)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordScopeCalculations-_new"></a>
### `RecordScopeCalculations._new`

接住未返回的实际子owner。

```python
RecordScopeCalculations._new(factory, recovery, *args, **kwargs)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`factory`|Callable|是|无|位置或关键字。要调用的资源构造器；失败时按recovery取回真实拥有者，不吞掉原始异常。|
|`recovery`|str|是|无|位置或关键字。构造异常上用于取回未返回资源拥有者的属性名，确保失败后仍能关闭和退款。|
|`args`|tuple|否|()|可变位置。传给factory的位置参数，保持原有参数顺序。|
|`kwargs`|dict|否|{}|可变关键字。传给factory的关键字参数，保持原有名称与值。|

#### 返回说明

owner。

#### 异常说明

原错。

源码：[`src/chronaxis/execution/record_scope_calculations.py:67`](../../../src/chronaxis/execution/record_scope_calculations.py#L67)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordScopeCalculations-_open"></a>
### `RecordScopeCalculations._open`

拒绝已失败/关闭的执行。

```python
RecordScopeCalculations._open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

ResultClosedError。

源码：[`src/chronaxis/execution/record_scope_calculations.py:75`](../../../src/chronaxis/execution/record_scope_calculations.py#L75)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordScopeCalculations-observe_group"></a>
### `RecordScopeCalculations.observe_group`

完整组已原子提交，更新各必要表达式一次。

```python
RecordScopeCalculations.observe_group()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

求值/写入/预算原错。

源码：[`src/chronaxis/execution/record_scope_calculations.py:80`](../../../src/chronaxis/execution/record_scope_calculations.py#L80)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordScopeCalculations-observe_event"></a>
### `RecordScopeCalculations.observe_event`

仅保等待计算需要的父ID和真实端点，不复制事件全文。

```python
RecordScopeCalculations.observe_event(event)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`event`|Event|是|无|位置或关键字。本次规则产生的活动或点事件；保留实际开始、确认、结束和状态。|

#### 返回说明

None。

#### 异常说明

预算/计算原错。

源码：[`src/chronaxis/execution/record_scope_calculations.py:100`](../../../src/chronaxis/execution/record_scope_calculations.py#L100)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordScopeCalculations-observe_segment"></a>
### `RecordScopeCalculations.observe_segment`

EOF后按实际片段范围计算，缺失扩展不伪装完整。

```python
RecordScopeCalculations.observe_segment(segment)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`segment`|CompactSegment|是|无|位置或关键字。已确定的实际窗口片段，包含业务范围及父事件关联，供计算或导出使用。|

#### 返回说明

None。

#### 异常说明

原查询错；空片段只返回无观测值。

源码：[`src/chronaxis/execution/record_scope_calculations.py:115`](../../../src/chronaxis/execution/record_scope_calculations.py#L115)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordScopeCalculations-_calculate"></a>
### `RecordScopeCalculations._calculate`

同范围、同表达式的相邻指标共读一次；预算余量不足时缩为单项。

```python
RecordScopeCalculations._calculate(requests, parent, start_ns, end_ns, *, partial=False, parent_coverage=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`requests`|Sequence[CalculationPlan]|是|无|位置或关键字。本次范围内需要计算的指标请求，保持声明顺序并共享必要回读。|
|`parent`|str &#124; None|是|无|位置或关键字。当前结果关联的事件或片段ID；会话级结果使用None。|
|`start_ns`|int|是|无|位置或关键字。本次查询或计算的实际开始时刻，单位纳秒。|
|`end_ns`|int|是|无|位置或关键字。本次查询或计算的实际结束时刻，单位纳秒；按具体函数保留必要右端点供半开范围计算。|
|`partial`|bool|否|False|仅关键字。父事件或窗口是否已经只有部分观测；该状态必须传到子指标，不能重新冒充完整。|
|`parent_coverage`|float &#124; None|否|None|仅关键字。父范围的有效覆盖信息；None表示没有单独给出，具体判定沿该指标的覆盖政策。|

#### 返回说明

None。

#### 异常说明

原查询、预算或输出错误。
不缓存整个范围；每次借一行同时交给有限计算器，仍按声明顺序发布。

源码：[`src/chronaxis/execution/record_scope_calculations.py:130`](../../../src/chronaxis/execution/record_scope_calculations.py#L130)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordScopeCalculations-_calculate_chunk"></a>
### `RecordScopeCalculations._calculate_chunk`

建立有限计算器组并共享一次回读。

```python
RecordScopeCalculations._calculate_chunk(key, requests, parent, start_ns, end_ns, partial, parent_coverage)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`key`|tuple|是|无|位置或关键字。由表达式、条件及驱动组成的内部共享键；只有计算输入相同的指标才能共用一份历史。|
|`requests`|Sequence[CalculationPlan]|是|无|位置或关键字。本次范围内需要计算的指标请求，保持声明顺序并共享必要回读。|
|`parent`|str &#124; None|是|无|位置或关键字。当前结果关联的事件或片段ID；会话级结果使用None。|
|`start_ns`|int|是|无|位置或关键字。本次查询或计算的实际开始时刻，单位纳秒。|
|`end_ns`|int|是|无|位置或关键字。本次查询或计算的实际结束时刻，单位纳秒；按具体函数保留必要右端点供半开范围计算。|
|`partial`|bool|是|无|位置或关键字。父事件或窗口是否已经只有部分观测；该状态必须传到子指标，不能重新冒充完整。|
|`parent_coverage`|float &#124; None|是|无|位置或关键字。父范围的有效覆盖信息；None表示没有单独给出，具体判定沿该指标的覆盖政策。|

#### 返回说明

None。

#### 异常说明

原错误保留owner。

源码：[`src/chronaxis/execution/record_scope_calculations.py:146`](../../../src/chronaxis/execution/record_scope_calculations.py#L146)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordScopeCalculations-_finish_observation_tail"></a>
### `RecordScopeCalculations._finish_observation_tail`

用真实来源终点补查询尾段，既不补固定周期也不增加真实样本。

```python
RecordScopeCalculations._finish_observation_tail(key, calculation, end_ns)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`key`|tuple|是|无|位置或关键字。当前表达式、条件和驱动对应的共享流键；只用于定位已经保存的必要历史。|
|`calculation`|[RecordIntegral](chronaxis.execution.record_integral.md#api-RecordIntegral) &#124; [RecordTimeCalculation](chronaxis.execution.record_time_calculation.md#api-RecordTimeCalculation) &#124; [RecordSelection](chronaxis.execution.record_selection.md#api-RecordSelection)|是|无|位置或关键字。正在结算本次事件或窗口的统计器，只有实际间隔或样本操作需要观测尾边界。|
|`end_ns`|int|是|无|位置或关键字。查询的右端时刻，单位纳秒；还要裁到依赖来源的实际观测结束，不能延长数据有效期。|

#### 返回说明

None。

#### 异常说明

表达式、预算或累计错误沿查询清理路径传播。
只处理整个历史的最后一点；旧范围已有右邻点时绝不借用当前状态重新求值。

源码：[`src/chronaxis/execution/record_scope_calculations.py:186`](../../../src/chronaxis/execution/record_scope_calculations.py#L186)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordScopeCalculations-_flush"></a>
### `RecordScopeCalculations._flush`

右侧实际驱动到达才结算；EOF直接按已有点计算，不补周期。

```python
RecordScopeCalculations._flush(final=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`final`|bool|否|False|位置或关键字。是否已到真实EOF后的最终处理；True允许收紧观测末端和结束未完成状态。|

#### 返回说明

None。

#### 异常说明

原查询错，未退费用由close清理。

源码：[`src/chronaxis/execution/record_scope_calculations.py:224`](../../../src/chronaxis/execution/record_scope_calculations.py#L224)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordScopeCalculations-finish"></a>
### `RecordScopeCalculations.finish`

来源全部完成后处理常量和剩余事件。

```python
RecordScopeCalculations.finish(cursors)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`cursors`|Sequence[RecordSourceCursor]|是|无|位置或关键字。本次实际打开的来源游标，借用其真实首末时刻和EOF状态；调用方保留关闭责任。|

#### 返回说明

None。

#### 异常说明

原求值/计算错。

源码：[`src/chronaxis/execution/record_scope_calculations.py:248`](../../../src/chronaxis/execution/record_scope_calculations.py#L248)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordScopeCalculations-closed"></a>
### `RecordScopeCalculations.closed`

返回关闭事实。

```python
RecordScopeCalculations.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

bool。

#### 异常说明

无。

源码：[`src/chronaxis/execution/record_scope_calculations.py:264`](../../../src/chronaxis/execution/record_scope_calculations.py#L264)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordScopeCalculations-close"></a>
### `RecordScopeCalculations.close`

按责任关闭子资源，失败时保槽供重试。

```python
RecordScopeCalculations.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

原关闭错。

源码：[`src/chronaxis/execution/record_scope_calculations.py:268`](../../../src/chronaxis/execution/record_scope_calculations.py#L268)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

## 内部匿名回调


<a id="lambda-137"></a>
### 第137行匿名函数

```python
lambda request: self._request_stream[request.calculation_id]
```

|参数|含义|返回/异常|
|---|---|---|
|`request`|已声明的计算请求。|用calculation_id查询已登记的输入流，按同流分组；键缺失传播KeyError。|
