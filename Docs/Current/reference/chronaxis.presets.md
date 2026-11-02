# chronaxis.presets

把四种预设展开为普通规则、窗口、指标或请求响应配对。检查角色对应的信号类型、单位和必要语义，不读取输入；全部参数见[预设](../presets.md)。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)、[DerivedDefinition](chronaxis.core.expression.md#api-DerivedDefinition)、[PlanFragment](chronaxis.planning.preset_models.md#api-PlanFragment)、[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)、[PresetCalculation](chronaxis.planning.preset_models.md#api-PresetCalculation)、[PresetRule](chronaxis.planning.preset_models.md#api-PresetRule)、[PresetSpec](chronaxis.planning.preset_models.md#api-PresetSpec)、[RoleBinding](chronaxis.planning.preset_models.md#api-RoleBinding)、[RoleContract](chronaxis.planning.preset_models.md#api-RoleContract)、[SequencePlan](chronaxis.planning.sequences.md#api-SequencePlan)、[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)、[WindowSpec](chronaxis.core.windows.md#api-WindowSpec)

## 对象导航

|对象|用途|
|---|---|
|[`_parameters`](#api-_parameters)|按kind检查工程参数，保持原数值并将时长转换为整数ns。|
|[`_mismatches`](#api-_mismatches)|列出转换后声明未满足的角色字段，不能用自由metadata放宽质量。|
|[`resolve_preset_roles`](#api-resolve_preset_roles)|显式优先解析本次实际角色，否则按版本化语义契约寻找唯一合格候选。|
|[`build_preset`](#api-build_preset)|校验v1预设并展开公共声明，不执行I/O或数值分析。|
|[`expand_presets`](#api-expand_presets)|在独立配置副本中合入预设片段，保留用户节点并拒绝全部生成ID冲突。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .core.binding import SignalDefinition
from .core.expression import DerivedDefinition
from .core.types import SignalDType as D
from .core.windows import WindowSpec
from .planning.checks import PlanValidationError, choice_at, duration_at, json_value, array_at, number_at, object_at, text_at
from .planning.preset_models import RoleContract, RoleBinding, PresetSpec, PresetRule, PresetCalculation, PlanFragment, CHARGE_ROLES, FAULT_ROLES, COMMAND_ROLES
from .planning.sequences import SequencePlan
from .timebase.conversion import INT64_MIN, INT64_MAX
```

</details>

<a id="api-_parameters"></a>
## `_parameters`

按kind检查工程参数，保持原数值并将时长转换为整数ns。

```python
_parameters(spec, signals=())
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|[PresetSpec](chronaxis.planning.preset_models.md#api-PresetSpec)|是|无|位置或关键字。spec为PresetSpec|
|`signals`|tuple[[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition), ...]|否|()|位置或关键字。当前信号定义，供阈值预设省略unit时从已绑定signal角色取得单位；空元组不虚构候选。|

### 返回说明

新dict，仅内部使用已校验参数，不作为公开无类型片段。

### 异常说明

PlanValidationError为缺项、未知参数、bool伪数值、非有限或错误范围。

源码：[`src/chronaxis/presets.py:23`](../../../src/chronaxis/presets.py#L23)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_mismatches"></a>
## `_mismatches`

列出转换后声明未满足的角色字段，不能用自由metadata放宽质量。

```python
_mismatches(definition, contract, *, generic_unit=False)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`definition`|[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)|是|无|位置或关键字。definition为SignalDefinition|
|`contract`|[RoleContract](chronaxis.planning.preset_models.md#api-RoleContract)|是|无|位置或关键字。当前预设某个角色的要求，包含量纲、方向、测量位置等；与候选信号逐项比较并列出不匹配项。|
|`generic_unit`|bool|否|False|仅关键字。generic_unit允许明确同名无转换的自定义单位。|

### 返回说明

tuple[str, ...]，空表示字段契约通过，不证明真实数据正确。

### 异常说明

无主动异常；输入类型由公共解析入口证明。

源码：[`src/chronaxis/presets.py:78`](../../../src/chronaxis/presets.py#L78)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-resolve_preset_roles"></a>
## `resolve_preset_roles`

显式优先解析本次实际角色，否则按版本化语义契约寻找唯一合格候选。

```python
resolve_preset_roles(spec: PresetSpec, signals: tuple[SignalDefinition, ...]) -> tuple[RoleBinding, ...]
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|[PresetSpec](chronaxis.planning.preset_models.md#api-PresetSpec)|是|无|位置或关键字。提供PresetSpec预设声明，可用PresetSpec.from_dict({...})从必填name、preset_type、parameters，以及可选version、role_bindings的Python字典建立；完整可运行调用见预设API示例。|
|`signals`|tuple[[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition), ...]|是|无|位置或关键字。提供本计划的SignalDefinition元组，例如tuple(item.definition for item in plan.signals)，其中plan由load_analysis_plan取得；角色引用这些定义的name，不直接填CSV列名。|

### 返回说明

RoleBinding tuple，保留原定义与explicit/semantic_unique路径。

### 异常说明

PlanValidationError为类型、重复别名、未知角色、缺项、候选歧义或契约冲突。

- PlanValidationError：需要PresetSpec与SignalDefinition tuple。
- PlanValidationError：signal别名重复。
- PlanValidationError：threshold_excursion必须显式指定signal角色。

### 边界说明

显式别名无需semantic_id，仍检查类型/单位/方向/位置/质量；不选第一个候选。

返回类型：tuple[[RoleBinding](chronaxis.planning.preset_models.md#api-RoleBinding), ...]。

源码：[`src/chronaxis/presets.py:104`](../../../src/chronaxis/presets.py#L104)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-build_preset"></a>
## `build_preset`

校验v1预设并展开公共声明，不执行I/O或数值分析。

```python
build_preset(spec: PresetSpec, signals: tuple[SignalDefinition, ...]) -> PlanFragment
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|[PresetSpec](chronaxis.planning.preset_models.md#api-PresetSpec)|是|无|位置或关键字。提供PresetSpec预设声明，可用PresetSpec.from_dict({...})从必填name、preset_type、parameters，以及可选version、role_bindings的Python字典建立；完整可运行调用见预设API示例。|
|`signals`|tuple[[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition), ...]|是|无|位置或关键字。提供本计划的SignalDefinition元组，例如tuple(item.definition for item in plan.signals)，其中plan由load_analysis_plan取得；角色引用这些定义的name，不直接填CSV列名。|

### 返回说明

PlanFragment，生成请求的功率/Wh/Ah、报警、阈值迟滞/逐段时长或响应配对。

### 异常说明

PlanValidationError为参数/角色契约、模式编码范围及生成ID与信号冲突。

- PlanValidationError：模式编码超出已声明dtype/valid_range。

### 流程说明

检查角色→生成简单别名DSL→构造类型化节点→拒绝当前可见ID冲突。
    用户其他节点/多个预设的冲突由AnalysisPlan合入时继续检查。

返回类型：[PlanFragment](chronaxis.planning.preset_models.md#api-PlanFragment)。

源码：[`src/chronaxis/presets.py:158`](../../../src/chronaxis/presets.py#L158)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-expand_presets"></a>
## `expand_presets`

在独立配置副本中合入预设片段，保留用户节点并拒绝全部生成ID冲突。

```python
expand_presets(config, signals)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`config`|dict[str, object]|是|无|位置或关键字。调用方已复制的配置映射；本函数原地合入derived、rules、windows、calculations和sequences中的预设节点。|
|`signals`|tuple[[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition), ...]|是|无|位置或关键字。signals为当前SignalDefinition tuple。|

### 返回说明

(PresetSpec tuple, 各预设RoleBinding tuple)，供计划保留原声明及角色追溯。

### 异常说明

PlanValidationError为预设/用户结构或生成ID与用户/其他预设重名。

- PlanValidationError：derived必须为别名对象。
- PlanValidationError：节点必须包含id。

### 副作用说明

仅修改传入的局部derived/rules/windows/calculations/sequences；不修改raw_config快照或来源。

源码：[`src/chronaxis/presets.py:219`](../../../src/chronaxis/presets.py#L219)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
