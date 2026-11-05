"""把同一报文的集中声明展开为既有信号绑定，不增加运行时分组或重复读取。"""
from .diagnostic_collection import usable_node, collect_node_error
from .checks import array_at, object_at, choice_at, text_at, model_at, PlanValidationError


SHARED = ('period', 'valid_for', 'same_time_policy')
LOCATOR = ('frame_id', 'channel', 'is_extended', 'is_fd')


def signal_entries(value):
    """按原顺序提供信号副本和声明路径。参数: signals数组。返回: 迭代器。异常: 结构错误。

    集中项只允许声明一套报文定位；子项可覆盖周期、有效期和同刻策略，
    不能把另一个报文塞进本组。没有额外组名、引用或运行时对象。
    """
    for index, raw in enumerate(array_at(value, '$.signals')):
        path = f'$.signals[{index}]'
        if type(raw) is not dict or 'signals' not in raw:
            yield raw, path
            continue
        group = object_at(raw, path, ('frame_id', 'signals'),
                          ('source', 'channel', 'is_extended', 'is_fd') + SHARED)
        children = array_at(group['signals'], path + '.signals')
        if not children:
            raise PlanValidationError(path + '.signals', '报文组至少需要一个信号')
        # 即使所有子项都覆盖共享参数，也不能把填写错误当成未提供。
        from .signal_validity import declared_valid_for
        declared_valid_for(group, path, dbc_available=True)
        if 'same_time_policy' in group:
            choice_at(group['same_time_policy'], ('error', 'last_by_sequence'), path + '.same_time_policy')
        common = {key: group[key] for key in SHARED if key in group}
        if 'source' in group:
            common['source'] = group['source']
        locator = {key: group[key] for key in LOCATOR if key in group}
        from ..legacy.records import field_from_dict
        # 预检使用转换后的副本；展开给子项的locator仍保留用户1基编号。
        from .channels import channel_index
        checked = dict(locator, signal='_group_check')
        checked['channel'] = channel_index(locator['channel'], path + '.channel') if 'channel' in locator else 0
        model_at(field_from_dict, path, checked)
        for child_index, child in enumerate(children):
            child_path = f'{path}.signals[{child_index}]'
            if not usable_node(child_path, child):
                continue
            try:
                child_path = f'{path}.signals[{child_index}]'
                if type(child) is not dict:
                    raise PlanValidationError(child_path, '信号必须为对象')
                forbidden = set(child) & ({'field', 'source', 'signals'} | set(LOCATOR))
                if forbidden:
                    raise PlanValidationError(child_path, '组内信号不能重复声明报文定位：' + ', '.join(sorted(forbidden)))
                if 'signal' not in child:
                    raise PlanValidationError(child_path + '.signal', '需要DBC信号名称')
                text_at(child['signal'], child_path + '.signal')
                expanded = dict(common, **child)
                expanded['field'] = dict(locator, signal=expanded.pop('signal'))
                yield expanded, child_path
            except PlanValidationError as error:
                collect_node_error(error, child_path, child)


def declared_signals(value):
    """遍历原声明的叶信号供默认展开使用。参数: 已校验数组。返回: 原字典迭代器。异常: 无。"""
    for item in value:
        if 'signals' in item:
            yield from item['signals']
        else:
            yield item
