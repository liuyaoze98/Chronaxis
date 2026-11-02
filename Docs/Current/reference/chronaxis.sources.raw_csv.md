# chronaxis.sources.raw_csv

按明确列映射和时间格式直接读取原始CAN报文CSV，得到原始报文和行位置；不先转换为ASC。DBC解码由上层继续处理。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CANCSVLayout](chronaxis.sources.raw_csv_layout.md#api-CANCSVLayout)、[CANTextError](chronaxis.sources.raw_can.md#api-CANTextError)、[LegacyRawFrame](chronaxis.legacy.records.md#api-LegacyRawFrame)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[RawCANRecord](chronaxis.sources.raw_can.md#api-RawCANRecord)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)

## 对象导航

|对象|用途|
|---|---|
|[`CSVTimeSpec`](#api-CSVTimeSpec)|声明时间文字含义，固定偏移只施加一次，不用电脑日期或时区补值。|
|[`CSVTimeSpec.__post_init__`](#api-CSVTimeSpec-__post_init__)|校验时间政策。|
|[`CANCSVSpec`](#api-CANCSVSpec)|冻结单文件原始报文来源；布局/时间声明不打开输入或加载DBC。|
|[`CANCSVSpec.__post_init__`](#api-CANCSVSpec-__post_init__)|检查来源配置的字段类型、取值及相互关系，不读取数据文件。|
|[`_uint`](#api-_uint)|解析明确进制的非负整数。|
|[`_payload`](#api-_payload)|严格读取十六进制载荷，不补零/截短。|
|[`CSVClock`](#api-CSVClock)|保存一次来源的时间进度，默认拒绝回退，显式阈值才把大幅日内回退解释为次日。|
|[`CSVClock.__init__`](#api-CSVClock-__init__)|只建立状态。|
|[`CSVClock.parse`](#api-CSVClock-parse)|按声明转换并推进。|
|[`_csv_frame`](#api-_csv_frame)|把已明确映射的列转换成原帧，不按载荷/ID大小猜帧型。|
|[`_CSVLines`](#api-_CSVLines)|把一次有界表记录的物理行交给标准CSV解析器，位置/字节累计由父reader持有。|
|[`_CSVLines.__init__`](#api-_CSVLines-__init__)|借用父对象。|
|[`_CSVLines.__iter__`](#api-_CSVLines-__iter__)|不重新打开文件。|
|[`_CSVLines.__next__`](#api-_CSVLines-__next__)|提供一个实际物理行。|
|[`CANCSVRead`](#api-CANCSVRead)|拥有一个文件、CSV语法迭代器和时钟，正常/失败/取消均关闭自有资源。|
|[`CANCSVRead.__init__`](#api-CANCSVRead-__init__)|预约并只读打开一次。|
|[`CANCSVRead.closed`](#api-CANCSVRead-closed)|查看本对象负责的资源是否已经全部关闭。|
|[`CANCSVRead.__iter__`](#api-CANCSVRead-__iter__)|迭代同次扫描。|
|[`CANCSVRead._next_row`](#api-CANCSVRead-_next_row)|取得一条有界CSV表记录。|
|[`CANCSVRead._initialize`](#api-CANCSVRead-_initialize)|按声明跳过记录/绑定表头一次。|
|[`CANCSVRead.__next__`](#api-CANCSVRead-__next__)|返回下一原始CAN记录。|
|[`CANCSVRead.close`](#api-CANCSVRead-close)|关闭文件和解析状态再归还自有预算，可重试。|
|[`CANCSVRead.__enter__`](#api-CANCSVRead-__enter__)|提供受控读取上下文。|
|[`CANCSVRead.__exit__`](#api-CANCSVRead-__exit__)|保留原错并收尾。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass, field
from datetime import timezone, timedelta
from decimal import Decimal, localcontext
from pathlib import Path
from ..legacy.records import LegacyRawFrame
from ..results.budget import ResourceBudget, _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..timebase.conversion import convert_time, checked_add_ns, parse_datetime_ns, require_int64_ns
from .raw_can import RawCANRecord, CANTextError
from .raw_csv_layout import CANCSVLayout, MAX_COLUMNS
```

</details>

<a id="api-CSVTimeSpec"></a>
## `CSVTimeSpec`

声明时间文字含义，固定偏移只施加一次，不用电脑日期或时区补值。

```python
class CSVTimeSpec
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`format`|str|否|'numeric'|numeric、clock、clock-ms-us-v1或iso8601，必须显式选择。|
|`unit`|str|否|'s'|numeric的s/ms/us/ns，其他格式只接受默认s，避免无效配置。|
|`offset_ns`|int|否|0|数值固定平移；日内时间可据明确原点映射到会话。|
|`timezone_offset_minutes`|int &#124; None|否|None|仅ISO无时区文本的显式补充。 None表示不为ISO文本补时区；无时区ISO值需显式提供偏移。|
|`rollover_min_drop_ns`|int &#124; None|否|None|两种日内格式可选：回退至少此纳秒数才按次日解释。|

源码：[`src/chronaxis/sources/raw_csv.py:32`](../../../src/chronaxis/sources/raw_csv.py#L32)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-CSVTimeSpec-__post_init__"></a>
### `CSVTimeSpec.__post_init__`

校验时间政策。

```python
CSVTimeSpec.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

类型、格式、单位、时区或午夜规则非法。

本函数直接报告的具体错误：

- `ValueError`：CSV时间格式或单位不支持。
- `ValueError`：非数值时间不能额外声明数值单位。
- `ValueError`：只有ISO时间可声明整数分钟时区偏移。
- `ValueError`：跨午夜阈值需日内时间格式的0到一天之间整数纳秒。

源码：[`src/chronaxis/sources/raw_csv.py:41`](../../../src/chronaxis/sources/raw_csv.py#L41)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-CANCSVSpec"></a>
## `CANCSVSpec`

冻结单文件原始报文来源；布局/时间声明不打开输入或加载DBC。

```python
class CANCSVSpec
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|CSV/TXT只是文件名，不用于推断格式。|
|`layout`|[CANCSVLayout](chronaxis.sources.raw_csv_layout.md#api-CANCSVLayout)|是|无|编码、分隔符、列/中文映射及明确固定值。|
|`time`|[CSVTimeSpec](chronaxis.sources.raw_csv.md#api-CSVTimeSpec)|否|调用 CSVTimeSpec() 生成|时间解释单独声明。|
|`id_base`|int &#124; str|否|'auto'|0x十六进制、0b二进制、无前缀十进制；裸十六进制表可显式选16。|
|`length_base`|int|否|10|DLC/字节数列的明确进制，原始CSV的0x08应设16。|
|`channel_origin`|int|否|0|原列从0或1开始，统一转换为0基通道。|
|`payload_style`|str|否|'spaced'|spaced逐字节，或contiguous连续偶数位十六进制。|

源码：[`src/chronaxis/sources/raw_csv.py:62`](../../../src/chronaxis/sources/raw_csv.py#L62)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-CANCSVSpec-__post_init__"></a>
### `CANCSVSpec.__post_init__`

检查来源配置的字段类型、取值及相互关系，不读取数据文件。

```python
CANCSVSpec.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

声明类型或不支持选项。

本函数直接报告的具体错误：

- `TypeError`：CANCSVSpec需要Path、CANCSVLayout及CSVTimeSpec。
- `ValueError`：原始CAN CSV当前不支持该逐行编码。
- `ValueError`：CSV ID/长度进制需要10或16。
- `ValueError`：CSV通道起点或载荷布局错误。

源码：[`src/chronaxis/sources/raw_csv.py:73`](../../../src/chronaxis/sources/raw_csv.py#L73)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_uint"></a>
## `_uint`

解析明确进制的非负整数。

```python
_uint(value, base, maximum, label)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|str &#124; int|是|无|位置或关键字。CSV字段取出的文本或显式常量整数，按base转成无符号整数并检查上限。|
|`base`|int|是|无|位置或关键字。字段的解析进制，10为十进制，16为十六进制。|
|`maximum`|int|是|无|位置或关键字。可接受的最大数值，包含该上限；编码函数中表示最大字节数。|
|`label`|str|是|无|位置或关键字。错误信息中使用的字段名，例如channel或frame_id，用于指出哪一项填写有误。|

### 返回说明

int。

### 异常说明

ValueError为符号/字符/隐式转换或越界，不允许bool/下划线。

源码：[`src/chronaxis/sources/raw_csv.py:91`](../../../src/chronaxis/sources/raw_csv.py#L91)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_payload"></a>
## `_payload`

严格读取十六进制载荷，不补零/截短。

```python
_payload(text, style)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`text`|str|是|无|位置或关键字。CSV数据字段中的原始文字，按style解释为十六进制字节。|
|`style`|str|是|无|位置或关键字。数据字节排列格式，支持值及填写例子见[原始CSV布局](../text-inputs.md)。|

### 返回说明

bytes。

### 异常说明

格式/长度错误。

本函数直接报告的具体错误：

- `ValueError`：分隔载荷需不超过64个十六进制字节。
- `ValueError`：连续载荷需不超过64字节的偶数位十六进制。

源码：[`src/chronaxis/sources/raw_csv.py:118`](../../../src/chronaxis/sources/raw_csv.py#L118)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-CSVClock"></a>
## `CSVClock`

保存一次来源的时间进度，默认拒绝回退，显式阈值才把大幅日内回退解释为次日。

```python
CSVClock(spec)
```


源码：[`src/chronaxis/sources/raw_csv.py:133`](../../../src/chronaxis/sources/raw_csv.py#L133)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-CSVClock-__init__"></a>
### `CSVClock.__init__`

只建立状态。

```python
CSVClock.__init__(spec)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|[CSVTimeSpec](chronaxis.sources.raw_csv.md#api-CSVTimeSpec)|是|无|位置或关键字。spec为CSVTimeSpec。|

#### 返回说明

时钟。

#### 异常说明

类型错误。

本函数直接报告的具体错误：

- `TypeError`：CSVClock需要CSVTimeSpec。

源码：[`src/chronaxis/sources/raw_csv.py:136`](../../../src/chronaxis/sources/raw_csv.py#L136)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-CSVClock-parse"></a>
### `CSVClock.parse`

按声明转换并推进。

```python
CSVClock.parse(value)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|str &#124; int|是|无|位置或关键字。经列映射取得的时间字段；按来源配置的timestamp_unit、时间格式和时区解析。|

#### 返回说明

(int64纳秒,量化bool)。

#### 异常说明

格式/时区/回退/越界。

本函数直接报告的具体错误：

- `ValueError`：CSV时间需要有限文字或整数。
- `ValueError`：CSV来源时间回退。
- `ValueError`：日内时间需要明确时分秒文字。
- `ValueError`：日内时分秒越界。
- `ValueError`：CSV日内时间回退，未满足明确跨午夜规则。

源码：[`src/chronaxis/sources/raw_csv.py:143`](../../../src/chronaxis/sources/raw_csv.py#L143)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_csv_frame"></a>
## `_csv_frame`

把已明确映射的列转换成原帧，不按载荷/ID大小猜帧型。

```python
_csv_frame(values, spec, time_ns, flag_resolver=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`values`|dict[str, object]|是|无|位置或关键字。完成列映射后的标准帧字段，如id、channel、data等，见[原始CSV布局](../text-inputs.md)。|
|`spec`|[CANCSVSpec](chronaxis.sources.raw_csv.md#api-CANCSVSpec)|是|无|位置或关键字。该来源的CSV布局、时间及帧格式声明，用于解释映射后字段。|
|`time_ns`|int|是|无|位置或关键字。当前计算时刻，单位为纳秒；推进检测器时不能早于上一次已处理的时刻。|
|`flag_resolver`|Callable &#124; None|否|None|位置或关键字。可选回调(channel, frame_id, extended, fd)→(bool, bool)，只补CSV缺失的帧型；默认None表示不能自动补齐。已有列值不会被覆盖，实际分析入口传入本次DBC解析器。|

### 返回说明

(LegacyRawFrame, DLC编码或None)。

### 异常说明

ID/通道/载荷/标志/DLC不一致。

本函数直接报告的具体错误：

- `ValueError`：CSV通道低于明确起点。
- `ValueError`：CSV声明载荷长度与实际字节数不一致。
- `ValueError`：经典CAN不能携带FD BRS/ESI标志。
- `ValueError`：远程帧需经典CAN、空载荷和明确DLC编码。
- `ValueError`：当前CSV错误帧需空载荷/零长度。
- `ValueError`：CSV DLC编码与载荷长度不一致。
- `ValueError`：CAN FD字节数不能对应合法DLC编码。

源码：[`src/chronaxis/sources/raw_csv.py:200`](../../../src/chronaxis/sources/raw_csv.py#L200)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_CSVLines"></a>
## `_CSVLines`

把一次有界表记录的物理行交给标准CSV解析器，位置/字节累计由父reader持有。

```python
_CSVLines(owner)
```


源码：[`src/chronaxis/sources/raw_csv.py:256`](../../../src/chronaxis/sources/raw_csv.py#L256)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_CSVLines-__init__"></a>
### `_CSVLines.__init__`

借用父对象。

```python
_CSVLines.__init__(owner)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|[CANCSVRead](chronaxis.sources.raw_csv.md#api-CANCSVRead)|是|无|位置或关键字。当前CSV读取对象，提供行号、文件和取消检查。|

#### 返回说明

行迭代器。

#### 异常说明

无。

源码：[`src/chronaxis/sources/raw_csv.py:259`](../../../src/chronaxis/sources/raw_csv.py#L259)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_CSVLines-__iter__"></a>
### `_CSVLines.__iter__`

不重新打开文件。

```python
_CSVLines.__iter__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回当前对象本身。后续迭代或with语句使用的仍是同一个对象。

#### 异常说明

无。

源码：[`src/chronaxis/sources/raw_csv.py:264`](../../../src/chronaxis/sources/raw_csv.py#L264)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_CSVLines-__next__"></a>
### `_CSVLines.__next__`

提供一个实际物理行。

```python
_CSVLines.__next__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

含换行str。

#### 异常说明

EOF、定位编码错、超限或取消。

源码：[`src/chronaxis/sources/raw_csv.py:269`](../../../src/chronaxis/sources/raw_csv.py#L269)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-CANCSVRead"></a>
## `CANCSVRead`

拥有一个文件、CSV语法迭代器和时钟，正常/失败/取消均关闭自有资源。

```python
CANCSVRead(spec, budget, *, check_cancel=None, retain_original=True, retain_source_time=True, flag_resolver=None, selected_ids=None)
```


源码：[`src/chronaxis/sources/raw_csv.py:295`](../../../src/chronaxis/sources/raw_csv.py#L295)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-CANCSVRead-__init__"></a>
### `CANCSVRead.__init__`

预约并只读打开一次。

```python
CANCSVRead.__init__(spec, budget, *, check_cancel=None, retain_original=True, retain_source_time=True, flag_resolver=None, selected_ids=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|[CANCSVSpec](chronaxis.sources.raw_csv.md#api-CANCSVSpec)|是|无|位置或关键字。原始CAN CSV来源声明，包含布局、时间和解析设置。|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)|是|无|位置或关键字。本次读取共用的资源额度管理器，记录内存、文件及磁盘使用量。|
|`check_cancel`|Callable[[], None] &#124; None|否|None|仅关键字。可选无参取消检查函数；需要停止时抛出异常，None不额外检查。|
|`retain_original`|bool|否|True|仅关键字。是否保留解析前原始文本；关闭时仍解析并检查输入，只是不保存原文副本。|
|`retain_source_time`|bool|否|True|仅关键字。是否保留导出实际需要的源时间坐标；关闭时不额外保留源时间副本。|
|`flag_resolver`|Callable &#124; None|否|None|仅关键字。可选回调(channel, frame_id, extended, fd)→(bool, bool)，只补CSV缺失的帧型；默认None表示不能自动补齐。已有列值不会被覆盖，实际分析入口传入本次DBC解析器。|
|`selected_ids`|tuple[int, ...] &#124; None|否|None|仅关键字。需要处理的报文ID；默认None读取全部记录。仅在不需要完整原帧和来源时间的消息分析路径使用：原始CSV先读ID，未匹配时跳过该行的时间、载荷和帧型解析；目标记录仍完整校验。ASC路径不使用此筛选。|

#### 返回说明

reader，不预读数据。

#### 异常说明

类型/预算/I/O原错；清理失败保raw_csv_cleanup_owner。

本函数直接报告的具体错误：

- `TypeError`：CANCSVRead需要CANCSVSpec和ResourceBudget。
- `TypeError`：CSV取消检查需要可调用对象。

源码：[`src/chronaxis/sources/raw_csv.py:298`](../../../src/chronaxis/sources/raw_csv.py#L298)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-CANCSVRead-closed"></a>
### `CANCSVRead.closed`

查看本对象负责的资源是否已经全部关闭。

```python
CANCSVRead.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/sources/raw_csv.py:338`](../../../src/chronaxis/sources/raw_csv.py#L338)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-CANCSVRead-__iter__"></a>
### `CANCSVRead.__iter__`

迭代同次扫描。

```python
CANCSVRead.__iter__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回当前对象本身。后续迭代或with语句使用的仍是同一个对象。

#### 异常说明

无，不另开文件。

源码：[`src/chronaxis/sources/raw_csv.py:343`](../../../src/chronaxis/sources/raw_csv.py#L343)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-CANCSVRead-_next_row"></a>
### `CANCSVRead._next_row`

取得一条有界CSV表记录。

```python
CANCSVRead._next_row()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

str列表。

#### 异常说明

EOF/定位语法错/取消。

源码：[`src/chronaxis/sources/raw_csv.py:348`](../../../src/chronaxis/sources/raw_csv.py#L348)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-CANCSVRead-_initialize"></a>
### `CANCSVRead._initialize`

按声明跳过记录/绑定表头一次。

```python
CANCSVRead._initialize()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

缺表头/缺列或EOF。

源码：[`src/chronaxis/sources/raw_csv.py:363`](../../../src/chronaxis/sources/raw_csv.py#L363)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-CANCSVRead-__next__"></a>
### `CANCSVRead.__next__`

返回下一原始CAN记录。

```python
CANCSVRead.__next__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

RawCANRecord。

#### 异常说明

EOF/定位坏行/预算/取消原错。

源码：[`src/chronaxis/sources/raw_csv.py:388`](../../../src/chronaxis/sources/raw_csv.py#L388)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-CANCSVRead-close"></a>
### `CANCSVRead.close`

关闭文件和解析状态再归还自有预算，可重试。

```python
CANCSVRead.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

关闭/预算原错。

源码：[`src/chronaxis/sources/raw_csv.py:441`](../../../src/chronaxis/sources/raw_csv.py#L441)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-CANCSVRead-__enter__"></a>
### `CANCSVRead.__enter__`

提供受控读取上下文。

```python
CANCSVRead.__enter__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回当前对象本身。后续迭代或with语句使用的仍是同一个对象。

#### 异常说明

无。

源码：[`src/chronaxis/sources/raw_csv.py:457`](../../../src/chronaxis/sources/raw_csv.py#L457)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-CANCSVRead-__exit__"></a>
### `CANCSVRead.__exit__`

保留原错并收尾。

```python
CANCSVRead.__exit__(exception_type, error, traceback)
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

无原错时关闭失败。

源码：[`src/chronaxis/sources/raw_csv.py:462`](../../../src/chronaxis/sources/raw_csv.py#L462)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
