"""一次收集独立配置错误，并阻断依赖坏声明的检查。

输入是已解析配置，输出为定位诊断或完整计划。Schema只负责结构与单字段约束；
语义仍由原解析器检查。只跳过无效声明，不改配置、不补假值，不创建可运行残缺计划。
上下文仅覆盖本次同步构建，退出后恢复；schema来自唯一维护的Docs/Schema，安装时随包提供。
"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache, wraps
from pathlib import Path
import json

from jsonschema import Draft202012Validator, validators
from ..configuration.models import field_path_text
from .checks import PlanValidationError


_ACTIVE = ContextVar('chronaxis_configuration_diagnostics', default=None)


@lru_cache(maxsize=4)
def schema_validator(name):
    """加载只读结构规范。参数: 固定规范名。返回: validator。异常: 安装缺资源或规范损坏。

    原生整数检查与typed API一致，不让bool或1.0冒充整数；不访问网络引用。
    """
    package = Path(__file__).resolve().parents[1]
    path = package / 'schemas' / name
    if not path.is_file():
        path = package.parents[1] / 'Docs' / 'Schema' / name
    schema = json.loads(path.read_text(encoding='utf-8-sig'))
    checker = Draft202012Validator.TYPE_CHECKER.redefine('integer',
        lambda checker, value: type(value) is int)
    return validators.extend(Draft202012Validator, type_checker=checker)(schema)


def _host_validator(validator, extensions):
    """在本次验证器中放行宿主已登记的操作名。参数: 原规范、注册。返回: 独立验证器。异常: 注册非法。

    只复制变化的字典路径；内置操作和无注册的 CLI 始终使用原规范，不改变共享缓存。
    """
    schema = validator.schema
    sections = dict(schema['properties'])
    for section, names in (('calculations', extensions.reductions), ('transforms', extensions.transforms)):
        if not names:
            continue
        array = sections[section]
        item = array['items']
        operations = item['properties']['operation']
        properties = dict(item['properties'], operation=dict(operations, enum=[*operations['enum'], *names]))
        sections[section] = dict(array, items=dict(item, properties=properties))
    return type(validator)(dict(schema, properties=sections))


def _specific_errors(error):
    """展开最适用联合分支，避免列出不相关格式的全部缺项。

    参数: jsonschema错误。返回: 叶错误迭代器。异常: 无。
    优先匹配已有字段的const/enum判别，再选择错误最少的分支；未知判别值保留父错误。
    """
    if error.validator not in ('oneOf', 'anyOf') or not error.context:
        yield error
        return
    groups = {}
    for child in error.context:
        groups.setdefault(child.schema_path[0], []).append(child)
    instance = error.instance
    candidates = []
    for index, children in groups.items():
        branch = error.validator_value[index]
        score = 0
        if 'type' in branch:
            # 先按输入真实类型选分支，不能把坏对象误诊为“应填写字符串”。
            types = branch['type'] if type(branch['type']) is list else [branch['type']]
            matching = any(Draft202012Validator.TYPE_CHECKER.is_type(instance, name) for name in types)
            score += 1000 if matching else -1000
        for key, rule in branch.get('properties', {}).items():
            if type(instance) is dict and key in instance:
                if 'const' in rule:
                    score += 10 if instance[key] == rule['const'] else -100
                elif 'enum' in rule:
                    score += 5 if instance[key] in rule['enum'] else -100
        candidates.append((score, -len(children), index, children))
    chosen = max(candidates, key=lambda item: item[:3])[-1]
    for child in chosen:
        yield from _specific_errors(child)


class DiagnosticCollection:
    """持有本次有限错误、阻断说明和无效对象；不保存输入或运行结果。"""

    def __init__(self, config, schema_name='analysis.schema.json', *, extensions=None):
        """检查所有独立结构字段。参数: 原配置和规范名。返回: 新集合。异常: 资源错误。"""
        self.errors = []
        self.blocked = []
        self.invalid_names = set()
        self.invalid_nodes = set()
        self.invalid_sources = set()
        self.checking_derived = False
        validator = schema_validator(schema_name)
        if extensions is not None:
            from ..extensions import ExtensionRegistry
            if type(extensions) is not ExtensionRegistry or type(config) is not dict or config.get('config_version') != 4:
                raise PlanValidationError('$.config_version','宿主扩展需要版本4和ExtensionRegistry')
            validator = _host_validator(validator, extensions)
        for error in validator.iter_errors(config):
            for issue in _specific_errors(error):
                path = tuple(issue.absolute_path)
                code = 'invalid_config'
                # 未专门处理的Schema约束也使用项目文案，不透传校验器内部英文。
                message = '值或字段组合不符合当前配置要求'
                hint = '按字段参考修正此值'
                if issue.validator == 'required':
                    missing = sorted(key for key in issue.validator_value if key not in issue.instance)
                    for key in missing:
                        self.add(PlanValidationError(field_path_text((*path, key)),
                            '缺少必填字段：' + key, 'invalid_config' if 'field' in path else 'missing_field', hint='在所属对象中补充 ' + key))
                    continue
                if issue.validator == 'additionalProperties' and type(issue.instance) is dict:
                    from difflib import get_close_matches
                    unknown = set(issue.instance) - set(issue.schema.get('properties', {}))
                    for key in sorted(unknown):
                        candidate = get_close_matches(key, list(issue.schema.get('properties', {})), n=1, cutoff=0.65)
                        if key in ('workers', 'max_workers') and 'process_count' in issue.schema.get('properties', {}):
                            candidate = ['process_count']
                        if key == 'cache_policy' and path and path[0] == 'message_calculations':
                            self.add(PlanValidationError(field_path_text((*path, key)),
                                '旧缓存策略尚未接线；当前仅支持current_message-v1', 'capability_unavailable'))
                        else:
                            known_in_other_mode = path and path[-1] == 'time' and key in ('clock', 'timezone')
                            self.add(PlanValidationError(field_path_text((*path, key)),
                                ('此时间模式不适用字段：' if known_in_other_mode else '未知字段：') + key,
                                'invalid_config' if 'field' in path or known_in_other_mode else 'unknown_field',
                                hint=('是否要写 ' + candidate[0] + '？' if candidate else '检查拼写或删除不适用字段')))
                    continue
                if issue.validator == 'type':
                    type_names = {'object': '对象', 'array': '列表', 'string': '字符串',
                                  'integer': '整数', 'number': '数值', 'boolean': '布尔值', 'null': '空值'}
                    expected = issue.validator_value if type(issue.validator_value) is list else [issue.validator_value]
                    code, message = 'invalid_type', '值类型应为' + '或'.join(type_names.get(value, '规定类型') for value in expected)
                    if path[-2:] == ('conversion', 'input_unit') and issue.instance is None:
                        message = 'input_unit不能填写null；需要自动确定输入单位时请省略此字段'
                        hint = '删除input_unit字段；如需手动指定，请填写非空单位字符串'
                elif issue.validator in ('enum', 'const'):
                    code = 'invalid_choice'
                    message = '值必须属于 ' + str(issue.validator_value)
                    values = issue.validator_value if issue.validator == 'enum' else [issue.validator_value]
                    if len(values) == 1 and path:
                        label = '.'.join(str(part) for part in path[-2:]) if path[-1] == 'mode' else str(path[-1])
                        message = label + '必须为' + str(values[0])
                    if path and path[-1] == 'source_type':
                        code = 'capability_unavailable'
                elif issue.validator in ('minimum', 'maximum', 'exclusiveMinimum', 'exclusiveMaximum'):
                    code = 'out_of_range'
                    relation = {'minimum': '大于或等于', 'maximum': '小于或等于',
                                'exclusiveMinimum': '大于', 'exclusiveMaximum': '小于'}[issue.validator]
                    message = '数值必须' + relation + str(issue.validator_value)
                elif issue.validator in ('minLength', 'maxLength', 'minItems', 'maxItems'):
                    subject = '文本长度' if issue.validator.endswith('Length') else '列表项数'
                    relation = '至少为' if issue.validator.startswith('min') else '最多为'
                    message = subject + relation + str(issue.validator_value)
                elif issue.validator == 'not':
                    forbidden = issue.validator_value.get('required', ()) if type(issue.validator_value) is dict else ()
                    if type(issue.instance) is dict and len(forbidden) == 1:
                        path = (*path, forbidden[0])
                        message = '当前操作或配置下不能填写字段：' + str(forbidden[0])
                    elif type(issue.instance) is dict and forbidden:
                        message = '不能同时填写字段：' + '、'.join(forbidden)
                    elif issue.validator_value == {} and path:
                        message = '当前操作或配置下不能填写字段：' + str(path[-1])
                    else:
                        message = '此值或字段组合不适用于当前配置'
                    hint = '删除不适用的字段，或按所选操作的字段说明调整配置'
                elif issue.validator == 'pattern':
                    message = '文本格式不符合字段要求：' + str(issue.validator_value)
                    if path and (path[-1].endswith('duration') or path[-1] in ('valid_for','period','pre','post','min_delay','max_delay')):
                        code = 'invalid_duration'
                if path and path[-1] == 'config_version':
                    code = 'invalid_choice'
                if path and path[-1] == 'anchor':
                    code = 'invalid_config'
                # 原定位模型使用统一invalid_config；保留机器码，位置细化到真实坏字段。
                if code not in ('unknown_field', 'missing_field') and (
                    'field' in path or 'update_message' in path or 'dbc_by_channel' in path or
                    (path and path[0] == 'message_calculations' and 'parameters' in path)):
                    code = 'invalid_config'
                if path and path[-1] == 'channel':
                    message = '通道必须为从1开始的原生整数'
                self.add(PlanValidationError(field_path_text(path), message, code, hint=hint))

    def add(self, error):
        """登记唯一错误。参数: PlanValidationError。返回: None。异常: 无。"""
        if not any(item.path == error.path and item.code == error.code for item in self.errors):
            self.errors.append(error)

    def usable(self, path):
        """判断对象是否有结构错误。参数: JSON路径。返回: bool。异常: 无。"""
        return not any(item.path == path or item.path.startswith(path + '.') or
                       item.path.startswith(path + '[') for item in self.errors)

    def block(self, path, reason):
        """记录依赖阻断，避免派生假错误。参数: 字段路径/原因。返回: None。异常: 无。"""
        record = dict(path=path, reason=reason)
        if record not in self.blocked:
            self.blocked.append(record)

    @contextmanager
    def stage(self, path, *, requires=True, check=True):
        """隔离一个有明确依赖的检查。参数: 路径/依赖是否有效。返回: 是否执行。异常: 非配置错误传播。"""
        if check and not self.usable(path):
            yield False
            return
        if not requires:
            self.block(path, '依赖的声明无效，修复上游后继续检查')
            yield False
            return
        try:
            yield True
        except PlanValidationError as error:
            if error.code == 'blocked_dependency':
                self.block(error.path, error.message)
            else:
                self.add(error)

    def finish(self):
        """有错则统一抛出，不返回残缺计划。参数: 无。返回: None。异常: PlanValidationError。"""
        if self.errors:
            # 拼写建议先于其缺项；操作名决定后续填写规则，先于其他独立字段错误。
            def priority(error):
                """参数: 单条诊断。返回: 根因优先级。异常: 无。"""
                if error.code == 'unknown_field':
                    return 0
                if error.path.endswith('.operation') and error.code in ('missing_field', 'invalid_choice', 'invalid_type'):
                    return 1
                return 3 if error.code == 'missing_field' else 2
            self.errors.sort(key=priority)
            raise PlanValidationError.from_diagnostics(self.errors, self.blocked)


def current_collection():
    """返回当前构建的集合。参数: 无。返回: 集合或None。异常: 无。"""
    return _ACTIVE.get()


@contextmanager
def collecting(collection):
    """临时接入本次构建。参数: 集合。返回: 无。异常: 原异常传播，始终恢复上下文。"""
    token = _ACTIVE.set(collection)
    try:
        yield
    finally:
        _ACTIVE.reset(token)


def usable_node(path, raw=None):
    """跳过坏节点且记录名称供依赖判断。参数: 路径/原声明。返回: bool。异常: 无。"""
    active = current_collection()
    if active is None:
        return True
    if active.usable(path):
        # 引用坏规则或窗口时，只说明未检查，不再伪报该名称不存在。
        if type(raw) is dict:
            for key in ('expr', 'condition'):
                try:
                    require_expression_dependencies(raw.get(key), path + '.' + key, ())
                except PlanValidationError as error:
                    active.block(error.path, error.message)
                    if type(raw.get('name')) is str:
                        active.invalid_nodes.add(raw['name'])
                    return False
            references = [raw.get(key) for key in ('rule', 'window', 'start', 'response')]
            scope = raw.get('scope')
            if type(scope) is str and ':' in scope:
                references.append(scope.split(':', 1)[1])
            if any(type(name) is str and name in active.invalid_nodes for name in references):
                active.block(path, '引用的规则或窗口无效')
            else:
                return True
        else:
            return True
    if path.startswith('$.sources['):
        import re
        index = re.match(r'\$\.sources\[(\d+)\]', path)
        name = raw.get('name') if type(raw) is dict else None
        active.invalid_sources.add(name if type(name) is str else 'source_' + str(int(index[1]) + 1))
    elif type(raw) is dict and type(raw.get('name')) is str:
        names = active.invalid_names if path.startswith(('$.signals[', '$.derived.')) else active.invalid_nodes
        names.add(raw['name'])
    return False


def collect_node_error(error, path, raw):
    """收集单节点失败；非汇总模式保持原抛出行为。参数: 异常/路径/声明。返回: None。异常: 原错误。"""
    active = current_collection()
    if active is None:
        raise error
    if error.code == 'blocked_dependency':
        active.block(error.path, error.message)
        if type(raw) is dict and type(raw.get('name')) is str:
            names = active.invalid_names if path.startswith(('$.signals[', '$.derived.')) else active.invalid_nodes
            names.add(raw['name'])
        return
    active.add(error)
    usable_node(path, raw)


def require_expression_dependencies(text, path, derived):
    """遇到已知坏信号只阻断当前表达式。参数: 文本/位置/派生定义。返回: None。异常: 依赖阻断。

    只读取AST名称，不执行表达式；真正的语法、dtype和单位仍由表达式编译器检查。
    """
    import ast
    active = current_collection()
    if active is None or not active.invalid_names or type(text) is not str:
        return
    definitions = {item.name: item.expr for item in derived}
    visited = set()
    pending = [text]
    while pending:
        value = pending.pop()
        try:
            names = {node.id for node in ast.walk(ast.parse(value, mode='eval')) if isinstance(node, ast.Name)}
        except SyntaxError:
            return
        bad = names & active.invalid_names
        if bad:
            raise PlanValidationError(path, '依赖的信号或派生项无效：' + ', '.join(sorted(bad)), 'blocked_dependency')
        for name in names - visited:
            visited.add(name)
            if name in definitions:
                pending.append(definitions[name])


def expression_scope(text, bindings, derived):
    """给单项静态诊断选择真实依赖，避免无关坏派生项遮蔽此项。

    参数: 表达式/声明绑定/全部派生。返回: 仅用于静态诊断的绑定和派生。异常: 原模型错误。
    全计划仍逐项检查所有派生；此处不创建运行计划或修改输入配置。
    """
    active = current_collection()
    if active is None or (not active.checking_derived and not active.errors):
        return bindings, derived
    import ast
    from dataclasses import replace
    definitions = {item.name: item for item in derived}
    selected = set()
    pending = [text]
    while pending:
        value = pending.pop()
        if type(value) is not str:
            continue
        try:
            names = {node.id for node in ast.walk(ast.parse(value, mode='eval')) if isinstance(node, ast.Name)}
        except SyntaxError:
            continue
        for name in names & definitions.keys() - selected:
            selected.add(name)
            pending.append(definitions[name].expr)
    required = tuple(item for item in derived if item.name in selected)
    return replace(bindings, derived_names=tuple(item.name for item in required)), required


def diagnose_plan(function):
    """为计划入口建立唯一诊断上下文。参数: 构建方法。返回: 包装方法。异常: 完整配置错误。

    合法输入只构建一次；错误输入从不返回局部计划，且始终恢复上层上下文。
    """
    @wraps(function)
    def checked(cls, config, *args, **kwargs):
        """调用一次构建。参数: 原配置及路径参数。返回: 完整计划。异常: 汇总配置错误。"""
        from .checks import require_json_value
        require_json_value(config, '$')
        collection = DiagnosticCollection(config, extensions=kwargs.get('extensions'))
        with collecting(collection):
            try:
                result = function(cls, config, *args, **kwargs)
            except PlanValidationError as error:
                if tuple(collection.errors) == error.diagnostics:
                    raise
                for item in error.diagnostics:
                    collection.add(item)
                collection.finish()
            collection.finish()
            return result
    return checked
