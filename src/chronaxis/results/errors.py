"""定义结果暂存、资源预算和发布的明确异常边界。

输入是结果层失败原因，输出是供调用者捕获的异常类型；不执行I/O或清理。
AnalysisError是分析执行和结果交付共用的失败基类，原始异常通过异常链保留。
"""


class AnalysisError(RuntimeError):
    """表示分析或结果交付失败；异常本身不承诺旧输出已回滚。"""


class BudgetExceededError(AnalysisError):
    """表示新分析层估算RAM或累计磁盘暂存超过显式限额。"""


class ResultClosedError(AnalysisError):
    """表示结果已经关闭，不能再创建迭代器、读取或发布。"""


class ResultFormatError(AnalysisError):
    """表示暂存行版本、结构或typed事实非法；禁止静默补值。"""


class ContributionsUnavailableError(AnalysisError):
    """表示本次选择不生成贡献明细；应改为full重新运行，不能把缺失明细当作零条计算。"""
