# `chronaxis.core.extension_points`

把宿主已经明确注册的纯函数调用编译进白名单表达式树。

固定参数及其声明尺度由FunctionSpec提供。此层只检查类型、解释裸常量并
编译必要的单位转换；静态编译从不实例化宿主状态或执行用户的逐点回调。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)、[ExprNode](chronaxis.core.expression.md#api-ExprNode)

## 对象导航

|对象|用途|
|---|---|
|[`compile_host_function`](#api-compile_host_function)|检查固定位置端口，将显式可信实现绑定到当前不可变树。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import replace
from .expression import _node, ExprNode
from .expression_math_v4 import check_integer_leaves
from .numeric import INTEGER_BOUNDS
from .types import SignalDType as D
```

</details>

<a id="api-compile_host_function"></a>
## `compile_host_function`

检查固定位置端口，将显式可信实现绑定到当前不可变树。

```python
compile_host_function(compiler, call, spec)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiler`|UnitCompiler|是|无|位置或关键字。本次v4编译器，负责检查每个AST参数、单位换算和常量适配。|
|`call`|ast.Call|是|无|位置或关键字。表达式里以注册名称调用函数的语法结点，实参必须按固定位置传入。|
|`spec`|FunctionSpec|是|无|位置或关键字。宿主函数的不可变注册，提供输入端口顺序、输出dtype/单位及该操作的实现。|

### 返回说明

带有明确类型的 ExprNode。

### 异常说明

ValueError为位置数量、类型、单位或整数字面量非法；不加载配置路径。

源码：[`src/chronaxis/core/extension_points.py:13`](../../../src/chronaxis/core/extension_points.py#L13)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
