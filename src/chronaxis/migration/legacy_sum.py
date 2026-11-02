"""静态迁移ChrgInfo当前消息公式，保原参数顺序、缺值门控和分桶定位。

输入为已按旧大小写/分号口径解析的INI及显式mapping；输出仅追加独立分析
字典的message_calculations与有限报告。period/factor沿旧float文本解析；只有global
在float文本失败后通过受限AST原序计算。公式只替换Name；
不执行eval、旧ConfigManager、DBC、reader或数据扫描。旧完整触发/缓存不支持。
正负分桶复用已接入raw_decoded-v1，不改贡献符号、周期、单位或普通数值核。
"""

import ast
from dataclasses import replace
from math import isfinite

from ..core.message_binding import ExpressionParameter
from ..legacy.records import PROFILE_ID, field_from_dict
from .ini import field_path, locate, mark, problem
from .models import LegacyImportIssue


def _reject(fields, headers, section, key, code, message):
    """拒绝原字段并保真实位置；参数: 定位/原因；返回: 无；异常: ImportProblem。"""
    line, column = locate(fields, section, key)
    if line is None:
        line, column = headers[section], 1
    problem(code, 'ini', field_path(section, key), message, line, column)


def _targets(fields, section, key, targets, message='保原字段并显式映射'):
    """为一原字段保每个真实目标，不把多路径拼成无法解析的字符串。

    参数: fields局部报告列表、原位置、targets目标tuple和说明。返回: None。
    异常: 无；原字段缺失由必填校验处理。相同global可映射多个section参数。
    """
    matches = [(index, item) for index, item in enumerate(fields) if item.path == field_path(section, key)]
    if not matches:
        return
    index, original = matches[0]
    existing = {item.target for _, item in matches if item.target is not None}
    for target in targets:
        if target in existing:
            continue
        mapped = replace(original, target=target, status='mapped', message=message)
        if fields[index].status == 'pending':
            fields[index] = mapped
        else:
            fields.append(mapped)
        existing.add(target)


def _constant(text, fields, headers, section, key, *, float_only=False):
    """保旧float优先口径，只有global允许有界纯数字AST回退。

    参数: 原文本及INI位置；float_only限定旧period/factor。返回: 原生int/float；
    不重排结合顺序或先舍入，坏factor不静默沿旧fallback=1.0。
    异常: ImportProblem为非法、过大、非有限或除零；资源/取消原错传播。
    """
    code = 'invalid_factor' if float_only and key.startswith('factor') else 'invalid_constant'
    try:
        number = float(text)
    except (ValueError, OverflowError) as error:
        if float_only:
            explanation = ('旧factor只接受float文本，旧坏值fallback=1.0不能静默转成新计算值；'
                           if key.startswith('factor') else '旧period只接受float文本，不计算四则表达式；')
            _reject(fields, headers, section, key, code, explanation + str(error))
    else:
        if not isfinite(number):
            _reject(fields, headers, section, key, code, '参数必须是有限FLOAT64')
        return number
    # 只有旧global曾在float失败后eval；这里仅实现无名称/调用的安全数字子集。
    try:
        tree = ast.parse(text, mode='eval')
    except (SyntaxError, ValueError, RecursionError) as error:
        _reject(fields, headers, section, key, 'invalid_constant', str(error))
    # 限定配置运算规模，不为禁止的指数/位移或巨型中间整数分配无界空间。
    if sum(1 for _ in ast.walk(tree)) > 1024:
        _reject(fields, headers, section, key, 'invalid_constant', '常量AST超过1024节点')

    def evaluate(node, depth=0):
        """按原树逐节点算数；参数: 节点和深度；返回: 数值；异常: ValueError/算术错误。"""
        if depth > 32:
            raise ValueError('常量AST超过32层')
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            value = node.value
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = evaluate(node.operand, depth + 1)
            value = value if isinstance(node.op, ast.UAdd) else -value
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            left, right = evaluate(node.left, depth + 1), evaluate(node.right, depth + 1)
            if isinstance(node.op, ast.Add):
                value = left + right
            elif isinstance(node.op, ast.Sub):
                value = left - right
            elif isinstance(node.op, ast.Mult):
                if type(left) is int and type(right) is int and left.bit_length() + right.bit_length() > 4096:
                    raise ValueError('常量中间整数超过4096位')
                value = left * right
            else:
                value = left / right
        else:
            raise ValueError('常量仅允许有限数字、括号、正负及加减乘除')
        if type(value) is int and value.bit_length() > 4096 or type(value) is float and not isfinite(value):
            raise ValueError('常量中间值非有限或整数过大')
        return value

    try:
        value = evaluate(tree.body)
        number = float(value)
        if not isfinite(number) or type(value) is int and int(number) != value:
            raise ValueError('参数必须能精确表示为有限FLOAT64')
        return value
    except (ValueError, OverflowError, ZeroDivisionError) as error:
        _reject(fields, headers, section, key, 'invalid_constant', str(error))


