# `chronaxis.results.raw_exports`

保存原始片段索引并复制已生成的BLF，不重新调用旧读写或解码路径。

输入是实际Segment范围、已关闭的BLF文件及其明确摘要，输出是连续编号的有界
JSONL索引和发布目录内的逐文件副本。exported保留正长actual，即使文件含零帧；
empty_range保留已知零长度actual；no_observation仅用于actual为None，不造空文件。
append核实际BLF字节/SHA后写索引；seal真正关闭writer才开放独立reader。reader只有
完整EOF、流SHA/数量与真实关闭均成功后才verified_eof，提前关闭不能证明完整。

所有新增RAM与索引spool先预约，原BLF由旧writer封装预约，本模块不重复计算。
copy_to只逐条读索引、有限块复制和核现成BLF；发布副本不计入分析暂存配额。
输出失败只清本次复制资源，保sealed输入与其他reader，恢复后可向新目录重试；
原索引或原BLF内容损坏仍使输入仓failed，不把坏输入当作可发布结果。
所有真实FD、未返回reader和费用槽由本store可达，关闭失败可重试，保原异常/取消
及最高raw_export_store_cleanup_owner；文件与累计spool保留，不凭共享余额补账。
本模块只依赖标准库、创建后不可修改的对象和有界JSON，不导入CAN库，不声称整进程RSS受限。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Interval](chronaxis.core.models.md#api-Interval)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[ResultFormatError](chronaxis.results.errors.md#api-ResultFormatError)

## 对象导航

|对象|用途|
|---|---|
|[`_integer`](#api-_integer)|校验非负原生整数，不把bool或浮点作为数量。|
|[`_text`](#api-_text)|检查有界安全原文本，保留大小写、Unicode和合法ID标点。|
|[`_interval`](#api-_interval)|要求冻结Interval及原生int64端点，不重建或改变原范围。|
|[`_packet`](#api-_packet)|把固定模型转为固定JSON树，不复制文件内容或任意元数据。|
|[`RawExportRecord`](#api-RawExportRecord)|保存一个原片段导出事实；构造校声明，不据此宣称文件已读取或写出。|
|[`RawExportRecord.__post_init__`](#api-RawExportRecord-__post_init__)|检查数量、身份、范围和文件状态的闭合关系，整条记录有界。|
|[`_decode`](#api-_decode)|严格还原一条固定索引，不接受多键、重复JSON键或浮点端点。|
|[`_write_all`](#api-_write_all)|完整写有限bytes，短写继续，零写或非法返回立即失败。|
|[`RawExportStore`](#api-RawExportStore)|拥有索引、活reader与当前复制FD；状态与真实closed事实分别记录。|
|[`RawExportStore.__init__`](#api-RawExportStore-__init__)|先付固定费用，再在全新根独占创建目录和索引writer。|
|[`RawExportStore.closed`](#api-RawExportStore-closed)|查看本对象是否已经完成关闭。|
|[`RawExportStore.spool_bytes`](#api-RawExportStore-spool_bytes)|读取仅本索引新增的累计配额。|
|[`RawExportStore._require`](#api-RawExportStore-_require)|检查活状态，半关闭或失败前缀不能继续使用。|
|[`RawExportStore._fail`](#api-RawExportStore-_fail)|保原主错/取消、failed状态和最高恢复owner，清理副错只记note。|
|[`RawExportStore.next_path`](#api-RawExportStore-next_path)|计算当前记录对应BLF路径，不创建文件、不跳过无观测索引。|
|[`RawExportStore._relation`](#api-RawExportStore-_relation)|核本仓归属和连续索引，不从文件名猜来源。|
|[`RawExportStore._close_fd`](#api-RawExportStore-_close_fd)|真实FD关闭后才撤槽，关闭后抛错也依据actual.closed处理。|
|[`RawExportStore._file`](#api-RawExportStore-_file)|有限块核实际BLF；可同时复制到独占目标，不调用任何CAN读写器。|
|[`RawExportStore._check_copy`](#api-RawExportStore-_check_copy)|在已预约IO空间内回读真实发布文件，BLF与索引使用同一有界验证。|
|[`RawExportStore.append`](#api-RawExportStore-append)|预付索引RAM/累计spool，核实际文件后完整写一行再推进计数。|
|[`RawExportStore.seal`](#api-RawExportStore-seal)|真实关闭索引writer并固定流SHA；零记录亦可封口。|
|[`RawExportStore.iter_records`](#api-RawExportStore-iter_records)|创建有限独立索引reader，未返回构造始终在本父pending槽可达。|
|[`RawExportStore.copy_to`](#api-RawExportStore-copy_to)|向新发布根独占创建原始目录与索引，逐条核验复制现成BLF。|
|[`RawExportStore.recover_copy`](#api-RawExportStore-recover_copy)|仅恢复上次输出复制的真实责任，保sealed固定输入及其他独立reader。|
|[`RawExportStore._close_copy_resources`](#api-RawExportStore-_close_copy_resources)|关闭本次copy子reader和FD，完全释放后再清当前缓冲与复制费用。|
|[`RawExportStore.close`](#api-RawExportStore-close)|关闭全部自有FD/reader并抵销自有RAM，文件与累计spool保留。|
|[`_RawExportReader`](#api-_RawExportReader)|拥有单个索引位置/摘要和固定读槽；完整EOF与成功关闭才verified_eof。|
|[`_RawExportReader.__init__`](#api-_RawExportReader-__init__)|先装父pending槽，再付费打开/登记真实reader。|
|[`_RawExportReader.__iter__`](#api-_RawExportReader-__iter__)|保持独立原位置。|
|[`_RawExportReader.__next__`](#api-_RawExportReader-__next__)|逐行校索引归属/序号，真实EOF核完整SHA、条数、文件数与字节数后关闭。|
|[`_RawExportReader.close`](#api-_RawExportReader-close)|真实关FD、抵销本笔费用并解除父登记后才closed，可持续重试。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from re import fullmatch
from ..core.models import Interval
from ..core.validation import require_identifier
from ..legacy.records import MAX_WIRE_BYTES, encode_packet, decode_packet
from ..timebase.conversion import INT64_MAX, require_int64_ns
from .budget import ResourceBudget
from .errors import ResultClosedError, ResultFormatError
from .spool import _cleanup_owner, _reserve_owned_ram, _release_owned_ram
```

</details>

<a id="api-_integer"></a>
## `_integer`

校验非负原生整数，不把bool或浮点作为数量。

```python
_integer(value, name, maximum=INT64_MAX)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int|是|无|位置或关键字。待检查的非负整数，bool不作为整数接受；还需满足maximum指定的上限。|
|`name`|str|是|无|位置或关键字。错误信息中使用的字段名，例如channel或frame_id，用于指出哪一项填写有误。|
|`maximum`|int|否|INT64_MAX|位置或关键字。可接受的最大数值，包含该上限；编码函数中表示最大字节数。|

### 返回说明

原int。

### 异常说明

TypeError/ValueError为类型或范围错误；不截断、不转换。

源码：[`src/chronaxis/results/raw_exports.py:40`](../../../src/chronaxis/results/raw_exports.py#L40)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_text"></a>
## `_text`

检查有界安全原文本，保留大小写、Unicode和合法ID标点。

```python
_text(value, name, *, identifier=False)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|str|是|无|位置或关键字。待检查的导出记录文本，按字段要求检查是否为空及内容是否合法。|
|`name`|str|是|无|位置或关键字。name位置|
|`identifier`|bool|否|False|仅关键字。identifier要求来源/会话简单名。|

### 返回说明

原str。

### 异常说明

TypeError/ValueError为非原生str、空白、控制字符、过长或名称非法。

源码：[`src/chronaxis/results/raw_exports.py:53`](../../../src/chronaxis/results/raw_exports.py#L53)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_interval"></a>
## `_interval`

要求冻结Interval及原生int64端点，不重建或改变原范围。

```python
_interval(value, name)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|[Interval](chronaxis.core.models.md#api-Interval)|是|无|位置或关键字。导出使用的纳秒时间范围，检查起止坐标和范围关系。|
|`name`|str|是|无|位置或关键字。name位置。|

### 返回说明

原Interval。

### 异常说明

TypeError/ValueError/OverflowError为类型、顺序或整数范围非法。

源码：[`src/chronaxis/results/raw_exports.py:68`](../../../src/chronaxis/results/raw_exports.py#L68)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_packet"></a>
## `_packet`

把固定模型转为固定JSON树，不复制文件内容或任意元数据。

```python
_packet(record)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`record`|[RawExportRecord](chronaxis.results.raw_exports.md#api-RawExportRecord)|是|无|位置或关键字。record为RawExportRecord。|

### 返回说明

仅13字段dict。

### 异常说明

内部模型属性错误传播；调用者另核整包64KiB上限。

源码：[`src/chronaxis/results/raw_exports.py:86`](../../../src/chronaxis/results/raw_exports.py#L86)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RawExportRecord"></a>
## `RawExportRecord`

保存一个原片段导出事实；构造校声明，不据此宣称文件已读取或写出。

```python
class RawExportRecord
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`index`|int|是|无|从0连续；对应唯一12位文件名，非业务排序键。|
|`source`|str|是|无|同一store的CAN来源安全名。|
|`session_id`|str|是|无|原会话安全名。|
|`segment_id`|str|是|无|实际Segment的原ID。|
|`window_id`|str|是|无|产生原片段的窗口ID。|
|`requested`|[Interval](chronaxis.core.models.md#api-Interval)|是|无|保留完整原请求范围。|
|`actual`|[Interval](chronaxis.core.models.md#api-Interval) &#124; None|是|无|原实际交集；已知点与无观测严格区分。|
|`frame_count`|int|是|无|原writer成功交付的帧数；正长范围可为0。|
|`file_name`|str &#124; None|是|无|exported固定为raw_segments/12位.blf。|
|`sha256`|str &#124; None|是|无|实际输出BLF字节SHA，不是原输入SHA。|
|`byte_count`|int|是|无|实际输出文件字节数。|
|`status`|str|是|无|`exported`表示已生成报文文件；`empty_range`表示选定时间范围为空；`no_observation`表示没有能支持该范围的来源观测。后两者不能当成成功导出了一个非空日志。|
|`device_label`|str|是|无|本条产生设备标签，与store严格一致。|

源码：[`src/chronaxis/results/raw_exports.py:100`](../../../src/chronaxis/results/raw_exports.py#L100)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RawExportRecord-__post_init__"></a>
### `RawExportRecord.__post_init__`

检查数量、身份、范围和文件状态的闭合关系，整条记录有界。

```python
RawExportRecord.__post_init__()
```

参数：无显式参数。


#### 参数说明

无，读取创建后不可修改的字段。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError/OverflowError为非法事实；不打开、stat或创建文件。

本函数直接报告的具体错误：

- `ValueError`：原始导出状态非法。
- `ValueError`：原始导出索引行超过64KiB。
- `ValueError`：raw_export.actual必须落在原requested内。
- `ValueError`：exported需正长实际范围。
- `ValueError`：原始导出文件名必须对应当前连续索引。
- `ValueError`：原始导出SHA需64位十六进制。
- `ValueError`：无观测/零范围必须保原actual且不得带文件、SHA或帧字节数。

源码：[`src/chronaxis/results/raw_exports.py:117`](../../../src/chronaxis/results/raw_exports.py#L117)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_decode"></a>
## `_decode`

严格还原一条固定索引，不接受多键、重复JSON键或浮点端点。

```python
_decode(payload)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`payload`|bytes|是|无|位置或关键字。payload为不含换行的有限bytes。|

### 返回说明

RawExportRecord。

### 异常说明

ResultFormatError保留底层结构/类型/时间校验原因；取消原样传播。

本函数直接报告的具体错误：

- `ValueError`：原始导出索引字段缺失或多余。
- `ValueError`：索引范围必须精确含start_ns/end_ns。
- `TypeError`：索引范围端点必须为原生int。

源码：[`src/chronaxis/results/raw_exports.py:151`](../../../src/chronaxis/results/raw_exports.py#L151)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_write_all"></a>
## `_write_all`

完整写有限bytes，短写继续，零写或非法返回立即失败。

```python
_write_all(handle, payload)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`handle`|BinaryIO|是|无|位置或关键字。本次操作已经打开的二进制文件对象；在此句柄上读写字节，不传文件路径。关闭责任仍由创建句柄的对象承担。|
|`payload`|bytes|是|无|位置或关键字。本次要完整写入的字节；处理短写，直到全部写完或发生错误。|

### 返回说明

返回None，不返回额外的计算值。

### 异常说明

原write/取消或OSError；费用由调用方先预约，不在此重复计算。

本函数直接报告的具体错误：

- `OSError`：原始导出文件写入未正确推进。

源码：[`src/chronaxis/results/raw_exports.py:175`](../../../src/chronaxis/results/raw_exports.py#L175)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RawExportStore"></a>
## `RawExportStore`

拥有索引、活reader与当前复制FD；状态与真实closed事实分别记录。

building只可append/seal；sealed可独立回读或重复copy。构建或输入完整性失败
转failed；普通复制输出失败仅恢复本次资源。关闭中需要重试close来完成关闭，不丢槽。

```python
RawExportStore(budget, work_dir, source, session_id, device_label='pending')
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`format`|str|类成员，不作为构造参数填写|'blf'|原始导出格式，由现有导出合同确定；决定文件编码，不表示分析结果表格式。|

源码：[`src/chronaxis/results/raw_exports.py:189`](../../../src/chronaxis/results/raw_exports.py#L189)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RawExportStore-__init__"></a>
### `RawExportStore.__init__`

先付固定费用，再在全新根独占创建目录和索引writer。

```python
RawExportStore.__init__(budget, work_dir, source, session_id, device_label='pending')
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)|是|无|位置或关键字。本次运行共用的ResourceBudget对象，用于检查内存和临时磁盘用量。当前对象在分配前申请额度，用完后归还；同一次运行的组件应使用同一个对象。|
|`work_dir`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。本次运行独占的工作目录，用来保存中间文件。自行指定时要求尚不存在；不会覆盖旧目录。|
|`source`|str|是|无|位置或关键字。source/session_id     为安全名|
|`session_id`|str|是|无|位置或关键字。本次会话的名字，用来防止把不同试验的数据混在一起。|
|`device_label`|str|否|'pending'|位置或关键字。产出记录的设备标签，接受任意非空文本，如lab-pc或试验台一号；省略时使用pending。标签不参与计算，也不根据文件路径猜测。|

#### 返回说明

building仓。

#### 异常说明

原声明/路径/预算/IO/取消；持续清理失败附最高恢复owner。

本函数直接报告的具体错误：

- `TypeError`：原始导出仓需ResourceBudget及显式新目录。
- `ValueError`：原始导出工作路径超过有界能力。

源码：[`src/chronaxis/results/raw_exports.py:198`](../../../src/chronaxis/results/raw_exports.py#L198)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RawExportStore-closed"></a>
### `RawExportStore.closed`

查看本对象是否已经完成关闭。

```python
RawExportStore.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无，FD或费用未清不为True。

源码：[`src/chronaxis/results/raw_exports.py:238`](../../../src/chronaxis/results/raw_exports.py#L238)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RawExportStore-spool_bytes"></a>
### `RawExportStore.spool_bytes`

读取仅本索引新增的累计配额。

```python
RawExportStore.spool_bytes
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

int。

#### 异常说明

无，不含BLF或发布副本。

源码：[`src/chronaxis/results/raw_exports.py:243`](../../../src/chronaxis/results/raw_exports.py#L243)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RawExportStore-_require"></a>
### `RawExportStore._require`

检查活状态，半关闭或失败前缀不能继续使用。

```python
RawExportStore._require(state)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`state`|str|是|无|位置或关键字。期望的仓状态："building"表示仍可追加记录，"sealed"表示已经结束写入、可以回读；当前状态不匹配时报错。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ResultClosedError/RuntimeError。

本函数直接报告的具体错误：

- `ResultClosedError`：原始导出仓已关闭或正在清理。

源码：[`src/chronaxis/results/raw_exports.py:247`](../../../src/chronaxis/results/raw_exports.py#L247)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RawExportStore-_fail"></a>
### `RawExportStore._fail`

保原主错/取消、failed状态和最高恢复owner，清理副错只记note。

```python
RawExportStore._fail(exc)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`exc`|BaseException|是|无|位置或关键字。本次操作的原异常，供附加关闭失败信息并保留原因链。不要用错误字符串代替异常对象。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

清理错误不替代原exc。

源码：[`src/chronaxis/results/raw_exports.py:257`](../../../src/chronaxis/results/raw_exports.py#L257)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RawExportStore-next_path"></a>
### `RawExportStore.next_path`

计算当前记录对应BLF路径，不创建文件、不跳过无观测索引。

```python
RawExportStore.next_path()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

根/raw_segments/{record_count:012d}.blf。

#### 异常说明

状态错误或索引超过12位能力；原writer由调用方独立持有和关闭。

源码：[`src/chronaxis/results/raw_exports.py:266`](../../../src/chronaxis/results/raw_exports.py#L266)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RawExportStore-_relation"></a>
### `RawExportStore._relation`

核本仓归属和连续索引，不从文件名猜来源。

```python
RawExportStore._relation(record, index)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`record`|[RawExportRecord](chronaxis.results.raw_exports.md#api-RawExportRecord)|是|无|位置或关键字。record为冻结记录|
|`index`|int|是|无|位置或关键字。当前记录或文件槽的序号，从0开始，按原有顺序定位。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError。

本函数直接报告的具体错误：

- `TypeError`：原始导出仓仅接受RawExportRecord。
- `ValueError`：原始导出记录索引/来源/会话/设备不属于本仓。

源码：[`src/chronaxis/results/raw_exports.py:276`](../../../src/chronaxis/results/raw_exports.py#L276)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RawExportStore-_close_fd"></a>
### `RawExportStore._close_fd`

真实FD关闭后才撤槽，关闭后抛错也依据actual.closed处理。

```python
RawExportStore._close_fd(slot)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`slot`|str|是|无|位置或关键字。当前对象中用于保存资源或其费用的属性名，例如"_row_cost"；只能指向本对象实际管理的项。释放成功后才清空对应项。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原close/取消，持续失败可重试。

源码：[`src/chronaxis/results/raw_exports.py:287`](../../../src/chronaxis/results/raw_exports.py#L287)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RawExportStore-_file"></a>
### `RawExportStore._file`

有限块核实际BLF；可同时复制到独占目标，不调用任何CAN读写器。

```python
RawExportStore._file(record, destination=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`record`|[RawExportRecord](chronaxis.results.raw_exports.md#api-RawExportRecord)|是|无|位置或关键字。状态为exported的导出记录，包含文件路径、字节数和SHA-256。|
|`destination`|[pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) &#124; None|否|None|位置或关键字。复制输出的新文件；None只检查原导出文件，不执行复制。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原预算/IO/取消或ResultFormatError；所有当前FD仍从本store可达。

本函数直接报告的具体错误：

- `ResultClosedError`：原始导出仓有未完成文件资源待清理。

源码：[`src/chronaxis/results/raw_exports.py:300`](../../../src/chronaxis/results/raw_exports.py#L300)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RawExportStore-_check_copy"></a>
### `RawExportStore._check_copy`

在已预约IO空间内回读真实发布文件，BLF与索引使用同一有界验证。

```python
RawExportStore._check_copy(path, expected_bytes, expected_sha)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|[pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。本次刚复制出的目标文件，重新读取并核对字节数和摘要。|
|`expected_bytes`|int|是|无|位置或关键字。结束写入时记录的原文件字节数，复制后必须完全一致。|
|`expected_sha`|str|是|无|位置或关键字。结束写入时记录的原文件SHA-256，复制后必须完全一致。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原打开/read/close/取消或ResultFormatError；当前真实FD留在本owner槽。

本函数直接报告的具体错误：

- `ResultClosedError`：发布文件回读需空输入槽和已预约IO空间。
- `ResultFormatError`：发布文件字节数或SHA与封口事实不符。
- `ResultFormatError`：发布文件字节数超过封口事实。

源码：[`src/chronaxis/results/raw_exports.py:345`](../../../src/chronaxis/results/raw_exports.py#L345)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RawExportStore-append"></a>
### `RawExportStore.append`

预付索引RAM/累计spool，核实际文件后完整写一行再推进计数。

```python
RawExportStore.append(record)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`record`|[RawExportRecord](chronaxis.results.raw_exports.md#api-RawExportRecord)|是|无|位置或关键字。record为本仓当前索引的RawExportRecord。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原归属/预算/文件/编码/取消；开始后的失败poison，原BLF费用不重复预约。

源码：[`src/chronaxis/results/raw_exports.py:368`](../../../src/chronaxis/results/raw_exports.py#L368)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RawExportStore-seal"></a>
### `RawExportStore.seal`

真实关闭索引writer并固定流SHA；零记录亦可封口。

```python
RawExportStore.seal()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原flush/close/取消，失败不能冒充sealed。

源码：[`src/chronaxis/results/raw_exports.py:398`](../../../src/chronaxis/results/raw_exports.py#L398)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RawExportStore-iter_records"></a>
### `RawExportStore.iter_records`

创建有限独立索引reader，未返回构造始终在本父pending槽可达。

```python
RawExportStore.iter_records()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

逐条RawExportRecord迭代器。

#### 异常说明

原预算/打开/登记/取消及状态错误。

本函数直接报告的具体错误：

- `ResultClosedError`：原始导出仓有未返回reader待清理。

源码：[`src/chronaxis/results/raw_exports.py:412`](../../../src/chronaxis/results/raw_exports.py#L412)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RawExportStore-copy_to"></a>
### `RawExportStore.copy_to`

向新发布根独占创建原始目录与索引，逐条核验复制现成BLF。

```python
RawExportStore.copy_to(destination)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`destination`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。destination为Path|

#### 返回说明

目标raw_segments.jsonl Path。

#### 异常说明

原路径/预算/IO/取消或完整性错误；
    输出失败保本次FD责任及部分文件，不覆盖已有工件或关闭sealed输入；
    入口先恢复上次复制，持续关闭失败时不得覆盖旧槽或创建下个目标。

源码：[`src/chronaxis/results/raw_exports.py:428`](../../../src/chronaxis/results/raw_exports.py#L428)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RawExportStore-recover_copy"></a>
### `RawExportStore.recover_copy`

仅恢复上次输出复制的真实责任，保sealed固定输入及其他独立reader。

```python
RawExportStore.recover_copy()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None；copy_to入口会自动调用，调用方也可显式恢复。

#### 异常说明

原FD/reader/费用关闭错误或状态错误；持续失败保最高store与原槽，
    不把整个输入仓置关闭中，不覆盖上次复制尚未释放的资源。

源码：[`src/chronaxis/results/raw_exports.py:488`](../../../src/chronaxis/results/raw_exports.py#L488)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RawExportStore-_close_copy_resources"></a>
### `RawExportStore._close_copy_resources`

关闭本次copy子reader和FD，完全释放后再清当前缓冲与复制费用。

```python
RawExportStore._close_copy_resources()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None；不操作固定费、原索引writer或其他独立reader。

#### 异常说明

首个真实关闭/抵销错误，副错记note；最高store保存未完成实际槽。

源码：[`src/chronaxis/results/raw_exports.py:498`](../../../src/chronaxis/results/raw_exports.py#L498)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RawExportStore-close"></a>
### `RawExportStore.close`

关闭全部自有FD/reader并抵销自有RAM，文件与累计spool保留。

```python
RawExportStore.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None，完成后幂等。

#### 异常说明

首个真实关闭/抵销错误，副错记note；
    持续故障保原槽/最高owner，不能从共用的资源用量记录总额倒推或多扣费用。

源码：[`src/chronaxis/results/raw_exports.py:535`](../../../src/chronaxis/results/raw_exports.py#L535)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_RawExportReader"></a>
## `_RawExportReader`

拥有单个索引位置/摘要和固定读槽；完整EOF与成功关闭才verified_eof。

copy模式只把临时资源错误交本次复制恢复，输入格式/摘要破坏仍poison父仓。

```python
_RawExportReader(owner, *, copy=False)
```


源码：[`src/chronaxis/results/raw_exports.py:588`](../../../src/chronaxis/results/raw_exports.py#L588)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_RawExportReader-__init__"></a>
### `_RawExportReader.__init__`

先装父pending槽，再付费打开/登记真实reader。

```python
_RawExportReader.__init__(owner, *, copy=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|[RawExportStore](chronaxis.results.raw_exports.md#api-RawExportStore)|是|无|位置或关键字。已经结束写入、仍处于打开状态的导出记录仓。|
|`copy`|bool|否|False|仅关键字。copy为内部临时复制模式，直接先装父_copy_reader槽。|

#### 返回说明

独立reader。

#### 异常说明

原预算/打开/登记/取消；真实父槽始终保未返回self。

源码：[`src/chronaxis/results/raw_exports.py:594`](../../../src/chronaxis/results/raw_exports.py#L594)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_RawExportReader-__iter__"></a>
### `_RawExportReader.__iter__`

保持独立原位置。

```python
_RawExportReader.__iter__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回当前对象本身。后续迭代或with语句使用的仍是同一个对象。

#### 异常说明

无，不重新开文件。

源码：[`src/chronaxis/results/raw_exports.py:622`](../../../src/chronaxis/results/raw_exports.py#L622)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_RawExportReader-__next__"></a>
### `_RawExportReader.__next__`

逐行校索引归属/序号，真实EOF核完整SHA、条数、文件数与字节数后关闭。

```python
_RawExportReader.__next__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

RawExportRecord。

#### 异常说明

真实StopIteration或原格式/关闭/取消；
    输入损坏poison父；copy临时资源失败交本次恢复，原异常/取消对象保持。

本函数直接报告的具体错误：

- `ResultClosedError`：原始导出reader正在清理。
- `ResultFormatError`：原始导出索引EOF数量或SHA不匹配。
- `ResultFormatError`：原始导出索引行超限或缺完整换行。
- `ResultFormatError`：原始导出索引出现额外后缀。
- `ResultFormatError`：原始导出索引归属或序号非法。

源码：[`src/chronaxis/results/raw_exports.py:626`](../../../src/chronaxis/results/raw_exports.py#L626)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_RawExportReader-close"></a>
### `_RawExportReader.close`

真实关FD、抵销本笔费用并解除父登记后才closed，可持续重试。

```python
_RawExportReader.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原close/预算/取消；最高store仍持本实例。

源码：[`src/chronaxis/results/raw_exports.py:667`](../../../src/chronaxis/results/raw_exports.py#L667)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
