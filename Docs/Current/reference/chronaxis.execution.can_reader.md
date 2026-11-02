# chronaxis.execution.can_reader

把旧 CAN 读取和解码程序接到 Chronaxis，按批次返回信号样本。创建读取器或查询描述时不会打开 BLF、DBC；第一次取数据时才启动读取进程。

`decode_scope="all"`沿用旧程序逐条解码；`"requested"`只取本次需要的报文和字段。每条报文仍计入读取数量。`batch_rows`限制一批中所有信号的样本总数；不相关报文不会更新信号，相关报文缺少所需字段时返回值为None、质量为MISSING的样本，不沿用旧值。

浮点秒时间通过convert_time转换，并加一次配置的偏移。读取器保留同一时刻后续更新的处理机会。只有读完数据、关闭输出并完成校验后，才能取得最终观测范围。DBC没有提供单位时，元数据不会将单位标为已核实。

只有retain_raw_frames启用时才保存原始报文。完成后可调用take_raw_store取走一次，接收方随后负责关闭；未取走时由读取器关闭。capture_message_updates启用时，每条报文保存一次完整解码字典，不因信号别名或分批而重复保存。

自动批量读取在requested模式使用can_batch_reader，在all模式沿用逐条路径；显式布尔设置可覆盖自动选择，但requested模式不能将batch_read设为False。资源限制约束本读取器登记的占用，不代表整个Python进程的内存上限。失败时保留尚未关闭的资源，以便再次清理。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[BatchValidator](chronaxis.sources.protocol.md#api-BatchValidator)、[CANSourceRef](chronaxis.sources.can_spec.md#api-CANSourceRef)、[DecodedMessageStore](chronaxis.legacy.message_store.md#api-DecodedMessageStore)、[LegacyCANField](chronaxis.legacy.records.md#api-LegacyCANField)、[LegacyCANProcessRead](chronaxis.legacy.process_read.md#api-LegacyCANProcessRead)、[LegacyCANRequest](chronaxis.legacy.records.md#api-LegacyCANRequest)、[LegacyCANSpec](chronaxis.sources.can_spec.md#api-LegacyCANSpec)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[RawFrameStore](chronaxis.legacy.raw_store.md#api-RawFrameStore)、[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[SignalBatch](chronaxis.sources.models.md#api-SignalBatch)、[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)、[SourceCapabilities](chronaxis.sources.models.md#api-SourceCapabilities)、[SourceClosedError](chronaxis.sources.protocol.md#api-SourceClosedError)、[SourceDescription](chronaxis.sources.models.md#api-SourceDescription)、[SourceReadError](chronaxis.sources.protocol.md#api-SourceReadError)

## 对象导航

|对象|用途|
|---|---|
|[`CANObservation`](#api-CANObservation)|保存本read实际全部yield的完成事实，不接受请求范围作为原行首末。|
|[`CANObservation.__post_init__`](#api-CANObservation-__post_init__)|检查完成记录中的数量、起止时间和结束状态是否一致。|
|[`BudgetedLegacyCANSourceAdapter`](#api-BudgetedLegacyCANSourceAdapter)|拥有静态来源描述和活read登记，完成read与已移交store由新父负责。|
|[`BudgetedLegacyCANSourceAdapter.__init__`](#api-BudgetedLegacyCANSourceAdapter-__init__)|先付声明费用，建立显式新工作根但不访问原输入。|
|[`BudgetedLegacyCANSourceAdapter.capture_message_updates`](#api-BudgetedLegacyCANSourceAdapter-capture_message_updates)|读取原配置的消息捕获开关，不启动来源或开放完成证明。|
|[`BudgetedLegacyCANSourceAdapter.batch_read`](#api-BudgetedLegacyCANSourceAdapter-batch_read)|读取本adapter冻结的批协议选择。|
|[`BudgetedLegacyCANSourceAdapter.retain_raw_frames`](#api-BudgetedLegacyCANSourceAdapter-retain_raw_frames)|读取原始帧保存选择。|
|[`BudgetedLegacyCANSourceAdapter.message_frame_ids`](#api-BudgetedLegacyCANSourceAdapter-message_frame_ids)|读取实际消息保留ID。|
|[`BudgetedLegacyCANSourceAdapter.decode_scope`](#api-BudgetedLegacyCANSourceAdapter-decode_scope)|读取创建时的解码方式。|
|[`BudgetedLegacyCANSourceAdapter.decode_frame_ids`](#api-BudgetedLegacyCANSourceAdapter-decode_frame_ids)|借用已付费的固定解码集合。|
|[`BudgetedLegacyCANSourceAdapter._ensure_open`](#api-BudgetedLegacyCANSourceAdapter-_ensure_open)|拒绝关闭中/已关闭。|
|[`BudgetedLegacyCANSourceAdapter.describe`](#api-BudgetedLegacyCANSourceAdapter-describe)|返回已付费静态描述，不读BLF/DBC或spawn。|
|[`BudgetedLegacyCANSourceAdapter.iter_batches`](#api-BudgetedLegacyCANSourceAdapter-iter_batches)|创建独立观测read，首次next才实际输入。|
|[`BudgetedLegacyCANSourceAdapter.iter_batches_with_observation`](#api-BudgetedLegacyCANSourceAdapter-iter_batches_with_observation)|使用同一独立read合同。|
|[`BudgetedLegacyCANSourceAdapter.close`](#api-BudgetedLegacyCANSourceAdapter-close)|关闭本来源活read及费用，不关闭已完成脱登记read或其新父raw store。|
|[`CANObservationRead`](#api-CANObservationRead)|拥有同次CAN读取进程进程、原帧/可选消息仓及当前帧；事实活到自身close，移交仓归新父。|
|[`CANObservationRead.__init__`](#api-CANObservationRead-__init__)|先安装未返回槽并预付固定树，不实际打开来源。|
|[`CANObservationRead.capture_message_updates`](#api-CANObservationRead-capture_message_updates)|读取创建本read时的原捕获开关，不因adapter关闭而失去来源。|
|[`CANObservationRead.identity`](#api-CANObservationRead-identity)|读取本次独立UUID。|
|[`CANObservationRead.request`](#api-CANObservationRead-request)|读取创建时原请求。|
|[`CANObservationRead.closed`](#api-CANObservationRead-closed)|查看本对象是否已经完成关闭。|
|[`CANObservationRead.failed`](#api-CANObservationRead-failed)|读取失败标记。|
|[`CANObservationRead.finished`](#api-CANObservationRead-finished)|查看迭代是否已正常结束。仅仅读到批次末尾还不算结束。|
|[`CANObservationRead.exhausted`](#api-CANObservationRead-exhausted)|提供完成别名。|
|[`CANObservationRead._require_open`](#api-CANObservationRead-_require_open)|拒绝已关闭/失败/半关闭。|
|[`CANObservationRead.observation`](#api-CANObservationRead-observation)|读取已经完成的观测记录；尚未完成读取时会报错。|
|[`CANObservationRead.observed_bounds`](#api-CANObservationRead-observed_bounds)|读取已经看到的首末时间供在线规则定界，不表示输入已完整结束。|
|[`CANObservationRead.input_fingerprints`](#api-CANObservationRead-input_fingerprints)|借读实际输入的两段字节指纹，不把它解释成普通信号样本摘要。|
|[`CANObservationRead._observe_validated_packet`](#api-CANObservationRead-_observe_validated_packet)|在严格批解包后借用原字节，按原顺序增量计算时间和所需记录指纹。|
|[`CANObservationRead.runtime_metadata`](#api-CANObservationRead-runtime_metadata)|借读同次READY原冻结映射，None/空unit仍未核实。|
|[`CANObservationRead.prepare_metadata`](#api-CANObservationRead-prepare_metadata)|初始化同次DBC并返回周期/单位事实，不读取首帧。|
|[`CANObservationRead._adopt`](#api-CANObservationRead-_adopt)|接管未返回的实际CAN读取进程/raw/消息仓子owner。|
|[`CANObservationRead._fail`](#api-CANObservationRead-_fail)|保原错/取消并关闭同一最高read。|
|[`CANObservationRead._start`](#api-CANObservationRead-_start)|原start仅INIT，复制同次READY并核全部声明单位后才允许第一PULL。|
|[`CANObservationRead._accept`](#api-CANObservationRead-_accept)|先申请校验和去重所需的内存，检查通过后一次更新读取状态，并记录仍在占用的字节数。|
|[`CANObservationRead._release_current`](#api-CANObservationRead-_release_current)|下一步前停止持有原batch再归还其装箱空间。|
|[`CANObservationRead._new_record`](#api-CANObservationRead-_new_record)|原帧进入前先付本层记录/引用空间；全部yield先暂存再作分析层列选择。|
|[`CANObservationRead._deliver_message`](#api-CANObservationRead-_deliver_message)|仅有明确消费者时构造共同消息，默认读取不增加逐帧对象。|
|[`CANObservationRead._batch`](#api-CANObservationRead-_batch)|为当前原帧最多batch_rows个匹配别名装箱，缺key产生明确MISSING更新。|
|[`CANObservationRead.__iter__`](#api-CANObservationRead-__iter__)|保持本次原序位置。|
|[`CANObservationRead.__next__`](#api-CANObservationRead-__next__)|逐次交付当前原帧分片或独立空EOF批，真正下一次耗尽才开放完成事实。|
|[`CANObservationRead._close_child`](#api-CANObservationRead-_close_child)|关闭子对象；成功后才清除它的引用，失败时保留供重试。|
|[`CANObservationRead._finish`](#api-CANObservationRead-_finish)|确认读取和清理都已完成后保存观测记录，并从来源适配器的活动请求中移除本次读取。|
|[`CANObservationRead.take_raw_store`](#api-CANObservationRead-take_raw_store)|仅完成后一次移交真实sealed store，本read后续不再关闭新父资源。|
|[`CANObservationRead.take_message_store`](#api-CANObservationRead-take_message_store)|完成后一次移交同次消息仓，父实际安装成功才解除本read责任。|
|[`CANObservationRead.close`](#api-CANObservationRead-close)|只关闭仍自有的输入/raw/消息store和所有实际费用，可持续重试。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4
from ..core.binding import SignalDefinition
from ..core.validation import require_identifier, require_text
from ..legacy.process_read import LegacyCANProcessRead
from ..legacy.raw_store import RawFrameStore
from ..legacy.message_store import DecodedMessageStore, MAX_DECODED_MESSAGE_ROW_BYTES
from ..legacy.records import LegacyCANRequest, field_to_dict
from ..legacy.batch_wire import HEADER
from ..legacy.batch_worker import REQUESTED_VALUES_POLICY
from ..results.budget import ResourceBudget
from ..results.errors import ResultClosedError
from ..results.spool import _cleanup_owner, _reserve_owned_ram, _release_owned_ram
from ..sources.can_spec import LegacyCANSpec, CANSourceRef, can_field_from_key
from ..sources.descriptions import describe_fields, source_timebase_identity
from ..sources.models import ReadRequest, SignalBatch, SourceDescription, SourceCapabilities, freeze_metadata
from ..sources.packing import pack_decoded
from ..sources.protocol import BatchValidator, SourceClosedError, SourceReadError
from ..timebase.conversion import checked_add_ns, convert_time, require_int64_ns
from .history import _metadata_bytes, _pending_bytes
```

</details>

<a id="api-CANObservation"></a>
## `CANObservation`

保存本read实际全部yield的完成事实，不接受请求范围作为原行首末。

```python
class CANObservation
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|str|是|无|当前来源名。|
|`session_id`|str|是|无|原会话。|
|`request`|[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)|是|无|创建本read的原对象，不按值重建。|
|`read_identity`|str|是|无|每个read独立UUID。|
|`first_ns`|int &#124; None|是|无|全部原yield经一次映射的首端，全空为None。|
|`last_ns`|int &#124; None|是|无|全部原yield经一次映射的末端，全空为None。|
|`row_count`|int|是|无|包含未知ID/空投影的原yield数，不是样本数。|
|`source_eof`|bool|是|无|仅真实完整完成为True。|
|`time_scope`|str|否|'source'|`"none"`：本次未收集时间范围；`"selected"`：范围只基于选中的报文；`"source"`：范围基于整个来源。selected的首末时间不代表整个文件的首末时间。|
|`retained_record_count`|int|否|0|本次实际保留记录数，不等于贡献数。|
|`full_check_count`|int|否|0|按需策略下非原生输入的完整检查回退数。|

源码：[`src/chronaxis/execution/can_reader.py:59`](../../../src/chronaxis/execution/can_reader.py#L59)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANObservation-__post_init__"></a>
### `CANObservation.__post_init__`

检查完成记录中的数量、起止时间和结束状态是否一致。

```python
CANObservation.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

类型/会话/端点或EOF矛盾。

本函数直接报告的具体错误：

- `ValueError`：CAN观测需原请求、非负原行数及完整EOF。
- `ValueError`：CAN观测时间范围非法。
- `ValueError`：CAN观测保留/完整回退计数非法。
- `ValueError`：未采集时间不能声明首末。
- `ValueError`：空CAN输入没有可猜测首末。
- `ValueError`：CAN观测时间不能回退。

源码：[`src/chronaxis/execution/can_reader.py:74`](../../../src/chronaxis/execution/can_reader.py#L74)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-BudgetedLegacyCANSourceAdapter"></a>
## `BudgetedLegacyCANSourceAdapter`

拥有静态来源描述和活read登记，完成read与已移交store由新父负责。

```python
BudgetedLegacyCANSourceAdapter(budget, spec, session_id, signals, *, backend='numpy', work_dir, capture_message_updates=False, batch_read=None, retain_raw_frames=True, input_check='full', time_scope='source', message_frame_ids=None, extra_fields=(), message_consumer=None, cycle_fields=(), metadata_fields=(), message_keys=(), input_fingerprints=True, history_integrity=True, frame_observer=None)
```


源码：[`src/chronaxis/execution/can_reader.py:102`](../../../src/chronaxis/execution/can_reader.py#L102)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-BudgetedLegacyCANSourceAdapter-__init__"></a>
### `BudgetedLegacyCANSourceAdapter.__init__`

先付声明费用，建立显式新工作根但不访问原输入。

```python
BudgetedLegacyCANSourceAdapter.__init__(budget, spec, session_id, signals, *, backend='numpy', work_dir, capture_message_updates=False, batch_read=None, retain_raw_frames=True, input_check='full', time_scope='source', message_frame_ids=None, extra_fields=(), message_consumer=None, cycle_fields=(), metadata_fields=(), message_keys=(), input_fingerprints=True, history_integrity=True, frame_observer=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)|是|无|位置或关键字。本次运行共用的ResourceBudget对象，用于检查内存和临时磁盘用量。当前对象在分配前申请额度，用完后归还；同一次运行的组件应使用同一个对象。|
|`spec`|[LegacyCANSpec](chronaxis.sources.can_spec.md#api-LegacyCANSpec)|是|无|位置或关键字。spec为LegacyCANSpec；低层默认full/source保旧入口。     spec.decode_scope=requested使用批协议，将实际需要的字段及指标ID固定为解码集合|
|`session_id`|str|是|无|位置或关键字。本次会话的名字，用来防止把不同试验的数据混在一起。|
|`signals`|tuple|是|无|位置或关键字。signals为SignalDefinition tuple|
|`backend`|str|否|'numpy'|仅关键字。`"reference"`使用独立参考计算；`"numpy"`使用NumPy数组计算。须明确选择一种。|
|`work_dir`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|仅关键字。本次运行独占的工作目录，用来保存中间文件。自行指定时要求尚不存在；不会覆盖旧目录。|
|`capture_message_updates`|bool|否|False|仅关键字。capture_message_updates为严格bool，默认False，仅显式开启才存同次decoded仓|
|`batch_read`|bool &#124; None|否|None|仅关键字。True使用批量读取，False逐条读取；None按decode_scope选择：requested使用批量，all逐条读取。|
|`retain_raw_frames`|bool|否|True|仅关键字。retain_raw_frames决定是否保存原帧|
|`input_check`|str|否|'full'|仅关键字。`"auto"`按实际使用的报文和字段检查；`"full"`检查全部原始帧及时间。发送端与接收端必须使用同一次读取确认的设置。|
|`time_scope`|str|否|'source'|仅关键字。`"none"`不收集时间范围；`"selected"`只收集选中记录的时间；`"source"`收集全部来源时间。发送端与接收端必须使用同一次读取确认的设置。full检查要求time_scope为source。|
|`message_frame_ids`|tuple[int, ...] &#124; None|否|None|仅关键字。需要保留完整逐消息记录的报文ID；None保留实际返回的所有消息记录。|
|`extra_fields`|tuple[[LegacyCANField](chronaxis.legacy.records.md#api-LegacyCANField), ...]|否|()|仅关键字。显式报文重建额外需要的连续信号及复用选择器，不为它们创建普通分析信号别名。|
|`message_consumer`|Callable[[LegacyDecodedUpdate], None] &#124; None|否|None|仅关键字。接收当前所需报文解码更新的函数；None不启用额外逐消息交付。|
|`cycle_fields`|tuple[[LegacyCANField](chronaxis.legacy.records.md#api-LegacyCANField), ...]|否|()|仅关键字。需要读取DBC周期的字段定位集合；初始化时读取元数据，不逐帧读取DBC。|
|`metadata_fields`|tuple[[LegacyCANField](chronaxis.legacy.records.md#api-LegacyCANField), ...]|否|()|仅关键字。仅请求驱动信号的DBC候选声明，默认空tuple；用于确认实际帧身份，不请求信号值，也不增加普通样本或值解码。|
|`message_keys`|tuple[tuple[int, int, bool, bool], ...]|否|()|仅关键字。所需报文定位，依次为通道、ID、扩展帧标志、FD标志；空集合表示没有额外逐消息需求。|
|`input_fingerprints`|bool|否|True|仅关键字。是否为当前输入记录计算额外内容指纹；False不重复生成摘要。|
|`history_integrity`|bool|否|True|仅关键字。是否为确实需要保存的历史执行额外内容摘要；不因True而创建无消费者的历史。|
|`frame_observer`|Callable[[LegacyRawFrame], None] &#124; None|否|None|仅关键字。默认None；只有显式报文重建导出才传回调，在同次读取时识别真实帧型，不另存原帧或额外扫描。|

#### 返回说明

静态adapter。

#### 异常说明

原配置/目录/预算/取消；持续清理失败附can_source_cleanup_owner。

本函数直接报告的具体错误：

- `TypeError`：CAN来源需预算、静态spec、定义tuple、后端及新工作目录。
- `ValueError`：重建字段需要同通道有限LegacyCANField tuple。
- `ValueError`：CAN信号来源须匹配且别名唯一。
- `ValueError`：CAN检查范围或时间范围非法。
- `ValueError`：完整诊断/原帧/消息历史必须保全来源时间。
- `ValueError`：CAN字段通道必须等于单声明通道。
- `ValueError`：CAN工作目录禁止RefProjects。
- `ValueError`：requested来源需要批次读取，batch_read不能为False。
- `ValueError`：requested最多声明4096个不同报文ID。

源码：[`src/chronaxis/execution/can_reader.py:105`](../../../src/chronaxis/execution/can_reader.py#L105)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-BudgetedLegacyCANSourceAdapter-capture_message_updates"></a>
### `BudgetedLegacyCANSourceAdapter.capture_message_updates`

读取原配置的消息捕获开关，不启动来源或开放完成证明。

```python
BudgetedLegacyCANSourceAdapter.capture_message_updates
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

原生bool，关闭adapter后仍可核原开关。

#### 异常说明

无；只读属性不允许调用方改写活read的捕获来源。

源码：[`src/chronaxis/execution/can_reader.py:256`](../../../src/chronaxis/execution/can_reader.py#L256)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-BudgetedLegacyCANSourceAdapter-batch_read"></a>
### `BudgetedLegacyCANSourceAdapter.batch_read`

读取本adapter冻结的批协议选择。

```python
BudgetedLegacyCANSourceAdapter.batch_read
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示启用按批读取CAN记录；False表示采用逐条读取方式。

#### 异常说明

无。

源码：[`src/chronaxis/execution/can_reader.py:265`](../../../src/chronaxis/execution/can_reader.py#L265)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-BudgetedLegacyCANSourceAdapter-retain_raw_frames"></a>
### `BudgetedLegacyCANSourceAdapter.retain_raw_frames`

读取原始帧保存选择。

```python
BudgetedLegacyCANSourceAdapter.retain_raw_frames
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示保存原始报文供后续导出；False表示不为此目的保存原始报文。

#### 异常说明

无，不随关闭改变。

源码：[`src/chronaxis/execution/can_reader.py:270`](../../../src/chronaxis/execution/can_reader.py#L270)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-BudgetedLegacyCANSourceAdapter-message_frame_ids"></a>
### `BudgetedLegacyCANSourceAdapter.message_frame_ids`

读取实际消息保留ID。

```python
BudgetedLegacyCANSourceAdapter.message_frame_ids
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

tuple或None。

#### 异常说明

无。

源码：[`src/chronaxis/execution/can_reader.py:275`](../../../src/chronaxis/execution/can_reader.py#L275)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-BudgetedLegacyCANSourceAdapter-decode_scope"></a>
### `BudgetedLegacyCANSourceAdapter.decode_scope`

读取创建时的解码方式。

```python
BudgetedLegacyCANSourceAdapter.decode_scope
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

all/requested。

#### 异常说明

无。

源码：[`src/chronaxis/execution/can_reader.py:280`](../../../src/chronaxis/execution/can_reader.py#L280)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-BudgetedLegacyCANSourceAdapter-decode_frame_ids"></a>
### `BudgetedLegacyCANSourceAdapter.decode_frame_ids`

借用已付费的固定解码集合。

```python
BudgetedLegacyCANSourceAdapter.decode_frame_ids
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

tuple，close后为空。

#### 异常说明

无。

源码：[`src/chronaxis/execution/can_reader.py:285`](../../../src/chronaxis/execution/can_reader.py#L285)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-BudgetedLegacyCANSourceAdapter-_ensure_open"></a>
### `BudgetedLegacyCANSourceAdapter._ensure_open`

拒绝关闭中/已关闭。

```python
BudgetedLegacyCANSourceAdapter._ensure_open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

SourceClosedError。

本函数直接报告的具体错误：

- `SourceClosedError`：CAN来源已关闭或正在清理。

源码：[`src/chronaxis/execution/can_reader.py:289`](../../../src/chronaxis/execution/can_reader.py#L289)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-BudgetedLegacyCANSourceAdapter-describe"></a>
### `BudgetedLegacyCANSourceAdapter.describe`

返回已付费静态描述，不读BLF/DBC或spawn。

```python
BudgetedLegacyCANSourceAdapter.describe()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

SourceDescription。

#### 异常说明

SourceClosedError为关闭中/已关闭。

源码：[`src/chronaxis/execution/can_reader.py:295`](../../../src/chronaxis/execution/can_reader.py#L295)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-BudgetedLegacyCANSourceAdapter-iter_batches"></a>
### `BudgetedLegacyCANSourceAdapter.iter_batches`

创建独立观测read，首次next才实际输入。

```python
BudgetedLegacyCANSourceAdapter.iter_batches(request)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`request`|[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)|是|无|位置或关键字。request为原ReadRequest。|

#### 返回说明

CANObservationRead。

#### 异常说明

原配置/预约/登记错误，持续失败保最高真实owner。

本函数直接报告的具体错误：

- `SourceClosedError`：CAN来源有未返回read待清理。

源码：[`src/chronaxis/execution/can_reader.py:302`](../../../src/chronaxis/execution/can_reader.py#L302)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-BudgetedLegacyCANSourceAdapter-iter_batches_with_observation"></a>
### `BudgetedLegacyCANSourceAdapter.iter_batches_with_observation`

使用同一独立read合同。

```python
BudgetedLegacyCANSourceAdapter.iter_batches_with_observation(request)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`request`|[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)|是|无|位置或关键字。原始读取请求；在读取样本的同时保留实际观测范围。|

#### 返回说明

CANObservationRead。

#### 异常说明

与iter_batches相同；不复用adapter全局最后事实或request值map。

源码：[`src/chronaxis/execution/can_reader.py:327`](../../../src/chronaxis/execution/can_reader.py#L327)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-BudgetedLegacyCANSourceAdapter-close"></a>
### `BudgetedLegacyCANSourceAdapter.close`

关闭本来源活read及费用，不关闭已完成脱登记read或其新父raw store。

```python
BudgetedLegacyCANSourceAdapter.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None，可重试。

#### 异常说明

首个实际关闭/抵销错误，最高can_source_cleanup_owner。

源码：[`src/chronaxis/execution/can_reader.py:333`](../../../src/chronaxis/execution/can_reader.py#L333)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANObservationRead"></a>
## `CANObservationRead`

拥有同次CAN读取进程进程、原帧/可选消息仓及当前帧；事实活到自身close，移交仓归新父。

```python
CANObservationRead(owner, request)
```


源码：[`src/chronaxis/execution/can_reader.py:368`](../../../src/chronaxis/execution/can_reader.py#L368)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANObservationRead-__init__"></a>
### `CANObservationRead.__init__`

先安装未返回槽并预付固定树，不实际打开来源。

```python
CANObservationRead.__init__(owner, request)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|[BudgetedLegacyCANSourceAdapter](chronaxis.execution.can_reader.md#api-BudgetedLegacyCANSourceAdapter)|是|无|位置或关键字。创建本次观测读取的CAN适配器，提供来源配置和资源额度。|
|`request`|[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)|是|无|位置或关键字。同一会话中的原始读取请求，保留信号、范围和批次要求。|

#### 返回说明

独立read。

#### 异常说明

原请求/预算/取消；构造未返回资源由本read最高恢复owner负责。

本函数直接报告的具体错误：

- `TypeError`：CAN read需要实际来源及ReadRequest。
- `ValueError`：CAN请求会话或投影不匹配。
- `ValueError`：CAN真实输入指纹需要批次读取。

源码：[`src/chronaxis/execution/can_reader.py:371`](../../../src/chronaxis/execution/can_reader.py#L371)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANObservationRead-capture_message_updates"></a>
### `CANObservationRead.capture_message_updates`

读取创建本read时的原捕获开关，不因adapter关闭而失去来源。

```python
CANObservationRead.capture_message_updates
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

原生bool快照。

#### 异常说明

无；该标志本身不证明已经完成输入。

源码：[`src/chronaxis/execution/can_reader.py:425`](../../../src/chronaxis/execution/can_reader.py#L425)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANObservationRead-identity"></a>
### `CANObservationRead.identity`

读取本次独立UUID。

```python
CANObservationRead.identity
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

str。

#### 异常说明

无，不按request值复用。

源码：[`src/chronaxis/execution/can_reader.py:433`](../../../src/chronaxis/execution/can_reader.py#L433)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANObservationRead-request"></a>
### `CANObservationRead.request`

读取创建时原请求。

```python
CANObservationRead.request
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

原ReadRequest。

#### 异常说明

关闭时ResultClosedError。

源码：[`src/chronaxis/execution/can_reader.py:438`](../../../src/chronaxis/execution/can_reader.py#L438)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANObservationRead-closed"></a>
### `CANObservationRead.closed`

查看本对象是否已经完成关闭。

```python
CANObservationRead.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/execution/can_reader.py:444`](../../../src/chronaxis/execution/can_reader.py#L444)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANObservationRead-failed"></a>
### `CANObservationRead.failed`

读取失败标记。

```python
CANObservationRead.failed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象已记录处理失败；False表示尚未记录失败。

#### 异常说明

无，不代表已清理。

源码：[`src/chronaxis/execution/can_reader.py:449`](../../../src/chronaxis/execution/can_reader.py#L449)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANObservationRead-finished"></a>
### `CANObservationRead.finished`

查看迭代是否已正常结束。仅仅读到批次末尾还不算结束。

```python
CANObservationRead.finished
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示规定的处理步骤已全部完成；False表示尚未完成。完成处理和关闭资源是两个独立状态。

#### 异常说明

无。

源码：[`src/chronaxis/execution/can_reader.py:454`](../../../src/chronaxis/execution/can_reader.py#L454)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANObservationRead-exhausted"></a>
### `CANObservationRead.exhausted`

提供完成别名。

```python
CANObservationRead.exhausted
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示输入或结果已正常读完；False表示尚未正常读完。发生异常不等于正常读完。

#### 异常说明

无，EOF批交付仍为False。

源码：[`src/chronaxis/execution/can_reader.py:459`](../../../src/chronaxis/execution/can_reader.py#L459)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANObservationRead-_require_open"></a>
### `CANObservationRead._require_open`

拒绝已关闭/失败/半关闭。

```python
CANObservationRead._require_open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ResultClosedError。

本函数直接报告的具体错误：

- `ResultClosedError`：CAN read已关闭、失败或正在清理。

源码：[`src/chronaxis/execution/can_reader.py:463`](../../../src/chronaxis/execution/can_reader.py#L463)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANObservationRead-observation"></a>
### `CANObservationRead.observation`

读取已经完成的观测记录；尚未完成读取时会报错。

```python
CANObservationRead.observation
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

CANObservation。

#### 异常说明

ResultClosedError。

本函数直接报告的具体错误：

- `ResultClosedError`：CAN read尚未真正完整耗尽。

源码：[`src/chronaxis/execution/can_reader.py:469`](../../../src/chronaxis/execution/can_reader.py#L469)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANObservationRead-observed_bounds"></a>
### `CANObservationRead.observed_bounds`

读取已经看到的首末时间供在线规则定界，不表示输入已完整结束。

```python
CANObservationRead.observed_bounds
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

两个必要整数或None；none时间范围不补造坐标。

#### 异常说明

读取器已关闭/失败。

源码：[`src/chronaxis/execution/can_reader.py:477`](../../../src/chronaxis/execution/can_reader.py#L477)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANObservationRead-input_fingerprints"></a>
### `CANObservationRead.input_fingerprints`

借读实际输入的两段字节指纹，不把它解释成普通信号样本摘要。

```python
CANObservationRead.input_fingerprints
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

(时间SHA256,记录SHA256,全原帧数,保留记录数)的tuple。

#### 异常说明

ResultClosedError为未启用、未完成、失败或已关闭；不返回半成品hash。
指纹只活到本read关闭，接收方要继续保留须在自己的预算下复制/持有。

源码：[`src/chronaxis/execution/can_reader.py:486`](../../../src/chronaxis/execution/can_reader.py#L486)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANObservationRead-_observe_validated_packet"></a>
### `CANObservationRead._observe_validated_packet`

在严格批解包后借用原字节，按原顺序增量计算时间和所需记录指纹。

```python
CANObservationRead._observe_validated_packet(process, payload, batch)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`process`|[LegacyCANProcessRead](chronaxis.legacy.process_read.md#api-LegacyCANProcessRead)|是|无|位置或关键字。本次读取实际使用的子进程读取器，提供已经核验过的协议数据。|
|`payload`|bytes|是|无|位置或关键字。该子进程刚返回并检查过的协议包，供本次观测记账使用。|
|`batch`|LegacyDecodedBatch|是|无|位置或关键字。当前子进程刚返回且已核验的批次；其原帧起始序号必须接续此前已接收的帧数。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

SourceReadError为归属/原序不符；原hash/取消错误保持且标记失败。
时间区是头后每原帧8字节，记录区保每条长度及原JSON；不包含随分批改变的包头。
任一更新中断后本read永久失败，不能重试同一批或发布部分指纹。

源码：[`src/chronaxis/execution/can_reader.py:498`](../../../src/chronaxis/execution/can_reader.py#L498)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANObservationRead-runtime_metadata"></a>
### `CANObservationRead.runtime_metadata`

借读同次READY原冻结映射，None/空unit仍未核实。

```python
CANObservationRead.runtime_metadata
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

保operation/version/profile等原键的映射。

#### 异常说明

未READY/关闭ResultClosedError。

本函数直接报告的具体错误：

- `ResultClosedError`：CAN read尚未取得同次READY。

源码：[`src/chronaxis/execution/can_reader.py:537`](../../../src/chronaxis/execution/can_reader.py#L537)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANObservationRead-prepare_metadata"></a>
### `CANObservationRead.prepare_metadata`

初始化同次DBC并返回周期/单位事实，不读取首帧。

```python
CANObservationRead.prepare_metadata()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

同一冻结READY。

#### 异常说明

原启动错误，沿本read清理链处理。
重复调用复用同次初始化；不把初始化成功当作输入EOF。

源码：[`src/chronaxis/execution/can_reader.py:547`](../../../src/chronaxis/execution/can_reader.py#L547)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANObservationRead-_adopt"></a>
### `CANObservationRead._adopt`

接管未返回的实际CAN读取进程/raw/消息仓子owner。

```python
CANObservationRead._adopt(exc)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`exc`|BaseException|是|无|位置或关键字。本次操作的原异常，供附加关闭失败信息并保留原因链。不要用错误字符串代替异常对象。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

无预期异常。

源码：[`src/chronaxis/execution/can_reader.py:562`](../../../src/chronaxis/execution/can_reader.py#L562)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANObservationRead-_fail"></a>
### `CANObservationRead._fail`

保原错/取消并关闭同一最高read。

```python
CANObservationRead._fail(exc)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`exc`|BaseException|是|无|位置或关键字。本次操作的原异常，供附加关闭失败信息并保留原因链。不要用错误字符串代替异常对象。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

清理副错只note。

源码：[`src/chronaxis/execution/can_reader.py:572`](../../../src/chronaxis/execution/can_reader.py#L572)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANObservationRead-_start"></a>
### `CANObservationRead._start`

原start仅INIT，复制同次READY并核全部声明单位后才允许第一PULL。

```python
CANObservationRead._start()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原B1/单位/预算/原始暂存错误；上层保真实子槽。

本函数直接报告的具体错误：

- `SourceReadError`：同次CAN READY与来源固定requested策略不符。
- `SourceReadError`：同次CAN READY检查/时间范围与来源不同。
- `SourceReadError`：全解码来源必须保原v1 READY且不带按需策略。

源码：[`src/chronaxis/execution/can_reader.py:579`](../../../src/chronaxis/execution/can_reader.py#L579)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANObservationRead-_accept"></a>
### `CANObservationRead._accept`

先申请校验和去重所需的内存，检查通过后一次更新读取状态，并记录仍在占用的字节数。

```python
CANObservationRead._accept(batch)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`batch`|[SignalBatch](chronaxis.sources.models.md#api-SignalBatch)|是|无|位置或关键字。batch为有限SignalBatch。|

#### 返回说明

原batch。

#### 异常说明

原协议/预算/取消，由上层poison。

源码：[`src/chronaxis/execution/can_reader.py:669`](../../../src/chronaxis/execution/can_reader.py#L669)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANObservationRead-_release_current"></a>
### `CANObservationRead._release_current`

下一步前停止持有原batch再归还其装箱空间。

```python
CANObservationRead._release_current()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原抵销/取消。

源码：[`src/chronaxis/execution/can_reader.py:685`](../../../src/chronaxis/execution/can_reader.py#L685)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANObservationRead-_new_record"></a>
### `CANObservationRead._new_record`

原帧进入前先付本层记录/引用空间；全部yield先暂存再作分析层列选择。

```python
CANObservationRead._new_record()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

True有新原帧，False为CAN读取进程真实EOF。

#### 异常说明

原输入/时间/暂存错误。

本函数直接报告的具体错误：

- `SourceReadError`：CAN原yield时间回退，禁止重排。
- `SourceReadError`：目标CAN frame_id的通道/标准/FD标志歧义。
- `SourceReadError`：CAN进程没有完整EOF。

源码：[`src/chronaxis/execution/can_reader.py:690`](../../../src/chronaxis/execution/can_reader.py#L690)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANObservationRead-_deliver_message"></a>
### `CANObservationRead._deliver_message`

仅有明确消费者时构造共同消息，默认读取不增加逐帧对象。

```python
CANObservationRead._deliver_message(record, time_ns)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`record`|LegacyDecodedFrame|是|无|位置或关键字。同次原帧与解码值的冻结记录，保持输入顺序和已核对的帧属性。|
|`time_ns`|int &#124; None|是|无|位置或关键字。当前记录的实际纳秒时刻；仅明确不需要采集时间的输入诊断可为None。|

#### 返回说明

None。

#### 异常说明

投影、预算或消费者错误由read统一标记失败并清理。

源码：[`src/chronaxis/execution/can_reader.py:734`](../../../src/chronaxis/execution/can_reader.py#L734)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANObservationRead-_batch"></a>
### `CANObservationRead._batch`

为当前原帧最多batch_rows个匹配别名装箱，缺key产生明确MISSING更新。

```python
CANObservationRead._batch()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

已校验SignalBatch。

#### 异常说明

原refs/归一化/预约/协议错误。

源码：[`src/chronaxis/execution/can_reader.py:745`](../../../src/chronaxis/execution/can_reader.py#L745)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANObservationRead-__iter__"></a>
### `CANObservationRead.__iter__`

保持本次原序位置。

```python
CANObservationRead.__iter__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回当前对象本身。后续迭代或with语句使用的仍是同一个对象。

#### 异常说明

无，不启动读取。

源码：[`src/chronaxis/execution/can_reader.py:773`](../../../src/chronaxis/execution/can_reader.py#L773)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANObservationRead-__next__"></a>
### `CANObservationRead.__next__`

逐次交付当前原帧分片或独立空EOF批，真正下一次耗尽才开放完成事实。

```python
CANObservationRead.__next__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

SignalBatch。

#### 异常说明

真StopIteration/原来源/预算/取消，最高read可恢复。

源码：[`src/chronaxis/execution/can_reader.py:777`](../../../src/chronaxis/execution/can_reader.py#L777)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANObservationRead-_close_child"></a>
### `CANObservationRead._close_child`

关闭子对象；成功后才清除它的引用，失败时保留供重试。

```python
CANObservationRead._close_child(slot)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`slot`|str|是|无|位置或关键字。当前对象中用于保存资源或其费用的属性名，例如"_row_cost"；只能指向本对象实际管理的项。释放成功后才清空对应项。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原close错误。

源码：[`src/chronaxis/execution/can_reader.py:807`](../../../src/chronaxis/execution/can_reader.py#L807)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANObservationRead-_finish"></a>
### `CANObservationRead._finish`

确认读取和清理都已完成后保存观测记录，并从来源适配器的活动请求中移除本次读取。

```python
CANObservationRead._finish()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原关闭/协议/登记错误，不能伪造完成。

本函数直接报告的具体错误：

- `SourceReadError`：CAN输入尚未满足真实完成条件。
- `SourceReadError`：同次CAN消息仓尚未满足原对象及完整封口事实。
- `SourceReadError`：CAN真实输入指纹的原帧数与完成观测不符。

源码：[`src/chronaxis/execution/can_reader.py:817`](../../../src/chronaxis/execution/can_reader.py#L817)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANObservationRead-take_raw_store"></a>
### `CANObservationRead.take_raw_store`

仅完成后一次移交真实sealed store，本read后续不再关闭新父资源。

```python
CANObservationRead.take_raw_store(receiver, slot='_raw_store')
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`receiver`|资源接收对象|是|无|位置或关键字。接收当前资源所有权的父对象；其_budget必须与发送方相同，指定的接收属性必须为空。接收后由父对象负责close()和归还资源额度。|
|`slot`|str|否|'_raw_store'|位置或关键字。当前对象中用于保存资源或其费用的属性名，例如"_row_cost"；只能指向本对象实际管理的项。释放成功后才清空对应项。|

#### 返回说明

原RawFrameStore，先装父槽再撤本子槽。

#### 异常说明

状态/预算/槽错误或原安装取消；
    安装后取消仍由接收父实际槽可达，不在返回边界丢失真实费用。

本函数直接报告的具体错误：

- `ResultClosedError`：原始store未完成或已移交。
- `ValueError`：原始store移交须同账本且接收实际槽为空。

源码：[`src/chronaxis/execution/can_reader.py:852`](../../../src/chronaxis/execution/can_reader.py#L852)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANObservationRead-take_message_store"></a>
### `CANObservationRead.take_message_store`

完成后一次移交同次消息仓，父实际安装成功才解除本read责任。

```python
CANObservationRead.take_message_store(receiver, slot='_message_store')
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`receiver`|资源接收对象|是|无|位置或关键字。接收当前资源所有权的父对象；其_budget必须与发送方相同，指定的接收属性必须为空。接收后由父对象负责close()和归还资源额度。|
|`slot`|str|否|'_message_store'|位置或关键字。当前对象中用于保存资源或其费用的属性名，例如"_row_cost"；只能指向本对象实际管理的项。释放成功后才清空对应项。|

#### 返回说明

原DecodedMessageStore对象，不重建文件或复制decoded记录。

#### 异常说明

ResultClosedError为未开启、未完成或已移交；ValueError为预算/槽不符；
    父安装前后取消保原异常和can_observation_read_cleanup_owner。

源码：[`src/chronaxis/execution/can_reader.py:877`](../../../src/chronaxis/execution/can_reader.py#L877)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANObservationRead-close"></a>
### `CANObservationRead.close`

只关闭仍自有的输入/raw/消息store和所有实际费用，可持续重试。

```python
CANObservationRead.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

首个子关闭/费用取消；can_observation_read_cleanup_owner保本对象。

源码：[`src/chronaxis/execution/can_reader.py:904`](../../../src/chronaxis/execution/can_reader.py#L904)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
