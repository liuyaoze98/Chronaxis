# `chronaxis.fast.session_worker`

可复用文件worker：流式求贡献，获得父进程许可后直传或直接写暂存。

控制和数据独立，任一时刻只有一个尚未交付块。worker不累计总量、不创建
子进程；EOF包含最终块数与已成功关闭的文件事实。父进程拥有取消和回收责任。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)

## 对象导航

|对象|用途|
|---|---|
|[`worker_main`](#api-worker_main)|运行父授权的文件任务。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from .blocks import batches, encode, LIMIT
```

</details>

<a id="api-worker_main"></a>
## `worker_main`

运行父授权的文件任务。

```python
worker_main(control, data, cancel)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`control`|multiprocessing.connection.Connection|是|无|位置或关键字。双向控制连接，传递文件任务、交付许可、错误及最终计数；与完整数据传输分离。|
|`data`|multiprocessing.connection.Connection|是|无|位置或关键字。单向数据连接，传递获准直传的完整贡献块；暂存块只通过控制连接通知位置。|
|`cancel`|Event &#124; None|是|无|位置或关键字。调用方取消事件；is_set为真时停止继续读取或调度，None表示没有外部取消信号。|

### 返回说明

None。

### 异常说明

原错误通过控制通道报告；断管退出，finally释放读取器。

源码：[`src/chronaxis/fast/session_worker.py:15`](../../../src/chronaxis/fast/session_worker.py#L15)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
