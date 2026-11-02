"""提供纯字节旧INI导入与显式配置文件的加载入口，不读取分析数据。

共享流程检查原生JSON mapping、保存身份、复制analysis并固定词法绝对路径，
按模式转换后调用公开AnalysisPlan.from_dict/validate_analysis_plan。配置语义错误返回
整份失败报告；API类型、文件I/O、内存与取消错误保持原生异常，不伪装成成功。
支持Sclicer single/start_only、显式slope/start_end迁移和当前消息legacy_sum；不承诺旧完整缓存等价。
"""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

from ..configuration import load_configuration, ConfigurationError, field_path_text
from ..configuration.diagnostics import locate_error, field_path_parts
from ..planning import AnalysisPlan, PlanValidationError, validate_analysis_plan
from ..planning.checks import absolute_path, require_json_value
from .ini import ImportProblem, parse_ini, problem
from .models import LegacyImportIssue, LegacyImportReport, LegacyImportResult
from .sclicer import convert_sclicer
from .legacy_sum import convert_legacy_sum

MODES = ('legacy_sum', 'sclicer_single', 'sclicer_start_only', 'sclicer_slope', 'sclicer_start_end')


def _arguments(content, mapping, mode, base_dir, source_name, device_label):
    """先核公开API类型，不把编程错误包成迁移拒绝。

    参数: 原公开入口参数。返回: None。异常: TypeError为原生类型错误；ValueError为未知mode。
    """
    if type(content) is not bytes or type(mapping) is not dict:
        raise TypeError('content需要bytes，mapping需要原生dict')
    if type(mode) is not str or type(source_name) is not str or type(device_label) is not str:
        raise TypeError('mode/source_name/device_label需要原生str')
    if not isinstance(base_dir, (str, Path)):
        raise TypeError('base_dir需要str或Path')
    if mode not in MODES:
        raise ValueError('未知导入mode：' + mode)


def _report(content, mode, source_name, device_label, mapping_identity, fields, issues, plan):
    """封装整份结果；参数: 本次原事实；返回: LegacyImportResult；异常: 资源错误原样传播。"""
    report = LegacyImportReport('success' if plan is not None else 'failed', mode, source_name,
        hashlib.sha256(content).hexdigest(), mapping_identity, device_label,
        tuple(fields), tuple(issues), None if plan is None else plan.identity)
    return LegacyImportResult(plan, report, content)


