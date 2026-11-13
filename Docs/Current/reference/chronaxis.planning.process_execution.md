# `chronaxis.planning.process_execution`

静态检查单会话文件读取并行的支持范围，不打开日志或DBC。

进程数与文件归并分别检查，明确拒绝未接入的来源及嵌套并行。
只声明执行上限，不能凭校验成功证明文件内部有序或实际使用了多个进程。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`process_execution_errors`](#api-process_execution_errors)|核有效计划的进程与归并声明。|
|[`source_execution_facts`](#api-source_execution_facts)|解释文件组织与读取进程上限。|

<a id="api-process_execution_errors"></a>
## `process_execution_errors`

核有效计划的进程与归并声明。

```python
process_execution_errors(plan)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|AnalysisPlan|是|无|位置或关键字。本次已应用API/CLI覆盖的有效执行视图；只查声明，不读取业务输入或启动工作进程。|

### 返回说明

错误tuple。

### 异常说明

无输入IO。

源码：[`src/chronaxis/planning/process_execution.py:11`](../../../src/chronaxis/planning/process_execution.py#L11)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-source_execution_facts"></a>
## `source_execution_facts`

解释文件组织与读取进程上限。

```python
source_execution_facts(plan)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|AnalysisPlan|是|无|位置或关键字。本次已应用API/CLI覆盖的有效执行视图；只查声明，不读取业务输入或启动工作进程。|

### 返回说明

有限dict元组。

### 异常说明

无；不读输入。

源码：[`src/chronaxis/planning/process_execution.py:34`](../../../src/chronaxis/planning/process_execution.py#L34)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
