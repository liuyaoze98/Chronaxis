# chronaxis.batch.process_tree

将批量工作进程及其CAN读取子进程纳入同一个Windows作业对象。

主进程持有唯一作业句柄；工作进程先等待派发，归属登记成功后才运行用户计划。
关闭作业会结束残余后代，避免工作进程异常退出留下读取进程。不修改旧读取器。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`_BasicLimits`](#api-_BasicLimits)|对应Windows基本作业限制结构；仅设置关闭句柄时结束整个作业。|
|[`_ExtendedLimits`](#api-_ExtendedLimits)|对应Windows扩展作业限制，未使用的资源额度保持零值。|
|[`ProcessTree`](#api-ProcessTree)|持有一个工作进程树的关闭责任；当前公开结果发布仅支持Windows。|
|[`ProcessTree.__init__`](#api-ProcessTree-__init__)|登记实际PID。|
|[`ProcessTree.close`](#api-ProcessTree-close)|关闭树句柄，终止残余后代。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ctypes import wintypes
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

源码：[`src/chronaxis/batch/process_tree.py:12`](../../../src/chronaxis/batch/process_tree.py#L12)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

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

源码：[`src/chronaxis/batch/process_tree.py:22`](../../../src/chronaxis/batch/process_tree.py#L22)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ProcessTree"></a>
## `ProcessTree`

持有一个工作进程树的关闭责任；当前公开结果发布仅支持Windows。

```python
ProcessTree(pid)
```


源码：[`src/chronaxis/batch/process_tree.py:30`](../../../src/chronaxis/batch/process_tree.py#L30)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ProcessTree-__init__"></a>
### `ProcessTree.__init__`

登记实际PID。

```python
ProcessTree.__init__(pid)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`pid`|int|是|无|位置或关键字。已经启动、尚未领取分析任务的工作进程PID。归入Windows作业后，其后续CAN读取子进程也由同一作业回收。|

#### 返回说明

新对象。

#### 异常说明

平台或系统错误。

源码：[`src/chronaxis/batch/process_tree.py:33`](../../../src/chronaxis/batch/process_tree.py#L33)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ProcessTree-close"></a>
### `ProcessTree.close`

关闭树句柄，终止残余后代。

```python
ProcessTree.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

关闭失败仍保留句柄供重试。

源码：[`src/chronaxis/batch/process_tree.py:67`](../../../src/chronaxis/batch/process_tree.py#L67)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
