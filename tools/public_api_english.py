"""将英文API的机器事实与同基线中文页同步，保留已审阅英文行为说明。

签名、类型、必填、默认值和源码定位不分别翻译维护。缺少参数说明时直接失败，
避免新增参数被旧译文静默丢掉；新增子模块使用独立双语说明来源。
"""
import json
from pathlib import Path
import re

from public_api_notes import NOTES, render_note

PARAMETER_NOTES = {
    ('api-PlanValidationError-from_diagnostics', '`errors`'): 'Nonempty sequence of individual configuration errors. A single error without blocked checks is returned unchanged.',
    ('api-PlanValidationError-from_diagnostics', '`blocked`'): 'Sequence of blocked-check dictionaries with path and reason. An empty tuple means no blocked checks were recorded.',
}


def sections(text):
    """按公开锚点切分，返回前言及有序正文；保留未生成的行为文字。"""
    markers = list(re.finditer(r'<a id="(api-[^"]+)"></a>', text))
    if not markers:
        raise ValueError('API page has no member anchor')
    return text[:markers[0].start()], [(marker[1], text[marker.start():markers[i+1].start() if i+1<len(markers) else len(text)])
                                          for i, marker in enumerate(markers)]


def english_links(text):
    """英文页深一层，仅调整源码及模块参考路径。"""
    return text.replace('](../reference/', '](../../reference/').replace('](../../../src/', '](../../../../src/')


def synchronize_page(source, translated, baseline):
    """以中文生成页修复英文事实列，缺译成员/参数时拒绝完成。"""
    translated = re.sub(r'(?ms)^## Source locations\s*\n.*?(?=^## |\Z)', '', translated)
    intro, targets = sections(translated)
    # 成员名是Python标识符，必须作为代码显示，避免双下划线被Markdown当成强调。
    intro = re.sub(r'(?m)^- \[([^`\]\n]+)\]\((#api-[^)]+)\)', r'- [`\1`](\2)', intro)
    _, originals = sections(source)
    expected = dict(originals)
    if set(expected) != {key for key, _ in targets}:
        raise ValueError('English member coverage differs from the current public API')
    result = [intro]
    for key, text in targets:
        original = expected[key]
        signatures = re.findall(r'```python\n(.*?)\n```', original, re.S)
        if signatures:
            text, count = re.subn(r'```python\n.*?\n```', lambda match: '```python\n'+signatures[0]+'\n```', text, count=1, flags=re.S)
            if count != 1:
                # 属性页先前只有读取说明；补入与中文相同的属性类型签名。
                text = re.sub(r'(?m)^(#{2,4} `[^`]+`\s*)$', lambda match: match[0]+'\n```python\n'+signatures[0]+'\n```\n', text, count=1)
        rows = {}
        for line in original.splitlines():
            cells = [cell.strip() for cell in line.strip().split('|')]
            if len(cells) == 7 and cells[1].startswith('`'):
                rows[cells[1]] = cells
        missing_table = [name for name in rows if not re.search(r'\|\s*'+re.escape(name)+r'\s*\|', text)]
        if missing_table:
            text += '\n| Name | Type | Required | Default | Purpose |\n|---|---|---|---|---|\n'
            for name in missing_table:
                description = PARAMETER_NOTES.get((key, name))
                if description is None:
                    raise ValueError('English parameter explanation missing: '+key+' '+name)
                text += f'|{name}||||{description}|\n'
        seen = set()
        lines = []
        for line in text.splitlines():
            cells = [cell.strip() for cell in line.strip().split('|')]
            if len(cells) == 6 and 'Required' in cells[3]:
                line = '| Name | Type | Required | Default | Purpose, choices, and effect |'
            elif len(cells) == 6 and cells[1].startswith('---'):
                line = '|---|---|---|---|---|'
            if len(cells) in (6,7) and cells[1] in rows:
                if len(cells) == 6:
                    cells.insert(4, '')
                fact = rows[cells[1]]
                seen.add(cells[1])
                required = {'是':'Yes','否':'No','不填写':'Not supplied','不直接填写':'Not supplied directly',
                            '类成员，不作为构造参数填写':'Class member, not a constructor argument'}
                defaults = {'无':'No default','无默认值':'No default','构造时计算':'Computed during construction',
                            '由自定义构造器建立；见 __init__':'Set by the custom constructor; see `__init__`'}
                cells[2] = english_links(fact[2]).replace(' 或 ', ' or ')
                cells[3] = required.get(fact[3], fact[3])
                cells[4] = defaults.get(fact[4], fact[4])
                # 公开分析配置版本已统一为4；不改未触及的业务说明。
                if cells[1] == '`config_version`':
                    cells[5] = 'Analysis configuration structure version: native integer 4. This is not the software or preset version. Boolean values and other versions are rejected.'
                line = '|'.join(cells)
            lines.append(line)
        if seen != set(rows):
            raise ValueError('English parameter explanation missing: '+key+' '+str(sorted(set(rows)-seen)))
        result.append('\n'.join(lines).rstrip()+'\n\n')
    locations = []
    for match in re.finditer(r'^源码：(.*)$', source, re.M):
        link = re.search(r'\[[^\n]+?\]\([^\n]+?\)', match[1])
        if link:
            locations.append('- '+english_links(link[0])+f' — line at `{baseline}`.\n')
    if locations:
        result.extend(['## Source locations\n\n', *dict.fromkeys(locations)])
    return ''.join(result).rstrip()+'\n'


def synchronize(current):
    """同步本次清单中的全部英文API页，不扫描或改写历史版手册。"""
    current = Path(current)
    public = json.loads((current/'public-api.json').read_bytes())
    baseline = json.loads((current/'documentation.json').read_bytes())['baseline']
    for item in public['objects']:
        source = (current/'public-api'/f'{item["name"]}.md').read_text(encoding='utf8')
        target = current/'en/public-api'/f'{item["name"]}.md'
        if item['name'] in NOTES:
            text = render_note(item, source, 'en')
            # 新页同样用统一基线源码定位，避免保留中文定位句。
            text = re.sub(r'(?m)^源码：(.*)$', lambda m: 'Source: '+english_links(m[1]), text)
            text = text.replace('（行号属于 ', ' (line at ').replace('）。', ').')
        else:
            text = synchronize_page(source, target.read_text(encoding='utf8'), baseline)
        target.write_text(text, encoding='utf8', newline='\n')