def _formula(text, signals, parameters, aliases, fields, headers, section):
    """保数值公式顺序并精确替换signal Name，参数不改名。

    参数: 原文本、原signal/参数名称集合、显式alias和原位置。返回: 新DSL文本。
    异常: ImportProblem为危险AST、未知名、缺alias或未使用signal门控。
    """
    try:
        tree = ast.parse(text, mode='eval')
    except (SyntaxError, ValueError, RecursionError) as error:
        _reject(fields, headers, section, 'expr', 'invalid_expression', str(error))
    allowed = (ast.Expression, ast.Name, ast.Load, ast.Constant, ast.BinOp, ast.UnaryOp,
               ast.Add, ast.Sub, ast.Mult, ast.Div, ast.UAdd, ast.USub)
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, allowed) or isinstance(node, ast.Constant) and type(node.value) not in (int, float):
            _reject(fields, headers, section, 'expr', 'unsafe_expression', 'legacy_sum仅支持纯数值公式，不支持调用/属性/条件语法')
        if isinstance(node, ast.Name):
            names.add(node.id)
            if node.id not in signals and node.id not in parameters:
                _reject(fields, headers, section, 'expr', 'unknown_expression_name', '未声明原变量：' + node.id)
    unused = set(signals) - names
    if unused:
        _reject(fields, headers, section, 'expr', 'unused_signal_gate',
                '旧配置即使expr未使用也要求字段存在，不能丢弃缺值门控：' + ', '.join(sorted(unused)))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in signals:
            if node.id not in aliases:
                _reject(fields, headers, section, node.id, 'missing_alias', '缺少原signal变量的显式alias')
            node.id = aliases[node.id]
    return ast.unparse(ast.fix_missing_locations(tree))


def _io_fields(parser, fields, headers, issues):
    """保旧I/O及完整替代政策；参数: 原解析和报告；返回: None；异常: ImportProblem。"""
    for section, allowed in (('input', ('ini_path', 'dbc_path', 'msg_path')),
                             ('output', ('log_path', 'result_path', 'log_level'))):
        if parser.has_section(section):
            for key in parser.options(section):
                if key not in allowed:
                    _reject(fields, headers, section, key, 'unknown_option', '未知旧I/O配置项')
                mark(fields, section, key, '$.analysis.sources' if section == 'input' else '$.analysis.outputs',
                     'replaced', '旧I/O由explicit_mapping替代，保原值但不创建旧日志/结果目录')
    issues.append(LegacyImportIssue('explicit_io_mapping', 'mapping', '$.analysis',
        '报文格式、显式文件顺序、DBC、时钟、请求和输出全部来自mapping；不继承旧CWD、目录批处理或旧日志副作用', level='warning'))
    issues.append(LegacyImportIssue('current_message_difference', 'plan', '$.message_calculations',
        '使用current_message-v1本条字段，不复用旧触发/cache；每次AnalysisRunner会话独立累计，同刻消息分别计数', level='warning'))
    issues.append(LegacyImportIssue('empty_sum_difference', 'plan', '$.message_calculations',
        '无匹配/全跳过保None及原因，有贡献零和为0.0；区别于旧累加器初始0，贡献不舍入且仅最终round6', level='warning'))


