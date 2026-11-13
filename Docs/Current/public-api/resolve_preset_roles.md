# chronaxis.resolve_preset_roles

使用`from chronaxis import resolve_preset_roles`导入。本页只列直接公开成员与必要的构造/上下文协议；内部实现见[模块参考](../reference/chronaxis.presets.md)。

返回[公开API索引](../api.md)。参数表中的类型可跳转到定义；先核对必填、默认值与返回/异常说明。

## 成员导航

- [`resolve_preset_roles`](#api-resolve_preset_roles)

<a id="api-resolve_preset_roles"></a>
## `resolve_preset_roles`

显式优先解析本次实际角色，否则按版本化语义契约寻找唯一合格候选。

```python
resolve_preset_roles(spec: PresetSpec, signals: tuple[SignalDefinition, ...]) -> tuple[RoleBinding, ...]
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|[PresetSpec](PresetSpec.md#api-PresetSpec)|是|无|位置或关键字。提供PresetSpec预设声明，可用PresetSpec.from_dict({...})从必填name、preset_type、parameters，以及可选version、role_bindings的Python字典建立；完整可运行调用见预设API示例。|
|`signals`|tuple[[SignalDefinition](../reference/chronaxis.core.binding.md#api-SignalDefinition), ...]|是|无|位置或关键字。提供本计划的SignalDefinition元组，例如tuple(item.definition for item in plan.signals)，其中plan由load_analysis_plan取得；角色引用这些定义的name，不直接填CSV列名。|

### 返回说明

RoleBinding tuple，保留原定义与explicit/semantic_unique路径。

### 异常说明

PlanValidationError为类型、重复别名、未知角色、缺项、候选歧义或契约冲突。

- PlanValidationError：需要PresetSpec与SignalDefinition tuple。
- PlanValidationError：signal别名重复。
- PlanValidationError：threshold_excursion必须显式指定signal角色。

### 边界说明

显式别名无需semantic_id，仍检查类型/单位/方向/位置/质量；不选第一个候选。

返回类型：tuple[[RoleBinding](../reference/chronaxis.planning.preset_models.md#api-RoleBinding), ...]。

源码：[`src/chronaxis/presets.py:104`](../../../src/chronaxis/presets.py#L104)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
