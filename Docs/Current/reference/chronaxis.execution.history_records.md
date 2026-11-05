# `chronaxis.execution.history_records`

定义已解码历史记录与严格JSONL格式，不再次归一化数值。

样本同时保存物理数组值、逻辑ScalarValue和可选原诊断，时间/序号保持整数。
进度记录保留空批、watermark和整个来源EOF；None观测终点不补齐。
编码复用结果层固定白名单标签，不注册动态类或允许任意对象反序列化。
格式只用于新执行层历史，不修改分析计划schema或旧读写格式。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CANSourceRef](chronaxis.sources.can_spec.md#api-CANSourceRef)、[CANTextSourceRef](chronaxis.sources.text_can_ref.md#api-CANTextSourceRef)、[CSVSourceRef](chronaxis.sources.csv_spec.md#api-CSVSourceRef)、[RecordSample](chronaxis.execution.record_sample.md#api-RecordSample)、[ResultFormatError](chronaxis.results.errors.md#api-ResultFormatError)、[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)、[SignalDType](chronaxis.core.types.md#api-SignalDType)、[SignalSample](chronaxis.core.models.md#api-SignalSample)、[SourceRef](chronaxis.core.models.md#api-SourceRef)

## 对象导航

|对象|用途|
|---|---|
|[`HistorySample`](#api-HistorySample)|保存单个已归一化观测；array_value不被用来推断有效性。|
|[`HistorySample.__post_init__`](#api-HistorySample-__post_init__)|验证物理/逻辑值、身份和原诊断，不做scale或offset转换。|
|[`HistoryProgress`](#api-HistoryProgress)|保存一批结束时的读取事实，sample_count包含该批所有信号列。|
|[`HistoryProgress.__post_init__`](#api-HistoryProgress-__post_init__)|校验计数、身份和可未知的观测/进度坐标。|
|[`record_values`](#api-record_values)|按固定字段顺序提取白名单值，不将dataclass变成动态对象格式。|
|[`estimate_record_bytes`](#api-estimate_record_bytes)|保守估算一行装箱、JSON结构和UTF8副本的临时RAM。|
|[`encode_record`](#api-encode_record)|编码一条历史JSONL；基础v1、信号CSV v2、旧CAN v3、文本CAN v4。|
|[`decode_record`](#api-decode_record)|严格重建单行带有明确类型的记录，拒绝重复键、额外字段和损坏换行。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from math import isfinite
from ..core.models import SourceRef, SignalSample, require_identifier, require_scalar
from ..sources.csv_spec import CSVSourceRef
from ..sources.can_spec import CANSourceRef
from ..sources.text_can_ref import CANTextSourceRef
from ..core.numeric import ScalarValue
from .record_sample import RecordSample
from ..timebase.conversion import require_int64_ns
from ..core.types import SignalDType
from ..results.codec import _pack, _unpack, _unique_object, _reject_constant, _estimate
from ..results.errors import ResultFormatError
```

</details>

<a id="api-HistorySample"></a>
## `HistorySample`

保存单个已归一化观测；array_value不被用来推断有效性。

value携带逻辑值、类型、掩码和质量，ENUM正常值是标签文本；array_value保留整数编码。
original_present区分没有原诊断列与该列中的真实None，原诊断允许非有限浮点。
batch_index只标识传输批次，不作为事件身份或绑定身份。

```python
class HistorySample
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`batch_index`|int|是|无|样本来自第几个传输批次，从0开始；改变分批方式可改变此值，但不改变事件或绑定身份。|
|`name`|str|是|无|当前计划中的简单信号别名。|
|`time_ns`|int|是|无|当前事实对应的整数纳秒时间，不经过浮点二次取整。|
|`sequence`|int|是|无|稳定序号，非负原生整数；不是用时间推导的序号。|
|`array_value`|int &#124; float &#124; bool|是|无|保存数组使用的物理标量；数值和布尔直接保存，enum保存状态名称在labels中的整数索引。有效性以value.valid为准，不能用占位数值推断。|
|`value`|[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)|是|无|保存ScalarValue逻辑样本，包含值、类型、有效性和质量；enum的正常逻辑值是状态名称文本。与array_value必须表示同一个有效样本。|
|`unit`|str|是|无|该值或指标采用的单位字符串；不凭名称推测单位。|
|`source_ref`|[SourceRef](chronaxis.core.models.md#api-SourceRef)|是|无|该值的实际来源定位，供追溯到原会话/字段/消息。|
|`original_present`|bool|是|无|True表示原始诊断值列存在；False表示没有该列。这样能区分未提供诊断列与列中真实保存了None。|
|`original_value`|int &#124; float &#124; bool &#124; str &#124; None|是|无|归一化之前的原值；配合original_present区分真实None与没有保留原值。|

源码：[`src/chronaxis/execution/history_records.py:26`](../../../src/chronaxis/execution/history_records.py#L26)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-HistorySample-__post_init__"></a>
### `HistorySample.__post_init__`

验证物理/逻辑值、身份和原诊断，不做scale或offset转换。

```python
HistorySample.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无；读取创建后不可修改的字段。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError/OverflowError为记录矛盾或非法标量。

本函数直接报告的具体错误：

- `ValueError`：历史batch_index需要非负int64。
- `TypeError`：历史需要ScalarValue和字符串单位。
- `TypeError`：历史物理值必须符合固定数组类型且有限。
- `TypeError`：original_present需要bool。
- `ValueError`：缺原诊断列时不能附带诊断值。
- `ValueError`：历史物理值与正常逻辑值矛盾。

返回类型：None。

源码：[`src/chronaxis/execution/history_records.py:45`](../../../src/chronaxis/execution/history_records.py#L45)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-HistoryProgress"></a>
## `HistoryProgress`

保存一批结束时的读取事实，sample_count包含该批所有信号列。

```python
class HistoryProgress
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`batch_index`|int|是|无|来源批次序号，用于跟踪读取事实，不是业务事件编号。|
|`source`|str|是|无|原SourcePlan声明，必须与同次真实扫描和绑定一致。|
|`session_id`|str|是|无|所属会话的唯一标识，必须与本次计划/来源一致。|
|`sample_count`|int|是|无|记录本批所有信号列合计的样本数，使用非负int64整数。空批为0；不是已读取文件行数或累计批次数。|
|`watermark_ns`|int &#124; None|是|无|来源已经推进到的纳秒水位，按批次协议说明后续顺序。|
|`source_eof`|bool|是|无|来源读取是否到达真实EOF的布尔值。|
|`observed_end_ns`|int &#124; None|是|无|实际观测终点纳秒；未知时保留None，不能填请求终点。|

源码：[`src/chronaxis/execution/history_records.py:79`](../../../src/chronaxis/execution/history_records.py#L79)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-HistoryProgress-__post_init__"></a>
### `HistoryProgress.__post_init__`

校验计数、身份和可未知的观测/进度坐标。

```python
HistoryProgress.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无；读取全部字段。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError/OverflowError为记录结构或时间错误。

本函数直接报告的具体错误：

- `TypeError`：source_eof需要bool。
- `ValueError`：历史计数需要非负int64。

返回类型：None。

源码：[`src/chronaxis/execution/history_records.py:90`](../../../src/chronaxis/execution/history_records.py#L90)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-record_values"></a>
## `record_values`

按固定字段顺序提取白名单值，不将dataclass变成动态对象格式。

```python
record_values(record: HistoryRecord) -> tuple
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`record`|HistoryRecord|是|无|位置或关键字。record为两种历史记录之一。|

### 返回说明

字段tuple。

### 异常说明

TypeError为未支持记录。

本函数直接报告的具体错误：

- `TypeError`：未知历史记录类型。

返回类型：tuple。

源码：[`src/chronaxis/execution/history_records.py:112`](../../../src/chronaxis/execution/history_records.py#L112)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-estimate_record_bytes"></a>
## `estimate_record_bytes`

保守估算一行装箱、JSON结构和UTF8副本的临时RAM。

```python
estimate_record_bytes(record: HistoryRecord) -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`record`|HistoryRecord|是|无|位置或关键字。record为已检查记录。|

### 返回说明

bytes估算，非全进程RSS。

### 异常说明

类型或深度错误传播。

返回类型：int。

源码：[`src/chronaxis/execution/history_records.py:147`](../../../src/chronaxis/execution/history_records.py#L147)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-encode_record"></a>
## `encode_record`

编码一条历史JSONL；基础v1、信号CSV v2、旧CAN v3、文本CAN v4。

```python
encode_record(record: HistoryRecord, max_bytes: int) -> bytes
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`record`|HistoryRecord|是|无|位置或关键字。一条历史样本或进度记录，编码为带类型信息的JSONL行。|
|`max_bytes`|int|是|无|位置或关键字。单条编码记录的最大字节数，包含完整JSON行；超过时报错。|

### 返回说明

含换行UTF8 bytes。

### 异常说明

ResultFormatError为超长/不支持结构。

本函数直接报告的具体错误：

- `ResultFormatError`：历史单行超过有限读取上限。

返回类型：bytes。

源码：[`src/chronaxis/execution/history_records.py:159`](../../../src/chronaxis/execution/history_records.py#L159)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-decode_record"></a>
## `decode_record`

严格重建单行带有明确类型的记录，拒绝重复键、额外字段和损坏换行。

```python
decode_record(payload: bytes, max_bytes: int) -> HistoryRecord
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`payload`|bytes|是|无|位置或关键字。包含末尾换行的UTF-8历史记录，先检查长度再解析并还原模型。|
|`max_bytes`|int|是|无|位置或关键字。单条编码记录的最大字节数，包含完整JSON行；超过时报错。|

### 返回说明

HistoryRecord。

### 异常说明

ResultFormatError并保留原格式/模型异常链。

本函数直接报告的具体错误：

- `ResultFormatError`：历史行过长或未完整写入。
- `ResultFormatError`：历史版本或字段错误。
- `ResultFormatError`：历史kind或值容器错误。
- `ResultFormatError`：历史记录结构/模型非法。
- `ResultFormatError`：历史v2需要完整CSV固定定位。
- `ResultFormatError`：历史v3需要完整CAN固定定位。
- `ResultFormatError`：历史v4需要完整文本CAN定位。
- `ResultFormatError`：CAN历史定位必须使用对应v3/v4固定格式。

返回类型：HistoryRecord。

源码：[`src/chronaxis/execution/history_records.py:177`](../../../src/chronaxis/execution/history_records.py#L177)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
