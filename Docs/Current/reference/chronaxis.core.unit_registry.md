# `chronaxis.core.unit_registry`

在编译期解析版本4的有限单位目录，并推导转换及复合单位。

输入为单位文本或不可变Unit，输出单位元数据及转换系数，不处理样本值。
物理量纲和量种分别检查；有理数与π倍率保持符号形式，避免提前舍入。
解析器仅接受登记原子及有限乘除幂语法，不使用eval、不读写文件。
本模块是当前配置唯一的单位目录；未知标签不会隐式使用其他单位表。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`_indices`](#api-_indices)|检查不可变指数向量，拒绝布尔值和超限幂。|
|[`_dimensions`](#api-_dimensions)|从量种基计算物理量纲，不据量纲反猜量种。|
|[`Scale`](#api-Scale)|保存正有理系数乘π整数次幂，只有执行前才转float64。|
|[`Scale.__post_init__`](#api-Scale-__post_init__)|检查倍率结构及范围。|
|[`Scale.to_float`](#api-Scale-to_float)|在数值执行边界取得有限float倍率。|
|[`Scale.multiply`](#api-Scale-multiply)|相乘两个符号倍率。|
|[`Scale.divide`](#api-Scale-divide)|相除两个正符号倍率。|
|[`Scale.power`](#api-Scale-power)|对符号倍率求有界整数幂。|
|[`Scale.square_root`](#api-Scale-square_root)|对可精确开方的符号倍率取正平方根。|
|[`Unit`](#api-Unit)|保存单位拼写、物理量纲、量种、倍率及可选温度偏移。|
|[`Unit.__post_init__`](#api-Unit-__post_init__)|验证模型不变量，防止手工构造伪造量纲或温度角色。|
|[`_temperature_role`](#api-_temperature_role)|仅为单一绝对温度或温差赋角色，复合温度仍由量种指数区分。|
|[`_make`](#api-_make)|从量种统一构造含一致物理量纲和温度角色的单位。|
|[`_require_unit`](#api-_require_unit)|检查单位代数入口的带有明确类型的对象。|
|[`_require_multiplicative`](#api-_require_multiplicative)|拒绝带偏移温度参与乘除和幂运算。|
|[`multiply`](#api-multiply)|组合单位乘法，保留数值仍需应用的原尺度。|
|[`divide`](#api-divide)|组合单位除法，量种相同的比值成为普通比例。|
|[`_power`](#api-_power)|处理解析器和平方共用的有界单位整数幂。|
|[`square`](#api-square)|求单位平方，同时平方其倍率。|
|[`square_root`](#api-square_root)|对偶数量种指数和可精确开方倍率求平方根。|
|[`conversion`](#api-conversion)|计算source数值到target的乘法系数和加法偏移。|
|[`_kind_symbol`](#api-_kind_symbol)|为未命名量种构造固定基顺序的可解析乘除文本。|
|[`canonical_unit`](#api-canonical_unit)|取得该量种倍率1、偏移0的稳定计算/显示基准。|
|[`output_label`](#api-output_label)|为所选尺度返回可重新解析的输出单位名称。|
|[`_build_atoms`](#api-_build_atoms)|建立有限原子表，不自动扩张SI前缀或读取外部定义。|
|[`_build_preferred`](#api-_build_preferred)|登记倍率1的默认名称，不取用户参数顺序决定显示单位。|
|[`_Parser`](#api-_Parser)|用有限词元递归下降解析单位；未知原子保留None但仍检查完整语法。|
|[`_Parser.__init__`](#api-_Parser-__init__)|构建有限词元流。|
|[`_Parser.peek`](#api-_Parser-peek)|查看当前词元，不推进位置。|
|[`_Parser.factor`](#api-_Parser-factor)|解析原子或括号表达式及可选整数幂。|
|[`_Parser.expression`](#api-_Parser-expression)|按同级左结合解析乘除，完整检查未知项旁的已知非法温度。|
|[`resolve_unit`](#api-resolve_unit)|解析登记单位和受限复合文本，未知原子返回None。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from fractions import Fraction
from math import isfinite, isqrt, pi
from types import MappingProxyType
```

</details>

<a id="api-_indices"></a>
## `_indices`

检查不可变指数向量，拒绝布尔值和超限幂。

```python
_indices(value: tuple[int, ...], size: int, field: str, *, bounded: bool=True) -> None
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|tuple[int, ...]|是|无|位置或关键字。待核验的不可变指数向量，每一维均须为原生整数。|
|`size`|int|是|无|位置或关键字。当前单位维度体系要求的向量长度。|
|`field`|str|是|无|位置或关键字。错误报告所用的字段名称，用于区分量种或物理维度指数。|
|`bounded`|bool|否|True|仅关键字。bounded决定是否限制±32。|

### 返回说明

None。

### 异常说明

TypeError为结构或类型错误，ValueError为指数超限。

返回类型：None。

源码：[`src/chronaxis/core/unit_registry.py:29`](../../../src/chronaxis/core/unit_registry.py#L29)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_dimensions"></a>
## `_dimensions`

从量种基计算物理量纲，不据量纲反猜量种。

```python
_dimensions(kind: tuple[int, ...]) -> tuple[int, ...]
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`kind`|tuple[int, ...]|是|无|位置或关键字。kind为八维量种指数。|

### 返回说明

质量、长度、时间、电流、温度的五维指数。

### 异常说明

调用方负责输入结构检查。

返回类型：tuple[int, ...]。

源码：[`src/chronaxis/core/unit_registry.py:43`](../../../src/chronaxis/core/unit_registry.py#L43)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-Scale"></a>
## `Scale`

保存正有理系数乘π整数次幂，只有执行前才转float64。

factor与pi_power不可变；负方向属于信号转换，不属于单位倍率。
分子和分母分别最多4096位，避免无量纲嵌套幂绕过量种指数限制。

```python
class Scale
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`factor`|Fraction|是|无|正有理倍率，保持十进制换算精确。|
|`pi_power`|int|否|0|π指数，用于角度与角速度转换。|

源码：[`src/chronaxis/core/unit_registry.py:55`](../../../src/chronaxis/core/unit_registry.py#L55)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-Scale-__post_init__"></a>
### `Scale.__post_init__`

检查倍率结构及范围。

```python
Scale.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

TypeError为类型错误，ValueError为非正倍率、指数或有理数位数超限。

返回类型：None。

源码：[`src/chronaxis/core/unit_registry.py:65`](../../../src/chronaxis/core/unit_registry.py#L65)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-Scale-to_float"></a>
### `Scale.to_float`

在数值执行边界取得有限float倍率。

```python
Scale.to_float() -> float
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

正有限float；π取math.pi的float64表示，整体倍率最后统一舍入。

#### 异常说明

ValueError为上溢、下溢到零或非有限结果。

返回类型：float。

源码：[`src/chronaxis/core/unit_registry.py:81`](../../../src/chronaxis/core/unit_registry.py#L81)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-Scale-multiply"></a>
### `Scale.multiply`

相乘两个符号倍率。

```python
Scale.multiply(other: 'Scale') -> 'Scale'
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`other`|'[Scale](chronaxis.core.unit_registry.md#api-Scale)'|是|无|位置或关键字。other为Scale。|

#### 返回说明

新Scale，不舍入。

#### 异常说明

TypeError为输入类型错误，ValueError为指数超限。

返回类型：'[Scale](chronaxis.core.unit_registry.md#api-Scale)'。

源码：[`src/chronaxis/core/unit_registry.py:97`](../../../src/chronaxis/core/unit_registry.py#L97)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-Scale-divide"></a>
### `Scale.divide`

相除两个正符号倍率。

```python
Scale.divide(other: 'Scale') -> 'Scale'
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`other`|'[Scale](chronaxis.core.unit_registry.md#api-Scale)'|是|无|位置或关键字。other为Scale。|

#### 返回说明

新Scale，不舍入。

#### 异常说明

TypeError为输入类型错误，ValueError为指数超限。

返回类型：'[Scale](chronaxis.core.unit_registry.md#api-Scale)'。

源码：[`src/chronaxis/core/unit_registry.py:109`](../../../src/chronaxis/core/unit_registry.py#L109)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-Scale-power"></a>
### `Scale.power`

对符号倍率求有界整数幂。

```python
Scale.power(exponent: int) -> 'Scale'
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`exponent`|int|是|无|位置或关键字。exponent为-32到32的原生整数。|

#### 返回说明

新Scale。

#### 异常说明

TypeError为非整数，ValueError为幂或结果指数超限。

返回类型：'[Scale](chronaxis.core.unit_registry.md#api-Scale)'。

源码：[`src/chronaxis/core/unit_registry.py:121`](../../../src/chronaxis/core/unit_registry.py#L121)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-Scale-square_root"></a>
### `Scale.square_root`

对可精确开方的符号倍率取正平方根。

```python
Scale.square_root() -> 'Scale'
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

新Scale。

#### 异常说明

ValueError为有理系数非完全平方或π指数为奇数。

返回类型：'[Scale](chronaxis.core.unit_registry.md#api-Scale)'。

源码：[`src/chronaxis/core/unit_registry.py:135`](../../../src/chronaxis/core/unit_registry.py#L135)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-Unit"></a>
## `Unit`

保存单位拼写、物理量纲、量种、倍率及可选温度偏移。

数值换到基准的公式为value*scale+offset；偏移仅用于绝对温度。
量种指数独立区分能量、力矩、角度、比例及绝对温度/温差。
symbol可以是中间代数描述；只有canonical_unit返回的symbol保证可重读。

```python
class Unit
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`symbol`|str|是|无|当前表示的单位文本，复合表示可不同于基准名称。|
|`dimensions`|tuple[int, ...]|是|无|质量、长度、时间、电流、温度。|
|`kind`|tuple[int, ...]|是|无|KIND_BASES顺序的八维量种指数。|
|`scale`|[Scale](chronaxis.core.unit_registry.md#api-Scale)|是|无|相对量种基准的符号倍率。|
|`offset`|Fraction|否|Fraction(0)|基准单位中的偏移，如273.15K。|
|`temperature_role`|str &#124; None|否|None|absolute、delta或非单一温度。|

源码：[`src/chronaxis/core/unit_registry.py:151`](../../../src/chronaxis/core/unit_registry.py#L151)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-Unit-__post_init__"></a>
### `Unit.__post_init__`

验证模型不变量，防止手工构造伪造量纲或温度角色。

```python
Unit.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

TypeError为结构错误，ValueError为量纲/量种/角色不一致。

返回类型：None。

源码：[`src/chronaxis/core/unit_registry.py:166`](../../../src/chronaxis/core/unit_registry.py#L166)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_temperature_role"></a>
## `_temperature_role`

仅为单一绝对温度或温差赋角色，复合温度仍由量种指数区分。

```python
_temperature_role(kind: tuple[int, ...]) -> str | None
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`kind`|tuple[int, ...]|是|无|位置或关键字。kind为八维指数。|

### 返回说明

absolute、delta或None。

### 异常说明

无，结构由调用方检查。

返回类型：str &#124; None。

源码：[`src/chronaxis/core/unit_registry.py:187`](../../../src/chronaxis/core/unit_registry.py#L187)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_make"></a>
## `_make`

从量种统一构造含一致物理量纲和温度角色的单位。

```python
_make(symbol: str, kind: tuple[int, ...], scale: Scale | None=None, offset: Fraction=Fraction(0)) -> Unit
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`symbol`|str|是|无|位置或关键字。显示和解析时使用的单位符号。|
|`kind`|tuple[int, ...]|是|无|位置或关键字。按固定量种基底排列的指数向量，由此推导物理维度。|
|`scale`|[Scale](chronaxis.core.unit_registry.md#api-Scale) &#124; None|否|None|位置或关键字。相对量种基准的正倍率，省略采用单位倍率。|
|`offset`|Fraction|否|Fraction(0)|位置或关键字。标度转换到基准时的精确偏移量，乘积类单位不带温标偏移。|

### 返回说明

已校验Unit。

### 异常说明

Unit验证错误直接传播。

返回类型：[Unit](chronaxis.core.unit_registry.md#api-Unit)。

源码：[`src/chronaxis/core/unit_registry.py:202`](../../../src/chronaxis/core/unit_registry.py#L202)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_require_unit"></a>
## `_require_unit`

检查单位代数入口的带有明确类型的对象。

```python
_require_unit(value: Unit) -> None
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|[Unit](chronaxis.core.unit_registry.md#api-Unit)|是|无|位置或关键字。value为待检查对象。|

### 返回说明

None。

### 异常说明

TypeError为非Unit对象。

返回类型：None。

源码：[`src/chronaxis/core/unit_registry.py:214`](../../../src/chronaxis/core/unit_registry.py#L214)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_require_multiplicative"></a>
## `_require_multiplicative`

拒绝带偏移温度参与乘除和幂运算。

```python
_require_multiplicative(value: Unit) -> None
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|[Unit](chronaxis.core.unit_registry.md#api-Unit)|是|无|位置或关键字。value为Unit。|

### 返回说明

None。

### 异常说明

TypeError为非Unit；ValueError为带偏移单位。

返回类型：None。

源码：[`src/chronaxis/core/unit_registry.py:226`](../../../src/chronaxis/core/unit_registry.py#L226)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-multiply"></a>
## `multiply`

组合单位乘法，保留数值仍需应用的原尺度。

```python
multiply(left: Unit, right: Unit) -> Unit
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`left`|[Unit](chronaxis.core.unit_registry.md#api-Unit)|是|无|位置或关键字。乘积左侧的已解析单位，量种与倍率参加组合。|
|`right`|[Unit](chronaxis.core.unit_registry.md#api-Unit)|是|无|位置或关键字。乘积右侧的已解析单位，其各基底指数加到左侧单位上。|

### 返回说明

量种指数相加、倍率相乘的新Unit。

### 异常说明

TypeError为类型错误；ValueError为偏移单位或指数超限。

返回类型：[Unit](chronaxis.core.unit_registry.md#api-Unit)。

源码：[`src/chronaxis/core/unit_registry.py:239`](../../../src/chronaxis/core/unit_registry.py#L239)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-divide"></a>
## `divide`

组合单位除法，量种相同的比值成为普通比例。

```python
divide(left: Unit, right: Unit) -> Unit
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`left`|[Unit](chronaxis.core.unit_registry.md#api-Unit)|是|无|位置或关键字。作为分子的已解析单位。|
|`right`|[Unit](chronaxis.core.unit_registry.md#api-Unit)|是|无|位置或关键字。作为分母的已解析单位，从分子各基底指数减去其对应指数。|

### 返回说明

指数相减、倍率相除的新Unit。

### 异常说明

TypeError为类型错误；ValueError为偏移单位或指数超限。

返回类型：[Unit](chronaxis.core.unit_registry.md#api-Unit)。

源码：[`src/chronaxis/core/unit_registry.py:253`](../../../src/chronaxis/core/unit_registry.py#L253)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_power"></a>
## `_power`

处理解析器和平方共用的有界单位整数幂。

```python
_power(unit: Unit, exponent: int) -> Unit
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`unit`|[Unit](chronaxis.core.unit_registry.md#api-Unit)|是|无|位置或关键字。将要按整数幂组合量种、尺度和单位标签的已解析单位。|
|`exponent`|int|是|无|位置或关键字。作用于量种指数和倍率的有界整数幂。|

### 返回说明

新Unit。

### 异常说明

TypeError为类型错误；ValueError为偏移温度、幂或组合超限。

返回类型：[Unit](chronaxis.core.unit_registry.md#api-Unit)。

源码：[`src/chronaxis/core/unit_registry.py:267`](../../../src/chronaxis/core/unit_registry.py#L267)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-square"></a>
## `square`

求单位平方，同时平方其倍率。

```python
square(unit: Unit) -> Unit
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`unit`|[Unit](chronaxis.core.unit_registry.md#api-Unit)|是|无|位置或关键字。unit为Unit。|

### 返回说明

新Unit。

### 异常说明

TypeError或ValueError沿单位幂检查传播。

返回类型：[Unit](chronaxis.core.unit_registry.md#api-Unit)。

源码：[`src/chronaxis/core/unit_registry.py:280`](../../../src/chronaxis/core/unit_registry.py#L280)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-square_root"></a>
## `square_root`

对偶数量种指数和可精确开方倍率求平方根。

```python
square_root(unit: Unit) -> Unit
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`unit`|[Unit](chronaxis.core.unit_registry.md#api-Unit)|是|无|位置或关键字。unit为Unit。|

### 返回说明

新Unit；K²返回K量种，温差平方返回温差量种。非原子尺度的symbol
    只供内部描述；公开显示或重新解析应先取canonical_unit。

### 异常说明

TypeError为类型错误；ValueError为偏移、奇数指数或非精确倍率。

### 边界说明

数值编译器先把输入转为规范基准再开方，不能据中间倍率非完全平方
    拒绝本来合法的sqrt(mA*A)；本函数自身不转换样本数值。

返回类型：[Unit](chronaxis.core.unit_registry.md#api-Unit)。

源码：[`src/chronaxis/core/unit_registry.py:291`](../../../src/chronaxis/core/unit_registry.py#L291)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-conversion"></a>
## `conversion`

计算source数值到target的乘法系数和加法偏移。

```python
conversion(source: Unit, target: Unit) -> tuple[Scale, Fraction]
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|[Unit](chronaxis.core.unit_registry.md#api-Unit)|是|无|位置或关键字。原物理值的已解析单位，决定从何种尺度和温标开始换算。|
|`target`|[Unit](chronaxis.core.unit_registry.md#api-Unit)|是|无|位置或关键字。希望得到的已解析单位，须与原量种兼容。|

### 返回说明

(scale,offset)，数值公式为value*scale+offset。

### 异常说明

TypeError为非Unit；ValueError为量种、温度角色或偏移不兼容。

返回类型：tuple[[Scale](chronaxis.core.unit_registry.md#api-Scale), Fraction]。

源码：[`src/chronaxis/core/unit_registry.py:317`](../../../src/chronaxis/core/unit_registry.py#L317)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_kind_symbol"></a>
## `_kind_symbol`

为未命名量种构造固定基顺序的可解析乘除文本。

```python
_kind_symbol(kind: tuple[int, ...]) -> str
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`kind`|tuple[int, ...]|是|无|位置或关键字。kind为八维整数指数。|

### 返回说明

只含规范原子和乘除幂的文本。

### 异常说明

无，模型已限制指数。

返回类型：str。

源码：[`src/chronaxis/core/unit_registry.py:335`](../../../src/chronaxis/core/unit_registry.py#L335)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-canonical_unit"></a>
## `canonical_unit`

取得该量种倍率1、偏移0的稳定计算/显示基准。

```python
canonical_unit(unit: Unit) -> Unit
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`unit`|[Unit](chronaxis.core.unit_registry.md#api-Unit)|是|无|位置或关键字。unit为Unit。|

### 返回说明

首选规范单位或由固定量种基构造的单位。

### 异常说明

TypeError为非Unit，ValueError为模型不一致。

返回类型：[Unit](chronaxis.core.unit_registry.md#api-Unit)。

源码：[`src/chronaxis/core/unit_registry.py:358`](../../../src/chronaxis/core/unit_registry.py#L358)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-output_label"></a>
## `output_label`

为所选尺度返回可重新解析的输出单位名称。

```python
output_label(unit: Unit, spelling: str) -> str
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`unit`|[Unit](chronaxis.core.unit_registry.md#api-Unit)|是|无|位置或关键字。unit是已解析目标|
|`spelling`|str|是|无|位置或关键字。spelling是生成它的单位文本。|

### 返回说明

原子单位用登记名称，基准组合用规范名称，其他倍率保留原拼写。

### 异常说明

调用者须先解析单位；非法模型沿用注册表检查。

返回类型：str。

源码：[`src/chronaxis/core/unit_registry.py:372`](../../../src/chronaxis/core/unit_registry.py#L372)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_build_atoms"></a>
## `_build_atoms`

建立有限原子表，不自动扩张SI前缀或读取外部定义。

```python
_build_atoms() -> dict[str, Unit]
```

参数：无显式参数。


### 参数说明

无。

### 返回说明

供模块初始化冻结的字典。

### 异常说明

注册项不一致时传播Unit验证错误。

返回类型：dict[str, [Unit](chronaxis.core.unit_registry.md#api-Unit)]。

源码：[`src/chronaxis/core/unit_registry.py:386`](../../../src/chronaxis/core/unit_registry.py#L386)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_build_preferred"></a>
## `_build_preferred`

登记倍率1的默认名称，不取用户参数顺序决定显示单位。

```python
_build_preferred() -> dict[tuple[int, ...], Unit]
```

参数：无显式参数。


### 参数说明

无。

### 返回说明

按量种索引的首选单位字典，初始化后冻结。

### 异常说明

模型错误直接传播。

返回类型：dict[tuple[int, ...], [Unit](chronaxis.core.unit_registry.md#api-Unit)]。

源码：[`src/chronaxis/core/unit_registry.py:433`](../../../src/chronaxis/core/unit_registry.py#L433)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_Parser"></a>
## `_Parser`

用有限词元递归下降解析单位；未知原子保留None但仍检查完整语法。

状态仅为本次词元tuple与读取位置，不跨计划缓存，不执行输入文本。

```python
_Parser(text: str) -> None
```


源码：[`src/chronaxis/core/unit_registry.py:454`](../../../src/chronaxis/core/unit_registry.py#L454)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_Parser-__init__"></a>
### `_Parser.__init__`

构建有限词元流。

```python
_Parser.__init__(text: str) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`text`|str|是|无|位置或关键字。text为长度已检查的非空单位文本。|

#### 返回说明

None。

#### 异常说明

ValueError为词元数量超限。

返回类型：None。

源码：[`src/chronaxis/core/unit_registry.py:460`](../../../src/chronaxis/core/unit_registry.py#L460)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_Parser-peek"></a>
### `_Parser.peek`

查看当前词元，不推进位置。

```python
_Parser.peek() -> str | None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

当前文本或流尾None。

#### 异常说明

无。

返回类型：str &#124; None。

源码：[`src/chronaxis/core/unit_registry.py:474`](../../../src/chronaxis/core/unit_registry.py#L474)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_Parser-factor"></a>
### `_Parser.factor`

解析原子或括号表达式及可选整数幂。

```python
_Parser.factor() -> Unit | None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

已知Unit或未知原子的None。

#### 异常说明

ValueError为语法、幂或已知单位运算错误。

返回类型：[Unit](chronaxis.core.unit_registry.md#api-Unit) &#124; None。

源码：[`src/chronaxis/core/unit_registry.py:484`](../../../src/chronaxis/core/unit_registry.py#L484)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_Parser-expression"></a>
### `_Parser.expression`

按同级左结合解析乘除，完整检查未知项旁的已知非法温度。

```python
_Parser.expression() -> Unit | None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

已知Unit，含未知原子时为None。

#### 异常说明

ValueError为语法或单位组合错误。

返回类型：[Unit](chronaxis.core.unit_registry.md#api-Unit) &#124; None。

源码：[`src/chronaxis/core/unit_registry.py:521`](../../../src/chronaxis/core/unit_registry.py#L521)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-resolve_unit"></a>
## `resolve_unit`

解析登记单位和受限复合文本，未知原子返回None。

```python
resolve_unit(text: str) -> Unit | None
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`text`|str|是|无|位置或关键字。text为最多256字符的非空文本，允许首尾空白。|

### 返回说明

Unit或None；语法正确的未知单位不伪装为verified。

### 异常说明

TypeError为非文本；ValueError为空、语法、资源或非法单位组合。

返回类型：[Unit](chronaxis.core.unit_registry.md#api-Unit) &#124; None。

源码：[`src/chronaxis/core/unit_registry.py:545`](../../../src/chronaxis/core/unit_registry.py#L545)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
