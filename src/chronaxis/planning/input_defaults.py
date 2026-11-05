"""补齐来源的常用声明，只有唯一候选时自动选择引用。

输入为已检查JSON结构的配置；输出独立字典或来源名称。不打开数据/DBC，
不改输入值和时间戳。相对时间缺省采用来源专属基准，不声称多来源已经同步。
"""

# 仅用路径后缀识别自描述的CAN文件；格式正文仍由原读取器严格检查。
from pathlib import Path
from .checks import PlanValidationError, array_at, object_at, text_at


def source_defaults(raw, index, *, inferred_type=None):
    """补来源名、ASC/BLF格式及时间默认值，不修改调用方字典。

    参数: raw为单来源字典，index为零基来源序号；inferred_type为已编译来源类型。
    返回: 新字典；已有计划的调用方可避免重复展开目录。
    异常: PlanValidationError表示未知格式、显式空时间或非法名称。
    """
    # 自动名只作当前计划内定位，重名由原来源解析器统一拒绝。
    result = dict(raw)
    path = f'$.sources[{index}]'
    result.setdefault('name', f'source_{index + 1}')
    name = text_at(result['name'], path + '.name', identifier=True)
    if inferred_type is not None and ('source_type' not in result or result['source_type'] == 'asc_or_blf'):
        result['source_type'] = inferred_type
    if inferred_type is None and ('source_type' not in result or result['source_type'] == 'asc_or_blf'):
        # 这里只识别明确文件后缀；目录展开由文件输入节点实施，CSV必须声明含义。
        paths = [result['path']] if 'path' in result else array_at(result.get('paths', []), path + '.paths')
        suffixes = {Path(text_at(item, f'{path}.paths[{i}]')).suffix.lower() for i, item in enumerate(paths)}
        if not paths or not suffixes <= {'.asc', '.blf'}:
            raise PlanValidationError(path + '.source_type',
                '无法唯一识别ASC/BLF格式；CSV或内存输入请明确source_type')
        result['source_type'] = ('can_asc' if suffixes == {'.asc'} else
            'can_blf' if suffixes == {'.blf'} and 'offsets' not in result else 'asc_or_blf')
    # 不用“or {}”吞掉显式null；用户输入的错误必须仍然报出。
    clock = dict(object_at(result.get('time', {}), path + '.time', (),
                          ('time_type', 'unit', 'origin', 'offset', 'timezone', 'timezone_offset_minutes')))
    clock.setdefault('time_type', 'relative')
    if result['source_type'] in ('can_blf', 'can_asc', 'asc_or_blf', 'memory'):
        clock.setdefault('unit', 's')
    if clock['time_type'] == 'relative':
        # 缺省基准带来源名，不让独立采集的来源因共同默认字符串而被视为已同步。
        clock.setdefault('origin', '__source_' + name)
    result['time'] = clock
    return result


def source_reference(raw, sources, path, *, can_only=False):
    """取显式来源名，或选择唯一适用来源；多候选不选第一项。

    参数: raw为含可选source的对象，sources为来源计划序列，path为对象位置，
        can_only限定原始CAN来源。返回: 来源名称字符串。
    异常: PlanValidationError表示无候选、多候选或非法显式名称。
    """
    from .diagnostic_collection import current_collection
    active = current_collection()
    if active is not None and active.invalid_sources:
        if 'source' not in raw or (type(raw.get('source')) is str and raw['source'] in active.invalid_sources):
            raise PlanValidationError(path + '.source', '候选来源声明无效，修复后再确定信号来源', 'blocked_dependency')
    if 'source' in raw:
        # 显式null/空串不表示自动，原名称检查仍生效。
        return text_at(raw['source'], path + '.source', identifier=True)
    candidates = [item.name for item in sources if not can_only or
                  item.source_type in ('can_blf', 'can_asc', 'asc_or_blf', 'raw_can_csv')]
    if len(candidates) != 1:
        raise PlanValidationError(path + '.source', '请指定source；适用来源：' + ', '.join(candidates))
    return candidates[0]
