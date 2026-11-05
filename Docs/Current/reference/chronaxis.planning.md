# `chronaxis.planning`

公开配置构建、静态检查和计划解释入口。

AnalysisPlan.from_dict接收版本4配置字典，load_analysis_plan读取JSON配置后构建
不可变计划。validate_analysis_plan报告声明检查和能力限制，explain_analysis_plan说明依赖、
历史需求和资源预算。只有load_analysis_plan读取指定配置文件，静态检查不打开CSV或DBC。
预设已按角色契约展开；实际执行和发布由根包AnalysisRunner及结果层负责，计划合法不表示已执行分析。
旧来源能力按静态报告保留限制，不因公共入口存在而自动放行。
当前配置使用同一套记录间隔与诊断声明，不提供旧版本解析或迁移入口。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AggregationPlan](chronaxis.planning.aggregations.md#api-AggregationPlan)、[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)、[DiagnosticPlan](chronaxis.planning.intervals.md#api-DiagnosticPlan)、[ExplainReport](chronaxis.planning.reports.md#api-ExplainReport)、[IntervalChoice](chronaxis.planning.intervals.md#api-IntervalChoice)、[IntervalPlan](chronaxis.planning.intervals.md#api-IntervalPlan)、[LookupTablePlan](chronaxis.core.lookup.md#api-LookupTablePlan)、[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)、[SequencePlan](chronaxis.planning.sequences.md#api-SequencePlan)、[ValidationReport](chronaxis.planning.reports.md#api-ValidationReport)

## 对象导航

|对象|用途|
|---|---|

## 导出名称

`AnalysisPlan`, `SequencePlan`, `PlanValidationError`, `load_analysis_plan`, `ValidationReport`, `ExplainReport`, `validate_analysis_plan`, `explain_analysis_plan`, `IntervalChoice`, `IntervalPlan`, `DiagnosticPlan`, `LookupTablePlan`

重导出保持定义位置的签名；按上级[总索引](index.md)查找对象名。

公开重导出按[公开API索引](../api.md)查询定义、用途和调用示例。

<details><summary>导入与重导出来源（展开）</summary>

```python
from .checks import PlanValidationError
from .plan import AnalysisPlan, load_analysis_plan
from .aggregations import AggregationPlan
from .reports import ExplainReport, ValidationReport, explain_analysis_plan, validate_analysis_plan
from .sequences import SequencePlan
from .intervals import IntervalChoice, IntervalPlan, DiagnosticPlan
from ..core.lookup import LookupTablePlan
```

</details>
