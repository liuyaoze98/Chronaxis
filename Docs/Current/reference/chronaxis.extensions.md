# `chronaxis.extensions`

由宿主Python程序显式声明可信扩展，纯配置只引用其已注册名称。

逐点函数声明固定输入输出端口；样本归约与网格变换分别使用具有生命周期
的工厂。注册表冻结名称、版本、类型、单位和后端能力，以稳定摘要标识协议。
本模块不发现模块、不读取配置中的文件或导入路径，也不在注册时创建运行状态。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)

## 对象导航

|对象|用途|
|---|---|
|[`ValueSpec`](#api-ValueSpec)|一个固定类型与数值尺度的端口。BOOL使用单位1，枚举代码需在DSL中显式取出。|
|[`ValueSpec.__post_init__`](#api-ValueSpec-__post_init__)|核对宿主声明的类型与尺度。|
|[`_BackendSpec`](#api-_BackendSpec)|三类协议共享名称/版本与显式能力验证，不共享数值或状态回调。|
|[`_BackendSpec.require_backend`](#api-_BackendSpec-require_backend)|取得请求后端自身的实现。|
|[`_BackendSpec._check`](#api-_BackendSpec-_check)|校验名称、版本、端口与声明的具体后端。|
|[`FunctionSpec`](#api-FunctionSpec)|纯逐点函数，impl(args,resources)返回同一形状的ScalarValue或NumericArray。|
|[`FunctionSpec.__post_init__`](#api-FunctionSpec-__post_init__)||
|[`ReductionSpec`](#api-ReductionSpec)|标量样本归约协议；factory(resources)建立每范围独立的状态。|
|[`ReductionSpec.__post_init__`](#api-ReductionSpec-__post_init__)||
|[`TransformSpec`](#api-TransformSpec)|有状态网格变换；factory(resources)为本次会话创建状态。|
|[`TransformSpec.__post_init__`](#api-TransformSpec-__post_init__)||
|[`ExtensionRegistry`](#api-ExtensionRegistry)|不可变的宿主能力集合；同次运行必须提供与编译时相同的注册对象。|
|[`ExtensionRegistry.__init__`](#api-ExtensionRegistry-__init__)|登记三种互斥的带有明确类型的描述。|
|[`using_extension_budget`](#api-using_extension_budget)|让当前调用栈的逐点扩展使用实际运行账本，嵌套及异常后恢复原上下文。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from hashlib import sha256
from types import MappingProxyType
from .core.types import SignalDType as D
from .core.unit_registry import resolve_unit
from .core.validation import require_identifier, require_text
from .core.function_contracts import builtin_function_specs
```

</details>

<a id="api-ValueSpec"></a>
## `ValueSpec`

一个固定类型与数值尺度的端口。BOOL使用单位1，枚举代码需在DSL中显式取出。

```python
class ValueSpec
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`dtype`|SignalDType|是|无|固定端口的数值或BOOL逻辑类型；枚举应先通过enum_code取得代码。|
|`unit`|str|是|无|端口读取或返回的已登记单位；BOOL端口必须使用单位1。|

源码：[`src/chronaxis/extensions.py:33`](../../../src/chronaxis/extensions.py#L33)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ValueSpec-__post_init__"></a>
### `ValueSpec.__post_init__`

核对宿主声明的类型与尺度。

```python
ValueSpec.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

ValueError为非法端口。

源码：[`src/chronaxis/extensions.py:39`](../../../src/chronaxis/extensions.py#L39)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_BackendSpec"></a>
## `_BackendSpec`

三类协议共享名称/版本与显式能力验证，不共享数值或状态回调。

```python
class _BackendSpec
```


源码：[`src/chronaxis/extensions.py:47`](../../../src/chronaxis/extensions.py#L47)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_BackendSpec-require_backend"></a>
### `_BackendSpec.require_backend`

取得请求后端自身的实现。

```python
_BackendSpec.require_backend(backend)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`backend`|str|是|无|位置或关键字。所选执行后端名称，只能为声明了实现的reference或numpy。|

#### 返回说明

回调。

#### 异常说明

缺实现报ValueError。

源码：[`src/chronaxis/extensions.py:50`](../../../src/chronaxis/extensions.py#L50)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_BackendSpec-_check"></a>
### `_BackendSpec._check`

校验名称、版本、端口与声明的具体后端。

```python
_BackendSpec._check(inputs)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`inputs`|tuple[[ValueSpec](chronaxis.extensions.md#api-ValueSpec), ...]|是|无|位置或关键字。当前协议的固定输入端口序列，一并检查输出端口及可调用实现。|

#### 返回说明

None。

#### 异常说明

非法描述报错。

源码：[`src/chronaxis/extensions.py:59`](../../../src/chronaxis/extensions.py#L59)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-FunctionSpec"></a>
## `FunctionSpec`

纯逐点函数，impl(args,resources)返回同一形状的ScalarValue或NumericArray。

固定位置参数逐一按端口单位及dtype编译，任何必要输入无效都传递到结果；
无历史，真实输入更新沿用普通表达式政策。

```python
FunctionSpec(name: str, version: str, inputs: tuple[chronaxis.extensions.ValueSpec, ...], output: chronaxis.extensions.ValueSpec, reference: object = None, numpy: object = None) -> None
```

继承关系：[_BackendSpec](chronaxis.extensions.md#api-_BackendSpec)。下表列本类声明的字段；基类字段及其约束见对应类型链接。

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|配置DSL直接调用的唯一宿主函数名，不允许遮蔽内置能力。|
|`version`|str|是|无|宿主发布的实现版本文本；变更算法或兼容行为时应更新以隔离计划身份。|
|`inputs`|tuple[[ValueSpec](chronaxis.extensions.md#api-ValueSpec), ...]|是|无|从左到右的固定位置参数端口，决定数量、dtype及单位尺度。|
|`output`|[ValueSpec](chronaxis.extensions.md#api-ValueSpec)|是|无|函数返回值的固定dtype和单位；数组输出形状必须匹配所传行数。|
|`reference`|Callable[[tuple[ScalarValue, ...], ExtensionResources], ScalarValue] &#124; None|否|None|单点标量实现；缺失时不支持reference后端。|
|`numpy`|Callable[[tuple[NumericArray, ...], ExtensionResources], NumericArray] &#124; None|否|None|对整批有效行运行的数组实现；缺失时不支持numpy后端。|

源码：[`src/chronaxis/extensions.py:73`](../../../src/chronaxis/extensions.py#L73)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-FunctionSpec-__post_init__"></a>
### `FunctionSpec.__post_init__`



```python
FunctionSpec.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

声明或实现不合法时拒绝注册。

源码：[`src/chronaxis/extensions.py:86`](../../../src/chronaxis/extensions.py#L86)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ReductionSpec"></a>
## `ReductionSpec`

标量样本归约协议；factory(resources)建立每范围独立的状态。

consume接收已选真实样本，finalize返回ScalarValue，close退还外部资源；
mergeable=True时还必须提供merge(other)。cancel和close均为必需方法，分别处理取消及资源释放。

```python
ReductionSpec(name: str, version: str, input: chronaxis.extensions.ValueSpec, output: chronaxis.extensions.ValueSpec, reference: object = None, numpy: object = None, state_bytes: int = 0, mergeable: bool = False) -> None
```

继承关系：[_BackendSpec](chronaxis.extensions.md#api-_BackendSpec)。下表列本类声明的字段；基类字段及其约束见对应类型链接。

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|配置calculations.operation可引用的宿主样本归约名称。|
|`version`|str|是|无|宿主发布的实现版本文本；变更算法或兼容行为时应更新以隔离计划身份。|
|`input`|[ValueSpec](chronaxis.extensions.md#api-ValueSpec)|是|无|归约所接收的已选有效样本的数值端口。|
|`output`|[ValueSpec](chronaxis.extensions.md#api-ValueSpec)|是|无|finalize返回标量的固定逻辑类型和自然单位。|
|`reference`|Callable[[ExtensionResources], Any] &#124; None|否|None|建立一个消费标量元组的状态，其协议包含consume、finalize、cancel和close，可按声明提供merge。|
|`numpy`|Callable[[ExtensionResources], Any] &#124; None|否|None|建立独立数组消费状态，输入为NumericArray；不借用参考实现作为隐式后备。|
|`state_bytes`|int|否|0|新建本范围或会话状态前要预付的固定字节数，动态空间另由资源视图申请。|
|`mergeable`|bool|否|False|是否允许在同一注册及后端下调用merge(other)合并两个未结束的状态。|

源码：[`src/chronaxis/extensions.py:92`](../../../src/chronaxis/extensions.py#L92)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ReductionSpec-__post_init__"></a>
### `ReductionSpec.__post_init__`



```python
ReductionSpec.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

资源/合并能力或端口不合规时拒绝。

源码：[`src/chronaxis/extensions.py:107`](../../../src/chronaxis/extensions.py#L107)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TransformSpec"></a>
## `TransformSpec`

有状态网格变换；factory(resources)为本次会话创建状态。

advance(time_ns,window_ns,values,weights_ns)仅接收本窗口有效的ZOH区间，
返回实际网格时刻的ScalarValue。history_ns限制回看窗口的实际或周期
计量宽度，interval_modes声明该实现能正确使用的时间权重。

```python
TransformSpec(name: str, version: str, input: chronaxis.extensions.ValueSpec, output: chronaxis.extensions.ValueSpec, reference: object = None, numpy: object = None, state_bytes: int = 0, history_ns: int = 0, interval_modes: tuple[str, ...] = ('actual', 'fixed', 'dbc')) -> None
```

继承关系：[_BackendSpec](chronaxis.extensions.md#api-_BackendSpec)。下表列本类声明的字段；基类字段及其约束见对应类型链接。

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|transforms.operation中显式引用的宿主网格算法名。|
|`version`|str|是|无|宿主发布的实现版本文本；变更算法或兼容行为时应更新以隔离计划身份。|
|`input`|[ValueSpec](chronaxis.extensions.md#api-ValueSpec)|是|无|网格窗口有效保持段的数值输入端口。|
|`output`|[ValueSpec](chronaxis.extensions.md#api-ValueSpec)|是|无|advance每次交付单个网格结果时使用的dtype与自然单位。|
|`reference`|Callable[[ExtensionResources], Any] &#124; None|否|None|创建参考状态；advance接收按实际时序排列的标量元组和正纳秒权重，并须支持cancel及close。|
|`numpy`|Callable[[ExtensionResources], Any] &#124; None|否|None|创建数组状态；advance接收一维有效数值列、等长权重列，并返回当前网格标量。|
|`state_bytes`|int|否|0|新建本范围或会话状态前要预付的固定字节数，动态空间另由资源视图申请。|
|`history_ns`|int|否|0|该宿主时序算法支持的最大回看宽度（选定口径的正纳秒数）。|
|`interval_modes`|tuple[str, ...]|否|('actual', 'fixed', 'dbc')|本实现能够解释的间隔模式集合，可含actual、fixed和dbc且不得重复。|

源码：[`src/chronaxis/extensions.py:117`](../../../src/chronaxis/extensions.py#L117)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TransformSpec-__post_init__"></a>
### `TransformSpec.__post_init__`



```python
TransformSpec.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

非数值端口、非正历史或非法资源费时拒绝。

源码：[`src/chronaxis/extensions.py:134`](../../../src/chronaxis/extensions.py#L134)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ExtensionRegistry"></a>
## `ExtensionRegistry`

不可变的宿主能力集合；同次运行必须提供与编译时相同的注册对象。

```python
ExtensionRegistry(functions=(), reductions=(), transforms=())
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`functions`|Mapping[str, [FunctionSpec](chronaxis.extensions.md#api-FunctionSpec)]|不直接填写|由自定义构造器建立；见 __init__|只读名称映射，按函数名查可供DSL编译的逐点协议。|
|`reductions`|Mapping[str, [ReductionSpec](chronaxis.extensions.md#api-ReductionSpec)]|不直接填写|由自定义构造器建立；见 __init__|只读名称映射，按计算操作查对应的样本归约工厂。|
|`transforms`|Mapping[str, [TransformSpec](chronaxis.extensions.md#api-TransformSpec)]|不直接填写|由自定义构造器建立；见 __init__|只读名称映射，按时序操作查网格状态和历史契约。|
|`identity`|str|不直接填写|由自定义构造器建立；见 __init__|对协议名称、版本、端口、后端及资源规则计算的稳定SHA-256摘要。|

源码：[`src/chronaxis/extensions.py:147`](../../../src/chronaxis/extensions.py#L147)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ExtensionRegistry-__init__"></a>
### `ExtensionRegistry.__init__`

登记三种互斥的带有明确类型的描述。

```python
ExtensionRegistry.__init__(functions=(), reductions=(), transforms=())
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`functions`|tuple[[FunctionSpec](chronaxis.extensions.md#api-FunctionSpec), ...]|否|()|位置或关键字。待注册的一组逐点函数，按声明检查唯一名称后冻结。|
|`reductions`|tuple[[ReductionSpec](chronaxis.extensions.md#api-ReductionSpec), ...]|否|()|位置或关键字。待注册的一组标量归约描述，不在注册阶段创建状态。|
|`transforms`|tuple[[TransformSpec](chronaxis.extensions.md#api-TransformSpec), ...]|否|()|位置或关键字。待注册的一组有状态时序描述，名称与其他两类保持互斥。|

#### 返回说明

新注册表。

#### 异常说明

重名或模型错误。

源码：[`src/chronaxis/extensions.py:154`](../../../src/chronaxis/extensions.py#L154)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-using_extension_budget"></a>
## `using_extension_budget`

让当前调用栈的逐点扩展使用实际运行账本，嵌套及异常后恢复原上下文。

```python
using_extension_budget(budget)
```

装饰器：`contextmanager`。

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|ResourceBudget|是|无|位置或关键字。当前实际执行任务的共用的资源用量记录；退出上下文时恢复调用者原来的预算关联。|

### 返回说明

上下文管理器。

### 异常说明

回调/执行发生异常时直接交给调用者处理。

源码：[`src/chronaxis/extensions.py:179`](../../../src/chronaxis/extensions.py#L179)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
