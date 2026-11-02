"""把旧 slope 字符串拆为明确的完整窗口规则，不执行旧配置。

输入为一个原表达式、显式名称映射和该段的迁移选择；输出 window_delta
字段及可定位的差异报告。先识别固定前缀，再从右侧取阈值，剩余原信号名
必须完整命中 aliases，因此信号名可以包含下划线。此模块不读数据或 DBC，
不修复旧构造器，也不把完整窗口计算声称为旧样本口径的逐帧等价实现。
"""

from decimal import Decimal, InvalidOperation
import math
import re

from ..timebase import parse_duration
from .ini import field_path, locate, problem
from .models import LegacyImportIssue


def slope_rule(text, aliases, selected, fields, section, issues):
    """按显式迁移选择生成一个完整窗口规则。

    参数: text 为原 expr；aliases 为完整旧名称到新别名的映射；selected 为
    段映射；fields/section 定位原字段；issues 接收兼容差异。
    返回: 可交给 AnalysisPlan 的规则字典。异常: ImportProblem 表示有定位的
    配置问题；内存错误及取消原样传播。阈值沿用信号单位，不除以窗口时长。
    """
    path, (line, column) = field_path(section, 'expr'), locate(fields, section, 'expr')
    mapping_path = '$.sections.' + section
    expected = {'name', 'window', 'coverage_policy', 'emit_initial', 'retrigger'}
    if type(selected) is not dict or set(selected) != expected:
        problem('invalid_section_mapping', 'mapping', mapping_path,
                'slope段映射必须包含name/window/coverage_policy/emit_initial/retrigger')
    # 初始化和重复触发不能从旧锁存器猜测，要求调用方逐段作出明确选择。
    if selected['coverage_policy'] != 'full':
        problem('unsupported_slope_coverage', 'mapping', mapping_path + '.coverage_policy',
                '当前仅支持full完整窗口；legacy_samples尚未实现，不能默默替换')
    if type(selected['emit_initial']) is not bool:
        problem('invalid_slope_initial', 'mapping', mapping_path + '.emit_initial', '必须明确填写布尔值')
    if selected['retrigger'] not in ('edge', 'once'):
        problem('invalid_slope_retrigger', 'mapping', mapping_path + '.retrigger', '必须选择edge或once')
    match = re.fullmatch(r'_(slope2?)_(rise|fall|any)_([^_]+)_(.+)', text.strip())
    if match is None:
        problem('invalid_slope_syntax', 'ini', path,
                '需要_slope或_slope2、rise/fall/any、秒窗口、完整信号名及非负阈值', line, column)
    legacy_operator, direction, window, remainder = match.groups()
    # 最右分隔符属于阈值；信号名本身不按下划线拆开，也不接受旧未使用的尾字段。
    signal, separator, threshold_text = remainder.rpartition('_')
    if not separator or not signal or signal not in aliases:
        problem('missing_slope_alias', 'ini', path,
                '无法把完整信号名映射到aliases：' + signal + '；请明确名称，不会丢弃额外尾字段', line, column)
    if re.fullmatch(r'(?:\d+(?:\.\d*)?|\.\d+)s', window) is None:
        problem('invalid_slope_window', 'ini', path, '窗口必须为正的十进制秒数并以s结束', line, column)
    try:
        if parse_duration(window).time_ns <= 0:
            raise ValueError('窗口必须大于零')
    except (ValueError, OverflowError) as error:
        problem('invalid_slope_window', 'ini', path, str(error), line, column)
    try:
        if re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', threshold_text) is None:
            raise ValueError('阈值须为十进制数值')
        threshold = Decimal(threshold_text)
        if not threshold.is_finite() or threshold < 0:
            raise ValueError('阈值必须有限且非负')
        floating = float(threshold)
        if not math.isfinite(floating) or threshold != 0 and floating == 0:
            raise ValueError('阈值超出可表示的数值范围')
        # 整数保留精度；小数遵循配置已有的float64数值契约。
        number = int(threshold) if threshold == threshold.to_integral_value() else floating
    except (InvalidOperation, ValueError, OverflowError) as error:
        problem('invalid_slope_threshold', 'ini', path, str(error), line, column)
    issues.append(LegacyImportIssue('slope_semantic_differences', 'ini', path,
        '按文档字符串意图迁移，不宣称旧构造器可运行：旧代码误要求7段且忽略尾字段。'
        '新规则要求完整窗口与有效覆盖；旧规则至少两点即可。slope要求整窗单调，'
        '修正旧any的单调检查恒真；slope2不要求单调。初始化和重触发使用显式mapping，'
        '不复制旧触发后返回False的锁存。pre/post生成触发点周围的固定窗口，'
        '不复制旧single逐帧退出计时或缓冲重复写出。', line, column, 'warning'))
    return dict(name=selected['name'], rule_type='window_delta', signal=aliases[signal], window=window,
                direction=direction, threshold=number, monotonic=legacy_operator == 'slope',
                coverage_policy='full', emit_initial=selected['emit_initial'], retrigger=selected['retrigger'])
