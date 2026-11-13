# `chronaxis._process_start`

Linux工作进程在业务入口前登记进程组；此模块只依赖标准库。

独立限长bytes管道只用于启动握手，GO后立即关闭；业务通信仍使用原协议。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`registered_entry`](#api-registered_entry)|建立独立进程组，在父进程确认身份后调用原业务入口。|
|[`StartupGate`](#api-StartupGate)|仅拥有启动管道；父工作槽在分配完成后立即登记本对象。|
|[`StartupGate.__init__`](#api-StartupGate-__init__)|创建并拥有本次启动管道。|
|[`StartupGate.closed`](#api-StartupGate-closed)|查询启动管道是否全部关闭。|
|[`StartupGate.receive`](#api-StartupGate-receive)|限时等待本次进程的一条有限启动消息。|
|[`StartupGate.close_child`](#api-StartupGate-close_child)|关闭父进程持有的启动子端副本。|
|[`StartupGate.close`](#api-StartupGate-close)|关闭本对象持有的两个端点。|
|[`spawn_entry`](#api-spawn_entry)|为当前平台准备原业务入口，不启动进程。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from multiprocessing.connection import wait
```

</details>

<a id="api-registered_entry"></a>
## `registered_entry`

建立独立进程组，在父进程确认身份后调用原业务入口。

```python
registered_entry(connection, token, target, args)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`connection`|multiprocessing.connection.Connection|是|无|位置或关键字。本次启动握手的子端点；仅用 send_bytes/recv_bytes 交换限长消息，在调用业务入口前关闭，不用于传送分析数据。|
|`token`|bytes|是|无|位置或关键字。StartupGate 为本次启动生成的 16 字节随机标记；READY、PROBE、ACK 和 GO 必须使用同一标记。|
|`target`|Callable[..., Any]|是|无|位置或关键字。登记成功后才调用的原业务函数；它必须能作为 spawn 进程入口序列化。握手失败时不调用它。|
|`args`|tuple[Any, ...]|是|无|位置或关键字。传给原业务函数的位置参数元组；启动握手不解释或改写其中的业务对象。|

### 返回说明

原业务入口的返回值。

### 异常说明

握手、管道或原入口错误；未收到GO时不执行业务。

源码：[`src/chronaxis/_process_start.py:11`](../../../src/chronaxis/_process_start.py#L11)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-StartupGate"></a>
## `StartupGate`

仅拥有启动管道；父工作槽在分配完成后立即登记本对象。

```python
StartupGate(context)
```


源码：[`src/chronaxis/_process_start.py:41`](../../../src/chronaxis/_process_start.py#L41)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-StartupGate-__init__"></a>
### `StartupGate.__init__`

创建并拥有本次启动管道。

```python
StartupGate.__init__(context)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`context`|multiprocessing.context.BaseContext|是|无|位置或关键字。调用方通过 get_context("spawn") 取得的上下文；本对象使用其 Pipe 创建且持有启动握手的两个端点。|

#### 返回说明

新的启动资源对象。

#### 异常说明

创建错误原样传播；未关闭端点通过process_start_cleanup_owner保留。

源码：[`src/chronaxis/_process_start.py:44`](../../../src/chronaxis/_process_start.py#L44)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-StartupGate-closed"></a>
### `StartupGate.closed`

查询启动管道是否全部关闭。

```python
StartupGate.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

bool；True只表示本对象不再持有端点，不表示业务进程退出。

#### 异常说明

无。

源码：[`src/chronaxis/_process_start.py:64`](../../../src/chronaxis/_process_start.py#L64)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-StartupGate-receive"></a>
### `StartupGate.receive`

限时等待本次进程的一条有限启动消息。

```python
StartupGate.receive(process, timeout=5.0)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`process`|multiprocessing.process.BaseProcess|是|无|位置或关键字。本次实际启动的工作进程；借用其 sentinel，与启动管道同时等待，以识别尚未回复就退出的工作进程。此方法不关闭或终止该进程。|
|`timeout`|float|否|5.0|位置或关键字。本次等待启动消息的秒数，内部调用默认 5.0；到期仍无可读消息时抛 TimeoutError，不重新启动进程。|

#### 返回说明

最多64字节的bytes。

#### 异常说明

超时、提前退出、消息过长或断管时失败。

源码：[`src/chronaxis/_process_start.py:73`](../../../src/chronaxis/_process_start.py#L73)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-StartupGate-close_child"></a>
### `StartupGate.close_child`

关闭父进程持有的启动子端副本。

```python
StartupGate.close_child()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

真实关闭错误；尚未关闭的端点仍由本对象持有。

源码：[`src/chronaxis/_process_start.py:87`](../../../src/chronaxis/_process_start.py#L87)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-StartupGate-close"></a>
### `StartupGate.close`

关闭本对象持有的两个端点。

```python
StartupGate.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None；重复关闭安全。

#### 异常说明

报告首个关闭错误，其余写入notes；未关闭端点保留供恢复。

源码：[`src/chronaxis/_process_start.py:101`](../../../src/chronaxis/_process_start.py#L101)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-spawn_entry"></a>
## `spawn_entry`

为当前平台准备原业务入口，不启动进程。

```python
spawn_entry(context, target, args)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`context`|multiprocessing.context.BaseContext|是|无|位置或关键字。调用方选定的 spawn 上下文；Linux 用它创建独立启动管道，Windows 不新增启动管道。|
|`target`|Callable[..., Any]|是|无|位置或关键字。调用方原定的工作进程入口。Windows 原样返回；Linux 将其包在 registered_entry 后，先验证进程组身份再调用。|
|`args`|tuple[Any, ...]|是|无|位置或关键字。原业务入口的位置参数；Windows 原样返回，Linux 与握手子端点和随机标记一起封装进返回的入口参数。|

### 返回说明

返回 (入口函数, 参数元组, StartupGate 或 None)，供调用方随后创建 Process；本函数本身不启动进程。Windows 返回原入口和 None，Linux 返回握手入口及其管道拥有者。

### 异常说明

未支持的平台，或 Python 未提供 pidfd_open/pidfd_send_signal 时抛 NotImplementedError。管道创建错误原样传播；尚未关闭的启动资源通过 process_start_cleanup_owner 保留。内核是否实际接受进程组信号，由后续 ProcessTree 登记时检验。

源码：[`src/chronaxis/_process_start.py:125`](../../../src/chronaxis/_process_start.py#L125)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
