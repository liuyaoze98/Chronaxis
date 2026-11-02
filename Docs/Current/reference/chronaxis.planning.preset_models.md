# chronaxis.planning.preset_models

定义预设配置及其角色要求。例如充电预设需要电流角色，角色可要求特定单位、方向或测量位置。展开后的规则、窗口和指标仍是普通分析配置，可以保存为JSON。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)、[DerivedDefinition](chronaxis.core.expression.md#api-DerivedDefinition)、[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)、[SequencePlan](chronaxis.planning.sequences.md#api-SequencePlan)、[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)、[WindowSpec](chronaxis.core.windows.md#api-WindowSpec)

## 对象导航

|对象|用途|
|---|---|
|[`RoleContract`](#api-RoleContract)|公开本预设版本的角色类型、单位、语义候选、方向与位置要求。|
|[`PresetSpec`](#api-PresetSpec)|冻结预设ID、preset_type/version、角色别名及工程参数的独立JSON快照。|
|[`PresetSpec.__post_init__`](#api-PresetSpec-__post_init__)|检查公开spec结构并复制冻结，不运行数据计算。|
|[`PresetSpec.from_dict`](#api-PresetSpec-from_dict)|从当前配置的预设对象构造公开不可变声明。|
|[`RoleBinding`](#api-RoleBinding)|保存已通过字段契约的角色及其原信号定义，供调用者追溯转换与来源。|
|[`PresetRule`](#api-PresetRule)|保存生成的持续、rising_edge或迟滞声明，尚未绑定来源时钟或执行状态。|
|[`PresetCalculation`](#api-PresetCalculation)|保存按原活动范围计算的积分或时长声明及独立覆盖/数据不全时的处理方式。|
|[`PlanFragment`](#api-PlanFragment)|预设生成的一组派生量、规则、窗口、指标及配对配置，合并进完整分析计划后执行。它不包含真实样本，也不会自行读取文件；生成的节点ID仍需与用户配置中的ID保持唯一。|
|[`PlanFragment.to_dict`](#api-PlanFragment-to_dict)|将类型化片段序列化为当前配置节点副本；没有配对时省略空sequences键。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from collections.abc import Mapping
from dataclasses import dataclass
from ..core.binding import SignalDefinition
from ..core.expression import DerivedDefinition
from ..core.types import SignalDType as D
from ..core.windows import WindowSpec
from .checks import PlanValidationError, choice_at, json_value, metadata_at, object_at, require_json_value, text_at
from .sequences import SequencePlan
```

</details>

<a id="api-RoleContract"></a>
## `RoleContract`

公开本预设版本的角色类型、单位、语义候选、方向与位置要求。

有效期必须由SignalDefinition明确提供且正；基础质量使用其固定九位禁用策略。
semantic_id/version仅用于自动查找，显式绑定仍逐字段检查，不能只凭版本宣称符合。

```python
class RoleContract
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`role`|str|是|无|mode/current/voltage/alarm；不注册全量领域名称。|
|`dtypes`|tuple[[D](chronaxis.core.types.md#api-SignalDType), ...]|是|无|转换后的可接受逻辑类型。|
|`unit`|str|是|无|精确目标单位，关系须verified。|
|`semantic_id`|str|是|无|本模块v1候选标识，大小写敏感。|
|`sign_convention`|str &#124; None|否|None|需要时为明确转换后方向。 None表示该角色不约束正负方向。|
|`measurement_location`|str &#124; None|否|None|需要时为明确测量位置。 None表示该角色不约束测量位置。|
|`version`|str|否|'1'|本公开候选契约版本。|
|`forbidden_quality`|int|否|511|核心已定义九位基础质量全部禁止。|

源码：[`src/chronaxis/planning/preset_models.py:23`](../../../src/chronaxis/planning/preset_models.py#L23)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-PresetSpec"></a>
## `PresetSpec`

冻结预设ID、preset_type/version、角色别名及工程参数的独立JSON快照。

id只用简单标识；role_bindings值只引用当前计划简单别名，不能写领域属性路径。
parameters不保留调用者可变对象，实际preset_type参数在build_preset中统一校验。

```python
PresetSpec(id: str, preset_type: str, version: str, role_bindings: collections.abc.Mapping, parameters: collections.abc.Mapping) -> None
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`id`|str|是|无|设置本预设实例唯一名称，例如hot；生成规则和计算使用此前缀，须避免与已有节点重名。|
|`preset_type`|str|是|无|选择任务：charge_session分析充电，fault_context提取故障前后文，command_response配对请求响应，threshold_excursion累计阈值报警。各类型的角色和参数见预设指南。|
|`version`|str|是|无|选择预设模板版本，当前填写字符串"1"；不是整数1，也不是顶层config_version。|
|`role_bindings`|Mapping|是|无|将业务角色关联到signals中已定义的分析名，例如{"signal": "temperature"}。允许角色由preset_type决定；省略角色时须符合语义声明自动查找要求。|
|`parameters`|Mapping|是|无|提供所选预设的业务参数字典，例如阈值预设的unit、enter_threshold、exit_threshold。值来自业务阈值和设备单位；各类型字段不能互相套用，完整选项见预设指南。|

源码：[`src/chronaxis/planning/preset_models.py:52`](../../../src/chronaxis/planning/preset_models.py#L52)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-PresetSpec-__post_init__"></a>
### `PresetSpec.__post_init__`

检查公开spec结构并复制冻结，不运行数据计算。

```python
PresetSpec.__post_init__()
```

参数：无显式参数。


#### 参数说明

无；读取构造字段。

#### 返回说明

None，字段保存独立只读副本。

#### 异常说明

PlanValidationError为名称、版本、JSON结构或角色别名错误。

本函数直接报告的具体错误：

- `PlanValidationError`：$.preset。

源码：[`src/chronaxis/planning/preset_models.py:65`](../../../src/chronaxis/planning/preset_models.py#L65)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-PresetSpec-from_dict"></a>
### `PresetSpec.from_dict`

从当前配置的预设对象构造公开不可变声明。

```python
PresetSpec.from_dict(value)
```

装饰器：`classmethod`。

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|dict[str, object]|是|无|位置或关键字。预设配置字典：name、preset_type和parameters必填；version省略为字符串1，role_bindings省略为空映射。角色映射与业务约束见[业务预设](../presets.md)。|

#### 返回说明

PresetSpec，role_bindings缺省为空。

#### 异常说明

PlanValidationError为未知键、缺项或构造协议错误。

#### 调用示例

```python
from chronaxis import PresetSpec

# 构造预设声明；绑定和阈值的完整语义在组装计划时继续检查。
spec = PresetSpec.from_dict({
    "name": "heat_alarm",
    "preset_type": "threshold_excursion",
    "version": "1",
    "role_bindings": {"signal": "temperature"},
    "parameters": {"unit": "degC", "enter_threshold": 80, "exit_threshold": 75},
})
print(spec.id, spec.preset_type)

```

源码：[`src/chronaxis/planning/preset_models.py:90`](../../../src/chronaxis/planning/preset_models.py#L90)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RoleBinding"></a>
## `RoleBinding`

保存已通过字段契约的角色及其原信号定义，供调用者追溯转换与来源。

自动/显式查找方式不同，但definition保留完整来源、单位、方向转换和质量身份。
不保存样本值，也不伪称元数据的物理事实已由系统测量核实。

```python
class RoleBinding
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`contract`|[RoleContract](chronaxis.planning.preset_models.md#api-RoleContract)|是|无|本次实际校验的v1角色。|
|`definition`|[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)|是|无|原不可变完整绑定，包含转换证据。|
|`resolution`|str|是|无|`"explicit"`表示用户通过role_bindings指定了信号；`"semantic_unique"`表示按semantic_id和角色要求恰好找到了一个符合要求的信号。|

源码：[`src/chronaxis/planning/preset_models.py:103`](../../../src/chronaxis/planning/preset_models.py#L103)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-PresetRule"></a>
## `PresetRule`

保存生成的持续、rising_edge或迟滞声明，尚未绑定来源时钟或执行状态。

condition是由合法简单别名/原生有限常量生成的受限DSL；正常计划编译仍检查类型和依赖。
selection_origin仅持续规则为onset，point没有持续选择；实例不产生事件。

```python
class PresetRule
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`id`|str|是|无|生成节点ID。|
|`rule_type`|str|是|无|condition_duration、rising_edge或hysteresis。|
|`condition`|str &#124; None|是|无|公共DSL；迟滞改用两个明确条件。|
|`minimum_duration_ns`|int &#124; None|否|None|duration门槛，单位ns。 None表示此规则不使用持续时长门槛。|
|`selection_origin`|str &#124; None|否|None|计算每次活动的时长、平均值或积分时，决定是否计入确认前的等待时间。"onset"从条件开始成立时统计，包含等待时间；"confirmed"从满足持续时长要求时统计，不包含等待时间。例如第1秒开始、第3秒确认、第6秒结束，分别统计5秒和3秒；功率恒为10W时，积分分别为50J和30J。事件仍保留原始开始及确认时间。duration规则需填写上述字符串，其他规则使用None。充电预设自动生成的duration规则采用"onset"。见[等待时间的对照例子](../rules.md#duration-selection-origin)。|
|`emit_initial`|bool|否|False|rising_edge首次初始化政策。|
|`enter_condition`|str &#124; None|否|None|迟滞进入条件，普通规则不使用。 None用于不需要单独进入条件的规则。|
|`exit_condition`|str &#124; None|否|None|迟滞退出条件。 None用于不需要单独退出条件的规则。|
|`enter_delay_ns`|int|否|0|进入确认等待，纳秒。|
|`exit_delay_ns`|int|否|0|退出确认等待，纳秒。|

源码：[`src/chronaxis/planning/preset_models.py:116`](../../../src/chronaxis/planning/preset_models.py#L116)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-PresetCalculation"></a>
## `PresetCalculation`

保存按原活动范围计算的积分或时长声明及独立覆盖/数据不全时的处理方式。

积分signal是公共信号或派生别名，unit为Wh/Ah；condition_duration用明确BOOL条件和秒。
partial_policy=None表示继承execution，不是默认强制strict；覆盖质量由既有CalculationDefinition判断。

```python
class PresetCalculation
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`id`|str|是|无|生成指标ID。|
|`scope`|str|是|无|event:生成活动ID。|
|`signal`|str &#124; None|是|无|简单别名；condition-only duration不提供。|
|`unit`|str|是|无|明确积分输出单位。|
|`minimum_coverage`|int &#124; float|否|0|0—1，只影响覆盖质量判断。|
|`partial_policy`|str &#124; None|否|None|`"report"`：数据不全时保留已知部分算出的数值，并标记partial；`"strict"`：所需范围内有数据缺失时返回None。它不会补出缺失数据。 None表示此对象未设置该项；是否继承默认设置由其所属计划决定。|
|`operation`|str|否|'integral'|integral或按实际事件区间计算duration。|
|`condition`|str &#124; None|否|None|duration可用恒真条件计整个已知活动区间。 None表示没有额外选择条件，统计范围内全部有效值。|

源码：[`src/chronaxis/planning/preset_models.py:136`](../../../src/chronaxis/planning/preset_models.py#L136)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-PlanFragment"></a>
## `PlanFragment`

预设生成的一组派生量、规则、窗口、指标及配对配置，合并进完整分析计划后执行。它不包含真实样本，也不会自行读取文件；生成的节点ID仍需与用户配置中的ID保持唯一。

```python
PlanFragment(derived: tuple[chronaxis.core.expression.DerivedDefinition, ...] = (), rules: tuple[chronaxis.planning.preset_models.PresetRule, ...] = (), windows: tuple[chronaxis.core.windows.WindowSpec, ...] = (), calculations: tuple[chronaxis.planning.preset_models.PresetCalculation, ...] = (), sequences: tuple[chronaxis.planning.sequences.SequencePlan, ...] = ()) -> None
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`derived`|tuple[[DerivedDefinition](chronaxis.core.expression.md#api-DerivedDefinition), ...]|否|()|预设生成的派生量配置；空元组表示没有新增派生量。|
|`rules`|tuple[[PresetRule](chronaxis.planning.preset_models.md#api-PresetRule), ...]|否|()|预设生成的检测规则；空元组表示没有新增规则。|
|`windows`|tuple[[WindowSpec](chronaxis.core.windows.md#api-WindowSpec), ...]|否|()|预设生成的事件窗口配置；空元组表示没有新增窗口。|
|`calculations`|tuple[[PresetCalculation](chronaxis.planning.preset_models.md#api-PresetCalculation), ...]|否|()|预设生成的指标配置；空元组表示没有新增指标。|
|`sequences`|tuple[[SequencePlan](chronaxis.planning.sequences.md#api-SequencePlan), ...]|否|()|读取预设生成的SequencePlan元组；没有配对任务时为空。to_dict()将非空项转换为可合入完整配置的sequences列表。|

源码：[`src/chronaxis/planning/preset_models.py:154`](../../../src/chronaxis/planning/preset_models.py#L154)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-PlanFragment-to_dict"></a>
### `PlanFragment.to_dict`

将类型化片段序列化为当前配置节点副本；没有配对时省略空sequences键。

```python
PlanFragment.to_dict()
```

参数：无显式参数。


#### 参数说明

无；读取生成的不可变声明。

#### 返回说明

dict，可合入AnalysisPlan.from_dict；不含伪造来源或执行结果。

#### 异常说明

无主动异常；实例由build_preset构造。

源码：[`src/chronaxis/planning/preset_models.py:167`](../../../src/chronaxis/planning/preset_models.py#L167)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
