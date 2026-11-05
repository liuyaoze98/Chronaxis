# `chronaxis.legacy.export_worker`

在独立spawn子进程按单次PUT许可调用冻结的原BLF写出链。

输入为有界INIT/PUT/FINISH JSON bytes，输出同次READY、逐帧ACK和完成候选。
INIT才核三份vendor及锁定依赖，独占取得新输出文件，再原样调用一次
build_writer(str(path),'blf')。每PUT完整恢复同一LegacyRawFrame公开字段并
构造can.Message，原writer.on_message_received只调用一次，不读源CAN或DBC。
FINISH仅在原stop成功后发送完成候选；父仍须核真实子退出、句柄及费用收尾。

本模块复用CAN读取协议的有界JSON、错误摘要和vendor加载函数，不修改或继承其read
生命周期。失败保有限远端事实并非零退出，finally只对尚未尝试stop的writer调用
一次原stop；失败的stop不被静默重试或改写。实际子退出回收未公开旧FD，不能
据父RAM账本声称旧库、压缩缓存或整进程RSS受限。产物保留，不自动删除失败文件。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)

## 对象导航

|对象|用途|
|---|---|
|[`_output`](#api-_output)|检查唯一INIT及新输出路径，不猜格式或覆盖已有文件。|
|[`_message`](#api-_message)|把全部原公开写出字段交给原can.Message构造，不添加check或归一化参数。|
|[`worker_main`](#api-worker_main)|作为真实spawn目标，按INIT/单PUT/FINISH顺序调用唯一原writer。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from importlib import metadata
from pathlib import Path
from .records import PROFILE_ID, frame_from_dict
from .worker import VENDOR_SHA256, _exact, _load_vendor, _receive, _report_error, _send
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

源码：[`src/chronaxis/legacy/export_worker.py:27`](../../../src/chronaxis/legacy/export_worker.py#L27)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

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

源码：[`src/chronaxis/legacy/export_worker.py:51`](../../../src/chronaxis/legacy/export_worker.py#L51)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-worker_main"></a>
## `worker_main`

作为真实spawn目标，按INIT/单PUT/FINISH顺序调用唯一原writer。

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

独占创建一个新BLF、一次build_writer、每许可一次on_message_received，
    至多一次stop；不读取输入CAN/DBC，不调parse或为ACK额外写帧。

源码：[`src/chronaxis/legacy/export_worker.py:67`](../../../src/chronaxis/legacy/export_worker.py#L67)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
