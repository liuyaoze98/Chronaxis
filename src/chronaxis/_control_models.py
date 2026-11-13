"""三条内部控制通道的固定模型转换；协议只允许这里显式列出的构造器。"""
from collections.abc import Mapping
from math import isfinite
from pathlib import Path

_SIGNAL = ('name source field dtype unit valid_for_ns input_unit scale offset choices valid_range '
           'invalid_values sample_policy same_time_policy semantic_id semantic_contract_version '
           'mapping_version sign_convention measurement_location input_sign_convention direction_factor '
           'config_version input_dtype code_dtype capture_code').split()
_ASC = 'path parser_version encoding time_reference timezone_offset_minutes offset_ns'.split()
_CSV_TIME = 'format unit offset_ns timezone_offset_minutes rollover_min_drop_ns'.split()
_COLUMN = 'column fixed value_map strip'.split()
_LAYOUT = 'fields encoding delimiter has_header skip_rows layout_version'.split()
_RULE = 'channel frame_id continuous is_extended is_fd protected same_time_policy'.split()
_RESULT = ('job_id status plan_path plan_identity dataset_id entity_id session_id input_identity run_id '
           'output_dir manifest_path error_type error_message error_chain elapsed_seconds memory_budget_bytes worker_pid').split()
_OPTIONS = set(('classify_unselected cycle_fields metadata_fields integrity trace retain_source_time selected_ids '
                'time_frame_ids emit_frame_ids blf_time_scope legacy_blf_decode').split())


def native(value, depth=0):
    """复制控制值为有限JSON树。

    参数: value原生值或已冻结映射，depth从0累计且最多320层。
    返回: 独立list/dict及原生标量。
    异常: 类型、深度或非有限数错误。
    """
    if depth > 320:
        raise ValueError('控制数据嵌套超过320层')
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        if not isfinite(value):
            raise ValueError('控制数据需要有限数值')
        return value
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise ValueError('控制映射键需要文本')
        return {key: native(item, depth+1) for key,item in value.items()}
    if type(value) in (list, tuple):
        return [native(item, depth+1) for item in value]
    raise TypeError('控制数据含未声明类型')


def keys(data, names):
    """核对模型的完整字段集合。

    参数: data字典，names允许且必需的字段名序列。
    返回: 原字典。
    异常: 缺项、多项或非字典时ValueError。
    """
    if type(data) is not dict or set(data) != set(names):
        raise ValueError('控制模型字段不符：' + ','.join(names))
    return data


def extract(value, names):
    """摘取固定模型的明确字段。

    参数: value已知模型，names调用点写定的字段名序列。
    返回: 字段名到原值的dict。
    异常: 缺少已声明属性时AttributeError。
    """
    return {name: getattr(value, name) for name in names}


def _scalar(value):
    """编码信号无效值标记。

    参数: value原生标量，float允许NaN/Inf。
    返回: 二元素列表，分别为固定种类及无损原值。
    异常: 未支持类型时ValueError。
    """
    if type(value) is float:
        return ['float', value.hex()]
    if value is None or type(value) in (str, bool, int):
        return ['value', value]
    raise ValueError('信号无效值类型不可传输')


def _restore_scalar(data):
    """恢复信号无效值标记。

    参数: data固定二元素列表。
    返回: 原生标量，保留float与整数区别。
    异常: 种类、数量或浮点文本非法时ValueError。
    """
    if type(data) is not list or len(data) != 2:
        raise ValueError('信号无效值编码非法')
    if data[0] == 'float' and type(data[1]) is str:
        return float.fromhex(data[1])
    if data[0] == 'value' and (data[1] is None or type(data[1]) in (str,bool,int)):
        return data[1]
    raise ValueError('信号无效值编码非法')


def pack_signal(signal):
    """展开已冻结信号声明。

    参数: signal为SignalDefinition。
    返回: JSON原生字段字典。
    异常: 模型类型或字段值非法。
    """
    from .core.binding import SignalDefinition
    if type(signal) is not SignalDefinition:
        raise TypeError('CAN控制信号需要SignalDefinition')
    value = extract(signal, _SIGNAL)
    for name in ('dtype', 'input_dtype', 'code_dtype'):
        value[name] = value[name].value if value[name] is not None else None
    value['invalid_values'] = [_scalar(item) for item in value['invalid_values']]
    return native(value)


