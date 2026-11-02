# chronaxis.planning.record_execution

声明新记录流当前可执行范围；静态报告与实际会话共用同一检查。

这里只检查有限配置，不读取来源，不把尚尚未接入可运行流程的能力报为已支持。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`is_event_duration`](#api-is_event_duration)|识别事件总时长的静态声明，不导入执行层。|
|[`record_execution_errors`](#api-record_execution_errors)|检查会话时间指标的已接线路径。|

<a id="api-is_event_duration"></a>
## `is_event_duration`

识别事件总时长的静态声明，不导入执行层。

```python
is_event_duration(request)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`request`|CalculationPlan|是|无|位置或关键字。当前指标请求，包含ID、统计范围、算子、表达式和缺失处理政策。|

### 返回说明

bool。

### 异常说明

无。

源码：[`src/chronaxis/planning/record_execution.py:7`](../../../src/chronaxis/planning/record_execution.py#L7)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-record_execution_errors"></a>
## `record_execution_errors`

检查会话时间指标的已接线路径。

```python
record_execution_errors(plan)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|AnalysisPlan|是|无|位置或关键字。已完成静态解析的分析计划，包含来源、绑定、规则、指标、间隔选择和输出要求。|

### 返回说明

错误tuple，空值表示当前组合可执行。

### 异常说明

非法带有明确类型的对象属性错误传播；不访问文件或修改计划。

源码：[`src/chronaxis/planning/record_execution.py:14`](../../../src/chronaxis/planning/record_execution.py#L14)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
