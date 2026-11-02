# chronaxis.execution.record_exports

只为显式导出接同次读取的帧或样本；复用既有writer和结果发布。

会话范围在真实EOF后确定；片段由窗口消费者直接交付，不复制片段表。
不再次读原日志或解码，默认精简导出不产生逐帧旁表。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ArtifactExportStore](chronaxis.results.artifact_exports.md#api-ArtifactExportStore)、[FrameRebuildRead](chronaxis.results.frame_rebuild.md#api-FrameRebuildRead)、[Interval](chronaxis.core.models.md#api-Interval)、[LegacyFrameSamples](chronaxis.execution.legacy_frame_samples.md#api-LegacyFrameSamples)、[RecordSignalExport](chronaxis.execution.record_signal_export.md#api-RecordSignalExport)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)

## 对象导航

|对象|用途|
|---|---|
|[`RecordExports`](#api-RecordExports)|拥有导出索引、在线信号写出与当前帧游标；原帧仓由来源游标所有。|
|[`RecordExports.__init__`](#api-RecordExports-__init__)|建立仅显式请求的索引。|
|[`RecordExports._require_clock`](#api-RecordExports-_require_clock)|多来源片段须有可比时钟；单来源不强求映射。|
|[`RecordExports._export`](#api-RecordExports-_export)|借同次封口原帧写一份所需输出。|
|[`RecordExports.session`](#api-RecordExports-session)|EOF后裁实际会话范围，空输入保持空输出。|
|[`RecordExports.segment`](#api-RecordExports-segment)|直接接最终片段，不保存第二份片段历史。|
|[`RecordExports.seal`](#api-RecordExports-seal)|全部请求完成后封索引。|
|[`RecordExports.take_exports`](#api-RecordExports-take_exports)|唯一移交已完成结果；失败前责任仍可达。|
|[`RecordExports.closed`](#api-RecordExports-closed)|返回实际关闭状态。|
|[`RecordExports.close`](#api-RecordExports-close)|先关当前输出及索引，再释放自有状态；不关闭借用原帧。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..core.models import Interval
from .record_signal_export import RecordSignalExport
from .legacy_frame_samples import LegacyFrameSamples
from ..results.frame_rebuild import FrameRebuildRead
from ..results.artifact_exports import ArtifactExportStore
from ..results.frame_exports import export_can_frames
from ..results.errors import ResultClosedError
from ..results.budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
```

</details>

<a id="api-RecordExports"></a>
## `RecordExports`

拥有导出索引、在线信号写出与当前帧游标；原帧仓由来源游标所有。

```python
RecordExports(plan, budget, path, cursors)
```


源码：[`src/chronaxis/execution/record_exports.py:16`](../../../src/chronaxis/execution/record_exports.py#L16)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordExports-__init__"></a>
### `RecordExports.__init__`

建立仅显式请求的索引。

```python
RecordExports.__init__(plan, budget, path, cursors)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|AnalysisPlan|是|无|位置或关键字。已完成静态解析的分析计划，包含来源、绑定、规则、指标、间隔选择和输出要求。|
|`budget`|ResourceBudget|是|无|位置或关键字。本次分析共享的资源用量记录；新对象先预约所需内存和磁盘额度，关闭时归还自己的内存费用。|
|`path`|str &#124; Path|是|无|位置或关键字。本次任务专用路径；只操作本次登记的资源，不能指向原始输入或历史项目目录。|
|`cursors`|Sequence[RecordSourceCursor]|是|无|位置或关键字。本次实际打开的来源游标，借用其真实首末时刻和EOF状态；调用方保留关闭责任。|

#### 返回说明

owner。

#### 异常说明

原构造错。

源码：[`src/chronaxis/execution/record_exports.py:18`](../../../src/chronaxis/execution/record_exports.py#L18)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordExports-_require_clock"></a>
### `RecordExports._require_clock`

多来源片段须有可比时钟；单来源不强求映射。

```python
RecordExports._require_clock()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

缺同步依据。

源码：[`src/chronaxis/execution/record_exports.py:40`](../../../src/chronaxis/execution/record_exports.py#L40)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordExports-_export"></a>
### `RecordExports._export`

借同次封口原帧写一份所需输出。

```python
RecordExports._export(actual, segment_id=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`actual`|[Interval](chronaxis.core.models.md#api-Interval) &#124; None|是|无|位置或关键字。裁剪后实际可用的半开范围；None表示没有可导出的交集。|
|`segment_id`|str &#124; None|否|None|位置或关键字。所处理的片段id；会话导出没有父片段，使用None。|

#### 返回说明

None。

#### 异常说明

原消费/发布错。

源码：[`src/chronaxis/execution/record_exports.py:70`](../../../src/chronaxis/execution/record_exports.py#L70)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordExports-session"></a>
### `RecordExports.session`

EOF后裁实际会话范围，空输入保持空输出。

```python
RecordExports.session()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

原导出错。

源码：[`src/chronaxis/execution/record_exports.py:111`](../../../src/chronaxis/execution/record_exports.py#L111)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordExports-segment"></a>
### `RecordExports.segment`

直接接最终片段，不保存第二份片段历史。

```python
RecordExports.segment(segment)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`segment`|CompactSegment|是|无|位置或关键字。已确定的实际窗口片段，包含业务范围及父事件关联，供计算或导出使用。|

#### 返回说明

None。

#### 异常说明

原导出错。

源码：[`src/chronaxis/execution/record_exports.py:123`](../../../src/chronaxis/execution/record_exports.py#L123)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordExports-seal"></a>
### `RecordExports.seal`

全部请求完成后封索引。

```python
RecordExports.seal()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

原封口错。

源码：[`src/chronaxis/execution/record_exports.py:129`](../../../src/chronaxis/execution/record_exports.py#L129)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordExports-take_exports"></a>
### `RecordExports.take_exports`

唯一移交已完成结果；失败前责任仍可达。

```python
RecordExports.take_exports(receiver)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`receiver`|[ArtifactExportStore](chronaxis.results.artifact_exports.md#api-ArtifactExportStore)|是|无|位置或关键字。接收已经完成导出文件所有权的结果仓；移交后由接收者负责发布及关闭。|

#### 返回说明

None。

#### 异常说明

状态错。

源码：[`src/chronaxis/execution/record_exports.py:133`](../../../src/chronaxis/execution/record_exports.py#L133)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordExports-closed"></a>
### `RecordExports.closed`

返回实际关闭状态。

```python
RecordExports.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

bool。

#### 异常说明

无。

源码：[`src/chronaxis/execution/record_exports.py:144`](../../../src/chronaxis/execution/record_exports.py#L144)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-RecordExports-close"></a>
### `RecordExports.close`

先关当前输出及索引，再释放自有状态；不关闭借用原帧。

```python
RecordExports.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

原关闭错。

源码：[`src/chronaxis/execution/record_exports.py:148`](../../../src/chronaxis/execution/record_exports.py#L148)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
