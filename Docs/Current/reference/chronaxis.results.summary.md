# chronaxis.results.summary

定义按需执行的精简指标行，不要求不存在的完整输入证明。

只保留结果身份、业务数值、单位及完成/质量状态。事件或片段通过parent_id关联，
不逐行重复配置、信号定义、时间对照或贡献；公开结果只接受当前扁平模型。
本模型只校验结果字段，不读取输入或执行指标计算。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 继承字段

- `SummaryCoverageCalculationRow`同时继承[SummaryCalculationRow](chronaxis.results.summary.md#api-SummaryCalculationRow)字段：`sequence`, `dataset_id`, `entity_id`, `session_id`, `calculation_id`, `operation`, `scope`, `parent_id`, `value`, `unit`, `status`, `reason`, `quality`。构造时须一并提供基类的必填字段；类型、默认值及约束按基类表。

## 相关类型

[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)

## 对象导航

|对象|用途|
|---|---|
|[`SummaryCalculationRow`](#api-SummaryCalculationRow)|一条精简指标；未知用None，不能把缺失转换为正常零。|
|[`SummaryCalculationRow.__post_init__`](#api-SummaryCalculationRow-__post_init__)|核对身份、数值类型及状态，不补造来源或时间信息。|
|[`SummaryCoverageCalculationRow`](#api-SummaryCoverageCalculationRow)|仅明确设置覆盖门槛时补一个判定，不重复输出时长、比例或输入明细。|
|[`SummaryCoverageCalculationRow.__post_init__`](#api-SummaryCoverageCalculationRow-__post_init__)|保留数值政策与覆盖门槛两个不同事实。|
|[`_require_row_identity`](#api-_require_row_identity)|核精简事件和配对的公共身份。|
|[`SummaryEventRow`](#api-SummaryEventRow)|一条业务事件；开始、确认、结束各有不同含义，不含原帧或逐条来源副本。|
|[`SummaryEventRow.__post_init__`](#api-SummaryEventRow-__post_init__)|核实际业务端点，不能把未知结束填为零。|
|[`SummarySequenceRow`](#api-SummarySequenceRow)|一条配对结论，只关联既有事件ID并保存所选口径的延迟。|
|[`SummarySequenceRow.__post_init__`](#api-SummarySequenceRow-__post_init__)|核配对及未知结果，不逐行重复规则和事件。|
|[`SummarySegmentRow`](#api-SummarySegmentRow)|片段只输出实际边界、状态和父事件ID，不重复请求边界/原事件/来源。|
|[`SummarySegmentRow.__post_init__`](#api-SummarySegmentRow-__post_init__)|检查实际范围和必需父关联。|
|[`SummaryContributionRow`](#api-SummaryContributionRow)|一条明确请求的逐消息贡献；仅定位计算，不复制原帧或输入值。|
|[`SummaryContributionRow.__post_init__`](#api-SummaryContributionRow-__post_init__)|核定位及贡献/跳过互斥。|
|[`SummaryInputRow`](#api-SummaryInputRow)|按请求保存一次所需输入；字段原值一份，不保存双时间表示或原帧副本。|
|[`SummaryInputRow.__post_init__`](#api-SummaryInputRow-__post_init__)|核定位与有限JSON标量，拒绝任意嵌套模型。|
|[`SummarySelectionRow`](#api-SummarySelectionRow)|一条真实更新的选择结果；保业务值及三值选择，不重复输入证明。|
|[`SummarySelectionRow.__post_init__`](#api-SummarySelectionRow-__post_init__)|核选择行身份和值类型。|
|[`summary_fields`](#api-summary_fields)|转换必要平坦字段，CSV和JSONL共用，不附另一份row_json。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from math import isfinite
from ..core.types import QualityFlag as Q
from ..core.validation import require_identifier, require_text
from ..timebase.conversion import require_int64_ns
```

</details>

<a id="api-SummaryCalculationRow"></a>
## `SummaryCalculationRow`

一条精简指标；未知用None，不能把缺失转换为正常零。

```python
class SummaryCalculationRow
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`sequence`|int|是|无|本次结果流的非负生成序号，各结果类型共用计数。单表可缺号、可按业务键重排；activity计算表实际顺序为3、1。跨表关联使用event_id/segment_id等实例标识及parent_id，不用此序号。|
|`dataset_id`|str|是|无|配置声明的数据集标识，用于关联本次结果所属的数据集。|
|`entity_id`|str|是|无|配置声明的被分析对象标识，例如某设备或某辆车。|
|`session_id`|str|是|无|本次连续分析会话的标识；跨连续文件保持同一会话，独立任务各自隔离。|
|`calculation_id`|str|是|无|指标在分析计划中的稳定id，用于关联计算配置和最终结果。|
|`operation`|str|是|无|记录产生此行的计算操作，如integral、sample_mean、duration或逐消息legacy_sum；由对应计算配置生成，select通过选择结果表返回。|
|`scope`|str|是|无|session为整会话，event为单事件，segment为扩展或合并后的片段；父ID须与范围一致。|
|`parent_id`|str &#124; None|是|无|event或segment结果所引用的父对象ID；session结果必须为None。|
|`value`|int &#124; float &#124; None|是|无|数值与质量必须一起读取，None不等于有效零。|
|`unit`|str|是|无|物理量或结果单位，如W、J、s；按本接口的单位检查与换算规则使用。|
|`status`|str|是|无|complete表示结果完整，partial表示只包含可核实部分，indeterminate表示无法确定数值。|
|`reason`|str|是|无|说明数值完整、部分可用或不能确定的具体原因；与status一起读取，不能只看数值。|
|`quality`|[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)|是|无|该值或结果的质量位组合；缺失、过期等原因不能通过清零掩盖。|

源码：[`src/chronaxis/results/summary.py:18`](../../../src/chronaxis/results/summary.py#L18)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-SummaryCalculationRow-__post_init__"></a>
### `SummaryCalculationRow.__post_init__`

核对身份、数值类型及状态，不补造来源或时间信息。

```python
SummaryCalculationRow.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

TypeError/ValueError为字段或组合错误。

源码：[`src/chronaxis/results/summary.py:38`](../../../src/chronaxis/results/summary.py#L38)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-SummaryCoverageCalculationRow"></a>
## `SummaryCoverageCalculationRow`

仅明确设置覆盖门槛时补一个判定，不重复输出时长、比例或输入明细。

```python
class SummaryCoverageCalculationRow(SummaryCalculationRow)
```

继承关系：[SummaryCalculationRow](chronaxis.results.summary.md#api-SummaryCalculationRow)。下表列本类声明的字段；基类字段及其约束见对应类型链接。

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`coverage_status`|str|是|无|sufficient表示达到显式覆盖门槛；indeterminate表示未满足。默认不要求覆盖门槛时不输出此扩展字段。|

源码：[`src/chronaxis/results/summary.py:75`](../../../src/chronaxis/results/summary.py#L75)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-SummaryCoverageCalculationRow-__post_init__"></a>
### `SummaryCoverageCalculationRow.__post_init__`

保留数值政策与覆盖门槛两个不同事实。

```python
SummaryCoverageCalculationRow.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

非法判定。

源码：[`src/chronaxis/results/summary.py:80`](../../../src/chronaxis/results/summary.py#L80)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_require_row_identity"></a>
## `_require_row_identity`

核精简事件和配对的公共身份。

```python
_require_row_identity(row)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`row`|[SummaryCalculationRow](chronaxis.results.summary.md#api-SummaryCalculationRow) &#124; [SummaryEventRow](chronaxis.results.summary.md#api-SummaryEventRow) &#124; [SummarySequenceRow](chronaxis.results.summary.md#api-SummarySequenceRow) &#124; [SummarySegmentRow](chronaxis.results.summary.md#api-SummarySegmentRow) &#124; [SummaryContributionRow](chronaxis.results.summary.md#api-SummaryContributionRow) &#124; [SummaryInputRow](chronaxis.results.summary.md#api-SummaryInputRow) &#124; [SummarySelectionRow](chronaxis.results.summary.md#api-SummarySelectionRow)|是|无|位置或关键字。已完成的精简结果行，按真实行类型取得字段和版本，不为其补造旧追溯字段。|

### 返回说明

None。

### 异常说明

类型或字段错误。

源码：[`src/chronaxis/results/summary.py:87`](../../../src/chronaxis/results/summary.py#L87)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-SummaryEventRow"></a>
## `SummaryEventRow`

一条业务事件；开始、确认、结束各有不同含义，不含原帧或逐条来源副本。

```python
class SummaryEventRow
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`sequence`|int|是|无|本次结果流的非负生成序号，各结果类型共用计数。单表可缺号、可按业务键重排；activity计算表实际顺序为3、1。跨表关联使用event_id/segment_id等实例标识及parent_id，不用此序号。|
|`dataset_id`|str|是|无|配置声明的数据集标识，用于关联本次结果所属的数据集。|
|`entity_id`|str|是|无|配置声明的被分析对象标识，例如某设备或某辆车。|
|`session_id`|str|是|无|本次连续分析会话的标识；跨连续文件保持同一会话，独立任务各自隔离。|
|`rule_id`|str|是|无|读取产生此事件的rules[].name；预设事件使用展开后生成的规则ID。|
|`event_id`|str|是|无|本次事件的稳定id，用于指标、窗口及配对结果引用。|
|`start_ns`|int|是|无|读取事件起始时刻，始终是整数纳秒；点事件为该点时间，活动为开始时间。|
|`confirmed_ns`|int|是|无|满足等待条件后实际确认事件的时刻，单位纳秒，不早于开始时刻。|
|`end_ns`|int &#124; None|是|无|读取活动结束时刻，整数纳秒且区间右端不包含；点事件为None。结束状态须同时查看status和reason。|
|`status`|str|是|无|point为点事件，closed为条件正常解除，interrupted为未知中断，truncated为EOF截断，timeout为时限结束。|
|`trigger`|str|是|无|记录底层事件的触发标签：initial为允许的初始点事件；rising_edge/falling_edge为上升/下降沿点事件；start_only为启动点；condition_duration为持续活动（起止、迟滞或去抖也可能通过此标签输出）。标签不是配置rule_type的完整副本；具体算法由rule_id关联rules[].name后查看。|
|`quality`|[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)|是|无|该值或结果的质量位组合；缺失、过期等原因不能通过清零掩盖。|

源码：[`src/chronaxis/results/summary.py:98`](../../../src/chronaxis/results/summary.py#L98)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-SummaryEventRow-__post_init__"></a>
### `SummaryEventRow.__post_init__`

核实际业务端点，不能把未知结束填为零。

```python
SummaryEventRow.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

合同错误。

源码：[`src/chronaxis/results/summary.py:114`](../../../src/chronaxis/results/summary.py#L114)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-SummarySequenceRow"></a>
## `SummarySequenceRow`

一条配对结论，只关联既有事件ID并保存所选口径的延迟。

```python
class SummarySequenceRow
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`sequence`|int|是|无|本次结果流的非负生成序号，各结果类型共用计数。单表可缺号、可按业务键重排；activity计算表实际顺序为3、1。跨表关联使用event_id/segment_id等实例标识及parent_id，不用此序号。|
|`dataset_id`|str|是|无|配置声明的数据集标识，用于关联本次结果所属的数据集。|
|`entity_id`|str|是|无|配置声明的被分析对象标识，例如某设备或某辆车。|
|`session_id`|str|是|无|本次连续分析会话的标识；跨连续文件保持同一会话，独立任务各自隔离。|
|`rule_id`|str|是|无|读取产生本次请求/响应结果的sequences[].name；用于关联配对配置，不是起点或响应规则ID。|
|`result_id`|str|是|无|本次配对结果的稳定id，不复制其关联事件对象。|
|`request_id`|str|是|无|请求事件的id，引用事件表中的对应记录。|
|`response_id`|str &#124; None|是|无|响应事件的id；无确定匹配时为None，不能伪造响应。|
|`decided_ns`|int|是|无|作出配对或未响应结论的实际时刻，单位纳秒。|
|`delay_ns`|int &#124; None|是|无|匹配成功后按选定间隔累计的延迟，单位纳秒；无匹配时为None。|
|`status`|str|是|无|matched为成功配对，no_response为充分观测后仍无响应，indeterminate为观测或条件不足而不能断言超时。|
|`quality`|[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)|是|无|该值或结果的质量位组合；缺失、过期等原因不能通过清零掩盖。|

源码：[`src/chronaxis/results/summary.py:135`](../../../src/chronaxis/results/summary.py#L135)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-SummarySequenceRow-__post_init__"></a>
### `SummarySequenceRow.__post_init__`

核配对及未知结果，不逐行重复规则和事件。

```python
SummarySequenceRow.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

合同错误。

源码：[`src/chronaxis/results/summary.py:151`](../../../src/chronaxis/results/summary.py#L151)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-SummarySegmentRow"></a>
## `SummarySegmentRow`

片段只输出实际边界、状态和父事件ID，不重复请求边界/原事件/来源。

```python
class SummarySegmentRow
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`sequence`|int|是|无|本次结果流的非负生成序号，各结果类型共用计数。单表可缺号、可按业务键重排；activity计算表实际顺序为3、1。跨表关联使用event_id/segment_id等实例标识及parent_id，不用此序号。|
|`dataset_id`|str|是|无|配置声明的数据集标识，用于关联本次结果所属的数据集。|
|`entity_id`|str|是|无|配置声明的被分析对象标识，例如某设备或某辆车。|
|`session_id`|str|是|无|本次连续分析会话的标识；跨连续文件保持同一会话，独立任务各自隔离。|
|`window_id`|str|是|无|产生窗口的配置id；通过它找到锚点、前后范围及合并设置。|
|`segment_id`|str|是|无|读取此窗口片段的非空唯一ID，用它连接scope=segment的计算结果；该字段不使用None表示会话。|
|`start_ns`|int &#124; None|是|无|读取片段左边界，整数纳秒；空片段为None，需同时查看status。|
|`end_ns`|int &#124; None|是|无|读取片段不包含的右边界，整数纳秒；空片段为None。|
|`status`|str|是|无|complete为完整窗口，partial为观测不足而裁剪，empty为没有实际交集。|
|`parent_event_ids`|tuple[str, ...]|是|无|产生该片段的全部事件id；窗口合并后仍保留全部父事件关联。|
|`quality`|[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)|是|无|该值或结果的质量位组合；缺失、过期等原因不能通过清零掩盖。|

源码：[`src/chronaxis/results/summary.py:173`](../../../src/chronaxis/results/summary.py#L173)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-SummarySegmentRow-__post_init__"></a>
### `SummarySegmentRow.__post_init__`

检查实际范围和必需父关联。

```python
SummarySegmentRow.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

字段/组合错误。

源码：[`src/chronaxis/results/summary.py:187`](../../../src/chronaxis/results/summary.py#L187)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-SummaryContributionRow"></a>
## `SummaryContributionRow`

一条明确请求的逐消息贡献；仅定位计算，不复制原帧或输入值。

```python
class SummaryContributionRow
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`sequence`|int|是|无|本次结果流的非负生成序号，各结果类型共用计数。单表可缺号、可按业务键重排；activity计算表实际顺序为3、1。跨表关联使用event_id/segment_id等实例标识及parent_id，不用此序号。|
|`dataset_id`|str|是|无|配置声明的数据集标识，用于关联本次结果所属的数据集。|
|`entity_id`|str|是|无|配置声明的被分析对象标识，例如某设备或某辆车。|
|`session_id`|str|是|无|本次连续分析会话的标识；跨连续文件保持同一会话，独立任务各自隔离。|
|`calculation_id`|str|是|无|指标在分析计划中的稳定id，用于关联计算配置和最终结果。|
|`source`|str|是|无|当前结果或记录所属的来源名称，必须对应计划中已经定义的source。|
|`original_sequence`|int|是|无|来源中实际记录的非负序号，用于定位原输入；同一时刻多条记录仍保留各自序号。|
|`evaluation_index`|int|是|无|当前逐消息指标的非负求值序号，同一时刻多次求值不合并。|
|`value`|float &#124; None|是|无|该次有效计算贡献；None表示跳过，reason给出缺值、条件不成立、求值错误或非有限值。|
|`reason`|str|是|无|contributed为有效贡献；missing_input缺输入，condition_false条件未选中，evaluation_error求值失败，nonfinite_input输入非有限。|
|`quality`|[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)|是|无|该值或结果的质量位组合；缺失、过期等原因不能通过清零掩盖。|

源码：[`src/chronaxis/results/summary.py:219`](../../../src/chronaxis/results/summary.py#L219)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-SummaryContributionRow-__post_init__"></a>
### `SummaryContributionRow.__post_init__`

核定位及贡献/跳过互斥。

```python
SummaryContributionRow.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

类型或字段错误。

源码：[`src/chronaxis/results/summary.py:234`](../../../src/chronaxis/results/summary.py#L234)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-SummaryInputRow"></a>
## `SummaryInputRow`

按请求保存一次所需输入；字段原值一份，不保存双时间表示或原帧副本。

```python
class SummaryInputRow
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`sequence`|int|是|无|本次结果流的非负生成序号，各结果类型共用计数。单表可缺号、可按业务键重排；activity计算表实际顺序为3、1。跨表关联使用event_id/segment_id等实例标识及parent_id，不用此序号。|
|`dataset_id`|str|是|无|配置声明的数据集标识，用于关联本次结果所属的数据集。|
|`entity_id`|str|是|无|配置声明的被分析对象标识，例如某设备或某辆车。|
|`session_id`|str|是|无|本次连续分析会话的标识；跨连续文件保持同一会话，独立任务各自隔离。|
|`source`|str|是|无|当前结果或记录所属的来源名称，必须对应计划中已经定义的source。|
|`original_sequence`|int|是|无|来源中实际记录的非负序号，用于定位原输入；同一时刻多条记录仍保留各自序号。|
|`time_ns`|int &#124; None|是|无|当前记录的实际纳秒时刻；仅明确不需要采集时间的输入诊断可为None。|
|`record_type`|str|是|无|输入记录种类：decoded_message表示所需报文解码值，signal_sample表示普通信号值，signal_clock表示只保留更新时间的记录。|
|`locator`|str|是|无|定位来源记录的非空文本；例如decoded_message记录的can:0:256:0:0依次表示CAN、通道0、报文ID256、标准帧、非FD。与source、original_sequence一起读取，不当作分析信号名或跨任务ID。|
|`values_json`|str|是|无|保存实际追溯输入的JSON对象文本，例如{"Power":10.0}。CSV读取后json.loads(row.values_json)取得字典；键是来源字段名，不保证等于分析别名。非有限值按追溯协议标记，不作为有效数值。|
|`quality`|[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)|是|无|该值或结果的质量位组合；缺失、过期等原因不能通过清零掩盖。|

源码：[`src/chronaxis/results/summary.py:253`](../../../src/chronaxis/results/summary.py#L253)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-SummaryInputRow-__post_init__"></a>
### `SummaryInputRow.__post_init__`

核定位与有限JSON标量，拒绝任意嵌套模型。

```python
SummaryInputRow.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

字段/格式错误。

源码：[`src/chronaxis/results/summary.py:267`](../../../src/chronaxis/results/summary.py#L267)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-SummarySelectionRow"></a>
## `SummarySelectionRow`

一条真实更新的选择结果；保业务值及三值选择，不重复输入证明。

```python
class SummarySelectionRow
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`sequence`|int|是|无|本次结果流的非负生成序号，各结果类型共用计数。单表可缺号、可按业务键重排；activity计算表实际顺序为3、1。跨表关联使用event_id/segment_id等实例标识及parent_id，不用此序号。|
|`dataset_id`|str|是|无|配置声明的数据集标识，用于关联本次结果所属的数据集。|
|`entity_id`|str|是|无|配置声明的被分析对象标识，例如某设备或某辆车。|
|`session_id`|str|是|无|本次连续分析会话的标识；跨连续文件保持同一会话，独立任务各自隔离。|
|`calculation_id`|str|是|无|指标在分析计划中的稳定id，用于关联计算配置和最终结果。|
|`scope`|str|是|无|session为整会话，event为单事件，segment为扩展或合并后的片段；父ID须与范围一致。|
|`parent_id`|str &#124; None|是|无|event或segment结果所引用的父对象ID；session结果必须为None。|
|`time_ns`|int|是|无|读取被select选中的样本时间，始终为整数纳秒；不是可缺省的输入诊断时间。|
|`value`|int &#124; float &#124; bool &#124; str &#124; None|是|无|被选择的信号值，类型由dtype决定；无效时必须为None并附质量标志。|
|`dtype`|str|是|无|说明value的实际类型，取float64、int64、uint64、bool或enum。有效enum值为状态字符串、bool为真假值；valid=False时value为None，读取CSV空单元格不能当零。|
|`unit`|str|是|无|物理量或结果单位，如W、J、s；按本接口的单位检查与换算规则使用。|
|`valid`|bool|是|无|该样本值是否有效；False时输出值为None并保留质量原因，不补成0。|
|`selection`|str|是|无|选择条件的结果：true或unknown；明确false不输出选择行，unknown仍保质量原因。|
|`quality`|[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)|是|无|该值或结果的质量位组合；缺失、过期等原因不能通过清零掩盖。|

源码：[`src/chronaxis/results/summary.py:292`](../../../src/chronaxis/results/summary.py#L292)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-SummarySelectionRow-__post_init__"></a>
### `SummarySelectionRow.__post_init__`

核选择行身份和值类型。

```python
SummarySelectionRow.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

类型/结构错误。

源码：[`src/chronaxis/results/summary.py:309`](../../../src/chronaxis/results/summary.py#L309)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-summary_fields"></a>
## `summary_fields`

转换必要平坦字段，CSV和JSONL共用，不附另一份row_json。

```python
summary_fields(row)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`row`|[SummaryCalculationRow](chronaxis.results.summary.md#api-SummaryCalculationRow) &#124; [SummaryEventRow](chronaxis.results.summary.md#api-SummaryEventRow) &#124; [SummarySequenceRow](chronaxis.results.summary.md#api-SummarySequenceRow) &#124; [SummarySegmentRow](chronaxis.results.summary.md#api-SummarySegmentRow) &#124; [SummaryContributionRow](chronaxis.results.summary.md#api-SummaryContributionRow) &#124; [SummaryInputRow](chronaxis.results.summary.md#api-SummaryInputRow) &#124; [SummarySelectionRow](chronaxis.results.summary.md#api-SummarySelectionRow)|是|无|位置或关键字。已完成的精简结果行，按真实行类型取得字段和版本，不为其补造旧追溯字段。|

### 返回说明

固定字段dict。

### 异常说明

TypeError为错误根类型。

源码：[`src/chronaxis/results/summary.py:338`](../../../src/chronaxis/results/summary.py#L338)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
