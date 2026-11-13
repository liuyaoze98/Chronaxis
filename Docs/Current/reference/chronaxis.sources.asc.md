# `chronaxis.sources.asc`

按明确指定的ASC版本逐行读取原始CAN报文，保留文件位置与原时间；格式错误立即报告，不自动切换解析器。公共can_asc入口使用本读取器。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CANTextError](chronaxis.sources.raw_can.md#api-CANTextError)、[LegacyRawFrame](chronaxis.legacy.records.md#api-LegacyRawFrame)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[RawCANRecord](chronaxis.sources.raw_can.md#api-RawCANRecord)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)

## 对象导航

|对象|用途|
|---|---|
|[`ASCSpec`](#api-ASCSpec)|固定一次ASC读取的格式、编码、时间参考；不猜测本地时区。|
|[`ASCSpec.__post_init__`](#api-ASCSpec-__post_init__)|检查配置字段的类型、取值及相互关系，不读取数据文件。|
|[`_date`](#api-_date)|解析ASC英文日期，不调用宿主时区。|
|[`_unsigned`](#api-_unsigned)|严格解析无符号字段。|
|[`_status_event`](#api-_status_event)|识别已知CAN控制器状态事件，验证格式后告知调用方不产生数据帧。|
|[`_fd_error_diagnostics`](#api-_fd_error_diagnostics)|检查Vector CAN FD错误帧的结构，返回描述实际帧类型的扩展标志。|
|[`_error_diagnostics`](#api-_error_diagnostics)|验证错误帧的已知诊断尾，不将可能受损的诊断ID或DLC当成正常帧字段。|
|[`_frame`](#api-_frame)|解析标准数据部分，精确检查长度。|
|[`_repository_frame`](#api-_repository_frame)|同次解析标准统计尾或显式Sclicer布局，再复用标准字段检查。|
|[`ASCRead`](#api-ASCRead)|拥有单个文件及固定行缓冲预算；完成、错误和取消均关闭，禁止中途重读。|
|[`ASCRead.__init__`](#api-ASCRead-__init__)|预约后打开一次。|
|[`ASCRead.closed`](#api-ASCRead-closed)|提供真实关闭状态。|
|[`ASCRead.last_exact_time`](#api-ASCRead-last_exact_time)|取得最近参与时间顺序检查的精确秒值，供下一连续文件接续比较。|
|[`ASCRead.__iter__`](#api-ASCRead-__iter__)|返回本次读取。|
|[`ASCRead._set_date`](#api-ASCRead-_set_date)|设置段基准。|
|[`ASCRead._line`](#api-ASCRead-_line)|解释一行。|
|[`ASCRead._check_order`](#api-ASCRead-_check_order)|拒绝所需时间序列回退，包括舍入后相同的亚纳秒回退。|
|[`ASCRead.__next__`](#api-ASCRead-__next__)|读取到下一帧或EOF。|
|[`ASCRead.close`](#api-ASCRead-close)|关闭自有文件再归还预算，可重试。|
|[`ASCRead.__enter__`](#api-ASCRead-__enter__)|支持显式读取上下文。|
|[`ASCRead.__exit__`](#api-ASCRead-__exit__)|保留原错并收尾。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from pathlib import Path
from ..legacy.records import LegacyRawFrame
from ..results.budget import ResourceBudget, _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..timebase.conversion import checked_add_ns, convert_time, require_int64_ns
from .raw_can import CANTextError, RawCANRecord
```

</details>

<a id="api-ASCSpec"></a>
## `ASCSpec`

固定一次ASC读取的格式、编码、时间参考；不猜测本地时区。

```python
class ASCSpec
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|单文件，连续多文件的时序合并由外层负责。|
|`parser_version`|str|否|'vector-asc-v1'|标准布局含统计尾；statistics保留显式入口，sclicer须显式选择。|
|`encoding`|str|否|'utf-8-sig'|严格解码，兼容UTF-8 BOM，不自动换编码。|
|`time_reference`|str|否|'relative'|relative为首段原点，epoch为显式日期/时区。|
|`timezone_offset_minutes`|int &#124; None|否|None|epoch必填，避免依赖宿主时区。 None适用于不需要绝对epoch换算的相对时间；time_reference=epoch时必须填写。|
|`offset_ns`|int|否|0|一次明确的int64平移，不更改原始时间文本。|

源码：[`src/chronaxis/sources/asc.py:31`](../../../src/chronaxis/sources/asc.py#L31)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ASCSpec-__post_init__"></a>
### `ASCSpec.__post_init__`

检查配置字段的类型、取值及相互关系，不读取数据文件。

```python
ASCSpec.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

类型或不支持的选项。

本函数直接报告的具体错误：

- `TypeError`：ASC需要Path和明确编码。
- `ValueError`：ASC当前只支持UTF-8/ASCII/GBK/CP1252/Latin-1逐行编码。
- `ValueError`：不支持的ASC解析版本或时间参考。
- `ValueError`：ASC时区偏移需-1439到1439整数分钟。
- `ValueError`：ASC日历时间需要显式时区偏移。

源码：[`src/chronaxis/sources/asc.py:41`](../../../src/chronaxis/sources/asc.py#L41)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_date"></a>
## `_date`

解析ASC英文日期，不调用宿主时区。

```python
_date(text)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`text`|str|是|无|位置或关键字。去掉星期部分后的ASC日期文本，解析为文件头的日期和时刻。|

### 返回说明

无时区datetime。

### 异常说明

ValueError为月份或日期格式不支持。

本函数直接报告的具体错误：

- `ValueError`：ASC日期格式或取值无效。
- `ValueError`：ASC日期需要英文月份和明确年月日。

源码：[`src/chronaxis/sources/asc.py:61`](../../../src/chronaxis/sources/asc.py#L61)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_unsigned"></a>
## `_unsigned`

严格解析无符号字段。

```python
_unsigned(text, base, maximum, label)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`text`|str|是|无|位置或关键字。原文件中的无符号整数文本，按base解释并检查maximum上限。|
|`base`|int|是|无|位置或关键字。10按十进制解析，16按十六进制解析，由ASC文件头决定。|
|`maximum`|int|是|无|位置或关键字。可接受的最大数值，包含该上限；编码函数中表示最大字节数。|
|`label`|str|是|无|位置或关键字。错误信息中使用的字段名，例如channel或frame_id，用于指出哪一项填写有误。|

### 返回说明

int。

### 异常说明

ValueError为符号、非法字符、空值或越界；拒绝下划线和隐式前缀。

源码：[`src/chronaxis/sources/asc.py:81`](../../../src/chronaxis/sources/asc.py#L81)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_status_event"></a>
## `_status_event`

识别已知CAN控制器状态事件，验证格式后告知调用方不产生数据帧。

```python
_status_event(tokens: list[str]) -> bool
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`tokens`|list[str]|是|无|位置或关键字。tokens为去掉时间的有界字段列表|

### 返回说明

bool；普通帧为False，完整的chip status事件为True，无文件或状态副作用。

### 异常说明

ValueError为CAN事件的未知状态、通道、计数或残缺布局；不跳过未知事件。

返回类型：bool。

源码：[`src/chronaxis/sources/asc.py:96`](../../../src/chronaxis/sources/asc.py#L96)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_fd_error_diagnostics"></a>
## `_fd_error_diagnostics`

检查Vector CAN FD错误帧的结构，返回描述实际帧类型的扩展标志。

```python
_fd_error_diagnostics(tokens: list[str]) -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`tokens`|list[str]|是|无|位置或关键字。tokens为ErrorFrame后的错误文字、诊断字段、部分载荷和完整计时尾。|

### 返回说明

extFlags整数；不保留错误文字、部分载荷或诊断ID供正常信号解码。

### 异常说明

ValueError为未知阶段、缺字段、无效数值、载荷数量不符或保留位非零。
已损坏帧的DLC与已取得的DataLength可能不一致，不套用正常帧的长度关系。

返回类型：int。

源码：[`src/chronaxis/sources/asc.py:122`](../../../src/chronaxis/sources/asc.py#L122)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_error_diagnostics"></a>
## `_error_diagnostics`

验证错误帧的已知诊断尾，不将可能受损的诊断ID或DLC当成正常帧字段。

```python
_error_diagnostics(tokens: list[str], *, fd: bool) -> int | None
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`tokens`|list[str]|是|无|位置或关键字。tokens为ErrorFrame之后的字段|
|`fd`|bool|是|无|仅关键字。fd表明是否为CAN FD布局。|

### 返回说明

完整FD诊断的extFlags，其他已知形式返回None；无副作用。

### 异常说明

ValueError为未知/残缺诊断或无效数值。

返回类型：int &#124; None。

源码：[`src/chronaxis/sources/asc.py:161`](../../../src/chronaxis/sources/asc.py#L161)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_frame"></a>
## `_frame`

解析标准数据部分，精确检查长度。

```python
_frame(tokens, base, seconds)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`tokens`|list[str]|是|无|位置或关键字。本行去掉时间字段后的帧字段，按ASC标准格式解释通道、ID、方向和数据。|
|`base`|int|是|无|位置或关键字。文件头声明的数字进制：10为十进制，16为十六进制。|
|`seconds`|float|是|无|位置或关键字。原始秒时间戳的兼容表示；精确纳秒坐标另行保存，不从此值反推已保存纳秒。|

### 返回说明

(LegacyRawFrame, DLC编码或None)。

### 异常说明

ValueError为未知布局、身份或载荷错误；附加诊断由_error_diagnostics校验，拒绝未知或残缺的经典诊断以及附诊断的FD错误帧。

本函数直接报告的具体错误：

- `ValueError`：ASC行缺少帧或事件内容。
- `ValueError`：经典CAN行缺少ID、方向或d/r类型。
- `ValueError`：经典CAN数据帧缺少DLC。
- `ValueError`：ASC通道从1开始。
- `ValueError`：ASC方向需要Rx或Tx。
- `ValueError`：ASC实际载荷与声明长度不一致。
- `ValueError`：CAN FD BRS/ESI需要0或1。
- `ValueError`：CAN FD DLC编码与实际长度不一致。
- `ValueError`：CAN FD载荷或标准附加字段数量错误。
- `ValueError`：经典CAN类型需要d或r。

源码：[`src/chronaxis/sources/asc.py:186`](../../../src/chronaxis/sources/asc.py#L186)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_repository_frame"></a>
## `_repository_frame`

同次解析标准统计尾或显式Sclicer布局，再复用标准字段检查。

```python
_repository_frame(tokens, base, seconds, version)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`tokens`|list[str]|是|无|位置或关键字。去掉时间后的标准ASC帧字段或显式Sclicer字段；默认也识别标准统计尾。|
|`base`|int|是|无|位置或关键字。文件头声明的进制，10或16，用于解析ID和数据字段。|
|`seconds`|float|是|无|位置或关键字。原行秒时间戳的兼容表示，保留给旧帧接口。|
|`version`|str|是|无|位置或关键字。所选ASC格式版本，支持的完整名称及差别见[ASC版本](../text-inputs.md)。|

### 返回说明

(原帧快照, DLC编码)。

### 异常说明

ValueError/IndexError为布局、统计身份或载荷错误。
不探测后重新读取；同文件可含该版本规定的经典及FD行，未声明变体拒绝。

本函数直接报告的具体错误：

- `ValueError`：ASC统计尾需Length = n BitCount = n ID = n。
- `ValueError`：ASC统计ID与报文ID不一致。
- `ValueError`：sclicer-asc-v1只接受明确的CAN FD数据行。
- `ValueError`：Sclicer实际载荷与声明长度不一致。

源码：[`src/chronaxis/sources/asc.py:272`](../../../src/chronaxis/sources/asc.py#L272)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ASCRead"></a>
## `ASCRead`

拥有单个文件及固定行缓冲预算；完成、错误和取消均关闭，禁止中途重读。

```python
ASCRead(spec, budget, *, check_cancel=None, retain_original=True, retain_source_time=True, time_selector=None, previous_exact_time=None)
```


源码：[`src/chronaxis/sources/asc.py:313`](../../../src/chronaxis/sources/asc.py#L313)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ASCRead-__init__"></a>
### `ASCRead.__init__`

预约后打开一次。

```python
ASCRead.__init__(spec, budget, *, check_cancel=None, retain_original=True, retain_source_time=True, time_selector=None, previous_exact_time=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|[ASCSpec](chronaxis.sources.asc.md#api-ASCSpec)|是|无|位置或关键字。spec为ASCSpec|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)|是|无|位置或关键字。budget为共用的资源用量记录|
|`check_cancel`|Callable[[], None] &#124; None|否|None|仅关键字。可选的无参取消检查函数。需要终止时由它抛出异常；None表示不额外调用取消检查。|
|`retain_original`|bool|否|True|仅关键字。是否保留解析前原始文本；关闭时仍解析并检查输入，只是不保存原文副本。|
|`retain_source_time`|bool|否|True|仅关键字。是否保留导出实际需要的源时间坐标；关闭时不额外保留源时间副本。|
|`time_selector`|Callable[[[LegacyRawFrame](chronaxis.legacy.records.md#api-LegacyRawFrame)], bool] &#124; None|否|None|仅关键字。接收已解析原帧并返回是否参与顺序检查。None保持全量检查；选择模式仍准确累加relative时间，不改原帧时刻。默认/选择两种模式都保留输入结构检查和逐行取消。|
|`previous_exact_time`|Decimal &#124; None|否|None|仅关键字。上一连续文件最近参与顺序检查的精确秒值，已含日期参考和文件偏移；None表示没有前序比较点。只用于当前比较状态，不加入逐帧记录或结果。|

#### 返回说明

可迭代reader。

#### 异常说明

类型、预算、打开失败；清理失败附asc_read_cleanup_owner。

本函数直接报告的具体错误：

- `TypeError`：ASCRead需要ASCSpec和ResourceBudget。
- `TypeError`：取消检查必须可调用。

源码：[`src/chronaxis/sources/asc.py:316`](../../../src/chronaxis/sources/asc.py#L316)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ASCRead-closed"></a>
### `ASCRead.closed`

提供真实关闭状态。

```python
ASCRead.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/sources/asc.py:354`](../../../src/chronaxis/sources/asc.py#L354)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ASCRead-last_exact_time"></a>
### `ASCRead.last_exact_time`

取得最近参与时间顺序检查的精确秒值，供下一连续文件接续比较。

```python
ASCRead.last_exact_time
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

Decimal或None。含日期参考和文件offset；空文件保持前序比较点。只保留当前状态，不额外保存每帧时间。

#### 异常说明

无。不向逐帧记录或输出增加另一套时间，关闭后仍可取得该比较状态。

源码：[`src/chronaxis/sources/asc.py:360`](../../../src/chronaxis/sources/asc.py#L360)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ASCRead-__iter__"></a>
### `ASCRead.__iter__`

返回本次读取。

```python
ASCRead.__iter__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回当前对象本身。后续迭代或with语句使用的仍是同一个对象。

#### 异常说明

无；不启动第二次扫描。

源码：[`src/chronaxis/sources/asc.py:368`](../../../src/chronaxis/sources/asc.py#L368)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ASCRead-_set_date"></a>
### `ASCRead._set_date`

设置段基准。

```python
ASCRead._set_date(value, trigger=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|datetime|是|无|位置或关键字。从ASC文件头实际解析出的日期和时刻，保存为本次读取的时间依据。|
|`trigger`|bool|否|False|位置或关键字。trigger是否真实触发块。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

时间越界。

源码：[`src/chronaxis/sources/asc.py:373`](../../../src/chronaxis/sources/asc.py#L373)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ASCRead-_line"></a>
### `ASCRead._line`

解释一行。

```python
ASCRead._line(line)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`line`|str|是|无|位置或关键字。line有界去空白文本。|

#### 返回说明

RawCANRecord或元数据None。

#### 异常说明

格式错误。

本函数直接报告的具体错误：

- `ValueError`：ASC数据前缺少明确base/timestamps头。
- `ValueError`：日历时间ASC缺少日期头。
- `ValueError`：ASC时间需要非负十进制秒。
- `ValueError`：ASC来源时间回退。
- `ValueError`：数据中途不允许重新定义ASC日期。
- `ValueError`：ASC进制仅接受在头部定义一次。
- `ValueError`：ASC头需base hex/dec timestamps absolute/relative。

源码：[`src/chronaxis/sources/asc.py:389`](../../../src/chronaxis/sources/asc.py#L389)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ASCRead-_check_order"></a>
### `ASCRead._check_order`

拒绝所需时间序列回退，包括舍入后相同的亚纳秒回退。

```python
ASCRead._check_order(exact)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`exact`|Decimal|是|无|位置或关键字。本行按ASC日期/relative语义得到、尚未加文件offset的精确秒值；统一偏移后与最近所需时刻比较，回退立即报错。|

#### 返回说明

None。

#### 异常说明

ValueError为回退。
只保存最近参与检查的时刻；不排序、不钳平，也不改写返回报文。

源码：[`src/chronaxis/sources/asc.py:446`](../../../src/chronaxis/sources/asc.py#L446)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ASCRead-__next__"></a>
### `ASCRead.__next__`

读取到下一帧或EOF。

```python
ASCRead.__next__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

RawCANRecord。

#### 异常说明

定位格式错、I/O或取消原错。

完成/失败后释放自有资源；已返回前缀不会重复。取消回调在每个物理行前检查。

源码：[`src/chronaxis/sources/asc.py:464`](../../../src/chronaxis/sources/asc.py#L464)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ASCRead-close"></a>
### `ASCRead.close`

关闭自有文件再归还预算，可重试。

```python
ASCRead.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

关闭或预算原错。

源码：[`src/chronaxis/sources/asc.py:502`](../../../src/chronaxis/sources/asc.py#L502)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ASCRead-__enter__"></a>
### `ASCRead.__enter__`

支持显式读取上下文。

```python
ASCRead.__enter__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回当前对象本身。后续迭代或with语句使用的仍是同一个对象。

#### 异常说明

无。

源码：[`src/chronaxis/sources/asc.py:515`](../../../src/chronaxis/sources/asc.py#L515)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ASCRead-__exit__"></a>
### `ASCRead.__exit__`

保留原错并收尾。

```python
ASCRead.__exit__(exception_type, error, traceback)
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

无原错时的关闭失败。

源码：[`src/chronaxis/sources/asc.py:520`](../../../src/chronaxis/sources/asc.py#L520)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