def _prepare_mapping(mapping, base):
    """检查完整mapping合同并复制为独立可修改分析配置。

    参数: mapping原生对象；base词法绝对目录。返回: (独立mapping, identity)。
    异常: ImportProblem/PlanValidationError为配置问题。目录输入会展开文件集合，缺省CAN声明会读取DBC。
    """
    require_json_value(mapping, '$')
    required = {'mapping_version', 'analysis'}
    if not required <= set(mapping) or set(mapping) - required - {'aliases', 'sections', 'path_base', 'io_policy'}:
        problem('invalid_mapping_shape', 'mapping', '$', 'mapping需要版本、analysis；aliases、sections、路径与IO策略可选')
    if type(mapping['mapping_version']) is not int or mapping['mapping_version'] != 1:
        problem('invalid_mapping_version', 'mapping', '$.mapping_version', '仅支持原生整数1')
    if mapping.get('path_base', 'mapping_directory') != 'mapping_directory' or mapping.get('io_policy', 'explicit_mapping') != 'explicit_mapping':
        problem('invalid_mapping_policy', 'mapping', '$', '路径与IO策略只支持mapping_directory及explicit_mapping')
    # 身份识别原mapping；路径固定和新节点仅发生于后续独立副本。
    encoded = json.dumps(mapping, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':'))
    identity = hashlib.sha256(encoded.encode('utf-8')).hexdigest()
    copied = json.loads(encoded)
    copied.setdefault('aliases',{})
    copied.setdefault('sections',{})
    analysis, aliases, sections = copied['analysis'], copied['aliases'], copied['sections']
    if type(analysis) is not dict or type(aliases) is not dict or type(sections) is not dict:
        problem('invalid_mapping_shape', 'mapping', '$', 'analysis/aliases/sections必须为对象')
    if 'imports' in analysis:
        problem('unresolved_imports','mapping','$.analysis.imports',
                '纯字典映射不读取公共定义；请用load_legacy_ini加载映射文件或先config resolve')
    from ..planning.config_groups import normalize_configuration
    analysis=copied['analysis']=normalize_configuration(analysis)
    for key in ('rules', 'windows', 'message_calculations', 'presets'):
        if key in analysis and (type(analysis[key]) is not list or analysis[key]):
            problem('nonempty_generated_nodes', 'mapping', '$.analysis.' + key, '导入前该数组必须缺省或为空')
    signals = analysis.get('signals')
    if type(signals) is not list:
        problem('missing_signal_mapping', 'mapping', '$.analysis.signals', '必须显式声明signals数组')
    from ..planning.signal_groups import signal_entries
    signals=analysis['signals']=[dict(item) for item,_ in signal_entries(signals)]
    names = set()
    for index, signal in enumerate(signals):
        if type(signal) is not dict:
            problem('invalid_signal_mapping', 'mapping', f'$.analysis.signals[{index}]', 'signal必须为对象')
        # 有效期可按用户周期或运行时DBC周期确定，由公共计划执行同一套检查。
        for key in ('name',):
            if key not in signal:
                problem('missing_signal_metadata', 'mapping', f'$.analysis.signals[{index}].{key}', '不得猜测信号声明：' + key)
        if type(signal['name']) is str:
            names.add(signal['name'])
    # 原字段只有一个候选才自动对应；明确aliases始终优先，不从表达式名称猜测。
    candidates={}
    for signal in signals:
        field=signal.get('field')
        original=field.get('signal') if type(field) is dict else field
        if type(original) is str:candidates.setdefault(original,[]).append(signal['name'])
    for original,choices in candidates.items():
        if len(choices)==1:aliases.setdefault(original,choices[0])
    for old, new in aliases.items():
        if type(new) is not str or new not in names or not old.strip():
            problem('invalid_alias', 'mapping', '$.aliases.' + old, '原名称须明确映射至analysis.signals别名')
    # 不同旧Name可由用户显式指向同一新信号；每个旧键仍只有一个明确目标。
    # JSON/YAML重复旧键由加载器拒绝，未知目标在上面拒绝，不能借此猜测字段关系。
    # 只固定公开来源路径，不递归猜测任意metadata中的路径文本。
    sources = analysis.get('sources')
    if type(sources) is not list:
        problem('missing_source_mapping', 'mapping', '$.analysis.sources', '必须显式声明sources数组')
    for index, source in enumerate(sources):
        if type(source) is not dict:
            problem('invalid_source_mapping', 'mapping', f'$.analysis.sources[{index}]', 'source必须为对象')
        # 导入与普通入口使用同一来源默认规则，不要求再次填写格式/时间/名称。
        from ..planning.input_defaults import source_defaults
        from ..planning.input_paths import FILE_SUFFIXES, expand_source_files
        # 既有单文件声明保持原字段形态；只有集合声明才输出展开后的paths。
        single_path = (type(source.get('path')) is str and Path(source['path']).suffix.lower() in FILE_SUFFIXES
                       and not source['path'].endswith(('/', '\\')))
        if source.get('source_type') != 'memory' and ('path' in source or 'paths' in source):
            paths, shifts = expand_source_files(source,base,f'$.analysis.sources[{index}]')
            source = dict(source, paths=[str(item) for item in paths])
            source.pop('path',None)
            if shifts is not None:
                source['offsets'] = list(shifts)
        source = source_defaults(source, index)
        if single_path and 'paths' in source:
            source['path'] = source.pop('paths')[0]
        sources[index] = source
        path = f'$.analysis.sources[{index}]'
        if 'path' in source:
            source['path'] = str(absolute_path(source['path'], base, path + '.path'))
        if 'paths' in source:
            if type(source['paths']) is not list:
                problem('invalid_source_mapping', 'mapping', path + '.paths', 'paths必须为数组')
            source['paths'] = [str(absolute_path(value, base, path + '.paths')) for value in source['paths']]
        if 'dbc_by_channel' in source:
            if type(source['dbc_by_channel']) is not dict:
                problem('invalid_source_mapping', 'mapping', path + '.dbc_by_channel', 'dbc_by_channel必须为对象')
            source['dbc_by_channel'] = {key: str(absolute_path(value, base, path + '.dbc_by_channel.' + key))
                                        for key, value in source['dbc_by_channel'].items()}
    # 仅缺省声明/定位才编译来源和信号；完整旧映射不新增DBC访问。
    if any('dtype' not in item or 'unit' not in item or 'source' not in item
           or type(item.get('field')) is dict and 'channel' not in item['field'] for item in signals):
        from ..planning.inputs import parse_sources, parse_signals
        source_models=parse_sources(sources,base)
        typed=parse_signals(signals,source_models)
        for raw,model in zip(signals,typed):
            raw.setdefault('dtype',model.definition.dtype.value)
            raw.setdefault('unit',model.definition.unit)
            raw.setdefault('source',model.definition.source)
            if model.definition.choices:raw.setdefault('choices',[list(pair) for pair in model.definition.choices])
            if type(raw.get('field')) is dict:
                source=next(s for s in source_models if s.name==model.definition.source)
                raw['field'].setdefault('channel',source.config.channel + 1)
    return copied, identity


