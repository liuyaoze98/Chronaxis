# `chronaxis.core.models`

把调用者提供的内存观测构造成不可变模型，并检查身份、时间和质量约束。

输入包括会话和来源标识、整数纳秒坐标、原字段值及显式质量原因；输出时间范围、
时基、内存行、来源、会话、数据集和信号样本。构造时检查结构及范围，复制字段
映射为只读快照，拒绝来源时间回退，不排序或补齐数据。样本归属和声明类型
通过显式方法检查，模型构造不会执行信号绑定、保持或分析。
本模块只依赖标准库和整数时间协议，不读取文件，不加载NumPy或CAN组件，
不持有运行状态；SourceSpec当前只接受内存行。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[QualityFlag](chronaxis.core.types.md#api-QualityFlag)、[SignalDType](chronaxis.core.types.md#api-SignalDType)、[SourceType](chronaxis.core.types.md#api-SourceType)、[TimeType](chronaxis.core.types.md#api-TimeType)

## 对象导航

|对象|用途|
|---|---|
|[`Interval`](#api-Interval)|保存左闭右开纳秒范围，允许零长度，不允许反向或跨度溢出。|
|[`Interval.__post_init__`](#api-Interval-__post_init__)|构造时验证边界及完整整数跨度。|
|[`Interval.duration_ns`](#api-Interval-duration_ns)|返回已经验证的半开范围长度，不补样本周期。|
|[`Interval.contains`](#api-Interval-contains)|检查连续半开或显式点上下文成员关系。|
|[`TimebaseSpec`](#api-TimebaseSpec)|保存时间坐标种类及其起点声明，供来源映射和同步检查使用。|
|[`TimebaseSpec.__post_init__`](#api-TimebaseSpec-__post_init__)|检查时基类型和起点声明的一致性。|
|[`MemoryRow`](#api-MemoryRow)|保存一条内存观测的原时间、来源序号和原字段值。|
|[`MemoryRow.__post_init__`](#api-MemoryRow-__post_init__)|验证行容器并创建后不可修改的字段值快照。|
|[`SourceSpec`](#api-SourceSpec)|描述冻结内存来源及固定时钟偏移，不执行读取或绑定。|
|[`SourceSpec.__post_init__`](#api-SourceSpec-__post_init__)|检查来源形状、顺序、身份和固定偏移范围。|
|[`SourceRef`](#api-SourceRef)|用会话、来源和原字段定位内存样本，不以别名当全局数据键。|
|[`SourceRef.__post_init__`](#api-SourceRef-__post_init__)|验证可追溯身份，不解析字段为表达式。|
|[`SignalSample`](#api-SignalSample)|保留观测原值、显式有效性、质量原因及完整内存来源身份。|
|[`SignalSample.__post_init__`](#api-SignalSample-__post_init__)|拒绝类型/质量自相矛盾的样本，保留非法观测的诊断值。|
|[`SignalSample.validate_dtype`](#api-SignalSample-validate_dtype)|在已声明定义类型下验证有效值，不执行隐式归一化。|
|[`SessionSpec`](#api-SessionSpec)|保存一个会话的分析范围和来源集合。|
|[`SessionSpec.__post_init__`](#api-SessionSpec-__post_init__)|校验会话范围、带有明确类型的来源和唯一名称。|
|[`SessionSpec.validate_sample`](#api-SessionSpec-validate_sample)|检查样本会话/来源/字段和观测范围，不执行绑定或读取。|
|[`DatasetSpec`](#api-DatasetSpec)|保存一个分析对象、一个会话及其数据集身份。|
|[`DatasetSpec.__post_init__`](#api-DatasetSpec-__post_init__)|检查首版数据集身份与单会话类型。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from ..timebase.conversion import INT64_MAX, INT64_MIN, checked_add_ns, require_int64_ns
from .types import QualityFlag, SignalDType, SourceType, TimeType
from .validation import require_identifier, require_scalar, require_sequence, require_text
```

</details>

<a id="api-Interval"></a>
## `Interval`

保存左闭右开纳秒范围，允许零长度，不允许反向或跨度溢出。

构造校验时间/长度为int64；点上下文可显式包含end，不改变连续半开。

```python
class Interval
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`start_ns`|int|是|无|包含的开始坐标，整数纳秒。|
|`end_ns`|int|是|无|连续范围不包含的终点，允许等于开始。|

源码：[`src/chronaxis/core/models.py:24`](../../../src/chronaxis/core/models.py#L24)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-Interval-__post_init__"></a>
### `Interval.__post_init__`

构造时验证边界及完整整数跨度。

```python
Interval.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无额外参数；读取start_ns/end_ns，拒绝bool和float。

#### 返回说明

None；字段规范为精确Python整数并冻结。

#### 异常说明

TypeError为错误类型；ValueError为反向；TimeOverflowError为超界。

本函数直接报告的具体错误：

- `ValueError`：end_ns不能早于start_ns。

#### 副作用说明

只在初始化中规范自身字段，不修改调用方输入。

返回类型：None。

源码：[`src/chronaxis/core/models.py:33`](../../../src/chronaxis/core/models.py#L33)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-Interval-duration_ns"></a>
### `Interval.duration_ns`

返回已经验证的半开范围长度，不补样本周期。

```python
Interval.duration_ns() -> int
```

参数：无显式参数。


#### 参数说明

无额外参数；读取当前边界。

#### 返回说明

int；非负int64纳秒，零长度返回0。

#### 异常说明

无主动异常；构造已验证范围。

返回类型：int。

源码：[`src/chronaxis/core/models.py:54`](../../../src/chronaxis/core/models.py#L54)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-Interval-contains"></a>
### `Interval.contains`

检查连续半开或显式点上下文成员关系。

```python
Interval.contains(time_ns: int, *, point: bool=False) -> bool
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|位置或关键字。time_ns为int64纳秒|
|`point`|bool|否|False|仅关键字。point (bool)默认False，True包含实际末点。|

#### 返回说明

bool；零长度连续范围为空，点上下文可包含唯一端点。

#### 异常说明

TypeError为时间/point类型错误；TimeOverflowError为坐标超界。

本函数直接报告的具体错误：

- `TypeError`：point必须为bool。

返回类型：bool。

源码：[`src/chronaxis/core/models.py:64`](../../../src/chronaxis/core/models.py#L64)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TimebaseSpec"></a>
## `TimebaseSpec`

保存时间坐标种类及其起点声明，供来源映射和同步检查使用。

relative表示相对坐标，必须提供origin。absolute表示已经规范化的UTC纳秒，
不再接受相对起点。字段不可变，不读取机器时区；相同timebase_id本身不能
证明来源同步，联合计算仍须检查完整时基或显式同步证据。

```python
class TimebaseSpec
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`timebase_id`|str|是|无|当前显式时间基准ID，不从文件名猜测。|
|`time_type`|[TimeType](chronaxis.core.types.md#api-TimeType)|是|无|TimeType.RELATIVE表示相对于明确起点的时间，需填写origin；TimeType.ABSOLUTE表示UTC绝对时间，以Unix epoch为基准。不要把相对0秒当成1970年的绝对时间。|
|`origin`|str &#124; None|否|None|相对来源明确起点标签；绝对坐标使用UTC epoch。 None表示未提供相对时间的共同起点标签，不能仅据此把两个相对时钟当作已同步。|

源码：[`src/chronaxis/core/models.py:82`](../../../src/chronaxis/core/models.py#L82)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TimebaseSpec-__post_init__"></a>
### `TimebaseSpec.__post_init__`

检查时基类型和起点声明的一致性。

```python
TimebaseSpec.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无额外参数；读取timebase_id/time_type/origin。

#### 返回说明

None；保留调用者起点原文。

#### 异常说明

TypeError为错误类型；ValueError为名称/起点缺项或冲突。

本函数直接报告的具体错误：

- `TypeError`：kind必须为TimeType。
- `ValueError`：absolute时基不接受relative origin。

返回类型：None。

源码：[`src/chronaxis/core/models.py:94`](../../../src/chronaxis/core/models.py#L94)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-MemoryRow"></a>
## `MemoryRow`

保存一条内存观测的原时间、来源序号和原字段值。

values会复制为只读映射，None、NaN和无穷值保留供后续质量检查。一行可以
包含多个字段或没有字段；sequence是稳定的非负来源序号，同时间不同序号
分别保留。本模型不为原字段绑定表达式别名。

```python
class MemoryRow
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|来源原坐标，offset在分析层显式应用。|
|`values`|Mapping[str, int &#124; float &#124; bool &#124; str &#124; None]|是|无|原字段到原值，非表达式名。|
|`sequence`|int|是|无|来源内原序号，同时间不同序号不去重。|

源码：[`src/chronaxis/core/models.py:117`](../../../src/chronaxis/core/models.py#L117)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-MemoryRow-__post_init__"></a>
### `MemoryRow.__post_init__`

验证行容器并创建后不可修改的字段值快照。

```python
MemoryRow.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无额外参数；values接受Mapping，值仅原生不可变标量。

#### 返回说明

None；时间/序号规范为整数、values为新只读映射。

#### 异常说明

TypeError/ValueError为容器/字段/值/序号错误；TimeOverflowError为时间超界。

本函数直接报告的具体错误：

- `TypeError`：values必须为字段Mapping。

#### 副作用说明

复制值映射，不改原映射，不持有可变嵌套值。

返回类型：None。

源码：[`src/chronaxis/core/models.py:129`](../../../src/chronaxis/core/models.py#L129)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SourceSpec"></a>
## `SourceSpec`

描述冻结内存来源及固定时钟偏移，不执行读取或绑定。

rows为原坐标、非递减顺序；sequence唯一，同时间不同序号保留。
observation边界是来源原坐标，未知端点为None，不补假设周期。
所有已知坐标加offset必须合法；无任何自动排序、同步推断或缓存优化。

```python
class SourceSpec
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|会话内来源名，须唯一；跨会话可复用同名。|
|`timebase`|[TimebaseSpec](chronaxis.core.models.md#api-TimebaseSpec)|是|无|显式来源时基/起点，不继承上次任务。|
|`rows`|tuple[[MemoryRow](chronaxis.core.models.md#api-MemoryRow), ...]|是|无|原顺序只读行；空来源合法。|
|`offset_ns`|int|否|0|明确固定偏移，默认0不构成同步证明。|
|`observation_start_ns`|int &#124; None|否|None|已知来源开始坐标，否则unknown。 None表示开始范围未知，不自动当作0。|
|`observation_end_ns`|int &#124; None|否|None|已知来源末点坐标，否则unknown。 None表示末端范围未知，不自动用请求终点补齐。|
|`source_type`|[SourceType](chronaxis.core.types.md#api-SourceType)|否|SourceType.MEMORY|填SourceType.MEMORY，表示已准备好的内存信号。这是底层内存模型；公共AnalysisRunner另外支持CSV、BLF、ASC及原始CAN CSV，见[输入](../inputs.md)。|

源码：[`src/chronaxis/core/models.py:162`](../../../src/chronaxis/core/models.py#L162)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SourceSpec-__post_init__"></a>
### `SourceSpec.__post_init__`

检查来源形状、顺序、身份和固定偏移范围。

```python
SourceSpec.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无额外参数；rows必须tuple[MemoryRow]，不隐式转换列表/生成器。

#### 返回说明

None；offset及已知观测边界规范为整数，原rows保持顺序。

#### 异常说明

TypeError为结构；ValueError为回退/重复序号/边界冲突；TimeOverflowError为坐标/偏移溢出。

本函数直接报告的具体错误：

- `TypeError`：source需要TimebaseSpec、SourceType.MEMORY和tuple rows。
- `TypeError`：rows元素必须为MemoryRow。
- `ValueError`：source rows时间必须非递减。
- `ValueError`：source rows sequence重复。
- `ValueError`：source row超出已声明观测边界。

#### 副作用说明

只用局部校验集合，无数据读写/排序/归并或后端数值执行。

返回类型：None。

源码：[`src/chronaxis/core/models.py:178`](../../../src/chronaxis/core/models.py#L178)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SourceRef"></a>
## `SourceRef`

用会话、来源和原字段定位内存样本，不以别名当全局数据键。

字段文本保持点号和大小写；会话、来源和字段共同构成不可变身份。

```python
class SourceRef
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`session_id`|str|是|无|输入所属会话，跨会话同名来源不相等。|
|`source_name`|str|是|无|会话内来源名。|
|`field`|str|是|无|内存原字段；不是semantic_id或Python属性路径。|

源码：[`src/chronaxis/core/models.py:243`](../../../src/chronaxis/core/models.py#L243)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SourceRef-__post_init__"></a>
### `SourceRef.__post_init__`

验证可追溯身份，不解析字段为表达式。

```python
SourceRef.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无额外参数；读取三个定位字段。

#### 返回说明

None；冻结完整来源身份。

#### 异常说明

TypeError/ValueError为名称/字段缺失或非法。

返回类型：None。

源码：[`src/chronaxis/core/models.py:253`](../../../src/chronaxis/core/models.py#L253)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SignalSample"></a>
## `SignalSample`

保留观测原值、显式有效性、质量原因及完整内存来源身份。

基础策略禁止全部非零质量位；有效0合法，None/NaN不能伪装有效。
invalid必须有原因但可保留原值；定义dtype另显式校验，不推断绑定。

```python
class SignalSample
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|计划内简单别名，尚不证明绑定已完成。|
|`time_ns`|int|是|无|当前分析坐标；来源映射/会话归属另显式检查。|
|`value`|int &#124; float &#124; bool &#124; str &#124; None|是|无|保留原逻辑标量，不自动补0。|
|`valid`|bool|是|无|明确基础质量有效性，不接受0/1代替bool。|
|`quality`|[QualityFlag](chronaxis.core.types.md#api-QualityFlag)|是|无|可以组合的原因，NONE不替代valid。|
|`source_ref`|[SourceRef](chronaxis.core.models.md#api-SourceRef)|是|无|带有明确类型的会话/来源/字段，不复用跨会话绑定。|
|`sequence`|int|是|无|来源内稳定原序号。|
|`code`|'ScalarValue &#124; None'|否|None|仅请求枚举原码时保留独立类型与质量。|

源码：[`src/chronaxis/core/models.py:269`](../../../src/chronaxis/core/models.py#L269)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SignalSample-__post_init__"></a>
### `SignalSample.__post_init__`

拒绝类型/质量自相矛盾的样本，保留非法观测的诊断值。

```python
SignalSample.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无额外参数；valid/quality/source_ref须用明确类型。

#### 返回说明

None；时间/序号规范为整数，其他事实冻结保留。

#### 异常说明

TypeError为结构/标量类型；ValueError为有效性矛盾；TimeOverflowError为坐标超界。

本函数直接报告的具体错误：

- `TypeError`：sample需要bool valid、QualityFlag及SourceRef。
- `ValueError`：valid=True与禁止质量、None或非有限值矛盾。
- `ValueError`：invalid样本必须保留非零质量原因。

#### 副作用说明

不更改原值/质量，不推断缺失为0，不运行绑定或数值变换。

返回类型：None。

源码：[`src/chronaxis/core/models.py:285`](../../../src/chronaxis/core/models.py#L285)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SignalSample-validate_dtype"></a>
### `SignalSample.validate_dtype`

在已声明定义类型下验证有效值，不执行隐式归一化。

```python
SignalSample.validate_dtype(dtype: SignalDType, choices: tuple[str, ...]=()) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`dtype`|[SignalDType](chronaxis.core.types.md#api-SignalDType)|是|无|位置或关键字。dtype为SignalDType|
|`choices`|tuple[str, ...]|否|()|位置或关键字。choices仅ENUM使用，非空唯一原标签tuple。|

#### 返回说明

None；invalid占位不参与dtype数值校验，但声明域仍须合法。

#### 异常说明

TypeError为类型不符；ValueError为枚举域/标签；OverflowError为整数范围超界。

本函数直接报告的具体错误：

- `TypeError`：dtype必须为SignalDType，choices必须为tuple。
- `ValueError`：enum需要非空choices。
- `ValueError`：choices标签重复。
- `ValueError`：仅enum可声明choices。
- `ValueError`：value不在声明枚举域。

#### 副作用说明

不转换原值、不推断dtype，也不修改质量；数值失败的质量标志由数值层产生。

返回类型：None。

源码：[`src/chronaxis/core/models.py:318`](../../../src/chronaxis/core/models.py#L318)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SessionSpec"></a>
## `SessionSpec`

保存一个会话的分析范围和来源集合。

sources必须为tuple，来源名在本会话内唯一，声明顺序保留。连续范围左闭右开，
实际点查询可包含末端。不同来源可以有不同origin；身份检查不能替代联合计算的
同步检查。本模型不可变，不保存执行缓存或跨任务状态。

```python
class SessionSpec
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`session_id`|str|是|无|明确会话边界身份。|
|`timebase`|[TimebaseSpec](chronaxis.core.models.md#api-TimebaseSpec)|是|无|会话分析坐标声明。|
|`domain_start_ns`|int|是|无|连续开始包含。|
|`domain_end_ns`|int|是|无|连续末端不含，真实点上下文包含。|
|`sources`|tuple[[SourceSpec](chronaxis.core.models.md#api-SourceSpec), ...]|否|()|会话内来源名唯一；空会话描述合法。|

源码：[`src/chronaxis/core/models.py:372`](../../../src/chronaxis/core/models.py#L372)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SessionSpec-__post_init__"></a>
### `SessionSpec.__post_init__`

校验会话范围、带有明确类型的来源和唯一名称。

```python
SessionSpec.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无额外参数；读取session_id、timebase、domain和sources。

#### 返回说明

None；规范边界为整数，保留来源原顺序。

#### 异常说明

TypeError为结构；ValueError为名称/重复来源/反向；TimeOverflowError为边界/跨度。

本函数直接报告的具体错误：

- `TypeError`：session需要TimebaseSpec及tuple sources。
- `TypeError`：sources元素必须为SourceSpec。

返回类型：None。

源码：[`src/chronaxis/core/models.py:386`](../../../src/chronaxis/core/models.py#L386)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SessionSpec-validate_sample"></a>
### `SessionSpec.validate_sample`

检查样本会话/来源/字段和观测范围，不执行绑定或读取。

```python
SessionSpec.validate_sample(sample: SignalSample) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`sample`|[SignalSample](chronaxis.core.models.md#api-SignalSample)|是|无|位置或关键字。sample为带有明确类型的 SignalSample，时间为分析坐标|

#### 返回说明

None；归属/点范围匹配才通过，不证明值与某行/定义已绑定。

#### 异常说明

TypeError为非样本；ValueError为身份、字段或范围不符。

本函数直接报告的具体错误：

- `TypeError`：sample必须为SignalSample。
- `ValueError`：sample的session_id与当前会话不一致。
- `ValueError`：sample来源未在当前会话声明。
- `ValueError`：sample原字段在当前memory来源不存在。
- `ValueError`：sample时间超出会话点范围。
- `ValueError`：sample早于来源观测开始。
- `ValueError`：sample晚于来源观测结束。

返回类型：None。

源码：[`src/chronaxis/core/models.py:420`](../../../src/chronaxis/core/models.py#L420)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-DatasetSpec"></a>
## `DatasetSpec`

保存一个分析对象、一个会话及其数据集身份。

dataset_id和entity_id分别标明输入集合与试验对象，session必须为SessionSpec。
模型不可变，不把多个实体或会话接成同一条时间轴，也不会创建运行状态。
批量独立计划需由另外的执行能力处理。

```python
class DatasetSpec
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`dataset_id`|str|是|无|当前输入数据集ID。|
|`entity_id`|str|是|无|试验对象身份，不写死车辆或电池领域。|
|`session`|[SessionSpec](chronaxis.core.models.md#api-SessionSpec)|是|无|首版单会话，来源在会话中明确声明。|

源码：[`src/chronaxis/core/models.py:460`](../../../src/chronaxis/core/models.py#L460)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-DatasetSpec-__post_init__"></a>
### `DatasetSpec.__post_init__`

检查首版数据集身份与单会话类型。

```python
DatasetSpec.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无额外参数；dataset_id/entity_id为简单标识，session为SessionSpec。

#### 返回说明

None；保留冻结会话描述，不创建运行状态。

#### 异常说明

TypeError/ValueError为身份或会话类型错误。

本函数直接报告的具体错误：

- `TypeError`：dataset首版需要一个SessionSpec。

返回类型：None。

源码：[`src/chronaxis/core/models.py:472`](../../../src/chronaxis/core/models.py#L472)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
