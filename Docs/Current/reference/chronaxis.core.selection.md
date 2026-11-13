# `chronaxis.core.selection`

声明已解码信号层的选择行，保留时间、原值、三值状态和来源身份。

输入为CalculationSeries和select请求，输出由各独立后端逐行迭代SelectionRow。
TRUE行是已知选中；UNKNOWN行用于保留无法决定的诊断，消费方必须检查selection。
FALSE行被过滤。只输出目标表达式依赖的真实时间组更新，不伪造裁剪或TTL样本。
本模块仅验证不可变协议，不计算筛选掩码、不读写文件、不改变旧读取或解码。
来源定位是绑定字段与时间组，不宣称保存旧日志的物理行号或分别用每条消息中的值计算表达式序号。
输入仍为完整内存历史；逐行输出不意味着AnalysisRunner的内存预算已经实现。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)、[CalculationSeries](chronaxis.core.calculations.md#api-CalculationSeries)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)、[SourceRef](chronaxis.core.models.md#api-SourceRef)、[Truth](chronaxis.core.types.md#api-Truth)

## 对象导航

|对象|用途|
|---|---|
|[`SelectionRow`](#api-SelectionRow)|保存一个真实表达式更新时间组的选择结果。|
|[`SelectionRow.__post_init__`](#api-SelectionRow-__post_init__)|验证行类型、时间和当前来源身份，不执行筛选。|
|[`require_selection`](#api-require_selection)|验证选择行流的输入及当前版本允许的单位换算。|
|[`partial_selection`](#api-partial_selection)|处理来自部分时间窗口的选中值，不更改真实行身份。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from .calculations import CalculationSeries, CalculationDefinition, calculation_conversion
from .models import SourceRef
from .numeric import ScalarValue
from .types import Truth, QualityFlag as Q
from .validation import require_text
from ..timebase.conversion import require_int64_ns
```

</details>

<a id="api-SelectionRow"></a>
## `SelectionRow`

保存一个真实表达式更新时间组的选择结果。

value保存输出dtype、枚举标签、有效性和质量；selection仅接受TRUE或UNKNOWN。
quality汇总原依赖、值及条件原因；binding_identity与source_refs定位当前输入。
unit与当前行值一致；允许已核实的目标单位换算。
所有字段不可变，没有跨任务状态；UNKNOWN不是已知选中，不能隐式转bool。

```python
class SelectionRow
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|原子更新时间组的精确纳秒时间。|
|`value`|[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)|是|无|原带有明确类型的值，未知不填正常零，枚举不输出内部整数编码。|
|`selection`|[Truth](chronaxis.core.types.md#api-Truth)|是|无|TRUE选中或UNKNOWN诊断，不包含明确FALSE行。|
|`quality`|[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)|是|无|原值、条件与依赖的完整质量原因。|
|`binding_identity`|str|是|无|当前表达式/选择条件的实际执行身份。|
|`source_refs`|tuple[[SourceRef](chronaxis.core.models.md#api-SourceRef), ...]|是|无|当前所有依赖的原字段定位。|
|`unit`|str|是|无|当前分析值单位，和原带有明确类型的值一起保留。|

源码：[`src/chronaxis/core/selection.py:23`](../../../src/chronaxis/core/selection.py#L23)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SelectionRow-__post_init__"></a>
### `SelectionRow.__post_init__`

验证行类型、时间和当前来源身份，不执行筛选。

```python
SelectionRow.__post_init__()
```

参数：无显式参数。


#### 参数说明

无；读取创建后不可修改的字段。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError/OverflowError为不合法协议。

本函数直接报告的具体错误：

- `TypeError`：选择行需带有明确类型的值、TRUE/UNKNOWN及QualityFlag。
- `TypeError`：选择行来源需tuple SourceRef。
- `ValueError`：选择行质量不能隐藏无效值或UNKNOWN原因。

源码：[`src/chronaxis/core/selection.py:40`](../../../src/chronaxis/core/selection.py#L40)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-require_selection"></a>
## `require_selection`

验证选择行流的输入及当前版本允许的单位换算。

```python
require_selection(series, spec)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`series`|[CalculationSeries](chronaxis.core.calculations.md#api-CalculationSeries)|是|无|位置或关键字。当前计算窗口的数值片段和真实样本；有条件计算时还包含对应的TRUE、FALSE或UNKNOWN选择状态。|
|`spec`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|位置或关键字。当前指标请求，指定运算、窗口、结果单位及部分数据的处理方式。|

### 返回说明

返回None，不返回额外的计算值。

### 异常说明

TypeError为模型错误；ValueError为算子或单位转换请求。

本函数直接报告的具体错误：

- `TypeError`：选择行流需CalculationSeries和CalculationDefinition。
- `ValueError`：选择行流需select且保留输入单位。

源码：[`src/chronaxis/core/selection.py:62`](../../../src/chronaxis/core/selection.py#L62)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-partial_selection"></a>
## `partial_selection`

处理来自部分时间窗口的选中值，不更改真实行身份。

```python
partial_selection(value, quality, spec)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)|是|无|位置或关键字。已经完成输出单位换算的选择值，保留其是否基于部分窗口的标记。|
|`quality`|QualityFlag|是|无|位置或关键字。该选择行原有的诊断位；部分输入还要携带ESTIMATED。|
|`spec`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|位置或关键字。本次select请求；report保留部分值，strict不提供一个正常数值。|

### 返回说明

值及行质量；strict 不提供正常值。

### 异常说明

值契约不合法时传播。

源码：[`src/chronaxis/core/selection.py:79`](../../../src/chronaxis/core/selection.py#L79)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
