# chronaxis.AnalysisPlan

使用`from chronaxis import AnalysisPlan`导入。本页只列直接公开成员与必要的构造/上下文协议；内部实现见[模块参考](../reference/chronaxis.planning.plan.md)。

返回[公开API索引](../api.md)。参数表中的类型可跳转到定义；先核对必填、默认值与返回/异常说明。

## 成员导航

- [`AnalysisPlan`](#api-AnalysisPlan)
- [`AnalysisPlan.extensions`](#api-AnalysisPlan-extensions)
- [`AnalysisPlan.lookups`](#api-AnalysisPlan-lookups)
- [`AnalysisPlan.from_dict`](#api-AnalysisPlan-from_dict)

<a id="api-AnalysisPlan"></a>
## `AnalysisPlan`

保存一个会话的分析配置，以及静态检查得到的对象。

通过from_dict或load_analysis_plan构建，依次保存输入来源、信号、派生计算、
条件规则、窗口与指标。实例字段不能重新赋值；原配置及自由元数据
保存为独立的只读快照，不保留调用者可变字典或列表的引用。

bindings只描述“哪个信号来自哪里”，derived_expressions是已检查的
表达式结构；二者不表示真实数据已经读取或能够直接运行。
execution与outputs保存执行及输出声明，创建本类不会启动计算或发布文件。

identity由配置和来源定位声明计算，用于区分计划；不能据此断言CSV内容、
实际列、内存使用或分析结果已核实。各次构建的绑定和声明相互独立。

```python
AnalysisPlan(config_version: int, dataset: chronaxis.planning.models.DatasetPlan, sources: tuple[chronaxis.planning.models.SourcePlan, ...], signals: tuple[chronaxis.planning.models.SignalPlan, ...], derived: tuple[chronaxis.planning.models.DerivedPlan, ...], rules: tuple[chronaxis.planning.models.RulePlan, ...], windows: tuple[chronaxis.planning.models.WindowPlan, ...], calculations: tuple[chronaxis.planning.models.CalculationPlan, ...], presets: tuple[chronaxis.planning.preset_models.PresetSpec, ...], preset_bindings: tuple[tuple[chronaxis.planning.preset_models.RoleBinding, ...], ...], execution: chronaxis.planning.models.ExecutionPlan, outputs: chronaxis.planning.models.OutputPlan, bindings: chronaxis.core.declarations.DeclarationBindings, derived_expressions: tuple[chronaxis.core.expression.StaticExpression, ...], metadata: collections.abc.Mapping, raw_config: collections.abc.Mapping, base_dir: pathlib.Path, identity: str, message_calculations: tuple[chronaxis.planning.models.MessageCalculationPlan, ...] = (), sequences: tuple[chronaxis.planning.sequences.SequencePlan, ...] = (), intervals: 'IntervalPlan | None' = None, diagnostics: 'DiagnosticPlan | None' = None, aggregations: tuple[chronaxis.planning.aggregations.AggregationPlan, ...] = (), transforms: tuple[chronaxis.planning.transforms.TemporalTransformPlan, ...] = ()) -> None
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`config_version`|int|是|无|保存已加载配置的结构版本，接受整数3和4。通常调用load_analysis_plan(path)或AnalysisPlan.from_dict(config)建立整个计划，不逐字段手工拼接。|
|`dataset`|[DatasetPlan](../reference/chronaxis.planning.models.md#api-DatasetPlan)|是|无|分析对象、会话和请求时间范围。|
|`sources`|tuple[[SourcePlan](../reference/chronaxis.planning.models.md#api-SourcePlan), ...]|是|无|已解析的来源配置，保持用户声明顺序。|
|`signals`|tuple[[SignalPlan](../reference/chronaxis.planning.models.md#api-SignalPlan), ...]|是|无|原字段与信号名称、类型、单位及有效期声明。|
|`derived`|tuple[[DerivedPlan](../reference/chronaxis.planning.models.md#api-DerivedPlan), ...]|是|无|由已有信号计算的新信号，例如功率及其元数据。|
|`rules`|tuple[[RulePlan](../reference/chronaxis.planning.models.md#api-RulePlan), ...]|是|无|已经检查的布尔条件和时序规则。|
|`windows`|tuple[[WindowPlan](../reference/chronaxis.planning.models.md#api-WindowPlan), ...]|是|无|已检查的活动或时间点窗口，以及所引用的规则。|
|`calculations`|tuple[[CalculationPlan](../reference/chronaxis.planning.models.md#api-CalculationPlan), ...]|是|无|统计指标及其范围、计算口径、单位和缺失数据策略。|
|`presets`|tuple[[PresetSpec](PresetSpec.md#api-PresetSpec), ...]|是|无|原预设v1声明，冻结并保留生成参数。|
|`preset_bindings`|tuple[tuple[[RoleBinding](../reference/chronaxis.planning.preset_models.md#api-RoleBinding), ...], ...]|是|无|保存预设角色与实际信号的对应关系。加载计划时产生，外层元组与plan.presets顺序一致；内层每个RoleBinding保存contract（角色要求）、definition（选中的原信号定义）、resolution（explicit显式指定或semantic_unique唯一语义匹配）。没有预设时外层为()。使用zip(plan.presets, plan.preset_bindings)配对，再读取binding.definition.name等；见下方调用示例。|
|`execution`|[ExecutionPlan](../reference/chronaxis.planning.models.md#api-ExecutionPlan)|是|无|计算方式、分批大小和资源预算声明，尚未实际执行。|
|`outputs`|[OutputPlan](../reference/chronaxis.planning.models.md#api-OutputPlan)|是|无|结果表及清单的格式声明，尚未写出文件。|
|`bindings`|[DeclarationBindings](../reference/chronaxis.core.declarations.md#api-DeclarationBindings)|是|无|名称与来源之间的声明关系，不含实际读取的信号值。|
|`derived_expressions`|tuple[[StaticExpression](../reference/chronaxis.core.expression.md#api-StaticExpression), ...]|是|无|全部派生表达式的检查结果，已拒绝循环依赖。|
|`metadata`|Mapping|是|无|调用者附加的只读元数据，不改变计算规则。|
|`raw_config`|Mapping|是|无|解析时保存的内部只读配置快照，不是用户原文，省略字段也未必全部写回。字段可能为内部解析形式；需要可编辑的当前公共配置时使用config resolve。|
|`base_dir`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|相对来源路径的解释基准，保存为绝对路径。|
|`identity`|str|是|无|配置及来源定位声明的SHA-256哈希，不是文件内容哈希。|
|`message_calculations`|tuple[[MessageCalculationPlan](../reference/chronaxis.planning.models.md#api-MessageCalculationPlan), ...]|否|()|保存message_calculations配置解析后的逐消息计算项元组；空元组表示没有此类计算。与普通calculations分别执行。|
|`sequences`|tuple[[SequencePlan](../reference/chronaxis.planning.sequences.md#api-SequencePlan), ...]|否|()|保存sequences配置解析后的请求/响应配对元组；空元组表示不进行配对。|
|`intervals`|'[IntervalPlan](../reference/chronaxis.planning.intervals.md#api-IntervalPlan) &#124; None'|否|None|当前记录流的有限间隔声明。|
|`diagnostics`|'[DiagnosticPlan](../reference/chronaxis.planning.intervals.md#api-DiagnosticPlan) &#124; None'|否|None|分别声明追溯、完整性检查与现场留存。|
|`aggregations`|tuple[[AggregationPlan](../reference/chronaxis.planning.aggregations.md#api-AggregationPlan), ...]|否|()|本计划中已通过检查的结果聚合定义，按声明顺序保存。默认空元组表示无需订阅任何结果总体。|
|`transforms`|tuple[[TemporalTransformPlan](../reference/chronaxis.planning.transforms.md#api-TemporalTransformPlan), ...]|否|()|编译后的时序变换元组，所依赖的变换先于使用它的变换。|

### 调用示例

```python
from chronaxis import load_analysis_plan

# 从仓库根目录运行；此文件已定义所需来源、信号和预设。
plan = load_analysis_plan("Docs/Current/examples/preset-charge-minimal.yaml")
for preset, bindings in zip(plan.presets, plan.preset_bindings):
    for binding in bindings:
        print(preset.id, binding.contract.role,
              binding.definition.name, binding.resolution)
# demo_preset mode mode explicit
# demo_preset current current explicit
```

源码：[`src/chronaxis/planning/plan.py:63`](../../../src/chronaxis/planning/plan.py#L63)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-AnalysisPlan-extensions"></a>
### `AnalysisPlan.extensions`

读取计划使用的宿主注册。

```python
AnalysisPlan.extensions
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

ExtensionRegistry或None。

#### 异常说明

无。

源码：[`src/chronaxis/planning/plan.py:109`](../../../src/chronaxis/planning/plan.py#L109)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-AnalysisPlan-lookups"></a>
### `AnalysisPlan.lookups`

读取本配置声明的标定表。

```python
AnalysisPlan.lookups
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

LookupTablePlan 元组。

#### 异常说明

无。

源码：[`src/chronaxis/planning/plan.py:114`](../../../src/chronaxis/planning/plan.py#L114)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-AnalysisPlan-from_dict"></a>
### `AnalysisPlan.from_dict`

复制配置字典，按唯一支持的版本4检查静态要求；执行能力由所选后端决定。

```python
AnalysisPlan.from_dict(config: dict, *, base_dir: Path | str | None=None, extensions=None) -> 'AnalysisPlan'
```

装饰器：`classmethod`, `public_errors`, `diagnose_plan`。

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`config`|dict[str, object]|是|无|位置或关键字。当前公开分析配置字典，含config_version（4）、dataset、sources和signals；不接受未展开imports。目录声明会枚举文件名，缺省CAN元数据时读取DBC；不读取业务记录。见[配置字段参考](../configuration-reference.md)。|
|`base_dir`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) &#124; str &#124; None|否|None|仅关键字。相对来源路径的解释基准；默认None， 使用当前工作目录。传入Path或文本时转换为绝对路径。|
|`extensions`|ExtensionRegistry &#124; None|否|None|仅关键字。宿主为版本4分析显式创建的注册表；省略时没有可额外调用的宿主操作。|

#### 返回说明

AnalysisPlan: 保存经过静态检查的来源、信号及计算节点。
        raw_config和metadata是独立的只读快照；创建计划不读取分析数据。

#### 异常说明

PlanValidationError: 字段或版本不合法，名称冲突、表达式或引用错误，
        输入模型不合规，或配置请求尚未接入的能力；错误保留配置位置。
    OSError: 获取当前工作目录或转换路径时发生系统错误，可原样传播。

#### 处理流程说明

检查当前公开配置并展开节点，解析来源和信号；目录声明枚举文件名，缺省CAN元数据从DBC补全。随后检查引用、类型与单位，构造独立计划；不读取业务记录或执行分析。

返回类型：'[AnalysisPlan](AnalysisPlan.md#api-AnalysisPlan)'。

源码：[`src/chronaxis/planning/plan.py:121`](../../../src/chronaxis/planning/plan.py#L121)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
