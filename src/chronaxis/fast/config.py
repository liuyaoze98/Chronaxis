"""把独立原始报文配置编译成每文件任务，共用 Chronaxis 的单位、类型与来源位置规则。"""
from dataclasses import asdict
from pathlib import Path

from ..configuration import ConfigurationError, load_configuration
from ..configuration.diagnostics import locate_error
from ..configuration.imports import expand_document_imports
from ..legacy.binding import dbc_candidates
from ..planning.checks import PlanValidationError, configuration_error
from ..planning.dbc_defaults import load_dbc, scoped_dbc_cache
from ..planning.plan import AnalysisPlan
from ..sources.asc import ASCSpec
from ..sources.can_spec import LegacyCANSpec, can_field_from_key
from .compute import encode_program, prepare_metric


def _unsupported(path, message):
    """构造可由已有配置诊断和 CLI 消费的错误。"""
    return PlanValidationError(path, message, 'unsupported_fast', hint='修改配置或使用通用 chronaxis run')


def _capabilities(raw):
    """仅检查显式请求，避免把通用计划的默认设置误判为用户要求。"""
    errors = []
    for key in ('derived', 'lookups', 'rules', 'windows', 'sequences', 'calculations', 'presets',
                'aggregations', 'transforms', 'intervals', 'preset_bindings'):
        if raw.get(key):
            errors.append(_unsupported('$.' + key, 'fast 只执行当前帧数值公式'))
    for key in ('execution', 'diagnostics'):
        group = raw.get(key)
        if isinstance(group, dict):
            for field, value in group.items():
                if key == 'diagnostics' and value is False:
                    continue
                errors.append(_unsupported(f'$.{key}.{field}', 'fast 不执行该资源或诊断策略'))
    outputs = raw.get('outputs')
    if isinstance(outputs, dict):
        for key in ('signal_csv', 'can_frames'):
            if outputs.get(key) is not None:
                errors.append(_unsupported('$.outputs.' + key, 'fast 只发布指标汇总'))
        if outputs.get('contributions', 'none') != 'none':
            errors.append(_unsupported('$.outputs.contributions', 'fast 不生成逐帧明细'))
    sources = raw.get('sources')
    if isinstance(sources, list):
        if len(sources) != 1:
            errors.append(_unsupported('$.sources', '当前 fast 任务须有一个来源'))
        for i, src in enumerate(sources):
            if not isinstance(src, dict):
                continue
            if 'legacy_profile' in src:
                errors.append(_unsupported(f'$.sources[{i}].legacy_profile', '显式锁定的 reader 与 fast 冲突'))
            reader = src.get('reader')
            if isinstance(reader, dict):
                for key, value in reader.items():
                    if (key,value) not in (('input_check','auto'), ('decode_scope','requested'), ('decode_policy','strict')):
                        errors.append(_unsupported(f'$.sources[{i}].reader.{key}', 'fast 仅支持按需读取与严格长度检查'))
    metrics = raw.get('message_calculations')
    if not metrics:
        errors.append(_unsupported('$.message_calculations', '至少需要一项逐消息累计'))
    elif isinstance(metrics, list):
        for i, item in enumerate(metrics):
            if isinstance(item, dict) and 'profile' in item:
                errors.append(_unsupported(f'$.message_calculations[{i}].profile', '显式锁定的解码器与 fast 冲突'))
    return errors


def _source(plan):
    """取得唯一文件及其时钟参数，保持 ASC 与 BLF 各自的时间解释。"""
    source, = plan.sources
    cfg = source.config
    if source.source_type not in ('can_blf', 'can_asc', 'asc_or_blf'):
        raise _unsupported('$.sources[0]', 'fast 首版只读取 ASC/BLF')
    if cfg.decode_policy != 'strict':
        raise _unsupported('$.sources[0].reader', 'fast 要求严格帧长')
    options = {}
    if isinstance(cfg, LegacyCANSpec):
        paths = cfg.input_paths
        options['offset_ns'] = cfg.offset_ns
    else:
        paths = tuple(item.path for item in cfg.inputs)
        if len(paths) == 1:
            item, = cfg.inputs
            if isinstance(item, ASCSpec):
                options['asc_options'] = {k:v for k,v in asdict(item).items() if k != 'path'}
            else:
                options['offset_ns'] = item.offset_ns
    if len(paths) != 1:
        raise _unsupported('$.sources[0].paths', 'fast单任务展开后须恰好一个ASC或BLF文件；独立文件可用fast batch，连续分卷请使用通用分析入口')
    domain = plan.dataset.domain
    return dict(path=str(paths[0]), dbc=str(cfg.dbc_path), channel=cfg.channel + 1,
                domain_ns=[domain.start_ns, domain.end_ns] if domain else None,
                table_format=plan.outputs.tables, **options)


def _flag(selector, fields, name):
    """合并同一公式中每个信号和选择器的身份限制；显式矛盾不可合并。"""
    flags = {getattr(v,name) for v in (selector,*fields)} - {None}
    if len(flags) > 1:
        raise ValueError('同一帧公式的 ' + name + ' 互相冲突')
    return next(iter(flags), None)


