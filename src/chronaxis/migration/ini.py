"""静态读取受支持INI语法并保字段位置，不实例化旧ConfigManager。

输入为已解码文本和本次局部报告字段列表；输出公开ConfigParser对象及原段序。
Sclicer保持旧option小写规则，ChrgInfo保持大小写及仅分号注释。预扫描拒DEFAULT、插值、重复和多行继承，
随后仍用标准ConfigParser核语法；不读外部INI、DBC、日志或环境变量。
"""

import configparser
import re
from dataclasses import replace

from .models import LegacyFieldMapping, LegacyImportIssue


class ImportProblem(Exception):
    """仅在本包内部传递一条配置语义问题，不接管I/O或取消异常。"""

    def __init__(self, issue: LegacyImportIssue):
        """保原问题；参数: issue；返回: None；异常: 无。"""
        self.issue = issue
        super().__init__(issue.message)


def problem(code, origin, path, message, line=None, column=None):
    """抛有限语义问题；参数: 机器码及定位；返回: 无；异常: ImportProblem。"""
    raise ImportProblem(LegacyImportIssue(code, origin, path, message, line, column))


def field_path(section, key):
    """生成稳定INI位置；参数: 原段名/规范键；返回: str；异常: 无。"""
    return '[' + section + '].' + key


def locate(fields, section, key=None):
    """查原字段定位；参数: 已收集字段/段/可选键；返回: 行列tuple；异常: 无。"""
    prefix = '[' + section + '].'
    for item in fields:
        matches = item.path == field_path(section, key) if key is not None else item.path.startswith(prefix)
        if matches:
            return item.line, item.column
    return None, None


def mark(fields, section, key, target, status='mapped', message='按显式映射转换'):
    """更新本次局部字段去向；参数: 字段列表和处理事实；返回: None；异常: 无。"""
    for index, item in enumerate(fields):
        if item.path == field_path(section, key):
            fields[index] = replace(item, target=target, status=status, message=message)
            return


def parse_ini(text, fields, *, preserve_case=False):
    """预扫有限INI位置并用标准解析器复核，不允许多行或隐式继承。

    参数: text原文本；fields本次输出列表；preserve_case选择ChrgInfo大小写及分号口径。
    返回: (ConfigParser, 段名到头部行号dict)。异常: ImportProblem为配置语法错误；
    MemoryError/取消原样传播。Sclicer无inline注释；ChrgInfo的井号不是INI注释。
    """
    headers, seen, section, previous_indent = {}, set(), None, None
    for line_number, line in enumerate(text.splitlines(), 1):
        if preserve_case:
            # 与旧ConfigParser相同：分号在行首或紧随空白时开始inline注释。
            # 不把a;b误截为a，也不因注释中的%(...)误报有效字段插值。
            for position, char in enumerate(line):
                if char == ';' and (position == 0 or line[position - 1].isspace()):
                    line = line[:position]
                    break
        stripped = line.strip()
        comments = (';',) if preserve_case else ('#', ';')
        if not stripped or stripped.startswith(comments):
            continue
        header = re.fullmatch(r'\[([^\]]+)\]\s*(?:[;#].*)?', stripped)
        if header:
            section = header.group(1)
            if section == 'DEFAULT':
                problem('unsupported_default', 'ini', '[DEFAULT]', '不支持DEFAULT继承', line_number, 1)
            if section in headers:
                problem('duplicate_section', 'ini', '[' + section + ']', '重复INI段', line_number, 1)
            headers[section], previous_indent = line_number, None
            continue
        indent = len(line) - len(line.lstrip())
        if previous_indent is not None and indent > previous_indent:
            problem('unsupported_multiline', 'ini', '[' + str(section) + ']',
                    '不支持INI多行续值', line_number, indent + 1)
        match = re.fullmatch(r'([^:=]+?)\s*[:=]\s*(.*)', stripped)
        if section is None or match is None:
            problem('invalid_ini', 'ini', '[' + str(section) + ']', '需要段内单行key=value', line_number, 1)
        original_key, value = match.group(1).strip(), match.group(2).strip()
        key = original_key if preserve_case else original_key.lower()
        path = field_path(section, key)
        if not key or (section, key) in seen:
            problem('duplicate_option', 'ini', path, '字段为空或按旧大小写规则重复', line_number, indent + 1)
        seen.add((section, key))
        fields.append(LegacyFieldMapping('ini', path, value, line_number, indent + 1,
                                         None, 'pending', '尚未转换'))
        if '%(' in value or '${' in value:
            problem('unsupported_interpolation', 'ini', path, '不支持插值，须提供显式值', line_number, indent + 1)
        previous_indent = indent
    parser = configparser.ConfigParser(interpolation=None, strict=True,
        comment_prefixes=(';',) if preserve_case else ('#', ';'),
        inline_comment_prefixes=(';',) if preserve_case else None)
    if preserve_case:
        parser.optionxform = str
    try:
        parser.read_string(text)
    except configparser.Error as error:
        problem('invalid_ini', 'ini', '$', str(error), getattr(error, 'lineno', None), 1)
    if not headers:
        problem('empty_ini', 'ini', '$', 'INI没有可转换段')
    return parser, headers
