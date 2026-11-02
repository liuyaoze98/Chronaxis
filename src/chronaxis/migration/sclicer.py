"""把受支持Sclicer段转换为新活动或固定窗口，完整报告边界差异。

输入是已定位INI、显式mapping及本次独立分析字典；输出只修改该新字典的
rules/windows并追加字段去向和警告。不执行旧触发器、eval或来源I/O。
single的post只作为exit_delay，start_only的post不再次延长固定duration。
显式sclicer_slope使用完整window_delta和触发点周围的pre/post窗口，差异写入报告。
显式sclicer_start_end还要求mapping确认新开始/结束含义，旧post不附加。
"""

import ast
from decimal import Decimal, InvalidOperation

from ..timebase import parse_duration
from .ini import field_path, locate, mark, problem
from .models import LegacyImportIssue
from .slope import slope_rule
from .start_end import start_end_options


def _ini_problem(fields, section, key, code, message, *, headers=None):
    """附原字段行列后拒绝，缺失字段回退到原段头。

    参数: fields/section/key为字段定位，code/message为原因；headers为可选原段行号。
    返回: 无。异常: ImportProblem；不为缺失字段编造一个不存在的字段行。
    """
    line, column = locate(fields, section, key)
    if line is None and headers is not None:
        line, column = headers[section], 1
    problem(code, 'ini', field_path(section, key), message, line, column)


def _seconds(parser, fields, section, key, default, *, positive=False):
    """把旧秒数转换为显式精确时长，不猜工程参数或接受NaN。

    参数: parser/fields/section/key为原定位；default为已审旧默认；positive限定正值。
    返回: 带s的时长文本。异常: ImportProblem为非法或不能精确表示的时长。
    """
    value = parser.get(section, key, fallback=default, raw=True)
    try:
        number = Decimal(value)
        if not number.is_finite() or number < 0 or positive and number == 0:
            raise ValueError('时长必须有限且非负，固定窗口须大于零')
        # 保留紧凑指数表示；由有界时间解析器检查范围，不能先展开巨量零。
        result = str(number) + 's'
        parse_duration(result)
    except (InvalidOperation, ValueError, OverflowError) as error:
        _ini_problem(fields, section, key, 'invalid_duration', str(error))
    return result


def _boolean(parser, fields, section, key, default):
    """沿ConfigParser旧布尔词表读取开关；参数: 原定位和默认；返回: bool；异常: ImportProblem。"""
    try:
        return parser.getboolean(section, key, fallback=default)
    except ValueError as error:
        _ini_problem(fields, section, key, 'invalid_boolean', str(error))


class _AliasTransformer(ast.NodeTransformer):
    """只替换AST Name，保字符串literal、原大小写和运算结合顺序。"""

    def __init__(self, aliases, fields, section, key):
        """保本次显式别名表；参数: 别名及原表达式定位；返回: None；异常: 无。"""
        self.aliases, self.fields, self.section, self.key = aliases, fields, section, key

    def visit_Name(self, node):
        """替换一个字段引用；参数: Name节点；返回: 新Name；异常: ImportProblem为缺映射。"""
        if node.id not in self.aliases:
            _ini_problem(self.fields, self.section, self.key, 'missing_alias', '缺少原名称的显式alias：' + node.id)
        return ast.copy_location(ast.Name(id=self.aliases[node.id], ctx=ast.Load()), node)

    def visit_Call(self, node):
        """仅保现有DSL注册函数，不把函数名当字段重写。

        参数: Call节点。返回: 原节点和改写后的参数。异常: ImportProblem为任意调用。
        """
        if not isinstance(node.func, ast.Name) or node.func.id not in ('abs', 'isclose'):
            _ini_problem(self.fields, self.section, self.key, 'unsafe_expression', '禁止任意调用或属性调用')
        node.args = [self.visit(item) for item in node.args]
        node.keywords = [self.visit(item) for item in node.keywords]
        return node


def _expression(text, aliases, fields, section, key):
    """解析白名单AST并替换Name，最终类型/单位仍交公开计划检查。

    参数: 原表达式、显式aliases和原位置。返回: 新DSL文本。
    异常: ImportProblem为危险语法、旧slope或缺映射；取消和资源错误不吞。
    """
    if text.lstrip().startswith(('_slope_', '_slope2_')):
        _ini_problem(fields, section, key, 'unsupported_slope', 'M2不支持slope/slope2配置')
    try:
        tree = ast.parse(text, mode='eval')
    except SyntaxError as error:
        _ini_problem(fields, section, key, 'invalid_expression', str(error))
    allowed = (ast.Expression, ast.Constant, ast.Name, ast.Load, ast.BinOp, ast.UnaryOp,
               ast.BoolOp, ast.Compare, ast.Call, ast.keyword, ast.Add, ast.Sub, ast.Mult,
               ast.Div, ast.UAdd, ast.USub, ast.Not, ast.And, ast.Or, ast.Eq, ast.NotEq,
               ast.Lt, ast.LtE, ast.Gt, ast.GtE)
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            _ini_problem(fields, section, key, 'unsafe_expression', '不支持AST节点：' + type(node).__name__)
    # 转换只作用本次新AST；字符串和包含另一名称的标识符不会误替换。
    tree = _AliasTransformer(aliases, fields, section, key).visit(tree)
    return ast.unparse(ast.fix_missing_locations(tree))


