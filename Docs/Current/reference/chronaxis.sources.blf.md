# `chronaxis.sources.blf`

将既有python-can BLFReader接入有序混合来源；不重新实现BLF格式解析。

只保留当前报文，DBC由混合来源共用一次。账本计入本层对象；第三方解压器内部
分配与原BLF路径一样不代表硬RSS上限。不扫描文件、不补日期、不改原帧字段。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CANTextError](chronaxis.sources.raw_can.md#api-CANTextError)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[RawCANRecord](chronaxis.sources.raw_can.md#api-RawCANRecord)

## 对象导航

|对象|用途|
|---|---|
|[`BLFSpec`](#api-BLFSpec)|单文件BLF声明；offset_ns仅平移分析坐标，原timestamp不改。|
|[`BLFSpec.__post_init__`](#api-BLFSpec-__post_init__)|核对静态路径与偏移，不打开输入。失败抛类型或范围错误。|
|[`BLFRead`](#api-BLFRead)|持有一个真实BLFReader与当前迭代器，EOF、失败、取消均关闭本次文件。|
|[`BLFRead.__init__`](#api-BLFRead-__init__)|参数为单文件声明、共用的资源用量记录及按需选择；返回reader；失败附恢复owner。|
|[`BLFRead.closed`](#api-BLFRead-closed)|返回本层所有文件和费用是否已释放。|
|[`BLFRead.__iter__`](#api-BLFRead-__iter__)|返回同次迭代器，不重复打开文件。|
|[`BLFRead.__next__`](#api-BLFRead-__next__)|读取下一实际帧，先按ID选择再转换；失败保原异常并清理。|
|[`BLFRead.close`](#api-BLFRead-close)|关闭本次库迭代器和文件再释放费用；失败保留owner以便重试。|
|[`_UntimedBLFRecord`](#api-_UntimedBLFRecord)|内部按需消息：保存真实输入身份与载荷，明确没有采集分析时间，禁止原帧导出。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from pathlib import Path
from ..legacy.worker import _frame
from ..results.budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..timebase.conversion import convert_time, checked_add_ns, require_int64_ns
from .raw_can import RawCANRecord, CANTextError
```

</details>

<a id="api-BLFSpec"></a>
## `BLFSpec`

单文件BLF声明；offset_ns仅平移分析坐标，原timestamp不改。

```python
class BLFSpec
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|输入.blf文件的Path，初始化只检查声明，不打开文件。|
|`offset_ns`|int|否|0|分析坐标偏移，默认0纳秒；保留原始报文时间。|

源码：[`src/chronaxis/sources/blf.py:16`](../../../src/chronaxis/sources/blf.py#L16)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-BLFSpec-__post_init__"></a>
### `BLFSpec.__post_init__`

核对静态路径与偏移，不打开输入。失败抛类型或范围错误。

```python
BLFSpec.__post_init__()
```

参数：无显式参数。


源码：[`src/chronaxis/sources/blf.py:21`](../../../src/chronaxis/sources/blf.py#L21)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-BLFRead"></a>
## `BLFRead`

持有一个真实BLFReader与当前迭代器，EOF、失败、取消均关闭本次文件。

```python
BLFRead(spec, budget, *, check_cancel=None, retain_original=False, retain_source_time=False, selected_ids=None, emit_frame_ids=None, channel=None, projection_only=False, time_check_all=False, time_scope='source')
```


源码：[`src/chronaxis/sources/blf.py:28`](../../../src/chronaxis/sources/blf.py#L28)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-BLFRead-__init__"></a>
### `BLFRead.__init__`

参数为单文件声明、共用的资源用量记录及按需选择；返回reader；失败附恢复owner。

```python
BLFRead.__init__(spec, budget, *, check_cancel=None, retain_original=False, retain_source_time=False, selected_ids=None, emit_frame_ids=None, channel=None, projection_only=False, time_check_all=False, time_scope='source')
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|[BLFSpec](chronaxis.sources.blf.md#api-BLFSpec)|是|无|位置或关键字。单文件路径与分析时间偏移；原帧时间不被改写。|
|`budget`|ResourceBudget|是|无|位置或关键字。本次运行共享的受管理资源用量记录。|
|`check_cancel`|Callable &#124; None|否|None|仅关键字。取消检查回调；为None时无外部检查，回调异常原样退出并清理。|
|`retain_original`|bool|否|False|仅关键字。沿用原帧读取接口选项，当前实现按实际帧返回，不额外复制全文件。|
|`retain_source_time`|bool|否|False|仅关键字。True在记录中保留原时间；False不构造额外时间字段。|
|`selected_ids`|set[int] &#124; None|否|None|仅关键字。仅处理这些CAN ID；None不过滤，在转换时间和记录对象前先筛ID。|
|`emit_frame_ids`|tuple[int, ...] &#124; None|否|None|仅关键字。限定实际交付的报文ID集合。None交付全部已解析帧；筛选不自动缩小任务要求的时间检查和观测范围。|
|`channel`|int &#124; None|否|None|仅关键字。投影需要的内部零基通道，来自已解析来源声明；不用文件名推断。|
|`projection_only`|bool|否|False|仅关键字。True允许在auto路径只为目标帧建立完整模型；必须同时提供emit_frame_ids，其他情况下保留普通解析。|
|`time_check_all`|bool|否|False|仅关键字。True要求投影前检查全来源记录顺序；False由目标记录检查决定，不能掩盖上层明确要求的完整检查。|
|`time_scope`|str|否|'source'|仅关键字。纯BLF按需时间范围：source检查并观测全部记录；selected只采目标时间；none明确不采时间，仅用于无需时间的逐消息累计。时间归并不能使用none。|

源码：[`src/chronaxis/sources/blf.py:31`](../../../src/chronaxis/sources/blf.py#L31)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-BLFRead-closed"></a>
### `BLFRead.closed`

返回本层所有文件和费用是否已释放。

```python
BLFRead.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


源码：[`src/chronaxis/sources/blf.py:70`](../../../src/chronaxis/sources/blf.py#L70)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-BLFRead-__iter__"></a>
### `BLFRead.__iter__`

返回同次迭代器，不重复打开文件。

```python
BLFRead.__iter__()
```

参数：无显式参数。


源码：[`src/chronaxis/sources/blf.py:74`](../../../src/chronaxis/sources/blf.py#L74)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-BLFRead-__next__"></a>
### `BLFRead.__next__`

读取下一实际帧，先按ID选择再转换；失败保原异常并清理。

```python
BLFRead.__next__()
```

参数：无显式参数。


源码：[`src/chronaxis/sources/blf.py:78`](../../../src/chronaxis/sources/blf.py#L78)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-BLFRead-close"></a>
### `BLFRead.close`

关闭本次库迭代器和文件再释放费用；失败保留owner以便重试。

```python
BLFRead.close()
```

参数：无显式参数。


源码：[`src/chronaxis/sources/blf.py:124`](../../../src/chronaxis/sources/blf.py#L124)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_UntimedBLFRecord"></a>
## `_UntimedBLFRecord`

内部按需消息：保存真实输入身份与载荷，明确没有采集分析时间，禁止原帧导出。

```python
class _UntimedBLFRecord
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`frame`|can.Message|是|无|由本次BLFReader实际提供的消息，保留原身份和载荷供同帧解码；未读取其时间。|
|`path`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|产生此消息的输入BLF路径，用于错误定位。|
|`sequence`|int|是|无|当前文件内从0开始的原记录序号，包括此前跳过的非目标消息。|
|`time_ns`|None|否|None|明确未采集分析时间，不能用作零纳秒或归并键。|
|`raw_time`|None|否|None|二进制消息没有文本时间原文，本内部记录不伪造文字。|
|`line_number`|None|否|None|BLF没有文本行号，定位使用sequence。|

### 返回说明

有限内部记录。

### 异常说明

工厂以真实解析输入构造。
生命周期仅覆盖同次解码和有界传输；不作为公开RawCANRecord或时间线样本。

源码：[`src/chronaxis/sources/blf.py:141`](../../../src/chronaxis/sources/blf.py#L141)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
