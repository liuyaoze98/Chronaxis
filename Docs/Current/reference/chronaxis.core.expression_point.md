# `chronaxis.core.expression_point`

为流式状态上的一个时刻准备独立生产求值，不装箱成单元素数组。

PointProgram只持有当前表达式的只读节点、常量和查表视图。每次求值的缓存
由调用者创建和释放，不能跨点复用数值。内建操作由numeric_point独立计算；
reference和真正批量NumPy入口不变。宿主扩展保留所选NumPy回调和列接口，
只在该边界产生必要的单元素列，未选分支不调用宿主。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)、[Evaluation](chronaxis.core.expression_reference.md#api-Evaluation)、[ExprNode](chronaxis.core.expression.md#api-ExprNode)、[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)

## 对象导航

|对象|用途|
|---|---|
|[`_column`](#api-_column)|仅为NumPy宿主边界装一条列。|
|[`_scalar`](#api-_scalar)|从宿主返回列恢复第一个值。|
|[`PointProgram`](#api-PointProgram)|持有单个已核表达式的准备数据，不拥有输入状态或跨点值缓存。|
|[`PointProgram.__init__`](#api-PointProgram-__init__)|一次准备常量、节点索引和所需查表。|
|[`PointProgram.used_names`](#api-PointProgram-used_names)|遍历本点实际访问的别名。|
|[`PointProgram.evaluate`](#api-PointProgram-evaluate)|求根节点。|
|[`PointProgram._evaluate`](#api-PointProgram-_evaluate)|解释一个活动子树，身份缓存只属于本次点。|
|[`PointProgram.updates`](#api-PointProgram-updates)|按活动分支判断原子组是否产生更新，不用数值相等替代更新证据。|
|[`PointProgram.updates.changed`](#api-PointProgram-updates-changed)|检查子树的活动更新。|
|[`PointProgram.active`](#api-PointProgram-active)|判断被标记的依赖是否活动。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .expression import ExprNode
from .expression_reference import Evaluation
from .expression_integer_v4 import INTEGER_KERNELS
from .expression_math_v4 import MATH_KERNELS
from .numeric import result_dtype
from .numeric_point import _COMPARE, affine_point, binary_point, failed, integer_point, logic_point, lookup_point, math_point, to_float_point, unary_point
from .scalar import ScalarValue
from .types import QualityFlag as Q, SignalDType as D, _QUALITY_BY_MASK
```

</details>

<a id="api-_column"></a>
## `_column`

仅为NumPy宿主边界装一条列。

```python
_column(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|[chronaxis.core.scalar.ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)|是|无|位置或关键字。仅在 NumPy 宿主回调边界装为一行列的标量；枚举标签和原码一并保留。|

### 返回说明

NumericArray。

### 异常说明

原列模型错误。

源码：[`src/chronaxis/core/expression_point.py:21`](../../../src/chronaxis/core/expression_point.py#L21)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_scalar"></a>
## `_scalar`

从宿主返回列恢复第一个值。

```python
_scalar(column)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`column`|[chronaxis.core.numeric_numpy.NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)|是|无|位置或关键字。宿主回调返回且已经检查为单行的列，读取第一行并保留质量、标签及原码。|

### 返回说明

ScalarValue。

### 异常说明

原模型错误。

源码：[`src/chronaxis/core/expression_point.py:33`](../../../src/chronaxis/core/expression_point.py#L33)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-PointProgram"></a>
## `PointProgram`

持有单个已核表达式的准备数据，不拥有输入状态或跨点值缓存。

构造费用由DriverExpression的固定预算预付；查表只持有打包数据的只读视图。
实例使用期间表达式和注册保持冻结，调用者在关闭时释放整个实例。

```python
PointProgram(root)
```


源码：[`src/chronaxis/core/expression_point.py:41`](../../../src/chronaxis/core/expression_point.py#L41)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-PointProgram-__init__"></a>
### `PointProgram.__init__`

一次准备常量、节点索引和所需查表。

```python
PointProgram.__init__(root)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`root`|[chronaxis.core.expression.ExprNode](chronaxis.core.expression.md#api-ExprNode)|是|无|位置或关键字。已完成绑定、类型和单位检查的根节点；准备数据仅属于这一棵表达式。|

#### 返回说明

新准备对象。

#### 异常说明

内部未支持节点、结构或分配错误；不执行任何宿主回调。

源码：[`src/chronaxis/core/expression_point.py:48`](../../../src/chronaxis/core/expression_point.py#L48)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-PointProgram-used_names"></a>
### `PointProgram.used_names`

遍历本点实际访问的别名。

```python
PointProgram.used_names(cache)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`cache`|dict[int, [chronaxis.core.expression_reference.Evaluation](chronaxis.core.expression_reference.md#api-Evaluation)]|是|无|位置或关键字。本次点已访问节点的求值缓存，只枚举其中实际访问过的信号别名。|

#### 返回说明

名称迭代器。

#### 异常说明

非法缓存键。

源码：[`src/chronaxis/core/expression_point.py:92`](../../../src/chronaxis/core/expression_point.py#L92)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-PointProgram-evaluate"></a>
### `PointProgram.evaluate`

求根节点。

```python
PointProgram.evaluate(context, cache)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`context`|Mapping[str, [chronaxis.core.scalar.ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)]|是|无|位置或关键字。本次点的别名到规范标量映射，包含当前表达式实际需要的输入。|
|`cache`|dict[int, [chronaxis.core.expression_reference.Evaluation](chronaxis.core.expression_reference.md#api-Evaluation)]|是|无|位置或关键字。本程序本次点的节点身份到 Evaluation 缓存；由调用方创建，初始为空，不跨点或程序复用。|

#### 返回说明

Evaluation。

#### 异常说明

计算/宿主错误。

源码：[`src/chronaxis/core/expression_point.py:98`](../../../src/chronaxis/core/expression_point.py#L98)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-PointProgram-_evaluate"></a>
### `PointProgram._evaluate`

解释一个活动子树，身份缓存只属于本次点。

```python
PointProgram._evaluate(node, context, cache)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`node`|[chronaxis.core.expression.ExprNode](chronaxis.core.expression.md#api-ExprNode)|是|无|位置或关键字。属于当前准备对象的活动子树节点。|
|`context`|Mapping[str, [chronaxis.core.scalar.ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)]|是|无|位置或关键字。本次点的规范标量映射；缺少被访问的别名会传播 KeyError。|
|`cache`|dict[int, [chronaxis.core.expression_reference.Evaluation](chronaxis.core.expression_reference.md#api-Evaluation)]|是|无|位置或关键字。本程序本次点的节点身份到 Evaluation 缓存；由调用方创建，初始为空，不跨点或程序复用。|

#### 返回说明

Evaluation。

#### 异常说明

内部节点/输入合同错误及宿主发生异常时直接交给调用者处理。

源码：[`src/chronaxis/core/expression_point.py:102`](../../../src/chronaxis/core/expression_point.py#L102)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-PointProgram-updates"></a>
### `PointProgram.updates`

按活动分支判断原子组是否产生更新，不用数值相等替代更新证据。

```python
PointProgram.updates(root, current, before, updates)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`root`|[chronaxis.core.expression.ExprNode](chronaxis.core.expression.md#api-ExprNode)|是|无|位置或关键字。当前准备对象中要检查更新性的子树。|
|`current`|Mapping[str, [chronaxis.core.scalar.ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)]|是|无|位置或关键字。原子组提交后的当前规范标量映射。|
|`before`|Mapping[str, [chronaxis.core.scalar.ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)] &#124; None|是|无|位置或关键字。提交前映射；None 表示只检查活动依赖，不比较条件前后变化。|
|`updates`|Mapping[str, bool]|是|无|位置或关键字。本组各别名是否真实更新的标志，不用新旧数值相等替代更新证据。|

#### 返回说明

bool。

#### 异常说明

条件求值或内部节点错误。

源码：[`src/chronaxis/core/expression_point.py:179`](../../../src/chronaxis/core/expression_point.py#L179)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-PointProgram-updates-changed"></a>
### `PointProgram.updates.changed`

检查子树的活动更新。

```python
PointProgram.updates.changed(node)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`node`|[chronaxis.core.expression.ExprNode](chronaxis.core.expression.md#api-ExprNode)|是|无|位置或关键字。当前准备对象中的子树，根据活动分支递归判断更新。|

#### 返回说明

bool。

#### 异常说明

原条件求值错误。

源码：[`src/chronaxis/core/expression_point.py:187`](../../../src/chronaxis/core/expression_point.py#L187)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-PointProgram-active"></a>
### `PointProgram.active`

判断被标记的依赖是否活动。

```python
PointProgram.active(root, context, flags)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`root`|[chronaxis.core.expression.ExprNode](chronaxis.core.expression.md#api-ExprNode)|是|无|位置或关键字。当前准备对象中要检查活动性的子树。|
|`context`|Mapping[str, [chronaxis.core.scalar.ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)]|是|无|位置或关键字。当前规范标量映射，用于确定 where 实际选择的分支。|
|`flags`|Mapping[str, bool]|是|无|位置或关键字。各输入别名是否属于本次待检查集合的标志。|

#### 返回说明

bool。

#### 异常说明

条件错误。

源码：[`src/chronaxis/core/expression_point.py:214`](../../../src/chronaxis/core/expression_point.py#L214)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
