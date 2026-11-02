"""核对旧start_end的显式业务选择及等待时限。

输入为已定位INI和用户映射，输出新开始/结束规则的初始化及时限字段。
旧模式先准备再确认切片，新模式从start记录到end；mapping必须声明
start_end_timeout-v1。本模块不执行条件、读取日志或修复旧入口。
"""

from decimal import Decimal, InvalidOperation
from ..timebase import parse_duration
from .ini import problem, field_path, locate
from .models import LegacyImportIssue


def start_end_options(parser, fields, section, selected, issues):
    """检查显式新语义，按已审旧字段解释正时限和不限时。

    参数: parser/fields/section为原配置及定位；selected为段映射；issues接收差异。
    返回: timeout/emit_initial字典。异常: ImportProblem为配置非法；取消和内存错误原样传播。
    """
    path = '$.sections.' + section
    if type(selected) is not dict or set(selected) != {'name', 'window', 'semantics', 'emit_initial'}:
        problem('invalid_section_mapping', 'mapping', path,
                'start_end段映射必须含name/window/semantics/emit_initial')
    if selected['semantics'] != 'start_end_timeout-v1':
        problem('unconfirmed_start_end_semantics', 'mapping', path + '.semantics',
                '请明确选择start_end_timeout-v1：start开始、end结束、时限从start计')
    if type(selected['emit_initial']) is not bool:
        problem('invalid_start_end_initial', 'mapping', path + '.emit_initial', '必须明确填写布尔值')
    raw = parser.get(section, 'duration_sec', fallback='-1', raw=True)
    line, column = locate(fields, section, 'duration_sec')
    try:
        value = Decimal(raw)
        if not value.is_finite():
            raise ValueError('duration_sec必须有限')
        # 非正值是旧模式的不限时，不偷偷选择工程默认时长。
        # 正值保留紧凑指数表示，让时间解析器在分配定点字符串之前拒绝越界。
        timeout = None if value <= 0 else str(value) + 's'
        if timeout is not None and parse_duration(timeout).time_ns <= 0:
            raise ValueError('正时限不能小于可表示的纳秒')
    except (InvalidOperation, ValueError, OverflowError) as error:
        problem('invalid_duration', 'ini', field_path(section, 'duration_sec'), str(error), line, column)
    line, column = locate(fields, section, 'mode')
    issues.append(LegacyImportIssue('start_end_semantic_change', 'ini', field_path(section, 'mode'),
        '显式采用start开始/end结束/从start计时，改变旧start仅准备、end才开始切片。'
        '新时限精确推进，同刻已知end正常结束；可判断却未结束标timeout，缺数据另标中断或截断。'
        '开始采用新上升沿及映射的首次策略，活动中不排队；旧post不附加，非正duration为不限时。'
        '不宣称修复旧last_ts缺陷或旧逐帧等价。', line, column, 'warning'))
    return dict(timeout=timeout, emit_initial=selected['emit_initial'])
