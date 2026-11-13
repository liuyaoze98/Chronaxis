"""为 DBC 缓存规则测试解析常见引用，不宣称证明任意动态 Python 程序安全。"""
import ast


_LOADERS = frozenset('cantools.database.' + name for name in ('load_file', 'load', 'load_string'))


def _qualified_name(node, aliases):
    """解析模块/函数引用。参数: AST 节点和别名表；返回: 名称或空串。异常: 无主动异常。"""
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        base = _qualified_name(node.value, aliases)
        if node.attr == 'cantools':
            return 'cantools'  # 旧处理器持有它实际导入的 cantools。
        return base + '.' + node.attr if base else ''
    if isinstance(node, ast.Call):
        name = _qualified_name(node.func, aliases)
        if name in ('getattr', 'builtins.getattr') and len(node.args) >= 2:
            member = node.args[1]
            if isinstance(member, ast.Constant) and isinstance(member.value, str):
                return _qualified_name(node.args[0], aliases) + '.' + member.value
        if name in ('import_can_dependency', 'importlib.import_module', '__import__') and node.args:
            module = node.args[0]
            if isinstance(module, ast.Constant) and module.value == 'cantools':
                return 'cantools'
    return ''


def cache_policy_errors(source, *, gateway=False):
    """收集绕过入口或改变加载参数的位置。参数: 源码及是否入口；返回: 错误列表。

    异常: 非法 Python 源码由 ast.parse 抛出；不把解析失败当作检查通过。
    """
    nodes = list(ast.walk(ast.parse(source)))
    aliases = {}
    for node in nodes:
        if isinstance(node, ast.Import):
            for item in node.names:
                aliases[item.asname or item.name.split('.')[0]] = item.name if item.asname else item.name.split('.')[0]
        elif isinstance(node, ast.ImportFrom):
            for item in node.names:
                aliases[item.asname or item.name] = (node.module or '') + '.' + item.name
    # 赋值别名可以跨多层；仅跟踪 CAN 加载引用，不推断整个程序的数据流。
    for _ in range(len(nodes)):
        previous = dict(aliases)
        for node in nodes:
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
                name = _qualified_name(node.value, aliases)
                if name == 'cantools' or name.startswith('cantools.'):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for target in targets:
                        if isinstance(target, ast.Name):
                            aliases[target.id] = name
        if aliases == previous:
            break
    calls = [node for node in nodes if isinstance(node, ast.Call)
             and _qualified_name(node.func, aliases) in _LOADERS]
    permitted = set()
    if gateway:
        for node in calls:
            options = {item.arg: item.value for item in node.keywords}
            expected = {'frame_id_mask': None, 'prune_choices': False, 'strict': True}
            if (_qualified_name(node.func, aliases) == 'cantools.database.load'
                    and len(node.args) == 1 and not isinstance(node.args[0], ast.Starred)
                    and len(node.keywords) == 4
                    and set(options) == {'database_format', *expected}
                    and isinstance(options['database_format'], ast.Name)
                    and options['database_format'].id == 'database_format'
                    and all(isinstance(options[key], ast.Constant)
                            and type(options[key].value) is type(value)
                            and options[key].value == value for key, value in expected.items())):
                permitted.add(id(node.func))
    errors = []
    for node in nodes:
        if _qualified_name(node, aliases) in _LOADERS and id(node) not in permitted:
            errors.append(f'{node.lineno}: DBC加载须经共用入口，入口只允许一次无缓存文本解析')
    if gateway and (len(calls) != 1 or len(permitted) != 1):
        errors.append('共用入口应只有一次保持格式及默认参数的load调用')
    return errors
