# `chronaxis._batch_worker`

批量工作进程控制消息；只在收到对应任务时加载计算实现。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[threading.Event](https://docs.python.org/3.12/library/threading.html#event-objects)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)

## 对象导航

|对象|用途|
|---|---|
|[`_diagnostics`](#api-_diagnostics)|保留有限异常链而不持有栈。|
|[`worker_main`](#api-worker_main)|处理run/cleanup/close命令。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import replace
from pathlib import Path
from threading import Event
```

</details>

<a id="api-_diagnostics"></a>
## `_diagnostics`

保留有限异常链而不持有栈。

```python
_diagnostics(error) -> tuple[str, ...]
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`error`|BaseException|是|无|位置或关键字。本次操作产生的原异常对象；用于保留原因链、附加清理失败信息或继续抛出，不应换成一段字符串。|

### 返回说明

文本tuple。

### 异常说明

原异常格式错误。

返回类型：tuple[str, ...]。

源码：[`src/chronaxis/_batch_worker.py:8`](../../../src/chronaxis/_batch_worker.py#L8)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-worker_main"></a>
## `worker_main`

处理run/cleanup/close命令。

```python
worker_main(connection, fast_cancel=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`connection`|multiprocessing.connection.PipeConnection|是|无|位置或关键字。本次spawn建立的私有双向Windows管道，只接受所属主进程发送的run、cleanup和close命令。|
|`fast_cancel`|multiprocessing.Event &#124; None|否|None|位置或关键字。每个 fast 工作进程的共享取消信号，普通工作进程省略。|

### 返回说明

None。

### 异常说明

断管退出，父进程负责树清理。

源码：[`src/chronaxis/_batch_worker.py:19`](../../../src/chronaxis/_batch_worker.py#L19)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
