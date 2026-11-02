"""将文件、目录或通配符展开为有序输入，不读取报文内容。

明确文件列表保持用户顺序；每个目录或通配符内部采用自然排序。
只枚举显式请求的目录，不递归追踪子目录；递归必须通过**通配符提出。
展开最多4096项，空匹配及无效路径报配置错误，不悄悄跳过缺失目录。
"""

from glob import iglob
from pathlib import Path
import re

from .checks import PlanValidationError, absolute_path, array_at, coordinate_at, object_at, text_at

# 明确后缀的文件只做词法定位，保持现有静态配置不访问业务文件的行为。
FILE_SUFFIXES = frozenset(('.asc', '.blf', '.csv', '.txt'))
SOURCE_SUFFIXES = {'can_blf': {'.blf'}, 'can_asc': {'.asc'},
                   'raw_can_csv': {'.csv', '.txt'}, 'signal_csv': {'.csv', '.txt'}}
MAX_INPUT_FILES = 4096


def natural_path_key(path):
    """产生稳定自然序键，使file2排在file10前。

    参数: path为Path。返回: 数字/文字分段键及原路径平局键。
    异常: 无主动异常；不访问文件系统。
    """
    text = str(path)
    # 类型标签避免数字与文字直接比较；补原文本使01/1及大小写平局可复现。
    parts = tuple((1, int(part)) if part.isdigit() else (0, part.casefold())
                  for part in re.split(r'(\d+)', text))
    return parts, text.casefold(), text


def expand_source_files(raw, base, where):
    """按声明展开来源路径；目录只取该来源支持的格式。

    参数: raw为来源字典，base为配置文件目录，where为来源错误位置。
    返回: (绝对Path元组, 可选逐文件偏移字符串元组)。异常: PlanValidationError表示缺项、空匹配或超限；
        OSError由目录读取产生并转换为带配置位置的错误。
    副作用: 仅目录/通配符声明枚举文件名；明确文件不stat、不读数据内容。
    """
    if ('path' in raw) == ('paths' in raw):
        raise PlanValidationError(where, 'path与paths必须且只能提供一个')
    key = 'path' if 'path' in raw else 'paths'
    value = raw[key]
    entries = [value] if type(value) in (str, dict) else array_at(value, where + '.' + key)
    if not entries:
        raise PlanValidationError(where + '.' + key, '至少需要一个输入文件或目录')
    allowed = SOURCE_SUFFIXES.get(raw.get('source_type'), {'.asc', '.blf'})
    result, shifts, has_shifts = [], [], False
    for index, entry in enumerate(entries):
        location = f'{where}.{key}[{index}]'
        # 文件自己的偏移跟在同一条声明内，展开目录时该偏移作用于其中各文件。
        shift = '0s'
        if type(entry) is dict:
            item = object_at(entry, location, ('path',), ('offset',))
            text = text_at(item['path'], location + '.path')
            if 'offset' in item:
                coordinate_at(item['offset'], location + '.offset')
                shift = item['offset']
                has_shifts = True
        else:
            text = text_at(entry, location)
        target = absolute_path(text, base, location)
        # 仅*和?启动通配符模式，普通文件名中的方括号保持字面含义。
        wildcard = any(char in text for char in '*?')
        # 常规文件不访问磁盘；目录名像文件时可用末尾分隔符明确目录含义。
        if not wildcard and target.suffix.lower() in FILE_SUFFIXES and not text.endswith(('/', '\\')):
            selected = [target]
        else:
            selected = []
            try:
                candidates = (Path(item) for item in iglob(str(target), recursive='**' in text)) if wildcard else target.iterdir()
                for candidate in candidates:
                    if candidate.suffix.lower() in allowed and candidate.is_file():
                        selected.append(candidate)
                        if len(result) + len(selected) > MAX_INPUT_FILES:
                            raise PlanValidationError(location, '输入文件超过4096项')
            except OSError as error:
                raise PlanValidationError(location, '无法枚举输入目录：' + str(error)) from error
            if not selected:
                raise PlanValidationError(location, '目录或通配符没有匹配的输入文件')
            selected.sort(key=natural_path_key)
        # 不重排显式列表、不合并不同声明项，也不因内容相同而删除真实文件。
        result.extend(selected)
        shifts.extend([shift] * len(selected))
        if len(result) > MAX_INPUT_FILES:
            raise PlanValidationError(location, '输入文件超过4096项')
    if has_shifts and 'offsets' in raw:
        raise PlanValidationError(where, '文件内offset与来源offsets不能同时填写')
    return tuple(result), tuple(shifts) if has_shifts else None


def expand_input_paths(raw, base, where):
    """只取展开文件路径，供无需文件偏移的调用方使用。

    参数: 来源配置、基准目录、错误位置。返回: Path元组。
    异常: 与expand_source_files一致；目录扫描只执行一次。
    """
    return expand_source_files(raw, base, where)[0]


def source_path_fields(source, where='$.sources'):
    """枚举文件声明中的路径文字，供转换/导入工具固定路径基准。

    参数: source为来源字典，where为错误位置。返回: (容器,键)迭代器。
    异常: PlanValidationError为错误结构。不扫描目录，不改变offset或其他元数据。
    """
    for key in ('path', 'paths'):
        if key not in source:
            continue
        value = source[key]
        if type(value) is str:
            yield source, key
            continue
        # 每项可以是路径文字或带自己偏移的文件声明，工具不能把对象转成字符串。
        entries = [value] if type(value) is dict else array_at(value, where + '.' + key)
        for index, item in enumerate(entries):
            if type(item) is dict:
                object_at(item, f'{where}.{key}[{index}]', ('path',), ('offset',))
                yield item, 'path'
            else:
                text_at(item, f'{where}.{key}[{index}]')
                yield entries, index