def import_legacy_ini(content: bytes, mapping: dict, *, mode, base_dir,
                      source_name='input.ini', device_label='pending') -> LegacyImportResult:
    """从原INI字节和显式mapping生成完整静态计划或整份拒绝报告。

    参数: content为原bytes，mapping为JSON对象；mode选择合同模式；base_dir
    为mapping目录；source_name/device_label只标识来源。返回: LegacyImportResult，
    original_ini保同一bytes，失败plan为None。异常: API类型/未知mode、OSError、
    MemoryError及取消保持原对象；配置语义与UTF-8错误进入report，不返回部分计划。
    """
    _arguments(content, mapping, mode, base_dir, source_name, device_label)
    fields, issues, identity = [], [], None
    try:
        try:
            text = content.decode('utf-8-sig')
        except UnicodeDecodeError as error:
            problem('invalid_ini_encoding', 'ini', '$', str(error))
        base = Path(base_dir).absolute()
        try:
            copied, identity = _prepare_mapping(mapping, base)
        except PlanValidationError as error:
            problem(error.code, 'mapping', error.path,
                error.message+('；修正：'+error.hint if error.hint else ''))
        parser, headers = parse_ini(text, fields, preserve_case=mode == 'legacy_sum')
        if 'sections' not in mapping:
            if mode in ('sclicer_single','sclicer_start_only','sclicer_start_end'):
                for number,section in enumerate((s for s in parser.sections() if s.startswith('TRIGGER_')),1):
                    item=dict(name=f'trigger_{number}',window=f'window_{number}')
                    if mode=='sclicer_start_end':item.update(semantics='start_end_timeout-v1',emit_initial=False)
                    copied['sections'][section]=item
            else:
                problem('missing_section_parameters','mapping','$.sections','该模式仍需提供计算单位或slope参数，不能从段名猜测')
        analysis = copied['analysis']
        if mode == 'legacy_sum':
            convert_legacy_sum(parser, headers, copied, analysis, fields, issues)
        else:
            convert_sclicer(parser, headers, copied, analysis, fields, issues, mode)
        try:
            from ..planning.config_groups import public_configuration
            plan = AnalysisPlan.from_dict(public_configuration(analysis), base_dir=base)
            validation = validate_analysis_plan(plan)
        except PlanValidationError as error:
            # 新条件错误仍回指原字段；其他计划配置错误明确归mapping，不制造INI行号。
            original = next((item for item in fields if item.target == error.path), None)
            problem(error.code, 'ini' if original else 'mapping', original.path if original else error.path,
                    error.message+('；修正：'+error.hint if error.hint else ''),
                    original.line if original else None, original.column if original else None)
        if not validation.valid or not validation.execution_ready:
            problem('plan_unavailable', 'plan', '$', '; '.join(validation.errors))
        for warning in validation.warnings:
            issues.append(LegacyImportIssue('static_unverified', 'plan', '$', warning, level='warning'))
        return _report(content, mode, source_name, device_label, identity, fields, issues, plan)
    except ImportProblem as error:
        issues.append(error.issue)
        return _report(content, mode, source_name, device_label, identity, fields, issues, None)



