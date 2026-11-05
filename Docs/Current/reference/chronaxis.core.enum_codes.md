# `chronaxis.core.enum_codes`

在 v4 表达式中读取按需保留的枚举原始整数列，标签索引没有原码含义。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)、[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)

## 对象导航

|对象|用途|
|---|---|
|[`validate_code_dtype`](#api-validate_code_dtype)|检查声明的整数存储类型及其可表示的 choices 键。|
|[`compile_enum_code`](#api-compile_enum_code)|从已编译的枚举来源取得原码 dtype 并登记本节点的真实依赖。|
|[`code_dependencies`](#api-code_dependencies)|收集参与本次计算或其派生子树的枚举原码，忽略单纯使用标签的名称。|
|[`original_code`](#api-original_code)|把已解码原整数装入声明的定宽类型，不经标签或浮点中转。|
|[`code_column`](#api-code_column)|按原生输入类型装箱有限原码批；未请求不分配列。|
|[`memory_histories`](#api-memory_histories)|只为实际消费码视图的表达式建立附原码的历史。|
|[`aligned_scalar`](#api-aligned_scalar)|恢复对齐点的标签和独立原码，过期和域外状态同时作用于两者。|
|[`expire_value`](#api-expire_value)|把同一观测边界分别施加到值及附带原码，各自保留独立质量。|
|[`aligned_column`](#api-aligned_column)|使用数组保持的相同样本索引同步原码及其自身质量。|
|[`history_code`](#api-history_code)|读取历史中单独保存的原码，从原数据重查标签映射无关的质量。|
|[`historical_column`](#api-historical_column)|沿历史保持的有样本掩码及时间质量构建请求的原码列。|
|[`enum_code_reference`](#api-enum_code_reference)|读取一条原码及其独立质量，保持有效的未映射代码。|
|[`enum_code_numpy`](#api-enum_code_numpy)|读取当前批的原码列及独立有效性，原码与枚举有效性分别判断。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .numeric import INTEGER_BOUNDS, ScalarValue
from .types import QualityFlag as Q, SignalDType as D
from math import isfinite
```

</details>

<a id="api-validate_code_dtype"></a>
## `validate_code_dtype`

检查声明的整数存储类型及其可表示的 choices 键。

```python
validate_code_dtype(dtype, choices)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`dtype`|SignalDType|是|无|位置或关键字。为枚举原码声明的 INT64 或 UINT64，决定每个键允许的整数范围。|
|`choices`|Iterable[tuple[int, str]]|是|无|位置或关键字。原始整数到逻辑标签的映射对，只检验原码键类型及定宽边界。|

### 返回说明

None。

### 异常说明

ValueError 为非整数类型、非整数键或定宽范围不符。
同一标签可由多个不同代码表示，此处不反向查找标签。

源码：[`src/chronaxis/core/enum_codes.py:8`](../../../src/chronaxis/core/enum_codes.py#L8)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-compile_enum_code"></a>
## `compile_enum_code`

从已编译的枚举来源取得原码 dtype 并登记本节点的真实依赖。

```python
compile_enum_code(compiler, call)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiler`|UnitCompiler|是|无|位置或关键字。当前 v4 编译器实例，负责验证参数、统一单位及在原配置位置报告错误。|
|`call`|ast.Call|是|无|位置或关键字。当前函数调用的原始语法节点，提供参数和关键字，并用于定位配置错误。|

### 返回说明

输出单位 1 的整数节点。

### 异常说明

参数数量、来源或原码类型不明时报编译错误。

源码：[`src/chronaxis/core/enum_codes.py:22`](../../../src/chronaxis/core/enum_codes.py#L22)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-code_dependencies"></a>
## `code_dependencies`

收集参与本次计算或其派生子树的枚举原码，忽略单纯使用标签的名称。

```python
code_dependencies(root)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`root`|ExprNode|是|无|位置或关键字。当前已编译表达式子树的根，包含静态类型、操作和依赖。|

### 返回说明

需要同时读取原码的别名集合。

### 异常说明

输入不是表达式节点时传播属性错误。

源码：[`src/chronaxis/core/enum_codes.py:40`](../../../src/chronaxis/core/enum_codes.py#L40)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-original_code"></a>
## `original_code`

把已解码原整数装入声明的定宽类型，不经标签或浮点中转。

```python
original_code(definition, original, quality=Q.NONE)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`definition`|SignalDefinition|是|无|位置或关键字。声明枚举标签、原码类型和无效值策略的信号定义，用于从实际输入恢复独立原码。|
|`original`|object|是|无|位置或关键字。映射到逻辑标签前的解码值，需检验缺失、原始类型、范围和用户声明的无效值。|
|`quality`|QualityFlag|否|Q.NONE|位置或关键字。读取原始观测时已有的质量位，已有错误时不把原码当作有效整数。|

### 返回说明

整数 ScalarValue。

### 异常说明

缺少有效类型声明时报错。未知映射不使整数本身无效。

源码：[`src/chronaxis/core/enum_codes.py:58`](../../../src/chronaxis/core/enum_codes.py#L58)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-code_column"></a>
## `code_column`

按原生输入类型装箱有限原码批；未请求不分配列。

```python
code_column(definition, originals)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`definition`|SignalDefinition|是|无|位置或关键字。声明枚举标签、原码类型和无效值策略的信号定义，用于从实际输入恢复独立原码。|
|`originals`|Sequence[object]|是|无|位置或关键字。一批映射前的原输入，按记录顺序检验整数身份并组成定宽数组。|

### 返回说明

None 或只读的定宽整数 NumericArray。

### 异常说明

声明或输入违反模型时传播。

源码：[`src/chronaxis/core/enum_codes.py:80`](../../../src/chronaxis/core/enum_codes.py#L80)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-memory_histories"></a>
## `memory_histories`

只为实际消费码视图的表达式建立附原码的历史。

```python
memory_histories(compiled, names, factory, condition=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiled`|CompiledExpression|是|无|位置或关键字。包含实际运行绑定的值表达式，遍历树确定哪些别名要保留原码。|
|`names`|Iterable[str]|是|无|位置或关键字。值表达式与条件表达式实际联合依赖的信号别名。|
|`factory`|Callable|是|无|位置或关键字。当前后端建历史的函数，按别名接收绑定及 capture_code 标志。|
|`condition`|CompiledExpression &#124; None|否|None|位置或关键字。可选的筛选条件，条件内显式请求原码的信号也要保留该列。|

### 返回说明

名称到 SignalSeries 的映射。

### 异常说明

原输入转换或绑定错误直接传播。

源码：[`src/chronaxis/core/enum_codes.py:100`](../../../src/chronaxis/core/enum_codes.py#L100)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-aligned_scalar"></a>
## `aligned_scalar`

恢复对齐点的标签和独立原码，过期和域外状态同时作用于两者。

```python
aligned_scalar(definition, state)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`definition`|SignalDefinition|是|无|位置或关键字。声明枚举标签、原码类型和无效值策略的信号定义，用于从实际输入恢复独立原码。|
|`state`|StateValue|是|无|位置或关键字。参考后端在某个时刻的保持值，含过期、来源边界和原码的独立质量。|

### 返回说明

ScalarValue。

### 异常说明

质量或输入布局非法时传播。

源码：[`src/chronaxis/core/enum_codes.py:112`](../../../src/chronaxis/core/enum_codes.py#L112)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-expire_value"></a>
## `expire_value`

把同一观测边界分别施加到值及附带原码，各自保留独立质量。

```python
expire_value(value, reason)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)|是|无|位置或关键字。当前保存的类型化标量，可能含同步保留的枚举原码。|
|`reason`|QualityFlag|是|无|位置或关键字。应同时施加到逻辑值与原码的过期、缺失或来源边界质量位。|

### 返回说明

当前时刻无效的 ScalarValue。

### 异常说明

错误 dtype 或质量组合由模型拒绝。

源码：[`src/chronaxis/core/enum_codes.py:126`](../../../src/chronaxis/core/enum_codes.py#L126)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-aligned_column"></a>
## `aligned_column`

使用数组保持的相同样本索引同步原码及其自身质量。

```python
aligned_column(state)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`state`|AlignedArray|是|无|位置或关键字。数组对齐器给出的保持批，保留相同时间轴的原始索引、质量及可选原码。|

### 返回说明

NumericArray；标签单独使用时不分配码列。

### 异常说明

不一致的历史布局或整数存储错误。

源码：[`src/chronaxis/core/enum_codes.py:138`](../../../src/chronaxis/core/enum_codes.py#L138)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-history_code"></a>
## `history_code`

读取历史中单独保存的原码，从原数据重查标签映射无关的质量。

```python
history_code(definition, sample)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`definition`|SignalDefinition|是|无|位置或关键字。声明枚举标签、原码类型和无效值策略的信号定义，用于从实际输入恢复独立原码。|
|`sample`|HistorySample &#124; None|是|无|位置或关键字。当前回读的实际历史观测，None 表示此处尚无原始样本。|

### 返回说明

原码 ScalarValue。

### 异常说明

缺少必要历史投影时明确失败。

源码：[`src/chronaxis/core/enum_codes.py:164`](../../../src/chronaxis/core/enum_codes.py#L164)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-historical_column"></a>
## `historical_column`

沿历史保持的有样本掩码及时间质量构建请求的原码列。

```python
historical_column(definition, arrays)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`definition`|SignalDefinition|是|无|位置或关键字。声明枚举标签、原码类型和无效值策略的信号定义，用于从实际输入恢复独立原码。|
|`arrays`|_HeldArrays|是|无|位置或关键字。在同一历史快照上对齐的有限数组批，提供是否有样本的掩码及时间质量。|

### 返回说明

与该批同长的整数 NumericArray。

### 异常说明

缺少原码投影或布局错误。

源码：[`src/chronaxis/core/enum_codes.py:182`](../../../src/chronaxis/core/enum_codes.py#L182)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-enum_code_reference"></a>
## `enum_code_reference`

读取一条原码及其独立质量，保持有效的未映射代码。

```python
enum_code_reference(node, operand)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`node`|ExprNode|是|无|位置或关键字。已通过静态检查的操作节点，携带操作类型、输入依赖和输出单位。|
|`operand`|[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)|是|无|位置或关键字。已求值的枚举操作数，其中的独立整数原码可直接读取，未观测时保留相应质量。|

### 返回说明

整数 ScalarValue。

### 异常说明

已有观测却缺原码投影或类型不一致时报错。

源码：[`src/chronaxis/core/enum_codes.py:197`](../../../src/chronaxis/core/enum_codes.py#L197)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-enum_code_numpy"></a>
## `enum_code_numpy`

读取当前批的原码列及独立有效性，原码与枚举有效性分别判断。

```python
enum_code_numpy(node, operand)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`node`|ExprNode|是|无|位置或关键字。已通过静态检查的操作节点，携带操作类型、输入依赖和输出单位。|
|`operand`|[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)|是|无|位置或关键字。已求值的枚举操作数，其中的独立整数原码可直接读取，未观测时保留相应质量。|

### 返回说明

同形状整数 NumericArray。

### 异常说明

有观测而原码投影缺失或类型错误时报错。

源码：[`src/chronaxis/core/enum_codes.py:210`](../../../src/chronaxis/core/enum_codes.py#L210)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
