"""检查来源和信号配置，建立静态定位与显式转换声明。

输入是当前配置的sources、signals数组和相对路径基准，输出SourcePlan
与SignalPlan元组。内存原行已在配置中，可核对原顺序和已出现字段；CSV
只保存有序路径和格式，不读取文件表头。时间使用明确单位、公共起点或时区，
原字段保持原文，整数值不先转浮点。valid_for声明有效值最多保持的时间，
省略时取本信号period或运行期DBC周期的三倍。
CAN支持既有单BLF profile与新ASC/原始CSV静态规格，完整原定位保存为规范字段键；
旧表格profile仍报告capability_unavailable。仅需补齐信号元数据时读取DBC，不读日志。
"""

# 配置基准和时基身份使用标准库，无输入扫描。
from hashlib import sha256
from pathlib import Path
# 原模型负责声明范围/值类型/时序顺序门槛。
from ..core.binding import SignalDefinition
from ..core.models import MemoryRow, SourceSpec, TimebaseSpec
from ..core.types import SignalDType, TimeType
# CSV只构造配置，不实例化文件读取器。
from ..sources.csv_spec import SignalCSVSpec
from ..sources.can_spec import LegacyCANSpec
from ..sources.text_can_spec import CANTextSpec
from ..legacy.records import PROFILE_ID, field_from_dict
# 配置校验严格定位并深冻结元数据。
from .checks import (PlanValidationError, absolute_path, array_at, canonical, choice_at, coordinate_at,
                     duration_at, metadata_at, model_at, number_at, object_at, text_at, timezone_at)
from .models import SignalPlan, SourcePlan
from .signal_validity import declared_valid_for
from .input_defaults import source_defaults, source_reference
from .input_paths import expand_source_files
from .dbc_defaults import DBCDefaults


