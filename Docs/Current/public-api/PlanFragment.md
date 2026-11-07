# chronaxis.PlanFragment

使用`from chronaxis import PlanFragment`导入。本页只列直接公开成员与必要的构造/上下文协议；内部实现见[模块参考](../reference/chronaxis.planning.preset_models.md)。

返回[公开API索引](../api.md)。参数表中的类型可跳转到定义；先核对必填、默认值与返回/异常说明。

## 成员导航

- [`PlanFragment`](#api-PlanFragment)
- [`PlanFragment.to_dict`](#api-PlanFragment-to_dict)

<a id="api-PlanFragment"></a>
## `PlanFragment`

预设生成的一组派生量、规则、窗口、指标及配对配置，合并进完整分析计划后执行。它不包含真实样本，也不会自行读取文件；生成的节点ID仍需与用户配置中的ID保持唯一。

```python
PlanFragment(derived: tuple[chronaxis.core.expression.DerivedDefinition, ...] = (), rules: tuple[chronaxis.planning.preset_models.PresetRule, ...] = (), windows: tuple[chronaxis.core.windows.WindowSpec, ...] = (), calculations: tuple[chronaxis.planning.preset_models.PresetCalculation, ...] = (), sequences: tuple[chronaxis.planning.sequences.SequencePlan, ...] = ()) -> None
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`derived`|tuple[[DerivedDefinition](../reference/chronaxis.core.expression.md#api-DerivedDefinition), ...]|否|()|预设生成的派生量配置；空元组表示没有新增派生量。|
|`rules`|tuple[[PresetRule](../reference/chronaxis.planning.preset_models.md#api-PresetRule), ...]|否|()|预设生成的检测规则；空元组表示没有新增规则。|
|`windows`|tuple[[WindowSpec](../reference/chronaxis.core.windows.md#api-WindowSpec), ...]|否|()|预设生成的事件窗口配置；空元组表示没有新增窗口。|
|`calculations`|tuple[[PresetCalculation](../reference/chronaxis.planning.preset_models.md#api-PresetCalculation), ...]|否|()|预设生成的指标配置；空元组表示没有新增指标。|
|`sequences`|tuple[[SequencePlan](../reference/chronaxis.planning.sequences.md#api-SequencePlan), ...]|否|()|读取预设生成的SequencePlan元组；没有配对任务时为空。to_dict()将非空项转换为可合入完整配置的sequences列表。|

源码：[`src/chronaxis/planning/preset_models.py:154`](../../../src/chronaxis/planning/preset_models.py#L154)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

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

源码：[`src/chronaxis/planning/preset_models.py:167`](../../../src/chronaxis/planning/preset_models.py#L167)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
