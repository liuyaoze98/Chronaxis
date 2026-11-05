# `chronaxis.execution.record_export_samples`

只在片段信号导出需要回看时保存所选样本；每行一个值和一个实际时间。

别名、来源、单位和枚举标签留在有限声明中，行内用序号引用。
定长数据按实际时间二分，不构造原文、输入指纹或逐条来源JSON。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[RecordSample](chronaxis.execution.record_sample.md#api-RecordSample)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)、[SourceRef](chronaxis.core.models.md#api-SourceRef)

## 对象导航

|对象|用途|
|---|---|
|[`RecordExportSamples`](#api-RecordExportSamples)|拥有一个惰性定长临时文件；范围查询期间只恢复一条所需样本。|
|[`RecordExportSamples.__init__`](#api-RecordExportSamples-__init__)|只保有限定义和文件槽。|
|[`RecordExportSamples.append`](#api-RecordExportSamples-append)|保存一次所选真实更新，保同一时刻原序号。|
|[`RecordExportSamples._fields`](#api-RecordExportSamples-_fields)|只按已登记位置读取一条。|
|[`RecordExportSamples._lower`](#api-RecordExportSamples-_lower)|二分首个不早于time_ns的行。|
|[`RecordExportSamples.rows`](#api-RecordExportSamples-rows)|只回读半开片段内所选样本，不全量核验或扫描。|
|[`RecordExportSamples.closed`](#api-RecordExportSamples-closed)|返回实际资源状态。|
|[`RecordExportSamples.close`](#api-RecordExportSamples-close)|关闭自有临时文件并释放定义；不碰原输入。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from struct import Struct
from tempfile import TemporaryFile
from ..core.models import SourceRef
from ..core.numeric import ScalarValue
from ..core.types import SignalDType as D, QualityFlag as Q
from ..results.budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..results.errors import ResultClosedError
from .history import _metadata_bytes
from .record_sample import RecordSample
```

</details>

<a id="api-RecordExportSamples"></a>
## `RecordExportSamples`

拥有一个惰性定长临时文件；范围查询期间只恢复一条所需样本。

```python
RecordExportSamples(budget, path, definitions, session)
```


源码：[`src/chronaxis/execution/record_export_samples.py:17`](../../../src/chronaxis/execution/record_export_samples.py#L17)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-RecordExportSamples-__init__"></a>
### `RecordExportSamples.__init__`

只保有限定义和文件槽。

```python
RecordExportSamples.__init__(budget, path, definitions, session)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|ResourceBudget|是|无|位置或关键字。本次分析共享的资源用量记录；新对象先预约所需内存和磁盘额度，关闭时归还自己的内存费用。|
|`path`|str &#124; Path|是|无|位置或关键字。本次任务专用路径；只操作本次登记的资源，不能指向原始输入或历史项目目录。|
|`definitions`|tuple[SignalDefinition, ...]|是|无|位置或关键字。按导出列顺序排列的信号定义；共享枚举标签及字段引用，不逐行复制。|
|`session`|str|是|无|位置或关键字。当前会话ID，用于构造源字段引用，不是整个会话计划。|

#### 返回说明

owner。

#### 异常说明

原构造错。

源码：[`src/chronaxis/execution/record_export_samples.py:19`](../../../src/chronaxis/execution/record_export_samples.py#L19)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-RecordExportSamples-append"></a>
### `RecordExportSamples.append`

保存一次所选真实更新，保同一时刻原序号。

```python
RecordExportSamples.append(sample)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`sample`|[RecordSample](chronaxis.execution.record_sample.md#api-RecordSample)|是|无|位置或关键字。当前一条已归一化的所需信号更新，含实际时间、值及有效状态。|

#### 返回说明

None。

#### 异常说明

顺序/预算/短写。

源码：[`src/chronaxis/execution/record_export_samples.py:37`](../../../src/chronaxis/execution/record_export_samples.py#L37)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-RecordExportSamples-_fields"></a>
### `RecordExportSamples._fields`

只按已登记位置读取一条。

```python
RecordExportSamples._fields(index)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`index`|int|是|无|位置或关键字。当前内部序列的记录索引；读取时检查范围，不把越界当作空输入。|

#### 返回说明

解包字段。

#### 异常说明

越界/短读。

源码：[`src/chronaxis/execution/record_export_samples.py:54`](../../../src/chronaxis/execution/record_export_samples.py#L54)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-RecordExportSamples-_lower"></a>
### `RecordExportSamples._lower`

二分首个不早于time_ns的行。

```python
RecordExportSamples._lower(time_ns)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|位置或关键字。本次操作对应的实际时刻，单位纳秒；必须按输入的单调顺序推进，不是累计的固定周期数。|

#### 返回说明

索引。

#### 异常说明

原读取错。

源码：[`src/chronaxis/execution/record_export_samples.py:63`](../../../src/chronaxis/execution/record_export_samples.py#L63)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-RecordExportSamples-rows"></a>
### `RecordExportSamples.rows`

只回读半开片段内所选样本，不全量核验或扫描。

```python
RecordExportSamples.rows(interval)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`interval`|Interval|是|无|位置或关键字。要处理的实际半开时间范围，包含start_ns而不包含end_ns之后的时长。|

#### 返回说明

迭代器。

#### 异常说明

原读取/模型错。

源码：[`src/chronaxis/execution/record_export_samples.py:72`](../../../src/chronaxis/execution/record_export_samples.py#L72)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-RecordExportSamples-closed"></a>
### `RecordExportSamples.closed`

返回实际资源状态。

```python
RecordExportSamples.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

bool。

#### 异常说明

无。

源码：[`src/chronaxis/execution/record_export_samples.py:85`](../../../src/chronaxis/execution/record_export_samples.py#L85)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-RecordExportSamples-close"></a>
### `RecordExportSamples.close`

关闭自有临时文件并释放定义；不碰原输入。

```python
RecordExportSamples.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

原关闭错，可重试。

源码：[`src/chronaxis/execution/record_export_samples.py:89`](../../../src/chronaxis/execution/record_export_samples.py#L89)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
