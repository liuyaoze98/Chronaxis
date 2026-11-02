# chronaxis.results.frame_exports

把明确范围内的原帧写成新ASC或复用旧封装的BLF，同时保精确逐帧索引。

输入来自同次读取的新暂存，包含未参与分析和DBC未知的帧；不重新读日志/解码。
ASC时间用整数纳秒文本；BLF沿现有writer及float秒接口，其精度和错误帧能力限制
在清单记录，精确源时间和全部原字段保存在frames.jsonl。筛选使用分析坐标，
写出仍保原坐标，只有显式output_offset_ns才移动输出时间。关闭后独占发布目录。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[DecodedCANRecord](chronaxis.sources.text_can_decode.md#api-DecodedCANRecord)、[ExportFiles](chronaxis.results.export_files.md#api-ExportFiles)、[Interval](chronaxis.core.models.md#api-Interval)、[LegacyCANProcessWrite](chronaxis.legacy.export_write.md#api-LegacyCANProcessWrite)、[LegacyRawFrame](chronaxis.legacy.records.md#api-LegacyRawFrame)、[RawCANRecord](chronaxis.sources.raw_can.md#api-RawCANRecord)、[StoredRawFrame](chronaxis.legacy.records.md#api-StoredRawFrame)

## 对象导航

|对象|用途|
|---|---|
|[`FrameExportSpec`](#api-FrameExportSpec)|声明报文写成ASC还是BLF，以及怎样解释原时间。无日期数据写BLF须明确采集日期和时区。|
|[`FrameExportSpec.__post_init__`](#api-FrameExportSpec-__post_init__)|核格式与时间。|
|[`FrameExportSpec.date_origin_ns`](#api-FrameExportSpec-date_origin_ns)|把日内零点映射到实际当地午夜。|
|[`ExportCANFrame`](#api-ExportCANFrame)|统一真实/生成记录；保分析坐标、原输出坐标、完整原帧和有限原始定位。|
|[`ExportCANFrame.__post_init__`](#api-ExportCANFrame-__post_init__)|核静态字段。|
|[`SkippedCANFrame`](#api-SkippedCANFrame)|保存重建未生成的网格点；不是原帧，不进入ASC/BLF，也不伪装成零载荷。|
|[`SkippedCANFrame.__post_init__`](#api-SkippedCANFrame-__post_init__)|核有界诊断。|
|[`as_export_frame`](#api-as_export_frame)|保既有原帧及原坐标，转换有限导出外壳。|
|[`_asc_line`](#api-_asc_line)|写标准ASC数据行及无法表达的原字段名单。|
|[`export_can_frames`](#api-export_can_frames)|逐条筛选并写出原始范围，完整消费新暂存后发布。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from fractions import Fraction
from math import isfinite
from ..core.models import Interval
from ..core.validation import require_identifier
from ..execution.history import _metadata_bytes
from ..legacy.records import LegacyRawFrame, StoredRawFrame, frame_to_dict
from ..legacy.export_write import LegacyCANProcessWrite
from ..sources.raw_can import RawCANRecord
from ..sources.text_can_decode import DecodedCANRecord
from ..timebase.conversion import require_int64_ns, checked_add_ns, convert_time
from .budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from .export_files import ExportFiles
```

</details>

<a id="api-FrameExportSpec"></a>
## `FrameExportSpec`

声明报文写成ASC还是BLF，以及怎样解释原时间。无日期数据写BLF须明确采集日期和时区。

```python
class FrameExportSpec
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`format`|str|否|'asc'|asc或blf，目标报文格式。|
|`output_offset_ns`|int|否|0|导出原报文时间另加的整数纳秒偏移，默认0；不是分析来源的time.offset。|
|`source_time_reference`|str|否|'relative'|relative表示无日历的相对时间；epoch表示已有纪元时间。|
|`capture_date`|str &#124; None|否|None|relative输出BLF时的实际采集日期；不能用电脑今天日期猜测。 None表示未提供；relative时间导出BLF时需要显式补齐该日期。|
|`timezone_offset_minutes`|int &#124; None|否|None|采集日期的UTC偏移，整数分钟；例如北京时间480。 None表示未提供；需要用采集日期构造BLF绝对时间时必须补齐。|

源码：[`src/chronaxis/results/frame_exports.py:28`](../../../src/chronaxis/results/frame_exports.py#L28)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameExportSpec-__post_init__"></a>
### `FrameExportSpec.__post_init__`

核格式与时间。

```python
FrameExportSpec.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

不支持格式或非法偏移。

本函数直接报告的具体错误：

- `ValueError`：原帧导出需要asc/blf和整数偏移。
- `ValueError`：必须明确源时间为relative或epoch，不能按数字大小猜日期。
- `ValueError`：采集日期和时区必须一起填写。
- `ValueError`：BLF导出前必须填写实际采集日期和时区。
- `ValueError`：需要YYYY-MM-DD实际采集日期及合法整数时区分钟。
- `ValueError`：已有绝对时间不能重复叠加采集日期。

源码：[`src/chronaxis/results/frame_exports.py:37`](../../../src/chronaxis/results/frame_exports.py#L37)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameExportSpec-date_origin_ns"></a>
### `FrameExportSpec.date_origin_ns`

把日内零点映射到实际当地午夜。

```python
FrameExportSpec.date_origin_ns()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

精确UTC纳秒或0。

#### 异常说明

int64溢出。

源码：[`src/chronaxis/results/frame_exports.py:59`](../../../src/chronaxis/results/frame_exports.py#L59)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ExportCANFrame"></a>
## `ExportCANFrame`

统一真实/生成记录；保分析坐标、原输出坐标、完整原帧和有限原始定位。

```python
class ExportCANFrame
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`sequence`|int|是|无|原始读取序号，用于同一时刻记录排序和追溯。|
|`time_ns`|int|是|无|分析时间轴中的整数纳秒时间，用于范围选择与排序。|
|`output_time_ns`|int|是|无|导出使用的原报文时间，整数纳秒；可与分析时间有已知固定偏移。|
|`frame`|[LegacyRawFrame](chronaxis.legacy.records.md#api-LegacyRawFrame)|是|无|实际LegacyRawFrame，包含ID、通道、标志和原始字节。|
|`provenance`|tuple[tuple[str, str &#124; int &#124; float &#124; bool &#124; None], ...]|是|无|不可变来源信息键值对元组，指向输入文件、行号或原消息。|
|`frame_origin`|str|否|'passthrough'|passthrough表示原帧透传，generated表示生成帧；默认passthrough。|

源码：[`src/chronaxis/results/frame_exports.py:74`](../../../src/chronaxis/results/frame_exports.py#L74)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ExportCANFrame-__post_init__"></a>
### `ExportCANFrame.__post_init__`

核静态字段。

```python
ExportCANFrame.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

类型、范围、重复定位或非有限值。

本函数直接报告的具体错误：

- `TypeError`：导出帧需要非负原序及LegacyRawFrame。
- `ValueError`：导出帧种类或定位非法。
- `TypeError`：帧定位需要有限键值tuple。
- `ValueError`：帧定位重复或非有限。

源码：[`src/chronaxis/results/frame_exports.py:84`](../../../src/chronaxis/results/frame_exports.py#L84)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-SkippedCANFrame"></a>
## `SkippedCANFrame`

保存重建未生成的网格点；不是原帧，不进入ASC/BLF，也不伪装成零载荷。

```python
class SkippedCANFrame
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|未能生成报文的目标网格时间，整数纳秒。|
|`reason`|str|是|无|未生成原因，例如缺少端点或两端间隔过大。|
|`details`|str|是|无|补充定位信息的不可变键值对元组；不放伪造报文字节。|

源码：[`src/chronaxis/results/frame_exports.py:103`](../../../src/chronaxis/results/frame_exports.py#L103)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-SkippedCANFrame-__post_init__"></a>
### `SkippedCANFrame.__post_init__`

核有界诊断。

```python
SkippedCANFrame.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

时间、原因或文本非法。

本函数直接报告的具体错误：

- `ValueError`：未生成帧需要有限原因及JSON说明文本。

源码：[`src/chronaxis/results/frame_exports.py:110`](../../../src/chronaxis/results/frame_exports.py#L110)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-as_export_frame"></a>
## `as_export_frame`

保既有原帧及原坐标，转换有限导出外壳。

```python
as_export_frame(record, *, compact=False)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`record`|[ExportCANFrame](chronaxis.results.frame_exports.md#api-ExportCANFrame) &#124; [StoredRawFrame](chronaxis.legacy.records.md#api-StoredRawFrame) &#124; [DecodedCANRecord](chronaxis.sources.text_can_decode.md#api-DecodedCANRecord)|是|无|位置或关键字。RawCANRecord、DecodedCANRecord、StoredRawFrame或ExportCANFrame；按实际支持分支规范为导出记录，保留原帧与来源。|
|`compact`|bool|否|False|仅关键字。控制是否保留逐帧来源说明：True不构造provenance明细，False保存原始定位；两者都保持原帧与原始时间。|

### 返回说明

ExportCANFrame。

### 异常说明

类型错。

本函数直接报告的具体错误：

- `TypeError`：帧导出需要同次原始/解码暂存记录。

源码：[`src/chronaxis/results/frame_exports.py:118`](../../../src/chronaxis/results/frame_exports.py#L118)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_asc_line"></a>
## `_asc_line`

写标准ASC数据行及无法表达的原字段名单。

```python
_asc_line(record, output_ns)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`record`|[StoredRawFrame](chronaxis.legacy.records.md#api-StoredRawFrame) &#124; [RawCANRecord](chronaxis.sources.raw_can.md#api-RawCANRecord) &#124; [ExportCANFrame](chronaxis.results.frame_exports.md#api-ExportCANFrame)|是|无|位置或关键字。包含frame原始帧及时间定位的导出记录；从frame提取ID、通道、标志和数据生成ASC行。|
|`output_ns`|int|是|无|位置或关键字。已经应用输出时间偏移的整数纳秒，格式化为ASC秒数。|

### 返回说明

(bytes,losses)。

### 异常说明

格式不可表达。

本函数直接报告的具体错误：

- `ValueError`：ASC需要非负时间和明确0基整数通道。
- `ValueError`：ASC标准帧ID超出11位。
- `ValueError`：ASC远程帧需要经典CAN、空数据和0至8 DLC。
- `ValueError`：ASC FD长度或DLC不一致。
- `ValueError`：ASC经典帧长度不一致。

源码：[`src/chronaxis/results/frame_exports.py:141`](../../../src/chronaxis/results/frame_exports.py#L141)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-export_can_frames"></a>
## `export_can_frames`

逐条筛选并写出原始范围，完整消费新暂存后发布。

```python
export_can_frames(records, spec, interval, destination, budget, *, source, device_label, check_cancel=None, compact=False, integrity=True, file_consumer=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`records`|可关闭的帧迭代器|是|无|位置或关键字。来自本次读取的原始帧流；逐条输出后关闭，不将整个日志装入列表。|
|`spec`|[FrameExportSpec](chronaxis.results.frame_exports.md#api-FrameExportSpec)|是|无|位置或关键字。spec格式/偏移|
|`interval`|[Interval](chronaxis.core.models.md#api-Interval)|是|无|位置或关键字。interval半开分析范围|
|`destination`|str &#124; [pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。本次报文导出的新目录，写入报文文件及质量说明。|
|`budget`|ResourceBudget|是|无|位置或关键字。本次运行共用的ResourceBudget对象，用于检查内存和临时磁盘用量。当前对象在分配前申请额度，用完后归还；同一次运行的组件应使用同一个对象。|
|`source`|str|是|无|仅关键字。source来源名|
|`device_label`|str|是|无|仅关键字。记录本次导出的设备来源标签；当前这个导出入口只接受home或work，pending会被拒绝。标签应来自已确认的执行设备映射，不从输入路径推断。|
|`check_cancel`|Callable[[], None] &#124; None|否|None|仅关键字。可选的无参取消检查函数。需要终止时由它抛出异常；None表示不额外调用取消检查。|
|`compact`|bool|否|False|仅关键字。控制CAN导出的附加诊断：True仅保目标报文与必要清单；False额外保存逐帧副本、时间及误差信息。默认False；公共Runner使用其明确选择的摘要模式。|
|`integrity`|bool|否|True|仅关键字。是否执行本对象的额外内容摘要或认证核验；False仍保留结构、类型、预算及必要文件变化检查。|
|`file_consumer`|Callable &#124; None|否|None|仅关键字。可选内部回调，接收已关闭并发布的至多16个文件写入事实；用于登记复用，不重新扫描内容。|

### 返回说明

已发布目录Path，含frames.asc/blf和manifest.json；旧完整模式另有frames.jsonl。

### 异常说明

格式/时间/原历史/I/O/预算/取消错；持续清理失败保export_cleanup_owner。

本函数直接报告的具体错误：

- `TypeError`：帧导出需要FrameExportSpec和Interval。
- `ValueError`：帧导出需要实际设备及可选取消回调。
- `ValueError`：导出帧时间回退，不能重排原记录。
- `ValueError`：未生成帧记录时间回退。
- `ValueError`：现有BLF写库不支持1990年以前的日期，不能改写为固定参考日期。
- `ValueError`：BLF需要0至65534的明确整数通道，避免写库隐式改通道。

源码：[`src/chronaxis/results/frame_exports.py:183`](../../../src/chronaxis/results/frame_exports.py#L183)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
