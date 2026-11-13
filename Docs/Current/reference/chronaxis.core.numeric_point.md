# `chronaxis.core.numeric_point`

生产逐点计算的定宽数值原语，不构造单元素数组。

输入是编译器已核实类型和单位的ScalarValue。输出保留数值类型、无效原因和
有限精度要求；整数用无界临时值验证定宽结果，float转换先检查有效尾位。
这些函数不调用参考数值实现，不读写来源，也不持有跨点状态。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)

## 对象导航

|对象|用途|
|---|---|
|[`failed`](#api-failed)|构造不可用结果。|
|[`exact_float`](#api-exact_float)|按整数幅度的有效尾位判断float64可表示性。|
|[`to_float_point`](#api-to_float_point)|无损转换当前数值。|
|[`checked_result`](#api-checked_result)|校验计算完成后的定宽范围或有限性。|
|[`binary_point`](#api-binary_point)|计算已通过静态类型检查的二元运算。|
|[`unary_point`](#api-unary_point)|计算取负或绝对值。|
|[`affine_point`](#api-affine_point)|按完整value*scale+offset换算当前值，不进行第二次DBC换算。|
|[`logic_point`](#api-logic_point)|按对称三值规则求布尔值。|
|[`math_point`](#api-math_point)|执行极值、限幅和开方。|
|[`integer_point`](#api-integer_point)|执行定宽取余、位操作和精确转整数。|
|[`lookup_point`](#api-lookup_point)|用准备期只读表视图查一个有效点，不建立单元素列。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from math import isfinite, sqrt
from .scalar import INTEGER_BOUNDS, ScalarValue
from .types import QualityFlag as Q, SignalDType as D, _QUALITY_BY_MASK
```

</details>

<a id="api-failed"></a>
## `failed`

构造不可用结果。

```python
failed(dtype, quality, labels=())
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`dtype`|SignalDType|是|无|位置或关键字。静态编译确定的结果类型；此处不按当前数值大小推断类型。|
|`quality`|QualityFlag|是|无|位置或关键字。无效结果携带的质量位组合。|
|`labels`|tuple[str, ...]|否|()|位置或关键字。枚举声明的有序标签；普通数值和布尔结果使用空元组。|

### 返回说明

ScalarValue。

### 异常说明

模型合同错误。

源码：[`src/chronaxis/core/numeric_point.py:20`](../../../src/chronaxis/core/numeric_point.py#L20)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-exact_float"></a>
## `exact_float`

按整数幅度的有效尾位判断float64可表示性。

```python
exact_float(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; float|是|无|位置或关键字。待转为 float64 的原生整数或浮点数；不接受布尔值，整数必须能无损表示。|

### 返回说明

(有限float或None, 质量)。

### 异常说明

非数值结构错误；超大整数作为NONFINITE返回，不抛转换溢出。

源码：[`src/chronaxis/core/numeric_point.py:25`](../../../src/chronaxis/core/numeric_point.py#L25)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-to_float_point"></a>
## `to_float_point`

无损转换当前数值。

```python
to_float_point(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|[chronaxis.core.scalar.ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)|是|无|位置或关键字。当前规范标量，包含声明类型、有效性、质量位及适用的枚举信息。|

### 返回说明

FLOAT64值。

### 异常说明

非数值类型。

源码：[`src/chronaxis/core/numeric_point.py:51`](../../../src/chronaxis/core/numeric_point.py#L51)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-checked_result"></a>
## `checked_result`

校验计算完成后的定宽范围或有限性。

```python
checked_result(number, dtype)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`number`|int &#124; float|是|无|位置或关键字。已经求出的原生数值，按目标类型检查范围和非有限值。|
|`dtype`|SignalDType|是|无|位置或关键字。静态编译确定的结果类型；此处不按当前数值大小推断类型。|

### 返回说明

带有明确类型的值。

### 异常说明

非数值类型。

源码：[`src/chronaxis/core/numeric_point.py:61`](../../../src/chronaxis/core/numeric_point.py#L61)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-binary_point"></a>
## `binary_point`

计算已通过静态类型检查的二元运算。

```python
binary_point(op, left, right, dtype)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`op`|str|是|无|位置或关键字。内部二元指令：add、sub、mul、div，或 eq、ne、lt、le、gt、ge 比较。|
|`left`|[chronaxis.core.scalar.ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)|是|无|位置或关键字。左操作数；类型和单位关系已由表达式编译器检查。|
|`right`|[chronaxis.core.scalar.ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)|是|无|位置或关键字。右操作数；枚举比较须与左侧使用同一标签域。|
|`dtype`|SignalDType|是|无|位置或关键字。静态编译确定的结果类型；此处不按当前数值大小推断类型。|

### 返回说明

ScalarValue。

### 异常说明

未登记操作或内部类型合同错误；除零和定宽失败转成质量。

源码：[`src/chronaxis/core/numeric_point.py:72`](../../../src/chronaxis/core/numeric_point.py#L72)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-unary_point"></a>
## `unary_point`

计算取负或绝对值。

```python
unary_point(op, value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`op`|str|是|无|位置或关键字。单值运算指令：abs 取绝对值，neg 取相反数。|
|`value`|[chronaxis.core.scalar.ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)|是|无|位置或关键字。当前规范标量，包含声明类型、有效性、质量位及适用的枚举信息。|

### 返回说明

同型值。

### 异常说明

未知操作。

源码：[`src/chronaxis/core/numeric_point.py:99`](../../../src/chronaxis/core/numeric_point.py#L99)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-affine_point"></a>
## `affine_point`

按完整value*scale+offset换算当前值，不进行第二次DBC换算。

```python
affine_point(value, scale, offset, dtype)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|[chronaxis.core.scalar.ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)|是|无|位置或关键字。当前规范标量，包含声明类型、有效性、质量位及适用的枚举信息。|
|`scale`|int &#124; float|是|无|位置或关键字。仿射换算中的乘数，计算 value * scale + offset；整数输出要求原生整数系数。|
|`offset`|int &#124; float|是|无|位置或关键字。乘法后的加数；偏移相消得到零是合法结果，不按乘法下溢处理。|
|`dtype`|SignalDType|是|无|位置或关键字。静态编译确定的结果类型；此处不按当前数值大小推断类型。|

### 返回说明

ScalarValue。

### 异常说明

内部静态合同错误；数值失败保存为质量。

源码：[`src/chronaxis/core/numeric_point.py:109`](../../../src/chronaxis/core/numeric_point.py#L109)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-logic_point"></a>
## `logic_point`

按对称三值规则求布尔值。

```python
logic_point(op, values)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`op`|str|是|无|位置或关键字。布尔指令 not、and 或 or，按三值逻辑保留能决定结果的有效值。|
|`values`|tuple[[chronaxis.core.scalar.ScalarValue](chronaxis.core.scalar.md#api-ScalarValue), ...]|是|无|位置或关键字。已静态检查为布尔类型的操作数，顺序与指令参数一致。|

### 返回说明

BOOL。

### 异常说明

未知操作。

源码：[`src/chronaxis/core/numeric_point.py:136`](../../../src/chronaxis/core/numeric_point.py#L136)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-math_point"></a>
## `math_point`

执行极值、限幅和开方。

```python
math_point(op, values)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`op`|str|是|无|位置或关键字。数学指令 minimum、maximum、clip 或 sqrt。|
|`values`|tuple[[chronaxis.core.scalar.ScalarValue](chronaxis.core.scalar.md#api-ScalarValue), ...]|是|无|位置或关键字。已完成类型和单位统一的数值操作数；clip 依次为值、下限、上限。|

### 返回说明

带有明确类型的结果。

### 异常说明

未知操作。

源码：[`src/chronaxis/core/numeric_point.py:152`](../../../src/chronaxis/core/numeric_point.py#L152)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-integer_point"></a>
## `integer_point`

执行定宽取余、位操作和精确转整数。

```python
integer_point(node, values)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`node`|[chronaxis.core.expression.ExprNode](chronaxis.core.expression.md#api-ExprNode)|是|无|位置或关键字。包含 mod、位运算或整数转换指令、结果类型及静态参数的已编译节点。|
|`values`|tuple[[chronaxis.core.scalar.ScalarValue](chronaxis.core.scalar.md#api-ScalarValue), ...]|是|无|位置或关键字。本次数值操作数；整数转换可接收浮点输入，类型与参数由静态节点确定；输入无效、越界或精度问题通过结果质量位表达。|

### 返回说明

静态dtype结果。

### 异常说明

未知操作；小数、越界、零除保存对应质量。

源码：[`src/chronaxis/core/numeric_point.py:187`](../../../src/chronaxis/core/numeric_point.py#L187)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-lookup_point"></a>
## `lookup_point`

用准备期只读表视图查一个有效点，不建立单元素列。

```python
lookup_point(table, axis, nodes, value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`table`|[chronaxis.core.lookup.PreparedLookup](chronaxis.core.lookup.md#api-PreparedLookup)|是|无|位置或关键字。本程序准备的 packed() 查表副本，包含边界策略、输出类型及冻结字节列。|
|`axis`|numpy.ndarray[float64]|是|无|位置或关键字。由不可变字节建立的一维只读坐标视图，不复制为单元素数组。|
|`nodes`|numpy.ndarray|是|无|位置或关键字。与坐标等长的一维只读节点值视图，采用 table.dtype 对应的小端 8 字节数值类型。|
|`value`|[chronaxis.core.scalar.ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)|是|无|位置或关键字。当前规范标量，包含声明类型、有效性、质量位及适用的枚举信息。|

### 返回说明

表声明类型的值。

### 异常说明

静态表结构错误；范围、精度及非有限结果保存为质量。

源码：[`src/chronaxis/core/numeric_point.py:215`](../../../src/chronaxis/core/numeric_point.py#L215)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
