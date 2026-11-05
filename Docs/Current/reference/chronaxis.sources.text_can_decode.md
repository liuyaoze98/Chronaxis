# `chronaxis.sources.text_can_decode`

按需解码新ASC/CSV原帧，并接到既有数值归一化核心。

CANTextDecodeRead消费显式CANTextSpec与本次需要的SignalDefinition，逐个交付
DecodedCANRecord；未知ID、未选中和非数据帧仍保原记录，仅所需帧调用cantools。
DBC沿用decode_choices=False/allow_truncated=True参数，但新入口先严格核已选帧长度；
已定义报文解码失败直接定位，不冒充未知ID。pack_text_records输出既有SignalSeries。
完整读取核对全部原帧时间；按需ASC仅核所需通道/ID的连续顺序，并同次统计来源范围。
文件不重读；DBC加载和临时对象先付预算。
解析文件逐个关闭，失败/取消保原错误及必要恢复owner，不改旧reader或vendor。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ASCRead](chronaxis.sources.asc.md#api-ASCRead)、[ASCSpec](chronaxis.sources.asc.md#api-ASCSpec)、[BLFRead](chronaxis.sources.blf.md#api-BLFRead)、[BLFSpec](chronaxis.sources.blf.md#api-BLFSpec)、[CANCSVRead](chronaxis.sources.raw_csv.md#api-CANCSVRead)、[CANTextError](chronaxis.sources.raw_can.md#api-CANTextError)、[CANTextSourceRef](chronaxis.sources.text_can_ref.md#api-CANTextSourceRef)、[CANTextSpec](chronaxis.sources.text_can_spec.md#api-CANTextSpec)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[RawCANRecord](chronaxis.sources.raw_can.md#api-RawCANRecord)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)

## 对象导航

|对象|用途|
|---|---|
|[`DecodedCANRecord`](#api-DecodedCANRecord)|保留一条原帧及本次所需原信号值；非decoded记录的values必须为空。|
|[`DecodedCANRecord.__post_init__`](#api-DecodedCANRecord-__post_init__)|核记录冻结结构。|
|[`CANTextDecodeRead`](#api-CANTextDecodeRead)|拥有单次DBC和逐文件解析器；EOF后保有限元数据到显式close。|
|[`CANTextDecodeRead.__init__`](#api-CANTextDecodeRead-__init__)|只核声明并预约固定费用。|
|[`CANTextDecodeRead.closed`](#api-CANTextDecodeRead-closed)|查看本对象负责的资源是否已经全部关闭。|
|[`CANTextDecodeRead.exhausted`](#api-CANTextDecodeRead-exhausted)|区别真实全文件EOF与提前close。|
|[`CANTextDecodeRead.metadata`](#api-CANTextDecodeRead-metadata)|取得本次读取使用的DBC及其相关记录。|
|[`CANTextDecodeRead.prepare_metadata`](#api-CANTextDecodeRead-prepare_metadata)|只初始化一次DBC，供计算在首帧前取得周期。|
|[`CANTextDecodeRead._start`](#api-CANTextDecodeRead-_start)|一次加载并核所需定位/单位。|
|[`CANTextDecodeRead._decode`](#api-CANTextDecodeRead-_decode)|给本条原帧分类并按需解码。|
|[`CANTextDecodeRead.__iter__`](#api-CANTextDecodeRead-__iter__)|迭代同次读取。|
|[`CANTextDecodeRead._time_selected`](#api-CANTextDecodeRead-_time_selected)|判断此帧是否属于所需通道与ID；不解码、不改时间。|
|[`CANTextDecodeRead.__next__`](#api-CANTextDecodeRead-__next__)|逐条返回原始报文和本次请求的解码信号值。|
|[`CANTextDecodeRead.close`](#api-CANTextDecodeRead-close)|关闭自有解析器及DBC状态，可重试。|
|[`CANTextDecodeRead.__enter__`](#api-CANTextDecodeRead-__enter__)|建立显式资源上下文。|
|[`CANTextDecodeRead.__exit__`](#api-CANTextDecodeRead-__exit__)|保原业务错误并收尾。|
|[`pack_text_records`](#api-pack_text_records)|把有限已解码原帧交给现有数值核心，不再次解码或重复DBC缩放。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from decimal import Decimal
from hashlib import file_digest
from pathlib import Path
from ..core.binding import SignalDefinition
from ..core.validation import require_identifier
from ..execution.history import _metadata_bytes
from ..legacy.records import field_to_dict
from ..legacy.worker import _field_metadata
from ..results.budget import ResourceBudget, _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..results.errors import ResultClosedError
from .asc import ASCSpec, ASCRead
from .blf import BLFSpec, BLFRead
from .raw_csv import CANCSVRead
from .raw_can import RawCANRecord, CANTextError
from .can_spec import can_field_from_key
from .models import freeze_metadata
from .packing import pack_decoded
from .text_can_ref import CANTextSourceRef
from .text_can_spec import CANTextSpec
```

</details>

<a id="api-DecodedCANRecord"></a>
## `DecodedCANRecord`

保留一条原帧及本次所需原信号值；非decoded记录的values必须为空。

```python
class DecodedCANRecord
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|str|是|无|当前来源名称。|
|`input_index`|int|是|无|原输入列表位置。|
|`sequence`|int|是|无|全部文件连续的原帧序号，不仅是参与计算的序号。|
|`raw`|[RawCANRecord](chronaxis.sources.raw_can.md#api-RawCANRecord)|是|无|原文件/行/精确时间和原帧字段。|
|`values`|tuple[tuple[str, int &#124; float &#124; bool &#124; None], ...]|是|无|规范CAN字段键到DBC物理值。|
|`status`|str|是|无|`decoded`：已用DBC解码；`unknown`：DBC中找不到该报文；`unselected`：本次未选择解码该报文；`non_data`：远程帧或错误帧，不按普通数据帧解码。解析错误会报错，不改记为unknown。|
|`frame_values`|tuple[tuple[str, int &#124; float &#124; bool &#124; None], ...]|否|()|显式重建所需原物理字段。|
|`frame_layout`|tuple[tuple[str, int], ...]|否|()|当次复用选择器的原始码值。|

源码：[`src/chronaxis/sources/text_can_decode.py:36`](../../../src/chronaxis/sources/text_can_decode.py#L36)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-DecodedCANRecord-__post_init__"></a>
### `DecodedCANRecord.__post_init__`

核记录冻结结构。

```python
DecodedCANRecord.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

来源、位置、状态或值结构非法。

本函数直接报告的具体错误：

- `ValueError`：解码CAN记录结构或状态非法。
- `ValueError`：未解码原帧不能携带信号值。
- `ValueError`：未解码原帧不能伪造重建值。
- `TypeError`：解码值需要规范字段键及原生数值/None。
- `ValueError`：解码CAN字段重复。
- `ValueError`：重建物理值或布局结构非法。

源码：[`src/chronaxis/sources/text_can_decode.py:48`](../../../src/chronaxis/sources/text_can_decode.py#L48)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-CANTextDecodeRead"></a>
## `CANTextDecodeRead`

拥有单次DBC和逐文件解析器；EOF后保有限元数据到显式close。

```python
CANTextDecodeRead(spec, budget, signals, *, check_cancel=None, database_context=None, classify_unselected=True, cycle_fields=(), metadata_fields=(), integrity=True, trace=True, retain_source_time=True, selected_ids=None, time_frame_ids=None)
```


源码：[`src/chronaxis/sources/text_can_decode.py:75`](../../../src/chronaxis/sources/text_can_decode.py#L75)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-CANTextDecodeRead-__init__"></a>
### `CANTextDecodeRead.__init__`

只核声明并预约固定费用。

```python
CANTextDecodeRead.__init__(spec, budget, signals, *, check_cancel=None, database_context=None, classify_unselected=True, cycle_fields=(), metadata_fields=(), integrity=True, trace=True, retain_source_time=True, selected_ids=None, time_frame_ids=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|[CANTextSpec](chronaxis.sources.text_can_spec.md#api-CANTextSpec)|是|无|位置或关键字。ASC或原始CSV文本CAN来源配置，包括输入格式与DBC设置。|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)|是|无|位置或关键字。当前读取共用的资源额度管理器，解码和保留数据前先预约所需资源。|
|`signals`|tuple[[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition), ...]|是|无|位置或关键字。实际需要的信号定义，根据明确字段定位选择解码后的信号。|
|`check_cancel`|Callable[[], None] &#124; None|否|None|仅关键字。可选的无参取消检查函数。需要终止时由它抛出异常；None表示不额外调用取消检查。|
|`database_context`|FrameDBCContext &#124; None|否|None|仅关键字。本次已加载的DBC上下文；提供时借用数据库，None按读取流程加载所需DBC。|
|`classify_unselected`|bool|否|True|仅关键字。是否检查未选报文的分类信息；关闭时在确认报文不相关后尽早跳过。|
|`cycle_fields`|tuple[LegacyCANField, ...]|否|()|仅关键字。需要读取DBC周期的字段定位集合；初始化时读取元数据，不逐帧读取DBC。|
|`metadata_fields`|tuple[LegacyCANField, ...]|否|()|仅关键字。仅请求驱动信号的DBC候选声明，默认空tuple；用于确认实际帧身份，不请求信号值，也不增加普通样本或值解码。|
|`integrity`|bool|否|True|仅关键字。是否执行本对象的额外内容摘要或认证核验；False仍保留结构、类型、预算及必要文件变化检查。|
|`trace`|bool|否|True|仅关键字。是否保存此功能的详细来源或输入追溯；False在生成处跳过，不能先构造再隐藏。|
|`retain_source_time`|bool|否|True|仅关键字。是否保留导出实际需要的源时间坐标；关闭时不额外保留源时间副本。|
|`selected_ids`|tuple[int, ...] &#124; None|否|None|仅关键字。需要处理的报文ID；默认None读取全部记录。仅在不需要完整原帧和来源时间的消息分析路径使用：原始CSV先读ID，未匹配时跳过该行的时间、载荷和帧型解析；目标记录仍完整校验。ASC路径不使用此筛选。|
|`time_frame_ids`|tuple[int, ...] &#124; None|否|None|仅关键字。本次需要检查时间顺序的CAN报文ID；同时限定来源的内部通道。None检查完整序列；空元组不交付帧但仍同次统计来源范围。完整检查或原帧导出不得传选择集合。|

#### 返回说明

未开始读取的owner。

#### 异常说明

声明/预算错误；持续清理失败附text_can_cleanup_owner。

本函数直接报告的具体错误：

- `TypeError`：文本CAN读取需要静态声明、预算及所需信号定义。
- `ValueError`：文本CAN别名不能重复。
- `ValueError`：文本CAN字段通道与来源声明不一致。
- `ValueError`：共用DBC上下文必须匹配当前文件和共享预算。

源码：[`src/chronaxis/sources/text_can_decode.py:78`](../../../src/chronaxis/sources/text_can_decode.py#L78)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-CANTextDecodeRead-closed"></a>
### `CANTextDecodeRead.closed`

查看本对象负责的资源是否已经全部关闭。

```python
CANTextDecodeRead.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/sources/text_can_decode.py:149`](../../../src/chronaxis/sources/text_can_decode.py#L149)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-CANTextDecodeRead-exhausted"></a>
### `CANTextDecodeRead.exhausted`

区别真实全文件EOF与提前close。

```python
CANTextDecodeRead.exhausted
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示输入或结果已正常读完；False表示尚未正常读完。发生异常不等于正常读完。

#### 异常说明

无。

源码：[`src/chronaxis/sources/text_can_decode.py:155`](../../../src/chronaxis/sources/text_can_decode.py#L155)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-CANTextDecodeRead-metadata"></a>
### `CANTextDecodeRead.metadata`

取得本次读取使用的DBC及其相关记录。

```python
CANTextDecodeRead.metadata
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

冻结Mapping。

#### 异常说明

未启动或已关闭时ResultClosedError。

本函数直接报告的具体错误：

- `ResultClosedError`：文本CAN尚无可用的同次DBC元数据。

源码：[`src/chronaxis/sources/text_can_decode.py:161`](../../../src/chronaxis/sources/text_can_decode.py#L161)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-CANTextDecodeRead-prepare_metadata"></a>
### `CANTextDecodeRead.prepare_metadata`

只初始化一次DBC，供计算在首帧前取得周期。

```python
CANTextDecodeRead.prepare_metadata()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

同次冻结元数据。

#### 异常说明

失败/关闭拒绝，启动错误交实际owner清理。
不打开原始文件，不改变EOF状态。

源码：[`src/chronaxis/sources/text_can_decode.py:168`](../../../src/chronaxis/sources/text_can_decode.py#L168)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-CANTextDecodeRead-_start"></a>
### `CANTextDecodeRead._start`

一次加载并核所需定位/单位。

```python
CANTextDecodeRead._start()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原DBC/I/O/预算或单位不符。

本函数直接报告的具体错误：

- `ValueError`：加载期间DBC内容发生变化。

源码：[`src/chronaxis/sources/text_can_decode.py:185`](../../../src/chronaxis/sources/text_can_decode.py#L185)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-CANTextDecodeRead-_decode"></a>
### `CANTextDecodeRead._decode`

给本条原帧分类并按需解码。

```python
CANTextDecodeRead._decode(raw)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`raw`|[RawCANRecord](chronaxis.sources.raw_can.md#api-RawCANRecord)|是|无|位置或关键字。raw为本次实际RawCANRecord。|

#### 返回说明

(values,status)。

#### 异常说明

已选帧结构错；legacy遇解码失败停止，新政策将DecodeError置为本条无效。

源码：[`src/chronaxis/sources/text_can_decode.py:236`](../../../src/chronaxis/sources/text_can_decode.py#L236)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-CANTextDecodeRead-__iter__"></a>
### `CANTextDecodeRead.__iter__`

迭代同次读取。

```python
CANTextDecodeRead.__iter__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回当前对象本身。后续迭代或with语句使用的仍是同一个对象。

#### 异常说明

无。

源码：[`src/chronaxis/sources/text_can_decode.py:278`](../../../src/chronaxis/sources/text_can_decode.py#L278)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-CANTextDecodeRead-_time_selected"></a>
### `CANTextDecodeRead._time_selected`

判断此帧是否属于所需通道与ID；不解码、不改时间。

```python
CANTextDecodeRead._time_selected(frame)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`frame`|LegacyRawFrame|是|无|位置或关键字。已经解析的当前原帧；只读取其内部通道和报文ID，判断是否属于本次所需时间序列。|

#### 返回说明

bool；None选择全部帧。

#### 异常说明

无。
同ID的帧类型仍交既有绑定解析器核对，不能用筛选隐藏歧义。

源码：[`src/chronaxis/sources/text_can_decode.py:283`](../../../src/chronaxis/sources/text_can_decode.py#L283)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-CANTextDecodeRead-__next__"></a>
### `CANTextDecodeRead.__next__`

逐条返回原始报文和本次请求的解码信号值。

```python
CANTextDecodeRead.__next__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

DecodedCANRecord。

#### 异常说明

EOF/定位数据错/原I/O、预算、取消。

源码：[`src/chronaxis/sources/text_can_decode.py:292`](../../../src/chronaxis/sources/text_can_decode.py#L292)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-CANTextDecodeRead-close"></a>
### `CANTextDecodeRead.close`

关闭自有解析器及DBC状态，可重试。

```python
CANTextDecodeRead.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原关闭/预算错误。

源码：[`src/chronaxis/sources/text_can_decode.py:365`](../../../src/chronaxis/sources/text_can_decode.py#L365)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-CANTextDecodeRead-__enter__"></a>
### `CANTextDecodeRead.__enter__`

建立显式资源上下文。

```python
CANTextDecodeRead.__enter__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回当前对象本身。后续迭代或with语句使用的仍是同一个对象。

#### 异常说明

无。

源码：[`src/chronaxis/sources/text_can_decode.py:383`](../../../src/chronaxis/sources/text_can_decode.py#L383)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-CANTextDecodeRead-__exit__"></a>
### `CANTextDecodeRead.__exit__`

保原业务错误并收尾。

```python
CANTextDecodeRead.__exit__(exception_type, error, traceback)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`exception_type`|type[BaseException] &#124; None|是|无|位置或关键字。with代码块抛出的异常类型；正常离开时为None，由Python传入。|
|`error`|BaseException &#124; None|是|无|位置或关键字。with代码块抛出的异常对象；正常离开时为None，由Python传入。|
|`traceback`|TracebackType &#124; None|是|无|位置或关键字。异常发生时的调用栈；正常离开时为None，由Python传入，供异常继续传播。|

#### 返回说明

False。

#### 异常说明

正常退出时的关闭错误。

源码：[`src/chronaxis/sources/text_can_decode.py:388`](../../../src/chronaxis/sources/text_can_decode.py#L388)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-pack_text_records"></a>
## `pack_text_records`

把有限已解码原帧交给现有数值核心，不再次解码或重复DBC缩放。

```python
pack_text_records(definition, records, session_id, backend)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`definition`|[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)|是|无|位置或关键字。definition为SignalDefinition|
|`records`|tuple|是|无|位置或关键字。records为有限DecodedCANRecord tuple|
|`session_id`|str|是|无|位置或关键字。session_id会话|
|`backend`|str|是|无|位置或关键字。`"reference"`使用独立参考计算；`"numpy"`使用NumPy数组计算。须明确选择一种。|

### 返回说明

SignalSeries，保精确纳秒、同一时刻原序号和CANTextSourceRef；调用方负责批次数组的长期预算。

### 异常说明

来源/声明/记录类型不符，或既有pack_decoded类型、数值转换错误。

本函数直接报告的具体错误：

- `TypeError`：文本CAN归一化需要定义及有限解码记录tuple。
- `ValueError`：文本CAN记录与信号来源不一致。

源码：[`src/chronaxis/sources/text_can_decode.py:398`](../../../src/chronaxis/sources/text_can_decode.py#L398)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
