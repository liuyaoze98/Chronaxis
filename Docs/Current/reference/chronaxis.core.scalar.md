# `chronaxis.core.scalar`

保存数值及枚举的声明类型、有效性和质量原因。

ScalarValue 是模型和数值计算共同使用的不可变数据对象。它只依赖基础类型和
原生标量校验，不导入信号模型、绑定或计算模块，供这些模块安全地共同引用。
公开入口仍由 chronaxis.core.numeric 和 chronaxis.core 重导出同一个类。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[QualityFlag](chronaxis.core.types.md#api-QualityFlag)、[SignalDType](chronaxis.core.types.md#api-SignalDType)

## 对象导航

|对象|用途|
|---|---|
|[`ScalarValue`](#api-ScalarValue)|保存一个值的声明类型、有效性和质量原因。|
|[`ScalarValue.__post_init__`](#api-ScalarValue-__post_init__)|检查值与声明类型是否一致，并核对有效性和质量原因。|
|[`_scalar_from_validated_fields`](#api-_scalar_from_validated_fields)|从同次运行已核的数值列或已有标量构造共享值，不重复检查声明。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass, field
from math import isfinite
from types import MappingProxyType
from .types import QualityFlag, SignalDType
from .validation import require_scalar, require_text
```

</details>

<a id="api-ScalarValue"></a>
## `ScalarValue`

保存一个值的声明类型、有效性和质量原因。

valid只能是bool，且当且仅当quality为NONE时为True。有质量问题的value
可保留原始诊断，例如None或NaN，但不能作为正常数值参加后续计算。
有效整数必须落在dtype对应的定宽范围内，有效float64必须有限。
枚举使用labels中的文本值；labels是不可变的固定标签域，比较时必须同域。
实例不可重新赋值，不持有跨时间或跨分析任务的状态。

```python
class ScalarValue
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; float &#124; bool &#124; str &#124; None|是|无|正常值或无效原诊断。|
|`dtype`|[SignalDType](chronaxis.core.types.md#api-SignalDType)|是|无|SignalDType枚举成员：INT64是有符号64位整数，UINT64是无符号64位整数，FLOAT64是双精度浮点，BOOL是真/假，ENUM是预先声明的状态标签。这里传枚举成员，不传字符串；当前运算支持哪些类型仍见本对象的约束。|
|`valid`|bool|否|True|无效不代表正常0。|
|`quality`|[QualityFlag](chronaxis.core.types.md#api-QualityFlag)|否|QualityFlag.NONE|输入原因和计算失败原因。|
|`labels`|tuple[str, ...]|否|()|仅enum有固定公开逻辑域。|
|`code`|'[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue) &#124; None'|否|None|仅 enum_code 需要的原整数，可与标签有不同有效性。|
|`partial`|bool|否|False|此值是否使用了可估算但覆盖不全的变换输入；有效数值可以同时携带这个标志。|

源码：[`src/chronaxis/core/scalar.py:21`](../../../src/chronaxis/core/scalar.py#L21)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ScalarValue-__post_init__"></a>
### `ScalarValue.__post_init__`

检查值与声明类型是否一致，并核对有效性和质量原因。

```python
ScalarValue.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无显式参数；读取value、dtype、valid、quality和labels。

#### 返回说明

None。保留输入声明，不自动转换类型、补零或清除质量原因。

#### 异常说明

TypeError: 字段类型或枚举标签域结构不合法。
    ValueError: 有效性与质量矛盾，浮点值非有限或枚举值不在声明域内。
    OverflowError: 有效整数超出声明类型的定宽范围。

返回类型：None。

源码：[`src/chronaxis/core/scalar.py:39`](../../../src/chronaxis/core/scalar.py#L39)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_scalar_from_validated_fields"></a>
## `_scalar_from_validated_fields`

从同次运行已核的数值列或已有标量构造共享值，不重复检查声明。

```python
_scalar_from_validated_fields(value, dtype, valid=True, quality=QualityFlag.NONE, labels=(), code=None, *, partial=False)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; float &#124; bool &#124; str &#124; None|是|无|位置或关键字。同次运行已经验证的逻辑值或无效诊断值；新算术结果必须先完成范围和有限性检查。|
|`dtype`|[SignalDType](chronaxis.core.types.md#api-SignalDType)|是|无|位置或关键字。已验证的声明类型，不从value重新推断。|
|`valid`|bool|否|True|位置或关键字。已证明与quality一致的有效性，不能用此入口绕过外部输入检查。|
|`quality`|[QualityFlag](chronaxis.core.types.md#api-QualityFlag)|否|QualityFlag.NONE|位置或关键字。已核对范围的质量原因；有效值使用NONE。|
|`labels`|tuple[str, ...]|否|()|位置或关键字。已验证的不可变枚举标签域；非枚举为空tuple。|
|`code`|[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue) &#124; None|否|None|位置或关键字。需要保留的枚举原始整数值及其独立质量；不需要时为None。|
|`partial`|bool|否|False|仅关键字。已确定的部分窗口标志；不改变valid或伪造完整结果。|

### 返回说明

字段完全相同的冻结ScalarValue，不保存检查标志或额外副本。

### 异常说明

分配错误原样传播。仅限内部调用，公开构造仍完整验证。

源码：[`src/chronaxis/core/scalar.py:109`](../../../src/chronaxis/core/scalar.py#L109)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
