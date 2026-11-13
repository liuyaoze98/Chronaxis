# `chronaxis.core.binding`

把分析中使用的名称对应到实际信号。例如把current对应到来源pack的电流字段，随后表达式就可以使用current。模块检查名称冲突、字段是否存在、单位转换和多个来源的时间关系，再生成SignalBindings。绑定标识还包含输入内容及转换设置，用来识别两次计算是否使用了相同输入。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ExtensionRegistry](chronaxis.extensions.md#api-ExtensionRegistry)、[LookupTablePlan](chronaxis.core.lookup.md#api-LookupTablePlan)、[SessionSpec](chronaxis.core.models.md#api-SessionSpec)、[SignalDType](chronaxis.core.types.md#api-SignalDType)、[SourceRef](chronaxis.core.models.md#api-SourceRef)、[SourceSpec](chronaxis.core.models.md#api-SourceSpec)、[TimeType](chronaxis.core.types.md#api-TimeType)、[TimebaseSpec](chronaxis.core.models.md#api-TimebaseSpec)

## 对象导航

|对象|用途|
|---|---|
|[`_identity`](#api-_identity)|把已知不可变元数据编码为带类型的确定身份文本。|
|[`_source_identity`](#api-_source_identity)|保存内存来源定位、时间映射、观测域和实际行内容的身份。|
|[`SignalDefinition`](#api-SignalDefinition)|给一个原始字段建立分析用的名字，并声明数值类型、单位、有效期和转换方式。例如把来源table的Voltage列命名为u，再在表达式中写u*i。方向和测量位置等标签供预设检查含义；只填写标签不会自动改变数值。|
|[`SignalDefinition.__post_init__`](#api-SignalDefinition-__post_init__)|校验完整声明并冻结默认输入单位及精确有效期。|
|[`SignalDefinition.identity`](#api-SignalDefinition-identity)|返回声明字段完整身份，供执行计划缓存和追溯使用。|
|[`SignalDefinition.unit_conversion_promoted`](#api-SignalDefinition-unit_conversion_promoted)|说明浮点类型是否由已知整数输入的单位换算引起。|
|[`SynchronizationEvidence`](#api-SynchronizationEvidence)|保存来源使用固定时间偏移进入公共分析时基的核实说明。|
|[`SynchronizationEvidence.__post_init__`](#api-SynchronizationEvidence-__post_init__)|校验显式来源和时基证据结构。|
|[`SignalBindings`](#api-SignalBindings)|检查并冻结一个会话的信号定义、实际来源和同步证据。|
|[`SignalBindings.__post_init__`](#api-SignalBindings-__post_init__)|检查统一名称空间、来源定位和同步证据，再构建身份。|
|[`SignalBindings.resolve`](#api-SignalBindings-resolve)|解析当前计划真实信号别名，不自动寻找semantic候选。|
|[`SignalBindings.source_ref`](#api-SignalBindings-source_ref)|给出当前会话下解析后的完整memory字段引用。|
|[`SignalBindings.require_synchronized`](#api-SignalBindings-require_synchronized)|在联合依赖执行前检查实际来源的公共分析基准。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass, field as dataclass_field
from hashlib import sha256
from .models import SessionSpec, SourceRef, SourceSpec, TimebaseSpec
from .types import BASE_FORBIDDEN_QUALITY, SignalDType, TimeType
from .units import require_number
from .unit_conversion import binding_version, converted_dtype, require_config_version, validate_conversion_v4
from .unit_registry import REGISTRY_VERSION
from .lookup import LookupTablePlan, validate_lookups
from .validation import require_identifier, require_scalar, require_text
from ..timebase.conversion import require_int64_ns
```

</details>

<a id="api-_identity"></a>
## `_identity`

把已知不可变元数据编码为带类型的确定身份文本。

```python
_identity(value) -> str
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|object|是|无|位置或关键字。信号身份计算中的原生标量或嵌套元组；NaN和无穷值会作为原始诊断值编码，不当作正常测量值。|

### 返回说明

str；保留bool/int区别及浮点位值，tuple用长度前缀防歧义。

### 异常说明

TypeError为内部未声明结构；不读取文件或执行任意对象repr。

本函数直接报告的具体错误：

- `TypeError`：绑定身份含未声明结构。

返回类型：str。

源码：[`src/chronaxis/core/binding.py:26`](../../../src/chronaxis/core/binding.py#L26)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_source_identity"></a>
## `_source_identity`

保存内存来源定位、时间映射、观测域和实际行内容的身份。

```python
_source_identity(source: SourceSpec) -> str
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|[SourceSpec](chronaxis.core.models.md#api-SourceSpec)|是|无|位置或关键字。source为已校验SourceSpec|

### 返回说明

SHA256文本；不同原内容不会只因同名来源而复用绑定。

### 异常说明

TypeError为内部结构错误；无文件或旧reader副作用。

返回类型：str。

源码：[`src/chronaxis/core/binding.py:63`](../../../src/chronaxis/core/binding.py#L63)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SignalDefinition"></a>
## `SignalDefinition`

给一个原始字段建立分析用的名字，并声明数值类型、单位、有效期和转换方式。例如把来源table的Voltage列命名为u，再在表达式中写u*i。方向和测量位置等标签供预设检查含义；只填写标签不会自动改变数值。

```python
class SignalDefinition
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|表达式中使用的信号名称，如 `"current"`。|
|`source`|str|是|无|sources中某一项的name，例如 `"table"`。|
|`field`|str|是|无|memory原字段，不替换点号。|
|`dtype`|[SignalDType](chronaxis.core.types.md#api-SignalDType)|是|无|SignalDType枚举成员：INT64是有符号64位整数，UINT64是无符号64位整数，FLOAT64是双精度浮点，BOOL是真/假，ENUM是预先声明的状态标签。这里传枚举成员，不传字符串；当前运算支持哪些类型仍见本对象的约束。|
|`unit`|str|是|无|转换后的单位。例如 `"A"` 为安培，`"1"` 表示无单位。|
|`valid_for_ns`|int &#124; None|是|无|正int64纳秒有效期；CAN声明阶段None表示尚未解析默认有效期。需要沿用历史样本的计算在使用前取本信号period的3倍，否则取DBC报文周期的3倍；仅使用当前报文值的计算无需解析未使用的有效期。到期按实际时间判断。|
|`input_unit`|str &#124; None|否|None|原数据的单位；原值为毫安时填 `"mA"`。null也表示沿用unit。 None表示沿用unit。|
|`scale`|int &#124; float|否|1|原值乘以多少。例如毫安转安培填0.001，程序不会因为填了A而自动补倍率。|
|`offset`|int &#124; float|否|0|乘完scale后再加的数；换算公式是原值×scale＋offset。已登记单位之间的转换要求offset为0。|
|`choices`|tuple[tuple[int &#124; bool &#124; str, str &#124; bool], ...]|否|()|不可修改的(raw_value, label)二元组序列。enum把原始代码映射为非空字符串标签；bool把原始代码映射为True/False。原值可为int、bool、str，类型不同的1、True、"1"不会混为一项；数值信号不使用choices。|
|`valid_range`|tuple[int &#124; float, int &#124; float] &#124; None|否|None|转换后数值的有效范围，如 `[-100,100]`，包含两个端点。最小值写在前面；bool和enum不使用此字段。 None表示不增加数值范围限制；Python中使用二元tuple，例如(-100, 100)。|
|`invalid_values`|tuple[int &#124; float &#124; bool &#124; str &#124; None, ...]|否|()|原数据中代表无效的值，如 `[65535,-999]`。在单位转换前检查；匹配时区分数字1、布尔true和字符串"1"。|
|`sample_policy`|str|否|'backward_hold'|填`"backward_hold"`：两次更新之间沿用前一次仍有效的值，达到valid_for_ns后失效；没有线性插值或无限期保持选项。|
|`same_time_policy`|str|否|'error'|`"error"`：同一时刻的多个有效值冲突时，把该点视为无法确定，不任选一个值；`"last_by_sequence"`：按来源序号选择最后一条记录。|
|`semantic_id`|str &#124; None|否|None|可选的含义标签，如 `"battery.current"`，供预设寻找信号；表达式仍写name，不写这个点号名称。|
|`semantic_contract_version`|str &#124; None|否|None|该含义标签采用的约定版本，如 `"1"`。填写它时也须填写semantic_id。填了版本号不等于单位和方向已经符合预设要求。 None表示未声明语义约定版本。|
|`mapping_version`|str &#124; None|否|None|你为这套字段映射起的版本号，如 `"vehicle_a_v2"`，方便追查两次配置是否相同；不触发任何自动转换。 None表示未记录映射版本。|
|`sign_convention`|str &#124; None|否|None|记录数值正负的含义。充电预设要求 `"positive_is_charge"`，即正电流表示充电；填写这句话不会反转数据。 None表示未声明正负方向，依赖方向的预设因此可能无法匹配。|
|`measurement_location`|str &#124; None|否|None|测量位置。充电预设要求 `"pack_terminal"`，即电池包端；普通分析可以使用自己的明确位置文字。 None表示未声明测量位置，要求该位置的预设因此可能无法匹配。|
|`input_sign_convention`|str &#124; None|否|None|转换前方向证据，core 带有明确类型的元数据。 None表示没有提供转换前的方向说明。|
|`direction_factor`|int|否|1|方向不变1，显式反转-1。|
|`config_version`|int|否|dataclass_field(default=4, kw_only=True)|规则版本；低层系数已确定，不按省略推导。|
|`input_dtype`|[SignalDType](chronaxis.core.types.md#api-SignalDType) &#124; None|否|dataclass_field(default=None, kw_only=True)|配置推导前类型；不新增用户字段。|
|`code_dtype`|[SignalDType](chronaxis.core.types.md#api-SignalDType) &#124; None|否|dataclass_field(default=None, kw_only=True)|仅 v4 枚举的原始整数类型。|
|`capture_code`|bool|否|dataclass_field(default=False, kw_only=True, compare=False, repr=False)|当前执行投影要求。|
|`unit_status`|str|不填写|构造时计算|`"verified"`表示单位及换算关系已通过程序的单位表检查；`"unverified"`表示使用未登记的单位文字，程序未验证其物理换算关系。|

源码：[`src/chronaxis/core/binding.py:81`](../../../src/chronaxis/core/binding.py#L81)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SignalDefinition-__post_init__"></a>
### `SignalDefinition.__post_init__`

校验完整声明并冻结默认输入单位及精确有效期。

```python
SignalDefinition.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无额外参数；valid_for_ns为正int64纳秒，或尚待DBC周期的None。

#### 返回说明

None；unit_status为verified/unverified，未修改输入值。

#### 异常说明

TypeError为字段结构；ValueError为缺项/策略/映射/转换冲突；
    TimeOverflowError为有效期超界。数值样本失败由数值层生成质量原因。

返回类型：None。

源码：[`src/chronaxis/core/binding.py:120`](../../../src/chronaxis/core/binding.py#L120)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SignalDefinition-identity"></a>
### `SignalDefinition.identity`

返回声明字段完整身份，供执行计划缓存和追溯使用。

```python
SignalDefinition.identity() -> tuple
```

参数：无显式参数。


#### 参数说明

无；读取当前冻结声明。

#### 返回说明

tuple；含实际定位、转换、有效期、质量及语义/版本元数据。

#### 异常说明

无主动异常；不使用全局缓存或当前样本值。

返回类型：tuple。

源码：[`src/chronaxis/core/binding.py:275`](../../../src/chronaxis/core/binding.py#L275)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SignalDefinition-unit_conversion_promoted"></a>
### `SignalDefinition.unit_conversion_promoted`

说明浮点类型是否由已知整数输入的单位换算引起。

```python
SignalDefinition.unit_conversion_promoted: bool
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

仅有整数输入证据且实际提升时为True。

#### 异常说明

无；不依据样本数值猜类型。

返回类型：bool。

源码：[`src/chronaxis/core/binding.py:297`](../../../src/chronaxis/core/binding.py#L297)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SynchronizationEvidence"></a>
## `SynchronizationEvidence`

保存来源使用固定时间偏移进入公共分析时基的核实说明。

source指定会话内来源，analysis_timebase指定目标时基，evidence保留调用者
提供的依据。本模型检查声明结构，不检查物理设备、不估计漂移或改动偏移。
来源缺少同步依据时仍可独立分析；参与联合计算时须满足同步检查。

```python
class SynchronizationEvidence
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|str|是|无|明确会话内来源。|
|`analysis_timebase`|[TimebaseSpec](chronaxis.core.models.md#api-TimebaseSpec)|是|无|offset映射后的公共分析基准。|
|`evidence`|str|是|无|调用者声明的核实依据，不自动生成业务事实。|

源码：[`src/chronaxis/core/binding.py:311`](../../../src/chronaxis/core/binding.py#L311)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SynchronizationEvidence-__post_init__"></a>
### `SynchronizationEvidence.__post_init__`

校验显式来源和时基证据结构。

```python
SynchronizationEvidence.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无；读取source、analysis_timebase及evidence。

#### 返回说明

None；不更改来源或推断时间映射。

#### 异常说明

TypeError/ValueError为无效声明。

本函数直接报告的具体错误：

- `TypeError`：analysis_timebase必须为TimebaseSpec。

返回类型：None。

源码：[`src/chronaxis/core/binding.py:323`](../../../src/chronaxis/core/binding.py#L323)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SignalBindings"></a>
## `SignalBindings`

检查并冻结一个会话的信号定义、实际来源和同步证据。

signals与derived_names共用简单名称空间，每个原字段必须出现在本会话内存行中。
identity包含实际内容、时基、转换和策略，来源同名也不能替代完整身份。
本对象没有全局注册表，不继承其他任务绑定；值更新由状态执行器读取创建后不可修改的输入对象，
不会修改本对象。

```python
class SignalBindings
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`session`|[SessionSpec](chronaxis.core.models.md#api-SessionSpec)|是|无|当前计划单会话来源上下文。|
|`signals`|tuple[[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition), ...]|是|无|已声明原字段到别名的关联。|
|`derived_names`|tuple[str, ...]|否|()|实际派生定义由表达式层提供，此处只检查名称冲突。|
|`synchronization`|tuple[[SynchronizationEvidence](chronaxis.core.binding.md#api-SynchronizationEvidence), ...]|否|()|明示固定offset依据。|
|`config_version`|int &#124; None|否|dataclass_field(default=None, kw_only=True)|缺省继承定义；空绑定默认4。|
|`extensions`|[ExtensionRegistry](chronaxis.extensions.md#api-ExtensionRegistry) &#124; None|否|dataclass_field(default=None, kw_only=True, repr=False)|宿主交给信号绑定的不可变注册表，运行表达式时用它核对函数身份。|
|`lookups`|tuple[[LookupTablePlan](chronaxis.core.lookup.md#api-LookupTablePlan), ...]|否|dataclass_field(default=(), kw_only=True)|数值标定表声明。|
|`identity`|str|不填写|构造时计算|实际校验所得完整绑定SHA。|

源码：[`src/chronaxis/core/binding.py:341`](../../../src/chronaxis/core/binding.py#L341)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SignalBindings-__post_init__"></a>
### `SignalBindings.__post_init__`

检查统一名称空间、来源定位和同步证据，再构建身份。

```python
SignalBindings.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无；session/signals及可选derived_names/synchronization均为已校验且不可变的模型输入。

#### 返回说明

None；通过后所有字段保持不可变。

#### 异常说明

TypeError为结构；ValueError为名称、来源字段或证据冲突。

本函数直接报告的具体错误：

- `TypeError`：绑定需要SessionSpec及tuple声明。
- `TypeError`：signals必须包含SignalDefinition。
- `TypeError`：synchronization需要SynchronizationEvidence。
- `ValueError`：同步证据来源不存在或重复。
- `ValueError`：同步证据目标与会话分析时基不一致。

返回类型：None。

源码：[`src/chronaxis/core/binding.py:359`](../../../src/chronaxis/core/binding.py#L359)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SignalBindings-resolve"></a>
### `SignalBindings.resolve`

解析当前计划真实信号别名，不自动寻找semantic候选。

```python
SignalBindings.resolve(name: str) -> SignalDefinition
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|位置或关键字。name为简单别名|

#### 返回说明

对应冻结SignalDefinition。

#### 异常说明

ValueError为非法或未知别名；不访问Python对象属性。

返回类型：[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)。

源码：[`src/chronaxis/core/binding.py:449`](../../../src/chronaxis/core/binding.py#L449)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SignalBindings-source_ref"></a>
### `SignalBindings.source_ref`

给出当前会话下解析后的完整memory字段引用。

```python
SignalBindings.source_ref(name: str) -> SourceRef
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|位置或关键字。name为已定义信号别名。|

#### 返回说明

SourceRef；含当前session_id、source_name和原field。

#### 异常说明

ValueError为未定义或非法别名。

返回类型：[SourceRef](chronaxis.core.models.md#api-SourceRef)。

源码：[`src/chronaxis/core/binding.py:467`](../../../src/chronaxis/core/binding.py#L467)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SignalBindings-require_synchronized"></a>
### `SignalBindings.require_synchronized`

在联合依赖执行前检查实际来源的公共分析基准。

```python
SignalBindings.require_synchronized(names: tuple[str, ...]) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`names`|tuple[str, ...]|是|无|位置或关键字。names为参与同一表达式/指标的原信号别名tuple|

#### 返回说明

None；公共起点或显式固定offset依据齐全时通过。

#### 异常说明

TypeError为容器；ValueError为未知别名或同步缺项。

本函数直接报告的具体错误：

- `TypeError`：联合依赖names必须为tuple。

返回类型：None。

源码：[`src/chronaxis/core/binding.py:479`](../../../src/chronaxis/core/binding.py#L479)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
