"""把当前配置的就地分组送入既有解析器，不改变时间或数值规则。

输入为JSON配置副本，输出独立副本。reader集中读取参数，conversion集中换算，
interval跟随实际消费者，scope对象明确引用规则或窗口。仅复制配置，不读输入、
不推断设备同步、不生成逐帧追溯。反向函数用于配置工具输出当前唯一公共形式。
"""
from copy import deepcopy
from functools import wraps
import re
from .checks import object_at, array_at, text_at, timezone_at, PlanValidationError

CONVERSION = ('input_unit', 'scale', 'offset')
READER_FLAT = ('encoding', 'delimiter', 'missing_values', 'decode_scope', 'input_check')
NODES = ('rules', 'windows', 'calculations', 'sequences')


def public_errors(function):
    """将内部字段错误还原到用户声明位置。参数: 计划构建方法。返回: 包装方法。异常: 原PlanValidationError。

    不改变错误代码和原因，不读取或保存输入；结构阶段对旧名的拒绝保留旧名位置。
    """
    @wraps(function)
    def checked(cls, config, *args, **kwargs):
        """调用原解析器，仅在错误退出时修正已归组字段的路径。"""
        try:
            return function(cls, config, *args, **kwargs)
        except PlanValidationError as error:
            if error.code == 'unknown_field' or type(config) is not dict:
                raise
            path = error.path
            path = re.sub(r'(\$\.sources\[\d+\])\.(?:parser|reader_options)(?=\.|$)', r'\1.reader', path)
            path = re.sub(r'(\$\.sources\[\d+\])\.(encoding|delimiter|missing_values|decode_scope|input_check)(?=\.|$)', r'\1.reader.\2', path)
            path = re.sub(r'(\$\.signals\[\d+\](?:\.signals\[\d+\])?)\.(input_unit|scale|offset)(?=\.|$)', r'\1.conversion.\2', path)
            path = re.sub(r'(\.time)\.origin(?=\.|$)', r'\1.clock', path)
            path = re.sub(r'(\.resampling)\.origin(?=\.|$)', r'\1.start', path)
            path = path.replace('$.outputs.can_frames.timezone_offset_minutes', '$.outputs.can_frames.timezone')
            path = re.sub(r'(\$\.outputs\.(?:can_frames|signal_csv))\.window(?=\.|$)', r'\1.scope.window', path)
            match = re.match(r'^\$\.intervals\.overrides\.([^\.]+)(.*)$', path)
            if match:
                for section in NODES:
                    nodes = config.get(section, [])
                    if type(nodes) is not list: continue
                    for index, node in enumerate(nodes):
                        if type(node) is dict and node.get('name') == match[1] and 'interval' in node:
                            path = f'$.{section}[{index}].interval' + match[2]
            error.path = path
            error.refresh_text()
            raise
    return checked


def _leaves(signals, path='$.signals'):
    """遍历叶信号及声明路径。参数: 数组。返回: (dict,path)。异常: 错误数组/对象。"""
    for index, item in enumerate(array_at(signals, path)):
        child_path = f'{path}[{index}]'
        if type(item) is not dict:
            raise PlanValidationError(child_path, '信号声明必须为对象')
        if 'signals' in item:
            yield from _leaves(item['signals'], child_path + '.signals')
        else:
            yield item, child_path


