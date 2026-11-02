# chronaxis.sources.signal_csv

读取明确格式的已解码CSV或TSV信号表，逐批传送归一化信号。

输入是SignalCSVSpec和显式SignalDefinition。构造与describe只检查声明；
实际迭代时才按paths原顺序打开文件，检查表头、列数和来源内时间顺序。
每行每个请求列都是一次观测，缺失文本转None并覆盖旧值，区别于旧Filter
工件中空白表示未更新的政策。数字先保留精确整数，再由选定后端归一化。

输出SignalBatch保留文件、物理行、原文本和时间量化诊断。
batch_rows限制全部列的样本总数；同时间组允许跨文件或跨批，只有更晚
原行或整个来源结束才确认进度。全部paths耗尽才报告source_eof。
请求分析域不用于裁剪原行，开始前的更新仍保留。

本实例管理活动生成器和文件句柄。正常耗尽、读取错误和显式close均尝试
释放资源，清理失败保留读取根因。本模块不调用旧CAN解码，也不重排文件。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[BatchValidator](chronaxis.sources.protocol.md#api-BatchValidator)、[CSVSourceRef](chronaxis.sources.csv_spec.md#api-CSVSourceRef)、[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)、[SignalBatch](chronaxis.sources.models.md#api-SignalBatch)、[SignalCSVSpec](chronaxis.sources.csv_spec.md#api-SignalCSVSpec)、[SignalDType](chronaxis.core.types.md#api-SignalDType)、[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)、[SourceCapabilities](chronaxis.sources.models.md#api-SourceCapabilities)、[SourceClosedError](chronaxis.sources.protocol.md#api-SourceClosedError)、[SourceDescription](chronaxis.sources.models.md#api-SourceDescription)、[SourceReadError](chronaxis.sources.protocol.md#api-SourceReadError)、[SourceRef](chronaxis.core.models.md#api-SourceRef)

## 对象导航

|对象|用途|
|---|---|
|[`choice_text`](#api-choice_text)|生成声明编码对应的CSV文本，区分布尔与整数。|
|[`SignalCSVSourceAdapter`](#api-SignalCSVSourceAdapter)|按文件声明顺序读取已解码表，每次请求独立保存进度。|
|[`SignalCSVSourceAdapter.__init__`](#api-SignalCSVSourceAdapter-__init__)|检查来源绑定和声明编码的文本歧义，不读取实际表头。|
|[`SignalCSVSourceAdapter._ensure_open`](#api-SignalCSVSourceAdapter-_ensure_open)|拒绝关闭后操作，重复close本身仍安全。|
|[`SignalCSVSourceAdapter.describe`](#api-SignalCSVSourceAdapter-describe)|返回CSV配置描述，保留尚未读取的表头和观测范围状态。|
|[`SignalCSVSourceAdapter.iter_batches`](#api-SignalCSVSourceAdapter-iter_batches)|创建读取请求生成器，第一次迭代时才打开文件。|
|[`SignalCSVSourceAdapter._request_batches`](#api-SignalCSVSourceAdapter-_request_batches)|创建独立原请求，可选向执行层传递首次扫描的最终观测候选。|
|[`SignalCSVSourceAdapter._request_batches.iterate`](#api-SignalCSVSourceAdapter-_request_batches-iterate)|转发本次请求，并在任意退出路径移除活动登记。|
|[`SignalCSVSourceAdapter._parse_value`](#api-SignalCSVSourceAdapter-_parse_value)|按缺失标记、原编码和逻辑类型解释单元格文本。|
|[`SignalCSVSourceAdapter._close_handle`](#api-SignalCSVSourceAdapter-_close_handle)|关闭一个已登记句柄，保留读取根因和清理失败证据。|
|[`SignalCSVSourceAdapter._read_resources`](#api-SignalCSVSourceAdapter-_read_resources)|为执行层封装提供独立请求的内部资源检查入口。|
|[`SignalCSVSourceAdapter._iterate`](#api-SignalCSVSourceAdapter-_iterate)|按原文件顺序逐行读取，保持跨文件的时间组和原行序号。|
|[`SignalCSVSourceAdapter._make_batch`](#api-SignalCSVSourceAdapter-_make_batch)|归一化当前缓冲中的原值，保留逐样本CSV位置。|
|[`SignalCSVSourceAdapter.close`](#api-SignalCSVSourceAdapter-close)|尝试关闭全部活动请求和句柄，最后报告最初清理失败。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from collections.abc import Iterator
from decimal import Decimal, InvalidOperation
from typing import TextIO
from ..core.binding import SignalDefinition
from ..core.types import SignalDType
from ..core.models import SourceRef
from ..core.validation import require_identifier
from ..timebase.conversion import checked_add_ns, convert_time, parse_datetime_ns
from .csv_spec import CSVSourceRef, SignalCSVSpec
from .descriptions import describe_fields, source_timebase_identity
from .models import ReadRequest, SignalBatch, SourceCapabilities, SourceDescription
from .packing import pack_decoded
from .protocol import BatchValidator, SourceClosedError, SourceReadError
```

</details>

<a id="api-choice_text"></a>
## `choice_text`

生成声明编码对应的CSV文本，区分布尔与整数。

```python
choice_text(value: int | bool | str) -> str
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; bool &#124; str|是|无|位置或关键字。SignalDefinition已检查的原编码。|

### 返回说明

str。布尔使用'true'或'false'，整数使用十进制文本，字符串保持原样。

### 异常说明

无主动异常；调用者须先保证原编码属于允许类型。

返回类型：str。

源码：[`src/chronaxis/sources/signal_csv.py:48`](../../../src/chronaxis/sources/signal_csv.py#L48)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-SignalCSVSourceAdapter"></a>
## `SignalCSVSourceAdapter`

按文件声明顺序读取已解码表，每次请求独立保存进度。

spec固定格式和路径，session_id确定会话，signals与backend决定列转换。
choices保存声明原编码的文本映射，不缓存随时间变化的值或DBC消息绑定。
closed、active和handles分别记录关闭标记、活动请求及文件句柄。
close后拒绝描述和读取。可重复扫描只表示新CSV能再次打开，不授权增加旧链扫描。

```python
SignalCSVSourceAdapter(spec: SignalCSVSpec, session_id: str, signals: tuple[SignalDefinition, ...], *, backend: str='numpy', clock_only=(), retain_original=True) -> None
```


源码：[`src/chronaxis/sources/signal_csv.py:66`](../../../src/chronaxis/sources/signal_csv.py#L66)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-SignalCSVSourceAdapter-__init__"></a>
### `SignalCSVSourceAdapter.__init__`

检查来源绑定和声明编码的文本歧义，不读取实际表头。

```python
SignalCSVSourceAdapter.__init__(spec: SignalCSVSpec, session_id: str, signals: tuple[SignalDefinition, ...], *, backend: str='numpy', clock_only=(), retain_original=True) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|[SignalCSVSpec](chronaxis.sources.csv_spec.md#api-SignalCSVSpec)|是|无|位置或关键字。已检查的表格格式、时钟和有序路径声明。|
|`session_id`|str|是|无|位置或关键字。本来源所属的会话名称。|
|`signals`|tuple[[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition), ...]|是|无|位置或关键字。当前来源的定义，输出别名须唯一。|
|`backend`|str|否|'numpy'|仅关键字。`"reference"`使用独立参考计算；`"numpy"`使用NumPy数组计算。须明确选择一种。|
|`clock_only`|tuple[str, ...]|否|()|仅关键字。仅作为时间驱动的信号别名集合；保留真实更新时刻，不解析或构造该信号的数值样本。|
|`retain_original`|bool|否|True|仅关键字。是否保留解析前原始文本；关闭时仍解析并检查输入，只是不保存原文副本。|

#### 返回说明

None。保存输入和编码映射，初始化活动资源集合。

#### 异常说明

TypeError: 配置、信号容器或后端类型不合法。
    ValueError: 会话、信号归属、别名冲突，或原码文本与缺失标记有歧义。

本函数直接报告的具体错误：

- `TypeError`：signal_csv需要带有明确类型的 spec/signals和明确backend。

#### 副作用说明

不打开文件；实际字段是否存在在迭代读取时核实。

返回类型：None。

源码：[`src/chronaxis/sources/signal_csv.py:75`](../../../src/chronaxis/sources/signal_csv.py#L75)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-SignalCSVSourceAdapter-_ensure_open"></a>
### `SignalCSVSourceAdapter._ensure_open`

拒绝关闭后操作，重复close本身仍安全。

```python
SignalCSVSourceAdapter._ensure_open() -> None
```

参数：无显式参数。


#### 参数说明

无；读取closed。

#### 返回说明

None；开放时无副作用。

#### 异常说明

SourceClosedError包含当前来源名。

返回类型：None。

源码：[`src/chronaxis/sources/signal_csv.py:127`](../../../src/chronaxis/sources/signal_csv.py#L127)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-SignalCSVSourceAdapter-describe"></a>
### `SignalCSVSourceAdapter.describe`

返回CSV配置描述，保留尚未读取的表头和观测范围状态。

```python
SignalCSVSourceAdapter.describe() -> SourceDescription
```

参数：无显式参数。


#### 参数说明

无。读取spec和signals，不打开文件或查询文件状态。

#### 返回说明

SourceDescription。定位保存有序路径、时间列、单位、偏移和时区，
    观测端点均为None，metadata_status为'declared'。

#### 异常说明

SourceClosedError: 本实例已经关闭。
    TypeError或ValueError: 字段元数据或描述模型结构错误。

返回类型：[SourceDescription](chronaxis.sources.models.md#api-SourceDescription)。

源码：[`src/chronaxis/sources/signal_csv.py:139`](../../../src/chronaxis/sources/signal_csv.py#L139)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-SignalCSVSourceAdapter-iter_batches"></a>
### `SignalCSVSourceAdapter.iter_batches`

创建读取请求生成器，第一次迭代时才打开文件。

```python
SignalCSVSourceAdapter.iter_batches(request: ReadRequest) -> Iterator[SignalBatch]
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`request`|[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)|是|无|位置或关键字。当前会话、投影别名、分析范围及总样本上限。|

#### 返回说明

Iterator[SignalBatch]。保留前置更新；所有文件耗尽后最后一批报告来源结束。

#### 异常说明

SourceClosedError: 实例已经关闭。
    ValueError: 请求类型、会话或投影别名错误。
    SourceReadError: 实际迭代时失败，附来源、文件、物理行及原异常链。

#### 副作用说明

登记活动请求；创建迭代器本身不读取表头。

返回类型：Iterator[[SignalBatch](chronaxis.sources.models.md#api-SignalBatch)]。

源码：[`src/chronaxis/sources/signal_csv.py:164`](../../../src/chronaxis/sources/signal_csv.py#L164)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-SignalCSVSourceAdapter-_request_batches"></a>
### `SignalCSVSourceAdapter._request_batches`

创建独立原请求，可选向执行层传递首次扫描的最终观测候选。

```python
SignalCSVSourceAdapter._request_batches(request: ReadRequest, observation_sink=None, resource_sink=None) -> Iterator[SignalBatch]
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`request`|[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)|是|无|位置或关键字。request为原ReadRequest|
|`observation_sink`|CSVObservationRead &#124; None|否|None|位置或关键字。可选的观测结果接收器，接收本次读取的首末时间及原始行数；None表示不额外收集观测信息。|
|`resource_sink`|_CSVRequest &#124; CSVObservationRead &#124; None|否|None|位置或关键字。可选的读取资源接收器，保留生成器和关闭责任；None使用来源的普通资源管理路径，不改变返回的样本。|

#### 返回说明

原SignalBatch生成器；构造只验证并登记，不打开CSV。

#### 异常说明

原SourceClosedError、配置和后续SourceReadError保持；可选sink原错传播。

#### 副作用说明

仅登记当前生成器，其他请求及默认预算协议保持。

返回类型：Iterator[[SignalBatch](chronaxis.sources.models.md#api-SignalBatch)]。

源码：[`src/chronaxis/sources/signal_csv.py:181`](../../../src/chronaxis/sources/signal_csv.py#L181)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-SignalCSVSourceAdapter-_request_batches-iterate"></a>
### `SignalCSVSourceAdapter._request_batches.iterate`

转发本次请求，并在任意退出路径移除活动登记。

```python
SignalCSVSourceAdapter._request_batches.iterate() -> Iterator[SignalBatch]
```

参数：无显式参数。


#### 参数说明

无。闭包保存当前request、validator及iterator。

#### 返回说明

每次产生内部读取器提供的SignalBatch，不重复读取或改动进度。

#### 异常说明

原读取错误传播；finally只移除本请求的登记。

返回类型：Iterator[[SignalBatch](chronaxis.sources.models.md#api-SignalBatch)]。

源码：[`src/chronaxis/sources/signal_csv.py:200`](../../../src/chronaxis/sources/signal_csv.py#L200)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-SignalCSVSourceAdapter-_parse_value"></a>
### `SignalCSVSourceAdapter._parse_value`

按缺失标记、原编码和逻辑类型解释单元格文本。

```python
SignalCSVSourceAdapter._parse_value(text: str, definition: SignalDefinition) -> int | float | bool | str | None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`text`|str|是|无|位置或关键字。原单元格文本，缺失标记精确匹配，不先去除空白。|
|`definition`|[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)|是|无|位置或关键字。当前字段的目标类型与显式转换声明。|

#### 返回说明

int、float、bool、str或None。缺失为None；数学整数先精确转int，
    其他数值用float表示；未声明的字符串编码可交后续归一化层判无效。

#### 异常说明

ValueError: 布尔文本不合法、数值语法错误、解析资源超限、
        整型转换前小数无法精确表示，或非零小数解析下溢。

#### 边界说明

非有限数值留给质量检查，不伪装成0。文本和整数展开分别限制4096字符或位。
    本函数只解析原值，不提前做工程缩放或有效期保持。

返回类型：int &#124; float &#124; bool &#124; str &#124; None。

源码：[`src/chronaxis/sources/signal_csv.py:234`](../../../src/chronaxis/sources/signal_csv.py#L234)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-SignalCSVSourceAdapter-_close_handle"></a>
### `SignalCSVSourceAdapter._close_handle`

关闭一个已登记句柄，保留读取根因和清理失败证据。

```python
SignalCSVSourceAdapter._close_handle(handle: TextIO, primary: BaseException | None) -> None
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`handle`|TextIO|是|无|位置或关键字。本实例打开的文件句柄。|
|`primary`|BaseException &#124; None|是|无|位置或关键字。已有读取根因；没有时为None。|

#### 返回说明

None。无论关闭成功与否都移除本句柄登记，不删除文件。

#### 异常说明

关闭错误: 没有根因或primary为GeneratorExit时原样传播；
        已有读取根因时添加附注，保留最初异常。

返回类型：None。

源码：[`src/chronaxis/sources/signal_csv.py:306`](../../../src/chronaxis/sources/signal_csv.py#L306)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-SignalCSVSourceAdapter-_read_resources"></a>
### `SignalCSVSourceAdapter._read_resources`

为执行层封装提供独立请求的内部资源检查入口。

```python
SignalCSVSourceAdapter._read_resources(request: ReadRequest)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`request`|[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)|是|无|位置或关键字。request为当前已校验请求。|

#### 返回说明

默认None，直接CSV入口行为不变。

#### 异常说明

执行层子类可在申请预算失败时抛错；不涉及旧报文reader或DBC。

源码：[`src/chronaxis/sources/signal_csv.py:333`](../../../src/chronaxis/sources/signal_csv.py#L333)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-SignalCSVSourceAdapter-_iterate"></a>
### `SignalCSVSourceAdapter._iterate`

按原文件顺序逐行读取，保持跨文件的时间组和原行序号。

```python
SignalCSVSourceAdapter._iterate(request: ReadRequest, validator: BatchValidator, observation_sink=None, resource_sink=None) -> Iterator[SignalBatch]
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`request`|[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)|是|无|位置或关键字。当前投影和有限批次样本上限。|
|`validator`|[BatchValidator](chronaxis.sources.protocol.md#api-BatchValidator)|是|无|位置或关键字。本次请求独立的跨批协议检查状态。|
|`observation_sink`|CSVObservationRead &#124; None|否|None|位置或关键字。可选的观测结果接收器，接收本次读取的首末时间及原始行数；None表示不额外收集观测信息。|
|`resource_sink`|_CSVRequest &#124; CSVObservationRead &#124; None|否|None|位置或关键字。可选的读取资源接收器，保留生成器和关闭责任；None使用来源的普通资源管理路径，不改变返回的样本。|

#### 返回说明

每次产生SignalBatch。最后一批可为空，且source_eof为True。

#### 异常说明

SourceReadError: 文件、表头、行、时间、数值或协议校验失败；
        保存来源、路径、记录结束物理行及原异常链，清理错误不覆盖根因。

#### 处理流程说明

每个文件打开后验证表头，按请求列解析原值并记录逐样本位置。
    缓冲满时先发布已有样本；更晚原行证明上一组完整。
    单文件结束不重置时间、序号或缓冲；所有文件结束后确认最后时间组。
    退出时关闭句柄和清空缓冲，不修改已经返回的数组。

返回类型：Iterator[[SignalBatch](chronaxis.sources.models.md#api-SignalBatch)]。

源码：[`src/chronaxis/sources/signal_csv.py:342`](../../../src/chronaxis/sources/signal_csv.py#L342)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-SignalCSVSourceAdapter-_make_batch"></a>
### `SignalCSVSourceAdapter._make_batch`

归一化当前缓冲中的原值，保留逐样本CSV位置。

```python
SignalCSVSourceAdapter._make_batch(pending, watermark: int | None, eof: bool, observed_end: int | None) -> SignalBatch
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`pending`|dict|是|无|位置或关键字。别名到(time_ns, sequence, 原值, CSVSourceRef)记录列表。|
|`watermark`|int &#124; None|是|无|位置或关键字。完整时间组的进度坐标，单位为纳秒。|
|`eof`|bool|是|无|位置或关键字。整个来源是否耗尽。|
|`observed_end`|int &#124; None|是|无|位置或关键字。实际观测终点纳秒坐标，未知时为None。|

#### 返回说明

SignalBatch。每列与当前位置记录对应，未知端点不补0。

#### 异常说明

TypeError、ValueError或OverflowError: 数值、时间或列结构校验失败；外层附读取位置。

#### 副作用说明

分配批次列，不额外读取输入，也不继承其他请求的信号值。

返回类型：[SignalBatch](chronaxis.sources.models.md#api-SignalBatch)。

源码：[`src/chronaxis/sources/signal_csv.py:536`](../../../src/chronaxis/sources/signal_csv.py#L536)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-SignalCSVSourceAdapter-close"></a>
### `SignalCSVSourceAdapter.close`

尝试关闭全部活动请求和句柄，最后报告最初清理失败。

```python
SignalCSVSourceAdapter.close() -> None
```

参数：无显式参数。


#### 参数说明

无。读取closed、active和handles。

#### 返回说明

None。重复调用直接返回；原输入文件保留。

#### 异常说明

SourceReadError: 至少一次清理失败，原异常链保存首错，其他失败作为附注。

#### 副作用说明

先标记关闭，再逐个清理生成器和残留句柄，最后清空资源登记。

返回类型：None。

源码：[`src/chronaxis/sources/signal_csv.py:560`](../../../src/chronaxis/sources/signal_csv.py#L560)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
