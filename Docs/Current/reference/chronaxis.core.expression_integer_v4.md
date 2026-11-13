# `chronaxis.core.expression_integer_v4`

将版本4整数编码、位选取和显式数值类型转换编译为冻结节点。

mod及位操作在单位为1的64位整数域工作，位号在编译时校验并固化。
显式cast先确定输入的物理尺度，再选择结果dtype。编译只访问声明与纯常量，
逐点的溢出、域错误和精度失败交给各自的参考/数组内核处理。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)、[ExprNode](chronaxis.core.expression.md#api-ExprNode)

## 对象导航

|对象|用途|
|---|---|
|[`_require_word`](#api-_require_word)|核对64位整数及数值尺度1，可接受等价的无量纲单位表达式。|
|[`_bit_parameter`](#api-_bit_parameter)|读取可在编译期确定的无量纲整数，位置与宽度边界由调用处统一判定。|
|[`compile_integer`](#api-compile_integer)|编译mod、位操作或精确cast，冻结整数策略与编译期位参数。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import replace
from . import unit_registry as units
from .expression import _node, ExprNode, contains_host_call
from .expression_math_v4 import check_integer_leaves
from .numeric import INTEGER_BOUNDS
from .types import SignalDType as D
```

</details>

<a id="api-_require_word"></a>
## `_require_word`

核对64位整数及数值尺度1，可接受等价的无量纲单位表达式。

```python
_require_word(compiler, child, call)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiler`|UnitCompiler|是|无|位置或关键字。当前 v4 编译器实例，负责验证参数、统一单位及在原配置位置报告错误。|
|`child`|[ExprNode](chronaxis.core.expression.md#api-ExprNode)|是|无|位置或关键字。待验证的运算数，应是量纲一且倍率为一的定宽整数表达式。|
|`call`|ast.Call|是|无|位置或关键字。当前函数调用的原始语法节点，提供参数和关键字，并用于定位配置错误。|

### 返回说明

None。

### 异常说明

ValueError为非整数、未知单位、带物理单位或非1倍率。

源码：[`src/chronaxis/core/expression_integer_v4.py:21`](../../../src/chronaxis/core/expression_integer_v4.py#L21)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_bit_parameter"></a>
## `_bit_parameter`

读取可在编译期确定的无量纲整数，位置与宽度边界由调用处统一判定。

```python
_bit_parameter(compiler, child, call)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiler`|UnitCompiler|是|无|位置或关键字。当前 v4 编译器实例，负责验证参数、统一单位及在原配置位置报告错误。|
|`child`|[ExprNode](chronaxis.core.expression.md#api-ExprNode)|是|无|位置或关键字。提供位号、起点或位宽的编译期常量整数节点，不能依赖运行数据。|
|`call`|ast.Call|是|无|位置或关键字。当前函数调用的原始语法节点，提供参数和关键字，并用于定位配置错误。|

### 返回说明

原生int。

### 异常说明

ValueError为依赖运行数据或静态数值本身无效。

源码：[`src/chronaxis/core/expression_integer_v4.py:34`](../../../src/chronaxis/core/expression_integer_v4.py#L34)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-compile_integer"></a>
## `compile_integer`

编译mod、位操作或精确cast，冻结整数策略与编译期位参数。

```python
compile_integer(compiler, call)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiler`|UnitCompiler|是|无|位置或关键字。当前 v4 编译器实例，负责验证参数、统一单位及在原配置位置报告错误。|
|`call`|ast.Call|是|无|位置或关键字。当前函数调用的原始语法节点，提供参数和关键字，并用于定位配置错误。|

### 返回说明

ExprNode；cast结果按所选尺度保持目标dtype，位索引不构造运行列。

### 异常说明

ValueError为签名、输入类型/单位、位参数、常量越界或隐式混合定宽。

源码：[`src/chronaxis/core/expression_integer_v4.py:51`](../../../src/chronaxis/core/expression_integer_v4.py#L51)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
