# chronaxis.legacy.vendor.sclicer_functions_v1.file_processor

冻结的Sclicer文件遍历与writer工厂。读取原日志并产生旧Message对象；Chronaxis外部封装将受支持的BLF消息送入分析层。该文件里存在的格式分支不表示公共AnalysisRunner支持所有格式。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`iter_frames`](#api-iter_frames)|该函数是一个统一的生成器，用于按时间顺序逐个生成 can.Message 对象。|
|[`check_csv_header`](#api-check_csv_header)|前置检查：csv必须含timestamp/arbitration_id/data三列，缺失则抛异常|
|[`merge_convert`](#api-merge_convert)|合并输入文件/文件夹→指定格式，csv前置检查|
|[`output_suffix`](#api-output_suffix)|生成带时间戳的输出基础名|
|[`fix_asc_header`](#api-fix_asc_header)|修复ASC文件头部时间信息|

<details><summary>导入与重导出来源（展开）</summary>

```python
from datetime import datetime, timedelta
from natsort import natsorted
from utils import ASCReaderForCANFD
```

</details>

<a id="api-iter_frames"></a>
## `iter_frames`

该函数是一个统一的生成器，用于按时间顺序逐个生成 can.Message 对象。
支持处理单个文件或整个文件夹，具体功能如下：

1. 当输入为单个文件时：
   - 检查文件扩展名，仅支持 .blf、.asc 和 .csv 格式
   - 若为 .blf 文件，使用 can.BLFReader 读取并生成消息
   - 若为 .asc 文件，使用 can.ASCReader 读取并生成消息
   - 若为 .csv 文件，使用 can.CSVReader 读取并生成消息
   - 若文件格式不支持，抛出 ValueError 异常

2. 当输入为文件夹时：
   - 筛选出文件夹内所有 .blf、.asc 和 .csv 文件，并按自然排序
   - 递归调用本函数处理每个文件，逐个生成消息

3. 若输入既不是文件也不是文件夹，抛出 FileNotFoundError 异常

```python
iter_frames(path)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|str|是|无|位置或关键字。输入的文件路径或文件夹路径|

### 返回说明

generator: 按时间顺序生成 can.Message 对象的生成器

### 异常说明

ValueError: 当输入文件的格式不是 .blf、.asc 或 .csv 时抛出
FileNotFoundError: 当输入路径既不是文件也不是文件夹时抛出

源码：[`src/chronaxis/legacy/vendor/sclicer_functions_v1/file_processor.py:13`](../../../src/chronaxis/legacy/vendor/sclicer_functions_v1/file_processor.py#L13)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-check_csv_header"></a>
## `check_csv_header`

前置检查：csv必须含timestamp/arbitration_id/data三列，缺失则抛异常

```python
check_csv_header(file_path)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`file_path`|str|是|无|位置或关键字。csv文件路径|

### 返回说明

bool: 若文件头包含timestamp/arbitration_id/data三列则返回True

### 异常说明

ValueError: 当文件头缺失timestamp/arbitration_id/data三列时抛出

源码：[`src/chronaxis/legacy/vendor/sclicer_functions_v1/file_processor.py:65`](../../../src/chronaxis/legacy/vendor/sclicer_functions_v1/file_processor.py#L65)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-merge_convert"></a>
## `merge_convert`

合并输入文件/文件夹→指定格式，csv前置检查

```python
merge_convert(inputs, out_base, out_fmt, db)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`inputs`|list|是|无|位置或关键字。输入文件/文件夹路径列表|
|`out_base`|str|是|无|位置或关键字。输出文件基础名（不含扩展名）|
|`out_fmt`|str|是|无|位置或关键字。输出格式，可选"blf"/"asc"/"csv"|
|`db`|can.Database|是|无|位置或关键字。数据库对象，用于解析报文|

### 返回说明

返回None，不返回额外的计算值。

### 异常说明

ValueError: 当输入文件为csv格式且缺失timestamp/id/data三列时抛出
FileNotFoundError: 当输入路径既不是文件也不是文件夹时抛出

源码：[`src/chronaxis/legacy/vendor/sclicer_functions_v1/file_processor.py:85`](../../../src/chronaxis/legacy/vendor/sclicer_functions_v1/file_processor.py#L85)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-output_suffix"></a>
## `output_suffix`

生成带时间戳的输出基础名

```python
output_suffix(path)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|str|是|无|位置或关键字。输入文件路径（不含扩展名）|

### 返回说明

str: 带时间戳的输出基础名（不含扩展名）

源码：[`src/chronaxis/legacy/vendor/sclicer_functions_v1/file_processor.py:120`](../../../src/chronaxis/legacy/vendor/sclicer_functions_v1/file_processor.py#L120)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-fix_asc_header"></a>
## `fix_asc_header`

修复ASC文件头部时间信息
将文件前4行从：
date Tue Oct 14 16:11:16.648 2025
base hex  timestamps absolute
internal events logged
Begin Triggerblock Tue Jun 10 22:35:34.949 2025

变为：
date Tue Jun 10 22:35:34.949 2025
base hex  timestamps absolute

```python
fix_asc_header(file_path, utc_offset=0)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`file_path`|str|是|无|位置或关键字。ASC文件路径|
|`utc_offset`|int|否|0|位置或关键字。UTC偏移量(小时)，如果为x，则从date时间减去x小时|

### 返回说明

返回None，不返回额外的计算值。

源码：[`src/chronaxis/legacy/vendor/sclicer_functions_v1/file_processor.py:133`](../../../src/chronaxis/legacy/vendor/sclicer_functions_v1/file_processor.py#L133)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
