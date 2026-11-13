# `chronaxis.core.expression`

检查表达式中每个名称、运算、函数、类型和单位。例如voltage * current可以算功率，而battery.current这种属性访问不允许。检查成功后生成执行器可用的表达式对象；不会打开数据文件或运行任意Python代码。全部语法见表达式完整说明。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[DeclarationBindings](chronaxis.core.declarations.md#api-DeclarationBindings)、[DecodedBindings](chronaxis.core.decoded_binding.md#api-DecodedBindings)、[ExtensionRegistry](chronaxis.extensions.md#api-ExtensionRegistry)、[MessageBindings](chronaxis.core.message_binding.md#api-MessageBindings)、[MessageDeclarations](chronaxis.core.message_binding.md#api-MessageDeclarations)、[PreparedLookup](chronaxis.core.lookup.md#api-PreparedLookup)、[SignalBindings](chronaxis.core.binding.md#api-SignalBindings)、[SignalDType](chronaxis.core.types.md#api-SignalDType)

## 对象导航

|对象|用途|
|---|---|
|[`DerivedDefinition`](#api-DerivedDefinition)|声明一个由现有信号计算得到的新名称、表达式和结果单位。|
|[`DerivedDefinition.__post_init__`](#api-DerivedDefinition-__post_init__)|验证派生声明结构，不解析或加载来源。|
|[`ExprNode`](#api-ExprNode)|保存表达式编译器已检查的一个内部节点。|
|[`CompiledExpression`](#api-CompiledExpression)|保存可供求值器使用的表达式树及其真实输入绑定。|
|[`StaticExpression`](#api-StaticExpression)|表达式通过配置检查后得到的对象。它保存语法、类型、单位和依赖名称，但尚未核实实际数据，不能直接交给数值求值器。运行时需要根据实际输入生成CompiledExpression。|
|[`contains_host_call`](#api-contains_host_call)|判定子树是否含宿主运行回调，以隔离静态常量参数检查。|
|[`_node`](#api-_node)|从已验证子节点汇总局部依赖及单位状态。|
|[`_SyntaxCompiler`](#api-_SyntaxCompiler)|在一次编译中检查名称、语法、单位与派生依赖。|
|[`_SyntaxCompiler.__init__`](#api-_SyntaxCompiler-__init__)|建立当前声明表并校验完整派生输入。|
|[`_SyntaxCompiler._error`](#api-_SyntaxCompiler-_error)|给出语法位置、拒绝原因与可用别名。|
|[`_SyntaxCompiler.parse`](#api-_SyntaxCompiler-parse)|解析一个表达式并验证根结果单位/枚举域。|
|[`_SyntaxCompiler._final_unit`](#api-_SyntaxCompiler-_final_unit)|执行当前版本的根结果单位要求。|
|[`_SyntaxCompiler._name`](#api-_SyntaxCompiler-_name)|解析真实别名、消息参数或本计划派生，并拒绝环/未知名称。|
|[`_SyntaxCompiler._context`](#api-_SyntaxCompiler-_context)|把纯数字/enum常量按另一侧明确类型及单位校验。|
|[`_SyntaxCompiler._units`](#api-_SyntaxCompiler-_units)|按首版表推断单位，裸常量加减/比较采用对方单位。|
|[`_SyntaxCompiler._binary`](#api-_SyntaxCompiler-_binary)|静态编译数值/比较，整数常量比较保留精确边界。|
|[`_SyntaxCompiler.visit`](#api-_SyntaxCompiler-visit)|逐AST节点执行首版白名单，不递归放行未知语法。|
|[`compile_expression`](#api-compile_expression)|检查表达式及全部派生声明，关联当前真实输入绑定。|
|[`validate_expression`](#api-validate_expression)|只根据来源声明检查表达式，不读取真实输入。|
|[`_create_compiler`](#api-_create_compiler)|构造当前编译器，拒绝用参数重解释绑定版本。|
|[`expression_identity`](#api-expression_identity)|共用公开与按需重编译的身份公式，防止版本接线遗漏。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass, field, replace
from hashlib import sha256
from math import isfinite
from types import MappingProxyType
from .binding import SignalBindings, _identity
from .lookup import PreparedLookup
from .declarations import DeclarationBindings
from .decoded_binding import DecodedBindings
from .message_binding import MessageBindings, MessageDeclarations
from .numeric import INTEGER_BOUNDS, result_dtype
from .types import SignalDType
from .unit_registry import resolve_unit
from .validation import require_identifier, require_text
```

</details>

<a id="api-DerivedDefinition"></a>
## `DerivedDefinition`

声明一个由现有信号计算得到的新名称、表达式和结果单位。

name与原信号共用名称空间，需在bindings.derived_names中预先登记。
构造本类只检查文本和名称；表达式编译时才检查单位、依赖和循环引用。
unit省略时由表达式支持的单位关系推导；显式标签不授权猜测物理量纲，未知单位组合仍保留unverified状态，
表示关系未验证。实例不可重新赋值，不保存信号值或运行中的状态。

```python
class DerivedDefinition
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|已在bindings.derived_names登记的简单别名。|
|`expr`|str|是|无|白名单DSL文本，不是任意Python。|
|`unit`|str &#124; None|否|None|缺省使用表达式已支持的单位关系。|

源码：[`src/chronaxis/core/expression.py:57`](../../../src/chronaxis/core/expression.py#L57)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-DerivedDefinition-__post_init__"></a>
### `DerivedDefinition.__post_init__`

验证派生声明结构，不解析或加载来源。

```python
DerivedDefinition.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无；读取name/expr/unit。

#### 返回说明

None，不改用户声明。

#### 异常说明

TypeError/ValueError为标识符/空文本问题。

返回类型：None。

源码：[`src/chronaxis/core/expression.py:70`](../../../src/chronaxis/core/expression.py#L70)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ExprNode"></a>
## `ExprNode`

保存表达式编译器已检查的一个内部节点。

operator给出注册操作，args保存不可变子节点，dtype和unit说明结果类型与单位。
aliases记录展开后的原信号依赖，运行时只按简单别名取值，不访问属性路径。
constant说明整棵子树只由字面量组成；编译器可据此赋予常量上下文单位和
整数类型，不能借此改变信号本身的类型。unit_status保留单位是否已验证。
节点不保存样本值缓存，解释器的计算结果仅在当前一次求值中保存。

```python
class ExprNode
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`operator`|str|是|无|节点执行的操作。`const`保存常量；`name`读取信号；`add/sub/mul/div`分别加、减、乘、除；`eq/ne/lt/le/gt/ge`分别等于、不等于、小于、小于或等于、大于、大于或等于；`and/or/not`为且、或、非；`abs/neg`取绝对值、相反数；`isclose`按给定容差比较；`to_float`转成浮点数；`int_literal_eq/ne/lt/le/gt/ge`按精确整数字面量边界作对应的六种比较。节点由编译器生成，普通用户在配置中填写表达式。|
|`dtype`|[SignalDType](chronaxis.core.types.md#api-SignalDType)|是|无|SignalDType枚举成员：INT64是有符号64位整数，UINT64是无符号64位整数，FLOAT64是双精度浮点，BOOL是真/假，ENUM是预先声明的状态标签。这里传枚举成员，不传字符串；当前运算支持哪些类型仍见本对象的约束。|
|`unit`|str|是|无|结果单位标签。|
|`unit_status`|str|是|无|`"verified"`表示单位及换算关系已通过程序的单位表检查；`"unverified"`表示使用未登记的单位文字，程序未验证其物理换算关系。|
|`args`|tuple|否|()|参与本操作的子节点元组。const和name没有子节点；abs、neg、not、to_float及int_literal_*有一个；算术和普通比较有两个；and/or可有多个；isclose按a、b、atol、rtol顺序有四个。|
|`value`|int &#124; float &#124; bool &#124; str &#124; tuple[int &#124; float, int &#124; float] &#124; [PreparedLookup](chronaxis.core.lookup.md#api-PreparedLookup) &#124; None|否|None|纯常量或精确比较边界。 None用于非恒定值节点；实际常量保存在此字段。|
|`name`|str &#124; None|否|None|name仅简单已绑定别名。 None用于不是信号引用的节点；信号节点保存简单别名。|
|`labels`|tuple[str, ...]|否|()|enum逻辑域。|
|`aliases`|tuple[str, ...]|否|()|本节点实际依赖的原信号别名元组；派生信号会展开到它依赖的原信号。没有信号依赖时为空元组。|
|`constant`|bool|否|False|纯常量静态上下文标志。|
|`allow_float_literal`|bool|否|False|编译器已检查是否可以让浮点字面量参与当前运算。True表示可以，False表示不能走这条转换路径；普通用户不通过修改此字段放宽类型检查。|
|`conversion_promoted`|bool|否|False|编译时类型提升依据，不影响最终数值节点等价。|
|`unit_explicit`|bool|否|False|编译时目标尺度；运行身份由实际转换节点确定。|
|`typed_constant`|bool|否|False|带单位纯常量只适配dtype，不继承别的单位。|
|`host_function`|FunctionSpec &#124; None|否|None|宿主逐点调用编译出的函数契约，保存输出规范、回调及实现身份。普通表达式节点省略。|

源码：[`src/chronaxis/core/expression.py:87`](../../../src/chronaxis/core/expression.py#L87)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-CompiledExpression"></a>
## `CompiledExpression`

保存可供求值器使用的表达式树及其真实输入绑定。

root已检查语法、类型与单位；dependencies只包含展开后的原信号别名。
identity关联绑定、派生定义、规范语法树和编译版本。改变会话、字段映射、
有效期或转换声明都会影响身份，解释器要求调用时bindings与编译时一致。
实例不可重新赋值，没有全局执行缓存；创建本对象并不执行数值计算。

```python
class CompiledExpression
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`text`|str|是|无|原表达式仅供定位，不动态执行。|
|`bindings`|[SignalBindings](chronaxis.core.binding.md#api-SignalBindings) &#124; [DecodedBindings](chronaxis.core.decoded_binding.md#api-DecodedBindings) &#124; [MessageBindings](chronaxis.core.message_binding.md#api-MessageBindings)|是|无|各自真实输入域的运行身份。|
|`root`|[ExprNode](chronaxis.core.expression.md#api-ExprNode)|是|无|实际白名单带有明确类型的树。|
|`dependencies`|tuple[str, ...]|是|无|实际需要的已解码信号列。|
|`normalized_ast`|str|是|无|不含位置的AST规范结构。|
|`identity`|str|是|无|完整执行身份SHA。|

源码：[`src/chronaxis/core/expression.py:115`](../../../src/chronaxis/core/expression.py#L115)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-StaticExpression"></a>
## `StaticExpression`

表达式通过配置检查后得到的对象。它保存语法、类型、单位和依赖名称，但尚未核实实际数据，不能直接交给数值求值器。运行时需要根据实际输入生成CompiledExpression。

```python
class StaticExpression
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`text`|str|是|无|原DSL，仅用于定位。|
|`bindings`|[DeclarationBindings](chronaxis.core.declarations.md#api-DeclarationBindings) &#124; [MessageDeclarations](chronaxis.core.message_binding.md#api-MessageDeclarations)|是|无|声明身份，没有实际读入证明。|
|`root`|[ExprNode](chronaxis.core.expression.md#api-ExprNode)|是|无|白名单类型/单位已经校验。|
|`dependencies`|tuple[str, ...]|是|无|展开后的原信号依赖。|
|`normalized_ast`|str|是|无|规范语法，仅供静态身份。|
|`identity`|str|是|无|独立静态版本前缀的SHA。|

源码：[`src/chronaxis/core/expression.py:133`](../../../src/chronaxis/core/expression.py#L133)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-contains_host_call"></a>
## `contains_host_call`

判定子树是否含宿主运行回调，以隔离静态常量参数检查。

```python
contains_host_call(root)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`root`|[ExprNode](chronaxis.core.expression.md#api-ExprNode)|是|无|位置或关键字。静态常量参数的候选子树；若含宿主调用，不在编译阶段运行该回调。|

### 返回说明

bool。

### 异常说明

内部不合法树传播属性错误。

源码：[`src/chronaxis/core/expression.py:148`](../../../src/chronaxis/core/expression.py#L148)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_node"></a>
## `_node`

从已验证子节点汇总局部依赖及单位状态。

```python
_node(operator, dtype, unit, args=(), **kwargs) -> ExprNode
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`operator`|str|是|无|位置或关键字。已由编译器确定的节点操作名，与ExprNode.operator使用同一含义。这个辅助函数把已检查的子节点组合起来，不负责接收或验证用户自由输入的操作名。|
|`dtype`|[SignalDType](chronaxis.core.types.md#api-SignalDType)|是|无|位置或关键字。此节点的结果类型，传SignalDType枚举成员；由编译器根据操作及子节点确定。|
|`unit`|str|是|无|位置或关键字。此节点结果的单位，例如W；由编译器先检查运算关系。|
|`args`|tuple[[ExprNode](chronaxis.core.expression.md#api-ExprNode), ...]|否|()|位置或关键字。按运算顺序排列的子节点。二元运算依次为左、右；isclose依次保存两个待比较值和两项容差。|
|`kwargs`|dict[str, object]|否|{}|可变关键字。转交ExprNode的额外构造字段，如value、name、labels、allow_float_literal；这些字段的类型和用途见[ExprNode](chronaxis.core.expression.md#api-ExprNode)。|

### 返回说明

冻结ExprNode；不进行样本计算。

### 异常说明

内部参数冲突传播，配置由编译器先验证。

返回类型：[ExprNode](chronaxis.core.expression.md#api-ExprNode)。

源码：[`src/chronaxis/core/expression.py:164`](../../../src/chronaxis/core/expression.py#L164)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_SyntaxCompiler"></a>
## `_SyntaxCompiler`

在一次编译中检查名称、语法、单位与派生依赖。

signals和derived来自当前绑定，不读取数据来源。消息域另有显式参数表，
参数按const执行但保constant=False，不随对方改变单位。nodes仅在本实例
内复用已编译的派生树；visiting记录当前递归路径，用于指出循环依赖。
根表达式的declared_unit可给未知组合提供显式标签，但不证明该量纲正确。
状态不跨编译调用共享，不缓存信号值，也不扩大受限表达式语法。

```python
_SyntaxCompiler(bindings, derived)
```


源码：[`src/chronaxis/core/expression.py:182`](../../../src/chronaxis/core/expression.py#L182)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_SyntaxCompiler-__init__"></a>
### `_SyntaxCompiler.__init__`

建立当前声明表并校验完整派生输入。

```python
_SyntaxCompiler.__init__(bindings, derived)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`bindings`|[MessageBindings](chronaxis.core.message_binding.md#api-MessageBindings) &#124; [MessageDeclarations](chronaxis.core.message_binding.md#api-MessageDeclarations) &#124; [SignalBindings](chronaxis.core.binding.md#api-SignalBindings) &#124; [DecodedBindings](chronaxis.core.decoded_binding.md#api-DecodedBindings) &#124; [DeclarationBindings](chronaxis.core.declarations.md#api-DeclarationBindings)|是|无|位置或关键字。bindings为明确带有明确类型的普通/消息运行绑定或各自静态声明|
|`derived`|tuple|是|无|位置或关键字。derived为tuple DerivedDefinition，数值执行仍由公开入口的类型门槛控制。|

#### 返回说明

None，仅局部解析状态。

#### 异常说明

TypeError/ValueError为类型/缺项/重复/名称空间不一致。

本函数直接报告的具体错误：

- `TypeError`：解析需要带有明确类型的真实/声明绑定及tuple DerivedDefinition。
- `ValueError`：derived声明与bindings名称不一致或重复。

源码：[`src/chronaxis/core/expression.py:192`](../../../src/chronaxis/core/expression.py#L192)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_SyntaxCompiler-_error"></a>
### `_SyntaxCompiler._error`

给出语法位置、拒绝原因与可用别名。

```python
_SyntaxCompiler._error(node, message)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`node`|ast.AST|是|无|位置或关键字。当前正在检查的Python表达式语法节点；保留行列位置，出错时可指出原表达式的具体位置。支持的语法见[表达式](../expressions.md)。|
|`message`|str|是|无|位置或关键字。向用户解释配置错误的文字；与node中的行列位置一起组成错误信息。|

#### 返回说明

不返回，抛ValueError。

#### 异常说明

ValueError定位行/列，不自动点号改名。

源码：[`src/chronaxis/core/expression.py:224`](../../../src/chronaxis/core/expression.py#L224)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_SyntaxCompiler-parse"></a>
### `_SyntaxCompiler.parse`

解析一个表达式并验证根结果单位/枚举域。

```python
_SyntaxCompiler.parse(text, unit=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`text`|str|是|无|位置或关键字。text为非空DSL|
|`unit`|str &#124; None|否|None|位置或关键字。unit为可选显式结果单位。|

#### 返回说明

带有明确类型的 ExprNode和规范AST。

#### 异常说明

ValueError为语法/白名单/类型/单位/环；不吞I/O异常。

源码：[`src/chronaxis/core/expression.py:234`](../../../src/chronaxis/core/expression.py#L234)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_SyntaxCompiler-_final_unit"></a>
### `_SyntaxCompiler._final_unit`

执行当前版本的根结果单位要求。

```python
_SyntaxCompiler._final_unit(root, unit, node)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`root`|[ExprNode](chronaxis.core.expression.md#api-ExprNode)|是|无|位置或关键字。当前已编译表达式子树的根，包含静态类型、操作和依赖。|
|`unit`|str &#124; None|是|无|位置或关键字。用户明确要求的输出单位标签，省略时沿用此版本的默认表达式单位规则。|
|`node`|ast.AST|是|无|位置或关键字。原配置的表达式语法位置，用于报告当前步骤发现的编译错误。|

#### 返回说明

已核对未知单位标签的原节点。

#### 异常说明

ValueError为结果与声明单位不一致。

源码：[`src/chronaxis/core/expression.py:269`](../../../src/chronaxis/core/expression.py#L269)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_SyntaxCompiler-_name"></a>
### `_SyntaxCompiler._name`

解析真实别名、消息参数或本计划派生，并拒绝环/未知名称。

```python
_SyntaxCompiler._name(node)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`node`|ast.AST|是|无|位置或关键字。当前正在检查的Python表达式语法节点；保留行列位置，出错时可指出原表达式的具体位置。支持的语法见[表达式](../expressions.md)。|

#### 返回说明

已绑定name节点或已编译派生树。

#### 异常说明

ValueError为未知别名/环/派生表达式错误。

源码：[`src/chronaxis/core/expression.py:281`](../../../src/chronaxis/core/expression.py#L281)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_SyntaxCompiler-_context"></a>
### `_SyntaxCompiler._context`

把纯数字/enum常量按另一侧明确类型及单位校验。

```python
_SyntaxCompiler._context(literal, other, node, *, arithmetic)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`literal`|[ExprNode](chronaxis.core.expression.md#api-ExprNode)|是|无|位置或关键字。纯常量子树，用来检查常量在当前比较或运算中的类型和单位。|
|`other`|[ExprNode](chronaxis.core.expression.md#api-ExprNode)|是|无|位置或关键字。与常量进行运算的另一棵表达式子树，提供其已知类型和单位。|
|`node`|ast.AST|是|无|位置或关键字。当前正在检查的Python表达式语法节点；保留行列位置，出错时可指出原表达式的具体位置。支持的语法见[表达式](../expressions.md)。|
|`arithmetic`|int|是|无|仅关键字。arithmetic     表示算术字面量必须能在目标整数类型表示。|

#### 返回说明

合法常量子树；含浮点常量的整型运算保持float路径。

#### 异常说明

ValueError为字面量类型/定宽/枚举域冲突。

源码：[`src/chronaxis/core/expression.py:326`](../../../src/chronaxis/core/expression.py#L326)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_SyntaxCompiler-_units"></a>
### `_SyntaxCompiler._units`

按首版表推断单位，裸常量加减/比较采用对方单位。

```python
_SyntaxCompiler._units(operator, left, right, node, declared_unit=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`operator`|str|是|无|位置或关键字。单位推导使用的运算类别：`add`相加、`sub`相减、`compare`比较、`mul`相乘、`div`相除。比较类别还用于isclose的两个被比较值。|
|`left`|[ExprNode](chronaxis.core.expression.md#api-ExprNode)|是|无|位置或关键字。已经静态检查的左操作数ExprNode。|
|`right`|[ExprNode](chronaxis.core.expression.md#api-ExprNode)|是|无|位置或关键字。已经静态检查的右操作数ExprNode。|
|`node`|ast.AST|是|无|位置或关键字。当前正在检查的Python表达式语法节点；保留行列位置，出错时可指出原表达式的具体位置。支持的语法见[表达式](../expressions.md)。|
|`declared_unit`|str &#124; None|否|None|位置或关键字。表达式根节点声明的结果单位；None表示未额外提供标签。声明单位不负责自动改变输入数值或把错误量纲改正确。|

#### 返回说明

上下文单位子树及输出单位。

#### 异常说明

ValueError为未转换单位或未支持组合。

源码：[`src/chronaxis/core/expression.py:375`](../../../src/chronaxis/core/expression.py#L375)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_SyntaxCompiler-_binary"></a>
### `_SyntaxCompiler._binary`

静态编译数值/比较，整数常量比较保留精确边界。

```python
_SyntaxCompiler._binary(operator, left, right, node, declared_unit=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`operator`|str|是|无|位置或关键字。本入口支持`add`相加、`sub`相减、`mul`相乘、`div`相除，以及`eq`等于、`ne`不等于、`lt`小于、`le`小于或等于、`gt`大于、`ge`大于或等于。填写这些内部名称，不填写符号或任意函数名。|
|`left`|[ExprNode](chronaxis.core.expression.md#api-ExprNode)|是|无|位置或关键字。已经静态检查的左操作数ExprNode。|
|`right`|[ExprNode](chronaxis.core.expression.md#api-ExprNode)|是|无|位置或关键字。已经静态检查的右操作数ExprNode。|
|`node`|ast.AST|是|无|位置或关键字。当前正在检查的Python表达式语法节点；保留行列位置，出错时可指出原表达式的具体位置。支持的语法见[表达式](../expressions.md)。|
|`declared_unit`|str &#124; None|否|None|位置或关键字。表达式根节点声明的结果单位；None表示未额外提供标签。声明单位不负责自动改变输入数值或把错误量纲改正确。|

#### 返回说明

带有明确类型的 ExprNode；绝不运行用户代码。

#### 异常说明

ValueError为单位/类型/常量配置错误。

源码：[`src/chronaxis/core/expression.py:413`](../../../src/chronaxis/core/expression.py#L413)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_SyntaxCompiler-visit"></a>
### `_SyntaxCompiler.visit`

逐AST节点执行首版白名单，不递归放行未知语法。

```python
_SyntaxCompiler.visit(node, declared_unit=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`node`|ast.AST|是|无|位置或关键字。当前正在检查的Python表达式语法节点；保留行列位置，出错时可指出原表达式的具体位置。支持的语法见[表达式](../expressions.md)。|
|`declared_unit`|str &#124; None|否|None|位置或关键字。表达式根节点声明的结果单位；None表示未额外提供标签。声明单位不负责自动改变输入数值或把错误量纲改正确。|

#### 返回说明

完整带有明确类型的内部节点。

#### 异常说明

ValueError定位未注册语法/函数/类型/单位。

源码：[`src/chronaxis/core/expression.py:475`](../../../src/chronaxis/core/expression.py#L475)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-compile_expression"></a>
## `compile_expression`

检查表达式及全部派生声明，关联当前真实输入绑定。

```python
compile_expression(text: str, bindings: SignalBindings | DecodedBindings | MessageBindings, *, derived: tuple[DerivedDefinition, ...]=(), unit: str | None=None, config_version: int | None=None, extensions=None) -> CompiledExpression
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`text`|str|是|无|位置或关键字。非空文本；bindings为真实SignalBindings、DecodedBindings或MessageBindings。|
|`bindings`|[SignalBindings](chronaxis.core.binding.md#api-SignalBindings) &#124; [DecodedBindings](chronaxis.core.decoded_binding.md#api-DecodedBindings) &#124; [MessageBindings](chronaxis.core.message_binding.md#api-MessageBindings)|是|无|位置或关键字。bindings为真实SignalBindings、DecodedBindings或MessageBindings。     derived: 完整且不可变的DerivedDefinition元组，需与已登记名称一致。     unit: 可选结果单位|
|`derived`|tuple[[DerivedDefinition](chronaxis.core.expression.md#api-DerivedDefinition), ...]|否|()|仅关键字。完整且不可变的DerivedDefinition元组，需与已登记名称一致。|
|`unit`|str &#124; None|否|None|仅关键字。可选结果单位；兼容登记单位同时转换数值。config_version省略时继承绑定。|
|`config_version`|int &#124; None|否|None|仅关键字。兼容登记单位同时转换数值。config_version省略时继承绑定。     extensions: 可选的宿主ExtensionRegistry，省略时使用绑定已经关联的注册。|
|`extensions`|None|否|None|仅关键字。此版本预留的编译参数，必须保持 None，非空对象在编译前被拒绝。|

### 返回说明

CompiledExpression，保存表达式树、实际依赖别名和完整绑定身份。

### 异常说明

TypeError、ValueError: 输入结构、语法、名称、类型、单位、循环依赖
    或多来源同步依据不满足要求。

本函数直接报告的具体错误：

- `TypeError`：可执行编译需要真实SignalBindings、DecodedBindings或MessageBindings。

### 流程说明

每次新建编译状态，先检查所有派生声明，再编译根表达式与同步依赖。
    此时不计算数值，也不读取日志或加载DBC；数值精度失败由求值器报告。

返回类型：[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)。

源码：[`src/chronaxis/core/expression.py:606`](../../../src/chronaxis/core/expression.py#L606)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-validate_expression"></a>
## `validate_expression`

只根据来源声明检查表达式，不读取真实输入。

```python
validate_expression(text: str, bindings: DeclarationBindings | MessageDeclarations, *, derived: tuple[DerivedDefinition, ...]=(), unit: str | None=None, config_version: int | None=None, extensions=None) -> StaticExpression
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`text`|str|是|无|位置或关键字。非空表达式文本；bindings为DeclarationBindings或MessageDeclarations。|
|`bindings`|[DeclarationBindings](chronaxis.core.declarations.md#api-DeclarationBindings) &#124; [MessageDeclarations](chronaxis.core.message_binding.md#api-MessageDeclarations)|是|无|位置或关键字。bindings为DeclarationBindings或MessageDeclarations。     derived: 完整DerivedDefinition元组|
|`derived`|tuple[[DerivedDefinition](chronaxis.core.expression.md#api-DerivedDefinition), ...]|否|()|仅关键字。完整DerivedDefinition元组；unit为可选显式结果单位。|
|`unit`|str &#124; None|否|None|仅关键字。unit为可选显式结果单位。     config_version: 省略时继承绑定|
|`config_version`|int &#124; None|否|None|仅关键字。省略时继承绑定；extensions为可选宿主注册，不运行回调。|
|`extensions`|None|否|None|仅关键字。此版本预留的编译参数，必须保持 None，非空对象在编译前被拒绝。|

### 返回说明

StaticExpression，说明名称、语法、类型、单位和同步声明已检查。
    该类型不能交给数值解释器执行，也不证明实际字段或数据内容已核实。

### 异常说明

TypeError、ValueError: 声明结构、语法、名称、单位、循环依赖或同步缺项。

本函数直接报告的具体错误：

- `TypeError`：静态校验需要DeclarationBindings或MessageDeclarations。

### 边界说明

未被根引用的派生表达式也要检查；读取真实输入后需要重新建立运行绑定。

返回类型：[StaticExpression](chronaxis.core.expression.md#api-StaticExpression)。

源码：[`src/chronaxis/core/expression.py:643`](../../../src/chronaxis/core/expression.py#L643)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_create_compiler"></a>
## `_create_compiler`

构造当前编译器，拒绝用参数重解释绑定版本。

```python
_create_compiler(bindings, derived, *, config_version=None, extensions=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`bindings`|[SignalBindings](chronaxis.core.binding.md#api-SignalBindings) &#124; [DecodedBindings](chronaxis.core.decoded_binding.md#api-DecodedBindings) &#124; [MessageBindings](chronaxis.core.message_binding.md#api-MessageBindings) &#124; [DeclarationBindings](chronaxis.core.declarations.md#api-DeclarationBindings) &#124; [MessageDeclarations](chronaxis.core.message_binding.md#api-MessageDeclarations)|是|无|位置或关键字。本次编译所用绑定容器，提供名称、输入类型与单位。运行绑定和纯声明保持各自身份。|
|`derived`|tuple[[DerivedDefinition](chronaxis.core.expression.md#api-DerivedDefinition), ...]|是|无|位置或关键字。参与本次编译的派生定义，包含名称、表达式和可选输出单位。|
|`config_version`|int &#124; None|否|None|仅关键字。显式版本必须与绑定一致；省略时使用绑定记录的版本。|
|`extensions`|None|否|None|仅关键字。此版本预留的编译参数，必须保持 None，非空对象在编译前被拒绝。|

### 返回说明

当前任务独享的编译器实例。

### 异常说明

TypeError/ValueError为版本类型、冲突或尚未支持的扩展对象。

源码：[`src/chronaxis/core/expression.py:678`](../../../src/chronaxis/core/expression.py#L678)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-expression_identity"></a>
## `expression_identity`

共用公开与按需重编译的身份公式，防止版本接线遗漏。

```python
expression_identity(bindings, root, normalized, derived, *, static=False, extensions=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`bindings`|[SignalBindings](chronaxis.core.binding.md#api-SignalBindings) &#124; [DecodedBindings](chronaxis.core.decoded_binding.md#api-DecodedBindings) &#124; [MessageBindings](chronaxis.core.message_binding.md#api-MessageBindings) &#124; [DeclarationBindings](chronaxis.core.declarations.md#api-DeclarationBindings) &#124; [MessageDeclarations](chronaxis.core.message_binding.md#api-MessageDeclarations)|是|无|位置或关键字。本次编译所用绑定容器，提供名称、输入类型与单位。运行绑定和纯声明保持各自身份。|
|`root`|[ExprNode](chronaxis.core.expression.md#api-ExprNode)|是|无|位置或关键字。当前已编译表达式子树的根，包含静态类型、操作和依赖。|
|`normalized`|str|是|无|位置或关键字。解析后的规范 AST 文本，用于生成可复现的表达式身份。|
|`derived`|tuple[[DerivedDefinition](chronaxis.core.expression.md#api-DerivedDefinition), ...]|是|无|位置或关键字。参与本次编译的派生定义，包含名称、表达式和可选输出单位。|
|`static`|bool|否|False|仅关键字。static区分静态域。|
|`extensions`|[ExtensionRegistry](chronaxis.extensions.md#api-ExtensionRegistry) &#124; None|否|None|仅关键字。可执行或静态表达式所用的宿主注册；注册的名称、版本、端口和后端能力摘要参与身份计算。|

### 返回说明

SHA256文本，包含当前单位和函数规则版本。

### 异常说明

内部类型错误直接传播，不读取文件。

源码：[`src/chronaxis/core/expression.py:704`](../../../src/chronaxis/core/expression.py#L704)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
