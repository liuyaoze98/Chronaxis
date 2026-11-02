# chronaxis.legacy.export_write

在独立进程把原始帧交给冻结旧BLF writer，真实收尾后才确认完成。

LegacyCANProcessWrite接收共享ResourceBudget和新输出路径，构造只计有限状态、
核路径而不spawn或执行旧IO。start实际加载锁定依赖/vendor并创建原writer；每次
write只发一个有界PUT，收到同序ACK才承认该帧，FINISH没有额外帧写入许可。
finish须原stop成功、实际exitcode0、所有Pipe/Process及自有RAM清完，并核输出
stat不超过本writer直接预留，才公开finished。提前close、失败或取消不能伪完成。

进程/管道/wire/READY/当前帧分别先付并记真实槽；释放前后取消可重试，最高
can_process_write_cleanup_owner始终指向同一实际owner。磁盘在start前保守预留
65536 bytes、每PUT前4096 bytes，累计保留且不倒扣；不凭共享余额差接管费用。
原BLF压缩、库内部缓存及整进程RSS未测，也不承诺文件与源BLF字节一致。
这里只写控制器新工作根下的新文件，不读源CAN/DBC，不修改原read/records/vendor。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisError](chronaxis.results.errors.md#api-AnalysisError)、[LegacyRawFrame](chronaxis.legacy.records.md#api-LegacyRawFrame)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[RemoteLegacyError](chronaxis.legacy.process_read.md#api-RemoteLegacyError)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)

## 对象导航

|对象|用途|
|---|---|
|[`LegacyCANWriteError`](#api-LegacyCANWriteError)|报告新外部writer协议或原子进程失败；远端原错仅作为明确事实cause。|
|[`LegacyCANProcessWrite`](#api-LegacyCANProcessWrite)|拥有一个真实writer子进程与独立费用，共用的资源用量记录但不关闭其他owner。|
|[`LegacyCANProcessWrite.__init__`](#api-LegacyCANProcessWrite-__init__)|预约固定协调状态并检查新路径，不启动进程或创建目标文件。|
|[`LegacyCANProcessWrite._check_path`](#api-LegacyCANProcessWrite-_check_path)|拒绝已有/受保护目标及缺少的新工作根，不创建目录或文件。|
|[`LegacyCANProcessWrite.output_path`](#api-LegacyCANProcessWrite-output_path)|读取实际新目标。|
|[`LegacyCANProcessWrite.closed`](#api-LegacyCANProcessWrite-closed)|读取全部自有责任关闭状态。|
|[`LegacyCANProcessWrite.finished`](#api-LegacyCANProcessWrite-finished)|读取完整FINISH事实。|
|[`LegacyCANProcessWrite.failed`](#api-LegacyCANProcessWrite-failed)|读取失败诊断状态。|
|[`LegacyCANProcessWrite.worker_pid`](#api-LegacyCANProcessWrite-worker_pid)|读取本次真实启动PID。|
|[`LegacyCANProcessWrite.spool_bytes`](#api-LegacyCANProcessWrite-spool_bytes)|读取本writer直接累计磁盘预留。|
|[`LegacyCANProcessWrite.counters`](#api-LegacyCANProcessWrite-counters)|区分PUT尝试、合法ACK和本父确认帧数，不用断管推断写入成功。|
|[`LegacyCANProcessWrite.metadata`](#api-LegacyCANProcessWrite-metadata)|借读同次READY事实，不隐式start。|
|[`LegacyCANProcessWrite._require_open`](#api-LegacyCANProcessWrite-_require_open)|阻止关闭或失败后继续许可。|
|[`LegacyCANProcessWrite._reserve_spool`](#api-LegacyCANProcessWrite-_reserve_spool)|逐笔记录本次直接磁盘预留，回调执行后取消也保留真实归属。|
|[`LegacyCANProcessWrite._fail`](#api-LegacyCANProcessWrite-_fail)|以实际父错误为主收尾，普通底层错误包装并保cause及最高恢复owner。|
|[`LegacyCANProcessWrite.start`](#api-LegacyCANProcessWrite-start)|实际创建独立spawn及原writer，READY不包含任何帧许可。|
|[`LegacyCANProcessWrite._check_ready`](#api-LegacyCANProcessWrite-_check_ready)|核同次实际PID及锁定依赖/vendor，不接受bool伪版本或自称READY。|
|[`LegacyCANProcessWrite._exchange`](#api-LegacyCANProcessWrite-_exchange)|同步交换唯一控制包，禁止第二个在途PUT或把子退出当成ACK。|
|[`LegacyCANProcessWrite.write`](#api-LegacyCANProcessWrite-write)|完整发送一个原始帧并等唯一ACK，不缓存后继或按ID筛帧。|
|[`LegacyCANProcessWrite.finish`](#api-LegacyCANProcessWrite-finish)|完成原stop、真实正常退出及全部费用，再核实际文件未超过预留。|
|[`LegacyCANProcessWrite._close_connection`](#api-LegacyCANProcessWrite-_close_connection)|实际关闭端点后才撤槽。|
|[`LegacyCANProcessWrite._close_process`](#api-LegacyCANProcessWrite-_close_process)|有限等待自己实际进程退出再关句柄，绝不以终止请求代替退出证明。|
|[`LegacyCANProcessWrite.close`](#api-LegacyCANProcessWrite-close)|只关本writer实际IPC/进程和费用，产物与累计磁盘预留保留。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from pathlib import Path
from .export_worker import WRITE_DEPENDENCIES, worker_main
from .process_read import RemoteLegacyError, _freeze, _wire_metadata_bytes
from .records import MAX_WIRE_BYTES, PROFILE_ID, LegacyRawFrame, decode_packet, encode_packet, frame_to_dict
from .worker import VENDOR_SHA256
from ..results.budget import ResourceBudget
from ..results.errors import AnalysisError, ResultClosedError
from ..results.spool import _cleanup_owner, _release_owned_ram, _reserve_owned_ram
```

</details>

<a id="api-LegacyCANWriteError"></a>
## `LegacyCANWriteError`

报告新外部writer协议或原子进程失败；远端原错仅作为明确事实cause。

```python
class LegacyCANWriteError(AnalysisError)
```

继承关系：[AnalysisError](chronaxis.results.errors.md#api-AnalysisError)。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/legacy/export_write.py:29`](../../../src/chronaxis/legacy/export_write.py#L29)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessWrite"></a>
## `LegacyCANProcessWrite`

拥有一个真实writer子进程与独立费用，共用的资源用量记录但不关闭其他owner。

_waiting阻止第二个在途控制包；_process_stopped只由实际exitcode确认。
_closed表示自有责任结束，_finished还须本次FINISH及输出大小验证成功。
输出路径和累计spool事实在close后保留，READY借引用在close时解除。

```python
LegacyCANProcessWrite(budget, output_path)
```


源码：[`src/chronaxis/legacy/export_write.py:33`](../../../src/chronaxis/legacy/export_write.py#L33)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessWrite-__init__"></a>
### `LegacyCANProcessWrite.__init__`

预约固定协调状态并检查新路径，不启动进程或创建目标文件。

```python
LegacyCANProcessWrite.__init__(budget, output_path)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)|是|无|位置或关键字。本次运行共用的ResourceBudget对象，用于检查内存和临时磁盘用量。当前对象在分配前申请额度，用完后归还；同一次运行的组件应使用同一个对象。|
|`output_path`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。output_path为控制器已有新工作根下的     str/Path目标，须为.blf后缀，不能已存在或位于RefProjects。|

#### 返回说明

未启动的独立writer。

#### 异常说明

类型、路径或预算原错；未返回构造的持续
    清理失败附can_process_write_cleanup_owner，同对象恢复后close。

本函数直接报告的具体错误：

- `TypeError`：原CAN写出需要ResourceBudget和新输出路径。
- `ValueError`：原CAN输出路径超过本层有限能力。

源码：[`src/chronaxis/legacy/export_write.py:41`](../../../src/chronaxis/legacy/export_write.py#L41)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessWrite-_check_path"></a>
### `LegacyCANProcessWrite._check_path`

拒绝已有/受保护目标及缺少的新工作根，不创建目录或文件。

```python
LegacyCANProcessWrite._check_path()
```

参数：无显式参数。


#### 参数说明

无，使用已保存resolved路径。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ValueError为后缀/RefProjects，FileExistsError为已有目标，
    FileNotFoundError为父目录不存在；真正独占创建由child执行。

源码：[`src/chronaxis/legacy/export_write.py:72`](../../../src/chronaxis/legacy/export_write.py#L72)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessWrite-output_path"></a>
### `LegacyCANProcessWrite.output_path`

读取实际新目标。

```python
LegacyCANProcessWrite.output_path
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

resolved Path或构造前失败时None。

#### 异常说明

无。

源码：[`src/chronaxis/legacy/export_write.py:88`](../../../src/chronaxis/legacy/export_write.py#L88)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessWrite-closed"></a>
### `LegacyCANProcessWrite.closed`

读取全部自有责任关闭状态。

```python
LegacyCANProcessWrite.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/legacy/export_write.py:93`](../../../src/chronaxis/legacy/export_write.py#L93)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessWrite-finished"></a>
### `LegacyCANProcessWrite.finished`

读取完整FINISH事实。

```python
LegacyCANProcessWrite.finished
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

bool，失败/提前close为False。

#### 异常说明

无。

源码：[`src/chronaxis/legacy/export_write.py:98`](../../../src/chronaxis/legacy/export_write.py#L98)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessWrite-failed"></a>
### `LegacyCANProcessWrite.failed`

读取失败诊断状态。

```python
LegacyCANProcessWrite.failed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象已记录处理失败；False表示尚未记录失败。

#### 异常说明

无。

源码：[`src/chronaxis/legacy/export_write.py:103`](../../../src/chronaxis/legacy/export_write.py#L103)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessWrite-worker_pid"></a>
### `LegacyCANProcessWrite.worker_pid`

读取本次真实启动PID。

```python
LegacyCANProcessWrite.worker_pid
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

int或None，关闭后保留。

#### 异常说明

无。

源码：[`src/chronaxis/legacy/export_write.py:108`](../../../src/chronaxis/legacy/export_write.py#L108)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessWrite-spool_bytes"></a>
### `LegacyCANProcessWrite.spool_bytes`

读取本writer直接累计磁盘预留。

```python
LegacyCANProcessWrite.spool_bytes
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

int bytes，不倒扣。

#### 异常说明

无。

源码：[`src/chronaxis/legacy/export_write.py:113`](../../../src/chronaxis/legacy/export_write.py#L113)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessWrite-counters"></a>
### `LegacyCANProcessWrite.counters`

区分PUT尝试、合法ACK和本父确认帧数，不用断管推断写入成功。

```python
LegacyCANProcessWrite.counters
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

新dict，取消时puts_issued仅为许可尝试上界。

#### 异常说明

原小容器分配错误；不向child发送额外控制或写入。

源码：[`src/chronaxis/legacy/export_write.py:118`](../../../src/chronaxis/legacy/export_write.py#L118)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessWrite-metadata"></a>
### `LegacyCANProcessWrite.metadata`

借读同次READY事实，不隐式start。

```python
LegacyCANProcessWrite.metadata
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

冻结映射，借用至close。

#### 异常说明

ResultClosedError为关闭/失败，RuntimeError为尚无实际READY。

本函数直接报告的具体错误：

- `RuntimeError`：原CAN writer尚未READY。

源码：[`src/chronaxis/legacy/export_write.py:128`](../../../src/chronaxis/legacy/export_write.py#L128)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessWrite-_require_open"></a>
### `LegacyCANProcessWrite._require_open`

阻止关闭或失败后继续许可。

```python
LegacyCANProcessWrite._require_open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

ResultClosedError为不可推进；close仍可重复恢复。

本函数直接报告的具体错误：

- `ResultClosedError`：原CAN writer已关闭、清理中或失败。

源码：[`src/chronaxis/legacy/export_write.py:137`](../../../src/chronaxis/legacy/export_write.py#L137)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessWrite-_reserve_spool"></a>
### `LegacyCANProcessWrite._reserve_spool`

逐笔记录本次直接磁盘预留，回调执行后取消也保留真实归属。

```python
LegacyCANProcessWrite._reserve_spool(amount)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`amount`|int|是|无|位置或关键字。本次要申请或归还的内存字节数，填写非负整数。申请后计入本对象的占用；归还的数量不能超过本对象此前申请且尚未归还的数量。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原配额/取消，文件及累计值不倒扣。

源码：[`src/chronaxis/legacy/export_write.py:144`](../../../src/chronaxis/legacy/export_write.py#L144)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessWrite-_fail"></a>
### `LegacyCANProcessWrite._fail`

以实际父错误为主收尾，普通底层错误包装并保cause及最高恢复owner。

```python
LegacyCANProcessWrite._fail(exc, phase)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`exc`|BaseException|是|无|位置或关键字。本次操作的原异常，供附加关闭失败信息并保留原因链。不要用错误字符串代替异常对象。|
|`phase`|str|是|无|位置或关键字。发生错误时正在执行的步骤名称；写入错误信息，帮助区分初始化、读取、解码或关闭失败。|

#### 返回说明

不返回。

#### 异常说明

KI/SystemExit/AnalysisError原对象，其余LegacyCANWriteError保原cause；
    两次有限cleanup副错只附note，绝不伪称写出完成。

源码：[`src/chronaxis/legacy/export_write.py:156`](../../../src/chronaxis/legacy/export_write.py#L156)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessWrite-start"></a>
### `LegacyCANProcessWrite.start`

实际创建独立spawn及原writer，READY不包含任何帧许可。

```python
LegacyCANProcessWrite.start()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

self，重复成功调用不重建或重复预留。

#### 异常说明

路径/依赖/管道/协议/配额/预算或父原取消，最高owner按实际槽可恢复。

源码：[`src/chronaxis/legacy/export_write.py:171`](../../../src/chronaxis/legacy/export_write.py#L171)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessWrite-_check_ready"></a>
### `LegacyCANProcessWrite._check_ready`

核同次实际PID及锁定依赖/vendor，不接受bool伪版本或自称READY。

```python
LegacyCANProcessWrite._check_ready(packet)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`packet`|dict[str, object]|是|无|位置或关键字。已经解码并检查字段的进程通信包，含op操作名及该操作的数据；本函数按当前协议步骤继续检查或发送它。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

LegacyCANWriteError为结构/类型/profile/PID/版本/摘要不符。

本函数直接报告的具体错误：

- `LegacyCANWriteError`：原CAN writer READY身份、版本、实际PID或vendor不符。

源码：[`src/chronaxis/legacy/export_write.py:207`](../../../src/chronaxis/legacy/export_write.py#L207)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessWrite-_exchange"></a>
### `LegacyCANProcessWrite._exchange`

同步交换唯一控制包，禁止第二个在途PUT或把子退出当成ACK。

```python
LegacyCANProcessWrite._exchange(packet)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`packet`|dict|是|无|位置或关键字。packet为有界控制dict。|

#### 返回说明

严格JSON dict。

#### 异常说明

父原取消/管道/编码错误或LegacyCANWriteError；远端失败以明确
    RemoteLegacyError事实为cause，不能声称跨进程保留异常对象身份。

源码：[`src/chronaxis/legacy/export_write.py:221`](../../../src/chronaxis/legacy/export_write.py#L221)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessWrite-write"></a>
### `LegacyCANProcessWrite.write`

完整发送一个原始帧并等唯一ACK，不缓存后继或按ID筛帧。

```python
LegacyCANProcessWrite.write(frame)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`frame`|[LegacyRawFrame](chronaxis.legacy.records.md#api-LegacyRawFrame)|是|无|位置或关键字。frame为原生LegacyRawFrame，保全部公开字段及原浮点timestamp。|

#### 返回说明

None，合法ACK后counters增加；无额外on_message_received。

#### 异常说明

TypeError为非原模型；原预算/磁盘/取消或writer/协议失败，之后只能close。

本函数直接报告的具体错误：

- `TypeError`：原CAN writer.write需要LegacyRawFrame。
- `LegacyCANWriteError`：原CAN writer ACK不属于本次唯一PUT。

源码：[`src/chronaxis/legacy/export_write.py:253`](../../../src/chronaxis/legacy/export_write.py#L253)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessWrite-finish"></a>
### `LegacyCANProcessWrite.finish`

完成原stop、真实正常退出及全部费用，再核实际文件未超过预留。

```python
LegacyCANProcessWrite.finish()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

self，成功后重复调用不重发FINISH或重写文件。

#### 异常说明

原取消/预算/关闭错误，或LegacyCANWriteError为不完整回应、异常退出
    或实际stat超本writer累计预留；任何失败都不置finished。

源码：[`src/chronaxis/legacy/export_write.py:285`](../../../src/chronaxis/legacy/export_write.py#L285)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessWrite-_close_connection"></a>
### `LegacyCANProcessWrite._close_connection`

实际关闭端点后才撤槽。

```python
LegacyCANProcessWrite._close_connection(slot)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`slot`|str|是|无|位置或关键字。保存本对象通信端点的属性名；关闭后清空该属性，防止重复关闭旧端点。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原close/取消；执行后异常也按真实closed确认，不丢未关句柄。

源码：[`src/chronaxis/legacy/export_write.py:313`](../../../src/chronaxis/legacy/export_write.py#L313)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessWrite-_close_process"></a>
### `LegacyCANProcessWrite._close_process`

有限等待自己实际进程退出再关句柄，绝不以终止请求代替退出证明。

```python
LegacyCANProcessWrite._close_process()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原join/terminate/kill/close或LegacyCANWriteError；
    未确认时保原进程/费用并附稳定退出诊断。显式join上限为.5/.5/5秒，
    Windows kill仍是TerminateProcess，必须实际exitcode非None。

源码：[`src/chronaxis/legacy/export_write.py:325`](../../../src/chronaxis/legacy/export_write.py#L325)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANProcessWrite-close"></a>
### `LegacyCANProcessWrite.close`

只关本writer实际IPC/进程和费用，产物与累计磁盘预留保留。

```python
LegacyCANProcessWrite.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None，完成后重复调用幂等。

#### 异常说明

原关闭/预算/取消附can_process_write_cleanup_owner，当前槽供持续恢复；
    提前关闭不发送额外帧或FINISH，不设置finished，不修改借用预算的其他费用。

源码：[`src/chronaxis/legacy/export_write.py:356`](../../../src/chronaxis/legacy/export_write.py#L356)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
