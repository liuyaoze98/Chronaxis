# `chronaxis.core.expression_math_v4`

编译版本4的逐点极值、限幅、平方和开方表达式。

输入是白名单调用AST及本次编译器，输出是显式标记单位、dtype与依赖的
冻结节点。先检查完整输入，再按所有参数的原始声明尺度解释裸常量，
最后确定公共数值表示。仅对不依赖样本的clip边界执行静态判序。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)、[ExprNode](chronaxis.core.expression.md#api-ExprNode)

## 对象导航

|对象|用途|
|---|---|
|[`_common_unit`](#api-_common_unit)|将同量种的多个数值放到共同尺度，在换算前确定裸数字单位。|
|[`_common_dtype`](#api-_common_dtype)|对称选定可用于极值和限幅的公共dtype，明确记录必要的精确提升。|
|[`check_integer_leaves`](#api-check_integer_leaves)|检查实际需要定宽存储的叶节点，包括未选分支内的配置字面量。|
|[`compile_math`](#api-compile_math)|为一个已注册的数学函数检查签名、单位、类型和静态边界。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import replace
from . import unit_registry as units
from .expression import ExprNode, _node, contains_host_call
from .numeric import INTEGER_BOUNDS
from .types import SignalDType as D
```

</details>

<a id="api-_common_unit"></a>
## `_common_unit`

将同量种的多个数值放到共同尺度，在换算前确定裸数字单位。

```python
_common_unit(compiler, args, call)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiler`|UnitCompiler|是|无|位置或关键字。当前 v4 编译器实例，负责验证参数、统一单位及在原配置位置报告错误。|
|`args`|Sequence[[ExprNode](chronaxis.core.expression.md#api-ExprNode)]|是|无|位置或关键字。本次数学调用的已编译实参，按声明顺序校验量种、可表示性与可用的共同类型。|
|`call`|ast.Call|是|无|位置或关键字。当前函数调用的原始语法节点，提供参数和关键字，并用于定位配置错误。|

### 返回说明

同单位节点tuple，已知单位取规范基准，未知同名保留原标签。

### 异常说明

ValueError为量种不兼容、未知单位异名或裸数字有多种尺度解释。

源码：[`src/chronaxis/core/expression_math_v4.py:19`](../../../src/chronaxis/core/expression_math_v4.py#L19)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_common_dtype"></a>
## `_common_dtype`

对称选定可用于极值和限幅的公共dtype，明确记录必要的精确提升。

```python
_common_dtype(compiler, args, call)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiler`|UnitCompiler|是|无|位置或关键字。当前 v4 编译器实例，负责验证参数、统一单位及在原配置位置报告错误。|
|`args`|Sequence[[ExprNode](chronaxis.core.expression.md#api-ExprNode)]|是|无|位置或关键字。本次数学调用的已编译实参，按声明顺序校验量种、可表示性与可用的共同类型。|
|`call`|ast.Call|是|无|位置或关键字。当前函数调用的原始语法节点，提供参数和关键字，并用于定位配置错误。|

### 返回说明

逐一适配后的节点tuple；所有节点dtype相同。

### 异常说明

ValueError为原信号类型冲突、定宽字面量越界或不允许的提升。

源码：[`src/chronaxis/core/expression_math_v4.py:53`](../../../src/chronaxis/core/expression_math_v4.py#L53)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-check_integer_leaves"></a>
## `check_integer_leaves`

检查实际需要定宽存储的叶节点，包括未选分支内的配置字面量。

```python
check_integer_leaves(compiler, args, call)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiler`|UnitCompiler|是|无|位置或关键字。当前 v4 编译器实例，负责验证参数、统一单位及在原配置位置报告错误。|
|`args`|Sequence[[ExprNode](chronaxis.core.expression.md#api-ExprNode)]|是|无|位置或关键字。本次数学调用的已编译实参，按声明顺序校验量种、可表示性与可用的共同类型。|
|`call`|ast.Call|是|无|位置或关键字。当前函数调用的原始语法节点，提供参数和关键字，并用于定位配置错误。|

### 返回说明

None。

### 异常说明

ValueError为叶节点定宽越界。

源码：[`src/chronaxis/core/expression_math_v4.py:85`](../../../src/chronaxis/core/expression_math_v4.py#L85)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-compile_math"></a>
## `compile_math`

为一个已注册的数学函数检查签名、单位、类型和静态边界。

```python
compile_math(compiler, call)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiler`|UnitCompiler|是|无|位置或关键字。当前 v4 编译器实例，负责验证参数、统一单位及在原配置位置报告错误。|
|`call`|ast.Call|是|无|位置或关键字。当前函数调用的原始语法节点，提供参数和关键字，并用于定位配置错误。|

### 返回说明

ExprNode；平方直接复用经过定宽溢出检查的乘法节点。

### 异常说明

ValueError为非法参数、越界常量、不可推导的单位或静态倒置边界。

源码：[`src/chronaxis/core/expression_math_v4.py:104`](../../../src/chronaxis/core/expression_math_v4.py#L104)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
