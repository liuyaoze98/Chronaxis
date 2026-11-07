# `chronaxis.results.merge_runs`

在固定内存和文件句柄数量内归并多份已排序结果，减少中间文件重复写入。

输入为同一ResultSpool持有的1至64份run及一个全新目标路径；输出保留原JSONL
的全部JSONL字节。每路只保留当前一行，按原排序键及输入路序稳定归并。
读取与写入沿用owner的严格校验和累计磁盘配额，RAM先预约到owner._merge_cost。
本模块不删除输入、不修改结果模型，也不持有全量run清单或独立预算。ExitStack
逐个关闭实际文件，未关闭句柄和未退费用仍保留在owner._merge_run_resources，
调用方可通过同一owner.close重试；关闭失败不能被当成归并成功或资源已经释放。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisError](chronaxis.results.errors.md#api-AnalysisError)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[ResultFormatError](chronaxis.results.errors.md#api-ResultFormatError)

## 对象导航

|对象|用途|
|---|---|
|[`_MergeResources`](#api-_MergeResources)|保存本次所有实际文件与已付归并费，持续关闭失败也不丢真实责任。|
|[`_MergeResources.__init__`](#api-_MergeResources-__init__)|建立已预付的有限责任对象。|
|[`_MergeResources.open`](#api-_MergeResources-open)|把新FD先安装到真实槽，再登记ExitStack回调，覆盖登记时取消。|
|[`_MergeResources._close_slot`](#api-_MergeResources-_close_slot)|实际关闭一个已登记FD，关闭后取消仍记录真实关闭事实。|
|[`_MergeResources.close`](#api-_MergeResources-close)|先关闭所有实际FD再退自有费用；失败后同一责任对象可重复关闭。|
|[`merge_runs`](#api-merge_runs)|将同一暂存的有限有序输入稳定合并到新文件，失败仍保原错误与实际费用。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from contextlib import ExitStack
from heapq import heappop, heappush
from pathlib import Path
from .budget import _reserve_owned_ram, _release_owned_ram
from .errors import AnalysisError, ResultFormatError
```

</details>

<a id="api-_MergeResources"></a>
## `_MergeResources`

保存本次所有实际文件与已付归并费，持续关闭失败也不丢真实责任。

handles每槽只持一个实际FD或None；pending先安装新开FD再扩展登记列表。
ExitStack完成首轮关闭，失败后按仍存活的槽重试；只有全部FD与费用均清理才closed。

```python
_MergeResources(owner)
```


源码：[`src/chronaxis/results/merge_runs.py:24`](../../../src/chronaxis/results/merge_runs.py#L24)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_MergeResources-__init__"></a>
### `_MergeResources.__init__`

建立已预付的有限责任对象。

```python
_MergeResources.__init__(owner)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|ResultSpool|是|无|位置或关键字。本次结果暂存器，提供归并文件的资源额度和文件计数。|

#### 返回说明

None；初始化实例状态。

#### 异常说明

分配错误。

源码：[`src/chronaxis/results/merge_runs.py:31`](../../../src/chronaxis/results/merge_runs.py#L31)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_MergeResources-open"></a>
### `_MergeResources.open`

把新FD先安装到真实槽，再登记ExitStack回调，覆盖登记时取消。

```python
_MergeResources.open(path, mode, buffering)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。要打开的暂存文件路径，由归并过程提供。|
|`mode`|str|是|无|位置或关键字。Python文件打开模式，例如"rb"读取二进制、"wb"写入二进制；本函数不改变该模式。|
|`buffering`|int|是|无|位置或关键字。交给open的缓冲参数；正数是缓冲字节数，0表示不缓冲，-1表示使用默认缓冲。|

#### 返回说明

本对象实际持有的句柄。

#### 异常说明

原打开/登记/取消错误；已打开的FD仍由pending或handles持有。

源码：[`src/chronaxis/results/merge_runs.py:37`](../../../src/chronaxis/results/merge_runs.py#L37)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_MergeResources-_close_slot"></a>
### `_MergeResources._close_slot`

实际关闭一个已登记FD，关闭后取消仍记录真实关闭事实。

```python
_MergeResources._close_slot(position)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`position`|int|是|无|位置或关键字。当前消息在本批记录中的位置，从0开始，用于取得该条消息的值。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原close错误；未关对象保原槽。

源码：[`src/chronaxis/results/merge_runs.py:50`](../../../src/chronaxis/results/merge_runs.py#L50)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_MergeResources-close"></a>
### `_MergeResources.close`

先关闭所有实际FD再退自有费用；失败后同一责任对象可重复关闭。

```python
_MergeResources.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None；closed后幂等。

#### 异常说明

首个清理错误为主，其他错误附note；
    存活FD或未抵销费用时保owner._merge_run_resources，绝不释放借用余额。

源码：[`src/chronaxis/results/merge_runs.py:65`](../../../src/chronaxis/results/merge_runs.py#L65)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-merge_runs"></a>
## `merge_runs`

将同一暂存的有限有序输入稳定合并到新文件，失败仍保原错误与实际费用。

```python
merge_runs(owner, paths_tuple, destination, *, table)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|ResultSpool|是|无|位置或关键字。owner为当前ResultSpool|
|`paths_tuple`|tuple|是|无|位置或关键字。paths_tuple为1至64个Path且无重复|
|`destination`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。destination     为不存在的Path|
|`table`|str &#124; None|是|无|仅关键字。结果表名称，具体可用名称见[结果文件](../results.md)；None兼容旧的双路归并调用。内部传递时须与当前行所属表一致。|

### 返回说明

None；目标JSONL经真实关闭后才成功返回。

### 异常说明

配置/预算/行损坏、排序回退、文件错误和原取消；清理副错只附note，
    未退RAM仍留在同一owner._merge_cost，可由owner.close继续处理。

### 边界说明

相等键按输入路序稳定取出；每次写后先丢旧行再读该路下一行。

源码：[`src/chronaxis/results/merge_runs.py:133`](../../../src/chronaxis/results/merge_runs.py#L133)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
