# `chronaxis.legacy.export_worker`

在独立spawn进程按PUT许可将原报文写入新的BLF文件。

有效INIT后核现有依赖版本，BLFWrite独占取得文件并把同一句柄交给python-can。
每PUT恢复原公开字段并写一次，不读取来源或DBC；FINISH仅在最终写入成功后确认。
关闭失败保留原错误与实际文件owner，第三方stop不重复执行，父侧仍核实际子退出。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)

## 对象导航

|对象|用途|
|---|---|
|[`_output`](#api-_output)|检查唯一INIT及新输出路径，不猜格式或覆盖已有文件。|
|[`_message`](#api-_message)|把全部原公开写出字段交给原can.Message构造，不添加check或归一化参数。|
|[`worker_main`](#api-worker_main)|作为真实spawn目标，按INIT/单PUT/FINISH顺序调用唯一BLF writer。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from pathlib import Path
from .records import PROFILE_ID, frame_from_dict
from .worker import _exact, _load_can_runtime, _receive, _report_error, _send
from ..can_dependencies import runtime_dependency_versions
```

</details>

<a id="api-_output"></a>
## `_output`

检查唯一INIT及新输出路径，不猜格式或覆盖已有文件。

```python
_output(packet)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`packet`|dict[str, object]|是|无|位置或关键字。已经解码并检查字段的进程通信包，含op操作名及该操作的数据；本函数按当前协议步骤继续检查或发送它。|

### 返回说明

resolved新BLF Path。

### 异常说明

TypeError/ValueError为字段、版本、profile、后缀或受保护路径；
    FileExistsError为已有目标，FileNotFoundError为尚无控制器工作根。

### 副作用说明

仅检查文件系统；真正独占创建仍在writer建立之前执行。

源码：[`src/chronaxis/legacy/export_worker.py:17`](../../../src/chronaxis/legacy/export_worker.py#L17)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_message"></a>
## `_message`

把全部原公开写出字段交给原can.Message构造，不添加check或归一化参数。

```python
_message(can, frame)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`can`|ModuleType|是|无|位置或关键字。旧实现实际导入的python-can模块，用其Message类型构造输出报文。|
|`frame`|LegacyRawFrame|是|无|位置或关键字。frame为已校验LegacyRawFrame。|

### 返回说明

新can.Message，timestamp/data/DLC及全部标志保持原参数。

### 异常说明

原can.Message构造错误；不以新层猜测修正旧格式限制。

源码：[`src/chronaxis/legacy/export_worker.py:41`](../../../src/chronaxis/legacy/export_worker.py#L41)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-worker_main"></a>
## `worker_main`

作为真实spawn目标，按INIT/单PUT/FINISH顺序调用唯一BLF writer。

```python
worker_main(connection)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`connection`|multiprocessing.connection.Connection|是|无|位置或关键字。父子进程之间已经建立的双向通信端点，用于发送请求和接收结果；不是文件路径或网络地址。|

### 返回说明

原stop成功并发送候选后None。

### 异常说明

原错误尽力发送有限ERROR，最终SystemExit(1)；管道清理也不能伪成正常退出。

本函数直接报告的具体错误：

- `ValueError`：原CAN writer依赖不符合已验证profile。
- `ValueError`：原build_writer返回的路径与本次目标不一致。
- `ValueError`：PUT许可必须从0严格连续且为原生int。
- `ValueError`：FINISH帧数与本次原writer确认数量不符。

### 副作用说明

独占创建一个新BLF、一次BLFWrite、每许可一次on_message_received，
    至多一次stop；不读取输入CAN/DBC，不调parse或为ACK额外写帧。

源码：[`src/chronaxis/legacy/export_worker.py:57`](../../../src/chronaxis/legacy/export_worker.py#L57)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
