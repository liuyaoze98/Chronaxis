# `chronaxis.batch.process_tree`

管理本次工作进程树；Windows使用作业对象，Linux使用已确认身份的pidfd进程组。

父进程持有本次任务的作业句柄或pidfd；工作进程完成登记后才运行用户计划。
关闭时回收本任务的剩余后代，不扫描或接管其他任务的进程。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`_BasicLimits`](#api-_BasicLimits)|对应Windows基本作业限制结构；仅设置关闭句柄时结束整个作业。|
|[`_ExtendedLimits`](#api-_ExtendedLimits)|对应Windows扩展作业限制，未使用的资源额度保持零值。|
|[`ProcessTree`](#api-ProcessTree)|持有一个工作进程树的关闭责任；Linux在GO前完成双向身份核验。|
|[`ProcessTree.__init__`](#api-ProcessTree-__init__)|登记本次工作进程的关闭责任；Windows 采用作业对象，Linux 在允许业务运行前核对进程组身份与内核能力。|
|[`ProcessTree._register_linux`](#api-ProcessTree-_register_linux)|通过本次进程的双向握手登记pidfd。|
|[`ProcessTree._close_linux`](#api-ProcessTree-_close_linux)|关闭已确认的进程组并核对实际消失。|
|[`ProcessTree._close_process_handle`](#api-ProcessTree-_close_process_handle)|关闭登记期间真实打开的进程句柄。|
|[`ProcessTree.close`](#api-ProcessTree-close)|关闭本次平台资源；Windows失败保留实际句柄，Linux只重试尚未结束的组。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ctypes import wintypes
from time import monotonic, sleep
from ..results.budget import _cleanup_owner
```

</details>

<a id="api-_BasicLimits"></a>
## `_BasicLimits`

对应Windows基本作业限制结构；仅设置关闭句柄时结束整个作业。

```python
class _BasicLimits(ctypes.Structure)
```

继承关系：ctypes.Structure。下表列本类声明的字段；基类字段及其约束见对应类型链接。

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`_fields_`|list[tuple[str, type]]|类成员，不作为构造参数填写|[('per_process', ctypes.c_longlong), ('per_job', ctypes.c_longlong), ('flags', wintypes.DWORD), ('min_ws', ctypes.c_size_t), ('max_ws', ctypes.c_size_t), ('active_limit', wintypes.DWORD), ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD), ('scheduling', wintypes.DWORD)]|Windows作业结构的固定ABI布局；由ctypes使用，不是用户配置参数，不能按字段名称随意调整次序或宽度。|

源码：[`src/chronaxis/batch/process_tree.py:17`](../../../src/chronaxis/batch/process_tree.py#L17)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_ExtendedLimits"></a>
## `_ExtendedLimits`

对应Windows扩展作业限制，未使用的资源额度保持零值。

```python
class _ExtendedLimits(ctypes.Structure)
```

继承关系：ctypes.Structure。下表列本类声明的字段；基类字段及其约束见对应类型链接。

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`_fields_`|list[tuple[str, type]]|类成员，不作为构造参数填写|[('basic', _BasicLimits), ('io', ctypes.c_ulonglong * 6), ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]|Windows作业结构的固定ABI布局；由ctypes使用，不是用户配置参数，不能按字段名称随意调整次序或宽度。|

源码：[`src/chronaxis/batch/process_tree.py:27`](../../../src/chronaxis/batch/process_tree.py#L27)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ProcessTree"></a>
## `ProcessTree`

持有一个工作进程树的关闭责任；Linux在GO前完成双向身份核验。

```python
ProcessTree(pid, *, registration=None, process=None)
```


源码：[`src/chronaxis/batch/process_tree.py:35`](../../../src/chronaxis/batch/process_tree.py#L35)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ProcessTree-__init__"></a>
### `ProcessTree.__init__`

登记本次工作进程的关闭责任；Windows 采用作业对象，Linux 在允许业务运行前核对进程组身份与内核能力。

```python
ProcessTree.__init__(pid, *, registration=None, process=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`pid`|int|是|无|位置或关键字。本次已启动工作进程的实际正整数 PID。Windows 将该进程纳入作业对象；Linux 要求它与 process.pid、启动握手声明的 PID 及独立进程组号一致。|
|`registration`|StartupGate &#124; None|否|None|仅关键字。Linux 启动握手的拥有者，用于 READY/ACK 身份核验和发送 GO；Linux 必须提供。Windows 不使用该参数，可保留默认 None。|
|`process`|multiprocessing.process.BaseProcess &#124; None|否|None|仅关键字。Linux 本次工作进程对象；借用其身份、退出哨兵及 join/is_alive 检查，不在本对象中关闭 Process 句柄。Linux 必须提供；Windows 可省略。|

#### 返回说明

__init__ 返回 None；构造所得 ProcessTree 持有作业句柄或 pidfd，由调用方在工作进程结束后关闭。

#### 异常说明

不支持的平台或缺少 Linux 进程组信号能力时抛 NotImplementedError；Linux 的进程或握手身份不符时抛 ValueError。等待、管道和系统调用错误原样传播。构造失败会先尝试清理，尚未释放的资源通过原异常的 process_tree_cleanup_owner 保留。

源码：[`src/chronaxis/batch/process_tree.py:38`](../../../src/chronaxis/batch/process_tree.py#L38)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ProcessTree-_register_linux"></a>
### `ProcessTree._register_linux`

通过本次进程的双向握手登记pidfd。

```python
ProcessTree._register_linux(pid, registration, process)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`pid`|int|是|无|位置或关键字。待登记进程的正整数 PID，必须与传入 Process 的实际 PID 相同；不接受借用其他任务的进程编号。|
|`registration`|StartupGate|是|无|位置或关键字。本次 spawn 创建的启动管道拥有者；先关闭父侧的子端副本，再完成 READY、PROBE/ACK 和 GO 握手。|
|`process`|multiprocessing.process.BaseProcess|是|无|位置或关键字。本次启动的进程对象；用于验证 PID、等待启动消息和后续关闭时回收组长，不接管外部进程。|

#### 返回说明

None；能力与身份核验完成后才发GO。

#### 异常说明

无效身份、握手或系统错误原样传播；未确认fd只关闭，不发送组信号。

源码：[`src/chronaxis/batch/process_tree.py:77`](../../../src/chronaxis/batch/process_tree.py#L77)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ProcessTree-_close_linux"></a>
### `ProcessTree._close_linux`

关闭已确认的进程组并核对实际消失。

```python
ProcessTree._close_linux()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None；未确认fd仅关闭。

#### 异常说明

组未消失或信号失败时保留责任；Linux close本身报错也不重试已释放编号。

源码：[`src/chronaxis/batch/process_tree.py:115`](../../../src/chronaxis/batch/process_tree.py#L115)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ProcessTree-_close_process_handle"></a>
### `ProcessTree._close_process_handle`

关闭登记期间真实打开的进程句柄。

```python
ProcessTree._close_process_handle()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

失败仍保留句柄。

源码：[`src/chronaxis/batch/process_tree.py:153`](../../../src/chronaxis/batch/process_tree.py#L153)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ProcessTree-close"></a>
### `ProcessTree.close`

关闭本次平台资源；Windows失败保留实际句柄，Linux只重试尚未结束的组。

```python
ProcessTree.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None；重复关闭安全。

#### 异常说明

第一个关闭错误，其余写入notes。
Windows作业关闭后结束残余后代；登记句柄失败仍尝试结束作业。
Linux组确认消失后只close一次pidfd；错误向上传播，不重试已释放编号。

源码：[`src/chronaxis/batch/process_tree.py:160`](../../../src/chronaxis/batch/process_tree.py#L160)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
