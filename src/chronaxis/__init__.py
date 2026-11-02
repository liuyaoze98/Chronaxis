"""公开时间转换、分析计划、公共AnalysisRunner和流式结果入口。

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
"""

# 普通根包导入仍只加载标准库时间协议；计划、运行和结果入口按需加载。
from .timebase import (
    TimeConversion, TimeOverflowError, checked_add_ns, convert_time,
    parse_datetime_ns, parse_duration, shift_times_reference, time_deltas_reference,
)

# 明确公开范围；没有隐式文件读取、后端回退或CAN依赖。
__all__ = [
    "TimeConversion", "TimeOverflowError", "checked_add_ns", "convert_time",
    "parse_datetime_ns", "parse_duration", "shift_times_reference", "time_deltas_reference",
    "AnalysisPlan", "PlanValidationError", "load_analysis_plan", "validate_analysis_plan", "explain_analysis_plan",
    "PresetSpec", "PlanFragment", "build_preset", "resolve_preset_roles",
    "AnalysisResult", "OutputManifest", "RunMetadata", "AnalysisError", "ResultClosedError",
    "AnalysisRunner",
    "BatchJob", "BatchJobResult", "BatchReport", "BatchRunner", "BatchPlan", "load_batch_plan", "run_batch",
]


def __getattr__(name: str):
    """按公开名称加载计划接口，避免基础时间入口立即依赖数组模块。

    参数:
        name (str): Python请求的模块属性名，与配置表达式的属性访问无关。
    返回:
        公开名单中的类或函数对象。返回接口本身，不构造计划或打开分析输入。
    异常:
        AttributeError: 名称未在公开名单中。
        ImportError等导入异常: 访问计划接口时所需依赖缺失或模块加载失败。
    副作用:
        导入planning及其依赖；不缓存任何会话输入或绑定。
    """
    # Python模块只公开列出的名称；配置表达式的属性访问仍由独立语法检查拒绝。
    if name in ('BatchJob', 'BatchJobResult', 'BatchReport', 'BatchRunner', 'BatchPlan', 'load_batch_plan', 'run_batch'):
        # 取得批量入口时才加载模型；普通根包和CLI帮助仍不加载数组或来源。
        from . import batch
        return getattr(batch, name)
    if name == 'AnalysisRunner':
        # 取得类本身不创建session或输入；validate/explain仍只消费冻结计划声明。
        from .runner import AnalysisRunner
        return AnalysisRunner
    if name in ('AnalysisResult', 'OutputManifest', 'RunMetadata', 'AnalysisError', 'ResultClosedError'):
        # 结果层只依赖标准库和核心模型，访问入口也不启动任何读取或发布。
        from .results import AnalysisResult, OutputManifest, RunMetadata, AnalysisError, ResultClosedError
        return {'AnalysisResult': AnalysisResult, 'OutputManifest': OutputManifest, 'RunMetadata': RunMetadata,
                'AnalysisError': AnalysisError, 'ResultClosedError': ResultClosedError}[name]
    if name in ('PresetSpec', 'PlanFragment', 'build_preset', 'resolve_preset_roles'):
        # 预设是外部领域构建层，根包普通导入仍仅加载标准库时间协议。
        from .presets import PresetSpec, PlanFragment, build_preset, resolve_preset_roles
        return {'PresetSpec': PresetSpec, 'PlanFragment': PlanFragment, 'build_preset': build_preset,
                'resolve_preset_roles': resolve_preset_roles}[name]
    if name not in ('AnalysisPlan', 'PlanValidationError', 'load_analysis_plan', 'validate_analysis_plan', 'explain_analysis_plan'):
        # Python正常未知模块属性行为，不静默补占位。
        raise AttributeError(f'chronaxis没有公开属性{name!r}')
    # 只有用户实际访问计划接口时加载数组来源依赖。
    from .planning import AnalysisPlan, PlanValidationError, load_analysis_plan, validate_analysis_plan, explain_analysis_plan
    # 固定映射返回具体能力，不用eval/getattr任意对象或缓存输入绑定。
    return {'AnalysisPlan': AnalysisPlan, 'PlanValidationError': PlanValidationError, 'load_analysis_plan': load_analysis_plan,
            'validate_analysis_plan': validate_analysis_plan, 'explain_analysis_plan': explain_analysis_plan}[name]
