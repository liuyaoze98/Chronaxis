"""按请求生成可独立加载的有效配置；只读配置，不读取业务输入。"""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

from . import load_configuration, parse_configuration
from .file_tools import path_fields,validate_document,serialize_configuration,output_format,write_new_configuration


def _duration(value):
    """纳秒用整数文本输出，不经浮点。参数: int。返回: 时长str。异常: 无。"""
    return str(value)+'ns'


def _interval(choice):
    """输出合法间隔对象，不为actual/dbc补伪周期。参数: IntervalChoice。返回: dict。异常: 无。"""
    result={'mode':choice.mode}
    if choice.step_ns is not None:result['value']=_duration(choice.step_ns)
    if choice.driver is not None:result['driver']=choice.driver
    return result


def _signal_defaults(raw,plan,*,normalized=False):
    """复用当前编译的信号事实，不为导出配置再次读取DBC。

    参数: raw为独立配置副本；plan为当前计划；normalized表示转换字段已展开为内部平铺形式。
    返回: None；只补入可重复加载的原类型、单位及映射。
    异常: KeyError为内部配置与计划不匹配；不修改用户原文件。
    """
    from ..planning.signal_groups import declared_signals
    for signal,typed in zip(declared_signals(raw['signals']),plan.signals):
        # 保留换算前的声明类型，重载再推导同一提升；不输出额外input_dtype字段。
        signal.setdefault('dtype',(typed.definition.input_dtype or typed.definition.dtype).value)
        # 固定DBC原单位而不新增另一份转换记录；重载继续沿完整系数做一次转换。
        if plan.config_version == 4:
            destination = signal if normalized else signal.setdefault('conversion', {})
            destination.setdefault('input_unit', typed.definition.input_unit)
        signal.setdefault('unit',typed.definition.unit)
        if typed.definition.dtype.value=='enum':
            signal.setdefault('choices',[list(pair) for pair in typed.definition.choices])
            if typed.definition.code_dtype is not None:
                signal.setdefault('code_dtype', typed.definition.code_dtype.value)


def _analysis_defaults(raw,plan):
    """显式化已编译模型的适用默认值。参数: 独立原生配置、计划。返回: None。异常: 内部契约错误。

    只填写实际有含义且可重新加载的字段；不猜单位/方向/阈值，不写无关规则参数或DBC周期。
    """
    _signal_defaults(raw,plan,normalized=True)
    raw.setdefault('execution',{}).update(asdict(plan.execution))
    raw.setdefault('diagnostics',{}).update(asdict(plan.diagnostics))
    outputs=raw.setdefault('outputs',{})
    for key in ('tables','manifest','contributions'):outputs.setdefault(key,getattr(plan.outputs,key))
    for key in ('signal_csv','can_frames'):
        option=getattr(plan.outputs,key)
        if option is None:outputs.setdefault(key,None);continue
        item=outputs[key];item.setdefault('scope',option.scope)
        grid=option.spec.resampling if key=='signal_csv' else option.resampling
        if grid is not None:item['resampling'].setdefault('origin',_duration(grid.origin_ns))
        if key=='can_frames':
            item.setdefault('source_time_reference',option.spec.source_time_reference)
            item.setdefault('output_offset',_duration(option.spec.output_offset_ns))
    for index,(source,typed) in enumerate(zip(raw['sources'],plan.sources)):
        # --defaults展开有效来源默认值；普通resolve仍保留用户简写。
        from ..planning.input_defaults import source_defaults
        source.update(source_defaults(source,index,inferred_type=typed.source_type))
        source['time'].setdefault('offset','0s')
        if typed.source_type=='signal_csv':
            for key in ('encoding','delimiter'):source.setdefault(key,getattr(typed.config,key))
            source.setdefault('missing_values',list(typed.config.missing_values))
        elif typed.source_type in ('can_blf','can_asc','asc_or_blf','raw_can_csv'):
            source.setdefault('reader_options',{}).setdefault('decode_policy',typed.config.decode_policy)
            if typed.source_type=='can_blf':
                for key in ('decode_scope','input_check'):source.setdefault(key,getattr(typed.config,key))
    from ..planning.signal_groups import declared_signals
    for signal,typed in zip(declared_signals(raw['signals']),plan.signals):
        for key in ('scale','offset','sample_policy','same_time_policy'):
            signal.setdefault(key,getattr(typed.definition,key))
    for typed,expression in zip(plan.derived,plan.derived_expressions):
        raw['derived'][typed.definition.name].setdefault('unit',expression.root.unit)
    by_rule={item.rule_id:item for item in plan.rules}
    for rule in raw.get('rules',[]):
        typed=by_rule[rule['name']];kind=typed.rule_type
        if kind=='condition_duration':rule.setdefault('selection_origin',typed.selection_origin)
        elif kind in ('debounce','hysteresis'):
            rule.setdefault('enter_delay',_duration(typed.stability.enter_ns))
            rule.setdefault('exit_delay',_duration(typed.stability.exit_ns))
        elif kind=='start_end':
            rule.setdefault('emit_initial',typed.start_end.emit_initial)
            rule.setdefault('timeout',None if typed.start_end.timeout_ns is None else _duration(typed.start_end.timeout_ns))
        else:
            rule.setdefault('emit_initial',typed.emit_initial)
            if kind=='window_delta':
                rule.setdefault('retrigger',typed.retrigger)
                for key in ('monotonic','coverage_policy'):rule.setdefault(key,getattr(typed.window_delta,key))
    for window,typed in zip(raw.get('windows',[]),plan.windows):
        for key in ('pre','post'):window.setdefault(key,_duration(getattr(typed,key+'_ns')))
        window.setdefault('merge',typed.merge)
    for calculation,typed in zip(raw.get('calculations',[]),plan.calculations):
        # 对象数本身没有覆盖率门槛；补齐默认值后仍应是一份合法配置。
        keys = ('unit','partial_policy') if typed.count_target is not None else ('unit','partial_policy','minimum_coverage')
        for key in keys:calculation.setdefault(key,getattr(typed,key))
        if typed.method is not None:calculation.setdefault('method',typed.method)
        if typed.ddof is not None:calculation.setdefault('ddof',typed.ddof)
    # 只列出该归约实际使用的默认值；例如 count 不接受 field，也不需要输入单位转换。
    for aggregation, typed in zip(raw.get('aggregations', []), plan.aggregations):
        aggregation.setdefault('unit', typed.unit)
        aggregation.setdefault('partial_policy', typed.partial_policy)
        if typed.field is not None:
            aggregation.setdefault('field', typed.field)
        if typed.operation == 'variance':
            aggregation.setdefault('ddof', typed.ddof)
        if typed.operation != 'count' and typed.source_kind == 'calculation':
            aggregation.setdefault('include_partial', typed.include_partial)
    # 变换可相互引用，计划按依赖排序；用名字找对应项，不能和原列表按位置配对。
    transform_plans = {item.name: item for item in plan.transforms}
    for transform in raw.get('transforms', ()):
        typed = transform_plans[transform['name']]
        transform.setdefault('unit', typed.output.unit)
        if typed.step_ns is not None:
            transform.setdefault('partial_policy', typed.partial_policy)
            transform.setdefault('minimum_coverage', typed.minimum_coverage)
            # 网格默认以该时钟的零点为起点。绝对时钟不能填入相对时长。
            zero = '1970-01-01T00:00:00+00:00' if plan.bindings.timebase.time_type.value == 'absolute' else '0s'
            transform.setdefault('origin', zero)
    for sequence,typed in zip(raw.get('sequences',[]),plan.sequences):sequence.setdefault('max_pending',typed.max_pending)
    intervals=raw.setdefault('intervals',{})
    intervals.setdefault('default',_interval(plan.intervals.default))
    # 每个消费者的驱动已由静态依赖确定；DBC周期仍须运行时读取，绝不虚构数值。
    if plan.intervals.resolved:
        intervals['overrides']={name:_interval(choice) for name,choice in plan.intervals.resolved}


