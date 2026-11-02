# chronaxis.execution.scanned_signal_proof

为只需要逐消息累计的CAN任务记录实际完成的读取检查。当后续不需要普通信号历史时，无需额外保存一份无人读取的样本文件；完成信息仍按实际扫描情况记录。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisError](chronaxis.results.errors.md#api-AnalysisError)、[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)、[BatchValidator](chronaxis.sources.protocol.md#api-BatchValidator)、[BudgetedLegacyCANSourceAdapter](chronaxis.execution.can_reader.md#api-BudgetedLegacyCANSourceAdapter)、[CANBatchObservationRead](chronaxis.execution.can_batch_reader.md#api-CANBatchObservationRead)、[HistoryProgress](chronaxis.execution.history_records.md#api-HistoryProgress)、[HistorySample](chronaxis.execution.history_records.md#api-HistorySample)、[QualityFlag](chronaxis.core.types.md#api-QualityFlag)、[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[ResultFormatError](chronaxis.results.errors.md#api-ResultFormatError)、[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)、[SignalBatch](chronaxis.sources.models.md#api-SignalBatch)、[SignalDType](chronaxis.core.types.md#api-SignalDType)、[SourcePlan](chronaxis.planning.models.md#api-SourcePlan)、[SourceScanObservation](chronaxis.execution.observed_ingestion.md#api-SourceScanObservation)

## 对象导航

|对象|用途|
|---|---|
|[`can_message_only`](#api-can_message_only)|选择没有普通样本消费者的全CAN计划。|
|[`_source_contract`](#api-_source_contract)|提取有限原CAN配置事实供替换检查。|
|[`ScannedSignalFacts`](#api-ScannedSignalFacts)|保存已完成首遍验证的有限事实；stream摘要不声称有对应磁盘文件。|
|[`ScannedInputFacts`](#api-ScannedInputFacts)|记录纯消息读取的实际输入摘要，不声称生成或验证过普通信号样本。|
|[`ScannedCANSignals`](#api-ScannedCANSignals)|拥有一个实际CAN read、有限验证状态和未移交消息仓，不拥有普通历史文件。|
|[`ScannedCANSignals.__init__`](#api-ScannedCANSignals-__init__)|核实际投影和原来源后预付状态。|
|[`ScannedCANSignals._require_contract`](#api-ScannedCANSignals-_require_contract)|核原对象与实际本流状态，完成后不再访问已关闭adapter。|
|[`ScannedCANSignals._digest_record`](#api-ScannedCANSignals-_digest_record)|编码一条原规范记录并更新流摘要。|
|[`ScannedCANSignals._release_temporary`](#api-ScannedCANSignals-_release_temporary)|归还实际临时费，清理错误不覆盖主错。|
|[`ScannedCANSignals._accept`](#api-ScannedCANSignals-_accept)|按原历史顺序验证并编码一批，不写磁盘。|
|[`ScannedCANSignals._adopt`](#api-ScannedCANSignals-_adopt)|接实际未返回的read，避免丢失构造失败资源。|
|[`ScannedCANSignals._close_read`](#api-ScannedCANSignals-_close_read)|关闭本次真实read，失败保留责任。|
|[`ScannedCANSignals.consume`](#api-ScannedCANSignals-consume)|完整扫描一次并在真实EOF和关闭后发布证明。|
|[`ScannedCANSignals.assert_current`](#api-ScannedCANSignals-assert_current)|核活的完整扫描与调用者原合同。|
|[`ScannedCANSignals.facts`](#api-ScannedCANSignals-facts)|借读真实完成的扫描事实。|
|[`ScannedCANSignals.observation`](#api-ScannedCANSignals-observation)|读取全部原帧观测。|
|[`ScannedCANSignals.runtime_metadata`](#api-ScannedCANSignals-runtime_metadata)|借读同次READY。|
|[`ScannedCANSignals.read_identity`](#api-ScannedCANSignals-read_identity)|读取同次真实read标识。|
|[`ScannedCANSignals.capture_message_updates`](#api-ScannedCANSignals-capture_message_updates)|读取原捕获开关。|
|[`ScannedCANSignals.closed`](#api-ScannedCANSignals-closed)|读取实际关闭状态。|
|[`ScannedCANSignals.finished`](#api-ScannedCANSignals-finished)|读取成功扫描事实，不代替当前活性检查。|
|[`ScannedCANSignals.take_message_store`](#api-ScannedCANSignals-take_message_store)|先安装父实际槽再解除本消息仓责任。|
|[`ScannedCANSignals.close`](#api-ScannedCANSignals-close)|关闭真实read/未移交仓后归还本owner费用。|
|[`_ScannedBindings`](#api-_ScannedBindings)|仅用于纯消息运行清单的已扫描定义，不能交给普通历史表达式执行入口。|
|[`_ScannedBindings.signals`](#api-_ScannedBindings-signals)|借用全部原信号定义。|
|[`_ScannedBindings.resolve`](#api-_ScannedBindings-resolve)|解析原定义供清单角色核对。|
|[`ScannedBindingLease`](#api-ScannedBindingLease)|拥有已完成扫描的有限运行清单证明；借用scan但不关闭它们。|
|[`ScannedBindingLease.__init__`](#api-ScannedBindingLease-__init__)|核真实扫描后建立版本化绑定摘要。|
|[`ScannedBindingLease.bindings`](#api-ScannedBindingLease-bindings)|借读当前完整扫描绑定，拒绝失效scan。|
|[`ScannedBindingLease.closed`](#api-ScannedBindingLease-closed)|读取真实关闭状态。|
|[`ScannedBindingLease.close`](#api-ScannedBindingLease-close)|释放自有证明，不关闭借用scan。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from collections.abc import Mapping
from hashlib import sha256
from ..core.numeric import ScalarValue
from ..core.types import QualityFlag, SignalDType
from ..planning.plan import AnalysisPlan
from ..planning.models import SourcePlan
from ..planning.input_requirements import collect_input_requirements
from ..results.errors import AnalysisError, ResultClosedError, ResultFormatError
from ..results.spool import _cleanup_owner, _reserve_owned_ram, _release_owned_ram
from ..sources.models import ReadRequest, SignalBatch
from ..sources.protocol import BatchValidator
from .bindings import _fingerprint, require_decoded_source_contract
from .can_reader import BudgetedLegacyCANSourceAdapter
from .can_batch_reader import CANBatchObservationRead
from .history import _metadata_bytes, _pending_bytes, _batch_bytes
from .history_records import HistorySample, HistoryProgress, estimate_record_bytes, encode_record
from .observed_ingestion import SourceScanObservation
```

</details>

<a id="api-can_message_only"></a>
## `can_message_only`

选择没有普通样本消费者的全CAN计划。

```python
can_message_only(plan)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)|是|无|位置或关键字。本次冻结AnalysisPlan，提供来源、规则、范围与执行预算。|

### 返回说明

True表示计划中的来源全是CAN，且没有后续计算需要普通信号样本历史；False表示不满足这些条件。

### 异常说明

错误模型属性错误。

源码：[`src/chronaxis/execution/scanned_signal_proof.py:35`](../../../src/chronaxis/execution/scanned_signal_proof.py#L35)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_source_contract"></a>
## `_source_contract`

提取有限原CAN配置事实供替换检查。

```python
_source_contract(source)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|[SourcePlan](chronaxis.planning.models.md#api-SourcePlan)|是|无|位置或关键字。原SourcePlan声明，必须与同次真实扫描和绑定一致。|

### 返回说明

冻结tuple。

### 异常说明

非CAN属性错误。

源码：[`src/chronaxis/execution/scanned_signal_proof.py:42`](../../../src/chronaxis/execution/scanned_signal_proof.py#L42)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ScannedSignalFacts"></a>
## `ScannedSignalFacts`

保存已完成首遍验证的有限事实；stream摘要不声称有对应磁盘文件。

```python
class ScannedSignalFacts
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|str|是|无|原SourcePlan声明，必须与同次真实扫描和绑定一致。|
|`session_id`|str|是|无|所属会话的唯一标识，必须与本次计划/来源一致。|
|`source_contract_sha256`|str|是|无|来源配置契约的SHA-256摘要，用于发现声明被替换。|
|`description_sha256`|str|是|无|同次来源描述的SHA-256摘要。|
|`request_sha256`|str|是|无|实际读取请求的SHA-256摘要。|
|`stream_sha256`|str|是|无|按原顺序编码的实际样本/进度流摘要，不表示一定存在对应磁盘文件。|
|`progress_count`|int|是|无|扫描中接受的进度记录数量。|
|`sample_count`|int|是|无|扫描中实际接受的信号样本数量。|
|`projected_aliases`|tuple[str, ...]|是|无|此次实际投影并检查的信号别名，未列入的字段不冒充已核验。|
|`completion`|[HistoryProgress](chronaxis.execution.history_records.md#api-HistoryProgress)|是|无|同次真实EOF/关闭等来源完成事实。|
|`observation`|[SourceScanObservation](chronaxis.execution.observed_ingestion.md#api-SourceScanObservation)|是|无|实际观测范围Interval或按合同允许的空值，不是用户请求范围的复制。|

源码：[`src/chronaxis/execution/scanned_signal_proof.py:54`](../../../src/chronaxis/execution/scanned_signal_proof.py#L54)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ScannedInputFacts"></a>
## `ScannedInputFacts`

记录纯消息读取的实际输入摘要，不声称生成或验证过普通信号样本。

```python
class ScannedInputFacts
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|str|是|无|本次真实来源。|
|`session_id`|str|是|无|原会话。|
|`source_contract_sha256`|str|是|无|静态来源与解码策略。|
|`description_sha256`|str|是|无|实际需求字段描述。|
|`request_sha256`|str|是|无|无普通样本的真实读取请求。|
|`original_timestamps_sha256`|str &#124; None|是|无|source为全时间SHA，其他范围明确未采集。|
|`retained_records_sha256`|str|是|无|实际保留记录的长度前缀与JSON原字节。|
|`required_aliases`|tuple[str, ...]|是|无|实际需要的消息字段别名。|
|`retained_record_count`|int|是|无|保留的原消息数，不是样本数。|
|`completion`|[HistoryProgress](chronaxis.execution.history_records.md#api-HistoryProgress)|是|无|仅内部EOF协议标记；不编码成样本流摘要。|
|`observation`|[SourceScanObservation](chronaxis.execution.observed_ingestion.md#api-SourceScanObservation)|是|无|原读取数量及明确时间范围。|
|`time_scope`|str|否|'source'|`"none"`：本次未收集时间范围；`"selected"`：范围只基于选中的报文；`"source"`：范围基于整个来源。selected的首末时间不代表整个文件的首末时间。|
|`input_check`|str|否|'full'|`"auto"`按本计划实际要计算的内容检查输入；`"full"`检查全部原帧及时间，即使某帧不参与指标也检查它。|

源码：[`src/chronaxis/execution/scanned_signal_proof.py:71`](../../../src/chronaxis/execution/scanned_signal_proof.py#L71)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ScannedCANSignals"></a>
## `ScannedCANSignals`

拥有一个实际CAN read、有限验证状态和未移交消息仓，不拥有普通历史文件。

```python
ScannedCANSignals(declarations, source_plan, adapter, request, *, input_only=False)
```


源码：[`src/chronaxis/execution/scanned_signal_proof.py:89`](../../../src/chronaxis/execution/scanned_signal_proof.py#L89)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ScannedCANSignals-__init__"></a>
### `ScannedCANSignals.__init__`

核实际投影和原来源后预付状态。

```python
ScannedCANSignals.__init__(declarations, source_plan, adapter, request, *, input_only=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`declarations`|DeclarationBindings|是|无|位置或关键字。本计划的声明绑定，保留全部声明与实际需求之间的关系。|
|`source_plan`|[SourcePlan](chronaxis.planning.models.md#api-SourcePlan)|是|无|位置或关键字。本次SourcePlan，包含原来源定位与按需检查策略。|
|`adapter`|[BudgetedLegacyCANSourceAdapter](chronaxis.execution.can_reader.md#api-BudgetedLegacyCANSourceAdapter)|是|无|位置或关键字。同次受预算管理的真实来源适配器；不在这里新建第二次输入扫描。|
|`request`|[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)|是|无|位置或关键字。同次ReadRequest，包含实际所需字段、时间范围和检查要求。|
|`input_only`|bool|否|False|仅关键字。input_only仅纯消息空样本请求，改存实际输入指纹。|

#### 返回说明

读取与证明owner。

#### 异常说明

原合同/预算错误，不打开第二次来源。

本函数直接报告的具体错误：

- `TypeError`：扫描证明只接真实有界CAN来源、原请求且无原始导出。
- `ValueError`：输入证明仅接真实直接累计的空普通样本请求。

源码：[`src/chronaxis/execution/scanned_signal_proof.py:92`](../../../src/chronaxis/execution/scanned_signal_proof.py#L92)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ScannedCANSignals-_require_contract"></a>
### `ScannedCANSignals._require_contract`

核原对象与实际本流状态，完成后不再访问已关闭adapter。

```python
ScannedCANSignals._require_contract(*, completed=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`completed`|bool|否|False|仅关键字。是否要求读取已经完成；True同时检查完整结束状态，默认False。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

替换/失效错误。

本函数直接报告的具体错误：

- `ResultClosedError`：CAN扫描证明已关闭、清理或失败。
- `ValueError`：CAN扫描证明的原来源、完整投影、请求、验证器或计数摘要已改变。
- `ValueError`：CAN扫描证明的实际adapter与原合同不符。

源码：[`src/chronaxis/execution/scanned_signal_proof.py:150`](../../../src/chronaxis/execution/scanned_signal_proof.py#L150)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ScannedCANSignals-_digest_record"></a>
### `ScannedCANSignals._digest_record`

编码一条原规范记录并更新流摘要。

```python
ScannedCANSignals._digest_record(record)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`record`|HistoryRecord|是|无|位置或关键字。当前HistorySample或HistoryProgress规范记录，按原顺序编码。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原模型/编码/预算错误。

源码：[`src/chronaxis/execution/scanned_signal_proof.py:176`](../../../src/chronaxis/execution/scanned_signal_proof.py#L176)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ScannedCANSignals-_release_temporary"></a>
### `ScannedCANSignals._release_temporary`

归还实际临时费，清理错误不覆盖主错。

```python
ScannedCANSignals._release_temporary(slot, primary)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`slot`|str|是|无|位置或关键字。当前对象中用于保存资源或其费用的属性名，例如"_row_cost"；只能指向本对象实际管理的项。释放成功后才清空对应项。|
|`primary`|BaseException|是|无|位置或关键字。本次操作的原异常，供附加关闭失败信息并保留原因链。不要用错误字符串代替异常对象。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

无主错时释放错误。

源码：[`src/chronaxis/execution/scanned_signal_proof.py:190`](../../../src/chronaxis/execution/scanned_signal_proof.py#L190)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ScannedCANSignals-_accept"></a>
### `ScannedCANSignals._accept`

按原历史顺序验证并编码一批，不写磁盘。

```python
ScannedCANSignals._accept(batch)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`batch`|[SignalBatch](chronaxis.sources.models.md#api-SignalBatch)|是|无|位置或关键字。当前SignalBatch，包含同批值、时间、质量与来源进度。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原协议/样本/预算错。

本函数直接报告的具体错误：

- `ValueError`：扫描样本批不属于原来源。
- `OverflowError`：扫描批次/样本计数超过int64。
- `ValueError`：纯消息输入证明不能混入普通样本或非最终批。
- `ResultFormatError`：实际扫描样本与当前绑定契约不符。

源码：[`src/chronaxis/execution/scanned_signal_proof.py:199`](../../../src/chronaxis/execution/scanned_signal_proof.py#L199)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ScannedCANSignals-_adopt"></a>
### `ScannedCANSignals._adopt`

接实际未返回的read，避免丢失构造失败资源。

```python
ScannedCANSignals._adopt(exc)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`exc`|BaseException|是|无|位置或关键字。本次操作的原异常，供附加关闭失败信息并保留原因链。不要用错误字符串代替异常对象。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

无正常新增异常。

源码：[`src/chronaxis/execution/scanned_signal_proof.py:268`](../../../src/chronaxis/execution/scanned_signal_proof.py#L268)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ScannedCANSignals-_close_read"></a>
### `ScannedCANSignals._close_read`

关闭本次真实read，失败保留责任。

```python
ScannedCANSignals._close_read()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原关闭错误。

本函数直接报告的具体错误：

- `AnalysisError`：扫描read关闭未完成。

源码：[`src/chronaxis/execution/scanned_signal_proof.py:275`](../../../src/chronaxis/execution/scanned_signal_proof.py#L275)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ScannedCANSignals-consume"></a>
### `ScannedCANSignals.consume`

完整扫描一次并在真实EOF和关闭后发布证明。

```python
ScannedCANSignals.consume()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原错误及最高恢复owner。

本函数直接报告的具体错误：

- `ResultClosedError`：CAN扫描证明不能重复开始读取。
- `TypeError`：扫描证明必须消费本次实际CANBatchObservationRead。
- `ValueError`：扫描证明缺少原流完整EOF。
- `ValueError`：CAN扫描完成事实不属于同一次真实读取。
- `ValueError`：扫描read的原消息捕获开关已改变。
- `ValueError`：扫描消息仓不属于本次完整输入。
- `ValueError`：实际输入指纹原帧数与观测不一致。

源码：[`src/chronaxis/execution/scanned_signal_proof.py:284`](../../../src/chronaxis/execution/scanned_signal_proof.py#L284)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ScannedCANSignals-assert_current"></a>
### `ScannedCANSignals.assert_current`

核活的完整扫描与调用者原合同。

```python
ScannedCANSignals.assert_current(source, description, request, declarations)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|[SourcePlan](chronaxis.planning.models.md#api-SourcePlan)|是|无|位置或关键字。原SourcePlan声明，必须与同次真实扫描和绑定一致。|
|`description`|SourceDescription|是|无|位置或关键字。本次来源返回的SourceDescription，须与原扫描事实一致。|
|`request`|[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)|是|无|位置或关键字。同次ReadRequest，包含实际所需字段、时间范围和检查要求。|
|`declarations`|DeclarationBindings|是|无|位置或关键字。本计划的声明绑定，核对扫描结果仍对应原信号定义和实际读取需求。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

替换或未完成证明。

本函数直接报告的具体错误：

- `ValueError`：扫描证明未完成或不是当前原计划及完整样本流。
- `ValueError`：扫描证明的完成事实已被替换。
- `ValueError`：输入证明与实际已验证字节流不符。
- `ValueError`：样本扫描证明与实际计数摘要不符。

源码：[`src/chronaxis/execution/scanned_signal_proof.py:359`](../../../src/chronaxis/execution/scanned_signal_proof.py#L359)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ScannedCANSignals-facts"></a>
### `ScannedCANSignals.facts`

借读真实完成的扫描事实。

```python
ScannedCANSignals.facts
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

ScannedSignalFacts。

#### 异常说明

原生命周期/合同错误。

源码：[`src/chronaxis/execution/scanned_signal_proof.py:382`](../../../src/chronaxis/execution/scanned_signal_proof.py#L382)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ScannedCANSignals-observation"></a>
### `ScannedCANSignals.observation`

读取全部原帧观测。

```python
ScannedCANSignals.observation
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

SourceScanObservation。

#### 异常说明

未完成/失效证明。

源码：[`src/chronaxis/execution/scanned_signal_proof.py:388`](../../../src/chronaxis/execution/scanned_signal_proof.py#L388)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ScannedCANSignals-runtime_metadata"></a>
### `ScannedCANSignals.runtime_metadata`

借读同次READY。

```python
ScannedCANSignals.runtime_metadata
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

冻结元数据。

#### 异常说明

未完成/失效证明。

源码：[`src/chronaxis/execution/scanned_signal_proof.py:393`](../../../src/chronaxis/execution/scanned_signal_proof.py#L393)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ScannedCANSignals-read_identity"></a>
### `ScannedCANSignals.read_identity`

读取同次真实read标识。

```python
ScannedCANSignals.read_identity
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

str。

#### 异常说明

未完成/失效证明。

源码：[`src/chronaxis/execution/scanned_signal_proof.py:399`](../../../src/chronaxis/execution/scanned_signal_proof.py#L399)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ScannedCANSignals-capture_message_updates"></a>
### `ScannedCANSignals.capture_message_updates`

读取原捕获开关。

```python
ScannedCANSignals.capture_message_updates
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本次读取会保存逐消息计算需要的原值；False表示不保存这类消息记录。

#### 异常说明

无。

源码：[`src/chronaxis/execution/scanned_signal_proof.py:405`](../../../src/chronaxis/execution/scanned_signal_proof.py#L405)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ScannedCANSignals-closed"></a>
### `ScannedCANSignals.closed`

读取实际关闭状态。

```python
ScannedCANSignals.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/execution/scanned_signal_proof.py:410`](../../../src/chronaxis/execution/scanned_signal_proof.py#L410)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ScannedCANSignals-finished"></a>
### `ScannedCANSignals.finished`

读取成功扫描事实，不代替当前活性检查。

```python
ScannedCANSignals.finished
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示规定的处理步骤已全部完成；False表示尚未完成。完成处理和关闭资源是两个独立状态。

#### 异常说明

无。

源码：[`src/chronaxis/execution/scanned_signal_proof.py:415`](../../../src/chronaxis/execution/scanned_signal_proof.py#L415)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ScannedCANSignals-take_message_store"></a>
### `ScannedCANSignals.take_message_store`

先安装父实际槽再解除本消息仓责任。

```python
ScannedCANSignals.take_message_store(receiver, slot='_message_store')
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`receiver`|资源接收对象|是|无|位置或关键字。接收当前资源所有权的父对象；其_budget必须与发送方相同，指定的接收属性必须为空。接收后由父对象负责close()和归还资源额度。|
|`slot`|str|否|'_message_store'|位置或关键字。当前对象中用于保存资源或其费用的属性名，例如"_row_cost"；只能指向本对象实际管理的项。释放成功后才清空对应项。|

#### 返回说明

原仓。

#### 异常说明

原移交错误。

本函数直接报告的具体错误：

- `ValueError`：扫描消息仓移交需同预算空父槽且只能一次。

源码：[`src/chronaxis/execution/scanned_signal_proof.py:419`](../../../src/chronaxis/execution/scanned_signal_proof.py#L419)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ScannedCANSignals-close"></a>
### `ScannedCANSignals.close`

关闭真实read/未移交仓后归还本owner费用。

```python
ScannedCANSignals.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

持续失败保本最高owner。

本函数直接报告的具体错误：

- `AnalysisError`：扫描消息仓未完成关闭。

源码：[`src/chronaxis/execution/scanned_signal_proof.py:437`](../../../src/chronaxis/execution/scanned_signal_proof.py#L437)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_ScannedBindings"></a>
## `_ScannedBindings`

仅用于纯消息运行清单的已扫描定义，不能交给普通历史表达式执行入口。

```python
class _ScannedBindings
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`declarations`|object|是|无|本计划的声明绑定，保留全部声明与实际需求之间的关系。|
|`sources`|tuple[[ScannedSignalFacts](chronaxis.execution.scanned_signal_proof.md#api-ScannedSignalFacts) &#124; [ScannedInputFacts](chronaxis.execution.scanned_signal_proof.md#api-ScannedInputFacts), ...]|是|无|各来源已经完成的扫描事实元组。|
|`identity`|str|是|无|该已扫描绑定的版本化身份摘要。|

源码：[`src/chronaxis/execution/scanned_signal_proof.py:464`](../../../src/chronaxis/execution/scanned_signal_proof.py#L464)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_ScannedBindings-signals"></a>
### `_ScannedBindings.signals`

借用全部原信号定义。

```python
_ScannedBindings.signals
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

冻结tuple。

#### 异常说明

无。

源码：[`src/chronaxis/execution/scanned_signal_proof.py:472`](../../../src/chronaxis/execution/scanned_signal_proof.py#L472)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_ScannedBindings-resolve"></a>
### `_ScannedBindings.resolve`

解析原定义供清单角色核对。

```python
_ScannedBindings.resolve(name)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|位置或关键字。计划中的简单信号别名，例如"u"；返回该别名对应的已扫描信号定义。|

#### 返回说明

SignalDefinition。

#### 异常说明

原声明解析错误。

源码：[`src/chronaxis/execution/scanned_signal_proof.py:476`](../../../src/chronaxis/execution/scanned_signal_proof.py#L476)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ScannedBindingLease"></a>
## `ScannedBindingLease`

拥有已完成扫描的有限运行清单证明；借用scan但不关闭它们。

```python
ScannedBindingLease(plan, scans, descriptions, requests, budget)
```


源码：[`src/chronaxis/execution/scanned_signal_proof.py:481`](../../../src/chronaxis/execution/scanned_signal_proof.py#L481)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ScannedBindingLease-__init__"></a>
### `ScannedBindingLease.__init__`

核真实扫描后建立版本化绑定摘要。

```python
ScannedBindingLease.__init__(plan, scans, descriptions, requests, budget)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)|是|无|位置或关键字。本次冻结AnalysisPlan，提供来源、规则、范围与执行预算。|
|`scans`|tuple|是|无|位置或关键字。同次各来源扫描对象，用于核实真实EOF、关闭及摘要。|
|`descriptions`|tuple|是|无|位置或关键字。本次真实SourceDescription集合，保留来源能力和字段说明。|
|`requests`|Mapping|是|无|位置或关键字。同次各来源实际ReadRequest集合。|
|`budget`|ResourceBudget|是|无|位置或关键字。本次运行共用的ResourceBudget对象，用于检查内存和临时磁盘用量。当前对象在分配前申请额度，用完后归还；同一次运行的组件应使用同一个对象。|

#### 返回说明

lease。

#### 异常说明

合同/预算错误。

本函数直接报告的具体错误：

- `TypeError`：扫描绑定仅接全CAN纯消息计划及完整实际扫描。
- `ValueError`：扫描绑定必须使用同一实际budget。
- `ValueError`：扫描投影未恰好覆盖本计划实际需求。

源码：[`src/chronaxis/execution/scanned_signal_proof.py:484`](../../../src/chronaxis/execution/scanned_signal_proof.py#L484)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ScannedBindingLease-bindings"></a>
### `ScannedBindingLease.bindings`

借读当前完整扫描绑定，拒绝失效scan。

```python
ScannedBindingLease.bindings
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

私有绑定。

#### 异常说明

状态/原合同错误。

本函数直接报告的具体错误：

- `ResultClosedError`：扫描绑定未完成或已关闭。

源码：[`src/chronaxis/execution/scanned_signal_proof.py:530`](../../../src/chronaxis/execution/scanned_signal_proof.py#L530)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ScannedBindingLease-closed"></a>
### `ScannedBindingLease.closed`

读取真实关闭状态。

```python
ScannedBindingLease.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/execution/scanned_signal_proof.py:539`](../../../src/chronaxis/execution/scanned_signal_proof.py#L539)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ScannedBindingLease-close"></a>
### `ScannedBindingLease.close`

释放自有证明，不关闭借用scan。

```python
ScannedBindingLease.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

预算释放错误可重试。

源码：[`src/chronaxis/execution/scanned_signal_proof.py:543`](../../../src/chronaxis/execution/scanned_signal_proof.py#L543)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
