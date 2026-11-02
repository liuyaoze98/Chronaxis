# chronaxis.core.decoded_binding

把读取到的信号对应回分析计划。输入包含计划中的信号定义，以及实际读取的字段、样本数量、结束状态和内容摘要；输出供表达式执行使用的DecodedBindings。调用方必须先核实读取记录，单独填写一个合法的摘要字符串并不代表文件已经读过。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[DeclarationBindings](chronaxis.core.declarations.md#api-DeclarationBindings)、[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)

## 对象导航

|对象|用途|
|---|---|
|[`_require_sha256`](#api-_require_sha256)|只校验固定SHA-256文本格式，不声称摘要来自已核实文件。|
|[`DecodedSourceEvidence`](#api-DecodedSourceEvidence)|保存工厂已核对的一份来源历史事实，字段冻结且不保存逐条样本。|
|[`DecodedSourceEvidence.__post_init__`](#api-DecodedSourceEvidence-__post_init__)|检查固定身份、摘要格式、全源计数、投影和精确观测端点。|
|[`DecodedBindings`](#api-DecodedBindings)|冻结当前声明与实际解码历史证据，供编译和两个数值context入口使用。|
|[`DecodedBindings.__post_init__`](#api-DecodedBindings-__post_init__)|检查来源/会话/投影归属，再生成与完整实际证据关联的身份。|
|[`DecodedBindings.signals`](#api-DecodedBindings-signals)|读取当前冻结信号声明，不创建原始行或数值历史。|
|[`DecodedBindings.projected_signals`](#api-DecodedBindings-projected_signals)|按原声明顺序返回实际历史投影中的定义，不把未读取声明当作运行状态。|
|[`DecodedBindings.derived_names`](#api-DecodedBindings-derived_names)|读取当前统一名称空间中的派生别名。|
|[`DecodedBindings.resolve`](#api-DecodedBindings-resolve)|按当前声明查找原信号定义，不推断字段或执行数值转换。|
|[`DecodedBindings.require_synchronized`](#api-DecodedBindings-require_synchronized)|先检查用到的信号都已读取，再核对这些信号的时间基准或明确提供的同步依据。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass, field
from hashlib import sha256
from .binding import SignalDefinition, _identity
from .declarations import DeclarationBindings
from .validation import require_identifier
from ..timebase.conversion import require_int64_ns
```

</details>

<a id="api-_require_sha256"></a>
## `_require_sha256`

只校验固定SHA-256文本格式，不声称摘要来自已核实文件。

```python
_require_sha256(value: str, name: str) -> None
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|str|是|无|位置或关键字。value为64位小写十六进制文本|
|`name`|str|是|无|位置或关键字。name为错误定位字段。|

### 返回说明

None；无数据读取或字符串归一化。

### 异常说明

TypeError为非原生str；ValueError为长度或字符不符。

返回类型：None。

源码：[`src/chronaxis/core/decoded_binding.py:21`](../../../src/chronaxis/core/decoded_binding.py#L21)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-DecodedSourceEvidence"></a>
## `DecodedSourceEvidence`

保存工厂已核对的一份来源历史事实，字段冻结且不保存逐条样本。

三份摘要分别关联实际描述、请求和规范历史，不以文件名代替数据身份。
counts记录全源重放总量，projected_aliases保存实际请求投影顺序。
观测端点允许未知且保持None；EOF只接受整个来源结束，不能冒充批次结束。
模型仅验证证据结构，实际文件、字段、计数和摘要由执行层工厂负责核实。

```python
class DecodedSourceEvidence
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|str|是|无|当前声明中的唯一来源名。|
|`session_id`|str|是|无|当前实际重放所属会话。|
|`description_sha256`|str|是|无|实际来源描述及完整转换契约摘要。|
|`request_sha256`|str|是|无|本次读取范围、投影和批次声明摘要。|
|`history_sha256`|str|是|无|已核实规范历史字节摘要，不冒充原始日志摘要。|
|`sample_count`|int|是|无|全源实际样本总数，非负原生整数。|
|`progress_count`|int|是|无|全源实际批次进度记录数，至少包含最终EOF。|
|`projected_aliases`|tuple[str, ...]|是|无|实际读取的唯一简单别名，空投影合法。|
|`observation_start_ns`|int &#124; None|是|无|原描述中的已知会话坐标首端；未知不补0。|
|`observation_end_ns`|int &#124; None|是|无|最终EOF中的已知会话坐标终点；未知不补周期。|
|`source_eof`|bool|是|无|必须为True，表示整个配置来源已完成。|

源码：[`src/chronaxis/core/decoded_binding.py:37`](../../../src/chronaxis/core/decoded_binding.py#L37)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-DecodedSourceEvidence-__post_init__"></a>
### `DecodedSourceEvidence.__post_init__`

检查固定身份、摘要格式、全源计数、投影和精确观测端点。

```python
DecodedSourceEvidence.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无，读取创建后不可修改的字段；时间单位均为整数纳秒。

#### 返回说明

None；合法整数端点规范为原生int，None保持未知。

#### 异常说明

TypeError/ValueError为结构或事实矛盾；时间溢出发生异常时直接交给调用者处理。

本函数直接报告的具体错误：

- `ValueError`：decoded.sample_count需要非负原生int。
- `ValueError`：decoded.progress_count需要至少为1的原生int。
- `TypeError`：decoded.projected_aliases需要tuple。
- `ValueError`：decoded.projected_aliases不能重复。
- `ValueError`：decoded来源观测终点早于起点。
- `ValueError`：decoded证据需要真正whole-source EOF=True。

#### 副作用说明

仅在构造期规范本对象端点，不访问来源或验证文件内容。

返回类型：None。

源码：[`src/chronaxis/core/decoded_binding.py:58`](../../../src/chronaxis/core/decoded_binding.py#L58)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-DecodedBindings"></a>
## `DecodedBindings`

冻结当前声明与实际解码历史证据，供编译和两个数值context入口使用。

sources必须与声明来源一一对应，投影只能包含该来源声明的原信号别名。
identity使用decoded-binding-v1前缀与完整证据，不能与声明或memory身份混用。
resolve仅委托冻结声明；执行前仍检查实际投影和已有同步政策。
本对象不保存SourceSpec.rows，也不能交给材料化完整内存历史的快捷入口。

```python
class DecodedBindings
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`declarations`|[DeclarationBindings](chronaxis.core.declarations.md#api-DeclarationBindings)|是|无|原配置关系与同步依据；其身份仍只是声明证明。|
|`sources`|tuple[[DecodedSourceEvidence](chronaxis.core.decoded_binding.md#api-DecodedSourceEvidence), ...]|是|无|已核对来源事实，保留工厂的固定顺序。|
|`identity`|str|不填写|构造时计算|声明加实际证据的独立SHA-256运行身份。|

源码：[`src/chronaxis/core/decoded_binding.py:100`](../../../src/chronaxis/core/decoded_binding.py#L100)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-DecodedBindings-__post_init__"></a>
### `DecodedBindings.__post_init__`

检查来源/会话/投影归属，再生成与完整实际证据关联的身份。

```python
DecodedBindings.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无，读取declarations与sources；所有容器必须冻结。

#### 返回说明

None；构造identity，不重新读取历史或改变声明。

#### 异常说明

TypeError/ValueError为模型、重复/缺少来源、会话或投影冲突。

本函数直接报告的具体错误：

- `TypeError`：解码绑定需要DeclarationBindings和DecodedSourceEvidence tuple。
- `ValueError`：解码证据来源必须唯一且与声明完全对应。
- `ValueError`：解码证据会话与当前声明不一致。
- `ValueError`：解码投影包含其他来源或未声明别名。

返回类型：None。

源码：[`src/chronaxis/core/decoded_binding.py:113`](../../../src/chronaxis/core/decoded_binding.py#L113)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-DecodedBindings-signals"></a>
### `DecodedBindings.signals`

读取当前冻结信号声明，不创建原始行或数值历史。

```python
DecodedBindings.signals: tuple[SignalDefinition, ...]
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

SignalDefinition tuple。

#### 异常说明

无；属性不能重新赋值。

返回类型：tuple[[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition), ...]。

源码：[`src/chronaxis/core/decoded_binding.py:142`](../../../src/chronaxis/core/decoded_binding.py#L142)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-DecodedBindings-projected_signals"></a>
### `DecodedBindings.projected_signals`

按原声明顺序返回实际历史投影中的定义，不把未读取声明当作运行状态。

```python
DecodedBindings.projected_signals: tuple[SignalDefinition, ...]
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无，使用当前已校验sources中的projected_aliases。

#### 返回说明

原SignalDefinition对象组成的tuple；signals仍保留完整声明。

#### 异常说明

分配或取消错误原样传播。调用执行层须先为有限索引和tuple预付费用。
不读取历史、不改变绑定身份，也不把不同来源的投影误判为同步依据。

返回类型：tuple[[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition), ...]。

源码：[`src/chronaxis/core/decoded_binding.py:150`](../../../src/chronaxis/core/decoded_binding.py#L150)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-DecodedBindings-derived_names"></a>
### `DecodedBindings.derived_names`

读取当前统一名称空间中的派生别名。

```python
DecodedBindings.derived_names: tuple[str, ...]
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

str tuple。

#### 异常说明

无；不把派生名称当实际读入列。

返回类型：tuple[str, ...]。

源码：[`src/chronaxis/core/decoded_binding.py:166`](../../../src/chronaxis/core/decoded_binding.py#L166)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-DecodedBindings-resolve"></a>
### `DecodedBindings.resolve`

按当前声明查找原信号定义，不推断字段或执行数值转换。

```python
DecodedBindings.resolve(name: str) -> SignalDefinition
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|位置或关键字。name为安全简单别名。|

#### 返回说明

当前SignalDefinition。

#### 异常说明

ValueError为非法或未声明名称；查找本身不证明该别名已投影。

返回类型：[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)。

源码：[`src/chronaxis/core/decoded_binding.py:173`](../../../src/chronaxis/core/decoded_binding.py#L173)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-DecodedBindings-require_synchronized"></a>
### `DecodedBindings.require_synchronized`

先检查用到的信号都已读取，再核对这些信号的时间基准或明确提供的同步依据。

```python
DecodedBindings.require_synchronized(names: tuple[str, ...]) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`names`|tuple[str, ...]|是|无|位置或关键字。names为展开后的原信号依赖tuple|

#### 返回说明

None；不修改投影、偏移或同步声明。

#### 异常说明

TypeError为错误容器；ValueError为未知/未投影依赖或同步缺项。

本函数直接报告的具体错误：

- `TypeError`：解码联合依赖names必须为tuple。

返回类型：None。

源码：[`src/chronaxis/core/decoded_binding.py:181`](../../../src/chronaxis/core/decoded_binding.py#L181)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
