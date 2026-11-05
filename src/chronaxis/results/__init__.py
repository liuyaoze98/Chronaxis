"""提供typed结果行、共享预算、有限暂存、流式读取与发布协议。

导入不启动运行或打开文件；基础行模型和预算不加载NumPy、CAN或DBC。
实际请求ResultSpool或AnalysisResult时才导入暂存与发布模块及其依赖。
输入读取由执行层负责；本模块预算跟踪已登记资源，不保证整个进程的RSS上限。
"""

# 导出结果层异常。
from .errors import (AnalysisError, BudgetExceededError, ResultClosedError, ResultFormatError,
                     ContributionsUnavailableError)
from .budget import ResourceBudget
from .manifest import RunMetadata, OutputManifest, ExportManifest

__all__ = ['AnalysisError', 'BudgetExceededError', 'ResultClosedError', 'ResultFormatError', 'ContributionsUnavailableError', 'SummaryCalculationRow', 'SummaryCoverageCalculationRow', 'SummaryEventRow', 'SummarySequenceRow', 'SummarySegmentRow', 'SummaryContributionRow', 'SummaryInputRow', 'SummarySelectionRow', 'SummaryAggregationRow', 'SummaryHostedCalculationRow', 'ResultRow', 'ResourceBudget', 'ResultSpool', 'RunMetadata', 'OutputManifest', 'ExportManifest', 'AnalysisResult']


def __getattr__(name):
    """按需提供行模型、暂存和发布类，让纯预算与参考累计不形成依赖环。

    参数: name为请求的公开属性名称。返回: 对应原实现类，不创建实例。
    异常: AttributeError为未知名称；实际模块导入错误原样传播。
    副作用: 访问对应类才加载实现及其依赖，不读取输入或启动分析。
    """
    # 延迟加载结果模型，纯预算消费者导入时不建立执行层依赖。
    if name in ('SummaryCalculationRow', 'SummaryCoverageCalculationRow', 'SummaryEventRow', 'SummarySequenceRow', 'SummarySegmentRow', 'SummaryContributionRow', 'SummaryInputRow', 'SummarySelectionRow', 'SummaryAggregationRow', 'SummaryHostedCalculationRow', 'ResultRow'):
        from . import rows
        return getattr(rows, name)
    if name == 'ResultSpool':
        from .spool import ResultSpool
        return ResultSpool
    if name == 'AnalysisResult':
        from .result import AnalysisResult
        return AnalysisResult
    raise AttributeError(f'chronaxis.results没有公开属性{name!r}')
