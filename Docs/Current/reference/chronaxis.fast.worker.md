# `chronaxis.fast.worker`

在本工作进程内执行事先验证的参数，只上传本文件的少量结果。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)

## 对象导航

|对象|用途|
|---|---|
|[`_run_file`](#api-_run_file)|在已持有该文件的工作进程直接分析并发布。返回任务状态及可选的小型汇总行。|
|[`_dbc_digest`](#api-_dbc_digest)|读取解码声明的摘要；只在请求跨文件求和时使用。|
|[`file_response`](#api-file_response)|仅传已冻结的结果字段；接收方使用与通用批量相同的结果模型校验。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from .run import run_prepared
from .._batch_worker import _diagnostics
```

</details>

<a id="api-_run_file"></a>
## `_run_file`

在已持有该文件的工作进程直接分析并发布。返回任务状态及可选的小型汇总行。

```python
_run_file(packet, directory, cancel)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`packet`|dict|是|无|位置或关键字。主进程发送的任务名、文件路径、执行参数及总量请求。|
|`directory`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。给本次任务独占的结果目录。|
|`cancel`|multiprocessing.Event|是|无|位置或关键字。由父进程设置的在途任务取消信号。|

源码：[`src/chronaxis/fast/worker.py:9`](../../../src/chronaxis/fast/worker.py#L9)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_dbc_digest"></a>
## `_dbc_digest`

读取解码声明的摘要；只在请求跨文件求和时使用。

```python
_dbc_digest(path)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。要读取的文件路径。|

源码：[`src/chronaxis/fast/worker.py:40`](../../../src/chronaxis/fast/worker.py#L40)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-file_response"></a>
## `file_response`

仅传已冻结的结果字段；接收方使用与通用批量相同的结果模型校验。

```python
file_response(packet, directory, cancel)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`packet`|dict|是|无|位置或关键字。主进程发送的任务名、文件路径、执行参数及总量请求。|
|`directory`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。给本次任务独占的结果目录。|
|`cancel`|multiprocessing.Event|是|无|位置或关键字。由父进程设置的在途任务取消信号。|

源码：[`src/chronaxis/fast/worker.py:46`](../../../src/chronaxis/fast/worker.py#L46)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
