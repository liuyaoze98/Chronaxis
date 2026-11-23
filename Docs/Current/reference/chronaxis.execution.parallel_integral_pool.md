# `chronaxis.execution.parallel_integral_pool`

按文件原序交付面积事件的有限工作进程池。

每槽只拥有一份待交付块。后文件的元数据、数据块和文件错误可先到达，
但只在轮到该文件时生效；基础设施故障立即结束。所有子进程、端点及预算
归本owner，取消不会等待堵塞的数据管道自行排空。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ControlChannel](chronaxis._control_wire.md#api-ControlChannel)、[ControlProtocolError](chronaxis._control_wire.md#api-ControlProtocolError)、[SourceReadError](chronaxis.sources.protocol.md#api-SourceReadError)

## 对象导航

|对象|用途|
|---|---|
|[`_configuration_rows`](#api-_configuration_rows)|取得实际工作块行数。|
|[`_task_bytes`](#api-_task_bytes)|估算本模块已生成JSON树的实际容器费用。|
|[`_startup_costs`](#api-_startup_costs)|只读估算基础工作槽，不打开原报文。|
|[`ParallelIntegralPool`](#api-ParallelIntegralPool)|持有一个连续来源的工作槽及有界待交付状态，不累计数值总量。|
|[`ParallelIntegralPool.__init__`](#api-ParallelIntegralPool-__init__)|登记来源并预约固定声明空间，不读原文件。|
|[`ParallelIntegralPool.startup_cost`](#api-ParallelIntegralPool-startup_cost)|查询构造和启动全部槽的额外费用，供首帧前选择路径。|
|[`ParallelIntegralPool.configuration_minimum_cost`](#api-ParallelIntegralPool-configuration_minimum_cost)|查询全部工作槽数值任务的必要费用下界，用于创建进程前排除必然不足的预算。|
|[`ParallelIntegralPool.closed`](#api-ParallelIntegralPool-closed)|返回实际关闭事实。|
|[`ParallelIntegralPool.metadata`](#api-ParallelIntegralPool-metadata)|返回首文件DBC事实。|
|[`ParallelIntegralPool._dispatch`](#api-ParallelIntegralPool-_dispatch)|给空槽派发下一文件，不等待其初始化。|
|[`ParallelIntegralPool._start`](#api-ParallelIntegralPool-_start)|创建有界槽并按文件序派发。|
|[`ParallelIntegralPool._bytes`](#api-ParallelIntegralPool-_bytes)|接收已预付的一个包。|
|[`ParallelIntegralPool._configure_slot`](#api-ParallelIntegralPool-_configure_slot)|仅在READY后安装数值任务并许可首块。|
|[`ParallelIntegralPool._request`](#api-ParallelIntegralPool-_request)|授予单块额度，不允许同时保留待交付包和另一个在途包。|
|[`ParallelIntegralPool._poll_controls`](#api-ParallelIntegralPool-_poll_controls)|缓存各文件控制消息，数据错误不抢先抛给用户。|
|[`ParallelIntegralPool._wait`](#api-ParallelIntegralPool-_wait)|等待当前文件状态，并接收其他工作槽的有限通知。|
|[`ParallelIntegralPool._raise_file`](#api-ParallelIntegralPool-_raise_file)|按固定阶段保留异常类型，不按远端字符串导入任意类。|
|[`ParallelIntegralPool._accept_metadata`](#api-ParallelIntegralPool-_accept_metadata)|按文件序核共同DBC事实。|
|[`ParallelIntegralPool._accept_metadata.reserve_model`](#api-ParallelIntegralPool-_accept_metadata-reserve_model)|先预约正在展开的两份元数据图。|
|[`ParallelIntegralPool.prepare_metadata`](#api-ParallelIntegralPool-prepare_metadata)|准备首文件元数据，不读取任何原帧。|
|[`ParallelIntegralPool._configuration`](#api-ParallelIntegralPool-_configuration)|构造固定任务并计算配置实际需要的额外预约费用。|
|[`ParallelIntegralPool.configuration_cost`](#api-ParallelIntegralPool-configuration_cost)|查询configure还将预约的总费用，供首帧前预算准入。|
|[`ParallelIntegralPool.configure`](#api-ParallelIntegralPool-configure)|安装实际有效期与表达式，之后才允许读取。|
|[`ParallelIntegralPool._accept_facts`](#api-ParallelIntegralPool-_accept_facts)|按消费顺序更新同次读取得到的事实。|
|[`ParallelIntegralPool.iter_file`](#api-ParallelIntegralPool-iter_file)|按配置文件序交付固定事件；未来文件错误在轮到时才抛。|
|[`ParallelIntegralPool.close`](#api-ParallelIntegralPool-close)|关闭进程、管道和费用；失败保留真实owner以便重试。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import replace
from sys import getsizeof
from time import perf_counter
from .._control_wire import ControlChannel, ControlProtocolError
from ..results.budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..sources.models import freeze_metadata
from ..sources.protocol import SourceReadError
from .can_block_codec import decode_metadata
from .history import _metadata_bytes
from .integral_blocks import BLOCK_RAM, WIRE_LIMIT, decode_packet, pack_task
from .parallel_integral_worker import worker_main
```

</details>

<a id="api-_configuration_rows"></a>
## `_configuration_rows`

取得实际工作块行数。

```python
_configuration_rows(batch_intervals: int, calculation_count: int) -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`batch_intervals`|int|是|无|位置或关键字。用户给定的正原生整数区间批上限；实际传输块还受最多64行和计算项宽度约束，本函数与正式配置共用这一计算。|
|`calculation_count`|int|是|无|位置或关键字。同一工作块中的积分计算项数，允许非负原生整数，不接受bool；计算项越多，每行越宽，可容纳行数相应减少。|

### 返回说明

int，1至64之间且不超过用户批上限的实际工作块行数；不读取文件或修改预算。

### 异常说明

批上限不是正原生整数，或计算项数不是非负原生整数时抛ValueError。

返回类型：int。

源码：[`src/chronaxis/execution/parallel_integral_pool.py:24`](../../../src/chronaxis/execution/parallel_integral_pool.py#L24)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-_task_bytes"></a>
## `_task_bytes`

估算本模块已生成JSON树的实际容器费用。

```python
_task_bytes(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|dict &#124; list &#124; str &#124; int &#124; float &#124; bool &#124; None|是|无|位置或关键字。本模块已生成的有限JSON树，递归估算其容器和标量费用，不接受任意Python对象。|

### 返回说明

int，保守预约字节数。

### 异常说明

发现非固定类型时TypeError；不把list传给只接受冻结容器的历史估算器。

源码：[`src/chronaxis/execution/parallel_integral_pool.py:33`](../../../src/chronaxis/execution/parallel_integral_pool.py#L33)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-_startup_costs"></a>
## `_startup_costs`

只读估算基础工作槽，不打开原报文。

```python
_startup_costs(spec, signals, process_count, options)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|CANTextSpec|是|无|位置或关键字。同一来源的连续ASC/BLF输入，file_merge必须为concatenate；保留原路径、时基和读取政策。|
|`signals`|Sequence[SignalDefinition]|是|无|位置或关键字。当前任务所需的原信号定义，启动时据此加载同次DBC事实；实际有效期在数值配置前补齐。|
|`process_count`|int|是|无|位置或关键字。正原生整数工作进程上限，实际槽数不超过输入文件数，不含主进程。|
|`options`|dict[str, object]|是|无|位置或关键字。共用CANTextDecodeRead的固定读取选项；不接受非空database_context原帧捕获上下文。|

### 返回说明

tuple[int, int, int]，单位均为字节，依次为池固定费、每工作进程额度和全部槽费用；
    槽费用含每子额度与对应父接收空间，不含数值任务和READY实际图。

### 异常说明

DBC文件stat失败时OSError；静态声明估算原错误继续传播。

源码：[`src/chronaxis/execution/parallel_integral_pool.py:46`](../../../src/chronaxis/execution/parallel_integral_pool.py#L46)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelIntegralPool"></a>
## `ParallelIntegralPool`

持有一个连续来源的工作槽及有界待交付状态，不累计数值总量。

```python
ParallelIntegralPool(spec, budget, signals, *, process_count, **options)
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`_FILE_MERGE`|类属性|类成员，不作为构造参数填写|'concatenate'|本类接受的来源文件合并方式；子类按自己的模式覆盖。|

源码：[`src/chronaxis/execution/parallel_integral_pool.py:61`](../../../src/chronaxis/execution/parallel_integral_pool.py#L61)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelIntegralPool-__init__"></a>
### `ParallelIntegralPool.__init__`

登记来源并预约固定声明空间，不读原文件。

```python
ParallelIntegralPool.__init__(spec, budget, signals, *, process_count, **options)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|CANTextSpec|是|无|位置或关键字。同一来源的连续ASC/BLF输入，file_merge必须为concatenate；保留原路径、时基和读取政策。|
|`budget`|ResourceBudget|是|无|位置或关键字。父会话共享预算，本池预约声明、工作槽、任务和元数据费用并负责归还。|
|`signals`|Sequence[SignalDefinition]|是|无|位置或关键字。当前任务所需的原信号定义，启动时据此加载同次DBC事实；实际有效期在数值配置前补齐。|
|`process_count`|int|是|无|仅关键字。正原生整数工作进程上限，实际槽数不超过输入文件数，不含主进程。|
|`options`|dict[str, object]|否|{}|可变关键字。共用CANTextDecodeRead的固定读取选项；不接受非空database_context原帧捕获上下文。|

#### 返回说明

None，构造新的池owner。

#### 异常说明

非法进程数、非接续来源、空文件列表或原帧捕获上下文时ValueError；
    预算不足时BudgetExceededError，构造清理失败附parallel_integral_pool_cleanup_owner。

源码：[`src/chronaxis/execution/parallel_integral_pool.py:66`](../../../src/chronaxis/execution/parallel_integral_pool.py#L66)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelIntegralPool-startup_cost"></a>
### `ParallelIntegralPool.startup_cost`

查询构造和启动全部槽的额外费用，供首帧前选择路径。

```python
ParallelIntegralPool.startup_cost(spec, signals, *, process_count, **options)
```

装饰器：`staticmethod`。

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|CANTextSpec|是|无|位置或关键字。同一来源的连续ASC/BLF输入，file_merge必须为concatenate；保留原路径、时基和读取政策。|
|`signals`|Sequence[SignalDefinition]|是|无|位置或关键字。当前任务所需的原信号定义，启动时据此加载同次DBC事实；实际有效期在数值配置前补齐。|
|`process_count`|int|是|无|仅关键字。正原生整数工作进程上限，实际槽数不超过输入文件数，不含主进程。|
|`options`|dict[str, object]|否|{}|可变关键字。共用CANTextDecodeRead的固定读取选项；不接受非空database_context原帧捕获上下文。|

#### 返回说明

int，全部启动预约字节数，不含数值任务和READY实际图。

#### 异常说明

进程数或上下文不合法时ValueError，DBC stat失败时OSError；声明估算原错继续传播。
不创建进程、不读取报文、不修改账本。

源码：[`src/chronaxis/execution/parallel_integral_pool.py:100`](../../../src/chronaxis/execution/parallel_integral_pool.py#L100)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelIntegralPool-configuration_minimum_cost"></a>
### `ParallelIntegralPool.configuration_minimum_cost`

查询全部工作槽数值任务的必要费用下界，用于创建进程前排除必然不足的预算。

```python
ParallelIntegralPool.configuration_minimum_cost(calculation_count: int, *, process_count: int, file_count: int, batch_intervals: int=64) -> int
```

装饰器：`staticmethod`。

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`calculation_count`|int|是|无|位置或关键字。本次会话的积分计算项数量，允许非负原生整数，不接受bool；用于估算每项必须保留的状态，不是报文数。|
|`process_count`|int|是|无|仅关键字。配置允许的文件工作进程上限，必须是正原生整数；与file_count取较小值确定需要预留的工作槽数，不代表已启动进程数。|
|`file_count`|int|是|无|仅关键字。连续输入文件数量，必须是正原生整数；限制同时需要的工作槽数，不能用采样数量代替。|
|`batch_intervals`|int|否|64|仅关键字。用户指定的正原生整数区间批上限，默认64；与正式配置共用工作块行数计算，再估算每个工作槽必须持有的数值状态。|

#### 返回说明

int，父任务及全部工作槽的必要数值任务字节下界；包括固定重建和数值状态，不含DBC和声明图。用于创建进程前排除预算必然不足的情况，不能代替后续完整费用核对。

#### 异常说明

计算项数不是非负原生整数，或进程上限、文件数、批上限不是正原生整数时抛ValueError；不创建进程、任务树或修改预算。

返回类型：int。

源码：[`src/chronaxis/execution/parallel_integral_pool.py:115`](../../../src/chronaxis/execution/parallel_integral_pool.py#L115)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelIntegralPool-closed"></a>
### `ParallelIntegralPool.closed`

返回实际关闭事实。

```python
ParallelIntegralPool.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

bool。

#### 异常说明

无。

源码：[`src/chronaxis/execution/parallel_integral_pool.py:132`](../../../src/chronaxis/execution/parallel_integral_pool.py#L132)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelIntegralPool-metadata"></a>
### `ParallelIntegralPool.metadata`

返回首文件DBC事实。

```python
ParallelIntegralPool.metadata
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

Mapping[str, object]，只读冻结映射。

#### 异常说明

尚未准备时SourceReadError。

源码：[`src/chronaxis/execution/parallel_integral_pool.py:137`](../../../src/chronaxis/execution/parallel_integral_pool.py#L137)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelIntegralPool-_dispatch"></a>
### `ParallelIntegralPool._dispatch`

给空槽派发下一文件，不等待其初始化。

```python
ParallelIntegralPool._dispatch(slot, index)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`slot`|dict[str, object]|是|无|位置或关键字。池拥有的工作槽，包含进程、端点、当前文件/块序号及READY、待交付包和释放确认状态。|
|`index`|int|是|无|位置或关键字。来源声明中的零起文件序号，按配置顺序消费，不按工作进程完成次序重排。|

#### 返回说明

None。

#### 异常说明

发送失败。

源码：[`src/chronaxis/execution/parallel_integral_pool.py:142`](../../../src/chronaxis/execution/parallel_integral_pool.py#L142)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelIntegralPool-_start"></a>
### `ParallelIntegralPool._start`

创建有界槽并按文件序派发。

```python
ParallelIntegralPool._start()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

启动/预算/端点错误。

源码：[`src/chronaxis/execution/parallel_integral_pool.py:149`](../../../src/chronaxis/execution/parallel_integral_pool.py#L149)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelIntegralPool-_bytes"></a>
### `ParallelIntegralPool._bytes`

接收已预付的一个包。

```python
ParallelIntegralPool._bytes(slot, size)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`slot`|dict[str, object]|是|无|位置或关键字。池拥有的工作槽，包含进程、端点、当前文件/块序号及READY、待交付包和释放确认状态。|
|`size`|int|是|无|位置或关键字。控制通道声明的正整数包长，不能超过WIRE_LIMIT；接收后还核实际长度。|

#### 返回说明

bytes。

#### 异常说明

断连/长度错误。

源码：[`src/chronaxis/execution/parallel_integral_pool.py:182`](../../../src/chronaxis/execution/parallel_integral_pool.py#L182)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelIntegralPool-_configure_slot"></a>
### `ParallelIntegralPool._configure_slot`

仅在READY后安装数值任务并许可首块。

```python
ParallelIntegralPool._configure_slot(slot)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`slot`|dict[str, object]|是|无|位置或关键字。池拥有的工作槽，包含进程、端点、当前文件/块序号及READY、待交付包和释放确认状态。|

#### 返回说明

None。

#### 异常说明

发送错误。

源码：[`src/chronaxis/execution/parallel_integral_pool.py:192`](../../../src/chronaxis/execution/parallel_integral_pool.py#L192)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelIntegralPool-_request"></a>
### `ParallelIntegralPool._request`

授予单块额度，不允许同时保留待交付包和另一个在途包。

```python
ParallelIntegralPool._request(slot)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`slot`|dict[str, object]|是|无|位置或关键字。池拥有的工作槽，包含进程、端点、当前文件/块序号及READY、待交付包和释放确认状态。|

#### 返回说明

None。

#### 异常说明

状态错误。

源码：[`src/chronaxis/execution/parallel_integral_pool.py:202`](../../../src/chronaxis/execution/parallel_integral_pool.py#L202)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelIntegralPool-_poll_controls"></a>
### `ParallelIntegralPool._poll_controls`

缓存各文件控制消息，数据错误不抢先抛给用户。

```python
ParallelIntegralPool._poll_controls()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

bool，是否接收到至少一条控制消息。

#### 异常说明

协议不一致时ControlProtocolError，工作进程退出时SourceReadError；
    端点错误立即传播，未来文件的数据错误仅缓存，不抢先作为当前文件错误抛出。

源码：[`src/chronaxis/execution/parallel_integral_pool.py:208`](../../../src/chronaxis/execution/parallel_integral_pool.py#L208)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelIntegralPool-_wait"></a>
### `ParallelIntegralPool._wait`

等待当前文件状态，并接收其他工作槽的有限通知。

```python
ParallelIntegralPool._wait(slot, *, metadata=False, finished=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`slot`|dict[str, object]|是|无|位置或关键字。池拥有的工作槽，包含进程、端点、当前文件/块序号及READY、待交付包和释放确认状态。|
|`metadata`|bool|否|False|仅关键字。默认False；True时等待同次DBC的READY。优先于finished，不读取原帧来补元数据。|
|`finished`|bool|否|False|仅关键字。默认False；metadata为False且本项True时等待最终工作区释放确认，否则等待数据包。|

#### 返回说明

None，指定状态已到达。

#### 异常说明

当前文件错误按原阶段传播；任何工作槽的协议、端点或进程故障立即传播。

源码：[`src/chronaxis/execution/parallel_integral_pool.py:248`](../../../src/chronaxis/execution/parallel_integral_pool.py#L248)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelIntegralPool-_raise_file"></a>
### `ParallelIntegralPool._raise_file`

按固定阶段保留异常类型，不按远端字符串导入任意类。

```python
ParallelIntegralPool._raise_file(slot)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`slot`|dict[str, object]|是|无|位置或关键字。池拥有的工作槽，包含进程、端点、当前文件/块序号及READY、待交付包和释放确认状态。|

#### 返回说明

不返回。

#### 异常说明

读取/清理包装SourceReadError；
    数值阶段仅恢复明确列出的标准及项目异常，其余仍保留类型文本。

源码：[`src/chronaxis/execution/parallel_integral_pool.py:264`](../../../src/chronaxis/execution/parallel_integral_pool.py#L264)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelIntegralPool-_accept_metadata"></a>
### `ParallelIntegralPool._accept_metadata`

按文件序核共同DBC事实。

```python
ParallelIntegralPool._accept_metadata(slot)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`slot`|dict[str, object]|是|无|位置或关键字。池拥有的工作槽，包含进程、端点、当前文件/块序号及READY、待交付包和释放确认状态。|

#### 返回说明

None。

#### 异常说明

元数据不一致。

源码：[`src/chronaxis/execution/parallel_integral_pool.py:281`](../../../src/chronaxis/execution/parallel_integral_pool.py#L281)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelIntegralPool-_accept_metadata-reserve_model"></a>
### `ParallelIntegralPool._accept_metadata.reserve_model`

先预约正在展开的两份元数据图。

```python
ParallelIntegralPool._accept_metadata.reserve_model(size)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`size`|int|是|无|位置或关键字。单份元数据展开图的保守字节数；预约同时存在的解码图、冻结图及已持有首文件图。|

#### 返回说明

None。

#### 异常说明

预算原错。

源码：[`src/chronaxis/execution/parallel_integral_pool.py:284`](../../../src/chronaxis/execution/parallel_integral_pool.py#L284)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelIntegralPool-prepare_metadata"></a>
### `ParallelIntegralPool.prepare_metadata`

准备首文件元数据，不读取任何原帧。

```python
ParallelIntegralPool.prepare_metadata()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

冻结元数据。

#### 异常说明

启动/文件错。

源码：[`src/chronaxis/execution/parallel_integral_pool.py:299`](../../../src/chronaxis/execution/parallel_integral_pool.py#L299)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelIntegralPool-_configuration"></a>
### `ParallelIntegralPool._configuration`

构造固定任务并计算配置实际需要的额外预约费用。

```python
ParallelIntegralPool._configuration(definitions, expressions, specs, binding, session_id, derived, domain, batch_intervals, step_ns=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`definitions`|tuple[SignalDefinition, ...]|是|无|位置或关键字。本次积分实际依赖的信号定义，按冻结顺序排列；已由同次DBC事实补齐有效期。|
|`expressions`|tuple[StaticExpression, ...]|是|无|位置或关键字。已验证的简单数值表达式，与积分计算项顺序一致。|
|`specs`|tuple[CalculationDefinition, ...]|是|无|位置或关键字。与表达式逐项对应的会话积分请求，保留请求单位及完整性规则。|
|`binding`|SameFrameBinding|是|无|位置或关键字。首帧前由同次DBC元数据证明的唯一共同报文定位。|
|`session_id`|str|是|无|位置或关键字。本次连续分析的会话名称，文件切换时保持不变。|
|`derived`|tuple[DerivedDefinition, ...]|是|无|位置或关键字。原计划的派生声明，默认空tuple；用于核对表达式身份，不新增输出。|
|`domain`|Interval &#124; None|是|无|位置或关键字。实际纳秒坐标中的请求范围；None表示按已有观测范围处理，不创建第二套时钟。|
|`batch_intervals`|int|是|无|位置或关键字。用户指定的正整数区间批上限，默认64；传输部分进一步按64项及字节预算缩小，不改变父进程全局批界。|
|`step_ns`|int &#124; None|否|None|位置或关键字。父积分器共用的间隔，原样写入固定任务；None为实际间隔。|

#### 返回说明

tuple[dict, int, int]，依次为固定task、父任务字节费和每子数值/任务额外字节费；
    不包含已预约的启动费。

#### 异常说明

批上限非法时ValueError；原声明展开或静态费用错误继续传播。

源码：[`src/chronaxis/execution/parallel_integral_pool.py:309`](../../../src/chronaxis/execution/parallel_integral_pool.py#L309)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelIntegralPool-configuration_cost"></a>
### `ParallelIntegralPool.configuration_cost`

查询configure还将预约的总费用，供首帧前预算准入。

```python
ParallelIntegralPool.configuration_cost(definitions, expressions, specs, binding, session_id, *, derived=(), domain=None, batch_intervals=64, step_ns=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`definitions`|tuple[SignalDefinition, ...]|是|无|位置或关键字。本次积分实际依赖的信号定义，按冻结顺序排列；已由同次DBC事实补齐有效期。|
|`expressions`|tuple[StaticExpression, ...]|是|无|位置或关键字。已验证的简单数值表达式，与积分计算项顺序一致。|
|`specs`|tuple[CalculationDefinition, ...]|是|无|位置或关键字。与表达式逐项对应的会话积分请求，保留请求单位及完整性规则。|
|`binding`|SameFrameBinding|是|无|位置或关键字。首帧前由同次DBC元数据证明的唯一共同报文定位。|
|`session_id`|str|是|无|位置或关键字。本次连续分析的会话名称，文件切换时保持不变。|
|`derived`|tuple[DerivedDefinition, ...]|否|()|仅关键字。原计划的派生声明，默认空tuple；用于核对表达式身份，不新增输出。|
|`domain`|Interval &#124; None|否|None|仅关键字。实际纳秒坐标中的请求范围；None表示按已有观测范围处理，不创建第二套时钟。|
|`batch_intervals`|int|否|64|仅关键字。用户指定的正整数区间批上限，默认64；传输部分进一步按64项及字节预算缩小，不改变父进程全局批界。|
|`step_ns`|int &#124; None|否|None|仅关键字。与随后configure相同的共用间隔；只用于构造同一任务以计算费用，不安装任务。|

#### 返回说明

int，父任务费与全部工作槽额外费之和，单位字节；不修改账本、不启动读取。

#### 异常说明

声明错误；调用方应在原计划已有固定工作区内使用短暂的任务结构。

源码：[`src/chronaxis/execution/parallel_integral_pool.py:331`](../../../src/chronaxis/execution/parallel_integral_pool.py#L331)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelIntegralPool-configure"></a>
### `ParallelIntegralPool.configure`

安装实际有效期与表达式，之后才允许读取。

```python
ParallelIntegralPool.configure(definitions, expressions, specs, binding, session_id, *, derived=(), domain=None, batch_intervals=64, step_ns=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`definitions`|tuple[SignalDefinition, ...]|是|无|位置或关键字。本次积分实际依赖的信号定义，按冻结顺序排列；已由同次DBC事实补齐有效期。|
|`expressions`|tuple[StaticExpression, ...]|是|无|位置或关键字。已验证的简单数值表达式，与积分计算项顺序一致。|
|`specs`|tuple[CalculationDefinition, ...]|是|无|位置或关键字。与表达式逐项对应的会话积分请求，保留请求单位及完整性规则。|
|`binding`|SameFrameBinding|是|无|位置或关键字。首帧前由同次DBC元数据证明的唯一共同报文定位。|
|`session_id`|str|是|无|位置或关键字。本次连续分析的会话名称，文件切换时保持不变。|
|`derived`|tuple[DerivedDefinition, ...]|否|()|仅关键字。原计划的派生声明，默认空tuple；用于核对表达式身份，不新增输出。|
|`domain`|Interval &#124; None|否|None|仅关键字。实际纳秒坐标中的请求范围；None表示按已有观测范围处理，不创建第二套时钟。|
|`batch_intervals`|int|否|64|仅关键字。用户指定的正整数区间批上限，默认64；传输部分进一步按64项及字节预算缩小，不改变父进程全局批界。|
|`step_ns`|int &#124; None|否|None|仅关键字。父积分器共用的间隔，随任务发给每个工作进程；None为实际间隔，否则为固定间隔纳秒。|

#### 返回说明

None。

#### 异常说明

未准备、重复安装或预算/声明错误。

源码：[`src/chronaxis/execution/parallel_integral_pool.py:342`](../../../src/chronaxis/execution/parallel_integral_pool.py#L342)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelIntegralPool-_accept_facts"></a>
### `ParallelIntegralPool._accept_facts`

按消费顺序更新同次读取得到的事实。

```python
ParallelIntegralPool._accept_facts(index, facts)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`index`|int|是|无|位置或关键字。来源声明中的零起文件序号，按配置顺序消费，不按工作进程完成次序重排。|
|`facts`|dict[str, object]|是|无|位置或关键字。同次读取事实：原帧/解码累计数、实际首末纳秒、Decimal顺序时间及compatibility_fields tuple。|

#### 返回说明

None。

#### 异常说明

计数或字段回退。

源码：[`src/chronaxis/execution/parallel_integral_pool.py:366`](../../../src/chronaxis/execution/parallel_integral_pool.py#L366)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelIntegralPool-iter_file"></a>
### `ParallelIntegralPool.iter_file`

按配置文件序交付固定事件；未来文件错误在轮到时才抛。

```python
ParallelIntegralPool.iter_file(index)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`index`|int|是|无|位置或关键字。来源声明中的零起文件序号，按配置顺序消费，不按工作进程完成次序重排。|

#### 返回说明

生成器，依次产生FileIntegralHead、IntegralTermsChunk、FileIntegralTail或FileIntegralFrontier；
    收到eof数据包后仍等待finished资源释放确认，之后才自然结束并复用槽。

#### 异常说明

调用次序不合法时ValueError；文件数据错误按阶段传播，协议故障时ControlProtocolError；
    失败自动清理自有进程与费用。

源码：[`src/chronaxis/execution/parallel_integral_pool.py:391`](../../../src/chronaxis/execution/parallel_integral_pool.py#L391)（行号对应 Chronaxis 0.1.0.dev6 源码）。

<a id="api-ParallelIntegralPool-close"></a>
### `ParallelIntegralPool.close`

关闭进程、管道和费用；失败保留真实owner以便重试。

```python
ParallelIntegralPool.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None，可重复调用。

#### 异常说明

持续退出/关闭/预算释放失败。

源码：[`src/chronaxis/execution/parallel_integral_pool.py:434`](../../../src/chronaxis/execution/parallel_integral_pool.py#L434)（行号对应 Chronaxis 0.1.0.dev6 源码）。
