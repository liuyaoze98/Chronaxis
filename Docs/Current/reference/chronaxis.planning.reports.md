# chronaxis.planning.reports

解释已构建计划的声明检查结果、计算依赖和当前能力限制。

输入为AnalysisPlan，validate_analysis_plan生成ValidationReport，explain_analysis_plan
生成ExplainReport，列出依赖节点、需要保留的历史时长和预算声明。
报告不重新读取CSV或DBC，不运行旧reader或数值内核。
valid与execution_ready表示当前声明使用已接入的公共执行路径；带有明确类型的计划被
替换为不支持的来源、算子或后端时会报告明确errors。静态可执行不证明来源
已读、真实字段已核实或峰值RAM一定满足预算。预算与历史需求不是实测结果。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)、[CANFramesOutput](chronaxis.planning.export_options.md#api-CANFramesOutput)、[CANTextSpec](chronaxis.sources.text_can_spec.md#api-CANTextSpec)、[DiagnosticPlan](chronaxis.planning.intervals.md#api-DiagnosticPlan)、[InputRequirements](chronaxis.planning.input_requirements.md#api-InputRequirements)、[IntervalPlan](chronaxis.planning.intervals.md#api-IntervalPlan)、[LegacyCANSpec](chronaxis.sources.can_spec.md#api-LegacyCANSpec)、[MessageCalculationPlan](chronaxis.planning.models.md#api-MessageCalculationPlan)、[SignalCSVOutput](chronaxis.planning.export_options.md#api-SignalCSVOutput)、[SignalCSVSpec](chronaxis.sources.csv_spec.md#api-SignalCSVSpec)、[SourceSpec](chronaxis.core.models.md#api-SourceSpec)

## 对象导航

|对象|用途|
|---|---|
|[`ValidationReport`](#api-ValidationReport)|一次配置检查的报告。valid说明配置是否通过检查；execution_ready说明当前版本是否具备所需执行能力。文件、字段和DBC尚未读取时，会在报告中注明；这两个标志不代表实际数据已经验证或分析完成。|
|[`ExplainNode`](#api-ExplainNode)|保存单声明节点的实际依赖和预计执行层。|
|[`ExplainReport`](#api-ExplainReport)|保存计划依赖、历史需求和未执行的预算声明。|
|[`_window_available`](#api-_window_available)|核窗口是否引用当前支持的真实规则、锚点与合并路径。|
|[`_can_source_available`](#api-_can_source_available)|核一个带有明确类型的来源是否具有当前单BLF固定profile的声明能力。|
|[`_static_errors`](#api-_static_errors)|依据已构建带有明确类型的声明检查公共执行路径，不重新解析配置或输入。|
|[`validate_analysis_plan`](#api-validate_analysis_plan)|报告静态配置有效性及当前读取、执行和发布能力限制。|
|[`explain_analysis_plan`](#api-explain_analysis_plan)|列出计划依赖、各节点计算方式、历史需求和预算声明。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from types import MappingProxyType
from collections.abc import Mapping
from .plan import AnalysisPlan
from .models import MessageCalculationPlan
from .message_calculations import require_message_calculation
from .legacy_execution import require_can_decode_scope
from .input_requirements import InputRequirements, collect_input_requirements
from .sequences import sequence_dependencies
from .intervals import IntervalPlan, DiagnosticPlan, require_interval_declarations
from .export_options import require_export_options, SignalCSVOutput, CANFramesOutput
from ..core.models import SourceSpec
from ..sources.csv_spec import SignalCSVSpec
from ..sources.can_spec import LegacyCANSpec, can_field_from_key
from ..sources.text_can_spec import CANTextSpec
from ..legacy.records import PROFILE_ID
```

</details>

<a id="api-ValidationReport"></a>
## `ValidationReport`

一次配置检查的报告。valid说明配置是否通过检查；execution_ready说明当前版本是否具备所需执行能力。文件、字段和DBC尚未读取时，会在报告中注明；这两个标志不代表实际数据已经验证或分析完成。

```python
class ValidationReport
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`valid`|bool|是|无|读取静态声明是否通过：True表示无静态错误，False时查看errors；不证明输入文件已读取。|
|`errors`|tuple[str, ...]|是|无|读取导致静态校验失败的原因元组；无错误为空元组。|
|`warnings`|tuple[str, ...]|是|无|读取未核实的来源信息或能力限制；空元组不代替真实数据验收。|
|`capability_status`|Mapping[str, str]|是|无|读取各能力名称到状态的映射：implemented已实现，partial部分支持，unavailable不可用，declared仅有声明。结合warnings判断当前计划限制。|
|`execution_ready`|bool|是|无|读取当前计划是否使用已接入公共执行路径：True可尝试运行，False应先解决errors；不保证文件存在或实际内存足够。|

源码：[`src/chronaxis/planning/reports.py:40`](../../../src/chronaxis/planning/reports.py#L40)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ExplainNode"></a>
## `ExplainNode`

保存单声明节点的实际依赖和预计执行层。

backend说明数组/状态驱动或尚未接入可运行流程，不把整个NumPy计划假称全数组化。

```python
class ExplainNode
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`node_id`|str|是|无|读取被解释的派生量、规则、窗口、配对或计算ID，来自本计划声明。|
|`node_type`|str|是|无|读取节点类别，如derived、rule、window、sequence、calculation或message_calculation，用于定位相应配置章节。|
|`dependencies`|tuple[str, ...]|是|无|读取该节点展开后依赖的原始分析信号名称元组；不是CSV列名。|
|`unit`|str &#124; None|是|无|读取该节点适用的结果单位；没有单位时为None。|
|`backend`|str|是|无|读取该节点预计采用的计算方式：reference参考实现、numpy数组实现、state_driver状态计算或unavailable不可执行；尚未运行。|

源码：[`src/chronaxis/planning/reports.py:54`](../../../src/chronaxis/planning/reports.py#L54)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ExplainReport"></a>
## `ExplainReport`

保存计划依赖、历史需求和未执行的预算声明。

validation沿用静态能力报告，plan_identity只识别配置和来源定位声明。
source_names保持来源顺序，nodes保存计算节点和展开的原信号依赖。
history_ns仅对实际普通样本依赖，按valid_for_ns和窗口pre取需要保留的时长；
显式all额外产生的诊断样本不计作结果需求，warnings单独说明其读取与核验范围。
budget原样报告资源限额。实例不保存运行状态，也不估算实测峰值内存。
input_requirements保存各来源实际选择的检查策略和时间范围；它是计划声明，
不能代替运行结果记录的实际检查计数和来源观测证明。

```python
class ExplainReport
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`validation`|[ValidationReport](chronaxis.planning.reports.md#api-ValidationReport)|是|无|读取同一计划的ValidationReport；先检查它的errors和warnings再判断是否可运行。|
|`plan_identity`|str|是|无|读取配置声明的身份摘要；不等于输入文件内容哈希。|
|`source_names`|tuple[str, ...]|是|无|读取sources中来源名称的元组，保持声明顺序。|
|`nodes`|tuple[[ExplainNode](chronaxis.planning.reports.md#api-ExplainNode), ...]|是|无|读取各依赖节点的ExplainNode元组；按node_id定位配置，再查看dependencies和backend。|
|`history_ns`|Mapping[str, int &#124; None]|是|无|读取每个信号预计需要保留的历史时长，单位纳秒；None表示仍需读取DBC周期确定，不能按0处理。|
|`budget`|Mapping[str, int &#124; None]|是|无|读取配置声明的资源预算映射；数值是计划限制，None表示该项没有数值预算，不是实际测得峰值。|
|`input_requirements`|[InputRequirements](chronaxis.planning.input_requirements.md#api-InputRequirements) &#124; None|否|None|读取计划要求的输入检查范围和策略；不合法的类型化计划可能为None。这是静态说明，实际检查结果在运行元数据中。|
|`intervals`|[IntervalPlan](chronaxis.planning.intervals.md#api-IntervalPlan) &#124; None|否|None|读取记录间隔声明IntervalPlan；包含配置选择，不包含运行时才取得的DBC周期。|
|`diagnostics`|[DiagnosticPlan](chronaxis.planning.intervals.md#api-DiagnosticPlan) &#124; None|否|None|读取诊断开关DiagnosticPlan；表示请求哪些诊断，不能证明这些诊断已执行。|

源码：[`src/chronaxis/planning/reports.py:68`](../../../src/chronaxis/planning/reports.py#L68)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_window_available"></a>
## `_window_available`

核窗口是否引用当前支持的真实规则、锚点与合并路径。

```python
_window_available(window, rules) -> bool
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`window`|WindowPlan|是|无|位置或关键字。window为原WindowPlan|
|`rules`|RulePlan|是|无|位置或关键字。rules为本计划rule_id到原RulePlan的映射。|

### 返回说明

bool，同一判断供validation和explain节点使用。

### 异常说明

非法带有明确类型的属性错误原样传播。

### 副作用说明

无，不构造窗口、事件或遍历输入样本。

返回类型：bool。

源码：[`src/chronaxis/planning/reports.py:91`](../../../src/chronaxis/planning/reports.py#L91)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_can_source_available"></a>
## `_can_source_available`

核一个带有明确类型的来源是否具有当前单BLF固定profile的声明能力。

```python
_can_source_available(source) -> bool
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|SourcePlan|是|无|位置或关键字。source为当前SourcePlan，允许调用方以带有明确类型的 replace制造不匹配声明。|

### 返回说明

bool，供来源、raw输出和能力表共享。

### 异常说明

非法外部对象属性错误原样传播。

### 副作用说明

只查有限模型字段，不打开输入、DBC、writer或重建原始配置。

返回类型：bool。

源码：[`src/chronaxis/planning/reports.py:107`](../../../src/chronaxis/planning/reports.py#L107)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_static_errors"></a>
## `_static_errors`

依据已构建带有明确类型的声明检查公共执行路径，不重新解析配置或输入。

```python
_static_errors(plan: AnalysisPlan) -> tuple[str, ...]
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)|是|无|位置或关键字。plan为已确认类型的AnalysisPlan，可含测试明确替换的不支持声明。|

### 返回说明

错误tuple；已支持的构建计划为空。

### 异常说明

非法模型属性错误原样传播。

### 边界说明

这不是第二套配置解析器，不重算AST、原rows、绑定或计划identity。

返回类型：tuple[str, ...]。

源码：[`src/chronaxis/planning/reports.py:120`](../../../src/chronaxis/planning/reports.py#L120)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-validate_analysis_plan"></a>
## `validate_analysis_plan`

报告静态配置有效性及当前读取、执行和发布能力限制。

```python
validate_analysis_plan(plan: AnalysisPlan) -> ValidationReport
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)|是|无|位置或关键字。提供已校验的AnalysisPlan，通过load_analysis_plan("analysis.yaml")取得，或用AnalysisPlan.from_dict(config)从Python字典建立；这里不接收YAML文件名字符串。|

### 返回说明

ValidationReport。合法已接入计划valid为True且errors为空；warnings保留尚未核实的
    字段、观测范围和单位状态，capability_status记录当前接入情况。
    execution_ready随静态能力错误为False或True，不表示已读取或保证实际RAM。

### 异常说明

TypeError: 输入不是AnalysisPlan；配置构建错误应由构建入口先报告。

本函数直接报告的具体错误：

- `TypeError`：validate_analysis_plan需要AnalysisPlan。

### 副作用说明

无来源读取，不重新核实CSV、BLF/DBC、实际字段或物理测量含义。

返回类型：[ValidationReport](chronaxis.planning.reports.md#api-ValidationReport)。

### 调用示例

```python
from chronaxis import load_analysis_plan, validate_analysis_plan
plan = load_analysis_plan("Docs/Current/examples/analysis.yaml")
report = validate_analysis_plan(plan)
print(report.valid, report.execution_ready)
```

源码：[`src/chronaxis/planning/reports.py:231`](../../../src/chronaxis/planning/reports.py#L231)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-explain_analysis_plan"></a>
## `explain_analysis_plan`

列出计划依赖、各节点计算方式、历史需求和预算声明。

```python
explain_analysis_plan(plan: AnalysisPlan) -> ExplainReport
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)|是|无|位置或关键字。提供已校验的AnalysisPlan，通过load_analysis_plan("analysis.yaml")取得，或用AnalysisPlan.from_dict(config)从Python字典建立；这里不接收YAML文件名字符串。|

### 返回说明

ExplainReport。包括同一校验限制、依赖节点、history_ns和budget只读映射。
    已有数值内核与尚未接入节点分别标记，不能将整份计划当作全数组执行。

### 异常说明

TypeError: 输入不是AnalysisPlan。

### 处理流程说明

展开派生、规则、窗口和指标依赖；事件或片段范围的条件也参与依赖收集。
    原信号有效期与所需窗口pre取较大时长，只报告需求，不修改输入读取范围。

### 副作用说明

不运行分析、不读取数据，也不测量内存峰值。

返回类型：[ExplainReport](chronaxis.planning.reports.md#api-ExplainReport)。

### 调用示例

```python
from chronaxis import load_analysis_plan, explain_analysis_plan
plan = load_analysis_plan("Docs/Current/examples/analysis.yaml")
print(explain_analysis_plan(plan))
```

源码：[`src/chronaxis/planning/reports.py:381`](../../../src/chronaxis/planning/reports.py#L381)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
