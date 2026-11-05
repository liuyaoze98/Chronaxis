# `chronaxis.results.signal_exports`

将指定信号的已解码历史写为原始采样及可选连续量网格CSV长表。

输入为同次读取生成的HistorySample/HistoryProgress流及显式导出范围，不打开日志
或DBC；输出original.csv及清单，启用线性时另写resampled.csv。异步信号分别
一行，状态/计数不补点；显式连续量交给独立有界网格owner。
值无效时留空并保质量原因和完整来源引用；原无效值以既有安全编码保存。
逐行缓冲和编码先付预算，输入正常/失败/取消均关闭，整个目录最终独占发布。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ExportFiles](chronaxis.results.export_files.md#api-ExportFiles)、[HistoryProgress](chronaxis.execution.history_records.md#api-HistoryProgress)、[HistorySample](chronaxis.execution.history_records.md#api-HistorySample)、[Interval](chronaxis.core.models.md#api-Interval)、[RecordSample](chronaxis.execution.record_sample.md#api-RecordSample)、[SignalGrid](chronaxis.results.signal_grid.md#api-SignalGrid)、[SignalGridSpec](chronaxis.results.signal_grid.md#api-SignalGridSpec)

## 对象导航

|对象|用途|
|---|---|
|[`SignalCSVExportSpec`](#api-SignalCSVExportSpec)|指定待导出的已绑定别名；字段含义和单位沿用原绑定，不由文件名推断。|
|[`SignalCSVExportSpec.__post_init__`](#api-SignalCSVExportSpec-__post_init__)|只核静态选择。|
|[`_csv_bytes`](#api-_csv_bytes)|编码一个有界CSV行。|
|[`_sample_row`](#api-_sample_row)|提取原样本可读列及完整证据。|
|[`_reference_json`](#api-_reference_json)|编码实际端点引用。|
|[`_write_grid`](#api-_write_grid)|有界编码网格行及两端引用。|
|[`SignalCSVWriter`](#api-SignalCSVWriter)|复用原写文件和线性网格，支持逐样本推进而不强制暂存整份输入。|
|[`SignalCSVWriter.__init__`](#api-SignalCSVWriter-__init__)|预付输出状态并建立所需表。|
|[`SignalCSVWriter.push`](#api-SignalCSVWriter-push)|写一个已验证样本或推进原网格。|
|[`SignalCSVWriter.observed_end`](#api-SignalCSVWriter-observed_end)|在线调用方在末组交付前收紧EOF；不能用它改已经写出的记录。|
|[`SignalCSVWriter.complete`](#api-SignalCSVWriter-complete)|结束网格、写一次必要清单并原子发布。|
|[`export_signal_csv`](#api-export_signal_csv)|消费既有记录流并复用在线写出器，保原公开调用与关闭责任。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from io import StringIO
from ..core.models import Interval
from ..core.validation import require_identifier
from ..execution.record_sample import RecordSample
from ..execution.history_records import HistorySample, HistoryProgress, estimate_record_bytes
from ..execution.history import _metadata_bytes
from .budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from .codec import _pack
from .export_files import ExportFiles
from .signal_grid import SignalGridSpec, SignalGrid
```

</details>

<a id="api-SignalCSVExportSpec"></a>
## `SignalCSVExportSpec`

指定待导出的已绑定别名；字段含义和单位沿用原绑定，不由文件名推断。

```python
class SignalCSVExportSpec
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`signals`|tuple[str, ...]|是|无|唯一非空别名，最多4096，保持配置顺序。|
|`resampling`|[SignalGridSpec](chronaxis.results.signal_grid.md#api-SignalGridSpec) &#124; None|否|None|默认原始采样，显式连续量才进入线性网格。|

源码：[`src/chronaxis/results/signal_exports.py:27`](../../../src/chronaxis/results/signal_exports.py#L27)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SignalCSVExportSpec-__post_init__"></a>
### `SignalCSVExportSpec.__post_init__`

只核静态选择。

```python
SignalCSVExportSpec.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

类型/数量/重复或非法别名。

本函数直接报告的具体错误：

- `ValueError`：信号CSV需要1到4096个显式别名。
- `ValueError`：信号CSV别名重复。
- `ValueError`：重采样必须是所选信号的明确子集。

源码：[`src/chronaxis/results/signal_exports.py:33`](../../../src/chronaxis/results/signal_exports.py#L33)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_csv_bytes"></a>
## `_csv_bytes`

编码一个有界CSV行。

```python
_csv_bytes(values)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`values`|list|是|无|位置或关键字。values有限标量列表。|

### 返回说明

UTF8 bytes。

### 异常说明

CSV/Unicode/内存错。

源码：[`src/chronaxis/results/signal_exports.py:51`](../../../src/chronaxis/results/signal_exports.py#L51)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_sample_row"></a>
## `_sample_row`

提取原样本可读列及完整证据。

```python
_sample_row(sample, compact=False)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`sample`|[HistorySample](chronaxis.execution.history_records.md#api-HistorySample)|是|无|位置或关键字。sample已校验HistorySample。|
|`compact`|bool|否|False|位置或关键字。控制信号表列和来源明细。True使用摘要列time_ns、signal、value、unit、quality；False保留原始值和来源定位等详细列。重采样行仍保留status/reason；默认False。|

### 返回说明

行tuple。

### 异常说明

安全编码错。

源码：[`src/chronaxis/results/signal_exports.py:60`](../../../src/chronaxis/results/signal_exports.py#L60)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_reference_json"></a>
## `_reference_json`

编码实际端点引用。

```python
_reference_json(sample)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`sample`|[HistorySample](chronaxis.execution.history_records.md#api-HistorySample) &#124; None|是|无|位置或关键字。实际信号历史样本，提取其中来源定位；None表示该端没有实际样本。|

### 返回说明

JSON文本或空字符串。

### 异常说明

安全编码错。

源码：[`src/chronaxis/results/signal_exports.py:74`](../../../src/chronaxis/results/signal_exports.py#L74)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_write_grid"></a>
## `_write_grid`

有界编码网格行及两端引用。

```python
_write_grid(owner, rows, counts, compact=False)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|[ExportFiles](chronaxis.results.export_files.md#api-ExportFiles)|是|无|位置或关键字。当前导出文件管理器，提供CSV及质量说明文件句柄。|
|`rows`|Iterable[GridRow]|是|无|位置或关键字。已生成的信号网格行，逐行写入数值和质量说明。|
|`counts`|dict|是|无|位置或关键字。按observed、estimated、missing计数的字典；每写一行就增加相应项，原地更新。|
|`compact`|bool|否|False|位置或关键字。控制重采样行是否附带两端样本证据：True省略left/right时间与来源列，False附带；数值、状态和原因两种模式都保留。|

### 返回说明

返回None，不返回额外的计算值。

### 异常说明

编码/预算/I/O/取消错。

源码：[`src/chronaxis/results/signal_exports.py:81`](../../../src/chronaxis/results/signal_exports.py#L81)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SignalCSVWriter"></a>
## `SignalCSVWriter`

复用原写文件和线性网格，支持逐样本推进而不强制暂存整份输入。

```python
SignalCSVWriter(spec, interval, destination, budget, *, device_label, check_cancel=None, definitions=(), backend='numpy', compact=False, integrity=True, timestamped=False)
```

继承关系：[ExportFiles](chronaxis.results.export_files.md#api-ExportFiles)。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/results/signal_exports.py:101`](../../../src/chronaxis/results/signal_exports.py#L101)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SignalCSVWriter-__init__"></a>
### `SignalCSVWriter.__init__`

预付输出状态并建立所需表。

```python
SignalCSVWriter.__init__(spec, interval, destination, budget, *, device_label, check_cancel=None, definitions=(), backend='numpy', compact=False, integrity=True, timestamped=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|[SignalCSVExportSpec](chronaxis.results.signal_exports.md#api-SignalCSVExportSpec)|是|无|位置或关键字。信号CSV列和可选网格声明；必须是已核对的导出spec，不是包含scope的外层Output对象。|
|`interval`|[Interval](chronaxis.core.models.md#api-Interval)|是|无|位置或关键字。要处理的实际半开时间范围，包含start_ns而不包含end_ns之后的时长。|
|`destination`|str &#124; Path|是|无|位置或关键字。本次新输出路径，已有目标不能覆盖；不能位于只读历史目录。|
|`budget`|ResourceBudget|是|无|位置或关键字。本次分析共享的资源用量记录；新对象先预约所需内存和磁盘额度，关闭时归还自己的内存费用。|
|`device_label`|str|是|无|仅关键字。记录本次导出的设备来源标签；当前这个导出入口只接受home或work，pending会被拒绝。标签应来自已确认的执行设备映射，不从输入路径推断。|
|`check_cancel`|Callable[[], None] &#124; None|否|None|仅关键字。可选取消检查函数；正常返回None，需要中止时抛异常，原错误继续传播。|
|`definitions`|Mapping[str, SignalDefinition]|否|()|仅关键字。以信号别名为键的定义，提供来源、类型、单位和有效期；不会在这里重新加载DBC。|
|`backend`|str|否|'numpy'|仅关键字。计算实现：reference使用独立参考核，numpy使用数组核；两者遵守相同的业务和缺失数据规则。|
|`compact`|bool|否|False|仅关键字。控制信号表列和来源明细。True使用摘要列time_ns、signal、value、unit、quality；False保留原始值和来源定位等详细列。重采样行仍保留status/reason；默认False。|
|`integrity`|bool|否|True|仅关键字。是否执行本对象的额外内容摘要或认证核验；False仍保留结构、类型、预算及必要文件变化检查。|
|`timestamped`|bool|否|False|仅关键字。是否使用公开导出的时间文件名；内部file_consumer模式保持独占目录，调用封装按模式设置。|

#### 返回说明

owner。

#### 异常说明

原构造错。

源码：[`src/chronaxis/results/signal_exports.py:104`](../../../src/chronaxis/results/signal_exports.py#L104)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SignalCSVWriter-push"></a>
### `SignalCSVWriter.push`

写一个已验证样本或推进原网格。

```python
SignalCSVWriter.push(sample)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`sample`|[RecordSample](chronaxis.execution.record_sample.md#api-RecordSample)|是|无|位置或关键字。当前一条已归一化的所需信号更新，含实际时间、值及有效状态。|

#### 返回说明

None。

#### 异常说明

原输入/写入错。

源码：[`src/chronaxis/results/signal_exports.py:140`](../../../src/chronaxis/results/signal_exports.py#L140)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SignalCSVWriter-observed_end"></a>
### `SignalCSVWriter.observed_end`

在线调用方在末组交付前收紧EOF；不能用它改已经写出的记录。

```python
SignalCSVWriter.observed_end(end_ns)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`end_ns`|int|是|无|位置或关键字。本次查询或计算的实际结束时刻，单位纳秒；按具体函数保留必要右端点供半开范围计算。|

#### 返回说明

None。

#### 异常说明

越界。

源码：[`src/chronaxis/results/signal_exports.py:161`](../../../src/chronaxis/results/signal_exports.py#L161)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SignalCSVWriter-complete"></a>
### `SignalCSVWriter.complete`

结束网格、写一次必要清单并原子发布。

```python
SignalCSVWriter.complete()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

输出Path。

#### 异常说明

原完成错。

源码：[`src/chronaxis/results/signal_exports.py:171`](../../../src/chronaxis/results/signal_exports.py#L171)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-export_signal_csv"></a>
## `export_signal_csv`

消费既有记录流并复用在线写出器，保原公开调用与关闭责任。

```python
export_signal_csv(records, spec, interval, destination, budget, *, device_label, check_cancel=None, definitions=(), backend='numpy', compact=False, integrity=True, file_consumer=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`records`|可关闭的历史记录迭代器|是|无|位置或关键字。同次读取生成的历史记录流，按顺序导出并关闭，不重新读取原始日志。|
|`spec`|[SignalCSVExportSpec](chronaxis.results.signal_exports.md#api-SignalCSVExportSpec)|是|无|位置或关键字。spec选择|
|`interval`|[Interval](chronaxis.core.models.md#api-Interval)|是|无|位置或关键字。interval半开范围|
|`destination`|str &#124; [pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。可重复使用的导出目录；公开直接调用生成带统一时间后缀的文件，内部file_consumer交接仍使用独占目录。|
|`budget`|ResourceBudget|是|无|位置或关键字。本次运行共用的ResourceBudget对象，用于检查内存和临时磁盘用量。当前对象在分配前申请额度，用完后归还；同一次运行的组件应使用同一个对象。|
|`device_label`|str|是|无|仅关键字。记录本次导出的设备来源标签；当前这个导出入口只接受home或work，pending会被拒绝。标签应来自已确认的执行设备映射，不从输入路径推断。|
|`check_cancel`|Callable[[], None] &#124; None|否|None|仅关键字。可选的无参取消检查函数。需要终止时由它抛出异常；None表示不额外调用取消检查。|
|`definitions`|tuple[SignalDefinition, ...]|否|()|仅关键字。导出信号在原绑定中的定义，提供类型、单位和有效期，供可选重采样使用。|
|`backend`|str|否|'numpy'|仅关键字。`"reference"`使用独立参考计算；`"numpy"`使用NumPy数组计算。须明确选择一种。|
|`compact`|bool|否|False|仅关键字。控制信号表列和来源明细。True使用摘要列time_ns、signal、value、unit、quality；False保留原始值和来源定位等详细列。重采样行仍保留status/reason；默认False。|
|`integrity`|bool|否|True|仅关键字。是否执行本对象的额外内容摘要或认证核验；False仍保留结构、类型、预算及必要文件变化检查。|
|`file_consumer`|Callable &#124; None|否|None|仅关键字。可选内部回调，接收已关闭并发布的至多16个文件写入事实；用于登记复用，不重新扫描内容。|

### 返回说明

公开直接调用返回ExportManifest，包含output_dir、manifest_path及output_files。不要把返回值直接当Path；通过这些属性取得实际文件。内部file_consumer交接返回原Path。

### 异常说明

声明/历史/I/O/预算/取消错误；持续关闭失败附export_cleanup_owner可重试。

本函数直接报告的具体错误：

- `TypeError`：信号导出需要选择及明确Interval。
- `ValueError`：导出需要实际设备标签及可选取消回调。
- `TypeError`：信号导出只接受已解码历史记录。

源码：[`src/chronaxis/results/signal_exports.py:191`](../../../src/chronaxis/results/signal_exports.py#L191)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
