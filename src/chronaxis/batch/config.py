"""加载批量清单；显式jobs保存路径，template展开为每文件独立计划。

JSON/YAML重复键、非有限值和错误定位沿用共享配置语法规则；实际独立计划到
jobs在worker启动时加载；template在此时读取模板和必要DBC元数据，均不预读业务日志。
"""

from pathlib import Path
from ..configuration import load_configuration, ConfigurationError
from ..configuration.diagnostics import locate_error
from ..planning.checks import PlanValidationError, configuration_error
from .models import BatchPlan


def load_batch_plan(path: str | Path) -> BatchPlan:
    """读取批量YAML或JSON文件，建立独立任务及其调度设置。

    参数:
        path (str | Path): UTF-8批量配置路径；子计划相对路径以本文件目录为起点。
    返回:
        BatchPlan: 已检查批量结构的不可变计划；template已展开，jobs仍保存路径，均未读取业务输入。
    异常:
        PlanValidationError: 路径类型不合法、文件不可读、编码/语法错误或批量字段不合法。
            先按错误字段路径修正批量或模板文件；jobs中的子计划错误在任务启动时记入任务报告。
    副作用:
        读取批量文件，template模式还读取模板与必要DBC、枚举输入集合；不创建输出目录。"""
    if not isinstance(path, (str, Path)):
        raise PlanValidationError('$', '批量配置路径必须为Path或文本')
    target = Path(path).absolute()
    try:
        document = load_configuration(target)
        return BatchPlan.from_dict(document.data, base_dir=target.parent)
    except ConfigurationError as error:
        raise configuration_error(error) from error
    except PlanValidationError as error:
        raise locate_error(error,document)
    except (OSError, UnicodeError, ValueError, TypeError) as error:
        raise PlanValidationError('$',str(error),'load_error',source=str(target)) from error
