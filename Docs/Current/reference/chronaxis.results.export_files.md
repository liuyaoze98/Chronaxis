# `chronaxis.results.export_files`

用有限大小的缓冲写出一组导出文件。所有文件关闭成功后才把临时目录改成正式目录；已有目标不会被覆盖。关闭失败时保存对应文件对象，以便重试清理。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[ResultFormatError](chronaxis.results.errors.md#api-ResultFormatError)

## 对象导航

|对象|用途|
|---|---|
|[`ExportFiles`](#api-ExportFiles)|拥有当前/挂起的有限输出文件、消费游标及可选处理owner，最多16文件。|
|[`ExportFiles.__init__`](#api-ExportFiles-__init__)|预检输出并创建独占临时目录。|
|[`ExportFiles.closed`](#api-ExportFiles-closed)|返回真实关闭状态。|
|[`ExportFiles.open_file`](#api-ExportFiles-open_file)|打开一个固定平面文件。|
|[`ExportFiles.select_file`](#api-ExportFiles-select_file)|切换有限输出表，不重新打开或覆盖。|
|[`ExportFiles.append`](#api-ExportFiles-append)|有限块实际写入并更新摘要。|
|[`ExportFiles.close_file`](#api-ExportFiles-close_file)|真实关闭后登记摘要。|
|[`ExportFiles.close_reader`](#api-ExportFiles-close_reader)|关闭已接管的输入游标。|
|[`ExportFiles.close_files`](#api-ExportFiles-close_files)|关闭当前及挂起文件。|
|[`ExportFiles.register_external`](#api-ExportFiles-register_external)|登记同目录内已关闭的外部writer文件。|
|[`ExportFiles.finish`](#api-ExportFiles-finish)|写出完成清单，随后把临时目录一次重命名为正式目录。|
|[`ExportFiles.close`](#api-ExportFiles-close)|只关闭自有资源，保留诊断文件。|
|[`ExportFiles._cleanup_failed_output`](#api-ExportFiles-_cleanup_failed_output)|公开导出失败时清理本次临时目录。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
from .budget import ResourceBudget, _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from .errors import ResultClosedError, ResultFormatError
```

</details>

<a id="api-ExportFiles"></a>
## `ExportFiles`

拥有当前/挂起的有限输出文件、消费游标及可选处理owner，最多16文件。

```python
ExportFiles(destination, budget, *, integrity=True, timestamped=False)
```


源码：[`src/chronaxis/results/export_files.py:18`](../../../src/chronaxis/results/export_files.py#L18)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ExportFiles-__init__"></a>
### `ExportFiles.__init__`

预检输出并创建独占临时目录。

```python
ExportFiles.__init__(destination, budget, *, integrity=True, timestamped=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`destination`|str &#124; [pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。本次导出的输出目录；timestamped=False 要求目录不存在，内部时间命名模式可复用已有的普通目录，但不接受符号链接或非目录目标。|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)|是|无|位置或关键字。本次运行共用的ResourceBudget对象，用于检查内存和临时磁盘用量。当前对象在分配前申请额度，用完后归还；同一次运行的组件应使用同一个对象。|
|`integrity`|bool|否|True|仅关键字。是否执行本对象的额外内容摘要或认证核验；False仍保留结构、类型、预算及必要文件变化检查。|
|`timestamped`|bool|否|False|仅关键字。内部选择的时间命名模式；默认 False 使用新目录，True 为本次文件分配独占时间后缀，仍不覆盖既有文件。|

#### 返回说明

__init__返回None；使用类名构造时得到已经初始化的对象。后续由该对象管理并关闭自己创建的资源。

#### 异常说明

参数类型、平台能力、已有目标、资源预算或 I/O 错误向外传播。Windows 使用不覆盖移动；Linux 需要 renameat2，文件系统支持在实际安装时确认。构造失败后尚未释放的资源通过 export_cleanup_owner 保留。

源码：[`src/chronaxis/results/export_files.py:21`](../../../src/chronaxis/results/export_files.py#L21)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ExportFiles-closed"></a>
### `ExportFiles.closed`

返回真实关闭状态。

```python
ExportFiles.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/results/export_files.py:66`](../../../src/chronaxis/results/export_files.py#L66)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ExportFiles-open_file"></a>
### `ExportFiles.open_file`

打开一个固定平面文件。

```python
ExportFiles.open_file(name)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|位置或关键字。name安全文件名。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

未关闭/重复/非法名/I/O错。

本函数直接报告的具体错误：

- `ResultClosedError`：导出已关闭或前一文件未关闭。
- `ValueError`：导出文件名或数量非法。
- `ValueError`：导出文件重复。

源码：[`src/chronaxis/results/export_files.py:71`](../../../src/chronaxis/results/export_files.py#L71)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ExportFiles-select_file"></a>
### `ExportFiles.select_file`

切换有限输出表，不重新打开或覆盖。

```python
ExportFiles.select_file(name)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|位置或关键字。本导出使用的固定文件名，已经打开则复用，否则在本目录中新建；不是任意外部路径。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

打开/状态错。

本函数直接报告的具体错误：

- `ResultClosedError`：导出已关闭。

源码：[`src/chronaxis/results/export_files.py:86`](../../../src/chronaxis/results/export_files.py#L86)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ExportFiles-append"></a>
### `ExportFiles.append`

有限块实际写入并更新摘要。

```python
ExportFiles.append(payload)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`payload`|bytes|是|无|位置或关键字。payload最多64KiB bytes。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

配额/写入/结构错。

本函数直接报告的具体错误：

- `ResultClosedError`：导出文件未打开。
- `ResultFormatError`：导出块需要至多64KiB bytes。
- `OSError`：导出写入没有合法进展。

源码：[`src/chronaxis/results/export_files.py:102`](../../../src/chronaxis/results/export_files.py#L102)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ExportFiles-close_file"></a>
### `ExportFiles.close_file`

真实关闭后登记摘要。

```python
ExportFiles.close_file()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

关闭失败保留句柄供重试。

源码：[`src/chronaxis/results/export_files.py:120`](../../../src/chronaxis/results/export_files.py#L120)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ExportFiles-close_reader"></a>
### `ExportFiles.close_reader`

关闭已接管的输入游标。

```python
ExportFiles.close_reader()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原关闭错误，保留游标供重试。

源码：[`src/chronaxis/results/export_files.py:131`](../../../src/chronaxis/results/export_files.py#L131)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ExportFiles-close_files"></a>
### `ExportFiles.close_files`

关闭当前及挂起文件。

```python
ExportFiles.close_files()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原关闭错误，未关的仍在owner中。

源码：[`src/chronaxis/results/export_files.py:140`](../../../src/chronaxis/results/export_files.py#L140)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ExportFiles-register_external"></a>
### `ExportFiles.register_external`

登记同目录内已关闭的外部writer文件。

```python
ExportFiles.register_external(name)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|位置或关键字。name固定文件名。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

名称/读取/关闭错。

外部writer已付spool，本层仅有限回读计算摘要，不再次计算磁盘费用。

本函数直接报告的具体错误：

- `ValueError`：外部导出文件名称或状态非法。

源码：[`src/chronaxis/results/export_files.py:149`](../../../src/chronaxis/results/export_files.py#L149)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ExportFiles-finish"></a>
### `ExportFiles.finish`

写出完成清单，随后把临时目录一次重命名为正式目录。

```python
ExportFiles.finish(metadata)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`metadata`|dict[str, object]|是|无|位置或关键字。本次导出实际产生的元数据，如行数、格式和范围；写入最终清单。|

#### 返回说明

内部目录Path或公开ExportManifest。

#### 异常说明

序列化/配额/关闭/竞态目标错误；失败保.incomplete目录，不冒报发布成功。

源码：[`src/chronaxis/results/export_files.py:174`](../../../src/chronaxis/results/export_files.py#L174)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ExportFiles-close"></a>
### `ExportFiles.close`

只关闭自有资源，保留诊断文件。

```python
ExportFiles.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原关闭/释放错，允许重试。

源码：[`src/chronaxis/results/export_files.py:232`](../../../src/chronaxis/results/export_files.py#L232)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ExportFiles-_cleanup_failed_output"></a>
### `ExportFiles._cleanup_failed_output`

公开导出失败时清理本次临时目录。

```python
ExportFiles._cleanup_failed_output()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

身份或IO错误，可重试close。

源码：[`src/chronaxis/results/export_files.py:255`](../../../src/chronaxis/results/export_files.py#L255)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
