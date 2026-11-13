# `chronaxis.process_capabilities`

按实际调度需求提示 Linux 受管工作进程的能力，不执行分析。

只在调用者确认需要受管工作进程时，打开本进程的 pidfd 并用信号0检查接口。
不创建进程、不读取日志、不改变进程组，不发送真实信号；每次探测后关闭描述符。
检查结果只描述当前环境，运行时的身份握手、权限与清理检查仍须执行。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`_pidfd_group_capability`](#api-_pidfd_group_capability)|用本进程的描述符检查组信号标志，不依赖内核版本字符串。|
|[`managed_worker_warnings`](#api-managed_worker_warnings)|为实际需要受管工作进程的计划生成当前 Linux 环境提示。|
|[`warn_managed_worker`](#api-warn_managed_worker)|为没有静态报告返回值的运行准备入口发出同一环境提示。|

<a id="api-_pidfd_group_capability"></a>
## `_pidfd_group_capability`

用本进程的描述符检查组信号标志，不依赖内核版本字符串。

```python
_pidfd_group_capability()
```

参数：无显式参数。


### 参数说明

无。

### 返回说明

(状态, 原因)，状态为supported/unavailable/unknown。

### 异常说明

关闭描述符失败或取消原样传播；普通探测OSError保留errno为提示原因。

源码：[`src/chronaxis/process_capabilities.py:15`](../../../src/chronaxis/process_capabilities.py#L15)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-managed_worker_warnings"></a>
## `managed_worker_warnings`

为实际需要受管工作进程的计划生成当前 Linux 环境提示。

```python
managed_worker_warnings(required, context)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`required`|bool|是|无|位置或关键字。实际调度是否需要受管工作进程；false不探测Linux接口。|
|`context`|str|是|无|位置或关键字。用于提示的入口名称，例如普通分析或独立批量任务；不参与调度判断。|

### 返回说明

提示字符串tuple；不需要该路径、其他平台或探测通过时为空。

### 异常说明

探测资源关闭失败或取消传播；不把环境提示改成配置错误。

源码：[`src/chronaxis/process_capabilities.py:49`](../../../src/chronaxis/process_capabilities.py#L49)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-warn_managed_worker"></a>
## `warn_managed_worker`

为没有静态报告返回值的运行准备入口发出同一环境提示。

```python
warn_managed_worker(required, context)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`required`|bool|是|无|位置或关键字。实际调度是否需要受管工作进程；false不探测Linux接口。|
|`context`|str|是|无|位置或关键字。用于提示的入口名称，例如普通分析或独立批量任务；不参与调度判断。|

### 返回说明

None。

### 异常说明

资源关闭或取消传播；告警遵循调用者的Python warnings策略。

源码：[`src/chronaxis/process_capabilities.py:68`](../../../src/chronaxis/process_capabilities.py#L68)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