def _metric(plan, item, database):
    """静态验证本次请求的信号及原单位，将已检查的表达式树编码为简单数值指令。"""
    required = set(item.expr.dependencies)
    if item.disjunction:
        required.add(item.disjunction.signal)
    signals, fields = {}, {}
    for name in sorted(required):
        definition = plan.bindings.resolve(name)
        if definition.dtype.value not in ('int64','uint64','float64'):
            raise ValueError(name + ' 需要数值类型')
        if definition.valid_range or definition.invalid_values:
            raise ValueError(name + ' 声明了 fast 尚不支持的有效范围或无效值')
        if definition.unit_status != 'verified':
            raise ValueError(name + ' 未验证单位或换算')
        field = can_field_from_key(definition.field)
        fields[name] = field
        signals[name] = dict(signal=field.signal, dtype=definition.dtype.value,
                             scale=definition.scale, offset=definition.offset)
        if definition.input_dtype is not None:
            signals[name]['input_dtype'] = definition.input_dtype.value
    selector = item.update_message
    extended = _flag(selector, fields.values(), 'is_extended')
    fd = _flag(selector, fields.values(), 'is_fd')
    messages = dbc_candidates(database, selector.frame_id, [v.signal for v in fields.values()], extended, fd)
    if len(messages) != 1:
        raise ValueError('DBC 候选不唯一，请补充扩展帧或 FD 标志')
    message, = messages
    if message.is_container or message.is_multiplexed():
        raise ValueError('fast 首版不支持 container 或 multiplex 报文')
    for name, field in fields.items():
        unit = message.get_signal_by_name(field.signal).unit
        if unit and unit != plan.bindings.resolve(name).input_unit:
            raise ValueError(name + ' 的 DBC 单位与声明的输入单位不符')
    direction = item.disjunction
    spec = dict(name=item.calculation_id,frame_id=selector.frame_id,is_extended=message.is_extended_frame,
                is_fd=fd,expr=item.expr.text,unit=item.unit,signals=signals,
                parameters={p.name:p.value for p in item.parameters},
                direction=dict(signal=fields[direction.signal].signal,bucket=direction.bucket) if direction else None,
                output_scale=1,program=encode_program(item.expr.root))
    prepare_metric(spec)
    return spec, message


def _compile_plan(plan, with_database):
    """编译公共静态计划的独立文件任务，仅需加载本计划的 DBC 元数据。"""
    import cantools
    errors = []
    result = _source(plan)
    try:
        database = load_dbc(result['dbc'])
    except (OSError, ValueError, cantools.database.errors.Error) as exc:
        raise PlanValidationError('$.sources[0].dbc_by_channel', str(exc)) from exc
    metrics = []
    bindings = {}
    for i, item in enumerate(plan.message_calculations):
        try:
            metric, message = _metric(plan,item,database)
            # 同一实际帧只解码一次。不同公式若各自选中不同定义，不能等到 worker 才拒绝。
            fd = metric['is_fd']
            for actual_fd in ((False, True) if fd is None else (fd,)):
                key = (metric['frame_id'], metric['is_extended'], actual_fd)
                decoder = None if actual_fd and not message.is_fd else message
                if bindings.setdefault(key,decoder) is not decoder:
                    raise ValueError(f'ID {key[0]:#x} 在同一实际帧型中对应多个 DBC 定义')
            metrics.append(metric)
        except (TypeError, ValueError, OverflowError) as exc:
            errors.append(_unsupported(f'$.message_calculations[{i}]', str(exc)))
    if errors:
        raise PlanValidationError.from_diagnostics(errors)
    result['metrics'] = metrics
    if with_database:
        result['_database'] = database
    return result


def compile_template_plan(plan, *, template_path=None, _with_database=False):
    """为 batch.template_jobs 展开的一个真实文件编译 fast 任务。

    只使用原模板中显式声明的选项判断能力冲突，不把通用缺省值解释为用户要求。
    模板绑定错误带模板路径及当前文件说明。此步骤不执行分析或打开原始日志。
    """
    from ..planning.checks import json_value
    raw = json_value(plan.raw_config)
    try:
        errors = _capabilities(raw)
        if errors:
            raise PlanValidationError.from_diagnostics(errors)
        return _compile_plan(plan, _with_database)
    except PlanValidationError as exc:
        if template_path is not None:
            source = raw['sources'][0]
            input_path = source.get('path', source.get('paths', ''))
            for diagnostic in exc.diagnostics:
                diagnostic.source = str(template_path)
                diagnostic.hint = f'模板输入 {input_path}。' + (diagnostic.hint or '')
                diagnostic.refresh_text()
            exc.source = str(template_path)
            exc.refresh_text()
        raise


@scoped_dbc_cache()
def compile_config(path, *, _with_database=False):
    """读取配置和导入定义，验证 DBC 与 fast 子集。默认返回可序列化单文件任务。

    参数 path 是 JSON/YAML 文件路径；_with_database 仅给同进程立即执行时复用数据库。
    错误带配置路径。此入口只准备计算，不打开日志或创建输出目录。
    """
    target = Path(path).absolute()
    try:
        doc = expand_document_imports(load_configuration(target))
    except ConfigurationError as exc:
        raise configuration_error(exc) from exc
    try:
        if not isinstance(doc.data,dict):
            raise _unsupported('$', '需要单任务分析配置')
        errors = _capabilities(doc.data)
        if errors:
            raise PlanValidationError.from_diagnostics(errors)
        plan = AnalysisPlan.from_dict(doc.data,base_dir=target.parent)
        return _compile_plan(plan, _with_database)
    except PlanValidationError as exc:
        raise locate_error(exc,doc)