def load_legacy_ini(ini_path, mapping_path, *, mode, device_label='pending') -> LegacyImportResult:
    """只读INI、映射及显式一层公共定义，来源路径基准按实际声明文件确定。

    参数: ini_path/mapping_path为str或Path；mode/device_label同字节API。
    返回: LegacyImportResult，非法JSON/YAML给mapping定位。异常: API类型、未知mode、
    文件读取OSError、MemoryError及取消原样传播；按声明展开目录及读取缺省信号所需DBC，不读取业务报文。
    """
    if not isinstance(ini_path, (str, Path)) or not isinstance(mapping_path, (str, Path)):
        raise TypeError('配置路径需要str或Path')
    # API参数先校验，不能在明显编程错误下先触发文件读取。
    _arguments(b'', {}, mode, mapping_path, str(ini_path), device_label)
    ini, mapping_file = Path(ini_path), Path(mapping_path).absolute()
    content = ini.read_bytes()
    try:
        document = load_configuration(mapping_file)
        from ..configuration.imports import expand_document_imports
        document = expand_document_imports(document)
        mapping = document.data
    except PlanValidationError as error:
        location=error.location
        issue=LegacyImportIssue(error.code,'mapping',error.path,str(error),
            None if location is None else location.line,None if location is None else location.column)
        return _report(content,mode,str(ini),device_label,None,(),(issue,),None)
    except ConfigurationError as error:
        # 文件IO沿用导入API的原生异常合同；语法错误则进入可发布的迁移报告。
        if error.code=='load_error' and isinstance(error.__cause__,OSError):
            raise error.__cause__
        syntax_code='invalid_mapping_yaml' if mapping_file.suffix.lower() in ('.yaml','.yml') else 'invalid_mapping_json'
        code={'duplicate_key':'duplicate_mapping_key','nonfinite_number':'invalid_mapping_number',
              'invalid_number':'invalid_mapping_number','unsupported_format':'unsupported_mapping_format'}.get(error.code,syntax_code)
        location=error.location
        issue=LegacyImportIssue(code,'mapping',field_path_text(error.field_path),str(error),
            None if location is None else location.line,None if location is None else location.column)
        return _report(content,mode,str(ini),device_label,None,(),(issue,),None)
    if type(mapping) is not dict:
        return _report(content, mode, str(ini), device_label, None, (),
            (LegacyImportIssue('invalid_mapping_shape', 'mapping', '$', 'mapping配置根必须为对象'),), None)
    result=import_legacy_ini(content, mapping, mode=mode, base_dir=mapping_file.parent,
                             source_name=str(ini), device_label=device_label)
    # 只补映射原文的错误位置。INI字段的行列已由迁移器确定，不能套映射位置。
    issues=[]
    for issue in result.report.issues:
        parts=field_path_parts(issue.path)
        if issue.origin!='mapping' or parts is None:
            issues.append(issue)
            continue
        # 转换后计划路径从analysis内部开始，原mapping校验路径则已带前缀。
        if parts and parts[0] not in mapping and ('analysis',*parts[:-1]) in document.locations:
            parts=('analysis',*parts)
        error=locate_error(PlanValidationError(field_path_text(parts),issue.message,issue.code),document)
        location=error.location
        issues.append(replace(issue,path=error.path,message=str(error),
            line=None if location is None else location.line,column=None if location is None else location.column))
    return replace(result,report=replace(result.report,issues=tuple(issues)))
