# `chronaxis.execution.record_signal_export`

会话信号CSV随同次合并流在线写出；只暂留最后一个所需时刻组。

最后组在真实EOF范围确定后才写，保半开范围而不保存整段信号历史。
线性网格仍使用原SignalGrid；未请求的别名不进入本owner。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Interval](chronaxis.core.models.md#api-Interval)、[RecordExportSamples](chronaxis.execution.record_export_samples.md#api-RecordExportSamples)、[SignalCSVWriter](chronaxis.results.signal_exports.md#api-SignalCSVWriter)

## 对象导航

|对象|用途|
|---|---|
|[`RecordSignalExport`](#api-RecordSignalExport)|拥有一个在线writer和待定末组，借用最终导出索引。|
|[`RecordSignalExport.__init__`](#api-RecordSignalExport-__init__)|预约必要别名状态，不读取文件。|
|[`RecordSignalExport.update_observation`](#api-RecordSignalExport-update_observation)|接收同次读取已见范围，在线writer不会预造末端样本。|
|[`RecordSignalExport._bounds`](#api-RecordSignalExport-_bounds)|只查所选来源实际首末，不扫描输入。|
|[`RecordSignalExport._begin`](#api-RecordSignalExport-_begin)|第一次需要写出时确定真实起点，末端暂以请求上限约束。|
|[`RecordSignalExport._flush`](#api-RecordSignalExport-_flush)|交出上一实际组并释放待定费用。|
|[`RecordSignalExport.observe`](#api-RecordSignalExport-observe)|仅保所选样本的一个完整时刻；不在最新值状态里重复保存导出值。|
|[`RecordSignalExport.finish`](#api-RecordSignalExport-finish)|EOF收紧末端，再交末组和网格，登记唯一输出。|
|[`RecordSignalExport.segment`](#api-RecordSignalExport-segment)|片段确定后只读必要样本，复用同一导出器。|
|[`RecordSignalExport.closed`](#api-RecordSignalExport-closed)|返回资源关闭状态。|
|[`RecordSignalExport.close`](#api-RecordSignalExport-close)|关闭尚未发布writer及末组，保留原输入和借用索引。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import replace
from ..core.models import Interval
from ..sources.can_spec import can_field_from_key
from ..legacy.records import field_to_dict
from ..results.signal_exports import SignalCSVWriter, export_signal_csv
from .record_export_samples import RecordExportSamples
from ..results.budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from .history import _metadata_bytes
```

</details>

<a id="api-RecordSignalExport"></a>
## `RecordSignalExport`

拥有一个在线writer和待定末组，借用最终导出索引。

```python
RecordSignalExport(plan, budget, cursors, exports, path)
```


源码：[`src/chronaxis/execution/record_signal_export.py:16`](../../../src/chronaxis/execution/record_signal_export.py#L16)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordSignalExport-__init__"></a>
### `RecordSignalExport.__init__`

预约必要别名状态，不读取文件。

```python
RecordSignalExport.__init__(plan, budget, cursors, exports, path)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|AnalysisPlan|是|无|位置或关键字。已完成静态解析的分析计划，包含来源、绑定、规则、指标、间隔选择和输出要求。|
|`budget`|ResourceBudget|是|无|位置或关键字。本次分析共享的资源用量记录；新对象先预约所需内存和磁盘额度，关闭时归还自己的内存费用。|
|`cursors`|Sequence[RecordSourceCursor]|是|无|位置或关键字。本次实际打开的来源游标，借用其真实首末时刻和EOF状态；调用方保留关闭责任。|
|`exports`|SignalCSVOutput|是|无|位置或关键字。已解析的信号CSV导出请求，包含列、范围、插值和网格设置。|
|`path`|str &#124; Path|是|无|位置或关键字。本次任务专用路径；只操作本次登记的资源，不能指向原始输入或历史项目目录。|

#### 返回说明

owner。

#### 异常说明

构造原错。

源码：[`src/chronaxis/execution/record_signal_export.py:18`](../../../src/chronaxis/execution/record_signal_export.py#L18)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordSignalExport-update_observation"></a>
### `RecordSignalExport.update_observation`

接收同次读取已见范围，在线writer不会预造末端样本。

```python
RecordSignalExport.update_observation(plan)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|AnalysisPlan|是|无|位置或关键字。更新实际观测范围后的计划，供信号导出结算范围使用。|

#### 返回说明

None。

#### 异常说明

无。

源码：[`src/chronaxis/execution/record_signal_export.py:46`](../../../src/chronaxis/execution/record_signal_export.py#L46)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordSignalExport-_bounds"></a>
### `RecordSignalExport._bounds`

只查所选来源实际首末，不扫描输入。

```python
RecordSignalExport._bounds()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

实际范围或None。

#### 异常说明

无。

源码：[`src/chronaxis/execution/record_signal_export.py:54`](../../../src/chronaxis/execution/record_signal_export.py#L54)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordSignalExport-_begin"></a>
### `RecordSignalExport._begin`

第一次需要写出时确定真实起点，末端暂以请求上限约束。

```python
RecordSignalExport._begin(final=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`final`|bool|否|False|位置或关键字。是否已到真实EOF后的最终处理；True允许收紧观测末端和结束未完成状态。|

#### 返回说明

None。

#### 异常说明

构造原错。

源码：[`src/chronaxis/execution/record_signal_export.py:63`](../../../src/chronaxis/execution/record_signal_export.py#L63)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordSignalExport-_flush"></a>
### `RecordSignalExport._flush`

交出上一实际组并释放待定费用。

```python
RecordSignalExport._flush()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

原写入/清理错。

源码：[`src/chronaxis/execution/record_signal_export.py:76`](../../../src/chronaxis/execution/record_signal_export.py#L76)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordSignalExport-observe"></a>
### `RecordSignalExport.observe`

仅保所选样本的一个完整时刻；不在最新值状态里重复保存导出值。

```python
RecordSignalExport.observe(group)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`group`|DecodedTimeGroup|是|无|位置或关键字。同一实际时刻收齐的所需信号更新；本组全部到齐后再求值，避免来源遍历顺序影响结果。|

#### 返回说明

None。

#### 异常说明

原错。

源码：[`src/chronaxis/execution/record_signal_export.py:82`](../../../src/chronaxis/execution/record_signal_export.py#L82)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordSignalExport-finish"></a>
### `RecordSignalExport.finish`

EOF收紧末端，再交末组和网格，登记唯一输出。

```python
RecordSignalExport.finish()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

原发布错。

源码：[`src/chronaxis/execution/record_signal_export.py:94`](../../../src/chronaxis/execution/record_signal_export.py#L94)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordSignalExport-segment"></a>
### `RecordSignalExport.segment`

片段确定后只读必要样本，复用同一导出器。

```python
RecordSignalExport.segment(segment)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`segment`|CompactSegment|是|无|位置或关键字。已确定的实际窗口片段，包含业务范围及父事件关联，供计算或导出使用。|

#### 返回说明

None。

#### 异常说明

原导出错。

源码：[`src/chronaxis/execution/record_signal_export.py:106`](../../../src/chronaxis/execution/record_signal_export.py#L106)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordSignalExport-closed"></a>
### `RecordSignalExport.closed`

返回资源关闭状态。

```python
RecordSignalExport.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

bool。

#### 异常说明

无。

源码：[`src/chronaxis/execution/record_signal_export.py:122`](../../../src/chronaxis/execution/record_signal_export.py#L122)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordSignalExport-close"></a>
### `RecordSignalExport.close`

关闭尚未发布writer及末组，保留原输入和借用索引。

```python
RecordSignalExport.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

原关闭错。

源码：[`src/chronaxis/execution/record_signal_export.py:126`](../../../src/chronaxis/execution/record_signal_export.py#L126)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
