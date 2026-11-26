# `chronaxis.execution.parallel_integral_worker`

一个积分工作槽按许可读取文件并生成原序面积块或同一时刻组点块。

读取器和数值状态在子进程中关闭，父进程拥有整个进程生命周期。文件错误
先保留已经形成的边界/面积前缀，下一次许可才交付错误。eof数据包晚于
读取器和数值owner关闭，finished确认再证明包工作区已释放。没有许可时
不继续读取，不生成面积文件或最终结果。

任务的mode决定数值owner：terms构造FileIntegralTerms并发P5I1面积包（concatenate）；
points构造FileGroupPoints并发P5G1组点包（time_order，PERF-P5-ORDER-01）。
两种模式共用命令协议、许可与释放次序。points模式的错误信息只带str(错误)，
不附加notes，与现有time_order读取的格式一致；其父进程把各阶段错误都按读取段报告。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CANTextDecodeRead](chronaxis.sources.text_can_decode.md#api-CANTextDecodeRead)、[ControlChannel](chronaxis._control_wire.md#api-ControlChannel)、[FileGroupPoints](chronaxis.execution.file_group_points.md#api-FileGroupPoints)、[FileIntegralTerms](chronaxis.execution.file_integral_terms.md#api-FileIntegralTerms)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)

## 对象导航

|对象|用途|
|---|---|
|[`_points`](#api-_points)|判断数值owner是否为组点模式。|
|[`_limits`](#api-_limits)|取得当前模式的事件费用函数、事实费用函数和单包事件上限。|
|[`_facts`](#api-_facts)|摘取同次文件事实。|
|[`_error_text`](#api-_error_text)|保留原错误及有限清理说明。|
|[`_close_file`](#api-_close_file)|关闭数值和读取资源，保留首个错误。|
|[`read_events`](#api-read_events)|读取一批原记录，返回已形成事件及真实EOF或原错误。|
|[`read_events.append`](#api-read_events-append)|只为实际事件保存同次事实。|
|[`take_events`](#api-take_events)|从已形成前缀中取得一份有界多事件包，不触发下一次读取。|
|[`worker_main`](#api-worker_main)|处理固定文件、配置及next命令，不创建子工作进程。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from time import perf_counter
from .._control_wire import ControlChannel
from ..results.budget import ResourceBudget
from ..sources.text_can_decode import CANTextDecodeRead
from .can_block_codec import encode_metadata
from .integral_blocks import BLOCK_RAM, WIRE_LIMIT, MAX_EVENTS, MAX_POINTS, MODEL_LIMIT, event_cost, facts_cost, point_cost, point_facts_cost, encode_packet, encode_points, restore_task, task_mode
from .parallel_can_worker import plain
```

</details>

<a id="api-_points"></a>
## `_points`

判断数值owner是否为组点模式。

```python
_points(terms)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`terms`|[FileIntegralTerms](chronaxis.execution.file_integral_terms.md#api-FileIntegralTerms) &#124; [FileGroupPoints](chronaxis.execution.file_group_points.md#api-FileGroupPoints)|是|无|位置或关键字。当前文件的数值owner。|

### 返回说明

bool。

### 异常说明

无。

源码：[`src/chronaxis/execution/parallel_integral_worker.py:28`](../../../src/chronaxis/execution/parallel_integral_worker.py#L28)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-_limits"></a>
## `_limits`

取得当前模式的事件费用函数、事实费用函数和单包事件上限。

```python
_limits(terms)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`terms`|[FileIntegralTerms](chronaxis.execution.file_integral_terms.md#api-FileIntegralTerms) &#124; [FileGroupPoints](chronaxis.execution.file_group_points.md#api-FileGroupPoints)|是|无|位置或关键字。当前文件的数值owner，决定使用哪种包的费用和单包上限。|

### 返回说明

tuple，依次为event费用函数、facts费用函数和单包最大事件数int。

### 异常说明

无；未知owner按面积模式处理，由原编码器拒绝未知事件。

源码：[`src/chronaxis/execution/parallel_integral_worker.py:34`](../../../src/chronaxis/execution/parallel_integral_worker.py#L34)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-_facts"></a>
## `_facts`

摘取同次文件事实。

```python
_facts(reader, terms, compatibility)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`reader`|[CANTextDecodeRead](chronaxis.sources.text_can_decode.md#api-CANTextDecodeRead)|是|无|位置或关键字。当前文件的活读取器，保留同次读取计数和精确时间，调用方负责关闭。|
|`terms`|[FileIntegralTerms](chronaxis.execution.file_integral_terms.md#api-FileIntegralTerms)|是|无|位置或关键字。当前文件的有界归组与面积owner，不保存完整原帧或局部总和。|
|`compatibility`|dict[str, object]|是|无|位置或关键字。本文件的必要帧型提示缓存，只记录已见兼容字段并复用冻结tuple。|

### 返回说明

dict，含累计原帧/解码数、实际首末纳秒、精确顺序时间、帧型提示tuple和frame_identity
    （本文件目标帧实际帧型或None，两种模式都带，父进程据此跨文件核对）。

### 异常说明

非法内部对象时AttributeError；不读取下一帧。

源码：[`src/chronaxis/execution/parallel_integral_worker.py:44`](../../../src/chronaxis/execution/parallel_integral_worker.py#L44)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-_error_text"></a>
## `_error_text`

保留原错误及有限清理说明。

```python
_error_text(error, notes=True)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`error`|BaseException|是|无|位置或关键字。要报告的主异常；保留其文字及最多4条、每条至多256字符的清理说明，通道仍另做字节限长。|
|`notes`|bool|否|True|位置或关键字。notes为False时只返回str(错误)（组点模式，与现有time_order读取格式一致）。|

### 返回说明

str。

### 异常说明

原对象字符串转换错误继续传播。

源码：[`src/chronaxis/execution/parallel_integral_worker.py:63`](../../../src/chronaxis/execution/parallel_integral_worker.py#L63)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-_close_file"></a>
## `_close_file`

关闭数值和读取资源，保留首个错误。

```python
_close_file(reader, terms, primary=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`reader`|[CANTextDecodeRead](chronaxis.sources.text_can_decode.md#api-CANTextDecodeRead) &#124; None|是|无|位置或关键字。待关闭读取器；None表示已经关闭或未构造。|
|`terms`|[FileIntegralTerms](chronaxis.execution.file_integral_terms.md#api-FileIntegralTerms) &#124; None|是|无|位置或关键字。待关闭数值owner；None表示已经关闭或未构造。|
|`primary`|BaseException &#124; None|否|None|位置或关键字。原主异常，默认None；后续清理错误只附注，不替换已有主错。|

### 返回说明

BaseException或None；保留已有主错，把后续清理错误写入其说明。

### 异常说明

两资源的close异常作为返回值交付，不直接抛出。

源码：[`src/chronaxis/execution/parallel_integral_worker.py:74`](../../../src/chronaxis/execution/parallel_integral_worker.py#L74)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-read_events"></a>
## `read_events`

读取一批原记录，返回已形成事件及真实EOF或原错误。

```python
read_events(reader, terms, compatibility)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`reader`|[CANTextDecodeRead](chronaxis.sources.text_can_decode.md#api-CANTextDecodeRead)|是|无|位置或关键字。当前文件的活读取器，保留同次读取计数和精确时间，调用方负责关闭。|
|`terms`|[FileIntegralTerms](chronaxis.execution.file_integral_terms.md#api-FileIntegralTerms)|是|无|位置或关键字。当前文件的有界归组与面积owner，不保存完整原帧或局部总和。|
|`compatibility`|dict[str, object]|是|无|位置或关键字。本文件的必要帧型提示缓存，只记录已见兼容字段并复用冻结tuple。|

### 返回说明

五元tuple，依次为(event, facts)条目的tuple、eof bool、Exception或None、
    阶段str（read或compute）及最新facts dict。此eof尚未证明后续资源关闭成功。

### 异常说明

KeyboardInterrupt/SystemExit原样抛；数据错误保留在返回值，先交付数值前缀；
    没有主错时，事实整理失败原样传播。
组点模式下FileGroupPoints停止交付后仍继续读取，使同一文件后面的读取错误照常报出。

源码：[`src/chronaxis/execution/parallel_integral_worker.py:91`](../../../src/chronaxis/execution/parallel_integral_worker.py#L91)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-read_events-append"></a>
### `read_events.append`

只为实际事件保存同次事实。

```python
read_events.append(items)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`items`|tuple[FileIntegralHead &#124; IntegralTermsChunk &#124; FileIntegralTail &#124; FileIntegralFrontier, ...]|是|无|位置或关键字。数值owner本次产生的有限事件；附带同一时刻的读取事实并累计编码/展开估算。|

#### 返回说明

None。

#### 异常说明

编码模型错误。

源码：[`src/chronaxis/execution/parallel_integral_worker.py:105`](../../../src/chronaxis/execution/parallel_integral_worker.py#L105)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-take_events"></a>
## `take_events`

从已形成前缀中取得一份有界多事件包，不触发下一次读取。

```python
take_events(items, last_facts, *, points=False)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`items`|tuple[tuple[FileIntegralHead &#124; IntegralTermsChunk &#124; FileIntegralTail &#124; FileIntegralFrontier, dict[str, object]], ...]|是|无|位置或关键字。已经形成、尚未交付的事件与对应facts条目；保留原顺序。|
|`last_facts`|dict[str, object]|是|无|位置或关键字。同次读取事实：原帧/解码累计数、实际首末纳秒、Decimal顺序时间及compatibility_fields tuple。|
|`points`|bool|否|False|仅关键字。points为True时按组点包的费用和每包2048个事件封包，默认False按面积包。|

### 返回说明

三元tuple，依次为本包事件tuple、剩余(event, facts)条目tuple、本包facts dict；
    items为空时仍校验并交付last_facts。

### 异常说明

单事件连同事实或空包事实超限时ValueError；未知事件时IntegralBlockError，原事实错误继续传播。
不扩大队列、不截短精确时间，也不丢弃尚未发送的事件。

源码：[`src/chronaxis/execution/parallel_integral_worker.py:140`](../../../src/chronaxis/execution/parallel_integral_worker.py#L140)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-worker_main"></a>
## `worker_main`

处理固定文件、配置及next命令，不创建子工作进程。

```python
worker_main(control, data)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`control`|[ControlChannel](chronaxis._control_wire.md#api-ControlChannel)|是|无|位置或关键字。integral族的工作端控制通道；只接受固定file、budget、configure、next和close命令。|
|`data`|multiprocessing.connection.Connection|是|无|位置或关键字。单向发送二进制元数据和面积包的实际管道端点；本函数结束时关闭。|

### 返回说明

None，收到关闭指令或父进程断连后结束。

### 异常说明

control类型或通道族不符时TypeError；运行数据错误按阶段发回父进程，
    与父进程通信的EOFError、BrokenPipeError或OSError导致退出；最终未能清理的资源错误原样抛出。

源码：[`src/chronaxis/execution/parallel_integral_worker.py:167`](../../../src/chronaxis/execution/parallel_integral_worker.py#L167)（行号对应 Chronaxis 0.1.0 源码）。
