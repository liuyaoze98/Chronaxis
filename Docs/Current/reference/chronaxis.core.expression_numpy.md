# `chronaxis.core.expression_numpy`

在同长度信号列上批量求值表达式，并逐位置保留质量诊断。

evaluate_numpy接收当前编译绑定和context中的NumericArray，输出
ArrayEvaluation：数值结果列与独立的uint16依赖诊断列均为形状(N,)。
布尔逻辑用掩码区分TRUE、FALSE和UNKNOWN（未知），不把无效False占位
当作条件不成立；已知值决定结果时，原依赖异常仍留在诊断列。

解释器按表达式树遍历节点，每个节点用NumPy逐元素函数计算整列。
isclose使用显式atol与rtol计算abs(a-b) <= atol + rtol*abs(b)。
evaluate_memory_numpy从已有内存行归一化信号，用searchsorted找到每个
查询时间的最近观测，再按有效期保持并求值，不额外读取或解码。

依赖NumPy及核心编译、数值和对齐模块；共享检查协议，不调用参考数值
求值器。结果为独立只读存储，当前批次缓存不跨调用保留，不修改输入。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)、[D](chronaxis.core.types.md#api-SignalDType)、[DecodedBindings](chronaxis.core.decoded_binding.md#api-DecodedBindings)、[MessageBindings](chronaxis.core.message_binding.md#api-MessageBindings)、[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[SignalBindings](chronaxis.core.binding.md#api-SignalBindings)

## 对象导航

|对象|用途|
|---|---|
|[`ArrayEvaluation`](#api-ArrayEvaluation)|保存同长度的计算结果列与依赖质量诊断列。|
|[`ArrayEvaluation.__post_init__`](#api-ArrayEvaluation-__post_init__)|验证诊断布局和已知位后复制只读列。|
|[`_logic`](#api-_logic)|独立以整列掩码实现and/or/not三值真值表。|
|[`_constant`](#api-_constant)|把表达式中的一个常量重复成与输入同样长的一维数组。例如常量2对应3个输入时间，就生成3项值为2的数组；数据类型和枚举标签按已经检查过的表达式保存。|
|[`_literal_compare`](#api-_literal_compare)|在整数域比较原列与任意精确Python整数常量边界。|
|[`_where`](#api-_where)|按有效条件拆成真、假两个活动子批，再按原行序还原输出。|
|[`_evaluate`](#api-_evaluate)|按静态节点结构调用真实批量数值/逻辑内核。|
|[`evaluate_numpy`](#api-evaluate_numpy)|检查绑定、依赖列与行数后，批量计算一个表达式。|
|[`evaluate_memory_numpy`](#api-evaluate_memory_numpy)|从已有内存信号批量对齐到查询时间，再计算表达式。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from .enum_codes import memory_histories, aligned_column
from .expression import CompiledExpression
from .binding import SignalBindings
from .decoded_binding import DecodedBindings
from .message_binding import MessageBindings
from .numeric import INTEGER_BOUNDS
from .numeric_numpy import COMPARE_UFUNCS, DTYPES, NumericArray, _output, _readonly, binary_numpy, to_float_numpy, unary_numpy
from .affine_numpy import affine_numpy
from .expression_math_v4 import MATH_KERNELS
from .expression_math_numpy import math_numpy
from .expression_integer_v4 import INTEGER_KERNELS
from .expression_integer_numpy import integer_numpy
from .lookup_numpy import lookup_numpy
from .enum_codes import enum_code_numpy
from .expression_reference import require_context
from .normalize_numpy import memory_series_numpy
from .state_numpy import align_numpy, build_signal_array, _require_axis
from .types import QualityFlag as Q, SignalDType as D
```

</details>

<a id="api-ArrayEvaluation"></a>
## `ArrayEvaluation`

保存同长度的计算结果列与依赖质量诊断列。

value为NumericArray，dependency_quality是形状(N,)的uint16数组。
布尔结果可能因已知TRUE或FALSE而有效，诊断仍可包含非零的原依赖原因；
不能因此把UNKNOWN填为FALSE。构造时检查诊断布局并复制为只读存储。
实例不可重新赋值，不持有跨批次的求值状态。

```python
class ArrayEvaluation
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)|是|无|真实逻辑结果列。|
|`dependency_quality`|np.ndarray|是|无|同长uint16原因并集。|

源码：[`src/chronaxis/core/expression_numpy.py:54`](../../../src/chronaxis/core/expression_numpy.py#L54)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ArrayEvaluation-__post_init__"></a>
### `ArrayEvaluation.__post_init__`

验证诊断布局和已知位后复制只读列。

```python
ArrayEvaluation.__post_init__()
```

参数：无显式参数。


#### 参数说明

无，读取value与dependency_quality。

#### 返回说明

None，不修改调用侧数组。

#### 异常说明

TypeError/ValueError为结构/长度/未知位。

本函数直接报告的具体错误：

- `TypeError`：ArrayEvaluation诊断需1维uint16列。
- `ValueError`：ArrayEvaluation诊断长度/原因不合法。

源码：[`src/chronaxis/core/expression_numpy.py:66`](../../../src/chronaxis/core/expression_numpy.py#L66)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_logic"></a>
## `_logic`

独立以整列掩码实现and/or/not三值真值表。

```python
_logic(operator, values)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`operator`|str|是|无|位置或关键字。选择布尔运算：`and`要求全部成立；`or`要求至少一项成立；`not`反转一个已知真假值。未知值按三值逻辑处理，不能直接当成False。|
|`values`|tuple[[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray), ...]|是|无|位置或关键字。参加and或or的BOOL结果列，所有列的长度相同；同时保留各列的有效性和质量标记。|

### 返回说明

NumericArray，known决定时质量NONE，否则UNKNOWN原因并集。

### 异常说明

调用者保证static BOOL及shape，分配错误传播。

源码：[`src/chronaxis/core/expression_numpy.py:85`](../../../src/chronaxis/core/expression_numpy.py#L85)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_constant"></a>
## `_constant`

把表达式中的一个常量重复成与输入同样长的一维数组。例如常量2对应3个输入时间，就生成3项值为2的数组；数据类型和枚举标签按已经检查过的表达式保存。

```python
_constant(node, size)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`node`|ExprNode|是|无|位置或关键字。编译树中的const节点，保存常量值、类型及单位。|
|`size`|int|是|无|位置或关键字。需要生成的常量列行数，必须非负；0生成空列。|

### 返回说明

正常NumericArray；integer边界此前静态检查。

### 异常说明

模型/分配错误传播，不自动promotion。

源码：[`src/chronaxis/core/expression_numpy.py:120`](../../../src/chronaxis/core/expression_numpy.py#L120)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_literal_compare"></a>
## `_literal_compare`

在整数域比较原列与任意精确Python整数常量边界。

```python
_literal_compare(node, value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`node`|ExprNode|是|无|位置或关键字。编译后的比较节点，保存比较运算和未经浮点转换的整数常量边界。|
|`value`|[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)|是|无|位置或关键字。参与整数常量比较的定宽整数列，保留有效掩码与质量标记。|

### 返回说明

BOOL列，invalid保持原原因，不转float或cast越界常量。

### 异常说明

编译器保证类型与注册比较，分配错误传播。

源码：[`src/chronaxis/core/expression_numpy.py:135`](../../../src/chronaxis/core/expression_numpy.py#L135)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_where"></a>
## `_where`

按有效条件拆成真、假两个活动子批，再按原行序还原输出。

```python
_where(node, context, size, cache)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`node`|ExprNode|是|无|位置或关键字。已通过静态检查的操作节点，携带操作类型、输入依赖和输出单位。|
|`context`|Mapping[str, [NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)]|是|无|位置或关键字。当前批按别名取得的输入列，分支只在被选中的行上求值。|
|`size`|int|是|无|位置或关键字。整个当前批的行数，划分子批并恢复原行序时使用。|
|`cache`|dict[ExprNode, [ArrayEvaluation](chronaxis.core.expression_numpy.md#api-ArrayEvaluation)]|是|无|位置或关键字。仅限当前批行坐标的求值结果缓存，不能把其他子批的数组当作对应行。|

### 返回说明

ArrayEvaluation；条件未知的行保留条件原因，其他行仅并入所选分支诊断。

### 异常说明

模型、数组布局或分配发生异常时直接交给调用者处理；不以逐行解释器代替掩码计算。

源码：[`src/chronaxis/core/expression_numpy.py:163`](../../../src/chronaxis/core/expression_numpy.py#L163)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_evaluate"></a>
## `_evaluate`

按静态节点结构调用真实批量数值/逻辑内核。

```python
_evaluate(node, context, size, cache)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`node`|ExprNode|是|无|位置或关键字。当前待求值的表达式节点；递归求值其依赖节点，并在本批缓存结果。|
|`context`|Mapping[str, [NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)]|是|无|位置或关键字。信号别名到本批输入列的映射；各列行数须与size一致。|
|`size`|int|是|无|位置或关键字。本批输入行数，决定常量及表达式结果列的长度。|
|`cache`|dict|是|无|位置或关键字。本次计算使用的局部缓存。表达式求值按节点保存已算结果，编译入口按表达式保存编译结果；不能跨绑定或跨次运行复用。|

### 返回说明

ArrayEvaluation，完整诊断不因known逻辑结果丢失。

### 异常说明

静态/输入模型问题传播，不调用reference/eval/逐样本Python。

源码：[`src/chronaxis/core/expression_numpy.py:200`](../../../src/chronaxis/core/expression_numpy.py#L200)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-evaluate_numpy"></a>
## `evaluate_numpy`

检查绑定、依赖列与行数后，批量计算一个表达式。

```python
evaluate_numpy(compiled: CompiledExpression, context, bindings: SignalBindings | DecodedBindings | MessageBindings, *, size: int | None=None) -> ArrayEvaluation
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiled`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)|是|无|位置或关键字。当前CompiledExpression；bindings为对应普通或MessageBindings运行绑定。|
|`context`|[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)|是|无|位置或关键字。以精确依赖别名为键的NumericArray映射；所有列须同长同布局。|
|`bindings`|[SignalBindings](chronaxis.core.binding.md#api-SignalBindings) &#124; [DecodedBindings](chronaxis.core.decoded_binding.md#api-DecodedBindings) &#124; [MessageBindings](chronaxis.core.message_binding.md#api-MessageBindings)|是|无|位置或关键字。bindings为对应普通或MessageBindings运行绑定。     context: 以精确依赖别名为键的NumericArray映射|
|`size`|int &#124; None|否|None|仅关键字。可选的非负行数N。可从第一列推断，纯常量无依赖时必须显式提供。|

### 返回说明

ArrayEvaluation，结果和诊断均为形状(N,)的独立只读数组，允许N为零。

### 异常说明

TypeError、ValueError: 模型、绑定身份、依赖键、类型、枚举域或形状不合法。
    数值失败追加质量原因；内存分配异常直接传播。

本函数直接报告的具体错误：

- `TypeError`：size需要非负原生int。
- `ValueError`：纯常量批量执行须明确size。
- `TypeError`：context列dtype与当前绑定不同。
- `ValueError`：context enum域不同。
- `ValueError`：context各列shape不同。

### 边界说明

不广播或补齐错位列。每次调用创建新缓存，只复用当前批次的公共子树。

返回类型：[ArrayEvaluation](chronaxis.core.expression_numpy.md#api-ArrayEvaluation)。

源码：[`src/chronaxis/core/expression_numpy.py:297`](../../../src/chronaxis/core/expression_numpy.py#L297)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-evaluate_memory_numpy"></a>
## `evaluate_memory_numpy`

从已有内存信号批量对齐到查询时间，再计算表达式。

```python
evaluate_memory_numpy(compiled: CompiledExpression, times: np.ndarray, *, point: bool=False) -> ArrayEvaluation
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiled`|[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)|是|无|位置或关键字。关联真实输入的CompiledExpression。|
|`times`|np.ndarray|是|无|位置或关键字。非递减的一维int64纳秒轴，形状(N,)；point控制真实末点查询视图。|
|`point`|bool|否|False|仅关键字。point控制真实末点查询视图。|

### 返回说明

同形状ArrayEvaluation，保留有效掩码、质量原因和绑定身份。

### 异常说明

TypeError: 非memory绑定，包括DecodedBindings；其他时间/归属/形状发生异常时直接交给调用者处理。

本函数直接报告的具体错误：

- `TypeError`：memory快捷求值需要真实SignalBindings的CompiledExpression。
- `TypeError`：point需要bool。

### 流程说明

只建立实际依赖的历史列，独立归一化并按有效期对齐，再整列求值。
    纯常量也检查时间轴；保留完整历史，结果复制存储，不额外读取或解码。

返回类型：[ArrayEvaluation](chronaxis.core.expression_numpy.md#api-ArrayEvaluation)。

源码：[`src/chronaxis/core/expression_numpy.py:348`](../../../src/chronaxis/core/expression_numpy.py#L348)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
