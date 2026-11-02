# chronaxis.results.frame_sort

为离线报文导出进行有界磁盘排序，不把整段报文留在内存。

输入为有限标量排序键和新导出自己的JSON记录，输出按键稳定排列的记录流。
每批最多64行，归并只开两路输入；旧run留作诊断且累计计入spool。旧调用默认用摘要绑定每行与结束标记；新版仅显式完整性诊断时启用。
不启用摘要时仍校验行结构、行长和结束计数，拒绝截断，不提供防篡改证明。
所有句柄在owner上登记，持续关闭失败仍可重试；本模块不读原日志或加载DBC。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[ResultFormatError](chronaxis.results.errors.md#api-ResultFormatError)

## 对象导航

|对象|用途|
|---|---|
|[`FrameSort`](#api-FrameSort)|拥有一个新目录、最多64行缓冲和三个实际文件，封口后仅接受顺序回读。|
|[`FrameSort.__init__`](#api-FrameSort-__init__)|预约并创建暂存。|
|[`FrameSort._check`](#api-FrameSort-_check)|在有界I/O间检查取消。|
|[`FrameSort._open`](#api-FrameSort-_open)|登记真实句柄后交付。|
|[`FrameSort._close_file`](#api-FrameSort-_close_file)|关闭成功才撤销登记。|
|[`FrameSort._mac`](#api-FrameSort-_mac)|把完整行绑定当前run及顺序。|
|[`FrameSort._write`](#api-FrameSort-_write)|有界编码并实写一行。|
|[`FrameSort._read`](#api-FrameSort-_read)|逐行核完整性，必须读到合法结束记录。|
|[`FrameSort.append`](#api-FrameSort-append)|预约后缓冲一条。|
|[`FrameSort._flush`](#api-FrameSort-_flush)|稳定排序有限缓冲并保存一个run。|
|[`FrameSort._merge`](#api-FrameSort-_merge)|只保两路当前行进行稳定归并。|
|[`FrameSort.seal`](#api-FrameSort-seal)|完成所有有界归并，空输入也有完整结束记录。|
|[`FrameSort.rows`](#api-FrameSort-rows)|交付单一可关闭回读游标。|
|[`FrameSort.close`](#api-FrameSort-close)|关闭全部实际文件后释放自有预算；保暂存供诊断。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from hashlib import blake2b
from hmac import compare_digest
from pathlib import Path
from secrets import token_bytes
from .budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from .errors import ResultClosedError, ResultFormatError
```

</details>

<a id="api-FrameSort"></a>
## `FrameSort`

拥有一个新目录、最多64行缓冲和三个实际文件，封口后仅接受顺序回读。

```python
FrameSort(path, budget, *, check_cancel=None, buffer_rows=64, integrity=True)
```


源码：[`src/chronaxis/results/frame_sort.py:19`](../../../src/chronaxis/results/frame_sort.py#L19)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameSort-__init__"></a>
### `FrameSort.__init__`

预约并创建暂存。

```python
FrameSort.__init__(path, budget, *, check_cancel=None, buffer_rows=64, integrity=True)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|[pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。本次排序使用的文件或新工作目录路径。|
|`budget`|ResourceBudget|是|无|位置或关键字。本次运行共用的ResourceBudget对象，用于检查内存和临时磁盘用量。当前对象在分配前申请额度，用完后归还；同一次运行的组件应使用同一个对象。|
|`check_cancel`|Callable[[], None] &#124; None|否|None|仅关键字。可选的无参取消检查函数。需要终止时由它抛出异常；None表示不额外调用取消检查。|
|`buffer_rows`|int|否|64|仅关键字。内存中积累多少条排序记录后写入暂存文件，正整数；不是总输出数量限制。|
|`integrity`|bool|否|True|仅关键字。是否执行本对象的额外内容摘要或认证核验；False仍保留结构、类型、预算及必要文件变化检查。|

#### 返回说明

__init__返回None；使用类名构造时得到已经初始化的对象。后续由该对象管理并关闭自己创建的资源。

#### 异常说明

配置/预算/I/O错。

本函数直接报告的具体错误：

- `ValueError`：报文排序缓冲需要1至64行。
- `ValueError`：报文排序不能写RefProjects。

源码：[`src/chronaxis/results/frame_sort.py:22`](../../../src/chronaxis/results/frame_sort.py#L22)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameSort-_check"></a>
### `FrameSort._check`

在有界I/O间检查取消。

```python
FrameSort._check()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

关闭或取消。

本函数直接报告的具体错误：

- `ResultClosedError`：报文排序已关闭。

源码：[`src/chronaxis/results/frame_sort.py:44`](../../../src/chronaxis/results/frame_sort.py#L44)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameSort-_open"></a>
### `FrameSort._open`

登记真实句柄后交付。

```python
FrameSort._open(path, mode)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|[pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。本次排序使用的文件或新工作目录路径。|
|`mode`|str|是|无|位置或关键字。文件打开模式字符串，例如rb/wb；按当前读写用途传入。|

#### 返回说明

文件。

#### 异常说明

打开或登记失败。

源码：[`src/chronaxis/results/frame_sort.py:52`](../../../src/chronaxis/results/frame_sort.py#L52)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameSort-_close_file"></a>
### `FrameSort._close_file`

关闭成功才撤销登记。

```python
FrameSort._close_file(stream)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`stream`|BinaryIO|是|无|位置或关键字。当前已打开的二进制暂存流，函数在此读写或关闭；不是文件路径。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

关闭错保责任。

源码：[`src/chronaxis/results/frame_sort.py:60`](../../../src/chronaxis/results/frame_sort.py#L60)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameSort-_mac"></a>
### `FrameSort._mac`

把完整行绑定当前run及顺序。

```python
FrameSort._mac(path, index, body)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|[pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。本次排序使用的文件或新工作目录路径。|
|`index`|int|是|无|位置或关键字。该文件中的整数记录序号，纳入校验以发现调换顺序。|
|`body`|bytes|是|无|位置或关键字。一行UTF-8 JSON正文，不含前面的认证码和末尾换行。|

#### 返回说明

64字节摘要。

#### 异常说明

原类型错。

源码：[`src/chronaxis/results/frame_sort.py:65`](../../../src/chronaxis/results/frame_sort.py#L65)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameSort-_write"></a>
### `FrameSort._write`

有界编码并实写一行。

```python
FrameSort._write(stream, index, packet)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`stream`|BinaryIO|是|无|位置或关键字。当前已打开的二进制暂存流，函数在此读写或关闭；不是文件路径。|
|`index`|int|是|无|位置或关键字。将写入记录在本文件中的整数序号。|
|`packet`|dict[str, object]|是|无|位置或关键字。提供待写入排序暂存的一行JSON结构：数据行为排序键、序号和内容组成的三项结构，结束行为带end计数的对象；编码后不超过64KiB。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

配额/超行/写入错。

本函数直接报告的具体错误：

- `ResultFormatError`：报文排序单行超过64KiB。
- `OSError`：报文排序写入无进展。

源码：[`src/chronaxis/results/frame_sort.py:73`](../../../src/chronaxis/results/frame_sort.py#L73)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameSort-_read"></a>
### `FrameSort._read`

逐行核完整性，必须读到合法结束记录。

```python
FrameSort._read(path)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|[pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。本次排序使用的文件或新工作目录路径。|

#### 返回说明

记录生成器。

#### 异常说明

改写/截断/关闭错。

本函数直接报告的具体错误：

- `ResultFormatError`：报文排序行截断或超限。
- `ResultFormatError`：报文排序行内容或顺序被修改。
- `ResultFormatError`：报文排序行结构非法。
- `ResultFormatError`：报文排序结束记录不一致。

源码：[`src/chronaxis/results/frame_sort.py:89`](../../../src/chronaxis/results/frame_sort.py#L89)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameSort-append"></a>
### `FrameSort.append`

预约后缓冲一条。

```python
FrameSort.append(key, packet)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`key`|tuple|是|无|位置或关键字。key有限同类型标量tuple、packet有限JSON对象。|
|`packet`|dict[str, object]|是|无|位置或关键字。提供一条待排序的有限JSON记录；和独立的key一起保存，编码后不能超过65000字节。这是导出数据，不是进程通信命令。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

结构/预算/I/O错。

本函数直接报告的具体错误：

- `ValueError`：报文排序需要building及有限标量键。
- `ResultFormatError`：报文记录超过排序行能力。

源码：[`src/chronaxis/results/frame_sort.py:122`](../../../src/chronaxis/results/frame_sort.py#L122)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameSort-_flush"></a>
### `FrameSort._flush`

稳定排序有限缓冲并保存一个run。

```python
FrameSort._flush()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

排序/I/O/配额错。

源码：[`src/chronaxis/results/frame_sort.py:137`](../../../src/chronaxis/results/frame_sort.py#L137)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameSort-_merge"></a>
### `FrameSort._merge`

只保两路当前行进行稳定归并。

```python
FrameSort._merge(left, right, target)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`left`|[pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。已排序的左侧临时文件。|
|`right`|[pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。已排序的右侧临时文件。|
|`target`|[pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。归并输出的新文件，逐行写入，不一次读完两个输入。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

输入校验/写入/关闭错。

源码：[`src/chronaxis/results/frame_sort.py:150`](../../../src/chronaxis/results/frame_sort.py#L150)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameSort-seal"></a>
### `FrameSort.seal`

完成所有有界归并，空输入也有完整结束记录。

```python
FrameSort.seal()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

输入/预算/取消/I/O错。

本函数直接报告的具体错误：

- `ResultClosedError`：报文排序不能重复封口。

源码：[`src/chronaxis/results/frame_sort.py:183`](../../../src/chronaxis/results/frame_sort.py#L183)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameSort-rows"></a>
### `FrameSort.rows`

交付单一可关闭回读游标。

```python
FrameSort.rows()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

(key,序号,记录)生成器。

#### 异常说明

非sealed或已有游标。

本函数直接报告的具体错误：

- `ResultClosedError`：报文排序未封口或已交付游标。

源码：[`src/chronaxis/results/frame_sort.py:201`](../../../src/chronaxis/results/frame_sort.py#L201)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameSort-close"></a>
### `FrameSort.close`

关闭全部实际文件后释放自有预算；保暂存供诊断。

```python
FrameSort.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原关闭/释放错可重试。

源码：[`src/chronaxis/results/frame_sort.py:210`](../../../src/chronaxis/results/frame_sort.py#L210)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

## 内部匿名回调


<a id="lambda-142"></a>
### 第142行匿名函数

```python
lambda item: (item[0], item[1])
```

|参数|含义|返回/异常|
|---|---|---|
|`item`|帧排序缓存条目。|返回时间与排序序号二元组，确定缓存归并顺序。|
