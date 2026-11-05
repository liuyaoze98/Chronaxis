# `chronaxis.execution.text_can_reader`

把新ASC/原始CSV的同次解码接到公共信号批次和真实观测协议。

适配器声明字段和时基，不读文件；每个TextCANObservationRead拥有独立解析器、
有限原帧块和预算。每次交付同时段各别名批，总样本数不超过batch_rows；同一时刻别名未全部
交付前不越过其watermark。完整EOF并关闭解析器后才开放观测证明和可选原帧仓。
原帧仓仅显式导出时创建，共用已解码值，不另扫描原文件。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[BatchValidator](chronaxis.sources.protocol.md#api-BatchValidator)、[CANObservation](chronaxis.execution.can_reader.md#api-CANObservation)、[CANTextDecodeRead](chronaxis.sources.text_can_decode.md#api-CANTextDecodeRead)、[CANTextSpec](chronaxis.sources.text_can_spec.md#api-CANTextSpec)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[SignalBatch](chronaxis.sources.models.md#api-SignalBatch)、[SourceCapabilities](chronaxis.sources.models.md#api-SourceCapabilities)、[SourceClosedError](chronaxis.sources.protocol.md#api-SourceClosedError)、[SourceDescription](chronaxis.sources.models.md#api-SourceDescription)、[TextFrameStore](chronaxis.execution.frame_capture.md#api-TextFrameStore)

## 对象导航

|对象|用途|
|---|---|
|[`BudgetedTextCANSourceAdapter`](#api-BudgetedTextCANSourceAdapter)|拥有静态描述和活read集合，借用导出DBC上下文；关闭不会释放借用上下文。|
|[`BudgetedTextCANSourceAdapter.__init__`](#api-BudgetedTextCANSourceAdapter-__init__)|构造声明，不读取输入。|
|[`BudgetedTextCANSourceAdapter.retain_raw_frames`](#api-BudgetedTextCANSourceAdapter-retain_raw_frames)|返回本来源冻结的原帧保存选择。|
|[`BudgetedTextCANSourceAdapter._ensure_open`](#api-BudgetedTextCANSourceAdapter-_ensure_open)|拒绝使用已关闭适配器。|
|[`BudgetedTextCANSourceAdapter.describe`](#api-BudgetedTextCANSourceAdapter-describe)|返回静态字段及时间声明。|
|[`BudgetedTextCANSourceAdapter.iter_batches_with_observation`](#api-BudgetedTextCANSourceAdapter-iter_batches_with_observation)|创建具有同次观测的独立read。|
|[`BudgetedTextCANSourceAdapter.iter_batches`](#api-BudgetedTextCANSourceAdapter-iter_batches)|沿同一批次合同创建read，不另读输入。|
|[`BudgetedTextCANSourceAdapter.close`](#api-BudgetedTextCANSourceAdapter-close)|关闭所有本来源活read，再释放描述费用。|
|[`TextCANObservationRead`](#api-TextCANObservationRead)|拥有一个有限原帧块和一个归一化批，完整EOF前不开放完成事实。|
|[`TextCANObservationRead.__init__`](#api-TextCANObservationRead-__init__)|验证原会话/投影并构造未开始的解码器。|
|[`TextCANObservationRead.closed`](#api-TextCANObservationRead-closed)|返回真实关闭状态。|
|[`TextCANObservationRead.failed`](#api-TextCANObservationRead-failed)|返回当前读取是否失败。|
|[`TextCANObservationRead.exhausted`](#api-TextCANObservationRead-exhausted)|返回完整EOF及解析器关闭事实。|
|[`TextCANObservationRead.observation`](#api-TextCANObservationRead-observation)|仅交付本read已完成的真实观测。|
|[`TextCANObservationRead.observed_bounds`](#api-TextCANObservationRead-observed_bounds)|返回同次解析已经看到的首末时间，不额外扫描或冒充EOF。|
|[`TextCANObservationRead.runtime_metadata`](#api-TextCANObservationRead-runtime_metadata)|交付同次DBC身份与解码次数。|
|[`TextCANObservationRead.prepare_metadata`](#api-TextCANObservationRead-prepare_metadata)|在读取前取得同次DBC周期，不冒充最终解码计数。|
|[`TextCANObservationRead.__iter__`](#api-TextCANObservationRead-__iter__)|返回独立游标。|
|[`TextCANObservationRead._accept`](#api-TextCANObservationRead-_accept)|按既有批合同核同一时刻组，保留所需pending费用。|
|[`TextCANObservationRead._fill`](#api-TextCANObservationRead-_fill)|按全部别名的样本容量取有限原记录，所有值只解码一次。|
|[`TextCANObservationRead.__next__`](#api-TextCANObservationRead-__next__)|交付全局时间非递减的有界批，最终EOF后保完成事实。|
|[`TextCANObservationRead._finish`](#api-TextCANObservationRead-_finish)|封口可选原帧仓，解析器真正关闭后提交完整事实。|
|[`TextCANObservationRead.take_raw_store`](#api-TextCANObservationRead-take_raw_store)|移交本read的同次封口原帧仓。|
|[`TextCANObservationRead.close`](#api-TextCANObservationRead-close)|关闭实际解析器/原帧仓并释放自身费用，不释放共享DBC。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from pathlib import Path
from uuid import uuid4
from ..core.validation import require_identifier
from ..sources.text_can_spec import CANTextSpec
from ..sources.text_can_decode import CANTextDecodeRead, pack_text_records
from ..sources.descriptions import describe_fields, source_timebase_identity
from ..sources.models import ReadRequest, SignalBatch, SourceDescription, SourceCapabilities, freeze_metadata
from ..sources.protocol import BatchValidator, SourceClosedError
from ..results.budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..results.errors import ResultClosedError
from .can_reader import CANObservation
from .frame_capture import TextFrameStore
from .history import _metadata_bytes, _pending_bytes
```

</details>

<a id="api-BudgetedTextCANSourceAdapter"></a>
## `BudgetedTextCANSourceAdapter`

拥有静态描述和活read集合，借用导出DBC上下文；关闭不会释放借用上下文。

```python
BudgetedTextCANSourceAdapter(budget, spec, session_id, signals, *, backend='numpy', work_dir=None, retain_raw_frames=False, database_context=None, message_consumer=None, cycle_fields=(), metadata_fields=(), message_keys=(), integrity=True, trace=True, selected_ids=None, time_frame_ids=None)
```


源码：[`src/chronaxis/execution/text_can_reader.py:25`](../../../src/chronaxis/execution/text_can_reader.py#L25)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BudgetedTextCANSourceAdapter-__init__"></a>
### `BudgetedTextCANSourceAdapter.__init__`

构造声明，不读取输入。

```python
BudgetedTextCANSourceAdapter.__init__(budget, spec, session_id, signals, *, backend='numpy', work_dir=None, retain_raw_frames=False, database_context=None, message_consumer=None, cycle_fields=(), metadata_fields=(), message_keys=(), integrity=True, trace=True, selected_ids=None, time_frame_ids=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|ResourceBudget|是|无|位置或关键字。本次运行共用的ResourceBudget对象，用于检查内存和临时磁盘用量。当前对象在分配前申请额度，用完后归还；同一次运行的组件应使用同一个对象。|
|`spec`|[CANTextSpec](chronaxis.sources.text_can_spec.md#api-CANTextSpec)|是|无|位置或关键字。预算/spec/会话/定义、后端、可选暂存目录及DBC上下文。|
|`session_id`|str|是|无|位置或关键字。本次会话的名字，用来防止把不同试验的数据混在一起。|
|`signals`|tuple[SignalDefinition, ...]|是|无|位置或关键字。当前来源需要接入分析的SignalDefinition元组，明确别名与CAN字段。|
|`backend`|str|否|'numpy'|仅关键字。`"reference"`使用独立参考计算；`"numpy"`使用NumPy数组计算。须明确选择一种。|
|`work_dir`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) &#124; None|否|None|仅关键字。本次运行独占的工作目录，用来保存中间文件。自行指定时要求尚不存在；不会覆盖旧目录。None让入口自动创建唯一目录。|
|`retain_raw_frames`|bool|否|False|仅关键字。是否保留原始报文用于后续导出；False不创建这份原帧历史。|
|`database_context`|FrameDBCContext &#124; None|否|None|仅关键字。可借用的已加载DBC上下文；None表示未提供，按文本来源流程加载所需数据库。|
|`message_consumer`|Callable[[LegacyDecodedUpdate], None] &#124; None|否|None|仅关键字。接收当前所需报文解码更新的函数；None不启用额外逐消息交付。|
|`cycle_fields`|tuple[LegacyCANField, ...]|否|()|仅关键字。需要读取DBC周期的字段定位集合；初始化时读取元数据，不逐帧读取DBC。|
|`metadata_fields`|tuple[LegacyCANField, ...]|否|()|仅关键字。仅请求驱动信号的DBC候选声明，默认空tuple；用于确认实际帧身份，不请求信号值，也不增加普通样本或值解码。|
|`message_keys`|tuple[tuple[int, int, bool, bool], ...]|否|()|仅关键字。所需报文定位，依次为通道、ID、扩展帧标志、FD标志；空集合表示没有额外逐消息需求。|
|`integrity`|bool|否|True|仅关键字。是否执行本对象的额外内容摘要或认证核验；False仍保留结构、类型、预算及必要文件变化检查。|
|`trace`|bool|否|True|仅关键字。是否保存此功能的详细来源或输入追溯；False在生成处跳过，不能先构造再隐藏。|
|`selected_ids`|tuple[int, ...] &#124; None|否|None|仅关键字。需要处理的报文ID；默认None读取全部记录。仅在不需要完整原帧和来源时间的消息分析路径使用：原始CSV先读ID，未匹配时跳过该行的时间、载荷和帧型解析；目标记录仍完整校验。ASC路径不使用此筛选。|
|`time_frame_ids`|tuple[int, ...] &#124; None|否|None|仅关键字。本次需要检查时间顺序的CAN报文ID；同时限定来源的内部通道。None检查完整序列；空元组不交付帧但仍同次统计来源范围。完整检查或原帧导出不得传选择集合。|

#### 返回说明

adapter。

#### 异常说明

配置/预算错。

本函数直接报告的具体错误：

- `ValueError`：文本CAN来源配置或后端非法。
- `ValueError`：显式原帧保存需要新工作目录。

源码：[`src/chronaxis/execution/text_can_reader.py:28`](../../../src/chronaxis/execution/text_can_reader.py#L28)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BudgetedTextCANSourceAdapter-retain_raw_frames"></a>
### `BudgetedTextCANSourceAdapter.retain_raw_frames`

返回本来源冻结的原帧保存选择。

```python
BudgetedTextCANSourceAdapter.retain_raw_frames
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示保存原始报文供后续导出；False表示不为此目的保存原始报文。

#### 异常说明

无。

源码：[`src/chronaxis/execution/text_can_reader.py:86`](../../../src/chronaxis/execution/text_can_reader.py#L86)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BudgetedTextCANSourceAdapter-_ensure_open"></a>
### `BudgetedTextCANSourceAdapter._ensure_open`

拒绝使用已关闭适配器。

```python
BudgetedTextCANSourceAdapter._ensure_open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

SourceClosedError。

本函数直接报告的具体错误：

- `SourceClosedError`：文本CAN来源已关闭。

源码：[`src/chronaxis/execution/text_can_reader.py:91`](../../../src/chronaxis/execution/text_can_reader.py#L91)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BudgetedTextCANSourceAdapter-describe"></a>
### `BudgetedTextCANSourceAdapter.describe`

返回静态字段及时间声明。

```python
BudgetedTextCANSourceAdapter.describe()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

SourceDescription。

#### 异常说明

已关闭。

源码：[`src/chronaxis/execution/text_can_reader.py:97`](../../../src/chronaxis/execution/text_can_reader.py#L97)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BudgetedTextCANSourceAdapter-iter_batches_with_observation"></a>
### `BudgetedTextCANSourceAdapter.iter_batches_with_observation`

创建具有同次观测的独立read。

```python
BudgetedTextCANSourceAdapter.iter_batches_with_observation(request)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`request`|[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)|是|无|位置或关键字。本次ReadRequest，声明会话、所需信号和分批大小，并据此读取文本CAN。|

#### 返回说明

read。

#### 异常说明

合同/预算错及可恢复owner。

本函数直接报告的具体错误：

- `ResultClosedError`：文本CAN仍有未返回read待清理。

源码：[`src/chronaxis/execution/text_can_reader.py:102`](../../../src/chronaxis/execution/text_can_reader.py#L102)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BudgetedTextCANSourceAdapter-iter_batches"></a>
### `BudgetedTextCANSourceAdapter.iter_batches`

沿同一批次合同创建read，不另读输入。

```python
BudgetedTextCANSourceAdapter.iter_batches(request)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`request`|[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)|是|无|位置或关键字。本次ReadRequest；本入口只返回信号批次，带进度的完整入口见iter_batches_with_observation。|

#### 返回说明

read。

#### 异常说明

原工厂错。

源码：[`src/chronaxis/execution/text_can_reader.py:121`](../../../src/chronaxis/execution/text_can_reader.py#L121)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-BudgetedTextCANSourceAdapter-close"></a>
### `BudgetedTextCANSourceAdapter.close`

关闭所有本来源活read，再释放描述费用。

```python
BudgetedTextCANSourceAdapter.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

关闭/费用错可重试。

源码：[`src/chronaxis/execution/text_can_reader.py:126`](../../../src/chronaxis/execution/text_can_reader.py#L126)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TextCANObservationRead"></a>
## `TextCANObservationRead`

拥有一个有限原帧块和一个归一化批，完整EOF前不开放完成事实。

```python
TextCANObservationRead(owner, request)
```


源码：[`src/chronaxis/execution/text_can_reader.py:140`](../../../src/chronaxis/execution/text_can_reader.py#L140)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TextCANObservationRead-__init__"></a>
### `TextCANObservationRead.__init__`

验证原会话/投影并构造未开始的解码器。

```python
TextCANObservationRead.__init__(owner, request)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|[BudgetedTextCANSourceAdapter](chronaxis.execution.text_can_reader.md#api-BudgetedTextCANSourceAdapter)|是|无|位置或关键字。仍处于打开状态的文本CAN来源适配器，本读取使用它的配置和资源额度。|
|`request`|[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)|是|无|位置或关键字。本次ReadRequest，必须与所用适配器和会话一致。|

#### 返回说明

read。

#### 异常说明

合同/预算错。

本函数直接报告的具体错误：

- `ValueError`：文本CAN读取需要原会话ReadRequest。
- `ValueError`：文本CAN请求包含未声明信号。

源码：[`src/chronaxis/execution/text_can_reader.py:143`](../../../src/chronaxis/execution/text_can_reader.py#L143)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TextCANObservationRead-closed"></a>
### `TextCANObservationRead.closed`

返回真实关闭状态。

```python
TextCANObservationRead.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/execution/text_can_reader.py:184`](../../../src/chronaxis/execution/text_can_reader.py#L184)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TextCANObservationRead-failed"></a>
### `TextCANObservationRead.failed`

返回当前读取是否失败。

```python
TextCANObservationRead.failed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象已记录处理失败；False表示尚未记录失败。

#### 异常说明

无。

源码：[`src/chronaxis/execution/text_can_reader.py:190`](../../../src/chronaxis/execution/text_can_reader.py#L190)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TextCANObservationRead-exhausted"></a>
### `TextCANObservationRead.exhausted`

返回完整EOF及解析器关闭事实。

```python
TextCANObservationRead.exhausted
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示输入或结果已正常读完；False表示尚未正常读完。发生异常不等于正常读完。

#### 异常说明

无。

源码：[`src/chronaxis/execution/text_can_reader.py:196`](../../../src/chronaxis/execution/text_can_reader.py#L196)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TextCANObservationRead-observation"></a>
### `TextCANObservationRead.observation`

仅交付本read已完成的真实观测。

```python
TextCANObservationRead.observation
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

CANObservation。

#### 异常说明

未完成/失败。

本函数直接报告的具体错误：

- `ResultClosedError`：文本CAN观测尚未完成。

源码：[`src/chronaxis/execution/text_can_reader.py:202`](../../../src/chronaxis/execution/text_can_reader.py#L202)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TextCANObservationRead-observed_bounds"></a>
### `TextCANObservationRead.observed_bounds`

返回同次解析已经看到的首末时间，不额外扫描或冒充EOF。

```python
TextCANObservationRead.observed_bounds
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

(first,last)，空输入为None。

#### 异常说明

失败/关闭状态拒绝借读。

源码：[`src/chronaxis/execution/text_can_reader.py:210`](../../../src/chronaxis/execution/text_can_reader.py#L210)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TextCANObservationRead-runtime_metadata"></a>
### `TextCANObservationRead.runtime_metadata`

交付同次DBC身份与解码次数。

```python
TextCANObservationRead.runtime_metadata
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

冻结元数据。

#### 异常说明

未完成。

源码：[`src/chronaxis/execution/text_can_reader.py:222`](../../../src/chronaxis/execution/text_can_reader.py#L222)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TextCANObservationRead-prepare_metadata"></a>
### `TextCANObservationRead.prepare_metadata`

在读取前取得同次DBC周期，不冒充最终解码计数。

```python
TextCANObservationRead.prepare_metadata()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

冻结DBC事实。

#### 异常说明

关闭/失败或启动原错；清理由本read负责。

源码：[`src/chronaxis/execution/text_can_reader.py:228`](../../../src/chronaxis/execution/text_can_reader.py#L228)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TextCANObservationRead-__iter__"></a>
### `TextCANObservationRead.__iter__`

返回独立游标。

```python
TextCANObservationRead.__iter__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回当前对象本身。后续迭代或with语句使用的仍是同一个对象。

#### 异常说明

无。

源码：[`src/chronaxis/execution/text_can_reader.py:245`](../../../src/chronaxis/execution/text_can_reader.py#L245)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TextCANObservationRead-_accept"></a>
### `TextCANObservationRead._accept`

按既有批合同核同一时刻组，保留所需pending费用。

```python
TextCANObservationRead._accept(batch)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`batch`|[SignalBatch](chronaxis.sources.models.md#api-SignalBatch)|是|无|位置或关键字。已读取的一批SignalBatch，更新观测进度并核对批次顺序。|

#### 返回说明

原批。

#### 异常说明

校验/预算错。

源码：[`src/chronaxis/execution/text_can_reader.py:250`](../../../src/chronaxis/execution/text_can_reader.py#L250)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TextCANObservationRead-_fill"></a>
### `TextCANObservationRead._fill`

按全部别名的样本容量取有限原记录，所有值只解码一次。

```python
TextCANObservationRead._fill()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原读/预算/暂存错。

源码：[`src/chronaxis/execution/text_can_reader.py:261`](../../../src/chronaxis/execution/text_can_reader.py#L261)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TextCANObservationRead-__next__"></a>
### `TextCANObservationRead.__next__`

交付全局时间非递减的有界批，最终EOF后保完成事实。

```python
TextCANObservationRead.__next__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

SignalBatch。

#### 异常说明

EOF/原读/预算/合同错。

本函数直接报告的具体错误：

- `ResultClosedError`：失败的文本CAN读取只能清理。

源码：[`src/chronaxis/execution/text_can_reader.py:284`](../../../src/chronaxis/execution/text_can_reader.py#L284)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TextCANObservationRead-_finish"></a>
### `TextCANObservationRead._finish`

封口可选原帧仓，解析器真正关闭后提交完整事实。

```python
TextCANObservationRead._finish()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

封口/关闭/预算错。

本函数直接报告的具体错误：

- `ValueError`：文本原始解析器没有真正到达EOF。

源码：[`src/chronaxis/execution/text_can_reader.py:320`](../../../src/chronaxis/execution/text_can_reader.py#L320)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TextCANObservationRead-take_raw_store"></a>
### `TextCANObservationRead.take_raw_store`

移交本read的同次封口原帧仓。

```python
TextCANObservationRead.take_raw_store(receiver, slot)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`receiver`|资源接收对象|是|无|位置或关键字。接收当前资源所有权的父对象；其_budget必须与发送方相同，指定的接收属性必须为空。接收后由父对象负责close()和归还资源额度。|
|`slot`|str|是|无|位置或关键字。当前对象中用于保存资源或其费用的属性名，例如"_row_cost"；只能指向本对象实际管理的项。释放成功后才清空对应项。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

未完成/已有责任。

本函数直接报告的具体错误：

- `ValueError`：文本原帧仓不能移交。

源码：[`src/chronaxis/execution/text_can_reader.py:338`](../../../src/chronaxis/execution/text_can_reader.py#L338)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-TextCANObservationRead-close"></a>
### `TextCANObservationRead.close`

关闭实际解析器/原帧仓并释放自身费用，不释放共享DBC。

```python
TextCANObservationRead.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原清理错可恢复。

源码：[`src/chronaxis/execution/text_can_reader.py:346`](../../../src/chronaxis/execution/text_can_reader.py#L346)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
