"""把分析计划交给同一公共入口检查、解释和执行，返回可流式读取的结果。

AnalysisRunner接收已经由load_analysis_plan或AnalysisPlan.from_dict构建的计划。validate和explain
只查看声明，沿用planning.reports，不打开CSV、DBC或旧日志。run才创建独立
RunSession，首次扫描来源、封存新历史并依次运行已有四个分析阶段；这里不重写
读取、数值算法或发布。返回AnalysisResult表示analysis_complete，write另行发布。

显式backend只替换内部执行视图中的计算方式，保留原配置identity、raw_config和
来源对象；清单另记实际后端。AnalysisRunner本身没有输入、FD或跨运行状态，能够重复运行
同一计划，每次使用独立资源。成功前全部输入关闭；失败保原cause及最高运行恢复
owner，取消保原KeyboardInterrupt/SystemExit。暂存与诊断保留，不宣称回滚输入。
"""

# 只在run时加载实际执行组件；静态检查不创建预算、工作目录或来源adapter。
from dataclasses import replace
from .planning.plan import AnalysisPlan
from .planning.models import ExecutionPlan
from .planning.reports import validate_analysis_plan, explain_analysis_plan
from .results.errors import AnalysisError
from .results.spool import _cleanup_owner


class AnalysisRunner:
    """保存可选后端覆盖，复用同一静态校验，逐次创建独立运行资源。

    _backend为None或已支持的明确后端，不自动回退。实例不持有执行结果或活动
    session；结果所有权交给调用者，失败未清完资源通过原异常的最高owner恢复。
    """

    def __init__(self, backend=None):
        """选择是否覆盖计划后端，不读取任何来源或配置文件。

        参数: backend为None/reference/numpy；None使用各次计划原execution.backend。
        返回: None；初始化实例状态。异常: TypeError为非文本覆盖；ValueError为未知后端。
        """
        # 明确拒绝任意对象和隐藏回退，不能把拼错的后端当成默认NumPy。
        if backend is not None:
            if type(backend) is not str:
                raise TypeError('AnalysisRunner backend需要reference、numpy或None')
            if backend not in ('reference', 'numpy'):
                raise ValueError('AnalysisRunner仅支持reference与numpy后端')
        self._backend = backend

    @property
    def backend(self):
        """读取构造时的覆盖选择，不表示某个尚未运行计划的实际后端。

        参数: 无。返回: None/reference/numpy。异常: 无。
        """
        return self._backend

    def _effective_plan(self, plan):
        """保留原声明身份，只为明确覆盖创建内部执行视图。

        参数: plan为已构建AnalysisPlan。返回: 原plan或仅execution.backend不同的新view。
        异常: TypeError为非计划/执行声明；不重新解析配置或复制原输入行。
        """
        if not isinstance(plan, AnalysisPlan) or not isinstance(plan.execution, ExecutionPlan):
            raise TypeError('AnalysisRunner需要load_analysis_plan或AnalysisPlan.from_dict构建的计划')
        # 来源、绑定及raw_config仍借原对象；后端是本次执行选项，不伪造另一份输入。
        if self._backend is None or self._backend == plan.execution.backend:
            return plan
        return replace(plan, execution=replace(plan.execution, backend=self._backend))

    def validate(self, plan):
        """报告声明是否合法及执行路径是否已接入，不提前读取数据。

        参数: plan为已构建AnalysisPlan。返回: 同一共享ValidationReport，保留实际字段/范围未验警告。
        异常: TypeError为非AnalysisPlan或非法执行模型；正常计划的静态问题写入报告errors，
            不以校验成功证明输入文件内容有效。副作用: 无来源I/O或目录创建。
        """
        # 使用相同有效视图和纯静态报告，避免校验后偷偷换另一套后端能力。
        return validate_analysis_plan(self._effective_plan(plan))

    def explain(self, plan):
        """列出真实依赖、各节点后端、历史需求及声明预算，不启动分析。

        参数: plan为已构建AnalysisPlan。返回: ExplainReport，plan_identity保原声明身份。
        异常: TypeError为非AnalysisPlan或非法执行模型；调用者绕过解析器手工破坏typed
            引用时可能产生AttributeError/KeyError，应重新从完整配置构造计划。
        副作用: 不读取CSV/DBC，也不测量实耗。
        """
        # 规则状态驱动与数组节点分别由同一报告说明，不把覆盖当整个计划标量回退。
        return explain_analysis_plan(self._effective_plan(plan))

    def run(self, plan, work_dir=None):
        """验证后执行一次真实分析，输入全关才返回独立AnalysisResult。

        参数: plan为已构建AnalysisPlan；work_dir为全新工作目录或None（唯一专用目录）。
        返回: analysis_complete的AnalysisResult，由调用者close/上下文管理，write另行发布。
        异常: TypeError为错误plan；验证或运行错误为AnalysisError，保原cause和诊断；
            KeyboardInterrupt/SystemExit原样传播。持续清理失败用runner_cleanup_owner.close恢复。
        副作用: 创建本次新暂存；扫描来源一次、后续仅回读新history，不自动删除或发布文件。
        """
        effective = self._effective_plan(plan)
        validation = validate_analysis_plan(effective)
        if validation.errors or not validation.valid or not validation.execution_ready:
            raise AnalysisError('计划尚不能执行：' + ('；'.join(validation.errors) or '所需执行路径不可用'))
        session = None
        try:
            # 惰性加载保证validate/explain没有实际来源组件的创建或调用。
            from .execution.run_session import RunSession
            session = RunSession(effective, work_dir=work_dir)
            return session.execute()
        except BaseException as exc:
            # 未返回构造有自己的最高owner；正常构造后仍由唯一session关闭全部本次资源。
            owner = getattr(exc, 'runner_cleanup_owner', None)
            if owner is None:
                owner = session
            if owner is not None:
                _cleanup_owner(owner, exc, 'runner_cleanup_owner', '公共分析运行')
            # 保留原分析异常与取消类型；其他业务错误通过cause说明最初失败位置。
            if isinstance(exc, (AnalysisError, KeyboardInterrupt, SystemExit)):
                raise
            error = AnalysisError('分析运行失败：' + str(exc))
            recovery = getattr(exc, 'runner_cleanup_owner', None)
            if recovery is not None:
                error.runner_cleanup_owner = recovery
            for note in getattr(exc, '__notes__', ()):
                error.add_note(note)
            raise error from exc
