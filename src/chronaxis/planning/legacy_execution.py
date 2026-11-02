"""在读取前校验逐消息计划的时间域与CAN读取策略；不选择历史兼容路径。"""

from ..core.models import Interval
from ..sources.can_spec import LegacyCANSpec
from .checks import PlanValidationError


def require_can_decode_scope(plan) -> None:
    """在资源创建前检查请求时间域及CAN策略，不自动更换执行方式。

    参数: plan为完整AnalysisPlan；直接构造或replace的typed声明同样接受检查。
    返回: None；requested按统一需求接普通、消息和原帧消费者，all保留显式完整诊断。
    异常: PlanValidationError定位时间域、陈旧绑定或来源策略错误；其他属性错误原样传播。
    边界: 不读文件、DBC或信号值；纯参数指标和空signals仍可请求其指标报文。
    """
    # typed replace不重新绑定表达式；不能借改dataset静默增删原声明的时间筛选。
    domain = plan.dataset.domain
    if domain is not None and not isinstance(domain, Interval):
        raise PlanValidationError('$.dataset.domain', '请求时间域需要Interval或整文件None声明')
    if type(plan.dataset.domain_explicit) is not bool:
        raise PlanValidationError('$.dataset.domain', 'domain_explicit需要原生bool')
    if plan.dataset.domain_explicit != (domain is not None):
        raise PlanValidationError('$.dataset.domain', 'domain_explicit必须与实际domain声明一致')
    if plan.bindings.domain != domain:
        raise PlanValidationError('$.dataset.domain', '请求时间域与原声明绑定不一致，需重新构建计划')
    # 先核有限静态选项；需要真实来源类型的其他约束仍由原计划校验承担。
    for index, source in enumerate(plan.sources):
        if source.source_type != 'can_blf' or not isinstance(source.config, LegacyCANSpec):
            continue
        scope = source.config.decode_scope
        path = f'$.sources[{index}].decode_scope'
        if type(scope) is not str or scope not in ('all', 'requested'):
            raise PlanValidationError(path, '需要all或requested')
        # 同一前置门禁也拒绝绕过dataclass构造器的typed检查范围替换。
        check = source.config.input_check
        if type(check) is not str or check not in ('auto', 'full'):
            raise PlanValidationError(f'$.sources[{index}].input_check', '需要auto或full')
        # 实际字段、普通样本、消息触发和原帧导出分别规划；不得因混合任务静默退回all。
