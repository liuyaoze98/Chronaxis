"""仅在信号省略类型/单位或enum映射时读取DBC元数据，不读取报文。

每次计划编译按DBC路径共用一次加载；结果冻结为已有SignalDefinition字段。
数值信号不会因存在VAL表而变成文字枚举。重新加载配置才重新推导默认值。
"""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from .checks import PlanValidationError
from ..legacy.binding import dbc_candidates
from ..can_dependencies import CANDependencyError, import_can_dependency
from ..dbc_loading import load_dbc_file


_PREPARED_DBC = ContextVar('chronaxis_prepared_dbc', default=None)


@contextmanager
def scoped_dbc_cache():
    """在一次 fast 准备期间共享 DBC，嵌套子计划沿用外层缓存，退出即释放。"""
    if _PREPARED_DBC.get() is not None:
        yield
        return
    token = _PREPARED_DBC.set({})
    try:
        yield
    finally:
        _PREPARED_DBC.reset(token)


def load_dbc(path):
    """返回当前准备范围的数据库；普通单任务保持原加载行为。"""
    cache = _PREPARED_DBC.get()
    cantools = import_can_dependency('cantools')
    if cache is None:
        return load_dbc_file(path, cantools)
    key = Path(path).resolve()
    if key not in cache:
        cache[key] = load_dbc_file(path, cantools)
    return cache[key]


def requested_enum_codes(config):
    """在加载 DBC 前定位 enum_code 使用的信号，只解析表达式位置和简单派生别名。

    参数: config 为已归组的分析配置，可能含尚待完整校验的节点。
    返回: 原码别名集合。异常: 完整语法诊断由稍后的统一编译器报告。
    """
    import ast
    derived = config.get('derived', {})
    pending = [config.get(group, ()) for group in ('derived', 'rules', 'calculations', 'message_calculations')]
    names = set()
    while pending:
        item = pending.pop()
        if isinstance(item, (tuple, list)):
            pending.extend(item)
        elif isinstance(item, dict):
            for key, value in item.items():
                if isinstance(value, (list, dict)) and key not in ('metadata', 'parameters'):
                    pending.append(value)
                elif isinstance(value, str) and 'enum_code' in value and key in (
                        'expr', 'signal', 'condition', 'end_condition', 'start_condition', 'exit_condition', 'enter_condition'):
                    try:
                        tree = ast.parse(value, mode='eval')
                    except (SyntaxError, ValueError):
                        continue
                    for node in ast.walk(tree):
                        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and
                                node.func.id == 'enum_code' and len(node.args) == 1 and isinstance(node.args[0], ast.Name)):
                            names.add(node.args[0].id)
    for name in tuple(names):
        seen = set()
        while isinstance(derived, dict) and isinstance(derived.get(name), dict) and name not in seen:
            seen.add(name)
            text = derived[name].get('expr')
            if not isinstance(text, str):
                break
            try:
                expression = ast.parse(text, mode='eval').body
            except (SyntaxError, ValueError):
                break
            if not isinstance(expression, ast.Name):
                break
            name = expression.id
            names.add(name)
    return names


def _numeric_dtype(signal):
    """按解码后的数值范围选类型；有浮点缩放就使用float64，不丢弃小数。

    参数: signal为DBC信号定义，包含原位宽、符号及解码倍率/偏移。
    返回: float64、int64或uint64文本。
    异常: ValueError为缩放后整数不能用64位类型表示。
    """
    if signal.is_float or type(signal.scale) is not int or type(signal.offset) is not int:
        return 'float64'
    low = -(2**(signal.length-1)) if signal.is_signed else 0
    high = 2**(signal.length-1)-1 if signal.is_signed else 2**signal.length-1
    limits = sorted((low*signal.scale+signal.offset, high*signal.scale+signal.offset))
    if -(2**63) <= limits[0] and limits[1] < 2**63:
        return 'int64'
    if 0 <= limits[0] and limits[1] < 2**64:
        return 'uint64'
    raise ValueError('DBC缩放后的整数超出64位，请显式选择dtype并核对数值范围')


