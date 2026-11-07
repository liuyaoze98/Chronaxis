# `chronaxis.core.numeric`

把已解码的单个值转换成声明类型，并提供独立的标量运算参考实现。

normalize_reference接收SignalDefinition、原生标量和上游质量原因，
只应用额外声明的scale、offset、枚举映射与有效范围，输出ScalarValue。
算术和比较接收ScalarValue，先检查类型与质量，再计算并检查结果范围。
value保存数值或原诊断；dtype说明类型；valid表示能否使用；quality记录原因。

整数先在Python精确整数域中运算，再检查int64或uint64的定宽边界。
需要float64时，先检查整数是否能被精确表示；无效输入不参与正常计算。
memory_series_reference从已有内存行生成信号历史，保留来源和纳秒时间。
本模块只依赖标准库与核心模型，不读取文件、加载DBC或调用NumPy数值内核。
数组实现可共享静态类型规则和模型检查，数值计算仍由各自实现承担。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[QualityFlag](chronaxis.core.types.md#api-QualityFlag)、[SignalBindings](chronaxis.core.binding.md#api-SignalBindings)、[SignalDType](chronaxis.core.types.md#api-SignalDType)、[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)、[SignalSample](chronaxis.core.models.md#api-SignalSample)、[SignalSeries](chronaxis.core.state.md#api-SignalSeries)

## 对象导航

|对象|用途|
|---|---|
|[`ScalarValue`](#api-ScalarValue)|保存一个值的声明类型、有效性和质量原因。|
|[`ScalarValue.__post_init__`](#api-ScalarValue-__post_init__)|检查值与声明类型是否一致，并核对有效性和质量原因。|
|[`result_dtype`](#api-result_dtype)|根据运算和两侧声明类型，确定允许的结果类型。|
|[`_exact_float`](#api-_exact_float)|参考路径用整数往返校验显式浮点转换。|
|[`to_float_reference`](#api-to_float_reference)|显式将数值结果转换float64，保留invalid和精度失败。|
|[`binary_reference`](#api-binary_reference)|对两个已检查的标量执行算术或比较，并保留质量原因。|
|[`unary_reference`](#api-unary_reference)|独立参考abs/negate，在整数域拒绝min翻转及unsigned下溢。|
|[`normalize_reference`](#api-normalize_reference)|按显式信号声明转换一个已解码值，并检查业务有效范围。|
|[`memory_series_reference`](#api-memory_series_reference)|从当前内存来源提取一个字段，转换后生成信号历史。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass, field
from math import isfinite
from operator import eq, ne, lt, le, gt, ge
from types import MappingProxyType
from .binding import SignalBindings, SignalDefinition
from .models import SignalSample
from .state import SignalSeries
from .types import QualityFlag, SignalDType
from .validation import require_scalar, require_text
from ..timebase.conversion import checked_add_ns
```

</details>

<a id="api-ScalarValue"></a>
## `ScalarValue`

保存一个值的声明类型、有效性和质量原因。

valid只能是bool，且当且仅当quality为NONE时为True。有质量问题的value
可保留原始诊断，例如None或NaN，但不能作为正常数值参加后续计算。
有效整数必须落在dtype对应的定宽范围内，有效float64必须有限。
枚举使用labels中的文本值；labels是不可变的固定标签域，比较时必须同域。
实例不可重新赋值，不持有跨时间或跨分析任务的状态。

```python
class ScalarValue
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; float &#124; bool &#124; str &#124; None|是|无|正常值或无效原诊断。|
|`dtype`|[SignalDType](chronaxis.core.types.md#api-SignalDType)|是|无|SignalDType枚举成员：INT64是有符号64位整数，UINT64是无符号64位整数，FLOAT64是双精度浮点，BOOL是真/假，ENUM是预先声明的状态标签。这里传枚举成员，不传字符串；当前运算支持哪些类型仍见本对象的约束。|
|`valid`|bool|否|True|无效不代表正常0。|
|`quality`|[QualityFlag](chronaxis.core.types.md#api-QualityFlag)|否|QualityFlag.NONE|输入原因和计算失败原因。|
|`labels`|tuple[str, ...]|否|()|仅enum有固定公开逻辑域。|
|`code`|'[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue) &#124; None'|否|None|仅 enum_code 需要的原整数，可与标签有不同有效性。|
|`partial`|bool|否|False|此值是否使用了可估算但覆盖不全的变换输入；有效数值可以同时携带这个标志。|

源码：[`src/chronaxis/core/numeric.py:48`](../../../src/chronaxis/core/numeric.py#L48)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ScalarValue-__post_init__"></a>
### `ScalarValue.__post_init__`

检查值与声明类型是否一致，并核对有效性和质量原因。

```python
ScalarValue.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无显式参数；读取value、dtype、valid、quality和labels。

#### 返回说明

None。保留输入声明，不自动转换类型、补零或清除质量原因。

#### 异常说明

TypeError: 字段类型或枚举标签域结构不合法。
    ValueError: 有效性与质量矛盾，浮点值非有限或枚举值不在声明域内。
    OverflowError: 有效整数超出声明类型的定宽范围。

返回类型：None。

源码：[`src/chronaxis/core/numeric.py:66`](../../../src/chronaxis/core/numeric.py#L66)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-result_dtype"></a>
## `result_dtype`

根据运算和两侧声明类型，确定允许的结果类型。

```python
result_dtype(operator: str, left: SignalDType, right: SignalDType, allow_float_literal: bool=False) -> SignalDType
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`operator`|str|是|无|位置或关键字。本入口支持`add`相加、`sub`相减、`mul`相乘、`div`相除，以及`eq`等于、`ne`不等于、`lt`小于、`le`小于或等于、`gt`大于、`ge`大于或等于。填写这些内部名称，不填写符号或任意函数名。|
|`left`|[SignalDType](chronaxis.core.types.md#api-SignalDType)|是|无|位置或关键字。左操作数的声明类型，用于判断两个操作数能否参与该运算。|
|`right`|[SignalDType](chronaxis.core.types.md#api-SignalDType)|是|无|位置或关键字。右操作数的声明类型，用于判断两个操作数能否参与该运算。|
|`allow_float_literal`|bool|否|False|位置或关键字。编译器已证明混合类型中的浮点侧是字面量时才为True。|

### 返回说明

SignalDType。比较返回BOOL；除法或允许的浮点算术返回FLOAT64。

### 异常说明

TypeError: 类型声明或字面量证明标志的类型不合法。
    ValueError: 运算未注册、逻辑类型不支持该运算，或混合类型未显式归一化。

### 边界说明

本函数只检查静态类型，不计算信号值。INT64与UINT64可精确比较；
    两种不同整数类型的信号不能直接混合算术。

返回类型：[SignalDType](chronaxis.core.types.md#api-SignalDType)。

源码：[`src/chronaxis/core/numeric.py:136`](../../../src/chronaxis/core/numeric.py#L136)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_exact_float"></a>
## `_exact_float`

参考路径用整数往返校验显式浮点转换。

```python
_exact_float(value: int | float) -> tuple[float | None, QualityFlag]
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; float|是|无|位置或关键字。value为原生整数或float|

### 返回说明

float值及NONE，或None及PRECISION_LOSS/NONFINITE。

### 异常说明

无主动异常；数值溢出转换为质量，不吞配置类型错误。

返回类型：tuple[float &#124; None, [QualityFlag](chronaxis.core.types.md#api-QualityFlag)]。

源码：[`src/chronaxis/core/numeric.py:184`](../../../src/chronaxis/core/numeric.py#L184)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-to_float_reference"></a>
## `to_float_reference`

显式将数值结果转换float64，保留invalid和精度失败。

```python
to_float_reference(value: ScalarValue) -> ScalarValue
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)|是|无|位置或关键字。value为int64/uint64/float64 ScalarValue。|

### 返回说明

ScalarValue float64，无法精确表示时invalid/PRECISION_LOSS。

### 异常说明

TypeError/ValueError为结构或逻辑dtype。

本函数直接报告的具体错误：

- `TypeError`：float转换需要数值ScalarValue。

返回类型：[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)。

源码：[`src/chronaxis/core/numeric.py:210`](../../../src/chronaxis/core/numeric.py#L210)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-binary_reference"></a>
## `binary_reference`

对两个已检查的标量执行算术或比较，并保留质量原因。

```python
binary_reference(operator: str, left: ScalarValue, right: ScalarValue, *, allow_float_literal: bool=False) -> ScalarValue
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`operator`|str|是|无|位置或关键字。本入口支持`add`相加、`sub`相减、`mul`相乘、`div`相除，以及`eq`等于、`ne`不等于、`lt`小于、`le`小于或等于、`gt`大于、`ge`大于或等于。填写这些内部名称，不填写符号或任意函数名。|
|`left`|[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)|是|无|位置或关键字。左侧参与运算的ScalarValue，包含一个值、类型及有效性。|
|`right`|[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)|是|无|位置或关键字。右侧参与运算的ScalarValue，包含一个值、类型及有效性。|
|`allow_float_literal`|bool|否|False|仅关键字。由编译器证明浮点字面量可以参与混合类型运算。|

### 返回说明

ScalarValue。输入无效时传播两侧原因；整数超界、除零、非有限结果
    或浮点转换丢精度时返回无效结果，不以零或舍入值替代。

### 异常说明

TypeError、ValueError: 输入模型、运算类型或枚举比较域不符合要求。

本函数直接报告的具体错误：

- `TypeError`：二元运算需要ScalarValue。
- `ValueError`：enum比较域不一致。

### 流程说明

先检查静态类型，即使输入无效也不跳过配置错误。正常整数在Python
    精确整数域中计算，再检查目标定宽范围；浮点路径先检查转换精度。

返回类型：[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)。

源码：[`src/chronaxis/core/numeric.py:231`](../../../src/chronaxis/core/numeric.py#L231)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-unary_reference"></a>
## `unary_reference`

独立参考abs/negate，在整数域拒绝min翻转及unsigned下溢。

```python
unary_reference(operator: str, value: ScalarValue) -> ScalarValue
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`operator`|str|是|无|位置或关键字。选择一种单值运算：`abs`取绝对值；`neg`取相反数。逻辑取反由表达式模块处理，不传到这里。|
|`value`|[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)|是|无|位置或关键字。value为数值ScalarValue。|

### 返回说明

同dtype ScalarValue，超界为OVERFLOW，invalid原因保留。

### 异常说明

TypeError/ValueError为输入或未支持逻辑/运算。

本函数直接报告的具体错误：

- `ValueError`：unary仅支持数值abs/neg。

返回类型：[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)。

源码：[`src/chronaxis/core/numeric.py:304`](../../../src/chronaxis/core/numeric.py#L304)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-normalize_reference"></a>
## `normalize_reference`

按显式信号声明转换一个已解码值，并检查业务有效范围。

```python
normalize_reference(definition: SignalDefinition, value, quality: QualityFlag=QualityFlag.NONE) -> ScalarValue
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`definition`|[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)|是|无|位置或关键字。SignalDefinition，提供目标类型、scale、offset、choices及范围。|
|`value`|int &#124; float &#124; bool &#124; str|是|无|位置或关键字。一条已解码的原生值，按SignalDefinition转换和检查；数值信号不把数字字符串自动解析成数值。|
|`quality`|[QualityFlag](chronaxis.core.types.md#api-QualityFlag)|否|QualityFlag.NONE|位置或关键字。上游已有质量原因，默认NONE。|

### 返回说明

ScalarValue。正常值使用目标类型；无效时保留原值及缺失、非有限、
    超范围、解码失败、精度损失或溢出的原因。枚举同时保留固定标签域。

### 异常说明

TypeError: 声明、质量或原生标量结构不合法。
    数值转换失败记入quality，配置错误仍由底层检查直接抛出。

本函数直接报告的具体错误：

- `TypeError`：normalize需要SignalDefinition及QualityFlag。

### 流程说明

先处理已有质量、缺失值和显式无效值；逻辑类型按choices映射，
    数值类型应用额外的value * scale + offset，再检查定宽与valid_range。
    输入已完成上游解码，本函数不加载DBC，也不重复上游的工程单位转换。

返回类型：[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)。

源码：[`src/chronaxis/core/numeric.py:333`](../../../src/chronaxis/core/numeric.py#L333)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-memory_series_reference"></a>
## `memory_series_reference`

从当前内存来源提取一个字段，转换后生成信号历史。

```python
memory_series_reference(bindings: SignalBindings, name: str, *, capture_code=False) -> SignalSeries
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`bindings`|[SignalBindings](chronaxis.core.binding.md#api-SignalBindings)|是|无|位置或关键字。当前真实SignalBindings；name为其中已定义的简单别名。 原行时间使用整数纳秒，来源offset_ns只作为显式时间偏移应用一次。|
|`name`|str|是|无|位置或关键字。name为其中已定义的简单别名。     原行时间使用整数纳秒，来源offset_ns只作为显式时间偏移应用一次。|
|`capture_code`|bool|否|False|仅关键字。本次表达式需要 enum_code 时才保留映射前的整数。|

### 返回说明

SignalSeries。保存正常转换值或无效原值，以及质量、时间、序号和来源。

### 异常说明

绑定、归属、时间溢出、顺序或冲突检查失败时传播底层异常。

### 边界说明

只处理原行中实际出现的字段；其他字段更新不生成该信号的新观测。
    创建新的样本集合，不修改原行、不排序，也不读取日志或加载DBC。

返回类型：[SignalSeries](chronaxis.core.state.md#api-SignalSeries)。

源码：[`src/chronaxis/core/numeric.py:444`](../../../src/chronaxis/core/numeric.py#L444)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