def restore_signal(value):
    """恢复明确的信号声明。

    参数: value必须包含_SIGNAL全部字段。
    返回: SignalDefinition，其派生单位状态由构造重新核对。
    异常: 字段、dtype或模型约束错误。
    """
    from .core.binding import SignalDefinition
    from .core.types import SignalDType
    value = dict(keys(value, _SIGNAL))
    for name in ('dtype', 'input_dtype', 'code_dtype'):
        value[name] = SignalDType(value[name]) if value[name] is not None else None
    value['choices'] = tuple(tuple(item) for item in value['choices'])
    value['valid_range'] = tuple(value['valid_range']) if value['valid_range'] is not None else None
    value['invalid_values'] = tuple(_restore_scalar(item) for item in value['invalid_values'])
    return SignalDefinition(**value)


def pack_input(item):
    """展开一个CAN文件输入。

    参数: item为ASCSpec、BLFSpec或CANCSVSpec。
    返回: 固定种类及字段字典的二元素列表。
    异常: 未知输入类型时TypeError。
    """
    from .sources.asc import ASCSpec
    from .sources.blf import BLFSpec
    from .sources.raw_csv import CANCSVSpec
    if type(item) is ASCSpec:
        value = extract(item, _ASC)
        value['path'] = str(value['path'])
        return ['asc', native(value)]
    if type(item) is BLFSpec:
        return ['blf', dict(path=str(item.path), offset_ns=item.offset_ns)]
    if type(item) is CANCSVSpec:
        layout = extract(item.layout, _LAYOUT)
        layout['fields'] = {name: extract(mapping, _COLUMN) for name,mapping in item.layout.fields.items()}
        return ['csv', native(dict(path=str(item.path), layout=layout,
            time=extract(item.time,_CSV_TIME), id_base=item.id_base, length_base=item.length_base,
            channel_origin=item.channel_origin, payload_style=item.payload_style))]
    raise TypeError('CAN控制输入类型未声明')


def restore_input(data):
    """恢复一个CAN文件输入。

    参数: data为固定种类及字段字典。
    返回: ASCSpec、BLFSpec或CANCSVSpec，不读取输入。
    异常: 种类、字段或原模型约束错误。
    """
    from .sources.asc import ASCSpec
    from .sources.blf import BLFSpec
    from .sources.raw_csv import CANCSVSpec, CSVTimeSpec
    from .sources.raw_csv_layout import CANCSVLayout, ColumnMapping
    if type(data) is not list or len(data) != 2:
        raise ValueError('CAN输入声明结构非法')
    kind, value = data
    if kind == 'asc':
        value = dict(keys(value, _ASC))
        value['path'] = Path(value['path'])
        return ASCSpec(**value)
    if kind == 'blf':
        keys(value, ('path','offset_ns'))
        return BLFSpec(Path(value['path']),value['offset_ns'])
    if kind == 'csv':
        value = dict(keys(value, ('path','layout','time','id_base','length_base','channel_origin','payload_style')))
        layout = dict(keys(value['layout'], _LAYOUT))
        if type(layout['fields']) is not dict:
            raise ValueError('CAN CSV列映射需要对象')
        layout['fields'] = {name:ColumnMapping(**keys(mapping,_COLUMN)) for name,mapping in layout['fields'].items()}
        value.update(path=Path(value['path']), layout=CANCSVLayout(**layout),
                     time=CSVTimeSpec(**keys(value['time'],_CSV_TIME)))
        return CANCSVSpec(**value)
    raise ValueError('CAN输入类型未知')


