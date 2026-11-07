# `chronaxis.core.numeric_numpy`

对同长度数值列执行算术和比较，并逐位置记录有效性与质量。

输入NumericArray保存一维values、bool类型的valid和uint16类型的quality。
算术先合并质量原因，再用布尔掩码选择能计算的位置，输出独立的只读列。
整数先检查符号、幅度和目标定宽范围，再执行NumPy逐元素函数；
需要float64时先检查整数的精确表示，失败位置不执行正常运算。

所有列的形状都是(N,)，N为行数；枚举存为int64编码并携带固定labels。
无效位置的零或False仅是存储占位，不能脱离valid当作业务值使用。
本模块依赖NumPy及核心类型规则，不读写文件或加载旧解码路径。
仅共享静态类型与模型检查，不调用标量参考数值函数，也不以object数组
或逐样本Python回调代替列运算；输出复制存储，不修改调用者数组。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[QualityFlag](chronaxis.core.types.md#api-QualityFlag)、[SignalDType](chronaxis.core.types.md#api-SignalDType)

## 对象导航

|对象|用途|
|---|---|
|[`_readonly`](#api-_readonly)|复制列并设置普通只读所有权约定。|
|[`NumericArray`](#api-NumericArray)|保存没有时间轴的一组数值，以及每个位置的有效性和质量原因。|
|[`NumericArray.take`](#api-NumericArray-take)|按活动行切出标签及所需原码，保持同一坐标系。|
|[`NumericArray.__post_init__`](#api-NumericArray-__post_init__)|验证布局、基础质量、有限性及enum域后冻结独立副本。|
|[`_output`](#api-_output)|用已有质量列建立统一有效性结果。|
|[`_magnitude`](#api-_magnitude)|在uint64中取得整数列的精确绝对幅度。|
|[`_from_magnitude`](#api-_from_magnitude)|将已检查范围的整数绝对值与符号组合成int64数组。|
|[`to_float_numpy`](#api-to_float_numpy)|用固定11个尾位掩码独立检查整数到float64是否精确。|
|[`_integer_compare`](#api-_integer_compare)|在整数域精确比较signed/unsigned两列。|
|[`_integer_arithmetic`](#api-_integer_arithmetic)|先检查整数结果是否超界，再计算安全位置的加减乘。|
|[`binary_numpy`](#api-binary_numpy)|对两列执行注册算术或比较，只计算质量允许的位置。|
|[`unary_numpy`](#api-unary_numpy)|独立数组abs/neg，signed min和unsigned负号先拒绝。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from types import MappingProxyType
from .numeric import COMPARISONS, result_dtype
from .types import QualityFlag, SignalDType
from .validation import require_text
```

</details>

<a id="api-_readonly"></a>
## `_readonly`

复制列并设置普通只读所有权约定。

```python
_readonly(array: np.ndarray) -> np.ndarray
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`array`|np.ndarray|是|无|位置或关键字。array为已校验ndarray。|

### 返回说明

拥有独立存储的只读列。

### 异常说明

内存分配错误传播；不声称防恶意篡改。

返回类型：np.ndarray。

源码：[`src/chronaxis/core/numeric_numpy.py:38`](../../../src/chronaxis/core/numeric_numpy.py#L38)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-NumericArray"></a>
## `NumericArray`

保存没有时间轴的一组数值，以及每个位置的有效性和质量原因。

values、valid和quality均为形状(N,)的普通ndarray，长度必须一致。
values的物理类型由dtype指定，valid为bool，quality为uint16；
valid严格等于quality == 0，无效位置只能作为存储占位使用。
枚举以int64编码表示，labels给出固定标签顺序，只检查有效位置的编码。
构造时复制三个数组并设置只读标志，保留独立存储；这是一项普通使用
约定，不声称能抵御主动解除写保护。实例不保存时间、单位或跨批次状态。

```python
class NumericArray
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`dtype`|[SignalDType](chronaxis.core.types.md#api-SignalDType)|是|无|SignalDType枚举成员：INT64是有符号64位整数，UINT64是无符号64位整数，FLOAT64是双精度浮点，BOOL是真/假，ENUM是预先声明的状态标签。这里传枚举成员，不传字符串；当前运算支持哪些类型仍见本对象的约束。|
|`values`|np.ndarray|是|无|int64/uint64/float64/bool列；enum为int64 code。|
|`valid`|np.ndarray|是|无|bool有效位置，禁止maskless运算。|
|`quality`|np.ndarray|是|无|uint16足够容纳九种质量位。|
|`labels`|tuple[str, ...]|否|()|enum顺序域，其他dtype为空。|
|`code`|'[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray) &#124; None'|否|None|仅请求 enum_code 时附带独立整数列。|

源码：[`src/chronaxis/core/numeric_numpy.py:54`](../../../src/chronaxis/core/numeric_numpy.py#L54)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-NumericArray-take"></a>
### `NumericArray.take`

按活动行切出标签及所需原码，保持同一坐标系。

```python
NumericArray.take(indices)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`indices`|numpy.ndarray|是|无|位置或关键字。当前批中需要提取的行索引，按相同次序选取数值、质量及可选原码。|

#### 返回说明

对应行的独立 NumericArray。

#### 异常说明

索引或布局不合法时传播数组错误。

源码：[`src/chronaxis/core/numeric_numpy.py:72`](../../../src/chronaxis/core/numeric_numpy.py#L72)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-NumericArray-__post_init__"></a>
### `NumericArray.__post_init__`

验证布局、基础质量、有限性及enum域后冻结独立副本。

```python
NumericArray.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无；读取数据类字段。

#### 返回说明

None；不隐式cast或清除质量。

#### 异常说明

TypeError为布局；ValueError为shape/质量/非法正常值。

本函数直接报告的具体错误：

- `TypeError`：NumericArray需要带有明确类型的 dtype与tuple labels。
- `ValueError`：数值/valid/quality长度不同。
- `ValueError`：质量与valid矛盾或未知质量位。
- `ValueError`：正常float必须有限。
- `TypeError`：NumericArray需要1维精确dtype ndarray。
- `ValueError`：enum需要非空唯一域。
- `ValueError`：正常enum code超出域。
- `ValueError`：非enum不能携带labels。

返回类型：None。

源码：[`src/chronaxis/core/numeric_numpy.py:82`](../../../src/chronaxis/core/numeric_numpy.py#L82)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_output"></a>
## `_output`

用已有质量列建立统一有效性结果。

```python
_output(dtype, values, quality, labels=()) -> NumericArray
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`dtype`|[SignalDType](chronaxis.core.types.md#api-SignalDType)|是|无|位置或关键字。本次运算已经确定的逻辑结果类型，用来构造NumericArray。|
|`values`|numpy.ndarray|是|无|位置或关键字。本次数值结果的一维数组，物理dtype须符合逻辑dtype。|
|`quality`|numpy.ndarray[uint16]|是|无|位置或关键字。与values等长的质量位数组；非零位置包含缺失、溢出等原因，不能把失败值当成有效结果。|
|`labels`|tuple[str, ...]|否|()|位置或关键字。枚举值对应的标签集合；非枚举输出使用空元组。|

### 返回说明

独立只读NumericArray。

### 异常说明

模型校验/分配错误传播，不改变数值政策。

返回类型：[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)。

源码：[`src/chronaxis/core/numeric_numpy.py:138`](../../../src/chronaxis/core/numeric_numpy.py#L138)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_magnitude"></a>
## `_magnitude`

在uint64中取得整数列的精确绝对幅度。

```python
_magnitude(values: np.ndarray) -> np.ndarray
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`values`|np.ndarray|是|无|位置或关键字。形状(N,)的int64或uint64数组，由调用者保证布局。|

### 返回说明

新的uint64数组，形状保持(N,)；int64最小值得到2**63。

### 异常说明

内存分配或底层数组操作异常直接传播。

### 流程说明

先复制位表示，再对有符号负数按补码取反加一，不调用会溢出的abs(min)。

返回类型：np.ndarray。

源码：[`src/chronaxis/core/numeric_numpy.py:149`](../../../src/chronaxis/core/numeric_numpy.py#L149)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_from_magnitude"></a>
## `_from_magnitude`

将已检查范围的整数绝对值与符号组合成int64数组。

```python
_from_magnitude(magnitude: np.ndarray, negative: np.ndarray) -> np.ndarray
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`magnitude`|np.ndarray|是|无|位置或关键字。形状(N,)的uint64幅度。正数不超过2**63-1，负数不超过2**63。|
|`negative`|np.ndarray|是|无|位置或关键字。同形状bool掩码，True表示该位置应为负数。|

### 返回说明

独立存储的int64数组；零和最小负数均通过位表示恢复。

### 异常说明

调用者负责证明范围与布局；内存分配或数组操作异常直接传播。

### 边界说明

先复制幅度再构建负数补码，最后改变位视图，不先执行危险的有符号负号。

返回类型：np.ndarray。

源码：[`src/chronaxis/core/numeric_numpy.py:173`](../../../src/chronaxis/core/numeric_numpy.py#L173)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-to_float_numpy"></a>
## `to_float_numpy`

用固定11个尾位掩码独立检查整数到float64是否精确。

```python
to_float_numpy(value: NumericArray) -> NumericArray
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)|是|无|位置或关键字。value为数值NumericArray|

### 返回说明

float64列及保留/新增PRECISION_LOSS质量；shape保持。

### 异常说明

TypeError为结构/逻辑类型；分配错误传播。

本函数直接报告的具体错误：

- `TypeError`：float转换需要数值列。

返回类型：[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)。

源码：[`src/chronaxis/core/numeric_numpy.py:196`](../../../src/chronaxis/core/numeric_numpy.py#L196)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_integer_compare"></a>
## `_integer_compare`

在整数域精确比较signed/unsigned两列。

```python
_integer_compare(operator, left, right, selected) -> np.ndarray
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`operator`|str|是|无|位置或关键字。选择整数比较：`eq`等于、`ne`不等于、`lt`小于、`le`小于或等于、`gt`大于、`ge`大于或等于。|
|`left`|numpy.ndarray|是|无|位置或关键字。左侧参与运算的一维数组；它的长度须与另一侧相同，各位置一一对应。这里处理整数数组。|
|`right`|numpy.ndarray|是|无|位置或关键字。右侧参与运算的一维数组；它的长度须与另一侧相同，各位置一一对应。这里处理整数数组。|
|`selected`|numpy.ndarray[bool]|是|无|位置或关键字。两侧均有效的位置为True，只对这些位置进行整数比较；形状与输入列一致。|

### 返回说明

bool结果列，invalid占位False。

### 异常说明

调用者保证等长/类型，分配错误传播。

返回类型：np.ndarray。

源码：[`src/chronaxis/core/numeric_numpy.py:236`](../../../src/chronaxis/core/numeric_numpy.py#L236)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_integer_arithmetic"></a>
## `_integer_arithmetic`

先检查整数结果是否超界，再计算安全位置的加减乘。

```python
_integer_arithmetic(operator, left, right, selected)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`operator`|str|是|无|位置或关键字。选择整数运算：`add`相加、`sub`相减、`mul`相乘。此入口不处理除法。|
|`left`|numpy.ndarray|是|无|位置或关键字。左侧参与运算的一维数组；它的长度须与另一侧相同，各位置一一对应。这里处理整数数组。|
|`right`|numpy.ndarray|是|无|位置或关键字。右侧参与运算的一维数组；它的长度须与另一侧相同，各位置一一对应。这里处理整数数组。|
|`selected`|numpy.ndarray[bool]|是|无|位置或关键字。与输入列等长的布尔掩码；True的位置参加本次运算，False的位置跳过。|

### 返回说明

同类型结果数组和bool溢出掩码，均为形状(N,)。
    未选中或溢出位置保持零占位，调用者必须同时传递有效性与质量。

### 异常说明

调用者保证输入布局和注册运算；内存分配或数组操作异常直接传播。

### 流程说明

加减按符号检查安全门槛；乘法在uint64幅度域检查limit // b。
    检查后才调用逐元素函数，避免先发生整数回绕再判断溢出。

源码：[`src/chronaxis/core/numeric_numpy.py:269`](../../../src/chronaxis/core/numeric_numpy.py#L269)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-binary_numpy"></a>
## `binary_numpy`

对两列执行注册算术或比较，只计算质量允许的位置。

```python
binary_numpy(operator: str, left: NumericArray, right: NumericArray, *, allow_float_literal: bool=False) -> NumericArray
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`operator`|str|是|无|位置或关键字。本入口支持`add`相加、`sub`相减、`mul`相乘、`div`相除，以及`eq`等于、`ne`不等于、`lt`小于、`le`小于或等于、`gt`大于、`ge`大于或等于。填写这些内部名称，不填写符号或任意函数名。|
|`left`|[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)|是|无|位置或关键字。左侧参与运算的一维数组；它的长度须与另一侧相同，各位置一一对应。传NumericArray，包含数值、有效标记和质量原因。|
|`right`|[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)|是|无|位置或关键字。右侧参与运算的一维数组；它的长度须与另一侧相同，各位置一一对应。传NumericArray，包含数值、有效标记和质量原因。|
|`allow_float_literal`|bool|否|False|仅关键字。编译器证明浮点字面量可用于混合类型时才为True。|

### 返回说明

独立只读NumericArray，形状保持(N,)。质量按位合并，计算失败追加原因。
    比较返回BOOL，算术遵守静态结果类型；无效占位不表示正常零或False。

### 异常说明

TypeError、ValueError: 模型、类型、长度、注册运算或枚举域不合法。
    内存分配异常直接传播；除零、溢出或丢精度作为质量原因返回。

### 流程说明

先检查类型与等长布局，再合并有效掩码；整数路径保留精确比较和定宽
    检查，浮点路径先做精度转换。各路径独立于标量参考实现，不修改输入。

返回类型：[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)。

源码：[`src/chronaxis/core/numeric_numpy.py:333`](../../../src/chronaxis/core/numeric_numpy.py#L333)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-unary_numpy"></a>
## `unary_numpy`

独立数组abs/neg，signed min和unsigned负号先拒绝。

```python
unary_numpy(operator: str, value: NumericArray) -> NumericArray
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`operator`|str|是|无|位置或关键字。选择一种单值运算：`abs`取绝对值；`neg`取相反数。逻辑取反由表达式模块处理，不传到这里。|
|`value`|[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)|是|无|位置或关键字。value为数值列。|

### 返回说明

同dtype列及保留/新增质量，shape保持。

### 异常说明

TypeError/ValueError为结构/未知运算，分配错误传播。

本函数直接报告的具体错误：

- `ValueError`：unary仅支持数值abs/neg。

返回类型：[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)。

源码：[`src/chronaxis/core/numeric_numpy.py:422`](../../../src/chronaxis/core/numeric_numpy.py#L422)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
