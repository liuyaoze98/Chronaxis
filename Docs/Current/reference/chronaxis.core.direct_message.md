# chronaxis.core.direct_message

记录一次直接逐消息计算实际读了哪些输入、检查了多少条记录、何时结束。摘要根据读取过程中处理的内容生成，用来区分输入；它不是原BLF文件的哈希。构造这些数据对象只检查字段之间是否一致，实际读取由执行层负责。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`_text`](#api-_text)|检查原生非空文本。|
|[`_sha`](#api-_sha)|检查规范SHA文本，不把标签冒充摘要。|
|[`DirectMessageEvidence`](#api-DirectMessageEvidence)|保存一次扫描的数量、时间范围和摘要。构造时检查字段是否一致，实际读取仍由读取器完成。|
|[`DirectMessageEvidence.__post_init__`](#api-DirectMessageEvidence-__post_init__)|核扫描范围、真实EOF标志和固定选择域，再计算独立身份。|
|[`DirectMessageInputEvidence`](#api-DirectMessageInputEvidence)|冻结按实际需求完成读取的输入事实，与旧普通信号扫描证据分开。|
|[`DirectMessageInputEvidence.__post_init__`](#api-DirectMessageInputEvidence-__post_init__)|核实际选择、两路内容摘要及完整读取范围，计算独立版本身份。|
|[`DemandMessageInputEvidence`](#api-DemandMessageInputEvidence)|保存按需处理范围与实际输入，允许完全不采集时间。|
|[`DemandMessageInputEvidence.__post_init__`](#api-DemandMessageInputEvidence-__post_init__)|核实际选择、两路内容摘要及完整读取范围，计算独立版本身份。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass, field
from .message_binding import _hash_parts
from .validation import require_identifier, require_text
from ..timebase.conversion import require_int64_ns
```

</details>

<a id="api-_text"></a>
## `_text`

检查原生非空文本。

```python
_text(value, name, *, identifier=False)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|str|是|无|位置或关键字。待检查的文本原值；须非空，identifier=True时还须满足简单名称格式。此函数不做数值有限性检查。|
|`name`|str|是|无|位置或关键字。用于报错定位的字段名称，例如"source"；它不一定是信号别名。|
|`identifier`|bool|否|False|仅关键字。False检查非空文本；True还检查英文字母/下划线开头的简单名称，并拒绝关键字与保留名称。|

### 返回说明

返回None，不返回额外的计算值。

### 异常说明

原类型/文本错误。

源码：[`src/chronaxis/core/direct_message.py:19`](../../../src/chronaxis/core/direct_message.py#L19)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_sha"></a>
## `_sha`

检查规范SHA文本，不把标签冒充摘要。

```python
_sha(value, name)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|str|是|无|位置或关键字。待检查的SHA-256摘要文本，要求恰好64个小写十六进制字符。|
|`name`|str|是|无|位置或关键字。错误信息中显示的字段名称，例如"input_sha256"。|

### 返回说明

返回None，不返回额外的计算值。

### 异常说明

类型/格式错误。

源码：[`src/chronaxis/core/direct_message.py:26`](../../../src/chronaxis/core/direct_message.py#L26)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-DirectMessageEvidence"></a>
## `DirectMessageEvidence`

保存一次扫描的数量、时间范围和摘要。构造时检查字段是否一致，实际读取仍由读取器完成。

```python
class DirectMessageEvidence
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|str|是|无|原计划中的CAN来源名。|
|`session_id`|str|是|无|同次请求的会话身份。|
|`decoder_profile`|str|是|无|同次READY确认的旧解码profile。|
|`read_identity`|str|是|无|实际read的UUID，不用于稳定输入身份。|
|`input_identity`|str|是|无|原来源声明的输入身份，不冒充原文件内容SHA。|
|`source_contract_sha256`|str|是|无|来源配置、时基、偏移和输入声明的规范摘要。|
|`description_sha256`|str|是|无|原adapter描述的规范摘要。|
|`request_sha256`|str|是|无|本次全部别名、请求范围及批上限的规范摘要。|
|`signal_stream_sha256`|str|是|无|已校验信号样本/进度流摘要；不存在对应消息历史文件。|
|`projected_aliases`|tuple[str, ...]|是|无|原请求的完整别名顺序，允许空投影。|
|`progress_count`|int|是|无|实际验证的进度记录数，含最终EOF记录。|
|`sample_count`|int|是|无|已校验信号样本数，多信号时不同于原帧数。|
|`observed_frame_count`|int|是|无|全部原yield数，包括不匹配指标或没有信号的帧。|
|`first_time_ns`|int &#124; None|是|无|全原帧首个映射时间，空源为None。|
|`last_time_ns`|int &#124; None|是|无|全原帧最后映射时间，不补采样周期。|
|`observed_start_ns`|int &#124; None|是|无|来源实际观测范围起点，可保声明的更早起点。|
|`observed_end_ns`|int &#124; None|是|无|真实EOF确认的观测终点。|
|`calculation_frame_ids`|tuple[int, ...]|是|无|指标请求的去重原ID，非全部读取帧集合。|
|`source_eof`|bool|是|无|必须True；工厂还需核实际进程结束和read关闭。|
|`evidence_kind`|str|否|'can-direct-scan-v1'|与消息仓证据完全独立的固定版本。|
|`identity`|str|不填写|构造时计算|全字段版本化SHA，含本次read UUID。|

源码：[`src/chronaxis/core/direct_message.py:34`](../../../src/chronaxis/core/direct_message.py#L34)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-DirectMessageEvidence-__post_init__"></a>
### `DirectMessageEvidence.__post_init__`

核扫描范围、真实EOF标志和固定选择域，再计算独立身份。

```python
DirectMessageEvidence.__post_init__()
```

参数：无显式参数。


#### 参数说明

全部构造字段。

#### 返回说明

None，时间规范为原生int，identity为全字段SHA。

#### 异常说明

TypeError/ValueError为结构矛盾；时间越界、编码及取消错误原样传播。
执行工厂还须核同scan/read/request及预算归属；此模型不开放假历史字段。

源码：[`src/chronaxis/core/direct_message.py:59`](../../../src/chronaxis/core/direct_message.py#L59)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-DirectMessageInputEvidence"></a>
## `DirectMessageInputEvidence`

冻结按实际需求完成读取的输入事实，与旧普通信号扫描证据分开。

原时间摘要按原序连接每帧大端float64字节，保留正负零；记录摘要连接每条
已严格解包记录的四字节长度及JSON字节，两者均不包含批头，故不依赖分批。
它们不是BLF文件SHA，也不证明未保留帧的载荷；实际投影范围由请求、描述、
所需别名和指标ID共同标识。构造仅检查有限结构，完成工厂仍须核同次读取、
全部时间映射、EOF与资源成功关闭，并先预约模型和身份计算的内存。

```python
class DirectMessageInputEvidence
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|str|是|无|计划中的CAN来源名称。|
|`session_id`|str|是|无|同次读取和累计所属的会话身份。|
|`decoder_profile`|str|是|无|实际READY确认的旧解码profile。|
|`read_identity`|str|是|无|同次真实read UUID，不用于跨运行稳定输入身份。|
|`input_identity`|str|是|无|原来源输入声明身份，不冒充BLF内容SHA。|
|`source_contract_sha256`|str|是|无|来源配置、时基、偏移与输入声明的规范摘要。|
|`description_sha256`|str|是|无|实际来源描述，包含解码策略和字段选择范围。|
|`request_sha256`|str|是|无|实际请求字段、范围、批上限等的规范摘要。|
|`original_timestamps_sha256`|str|是|无|全部原帧时间字节流SHA，包含未保留帧的时间。|
|`retained_records_sha256`|str|是|无|保留记录长度及JSON字节流SHA，仅覆盖实际投影内容。|
|`required_aliases`|tuple[str, ...]|是|无|本次实际计算所需别名顺序，常量指标允许为空。|
|`observed_frame_count`|int|是|无|全部原yield数量，不限于目标ID或有效计算。|
|`retained_record_count`|int|是|无|严格解包的实际保留记录数，不等同求值或贡献数。|
|`first_time_ns`|int &#124; None|是|无|全原帧首个映射时间；空输入为None。|
|`last_time_ns`|int &#124; None|是|无|全原帧最后映射时间，不补采样周期。|
|`observed_start_ns`|int &#124; None|是|无|实际观测范围起点，可包括声明的更早起点。|
|`observed_end_ns`|int &#124; None|是|无|真实EOF确认的观测终点。|
|`calculation_frame_ids`|tuple[int, ...]|是|无|指标请求的去重原ID，严格递增。|
|`source_eof`|bool|是|无|只能为True；工厂另核真实EOF和成功关闭。|
|`evidence_kind`|str|否|'can-direct-input-v2'|与旧信号流及消息历史证据不同的版本。|
|`identity`|str|不填写|构造时计算|全部字段及版本的SHA，包含本次read UUID。|

源码：[`src/chronaxis/core/direct_message.py:126`](../../../src/chronaxis/core/direct_message.py#L126)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-DirectMessageInputEvidence-__post_init__"></a>
### `DirectMessageInputEvidence.__post_init__`

核实际选择、两路内容摘要及完整读取范围，计算独立版本身份。

```python
DirectMessageInputEvidence.__post_init__()
```

参数：无显式参数。


#### 参数说明

全部构造字段；计数为非负原生int，时间为可规范化的int64纳秒。

#### 返回说明

None；时间规范为原生int，identity写入全字段版本化SHA。

#### 异常说明

TypeError/ValueError为结构矛盾，时间溢出、编码或取消错误原样传播。
无文件或进程操作；SHA文本合法不等于此构造器认证了实际输入内容。

源码：[`src/chronaxis/core/direct_message.py:158`](../../../src/chronaxis/core/direct_message.py#L158)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-DemandMessageInputEvidence"></a>
## `DemandMessageInputEvidence`

保存按需处理范围与实际输入，允许完全不采集时间。

source模式的时间摘要连接每帧float64字节，其他模式为None。记录摘要连接每条
已严格解包记录的四字节长度及JSON字节，两者均不包含批头，故不依赖分批。
它们不是BLF文件SHA，也不证明未保留帧的载荷；实际投影范围由请求、描述、
所需别名和指标ID共同标识。构造仅检查有限结构，完成工厂仍须核同次读取、
声明范围内的时间检查、EOF与资源成功关闭，并先预约模型和身份计算的内存。

```python
class DemandMessageInputEvidence
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|str|是|无|计划中的CAN来源名称。|
|`session_id`|str|是|无|同次读取和累计所属的会话身份。|
|`decoder_profile`|str|是|无|实际READY确认的旧解码profile。|
|`read_identity`|str|是|无|同次真实read UUID，不用于跨运行稳定输入身份。|
|`input_identity`|str|是|无|原来源输入声明身份，不冒充BLF内容SHA。|
|`source_contract_sha256`|str|是|无|来源配置、时基、偏移与输入声明的规范摘要。|
|`description_sha256`|str|是|无|实际来源描述，包含解码策略和字段选择范围。|
|`request_sha256`|str|是|无|实际请求字段、范围、批上限等的规范摘要。|
|`original_timestamps_sha256`|str &#124; None|是|无|只有source模式提供全部原帧时间SHA。|
|`retained_records_sha256`|str|是|无|保留记录长度及JSON字节流SHA，仅覆盖实际投影内容。|
|`required_aliases`|tuple[str, ...]|是|无|本次实际计算所需别名顺序，常量指标允许为空。|
|`observed_frame_count`|int|是|无|全部原yield数量，不限于目标ID或有效计算。|
|`retained_record_count`|int|是|无|严格解包的实际保留记录数，不等同求值或贡献数。|
|`first_time_ns`|int &#124; None|是|无|source为全来源首时间，selected为目标首时间，none未采集。|
|`last_time_ns`|int &#124; None|是|无|对应采集范围的末时间，不补采样周期。|
|`observed_start_ns`|int &#124; None|是|无|实际观测范围起点，可包括声明的更早起点。|
|`observed_end_ns`|int &#124; None|是|无|真实EOF确认的观测终点。|
|`calculation_frame_ids`|tuple[int, ...]|是|无|指标请求的去重原ID，严格递增。|
|`source_eof`|bool|是|无|只能为True；工厂另核真实EOF和成功关闭。|
|`time_scope`|str|是|无|`"none"`：本次未收集时间范围；`"selected"`：范围只基于选中的报文；`"source"`：范围基于整个来源。selected的首末时间不代表整个文件的首末时间。|
|`input_check`|str|是|无|`"auto"`按本计划实际要计算的内容检查输入；`"full"`检查全部原帧及时间，即使某帧不参与指标也检查它。|
|`evidence_kind`|str|否|'can-demand-input-v1'|与旧信号流及消息历史证据不同的版本。|
|`identity`|str|不填写|构造时计算|全部字段及版本的SHA，包含本次read UUID。|

源码：[`src/chronaxis/core/direct_message.py:244`](../../../src/chronaxis/core/direct_message.py#L244)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-DemandMessageInputEvidence-__post_init__"></a>
### `DemandMessageInputEvidence.__post_init__`

核实际选择、两路内容摘要及完整读取范围，计算独立版本身份。

```python
DemandMessageInputEvidence.__post_init__()
```

参数：无显式参数。


#### 参数说明

全部构造字段；计数为非负原生int，时间为可规范化的int64纳秒。

#### 返回说明

None；时间规范为原生int，identity写入全字段版本化SHA。

#### 异常说明

TypeError/ValueError为结构矛盾，时间溢出、编码或取消错误原样传播。
无文件或进程操作；SHA文本合法不等于此构造器认证了实际输入内容。

源码：[`src/chronaxis/core/direct_message.py:278`](../../../src/chronaxis/core/direct_message.py#L278)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
