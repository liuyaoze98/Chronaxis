"""静态核对当前离线手册；代码复制文本与两种Markdown围栏逐块比较，不代替浏览器测试。"""
from html.parser import HTMLParser
from pathlib import Path
import argparse
import json
import re
from public_docs import reading_text
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1] / 'Docs/Current'


def fenced_blocks(text):
    """读取反引号或波浪线围栏；返回代码内容，不包括围栏本身。"""
    blocks, current, marker = [], [], None
    for line in text.splitlines():
        if marker is None:
            match = re.match(r'^(`{3,}|~{3,})[^\n]*$', line)
            if match:
                marker = match[1]
                current = []
        elif re.fullmatch(re.escape(marker[0]) + '{' + str(len(marker)) + r',}\s*', line):
            blocks.append('\n'.join(current).rstrip('\n'))
            marker = None
        else:
            current.append(line)
    if marker:
        raise AssertionError('未结束的代码围栏')
    return blocks


class Page(HTMLParser):
    """提取高亮代码的真实文本及链接，不将span样式混入复制内容。"""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.codes, self.links, self.ids = [], [], set()
        self.duplicate_ids = set()
        self.in_code = False
        self.paragraph = None
        self.markup_leaks = []
        self.tables = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'p':self.paragraph = ''
        if tag == 'table':self.tables.append([])
        if tag == 'tr':self.row = []
        if tag in ('td', 'th'):self.cell = ''
        if 'id' in attrs:
            if attrs['id'] in self.ids:self.duplicate_ids.add(attrs['id'])
            self.ids.add(attrs['id'])
        for name in ('href', 'src'):
            if name in attrs:
                self.links.append(attrs[name])
        if tag == 'code' and 'hljs' in attrs.get('class', '').split():
            self.in_code = True
            self.codes.append('')

    def handle_endtag(self, tag):
        if tag == 'p' and self.paragraph is not None:
            if re.match(r'^\s*\|.*\|', self.paragraph):self.markup_leaks.append(self.paragraph[:160])
            self.paragraph = None
        if tag in ('td', 'th') and self.cell is not None:
            if self.row is not None:self.row.append(self.cell.strip())
            self.cell = None
        if tag == 'tr' and self.row is not None:
            if self.tables:self.tables[-1].append(self.row)
            self.row = None
        if tag == 'code':
            self.in_code = False

    def handle_data(self, data):
        if self.paragraph is not None:self.paragraph += data
        if self.cell is not None:self.cell += data
        if self.in_code:
            self.codes[-1] += data


def verify_links(directory):
    """检查全部页面资源、锚点和搜索目标。返回计数；失效链接抛AssertionError。"""
    directory = directory.resolve()
    pages = {}
    for path in directory.rglob('*.html'):
        page = Page()
        page.feed(path.read_text(encoding='utf8'))
        assert not page.duplicate_ids, (str(path), sorted(page.duplicate_ids), '重复HTML ID')
        assert not page.markup_leaks, (str(path), page.markup_leaks, 'Markdown表格泄漏到段落')
        pages[path.resolve()] = page
    # 字段文字存在不等于形成表格：完整参考的22个字段必须位于同一张三列表中。
    fields = set('name source field dtype unit valid_for period conversion conversion.input_unit conversion.scale conversion.offset choices valid_range invalid_values sample_policy same_time_policy semantic_id semantic_contract_version mapping_version sign_convention measurement_location metadata'.split())
    signal_tables = pages[(directory / 'signals.html').resolve()].tables
    assert any(fields <= {r[0] for r in table if len(r) == 3} for table in signal_tables), '信号完整字段参考缺少真实三列表行'
    terms = (directory / 'terms.html').read_text(encoding='utf8')
    assert '**角色要求' not in terms, '术语强调标记未渲染'
    count = 0
    def check(source, url):
        nonlocal count
        parts = urlsplit(url)
        assert parts.scheme != 'file', (source, url, '机器绝对路径')
        if parts.scheme in ('https', 'http', 'mailto'):
            return
        assert not parts.scheme and not parts.netloc, (source, url, '未知链接协议')
        target = (source.parent / unquote(parts.path)).resolve() if parts.path else source
        assert target.is_relative_to(directory), (source, url, '离开离线目录')
        assert target.is_file(), (source, url, '目标不存在')
        if parts.fragment and target in pages:
            assert unquote(parts.fragment) in pages[target].ids, (source, url, '锚点不存在')
        count += 1
    for source, page in pages.items():
        for link in page.links:
            check(source, link)
    raw = (directory / 'search-data.js').read_text(encoding='utf8')
    entries = json.loads(raw.removeprefix('window.DOC_SEARCH=').strip().removesuffix(';'))
    for entry in entries:
        check(directory / 'index.html', entry['url'])
    return {'html_pages':len(pages), 'local_references':count, 'search_targets':len(entries)}


def main():
    """核对正文复制文本和离线链接；--root可检查搬移后的目录，失败即非零退出。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT / '_build/html')
    args = parser.parse_args()
    total = 0
    for source in list(ROOT.glob('*.md')) + list((ROOT / 'en').glob('*.md')):
        text = reading_text(source.read_text(encoding='utf8'))
        expected = fenced_blocks(text)
        page = Page()
        page.feed((args.root / source.relative_to(ROOT).with_suffix('.html')).read_text(encoding='utf8'))
        assert expected == page.codes, (source.name, len(expected), len(page.codes))
        total += len(expected)
    for name in ('quickstart', 'api-usage', 'batch', 'imports'):
        html = (args.root / (name + '.html')).read_text(encoding='utf8')
        assert 'copy-code' in html and 'hljs-' in html, name
    print(f'人工正文{total}段代码复制文本逐字一致；反引号/波浪线及高亮标记通过。')
    print(json.dumps(verify_links(args.root), ensure_ascii=False))


if __name__ == '__main__':
    main()
