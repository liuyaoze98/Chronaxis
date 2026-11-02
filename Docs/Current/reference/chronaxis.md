# chronaxis

公开时间转换、分析计划、公共AnalysisRunner和流式结果入口。

时间入口接收显式单位时间、日期或整数纳秒序列，返回转换诊断与参考结果。
AnalysisPlan、load_analysis_plan、validate_analysis_plan和explain_analysis_plan提供配置构建、静态
检查及依赖解释；访问这些名称时才加载计划模块及其数组来源依赖。
直接导入时间或核心入口只需标准库，不加载CAN或DBC，也不创建文件和日志。
预设入口校验角色并生成公共声明；结果入口提供有限暂存、流式读取和Windows原子发布。
AnalysisRunner接收内存信号、独立信号CSV、BLF及显式格式的ASC/原始报文CSV；访问该名称才加载运行包装。
BatchRunner或run_batch在外层调度独立计划，各任务使用独立状态和结果目录。
BLF沿用sclicer-functions-v1旧读取链；新文本CAN使用can-text-v1独立入口。
信号表及原帧导出可分别选择原始采样或连续量重采样，配置和边界见当前用户手册的输入与导出章节。
具体配置和输入限制见当前用户手册。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisError](chronaxis.results.errors.md#api-AnalysisError)、[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)、[AnalysisResult](chronaxis.results.result.md#api-AnalysisResult)、[AnalysisRunner](chronaxis.runner.md#api-AnalysisRunner)、[OutputManifest](chronaxis.results.manifest.md#api-OutputManifest)、[PlanFragment](chronaxis.planning.preset_models.md#api-PlanFragment)、[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)、[PresetSpec](chronaxis.planning.preset_models.md#api-PresetSpec)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[RunMetadata](chronaxis.results.manifest.md#api-RunMetadata)、[TimeConversion](chronaxis.timebase.conversion.md#api-TimeConversion)、[TimeOverflowError](chronaxis.timebase.conversion.md#api-TimeOverflowError)

## 对象导航

|对象|用途|
|---|---|
|[`__getattr__`](#api-__getattr__)|按公开名称加载计划接口，避免基础时间入口立即依赖数组模块。|

## 导出名称

`TimeConversion`, `TimeOverflowError`, `checked_add_ns`, `convert_time`, `parse_datetime_ns`, `parse_duration`, `shift_times_reference`, `time_deltas_reference`, `AnalysisPlan`, `PlanValidationError`, `load_analysis_plan`, `validate_analysis_plan`, `explain_analysis_plan`, `PresetSpec`, `PlanFragment`, `build_preset`, `resolve_preset_roles`, `AnalysisResult`, `OutputManifest`, `RunMetadata`, `AnalysisError`, `ResultClosedError`, `AnalysisRunner`, `BatchJob`, `BatchJobResult`, `BatchReport`, `BatchRunner`, `BatchPlan`, `load_batch_plan`, `run_batch`

重导出保持定义位置的签名；按上级[总索引](index.md)查找对象名。

公开重导出按[公开API索引](../api.md)查询定义、用途和调用示例。

<details><summary>导入与重导出来源（展开）</summary>

```python
from .timebase import TimeConversion, TimeOverflowError, checked_add_ns, convert_time, parse_datetime_ns, parse_duration, shift_times_reference, time_deltas_reference
```

</details>

<a id="api-__getattr__"></a>
## `__getattr__`

按公开名称加载计划接口，避免基础时间入口立即依赖数组模块。

```python
__getattr__(name: str)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|位置或关键字。Python请求的模块属性名，与配置表达式的属性访问无关。|

### 返回说明

公开名单中的类或函数对象。返回接口本身，不构造计划或打开分析输入。

### 异常说明

AttributeError: 名称未在公开名单中。
    ImportError等导入
访问计划接口时所需依赖缺失或模块加载失败。

### 副作用说明

导入planning及其依赖；不缓存任何会话输入或绑定。

源码：[`src/chronaxis/__init__.py:33`](../../../src/chronaxis/__init__.py#L33)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