def pack_source(source):
    """展开单次CAN来源。

    参数: source为CANTextSpec。
    返回: 原生字段字典，路径按现有文本保留。
    异常: 类型或嵌套模型错误。
    """
    from .sources.text_can_spec import CANTextSpec
    if type(source) is not CANTextSpec:
        raise TypeError('CAN控制来源需要CANTextSpec')
    return dict(name=source.name,inputs=[pack_input(item) for item in source.inputs],
        dbc_path=str(source.dbc_path), channel=source.channel,
        timebase=dict(timebase_id=source.timebase.timebase_id,time_type=source.timebase.time_type.value,
                      origin=source.timebase.origin),
        decode_policy=source.decode_policy,input_check=source.input_check,file_merge=source.file_merge)


def restore_source(value):
    """恢复单文件CAN来源。

    参数: value为固定来源字段字典，inputs必须恰好一份。
    返回: CANTextSpec，不打开DBC或日志。
    异常: 字段、时间类型或输入数量错误。
    """
    from .sources.text_can_spec import CANTextSpec
    from .core.models import TimebaseSpec
    from .core.types import TimeType
    value = dict(keys(value, ('name','inputs','dbc_path','channel','timebase','decode_policy','input_check','file_merge')))
    base = keys(value['timebase'], ('timebase_id','time_type','origin'))
    if type(value['inputs']) is not list or len(value['inputs']) != 1:
        raise ValueError('CAN工作进程需要恰好一个输入')
    value.update(inputs=tuple(restore_input(item) for item in value['inputs']),
        dbc_path=Path(value['dbc_path']),
        timebase=TimebaseSpec(base['timebase_id'],TimeType(base['time_type']),base['origin']))
    return CANTextSpec(**value)


def pack_options(options):
    """展开CAN读取关键字。

    参数: options仅包含_OPTIONS白名单。
    返回: 原生字典，周期定位显式展开，ID集合变列表。
    异常: 回调、未知关键字或未支持值类型错误。
    """
    from .legacy.records import field_to_dict
    if type(options) is not dict or not set(options) <= _OPTIONS:
        raise ValueError('CAN控制选项不在固定白名单')
    result = dict(options)
    for name in ('cycle_fields','metadata_fields'):
        if name in result:
            result[name] = [field_to_dict(value) for value in result[name]]
    for name in ('selected_ids','time_frame_ids','emit_frame_ids'):
        if result.get(name) is not None:
            result[name] = list(result[name])
    return native(result)


def restore_options(options):
    """恢复CAN读取关键字。

    参数: options为白名单原生字典。
    返回: 含固定LegacyCANField元组及ID元组的dict。
    异常: 未知选项或非法定位模型错误。
    """
    from .legacy.records import field_from_dict
    if type(options) is not dict or not set(options) <= _OPTIONS:
        raise ValueError('CAN控制选项不在固定白名单')
    result = dict(options)
    for name in ('cycle_fields','metadata_fields'):
        if name in result:
            result[name] = tuple(field_from_dict(value) for value in result[name])
    for name in ('selected_ids','time_frame_ids','emit_frame_ids'):
        if result.get(name) is not None:
            result[name] = tuple(result[name])
    return result


def pack_frame_context(value):
    """展开所需帧重建声明。

    参数: value为None或规则元组、周期开关、完整性开关。
    返回: None或固定三元素列表。
    异常: 非原生字段错误。
    """
    if value is None:
        return None
    rules, cycles, integrity = value
    return [native([extract(rule,_RULE) for rule in rules]), cycles, integrity]


def restore_frame_context(value):
    """恢复固定帧重建上下文。

    参数: value为None或三元素列表。
    返回: None或FrameRebuildRule元组与两个bool。
    异常: 字段、开关或规则校验错误。
    """
    from .results.frame_patch import FrameRebuildRule
    if value is None:
        return None
    if type(value) is not list or len(value) != 3 or type(value[1]) is not bool or type(value[2]) is not bool:
        raise ValueError('CAN帧重建上下文非法')
    rules = []
    for row in value[0]:
        row = dict(keys(row,_RULE))
        row['continuous'], row['protected'] = tuple(row['continuous']), tuple(row['protected'])
        rules.append(FrameRebuildRule(**row))
    return tuple(rules), value[1], value[2]


