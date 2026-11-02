"""公开配置构建、静态检查和计划解释入口。

AnalysisPlan.from_dict接收版本3配置字典，load_analysis_plan读取JSON配置后构建
不可变计划。validate_analysis_plan报告声明检查和能力限制，explain_analysis_plan说明依赖、
历史需求和资源预算。只有load_analysis_plan读取指定配置文件，静态检查不打开CSV或DBC。
预设已按角色契约展开；实际执行和发布由根包AnalysisRunner及结果层负责，计划合法不表示已执行分析。
旧来源能力按静态报告保留限制，不因公共入口存在而自动放行。
当前配置使用同一套记录间隔与诊断声明，不提供旧版本解析或迁移入口。
"""

# 公开具体已实现入口，而非无类型占位类。
from .checks import PlanValidationError
from .plan import AnalysisPlan, load_analysis_plan
from .reports import ExplainReport, ValidationReport, explain_analysis_plan, validate_analysis_plan
from .sequences import SequencePlan
from .intervals import IntervalChoice, IntervalPlan, DiagnosticPlan

# 此包仅导出配置和静态报告；公共AnalysisRunner从chronaxis根包取得。
__all__ = ['AnalysisPlan', 'SequencePlan', 'PlanValidationError', 'load_analysis_plan', 'ValidationReport', 'ExplainReport', 'validate_analysis_plan', 'explain_analysis_plan', 'IntervalChoice', 'IntervalPlan', 'DiagnosticPlan']
