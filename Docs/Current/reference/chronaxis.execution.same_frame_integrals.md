# `chronaxis.execution.same_frame_integrals`

把同一物理报文的简单数值表达式直接交给现役实际时间积分器。

本对象只保存一个待完成同一时刻组；不构造信号数组、历史或通用最新状态。
读取、DBC投影、范围推进、积分器及结果发布仍由原会话负责。只有首帧前
证明绑定一致的内部调用方使用本入口，运行错误不切换路径或重读输入。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)、[D](chronaxis.core.types.md#api-SignalDType)、[LegacyDecodedUpdate](chronaxis.legacy.updates.md#api-LegacyDecodedUpdate)、[RecordIntegral](chronaxis.execution.record_integral.md#api-RecordIntegral)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)、[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)、[StaticExpression](chronaxis.core.expression.md#api-StaticExpression)

## 对象导航

|对象|用途|
|---|---|
|[`direct_integral_inputs`](#api-direct_integral_inputs)|检查直接积分的完整静态边界，不读取DBC或数据。|
|[`SameFrameBinding`](#api-SameFrameBinding)|保存同次DBC证明的共同定位；fd可为None，真实歧义继续由原投影器检查。|
|[`SameFrameBinding.matches`](#api-SameFrameBinding-matches)|匹配已投影更新。|
|[`same_frame_binding`](#api-same_frame_binding)|复用同次DBC字段事实证明唯一共同绑定，不加载文件。|
|[`_same_value`](#api-_same_value)|沿用同一时刻事实比较。|
|[`SameFrameIntegrals`](#api-SameFrameIntegrals)|拥有同一时刻选择和表达式上下文；借用积分器，关闭时不代替父会话关闭它们。|
|[`SameFrameIntegrals.__init__`](#api-SameFrameIntegrals-__init__)|检查静态表达式与实定义，预付有界状态，不读取输入。|
|[`SameFrameIntegrals._require_open`](#api-SameFrameIntegrals-_require_open)|失败后仅允许关闭。|
|[`SameFrameIntegrals.consume`](#api-SameFrameIntegrals-consume)|接收一条已投影报文，完整同一时刻组才推进积分。|
|[`SameFrameIntegrals._flush`](#api-SameFrameIntegrals-_flush)|提交完整同一时刻值，复用原表达式核及积分器。|
|[`SameFrameIntegrals.finish`](#api-SameFrameIntegrals-finish)|在原读取器确认EOF并关闭后，补算到来源真实末端的保持尾段。|
|[`SameFrameIntegrals.close`](#api-SameFrameIntegrals-close)|释放自有上下文及费用，借用积分器由父会话关闭。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from __future__ import annotations
from dataclasses import dataclass, replace
from math import isnan
from typing import Callable, Mapping, Sequence, TYPE_CHECKING
from ..core.binding import SignalDefinition
from ..core.expression import validate_expression
from ..core.expression_reference import _evaluate
from ..core.numeric import normalize_reference, ScalarValue
from ..core.scalar import _scalar_from_validated_fields
from ..core.types import SignalDType as D
from ..legacy.records import field_from_dict
from ..legacy.updates import LegacyDecodedUpdate
from ..planning.backend_selection import simple_numeric_expression
from ..results.budget import ResourceBudget, _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..results.errors import ResultClosedError
from ..sources.can_spec import can_field_from_key
from .history import _metadata_bytes
from .static_metadata import static_metadata_bytes
```

</details>

<a id="api-direct_integral_inputs"></a>
## `direct_integral_inputs`

检查直接积分的完整静态边界，不读取DBC或数据。

```python
direct_integral_inputs(plan: AnalysisPlan) -> tuple[SignalDefinition, ...] | None
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)|是|无|位置或关键字。已经完成静态后端选择的计划；检查直接积分全部条件，不读取DBC或报文。|

### 返回说明

本次必要定义tuple；不适用为None。

### 异常说明

非法带有明确类型的结构，不把运行错误当成选择其他路径的理由。

返回类型：tuple[[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition), ...] &#124; None。

源码：[`src/chronaxis/execution/same_frame_integrals.py:35`](../../../src/chronaxis/execution/same_frame_integrals.py#L35)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SameFrameBinding"></a>
## `SameFrameBinding`

保存同次DBC证明的共同定位；fd可为None，真实歧义继续由原投影器检查。

```python
class SameFrameBinding
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|str|是|无|当前计划中的来源名称。|
|`channel`|int|是|无|已转换为内部零起序号的通道。|
|`frame_id`|int|是|无|DBC和原配置共同定位的报文编号。|
|`extended`|bool|是|无|同次DBC字段事实已经确定的标准/扩展标记。|
|`fd`|bool &#124; None|是|无|原配置的CAN/FD约束；None保留原投影器的自动识别。|
|`dbc_fd`|bool|是|无|DBC声明的FD属性，沿用经典CAN兼容规则。|

源码：[`src/chronaxis/execution/same_frame_integrals.py:70`](../../../src/chronaxis/execution/same_frame_integrals.py#L70)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SameFrameBinding-matches"></a>
### `SameFrameBinding.matches`

匹配已投影更新。

```python
SameFrameBinding.matches(update: LegacyDecodedUpdate) -> bool
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`update`|[LegacyDecodedUpdate](chronaxis.legacy.updates.md#api-LegacyDecodedUpdate)|是|无|位置或关键字。原读取器和投影器已经验证的本条解码更新；无效新值也必须交付。|

#### 返回说明

bool。

#### 异常说明

非法内部对象属性错误。

返回类型：bool。

源码：[`src/chronaxis/execution/same_frame_integrals.py:80`](../../../src/chronaxis/execution/same_frame_integrals.py#L80)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-same_frame_binding"></a>
## `same_frame_binding`

复用同次DBC字段事实证明唯一共同绑定，不加载文件。

```python
same_frame_binding(definitions: tuple[SignalDefinition, ...], facts: Sequence[Mapping]) -> SameFrameBinding | None
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`definitions`|tuple[[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition), ...]|是|无|位置或关键字。表达式实际依赖的定义，所有字段应证明属于同一消息。|
|`facts`|Sequence[Mapping[str, object]]|是|无|位置或关键字。同次来源初始化得到的metadata.fields；包含已核定位和DBC帧型，不再次加载文件。|

### 返回说明

共同定位或None（交回普通路径）。

### 异常说明

已有元数据结构损坏；不能将损坏当不支持而吞错。

返回类型：[SameFrameBinding](chronaxis.execution.same_frame_integrals.md#api-SameFrameBinding) &#124; None。

源码：[`src/chronaxis/execution/same_frame_integrals.py:89`](../../../src/chronaxis/execution/same_frame_integrals.py#L89)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_same_value"></a>
## `_same_value`

沿用同一时刻事实比较。

```python
_same_value(left: ScalarValue, right: ScalarValue) -> bool
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`left`|[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)|是|无|位置或关键字。已归一化的同一时刻左值。|
|`right`|[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)|是|无|位置或关键字。已归一化的同一时刻右值；按类型、有效性、质量、码和值比较。|

### 返回说明

bool。

### 异常说明

无外部输入转换。

返回类型：bool。

源码：[`src/chronaxis/execution/same_frame_integrals.py:127`](../../../src/chronaxis/execution/same_frame_integrals.py#L127)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SameFrameIntegrals"></a>
## `SameFrameIntegrals`

拥有同一时刻选择和表达式上下文；借用积分器，关闭时不代替父会话关闭它们。

```python
SameFrameIntegrals(budget: ResourceBudget, definitions: tuple[SignalDefinition, ...], expressions: tuple[StaticExpression, ...], calculations: tuple[RecordIntegral, ...], binding: SameFrameBinding, session_id: str, before_group: Callable[[], None], *, derived: tuple=()) -> None
```


源码：[`src/chronaxis/execution/same_frame_integrals.py:134`](../../../src/chronaxis/execution/same_frame_integrals.py#L134)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SameFrameIntegrals-__init__"></a>
### `SameFrameIntegrals.__init__`

检查静态表达式与实定义，预付有界状态，不读取输入。

```python
SameFrameIntegrals.__init__(budget: ResourceBudget, definitions: tuple[SignalDefinition, ...], expressions: tuple[StaticExpression, ...], calculations: tuple[RecordIntegral, ...], binding: SameFrameBinding, session_id: str, before_group: Callable[[], None], *, derived: tuple=()) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)|是|无|位置或关键字。与父会话共享的受管理预算；构造时预付自有状态。|
|`definitions`|tuple[[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition), ...]|是|无|位置或关键字。已由来源补齐实际有效期的必要信号定义。|
|`expressions`|tuple[[StaticExpression](chronaxis.core.expression.md#api-StaticExpression), ...]|是|无|位置或关键字。已编译的简单数值表达式，逐项对应calculations。|
|`calculations`|tuple[[RecordIntegral](chronaxis.execution.record_integral.md#api-RecordIntegral), ...]|是|无|位置或关键字。父会话拥有的现役积分器；本对象只交付值，不替代父对象关闭它们。|
|`binding`|[SameFrameBinding](chronaxis.execution.same_frame_integrals.md#api-SameFrameBinding)|是|无|位置或关键字。首帧前已由同次DBC事实证明的共同消息定位。|
|`session_id`|str|是|无|位置或关键字。当前分析会话身份，分卷不重置。|
|`before_group`|Callable[[], None]|是|无|位置或关键字。积分缓冲即将结算时同步刷新真实观测范围；无参数且返回None，发生异常时直接交给调用者处理。|
|`derived`|tuple[DerivedDefinition, ...]|否|()|仅关键字。本计划原有派生声明，供静态校核使用；不额外计算未请求的输出。|

#### 返回说明

None。构造器预付并安装自有状态；调用SameFrameIntegrals(...)取得实例。

#### 异常说明

声明/预算/取消；未返回时附same_frame_cleanup_owner。

返回类型：None。

源码：[`src/chronaxis/execution/same_frame_integrals.py:137`](../../../src/chronaxis/execution/same_frame_integrals.py#L137)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SameFrameIntegrals-_require_open"></a>
### `SameFrameIntegrals._require_open`

失败后仅允许关闭。

```python
SameFrameIntegrals._require_open() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

ResultClosedError。

返回类型：None。

源码：[`src/chronaxis/execution/same_frame_integrals.py:207`](../../../src/chronaxis/execution/same_frame_integrals.py#L207)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SameFrameIntegrals-consume"></a>
### `SameFrameIntegrals.consume`

接收一条已投影报文，完整同一时刻组才推进积分。

```python
SameFrameIntegrals.consume(update: LegacyDecodedUpdate) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`update`|[LegacyDecodedUpdate](chronaxis.legacy.updates.md#api-LegacyDecodedUpdate)|是|无|位置或关键字。原读取器和投影器已经验证的本条解码更新；无效新值也必须交付。|

#### 返回说明

None。

#### 异常说明

身份、同一时刻冲突、预算、计算原错。
无效字段覆盖本次值，不沿用前条。未选择的帧只由原读取器维护观测范围。

返回类型：None。

源码：[`src/chronaxis/execution/same_frame_integrals.py:212`](../../../src/chronaxis/execution/same_frame_integrals.py#L212)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SameFrameIntegrals-_flush"></a>
### `SameFrameIntegrals._flush`

提交完整同一时刻值，复用原表达式核及积分器。

```python
SameFrameIntegrals._flush() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

原计算/预算错误。

返回类型：None。

源码：[`src/chronaxis/execution/same_frame_integrals.py:264`](../../../src/chronaxis/execution/same_frame_integrals.py#L264)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SameFrameIntegrals-finish"></a>
### `SameFrameIntegrals.finish`

在原读取器确认EOF并关闭后，补算到来源真实末端的保持尾段。

```python
SameFrameIntegrals.finish(observed_end: int | None) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`observed_end`|int &#124; None|是|无|位置或关键字。原游标确认EOF后的实际末端纳秒；无观测为None，不用配置终点补造数据。|

#### 返回说明

None。

#### 异常说明

原数值、预算或取消错误。
不替代EOF证明，不把domain.end当采集终点，不虚构固定周期。

返回类型：None。

源码：[`src/chronaxis/execution/same_frame_integrals.py:301`](../../../src/chronaxis/execution/same_frame_integrals.py#L301)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SameFrameIntegrals-close"></a>
### `SameFrameIntegrals.close`

释放自有上下文及费用，借用积分器由父会话关闭。

```python
SameFrameIntegrals.close() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

释放失败可重试。

返回类型：None。

源码：[`src/chronaxis/execution/same_frame_integrals.py:325`](../../../src/chronaxis/execution/same_frame_integrals.py#L325)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