def pack_result(result):
    """展开无活动资源的批量结果。

    参数: result为recovery为None的BatchJobResult。
    返回: 固定原生结果字典。
    异常: 未知类型或仍持恢复句柄时TypeError。
    """
    from .batch.models import BatchJobResult
    if type(result) is not BatchJobResult or result.recovery is not None:
        raise TypeError('批量结果只能发送无活动恢复对象的事实')
    value = extract(result,_RESULT)
    for name in ('output_dir','manifest_path'):
        value[name] = str(value[name]) if value[name] is not None else None
    return native(value)


def restore_result(value):
    """恢复批量任务结果事实。

    参数: value包含_RESULT全部字段。
    返回: BatchJobResult，指定路径字段恢复为Path，恢复对象仍为空。
    异常: 字段或结果模型约束错误。
    """
    from .batch.models import BatchJobResult
    value = dict(keys(value,_RESULT))
    for name in ('output_dir','manifest_path'):
        value[name] = Path(value[name]) if value[name] is not None else None
    value['error_chain'] = tuple(value['error_chain'])
    return BatchJobResult(**value)


def pack_message(family, message):
    """展开固定控制命令的参数。

    参数: family为can/fast/batch，message为现有命令tuple。
    返回: JSON原生参数列表。
    异常: 未支持对象或固定模型错误。
    """
    operation, *arguments = message
    if family == 'can' and operation == 'file':
        source, signals, options, limit, context = arguments
        arguments = [pack_source(source),[pack_signal(item) for item in signals],
                     pack_options(options),limit,pack_frame_context(context)]
    elif family == 'batch' and operation == 'result':
        result, pending = arguments
        arguments = [pack_result(result),pending]
    elif family == 'batch' and operation == 'fast_result':
        # fast工作结果是已知字段dict，Path只在这两个固定结果位置允许。
        arguments[0] = dict(arguments[0])
        for name in ('output_dir','manifest_path'):
            value = arguments[0].get(name)
            if isinstance(value,Path):
                arguments[0][name] = str(value)
    return native(arguments)


def restore_message(family, operation, arguments):
    """恢复固定命令参数。

    参数: family通道、operation命令、arguments原生参数列表。
    返回: 现有消费者使用的tuple，仅恢复写定模型。
    异常: 数量、类型或模型校验错误。
    """
    if type(arguments) is not list:
        raise ValueError('控制消息参数需要列表')
    if family == 'can' and operation == 'file':
        if len(arguments) != 5:
            raise ValueError('CAN文件命令参数数量不符')
        source, signals, options, limit, context = arguments
        if type(signals) is not list or len(signals) > 4096:
            raise ValueError('CAN信号声明数量非法')
        if type(limit) is not int or limit <= 0:
            raise ValueError('CAN工作预算非法')
        arguments = [restore_source(source),tuple(restore_signal(item) for item in signals),
                     restore_options(options),limit,restore_frame_context(context)]
    elif family == 'batch' and operation == 'result':
        if len(arguments) != 2 or type(arguments[1]) is not bool:
            raise ValueError('批量结果参数非法')
        arguments = [restore_result(arguments[0]),arguments[1]]
    elif family == 'batch' and operation == 'fast_result':
        if len(arguments) not in (2,3) or type(arguments[0]) is not dict or type(arguments[1]) is not bool:
            raise ValueError('fast批量结果参数非法')
        result = dict(arguments[0])
        for name in ('output_dir','manifest_path'):
            if result.get(name) is not None:
                result[name] = Path(result[name])
        if 'error_chain' in result:
            result['error_chain'] = tuple(result['error_chain'])
        arguments[0] = result
    elif family == 'can' and operation in ('next','close') and arguments:
        raise ValueError('CAN无参数命令包含多余参数')
    return (operation, *arguments)



_FAST_KEYS = set(('path dbc channel offset_ns asc_options domain_ns table_format file_merge process_count '
                 'memory_budget_bytes spool_quota_bytes metrics inputs _dbc_digest _profile').split())
