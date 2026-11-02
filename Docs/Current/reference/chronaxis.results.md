# chronaxis.results

提供带有明确类型的结果行、共享预算、有限暂存、流式读取与发布协议。

导入不启动运行或打开文件；基础行模型和预算不加载NumPy、CAN或DBC。
实际请求ResultSpool或AnalysisResult时才导入暂存与发布模块及其依赖。
输入读取由执行层负责；本模块预算跟踪已登记资源，不保证整个进程的RSS上限。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisError](chronaxis.results.errors.md#api-AnalysisError)、[AnalysisResult](chronaxis.results.result.md#api-AnalysisResult)、[BudgetExceededError](chronaxis.results.errors.md#api-BudgetExceededError)、[ContributionsUnavailableError](chronaxis.results.errors.md#api-ContributionsUnavailableError)、[OutputManifest](chronaxis.results.manifest.md#api-OutputManifest)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[ResultFormatError](chronaxis.results.errors.md#api-ResultFormatError)、[ResultSpool](chronaxis.results.spool.md#api-ResultSpool)、[RunMetadata](chronaxis.results.manifest.md#api-RunMetadata)

## 对象导航

|对象|用途|
|---|---|
|[`__getattr__`](#api-__getattr__)|按需提供行模型、暂存和发布类，让纯预算与参考累计不形成依赖环。|

## 导出名称

`AnalysisError`, `BudgetExceededError`, `ResultClosedError`, `ResultFormatError`, `ContributionsUnavailableError`, `SummaryCalculationRow`, `SummaryCoverageCalculationRow`, `SummaryEventRow`, `SummarySequenceRow`, `SummarySegmentRow`, `SummaryContributionRow`, `SummaryInputRow`, `SummarySelectionRow`, `ResultRow`, `ResourceBudget`, `ResultSpool`, `RunMetadata`, `OutputManifest`, `AnalysisResult`

重导出保持定义位置的签名；按上级[总索引](index.md)查找对象名。

公开重导出按[公开API索引](../api.md)查询定义、用途和调用示例。

<details><summary>导入与重导出来源（展开）</summary>

```python
from .errors import AnalysisError, BudgetExceededError, ResultClosedError, ResultFormatError, ContributionsUnavailableError
from .budget import ResourceBudget
from .manifest import RunMetadata, OutputManifest
```

</details>

<a id="api-__getattr__"></a>
## `__getattr__`

按需提供行模型、暂存和发布类，让纯预算与参考累计不形成依赖环。

```python
__getattr__(name)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|位置或关键字。结果包请求的公开属性名；按当前导出集合加载，未公开名称不提供旧名回退。|

### 返回说明

对应原实现类，不创建实例。

### 异常说明

AttributeError为未知名称；实际模块导入错误原样传播。

### 副作用说明

访问对应类才加载实现及其依赖，不读取输入或启动分析。

源码：[`src/chronaxis/results/__init__.py:17`](../../../src/chronaxis/results/__init__.py#L17)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