def _enum_choices(signal):
    """把DBC原码表转换到既有解码值域，不对实际记录再施加一次DBC缩放。

    参数: signal为含choices的DBC信号定义。
    返回: [已解码整数码, 标签]列表。
    异常: ValueError为缺少枚举、解码码值含小数或标签为空。
    """
    if not signal.choices:
        raise ValueError('DBC没有该信号的枚举表，请提供choices或选择数值dtype')
    result = []
    for code, label in signal.choices.items():
        value = signal.conversion.raw_to_scaled(code, decode_choices=False)
        # 核心枚举编码保持int/bool/str契约；不把浮点物理值截断成整数码。
        if type(value) is not int or signal.is_float:
            raise ValueError('DBC枚举缩放产生浮点值，当前枚举编码不支持；请使用数值dtype，不会截断或重复缩放')
        text = str(label)
        if not text:
            raise ValueError('DBC枚举标签为空，请提供明确choices')
        result.append([value,text])
    return result


class DBCDefaults:
    """一次计划编译内的临时数据库缓存，显式完整声明不打开DBC。"""
    def __init__(self):
        """创建空缓存，不访问磁盘。

        参数: 无。返回: None。异常: 内存分配错误传播。
        """
        self.databases = {}
        self.failures = {}

    def fill(self, raw, config, field, path, *, config_version=4, need_code=False):
        """补全DBC可证明的声明，不重复应用原解码缩放。

        参数: raw为配置；config/field为来源与定位；path为诊断位置；config_version选择规则。
        返回: 独立dict，v4保留DBC原单位作为input_unit。
        异常: PlanValidationError为缺项、歧义、读取或依赖错误。
        """
        from ..core.unit_conversion import require_config_version
        require_config_version(config_version)
        result = dict(raw)
        # 手工映射已明确标签类型，可以直接得出逻辑dtype，不读取DBC作第二次猜测。
        choices = result.get('choices')
        if 'dtype' not in result and type(choices) is list and choices:
            if all(type(pair) is list and len(pair)==2 and type(pair[1]) is str for pair in choices):
                result['dtype']='enum'
            elif all(type(pair) is list and len(pair)==2 and type(pair[1]) is bool for pair in choices):
                result['dtype']='bool'
        needed = [key for key in ('dtype','unit') if key not in result]
        # 目标单位显式填写仍不代表DBC原值已经处于该尺度。
        if 'input_unit' not in result:
            needed.append('input_unit')
        if result.get('dtype') == 'enum' and 'choices' not in result:
            needed.append('choices')
        if need_code:
            needed.append('code_dtype')
        if not needed:
            return result
        key = str(config.dbc_path)
        if key in self.failures:
            raise PlanValidationError(path, 'DBC加载已失败，先修复 ' + self.failures[key], 'blocked_dependency')
        try:
            if key not in self.databases:
                try:
                    self.databases[key] = load_dbc(key)
                except Exception:
                    # 同一次失败文件不因另一个信号再次加载；不缓存跨任务的失败。
                    self.failures[key] = path
                    raise
            candidates = dbc_candidates(self.databases[key],field.frame_id,(field.signal,),field.is_extended,field.is_fd)
            signals = [next(s for s in message.signals if s.name==field.signal) for message in candidates]
            for name in needed:
                if name == 'dtype':
                    values = [_numeric_dtype(signal) for signal in signals]
                elif name == 'code_dtype':
                    if any(signal.is_float or signal.scale != 1 or signal.offset != 0 for signal in signals):
                        raise ValueError('enum_code 需要原整数；该 DBC 已缩放或提供浮点解码值')
                    values = ['int64' if signal.is_signed else 'uint64' for signal in signals]
                    if 'code_dtype' in raw and any(value != raw['code_dtype'] for value in values):
                        raise ValueError('code_dtype 与 DBC 原始整数有符号性不符')
                elif name in ('unit', 'input_unit'):
                    # 无单位定义时标未知，不冒称已核实为V/A或无量纲。
                    values = [signal.unit or ('1' if result.get('dtype') in ('enum','bool') else 'unknown') for signal in signals]
                else:
                    values = [_enum_choices(signal) for signal in signals]
                if any(value != values[0] for value in values[1:]):
                    raise ValueError(f'候选DBC的{name}不同，请补充帧类型或显式{name}')
                result[name] = values[0]
        except CANDependencyError as error:
            # 这是来源的安装环境缺项，不要求用户反复修改当前信号字段。
            raise PlanValidationError('$.sources', str(error), error.code,
                hint=error.hint, object_name='来源 ' + config.name) from error
        except Exception as error:
            # 不吞文件/解析错误，不用猜测值替代无法读取的元数据。
            raise PlanValidationError(path,'无法从DBC补充信号声明：'+str(error)) from error
        return result