_METRIC_KEYS = set(('name frame_id is_extended is_fd expr unit signals parameters direction output_scale program').split())


def _object(value, required, allowed):
    """核对有限对象字段。

    参数: value字典，required必需字段，allowed全部允许字段。
    返回: None，不改输入。
    异常: 缺项、未知字段或类型错误。
    """
    if type(value) is not dict or not set(required)<=set(value) or not set(value)<=set(allowed):
        raise ValueError('控制对象字段不符')


def _program(value, depth=0):
    """核对已有数值指令形状。

    参数: value固定指令dict，depth从0累计且最多128。
    返回: None，不重新编译文本表达式。
    异常: 未知操作、dtype、参数或深度错误。
    """
    if depth>128:
        raise ValueError('fast控制指令深度超过128')
    _object(value,('op','dtype'),('op','dtype','name','value','args','scale','offset'))
    operation=value['op']
    if value['dtype'] not in ('int64','uint64','float64'):
        raise ValueError('fast控制指令数值类型非法')
    if operation=='name':
        keys(value,('op','dtype','name'))
        if type(value['name']) is not str:raise ValueError('fast指令名称非法')
    elif operation=='const':
        keys(value,('op','dtype','value'))
        if type(value['value']) not in (int,float):raise ValueError('fast指令常量非法')
    elif operation in ('add','sub','mul','div','abs','neg','to_float','unit_convert'):
        names=('op','dtype','args','scale','offset') if operation=='unit_convert' else ('op','dtype','args')
        keys(value,names)
        expected=2 if operation in ('add','sub','mul','div') else 1
        if type(value['args']) is not list or len(value['args'])!=expected:
            raise ValueError('fast指令参数数量非法')
        if operation=='unit_convert' and any(type(value[k]) not in (int,float) for k in ('scale','offset')):
            raise ValueError('fast指令换算系数非法')
        for argument in value['args']:_program(argument,depth+1)
    else:
        raise ValueError('fast控制指令未知')


def check_fast_spec(value):
    """核对有限fast文件声明。

    参数: value原生spec字典。
    返回: None，不加载数据库或运行公式。
    异常: 未知字段、缺项或固定指令错误。
    """
    _object(value,('path','dbc','channel','metrics'),_FAST_KEYS)
    if type(value['path']) is not str or type(value['dbc']) is not str or type(value['channel']) is not int:
        raise ValueError('fast路径或通道类型非法')
    if type(value['metrics']) not in (tuple,list) or not value['metrics']:
        raise ValueError('fast需要非空计算项列表')
    for item in value['metrics']:
        _object(item,('name','frame_id','expr','unit','signals'),_METRIC_KEYS)
        if any(type(item[key]) is not str for key in ('name','expr','unit')) or type(item['frame_id']) is not int:
            raise ValueError('fast计算项字段类型非法')
        if type(item['signals']) is not dict:
            raise ValueError('fast信号需要对象')
        for signal in item['signals'].values():
            _object(signal,('signal','dtype'),('signal','dtype','input_dtype','scale','offset'))
            if type(signal['signal']) is not str or signal['dtype'] not in ('int64','uint64','float64'):
                raise ValueError('fast信号字段非法')
        if 'parameters' in item and (type(item['parameters']) is not dict
                or any(type(v) not in (int,float) for v in item['parameters'].values())):
            raise ValueError('fast参数需数值映射')
        if item.get('direction') is not None:
            keys(item['direction'],('signal','bucket'))
        if 'program' in item:_program(item['program'])
    if 'inputs' in value:
        if type(value['inputs']) is not list:raise ValueError('fast输入需列表')
        for item in value['inputs']:
            _object(item,('path',),_FAST_KEYS-{'inputs'})
    if 'asc_options' in value:
        _object(value['asc_options'],(),set(_ASC)-{'path'})



