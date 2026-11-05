# `chronaxis.planning.intervals`

声明计算所用的间隔及可选诊断，不读取报文或建立额外时间轴。

输入是配置中的intervals/diagnostics和已编译计划。输出为冻结选择，
记录每个消费者采用actual、fixed或dbc，以及明确的驱动信号。
DBC周期只在运行初始化读取；这里检查来源种类和完整报文定位。
当前配置3支持这些声明；执行是否就绪由公共能力报告判断。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)

## 对象导航

|对象|用途|
|---|---|
|[`IntervalChoice`](#api-IntervalChoice)|选择一次计时依据；step_ns仅用于fixed，driver为原信号别名。|
|[`IntervalChoice.__post_init__`](#api-IntervalChoice-__post_init__)|拒绝矛盾字段、布尔间隔及溢出；无I/O或隐式数值转换。|
|[`IntervalPlan`](#api-IntervalPlan)|保存任务默认、显式覆盖及已解析的消费者选择。|
|[`IntervalPlan.__post_init__`](#api-IntervalPlan-__post_init__)|检查冻结容器、唯一节点与选择类型，防止带有明确类型的替换引入可变对象。|
|[`DiagnosticPlan`](#api-DiagnosticPlan)|分别声明详细追溯、完整性诊断及现场留存，全部默认关闭。|
|[`DiagnosticPlan.__post_init__`](#api-DiagnosticPlan-__post_init__)|仅接受原生bool；不把0/1或文本解释成开关。|
|[`parse_diagnostics`](#api-parse_diagnostics)|解析可选诊断对象；未知键或非bool报配置错误，不打开文件。|
|[`_choice`](#api-_choice)|将显式单位数值解析为纳秒；不查询DBC或猜测缺失的fixed数值。|
|[`_consumers`](#api-_consumers)|列出规则、配对、窗口和需时长指标的原信号依赖，保持计划顺序。|
|[`_driver_key`](#api-_driver_key)|按真实报文定位合并同帧信号候选；已解析信号各自独立。|
|[`_resolve`](#api-_resolve)|选定唯一驱动，检查DBC适用性；多候选/常量无驱动时要求明确填写。|
|[`resolve_intervals`](#api-resolve_intervals)|把有限声明解析为消费者选择；带有明确类型的校验与JSON解析共用本函数。|
|[`parse_intervals`](#api-parse_intervals)|解析任务默认和节点覆盖；显式null与未知字段均拒绝，缺省使用actual。|
|[`require_interval_declarations`](#api-require_interval_declarations)|核对类型化计划中的间隔和诊断声明未被替换为不一致的解析结果。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..core.moments import TIME_MOMENTS
from dataclasses import dataclass, replace
from ..core.validation import require_identifier
from ..sources.can_spec import can_field_from_key
from .checks import PlanValidationError, duration_at, model_at, object_at
from .sequences import sequence_dependencies
```

</details>

<a id="api-IntervalChoice"></a>
## `IntervalChoice`

选择一次计时依据；step_ns仅用于fixed，driver为原信号别名。

actual沿既有真实时间推进，不额外指定驱动。fixed/dbc的驱动可以在
配置解析时按唯一候选补齐；不在对象中保存逐帧时间或DBC实例。

```python
class IntervalChoice
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`mode`|str|否|'actual'|实际差、固定值或运行时读取的DBC周期。|
|`step_ns`|int &#124; None|否|None|仅fixed使用的正纳秒数；DBC在这里不提前填值。|
|`driver`|str &#124; None|否|None|推进累计的原信号别名；不存另一列时间。|

源码：[`src/chronaxis/planning/intervals.py:19`](../../../src/chronaxis/planning/intervals.py#L19)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-IntervalChoice-__post_init__"></a>
### `IntervalChoice.__post_init__`

拒绝矛盾字段、布尔间隔及溢出；无I/O或隐式数值转换。

```python
IntervalChoice.__post_init__()
```

参数：无显式参数。


#### 参数说明

无，读取mode、step_ns和driver。

#### 返回说明

None。

#### 异常说明

TypeError/ValueError为模式、纳秒范围或信号名错误。

#### 副作用说明

无。

源码：[`src/chronaxis/planning/intervals.py:30`](../../../src/chronaxis/planning/intervals.py#L30)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-IntervalPlan"></a>
## `IntervalPlan`

保存任务默认、显式覆盖及已解析的消费者选择。

三组数据均为有限配置，不是样本历史。resolved按声明顺序列出实际
消费者；legacy_sum自带period，不进入普通间隔解析。

```python
class IntervalPlan
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`default`|[IntervalChoice](chronaxis.planning.intervals.md#api-IntervalChoice)|否|IntervalChoice()|任务级缺省选择。|
|`overrides`|tuple[tuple[str, [IntervalChoice](chronaxis.planning.intervals.md#api-IntervalChoice)], ...]|否|()|按稳定节点ID的显式选择。|
|`resolved`|tuple[tuple[str, [IntervalChoice](chronaxis.planning.intervals.md#api-IntervalChoice)], ...]|否|()|当前消费者的唯一有效选择。|

源码：[`src/chronaxis/planning/intervals.py:49`](../../../src/chronaxis/planning/intervals.py#L49)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-IntervalPlan-__post_init__"></a>
### `IntervalPlan.__post_init__`

检查冻结容器、唯一节点与选择类型，防止带有明确类型的替换引入可变对象。

```python
IntervalPlan.__post_init__()
```

参数：无显式参数。


#### 参数说明

无，读取default、overrides及resolved。

#### 返回说明

None。

#### 异常说明

TypeError/ValueError为非冻结选择、节点重复或非法名称。

#### 副作用说明

无。

源码：[`src/chronaxis/planning/intervals.py:60`](../../../src/chronaxis/planning/intervals.py#L60)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-DiagnosticPlan"></a>
## `DiagnosticPlan`

分别声明详细追溯、完整性诊断及现场留存，全部默认关闭。

这些开关不取消必要输入检查，不代替outputs.contributions，彼此不捆绑。
此对象不分配暂存或执行核验；实际资源能力接线前必须拒绝执行。

```python
class DiagnosticPlan
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`trace`|bool|否|False|请求详细追溯，独立于贡献明细。|
|`integrity`|bool|否|False|请求额外完整性诊断，不代替必要输入检查。|
|`retain_work`|bool|否|False|请求保留本次自有现场，不授权保留无关用户数据。|

源码：[`src/chronaxis/planning/intervals.py:82`](../../../src/chronaxis/planning/intervals.py#L82)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-DiagnosticPlan-__post_init__"></a>
### `DiagnosticPlan.__post_init__`

仅接受原生bool；不把0/1或文本解释成开关。

```python
DiagnosticPlan.__post_init__()
```

参数：无显式参数。


#### 参数说明

无，读取三个独立开关。

#### 返回说明

None。

#### 异常说明

TypeError为任一值不是原生bool。

#### 副作用说明

无。

源码：[`src/chronaxis/planning/intervals.py:93`](../../../src/chronaxis/planning/intervals.py#L93)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-parse_diagnostics"></a>
## `parse_diagnostics`

解析可选诊断对象；未知键或非bool报配置错误，不打开文件。

```python
parse_diagnostics(value) -> DiagnosticPlan
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|dict &#124; None|是|无|位置或关键字。diagnostics配置对象；省略时三个开关均关闭，显式键只能是trace、integrity、retain_work且值为bool。|

### 返回说明

DiagnosticPlan，省略项为False。

### 异常说明

PlanValidationError为未知键或非bool。

### 副作用说明

无。

返回类型：[DiagnosticPlan](chronaxis.planning.intervals.md#api-DiagnosticPlan)。

源码：[`src/chronaxis/planning/intervals.py:102`](../../../src/chronaxis/planning/intervals.py#L102)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_choice"></a>
## `_choice`

将显式单位数值解析为纳秒；不查询DBC或猜测缺失的fixed数值。

```python
_choice(value, path) -> IntervalChoice
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|dict|是|无|位置或关键字。一个间隔选择对象；mode必填，fixed另需value，driver按驱动候选规则填写。|
|`path`|str|是|无|位置或关键字。配置中的字段路径，用于在错误中指出具体位置，例如intervals.default。|

### 返回说明

IntervalChoice，固定间隔以整数ns保存。

### 异常说明

PlanValidationError为缺项、矛盾、单位或类型错误。

### 副作用说明

无。

返回类型：[IntervalChoice](chronaxis.planning.intervals.md#api-IntervalChoice)。

源码：[`src/chronaxis/planning/intervals.py:111`](../../../src/chronaxis/planning/intervals.py#L111)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_consumers"></a>
## `_consumers`

列出规则、配对、窗口和需时长指标的原信号依赖，保持计划顺序。

返回(node_id, aliases)元组。样本min/max/select与旧逐消息求和没有
普通dt消费者；对它们单独配置覆盖属于无效需求，不能静默忽略。

```python
_consumers(plan)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|AnalysisPlan|是|无|位置或关键字。已完成静态解析的分析计划，包含来源、绑定、规则、指标、间隔选择和输出要求。|

### 返回说明

tuple，每项为节点ID及原信号别名tuple，无消费者为空。

### 异常说明

错误带有明确类型的引用的KeyError/StopIteration由外层验证报告捕获。

### 副作用说明

无。

源码：[`src/chronaxis/planning/intervals.py:125`](../../../src/chronaxis/planning/intervals.py#L125)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_driver_key"></a>
## `_driver_key`

按真实报文定位合并同帧信号候选；已解析信号各自独立。

返回来源与报文身份或来源与字段；只读已校验声明，不加载DBC。

```python
_driver_key(plan, alias)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|AnalysisPlan|是|无|位置或关键字。已完成静态解析的分析计划，包含来源、绑定、规则、指标、间隔选择和输出要求。|
|`alias`|str|是|无|位置或关键字。已声明的原信号别名；用于解析物理驱动身份，不接受未定义名称。|

### 返回说明

tuple物理更新身份。

### 异常说明

无效别名/报文定位的ValueError或缺来源StopIteration。

### 副作用说明

无。

源码：[`src/chronaxis/planning/intervals.py:158`](../../../src/chronaxis/planning/intervals.py#L158)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_resolve"></a>
## `_resolve`

选定唯一驱动，检查DBC适用性；多候选/常量无驱动时要求明确填写。

```python
_resolve(plan, choice, aliases, path)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|AnalysisPlan|是|无|位置或关键字。已完成静态解析的分析计划，包含来源、绑定、规则、指标、间隔选择和输出要求。|
|`choice`|[IntervalChoice](chronaxis.planning.intervals.md#api-IntervalChoice)|是|无|位置或关键字。当前节点声明的actual、fixed或dbc选择；补齐唯一驱动，不在静态阶段读取DBC周期。|
|`aliases`|tuple[str, ...]|是|无|位置或关键字。实际需要的信号别名；序列用于内部范围校验，发布时通过bindings统一说明。|
|`path`|str|是|无|位置或关键字。配置中的字段路径，用于在错误中指出具体位置，例如intervals.default。|

### 返回说明

补齐driver的IntervalChoice，actual原样返回。

### 异常说明

PlanValidationError为歧义、未知驱动、时基不符或DBC不适用。

### 副作用说明

无。

源码：[`src/chronaxis/planning/intervals.py:173`](../../../src/chronaxis/planning/intervals.py#L173)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-resolve_intervals"></a>
## `resolve_intervals`

把有限声明解析为消费者选择；带有明确类型的校验与JSON解析共用本函数。

输入是已构造的计划和冻结选择；返回新的IntervalPlan。未知节点、
无用覆盖或不适用DBC报ValueError/PlanValidationError；无数据读取。

```python
resolve_intervals(plan, default, overrides) -> IntervalPlan
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|AnalysisPlan|是|无|位置或关键字。已完成静态解析的分析计划，包含来源、绑定、规则、指标、间隔选择和输出要求。|
|`default`|[IntervalChoice](chronaxis.planning.intervals.md#api-IntervalChoice)|是|无|位置或关键字。整个任务缺省的间隔选择；没有覆盖的适用节点使用此项。|
|`overrides`|tuple[tuple[str, [IntervalChoice](chronaxis.planning.intervals.md#api-IntervalChoice)], ...]|是|无|位置或关键字。节点ID及其间隔选择的有序覆盖，不能引用不存在或不使用间隔的节点。|

### 返回说明

IntervalPlan，resolved保持消费者声明顺序。

### 异常说明

TypeError/ValueError及PlanValidationError为非法声明或不明确驱动。

### 副作用说明

无。

返回类型：[IntervalPlan](chronaxis.planning.intervals.md#api-IntervalPlan)。

源码：[`src/chronaxis/planning/intervals.py:201`](../../../src/chronaxis/planning/intervals.py#L201)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-parse_intervals"></a>
## `parse_intervals`

解析任务默认和节点覆盖；显式null与未知字段均拒绝，缺省使用actual。

```python
parse_intervals(value, plan) -> IntervalPlan
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|dict &#124; None|是|无|位置或关键字。归组转换后的内部intervals对象，可含default和overrides。用户配置只写intervals.default，单项选择放在各节点interval；本函数不读取DBC或业务文件。|
|`plan`|AnalysisPlan|是|无|位置或关键字。已完成静态解析的分析计划，包含来源、绑定、规则、指标、间隔选择和输出要求。|

### 返回说明

IntervalPlan。

### 异常说明

PlanValidationError为结构、取值或引用错误。

### 副作用说明

无。

返回类型：[IntervalPlan](chronaxis.planning.intervals.md#api-IntervalPlan)。

源码：[`src/chronaxis/planning/intervals.py:229`](../../../src/chronaxis/planning/intervals.py#L229)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-require_interval_declarations"></a>
## `require_interval_declarations`

核对类型化计划中的间隔和诊断声明未被替换为不一致的解析结果。

```python
require_interval_declarations(plan)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|AnalysisPlan|是|无|位置或关键字。已完成静态解析的分析计划，包含来源、绑定、规则、指标、间隔选择和输出要求。|

### 返回说明

None。

### 异常说明

TypeError/ValueError为版本、新类型或解析结果不一致；引用错误由公共报告收集。

### 副作用说明

无，不重编译表达式。

源码：[`src/chronaxis/planning/intervals.py:244`](../../../src/chronaxis/planning/intervals.py#L244)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
