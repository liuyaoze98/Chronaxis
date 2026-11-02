"""仅在信号省略类型/单位或enum映射时读取DBC元数据，不读取报文。

每次计划编译按DBC路径共用一次加载；结果冻结为已有SignalDefinition字段。
数值信号不会因存在VAL表而变成文字枚举。重新加载配置才重新推导默认值。
"""
from .checks import PlanValidationError
from ..legacy.binding import dbc_candidates
from ..can_dependencies import CANDependencyError, import_can_dependency


def _numeric_dtype(signal):
    """按解码后的数值范围选类型；有浮点缩放就使用float64，不丢弃小数。"""
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
    """把DBC原码表转换到既有解码值域，不对实际记录再施加一次DBC缩放。"""
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
        """创建空缓存，不访问磁盘。"""
        self.databases = {}

    def fill(self, raw, config, field, path):
        """参数为信号配置、CAN来源和定位；返回补默认值的独立dict，错误定位到信号。"""
        result = dict(raw)
        # 手工映射已明确标签类型，可以直接得出逻辑dtype，不读取DBC作第二次猜测。
        choices = result.get('choices')
        if 'dtype' not in result and type(choices) is list and choices:
            if all(type(pair) is list and len(pair)==2 and type(pair[1]) is str for pair in choices):
                result['dtype']='enum'
            elif all(type(pair) is list and len(pair)==2 and type(pair[1]) is bool for pair in choices):
                result['dtype']='bool'
        needed = [key for key in ('dtype','unit') if key not in result]
        if result.get('dtype') == 'enum' and 'choices' not in result:
            needed.append('choices')
        if not needed:
            return result
        try:
            key = str(config.dbc_path)
            if key not in self.databases:
                cantools = import_can_dependency('cantools')
                self.databases[key] = cantools.database.load_file(key)
            candidates = dbc_candidates(self.databases[key],field.frame_id,(field.signal,),field.is_extended,field.is_fd)
            signals = [next(s for s in message.signals if s.name==field.signal) for message in candidates]
            for name in needed:
                if name == 'dtype':
                    values = [_numeric_dtype(signal) for signal in signals]
                elif name == 'unit':
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