def _check_fast_rows(rows):
    """检查快速批量总量所用的固定五字段结果。

    参数: rows为未请求/任务失败时的None，或当前累计器产出的行列表。
    返回: None；不改数值、名称和顺序，也不限制合法任务的计算项数量。
    异常: 未知字段、类型或结果状态错误。
    """
    if rows is None:
        return
    if type(rows) is not list:
        raise ValueError('fast批量累计结果需要列表或None')
    for row in rows:
        keys(row,('name','unit','value','status','reason'))
        if type(row['name']) is not str or type(row['unit']) is not str:
            raise ValueError('fast累计名称及单位需要文本')
        value=row['value']
        if value is not None and (type(value) not in (int,float) or not isfinite(value)):
            raise ValueError('fast累计数值需要有限数或None')
        if row['status'] not in ('complete','indeterminate') or row['reason'] not in (
                None,'no_target_frames','no_selected_direction'):
            raise ValueError('fast累计状态或原因非法')


def check_message_fields(family, operation, arguments):
    """核对大消息的固定字段。

    参数: family通道、operation命令、arguments参数序列。
    返回: None，用户config仍交原AnalysisPlan验证。
    异常: 固定字段、计数、结果状态或指令错误。
    """
    if family=='fast' and operation in ('file','program_file'):
        check_fast_spec(arguments[1])
    elif family=='fast' and operation=='eof':
        facts,clocks=arguments[2],arguments[3]
        keys(facts,('raw','targets','valid','selected','kinds','compatible'))
        if type(facts['raw']) is not int or facts['raw']<0:
            raise ValueError('fast原帧计数非法')
        counts=[]
        for key in ('targets','valid','selected','kinds','compatible'):
            if type(facts[key]) not in (list,tuple) or any(type(v) is not int or v<0 for v in facts[key]):
                raise ValueError('fast计数或身份列表非法')
            if key!='compatible':counts.append(len(facts[key]))
        if len(set(counts))>1:
            raise ValueError('fast各计算项计数长度不符')
        allowed={'compute_seconds','credit_wait_seconds','send_seconds','write_seconds',
                 'read_seconds','decode_seconds','formula_seconds'}
        if not set(clocks)<=allowed or any(type(v) not in (int,float) or not isfinite(v) or v<0 for v in clocks.values()):
            raise ValueError('fast计时字段非法')
    elif family=='batch' and operation in ('run','fast'):
        packet=arguments[0]
        if operation=='run':
            names=('job_id','path') if 'path' in packet else ('job_id','config','base_dir','identity')
            keys(packet,names)
            for key in set(names)-{'config'}:
                if type(packet[key]) is not str:raise ValueError('batch任务文本字段非法')
            if 'config' in packet and type(packet['config']) is not dict:
                raise ValueError('batch内存配置需要对象')
        else:
            keys(packet,('job_id','path','spec','total'))
            if type(packet['job_id']) is not str or packet['path'] is not None and type(packet['path']) is not str or type(packet['total']) is not bool:
                raise ValueError('fast批量任务字段非法')
            check_fast_spec(packet['spec'])
    elif family=='batch' and operation in ('result','fast_result'):
        if operation=='fast_result' and len(arguments)==3:
            _check_fast_rows(arguments[2])
        row=arguments[0]
        _object(row,('job_id','status'),_RESULT)
        if row['status'] not in ('completed','failed','cancelled'):
            raise ValueError('batch结果状态非法')
        for key in set(_RESULT)-{'error_chain','elapsed_seconds','memory_budget_bytes','worker_pid'}:
            if row.get(key) is not None and type(row[key]) is not str:
                raise ValueError('batch结果文本字段非法')
        if 'error_chain' in row and (type(row['error_chain']) is not list or any(type(v) is not str for v in row['error_chain'])):
            raise ValueError('batch错误链需要文本列表')
        if 'elapsed_seconds' in row and (type(row['elapsed_seconds']) not in (int,float) or not isfinite(row['elapsed_seconds']) or row['elapsed_seconds']<0):
            raise ValueError('batch结果耗时非法')
        for key in ('memory_budget_bytes','worker_pid'):
            if row.get(key) is not None and (type(row[key]) is not int or row[key]<1):
                raise ValueError('batch结果计数非法')
