# `chronaxis.planning.transforms`

解析 v4 时序变换的名称图、时间网格、输入表达式及输出单位。

每个离散序列作为独立的分析来源声明，不向真实 reader 增加字段。先按表达式
引用拓扑校验所有声明（包括不用的声明），再给消费者提供同一套最终绑定。
本模块不扫描数据、不生成网格点，也不创建历史。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CalculationConversion](chronaxis.core.calculations.md#api-CalculationConversion)、[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)、[D](chronaxis.core.types.md#api-SignalDType)、[DeclaredSource](chronaxis.core.declarations.md#api-DeclaredSource)、[Interval](chronaxis.core.models.md#api-Interval)、[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)、[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)、[StaticExpression](chronaxis.core.expression.md#api-StaticExpression)、[TimeType](chronaxis.core.types.md#api-TimeType)

## 对象导航

|对象|用途|
|---|---|
|[`TemporalTransformPlan`](#api-TemporalTransformPlan)|按拓扑序保存一个已验证的离散变换，预算与运行状态在任务启动时创建。|
|[`_names`](#api-_names)|提取引用边。|
|[`build_transforms`](#api-build_transforms)|解析全图。|
|[`build_transforms.visit`](#api-build_transforms-visit)|按依赖先后检查循环。|
|[`active_transforms`](#api-active_transforms)|从消费者逆向收集必要变换。|
|[`physical_dependencies`](#api-physical_dependencies)|展开原采集依赖。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass, field, replace
from hashlib import sha256
from ..core.binding import SignalDefinition
from ..core.calculations import CalculationDefinition, CalculationConversion, calculation_conversion
from ..core.declarations import DeclaredSource
from ..core.expression import StaticExpression, validate_expression
from ..core.models import Interval
from ..core.types import SignalDType as D, TimeType
from .checks import PlanValidationError, array_at, canonical, choice_at, coordinate_at, duration_at, model_at, number_at, object_at, text_at
```

</details>

<a id="api-TemporalTransformPlan"></a>
## `TemporalTransformPlan`

按拓扑序保存一个已验证的离散变换，预算与运行状态在任务启动时创建。

```python
class TemporalTransformPlan
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|这条离散序列在统一数值名称空间中的简单别名。|
|`operation`|str|是|无|已选的滚动值、变化率或宿主注册时序操作。|
|`expression`|[StaticExpression](chronaxis.core.expression.md#api-StaticExpression)|是|无|已静态检查且展开依赖的输入表达式，运行前需要在实际来源上校验。|
|`output`|[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)|是|无|供下游规则/计算绑定的合成输出定义，包括来源身份、dtype、单位及有效期。|
|`conversion`|[CalculationConversion](chronaxis.core.calculations.md#api-CalculationConversion)|是|无|将变换自然结果换到最终输出尺度的静态转换描述。|
|`physical`|tuple[str, ...]|是|无|将上游变换递归展开后，本序列实际需要原始输入的别名集合。|
|`window_ns`|int &#124; None|是|无|网格算法的回看宽度，单位是所选实际或周期计量的纳秒；相邻差分不需要。|
|`step_ns`|int &#124; None|是|无|实际时间上相邻网格点之间的正纳秒间隔；相邻速率按右侧样本驱动。|
|`origin_ns`|int|是|无|分析时基上建立网格的实际时间原点，归一化为整数纳秒。|
|`max_gap_ns`|int &#124; None|是|无|相邻变化率可连接的最大实际间隔纳秒；网格操作没有此参数。|
|`partial_policy`|str|是|无|窗口不完整时的strict或report输出政策。|
|`minimum_coverage`|float|是|无|请求窗口中有效输入所需的最低权重占比，范围0到1。|
|`host_spec`|TransformSpec &#124; None|否|None|仅自定义网格保存其宿主描述，用于选择后端并预约有界状态。|

源码：[`src/chronaxis/planning/transforms.py:26`](../../../src/chronaxis/planning/transforms.py#L26)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_names"></a>
## `_names`

提取引用边。

```python
_names(text, path)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`text`|str|是|无|位置或关键字。需要从其受限表达式语法树中提取名称引用的配置文本。|
|`path`|str|是|无|位置或关键字。出现该表达式的配置路径，用于标明解析错误位置。|

### 返回说明

名称集合。

### 异常说明

带位置的语法错误。

源码：[`src/chronaxis/planning/transforms.py:44`](../../../src/chronaxis/planning/transforms.py#L44)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-build_transforms"></a>
## `build_transforms`

解析全图。

```python
build_transforms(raw, bindings, derived, *, timezone=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`raw`|list[dict]|是|无|位置或关键字。配置中transforms列表，包含显式名称、operation、expr及算法所需参数。|
|`bindings`|DeclarationBindings|是|无|位置或关键字。当前物理输入和可用定义的不可变声明，用于检查类型、单位及同步依据。|
|`derived`|tuple[DerivedDefinition, ...]|是|无|位置或关键字。与时序声明共同检查名称和循环的普通派生表达式表。|
|`timezone`|str &#124; None|否|None|仅关键字。解释带日期的绝对网格原点时使用的默认时区；相对时间不依赖此值。|

### 返回说明

最终声明和变换元组。

### 异常说明

配置错误。

源码：[`src/chronaxis/planning/transforms.py:53`](../../../src/chronaxis/planning/transforms.py#L53)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-build_transforms-visit"></a>
### `build_transforms.visit`

按依赖先后检查循环。

```python
build_transforms.visit(name)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|位置或关键字。当前深度优先检查的节点名；先检查依赖，再登记其拓扑位置。|

#### 返回说明

无。

#### 异常说明

包括派生/变换混合环。

源码：[`src/chronaxis/planning/transforms.py:82`](../../../src/chronaxis/planning/transforms.py#L82)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-active_transforms"></a>
## `active_transforms`

从消费者逆向收集必要变换。

```python
active_transforms(plan, aliases)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|AnalysisPlan|是|无|位置或关键字。包含已按依赖排序的全部时序声明的计划，供逆向裁剪。|
|`aliases`|Iterable[str]|是|无|位置或关键字。结果消费者实际请求的别名，作为向上追溯时序依赖的起点。|

### 返回说明

拓扑序元组。

### 异常说明

已建计划错误。

源码：[`src/chronaxis/planning/transforms.py:162`](../../../src/chronaxis/planning/transforms.py#L162)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-physical_dependencies"></a>
## `physical_dependencies`

展开原采集依赖。

```python
physical_dependencies(plan, aliases)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|AnalysisPlan|是|无|位置或关键字。含物理信号与合成时序声明的计划。|
|`aliases`|Iterable[str]|是|无|位置或关键字。需要展开的信号或时序别名，最终用于匹配实际原报文驱动。|

### 返回说明

保序去重原别名。

### 异常说明

已建计划错误。

源码：[`src/chronaxis/planning/transforms.py:173`](../../../src/chronaxis/planning/transforms.py#L173)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
