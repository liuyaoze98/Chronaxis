# chronaxis.planning.nodes

检查计算条件、窗口和指标配置，保存静态依赖与边界声明。

输入是节点配置及当前信号绑定，输出RulePlan、WindowPlan和CalculationPlan。
表达式仅接受受控语法，条件结果必须为布尔类型；窗口区分持续活动与时间点，
指标区分全会话、原事件和合并片段范围。检查引用、类型、单位及同步声明后，
节点按用户顺序保存。本模块不读来源或DBC，不运行时序规则或积分；
可配置的节点不等于运行接入完成，实际能力由计划报告说明。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)、[CalculationPlan](chronaxis.planning.models.md#api-CalculationPlan)、[D](chronaxis.core.types.md#api-SignalDType)、[Interval](chronaxis.core.models.md#api-Interval)、[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)、[RulePlan](chronaxis.planning.models.md#api-RulePlan)、[StabilitySpec](chronaxis.core.stability.md#api-StabilitySpec)、[StartEndSpec](chronaxis.core.start_end.md#api-StartEndSpec)、[WindowDeltaSpec](chronaxis.core.window_delta.md#api-WindowDeltaSpec)、[WindowPlan](chronaxis.planning.models.md#api-WindowPlan)

## 对象导航

|对象|用途|
|---|---|
|[`expression_at`](#api-expression_at)|检查表达式声明，并将语法、类型或时钟错误关联到配置位置。|
|[`register_id`](#api-register_id)|将一个合法节点ID登记到本计划的名称集合。|
|[`parse_rules`](#api-parse_rules)|检查普通布尔规则或数值窗口规则，保存参数与静态依赖。|
|[`parse_windows`](#api-parse_windows)|检查事件窗口锚点、前后扩展和合并参数，不改变原事件声明。|
|[`parse_calculations`](#api-parse_calculations)|检查指标统计范围、信号、条件、单位和覆盖政策。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..core.expression import validate_expression
from ..core.calculations import CalculationDefinition, calculation_unit
from ..core.models import Interval
from ..core.types import SignalDType as D
from ..core.units import UNIT_TABLE
from ..core.window_delta import WindowDeltaSpec
from ..core.stability import StabilitySpec
from ..core.start_end import StartEndSpec
from .checks import PlanValidationError, array_at, choice_at, duration_at, model_at, number_at, object_at, text_at
from .models import CalculationPlan, RulePlan, WindowPlan
```

</details>

<a id="api-expression_at"></a>
## `expression_at`

检查表达式声明，并将语法、类型或时钟错误关联到配置位置。

```python
expression_at(text, path, bindings, derived, *, boolean=False, unit=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`text`|str|是|无|位置或关键字。使用已绑定简单别名的表达式文本。|
|`path`|str|是|无|位置或关键字。表达式对应的配置位置。|
|`bindings`|DeclarationBindings|是|无|位置或关键字。当前会话的名称、来源和时间声明关系。|
|`derived`|tuple|是|无|位置或关键字。全部派生定义，供依赖展开和循环检查。|
|`boolean`|bool|否|False|仅关键字。默认False；True时要求结果为布尔类型。|
|`unit`|str &#124; None|否|None|仅关键字。可选输出单位，默认None，按表达式推导。|

### 返回说明

StaticExpression。保留类型、单位和依赖，尚未读取数据或执行计算。

### 异常说明

PlanValidationError: 受控语法、名称、依赖、类型、单位或同步声明不合法。

源码：[`src/chronaxis/planning/nodes.py:24`](../../../src/chronaxis/planning/nodes.py#L24)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-register_id"></a>
## `register_id`

将一个合法节点ID登记到本计划的名称集合。

```python
register_id(raw, path, ids) -> str
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`raw`|str|是|无|位置或关键字。用户声明的节点ID。|
|`path`|str|是|无|位置或关键字。ID对应的配置位置。|
|`ids`|set[str]|是|无|位置或关键字。本计划已经使用的节点名字集合；解析成功后把新名字加入，遇到重复名字报错。它是本次解析的可变工作集合，不是原始信号值。|

### 返回说明

str。原ID保持不变，并加入ids。

### 异常说明

PlanValidationError: ID非法或已经存在，不自动改名或覆盖。

### 副作用说明

只修改传入的局部集合，不注册全局名称。

返回类型：str。

源码：[`src/chronaxis/planning/nodes.py:49`](../../../src/chronaxis/planning/nodes.py#L49)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-parse_rules"></a>
## `parse_rules`

检查普通布尔规则或数值窗口规则，保存参数与静态依赖。

```python
parse_rules(value, bindings, derived, ids) -> tuple[RulePlan, ...]
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|list|是|无|位置或关键字。规则配置数组。|
|`bindings`|DeclarationBindings|是|无|位置或关键字。当前来源和名称声明关系。|
|`derived`|tuple|是|无|位置或关键字。完整派生定义。|
|`ids`|set[str]|是|无|位置或关键字。本计划已经使用的节点名字集合；解析成功后把新名字加入，遇到重复名字报错。它是本次解析的可变工作集合，不是原始信号值。|

### 返回说明

tuple[RulePlan, ...]。保持规则顺序，参数按kind互斥；不产生事件或活动状态。

### 异常说明

PlanValidationError: 字段、ID、kind、条件类型、初始触发或持续参数错误。

返回类型：tuple[[RulePlan](chronaxis.planning.models.md#api-RulePlan), ...]。

源码：[`src/chronaxis/planning/nodes.py:75`](../../../src/chronaxis/planning/nodes.py#L75)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-parse_windows"></a>
## `parse_windows`

检查事件窗口锚点、前后扩展和合并参数，不改变原事件声明。

```python
parse_windows(value, rules, ids) -> tuple[WindowPlan, ...]
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|list|是|无|位置或关键字。窗口配置数组。|
|`rules`|tuple[[RulePlan](chronaxis.planning.models.md#api-RulePlan), ...]|是|无|位置或关键字。可引用的已检查规则。|
|`ids`|set[str]|是|无|位置或关键字。本计划已经使用的节点名字集合；解析成功后把新名字加入，遇到重复名字报错。它是本次解析的可变工作集合，不是原始信号值。|

### 返回说明

tuple[WindowPlan, ...]。持续规则只能使用activity锚点，其余使用point。
    exit_delay要求activity且post为0，start_only的post须等于固定窗口时长。

### 异常说明

PlanValidationError: 引用、ID、锚点、扩展时间或合并参数冲突。

### 副作用说明

登记窗口ID，但不运行合并或生成片段。

返回类型：tuple[[WindowPlan](chronaxis.planning.models.md#api-WindowPlan), ...]。

源码：[`src/chronaxis/planning/nodes.py:173`](../../../src/chronaxis/planning/nodes.py#L173)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-parse_calculations"></a>
## `parse_calculations`

检查指标统计范围、信号、条件、单位和覆盖政策。

```python
parse_calculations(value, bindings, derived, rules, windows, execution, ids) -> tuple[CalculationPlan, ...]
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|list|是|无|位置或关键字。指标配置数组。|
|`bindings`|DeclarationBindings|是|无|位置或关键字。当前名称及来源同步声明。|
|`derived`|tuple|是|无|位置或关键字。完整派生定义，用于静态依赖展开。|
|`rules`|tuple[[RulePlan](chronaxis.planning.models.md#api-RulePlan), ...]|是|无|位置或关键字。原事件范围可引用的规则。|
|`windows`|tuple[[WindowPlan](chronaxis.planning.models.md#api-WindowPlan), ...]|是|无|位置或关键字。片段范围可引用的窗口。|
|`execution`|ExecutionPlan|是|无|位置或关键字。提供默认partial_policy。|
|`ids`|set[str]|是|无|位置或关键字。本计划已经使用的节点名字集合；解析成功后把新名字加入，遇到重复名字报错。它是本次解析的可变工作集合，不是原始信号值。|

### 返回说明

tuple[CalculationPlan, ...]。保存全会话、原事件或片段范围，明确样本统计、
    时间统计和选择行等口径；只检查声明，不生成数值或结果行。

### 异常说明

PlanValidationError: 算子、ID、引用、信号类型、条件、单位或覆盖政策错误。

### 处理流程说明

范围条件、数值信号和选择条件的原始依赖一起检查同步声明。
    select保留原单位；积分仅接受左侧保持'zoh'；其他算子拒绝method字段。

返回类型：tuple[[CalculationPlan](chronaxis.planning.models.md#api-CalculationPlan), ...]。

源码：[`src/chronaxis/planning/nodes.py:244`](../../../src/chronaxis/planning/nodes.py#L244)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