def resolved_configuration(source, *, defaults=False):
    """展开预设并固定路径。参数: 输入配置、是否填默认。返回: 原生配置。异常: 配置/IO错误。

    原配置不写回；省略defaults时保原显式值。公开预设构建器只在独立副本执行。
    """
    from ..presets import expand_presets
    source=Path(source).absolute();document=load_configuration(source)
    from .imports import expand_document_imports
    document=expand_document_imports(document)
    name,plan=validate_document(document,source.parent,return_plan=True);raw=deepcopy(document.data)
    if name=='batch':
        if defaults:
            raw.setdefault('process_count',plan.process_count)
            for key in ('fail_fast','backend'):raw.setdefault(key,getattr(plan,key))
    else:
        from ..planning.config_groups import normalize_configuration
        raw=normalize_configuration(raw)
        if raw.get('presets'):
            expand_presets(raw,tuple(item.definition for item in plan.signals))
        raw.pop('presets',None)
        if defaults:_analysis_defaults(raw,plan)
    # 默认展开和预设内部片段统一还原成当前公共分组，不输出第二套配置语法。
    if name!='batch':
        from ..planning.config_groups import public_configuration
        raw=public_configuration(raw)
    # 使用词法绝对定位，保留..与符号链接的原路径解释；不stat/open业务文件。
    for owner,key in path_fields(raw,name):
        owner[key]=str((source.parent/Path(owner[key])).absolute())
    # 导出前复核全部有效字段；失败时还没有创建输出文件。
    validation=deepcopy(raw)
    if name!='batch':
        _signal_defaults(validation,plan)
    checked=parse_configuration(serialize_configuration(validation,'json'),format='json',source=str(source))
    validate_document(checked,source.parent)
    return raw


def resolve_configuration(source, *, output=None, format=None, defaults=False):
    """显示或导出有效配置。参数: 输入、可选新文件/格式/默认值。返回: 文本或Path。异常: 配置/IO错误。

    无输出文件时默认YAML写给调用者；有文件时扩展名定格式，显式格式不一致则拒绝。
    """
    chosen='yaml' if output is None else output_format(Path(output))
    if format is not None:
        if output is not None and format!=chosen:raise ValueError('--format与输出扩展名不一致')
        chosen=format
    raw=resolved_configuration(source,defaults=defaults)
    text=serialize_configuration(raw,chosen)
    return text if output is None else write_new_configuration(output,text)
