# `chronaxis.execution.parallel_point_session`

time_order直接积分的组点并行会话：文件工作进程送同一时刻组点，主进程按串行顺序归并并积分。

PERF-P5-ORDER-01（A1、A2合同）。适用计划与连续多文件并行积分相同，只是来源`file_merge`为
`time_order`、进程上限1及以上都可以（parallel_point_inputs）。

输入：已验证计划、共享预算、共用需求分析结果和本次会话工作目录。
输出：与计划计算项同序的RecordIntegralResult，以及供结果清单使用的帧型兼容提示；
与现有串行time_order直接积分逐位相同。

流程：
1. prepare：首帧前核对时间范围、静态和动态条件及预算，任一不满足就返回False沿用现有路径；
2. execute读取段：ParallelPointPool收齐全部文件的组点包写入PointSpool，读取段错误一律在此报出；
3. execute归并段：关闭工作进程后，按（时间、文件位置）k路归并各文件组点，同一时刻的各文件部分按
   文件位置依次合并；先核跨文件帧型、再合并、遇延迟错误按原类型抛出，最后用SameFrameIntegrals
   的同一求值与积分规则推进RecordIntegral；
4. 交付结果前删除暂存。失败只清理本次登记的进程、暂存与费用，不重读、不换路径。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisError](chronaxis.results.errors.md#api-AnalysisError)、[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)、[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)、[InputRequirements](chronaxis.planning.input_requirements.md#api-InputRequirements)、[Interval](chronaxis.core.models.md#api-Interval)、[RecordIntegralResult](chronaxis.execution.record_integral.md#api-RecordIntegralResult)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)、[SourceReadError](chronaxis.sources.protocol.md#api-SourceReadError)

## 对象导航

|对象|用途|
|---|---|
|[`parallel_point_inputs`](#api-parallel_point_inputs)|判断已经选择后端的计划能否使用time_order组点并行（A1-1静态部分）。|
|[`ParallelPointSession`](#api-ParallelPointSession)|拥有一次time_order组点任务：工作池、暂存、同帧积分owner和积分器。|
|[`ParallelPointSession.fixed_cost`](#api-ParallelPointSession-fixed_cost)|查询会话声明费，供构造及首帧前准入共用。|
|[`ParallelPointSession.__init__`](#api-ParallelPointSession-__init__)|登记自有资源槽并预付有限声明空间，不读输入。|
|[`ParallelPointSession._new`](#api-ParallelPointSession-_new)|接管构造未返回的资源。|
|[`ParallelPointSession.prepare`](#api-ParallelPointSession-prepare)|读取同次DBC元数据并建立积分状态，在首帧前决定是否适用（A1-1、A2-7）。|
|[`ParallelPointSession._update_bounds`](#api-ParallelPointSession-_update_bounds)|同步全部文件的实际观测范围。|
|[`ParallelPointSession._retain_notices`](#api-ParallelPointSession-_retain_notices)|保留本次实际帧型兼容提示，规则与连续并行积分会话相同。|
|[`ParallelPointSession._merge`](#api-ParallelPointSession-_merge)|归并段：k路归并各文件组点，合并同一时刻组并交给同帧积分owner（A2-6）。|
|[`ParallelPointSession._merge.advance`](#api-ParallelPointSession-_merge-advance)|取文件的下一个事件压入堆。|
|[`ParallelPointSession.execute`](#api-ParallelPointSession-execute)|执行读取段与归并段，全部完成后交付最终结果。|
|[`ParallelPointSession.close`](#api-ParallelPointSession-close)|关闭真实资源后逐项退款，失败保留所有权供重试。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from __future__ import annotations
from dataclasses import replace
from time import process_time, perf_counter
from typing import TYPE_CHECKING
from ..core.calculations import CalculationDefinition
from ..core.models import Interval
from ..results.budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..results.errors import AnalysisError, ResultClosedError
from ..sources.protocol import SourceReadError
from .history import _metadata_bytes
from .same_frame_integrals import direct_integral_inputs
```

</details>

<a id="api-parallel_point_inputs"></a>
## `parallel_point_inputs`

判断已经选择后端的计划能否使用time_order组点并行（A1-1静态部分）。

```python
parallel_point_inputs(plan: AnalysisPlan) -> tuple[SignalDefinition, ...] | None
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)|是|无|位置或关键字。plan为公共入口已验证并解析后端的计划|

### 返回说明

实际依赖信号定义tuple；不适用返回None，不读取DBC或原文件。

### 异常说明

非法内部计划结构的属性错误；运行错误不作为切换路径的依据。
与parallel_integral_inputs只有两点不同：要求time_order；进程上限为1也适用。
time_scope为source的动态条件需要需求分析结果，在ParallelPointSession.prepare中核对。

返回类型：tuple[[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition), ...] &#124; None。

源码：[`src/chronaxis/execution/parallel_point_session.py:42`](../../../src/chronaxis/execution/parallel_point_session.py#L42)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelPointSession"></a>
## `ParallelPointSession`

拥有一次time_order组点任务：工作池、暂存、同帧积分owner和积分器。

准备阶段只取得DBC事实；读取许可在数值任务安装后才发出。失败后只清理，不重扫输入。
关闭保留统计和帧型提示，供父会话写清单。

```python
ParallelPointSession(plan: AnalysisPlan, budget: ResourceBudget, requirements: InputRequirements, work_dir) -> None
```


源码：[`src/chronaxis/execution/parallel_point_session.py:76`](../../../src/chronaxis/execution/parallel_point_session.py#L76)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelPointSession-fixed_cost"></a>
### `ParallelPointSession.fixed_cost`

查询会话声明费，供构造及首帧前准入共用。

```python
ParallelPointSession.fixed_cost(plan: AnalysisPlan) -> int
```

装饰器：`staticmethod`。

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)|是|无|位置或关键字。plan为已选中的AnalysisPlan。|

#### 返回说明

int，保守预约的字节数。

#### 异常说明

不适用计划时ValueError；静态模型原错误继续传播。

返回类型：int。

源码：[`src/chronaxis/execution/parallel_point_session.py:84`](../../../src/chronaxis/execution/parallel_point_session.py#L84)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelPointSession-__init__"></a>
### `ParallelPointSession.__init__`

登记自有资源槽并预付有限声明空间，不读输入。

```python
ParallelPointSession.__init__(plan: AnalysisPlan, budget: ResourceBudget, requirements: InputRequirements, work_dir) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)|是|无|位置或关键字。plan为适用计划|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)|是|无|位置或关键字。budget为父会话账本|
|`requirements`|[InputRequirements](chronaxis.planning.input_requirements.md#api-InputRequirements)|是|无|位置或关键字。requirements为共用需求|
|`work_dir`|str &#124; Path|是|无|位置或关键字。本次会话自有工作目录，组点暂存目录建在其下。|

#### 返回说明

None。

#### 异常说明

不适用计划时ValueError；预算不足时BudgetExceededError，清理失败附parallel_point_session_cleanup_owner。

返回类型：None。

源码：[`src/chronaxis/execution/parallel_point_session.py:95`](../../../src/chronaxis/execution/parallel_point_session.py#L95)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelPointSession-_new"></a>
### `ParallelPointSession._new`

接管构造未返回的资源。

```python
ParallelPointSession._new(factory, recovery, *args, **kwargs)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`factory`|type|是|无|位置或关键字。要构造的资源类。|
|`recovery`|str|是|无|位置或关键字。构造异常上携带待清理owner的属性名。|
|`args`|tuple|否|()|可变位置。args、kwargs为构造参数。|
|`kwargs`|dict|否|{}|可变关键字。args、kwargs为构造参数。|

#### 返回说明

新owner。

#### 异常说明

原构造错误，已部分创建的资源记入_pending。

源码：[`src/chronaxis/execution/parallel_point_session.py:124`](../../../src/chronaxis/execution/parallel_point_session.py#L124)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelPointSession-prepare"></a>
### `ParallelPointSession.prepare`

读取同次DBC元数据并建立积分状态，在首帧前决定是否适用（A1-1、A2-7）。

```python
ParallelPointSession.prepare() -> bool
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

bool；True表示已安装数值任务并许可读取，False表示条件或预算不适用、输入未被消费。

#### 异常说明

重复调用或已关闭时ResultClosedError；DBC、类型、预算及进程错误原样传播，False不用于吞掉运行错误。

返回类型：bool。

源码：[`src/chronaxis/execution/parallel_point_session.py:136`](../../../src/chronaxis/execution/parallel_point_session.py#L136)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelPointSession-_update_bounds"></a>
### `ParallelPointSession._update_bounds`

同步全部文件的实际观测范围。

```python
ParallelPointSession._update_bounds() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

非法内部时间。

读取段结束时范围已是最终值（A1-8）；省略domain时把积分器窗口改为该范围，与现有路径相同。

返回类型：None。

源码：[`src/chronaxis/execution/parallel_point_session.py:218`](../../../src/chronaxis/execution/parallel_point_session.py#L218)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelPointSession-_retain_notices"></a>
### `ParallelPointSession._retain_notices`

保留本次实际帧型兼容提示，规则与连续并行积分会话相同。

```python
ParallelPointSession._retain_notices() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

元数据或预算错误。

返回类型：None。

源码：[`src/chronaxis/execution/parallel_point_session.py:230`](../../../src/chronaxis/execution/parallel_point_session.py#L230)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelPointSession-_merge"></a>
### `ParallelPointSession._merge`

归并段：k路归并各文件组点，合并同一时刻组并交给同帧积分owner（A2-6）。

```python
ParallelPointSession._merge(identities) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`identities`|tuple[tuple[bool, bool] &#124; None, ...]|是|无|位置或关键字。按文件序号排列的实际帧型（扩展帧, FD），无目标帧的文件为None。|

#### 返回说明

None。

#### 异常说明

跨文件帧型不一致、同一时刻冲突或延迟错误时按串行相同的类型和信息抛出；暂存读回、
    时间次序或积分器错误原样传播。

返回类型：None。

源码：[`src/chronaxis/execution/parallel_point_session.py:235`](../../../src/chronaxis/execution/parallel_point_session.py#L235)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelPointSession-_merge-advance"></a>
### `ParallelPointSession._merge.advance`

取文件的下一个事件压入堆。

```python
ParallelPointSession._merge.advance(index)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`index`|int|是|无|位置或关键字。要取下一个事件的文件序号。|

#### 返回说明

None。

#### 异常说明

读回错误或文件内时间倒退。

源码：[`src/chronaxis/execution/parallel_point_session.py:252`](../../../src/chronaxis/execution/parallel_point_session.py#L252)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelPointSession-execute"></a>
### `ParallelPointSession.execute`

执行读取段与归并段，全部完成后交付最终结果。

```python
ParallelPointSession.execute() -> tuple[RecordIntegralResult, ...]
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

与计划计算项同序的RecordIntegralResult tuple。

#### 异常说明

读取段错误（SourceReadError）、归并段的串行同类错误、暂存或累计错误；不交付失败前缀。

返回类型：tuple[[RecordIntegralResult](chronaxis.execution.record_integral.md#api-RecordIntegralResult), ...]。

源码：[`src/chronaxis/execution/parallel_point_session.py:305`](../../../src/chronaxis/execution/parallel_point_session.py#L305)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelPointSession-close"></a>
### `ParallelPointSession.close`

关闭真实资源后逐项退款，失败保留所有权供重试。

```python
ParallelPointSession.close() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None；成功后幂等。

#### 异常说明

子资源关闭或账本原错。

返回类型：None。

源码：[`src/chronaxis/execution/parallel_point_session.py:345`](../../../src/chronaxis/execution/parallel_point_session.py#L345)（行号对应 Chronaxis 0.1.0.dev6 源码）。
