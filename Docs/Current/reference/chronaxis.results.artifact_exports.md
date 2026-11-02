# chronaxis.results.artifact_exports

管理本次生成的导出文件及其索引。结果发布时复制并核对这些文件，不再重新计算导出数据。关闭对象会释放读取资源，文件是否发布由单独状态记录。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[FrameSort](chronaxis.results.frame_sort.md#api-FrameSort)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[ResultFormatError](chronaxis.results.errors.md#api-ResultFormatError)

## 对象导航

|对象|用途|
|---|---|
|[`ArtifactExportStore`](#api-ArtifactExportStore)|保存一次会话的信号/报文导出及独立清单，不借用原数据reader。|
|[`ArtifactExportStore.__init__`](#api-ArtifactExportStore-__init__)|创建独占目录及索引。|
|[`ArtifactExportStore.closed`](#api-ArtifactExportStore-closed)|读取真实关闭状态。|
|[`ArtifactExportStore.owned_ram`](#api-ArtifactExportStore-owned_ram)|汇总本仓及索引实际费用供父层核账。|
|[`ArtifactExportStore.next_path`](#api-ArtifactExportStore-next_path)|提供当前导出独占子目录。|
|[`ArtifactExportStore._close_slot`](#api-ArtifactExportStore-_close_slot)|真实close成功后撤槽。|
|[`ArtifactExportStore._identity`](#api-ArtifactExportStore-_identity)|取得普通文件的替换/修改标识。|
|[`ArtifactExportStore._file`](#api-ArtifactExportStore-_file)|必要复制时才读内容；请求摘要则在同次读取计算。|
|[`ArtifactExportStore.append`](#api-ArtifactExportStore-append)|登记刚生成目录中有限文件的实际身份。|
|[`ArtifactExportStore.seal`](#api-ArtifactExportStore-seal)|结束目录索引的写入；之后才能把导出文件交给结果对象管理。|
|[`ArtifactExportStore.copy_to`](#api-ArtifactExportStore-copy_to)|逐目录复制到新发布位置，按请求在同次读取核摘要。|
|[`ArtifactExportStore.recover_copy`](#api-ArtifactExportStore-recover_copy)|关闭失败发布句柄，可重新发布到另一新目录。|
|[`ArtifactExportStore.close`](#api-ArtifactExportStore-close)|真实关闭索引及IO后释放自己的费用，保留磁盘。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from pathlib import Path
from hashlib import sha256
from .frame_sort import FrameSort
from .budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from .errors import ResultClosedError, ResultFormatError
from .raw_exports import _write_all
```

</details>

<a id="api-ArtifactExportStore"></a>
## `ArtifactExportStore`

保存一次会话的信号/报文导出及独立清单，不借用原数据reader。

```python
ArtifactExportStore(budget, path, session_id, device_label, *, integrity=True)
```


源码：[`src/chronaxis/results/artifact_exports.py:18`](../../../src/chronaxis/results/artifact_exports.py#L18)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ArtifactExportStore-__init__"></a>
### `ArtifactExportStore.__init__`

创建独占目录及索引。

```python
ArtifactExportStore.__init__(budget, path, session_id, device_label, *, integrity=True)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|ResourceBudget|是|无|位置或关键字。本次运行共用的ResourceBudget对象，用于检查内存和临时磁盘用量。当前对象在分配前申请额度，用完后归还；同一次运行的组件应使用同一个对象。|
|`path`|[pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。保存本次导出文件登记信息的新目录，记录会话与文件摘要。|
|`session_id`|str|是|无|位置或关键字。本次会话的名字，用来防止把不同试验的数据混在一起。|
|`device_label`|str|是|无|位置或关键字。记录本次导出的设备来源标签；当前这个导出入口只接受home或work，pending会被拒绝。标签应来自已确认的执行设备映射，不从输入路径推断。|
|`integrity`|bool|否|True|仅关键字。是否执行本对象的额外内容摘要或认证核验；False仍保留结构、类型、预算及必要文件变化检查。|

#### 返回说明

__init__返回None；使用类名构造时得到已经初始化的对象。后续由该对象管理并关闭自己创建的资源。

#### 异常说明

配置/IO/预算错。

本函数直接报告的具体错误：

- `ValueError`：新导出需要实际设备标签及新工作目录。

源码：[`src/chronaxis/results/artifact_exports.py:21`](../../../src/chronaxis/results/artifact_exports.py#L21)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ArtifactExportStore-closed"></a>
### `ArtifactExportStore.closed`

读取真实关闭状态。

```python
ArtifactExportStore.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/results/artifact_exports.py:42`](../../../src/chronaxis/results/artifact_exports.py#L42)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ArtifactExportStore-owned_ram"></a>
### `ArtifactExportStore.owned_ram`

汇总本仓及索引实际费用供父层核账。

```python
ArtifactExportStore.owned_ram
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

bytes。

#### 异常说明

无。

源码：[`src/chronaxis/results/artifact_exports.py:48`](../../../src/chronaxis/results/artifact_exports.py#L48)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ArtifactExportStore-next_path"></a>
### `ArtifactExportStore.next_path`

提供当前导出独占子目录。

```python
ArtifactExportStore.next_path()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

Path。

#### 异常说明

非building。

本函数直接报告的具体错误：

- `ResultClosedError`：导出索引不能新增。

源码：[`src/chronaxis/results/artifact_exports.py:53`](../../../src/chronaxis/results/artifact_exports.py#L53)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ArtifactExportStore-_close_slot"></a>
### `ArtifactExportStore._close_slot`

真实close成功后撤槽。

```python
ArtifactExportStore._close_slot(slot)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`slot`|str|是|无|位置或关键字。当前对象中用于保存资源或其费用的属性名，例如"_row_cost"；只能指向本对象实际管理的项。释放成功后才清空对应项。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原close错，保槽重试。

源码：[`src/chronaxis/results/artifact_exports.py:60`](../../../src/chronaxis/results/artifact_exports.py#L60)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ArtifactExportStore-_identity"></a>
### `ArtifactExportStore._identity`

取得普通文件的替换/修改标识。

```python
ArtifactExportStore._identity(path)
```

装饰器：`staticmethod`。

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。本次任务专用路径；只操作本次登记的资源，不能指向原始输入或历史项目目录。|

#### 返回说明

四整数tuple。

#### 异常说明

链接/非普通文件/IO。

源码：[`src/chronaxis/results/artifact_exports.py:68`](../../../src/chronaxis/results/artifact_exports.py#L68)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ArtifactExportStore-_file"></a>
### `ArtifactExportStore._file`

必要复制时才读内容；请求摘要则在同次读取计算。

```python
ArtifactExportStore._file(path, destination=None, expected=None, identity=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|[pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。实际导出源文件，读取其字节数和SHA-256以核对完整性。|
|`destination`|[pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) &#124; None|否|None|位置或关键字。复制的目标文件；None表示仅核对源文件，不执行复制。|
|`expected`|tuple &#124; None|否|None|位置或关键字。可选(size_bytes, sha256)二元组；文件大小与哈希都必须与登记值相同。|
|`identity`|tuple[int, int, int, int] &#124; None|否|None|位置或关键字。本次登记的设备号、文件号、大小和mtime_ns；未请求摘要时据此拒绝文件替换或修改。|

#### 返回说明

大小和可选摘要。

#### 异常说明

IO/内容变化。

本函数直接报告的具体错误：

- `ResultClosedError`：导出文件还有未清理句柄。
- `ResultFormatError`：导出文件内容与登记身份不同。
- `ResultFormatError`：导出文件超过登记大小。

源码：[`src/chronaxis/results/artifact_exports.py:75`](../../../src/chronaxis/results/artifact_exports.py#L75)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ArtifactExportStore-append"></a>
### `ArtifactExportStore.append`

登记刚生成目录中有限文件的实际身份。

```python
ArtifactExportStore.append(export_type, scope, interval, *, segment_id=None, completed_files=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`export_type`|str|是|无|位置或关键字。"signal_csv"是信号CSV，"can_frames"是CAN报文文件；写入导出清单用于分类。|
|`scope`|str|是|无|位置或关键字。"session"表示整个会话，"segments"表示窗口产生的单个片段。|
|`interval`|Interval|是|无|位置或关键字。实际导出的左闭右开Interval；无观测时可为None。|
|`segment_id`|str &#124; None|否|None|仅关键字。本导出所属的片段ID；导出整个会话时填写None。|
|`completed_files`|Sequence[dict] &#124; None|否|None|仅关键字。同次writer交出的文件名、字节数和可选摘要；None沿原登记路径取得事实，不能传外部伪造的证明。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

文件/索引错。

本函数直接报告的具体错误：

- `ValueError`：导出种类或范围错误。
- `ValueError`：导出缺完成清单。
- `ValueError`：导出目录仅接受至多16个普通文件。

源码：[`src/chronaxis/results/artifact_exports.py:111`](../../../src/chronaxis/results/artifact_exports.py#L111)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ArtifactExportStore-seal"></a>
### `ArtifactExportStore.seal`

结束目录索引的写入；之后才能把导出文件交给结果对象管理。

```python
ArtifactExportStore.seal()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

状态/排序IO错。

源码：[`src/chronaxis/results/artifact_exports.py:146`](../../../src/chronaxis/results/artifact_exports.py#L146)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ArtifactExportStore-copy_to"></a>
### `ArtifactExportStore.copy_to`

逐目录复制到新发布位置，按请求在同次读取核摘要。

```python
ArtifactExportStore.copy_to(destination)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`destination`|[pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。新的发布目录；复制已经生成的文件并核对摘要，不再读取或解码原始日志。|

#### 返回说明

exports.jsonl路径。

#### 异常说明

IO/完整性错。

本函数直接报告的具体错误：

- `ResultClosedError`：导出索引未封口或有发布资源待恢复。
- `ResultFormatError`：导出索引数量不符。
- `ResultFormatError`：导出索引序号不连续。
- `ResultFormatError`：导出索引目录错误。
- `ResultFormatError`：导出索引包含不安全文件名。

源码：[`src/chronaxis/results/artifact_exports.py:151`](../../../src/chronaxis/results/artifact_exports.py#L151)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ArtifactExportStore-recover_copy"></a>
### `ArtifactExportStore.recover_copy`

关闭失败发布句柄，可重新发布到另一新目录。

```python
ArtifactExportStore.recover_copy()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

实际close错可重试。

源码：[`src/chronaxis/results/artifact_exports.py:196`](../../../src/chronaxis/results/artifact_exports.py#L196)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ArtifactExportStore-close"></a>
### `ArtifactExportStore.close`

真实关闭索引及IO后释放自己的费用，保留磁盘。

```python
ArtifactExportStore.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原close错。

源码：[`src/chronaxis/results/artifact_exports.py:206`](../../../src/chronaxis/results/artifact_exports.py#L206)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

## 内部匿名回调


<a id="lambda-141"></a>
### 第141行匿名函数

```python
lambda f: f['name']
```

|参数|含义|返回/异常|
|---|---|---|
|`f`|包含name字段的导出文件说明映射。|返回文件名，使清单顺序确定；缺少name传播KeyError。|