def parse_sources(value, base: Path) -> tuple[SourcePlan, ...]:
    """按声明顺序解析内存、已解码CSV或原始CAN规格，不读取分析文件。

    参数:
        value (list): sources配置数组，每项含名称、来源种类和时间声明。
        base (Path): 相对CSV、BLF及DBC路径的词法解释基准。
    返回:
        tuple[SourcePlan, ...]。至少含一个来源；路径转为绝对定位并保留原顺序。
        内存原行按声明顺序构造，CSV/CAN仅构造配置，文件、表头及DBC尚未核实。
    异常:
        PlanValidationError: 字段、格式、名称、时序、时间基准或来源能力错误，
            保存对应配置位置；未接入来源使用capability_unavailable错误码。
    副作用:
        不打开CSV或DBC；地区时区解析可能访问本机时区数据库。
    """
    # 来源数组保持声明顺序，只有用户明确的目录/通配符会枚举文件名。
    items = array_at(value, '$.sources')
    # dataset分析基准需要至少一个明确来源。
    if not items:
        # 空来源计划无法声明时间坐标。
        raise PlanValidationError('$.sources', '至少需要一个来源')
    # 当前计划内登记唯一来源名称。
    result, names = [], set()
    # 原文件和来源顺序保持调用者声明。
    for index, raw in enumerate(items):
        # 每个错误准确定位数组项。
        path = f'$.sources[{index}]'
        # 在种类分派前确认基本对象与kind，不忽略未知顶层键。
        if type(raw) is not dict:
            # 不从类名或字符串构建来源。
            raise PlanValidationError(path, 'source必须为对象')
        # 仅显式目录/通配符枚举文件名；完整路径仍不stat、不打开业务输入。
        if raw.get('source_type') != 'memory' and ('path' in raw or 'paths' in raw):
            paths, shifts = expand_source_files(raw, base, path)
            raw = dict(raw, paths=[str(item) for item in paths])
            raw.pop('path', None)
            if shifts is not None:
                raw['offsets'] = list(shifts)
        # 默认仅识别ASC/BLF，CSV/内存保持明确种类；省略时间不代表自动校时。
        raw = source_defaults(raw, index)
        # 解析补齐后的来源类型，未知值仍由统一选择检查报告。
        source_type = choice_at(raw.get('source_type'), ('memory', 'signal_csv', 'can_asc', 'asc_or_blf', 'can_blf', 'legacy_raw_csv','raw_can_csv'), path + '.source_type')
        if source_type in ('can_asc','asc_or_blf','raw_can_csv'):
            # 新路径独立声明格式和连续文件，不冒充旧profile或把原始表当信号表。
            from .text_inputs import parse_text_source
            source=parse_text_source(raw,base,path)
            if source.name in names:
                raise PlanValidationError(path+'.name','来源重复：'+source.name)
            names.add(source.name); result.append(source)
            continue
        # 其余来源只接受内存、信号CSV及受控BLF读取路径。
        if source_type not in ('memory', 'signal_csv', 'can_blf'):
            # 未支持的来源应在配置阶段拒绝。
            raise PlanValidationError(path + '.source_type', f'{source_type}不支持；原始CSV请使用can_raw_csv来源', 'capability_unavailable')
        # 格式特有字段必须按种类严格限定。
        if source_type == 'can_blf':
            # BLF来源使用固定profile、单通道DBC和有序文件路径，只接受声明的读取选项。
            raw = object_at(raw, path, ('name', 'source_type', 'time', 'dbc_by_channel'),
                            ('path', 'paths', 'reader_options', 'metadata', 'decode_scope', 'input_check', 'legacy_profile'))
        else:
            optional = ('metadata',) if source_type == 'memory' else ('path', 'paths', 'encoding', 'delimiter', 'missing_values', 'metadata')
            # memory行或CSV时间列不能省略。
            raw = object_at(raw, path, ('name', 'source_type', 'time', 'rows' if source_type == 'memory' else 'time_column'), optional)
        # 来源名与DSL别名采用统一安全标识规则。
        name = text_at(raw['name'], path + '.name', identifier=True)
        # 重名不能选首项/覆盖。
        if name in names:
            # 精确指出第二次定义位置。
            raise PlanValidationError(path + '.name', f'来源重复：{name}')
        # 只登记当前计划名称。
        names.add(name)
        # 不接受漂移/隐式机器时区等未定义字段。
        clock = object_at(raw['time'], path + '.time', ('time_type', 'unit'), ('origin', 'offset', 'timezone'))
        # 时间坐标种类与单位独立。
        time_type = choice_at(clock['time_type'], ('relative', 'absolute'), path + '.time.time_type')
        # ISO表示只允许absolute。
        unit = choice_at(clock['unit'], ('s', 'ms', 'us', 'ns', 'ISO8601'), path + '.time.unit')
        if source_type == 'can_blf':
            # 原CAN timestamp固定为秒；不接受不会参与该转换的timezone声明。
            choice_at(unit, ('s',), path + '.time.unit')
            if 'timezone' in clock:
                raise PlanValidationError(path + '.time.timezone', '固定CAN秒时间不接受timezone')
        # 首版relative必须有明确公共起点声明。
        if time_type == 'relative' and ('origin' not in clock or unit == 'ISO8601' or 'timezone' in clock):
            # 不把原首点0视为公共origin。
            raise PlanValidationError(path + '.time', 'relative必须origin，不接受ISO8601或timezone')
        # absolute坐标已经UTC，不接相对origin。
        if time_type == 'absolute' and 'origin' in clock:
            # 防止一来源同时声明两种坐标含义。
            raise PlanValidationError(path + '.time.origin', 'absolute不接受relative origin')
        # 同一完整relative origin生成相同ID，absolute统一UTC。
        origin = text_at(clock['origin'], path + '.time.origin') if time_type == 'relative' else None
        # ID来自声明内容，不来自机器、文件名或实际首点。
        clock_id = 'relative_' + sha256(origin.encode('utf-8')).hexdigest()[:16] if origin is not None else 'utc'
        # 固定映射坐标保持定宽纳秒，负offset允许。
        offset = coordinate_at(clock.get('offset', '0s'), path + '.time.offset')
        # naive日期是否可解析由实际显式tz决定。
        tz = timezone_at(clock.get('timezone'), path + '.time.timezone')
        # 型别与origin契约沿用已验时间模型。
        timebase = model_at(TimebaseSpec, path + '.time', clock_id, TimeType(time_type), origin)
        # 规范定位身份包括完整原格式与时间声明。
        identity_input = dict(raw)
        # memory行在配置中已经可见，允许检查原顺序但不补数据。
        if source_type == 'memory':
            # memory行time必须明确单位，不用source.unit解释裸数。
            rows = []
            # 行序号由声明原序生成，不排序。
            for row_index, row in enumerate(array_at(raw['rows'], path + '.rows')):
                # 行仅time与values，未知字段不忽略。
                row_path = f'{path}.rows[{row_index}]'
                # 保留原字段值且拒绝自由行选项。
                row = object_at(row, row_path, ('time', 'values'))
                # 原值对象不是自由元数据，但字段名称允许完整原文。
                if type(row['values']) is not dict:
                    # 不接受不明列排列或假默认值。
                    raise PlanValidationError(row_path + '.values', '必须为原字段对象')
                # 单位/日期与时基种类显式配合。
                time_ns = coordinate_at(row['time'], row_path + '.time', absolute=time_type == 'absolute', tz=tz)
                # 原标量模型复制只读值映射，不将None补0。
                rows.append(model_at(MemoryRow, row_path, time_ns=time_ns, values=row['values'], sequence=row_index))
            # SourceSpec检查来源内回退/offset溢出，不重排原行。
            config = model_at(SourceSpec, path, name=name, timebase=timebase, rows=tuple(rows), offset_ns=offset)
        else:
            # 文件路径必须且只能使用一种明确写法。
            if ('path' in raw) == ('paths' in raw):
                # 文件选择已在前面展开，不在这里重复扫描目录或拼接两组路径。
                raise PlanValidationError(path, 'path与paths必须且只能提供一个')
            # path单项和paths数组归一为严格原序tuple。
            raw_paths = [raw['path']] if 'path' in raw else array_at(raw['paths'], path + '.paths')
            # 词法绝对化不检查文件存在，配置目录作为明确基准。
            paths = tuple(absolute_path(item, base, f'{path}.paths[{i}]') for i, item in enumerate(raw_paths))
            if source_type == 'can_blf':
                # 每个来源按声明顺序读取1至4096个BLF文件，不扫描目录或忽略额外路径。
                if not 1 <= len(paths) <= (4096):
                    raise PlanValidationError(path + '.paths', 'BLF来源需要1至4096个有序文件路径')
                profile = choice_at(raw.get('legacy_profile', PROFILE_ID), (PROFILE_ID,), path + '.legacy_profile')
                options = object_at(raw.get('reader_options', {}), path + '.reader_options', (),
                    ('decode_policy',))
                dbc = raw['dbc_by_channel']
                if type(dbc) is not dict or len(dbc) != 1:
                    raise PlanValidationError(path + '.dbc_by_channel', '当前CAN必须恰有一个通道到DBC路径声明')
                channel_text = next(iter(dbc))
                from .channels import channel_index
                channel = channel_index(channel_text, path + '.dbc_by_channel', key=True)
                dbc_path = absolute_path(dbc[channel_text], base, path + '.dbc_by_channel.' + channel_text)
                # model_at的path参数表示错误位置；源模型path按位置传递，避免同名冲突。
                config = model_at(LegacyCANSpec, path, name, paths[0], dbc_path,
                    channel, timebase, unit, offset, profile,
                    choice_at(raw.get('decode_scope', 'requested'), ('all', 'requested'), path + '.decode_scope'),
                    choice_at(raw.get('input_check', 'auto'), ('auto', 'full'), path + '.input_check'),
                    paths if len(paths)>1 else (),
                    choice_at(options.get('decode_policy','strict'),
                        ('strict','partial','legacy'),path+'.reader_options.decode_policy'))
                # 默认按实际需求执行，不回填raw；实际执行策略还进入来源描述和运行证明。
                # 实际绝对定位进入来源声明身份，不读取路径内容或猜测DBC元数据。
                identity_input['dbc_by_channel'] = {channel_text: str(dbc_path)}
            else:
                # missing标记精确匹配，包括空字符串，不strip或猜NA。
                missing = array_at(raw.get('missing_values', ['']), path + '.missing_values')
                # SignalCSVSpec检查空paths/编码/分隔符/重复标记，无输入I/O。
                config = model_at(SignalCSVSpec, path, name=name, paths=paths, timebase=timebase,
                                  time_column=text_at(raw['time_column'], path + '.time_column'), unit=unit, offset_ns=offset,
                                  timezone=tz, encoding=raw.get('encoding', 'utf-8'), delimiter=raw.get('delimiter', ','), missing_values=tuple(missing))
            # 实际定位身份使用已解析绝对路径，仍保留数组原序。
            identity_input['paths'] = [str(item) for item in paths]
            # 两种等价路径输入形式不保留冗余path键。
            identity_input.pop('path', None)
        # 自由元数据深冻结，不向reader转发未定义键。
        metadata = metadata_at(raw.get('metadata', {}), path + '.metadata')
        # 构造来源声明模型；文件存在性和实际列仍留待读取核实。
        result.append(SourcePlan(name, source_type, config, unit, clock.get('timezone'), canonical(identity_input), metadata))
    # 不保留用户可变列表引用。
    return tuple(result)


