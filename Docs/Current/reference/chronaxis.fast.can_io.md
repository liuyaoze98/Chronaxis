# `chronaxis.fast.can_io`

修复版 ChrgInfo 文件循环：先选 ID，再解码一次并更新该帧的全部公式。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)

## 对象导航

|对象|用途|
|---|---|
|[`_Group`](#api-_Group)|同一实际报文类型共享一次解码。只有已请求的公式进入该组。|
|[`_prepare`](#api-_prepare)|预建 ID 索引及每文件状态；内部已编译路径仅绑定指令，低层默认检查文本。|
|[`run_one`](#api-run_one)|流式运行单文件低层入口，保留原调用的行及提示返回结构。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass, field
from itertools import islice
from pathlib import Path
from types import SimpleNamespace
from ..legacy.binding import dbc_candidates, select_message
from ..legacy.decode_policy import check_decode_length
from ..timebase.conversion import convert_time, checked_add_ns
from .compute import prepare_metric, _prepare_program_metric
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

源码：[`src/chronaxis/fast/can_io.py:18`](../../../src/chronaxis/fast/can_io.py#L18)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_prepare"></a>
## `_prepare`

预建 ID 索引及每文件状态；内部已编译路径仅绑定指令，低层默认检查文本。

参数为声明、DBC及内部准备状态。返回组索引和累计器；字段、歧义或公式错误
在开日志前抛出。准备状态由调用链传入，不从用户配置或 spec 标志中读取。

```python
_prepare(spec, db, *, _programs_checked=False)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|dict|是|无|位置或关键字。一个文件的已绑定参数，包括 DBC、通道、数值公式和输出单位。|
|`db`|cantools.database.Database|是|无|位置或关键字。已读入的 DBC，供按 ID、信号和帧型定位报文。|
|`_programs_checked`|bool|否|False|仅关键字。仅由内部调用传入的公式已检查标志；默认 False，普通入口仍核对原始公式和指令，不读取配置中的同名值。|

源码：[`src/chronaxis/fast/can_io.py:28`](../../../src/chronaxis/fast/can_io.py#L28)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-run_one"></a>
## `run_one`

流式运行单文件低层入口，保留原调用的行及提示返回结构。

```python
run_one(spec, database=None, *, cancel_event=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|dict|是|无|位置或关键字。一个文件的已绑定参数，包括 DBC、通道、数值公式和输出单位。|
|`database`|cantools.database.Database &#124; None|否|None|位置或关键字。预检时加载的 DBC，可交本次执行复用。|
|`cancel_event`|Event &#124; None|否|None|仅关键字。已设置时取消本次操作，省略时按调用方的正常生命周期运行。|

### 返回说明

(汇总行list, 提示list)。

### 异常说明

读取/解码/数值/取消错误。

源码：[`src/chronaxis/fast/can_io.py:76`](../../../src/chronaxis/fast/can_io.py#L76)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
