# `chronaxis.execution.parallel_integral_worker`

一个积分工作槽按许可读取文件并生成原序面积块。

读取器和数值状态在子进程中关闭，父进程拥有整个进程生命周期。文件错误
先保留已经形成的边界/面积前缀，下一次许可才交付错误。eof数据包晚于
读取器和数值owner关闭，finished确认再证明包工作区已释放。没有许可时
不继续读取，不生成面积文件或最终结果。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CANTextDecodeRead](chronaxis.sources.text_can_decode.md#api-CANTextDecodeRead)、[ControlChannel](chronaxis._control_wire.md#api-ControlChannel)、[FileIntegralTerms](chronaxis.execution.file_integral_terms.md#api-FileIntegralTerms)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)

## 对象导航

|对象|用途|
|---|---|
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
from .integral_blocks import BLOCK_RAM, WIRE_LIMIT, MAX_EVENTS, MODEL_LIMIT, event_cost, facts_cost, encode_packet, restore_task
from .parallel_can_worker import plain
```

</details>

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

dict，含累计原帧/解码数、实际首末纳秒、精确顺序时间和帧型提示tuple。

### 异常说明

非法内部对象时AttributeError；不读取下一帧。

源码：[`src/chronaxis/execution/parallel_integral_worker.py:22`](../../../src/chronaxis/execution/parallel_integral_worker.py#L22)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_error_text"></a>
## `_error_text`

保留原错误及有限清理说明。

```python
_error_text(error)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`error`|BaseException|是|无|位置或关键字。要报告的主异常；保留其文字及最多4条、每条至多256字符的清理说明，通道仍另做字节限长。|

### 返回说明

str。

### 异常说明

原对象字符串转换错误继续传播。

源码：[`src/chronaxis/execution/parallel_integral_worker.py:39`](../../../src/chronaxis/execution/parallel_integral_worker.py#L39)（行号对应 Chronaxis 0.1.0.dev5 源码）。

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

源码：[`src/chronaxis/execution/parallel_integral_worker.py:45`](../../../src/chronaxis/execution/parallel_integral_worker.py#L45)（行号对应 Chronaxis 0.1.0.dev5 源码）。

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

源码：[`src/chronaxis/execution/parallel_integral_worker.py:62`](../../../src/chronaxis/execution/parallel_integral_worker.py#L62)（行号对应 Chronaxis 0.1.0.dev5 源码）。

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

源码：[`src/chronaxis/execution/parallel_integral_worker.py:73`](../../../src/chronaxis/execution/parallel_integral_worker.py#L73)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-take_events"></a>
## `take_events`

从已形成前缀中取得一份有界多事件包，不触发下一次读取。

```python
take_events(items, last_facts)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`items`|tuple[tuple[FileIntegralHead &#124; IntegralTermsChunk &#124; FileIntegralTail &#124; FileIntegralFrontier, dict[str, object]], ...]|是|无|位置或关键字。已经形成、尚未交付的事件与对应facts条目；保留原顺序。|
|`last_facts`|dict[str, object]|是|无|位置或关键字。同次读取事实：原帧/解码累计数、实际首末纳秒、Decimal顺序时间及compatibility_fields tuple。|

### 返回说明

三元tuple，依次为本包事件tuple、剩余(event, facts)条目tuple、本包facts dict；
    items为空时仍校验并交付last_facts。

### 异常说明

单事件连同事实或空包事实超限时ValueError；未知事件时IntegralBlockError，原事实错误继续传播。
不扩大队列、不截短精确时间，也不丢弃尚未发送的事件。

源码：[`src/chronaxis/execution/parallel_integral_worker.py:108`](../../../src/chronaxis/execution/parallel_integral_worker.py#L108)（行号对应 Chronaxis 0.1.0.dev5 源码）。

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

源码：[`src/chronaxis/execution/parallel_integral_worker.py:133`](../../../src/chronaxis/execution/parallel_integral_worker.py#L133)（行号对应 Chronaxis 0.1.0.dev5 源码）。