def normalize_configuration(config):
    """解析当前公共分组。参数: 已验证JSON字典。返回: 独立内部字典。异常: 公共结构错误。

    只接受当前拼写，旧扁平参数明确拒绝；内部parser/reader_options等仅供既有
    解析器消费，不作为第二套用户配置入口。调用应在预设展开之前。
    """
    root = deepcopy(config)
    for index, source in enumerate(array_at(root['sources'], '$.sources')):
        path = f'$.sources[{index}]'
        if type(source) is not dict:
            raise PlanValidationError(path, '来源必须为对象')
        for key in ('parser', 'reader_options', *READER_FLAT):
            if key in source:
                raise PlanValidationError(path + '.' + key, '读取参数请放在reader对象内', 'unknown_field')
        if 'reader' in source:
            reader = dict(object_at(source.pop('reader'), path + '.reader', (),
                (*READER_FLAT, 'decode_policy', 'version', 'layout', 'time_format', 'id_base',
                 'length_base', 'channel_origin', 'payload_style', 'rollover_min_drop')))
            # 信号表读取参数和CAN解码参数分别交给各自的原校验器。
            for key in ('decode_scope', 'input_check'):
                if key in reader: source[key] = reader.pop(key)
            if 'decode_policy' in reader:
                source['reader_options'] = {'decode_policy': reader.pop('decode_policy')}
            if source.get('source_type') == 'signal_csv':
                source.update(reader)
            elif reader:
                source['parser'] = reader
        clock = source.get('time')
        if type(clock) is dict and 'origin' in clock:
            raise PlanValidationError(path + '.time.origin', '来源时间基准名称请使用clock', 'unknown_field')
        if type(clock) is dict and 'clock' in clock:
            clock['origin'] = clock.pop('clock')
        if type(clock) is dict and 'timezone_offset_minutes' in clock:
            raise PlanValidationError(path + '.time.timezone_offset_minutes',
                '时区统一使用timezone，例如+08:00', 'unknown_field')
    for signal, path in _leaves(root['signals']):
        for key in CONVERSION:
            if key in signal:
                raise PlanValidationError(path + '.' + key, '信号换算请放在conversion对象内', 'unknown_field')
        if 'conversion' in signal:
            signal.update(object_at(signal.pop('conversion'), path + '.conversion', (), CONVERSION))
    intervals = dict(object_at(root.get('intervals', {}), '$.intervals', (), ('default',)))
    overrides = {}
    for section in NODES:
        for index, node in enumerate(array_at(root.get(section, []), '$.' + section)):
            path = f'$.{section}[{index}]'
            if type(node) is not dict:
                raise PlanValidationError(path, '节点必须为对象')
            if 'interval' in node:
                name = text_at(node.get('name'), path + '.name', identifier=True)
                if name in overrides:
                    raise PlanValidationError(path + '.name', '间隔消费者名称重复')
                # 原间隔解析器随后检查模式、驱动、正周期和消费者是否适用。
                overrides[name] = node.pop('interval')
            if section == 'calculations' and 'scope' in node:
                scope = node['scope']
                if scope == 'session':
                    continue
                scope = object_at(scope, path + '.scope', (), ('rule', 'window'))
                if len(scope) != 1:
                    raise PlanValidationError(path + '.scope', 'scope需要且只能引用一个rule或window')
                key = next(iter(scope))
                target = text_at(scope[key], path + '.scope.' + key, identifier=True)
                node['scope'] = ('event:' if key == 'rule' else 'segment:') + target
    if overrides: intervals['overrides'] = overrides
    if intervals or 'intervals' in root: root['intervals'] = intervals
    for kind in ('signal_csv', 'can_frames'):
        outputs = root.get('outputs', {})
        output = outputs.get(kind) if type(outputs) is dict else None
        if type(output) is not dict: continue
        path = '$.outputs.' + kind
        if kind == 'can_frames':
            if 'timezone_offset_minutes' in output:
                raise PlanValidationError(path + '.timezone_offset_minutes', '时区请使用timezone，例如+08:00', 'unknown_field')
            if 'timezone' in output:
                zone = timezone_at(output.pop('timezone'), path + '.timezone')
                offset = None if zone is None else zone.utcoffset(None)
                if zone is not None and offset is None:
                    raise PlanValidationError(path + '.timezone', '原帧导出需要UTC或固定时区，例如+08:00')
                output['timezone_offset_minutes'] = None if offset is None else int(offset.total_seconds() // 60)
        grid = output.get('resampling')
        if type(grid) is dict:
            if 'origin' in grid:
                raise PlanValidationError(path + '.resampling.origin', '采样网格起点请使用start', 'unknown_field')
            if 'start' in grid: grid['origin'] = grid.pop('start')
        if 'window' in output:
            raise PlanValidationError(path + '.window', '窗口引用请写scope: {window: 名称}', 'unknown_field')
        scope = output.get('scope', 'session')
        if scope == 'session': continue
        scope = object_at(scope, path + '.scope', (), ('window', 'windows'))
        if len(scope) != 1:
            raise PlanValidationError(path + '.scope', '导出scope需要一个window引用或windows: all')
        output['scope'] = 'segments'
        if 'window' in scope:
            output['window'] = text_at(scope['window'], path + '.scope.window', identifier=True)
        elif kind != 'can_frames' or scope['windows'] != 'all':
            raise PlanValidationError(path + '.scope.windows', '仅原帧导出支持windows: all')
    return root


def public_configuration(config):
    """把生成器内部结构转成当前公共配置。参数: 配置字典。返回: 独立字典。异常: 结构错误。

    不读取文件，不改变自由metadata或业务值；已使用新分组的内容原样保留。
    用于预设展开、INI导入和resolve，不能用作接受旧用户配置的兼容入口。
    """
    root = deepcopy(config)
    for source in root.get('sources', []):
        reader = dict(source.get('reader', {}))
        for key in ('parser', 'reader_options'):
            reader.update(source.pop(key, {}))
        for key in READER_FLAT:
            if key in source: reader[key] = source.pop(key)
        if reader: source['reader'] = reader
        clock = source.get('time', {})
        if 'origin' in clock: clock['clock'] = clock.pop('origin')
        if 'timezone_offset_minutes' in clock:
            minutes = clock.pop('timezone_offset_minutes')
            if type(minutes) is not int or not -1439 <= minutes <= 1439:
                raise PlanValidationError('$.sources.time.timezone', '固定时区分钟数无效')
            clock['timezone'] = ('+' if minutes >= 0 else '-') + f'{abs(minutes)//60:02}:{abs(minutes)%60:02}'
    for signal, _ in _leaves(root.get('signals', [])):
        conversion = dict(signal.get('conversion', {}))
        for key in CONVERSION:
            if key in signal: conversion[key] = signal.pop(key)
        if conversion: signal['conversion'] = conversion
    intervals = root.get('intervals', {})
    overrides = intervals.pop('overrides', {}) if type(intervals) is dict else {}
    for section in NODES:
        for node in root.get(section, []):
            if node.get('name') in overrides:
                node['interval'] = overrides.pop(node['name'])
            scope = node.get('scope')
            if section == 'calculations' and type(scope) is str and ':' in scope:
                kind, target = scope.split(':', 1)
                if kind in ('event', 'segment'):
                    node['scope'] = {'rule' if kind == 'event' else 'window': target}
    # 无对应节点不能丢弃声明，让原错误继续可见而不是静默删配置。
    if overrides: intervals['overrides'] = overrides
    for kind in ('signal_csv', 'can_frames'):
        outputs = root.get('outputs', {})
        output = outputs.get(kind) if type(outputs) is dict else None
        if type(output) is not dict: continue
        if kind == 'can_frames' and 'timezone_offset_minutes' in output:
            minutes = output.pop('timezone_offset_minutes')
            output['timezone'] = None if minutes is None else ('+' if minutes >= 0 else '-') + f'{abs(minutes)//60:02}:{abs(minutes)%60:02}'
        grid = output.get('resampling')
        if type(grid) is dict and 'origin' in grid: grid['start'] = grid.pop('origin')
        if output.get('scope') != 'segments': continue
        window = output.pop('window', None)
        output['scope'] = {'windows': 'all'} if window is None else {'window': window}
    return root
