# `chronaxis.planning.message_calculations`

静态解析当前消息legacy_sum声明，保持解码profile和新计算policy分开。

输入为message_calculations原生JSON数组、当前来源/绑定和计划ID集合；输出冻结的
MessageCalculationPlan tuple。frame_id必填，channel默认采用来源通道，帧类型可省略；参数按FLOAT64处理，表达式
只访问本来源、本消息的完整CAN定位，不沿用全局派生、上一条值或普通TTL。
当前模式明确拒绝cache_policy，旧完整触发/缓存尚未接入可运行流程不能靠同名字段冒充。
可选disjunction另声明方向别名和正负桶；方向可不在expr中，仍须有同一原消息
的完整定位。它选择本条原解码值，不改表达式、信号转换或旧读写调用。

require_message_calculation只检查已有带有明确类型的计划与当前来源/声明的关系，供解析和
validate/explain共用；它不重新解析AST或raw_config。所有操作只处理有限配置，
不open/stat/resolve，不加载DBC、旧reader或执行流，不读取任何分析输入。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CANTextSpec](chronaxis.sources.text_can_spec.md#api-CANTextSpec)、[DeclarationBindings](chronaxis.core.declarations.md#api-DeclarationBindings)、[ExpressionParameter](chronaxis.core.message_binding.md#api-ExpressionParameter)、[LegacyCANSpec](chronaxis.sources.can_spec.md#api-LegacyCANSpec)、[LegacyDisjunction](chronaxis.legacy.disjunction.md#api-LegacyDisjunction)、[LegacyMessageSelector](chronaxis.planning.models.md#api-LegacyMessageSelector)、[MessageCalculationPlan](chronaxis.planning.models.md#api-MessageCalculationPlan)、[MessageDeclarations](chronaxis.core.message_binding.md#api-MessageDeclarations)、[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)、[SignalDType](chronaxis.core.types.md#api-SignalDType)

## 对象导航

|对象|用途|
|---|---|
|[`require_message_calculation`](#api-require_message_calculation)|核已有带有明确类型的逐消息指标与当前计划一致，不借旧配置覆盖带有明确类型的替换。|
|[`parse_message_calculations`](#api-parse_message_calculations)|按声明顺序解析独立逐消息指标，ID与原规则/窗口/指标共用集合。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..core.declarations import DeclarationBindings
from ..core.message_binding import ExpressionParameter, MessageDeclarations
from ..legacy.records import PROFILE_ID
from ..legacy.disjunction import LegacyDisjunction
from ..core.types import SignalDType
from ..sources.can_spec import LegacyCANSpec, can_field_from_key
from ..sources.text_can_spec import CANTextSpec
from .diagnostic_collection import usable_node, collect_node_error
from .checks import PlanValidationError, array_at, choice_at, model_at, object_at, text_at
from .models import LegacyMessageSelector, MessageCalculationPlan
from .nodes import expression_at, register_id
```

</details>

<a id="api-require_message_calculation"></a>
## `require_message_calculation`

核已有带有明确类型的逐消息指标与当前计划一致，不借旧配置覆盖带有明确类型的替换。

```python
require_message_calculation(calculation, sources, bindings: DeclarationBindings) -> None
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`calculation`|[MessageCalculationPlan](chronaxis.planning.models.md#api-MessageCalculationPlan)|是|无|位置或关键字。calculation为MessageCalculationPlan|
|`sources`|tuple[SourcePlan, ...]|是|无|位置或关键字。sources为当前SourcePlan tuple|
|`bindings`|[DeclarationBindings](chronaxis.core.declarations.md#api-DeclarationBindings)|是|无|位置或关键字。bindings     为当前DeclarationBindings。|

### 返回说明

None，来源、帧定位和原声明均一致。

### 异常说明

TypeError为指标/绑定模型错误；ValueError为来源能力、声明或定位冲突。

本函数直接报告的具体错误：

- `TypeError`：逐消息指标需要MessageCalculationPlan及当前DeclarationBindings。
- `ValueError`：逐消息指标必须引用当前唯一来源。
- `ValueError`：逐消息计算仅支持已接入的单BLF/sclicer-functions-v1来源。
- `ValueError`：逐消息指标profile必须等于来源legacy_profile。
- `ValueError`：逐消息来源定位、原时基或offset与当前完整声明不符。
- `ValueError`：逐消息选择器channel与来源声明不一致。
- `ValueError`：逐消息表达式必须属于当前完整原声明、来源和参数。
- `ValueError`：逐消息表达式依赖与静态树不一致。
- `ValueError`：disjunction方向仅接受数值或bool声明，不接受enum。
- `ValueError`：逐消息依赖须保当前来源的同一原SignalDefinition。
- `ValueError`：逐消息依赖的完整帧定位与update_message不一致。
- `ValueError`：逐消息表达式的所有依赖必须属于同一原message。

### 边界说明

不重编译AST，不读DBC；字段存在性和单位实况仍由同次READY另行验证。

返回类型：None。

源码：[`src/chronaxis/planning/message_calculations.py:29`](../../../src/chronaxis/planning/message_calculations.py#L29)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-parse_message_calculations"></a>
## `parse_message_calculations`

按声明顺序解析独立逐消息指标，ID与原规则/窗口/指标共用集合。

```python
parse_message_calculations(value, sources, bindings, ids) -> tuple[MessageCalculationPlan, ...]
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|list[dict]|是|无|位置或关键字。message_calculations原始配置数组；逐项解析消息定位、公式、方向及贡献明细设置。|
|`sources`|tuple[SourcePlan, ...]|是|无|位置或关键字。当前计划已经解析的来源声明，用于检查指标引用的来源和CAN配置。|
|`bindings`|[DeclarationBindings](chronaxis.core.declarations.md#api-DeclarationBindings)|是|无|位置或关键字。当前计划的静态信号声明绑定，用于编译消息公式；此时还没有读取实际日志。|
|`ids`|set[str]|是|无|位置或关键字。本计划已经使用的节点名字集合；解析成功后把新名字加入，遇到重复名字报错。它是本次解析的可变工作集合，不是原始信号值。|

### 返回说明

MessageCalculationPlan tuple。

### 异常说明

PlanValidationError保具体JSON路径；cache_policy报旧完整缓存能力尚未接入可运行流程。

### 副作用说明

只向本次局部ids登记名称，不读输入、DBC或执行表达式。

返回类型：tuple[[MessageCalculationPlan](chronaxis.planning.models.md#api-MessageCalculationPlan), ...]。

源码：[`src/chronaxis/planning/message_calculations.py:99`](../../../src/chronaxis/planning/message_calculations.py#L99)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
