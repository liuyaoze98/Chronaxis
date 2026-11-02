# chronaxis.execution.frame_capture

为显式报文导出保存同次记录和新编码所需DBC上下文。

默认关闭时不创建这些对象。TextFrameStore只保存本次文本读取已交付的原帧、
物理值和定位，可为多个窗口有限回放；不重新读原文件。FrameDBCContext负责
新编码的DBC身份/字段声明，可借给新文本解码器共用一次加载。旧BLF链自身的
DBC加载和解码不改变；为新增编码另加载同一哈希的定义属于新输出的显式成本。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[DBCFramePatch](chronaxis.results.frame_patch.md#api-DBCFramePatch)、[FrameSample](chronaxis.results.frame_rebuild.md#api-FrameSample)、[FrameSort](chronaxis.results.frame_sort.md#api-FrameSort)、[LegacyCANField](chronaxis.legacy.records.md#api-LegacyCANField)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)

## 对象导航

|对象|用途|
|---|---|
|[`FrameDBCContext`](#api-FrameDBCContext)|拥有供新输出使用的DBC定义、摘要和额外请求字段，借用者不负责释放。|
|[`FrameDBCContext.__init__`](#api-FrameDBCContext-__init__)|加载并核身份，生成连续量/选择器请求。|
|[`FrameDBCContext._hash`](#api-FrameDBCContext-_hash)|核同一文件的完整内容身份。|
|[`FrameDBCContext.require_open`](#api-FrameDBCContext-require_open)|禁止使用已释放DBC。|
|[`FrameDBCContext.pairs`](#api-FrameDBCContext-pairs)|交付规则与同次定义的有限借用。|
|[`FrameDBCContext.observe`](#api-FrameDBCContext-observe)|核对同次实际帧身份，复用已加载DBC，不增加文件扫描。|
|[`FrameDBCContext.is_known_frame`](#api-FrameDBCContext-is_known_frame)|核对同次实际帧身份，复用已加载DBC，不增加文件扫描。|
|[`FrameDBCContext.close`](#api-FrameDBCContext-close)|在借用者关闭后释放定义和实际句柄。|
|[`TextFrameStore`](#api-TextFrameStore)|保存连续原序的同次文本CAN事实；封口后允许多个窗口逐个回放。|
|[`TextFrameStore.__init__`](#api-TextFrameStore-__init__)|建立有限排序暂存及真实读取身份。|
|[`TextFrameStore.append`](#api-TextFrameStore-append)|保原序原时间，不让排序掩盖回退。|
|[`TextFrameStore.seal`](#api-TextFrameStore-seal)|完整真实EOF后封口。|
|[`TextFrameStore.iter_samples`](#api-TextFrameStore-iter_samples)|打开一个有界完整回放，提前关闭不声称完整核验。|
|[`TextFrameStore.iter_frames`](#api-TextFrameStore-iter_frames)|只交付原帧及定位，不重新解码。|
|[`TextFrameStore.close`](#api-TextFrameStore-close)|关闭全部真实回放FD和排序仓，保诊断文件。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from hashlib import file_digest
from pathlib import Path
from ..legacy.records import LegacyCANField
from ..legacy.binding import dbc_candidates, select_message
from ..results.budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..results.errors import ResultClosedError
from ..results.frame_exports import as_export_frame
from ..results.frame_patch import DBCFramePatch
from ..results.frame_rebuild import FrameSample, _sample_packet, _restore_sample
from ..results.frame_sort import FrameSort
from .history import _metadata_bytes
```

</details>

<a id="api-FrameDBCContext"></a>
## `FrameDBCContext`

拥有供新输出使用的DBC定义、摘要和额外请求字段，借用者不负责释放。

```python
FrameDBCContext(path, rules, budget, *, cycle_periods=False, integrity=True)
```


源码：[`src/chronaxis/execution/frame_capture.py:23`](../../../src/chronaxis/execution/frame_capture.py#L23)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-FrameDBCContext-__init__"></a>
### `FrameDBCContext.__init__`

加载并核身份，生成连续量/选择器请求。

```python
FrameDBCContext.__init__(path, rules, budget, *, cycle_periods=False, integrity=True)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|str &#124; [pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。本来源DBC文件路径；打开后供报文重建读取信号位定义。|
|`rules`|tuple[FrameRebuildRule, ...]|是|无|位置或关键字。FrameRebuildRule元组，列出本次允许重建的报文和连续字段。|
|`budget`|ResourceBudget|是|无|位置或关键字。本次运行共用的ResourceBudget对象，用于检查内存和临时磁盘用量。当前对象在分配前申请额度，用完后归还；同一次运行的组件应使用同一个对象。|
|`cycle_periods`|Mapping[tuple, int]|否|False|仅关键字。已读取的报文定位到正纳秒周期的映射；只含当前导出或计算确实需要的报文。|
|`integrity`|bool|否|True|仅关键字。是否执行本对象的额外内容摘要或认证核验；False仍保留结构、类型、预算及必要文件变化检查。|

#### 返回说明

__init__返回None；使用类名构造时得到已经初始化的对象。后续由该对象管理并关闭自己创建的资源。

#### 异常说明

DBC/预算/字段/I/O错。

本函数直接报告的具体错误：

- `ValueError`：新增编码加载DBC期间内容发生变化。

源码：[`src/chronaxis/execution/frame_capture.py:26`](../../../src/chronaxis/execution/frame_capture.py#L26)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-FrameDBCContext-_hash"></a>
### `FrameDBCContext._hash`

核同一文件的完整内容身份。

```python
FrameDBCContext._hash()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

SHA256文本。

#### 异常说明

打开/读取/真实关闭错。

源码：[`src/chronaxis/execution/frame_capture.py:78`](../../../src/chronaxis/execution/frame_capture.py#L78)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-FrameDBCContext-require_open"></a>
### `FrameDBCContext.require_open`

禁止使用已释放DBC。

```python
FrameDBCContext.require_open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ResultClosedError。

本函数直接报告的具体错误：

- `ResultClosedError`：导出DBC上下文已关闭。

源码：[`src/chronaxis/execution/frame_capture.py:86`](../../../src/chronaxis/execution/frame_capture.py#L86)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-FrameDBCContext-pairs"></a>
### `FrameDBCContext.pairs`

交付规则与同次定义的有限借用。

```python
FrameDBCContext.pairs()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

tuple。

#### 异常说明

已关闭或身份缺失。

源码：[`src/chronaxis/execution/frame_capture.py:92`](../../../src/chronaxis/execution/frame_capture.py#L92)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-FrameDBCContext-observe"></a>
### `FrameDBCContext.observe`

核对同次实际帧身份，复用已加载DBC，不增加文件扫描。

```python
FrameDBCContext.observe(frame)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`frame`|LegacyRawFrame|是|无|位置或关键字。当前原帧，必须保留实际通道、ID和类型标志。|

#### 返回说明

本次实际匹配的cantools Message；没有选中输出规则时为None。

#### 异常说明

ValueError：规则匹配多种实际身份或多个输出规则；ResultClosedError：上下文已关闭。

#### 副作用说明

每条规则只保存一个已识别定义和身份，不保留额外帧或扫描文件。

源码：[`src/chronaxis/execution/frame_capture.py:110`](../../../src/chronaxis/execution/frame_capture.py#L110)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-FrameDBCContext-is_known_frame"></a>
### `FrameDBCContext.is_known_frame`

核对同次实际帧身份，复用已加载DBC，不增加文件扫描。

```python
FrameDBCContext.is_known_frame(frame)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`frame`|LegacyRawFrame|是|无|位置或关键字。当前原帧，必须保留实际通道、ID和类型标志。|

#### 返回说明

bool，表示当前实际帧型在DBC中存在可用定义；不要求未选报文的信号唯一。

#### 异常说明

ResultClosedError：上下文已关闭。

#### 副作用说明

无，不解码或记录帧内容。

源码：[`src/chronaxis/execution/frame_capture.py:137`](../../../src/chronaxis/execution/frame_capture.py#L137)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-FrameDBCContext-close"></a>
### `FrameDBCContext.close`

在借用者关闭后释放定义和实际句柄。

```python
FrameDBCContext.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原关闭/释放错可恢复。

源码：[`src/chronaxis/execution/frame_capture.py:148`](../../../src/chronaxis/execution/frame_capture.py#L148)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-TextFrameStore"></a>
## `TextFrameStore`

保存连续原序的同次文本CAN事实；封口后允许多个窗口逐个回放。

```python
TextFrameStore(path, budget, source, session_id, read_identity, *, database_context=None, channel=None, integrity=True, trace=True)
```


源码：[`src/chronaxis/execution/frame_capture.py:162`](../../../src/chronaxis/execution/frame_capture.py#L162)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-TextFrameStore-__init__"></a>
### `TextFrameStore.__init__`

建立有限排序暂存及真实读取身份。

```python
TextFrameStore.__init__(path, budget, source, session_id, read_identity, *, database_context=None, channel=None, integrity=True, trace=True)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|[pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。用于保存文本CAN原帧的新目录；不覆盖已有目录。|
|`budget`|ResourceBudget|是|无|位置或关键字。本次运行共用的ResourceBudget对象，用于检查内存和临时磁盘用量。当前对象在分配前申请额度，用完后归还；同一次运行的组件应使用同一个对象。|
|`source`|str|是|无|位置或关键字。计划中的CAN来源别名，例如"bus"，用于关联来源记录。|
|`session_id`|str|是|无|位置或关键字。本次会话的名字，用来防止把不同试验的数据混在一起。|
|`read_identity`|str|是|无|位置或关键字。这一次实际读取的唯一标识；不同次读取即使文件同名也不能混用此标识。|
|`database_context`|[FrameDBCContext](chronaxis.execution.frame_capture.md#api-FrameDBCContext) &#124; None|否|None|仅关键字。已经加载的DBC上下文；需要解码或重建字段时借用，None表示未提供。|
|`channel`|int &#124; None|否|None|仅关键字。本来源的内部0基CAN通道，用来核对报文定位与DBC规则；None表示未提供声明，不从文件名猜测。用户配置通道1在此为0。|
|`integrity`|bool|否|True|仅关键字。是否执行本对象的额外内容摘要或认证核验；False仍保留结构、类型、预算及必要文件变化检查。|
|`trace`|bool|否|True|仅关键字。是否保存此功能的详细来源或输入追溯；False在生成处跳过，不能先构造再隐藏。|

#### 返回说明

__init__返回None；使用类名构造时得到已经初始化的对象。后续由该对象管理并关闭自己创建的资源。

#### 异常说明

I/O/预算错。

源码：[`src/chronaxis/execution/frame_capture.py:165`](../../../src/chronaxis/execution/frame_capture.py#L165)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-TextFrameStore-append"></a>
### `TextFrameStore.append`

保原序原时间，不让排序掩盖回退。

```python
TextFrameStore.append(record)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`record`|DecodedCANRecord|是|无|位置或关键字。本次连续序号的DecodedCANRecord，含原报文、时间及已解码字段；时间不能回退。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

时序/状态/预算/I/O错。

本函数直接报告的具体错误：

- `ValueError`：文本原帧仓状态或连续序号不符。
- `ValueError`：文本原帧时间回退。

源码：[`src/chronaxis/execution/frame_capture.py:183`](../../../src/chronaxis/execution/frame_capture.py#L183)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-TextFrameStore-seal"></a>
### `TextFrameStore.seal`

完整真实EOF后封口。

```python
TextFrameStore.seal()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

状态/配额/I/O错。

本函数直接报告的具体错误：

- `ResultClosedError`：文本原帧仓不能重复封口。

源码：[`src/chronaxis/execution/frame_capture.py:205`](../../../src/chronaxis/execution/frame_capture.py#L205)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-TextFrameStore-iter_samples"></a>
### `TextFrameStore.iter_samples`

打开一个有界完整回放，提前关闭不声称完整核验。

```python
TextFrameStore.iter_samples()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

FrameSample生成器。

#### 异常说明

仓状态/篡改/I/O错。

本函数直接报告的具体错误：

- `ResultClosedError`：文本原帧仓不可读。
- `ValueError`：文本原帧暂存序号不一致。

源码：[`src/chronaxis/execution/frame_capture.py:212`](../../../src/chronaxis/execution/frame_capture.py#L212)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-TextFrameStore-iter_frames"></a>
### `TextFrameStore.iter_frames`

只交付原帧及定位，不重新解码。

```python
TextFrameStore.iter_frames()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

ExportCANFrame生成器。

#### 异常说明

原回放错。

源码：[`src/chronaxis/execution/frame_capture.py:227`](../../../src/chronaxis/execution/frame_capture.py#L227)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-TextFrameStore-close"></a>
### `TextFrameStore.close`

关闭全部真实回放FD和排序仓，保诊断文件。

```python
TextFrameStore.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

清理错可重试。

源码：[`src/chronaxis/execution/frame_capture.py:237`](../../../src/chronaxis/execution/frame_capture.py#L237)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
