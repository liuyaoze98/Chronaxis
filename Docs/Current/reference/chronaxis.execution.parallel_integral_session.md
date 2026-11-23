# `chronaxis.execution.parallel_integral_session`

把连续文件的内部面积生成交给工作进程，保留主会话的原序积分结果。

本模块只服务于已确认的同帧、ZOH 会话积分，全部积分项共用实际间隔、同一个
固定间隔或DBC周期；DBC周期取同次DBC核实的驱动报文周期。读取配置沿用普通
CAN 并行路径；未满足静态条件时不创建资源。工作进程不发布结果，主进程
负责跨文件状态和最终累计，所有自有进程及预算由本次会话关闭。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisError](chronaxis.results.errors.md#api-AnalysisError)、[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)、[CANTextSpec](chronaxis.sources.text_can_spec.md#api-CANTextSpec)、[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)、[InputRequirements](chronaxis.planning.input_requirements.md#api-InputRequirements)、[Interval](chronaxis.core.models.md#api-Interval)、[RecordIntegralResult](chronaxis.execution.record_integral.md#api-RecordIntegralResult)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)、[SourceInputRequirements](chronaxis.planning.input_requirements.md#api-SourceInputRequirements)、[SourcePlan](chronaxis.planning.models.md#api-SourcePlan)

## 对象导航

|对象|用途|
|---|---|
|[`parallel_integral_inputs`](#api-parallel_integral_inputs)|判断已经选择后端的计划能否使用连续多文件面积生成。|
|[`parallel_integral_source`](#api-parallel_integral_source)|取得普通并行 CAN 读取使用的来源与选中字段政策。|
|[`ParallelIntegralSession`](#api-ParallelIntegralSession)|拥有一次面积并行任务和父累计状态，最终结果沿原会话发布。|
|[`ParallelIntegralSession.fixed_cost`](#api-ParallelIntegralSession-fixed_cost)|查询会话声明费，供构造及首帧前准入共用。|
|[`ParallelIntegralSession.__init__`](#api-ParallelIntegralSession-__init__)|登记自有资源槽并预付有限声明空间。|
|[`ParallelIntegralSession._new`](#api-ParallelIntegralSession-_new)|接管构造未返回的资源。|
|[`ParallelIntegralSession.prepare`](#api-ParallelIntegralSession-prepare)|读取同次 DBC 元数据并建立父累计器，在首帧前决定是否适用。|
|[`ParallelIntegralSession._update_bounds`](#api-ParallelIntegralSession-_update_bounds)|同步已消费输入的实际范围。|
|[`ParallelIntegralSession.execute`](#api-ParallelIntegralSession-execute)|按文件顺序消费面积及边界，全部 EOF 后交付最终结果。|
|[`ParallelIntegralSession._retain_notices`](#api-ParallelIntegralSession-_retain_notices)|保留本次实际帧型兼容提示。|
|[`ParallelIntegralSession.close`](#api-ParallelIntegralSession-close)|关闭真实资源后逐项退款，失败保留所有权供重试。|

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
from ..sources.can_spec import can_field_from_key
from .history import _metadata_bytes
from .same_frame_integrals import direct_integral_inputs
```

</details>

<a id="api-parallel_integral_inputs"></a>
## `parallel_integral_inputs`

判断已经选择后端的计划能否使用连续多文件面积生成。

```python
parallel_integral_inputs(plan: AnalysisPlan) -> tuple[SignalDefinition, ...] | None
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)|是|无|位置或关键字。已验证并解析数值后端的计划；调用方另外确认原请求为auto，只检查适用范围，不读DBC或原帧。|

### 返回说明

实际依赖信号定义 tuple；不适用返回 None，不读取 DBC 或原文件。

### 异常说明

非法内部计划结构的属性错误，运行错误不作为切换路径的依据。

返回类型：tuple[[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition), ...] &#124; None。

源码：[`src/chronaxis/execution/parallel_integral_session.py:33`](../../../src/chronaxis/execution/parallel_integral_session.py#L33)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-parallel_integral_source"></a>
## `parallel_integral_source`

取得普通并行 CAN 读取使用的来源与选中字段政策。

```python
parallel_integral_source(source: SourcePlan, definitions: tuple[SignalDefinition, ...], requirement: SourceInputRequirements, intervals: tuple=()) -> tuple[CANTextSpec, dict]
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|[SourcePlan](chronaxis.planning.models.md#api-SourcePlan)|是|无|位置或关键字。当前计划唯一的ASC/BLF来源，沿用普通并行CAN读取的源配置和解码政策。|
|`definitions`|tuple[[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition), ...]|是|无|位置或关键字。本次积分实际依赖的信号定义，按冻结顺序排列；已由同次DBC事实补齐有效期。|
|`requirement`|[SourceInputRequirements](chronaxis.planning.input_requirements.md#api-SourceInputRequirements)|是|无|位置或关键字。共用需求分析对该来源的结果，决定目标ID和所需时间检查范围。|
|`intervals`|tuple|否|()|位置或关键字。intervals 为计划已解析的 (消费者, IntervalChoice) tuple，默认空，用于请求DBC驱动周期。|

### 返回说明

(CANTextSpec, options)，直接供现有 CANTextDecodeRead 使用。

### 异常说明

内部来源或字段结构错误；不加载 DBC，不读取文件。
此函数限无导出、无追溯的直接积分子集；选中时间检查与全来源观测仍分开。
周期请求与普通记录游标相同：先按间隔声明顺序列DBC驱动字段，再列未填有效期的字段，
使缺少DBC周期时由同一检查报告同一字段。

返回类型：tuple[[CANTextSpec](chronaxis.sources.text_can_spec.md#api-CANTextSpec), dict]。

源码：[`src/chronaxis/execution/parallel_integral_session.py:66`](../../../src/chronaxis/execution/parallel_integral_session.py#L66)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelIntegralSession"></a>
## `ParallelIntegralSession`

拥有一次面积并行任务和父累计状态，最终结果沿原会话发布。

准备阶段仅取得 DBC 事实；实际读取必须等待绑定证明、有效期和数值任务
安装。失败后只清理，不重扫输入。关闭保留统计和必要帧型提示，供父会话
写清单；原记录、面积块和完整元数据不作为默认输出保存。

```python
ParallelIntegralSession(plan: AnalysisPlan, budget: ResourceBudget, requirements: InputRequirements) -> None
```


源码：[`src/chronaxis/execution/parallel_integral_session.py:111`](../../../src/chronaxis/execution/parallel_integral_session.py#L111)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelIntegralSession-fixed_cost"></a>
### `ParallelIntegralSession.fixed_cost`

查询会话声明费，供构造及首帧前准入共用。

```python
ParallelIntegralSession.fixed_cost(plan: AnalysisPlan) -> int
```

装饰器：`staticmethod`。

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)|是|无|位置或关键字。已满足静态并行积分条件的计划，用于计算会话声明固定费用。|

#### 返回说明

int，保守预约的字节数。

#### 异常说明

不适用计划时ValueError；静态模型原错误继续传播。

返回类型：int。

源码：[`src/chronaxis/execution/parallel_integral_session.py:120`](../../../src/chronaxis/execution/parallel_integral_session.py#L120)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelIntegralSession-__init__"></a>
### `ParallelIntegralSession.__init__`

登记自有资源槽并预付有限声明空间。

```python
ParallelIntegralSession.__init__(plan: AnalysisPlan, budget: ResourceBudget, requirements: InputRequirements) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)|是|无|位置或关键字。已满足静态条件的连续多文件会话计划，尚未读取原帧。|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)|是|无|位置或关键字。与父会话共享的受管理预算；本对象只预约和归还自身持有的费用。|
|`requirements`|[InputRequirements](chronaxis.planning.input_requirements.md#api-InputRequirements)|是|无|位置或关键字。当前计划的共用输入需求，按来源获取解码和时间检查范围。|

#### 返回说明

None，构造新的会话owner，尚未读取原帧。

#### 异常说明

不适用计划时ValueError；预算不足时BudgetExceededError，
    清理失败附parallel_integral_session_cleanup_owner。

返回类型：None。

源码：[`src/chronaxis/execution/parallel_integral_session.py:131`](../../../src/chronaxis/execution/parallel_integral_session.py#L131)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelIntegralSession-_new"></a>
### `ParallelIntegralSession._new`

接管构造未返回的资源。

```python
ParallelIntegralSession._new(factory, recovery, *args, **kwargs)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`factory`|Callable[..., object]|是|无|位置或关键字。构造受本会话管理资源的工厂；返回需要close清理的owner。|
|`recovery`|str|是|无|位置或关键字。构造失败异常上保存清理owner的准确属性名，不按异常文字推断资源。|
|`args`|tuple[object, ...]|否|()|可变位置。原样交给factory的位置参数。|
|`kwargs`|dict[str, object]|否|{}|可变关键字。原样交给factory的关键字参数。|

#### 返回说明

object，factory成功返回的资源owner；构造失败时只接管恢复属性并重新抛出原异常。

#### 异常说明

原错。

源码：[`src/chronaxis/execution/parallel_integral_session.py:161`](../../../src/chronaxis/execution/parallel_integral_session.py#L161)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelIntegralSession-prepare"></a>
### `ParallelIntegralSession.prepare`

读取同次 DBC 元数据并建立父累计器，在首帧前决定是否适用。

```python
ParallelIntegralSession.prepare() -> bool
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

bool；True表示已安装数值任务，False表示绑定不能证明同帧或预算不适合。

#### 异常说明

重复调用或已关闭时ResultClosedError；DBC、类型、预算及进程错误原样传播，
    False不用于吞掉运行错误。

返回类型：bool。

源码：[`src/chronaxis/execution/parallel_integral_session.py:169`](../../../src/chronaxis/execution/parallel_integral_session.py#L169)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelIntegralSession-_update_bounds"></a>
### `ParallelIntegralSession._update_bounds`

同步已消费输入的实际范围。

```python
ParallelIntegralSession._update_bounds() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

非法内部时间。

没有显式 domain 时，只修改最终分类所需窗口；不构造第二条时间轴。

返回类型：None。

源码：[`src/chronaxis/execution/parallel_integral_session.py:250`](../../../src/chronaxis/execution/parallel_integral_session.py#L250)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelIntegralSession-execute"></a>
### `ParallelIntegralSession.execute`

按文件顺序消费面积及边界，全部 EOF 后交付最终结果。

```python
ParallelIntegralSession.execute() -> tuple[RecordIntegralResult, ...]
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

与计划计算项同序的 RecordIntegralResult tuple。

#### 异常说明

原始读取、边界、累计或关闭错误；不交付失败前缀。

返回类型：tuple[[RecordIntegralResult](chronaxis.execution.record_integral.md#api-RecordIntegralResult), ...]。

源码：[`src/chronaxis/execution/parallel_integral_session.py:261`](../../../src/chronaxis/execution/parallel_integral_session.py#L261)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelIntegralSession-_retain_notices"></a>
### `ParallelIntegralSession._retain_notices`

保留本次实际帧型兼容提示。

```python
ParallelIntegralSession._retain_notices() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

元数据或预算错误。

返回类型：None。

源码：[`src/chronaxis/execution/parallel_integral_session.py:309`](../../../src/chronaxis/execution/parallel_integral_session.py#L309)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelIntegralSession-close"></a>
### `ParallelIntegralSession.close`

关闭真实资源后逐项退款，失败保留所有权供重试。

```python
ParallelIntegralSession.close() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None；成功后幂等。

#### 异常说明

子资源关闭或账本原错。

返回类型：None。

源码：[`src/chronaxis/execution/parallel_integral_session.py:334`](../../../src/chronaxis/execution/parallel_integral_session.py#L334)（行号对应 Chronaxis 0.1.0.dev6 源码）。