def convert_sclicer(parser, headers, mapping, analysis, fields, issues, mode):
    """整份转换显式选择的Sclicer模式，遇一项不支持便拒绝整个计划。

    参数: 已解析INI/头部定位、mapping、新analysis、局部报告列表和公开mode。
    返回: None；新rules/windows按原段序填充。异常: ImportProblem为语义问题。
    """
    triggers = [name for name in parser.sections() if name.startswith('TRIGGER_')]
    for section in parser.sections():
        if section not in ('INPUT', 'OUTPUT') and section not in triggers:
            problem('unsupported_section', 'ini', '[' + section + ']', '未知或未支持的INI段', headers[section], 1)
    if not triggers:
        problem('missing_trigger', 'ini', '$', '至少需要一个TRIGGER_段')
    if set(mapping['sections']) != set(triggers):
        problem('section_mapping_mismatch', 'mapping', '$.sections', 'sections必须恰好映射全部原TRIGGER_段')
    # I/O必须显式来自mapping；保原字段并报告ASC显示项与新输出的差异。
    catalog = {'INPUT': ('msg_path', 'dbc_path'),
               'OUTPUT': ('slice', 'log', 'format', 'merge', 'utc', 'msg_path')}
    for section, keys in catalog.items():
        if not parser.has_section(section):
            continue
        for key in parser.options(section):
            if key not in keys:
                _ini_problem(fields, section, key, 'unknown_option', '未知I/O字段')
            mark(fields, section, key, '$.analysis.sources' if section == 'INPUT' else '$.analysis.outputs',
                 'replaced', '旧I/O由explicit_mapping完整替代；原字段仅保审计，不执行旧输出')
    if parser.has_section('OUTPUT'):
        if not _boolean(parser, fields, 'OUTPUT', 'slice', True):
            _ini_problem(fields, 'OUTPUT', 'slice', 'unsupported_slice_disabled', 'slice=false不能转换为分析窗口成功')
        if _boolean(parser, fields, 'OUTPUT', 'merge', False):
            _ini_problem(fields, 'OUTPUT', 'merge', 'unsupported_merge', '旧merge=true未支持')
        _boolean(parser, fields, 'OUTPUT', 'log', True)
        if parser.get('OUTPUT', 'format', fallback='asc').lower() not in ('asc', 'blf'):
            _ini_problem(fields, 'OUTPUT', 'format', 'unsupported_output_format', '未知旧原始输出格式')
        try:
            parser.getint('OUTPUT', 'utc', fallback=0)
        except ValueError as error:
            _ini_problem(fields, 'OUTPUT', 'utc', 'invalid_utc', str(error))
    issues.append(LegacyImportIssue('explicit_io_mapping', 'mapping', '$.analysis',
        '来源与输出完全采用显式mapping；OUTPUT.utc仅是旧ASC显示参数，不转换来源时钟', level='warning'))
    issues.append(LegacyImportIssue('unknown_ttl_difference', 'plan', '$.signals',
        '新分析使用显式有限valid_for及UNKNOWN；旧逐帧缺值/缓存行为不据此宣称等价', level='warning'))
    issues.append(LegacyImportIssue('comparison_rounding_difference', 'plan', '$.rules',
        '旧eval_expr先对float值round(v,10)再比较；新条件使用原值和typed数值政策，不隐式复现该舍入', level='warning'))
    issues.append(LegacyImportIssue('raw_trigger_duplicate_difference', 'plan', '$.outputs',
        'LC02旧触发帧可能先随pre缓冲写出后再次写入；本导入不修改旧writer，不宣称原始输出帧唯一性等价或该缺陷已修复',
        level='warning'))
    slope_mode = mode == 'sclicer_slope'
    start_end_mode = mode == 'sclicer_start_end'
    expected_mode = 'single' if slope_mode else mode.removeprefix('sclicer_')
    analysis['rules'], analysis['windows'] = [], []
    for section in triggers:
        old_mode = parser.get(section, 'mode', fallback=None)
        if old_mode is None:
            _ini_problem(fields, section, 'mode', 'missing_option', '缺少原mode字段', headers=headers)
        if old_mode != expected_mode:
            _ini_problem(fields, section, 'mode', 'unsupported_mode', '原模式必须全部为' + expected_mode + '；不跳过其他模式或混合段')
        keys = ('mode', 'pre_sec', 'post_sec', 'expr') if old_mode == 'single' else (
                'mode', 'pre_sec', 'post_sec', 'start_expr', 'duration_sec')
        if start_end_mode:
            keys += ('end_expr',)
        for key in parser.options(section):
            if key not in keys:
                _ini_problem(fields, section, key, 'unknown_option', '此模式不支持该字段')
        selected = mapping['sections'][section]
        if not slope_mode and not start_end_mode and (type(selected) is not dict or set(selected) != {'name', 'window'}):
            problem('invalid_section_mapping', 'mapping', '$.sections.' + section, '段映射必须恰含name/window')
        if slope_mode:
            # 专用解析器先核段映射，之后才能安全取id；普通single仍明确拒绝旧slope串。
            if not parser.has_option(section, 'expr'):
                _ini_problem(fields, section, 'expr', 'missing_option', '缺少原slope表达式', headers=headers)
            slope = slope_rule(parser.get(section, 'expr', raw=True, fallback=''),
                               mapping['aliases'], selected, fields, section, issues)
        if start_end_mode:
            options = start_end_options(parser, fields, section, selected, issues)
        rule_id, window_id = selected['name'], selected['window']
        pre = _seconds(parser, fields, section, 'pre_sec', '5')
        post = _seconds(parser, fields, section, 'post_sec', '3')
        missing_defaults = [key for key in ('pre_sec', 'post_sec') if not parser.has_option(section, key)]
        if old_mode in ('start_only', 'start_end') and not parser.has_option(section, 'duration_sec'):
            missing_defaults.append('duration_sec')
        if missing_defaults:
            issues.append(LegacyImportIssue('old_defaults_applied', 'ini', '[' + section + ']',
                '沿已审旧默认：' + ', '.join(missing_defaults) + '；pre=5s/post=3s/start_only duration=10s/start_end duration=-1（不限时）',
                headers[section], 1, 'warning'))
        key = 'expr' if old_mode == 'single' else 'start_expr'
        if not parser.has_option(section, key):
            _ini_problem(fields, section, key, 'missing_option', '缺少原条件表达式', headers=headers)
        condition = None if slope_mode else _expression(
            parser.get(section, key, raw=True), mapping['aliases'], fields, section, key)
        index = len(analysis['rules'])
        rule_path, window_path = f'$.rules[{index}]', f'$.windows[{index}]'
        if slope_mode:
            rule = slope
            window = {'name': window_id, 'rule': rule_id, 'anchor': 'point', 'pre': pre,
                      'post': post, 'merge': 'none'}
        elif start_end_mode:
            if not parser.has_option(section, 'end_expr'):
                _ini_problem(fields, section, 'end_expr', 'missing_option', '缺少原结束条件', headers=headers)
            end_condition = _expression(parser.get(section, 'end_expr', raw=True), mapping['aliases'], fields, section, 'end_expr')
            rule = dict(name=rule_id, rule_type='start_end', start_condition=condition, end_condition=end_condition, **options)
            window = dict(name=window_id, rule=rule_id, anchor='activity', pre=pre, post='0s', merge='none')
            mark(fields, section, 'end_expr', rule_path + '.end_condition')
            mark(fields, section, 'duration_sec', rule_path + '.timeout')
        elif old_mode == 'single':
            rule = {'name': rule_id, 'rule_type': 'condition_duration', 'condition': condition, 'minimum_duration': '0s', 'selection_origin': 'onset'}
            window = {'name': window_id, 'rule': rule_id, 'anchor': 'activity', 'pre': pre,
                      'post': '0s', 'merge': 'exit_delay', 'exit_delay': post}
            issues.append(LegacyImportIssue('single_deadline_difference', 'ini', '[' + section + ']',
                '活动立即按FALSE/UNKNOWN结束；片段使用精确exit_delay，区别于旧等待下一帧且严格超过post关闭',
                headers[section], 1, 'warning'))
        else:
            duration = _seconds(parser, fields, section, 'duration_sec', '10', positive=True)
            rule = {'name': rule_id, 'rule_type': 'start_only', 'condition': condition,
                    'window_duration': duration, 'emit_initial': True}
            window = {'name': window_id, 'rule': rule_id, 'anchor': 'point', 'pre': pre,
                      'post': duration, 'merge': 'none'}
            mark(fields, section, 'duration_sec', rule_path + '.window_duration')
            issues.append(LegacyImportIssue('start_only_edge_difference', 'ini', '[' + section + ']',
                '采用真实边沿和固定抑制窗；emit_initial=true，旧post不叠加，不声称修复旧last_ts缺陷或重现逐帧锁存',
                headers[section], 1, 'warning'))
        analysis['rules'].append(rule)
        analysis['windows'].append(window)
        mark(fields, section, 'mode', rule_path + '.rule_type')
        mark(fields, section, key, rule_path if slope_mode else rule_path + ('.start_condition' if start_end_mode else '.condition'))
        mark(fields, section, 'pre_sec', window_path + '.pre')
        if slope_mode:
            mark(fields, section, 'post_sec', window_path + '.post', message='触发点后的固定长度，不模拟旧退出计时')
            continue
        if start_end_mode:
            mark(fields, section, 'post_sec', None, 'replaced', '旧start_end未使用post，不延长新活动或片段')
            continue
        mark(fields, section, 'post_sec', window_path + '.exit_delay' if old_mode == 'single' else None,
             'mapped' if old_mode == 'single' else 'replaced',
             'single退出延迟，不再叠加post' if old_mode == 'single' else 'start_only使用duration_sec，原post不叠加')
