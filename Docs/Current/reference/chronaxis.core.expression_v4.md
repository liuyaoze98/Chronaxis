# `chronaxis.core.expression_v4`

为版本4表达式编译一次性单位转换，统一处理当前单位与函数规则。

输入为已校验绑定和AST，输出包含unit_convert节点的不可变表达式树。
先解释裸常量的单位，再统一兼容量的尺度，最后推导结果单位及数值类型。
编译只使用声明与常量。clip的两个边界均无信号依赖时，标量核在此判定
其顺序；编译器不读取日志或求样本值。
温度偏移、量种和整数精度规则不能通过只改单位标签绕过。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)、[ExprNode](chronaxis.core.expression.md#api-ExprNode)、[_SyntaxCompiler](chronaxis.core.expression.md#api-_SyntaxCompiler)

## 对象导航

|对象|用途|
|---|---|
|[`numeric_coefficient`](#api-numeric_coefficient)|将精确有理系数压为整数或float，供已选后端执行。|
|[`UnitCompiler`](#api-UnitCompiler)|在原受限语法上接入v4单位、常量和转换规则。|
|[`UnitCompiler.__init__`](#api-UnitCompiler-__init__)|建立绑定并检查本版本已经开放的函数名冲突。|
|[`UnitCompiler._known_node`](#api-UnitCompiler-_known_node)|按v4目录判定组合结果的单位状态，不提升未知输入的可信度。|
|[`UnitCompiler._name`](#api-UnitCompiler-_name)|取得信号/派生原声明尺度，附带已有输入转换的类型提升依据。|
|[`UnitCompiler._convert`](#api-UnitCompiler-_convert)|为兼容单位生成一次仿射转换，不重复应用源层的DBC或标定系数。|
|[`UnitCompiler._canonical`](#api-UnitCompiler-_canonical)|把已知数值换到该量种的固定基准，未知标签保持。|
|[`UnitCompiler._final_unit`](#api-UnitCompiler-_final_unit)|在表达式输出边界同时转换目标数值和标签。|
|[`UnitCompiler._context`](#api-UnitCompiler-_context)|复用定宽字面量检查，同时保持新单位的验证状态。|
|[`UnitCompiler._units`](#api-UnitCompiler-_units)|先解释裸常量，再按兼容量换算，独立处理温度加减。|
|[`UnitCompiler._binary`](#api-UnitCompiler-_binary)|复用原定宽编译规则，并按新目录确定结果单位状态。|
|[`UnitCompiler._where`](#api-UnitCompiler-_where)|编译只在条件已知时选取一条数值分支的节点。|
|[`UnitCompiler.visit`](#api-UnitCompiler-visit)|解析已登记的v4单位、选择与数学函数，其余受限语法沿原访问器。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import replace
from .expression import _SyntaxCompiler, ExprNode, _node
from .expression_math_v4 import MATH_FUNCTIONS, check_integer_leaves, compile_math
from .lookup_compiler import compile_lookup
from .expression_integer_v4 import INTEGER_FUNCTIONS, compile_integer
from .enum_codes import compile_enum_code
from .numeric import INTEGER_BOUNDS
from .types import SignalDType as D
from . import unit_registry as units
```

</details>

<a id="api-numeric_coefficient"></a>
## `numeric_coefficient`

将精确有理系数压为整数或float，供已选后端执行。

```python
numeric_coefficient(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|Fraction|是|无|位置或关键字。待转换的精确有理倍率或偏移，分母为一时保持原生整数。|

### 返回说明

分母为1时返回int，否则返回float。

### 异常说明

不能表示的浮点范围错误由调用者/倍率模型检查。

源码：[`src/chronaxis/core/expression_v4.py:23`](../../../src/chronaxis/core/expression_v4.py#L23)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-UnitCompiler"></a>
## `UnitCompiler`

在原受限语法上接入v4单位、常量和转换规则。

每次编译独享状态。声明单位在裸常量适配之前保留，转换只写入树一次；
数值执行根据节点系数转换，编译器不逐条处理数据。

```python
UnitCompiler(bindings, derived, extensions=None)
```

继承关系：[_SyntaxCompiler](chronaxis.core.expression.md#api-_SyntaxCompiler)。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/core/expression_v4.py:34`](../../../src/chronaxis/core/expression_v4.py#L34)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-UnitCompiler-__init__"></a>
### `UnitCompiler.__init__`

建立绑定并检查本版本已经开放的函数名冲突。

```python
UnitCompiler.__init__(bindings, derived, extensions=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`bindings`|SignalBindings &#124; DecodedBindings &#124; MessageBindings &#124; DeclarationBindings &#124; MessageDeclarations|是|无|位置或关键字。本次编译所用绑定容器，提供名称、输入类型与单位。运行绑定和纯声明保持各自身份。|
|`derived`|tuple[DerivedDefinition, ...]|是|无|位置或关键字。参与本次编译的派生定义，包含名称、表达式和可选输出单位。|
|`extensions`|ExtensionRegistry &#124; None|否|None|位置或关键字。当前绑定允许的宿主注册；编译器据此保留函数名并逐个检查显式输入端口。|

#### 返回说明

None。

#### 异常说明

ValueError为别名与本版本函数重名；其余声明错误沿原校验传播。

源码：[`src/chronaxis/core/expression_v4.py:41`](../../../src/chronaxis/core/expression_v4.py#L41)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-UnitCompiler-_known_node"></a>
### `UnitCompiler._known_node`

按v4目录判定组合结果的单位状态，不提升未知输入的可信度。

```python
UnitCompiler._known_node(result)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`result`|[ExprNode](chronaxis.core.expression.md#api-ExprNode)|是|无|位置或关键字。经过基类类型检查的表达式节点，补登记单位是否已知的状态。|

#### 返回说明

单位状态准确的新节点或原节点。

#### 异常说明

非法单位文本按编译错误传播。

源码：[`src/chronaxis/core/expression_v4.py:58`](../../../src/chronaxis/core/expression_v4.py#L58)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-UnitCompiler-_name"></a>
### `UnitCompiler._name`

取得信号/派生原声明尺度，附带已有输入转换的类型提升依据。

```python
UnitCompiler._name(node)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`node`|ast.Name|是|无|位置或关键字。含待解析别名的名称语法节点，通过当前绑定定位信号、参数或派生定义。|

#### 返回说明

已校验ExprNode。

#### 异常说明

名称/循环/声明错误沿原编译器传播。

源码：[`src/chronaxis/core/expression_v4.py:71`](../../../src/chronaxis/core/expression_v4.py#L71)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-UnitCompiler-_convert"></a>
### `UnitCompiler._convert`

为兼容单位生成一次仿射转换，不重复应用源层的DBC或标定系数。

```python
UnitCompiler._convert(child, target, node, *, explicit=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`child`|[ExprNode](chronaxis.core.expression.md#api-ExprNode)|是|无|位置或关键字。待适配尺度的已编译子表达式，其当前单位和类型决定需要何种换算。|
|`target`|str|是|无|位置或关键字。本次要转换到的注册单位标签，须与输入单位兼容。|
|`node`|ast.AST|是|无|位置或关键字。原配置的表达式语法位置，用于报告当前步骤发现的编译错误。|
|`explicit`|bool|否|False|仅关键字。explicit保留输出尺度。|

#### 返回说明

原节点或unit_convert节点，dtype在编译期确定。

#### 异常说明

ValueError为非数值转换、未知关系、量种不兼容或不可表示倍率。

源码：[`src/chronaxis/core/expression_v4.py:85`](../../../src/chronaxis/core/expression_v4.py#L85)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-UnitCompiler-_canonical"></a>
### `UnitCompiler._canonical`

把已知数值换到该量种的固定基准，未知标签保持。

```python
UnitCompiler._canonical(child, node)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`child`|[ExprNode](chronaxis.core.expression.md#api-ExprNode)|是|无|位置或关键字。待适配尺度的已编译子表达式，其当前单位和类型决定需要何种换算。|
|`node`|ast.AST|是|无|位置或关键字。原配置的表达式语法位置，用于报告当前步骤发现的编译错误。|

#### 返回说明

已转换节点；逻辑/枚举不作数值换算。

#### 异常说明

单位或转换边界错误传播。

源码：[`src/chronaxis/core/expression_v4.py:123`](../../../src/chronaxis/core/expression_v4.py#L123)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-UnitCompiler-_final_unit"></a>
### `UnitCompiler._final_unit`

在表达式输出边界同时转换目标数值和标签。

```python
UnitCompiler._final_unit(root, unit, node)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`root`|[ExprNode](chronaxis.core.expression.md#api-ExprNode)|是|无|位置或关键字。当前已编译表达式子树的根，包含静态类型、操作和依赖。|
|`unit`|str &#124; None|是|无|位置或关键字。用户明确要求的输出单位标签，省略时沿用此版本的默认表达式单位规则。|
|`node`|ast.AST|是|无|位置或关键字。原配置的表达式语法位置，用于报告当前步骤发现的编译错误。|

#### 返回说明

显式目标优先，否则用规范基准。

#### 异常说明

不兼容目标或未知转换明确报错。

源码：[`src/chronaxis/core/expression_v4.py:136`](../../../src/chronaxis/core/expression_v4.py#L136)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-UnitCompiler-_context"></a>
### `UnitCompiler._context`

复用定宽字面量检查，同时保持新单位的验证状态。

```python
UnitCompiler._context(literal, other, node, *, arithmetic)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`literal`|[ExprNode](chronaxis.core.expression.md#api-ExprNode)|是|无|位置或关键字。等待按上下文解释单位或整数类型的候选裸常量。|
|`other`|[ExprNode](chronaxis.core.expression.md#api-ExprNode)|是|无|位置或关键字。同一运算的另一侧节点，提供量种、尺度及类型基准。|
|`node`|ast.AST|是|无|位置或关键字。原配置的表达式语法位置，用于报告当前步骤发现的编译错误。|
|`arithmetic`|bool|是|无|仅关键字。当前适配是否用于算术运算，决定文字常量与对端类型的处理。|

#### 返回说明

按上下文检查过的节点。

#### 异常说明

类型、范围或枚举域错误沿原检查传播。

源码：[`src/chronaxis/core/expression_v4.py:148`](../../../src/chronaxis/core/expression_v4.py#L148)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-UnitCompiler-_units"></a>
### `UnitCompiler._units`

先解释裸常量，再按兼容量换算，独立处理温度加减。

```python
UnitCompiler._units(operator, left, right, node, declared_unit=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`operator`|str|是|无|位置或关键字。编译器归一化的二元操作名，如加减乘除或比较，决定单位关系和结果类型。|
|`left`|[ExprNode](chronaxis.core.expression.md#api-ExprNode)|是|无|位置或关键字。二元运算的左操作数，是差值和除法的被减数或分子。|
|`right`|[ExprNode](chronaxis.core.expression.md#api-ExprNode)|是|无|位置或关键字。二元运算的右操作数，是差值和除法的减数或分母。|
|`node`|ast.AST|是|无|位置或关键字。原配置的表达式语法位置，用于报告当前步骤发现的编译错误。|
|`declared_unit`|str &#124; None|否|None|位置或关键字。表达式上层声明的可选结果单位，按该算子的版本化单位规则校验。|

#### 返回说明

已转换左右节点与结果单位。

#### 异常说明

ValueError为不兼容量种、温度组合或未登记关系。

源码：[`src/chronaxis/core/expression_v4.py:164`](../../../src/chronaxis/core/expression_v4.py#L164)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-UnitCompiler-_binary"></a>
### `UnitCompiler._binary`

复用原定宽编译规则，并按新目录确定结果单位状态。

```python
UnitCompiler._binary(operator, left, right, node, declared_unit=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`operator`|str|是|无|位置或关键字。编译器归一化的二元操作名，如加减乘除或比较，决定单位关系和结果类型。|
|`left`|[ExprNode](chronaxis.core.expression.md#api-ExprNode)|是|无|位置或关键字。二元运算的左操作数，是差值和除法的被减数或分子。|
|`right`|[ExprNode](chronaxis.core.expression.md#api-ExprNode)|是|无|位置或关键字。二元运算的右操作数，是差值和除法的减数或分母。|
|`node`|ast.AST|是|无|位置或关键字。原配置的表达式语法位置，用于报告当前步骤发现的编译错误。|
|`declared_unit`|str &#124; None|否|None|位置或关键字。表达式上层声明的可选结果单位，按该算子的版本化单位规则校验。|

#### 返回说明

不可变数值/比较节点。

#### 异常说明

原类型校验和新单位校验错误直接传播。

源码：[`src/chronaxis/core/expression_v4.py:201`](../../../src/chronaxis/core/expression_v4.py#L201)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-UnitCompiler-_where"></a>
### `UnitCompiler._where`

编译只在条件已知时选取一条数值分支的节点。

```python
UnitCompiler._where(node)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`node`|ast.Call|是|无|位置或关键字。where 的原始调用，包含一个布尔条件和两个数值分支。|

#### 返回说明

包含完整依赖的节点，两条分支已统一单位和dtype。

#### 异常说明

ValueError为签名、非布尔条件、类型/量种不兼容或字面量越界。

源码：[`src/chronaxis/core/expression_v4.py:211`](../../../src/chronaxis/core/expression_v4.py#L211)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-UnitCompiler-visit"></a>
### `UnitCompiler.visit`

解析已登记的v4单位、选择与数学函数，其余受限语法沿原访问器。

```python
UnitCompiler.visit(node, declared_unit=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`node`|ast.AST|是|无|位置或关键字。待递归编译的当前语法节点，只接受已登记的表达式结构和函数。|
|`declared_unit`|str &#124; None|否|None|位置或关键字。上层声明的输出单位标签，缺省由该节点的运算和类型推导。|

#### 返回说明

已检查类型、单位和依赖的表达式节点。

#### 异常说明

ValueError为签名、非字面量单位、非法数值或未知函数。

源码：[`src/chronaxis/core/expression_v4.py:253`](../../../src/chronaxis/core/expression_v4.py#L253)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