def convert_legacy_sum(parser, headers, mapping, analysis, fields, issues):
    """整份生成普通或正负legacy指标，保字段、参数及输出标签的逐项关系。

    参数: 旧口径parser/headers、六键mapping、独立analysis和局部报告列表。
    返回: None；只填新message_calculations。异常: ImportProblem为原配置/映射拒绝；
    不把解析成功或声明SHA当作实际CAN输入/DBC已验证，不修改数值核。
    """
    sections = [name for name in parser.sections() if name.startswith('integral_')]
    # 先定位具体未支持段，再检查mapping集合，不能用笼统缺mapping掩盖旧trigger。
    for section in parser.sections():
        if section not in ('input', 'output', 'global') and section not in sections:
            problem('unsupported_section', 'ini', '[' + section + ']',
                    '不支持旧完整trigger/cache、Sclicer或其它段', headers[section], 1)
    if not sections:
        problem('missing_integral', 'ini', '$', '至少需要一个integral_段')
    if set(mapping['sections']) != set(sections):
        problem('section_mapping_mismatch', 'mapping', '$.sections', 'sections必须恰好映射全部原integral_段')
    _io_fields(parser, fields, headers, issues)
    globals_ = {}
    if parser.has_section('global'):
        for key, text in parser.items('global', raw=True):
            globals_[key] = _constant(text, fields, headers, 'global', key)
    analysis['message_calculations'] = []
    for section in sections:
        signals, factors = {}, {}
        for key, text in parser.items(section, raw=True):
            if key.startswith('signal_'):
                if not text.strip():
                    _reject(fields, headers, section, key, 'missing_signal_field', '原signal字段名不能为空')
                signals[key] = text.strip()
            elif key.startswith('factor'):
                factors[key] = _constant(text, fields, headers, section, key, float_only=True)
            elif key not in ('period', 'expr', 'disjunction'):
                _reject(fields, headers, section, key, 'unknown_option', '未知或未支持的旧积分配置项')
        for key in ('period', 'expr'):
            if not parser.has_option(section, key):
                _reject(fields, headers, section, key, 'missing_option', '缺少必填原字段：' + key)
        if not signals:
            _reject(fields, headers, section, 'expr', 'missing_signal_mapping', '旧积分至少要求一个signal_*')
        # 保旧四层优先关系的审计，但新模式不模拟覆盖，任何冲突均明确拒绝。
        groups = ({'period': _constant(parser.get(section, 'period', raw=True), fields, headers, section, 'period', float_only=True)},
                  signals, factors, globals_)
        occupied = set()
        for group in groups:
            overlap = occupied.intersection(group)
            if overlap:
                _reject(fields, headers, section, 'expr', 'variable_override', '旧period→signals→factors→global发生覆盖：' + ', '.join(sorted(overlap)))
            occupied.update(group)
        parameters = {**groups[0], **factors, **globals_}
        selected = mapping['sections'][section]
        required = {'name', 'source', 'unit', 'message_policy', 'update_message', 'parameter_units'}
        if type(selected) is not dict or set(selected) != required:
            problem('invalid_section_mapping', 'mapping', '$.sections.' + section, '积分映射必须精确包含六个合同字段')
        if selected['message_policy'] != 'current_message-v1':
            problem('invalid_message_policy', 'mapping', '$.sections.' + section + '.message_policy', '必须显式选择current_message-v1')
        units = selected['parameter_units']
        if type(units) is not dict or set(units) != set(parameters):
            missing = sorted(set(parameters) - set(units)) if type(units) is dict else sorted(parameters)
            extra = sorted(set(units) - set(parameters)) if type(units) is dict else []
            problem('parameter_units_mismatch', 'mapping', '$.sections.' + section + '.parameter_units',
                    'parameter_units须恰好覆盖全部period/factor/global名称；缺少' + repr(missing) + '；多余' + repr(extra))
        typed_parameters = {}
        for name, value in parameters.items():
            try:
                parameter = ExpressionParameter(name, value, units[name])
            except (TypeError, ValueError) as error:
                problem('invalid_parameter', 'mapping', '$.sections.' + section + '.parameter_units.' + name, str(error))
            typed_parameters[name] = {'value': parameter.value, 'unit': parameter.unit}
        expression = _formula(parser.get(section, 'expr', raw=True), signals, parameters,
                              mapping['aliases'], fields, headers, section)
        source = next((item for item in analysis['sources'] if item.get('name') == selected['source']), None)
        # 新版本可显式把同一公式映射到文本原始报文，profile如实标识实际读取路径。
        text_source = (source is not None
                       and source.get('source_type') in ('can_asc', 'asc_or_blf', 'raw_can_csv'))
        if not text_source and (source is None or source.get('source_type') != 'can_blf'
                                or source.get('legacy_profile', PROFILE_ID) != PROFILE_ID):
            problem('invalid_legacy_source', 'mapping', '$.sections.' + section + '.source',
                    '需要BLF/sclicer-functions-v1，或schema2明确声明的ASC/原始报文CSV来源')
        profile = 'can-text-v1' if text_source else source.get('legacy_profile', PROFILE_ID)
        for key, original_signal in signals.items():
            definitions = [item for item in analysis['signals'] if item.get('name') == mapping['aliases'][key]]
            if len(definitions) != 1:
                _reject(fields, headers, section, key, 'invalid_signal_field', 'signal_*必须唯一映射至完整CAN信号声明')
            definition = definitions[0]
            try:
                field = field_from_dict(definition.get('field'))
            except (TypeError, ValueError) as error:
                _reject(fields, headers, section, key, 'invalid_signal_field', str(error))
            # alias只替换表达式变量名，不能借同消息同单位偷偷接到另一个原字段。
            if definition.get('source') != selected['source'] or field.signal != original_signal:
                _reject(fields, headers, section, key, 'signal_field_mismatch',
                        '目标必须属于本来源且完整CAN定位.signal等于原signal_*文本：' + original_signal)
        direction = parser.get(section, 'disjunction', fallback=None, raw=True)
        direction_alias = None
        if direction:
            direction_alias = mapping['aliases'].get(direction)
            definitions = [item for item in analysis['signals'] if item.get('name') == direction_alias]
            if direction_alias is None or len(definitions) != 1:
                _reject(fields, headers, section, 'disjunction', 'missing_direction_alias', '方向原字段必须显式且唯一映射至信号别名')
            definition = definitions[0]
            try:
                field = field_from_dict(definition.get('field'))
            except (TypeError, ValueError) as error:
                _reject(fields, headers, section, 'disjunction', 'invalid_direction_field', str(error))
            if definition.get('source') != selected['source'] or field.signal != direction:
                _reject(fields, headers, section, 'disjunction', 'direction_field_mismatch', '方向必须属于本来源且完整CAN定位.signal等于原disjunction文本')
        start = len(analysis['message_calculations'])
        buckets = ('positive', 'negative') if direction else (None,)
        base_id = selected['name']
        if type(base_id) is not str:
            problem('invalid_calculation_id', 'mapping', '$.sections.' + section + '.name', 'id必须是原生文本')
        for bucket in buckets:
            calculation = {'name': base_id if bucket is None else base_id + '_' + bucket,
                'source': selected['source'], 'profile': profile, 'operation': 'legacy_sum',
                'update_message': selected['update_message'], 'expr': expression, 'unit': selected['unit'],
                'parameters': typed_parameters, 'message_policy': selected['message_policy']}
            if bucket is not None:
                calculation['split_by_sign'] = {'signal': direction_alias, 'bucket': bucket, 'value_policy': 'raw_decoded-v1'}
            analysis['message_calculations'].append(calculation)
        indexes = tuple(range(start, len(analysis['message_calculations'])))
        _targets(fields, section, 'expr', tuple(f'$.message_calculations[{index}].expr' for index in indexes))
        for key in signals:
            signal_index = next(index for index, item in enumerate(analysis['signals'])
                                if item.get('name') == mapping['aliases'][key])
            _targets(fields, section, key, (f'$.signals[{signal_index}].field',))
        for name in parameters:
            origin = 'global' if name in globals_ else section
            _targets(fields, origin, name, tuple(f'$.message_calculations[{index}].parameters.{name}.value' for index in indexes))
        if direction:
            _targets(fields, section, 'disjunction', tuple(f'$.message_calculations[{index}].split_by_sign.signal' for index in indexes))
            old_base = section.replace('integral_', '')
            for index, suffix in zip(indexes, ('+', '-')):
                issues.append(LegacyImportIssue('disjunction_output_mapping', 'ini', field_path(section, 'disjunction'),
                    old_base + suffix + ' → ' + analysis['message_calculations'][index]['name'],
                    *locate(fields, section, 'disjunction'), level='warning'))
            issues.append(LegacyImportIssue('disjunction_quality_difference', 'ini', field_path(section, 'disjunction'),
                '原值分桶不abs/不施scale或TTL；缺方向记MISSING_INPUT，NaN/±Inf记NONFINITE_INPUT；区别于旧缺失按0及±Inf入桶',
                *locate(fields, section, 'disjunction'), level='warning'))
        elif parser.has_option(section, 'disjunction'):
            mark(fields, section, 'disjunction', None, 'replaced', '原空disjunction不分桶')
