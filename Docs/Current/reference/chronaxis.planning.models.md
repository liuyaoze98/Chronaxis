# `chronaxis.planning.models`

保存配置解析得到的来源、信号、计算节点和执行选项声明。

配置解析器先检查字段与引用，再构造本模块的冻结数据类；调用者的自由
元数据在解析边界复制为只读快照。输出记录分析对象、会话范围、来源定位、
显式信号转换、条件规则、窗口、统计指标、当前消息计算及预算和输出格式。
当前消息计算明确新policy，不表示旧完整触发/cache兼容。本层不读取数据、
不调用旧reader或DBC，也不运行表达式。
规则、窗口与预算是配置声明；实际可用能力由计划报告另行说明。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CANFramesOutput](chronaxis.planning.export_options.md#api-CANFramesOutput)、[CANTextSpec](chronaxis.sources.text_can_spec.md#api-CANTextSpec)、[DerivedDefinition](chronaxis.core.expression.md#api-DerivedDefinition)、[ExprNode](chronaxis.core.expression.md#api-ExprNode)、[ExpressionParameter](chronaxis.core.message_binding.md#api-ExpressionParameter)、[Interval](chronaxis.core.models.md#api-Interval)、[LegacyCANSpec](chronaxis.sources.can_spec.md#api-LegacyCANSpec)、[LegacyDisjunction](chronaxis.legacy.disjunction.md#api-LegacyDisjunction)、[MessageDeclarations](chronaxis.core.message_binding.md#api-MessageDeclarations)、[SignalCSVOutput](chronaxis.planning.export_options.md#api-SignalCSVOutput)、[SignalCSVSpec](chronaxis.sources.csv_spec.md#api-SignalCSVSpec)、[SignalDType](chronaxis.core.types.md#api-SignalDType)、[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)、[SourceSpec](chronaxis.core.models.md#api-SourceSpec)、[StabilitySpec](chronaxis.core.stability.md#api-StabilitySpec)、[StartEndSpec](chronaxis.core.start_end.md#api-StartEndSpec)、[StaticExpression](chronaxis.core.expression.md#api-StaticExpression)、[TimebaseSpec](chronaxis.core.models.md#api-TimebaseSpec)、[WindowDeltaSpec](chronaxis.core.window_delta.md#api-WindowDeltaSpec)

## 对象导航

|对象|用途|
|---|---|
|[`DatasetPlan`](#api-DatasetPlan)|保存单个分析对象、会话及请求时间范围。|
|[`SourcePlan`](#api-SourcePlan)|保存一个已支持来源种类的配置和定位声明。|
|[`SignalPlan`](#api-SignalPlan)|保存一个原字段到简单表达式别名的显式信号定义。|
|[`DerivedPlan`](#api-DerivedPlan)|保存由已有信号计算的新信号声明及可选语义信息。|
|[`RulePlan`](#api-RulePlan)|保存一条已经解析的事件检测规则。rule_id用于窗口和计算引用，rule_type选择检测方法；其余字段按类型填写。运行时由检测器产生事件；具体行为见[事件检测规则](../rules.md)。本对象时间字段使用整数纳秒，YAML配置使用带单位的时长。|
|[`RulePlan.__post_init__`](#api-RulePlan-__post_init__)|检查窗口、迟滞和开始/结束规则，保持原字段位置参数兼容。|
|[`RulePlan.temporal_rule_type`](#api-RulePlan-temporal_rule_type)|读取交给事件检测器的类型。|
|[`RulePlan.expressions`](#api-RulePlan-expressions)|列出规则全部静态条件。|
|[`RulePlan.dependencies`](#api-RulePlan-dependencies)|取得进出条件的去重依赖。|
|[`WindowPlan`](#api-WindowPlan)|一条已经解析的窗口配置，将指定规则的事件扩展成需要分析或导出的时间片段。例如活动在1～6秒，向前、向后各扩展1秒可得到0～7秒的请求范围；实际范围还需结合观测边界处理。|
|[`CalculationPlan`](#api-CalculationPlan)|一条已经解析的指标配置。指定计算哪个信号、用哪种运算，以及对整个会话、某次活动还是某个片段分别计算。on决定统计范围，op决定计算方法；其他字段说明缺失数据如何处理及输出单位。它不保存计算结果，结果由AnalysisRunner.run生成。|
|[`LegacyMessageSelector`](#api-LegacyMessageSelector)|明确选择当前消息计算的CAN帧，不猜旧profile的求值选择器默认。|
|[`LegacyMessageSelector.__post_init__`](#api-LegacyMessageSelector-__post_init__)|核原生类型和帧ID范围，不进行输入过滤或DBC查找。|
|[`MessageCalculationPlan`](#api-MessageCalculationPlan)|保存一个会话内按当前匹配消息逐次求值的明确计算声明。|
|[`MessageCalculationPlan.__post_init__`](#api-MessageCalculationPlan-__post_init__)|检查固定模式及静态消息表达式的一致性，不打开任何来源。|
|[`ExecutionPlan`](#api-ExecutionPlan)|本次分析的资源和读取设置，包括内存上限、分批大小、解码范围以及是否读取完整来源时间。各字段影响哪些工作会执行、怎样限制资源，不替代信号单位和时间基准的配置。完整例子见[运行参数](../execution.md)。|
|[`OutputPlan`](#api-OutputPlan)|保存新结果表和清单的输出格式声明。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass, field
from collections.abc import Mapping
from ..core.binding import SignalDefinition
from ..core.expression import DerivedDefinition, ExprNode, StaticExpression
from ..core.message_binding import ExpressionParameter, MessageDeclarations
from ..core.models import Interval, SourceSpec, TimebaseSpec
from ..core.types import SignalDType
from ..core.validation import require_identifier, require_text
from ..core.window_delta import WindowDeltaSpec
from ..core.stability import StabilitySpec
from ..core.start_end import StartEndSpec
from ..sources.csv_spec import SignalCSVSpec
from ..sources.can_spec import LegacyCANSpec
from ..sources.text_can_spec import CANTextSpec
from ..legacy.records import PROFILE_ID, normalize_frame_id
from ..legacy.disjunction import LegacyDisjunction
from .export_options import SignalCSVOutput, CANFramesOutput
```

</details>

<a id="api-DatasetPlan"></a>
## `DatasetPlan`

保存单个分析对象、会话及请求时间范围。

dataset_id与entity命名数据集和对象，session_id确定会话。
domain是用户请求的左闭右开区间，不证明实际输入已覆盖该范围。
domain_explicit区分用户时间筛选与domain=None的整文件声明；后者不能
当作观测时间或向运行结果报告为已采集范围。
timebase保存来源声明确定的分析时钟，metadata保存只读附加信息。
实例字段冻结，不维持运行状态。

```python
class DatasetPlan
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`dataset_id`|str|是|无|单计划数据集ID。|
|`entity`|str|是|无|分析对象ID，不内置车辆含义。|
|`session_id`|str|是|无|当前单会话ID。|
|`domain`|[Interval](chronaxis.core.models.md#api-Interval) &#124; None|是|无|用户请求半开范围；None为整文件无筛选，不能当作实际空范围。|
|`timebase`|[TimebaseSpec](chronaxis.core.models.md#api-TimebaseSpec)|是|无|同步分析基准。|
|`metadata`|Mapping|是|无|深冻结自由JSON元数据。|
|`domain_explicit`|bool|否|True|旧位置构造保留显式请求；False仅供合格整文件消息任务。|

源码：[`src/chronaxis/planning/models.py:34`](../../../src/chronaxis/planning/models.py#L34)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SourcePlan"></a>
## `SourcePlan`

保存一个已支持来源种类的配置和定位声明。

name是唯一来源名，source_type区分memory、signal_csv、can_blf、can_asc和raw_can_csv。
config保存对应静态来源规格，文本CAN使用CANTextSpec，供实际适配器构造。
time_unit与timezone_text记录时间表示；input_identity规范记录路径顺序、
格式和时间映射声明，不能证明文件内容。metadata是只读自由元数据。
CSV/BLF/DBC尚未打开，实际列、单位与范围留待读取核实；不创建适配器或持有句柄。

```python
class SourcePlan
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|当前唯一来源名。|
|`source_type`|str|是|无|来源种类：`memory`读配置中的记录，`signal_csv`读已解码的信号表，`can_blf`读BLF报文，`can_asc`读ASC报文，`raw_can_csv`读原始报文CSV。它们对应不同config对象，不能只改source_type就改变文件格式。|
|`config`|[SourceSpec](chronaxis.core.models.md#api-SourceSpec) &#124; [SignalCSVSpec](chronaxis.sources.csv_spec.md#api-SignalCSVSpec) &#124; [LegacyCANSpec](chronaxis.sources.can_spec.md#api-LegacyCANSpec) &#124; [CANTextSpec](chronaxis.sources.text_can_spec.md#api-CANTextSpec)|是|无|对应memory/信号表/旧BLF/新文本CAN。|
|`time_unit`|str|是|无|原时间表示单位。|
|`timezone_text`|str &#124; None|是|无|明确声明原时区文本。|
|`input_identity`|str|是|无|规范来源配置，包含路径顺序/格式/时间映射。|
|`metadata`|Mapping|是|无|深冻结自由元数据。|

源码：[`src/chronaxis/planning/models.py:55`](../../../src/chronaxis/planning/models.py#L55)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SignalPlan"></a>
## `SignalPlan`

保存一个原字段到简单表达式别名的显式信号定义。

definition包含原字段、类型、单位、转换和valid_for_ns有效期等契约。
有效期是有效样本最多保持的时长；None表示等待运行启动读取DBC周期，
不能用于计算状态。实际过期判断由时间驱动层按真实更新时间执行。
metadata独立冻结，不改变转换或基础质量规则。本类不保存信号值。

```python
class SignalPlan
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`definition`|[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)|是|无|当前信号的SignalDefinition；valid_for_ns可暂为None以等待DBC周期，不能以未解析定义执行状态计算。|
|`metadata`|Mapping|是|无|只读业务元数据，不把自由键当作周期、有效期或帧型配置。|

源码：[`src/chronaxis/planning/models.py:75`](../../../src/chronaxis/planning/models.py#L75)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-DerivedPlan"></a>
## `DerivedPlan`

保存由已有信号计算的新信号声明及可选语义信息。

definition保存名称、表达式和显式单位，类型由表达式静态检查推断。
semantic_id和semantic_contract_version声明语义及版本，sign_convention
与measurement_location声明方向及位置；这些字段不证明角色已核实。
metadata为只读附加信息。派生值不能另行声明更长有效期或覆盖推断类型，
实际有效性仍取决于输入依赖。本类不执行计算。

```python
class DerivedPlan
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`definition`|[DerivedDefinition](chronaxis.core.expression.md#api-DerivedDefinition)|是|无|名称/表达式/显式单位。|
|`semantic_id`|str &#124; None|是|无|新信号的含义标签，如 `"battery.power"`。|
|`semantic_contract_version`|str &#124; None|是|无|这项含义约定的版本，例如 `"1"`。|
|`sign_convention`|str &#124; None|是|无|结果正负的含义，如正功率表示输入能量；填写文字不改变公式。|
|`measurement_location`|str &#124; None|是|无|结果对应的测量位置，例如 `"pack_terminal"`。|
|`metadata`|Mapping|是|无|新信号的备注。|

源码：[`src/chronaxis/planning/models.py:89`](../../../src/chronaxis/planning/models.py#L89)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-RulePlan"></a>
## `RulePlan`

保存一条已经解析的事件检测规则。rule_id用于窗口和计算引用，rule_type选择检测方法；其余字段按类型填写。运行时由检测器产生事件；具体行为见[事件检测规则](../rules.md)。本对象时间字段使用整数纳秒，YAML配置使用带单位的时长。

```python
class RulePlan
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`rule_id`|str|是|无|唯一规则ID。|
|`rule_type`|str|是|无|选择检测方法：condition_duration持续条件、rising_edge由假变真、falling_edge由真变假、start_only触发后抑制重复、window_delta窗口变化、hysteresis迟滞、debounce去抖、start_end起止活动。必须用这些精确名称；各自必需字段见规则指南。|
|`condition`|[StaticExpression](chronaxis.core.expression.md#api-StaticExpression)|是|无|普通BOOL树或window_delta数值树，不能直接执行。|
|`minimum_duration_ns`|int &#124; None|是|无|仅condition_duration，非负纳秒。|
|`selection_origin`|str &#124; None|是|无|计算每次活动的时长、平均值或积分时，决定是否计入确认前的等待时间。"onset"从条件开始成立时统计，包含等待时间；"confirmed"从满足持续时长要求时统计，不包含等待时间。例如第1秒开始、第3秒确认、第6秒结束，分别统计5秒和3秒；功率恒为10W时，积分分别为50J和30J。事件仍保留原始开始及确认时间。直接构造RulePlan时必须传入这个字段：condition_duration填上述字符串，其他规则填None。YAML配置中它是可选字段，condition_duration省略时采用"onset"。见[等待时间的对照例子](../rules.md#duration-selection-origin)。|
|`emit_initial`|bool|是|无|边沿/start_only初始化策略。|
|`window_duration_ns`|int &#124; None|是|无|仅start_only正抑制窗口。|
|`window_delta`|[WindowDeltaSpec](chronaxis.core.window_delta.md#api-WindowDeltaSpec) &#124; None|否|None|window_delta规则的完整回看契约。 None用于其他规则种类。|
|`retrigger`|str|否|'edge'|`"edge"`在条件不满足后再次满足时可重新触发；`"once"`在本次分析中最多触发一次。|
|`stability`|[StabilitySpec](chronaxis.core.stability.md#api-StabilitySpec) &#124; None|否|None|debounce/hysteresis的独立进入/退出防抖时长。 None表示不采用debounce或hysteresis规则。|
|`exit_condition`|[StaticExpression](chronaxis.core.expression.md#api-StaticExpression) &#124; None|否|None|hysteresis或start_end的独立退出条件。 None用于不需要独立退出表达式的规则。|
|`start_end`|[StartEndSpec](chronaxis.core.start_end.md#api-StartEndSpec) &#124; None|否|None|保存start_end活动的StartEndSpec，包含超时限制与初始触发选择；仅此规则使用，其他类型填写None。|
|`duration_comparison`|str|否|'>='|持续时长比较符：>=表示达到minimum_duration，>表示严格超过；默认>=。仅condition_duration使用。实际时间模式按整数纳秒比较，固定/DBC模式随所选报文推进；不改变onset/confirmed的积分起点选择。|

源码：[`src/chronaxis/planning/models.py:108`](../../../src/chronaxis/planning/models.py#L108)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-RulePlan-__post_init__"></a>
### `RulePlan.__post_init__`

检查窗口、迟滞和开始/结束规则，保持原字段位置参数兼容。

```python
RulePlan.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

新规则类型、配置或普通规则混入专用参数。

本函数直接报告的具体错误：

- `ValueError`：其他规则不接受StartEndSpec。
- `TypeError`：start_end需要两个BOOL条件及StartEndSpec。
- `ValueError`：start_end不能混用其他规则参数。
- `TypeError`：迟滞/防抖需要BOOL条件及StabilitySpec。
- `ValueError`：迟滞/防抖不能混用其他规则参数。
- `ValueError`：普通规则不接受迟滞/防抖参数。
- `TypeError`：hysteresis需要BOOL退出条件。
- `ValueError`：debounce退出使用not condition，不接受exit_condition。
- `TypeError`：window_delta需要数值signal与WindowDeltaSpec。
- `ValueError`：window_delta参数冲突或重触发策略非法。
- `ValueError`：普通规则不接受window_delta或retrigger参数。

源码：[`src/chronaxis/planning/models.py:133`](../../../src/chronaxis/planning/models.py#L133)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-RulePlan-temporal_rule_type"></a>
### `RulePlan.temporal_rule_type`

读取交给事件检测器的类型。

```python
RulePlan.temporal_rule_type
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

str。

#### 异常说明

无。

window_delta使用rising_edge；迟滞/防抖确认后的状态使用condition_duration=0活动。
完整窗口、条件、防抖和开始/结束时限保留在原计划；start_end也输出活动。

源码：[`src/chronaxis/planning/models.py:183`](../../../src/chronaxis/planning/models.py#L183)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-RulePlan-expressions"></a>
### `RulePlan.expressions`

列出规则全部静态条件。

```python
RulePlan.expressions
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

tuple。

#### 异常说明

无。

迟滞退出条件同样参与实际绑定、投影、同步与预算，不遗漏第二个来源。

源码：[`src/chronaxis/planning/models.py:193`](../../../src/chronaxis/planning/models.py#L193)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-RulePlan-dependencies"></a>
### `RulePlan.dependencies`

取得进出条件的去重依赖。

```python
RulePlan.dependencies
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

名称tuple。

#### 异常说明

无。

源码：[`src/chronaxis/planning/models.py:201`](../../../src/chronaxis/planning/models.py#L201)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-WindowPlan"></a>
## `WindowPlan`

一条已经解析的窗口配置，将指定规则的事件扩展成需要分析或导出的时间片段。例如活动在1～6秒，向前、向后各扩展1秒可得到0～7秒的请求范围；实际范围还需结合观测边界处理。

```python
class WindowPlan
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`window_id`|str|是|无|唯一窗口ID。|
|`event`|str|是|无|已有规则的id，如 `"hot"`，不加event:前缀。|
|`anchor`|str|是|无|`"activity"`：围绕整段活动扩展；`"point"`：围绕一个触发时刻扩展。须与规则产生的事件类型一致。|
|`pre_ns`|int|是|无|非负请求前扩范围。|
|`post_ns`|int|是|无|非负请求后扩范围。|
|`merge`|str|是|无|多段窗口如何合并，四种值见下表。|
|`exit_delay_ns`|int &#124; None|是|无|仅exit_delay模式有效。|

源码：[`src/chronaxis/planning/models.py:207`](../../../src/chronaxis/planning/models.py#L207)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-CalculationPlan"></a>
## `CalculationPlan`

一条已经解析的指标配置。指定计算哪个信号、用哪种运算，以及对整个会话、某次活动还是某个片段分别计算。on决定统计范围，op决定计算方法；其他字段说明缺失数据如何处理及输出单位。它不保存计算结果，结果由AnalysisRunner.run生成。

```python
class CalculationPlan
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`calculation_id`|str|是|无|唯一指标ID。|
|`scope`|str|是|无|`"session"`：整次请求范围；`"event:规则ID"`：对该规则每个事件分别算；`"segment:窗口ID"`：对该窗口产生的每个片段分别算。|
|`operation`|str|是|无|九种值：`integral`按所选计算间隔积分；`duration`累计条件成立的秒数；`select`返回满足条件的数据行；`sample_minimum/sample_maximum/sample_mean`分别计算真实样本最小值、最大值、算术平均；`min_time/max_time/time_weighted_mean`分别计算有持续时间的值的最小值、最大值、时间加权平均。详见[逐项数值例子](../calculations.md)。|
|`signal`|[StaticExpression](chronaxis.core.expression.md#api-StaticExpression) &#124; None|是|无|数值/BOOL信号或派生别名树。|
|`condition`|[StaticExpression](chronaxis.core.expression.md#api-StaticExpression) &#124; None|是|无|可选BOOL选择或condition_duration条件。|
|`unit`|str|是|无|duration固定为s；select保持原单位；积分可明确要求J、Wh、kWh、Ah等与输入匹配的单位。|
|`partial_policy`|str|是|无|`"report"`：数据不全时保留已知部分算出的数值，并标记partial；`"strict"`：所需范围内有数据缺失时返回None。它不会补出缺失数据。|
|`minimum_coverage`|int &#124; float|是|无|要求达到的最低覆盖比例，0～1且包含端点。0.9表示90%，不能填90；它影响质量判断，不补齐数据。|
|`method`|str &#124; None|是|无|当前填写 `"zoh"`：下一次更新前保持旧值，用保持值乘实际秒数再累加。其他算子不填写method。|
|`count_target`|str &#124; None|否|None|v4对象计数显式引用的规则或窗口名。|
|`ddof`|int &#124; None|否|None|样本/时间方差和标准差的分母选择。|
|`q`|int &#124; float &#124; None|否|None|仅sample_quantile显式指定概率。|

源码：[`src/chronaxis/planning/models.py:226`](../../../src/chronaxis/planning/models.py#L226)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-LegacyMessageSelector"></a>
## `LegacyMessageSelector`

明确选择当前消息计算的CAN帧，不猜旧profile的求值选择器默认。

通道与ID必须提供，两个帧类型可省略。ID支持整数或带进制文本，不接受bool或
float；实际记录保留remote/error等标志，消息计算只处理数据帧。
本声明不读DBC，也不证明该消息在输入中出现。

```python
class LegacyMessageSelector
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`channel`|int|是|无|内部0基CAN通道，限定触发计算的报文来源；用户配置通道1在此为0。|
|`frame_id`|int &#124; str|是|无|原生整数或进制字符串；0x/0X为十六进制，0b/0B为二进制，无前缀为十进制，010表示10。构造后保存0至0x1FFFFFFF的整数；拒绝bool、float、负数、加号、下划线及0o前缀。 Python构造器接受两种输入；对象建立后该属性为int。|
|`is_extended`|bool &#124; None|否|None|None表示未限定，运行时结合DBC及实际帧识别；False限定标准帧且ID不超过0x7FF，True限定扩展帧。Python允许None表达省略，JSON/YAML填写时只能是布尔值。|
|`is_fd`|bool &#124; None|否|None|None表示未限定，按日志实际帧匹配；False限定经典CAN，True限定CAN FD。DBC为FD而实际为经典CAN可按已批准规则兼容，不修改真实帧。JSON/YAML填写时只能是布尔值。|

源码：[`src/chronaxis/planning/models.py:251`](../../../src/chronaxis/planning/models.py#L251)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-LegacyMessageSelector-__post_init__"></a>
### `LegacyMessageSelector.__post_init__`

核原生类型和帧ID范围，不进行输入过滤或DBC查找。

```python
LegacyMessageSelector.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无，读取创建后不可修改的字段。

#### 返回说明

None，ID统一为整数，省略类型保留None。

#### 异常说明

TypeError为非原生int/bool；ValueError为负通道或ID超相应帧范围。

本函数直接报告的具体错误：

- `TypeError`：消息选择器channel/frame_id需要原生int。
- `TypeError`：消息选择器is_extended/is_fd需要原生bool。
- `ValueError`：消息选择器通道或帧ID范围非法。

返回类型：None。

源码：[`src/chronaxis/planning/models.py:264`](../../../src/chronaxis/planning/models.py#L264)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-MessageCalculationPlan"></a>
## `MessageCalculationPlan`

保存一个会话内按当前匹配消息逐次求值的明确计算声明。

expr来自本来源MessageDeclarations，parameters为同一冻结参数tuple。
operation仅legacy_sum，message_policy必须显式current_message-v1；这里不设置
旧触发器、跨消息缓存、普通TTL、连续时间覆盖率或事件/片段范围。
profile标识原解码路径，与新计算policy分别保存，不冒充旧完整兼容。
可选disjunction只把本条贡献路由到正/负桶；原方向定位关系由计划交叉校验。

```python
class MessageCalculationPlan
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`calculation_id`|str|是|无|与rules/windows/普通calculations共用计划ID空间。|
|`source`|str|是|无|当前单一CAN来源。|
|`profile`|str|是|无|原解码profile，须与实际来源声明对应。|
|`operation`|str|是|无|固定legacy_sum，不放入普通CalculationDefinition。|
|`update_message`|[LegacyMessageSelector](chronaxis.planning.models.md#api-LegacyMessageSelector)|是|无|选择触发计算的报文；channel和frame_id必填，is_extended和is_fd可省略，存在实际匹配歧义时补充。|
|`expr`|[StaticExpression](chronaxis.core.expression.md#api-StaticExpression)|是|无|逐消息表达式的静态语法树；构建它不会读取或执行分析。|
|`unit`|str|是|无|一次贡献及累计结果的单位，必须等于表达式结果单位。|
|`parameters`|tuple[[ExpressionParameter](chronaxis.core.message_binding.md#api-ExpressionParameter), ...]|是|无|原单位、规范FLOAT64参数。|
|`message_policy`|str|是|无|填`"current_message-v1"`：每次求值只取当前报文中的值，缺值就记录跳过原因，不借用前一条消息或另一条报文的值。|
|`disjunction`|[LegacyDisjunction](chronaxis.legacy.disjunction.md#api-LegacyDisjunction) &#124; None|否|None|可选原解码方向选择，不进入表达式或TTL。|

源码：[`src/chronaxis/planning/models.py:282`](../../../src/chronaxis/planning/models.py#L282)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-MessageCalculationPlan-__post_init__"></a>
### `MessageCalculationPlan.__post_init__`

检查固定模式及静态消息表达式的一致性，不打开任何来源。

```python
MessageCalculationPlan.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无，读取冻结声明。

#### 返回说明

None，不重编译AST或重建原信号。

#### 异常说明

TypeError为模型/容器错误；ValueError为模式、来源、单位或参数冲突。

本函数直接报告的具体错误：

- `TypeError`：逐消息disjunction需要LegacyDisjunction或None。
- `ValueError`：当前逐消息计算仅支持固定解码profile、legacy_sum及current_message-v1。
- `TypeError`：逐消息计划需要选择器、消息域StaticExpression及参数tuple。
- `ValueError`：逐消息计划来源、policy或参数与消息表达式声明不符。
- `ValueError`：legacy_sum表达式必须为数值，不接受bool或enum。
- `ValueError`：legacy_sum单位必须与表达式结果一致。

返回类型：None。

源码：[`src/chronaxis/planning/models.py:303`](../../../src/chronaxis/planning/models.py#L303)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ExecutionPlan"></a>
## `ExecutionPlan`

本次分析的资源和读取设置，包括内存上限、分批大小、解码范围以及是否读取完整来源时间。各字段影响哪些工作会执行、怎样限制资源，不替代信号单位和时间基准的配置。完整例子见[运行参数](../execution.md)。

```python
class ExecutionPlan
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`backend`|str|是|无|`"reference"`使用独立参考计算，`"numpy"`使用NumPy数组计算。须明确选择一种，不在运行失败后自动换用另一种。|
|`batch_rows`|int|是|无|来源批次样本上限。|
|`memory_budget_bytes`|int|是|无|新分析层RAM预算。|
|`result_buffer_rows`|int|是|无|结果流缓冲上限。|
|`partial_policy`|str|是|无|`"report"`：数据不全时保留已知部分算出的数值，并标记partial；`"strict"`：所需范围内有数据缺失时返回None。它不会补出缺失数据。|
|`spool_quota_bytes`|int &#124; None|是|无|磁盘配额，None表示未显式限额。|
|`on_budget_exceeded`|str|否|'error'|首版不丢数据或增加旧扫描。|

源码：[`src/chronaxis/planning/models.py:338`](../../../src/chronaxis/planning/models.py#L338)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-OutputPlan"></a>
## `OutputPlan`

保存新结果表和清单的输出格式声明。

tables接受普通使用默认'readable_csv'，或供程序使用的'csv'/'jsonl'；manifest使用'json'。
contributions仅控制逐消息贡献明细，none仍保留统计汇总和其他请求结果；省略为none。
本类不创建目录或写文件；run生成本次实际原始片段，write只复制已封口输出。

```python
class OutputPlan
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`tables`|str|是|无|readable_csv、csv或jsonl；只生成所选的一套表。|
|`manifest`|str|是|无|json。|
|`contributions`|str|否|'none'|只有明确请求full时生成逐消息贡献明细。|
|`signal_csv`|[SignalCSVOutput](chronaxis.planning.export_options.md#api-SignalCSVOutput) &#124; None|否|None|显式请求的信号长表，可单独设置线性网格。 None表示不导出信号CSV。|
|`can_frames`|[CANFramesOutput](chronaxis.planning.export_options.md#api-CANFramesOutput) &#124; None|否|None|显式原帧/重建帧输出，默认不保额外原始数据。|

源码：[`src/chronaxis/planning/models.py:360`](../../../src/chronaxis/planning/models.py#L360)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
