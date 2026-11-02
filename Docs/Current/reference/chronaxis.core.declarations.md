# chronaxis.core.declarations

在读取数据之前检查来源、信号和派生名称声明，生成不可变的声明绑定。

输入为来源定位、时基、请求范围、信号定义和同步证据；输出DeclarationBindings
及其SHA-256身份。函数只检查配置关系，不证明文件、DBC字段或实际观测存在，
也不创建虚拟样本。静态表达式检查可使用这些声明；实际解释器仍需包含内存数据
的SignalBindings。本模块只依赖标准库和核心模型，没有文件操作、样本计算、
全局注册或执行计划缓存。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Interval](chronaxis.core.models.md#api-Interval)、[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)、[SynchronizationEvidence](chronaxis.core.binding.md#api-SynchronizationEvidence)、[TimeType](chronaxis.core.types.md#api-TimeType)、[TimebaseSpec](chronaxis.core.models.md#api-TimebaseSpec)

## 对象导航

|对象|用途|
|---|---|
|[`DeclaredSource`](#api-DeclaredSource)|保存一个尚未读取的来源定位，以及其声明的固定时间映射。|
|[`DeclaredSource.__post_init__`](#api-DeclaredSource-__post_init__)|校验声明结构，保持声明身份与实际内容证据保持分开。|
|[`DeclarationBindings`](#api-DeclarationBindings)|冻结一个计划的来源、信号名称和同步关系，供执行前检查使用。|
|[`DeclarationBindings.__post_init__`](#api-DeclarationBindings-__post_init__)|检查名称、来源和显式同步关系，并生成声明身份。|
|[`DeclarationBindings.resolve`](#api-DeclarationBindings-resolve)|定位当前声明中的唯一信号别名。|
|[`DeclarationBindings.require_synchronized`](#api-DeclarationBindings-require_synchronized)|按实际联合依赖检查声明的公共时间基准。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass, field
from hashlib import sha256
from .binding import SignalDefinition, SynchronizationEvidence, _identity
from .models import Interval, TimebaseSpec
from .types import TimeType
from .validation import require_identifier, require_text
from ..timebase.conversion import require_int64_ns
```

</details>

<a id="api-DeclaredSource"></a>
## `DeclaredSource`

保存一个尚未读取的来源定位，以及其声明的固定时间映射。

input_identity包含规范配置中的路径顺序、格式和处理配置标识，不是文件内容
哈希。offset_ns是整数纳秒偏移；模型不会估计漂移。字段实际存在性由来源执行
接口另行检查，不能凭声明认定数据已读取。全部字段不可变。

```python
class DeclaredSource
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|当前计划来源名。|
|`timebase`|[TimebaseSpec](chronaxis.core.models.md#api-TimebaseSpec)|是|无|原始来源坐标。|
|`input_identity`|str|是|无|规范声明身份，与实际数据身份分别保存。|
|`offset_ns`|int|否|0|显式固定偏移，不自动估计漂移。|

源码：[`src/chronaxis/core/declarations.py:23`](../../../src/chronaxis/core/declarations.py#L23)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-DeclaredSource-__post_init__"></a>
### `DeclaredSource.__post_init__`

校验声明结构，保持声明身份与实际内容证据保持分开。

```python
DeclaredSource.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无；读取name/timebase/input_identity/offset_ns。

#### 返回说明

None，冻结声明。

#### 异常说明

TypeError/ValueError/TimeOverflowError为配置错误。

本函数直接报告的具体错误：

- `TypeError`：声明来源需要TimebaseSpec。

返回类型：None。

源码：[`src/chronaxis/core/declarations.py:36`](../../../src/chronaxis/core/declarations.py#L36)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-DeclarationBindings"></a>
## `DeclarationBindings`

冻结一个计划的来源、信号名称和同步关系，供执行前检查使用。

signals与derived_names共用名称空间。identity只证明配置声明；来源路径、
处理配置、转换或有效期变化会改变它。模型不验证文件内容、实际列或DBC
元数据，不能代替执行数据绑定。同步检查只针对当前节点实际使用的来源。

```python
class DeclarationBindings
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`session_id`|str|是|无|当前会话声明。|
|`timebase`|[TimebaseSpec](chronaxis.core.models.md#api-TimebaseSpec)|是|无|计划分析坐标。|
|`domain`|[Interval](chronaxis.core.models.md#api-Interval) &#124; None|是|无|用户请求范围；None声明整文件无时间筛选，不表示无观测。|
|`sources`|tuple[[DeclaredSource](chronaxis.core.declarations.md#api-DeclaredSource), ...]|是|无|保留声明原顺序。|
|`signals`|tuple[[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition), ...]|是|无|已校验单信号契约。|
|`derived_names`|tuple[str, ...]|否|()|signals统一名称空间。|
|`synchronization`|tuple[[SynchronizationEvidence](chronaxis.core.binding.md#api-SynchronizationEvidence), ...]|否|()|显式核实依据。|
|`identity`|str|不填写|构造时计算|配置身份，不是执行绑定SHA。|

源码：[`src/chronaxis/core/declarations.py:56`](../../../src/chronaxis/core/declarations.py#L56)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-DeclarationBindings-__post_init__"></a>
### `DeclarationBindings.__post_init__`

检查名称、来源和显式同步关系，并生成声明身份。

```python
DeclarationBindings.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无；输入均为已经校验的不可变声明模型。

#### 返回说明

None；不读取任何样本、文件或DBC。

#### 异常说明

TypeError/ValueError为结构错误、名称冲突、来源错误或同步关系冲突。

本函数直接报告的具体错误：

- `TypeError`：声明绑定需要带有明确类型的时基/范围与tuple容器。
- `TypeError`：声明绑定需要DeclaredSource/SignalDefinition。
- `ValueError`：source.name重复。
- `TypeError`：同步需要SynchronizationEvidence。
- `ValueError`：同步来源重复/未知或目标时基不一致。

返回类型：None。

源码：[`src/chronaxis/core/declarations.py:73`](../../../src/chronaxis/core/declarations.py#L73)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-DeclarationBindings-resolve"></a>
### `DeclarationBindings.resolve`

定位当前声明中的唯一信号别名。

```python
DeclarationBindings.resolve(name: str) -> SignalDefinition
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|位置或关键字。name简单别名。|

#### 返回说明

当前计划SignalDefinition。

#### 异常说明

ValueError为名称非法或未知。

返回类型：[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)。

源码：[`src/chronaxis/core/declarations.py:144`](../../../src/chronaxis/core/declarations.py#L144)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-DeclarationBindings-require_synchronized"></a>
### `DeclarationBindings.require_synchronized`

按实际联合依赖检查声明的公共时间基准。

```python
DeclarationBindings.require_synchronized(names: tuple[str, ...]) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`names`|tuple[str, ...]|是|无|位置或关键字。names为原信号简单别名tuple。|

#### 返回说明

None，单来源或公共起点/显式同步依据齐备时通过。

#### 异常说明

TypeError/ValueError为容器、别名或同步缺项。

本函数直接报告的具体错误：

- `TypeError`：联合依赖names必须为tuple。

返回类型：None。

源码：[`src/chronaxis/core/declarations.py:162`](../../../src/chronaxis/core/declarations.py#L162)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
