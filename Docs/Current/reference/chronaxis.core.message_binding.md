# `chronaxis.core.message_binding`

为当前消息表达式声明参数，并把独立消息仓事实关联为运行绑定。

ExpressionParameter将显式单位的配置数值规范成精确FLOAT64。MessageDeclarations
引用当前DeclarationBindings中选定来源的原SignalDefinition，不复制或虚构信号、
普通历史或TTL；当前policy只使用本条消息原字典，不继承上一条值。
MessageSourceEvidence只检查显式来源标签、全仓摘要、条数和首末的结构；
MessageBindings将其与完整声明身份关联。真正封存文件的EOF/SHA/条数验证由
执行层bind_message_store负责，单独构造证据不证明来源文件已经读取。

本模块只保存创建后不可修改的配置与有限事实，不读文件、不执行表达式、不加载NumPy或
CAN，也不证明仓来自同一次CAN捕获或DBC单位已核实。这些关联留给实际生产端。
身份使用新版本前缀与固定字段的长度前缀增量SHA，不改变普通绑定的身份协议。
模型及调用者保留的配置由调用者拥有；执行工厂另付其新运行元数据费用。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[DeclarationBindings](chronaxis.core.declarations.md#api-DeclarationBindings)、[SignalDType](chronaxis.core.types.md#api-SignalDType)、[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)

## 对象导航

|对象|用途|
|---|---|
|[`_hash_parts`](#api-_hash_parts)|按固定模型字段顺序增量编码文本身份，失败不保活新增整段编码副本。|
|[`ExpressionParameter`](#api-ExpressionParameter)|保存一个有明确单位、不可被对方重赋单位的FLOAT64配置参数。|
|[`ExpressionParameter.__post_init__`](#api-ExpressionParameter-__post_init__)|验证参数名称、精确数值及单位，不执行来源或表达式。|
|[`ExpressionParameter.dtype`](#api-ExpressionParameter-dtype)|读取固定数值类型；|
|[`MessageDeclarations`](#api-MessageDeclarations)|为一个选定来源建立独立的当前消息名称空间，不制造运行证明。|
|[`MessageDeclarations.__post_init__`](#api-MessageDeclarations-__post_init__)|核对来源、完整名称空间与policy，生成静态消息声明身份。|
|[`MessageDeclarations.extensions`](#api-MessageDeclarations-extensions)|读取宿主注册。|
|[`MessageDeclarations.lookups`](#api-MessageDeclarations-lookups)|读取普通声明中的标定表。|
|[`MessageDeclarations.signals`](#api-MessageDeclarations-signals)|选择同一原定义对象；|
|[`MessageDeclarations.resolve`](#api-MessageDeclarations-resolve)|只定位本来源原信号，参数名称另由编译器处理。|
|[`MessageDeclarations.require_synchronized`](#api-MessageDeclarations-require_synchronized)|检查实际依赖均在本来源，不借其他来源的同步声明引入缓存值。|
|[`MessageSourceEvidence`](#api-MessageSourceEvidence)|保存独立解码消息仓的有限事实，仅校结构而不声明真实回读已发生。|
|[`MessageSourceEvidence.__post_init__`](#api-MessageSourceEvidence-__post_init__)|验证有限证据一致性，单独构造不能替代实际EOF校验。|
|[`MessageBindings`](#api-MessageBindings)|关联消息声明与实际仓证据，保持独立于普通DecodedBindings的运行身份。|
|[`MessageBindings.__post_init__`](#api-MessageBindings-__post_init__)|核对声明与证据来源/会话，增量生成有限运行身份。|
|[`MessageBindings.extensions`](#api-MessageBindings-extensions)|读取宿主注册。|
|[`MessageBindings.lookups`](#api-MessageBindings-lookups)|读取消息声明中的标定表。|
|[`MessageBindings.signals`](#api-MessageBindings-signals)|读取同一原信号定义；|
|[`MessageBindings.parameters`](#api-MessageBindings-parameters)|读取创建后不可修改的配置参数；|
|[`MessageBindings.derived_names`](#api-MessageBindings-derived_names)|读取显式局部派生名；|
|[`MessageBindings.resolve`](#api-MessageBindings-resolve)|按单来源原定义定位信号，不从证据标签生成字段。|
|[`MessageBindings.require_synchronized`](#api-MessageBindings-require_synchronized)|执行前复核全部依赖属于本来源，不执行普通TTL或时钟合并。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass, field
from hashlib import sha256
from math import isfinite
from .binding import SignalDefinition
from .declarations import DeclarationBindings
from .unit_conversion import binding_version, require_config_version
from .unit_registry import REGISTRY_VERSION, resolve_unit
from .types import SignalDType
from .validation import require_identifier, require_text
from ..timebase.conversion import require_int64_ns
```

</details>

<a id="api-_hash_parts"></a>
## `_hash_parts`

按固定模型字段顺序增量编码文本身份，失败不保活新增整段编码副本。

```python
_hash_parts(parts: tuple[str, ...]) -> str
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`parts`|tuple[str, ...]|是|无|位置或关键字。parts为本模块已检查的原生文本tuple，首项含独立版本前缀。|

### 返回说明

小写SHA-256文本；每段UTF-8字节有长度前缀，分隔符不能造成碰撞。

### 异常说明

原Unicode、内存或取消错误；不调用外部repr或保存全量canonical文本。

本函数直接报告的具体错误：

- `TypeError`：消息身份只编码已检查的原生文本。

返回类型：str。

源码：[`src/chronaxis/core/message_binding.py:30`](../../../src/chronaxis/core/message_binding.py#L30)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ExpressionParameter"></a>
## `ExpressionParameter`

保存一个有明确单位、不可被对方重赋单位的FLOAT64配置参数。

只接受原生有限int/float；int须能精确转为有限float，不能静默舍入。
该参数不是信号或裸数字literal，不产生来源依赖和时间保持状态。

```python
class ExpressionParameter
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|表达式使用的安全简单名称。|
|`value`|int &#124; float|是|无|构造后规范为有限原生float。|
|`unit`|str|是|无|明确单位标签；不按对方信号自动改写。|
|`config_version`|int|否|4|参数与绑定同版本，默认使用当前规则。|
|`unit_status`|str|不填写|构造时计算|`"verified"`表示单位及换算关系已通过程序的单位表检查；`"unverified"`表示使用未登记的单位文字，程序未验证其物理换算关系。|

源码：[`src/chronaxis/core/message_binding.py:56`](../../../src/chronaxis/core/message_binding.py#L56)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ExpressionParameter-__post_init__"></a>
### `ExpressionParameter.__post_init__`

验证参数名称、精确数值及单位，不执行来源或表达式。

```python
ExpressionParameter.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无，读取name/value/unit。

#### 返回说明

None，value规范成FLOAT64可精确表示的原生float。

#### 异常说明

TypeError为非原生数值；ValueError为非有限、有损整数或声明非法。

本函数直接报告的具体错误：

- `TypeError`：表达式参数名称和单位需要原生str。
- `TypeError`：表达式参数只接受原生int/float，不能为bool。
- `ValueError`：表达式参数必须能精确表示为有限FLOAT64。
- `ValueError`：表达式参数不能表示为有限FLOAT64。

返回类型：None。

源码：[`src/chronaxis/core/message_binding.py:69`](../../../src/chronaxis/core/message_binding.py#L69)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ExpressionParameter-dtype"></a>
### `ExpressionParameter.dtype`

读取固定数值类型；

```python
ExpressionParameter.dtype: SignalDType
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无；

#### 返回说明

FLOAT64；

#### 异常说明

无。

返回类型：[SignalDType](chronaxis.core.types.md#api-SignalDType)。

源码：[`src/chronaxis/core/message_binding.py:96`](../../../src/chronaxis/core/message_binding.py#L96)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-MessageDeclarations"></a>
## `MessageDeclarations`

为一个选定来源建立独立的当前消息名称空间，不制造运行证明。

signals引用原声明中的同一SignalDefinition对象。原定义的转换声明保留，
其TTL不在本模型执行；依赖仅能来自selected source。parameters及局部
derived_names不能覆盖原计划任何signal/derived，也不能互相覆盖。

```python
class MessageDeclarations
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`declarations`|[DeclarationBindings](chronaxis.core.declarations.md#api-DeclarationBindings)|是|无|完整原配置声明及身份，非实际文件证明。|
|`source`|str|是|无|当前消息表达式所属的来源别名；参与公式的信号均须来自该来源，避免将其他消息的旧值混入。|
|`parameters`|tuple[[ExpressionParameter](chronaxis.core.message_binding.md#api-ExpressionParameter), ...]|否|()|有明确单位的配置参数。|
|`derived_names`|tuple[str, ...]|否|()|当前指标显式登记的局部派生名。|
|`message_policy`|str|否|'current_message-v1'|填`"current_message-v1"`：每次求值只取当前报文中的值，缺值就记录跳过原因，不借用前一条消息或另一条报文的值。|
|`config_version`|int &#124; None|否|None|继承原声明，参数必须同版。|
|`identity`|str|不填写|构造时计算|完整原配置与消息配置的独立声明SHA。|

源码：[`src/chronaxis/core/message_binding.py:102`](../../../src/chronaxis/core/message_binding.py#L102)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-MessageDeclarations-__post_init__"></a>
### `MessageDeclarations.__post_init__`

核对来源、完整名称空间与policy，生成静态消息声明身份。

```python
MessageDeclarations.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无，读取创建后不可修改的字段，不读取文件或DBC。

#### 返回说明

None；保原定义对象，不将声明身份当真实仓EOF证明。

#### 异常说明

TypeError为模型/容器错误；ValueError为来源、名称或policy冲突。

本函数直接报告的具体错误：

- `TypeError`：消息声明需要DeclarationBindings。
- `TypeError`：消息来源需要原生str。
- `ValueError`：消息来源不在原声明中。
- `TypeError`：消息参数与局部派生名称需要带有明确类型的 tuple。
- `ValueError`：消息policy仅支持current_message-v1。
- `TypeError`：消息局部派生名称需要原生str。

返回类型：None。

源码：[`src/chronaxis/core/message_binding.py:118`](../../../src/chronaxis/core/message_binding.py#L118)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-MessageDeclarations-extensions"></a>
### `MessageDeclarations.extensions`

读取宿主注册。

```python
MessageDeclarations.extensions
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

冻结注册或None。

#### 异常说明

无。

源码：[`src/chronaxis/core/message_binding.py:172`](../../../src/chronaxis/core/message_binding.py#L172)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-MessageDeclarations-lookups"></a>
### `MessageDeclarations.lookups`

读取普通声明中的标定表。

```python
MessageDeclarations.lookups
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

冻结tuple。

#### 异常说明

无。

源码：[`src/chronaxis/core/message_binding.py:177`](../../../src/chronaxis/core/message_binding.py#L177)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-MessageDeclarations-signals"></a>
### `MessageDeclarations.signals`

选择同一原定义对象；

```python
MessageDeclarations.signals: tuple[SignalDefinition, ...]
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无；

#### 返回说明

tuple；

#### 异常说明

无主动异常。

返回类型：tuple[[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition), ...]。

源码：[`src/chronaxis/core/message_binding.py:182`](../../../src/chronaxis/core/message_binding.py#L182)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-MessageDeclarations-resolve"></a>
### `MessageDeclarations.resolve`

只定位本来源原信号，参数名称另由编译器处理。

```python
MessageDeclarations.resolve(name: str) -> SignalDefinition
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|位置或关键字。name为安全简单信号别名。|

#### 返回说明

原SignalDefinition对象。

#### 异常说明

ValueError为未知、其他来源或非法名称；不从点号猜测原字段。

返回类型：[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)。

源码：[`src/chronaxis/core/message_binding.py:186`](../../../src/chronaxis/core/message_binding.py#L186)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-MessageDeclarations-require_synchronized"></a>
### `MessageDeclarations.require_synchronized`

检查实际依赖均在本来源，不借其他来源的同步声明引入缓存值。

```python
MessageDeclarations.require_synchronized(names: tuple[str, ...]) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`names`|tuple[str, ...]|是|无|位置或关键字。names为展开后的原信号依赖tuple，空依赖合法。|

#### 返回说明

None；单源当前字典不需要合并其他来源时钟。

#### 异常说明

TypeError为容器错误；ValueError为非本来源或未知依赖。

本函数直接报告的具体错误：

- `TypeError`：消息依赖names需要tuple。

返回类型：None。

源码：[`src/chronaxis/core/message_binding.py:198`](../../../src/chronaxis/core/message_binding.py#L198)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-MessageSourceEvidence"></a>
## `MessageSourceEvidence`

保存独立解码消息仓的有限事实，仅校结构而不声明真实回读已发生。

decoder_profile/read_identity是仓内显式标签，不认证旧CAN来源。原序SHA
包含记录和值/映射时间；首末可相同，空仓必须两端None且条数为0。

```python
class MessageSourceEvidence
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|str|是|无|本消息来源。|
|`session_id`|str|是|无|原声明会话。|
|`decoder_profile`|str|是|无|显式解码来源标签，不冒充计算policy。|
|`read_identity`|str|是|无|仓的显式读取标识，CAN同次关联由生产端另核。|
|`store_sha256`|str|是|无|已封口全消息行流摘要。|
|`record_count`|int|是|无|全decoded条数，不是普通历史样本数。|
|`first_time_ns`|int &#124; None|是|无|全仓首条映射坐标，空仓为None。|
|`last_time_ns`|int &#124; None|是|无|全仓最后坐标，不补采样周期。|

源码：[`src/chronaxis/core/message_binding.py:212`](../../../src/chronaxis/core/message_binding.py#L212)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-MessageSourceEvidence-__post_init__"></a>
### `MessageSourceEvidence.__post_init__`

验证有限证据一致性，单独构造不能替代实际EOF校验。

```python
MessageSourceEvidence.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无，读取创建后不可修改的字段。

#### 返回说明

None，已知时间规范成原生int。

#### 异常说明

TypeError/ValueError为类型、SHA、条数或首末矛盾；时间超界原样传播。

本函数直接报告的具体错误：

- `TypeError`：消息证据来源、会话及读取标签需要原生str。
- `TypeError`：消息仓摘要需要原生str。
- `ValueError`：消息仓摘要需要64位小写十六进制SHA-256。
- `ValueError`：消息条数需要非负原生int。
- `ValueError`：非空消息仓必须有真实首末时间。
- `ValueError`：消息仓终点早于起点。
- `ValueError`：空消息仓首末必须为None。

返回类型：None。

源码：[`src/chronaxis/core/message_binding.py:228`](../../../src/chronaxis/core/message_binding.py#L228)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-MessageBindings"></a>
## `MessageBindings`

关联消息声明与实际仓证据，保持独立于普通DecodedBindings的运行身份。

证据实际性由bind_message_store完整回读负责；本模型只校结构/归属。
不证明普通历史、TTL、DBC字段单位或同次CAN捕获，也不保存逐条记录。

```python
class MessageBindings
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`declarations`|[MessageDeclarations](chronaxis.core.message_binding.md#api-MessageDeclarations)|是|无|单源消息配置及完整原声明身份。|
|`evidence`|[MessageSourceEvidence](chronaxis.core.message_binding.md#api-MessageSourceEvidence)|是|无|执行工厂核实后的仓事实，非手造即证明。|
|`config_version`|int &#124; None|否|None|继承消息声明，不允许运行时切换。|
|`identity`|str|不填写|构造时计算|独立message-binding-v1身份。|

源码：[`src/chronaxis/core/message_binding.py:264`](../../../src/chronaxis/core/message_binding.py#L264)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-MessageBindings-__post_init__"></a>
### `MessageBindings.__post_init__`

核对声明与证据来源/会话，增量生成有限运行身份。

```python
MessageBindings.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无，读取declarations/evidence。

#### 返回说明

None，不再次打开消息仓。

#### 异常说明

TypeError为模型错误；ValueError为来源/会话不符；编码或取消原错传播。

本函数直接报告的具体错误：

- `TypeError`：消息运行绑定需要MessageDeclarations和MessageSourceEvidence。
- `ValueError`：消息仓证据的来源或会话与当前声明不符。

返回类型：None。

源码：[`src/chronaxis/core/message_binding.py:276`](../../../src/chronaxis/core/message_binding.py#L276)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-MessageBindings-extensions"></a>
### `MessageBindings.extensions`

读取宿主注册。

```python
MessageBindings.extensions
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

冻结注册或None。

#### 异常说明

无。

源码：[`src/chronaxis/core/message_binding.py:307`](../../../src/chronaxis/core/message_binding.py#L307)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-MessageBindings-lookups"></a>
### `MessageBindings.lookups`

读取消息声明中的标定表。

```python
MessageBindings.lookups
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

冻结tuple。

#### 异常说明

无。

源码：[`src/chronaxis/core/message_binding.py:312`](../../../src/chronaxis/core/message_binding.py#L312)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-MessageBindings-signals"></a>
### `MessageBindings.signals`

读取同一原信号定义；

```python
MessageBindings.signals: tuple[SignalDefinition, ...]
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无；

#### 返回说明

tuple；

#### 异常说明

无主动异常。

返回类型：tuple[[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition), ...]。

源码：[`src/chronaxis/core/message_binding.py:317`](../../../src/chronaxis/core/message_binding.py#L317)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-MessageBindings-parameters"></a>
### `MessageBindings.parameters`

读取创建后不可修改的配置参数；

```python
MessageBindings.parameters: tuple[ExpressionParameter, ...]
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无；

#### 返回说明

tuple；

#### 异常说明

无。

返回类型：tuple[[ExpressionParameter](chronaxis.core.message_binding.md#api-ExpressionParameter), ...]。

源码：[`src/chronaxis/core/message_binding.py:322`](../../../src/chronaxis/core/message_binding.py#L322)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-MessageBindings-derived_names"></a>
### `MessageBindings.derived_names`

读取显式局部派生名；

```python
MessageBindings.derived_names: tuple[str, ...]
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无；

#### 返回说明

tuple；

#### 异常说明

无。

返回类型：tuple[str, ...]。

源码：[`src/chronaxis/core/message_binding.py:327`](../../../src/chronaxis/core/message_binding.py#L327)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-MessageBindings-resolve"></a>
### `MessageBindings.resolve`

按单来源原定义定位信号，不从证据标签生成字段。

```python
MessageBindings.resolve(name: str) -> SignalDefinition
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|位置或关键字。name为安全别名。|

#### 返回说明

原SignalDefinition。

#### 异常说明

ValueError为非法、未知或其他来源名称。

返回类型：[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)。

源码：[`src/chronaxis/core/message_binding.py:331`](../../../src/chronaxis/core/message_binding.py#L331)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-MessageBindings-require_synchronized"></a>
### `MessageBindings.require_synchronized`

执行前复核全部依赖属于本来源，不执行普通TTL或时钟合并。

```python
MessageBindings.require_synchronized(names: tuple[str, ...]) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`names`|tuple[str, ...]|是|无|位置或关键字。names为原信号依赖tuple。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError为容器或非本来源依赖。

返回类型：None。

源码：[`src/chronaxis/core/message_binding.py:339`](../../../src/chronaxis/core/message_binding.py#L339)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
