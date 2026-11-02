# chronaxis.core.expression_reference

用独立标量计算求值表达式，并保留未知结果的原因。

evaluate_reference接收当前CompiledExpression、真实普通或消息绑定和context。
context按依赖别名提供ScalarValue，输出Evaluation，分别保存计算结果和
全部被求值依赖的质量原因。evaluate_memory_reference还可从已有内存行
提取信号，经参考转换和按时间保持后，在给定纳秒坐标逐点求值。

布尔表达式使用TRUE、FALSE、UNKNOWN（未知）三种状态。例如FALSE and
UNKNOWN可确定为FALSE，TRUE or UNKNOWN可确定为TRUE；被遮蔽的异常
仍保留在dependency_quality中。isclose按abs(a-b) <= atol + rtol*abs(b)
计算，两种容差均由表达式显式提供，非有限中间值不能变成正常判断。

只依赖标准库和参考数值、对齐模块，不执行任意Python代码，也不读取
旧日志或额外解码。当前求值缓存不跨时间点保留，不调用NumPy数值内核。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)、[D](chronaxis.core.types.md#api-SignalDType)、[DecodedBindings](chronaxis.core.decoded_binding.md#api-DecodedBindings)、[MessageBindings](chronaxis.core.message_binding.md#api-MessageBindings)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)、[SignalBindings](chronaxis.core.binding.md#api-SignalBindings)

## 对象导航

|对象|用途|
|---|---|
|[`Evaluation`](#api-Evaluation)|分别保存可用的计算结果，以及本次求值的全部质量诊断。|
|[`require_context`](#api-require_context)|核对表达式的输入身份和调用者提供的依赖名称。|
|[`_logic`](#api-_logic)|独立标量三值and/or/not，不以UNKNOWN当False。|
|[`_evaluate`](#api-_evaluate)|用独立参考数值解释单个冻结节点及局部公共子树。|
|[`evaluate_reference`](#api-evaluate_reference)|检查当前标量输入后，对表达式进行一次独立参考求值。|
|[`evaluate_memory_reference`](#api-evaluate_memory_reference)|从已有内存行取得信号，在指定纳秒坐标逐点计算表达式。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from collections.abc import Mapping
from .expression import CompiledExpression
from .binding import SignalBindings
from .decoded_binding import DecodedBindings
from .message_binding import MessageBindings
from .numeric import COMPARE_FUNCTIONS, ScalarValue, binary_reference, memory_series_reference, to_float_reference, unary_reference
from .state import align_reference
from .types import QualityFlag as Q, SignalDType as D
```

</details>

<a id="api-Evaluation"></a>
## `Evaluation`

分别保存可用的计算结果，以及本次求值的全部质量诊断。

value是ScalarValue，其quality表示结果本身不可用的原因。
dependency_quality另存依赖和计算的原因并集；即使已知FALSE或TRUE使
布尔结果可以确定，原来的异常也仍可追溯，不能强塞回正常结果的quality。
实例不可重新赋值，不保存下一个时间点的信号状态。

```python
class Evaluation
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)|是|无|实际逻辑输出。|
|`dependency_quality`|[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)|是|无|原依赖/本次计算的全部诊断并集。|

源码：[`src/chronaxis/core/expression_reference.py:39`](../../../src/chronaxis/core/expression_reference.py#L39)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-require_context"></a>
## `require_context`

核对表达式的输入身份和调用者提供的依赖名称。

```python
require_context(compiled, context, bindings)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiled`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)|是|无|位置或关键字。可执行CompiledExpression；context为真实映射对象。|
|`context`|Mapping|是|无|位置或关键字。context为真实映射对象。     bindings: 当前SignalBindings、DecodedBindings或MessageBindings，须与编译身份一致。|
|`bindings`|[DecodedBindings](chronaxis.core.decoded_binding.md#api-DecodedBindings) &#124; [MessageBindings](chronaxis.core.message_binding.md#api-MessageBindings) &#124; [SignalBindings](chronaxis.core.binding.md#api-SignalBindings)|是|无|位置或关键字。当前SignalBindings、DecodedBindings或MessageBindings，须与编译身份一致。|

### 返回说明

None。context的键必须恰好等于dependencies，纯常量表达式需空映射。

### 异常说明

TypeError: 计划、映射或绑定模型类型不合法。
    ValueError: 绑定身份不同，或依赖键缺失、多余。

本函数直接报告的具体错误：

- `TypeError`：执行需要CompiledExpression/context及真实普通或消息绑定。
- `ValueError`：可执行表达式与当前输入绑定身份不同。
- `ValueError`：context必须精确提供表达式dependencies。

### 边界说明

只校验结构，不读来源、不求值；各个值的类型由后续执行入口检查。

源码：[`src/chronaxis/core/expression_reference.py:52`](../../../src/chronaxis/core/expression_reference.py#L52)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_logic"></a>
## `_logic`

独立标量三值and/or/not，不以UNKNOWN当False。

```python
_logic(operator, values)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`operator`|str|是|无|位置或关键字。选择布尔运算：`and`要求全部成立；`or`要求至少一项成立；`not`反转一个已知真假值。未知值按三值逻辑处理，不能直接当成False。|
|`values`|tuple[[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue), ...]|是|无|位置或关键字。op固定逻辑名，values为BOOL ScalarValue tuple。|

### 返回说明

ScalarValue；正常决断quality NONE，未知保留原因并集。

### 异常说明

调用侧静态类型保证，不接数值truthiness。

源码：[`src/chronaxis/core/expression_reference.py:84`](../../../src/chronaxis/core/expression_reference.py#L84)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_evaluate"></a>
## `_evaluate`

用独立参考数值解释单个冻结节点及局部公共子树。

```python
_evaluate(node, context, cache)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`node`|ExprNode|是|无|位置或关键字。当前待求值的表达式节点；递归计算该时刻各子节点的标量结果。|
|`context`|Mapping[str, [ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)]|是|无|位置或关键字。信号别名到当前时刻数值的映射，包含值类型、有效性和质量原因。|
|`cache`|dict|是|无|位置或关键字。本次计算使用的局部缓存。表达式求值按节点保存已算结果，编译入口按表达式保存编译结果；不能跨绑定或跨次运行复用。|

### 返回说明

Evaluation，完整诊断与逻辑有效性分开。

### 异常说明

静态模型/类型错误直接传播，不eval或吞配置异常。

源码：[`src/chronaxis/core/expression_reference.py:115`](../../../src/chronaxis/core/expression_reference.py#L115)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-evaluate_reference"></a>
## `evaluate_reference`

检查当前标量输入后，对表达式进行一次独立参考求值。

```python
evaluate_reference(compiled: CompiledExpression, context: Mapping, bindings: SignalBindings | DecodedBindings | MessageBindings) -> Evaluation
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiled`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)|是|无|位置或关键字。当前CompiledExpression；bindings为对应的普通或MessageBindings运行绑定。|
|`context`|Mapping|是|无|位置或关键字。以精确依赖别名为键的ScalarValue映射，声明类型与枚举域须匹配。|
|`bindings`|[SignalBindings](chronaxis.core.binding.md#api-SignalBindings) &#124; [DecodedBindings](chronaxis.core.decoded_binding.md#api-DecodedBindings) &#124; [MessageBindings](chronaxis.core.message_binding.md#api-MessageBindings)|是|无|位置或关键字。bindings为对应的普通或MessageBindings运行绑定。     context: 以精确依赖别名为键的ScalarValue映射，声明类型与枚举域须匹配。|

### 返回说明

Evaluation，区分正常或未知的计算结果，并保留所有依赖的质量诊断。

### 异常说明

TypeError、ValueError: 依赖键、模型、类型、枚举域或绑定身份不合法。
    数值计算失败写入质量原因，不把配置错误当作缺失数据。

本函数直接报告的具体错误：

- `TypeError`：context值与当前signal dtype不一致。
- `ValueError`：context enum域与绑定不同。

### 边界说明

每次调用使用新缓存，只复用本次求值中的公共子树，不继承上一次的值。

返回类型：[Evaluation](chronaxis.core.expression_reference.md#api-Evaluation)。

源码：[`src/chronaxis/core/expression_reference.py:190`](../../../src/chronaxis/core/expression_reference.py#L190)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-evaluate_memory_reference"></a>
## `evaluate_memory_reference`

从已有内存行取得信号，在指定纳秒坐标逐点计算表达式。

```python
evaluate_memory_reference(compiled: CompiledExpression, times: tuple[int, ...], *, point: bool=False) -> tuple[Evaluation, ...]
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiled`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)|是|无|位置或关键字。关联真实内存输入的CompiledExpression。|
|`times`|tuple[int, ...]|是|无|位置或关键字。非递减的整数纳秒元组；point控制真实末点查询视图。|
|`point`|bool|否|False|仅关键字。point控制真实末点查询视图。|

### 返回说明

与times等长的Evaluation元组，保存正常值、未知状态和依赖诊断。

### 异常说明

TypeError: 非memory绑定，包括DecodedBindings；其他时间/来源/配置发生异常时直接交给调用者处理。

本函数直接报告的具体错误：

- `TypeError`：memory快捷求值需要真实SignalBindings的CompiledExpression。
- `TypeError`：times需tuple且point需bool。
- `ValueError`：时间轴回退。

### 边界说明

只提取实际依赖，先归一化再按有效期保持；纯常量也检查时间轴。
    为完整内存历史建立新对象，不读取文件、额外解码或修改原行。

返回类型：tuple[[Evaluation](chronaxis.core.expression_reference.md#api-Evaluation), ...]。

源码：[`src/chronaxis/core/expression_reference.py:224`](../../../src/chronaxis/core/expression_reference.py#L224)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