def parse_signals(value, sources: tuple[SourcePlan, ...]) -> tuple[SignalPlan, ...]:
    """检查原字段到简单别名的转换与有效期声明。

    参数:
        value (list): signals配置数组，声明来源、原字段、类型、单位及可选period/valid_for。
        sources (tuple[SourcePlan, ...]): 当前计划已经解析的来源。
    返回:
        tuple[SignalPlan, ...]。保持信号顺序，choices原编码类型保留，
        valid_for转为正整数纳秒；缺省且等待DBC时保存None，转换和可选语义按核心模型检查。
    异常:
        PlanValidationError: 结构、来源、字段、类型、单位、有效期或转换契约错误。
    边界:
        非空内存可检查字段；CSV/CAN日志不读。缺省CAN元数据只读取DBC。
        本函数保存有效期声明，不保持信号值或执行过期判断。
    """
    # 来源定位表仅当前计划有效。
    source_map = {item.name: item for item in sources}
    defaults = DBCDefaults()
    # 信号原顺序保留，唯一性由声明绑定统一检查。
    result = []
    # 可选项来自当前配置schema，不开放自由质量或额外有效期政策。
    optional = ('valid_for', 'period', 'input_unit', 'scale', 'offset', 'sample_policy', 'same_time_policy', 'choices', 'valid_range', 'invalid_values',
                'sign_convention', 'measurement_location', 'mapping_version', 'semantic_id', 'semantic_contract_version', 'metadata')
    # 不将字符串解释为signal迭代器。
    from .signal_groups import signal_entries
    for raw, path in signal_entries(value):
        # 未登记的字段明确报错，不能静默忽略拼写错误或已删除的旧参数。
        raw = object_at(raw, path, ('name', 'field'), optional + ('source','dtype','unit'))
        if 'dtype' in raw:
            choice_at(raw['dtype'],tuple(item.value for item in SignalDType),path+'.dtype')
        if 'unit' in raw:
            text_at(raw['unit'],path+'.unit')
        # 来源名本身是简单标识符。
        source = source_reference(raw, sources, path)
        # 不靠相同semantic_id推测来源。
        if source not in source_map:
            # static也必须唯一定位当前来源。
            raise PlanValidationError(path + '.source', f'未知来源：{source}','invalid_reference',
                hint='填写sources中已声明的name：'+', '.join(source_map))
        # memory行已在配置内可见时检查实际字段，不为CSV额外读表头。
        config = source_map[source].config
        if isinstance(config, (LegacyCANSpec,CANTextSpec)):
            # 原CAN定位严格复用六字段模型；只保存规范键，不把点号原名变成DSL属性。
            # 当前来源只有一个DBC通道；省略时继承，显式错误仍由原模型检查。
            field_raw = raw['field']
            if type(field_raw) is dict:
                field_raw = dict(field_raw)
                from .channels import channel_index
                field_raw['channel'] = (channel_index(field_raw['channel'], path + '.field.channel')
                                        if 'channel' in field_raw else config.channel)
            locator = model_at(field_from_dict, path + '.field', field_raw)
            if locator.channel != config.channel:
                raise PlanValidationError(path + '.field.channel', '信号通道必须与来源唯一DBC通道一致')
            raw = defaults.fill(raw,config,locator,path)
            try:
                # 规范定位也受CAN读取协议的有界JSON约束；生成失败仍归为当前位置的配置错误。
                field = locator.key
            except (TypeError, ValueError) as error:
                raise PlanValidationError(path + '.field', str(error)) from error
        else:
            # memory/CSV仍只接受原字段文本，不能借CAN对象扩展其他来源的定位语义。
            field = text_at(raw['field'], path + '.field')
            for key in ('dtype', 'unit'):
                if key not in raw:
                    raise PlanValidationError(path + '.' + key,'已解析数据没有DBC元数据，请提供' + key, 'missing_field')
        # 空memory无实际字段证明，保留空观测状态供报告。
        if isinstance(config, SourceSpec) and config.rows and not any(field in row.values for row in config.rows):
            # 不造虚拟字段通过T39。
            raise PlanValidationError(path + '.field', f'原memory字段不存在：{field}')
        # CAN缺省值已由DBC元数据推导；不扫描日志猜数据类型。
        dtype = choice_at(raw['dtype'], tuple(item.value for item in SignalDType), path + '.dtype')
        # choices用二元JSON数组保存int/bool/str编码类型，避免对象键字符串化。
        choices = []
        # 每个明确映射均保留原序和原类型。
        for choice_index, pair in enumerate(array_at(raw.get('choices', []), path + '.choices')):
            # 不接无类型字典编码或错长度配对。
            if type(pair) is not list or len(pair) != 2:
                # 核心随后继续检查标签域与重复编码。
                raise PlanValidationError(f'{path}.choices[{choice_index}]', 'choices项必须为[原编码, 标签]二元数组')
            # 仅冻结结构，不做bool truthiness或整数float转换。
            choices.append(tuple(pair))
        # 范围若存在必须保持二端点原数值。
        valid_range = tuple(array_at(raw['valid_range'], path + '.valid_range')) if 'valid_range' in raw else None
        # 用户有效期优先；信号周期乘三只决定保持上限，不改报文实际时间。
        valid_for_ns = declared_valid_for(raw, path,
            dbc_available=isinstance(config, (LegacyCANSpec, CANTextSpec)))
        # core检查所有声明转换及语义，额外factor只在解码输出之后应用一次。
        definition = model_at(SignalDefinition, path, name=raw['name'], source=source, field=field,
                              dtype=SignalDType(dtype), unit=raw['unit'], valid_for_ns=valid_for_ns,
                              input_unit=raw.get('input_unit'), scale=raw.get('scale', 1), offset=raw.get('offset', 0), choices=tuple(choices),
                              valid_range=valid_range, invalid_values=tuple(array_at(raw.get('invalid_values', []), path + '.invalid_values')),
                              sample_policy=raw.get('sample_policy', 'backward_hold'), same_time_policy=raw.get('same_time_policy', 'error'),
                              semantic_id=raw.get('semantic_id'), semantic_contract_version=raw.get('semantic_contract_version'),
                              mapping_version=raw.get('mapping_version'), sign_convention=raw.get('sign_convention'), measurement_location=raw.get('measurement_location'))
        # 自由metadata不作为隐藏转换或质量策略。
        result.append(SignalPlan(definition, metadata_at(raw.get('metadata', {}), path + '.metadata')))
    # 全部契约已经冻结，不依赖用户列表生命周期。
    return tuple(result)
