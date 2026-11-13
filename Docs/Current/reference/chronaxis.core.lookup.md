# `chronaxis.core.lookup`

校验 v4 一维标定表声明，并按已请求的插值方式生成只读计算表。

声明只保存配置点对和内容身份。被表达式引用时才将两列写为固定小端字节，
支持标量随机读取或 NumPy 零复制视图。无文件、全局缓存或第三方依赖。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)

## 对象导航

|对象|用途|
|---|---|
|[`_exact_f64`](#api-_exact_f64)|校验 float64 转换。|
|[`LookupTablePlan`](#api-LookupTablePlan)|保存经校验的有限标定点。身份保留原生数字类型、单位和每一点的次序。|
|[`LookupTablePlan.__post_init__`](#api-LookupTablePlan-__post_init__)|校验轴和阶梯输出的共同类型。|
|[`LookupTablePlan.prepare`](#api-LookupTablePlan-prepare)|校验查表调用，不生成数值列。|
|[`PreparedLookup`](#api-PreparedLookup)|保存已校验的模式和冻结点引用；实际数组执行者可单独持有只读打包列。|
|[`PreparedLookup.packed`](#api-PreparedLookup-packed)|产生只读数组视图的底层列。|
|[`PreparedLookup.axis_at`](#api-PreparedLookup-axis_at)|按序号读取物理坐标。|
|[`PreparedLookup.value_at`](#api-PreparedLookup-value_at)|按序号读取定宽值。|
|[`pack_requested_lookups`](#api-pack_requested_lookups)|只为实际执行的根建立数组查表列。|
|[`pack_requested_lookups.visit`](#api-pack_requested_lookups-visit)|改写本根的查表节点。|
|[`validate_lookups`](#api-validate_lookups)|检查有限表集合。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass, field, replace
from hashlib import sha256
from math import isfinite
from struct import Struct
from .types import SignalDType as D
from .unit_registry import resolve_unit
from .validation import require_identifier
```

</details>

<a id="api-_exact_f64"></a>
## `_exact_f64`

校验 float64 转换。

```python
_exact_f64(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; float|是|无|位置或关键字。原始标定点坐标或线性表值，转为有限 float64 前先检查是否会丢失整数精度。|

### 返回说明

float。

### 异常说明

非有限、整数超界或精度损失。

源码：[`src/chronaxis/core/lookup.py:22`](../../../src/chronaxis/core/lookup.py#L22)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-LookupTablePlan"></a>
## `LookupTablePlan`

保存经校验的有限标定点。身份保留原生数字类型、单位和每一点的次序。

```python
class LookupTablePlan
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|本计划中供表达式引用的唯一标定表名。|
|`points`|tuple[tuple[int &#124; float, int &#124; float], ...]|是|无|按输入严格递增的标定点；每项为输入坐标与对应输出值。|
|`input_unit`|str|是|无|标定点第一列的单位；查询值先换算到此单位。|
|`unit`|str|是|无|标定点第二列的单位，也是查表结果的单位。|
|`dtype`|[D](chronaxis.core.types.md#api-SignalDType)|不填写|构造时计算|此表在当前插值方式下返回的数值类型。|
|`identity`|str|不填写|构造时计算|由单位、类型和点对确定的标定表标识，区分同名但内容不同的表。|

源码：[`src/chronaxis/core/lookup.py:35`](../../../src/chronaxis/core/lookup.py#L35)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-LookupTablePlan-__post_init__"></a>
### `LookupTablePlan.__post_init__`

校验轴和阶梯输出的共同类型。

```python
LookupTablePlan.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

无。

#### 异常说明

类型、单位、次序、大小或精度错误。

源码：[`src/chronaxis/core/lookup.py:45`](../../../src/chronaxis/core/lookup.py#L45)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-LookupTablePlan-prepare"></a>
### `LookupTablePlan.prepare`

校验查表调用，不生成数值列。

```python
LookupTablePlan.prepare(mode, bounds)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`mode`|str|是|无|位置或关键字。表内模式，linear 线性插值，previous 或 next 选相邻台阶。|
|`bounds`|str|是|无|位置或关键字。查询超出标定轴范围时的处理，invalid 返回无效，clamp 取最近端点。|

#### 返回说明

PreparedLookup。

#### 异常说明

模式或精度错误。

源码：[`src/chronaxis/core/lookup.py:85`](../../../src/chronaxis/core/lookup.py#L85)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-PreparedLookup"></a>
## `PreparedLookup`

保存已校验的模式和冻结点引用；实际数组执行者可单独持有只读打包列。

```python
class PreparedLookup
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`identity`|str|是|无|由单位、类型和点对确定的标定表标识，区分同名但内容不同的表。|
|`mode`|str|是|无|linear 在两点间线性插值；previous 和 next 分别取前后标定点。|
|`bounds`|str|是|无|输入超出标定范围时，invalid 标为无效，clamp 使用最近端点。|
|`dtype`|[D](chronaxis.core.types.md#api-SignalDType)|是|无|此表在当前插值方式下返回的数值类型。|
|`points`|tuple|是|无|按输入严格递增的标定点；每项为输入坐标与对应输出值。|
|`axis`|bytes &#124; None|否|None|按输入单位升序排列的横坐标；紧凑表示只为实际引用的表创建。|
|`values`|bytes &#124; None|否|None|各标定横坐标对应的输出值；阶梯读取保留原整数精度。|

源码：[`src/chronaxis/core/lookup.py:97`](../../../src/chronaxis/core/lookup.py#L97)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-PreparedLookup-packed"></a>
### `PreparedLookup.packed`

产生只读数组视图的底层列。

```python
PreparedLookup.packed()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

定宽两列的执行副本。

#### 异常说明

分配错误。

源码：[`src/chronaxis/core/lookup.py:108`](../../../src/chronaxis/core/lookup.py#L108)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-PreparedLookup-axis_at"></a>
### `PreparedLookup.axis_at`

按序号读取物理坐标。

```python
PreparedLookup.axis_at(index)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`index`|int|是|无|位置或关键字。从零起算的标定点下标，用于取得该点原轴坐标。|

#### 返回说明

float。

#### 异常说明

非法索引。

源码：[`src/chronaxis/core/lookup.py:118`](../../../src/chronaxis/core/lookup.py#L118)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-PreparedLookup-value_at"></a>
### `PreparedLookup.value_at`

按序号读取定宽值。

```python
PreparedLookup.value_at(index)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`index`|int|是|无|位置或关键字。从零起算的标定点下标，用于按准备好的类型取得该点表值。|

#### 返回说明

原生int或float。

#### 异常说明

非法索引。

源码：[`src/chronaxis/core/lookup.py:122`](../../../src/chronaxis/core/lookup.py#L122)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-pack_requested_lookups"></a>
## `pack_requested_lookups`

只为实际执行的根建立数组查表列。

```python
pack_requested_lookups(expression)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`expression`|StaticExpression &#124; CompiledExpression|是|无|位置或关键字。仅在本次准备执行的表达式树上遍历查表节点，按需建立可复用的不可变定宽列。|

### 返回说明

局部执行副本。

### 异常说明

分配错误。

共用同一配置及模式的调用只打包一次。未消费的派生定义不会进入此根，原声明保持不可变。

源码：[`src/chronaxis/core/lookup.py:128`](../../../src/chronaxis/core/lookup.py#L128)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-pack_requested_lookups-visit"></a>
### `pack_requested_lookups.visit`

改写本根的查表节点。

```python
pack_requested_lookups.visit(node)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`node`|ExprNode|是|无|位置或关键字。正在处理的已编译子节点，包含操作、参数和输入依赖。|

#### 返回说明

原节点或带执行列的副本。

#### 异常说明

分配错误。

源码：[`src/chronaxis/core/lookup.py:137`](../../../src/chronaxis/core/lookup.py#L137)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-validate_lookups"></a>
## `validate_lookups`

检查有限表集合。

```python
validate_lookups(tables, version)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`tables`|tuple[[LookupTablePlan](chronaxis.core.lookup.md#api-LookupTablePlan), ...]|是|无|位置或关键字。本配置中已冻结的全部标定表声明，用于核对表名唯一性和表数上限。|
|`version`|int|是|无|位置或关键字。所属配置的整数版本，非空查表声明要求版本 4。|

### 返回说明

无。

### 异常说明

非v4、重复名或表过多。

源码：[`src/chronaxis/core/lookup.py:156`](../../../src/chronaxis/core/lookup.py#L156)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
