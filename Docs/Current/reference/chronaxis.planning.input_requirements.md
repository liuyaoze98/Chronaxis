# chronaxis.planning.input_requirements

根据实际请求的指标、事件和导出，确定需要读取哪些信号、需要检查哪些输入以及是否需要时间。配置中声明过一个信号，并不代表每个任务都必须读取它。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)、[LegacyCANSpec](chronaxis.sources.can_spec.md#api-LegacyCANSpec)

## 对象导航

|对象|用途|
|---|---|
|[`SourceInputRequirements`](#api-SourceInputRequirements)|保存一个来源的有限需求，不持有输入行、表达式树或可变配置。|
|[`InputRequirements`](#api-InputRequirements)|保存同一计划的样本、逐消息、观测及原帧需求，保留原声明顺序。|
|[`InputRequirements.for_source`](#api-InputRequirements-for_source)|按来源名称取得本计划的需求，不创建新副本。|
|[`supports_unbounded_message_summary`](#api-supports_unbounded_message_summary)|检查计划是否只请求整文件逐消息累计，不据此读取或计算数据。|
|[`collect_input_requirements`](#api-collect_input_requirements)|从全部请求结果收集原始输入需求，不进行输入 I/O 或运行时值校验。|
|[`collect_input_requirements.add`](#api-collect_input_requirements-add)|将已展开依赖加入本次有限集合，拒绝未知别名。|
|[`collect_input_requirements.add_rule`](#api-collect_input_requirements-add_rule)|收集定义结果范围的原规则条件，不用空依赖掩盖缺失引用。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from ..sources.can_spec import LegacyCANSpec, can_field_from_key
```

</details>

<a id="api-SourceInputRequirements"></a>
## `SourceInputRequirements`

保存一个来源的有限需求，不持有输入行、表达式树或可变配置。

别名按 signals 原声明序；字段和 ID 按首次出现顺序去重。decode_frame_ids
包含所需 CAN 字段的 ID 和所有逐消息选择器 ID，不是实际观测到的 ID 集合。
非 CAN 来源的两个 ID 字段为空，required_fields 仍为原字段定位字符串。

```python
class SourceInputRequirements
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|str|是|无|原来源名。|
|`ordinary_sample_aliases`|tuple[str, ...]|是|无|普通时序结果实际读取的别名。|
|`message_aliases`|tuple[str, ...]|是|无|当次消息公式及方向使用的别名。|
|`required_aliases`|tuple[str, ...]|是|无|两类消费者的字段并集。|
|`required_fields`|tuple[str, ...]|是|无|去重后的原规范定位，不重新解释信号名。|
|`decode_frame_ids`|tuple[int, ...]|是|无|所需字段和消息触发ID；非CAN为空。|
|`selector_ids`|tuple[int, ...]|是|无|即使公式无字段也保留的触发ID。|
|`time_scope`|str|否|'source'|`"none"`：本次未收集时间范围；`"selected"`：范围只基于选中的报文；`"source"`：范围基于整个来源。selected的首末时间不代表整个文件的首末时间。|
|`input_check`|str|否|'auto'|`"auto"`按本计划实际要计算的内容检查输入；`"full"`检查全部原帧及时间，即使某帧不参与指标也检查它。|
|`reasons`|tuple[str, ...]|否|()|计划阶段选择原因，不冒充实际执行或观测证明。|
|`active`|bool|否|True|只为实际消费者打开来源。|
|`clock_aliases`|tuple[str, ...]|否|()|只用于推进周期的定位，不因此读取该信号数值。|

源码：[`src/chronaxis/planning/input_requirements.py:19`](../../../src/chronaxis/planning/input_requirements.py#L19)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-InputRequirements"></a>
## `InputRequirements`

保存同一计划的样本、逐消息、观测及原帧需求，保留原声明顺序。

ordinary_sample_aliases 供普通信号批和历史使用；message_aliases 供同条
消息求值使用。required_aliases 是二者并集，不能用它强制生成普通样本。
sources保留全部声明；observation_sources仅列实际需要完整来源观测的来源。
raw_sources 只来自显式原帧导出请求，不由解码或指标依赖推导。

```python
class InputRequirements
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`ordinary_sample_aliases`|tuple[str, ...]|是|无|全计划所需普通样本，保原声明序。|
|`message_aliases`|tuple[str, ...]|是|无|全计划所需逐消息字段。|
|`required_aliases`|tuple[str, ...]|是|无|两类输入的声明序并集。|
|`sources`|tuple[[SourceInputRequirements](chronaxis.planning.input_requirements.md#api-SourceInputRequirements), ...]|是|无|每来源独立需求，不省略观测来源。|
|`observation_sources`|tuple[str, ...]|是|无|time_scope=source的来源；不是目标记录时间范围。|
|`raw_sources`|tuple[str, ...]|是|无|仅显式原始片段输出需要保存原帧的来源。|
|`analysis_sample_aliases`|tuple[str, ...]|否|()|普通计算所需值，不含纯导出列。|
|`constant_observation`|bool|否|False|无信号常量规则/统计需要会话观测范围。|

源码：[`src/chronaxis/planning/input_requirements.py:42`](../../../src/chronaxis/planning/input_requirements.py#L42)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-InputRequirements-for_source"></a>
### `InputRequirements.for_source`

按来源名称取得本计划的需求，不创建新副本。

```python
InputRequirements.for_source(name: str) -> SourceInputRequirements
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|位置或关键字。name为原生来源名称字符串。|

#### 返回说明

同一冻结 SourceInputRequirements。

#### 异常说明

TypeError 为非原生文本；ValueError 为未知来源。

本函数直接报告的具体错误：

- `TypeError`：需求来源名称必须为原生str。

返回类型：[SourceInputRequirements](chronaxis.planning.input_requirements.md#api-SourceInputRequirements)。

源码：[`src/chronaxis/planning/input_requirements.py:61`](../../../src/chronaxis/planning/input_requirements.py#L61)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-supports_unbounded_message_summary"></a>
## `supports_unbounded_message_summary`

检查计划是否只请求整文件逐消息累计，不据此读取或计算数据。

```python
supports_unbounded_message_summary(plan) -> bool
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)|是|无|位置或关键字。plan为已解析的AnalysisPlan|

### 返回说明

bool；True允许用户省略dataset.domain，仍需另选实际检查和时间范围。

### 异常说明

非法带有明确类型的对象的属性错误原样传播；本函数不吞配置或来源错误。

返回类型：bool。

源码：[`src/chronaxis/planning/input_requirements.py:76`](../../../src/chronaxis/planning/input_requirements.py#L76)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-collect_input_requirements"></a>
## `collect_input_requirements`

从全部请求结果收集原始输入需求，不进行输入 I/O 或运行时值校验。

```python
collect_input_requirements(plan) -> InputRequirements
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)|是|无|位置或关键字。已静态检查的 AnalysisPlan；不根据 raw_config 重新解析或猜测引用。|

### 返回说明

InputRequirements。别名、来源和去重字段保留声明顺序，纯参数逐消息
    指标即使没有信号依赖，也保留 update_message.frame_id。

### 异常说明

TypeError 为非计划对象或依赖容器错误；ValueError 为未声明依赖、
    缺少规则/窗口/来源引用或错误 CAN 字段。模型属性错误原样传播。

### 边界说明

仅收集依赖，不替代完整配置校验；不用的声明仍由计划构建器校验。
    所有声明规则和窗口本身都是输出根，不只收集被指标引用的节点。

返回类型：[InputRequirements](chronaxis.planning.input_requirements.md#api-InputRequirements)。

源码：[`src/chronaxis/planning/input_requirements.py:90`](../../../src/chronaxis/planning/input_requirements.py#L90)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-collect_input_requirements-add"></a>
### `collect_input_requirements.add`

将已展开依赖加入本次有限集合，拒绝未知别名。

```python
collect_input_requirements.add(expression, destination)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`expression`|str|是|无|位置或关键字。配置中尚未求值的表达式文本，解析其中引用了哪些信号别名。|
|`destination`|set[str]|是|无|位置或关键字。本次收集依赖的信号名集合，函数把expression中的名称加入此集合。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

依赖类型错误或未声明名称抛 TypeError/ValueError。

本函数直接报告的具体错误：

- `TypeError`：表达式依赖必须为原生str tuple。
- `ValueError`：表达式依赖包含未声明信号。

源码：[`src/chronaxis/planning/input_requirements.py:118`](../../../src/chronaxis/planning/input_requirements.py#L118)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-collect_input_requirements-add_rule"></a>
### `collect_input_requirements.add_rule`

收集定义结果范围的原规则条件，不用空依赖掩盖缺失引用。

```python
collect_input_requirements.add_rule(rule_id)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`rule_id`|str|是|无|位置或关键字。当前计划中的规则ID，递归收集该规则及其依赖的输入信号。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ValueError 为未知规则；条件依赖错误沿 add 原样传播。

源码：[`src/chronaxis/planning/input_requirements.py:131`](../../../src/chronaxis/planning/input_requirements.py#L131)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
