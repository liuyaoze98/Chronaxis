# `chronaxis.fast.can_io`

修复版 ChrgInfo 文件循环：先选 ID，再解码一次并更新该帧的全部公式。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)

## 对象导航

|对象|用途|
|---|---|
|[`_Group`](#api-_Group)|同一实际报文类型共享一次解码。只有已请求的公式进入该组。|
|[`_prepare`](#api-_prepare)|按选择器预建 ID 索引并为每项新建累计器。缺字段或歧义在开日志之前报告。|
|[`_read_all`](#api-_read_all)|完整读入本文件；批量任务每 4096 帧检查一次取消，reader 由调用方关闭。|
|[`_read`](#api-_read)|与 base 一样按文件读入并确定关闭。ASC 保留文本解析所得的精确纳秒。|
|[`_read.selected_time`](#api-_read-selected_time)|只比较实际进入时间筛选的帧，其他通道或远程帧不改变前一时刻。|
|[`run_one`](#api-run_one)|执行一份已准备的任务并返回汇总行及兼容提示。任何文件错误均不返回部分指标。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass, field
from itertools import islice
from pathlib import Path
from types import SimpleNamespace
from ..legacy.binding import dbc_candidates, select_message
from ..legacy.decode_policy import check_decode_length
from ..timebase.conversion import convert_time, checked_add_ns
from .compute import prepare_metric
```

</details>

<a id="api-_Group"></a>
## `_Group`

同一实际报文类型共享一次解码。只有已请求的公式进入该组。

```python
class _Group
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`message`|cantools.database.can.Message|是|无|此组按实际帧型选用的 DBC 报文定义。|
|`entries`|list[tuple]|否|[]|该报文上的指标名、独立累计器及可选的已观测身份集合。|

源码：[`src/chronaxis/fast/can_io.py:18`](../../../src/chronaxis/fast/can_io.py#L18)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_prepare"></a>
## `_prepare`

按选择器预建 ID 索引并为每项新建累计器。缺字段或歧义在开日志之前报告。

```python
_prepare(spec, db)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|dict|是|无|位置或关键字。一个文件的已绑定参数，包括 DBC、通道、数值公式和输出单位。|
|`db`|cantools.database.Database|是|无|位置或关键字。已读入的 DBC，供按 ID、信号和帧型定位报文。|

源码：[`src/chronaxis/fast/can_io.py:28`](../../../src/chronaxis/fast/can_io.py#L28)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_read_all"></a>
## `_read_all`

完整读入本文件；批量任务每 4096 帧检查一次取消，reader 由调用方关闭。

```python
_read_all(reader, cancel_event)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`reader`|Iterable|是|无|位置或关键字。该文件的原始报文迭代器，关闭由外层负责。|
|`cancel_event`|Event &#124; None|是|无|位置或关键字。已设置时取消本次操作，省略时按调用方的正常生命周期运行。|

源码：[`src/chronaxis/fast/can_io.py:71`](../../../src/chronaxis/fast/can_io.py#L71)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_read"></a>
## `_read`

与 base 一样按文件读入并确定关闭。ASC 保留文本解析所得的精确纳秒。

```python
_read(path, groups, spec, cancel_event)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。要读取的文件路径。|
|`groups`|dict|是|无|位置或关键字。以报文 ID 和帧型索引本文件的计算项，供筛选目标及检查时间。|
|`spec`|dict|是|无|位置或关键字。一个文件的已绑定参数，包括 DBC、通道、数值公式和输出单位。|
|`cancel_event`|Event &#124; None|是|无|位置或关键字。已设置时取消本次操作，省略时按调用方的正常生命周期运行。|

源码：[`src/chronaxis/fast/can_io.py:85`](../../../src/chronaxis/fast/can_io.py#L85)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_read-selected_time"></a>
### `_read.selected_time`

只比较实际进入时间筛选的帧，其他通道或远程帧不改变前一时刻。

```python
_read.selected_time(frame)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`frame`|LegacyRawFrame|是|无|位置或关键字。ASC 中的当前帧，按通道、帧型和 ID 确认是否检查时间顺序。|

源码：[`src/chronaxis/fast/can_io.py:95`](../../../src/chronaxis/fast/can_io.py#L95)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-run_one"></a>
## `run_one`

执行一份已准备的任务并返回汇总行及兼容提示。任何文件错误均不返回部分指标。

```python
run_one(spec, database=None, *, cancel_event=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|dict|是|无|位置或关键字。一个文件的已绑定参数，包括 DBC、通道、数值公式和输出单位。|
|`database`|cantools.database.Database &#124; None|否|None|位置或关键字。预检时加载的 DBC，可交本次执行复用。|
|`cancel_event`|Event &#124; None|否|None|仅关键字。已设置时取消本次操作，省略时按调用方的正常生命周期运行。|

源码：[`src/chronaxis/fast/can_io.py:108`](../../../src/chronaxis/fast/can_io.py#L108)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
