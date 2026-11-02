# chronaxis.sources.blf

将既有python-can BLFReader接入有序混合来源；不重新实现BLF格式解析。

只保留当前报文，DBC由混合来源共用一次。账本计入本层对象；第三方解压器内部
分配与原BLF路径一样不代表硬RSS上限。不扫描文件、不补日期、不改原帧字段。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[RawCANRecord](chronaxis.sources.raw_can.md#api-RawCANRecord)

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

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from pathlib import Path
from ..legacy.worker import _frame
from ..results.budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..timebase.conversion import convert_time, checked_add_ns, require_int64_ns
from .raw_can import RawCANRecord
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

源码：[`src/chronaxis/sources/blf.py:16`](../../../src/chronaxis/sources/blf.py#L16)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BLFSpec-__post_init__"></a>
### `BLFSpec.__post_init__`

核对静态路径与偏移，不打开输入。失败抛类型或范围错误。

```python
BLFSpec.__post_init__()
```

参数：无显式参数。


源码：[`src/chronaxis/sources/blf.py:21`](../../../src/chronaxis/sources/blf.py#L21)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BLFRead"></a>
## `BLFRead`

持有一个真实BLFReader与当前迭代器，EOF、失败、取消均关闭本次文件。

```python
BLFRead(spec, budget, *, check_cancel=None, retain_original=False, retain_source_time=False, selected_ids=None)
```


源码：[`src/chronaxis/sources/blf.py:28`](../../../src/chronaxis/sources/blf.py#L28)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BLFRead-__init__"></a>
### `BLFRead.__init__`

参数为单文件声明、共用的资源用量记录及按需选择；返回reader；失败附恢复owner。

```python
BLFRead.__init__(spec, budget, *, check_cancel=None, retain_original=False, retain_source_time=False, selected_ids=None)
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

源码：[`src/chronaxis/sources/blf.py:31`](../../../src/chronaxis/sources/blf.py#L31)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BLFRead-closed"></a>
### `BLFRead.closed`

返回本层所有文件和费用是否已释放。

```python
BLFRead.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


源码：[`src/chronaxis/sources/blf.py:57`](../../../src/chronaxis/sources/blf.py#L57)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BLFRead-__iter__"></a>
### `BLFRead.__iter__`

返回同次迭代器，不重复打开文件。

```python
BLFRead.__iter__()
```

参数：无显式参数。


源码：[`src/chronaxis/sources/blf.py:61`](../../../src/chronaxis/sources/blf.py#L61)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BLFRead-__next__"></a>
### `BLFRead.__next__`

读取下一实际帧，先按ID选择再转换；失败保原异常并清理。

```python
BLFRead.__next__()
```

参数：无显式参数。


源码：[`src/chronaxis/sources/blf.py:65`](../../../src/chronaxis/sources/blf.py#L65)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BLFRead-close"></a>
### `BLFRead.close`

关闭本次库迭代器和文件再释放费用；失败保留owner以便重试。

```python
BLFRead.close()
```

参数：无显式参数。


源码：[`src/chronaxis/sources/blf.py:88`](../../../src/chronaxis/sources/blf.py#L88)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
