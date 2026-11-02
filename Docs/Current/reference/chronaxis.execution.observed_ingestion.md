# chronaxis.execution.observed_ingestion

一边读取来源，一边把信号写入本次历史文件，同时保存实际行数和起止时间。读取记录与历史文件属于同一次运行，后续可据此核对结果使用的输入。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisError](chronaxis.results.errors.md#api-AnalysisError)、[BudgetedLegacyCANSourceAdapter](chronaxis.execution.can_reader.md#api-BudgetedLegacyCANSourceAdapter)、[BudgetedMemorySourceAdapter](chronaxis.execution.memory_reader.md#api-BudgetedMemorySourceAdapter)、[BudgetedSignalCSVSourceAdapter](chronaxis.execution.csv_reader.md#api-BudgetedSignalCSVSourceAdapter)、[BudgetedTextCANSourceAdapter](chronaxis.execution.text_can_reader.md#api-BudgetedTextCANSourceAdapter)、[CANObservationRead](chronaxis.execution.can_reader.md#api-CANObservationRead)、[CANTextSpec](chronaxis.sources.text_can_spec.md#api-CANTextSpec)、[CSVObservationRead](chronaxis.execution.csv_observation.md#api-CSVObservationRead)、[DecodedHistoryStore](chronaxis.execution.history.md#api-DecodedHistoryStore)、[LegacyCANSpec](chronaxis.sources.can_spec.md#api-LegacyCANSpec)、[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[SignalCSVSpec](chronaxis.sources.csv_spec.md#api-SignalCSVSpec)、[SourcePlan](chronaxis.planning.models.md#api-SourcePlan)、[SourceSpec](chronaxis.core.models.md#api-SourceSpec)、[TextCANObservationRead](chronaxis.execution.text_can_reader.md#api-TextCANObservationRead)

## 对象导航

|对象|用途|
|---|---|
|[`SourceScanObservation`](#api-SourceScanObservation)|保留本scan实际原行事实及来源声明允许的观测范围，不证明来源之间同步。|
|[`SourceScanObservation.__post_init__`](#api-SourceScanObservation-__post_init__)|检查事实内部一致性，不读文件、扩展范围或补假设周期。|
|[`ObservedSourceScan`](#api-ObservedSourceScan)|拥有单个真实read及有限扫描快照，借用历史、来源和计划但不关闭它们。|
|[`ObservedSourceScan.__init__`](#api-ObservedSourceScan-__init__)|核对空的building来源及原对象关系，先预约有限合同，不开始读取。|
|[`ObservedSourceScan._require_contract`](#api-ObservedSourceScan-_require_contract)|在每次读取和追加边界核对原来源对象、描述、请求与本source预期写入。|
|[`ObservedSourceScan._adopt_cleanup`](#api-ObservedSourceScan-_adopt_cleanup)|接管实际未返回的最高来源读取owner，不接借用来源或历史。|
|[`ObservedSourceScan._close_read`](#api-ObservedSourceScan-_close_read)|结束本scan实际read，成功后才清字段，不影响adapter的其他read。|
|[`ObservedSourceScan.consume`](#api-ObservedSourceScan-consume)|单次扫描真实来源并把每个原batch直接写入同一history，成功后开放快照。|
|[`ObservedSourceScan._ensure_active`](#api-ObservedSourceScan-_ensure_active)|拒绝关闭、清理或失败后的读取及事实访问。|
|[`ObservedSourceScan._require_finished`](#api-ObservedSourceScan-_require_finished)|仅接受活的成功scan提供数据流快照。|
|[`ObservedSourceScan.capture_message_updates`](#api-ObservedSourceScan-capture_message_updates)|读取本scan原来源的消息捕获开关，不据此开放完成证明。|
|[`ObservedSourceScan.history`](#api-ObservedSourceScan-history)|读取原历史对象。|
|[`ObservedSourceScan.source_plan`](#api-ObservedSourceScan-source_plan)|读取原来源计划。|
|[`ObservedSourceScan.request`](#api-ObservedSourceScan-request)|读取本次原request。|
|[`ObservedSourceScan.finished`](#api-ObservedSourceScan-finished)|查看本次操作是否已经成功完成。|
|[`ObservedSourceScan.closed`](#api-ObservedSourceScan-closed)|查看本对象负责的资源是否已经全部关闭。|
|[`ObservedSourceScan.failed`](#api-ObservedSourceScan-failed)|查看本次操作是否已经失败。|
|[`ObservedSourceScan.history_sha256`](#api-ObservedSourceScan-history_sha256)|读取本source完成写入时的历史SHA。|
|[`ObservedSourceScan.counts`](#api-ObservedSourceScan-counts)|读取进度数及样本数。|
|[`ObservedSourceScan.observation`](#api-ObservedSourceScan-observation)|读取本scan完成的原行及观测范围事实。|
|[`ObservedSourceScan.runtime_metadata`](#api-ObservedSourceScan-runtime_metadata)|读取成功CAN扫描的同次READY。|
|[`ObservedSourceScan.read_identity`](#api-ObservedSourceScan-read_identity)|读取成功CAN扫描的原read身份。|
|[`ObservedSourceScan.take_raw_store`](#api-ObservedSourceScan-take_raw_store)|把同次原帧仓先装入真实父槽再解除本责任，取消时仍有可达owner。|
|[`ObservedSourceScan.take_message_store`](#api-ObservedSourceScan-take_message_store)|把实际同次decoded仓先安装接收父，再结束本scan唯一子责任。|
|[`ObservedSourceScan.close`](#api-ObservedSourceScan-close)|关闭本scan的read、未移交仓和费用，保留借用来源、历史及磁盘文件。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from ..core.models import SourceSpec
from ..core.validation import require_identifier
from ..timebase.conversion import checked_add_ns, require_int64_ns
from ..planning.models import SourcePlan
from ..sources.csv_spec import SignalCSVSpec
from ..sources.can_spec import LegacyCANSpec
from ..sources.text_can_spec import CANTextSpec
from .text_can_reader import BudgetedTextCANSourceAdapter, TextCANObservationRead
from ..sources.models import ReadRequest
from ..results.errors import AnalysisError, ResultClosedError
from ..results.spool import _cleanup_owner, _reserve_owned_ram, _release_owned_ram
from .csv_observation import CSVObservationRead
from .csv_reader import BudgetedSignalCSVSourceAdapter
from .can_reader import BudgetedLegacyCANSourceAdapter, CANObservationRead
from .memory_reader import BudgetedMemorySourceAdapter
from .history import DecodedHistoryStore, _metadata_bytes
```

</details>

<a id="api-SourceScanObservation"></a>
## `SourceScanObservation`

保留本scan实际原行事实及来源声明允许的观测范围，不证明来源之间同步。

first_ns、last_ns及row_count描述原行；observed_start_ns、observed_end_ns
保留描述与实际完成进度。空来源仍可有声明边界，但row_count必须为0且原行
首末均为None，后继不能把声明边界解释成真实原行或常量规则的观测证据。

```python
class SourceScanObservation
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|str|是|无|实际来源名称。|
|`session_id`|str|是|无|原请求与完成进度的同一会话。|
|`first_ns`|int &#124; None|是|无|实际首条原时间行，转换及offset后的整数ns。|
|`last_ns`|int &#124; None|是|无|实际末条原时间行，全空为None。|
|`row_count`|int|是|无|原时间行总数，包含空投影行而不按信号样本数计算。|
|`observed_start_ns`|int &#124; None|是|无|明确描述start优先，否则实际first。|
|`observed_end_ns`|int &#124; None|是|无|实际EOF进度的observed_end，已完成一次时钟映射。|
|`source_eof`|bool|是|无|完整来源耗尽并已写入本history，必须为True。|
|`time_scope`|str|否|'source'|`"none"`：本次未收集时间范围；`"selected"`：范围只基于选中的报文；`"source"`：范围基于整个来源。selected的首末时间不代表整个文件的首末时间。|
|`retained_record_count`|int|否|0|所需记录数，用于解释稀疏时间范围。|
|`full_check_count`|int|否|0|非原生输入完整检查回退数。|

源码：[`src/chronaxis/execution/observed_ingestion.py:50`](../../../src/chronaxis/execution/observed_ingestion.py#L50)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-SourceScanObservation-__post_init__"></a>
### `SourceScanObservation.__post_init__`

检查事实内部一致性，不读文件、扩展范围或补假设周期。

```python
SourceScanObservation.__post_init__()
```

参数：无显式参数。


#### 参数说明

无，读取创建后不可修改的字段。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

类型、行数、端点或EOF矛盾。

本函数直接报告的具体错误：

- `ValueError`：来源扫描事实需非负原生行数及完整EOF。
- `ValueError`：来源保留记录/完整回退计数非法。
- `ValueError`：来源时间范围非法。
- `ValueError`：来源扫描观测范围不能回退。
- `ValueError`：部分或未采集时间不能声明全来源范围。
- `ValueError`：无时间来源不能声明首末。
- `ValueError`：目标记录首末时间不一致。
- `ValueError`：全空扫描的原行首末须为None。
- `ValueError`：非空扫描需有序原行首末及包含它们的实际观测边界。
- `ValueError`：没有目标记录不能声明目标首末时间。
- `ValueError`：存在目标记录时必须保留目标首末时间。

源码：[`src/chronaxis/execution/observed_ingestion.py:70`](../../../src/chronaxis/execution/observed_ingestion.py#L70)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ObservedSourceScan"></a>
## `ObservedSourceScan`

拥有单个真实read及有限扫描快照，借用历史、来源和计划但不关闭它们。

_expected_counts和_expected_sha只跟踪本source的成功写入，consume不向外
交付批次。_finished须在真实耗尽与read关闭后设置；失败或半关闭需要调用close关闭资源。
固定费用覆盖描述、请求及所有有限快照，直到显式close才释放。

```python
ObservedSourceScan(history, source_plan, adapter, request)
```


源码：[`src/chronaxis/execution/observed_ingestion.py:116`](../../../src/chronaxis/execution/observed_ingestion.py#L116)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ObservedSourceScan-__init__"></a>
### `ObservedSourceScan.__init__`

核对空的building来源及原对象关系，先预约有限合同，不开始读取。

```python
ObservedSourceScan.__init__(history, source_plan, adapter, request)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`history`|[DecodedHistoryStore](chronaxis.execution.history.md#api-DecodedHistoryStore)|是|无|位置或关键字。history为实际DecodedHistoryStore；request须是history使用的原对象。|
|`source_plan`|[SourcePlan](chronaxis.planning.models.md#api-SourcePlan)|是|无|位置或关键字。source_plan为原SourcePlan|
|`adapter`|[BudgetedLegacyCANSourceAdapter](chronaxis.execution.can_reader.md#api-BudgetedLegacyCANSourceAdapter) &#124; [BudgetedTextCANSourceAdapter](chronaxis.execution.text_can_reader.md#api-BudgetedTextCANSourceAdapter) &#124; [BudgetedMemorySourceAdapter](chronaxis.execution.memory_reader.md#api-BudgetedMemorySourceAdapter) &#124; [BudgetedSignalCSVSourceAdapter](chronaxis.execution.csv_reader.md#api-BudgetedSignalCSVSourceAdapter)|是|无|位置或关键字。adapter     为同budget实际预算memory、CSV、旧CAN或新文本CAN来源|
|`request`|[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)|是|无|位置或关键字。request须是history使用的原对象。|

#### 返回说明

尚未扫描的owner。

#### 异常说明

合同、类型、预算或取消原错；持续构造清理失败
    附observed_source_scan_cleanup_owner，恢复后调用其close。

本函数直接报告的具体错误：

- `TypeError`：来源扫描需实际历史、SourcePlan、预算来源及原ReadRequest。
- `ValueError`：来源扫描需属于同一历史及共享budget。
- `ValueError`：来源扫描需原request及尚无append或EOF的历史来源。

源码：[`src/chronaxis/execution/observed_ingestion.py:124`](../../../src/chronaxis/execution/observed_ingestion.py#L124)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ObservedSourceScan-_require_contract"></a>
### `ObservedSourceScan._require_contract`

在每次读取和追加边界核对原来源对象、描述、请求与本source预期写入。

```python
ObservedSourceScan._require_contract()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原生命周期错误，或ValueError为替换、外部追加或合同变化。

本函数直接报告的具体错误：

- `ValueError`：扫描来源或历史的实际共享budget已被替换。
- `ValueError`：扫描历史的原validator、request、计数或摘要已被其他写入替换。
- `ValueError`：扫描来源原config、会话或实际描述与历史合同不一致。
- `ValueError`：扫描CAN来源的原消息捕获开关已改变。
- `ValueError`：文本CAN原帧保存选择已改变。

源码：[`src/chronaxis/execution/observed_ingestion.py:176`](../../../src/chronaxis/execution/observed_ingestion.py#L176)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ObservedSourceScan-_adopt_cleanup"></a>
### `ObservedSourceScan._adopt_cleanup`

接管实际未返回的最高来源读取owner，不接借用来源或历史。

```python
ObservedSourceScan._adopt_cleanup(exc)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`exc`|BaseException|是|无|位置或关键字。本次操作的原异常，供附加关闭失败信息并保留原因链。不要用错误字符串代替异常对象。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

无预期异常。

源码：[`src/chronaxis/execution/observed_ingestion.py:217`](../../../src/chronaxis/execution/observed_ingestion.py#L217)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ObservedSourceScan-_close_read"></a>
### `ObservedSourceScan._close_read`

结束本scan实际read，成功后才清字段，不影响adapter的其他read。

```python
ObservedSourceScan._close_read()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原read关闭错误；旧memory未完成费用明确拒绝。

本函数直接报告的具体错误：

- `AnalysisError`：原memory读取仍有未完成清理费用，来源扫描不能声明完成。

源码：[`src/chronaxis/execution/observed_ingestion.py:233`](../../../src/chronaxis/execution/observed_ingestion.py#L233)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ObservedSourceScan-consume"></a>
### `ObservedSourceScan.consume`

单次扫描真实来源并把每个原batch直接写入同一history，成功后开放快照。

```python
ObservedSourceScan.consume()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None，重复调用已完成scan不重读。

#### 异常说明

原读取、历史追加、预算、来源变化或关闭错误；failed后只可close，原错附最高恢复owner。

本函数直接报告的具体错误：

- `ResultClosedError`：来源扫描consume已开始，不能重入同一读取。
- `ValueError`：来源扫描没有本历史实际完整EOF进度。
- `TypeError`：CSV扫描必须使用实际CSVObservationRead。
- `ValueError`：扫描read交付了另一来源或会话的batch。
- `ValueError`：来源扫描实际历史追加计数未对应唯一原batch。
- `ValueError`：来源实际读取事实与同一次历史EOF不一致。
- `TypeError`：文本CAN扫描必须使用真实TextCANObservationRead。
- `ValueError`：同次CAN原read的消息捕获开关不符。
- `TypeError`：CAN扫描必须使用本adapter对应的实际read。
- `ValueError`：同次文本原帧仓与实际观测身份不符。
- `ValueError`：同次CAN原帧仓与真实扫描完成事实不一致。
- `ValueError`：同次CAN消息仓与原读取及真实扫描事实不一致。

源码：[`src/chronaxis/execution/observed_ingestion.py:247`](../../../src/chronaxis/execution/observed_ingestion.py#L247)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ObservedSourceScan-_ensure_active"></a>
### `ObservedSourceScan._ensure_active`

拒绝关闭、清理或失败后的读取及事实访问。

```python
ObservedSourceScan._ensure_active()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ResultClosedError为本owner不可用。

本函数直接报告的具体错误：

- `ResultClosedError`：来源扫描已关闭、正在清理或失败。

源码：[`src/chronaxis/execution/observed_ingestion.py:369`](../../../src/chronaxis/execution/observed_ingestion.py#L369)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ObservedSourceScan-_require_finished"></a>
### `ObservedSourceScan._require_finished`

仅接受活的成功scan提供数据流快照。

```python
ObservedSourceScan._require_finished()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ResultClosedError。

本函数直接报告的具体错误：

- `ResultClosedError`：来源扫描尚未正常完成。

源码：[`src/chronaxis/execution/observed_ingestion.py:378`](../../../src/chronaxis/execution/observed_ingestion.py#L378)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ObservedSourceScan-capture_message_updates"></a>
### `ObservedSourceScan.capture_message_updates`

读取本scan原来源的消息捕获开关，不据此开放完成证明。

```python
ObservedSourceScan.capture_message_updates
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

原生bool；非CAN来源为False，关闭后仍保配置快照。

#### 异常说明

无；readonly属性不能把尚未完成的消息仓改成可移交。

源码：[`src/chronaxis/execution/observed_ingestion.py:387`](../../../src/chronaxis/execution/observed_ingestion.py#L387)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ObservedSourceScan-history"></a>
### `ObservedSourceScan.history`

读取原历史对象。

```python
ObservedSourceScan.history
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

DecodedHistoryStore。

#### 异常说明

ResultClosedError为不可用。

源码：[`src/chronaxis/execution/observed_ingestion.py:396`](../../../src/chronaxis/execution/observed_ingestion.py#L396)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ObservedSourceScan-source_plan"></a>
### `ObservedSourceScan.source_plan`

读取原来源计划。

```python
ObservedSourceScan.source_plan
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

SourcePlan。

#### 异常说明

ResultClosedError为不可用。

源码：[`src/chronaxis/execution/observed_ingestion.py:403`](../../../src/chronaxis/execution/observed_ingestion.py#L403)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ObservedSourceScan-request"></a>
### `ObservedSourceScan.request`

读取本次原request。

```python
ObservedSourceScan.request
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

ReadRequest。

#### 异常说明

ResultClosedError为不可用。

源码：[`src/chronaxis/execution/observed_ingestion.py:410`](../../../src/chronaxis/execution/observed_ingestion.py#L410)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ObservedSourceScan-finished"></a>
### `ObservedSourceScan.finished`

查看本次操作是否已经成功完成。

```python
ObservedSourceScan.finished
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示规定的处理步骤已全部完成；False表示尚未完成。完成处理和关闭资源是两个独立状态。

#### 异常说明

无。

源码：[`src/chronaxis/execution/observed_ingestion.py:417`](../../../src/chronaxis/execution/observed_ingestion.py#L417)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ObservedSourceScan-closed"></a>
### `ObservedSourceScan.closed`

查看本对象负责的资源是否已经全部关闭。

```python
ObservedSourceScan.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/execution/observed_ingestion.py:423`](../../../src/chronaxis/execution/observed_ingestion.py#L423)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ObservedSourceScan-failed"></a>
### `ObservedSourceScan.failed`

查看本次操作是否已经失败。

```python
ObservedSourceScan.failed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象已记录处理失败；False表示尚未记录失败。

#### 异常说明

无。

源码：[`src/chronaxis/execution/observed_ingestion.py:429`](../../../src/chronaxis/execution/observed_ingestion.py#L429)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ObservedSourceScan-history_sha256"></a>
### `ObservedSourceScan.history_sha256`

读取本source完成写入时的历史SHA。

```python
ObservedSourceScan.history_sha256
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

str。

#### 异常说明

对象处于下列状态时抛ResultClosedError：来源扫描尚未正常完成。

源码：[`src/chronaxis/execution/observed_ingestion.py:435`](../../../src/chronaxis/execution/observed_ingestion.py#L435)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ObservedSourceScan-counts"></a>
### `ObservedSourceScan.counts`

读取进度数及样本数。

```python
ObservedSourceScan.counts
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

二元素int tuple。

#### 异常说明

对象处于下列状态时抛ResultClosedError：来源扫描尚未正常完成。

源码：[`src/chronaxis/execution/observed_ingestion.py:442`](../../../src/chronaxis/execution/observed_ingestion.py#L442)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ObservedSourceScan-observation"></a>
### `ObservedSourceScan.observation`

读取本scan完成的原行及观测范围事实。

```python
ObservedSourceScan.observation
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

SourceScanObservation。

#### 异常说明

对象处于下列状态时抛ResultClosedError：来源扫描尚未正常完成。

源码：[`src/chronaxis/execution/observed_ingestion.py:449`](../../../src/chronaxis/execution/observed_ingestion.py#L449)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ObservedSourceScan-runtime_metadata"></a>
### `ObservedSourceScan.runtime_metadata`

读取成功CAN扫描的同次READY。

```python
ObservedSourceScan.runtime_metadata
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

冻结映射。

#### 异常说明

非CAN或未完成。

本函数直接报告的具体错误：

- `ValueError`：此来源没有CAN运行元数据。

源码：[`src/chronaxis/execution/observed_ingestion.py:456`](../../../src/chronaxis/execution/observed_ingestion.py#L456)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ObservedSourceScan-read_identity"></a>
### `ObservedSourceScan.read_identity`

读取成功CAN扫描的原read身份。

```python
ObservedSourceScan.read_identity
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

str。

#### 异常说明

非CAN或未完成。

本函数直接报告的具体错误：

- `ValueError`：此来源没有CAN读取身份。

源码：[`src/chronaxis/execution/observed_ingestion.py:465`](../../../src/chronaxis/execution/observed_ingestion.py#L465)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ObservedSourceScan-take_raw_store"></a>
### `ObservedSourceScan.take_raw_store`

把同次原帧仓先装入真实父槽再解除本责任，取消时仍有可达owner。

```python
ObservedSourceScan.take_raw_store(receiver, slot='_raw_store')
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`receiver`|资源接收对象|是|无|位置或关键字。接收当前资源所有权的父对象；其_budget必须与发送方相同，指定的接收属性必须为空。接收后由父对象负责close()和归还资源额度。|
|`slot`|str|否|'_raw_store'|位置或关键字。当前对象中用于保存资源或其费用的属性名，例如"_row_cost"；只能指向本对象实际管理的项。释放成功后才清空对应项。|

#### 返回说明

原RawFrameStore。

#### 异常说明

未完成、重复移交、预算或接收槽错误；安装后取消不丢父槽。

本函数直接报告的具体错误：

- `ValueError`：原帧仓移交需同预算空父槽且只能一次。

源码：[`src/chronaxis/execution/observed_ingestion.py:473`](../../../src/chronaxis/execution/observed_ingestion.py#L473)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ObservedSourceScan-take_message_store"></a>
### `ObservedSourceScan.take_message_store`

把实际同次decoded仓先安装接收父，再结束本scan唯一子责任。

```python
ObservedSourceScan.take_message_store(receiver, slot='_message_store')
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`receiver`|资源接收对象|是|无|位置或关键字。接收当前资源所有权的父对象；其_budget必须与发送方相同，指定的接收属性必须为空。接收后由父对象负责close()和归还资源额度。|
|`slot`|str|否|'_message_store'|位置或关键字。当前对象中用于保存资源或其费用的属性名，例如"_row_cost"；只能指向本对象实际管理的项。释放成功后才清空对应项。|

#### 返回说明

原DecodedMessageStore；只能在真实finished后成功移交一次。

#### 异常说明

未完成/已关闭错误，ValueError为未开启、已移交或接收槽不符；
    安装前后取消保原异常和observed_source_scan_cleanup_owner。

源码：[`src/chronaxis/execution/observed_ingestion.py:492`](../../../src/chronaxis/execution/observed_ingestion.py#L492)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ObservedSourceScan-close"></a>
### `ObservedSourceScan.close`

关闭本scan的read、未移交仓和费用，保留借用来源、历史及磁盘文件。

```python
ObservedSourceScan.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None。关闭成功后再次调用不会重复释放同一份资源。

#### 异常说明

原read或预算取消，未完责任保留供同一owner重试。

本函数直接报告的具体错误：

- `AnalysisError`：CAN原帧仓尚未完成关闭。
- `AnalysisError`：CAN消息仓尚未完成关闭。

源码：[`src/chronaxis/execution/observed_ingestion.py:517`](../../../src/chronaxis/execution/observed_ingestion.py#L517)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
